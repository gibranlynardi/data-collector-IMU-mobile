import logging
from dataclasses import asdict, dataclass
from pathlib import Path

from app.core.config import get_settings
from app.db.session import dispose_engine


@dataclass
class PreflightReport:
    backend_healthy: bool
    storage_path_writable: bool
    storage_free_bytes: int
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


def _check_webcam(index: int) -> tuple[bool, str]:
    try:
        import cv2  # type: ignore

        cap = cv2.VideoCapture(index)
        if not cap.isOpened():
            return False, f"camera index {index} cannot be opened"
        ok, _ = cap.read()
        cap.release()
        if not ok:
            return False, f"camera index {index} opened but no frame"
        return True, f"camera index {index} ready"
    except Exception as exc:
        return False, f"opencv unavailable or camera check failed: {exc}"


def run_startup_checks() -> dict:
    settings = get_settings()
    storage_ok, free_bytes = _check_storage(settings.data_root)
    webcam_ok, webcam_detail = _check_webcam(settings.webcam_index)

    report = PreflightReport(
        backend_healthy=True,
        storage_path_writable=storage_ok,
        storage_free_bytes=free_bytes,
        webcam_available=webcam_ok,
        webcam_detail=webcam_detail,
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
