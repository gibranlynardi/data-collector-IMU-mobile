from typing import Annotated

from fastapi import APIRouter, Body, Depends, HTTPException, Path
from sqlalchemy.orm import Session

from app.db.models import Session as SessionModel
from app.db.session import get_db
from app.services.ingest_pipeline import ingest_protobuf_batch_message
from generated.sensor_sample_pb2 import SensorBatch

router = APIRouter(prefix="/sessions", tags=["ingest"])
DBSession = Annotated[Session, Depends(get_db)]
SESSION_ID_PATTERN = r"^\d{8}_\d{6}_[A-F0-9]{8}$"
DEVICE_ID_PATTERN = r"^DEVICE-(CHEST|WAIST|THIGH|OTHER)-\d{3}$"


@router.post("/{session_id}/ingest/sensor-batch", responses={404: {"description": "Session not found"}, 409: {"description": "Session cannot ingest in current state"}})
def ingest_sensor_batch(
    session_id: Annotated[str, Path(pattern=SESSION_ID_PATTERN)],
    device_id: Annotated[str, Body(embed=True, pattern=DEVICE_ID_PATTERN)],
    device_role: Annotated[str, Body(embed=True)],
    samples: Annotated[list[dict], Body(embed=True)],
    db: DBSession,
) -> dict:
    session = db.get(SessionModel, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="session not found")
    if session.status not in {"RUNNING", "ENDING"}:
        raise HTTPException(status_code=409, detail=f"session status {session.status} tidak menerima ingest")

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
        sample.device_role = device_role.lower()
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
        device_role_override=device_role.lower(),
    )
    return {
        "session_id": session_id,
        "device_id": device_id,
        **result,
    }
