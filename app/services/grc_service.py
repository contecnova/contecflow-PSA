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
from app.models.billing_reports import RolePermission, SodRule, SodViolation, GrcAuditLog
from app.core.errores import ErrorDeDominio


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


# ── Permission matrix ─────────────────────────────────────────────────────────
#
# Revisión 2026-11 (multiempresa). La matriz era UNA para toda la plataforma,
# sembrada sin empresa, y se leía y escribía confiando en el filtro de la
# sesión: un administrador de empresa veía la matriz vacía (las filas globales
# no son de su empresa), cada visita volvía a sembrarla (contaba 0), lo que
# editaba quedaba en filas propias que la comprobación podía no leer, y lo que
# se restringía podía aplicarse a otras empresas. Ahora:
#
#   · filas globales (organization_id NULL) = valores por defecto, sembradas
#     una vez y ampliadas con los módulos nuevos;
#   · filas de una empresa = sus excepciones; ganan sobre las globales;
#   · leer, escribir y restablecer nombran la empresa explícitamente.

def _globales(db: Session):
    return db.query(RolePermission).filter(RolePermission.organization_id.is_(None))


def ensure_matrix_seeded(db: Session, default_matrix: dict) -> None:
    """Siembra los valores globales si no hay ninguno. Idempotente."""
    from app.db.session import sin_filtro_de_tenant
    with sin_filtro_de_tenant(db):
        if _globales(db).count():
            return
        db.bulk_save_objects([
            RolePermission(id=str(uuid.uuid4()), organization_id=None, role=role, module=module,
                           action=action, allowed=allowed)
            for role, modules in default_matrix.items()
            for module, actions in modules.items()
            for action, allowed in actions.items()])
        db.commit()


def ensure_matrix_covers_all_modules(db: Session, default_matrix: dict) -> int:
    """Completa los valores globales para TODOS los módulos que expone la API.

    Auditoría 2026-08 (hallazgo 28): la lista de módulos se deriva del router
    (app/core/grc_catalog.py). Las casillas nuevas nacen con ``allowed=True``:
    la matriz es un control ADITIVO que solo puede quitar permiso. Devuelve
    cuántas filas creó. Idempotente.
    """
    from app.core.grc_catalog import discover_module_actions
    from app.db.session import sin_filtro_de_tenant
    from app.main import app as fastapi_app

    por_modulo = discover_module_actions(fastapi_app)
    roles = list(default_matrix.keys())
    with sin_filtro_de_tenant(db):
        existentes = {(r.role, r.module, r.action) for r in
                      _globales(db).with_entities(RolePermission.role, RolePermission.module, RolePermission.action)}
        nuevas = []
        for modulo, acciones in por_modulo.items():
            for rol in roles:
                declarado = default_matrix.get(rol, {}).get(modulo, {})
                for accion in sorted(acciones):
                    if (rol, modulo, accion) not in existentes:
                        nuevas.append(RolePermission(id=str(uuid.uuid4()), organization_id=None, role=rol,
                                                     module=modulo, action=accion,
                                                     allowed=bool(declarado.get(accion, True))))
        if nuevas:
            db.bulk_save_objects(nuevas)
            db.commit()
    return len(nuevas)


def ensure_sod_seeded(db: Session, default_sod_rules: list, organization_id: Optional[str] = None) -> None:
    """Siembra las reglas SoD por defecto EN ESA EMPRESA si no tiene ninguna.

    Revisión 2026-11: contaba con el filtro de la sesión y sembraba sin empresa.
    Cada empresa tiene su copia, así que editar una regla no toca a las demás.
    """
    from app.db.session import sin_filtro_de_tenant
    with sin_filtro_de_tenant(db):
        q = db.query(SodRule)
        q = q.filter(SodRule.organization_id == organization_id) if organization_id \
            else q.filter(SodRule.organization_id.is_(None))
        if q.count():
            return
        db.bulk_save_objects([
            SodRule(id=str(uuid.uuid4()), organization_id=organization_id,
                    module_a=r["module_a"], action_a=r["action_a"],
                    module_b=r["module_b"], action_b=r["action_b"],
                    risk=r["risk"], description=r["description"],
                    roles_conflict=json.dumps(r["roles_conflict"]))
            for r in default_sod_rules])
        db.commit()


class _Casilla:
    __slots__ = ("role", "module", "action", "allowed", "organization_id")

    def __init__(self, role, module, action, allowed, organization_id=None):
        self.role, self.module, self.action, self.allowed = role, module, action, allowed
        self.organization_id = organization_id   # None: la casilla global


def get_all_permissions(db: Session, organization_id: Optional[str] = None) -> list:
    """La matriz efectiva de la empresa: lo global, con sus excepciones encima."""
    from sqlalchemy import or_
    from app.db.session import sin_filtro_de_tenant
    with sin_filtro_de_tenant(db):
        q = db.query(RolePermission)
        q = q.filter(or_(RolePermission.organization_id.is_(None), RolePermission.organization_id == organization_id)) \
            if organization_id else _globales(db)
        filas = q.all()
    efectiva = {}
    for f in sorted(filas, key=lambda f: f.organization_id is not None):   # globales primero
        efectiva[(f.role, f.module, f.action)] = f.allowed
    return [_Casilla(r, m, a, v) for (r, m, a), v in efectiva.items()]


def get_role_permission(db: Session, role: str, module: str, action: str,
                        organization_id: Optional[str] = None):
    """La casilla efectiva (excepción de la empresa, si no la global), o None."""
    from app.db.session import sin_filtro_de_tenant
    with sin_filtro_de_tenant(db):
        base = db.query(RolePermission).filter(RolePermission.role == role, RolePermission.module == module,
                                               RolePermission.action == action)
        fila = base.filter(RolePermission.organization_id == organization_id).first() if organization_id else None
        fila = fila or base.filter(RolePermission.organization_id.is_(None)).first()
    return _Casilla(fila.role, fila.module, fila.action, fila.allowed, fila.organization_id) if fila else None


def upsert_permission(
    db: Session,
    role: str, module: str, action: str,
    allowed: bool, updated_by: Optional[str],
    organization_id: Optional[str] = None,
):
    """Guarda la excepción de la empresa (sin empresa: el valor global). Devuelve (fila, valor anterior)."""
    from app.db.session import sin_filtro_de_tenant
    anterior = get_role_permission(db, role, module, action, organization_id)
    with sin_filtro_de_tenant(db):
        q = db.query(RolePermission).filter(RolePermission.role == role, RolePermission.module == module,
                                            RolePermission.action == action)
        q = q.filter(RolePermission.organization_id == organization_id) if organization_id \
            else q.filter(RolePermission.organization_id.is_(None))
        row = q.first()
        if row:
            row.allowed, row.updated_by = allowed, updated_by
        else:
            row = RolePermission(id=str(uuid.uuid4()), organization_id=organization_id, role=role, module=module,
                                 action=action, allowed=allowed, updated_by=updated_by)
            db.add(row)
    return row, (anterior.allowed if anterior else None)


def reset_permission_matrix(db: Session, default_matrix: dict, organization_id: Optional[str] = None) -> None:
    """Con empresa: quita sus excepciones (vuelve a los valores globales).
    Sin empresa (superadmin de plataforma): rehace los valores globales."""
    from app.db.session import sin_filtro_de_tenant
    with sin_filtro_de_tenant(db):
        if organization_id:
            db.query(RolePermission).filter(RolePermission.organization_id == organization_id).delete()
            db.commit()
            return
        _globales(db).delete()
        db.commit()
    ensure_matrix_seeded(db, default_matrix)


# ── SoD Rules CRUD ────────────────────────────────────────────────────────────

def _sod_de(db: Session, organization_id: Optional[str]):
    q = db.query(SodRule)
    return q.filter(SodRule.organization_id == organization_id) if organization_id else q


def list_sod_rules_db(db: Session, organization_id: Optional[str] = None):
    """Las reglas SoD de la empresa, por riesgo."""
    return _sod_de(db, organization_id).order_by(SodRule.risk).all()


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
        raise ErrorDeDominio(status_code=404)
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

def get_active_sod_rules(db: Session, organization_id: Optional[str] = None):
    """Las reglas SoD activas de la empresa."""
    return _sod_de(db, organization_id).filter(SodRule.is_active == True).all()


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
        raise ErrorDeDominio(status_code=404)
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
