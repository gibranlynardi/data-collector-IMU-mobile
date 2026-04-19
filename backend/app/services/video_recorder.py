from __future__ import annotations

import json
import logging
import threading
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from types import ModuleType
from typing import Any

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.models import VideoRecording

logger = logging.getLogger(__name__)


@dataclass
class RecordingState:
    session_id: str
    video_id: str
    camera_id: str
    file_path: Path
    sidecar_path: Path
    stop_event: threading.Event
    thread: threading.Thread
    capture: Any
    writer: Any
    started_at: datetime
    started_monotonic: float
    fps: float
    width: int
    height: int
    codec: str
    frame_count: int = 0
    dropped_frame_estimate: int = 0
    failed: bool = False
    error_message: str | None = None


class VideoRecorderService:
    def __init__(self) -> None:
        self._settings = get_settings()
        self._lock = threading.RLock()
        self._active: dict[str, RecordingState] = {}

    @staticmethod
    def _import_cv2() -> ModuleType:
        import cv2  # type: ignore

        return cv2

    def inspect_webcam(self) -> dict[str, Any]:
        settings = self._settings
        source = settings.webcam_path if settings.webcam_path else settings.webcam_index

        try:
            cv2 = self._import_cv2()
            cap = cv2.VideoCapture(source)
            if not cap.isOpened():
                return {
                    "webcam_connected": False,
                    "webcam_preview_ok": False,
                    "webcam_fps": 0.0,
                    "webcam_fps_ok": False,
                    "webcam_detail": f"camera source {source} cannot be opened",
                }

            ok, _ = cap.read()
            fps = float(cap.get(cv2.CAP_PROP_FPS) or 0.0)
            if fps <= 1.0:
                fps = settings.webcam_target_fps
            cap.release()

            preview_ok = bool(ok)
            fps_ok = fps >= settings.webcam_min_fps
            detail = f"camera source {source} ready fps={fps:.2f}" if preview_ok else f"camera source {source} opened but no frame"
            return {
                "webcam_connected": True,
                "webcam_preview_ok": preview_ok,
                "webcam_fps": fps,
                "webcam_fps_ok": fps_ok,
                "webcam_detail": detail,
            }
        except Exception as exc:
            return {
                "webcam_connected": False,
                "webcam_preview_ok": False,
                "webcam_fps": 0.0,
                "webcam_fps_ok": False,
                "webcam_detail": f"opencv unavailable or camera check failed: {exc}",
            }

    def start_session_recording(self, db: Session, session_id: str, allow_override: bool = False) -> dict[str, Any]:
        with self._lock:
            if session_id in self._active:
                return self._status_payload(self._active[session_id], status="recording")

            settings = self._settings
            session_root = settings.data_root / "sessions" / session_id
            video_dir = session_root / "video"
            video_dir.mkdir(parents=True, exist_ok=True)

            file_path = video_dir / f"{session_id}_webcam.mp4"
            sidecar_path = video_dir / f"{session_id}_webcam.json"
            video_id = f"VID-{session_id}-WEBCAM-01"
            camera_id = f"webcam-{settings.webcam_index}" if not settings.webcam_path else str(settings.webcam_path)

            try:
                cv2 = self._import_cv2()
                source = settings.webcam_path if settings.webcam_path else settings.webcam_index
                cap = cv2.VideoCapture(source)
                if not cap.isOpened():
                    raise RuntimeError(f"camera source {source} cannot be opened")

                cap.set(cv2.CAP_PROP_FRAME_WIDTH, settings.webcam_target_width)
                cap.set(cv2.CAP_PROP_FRAME_HEIGHT, settings.webcam_target_height)
                cap.set(cv2.CAP_PROP_FPS, settings.webcam_target_fps)

                ok, first_frame = cap.read()
                if not ok:
                    cap.release()
                    raise RuntimeError("camera opened but failed to read first frame")

                width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or settings.webcam_target_width)
                height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or settings.webcam_target_height)
                fps = float(cap.get(cv2.CAP_PROP_FPS) or 0.0)
                if fps <= 1.0:
                    fps = settings.webcam_target_fps

                codec = settings.webcam_codec
                fourcc = cv2.VideoWriter_fourcc(*codec)
                writer = cv2.VideoWriter(str(file_path), fourcc, fps, (width, height))
                if not writer.isOpened():
                    cap.release()
                    raise RuntimeError("failed to open video writer")

                started_at = datetime.now(UTC).replace(tzinfo=None)
                stop_event = threading.Event()
                state = RecordingState(
                    session_id=session_id,
                    video_id=video_id,
                    camera_id=camera_id,
                    file_path=file_path,
                    sidecar_path=sidecar_path,
                    stop_event=stop_event,
                    thread=threading.Thread(target=self._record_loop, args=(session_id,), name=f"video-rec-{session_id}", daemon=True),
                    capture=cap,
                    writer=writer,
                    started_at=started_at,
                    started_monotonic=time.monotonic(),
                    fps=fps,
                    width=width,
                    height=height,
                    codec=codec,
                )

                # Write first frame immediately to ensure file validity.
                state.writer.write(first_frame)
                state.frame_count = 1

                self._upsert_video_record(db, state, status="RECORDING")
                self._active[session_id] = state
                state.thread.start()
                return self._status_payload(state, status="recording")
            except Exception as exc:
                logger.exception("Failed starting webcam recording for session %s", session_id)
                if not allow_override:
                    raise RuntimeError(f"video recorder start failed: {exc}") from exc
                self._upsert_failed_record(db, session_id, video_id, camera_id, file_path, str(exc))
                return {
                    "status": "failed",
                    "session_id": session_id,
                    "video_id": video_id,
                    "error": str(exc),
                }

    def stop_session_recording(self, db: Session, session_id: str, suppress_errors: bool = False) -> dict[str, Any]:
        with self._lock:
            state = self._active.pop(session_id, None)

        if state is None:
            existing = (
                db.query(VideoRecording)
                .filter(VideoRecording.session_id == session_id)
                .order_by(VideoRecording.video_start_server_time.desc())
                .first()
            )
            if existing:
                return {
                    "status": existing.status.lower(),
                    "session_id": session_id,
                    "video_id": existing.video_id,
                    "file_path": existing.file_path,
                }
            return {"status": "idle", "session_id": session_id}

        try:
            state.stop_event.set()
            state.thread.join(timeout=5.0)
            state.capture.release()
            state.writer.release()

            ended_at = datetime.now(UTC).replace(tzinfo=None)
            duration_ms = int((time.monotonic() - state.started_monotonic) * 1000)
            sidecar = {
                "session_id": session_id,
                "camera_id": state.camera_id,
                "fps": round(state.fps, 2),
                "width": state.width,
                "height": state.height,
                "codec": state.codec,
                "video_start_server_time": state.started_at.isoformat(),
                "video_end_server_time": ended_at.isoformat(),
                "duration_ms": duration_ms,
                "frame_count": state.frame_count,
                "dropped_frame_estimate": state.dropped_frame_estimate,
                "file_path": str(state.file_path),
                "status": "FAILED" if state.failed else "COMPLETED",
                "error": state.error_message,
            }
            state.sidecar_path.write_text(json.dumps(sidecar, ensure_ascii=True, indent=2), encoding="utf-8")

            record = db.get(VideoRecording, state.video_id)
            if record:
                record.status = "FAILED" if state.failed else "COMPLETED"
                record.video_end_server_time = ended_at
                record.duration_ms = duration_ms
                record.frame_count = state.frame_count
                record.dropped_frame_estimate = state.dropped_frame_estimate
                db.commit()

            return {
                "status": "failed" if state.failed else "completed",
                "session_id": session_id,
                "video_id": state.video_id,
                "file_path": str(state.file_path),
                "sidecar_path": str(state.sidecar_path),
            }
        except Exception as exc:
            logger.exception("Failed stopping webcam recording for session %s", session_id)
            if suppress_errors:
                return {
                    "status": "failed",
                    "session_id": session_id,
                    "error": str(exc),
                }
            raise RuntimeError(f"video recorder stop failed: {exc}") from exc

    def close_all(self) -> None:
        with self._lock:
            states = list(self._active.values())
            self._active.clear()

        for state in states:
            try:
                state.stop_event.set()
                state.thread.join(timeout=2.0)
                state.capture.release()
                state.writer.release()
            except Exception:
                logger.exception("Failed during close_all for session %s", state.session_id)

    def get_runtime_status(self, db: Session, session_id: str) -> dict[str, Any]:
        with self._lock:
            state = self._active.get(session_id)
            if state:
                elapsed_ms = int((time.monotonic() - state.started_monotonic) * 1000)
                return {
                    "status": "recording",
                    "session_id": session_id,
                    "video_id": state.video_id,
                    "camera_id": state.camera_id,
                    "file_path": str(state.file_path),
                    "elapsed_ms": elapsed_ms,
                    "frame_count": state.frame_count,
                    "dropped_frame_estimate": state.dropped_frame_estimate,
                }

        existing = (
            db.query(VideoRecording)
            .filter(VideoRecording.session_id == session_id)
            .order_by(VideoRecording.video_start_server_time.desc())
            .first()
        )
        if not existing:
            return {
                "status": "idle",
                "session_id": session_id,
            }

        return {
            "status": existing.status.lower(),
            "session_id": session_id,
            "video_id": existing.video_id,
            "camera_id": existing.camera_id,
            "file_path": existing.file_path,
            "elapsed_ms": existing.duration_ms or 0,
            "frame_count": existing.frame_count or 0,
            "dropped_frame_estimate": existing.dropped_frame_estimate or 0,
        }

    def _record_loop(self, session_id: str) -> None:
        settings = self._settings
        frame_interval = 1.0 / max(settings.webcam_target_fps, 1.0)

        with self._lock:
            state = self._active.get(session_id)
        if state is None:
            return

        while not state.stop_event.is_set():
            ok, frame = state.capture.read()
            if not ok:
                state.dropped_frame_estimate += 1
                state.failed = True
                state.error_message = "failed to read frame"
                time.sleep(0.02)
                continue

            state.writer.write(frame)
            state.frame_count += 1
            time.sleep(frame_interval)

    @staticmethod
    def _upsert_video_record(db: Session, state: RecordingState, status: str) -> None:
        record = db.get(VideoRecording, state.video_id)
        if not record:
            record = VideoRecording(
                video_id=state.video_id,
                session_id=state.session_id,
                camera_id=state.camera_id,
                file_path=str(state.file_path),
                status=status,
                video_start_server_time=state.started_at,
            )
            db.add(record)
        else:
            record.camera_id = state.camera_id
            record.file_path = str(state.file_path)
            record.status = status
            record.video_start_server_time = state.started_at
        db.commit()

    @staticmethod
    def _upsert_failed_record(
        db: Session,
        session_id: str,
        video_id: str,
        camera_id: str,
        file_path: Path,
        reason: str,
    ) -> None:
        record = db.get(VideoRecording, video_id)
        started_at = datetime.now(UTC).replace(tzinfo=None)
        if not record:
            record = VideoRecording(
                video_id=video_id,
                session_id=session_id,
                camera_id=camera_id,
                file_path=str(file_path),
                status="FAILED",
                video_start_server_time=started_at,
                video_end_server_time=started_at,
                duration_ms=0,
                frame_count=0,
                dropped_frame_estimate=0,
            )
            db.add(record)
        else:
            record.status = "FAILED"
            record.video_end_server_time = started_at
        db.commit()

    @staticmethod
    def _status_payload(state: RecordingState, status: str) -> dict[str, Any]:
        return {
            "status": status,
            "session_id": state.session_id,
            "video_id": state.video_id,
            "camera_id": state.camera_id,
            "file_path": str(state.file_path),
            "fps": round(state.fps, 2),
            "width": state.width,
            "height": state.height,
        }


video_recorder_service = VideoRecorderService()
