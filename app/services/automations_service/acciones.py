"""Ejecucion de las acciones de una regla: avisos, correo, webhooks, mensajeria, tareas, tickets, asignacion y aprobaciones.

Parte de `app.services.automations_service` (auditoria 2026-11, #24): se partio por responsabilidad
sin cambiar el codigo. El paquete reexporta todos los nombres.
"""
import json
from datetime import datetime, timedelta, timezone
from typing import Optional
from sqlalchemy import func
from sqlalchemy.orm import Session
from app.core import timeutil
from app.core.outbound_url import abrir, validate_outbound_url
from app.models.alert import Alert, AlertSeverity, AlertType
from app.models.automations import ActionType
from app.models.project import Project
from app.models.task import Task
from app.models.user import User
from app.core.errores import ErrorDeDominio

from app.services.automations_service.catalogo import (
    CAMPOS_ACTUALIZABLES,
    _SEVERIDADES,
    check_conditions,
)
from app.services.automations_service._comun import _v, logger


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
        with abrir(peticion, timeout=_timeout(db, context)):  # noqa: S310
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


# ── Revisión 2026-11: asignar, actualizar campo, crear aprobación ──────────

_TICKET_CERRADO = ("resolved", "closed", "cancelled")


def _menos_cargado(db: Session, role: str, org: Optional[str], de_tickets: bool) -> Optional[User]:
    """El miembro activo del rol con menos trabajo abierto (empate: el primero por nombre)."""
    usuarios = sorted(_usuarios_del_rol(db, role, org), key=lambda u: (u.full_name or "", u.id))
    if not usuarios:
        return None
    ids = [u.id for u in usuarios]
    if de_tickets:
        from app.models.service_desk import Ticket
        carga = dict(db.query(Ticket.assigned_to_user_id, func.count(Ticket.id)).filter(
            Ticket.assigned_to_user_id.in_(ids), Ticket.status.notin_(_TICKET_CERRADO))
            .group_by(Ticket.assigned_to_user_id).all())
    else:
        carga = dict(db.query(Task.assignee_id, func.count(Task.id)).filter(
            Task.assignee_id.in_(ids), Task.is_active.is_(True), Task.status.notin_(_TAREA_ABIERTA))
            .group_by(Task.assignee_id).all())
    return min(usuarios, key=lambda u: carga.get(u.id, 0))


def _accion_assign(db: Session, atype, action: dict, params: dict, context: dict, results: list) -> None:
    """Asigna la tarea o el ticket del evento a una persona o al menos cargado de un rol."""
    ticket = _ticket_del_evento(db, context)
    tarea = None if ticket else _tarea_del_evento(db, context, params)
    if not (ticket or tarea):
        results.append({"action": atype, "ok": False, "error": "El evento no trae tarea ni ticket"})
        return
    org = _org(context)
    if params.get("to_user"):
        quien = db.query(User).filter(User.email == str(params["to_user"]).strip().lower(),
                                      User.is_active.is_(True), User.organization_id == org).first()
        if not quien:
            results.append({"action": atype, "ok": False, "error": f"Usuario no encontrado: {params['to_user']}"})
            return
    else:
        quien = _menos_cargado(db, params["to_role"], org, de_tickets=bool(ticket))
        if not quien:
            results.append({"action": atype, "ok": False, "error": f"Nadie activo con rol {params['to_role']}"})
            return
    if ticket:
        ticket.assigned_to_user_id = quien.id
        results.append({"action": atype, "ok": True, "ticket": ticket.number, "assignee": quien.email})
    else:
        tarea.assignee_id = quien.id
        results.append({"action": atype, "ok": True, "task": tarea.code, "assignee": quien.email})


def _valor_de_campo(tipo: str, columna, valor: str):
    texto = str(valor).strip()
    if tipo == "date":
        if texto.startswith("+") or texto.startswith("-"):
            return timeutil.today() + timedelta(days=int(texto))
        from datetime import date
        return date.fromisoformat(texto)
    if tipo == "number":
        return float(texto)
    if tipo == "int":
        return int(texto)
    if tipo == "enum":
        return columna.type.enum_class(texto)
    return texto


def _accion_update_field(db: Session, atype, action: dict, params: dict, context: dict, results: list) -> None:
    campo = params["field"]
    if campo not in CAMPOS_ACTUALIZABLES:
        results.append({"action": atype, "ok": False, "error": f"Campo no permitido: {campo}"})
        return
    entidad, tipo = CAMPOS_ACTUALIZABLES[campo]
    obj = _ticket_del_evento(db, context) if entidad == "ticket" else _tarea_del_evento(db, context, params)
    if not obj:
        results.append({"action": atype, "ok": False, "error": f"El evento no trae {entidad}"})
        return
    atributo = campo.split(".", 1)[1]
    try:
        valor = _valor_de_campo(tipo, type(obj).__table__.c[atributo], params["value"])
    except (ValueError, TypeError) as e:
        results.append({"action": atype, "ok": False, "error": f"Valor no válido para {campo}: {e}"})
        return
    setattr(obj, atributo, valor)
    results.append({"action": atype, "ok": True, "field": campo, "value": str(_v(valor))})


#: Qué entidad aprueba una regla, según lo que trae el evento (la primera que haya).
_ENTIDAD_DEL_EVENTO = (("expense_id", "expense"), ("invoice_id", "invoice"), ("timesheet_id", "timesheet"),
                       ("absence_id", "leave"), ("ticket_id", "ticket"), ("task_id", "task"),
                       ("opportunity_id", "opportunity"), ("project_id", "project"))


def _accion_create_approval(db: Session, atype, action: dict, params: dict, context: dict, results: list) -> None:
    """Abre una aprobación sobre el registro del evento, con el flujo que elijan sus condiciones."""
    from app.models.billing_reports import ApprovalRequest
    from app.schemas.approvals import ApprovalRequestIn
    from app.services.approval_engine.requests import create_approval_request
    clave, tipo = next(((k, t) for k, t in _ENTIDAD_DEL_EVENTO if context.get(k)), (None, None))
    if not clave:
        results.append({"action": atype, "ok": False, "error": "El evento no trae nada que aprobar"})
        return
    tipo = (params.get("entity_type") or "").strip() or tipo
    entidad = str(context[clave])
    if db.query(ApprovalRequest.id).filter(ApprovalRequest.entity_type == tipo, ApprovalRequest.entity_id == entidad,
                                           ApprovalRequest.status == "pending").first():
        results.append({"action": atype, "ok": True, "skipped": "ya hay una aprobación pendiente"})
        return
    solicitante_id = context.get("user_id") or context.get("rule_owner_id")
    solicitante = db.query(User).filter(User.id == solicitante_id, User.organization_id == _org(context)).first() \
        if solicitante_id else None
    if not solicitante:
        results.append({"action": atype, "ok": False, "error": "Sin solicitante: ni usuario del evento ni autor de la regla"})
        return
    resumen = (params.get("summary") or context.get("title") or context.get("code")
               or f"{tipo} {entidad}")
    contexto = {k: v for k, v in context.items() if isinstance(v, (str, int, float, bool)) or v is None}
    try:
        req = create_approval_request(
            ApprovalRequestIn(entity_type=tipo, entity_id=entidad, entity_summary=str(resumen)[:500],
                              context=contexto), db, solicitante, confirmar=False)
    except ErrorDeDominio as e:
        results.append({"action": atype, "ok": False, "error": str(e.detail)})
        return
    results.append({"action": atype, "ok": True, "approval_id": req.id, "entity_type": tipo})


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
    ActionType.assign: _accion_assign,
    ActionType.update_field: _accion_update_field,
    ActionType.create_approval: _accion_create_approval,
}
assert {a.value for a in ActionType} == {a.value for a in _ACCIONES}


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


_TAREA_ABIERTA = ("done", "cancelled")
