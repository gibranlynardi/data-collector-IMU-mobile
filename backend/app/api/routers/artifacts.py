import hashlib
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.core.auth import get_request_actor, require_operator_access
from app.core.config import get_settings
from app.db.models import ArchiveUpload, FileArtifact
from app.db.session import get_db
from app.schemas.artifacts import (
    ArchiveUploadMarkRequest,
    ArchiveUploadStatusResponse,
    ArtifactResponse,
    UploadInstructionsResponse,
)
from app.services.operator_audit import write_operator_action_audit

router = APIRouter(tags=["artifacts"], dependencies=[Depends(require_operator_access)])
DBSession = Annotated[Session, Depends(get_db)]


def _sha256(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as file_obj:
        for chunk in iter(lambda: file_obj.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def _export_zip_path(session_id: str) -> Path:
    settings = get_settings()
    return settings.data_root / "sessions" / session_id / "export" / f"{session_id}_dataset.zip"


def _remote_zip_path(session_id: str) -> str:
    settings = get_settings()
    remote_root = settings.fams_remote_path.rstrip("/")
    if not remote_root:
        remote_root = "/tmp/fams-dataset"
    return f"{remote_root}/{session_id}_dataset.zip"


def _resolve_archive_upload(db: Session, session_id: str) -> ArchiveUpload:
    row = db.query(ArchiveUpload).filter(ArchiveUpload.session_id == session_id).first()
    if row is not None:
        return row

    created = ArchiveUpload(session_id=session_id, uploaded=False)
    db.add(created)
    db.commit()
    db.refresh(created)
    return created


@router.get("/sessions/{session_id}/artifacts")
def list_artifacts(session_id: str, db: DBSession) -> list[ArtifactResponse]:
    return (
        db.query(FileArtifact)
        .filter(FileArtifact.session_id == session_id)
        .order_by(FileArtifact.id.asc())
        .all()
    )


@router.get("/sessions/{session_id}/manifest.json", responses={404: {"description": "Manifest not found"}})
def get_manifest(session_id: str) -> FileResponse:
    settings = get_settings()
    path = settings.data_root / "sessions" / session_id / "manifest.json"
    if not path.exists():
        raise HTTPException(status_code=404, detail="manifest not found")
    return FileResponse(path=str(path), media_type="application/json", filename="manifest.json")


@router.get("/sessions/{session_id}/export.zip", responses={404: {"description": "Export zip not found"}})
def get_export_zip(session_id: str) -> FileResponse:
    path = _export_zip_path(session_id)
    if not path.exists():
        raise HTTPException(status_code=404, detail="export zip not found")
    return FileResponse(path=str(path), media_type="application/zip", filename=path.name)


@router.get("/sessions/{session_id}/upload-instructions")
def get_upload_instructions(session_id: str) -> UploadInstructionsResponse:
    settings = get_settings()
    export_zip = _export_zip_path(session_id)
    if not export_zip.exists():
        raise HTTPException(status_code=404, detail="export zip not found")

    checksum = _sha256(export_zip)
    remote_target = _remote_zip_path(session_id)
    host = settings.fams_host or "<FAMS_HOST>"
    user = settings.fams_user or "<FAMS_USER>"

    command_ps = (
        f"./scripts/upload_to_fams.ps1 -SessionId {session_id} -LocalFile \"{export_zip.as_posix()}\" "
        f"-FamsHost \"{host}\" -FamsUser \"{user}\" -RemotePath \"{remote_target}\""
    )
    command_sh = (
        f"./scripts/upload_to_fams.sh --session-id {session_id} --local-file \"{export_zip.as_posix()}\" "
        f"--fams-host \"{host}\" --fams-user \"{user}\" --remote-path \"{remote_target}\""
    )

    return UploadInstructionsResponse(
        session_id=session_id,
        export_zip_path=str(export_zip),
        checksum_sha256=checksum,
        remote_target=remote_target,
        command_powershell=command_ps,
        command_shell=command_sh,
    )


@router.get("/sessions/{session_id}/archive-upload")
def get_archive_upload_status(session_id: str, db: DBSession) -> ArchiveUploadStatusResponse:
    row = _resolve_archive_upload(db, session_id)
    return ArchiveUploadStatusResponse(
        session_id=row.session_id,
        uploaded=bool(row.uploaded),
        uploaded_at=row.uploaded_at,
        uploaded_by=row.uploaded_by,
        remote_path=row.remote_path,
        checksum=row.checksum,
    )


@router.post("/sessions/{session_id}/archive-upload/mark-uploaded")
def mark_archive_uploaded(
    session_id: str,
    payload: ArchiveUploadMarkRequest,
    db: DBSession,
    request: Request,
) -> ArchiveUploadStatusResponse:
    export_zip = _export_zip_path(session_id)
    if not export_zip.exists():
        raise HTTPException(status_code=404, detail="export zip not found")

    local_checksum = _sha256(export_zip)
    if payload.checksum.strip().lower() != local_checksum.lower():
        raise HTTPException(status_code=400, detail="checksum mismatch with local export zip")

    row = _resolve_archive_upload(db, session_id)
    row.uploaded = True
    row.uploaded_at = datetime.now(UTC).replace(tzinfo=None)
    row.uploaded_by = payload.uploaded_by.strip()
    row.remote_path = payload.remote_path.strip()
    row.checksum = local_checksum
    db.commit()
    db.refresh(row)

    operator_id, operator_type = get_request_actor(request)
    write_operator_action_audit(
        db,
        operator_id=operator_id or "operator",
        operator_type=operator_type or "operator",
        action="archive.mark_uploaded",
        session_id=session_id,
        target_type="archive_upload",
        target_id=session_id,
        details={"uploaded_by": row.uploaded_by, "remote_path": row.remote_path},
    )
    db.commit()

    return ArchiveUploadStatusResponse(
        session_id=row.session_id,
        uploaded=bool(row.uploaded),
        uploaded_at=row.uploaded_at,
        uploaded_by=row.uploaded_by,
        remote_path=row.remote_path,
        checksum=row.checksum,
    )
