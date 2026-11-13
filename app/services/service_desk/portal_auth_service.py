"""Resolver al cliente del portal a partir de su token.

Auditoria 2026-11 (item 36): las dependencias FastAPI que leen cabecera y
cookie (`get_current_portal_client`, `get_portal_client_or_user`) estan en
`app/core/deps.py`; aqui queda la logica, sin objetos HTTP.
"""
from typing import Optional

from sqlalchemy.orm import Session

from app.services.sla_service import get_client_from_token
import logging
from app.core.errores import ErrorDeDominio

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
        raise ErrorDeDominio(401, detail)
    return client


class Lector:
    """Quien lee algo del Service Desk que tambien ve el portal: un usuario o un cliente."""

    def __init__(self, usuario=None, cliente=None):
        self.usuario, self.cliente = usuario, cliente

    @property
    def solo_publico(self) -> bool:
        return self.cliente is not None
