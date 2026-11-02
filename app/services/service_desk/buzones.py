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

logger = logging.getLogger(__name__)

GRAPH = "https://graph.microsoft.com/v1.0"


@dataclass
class Mensaje:
    referencia: str                  # UID de IMAP o id de Graph
    crudo: bytes
    marcar_leido: Callable[[], None]


def organizaciones_con_buzon(db: Session) -> list[Optional[str]]:
    from app.db.session import sin_filtro_de_tenant
    from app.models.settings import IntegrationCredential

    with sin_filtro_de_tenant(db):
        filas = db.query(IntegrationCredential.organization_id).filter(
            IntegrationCredential.provider == "sd_mailbox",
            IntegrationCredential.key == "protocol",
            IntegrationCredential.value.in_(["imap", "graph"]),
        ).all()
    return [f[0] for f in filas]


# ── IMAP ─────────────────────────────────────────────────────────────────────

def _leer_imap(cfg: dict, maximo: int) -> Iterator[Mensaje]:
    conexion = imaplib.IMAP4_SSL(cfg["host"], int(cfg.get("port") or 993), timeout=30)
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
    azure = get_provider_config(db, "ms_graph", org_id=org_id)
    if not (azure.get("tenant_id") and azure.get("client_id") and azure.get("client_secret")):
        raise RuntimeError("Faltan las credenciales de Microsoft 365 (tenant, client id y secret)")
    r = httpx.post(
        f"https://login.microsoftonline.com/{azure['tenant_id']}/oauth2/v2.0/token",
        data={"client_id": azure["client_id"], "client_secret": azure["client_secret"],
              "scope": "https://graph.microsoft.com/.default", "grant_type": "client_credentials"},
        timeout=20,
    )
    r.raise_for_status()
    return r.json()["access_token"]


def _leer_graph(db: Session, org_id: Optional[str], cfg: dict, maximo: int) -> Iterator[Mensaje]:
    buzon = cfg.get("mailbox")
    if not buzon:
        raise RuntimeError("Falta el buzón de Microsoft 365")
    cabeceras = {"Authorization": f"Bearer {_token_graph(db, org_id)}"}
    with httpx.Client(base_url=GRAPH, headers=cabeceras, timeout=30) as cliente:
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
            resultado[org_id or "global"] = {"error": str(exc)[:300]}
    return resultado


def probar_buzon(db: Session, org_id: Optional[str]) -> dict:
    """Se conecta y cuenta los no leidos, sin procesar ni marcar nada."""
    cfg = get_provider_config(db, "sd_mailbox", org_id=org_id)
    protocolo = (cfg.get("protocol") or "").strip().lower()
    try:
        if protocolo == "imap":
            conexion = imaplib.IMAP4_SSL(cfg["host"], int(cfg.get("port") or 993), timeout=20)
            try:
                conexion.login(cfg["user"], cfg["password"])
                conexion.select(cfg.get("folder") or "INBOX", readonly=True)
                _, datos = conexion.uid("search", None, "UNSEEN")
                return {"ok": True, "protocol": "imap", "unread": len((datos[0] or b"").split())}
            finally:
                conexion.logout()
        if protocolo == "graph":
            buzon = cfg.get("mailbox")
            if not buzon:
                return {"ok": False, "protocol": "graph", "error": "Falta el buzón de Microsoft 365"}
            r = httpx.get(f"{GRAPH}/users/{buzon}/mailFolders/inbox", timeout=20,
                          headers={"Authorization": f"Bearer {_token_graph(db, org_id)}"})
            r.raise_for_status()
            return {"ok": True, "protocol": "graph", "unread": r.json().get("unreadItemCount")}
        return {"ok": False, "protocol": protocolo or None, "error": "Buzón sin configurar"}
    except (imaplib.IMAP4.error, OSError, KeyError, httpx.HTTPError, RuntimeError) as exc:
        return {"ok": False, "protocol": protocolo, "error": str(exc)[:300]}
