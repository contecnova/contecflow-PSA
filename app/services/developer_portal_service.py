"""Service layer for Developer Portal — OAuth2 app & token management."""
import json
import uuid
import secrets
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session
from sqlalchemy import func as sa_func

from app.models.oauth_apps import OAuthApp, OAuthToken
from app.models.user import User


# ── App queries ─────────────────────────────────────────────────────────────────

def list_apps_for_user(db: Session, user_id: str) -> list[OAuthApp]:
    return db.query(OAuthApp).filter(OAuthApp.owner_id == user_id).all()


def count_apps_for_user(db: Session, user_id: str) -> int:
    return db.query(sa_func.count(OAuthApp.id)).filter(OAuthApp.owner_id == user_id).scalar() or 0


def get_app_by_id(db: Session, app_id: str) -> OAuthApp | None:
    return db.query(OAuthApp).filter(OAuthApp.id == app_id).first()


def get_app_by_client_id(db: Session, client_id: str) -> OAuthApp | None:
    return db.query(OAuthApp).filter(
        OAuthApp.client_id == client_id,
        OAuthApp.is_active == True,
    ).first()


# ── App mutations ───────────────────────────────────────────────────────────────

def create_app(
    db: Session,
    *,
    name: str,
    description: str | None,
    homepage_url: str | None,
    redirect_uris: list[str],
    scopes: list[str],
    owner_id: str,
    secret_hash: str,
) -> OAuthApp:
    app = OAuthApp(
        id=str(uuid.uuid4()),
        name=name,
        description=description,
        homepage_url=homepage_url,
        client_id=f"nxpm_{secrets.token_urlsafe(16)}",
        client_secret_hash=secret_hash,
        redirect_uris=json.dumps(redirect_uris),
        scopes=json.dumps(scopes),
        owner_id=owner_id,
    )
    db.add(app)
    db.commit()
    db.refresh(app)
    return app


def update_app(db: Session, app: OAuthApp, updates: dict) -> OAuthApp:
    for field, value in updates.items():
        if field in ("redirect_uris", "scopes"):
            setattr(app, field, json.dumps(value))
        else:
            setattr(app, field, value)
    db.commit()
    db.refresh(app)
    return app


def delete_app(db: Session, app: OAuthApp) -> None:
    db.delete(app)
    db.commit()


def rotate_app_secret(db: Session, app: OAuthApp, new_secret_hash: str) -> OAuthApp:
    app.client_secret_hash = new_secret_hash
    db.commit()
    return app


# ── Token mutations ─────────────────────────────────────────────────────────────

def create_token(
    db: Session,
    *,
    app_id: str,
    user_id: str,
    token_hash: str,
    scopes: list[str],
    expires_at: datetime,
) -> OAuthToken:
    token = OAuthToken(
        id=str(uuid.uuid4()),
        app_id=app_id,
        user_id=user_id,
        access_token_hash=token_hash,
        scopes=json.dumps(scopes),
        expires_at=expires_at,
    )
    db.add(token)
    db.commit()
    return token


def get_token_by_hash(db: Session, token_hash: str) -> OAuthToken | None:
    return db.query(OAuthToken).filter(OAuthToken.access_token_hash == token_hash).first()


def get_active_token_by_hash(db: Session, token_hash: str) -> OAuthToken | None:
    return db.query(OAuthToken).filter(
        OAuthToken.access_token_hash == token_hash,
        OAuthToken.revoked == False,
    ).first()


def revoke_token(db: Session, token: OAuthToken) -> None:
    token.revoked = True
    db.commit()


# ── User query ──────────────────────────────────────────────────────────────────

def get_user_by_id(db: Session, user_id: str) -> User | None:
    return db.query(User).filter(User.id == user_id).first()

# ── Crypto helpers (PBKDF2-HMAC-SHA256) ───────────────────────────────────

import hashlib as _hashlib
import hmac as _hmac
import os as _os
import json as _json

_PBKDF2_ITERATIONS = 260_000
_MAX_APPS_PER_USER = 10


def hash_secret(secret: str) -> str:
    """PBKDF2-HMAC-SHA256 with a random salt — returns '<salt_hex>:<dk_hex>'."""
    salt = _os.urandom(16)
    dk = _hashlib.pbkdf2_hmac("sha256", secret.encode(), salt, _PBKDF2_ITERATIONS)
    return salt.hex() + ":" + dk.hex()


def verify_secret(secret: str, hashed: str) -> bool:
    """Constant-time comparison to prevent timing-attack leakage."""
    try:
        salt_hex, dk_hex = hashed.split(":", 1)
        salt = bytes.fromhex(salt_hex)
        dk = bytes.fromhex(dk_hex)
    except (ValueError, AttributeError):
        return False
    candidate = _hashlib.pbkdf2_hmac("sha256", secret.encode(), salt, _PBKDF2_ITERATIONS)
    return _hmac.compare_digest(candidate, dk)


def serialize_app(app, include_secret: str = None) -> dict:
    out = {
        "id": app.id,
        "name": app.name,
        "description": app.description,
        "homepage_url": app.homepage_url,
        "client_id": app.client_id,
        "redirect_uris": _json.loads(app.redirect_uris or "[]"),
        "scopes": _json.loads(app.scopes or '["read"]'),
        "is_active": app.is_active,
        "is_first_party": app.is_first_party,
        "owner_id": app.owner_id,
        "created_at": app.created_at.isoformat() if app.created_at else None,
    }
    if include_secret:
        out["client_secret"] = include_secret
    return out