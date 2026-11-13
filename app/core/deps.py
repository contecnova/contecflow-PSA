from fastapi import Cookie, Depends, Header, HTTPException, Request, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from typing import Optional

from app.db.session import get_db
from app.core.security import decode_token
from app.models.user import User, UserRole

security = HTTPBearer(auto_error=False)


TOKENS_DE_USO_CONCRETO = ("bi_embed", "bi_intelligence_stream", "ws", "document_file_access")


def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db),
) -> User:
    # Accept token from Authorization header or httpOnly cookie
    token = None
    if credentials:
        token = credentials.credentials
    else:
        token = request.cookies.get("access_token")

    # Auditoria 2026-11: clave de API o token del portal de desarrolladores.
    from app.core import credenciales_delegadas as _delegadas
    delegada = _delegadas.resolver(db, request, credentials.credentials if credentials else None)
    if delegada is not None:
        return _usuario_de_credencial_delegada(db, request, *delegada)

    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="No autenticado",
            headers={"WWW-Authenticate": "Bearer"},
        )
    payload = decode_token(token)

    if not payload or payload.get("type") != "access":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token inválido o expirado",
            headers={"WWW-Authenticate": "Bearer"},
        )
    # Auditoria 2026-11: los tokens de uso concreto (incrustar un panel BI, el
    # flujo en tiempo real, el WebSocket) eran tokens de acceso completos: con
    # uno se llamaba a toda la API. Cada uno lo valida su propio receptor.
    if any(payload.get(c) for c in TOKENS_DE_USO_CONCRETO):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Este token solo vale para su uso concreto",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user_id = payload.get("sub")
    user = db.query(User).filter(User.id == user_id, User.is_active == True).first()
    # «Entrar como»: corta las rutas de credenciales y deja constancia en la peticion.
    from app.services.entrada_service import comprobar_suplantacion
    suplantador = comprobar_suplantacion(payload, request)
    if suplantador:
        # Revision multitenant 2026-11b: lo que se hace «entrando como» queda en
        # la auditoria con quien lo hizo de verdad (ver `audit.audit_log`).
        db.info["suplantado_por"] = suplantador

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Usuario no encontrado o inactivo",
        )

    # Store tenant context in the session so query scoping can enforce row-level isolation.
    # is_superadmin=True  → bypass all tenant filters (full cross-tenant visibility)
    # is_superadmin=False → enforce tenant filter; if org_id is also None the user has
    #                       no assigned organisation and must see zero rows (not all rows).
    if getattr(user, "is_superadmin", False):
        db.info["organization_id"] = None
        db.info["is_superadmin"] = True
    else:
        # La empresa activa es la del token (claim `org`), validada: pertenencia
        # vigente y, en modo subdominio, la del host. Tokens antiguos sin claim:
        # la de la ficha del usuario. Ver app/services/entrada_service.py.
        from app.services.entrada_service import organizacion_de_la_peticion
        db.info["organization_id"] = organizacion_de_la_peticion(db, user, payload, request)
        db.info["is_superadmin"] = False
        from app.db.session import exigir_organizacion_activa
        exigir_organizacion_activa(db, db.info["organization_id"])

    # Make the authenticated user available to the service layer so events
    # can be emitted without passing actor as an explicit parameter.
    db.info["current_user"] = user

    # Auditoria 2026-11: el acceso por modulo del rol y los permisos por
    # proyecto se aplican.
    from app.core import modulos as _modulos, permisos_de_proyecto as _permisos
    _modulos.comprobar(db, user, request)
    _permisos.comprobar(db, user, request)

    return user


def _usuario_de_credencial_delegada(db: Session, request: Request, user_id: str, alcances: list, tipo: str,
                                    empresa: Optional[str] = None) -> User:
    from app.core import credenciales_delegadas as _delegadas
    user = db.query(User).filter(User.id == user_id, User.is_active == True).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                            detail="El dueño de la credencial no existe o está inactivo")
    _delegadas.comprobar_alcance(request.method, request.url.path, alcances)
    db.commit()  # contadores de uso de la clave
    if getattr(user, "is_superadmin", False):
        db.info["organization_id"] = None
        db.info["is_superadmin"] = True
    else:
        # Revision multitenant 2026-11b: la credencial trabaja en la empresa en
        # la que se creo, no en la de la ficha de su dueño (con pertenencias en
        # varias, una clave creada en B leia y escribia A). Si el dueño ya no
        # pertenece a ella, la credencial no vale.
        from app.services.entrada_service import organizacion_de_la_peticion, pertenece
        if empresa and empresa != user.organization_id and not pertenece(db, user, empresa):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                                detail="El dueño de la credencial ya no pertenece a su organización")
        db.info["organization_id"] = organizacion_de_la_peticion(
            db, user, {"org": empresa} if empresa else {}, request)
        db.info["is_superadmin"] = False
        from app.db.session import exigir_organizacion_activa
        exigir_organizacion_activa(db, db.info["organization_id"])
    db.info["current_user"] = user
    request.state.credencial_delegada = {"tipo": tipo, "alcances": alcances}
    from app.core import modulos as _modulos, permisos_de_proyecto as _permisos
    _modulos.comprobar(db, user, request)
    _permisos.comprobar(db, user, request)
    return user


def get_current_active_user(current_user: User = Depends(get_current_user)) -> User:
    # is_active is already checked inside get_current_user at the DB query level
    return current_user


class RequireRole:
    """Dependency factory for role-based access control."""

    def __init__(self, *roles: UserRole):
        self.roles = roles

    def __call__(self, current_user: User = Depends(get_current_user)) -> User:
        if current_user.is_superadmin:
            return current_user
        if current_user.role not in self.roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Acceso denegado. Roles requeridos: {[r.value for r in self.roles]}",
            )
        return current_user


def require_superadmin(current_user: User = Depends(get_current_user)) -> User:
    """Cross-tenant guard: only the platform superadmin passes.

    `require_admin` is NOT this: `UserRole.admin` is the *tenant* administrator
    role, so it grants nothing across organisations. Any endpoint that operates
    on the Organization model — the only mapped model without a tenant column,
    and therefore the only one TenantSession cannot scope — must use this
    dependency instead. See app/db/session.py::TenantSession.
    """
    if not getattr(current_user, "is_superadmin", False):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Acceso denegado. Requiere superadministrador de plataforma.",
        )
    return current_user


# Shortcut dependencies
require_admin = RequireRole(UserRole.admin)
require_admin_or_hr = RequireRole(UserRole.admin, UserRole.hr)
require_admin_or_pm = RequireRole(UserRole.admin, UserRole.pm)
require_any_manager = RequireRole(UserRole.admin, UserRole.pm, UserRole.team_lead, UserRole.hr)
# All internal employees — excludes subcontractor from accessing organisation-wide data
require_internal_user = RequireRole(
    UserRole.admin, UserRole.pm, UserRole.team_lead, UserRole.hr, UserRole.employee
)


def get_current_org_id(current_user: User = Depends(get_current_user)) -> Optional[str]:
    """Row-level tenant dependency.

    Returns the organisation ID of the current user so endpoints can
    filter queries to the user's tenant.  Superadmins return ``None``
    which signals 'no restriction' (they can see everything).
    """
    if current_user.is_superadmin:
        return None
    return current_user.organization_id

def get_current_client(
    request: Request,
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db),
):
    """Authenticate a client portal user via JWT (header or cookie)."""
    token = None
    if credentials:
        token = credentials.credentials
    else:
        token = request.cookies.get("portal_access_token")

    if not token:
        raise HTTPException(status_code=401, detail="Token de cliente requerido")
    from app.core.security import verify_client_token
    client = verify_client_token(token, db)
    if not client:
        raise HTTPException(status_code=401, detail="Token de cliente inválido")
    # Revision 2026-11: no publicaba el tenant, y `TenantSession` sin contexto
    # no filtra (las rutas de colaboracion y conversaciones del portal).
    from app.db.session import publicar_contexto_de_tenant
    publicar_contexto_de_tenant(db, client, es_cliente=True)
    return client


# ── Portal de cliente ────────────────────────────────────────────────────────
# Auditoria 2026-11 (item 36): estas dos dependencias vivian en
# `app/services/service_desk/portal_auth_service.py`, que importaba
# `Depends`/`Header`/`Cookie`/`Request`. Leer cabeceras y cookies es HTTP: vive
# aqui. La logica (resolver el token, `Lector`) sigue en el servicio.

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

    Auditoria 2026-11: publica la organizacion del cliente en la sesion, como
    `get_portal_client_or_user`. Sin esto lo que creaba el portal (tickets)
    quedaba sin organizacion.
    """
    from app.db.session import publicar_contexto_de_tenant
    from app.services.service_desk.portal_auth_service import require_portal_client
    cliente = require_portal_client(authorization, portal_access_token, db)
    publicar_contexto_de_tenant(db, cliente, es_cliente=True)
    return cliente


def get_portal_client_or_user(
    request: Request,
    db: Session = Depends(get_db),
    authorization: Optional[str] = Header(None),
    portal_access_token: Optional[str] = Cookie(None),
):
    """Un cliente del portal (con su organizacion publicada) o un usuario. Si no, 401.

    Auditoria 2026-11 (medido con un cliente sin cookies): el catalogo y la base
    de conocimiento se servian sin login, y sin sesion no hay filtro de
    organizacion: cualquiera leia el contenido interno de todas. Un visitante
    anonimo no se puede acotar a ninguna organizacion, asi que no lee.
    """
    from app.db.session import publicar_contexto_de_tenant
    from app.services.service_desk.portal_auth_service import Lector, resolve_portal_client

    cliente = resolve_portal_client(authorization, portal_access_token, db)
    if cliente is not None:
        publicar_contexto_de_tenant(db, cliente, es_cliente=True)
        return Lector(cliente=cliente)
    credenciales = None
    if authorization and authorization.lower().startswith("bearer "):
        credenciales = HTTPAuthorizationCredentials(scheme="Bearer", credentials=authorization.split(" ", 1)[1].strip())
    return Lector(usuario=get_current_user(request, credenciales, db))
