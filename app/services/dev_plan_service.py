"""Development plans — plan de acción que sigue al 360°.

Quién puede crear/editar:
  - El subject (la persona que tiene el plan)
  - Su manager directo (subject.manager_id)
  - Admin / HR
"""
from __future__ import annotations
from datetime import datetime, timezone
import logging
import uuid as _uuid

from sqlalchemy.orm import Session, joinedload

from app.models.performance import (
    DevelopmentPlan, DevGoal, DevPlanStatus, DevGoalStatus,
)
from app.models.user import User

logger = logging.getLogger(__name__)


def can_edit_plan(*, current_user: User, plan: DevelopmentPlan, db: Session) -> bool:
    if getattr(current_user, "is_superadmin", False):
        return True
    if current_user.role in ("admin", "hr"):
        return True
    if current_user.id == plan.subject_id:
        return True
    subj = db.query(User).filter(User.id == plan.subject_id).first()
    if subj and subj.manager_id == current_user.id:
        return True
    return False


def can_view_plan(*, current_user: User, plan: DevelopmentPlan, db: Session) -> bool:
    # Misma regla que editar — los planes son privados al subject + managers + HR.
    return can_edit_plan(current_user=current_user, plan=plan, db=db)


def list_plans_for_subject(db: Session, subject_id: str) -> list[DevelopmentPlan]:
    return (
        db.query(DevelopmentPlan)
        .options(joinedload(DevelopmentPlan.goals))
        .filter(DevelopmentPlan.subject_id == subject_id)
        .order_by(DevelopmentPlan.created_at.desc())
        .all()
    )


def get_plan(db: Session, plan_id: str) -> DevelopmentPlan | None:
    return (
        db.query(DevelopmentPlan)
        .options(joinedload(DevelopmentPlan.goals))
        .filter(DevelopmentPlan.id == plan_id)
        .first()
    )


def create_plan(db: Session, *, subject_id: str, created_by: str,
                title: str, summary: str | None = None,
                campaign_id: str | None = None, cycle_id: str | None = None,
                target_date=None, next_review_at=None,
                organization_id: str | None = None,
                goals: list[dict] | None = None) -> DevelopmentPlan:
    """Crea un plan de desarrollo con sus objetivos.

    Auditoria 2026-08: ni el plan ni sus objetivos guardaban
    `organization_id`, y esa es la columna por la que filtra la guarda de
    tenant. Una fila NULL no la ve nadie salvo un superadmin, asi que el plan
    se creaba y desaparecia. Los objetivos la heredan del plan.
    """
    plan = DevelopmentPlan(
        id=str(_uuid.uuid4()),
        organization_id=organization_id,
        subject_id=subject_id, created_by=created_by,
        title=title, summary=summary,
        campaign_id=campaign_id, cycle_id=cycle_id,
        target_date=target_date, next_review_at=next_review_at,
    )
    db.add(plan)
    db.flush()
    for i, g in enumerate(goals or []):
        db.add(DevGoal(
            id=str(_uuid.uuid4()), plan_id=plan.id,
            organization_id=plan.organization_id,
            title=g["title"], description=g.get("description"),
            due_date=g.get("due_date"), order=g.get("order", i),
        ))
    db.commit()
    db.refresh(plan)
    return plan


def update_plan(db: Session, plan: DevelopmentPlan, updates: dict) -> DevelopmentPlan:
    # Whitelist de campos editables
    allowed = {"title", "summary", "status", "target_date", "next_review_at"}
    for k, v in updates.items():
        if k in allowed:
            setattr(plan, k, v)
    db.commit()
    db.refresh(plan)
    return plan


def add_goal(db: Session, plan: DevelopmentPlan, data: dict) -> DevGoal:
    order = data.get("order")
    if order is None:
        order = max((g.order for g in plan.goals), default=-1) + 1
    g = DevGoal(
        id=str(_uuid.uuid4()), plan_id=plan.id,
        organization_id=plan.organization_id,
        title=data["title"], description=data.get("description"),
        due_date=data.get("due_date"), order=order,
    )
    db.add(g)
    db.commit()
    db.refresh(g)
    return g


def update_goal(db: Session, goal: DevGoal, updates: dict) -> DevGoal:
    allowed = {"title", "description", "status", "due_date", "progress", "order"}
    prev_status = goal.status
    for k, v in updates.items():
        if k in allowed:
            setattr(goal, k, v)
    # Si pasa a done, fijamos completed_at y progress=100. Si retrocede, liberamos.
    if goal.status == DevGoalStatus.done and prev_status != DevGoalStatus.done:
        goal.completed_at = datetime.now(timezone.utc)
        goal.progress = 100
    elif goal.status != DevGoalStatus.done and prev_status == DevGoalStatus.done:
        goal.completed_at = None
    db.commit()
    db.refresh(goal)
    # Si todos los goals están done → marcamos el plan como completed
    plan = goal.plan
    if plan and plan.goals and all(g.status == DevGoalStatus.done for g in plan.goals):
        plan.status = DevPlanStatus.completed
        db.commit()
    return goal


def delete_goal(db: Session, goal: DevGoal) -> None:
    db.delete(goal)
    db.commit()


def serialize_plan(plan: DevelopmentPlan) -> dict:
    goals = sorted(plan.goals or [], key=lambda g: g.order)
    done_count = sum(1 for g in goals if g.status == DevGoalStatus.done)
    return {
        "id": plan.id, "subject_id": plan.subject_id,
        "subject_name": plan.subject.full_name if plan.subject else None,
        "campaign_id": plan.campaign_id,
        "cycle_id": plan.cycle_id,
        "cycle_name": plan.cycle.name if plan.cycle else None,
        "title": plan.title, "summary": plan.summary,
        "status": plan.status.value if hasattr(plan.status, "value") else plan.status,
        "target_date":    plan.target_date.isoformat()    if plan.target_date    else None,
        "next_review_at": plan.next_review_at.isoformat() if plan.next_review_at else None,
        "created_at": str(plan.created_at)[:16] if plan.created_at else None,
        "goals": [serialize_goal(g) for g in goals],
        "progress_pct": round(done_count / len(goals) * 100, 1) if goals else 0.0,
    }


def serialize_goal(g: DevGoal) -> dict:
    return {
        "id": g.id, "plan_id": g.plan_id,
        "title": g.title, "description": g.description,
        "status": g.status.value if hasattr(g.status, "value") else g.status,
        "due_date": g.due_date.isoformat() if g.due_date else None,
        "progress": g.progress, "order": g.order,
        "completed_at": str(g.completed_at)[:16] if g.completed_at else None,
    }
