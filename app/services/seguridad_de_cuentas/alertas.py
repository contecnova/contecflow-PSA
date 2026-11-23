"""Alertas de seguridad al administrador y avisos al usuario (campana existente).

Textos en es/en/zh registrados en `textos_de_salida.TEXTOS` (cada aviso se pinta
en el idioma de su destinatario). Nunca propaga: una alerta que falla no puede
tumbar un login.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

logger = logging.getLogger(__name__)

TIPO = "security_alert"

TEXTOS = {
    "seguridad.alerta.titulo": {"es": "Alerta de seguridad", "en": "Security alert", "zh": "安全警报"},
    "seguridad.alerta.fallos_masivos": {
        "es": "{n} intentos de acceso fallidos en los últimos 15 minutos en la empresa.",
        "en": "{n} failed sign-in attempts in the company in the last 15 minutes.",
        "zh": "过去 15 分钟内公司有 {n} 次登录失败。"},
    "seguridad.alerta.ip_nueva": {
        "es": "{usuario} ha entrado desde una IP nueva ({ip}).",
        "en": "{usuario} signed in from a new IP ({ip}).",
        "zh": "{usuario} 从新的 IP（{ip}）登录。"},
    "seguridad.alerta.mfa_desactivado": {
        "es": "{usuario} ha desactivado su segundo factor.",
        "en": "{usuario} disabled their second factor.",
        "zh": "{usuario} 已停用其第二因素认证。"},
    "seguridad.alerta.mfa_restablecido": {
        "es": "{actor} ha restablecido el segundo factor de {usuario}.",
        "en": "{actor} reset the second factor of {usuario}.",
        "zh": "{actor} 已重置 {usuario} 的第二因素认证。"},
    "seguridad.alerta.politica": {
        "es": "{actor} ha cambiado la política de seguridad: {claves}.",
        "en": "{actor} changed the security policy: {claves}.",
        "zh": "{actor} 修改了安全策略：{claves}。"},
    "seguridad.alerta.bloqueo": {
        "es": "La cuenta de {usuario} se ha bloqueado por intentos fallidos.",
        "en": "The account of {usuario} was locked after failed attempts.",
        "zh": "{usuario} 的账户因多次失败尝试已被锁定。"},
    "seguridad.alerta.solicitud": {
        "es": "{actor} pide un cambio de seguridad que necesita la aprobación de otro administrador.",
        "en": "{actor} requested a security change that needs another administrator's approval.",
        "zh": "{actor} 请求了一项需要另一位管理员批准的安全变更。"},
    "seguridad.alerta.bypass": {
        "es": "Se ha usado el acceso de recuperación del superadministrador (ENABLE_SUPERADMIN_BYPASS).",
        "en": "The superadmin recovery bypass (ENABLE_SUPERADMIN_BYPASS) was used.",
        "zh": "已使用超级管理员恢复旁路（ENABLE_SUPERADMIN_BYPASS）。"},
    "seguridad.aviso.titulo": {"es": "Seguridad de tu cuenta", "en": "Your account security", "zh": "您的账户安全"},
    "seguridad.aviso.bloqueo": {
        "es": "Tu cuenta se ha bloqueado {min} minutos por intentos de acceso fallidos. Si no has sido tú, avisa a tu administrador.",
        "en": "Your account was locked for {min} minutes after failed sign-in attempts. If it was not you, tell your administrator.",
        "zh": "由于多次登录失败，您的账户已被锁定 {min} 分钟。如果不是您本人操作，请告知管理员。"},
    "seguridad.aviso.caducidad": {
        "es": "Tu contraseña caduca en {dias} días. Cámbiala desde tu perfil.",
        "en": "Your password expires in {dias} days. Change it from your profile.",
        "zh": "您的密码将在 {dias} 天后过期。请在个人资料中修改。"},
    "seguridad.aviso.cambio_forzado": {
        "es": "Tu administrador te pide que cambies la contraseña la próxima vez que entres.",
        "en": "Your administrator requires you to change your password next time you sign in.",
        "zh": "管理员要求您在下次登录时修改密码。"},
    "seguridad.aviso.recertificacion": {
        "es": "Tienes {n} accesos pendientes de revisar en la campaña «{campana}».",
        "en": "You have {n} accesses to review in the campaign «{campana}».",
        "zh": "您在“{campana}”活动中有 {n} 项访问权限待审核。"},
}


def _registrar_textos() -> None:
    try:
        from app.services import textos_de_salida
        for k, v in TEXTOS.items():
            textos_de_salida.TEXTOS.setdefault(k, v)
    except Exception:
        logger.debug("textos de seguridad no registrados", exc_info=True)


_registrar_textos()


def a_los_admins(db, org_id: Optional[str], clave: str, **params) -> int:
    """Aviso a los administradores activos de la empresa. Nunca propaga."""
    if not org_id:
        return 0
    try:
        from app.services.notifications import notify_role
        from app.services.textos_de_salida import texto
        return notify_role(db, "admin", TIPO, texto("seguridad.alerta.titulo", "es"), texto(clave, "es", **params),
                           resource="security", action_url="/settings/seguridad-cuentas",
                           organization_id=org_id,
                           aviso={"titulo": "seguridad.alerta.titulo", "cuerpo": clave, "params": params})
    except Exception:
        logger.warning("alerta de seguridad %s no enviada (org=%s)", clave, org_id, exc_info=True)
        return 0


def al_usuario(db, user_id: str, clave: str, **params) -> None:
    try:
        from app.services.notifications import notify_user
        from app.services.textos_de_salida import texto
        notify_user(db, user_id, TIPO, texto("seguridad.aviso.titulo", "es"), texto(clave, "es", **params),
                    resource="security", action_url="/profile",
                    aviso={"titulo": "seguridad.aviso.titulo", "cuerpo": clave, "params": params})
    except Exception:
        logger.warning("aviso de seguridad %s no enviado (user=%s)", clave, user_id, exc_info=True)


def fallos_masivos(db, org_id: Optional[str], umbral: int) -> None:
    """Si la empresa pasa de `umbral` fallos en 15 min, alerta (una vez por ventana)."""
    if not org_id or umbral <= 0:
        return
    try:
        from app.db.session import sin_filtro_de_tenant
        from app.models.security_observability import SecurityEvent
        desde = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(minutes=15)  # occurred_at es naive (UTC)
        with sin_filtro_de_tenant(db):
            n = db.query(SecurityEvent).filter(SecurityEvent.org_id == org_id,
                                               SecurityEvent.event_type == "login_failed",
                                               SecurityEvent.occurred_at >= desde).count()
        if n == umbral:   # justo al cruzar: una alerta, no una por fallo
            a_los_admins(db, org_id, "seguridad.alerta.fallos_masivos", n=n)
    except Exception:
        logger.debug("fallos_masivos: no medible", exc_info=True)


def ip_nueva(db, user, ip: Optional[str], salvo_jti: Optional[str] = None) -> None:
    """Alerta si el usuario entra desde una IP que no consta en sus sesiones anteriores."""
    if not ip or getattr(user, "is_superadmin", False):
        return
    try:
        from app.db.session import sin_filtro_de_tenant
        from app.models.sessions import UserSession
        with sin_filtro_de_tenant(db), db.no_autoflush:
            otras = db.query(UserSession.id).filter(UserSession.user_id == user.id)
            if salvo_jti:
                otras = otras.filter(UserSession.refresh_token_jti != salvo_jti)
            vistas = otras.filter(UserSession.ip_address == ip).first()
            alguna = otras.first()
        if alguna and not vistas:
            a_los_admins(db, user.organization_id, "seguridad.alerta.ip_nueva",
                         usuario=user.email or user.username, ip=ip)
    except Exception:
        logger.debug("ip_nueva: no medible", exc_info=True)
