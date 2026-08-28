"""
Automations service — business logic extracted from automations.py router.
"""
import logging
from typing import Optional
from datetime import date, datetime, timedelta, timezone
from sqlalchemy.orm import Session
import json

logger = logging.getLogger(__name__)

from app.models.automations import AutomationRule, AutomationExecution, ActionType
from app.core.outbound_url import validate_outbound_url
from app.models.alert import Alert, AlertType, AlertSeverity
from app.services.alert_service import derive_alert_org_id
from app.models.task import Task
from app.models.user import User
from app.models.financial import Timesheet
from app.models.project import Project
from fastapi import HTTPException
from sqlalchemy import or_
from sqlalchemy.orm import joinedload


def serialize_rule(r: AutomationRule) -> dict:
    return {
        "id": r.id, "name": r.name, "description": r.description,
        "project_id": r.project_id,
        "project_name": r.project.name if r.project else None,
        "is_active": r.is_active, "is_global": r.is_global,
        "trigger_type": r.trigger_type,
        "trigger_conditions": json.loads(r.trigger_conditions) if r.trigger_conditions else None,
        "actions": json.loads(r.actions) if r.actions else [],
        "run_count": r.run_count or 0,
        "last_run_at": str(r.last_run_at)[:16] if r.last_run_at else None,
        "last_error": r.last_error,
        "created_at": str(r.created_at)[:10] if r.created_at else None,
    }


def check_conditions(conditions: Optional[dict], context: dict) -> bool:
    """Evaluate trigger conditions against context."""
    if not conditions:
        return True
    field = conditions.get("field")
    operator = conditions.get("operator", "equals")
    value = conditions.get("value")
    ctx_value = context.get(field)
    if ctx_value is None:
        return False
    if operator == "equals":
        return str(ctx_value) == str(value)
    elif operator == "not_equals":
        return str(ctx_value) != str(value)
    elif operator == "greater_than":
        try:
            return float(ctx_value) > float(value)
        except Exception:
            logger.debug("Automation condition greater_than eval failed (ctx=%r value=%r)", ctx_value, value, exc_info=True)
            return False
    elif operator == "less_than":
        try:
            return float(ctx_value) < float(value)
        except Exception:
            logger.debug("Automation condition less_than eval failed (ctx=%r value=%r)", ctx_value, value, exc_info=True)
            return False
    elif operator == "contains":
        return str(value).lower() in str(ctx_value).lower()
    return True


def execute_actions(actions: list, context: dict, db: Session) -> list:
    """Execute the list of actions for a triggered rule."""
    results = []
    for action in actions:
        atype = action.get("type")
        params = action.get("params", {})
        try:
            if atype == ActionType.create_alert or atype == ActionType.send_alert:
                alert = Alert(
                    alert_type=AlertType.budget_exceeded,
                    title=params.get("title", "Automatización activada"),
                    description=params.get("message", action.get("message", "")),
                    severity=AlertSeverity.warning if params.get("severity") == "warning" else AlertSeverity.info,
                    # Sin organization_id la alerta cae en el fallback "visible para
                    # todas las organizaciones" de _scope_alert_to_org, y una regla
                    # global sin project_id en contexto la dejaba ahí.
                    organization_id=derive_alert_org_id(
                        db, project_id=context.get("project_id"), task_id=context.get("task_id"),
                    ),
                    project_id=context.get("project_id"),
                    task_id=context.get("task_id"),
                )
                db.add(alert)
                results.append({"action": atype, "ok": True})

            elif atype == ActionType.change_task_status:
                task_id = context.get("task_id") or params.get("task_id")
                if task_id:
                    task = db.query(Task).filter(Task.id == task_id).first()
                    if task:
                        task.status = params.get("status", task.status)
                        results.append({"action": atype, "ok": True, "task": task.code})

            elif atype == ActionType.notify_role:
                role = params.get("role", "pm")
                message = params.get("message", "Notificación de automatización")
                users = db.query(User).filter(User.role == role, User.is_active == True).all()
                for u in users:
                    alert = Alert(
                        alert_type=AlertType.no_imputation,
                        title=message,
                        description=params.get("description", ""),
                        severity=AlertSeverity.info,
                        organization_id=derive_alert_org_id(
                            db, user_id=u.id, project_id=context.get("project_id"),
                        ),
                        project_id=context.get("project_id"),
                        user_id=u.id,
                    )
                    db.add(alert)
                results.append({"action": atype, "ok": True, "notified": len(users)})

            elif atype == ActionType.notify_user:
                user_id = params.get("user_id") or context.get("user_id")
                if user_id:
                    alert = Alert(
                        alert_type=AlertType.no_imputation,
                        title=params.get("message", "Tienes una notificación automática"),
                        description=params.get("description", ""),
                        severity=AlertSeverity.info,
                        organization_id=derive_alert_org_id(
                            db, user_id=user_id, project_id=context.get("project_id"),
                        ),
                        project_id=context.get("project_id"),
                        user_id=user_id,
                    )
                    db.add(alert)
                    results.append({"action": atype, "ok": True})

            elif atype == ActionType.send_email:
                to_addr = params.get("to") or params.get("email")
                subject = params.get("subject", "Notificación automática — Contecflow")
                body    = params.get("body") or params.get("message", "")
                if to_addr:
                    try:
                        from app.services.notification_service import send_email_notification
                        send_email_notification(to=to_addr, subject=subject, body=body)
                        results.append({"action": atype, "ok": True, "to": to_addr})
                    except Exception as email_err:
                        logger.exception("Automation send_email action failed for to=%s", to_addr)
                        results.append({"action": atype, "ok": False, "error": str(email_err)})
                else:
                    results.append({"action": atype, "ok": False, "error": "Missing 'to' parameter"})

            elif atype == ActionType.call_webhook:
                url    = params.get("url")
                method = params.get("method", "POST").upper()
                headers = params.get("headers", {})
                payload = params.get("payload") or {
                    "event": context.get("event_type", "automation"),
                    "rule_id": context.get("rule_id"),
                    "project_id": context.get("project_id"),
                    "task_id": context.get("task_id"),
                }
                if url:
                    # SSRF protection: only allow HTTPS to public hosts
                    import ipaddress
                    from urllib.parse import urlparse
                    import socket as _socket
                    _ssrf_err = None
                    try:
                        _parsed = urlparse(url)
                        if _parsed.scheme != "https":
                            raise ValueError("Solo se permiten URLs HTTPS para webhooks")
                        _host = _parsed.hostname or ""
                        try:
                            _ip = ipaddress.ip_address(_host)
                            if _ip.is_private or _ip.is_loopback or _ip.is_link_local or _ip.is_reserved:
                                raise ValueError("El webhook apunta a una dirección IP privada/interna")
                        except ValueError as _ve:
                            if "Solo se permiten" in str(_ve) or "dirección IP" in str(_ve):
                                raise
                            try:
                                _resolved = _socket.getaddrinfo(_host, None)
                                for _r in _resolved:
                                    _rip = ipaddress.ip_address(_r[4][0])
                                    if _rip.is_private or _rip.is_loopback or _rip.is_link_local:
                                        raise ValueError("El webhook resuelve a una dirección IP interna")
                            except ValueError:
                                raise
                            except Exception:
                                logger.warning("Fallo resolviendo getaddrinfo para webhook host=%s en SSRF check", _host)
                    except ValueError as ssrf_e:
                        _ssrf_err = str(ssrf_e)
                    if _ssrf_err:
                        results.append({"action": atype, "ok": False, "error": _ssrf_err})
                    else:
                        import urllib.request as _ur
                        import json as _json
                        _data = _json.dumps(payload).encode()
                        _req  = _ur.Request(validate_outbound_url(url, field="URL de webhook"), data=_data, method=method,  # noqa: S310
                                            headers={"Content-Type": "application/json", **headers})
                        try:
                            with _ur.urlopen(_req, timeout=10):  # noqa: S310
                                pass
                            results.append({"action": atype, "ok": True, "url": url})
                        except Exception as wh_err:
                            logger.exception("Automation webhook POST failed url=%s", url)
                            results.append({"action": atype, "ok": False, "error": str(wh_err)})
                else:
                    results.append({"action": atype, "ok": False, "error": "Missing 'url' parameter"})

            elif atype == ActionType.send_slack_message:
                webhook_url = params.get("webhook_url")
                message     = params.get("message", "Notificación automática de Contecflow")
                if webhook_url:
                    from app.services.integrations import send_slack_message
                    res = send_slack_message(webhook_url, message)
                    results.append({"action": atype, "ok": res.get("ok", False),
                                    "error": res.get("error") if not res.get("ok") else None})
                else:
                    from app.models.cab import IntegrationConfig, IntegrationType
                    cfg = db.query(IntegrationConfig).filter(
                        IntegrationConfig.integration_type == IntegrationType.slack,
                        IntegrationConfig.is_active == True,
                    ).first()
                    if cfg:
                        import json as _j
                        config_data = _j.loads(cfg.config or "{}")
                        wh = config_data.get("webhook_url")
                        if wh:
                            from app.services.integrations import send_slack_message
                            res = send_slack_message(wh, message)
                            results.append({"action": atype, "ok": res.get("ok", False)})
                            continue
                    results.append({"action": atype, "ok": False, "error": "No Slack webhook_url configured"})

            elif atype == ActionType.send_teams_message:
                webhook_url = params.get("webhook_url")
                title   = params.get("title", "Contecflow — Automatización")
                message = params.get("message", "")
                if webhook_url:
                    from app.services.integrations import send_teams_message
                    res = send_teams_message(webhook_url, title, message)
                    results.append({"action": atype, "ok": res.get("ok", False)})
                else:
                    from app.models.cab import IntegrationConfig, IntegrationType
                    cfg = db.query(IntegrationConfig).filter(
                        IntegrationConfig.integration_type == IntegrationType.teams,
                        IntegrationConfig.is_active == True,
                    ).first()
                    if cfg:
                        import json as _j
                        config_data = _j.loads(cfg.config or "{}")
                        wh = config_data.get("webhook_url")
                        if wh:
                            from app.services.integrations import send_teams_message
                            res = send_teams_message(wh, title, message)
                            results.append({"action": atype, "ok": res.get("ok", False)})
                            continue
                    results.append({"action": atype, "ok": False, "error": "No Teams webhook_url configured"})

            elif atype == ActionType.wait_step:
                delay_hours = params.get("delay_hours", 0)
                label = params.get("label", f"Esperar {delay_hours}h")
                results.append({"action": atype, "ok": True, "label": label,
                                "delay_hours": delay_hours, "status": "logged"})

            elif atype == ActionType.conditional_branch:
                condition = params.get("condition", {})
                if_true_actions = params.get("if_true", [])
                if_false_actions = params.get("if_false", [])
                branch_result = check_conditions(condition, context)
                branch_actions = if_true_actions if branch_result else if_false_actions
                branch_label = "if_true" if branch_result else "if_false"
                if branch_actions:
                    branch_results = execute_actions(branch_actions, context, db)
                    results.append({"action": atype, "ok": True,
                                    "branch_taken": branch_label, "branch_results": branch_results})
                else:
                    results.append({"action": atype, "ok": True,
                                    "branch_taken": branch_label, "branch_results": []})

        except Exception as e:
            logger.exception("Automation action %s execution failed", atype)
            results.append({"action": atype, "ok": False, "error": str(e)})

    return results


def fire_trigger(trigger_type: str, context: dict, db: Session):
    """Called from other endpoints when an event occurs. Evaluates all matching rules."""
    rules = db.query(AutomationRule).filter(
        AutomationRule.trigger_type == trigger_type,
        AutomationRule.is_active == True,
    ).all()

    for rule in rules:
        if rule.project_id and rule.project_id != context.get("project_id"):
            continue

        conditions = json.loads(rule.trigger_conditions) if rule.trigger_conditions else None
        if not check_conditions(conditions, context):
            continue

        actions = json.loads(rule.actions) if rule.actions else []
        results = execute_actions(actions, context, db)
        success = all(r.get("ok", True) for r in results)

        db.add(AutomationExecution(
            rule_id=rule.id,
            trigger_context=json.dumps(context),
            actions_taken=json.dumps(results),
            success=success,
        ))
        rule.run_count = (rule.run_count or 0) + 1
        rule.last_run_at = datetime.now(timezone.utc)
        if not success:
            rule.last_error = str(results)

    db.commit()


def run_scheduled_automations(db: Session) -> dict:
    """Execute scheduled automations (timesheet reminders, overdue tasks)."""

    results = {"executed": 0, "errors": 0}
    today = date.today()

    if today.weekday() == 4:  # Friday
        week_start = today - timedelta(days=4)
        users_no_ts = db.query(User).filter(User.is_active == True).all()
        for u in users_no_ts:
            ts = db.query(Timesheet).filter(
                Timesheet.user_id == u.id, Timesheet.week_start == week_start
            ).first()
            if not ts or ts.status == "draft":
                fire_trigger("timesheet_not_submitted", {"user_id": u.id, "week_start": str(week_start)}, db)
                results["executed"] += 1

    overdue_tasks = db.query(Task).filter(
        Task.due_date < today,
        Task.status.notin_(["done", "cancelled"]),
    ).all()
    for task in overdue_tasks:
        fire_trigger("task_overdue", {
            "task_id": task.id, "project_id": task.project_id,
            "days_overdue": (today - task.due_date).days
        }, db)
        results["executed"] += 1

    return results


def test_automation_rule(rule: AutomationRule, user_id: str, db: Session) -> dict:
    """Execute a rule's actions with a test context."""
    actions = json.loads(rule.actions) if rule.actions else []
    context = {"project_id": rule.project_id, "manual_test": True, "user_id": user_id}
    results = execute_actions(actions, context, db)
    db.add(AutomationExecution(
        rule_id=rule.id,
        trigger_context=json.dumps({"test": True}),
        actions_taken=json.dumps(results),
        success=True,
    ))
    rule.run_count = (rule.run_count or 0) + 1
    rule.last_run_at = datetime.now(timezone.utc)
    db.commit()
    return {"ok": True, "results": results}


def get_automation_templates() -> list:
    """Return predefined automation rule templates."""
    return [
        {
            "id": "budget_alert",
            "name": "Alerta cuando el presupuesto supera el 85%",
            "description": "Notifica al PM cuando el gasto acumulado supera el 85% del presupuesto del proyecto",
            "trigger_type": "budget_threshold",
            "trigger_conditions": {"field": "budget_pct", "operator": "greater_than", "value": "85"},
            "actions": [{"type": "create_alert", "params": {"alert_type": "budget_warning", "message": "⚠ Presupuesto al 85% — revisar consumo del proyecto", "severity": "warning"}}],
        },
        {
            "id": "task_overdue_notify_pm",
            "name": "Notificar al PM cuando una tarea vence sin completarse",
            "trigger_type": "task_overdue",
            "trigger_conditions": None,
            "actions": [{"type": "notify_role", "params": {"role": "pm", "message": "⏰ Una tarea ha vencido sin completarse", "severity": "warning"}}],
        },
        {
            "id": "sprint_started_notify",
            "name": "Notificar al equipo cuando empieza un sprint",
            "trigger_type": "sprint_started",
            "trigger_conditions": None,
            "actions": [{"type": "notify_role", "params": {"role": "employee", "message": "🚀 Nuevo sprint iniciado — revisa tu backlog", "severity": "info"}}],
        },
        {
            "id": "timesheet_reminder",
            "name": "Recordar timesheet no enviado (viernes)",
            "trigger_type": "timesheet_not_submitted",
            "trigger_conditions": None,
            "actions": [{"type": "notify_role", "params": {"role": "employee", "message": "📋 Recuerda enviar tu timesheet semanal", "severity": "info"}}],
        },
        {
            "id": "ticket_p1_escalate",
            "name": "Escalar ticket P1 al gerente",
            "trigger_type": "ticket_created",
            "trigger_conditions": {"field": "priority", "operator": "equals", "value": "p1_critical"},
            "actions": [
                {"type": "notify_role", "params": {"role": "admin", "message": "🚨 Ticket P1 creado — requiere atención inmediata", "severity": "critical"}},
                {"type": "escalate_ticket", "params": {"to_level": "l2"}},
            ],
        },
        {
            "id": "expense_pending",
            "name": "Notificar al PM de gasto pendiente de aprobación",
            "trigger_type": "expense_submitted",
            "trigger_conditions": None,
            "actions": [{"type": "notify_role", "params": {"role": "pm", "message": "💸 Gasto enviado pendiente de aprobación", "severity": "info"}}],
        },
        {
            "id": "risk_high",
            "name": "Alerta de riesgo crítico",
            "trigger_type": "risk_score_high",
            "trigger_conditions": {"field": "risk_score", "operator": "greater_than", "value": "3"},
            "actions": [{"type": "create_alert", "params": {"alert_type": "risk_critical", "message": "⚠ Riesgo de alto impacto detectado en el proyecto", "severity": "critical"}}],
        },
    ]


# ── Router-extracted CRUD helpers ─────────────────────────────────────────────

def list_rules_for_user(db: Session, current_user, project_id, is_active):
    q = db.query(AutomationRule).options(joinedload(AutomationRule.project))
    if not current_user.is_superadmin and current_user.organization_id:
        org_user_ids = db.query(User.id).filter(
            User.organization_id == current_user.organization_id
        ).scalar_subquery()
        org_project_ids = db.query(Project.id).filter(
            Project.organization_id == current_user.organization_id
        ).scalar_subquery()
        q = q.filter(
            or_(
                AutomationRule.project_id.in_(org_project_ids),
                AutomationRule.created_by.in_(org_user_ids),
            )
        )
    if project_id:
        q = q.filter(
            (AutomationRule.project_id == project_id) | (AutomationRule.is_global == True)
        )
    if is_active is None:
        q = q.filter(AutomationRule.is_active == True)
    else:
        q = q.filter(AutomationRule.is_active == is_active)
    return [serialize_rule(r) for r in q.order_by(AutomationRule.created_at.desc()).all()]


def create_rule_db(payload, db: Session, current_user_id: str) -> dict:
    rule = AutomationRule(
        name=payload.name,
        description=payload.description,
        project_id=payload.project_id,
        is_global=payload.is_global,
        trigger_type=payload.trigger_type,
        trigger_conditions=json.dumps(payload.trigger_conditions) if payload.trigger_conditions else None,
        actions=json.dumps(payload.actions),
        created_by=current_user_id,
    )
    db.add(rule)
    db.commit()
    db.refresh(rule)
    rule = db.query(AutomationRule).options(joinedload(AutomationRule.project)).filter(
        AutomationRule.id == rule.id
    ).first()
    return serialize_rule(rule)


def update_rule_db(rule_id: str, payload, db: Session) -> dict:
    rule = db.query(AutomationRule).filter(
        AutomationRule.id == rule_id,
        AutomationRule.is_active == True,
    ).first()
    if not rule:
        raise HTTPException(404, "Regla no encontrada")
    data = payload.model_dump(exclude_unset=True)
    if "trigger_conditions" in data:
        data["trigger_conditions"] = json.dumps(data["trigger_conditions"]) if data["trigger_conditions"] else None
    if "actions" in data:
        data["actions"] = json.dumps(data["actions"])
    for k, v in data.items():
        setattr(rule, k, v)
    db.commit()
    rule = db.query(AutomationRule).options(joinedload(AutomationRule.project)).filter(
        AutomationRule.id == rule_id
    ).first()
    return serialize_rule(rule)


def delete_rule_db(rule_id: str, db: Session) -> dict:
    rule = db.query(AutomationRule).filter(
        AutomationRule.id == rule_id,
        AutomationRule.is_active == True,
    ).first()
    if not rule:
        raise HTTPException(404)
    rule.is_active = False
    db.commit()
    return {"ok": True, "message": "Regla eliminada correctamente"}


def get_executions_db(rule_id: str, limit: int, db: Session) -> list:
    rule = db.query(AutomationRule).filter(
        AutomationRule.id == rule_id,
        AutomationRule.is_active == True,
    ).first()
    if not rule:
        raise HTTPException(404, "Regla no encontrada")
    executions = db.query(AutomationExecution).filter(
        AutomationExecution.rule_id == rule_id
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


def test_rule_by_id(rule_id: str, user_id: str, db: Session) -> dict:
    rule = db.query(AutomationRule).filter(
        AutomationRule.id == rule_id,
        AutomationRule.is_active == True,
    ).first()
    if not rule:
        raise HTTPException(404)
    return test_automation_rule(rule, user_id, db)
