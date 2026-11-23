"""Test-connection probes per integration provider.

Used by ``POST /api/v1/settings/integrations/{provider}/test``. Each probe is
a tiny, non-mutating call to the provider (auth check, balance query, bucket
HEAD, etc.) so the admin can verify their newly entered credentials work
*before* a real flow exercises them in production.

Each probe receives the effective credentials dict from
``get_provider_config`` and returns either:
  - {"ok": True,  "detail": "Authenticated as ..." }
  - {"ok": False, "detail": "401 Unauthorized: bad token"}

Probes must never raise — wrap the underlying call in try/except.

23-11-2026 (auditoría 2026-11-22, «conectores sin probar contra el servicio
real»): cada resultado lleva `verificado`, lo que la prueba demuestra DE VERDAD
contra el servicio (no lo que se supone):

- `nada`: no se ha llamado al servicio (falta configuración o el fallo es previo).
- `configuracion`: solo se ha comprobado que los campos están; el servicio
  exige un flujo que la prueba no puede hacer (OAuth con consentimiento).
- `alcance`: el servicio responde en esa dirección, sin validar credenciales.
- `credencial`: el servicio ha aceptado la credencial.
- `credencial_y_uso`: además, la operación que usa el producto (leer el tenant,
  el número, la bandeja, el bucket...) funciona con esos permisos.
- `pasivo`: secretos de entrada (firmas de webhooks): se verifican cuando llega
  el primer evento; no hay nada saliente que probar.

La tabla por proveedor está en docs/integraciones/pruebas_de_conexion.md.
"""
from __future__ import annotations

from contextvars import ContextVar

import logging
from typing import Callable, Optional

from sqlalchemy.orm import Session

from app.services.integration_credentials_service import (
    PROVIDER_REGISTRY,
    get_provider_config,
)
from app.services.settings_service import outbound_http_timeout
from app.core.config import settings
# 22-11-2026 (02 A28): todas las sondas salen por el guardia SSRF central
# (`cliente_httpx` valida la URL, cada redirección y la IP conectada). Las URLs
# que escribe el admin (webhook de Slack, base de Adobe Sign, host SMTP) ya no
# sirven para sondear la red interna con el estado HTTP como oráculo.
from app.core.outbound_url import cliente_httpx, validar_host_saliente

logger = logging.getLogger("contecflow.integrations.test")


def _err(exc: Exception, hint: str = "") -> dict:
    msg = getattr(exc, "detail", None) or str(exc)
    return {"ok": False, "detail": (f"{hint}: {msg}" if hint else msg)[:400]}


# ── Provider-specific probes ─────────────────────────────────────────────────


def _test_smtp(cfg: dict, db: Session) -> dict:
    # Auditoria 2026-11 (hallazgo 20): la conexion la abre el emisor comun, con
    # la misma negociacion de TLS que el envio real; asi la prueba dice la verdad.
    from app.services.notification_service import ServidorSmtp, comprobar_smtp
    host, port = cfg.get("host"), cfg.get("port") or 587
    if not host:
        return {"ok": False, "detail": "SMTP host no configurado"}
    try:
        validar_host_saliente(host, field="SMTP host")
        comprobar_smtp(ServidorSmtp(
            host=host, port=int(port), user=cfg.get("user") or None,
            password=cfg.get("password") or None,
            timeout=outbound_http_timeout(db, default=10.0),
        ))
        return {"ok": True, "detail": f"Conexión SMTP OK ({host}:{port})"}
    except Exception as exc:
        logger.warning("_test_smtp: excepcion ignorada", exc_info=True)
        return _err(exc, "SMTP")


def _test_aws_s3(cfg: dict, db: Session) -> dict:
    try:
        import boto3
        bucket = cfg.get("bucket")
        if not bucket:
            return {"ok": False, "detail": "Bucket no configurado"}
        # M101 (auditoría 22-11-2026): sin claves propias la prueba NO usa la
        # cadena de credenciales del servidor (rol de la instancia, variables de
        # entorno): diría «OK» con las de la plataforma, no con las de la empresa.
        if not (cfg.get("access_key") and cfg.get("secret_key")):
            return {"ok": False, "detail": "Faltan access_key y secret_key", "verificado": "nada"}
        client = boto3.client(
            "s3",
            region_name=cfg.get("region") or settings.AWS_REGION,  # 19-11-2026: sin región fija
            aws_access_key_id=cfg.get("access_key"),
            aws_secret_access_key=cfg.get("secret_key"),
        )
        client.head_bucket(Bucket=bucket)
        return {"ok": True, "detail": f"head_bucket OK ({bucket})"}
    except Exception as exc:
        logger.warning("_test_aws_s3: excepcion ignorada", exc_info=True)
        return _err(exc, "AWS S3")


def _test_ms_graph(cfg: dict, db: Session) -> dict:
    """23-11-2026 (03 A-MP3): la prueba usa la credencial de ESA empresa (la que
    usará Graph de verdad; nunca los `AZURE_*` salvo credencial de plataforma
    explícita), pide el token y lee `/organization` de su tenant."""
    from app.services.m365_service import probar_conexion
    r = probar_conexion(db, _org_de_la_prueba.get())
    if r["ok"]:
        return {"ok": True, "detail": f"Token y tenant verificados ({r.get('tenant') or '-'}; {r['origen']})",
                "verificado": r["verificado"]}
    if r["verificado"] == "sin_credencial":
        return {"ok": False, "detail": "tenant_id / client_id / client_secret incompletos", "verificado": "nada"}
    motivo = r.get("error") or f"HTTP {r.get('status')}"
    return {"ok": False, "detail": f"MS Graph: {motivo}", "verificado": r["verificado"]}


def _test_slack(cfg: dict, db: Session) -> dict:
    webhook = cfg.get("webhook_url")
    if not webhook:
        return {"ok": False, "detail": "webhook_url no configurado"}
    # We don't actually post a message — just verify the URL is reachable.
    # Slack returns 400 for an empty body, which proves the host accepts.
    try:
        with cliente_httpx(timeout=outbound_http_timeout(db, default=10.0)) as c:
            r = c.post(webhook, json={})
        if r.status_code in (200, 400):
            return {"ok": True, "detail": f"Slack webhook responde HTTP {r.status_code}"}
        return {"ok": False, "detail": f"Slack respondió HTTP {r.status_code}"}
    except Exception as exc:
        logger.warning("_test_slack: excepcion ignorada", exc_info=True)
        return _err(exc, "Slack")


def _test_twilio(cfg: dict, db: Session) -> dict:
    sid, token = cfg.get("account_sid"), cfg.get("auth_token")
    if not (sid and token):
        return {"ok": False, "detail": "account_sid o auth_token vacíos"}
    try:
        from twilio.rest import Client as _TwilioClient
        client = _TwilioClient(sid, token)
        acct = client.api.v2010.accounts(sid).fetch()
        return {"ok": True, "detail": f"Twilio cuenta '{acct.friendly_name}' status={acct.status}"}
    except Exception as exc:
        logger.debug("_test_twilio: excepcion ignorada", exc_info=True)
        return _err(exc, "Twilio")


def _test_stripe(cfg: dict, db: Session) -> dict:
    key = cfg.get("secret_key")
    if not key:
        return {"ok": False, "detail": "secret_key vacía"}
    try:
        with cliente_httpx(timeout=outbound_http_timeout(db, default=10.0)) as c:
            r = c.get("https://api.stripe.com/v1/balance", auth=(key, ""))
        if r.status_code == 200:
            data = r.json()
            return {"ok": True, "detail": f"Stripe balance OK — {len(data.get('available', []))} currencies"}
        return {"ok": False, "detail": f"Stripe HTTP {r.status_code}"}
    except Exception as exc:
        logger.warning("_test_stripe: excepcion ignorada", exc_info=True)
        return _err(exc, "Stripe")


def _test_docusign(cfg: dict, db: Session) -> dict:
    """23-11-2026: antes devolvía `ok: True` sin llamar a DocuSign. El flujo es
    OAuth con consentimiento de un usuario, que una prueba no puede hacer: se
    comprueba la configuración y que el servidor de autenticación responde, y se
    dice que la credencial queda sin verificar (`verificado: configuracion`)."""
    faltan = [k for k in ("integration_key", "secret_key", "account_id") if not cfg.get(k)]
    if faltan:
        return {"ok": False, "detail": f"Faltan: {', '.join(faltan)}", "verificado": "nada"}
    from app.services.esign_providers import _ds_auth
    try:
        with cliente_httpx(timeout=outbound_http_timeout(db, default=10.0)) as c:
            r = c.get(f"{_ds_auth(None).rstrip('/')}/.well-known/openid-configuration")
        if r.status_code != 200:
            return {"ok": False, "detail": f"DocuSign HTTP {r.status_code}", "verificado": "nada"}
    except Exception as exc:
        logger.warning("_test_docusign: excepcion ignorada", exc_info=True)
        return {**_err(exc, "DocuSign"), "verificado": "nada"}
    return {"ok": True, "verificado": "configuracion",
            "detail": "Configuración completa y servidor de DocuSign alcanzable. La clave se verifica al "
                      "conectar la cuenta (OAuth): la prueba no puede hacerlo sin un usuario."}


def _test_adobe_sign(cfg: dict, db: Session) -> dict:
    base = cfg.get("base_url")
    if not base:
        return {"ok": False, "detail": "base_url vacía"}
    # Probe the discovery endpoint (no auth needed) to confirm host is right.

    try:
        with cliente_httpx(timeout=outbound_http_timeout(db, default=10.0)) as c:
            r = c.get(f"{base.rstrip('/')}/baseUris")
        if r.status_code in (200, 401):
            return {"ok": True, "verificado": "alcance",
                    "detail": f"Adobe Sign endpoint alcanzable (HTTP {r.status_code}). La credencial se "
                              "verifica al conectar la cuenta (OAuth)."}
        return {"ok": False, "detail": f"Adobe Sign HTTP {r.status_code}"}
    except Exception as exc:
        logger.warning("_test_adobe_sign: excepcion ignorada", exc_info=True)
        return _err(exc, "Adobe Sign")


def _test_ai_providers(cfg: dict, db: Session) -> dict:
    """Try whichever key is configured. Anthropic first, then OpenAI."""

    ant_key = cfg.get("anthropic_api_key")
    oai_key = cfg.get("openai_api_key")
    if ant_key:
        try:
            with cliente_httpx(timeout=outbound_http_timeout(db, default=10.0)) as c:
                r = c.post(
                    f"{settings.ANTHROPIC_API_URL.rstrip('/')}/messages/count_tokens",
                    headers={
                        "x-api-key": ant_key,
                        "anthropic-version": "2023-06-01",
                        "Content-Type": "application/json",
                    },
                    json={"model": settings.CONTECFLOW_AI_MODEL, "messages": [{"role": "user", "content": "ping"}]},
                )
            if r.status_code == 200:
                return {"ok": True, "detail": "Anthropic API key válida"}
            return {"ok": False, "detail": f"Anthropic HTTP {r.status_code}"}
        except Exception as exc:
            logger.warning("_test_ai_providers: excepcion ignorada", exc_info=True)
            return _err(exc, "Anthropic")
    if oai_key:
        try:
            with cliente_httpx(timeout=outbound_http_timeout(db, default=10.0)) as c:
                r = c.get(f"{settings.OPENAI_API_URL.rstrip('/')}/models", headers={"Authorization": f"Bearer {oai_key}"})
            if r.status_code == 200:
                return {"ok": True, "detail": "OpenAI API key válida"}
            return {"ok": False, "detail": f"OpenAI HTTP {r.status_code}"}
        except Exception as exc:
            logger.warning("_test_ai_providers: excepcion ignorada", exc_info=True)
            return _err(exc, "OpenAI")
    return {"ok": False, "detail": "Ni Anthropic ni OpenAI key configurada"}


def _test_open_exchange_rates(cfg: dict, db: Session) -> dict:
    app_id = cfg.get("app_id")
    if not app_id:
        return {"ok": False, "detail": "app_id vacío"}
    try:
        with cliente_httpx(timeout=outbound_http_timeout(db, default=10.0)) as c:
            # M5: el App ID en la cabecera, no en la URL.
            r = c.get("https://openexchangerates.org/api/latest.json", params={"symbols": "EUR"},
                      headers={"Authorization": f"Token {app_id}"})
        if r.status_code == 200:
            j = r.json()
            return {"ok": True, "detail": f"OER OK — base={j.get('base')} rates={list(j.get('rates', {}).keys())}"}
        return {"ok": False, "detail": f"OER HTTP {r.status_code}"}
    except Exception as exc:
        logger.warning("_test_open_exchange_rates: excepcion ignorada", exc_info=True)
        return _err(exc, "OpenExchangeRates")


def _test_webhooks(cfg: dict, db: Session) -> dict:
    # Inbound-only signing secrets — nothing to probe outbound.
    configured = [k for k, v in cfg.items() if v]
    if not configured:
        return {"ok": False, "detail": "Sin secretos configurados"}
    return {"ok": True, "detail": f"Secretos cargados: {', '.join(configured)} (verificación pasiva)"}


_org_de_la_prueba: ContextVar[Optional[str]] = ContextVar("org_de_la_prueba", default=None)


# ── 23-11-2026: proveedores que no tenían prueba ─────────────────────────────

def _test_sd_mailbox(cfg: dict, db: Session) -> dict:
    """Buzón del service desk: se conecta (IMAP con la IP validada y fijada, o
    Graph con la credencial de la empresa) y cuenta los no leídos, sin procesar."""
    from app.services.service_desk.buzones import probar_buzon
    r = probar_buzon(db, _org_de_la_prueba.get())
    # Incidencia 10 de usuarios (23-11-2026): con `code` y `params`, la interfaz
    # pinta el resultado en el idioma del operador (antes, texto fijo en castellano).
    if r.get("ok"):
        return {"ok": True, "verificado": "credencial_y_uso",
                "detail": f"{r.get('protocol')}: {r.get('unread')} sin leer",
                "code": "buzon_prueba_ok", "params": {"protocolo": r.get("protocol"), "n": r.get("unread") or 0}}
    return {"ok": False, "verificado": "nada", "detail": str(r.get("error") or "Buzón sin configurar"),
            "code": r.get("code") or "buzon_sin_configurar", "params": r.get("params") or {}}


def _test_whatsapp(cfg: dict, db: Session) -> dict:
    """WhatsApp Business: lee el número (`GET /{version}/{phone_number_id}`) con el
    token de la empresa: credencial y número a la vez. No envía nada."""
    import re

    from app.services.service_desk.canal_whatsapp import GRAPH, VERSION_POR_DEFECTO
    numero, token = cfg.get("phone_number_id"), cfg.get("access_token")
    if not (numero and token):
        return {"ok": False, "detail": "phone_number_id o access_token vacíos", "verificado": "nada"}
    version = str(cfg.get("api_version") or VERSION_POR_DEFECTO)
    if not re.fullmatch(r"v\d{1,3}\.\d{1,2}", version) or not re.fullmatch(r"\d{1,30}", str(numero)):
        return {"ok": False, "detail": "phone_number_id o api_version no válidos", "verificado": "nada"}
    try:
        with cliente_httpx(timeout=outbound_http_timeout(db, default=10.0)) as c:
            r = c.get(f"{GRAPH}/{version}/{numero}", params={"fields": "display_phone_number"},
                      headers={"Authorization": f"Bearer {token}"})
        if r.status_code == 200:
            return {"ok": True, "verificado": "credencial_y_uso",
                    "detail": f"Número {r.json().get('display_phone_number') or numero} accesible"}
        return {"ok": False, "verificado": "alcance", "detail": f"WhatsApp HTTP {r.status_code}"}
    except Exception as exc:
        logger.warning("_test_whatsapp: excepcion ignorada", exc_info=True)
        return {**_err(exc, "WhatsApp"), "verificado": "nada"}


def _test_monitoring(cfg: dict, db: Session) -> dict:
    """Alertas de monitorización: solo entrada (token que trae el emisor)."""
    if not cfg.get("ingest_token"):
        return {"ok": False, "detail": "ingest_token vacío", "verificado": "nada"}
    return {"ok": True, "verificado": "pasivo",
            "detail": "Token cargado; se verifica con el primer evento recibido"}


def _probar_alm(clave: str):
    """Fuentes de uso de licencias: la prueba propia de cada fuente (la llamada
    más barata con permisos reales; `alm_uso.conexiones.probar`)."""
    def probe(cfg: dict, db: Session) -> dict:
        from types import SimpleNamespace

        from app.services.alm_uso import conexiones
        r = conexiones.probar(db, SimpleNamespace(organization_id=_org_de_la_prueba.get()), clave)
        if r.get("ok"):
            return {"ok": True, "verificado": "credencial_y_uso",
                    "detail": str(r.get("detalle") or r.get("detail") or "OK")}
        return {"ok": False, "verificado": "nada",
                "detail": f"{r.get('codigo') or 'ERROR'}: {r.get('mensaje') or ''}".strip()}
    return probe


#: Lo que demuestra una prueba que sale bien, cuando la sonda no lo dice.
_VERIFICA: dict[str, str] = {
    "smtp": "credencial", "aws_s3": "credencial_y_uso", "ms_graph": "credencial_y_uso",
    "slack": "alcance", "twilio": "credencial", "stripe": "credencial", "deepl": "credencial_y_uso",
    "azure_translator": "credencial_y_uso", "ai_providers": "credencial",
    "open_exchange_rates": "credencial_y_uso", "webhooks": "pasivo",
    "contecmind": "credencial", "contecintelligence": "credencial",
}


def _probar_conector(clave: str):
    """contecmind y contecintelligence: credencial de aplicación y salud (revisión 2026-11).

    El alta de la EMPRESA necesita un usuario; la prueba completa está en
    `POST /conectores/{producto}/probar`, que es la que usa la pantalla.
    """
    def probe(cfg: dict, db: Session) -> dict:
        from app.services.conectores import anfitrion
        r = anfitrion.probar(db, anfitrion.PRODUCTOS[clave], _org_de_la_prueba.get())
        return {"ok": r["ok"], "detail": r["detail"]}
    return probe


def _probar_traductor(nombre: str):
    """DeepL y Azure Translator (traduccion en tiempo real, 16-11-2026): traduce
    una palabra con las credenciales de ESA empresa (nunca las globales)."""
    def probe(cfg: dict, db: Session) -> dict:
        from app.services.traduccion.servicio import probar
        r = probar(db, _org_de_la_prueba.get(), nombre, "en", "hola")
        return {"ok": r["ok"], "detail": r.get("text") or r.get("reason") or ""}
    return probe


_PROBES: dict[str, Callable[[dict, Session], dict]] = {
    "deepl":                _probar_traductor("deepl"),
    "azure_translator":     _probar_traductor("azure"),
    "contecmind":           _probar_conector("contecmind"),
    "contecintelligence":   _probar_conector("contecintelligence"),
    "smtp":                 _test_smtp,
    "aws_s3":               _test_aws_s3,
    "ms_graph":             _test_ms_graph,
    "slack":                _test_slack,
    "twilio":               _test_twilio,
    "stripe":               _test_stripe,
    "docusign":             _test_docusign,
    "adobe_sign":           _test_adobe_sign,
    "ai_providers":         _test_ai_providers,
    "open_exchange_rates":  _test_open_exchange_rates,
    "webhooks":             _test_webhooks,
    # 23-11-2026: los que no tenían prueba.
    "sd_mailbox":           _test_sd_mailbox,
    "whatsapp":             _test_whatsapp,
    "monitoring":           _test_monitoring,
    "alm_m365":             _probar_alm("m365"),
    "alm_google":           _probar_alm("google"),
    "alm_okta":             _probar_alm("okta"),
    "alm_jamf":             _probar_alm("jamf"),
}


def test_provider_connection(db: Session, provider: str, org_id: Optional[str] = None) -> dict:
    """Run the configured probe for *provider*. Caller enforces RBAC.

    Returns a stable shape: ``{"ok": bool, "detail": str, "provider": str}``.
    The probe is wrapped in a final try/except so the API endpoint never 500s.
    """
    if provider not in PROVIDER_REGISTRY:
        return {"ok": False, "detail": f"unknown provider: {provider}", "provider": provider,
                "code": "integracion_desconocida", "params": {"proveedor": provider}}
    probe = _PROBES.get(provider)
    if probe is None:
        # Incidencia 10 (23-11-2026): con código; el aviso salía en inglés.
        return {"ok": False, "detail": f"no test probe defined for {provider}", "provider": provider,
                "code": "integracion_sin_prueba", "params": {"proveedor": provider}}
    marca = _org_de_la_prueba.set(org_id)
    try:
        cfg = get_provider_config(db, provider, org_id=org_id)
        result = probe(cfg, db)
    except Exception as exc:
        logger.exception("integration test failed for %s", provider)
        result = _err(exc, provider)
    finally:
        # Auditoría 22-11-2026 (baja): el ContextVar se restablece (antes quedaba
        # puesto en el hilo y la siguiente prueba podía heredar la empresa).
        _org_de_la_prueba.reset(marca)
    result.setdefault("provider", provider)
    result.setdefault("verificado", _VERIFICA.get(provider, "nada") if result.get("ok") else "nada")
    return result


__all__ = ["test_provider_connection"]
