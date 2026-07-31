"""Service Desk curated connectors marketplace (MVP)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, require_any_manager
from app.core.responses import APIListResponse, APIResponse
from app.db.session import get_db
from app.models.marketplace import IntegrationConnector, IntegrationInstance
from app.models.user import User

router = APIRouter()


class ConnectorInstallIn(BaseModel):
    connector_id: str
    name: str = Field(..., min_length=1, max_length=100)
    sync_direction: str = "bidirectional"
    sync_frequency: str = "hourly"


@router.get("/connectors/marketplace", summary="Marketplace curado de conectores Service Desk")
def list_connectors(
    category: str | None = Query(None),
    certified_only: bool = Query(False),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    q = db.query(IntegrationConnector).filter(IntegrationConnector.is_active == True)
    if category:
        q = q.filter(IntegrationConnector.category == category)
    if certified_only:
        q = q.filter(IntegrationConnector.is_certified == True)

    curated_priority = ["jira", "servicenow", "zendesk", "slack", "teams", "pagerduty"]
    rows = q.all()
    rows.sort(key=lambda c: (curated_priority.index(c.slug) if c.slug in curated_priority else 999, c.name.lower()))

    return APIListResponse.ok(items=[
        {
            "id": c.id,
            "name": c.name,
            "slug": c.slug,
            "category": c.category,
            "description": c.description,
            "docs_url": c.docs_url,
            "auth_scheme": c.auth_scheme,
            "is_certified": c.is_certified,
        }
        for c in rows
    ])


@router.get("/connectors/installed", summary="Conectores instalados para la organización")
def list_installed_connectors(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    org_id = getattr(current_user, "organization_id", None)
    if not org_id:
        return APIListResponse.ok(items=[])

    rows = (
        db.query(IntegrationInstance, IntegrationConnector)
        .join(IntegrationConnector, IntegrationConnector.id == IntegrationInstance.connector_id)
        .filter(IntegrationInstance.organization_id == org_id)
        .all()
    )

    return APIListResponse.ok(items=[
        {
            "id": inst.id,
            "name": inst.name,
            "connector": {
                "id": conn.id,
                "name": conn.name,
                "slug": conn.slug,
                "category": conn.category,
            },
            "sync_direction": inst.sync_direction,
            "sync_frequency": inst.sync_frequency,
            "is_enabled": inst.is_enabled,
            "last_sync_at": inst.last_sync_at,
            "last_sync_status": inst.last_sync_status,
        }
        for inst, conn in rows
    ])


@router.post("/connectors/install", summary="Instalar conector desde marketplace")
def install_connector(
    payload: ConnectorInstallIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    org_id = getattr(current_user, "organization_id", None)
    if not org_id:
        raise HTTPException(400, "organization_id no disponible")

    connector = db.query(IntegrationConnector).filter(
        IntegrationConnector.id == payload.connector_id,
        IntegrationConnector.is_active == True,
    ).first()
    if not connector:
        raise HTTPException(404, "Connector not found")

    inst = IntegrationInstance(
        organization_id=org_id,
        connector_id=connector.id,
        name=payload.name,
        sync_direction=payload.sync_direction,
        sync_frequency=payload.sync_frequency,
        is_enabled=True,
        created_by=current_user.id,
    )
    db.add(inst)
    db.commit()
    db.refresh(inst)

    return APIResponse.ok(data={"ok": True, "instance_id": inst.id})
