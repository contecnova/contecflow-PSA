from __future__ import annotations

from datetime import date, timedelta
from typing import List, Optional

from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload

from app.models.financial import CapacityPlan
from app.models.imputation import Imputation
from app.models.project import Project
from app.models.user import User, UserStatus
from app.db.session import is_postgres
import logging

logger = logging.getLogger(__name__)


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
        CapacityPlan.is_active == True,
    ).all()


def get_actual_hours_by_week(
    db: Session,
    date_from: date,
    date_to: date,
    user_ids: Optional[List] = None,
):
    """Return rows of (user_id, week, hours) for the given date range.

    Baja (auditoría 22-11-2026): la semana (lunes, `date`) se calcula en Python
    a partir del día, igual en PostgreSQL y SQLite (antes `date_trunc` en uno y
    `strftime('%Y-%W')` en el otro: semanas distintas en cada base); solo
    imputaciones activas y, si se pasan, de esas personas (la empresa).
    """
    from collections import defaultdict
    from types import SimpleNamespace
    q = db.query(Imputation.user_id, Imputation.date, func.sum(Imputation.hours)).filter(
        Imputation.date >= date_from, Imputation.date <= date_to, Imputation.is_active.is_(True))
    if user_ids is not None:
        q = q.filter(Imputation.user_id.in_(list(user_ids) or [""]))
    por_semana: dict = defaultdict(float)
    for uid, dia, horas in q.group_by(Imputation.user_id, Imputation.date).all():
        por_semana[(uid, dia - timedelta(days=dia.weekday()))] += float(horas or 0)
    return [SimpleNamespace(user_id=uid, week=lunes, hours=h) for (uid, lunes), h in por_semana.items()]


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
    ).filter(CapacityPlan.is_active == True)
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
    q = db.query(CapacityPlan).filter(CapacityPlan.is_active == True)
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
    return db.query(CapacityPlan).filter(CapacityPlan.id == plan_id, CapacityPlan.is_active == True).first()


def update_capacity_plan(db: Session, plan: CapacityPlan, payload: dict) -> CapacityPlan:
    allowed = ["user_id", "project_id", "week_start", "planned_hours", "notes"]
    if any(k in payload for k in ("user_id", "week_start", "planned_hours")):
        from app.services.psa_flows import comprobar_plan_de_capacidad
        semana = payload.get("week_start", plan.week_start)
        if isinstance(semana, str):
            semana = date.fromisoformat(semana)
        comprobar_plan_de_capacidad(db, payload.get("user_id", plan.user_id), semana,
                                    float(payload.get("planned_hours", plan.planned_hours) or 0), excluir_id=plan.id)
    for k, v in payload.items():
        if k in allowed:
            if k == "week_start" and isinstance(v, str):
                v = date.fromisoformat(v)
            setattr(plan, k, v)
    db.commit()
    return plan


def delete_capacity_plan(db: Session, plan: CapacityPlan) -> None:
    plan.is_active = False
    db.commit()


# Baja (auditoría 22-11-2026, §5): `get_plans_for_leveling` (copia literal de
# `get_plans_for_period`, sin uso) retirada.


# ── Date helpers ──────────────────────────────────────────────────────────────

def get_weeks(from_date: date, num_weeks: int) -> List[date]:
    """Return a list of *num_weeks* Monday dates starting from the week of *from_date*."""
    monday = from_date - timedelta(days=from_date.weekday())
    return [monday + timedelta(weeks=i) for i in range(num_weeks)]
