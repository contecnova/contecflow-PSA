"""
grc_service.py — Service layer for GRC (Governance, Risk & Compliance)

All database operations for the GRC module live here.
The router imports these functions and passes the db session.
"""
import uuid
import json
from datetime import datetime, timezone
from typing import Optional, List

from sqlalchemy.orm import Session
from fastapi import HTTPException
from app.models.billing_reports import RolePermission, SodRule, SodViolation, GrcAuditLog


# ── Lazy model imports (avoid circular imports at module load) ─────────────────

def _models():
    return RolePermission, SodRule, SodViolation, GrcAuditLog


# ── Session helpers ───────────────────────────────────────────────────────────

def commit_db(db: Session) -> None:
    """Commit the current session."""
    db.commit()


# ── Audit log ─────────────────────────────────────────────────────────────────

def log_grc_entry(
    db: Session,
    user_id: Optional[str],
    action_type: str,
    resource_type: Optional[str] = None,
    resource_id: Optional[str] = None,
    detail=None,
    ip: Optional[str] = None,
    severity: str = "info",
) -> None:
    """Add a GRC audit log entry to the session (no commit)."""
    RolePermission, SodRule, SodViolation, GrcAuditLog = _models()
    entry = GrcAuditLog(
        id=str(uuid.uuid4()),
        user_id=user_id,
        action_type=action_type,
        resource_type=resource_type,
        resource_id=resource_id,
        detail=json.dumps(detail) if detail is not None else None,
        ip_address=ip,
        severity=severity,
    )
    db.add(entry)


# ── Permission matrix seeding ─────────────────────────────────────────────────

def ensure_matrix_seeded(db: Session, default_matrix: dict) -> None:
    """Seed default_matrix into DB if grc_role_permissions is empty."""
    RolePermission, *_ = _models()
    count = db.query(RolePermission).count()
    if count == 0:
        rows = []
        for role, modules in default_matrix.items():
            for module, actions in modules.items():
                for action, allowed in actions.items():
                    rows.append(RolePermission(
                        id=str(uuid.uuid4()), role=role, module=module,
                        action=action, allowed=allowed,
                    ))
        db.bulk_save_objects(rows)
        db.commit()


def ensure_sod_seeded(db: Session, default_sod_rules: list) -> None:
    """Seed default_sod_rules into DB if grc_sod_rules is empty."""
    _, SodRule, *_ = _models()
    count = db.query(SodRule).count()
    if count == 0:
        rows = [
            SodRule(
                id=str(uuid.uuid4()),
                module_a=r["module_a"], action_a=r["action_a"],
                module_b=r["module_b"], action_b=r["action_b"],
                risk=r["risk"], description=r["description"],
                roles_conflict=json.dumps(r["roles_conflict"]),
            )
            for r in default_sod_rules
        ]
        db.bulk_save_objects(rows)
        db.commit()


# ── Permission CRUD ───────────────────────────────────────────────────────────

def get_all_permissions(db: Session):
    """Return all RolePermission rows."""
    RolePermission, *_ = _models()
    return db.query(RolePermission).all()


def upsert_permission(
    db: Session,
    role: str, module: str, action: str,
    allowed: bool, updated_by: Optional[str],
):
    """Update existing permission or create it if missing. Returns (row, old_value)."""
    RolePermission, *_ = _models()
    row = db.query(RolePermission).filter(
        RolePermission.role == role,
        RolePermission.module == module,
        RolePermission.action == action,
    ).first()
    old_val = None
    if row:
        old_val = row.allowed
        row.allowed = allowed
        row.updated_by = updated_by
    else:
        row = RolePermission(
            id=str(uuid.uuid4()), role=role, module=module, action=action,
            allowed=allowed, updated_by=updated_by,
        )
        db.add(row)
    return row, old_val


def reset_permission_matrix(db: Session, default_matrix: dict) -> None:
    """Delete all permissions and re-seed from default_matrix."""
    RolePermission, *_ = _models()
    db.query(RolePermission).delete()
    db.commit()
    ensure_matrix_seeded(db, default_matrix)


def get_role_permission(db: Session, role: str, module: str, action: str):
    """Return a single RolePermission row or None."""
    RolePermission, *_ = _models()
    return db.query(RolePermission).filter(
        RolePermission.role == role,
        RolePermission.module == module,
        RolePermission.action == action,
    ).first()


# ── SoD Rules CRUD ────────────────────────────────────────────────────────────

def list_sod_rules_db(db: Session):
    """Return all SodRule rows ordered by risk."""
    _, SodRule, *_ = _models()
    return db.query(SodRule).order_by(SodRule.risk).all()


def create_sod_rule_db(
    db: Session,
    module_a: str, action_a: str,
    module_b: str, action_b: str,
    risk: str, description: Optional[str],
    roles_conflict: List[str],
    mitigated_by_workflow_id: Optional[str],
    created_by: Optional[str],
):
    """Create and persist a new SodRule. Returns the new rule (before commit)."""
    _, SodRule, *_ = _models()
    rule = SodRule(
        id=str(uuid.uuid4()),
        module_a=module_a, action_a=action_a,
        module_b=module_b, action_b=action_b,
        risk=risk, description=description,
        roles_conflict=json.dumps(roles_conflict),
        mitigated_by_workflow_id=mitigated_by_workflow_id or None,
        created_by=created_by,
    )
    db.add(rule)
    return rule


def get_sod_rule_or_404(db: Session, rule_id: str):
    """Return SodRule by id or raise HTTP 404."""
    _, SodRule, *_ = _models()
    rule = db.query(SodRule).filter(SodRule.id == rule_id).first()
    if not rule:
        raise HTTPException(status_code=404)
    return rule


def update_sod_rule_db(db: Session, rule, payload: dict) -> None:
    """Apply allowed field updates to a SodRule and commit."""
    allowed_fields = ["risk", "description", "is_active", "roles_conflict", "mitigated_by_workflow_id"]
    for k, v in payload.items():
        if k in allowed_fields:
            if k == "roles_conflict":
                v = json.dumps(v) if isinstance(v, list) else v
            setattr(rule, k, v)
    db.commit()


def delete_sod_rule_db(db: Session, rule) -> None:
    """Delete a SodRule and commit."""
    db.delete(rule)
    db.commit()


# ── SoD Check ─────────────────────────────────────────────────────────────────

def get_active_sod_rules(db: Session):
    """Return all active SodRule rows."""
    _, SodRule, *_ = _models()
    return db.query(SodRule).filter(SodRule.is_active == True).all()


# ── SoD Violations ────────────────────────────────────────────────────────────

def list_violations_db(db: Session, resolved: Optional[bool], limit: int):
    """Return SodViolation rows, optionally filtered by resolved status."""
    _, _, SodViolation, _ = _models()
    q = db.query(SodViolation)
    if resolved is not None:
        q = q.filter(SodViolation.resolved == resolved)
    return q.order_by(SodViolation.detected_at.desc()).limit(limit).all()


def get_violation_or_404(db: Session, violation_id: str):
    """Return SodViolation by id or raise HTTP 404."""
    _, _, SodViolation, _ = _models()
    v = db.query(SodViolation).filter(SodViolation.id == violation_id).first()
    if not v:
        raise HTTPException(status_code=404)
    return v


def resolve_violation_db(db: Session, v, resolution_note: Optional[str]) -> None:
    """Mark a SodViolation as resolved and commit."""
    v.resolved = True
    v.resolved_at = datetime.now(timezone.utc)
    v.resolution_note = resolution_note
    db.commit()


# ── Audit Log ─────────────────────────────────────────────────────────────────

def list_audit_log_db(
    db: Session,
    severity: Optional[str],
    action_type: Optional[str],
    limit: int,
):
    """Return GrcAuditLog rows with optional filters."""
    _, _, _, GrcAuditLog = _models()
    q = db.query(GrcAuditLog)
    if severity:
        q = q.filter(GrcAuditLog.severity == severity)
    if action_type:
        q = q.filter(GrcAuditLog.action_type == action_type)
    return q.order_by(GrcAuditLog.timestamp.desc()).limit(limit).all()


# ── Permission check (internal utility) ──────────────────────────────────────

def check_permission_db(
    db: Session,
    role: str,
    module: str,
    action: str,
    default_matrix: dict,
) -> bool:
    """
    Return True if role has permission for (module, action).
    Falls back to default_matrix if DB has no matching row.
    """
    row = get_role_permission(db, role, module, action)
    if row is not None:
        return row.allowed
    return default_matrix.get(role, {}).get(module, {}).get(action, False)


# ── Serialization helpers ───────────────────────────────────────────────────────────

def serialize_sod_rule(r) -> dict:
    import json as _json
    return {
        "id": r.id, "module_a": r.module_a, "action_a": r.action_a,
        "module_b": r.module_b, "action_b": r.action_b,
        "risk": r.risk, "description": r.description,
        "is_active": r.is_active,
        "roles_conflict": _json.loads(r.roles_conflict or "[]"),
        "mitigated_by_workflow_id": r.mitigated_by_workflow_id,
        "created_at": str(r.created_at)[:10] if r.created_at else None,
    }


def serialize_violation(v) -> dict:
    return {
        "id": v.id, "rule_id": v.rule_id,
        "user_id": v.user_id,
        "user_name": v.user.full_name if v.user else None,
        "role": v.role,
        "context_type": v.context_type, "context_id": v.context_id,
        "detected_at": str(v.detected_at)[:19] if v.detected_at else None,
        "resolved": v.resolved,
        "resolved_at": str(v.resolved_at)[:19] if v.resolved_at else None,
        "resolution_note": v.resolution_note,
    }
