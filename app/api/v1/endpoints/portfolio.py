"""
Portfolio API — gestión de carteras de proyectos.
GET/POST /portfolios
GET/PATCH/DELETE /portfolios/{portfolio_id}
POST /portfolios/{portfolio_id}/projects
DELETE /portfolios/{portfolio_id}/projects/{project_id}
GET /portfolios/{portfolio_id}/dashboard
"""
import uuid
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import Optional
from pydantic import BaseModel
from datetime import date

from app.db.session import get_db
from app.core.deps import get_current_user, require_admin_or_pm
from app.models.user import User
from app.models.portfolio import Portfolio, PortfolioProject
from app.models.project import Project
from app.models.task import Task, TaskStatus
from app.models.imputation import Imputation
from app.models.financial import ProjectMilestone

router = APIRouter()


# ── Schemas ───────────────────────────────────────────────────────────────────
class PortfolioIn(BaseModel):
    name:         str
    description:  Optional[str]  = None
    status:       Optional[str]  = "active"
    budget_total: Optional[float]= None
    start_date:   Optional[date] = None
    end_date:     Optional[date] = None


class PortfolioProjectIn(BaseModel):
    project_id:    str
    rag_override:  Optional[str]  = None
    display_order: Optional[float]= 0.0


# ── Helpers ───────────────────────────────────────────────────────────────────
def _evm_quick(project_id: str, db: Session) -> dict:
    """Fast EVM snapshot for a project — replicates project EVM logic."""
    proj = db.query(Project).filter(Project.id == project_id).first()
    if not proj:
        return {"cpi": None, "spi": None, "pct_complete": 0, "health": "grey", "ac": 0, "bac": 0}

    bac = proj.budget_amount or 0.0
    ac  = db.query(func.sum(Imputation.cost_amount)).filter(
        Imputation.project_id == project_id,
        Imputation.cost_amount.isnot(None),
    ).scalar() or 0.0

    total_est = db.query(func.sum(Task.estimated_hours)).filter(Task.project_id == project_id).scalar() or 0.0
    done_est  = db.query(func.sum(Task.estimated_hours)).filter(
        Task.project_id == project_id, Task.status == TaskStatus.done
    ).scalar() or 0.0
    pct = (done_est / total_est) if total_est > 0 else 0.0
    ev  = bac * pct

    today = date.today()
    s, e  = proj.start_date, proj.end_date_planned
    pct_t = min((today - s).days / (e - s).days, 1.0) if s and e and e > s else pct
    pv    = bac * max(pct_t, 0)

    cpi = round(ev / ac, 3) if ac > 0 else None
    spi = round(ev / pv, 3) if pv > 0 else None

    def _h(c, s):
        if c is None or s is None: return "grey"
        if c >= 0.9 and s >= 0.9:  return "green"
        if c < 0.85 or s < 0.85:   return "red"
        return "yellow"

    return {"cpi": cpi, "spi": spi, "pct_complete": round(pct * 100, 1),
            "health": _h(cpi, spi), "ac": round(ac, 2), "bac": round(bac, 2),
            "ev": round(ev, 2)}


def _serialize_portfolio(p: Portfolio):
    return {
        "id": p.id, "name": p.name, "description": p.description,
        "status": p.status, "budget_total": p.budget_total,
        "start_date": p.start_date.isoformat() if p.start_date else None,
        "end_date": p.end_date.isoformat() if p.end_date else None,
        "owner_id": p.owner_id,
        "project_count": len(p.members),
        "created_at": p.created_at.isoformat() if p.created_at else None,
    }


# ── CRUD ──────────────────────────────────────────────────────────────────────
@router.get("", summary="Listar carteras")
def list_portfolios(db: Session = Depends(get_db),
                    cu: User = Depends(get_current_user)):
    q = db.query(Portfolio)
    if not cu.is_superadmin and cu.organization_id:
        org_user_ids = db.query(User.id).filter(
            User.organization_id == cu.organization_id
        ).scalar_subquery()
        q = q.filter(Portfolio.owner_id.in_(org_user_ids))
    rows = q.order_by(Portfolio.name).all()
    return [_serialize_portfolio(r) for r in rows]


@router.post("", summary="Crear cartera", status_code=201)
def create_portfolio(payload: PortfolioIn, db: Session = Depends(get_db),
                     cu: User = Depends(require_admin_or_pm)):
    p = Portfolio(id=str(uuid.uuid4()), owner_id=cu.id, **payload.model_dump())
    db.add(p); db.commit(); db.refresh(p)
    return _serialize_portfolio(p)


@router.get("/{portfolio_id}", summary="Detalle de cartera")
def get_portfolio(portfolio_id: str, db: Session = Depends(get_db),
                  cu: User = Depends(get_current_user)):
    p = db.query(Portfolio).filter(Portfolio.id == portfolio_id).first()
    if not p: raise HTTPException(404, "Cartera no encontrada")
    return _serialize_portfolio(p)


@router.patch("/{portfolio_id}", summary="Actualizar cartera")
def update_portfolio(portfolio_id: str, payload: PortfolioIn,
                     db: Session = Depends(get_db),
                     cu: User = Depends(require_admin_or_pm)):
    p = db.query(Portfolio).filter(Portfolio.id == portfolio_id).first()
    if not p: raise HTTPException(404, "Cartera no encontrada")
    for k, v in payload.model_dump(exclude_unset=True).items():
        setattr(p, k, v)
    db.commit(); db.refresh(p)
    return _serialize_portfolio(p)


@router.delete("/{portfolio_id}", summary="Eliminar cartera")
def delete_portfolio(portfolio_id: str, db: Session = Depends(get_db),
                     cu: User = Depends(require_admin_or_pm)):
    p = db.query(Portfolio).filter(Portfolio.id == portfolio_id).first()
    if not p: raise HTTPException(404, "Cartera no encontrada")
    db.delete(p); db.commit()
    return {"deleted": True}


# ── Projects within portfolio ──────────────────────────────────────────────────
@router.post("/{portfolio_id}/projects", summary="Añadir proyecto a la cartera", status_code=201)
def add_project(portfolio_id: str, payload: PortfolioProjectIn,
                db: Session = Depends(get_db),
                cu: User = Depends(require_admin_or_pm)):
    p = db.query(Portfolio).filter(Portfolio.id == portfolio_id).first()
    if not p: raise HTTPException(404, "Cartera no encontrada")
    proj = db.query(Project).filter(Project.id == payload.project_id).first()
    if not proj: raise HTTPException(404, "Proyecto no encontrado")
    existing = db.query(PortfolioProject).filter(
        PortfolioProject.portfolio_id == portfolio_id,
        PortfolioProject.project_id   == payload.project_id,
    ).first()
    if existing: raise HTTPException(409, "El proyecto ya pertenece a esta cartera")
    pp = PortfolioProject(id=str(uuid.uuid4()), portfolio_id=portfolio_id, **payload.model_dump())
    db.add(pp); db.commit()
    return {"ok": True}


@router.delete("/{portfolio_id}/projects/{project_id}", summary="Quitar proyecto de la cartera")
def remove_project(portfolio_id: str, project_id: str,
                   db: Session = Depends(get_db),
                   cu: User = Depends(require_admin_or_pm)):
    pp = db.query(PortfolioProject).filter(
        PortfolioProject.portfolio_id == portfolio_id,
        PortfolioProject.project_id   == project_id,
    ).first()
    if not pp: raise HTTPException(404, "El proyecto no está en esta cartera")
    db.delete(pp); db.commit()
    return {"deleted": True}


# ── Portfolio Dashboard ────────────────────────────────────────────────────────
@router.get("/{portfolio_id}/dashboard", summary="Dashboard de cartera — RAG, EVM, hitos")
def portfolio_dashboard(portfolio_id: str, db: Session = Depends(get_db),
                         cu: User = Depends(get_current_user)):
    """
    Returns a full portfolio dashboard:
    - Per-project health (RAG), EVM snapshot, upcoming milestones
    - Budget summary (total envelope vs. actual spend)
    - Cross-project milestone timeline (for Gantt-style view)
    """
    port = db.query(Portfolio).filter(Portfolio.id == portfolio_id).first()
    if not port: raise HTTPException(404, "Cartera no encontrada")

    projects_data = []
    total_budget  = 0.0
    total_ac      = 0.0
    today         = date.today()

    for pp in port.members:
        proj = pp.project
        if not proj:
            continue

        evm = _evm_quick(proj.id, db)

        # RAG: use manual override if set, else EVM health
        rag = pp.rag_override or evm["health"]

        # Upcoming milestones (next 60 days)
        milestones = db.query(ProjectMilestone).filter(
            ProjectMilestone.project_id == proj.id,
            ProjectMilestone.due_date   >= today,
        ).order_by(ProjectMilestone.due_date).limit(5).all()

        ms_list = [{
            "id": m.id, "title": m.title,
            "due_date": m.due_date.isoformat() if m.due_date else None,
            "is_completed": m.is_completed,
        } for m in milestones]

        total_budget += evm["bac"]
        total_ac     += evm["ac"]

        projects_data.append({
            "project_id":   proj.id,
            "project_name": proj.name,
            "status":       proj.status.value if proj.status else None,
            "rag":          rag,
            "display_order":pp.display_order,
            "start_date":   proj.start_date.isoformat() if proj.start_date else None,
            "end_date":     proj.end_date_planned.isoformat() if proj.end_date_planned else None,
            "pct_complete": evm["pct_complete"],
            "cpi":          evm["cpi"],
            "spi":          evm["spi"],
            "bac":          evm["bac"],
            "ac":           evm["ac"],
            "ev":           evm["ev"],
            "milestones":   ms_list,
        })

    # Sort: red first, then yellow, then green, then grey
    _rank = {"red": 0, "yellow": 1, "green": 2, "grey": 3}
    projects_data.sort(key=lambda r: _rank.get(r["rag"], 4))

    # Health counts
    health_counts = {"red": 0, "yellow": 0, "green": 0, "grey": 0}
    for r in projects_data:
        health_counts[r["rag"]] = health_counts.get(r["rag"], 0) + 1

    budget_envelope = port.budget_total or total_budget

    return {
        "portfolio_id":   portfolio_id,
        "portfolio_name": port.name,
        "status":         port.status,
        "budget_envelope":round(budget_envelope, 2),
        "budget_spent":   round(total_ac, 2),
        "budget_pct":     round((total_ac / budget_envelope * 100) if budget_envelope > 0 else 0, 1),
        "project_count":  len(projects_data),
        "health_counts":  health_counts,
        "projects":       projects_data,
    }
