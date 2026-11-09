"""
Portfolio service — all DB access for portfolio endpoints.
"""
import uuid
from datetime import date
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.models.portfolio import Portfolio, PortfolioProject
from app.models.project import Project
from app.models.financial import ProjectMilestone
from app.models.user import User


# ── EVM ───────────────────────────────────────────────────────────────────────

def get_evm_quick(db: Session, project_id: str) -> dict:
    """EVM de un proyecto con el mismo cálculo que la ficha y la lista de EVM.

    Revisión 2026-11: tenía su copia sin respaldos de BAC y AC (proyectos sin
    `budget_amount` salían en gris) y otro semáforo.
    """
    from app.services.project_service import calculate_evm
    d = calculate_evm(project_id, db)
    if not d:
        return {"cpi": None, "spi": None, "pct_complete": 0, "health": "grey", "ac": 0, "bac": 0, "ev": 0}
    return {k: d[k] for k in ("cpi", "spi", "pct_complete", "health", "ac", "bac", "ev")}


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
