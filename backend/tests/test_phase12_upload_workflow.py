import hashlib
import json

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.db.session as db_session
import app.main as main_app
import app.services.storage_monitor as storage_monitor_module
from app.core.config import get_settings
from app.db.base import Base
from app.db.models import Session as SessionModel


def _setup_db(tmp_path, monkeypatch):
    data_root = tmp_path / "data"
    data_root.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("DATA_ROOT", str(data_root))
    monkeypatch.setenv("FAMS_HOST", "fams.example.org")
    monkeypatch.setenv("FAMS_USER", "collector")
    monkeypatch.setenv("FAMS_REMOTE_PATH", "/srv/fams/archive")
    get_settings.cache_clear()

    db_file = tmp_path / "metadata.db"
    engine = create_engine(f"sqlite:///{db_file.as_posix()}", connect_args={"check_same_thread": False})
    testing_session_local = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    db_session.engine = engine
    db_session.SessionLocal = testing_session_local
    main_app.engine = engine
    storage_monitor_module.SessionLocal = testing_session_local
    Base.metadata.create_all(bind=engine)
    return testing_session_local, data_root


def test_upload_instructions_and_mark_uploaded_flow(tmp_path, monkeypatch) -> None:
    testing_session_local, data_root = _setup_db(tmp_path, monkeypatch)
    session_id = "20260419_143022_A1B2C3D4"

    with testing_session_local() as db:
        db.add(SessionModel(session_id=session_id, status="COMPLETED", preflight_passed=True))
        db.commit()

    export_dir = data_root / "sessions" / session_id / "export"
    export_dir.mkdir(parents=True, exist_ok=True)
    export_zip = export_dir / f"{session_id}_dataset.zip"
    export_zip.write_bytes(b"phase12-export-content")
    expected_checksum = hashlib.sha256(export_zip.read_bytes()).hexdigest()

    with TestClient(main_app.app) as client:
        instructions = client.get(f"/sessions/{session_id}/upload-instructions")
        assert instructions.status_code == 200
        payload = instructions.json()

        assert payload["session_id"] == session_id
        assert payload["checksum_sha256"] == expected_checksum
        assert payload["export_zip_path"].endswith(f"{session_id}_dataset.zip")
        assert "upload_to_fams.ps1" in payload["command_powershell"]
        assert "upload_to_fams.sh" in payload["command_shell"]
        assert payload["remote_target"].endswith(f"/{session_id}_dataset.zip")

        status_before = client.get(f"/sessions/{session_id}/archive-upload")
        assert status_before.status_code == 200
        assert status_before.json()["uploaded"] is False

        marked = client.post(
            f"/sessions/{session_id}/archive-upload/mark-uploaded",
            json={
                "uploaded_by": "antho",
                "remote_path": f"/srv/fams/archive/{session_id}_dataset.zip",
                "checksum": expected_checksum,
            },
        )
        assert marked.status_code == 200
        marked_payload = marked.json()
        assert marked_payload["uploaded"] is True
        assert marked_payload["uploaded_by"] == "antho"
        assert marked_payload["remote_path"].endswith(f"/{session_id}_dataset.zip")
        assert marked_payload["checksum"] == expected_checksum

        status_after = client.get(f"/sessions/{session_id}/archive-upload")
        assert status_after.status_code == 200
        assert status_after.json()["uploaded"] is True


def test_mark_uploaded_rejects_checksum_mismatch(tmp_path, monkeypatch) -> None:
    testing_session_local, data_root = _setup_db(tmp_path, monkeypatch)
    session_id = "20260419_143022_A1B2C3D4"

    with testing_session_local() as db:
        db.add(SessionModel(session_id=session_id, status="COMPLETED", preflight_passed=True))
        db.commit()

    export_dir = data_root / "sessions" / session_id / "export"
    export_dir.mkdir(parents=True, exist_ok=True)
    export_zip = export_dir / f"{session_id}_dataset.zip"
    export_zip.write_bytes(b"phase12-export-content")

    with TestClient(main_app.app) as client:
        response = client.post(
            f"/sessions/{session_id}/archive-upload/mark-uploaded",
            json={
                "uploaded_by": "antho",
                "remote_path": f"/srv/fams/archive/{session_id}_dataset.zip",
                "checksum": "deadbeef",
            },
        )

    assert response.status_code == 400
    assert "checksum mismatch" in response.json()["detail"]
