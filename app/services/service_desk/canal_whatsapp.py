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

Solo mensajes de texto: los demas tipos se anotan como «[tipo]» para que el
agente sepa que llegaron.
"""
from __future__ import annotations

import hashlib
import hmac
import logging
from typing import Optional

import httpx
from sqlalchemy.orm import Session

from app.core.errores import ErrorDeDominio

logger = logging.getLogger(__name__)

PROVEEDOR = "whatsapp"
#: Version de la Graph API si la empresa no fija otra.
VERSION_POR_DEFECTO = "v20.0"
GRAPH = "https://graph.facebook.com"


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
    return f"[{tipo}]"


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
                r = conversaciones.mensaje_del_cliente(db, conv, _texto(m) or "[vacío]", telefono=f"+{de}",
                                                       external_message_id=m.get("id"))
                duplicados += int(r["duplicate"])
                procesados += int(not r["duplicate"])
    return {"processed": procesados, "duplicates": duplicados}


def enviar(db: Session, org_id: str, destino: str, texto: str) -> Optional[str]:
    """Manda un texto por WhatsApp. Devuelve el id del mensaje o None si falla (queda en el log)."""
    from app.services.integration_credentials_service import get_credential
    from app.services.settings_service import outbound_http_timeout
    numero = get_credential(db, PROVEEDOR, "phone_number_id", org_id)
    token = _secreto(db, "access_token", org_id)
    if not numero or not token:
        logger.warning("WhatsApp sin configurar en la empresa %s: el mensaje no sale", org_id)
        return None
    version = get_credential(db, PROVEEDOR, "api_version", org_id) or VERSION_POR_DEFECTO
    try:
        r = httpx.post(f"{GRAPH}/{version}/{numero}/messages", headers={"Authorization": f"Bearer {token}"},
                       json={"messaging_product": "whatsapp", "to": destino, "type": "text",
                             "text": {"body": texto[:4096]}},
                       timeout=outbound_http_timeout(db, default=10))
        r.raise_for_status()
        return ((r.json().get("messages") or [{}])[0]).get("id")
    except (httpx.HTTPError, ValueError):
        logger.warning("WhatsApp: no se pudo enviar a %s", destino, exc_info=True)
        return None
