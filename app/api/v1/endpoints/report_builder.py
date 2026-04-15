"""
Report Builder — no-code parametric report system (thin router).

Delegates all logic to app.services.report_builder_service.
"""

import csv
import io
from datetime import date
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

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

@router.get("/schema")
def get_schema(_: User = Depends(get_current_user)):
    return {
        "entities":  _svc.ENTITIES,
        "operators": _svc.OPERATORS,
        "groups":    _svc.GROUPS,
    }


@router.post("/preview")
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


@router.post("/export")
def export_report(
    q: ReportQuery,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if q.entity not in _svc.ENTITIES:
        raise HTTPException(400, f"Entidad '{q.entity}' desconocida")
    rows = _svc.execute_report(
        q.entity, q.columns, q.filters,
        q.sort.column if q.sort else None,
        q.sort.direction if q.sort else "asc",
        2000, current_user, db,
    )
    return _svc.build_csv_response(q.columns, rows, q.entity)


@router.get("/templates")
def list_templates(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return _svc.load_user_templates(str(current_user.id), db)


@router.post("/templates")
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


@router.delete("/templates/{template_id}")
def delete_template(
    template_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    templates = _svc.load_user_templates(str(current_user.id), db)
    updated = [t for t in templates if t["id"] != template_id]
    if len(updated) == len(templates):
        raise HTTPException(404, "Plantilla no encontrada")
    _svc.save_user_templates(str(current_user.id), updated, db)
    return {"ok": True}
