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


# NOTE (audit #110): an earlier version of this file used a ``_models()``
# function that returned the four model classes, ostensibly to avoid circular
# imports at module load. Verified: app.models.billing_reports only depends on
# app.db.base / sqlalchemy and nothing inside app.models imports this service,
# so there was never a real cycle. The classes are now imported eagerly at the
# top of the file and used directly by each function.


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


def ensure_matrix_covers_all_modules(db: Session, default_matrix: dict) -> int:
    """Completa la matriz para TODOS los módulos que expone la API.

    Auditoría 2026-08 (hallazgo 28). `default_matrix` opina sobre 15 módulos
    escritos a mano, frente a los 126 dominios de la API: 111 no tenían ni una
    casilla que un administrador pudiera configurar. La lista de módulos se
    DERIVA aquí del router en tiempo de ejecución (ver app/core/grc_catalog.py),
    así que un dominio nuevo entra en la matriz el día que se añade su primera
    ruta, sin que nadie tenga que registrarlo.

    Las casillas nuevas se crean con ``allowed=True`` a propósito: la matriz es un
    control ADITIVO que sólo puede quitar permiso (ver app/core/grc_enforce.py).
    Sembrarlas en False cerraría de golpe 111 dominios para todos los roles no
    administradores. Con True, el comportamiento no cambia hasta que un
    administrador decida restringir algo — y ahora puede, que es lo que faltaba.

    Sólo se crean las acciones que el módulo expone de verdad: una casilla que no
    corresponde a ninguna ruta es indistinguible de una que no se aplica, y el
    objetivo es que todo lo que se ve gobierne algo.

    Devuelve el número de filas creadas. Idempotente.
    """
    from app.core.grc_catalog import discover_module_actions
    from app.main import app as fastapi_app

    por_modulo = discover_module_actions(fastapi_app)
    roles = list(default_matrix.keys())

    existentes = {
        (r.role, r.module, r.action)
        for r in db.query(RolePermission.role, RolePermission.module, RolePermission.action).all()
    }

    nuevas = []
    for modulo, acciones in por_modulo.items():
        for rol in roles:
            declarado = default_matrix.get(rol, {}).get(modulo, {})
            for accion in sorted(acciones):
                if (rol, modulo, accion) in existentes:
                    continue
                # Si default_matrix opina sobre esta casilla, se respeta su valor;
                # si no, permisiva (ver el razonamiento del docstring).
                permitido = declarado.get(accion, True)
                nuevas.append(RolePermission(
                    id=str(uuid.uuid4()), role=rol, module=modulo,
                    action=accion, allowed=bool(permitido),
                ))

    if nuevas:
        db.bulk_save_objects(nuevas)
        db.commit()
    return len(nuevas)


def ensure_sod_seeded(db: Session, default_sod_rules: list) -> None:
    """Seed default_sod_rules into DB if grc_sod_rules is empty."""
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
    return db.query(RolePermission).all()


def upsert_permission(
    db: Session,
    role: str, module: str, action: str,
    allowed: bool, updated_by: Optional[str],
):
    """Update existing permission or create it if missing. Returns (row, old_value)."""
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
    db.query(RolePermission).delete()
    db.commit()
    ensure_matrix_seeded(db, default_matrix)


def get_role_permission(db: Session, role: str, module: str, action: str):
    """Return a single RolePermission row or None."""
    return db.query(RolePermission).filter(
        RolePermission.role == role,
        RolePermission.module == module,
        RolePermission.action == action,
    ).first()


# ── SoD Rules CRUD ────────────────────────────────────────────────────────────

def list_sod_rules_db(db: Session):
    """Return all SodRule rows ordered by risk."""
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
    return db.query(SodRule).filter(SodRule.is_active == True).all()


# ── SoD Violations ────────────────────────────────────────────────────────────

def list_violations_db(db: Session, resolved: Optional[bool], limit: int):
    """Return SodViolation rows, optionally filtered by resolved status."""
    q = db.query(SodViolation)
    if resolved is not None:
        q = q.filter(SodViolation.resolved == resolved)
    return q.order_by(SodViolation.detected_at.desc()).limit(limit).all()


def get_violation_or_404(db: Session, violation_id: str):
    """Return SodViolation by id or raise HTTP 404."""
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
