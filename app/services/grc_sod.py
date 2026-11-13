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
    "contract": "contracts",
    "mcp_action": "mcp",
}


def regla_de_autoaprobacion(db: Session, entity_type: str, organization_id: Optional[str]):
    """La regla SoD «quien pide no aprueba» que aplica a esa entidad en esa empresa, o None.

    Coincide con el nombre de la entidad o con su módulo GRC, misma entidad en
    los dos lados y `aprobar` en el segundo; prefiere `crear` en el primero.
    """
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
