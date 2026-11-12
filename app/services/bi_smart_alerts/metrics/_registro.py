"""El registro de resolutores (clave -> serie), la entrada `serie_con_meses` y las series que se derivan de otras metricas.

Parte de `app.services.bi_smart_alerts.metrics` (auditoria 2026-11, #24): se partio por responsabilidad
sin cambiar el codigo. El paquete reexporta todos los nombres.
"""
from __future__ import annotations

from typing import Callable, Optional
from sqlalchemy.orm import Session
from app.services.bi_smart_alerts.constants import CUSTOM_METRICS_KEY
from app.services.bi_smart_alerts.persistence import _get_json

from app.services.bi_smart_alerts.metrics.finanzas import (
    COST_PROFILE_KEYS,
    _serie_budget_used_pct,
    _serie_cost,
    _serie_cost_profile,
    _serie_expense,
    _serie_invoice,
    _serie_margin,
    _serie_margin_pct,
    _serie_revenue,
)
from app.services.bi_smart_alerts.metrics._contexto import _Ctx, _construir_contexto, logger
from app.services.bi_smart_alerts.metrics.recursos import (
    _serie_absence,
    _serie_avg_user_load_pct,
    _serie_certified_users_count,
    _serie_hours_billable,
    _serie_hours_logged,
    _serie_imputations_approved_hours,
    _serie_overloaded_users,
    _serie_pending_timesheets,
    _serie_resource_alerts,
    _serie_snapshot_billable_pct,
    _serie_users_at_capacity,
    _serie_users_underutilized,
    _serie_utilization,
)
from app.services.bi_smart_alerts.metrics.proyectos import (
    _serie_active_projects,
    _serie_change_requests,
    _serie_deliverables,
    _serie_milestones,
    _serie_projects_at_risk,
    _serie_projects_cancelled,
    _serie_projects_completed_count,
    _serie_projects_on_hold,
    _serie_projects_over_budget,
    _serie_projects_overdue,
    _serie_tasks_blocked,
    _serie_tasks_completed,
    _serie_tasks_created,
    _serie_tasks_overdue,
)
from app.services.bi_smart_alerts.metrics.itsm import (
    _serie_assets_total,
    _serie_escalations_total,
    _serie_itsm_changes,
    _serie_kb,
    _serie_known_errors_active,
    _serie_major_incidents_active,
    _serie_problems_open,
    _serie_sla_breach_count,
    _serie_sla_compliance_pct,
    _serie_ticket_time_log_total,
    _serie_tickets_open,
)
from app.services.bi_smart_alerts.metrics.gobierno import (
    _serie_grc,
    _serie_imports,
    _serie_pending_approvals,
    _serie_playbook,
    _serie_sod_violations,
    _serie_workflow,
)


# ═════════════════════════════════════════════════════════════════════════════
# Resolutores. Uno por metrica o por grupo de metricas que comparten consulta.
# El cuerpo de cada uno viene VERBATIM de la funcion original.
# ═════════════════════════════════════════════════════════════════════════════

def _serie_custom(ctx: _Ctx) -> Optional[list[float]]:
    """Metricas compuestas definidas por el cliente (prefijo `custom_`)."""
    _empty_like, db, metric_key, organization_id = ctx.empty_like, ctx.db, ctx.key, ctx.org_id
    if metric_key.startswith("custom_"):
        customs = _get_json(db, CUSTOM_METRICS_KEY, organization_id, default=[])
        cm = next((c for c in customs if c.get("key") == metric_key), None)
        if not cm:
            return _empty_like()
        f = cm.get("formula", {})
        a_s = _fetch_metric_series(db, f.get("operand_a", ""), organization_id)
        op = f.get("operator", "+")
        b_s = (_fetch_metric_series(db, f.get("operand_b", ""), organization_id)
               if f.get("operand_b_type") == "metric"
               else [float(f.get("operand_b", 0) or 0)] * len(a_s))
        scale = float(f.get("scale", 1) or 1)
        result = []
        for a, b in zip(a_s, b_s):  # noqa: B905
            try:
                v = {"+": a+b, "-": a-b, "*": a*b, "/": a/b if b else 0.0}.get(op, a)
            except Exception:
                logger.debug("Custom metric %s arithmetic failed (op=%s a=%s b=%s)", metric_key, op, a, b, exc_info=True)
                v = 0.0
            result.append(round(v * scale, 4))
        return result

def _serie_billable_pct(ctx: _Ctx) -> Optional[list[float]]:
    """Metrica `billable_pct`."""
    db, metric_key, organization_id = ctx.db, ctx.key, ctx.org_id
    if metric_key == "billable_pct":
        t = _fetch_metric_series(db, "hours_logged", organization_id)
        b = _fetch_metric_series(db, "hours_billable", organization_id)
        return [round(bv/tv*100,2) if tv > 0 else 0.0 for tv,bv in zip(t,b)]  # noqa: B905

def _serie_task_completion_rate(ctx: _Ctx) -> Optional[list[float]]:
    """Metrica `task_completion_rate`."""
    db, metric_key, organization_id = ctx.db, ctx.key, ctx.org_id
    if metric_key == "task_completion_rate":
        c = _fetch_metric_series(db, "tasks_completed", organization_id)
        o = _fetch_metric_series(db, "tasks_overdue", organization_id)
        return [round(cv/(cv+ov)*100,2) if (cv+ov) > 0 else 0.0 for cv,ov in zip(c,o)]  # noqa: B905

# ═════════════════════════════════════════════════════════════════════════════
# Tabla de despacho
# ═════════════════════════════════════════════════════════════════════════════

_Resolutor = Callable[[_Ctx], Optional[list[float]]]

# Clave exacta → resolutor. Es la tabla que antes era una cadena de 55 `if`.
_RESOLUTORES: dict[str, _Resolutor] = {
    "revenue": _serie_revenue,
    "cost": _serie_cost,
    "margin": _serie_margin,
    "margin_pct": _serie_margin_pct,
    "budget_used_pct": _serie_budget_used_pct,
    "invoice_days_to_pay_avg": _serie_invoice,
    "invoice_overdue_amount": _serie_invoice,
    "invoice_overdue_count": _serie_invoice,
    "invoices_draft_count": _serie_invoice,
    "invoices_paid_count": _serie_invoice,
    "invoices_paid_total": _serie_invoice,
    "invoices_sent_count": _serie_invoice,
    "expense_total": _serie_expense,
    "expenses_approved_count": _serie_expense,
    "expenses_draft_count": _serie_expense,
    "expenses_hardware": _serie_expense,
    "expenses_rejected_count": _serie_expense,
    "expenses_software": _serie_expense,
    "expenses_subcontract": _serie_expense,
    "expenses_submitted_count": _serie_expense,
    "expenses_training_exp": _serie_expense,
    "expenses_travel": _serie_expense,
    "hourly_rate_avg": _serie_imputations_approved_hours,
    "imputations_approved_hours": _serie_imputations_approved_hours,
    "imputations_cost_total": _serie_imputations_approved_hours,
    "imputations_invoiced_count": _serie_imputations_approved_hours,
    "hours_logged": _serie_hours_logged,
    "hours_billable": _serie_hours_billable,
    "billable_pct": _serie_billable_pct,
    "utilization": _serie_utilization,
    "overloaded_users": _serie_overloaded_users,
    "avg_user_load_pct": _serie_avg_user_load_pct,
    "users_at_capacity": _serie_users_at_capacity,
    "users_underutilized": _serie_users_underutilized,
    "snapshot_billable_pct": _serie_snapshot_billable_pct,
    "pending_timesheets": _serie_pending_timesheets,
    "timesheet_avg_hours": _serie_pending_timesheets,
    "timesheet_cost_total": _serie_pending_timesheets,
    "timesheets_draft_count": _serie_pending_timesheets,
    "timesheets_rejected_count": _serie_pending_timesheets,
    "timesheets_submitted_count": _serie_pending_timesheets,
    "absence_days": _serie_absence,
    "absence_pending_count": _serie_absence,
    "absence_sick_days": _serie_absence,
    "absence_training_days": _serie_absence,
    "absence_vacation_days": _serie_absence,
    "certified_users_count": _serie_certified_users_count,
    "resource_alerts_overload": _serie_resource_alerts,
    "resource_alerts_skill_gap": _serie_resource_alerts,
    "active_projects": _serie_active_projects,
    "projects_at_risk": _serie_projects_at_risk,
    "projects_over_budget": _serie_projects_over_budget,
    "projects_overdue": _serie_projects_overdue,
    "projects_on_hold": _serie_projects_on_hold,
    "projects_cancelled": _serie_projects_cancelled,
    "projects_completed_count": _serie_projects_completed_count,
    "milestones_completed": _serie_milestones,
    "milestones_invoiced": _serie_milestones,
    "milestones_overdue": _serie_milestones,
    "milestones_pending": _serie_milestones,
    "milestones_pending_approval": _serie_milestones,
    "deliverables_accepted": _serie_deliverables,
    "deliverables_in_progress": _serie_deliverables,
    "deliverables_in_review": _serie_deliverables,
    "deliverables_rejected": _serie_deliverables,
    "change_requests_cost_impact": _serie_change_requests,
    "change_requests_pending": _serie_change_requests,
    "change_requests_schedule": _serie_change_requests,
    "change_requests_total": _serie_change_requests,
    "tasks_overdue": _serie_tasks_overdue,
    "tasks_blocked": _serie_tasks_blocked,
    "tasks_created": _serie_tasks_created,
    "tasks_completed": _serie_tasks_completed,
    "task_completion_rate": _serie_task_completion_rate,
    "auto_resolved_count": _serie_tickets_open,
    "csat_avg": _serie_tickets_open,
    "first_response_time_avg": _serie_tickets_open,
    "resolution_time_avg": _serie_tickets_open,
    "sla_resolution_breached": _serie_tickets_open,
    "sla_response_breached": _serie_tickets_open,
    "ticket_time_spent_total": _serie_tickets_open,
    "tickets_created": _serie_tickets_open,
    "tickets_open": _serie_tickets_open,
    "tickets_p1_count": _serie_tickets_open,
    "tickets_p2_count": _serie_tickets_open,
    "tickets_resolved": _serie_tickets_open,
    "ticket_time_log_total": _serie_ticket_time_log_total,
    "sla_breach_count": _serie_sla_breach_count,
    "sla_compliance_pct": _serie_sla_compliance_pct,
    "kb_articles_published": _serie_kb,
    "kb_helpful_count": _serie_kb,
    "kb_views_total": _serie_kb,
    "problems_open": _serie_problems_open,
    "known_errors_active": _serie_known_errors_active,
    "itsm_changes_downtime": _serie_itsm_changes,
    "itsm_changes_emergency": _serie_itsm_changes,
    "itsm_changes_total": _serie_itsm_changes,
    "asset_value_total": _serie_assets_total,
    "assets_deployed": _serie_assets_total,
    "assets_in_repair": _serie_assets_total,
    "assets_total": _serie_assets_total,
    "license_seats_total": _serie_assets_total,
    "license_used_total": _serie_assets_total,
    "major_incidents_active": _serie_major_incidents_active,
    "escalations_total": _serie_escalations_total,
    "playbook_failure_count": _serie_playbook,
    "playbook_success_count": _serie_playbook,
    "approvals_approved_count": _serie_pending_approvals,
    "approvals_rejected_count": _serie_pending_approvals,
    "pending_approvals": _serie_pending_approvals,
    "workflow_error_total": _serie_workflow,
    "workflow_runs_total": _serie_workflow,
    "workflow_success_total": _serie_workflow,
    "sod_violations_total": _serie_sod_violations,
    "sod_violations_unresolved": _serie_sod_violations,
    "grc_audit_events_total": _serie_grc,
    "grc_critical_events": _serie_grc,
    "imports_completed_count": _serie_imports,
    "imports_failed_count": _serie_imports,
    "imports_success_rate": _serie_imports,
}

# Las metricas del perfil de coste comparten una consulta pesada, asi que se
# registran en bloque desde su propio conjunto de claves.
_RESOLUTORES.update({_k: _serie_cost_profile for _k in COST_PROFILE_KEYS})

# Resolutores por PREFIJO, para las metricas que el cliente define y cuyo nombre
# exacto no se puede conocer de antemano.
_POR_PREFIJO: tuple[tuple[str, _Resolutor], ...] = (
    ("custom_", _serie_custom),
)


def claves_atendidas() -> frozenset[str]:
    """Claves exactas que este modulo sabe resolver.

    Existe para que un test pueda comprobar que el catalogo (`SUPPORTED_METRICS`)
    y el codigo no se separan. Antes no habia forma de saberlo: las claves estaban
    incrustadas en 55 condiciones y una metrica anadida al catalogo sin
    implementar devolvia ceros en silencio.
    """
    return frozenset(_RESOLUTORES)


def _resolutor_para(metric_key: str) -> Optional[_Resolutor]:
    directo = _RESOLUTORES.get(metric_key)
    if directo is not None:
        return directo
    for prefijo, fn in _POR_PREFIJO:
        if metric_key.startswith(prefijo):
            return fn
    return None


def _fetch_metric_series(
    db: Session, metric_key: str, organization_id: Optional[str]
) -> list[float]:
    """Serie de los ultimos 24 meses de la metrica pedida.

    Una clave desconocida devuelve una serie a cero en vez de lanzar: una regla
    de alerta guardada con una metrica que despues se retiro no puede tumbar el
    motor entero.
    """
    return serie_con_meses(db, metric_key, organization_id)[0]


def serie_con_meses(
    db: Session, metric_key: str, organization_id: Optional[str]
) -> tuple[list[float], list[str]]:
    """La serie y el mes (`YYYY-MM`) de cada punto, para poder decir cuando."""
    ctx = _construir_contexto(db, metric_key, organization_id)
    meses = [m["month"] for m in ctx.series]

    resolutor = _resolutor_para(metric_key)
    if resolutor is None:
        return ctx.empty_like(), meses

    resultado = resolutor(ctx)
    # Un resolutor puede devolver None si su propia condicion no se cumple (los
    # grupos discriminan dentro). Se trata igual que «sin dato».
    return (resultado if resultado is not None else ctx.empty_like()), meses
