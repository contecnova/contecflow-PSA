"""Tokens efimeros, cookies de autenticacion y el flujo de restablecimiento de contrasena.

Parte de `app.services.auth_service` (auditoria 2026-11, #24): se partio por responsabilidad
sin cambiar el codigo. El paquete reexporta todos los nombres.
"""
from datetime import datetime, timezone
import base64
import uuid
from typing import Optional
from fastapi import Request, Response
from jose import jwt as jose_jwt, JWTError
from sqlalchemy.orm import Session
from app.core.config import settings
from app.core.security import decode_token
from app.models.user import User
from app.services.key_management import get_jwt_signing_key, get_jwt_verification_keys
from app.core.errores import ErrorDeDominio

from app.services.auth_service.estado_efimero import (
    PASSWORD_RESET_TTL_SECONDS,
    is_current_password_reset_jti,
    store_password_reset_jti,
)
from app.services.auth_service._comun import logger


# ── Base64url helpers ─────────────────────────────────────────────────────────

def b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode().rstrip("=")


def b64url_decode(data: str) -> bytes:
    padding = "=" * ((4 - len(data) % 4) % 4)
    return base64.urlsafe_b64decode(data + padding)


# ── Ephemeral tokens ──────────────────────────────────────────────────────────

def create_ephemeral_token(
    token_type: str,
    subject: str,
    challenge: str,
    ttl_seconds: int = 300,
    token_jti: Optional[str] = None,
) -> str:
    expire = datetime.now(timezone.utc).timestamp() + ttl_seconds
    jti = token_jti or uuid.uuid4().hex
    payload = {
        "sub": subject,
        "exp": int(expire),
        "type": token_type,
        "challenge": challenge,
        "jti": jti,
    }
    kid, key = get_jwt_signing_key()
    return jose_jwt.encode(payload, key, algorithm="HS256", headers={"kid": kid})


def read_ephemeral_token(token: str, expected_type: str) -> dict:
    payload = None
    for key in get_jwt_verification_keys().values():
        try:
            payload = jose_jwt.decode(token, key, algorithms=["HS256"])
            break
        except JWTError:
            continue
    if payload is None:
        raise ErrorDeDominio(401, "Token de challenge inválido o expirado")
    if payload.get("type") != expected_type:
        raise ErrorDeDominio(401, "Token de challenge inválido")

    if expected_type == "password_reset":
        user_id = payload.get("sub")
        token_jti = payload.get("jti")
        if not user_id or not token_jti or not is_current_password_reset_jti(user_id, token_jti):
            raise ErrorDeDominio(401, "Token de restablecimiento inválido o reemplazado")
    return payload


# ── Auth cookies ──────────────────────────────────────────────────────────────

COOKIE_OPTS = {
    "httponly": True,
    "samesite": "lax",
    # Audit (Sprint 3-4): require HTTPS-only cookies in staging too, not just
    # production. Only local development serves over plain HTTP.
    "secure": settings.ENVIRONMENT in {"production", "staging"},
}


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
        path="/api/v1/auth/refresh",
        **{**COOKIE_OPTS, "samesite": "strict"},
    )
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


# ── Password reset ────────────────────────────────────────────────────────────

def issue_password_reset_token(user: User) -> str:
    challenge = uuid.uuid4().hex
    jti = uuid.uuid4().hex
    store_password_reset_jti(user.id, jti, PASSWORD_RESET_TTL_SECONDS)
    return create_ephemeral_token(
        token_type="password_reset",  # noqa: S106
        subject=user.id,
        challenge=challenge,
        ttl_seconds=PASSWORD_RESET_TTL_SECONDS,
        token_jti=jti,
    )


def send_password_reset_email(recipient: str, reset_link: str, db: Optional[Session] = None, org_id: Optional[str] = None) -> None:
    subject = "Contecflow PSA - Restablecer contraseña"
    body = (
        "Has solicitado restablecer tu contraseña de Contecflow PSA.\n\n"
        f"Enlace de restablecimiento (válido {PASSWORD_RESET_TTL_SECONDS // 60} minutos):\n"
        f"{reset_link}\n\n"
        "Si no solicitaste este cambio, ignora este correo."
    )

    from app.services.notification_service import ServidorSmtp, construir_mensaje, entregar
    servidor = (ServidorSmtp.de_organizacion(db, org_id) if db is not None
                else ServidorSmtp.del_entorno())
    remitente = servidor.remitente or servidor.user

    if servidor.host and servidor.user and remitente:
        # Lanza si no sale: el router lo registra y no anota la solicitud.
        entregar(servidor, construir_mensaje(
            remitente=remitente, para=recipient, asunto=subject, texto=body))
        return

    logger.info("Password reset requested for %s (email backend not configured)", recipient)


# ── Password reset ────────────────────────────────────────────────────────────

def complete_password_reset(db: Session, user: User, new_hash: str) -> None:
    """Update user password hash and commit."""
    user.hashed_password = new_hash
    db.commit()
