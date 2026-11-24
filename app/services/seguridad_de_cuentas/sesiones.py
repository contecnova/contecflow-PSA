"""Sesiones: política al abrir (acceso, concurrentes, IP nueva) y en cada petición.

El token de acceso lleva `sid` = `user_sessions.session_key` (el primer jti de la
sesión, estable al rotar). En cada petición se comprueba que esa sesión sigue
viva, que no lleva más inactividad de la permitida ni pasa de su tope; así
revocar corta en el acto y no a los 15 minutos de vida del token.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from app.core.codigos_de_error import error

logger = logging.getLogger(__name__)

#: Cada cuánto como mucho se escribe `last_seen_at` (segundos).
MARCA_DE_ACTIVIDAD_S = 60


def _ahora() -> datetime:
    return datetime.now(timezone.utc)


def _aware(d):
    return d if d is None or d.tzinfo else d.replace(tzinfo=timezone.utc)


def al_abrir(db, user, sesion, ip: Optional[str], request=None, pais: Optional[str] = None) -> None:
    """Sesión NUEVA (no rotación): acceso, IP nueva y máximo de concurrentes. No confirma."""
    from app.db.session import sin_filtro_de_tenant
    from app.models.sessions import UserSession
    from app.services.seguridad_de_cuentas import acceso, alertas
    from app.services.seguridad_de_cuentas.politica import leer
    if user is None:
        return
    org = getattr(sesion, "organization_id", None) or getattr(user, "organization_id", None)
    p = leer(db, org)
    acceso.comprobar(db, user, org, ip, request, pais, p)
    if p.SECURITY_ALERT_NEW_IP:
        alertas.ip_nueva(db, user, ip, sesion.refresh_token_jti)
    sesion.session_key = sesion.session_key or sesion.refresh_token_jti
    if p.SESSION_MAX_CONCURRENT > 0 and not getattr(user, "is_superadmin", False):
        with sin_filtro_de_tenant(db):
            vivas = (db.query(UserSession).filter(UserSession.user_id == user.id,
                                                  UserSession.revoked_at.is_(None),
                                                  UserSession.expires_at > _ahora(),
                                                  UserSession.refresh_token_jti != sesion.refresh_token_jti)
                     .order_by(UserSession.created_at.asc()).all())
        sobran = len(vivas) - (p.SESSION_MAX_CONCURRENT - 1)
        for s in vivas[:max(0, sobran)]:
            s.revoked_at = _ahora()
            s.revoke_reason = "concurrent_limit"


def _rechazar(codigo: str):
    from app.core.codigos_de_error import error_http
    raise error_http(401, codigo, {"WWW-Authenticate": "Bearer"})


def comprobar_sesion(db, user, sid: Optional[str], org: Optional[str], p=None) -> None:
    """La sesión `sid` sigue viva, sin pasar la inactividad ni el tope. Si no, 401."""
    if not sid:
        return
    from app.db.session import sin_filtro_de_tenant
    from app.models.sessions import UserSession
    from app.services.seguridad_de_cuentas.politica import leer
    with sin_filtro_de_tenant(db):
        s = (db.query(UserSession).filter(UserSession.user_id == user.id, UserSession.session_key == sid)
             .order_by(UserSession.created_at.desc()).first())
    if s is None:
        return   # sesión anterior a la migración 199: sin fila con clave, decide el refresco
    ahora = _ahora()
    if s.revoked_at is not None or (_aware(s.expires_at) and _aware(s.expires_at) <= ahora):
        _rechazar("sesion_revocada")
    p = p or leer(db, org or getattr(user, "organization_id", None))
    visto = _aware(s.last_seen_at) or _aware(s.created_at) or ahora
    if p.idle_timeout_enabled and p.idle_timeout_minutes and ahora - visto > timedelta(minutes=p.idle_timeout_minutes):
        s.revoked_at, s.revoke_reason = ahora, "idle_timeout"
        db.commit()
        _rechazar("sesion_inactiva")
    inicio = _aware(s.created_at) or ahora
    if p.SESSION_MAX_HOURS and ahora - inicio > timedelta(hours=p.SESSION_MAX_HOURS):
        s.revoked_at, s.revoke_reason = ahora, "max_duration"
        db.commit()
        _rechazar("sesion_caducada_por_duracion")
    if (ahora - visto).total_seconds() > MARCA_DE_ACTIVIDAD_S:
        s.last_seen_at = ahora
        try:
            db.commit()
        except Exception:
            db.rollback()
            logger.debug("last_seen_at no guardado", exc_info=True)


def revocar_todas(db, user_id: str, motivo: str, salvo_jti: Optional[str] = None) -> int:
    from app.services.auth_service.tokens_y_cookies import revocar_sesiones_del_usuario
    return revocar_sesiones_del_usuario(db, user_id, motivo, salvo_jti=salvo_jti)


def de_la_empresa(db, org_id: str) -> list:
    """Sesiones vivas de los miembros de la empresa (para el administrador)."""
    from app.db.session import _miembros_de, sin_filtro_de_tenant
    from app.models.sessions import UserSession
    from app.models.user import User
    with sin_filtro_de_tenant(db):
        ids = [u for (u,) in db.query(User.id).filter(_miembros_de(User, org_id))]
        filas = (db.query(UserSession, User).join(User, User.id == UserSession.user_id)
                 .filter(UserSession.user_id.in_(ids or [""]), UserSession.revoked_at.is_(None),
                         UserSession.expires_at > _ahora())
                 .order_by(UserSession.last_seen_at.desc()).limit(1000).all())
    return [{"id": s.id, "user_id": u.id, "user": u.full_name, "email": u.email, "ip_address": s.ip_address,
             "country_code": s.country_code, "device_name": s.device_name, "auth_method": s.auth_method,
             "risk_level": s.risk_level, "created_at": s.created_at, "last_seen_at": s.last_seen_at,
             "expires_at": s.expires_at} for s, u in filas]


def revocar_una_de_la_empresa(db, org_id: str, session_id: str):
    """La sesión `session_id` de un miembro de la empresa (404 si es de otra)."""
    from app.db.session import _miembros_de, sin_filtro_de_tenant
    from app.models.sessions import UserSession
    from app.models.user import User
    with sin_filtro_de_tenant(db):
        fila = (db.query(UserSession, User).join(User, User.id == UserSession.user_id)
                .filter(UserSession.id == session_id, _miembros_de(User, org_id)).first())
    if fila is None:
        raise error(404, "no_encontrado", que="sesion")
    s, u = fila
    s.revoked_at, s.revoke_reason = _ahora(), "revoked_by_admin"
    return s, u
