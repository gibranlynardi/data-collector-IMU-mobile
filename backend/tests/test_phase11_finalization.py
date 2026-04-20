import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from zipfile import ZipFile

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.db.session as db_session
import app.main as main_app
import app.services.storage_monitor as storage_monitor_module
from app.core.config import get_settings
from app.db.base import Base
from app.db.models import Annotation, Device, Session as SessionModel, SessionDevice, VideoRecording


def _setup_db(tmp_path, monkeypatch):
  data_root = tmp_path / "data"
  data_root.mkdir(parents=True, exist_ok=True)
  monkeypatch.setenv("DATA_ROOT", str(data_root))
  monkeypatch.setenv("REQUIRED_DEVICE_ROLES", "chest")
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


def test_finalize_incomplete_requires_reason(tmp_path, monkeypatch) -> None:
  testing_session_local, _ = _setup_db(tmp_path, monkeypatch)
  session_id = "20260419_143022_A1B2C3D4"

  with testing_session_local() as db:
    db.add(SessionModel(session_id=session_id, status="SYNCING", preflight_passed=True))
    db.commit()

  with TestClient(main_app.app) as client:
    response = client.post(f"/sessions/{session_id}/finalize", json={"incomplete": True})

  assert response.status_code == 400
  assert "reason wajib diisi" in response.json()["detail"]


def test_finalize_complete_rejects_when_completeness_failed(tmp_path, monkeypatch) -> None:
  testing_session_local, _ = _setup_db(tmp_path, monkeypatch)
  session_id = "20260419_143022_A1B2C3D4"
  device_id = "DEVICE-CHEST-001"

  with testing_session_local() as db:
    db.add(Device(device_id=device_id, device_role="chest", connected=True))
    db.add(SessionModel(session_id=session_id, status="ENDING", preflight_passed=True))
    db.add(SessionDevice(session_id=session_id, device_id=device_id, required=True))
    db.commit()

  with TestClient(main_app.app) as client:
    response = client.post(f"/sessions/{session_id}/finalize", json={"incomplete": False})

  assert response.status_code == 409
  detail = response.json()["detail"]
  assert detail["completeness"]["checks"]["required_devices_have_data"] is False


def test_finalize_complete_writes_labeled_exports(tmp_path, monkeypatch) -> None:
  testing_session_local, data_root = _setup_db(tmp_path, monkeypatch)
  session_id = "20260419_143022_A1B2C3D4"
  device_id = "DEVICE-CHEST-001"

  start = datetime.now(UTC).replace(tzinfo=None)
  end = start + timedelta(seconds=5)
  ts_before = int((start - timedelta(seconds=1)).replace(tzinfo=UTC).timestamp() * 1_000_000_000)
  ts_inside = int((start + timedelta(seconds=1)).replace(tzinfo=UTC).timestamp() * 1_000_000_000)

  session_root = data_root / "sessions" / session_id
  sensor_dir = session_root / "sensor"
  video_dir = session_root / "video"
  sensor_dir.mkdir(parents=True, exist_ok=True)
  video_dir.mkdir(parents=True, exist_ok=True)

  csv_path = sensor_dir / f"chest_{device_id}.csv"
  csv_path.write_text(
    "session_id,device_id,device_role,seq,timestamp_device_unix_ns,timestamp_server_unix_ns,estimated_server_unix_ns,elapsed_ms,acc_x_g,acc_y_g,acc_z_g,gyro_x_deg,gyro_y_deg,gyro_z_deg\n"
    f"{session_id},{device_id},chest,1,{ts_before},{ts_before},{ts_before},1,0.1,0.2,0.3,1,2,3\n"
    f"{session_id},{device_id},chest,2,{ts_inside},{ts_inside},{ts_inside},2,0.1,0.2,0.3,1,2,3\n",
    encoding="utf-8",
  )
  (sensor_dir / f"chest_{device_id}.summary.json").write_text(
    json.dumps(
      {
        "session_id": session_id,
        "device_id": device_id,
        "device_role": "chest",
        "first_seq": 1,
        "last_seq": 2,
        "sample_count": 2,
        "duplicate_count": 0,
        "missing_seq_ranges": [],
      },
      ensure_ascii=True,
    ),
    encoding="utf-8",
  )

  video_path = video_dir / f"{session_id}_webcam.mp4"
  video_path.write_bytes(b"fake-mp4-content")

  with testing_session_local() as db:
    db.add(Device(device_id=device_id, device_role="chest", connected=True))
    db.add(SessionModel(session_id=session_id, status="ENDING", preflight_passed=True))
    db.add(SessionDevice(session_id=session_id, device_id=device_id, required=True))
    db.add(
      Annotation(
        annotation_id=f"ANN-{session_id}-0001",
        session_id=session_id,
        label="adl.walk.normal",
        started_at=start,
        ended_at=end,
      )
    )
    db.add(
      VideoRecording(
        video_id=f"VID-{session_id}-WEBCAM-01",
        session_id=session_id,
        camera_id="webcam-0",
        file_path=str(video_path),
        status="COMPLETED",
      )
    )
    db.commit()

  monkeypatch.setenv("SESSION_FINALIZE_MIN_SAMPLES_PER_REQUIRED_DEVICE", "2")
  monkeypatch.setenv("SESSION_FINALIZE_REQUIRE_VIDEO", "true")
  get_settings.cache_clear()

  with TestClient(main_app.app) as client:
    response = client.post(f"/sessions/{session_id}/finalize", json={"incomplete": False})
  assert response.status_code == 200
  assert response.json()["status"] == "COMPLETED"

  labeled_per_device = session_root / "export" / "labeled" / f"chest_{device_id}_labeled.csv"
  labeled_combined = session_root / "export" / "labeled" / "all_devices_labeled.csv"
  assert labeled_per_device.exists()
  assert labeled_combined.exists()

  lines = labeled_per_device.read_text(encoding="utf-8").strip().splitlines()
  assert lines[0].endswith("annotation_id,annotation_label")
  assert "ANN-20260419_143022_A1B2C3D4-0001,adl.walk.normal" in lines[2]
  assert lines[1].endswith(",")

  completeness_report = session_root / "completeness_report.json"
  assert completeness_report.exists()
  completeness_payload = json.loads(completeness_report.read_text(encoding="utf-8"))
  assert completeness_payload["complete"] is True

  export_zip = session_root / "export" / f"{session_id}_dataset.zip"
  assert export_zip.exists()
  with ZipFile(export_zip, "r") as zip_file:
    names = set(zip_file.namelist())
  assert f"sensor/chest_{device_id}.csv" in names
  assert f"video/{session_id}_webcam.mp4" in names
  assert "annotations.csv" in names
  assert "manifest.json" in names
  assert "sync_report.json" in names
  assert "preflight_report.json" in names
  assert "logs/warnings.log" in names
  assert f"export/labeled/chest_{device_id}_labeled.csv" in names
  assert "export/labeled/all_devices_labeled.csv" in names
