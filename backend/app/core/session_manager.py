from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.db.models import Session as SessionModel


@dataclass
class SessionState:
    session_id: str
    status: str


class SessionStateError(Exception):
    pass


class SessionManager:
    def __init__(self) -> None:
        self._active_sessions: dict[str, SessionState] = {}

    def create_session(self, db: Session, session_id: str, preflight_passed: bool, override_reason: str | None = None) -> SessionModel:
        existing = db.get(SessionModel, session_id)
        if existing:
            raise SessionStateError(f"session {session_id} already exists")

        session = SessionModel(
            session_id=session_id,
            status="CREATED",
            preflight_passed=preflight_passed,
            override_reason=override_reason,
        )
        db.add(session)
        db.commit()
        db.refresh(session)
        self._active_sessions[session_id] = SessionState(session_id=session_id, status=session.status)
        return session

    def start_session(self, db: Session, session_id: str) -> SessionModel:
        session = db.get(SessionModel, session_id)
        if not session:
            raise ValueError(SESSION_NOT_FOUND)
        if session.status != "CREATED":
            raise SessionStateError(f"invalid transition {session.status} -> RUNNING")
        session.status = "RUNNING"
        session.started_at = datetime.now(UTC).replace(tzinfo=None)
        db.commit()
        db.refresh(session)
        self._active_sessions[session_id] = SessionState(session_id=session_id, status=session.status)
        return session

    def stop_session(self, db: Session, session_id: str) -> SessionModel:
        session = db.get(SessionModel, session_id)
        if not session:
            raise ValueError(SESSION_NOT_FOUND)
        if session.status != "RUNNING":
            raise SessionStateError(f"invalid transition {session.status} -> ENDING")
        session.status = "ENDING"
        session.stopped_at = datetime.now(UTC).replace(tzinfo=None)
        db.commit()
        db.refresh(session)
        self._active_sessions[session_id] = SessionState(session_id=session_id, status=session.status)
        return session

    def finalize_session(self, db: Session, session_id: str, incomplete: bool = False) -> SessionModel:
        session = db.get(SessionModel, session_id)
        if not session:
            raise ValueError(SESSION_NOT_FOUND)
        if session.status != "ENDING":
            target = "INCOMPLETE_FINALIZED" if incomplete else "COMPLETED"
            raise SessionStateError(f"invalid transition {session.status} -> {target}")
        session.status = "INCOMPLETE_FINALIZED" if incomplete else "COMPLETED"
        session.finalized_at = datetime.now(UTC).replace(tzinfo=None)
        db.commit()
        db.refresh(session)
        self._active_sessions.pop(session_id, None)
        return session

    def get_status(self, db: Session, session_id: str) -> str:
        session = db.get(SessionModel, session_id)
        if not session:
            raise ValueError(SESSION_NOT_FOUND)
        return session.status


session_manager = SessionManager()
SESSION_NOT_FOUND = "session not found"
