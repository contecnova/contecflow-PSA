from fastapi import APIRouter, status, Depends, Body, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_current_org_id, get_db, require_admin
from app.core.abac_enforce import enforce_abac
from app.core.responses import APIResponse, APIListResponse
from app.services import marketplace_service

router = APIRouter()


@router.get("/marketplace", status_code=status.HTTP_200_OK)
def list_marketplace(
    category: str = None,
    certified_only: bool = False,
    org_id: str = Depends(get_current_org_id),
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    return APIListResponse.ok(items=marketplace_service.list_marketplace_connectors(
        category=category,
        certified_only=certified_only,
        organization_id=org_id,
        db=db,
    ))


@router.post("/instances", status_code=status.HTTP_201_CREATED)
def install_connector(
    payload: dict = Body(...),
    org_id: str = Depends(get_current_org_id),
    db: Session = Depends(get_db),
    user=Depends(require_admin),
):
    slug = payload.get("connector_slug")
    if not slug:
        raise HTTPException(status_code=400, detail="connector_slug is required")

    return APIResponse.ok(data=marketplace_service.install_integration_connector(
        connector_slug=slug,
        name=payload.get("name") or slug,
        config=payload.get("config") or {},
        sync_direction=payload.get("sync_direction", "bidirectional"),
        sync_frequency=payload.get("sync_frequency", "hourly"),
        organization_id=org_id,
        user_id=str(user.id),
        db=db,
    ))


@router.get("/instances", status_code=status.HTTP_200_OK)
def list_instances(
    org_id: str = Depends(get_current_org_id),
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    return APIListResponse.ok(items=marketplace_service.list_integration_instances(organization_id=org_id, db=db))


@router.delete("/instances/{instance_id}", status_code=status.HTTP_200_OK)
def uninstall_integration(
    instance_id: str,
    org_id: str = Depends(get_current_org_id),
    db: Session = Depends(get_db),
    user=Depends(require_admin),
):
    enforce_abac(db, user, "integration_instance", instance_id, action="delete")
    marketplace_service.uninstall_integration_connector(
        instance_id=instance_id, organization_id=org_id, db=db
    )
    return APIResponse.ok(data={"ok": True, "message": "Instancia de integración eliminada correctamente"})
