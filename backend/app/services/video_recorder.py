from __future__ import annotations

import json
import logging
import subprocess
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
from app.db.session import SessionLocal

logger = logging.getLogger(__name__)


@dataclass
class RecordingState:
    session_id: str
    video_id: str
    camera_id: str
    file_path: Path
    sidecar_path: Path
    stop_event: threading.Event
    thread: threading.Thread | None
    capture: Any | None
    writer: Any | None
    ffmpeg_process: subprocess.Popen | None
    backend: str
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
    failure_notified: bool = False


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

    def run_test_mode(self, duration_seconds: int = 10) -> dict[str, Any]:
        settings = self._settings
        duration_seconds = max(1, int(duration_seconds))
        source = settings.webcam_path if settings.webcam_path else settings.webcam_index
        test_dir = settings.data_root / "webcam_test"
        test_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
        file_path = test_dir / f"webcam_test_{timestamp}.mp4"

        cv2 = self._import_cv2()
        cap = cv2.VideoCapture(source)
        if not cap.isOpened():
            return {
                "status": "failed",
                "reason": "camera_unavailable",
                "file_path": str(file_path),
                "frame_count": 0,
                "valid_mp4": False,
            }

        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or settings.webcam_target_width)
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or settings.webcam_target_height)
        fps = float(cap.get(cv2.CAP_PROP_FPS) or 0.0)
        if fps <= 1.0:
            fps = settings.webcam_target_fps

        fourcc = cv2.VideoWriter_fourcc(*settings.webcam_codec)
        writer = cv2.VideoWriter(str(file_path), fourcc, fps, (width, height))

        frame_count = 0
        started = time.monotonic()
        try:
            while time.monotonic() - started < duration_seconds:
                ok, frame = cap.read()
                if not ok:
                    break
                writer.write(frame)
                frame_count += 1
        finally:
            with suppress(Exception):
                writer.release()
            with suppress(Exception):
                cap.release()

        valid_mp4 = file_path.exists() and file_path.stat().st_size > 0 and frame_count > 0
        return {
            "status": "completed" if valid_mp4 else "failed",
            "file_path": str(file_path),
            "duration_seconds": duration_seconds,
            "fps": round(fps, 2),
            "frame_count": frame_count,
            "valid_mp4": bool(valid_mp4),
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
                state = self._start_opencv_recording(session_id, video_id, camera_id, file_path, sidecar_path)
                self._upsert_video_record(db, state, status="RECORDING")
                self._active[session_id] = state
                if state.thread is not None:
                    state.thread.start()
                return self._status_payload(state, status="recording")
            except Exception as cv_exc:
                logger.exception("OpenCV recorder failed for session %s, trying FFmpeg fallback", session_id)
                try:
                    state = self._start_ffmpeg_recording(session_id, video_id, camera_id, file_path, sidecar_path)
                    self._upsert_video_record(db, state, status="RECORDING")
                    self._active[session_id] = state
                    if state.thread is not None:
                        state.thread.start()
                    return self._status_payload(state, status="recording")
                except Exception as ff_exc:
                    logger.exception("FFmpeg fallback failed for session %s", session_id)
                    error_detail = f"opencv={cv_exc}; ffmpeg={ff_exc}"
                    if not allow_override:
                        raise RuntimeError(f"video recorder start failed: {error_detail}") from ff_exc
                    self._upsert_failed_record(db, session_id, video_id, camera_id, file_path, error_detail)
                    return {
                        "status": "failed",
                        "session_id": session_id,
                        "video_id": video_id,
                        "error": error_detail,
                    }

    def stop_session_recording(self, db: Session, session_id: str, suppress_errors: bool = False) -> dict[str, Any]:
        with self._lock:
            state = self._active.pop(session_id, None)

        if state is None:
            return self._db_status_payload(db, session_id)

        try:
            self._stop_active_state(state, join_timeout=5.0)

            ended_at = datetime.now(UTC).replace(tzinfo=None)
            start_monotonic_ms = int(state.started_monotonic * 1000)
            end_monotonic_ms = int(time.monotonic() * 1000)
            duration_ms = max(0, end_monotonic_ms - start_monotonic_ms)
            sidecar = {
                "session_id": session_id,
                "camera_id": state.camera_id,
                "fps": round(state.fps, 2),
                "width": state.width,
                "height": state.height,
                "codec": state.codec,
                "video_start_server_time": state.started_at.isoformat(),
                "video_start_monotonic_ms": start_monotonic_ms,
                "video_end_server_time": ended_at.isoformat(),
                "video_end_monotonic_ms": end_monotonic_ms,
                "duration_ms": duration_ms,
                "frame_count": state.frame_count,
                "dropped_frame_estimate": state.dropped_frame_estimate,
                "file_path": str(state.file_path),
                "status": "FAILED" if state.failed else "COMPLETED",
                "error": state.error_message,
                "backend": state.backend,
            }
            state.sidecar_path.write_text(json.dumps(sidecar, ensure_ascii=True, indent=2), encoding="utf-8")

            record = db.get(VideoRecording, state.video_id)
            if record:
                record.status = "FAILED" if state.failed else "COMPLETED"
                record.video_end_server_time = ended_at
                record.video_start_monotonic_ms = start_monotonic_ms
                record.video_end_monotonic_ms = end_monotonic_ms
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
                "backend": state.backend,
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
            active_session_ids = list(self._active.keys())

        for session_id in active_session_ids:
            try:
                with SessionLocal() as db:
                    self.stop_session_recording(db, session_id, suppress_errors=True)
            except Exception:
                logger.exception("Failed during close_all for session %s", session_id)

    def collect_runtime_metrics(self) -> dict[str, float]:
        with self._lock:
            now = time.monotonic()
            payload: dict[str, float] = {}
            for session_id, state in self._active.items():
                elapsed = max(0.001, now - state.started_monotonic)
                payload[session_id] = round(state.frame_count / elapsed, 3)
            return payload

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
                    "backend": state.backend,
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
            "backend": "unknown",
        }

    def anonymize_session_video(self, session_id: str) -> dict[str, Any]:
        settings = self._settings
        source_path, sidecar_path = self._resolve_video_paths(session_id)
        output_path = source_path.with_name(f"{session_id}_webcam_anon.mp4")
        metadata_path = source_path.with_name(f"{session_id}_webcam_anon.json")

        self._validate_anonymize_preconditions(settings, source_path)
        command = self._build_deface_command(settings, source_path, output_path)
        completed = subprocess.run(command, check=False, capture_output=True, text=True)
        if completed.returncode != 0:
            stderr = (completed.stderr or "").strip()
            stdout = (completed.stdout or "").strip()
            detail = stderr or stdout or "unknown deface error"
            raise RuntimeError(f"deface failed: {detail}")

        if not output_path.exists():
            raise RuntimeError(f"deface completed but output not found: {output_path}")

        frame_count = 0
        faces_blurred = 0

        report = {
            "session_id": session_id,
            "status": "completed",
            "source_file_path": str(source_path),
            "output_file_path": str(output_path),
            "metadata_file_path": str(metadata_path),
            "frame_count": frame_count,
            "faces_blurred": faces_blurred,
            "created_at": datetime.now(UTC).replace(tzinfo=None).isoformat(),
        }
        metadata_path.write_text(json.dumps(report, ensure_ascii=True, indent=2), encoding="utf-8")

        if sidecar_path.exists():
            self._update_anonymized_sidecar(session_id, sidecar_path, output_path, metadata_path, faces_blurred)

        return report

    @staticmethod
    def _validate_anonymize_preconditions(settings: Any, source_path: Path) -> None:
        if not settings.video_deface_enabled:
            raise RuntimeError("video deface is disabled")
        if not source_path.exists():
            raise FileNotFoundError(f"source video not found: {source_path}")

    @staticmethod
    def _build_deface_command(settings: Any, source_path: Path, output_path: Path) -> list[str]:
        command = [
            settings.video_deface_executable,
            str(source_path),
            "--output",
            str(output_path),
            "--replacewith",
            settings.video_deface_replacewith,
            "--disable-progress-output",
        ]
        if settings.video_deface_keep_audio:
            command.append("--keep-audio")
        if settings.video_deface_backend and settings.video_deface_backend != "auto":
            command.extend(["--backend", settings.video_deface_backend])
        return command

    @staticmethod
    def _update_anonymized_sidecar(
        session_id: str,
        sidecar_path: Path,
        output_path: Path,
        metadata_path: Path,
        faces_blurred: int,
    ) -> None:
        try:
            sidecar_payload = json.loads(sidecar_path.read_text(encoding="utf-8"))
            sidecar_payload["anonymized_file_path"] = str(output_path)
            sidecar_payload["anonymized_metadata_path"] = str(metadata_path)
            sidecar_payload["anonymized_faces_blurred"] = faces_blurred
            sidecar_path.write_text(json.dumps(sidecar_payload, ensure_ascii=True, indent=2), encoding="utf-8")
        except Exception:
            logger.exception("Failed updating sidecar with anonymized metadata for session %s", session_id)

    def _resolve_video_paths(self, session_id: str) -> tuple[Path, Path]:
        session_root = self._settings.data_root / "sessions" / session_id / "video"
        return (
            session_root / f"{session_id}_webcam.mp4",
            session_root / f"{session_id}_webcam.json",
        )

    def _start_opencv_recording(
        self,
        session_id: str,
        video_id: str,
        camera_id: str,
        file_path: Path,
        sidecar_path: Path,
    ) -> RecordingState:
        settings = self._settings
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
            ffmpeg_process=None,
            backend="opencv",
            started_at=started_at,
            started_monotonic=time.monotonic(),
            fps=fps,
            width=width,
            height=height,
            codec=codec,
        )
        writer.write(first_frame)
        state.frame_count = 1
        return state

    def _start_ffmpeg_recording(
        self,
        session_id: str,
        video_id: str,
        camera_id: str,
        file_path: Path,
        sidecar_path: Path,
    ) -> RecordingState:
        settings = self._settings
        if not settings.ffmpeg_fallback_enabled:
            raise RuntimeError("ffmpeg fallback disabled")

        input_value = settings.ffmpeg_camera_input
        if not input_value:
            if settings.webcam_path:
                input_value = str(settings.webcam_path)
            else:
                raise RuntimeError("FFMPEG_CAMERA_INPUT required for webcam index fallback")

        cmd = [
            settings.ffmpeg_executable,
            "-y",
            "-f",
            settings.ffmpeg_camera_format,
            "-i",
            input_value,
            "-r",
            str(settings.webcam_target_fps),
            "-vcodec",
            "libx264",
            str(file_path),
        ]
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

        started_at = datetime.now(UTC).replace(tzinfo=None)
        return RecordingState(
            session_id=session_id,
            video_id=video_id,
            camera_id=camera_id,
            file_path=file_path,
            sidecar_path=sidecar_path,
            stop_event=threading.Event(),
            thread=threading.Thread(target=self._monitor_ffmpeg_loop, args=(session_id,), name=f"video-ffmpeg-mon-{session_id}", daemon=True),
            capture=None,
            writer=None,
            ffmpeg_process=process,
            backend="ffmpeg",
            started_at=started_at,
            started_monotonic=time.monotonic(),
            fps=settings.webcam_target_fps,
            width=settings.webcam_target_width,
            height=settings.webcam_target_height,
            codec="h264",
        )

    @staticmethod
    def _stop_ffmpeg_process(process: subprocess.Popen) -> None:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=5.0)
            except Exception:
                process.kill()

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
                self._mark_recording_failed(state, "failed to read frame")
                time.sleep(0.02)
                continue

            state.writer.write(frame)
            state.frame_count += 1
            time.sleep(frame_interval)

    def _monitor_ffmpeg_loop(self, session_id: str) -> None:
        with self._lock:
            state = self._active.get(session_id)
        if state is None:
            return

        while not state.stop_event.is_set():
            process = state.ffmpeg_process
            if process is None:
                return
            code = process.poll()
            if code is None:
                time.sleep(0.2)
                continue

            self._mark_recording_failed(state, f"ffmpeg exited unexpectedly with code {code}")
            return

    @staticmethod
    def _mark_recording_failed(state: RecordingState, reason: str) -> None:
        state.failed = True
        state.error_message = reason
        if state.failure_notified:
            return
        state.failure_notified = True

        try:
            from app.services.ws_runtime import ws_runtime

            ws_runtime.publish_session_event_sync(
                state.session_id,
                {
                    "type": "VIDEO_RECORDER_STATUS",
                    "session_id": state.session_id,
                    "status": "failed",
                    "backend": state.backend,
                    "error": reason,
                    "dropped_frame_estimate": state.dropped_frame_estimate,
                },
            )
            ws_runtime.publish_warning_sync(
                state.session_id,
                device_id="webcam",
                warning=f"video recorder failed: {reason}",
            )
        except Exception:
            logger.exception("Failed pushing recorder failure event for session %s", state.session_id)

    @staticmethod
    def _db_status_payload(db: Session, session_id: str) -> dict[str, Any]:
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

    def _stop_active_state(self, state: RecordingState, join_timeout: float) -> None:
        state.stop_event.set()
        if state.backend == "opencv":
            if state.thread is not None:
                state.thread.join(timeout=join_timeout)
            if state.capture is not None:
                state.capture.release()
            if state.writer is not None:
                state.writer.release()
            return

        if state.backend == "ffmpeg" and state.ffmpeg_process is not None:
            self._stop_ffmpeg_process(state.ffmpeg_process)
            if state.thread is not None:
                state.thread.join(timeout=join_timeout)

    @staticmethod
    def _upsert_video_record(db: Session, state: RecordingState, status: str) -> None:
        record = db.get(VideoRecording, state.video_id)
        start_monotonic_ms = int(state.started_monotonic * 1000)
        if not record:
            record = VideoRecording(
                video_id=state.video_id,
                session_id=state.session_id,
                camera_id=state.camera_id,
                file_path=str(state.file_path),
                status=status,
                video_start_server_time=state.started_at,
                video_start_monotonic_ms=start_monotonic_ms,
            )
            db.add(record)
        else:
            record.camera_id = state.camera_id
            record.file_path = str(state.file_path)
            record.status = status
            record.video_start_server_time = state.started_at
            record.video_start_monotonic_ms = start_monotonic_ms
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
                video_start_monotonic_ms=int(time.monotonic() * 1000),
                video_end_server_time=started_at,
                video_end_monotonic_ms=int(time.monotonic() * 1000),
                duration_ms=0,
                frame_count=0,
                dropped_frame_estimate=0,
            )
            db.add(record)
        else:
            record.status = "FAILED"
            record.video_end_server_time = started_at
            record.video_end_monotonic_ms = int(time.monotonic() * 1000)
        db.commit()

    @staticmethod
    def _status_payload(state: RecordingState, status: str) -> dict[str, Any]:
        return {
            "status": status,
            "session_id": state.session_id,
            "video_id": state.video_id,
            "camera_id": state.camera_id,
            "file_path": str(state.file_path),
            "backend": state.backend,
            "fps": round(state.fps, 2),
            "width": state.width,
            "height": state.height,
        }


video_recorder_service = VideoRecorderService()
