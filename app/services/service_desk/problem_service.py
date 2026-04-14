from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy.orm import Session, joinedload

from app.models.project import Project
from app.models.service_desk import Problem, Ticket
from app.models.user import User
from app.schemas.service_desk import ProblemIn, ProblemUpdateIn
from app.services.service_desk.scoping import (
    scope_problem_query as _scope_problem_query,
    scope_ticket_query as _scope_ticket_query,
)
from app.services.sla_service import next_problem_number as _next_problem_number


def list_problems_payload(db: Session, current_user: User, page: int, page_size: int) -> list[dict]:
    q = db.query(Problem).options(
        joinedload(Problem.ci),
        joinedload(Problem.owner),
        joinedload(Problem.related_tickets),
    )
    q = _scope_problem_query(q, db, current_user)
    problems = (
        q.order_by(Problem.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return [
        {
            "id": p.id,
            "number": p.number,
            "title": p.title,
            "description": p.description,
            "status": p.status,
            "priority": p.priority,
            "root_cause": p.root_cause,
            "workaround": p.workaround,
            "ci_name": p.ci.name if p.ci else None,
            "owner_name": p.owner.full_name if p.owner else None,
            "related_ticket_count": len(p.related_tickets),
            "created_at": str(p.created_at)[:10],
            "resolved_at": str(p.resolved_at)[:10] if p.resolved_at else None,
        }
        for p in problems
    ]


def _validate_problem_org_constraints(db: Session, current_user: User, project_id: str = None, owner_user_id: str = None, *, update: bool = False) -> None:
    if current_user.is_superadmin or not current_user.organization_id:
        return

    if project_id:
        project = db.query(Project).filter(
            Project.id == project_id,
            Project.organization_id == current_user.organization_id,
        ).first()
        if not project:
            if update:
                raise HTTPException(403, "No puedes mover problemas fuera de tu organización")
            raise HTTPException(403, "No puedes crear problemas para proyectos fuera de tu organización")

    if owner_user_id:
        owner = db.query(User).filter(User.id == owner_user_id).first()
        if not owner or owner.organization_id != current_user.organization_id:
            raise HTTPException(403, "No puedes asignar un owner fuera de tu organización")


def create_problem_record(db: Session, current_user: User, payload: ProblemIn) -> Problem:
    _validate_problem_org_constraints(
        db,
        current_user,
        project_id=payload.project_id,
        owner_user_id=payload.owner_user_id,
        update=False,
    )
    problem = Problem(number=_next_problem_number(db), **payload.model_dump())
    db.add(problem)
    return problem


def get_scoped_problem_or_404(db: Session, current_user: User, problem_id: str) -> Problem:
    problem = _scope_problem_query(db.query(Problem), db, current_user).filter(Problem.id == problem_id).first()
    if not problem:
        raise HTTPException(404)
    return problem


def apply_problem_update(db: Session, current_user: User, problem: Problem, payload: ProblemUpdateIn) -> None:
    _validate_problem_org_constraints(
        db,
        current_user,
        project_id=payload.project_id,
        owner_user_id=payload.owner_user_id,
        update=True,
    )
    for k, v in payload.model_dump(exclude_unset=True).items():
        setattr(problem, k, v)
    if payload.status in ["resolved", "closed"]:
        problem.resolved_at = datetime.now(timezone.utc)


def link_ticket_to_problem_record(db: Session, current_user: User, problem_id: str, ticket_id: str) -> None:
    problem = get_scoped_problem_or_404(db, current_user, problem_id)
    ticket = _scope_ticket_query(db.query(Ticket), db, current_user).filter(Ticket.id == ticket_id).first()
    if not ticket:
        raise HTTPException(404)
    ticket.problem_id = problem.id
