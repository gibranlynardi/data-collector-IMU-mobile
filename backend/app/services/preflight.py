from datetime import UTC, datetime
import json
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.models import PreflightCheck


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    partial_path = path.with_name(f"{path.name}.partial")
    partial_path.write_text(json.dumps(payload, ensure_ascii=True, indent=2), encoding="utf-8")
    partial_path.replace(path)


def preflight_report_path(session_id: str) -> Path:
    settings = get_settings()
    return settings.data_root / "sessions" / session_id / "preflight_report.json"


def write_preflight_report_file(session_id: str, payload: dict[str, Any]) -> Path:
    path = preflight_report_path(session_id)
    _atomic_write_json(path, payload)
    return path


def _legacy_check_items(report: dict[str, Any]) -> list[tuple[str, bool, str]]:
    return [
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


def store_preflight_checks(
    db: Session,
    check_items: list[tuple[str, bool, str]],
    *,
    session_id: str | None = None,
    measured_at: datetime | None = None,
) -> None:
    measured = measured_at or datetime.now(UTC).replace(tzinfo=None)
    for name, passed, details in check_items:
        db.add(
            PreflightCheck(
                session_id=session_id,
                check_name=name,
                passed=passed,
                details=details,
                measured_at=measured,
            )
        )

    db.commit()


def store_preflight_overall(
    db: Session,
    *,
    session_id: str,
    passed: bool,
    details: dict[str, Any],
    measured_at: datetime | None = None,
) -> None:
    measured = measured_at or datetime.now(UTC).replace(tzinfo=None)
    db.add(
        PreflightCheck(
            session_id=session_id,
            check_name="preflight_overall",
            passed=bool(passed),
            details=json.dumps(details, ensure_ascii=True),
            measured_at=measured,
        )
    )
    db.commit()


def is_preflight_passed(report: dict) -> bool:
    if "overall_passed" in report:
        return bool(report.get("overall_passed"))
    return bool(
        report.get("backend_healthy")
        and report.get("storage_path_writable")
        and report.get("webcam_available")
    )


def store_preflight_report(db: Session, report: dict, session_id: str | None = None) -> None:
    check_items = report.get("check_items")
    if isinstance(check_items, list):
        normalized: list[tuple[str, bool, str]] = []
        for item in check_items:
            if not isinstance(item, dict):
                continue
            normalized.append(
                (
                    str(item.get("check_name", "")),
                    bool(item.get("passed", False)),
                    str(item.get("details", "")),
                )
            )
        if normalized:
            store_preflight_checks(db, normalized, session_id=session_id)
            return

    store_preflight_checks(db, _legacy_check_items(report), session_id=session_id)
