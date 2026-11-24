"""MFA por política: obligatorio por empresa, rol o capacidad sensible; métodos;
periodo de gracia; dispositivos de confianza y restablecimiento por el administrador.

El TOTP, los códigos de recuperación y las passkeys ya existían
(`app/services/auth_service/mfa.py`, `webauthn.py`); aquí se decide quién los
necesita y qué cuenta como segundo factor.

- `organizations.require_mfa` (toda la empresa): como siempre, sin factor no se
  entra (403 `mfa_obligatorio_org`).
- Por rol o capacidad sensible: la primera vez se abre el periodo de gracia
  (`users.mfa_grace_started_at`); durante la gracia se entra con aviso, y pasada
  la gracia se entra pero la API solo deja configurar el MFA
  (`mfa_configuracion_obligatoria`).
"""
from __future__ import annotations
import logging

import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional

from app.core.codigos_de_error import error
from app.services.seguridad_de_cuentas.politica import CAPACIDADES_SENSIBLES, PoliticaDeCuenta, leer

COOKIE_DISPOSITIVO = "trusted_device"


def _ahora() -> datetime:
    return datetime.now(timezone.utc)


def _aware(d):
    return d if d is None or d.tzinfo else d.replace(tzinfo=timezone.utc)


def _rol(user) -> str:
    return getattr(getattr(user, "role", None), "value", getattr(user, "role", "")) or ""


def motivo_de_exigencia(db, user, org_id: Optional[str], p: Optional[PoliticaDeCuenta] = None) -> Optional[str]:
    """`org`, `rol`, `capacidad` o None (no se le exige)."""
    if getattr(user, "is_superadmin", False):
        return None
    p = p or leer(db, org_id)
    if p.require_mfa:
        return "org"
    if _rol(user) in p.roles_con_mfa():
        return "rol"
    if p.MFA_REQUIRED_FOR_SENSITIVE:
        try:
            from app.core.capacidades import capacidades_de
            if set(capacidades_de(db, user)) & set(CAPACIDADES_SENSIBLES):
                return "capacidad"
        except Exception:
            # 24-11-2026: falla CERRADO. Si no se pueden leer las capacidades no se
            # sabe si la persona tiene alguna sensible: se le exige MFA (con el mismo
            # periodo de gracia que el motivo «capacidad», así que no bloquea el login
            # de golpe). Antes se saltaba la exigencia en silencio.
            logging.getLogger(__name__).warning("MFA: no se pudieron leer las capacidades; se exige MFA", exc_info=True)
            return "capacidad"
    return None


def factores(db, user, p: PoliticaDeCuenta) -> dict:
    """Factores del usuario que cuentan según los métodos permitidos."""
    from app.services.auth_service.webauthn import user_has_passkeys
    metodos = p.metodos()
    totp = bool(user.mfa_enabled and user.mfa_secret) and "totp" in metodos
    llave = "webauthn" in metodos and user_has_passkeys(db, user.id)
    return {"totp": totp, "webauthn": llave, "alguno": totp or llave}


def estado(db, user, org_id: Optional[str], p: Optional[PoliticaDeCuenta] = None, *, abrir_gracia: bool = False) -> dict:
    """Marcas de MFA para la pantalla y para las guardas."""
    p = p or leer(db, org_id)
    motivo = motivo_de_exigencia(db, user, org_id, p)
    tiene = factores(db, user, p)["alguno"] if motivo else True
    salida = {"mfa_required": bool(motivo), "mfa_required_by": motivo, "mfa_enrollment_required": False,
              "mfa_grace_until": None, "mfa_allowed_methods": sorted(p.metodos())}
    if not motivo or tiene or motivo == "org":
        return salida
    inicio = _aware(getattr(user, "mfa_grace_started_at", None))
    if inicio is None and abrir_gracia:
        user.mfa_grace_started_at = inicio = _ahora()
    fin = (inicio or _ahora()) + timedelta(days=p.MFA_GRACE_DAYS)
    salida["mfa_grace_until"] = fin.isoformat()
    salida["mfa_enrollment_required"] = inicio is not None and fin <= _ahora()
    return salida


def metodo_permitido(db, user, metodo: str) -> None:
    p = leer(db, getattr(user, "organization_id", None))
    if metodo not in p.metodos():
        raise error(403, "mfa_metodo_no_permitido", metodo=metodo)


def puede_quitarse_el_factor(db, user, metodo: str) -> None:
    """Si la política le exige MFA y quitar `metodo` le deja sin ninguno: 409."""
    p = leer(db, getattr(user, "organization_id", None))
    if not motivo_de_exigencia(db, user, user.organization_id, p):
        return
    f = factores(db, user, p)
    otro = f["webauthn"] if metodo == "totp" else f["totp"]
    if metodo == "webauthn":
        from app.services.auth_service.webauthn import get_active_user_credentials
        otro = otro or len(get_active_user_credentials(db, user.id)) > 1
    if not otro:
        raise error(409, "mfa_obligatorio_no_desactivable")


# ── Dispositivos de confianza ──────────────────────────────────────────────

def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def recordar(db, user, ip: Optional[str], agente: Optional[str]) -> Optional[tuple[str, int]]:
    """Crea un dispositivo de confianza. Devuelve (token, segundos) o None si está apagado."""
    from app.models.seguridad_de_cuentas import TrustedDevice
    from app.services.session_security import _parse_device_name
    p = leer(db, getattr(user, "organization_id", None))
    if p.MFA_REMEMBER_DEVICE_DAYS <= 0:
        return None
    token = secrets.token_urlsafe(32)
    db.add(TrustedDevice(user_id=user.id, organization_id=user.organization_id, token_hash=_hash(token),
                         device_name=_parse_device_name(agente), ip_address=(ip or None),
                         expires_at=_ahora() + timedelta(days=p.MFA_REMEMBER_DEVICE_DAYS)))
    return token, p.MFA_REMEMBER_DEVICE_DAYS * 86400


def dispositivo_valido(db, user, token: Optional[str]) -> bool:
    """¿Es `token` un dispositivo de confianza vivo de `user`, con la política aún encendida?"""
    if not token:
        return False
    from app.db.session import sin_filtro_de_tenant
    from app.models.seguridad_de_cuentas import TrustedDevice
    p = leer(db, getattr(user, "organization_id", None))
    if p.MFA_REMEMBER_DEVICE_DAYS <= 0:
        return False
    with sin_filtro_de_tenant(db):
        d = db.query(TrustedDevice).filter(TrustedDevice.token_hash == _hash(token),
                                           TrustedDevice.user_id == user.id,
                                           TrustedDevice.revoked_at.is_(None)).first()
    if d is None or (_aware(d.expires_at) and _aware(d.expires_at) <= _ahora()):
        return False
    d.last_used_at = _ahora()
    return True


def revocar_dispositivos(db, user_id: str, motivo: str) -> int:
    from app.db.session import sin_filtro_de_tenant
    from app.models.seguridad_de_cuentas import TrustedDevice
    with sin_filtro_de_tenant(db):
        filas = db.query(TrustedDevice).filter(TrustedDevice.user_id == user_id,
                                               TrustedDevice.revoked_at.is_(None)).all()
    for d in filas:
        d.revoked_at, d.revoke_reason = _ahora(), motivo[:120]
    return len(filas)


def dispositivos(db, user_id: str) -> list[dict]:
    from app.db.session import sin_filtro_de_tenant
    from app.models.seguridad_de_cuentas import TrustedDevice
    with sin_filtro_de_tenant(db):
        filas = (db.query(TrustedDevice).filter(TrustedDevice.user_id == user_id, TrustedDevice.revoked_at.is_(None),
                                                TrustedDevice.expires_at > _ahora())
                 .order_by(TrustedDevice.created_at.desc()).all())
    return [{"id": d.id, "device_name": d.device_name, "ip_address": d.ip_address, "created_at": d.created_at,
             "last_used_at": d.last_used_at, "expires_at": d.expires_at} for d in filas]


def revocar_dispositivo(db, user_id: str, device_id: str) -> None:
    from app.models.seguridad_de_cuentas import TrustedDevice
    d = db.query(TrustedDevice).filter(TrustedDevice.id == device_id, TrustedDevice.user_id == user_id).first()
    if d is None:
        raise error(404, "no_encontrado", que="dispositivo")
    d.revoked_at, d.revoke_reason = _ahora(), "revoked_by_user"


# ── Restablecer el MFA de otro (administrador) ─────────────────────────────

def restablecer(db, objetivo) -> dict:
    """Borra TOTP, códigos, passkeys y dispositivos; revoca sus sesiones. No confirma."""
    from app.models.mfa import WebAuthnCredential
    from app.services.auth_service.mfa import borrar_codigos_de_respaldo
    from app.services.auth_service.tokens_y_cookies import revocar_sesiones_del_usuario
    objetivo.mfa_secret = None
    objetivo.mfa_enabled = False
    objetivo.mfa_verified_at = None
    objetivo.mfa_last_timestep = None
    objetivo.mfa_grace_started_at = _ahora()   # vuelve a tener la gracia para configurarlo
    borrar_codigos_de_respaldo(db, objetivo)
    llaves = 0
    for c in db.query(WebAuthnCredential).filter(WebAuthnCredential.user_id == objetivo.id,
                                                 WebAuthnCredential.is_active.is_(True)).all():
        c.is_active = False
        llaves += 1
    return {"passkeys_disabled": llaves, "trusted_devices_revoked": revocar_dispositivos(db, objetivo.id, "mfa_reset"),
            "sessions_revoked": revocar_sesiones_del_usuario(db, objetivo.id, "mfa_reset")}
