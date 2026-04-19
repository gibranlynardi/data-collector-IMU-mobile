from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.db.session as db_session
import app.main as main_app
from app.core.config import get_settings
from app.db.base import Base
from app.db.models import Session as SessionModel, VideoRecording
from app.services.video_recorder import video_recorder_service


class _FakeCapture:
    def __init__(self) -> None:
        self._opened = True
        self._fps = 30.0
        self._width = 640.0
        self._height = 480.0

    def isOpened(self) -> bool:
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

    def isOpened(self) -> bool:
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
    def VideoCapture(_source):
        return _FakeCapture()

    @staticmethod
    def VideoWriter_fourcc(*_args):
        return 0

    @staticmethod
    def VideoWriter(path: str, _fourcc: int, _fps: float, _size):
        return _FakeWriter(path)


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

    sidecar = data_root / "sessions" / session_id / "video" / f"{session_id}_webcam.json"
    assert sidecar.exists()


def test_video_recorder_inspect_webcam_fields(monkeypatch) -> None:
    monkeypatch.setattr(video_recorder_service, "_import_cv2", lambda: _FakeCv2)
    report = video_recorder_service.inspect_webcam()
    assert report["webcam_connected"] is True
    assert report["webcam_preview_ok"] is True
    assert report["webcam_fps"] >= 15
    assert "webcam_detail" in report
