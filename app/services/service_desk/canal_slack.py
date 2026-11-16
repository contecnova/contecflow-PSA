"""Slack como app interactiva del service desk (mejoras de mercado 16-11-2026).

Antes Slack solo recibia avisos y el comando `/contecflow ticket` abria un
ticket sin empresa, con numeracion propia y sin SLA. Ahora:

- **Comandos** (los del bot comun de `integrations_hub`, Slack y Teams):
  `ticket <asunto>` abre el ticket por el camino de los canales (empresa,
  numeracion, SLA, enrutado y avisos) y contesta con su tarjeta;
  `ver <INC-0042>`, `comentar <INC-0042> <texto>`, `asignarme <INC-0042>`,
  `encurso <INC-0042>` y `resolver <INC-0042> <texto>`.
- **Botones** de la tarjeta (`POST /sd/channels/slack/interactions`):
  «Asignarme», «En curso» y «Abrir». La peticion se verifica con la firma de
  Slack (`X-Slack-Signature`, HMAC-SHA256 con el signing secret de la empresa
  del workspace) y la marca de tiempo; la tarjeta se actualiza por el
  `response_url` de Slack (solo `hooks.slack.com`, con la espera saliente).

Quien actua es el usuario de Contecflow que corresponde al de Slack (mismo
criterio que el bot), con sus permisos: solo ve y toca los tickets que vera en
la aplicacion.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import time
from typing import Optional
from urllib.parse import parse_qs, urlparse

import httpx
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.errores import ErrorDeDominio

logger = logging.getLogger(__name__)

#: Ventana de Slack para la marca de tiempo de una peticion firmada (su documentacion: 5 min).
TOLERANCIA_DE_FIRMA_S = 300
#: Unico destino valido de un `response_url`.
HOST_DE_RESPUESTA = "hooks.slack.com"


def _v(x):
    return getattr(x, "value", x)


def firma_valida(secreto: Optional[str], marca: str, cuerpo: bytes, firma: str, ahora: Optional[float] = None) -> bool:
    if not secreto or not firma:
        return False
    try:
        if abs((ahora or time.time()) - float(marca)) > TOLERANCIA_DE_FIRMA_S:
            return False
    except (TypeError, ValueError):
        return False
    base = f"v0:{marca}:{cuerpo.decode(errors='replace')}"
    esperada = "v0=" + hmac.new(secreto.encode(), base.encode(), hashlib.sha256).hexdigest()
    return hmac.compare_digest(esperada, firma)


def tarjeta(ticket, texto: Optional[str] = None) -> dict:
    """Mensaje de Slack (Block Kit) con el ticket y sus botones."""
    url = f"{(settings.FRONTEND_URL or '').rstrip('/')}/service-desk?ticket={ticket.id}"
    asignado = ticket.assigned_to.full_name if getattr(ticket, "assigned_to", None) else "—"
    return {
        "response_type": "in_channel",
        "text": texto or f"{ticket.number} · {ticket.title}",
        "blocks": [
            {"type": "section", "text": {"type": "mrkdwn", "text": f"*{ticket.number}* · {ticket.title}"}},
            {"type": "context", "elements": [{"type": "mrkdwn", "text":
                f"{_v(ticket.status)} · {_v(ticket.priority)} · {asignado}"}]},
            {"type": "actions", "elements": [
                {"type": "button", "action_id": "sd_assign_me", "value": ticket.id,
                 "text": {"type": "plain_text", "text": "Asignarme"}},
                {"type": "button", "action_id": "sd_in_progress", "value": ticket.id,
                 "text": {"type": "plain_text", "text": "En curso"}},
                {"type": "button", "action_id": "sd_open", "url": url,
                 "text": {"type": "plain_text", "text": "Abrir"}},
            ]},
        ],
    }


def _ticket_por_numero(db: Session, usuario, numero: str):
    from app.models.service_desk import Ticket
    from app.services.service_desk.scoping import scope_ticket_query
    t = scope_ticket_query(db.query(Ticket), db, usuario).filter(Ticket.number == numero.strip().upper()).first()
    if t is None:
        raise ErrorDeDominio(404, f"No encuentro el ticket {numero}")
    return t


def _actualizar(db: Session, ticket, usuario, **cambios) -> None:
    from app.schemas.service_desk import TicketUpdateIn
    from app.services.service_desk.ticket_update_service import apply_ticket_update
    apply_ticket_update(db, ticket, ticket.id, TicketUpdateIn(**cambios), current_user_id=usuario.id,
                        old_assigned_to=ticket.assigned_to_user_id, old_support_level=ticket.support_level)
    db.commit()
    db.refresh(ticket)


def crear(db: Session, texto: str, usuario) -> dict:
    from app.services.service_desk.ticket_creation_service import build_channel_ticket
    asunto = (texto or "").strip()
    if not asunto:
        return {"response_type": "ephemeral", "text": "Uso: ticket <asunto>"}
    t = build_channel_ticket(db, org_id=usuario.organization_id, titulo=asunto[:255], descripcion=asunto,
                             source="slack", requester_user=usuario, requester_name=usuario.full_name,
                             requester_email=usuario.email)
    db.commit()
    db.refresh(t)
    return tarjeta(t, f"Ticket creado: {t.number}")


def ver(db: Session, texto: str, usuario) -> dict:
    return {**tarjeta(_ticket_por_numero(db, usuario, texto.split()[0] if texto.split() else "")),
            "response_type": "ephemeral"}


def comentar(db: Session, texto: str, usuario) -> dict:
    partes = (texto or "").split(None, 1)
    if len(partes) < 2:
        return {"response_type": "ephemeral", "text": "Uso: comentar <número> <texto>"}
    t = _ticket_por_numero(db, usuario, partes[0])
    from app.services.service_desk.comment_service import add_internal_comment
    add_internal_comment(db, t, t.id, partes[1], True, usuario)
    db.commit()
    return {"response_type": "ephemeral", "text": f"Comentario añadido a {t.number}"}


def asignarme(db: Session, texto: str, usuario) -> dict:
    t = _ticket_por_numero(db, usuario, (texto or "").strip())
    _actualizar(db, t, usuario, assigned_to_user_id=usuario.id)
    return tarjeta(t, f"{t.number} asignado a {usuario.full_name}")


def en_curso(db: Session, texto: str, usuario) -> dict:
    t = _ticket_por_numero(db, usuario, (texto or "").strip())
    _actualizar(db, t, usuario, status="in_progress")
    return tarjeta(t, f"{t.number} en curso")


def resolver(db: Session, texto: str, usuario) -> dict:
    partes = (texto or "").split(None, 1)
    if len(partes) < 2:
        return {"response_type": "ephemeral", "text": "Uso: resolver <número> <resolución>"}
    t = _ticket_por_numero(db, usuario, partes[0])
    t.resolution = partes[1]
    _actualizar(db, t, usuario, status="resolved")
    return tarjeta(t, f"{t.number} resuelto")


# ── Botones ───────────────────────────────────────────────────────────────────

def leer_interaccion(db: Session, cuerpo: bytes, marca: str, firma: str) -> tuple[dict, object]:
    """Verifica la peticion de Slack y devuelve (payload, usuario de Contecflow)."""
    from app.services.integrations import (
        VinculoAmbiguo, find_user_by_slack_name, organizacion_del_workspace_de_slack, secreto_de_firma_de_slack,
    )
    try:
        payload = json.loads((parse_qs(cuerpo.decode(errors="replace")).get("payload") or ["{}"])[0])
    except ValueError:
        raise ErrorDeDominio(400, "Payload de Slack ilegible")
    equipo = (payload.get("team") or {}).get("id")
    try:
        org = organizacion_del_workspace_de_slack(db, equipo)
    except VinculoAmbiguo:
        raise ErrorDeDominio(403, "Slack workspace linked to several organizations")
    if not firma_valida(secreto_de_firma_de_slack(db, org), marca, cuerpo, firma):
        raise ErrorDeDominio(403, "Invalid Slack signature")
    persona = payload.get("user") or {}
    usuario = find_user_by_slack_name(db, persona.get("username") or persona.get("name") or "", equipo)
    return payload, usuario


def procesar_interaccion(db: Session, payload: dict, usuario) -> dict:
    """Aplica el boton pulsado y devuelve la tarjeta nueva (o un aviso)."""
    from app.services.service_desk.scoping import get_scoped_ticket_or_404
    if usuario is None:
        return {"response_type": "ephemeral", "replace_original": False,
                "text": "No encuentro tu usuario de Contecflow para este Slack."}
    from app.db.session import publicar_contexto_de_tenant
    publicar_contexto_de_tenant(db, usuario)
    accion = ((payload.get("actions") or [{}])[0])
    if accion.get("action_id") == "sd_open":
        return {}
    ticket = get_scoped_ticket_or_404(db, usuario, accion.get("value") or "")
    if accion.get("action_id") == "sd_assign_me":
        _actualizar(db, ticket, usuario, assigned_to_user_id=usuario.id)
    elif accion.get("action_id") == "sd_in_progress":
        _actualizar(db, ticket, usuario, status="in_progress")
    else:
        return {}
    return {**tarjeta(ticket), "replace_original": True}


def responder_por_url(db: Session, response_url: Optional[str], mensaje: dict) -> bool:
    """Manda la tarjeta nueva al `response_url` de Slack (solo hooks.slack.com)."""
    from app.services.settings_service import outbound_http_timeout
    if not response_url or not mensaje:
        return False
    destino = urlparse(response_url)
    if destino.scheme != "https" or destino.hostname != HOST_DE_RESPUESTA:
        logger.warning("response_url de Slack rechazado: %s", destino.hostname)
        return False
    try:
        httpx.post(response_url, json=mensaje, timeout=outbound_http_timeout(db, default=10)).raise_for_status()
        return True
    except httpx.HTTPError:
        logger.warning("Slack: no se pudo actualizar la tarjeta", exc_info=True)
        return False
