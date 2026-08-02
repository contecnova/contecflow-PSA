from typing import Optional

from fastapi import Cookie, Depends, Header, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.services.sla_service import get_client_from_token
import logging

logger = logging.getLogger(__name__)


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


def get_current_portal_client(
    authorization: Optional[str] = Header(None),
    portal_access_token: Optional[str] = Cookie(None),
    db: Session = Depends(get_db),
):
    """Dependencia FastAPI para el cliente autenticado del portal.

    Usar SIEMPRE esta dependencia en lugar de llamar a `require_portal_client`
    dentro del handler. Motivos:

    - La authz queda en el grafo de dependencias, así que es auditable por
      herramientas (ver tests/test_route_auth_coverage.py) y aparece en OpenAPI.
    - Es imposible olvidar la llamada o descartar su valor de retorno, que es
      exactamente el fallo que provocó los IDOR de CSAT y comentarios de portal
      (auditoría 2026-07, docs/AUDIT_2026_07_FULL.md §1.1 y §1.2).
    """
    return require_portal_client(authorization, portal_access_token, db)
