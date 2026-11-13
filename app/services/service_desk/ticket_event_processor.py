"""Procesa la bandeja de eventos de ticket: avisos, correo y webhooks.

Cada evento de `sd_ticket_events` (ver `ticket_events.py`) se convierte en:

- un aviso en la campana para cada usuario interno al que le toca,
- un correo, con la plantilla de su papel y en su idioma,
- y el evento de sistema `ticket.*`, que dispara los webhooks suscritos.

Quien hizo el cambio no recibe aviso de su propio cambio, y un comentario
interno nunca llega al solicitante.

Corre en Celery, fuera de la peticion, y una organizacion cada vez: la sesion
del worker no tiene filtro de tenant y `fire_webhook` busca webhooks sin
filtrar, asi que sin publicar la organizacion del evento el webhook de un
cliente recibiria los tickets de otro.
"""
from __future__ import annotations

import html
import json
import logging
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.cab import EmailLog, EmailTemplate
from app.models.client_portal import ClientUser
from app.models.service_desk import (
    AgentGroupMember,
    Ticket,
    TicketComment,
    TicketEvent,
    TicketWatcher,
)
from app.models.user import User, UserPreference
from app.services import settings_service as _ss
from app.services.service_desk import correo
from app.services.formato_regional import IDIOMA_DE_RESPALDO
from app.services.service_desk.plantillas_aviso import ETIQUETAS, IDIOMAS, POR_DEFECTO

logger = logging.getLogger(__name__)

#: Tipo de aviso de la campana por tipo de evento.
TIPO_DE_AVISO = {
    "created": "ticket_created",
    "assigned": "ticket_assigned",
    "group_assigned": "ticket_assigned",
    "commented": "ticket_replied",
    "status_changed": "ticket_updated",
    "priority_changed": "ticket_updated",
    "sla_warning": "ticket_sla_warning",
    "sla_breached": "ticket_sla_breached",
    "ola_breached": "ticket_sla_breached",
    "uc_breached": "ticket_sla_breached",
    "escalated": "ticket_escalated",
    "approval_requested": "approval_requested",
    "approval_decided": "ticket_updated",
}

#: Eventos que se avisan solo en la campana: por correo serian ruido.
SOLO_CAMPANA = {"priority_changed"}

_ESTADOS_CERRADOS = {"resolved", "closed", "cancelled"}


@dataclass
class Destinatario:
    papel: str                      # requester | agent | approver
    email: Optional[str]
    nombre: str
    idioma: str
    user_id: Optional[str] = None   # usuario interno: recibe tambien la campana
    es_cliente: bool = False        # usuario del portal: su enlace va al portal
    guardia: bool = False           # de guardia: ademas, SMS si lo permite SD_ONCALL_SMS
    telefono: Optional[str] = None


# ── Contexto de organizacion ──────────────────────────────────────────────────

from app.services.service_desk.ticket_events import como_organizacion as _como_organizacion  # noqa: E402


# ── Idioma, plantillas y textos ──────────────────────────────────────────────

def _idioma(db: Session, preferido: Optional[str], org_id: Optional[str]) -> str:
    for candidato in (preferido, _ss.get_runtime_str(db, "DEFAULT_LANGUAGE", org_id), IDIOMA_DE_RESPALDO):
        corto = (candidato or "").split("-")[0].lower()
        if corto in IDIOMAS:
            return corto
    return IDIOMA_DE_RESPALDO


def _idioma_de_usuario(db: Session, user: User, org_id: Optional[str]) -> str:
    pref = db.query(UserPreference.language).filter(UserPreference.user_id == user.id).scalar()
    return _idioma(db, pref, org_id)


def plantilla(db: Session, code: str, idioma: str, org_id: Optional[str]) -> Optional[tuple[str, str]]:
    """(asunto, html) para un papel, o None si la organizacion lo ha apagado.

    Gana la personalizacion mas concreta: de la organizacion en su idioma, de
    la organizacion sin idioma, global en su idioma, global sin idioma. Si la
    que gana esta inactiva, el aviso esta apagado.
    """
    from app.db.session import sin_filtro_de_tenant

    with sin_filtro_de_tenant(db):
        filas = db.query(EmailTemplate).filter(EmailTemplate.code == code).all()
    candidatas = [f for f in filas if f.organization_id in (org_id, None) and f.language in (idioma, None)]
    if candidatas:
        mejor = min(candidatas, key=lambda f: (f.organization_id is None, f.language is None))
        if not mejor.is_active:
            return None
        return mejor.subject, mejor.body_html
    textos = POR_DEFECTO.get(code)
    if not textos:
        return None
    return textos.get(idioma) or textos[IDIOMA_DE_RESPALDO]


_VARIABLE = re.compile(r"\{\{\s*(\w+)\s*\}\}")


def renderizar(texto: str, variables: dict, *, escapar: bool) -> str:
    def _sustituir(m: re.Match) -> str:
        valor = str(variables.get(m.group(1), ""))
        return html.escape(valor) if escapar else valor
    return _VARIABLE.sub(_sustituir, texto)


def _texto_plano(cuerpo_html: str) -> str:
    sin_etiquetas = re.sub(r"<br\s*/?>|</p>|</blockquote>", "\n", cuerpo_html)
    sin_etiquetas = re.sub(r"<[^>]+>", "", sin_etiquetas)
    return html.unescape(re.sub(r"\n{3,}", "\n\n", sin_etiquetas)).strip()


def _enlace(ticket: Ticket, dest: Destinatario) -> str:
    base = settings.FRONTEND_URL.rstrip("/")
    if dest.es_cliente:
        return f"{base}/portal?ticket={ticket.id}"
    return f"{base}/service-desk?ticket={ticket.id}"


def _asunto_con_numero(asunto: str, numero: str) -> str:
    """El numero entre corchetes en el asunto es lo que engancha la respuesta.

    El correo entrante busca `[INC-0001]` en el asunto para añadir la respuesta
    al ticket en vez de abrir otro; si una plantilla personalizada lo quita, se
    pone delante.
    """
    marca = f"[{numero}]"
    return asunto if marca in asunto else f"{marca} {asunto}"


def _fecha(dt: Optional[datetime], org_id: Optional[str], db: Session) -> str:
    if dt is None:
        return "—"
    from zoneinfo import ZoneInfo
    from app.services.sla_service import aware
    zona = ZoneInfo(_ss.get_runtime_str(db, "DEFAULT_TIMEZONE", org_id) or settings.DEFAULT_TIMEZONE)
    return aware(dt).astimezone(zona).strftime("%d/%m/%Y %H:%M")


def _variables(db: Session, ev: TicketEvent, ticket: Ticket, data: dict, dest: Destinatario) -> dict:
    et = ETIQUETAS[dest.idioma]
    org_id = ev.organization_id
    estado = getattr(ticket.status, "value", ticket.status)
    prioridad = getattr(ticket.priority, "value", ticket.priority)
    comentario = None
    if data.get("comment_id"):
        comentario = db.get(TicketComment, data["comment_id"])
    autor = et["system"]
    if comentario is not None:
        if comentario.author_user is not None:
            autor = comentario.author_user.full_name
        elif comentario.author_client is not None:
            autor = comentario.author_client.full_name
        elif comentario.author_name:
            autor = comentario.author_name
    sla_due = data.get("due") or ticket.sla_resolution_due
    if isinstance(sla_due, str):
        try:
            sla_due = datetime.fromisoformat(sla_due)
        except ValueError:
            sla_due = None
    decision = data.get("decision")
    return {
        "ticket_number": ticket.number,
        "ticket_title": ticket.title,
        "ticket_status": et["status"].get(estado, estado),
        "ticket_priority": et["priority"].get(prioridad, prioridad),
        "requester_name": _nombre_solicitante(ticket) or "",
        "assignee_name": ticket.assigned_to.full_name if ticket.assigned_to else et["unassigned"],
        # El OLA nombra la cola que lo incumplio, aunque el ticket ya este en otra.
        "group_name": data.get("group") or (ticket.assigned_group.name if ticket.assigned_group else et["no_group"]),
        # El UC nombra el contrato y su proveedor tal como estaban al vencer.
        "vendor_name": " · ".join(x for x in (data.get("vendor"), data.get("contract")) if x),
        "comment_author": autor,
        "comment_body": comentario.body if comentario is not None else (data.get("note") or data.get("action") or ""),
        "resolution": et.get(decision, decision) if decision else (ticket.resolution or ""),
        "sla_due": _fecha(sla_due, org_id, db),
        "link": _enlace(ticket, dest),
        "org_name": "",
    }


# ── Destinatarios ────────────────────────────────────────────────────────────

def _nombre_solicitante(ticket: Ticket) -> Optional[str]:
    if ticket.requester_client is not None:
        return ticket.requester_client.full_name
    if ticket.requester_user is not None:
        return ticket.requester_user.full_name
    return ticket.requester_name or ticket.requester_email


def _solicitante(db: Session, ticket: Ticket, org_id: Optional[str]) -> Optional[Destinatario]:
    """Quien pidio el ticket.

    Un agente que abre un ticket por telefono queda como `requester_user` y el
    correo del cliente va en `requester_email`: cuando los dos no coinciden,
    el solicitante es ese correo, no el agente.
    """
    if ticket.requester_client is not None:
        c: ClientUser = ticket.requester_client
        return Destinatario("requester", c.email, c.full_name, _idioma(db, c.language, org_id), es_cliente=True)
    externo = (ticket.requester_email or "").strip().lower()
    if externo and (ticket.requester_user is None or (ticket.requester_user.email or "").lower() != externo):
        return Destinatario("requester", ticket.requester_email, ticket.requester_name or ticket.requester_email,
                            _idioma(db, None, org_id))
    if ticket.requester_user is not None:
        u: User = ticket.requester_user
        return Destinatario("requester", u.email, u.full_name, _idioma_de_usuario(db, u, org_id), user_id=u.id)
    return None


def _agente(db: Session, user: Optional[User], org_id: Optional[str], papel: str = "agent") -> Optional[Destinatario]:
    if user is None or not user.is_active:
        return None
    return Destinatario(papel, user.email, user.full_name, _idioma_de_usuario(db, user, org_id), user_id=user.id)


def _usuarios(db: Session, ids) -> list[User]:
    ids = [i for i in ids if i]
    if not ids:
        return []
    return db.query(User).filter(User.id.in_(ids), User.is_active == True).all()  # noqa: E712


def _miembros_del_grupo(db: Session, group_id: Optional[str], solo_responsables: bool = False) -> list[User]:
    if not group_id:
        return []
    q = db.query(AgentGroupMember.user_id).filter(AgentGroupMember.group_id == group_id)
    if solo_responsables:
        q = q.filter(AgentGroupMember.is_lead == True)  # noqa: E712
    return _usuarios(db, [r[0] for r in q.all()])


def _observadores(db: Session, ticket: Ticket) -> list[User]:
    ids = [r[0] for r in db.query(TicketWatcher.user_id).filter(TicketWatcher.ticket_id == ticket.id).all()]
    return _usuarios(db, ids)


def _quien_atiende(db: Session, ticket: Ticket) -> list[User]:
    """El agente asignado o, sin agente, toda la cola."""
    if ticket.assigned_to is not None:
        return [ticket.assigned_to]
    return _miembros_del_grupo(db, ticket.assigned_group_id)


def _de_guardia(db: Session, ticket: Ticket, org: Optional[str]) -> list[User]:
    """Quien esta de guardia ahora en la cola del ticket, si su prioridad lo pide.

    Auditoria 2026-11: las guardias se podian definir y nadie las consultaba;
    un P1 de madrugada no avisaba a quien estaba de guardia.
    """
    from app.models.service_desk import OnCallEntry, OnCallSchedule

    prioridades = {p.strip() for p in (_ss.get_runtime_str(db, "SD_ONCALL_PRIORITIES", org) or "").split(",")}
    if not ticket.assigned_group_id or getattr(ticket.priority, "value", ticket.priority) not in prioridades:
        return []
    ahora = datetime.now(timezone.utc)
    ids = [r[0] for r in db.query(OnCallEntry.user_id).join(OnCallSchedule).filter(
        OnCallSchedule.group_id == ticket.assigned_group_id, OnCallSchedule.is_active == True,  # noqa: E712
        OnCallEntry.start_dt <= ahora, OnCallEntry.end_dt > ahora,
    ).all()]
    return _usuarios(db, ids)


def _es_del_solicitante(ticket: Ticket, ev: TicketEvent) -> bool:
    if ev.actor_client_id and ev.actor_client_id == ticket.requester_client_id:
        return True
    return bool(ev.actor_user_id and ev.actor_user_id == ticket.requester_user_id)


def destinatarios(db: Session, ev: TicketEvent, ticket: Ticket, data: dict) -> list[tuple[str, Destinatario]]:
    """(code de plantilla, destinatario) para cada aviso que produce el evento."""
    org = ev.organization_id
    g = lambda clave: _ss.get_runtime_bool(db, clave, org)  # noqa: E731
    salida: list[tuple[str, Destinatario]] = []

    def agentes(code: str, usuarios) -> None:
        for u in usuarios:
            d = _agente(db, u, org)
            if d:
                salida.append((code, d))

    def solicitante(code: str, interruptor: str) -> None:
        if g(interruptor):
            d = _solicitante(db, ticket, org)
            if d:
                salida.append((code, d))

    def guardias(code: str) -> None:
        # Van delante: si la persona de guardia es tambien el agente, cuenta
        # como guardia (y recibe el SMS).
        for u in _de_guardia(db, ticket, org):
            d = _agente(db, u, org)
            if d:
                d.guardia, d.telefono = True, u.phone
                salida.append((code, d))

    kind = ev.kind
    if kind in ("created", "sla_breached", "escalated"):
        guardias({"created": "sd.created.agent", "sla_breached": "sd.sla_breached.agent",
                  "escalated": "sd.escalated.agent"}[kind])
    if kind == "created":
        solicitante("sd.created.requester", "SD_NOTIFY_REQUESTER_ON_CREATE")
        if ticket.assigned_to is not None:
            agentes("sd.assigned.agent", [ticket.assigned_to])
        else:
            agentes("sd.created.agent", _miembros_del_grupo(db, ticket.assigned_group_id))
    elif kind == "assigned" and data.get("new"):
        agentes("sd.assigned.agent", _usuarios(db, [data["new"]]))
    elif kind == "group_assigned" and data.get("new") and ticket.assigned_to is None:
        agentes("sd.group_assigned.agent", _miembros_del_grupo(db, data["new"]))
    elif kind == "commented":
        if _es_del_solicitante(ticket, ev):
            agentes("sd.commented.agent", _quien_atiende(db, ticket) + _observadores(db, ticket))
        else:
            if data.get("is_public"):
                solicitante("sd.commented.requester", "SD_NOTIFY_REQUESTER_ON_REPLY")
            agentes("sd.commented.agent",
                    ([ticket.assigned_to] if ticket.assigned_to else []) + _observadores(db, ticket))
    elif kind == "status_changed":
        if data.get("new") == "resolved":
            solicitante("sd.resolved.requester", "SD_NOTIFY_REQUESTER_ON_RESOLVE")
        agentes("sd.updated.agent", _observadores(db, ticket))
    elif kind == "priority_changed":
        agentes("sd.updated.agent",
                ([ticket.assigned_to] if ticket.assigned_to else []) + _observadores(db, ticket))
    elif kind in ("sla_warning", "sla_breached"):
        agentes(f"sd.{kind}.agent",
                _quien_atiende(db, ticket) + _miembros_del_grupo(db, ticket.assigned_group_id, solo_responsables=True))
    elif kind == "ola_breached":
        # A la cola que lo tenia cuando vencio, aunque ya se haya movido.
        agentes("sd.ola_breached.agent",
                _quien_atiende(db, ticket) + _miembros_del_grupo(db, data.get("group_id"), solo_responsables=True))
    elif kind == "uc_breached":
        agentes("sd.uc_breached.agent",
                _quien_atiende(db, ticket) + _miembros_del_grupo(db, ticket.assigned_group_id, solo_responsables=True))
    elif kind == "escalated":
        agentes("sd.escalated.agent", _usuarios(db, data.get("recipients") or []))
    elif kind == "approval_requested":
        for u in _usuarios(db, data.get("approver_ids") or []):
            d = _agente(db, u, org, papel="approver")
            if d:
                salida.append(("sd.approval_requested.approver", d))
    elif kind == "approval_decided":
        d = _solicitante(db, ticket, org)
        if d:
            salida.append(("sd.approval_decided.requester", d))

    # Nadie recibe aviso de lo que ha hecho el mismo, ni dos veces del mismo
    # evento. Salvo el acuse de recibo: lo pide quien abre el ticket, y es
    # justo para el (le da el numero con el que seguirlo).
    vistos: set = set()
    unicos = []
    for code, d in salida:
        clave = d.user_id or (d.email or "").lower()
        if not clave or clave in vistos:
            continue
        propio = (d.user_id and d.user_id == ev.actor_user_id) or (
            d.es_cliente and ev.actor_client_id and ticket.requester_client_id == ev.actor_client_id)
        # Un usuario interno que se abre un ticket a si mismo no necesita acuse.
        if propio and (code != "sd.created.requester" or d.user_id):
            continue
        vistos.add(clave)
        unicos.append((code, d))
    return unicos


# ── Entrega ──────────────────────────────────────────────────────────────────

def _emitir_webhook(db: Session, ev: TicketEvent, ticket: Ticket, data: dict) -> None:
    from app.core.events import EventType, emit_event

    tipo = {
        "created": EventType.TICKET_CREATED,
        "assigned": EventType.TICKET_ASSIGNED,
        "escalated": EventType.TICKET_ESCALATED,
    }.get(ev.kind)
    if ev.kind == "status_changed":
        tipo = {"resolved": EventType.TICKET_RESOLVED, "closed": EventType.TICKET_CLOSED}.get(data.get("new"))
    emit_event(
        db, tipo or EventType.TICKET_UPDATED,
        {"ticket_id": ticket.id, "number": ticket.number, "kind": ev.kind, "detail": data,
         "status": getattr(ticket.status, "value", ticket.status),
         "priority": getattr(ticket.priority, "value", ticket.priority)},
        org_id=ev.organization_id, resource_type="ticket", resource_id=ticket.id,
        project_id=ticket.project_id,
    )


def _avisar(db: Session, ev: TicketEvent, ticket: Ticket, data: dict) -> dict:
    from app.services.notifications import notify_user

    org = ev.organization_id
    por_correo_a_agentes = _ss.get_runtime_bool(db, "SD_NOTIFY_AGENTS_BY_EMAIL", org)
    sms_de_guardia = _ss.get_runtime_bool(db, "SD_ONCALL_SMS", org)
    responder_a = _ss.get_runtime_str(db, "SD_INBOUND_ADDRESS", org) or None
    cuenta = {"campana": 0, "correos": 0, "fallidos": 0}
    pendientes_de_correo = []

    for code, dest in destinatarios(db, ev, ticket, data):
        textos = plantilla(db, code, dest.idioma, org)
        if textos is None:
            continue
        variables = _variables(db, ev, ticket, data, dest)
        asunto = _asunto_con_numero(renderizar(textos[0], variables, escapar=False), ticket.number)
        cuerpo = renderizar(textos[1], variables, escapar=True)
        if dest.user_id:
            notify_user(
                db, dest.user_id, TIPO_DE_AVISO.get(ev.kind, "ticket_updated"), asunto[:255],
                _texto_plano(cuerpo)[:1000], resource="tickets", resource_id=ticket.id,
                action_url=f"/service-desk?ticket={ticket.id}",
            )
            cuenta["campana"] += 1
        quiere_correo = dest.email and ev.kind not in SOLO_CAMPANA and (
            dest.papel != "agent" or por_correo_a_agentes)
        if quiere_correo:
            pendientes_de_correo.append((dest, asunto, cuerpo))
        if dest.guardia and sms_de_guardia and dest.telefono:
            from app.services.service_desk.sms_service import send_sms
            send_sms(dest.telefono, f"{asunto[:120]} {_enlace(ticket, dest)}")
            cuenta["sms"] = cuenta.get("sms", 0) + 1

    # El correo va al final: lo que ya salio no se puede deshacer si otra cosa
    # del evento falla y se reintenta.
    for dest, asunto, cuerpo in pendientes_de_correo:
        r = correo.enviar(db, org, dest.email, asunto, cuerpo, _texto_plano(cuerpo), responder_a=responder_a)
        db.add(EmailLog(
            organization_id=org, to_address=dest.email, subject=asunto[:500],
            body_preview=_texto_plano(cuerpo)[:500], status="sent" if r.enviado else "failed",
            error=r.error, sent_at=datetime.now(timezone.utc) if r.enviado else None,
            source="service_desk", source_id=ticket.id,
        ))
        cuenta["correos" if r.enviado else "fallidos"] += 1
    return cuenta


def procesar_evento(db: Session, ev: TicketEvent) -> dict:
    """Avisa y emite el webhook de un evento. No confirma la transaccion."""
    data = json.loads(ev.data or "{}")
    with _como_organizacion(db, ev.organization_id):
        ticket = db.get(Ticket, ev.ticket_id)
        if ticket is None:
            return {"omitido": "ticket borrado"}
        cuenta = _avisar(db, ev, ticket, data)
        _emitir_webhook(db, ev, ticket, data)
        from app.services.service_desk.workflow_triggers import lanzar_flujos_del_evento
        cuenta["flujos"] = lanzar_flujos_del_evento(db, ev, ticket, data)
        if ev.kind == "status_changed" and data.get("new") in ("resolved", "closed", "cancelled"):
            from app.services.service_desk.fulfillment_service import al_terminar_una_tarea
            cuenta["peticion_resuelta"] = al_terminar_una_tarea(db, ticket)
    return cuenta


def procesar_pendientes(db: Session, limite: Optional[int] = None) -> dict:
    """Procesa la bandeja, un evento por transaccion.

    En PostgreSQL cada evento se toma con `FOR UPDATE SKIP LOCKED`: dos workers
    a la vez no avisan dos veces de lo mismo. Un evento que falla se reintenta
    hasta `SD_EVENT_MAX_ATTEMPTS` y se queda con su ultimo error a la vista.
    """
    maximo = _ss.get_runtime_int(db, "SD_EVENT_MAX_ATTEMPTS")
    limite = limite or _ss.get_runtime_int(db, "SD_EVENT_BATCH_SIZE")
    hechos = 0
    # Lo que falla en esta pasada espera a la siguiente: reintentarlo en el
    # acto gastaria todos sus intentos en el mismo segundo.
    fallados: list[str] = []
    for _ in range(limite):
        ev = (
            db.query(TicketEvent)
            .filter(TicketEvent.processed_at.is_(None), TicketEvent.attempts < maximo,
                    TicketEvent.id.notin_(fallados))
            .order_by(TicketEvent.created_at, TicketEvent.id)
            .with_for_update(skip_locked=True)
            .first()
        )
        if ev is None:
            break
        ev_id = ev.id
        try:
            procesar_evento(db, ev)
            ev.processed_at = datetime.now(timezone.utc)
            ev.attempts += 1
            db.commit()
            hechos += 1
        except Exception as exc:
            db.rollback()
            logger.exception("evento de ticket %s no procesado", ev_id)
            fila = db.get(TicketEvent, ev_id)
            if fila is not None:
                fila.attempts += 1
                fila.last_error = str(exc)[:500]
                db.commit()
            fallados.append(ev_id)
    return {"procesados": hechos, "fallidos": len(fallados)}
