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
