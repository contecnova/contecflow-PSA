from __future__ import annotations

from typing import Optional

from sqlalchemy.orm import Session

from app.models.service_desk import Problem, Ticket
from app.models.user import User
from app.schemas.service_desk import ProblemIn
from app.services.service_desk import problem_service


def create_problem_from_correlation(
    db: Session,
    *,
    ticket_ids: list[str],
    category: str,
    priority: str,
    auto_rca: bool = True,
) -> Problem:
    return problem_service.create_problem_from_correlation(
        db,
        ticket_ids=ticket_ids,
        category=category,
        priority=priority,
        auto_rca=auto_rca,
    )


def create_problem(
    db: Session,
    *,
    current_user: User,
    payload: ProblemIn,
) -> Problem:
    return problem_service.create_problem_record(db, current_user, payload)


def suggest_root_cause(db: Session, *, problem: Problem) -> dict:
    return problem_service.suggest_rca_from_ai(db, problem)


def link_incidents_to_problem(
    db: Session,
    *,
    problem_id: str,
    ticket_ids: list[str],
    current_user: User,
) -> dict:
    problem = problem_service.get_scoped_problem_or_404(db, current_user, problem_id)
    linked = 0
    for ticket_id in ticket_ids:
        ticket = db.query(Ticket).filter(Ticket.id == ticket_id).first()
        if not ticket:
            continue
        ticket.problem_id = problem.id
        linked += 1
    return {"problem_id": problem.id, "linked_count": linked}


def get_linked_incidents(
    db: Session,
    *,
    problem_id: str,
    current_user: User,
) -> list[dict]:
    problem = problem_service.get_scoped_problem_or_404(db, current_user, problem_id)
    rows = db.query(Ticket).filter(Ticket.problem_id == problem.id).order_by(Ticket.created_at.desc()).all()
    return [
        {
            "id": t.id,
            "number": t.number,
            "title": t.title,
            "status": str(t.status),
            "priority": str(t.priority),
            "ci_id": t.ci_id,
            "created_at": t.created_at.isoformat() if t.created_at else None,
        }
        for t in rows
    ]


def close_problem_to_change(
    db: Session,
    *,
    problem_id: str,
    current_user: User,
    change_type: str = "normal",
    planned_start: Optional[str] = None,
    planned_end: Optional[str] = None,
) -> dict:
    return problem_service.create_change_from_problem(
        db,
        current_user=current_user,
        problem_id=problem_id,
        change_type=change_type,
        planned_start=planned_start,
        planned_end=planned_end,
    )
