import asyncio
import contextlib
import json
import logging
import time
from concurrent.futures import Future
from dataclasses import dataclass, field
from typing import Any

from fastapi import WebSocket

from app.core.config import get_settings
from app.services.csv_writer import csv_writer_service

logger = logging.getLogger(__name__)


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
