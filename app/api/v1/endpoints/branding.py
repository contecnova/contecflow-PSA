from fastapi import APIRouter, status, Depends, Body
from app.api.deps import get_current_user

router = APIRouter()


@router.get("", summary="Get branding config")
def get_branding(user=Depends(get_current_user)):
    return {"app_name": "NexusPM", "primary_color": "#6366f1"}


@router.put("/{org_id}", status_code=status.HTTP_200_OK, summary="Update branding config")
def update_branding(
    org_id: int,
    payload: dict = Body(...),
    user=Depends(get_current_user),
):
    return payload
