import asyncio
import contextlib
import json
import logging
import time
import uuid
from concurrent.futures import Future
from dataclasses import dataclass, field
from typing import Any

from fastapi import WebSocket

from app.core.config import get_settings
from app.services.csv_writer import csv_writer_service
from generated.control_pb2 import ControlCommand, ControlCommandType

logger = logging.getLogger(__name__)
PROTO_SCHEMA_VERSION = "1.1.0"


@dataclass
class DeviceStreamState:
    last_received_seq: int = 0
    last_heartbeat_monotonic: float = field(default_factory=time.monotonic)
    received_batches: int = 0
    duplicate_batches: int = 0
    total_samples: int = 0
    warned_overload: bool = False


@dataclass
class DashboardConnection:
    websocket: WebSocket
    queue: asyncio.Queue[dict[str, Any]]
    sender_task: asyncio.Task[None]


class WsRuntime:
    def __init__(self) -> None:
        self._settings = get_settings()
        self._lock = asyncio.Lock()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._device_connections: dict[str, WebSocket] = {}
        self._dashboard_connections: dict[str, list[DashboardConnection]] = {}
        self._device_states: dict[tuple[str, str], DeviceStreamState] = {}
        self._device_session_map: dict[str, str] = {}
        self._clock_sync_pending: dict[tuple[str, str, str], asyncio.Future[dict[str, Any]]] = {}
        self._stop_ack_pending: dict[tuple[str, str, str], asyncio.Future[bool]] = {}
        self._timeout_task: asyncio.Task[None] | None = None

    def start(self) -> None:
        self._loop = asyncio.get_running_loop()
        if self._timeout_task is None or self._timeout_task.done():
            self._timeout_task = asyncio.create_task(self._timeout_loop(), name="ws-device-timeout-loop")

    async def stop(self) -> None:
        if self._timeout_task is not None:
            self._timeout_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._timeout_task
            self._timeout_task = None

        async with self._lock:
            dashboards = self._dashboard_connections
            self._dashboard_connections = {}
            devices = self._device_connections
            self._device_connections = {}
            self._device_session_map = {}
            self._device_states = {}
            pending = list(self._clock_sync_pending.values())
            self._clock_sync_pending = {}
            stop_pending = list(self._stop_ack_pending.values())
            self._stop_ack_pending = {}

        for future in pending:
            if not future.done():
                future.cancel()

        for future in stop_pending:
            if not future.done():
                future.cancel()

        for websocket in devices.values():
            with contextlib.suppress(Exception):
                await websocket.close(code=1001)

        for connections in dashboards.values():
            for connection in connections:
                connection.sender_task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await connection.sender_task
                with contextlib.suppress(Exception):
                    await connection.websocket.close(code=1001)

    async def register_dashboard(self, session_id: str, websocket: WebSocket) -> DashboardConnection:
        await websocket.accept()
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=self._settings.ws_dashboard_queue_size)
        sender_task = asyncio.create_task(self._dashboard_sender(websocket, queue), name=f"dashboard-sender-{session_id}")
        connection = DashboardConnection(websocket=websocket, queue=queue, sender_task=sender_task)

        async with self._lock:
            self._dashboard_connections.setdefault(session_id, []).append(connection)

        return connection

    async def unregister_dashboard(self, session_id: str, connection: DashboardConnection) -> None:
        async with self._lock:
            connections = self._dashboard_connections.get(session_id)
            if connections and connection in connections:
                connections.remove(connection)
                if not connections:
                    self._dashboard_connections.pop(session_id, None)

        connection.sender_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await connection.sender_task

    async def register_device(self, device_id: str, session_id: str, websocket: WebSocket) -> None:
        async with self._lock:
            old_ws = self._device_connections.get(device_id)
            self._device_connections[device_id] = websocket
            self._device_session_map[device_id] = session_id
            self._device_states.setdefault((session_id, device_id), DeviceStreamState())

        if old_ws is not None and old_ws is not websocket:
            with contextlib.suppress(Exception):
                await old_ws.close(code=1000)

    async def unregister_device(self, device_id: str, websocket: WebSocket) -> None:
        removed = False
        session_id = None
        async with self._lock:
            current = self._device_connections.get(device_id)
            if current is websocket:
                self._device_connections.pop(device_id, None)
                session_id = self._device_session_map.pop(device_id, None)
                removed = True

                pending_keys = [key for key in self._clock_sync_pending if key[1] == device_id]
                for key in pending_keys:
                    future = self._clock_sync_pending.pop(key)
                    if not future.done():
                        future.cancel()

                pending_stop_keys = [key for key in self._stop_ack_pending if key[1] == device_id]
                for key in pending_stop_keys:
                    future = self._stop_ack_pending.pop(key)
                    if not future.done():
                        future.cancel()

        if removed and session_id:
            await self.publish_device_event(
                session_id,
                {
                    "type": "DEVICE_OFFLINE",
                    "device_id": device_id,
                    "reason": "disconnect",
                },
            )

    async def touch_heartbeat(self, session_id: str, device_id: str) -> None:
        async with self._lock:
            state = self._device_states.setdefault((session_id, device_id), DeviceStreamState())
            state.last_heartbeat_monotonic = time.monotonic()

    async def process_batch(
        self,
        session_id: str,
        device_id: str,
        start_seq: int,
        end_seq: int,
        sample_count: int,
        preview_payload: dict[str, Any],
        duplicate_override: bool | None = None,
        last_received_seq_override: int | None = None,
    ) -> dict[str, Any]:
        now = time.monotonic()
        async with self._lock:
            state = self._device_states.setdefault((session_id, device_id), DeviceStreamState())
            state.last_heartbeat_monotonic = now

            duplicate = end_seq <= state.last_received_seq if duplicate_override is None else duplicate_override
            if duplicate:
                state.duplicate_batches += 1
            else:
                state.last_received_seq = end_seq if last_received_seq_override is None else last_received_seq_override
                state.received_batches += 1
                state.total_samples += sample_count

            if duplicate and last_received_seq_override is not None:
                state.last_received_seq = last_received_seq_override

            overload = sample_count > self._settings.ws_max_batch_samples
            if overload:
                state.warned_overload = True

            last_received_seq = state.last_received_seq
            duplicate_batches = state.duplicate_batches

        if not duplicate:
            await self.publish_preview_event(session_id, device_id, start_seq, end_seq, preview_payload)

        if overload:
            await self.publish_warning(
                session_id,
                device_id,
                f"batch sample_count={sample_count} melebihi limit {self._settings.ws_max_batch_samples}",
            )

        return {
            "type": "ACK",
            "session_id": session_id,
            "device_id": device_id,
            "batch_start_seq": start_seq,
            "batch_end_seq": end_seq,
            "last_received_seq": last_received_seq,
            "duplicate": duplicate,
            "duplicate_batches": duplicate_batches,
        }

    async def get_backend_last_seq(self, session_id: str, device_id: str) -> int:
        in_memory_last_seq = 0
        async with self._lock:
            state = self._device_states.get((session_id, device_id))
            if state is not None:
                in_memory_last_seq = state.last_received_seq

        durable_last_seq = csv_writer_service.get_last_seq_durable(session_id, device_id)
        return max(in_memory_last_seq, durable_last_seq)

    async def publish_session_event(self, session_id: str, payload: dict[str, Any]) -> None:
        await self._broadcast(session_id, payload, drop_if_busy=False)

    def publish_session_event_sync(self, session_id: str, payload: dict[str, Any]) -> Future[Any] | None:
        return self._submit_from_thread(self.publish_session_event(session_id, payload))

    async def publish_annotation_event(self, session_id: str, payload: dict[str, Any]) -> None:
        await self._broadcast(session_id, payload, drop_if_busy=True)

    async def publish_device_event(self, session_id: str, payload: dict[str, Any]) -> None:
        await self._broadcast(session_id, payload, drop_if_busy=False)

    async def send_command_to_device(self, session_id: str, device_id: str, payload: dict[str, Any]) -> bool:
        async with self._lock:
            websocket = self._device_connections.get(device_id)
            mapped_session = self._device_session_map.get(device_id)

        if websocket is None or mapped_session != session_id:
            return False

        try:
            binary_payload = self._encode_control_command(payload)
            if binary_payload is not None:
                await websocket.send_bytes(binary_payload)
            else:
                await websocket.send_text(json.dumps(payload, ensure_ascii=True))
            return True
        except Exception:
            return False

    async def broadcast_command_to_session_devices(self, session_id: str, payload: dict[str, Any]) -> list[str]:
        async with self._lock:
            candidates = [
                (device_id, websocket)
                for device_id, websocket in self._device_connections.items()
                if self._device_session_map.get(device_id) == session_id
            ]

        sent: list[str] = []
        encoded_json = json.dumps(payload, ensure_ascii=True)
        encoded_binary = self._encode_control_command(payload)
        for device_id, websocket in candidates:
            try:
                if encoded_binary is not None:
                    await websocket.send_bytes(encoded_binary)
                else:
                    await websocket.send_text(encoded_json)
                sent.append(device_id)
            except Exception:
                continue
        return sent

    async def get_online_device_ids(self, session_id: str) -> list[str]:
        async with self._lock:
            return sorted(
                [
                    device_id
                    for device_id in self._device_connections
                    if self._device_session_map.get(device_id) == session_id
                ]
            )

    async def request_clock_sync_probe(self, session_id: str, device_id: str, timeout_seconds: float) -> dict[str, Any] | None:
        ping_id = uuid.uuid4().hex
        server_send_unix_ns = time.time_ns()

        async with self._lock:
            websocket = self._device_connections.get(device_id)
            mapped_session = self._device_session_map.get(device_id)
            if websocket is None or mapped_session != session_id:
                return None
            future: asyncio.Future[dict[str, Any]] = asyncio.get_running_loop().create_future()
            self._clock_sync_pending[(session_id, device_id, ping_id)] = future

        payload = {
            "type": "CLOCK_SYNC_PING",
            "session_id": session_id,
            "device_id": device_id,
            "ping_id": ping_id,
            "server_send_unix_ns": server_send_unix_ns,
        }
        try:
            encoded = self._encode_control_command(payload)
            if encoded is not None:
                await websocket.send_bytes(encoded)
            else:
                await websocket.send_text(json.dumps(payload, ensure_ascii=True))
        except Exception:
            async with self._lock:
                self._clock_sync_pending.pop((session_id, device_id, ping_id), None)
            return None

        try:
            response = await asyncio.wait_for(future, timeout=timeout_seconds)
            response["server_send_unix_ns"] = server_send_unix_ns
            return response
        except Exception:
            return None
        finally:
            async with self._lock:
                self._clock_sync_pending.pop((session_id, device_id, ping_id), None)

    async def register_clock_sync_pong(
        self,
        *,
        session_id: str,
        device_id: str,
        ping_id: str,
        device_unix_ns: int,
    ) -> bool:
        async with self._lock:
            future = self._clock_sync_pending.get((session_id, device_id, ping_id))

        if future is None or future.done():
            return False

        future.set_result(
            {
                "session_id": session_id,
                "device_id": device_id,
                "ping_id": ping_id,
                "device_unix_ns": device_unix_ns,
                "server_recv_unix_ns": time.time_ns(),
            }
        )
        return True

    async def request_stop_acks(
        self,
        session_id: str,
        device_ids: list[str],
        timeout_seconds: float,
    ) -> dict[str, Any]:
        unique_device_ids = sorted(set(device_ids))
        command_id = uuid.uuid4().hex

        async with self._lock:
            candidates = {
                device_id: self._device_connections.get(device_id)
                for device_id in unique_device_ids
                if self._device_session_map.get(device_id) == session_id and self._device_connections.get(device_id) is not None
            }
            futures: dict[str, asyncio.Future[bool]] = {
                device_id: asyncio.get_running_loop().create_future() for device_id in candidates
            }
            for device_id, future in futures.items():
                self._stop_ack_pending[(session_id, device_id, command_id)] = future

        payload = {
            "type": "STOP_SESSION",
            "session_id": session_id,
            "command_id": command_id,
        }
        encoded_binary = self._encode_control_command(payload)
        encoded_json = json.dumps(payload, ensure_ascii=True)

        sent_devices: list[str] = []
        for device_id, websocket in candidates.items():
            try:
                if encoded_binary is not None:
                    await websocket.send_bytes(encoded_binary)
                else:
                    await websocket.send_text(encoded_json)
                sent_devices.append(device_id)
            except Exception:
                future = futures.get(device_id)
                if future is not None and not future.done():
                    future.cancel()

        acked_devices: list[str] = []
        pending_devices: list[str] = []
        for device_id in sent_devices:
            future = futures[device_id]
            try:
                await asyncio.wait_for(future, timeout=timeout_seconds)
                acked_devices.append(device_id)
            except Exception:
                pending_devices.append(device_id)

        async with self._lock:
            for device_id in sent_devices:
                self._stop_ack_pending.pop((session_id, device_id, command_id), None)

        unsent_devices = sorted(set(unique_device_ids) - set(sent_devices))
        return {
            "command_id": command_id,
            "sent_devices": sent_devices,
            "acked_devices": acked_devices,
            "pending_devices": sorted(set(pending_devices + unsent_devices)),
        }

    async def register_stop_session_ack(self, *, session_id: str, device_id: str, command_id: str) -> bool:
        async with self._lock:
            future = self._stop_ack_pending.get((session_id, device_id, command_id))

        if future is None or future.done():
            return False

        future.set_result(True)
        return True

    def _encode_control_command(self, payload: dict[str, Any]) -> bytes | None:
        msg_type = str(payload.get("type", "")).upper()
        command_map: dict[str, int] = {
            "START_SESSION": ControlCommandType.START_SESSION,
            "STOP_SESSION": ControlCommandType.STOP_SESSION,
            "CLOCK_SYNC_PING": ControlCommandType.SYNC_CLOCK,
            "SYNC_REQUIRED": ControlCommandType.SYNC_REQUIRED,
            "PING": ControlCommandType.PING,
            "CLOCK_SYNC_PONG": ControlCommandType.CLOCK_SYNC_PONG,
            "ACK": ControlCommandType.ACK,
        }
        command = command_map.get(msg_type)
        if command is None:
            return None

        message = ControlCommand(
            command=command,
            session_id=str(payload.get("session_id", "")),
            issued_at_server_unix_ns=int(payload.get("issued_at_server_unix_ns", time.time_ns()) or time.time_ns()),
            schema_version=str(payload.get("schema_version", PROTO_SCHEMA_VERSION)),
        )

        sampling_hz = payload.get("target_sampling_hz", payload.get("sampling_hz"))
        if sampling_hz is not None:
            message.target_sampling_hz = int(sampling_hz)
        if payload.get("recording_start_seq") is not None:
            message.recording_start_seq = int(payload["recording_start_seq"])
        if payload.get("server_start_time_unix_ns") is not None:
            message.server_start_time_unix_ns = int(payload["server_start_time_unix_ns"])
        if payload.get("backend_last_seq") is not None:
            message.backend_last_seq = int(payload["backend_last_seq"])
        command_id = payload.get("command_id")
        if command_id is None and msg_type == "CLOCK_SYNC_PING":
            command_id = payload.get("ping_id")
        if command_id is not None:
            message.command_id = str(command_id)
        if payload.get("ack") is not None:
            message.ack = bool(payload["ack"])
        if payload.get("device_unix_ns") is not None:
            message.device_unix_ns = int(payload["device_unix_ns"])
        if payload.get("batch_start_seq") is not None:
            message.batch_start_seq = int(payload["batch_start_seq"])
        if payload.get("batch_end_seq") is not None:
            message.batch_end_seq = int(payload["batch_end_seq"])
        if payload.get("duplicate_batches") is not None:
            message.duplicate_batches = int(payload["duplicate_batches"])
        if payload.get("duplicate") is not None:
            message.duplicate = bool(payload["duplicate"])
        if payload.get("detail") is not None:
            message.detail = str(payload["detail"])

        return message.SerializeToString()

    async def publish_warning(self, session_id: str, device_id: str, warning: str) -> None:
        await self._broadcast(
            session_id,
            {
                "type": "INGEST_WARNING",
                "device_id": device_id,
                "warning": warning,
            },
            drop_if_busy=True,
        )

    def publish_warning_sync(self, session_id: str, device_id: str, warning: str) -> Future[Any] | None:
        return self._submit_from_thread(self.publish_warning(session_id, device_id, warning))

    def _submit_from_thread(self, coroutine: Any) -> Future[Any] | None:
        loop = self._loop
        if loop is None or loop.is_closed():
            return None
        return asyncio.run_coroutine_threadsafe(coroutine, loop)

    async def publish_preview_event(
        self,
        session_id: str,
        device_id: str,
        start_seq: int,
        end_seq: int,
        preview_payload: dict[str, Any],
    ) -> None:
        await self._broadcast(
            session_id,
            {
                "type": "SENSOR_PREVIEW",
                "session_id": session_id,
                "device_id": device_id,
                "start_seq": start_seq,
                "end_seq": end_seq,
                "preview": preview_payload,
            },
            drop_if_busy=True,
        )

    async def _broadcast(self, session_id: str, payload: dict[str, Any], drop_if_busy: bool) -> None:
        async with self._lock:
            connections = list(self._dashboard_connections.get(session_id, []))

        stale, dropped_preview = await self._enqueue_payload_for_connections(
            connections=connections,
            payload=payload,
            drop_if_busy=drop_if_busy,
            session_id=session_id,
        )

        if dropped_preview and payload.get("type") == "SENSOR_PREVIEW":
            warning_payload = {
                "type": "INGEST_WARNING",
                "device_id": payload.get("device_id", "unknown"),
                "warning": "dashboard backpressure, preview event dropped",
            }
            self._enqueue_warning_non_blocking(connections, warning_payload)

        if stale:
            for connection in stale:
                await self.unregister_dashboard(session_id, connection)

    async def _enqueue_payload_for_connections(
        self,
        *,
        connections: list[DashboardConnection],
        payload: dict[str, Any],
        drop_if_busy: bool,
        session_id: str,
    ) -> tuple[list[DashboardConnection], bool]:
        stale: list[DashboardConnection] = []
        dropped_preview = False

        for connection in connections:
            try:
                if drop_if_busy:
                    connection.queue.put_nowait(payload)
                else:
                    await connection.queue.put(payload)
            except asyncio.QueueFull:
                logger.warning("Dropping preview event due to dashboard backpressure: session=%s", session_id)
                dropped_preview = True
            except Exception:
                stale.append(connection)

        return stale, dropped_preview

    @staticmethod
    def _enqueue_warning_non_blocking(connections: list[DashboardConnection], warning_payload: dict[str, Any]) -> None:
        for connection in connections:
            try:
                connection.queue.put_nowait(warning_payload)
            except Exception:
                continue

    async def snapshot_for_dashboard(self, session_id: str) -> dict[str, Any]:
        async with self._lock:
            devices = []
            for (state_session_id, device_id), state in self._device_states.items():
                if state_session_id != session_id:
                    continue
                online = self._device_session_map.get(device_id) == session_id and device_id in self._device_connections
                devices.append(
                    {
                        "device_id": device_id,
                        "online": online,
                        "last_received_seq": state.last_received_seq,
                        "received_batches": state.received_batches,
                        "duplicate_batches": state.duplicate_batches,
                        "total_samples": state.total_samples,
                    }
                )

        return {
            "type": "DASHBOARD_SNAPSHOT",
            "session_id": session_id,
            "devices": sorted(devices, key=lambda item: item["device_id"]),
        }

    async def _dashboard_sender(self, websocket: WebSocket, queue: asyncio.Queue[dict[str, Any]]) -> None:
        while True:
            payload = await queue.get()
            await websocket.send_text(json.dumps(payload, ensure_ascii=True))

    async def _timeout_loop(self) -> None:
        while True:
            await asyncio.sleep(1.0)
            timeout_seconds = self._settings.ws_device_timeout_seconds
            now = time.monotonic()

            timed_out: list[tuple[str, str]] = []
            async with self._lock:
                for (session_id, device_id), state in self._device_states.items():
                    is_online = self._device_session_map.get(device_id) == session_id and device_id in self._device_connections
                    if not is_online:
                        continue
                    if now - state.last_heartbeat_monotonic > timeout_seconds:
                        timed_out.append((session_id, device_id))

            for session_id, device_id in timed_out:
                async with self._lock:
                    websocket = self._device_connections.pop(device_id, None)
                    mapped_session = self._device_session_map.get(device_id)
                    if mapped_session == session_id:
                        self._device_session_map.pop(device_id, None)

                if websocket is not None:
                    with contextlib.suppress(Exception):
                        await websocket.close(code=1011)

                await self.publish_device_event(
                    session_id,
                    {
                        "type": "DEVICE_OFFLINE",
                        "device_id": device_id,
                        "reason": "heartbeat_timeout",
                    },
                )


ws_runtime = WsRuntime()
