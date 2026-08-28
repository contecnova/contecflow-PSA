"""
Portfolio service — all DB access for portfolio endpoints.
"""
import uuid
from datetime import date
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.models.portfolio import Portfolio, PortfolioProject
from app.models.project import Project
from app.models.task import Task, TaskStatus
from app.models.imputation import Imputation
from app.models.financial import ProjectMilestone
from app.models.user import User
from app.core import timeutil


# ── EVM ───────────────────────────────────────────────────────────────────────

def get_evm_quick(db: Session, project_id: str) -> dict:
    """Fast EVM snapshot for a project."""
    proj = db.query(Project).filter(Project.id == project_id).first()
    if not proj:
        return {"cpi": None, "spi": None, "pct_complete": 0, "health": "grey", "ac": 0, "bac": 0, "ev": 0}

    bac = proj.budget_amount or 0.0
    ac = (
        db.query(func.sum(Imputation.cost_amount))
        .filter(
            Imputation.project_id == project_id,
            Imputation.cost_amount.isnot(None),
        )
        .scalar() or 0.0
    )

    total_est = (
        db.query(func.sum(Task.estimated_hours))
        .filter(Task.project_id == project_id)
        .scalar() or 0.0
    )
    done_est = (
        db.query(func.sum(Task.estimated_hours))
        .filter(Task.project_id == project_id, Task.status == TaskStatus.done)
        .scalar() or 0.0
    )
    pct = (done_est / total_est) if total_est > 0 else 0.0
    ev = bac * pct

    today = timeutil.today()
    s, e = proj.start_date, proj.end_date_planned
    pct_t = min((today - s).days / (e - s).days, 1.0) if s and e and e > s else pct
    pv = bac * max(pct_t, 0)

    cpi = round(ev / ac, 3) if ac > 0 else None
    spi = round(ev / pv, 3) if pv > 0 else None

    def _health(c, s):
        if c is None or s is None:
            return "grey"
        if c >= 0.9 and s >= 0.9:
            return "green"
        if c < 0.85 or s < 0.85:
            return "red"
        return "yellow"

    return {
        "cpi": cpi,
        "spi": spi,
        "pct_complete": round(pct * 100, 1),
        "health": _health(cpi, spi),
        "ac": round(ac, 2),
        "bac": round(bac, 2),
        "ev": round(ev, 2),
    }


# ── Portfolio CRUD ────────────────────────────────────────────────────────────

def list_portfolios(db: Session, *, is_superadmin: bool, organization_id) -> list:
    q = db.query(Portfolio).filter(Portfolio.is_active == True)
    if not is_superadmin and organization_id:
        org_user_ids = (
            db.query(User.id)
            .filter(User.organization_id == organization_id)
            .scalar_subquery()
        )
        q = q.filter(Portfolio.owner_id.in_(org_user_ids))
    return q.order_by(Portfolio.name).all()


def create_portfolio(db: Session, *, owner_id: str, data: dict) -> Portfolio:
    p = Portfolio(id=str(uuid.uuid4()), owner_id=owner_id, **data)
    db.add(p)
    db.commit()
    db.refresh(p)
    return p


def get_portfolio(db: Session, portfolio_id: str):
    return db.query(Portfolio).filter(Portfolio.id == portfolio_id, Portfolio.is_active == True).first()


def get_project(db: Session, project_id: str):
    return db.query(Project).filter(Project.id == project_id).first()


def update_portfolio(db: Session, p: Portfolio, updates: dict) -> Portfolio:
    for k, v in updates.items():
        setattr(p, k, v)
    db.commit()
    db.refresh(p)
    return p


def delete_portfolio(db: Session, p: Portfolio) -> None:
    active_members = db.query(func.count(PortfolioProject.id)).filter(
        PortfolioProject.portfolio_id == p.id,
        PortfolioProject.is_active == True,
    ).scalar() or 0
    if active_members > 0:
        raise ValueError(f"No se puede eliminar: la cartera tiene {active_members} proyecto(s) vinculados")
    p.is_active = False
    p.status = "archived"
    db.commit()


# ── Portfolio ↔ Project membership ────────────────────────────────────────────

def get_portfolio_project(db: Session, portfolio_id: str, project_id: str):
    return (
        db.query(PortfolioProject)
        .filter(
            PortfolioProject.portfolio_id == portfolio_id,
            PortfolioProject.project_id == project_id,
            PortfolioProject.is_active == True,
        )
        .first()
    )


def add_project_to_portfolio(
    db: Session,
    portfolio_id: str,
    project_id: str,
    rag_override=None,
    display_order: float = 0.0,
) -> PortfolioProject:
    existing = (
        db.query(PortfolioProject)
        .filter(
            PortfolioProject.portfolio_id == portfolio_id,
            PortfolioProject.project_id == project_id,
        )
        .first()
    )
    if existing:
        existing.is_active = True
        existing.rag_override = rag_override
        existing.display_order = display_order
        db.commit()
        return existing

    pp = PortfolioProject(
        id=str(uuid.uuid4()),
        portfolio_id=portfolio_id,
        project_id=project_id,
        rag_override=rag_override,
        display_order=display_order,
    )
    db.add(pp)
    db.commit()
    return pp


def remove_project_from_portfolio(db: Session, pp: PortfolioProject) -> None:
    pp.is_active = False
    db.commit()


# ── Dashboard helpers ─────────────────────────────────────────────────────────

def get_upcoming_milestones(
    db: Session, project_id: str, from_date: date, limit: int = 5
) -> list:
    return (
        db.query(ProjectMilestone)
        .filter(
            ProjectMilestone.project_id == project_id,
            ProjectMilestone.is_active == True,
            ProjectMilestone.due_date >= from_date,
        )
        .order_by(ProjectMilestone.due_date)
        .limit(limit)
        .all()
    )


# ── Serialization helper ───────────────────────────────────────────────────

def serialize_portfolio(p) -> dict:
    return {
        "id": p.id, "name": p.name, "description": p.description,
        "status": p.status, "budget_total": p.budget_total,
        "start_date": p.start_date.isoformat() if p.start_date else None,
        "end_date": p.end_date.isoformat() if p.end_date else None,
        "owner_id": p.owner_id,
        "project_count": len([m for m in (p.members or []) if m.is_active]),
        "created_at": p.created_at.isoformat() if p.created_at else None,
    }
