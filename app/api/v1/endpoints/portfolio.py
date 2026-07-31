"""
Portfolio API — gestión de carteras de proyectos.
GET/POST   /portfolios
GET/PATCH/DELETE /portfolios/{portfolio_id}
POST   /portfolios/{portfolio_id}/projects
DELETE /portfolios/{portfolio_id}/projects/{project_id}
GET    /portfolios/{portfolio_id}/dashboard
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import Optional
from pydantic import BaseModel
from datetime import date

from app.db.session import get_db
from app.core.deps import get_current_user, require_admin_or_pm
from app.core.abac_enforce import enforce_abac
from app.core.events import emit_event, EventType
from app.core.responses import APIListResponse, APIResponse
from app.models.user import User
from app.services import portfolio_service
from app.services.portfolio_service import serialize_portfolio as _serialize_portfolio

router = APIRouter()


# ── Schemas ───────────────────────────────────────────────────────────────────
class PortfolioIn(BaseModel):
    name:         str
    description:  Optional[str]   = None
    status:       Optional[str]   = "active"
    budget_total: Optional[float] = None
    start_date:   Optional[date]  = None
    end_date:     Optional[date]  = None


class PortfolioProjectIn(BaseModel):
    project_id:    str
    rag_override:  Optional[str]   = None
    display_order: Optional[float] = 0.0


# ── CRUD ──────────────────────────────────────────────────────────────────────
@router.get("", response_model=APIListResponse[dict], summary="Listar carteras")
@router.get("/", response_model=APIListResponse[dict], summary="Listar carteras", include_in_schema=False)
def list_portfolios(page: int = Query(1, ge=1),
                    page_size: int = Query(50, ge=1, le=200),
                    db: Session = Depends(get_db),
                    cu: User = Depends(get_current_user)):
    rows = portfolio_service.list_portfolios(
        db,
        is_superadmin=cu.is_superadmin,
        organization_id=cu.organization_id,
    )
    items = [_serialize_portfolio(r) for r in rows]
    return APIListResponse.ok(items=items, page=page, page_size=page_size)


@router.post("", summary="Crear cartera", status_code=201)
@router.post("/", summary="Crear cartera", status_code=201, include_in_schema=False)
def create_portfolio(payload: PortfolioIn, db: Session = Depends(get_db),
                     cu: User = Depends(require_admin_or_pm)):
    p = portfolio_service.create_portfolio(db, owner_id=cu.id, data=payload.model_dump())
    emit_event(db, EventType.PORTFOLIO_CREATED, {"name": p.name, "status": p.status},
               actor=cu, resource_type="portfolio", resource_id=p.id)
    return APIResponse.ok(data=_serialize_portfolio(p))


@router.get("/{portfolio_id}", summary="Detalle de cartera")
def get_portfolio(portfolio_id: str, db: Session = Depends(get_db),
                  cu: User = Depends(get_current_user)):
    p = portfolio_service.get_portfolio(db, portfolio_id)
    if not p:
        raise HTTPException(404, "Cartera no encontrada")
    return APIResponse.ok(data=_serialize_portfolio(p))


@router.patch("/{portfolio_id}", summary="Actualizar cartera")
def update_portfolio(portfolio_id: str, payload: PortfolioIn,
                     db: Session = Depends(get_db),
                     cu: User = Depends(require_admin_or_pm)):
    p = portfolio_service.get_portfolio(db, portfolio_id)
    if not p:
        raise HTTPException(404, "Cartera no encontrada")
    p = portfolio_service.update_portfolio(db, p, payload.model_dump(exclude_unset=True))
    emit_event(db, EventType.PORTFOLIO_UPDATED, payload.model_dump(exclude_unset=True),
               actor=cu, resource_type="portfolio", resource_id=portfolio_id)
    return APIResponse.ok(data=_serialize_portfolio(p))


@router.delete("/{portfolio_id}", summary="Eliminar cartera")
def delete_portfolio(portfolio_id: str, db: Session = Depends(get_db),
                     cu: User = Depends(require_admin_or_pm)):
    p = portfolio_service.get_portfolio(db, portfolio_id)
    if not p:
        raise HTTPException(404, "Cartera no encontrada")
    enforce_abac(db, cu, "portfolio", portfolio_id, action="delete")
    name = p.name
    try:
        portfolio_service.delete_portfolio(db, p)
    except ValueError as e:
        raise HTTPException(400, str(e))
    emit_event(db, EventType.PORTFOLIO_DELETED, {"name": name},
               actor=cu, resource_type="portfolio", resource_id=portfolio_id)
    return APIResponse.ok(data={"ok": True, "message": "Cartera eliminada correctamente"})


# ── Projects within portfolio ──────────────────────────────────────────────────
@router.post("/{portfolio_id}/projects", summary="Añadir proyecto a la cartera", status_code=201)
def add_project(portfolio_id: str, payload: PortfolioProjectIn,
                db: Session = Depends(get_db),
                cu: User = Depends(require_admin_or_pm)):
    p = portfolio_service.get_portfolio(db, portfolio_id)
    if not p:
        raise HTTPException(404, "Cartera no encontrada")
    proj = portfolio_service.get_project(db, payload.project_id)
    if not proj:
        raise HTTPException(404, "Proyecto no encontrado")
    if portfolio_service.get_portfolio_project(db, portfolio_id, payload.project_id):
        raise HTTPException(409, "El proyecto ya pertenece a esta cartera")
    portfolio_service.add_project_to_portfolio(
        db,
        portfolio_id=portfolio_id,
        project_id=payload.project_id,
        rag_override=payload.rag_override,
        display_order=payload.display_order or 0.0,
    )
    emit_event(db, EventType.PORTFOLIO_PROJECT_ADDED,
               {"portfolio_id": portfolio_id, "project_id": payload.project_id, "project_name": proj.name},
               actor=cu, resource_type="portfolio", resource_id=portfolio_id)
    return APIResponse.ok(data={"ok": True})


@router.delete("/{portfolio_id}/projects/{project_id}", summary="Quitar proyecto de la cartera")
def remove_project(portfolio_id: str, project_id: str,
                   db: Session = Depends(get_db),
                   cu: User = Depends(require_admin_or_pm)):
    pp = portfolio_service.get_portfolio_project(db, portfolio_id, project_id)
    if not pp:
        raise HTTPException(404, "El proyecto no está en esta cartera")
    enforce_abac(db, cu, "portfolio_project", pp.id, action="delete")
    portfolio_service.remove_project_from_portfolio(db, pp)
    emit_event(db, EventType.PORTFOLIO_PROJECT_REMOVED,
               {"portfolio_id": portfolio_id, "project_id": project_id},
               actor=cu, resource_type="portfolio", resource_id=portfolio_id)
    return APIResponse.ok(data={"ok": True, "message": "Proyecto eliminado de la cartera correctamente"})


# ── Portfolio Dashboard ────────────────────────────────────────────────────────
@router.get("/{portfolio_id}/dashboard",
            summary="Dashboard de cartera — RAG, EVM, hitos")
def portfolio_dashboard(portfolio_id: str, db: Session = Depends(get_db),
                        cu: User = Depends(get_current_user)):
    """
    Returns a full portfolio dashboard:
    - Per-project health (RAG), EVM snapshot, upcoming milestones
    - Budget summary (total envelope vs. actual spend)
    - Cross-project milestone timeline (for Gantt-style view)
    """
    port = portfolio_service.get_portfolio(db, portfolio_id)
    if not port:
        raise HTTPException(404, "Cartera no encontrada")

    projects_data = []
    total_budget  = 0.0
    total_ac      = 0.0
    today         = date.today()

    for pp in port.members:
        if not pp.is_active:
            continue
        proj = pp.project
        if not proj:
            continue

        evm = portfolio_service.get_evm_quick(db, proj.id)
        rag = pp.rag_override or evm["health"]

        milestones = portfolio_service.get_upcoming_milestones(db, proj.id, today, limit=5)
        ms_list = [{
            "id": m.id, "title": m.title,
            "due_date": m.due_date.isoformat() if m.due_date else None,
            "is_completed": m.is_completed,
        } for m in milestones]

        total_budget += evm["bac"]
        total_ac     += evm["ac"]

        projects_data.append({
            "project_id":    proj.id,
            "project_name":  proj.name,
            "status":        proj.status.value if proj.status else None,
            "rag":           rag,
            "display_order": pp.display_order,
            "start_date":    proj.start_date.isoformat() if proj.start_date else None,
            "end_date":      proj.end_date_planned.isoformat() if proj.end_date_planned else None,
            "pct_complete":  evm["pct_complete"],
            "cpi":           evm["cpi"],
            "spi":           evm["spi"],
            "bac":           evm["bac"],
            "ac":            evm["ac"],
            "ev":            evm["ev"],
            "milestones":    ms_list,
        })

    _rank = {"red": 0, "yellow": 1, "green": 2, "grey": 3}
    projects_data.sort(key=lambda r: _rank.get(r["rag"], 4))

    health_counts = {"red": 0, "yellow": 0, "green": 0, "grey": 0}
    for r in projects_data:
        health_counts[r["rag"]] = health_counts.get(r["rag"], 0) + 1

    budget_envelope = port.budget_total or total_budget

    return APIResponse.ok(data={
        "portfolio_id":    portfolio_id,
        "portfolio_name":  port.name,
        "status":          port.status,
        "budget_envelope": round(budget_envelope, 2),
        "budget_spent":    round(total_ac, 2),
        "budget_pct":      round((total_ac / budget_envelope * 100) if budget_envelope > 0 else 0, 1),
        "project_count":   len(projects_data),
        "health_counts":   health_counts,
        "projects":        projects_data,
    })
