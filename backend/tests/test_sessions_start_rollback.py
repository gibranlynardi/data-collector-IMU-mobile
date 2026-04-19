from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.api.routers.sessions as sessions_router
import app.db.session as db_session
import app.main as main_app
from app.core.config import get_settings
from app.db.base import Base
from app.db.models import Device, Session as SessionModel, SessionDevice


def test_start_session_rolls_back_when_prepare_writers_fails(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("REQUIRED_DEVICE_ROLES", "chest")
    get_settings.cache_clear()

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

    monkeypatch.setattr(sessions_router, "run_startup_checks", lambda: {"backend_healthy": True})
    monkeypatch.setattr(sessions_router, "is_preflight_passed", lambda _report: True)

    calls: dict[str, int] = {"stop": 0, "close": 0}

    monkeypatch.setattr(
        sessions_router.video_recorder_service,
        "start_session_recording",
        lambda _db, _session_id, allow_override=False: {"status": "recording"},
    )

    def _stop_recorder(_db, _session_id, suppress_errors=False):
        calls["stop"] += 1
        return {"status": "completed"}

    monkeypatch.setattr(sessions_router.video_recorder_service, "stop_session_recording", _stop_recorder)

    def _close_session(_session_id):
        calls["close"] += 1

    def _prepare_fail(_db, _session_id):
        raise RuntimeError("prepare failed")

    monkeypatch.setattr(sessions_router.csv_writer_service, "close_session", _close_session)
    monkeypatch.setattr(sessions_router.csv_writer_service, "prepare_session_writers", _prepare_fail)

    async def _fake_online(_sid: str):
        return [device_id]

    async def _fake_sync(*, session_id: str, device_ids: list[str]):
        return {
            "session_id": session_id,
            "devices": [{"device_id": device_ids[0], "sync_quality": "good", "sync_quality_color": "green"}],
            "overall_sync_quality": "good",
            "overall_sync_quality_color": "green",
        }

    monkeypatch.setattr(sessions_router.ws_runtime, "get_online_device_ids", _fake_online)
    monkeypatch.setattr(sessions_router.clock_sync_service, "run_preflight_sync", _fake_sync)

    with TestClient(main_app.app) as client:
        response = client.post(f"/sessions/{session_id}/start")

    assert response.status_code == 400
    assert "prepare failed" in response.json()["detail"]
    assert calls["stop"] == 1
    assert calls["close"] == 1

    with testing_session_local() as db:
        session = db.get(SessionModel, session_id)
        assert session is not None
        assert session.status == "CREATED"
        assert session.started_at is None
