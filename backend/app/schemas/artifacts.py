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


class UploadInstructionsResponse(BaseModel):
    session_id: str
    export_zip_path: str
    checksum_sha256: str
    remote_target: str
    command_powershell: str
    command_shell: str


class ArchiveUploadMarkRequest(BaseModel):
    uploaded_by: str
    remote_path: str
    checksum: str


class ArchiveUploadStatusResponse(BaseModel):
    session_id: str
    uploaded: bool
    uploaded_at: datetime | None
    uploaded_by: str | None
    remote_path: str | None
    checksum: str | None
