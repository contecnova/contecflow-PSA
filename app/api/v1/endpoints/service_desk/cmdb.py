"""Service Desk — CMDB subdomain router."""
from fastapi import APIRouter, Depends, Query, Body
from sqlalchemy.orm import Session
from typing import Optional
from pydantic import BaseModel
import json
from datetime import datetime, timezone

from app.db.session import get_db
from app.core.deps import get_current_user, require_admin
from app.models.user import User
from app.models.cmdb import CMDBDiscoveryProvider, CMDBDiscoveryJob
from app.services.service_desk.ticket_ops_service import commit_or_rollback as _commit_or_rollback
from app.schemas.service_desk import CIIn
from app.services.service_desk.cmdb_service import (
    list_cmdb_items, serialize_cmdb_items, enforce_ci_org_constraints,
    build_ci, get_scoped_ci_or_404, apply_ci_update,
)
from app.services.service_desk.cmdb_relation_service import (
    get_ci_relations_payload, build_ci_relation, get_ci_impact_payload,
    get_ci_topology_graph_payload, get_dependency_graph_d3, get_blast_radius_summary,
)
from app.services.service_desk.cmdb_discovery_service import (
    run_discovery_for_provider,
    run_all_active_discoveries,
    get_reconciliation_health,
)

router = APIRouter()


class DiscoveryProviderIn(BaseModel):
    name: str
    provider_type: str  # aws|azure|gcp|kubernetes|vsphere
    config: dict | None = None
    is_active: bool = True


class DiscoveryProviderPatch(BaseModel):
    name: Optional[str] = None
    config: Optional[dict] = None
    is_active: Optional[bool] = None


def _serialize_discovery_provider(p: CMDBDiscoveryProvider) -> dict:
    return {
        "id": p.id,
        "name": p.name,
        "provider_type": p.provider_type,
        "is_active": p.is_active,
        "last_run_at": p.last_run_at,
        "last_run_status": p.last_run_status,
        "created_at": p.created_at,
    }


def _serialize_discovery_job(j: CMDBDiscoveryJob) -> dict:
    return {
        "id": j.id,
        "provider_id": j.provider_id,
        "status": j.status,
        "started_at": j.started_at,
        "finished_at": j.finished_at,
        "cis_created": j.cis_created,
        "cis_updated": j.cis_updated,
        "cis_deactivated": j.cis_deactivated,
        "error_message": j.error_message,
        "summary_json": j.summary_json,
        "triggered_by": j.triggered_by,
    }


@router.get("/cmdb", summary="Inventario CMDB")
def list_cmdb(
    page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db), current_user: User = Depends(get_current_user),
):
    return serialize_cmdb_items(list_cmdb_items(db, current_user, page, page_size))


@router.post("/cmdb", summary="Crear CI")
def create_ci(payload: CIIn, db: Session = Depends(get_db), current_user: User = Depends(require_admin)):
    enforce_ci_org_constraints(db, current_user, payload, is_update=False)
    ci = build_ci(db, payload)
    _commit_or_rollback(db); db.refresh(ci)
    return {"id": ci.id, "code": ci.code}


@router.patch("/cmdb/{ci_id}", summary="Actualizar CI")
def update_ci(ci_id: str, payload: CIIn, db: Session = Depends(get_db), current_user: User = Depends(require_admin)):
    ci = get_scoped_ci_or_404(db, current_user, ci_id)
    enforce_ci_org_constraints(db, current_user, payload, is_update=True)
    apply_ci_update(ci, payload)
    _commit_or_rollback(db)
    return {"ok": True}


@router.get("/cmdb/{ci_id}/relations", summary="Relaciones del CI (impacto)")
def get_ci_relations(ci_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    return get_ci_relations_payload(db, current_user, ci_id)


@router.post("/cmdb/relations", summary="Crear relación entre CIs")
def create_ci_relation(payload: dict = Body(...), db: Session = Depends(get_db), current_user: User = Depends(require_admin)):
    rel = build_ci_relation(db, current_user, payload)
    _commit_or_rollback(db)
    return {"id": rel.id, "ok": True}


@router.get("/cmdb/{ci_id}/impact", summary="Análisis de impacto — CIs afectados si este falla")
def get_ci_impact(
    ci_id: str,
    max_depth: int = Query(5, ge=1, le=10),
    limit: int = Query(500, ge=1, le=2000),
    db: Session = Depends(get_db), current_user: User = Depends(get_current_user),
):
    return get_ci_impact_payload(db, current_user, ci_id, max_depth=max_depth, limit=limit)


@router.get("/cmdb/{ci_id}/topology", summary="Topología CMDB navegable alrededor de un CI")
def get_ci_topology(
    ci_id: str,
    radius: int = Query(2, ge=1, le=5),
    limit: int = Query(300, ge=1, le=2000),
    db: Session = Depends(get_db), current_user: User = Depends(get_current_user),
):
    return get_ci_topology_graph_payload(db, current_user, ci_id, radius=radius, limit=limit)


@router.get("/cmdb/discovery/providers", summary="Listar proveedores discovery CMDB")
def list_discovery_providers(
    db: Session = Depends(get_db), current_user: User = Depends(require_admin)
):
    providers = (
        db.query(CMDBDiscoveryProvider)
        .order_by(CMDBDiscoveryProvider.created_at.desc())
        .all()
    )
    return [_serialize_discovery_provider(p) for p in providers]


@router.post("/cmdb/discovery/providers", summary="Crear proveedor discovery CMDB")
def create_discovery_provider(
    payload: DiscoveryProviderIn,
    db: Session = Depends(get_db), current_user: User = Depends(require_admin)
):
    provider = CMDBDiscoveryProvider(
        name=payload.name,
        provider_type=payload.provider_type,
        is_active=payload.is_active,
        config_json=json.dumps(payload.config or {}),
        organization_id=getattr(current_user, "organization_id", None),
        created_by=current_user.id,
    )
    db.add(provider)
    _commit_or_rollback(db)
    db.refresh(provider)
    return _serialize_discovery_provider(provider)


@router.patch("/cmdb/discovery/providers/{provider_id}", summary="Actualizar proveedor discovery CMDB")
def patch_discovery_provider(
    provider_id: str,
    payload: DiscoveryProviderPatch,
    db: Session = Depends(get_db), current_user: User = Depends(require_admin)
):
    provider = db.query(CMDBDiscoveryProvider).filter(CMDBDiscoveryProvider.id == provider_id).first()
    if not provider:
        return {"ok": False, "error": "Provider not found"}

    data = payload.model_dump(exclude_none=True)
    if "name" in data:
        provider.name = data["name"]
    if "is_active" in data:
        provider.is_active = data["is_active"]
    if "config" in data:
        provider.config_json = json.dumps(data["config"] or {})
    provider.updated_at = datetime.now(timezone.utc)

    _commit_or_rollback(db)
    db.refresh(provider)
    return _serialize_discovery_provider(provider)


@router.post("/cmdb/discovery/providers/{provider_id}/run", summary="Ejecutar discovery para proveedor")
def run_discovery_provider_now(
    provider_id: str,
    db: Session = Depends(get_db), current_user: User = Depends(require_admin)
):
    provider = db.query(CMDBDiscoveryProvider).filter(CMDBDiscoveryProvider.id == provider_id).first()
    if not provider:
        return {"ok": False, "error": "Provider not found"}
    job = run_discovery_for_provider(db, provider)
    return {"ok": True, "job": _serialize_discovery_job(job)}


@router.get("/cmdb/discovery/providers/{provider_id}/jobs", summary="Listar jobs de discovery")
def list_discovery_jobs(
    provider_id: str,
    page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=200),
    db: Session = Depends(get_db), current_user: User = Depends(require_admin)
):
    q = (
        db.query(CMDBDiscoveryJob)
        .filter(CMDBDiscoveryJob.provider_id == provider_id)
        .order_by(CMDBDiscoveryJob.started_at.desc())
    )
    total = q.count()
    jobs = q.offset((page - 1) * page_size).limit(page_size).all()
    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "items": [_serialize_discovery_job(j) for j in jobs],
    }


@router.post("/cmdb/discovery/run-all", summary="Ejecutar discovery para todos los proveedores activos")
def run_discovery_all(
    db: Session = Depends(get_db), current_user: User = Depends(require_admin)
):
    return {"ok": True, "results": run_all_active_discoveries(db)}


@router.get("/cmdb/discovery/reconciliation-health", summary="Salud de reconciliación CMDB")
def reconciliation_health(
    provider_type: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    return get_reconciliation_health(db, provider_type=provider_type)


# ── Dependency mapping + Blast Radius ────────────────────────────────────────

@router.get("/cmdb/{ci_id}/dependency-graph", summary="Grafo de dependencias D3.js force-directed")
def get_dependency_graph(
    ci_id: str,
    depth: int = Query(3, ge=1, le=6),
    limit: int = Query(300, ge=1, le=2000),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Retorna un grafo compatible con D3.js forceSimulation.

    Nodos incluyen color por tipo de CI y estado operacional.
    Links incluyen tipo de relación y strength para la simulación.
    """
    return get_dependency_graph_d3(db, current_user, ci_id, depth=depth, limit=limit)


@router.get("/cmdb/{ci_id}/blast-radius", summary="Resumen de blast radius (CIs afectados + usuarios estimados)")
def get_ci_blast_radius(
    ci_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Análisis de radio de impacto con desglose por criticidad y estimación de usuarios afectados."""
    return get_blast_radius_summary(db, current_user, ci_id)
