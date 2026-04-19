import asyncio

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.db.session as db_session
import app.main as main_app
from app.core.config import get_settings
from app.db.base import Base
from app.db.models import Device, Session as SessionModel, SessionDevice
from app.services.clock_sync import clock_sync_service
from app.services.csv_writer import csv_writer_service
from app.services.video_recorder import video_recorder_service


def _setup_db(tmp_path, monkeypatch):
    data_root = tmp_path / "data"
    data_root.mkdir(parents=True, exist_ok=True)

    monkeypatch.setenv("DATA_ROOT", str(data_root))
    monkeypatch.setenv("REQUIRED_DEVICE_ROLES", "chest,waist,thigh")
    get_settings.cache_clear()
    csv_writer_service._settings = get_settings()
    video_recorder_service._settings = get_settings()
    clock_sync_service._settings = get_settings()

    db_file = tmp_path / "metadata.db"
    engine = create_engine(f"sqlite:///{db_file.as_posix()}", connect_args={"check_same_thread": False})
    testing_session_local = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    db_session.engine = engine
    db_session.SessionLocal = testing_session_local
    main_app.engine = engine

    Base.metadata.create_all(bind=engine)
    return testing_session_local


def test_assign_session_devices_endpoint_and_list(tmp_path, monkeypatch) -> None:
    testing_session_local = _setup_db(tmp_path, monkeypatch)

    session_id = "20260419_143022_A1B2C3D4"
    with testing_session_local() as db:
        db.add(Device(device_id="DEVICE-CHEST-001", device_role="chest", connected=True))
        db.add(Device(device_id="DEVICE-WAIST-001", device_role="waist", connected=False))
        db.add(Device(device_id="DEVICE-THIGH-001", device_role="thigh", connected=False))
        db.add(SessionModel(session_id=session_id, status="CREATED", preflight_passed=True))
        db.commit()

    payload = {
        "replace": True,
        "assignments": [
            {"device_id": "DEVICE-CHEST-001", "required": True},
            {"device_id": "DEVICE-WAIST-001", "required": True},
            {"device_id": "DEVICE-THIGH-001", "required": True},
        ],
    }

    with TestClient(main_app.app) as client:
        put_resp = client.put(f"/sessions/{session_id}/devices", json=payload)
        assert put_resp.status_code == 200
        body = put_resp.json()
        assert body["session_id"] == session_id
        assert len(body["bindings"]) == 3

        get_resp = client.get(f"/sessions/{session_id}/devices")
        assert get_resp.status_code == 200
        listed = get_resp.json()
        assert len(listed["bindings"]) == 3


def test_start_session_blocks_when_required_roles_not_online(tmp_path, monkeypatch) -> None:
    testing_session_local = _setup_db(tmp_path, monkeypatch)

    session_id = "20260419_143022_A1B2C3D4"
    with testing_session_local() as db:
        db.add(Device(device_id="DEVICE-CHEST-001", device_role="chest", connected=True))
        db.add(Device(device_id="DEVICE-WAIST-001", device_role="waist", connected=False))
        db.add(Device(device_id="DEVICE-THIGH-001", device_role="thigh", connected=False))
        db.add(SessionModel(session_id=session_id, status="CREATED", preflight_passed=True))
        db.add(SessionDevice(session_id=session_id, device_id="DEVICE-CHEST-001", required=True))
        db.add(SessionDevice(session_id=session_id, device_id="DEVICE-WAIST-001", required=True))
        db.add(SessionDevice(session_id=session_id, device_id="DEVICE-THIGH-001", required=True))
        db.commit()

    monkeypatch.setattr("app.api.routers.sessions.run_startup_checks", lambda: {"backend_healthy": True, "webcam_available": True, "storage_path_writable": True})
    monkeypatch.setattr("app.api.routers.sessions.is_preflight_passed", lambda _report: True)

    async def _fake_online(_sid: str):
        await asyncio.sleep(0)
        return ["DEVICE-CHEST-001"]

    monkeypatch.setattr("app.api.routers.sessions.ws_runtime.get_online_device_ids", _fake_online)

    with TestClient(main_app.app) as client:
        response = client.post(f"/sessions/{session_id}/start")
        assert response.status_code == 400
        assert "belum online" in response.json()["detail"]
