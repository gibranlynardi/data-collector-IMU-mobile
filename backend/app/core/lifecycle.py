import logging
from dataclasses import asdict, dataclass
from pathlib import Path

from app.core.config import get_settings
from app.db.session import dispose_engine
from app.services.video_recorder import video_recorder_service


@dataclass
class PreflightReport:
    backend_healthy: bool
    storage_path_writable: bool
    storage_free_bytes: int
    webcam_connected: bool
    webcam_preview_ok: bool
    webcam_fps: float
    webcam_fps_ok: bool
    webcam_storage_ok: bool
    webcam_available: bool
    webcam_detail: str


logger = logging.getLogger(__name__)


def _check_storage(path: Path) -> tuple[bool, int]:
    try:
        path.mkdir(parents=True, exist_ok=True)
        test_file = path / ".write_test"
        test_file.write_text("ok", encoding="utf-8")
        test_file.unlink(missing_ok=True)
        free_bytes = 0
        try:
            import shutil

            free_bytes = shutil.disk_usage(path).free
        except Exception:
            free_bytes = 0
        return True, free_bytes
    except Exception:
        return False, 0


def run_startup_checks() -> dict:
    settings = get_settings()
    storage_ok, free_bytes = _check_storage(settings.data_root)
    webcam_report = video_recorder_service.inspect_webcam()
    webcam_storage_ok = storage_ok and free_bytes >= settings.webcam_min_free_bytes
    webcam_ok = bool(
        webcam_report.get("webcam_connected")
        and webcam_report.get("webcam_preview_ok")
        and webcam_report.get("webcam_fps_ok")
        and webcam_storage_ok
    )

    report = PreflightReport(
        backend_healthy=True,
        storage_path_writable=storage_ok,
        storage_free_bytes=free_bytes,
        webcam_connected=bool(webcam_report.get("webcam_connected", False)),
        webcam_preview_ok=bool(webcam_report.get("webcam_preview_ok", False)),
        webcam_fps=float(webcam_report.get("webcam_fps", 0.0) or 0.0),
        webcam_fps_ok=bool(webcam_report.get("webcam_fps_ok", False)),
        webcam_storage_ok=webcam_storage_ok,
        webcam_available=webcam_ok,
        webcam_detail=str(webcam_report.get("webcam_detail", "")),
    )
    return asdict(report)


def run_shutdown_tasks() -> dict:
    report = {
        "success": True,
        "steps": [],
    }

    def _record_step(name: str, status: str, detail: str = "") -> None:
        report["steps"].append({"name": name, "status": status, "detail": detail})

    try:
        dispose_engine()
        _record_step("dispose_db_engine", "ok")
    except Exception as exc:
        report["success"] = False
        _record_step("dispose_db_engine", "error", str(exc))
        logger.exception("Failed during graceful shutdown step: dispose_db_engine")

    return report
