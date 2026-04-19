from datetime import datetime

from pydantic import BaseModel


class ArtifactResponse(BaseModel):
    id: int
    session_id: str
    artifact_type: str
    file_path: str
    exists: bool
    size_bytes: int | None
    checksum: str | None
    created_at: datetime

    model_config = {"from_attributes": True}
