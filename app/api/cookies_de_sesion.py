"""Cookies de la sesion: escribirlas en la respuesta y leer el refresco de la peticion.

Auditoria 2026-11 (item 36): vivian en `app/services/auth_service/tokens_y_cookies.py`,
que por ellas importaba `Request` y `Response` de FastAPI. Poner y leer cookies
es HTTP, asi que es capa API. Los valores (`COOKIE_OPTS`, rutas de la cookie,
duraciones) siguen en el servicio y aqui solo se aplican. Mismo codigo, sin
cambios de comportamiento.
"""
from __future__ import annotations

from typing import Optional

from fastapi import Request, Response
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import decode_token
from app.services.auth_service.tokens_y_cookies import (
    COOKIE_OPTS,
    REFRESH_COOKIE_PATH,
    REFRESH_COOKIE_PATH_ANTIGUA,
)


def set_auth_cookies(response: Response, access_token: str, refresh_token: str, db: Optional[Session] = None, org_id: Optional[str] = None) -> None:
    if db is not None:
        from app.services.settings_service import get_runtime_int
        access_minutes = get_runtime_int(db, "ACCESS_TOKEN_EXPIRE_MINUTES", org_id) or settings.ACCESS_TOKEN_EXPIRE_MINUTES
        refresh_days   = get_runtime_int(db, "REFRESH_TOKEN_EXPIRE_DAYS",   org_id) or settings.REFRESH_TOKEN_EXPIRE_DAYS
    else:
        access_minutes = settings.ACCESS_TOKEN_EXPIRE_MINUTES
        refresh_days   = settings.REFRESH_TOKEN_EXPIRE_DAYS
    response.set_cookie(
        "access_token",
        access_token,
        max_age=access_minutes * 60,
        **COOKIE_OPTS,
    )
    # Audit (Sprint 3-4): refresh cookie is only ever sent to the dedicated
    # refresh endpoint via same-origin XHR, so SameSite=Strict is safe here and
    # blocks it from riding along on any cross-site navigation.
    response.set_cookie(
        "refresh_token",
        refresh_token,
        max_age=refresh_days * 86400,
        path=REFRESH_COOKIE_PATH,
        **{**COOKIE_OPTS, "samesite": "strict"},
    )
    # La de la ruta antigua, fuera: si no, el navegador manda las dos a /refresh.
    response.delete_cookie("refresh_token", path=REFRESH_COOKIE_PATH_ANTIGUA,
                           **{**COOKIE_OPTS, "samesite": "strict"})
    # Audit #C1: also mint a CSRF token cookie on every login/refresh. The
    # cookie is readable by JS so the SPA can echo it back via X-CSRF-Token
    # when CSRF_DOUBLE_SUBMIT=1 is enabled. No-op effect on clients that don't
    # opt in; pure preparation.
    try:
        from app.core.csrf import issue_csrf_cookie
        issue_csrf_cookie(response)
    except Exception:
        # Never block auth on CSRF token minting issues — log and continue.
        import logging as _logging
        _logging.getLogger("app.services.auth_service").warning("issue_csrf_cookie failed", exc_info=True)


def current_refresh_jti(request: Request) -> Optional[str]:
    raw_refresh = request.cookies.get("refresh_token")
    if not raw_refresh:
        return None
    token_data = decode_token(raw_refresh)
    if not token_data or token_data.get("type") != "refresh":
        return None
    return token_data.get("jti")
