"""Service functions for SoD enforcement and violation logging."""
import uuid
from typing import Optional

from sqlalchemy.orm import Session
from app.models.billing_reports import GrcAuditLog
from app.models.billing_reports import SodViolation
from app.models.billing_reports import SodRule


def _log_sod_violation_event(
    db: Session,
    user_id: Optional[str],
    rule_id: str,
    context_type: Optional[str],
    context_id: Optional[str],
) -> None:
    """Persist an audit trail entry for a detected SoD violation."""
    import json

    entry = GrcAuditLog(
        id=str(uuid.uuid4()),
        user_id=user_id,
        action_type="sod_violation_detected",
        resource_type="sod_violation",
        resource_id=context_id,
        detail=json.dumps(
            {
                "rule_id": rule_id,
                "context": context_type,
                "context_id": context_id,
            }
        ),
        severity="critical",
    )
    db.add(entry)


def record_sod_violation(
    db: Session,
    rule_id: str,
    user_id: Optional[str],
    role: Optional[str],
    context_type: Optional[str],
    context_id: Optional[str],
) -> None:
    """Create a SoD violation record plus its associated audit log entry."""

    violation = SodViolation(
        id=str(uuid.uuid4()),
        rule_id=rule_id,
        user_id=user_id,
        role=role,
        context_type=context_type,
        context_id=context_id,
    )
    db.add(violation)
    _log_sod_violation_event(db, user_id, rule_id, context_type, context_id)


def record_self_approval_violation_for_request(
    db: Session,
    entity_type: str,
    request_id: str,
    requested_by: str,
    actor_id: str,
    actor_role: Optional[str],
) -> bool:
    """
    Detect and record SoD violation when request creator tries to self-approve.

    Returns True when the violation condition is met, otherwise False.
    """
    if requested_by != actor_id:
        return False


    matching = db.query(SodRule).filter(
        SodRule.module_a == entity_type,
        SodRule.action_a == "crear",
        SodRule.module_b == entity_type,
        SodRule.action_b == "aprobar",
        SodRule.is_active == True,
    ).first()

    if matching:
        record_sod_violation(
            db=db,
            rule_id=matching.id,
            user_id=actor_id,
            role=actor_role,
            context_type="approval_request",
            context_id=request_id,
        )

    return True