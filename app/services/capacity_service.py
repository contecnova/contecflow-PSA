from __future__ import annotations

from datetime import date, timedelta
from typing import List, Optional

from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload

from app.models.financial import CapacityPlan
from app.models.imputation import Imputation
from app.models.project import Project
from app.models.user import User, UserStatus


# ── User helpers ─────────────────────────────────────────────────────────────

def get_active_users(
    db: Session,
    organization_id: Optional[str] = None,
) -> List[User]:
    q = db.query(User).filter(
        User.is_active == True,
        User.status == UserStatus.active,
    )
    if organization_id:
        q = q.filter(User.organization_id == organization_id)
    return q.order_by(User.full_name).all()


# ── CapacityPlan helpers ──────────────────────────────────────────────────────

def get_plans_for_period(
    db: Session,
    week_from: date,
    week_to: date,
    user_ids: List,
) -> List[CapacityPlan]:
    return db.query(CapacityPlan).filter(
        CapacityPlan.week_start >= week_from,
        CapacityPlan.week_start <= week_to,
        CapacityPlan.user_id.in_(user_ids),
    ).all()


def get_actual_hours_by_week(
    db: Session,
    date_from: date,
    date_to: date,
):
    """Return rows of (user_id, week_label, hours) for the given date range."""
    from app.db.session import is_postgres

    if is_postgres():
        week_expr = func.date_trunc("week", Imputation.date)
    else:
        week_expr = func.strftime("%Y-%W", Imputation.date)

    return db.query(
        Imputation.user_id,
        week_expr.label("week"),
        func.sum(Imputation.hours).label("hours"),
    ).filter(
        Imputation.date >= date_from,
        Imputation.date <= date_to,
    ).group_by(Imputation.user_id, week_expr).all()


def list_capacity_plans(
    db: Session,
    user_id: Optional[str] = None,
    project_id: Optional[str] = None,
    week_from: Optional[date] = None,
    week_to: Optional[date] = None,
) -> List[CapacityPlan]:
    q = db.query(CapacityPlan).options(
        joinedload(CapacityPlan.user),
        joinedload(CapacityPlan.project),
    )
    if user_id:
        q = q.filter(CapacityPlan.user_id == user_id)
    if project_id:
        q = q.filter(CapacityPlan.project_id == project_id)
    if week_from:
        q = q.filter(CapacityPlan.week_start >= week_from)
    if week_to:
        q = q.filter(CapacityPlan.week_start <= week_to)
    return q.order_by(CapacityPlan.week_start, CapacityPlan.user_id).all()


def get_plans_board(
    db: Session,
    week_from: Optional[date] = None,
    week_to: Optional[date] = None,
) -> List[CapacityPlan]:
    q = db.query(CapacityPlan)
    if week_from:
        q = q.filter(CapacityPlan.week_start >= week_from)
    if week_to:
        q = q.filter(CapacityPlan.week_start <= week_to)
    return q.order_by(CapacityPlan.week_start, CapacityPlan.user_id).all()


def get_project_names(db: Session, project_ids: set) -> dict:
    if not project_ids:
        return {}
    return {
        str(p.id): p.name
        for p in db.query(Project).filter(Project.id.in_(project_ids)).all()
    }


def get_capacity_plan_by_id(db: Session, plan_id: str) -> Optional[CapacityPlan]:
    return db.query(CapacityPlan).filter(CapacityPlan.id == plan_id).first()


def update_capacity_plan(db: Session, plan: CapacityPlan, payload: dict) -> CapacityPlan:
    allowed = ["user_id", "project_id", "week_start", "planned_hours", "notes"]
    for k, v in payload.items():
        if k in allowed:
            if k == "week_start" and isinstance(v, str):
                v = date.fromisoformat(v)
            setattr(plan, k, v)
    db.commit()
    return plan


def delete_capacity_plan(db: Session, plan: CapacityPlan) -> None:
    db.delete(plan)
    db.commit()


def get_plans_for_leveling(
    db: Session,
    week_from: date,
    week_to: date,
    user_ids: List,
) -> List[CapacityPlan]:
    return db.query(CapacityPlan).filter(
        CapacityPlan.week_start >= week_from,
        CapacityPlan.week_start <= week_to,
        CapacityPlan.user_id.in_(user_ids),
    ).all()
