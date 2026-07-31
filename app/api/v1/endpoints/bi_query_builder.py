"""
bi_query_builder.py — Self-service visual query builder REST endpoints.

Routes:
  GET  /bi/query-builder/schema       — available datasets, fields, operators
  GET  /bi/query-builder/queries      — list saved queries
  POST /bi/query-builder/queries      — save a new query
  DELETE /bi/query-builder/queries/{id} — delete a saved query
  POST /bi/query-builder/queries/{id}/execute — execute a saved query
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.abac_enforce import enforce_abac
from app.core.deps import get_current_user
from app.core.ratelimit import limiter
from app.core.responses import APIResponse
from app.db.session import get_db
from app.models.user import User
from app.services import bi_query_builder_service as svc

router = APIRouter()


class AggregationSpec(BaseModel):
    field: str
    func: str = Field(..., description="count | sum | avg | min | max")
    alias: Optional[str] = None


class FilterSpec(BaseModel):
    field: str
    operator: str = "eq"
    op: Optional[str] = None
    value: object = None


class OrderBySpec(BaseModel):
    field: str
    direction: str = Field("desc", pattern="^(asc|desc)$")


class SaveQueryIn(BaseModel):
    name: str = Field(..., min_length=2, max_length=200)
    dataset: str
    fields: list[str] = Field(default_factory=list)
    filters: list[FilterSpec] = Field(default_factory=list)
    group_by: list[str] = Field(default_factory=list)
    aggregations: list[AggregationSpec] = Field(default_factory=list)
    order_by: list[OrderBySpec] = Field(default_factory=list)
    sort_by: Optional[str] = None
    sort_dir: str = Field("desc", pattern="^(asc|desc)$")
    limit: int = Field(100, ge=1, le=5000)


class PreviewQueryIn(BaseModel):
    dataset: str
    fields: list[str] = Field(default_factory=list)
    filters: list[FilterSpec] = Field(default_factory=list)
    group_by: list[str] = Field(default_factory=list)
    aggregations: list[AggregationSpec] = Field(default_factory=list)
    order_by: list[OrderBySpec] = Field(default_factory=list)
    sort_by: Optional[str] = None
    sort_dir: str = Field("desc", pattern="^(asc|desc)$")
    limit: int = Field(100, ge=1, le=5000)


@router.get("/bi/query-builder/schema", summary="Esquema de datasets y campos disponibles")
@limiter.limit("60/minute")
def get_schema(
    request: Request,
    current_user: User = Depends(get_current_user),
):
    return APIResponse.ok(data=svc.get_schema())


@router.get("/bi/query-builder/queries", summary="Listar queries guardadas")
@limiter.limit("60/minute")
def list_queries(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    org_id = getattr(current_user, "organization_id", None)
    items = svc.list_queries(db, org_id=org_id)
    return APIResponse.ok(data={"items": items, "count": len(items)})


@router.post("/bi/query-builder/queries", summary="Guardar una nueva query visual", status_code=201)
@limiter.limit("20/minute")
def save_query(
    request: Request,
    body: SaveQueryIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    org_id = getattr(current_user, "organization_id", None)
    try:
        return APIResponse.ok(data=svc.save_query(
            db,
            org_id=org_id,
            name=body.name,
            dataset=body.dataset,
            fields=body.fields,
            filters=[
                {
                    "field": f.field,
                    "operator": f.operator or f.op or "eq",
                    "value": f.value,
                }
                for f in body.filters
            ],
            group_by=body.group_by,
            aggregations=[a.model_dump() for a in body.aggregations],
            sort_by=body.sort_by or (body.order_by[0].field if body.order_by else None),
            sort_dir=body.sort_dir if body.sort_by else (body.order_by[0].direction if body.order_by else body.sort_dir),
            limit=body.limit,
            created_by=current_user.id,
        ))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


@router.post("/bi/query-builder/preview", summary="Preview ad-hoc de query visual sin guardar")
@limiter.limit("30/minute")
def preview_query(
    request: Request,
    body: PreviewQueryIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        return APIResponse.ok(data=svc.preview_query(
            db,
            current_user=current_user,
            dataset=body.dataset,
            fields=body.fields,
            filters=[
                {
                    "field": f.field,
                    "operator": f.operator or f.op or "eq",
                    "value": f.value,
                }
                for f in body.filters
            ],
            group_by=body.group_by,
            aggregations=[a.model_dump() for a in body.aggregations],
            sort_by=body.sort_by or (body.order_by[0].field if body.order_by else None),
            sort_dir=body.sort_dir if body.sort_by else (body.order_by[0].direction if body.order_by else body.sort_dir),
            limit=body.limit,
        ))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


@router.delete("/bi/query-builder/queries/{query_id}", summary="Eliminar una query guardada", status_code=204)
@limiter.limit("20/minute")
def delete_query(
    request: Request,
    query_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    enforce_abac(db, current_user, "bi_saved_query", query_id, action="delete")
    org_id = getattr(current_user, "organization_id", None)
    try:
        svc.delete_query(db, org_id=org_id, query_id=query_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.post("/bi/query-builder/queries/{query_id}/execute", summary="Ejecutar una query guardada")
@limiter.limit("20/minute")
def execute_query(
    request: Request,
    query_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    org_id = getattr(current_user, "organization_id", None)
    try:
        return APIResponse.ok(data=svc.execute_query(db, org_id=org_id, query_id=query_id, current_user=current_user))
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
