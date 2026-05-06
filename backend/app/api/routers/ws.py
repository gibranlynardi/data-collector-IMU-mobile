import json
import re
from dataclasses import dataclass
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from sqlalchemy.orm import Session

from app.core.auth import verify_device_enrollment_token, verify_operator_token
from app.db.models import Annotation, Device, Session as SessionModel, SessionDevice
from app.db.session import SessionLocal
from generated.control_pb2 import ControlCommand, ControlCommandType
from generated.sensor_sample_pb2 import SensorBatch
from app.services.ingest_pipeline import IngestProtocolError, ingest_ws_binary_batch
from app.services.ws_runtime import ws_runtime

router = APIRouter(tags=["ws"])
DEVICE_ID_PATTERN = r"^DEVICE-(CHEST|WAIST|THIGH|OTHER)-\d{3}$"
SESSION_ID_PATTERN = r"^\d{8}_\d{6}_[A-F0-9]{8}$"
HANDSHAKE_ALLOWED_SESSION_STATES = {"CREATED", "RUNNING", "SYNCING"}


def _match_pattern(value: str, pattern: str) -> bool:
    return bool(re.fullmatch(pattern, value))


@dataclass
class DeviceConnectionContext:
    device_id: str
    session_id: str | None
    role: str
    session_state: str
    drain_only: bool
    local_last_seq: int
    backend_last_seq: int


async def _send_json(websocket: WebSocket, payload: dict[str, Any]) -> None:
    await websocket.send_text(json.dumps(payload, ensure_ascii=True))


async def _send_ws_error(websocket: WebSocket, code: str, detail: str) -> None:
    await _send_json(
        websocket,
        {
            "type": "ERROR",
            "code": code,
            "detail": detail,
        },
    )


def _extract_hello_payload(raw: str) -> dict[str, Any] | None:
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


def _select_session_id(hello: dict[str, Any]) -> str:
    return str(hello.get("session_id", ""))


def _normalize_session_id(value: str | None) -> str | None:
    if value is None:
        return None
    session_id = value.strip()
    return session_id or None


def _resolve_session_id_for_message(context: DeviceConnectionContext, candidate: str | None) -> str | None:
    explicit = _normalize_session_id(candidate)
    if explicit is not None:
        return explicit
    return _normalize_session_id(context.session_id)


async def _perform_handshake(websocket: WebSocket, device_id: str, db: Session) -> DeviceConnectionContext | None:
    hello_raw = await websocket.receive_text()
    hello = _extract_hello_payload(hello_raw)
    if hello is None:
        await websocket.close(code=1003)
        return None

    if hello.get("type") != "HELLO" or str(hello.get("device_id", "")) != device_id:
        await websocket.close(code=1008)
        return None

    enrollment_token = str(hello.get("enrollment_token", "") or "").strip()
    if not verify_device_enrollment_token(enrollment_token or None):
        await _send_ws_error(
            websocket,
            code="DEVICE_ENROLLMENT_TOKEN_INVALID",
            detail="device enrollment token invalid atau missing",
        )
        await websocket.close(code=1008)
        return None

    device = db.get(Device, device_id)
    if not device:
        await _send_ws_error(
            websocket,
            code="DEVICE_NOT_REGISTERED",
            detail="device belum terdaftar, lakukan POST /devices/register dulu",
        )
        await websocket.close(code=1008)
        return None

    bound_session_id = _normalize_session_id(_select_session_id(hello))
    session: SessionModel | None = None
    if bound_session_id is not None:
        if not _match_pattern(bound_session_id, SESSION_ID_PATTERN):
            await _send_ws_error(
                websocket,
                code="SESSION_INVALID",
                detail="session_id tidak valid",
            )
            await websocket.close(code=1008)
            return None

        session = db.get(SessionModel, bound_session_id)
        if not session:
            await _send_ws_error(websocket, code="SESSION_NOT_FOUND", detail="session tidak ditemukan")
            await websocket.close(code=1008)
            return None
        if session.status not in HANDSHAKE_ALLOWED_SESSION_STATES:
            await _send_ws_error(
                websocket,
                code="SESSION_NOT_CONNECTABLE",
                detail=f"session status {session.status} tidak menerima koneksi device",
            )
            await websocket.close(code=1008)
            return None

    await ws_runtime.register_device(device_id=device_id, session_id=bound_session_id or "", websocket=websocket)

    role = (device.device_role or str(hello.get("device_role", "other"))).lower()
    requested_role = str(hello.get("device_role", role)).lower()
    if requested_role != role:
        await _send_ws_error(
            websocket,
            code="DEVICE_ROLE_MISMATCH",
            detail=f"device_role mismatch: request={requested_role} registered={role}",
        )
        await websocket.close(code=1008)
        return None

    device.connected = True
    if device.device_role != role:
        device.device_role = role
    db.commit()

    local_last_seq = int(hello.get("local_last_seq", 0) or 0)
    backend_last_seq = await ws_runtime.get_backend_last_seq(bound_session_id, device_id) if bound_session_id else 0
    session_state = session.status if session is not None else "UNBOUND"
    drain_only = session_state == "SYNCING"

    return DeviceConnectionContext(
        device_id=device_id,
        session_id=bound_session_id,
        role=role,
        session_state=session_state,
        drain_only=drain_only,
        local_last_seq=local_last_seq,
        backend_last_seq=backend_last_seq,
    )


async def _send_hello_ack(websocket: WebSocket, context: DeviceConnectionContext) -> None:
    await _send_json(
        websocket,
        {
            "type": "HELLO_ACK",
            "device_id": context.device_id,
            "device_role": context.role,
            "session_id": context.session_id or "",
            "session_state": context.session_state,
            "ingest_mode": "DRAIN_ONLY" if context.drain_only else ("LIVE" if context.session_id else "IDLE"),
            "sampling_allowed": bool(context.session_id) and not context.drain_only,
            "local_last_seq": context.local_last_seq,
            "backend_last_seq": context.backend_last_seq,
        },
    )


def _build_binary_preview(batch: SensorBatch) -> dict[str, Any]:
    last = batch.samples[-1]
    return {
        "sample_count": len(batch.samples),
        "last_sample": {
            "seq": int(last.seq),
            "elapsed_ms": int(last.elapsed_ms),
            "acc_x_g": float(last.acc_x_g),
            "acc_y_g": float(last.acc_y_g),
            "acc_z_g": float(last.acc_z_g),
            "gyro_x_deg": float(last.gyro_x_deg),
            "gyro_y_deg": float(last.gyro_y_deg),
            "gyro_z_deg": float(last.gyro_z_deg),
        },
    }


async def _ack_batch(
    websocket: WebSocket,
    context: DeviceConnectionContext,
    start_seq: int,
    end_seq: int,
    sample_count: int,
    preview_payload: dict[str, Any],
) -> None:
    ack_payload = await ws_runtime.process_batch(
        session_id=context.session_id,
        device_id=context.device_id,
        start_seq=start_seq,
        end_seq=end_seq,
        sample_count=sample_count,
        preview_payload=preview_payload,
    )
    await _send_json(websocket, ack_payload)


async def _ack_batch_with_ingest(
    websocket: WebSocket,
    context: DeviceConnectionContext,
    payload: bytes,
) -> None:
    batch = SensorBatch()
    try:
        batch.ParseFromString(payload)
    except Exception:
        await _send_ws_error(websocket, code="BINARY_PROTO_INVALID", detail="payload protobuf tidak valid")
        return

    resolved_session_id = _resolve_session_id_for_message(context, batch.session_id)
    if resolved_session_id is None or not _match_pattern(resolved_session_id, SESSION_ID_PATTERN):
        await _send_ws_error(websocket, code="SESSION_REQUIRED", detail="session_id wajib untuk ingest")
        return

    ingest_allowed_states = {"RUNNING", "SYNCING"}
    with SessionLocal() as db:
        session = db.get(SessionModel, resolved_session_id)
        if not session:
            await _send_ws_error(websocket, code="SESSION_NOT_FOUND", detail="session tidak ditemukan")
            return
        if session.status not in ingest_allowed_states:
            await _send_ws_error(
                websocket,
                code="SESSION_NOT_RUNNING",
                detail=f"session status {session.status} tidak menerima ingest (hanya RUNNING/SYNCING)",
            )
            return

        mapped = (
            db.query(SessionDevice)
            .filter(SessionDevice.session_id == resolved_session_id, SessionDevice.device_id == context.device_id)
            .first()
        )
        if not mapped:
            await _send_ws_error(
                websocket,
                code="DEVICE_NOT_IN_SESSION",
                detail="device tidak tergabung pada session ini",
            )
            return

        tracked = db.get(Device, context.device_id)
        tracked_role = (tracked.device_role if tracked and tracked.device_role else "other").lower()
        if tracked_role != context.role:
            await _send_ws_error(
                websocket,
                code="DEVICE_ROLE_MISMATCH",
                detail=f"device_role mismatch: request={context.role} registered={tracked_role}",
            )
            return

    try:
        ingest_ack = ingest_ws_binary_batch(
            payload,
            connection_session_id=resolved_session_id,
            connection_device_id=context.device_id,
            device_role_override=context.role,
        )
    except IngestProtocolError as exc:
        await _send_ws_error(websocket, code=exc.code, detail=exc.detail)
        return

    preview_payload = _build_binary_preview(batch)
    runtime_ack = await ws_runtime.process_batch(
        session_id=resolved_session_id,
        device_id=context.device_id,
        start_seq=int(batch.start_seq),
        end_seq=int(batch.end_seq),
        sample_count=len(batch.samples),
        preview_payload=preview_payload,
        duplicate_override=bool(ingest_ack.get("duplicate", False)),
        last_received_seq_override=int(ingest_ack.get("last_received_seq", 0) or 0),
    )

    await _send_json(
        websocket,
        {
            **runtime_ack,
            "session_id": resolved_session_id,
            "batch_start_seq": int(batch.start_seq),
            "batch_end_seq": int(batch.end_seq),
            "last_received_seq": int(ingest_ack.get("last_received_seq", runtime_ack.get("last_received_seq", 0))),
            "duplicate": bool(ingest_ack.get("duplicate", runtime_ack.get("duplicate", False))),
        },
    )


async def _handle_binary_message(
    websocket: WebSocket,
    context: DeviceConnectionContext,
    payload: bytes,
) -> None:
    control = ControlCommand()
    try:
        control.ParseFromString(payload)
    except Exception:
        control = ControlCommand()

    if control.command != ControlCommandType.CONTROL_COMMAND_TYPE_UNSPECIFIED:
        await _handle_control_message(websocket, context, control)
        return

    await _ack_batch_with_ingest(websocket, context, payload)


async def _handle_control_message(
    websocket: WebSocket,
    context: DeviceConnectionContext,
    payload: ControlCommand,
) -> None:
    resolved_session_id = _resolve_session_id_for_message(context, payload.session_id)
    if resolved_session_id is None:
        await _send_ws_error(websocket, code="SESSION_REQUIRED", detail="session_id wajib untuk control message")
        return

    if payload.command == ControlCommandType.CLOCK_SYNC_PONG:
        ping_id = str(payload.command_id or "")
        device_unix_ns = int(payload.device_unix_ns or 0)
        if not ping_id or device_unix_ns <= 0:
            await _send_ws_error(websocket, code="CLOCK_SYNC_PONG_INVALID", detail="command_id/device_unix_ns wajib")
            return

        matched = await ws_runtime.register_clock_sync_pong(
            session_id=resolved_session_id,
            device_id=context.device_id,
            ping_id=ping_id,
            device_unix_ns=device_unix_ns,
        )
        if not matched:
            await _send_ws_error(
                websocket,
                code="CLOCK_SYNC_PONG_STALE",
                detail="clock sync pong tidak punya probe aktif",
            )
        return

    if payload.command == ControlCommandType.STOP_SESSION and bool(payload.ack):
        command_id = str(payload.command_id or "")
        if not command_id:
            await _send_ws_error(websocket, code="STOP_ACK_INVALID", detail="command_id wajib")
            return

        matched = await ws_runtime.register_stop_session_ack(
            session_id=resolved_session_id,
            device_id=context.device_id,
            command_id=command_id,
        )
        if not matched:
            await _send_ws_error(
                websocket,
                code="STOP_ACK_STALE",
                detail="stop session ack tidak punya command aktif",
            )
        return

    await _send_ws_error(
        websocket,
        code="UNKNOWN_BINARY_CONTROL",
        detail="binary control command tidak dikenali",
    )


async def _handle_text_message(
    websocket: WebSocket,
    context: DeviceConnectionContext,
    payload_text: str,
) -> None:
    payload = _extract_hello_payload(payload_text)
    if payload is None:
        await _send_ws_error(
            websocket,
            code="INVALID_JSON",
            detail="message text bukan JSON valid",
        )
        return

    msg_type = str(payload.get("type", ""))
    if msg_type == "HEARTBEAT":
        resolved_session_id = _resolve_session_id_for_message(context, payload.get("session_id"))
        # Always touch heartbeat — fall back to "" for session-less connections so the
        # timeout loop doesn't evict a device that is actively sending heartbeats.
        heartbeat_session_id = resolved_session_id if resolved_session_id is not None else (context.session_id or "")
        await ws_runtime.touch_heartbeat(heartbeat_session_id, context.device_id)
        await _send_json(
            websocket,
            {
                "type": "HEARTBEAT_ACK",
                "device_id": context.device_id,
                "session_id": resolved_session_id or "",
            },
        )
        return

    if msg_type == "CLOCK_SYNC_PONG":
        ping_id = str(payload.get("ping_id", ""))
        device_unix_ns_raw = payload.get("device_unix_ns")
        if not ping_id:
            await _send_ws_error(websocket, code="CLOCK_SYNC_PONG_INVALID", detail="ping_id wajib")
            return
        try:
            device_unix_ns = int(device_unix_ns_raw)
        except (TypeError, ValueError):
            await _send_ws_error(websocket, code="CLOCK_SYNC_PONG_INVALID", detail="device_unix_ns tidak valid")
            return

        resolved_session_id = _resolve_session_id_for_message(context, payload.get("session_id"))
        if resolved_session_id is None:
            await _send_ws_error(websocket, code="SESSION_REQUIRED", detail="session_id wajib untuk clock sync")
            return

        matched = await ws_runtime.register_clock_sync_pong(
            session_id=resolved_session_id,
            device_id=context.device_id,
            ping_id=ping_id,
            device_unix_ns=device_unix_ns,
        )
        if not matched:
            await _send_ws_error(
                websocket,
                code="CLOCK_SYNC_PONG_STALE",
                detail="clock sync pong tidak punya probe aktif",
            )
        return

    if msg_type == "STOP_SESSION_ACK":
        command_id = str(payload.get("command_id", ""))
        if not command_id:
            await _send_ws_error(websocket, code="STOP_ACK_INVALID", detail="command_id wajib")
            return

        resolved_session_id = _resolve_session_id_for_message(context, payload.get("session_id"))
        if resolved_session_id is None:
            await _send_ws_error(websocket, code="SESSION_REQUIRED", detail="session_id wajib untuk stop ack")
            return

        matched = await ws_runtime.register_stop_session_ack(
            session_id=resolved_session_id,
            device_id=context.device_id,
            command_id=command_id,
        )
        if not matched:
            await _send_ws_error(
                websocket,
                code="STOP_ACK_STALE",
                detail="stop session ack tidak punya command aktif",
            )
        return

    if msg_type == "SENSOR_BATCH_DEBUG":
        if not context.session_id:
            await _send_ws_error(
                websocket,
                code="SESSION_REQUIRED",
                detail="session_id wajib untuk debug batch",
            )
            return
        if context.drain_only:
            await _send_ws_error(
                websocket,
                code="SESSION_DRAIN_ONLY",
                detail="session SYNCING hanya menerima backlog ingest durable, bukan debug preview",
            )
            return
        sample_count = int(payload.get("sample_count", 0) or 0)
        start_seq = int(payload.get("start_seq", 0) or 0)
        end_seq = int(payload.get("end_seq", 0) or 0)
        preview = {
            "sample_count": sample_count,
            "debug": True,
            "payload": payload.get("preview", {}),
        }
        await _ack_batch(
            websocket,
            context,
            start_seq=start_seq,
            end_seq=end_seq,
            sample_count=sample_count,
            preview_payload=preview,
        )
        return

    await _send_ws_error(
        websocket,
        code="UNKNOWN_TEXT_MESSAGE",
        detail="type text message tidak dikenali",
    )


async def _handle_device_message(websocket: WebSocket, context: DeviceConnectionContext, message: dict[str, Any]) -> None:
    payload_bytes = message.get("bytes")
    if payload_bytes is not None:
        await _handle_binary_message(websocket, context, payload_bytes)
        return

    payload_text = message.get("text")
    if payload_text is not None:
        await _handle_text_message(websocket, context, payload_text)


@router.websocket("/ws/device/{device_id}")
async def ws_device(websocket: WebSocket, device_id: str) -> None:
    if not _match_pattern(device_id, DEVICE_ID_PATTERN):
        await websocket.close(code=1008)
        return

    await websocket.accept()
    db = SessionLocal()
    context: DeviceConnectionContext | None = None

    try:
        context = await _perform_handshake(websocket, device_id, db)
        if context is None:
            return

        await _send_hello_ack(websocket, context)

        if context.session_id:
            await ws_runtime.publish_device_event(
                context.session_id,
                {
                    "type": "DEVICE_ONLINE",
                    "device_id": context.device_id,
                    "device_role": context.role,
                    "session_id": context.session_id,
                    "backend_last_seq": context.backend_last_seq,
                },
            )

        while True:
            message = await websocket.receive()
            if message.get("type") == "websocket.disconnect":
                break
            await _handle_device_message(websocket, context, message)

    except WebSocketDisconnect:
        pass
    finally:
        await ws_runtime.unregister_device(device_id, websocket)
        with SessionLocal() as state_db:
            tracked = state_db.get(Device, device_id)
            if tracked:
                tracked.connected = False
                state_db.commit()
        db.close()


@router.websocket("/ws/dashboard/{session_id}")
async def ws_dashboard(
    websocket: WebSocket,
    session_id: str,
    operator_token: str | None = None,
    operator_id: str | None = None,
) -> None:
    if not _match_pattern(session_id, SESSION_ID_PATTERN):
        await websocket.close(code=1008)
        return

    token_candidate = (operator_token or "").strip()
    if not token_candidate:
        token_candidate = (websocket.headers.get("x-operator-token") or "").strip()
    if not token_candidate:
        auth_header = (websocket.headers.get("authorization") or "").strip()
        if auth_header.lower().startswith("bearer "):
            token_candidate = auth_header.split(" ", 1)[1].strip()
    if not verify_operator_token(token_candidate or None):
        await websocket.close(code=1008)
        return

    connection = await ws_runtime.register_dashboard(session_id=session_id, websocket=websocket)
    try:
        snapshot = await ws_runtime.snapshot_for_dashboard(session_id)
        await connection.queue.put(snapshot)
        with SessionLocal() as db:
            session = db.get(SessionModel, session_id)
            if session is not None:
                await connection.queue.put(
                    {
                        "type": "SESSION_STATE",
                        "session_id": session_id,
                        "status": session.status,
                    }
                )

            active_annotations = (
                db.query(Annotation)
                .filter(
                    Annotation.session_id == session_id,
                    Annotation.deleted.is_(False),
                    Annotation.ended_at.is_(None),
                )
                .order_by(Annotation.started_at.asc())
                .all()
            )
            await connection.queue.put(
                {
                    "type": "ANNOTATIONS_SNAPSHOT",
                    "session_id": session_id,
                    "active_annotations": [
                        {
                            "annotation_id": item.annotation_id,
                            "label": item.label,
                            "notes": item.notes,
                            "started_at": item.started_at.isoformat() if item.started_at else None,
                        }
                        for item in active_annotations
                    ],
                }
            )
        await connection.queue.put(
            {
                "type": "VIDEO_RECORDER_STATUS",
                "session_id": session_id,
                "status": "idle",
            }
        )

        while True:
            message = await websocket.receive_text()
            try:
                payload: dict[str, Any] = json.loads(message)
            except json.JSONDecodeError:
                continue

            if payload.get("type") == "PING":
                await connection.queue.put({"type": "PONG", "session_id": session_id})

    except WebSocketDisconnect:
        pass
    finally:
        await ws_runtime.unregister_dashboard(session_id, connection)
