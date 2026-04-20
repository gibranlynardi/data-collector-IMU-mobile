import json
from zipfile import ZipFile

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.db.session as db_session
import app.main as main_app
from app.core.config import get_settings
from app.db.base import Base
from app.db.models import Annotation, Device, FileArtifact, PreflightCheck, Session as SessionModel, SessionDevice
from app.services.artifacts import ensure_session_layout, finalize_session_artifacts, materialize_session_storage, seed_session_artifacts


def test_phase9_materialize_session_storage_writes_required_files(tmp_path, monkeypatch) -> None:
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
    Base.metadata.create_all(bind=engine)

    session_id = "20260419_143022_A1B2C3D4"
    device_id = "DEVICE-CHEST-001"

    with testing_session_local() as db:
        db.add(Device(device_id=device_id, device_role="chest", connected=True, display_name="Chest"))
        db.add(SessionModel(session_id=session_id, status="CREATED", preflight_passed=True))
        db.add(SessionDevice(session_id=session_id, device_id=device_id, required=True))
        db.add(
            Annotation(
                annotation_id=f"ANN-{session_id}-0001",
                session_id=session_id,
                label="adl.walk.normal",
                notes="n1",
            )
        )
        db.add(
            PreflightCheck(
                session_id=session_id,
                check_name="backend_healthy",
                passed=True,
                details="ok",
            )
        )
        db.commit()

        session_root = ensure_session_layout(session_id)
        seed_session_artifacts(db, session_id, session_root)
        materialize_session_storage(db, session_id)

        required_files = [
            session_root / "session.json",
            session_root / "devices.json",
            session_root / "annotations.csv",
            session_root / "preflight_report.json",
            session_root / "logs" / "backend.log",
            session_root / "logs" / "device_events.log",
            session_root / "logs" / "warnings.log",
        ]
        for file_path in required_files:
            assert file_path.exists()

        session_payload = json.loads((session_root / "session.json").read_text(encoding="utf-8"))
        assert session_payload["session_id"] == session_id

        devices_payload = json.loads((session_root / "devices.json").read_text(encoding="utf-8"))
        assert devices_payload["devices"][0]["device_id"] == device_id

        annotations_lines = (session_root / "annotations.csv").read_text(encoding="utf-8").strip().splitlines()
        assert annotations_lines[0].startswith("annotation_id,session_id,label")
        assert len(annotations_lines) >= 2

        artifacts = db.query(FileArtifact).filter(FileArtifact.session_id == session_id).all()
        assert any(item.artifact_type == "session" and item.exists for item in artifacts)
        assert any(item.artifact_type == "devices" and item.exists for item in artifacts)
        assert any(item.artifact_type == "annotations" and item.exists for item in artifacts)


def test_phase9_finalize_creates_manifest_and_export_zip(tmp_path, monkeypatch) -> None:
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
    Base.metadata.create_all(bind=engine)

    session_id = "20260419_143022_A1B2C3D4"

    with testing_session_local() as db:
        db.add(SessionModel(session_id=session_id, status="COMPLETED", preflight_passed=True))
        db.commit()

        session_root = ensure_session_layout(session_id)
        (session_root / "sync_report.json").write_text(
            json.dumps({"session_id": session_id, "devices": []}, ensure_ascii=True),
            encoding="utf-8",
        )

        materialize_session_storage(db, session_id)
        manifest_path, export_zip_path = finalize_session_artifacts(db, session_id)

        assert manifest_path.exists()
        assert export_zip_path.exists()

        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        assert manifest["session_id"] == session_id
        assert manifest["file_count"] >= 5

        with ZipFile(export_zip_path, "r") as zip_file:
            names = set(zip_file.namelist())
        assert "session.json" in names
        assert "devices.json" in names
        assert "annotations.csv" in names
        assert "preflight_report.json" in names
        assert "sync_report.json" in names
