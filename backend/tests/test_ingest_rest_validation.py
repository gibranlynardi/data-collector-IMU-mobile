from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.db.session as db_session
import app.main as main_app
from app.core.config import get_settings
from app.db.base import Base
from app.db.models import Device, Session as SessionModel, SessionDevice
from app.services.csv_writer import csv_writer_service


def _sample(seq: int) -> dict:
    return {
        "seq": seq,
        "timestamp_device_unix_ns": 1_700_000_000_000_000_000 + seq,
        "elapsed_ms": seq * 10,
        "acc_x_g": 0.1,
        "acc_y_g": 0.2,
        "acc_z_g": 0.3,
        "gyro_x_deg": 1.0,
        "gyro_y_deg": 2.0,
        "gyro_z_deg": 3.0,
    }


def _payload(device_id: str, device_role: str, samples: list[dict]) -> dict:
    return {
        "device_id": device_id,
        "device_role": device_role,
        "samples": samples,
    }


def test_ingest_rejects_unregistered_device(tmp_path, monkeypatch) -> None:
    csv_writer_service.close_all()
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
    with testing_session_local() as db:
        db.add(SessionModel(session_id=session_id, status="RUNNING", preflight_passed=True))
        db.commit()

    with TestClient(main_app.app) as client:
        response = client.post(
            f"/sessions/{session_id}/ingest/sensor-batch",
            json=_payload("DEVICE-CHEST-001", "chest", [_sample(1)]),
        )
        assert response.status_code == 404
        assert "device not registered" in response.json()["detail"]


def test_ingest_rejects_device_not_in_session(tmp_path, monkeypatch) -> None:
    csv_writer_service.close_all()
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

    with TestClient(main_app.app) as client:
        response = client.post(
            f"/sessions/{session_id}/ingest/sensor-batch",
            json=_payload(device_id, "chest", [_sample(1)]),
        )
        assert response.status_code == 409
        assert "tidak tergabung" in response.json()["detail"]


def test_ingest_rejects_role_mismatch(tmp_path, monkeypatch) -> None:
    csv_writer_service.close_all()
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
        db.add(SessionDevice(session_id=session_id, device_id=device_id, required=True))
        db.commit()

    with TestClient(main_app.app) as client:
        response = client.post(
            f"/sessions/{session_id}/ingest/sensor-batch",
            json=_payload(device_id, "waist", [_sample(1)]),
        )
        assert response.status_code == 409
        assert "device_role mismatch" in response.json()["detail"]


def test_ingest_rejects_empty_and_non_monotonic_samples(tmp_path, monkeypatch) -> None:
    csv_writer_service.close_all()
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
        db.add(SessionDevice(session_id=session_id, device_id=device_id, required=True))
        db.commit()

    with TestClient(main_app.app) as client:
        empty_resp = client.post(
            f"/sessions/{session_id}/ingest/sensor-batch",
            json=_payload(device_id, "chest", []),
        )
        assert empty_resp.status_code == 400

        non_mono_resp = client.post(
            f"/sessions/{session_id}/ingest/sensor-batch",
            json=_payload(device_id, "chest", [_sample(2), _sample(1)]),
        )
        assert non_mono_resp.status_code == 400
        assert "seq sample" in non_mono_resp.json()["detail"]


def test_ingest_rejects_batch_over_limit_and_accepts_valid(tmp_path, monkeypatch) -> None:
    csv_writer_service.close_all()
    data_root = tmp_path / "data"
    data_root.mkdir(parents=True, exist_ok=True)

    monkeypatch.setenv("DATA_ROOT", str(data_root))
    monkeypatch.setenv("WS_MAX_BATCH_SAMPLES", "3")
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
        db.add(SessionDevice(session_id=session_id, device_id=device_id, required=True))
        db.commit()

    with TestClient(main_app.app) as client:
        over_resp = client.post(
            f"/sessions/{session_id}/ingest/sensor-batch",
            json=_payload(device_id, "chest", [_sample(1), _sample(2), _sample(3), _sample(4)]),
        )
        assert over_resp.status_code == 400
        assert "melebihi limit" in over_resp.json()["detail"]

        ok_resp = client.post(
            f"/sessions/{session_id}/ingest/sensor-batch",
            json=_payload(device_id, "chest", [_sample(1), _sample(2), _sample(3)]),
        )
        assert ok_resp.status_code == 200
        body = ok_resp.json()
        assert body["written"] == 3
        assert body["device_id"] == device_id

    csv_writer_service.close_all()


def test_ingest_rejects_ending_session_and_does_not_reopen_writer(tmp_path, monkeypatch) -> None:
    csv_writer_service.close_all()
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
        db.add(SessionModel(session_id=session_id, status="ENDING", preflight_passed=True))
        db.add(SessionDevice(session_id=session_id, device_id=device_id, required=True))
        db.commit()

    with TestClient(main_app.app) as client:
        response = client.post(
            f"/sessions/{session_id}/ingest/sensor-batch",
            json=_payload(device_id, "chest", [_sample(1)]),
        )
        assert response.status_code == 409
        assert "RUNNING/SYNCING" in response.json()["detail"]

    sensor_dir = data_root / "sessions" / session_id / "sensor"
    assert not sensor_dir.exists()

    csv_writer_service.close_all()
