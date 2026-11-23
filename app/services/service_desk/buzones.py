"""Lectura del buzon de soporte: IMAP o Microsoft 365.

Cada organizacion configura su buzon en Credenciales > «Service Desk mailbox»
(`protocol` = imap o graph). Microsoft 365 no admite usuario y contraseña por
IMAP desde 2022, asi que para el se usa Graph con la aplicacion de Azure del
proveedor `ms_graph` (permiso de aplicacion Mail.ReadWrite).

Un correo se marca como leido solo despues de confirmar su ticket. Si su
proceso falla, queda en `sd_inbound_messages` como «failed» con el error y se
marca leido igualmente: reintentarlo cada dos minutos para siempre llenaria el
log y no lo arreglaria; el error queda a la vista en la pantalla del canal.
"""
from __future__ import annotations

import imaplib
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable, Iterator, Optional

import httpx
from sqlalchemy.orm import Session

from app.models.service_desk import InboundMessage
from app.services import settings_service as _ss
from app.services.integration_credentials_service import get_provider_config
from app.services.service_desk import inbound_mail
from app.services.settings_service import outbound_http_timeout
from app.core.config import settings

logger = logging.getLogger(__name__)

GRAPH = f"{settings.MICROSOFT_GRAPH_BASE}/v1.0"


@dataclass
class Mensaje:
    referencia: str                  # UID de IMAP o id de Graph
    crudo: bytes
    marcar_leido: Callable[[], None]


def organizaciones_con_buzon(db: Session) -> list[Optional[str]]:
    from sqlalchemy import or_, select
    from app.db.session import sin_filtro_de_tenant
    from app.models.mfa import Organization
    from app.models.settings import IntegrationCredential

    with sin_filtro_de_tenant(db):
        filas = db.query(IntegrationCredential.organization_id).filter(
            IntegrationCredential.provider == "sd_mailbox",
            IntegrationCredential.key == "protocol",
            IntegrationCredential.value.in_(["imap", "graph"]),
            # Revision multitenant 2026-11b: el buzon de una empresa desactivada
            # no se sigue leyendo (ni abre tickets).
            or_(IntegrationCredential.organization_id.is_(None),
                IntegrationCredential.organization_id.in_(
                    select(Organization.id).where(Organization.is_active == True))),  # noqa: E712
        ).all()
    return [f[0] for f in filas]


# ── IMAP ─────────────────────────────────────────────────────────────────────

def _host_imap(cfg: dict) -> Optional[str]:
    """23-11-2026 (01 M7, 03 «SSRF por IMAP»): el host lo escribe el admin de
    empresa; sin guardia servía para sondear la red interna (puerto libre). Un
    servidor interno legítimo se declara en `OUTBOUND_PRIVATE_HOSTS_ALLOWED`.
    Devuelve la IP validada a la que se conecta (`None` para un privado
    permitido, que va por nombre): imaplib ya no vuelve a resolver."""
    from app.core.conexion_fijada import ip_fijada
    return ip_fijada(cfg["host"], field="IMAP host")


def _abrir_imap(cfg: dict, timeout: float) -> imaplib.IMAP4_SSL:
    """IMAP sobre TLS a la IP validada (anti DNS rebinding) con SNI y
    certificado del nombre configurado. 23-11-2026: con `contexto_tls()`;
    antes `imaplib` usaba su contexto por defecto, que NO verifica el
    certificado (`SMTP_TLS_VERIFY=false` lo relaja igual que en SMTP)."""
    from app.core.conexion_fijada import Imap4SslFijado
    from app.services.notification_service import contexto_tls
    return Imap4SslFijado(cfg["host"], int(cfg.get("port") or 993), ip_fijada=_host_imap(cfg),
                          ssl_context=contexto_tls(), timeout=timeout)


def _leer_imap(cfg: dict, maximo: int) -> Iterator[Mensaje]:
    conexion = _abrir_imap(cfg, outbound_http_timeout(default=30))
    try:
        conexion.login(cfg["user"], cfg["password"])
        conexion.select(cfg.get("folder") or "INBOX")
        estado, datos = conexion.uid("search", None, "UNSEEN")
        if estado != "OK":
            raise RuntimeError(f"IMAP search: {estado}")
        for uid in (datos[0] or b"").split()[:maximo]:
            estado, partes = conexion.uid("fetch", uid, "(BODY.PEEK[])")
            if estado != "OK" or not partes or not isinstance(partes[0], tuple):
                continue
            yield Mensaje(uid.decode(), partes[0][1],
                          lambda u=uid: conexion.uid("store", u, "+FLAGS", "(\\Seen)"))
    finally:
        try:
            conexion.logout()
        except (imaplib.IMAP4.error, OSError):
            pass


# ── Microsoft 365 (Graph) ────────────────────────────────────────────────────

def _token_graph(db: Session, org_id: Optional[str]) -> str:
    """23-11-2026 (03 A-MP3): la credencial `ms_graph` de ESA empresa (o la de
    plataforma solo con `M365_PLATFORM_CREDENTIALS_ENABLED`); antes
    `get_provider_config` caia a los `AZURE_*` globales. Token cacheado por
    credencial en `m365_service`."""
    from app.services.m365_service import credenciales_de_graph, token_de_graph_sync
    cred = credenciales_de_graph(db, org_id)
    if cred is None:
        raise RuntimeError("Faltan las credenciales de Microsoft 365 (tenant, client id y secret)")
    return token_de_graph_sync(cred)


def _leer_graph(db: Session, org_id: Optional[str], cfg: dict, maximo: int) -> Iterator[Mensaje]:
    buzon = cfg.get("mailbox")
    if not buzon:
        raise RuntimeError("Falta el buzón de Microsoft 365")
    cabeceras = {"Authorization": f"Bearer {_token_graph(db, org_id)}"}
    with httpx.Client(base_url=GRAPH, headers=cabeceras, timeout=outbound_http_timeout(db, default=30)) as cliente:
        r = cliente.get(f"/users/{buzon}/mailFolders/inbox/messages",
                        params={"$filter": "isRead eq false", "$top": maximo, "$select": "id",
                                "$orderby": "receivedDateTime"})
        r.raise_for_status()
        for item in r.json().get("value", []):
            mid = item["id"]
            mime = cliente.get(f"/users/{buzon}/messages/{mid}/$value")
            mime.raise_for_status()
            yield Mensaje(mid, mime.content,
                          lambda m=mid: cliente.patch(f"/users/{buzon}/messages/{m}",
                                                      json={"isRead": True}).raise_for_status())


# ── Pasada ───────────────────────────────────────────────────────────────────

def leer_buzon(db: Session, org_id: Optional[str]) -> dict:
    """Lee los correos sin leer de un buzon y los convierte en tickets o comentarios."""
    cfg = get_provider_config(db, "sd_mailbox", org_id=org_id)
    protocolo = (cfg.get("protocol") or "").strip().lower()
    maximo = _ss.get_runtime_int(db, "SD_MAIL_MAX_PER_RUN", org_id)
    if protocolo == "imap":
        if not (cfg.get("host") and cfg.get("user") and cfg.get("password")):
            return {"error": "Faltan host, usuario o contraseña del IMAP"}
        mensajes = _leer_imap(cfg, maximo)
    elif protocolo == "graph":
        mensajes = _leer_graph(db, org_id, cfg, maximo)
    else:
        return {"error": f"Protocolo desconocido: {protocolo or 'vacío'}"}

    cuenta = {"created": 0, "commented": 0, "ignored": 0, "failed": 0}
    for m in mensajes:
        try:
            correo = inbound_mail.desde_mime(m.crudo)
            r = inbound_mail.procesar(db, org_id, correo)
            db.commit()
            cuenta[r.accion] += 1
        except Exception as exc:
            db.rollback()
            logger.exception("correo %s del buzón no procesado", m.referencia)
            _anotar_fallo(db, org_id, m, exc)
            cuenta["failed"] += 1
        m.marcar_leido()
    return cuenta


def _anotar_fallo(db: Session, org_id: Optional[str], m: Mensaje, exc: Exception) -> None:
    try:
        correo = inbound_mail.desde_mime(m.crudo)
        clave, remitente = inbound_mail.clave_del_mensaje(correo), correo.remitente[:255] or None
    except Exception:
        logger.debug("_anotar_fallo: excepcion ignorada", exc_info=True)
        clave, remitente = f"ilegible:{m.referencia}"[:255], None
    if db.query(InboundMessage.id).filter(InboundMessage.message_id == clave,
                                          InboundMessage.organization_id == org_id).first():
        return
    db.add(InboundMessage(organization_id=org_id, message_id=clave, channel="email", sender=remitente,
                          outcome="failed", reason=str(exc)[:255], received_at=datetime.now(timezone.utc)))
    db.commit()


def leer_todos(db: Session) -> dict:
    """Una pasada por el buzon de cada organizacion que tenga uno configurado."""
    resultado = {}
    for org_id in organizaciones_con_buzon(db):
        try:
            resultado[org_id or "global"] = leer_buzon(db, org_id)
        except Exception as exc:
            db.rollback()
            logger.exception("buzón de %s no leído", org_id)
            # Auditoria 2026-11-22 (4.3): la clase del error, no su texto (que
            # trae hosts, puertos y respuestas del servidor remoto).
            resultado[org_id or "global"] = {"error": type(exc).__name__}
    return resultado


def probar_buzon(db: Session, org_id: Optional[str]) -> dict:
    """Se conecta y cuenta los no leidos, sin procesar ni marcar nada."""
    cfg = get_provider_config(db, "sd_mailbox", org_id=org_id)
    protocolo = (cfg.get("protocol") or "").strip().lower()
    try:
        if protocolo == "imap":
            conexion = _abrir_imap(cfg, outbound_http_timeout(db, default=20))
            try:
                conexion.login(cfg["user"], cfg["password"])
                conexion.select(cfg.get("folder") or "INBOX", readonly=True)
                _, datos = conexion.uid("search", None, "UNSEEN")
                return {"ok": True, "protocol": "imap", "unread": len((datos[0] or b"").split()),
                        "code": "buzon_prueba_ok"}
            finally:
                conexion.logout()
        if protocolo == "graph":
            buzon = cfg.get("mailbox")
            if not buzon:
                return {"ok": False, "protocol": "graph", "error": "Falta el buzón de Microsoft 365",
                        "code": "buzon_falta_m365"}
            r = httpx.get(f"{GRAPH}/users/{buzon}/mailFolders/inbox", timeout=outbound_http_timeout(db, default=20),
                          headers={"Authorization": f"Bearer {_token_graph(db, org_id)}"})
            r.raise_for_status()
            return {"ok": True, "protocol": "graph", "unread": r.json().get("unreadItemCount"),
                    "code": "buzon_prueba_ok"}
        # Incidencia 10 (23-11-2026): cada resultado lleva `code` (texto traducido en la interfaz).
        return {"ok": False, "protocol": protocolo or None, "error": "Buzón sin configurar",
                "code": "buzon_sin_configurar"}
    except (imaplib.IMAP4.error, OSError, KeyError, httpx.HTTPError, RuntimeError) as exc:
        # Auditoria 2026-11-22 (4.3): sin `str(exc)`: con un host interno
        # («connection refused» frente a «timed out») servia de sonda de red.
        logger.info("prueba del buzon de %s fallida", org_id, exc_info=True)
        return {"ok": False, "protocol": protocolo, "error": type(exc).__name__,
                "code": "buzon_conexion_fallida", "params": {"error": type(exc).__name__}}


def ultimos_mensajes(db: Session, limite: int) -> list[dict]:
    """Los ultimos correos recibidos y que se hizo con cada uno."""
    from app.models.service_desk import Ticket

    filas = (db.query(InboundMessage, Ticket.number)
             .outerjoin(Ticket, Ticket.id == InboundMessage.ticket_id)
             .order_by(InboundMessage.received_at.desc()).limit(limite).all())
    return [{
        "id": m.id, "received_at": m.received_at.isoformat() if m.received_at else None,
        "sender": m.sender, "outcome": m.outcome, "reason": m.reason,
        "ticket_id": m.ticket_id, "ticket_number": numero, "channel": m.channel,
    } for m, numero in filas]
