import csv
import json
import os
import struct
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

import app.db.session as db_session
import app.main as main_app
from app.core.config import get_settings
from app.db.base import Base
from app.db.models import Device, Session as SessionModel, SessionDevice
from app.services.csv_writer import CsvWriterService, SensorSampleRow, csv_writer_service
from generated.sensor_sample_pb2 import SensorBatch


def _make_sample(session_id: str, device_id: str, role: str, seq: int, elapsed_ms: int) -> SensorSampleRow:
    return SensorSampleRow(
        session_id=session_id,
        device_id=device_id,
        device_role=role,
        seq=seq,
        timestamp_device_unix_ns=1_700_000_000_000_000_000 + seq,
        elapsed_ms=elapsed_ms,
        acc_x_g=0.1,
        acc_y_g=0.2,
        acc_z_g=0.3,
        gyro_x_deg=1.0,
        gyro_y_deg=2.0,
        gyro_z_deg=3.0,
    )


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


def test_csv_writer_dedup_gap_state_summary(tmp_path: Path, monkeypatch) -> None:
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
    role = "chest"

    with testing_session_local() as db:
        db.add(Device(device_id=device_id, device_role=role, connected=True))
        db.add(SessionModel(session_id=session_id, status="RUNNING", preflight_passed=True))
        db.commit()

        prepared = csv_writer_service.prepare_session_writers(db, session_id)
        assert device_id in prepared

    batch_1 = _make_batch(session_id, device_id, role, pairs=[(1, 0), (2, 10), (4, 30)])
    result_1 = csv_writer_service.ingest_sensor_batch_proto(batch_1)
    assert result_1["written"] == 3
    assert result_1["duplicates"] == 0
    assert result_1["missing_ranges_added"] == 1
    assert result_1["raw_archived"] is True

    batch_2 = _make_batch(session_id, device_id, role, pairs=[(4, 30), (5, 40)])
    result_2 = csv_writer_service.ingest_sensor_batch_proto(batch_2)
    assert result_2["written"] == 1
    assert result_2["duplicates"] == 1
    assert result_2["last_seq"] == 5

    csv_writer_service.close_session(session_id)

    csv_path = data_root / "sessions" / session_id / "sensor" / f"{role}_{device_id}.csv"
    state_path = data_root / "sessions" / session_id / "sensor" / f"{role}_{device_id}.state.json"
    summary_path = data_root / "sessions" / session_id / "sensor" / f"{role}_{device_id}.summary.json"
    lock_path = data_root / "sessions" / session_id / "sensor" / f"{role}_{device_id}.lock"
    binlog_path = data_root / "sessions" / session_id / "sensor" / f"{role}_{device_id}.binlog"
    binlog_index_path = data_root / "sessions" / session_id / "sensor" / f"{role}_{device_id}.binlog.index.jsonl"

    assert csv_path.exists()
    assert state_path.exists()
    assert summary_path.exists()
    assert not lock_path.exists()
    assert binlog_path.exists()
    assert binlog_index_path.exists()

    with csv_path.open("r", newline="", encoding="utf-8") as file_obj:
        rows = list(csv.reader(file_obj))
    assert rows[0][0] == "session_id"
    assert len(rows) == 5

    state = json.loads(state_path.read_text(encoding="utf-8"))
    assert state["first_seq"] == 1
    assert state["last_seq"] == 5
    assert state["sample_count"] == 4
    assert state["duplicate_count"] == 1
    assert state["missing_ranges"] == [[3, 3]]

    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    assert summary["first_seq"] == 1
    assert summary["last_seq"] == 5
    assert summary["sample_count"] == 4
    assert summary["missing_seq_ranges"] == [[3, 3]]

    index_lines = [line for line in binlog_index_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert len(index_lines) == 2

    with binlog_path.open("rb") as file_obj:
        first_len = struct.unpack("<I", file_obj.read(4))[0]
        first_payload = file_obj.read(first_len)
        second_len = struct.unpack("<I", file_obj.read(4))[0]
        second_payload = file_obj.read(second_len)

    first_batch = SensorBatch()
    first_batch.ParseFromString(first_payload)
    second_batch = SensorBatch()
    second_batch.ParseFromString(second_payload)
    assert first_batch.start_seq == 1
    assert first_batch.end_seq == 4
    assert second_batch.start_seq == 4
    assert second_batch.end_seq == 5


def test_ingest_endpoint_writes_csv(tmp_path: Path, monkeypatch) -> None:
    from fastapi.testclient import TestClient

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
    device_id = "DEVICE-WAIST-002"

    with testing_session_local() as db:
        db.add(Device(device_id=device_id, device_role="waist", connected=True))
        db.add(SessionModel(session_id=session_id, status="RUNNING", preflight_passed=True))
        db.add(SessionDevice(session_id=session_id, device_id=device_id, required=True))
        db.commit()

    with TestClient(main_app.app) as client:
        payload = {
            "device_id": device_id,
            "device_role": "waist",
            "samples": [
                {
                    "seq": 1,
                    "timestamp_device_unix_ns": 1700000000000000001,
                    "elapsed_ms": 0,
                    "acc_x_g": 0.1,
                    "acc_y_g": 0.2,
                    "acc_z_g": 0.3,
                    "gyro_x_deg": 1.0,
                    "gyro_y_deg": 2.0,
                    "gyro_z_deg": 3.0,
                },
                {
                    "seq": 2,
                    "timestamp_device_unix_ns": 1700000000000000002,
                    "elapsed_ms": 10,
                    "acc_x_g": 0.1,
                    "acc_y_g": 0.2,
                    "acc_z_g": 0.3,
                    "gyro_x_deg": 1.0,
                    "gyro_y_deg": 2.0,
                    "gyro_z_deg": 3.0,
                },
            ],
        }
        response = client.post(f"/sessions/{session_id}/ingest/sensor-batch", json=payload)
        assert response.status_code == 200
        body = response.json()
        assert body["written"] == 2
        assert body["duplicates"] == 0
        assert body["raw_archived"] is True
        assert body["raw_batch_count"] == 1
        assert body["raw_payload_size"] > 0

    csv_path = data_root / "sessions" / session_id / "sensor" / f"waist_{device_id}.csv"
    binlog_path = data_root / "sessions" / session_id / "sensor" / f"waist_{device_id}.binlog"
    assert csv_path.exists()
    assert binlog_path.exists()


def test_csv_lock_rejects_active_owner(tmp_path: Path, monkeypatch) -> None:
    data_root = tmp_path / "data"
    sensor_dir = data_root / "sessions" / "20260419_143022_A1B2C3D4" / "sensor"
    sensor_dir.mkdir(parents=True, exist_ok=True)

    monkeypatch.setenv("DATA_ROOT", str(data_root))
    get_settings.cache_clear()

    first = CsvWriterService()
    first._settings = get_settings()
    second = CsvWriterService()
    second._settings = get_settings()

    lock_path = sensor_dir / "chest_DEVICE-CHEST-001.lock"
    first._acquire_lock(lock_path)

    with pytest.raises(RuntimeError):
        second._acquire_lock(lock_path)


def test_csv_lock_recovers_stale_owner(tmp_path: Path, monkeypatch) -> None:
    data_root = tmp_path / "data"
    sensor_dir = data_root / "sessions" / "20260419_143022_A1B2C3D4" / "sensor"
    sensor_dir.mkdir(parents=True, exist_ok=True)

    monkeypatch.setenv("DATA_ROOT", str(data_root))
    get_settings.cache_clear()

    lock_path = sensor_dir / "chest_DEVICE-CHEST-001.lock"
    lock_path.write_text(json.dumps({"pid": 42424242, "acquired_at": "2026-04-19T00:00:00"}, ensure_ascii=True), encoding="utf-8")

    service = CsvWriterService()
    service._settings = get_settings()
    monkeypatch.setattr(service, "_is_pid_alive", lambda _pid: False)

    service._acquire_lock(lock_path)
    assert lock_path.exists()
    payload = json.loads(lock_path.read_text(encoding="utf-8"))
    assert int(payload.get("pid", 0) or 0) == os.getpid()


def test_csv_lock_does_not_recover_live_owner(tmp_path: Path, monkeypatch) -> None:
    data_root = tmp_path / "data"
    sensor_dir = data_root / "sessions" / "20260419_143022_A1B2C3D4" / "sensor"
    sensor_dir.mkdir(parents=True, exist_ok=True)

    monkeypatch.setenv("DATA_ROOT", str(data_root))
    get_settings.cache_clear()

    lock_path = sensor_dir / "chest_DEVICE-CHEST-001.lock"
    lock_path.write_text(json.dumps({"pid": 12345, "acquired_at": "2026-04-19T00:00:00"}, ensure_ascii=True), encoding="utf-8")

    service = CsvWriterService()
    service._settings = get_settings()
    monkeypatch.setattr(service, "_is_pid_alive", lambda _pid: True)

    with pytest.raises(RuntimeError):
        service._acquire_lock(lock_path)
