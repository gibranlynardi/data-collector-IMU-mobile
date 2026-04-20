from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path
from sqlalchemy.orm import Session

from app.core.auth import AccessIdentity, require_device_access, require_operator_access, require_operator_or_device_access
from app.core.config import get_settings
from app.db.models import Device, DeviceSamplingTelemetry
from app.db.models import Session as SessionModel
from app.db.models import SessionDevice
from app.db.session import get_db
from app.schemas.devices import DevicePatchRequest, DeviceRegisterRequest, DeviceResponse
from app.services.operator_audit import write_operator_action_audit
from app.services.ws_runtime import ws_runtime

router = APIRouter(prefix="/devices", tags=["devices"])
DBSession = Annotated[Session, Depends(get_db)]
DEVICE_ID_PATTERN = r"^DEVICE-(CHEST|WAIST|THIGH|OTHER)-\d{3}$"


@router.post("/register")
def register_device(
    payload: DeviceRegisterRequest,
    db: DBSession,
    identity: Annotated[AccessIdentity, Depends(require_device_access)],
) -> DeviceResponse:
    device = db.get(Device, payload.device_id)
    if device:
        device.device_role = payload.device_role
        device.display_name = payload.display_name
        device.ip_address = payload.ip_address
    else:
        device = Device(
            device_id=payload.device_id,
            device_role=payload.device_role,
            display_name=payload.display_name,
            ip_address=payload.ip_address,
            connected=False,
        )
        db.add(device)

    db.commit()
    db.refresh(device)
    write_operator_action_audit(
        db,
        operator_id=identity.actor_id,
        operator_type=identity.actor_type,
        action="device.register",
        target_type="device",
        target_id=device.device_id,
        details={"device_role": device.device_role, "display_name": device.display_name},
    )
    db.commit()
    return device


@router.get("")
def list_devices(
    db: DBSession,
    _operator: Annotated[AccessIdentity, Depends(require_operator_access)],
) -> list[DeviceResponse]:
    return db.query(Device).order_by(Device.device_id.asc()).all()


@router.patch("/{device_id}", responses={404: {"description": "Device not found"}})
def patch_device(
    device_id: Annotated[str, Path(pattern=DEVICE_ID_PATTERN)],
    payload: DevicePatchRequest,
    db: DBSession,
    identity: Annotated[AccessIdentity, Depends(require_operator_or_device_access)],
) -> DeviceResponse:
    device = db.get(Device, device_id)
    if not device:
        raise HTTPException(status_code=404, detail="device not found")

    updates = payload.model_dump(exclude_unset=True)
    telemetry_keys = {"effective_hz", "interval_p99_ms", "jitter_p99_ms"}
    telemetry_present = any(key in updates for key in telemetry_keys)
    for key, value in updates.items():
        setattr(device, key, value)

    db.commit()
    db.refresh(device)

    active_session_ids = [
        session_id
        for (session_id,) in (
            db.query(SessionDevice.session_id)
            .join(SessionModel, SessionModel.session_id == SessionDevice.session_id)
            .filter(
                SessionDevice.device_id == device_id,
                SessionModel.status.in_(["RUNNING", "SYNCING"]),
            )
            .order_by(SessionModel.started_at.desc(), SessionModel.session_id.asc())
            .all()
        )
    ]

    if telemetry_present:
        measured_at = device.updated_at
        telemetry_row = DeviceSamplingTelemetry(
            session_id=active_session_ids[0] if active_session_ids else None,
            device_id=device_id,
            connected=bool(device.connected),
            recording=bool(device.recording),
            battery_percent=device.battery_percent,
            storage_free_mb=device.storage_free_mb,
            effective_hz=device.effective_hz,
            interval_p99_ms=device.interval_p99_ms,
            jitter_p99_ms=device.jitter_p99_ms,
            measured_at=measured_at,
        )
        db.add(telemetry_row)
        db.commit()

        payload_event = {
            "type": "DEVICE_SAMPLING_QUALITY",
            "device_id": device_id,
            "effective_hz": float(device.effective_hz) if device.effective_hz is not None else None,
            "interval_p99_ms": float(device.interval_p99_ms) if device.interval_p99_ms is not None else None,
            "jitter_p99_ms": float(device.jitter_p99_ms) if device.jitter_p99_ms is not None else None,
            "battery_percent": float(device.battery_percent) if device.battery_percent is not None else None,
            "storage_free_mb": int(device.storage_free_mb) if device.storage_free_mb is not None else None,
            "measured_at": measured_at.isoformat() if measured_at else None,
        }
        for session_id in active_session_ids:
            ws_runtime.publish_device_event_sync(session_id, {**payload_event, "session_id": session_id})

    settings = get_settings()

    if device.storage_free_mb is not None and device.storage_free_mb <= settings.device_storage_critical_mb:
        for session_id in active_session_ids:
            ws_runtime.publish_warning_sync(
                session_id,
                device_id=device_id,
                warning=(
                    f"device storage kritis: {device.storage_free_mb}MB "
                    f"(threshold={settings.device_storage_critical_mb}MB)"
                ),
            )
            ws_runtime.publish_device_event_sync(
                session_id,
                {
                    "type": "DEVICE_STORAGE_CRITICAL",
                    "session_id": session_id,
                    "device_id": device_id,
                    "storage_free_mb": device.storage_free_mb,
                    "threshold_mb": settings.device_storage_critical_mb,
                },
            )

    if device.battery_percent is not None and device.battery_percent <= settings.battery_critical_percent:
        for session_id in active_session_ids:
            ws_runtime.publish_warning_sync(
                session_id,
                device_id=device_id,
                warning=(
                    f"device battery kritis: {device.battery_percent:.1f}% "
                    f"(threshold={settings.battery_critical_percent:.1f}%)"
                ),
            )
            ws_runtime.publish_device_event_sync(
                session_id,
                {
                    "type": "DEVICE_LOST",
                    "session_id": session_id,
                    "device_id": device_id,
                    "battery_percent": float(device.battery_percent),
                    "threshold_percent": float(settings.battery_critical_percent),
                    "reason": "battery_critical",
                },
            )

    write_operator_action_audit(
        db,
        operator_id=identity.actor_id,
        operator_type=identity.actor_type,
        action="device.patch",
        session_id=active_session_ids[0] if active_session_ids else None,
        target_type="device",
        target_id=device_id,
        details={"fields": sorted(list(updates.keys()))},
    )
    db.commit()

    return device
