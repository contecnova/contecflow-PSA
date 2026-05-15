"""
Report Builder — no-code parametric report system (thin router).

Delegates all logic to app.services.report_builder_service.
"""

from typing import Any, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.abac_enforce import enforce_abac
from app.core.deps import get_current_user, get_db
from app.models.user import User
import app.services.report_builder_service as _svc

router = APIRouter()

# Re-export catalog for tests/SDKs that import directly
ENTITIES = _svc.ENTITIES
OPERATORS = _svc.OPERATORS
GROUPS = _svc.GROUPS


# ── Pydantic schemas ──────────────────────────────────────────────────────────

class FilterCondition(BaseModel):
    column:   str
    operator: str
    value:    Any


class SortSpec(BaseModel):
    column:    str
    direction: str = "asc"


class ReportQuery(BaseModel):
    entity:  str
    columns: List[str]
    filters: List[FilterCondition] = []
    sort:    Optional[SortSpec] = None
    limit:   int = 500


class ReportTemplate(BaseModel):
    name:  str
    query: ReportQuery


# ── Routes ────────────────────────────────────────────────────────────────────

@router.get("/schema", summary="Obtener esquema de entidades disponibles")
def get_schema(_: User = Depends(get_current_user)):
    return {
        "entities":  _svc.ENTITIES,
        "operators": _svc.OPERATORS,
        "groups":    _svc.GROUPS,
    }


@router.post("/preview", summary="Previsualizar informe")
def preview_report(
    q: ReportQuery,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if q.entity not in _svc.ENTITIES:
        raise HTTPException(400, f"Entidad '{q.entity}' desconocida")
    limit = min(q.limit, 500)
    rows = _svc.execute_report(
        q.entity, q.columns, q.filters,
        q.sort.column if q.sort else None,
        q.sort.direction if q.sort else "asc",
        limit, current_user, db,
    )
    return {"rows": rows, "count": len(rows), "truncated": len(rows) == limit}



from fastapi import Query

@router.post("/export", summary="Exportar informe a CSV")
def export_report(
    q: ReportQuery,
    page: int = Query(1, ge=1, description="Número de página para exportación paginada"),
    page_size: int = Query(2000, ge=1, le=10000, description="Tamaño de página para exportación paginada"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if q.entity not in _svc.ENTITIES:
        raise HTTPException(400, f"Entidad '{q.entity}' desconocida")
    result = _svc.execute_report_paginated(
        q.entity, q.columns, q.filters,
        q.sort.column if q.sort else None,
        q.sort.direction if q.sort else "asc",
        page, page_size, current_user, db,
    )
    return _svc.build_csv_response(q.columns, result["items"], q.entity, pagination=result)


@router.get("/templates", summary="Listar plantillas de informes")
def list_templates(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return _svc.load_user_templates(str(current_user.id), db)


@router.post("/templates", summary="Guardar plantilla de informe")
def save_template(
    tpl: ReportTemplate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if tpl.query.entity not in _svc.ENTITIES:
        raise HTTPException(400, f"Entidad '{tpl.query.entity}' desconocida")
    templates = _svc.load_user_templates(str(current_user.id), db)
    next_id = max((t["id"] for t in templates), default=0) + 1
    record = {"id": next_id, "name": tpl.name, "query": tpl.query.model_dump()}
    templates.append(record)
    _svc.save_user_templates(str(current_user.id), templates, db)
    return record


@router.delete("/templates/{template_id}", summary="Eliminar plantilla de informe")
def delete_template(
    template_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    enforce_abac(db, current_user, "report_template", template_id, action="delete")
    templates = _svc.load_user_templates(str(current_user.id), db)
    updated = [t for t in templates if t["id"] != template_id]
    if len(updated) == len(templates):
        raise HTTPException(404, "Plantilla no encontrada")
    _svc.save_user_templates(str(current_user.id), updated, db)
    return {"ok": True}
