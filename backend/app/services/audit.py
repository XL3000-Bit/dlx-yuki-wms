from typing import Any
from sqlalchemy.orm import Session
from app.models.inbound import AuditLog
from app.models.user import User


def write_audit(
    db: Session,
    user: User | None,
    action: str,
    entity_type: str,
    entity_id: int | None,
    before: dict[str, Any] | None = None,
    after: dict[str, Any] | None = None,
) -> AuditLog:
    row = AuditLog(
        user_id=None if user is None else user.id,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        before_data=before,
        after_data=after,
    )
    db.add(row)
    return row
