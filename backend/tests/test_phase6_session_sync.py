import time

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


def test_start_session_writes_sync_report_and_exposes_endpoint(tmp_path, monkeypatch) -> None:
    data_root = tmp_path / "data"
    data_root.mkdir(parents=True, exist_ok=True)

    monkeypatch.setenv("DATA_ROOT", str(data_root))
    monkeypatch.setenv("REQUIRED_DEVICE_ROLES", "chest")
    monkeypatch.setenv("SESSION_START_LEAD_MS", "1500")
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

    session_id = "20260419_143022_A1B2C3D4"
    device_id = "DEVICE-CHEST-001"

    with testing_session_local() as db:
        db.add(Device(device_id=device_id, device_role="chest", connected=True))
        db.add(SessionModel(session_id=session_id, status="CREATED", preflight_passed=True))
        db.add(SessionDevice(session_id=session_id, device_id=device_id, required=True))
        db.commit()

    monkeypatch.setattr("app.api.routers.sessions.run_startup_checks", lambda: {"backend_healthy": True, "webcam_available": True, "storage_path_writable": True})
    monkeypatch.setattr("app.api.routers.sessions.is_preflight_passed", lambda _report: True)
    monkeypatch.setattr(
        "app.api.routers.sessions.video_recorder_service.start_session_recording",
        lambda _db, _session_id, allow_override=False: {
            "status": "recording",
            "session_id": _session_id,
            "video_id": f"VID-{_session_id}-WEBCAM-01",
        },
    )
    monkeypatch.setattr("app.api.routers.sessions.csv_writer_service.prepare_session_writers", lambda _db, _session_id: [device_id])
    async def _fake_online(_sid: str):
        return [device_id]

    monkeypatch.setattr("app.api.routers.sessions.ws_runtime.get_online_device_ids", _fake_online)

    async def _fake_sync(session_id: str, device_ids: list[str]):
        report = {
            "session_id": session_id,
            "devices": [
                {
                    "device_id": device_ids[0],
                    "sync_quality": "good",
                    "sync_quality_color": "green",
                }
            ],
            "overall_sync_quality": "good",
            "overall_sync_quality_color": "green",
        }
        clock_sync_service.write_sync_report(session_id, report)
        return report

    monkeypatch.setattr("app.api.routers.sessions.clock_sync_service.run_preflight_sync", _fake_sync)

    sent_commands: list[dict[str, object]] = []

    async def _fake_broadcast(_session_id: str, payload: dict[str, object]):
        sent_commands.append(payload)
        return [device_id]

    monkeypatch.setattr("app.api.routers.sessions.ws_runtime.broadcast_command_to_session_devices", _fake_broadcast)

    with TestClient(main_app.app) as client:
        before_start_ns = time.time_ns()
        start_resp = client.post(f"/sessions/{session_id}/start")
        assert start_resp.status_code == 200

        sync_resp = client.get(f"/sessions/{session_id}/sync-report")
        assert sync_resp.status_code == 200
        payload = sync_resp.json()
        assert payload["session_id"] == session_id
        assert payload["overall_sync_quality"] == "good"
        assert "server_start_time_unix_ns" in payload
        assert "session_start_monotonic_ms" in payload
        assert sent_commands
        start_command = sent_commands[-1]
        assert start_command.get("type") == "START_SESSION"
        assert int(start_command["start_at_unix_ns"]) == int(payload["server_start_time_unix_ns"])
        assert int(start_command["start_delay_ms"]) == 1500
        assert int(start_command["start_at_unix_ns"]) >= before_start_ns + 1_500_000_000


def test_start_session_rejects_when_session_has_no_device_assignments(tmp_path, monkeypatch) -> None:
    data_root = tmp_path / "data"
    data_root.mkdir(parents=True, exist_ok=True)

    monkeypatch.setenv("DATA_ROOT", str(data_root))
    monkeypatch.setenv("REQUIRED_DEVICE_ROLES", "chest")
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

    session_id = "20260419_143022_A1B2C3D4"
    device_id = "DEVICE-CHEST-001"

    with testing_session_local() as db:
        db.add(Device(device_id=device_id, device_role="chest", connected=True))
        db.add(SessionModel(session_id=session_id, status="CREATED", preflight_passed=True))
        db.commit()

    monkeypatch.setattr("app.api.routers.sessions.run_startup_checks", lambda: {"backend_healthy": True, "webcam_available": True, "storage_path_writable": True})
    monkeypatch.setattr("app.api.routers.sessions.is_preflight_passed", lambda _report: True)
    monkeypatch.setattr(
        "app.api.routers.sessions.video_recorder_service.start_session_recording",
        lambda _db, _session_id, allow_override=False: {
            "status": "recording",
            "session_id": _session_id,
            "video_id": f"VID-{_session_id}-WEBCAM-01",
        },
    )
    with TestClient(main_app.app) as client:
        response = client.post(f"/sessions/{session_id}/start")
        assert response.status_code == 400
        assert "belum di-assign" in response.json()["detail"]
