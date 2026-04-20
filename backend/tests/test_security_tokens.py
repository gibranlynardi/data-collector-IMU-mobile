from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.db.session as db_session
import app.main as main_app
import app.services.storage_monitor as storage_monitor_module
from app.core.config import get_settings
from app.db.base import Base


def _setup_db(tmp_path, monkeypatch):
    data_root = tmp_path / "data"
    data_root.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("DATA_ROOT", str(data_root))
    monkeypatch.setenv("OPERATOR_API_TOKEN", "op-token-123")
    monkeypatch.setenv("DEVICE_ENROLLMENT_TOKEN", "dev-token-123")
    get_settings.cache_clear()

    db_file = tmp_path / "metadata.db"
    engine = create_engine(f"sqlite:///{db_file.as_posix()}", connect_args={"check_same_thread": False})
    testing_session_local = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    db_session.engine = engine
    db_session.SessionLocal = testing_session_local
    main_app.engine = engine
    storage_monitor_module.SessionLocal = testing_session_local
    Base.metadata.create_all(bind=engine)


def test_operator_and_device_tokens_are_enforced(tmp_path, monkeypatch) -> None:
    _setup_db(tmp_path, monkeypatch)

    with TestClient(main_app.app) as client:
        no_auth_devices = client.get("/devices")
        assert no_auth_devices.status_code == 401

        no_auth_register = client.post(
            "/devices/register",
            json={"device_id": "DEVICE-CHEST-001", "device_role": "chest", "display_name": "Chest"},
        )
        assert no_auth_register.status_code == 401

        ok_register = client.post(
            "/devices/register",
            headers={
                "X-Device-Enrollment-Token": "dev-token-123",
                "X-Device-Id": "DEVICE-CHEST-001",
            },
            json={"device_id": "DEVICE-CHEST-001", "device_role": "chest", "display_name": "Chest"},
        )
        assert ok_register.status_code == 200

        no_auth_create = client.post("/sessions", json={"override_reason": "token test"})
        assert no_auth_create.status_code == 401

        ok_create = client.post(
            "/sessions",
            headers={"X-Operator-Token": "op-token-123", "X-Operator-Id": "qa-operator"},
            json={"override_reason": "token test"},
        )
        assert ok_create.status_code == 200
