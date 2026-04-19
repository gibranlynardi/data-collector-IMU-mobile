from datetime import datetime
from typing import Any

from pydantic import BaseModel

from app.schemas.common import AnnotationId, LabelName, SessionId


class AnnotationStartRequest(BaseModel):
    label: LabelName
    notes: str | None = None


class AnnotationPatchRequest(BaseModel):
    label: LabelName | None = None
    notes: str | None = None
    started_at: datetime | None = None
    ended_at: datetime | None = None


class AnnotationResponse(BaseModel):
    annotation_id: AnnotationId
    session_id: SessionId
    label: LabelName
    notes: str | None
    started_at: datetime
    ended_at: datetime | None
    auto_closed: bool
    deleted: bool

    model_config = {"from_attributes": True}


class AnnotationAuditResponse(BaseModel):
    id: int
    annotation_id: AnnotationId
    session_id: SessionId
    action: str
    old_value: dict[str, Any]
    new_value: dict[str, Any]
    changed_at: datetime
