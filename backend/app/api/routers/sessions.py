from datetime import UTC, datetime
import json
import logging
import time
from pathlib import Path as FsPath
from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.auth import get_request_actor, require_operator_access
from app.core.lifecycle import run_startup_checks
from app.core.session_manager import SessionStateError, session_manager
from app.db.models import Annotation, Device, DeviceSamplingTelemetry, PreflightCheck, Session as SessionModel, SessionDevice, VideoRecording
from app.db.session import get_db
from app.schemas.sessions import (
    SessionSamplingQualityHistoryResponse,
    SessionCreateRequest,
    SessionDeviceAssignmentResponse,
    SessionDeviceAssignRequest,
    SessionDeviceBindingResponse,
    SessionFinalizeRequest,
    SessionResponse,
    SessionStatusResponse,
)
from app.schemas.video import VideoAnonymizeResponse, VideoMetadataResponse, VideoStatusResponse
from app.services.artifacts import ensure_session_layout, finalize_session_artifacts, materialize_session_storage, seed_session_artifacts
from app.services.clock_sync import clock_sync_service
from app.services.csv_writer import csv_writer_service
from app.services.preflight import (
    is_preflight_passed,
    store_preflight_checks,
    store_preflight_overall,
    store_preflight_report,
    write_preflight_report_file,
)
from app.services.session_finalization import SessionCompleteness, evaluate_session_completeness, write_completeness_report
from app.services.annotation_audit import write_annotation_audit
from app.services.video_recorder import video_recorder_service
from app.services.ws_runtime import ws_runtime
from app.services.operator_audit import write_operator_action_audit

router = APIRouter(prefix="/sessions", tags=["sessions"], dependencies=[Depends(require_operator_access)])
logger = logging.getLogger(__name__)
DBSession = Annotated[Session, Depends(get_db)]
SESSION_ID_PATTERN = r"^\d{8}_\d{6}_[A-F0-9]{8}$"
SESSION_RESPONSES_404 = {404: {"description": "Session not found"}}
SESSION_RESPONSES_409 = {409: {"description": "Invalid session state transition"}}
SESSION_RESPONSES_400 = {400: {"description": "Bad request"}}
SESSION_NOT_FOUND = "session not found"


def _generate_session_id() -> str:
    timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    suffix = uuid4().hex[:8].upper()
    return f"{timestamp}_{suffix}"


def _sidecar_path_for_session(session_id: str):
    settings = get_settings()
    return settings.data_root / "sessions" / session_id / "video" / f"{session_id}_webcam.json"


def _audit_operator_action(
    db: Session,
    request: Request,
    *,
    action: str,
    session_id: str | None = None,
    target_type: str | None = None,
    target_id: str | None = None,
    details: dict[str, object] | None = None,
) -> None:
    operator_id, operator_type = get_request_actor(request)
    write_operator_action_audit(
        db,
        operator_id=operator_id or "operator",
        operator_type=operator_type or "operator",
        action=action,
        session_id=session_id,
        target_type=target_type,
        target_id=target_id,
        details=details or {},
    )
    db.commit()


def _rollback_start_failure(db: Session, session_id: str) -> None:
    session = db.get(SessionModel, session_id)
    if session and session.status == "RUNNING":
        session.status = "CREATED"
        session.started_at = None
        db.commit()


def _cleanup_failed_start(db: Session, session_id: str, *, video_started: bool, session_started: bool) -> None:
    if not (video_started or session_started):
        return

    try:
        csv_writer_service.close_session(session_id)
    except Exception:
        logger.exception("Failed closing CSV writers during start rollback for session %s", session_id)

    try:
        video_recorder_service.stop_session_recording(db, session_id, suppress_errors=True)
    except Exception:
        logger.exception("Failed stopping recorder during start rollback for session %s", session_id)
    ws_runtime.stop_session_countdown_sync(session_id)
    if session_started:
        _rollback_start_failure(db, session_id)


def _extract_video_start_monotonic_ms(db: Session, session_id: str) -> int | None:
    record = (
        db.query(VideoRecording)
        .filter(VideoRecording.session_id == session_id)
        .order_by(VideoRecording.video_start_server_time.desc())
        .first()
    )
    if record and record.video_start_monotonic_ms is not None:
        return int(record.video_start_monotonic_ms)
    return None


def _clock_sync_has_bad_quality(report: dict[str, object]) -> bool:
    devices = report.get("devices")
    if not isinstance(devices, list) or not devices:
        return True
    if str(report.get("overall_sync_quality", "unknown")) in {"bad", "unknown"}:
        return True
    for item in devices:
        if not isinstance(item, dict):
            continue
        if str(item.get("sync_quality", "")) == "bad":
            return True
    return False


def _check_clock_sync_quality(report: dict[str, object]) -> tuple[bool, str]:
    if _clock_sync_has_bad_quality(report):
        return False, f"overall={report.get('overall_sync_quality', 'unknown')}"
    return True, f"overall={report.get('overall_sync_quality', 'unknown')}"


def _check_required_roles(bindings: list[SessionDeviceBindingResponse]) -> tuple[bool, str, list[str], list[str], list[str]]:
    required_roles = {role.lower() for role in get_settings().required_roles}
    required_bindings = [binding for binding in bindings if binding.required]
    role_counts: dict[str, int] = {}
    for binding in required_bindings:
        role = binding.device_role.lower()
        role_counts[role] = role_counts.get(role, 0) + 1

    assigned_roles = set(role_counts.keys())
    missing_roles = sorted(required_roles - assigned_roles)
    duplicate_roles = sorted([role for role, count in role_counts.items() if count > 1])
    invalid_roles = sorted([role for role in assigned_roles if role not in required_roles])
    passed = not missing_roles and not duplicate_roles and not invalid_roles
    detail = (
        f"missing={','.join(missing_roles) or '-'};"
        f"duplicate={','.join(duplicate_roles) or '-'};"
        f"invalid={','.join(invalid_roles) or '-'}"
    )
    return passed, detail, missing_roles, duplicate_roles, invalid_roles


def _latest_preflight_overall(db: Session, session_id: str) -> PreflightCheck | None:
    return (
        db.query(PreflightCheck)
        .filter(
            PreflightCheck.session_id == session_id,
            PreflightCheck.check_name == "preflight_overall",
        )
        .order_by(PreflightCheck.measured_at.desc(), PreflightCheck.id.desc())
        .first()
    )


def _assert_start_preflight_fresh(db: Session, session: SessionModel) -> tuple[bool, dict[str, object] | None]:
    row = _latest_preflight_overall(db, session.session_id)
    if row is None:
        raise HTTPException(status_code=400, detail="preflight belum pernah dijalankan, panggil POST /sessions/{session_id}/preflight/run")

    now = datetime.now(UTC).replace(tzinfo=None)
    ttl_seconds = max(1, int(get_settings().preflight_report_ttl_seconds))
    age_seconds = max(0.0, (now - row.measured_at).total_seconds())
    if age_seconds > ttl_seconds:
        raise HTTPException(
            status_code=400,
            detail=f"preflight report expired ({age_seconds:.1f}s), jalankan ulang POST /sessions/{session.session_id}/preflight/run",
        )

    details_payload: dict[str, object] | None = None
    if row.details:
        try:
            parsed = json.loads(row.details)
            if isinstance(parsed, dict):
                details_payload = parsed
        except Exception:
            details_payload = None

    if not bool(row.passed):
        raise HTTPException(
            status_code=400,
            detail={
                "message": "preflight belum lulus",
                "preflight": details_payload or {"passed": False},
            },
        )
    return True, details_payload


async def _run_session_preflight(db: Session, session: SessionModel) -> dict[str, object]:
    measured_at = datetime.now(UTC).replace(tzinfo=None)
    measured_at_iso = measured_at.isoformat()
    settings = get_settings()
    check_items: list[tuple[str, bool, str]] = []

    startup_report = run_startup_checks()
    backend_healthy = bool(startup_report.get("backend_healthy", False))
    storage_ok = bool(startup_report.get("storage_path_writable", False))
    webcam_ok = bool(startup_report.get("webcam_available", False))
    webcam_required = bool(settings.webcam_required)
    check_items.extend(
        [
            ("backend_healthy", backend_healthy, "FastAPI app startup check"),
            (
                "storage_path_writable",
                storage_ok,
                f"free_bytes={int(startup_report.get('storage_free_bytes', 0) or 0)}",
            ),
            (
                "webcam_available",
                True if not webcam_required else webcam_ok,
                (str(startup_report.get("webcam_detail", "")) + (" (optional)" if not webcam_required else "")).strip(),
            ),
        ]
    )

    bindings = _load_session_bindings(db, session.session_id)
    required_bindings = [binding for binding in bindings if binding.required]
    required_device_ids = [binding.device_id for binding in required_bindings]

    roles_ok, roles_detail, missing_roles, duplicate_roles, invalid_roles = _check_required_roles(bindings)
    check_items.append(("required_roles_valid", roles_ok, roles_detail))

    devices = (
        db.query(Device)
        .filter(Device.device_id.in_(required_device_ids))
        .all()
        if required_device_ids
        else []
    )
    device_map = {item.device_id: item for item in devices}

    missing_devices = sorted([device_id for device_id in required_device_ids if device_id not in device_map])
    devices_present_ok = not missing_devices and bool(required_device_ids)
    check_items.append(
        (
            "required_devices_registered",
            devices_present_ok,
            f"missing_devices={','.join(missing_devices) or '-'}",
        )
    )

    offline_device_ids = sorted(
        [
            device_id
            for device_id in required_device_ids
            if device_id in device_map and not bool(device_map[device_id].connected)
        ]
    )
    devices_online_ok = devices_present_ok and not offline_device_ids
    check_items.append(
        (
            "required_devices_online",
            devices_online_ok,
            f"offline_devices={','.join(offline_device_ids) or '-'}",
        )
    )

    low_battery_ids = sorted(
        [
            device_id
            for device_id in required_device_ids
            if device_id in device_map
            and (
                device_map[device_id].battery_percent is None
                or float(device_map[device_id].battery_percent) <= float(settings.battery_critical_percent)
            )
        ]
    )
    battery_ok = devices_present_ok and not low_battery_ids
    check_items.append(
        (
            "device_battery_ok",
            battery_ok,
            f"threshold={settings.battery_critical_percent};low_or_unknown={','.join(low_battery_ids) or '-'}",
        )
    )

    low_storage_ids = sorted(
        [
            device_id
            for device_id in required_device_ids
            if device_id in device_map
            and (
                device_map[device_id].storage_free_mb is None
                or int(device_map[device_id].storage_free_mb) <= int(settings.device_storage_critical_mb)
            )
        ]
    )
    storage_devices_ok = devices_present_ok and not low_storage_ids
    check_items.append(
        (
            "device_storage_ok",
            storage_devices_ok,
            f"threshold_mb={settings.device_storage_critical_mb};low_or_unknown={','.join(low_storage_ids) or '-'}",
        )
    )

    hz_threshold = float(settings.session_target_sampling_hz) * float(settings.preflight_effective_hz_min_ratio)
    low_hz_ids = sorted(
        [
            device_id
            for device_id in required_device_ids
            if device_id in device_map
            and (
                device_map[device_id].effective_hz is None
                or float(device_map[device_id].effective_hz) < hz_threshold
            )
        ]
    )
    effective_hz_ok = devices_present_ok and not low_hz_ids
    check_items.append(
        (
            "device_effective_hz_ok",
            effective_hz_ok,
            f"threshold_hz={hz_threshold:.2f};low_or_unknown={','.join(low_hz_ids) or '-'}",
        )
    )

    sync_report: dict[str, object] = {
        "session_id": session.session_id,
        "devices": [],
        "overall_sync_quality": "unknown",
        "overall_sync_quality_color": "yellow",
    }
    clock_sync_ok = False
    if devices_online_ok:
        await ws_runtime.bind_devices_to_session(session_id=session.session_id, device_ids=required_device_ids)
        sync_report = await clock_sync_service.run_preflight_sync(
            session_id=session.session_id,
            device_ids=required_device_ids,
        )
        clock_sync_ok, clock_detail = _check_clock_sync_quality(sync_report)
    else:
        clock_detail = "required devices offline"

    check_items.append(("clock_sync_quality_ok", clock_sync_ok, clock_detail))

    overall_passed = all(item[1] for item in check_items)
    run_id = f"{session.session_id}:{measured_at.strftime('%Y%m%d%H%M%S%f')}"
    expires_at = datetime.fromtimestamp(
        measured_at.timestamp() + max(1, int(settings.preflight_report_ttl_seconds)),
        tz=UTC,
    ).replace(tzinfo=None)

    check_items_payload = [
        {
            "check_name": name,
            "passed": passed,
            "details": details,
            "measured_at": measured_at_iso,
        }
        for name, passed, details in check_items
    ]
    report = {
        "session_id": session.session_id,
        "run_id": run_id,
        "measured_at": measured_at_iso,
        "expires_at": expires_at.isoformat(),
        "overall_passed": overall_passed,
        "startup": startup_report,
        "required_device_ids": required_device_ids,
        "check_items": check_items_payload,
        "clock_sync": sync_report,
        "required_roles_detail": {
            "missing": missing_roles,
            "duplicate": duplicate_roles,
            "invalid": invalid_roles,
        },
    }

    store_preflight_checks(
        db,
        [(item["check_name"], bool(item["passed"]), str(item["details"])) for item in check_items_payload],
        session_id=session.session_id,
        measured_at=measured_at,
    )
    store_preflight_overall(
        db,
        session_id=session.session_id,
        passed=overall_passed,
        details=report,
        measured_at=measured_at,
    )

    session.preflight_passed = overall_passed
    db.commit()
    db.refresh(session)

    write_preflight_report_file(session.session_id, report)
    materialize_session_storage(db, session.session_id)
    return report


def _load_session_bindings(db: Session, session_id: str) -> list[SessionDeviceBindingResponse]:
    rows = (
        db.query(SessionDevice, Device)
        .join(Device, SessionDevice.device_id == Device.device_id)
        .filter(SessionDevice.session_id == session_id)
        .order_by(SessionDevice.id.asc())
        .all()
    )
    return [
        SessionDeviceBindingResponse(
            device_id=device.device_id,
            device_role=(device.device_role or "other").lower(),
            required=bool(mapping.required),
            connected=bool(device.connected),
        )
        for mapping, device in rows
    ]


def _validate_required_roles_ready(
    *,
    bindings: list[SessionDeviceBindingResponse],
    online_device_ids: list[str],
    allow_override: bool,
) -> None:
    required_roles = {role.lower() for role in get_settings().required_roles}
    required_bindings = [binding for binding in bindings if binding.required]

    assigned_roles = {binding.device_role.lower() for binding in required_bindings}
    missing_roles = sorted(required_roles - assigned_roles)
    if missing_roles and not allow_override:
        raise HTTPException(
            status_code=400,
            detail=f"required device roles belum di-assign: {', '.join(missing_roles)}",
        )

    online_set = set(online_device_ids)
    offline_required_roles = sorted(
        {
            binding.device_role.lower()
            for binding in required_bindings
            if binding.device_role.lower() in required_roles and binding.device_id not in online_set
        }
    )
    if offline_required_roles and not allow_override:
        raise HTTPException(
            status_code=400,
            detail=f"required device roles belum online: {', '.join(offline_required_roles)}",
        )


def _session_device_ids(db: Session, session_id: str) -> list[str]:
    rows = (
        db.query(SessionDevice.device_id)
        .filter(SessionDevice.session_id == session_id)
        .order_by(SessionDevice.device_id.asc())
        .all()
    )
    return [device_id for (device_id,) in rows]


def _set_session_status(db: Session, session: SessionModel, status: str, *, set_stopped_at: bool = False) -> SessionModel:
    session.status = status
    if set_stopped_at and session.stopped_at is None:
        session.stopped_at = datetime.now(UTC).replace(tzinfo=None)
    db.commit()
    db.refresh(session)
    return session


def _close_session_outputs(db: Session, session_id: str) -> None:
    csv_writer_service.flush_session(session_id)
    csv_writer_service.close_session(session_id)
    video_recorder_service.stop_session_recording(db, session_id, suppress_errors=True)


def _sensor_summary_files(session_id: str) -> list[FsPath]:
    sensor_dir = get_settings().data_root / "sessions" / session_id / "sensor"
    if not sensor_dir.exists():
        return []
    return sorted(sensor_dir.glob("*.summary.json"))


def _completeness_payload(report: SessionCompleteness) -> dict[str, object]:
    return {
        "complete": report.complete,
        "checks": report.checks,
        "detail": report.detail,
    }


def _update_missing_sample_sync_report(session_id: str) -> dict[str, object]:
    missing_payload: list[dict[str, object]] = []
    for summary_path in _sensor_summary_files(session_id):
        try:
            payload = json.loads(summary_path.read_text(encoding="utf-8"))
        except Exception:
            continue

        ranges = payload.get("missing_seq_ranges")
        if not isinstance(ranges, list) or not ranges:
            continue
        missing_payload.append(
            {
                "device_id": str(payload.get("device_id", "")),
                "device_role": str(payload.get("device_role", "other")),
                "missing_seq_ranges": ranges,
                "sample_count": int(payload.get("sample_count", 0) or 0),
                "duplicate_count": int(payload.get("duplicate_count", 0) or 0),
            }
        )

    report = clock_sync_service.read_sync_report(session_id)
    report["missing_ranges_by_device"] = missing_payload
    report["missing_range_device_count"] = len(missing_payload)
    clock_sync_service.write_sync_report(session_id, report)
    return {
        "session_id": session_id,
        "missing_ranges_by_device": missing_payload,
        "missing_range_device_count": len(missing_payload),
    }


def _resolve_assignment_devices(db: Session, assignments: list[object]) -> dict[str, Device]:
    device_ids = [item.device_id for item in assignments]
    existing_devices = db.query(Device).filter(Device.device_id.in_(device_ids)).all()
    existing_map = {device.device_id: device for device in existing_devices}
    missing = sorted({device_id for device_id in device_ids if device_id not in existing_map})
    if missing:
        raise HTTPException(status_code=404, detail=f"device belum terdaftar: {', '.join(missing)}")
    return existing_map


def _annotation_snapshot(annotation: Annotation) -> dict[str, object]:
    return {
        "annotation_id": annotation.annotation_id,
        "session_id": annotation.session_id,
        "label": annotation.label,
        "notes": annotation.notes,
        "started_at": annotation.started_at.isoformat() if annotation.started_at else None,
        "ended_at": annotation.ended_at.isoformat() if annotation.ended_at else None,
        "auto_closed": annotation.auto_closed,
        "deleted": annotation.deleted,
    }


async def _auto_close_active_annotations(db: Session, session_id: str) -> list[str]:
    active = (
        db.query(Annotation)
        .filter(
            Annotation.session_id == session_id,
            Annotation.deleted.is_(False),
            Annotation.ended_at.is_(None),
        )
        .order_by(Annotation.started_at.asc())
        .all()
    )
    if not active:
        return []

    closed_at = datetime.now(UTC).replace(tzinfo=None)
    for annotation in active:
        before = _annotation_snapshot(annotation)
        annotation.ended_at = closed_at
        annotation.auto_closed = True
        write_annotation_audit(
            db,
            "auto_close",
            annotation_id=annotation.annotation_id,
            session_id=annotation.session_id,
            before_payload=before,
            after_payload=_annotation_snapshot(annotation),
        )

    db.commit()

    for annotation in active:
        await ws_runtime.publish_annotation_event(
            session_id,
            {
                "type": "ANNOTATION_EVENT",
                "event": "auto_close",
                "session_id": session_id,
                "annotation_id": annotation.annotation_id,
                "label": annotation.label,
                "ended_at": annotation.ended_at.isoformat() if annotation.ended_at else None,
                "auto_closed": True,
            },
        )

    return [annotation.annotation_id for annotation in active]


def _validate_assignment_constraints(assignments: list[object], existing_map: dict[str, Device]) -> None:
    seen_ids: set[str] = set()
    required_role_map: dict[str, str] = {}
    for item in assignments:
        if item.device_id in seen_ids:
            raise HTTPException(status_code=400, detail=f"device duplicate dalam assignments: {item.device_id}")
        seen_ids.add(item.device_id)

        if not item.required:
            continue
        role = (existing_map[item.device_id].device_role or "other").lower()
        if role in required_role_map:
            raise HTTPException(
                status_code=400,
                detail=f"required role {role} tidak boleh dipetakan ke lebih dari satu device",
            )
        required_role_map[role] = item.device_id


def _upsert_session_assignments(
    db: Session,
    *,
    session_id: str,
    assignments: list[object],
    replace: bool,
) -> None:
    if replace:
        db.query(SessionDevice).filter(SessionDevice.session_id == session_id).delete()

    for item in assignments:
        existing = (
            db.query(SessionDevice)
            .filter(SessionDevice.session_id == session_id, SessionDevice.device_id == item.device_id)
            .first()
        )
        if existing:
            existing.required = item.required
        else:
            db.add(SessionDevice(session_id=session_id, device_id=item.device_id, required=item.required))
    db.commit()


@router.post("", responses={400: {"description": "Preflight failed"}, 409: {"description": "Another session is active"}})
async def create_session(payload: SessionCreateRequest, request: Request, db: DBSession) -> SessionResponse:
    blocking = (
        db.query(SessionModel)
        .filter(SessionModel.status.in_(["ENDING", "SYNCING", "RUNNING", "CREATED"]))
        .order_by(SessionModel.created_at.desc())
        .first()
    )
    if blocking:
        raise HTTPException(status_code=409, detail=f"session {blocking.session_id} masih aktif ({blocking.status})")

    session_id = payload.session_id or _generate_session_id()
    server_report = run_startup_checks()
    if not is_preflight_passed(server_report) and not payload.override_reason:
        raise HTTPException(status_code=400, detail="preflight wajib pass atau isi override_reason")

    session = session_manager.create_session(
        db=db,
        session_id=session_id,
        preflight_passed=is_preflight_passed(server_report),
        override_reason=payload.override_reason,
    )

    session_root = ensure_session_layout(session_id)
    seed_session_artifacts(db, session_id, session_root)

    request.app.state.preflight_report = server_report
    store_preflight_report(db, server_report, session_id=session_id)
    materialize_session_storage(db, session_id)

    await ws_runtime.publish_session_event(
        session_id,
        {
            "type": "SESSION_STATE",
            "session_id": session_id,
            "status": session.status,
        },
    )

    _audit_operator_action(
        db,
        request,
        action="session.create",
        session_id=session_id,
        target_type="session",
        target_id=session_id,
        details={"preflight_passed": bool(session.preflight_passed), "override_reason": session.override_reason or ""},
    )

    return session


@router.post(
    "/{session_id}/preflight/run",
    responses={404: {"description": "Session not found"}, 409: {"description": "Invalid session state transition"}},
)
async def run_session_preflight(
    session_id: Annotated[str, Path(pattern=SESSION_ID_PATTERN)],
    db: DBSession,
    request: Request,
) -> dict[str, object]:
    session = db.get(SessionModel, session_id)
    if not session:
        raise HTTPException(status_code=404, detail=SESSION_NOT_FOUND)
    if session.status != "CREATED":
        raise HTTPException(status_code=409, detail=f"preflight run hanya boleh saat session CREATED, saat ini {session.status}")

    report = await _run_session_preflight(db, session)
    await ws_runtime.publish_session_event(
        session_id,
        {
            "type": "SESSION_PREFLIGHT_RESULT",
            "session_id": session_id,
            "overall_passed": bool(report.get("overall_passed", False)),
            "expires_at": report.get("expires_at"),
            "check_items": report.get("check_items", []),
        },
    )
    _audit_operator_action(
        db,
        request,
        action="session.preflight.run",
        session_id=session_id,
        target_type="session",
        target_id=session_id,
        details={"overall_passed": bool(report.get("overall_passed", False))},
    )
    return report


@router.post("/{session_id}/start", responses={400: {"description": "Preflight failed"}, 404: {"description": "Session not found"}, 409: {"description": "Invalid session state transition"}})
async def start_session(
    session_id: Annotated[str, Path(pattern=SESSION_ID_PATTERN)],
    db: DBSession,
    request: Request,
) -> SessionResponse:
    session = db.get(SessionModel, session_id)
    if not session:
        raise HTTPException(status_code=404, detail=SESSION_NOT_FOUND)

    preflight_ok, _latest_preflight = _assert_start_preflight_fresh(db, session)
    if not preflight_ok and not session.override_reason:
        raise HTTPException(status_code=400, detail="preflight failed; start diblokir")

    session.preflight_passed = bool(preflight_ok)
    db.commit()
    db.refresh(session)

    bindings = _load_session_bindings(db, session_id)
    await ws_runtime.bind_devices_to_session(
        session_id=session_id,
        device_ids=[binding.device_id for binding in bindings],
    )
    online_device_ids = await ws_runtime.get_online_device_ids(session_id)
    _validate_required_roles_ready(
        bindings=bindings,
        online_device_ids=online_device_ids,
        allow_override=bool(session.override_reason),
    )

    sync_candidates = sorted({binding.device_id for binding in bindings})
    if not sync_candidates and not session.override_reason:
        raise HTTPException(
            status_code=400,
            detail="session belum memiliki assignment device, gunakan endpoint assign devices",
        )

    sync_report = await clock_sync_service.run_preflight_sync(session_id=session_id, device_ids=sync_candidates)

    if (
        _clock_sync_has_bad_quality(sync_report)
        and get_settings().clock_sync_block_on_bad
        and not session.override_reason
    ):
        raise HTTPException(
            status_code=400,
            detail="clock sync quality bad; start diblokir kecuali override_reason",
        )

    video_started = False
    session_started = False
    start_lead_ms = max(0, int(get_settings().session_start_lead_ms))
    agreed_server_start_time_unix_ns = time.time_ns() + (start_lead_ms * 1_000_000)
    agreed_session_start_monotonic_ms = int(time.monotonic() * 1000) + start_lead_ms
    agreed_started_at = datetime.fromtimestamp(agreed_server_start_time_unix_ns / 1_000_000_000, tz=UTC).replace(tzinfo=None)
    try:
        video_result = video_recorder_service.start_session_recording(
            db,
            session_id,
            allow_override=bool(session.override_reason),
        )
        video_started = video_result.get("status") == "recording"
        if video_result.get("status") == "failed" and not session.override_reason:
            raise RuntimeError(video_result.get("error") or "video recorder start failed")

        session = session_manager.start_session(db, session_id)
        session_started = True
        session.started_at = agreed_started_at
        db.commit()
        db.refresh(session)
        materialize_session_storage(db, session_id)

        authority = clock_sync_service.mark_session_started(
            session_id,
            session.started_at,
            agreed_server_start_time_unix_ns=agreed_server_start_time_unix_ns,
            agreed_session_start_monotonic_ms=agreed_session_start_monotonic_ms,
        )
        video_start_monotonic_ms = _extract_video_start_monotonic_ms(db, session_id)
        sync_report = clock_sync_service.enrich_report_with_session_start(
            session_id=session_id,
            authority=authority,
            video_start_monotonic_ms=video_start_monotonic_ms,
        )
        csv_writer_service.prepare_session_writers(db, session_id)
    except RuntimeError as exc:
        _cleanup_failed_start(db, session_id, video_started=video_started, session_started=session_started)
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except ValueError as exc:
        _cleanup_failed_start(db, session_id, video_started=video_started, session_started=session_started)
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except SessionStateError as exc:
        video_recorder_service.stop_session_recording(db, session_id, suppress_errors=True)
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    await ws_runtime.publish_session_event(
        session_id,
        {
            "type": "SESSION_STATE",
            "session_id": session_id,
            "status": session.status,
            "server_start_time_unix_ns": int(authority.server_start_time_unix_ns),
        },
    )
    await ws_runtime.start_session_countdown(
        session_id=session_id,
        start_at_unix_ns=int(authority.server_start_time_unix_ns),
    )
    await ws_runtime.publish_session_event(
        session_id,
        {
            "type": "CLOCK_SYNC_STATUS",
            "session_id": session_id,
            "overall_sync_quality": sync_report.get("overall_sync_quality", "unknown"),
            "overall_sync_quality_color": sync_report.get("overall_sync_quality_color", "yellow"),
            "devices": sync_report.get("devices", []),
        },
    )

    sent_to = await ws_runtime.broadcast_command_to_session_devices(
        session_id,
        {
            "type": "START_SESSION",
            "session_id": session_id,
            "start_at_unix_ns": int(authority.server_start_time_unix_ns),
            "start_delay_ms": start_lead_ms,
            "server_start_time_unix_ns": int(authority.server_start_time_unix_ns),
            "recording_start_seq": 1,
            "target_sampling_hz": get_settings().session_target_sampling_hz,
        },
    )
    await ws_runtime.publish_session_event(
        session_id,
        {
            "type": "VIDEO_RECORDER_STATUS",
            "session_id": session_id,
            "status": "recording",
            "video_start_offset_ms": sync_report.get("video_start_offset_ms"),
            "start_command_sent_devices": sent_to,
        },
    )
    _audit_operator_action(
        db,
        request,
        action="session.start",
        session_id=session_id,
        target_type="session",
        target_id=session_id,
        details={"start_command_sent_devices": sent_to, "clock_sync_quality": sync_report.get("overall_sync_quality", "unknown")},
    )
    return session


@router.put(
    "/{session_id}/devices",
    responses={
        **SESSION_RESPONSES_404,
        **SESSION_RESPONSES_409,
        **SESSION_RESPONSES_400,
    },
)
def assign_session_devices(
    session_id: Annotated[str, Path(pattern=SESSION_ID_PATTERN)],
    payload: SessionDeviceAssignRequest,
    db: DBSession,
    request: Request,
) -> SessionDeviceAssignmentResponse:
    session = db.get(SessionModel, session_id)
    if not session:
        raise HTTPException(status_code=404, detail=SESSION_NOT_FOUND)
    if session.status != "CREATED":
        raise HTTPException(status_code=409, detail=f"assign devices hanya boleh saat session CREATED, saat ini {session.status}")
    if not payload.assignments:
        raise HTTPException(status_code=400, detail="assignments tidak boleh kosong")

    existing_map = _resolve_assignment_devices(db, payload.assignments)
    _validate_assignment_constraints(payload.assignments, existing_map)
    _upsert_session_assignments(
        db,
        session_id=session_id,
        assignments=payload.assignments,
        replace=payload.replace,
    )
    _audit_operator_action(
        db,
        request,
        action="session.devices.assign",
        session_id=session_id,
        target_type="session",
        target_id=session_id,
        details={
            "replace": bool(payload.replace),
            "assignments": [
                {"device_id": item.device_id, "required": bool(item.required)} for item in payload.assignments
            ],
        },
    )

    return SessionDeviceAssignmentResponse(
        session_id=session_id,
        required_roles=get_settings().required_roles,
        bindings=_load_session_bindings(db, session_id),
    )


@router.get("/{session_id}/devices", responses=SESSION_RESPONSES_404)
def list_session_devices(
    session_id: Annotated[str, Path(pattern=SESSION_ID_PATTERN)],
    db: DBSession,
) -> SessionDeviceAssignmentResponse:
    session = db.get(SessionModel, session_id)
    if not session:
        raise HTTPException(status_code=404, detail=SESSION_NOT_FOUND)

    return SessionDeviceAssignmentResponse(
        session_id=session_id,
        required_roles=get_settings().required_roles,
        bindings=_load_session_bindings(db, session_id),
    )


@router.post("/{session_id}/stop", responses={404: {"description": "Session not found"}, 409: {"description": "Invalid session state transition"}})
async def stop_session(
    session_id: Annotated[str, Path(pattern=SESSION_ID_PATTERN)],
    db: DBSession,
    request: Request,
) -> SessionResponse:
    session = db.get(SessionModel, session_id)
    if not session:
        raise HTTPException(status_code=404, detail=SESSION_NOT_FOUND)

    if session.status in {"RUNNING", "SYNCING"}:
        await ws_runtime.stop_session_countdown(session_id)
        await _auto_close_active_annotations(db, session_id)

    if session.status == "SYNCING":
        session = _set_session_status(db, session, "ENDING", set_stopped_at=True)
        _close_session_outputs(db, session_id)
    elif session.status == "RUNNING":
        stop_ack = await ws_runtime.request_stop_acks(
            session_id,
            device_ids=_session_device_ids(db, session_id),
            timeout_seconds=get_settings().stop_command_ack_timeout_seconds,
        )

        pending_devices = list(stop_ack.get("pending_devices", []))
        if pending_devices:
            session = _set_session_status(db, session, "SYNCING", set_stopped_at=True)
            video_recorder_service.stop_session_recording(db, session_id, suppress_errors=True)
            await ws_runtime.publish_warning(
                session_id,
                device_id="session",
                warning=f"stop ack pending dari device: {', '.join(sorted(pending_devices))}",
            )
            await ws_runtime.publish_session_event(
                session_id,
                {
                    "type": "SESSION_STOP_SYNCING",
                    "session_id": session_id,
                    "status": "SYNCING",
                    "pending_devices": pending_devices,
                    "acked_devices": stop_ack.get("acked_devices", []),
                    "sent_devices": stop_ack.get("sent_devices", []),
                },
            )
        else:
            try:
                session = session_manager.stop_session(db, session_id)
            except SessionStateError as exc:
                raise HTTPException(status_code=409, detail=str(exc)) from exc
            _close_session_outputs(db, session_id)
            missing_summary = _update_missing_sample_sync_report(session_id)
            await ws_runtime.publish_session_event(
                session_id,
                {
                    "type": "MISSING_SAMPLE_SUMMARY",
                    **missing_summary,
                },
            )
            completeness = evaluate_session_completeness(db, session_id)
            write_completeness_report(session_id, completeness)
            await ws_runtime.publish_session_event(
                session_id,
                {
                    "type": "SESSION_COMPLETENESS",
                    "session_id": session_id,
                    "complete": completeness.complete,
                    "checks": completeness.checks,
                    "detail": completeness.detail,
                },
            )
            clock_sync_service.clear_session(session_id)
    else:
        raise HTTPException(status_code=409, detail=f"invalid transition {session.status} -> ENDING")

    await ws_runtime.publish_session_event(
        session_id,
        {
            "type": "SESSION_STATE",
            "session_id": session_id,
            "status": session.status,
        },
    )
    await ws_runtime.publish_session_event(
        session_id,
        {
            "type": "VIDEO_RECORDER_STATUS",
            "session_id": session_id,
            "status": "stopped",
        },
    )
    materialize_session_storage(db, session_id)
    _audit_operator_action(
        db,
        request,
        action="session.stop",
        session_id=session_id,
        target_type="session",
        target_id=session_id,
        details={"status_after": session.status},
    )
    return session


@router.get("/{session_id}/video/status", responses=SESSION_RESPONSES_404)
def get_video_status(session_id: Annotated[str, Path(pattern=SESSION_ID_PATTERN)], db: DBSession) -> VideoStatusResponse:
    session = db.get(SessionModel, session_id)
    if not session:
        raise HTTPException(status_code=404, detail=SESSION_NOT_FOUND)
    return VideoStatusResponse(**video_recorder_service.get_runtime_status(db, session_id))


@router.get("/{session_id}/video/metadata", responses=SESSION_RESPONSES_404)
def get_video_metadata(session_id: Annotated[str, Path(pattern=SESSION_ID_PATTERN)], db: DBSession) -> VideoMetadataResponse:
    session = db.get(SessionModel, session_id)
    if not session:
        raise HTTPException(status_code=404, detail=SESSION_NOT_FOUND)

    sidecar_path = _sidecar_path_for_session(session_id)
    if not sidecar_path.exists():
        raise HTTPException(status_code=404, detail="video metadata not found")

    payload = json.loads(sidecar_path.read_text(encoding="utf-8"))
    return VideoMetadataResponse(**payload)


@router.get("/{session_id}/sync-report", responses=SESSION_RESPONSES_404)
def get_sync_report(session_id: Annotated[str, Path(pattern=SESSION_ID_PATTERN)], db: DBSession) -> dict:
    session = db.get(SessionModel, session_id)
    if not session:
        raise HTTPException(status_code=404, detail=SESSION_NOT_FOUND)
    return clock_sync_service.read_sync_report(session_id)


@router.get("/{session_id}/completeness", responses=SESSION_RESPONSES_404)
def get_session_completeness(
    session_id: Annotated[str, Path(pattern=SESSION_ID_PATTERN)],
    db: DBSession,
) -> dict[str, object]:
    session = db.get(SessionModel, session_id)
    if not session:
        raise HTTPException(status_code=404, detail=SESSION_NOT_FOUND)

    report = evaluate_session_completeness(db, session_id)
    return {
        "session_id": session_id,
        **_completeness_payload(report),
    }


@router.get("/{session_id}/sampling-quality", responses=SESSION_RESPONSES_404)
def get_session_sampling_quality_history(
    session_id: Annotated[str, Path(pattern=SESSION_ID_PATTERN)],
    db: DBSession,
    device_id: str | None = None,
    limit: int = 500,
) -> SessionSamplingQualityHistoryResponse:
    session = db.get(SessionModel, session_id)
    if not session:
        raise HTTPException(status_code=404, detail=SESSION_NOT_FOUND)

    safe_limit = min(max(int(limit), 1), 5000)
    query = db.query(DeviceSamplingTelemetry).filter(DeviceSamplingTelemetry.session_id == session_id)
    if device_id and device_id.strip():
        query = query.filter(DeviceSamplingTelemetry.device_id == device_id.strip())

    rows = (
        query.order_by(DeviceSamplingTelemetry.measured_at.desc(), DeviceSamplingTelemetry.id.desc())
        .limit(safe_limit)
        .all()
    )
    points = list(reversed(rows))

    return SessionSamplingQualityHistoryResponse(
        session_id=session_id,
        points=[
            {
                "device_id": row.device_id,
                "connected": bool(row.connected),
                "recording": bool(row.recording),
                "battery_percent": row.battery_percent,
                "storage_free_mb": row.storage_free_mb,
                "effective_hz": row.effective_hz,
                "interval_p99_ms": row.interval_p99_ms,
                "jitter_p99_ms": row.jitter_p99_ms,
                "measured_at": row.measured_at,
            }
            for row in points
        ],
    )


@router.get("/{session_id}/video/metadata/download", responses=SESSION_RESPONSES_404)
def download_video_metadata(session_id: Annotated[str, Path(pattern=SESSION_ID_PATTERN)], db: DBSession) -> FileResponse:
    session = db.get(SessionModel, session_id)
    if not session:
        raise HTTPException(status_code=404, detail=SESSION_NOT_FOUND)

    sidecar_path = _sidecar_path_for_session(session_id)
    if not sidecar_path.exists():
        raise HTTPException(status_code=404, detail="video metadata not found")

    return FileResponse(path=str(sidecar_path), media_type="application/json", filename=sidecar_path.name)


@router.post("/{session_id}/video/anonymize", responses=SESSION_RESPONSES_404)
def anonymize_video(
    session_id: Annotated[str, Path(pattern=SESSION_ID_PATTERN)],
    db: DBSession,
    use_mock: bool = Query(default=False),
) -> VideoAnonymizeResponse:
    session = db.get(SessionModel, session_id)
    if not session:
        raise HTTPException(status_code=404, detail=SESSION_NOT_FOUND)

    try:
        payload = video_recorder_service.anonymize_session_video(session_id, force_mock=use_mock)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return VideoAnonymizeResponse(**payload)


@router.get("/{session_id}", responses=SESSION_RESPONSES_404)
def get_session(session_id: Annotated[str, Path(pattern=SESSION_ID_PATTERN)], db: DBSession) -> SessionResponse:
    session = db.get(SessionModel, session_id)
    if not session:
        raise HTTPException(status_code=404, detail=SESSION_NOT_FOUND)
    return session


@router.get("/{session_id}/status", responses=SESSION_RESPONSES_404)
def get_session_status(session_id: Annotated[str, Path(pattern=SESSION_ID_PATTERN)], db: DBSession) -> SessionStatusResponse:
    try:
        status = session_manager.get_status(db, session_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return SessionStatusResponse(session_id=session_id, status=status)


@router.post("/{session_id}/finalize", responses={404: {"description": "Session not found"}, 409: {"description": "Invalid session state transition"}})
async def finalize_session(
    session_id: Annotated[str, Path(pattern=SESSION_ID_PATTERN)],
    payload: SessionFinalizeRequest,
    db: DBSession,
    request: Request,
) -> SessionResponse:
    await ws_runtime.stop_session_countdown(session_id)
    session = db.get(SessionModel, session_id)
    if not session:
        raise HTTPException(status_code=404, detail=SESSION_NOT_FOUND)

    if session.status == "SYNCING":
        _close_session_outputs(db, session_id)
        session = _set_session_status(db, session, "ENDING")

    if payload.incomplete and not (payload.reason or "").strip():
        raise HTTPException(status_code=400, detail="reason wajib diisi untuk finalize incomplete")

    if not payload.incomplete:
        completeness = evaluate_session_completeness(db, session_id)
        write_completeness_report(session_id, completeness)
        if not completeness.complete:
            raise HTTPException(
                status_code=409,
                detail={
                    "message": "session belum lengkap, gunakan finalize incomplete dengan reason",
                    "completeness": _completeness_payload(completeness),
                },
            )

    try:
        session = session_manager.finalize_session(db, session_id, incomplete=payload.incomplete)
        if payload.incomplete:
            session.override_reason = (payload.reason or "").strip()
            db.commit()
            db.refresh(session)
        missing_summary = _update_missing_sample_sync_report(session_id)
        finalize_session_artifacts(db, session_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except SessionStateError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    await ws_runtime.publish_session_event(
        session_id,
        {
            "type": "SESSION_STATE",
            "session_id": session_id,
            "status": session.status,
        },
    )
    await ws_runtime.publish_session_event(
        session_id,
        {
            "type": "VIDEO_RECORDER_STATUS",
            "session_id": session_id,
            "status": "idle",
        },
    )
    await ws_runtime.publish_session_event(
        session_id,
        {
            "type": "MISSING_SAMPLE_SUMMARY",
            **missing_summary,
        },
    )
    materialize_session_storage(db, session_id)
    _audit_operator_action(
        db,
        request,
        action="session.finalize",
        session_id=session_id,
        target_type="session",
        target_id=session_id,
        details={"incomplete": bool(payload.incomplete), "reason": (payload.reason or "").strip()},
    )
    return session
