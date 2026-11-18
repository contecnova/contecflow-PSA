"""WhatsApp Business (Meta Cloud API) como canal del service desk
(mejoras de mercado 16-11-2026).

Configuracion por empresa en *Ajustes → Credenciales → WhatsApp Business*
(`whatsapp`): `phone_number_id`, `access_token`, `app_secret`, `verify_token` y
`api_version`. Los secretos van cifrados como el resto de credenciales.

- **Alta del webhook** (`GET /sd/channels/whatsapp/webhook`): Meta manda
  `hub.mode=subscribe`, `hub.verify_token` y `hub.challenge`; se contesta el
  `challenge` solo si el token coincide con el de alguna empresa.
- **Mensajes** (`POST /sd/channels/whatsapp/webhook`): la empresa sale del
  `phone_number_id` que recibe; la firma `X-Hub-Signature-256` (HMAC-SHA256 del
  cuerpo tal cual llega con el `app_secret` de ESA empresa) es obligatoria.
  Sin firma valida, 403. Un mensaje repetido (Meta reintenta) se ignora.
- **Respuestas**: lo que el agente escribe en la conversacion sale por la Graph
  API (`/{phone_number_id}/messages`) con el `access_token`, con la espera de
  las llamadas salientes (`OUTBOUND_HTTP_TIMEOUT_SECONDS`).

Adjuntos (17-11-2026):

- **Entrada**: imagen, documento, audio, video y sticker. Se pide la URL del
  medio por su id (`GET /{media_id}`) con el `access_token` de la empresa y se
  descarga (solo HTTPS a los hosts de Meta, con `cliente_httpx`, la espera
  saliente y el tope `SD_CHANNEL_MAX_ATTACHMENT_MB`). Pasa por
  `adjuntos_de_canal` (tipo, bytes magicos, antivirus) y queda como documento
  del ticket. Si no se puede bajar, el mensaje lo anota.
- **Salida**: un documento del ticket se sube a los medios de WhatsApp
  (`POST /{phone_number_id}/media`) y se envia por su id.
- **Ventana de 24 h** (regla de Meta): pasado un dia del ultimo mensaje del
  cliente solo se pueden enviar plantillas aprobadas. Con plantilla
  configurada (`template_name`, `template_language`; dos variables: numero
  del ticket y texto) el texto sale dentro de ella; sin plantilla no sale y se
  avisa al agente. Los adjuntos solo salen dentro de la ventana.

Toda llamada a Meta va por `cliente_httpx` (redirecciones e IP final
validadas).
"""
from __future__ import annotations

import hashlib
import hmac
import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Optional
from urllib.parse import urlparse

import httpx
from sqlalchemy.orm import Session

from app.core.errores import ErrorDeDominio
from app.services.formato_regional import IDIOMA_DE_RESPALDO

logger = logging.getLogger(__name__)

PROVEEDOR = "whatsapp"
#: Version de la Graph API si la empresa no fija otra.
VERSION_POR_DEFECTO = "v20.0"
GRAPH = "https://graph.facebook.com"
#: Ventana de Meta para mensajes libres tras el ultimo mensaje del cliente.
VENTANA = timedelta(hours=24)
#: Tipos de mensaje con medio adjunto.
TIPOS_CON_MEDIO = ("image", "document", "audio", "video", "sticker")
#: Hosts desde los que Meta sirve los medios (la URL que devuelve `GET /{media_id}`).
_HOSTS_DE_MEDIOS = (".fbsbx.com", ".facebook.com", ".whatsapp.net", ".fbcdn.net")


def _cliente(timeout: float):
    """Cliente HTTP saliente con proteccion SSRF (redirecciones e IP final validadas)."""
    from app.core.outbound_url import cliente_httpx
    return cliente_httpx(timeout=timeout, follow_redirects=False)


def _espera(db: Session) -> float:
    from app.services.settings_service import outbound_http_timeout
    return outbound_http_timeout(db, default=10)


def _version(db: Session, org_id: str) -> str:
    from app.services.integration_credentials_service import get_credential
    return get_credential(db, PROVEEDOR, "api_version", org_id) or VERSION_POR_DEFECTO


def _filas(db: Session, clave: str):
    from app.db.session import sin_filtro_de_tenant
    from app.models.settings import IntegrationCredential
    with sin_filtro_de_tenant(db):
        return db.query(IntegrationCredential).filter(IntegrationCredential.provider == PROVEEDOR,
                                                      IntegrationCredential.key == clave,
                                                      IntegrationCredential.organization_id.isnot(None)).all()


def _secreto(db: Session, clave: str, org_id: str) -> Optional[str]:
    from app.services.integration_credentials_service import secreto_propio_de_la_organizacion
    return secreto_propio_de_la_organizacion(db, PROVEEDOR, clave, f"WHATSAPP_{clave.upper()}", org_id)


def organizacion_del_numero(db: Session, phone_number_id: Optional[str]) -> Optional[str]:
    """La empresa duena del numero; si lo declaran dos, ninguna (no se adivina)."""
    if not phone_number_id:
        return None
    orgs = {f.organization_id for f in _filas(db, "phone_number_id") if (f.value or "").strip() == str(phone_number_id)}
    return orgs.pop() if len(orgs) == 1 else None


def comprobar_alta(db: Session, verify_token: Optional[str]) -> bool:
    """El token del alta del webhook coincide con el de alguna empresa."""
    if not verify_token:
        return False
    from app.core.encryption import decrypt_value
    for f in _filas(db, "verify_token"):
        valor = decrypt_value(f.value_encrypted) if f.value_encrypted else f.value
        if valor and hmac.compare_digest(str(valor), str(verify_token)):
            return True
    return False


def firma_valida(app_secret: Optional[str], cuerpo: bytes, cabecera: Optional[str]) -> bool:
    if not app_secret or not cabecera or not cabecera.startswith("sha256="):
        return False
    esperada = "sha256=" + hmac.new(app_secret.encode(), cuerpo, hashlib.sha256).hexdigest()
    return hmac.compare_digest(esperada, cabecera)


def _texto(mensaje: dict) -> str:
    tipo = mensaje.get("type")
    if tipo == "text":
        return (mensaje.get("text") or {}).get("body") or ""
    if tipo == "button":
        return (mensaje.get("button") or {}).get("text") or ""
    if tipo == "interactive":
        i = mensaje.get("interactive") or {}
        return ((i.get("button_reply") or i.get("list_reply") or {}).get("title")) or ""
    if tipo in TIPOS_CON_MEDIO:
        return ((mensaje.get(tipo) or {}).get("caption") or "").strip() or f"[{tipo}]"
    return f"[{tipo}]"


def _medio(db: Session, org_id: str, mensaje: dict):
    """(Fichero, None) con el medio del mensaje, o (None, nota) si no se pudo bajar."""
    from app.core.errores import ErrorDeDominio
    from app.services.service_desk import adjuntos_de_canal
    tipo = mensaje.get("type")
    datos = mensaje.get(tipo) or {}
    media_id = datos.get("id")
    if not media_id:
        return None, None
    token = _secreto(db, "access_token", org_id)
    if not token:
        return None, f"[{tipo}: sin credencial para descargarlo]"
    cabeceras = {"Authorization": f"Bearer {token}"}
    tope = adjuntos_de_canal.tope_en_bytes(db, org_id)
    try:
        with _cliente(_espera(db)) as c:
            r = c.get(f"{GRAPH}/{_version(db, org_id)}/{media_id}", headers=cabeceras)
            r.raise_for_status()
            info = r.json()
            if int(info.get("file_size") or 0) > tope:
                return None, f"[{tipo}: supera el tamaño máximo]"
            url = info.get("url") or ""
            destino = urlparse(url)
            if destino.scheme != "https" or not (destino.hostname or "").endswith(_HOSTS_DE_MEDIOS):
                logger.warning("WhatsApp: URL de medio rechazada (%s)", destino.hostname)
                return None, f"[{tipo}: origen no permitido]"
            contenido, cabecera_tipo = adjuntos_de_canal.descargar_acotado(
                c, url, headers=cabeceras, tope=tope, timeout=_espera(db))
    except ErrorDeDominio:
        return None, f"[{tipo}: supera el tamaño máximo]"
    except (httpx.HTTPError, ValueError, PermissionError):
        logger.warning("WhatsApp: no se pudo descargar el medio %s", media_id, exc_info=True)
        return None, f"[{tipo}: no se pudo descargar]"
    mime = datos.get("mime_type") or info.get("mime_type") or cabecera_tipo or "application/octet-stream"
    nombre = adjuntos_de_canal.nombre_de_fichero(datos.get("filename"), mime, f"whatsapp-{tipo}")
    return adjuntos_de_canal.Fichero(nombre=nombre, tipo=mime, contenido=contenido), None


def procesar(db: Session, cuerpo: bytes, firma: Optional[str], payload: dict) -> dict:
    """Mensajes de un webhook ya parseado. Verifica la firma con el secreto de
    la empresa del numero de cada cambio; 403 si no cuadra."""
    from app.services.service_desk import conversaciones
    procesados = duplicados = 0
    for entrada in payload.get("entry") or []:
        for cambio in entrada.get("changes") or []:
            valor = cambio.get("value") or {}
            numero = (valor.get("metadata") or {}).get("phone_number_id")
            org = organizacion_del_numero(db, numero)
            if org is None:
                raise ErrorDeDominio(403, "Número de WhatsApp no vinculado a ninguna empresa")
            if not firma_valida(_secreto(db, "app_secret", org), cuerpo, firma):
                raise ErrorDeDominio(403, "Firma de WhatsApp no válida")
            # La peticion no tiene usuario: corre en la empresa del numero.
            db.info["organization_id"], db.info["is_superadmin"] = org, False
            nombres = {c.get("wa_id"): ((c.get("profile") or {}).get("name")) for c in valor.get("contacts") or []}
            for m in valor.get("messages") or []:
                de = m.get("from")
                if not de:
                    continue
                conv = conversaciones.abrir_o_seguir(db, org, "whatsapp", de, visitor_name=nombres.get(de) or de)
                if _ya_visto(db, conv, m.get("id")):
                    duplicados += 1
                    continue
                adjunto, nota = _medio(db, org, m) if m.get("type") in TIPOS_CON_MEDIO else (None, None)
                r = conversaciones.mensaje_del_cliente(db, conv, _texto(m) or "[vacío]", telefono=f"+{de}",
                                                       external_message_id=m.get("id"), adjunto=adjunto,
                                                       nota_de_adjunto=nota)
                duplicados += int(r["duplicate"])
                procesados += int(not r["duplicate"])
    return {"processed": procesados, "duplicates": duplicados}


def _ya_visto(db: Session, conv, mensaje_id: Optional[str]) -> bool:
    """Meta reintenta: un mensaje ya guardado no se vuelve a descargar."""
    if not mensaje_id:
        return False
    from app.models.service_desk import ChannelMessage
    return db.query(ChannelMessage.id).filter(ChannelMessage.conversation_id == conv.id,
                                              ChannelMessage.external_message_id == mensaje_id).first() is not None


# ── Ventana de 24 h y plantilla ──────────────────────────────────────────────

def _aware(dt: Optional[datetime]) -> Optional[datetime]:
    if dt is None:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def plantilla(db: Session, org_id: str) -> Optional[tuple[str, str]]:
    """(nombre, idioma) de la plantilla para escribir fuera de la ventana, o None."""
    from app.services.integration_credentials_service import get_credential
    nombre = (get_credential(db, PROVEEDOR, "template_name", org_id) or "").strip()
    if not nombre:
        return None
    return nombre, (get_credential(db, PROVEEDOR, "template_language", org_id) or IDIOMA_DE_RESPALDO).strip()


def ventana_abierta(conv, ahora: Optional[datetime] = None) -> bool:
    ultimo = _aware(conv.last_inbound_at)
    return ultimo is not None and (ahora or datetime.now(timezone.utc)) - ultimo < VENTANA


def estado_de_la_ventana(db: Session, conv) -> dict:
    ultimo = _aware(conv.last_inbound_at)
    return {"open": ventana_abierta(conv), "expires_at": (ultimo + VENTANA).isoformat() if ultimo else None,
            "template": plantilla(db, conv.organization_id) is not None}


def _parametro(texto: str) -> str:
    """Las variables de una plantilla no admiten saltos de linea, tabuladores ni 4+ espacios."""
    return re.sub(r"\s{2,}", " ", re.sub(r"[\r\n\t]+", " / ", texto or "")).strip()[:1000] or "-"


def _enviar(db: Session, org_id: str, cuerpo: dict) -> Optional[str]:
    from app.services.integration_credentials_service import get_credential
    numero = get_credential(db, PROVEEDOR, "phone_number_id", org_id)
    token = _secreto(db, "access_token", org_id)
    if not numero or not token:
        logger.warning("WhatsApp sin configurar en la empresa %s: el mensaje no sale", org_id)
        return None
    try:
        with _cliente(_espera(db)) as c:
            r = c.post(f"{GRAPH}/{_version(db, org_id)}/{numero}/messages",
                       headers={"Authorization": f"Bearer {token}"},
                       json={"messaging_product": "whatsapp", **cuerpo})
            r.raise_for_status()
            return ((r.json().get("messages") or [{}])[0]).get("id")
    except (httpx.HTTPError, ValueError, PermissionError):
        logger.warning("WhatsApp: no se pudo enviar a %s", cuerpo.get("to"), exc_info=True)
        return None


def enviar_en_conversacion(db: Session, conv, texto: str, numero_de_ticket: Optional[str] = None
                           ) -> tuple[Optional[str], str]:
    """Texto al cliente respetando la ventana. Devuelve (id externo, estado de entrega)."""
    if ventana_abierta(conv):
        ext = enviar(db, conv.organization_id, conv.external_id, texto)
        return ext, "sent" if ext else "failed"
    p = plantilla(db, conv.organization_id)
    if p is None:
        return None, "outside_window"
    ext = _enviar(db, conv.organization_id, {"to": conv.external_id, "type": "template", "template": {
        "name": p[0], "language": {"code": p[1]},
        "components": [{"type": "body", "parameters": [
            {"type": "text", "text": _parametro(numero_de_ticket or "-")},
            {"type": "text", "text": _parametro(texto)}]}]}})
    return ext, "template" if ext else "failed"


def _tipo_de_medio(mime: str) -> str:
    base = (mime or "").split("/")[0]
    return base if base in ("image", "audio", "video") else "document"


def enviar_adjunto(db: Session, conv, fichero, caption: str = "") -> tuple[Optional[str], str]:
    """Sube el fichero a los medios de WhatsApp y lo envia. Solo dentro de la ventana."""
    from app.services.integration_credentials_service import get_credential
    if not ventana_abierta(conv):
        return None, "outside_window"
    org = conv.organization_id
    numero = get_credential(db, PROVEEDOR, "phone_number_id", org)
    token = _secreto(db, "access_token", org)
    if not numero or not token:
        return None, "failed"
    tipo = _tipo_de_medio(fichero.tipo)
    try:
        with _cliente(_espera(db)) as c:
            r = c.post(f"{GRAPH}/{_version(db, org)}/{numero}/media", headers={"Authorization": f"Bearer {token}"},
                       data={"messaging_product": "whatsapp", "type": fichero.tipo},
                       files={"file": (fichero.nombre, fichero.contenido, fichero.tipo)})
            r.raise_for_status()
            media_id = r.json().get("id")
    except (httpx.HTTPError, ValueError, PermissionError):
        logger.warning("WhatsApp: no se pudo subir el adjunto %s", fichero.nombre, exc_info=True)
        return None, "failed"
    if not media_id:
        return None, "failed"
    medio: dict = {"id": media_id}
    if caption and tipo != "audio":
        medio["caption"] = caption[:1024]
    if tipo == "document":
        medio["filename"] = fichero.nombre
    ext = _enviar(db, org, {"to": conv.external_id, "type": tipo, tipo: medio})
    return ext, "sent" if ext else "failed"


def enviar(db: Session, org_id: str, destino: str, texto: str) -> Optional[str]:
    """Manda un texto por WhatsApp. Devuelve el id del mensaje o None si falla (queda en el log)."""
    return _enviar(db, org_id, {"to": destino, "type": "text", "text": {"body": texto[:4096]}})
