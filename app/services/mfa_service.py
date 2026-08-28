"""MFA (TOTP): alta, verificacion y baja del segundo factor.

Auditoria 2026-08 (hallazgo 22). Este codigo vivia en `mfa_service.py`, un
fichero de 1.435 lineas que contenia OCHO dominios sin relacion entre si —MFA,
organizaciones, Slack, presupuestos, planificacion asistida, escenarios, PDF y
tokens de BI— servidos ademas por un unico router llamado `mfa.py` con 38 rutas.

El reparto se pudo hacer mecanicamente porque los ocho dominios nunca estuvieron
acoplados, solo apilados: se comprobo por AST que no habia ni una llamada entre
grupos ni un solo ciclo. Los cuerpos se movieron verbatim.
"""

import secrets
from datetime import datetime, timezone
from sqlalchemy.orm import Session
from sqlalchemy import func
from app.core.config import settings
from app.core.encryption import encrypt_value, decrypt_value
from app.models.user import User
from app.models.mfa import (
    MFAConfig, MFABackupCode,
)
from app.services.audit import audit_log


def get_totp_lib():
    try:
        import pyotp
        return pyotp
    except ImportError:
        return None


def get_mfa_status(user_id: str, db: Session) -> dict:
    config = db.query(MFAConfig).filter(MFAConfig.user_id == user_id).first()
    if not config:
        return {"enabled": False, "has_config": False}
    backup_count = db.query(func.count(MFABackupCode.id)).filter(
        MFABackupCode.mfa_id == config.id,
        MFABackupCode.used_at == None,
    ).scalar()
    return {
        "enabled": config.is_enabled,
        "has_config": True,
        "verified_at": str(config.verified_at)[:16] if config.verified_at else None,
        "last_used_at": str(config.last_used_at)[:16] if config.last_used_at else None,
        "backup_codes_remaining": backup_count or 0,
    }


def setup_mfa(user: User, db: Session) -> dict:
    pyotp = get_totp_lib()
    if not pyotp:
        raise ValueError("pyotp no instalado — ejecuta: pip install pyotp")

    existing = db.query(MFAConfig).filter(MFAConfig.user_id == user.id).first()
    if existing and existing.is_enabled:
        raise ValueError("MFA ya está activado. Desactívalo antes de reconfigurar.")
    if existing:
        db.delete(existing)
        db.flush()

    secret = pyotp.random_base32()
    totp = pyotp.TOTP(secret)
    uri = totp.provisioning_uri(name=user.email, issuer_name="Contecflow")

    config = MFAConfig(
        user_id=user.id,
        totp_secret=encrypt_value(secret),
        is_enabled=False,
    )
    db.add(config)
    db.commit()

    return {
        "secret": secret,
        "provisioning_uri": uri,
        "qr_url": f"{settings.GOOGLE_CHART_URL}?chs=200x200&chld=M|0&cht=qr&chl={uri}",
        "instructions": "Escanea el QR con Google Authenticator, Authy o similar. Luego llama a POST /mfa/verify con el código de 6 dígitos para activar.",
    }


def verify_and_activate_mfa(user: User, code: str, db: Session) -> dict:
    import bcrypt
    pyotp = get_totp_lib()
    if not pyotp:
        raise ValueError("pyotp no instalado")

    config = db.query(MFAConfig).filter(MFAConfig.user_id == user.id).first()
    if not config:
        raise ValueError("Primero llama a /mfa/setup")

    totp = pyotp.TOTP(decrypt_value(config.totp_secret) or config.totp_secret)
    if not totp.verify(code, valid_window=1):
        raise ValueError("Código incorrecto o caducado")

    config.is_enabled = True
    config.verified_at = datetime.now(timezone.utc)
    config.last_used_at = datetime.now(timezone.utc)

    backup_codes = []
    for _ in range(8):
        raw = secrets.token_hex(4).upper()
        hashed = bcrypt.hashpw(raw.encode(), bcrypt.gensalt()).decode()
        db.add(MFABackupCode(mfa_id=config.id, code_hash=hashed))
        backup_codes.append(raw)

    audit_log(db, user, "MFA_ENABLED", "users", user.id, user.email)
    db.commit()

    return {
        "ok": True,
        "message": "MFA activado correctamente",
        "backup_codes": backup_codes,
        "warning": "Guarda estos códigos en un lugar seguro. Solo se muestran una vez.",
    }


def validate_mfa_code(user: User, code: str, db: Session) -> dict:
    import bcrypt
    pyotp = get_totp_lib()
    config = db.query(MFAConfig).filter(
        MFAConfig.user_id == user.id,
        MFAConfig.is_enabled == True,
    ).first()
    if not config:
        return {"ok": True, "mfa_required": False}
    if not pyotp:
        raise ValueError("pyotp no instalado — ejecuta: pip install pyotp")

    totp = pyotp.TOTP(decrypt_value(config.totp_secret) or config.totp_secret)
    if totp.verify(code, valid_window=1):
        config.last_used_at = datetime.now(timezone.utc)
        db.commit()
        return {"ok": True, "valid": True}

    backup_codes = db.query(MFABackupCode).filter(
        MFABackupCode.mfa_id == config.id,
        MFABackupCode.used_at == None,
    ).all()
    for bc in backup_codes:
        if bcrypt.checkpw(code.upper().encode(), bc.code_hash.encode()):
            bc.used_at = datetime.now(timezone.utc)
            config.last_used_at = datetime.now(timezone.utc)
            db.commit()
            remaining = db.query(func.count(MFABackupCode.id)).filter(
                MFABackupCode.mfa_id == config.id, MFABackupCode.used_at == None,
            ).scalar()
            return {"ok": True, "valid": True, "used_backup_code": True,
                    "backup_codes_remaining": remaining}

    raise ValueError("Código MFA inválido")


def disable_mfa(user: User, code: str, db: Session) -> dict:
    pyotp = get_totp_lib()
    if not pyotp:
        raise ValueError("pyotp no instalado — ejecuta: pip install pyotp")
    config = db.query(MFAConfig).filter(
        MFAConfig.user_id == user.id, MFAConfig.is_enabled == True,
    ).first()
    if not config:
        raise ValueError("MFA no está activado")
    totp = pyotp.TOTP(decrypt_value(config.totp_secret) or config.totp_secret)
    if not totp.verify(code, valid_window=1):
        raise ValueError("Código incorrecto")
    config.is_enabled = False
    audit_log(db, user, "MFA_DISABLED", "users", user.id, user.email)
    db.commit()
    return {"ok": True}
