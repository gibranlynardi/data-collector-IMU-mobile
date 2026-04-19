import json
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, Query
from sqlalchemy.orm import Session

from app.db.models import Annotation, AnnotationAudit
from app.db.session import get_db
from app.schemas.annotations import AnnotationAuditResponse, AnnotationPatchRequest, AnnotationResponse, AnnotationStartRequest
from app.services.annotation_audit import write_annotation_audit

router = APIRouter(tags=["annotations"])
DBSession = Annotated[Session, Depends(get_db)]
ANNOTATION_NOT_FOUND = "annotation not found"
SESSION_ID_PATTERN = r"^\d{8}_\d{6}_[A-F0-9]{8}$"
ANNOTATION_ID_PATTERN = r"^ANN-\d{8}_\d{6}_[A-F0-9]{8}-\d{4}$"


def _snapshot(annotation: Annotation) -> dict:
    return {
        "annotation_id": annotation.annotation_id,
        "session_id": annotation.session_id,
        "label": annotation.label,
        "notes": annotation.notes,
        "started_at": annotation.started_at.isoformat() if annotation.started_at else None,
        "ended_at": annotation.ended_at.isoformat() if annotation.ended_at else None,
        "auto_closed": annotation.auto_closed,
        "deleted": annotation.deleted,
    }


def _next_annotation_id(db: Session, session_id: str) -> str:
    count = db.query(Annotation).filter(Annotation.session_id == session_id).count() + 1
    return f"ANN-{session_id}-{count:04d}"


@router.post("/sessions/{session_id}/annotations/start")
def start_annotation(
    session_id: Annotated[str, Path(pattern=SESSION_ID_PATTERN)],
    payload: AnnotationStartRequest,
    db: DBSession,
) -> AnnotationResponse:
    annotation = Annotation(
        annotation_id=_next_annotation_id(db, session_id),
        session_id=session_id,
        label=payload.label,
        notes=payload.notes,
        started_at=datetime.now(UTC).replace(tzinfo=None),
    )
    db.add(annotation)
    db.commit()
    db.refresh(annotation)
    return annotation


@router.post("/sessions/{session_id}/annotations/{annotation_id}/stop")
def stop_annotation(
    session_id: Annotated[str, Path(pattern=SESSION_ID_PATTERN)],
    annotation_id: Annotated[str, Path(pattern=ANNOTATION_ID_PATTERN)],
    db: DBSession,
) -> AnnotationResponse:
    annotation = db.get(Annotation, annotation_id)
    if not annotation or annotation.session_id != session_id or annotation.deleted:
        raise HTTPException(status_code=404, detail=ANNOTATION_NOT_FOUND)
    before = _snapshot(annotation)
    annotation.ended_at = datetime.now(UTC).replace(tzinfo=None)
    db.commit()
    db.refresh(annotation)
    write_annotation_audit(
        db,
        "stop",
        annotation_id=annotation.annotation_id,
        session_id=annotation.session_id,
        before_payload=before,
        after_payload=_snapshot(annotation),
    )
    db.commit()
    return annotation


@router.get("/sessions/{session_id}/annotations")
def list_annotations(session_id: Annotated[str, Path(pattern=SESSION_ID_PATTERN)], db: DBSession) -> list[AnnotationResponse]:
    return (
        db.query(Annotation)
        .filter(Annotation.session_id == session_id, Annotation.deleted.is_(False))
        .order_by(Annotation.started_at.asc())
        .all()
    )


@router.get("/sessions/{session_id}/annotations/audits")
def list_annotation_audits(
    session_id: Annotated[str, Path(pattern=SESSION_ID_PATTERN)],
    db: DBSession,
    annotation_id: Annotated[str | None, Query(pattern=ANNOTATION_ID_PATTERN)] = None,
) -> list[AnnotationAuditResponse]:
    query = db.query(AnnotationAudit).filter(AnnotationAudit.session_id == session_id)
    if annotation_id:
        query = query.filter(AnnotationAudit.annotation_id == annotation_id)

    items = query.order_by(AnnotationAudit.changed_at.asc(), AnnotationAudit.id.asc()).all()
    return [
        AnnotationAuditResponse(
            id=item.id,
            annotation_id=item.annotation_id,
            session_id=item.session_id,
            action=item.action,
            old_value=json.loads(item.old_value_json),
            new_value=json.loads(item.new_value_json),
            changed_at=item.changed_at,
        )
        for item in items
    ]


@router.patch("/annotations/{annotation_id}")
def patch_annotation(
    annotation_id: Annotated[str, Path(pattern=ANNOTATION_ID_PATTERN)],
    payload: AnnotationPatchRequest,
    db: DBSession,
) -> AnnotationResponse:
    annotation = db.get(Annotation, annotation_id)
    if not annotation or annotation.deleted:
        raise HTTPException(status_code=404, detail=ANNOTATION_NOT_FOUND)

    before = _snapshot(annotation)
    updates = payload.model_dump(exclude_unset=True)
    for key, value in updates.items():
        setattr(annotation, key, value)

    db.commit()
    db.refresh(annotation)
    write_annotation_audit(
        db,
        "patch",
        annotation_id=annotation.annotation_id,
        session_id=annotation.session_id,
        before_payload=before,
        after_payload=_snapshot(annotation),
    )
    db.commit()
    return annotation


@router.delete("/annotations/{annotation_id}")
def delete_annotation(annotation_id: Annotated[str, Path(pattern=ANNOTATION_ID_PATTERN)], db: DBSession) -> dict:
    annotation = db.get(Annotation, annotation_id)
    if not annotation:
        raise HTTPException(status_code=404, detail=ANNOTATION_NOT_FOUND)
    before = _snapshot(annotation)
    annotation.deleted = True
    db.commit()
    db.refresh(annotation)
    write_annotation_audit(
        db,
        "delete",
        annotation_id=annotation.annotation_id,
        session_id=annotation.session_id,
        before_payload=before,
        after_payload=_snapshot(annotation),
    )
    db.commit()
    return {"deleted": True, "annotation_id": annotation_id}
