from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.db.session as db_session
import app.main as main_app
from app.db.base import Base


def test_register_device_does_not_mark_transport_connected(tmp_path) -> None:
    db_file = tmp_path / "metadata.db"
    engine = create_engine(f"sqlite:///{db_file.as_posix()}", connect_args={"check_same_thread": False})
    testing_session_local = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    db_session.engine = engine
    db_session.SessionLocal = testing_session_local
    main_app.engine = engine
    Base.metadata.create_all(bind=engine)

    payload = {
        "device_id": "DEVICE-CHEST-001",
        "device_role": "chest",
        "display_name": "Chest Phone",
    }

    with TestClient(main_app.app) as client:
        response = client.post("/devices/register", json=payload)

    assert response.status_code == 200
    body = response.json()
    assert body["device_id"] == payload["device_id"]
    assert body["connected"] is False
