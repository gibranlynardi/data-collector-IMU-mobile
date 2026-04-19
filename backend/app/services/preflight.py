from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.db.models import PreflightCheck


def is_preflight_passed(report: dict) -> bool:
    return bool(
        report.get("backend_healthy")
        and report.get("storage_path_writable")
        and report.get("webcam_available")
    )


def store_preflight_report(db: Session, report: dict, session_id: str | None = None) -> None:
    check_items = [
        ("backend_healthy", bool(report.get("backend_healthy", False)), "FastAPI app startup check"),
        (
            "storage_path_writable",
            bool(report.get("storage_path_writable", False)),
            f"free_bytes={report.get('storage_free_bytes', 0)}",
        ),
        (
            "webcam_connected",
            bool(report.get("webcam_connected", False)),
            str(report.get("webcam_detail", "")),
        ),
        (
            "webcam_preview_ok",
            bool(report.get("webcam_preview_ok", False)),
            str(report.get("webcam_detail", "")),
        ),
        (
            "webcam_fps_ok",
            bool(report.get("webcam_fps_ok", False)),
            f"fps={report.get('webcam_fps', 0.0)}",
        ),
        (
            "webcam_storage_ok",
            bool(report.get("webcam_storage_ok", False)),
            f"free_bytes={report.get('storage_free_bytes', 0)}",
        ),
        ("webcam_available", bool(report.get("webcam_available", False)), str(report.get("webcam_detail", ""))),
    ]

    for name, passed, details in check_items:
        db.add(
            PreflightCheck(
                session_id=session_id,
                check_name=name,
                passed=passed,
                details=details,
                measured_at=datetime.now(UTC).replace(tzinfo=None),
            )
        )

    db.commit()
