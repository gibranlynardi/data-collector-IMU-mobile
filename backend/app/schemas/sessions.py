from datetime import datetime

from pydantic import BaseModel, Field

from app.schemas.common import DeviceId, DeviceRole, SessionId


class SessionCreateRequest(BaseModel):
    session_id: SessionId | None = None
    preflight_passed: bool = Field(default=False, description="Ignored by server; preflight is evaluated server-side")
    override_reason: str | None = None


class SessionFinalizeRequest(BaseModel):
    incomplete: bool = False
    reason: str | None = None


class SessionResponse(BaseModel):
    session_id: SessionId
    status: str
    preflight_passed: bool
    override_reason: str | None
    created_at: datetime
    started_at: datetime | None
    stopped_at: datetime | None
    finalized_at: datetime | None

    model_config = {"from_attributes": True}


class SessionStatusResponse(BaseModel):
    session_id: SessionId
    status: str


class SessionDeviceAssignItem(BaseModel):
    device_id: DeviceId
    required: bool = True


class SessionDeviceAssignRequest(BaseModel):
    assignments: list[SessionDeviceAssignItem]
    replace: bool = True


class SessionDeviceBindingResponse(BaseModel):
    device_id: DeviceId
    device_role: DeviceRole
    required: bool
    connected: bool


class SessionDeviceAssignmentResponse(BaseModel):
    session_id: SessionId
    required_roles: list[DeviceRole]
    bindings: list[SessionDeviceBindingResponse]
