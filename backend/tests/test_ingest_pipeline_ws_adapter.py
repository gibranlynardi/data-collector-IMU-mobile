from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.db.session as db_session
import app.main as main_app
from app.core.config import get_settings
from app.db.base import Base
from app.db.models import Device, Session as SessionModel
from app.services.csv_writer import csv_writer_service
from app.services.ingest_pipeline import IngestProtocolError, ingest_ws_binary_batch
from generated.sensor_sample_pb2 import SensorBatch


def _make_batch(session_id: str, device_id: str, role: str, pairs: list[tuple[int, int]]) -> SensorBatch:
    batch = SensorBatch(session_id=session_id, device_id=device_id)
    if pairs:
        batch.start_seq = pairs[0][0]
        batch.end_seq = pairs[-1][0]

    for seq, elapsed_ms in pairs:
        sample = batch.samples.add()
        sample.session_id = session_id
        sample.device_id = device_id
        sample.device_role = role
        sample.seq = seq
        sample.timestamp_device_unix_ns = 1_700_000_000_000_000_000 + seq
        sample.elapsed_ms = elapsed_ms
        sample.acc_x_g = 0.1
        sample.acc_y_g = 0.2
        sample.acc_z_g = 0.3
        sample.gyro_x_deg = 1.0
        sample.gyro_y_deg = 2.0
        sample.gyro_z_deg = 3.0
    return batch


def test_ingest_ws_binary_batch_ack_contract_and_duplicate(tmp_path: Path, monkeypatch) -> None:
    data_root = tmp_path / "data"
    data_root.mkdir(parents=True, exist_ok=True)

    monkeypatch.setenv("DATA_ROOT", str(data_root))
    get_settings.cache_clear()
    csv_writer_service._settings = get_settings()

    db_file = tmp_path / "metadata.db"
    engine = create_engine(f"sqlite:///{db_file.as_posix()}", connect_args={"check_same_thread": False})
    testing_session_local = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    db_session.engine = engine
    db_session.SessionLocal = testing_session_local
    main_app.engine = engine

    Base.metadata.create_all(bind=engine)

    session_id = "20260419_143022_A1B2C3D4"
    device_id = "DEVICE-CHEST-001"

    with testing_session_local() as db:
        db.add(Device(device_id=device_id, device_role="chest", connected=True))
        db.add(SessionModel(session_id=session_id, status="RUNNING", preflight_passed=True))
        db.commit()

    batch = _make_batch(session_id, device_id, "chest", pairs=[(1, 0), (2, 10)])
    payload = batch.SerializeToString()

    ack_1 = ingest_ws_binary_batch(
        payload,
        connection_session_id=session_id,
        connection_device_id=device_id,
    )
    assert ack_1["type"] == "ACK"
    assert ack_1["session_id"] == session_id
    assert ack_1["device_id"] == device_id
    assert ack_1["batch_start_seq"] == 1
    assert ack_1["batch_end_seq"] == 2
    assert ack_1["last_received_seq"] == 2
    assert ack_1["duplicate"] is False
    assert ack_1["duplicate_batches"] == 0

    ack_2 = ingest_ws_binary_batch(
        payload,
        connection_session_id=session_id,
        connection_device_id=device_id,
    )
    assert ack_2["duplicate"] is True
    assert ack_2["duplicate_batches"] == 1


def test_ingest_ws_binary_batch_mismatch_error(tmp_path: Path, monkeypatch) -> None:
    data_root = tmp_path / "data"
    data_root.mkdir(parents=True, exist_ok=True)

    monkeypatch.setenv("DATA_ROOT", str(data_root))
    get_settings.cache_clear()
    csv_writer_service._settings = get_settings()

    batch = _make_batch("20260419_143022_A1B2C3D4", "DEVICE-CHEST-001", "chest", pairs=[(1, 0)])
    payload = batch.SerializeToString()

    with pytest.raises(IngestProtocolError) as exc:
        ingest_ws_binary_batch(
            payload,
            connection_session_id="20260419_143022_FFFFFFFF",
            connection_device_id="DEVICE-CHEST-001",
        )
    assert exc.value.code == "SESSION_OR_DEVICE_MISMATCH"
