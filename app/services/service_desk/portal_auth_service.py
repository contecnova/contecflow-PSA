from typing import Optional

from fastapi import Cookie, Depends, Header, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials
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


class Lector:
    """Quien lee algo del Service Desk que tambien ve el portal: un usuario o un cliente."""

    def __init__(self, usuario=None, cliente=None):
        self.usuario, self.cliente = usuario, cliente

    @property
    def solo_publico(self) -> bool:
        return self.cliente is not None


def get_portal_client_or_user(
    request: Request,
    db: Session = Depends(get_db),
    authorization: Optional[str] = Header(None),
    portal_access_token: Optional[str] = Cookie(None),
) -> Lector:
    """Un cliente del portal (con su organizacion publicada) o un usuario. Si no, 401.

    Auditoria 2026-11 (medido con un cliente sin cookies): el catalogo y la base
    de conocimiento se servian sin login, y sin sesion no hay filtro de
    organizacion: cualquiera leia el contenido interno de todas. Un visitante
    anonimo no se puede acotar a ninguna organizacion, asi que no lee.
    """
    from app.core.deps import get_current_user
    from app.db.session import publicar_contexto_de_tenant

    cliente = resolve_portal_client(authorization, portal_access_token, db)
    if cliente is not None:
        publicar_contexto_de_tenant(db, cliente, es_cliente=True)
        return Lector(cliente=cliente)
    credenciales = None
    if authorization and authorization.lower().startswith("bearer "):
        credenciales = HTTPAuthorizationCredentials(scheme="Bearer", credentials=authorization.split(" ", 1)[1].strip())
    return Lector(usuario=get_current_user(request, credenciales, db))
