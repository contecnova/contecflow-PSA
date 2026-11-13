"""Tokens efimeros, cookies de autenticacion y el flujo de restablecimiento de contrasena.

Parte de `app.services.auth_service` (auditoria 2026-11, #24): se partio por responsabilidad
sin cambiar el codigo. El paquete reexporta todos los nombres.
"""
from datetime import datetime, timezone
import base64
import uuid
from typing import Optional
from jose import jwt as jose_jwt, JWTError
from sqlalchemy.orm import Session
from app.core.config import settings
from app.models.user import User
from app.services.key_management import get_jwt_signing_key, get_jwt_verification_keys
from app.core.errores import ErrorDeDominio

from app.services.auth_service.estado_efimero import (
    PASSWORD_RESET_TTL_SECONDS,
    is_current_password_reset_jti,
    store_password_reset_jti,
)
from app.services.auth_service._comun import logger
from app.core.constantes import NOMBRE_COMPLETO_DEL_PRODUCTO


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

#: Ruta de la cookie de refresco. Auditoria 2026-11 (#22): era
#: `/api/v1/auth/refresh`, asi que el navegador no la mandaba a `/auth/logout`,
#: `/auth/switch-organization`, `/auth/change-password` ni al panel de sesiones:
#: cerrar sesion no revocaba el refresco (seguia sirviendo 30 dias) y «revocar
#: las demas» revocaba tambien la actual. Ahora cubre todo `/api/v1/auth`.
REFRESH_COOKIE_PATH = "/api/v1/auth"
#: La ruta antigua, para borrar la cookie que quede en los navegadores.
REFRESH_COOKIE_PATH_ANTIGUA = "/api/v1/auth/refresh"

COOKIE_OPTS = {
    "httponly": True,
    "samesite": "lax",
    # Audit (Sprint 3-4): require HTTPS-only cookies in staging too, not just
    # production. Only local development serves over plain HTTP.
    "secure": settings.ENVIRONMENT in {"production", "staging"},
}


# `set_auth_cookies` y `current_refresh_jti` estan en `app/api/cookies_de_sesion.py`
# (auditoria 2026-11, item 36): escribir y leer cookies es capa HTTP.


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
    subject = f"{NOMBRE_COMPLETO_DEL_PRODUCTO} - Restablecer contraseña"
    body = (
        f"Has solicitado restablecer tu contraseña de {NOMBRE_COMPLETO_DEL_PRODUCTO}.\n\n"
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

def revocar_sesiones_del_usuario(db: Session, user_id: str, motivo: str,
                                 salvo_jti: Optional[str] = None) -> int:
    """Revoca todos los refrescos activos del usuario (menos `salvo_jti`). No confirma.

    Auditoria 2026-11 (#22): cambiar o restablecer la contrasena no cerraba
    ninguna sesion: quien la tuviera robada seguia dentro hasta 30 dias.
    """
    from app.models.sessions import UserSession

    ahora = datetime.now(timezone.utc)
    q = db.query(UserSession).filter(UserSession.user_id == user_id, UserSession.revoked_at.is_(None))
    if salvo_jti:
        q = q.filter(UserSession.refresh_token_jti != salvo_jti)
    filas = q.all()
    for fila in filas:
        fila.revoked_at = ahora
        fila.revoke_reason = motivo[:255]
    return len(filas)


def complete_password_reset(db: Session, user: User, new_hash: str) -> None:
    """Update user password hash, revoke every session, and commit."""
    user.hashed_password = new_hash
    revocar_sesiones_del_usuario(db, user.id, "password_reset")
    db.commit()
