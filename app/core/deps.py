from fastapi import Depends, HTTPException, Request, status
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
        db.info["organization_id"] = getattr(user, "organization_id", None)
        db.info["is_superadmin"] = False

    # Make the authenticated user available to the service layer so events
    # can be emitted without passing actor as an explicit parameter.
    db.info["current_user"] = user

    # Auditoria 2026-11: el acceso por modulo del rol y los permisos por
    # proyecto se aplican.
    from app.core import modulos as _modulos, permisos_de_proyecto as _permisos
    _modulos.comprobar(db, user, request)
    _permisos.comprobar(db, user, request)

    return user


def _usuario_de_credencial_delegada(db: Session, request: Request, user_id: str, alcances: list, tipo: str) -> User:
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
        db.info["organization_id"] = getattr(user, "organization_id", None)
        db.info["is_superadmin"] = False
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
    return client
