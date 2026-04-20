import json
from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.db.session as db_session
import app.main as main_app
import app.services.storage_monitor as storage_monitor_module
from app.core.config import get_settings
from app.db.base import Base
from app.db.models import Device, PreflightCheck, Session as SessionModel, SessionDevice
from app.services.clock_sync import clock_sync_service
from app.services.csv_writer import csv_writer_service
from app.services.video_recorder import video_recorder_service


def _setup_db(tmp_path, monkeypatch):
    data_root = tmp_path / "data"
    data_root.mkdir(parents=True, exist_ok=True)

    monkeypatch.setenv("DATA_ROOT", str(data_root))
    monkeypatch.setenv("REQUIRED_DEVICE_ROLES", "chest")
    monkeypatch.setenv("PREFLIGHT_REPORT_TTL_SECONDS", "180")
    get_settings.cache_clear()
    csv_writer_service._settings = get_settings()
    video_recorder_service._settings = get_settings()
    clock_sync_service._settings = get_settings()

    db_file = tmp_path / "metadata.db"
    engine = create_engine(f"sqlite:///{db_file.as_posix()}", connect_args={"check_same_thread": False})
    testing_session_local = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    db_session.engine = engine
    db_session.SessionLocal = testing_session_local
    storage_monitor_module.SessionLocal = testing_session_local
    main_app.engine = engine

    Base.metadata.create_all(bind=engine)
    return testing_session_local


def test_run_session_preflight_persists_db_and_json_report(tmp_path, monkeypatch) -> None:
    testing_session_local = _setup_db(tmp_path, monkeypatch)

    session_id = "20260419_143022_A1B2C3D4"
    device_id = "DEVICE-CHEST-001"

    with testing_session_local() as db:
        db.add(
            Device(
                device_id=device_id,
                device_role="chest",
                connected=True,
                battery_percent=88.0,
                storage_free_mb=2048,
                effective_hz=99.5,
            )
        )
        db.add(SessionModel(session_id=session_id, status="CREATED", preflight_passed=False))
        db.add(SessionDevice(session_id=session_id, device_id=device_id, required=True))
        db.commit()

    monkeypatch.setattr(
        "app.api.routers.sessions.run_startup_checks",
        lambda: {
            "backend_healthy": True,
            "storage_path_writable": True,
            "storage_free_bytes": 10_000_000_000,
            "webcam_connected": True,
            "webcam_preview_ok": True,
            "webcam_fps": 30.0,
            "webcam_fps_ok": True,
            "webcam_storage_ok": True,
            "webcam_available": True,
            "webcam_detail": "ok",
        },
    )

    async def _fake_sync(session_id: str, device_ids: list[str]):
        return {
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

    monkeypatch.setattr("app.api.routers.sessions.clock_sync_service.run_preflight_sync", _fake_sync)

    with TestClient(main_app.app) as client:
        response = client.post(f"/sessions/{session_id}/preflight/run")
        assert response.status_code == 200
        payload = response.json()
        assert payload["overall_passed"] is True
        assert payload["session_id"] == session_id
        assert payload["check_items"]

    with testing_session_local() as db:
        overall = (
            db.query(PreflightCheck)
            .filter(PreflightCheck.session_id == session_id, PreflightCheck.check_name == "preflight_overall")
            .order_by(PreflightCheck.measured_at.desc(), PreflightCheck.id.desc())
            .first()
        )
        assert overall is not None
        assert overall.passed is True

    report_path = get_settings().data_root / "sessions" / session_id / "preflight_report.json"
    assert report_path.exists()
    report_payload = json.loads(report_path.read_text(encoding="utf-8"))
    assert report_payload["session_id"] == session_id
    assert report_payload["latest_report"]["overall_passed"] is True


def test_start_requires_fresh_preflight_report(tmp_path, monkeypatch) -> None:
    testing_session_local = _setup_db(tmp_path, monkeypatch)

    session_id = "20260419_143022_A1B2C3D4"
    device_id = "DEVICE-CHEST-001"

    with testing_session_local() as db:
        db.add(
            Device(
                device_id=device_id,
                device_role="chest",
                connected=True,
                battery_percent=88.0,
                storage_free_mb=2048,
                effective_hz=100.0,
            )
        )
        db.add(SessionModel(session_id=session_id, status="CREATED", preflight_passed=False))
        db.add(SessionDevice(session_id=session_id, device_id=device_id, required=True))
        db.add(
            PreflightCheck(
                session_id=session_id,
                check_name="preflight_overall",
                passed=True,
                details=json.dumps({"overall_passed": True}, ensure_ascii=True),
                measured_at=(datetime.now(UTC) - timedelta(seconds=400)).replace(tzinfo=None),
            )
        )
        db.commit()

    with TestClient(main_app.app) as client:
        response = client.post(f"/sessions/{session_id}/start")

    assert response.status_code == 400
    assert "preflight report expired" in str(response.json()["detail"])
