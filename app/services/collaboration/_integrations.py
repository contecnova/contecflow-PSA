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
import os
import secrets
import urllib.parse
from dataclasses import dataclass
from typing import Optional

import httpx

from app.core.config import settings

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
        auth_url="https://accounts.google.com/o/oauth2/v2/auth",
        token_url="https://oauth2.googleapis.com/token",  # noqa: S106
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
        auth_url="https://login.microsoftonline.com/{tenant}/oauth2/v2.0/authorize",
        token_url="https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token",  # noqa: S106
        scopes=["offline_access", "Calendars.ReadWrite", "Mail.Send", "User.Read"],
    ),
}


# In-memory pending state -> integration_id (used in callback). For prod with
# multiple workers move to Redis.
_PENDING: dict[str, dict] = {}


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode().rstrip("=")


def _pkce_pair() -> tuple[str, str]:
    verifier = _b64url(secrets.token_bytes(32))
    challenge = _b64url(hashlib.sha256(verifier.encode()).digest())
    return verifier, challenge


def auth_url_for(kind: str, integration_id: str) -> Optional[str]:
    p = PROVIDERS.get(kind)
    if not p:
        return None
    # env-driven: per-provider OAuth credentials are looked up dynamically by env var
    # name (see PROVIDERS table). Not in Settings because providers are pluggable.
    client_id = os.environ.get(p.client_id_env)
    redirect = os.environ.get(p.redirect_env) or _default_redirect_uri()
    if not client_id:
        return None
    state = secrets.token_urlsafe(24)
    verifier, challenge = _pkce_pair()
    _PENDING[state] = {"kind": kind, "integration_id": integration_id, "verifier": verifier}
    auth_url = p.auth_url
    if kind == "microsoft_365":
        tenant = os.environ.get("MS365_TENANT_ID", "common")
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


async def handle_callback(state: str, code: str) -> tuple[Optional[str], Optional[dict], str]:
    """Returns (integration_id, token_data, error)."""
    pending = _PENDING.pop(state, None)
    if not pending:
        return None, None, "state desconocido o expirado"
    p = PROVIDERS[pending["kind"]]
    client_id = os.environ.get(p.client_id_env)
    client_secret = os.environ.get(p.client_secret_env)
    redirect = os.environ.get(p.redirect_env) or _default_redirect_uri()
    if not client_id or not client_secret:
        return None, None, "credenciales no configuradas"

    token_url = p.token_url
    if pending["kind"] == "microsoft_365":
        tenant = os.environ.get("MS365_TENANT_ID", "common")
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
        async with httpx.AsyncClient(timeout=20) as c:
            r = await c.post(token_url, data=body, headers={"Accept": "application/json"})
            if r.status_code >= 400:
                return None, None, f"token exchange falló: {r.status_code} {r.text[:200]}"
            data = r.json()
    except Exception as exc:
        return None, None, str(exc)
    return pending["integration_id"], data, ""


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
        return None


# ── Capabilities introspection ───────────────────────────────────────────────
def configured_providers() -> dict[str, bool]:
    out = {}
    for kind, p in PROVIDERS.items():
        out[kind] = bool(os.environ.get(p.client_id_env)) and bool(os.environ.get(p.client_secret_env))
    return out
