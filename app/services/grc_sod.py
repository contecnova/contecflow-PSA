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
    organization_id: Optional[str] = None,
) -> None:
    """Persist an audit trail entry for a detected SoD violation."""
    import json

    entry = GrcAuditLog(
        id=str(uuid.uuid4()),
        organization_id=organization_id,
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
    organization_id: Optional[str] = None,
) -> None:
    """Create a SoD violation record plus its associated audit log entry.

    Revisión GRC 2026-11b: la infracción y su entrada de auditoría se guardan
    con la empresa de la regla (o la indicada). Antes dependían de que la
    sesión tuviera empresa: un trabajo de fondo o un superadministrador las
    dejaba sin empresa y el informe de cumplimiento (que cuenta por empresa)
    no las veía.
    """
    if organization_id is None:
        regla = db.get(SodRule, rule_id)
        organization_id = getattr(regla, "organization_id", None)
    violation = SodViolation(
        id=str(uuid.uuid4()),
        organization_id=organization_id,
        rule_id=rule_id,
        user_id=user_id,
        role=role,
        context_type=context_type,
        context_id=context_id,
    )
    db.add(violation)
    _log_sod_violation_event(db, user_id, rule_id, context_type, context_id, organization_id)


# Revisión GRC 2026-11b. Las solicitudes y las rutas de aprobación directa
# nombran la entidad en singular (`expense`, `leave`, `itsm_change`) y las
# reglas SoD por defecto usan el módulo GRC, que es el segmento de la ruta
# (`expenses`, `absences`, `sd`). Sin esta tabla ninguna regla por defecto
# coincidía y la infracción no se registraba nunca (el 403 sí se daba).
MODULO_GRC_DE_ENTIDAD: dict[str, str] = {
    "expense": "expenses",
    "timesheet": "timesheets",
    "invoice": "invoices",
    "leave": "absences",
    "absence": "absences",
    "change_request": "changes",
    "budget": "budgets",
    "budget_transfer": "budgets",
    "document": "documents",
    "milestone": "milestones",
    "imputation": "imputations",
    "itsm_change": "sd",
    "catalog_request": "sd",     # segunda auditoría 2026-11
    "rollout_plan": "sd",        # segunda auditoría 2026-11
    "contract": "contracts",
    "mcp_action": "mcp",
}


DEFAULT_SOD_RULES = [
    {"module_a":"invoices","action_a":"crear","module_b":"invoices","action_b":"aprobar","risk":"high","description":"Quien crea facturas no debe aprobarlas (riesgo de fraude)","roles_conflict":["pm"]},
    {"module_a":"expenses","action_a":"crear","module_b":"expenses","action_b":"aprobar","risk":"high","description":"Quien registra gastos no debe aprobarlos","roles_conflict":[]},
    {"module_a":"contracts","action_a":"crear","module_b":"contracts","action_b":"aprobar","risk":"high","description":"Quien crea contratos no debe aprobarlos sin supervisión","roles_conflict":["pm"]},
    {"module_a":"resources","action_a":"editar","module_b":"timesheets","action_b":"aprobar","risk":"medium","description":"Gestión de recursos y aprobación de horas puede generar conflicto","roles_conflict":[]},
    {"module_a":"absences","action_a":"editar","module_b":"absences","action_b":"aprobar","risk":"high","description":"Gestión de RRHH y aprobación de ausencias","roles_conflict":["hr"]},
    {"module_a":"settings","action_a":"editar","module_b":"approvals","action_b":"aprobar","risk":"critical","description":"Quien configura el sistema no debe aprobar solicitudes críticas sin doble validación","roles_conflict":["admin"]},
    {"module_a":"timesheets","action_a":"crear","module_b":"timesheets","action_b":"aprobar","risk":"high","description":"El empleado no debe aprobar sus propios timesheets","roles_conflict":["pm","team_lead"]},
    {"module_a":"grc","action_a":"editar","module_b":"approvals","action_b":"aprobar","risk":"critical","description":"Quien modifica la matriz GRC no debe poder auto-aprobar sus propias solicitudes","roles_conflict":["admin"]},
    # Segunda auditoría 2026-11: presupuestos y Service Desk (servicios del
    # catálogo, planes de despliegue de cambios) también bloquean la autoaprobación.
    {"module_a":"budgets","action_a":"crear","module_b":"budgets","action_b":"aprobar","risk":"high","description":"Quien crea un presupuesto no debe aprobarlo","roles_conflict":[]},
    {"module_a":"sd","action_a":"crear","module_b":"sd","action_b":"aprobar","risk":"high","description":"Quien pide un servicio o crea un plan de cambio no debe aprobarlo","roles_conflict":[]},
]


def sembrar_reglas_por_defecto(db: Session, organization_id: Optional[str], commit: bool = True) -> None:
    """Siembra las reglas SoD por defecto en esa empresa si no tiene ninguna. Idempotente.

    Segunda auditoría 2026-11: antes sólo se sembraban al abrir la pestaña SoD,
    así que en una empresa donde nadie la había abierto ninguna autoaprobación
    quedaba registrada (el 403 sí se daba). Se llama al crear la empresa y,
    sin commit, en la primera comprobación de autoaprobación.
    """
    from app.services.grc_service import ensure_sod_seeded
    ensure_sod_seeded(db, DEFAULT_SOD_RULES, organization_id, commit=commit)


def regla_de_autoaprobacion(db: Session, entity_type: str, organization_id: Optional[str]):
    """La regla SoD «quien pide no aprueba» que aplica a esa entidad en esa empresa, o None.

    Coincide con el nombre de la entidad o con su módulo GRC, misma entidad en
    los dos lados y `aprobar` en el segundo; prefiere `crear` en el primero.
    """
    if organization_id:
        sembrar_reglas_por_defecto(db, organization_id, commit=False)
    candidatos = {entity_type, MODULO_GRC_DE_ENTIDAD.get(entity_type, entity_type)}
    q = db.query(SodRule).filter(
        SodRule.module_a.in_(candidatos),
        SodRule.module_b == SodRule.module_a,
        SodRule.action_b == "aprobar",
        SodRule.is_active == True,  # noqa: E712
    )
    if organization_id:
        from app.db.session import sin_filtro_de_tenant
        with sin_filtro_de_tenant(db):   # la empresa se nombra explícitamente
            reglas = q.filter(SodRule.organization_id == organization_id).all()
    else:
        reglas = q.all()
    return next((r for r in reglas if r.action_a == "crear"), reglas[0] if reglas else None)


def record_self_approval_violation_for_request(
    db: Session,
    entity_type: str,
    request_id: str,
    requested_by: str,
    actor_id: str,
    actor_role: Optional[str],
    organization_id: Optional[str] = None,
    context_type: str = "approval_request",
) -> bool:
    """
    Detect and record SoD violation when request creator tries to self-approve.

    Returns True when the violation condition is met, otherwise False. No hace
    commit. Es el único sitio que registra la autoaprobación: lo usan la bandeja
    de aprobaciones (`approval_engine._record_sod_violation`) y las rutas de
    aprobación directa (`approval_engine.exigir_que_no_sea_suyo`).
    """
    if not requested_by or requested_by != actor_id:
        return False

    matching = regla_de_autoaprobacion(db, entity_type, organization_id)
    if matching:
        record_sod_violation(
            db=db,
            rule_id=matching.id,
            user_id=actor_id,
            role=actor_role,
            context_type=context_type,
            context_id=request_id,
            organization_id=organization_id or matching.organization_id,
        )

    return True
