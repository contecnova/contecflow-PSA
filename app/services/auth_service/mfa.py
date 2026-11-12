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

def organizacion_exige_mfa(db, user) -> bool:
    """Devuelve si la organizacion de este usuario obliga a segundo factor.

    Auditoria 2026-08 (hallazgo 22): la consulta estaba en
    `routers/auth_core.py`. `Organization` es el unico modelo sin columna de
    tenant y `TenantSession` no lo filtra, asi que se busca por el id que trae
    el propio usuario — nunca por uno que venga del cliente.
    """
    from app.models.mfa import Organization

    org_id = getattr(user, "organization_id", None)
    if not org_id:
        return False
    org = db.query(Organization).filter(Organization.id == org_id).first()
    return bool(org and getattr(org, "require_mfa", False))


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
