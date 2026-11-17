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

**Hilos de Slack ↔ ticket (Events API, 17-11-2026)**

- `POST /sd/channels/slack/events`: `url_verification` (firmada; vale el signing
  secret de cualquier empresa o el global) y `event_callback` con eventos
  `message` (canales publicos, privados y MPIM). La firma se verifica con el
  signing secret de la empresa duena del workspace (`SLACK_TEAM_ID`); el evento
  se procesa fuera de la peticion (`encolar`): Slack pide respuesta en 3 s.
- **Vinculo hilo ↔ ticket**: es una conversacion del canal `slack` con
  `external_id = <canal>:<ts del mensaje raiz>`. Nace al crear el ticket con
  `/contecflow ticket` (con token de bot, la tarjeta se publica en el canal y su
  hilo queda atado), al publicar el aviso de un ticket nuevo en el canal de
  avisos de la empresa (`SD_SLACK_TICKET_CHANNEL`) o al escribir en un canal de
  entrada (`SD_SLACK_INTAKE_CHANNELS`: cada mensaje raiz abre un ticket).
- **Respuestas del hilo**: entran como comentario publico del ticket. Autor: el
  usuario de Contecflow con el mismo correo (`users.info`, scope
  `users:read.email`); si no, el contacto del portal con ese correo; si no,
  «Cliente externo». Los ficheros (`files`) se descargan con el token del bot
  (solo `files.slack.com`, con tope) y pasan por `adjuntos_de_canal`.
- **Sin bucles**: se ignoran los mensajes de bots (`bot_id`, `subtype`
  `bot_message`), los del propio bot (`authorizations[].user_id`) y las
  ediciones y borrados. Lo que entra queda unido a su comentario
  (`ticket_comment_id`), asi que la salida no lo devuelve al hilo.
- **Salida**: la respuesta publica de un agente en el ticket sale al hilo
  (`salida_por_canales`), en el idioma del cliente si la traduccion lo hace.

El token del bot es la credencial cifrada `slack.bot_token` de la empresa
(Ajustes → Credenciales → Slack). Todas las llamadas a la API van por
`cliente_httpx` con la espera saliente.
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
#: Unico origen valido de los ficheros (y de la subida de los nuestros).
HOST_DE_FICHEROS = "files.slack.com"
#: Subtipos de mensaje que entran al ticket (el resto: ediciones, uniones, bots...).
SUBTIPOS_ADMITIDOS = (None, "file_share", "thread_broadcast")
#: Cache de personas de Slack (correo y nombre) por (empresa, usuario): segundos.
TTL_DE_PERSONAS_S = 600
_personas: dict[tuple, tuple[float, Optional[str], Optional[str]]] = {}


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
    # Con token de bot, la tarjeta se publica en el canal y su hilo queda atado
    # al ticket (el receptor del comando deja el canal en `db.info`).
    canal = db.info.get("slack_canal")
    if canal and publicar_tarjeta_en_hilo(db, t, canal, visitante=usuario.full_name):
        return {"response_type": "ephemeral", "text": f"Ticket creado: {t.number}. Responde en su hilo."}
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


# ── API de Slack con el token del bot ─────────────────────────────────────────

def token_del_bot(db: Session, org_id: Optional[str]) -> Optional[str]:
    """El token del bot de ESA empresa (credencial cifrada); sin respaldo global."""
    if not org_id:
        return None
    from app.services.integration_credentials_service import secreto_propio_de_la_organizacion
    return secreto_propio_de_la_organizacion(db, "slack", "bot_token", "SLACK_BOT_TOKEN", org_id)


def _cliente(timeout: float):
    from app.core.outbound_url import cliente_httpx
    return cliente_httpx(timeout=timeout, follow_redirects=False)


def _espera(db: Session) -> float:
    from app.services.settings_service import outbound_http_timeout
    return outbound_http_timeout(db, default=10)


def api(db: Session, org_id: str, metodo: str, *, json_: Optional[dict] = None,
        params: Optional[dict] = None, form: Optional[dict] = None) -> Optional[dict]:
    """Llama a `metodo` de la Web API de Slack. None si no hay token o falla (queda en el log)."""
    token = token_del_bot(db, org_id)
    if not token:
        logger.info("Slack sin token de bot en la empresa %s: no se llama a %s", org_id, metodo)
        return None
    url = f"{(settings.SLACK_API_BASE or 'https://slack.com/api').rstrip('/')}/{metodo}"
    cabeceras = {"Authorization": f"Bearer {token}"}
    try:
        with _cliente(_espera(db)) as c:
            if params is not None:
                r = c.get(url, headers=cabeceras, params=params)
            elif form is not None:
                r = c.post(url, headers=cabeceras, data=form)
            else:
                r = c.post(url, headers={**cabeceras, "Content-Type": "application/json; charset=utf-8"},
                           json=json_ or {})
            r.raise_for_status()
            datos = r.json()
    except (httpx.HTTPError, ValueError, PermissionError):
        logger.warning("Slack: fallo en %s", metodo, exc_info=True)
        return None
    if not datos.get("ok"):
        logger.warning("Slack: %s respondio %s", metodo, datos.get("error"))
        return None
    return datos


def publicar(db: Session, org_id: str, canal: str, texto: str, *, blocks: Optional[list] = None,
             thread_ts: Optional[str] = None) -> Optional[str]:
    """`chat.postMessage`. Devuelve el `ts` del mensaje o None."""
    cuerpo: dict = {"channel": canal, "text": texto[:39000]}
    if blocks:
        cuerpo["blocks"] = blocks
    if thread_ts:
        cuerpo["thread_ts"] = thread_ts
    r = api(db, org_id, "chat.postMessage", json_=cuerpo)
    return (r or {}).get("ts")


def clave_de_hilo(canal: str, ts: str) -> str:
    return f"{canal}:{ts}"


def conversacion_del_hilo(db: Session, org_id: str, canal: str, ts: str):
    from app.models.service_desk import ChannelConversation
    return db.query(ChannelConversation).filter(
        ChannelConversation.organization_id == org_id, ChannelConversation.channel == "slack",
        ChannelConversation.external_id == clave_de_hilo(canal, ts)).first()


def vincular_hilo(db: Session, ticket, canal: str, ts: str, visitante: Optional[str] = None):
    """Ata el hilo (`canal`, `ts`) al ticket: una conversacion del canal `slack`."""
    from app.models.service_desk import ChannelConversation
    conv = conversacion_del_hilo(db, ticket.organization_id, canal, ts)
    if conv is None:
        conv = ChannelConversation(organization_id=ticket.organization_id, channel="slack",
                                   external_id=clave_de_hilo(canal, ts), ticket_id=ticket.id,
                                   visitor_name=(visitante or ticket.requester_name or None), status="agent")
        db.add(conv)
        db.flush()
    return conv


def publicar_tarjeta_en_hilo(db: Session, ticket, canal: str, *, visitante: Optional[str] = None,
                             thread_ts: Optional[str] = None) -> bool:
    """Publica la tarjeta del ticket (o la cuelga del mensaje `thread_ts`) y ata el hilo."""
    datos = tarjeta(ticket)
    ts = publicar(db, ticket.organization_id, canal, datos["text"], blocks=datos["blocks"], thread_ts=thread_ts)
    if not ts:
        return False
    vincular_hilo(db, ticket, canal, thread_ts or ts, visitante)
    db.commit()
    return True


def publicar_aviso_de_ticket(db: Session, ticket) -> bool:
    """Ticket nuevo: su tarjeta al canal de avisos de la empresa (`SD_SLACK_TICKET_CHANNEL`)
    y su hilo atado. Nada si no hay canal, no hay token o el ticket ya tiene hilo."""
    from app.models.service_desk import ChannelConversation
    from app.services.settings_service import get_runtime_str
    canal = (get_runtime_str(db, "SD_SLACK_TICKET_CHANNEL", ticket.organization_id) or "").strip()
    if not canal or not token_del_bot(db, ticket.organization_id):
        return False
    ya = db.query(ChannelConversation.id).filter(ChannelConversation.ticket_id == ticket.id,
                                                 ChannelConversation.channel == "slack").first()
    if ya:
        return False
    return publicar_tarjeta_en_hilo(db, ticket, canal)


def _con_autor(autor: Optional[str], texto: str) -> str:
    return f"*{autor}*: {texto}" if autor else texto


def responder_en_hilo(db: Session, conv, texto: str, autor: Optional[str] = None) -> Optional[str]:
    """Respuesta del ticket al hilo atado. Devuelve el `ts` o None."""
    canal, _, ts = (conv.external_id or "").partition(":")
    if not canal or not ts:
        return None
    return publicar(db, conv.organization_id, canal, _con_autor(autor, texto), thread_ts=ts)


def subir_al_hilo(db: Session, conv, fichero, comentario: str = "") -> Optional[str]:
    """Sube un documento del ticket al hilo (subida externa de Slack). Devuelve el id del fichero."""
    canal, _, ts = (conv.external_id or "").partition(":")
    org = conv.organization_id
    if not canal or not ts:
        return None
    paso1 = api(db, org, "files.getUploadURLExternal",
                form={"filename": fichero.nombre, "length": str(len(fichero.contenido))})
    if not paso1:
        return None
    destino = urlparse(paso1.get("upload_url") or "")
    if destino.scheme != "https" or destino.hostname != HOST_DE_FICHEROS:
        logger.warning("Slack: URL de subida rechazada (%s)", destino.hostname)
        return None
    try:
        with _cliente(_espera(db)) as c:
            c.post(paso1["upload_url"], content=fichero.contenido,
                   headers={"Content-Type": fichero.tipo or "application/octet-stream"}).raise_for_status()
    except (httpx.HTTPError, PermissionError):
        logger.warning("Slack: no se pudo subir %s", fichero.nombre, exc_info=True)
        return None
    cuerpo = {"files": [{"id": paso1.get("file_id"), "title": fichero.nombre}], "channel_id": canal,
              "thread_ts": ts}
    if comentario:
        cuerpo["initial_comment"] = comentario[:4000]
    return paso1.get("file_id") if api(db, org, "files.completeUploadExternal", json_=cuerpo) else None


# ── Events API ────────────────────────────────────────────────────────────────

def _secretos_de_firma(db: Session) -> list[str]:
    """Todos los signing secrets (empresas y global): solo para `url_verification`,
    que Slack firma pero no dice de que workspace es."""
    from app.core.encryption import decrypt_value
    from app.db.session import sin_filtro_de_tenant
    from app.models.settings import AppSetting, IntegrationCredential
    secretos = [settings.SLACK_SIGNING_SECRET] if settings.SLACK_SIGNING_SECRET else []
    with sin_filtro_de_tenant(db):
        for f in db.query(IntegrationCredential).filter(IntegrationCredential.provider == "slack",
                                                        IntegrationCredential.key == "signing_secret").all():
            valor = decrypt_value(f.value_encrypted) if f.value_encrypted else f.value
            if valor:
                secretos.append(str(valor))
        secretos += [a.value for a in db.query(AppSetting).filter(AppSetting.key == "SLACK_SIGNING_SECRET").all()
                     if a.value]
    return secretos


def leer_evento(db: Session, cuerpo: bytes, marca: str, firma: str) -> tuple[dict, Optional[str]]:
    """Verifica la peticion de la Events API. Devuelve (payload, empresa).

    `url_verification` no trae workspace: vale cualquier signing secret conocido
    (sigue haciendo falta conocer uno). El resto, el de la empresa del `team_id`.
    """
    from app.services.integrations import (
        VinculoAmbiguo, organizacion_del_workspace_de_slack, secreto_de_firma_de_slack,
    )
    try:
        payload = json.loads(cuerpo or b"{}")
    except ValueError:
        raise ErrorDeDominio(400, "Cuerpo de Slack ilegible")
    if payload.get("type") == "url_verification":
        if not any(firma_valida(s, marca, cuerpo, firma) for s in _secretos_de_firma(db)):
            raise ErrorDeDominio(403, "Invalid Slack signature")
        return payload, None
    try:
        org = organizacion_del_workspace_de_slack(db, payload.get("team_id"))
    except VinculoAmbiguo:
        raise ErrorDeDominio(403, "Slack workspace linked to several organizations")
    if org is None:
        raise ErrorDeDominio(403, "Slack workspace not linked to an organization (SLACK_TEAM_ID)")
    if not firma_valida(secreto_de_firma_de_slack(db, org), marca, cuerpo, firma):
        raise ErrorDeDominio(403, "Invalid Slack signature")
    return payload, org


def _es_del_bot(evento: dict, payload: dict) -> bool:
    """Mensajes que no deben entrar: de bots (incluido el nuestro), ediciones, borrados..."""
    if evento.get("bot_id") or evento.get("subtype") not in SUBTIPOS_ADMITIDOS:
        return True
    propios = {a.get("user_id") for a in payload.get("authorizations") or [] if a.get("is_bot")}
    autor = evento.get("user")
    return not autor or autor in propios


def _persona(db: Session, org_id: str, slack_user: str) -> tuple[Optional[str], Optional[str]]:
    """(correo, nombre) del usuario de Slack (`users.info`), con cache corta."""
    clave = (org_id, slack_user)
    hit = _personas.get(clave)
    if hit and hit[0] > time.time():
        return hit[1], hit[2]
    r = api(db, org_id, "users.info", params={"user": slack_user}) or {}
    perfil = (r.get("user") or {}).get("profile") or {}
    correo = (perfil.get("email") or "").strip().lower() or None
    nombre = perfil.get("real_name") or perfil.get("display_name") or (r.get("user") or {}).get("name")
    if r:
        _personas[clave] = (time.time() + TTL_DE_PERSONAS_S, correo, nombre)
    return correo, nombre


def _quien(db: Session, org_id: str, slack_user: str):
    """(usuario interno, contacto del portal, nombre a mostrar) por el correo de Slack."""
    from sqlalchemy import func
    from app.models.client_portal import ClientUser
    from app.models.user import User
    correo, nombre = _persona(db, org_id, slack_user)
    if correo:
        usuarios = db.query(User).filter(User.organization_id == org_id, User.is_active == True,  # noqa: E712
                                         func.lower(User.email) == correo).limit(2).all()
        if len(usuarios) == 1:
            return usuarios[0], None, usuarios[0].full_name
        contactos = db.query(ClientUser).filter(ClientUser.organization_id == org_id,
                                                ClientUser.is_active == True,  # noqa: E712
                                                func.lower(ClientUser.email) == correo).limit(2).all()
        if len(contactos) == 1:
            return None, contactos[0], contactos[0].full_name
    return None, None, f"Cliente externo ({nombre})" if nombre else "Cliente externo"


def _ficheros(db: Session, org_id: str, evento: dict) -> tuple[list, list[str]]:
    """Los ficheros del mensaje bajados con el token del bot, y las notas de los que no."""
    from app.core.errores import ErrorDeDominio as _Error
    from app.services.service_desk import adjuntos_de_canal
    token = token_del_bot(db, org_id)
    tope = adjuntos_de_canal.tope_en_bytes(db, org_id)
    bajados, notas = [], []
    for f in (evento.get("files") or [])[:10]:
        nombre = adjuntos_de_canal.nombre_de_fichero(f.get("name"), f.get("mimetype"), "slack-fichero")
        url = f.get("url_private_download") or f.get("url_private") or ""
        destino = urlparse(url)
        if not token or destino.scheme != "https" or destino.hostname != HOST_DE_FICHEROS:
            notas.append(f"[adjunto no disponible: {nombre}]")
            continue
        if int(f.get("size") or 0) > tope:
            notas.append(f"[adjunto rechazado (size): {nombre}]")
            continue
        try:
            with _cliente(_espera(db)) as c:
                contenido, tipo = adjuntos_de_canal.descargar_acotado(
                    c, url, headers={"Authorization": f"Bearer {token}"}, tope=tope, timeout=_espera(db))
        except _Error:
            notas.append(f"[adjunto rechazado (size): {nombre}]")
            continue
        except (httpx.HTTPError, PermissionError):
            logger.warning("Slack: no se pudo bajar %s", nombre, exc_info=True)
            notas.append(f"[adjunto no disponible: {nombre}]")
            continue
        bajados.append(adjuntos_de_canal.Fichero(nombre=nombre, tipo=f.get("mimetype") or tipo or
                                                 "application/octet-stream", contenido=contenido))
    return bajados, notas


def _canales_de_entrada(db: Session, org_id: str) -> set[str]:
    from app.services.settings_service import get_runtime_str
    crudo = get_runtime_str(db, "SD_SLACK_INTAKE_CHANNELS", org_id) or ""
    return {c.strip() for c in crudo.split(",") if c.strip()}


def procesar_evento(db: Session, payload: dict) -> dict:
    """Un `event_callback` ya verificado. La sesion corre en la empresa del workspace."""
    from app.models.service_desk import ChannelMessage
    from app.services.service_desk import conversaciones
    org = db.info.get("organization_id")
    evento = payload.get("event") or {}
    if not org or evento.get("type") != "message" or _es_del_bot(evento, payload):
        return {"ignored": True}
    canal, ts = evento.get("channel"), evento.get("ts")
    raiz = evento.get("thread_ts")
    if not canal or not ts:
        return {"ignored": True}
    texto = (evento.get("text") or "").strip()

    if raiz and raiz != ts:
        # Primero el vinculo: un hilo sin ticket no gasta llamadas a Slack.
        conv = conversacion_del_hilo(db, org, canal, raiz)
        if conv is None or not conv.ticket_id:
            return {"ignored": True, "reason": "thread_not_linked"}
        if db.query(ChannelMessage.id).filter(ChannelMessage.conversation_id == conv.id,
                                              ChannelMessage.external_message_id == ts).first():
            return {"comment": False, "duplicate": True}
        usuario, contacto, nombre = _quien(db, org, evento["user"])
        adjuntos, notas = _ficheros(db, org, evento)
        if conv.status == "closed":
            conv.status = "agent"
        r = conversaciones.mensaje_del_cliente(
            db, conv, texto or ("[adjunto]" if adjuntos or notas else "[vacío]"), client_user=contacto,
            external_message_id=ts, autor_usuario=usuario, autor_nombre=nombre,
            adjunto=adjuntos or None, nota_de_adjunto="\n".join(notas) or None)
        return {"comment": not r["duplicate"], "duplicate": r["duplicate"]}

    if canal not in _canales_de_entrada(db, org):
        return {"ignored": True, "reason": "not_intake_channel"}
    if conversacion_del_hilo(db, org, canal, ts) is not None:
        return {"duplicate": True}
    usuario, contacto, nombre = _quien(db, org, evento["user"])
    adjuntos, notas = _ficheros(db, org, evento)
    from app.services.service_desk.ticket_creation_service import build_channel_ticket
    t = build_channel_ticket(db, org_id=org, titulo=(texto.splitlines() or ["Slack"])[0][:200] or "Slack",
                             descripcion=texto or "[adjunto]", source="slack", requester_user=usuario,
                             requester_client=contacto, requester_name=nombre,
                             requester_email=(usuario or contacto).email if (usuario or contacto) else None)
    db.flush()
    conv = vincular_hilo(db, t, canal, ts, nombre)
    # El mensaje raiz es la descripcion: se apunta para no repetirlo, sin comentario.
    m = conversaciones.anotar(db, conv, "in", "customer", texto or "[adjunto]", external_message_id=ts)
    from app.services.service_desk import adjuntos_de_canal
    for f in adjuntos:
        res = adjuntos_de_canal.guardar(db, t, nombre=f.nombre, tipo=f.tipo, contenido=f.contenido, origen="slack")
        if res.document_id and m is not None and not m.attachment_document_id:
            m.attachment_document_id = res.document_id
        elif not res.document_id:
            notas.append(f"[adjunto rechazado ({res.motivo}): {res.nombre}]")
    if notas:
        t.description = (t.description or "") + "\n" + "\n".join(notas)
    db.commit()
    publicar_tarjeta_en_hilo(db, t, canal, visitante=nombre, thread_ts=ts)
    return {"ticket": t.number}
