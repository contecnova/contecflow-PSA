from typing import Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.services.sla_service import get_client_from_token


def resolve_portal_client(
    authorization: Optional[str],
    portal_access_token: Optional[str],
    db: Session,
):
    token_value = authorization
    if not token_value and portal_access_token:
        token_value = f"Bearer {portal_access_token}"
    return get_client_from_token(token_value, db)


def require_portal_client(
    authorization: Optional[str],
    portal_access_token: Optional[str],
    db: Session,
    detail: str = "Autenticacion requerida",
):
    client = resolve_portal_client(authorization, portal_access_token, db)
    if not client:
        raise HTTPException(401, detail)
    return client
