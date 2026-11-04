"""
Automations service — reglas SI disparador [condicion] ENTONCES acciones.

Auditoria 2026-11. Hasta ahora ninguna regla saltaba sola (nada llamaba a
`fire_trigger`), la pantalla ofrecia 64 disparadores y 23 acciones de los que
el motor conocia 14 y 11, «Probar» ejecutaba las acciones de verdad, y varias
acciones cruzaban organizaciones. Ahora:

- **Catalogo unico** (`CATALOGO_DISPARADORES`, `CATALOGO_ACCIONES`): la
  pantalla lo pide a la API, y guardar algo fuera de el da 422.
- **Disparo**: los cambios de registro los anota `automation_events` al
  guardar y los procesa el worker (`disparar`); los de fecha y umbral salen de
  `escanear`, que corre cada `AUTOMATIONS_SCAN_MINUTES`.
- **Una organizacion**: una regla solo ve eventos de la suya, y sus acciones
  (avisar a un rol, la integracion de Slack/Teams) se quedan dentro.
- **«Probar» simula**: dice que haria cada accion sin hacerla.
"""
import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import HTTPException
from sqlalchemy import func, or_
from sqlalchemy.orm import Session, joinedload

from app.core import timeutil
from app.core.outbound_url import validate_outbound_url
from app.models.alert import Alert, AlertSeverity, AlertType
from app.models.automations import ActionType, AutomationExecution, AutomationRule, TriggerType
from app.models.project import Project
from app.models.task import Task
from app.models.user import User

logger = logging.getLogger(__name__)


def _v(x):
    return getattr(x, "value", x)


# ═════════════════════════════════════════════════════════════════════════════
# Catalogo
# ═════════════════════════════════════════════════════════════════════════════

_CAMPOS_TAREA = ["status", "old_status", "priority", "assignee_id", "project_id"]
_CAMPOS_TICKET = ["priority", "ticket_type", "support_level", "status", "project_id"]

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
}
#: Alias historicos: se ejecutan, pero no se ofrecen.
_ALIAS = {"send_alert": "create_alert", "send_webhook": "call_webhook"}
_OPERADORES = {"equals", "not_equals", "greater_than", "less_than", "contains"}


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
    return faltan


def validar_regla(trigger_type: Optional[str], conditions: Optional[dict], actions: Optional[list]) -> None:
    """422 si la regla nombra algo que el motor no sabe hacer."""
    if trigger_type is not None and trigger_type not in CATALOGO_DISPARADORES:
        raise HTTPException(422, f"Disparador desconocido: {trigger_type}")
    if conditions:
        if not conditions.get("field"):
            raise HTTPException(422, "La condicion necesita un campo")
        if conditions.get("operator", "equals") not in _OPERADORES:
            raise HTTPException(422, f"Operador desconocido: {conditions.get('operator')}")
    if actions is not None:
        if not actions:
            raise HTTPException(422, "La regla necesita al menos una accion")
        for i, a in enumerate(actions, 1):
            tipo = (a or {}).get("type")
            if tipo == "conditional_branch":
                p = a.get("params") or {}
                validar_regla(None, p.get("condition"), (p.get("if_true") or []) + (p.get("if_false") or [])
                              or [{"type": "create_alert", "params": {"message": "-"}}])
                continue
            if _ALIAS.get(tipo, tipo) not in CATALOGO_ACCIONES:
                raise HTTPException(422, f"Accion {i}: tipo desconocido «{tipo}»")
            faltan = _faltan(tipo, a.get("params") or {})
            if faltan:
                raise HTTPException(422, f"Accion {i} ({tipo}): falta {', '.join(faltan)}")


def serialize_rule(r: AutomationRule) -> dict:
    return {
        "id": r.id, "name": r.name, "description": r.description,
        "project_id": r.project_id,
        "project_name": r.project.name if r.project else None,
        "is_active": r.is_active, "is_global": r.is_global,
        "trigger_type": _v(r.trigger_type),
        "trigger_conditions": json.loads(r.trigger_conditions) if r.trigger_conditions else None,
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


# ═════════════════════════════════════════════════════════════════════════════
# Acciones
#
# Todas comparten firma: (db, atype, action, params, context, results). La
# organizacion de la regla viaja en `context["organization_id"]`, y toda
# lectura de usuarios o integraciones se acota a ella.
# ═════════════════════════════════════════════════════════════════════════════

def _org(context: dict) -> Optional[str]:
    return context.get("organization_id")


def _usuarios_del_rol(db: Session, role: str, org: Optional[str]) -> list:
    q = db.query(User).filter(User.role == role, User.is_active.is_(True))
    return q.filter(User.organization_id == org).all() if org else []


def _accion_create_alert(db: Session, atype, action: dict, params: dict, context: dict, results: list) -> None:
    """Acciones `create_alert`, `send_alert` (mismo efecto)."""
    sev = params.get("severity") if params.get("severity") in _SEVERIDADES else "info"
    db.add(Alert(
        alert_type=AlertType.automation,
        title=params.get("title") or params.get("message") or "Automatización",
        description=params.get("message", ""),
        severity=AlertSeverity(sev),
        organization_id=_org(context),
        project_id=context.get("project_id"),
        task_id=context.get("task_id"),
        user_id=params.get("user_id"),
    ))
    results.append({"action": atype, "ok": True})


def _avisar(db: Session, user_ids: list, params: dict, context: dict) -> None:
    from app.services.notifications import notify_user
    titulo = params.get("message") or "Automatización"
    for uid in user_ids:
        notify_user(db, uid, "automation", titulo, params.get("description") or None,
                    resource=_recurso(context)[0], resource_id=_recurso(context)[1])


def _recurso(context: dict) -> tuple:
    for clave, nombre in (("ticket_id", "ticket"), ("task_id", "task"), ("expense_id", "expense"),
                          ("opportunity_id", "opportunity"), ("project_id", "project")):
        if context.get(clave):
            return nombre, context[clave]
    return None, None


def _accion_notify_role(db: Session, atype, action: dict, params: dict, context: dict, results: list) -> None:
    """Accion `notify_role`: campana a los usuarios activos del rol, de la organizacion."""
    users = _usuarios_del_rol(db, params.get("role", "pm"), _org(context))
    _avisar(db, [u.id for u in users], params, context)
    results.append({"action": atype, "ok": True, "notified": len(users)})


def _accion_notify_user(db: Session, atype, action: dict, params: dict, context: dict, results: list) -> None:
    """Accion `notify_user`: la persona del evento (asignado, solicitante, dueño)."""
    user_id = params.get("user_id") or context.get("user_id")
    if not user_id:
        results.append({"action": atype, "ok": False, "error": "El evento no trae usuario"})
        return
    _avisar(db, [user_id], params, context)
    results.append({"action": atype, "ok": True, "user_id": user_id})


def _destinatarios_de_correo(db: Session, params: dict, context: dict) -> list[str]:
    directos = [x.strip() for x in str(params.get("to") or params.get("email") or "").split(",") if x.strip()]
    if params.get("to_role"):
        directos += [u.email for u in _usuarios_del_rol(db, params["to_role"], _org(context)) if u.email]
    return sorted(set(directos))


def _accion_send_email(db: Session, atype, action: dict, params: dict, context: dict, results: list) -> None:
    """Accion `send_email`: a `to` (direcciones) y/o a los usuarios de `to_role`."""
    from app.services.notification_service import send_email_notification
    destinos = _destinatarios_de_correo(db, params, context)
    if not destinos:
        results.append({"action": atype, "ok": False, "error": "Sin destinatarios"})
        return
    subject = params.get("subject", "Notificación automática")
    body = params.get("body") or params.get("message", "")
    fallidos = [d for d in destinos if not send_email_notification(to=d, subject=subject, body=body)]
    if fallidos:
        results.append({"action": atype, "ok": False, "sent": len(destinos) - len(fallidos),
                        "error": f"No enviado a {len(fallidos)} de {len(destinos)} (SMTP)"})
    else:
        results.append({"action": atype, "ok": True, "sent": len(destinos)})


def _motivo_de_rechazo_ssrf(url: str) -> Optional[str]:
    """Por qué esta URL no puede salir a la red, o `None` si puede.

    Tres barreras: solo HTTPS; ni una IP privada escrita a mano; ni un nombre
    que resuelva a una IP privada. Si la resolucion falla se deja pasar (un DNS
    caido no debe bloquear todos los webhooks) y la propia peticion fallara.
    """
    import ipaddress
    import socket
    from urllib.parse import urlparse

    partes = urlparse(url)
    if partes.scheme != "https":
        return "Solo se permiten URLs HTTPS para webhooks"

    host = partes.hostname or ""
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        ip = None

    if ip is not None:
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
            return "El webhook apunta a una dirección IP privada/interna"
        return None

    try:
        resueltas = socket.getaddrinfo(host, None)
    except Exception:
        logger.warning("Fallo resolviendo getaddrinfo para webhook host=%s en SSRF check", host)
        return None

    for entrada in resueltas:
        resuelta = ipaddress.ip_address(entrada[4][0])
        if resuelta.is_private or resuelta.is_loopback or resuelta.is_link_local:
            return "El webhook resuelve a una dirección IP interna"
    return None


def _cuerpo_del_webhook(params: dict, context: dict) -> dict:
    crudo = params.get("payload")
    if isinstance(crudo, dict):
        return crudo
    if isinstance(crudo, str) and crudo.strip():
        try:
            return json.loads(crudo)
        except ValueError:
            return {"text": crudo, **_contexto_publico(context)}
    return _contexto_publico(context)


def _contexto_publico(context: dict) -> dict:
    return {k: v for k, v in context.items() if k not in ("organization_id",)}


def _timeout(db: Session, context: dict) -> int:
    from app.services.settings_service import get_runtime_int
    return get_runtime_int(db, "AUTOMATIONS_WEBHOOK_TIMEOUT_SECONDS", _org(context)) or 10


def _accion_call_webhook(db: Session, atype, action: dict, params: dict, context: dict, results: list) -> None:
    """Acción `call_webhook` (y su alias `send_webhook`): sirve tambien para RPA
    (Power Automate, Zapier, Make, n8n, UiPath), que se disparan por webhook."""
    import urllib.request as _ur

    url = params.get("url")
    if not url:
        results.append({"action": atype, "ok": False, "error": "Missing 'url' parameter"})
        return
    rechazo = _motivo_de_rechazo_ssrf(url)
    if rechazo:
        results.append({"action": atype, "ok": False, "error": rechazo})
        return
    cabeceras = params.get("headers") if isinstance(params.get("headers"), dict) else {}
    peticion = _ur.Request(  # noqa: S310
        validate_outbound_url(url, field="URL de webhook"),
        data=json.dumps(_cuerpo_del_webhook(params, context), default=str).encode(),
        method=(params.get("method") or "POST").upper(),
        headers={"Content-Type": "application/json", **cabeceras},
    )
    try:
        with _ur.urlopen(peticion, timeout=_timeout(db, context)):  # noqa: S310
            pass
        results.append({"action": atype, "ok": True, "url": url})
    except Exception as err:
        logger.exception("Automation webhook failed url=%s", url)
        results.append({"action": atype, "ok": False, "error": str(err)})


def _webhook_de_la_integracion(db: Session, tipo, context: dict) -> Optional[str]:
    """El webhook de la integracion activa de ESTA organizacion (antes: la primera de cualquiera)."""
    from app.models.cab import IntegrationConfig
    org = _org(context)
    if not org:
        return None
    cfg = db.query(IntegrationConfig).filter(
        IntegrationConfig.integration_type == tipo,
        IntegrationConfig.is_active.is_(True),
        IntegrationConfig.organization_id == org,
    ).first()
    if not cfg:
        return None
    try:
        from app.core.secret_utils import decrypt_config_secrets
        # `webhook_url` se guarda cifrado: sin descifrar no llegaba ningun aviso.
        return (decrypt_config_secrets(json.loads(cfg.config or "{}")) or {}).get("webhook_url")
    except ValueError:
        return None


def _accion_send_slack_message(db: Session, atype, action: dict, params: dict, context: dict, results: list) -> None:
    """Accion `send_slack_message`: la URL escrita en la regla o la integracion de la organizacion."""
    from app.models.cab import IntegrationType
    from app.services.integrations import send_slack_message
    url = params.get("slack_webhook_url") or params.get("webhook_url") \
        or _webhook_de_la_integracion(db, IntegrationType.slack, context)
    if not url:
        results.append({"action": atype, "ok": False, "error": "No hay webhook de Slack configurado"})
        return
    res = send_slack_message(url, params.get("message", "Notificación automática"))
    results.append({"action": atype, "ok": bool(res.get("ok")), "error": None if res.get("ok") else res.get("error")})


def _accion_send_teams_message(db: Session, atype, action: dict, params: dict, context: dict, results: list) -> None:
    """Accion `send_teams_message`: la URL escrita en la regla o la integracion de la organizacion."""
    from app.models.cab import IntegrationType
    from app.services.integrations import send_teams_message
    url = params.get("teams_webhook_url") or params.get("webhook_url") \
        or _webhook_de_la_integracion(db, IntegrationType.teams, context)
    if not url:
        results.append({"action": atype, "ok": False, "error": "No hay webhook de Teams configurado"})
        return
    res = send_teams_message(url, params.get("title") or "Automatización", params.get("message", ""))
    results.append({"action": atype, "ok": bool(res.get("ok")), "error": None if res.get("ok") else res.get("error")})


def _tarea_del_evento(db: Session, context: dict, params: dict) -> Optional[Task]:
    task_id = context.get("task_id") or params.get("task_id")
    if not task_id:
        return None
    q = db.query(Task).filter(Task.id == task_id)
    if _org(context):
        q = q.filter(Task.organization_id == _org(context))
    return q.first()


def _accion_change_task_status(db: Session, atype, action: dict, params: dict, context: dict, results: list) -> None:
    from app.models.task import TaskStatus
    task = _tarea_del_evento(db, context, params)
    if not task:
        results.append({"action": atype, "ok": False, "error": "El evento no trae tarea"})
        return
    task.status = TaskStatus(params["status"])
    results.append({"action": atype, "ok": True, "task": task.code})


def _accion_change_task_priority(db: Session, atype, action: dict, params: dict, context: dict, results: list) -> None:
    from app.models.task import TaskPriority
    task = _tarea_del_evento(db, context, params)
    if not task:
        results.append({"action": atype, "ok": False, "error": "El evento no trae tarea"})
        return
    task.priority = TaskPriority(params["priority"])
    results.append({"action": atype, "ok": True, "task": task.code})


def _codigo_de_tarea(db: Session) -> str:
    """La misma secuencia que el alta de tareas de la API."""
    from app.services.numbering import next_numbered_code
    return next_numbered_code(db, "task", prefix="TSK", padding=5)


def _accion_create_task(db: Session, atype, action: dict, params: dict, context: dict, results: list) -> None:
    """Accion `create_task`: en el proyecto del evento, asignada a su usuario si lo trae."""
    from app.models.task import TaskPriority
    project_id = context.get("project_id")
    if not project_id:
        results.append({"action": atype, "ok": False, "error": "El evento no trae proyecto"})
        return
    dias = params.get("due_in_days")
    try:
        vence = timeutil.today() + timedelta(days=int(dias)) if str(dias or "").strip() else None
    except ValueError:
        vence = None
    task = Task(
        code=_codigo_de_tarea(db), project_id=project_id, organization_id=_org(context),
        title=str(params["task_title"])[:500],
        description=f"Creada por la automatización a partir de {context.get('event_type', 'un evento')}.",
        priority=TaskPriority(params.get("priority") or "medium"),
        assignee_id=context.get("user_id"), due_date=vence,
    )
    db.add(task)
    db.flush()
    results.append({"action": atype, "ok": True, "task": task.code})


def _accion_change_project_status(db: Session, atype, action: dict, params: dict, context: dict, results: list) -> None:
    from app.models.project import ProjectStatus
    if not context.get("project_id"):
        results.append({"action": atype, "ok": False, "error": "El evento no trae proyecto"})
        return
    q = db.query(Project).filter(Project.id == context["project_id"])
    if _org(context):
        q = q.filter(Project.organization_id == _org(context))
    proyecto = q.first()
    if not proyecto:
        results.append({"action": atype, "ok": False, "error": "Proyecto no encontrado"})
        return
    proyecto.status = ProjectStatus(params["status"])
    results.append({"action": atype, "ok": True, "project": proyecto.code})


def _ticket_del_evento(db: Session, context: dict):
    from app.models.service_desk import Ticket
    if not context.get("ticket_id"):
        return None
    q = db.query(Ticket).filter(Ticket.id == context["ticket_id"])
    if _org(context):
        q = q.filter(Ticket.organization_id == _org(context))
    return q.first()


def _accion_escalate_ticket(db: Session, atype, action: dict, params: dict, context: dict, results: list) -> None:
    """Sube el nivel de soporte (nunca lo baja) y lo anota como escalado."""
    from app.models.service_desk import SupportLevel
    from app.services.service_desk.ticket_events import registrar
    ticket = _ticket_del_evento(db, context)
    if not ticket:
        results.append({"action": atype, "ok": False, "error": "El evento no trae ticket"})
        return
    nivel = params["to_level"]
    if (_v(ticket.support_level) or "l1") >= nivel:
        results.append({"action": atype, "ok": True, "skipped": f"ya está en {_v(ticket.support_level)}"})
        return
    antes = _v(ticket.support_level)
    ticket.support_level = SupportLevel(nivel)
    registrar(db, ticket, "escalated", {"from": antes, "to_level": nivel, "origin": "automation"})
    results.append({"action": atype, "ok": True, "ticket": ticket.number, "to_level": nivel})


def _accion_change_ticket_status(db: Session, atype, action: dict, params: dict, context: dict, results: list) -> None:
    from app.models.service_desk import TicketStatus
    ticket = _ticket_del_evento(db, context)
    if not ticket:
        results.append({"action": atype, "ok": False, "error": "El evento no trae ticket"})
        return
    nuevo = TicketStatus(params["status"])
    ticket.status = nuevo
    if nuevo == TicketStatus.resolved and not ticket.resolved_at:
        ticket.resolved_at = datetime.now(timezone.utc)
    results.append({"action": atype, "ok": True, "ticket": ticket.number})


def _accion_conditional_branch(db: Session, atype, action: dict, params: dict, context: dict, results: list) -> None:
    """Accion `conditional_branch`: evalua y ejecuta `if_true` o `if_false`."""
    rama = check_conditions(params.get("condition", {}), context)
    acciones = params.get("if_true", []) if rama else params.get("if_false", [])
    results.append({"action": atype, "ok": True, "branch_taken": "if_true" if rama else "if_false",
                    "branch_results": execute_actions(acciones, context, db) if acciones else []})


_ACCIONES = {
    ActionType.create_alert: _accion_create_alert,
    ActionType.send_alert: _accion_create_alert,
    ActionType.notify_role: _accion_notify_role,
    ActionType.notify_user: _accion_notify_user,
    ActionType.send_email: _accion_send_email,
    ActionType.call_webhook: _accion_call_webhook,
    ActionType.send_webhook: _accion_call_webhook,
    ActionType.send_slack_message: _accion_send_slack_message,
    ActionType.send_teams_message: _accion_send_teams_message,
    ActionType.change_task_status: _accion_change_task_status,
    ActionType.change_task_priority: _accion_change_task_priority,
    ActionType.create_task: _accion_create_task,
    ActionType.change_project_status: _accion_change_project_status,
    ActionType.escalate_ticket: _accion_escalate_ticket,
    ActionType.change_ticket_status: _accion_change_ticket_status,
    ActionType.conditional_branch: _accion_conditional_branch,
}
assert {a.value for a in ActionType} == {a.value for a in _ACCIONES}
assert set(CATALOGO_ACCIONES) | set(_ALIAS) | {"conditional_branch"} == {a.value for a in ActionType}


def execute_actions(actions: list, context: dict, db: Session) -> list:
    """Ejecuta las acciones en orden. Una que falla se anota y no para a las demas."""
    results = []
    for action in actions:
        atype = action.get("type")
        params = action.get("params", {}) or {}
        try:
            ejecutar = _ACCIONES.get(atype)
            if ejecutar is None:
                logger.warning("Tipo de acción de automatización desconocido: %s", atype)
                results.append({"action": atype, "ok": False, "error": "tipo desconocido"})
                continue
            ejecutar(db, atype, action, params, context, results)
        except Exception as e:
            logger.exception("Automation action %s execution failed", atype)
            results.append({"action": atype, "ok": False, "error": str(e)})
    return results


# ═════════════════════════════════════════════════════════════════════════════
# Disparo
# ═════════════════════════════════════════════════════════════════════════════

def _encendidas(db: Session, org_id: Optional[str]) -> bool:
    from app.services.settings_service import get_runtime_bool
    valor = get_runtime_bool(db, "AUTOMATIONS_ENABLED", org_id)
    return True if valor is None else bool(valor)


def _reglas(db: Session, trigger_type: str, org_id: str) -> list:
    return db.query(AutomationRule).filter(
        AutomationRule.trigger_type == trigger_type,
        AutomationRule.is_active.is_(True),
        AutomationRule.organization_id == org_id,
    ).order_by(AutomationRule.created_at).all()


def disparar(db: Session, trigger_type: str, context: dict, org_id: Optional[str], *,
             profundidad: int = 0, clave: Optional[str] = None) -> dict:
    """Ejecuta las reglas activas de `org_id` con ese disparador. No hace commit.

    `clave`: si la regla ya actuo con esta clave, no repite (barrido).
    """
    from app.services.automation_events import PROFUNDIDAD
    from app.services.settings_service import get_runtime_int

    if not org_id or not _encendidas(db, org_id):
        return {"rules": []}
    maximo = get_runtime_int(db, "AUTOMATIONS_MAX_CHAIN_DEPTH", org_id)
    if profundidad > (3 if maximo is None else maximo):
        logger.warning("automatizaciones: cadena cortada en %s (profundidad %s)", trigger_type, profundidad)
        return {"rules": [], "cut": True}

    context = {**context, "organization_id": org_id, "event_type": trigger_type}
    ejecutadas = []
    for rule in _reglas(db, trigger_type, org_id):
        if rule.project_id and rule.project_id != context.get("project_id"):
            continue
        conditions = json.loads(rule.trigger_conditions) if rule.trigger_conditions else None
        if not check_conditions(conditions, context):
            continue
        if clave and db.query(AutomationExecution.id).filter(
                AutomationExecution.rule_id == rule.id, AutomationExecution.dedupe_key == clave).first():
            continue
        previa = db.info.get(PROFUNDIDAD)
        db.info[PROFUNDIDAD] = profundidad + 1
        try:
            results = execute_actions(json.loads(rule.actions) if rule.actions else [], context, db)
            db.flush()
        finally:
            if previa is None:
                db.info.pop(PROFUNDIDAD, None)
            else:
                db.info[PROFUNDIDAD] = previa
        success = all(r.get("ok", True) for r in results)
        db.add(AutomationExecution(
            rule_id=rule.id, organization_id=org_id, dedupe_key=clave,
            trigger_context=json.dumps(_contexto_publico(context), default=str),
            actions_taken=json.dumps(results, default=str),
            success=success,
            error=None if success else "; ".join(str(r.get("error")) for r in results if not r.get("ok", True))[:500],
        ))
        rule.run_count = (rule.run_count or 0) + 1
        rule.last_run_at = datetime.now(timezone.utc)
        rule.last_error = None if success else json.dumps(
            [r for r in results if not r.get("ok", True)], default=str)[:500]
        ejecutadas.append({"rule_id": rule.id, "success": success})
    return {"rules": ejecutadas}


# ── Barrido periodico: fechas y umbrales ────────────────────────────────────

def _orgs_con_reglas(db: Session, trigger_type: str, org_id: Optional[str]) -> list[str]:
    q = db.query(AutomationRule.organization_id).filter(
        AutomationRule.trigger_type == trigger_type, AutomationRule.is_active.is_(True),
        AutomationRule.organization_id.isnot(None))
    if org_id:
        q = q.filter(AutomationRule.organization_id == org_id)
    return [o for (o,) in q.distinct().all()]


def _contexto_de_tarea(t: Task) -> dict:
    return {"task_id": t.id, "project_id": t.project_id, "code": t.code, "title": t.title,
            "status": _v(t.status), "priority": _v(t.priority), "assignee_id": t.assignee_id,
            "user_id": t.assignee_id, "due_date": str(t.due_date) if t.due_date else None}


_TAREA_ABIERTA = ("done", "cancelled")


def _barrer_tareas_vencidas(db: Session, org: str, hoy) -> int:
    n = 0
    for t in db.query(Task).filter(Task.organization_id == org, Task.is_active.is_(True),
                                   Task.due_date < hoy, Task.status.notin_(_TAREA_ABIERTA)):
        r = disparar(db, "task_overdue", {**_contexto_de_tarea(t), "days_overdue": (hoy - t.due_date).days},
                     org, clave=f"task_overdue:{t.id}:{t.due_date}")
        n += len(r["rules"])
    return n


def _barrer_tareas_que_vencen(db: Session, org: str, hoy) -> int:
    from app.services.settings_service import get_runtime_int
    dias = get_runtime_int(db, "AUTOMATIONS_DEADLINE_DAYS", org)
    dias = 2 if dias is None else dias
    n = 0
    for t in db.query(Task).filter(Task.organization_id == org, Task.is_active.is_(True),
                                   Task.due_date >= hoy, Task.due_date <= hoy + timedelta(days=dias),
                                   Task.status.notin_(_TAREA_ABIERTA)):
        r = disparar(db, "task_deadline_approaching",
                     {**_contexto_de_tarea(t), "days_left": (t.due_date - hoy).days},
                     org, clave=f"task_deadline:{t.id}:{t.due_date}")
        n += len(r["rules"])
    return n


def _barrer_presupuesto(db: Session, org: str, hoy) -> int:
    """Consumo = coste imputado / presupuesto, como el motor de alertas."""
    from app.models.project import ProjectStatus
    from app.models.imputation import Imputation
    proyectos = db.query(Project).filter(Project.organization_id == org, Project.status == ProjectStatus.active,
                                         Project.budget_amount > 0).all()
    if not proyectos:
        return 0
    costes = dict(db.query(Imputation.project_id, func.sum(Imputation.cost_amount)).filter(
        Imputation.project_id.in_([p.id for p in proyectos])).group_by(Imputation.project_id).all())
    n = 0
    for p in proyectos:
        pct = round(float(costes.get(p.id) or 0) / float(p.budget_amount) * 100, 1)
        # Una vez por regla y proyecto: la condicion de la regla decide el umbral.
        r = disparar(db, "budget_threshold", {"project_id": p.id, "code": p.code, "name": p.name,
                                              "budget_pct": pct}, org, clave=f"budget_threshold:{p.id}")
        n += len(r["rules"])
    return n


def _barrer_partes(db: Session, org: str, hoy) -> int:
    from app.models.financial import Timesheet, TimesheetStatus
    from app.services.settings_service import get_runtime_int
    dia = get_runtime_int(db, "AUTOMATIONS_TIMESHEET_WEEKDAY", org) or 5
    if hoy.isoweekday() < dia:
        return 0
    lunes = hoy - timedelta(days=hoy.weekday())
    enviados = {u for (u,) in db.query(Timesheet.user_id).filter(
        Timesheet.week_start == lunes, Timesheet.status != TimesheetStatus.draft)}
    n = 0
    for u in db.query(User).filter(User.organization_id == org, User.is_active.is_(True)):
        if u.id in enviados or _v(u.role) in ("client",):
            continue
        r = disparar(db, "timesheet_not_submitted", {"user_id": u.id, "week_start": str(lunes)}, org,
                     clave=f"timesheet_not_submitted:{u.id}:{lunes}")
        n += len(r["rules"])
    return n


_BARRIDOS = {
    "task_overdue": _barrer_tareas_vencidas,
    "task_deadline_approaching": _barrer_tareas_que_vencen,
    "budget_threshold": _barrer_presupuesto,
    "timesheet_not_submitted": _barrer_partes,
}
assert set(_BARRIDOS) == {k for k, d in CATALOGO_DISPARADORES.items() if d.get("scan")}


def escanear(db: Session, org_id: Optional[str] = None) -> dict:
    """Disparadores de fecha y umbral. Solo mira las organizaciones con reglas activas."""
    from app.services.service_desk.ticket_events import como_organizacion
    hoy = timeutil.today()
    salida = {}
    for disparador, barrer in _BARRIDOS.items():
        total = 0
        for org in _orgs_con_reglas(db, disparador, org_id):
            if not _encendidas(db, org):
                continue
            with como_organizacion(db, org):
                try:
                    with db.begin_nested():
                        total += barrer(db, org, hoy)
                except Exception:
                    logger.exception("automatizaciones: el barrido %s fallo en %s", disparador, org)
        salida[disparador] = total
    db.commit()
    return {"executed": sum(salida.values()), "by_trigger": salida}


def run_scheduled_automations(db: Session, org_id: Optional[str] = None) -> dict:
    """Compatibilidad con `POST /automations/run-scheduled`: corre el barrido."""
    return escanear(db, org_id)


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
                                                  "task_title", "to_level")})
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
        raise HTTPException(404, "Regla no encontrada")
    return rule


def _proyecto_de_mi_organizacion(db: Session, project_id: Optional[str], current_user) -> None:
    if not project_id:
        return
    q = db.query(Project.id).filter(Project.id == project_id)
    if not current_user.is_superadmin:
        q = q.filter(Project.organization_id == current_user.organization_id)
    if not q.first():
        raise HTTPException(422, "Proyecto no encontrado")


def create_rule_db(payload, db: Session, current_user) -> dict:
    validar_regla(payload.trigger_type, payload.trigger_conditions, payload.actions)
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
    )
    db.add(rule)
    db.commit()
    return serialize_rule(regla_de(db, rule.id, current_user))


def update_rule_db(rule_id: str, payload, db: Session, current_user) -> dict:
    rule = regla_de(db, rule_id, current_user)
    data = payload.model_dump(exclude_unset=True)
    validar_regla(data.get("trigger_type"), data.get("trigger_conditions"), data.get("actions"))
    if "project_id" in data:
        _proyecto_de_mi_organizacion(db, data["project_id"], current_user)
        data["project_id"] = data["project_id"] or None
        data["is_global"] = not data["project_id"]
    if "trigger_conditions" in data:
        data["trigger_conditions"] = json.dumps(data["trigger_conditions"]) if data["trigger_conditions"] else None
    if "actions" in data:
        data["actions"] = json.dumps(data["actions"])
    for k, v in data.items():
        setattr(rule, k, v)
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
