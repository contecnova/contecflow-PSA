"""Catalogo de disparadores y acciones, validacion de reglas y evaluacion de condiciones.

Parte de `app.services.automations_service` (auditoria 2026-11, #24): se partio por responsabilidad
sin cambiar el codigo. El paquete reexporta todos los nombres.
"""
import json
from typing import Optional
from app.models.automations import ActionType, AutomationRule, TriggerType
from app.core.errores import ErrorDeDominio

from app.services.automations_service._comun import _v


# ═════════════════════════════════════════════════════════════════════════════
# Catalogo
# ═════════════════════════════════════════════════════════════════════════════

_CAMPOS_TAREA = ["status", "old_status", "priority", "assignee_id", "project_id"]
_CAMPOS_TICKET = ["priority", "ticket_type", "support_level", "status", "project_id"]
_CAMPOS_FACTURA = ["total", "status", "client_name", "project_id", "number"]
_CAMPOS_APROBACION = ["entity_type", "status", "workflow_id", "user_id", "project_id"]

#: disparador -> categoria, campos que trae el contexto (para las condiciones)
#: y si sale del barrido periodico en vez de un cambio.
CATALOGO_DISPARADORES: dict[str, dict] = {
    "task_created":              {"category": "tasks", "fields": _CAMPOS_TAREA},
    "task_status_changed":       {"category": "tasks", "fields": _CAMPOS_TAREA},
    "task_assigned":             {"category": "tasks", "fields": _CAMPOS_TAREA},
    "task_completed":            {"category": "tasks", "fields": _CAMPOS_TAREA},
    "task_blocked":              {"category": "tasks", "fields": _CAMPOS_TAREA},
    "task_overdue":              {"category": "tasks", "fields": _CAMPOS_TAREA + ["days_overdue"], "scan": True},
    "task_deadline_approaching": {"category": "tasks", "fields": _CAMPOS_TAREA + ["days_left"], "scan": True},
    "project_created":           {"category": "projects", "fields": ["status"]},
    "project_status_changed":    {"category": "projects", "fields": ["status", "old_status"]},
    "budget_threshold":          {"category": "projects", "fields": ["budget_pct", "project_id"], "scan": True},
    "risk_score_high":           {"category": "projects", "fields": ["risk_score", "status", "project_id"]},
    "sprint_started":            {"category": "sprints", "fields": ["project_id"]},
    "sprint_ended":              {"category": "sprints", "fields": ["project_id"]},
    "timesheet_submitted":       {"category": "time", "fields": ["user_id"]},
    "timesheet_rejected":        {"category": "time", "fields": ["user_id"]},
    "timesheet_not_submitted":   {"category": "time", "fields": ["user_id"], "scan": True},
    "absence_requested":         {"category": "team", "fields": ["user_id"]},
    "absence_approved":          {"category": "team", "fields": ["user_id"]},
    "absence_rejected":          {"category": "team", "fields": ["user_id"]},
    "ticket_created":            {"category": "service_desk", "fields": _CAMPOS_TICKET},
    "ticket_resolved":           {"category": "service_desk", "fields": _CAMPOS_TICKET},
    "ticket_reopened":           {"category": "service_desk", "fields": _CAMPOS_TICKET},
    "ticket_escalated":          {"category": "service_desk", "fields": _CAMPOS_TICKET},
    "ticket_sla_at_risk":        {"category": "service_desk", "fields": _CAMPOS_TICKET},
    "ticket_sla_breached":       {"category": "service_desk", "fields": _CAMPOS_TICKET},
    "expense_submitted":         {"category": "finance", "fields": ["amount", "project_id", "user_id"]},
    "expense_approved":          {"category": "finance", "fields": ["amount", "project_id", "user_id"]},
    "expense_rejected":          {"category": "finance", "fields": ["amount", "project_id", "user_id"]},
    "opportunity_stage_changed": {"category": "finance", "fields": ["stage", "old_stage", "client_name"]},
    # Revisión 2026-11: facturas, aprobaciones y reglas programadas.
    "invoice_sent":              {"category": "finance", "fields": _CAMPOS_FACTURA},
    "invoice_paid":              {"category": "finance", "fields": _CAMPOS_FACTURA},
    "invoice_overdue":           {"category": "finance", "fields": _CAMPOS_FACTURA + ["days_overdue"], "scan": True},
    "approval_requested":        {"category": "approvals", "fields": _CAMPOS_APROBACION},
    "approval_approved":         {"category": "approvals", "fields": _CAMPOS_APROBACION},
    "approval_rejected":         {"category": "approvals", "fields": _CAMPOS_APROBACION},
    "scheduled":                 {"category": "schedule", "fields": ["project_id", "weekday", "hour"],
                                  "schedule": True},
}
assert set(CATALOGO_DISPARADORES) == {t.value for t in TriggerType}

_SEVERIDADES = ["info", "warning", "critical"]
_ROLES = ["admin", "pm", "team_lead", "hr", "employee"]
_ESTADOS_TAREA = ["backlog", "todo", "in_progress", "blocked", "in_review", "done", "cancelled"]
_PRIORIDADES_TAREA = ["critical", "high", "medium", "low"]
_ESTADOS_PROYECTO = ["planning", "active", "on_hold", "completed", "cancelled"]
_ESTADOS_TICKET = ["assigned", "in_progress", "pending_client", "resolved", "closed"]


def _p(key, type_="text", options=None, required=False):
    return {"key": key, "type": type_, "options": options, "required": required}


#: accion -> categoria y parametros (lo que la pantalla pinta y la API valida).
CATALOGO_ACCIONES: dict[str, dict] = {
    "create_alert":          {"category": "notifications",
                              "params": [_p("message", required=True), _p("severity", "select", _SEVERIDADES)]},
    "notify_user":           {"category": "notifications",
                              "params": [_p("message", required=True)],
                              "note": "the event's user (assignee, requester, owner)"},
    "notify_role":           {"category": "notifications",
                              "params": [_p("role", "select", _ROLES, True), _p("message", required=True)]},
    "send_email":            {"category": "notifications",
                              "params": [_p("to"), _p("to_role", "select", _ROLES), _p("subject", required=True),
                                         _p("body")]},
    "call_webhook":          {"category": "integrations",
                              "params": [_p("url", required=True), _p("method", "select", ["POST", "PUT", "PATCH"]),
                                         _p("payload")]},
    "send_slack_message":    {"category": "integrations",
                              "params": [_p("slack_webhook_url"), _p("message", required=True)]},
    "send_teams_message":    {"category": "integrations",
                              "params": [_p("teams_webhook_url"), _p("title"), _p("message", required=True)]},
    "change_task_status":    {"category": "tasks", "params": [_p("status", "select", _ESTADOS_TAREA, True)]},
    "change_task_priority":  {"category": "tasks", "params": [_p("priority", "select", _PRIORIDADES_TAREA, True)]},
    "create_task":           {"category": "tasks",
                              "params": [_p("task_title", required=True),
                                         _p("priority", "select", _PRIORIDADES_TAREA),
                                         _p("due_in_days", "number")]},
    "change_project_status": {"category": "projects", "params": [_p("status", "select", _ESTADOS_PROYECTO, True)]},
    "escalate_ticket":       {"category": "service_desk", "params": [_p("to_level", "select", ["l2", "l3"], True)]},
    "change_ticket_status":  {"category": "service_desk", "params": [_p("status", "select", _ESTADOS_TICKET, True)]},
    # Revisión 2026-11
    "assign":                {"category": "work",
                              "params": [_p("to_user"), _p("to_role", "select", _ROLES)],
                              "note": "the event's task or ticket; with a role, to its least loaded member"},
    "update_field":          {"category": "work",
                              "params": [_p("field", "select", None, True), _p("value", required=True)],
                              "note": "dates accept +N (days from today)"},
    "create_approval":       {"category": "approvals",
                              "params": [_p("entity_type"), _p("summary")],
                              "note": "the workflow is chosen by its conditions, as when someone asks"},
}
#: Alias historicos: se ejecutan, pero no se ofrecen.
_ALIAS = {"send_alert": "create_alert", "send_webhook": "call_webhook"}
_OPERADORES = {"equals", "not_equals", "greater_than", "less_than", "contains"}
_GRUPOS = {"all", "any"}

#: Campos que «actualizar campo» puede tocar: los que no tienen ya su propia
#: acción (estado y prioridad de tarea, estado de ticket y proyecto la tienen).
CAMPOS_ACTUALIZABLES: dict[str, tuple[str, str]] = {
    "task.due_date": ("task", "date"),
    "task.start_date": ("task", "date"),
    "task.estimated_hours": ("task", "number"),
    "task.story_points": ("task", "int"),
    "ticket.priority": ("ticket", "enum"),
    "ticket.support_level": ("ticket", "enum"),
}
CATALOGO_ACCIONES["update_field"]["params"][0]["options"] = sorted(CAMPOS_ACTUALIZABLES)


def catalogo() -> dict:
    return {
        "triggers": [{"type": k, **{c: v for c, v in d.items()}} for k, d in CATALOGO_DISPARADORES.items()],
        "actions": [{"type": k, **d} for k, d in CATALOGO_ACCIONES.items()],
        "operators": sorted(_OPERADORES),
    }


def _faltan(tipo: str, params: dict) -> list[str]:
    defs = CATALOGO_ACCIONES[_ALIAS.get(tipo, tipo)]["params"]
    faltan = [d["key"] for d in defs if d["required"] and not str(params.get(d["key"]) or "").strip()]
    if tipo == "send_email" and not (params.get("to") or params.get("email") or params.get("to_role")):
        faltan.append("to | to_role")
    if tipo == "assign" and not (params.get("to_user") or params.get("to_role")):
        faltan.append("to_user | to_role")
    if tipo == "update_field" and params.get("field") and params["field"] not in CAMPOS_ACTUALIZABLES:
        faltan.append(f"field válido ({', '.join(sorted(CAMPOS_ACTUALIZABLES))})")
    return faltan


def _validar_condicion(c: dict) -> None:
    if not isinstance(c, dict):
        raise ErrorDeDominio(422, "Condición mal formada")
    if "conditions" in c or "match" in c:
        if c.get("match", "all") not in _GRUPOS:
            raise ErrorDeDominio(422, f"Grupo desconocido: {c.get('match')} (all | any)")
        hijas = c.get("conditions")
        # Un grupo vacío no se puede evaluar: no se acepta (antes «sin condición» = siempre).
        if not isinstance(hijas, list) or not hijas:
            raise ErrorDeDominio(422, "Un grupo de condiciones necesita al menos una")
        for h in hijas:
            _validar_condicion(h)
        return
    if not c.get("field"):
        raise ErrorDeDominio(422, "La condicion necesita un campo")
    if c.get("operator", "equals") not in _OPERADORES:
        raise ErrorDeDominio(422, f"Operador desconocido: {c.get('operator')}")


def validar_cron(expr: Optional[str]):
    """El disparador de una expresión cron de cinco campos; 422 si no vale."""
    from apscheduler.triggers.cron import CronTrigger
    try:
        return CronTrigger.from_crontab((expr or "").strip())
    except (ValueError, TypeError) as e:
        raise ErrorDeDominio(422, f"Expresión cron no válida «{expr}»: {e}")


def validar_regla(trigger_type: Optional[str], conditions: Optional[dict], actions: Optional[list],
                  schedule_cron: Optional[str] = None) -> None:
    """422 si la regla nombra algo que el motor no sabe hacer."""
    if trigger_type is not None and trigger_type not in CATALOGO_DISPARADORES:
        raise ErrorDeDominio(422, f"Disparador desconocido: {trigger_type}")
    if trigger_type == "scheduled":
        validar_cron(schedule_cron)
    if conditions:
        _validar_condicion(conditions)
    if actions is not None:
        if not actions:
            raise ErrorDeDominio(422, "La regla necesita al menos una accion")
        for i, a in enumerate(actions, 1):
            tipo = (a or {}).get("type")
            if tipo == "conditional_branch":
                p = a.get("params") or {}
                validar_regla(None, p.get("condition"), (p.get("if_true") or []) + (p.get("if_false") or [])
                              or [{"type": "create_alert", "params": {"message": "-"}}])
                continue
            if _ALIAS.get(tipo, tipo) not in CATALOGO_ACCIONES:
                raise ErrorDeDominio(422, f"Accion {i}: tipo desconocido «{tipo}»")
            faltan = _faltan(tipo, a.get("params") or {})
            if faltan:
                raise ErrorDeDominio(422, f"Accion {i} ({tipo}): falta {', '.join(faltan)}")


def serialize_rule(r: AutomationRule) -> dict:
    return {
        "id": r.id, "name": r.name, "description": r.description,
        "project_id": r.project_id,
        "project_name": r.project.name if r.project else None,
        "is_active": r.is_active, "is_global": r.is_global,
        "trigger_type": _v(r.trigger_type),
        "trigger_conditions": json.loads(r.trigger_conditions) if r.trigger_conditions else None,
        "schedule_cron": r.schedule_cron,
        "next_run_at": r.next_run_at.isoformat() if r.next_run_at else None,
        "actions": json.loads(r.actions) if r.actions else [],
        "run_count": r.run_count or 0,
        "last_run_at": str(r.last_run_at)[:16] if r.last_run_at else None,
        "last_error": r.last_error,
        "created_at": str(r.created_at)[:10] if r.created_at else None,
    }


def check_conditions(conditions: Optional[dict], context: dict) -> bool:
    """Evaluate trigger conditions against context.

    Lo que no se puede evaluar no se cumple: campo ausente, numero que no es
    numero u operador desconocido dan False (antes el operador desconocido
    daba True y la regla saltaba siempre).
    """
    if not conditions:
        return True
    if "conditions" in conditions or "match" in conditions:
        # Grupo (revisión 2026-11). Vacío o mal formado no se cumple.
        hijas = conditions.get("conditions")
        if not isinstance(hijas, list) or not hijas:
            return False
        resultados = (check_conditions(h, context) if isinstance(h, dict) and h else False for h in hijas)
        match = conditions.get("match", "all")
        if match == "all":
            return all(resultados)
        if match == "any":
            return any(resultados)
        return False
    field = conditions.get("field")
    operator = conditions.get("operator", "equals")
    value = conditions.get("value")
    ctx_value = context.get(field)
    if ctx_value is None:
        return False
    if operator == "equals":
        return str(ctx_value) == str(value)
    if operator == "not_equals":
        return str(ctx_value) != str(value)
    if operator in ("greater_than", "less_than"):
        try:
            a, b = float(ctx_value), float(value)
        except (TypeError, ValueError):
            return False
        return a > b if operator == "greater_than" else a < b
    if operator == "contains":
        return str(value).lower() in str(ctx_value).lower()
    return False
assert set(CATALOGO_ACCIONES) | set(_ALIAS) | {"conditional_branch"} == {a.value for a in ActionType}
