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
    get_settings.cache_clear()

    db_file = tmp_path / "metadata.db"
    engine = create_engine(f"sqlite:///{db_file.as_posix()}", connect_args={"check_same_thread": False})
    testing_session_local = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    db_session.engine = engine
    db_session.SessionLocal = testing_session_local
    main_app.engine = engine
    storage_monitor_module.SessionLocal = testing_session_local
    Base.metadata.create_all(bind=engine)


def test_runtime_metrics_endpoint(monkeypatch, tmp_path) -> None:
    _setup_db(tmp_path, monkeypatch)

    async def _fake_collect():
        return {
            "samples_per_sec_per_device": {"S:D": 100.0},
            "effective_hz_per_device": {"S:D": 99.8},
            "dropped_gap_samples_per_device": {"S:D": 3},
            "websocket_reconnect_count_per_device": {"S:D": 1},
            "upload_retry_count_per_device": {"S:D": 2},
            "csv_write_latency_ms_per_device": {"S:D": {"avg": 1.2, "max": 4.5}},
            "video_fps_runtime": {"S": 29.97},
            "storage_free_bytes": 1234,
        }

    monkeypatch.setattr("app.api.routers.health.collect_runtime_metrics", _fake_collect)

    with TestClient(main_app.app) as client:
        response = client.get("/metrics/runtime")

    assert response.status_code == 200
    payload = response.json()
    assert payload["samples_per_sec_per_device"]["S:D"] == 100.0
    assert payload["effective_hz_per_device"]["S:D"] == 99.8
    assert payload["video_fps_runtime"]["S"] == 29.97


def test_webcam_test_mode_endpoint(monkeypatch, tmp_path) -> None:
    _setup_db(tmp_path, monkeypatch)

    monkeypatch.setattr(
        "app.api.routers.health.video_recorder_service.run_test_mode",
        lambda duration_seconds=10: {
            "status": "completed",
            "duration_seconds": duration_seconds,
            "file_path": "data/webcam_test/sample.mp4",
            "frame_count": 300,
            "valid_mp4": True,
        },
    )

    with TestClient(main_app.app) as client:
        response = client.post("/health/webcam-test-mode?duration_seconds=10")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "completed"
    assert payload["duration_seconds"] == 10
    assert payload["valid_mp4"] is True


def test_annotation_start_stop_endpoints(monkeypatch, tmp_path) -> None:
    _setup_db(tmp_path, monkeypatch)

    with TestClient(main_app.app) as client:
        start_response = client.post(
            "/sessions/20260419_143022_A1B2C3D4/annotations/start",
            json={"label": "adl.walk.normal", "notes": "phase13 smoke"},
        )
        assert start_response.status_code == 200
        started = start_response.json()
        assert started["annotation_id"].startswith("ANN-20260419_143022_A1B2C3D4-")
        assert started["ended_at"] is None

        stop_response = client.post(
            f"/sessions/20260419_143022_A1B2C3D4/annotations/{started['annotation_id']}/stop"
        )
        assert stop_response.status_code == 200
        stopped = stop_response.json()
        assert stopped["annotation_id"] == started["annotation_id"]
        assert stopped["ended_at"] is not None
