from typing import Annotated

from fastapi import APIRouter, Body, Depends, HTTPException, Path
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.models import Device, Session as SessionModel, SessionDevice
from app.db.session import get_db
from app.services.ingest_pipeline import ingest_protobuf_batch_message
from generated.sensor_sample_pb2 import SensorBatch

router = APIRouter(prefix="/sessions", tags=["ingest"])
DBSession = Annotated[Session, Depends(get_db)]
SESSION_ID_PATTERN = r"^\d{8}_\d{6}_[A-F0-9]{8}$"
DEVICE_ID_PATTERN = r"^DEVICE-(CHEST|WAIST|THIGH|OTHER)-\d{3}$"
VALID_ROLES = {"chest", "waist", "thigh", "other"}


def _validate_ingest_context(db: Session, session_id: str, device_id: str, device_role: str) -> tuple[SessionModel, Device]:
    ingest_allowed_states = {"RUNNING", "SYNCING"}
    session = db.get(SessionModel, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="session not found")
    if session.status not in ingest_allowed_states:
        raise HTTPException(
            status_code=409,
            detail=f"session status {session.status} tidak menerima ingest (hanya RUNNING/SYNCING)",
        )

    device = db.get(Device, device_id)
    if not device:
        raise HTTPException(status_code=404, detail="device not registered")

    mapped = (
        db.query(SessionDevice)
        .filter(SessionDevice.session_id == session_id, SessionDevice.device_id == device_id)
        .first()
    )
    if not mapped:
        raise HTTPException(status_code=409, detail="device tidak tergabung pada session ini")

    requested_role = device_role.lower()
    if requested_role not in VALID_ROLES:
        raise HTTPException(status_code=400, detail="device_role tidak valid")

    registered_role = (device.device_role or "other").lower()
    if requested_role != registered_role:
        raise HTTPException(
            status_code=409,
            detail=f"device_role mismatch: request={requested_role} registered={registered_role}",
        )

    return session, device


def _validate_samples(samples: list[dict], max_batch_samples: int) -> None:
    if not samples:
        raise HTTPException(status_code=400, detail="samples tidak boleh kosong")

    if len(samples) > max_batch_samples:
        raise HTTPException(
            status_code=400,
            detail=f"sample_count={len(samples)} melebihi limit {max_batch_samples}",
        )

    required_keys = {
        "seq",
        "timestamp_device_unix_ns",
        "elapsed_ms",
        "acc_x_g",
        "acc_y_g",
        "acc_z_g",
        "gyro_x_deg",
        "gyro_y_deg",
        "gyro_z_deg",
    }

    prev_seq: int | None = None
    for index, item in enumerate(samples):
        missing = [key for key in required_keys if key not in item]
        if missing:
            raise HTTPException(status_code=400, detail=f"sample[{index}] missing fields: {', '.join(sorted(missing))}")

        try:
            seq = int(item["seq"])
            int(item["timestamp_device_unix_ns"])
            int(item["elapsed_ms"])
            float(item["acc_x_g"])
            float(item["acc_y_g"])
            float(item["acc_z_g"])
            float(item["gyro_x_deg"])
            float(item["gyro_y_deg"])
            float(item["gyro_z_deg"])
        except (TypeError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=f"sample[{index}] memiliki tipe nilai tidak valid") from exc

        if prev_seq is not None and seq <= prev_seq:
            raise HTTPException(status_code=400, detail="seq sample harus berurutan naik (strictly increasing)")
        prev_seq = seq


@router.post(
    "/{session_id}/ingest/sensor-batch",
    responses={
        400: {"description": "Invalid ingest payload"},
        404: {"description": "Session or device not found"},
        409: {"description": "Session cannot ingest in current state or device mapping conflict"},
    },
)
def ingest_sensor_batch(
    session_id: Annotated[str, Path(pattern=SESSION_ID_PATTERN)],
    device_id: Annotated[str, Body(embed=True, pattern=DEVICE_ID_PATTERN)],
    device_role: Annotated[str, Body(embed=True)],
    samples: Annotated[list[dict], Body(embed=True)],
    db: DBSession,
) -> dict:
    settings = get_settings()
    normalized_role = device_role.lower()

    _validate_ingest_context(db, session_id, device_id, normalized_role)
    _validate_samples(samples, max_batch_samples=settings.ws_max_batch_samples)

    batch = SensorBatch(
        session_id=session_id,
        device_id=device_id,
    )

    batch.start_seq = int(samples[0]["seq"]) if samples else 0
    batch.end_seq = int(samples[-1]["seq"]) if samples else 0

    for item in samples:
        sample = batch.samples.add()
        sample.session_id = session_id
        sample.device_id = device_id
        sample.device_role = normalized_role
        sample.seq = int(item["seq"])
        sample.timestamp_device_unix_ns = int(item["timestamp_device_unix_ns"])
        sample.elapsed_ms = int(item["elapsed_ms"])
        sample.acc_x_g = float(item["acc_x_g"])
        sample.acc_y_g = float(item["acc_y_g"])
        sample.acc_z_g = float(item["acc_z_g"])
        sample.gyro_x_deg = float(item["gyro_x_deg"])
        sample.gyro_y_deg = float(item["gyro_y_deg"])
        sample.gyro_z_deg = float(item["gyro_z_deg"])

    raw_payload = batch.SerializeToString()
    result = ingest_protobuf_batch_message(
        batch=batch,
        raw_payload=raw_payload,
        device_role_override=normalized_role,
    )
    return {
        "session_id": session_id,
        "device_id": device_id,
        **result,
    }
