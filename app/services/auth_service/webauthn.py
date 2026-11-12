"""Credenciales WebAuthn (passkeys): consulta y alta.

Parte de `app.services.auth_service` (auditoria 2026-11, #24): se partio por responsabilidad
sin cambiar el codigo. El paquete reexporta todos los nombres.
"""
from sqlalchemy.orm import Session
from app.models.mfa import WebAuthnCredential
from app.core.errores import ErrorDeDominio


# ── WebAuthn helpers ──────────────────────────────────────────────────────────

def user_has_passkeys(db: Session, user_id: str) -> bool:
    """Return True if user has at least one active WebAuthn credential."""
    return (
        db.query(WebAuthnCredential.id)
        .filter(WebAuthnCredential.user_id == user_id, WebAuthnCredential.is_active == True)
        .first()
        is not None
    )


def get_active_user_credentials(db: Session, user_id: str):
    """Return all active WebAuthn credentials for a user, newest first."""
    return (
        db.query(WebAuthnCredential)
        .filter(WebAuthnCredential.user_id == user_id, WebAuthnCredential.is_active == True)
        .order_by(WebAuthnCredential.created_at.desc())
        .all()
    )


def get_active_webauthn_credential(db: Session, pk_id: str, user_id: str):
    """Find active WebAuthnCredential by pk UUID and user_id."""
    return db.query(WebAuthnCredential).filter(
        WebAuthnCredential.id == pk_id,
        WebAuthnCredential.user_id == user_id,
        WebAuthnCredential.is_active == True,
    ).first()


def has_remaining_active_credentials(db: Session, user_id: str, exclude_pk_id: str) -> bool:
    """Return True if user has other active credentials besides exclude_pk_id."""
    return (
        db.query(WebAuthnCredential.id)
        .filter(
            WebAuthnCredential.user_id == user_id,
            WebAuthnCredential.is_active == True,
            WebAuthnCredential.id != exclude_pk_id,
        )
        .first()
        is not None
    )


def get_webauthn_credential_for_auth(db: Session, user_id: str, credential_id: str):
    """Find active WebAuthnCredential by user_id and webauthn credential_id for authentication."""
    return db.query(WebAuthnCredential).filter(
        WebAuthnCredential.user_id == user_id,
        WebAuthnCredential.credential_id == credential_id,
        WebAuthnCredential.is_active == True,
    ).first()


def get_credential_by_credential_id(db: Session, credential_id: str):
    """Find a WebAuthnCredential by its webauthn credential_id (any user)."""
    return db.query(WebAuthnCredential).filter(
        WebAuthnCredential.credential_id == credential_id,
    ).first()


def upsert_webauthn_credential(
    db: Session,
    current_user_id: str,
    credential_id: str,
    public_key: str,
    sign_count: int,
    transports: str,
    nickname,
) -> None:
    """Add or update a WebAuthn credential. Raises 409 if credential belongs to another user."""
    existing = get_credential_by_credential_id(db, credential_id)
    if existing and existing.user_id != current_user_id:
        raise ErrorDeDominio(409, "La passkey ya está registrada para otro usuario")
    if existing:
        existing.public_key = public_key
        existing.sign_count = sign_count
        existing.is_active = True
        if nickname:
            existing.name = nickname
    else:
        db.add(WebAuthnCredential(
            user_id=current_user_id,
            credential_id=credential_id,
            public_key=public_key,
            sign_count=sign_count,
            transports=transports,
            name=nickname,
            is_active=True,
        ))
