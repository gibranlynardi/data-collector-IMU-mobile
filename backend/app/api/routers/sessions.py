from datetime import UTC, datetime
from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Path, Request
from sqlalchemy.orm import Session

from app.core.lifecycle import run_startup_checks
from app.core.session_manager import SessionStateError, session_manager
from app.db.models import Session as SessionModel
from app.db.session import get_db
from app.schemas.sessions import SessionCreateRequest, SessionFinalizeRequest, SessionResponse, SessionStatusResponse
from app.services.artifacts import ensure_session_layout, finalize_session_artifacts, seed_session_artifacts
from app.services.csv_writer import csv_writer_service
from app.services.preflight import is_preflight_passed, store_preflight_report

router = APIRouter(prefix="/sessions", tags=["sessions"])
DBSession = Annotated[Session, Depends(get_db)]
SESSION_ID_PATTERN = r"^\d{8}_\d{6}_[A-F0-9]{8}$"
SESSION_RESPONSES_404 = {404: {"description": "Session not found"}}
SESSION_RESPONSES_409 = {409: {"description": "Invalid session state transition"}}
SESSION_RESPONSES_400 = {400: {"description": "Bad request"}}


def _generate_session_id() -> str:
    timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    suffix = uuid4().hex[:8].upper()
    return f"{timestamp}_{suffix}"


@router.post("", responses={400: {"description": "Preflight failed"}, 409: {"description": "Another active session exists"}})
def create_session(payload: SessionCreateRequest, request: Request, db: DBSession) -> SessionResponse:
    blocking = (
        db.query(SessionModel)
        .filter(SessionModel.status.in_(["ENDING", "SYNCING", "RUNNING", "CREATED"]))
        .order_by(SessionModel.created_at.desc())
        .first()
    )
    if blocking:
        raise HTTPException(status_code=409, detail=f"session {blocking.session_id} masih aktif ({blocking.status})")

    session_id = payload.session_id or _generate_session_id()
    server_report = run_startup_checks()
    if not is_preflight_passed(server_report) and not payload.override_reason:
        raise HTTPException(status_code=400, detail="preflight wajib pass atau isi override_reason")

    session = session_manager.create_session(
        db=db,
        session_id=session_id,
        preflight_passed=is_preflight_passed(server_report),
        override_reason=payload.override_reason,
    )

    session_root = ensure_session_layout(session_id)
    seed_session_artifacts(db, session_id, session_root)

    request.app.state.preflight_report = server_report
    store_preflight_report(db, server_report, session_id=session_id)

    return session


@router.post("/{session_id}/start", responses={400: {"description": "Preflight failed"}, 404: {"description": "Session not found"}, 409: {"description": "Invalid session state transition"}})
def start_session(
    session_id: Annotated[str, Path(pattern=SESSION_ID_PATTERN)],
    db: DBSession,
) -> SessionResponse:
    session = db.get(SessionModel, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="session not found")

    server_report = run_startup_checks()
    preflight_ok = is_preflight_passed(server_report)
    if not preflight_ok and not session.override_reason:
        raise HTTPException(status_code=400, detail="server preflight failed; start diblokir")

    session.preflight_passed = preflight_ok
    store_preflight_report(db, server_report, session_id=session_id)

    try:
        session = session_manager.start_session(db, session_id)
        csv_writer_service.prepare_session_writers(db, session_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except SessionStateError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return session


@router.post("/{session_id}/stop", responses={404: {"description": "Session not found"}, 409: {"description": "Invalid session state transition"}})
def stop_session(session_id: Annotated[str, Path(pattern=SESSION_ID_PATTERN)], db: DBSession) -> SessionResponse:
    try:
        session = session_manager.stop_session(db, session_id)
        csv_writer_service.flush_session(session_id)
        csv_writer_service.close_session(session_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except SessionStateError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return session


@router.get("/{session_id}", responses=SESSION_RESPONSES_404)
def get_session(session_id: Annotated[str, Path(pattern=SESSION_ID_PATTERN)], db: DBSession) -> SessionResponse:
    session = db.get(SessionModel, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="session not found")
    return session


@router.get("/{session_id}/status", responses=SESSION_RESPONSES_404)
def get_session_status(session_id: Annotated[str, Path(pattern=SESSION_ID_PATTERN)], db: DBSession) -> SessionStatusResponse:
    try:
        status = session_manager.get_status(db, session_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return SessionStatusResponse(session_id=session_id, status=status)


@router.post("/{session_id}/finalize", responses={404: {"description": "Session not found"}, 409: {"description": "Invalid session state transition"}})
def finalize_session(
    session_id: Annotated[str, Path(pattern=SESSION_ID_PATTERN)],
    payload: SessionFinalizeRequest,
    db: DBSession,
) -> SessionResponse:
    try:
        session = session_manager.finalize_session(db, session_id, incomplete=payload.incomplete)
        finalize_session_artifacts(db, session_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except SessionStateError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return session
