from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.api.routers.devices as devices_router
import app.db.session as db_session
import app.main as main_app
import app.services.storage_monitor as storage_monitor_module
from app.core.config import get_settings
from app.db.base import Base
from app.db.models import Device, DeviceSamplingTelemetry, Session as SessionModel, SessionDevice


def _setup_db(tmp_path, monkeypatch):
    data_root = tmp_path / "data"
    data_root.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("DATA_ROOT", str(data_root))
    get_settings.cache_clear()

    db_file = tmp_path / "metadata.db"
    engine = create_engine(f"sqlite:///{db_file.as_posix()}", connect_args={"check_same_thread": False})
    testing_session_local = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    db_session.engine = engine
    db_session.SessionLocal = testing_session_local
    main_app.engine = engine
    storage_monitor_module.SessionLocal = testing_session_local
    Base.metadata.create_all(bind=engine)
    return testing_session_local


def test_sampling_quality_telemetry_is_stored_and_queryable(tmp_path, monkeypatch) -> None:
    testing_session_local = _setup_db(tmp_path, monkeypatch)

    session_id = "20260420_130000_A1B2C3D4"
    device_id = "DEVICE-CHEST-001"

    with testing_session_local() as db:
        db.add(Device(device_id=device_id, device_role="chest", connected=True))
        db.add(SessionModel(session_id=session_id, status="RUNNING", preflight_passed=True))
        db.add(SessionDevice(session_id=session_id, device_id=device_id, required=True))
        db.commit()

    emitted: list[tuple[str, dict]] = []
    monkeypatch.setattr(
        devices_router.ws_runtime,
        "publish_device_event_sync",
        lambda sid, payload: emitted.append((sid, payload)),
    )

    with TestClient(main_app.app) as client:
        patch_response = client.patch(
            f"/devices/{device_id}",
            json={
                "connected": True,
                "recording": True,
                "battery_percent": 82.0,
                "storage_free_mb": 4096,
                "effective_hz": 99.7,
                "interval_p99_ms": 14.2,
                "jitter_p99_ms": 4.2,
            },
        )

        assert patch_response.status_code == 200

        history_response = client.get(f"/sessions/{session_id}/sampling-quality")

    assert history_response.status_code == 200
    payload = history_response.json()
    assert payload["session_id"] == session_id
    assert len(payload["points"]) == 1

    point = payload["points"][0]
    assert point["device_id"] == device_id
    assert point["effective_hz"] == 99.7
    assert point["interval_p99_ms"] == 14.2
    assert point["jitter_p99_ms"] == 4.2

    assert any(event_payload.get("type") == "DEVICE_SAMPLING_QUALITY" for _, event_payload in emitted)

    with testing_session_local() as db:
        rows = db.query(DeviceSamplingTelemetry).all()

    assert len(rows) == 1
    assert rows[0].session_id == session_id
    assert rows[0].device_id == device_id
    assert rows[0].interval_p99_ms == 14.2
    assert rows[0].jitter_p99_ms == 4.2
