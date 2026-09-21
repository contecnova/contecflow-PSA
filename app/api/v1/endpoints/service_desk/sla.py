"""Service Desk — SLA subdomain router (policies, escalation, holidays, priority matrix, assignment)."""
from fastapi import APIRouter, Depends, Query, Body
from sqlalchemy.orm import Session
from typing import Optional

from app.db.session import get_db
from app.core.deps import get_current_user, require_admin, require_any_manager
from app.core.responses import APIListResponse, APIResponse
from app.models.user import User
from app.core.abac_enforce import enforce_abac
from app.services.service_desk.ticket_ops_service import commit_or_rollback as _commit_or_rollback
from app.schemas.service_desk import SLAPolicyIn, HolidayIn, EscalationRuleIn
from app.services.service_desk.sla_policy_service import (
    list_sla_policies_payload, create_sla_policy_record,
    update_sla_policy_record, deactivate_sla_policy_record,
)
from app.services.service_desk.sla_assignment_service import assign_sla_policy_target, sla_policy_id_from_payload
from app.services.service_desk.holiday_service import list_holidays_payload, create_holiday_record, delete_holiday as delete_holiday_svc
from app.services.service_desk.escalation_service import (
    list_escalation_rules_payload, create_escalation_rule_record,
    update_escalation_rule_record, delete_escalation_rule as delete_escalation_rule_svc,
    run_escalation_rules_job, list_escalation_logs_payload,
)
from app.services.service_desk.metrics_service import priority_matrix_payload

router = APIRouter()


@router.get("/sla-policies", summary="Políticas de SLA")
def get_sla_policies(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    return APIListResponse.ok(items=list_sla_policies_payload(db))


@router.post("/sla-policies", summary="Crear política SLA")
def create_sla_policy(payload: SLAPolicyIn, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    p = create_sla_policy_record(db, payload)
    _commit_or_rollback(db); db.refresh(p)
    return APIResponse.ok(data={"id": p.id, "name": p.name})


@router.patch("/sla-policies/{policy_id}", summary="Actualizar política SLA")
def update_sla_policy(policy_id: str, payload: SLAPolicyIn, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    p = update_sla_policy_record(db, policy_id, payload)
    _commit_or_rollback(db)
    return APIResponse.ok(data={"id": p.id, "name": p.name})


@router.delete("/sla-policies/{policy_id}", summary="Eliminar política SLA")
def delete_sla_policy(policy_id: str, db: Session = Depends(get_db), current_user: User = Depends(require_admin)):
    enforce_abac(db, current_user, "sd_sla_policy", policy_id, action="delete")
    deactivate_sla_policy_record(db, policy_id)
    _commit_or_rollback(db)
    return APIResponse.ok(data={"ok": True})


@router.patch("/sla-policies/assign/client/{client_id}", summary="Asignar política SLA a cliente")
def assign_sla_to_client(client_id: str, payload: dict = Body(...), db: Session = Depends(get_db), _: User = Depends(require_admin)):
    result = assign_sla_policy_target(db, "client", client_id, sla_policy_id_from_payload(payload))
    _commit_or_rollback(db)
    return APIResponse.ok(data=result)


@router.patch("/sla-policies/assign/contract/{contract_id}", summary="Asignar política SLA a contrato")
def assign_sla_to_contract(contract_id: str, payload: dict = Body(...), db: Session = Depends(get_db), _: User = Depends(require_admin)):
    result = assign_sla_policy_target(db, "contract", contract_id, sla_policy_id_from_payload(payload))
    _commit_or_rollback(db)
    return APIResponse.ok(data=result)


@router.get("/sla-holidays", summary="Festivos del calendario SLA")
def list_holidays(year: Optional[int] = None, country: Optional[str] = None, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    return APIListResponse.ok(items=list_holidays_payload(db, year, country))


@router.post("/sla-holidays", summary="Añadir festivo al calendario SLA", status_code=201)
def create_holiday(payload: HolidayIn, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    h = create_holiday_record(db, payload)
    _commit_or_rollback(db)
    return APIResponse.ok(data={"id": h.id})


@router.delete("/sla-holidays/{holiday_id}", summary="Eliminar festivo")
def delete_holiday(holiday_id: str, db: Session = Depends(get_db), current_user: User = Depends(require_admin)):
    enforce_abac(db, current_user, "sd_sla_holiday", holiday_id, action="delete")
    delete_holiday_svc(db, holiday_id)
    _commit_or_rollback(db)
    return APIResponse.ok(data={"ok": True})


@router.get("/escalation-rules", summary="Listar reglas de escalada automática")
def list_escalation_rules(db: Session = Depends(get_db), _: User = Depends(require_any_manager)):
    return APIListResponse.ok(items=list_escalation_rules_payload(db))


@router.post("/escalation-rules", summary="Crear regla de escalada", status_code=201)
def create_escalation_rule(payload: EscalationRuleIn, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    rule = create_escalation_rule_record(db, payload)
    _commit_or_rollback(db); db.refresh(rule)
    return APIResponse.ok(data={"ok": True, "id": rule.id})


@router.patch("/escalation-rules/{rule_id}", summary="Actualizar regla de escalada")
def update_escalation_rule(rule_id: str, payload: EscalationRuleIn, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    update_escalation_rule_record(db, rule_id, payload)
    _commit_or_rollback(db)
    return APIResponse.ok(data={"ok": True})


@router.delete("/escalation-rules/{rule_id}", summary="Eliminar regla de escalada")
def delete_escalation_rule(rule_id: str, db: Session = Depends(get_db), current_user: User = Depends(require_admin)):
    enforce_abac(db, current_user, "sd_escalation_rule", rule_id, action="delete")
    delete_escalation_rule_svc(db, rule_id)
    _commit_or_rollback(db)
    return APIResponse.ok(data={"ok": True})


@router.post("/escalation-rules/run", summary="Ejecutar reglas de escalada (job manual/cron)")
def run_escalation_rules(db: Session = Depends(get_db), _: User = Depends(require_admin)):
    result = run_escalation_rules_job(db)
    _commit_or_rollback(db)
    return APIResponse.ok(data=result)


@router.get("/escalation-rules/logs", summary="Historial de escaladas disparadas")
def get_escalation_logs(ticket_id: Optional[str] = None, limit: int = Query(50, le=200), db: Session = Depends(get_db), _: User = Depends(require_any_manager)):
    return APIListResponse.ok(items=list_escalation_logs_payload(db, ticket_id, limit))


@router.post("/priority-matrix", summary="Calcular prioridad ITIL por urgencia × impacto")
def calculate_priority(payload: dict = Body(...), current_user: User = Depends(get_current_user),
    _rol: User = Depends(require_admin),  # auditoria 2026-09: sus hermanas del fichero usan esa guarda
):
    return APIResponse.ok(data=priority_matrix_payload(payload))
