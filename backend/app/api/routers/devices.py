from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path
from sqlalchemy.orm import Session

from app.db.models import Device
from app.db.session import get_db
from app.schemas.devices import DevicePatchRequest, DeviceRegisterRequest, DeviceResponse

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
            connected=True,
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
    return device
