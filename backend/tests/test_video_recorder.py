import json
import threading
from datetime import UTC, datetime
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.db.session as db_session
import app.main as main_app
from app.core.config import get_settings
from app.db.base import Base
from app.db.models import Session as SessionModel, VideoRecording
from app.services.video_recorder import video_recorder_service
from app.services.video_recorder import RecordingState


class _FakeCapture:
    def __init__(self) -> None:
        self._opened = True
        self._fps = 30.0
        self._width = 640.0
        self._height = 480.0

    def is_opened(self) -> bool:
        return self._opened

    def read(self):
        return True, "frame"

    def release(self) -> None:
        self._opened = False

    def set(self, prop: int, value: float) -> None:
        if prop == 3:
            self._width = value
        elif prop == 4:
            self._height = value
        elif prop == 5:
            self._fps = value

    def get(self, prop: int) -> float:
        if prop == 3:
            return self._width
        if prop == 4:
            return self._height
        if prop == 5:
            return self._fps
        return 0.0


class _FakeWriter:
    def __init__(self, path: str) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._opened = True
        self._frames = 0

    def is_opened(self) -> bool:
        return self._opened

    def write(self, _frame) -> None:
        self._frames += 1
        self.path.write_bytes(f"frames={self._frames}".encode("utf-8"))

    def release(self) -> None:
        self._opened = False


class _FakeCv2:
    CAP_PROP_FRAME_WIDTH = 3
    CAP_PROP_FRAME_HEIGHT = 4
    CAP_PROP_FPS = 5

    @staticmethod
    def video_capture(_source):
        return _FakeCapture()

    @staticmethod
    def video_writer_fourcc(*_args):
        return 0

    @staticmethod
    def video_writer(path: str, _fourcc: int, _fps: float, _size):
        return _FakeWriter(path)


_FakeCapture.isOpened = _FakeCapture.is_opened
_FakeWriter.isOpened = _FakeWriter.is_opened
_FakeCv2.VideoCapture = staticmethod(_FakeCv2.video_capture)
_FakeCv2.VideoWriter_fourcc = staticmethod(_FakeCv2.video_writer_fourcc)
_FakeCv2.VideoWriter = staticmethod(_FakeCv2.video_writer)


class _BrokenCapture:
    def is_opened(self) -> bool:
        return False

    def read(self):
        return False, None

    def release(self) -> None:
        return

    def set(self, _prop: int, _value: float) -> None:
        return

    def get(self, _prop: int) -> float:
        return 0.0


class _BrokenCv2(_FakeCv2):
    @staticmethod
    def video_capture(_source):
        return _BrokenCapture()


_BrokenCapture.isOpened = _BrokenCapture.is_opened
_BrokenCv2.VideoCapture = staticmethod(_BrokenCv2.video_capture)


class _AlwaysFailCapture:
    def read(self):
        return False, None


class _FakePopen:
    def __init__(self, cmd, stdout=None, stderr=None):
        self.cmd = cmd
        self.stdout = stdout
        self.stderr = stderr
        self._returncode = None

    def poll(self):
        return self._returncode

    def terminate(self):
        self._returncode = 0

    def wait(self, timeout=None):
        self._returncode = 0
        return 0

    def kill(self):
        self._returncode = -9


class _FakeCompletedProcess:
    def __init__(self, returncode: int = 0, stdout: str = "", stderr: str = "") -> None:
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def test_video_recorder_start_stop_writes_sidecar(tmp_path: Path, monkeypatch) -> None:
    data_root = tmp_path / "data"
    data_root.mkdir(parents=True, exist_ok=True)

    monkeypatch.setenv("DATA_ROOT", str(data_root))
    get_settings.cache_clear()
    video_recorder_service._settings = get_settings()
    monkeypatch.setattr(video_recorder_service, "_import_cv2", lambda: _FakeCv2)

    db_file = tmp_path / "metadata.db"
    engine = create_engine(f"sqlite:///{db_file.as_posix()}", connect_args={"check_same_thread": False})
    testing_session_local = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    db_session.engine = engine
    db_session.SessionLocal = testing_session_local
    main_app.engine = engine

    Base.metadata.create_all(bind=engine)

    session_id = "20260419_143022_A1B2C3D4"
    with testing_session_local() as db:
        db.add(SessionModel(session_id=session_id, status="CREATED", preflight_passed=True))
        db.commit()

        started = video_recorder_service.start_session_recording(db, session_id)
        assert started["status"] == "recording"

        stopped = video_recorder_service.stop_session_recording(db, session_id)
        assert stopped["status"] in {"completed", "failed"}

        record = db.get(VideoRecording, started["video_id"])
        assert record is not None
        assert record.status in {"COMPLETED", "FAILED"}
        assert record.file_path.endswith(f"{session_id}_webcam.mp4")
        assert record.video_start_monotonic_ms is not None
        assert record.video_start_monotonic_ms >= 0
        assert record.video_end_monotonic_ms is not None
        assert record.video_end_monotonic_ms >= record.video_start_monotonic_ms

    sidecar = data_root / "sessions" / session_id / "video" / f"{session_id}_webcam.json"
    assert sidecar.exists()
    sidecar_payload = json.loads(sidecar.read_text(encoding="utf-8"))
    assert "video_start_monotonic_ms" in sidecar_payload
    assert sidecar_payload["video_start_monotonic_ms"] >= 0
    assert "video_end_monotonic_ms" in sidecar_payload
    assert sidecar_payload["video_end_monotonic_ms"] >= sidecar_payload["video_start_monotonic_ms"]


def test_video_recorder_inspect_webcam_fields(monkeypatch) -> None:
    monkeypatch.setattr(video_recorder_service, "_import_cv2", lambda: _FakeCv2)
    report = video_recorder_service.inspect_webcam()
    assert report["webcam_connected"] is True
    assert report["webcam_preview_ok"] is True
    assert report["webcam_fps"] >= 15
    assert "webcam_detail" in report


def test_video_recorder_ffmpeg_fallback_when_opencv_fails(tmp_path: Path, monkeypatch) -> None:
    data_root = tmp_path / "data"
    data_root.mkdir(parents=True, exist_ok=True)

    monkeypatch.setenv("DATA_ROOT", str(data_root))
    monkeypatch.setenv("FFMPEG_FALLBACK_ENABLED", "true")
    monkeypatch.setenv("FFMPEG_CAMERA_INPUT", "video=Fake Camera")
    monkeypatch.setenv("FFMPEG_CAMERA_FORMAT", "dshow")
    get_settings.cache_clear()
    video_recorder_service._settings = get_settings()

    monkeypatch.setattr(video_recorder_service, "_import_cv2", lambda: _BrokenCv2)
    monkeypatch.setattr("app.services.video_recorder.subprocess.Popen", _FakePopen)

    db_file = tmp_path / "metadata.db"
    engine = create_engine(f"sqlite:///{db_file.as_posix()}", connect_args={"check_same_thread": False})
    testing_session_local = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    db_session.engine = engine
    db_session.SessionLocal = testing_session_local
    main_app.engine = engine

    Base.metadata.create_all(bind=engine)

    session_id = "20260419_143022_A1B2C3D4"
    with testing_session_local() as db:
        db.add(SessionModel(session_id=session_id, status="CREATED", preflight_passed=True))
        db.commit()

        started = video_recorder_service.start_session_recording(db, session_id)
        assert started["status"] == "recording"
        assert started["backend"] == "ffmpeg"

        stopped = video_recorder_service.stop_session_recording(db, session_id)
        assert stopped["status"] in {"completed", "failed"}
        assert stopped["backend"] == "ffmpeg"


def test_video_metadata_endpoints(tmp_path: Path, monkeypatch) -> None:
    data_root = tmp_path / "data"
    data_root.mkdir(parents=True, exist_ok=True)

    monkeypatch.setenv("DATA_ROOT", str(data_root))
    get_settings.cache_clear()
    video_recorder_service._settings = get_settings()

    db_file = tmp_path / "metadata.db"
    engine = create_engine(f"sqlite:///{db_file.as_posix()}", connect_args={"check_same_thread": False})
    testing_session_local = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    db_session.engine = engine
    db_session.SessionLocal = testing_session_local
    main_app.engine = engine

    Base.metadata.create_all(bind=engine)

    session_id = "20260419_143022_A1B2C3D4"
    sidecar_path = data_root / "sessions" / session_id / "video" / f"{session_id}_webcam.json"
    sidecar_path.parent.mkdir(parents=True, exist_ok=True)
    sidecar_payload = {
        "session_id": session_id,
        "camera_id": "webcam-0",
        "fps": 30.0,
        "width": 1280,
        "height": 720,
        "codec": "mp4v",
        "video_start_server_time": "2026-04-19T10:00:00",
        "video_start_monotonic_ms": 1234567,
        "video_end_server_time": "2026-04-19T10:00:10",
        "video_end_monotonic_ms": 1244567,
        "duration_ms": 10000,
        "frame_count": 300,
        "dropped_frame_estimate": 0,
        "file_path": str(data_root / "sessions" / session_id / "video" / f"{session_id}_webcam.mp4"),
        "status": "COMPLETED",
        "error": None,
        "backend": "opencv",
    }
    sidecar_path.write_text(json.dumps(sidecar_payload, ensure_ascii=True), encoding="utf-8")

    with testing_session_local() as db:
        db.add(SessionModel(session_id=session_id, status="COMPLETED", preflight_passed=True))
        db.commit()

    with TestClient(main_app.app) as client:
        read_resp = client.get(f"/sessions/{session_id}/video/metadata")
        assert read_resp.status_code == 200
        assert read_resp.json()["session_id"] == session_id

        download_resp = client.get(f"/sessions/{session_id}/video/metadata/download")
        assert download_resp.status_code == 200
        assert "application/json" in download_resp.headers.get("content-type", "")


def test_video_anonymize_endpoint(tmp_path: Path, monkeypatch) -> None:
    data_root = tmp_path / "data"
    data_root.mkdir(parents=True, exist_ok=True)

    monkeypatch.setenv("DATA_ROOT", str(data_root))
    get_settings.cache_clear()
    video_recorder_service._settings = get_settings()

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

    monkeypatch.setattr(
        video_recorder_service,
        "anonymize_session_video",
        lambda sid, force_mock=False: {
            "session_id": sid,
            "status": "completed",
            "source_file_path": str(data_root / "sessions" / sid / "video" / f"{sid}_webcam.mp4"),
            "output_file_path": str(data_root / "sessions" / sid / "video" / f"{sid}_webcam_anon.mp4"),
            "metadata_file_path": str(data_root / "sessions" / sid / "video" / f"{sid}_webcam_anon.json"),
            "frame_count": 10,
            "faces_blurred": 4,
            "error": None,
        },
    )

    with TestClient(main_app.app) as client:
        response = client.post(f"/sessions/{session_id}/video/anonymize")
        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "completed"
        assert body["faces_blurred"] == 4


def test_video_anonymize_uses_deface_cli(tmp_path: Path, monkeypatch) -> None:
    data_root = tmp_path / "data"
    data_root.mkdir(parents=True, exist_ok=True)

    monkeypatch.setenv("DATA_ROOT", str(data_root))
    monkeypatch.setenv("VIDEO_DEFACE_EXECUTABLE", "deface")
    monkeypatch.setenv("VIDEO_DEFACE_REPLACEWITH", "blur")
    monkeypatch.setenv("VIDEO_DEFACE_KEEP_AUDIO", "false")
    monkeypatch.setenv("VIDEO_DEFACE_BACKEND", "auto")
    get_settings.cache_clear()
    video_recorder_service._settings = get_settings()

    session_id = "20260419_143022_A1B2C3D4"
    video_dir = data_root / "sessions" / session_id / "video"
    video_dir.mkdir(parents=True, exist_ok=True)
    source = video_dir / f"{session_id}_webcam.mp4"
    source.write_bytes(b"video")

    captured: dict[str, list[str]] = {}

    def _fake_run(cmd, check, capture_output, text):
        captured["cmd"] = cmd
        output = video_dir / f"{session_id}_webcam_anon.mp4"
        output.write_bytes(b"anon")
        return _FakeCompletedProcess(returncode=0)

    monkeypatch.setattr("app.services.video_recorder.subprocess.run", _fake_run)

    result = video_recorder_service.anonymize_session_video(session_id)
    assert result["status"] == "completed"
    assert result["output_file_path"].endswith(f"{session_id}_webcam_anon.mp4")
    assert captured["cmd"][0] == "deface"
    assert "--replacewith" in captured["cmd"]


def test_record_loop_pushes_failure_event_once(monkeypatch) -> None:
    session_id = "20260419_143022_A1B2C3D4"
    sidecar = Path("C:/tmp/fake_sidecar.json")
    state = RecordingState(
        session_id=session_id,
        video_id="VID-TEST",
        camera_id="webcam-0",
        file_path=Path("C:/tmp/fake_video.mp4"),
        sidecar_path=sidecar,
        stop_event=threading.Event(),
        thread=None,
        capture=_AlwaysFailCapture(),
        writer=None,
        ffmpeg_process=None,
        backend="opencv",
        started_at=datetime.now(UTC).replace(tzinfo=None),
        started_monotonic=0.0,
        fps=30.0,
        width=640,
        height=480,
        codec="mp4v",
    )

    events: list[dict] = []
    warnings: list[dict] = []

    monkeypatch.setattr(
        "app.services.ws_runtime.ws_runtime.publish_session_event_sync",
        lambda _sid, payload: events.append(payload),
    )
    monkeypatch.setattr(
        "app.services.ws_runtime.ws_runtime.publish_warning_sync",
        lambda _sid, **kwargs: warnings.append({"warning": kwargs.get("warning")}),
    )
    monkeypatch.setattr(
        "app.services.video_recorder.time.sleep",
        lambda _secs: state.stop_event.set(),
    )

    with video_recorder_service._lock:
        video_recorder_service._active[session_id] = state
    try:
        video_recorder_service._record_loop(session_id)
        video_recorder_service._mark_recording_failed(state, "failed to read frame")
    finally:
        with video_recorder_service._lock:
            video_recorder_service._active.pop(session_id, None)

    assert state.failed is True
    assert state.failure_notified is True
    assert len(events) == 1
    assert events[0]["type"] == "VIDEO_RECORDER_STATUS"
    assert events[0]["status"] == "failed"
    assert len(warnings) == 1
