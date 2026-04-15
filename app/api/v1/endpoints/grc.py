"""
grc.py — Governance, Risk & Compliance API

Expone:
  - Matriz de permisos por rol (RolePermission) — lectura y escritura
  - Reglas SoD (SodRule) — CRUD
  - Violaciones SoD (SodViolation) — listado, resolución
  - Audit log GRC — lectura paginada
  - Comprobación SoD ad-hoc

La GRC es la columna vertebral de seguridad de la plataforma.
Todos los cambios de permisos y violaciones quedan registrados en grc_audit_log.
"""
import uuid
import json
from datetime import datetime, timezone
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Body
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.core.deps import get_current_user, require_admin, require_any_manager
from app.models.user import User
from app.services.grc_sod import record_sod_violation as _record_sod_violation

router = APIRouter(prefix="/grc", tags=["GRC"])

# ── Default permission matrix (used for DB seeding) ──────────────────────────
#  Format: role -> module -> action -> allowed (bool)
DEFAULT_MATRIX = {
    "admin":     { m: {a: True  for a in ["ver","crear","editar","eliminar","aprobar","exportar"]}
                   for m in ["projects","tasks","timesheets","invoices","expenses","resources",
                              "service_desk","contracts","clients","reports","settings","approvals","alm","hr","grc"] },
    "pm":        {
        "projects":    {"ver":True,"crear":True,"editar":True,"eliminar":False,"aprobar":True,"exportar":True},
        "tasks":       {"ver":True,"crear":True,"editar":True,"eliminar":True, "aprobar":False,"exportar":True},
        "timesheets":  {"ver":True,"crear":True,"editar":True,"eliminar":False,"aprobar":True,"exportar":True},
        "invoices":    {"ver":True,"crear":True,"editar":True,"eliminar":False,"aprobar":False,"exportar":True},
        "expenses":    {"ver":True,"crear":False,"editar":False,"eliminar":False,"aprobar":True,"exportar":True},
        "resources":   {"ver":True,"crear":True,"editar":True,"eliminar":False,"aprobar":True,"exportar":True},
        "service_desk":{"ver":True,"crear":True,"editar":True,"eliminar":False,"aprobar":True,"exportar":True},
        "contracts":   {"ver":True,"crear":True,"editar":True,"eliminar":False,"aprobar":True,"exportar":True},
        "clients":     {"ver":True,"crear":True,"editar":True,"eliminar":False,"aprobar":True,"exportar":True},
        "reports":     {"ver":True,"crear":False,"editar":False,"eliminar":False,"aprobar":False,"exportar":True},
        "settings":    {"ver":True,"crear":False,"editar":False,"eliminar":False,"aprobar":False,"exportar":False},
        "approvals":   {"ver":True,"crear":True,"editar":True,"eliminar":False,"aprobar":True,"exportar":False},
        "alm":         {"ver":True,"crear":True,"editar":True,"eliminar":False,"aprobar":False,"exportar":True},
        "hr":          {"ver":True,"crear":False,"editar":False,"eliminar":False,"aprobar":False,"exportar":True},
        "grc":         {"ver":True,"crear":False,"editar":False,"eliminar":False,"aprobar":False,"exportar":True},
    },
    "team_lead": {
        "projects":    {"ver":True,"crear":True,"editar":True,"eliminar":False,"aprobar":False,"exportar":True},
        "tasks":       {"ver":True,"crear":True,"editar":True,"eliminar":True, "aprobar":False,"exportar":True},
        "timesheets":  {"ver":True,"crear":True,"editar":True,"eliminar":False,"aprobar":True,"exportar":True},
        "invoices":    {"ver":True,"crear":False,"editar":False,"eliminar":False,"aprobar":False,"exportar":True},
        "expenses":    {"ver":True,"crear":True,"editar":True,"eliminar":False,"aprobar":True,"exportar":True},
        "resources":   {"ver":True,"crear":True,"editar":True,"eliminar":False,"aprobar":False,"exportar":True},
        "service_desk":{"ver":True,"crear":True,"editar":True,"eliminar":False,"aprobar":True,"exportar":True},
        "contracts":   {"ver":True,"crear":False,"editar":False,"eliminar":False,"aprobar":False,"exportar":False},
        "clients":     {"ver":True,"crear":False,"editar":False,"eliminar":False,"aprobar":False,"exportar":False},
        "reports":     {"ver":True,"crear":False,"editar":False,"eliminar":False,"aprobar":False,"exportar":True},
        "settings":    {"ver":False,"crear":False,"editar":False,"eliminar":False,"aprobar":False,"exportar":False},
        "approvals":   {"ver":True,"crear":True,"editar":True,"eliminar":False,"aprobar":True,"exportar":False},
        "alm":         {"ver":True,"crear":True,"editar":True,"eliminar":False,"aprobar":False,"exportar":True},
        "hr":          {"ver":True,"crear":True,"editar":True,"eliminar":False,"aprobar":False,"exportar":True},
        "grc":         {"ver":True,"crear":False,"editar":False,"eliminar":False,"aprobar":False,"exportar":False},
    },
    "employee": {
        "projects":    {"ver":True,"crear":False,"editar":False,"eliminar":False,"aprobar":False,"exportar":False},
        "tasks":       {"ver":True,"crear":True,"editar":True,"eliminar":False,"aprobar":False,"exportar":False},
        "timesheets":  {"ver":True,"crear":True,"editar":True,"eliminar":False,"aprobar":False,"exportar":False},
        "invoices":    {"ver":False,"crear":False,"editar":False,"eliminar":False,"aprobar":False,"exportar":False},
        "expenses":    {"ver":True,"crear":True,"editar":True,"eliminar":False,"aprobar":False,"exportar":False},
        "resources":   {"ver":True,"crear":False,"editar":False,"eliminar":False,"aprobar":False,"exportar":False},
        "service_desk":{"ver":True,"crear":True,"editar":False,"eliminar":False,"aprobar":False,"exportar":False},
        "contracts":   {"ver":False,"crear":False,"editar":False,"eliminar":False,"aprobar":False,"exportar":False},
        "clients":     {"ver":True,"crear":False,"editar":False,"eliminar":False,"aprobar":False,"exportar":False},
        "reports":     {"ver":False,"crear":False,"editar":False,"eliminar":False,"aprobar":False,"exportar":False},
        "settings":    {"ver":False,"crear":False,"editar":False,"eliminar":False,"aprobar":False,"exportar":False},
        "approvals":   {"ver":True,"crear":False,"editar":False,"eliminar":False,"aprobar":False,"exportar":False},
        "alm":         {"ver":True,"crear":False,"editar":False,"eliminar":False,"aprobar":False,"exportar":False},
        "hr":          {"ver":True,"crear":True,"editar":False,"eliminar":False,"aprobar":False,"exportar":False},
        "grc":         {"ver":False,"crear":False,"editar":False,"eliminar":False,"aprobar":False,"exportar":False},
    },
    "hr": {
        "projects":    {"ver":True,"crear":False,"editar":False,"eliminar":False,"aprobar":False,"exportar":True},
        "tasks":       {"ver":True,"crear":False,"editar":False,"eliminar":False,"aprobar":False,"exportar":True},
        "timesheets":  {"ver":True,"crear":True,"editar":True,"eliminar":False,"aprobar":True,"exportar":True},
        "invoices":    {"ver":True,"crear":False,"editar":False,"eliminar":False,"aprobar":False,"exportar":True},
        "expenses":    {"ver":True,"crear":True,"editar":True,"eliminar":False,"aprobar":True,"exportar":True},
        "resources":   {"ver":True,"crear":True,"editar":True,"eliminar":False,"aprobar":True,"exportar":True},
        "service_desk":{"ver":True,"crear":True,"editar":False,"eliminar":False,"aprobar":False,"exportar":True},
        "contracts":   {"ver":True,"crear":False,"editar":False,"eliminar":False,"aprobar":False,"exportar":False},
        "clients":     {"ver":True,"crear":False,"editar":False,"eliminar":False,"aprobar":False,"exportar":False},
        "reports":     {"ver":True,"crear":False,"editar":False,"eliminar":False,"aprobar":False,"exportar":True},
        "settings":    {"ver":True,"crear":False,"editar":False,"eliminar":False,"aprobar":False,"exportar":False},
        "approvals":   {"ver":True,"crear":True,"editar":False,"eliminar":False,"aprobar":True,"exportar":False},
        "alm":         {"ver":True,"crear":False,"editar":False,"eliminar":False,"aprobar":False,"exportar":True},
        "hr":          {"ver":True,"crear":True,"editar":True,"eliminar":False,"aprobar":True,"exportar":True},
        "grc":         {"ver":True,"crear":False,"editar":False,"eliminar":False,"aprobar":False,"exportar":True},
    },
    "client": {
        m: {a: False for a in ["ver","crear","editar","eliminar","aprobar","exportar"]}
        for m in ["projects","tasks","timesheets","invoices","expenses","resources",
                  "service_desk","contracts","clients","reports","settings","approvals","alm","hr","grc"]
    },
}
# Override client ver on specific modules
DEFAULT_MATRIX["client"]["projects"]["ver"] = True
DEFAULT_MATRIX["client"]["invoices"]["ver"] = True
DEFAULT_MATRIX["client"]["service_desk"]["ver"] = True
DEFAULT_MATRIX["client"]["service_desk"]["crear"] = True
DEFAULT_MATRIX["client"]["contracts"]["ver"] = True
DEFAULT_MATRIX["client"]["clients"]["ver"] = True
DEFAULT_MATRIX["client"]["reports"]["ver"] = True

DEFAULT_SOD_RULES = [
    {"module_a":"invoices","action_a":"crear","module_b":"invoices","action_b":"aprobar","risk":"high","description":"Quien crea facturas no debe aprobarlas (riesgo de fraude)","roles_conflict":["pm"]},
    {"module_a":"expenses","action_a":"crear","module_b":"expenses","action_b":"aprobar","risk":"high","description":"Quien registra gastos no debe aprobarlos","roles_conflict":[]},
    {"module_a":"contracts","action_a":"crear","module_b":"contracts","action_b":"aprobar","risk":"high","description":"Quien crea contratos no debe aprobarlos sin supervisión","roles_conflict":["pm"]},
    {"module_a":"resources","action_a":"editar","module_b":"timesheets","action_b":"aprobar","risk":"medium","description":"Gestión de recursos y aprobación de horas puede generar conflicto","roles_conflict":[]},
    {"module_a":"hr","action_a":"editar","module_b":"hr","action_b":"aprobar","risk":"high","description":"Gestión de RRHH y aprobación de ausencias/nóminas","roles_conflict":["hr"]},
    {"module_a":"settings","action_a":"editar","module_b":"approvals","action_b":"aprobar","risk":"critical","description":"Quien configura el sistema no debe aprobar solicitudes críticas sin doble validación","roles_conflict":["admin"]},
    {"module_a":"timesheets","action_a":"crear","module_b":"timesheets","action_b":"aprobar","risk":"high","description":"El empleado no debe aprobar sus propios timesheets","roles_conflict":["pm","team_lead"]},
    {"module_a":"grc","action_a":"editar","module_b":"approvals","action_b":"aprobar","risk":"critical","description":"Quien modifica la matriz GRC no debe poder auto-aprobar sus propias solicitudes","roles_conflict":["admin"]},
]


# ── Helpers ───────────────────────────────────────────────────────────────────

def _log_grc(db: Session, user_id: Optional[str], action_type: str,
             resource_type: Optional[str] = None, resource_id: Optional[str] = None,
             detail=None, ip: Optional[str] = None, severity: str = "info"):
    from app.models.billing_reports import GrcAuditLog
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


def _ensure_matrix_seeded(db: Session):
    """Seed DEFAULT_MATRIX into DB if grc_role_permissions is empty."""
    from app.models.billing_reports import RolePermission
    count = db.query(RolePermission).count()
    if count == 0:
        rows = []
        for role, modules in DEFAULT_MATRIX.items():
            for module, actions in modules.items():
                for action, allowed in actions.items():
                    rows.append(RolePermission(
                        id=str(uuid.uuid4()), role=role, module=module,
                        action=action, allowed=allowed,
                    ))
        db.bulk_save_objects(rows)
        db.commit()


def _ensure_sod_seeded(db: Session):
    """Seed DEFAULT_SOD_RULES into DB if grc_sod_rules is empty."""
    from app.models.billing_reports import SodRule
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
            for r in DEFAULT_SOD_RULES
        ]
        db.bulk_save_objects(rows)
        db.commit()


# ── Schemas ───────────────────────────────────────────────────────────────────

class PermissionUpdate(BaseModel):
    allowed: bool

class SodRuleIn(BaseModel):
    module_a:    str
    action_a:    str
    module_b:    str
    action_b:    str
    risk:        str = "high"
    description: Optional[str] = None
    roles_conflict: List[str] = []
    mitigated_by_workflow_id: Optional[str] = None

class ViolationResolveIn(BaseModel):
    resolution_note: Optional[str] = None


# ── Permission Matrix ─────────────────────────────────────────────────────────

@router.get("/permissions", summary="Obtener matriz de permisos completa")
def get_permissions(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    from app.models.billing_reports import RolePermission
    _ensure_matrix_seeded(db)
    rows = db.query(RolePermission).all()

    # Build nested dict: role -> module -> action -> allowed
    matrix: dict = {}
    for row in rows:
        matrix.setdefault(row.role, {}).setdefault(row.module, {})[row.action] = row.allowed
    return {"matrix": matrix}


@router.patch("/permissions/{role}/{module}/{action}", summary="Actualizar un permiso")
def update_permission(
    role: str, module: str, action: str,
    body: PermissionUpdate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    from app.models.billing_reports import RolePermission
    _ensure_matrix_seeded(db)
    row = db.query(RolePermission).filter(
        RolePermission.role == role,
        RolePermission.module == module,
        RolePermission.action == action,
    ).first()

    old_val = None
    if row:
        old_val = row.allowed
        row.allowed = body.allowed
        row.updated_by = current_user.id
    else:
        row = RolePermission(
            id=str(uuid.uuid4()), role=role, module=module, action=action,
            allowed=body.allowed, updated_by=current_user.id,
        )
        db.add(row)

    _log_grc(db, current_user.id, "permission_changed", "role_permission",
             f"{role}/{module}/{action}",
             {"old": old_val, "new": body.allowed, "role": role, "module": module, "action": action},
             ip=request.client.host if request.client else None,
             severity="warning")
    db.commit()
    return {"role": role, "module": module, "action": action, "allowed": body.allowed}


@router.post("/permissions/seed", summary="Resetear matriz al estado por defecto")
def seed_permissions(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Borra todos los permisos y los recrea con la matriz por defecto."""
    from app.models.billing_reports import RolePermission
    db.query(RolePermission).delete()
    db.commit()
    _ensure_matrix_seeded(db)
    _log_grc(db, current_user.id, "permission_matrix_reset", severity="critical")
    db.commit()
    return {"ok": True, "message": "Matriz de permisos restaurada a valores por defecto"}


# ── SoD Rules ─────────────────────────────────────────────────────────────────

@router.get("/sod-rules", summary="Listar reglas SoD")
def list_sod_rules(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    from app.models.billing_reports import SodRule
    _ensure_sod_seeded(db)
    rules = db.query(SodRule).order_by(SodRule.risk).all()
    return [_rule_out(r) for r in rules]


def _rule_out(r) -> dict:
    return {
        "id": r.id, "module_a": r.module_a, "action_a": r.action_a,
        "module_b": r.module_b, "action_b": r.action_b,
        "risk": r.risk, "description": r.description,
        "is_active": r.is_active,
        "roles_conflict": json.loads(r.roles_conflict or "[]"),
        "mitigated_by_workflow_id": r.mitigated_by_workflow_id,
        "created_at": str(r.created_at)[:10] if r.created_at else None,
    }


@router.post("/sod-rules", summary="Crear nueva regla SoD")
def create_sod_rule(
    payload: SodRuleIn,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    from app.models.billing_reports import SodRule
    rule = SodRule(
        id=str(uuid.uuid4()),
        module_a=payload.module_a, action_a=payload.action_a,
        module_b=payload.module_b, action_b=payload.action_b,
        risk=payload.risk, description=payload.description,
        roles_conflict=json.dumps(payload.roles_conflict),
        mitigated_by_workflow_id=payload.mitigated_by_workflow_id or None,
        created_by=current_user.id,
    )
    db.add(rule)
    _log_grc(db, current_user.id, "sod_rule_created", "sod_rule", rule.id,
             payload.model_dump(), ip=request.client.host if request.client else None,
             severity="warning")
    db.commit()
    db.refresh(rule)
    return _rule_out(rule)


@router.patch("/sod-rules/{rule_id}", summary="Actualizar regla SoD")
def update_sod_rule(
    rule_id: str,
    payload: dict = Body(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    from app.models.billing_reports import SodRule
    rule = db.query(SodRule).filter(SodRule.id == rule_id).first()
    if not rule:
        raise HTTPException(404)
    allowed = ["risk", "description", "is_active", "roles_conflict", "mitigated_by_workflow_id"]
    for k, v in payload.items():
        if k in allowed:
            if k == "roles_conflict":
                v = json.dumps(v) if isinstance(v, list) else v
            setattr(rule, k, v)
    db.commit()
    return _rule_out(rule)


@router.delete("/sod-rules/{rule_id}", summary="Eliminar regla SoD")
def delete_sod_rule(
    rule_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    from app.models.billing_reports import SodRule
    rule = db.query(SodRule).filter(SodRule.id == rule_id).first()
    if not rule:
        raise HTTPException(404)
    db.delete(rule)
    db.commit()
    return {"ok": True}


# ── SoD Check ─────────────────────────────────────────────────────────────────

@router.get("/sod-check", summary="Verificar violaciones SoD activas por rol")
def sod_check(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    """
    Para cada regla SoD activa, determina qué roles tienen AMBAS acciones permitidas
    (es decir, tienen el conflicto potencial) y lo devuelve como lista de violaciones.
    """
    from app.models.billing_reports import SodRule, RolePermission
    _ensure_matrix_seeded(db)
    _ensure_sod_seeded(db)

    rules = db.query(SodRule).filter(SodRule.is_active == True).all()
    violations = []
    for rule in rules:
        # Check each role
        for role in ["admin", "pm", "team_lead", "employee", "hr", "client"]:
            perm_a = db.query(RolePermission).filter(
                RolePermission.role == role,
                RolePermission.module == rule.module_a,
                RolePermission.action == rule.action_a,
                RolePermission.allowed == True,
            ).first()
            perm_b = db.query(RolePermission).filter(
                RolePermission.role == role,
                RolePermission.module == rule.module_b,
                RolePermission.action == rule.action_b,
                RolePermission.allowed == True,
            ).first()
            if perm_a and perm_b:
                violations.append({
                    "rule_id": rule.id,
                    "rule_description": rule.description,
                    "module_a": rule.module_a, "action_a": rule.action_a,
                    "module_b": rule.module_b, "action_b": rule.action_b,
                    "risk": rule.risk,
                    "conflicting_role": role,
                    "mitigated": bool(rule.mitigated_by_workflow_id),
                })
    return {"violations": violations, "count": len(violations)}


# ── SoD Violations (runtime) ──────────────────────────────────────────────────

@router.get("/violations", summary="Listar violaciones SoD detectadas")
def list_violations(
    resolved: Optional[bool] = Query(None),
    limit: int = Query(50, le=200),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    from app.models.billing_reports import SodViolation
    q = db.query(SodViolation)
    if resolved is not None:
        q = q.filter(SodViolation.resolved == resolved)
    rows = q.order_by(SodViolation.detected_at.desc()).limit(limit).all()
    return [_violation_out(v) for v in rows]


def _violation_out(v) -> dict:
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


@router.patch("/violations/{violation_id}/resolve", summary="Marcar violación SoD como resuelta")
def resolve_violation(
    violation_id: str,
    payload: ViolationResolveIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    from app.models.billing_reports import SodViolation
    v = db.query(SodViolation).filter(SodViolation.id == violation_id).first()
    if not v:
        raise HTTPException(404)
    v.resolved = True
    v.resolved_at = datetime.now(timezone.utc)
    v.resolution_note = payload.resolution_note
    _log_grc(db, current_user.id, "sod_violation_resolved", "sod_violation", violation_id,
             {"note": payload.resolution_note}, severity="info")
    db.commit()
    return _violation_out(v)


# ── Audit Log ─────────────────────────────────────────────────────────────────

@router.get("/audit-log", summary="Historial de auditoría GRC")
def get_audit_log(
    severity: Optional[str] = Query(None),
    action_type: Optional[str] = Query(None),
    limit: int = Query(100, le=500),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    from app.models.billing_reports import GrcAuditLog
    q = db.query(GrcAuditLog)
    if severity:
        q = q.filter(GrcAuditLog.severity == severity)
    if action_type:
        q = q.filter(GrcAuditLog.action_type == action_type)
    rows = q.order_by(GrcAuditLog.timestamp.desc()).limit(limit).all()
    return [
        {
            "id": e.id,
            "timestamp": str(e.timestamp)[:19] if e.timestamp else None,
            "user_id": e.user_id,
            "user_name": e.actor.full_name if e.actor else None,
            "action_type": e.action_type,
            "resource_type": e.resource_type,
            "resource_id": e.resource_id,
            "detail": json.loads(e.detail) if e.detail else None,
            "ip_address": e.ip_address,
            "severity": e.severity,
        }
        for e in rows
    ]


# ── Utility: check_permission (for internal use by other endpoints) ───────────
def check_permission(db: Session, role: str, module: str, action: str) -> bool:
    """
    Returns True if the given role has permission for (module, action).
    Falls back to DEFAULT_MATRIX if DB has no data yet.
    Used by other API endpoints to enforce GRC.
    """
    from app.models.billing_reports import RolePermission
    row = db.query(RolePermission).filter(
        RolePermission.role == role,
        RolePermission.module == module,
        RolePermission.action == action,
    ).first()
    if row is not None:
        return row.allowed
    # Fallback to default
    return DEFAULT_MATRIX.get(role, {}).get(module, {}).get(action, False)


def record_sod_violation(
    db: Session,
    rule_id: str,
    user_id: Optional[str],
    role: Optional[str],
    context_type: Optional[str],
    context_id: Optional[str],
):
    """
    Records a SoD violation in grc_sod_violations.
    Called from approvals and other enforcement points.
    """
    _record_sod_violation(
        db=db,
        rule_id=rule_id,
        user_id=user_id,
        role=role,
        context_type=context_type,
        context_id=context_id,
    )
