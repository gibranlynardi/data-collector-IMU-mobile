import asyncio

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.db.session as db_session
import app.main as main_app
from app.db.base import Base
from app.db.models import Session as SessionModel
from app.services.storage_monitor import storage_monitor_service


def _setup_db(tmp_path):
    db_file = tmp_path / "metadata.db"
    engine = create_engine(f"sqlite:///{db_file.as_posix()}", connect_args={"check_same_thread": False})
    testing_session_local = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    db_session.engine = engine
    db_session.SessionLocal = testing_session_local
    main_app.engine = engine

    Base.metadata.create_all(bind=engine)
    return testing_session_local


def test_storage_monitor_emits_warning_and_critical_events(tmp_path, monkeypatch) -> None:
    testing_session_local = _setup_db(tmp_path)
    monkeypatch.setattr("app.services.storage_monitor.SessionLocal", testing_session_local)
    session_id = "20260419_143022_A1B2C3D4"

    with testing_session_local() as db:
        db.add(SessionModel(session_id=session_id, status="RUNNING", preflight_passed=True))
        db.commit()

    monkeypatch.setattr(storage_monitor_service._settings, "storage_runtime_warning_free_bytes", 2000)
    monkeypatch.setattr(storage_monitor_service._settings, "storage_runtime_critical_free_bytes", 1000)

    warnings: list[str] = []
    events: list[dict] = []
    safe_stops: list[tuple[str, int]] = []

    monkeypatch.setattr(
        "app.services.storage_monitor.ws_runtime.publish_warning_sync",
        lambda sid, device_id, warning: warnings.append(warning),
    )
    monkeypatch.setattr(
        "app.services.storage_monitor.ws_runtime.publish_session_event_sync",
        lambda sid, payload: events.append(payload),
    )
    monkeypatch.setattr(
        storage_monitor_service,
        "_safe_stop_session",
        lambda *, session_id, free_bytes: asyncio.sleep(0, result=safe_stops.append((session_id, free_bytes))),
    )

    monkeypatch.setattr(storage_monitor_service, "_get_free_bytes", lambda: 1500)
    storage_monitor_service._last_level_by_session.clear()
    reports_warning = asyncio.run(storage_monitor_service.run_once())
    assert reports_warning[0].level == "warning"
    assert any(event.get("type") == "BACKEND_STORAGE_WARNING" for event in events)

    monkeypatch.setattr(storage_monitor_service, "_get_free_bytes", lambda: 900)
    reports_critical = asyncio.run(storage_monitor_service.run_once())
    assert reports_critical[0].level == "critical"
    assert any(event.get("type") == "BACKEND_STORAGE_CRITICAL" for event in events)
    assert safe_stops == [(session_id, 900)]
