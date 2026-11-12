"""Reglas de la organizacion: alta, edicion, borrado, ejecuciones, plantillas y simulacion.

Parte de `app.services.automations_service` (auditoria 2026-11, #24): se partio por responsabilidad
sin cambiar el codigo. El paquete reexporta todos los nombres.
"""
import json
from typing import Optional
from sqlalchemy import or_
from sqlalchemy.orm import Session, joinedload
from app.models.automations import AutomationExecution, AutomationRule
from app.models.project import Project
from app.core.errores import ErrorDeDominio

from app.services.automations_service.catalogo import (
    CATALOGO_ACCIONES,
    CATALOGO_DISPARADORES,
    _ALIAS,
    _faltan,
    serialize_rule,
    validar_cron,
    validar_regla,
)
from app.services.automations_service.acciones import (
    _destinatarios_de_correo,
    _motivo_de_rechazo_ssrf,
    _usuarios_del_rol,
    _webhook_de_la_integracion,
)
from app.services.automations_service.disparo import _encendidas, proxima_ejecucion
from app.services.automations_service._comun import _v


# ── «Probar»: simulacion ────────────────────────────────────────────────────

_EFECTO = {
    "create_alert": "crearía una alerta «{message}»",
    "notify_user": "avisaría en la campana a la persona del evento: «{message}»",
    "notify_role": "avisaría en la campana a {n} usuario(s) con rol {role}",
    "send_email": "enviaría «{subject}» a {n} destinatario(s)",
    "call_webhook": "llamaría a {url}",
    "send_slack_message": "publicaría en Slack: «{message}»",
    "send_teams_message": "publicaría en Teams: «{message}»",
    "change_task_status": "pondría la tarea del evento en {status}",
    "change_task_priority": "pondría la tarea del evento en prioridad {priority}",
    "create_task": "crearía la tarea «{task_title}» en el proyecto del evento",
    "change_project_status": "pondría el proyecto del evento en {status}",
    "escalate_ticket": "escalaría el ticket del evento a {to_level}",
    "change_ticket_status": "pondría el ticket del evento en {status}",
    "assign": "asignaría la tarea o el ticket del evento a {to_user}{to_role}",
    "update_field": "pondría {field} = {value}",
    "create_approval": "abriría una aprobación sobre el registro del evento",
}


def simular(rule: AutomationRule, db: Session) -> dict:
    """Que haria la regla, sin hacerlo: no escribe, no envia, no llama a nadie."""
    org = rule.organization_id
    ctx = {"organization_id": org}
    pasos = []
    for a in json.loads(rule.actions) if rule.actions else []:
        tipo = _ALIAS.get(a.get("type"), a.get("type"))
        params = a.get("params") or {}
        if tipo not in CATALOGO_ACCIONES:
            pasos.append({"action": a.get("type"), "ok": False, "error": "tipo desconocido"})
            continue
        faltan = _faltan(tipo, params)
        if faltan:
            pasos.append({"action": tipo, "ok": False, "error": f"falta {', '.join(faltan)}"})
            continue
        n = 0
        error = None
        if tipo == "notify_role":
            n = len(_usuarios_del_rol(db, params.get("role"), org))
        elif tipo == "send_email":
            n = len(_destinatarios_de_correo(db, params, ctx))
        elif tipo == "call_webhook":
            error = _motivo_de_rechazo_ssrf(params["url"])
        elif tipo in ("send_slack_message", "send_teams_message"):
            from app.models.cab import IntegrationType
            clave = "slack_webhook_url" if tipo == "send_slack_message" else "teams_webhook_url"
            integ = IntegrationType.slack if tipo == "send_slack_message" else IntegrationType.teams
            if not (params.get(clave) or params.get("webhook_url") or _webhook_de_la_integracion(db, integ, ctx)):
                error = "no hay webhook configurado"
        try:
            texto = _EFECTO[tipo].format(n=n, **{k: params.get(k, "") for k in
                                                 ("message", "role", "subject", "url", "status", "priority",
                                                  "task_title", "to_level", "to_user", "to_role",
                                                  "field", "value")})
        except (KeyError, IndexError):
            texto = tipo
        pasos.append({"action": tipo, "ok": error is None, "would": texto, "error": error})
    return {
        "simulated": True,
        "enabled": _encendidas(db, org),
        "trigger_type": _v(rule.trigger_type),
        "scan": bool(CATALOGO_DISPARADORES.get(_v(rule.trigger_type), {}).get("scan")),
        "results": pasos,
    }


def get_automation_templates() -> list:
    """Plantillas: solo disparadores y acciones que el motor sabe hacer."""
    plantillas = [
        {
            "id": "budget_alert",
            "name": "Alerta cuando el presupuesto supera el 85%",
            "description": "Crea una alerta cuando el coste imputado supera el 85% del presupuesto",
            "trigger_type": "budget_threshold",
            "trigger_conditions": {"field": "budget_pct", "operator": "greater_than", "value": "85"},
            "actions": [{"type": "create_alert", "params": {"message": "Presupuesto al 85% — revisar consumo del proyecto", "severity": "warning"}}],
        },
        {
            "id": "task_overdue_notify",
            "name": "Avisar al responsable cuando su tarea vence",
            "trigger_type": "task_overdue",
            "trigger_conditions": None,
            "actions": [{"type": "notify_user", "params": {"message": "Una tarea tuya ha vencido sin completarse"}}],
        },
        {
            "id": "sprint_started_notify",
            "name": "Notificar al equipo cuando empieza un sprint",
            "trigger_type": "sprint_started",
            "trigger_conditions": None,
            "actions": [{"type": "notify_role", "params": {"role": "employee", "message": "Nuevo sprint iniciado — revisa tu backlog"}}],
        },
        {
            "id": "timesheet_reminder",
            "name": "Recordar el parte de horas sin enviar",
            "trigger_type": "timesheet_not_submitted",
            "trigger_conditions": None,
            "actions": [{"type": "notify_user", "params": {"message": "Recuerda enviar tu parte de horas semanal"}}],
        },
        {
            "id": "ticket_p1_escalate",
            "name": "Escalar ticket P1 a L2",
            "trigger_type": "ticket_created",
            "trigger_conditions": {"field": "priority", "operator": "equals", "value": "p1_critical"},
            "actions": [
                {"type": "escalate_ticket", "params": {"to_level": "l2"}},
                {"type": "notify_role", "params": {"role": "admin", "message": "Ticket P1 creado — requiere atención inmediata"}},
            ],
        },
        {
            "id": "expense_pending",
            "name": "Notificar al PM de gasto pendiente de aprobación",
            "trigger_type": "expense_submitted",
            "trigger_conditions": None,
            "actions": [{"type": "notify_role", "params": {"role": "pm", "message": "Gasto enviado pendiente de aprobación"}}],
        },
        {
            "id": "risk_high",
            "name": "Alerta de riesgo de alto impacto",
            "trigger_type": "risk_score_high",
            "trigger_conditions": {"field": "risk_score", "operator": "greater_than", "value": "12"},
            "actions": [{"type": "create_alert", "params": {"message": "Riesgo de alto impacto detectado en el proyecto", "severity": "critical"}}],
        },
    ]
    for p in plantillas:
        validar_regla(p["trigger_type"], p["trigger_conditions"], p["actions"])
    return plantillas


# ── Router-extracted CRUD helpers ─────────────────────────────────────────────

def _de_mi_organizacion(q, current_user):
    if current_user.is_superadmin:
        return q
    return q.filter(AutomationRule.organization_id == current_user.organization_id)


def list_rules_for_user(db: Session, current_user, project_id, is_active):
    q = _de_mi_organizacion(db.query(AutomationRule).options(joinedload(AutomationRule.project)), current_user)
    if project_id:
        q = q.filter(or_(AutomationRule.project_id == project_id, AutomationRule.project_id.is_(None)))
    if is_active is not None:
        q = q.filter(AutomationRule.is_active == is_active)
    return [serialize_rule(r) for r in q.order_by(AutomationRule.created_at.desc()).all()]


def regla_de(db: Session, rule_id: str, current_user) -> AutomationRule:
    """La regla si es de la organizacion de quien pregunta; si no, 404."""
    rule = _de_mi_organizacion(db.query(AutomationRule).filter(AutomationRule.id == rule_id),
                               current_user).first()
    if not rule:
        raise ErrorDeDominio(404, "Regla no encontrada")
    return rule


def _proyecto_de_mi_organizacion(db: Session, project_id: Optional[str], current_user) -> None:
    if not project_id:
        return
    q = db.query(Project.id).filter(Project.id == project_id)
    if not current_user.is_superadmin:
        q = q.filter(Project.organization_id == current_user.organization_id)
    if not q.first():
        raise ErrorDeDominio(422, "Proyecto no encontrado")


def create_rule_db(payload, db: Session, current_user) -> dict:
    validar_regla(payload.trigger_type, payload.trigger_conditions, payload.actions,
                  getattr(payload, "schedule_cron", None))
    _proyecto_de_mi_organizacion(db, payload.project_id, current_user)
    rule = AutomationRule(
        name=payload.name,
        description=payload.description,
        project_id=payload.project_id or None,
        is_global=not payload.project_id,
        is_active=payload.is_active,
        trigger_type=payload.trigger_type,
        trigger_conditions=json.dumps(payload.trigger_conditions) if payload.trigger_conditions else None,
        actions=json.dumps(payload.actions),
        created_by=current_user.id,
        organization_id=current_user.organization_id,
        schedule_cron=(getattr(payload, "schedule_cron", None) or "").strip() or None
        if payload.trigger_type == "scheduled" else None,
    )
    rule.next_run_at = proxima_ejecucion(db, rule)
    db.add(rule)
    db.commit()
    return serialize_rule(regla_de(db, rule.id, current_user))


def update_rule_db(rule_id: str, payload, db: Session, current_user) -> dict:
    rule = regla_de(db, rule_id, current_user)
    data = payload.model_dump(exclude_unset=True)
    tipo_final = data.get("trigger_type") or _v(rule.trigger_type)
    cron_final = data["schedule_cron"] if "schedule_cron" in data else rule.schedule_cron
    validar_regla(data.get("trigger_type"), data.get("trigger_conditions"), data.get("actions"))
    if tipo_final == "scheduled":
        validar_cron(cron_final)
    if "project_id" in data:
        _proyecto_de_mi_organizacion(db, data["project_id"], current_user)
        data["project_id"] = data["project_id"] or None
        data["is_global"] = not data["project_id"]
    if "trigger_conditions" in data:
        data["trigger_conditions"] = json.dumps(data["trigger_conditions"]) if data["trigger_conditions"] else None
    if "actions" in data:
        data["actions"] = json.dumps(data["actions"])
    if "schedule_cron" in data:
        data["schedule_cron"] = (data["schedule_cron"] or "").strip() or None
    for k, v in data.items():
        setattr(rule, k, v)
    if tipo_final != "scheduled":
        rule.schedule_cron = None
    rule.next_run_at = proxima_ejecucion(db, rule)
    db.commit()
    return serialize_rule(regla_de(db, rule_id, current_user))


def delete_rule_db(rule_id: str, db: Session, current_user) -> dict:
    """Borrar borra (con su historial). Pausar es `is_active=False`, y se puede reactivar."""
    rule = regla_de(db, rule_id, current_user)
    db.delete(rule)
    db.commit()
    return {"ok": True, "message": "Regla eliminada correctamente"}


def get_executions_db(rule_id: str, limit: int, db: Session, current_user) -> list:
    rule = regla_de(db, rule_id, current_user)
    executions = db.query(AutomationExecution).filter(
        AutomationExecution.rule_id == rule.id
    ).order_by(AutomationExecution.executed_at.desc()).limit(limit).all()
    return [
        {
            "id": e.id,
            "trigger_context": json.loads(e.trigger_context) if e.trigger_context else None,
            "actions_taken": json.loads(e.actions_taken) if e.actions_taken else None,
            "success": e.success,
            "error": e.error,
            "executed_at": str(e.executed_at)[:16],
        }
        for e in executions
    ]


def test_rule_by_id(rule_id: str, db: Session, current_user) -> dict:
    return simular(regla_de(db, rule_id, current_user), db)
