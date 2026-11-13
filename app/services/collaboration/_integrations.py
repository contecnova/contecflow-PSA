"""OAuth integrations para Bridge (Jira, GitHub, GitLab, Google Calendar, M365).

Flujo:
  1. /collaboration/integrations/{kind}/oauth/start  → redirige al provider
  2. provider redirige a /collaboration/integrations/oauth/callback?state=...&code=...
  3. backend intercambia code por tokens, guarda encriptados en
     collaboration_integrations.access_token_enc / refresh_token_enc.

Variables de entorno por proveedor:
  Jira:    JIRA_CLIENT_ID JIRA_CLIENT_SECRET JIRA_REDIRECT_URI
  GitHub:  GITHUB_CLIENT_ID GITHUB_CLIENT_SECRET GITHUB_REDIRECT_URI
  GitLab:  GITLAB_CLIENT_ID GITLAB_CLIENT_SECRET GITLAB_REDIRECT_URI
  Google:  GOOGLE_CLIENT_ID GOOGLE_CLIENT_SECRET GOOGLE_REDIRECT_URI
  M365:    MS365_CLIENT_ID MS365_CLIENT_SECRET MS365_REDIRECT_URI MS365_TENANT_ID

Las llamadas reales (crear issue Jira, abrir PR GitHub, etc.) viven en
_integrations_clients.py y son invocadas por slash commands.
"""
from __future__ import annotations

import base64
import hashlib
import logging
import secrets
import urllib.parse
from dataclasses import dataclass
from typing import Optional

import httpx

from app.core.config import settings
from app.services.settings_service import outbound_http_timeout

logger = logging.getLogger(__name__)

_CALLBACK_PATH = "/api/v1/collaboration/integrations/oauth/callback"


def _default_redirect_uri() -> str:
    """OAuth callback URL derived from BACKEND_URL — never a hardcoded localhost,
    which would break the flow (or leak the auth code) in staging/production."""
    return f"{settings.BACKEND_URL.rstrip('/')}{_CALLBACK_PATH}"


@dataclass
class OAuthProvider:
    kind: str
    client_id_env: str
    client_secret_env: str
    redirect_env: str
    auth_url: str
    token_url: str
    scopes: list[str]
    extra_auth_params: dict | None = None
    extra_token_params: dict | None = None


PROVIDERS: dict[str, OAuthProvider] = {
    "jira": OAuthProvider(
        kind="jira",
        client_id_env="JIRA_CLIENT_ID", client_secret_env="JIRA_CLIENT_SECRET",  # noqa: S106
        redirect_env="JIRA_REDIRECT_URI",
        auth_url="https://auth.atlassian.com/authorize",
        token_url="https://auth.atlassian.com/oauth/token",  # noqa: S106
        scopes=["read:jira-work", "write:jira-work", "offline_access"],
        extra_auth_params={"audience": "api.atlassian.com", "prompt": "consent"},
    ),
    "github": OAuthProvider(
        kind="github",
        client_id_env="GITHUB_CLIENT_ID", client_secret_env="GITHUB_CLIENT_SECRET",  # noqa: S106
        redirect_env="GITHUB_REDIRECT_URI",
        auth_url="https://github.com/login/oauth/authorize",
        token_url="https://github.com/login/oauth/access_token",  # noqa: S106
        scopes=["repo", "read:user", "read:org"],
    ),
    "gitlab": OAuthProvider(
        kind="gitlab",
        client_id_env="GITLAB_CLIENT_ID", client_secret_env="GITLAB_CLIENT_SECRET",  # noqa: S106
        redirect_env="GITLAB_REDIRECT_URI",
        auth_url="https://gitlab.com/oauth/authorize",
        token_url="https://gitlab.com/oauth/token",  # noqa: S106
        scopes=["api", "read_user", "read_repository"],
    ),
    "google_calendar": OAuthProvider(
        kind="google_calendar",
        client_id_env="GOOGLE_CLIENT_ID", client_secret_env="GOOGLE_CLIENT_SECRET",  # noqa: S106
        redirect_env="GOOGLE_REDIRECT_URI",
        auth_url=f"{settings.GOOGLE_OAUTH_BASE}/o/oauth2/v2/auth",
        token_url=settings.GOOGLE_TOKEN_URL,
        scopes=[
            "https://www.googleapis.com/auth/calendar.readonly",
            "https://www.googleapis.com/auth/calendar.events",
        ],
        extra_auth_params={"access_type": "offline", "prompt": "consent"},
    ),
    "microsoft_365": OAuthProvider(
        kind="microsoft_365",
        client_id_env="MS365_CLIENT_ID", client_secret_env="MS365_CLIENT_SECRET",  # noqa: S106
        redirect_env="MS365_REDIRECT_URI",
        auth_url=settings.MICROSOFT_OAUTH_BASE + "/{tenant}/oauth2/v2.0/authorize",
        token_url=settings.MICROSOFT_OAUTH_BASE + "/{tenant}/oauth2/v2.0/token",  # noqa: S106
        scopes=["offline_access", "Calendars.ReadWrite", "Mail.Send", "User.Read"],
    ),
}


# Auditoria 2026-11 (#26): el `state` era aleatorio, guardado en un dict de
# memoria de proceso (no sobrevivia a varios workers) y no ligado a nadie. Ahora
# es el de `app.services.oauth_state` —firmado, de un solo uso, con el usuario y
# la organizacion que iniciaron el flujo— y ademas va ligado al navegador que lo
# inicio por la cookie `COOKIE_DE_VINCULO` (el callback llega sin sesion).
_PROPOSITO = "collab_integration"
COOKIE_DE_VINCULO = "collab_oauth_bind"
CALLBACK_PATH = _CALLBACK_PATH


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode().rstrip("=")


def _pkce_pair() -> tuple[str, str]:
    verifier = _b64url(secrets.token_bytes(32))
    challenge = _b64url(hashlib.sha256(verifier.encode()).digest())
    return verifier, challenge


def auth_url_for(kind: str, integration_id: str, *, user_id: Optional[str] = None,
                 org_id: Optional[str] = None, vinculo: Optional[str] = None) -> Optional[str]:
    p = PROVIDERS.get(kind)
    if not p:
        return None
    # Credenciales por proveedor: el nombre sale de PROVIDERS y el valor de Settings.
    client_id = getattr(settings, p.client_id_env, None)
    redirect = getattr(settings, p.redirect_env, None) or _default_redirect_uri()
    if not client_id:
        return None
    from app.services import oauth_state

    verifier, challenge = _pkce_pair()
    state = oauth_state.emitir(
        _PROPOSITO, user_id=user_id, org_id=org_id, kind=kind, integration_id=integration_id,
        verifier=verifier, vinculo=oauth_state.huella(vinculo) if vinculo else None,
    )
    auth_url = p.auth_url
    if kind == "microsoft_365":
        tenant = settings.MS365_TENANT_ID or "common"
        auth_url = auth_url.format(tenant=tenant)
    params = {
        "client_id": client_id,
        "redirect_uri": redirect,
        "response_type": "code",
        "scope": " ".join(p.scopes),
        "state": state,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
    }
    if p.extra_auth_params:
        params.update(p.extra_auth_params)
    return f"{auth_url}?{urllib.parse.urlencode(params)}"


def consumir_estado(state: str, vinculo: Optional[str]) -> tuple[Optional[dict], str]:
    """El estado pendiente, si la firma vale, no se uso y lo trae el mismo navegador."""
    import hmac as _hmac

    from app.core.errores import ErrorDeDominio
    from app.services import oauth_state

    try:
        pending = oauth_state.consumir(_PROPOSITO, state)
    except ErrorDeDominio:
        return None, "state desconocido o expirado"
    esperado = pending.get("vinculo")
    if not esperado or not vinculo or not _hmac.compare_digest(esperado, oauth_state.huella(vinculo)):
        return None, "el flujo OAuth no se inició en este navegador"
    return pending, ""


async def handle_callback(state: str, code: str, vinculo: Optional[str] = None,
                          ) -> tuple[Optional[str], Optional[dict], str, Optional[str]]:
    """Returns (integration_id, token_data, error, org_id)."""
    pending, error = consumir_estado(state, vinculo)
    if not pending:
        return None, None, error, None
    p = PROVIDERS[pending["kind"]]
    client_id = getattr(settings, p.client_id_env, None)
    client_secret = getattr(settings, p.client_secret_env, None)
    redirect = getattr(settings, p.redirect_env, None) or _default_redirect_uri()
    if not client_id or not client_secret:
        return None, None, "credenciales no configuradas", None

    token_url = p.token_url
    if pending["kind"] == "microsoft_365":
        tenant = settings.MS365_TENANT_ID or "common"
        token_url = token_url.format(tenant=tenant)
    body = {
        "grant_type": "authorization_code",
        "code": code,
        "client_id": client_id,
        "client_secret": client_secret,
        "redirect_uri": redirect,
        "code_verifier": pending["verifier"],
    }
    if p.extra_token_params:
        body.update(p.extra_token_params)
    try:
        async with httpx.AsyncClient(timeout=outbound_http_timeout(default=20)) as c:
            r = await c.post(token_url, data=body, headers={"Accept": "application/json"})
            if r.status_code >= 400:
                logger.warning("OAuth token exchange %s: HTTP %s", pending["kind"], r.status_code)
                return None, None, f"token exchange falló: HTTP {r.status_code}", None
            data = r.json()
    except Exception:
        logger.warning("handle_callback: excepcion ignorada", exc_info=True)
        return None, None, "token exchange falló", None
    return pending["integration_id"], data, "", pending.get("org_id")


# ── Encryption (Fernet con clave derivada de SECRET_KEY existente) ──────────
def _fernet():
    """Cifra con SECRET_KEY y descifra tambien con las anteriores (rotacion)."""
    from cryptography.fernet import Fernet, MultiFernet
    from app.core.encryption import claves_secretas
    return MultiFernet([
        Fernet(base64.urlsafe_b64encode(hashlib.sha256(c.encode() + b"|collab-integrations").digest()))
        for c in claves_secretas()
    ])


def encrypt(value: str | None) -> Optional[str]:
    if not value:
        return None
    return _fernet().encrypt(value.encode()).decode()


def decrypt(value: str | None) -> Optional[str]:
    if not value:
        return None
    try:
        return _fernet().decrypt(value.encode()).decode()
    except Exception:
        logger.debug("decrypt: excepcion ignorada", exc_info=True)
        return None


# ── Capabilities introspection ───────────────────────────────────────────────
def configured_providers() -> dict[str, bool]:
    out = {}
    for kind, p in PROVIDERS.items():
        out[kind] = bool(getattr(settings, p.client_id_env, None)) and bool(getattr(settings, p.client_secret_env, None))
    return out
