from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.api.routers.devices as devices_router
import app.db.session as db_session
import app.main as main_app
import app.services.storage_monitor as storage_monitor_module
from app.core.config import get_settings
from app.db.base import Base
from app.db.models import Device, Session as SessionModel, SessionDevice


def test_patch_device_emits_critical_storage_and_battery_alerts(tmp_path, monkeypatch) -> None:
    data_root = tmp_path / "data"
    data_root.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("DATA_ROOT", str(data_root))
    monkeypatch.setenv("DEVICE_STORAGE_CRITICAL_MB", "700")
    monkeypatch.setenv("BATTERY_CRITICAL_PERCENT", "15")
    get_settings.cache_clear()

    db_file = tmp_path / "metadata.db"
    engine = create_engine(f"sqlite:///{db_file.as_posix()}", connect_args={"check_same_thread": False})
    testing_session_local = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    db_session.engine = engine
    db_session.SessionLocal = testing_session_local
    main_app.engine = engine
    storage_monitor_module.SessionLocal = testing_session_local
    Base.metadata.create_all(bind=engine)

    session_id = "20260419_143022_A1B2C3D4"
    device_id = "DEVICE-CHEST-001"

    with testing_session_local() as db:
        db.add(Device(device_id=device_id, device_role="chest", connected=True))
        db.add(SessionModel(session_id=session_id, status="RUNNING", preflight_passed=True))
        db.add(SessionDevice(session_id=session_id, device_id=device_id, required=True))
        db.commit()

    warnings: list[tuple[str, str, str]] = []
    events: list[tuple[str, dict]] = []

    monkeypatch.setattr(
        devices_router.ws_runtime,
        "publish_warning_sync",
        lambda sid, device_id, warning: warnings.append((sid, device_id, warning)),
    )
    monkeypatch.setattr(
        devices_router.ws_runtime,
        "publish_device_event_sync",
        lambda sid, payload: events.append((sid, payload)),
    )

    with TestClient(main_app.app) as client:
        response = client.patch(
            f"/devices/{device_id}",
            json={
                "storage_free_mb": 600,
                "battery_percent": 10,
            },
        )

    assert response.status_code == 200
    assert any("storage kritis" in message for _, _, message in warnings)
    assert any("battery kritis" in message for _, _, message in warnings)
    assert any(payload.get("type") == "DEVICE_STORAGE_CRITICAL" for _, payload in events)
    assert any(payload.get("type") == "DEVICE_LOST" for _, payload in events)
