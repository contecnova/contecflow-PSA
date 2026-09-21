"""
BI Data Versioning endpoints — DuckDB temporal tables + snapshots
=================================================================
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.core.responses import APIResponse
from app.models.user import User
from app.services import bi_data_versioning_service as svc
from app.core.deps import require_internal_user

router = APIRouter(prefix="/bi/versioning", tags=["BI Data Versioning"])


@router.post("/snapshots", summary="Crear snapshot versionado de un dataset", status_code=201)
def create_snapshot(
    payload: dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _rol: User = Depends(require_internal_user),  # auditoria 2026-09: dominio: analitica interna
):
    """Captura el estado actual de un dataset y lo guarda como versión inmutable.

    Body JSON:
        dataset_key  (str, required) — nombre del dataset, ej. "revenue_monthly"
        description  (str, optional) — descripción del cambio
    """
    org_id = str(current_user.organization_id or "global")
    return APIResponse.ok(data=svc.create_version_snapshot(
        db,
        org_id=org_id,
        dataset_key=payload["dataset_key"],
        description=payload.get("description", ""),
        created_by=str(current_user.id),
    ))


@router.get("/snapshots", summary="Listar versiones de un dataset")
def list_snapshots(
    dataset_key: str = Query(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    org_id = str(current_user.organization_id or "global")
    versions = svc.list_versions(db, org_id=org_id, dataset_key=dataset_key)
    return APIResponse.ok(data={"dataset_key": dataset_key, "versions": versions, "count": len(versions)})


@router.get("/snapshots/{version_id}", summary="Obtener datos de una versión específica")
def get_snapshot(
    version_id: str,
    dataset_key: str = Query(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    org_id = str(current_user.organization_id or "global")
    return APIResponse.ok(data=svc.get_version_data(db, org_id=org_id, dataset_key=dataset_key, version_id=version_id))


@router.get("/diff", summary="Comparar dos versiones de un dataset (diff)")
def diff_versions(
    dataset_key: str = Query(...),
    v1: str = Query(..., description="version_id de la versión base"),
    v2: str = Query(..., description="version_id de la versión comparada"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    org_id = str(current_user.organization_id or "global")
    return APIResponse.ok(data=svc.diff_versions(db, org_id=org_id, dataset_key=dataset_key, version_id_a=v1, version_id_b=v2))


@router.get("/temporal", summary="Query temporal — estado del dataset en un momento pasado")
def temporal_query(
    dataset_key: str = Query(...),
    as_of: str = Query(..., description="ISO 8601 timestamp, ej. 2024-06-01T00:00:00Z"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Devuelve el snapshot más reciente capturado en o antes de `as_of`."""
    org_id = str(current_user.organization_id or "global")
    return APIResponse.ok(data=svc.temporal_query(db, org_id=org_id, dataset_key=dataset_key, as_of=as_of))
