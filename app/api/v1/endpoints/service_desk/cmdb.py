"""Service Desk — CMDB subdomain router."""
from fastapi import APIRouter, Depends, Query, Body
from sqlalchemy.orm import Session
from typing import Optional

from app.db.session import get_db
from app.core.deps import get_current_user, require_admin
from app.models.user import User
from app.services.service_desk.ticket_ops_service import commit_or_rollback as _commit_or_rollback
from app.schemas.service_desk import CIIn
from app.services.service_desk.cmdb_service import (
    list_cmdb_items, serialize_cmdb_items, enforce_ci_org_constraints,
    build_ci, get_scoped_ci_or_404, apply_ci_update,
)
from app.services.service_desk.cmdb_relation_service import (
    get_ci_relations_payload, build_ci_relation, get_ci_impact_payload,
)

router = APIRouter()


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
