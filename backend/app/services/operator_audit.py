from __future__ import annotations

import json
from typing import Any

from sqlalchemy.orm import Session

from app.db.models import OperatorActionAudit


def write_operator_action_audit(
    db: Session,
    *,
    operator_id: str,
    operator_type: str,
    action: str,
    session_id: str | None = None,
    target_type: str | None = None,
    target_id: str | None = None,
    details: dict[str, Any] | None = None,
) -> None:
    row = OperatorActionAudit(
        operator_id=operator_id,
        operator_type=operator_type,
        action=action,
        session_id=session_id,
        target_type=target_type,
        target_id=target_id,
        details_json=json.dumps(details or {}, ensure_ascii=True),
    )
    db.add(row)
