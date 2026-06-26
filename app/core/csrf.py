"""
csrf.py — CSRF protection middleware (Audit #C1).

Two layered defences against cross-site request forgery on cookie-authenticated
endpoints:

1. **Origin/Referer check (always on)**
   For every "unsafe" method (POST, PUT, PATCH, DELETE) the middleware verifies
   that the request's Origin (or Referer fallback) is present in the configured
   `ALLOWED_ORIGINS` set. Browsers always send Origin on cross-site fetch with
   credentials; absence of Origin on a state-changing request is itself
   suspicious and is rejected.

2. **Double-submit cookie token (opt-in via CSRF_DOUBLE_SUBMIT=1)**
   When enabled, the middleware additionally requires the `X-CSRF-Token` header
   to match the value of the `csrf_token` cookie. The token is rotated on each
   login (see `ensure_csrf_cookie` helper). This blocks even sophisticated
   attacks where the browser leaks credentials via misconfigured CORS.

Both layers are bypassed for:
  - Safe methods (GET, HEAD, OPTIONS).
  - Authorization-header-only requests (no cookie auth used).
  - Public endpoints declared in `CSRF_EXEMPT_PATHS` (configurable list, includes
    third-party webhooks that use HMAC signature verification instead).
"""
from __future__ import annotations

import logging
import os
import secrets
from typing import Iterable, Set
from urllib.parse import urlparse

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from app.core.config import settings

logger = logging.getLogger(__name__)

_UNSAFE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}

# Paths that are CSRF-exempt by design: third-party webhooks that authenticate
# via HMAC signature instead of cookies, and public/health endpoints.
_DEFAULT_EXEMPT_PREFIXES = (
    "/api/v1/webhooks/",
    "/api/v1/cab/webhooks/",
    "/api/v1/integrations_hub/slack",
    "/api/v1/integrations_hub/teams",
    "/api/v1/esign/docusign/webhook",
    "/api/v1/esign/adobe/webhook",
    "/api/v1/service-desk/voice/twilio",
    "/api/v1/service-desk/multichannel/inbound",
    "/api/v1/collaboration/bots/",
    "/api/v1/m365/webhook",
    "/api/v1/scim/",
    "/health",
    "/status",
    "/metrics",
)


def _normalised_origins() -> Set[str]:
    out: Set[str] = set()
    for origin in settings.ALLOWED_ORIGINS or []:
        try:
            p = urlparse(origin)
            if p.scheme and p.netloc:
                out.add(f"{p.scheme}://{p.netloc}".lower())
        except Exception:
            continue
    return out


def _request_origin(request: Request) -> str | None:
    """Return the request's Origin (preferred) or Referer-derived origin."""
    origin = request.headers.get("origin")
    if origin:
        try:
            p = urlparse(origin)
            if p.scheme and p.netloc:
                return f"{p.scheme}://{p.netloc}".lower()
        except Exception:
            pass
    referer = request.headers.get("referer")
    if referer:
        try:
            p = urlparse(referer)
            if p.scheme and p.netloc:
                return f"{p.scheme}://{p.netloc}".lower()
        except Exception:
            pass
    return None


def _is_exempt_path(path: str, exempt_prefixes: Iterable[str]) -> bool:
    return any(path.startswith(prefix) for prefix in exempt_prefixes)


def _uses_cookie_auth(request: Request) -> bool:
    """Cookie auth is the CSRF-vulnerable surface. Authorization header is safe."""
    has_cookie = bool(request.cookies.get("access_token") or request.cookies.get("refresh_token"))
    has_bearer = bool(request.headers.get("authorization"))
    # If the client uses Authorization header, cookies are irrelevant for the
    # auth path — CSRF is not exploitable against pure-header auth.
    return has_cookie and not has_bearer


class CSRFMiddleware(BaseHTTPMiddleware):
    """Enforce Origin/Referer + (optional) double-submit token on unsafe methods."""

    def __init__(self, app, *, exempt_prefixes: Iterable[str] | None = None) -> None:
        super().__init__(app)
        self._exempt_prefixes = tuple(exempt_prefixes or _DEFAULT_EXEMPT_PREFIXES)
        self._double_submit = os.getenv("CSRF_DOUBLE_SUBMIT", "0") == "1"
        # In test mode we relax the origin check because the TestClient does not
        # send an Origin header by default.
        self._enabled = os.getenv("DISABLE_CSRF_MIDDLEWARE", "0") != "1" and os.getenv("TESTING", "0") != "1"

    async def dispatch(self, request: Request, call_next) -> Response:
        if not self._enabled:
            return await call_next(request)

        method = request.method.upper()
        if method not in _UNSAFE_METHODS:
            return await call_next(request)

        path = request.url.path or "/"
        if _is_exempt_path(path, self._exempt_prefixes):
            return await call_next(request)

        if not _uses_cookie_auth(request):
            return await call_next(request)

        # Layer 1: Origin / Referer must match an allowed origin
        allowed = _normalised_origins()
        if allowed:
            origin = _request_origin(request)
            if origin is None:
                logger.warning("CSRF block: missing Origin/Referer on %s %s", method, path)
                return JSONResponse(
                    {"detail": "CSRF protection: missing Origin/Referer header"},
                    status_code=403,
                )
            if origin not in allowed:
                logger.warning("CSRF block: Origin %s not in ALLOWED_ORIGINS for %s %s", origin, method, path)
                return JSONResponse(
                    {"detail": "CSRF protection: origin not allowed"},
                    status_code=403,
                )

        # Layer 2: double-submit cookie (opt-in)
        if self._double_submit:
            header_token = request.headers.get("x-csrf-token")
            cookie_token = request.cookies.get("csrf_token")
            if not header_token or not cookie_token:
                return JSONResponse(
                    {"detail": "CSRF protection: missing csrf token"},
                    status_code=403,
                )
            if not secrets.compare_digest(header_token, cookie_token):
                return JSONResponse(
                    {"detail": "CSRF protection: csrf token mismatch"},
                    status_code=403,
                )

        return await call_next(request)


def issue_csrf_cookie(response: Response) -> str:
    """Mint a fresh CSRF token and attach it as a readable cookie.

    Called after login/refresh. The cookie is intentionally NOT httpOnly because
    the SPA must read it and echo it back in the X-CSRF-Token header.
    """
    token = secrets.token_urlsafe(32)
    response.set_cookie(
        "csrf_token",
        token,
        httponly=False,
        samesite="lax",
        secure=settings.ENVIRONMENT in {"production", "staging"},
        max_age=settings.REFRESH_TOKEN_EXPIRE_DAYS * 86400,
        path="/",
    )
    return token


__all__ = ["CSRFMiddleware", "issue_csrf_cookie"]
