"""MFA: exigencia por organizacion, secreto y reto de segundo factor.

Parte de `app.services.auth_service` (auditoria 2026-11, #24): se partio por responsabilidad
sin cambiar el codigo. El paquete reexporta todos los nombres.
"""
from datetime import datetime, timedelta, timezone
from typing import Optional
from sqlalchemy.orm import Session
from app.core.security import (
    create_mfa_challenge_token,
    decode_token,
)
from app.db.session import is_postgres
from app.models.mfa import MFAChallenge
from app.models.user import User
from app.core.errores import ErrorDeDominio


# ── SOC helper ────────────────────────────────────────────────────────────────

def organizacion_exige_mfa(db, user, org_id: Optional[str] = None) -> bool:
    """Devuelve si la organizacion de este usuario obliga a segundo factor.

    Auditoria 2026-08 (hallazgo 22): la consulta estaba en
    `routers/auth_core.py`. `Organization` es el unico modelo sin columna de
    tenant y `TenantSession` no lo filtra, asi que se busca por el id que trae
    el propio usuario — nunca por uno que venga del cliente.

    `org_id`: la empresa en la que se abre la sesion, ya validada por
    `entrada_service` (la del proveedor SSO, la elegida). Si no, la del usuario.
    """
    from app.models.mfa import Organization

    org_id = org_id or getattr(user, "organization_id", None)
    if not org_id:
        return False
    org = db.query(Organization).filter(Organization.id == org_id).first()
    return bool(org and getattr(org, "require_mfa", False))


def exigir_reautenticacion(db, user, password: Optional[str] = None, code: Optional[str] = None) -> None:
    """401 si quien llama no confirma su identidad: contrasena actual o codigo TOTP.

    Auditoria 2026-11 (#21): `POST /auth/mfa/setup` reiniciaba el secreto y
    apagaba el 2FA, y registrar una passkey no pedia nada mas que la sesion. Con
    una sesion robada (o un token de acceso filtrado) se desactivaba el segundo
    factor o se anadia una passkey propia. Ahora se pide prueba de que quien
    esta detras sabe la contrasena o tiene el autenticador.

    El codigo TOTP sigue la misma regla anti-reutilizacion que el login: un paso
    ya aceptado no vale otra vez.
    """
    import time

    from app.core.encryption import decrypt_value
    from app.core.security import verify_password

    if password and getattr(user, "hashed_password", None):
        try:
            if verify_password(password, user.hashed_password):
                return
        except Exception:
            __import__("logging").getLogger(__name__).warning("exigir_reautenticacion: hash de contrasena ilegible", exc_info=True)
    codigo = (code or "").strip()
    if codigo and user.mfa_enabled and user.mfa_secret:
        try:
            import pyotp
        except ImportError:  # pragma: no cover
            pyotp = None
        if pyotp is not None:
            totp = pyotp.TOTP(decrypt_value(user.mfa_secret) or "")
            ahora = time.time()
            for desfase in (0, -1, 1):
                instante = ahora + desfase * totp.interval
                if totp.verify(codigo, for_time=instante, valid_window=0):
                    paso = totp.timecode(datetime.fromtimestamp(instante, tz=timezone.utc))
                    if user.mfa_last_timestep is None or paso > user.mfa_last_timestep:
                        user.mfa_last_timestep = paso
                        return
                    break
    raise ErrorDeDominio(401, "Confirma tu identidad: contraseña actual o código 2FA")


def guardar_secreto_de_mfa(db, user, secreto_cifrado: str) -> None:
    """Guarda el secreto TOTP del usuario y deja el MFA sin activar. No confirma.

    Auditoria 2026-08 (hallazgo 22): esto estaba en `routers/auth_mfa.py`. El
    `db.add()` sobre una fila que ya esta en la sesion no hace falta —SQLAlchemy
    la sigue por identidad— pero se conserva: cambiar el comportamiento de un
    camino de autenticacion en una tanda de reordenacion no toca.

    `mfa_enabled` se queda en `False` a proposito: el secreto existe pero el
    segundo factor no cuenta hasta que el usuario verifica un codigo.
    """
    user.mfa_secret = secreto_cifrado
    user.mfa_enabled = False
    db.add(user)


# ── Codigos de respaldo y estado ─────────────────────────────────────────────
# Auditoria 2026-11: vivian colgados de `mfa_configs`, el segundo sistema TOTP
# que el login no miraba. Ahora son del usuario, como su secreto.

CODIGOS_DE_RESPALDO = 8


def generar_codigos_de_respaldo(db, user) -> list[str]:
    """Sustituye los codigos del usuario por 8 nuevos; devuelve los claros (solo esta vez)."""
    import secrets

    import bcrypt
    from app.models.mfa import MFABackupCode

    borrar_codigos_de_respaldo(db, user)
    claros = []
    for _ in range(CODIGOS_DE_RESPALDO):
        claro = secrets.token_hex(4).upper()
        db.add(MFABackupCode(user_id=user.id, organization_id=getattr(user, "organization_id", None),
                             code_hash=bcrypt.hashpw(claro.encode(), bcrypt.gensalt()).decode()))
        claros.append(claro)
    return claros


def borrar_codigos_de_respaldo(db, user) -> None:
    from app.models.mfa import MFABackupCode
    db.query(MFABackupCode).filter(MFABackupCode.user_id == user.id).delete(synchronize_session=False)


def consumir_codigo_de_respaldo(db, user, code: str) -> bool:
    """Gasta un codigo de respaldo sin usar del usuario; True si valia. No confirma."""
    import bcrypt
    from app.models.mfa import MFABackupCode

    codigo = (code or "").strip().upper()
    if not codigo:
        return False
    for fila in db.query(MFABackupCode).filter(MFABackupCode.user_id == user.id,
                                               MFABackupCode.used_at.is_(None)):
        if bcrypt.checkpw(codigo.encode(), fila.code_hash.encode()):
            fila.used_at = datetime.now(timezone.utc)
            return True
    return False


def estado_de_mfa(db, user) -> dict:
    """Lo mismo que mira el login (`auth_core._segundo_factor_o_sesion`)."""
    from sqlalchemy import func
    from app.models.mfa import MFABackupCode
    from app.services.auth_service.webauthn import get_active_user_credentials

    totp = bool(user.mfa_enabled and user.mfa_secret)
    passkeys = len(get_active_user_credentials(db, user.id))
    restantes = db.query(func.count(MFABackupCode.id)).filter(
        MFABackupCode.user_id == user.id, MFABackupCode.used_at.is_(None)).scalar() or 0
    return {
        "enabled": totp,
        "passkeys": passkeys,
        "second_factor": totp or passkeys > 0,
        # Con cualquier segundo factor, `POST /auth/mfa/setup` pide contrasena o codigo.
        "reauth_required": bool(user.mfa_enabled),
        "verified_at": user.mfa_verified_at.isoformat()[:16] if totp and user.mfa_verified_at else None,
        "backup_codes_remaining": restantes if totp else 0,
    }


# ── MFA challenge helpers ─────────────────────────────────────────────────────

def mfa_challenge_query(db: Session):
    q = db.query(MFAChallenge)
    if is_postgres():
        q = q.with_for_update()
    return q


def issue_mfa_challenge(db: Session, user: User, org: Optional[str] = None) -> str:
    token, jti = create_mfa_challenge_token(user.id, org=org)
    db.query(MFAChallenge).filter(
        MFAChallenge.user_id == user.id,
        MFAChallenge.consumed_at.is_(None),
    ).update({"consumed_at": datetime.now(timezone.utc)})
    db.add(MFAChallenge(
        user_id=user.id,
        token_jti=jti,
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=5),
    ))
    db.commit()
    return token


def read_mfa_challenge(db: Session, challenge_token: str) -> tuple[dict, MFAChallenge]:
    challenge_data = decode_token(challenge_token)
    if not challenge_data or challenge_data.get("type") != "mfa_challenge":
        raise ErrorDeDominio(401, "mfa_challenge_token inválido o expirado")

    challenge_jti = challenge_data.get("jti")
    user_id = challenge_data.get("sub")
    if not challenge_jti or not user_id:
        raise ErrorDeDominio(401, "mfa_challenge_token inválido")

    row = mfa_challenge_query(db).filter(
        MFAChallenge.user_id == user_id,
        MFAChallenge.token_jti == challenge_jti,
    ).first()
    expires_at = row.expires_at if row else None
    if expires_at and expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if not row or not expires_at or expires_at <= datetime.now(timezone.utc):
        raise ErrorDeDominio(401, "mfa_challenge_token inválido o expirado")
    if row.consumed_at is not None:
        raise ErrorDeDominio(401, "mfa_challenge_token ya utilizado")
    return challenge_data, row


def consume_mfa_challenge(row: MFAChallenge) -> None:
    row.consumed_at = datetime.now(timezone.utc)
