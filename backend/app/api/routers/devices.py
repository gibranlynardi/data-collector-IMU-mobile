from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.models import Device
from app.db.models import Session as SessionModel
from app.db.models import SessionDevice
from app.db.session import get_db
from app.schemas.devices import DevicePatchRequest, DeviceRegisterRequest, DeviceResponse
from app.services.ws_runtime import ws_runtime

router = APIRouter(prefix="/devices", tags=["devices"])
DBSession = Annotated[Session, Depends(get_db)]
DEVICE_ID_PATTERN = r"^DEVICE-(CHEST|WAIST|THIGH|OTHER)-\d{3}$"


@router.post("/register")
def register_device(payload: DeviceRegisterRequest, db: DBSession) -> DeviceResponse:
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
    return device


@router.get("")
def list_devices(db: DBSession) -> list[DeviceResponse]:
    return db.query(Device).order_by(Device.device_id.asc()).all()


@router.patch("/{device_id}", responses={404: {"description": "Device not found"}})
def patch_device(device_id: Annotated[str, Path(pattern=DEVICE_ID_PATTERN)], payload: DevicePatchRequest, db: DBSession) -> DeviceResponse:
    device = db.get(Device, device_id)
    if not device:
        raise HTTPException(status_code=404, detail="device not found")

    updates = payload.model_dump(exclude_unset=True)
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
            .all()
        )
    ]
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

    return device
