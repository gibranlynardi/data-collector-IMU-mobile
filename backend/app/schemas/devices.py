from datetime import datetime

from pydantic import BaseModel, Field

from app.schemas.common import DeviceId, DeviceRole


class DeviceRegisterRequest(BaseModel):
    device_id: DeviceId
    device_role: DeviceRole
    display_name: str | None = None
    ip_address: str | None = None


class DevicePatchRequest(BaseModel):
    device_role: DeviceRole | None = None
    display_name: str | None = None
    ip_address: str | None = None
    connected: bool | None = None
    recording: bool | None = None
    battery_percent: float | None = None
    storage_free_mb: int | None = None
    effective_hz: float | None = None
    interval_p99_ms: float | None = None
    jitter_p99_ms: float | None = None


class DeviceResponse(BaseModel):
    device_id: DeviceId
    device_role: DeviceRole
    display_name: str | None
    ip_address: str | None
    connected: bool
    recording: bool
    battery_percent: float | None
    storage_free_mb: int | None
    effective_hz: float | None
    interval_p99_ms: float | None
    jitter_p99_ms: float | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
