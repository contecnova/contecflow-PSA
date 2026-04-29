"""
cmdb_3d.py — CMDB 3D dependency map and Asset-CMDB impact endpoints.

Routes:
  GET  /sd/cmdb/3d-graph                        — 3D graph data for visualization
  GET  /sd/cmdb/blast-radius/{ci_id}            — blast radius for a CI
  POST /sd/cmdb/asset-links                     — link asset to CI
  GET  /sd/cmdb/asset-links                     — list all asset-CI links
  GET  /sd/cmdb/asset-impact/{asset_id}         — impact of asset via linked CIs
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.core.ratelimit import limiter
from app.db.session import get_db
from app.models.user import User
from app.services.service_desk.cmdb_3d_service import (
    get_3d_graph,
    calculate_blast_radius,
    link_asset_to_ci,
    get_asset_impact,
    list_asset_links,
)

router = APIRouter(prefix="/sd", tags=["Service Desk - CMDB 3D"])


class AssetLinkIn(BaseModel):
    asset_id: str
    ci_id: str
    link_type: str = Field("physical_to_logical", description="physical_to_logical | logical_to_logical | virtual")
    notes: Optional[str] = None


@router.get("/cmdb/3d-graph", summary="Datos del grafo 3D de dependencias CMDB")
@limiter.limit("30/minute")
def get_cmdb_3d_graph(
    request: Request,
    max_nodes: int = Query(200, ge=10, le=500),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    org_id = getattr(current_user, "organization_id", None)
    return get_3d_graph(db, org_id=org_id, max_nodes=max_nodes)


@router.get("/cmdb/blast-radius/{ci_id}", summary="Radio de impacto si falla un CI")
@limiter.limit("30/minute")
def get_blast_radius(
    request: Request,
    ci_id: str,
    max_depth: int = Query(5, ge=1, le=10),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    org_id = getattr(current_user, "organization_id", None)
    return calculate_blast_radius(db, org_id=org_id, ci_id=ci_id, max_depth=max_depth)


@router.post("/cmdb/asset-links", summary="Vincular asset físico a CI lógico", status_code=201)
@limiter.limit("20/minute")
def create_asset_link(
    request: Request,
    body: AssetLinkIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    org_id = getattr(current_user, "organization_id", None)
    return link_asset_to_ci(
        db,
        org_id=org_id,
        asset_id=body.asset_id,
        ci_id=body.ci_id,
        link_type=body.link_type,
        notes=body.notes,
        created_by=current_user.id,
    )


@router.get("/cmdb/asset-links", summary="Listar vínculos asset-CI")
@limiter.limit("60/minute")
def get_asset_links(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    org_id = getattr(current_user, "organization_id", None)
    items = list_asset_links(db, org_id=org_id)
    return {"items": items, "count": len(items)}


@router.get("/cmdb/asset-impact/{asset_id}", summary="Impacto de un asset vía sus CIs vinculados")
@limiter.limit("20/minute")
def get_asset_impact_view(
    request: Request,
    asset_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    org_id = getattr(current_user, "organization_id", None)
    return get_asset_impact(db, org_id=org_id, asset_id=asset_id)
