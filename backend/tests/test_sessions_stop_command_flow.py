import asyncio
import json

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.api.routers.sessions as sessions_router
import app.db.session as db_session
import app.main as main_app
import app.services.storage_monitor as storage_monitor_module
from app.db.base import Base
from app.db.models import Annotation, AnnotationAudit, Device, Session as SessionModel, SessionDevice


def _setup_db(tmp_path):
    sessions_router.csv_writer_service.close_all()
    db_file = tmp_path / "metadata.db"
    engine = create_engine(f"sqlite:///{db_file.as_posix()}", connect_args={"check_same_thread": False})
    testing_session_local = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    db_session.engine = engine
    db_session.SessionLocal = testing_session_local
    main_app.engine = engine
    storage_monitor_module.SessionLocal = testing_session_local
    Base.metadata.create_all(bind=engine)
    return testing_session_local


def test_stop_session_moves_to_syncing_when_stop_ack_pending(tmp_path, monkeypatch) -> None:
    testing_session_local = _setup_db(tmp_path)
    session_id = "20260419_143022_A1B2C3D4"
    device_id = "DEVICE-CHEST-001"

    with testing_session_local() as db:
        db.add(Device(device_id=device_id, device_role="chest", connected=True))
        db.add(SessionModel(session_id=session_id, status="RUNNING", preflight_passed=True))
        db.add(SessionDevice(session_id=session_id, device_id=device_id, required=True))
        db.add(
            Annotation(
                annotation_id=f"ANN-{session_id}-0001",
                session_id=session_id,
                label="adl.walk.normal",
            )
        )
        db.commit()

    calls = {"csv_close": 0, "video_stop": 0}

    async def _fake_stop_acks_pending(_sid: str, device_ids: list[str], timeout_seconds: float):
        del timeout_seconds
        await asyncio.sleep(0)
        return {
            "sent_devices": list(device_ids),
            "acked_devices": [],
            "pending_devices": list(device_ids),
        }

    monkeypatch.setattr(sessions_router.ws_runtime, "request_stop_acks", _fake_stop_acks_pending)
    monkeypatch.setattr(
        sessions_router.csv_writer_service,
        "flush_session",
        lambda _sid: None,
    )
    monkeypatch.setattr(
        sessions_router.csv_writer_service,
        "close_session",
        lambda _sid: calls.__setitem__("csv_close", calls["csv_close"] + 1),
    )
    monkeypatch.setattr(
        sessions_router.video_recorder_service,
        "stop_session_recording",
        lambda _db, _sid, suppress_errors=False: calls.__setitem__("video_stop", calls["video_stop"] + 1),
    )

    with TestClient(main_app.app) as client:
        response = client.post(f"/sessions/{session_id}/stop")

    assert response.status_code == 200
    assert response.json()["status"] == "SYNCING"
    assert calls["csv_close"] == 0
    assert calls["video_stop"] == 1

    with testing_session_local() as db:
        annotation = db.get(Annotation, f"ANN-{session_id}-0001")
        assert annotation is not None
        assert annotation.ended_at is not None
        assert annotation.auto_closed is True
        audit = (
            db.query(AnnotationAudit)
            .filter(
                AnnotationAudit.session_id == session_id,
                AnnotationAudit.annotation_id == annotation.annotation_id,
                AnnotationAudit.action == "auto_close",
            )
            .first()
        )
        assert audit is not None


def test_stop_session_closes_outputs_when_all_stop_acked(tmp_path, monkeypatch) -> None:
    testing_session_local = _setup_db(tmp_path)
    session_id = "20260419_143022_A1B2C3D4"
    device_id = "DEVICE-CHEST-001"

    with testing_session_local() as db:
        db.add(Device(device_id=device_id, device_role="chest", connected=True))
        db.add(SessionModel(session_id=session_id, status="RUNNING", preflight_passed=True))
        db.add(SessionDevice(session_id=session_id, device_id=device_id, required=True))
        db.add(
            Annotation(
                annotation_id=f"ANN-{session_id}-0001",
                session_id=session_id,
                label="adl.walk.normal",
            )
        )
        db.commit()

    calls = {"csv_close": 0, "video_stop": 0}

    async def _fake_stop_acks_done(_sid: str, device_ids: list[str], timeout_seconds: float):
        del timeout_seconds
        await asyncio.sleep(0)
        return {
            "sent_devices": list(device_ids),
            "acked_devices": list(device_ids),
            "pending_devices": [],
        }

    monkeypatch.setattr(sessions_router.ws_runtime, "request_stop_acks", _fake_stop_acks_done)
    monkeypatch.setattr(
        sessions_router.csv_writer_service,
        "flush_session",
        lambda _sid: None,
    )
    monkeypatch.setattr(
        sessions_router.csv_writer_service,
        "close_session",
        lambda _sid: calls.__setitem__("csv_close", calls["csv_close"] + 1),
    )
    monkeypatch.setattr(
        sessions_router.video_recorder_service,
        "stop_session_recording",
        lambda _db, _sid, suppress_errors=False: calls.__setitem__("video_stop", calls["video_stop"] + 1),
    )

    with TestClient(main_app.app) as client:
        response = client.post(f"/sessions/{session_id}/stop")

    assert response.status_code == 200
    assert response.json()["status"] == "ENDING"
    assert calls["csv_close"] == 1
    assert calls["video_stop"] == 1

    with testing_session_local() as db:
        annotation = db.get(Annotation, f"ANN-{session_id}-0001")
        assert annotation is not None
        assert annotation.ended_at is not None
        assert annotation.auto_closed is True
        audit = (
            db.query(AnnotationAudit)
            .filter(
                AnnotationAudit.session_id == session_id,
                AnnotationAudit.annotation_id == annotation.annotation_id,
                AnnotationAudit.action == "auto_close",
            )
            .first()
        )
        assert audit is not None


def test_finalize_incomplete_allowed_from_syncing(tmp_path) -> None:
    testing_session_local = _setup_db(tmp_path)
    session_id = "20260419_143022_A1B2C3D4"

    with testing_session_local() as db:
        db.add(SessionModel(session_id=session_id, status="SYNCING", preflight_passed=True))
        db.commit()

    with TestClient(main_app.app) as client:
        response = client.post(
            f"/sessions/{session_id}/finalize",
            json={"incomplete": True, "reason": "device offline permanen saat syncing"},
        )

    assert response.status_code == 200
    assert response.json()["status"] == "INCOMPLETE_FINALIZED"


def test_stop_session_emits_missing_sample_summary_to_sync_report(tmp_path, monkeypatch) -> None:
    data_root = tmp_path / "data"
    data_root.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("DATA_ROOT", str(data_root))
    sessions_router.get_settings.cache_clear()

    testing_session_local = _setup_db(tmp_path)
    session_id = "20260419_143022_A1B2C3D4"
    device_id = "DEVICE-CHEST-001"

    with testing_session_local() as db:
        db.add(Device(device_id=device_id, device_role="chest", connected=True))
        db.add(SessionModel(session_id=session_id, status="RUNNING", preflight_passed=True))
        db.add(SessionDevice(session_id=session_id, device_id=device_id, required=True))
        db.commit()

    data_root = sessions_router.get_settings().data_root
    sensor_dir = data_root / "sessions" / session_id / "sensor"
    sensor_dir.mkdir(parents=True, exist_ok=True)
    (sensor_dir / f"chest_{device_id}.summary.json").write_text(
        json.dumps(
            {
                "session_id": session_id,
                "device_id": device_id,
                "device_role": "chest",
                "sample_count": 100,
                "duplicate_count": 2,
                "missing_seq_ranges": [[11, 13]],
            },
            ensure_ascii=True,
        ),
        encoding="utf-8",
    )

    async def _fake_stop_acks_done(_sid: str, device_ids: list[str], timeout_seconds: float):
        del timeout_seconds
        await asyncio.sleep(0)
        return {
            "sent_devices": list(device_ids),
            "acked_devices": list(device_ids),
            "pending_devices": [],
        }

    monkeypatch.setattr(sessions_router.ws_runtime, "request_stop_acks", _fake_stop_acks_done)
    monkeypatch.setattr(sessions_router.csv_writer_service, "flush_session", lambda _sid: None)
    monkeypatch.setattr(sessions_router.csv_writer_service, "close_session", lambda _sid: None)
    monkeypatch.setattr(
        sessions_router.video_recorder_service,
        "stop_session_recording",
        lambda _db, _sid, suppress_errors=False: {"status": "completed"},
    )

    with TestClient(main_app.app) as client:
        response = client.post(f"/sessions/{session_id}/stop")
    assert response.status_code == 200

    sync_report_path = data_root / "sessions" / session_id / "sync_report.json"
    assert sync_report_path.exists()
    payload = json.loads(sync_report_path.read_text(encoding="utf-8"))
    assert payload["missing_range_device_count"] == 1
    assert payload["missing_ranges_by_device"][0]["device_id"] == device_id
