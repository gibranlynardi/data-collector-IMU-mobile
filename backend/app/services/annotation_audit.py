import json
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.db.models import AnnotationAudit


def write_annotation_audit(
    db: Session,
    action: str,
    annotation_id: str,
    session_id: str,
    before_payload: dict,
    after_payload: dict,
) -> None:
    db.add(
        AnnotationAudit(
            annotation_id=annotation_id,
            session_id=session_id,
            action=action,
            old_value_json=json.dumps(before_payload, ensure_ascii=True),
            new_value_json=json.dumps(after_payload, ensure_ascii=True),
            changed_at=datetime.now(UTC).replace(tzinfo=None),
        )
    )
