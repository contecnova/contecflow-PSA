from fastapi import APIRouter, status, Depends, Body
from app.api.deps import get_current_user

router = APIRouter()

@router.get("", summary="Branding config")
def get_branding(user=Depends(get_current_user)):
    return {"app_name": "NexusPM", "primary_color": "#6366f1"}


# Exponer también el endpoint en la raíz para legacy
@router.put("/orgs/{org_id}/branding", status_code=status.HTTP_200_OK)
@router.put("/{org_id}/branding", status_code=status.HTTP_200_OK)

# Endpoint para /branding/orgs/{org_id}/branding
@router.put("/orgs/{org_id}/branding", status_code=status.HTTP_200_OK)
def update_org_branding(org_id: int, payload: dict = Body(...), user=Depends(get_current_user)):
    # Stub: echo back the payload as the updated branding config
    return payload

# Endpoint explícito para /orgs/{org_id}/branding (legacy/compatibilidad test)
from fastapi import APIRouter as _APIRouter
legacy_router = _APIRouter()

@legacy_router.put("/{org_id}/branding", status_code=status.HTTP_200_OK)
def legacy_update_org_branding(org_id: int, payload: dict = Body(...), user=Depends(get_current_user)):
    return payload
