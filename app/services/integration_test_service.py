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
"""
from __future__ import annotations

import logging
from typing import Callable, Optional

from sqlalchemy.orm import Session

from app.services.integration_credentials_service import (
    PROVIDER_REGISTRY,
    get_provider_config,
)
from app.services.settings_service import outbound_http_timeout

logger = logging.getLogger("contecflow.integrations.test")


def _err(exc: Exception, hint: str = "") -> dict:
    msg = str(exc)
    return {"ok": False, "detail": (f"{hint}: {msg}" if hint else msg)[:400]}


# ── Provider-specific probes ─────────────────────────────────────────────────


def _test_smtp(cfg: dict, db: Session) -> dict:
    import smtplib
    host, port = cfg.get("host"), cfg.get("port") or 587
    user, password = cfg.get("user"), cfg.get("password")
    if not host:
        return {"ok": False, "detail": "SMTP host no configurado"}
    try:
        with smtplib.SMTP(host, int(port), timeout=outbound_http_timeout(db, default=10.0)) as server:
            server.ehlo()
            try:
                server.starttls()
                server.ehlo()
            except Exception:
                pass
            if user and password:
                server.login(user, password)
            server.noop()
        return {"ok": True, "detail": f"Conexión SMTP OK ({host}:{port})"}
    except Exception as exc:
        return _err(exc, "SMTP")


def _test_aws_s3(cfg: dict, db: Session) -> dict:
    try:
        import boto3
        bucket = cfg.get("bucket")
        if not bucket:
            return {"ok": False, "detail": "Bucket no configurado"}
        client = boto3.client(
            "s3",
            region_name=cfg.get("region") or "eu-west-1",
            aws_access_key_id=cfg.get("access_key"),
            aws_secret_access_key=cfg.get("secret_key"),
        )
        client.head_bucket(Bucket=bucket)
        return {"ok": True, "detail": f"head_bucket OK ({bucket})"}
    except Exception as exc:
        return _err(exc, "AWS S3")


def _test_ms_graph(cfg: dict, db: Session) -> dict:
    import httpx
    tenant = cfg.get("tenant_id"); client_id = cfg.get("client_id"); secret = cfg.get("client_secret")
    if not (tenant and client_id and secret):
        return {"ok": False, "detail": "tenant_id / client_id / client_secret incompletos"}
    try:
        with httpx.Client(timeout=outbound_http_timeout(db, default=15.0)) as c:
            r = c.post(
                f"https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token",
                data={
                    "grant_type": "client_credentials",
                    "client_id": client_id,
                    "client_secret": secret,
                    "scope": "https://graph.microsoft.com/.default",
                },
            )
        if r.status_code == 200 and "access_token" in r.json():
            return {"ok": True, "detail": "Token Azure AD obtenido correctamente"}
        return {"ok": False, "detail": f"Azure AD respondió HTTP {r.status_code}: {r.text[:200]}"}
    except Exception as exc:
        return _err(exc, "MS Graph")


def _test_slack(cfg: dict, db: Session) -> dict:
    import httpx
    webhook = cfg.get("webhook_url")
    if not webhook:
        return {"ok": False, "detail": "webhook_url no configurado"}
    # We don't actually post a message — just verify the URL is reachable.
    # Slack returns 400 for an empty body, which proves the host accepts.
    try:
        with httpx.Client(timeout=outbound_http_timeout(db, default=10.0)) as c:
            r = c.post(webhook, json={})
        if r.status_code in (200, 400):
            return {"ok": True, "detail": f"Slack webhook responde HTTP {r.status_code}"}
        return {"ok": False, "detail": f"Slack respondió HTTP {r.status_code}"}
    except Exception as exc:
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
        return _err(exc, "Twilio")


def _test_stripe(cfg: dict, db: Session) -> dict:
    import httpx
    key = cfg.get("secret_key")
    if not key:
        return {"ok": False, "detail": "secret_key vacía"}
    try:
        with httpx.Client(timeout=outbound_http_timeout(db, default=10.0)) as c:
            r = c.get("https://api.stripe.com/v1/balance", auth=(key, ""))
        if r.status_code == 200:
            data = r.json()
            return {"ok": True, "detail": f"Stripe balance OK — {len(data.get('available', []))} currencies"}
        return {"ok": False, "detail": f"Stripe HTTP {r.status_code}: {r.text[:200]}"}
    except Exception as exc:
        return _err(exc, "Stripe")


def _test_docusign(cfg: dict, db: Session) -> dict:
    acct = cfg.get("account_id")
    if not acct:
        return {"ok": False, "detail": "account_id vacío (requiere flujo OAuth completo para test real)"}
    return {"ok": True, "detail": f"account_id configurado ({acct}). Test real requiere OAuth handshake — verifica integration_key/secret_key con flujo real."}


def _test_adobe_sign(cfg: dict, db: Session) -> dict:
    base = cfg.get("base_url")
    if not base:
        return {"ok": False, "detail": "base_url vacía"}
    # Probe the discovery endpoint (no auth needed) to confirm host is right.
    import httpx
    try:
        with httpx.Client(timeout=outbound_http_timeout(db, default=10.0)) as c:
            r = c.get(f"{base.rstrip('/')}/baseUris")
        if r.status_code in (200, 401):
            return {"ok": True, "detail": f"Adobe Sign endpoint alcanzable (HTTP {r.status_code}). Test real requiere OAuth."}
        return {"ok": False, "detail": f"Adobe Sign HTTP {r.status_code}"}
    except Exception as exc:
        return _err(exc, "Adobe Sign")


def _test_ai_providers(cfg: dict, db: Session) -> dict:
    """Try whichever key is configured. Anthropic first, then OpenAI."""
    import httpx
    ant_key = cfg.get("anthropic_api_key")
    oai_key = cfg.get("openai_api_key")
    if ant_key:
        try:
            with httpx.Client(timeout=outbound_http_timeout(db, default=10.0)) as c:
                r = c.post(
                    "https://api.anthropic.com/v1/messages/count_tokens",
                    headers={
                        "x-api-key": ant_key,
                        "anthropic-version": "2023-06-01",
                        "Content-Type": "application/json",
                    },
                    json={"model": "claude-haiku-4-5", "messages": [{"role": "user", "content": "ping"}]},
                )
            if r.status_code == 200:
                return {"ok": True, "detail": "Anthropic API key válida"}
            return {"ok": False, "detail": f"Anthropic HTTP {r.status_code}: {r.text[:200]}"}
        except Exception as exc:
            return _err(exc, "Anthropic")
    if oai_key:
        try:
            with httpx.Client(timeout=outbound_http_timeout(db, default=10.0)) as c:
                r = c.get("https://api.openai.com/v1/models", headers={"Authorization": f"Bearer {oai_key}"})
            if r.status_code == 200:
                return {"ok": True, "detail": "OpenAI API key válida"}
            return {"ok": False, "detail": f"OpenAI HTTP {r.status_code}: {r.text[:200]}"}
        except Exception as exc:
            return _err(exc, "OpenAI")
    return {"ok": False, "detail": "Ni Anthropic ni OpenAI key configurada"}


def _test_open_exchange_rates(cfg: dict, db: Session) -> dict:
    import httpx
    app_id = cfg.get("app_id")
    if not app_id:
        return {"ok": False, "detail": "app_id vacío"}
    try:
        with httpx.Client(timeout=outbound_http_timeout(db, default=10.0)) as c:
            r = c.get("https://openexchangerates.org/api/latest.json", params={"app_id": app_id, "symbols": "EUR"})
        if r.status_code == 200:
            j = r.json()
            return {"ok": True, "detail": f"OER OK — base={j.get('base')} rates={list(j.get('rates', {}).keys())}"}
        return {"ok": False, "detail": f"OER HTTP {r.status_code}: {r.text[:200]}"}
    except Exception as exc:
        return _err(exc, "OpenExchangeRates")


def _test_webhooks(cfg: dict, db: Session) -> dict:
    # Inbound-only signing secrets — nothing to probe outbound.
    configured = [k for k, v in cfg.items() if v]
    if not configured:
        return {"ok": False, "detail": "Sin secretos configurados"}
    return {"ok": True, "detail": f"Secretos cargados: {', '.join(configured)} (verificación pasiva)"}


_PROBES: dict[str, Callable[[dict, Session], dict]] = {
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
}


def test_provider_connection(db: Session, provider: str, org_id: Optional[str] = None) -> dict:
    """Run the configured probe for *provider*. Caller enforces RBAC.

    Returns a stable shape: ``{"ok": bool, "detail": str, "provider": str}``.
    The probe is wrapped in a final try/except so the API endpoint never 500s.
    """
    if provider not in PROVIDER_REGISTRY:
        return {"ok": False, "detail": f"unknown provider: {provider}", "provider": provider}
    probe = _PROBES.get(provider)
    if probe is None:
        return {"ok": False, "detail": f"no test probe defined for {provider}", "provider": provider}
    try:
        cfg = get_provider_config(db, provider, org_id=org_id)
        result = probe(cfg, db)
    except Exception as exc:
        logger.exception("integration test failed for %s", provider)
        result = _err(exc, provider)
    result.setdefault("provider", provider)
    return result


__all__ = ["test_provider_connection"]
