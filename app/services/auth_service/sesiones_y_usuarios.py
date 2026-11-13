"""Busqueda de usuarios, sesiones activas y su revocacion, e IP y eventos de seguridad.

Parte de `app.services.auth_service` (auditoria 2026-11, #24): se partio por responsabilidad
sin cambiar el codigo. El paquete reexporta todos los nombres.
"""
from datetime import datetime, timezone
from typing import Optional
from sqlalchemy.orm import Session
from app.models.sessions import UserSession
from app.models.user import User
from app.services.security_observability import SecurityEventService
from app.core.errores import ErrorDeDominio

from app.services.auth_service._comun import logger


def soc_svc(db, user) -> "SecurityEventService | None":
    """Return a SecurityEventService if the user has an org; else None."""
    try:
        org_id = str(user.organization_id) if user and user.organization_id else None
        return SecurityEventService(db=db, org_id=org_id) if org_id else None
    except Exception:
        logger.warning("Error inicializando SecurityEventService para user=%s", getattr(user, "id", None), exc_info=True)
        return None


# `client_ip(request)` era un alias de `app.core.network.extract_client_ip`; los
# routers lo usan directamente (auditoria 2026-11, item 36: sin `Request` aqui).


# ── DB helpers ────────────────────────────────────────────────────────────────

def commit_db(db: Session) -> None:
    """Commit the current DB transaction."""
    db.commit()


# ── User lookups ──────────────────────────────────────────────────────────────

def lookup_user_by_id_active(db: Session, user_id: str):
    """Return an active User by id, or None."""
    return db.query(User).filter(User.id == user_id, User.is_active == True).first()


def lookup_user_by_credentials(db: Session, username: str):
    """Return an active User matching username or email, or None."""
    return db.query(User).filter(
        (User.username == username) | (User.email == username),
        User.is_active == True,
    ).first()


def lookup_user_by_identifier(db: Session, identifier: str):
    """Return an active User matching email or username, or None. Used by password reset."""
    return db.query(User).filter(
        (User.email == identifier) | (User.username == identifier),
        User.is_active == True,
    ).first()


# ── Session helpers ───────────────────────────────────────────────────────────

def lookup_active_refresh_session(db: Session, user_id: str, token_jti: str):
    """Return the active UserSession matching the given JTI, or None."""
    now = datetime.now(timezone.utc)
    return db.query(UserSession).filter(
        UserSession.user_id == user_id,
        UserSession.refresh_token_jti == token_jti,
        UserSession.revoked_at.is_(None),
        UserSession.expires_at > now,
    ).first()


def get_active_user_sessions(db: Session, user_id: str, now):
    """Return all non-expired, non-revoked sessions for user ordered by last activity."""
    return (
        db.query(UserSession)
        .filter(
            UserSession.user_id == user_id,
            UserSession.revoked_at.is_(None),
            UserSession.expires_at > now,
        )
        .order_by(UserSession.last_seen_at.desc())
        .all()
    )


def revoke_one_session(db: Session, session_id: str, user_id: str):
    """Revoke a specific session. Raises 404 if not found or not owned by user."""
    session = db.query(UserSession).filter(
        UserSession.id == session_id,
        UserSession.user_id == user_id,
    ).first()
    if not session:
        raise ErrorDeDominio(404, "Sesión no encontrada")
    session.revoked_at = datetime.now(timezone.utc)
    db.commit()
    return {"ok": True, "revoked": session_id}


def revoke_all_user_sessions_except_current(db: Session, user_id: str, current_jti) -> int:
    """Revoke all active sessions except the current one. Returns count revoked."""
    now = datetime.now(timezone.utc)
    q = db.query(UserSession).filter(
        UserSession.user_id == user_id,
        UserSession.revoked_at.is_(None),
    )
    if current_jti:
        q = q.filter(UserSession.refresh_token_jti != current_jti)
    sessions = q.all()
    for s in sessions:
        s.revoked_at = now
    db.commit()
    return len(sessions)


def organizacion_desactivada(db: Session, organization_id) -> bool:
    """Si la organizacion del usuario existe y esta desactivada (acceso con passkey)."""
    from app.models.mfa import Organization
    org = db.query(Organization).filter(Organization.id == organization_id).first()
    return org is not None and not org.is_active


def correo_de_usuario(db: Session, user_id: str) -> Optional[str]:
    """El correo de cualquier usuario (sin filtro de tenant): quien suplanta."""
    from app.db.session import sin_filtro_de_tenant
    with sin_filtro_de_tenant(db):
        fila = db.query(User.email).filter(User.id == user_id).first()
    return fila[0] if fila else None
