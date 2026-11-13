"""
Developer Portal — OAuth2 Application management.

Endpoints (authenticated):
  GET    /developer/apps            — list own apps
  POST   /developer/apps            — register new app
  GET    /developer/apps/{id}       — get app detail (includes client_id)
  PATCH  /developer/apps/{id}       — update app metadata
  DELETE /developer/apps/{id}       — delete app + all tokens
  POST   /developer/apps/{id}/rotate-secret — generate new client secret

OAuth2 flow (can be called by third-party apps):
  GET    /developer/authorize       — show consent screen info (returns app info)
  POST   /developer/token           — exchange code/credentials for access token
  POST   /developer/token/revoke    — revoke a token
  GET    /developer/userinfo        — return current user profile (token auth)
"""
import json
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, get_db, require_admin_or_pm
from app.core.abac_enforce import enforce_abac
from app.models.user import User, UserRole
from app.services import developer_portal_service as svc
from app.core.responses import APIListResponse, APIResponse
from app.core.credenciales_delegadas import ALCANCES_VALIDOS, huella, ttl_de_token

router = APIRouter(prefix="/developer", tags=["Developer Portal"])

# ── Pydantic schemas ────────────────────────────────────────────────────────────

class AppCreateIn(BaseModel):
    name: str
    description: Optional[str] = None
    homepage_url: Optional[str] = None
    redirect_uris: list[str] = []
    scopes: list[str] = ["read"]


class AppUpdateIn(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    homepage_url: Optional[str] = None
    redirect_uris: Optional[list[str]] = None
    scopes: Optional[list[str]] = None
    is_active: Optional[bool] = None


class TokenRequestIn(BaseModel):
    grant_type: str               # "client_credentials" | "authorization_code"
    client_id: str
    client_secret: str
    scope: Optional[str] = "read"
    redirect_uri: Optional[str] = None
    code: Optional[str] = None    # for authorization_code flow


# ── Helpers ─────────────────────────────────────────────────────────────────────

_PBKDF2_ITERATIONS = 260_000
_MAX_APPS_PER_USER = 10


_hash_secret = svc.hash_secret
_verify_secret = svc.verify_secret
_app_out = svc.serialize_app


def _alcances_validos(scopes) -> None:
    invalidos = sorted(set(scopes or []) - set(ALCANCES_VALIDOS))
    if invalidos:
        raise HTTPException(422, f"Alcances no válidos: {', '.join(invalidos)}. Válidos: {', '.join(ALCANCES_VALIDOS)}")


# ── App management endpoints ────────────────────────────────────────────────────

@router.get("/apps", summary="Listar mis aplicaciones OAuth")
def list_apps(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    apps = svc.list_apps_for_user(db, current_user.id)
    items = [_app_out(a) for a in apps]
    return APIListResponse.ok(items=items, total=len(items))


@router.post("/apps", summary="Registrar nueva aplicación OAuth", status_code=201)
def create_app(
    payload: AppCreateIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _rol: User = Depends(require_admin_or_pm),  # auditoria 2026-09: excepcion revisada: credenciales OAuth, pero la audiencia prevista es PM segun test_developer_portal
):
    app_count = svc.count_apps_for_user(db, current_user.id)
    if app_count >= _MAX_APPS_PER_USER:
        raise HTTPException(400, f"Límite máximo de {_MAX_APPS_PER_USER} aplicaciones por usuario alcanzado")

    _alcances_validos(payload.scopes)
    raw_secret = secrets.token_urlsafe(32)
    app = svc.create_app(
        db,
        name=payload.name,
        description=payload.description,
        homepage_url=payload.homepage_url,
        redirect_uris=payload.redirect_uris,
        scopes=payload.scopes,
        owner_id=current_user.id,
        secret_hash=_hash_secret(raw_secret),
    )
    return APIResponse.ok(data=_app_out(app, include_secret=raw_secret))


@router.get("/apps/{app_id}", summary="Detalle de aplicación")
def get_app(app_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    app = svc.get_app_by_id(db, app_id)
    if not app:
        raise HTTPException(404, "Aplicación no encontrada")
    if app.owner_id != current_user.id and current_user.role != UserRole.admin:
        raise HTTPException(403, "Acceso denegado")
    return APIResponse.ok(data=_app_out(app))


@router.patch("/apps/{app_id}", summary="Actualizar aplicación")
def update_app(
    app_id: str,
    payload: AppUpdateIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _rol: User = Depends(require_admin_or_pm),  # auditoria 2026-09: excepcion revisada: la aplicacion es de quien la creo; misma audiencia que crearla
):
    app = svc.get_app_by_id(db, app_id)
    if not app:
        raise HTTPException(404, "Aplicación no encontrada")
    if app.owner_id != current_user.id and current_user.role != UserRole.admin:
        raise HTTPException(403, "Acceso denegado")
    _alcances_validos(payload.scopes)
    app = svc.update_app(db, app, payload.model_dump(exclude_none=True))
    return APIResponse.ok(data=_app_out(app))


@router.delete("/apps/{app_id}", summary="Eliminar aplicación")
def delete_app(app_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user),
    _rol: User = Depends(require_admin_or_pm),  # auditoria 2026-09: excepcion revisada: la aplicacion es de quien la creo; misma audiencia que crearla
):
    app = svc.get_app_by_id(db, app_id)
    if not app:
        raise HTTPException(404, "Aplicación no encontrada")
    if app.owner_id != current_user.id and current_user.role != UserRole.admin:
        raise HTTPException(403, "Acceso denegado")
    enforce_abac(db, current_user, "oauth_app", app_id, action="delete")
    svc.delete_app(db, app)
    return APIResponse.ok(data={"ok": True, "message": "Aplicación eliminada correctamente"})


@router.post("/apps/{app_id}/rotate-secret", summary="Rotar secreto de cliente")
def rotate_secret(app_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user),
    _rol: User = Depends(require_admin_or_pm),  # auditoria 2026-09: excepcion revisada: rotar el secreto de la propia aplicacion
):
    app = svc.get_app_by_id(db, app_id)
    if not app:
        raise HTTPException(404, "Aplicación no encontrada")
    if app.owner_id != current_user.id and current_user.role != UserRole.admin:
        raise HTTPException(403, "Acceso denegado")
    raw_secret = secrets.token_urlsafe(32)
    svc.rotate_app_secret(db, app, _hash_secret(raw_secret))
    # Revisión GRC 2026-11b: rotar el secreto de cliente OAuth no dejaba rastro.
    from app.services.audit import audit_log
    audit_log(db, current_user, "SECRET_ROTATED", "oauth_app", app.id, app.client_id)
    db.commit()
    return APIResponse.ok(data={"client_id": app.client_id, "client_secret": raw_secret})


# ── OAuth2 token endpoint ───────────────────────────────────────────────────────

@router.post("/token", summary="Obtener token de acceso OAuth2")
def oauth_token(
    payload: TokenRequestIn,
    db: Session = Depends(get_db),
):
    app = svc.get_app_by_client_id(db, payload.client_id)
    if not app or not _verify_secret(payload.client_secret, app.client_secret_hash):
        raise HTTPException(401, "client_id o client_secret inválido")

    if payload.grant_type == "client_credentials":
        # Validate requested scopes against the app's registered scopes
        allowed_scopes = set(json.loads(app.scopes or '["read"]'))
        requested_scopes = set(payload.scope.split() if payload.scope else ["read"])
        invalid_scopes = requested_scopes - allowed_scopes
        if invalid_scopes:
            raise HTTPException(400, f"Scopes no permitidos: {', '.join(sorted(invalid_scopes))}")

        # Issue token on behalf of the app owner
        owner_id = app.owner_id
        if not owner_id:
            raise HTTPException(400, "Esta app no tiene propietario configurado")

        raw_token = secrets.token_urlsafe(32)
        vida = ttl_de_token(db)
        expires_at = datetime.now(timezone.utc) + vida
        scopes_list = payload.scope.split() if payload.scope else ["read"]
        # Auditoria 2026-11: antes PBKDF2 con sal aleatoria, que luego se
        # buscaba por igualdad y no coincidia nunca. La huella SHA-256 si.
        svc.create_token(
            db,
            app_id=app.id,
            user_id=owner_id,
            token_hash=huella(raw_token),
            scopes=scopes_list,
            expires_at=expires_at,
        )

        return {
            "access_token": raw_token,
            "token_type": "bearer",
            "expires_in": int(vida.total_seconds()),
            "scope": payload.scope or "read",
        }

    raise HTTPException(400, f"grant_type '{payload.grant_type}' no soportado")


@router.post("/token/revoke", summary="Revocar token OAuth2")
def revoke_token(
    request: Request,
    db: Session = Depends(get_db),
):
    """Revoke a token by its raw value (provided in Authorization: Bearer header)."""
    auth = request.headers.get("authorization", "")
    if not auth.startswith("Bearer "):
        raise HTTPException(401, "Token requerido en cabecera Authorization: Bearer <token>")
    raw_token = auth.removeprefix("Bearer ").strip()
    token = svc.get_token_by_hash(db, huella(raw_token))
    if token:
        svc.revoke_token(db, token)
    return {"ok": True}


@router.get("/userinfo", summary="Información del usuario autenticado vía OAuth2")
def oauth_userinfo(
    request: Request,
    db: Session = Depends(get_db),
):
    """Returns basic profile for the user whose OAuth token is presented."""
    auth = request.headers.get("authorization", "")
    if not auth.startswith("Bearer "):
        raise HTTPException(401, "Token requerido")
    raw_token = auth.removeprefix("Bearer ").strip()
    token_obj = svc.get_active_token_by_hash(db, huella(raw_token))
    if not token_obj:
        raise HTTPException(401, "Token inválido o revocado")
    vence = token_obj.expires_at
    if vence and (vence if vence.tzinfo else vence.replace(tzinfo=timezone.utc)) < datetime.now(timezone.utc):
        raise HTTPException(401, "Token expirado")

    user = svc.get_user_by_id(db, token_obj.user_id)
    if not user:
        raise HTTPException(404, "Usuario no encontrado")

    return {
        "sub": user.id,
        "name": user.full_name or f"{user.first_name or ''} {user.last_name or ''}".strip(),
        "email": user.email,
        "role": user.role.value if hasattr(user.role, 'value') else user.role,
        "organization_id": user.organization_id,
    }
