from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.models import FileArtifact
from app.db.session import get_db
from app.schemas.artifacts import ArtifactResponse

router = APIRouter(tags=["artifacts"])
DBSession = Annotated[Session, Depends(get_db)]


@router.get("/sessions/{session_id}/artifacts")
def list_artifacts(session_id: str, db: DBSession) -> list[ArtifactResponse]:
    return (
        db.query(FileArtifact)
        .filter(FileArtifact.session_id == session_id)
        .order_by(FileArtifact.id.asc())
        .all()
    )


@router.get("/sessions/{session_id}/manifest.json")
def get_manifest(session_id: str) -> FileResponse:
    settings = get_settings()
    path = settings.data_root / "sessions" / session_id / "manifest.json"
    if not path.exists():
        raise HTTPException(status_code=404, detail="manifest not found")
    return FileResponse(path=str(path), media_type="application/json", filename="manifest.json")


@router.get("/sessions/{session_id}/export.zip")
def get_export_zip(session_id: str) -> FileResponse:
    settings = get_settings()
    path = settings.data_root / "sessions" / session_id / "export" / f"{session_id}_dataset.zip"
    if not path.exists():
        raise HTTPException(status_code=404, detail="export zip not found")
    return FileResponse(path=str(path), media_type="application/zip", filename=path.name)
