from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.models import Annotation, Session as SessionModel, SessionDevice, VideoRecording


@dataclass
class SessionCompleteness:
    complete: bool
    checks: dict[str, bool]
    detail: dict[str, object]


def _sensor_summary_files(session_id: str) -> list[Path]:
    sensor_dir = get_settings().data_root / "sessions" / session_id / "sensor"
    if not sensor_dir.exists():
        return []
    return sorted(sensor_dir.glob("*.summary.json"))


def _load_summary_by_device(session_id: str) -> dict[str, dict[str, object]]:
    result: dict[str, dict[str, object]] = {}
    for file_path in _sensor_summary_files(session_id):
        try:
            payload = json.loads(file_path.read_text(encoding="utf-8"))
        except Exception:
            continue
        device_id = str(payload.get("device_id", "")).strip()
        if not device_id:
            continue
        result[device_id] = payload
    return result


def _max_missing_gap_size(ranges: list[object]) -> int:
    largest = 0
    for item in ranges:
        if not isinstance(item, list) or len(item) != 2:
            continue
        try:
            start = int(item[0])
            end = int(item[1])
        except Exception:
            continue
        if end < start:
            continue
        largest = max(largest, (end - start) + 1)
    return largest


def evaluate_session_completeness(db: Session, session_id: str) -> SessionCompleteness:
    settings = get_settings()
    summary_by_device = _load_summary_by_device(session_id)

    required_mappings = (
        db.query(SessionDevice)
        .filter(SessionDevice.session_id == session_id, SessionDevice.required.is_(True))
        .order_by(SessionDevice.device_id.asc())
        .all()
    )
    required_device_ids = [item.device_id for item in required_mappings]

    missing_required_devices: list[str] = []
    low_sample_devices: list[dict[str, object]] = []
    large_gap_devices: list[dict[str, object]] = []

    for device_id in required_device_ids:
        payload = summary_by_device.get(device_id)
        if payload is None:
            missing_required_devices.append(device_id)
            continue

        sample_count = int(payload.get("sample_count", 0) or 0)
        if sample_count < settings.session_finalize_min_samples_per_required_device:
            low_sample_devices.append(
                {
                    "device_id": device_id,
                    "sample_count": sample_count,
                    "min_required": settings.session_finalize_min_samples_per_required_device,
                }
            )

        ranges = payload.get("missing_seq_ranges")
        if isinstance(ranges, list):
            largest_gap = _max_missing_gap_size(ranges)
            if largest_gap > settings.session_finalize_max_missing_gap_size:
                large_gap_devices.append(
                    {
                        "device_id": device_id,
                        "largest_gap": largest_gap,
                        "max_allowed": settings.session_finalize_max_missing_gap_size,
                    }
                )

    video_rows = (
        db.query(VideoRecording)
        .filter(VideoRecording.session_id == session_id)
        .order_by(VideoRecording.video_start_server_time.desc())
        .all()
    )
    video_valid = True
    video_detail: dict[str, object] = {}
    if settings.session_finalize_require_video:
        completed = [row for row in video_rows if row.status == "COMPLETED"]
        if not completed:
            video_valid = False
            video_detail = {"reason": "no_completed_video_record"}
        else:
            candidate = completed[0]
            video_path = Path(candidate.file_path)
            if (not video_path.exists()) or video_path.stat().st_size <= 0:
                video_valid = False
                video_detail = {
                    "reason": "video_file_invalid",
                    "file_path": str(video_path),
                }
            else:
                video_detail = {
                    "file_path": str(video_path),
                    "size_bytes": video_path.stat().st_size,
                }

    open_annotations = (
        db.query(Annotation)
        .filter(
            Annotation.session_id == session_id,
            Annotation.deleted.is_(False),
            Annotation.ended_at.is_(None),
        )
        .order_by(Annotation.annotation_id.asc())
        .all()
    )

    checks = {
        "required_devices_have_data": len(missing_required_devices) == 0,
        "sample_count_reasonable": len(low_sample_devices) == 0,
        "no_large_missing_gap": len(large_gap_devices) == 0,
        "video_file_valid": video_valid,
        "annotations_complete": len(open_annotations) == 0,
    }

    detail: dict[str, object] = {
        "required_device_ids": required_device_ids,
        "missing_required_devices": missing_required_devices,
        "low_sample_devices": low_sample_devices,
        "large_gap_devices": large_gap_devices,
        "open_annotations": [item.annotation_id for item in open_annotations],
        "video": video_detail,
        "summary_devices_found": sorted(summary_by_device.keys()),
    }

    return SessionCompleteness(
        complete=all(checks.values()),
        checks=checks,
        detail=detail,
    )


def write_completeness_report(session_id: str, report: SessionCompleteness) -> Path:
    root = get_settings().data_root / "sessions" / session_id
    root.mkdir(parents=True, exist_ok=True)
    path = root / "completeness_report.json"
    payload = {
        "session_id": session_id,
        "complete": bool(report.complete),
        "checks": report.checks,
        "detail": report.detail,
    }
    partial_path = path.with_name(f"{path.name}.partial")
    partial_path.write_text(json.dumps(payload, ensure_ascii=True, indent=2), encoding="utf-8")
    partial_path.replace(path)
    return path
