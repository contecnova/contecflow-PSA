"""SMS Service — Twilio-based SMS notifications and inbound handling.

Requires optional Twilio dependency. Install with:
    pip install twilio>=8.0.0

Configuration via AppSetting or environment variables:
    TWILIO_ACCOUNT_SID
    TWILIO_AUTH_TOKEN
    TWILIO_FROM_NUMBER  (E.164 format, e.g. +34600000000)
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import logging
from typing import Optional
from app.core.constantes import NOMBRE_DEL_PRODUCTO

logger = logging.getLogger(__name__)

try:
    from twilio.rest import Client as TwilioClient  # type: ignore
    _TWILIO_AVAILABLE = True
except ImportError:
    _TWILIO_AVAILABLE = False
    logger.info("Twilio not installed — SMS features disabled. Run: pip install twilio>=8.0.0")


def _get_twilio_config() -> tuple[Optional[str], Optional[str], Optional[str]]:
    """Return (account_sid, auth_token, from_number) from settings or env."""
    try:
        from app.core.config import settings
        sid = getattr(settings, "TWILIO_ACCOUNT_SID", None)
        token = getattr(settings, "TWILIO_AUTH_TOKEN", None)
        from_num = getattr(settings, "TWILIO_FROM_NUMBER", None)
        return sid, token, from_num
    except Exception:
        logger.debug("_get_twilio_config: excepcion ignorada", exc_info=True)
        return None, None, None


def send_sms(to: str, body: str) -> bool:
    """Send an SMS message via Twilio.

    Args:
        to:   Recipient phone number in E.164 format (e.g. +34612345678).
        body: Message text (≤160 characters for single SMS segment).

    Returns:
        True if sent successfully, False otherwise.
    """
    if not _TWILIO_AVAILABLE:
        logger.warning("SMS send skipped — Twilio not installed")
        return False

    sid, token, from_num = _get_twilio_config()
    if not all([sid, token, from_num]):
        logger.warning("SMS send skipped — Twilio credentials not configured (TWILIO_ACCOUNT_SID/AUTH_TOKEN/FROM_NUMBER)")
        return False

    try:
        from app.core.metrics import track_external_call

        client = TwilioClient(sid, token)
        with track_external_call("twilio"):
            message = client.messages.create(body=body[:1600], from_=from_num, to=to)
        logger.info("SMS sent to %s — SID: %s", telefono_enmascarado(to), message.sid)
        return True
    except Exception as exc:
        logger.error("SMS send failed to %s: %s", telefono_enmascarado(to), type(exc).__name__)
        return False


def telefono_enmascarado(numero) -> str:
    """El telefono para los logs: solo los 3 ultimos digitos.

    Auditoria 2026-11-22 (servicios m-z, 4.4): el numero completo (dato
    personal) quedaba en los logs de SMS y de WhatsApp.
    """
    digitos = "".join(c for c in str(numero or "") if c.isdigit())
    return ("***" + digitos[-3:]) if digitos else "-"


#: Ajuste por organizacion con sus numeros de Twilio (E.164, separados por comas).
CLAVE_NUMEROS_DE_TWILIO = "TWILIO_PHONE_NUMBERS"


def _normalizar_numero(numero: Optional[str]) -> str:
    """Un numero de telefono sin adornos: «+34 600-00-00 02» -> «+34600000002».

    Lo que no parece un telefono (`client:…`, `sip:…`) se compara tal cual.
    """
    texto = str(numero or "").strip()
    if not texto:
        return ""
    if all(c.isdigit() or c in "+ -().\u00a0" for c in texto):
        digitos = "".join(c for c in texto if c.isdigit())
        return ("+" + digitos) if texto.startswith("+") and digitos else digitos
    return texto.lower()


def organizacion_del_numero_de_twilio(db, numero: Optional[str]) -> Optional[str]:
    """La organizacion duena del numero de Twilio `numero` (el `To` del webhook).

    Segunda auditoria 2026-11 (#19): la declaran el ajuste por organizacion
    `TWILIO_PHONE_NUMBERS` (CSV) y la credencial `twilio.from_number`. Un numero
    que declaran DOS organizaciones no es de ninguna: se registra el error y se
    devuelve `None`, igual que un numero desconocido — nunca se elige una.
    """
    from app.db.session import sin_filtro_de_tenant
    from app.models.settings import AppSetting, IntegrationCredential

    buscado = _normalizar_numero(numero)
    if not buscado:
        return None
    with sin_filtro_de_tenant(db):
        ajustes = db.query(AppSetting.organization_id, AppSetting.value).filter(
            AppSetting.key == CLAVE_NUMEROS_DE_TWILIO, AppSetting.organization_id.isnot(None)).all()
        credenciales = db.query(IntegrationCredential.organization_id, IntegrationCredential.value).filter(
            IntegrationCredential.provider == "twilio", IntegrationCredential.key == "from_number",
            IntegrationCredential.organization_id.isnot(None)).all()
    orgs = {org for org, valor in ajustes
            if buscado in {_normalizar_numero(n) for n in (valor or "").split(",")}}
    orgs |= {org for org, valor in credenciales if _normalizar_numero(valor) == buscado}
    if len(orgs) > 1:
        logger.error("Twilio: el numero %s esta declarado en varias organizaciones; se rechaza", buscado)
        return None
    return orgs.pop() if orgs else None


def twilio_auth_token_de_la_organizacion(db, org_id: Optional[str]) -> Optional[str]:
    """El token propio de `org_id` (credencial cifrada `twilio.auth_token` o
    ajuste `TWILIO_AUTH_TOKEN` de esa organizacion) y, si no tiene, el global."""
    _, global_token, _ = _get_twilio_config()
    if db is None or not org_id:
        return global_token
    from app.services.integration_credentials_service import secreto_propio_de_la_organizacion

    propio = secreto_propio_de_la_organizacion(db, "twilio", "auth_token", "TWILIO_AUTH_TOKEN", org_id)
    return propio or global_token


def twilio_auth_token_para(db, to_phone: Optional[str]) -> Optional[str]:
    """El auth token con el que se verifica un SMS que llego a `to_phone`.

    Segunda auditoria 2026-11 (#9): la organizacion sale del numero receptor
    (`organizacion_del_numero_de_twilio`); se usa su token propio y, si no
    tiene, el global `TWILIO_AUTH_TOKEN`.
    """
    if db is None:
        return twilio_auth_token_de_la_organizacion(None, None)
    return twilio_auth_token_de_la_organizacion(db, organizacion_del_numero_de_twilio(db, to_phone))


def urls_de_firma_de_twilio(request) -> list[str]:
    """Las URLs contra las que se comprueba la firma de un webhook de Twilio.

    Segunda auditoria 2026-11 (#23): Twilio firma la URL que tiene configurada
    (`https://<dominio>/...`). Detras de nginx la API veia `http://...` y toda
    peticion daba 403. Primero la URL publica (`BACKEND_URL` + ruta y consulta),
    que es lo que Twilio recomienda detras de proxies; despues la que ve la API
    (`request.url`, ya con el esquema del proxy de confianza), para despliegues
    que la exponen con otro nombre. Las dos son la MISMA ruta y consulta: aceptar
    cualquiera no deja reutilizar una firma en otro endpoint.
    """
    from app.core.network import url_publica

    return list(dict.fromkeys([url_publica(request), str(request.url)]))


def firma_de_twilio_valida(url, params: dict, signature: Optional[str], token: Optional[str]) -> bool:
    """HMAC-SHA1 de la URL y los parametros ordenados, en base64 (algoritmo de Twilio).

    `url` es una URL o una lista de candidatas (`urls_de_firma_de_twilio`).
    """
    if not token or not signature:
        return False
    params = params or {}
    sufijo = "".join(f"{k}{params[k]}" for k in sorted(params))
    candidatas = [url] if isinstance(url, str) else list(url)
    valida = False
    for candidata in candidatas:
        datos = candidata + sufijo
        esperada = base64.b64encode(hmac.new(token.encode(), datos.encode(), hashlib.sha1).digest()).decode()
        valida |= hmac.compare_digest(esperada, signature)
    return valida


def validate_twilio_signature(url, params: dict, signature: Optional[str], db=None) -> bool:
    """Si la peticion viene de Twilio de verdad.

    Auditoria 2026-11: fallaba ABIERTA —sin la libreria de Twilio, sin token o
    sin cabecera de firma se aceptaba—, asi que cualquiera podia abrir tickets
    por SMS. Ahora sin token o sin firma se rechaza. El algoritmo es el
    documentado por Twilio (HMAC-SHA1 de la URL y los parametros ordenados, en
    base64) y no necesita la libreria.

    Con `db`, el token es el de la organizacion del numero receptor (`To`).
    """
    return firma_de_twilio_valida(url, params, signature, twilio_auth_token_para(db, (params or {}).get("To")))


def build_sms_ticket_notification(ticket_number: str, title: str, status: str) -> str:
    """Format a short SMS notification for a ticket status update."""
    return (
        f"[{NOMBRE_DEL_PRODUCTO}] Ticket {ticket_number}: {title[:60]}\n"
        f"Estado: {status}\n"
        "Responde a este mensaje para actualizar el ticket."
    )
