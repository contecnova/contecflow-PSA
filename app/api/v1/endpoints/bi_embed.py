"""
BI Embedded Analytics SDK — endpoints
========================================
Iframes seguros, JS SDK configuration, SSO token exchange.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.models.user import User
from app.services import bi_embed_service as svc

router = APIRouter(prefix="/bi/embed", tags=["BI Embedded SDK"])


# ── Token generation ──────────────────────────────────────────────────────────

@router.post("/token", summary="Generar embed token JWT para iframe seguro")
def create_embed_token(
    payload: dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Genera un JWT firmado para incrustar un dashboard en un iframe externo.

    Body JSON:
        dashboard_id  (str, required)
        permissions   (list[str], default ["read"])
        ttl_minutes   (int, default 60)
        user_id       (str, optional — si se omite se usa current_user.id)
    """
    org_id = str(current_user.organization_id or "global")
    user_id = payload.get("user_id") or str(current_user.id)
    dashboard_id = payload.get("dashboard_id", "default")
    permissions = payload.get("permissions", ["read"])
    ttl = int(payload.get("ttl_minutes", 60))
    return svc.create_embed_token(db, org_id, user_id, dashboard_id, permissions, ttl)


@router.delete("/token/{jti}", summary="Revocar embed token")
def revoke_embed_token(
    jti: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    org_id = str(current_user.organization_id or "global")
    svc.revoke_embed_token(db, org_id, jti)
    return {"revoked": True, "jti": jti}


# ── SSO exchange ──────────────────────────────────────────────────────────────

@router.post("/sso", summary="Intercambiar token SSO externo por embed token")
def sso_exchange(
    payload: dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Intercambia un token JWT de un proveedor SSO externo por un embed token.

    Body JSON:
        external_token  (str, required)
        dashboard_id    (str, required)
        ttl_minutes     (int, default 60)
    """
    org_id = str(current_user.organization_id or "global")
    return svc.sso_exchange_token(
        db,
        org_id,
        payload["external_token"],
        payload.get("dashboard_id", "default"),
        int(payload.get("ttl_minutes", 60)),
    )


# ── JS SDK config ─────────────────────────────────────────────────────────────

@router.get("/sdk-config", summary="Obtener configuración del JS SDK (validación de token)")
def get_sdk_config(
    dashboard_id: str = Query("default"),
    token: str = Query(...),
    org_id: str = Query(...),
    db: Session = Depends(get_db),
):
    """Endpoint público que valida el embed token y retorna la config JS SDK.
    No requiere autenticación Contecflow — el token embed actúa como credencial.
    """
    return svc.get_sdk_config(db, org_id, dashboard_id, token)


# ── Embed configuration (admin) ───────────────────────────────────────────────

@router.get("/config", summary="Obtener configuración embed (CSP, origins)")
def get_embed_config(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    org_id = str(current_user.organization_id or "global")
    return svc.get_embed_config(db, org_id)


@router.put("/config", summary="Actualizar configuración embed")
def save_embed_config(
    payload: dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    org_id = str(current_user.organization_id or "global")
    result = svc.save_embed_config(db, org_id, payload)
    db.commit()
    return result
