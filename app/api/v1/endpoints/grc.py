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
import json
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Body
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.core.deps import get_current_user, require_admin, require_any_manager
from app.models.user import User
from app.services.grc_sod import record_sod_violation as _record_sod_violation
import app.services.grc_service as grc_svc

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
    grc_svc.log_grc_entry(db, user_id, action_type, resource_type, resource_id, detail, ip, severity)


def _ensure_matrix_seeded(db: Session):
    grc_svc.ensure_matrix_seeded(db, DEFAULT_MATRIX)


def _ensure_sod_seeded(db: Session):
    grc_svc.ensure_sod_seeded(db, DEFAULT_SOD_RULES)


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
    _ensure_matrix_seeded(db)
    rows = grc_svc.get_all_permissions(db)

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
    _ensure_matrix_seeded(db)
    row, old_val = grc_svc.upsert_permission(db, role, module, action, body.allowed, current_user.id)
    _log_grc(db, current_user.id, "permission_changed", "role_permission",
             f"{role}/{module}/{action}",
             {"old": old_val, "new": body.allowed, "role": role, "module": module, "action": action},
             ip=request.client.host if request.client else None,
             severity="warning")
    grc_svc.commit_db(db)
    return {"role": role, "module": module, "action": action, "allowed": body.allowed}


@router.post("/permissions/seed", summary="Resetear matriz al estado por defecto")
def seed_permissions(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Borra todos los permisos y los recrea con la matriz por defecto."""
    grc_svc.reset_permission_matrix(db, DEFAULT_MATRIX)
    _log_grc(db, current_user.id, "permission_matrix_reset", severity="critical")
    grc_svc.commit_db(db)
    return {"ok": True, "message": "Matriz de permisos restaurada a valores por defecto"}


# ── SoD Rules ─────────────────────────────────────────────────────────────────

@router.get("/sod-rules", summary="Listar reglas SoD")
def list_sod_rules(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    _ensure_sod_seeded(db)
    rules = grc_svc.list_sod_rules_db(db)
    return [_rule_out(r) for r in rules]


_rule_out = grc_svc.serialize_sod_rule


@router.post("/sod-rules", summary="Crear nueva regla SoD")
def create_sod_rule(
    payload: SodRuleIn,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    rule = grc_svc.create_sod_rule_db(
        db,
        module_a=payload.module_a, action_a=payload.action_a,
        module_b=payload.module_b, action_b=payload.action_b,
        risk=payload.risk, description=payload.description,
        roles_conflict=payload.roles_conflict,
        mitigated_by_workflow_id=payload.mitigated_by_workflow_id,
        created_by=current_user.id,
    )
    _log_grc(db, current_user.id, "sod_rule_created", "sod_rule", rule.id,
             payload.model_dump(), ip=request.client.host if request.client else None,
             severity="warning")
    grc_svc.commit_db(db)
    db.refresh(rule)
    return _rule_out(rule)


@router.patch("/sod-rules/{rule_id}", summary="Actualizar regla SoD")
def update_sod_rule(
    rule_id: str,
    payload: dict = Body(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    rule = grc_svc.get_sod_rule_or_404(db, rule_id)
    grc_svc.update_sod_rule_db(db, rule, payload)
    return _rule_out(rule)


@router.delete("/sod-rules/{rule_id}", summary="Eliminar regla SoD")
def delete_sod_rule(
    rule_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    rule = grc_svc.get_sod_rule_or_404(db, rule_id)
    grc_svc.delete_sod_rule_db(db, rule)
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
    _ensure_matrix_seeded(db)
    _ensure_sod_seeded(db)

    rules = grc_svc.get_active_sod_rules(db)
    violations = []
    for rule in rules:
        # Check each role
        for role in ["admin", "pm", "team_lead", "employee", "hr", "client"]:
            perm_a = grc_svc.get_role_permission(db, role, rule.module_a, rule.action_a)
            perm_b = grc_svc.get_role_permission(db, role, rule.module_b, rule.action_b)
            if perm_a and perm_a.allowed and perm_b and perm_b.allowed:
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
    rows = grc_svc.list_violations_db(db, resolved, limit)
    return [_violation_out(v) for v in rows]


_violation_out = grc_svc.serialize_violation


@router.patch("/violations/{violation_id}/resolve", summary="Marcar violación SoD como resuelta")
def resolve_violation(
    violation_id: str,
    payload: ViolationResolveIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    v = grc_svc.get_violation_or_404(db, violation_id)
    _log_grc(db, current_user.id, "sod_violation_resolved", "sod_violation", violation_id,
             {"note": payload.resolution_note}, severity="info")
    grc_svc.resolve_violation_db(db, v, payload.resolution_note)
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
    rows = grc_svc.list_audit_log_db(db, severity, action_type, limit)
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
    return grc_svc.check_permission_db(db, role, module, action, DEFAULT_MATRIX)


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
