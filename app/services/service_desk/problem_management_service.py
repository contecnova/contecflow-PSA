"""Problem Management service — ITSM-P08 (relational schema)

Thin orchestration layer for problem management operations. The real
business logic lives in `problem_service.py`; this module handles
operations that span multiple models (e.g. IncidentToProblem links).

Tables used:
  sd_problems              — Problem ORM model
  sd_incident_to_problem   — rich junction table (ITSM-P08)
  sd_known_errors          — proper KEDB relational table (ITSM-P08)
  sd_problem_rca_templates — template definitions (ITSM-P08)
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

from app.models.service_desk import IncidentToProblem, Problem, ProblemRcaTemplate, Ticket
from app.models.user import User
from app.schemas.service_desk import ProblemIn
from app.services.service_desk import problem_service


# ── Problem CRUD helpers ──────────────────────────────────────────────────────


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


# ── Incident <-> Problem linking (sd_incident_to_problem) ────────────────────


def link_incidents_to_problem(
    db: Session,
    *,
    problem_id: str,
    ticket_ids: list[str],
    current_user: User,
    is_causal: bool = False,
    notes: Optional[str] = None,
) -> dict:
    """Link one or more incident tickets to a Problem.

    Writes to the rich junction table sd_incident_to_problem AND keeps the
    bare Ticket.problem_id FK in sync for backwards compatibility.
    """
    problem = problem_service.get_scoped_problem_or_404(db, current_user, problem_id)
    linked = 0
    already_linked = 0
    for ticket_id in ticket_ids:
        ticket = db.query(Ticket).filter(Ticket.id == ticket_id).first()
        if not ticket:
            continue
        if ticket.problem_id != problem.id:
            ticket.problem_id = problem.id
        existing = (
            db.query(IncidentToProblem)
            .filter(
                IncidentToProblem.problem_id == problem.id,
                IncidentToProblem.ticket_id == ticket.id,
            )
            .first()
        )
        if existing:
            already_linked += 1
            continue
        link = IncidentToProblem(
            id=str(uuid.uuid4()),
            problem_id=problem.id,
            ticket_id=ticket.id,
            is_causal=is_causal,
            notes=notes,
            linked_by=current_user.id,
            linked_at=datetime.now(timezone.utc),
        )
        db.add(link)
        linked += 1
    db.flush()
    return {"problem_id": problem.id, "linked_count": linked, "already_linked": already_linked}


def get_linked_incidents(
    db: Session,
    *,
    problem_id: str,
    current_user: User,
) -> list[dict]:
    """Return all incidents linked to a problem, with junction metadata."""
    problem = problem_service.get_scoped_problem_or_404(db, current_user, problem_id)
    links = (
        db.query(IncidentToProblem)
        .filter(IncidentToProblem.problem_id == problem.id)
        .order_by(IncidentToProblem.linked_at.desc())
        .all()
    )
    result = []
    for lnk in links:
        t = lnk.ticket
        if not t:
            continue
        result.append(
            {
                "id": t.id,
                "number": t.number,
                "title": t.title,
                "status": str(t.status),
                "priority": str(t.priority),
                "ci_id": t.ci_id,
                "created_at": t.created_at.isoformat() if t.created_at else None,
                "is_causal": lnk.is_causal,
                "notes": lnk.notes,
                "linked_by": lnk.linked_by,
                "linked_at": lnk.linked_at.isoformat() if lnk.linked_at else None,
            }
        )
    return result


# ── Known Error DB (sd_known_errors) ─────────────────────────────────────────


# ── RCA Template management (sd_problem_rca_templates) ───────────────────────


def get_rca_template(db: Session, *, template_id: str) -> Optional[ProblemRcaTemplate]:
    return db.query(ProblemRcaTemplate).filter(ProblemRcaTemplate.id == template_id).first()


def create_rca_template(
    db: Session,
    *,
    current_user: User,
    name: str,
    template_type: str,
    steps_json: str,
    description: Optional[str] = None,
    is_system: bool = False,
) -> ProblemRcaTemplate:
    tpl = ProblemRcaTemplate(
        id=str(uuid.uuid4()),
        name=name,
        template_type=template_type,
        steps_json=steps_json,
        description=description,
        is_system=is_system,
        is_active=True,
        created_by=current_user.id,
    )
    db.add(tpl)
    db.flush()
    return tpl


# ── Problem -> Change ─────────────────────────────────────────────────────────


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
