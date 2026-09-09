"""
Known Error Database (KEDB) service — ITSM-P02
===============================================
Lifecycle management for Known Errors:
  1. Promote a Problem to a Known Error (publish to KEDB)
  2. Track effectiveness: % of linked tickets resolved via workaround
  3. Review / refresh expiring KEDB entries
  4. Auto-generate KB article when promoting to KEDB
  5. Expire stale entries and flag them for re-review
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy.orm import Session, joinedload

from app.models.service_desk import (
    IncidentToProblem,
    KBArticle,
    KBStatus,
    KnownError,
    KnownErrorTicket,
    Problem,
    ProblemStatus,
    TicketStatus,
)

_logger = logging.getLogger(__name__)

# Days until a KEDB entry should be reviewed after publication
KEDB_DEFAULT_REVIEW_DAYS = 90


# ── Query helpers ─────────────────────────────────────────────────────────────


def tickets_de_un_error_conocido(db, current_user, known_error_id: str) -> list[dict]:
    """Los tickets vinculados a un Known Error del KEDB.

    Auditoria 2026-08 (hallazgo 37). `GET /sd/known-errors/{id}/tickets` **no
    existia** y la interfaz lo llamaba. El modelo si estaba: la tabla de union
    `sd_known_error_tickets` lleva `known_error_id` y `ticket_id`.

    La consulta de los tickets no lleva filtro de organizacion y es correcto: se
    parte de un Known Error ya verificado como propio, y los enlaces cuelgan de
    el, asi que el ambito llega por la clave padre.
    """
    from app.models.service_desk import KnownErrorTicket, Ticket
    from app.services.service_desk.problem_service import (
        get_scoped_problem_or_404,
    )

    # Un Known Error es un `Problem` promovido, asi que la guarda es la del
    # problema — la misma que usan el PATCH y el resto del modulo.
    get_scoped_problem_or_404(db, current_user, known_error_id)

    enlaces = (
        db.query(KnownErrorTicket)
        .filter(KnownErrorTicket.known_error_id == known_error_id)
        .all()
    )
    ids = [e.ticket_id for e in enlaces if e.ticket_id]
    if not ids:
        return []

    tickets = db.query(Ticket).filter(Ticket.id.in_(ids)).all()
    return [
        {
            "id": t.id,
            "number": t.number,
            "title": t.title,
            "status": str(getattr(t, "status", "") or ""),
            "priority": str(getattr(t, "priority", "") or ""),
            "created_at": str(t.created_at)[:19] if t.created_at else None,
        }
        for t in tickets
    ]


def get_known_errors(db: Session) -> list[KnownError]:
    """Return all active KEDB entries from the relational KnownError table."""
    return (
        db.query(KnownError)
        .options(
            joinedload(KnownError.problem).joinedload(Problem.ci),
            joinedload(KnownError.affected_ticket_links).joinedload(KnownErrorTicket.ticket),
        )
        .filter(KnownError.is_active.is_(True))
        .order_by(KnownError.published_at.desc().nullslast(), KnownError.created_at.desc())
        .all()
    )


def get_expiring_known_errors(db: Session, within_days: int = 7) -> list[KnownError]:
    """Return active KEDB entries whose review date falls within the next N days."""
    now = datetime.now(timezone.utc)
    deadline = now + timedelta(days=within_days)
    return (
        db.query(KnownError)
        .filter(
            KnownError.is_active.is_(True),
            KnownError.expires_at.isnot(None),
            KnownError.expires_at <= deadline,
            KnownError.expires_at >= now,
        )
        .all()
    )


def _ensure_known_error_ticket_links(db: Session, known_error: KnownError) -> int:
    """Sync KnownErrorTicket rows from IncidentToProblem links for same problem."""
    links = (
        db.query(IncidentToProblem)
        .filter(IncidentToProblem.problem_id == known_error.problem_id)
        .all()
    )
    created = 0
    for lnk in links:
        exists = (
            db.query(KnownErrorTicket)
            .filter(
                KnownErrorTicket.known_error_id == known_error.id,
                KnownErrorTicket.ticket_id == lnk.ticket_id,
            )
            .first()
        )
        if exists:
            continue
        db.add(
            KnownErrorTicket(
                id=str(uuid.uuid4()),
                known_error_id=known_error.id,
                ticket_id=lnk.ticket_id,
                incident_link_id=lnk.id,
            )
        )
        created += 1
    if created:
        db.flush()
    return created


def serialize_known_error(known_error: KnownError) -> dict:
    """Serialize a relational KEDB entry for API responses."""
    problem = known_error.problem
    links = known_error.affected_ticket_links or []
    return {
        "id": known_error.id,
        "problem_id": problem.id if problem else known_error.problem_id,
        "number": problem.number if problem else None,
        "title": known_error.title,
        "description": known_error.description,
        "workaround": known_error.workaround,
        "root_cause": known_error.root_cause,
        "rca_type": known_error.rca_type,
        "rca_evidence": problem.rca_evidence if problem else None,
        "rca_approved_at": problem.rca_approved_at.isoformat() if problem and problem.rca_approved_at else None,
        "ci": problem.ci.name if problem and problem.ci else None,
        "ci_id": problem.ci_id if problem else None,
        "priority": problem.priority.value if problem and problem.priority else None,
        "affected_tickets": len(links),
        "affected_ticket_ids": [lnk.ticket_id for lnk in links],
        "kedb_published_at": known_error.published_at.isoformat() if known_error.published_at else None,
        "kedb_expires_at": known_error.expires_at.isoformat() if known_error.expires_at else None,
        "kedb_reviewed_at": known_error.reviewed_at.isoformat() if known_error.reviewed_at else None,
        "kedb_effectiveness_score": known_error.effectiveness_score,
        "kb_article_id": known_error.kb_article_id,
        "is_active": known_error.is_active,
    }


# ── Promote to KEDB ───────────────────────────────────────────────────────────


def promote_to_known_error(
    db: Session,
    problem: Problem,
    *,
    workaround: Optional[str] = None,
    review_days: int = KEDB_DEFAULT_REVIEW_DAYS,
    auto_kb: bool = True,
) -> dict:
    """
    Promote a Problem to a Known Error in the KEDB.

    - Sets status → known_error
    - Stamps kedb_published_at, kedb_expires_at
    - Optionally creates a KB article from the workaround

    Returns serialized KEDB entry dict.
    """
    if not problem.workaround and not workaround:
        raise ValueError("A workaround is required to promote a problem to Known Error")

    if workaround:
        problem.workaround = workaround

    now = datetime.now(timezone.utc)
    problem.status = ProblemStatus.known_error
    problem.kedb_published_at = now
    problem.kedb_expires_at = now + timedelta(days=review_days)

    # Auto-generate KB article
    if auto_kb and not problem.kb_article_id:
        kb_article = _create_kb_article_from_problem(db, problem)
        if kb_article:
            problem.kb_article_id = kb_article.id

    known_error = (
        db.query(KnownError)
        .filter(KnownError.problem_id == problem.id, KnownError.is_active.is_(True))
        .order_by(KnownError.published_at.desc().nullslast())
        .first()
    )
    if not known_error:
        known_error = KnownError(
            id=str(uuid.uuid4()),
            problem_id=problem.id,
            title=problem.title,
            description=problem.description,
            workaround=problem.workaround,
            root_cause=problem.root_cause,
            rca_type=problem.rca_type,
            category_id=None,
            published_by=problem.owner_user_id,
            published_at=now,
            expires_at=now + timedelta(days=review_days),
            reviewed_at=problem.kedb_reviewed_at,
            effectiveness_score=problem.kedb_effectiveness_score,
            kb_article_id=problem.kb_article_id,
            is_active=True,
        )
        db.add(known_error)
    else:
        known_error.title = problem.title
        known_error.description = problem.description
        known_error.workaround = problem.workaround
        known_error.root_cause = problem.root_cause
        known_error.rca_type = problem.rca_type
        known_error.published_at = now
        known_error.expires_at = now + timedelta(days=review_days)
        known_error.kb_article_id = problem.kb_article_id

    db.flush()
    _ensure_known_error_ticket_links(db, known_error)

    db.flush()
    _logger.info("Problem %s promoted to Known Error (KEDB)", problem.number)
    return serialize_known_error(known_error)


def _create_kb_article_from_problem(db: Session, problem: Problem) -> Optional[KBArticle]:
    """Auto-generate a KB article from a Problem's workaround and RCA."""
    try:
        # Generate sequential KB number
        last = (
            db.query(KBArticle)
            .order_by(KBArticle.number.desc())
            .first()
        )
        if last and last.number and last.number.startswith("KB"):
            try:
                seq = int(last.number[2:]) + 1
            except ValueError:
                seq = 1
        else:
            seq = 1
        number = f"KB{seq:05d}"

        body_parts = []
        if problem.root_cause:
            body_parts.append(f"## Causa Raíz\n\n{problem.root_cause}")
        if problem.workaround:
            body_parts.append(f"## Solución / Workaround\n\n{problem.workaround}")
        if problem.fix_description:
            body_parts.append(f"## Corrección Permanente\n\n{problem.fix_description}")
        if problem.rca_evidence:
            body_parts.append(f"## Evidencia\n\n{problem.rca_evidence}")

        body = "\n\n".join(body_parts) or problem.description

        article = KBArticle(
            id=str(uuid.uuid4()),
            number=number,
            title=f"[Known Error] {problem.title}",
            body=body,
            summary=f"Workaround para: {problem.title[:200]}",
            status=KBStatus.published,
            is_public=True,
            created_from_ticket_id=None,
        )
        db.add(article)
        db.flush()
        _logger.info("KB article %s auto-created from Problem %s", number, problem.number)
        return article
    except Exception as exc:
        _logger.warning("Could not auto-create KB article for Problem %s: %s", problem.number, exc)
        return None


# ── RCA Approval ──────────────────────────────────────────────────────────────


def approve_rca(
    db: Session,
    problem: Problem,
    approver_user_id: str,
    *,
    evidence: Optional[str] = None,
) -> dict:
    """
    Approve the RCA for a Problem.

    Sets rca_approved_by, rca_approved_at.
    Optionally attaches evidence text/JSON.
    Returns updated problem summary.
    """
    now = datetime.now(timezone.utc)
    problem.rca_approved_by = approver_user_id
    problem.rca_approved_at = now
    if evidence is not None:
        problem.rca_evidence = evidence
    db.flush()
    _logger.info("RCA for Problem %s approved by user %s", problem.number, approver_user_id)
    return {
        "problem_id": problem.id,
        "problem_number": problem.number,
        "rca_approved_by": approver_user_id,
        "rca_approved_at": now.isoformat(),
    }


# ── Effectiveness tracking ────────────────────────────────────────────────────


def recompute_effectiveness(db: Session, problem: Problem) -> float:
    """
    Recompute the KEDB effectiveness score for a Known Error.

    Score = (resolved tickets) / (total linked tickets) * 100.
    Only counts tickets that were resolved AFTER the KEDB was published
    (proxy: resolved_at > kedb_published_at).

    Returns the score (0-100) and persists it to problem.kedb_effectiveness_score.
    """
    known_error = (
        db.query(KnownError)
        .options(joinedload(KnownError.affected_ticket_links).joinedload(KnownErrorTicket.ticket))
        .filter(KnownError.problem_id == problem.id, KnownError.is_active.is_(True))
        .order_by(KnownError.published_at.desc().nullslast())
        .first()
    )
    if not known_error:
        return 0.0

    _ensure_known_error_ticket_links(db, known_error)

    tickets = [lnk.ticket for lnk in (known_error.affected_ticket_links or []) if lnk.ticket is not None]
    if not tickets:
        return 0.0

    published = known_error.published_at
    relevant = [
        t for t in tickets
        if t.status in (TicketStatus.resolved, TicketStatus.closed)
        and (
            published is None
            or (t.resolved_at and (
                t.resolved_at.replace(tzinfo=timezone.utc) if t.resolved_at.tzinfo is None
                else t.resolved_at
            ) >= (published.replace(tzinfo=timezone.utc) if published.tzinfo is None else published))
        )
    ]

    score = round(len(relevant) / len(tickets) * 100, 1)
    known_error.effectiveness_score = score
    # Keep legacy column updated for backwards compatibility.
    problem.kedb_effectiveness_score = score
    db.flush()
    return score


def run_kedb_effectiveness_scan(db: Session) -> dict:
    """
    Batch job: recompute effectiveness score for all active KEDB entries.

    Returns: {updated: int, entries: [{number, score}]}
    """
    known_errors = get_known_errors(db)
    updated = []
    for known_error in known_errors:
        problem = known_error.problem
        if not problem:
            continue
        try:
            score = recompute_effectiveness(db, problem)
            updated.append({"number": problem.number, "known_error_id": known_error.id, "score": score})
        except Exception as exc:
            _logger.warning("Effectiveness scan failed for Problem %s: %s", problem.number, exc)
    _logger.info("KEDB effectiveness scan: %d entries updated", len(updated))
    return {"updated": len(updated), "entries": updated}


# ── Review / expiry ───────────────────────────────────────────────────────────


def mark_kedb_reviewed(
    db: Session,
    problem: Problem,
    *,
    extend_days: int = KEDB_DEFAULT_REVIEW_DAYS,
) -> dict:
    """
    Record a manual review of a KEDB entry and extend the review window.

    Returns updated expiry information.
    """
    now = datetime.now(timezone.utc)
    problem.kedb_reviewed_at = now
    problem.kedb_expires_at = now + timedelta(days=extend_days)

    known_error = (
        db.query(KnownError)
        .filter(KnownError.problem_id == problem.id, KnownError.is_active.is_(True))
        .order_by(KnownError.published_at.desc().nullslast())
        .first()
    )
    if known_error:
        known_error.reviewed_at = now
        known_error.expires_at = now + timedelta(days=extend_days)

    db.flush()
    return {
        "problem_id": problem.id,
        "kedb_reviewed_at": now.isoformat(),
        "kedb_expires_at": problem.kedb_expires_at.isoformat(),
    }


def run_kedb_expiry_scan(db: Session) -> dict:
    """
    Batch job: identify KEDB entries past their review date and flag them.

    Entries past kedb_expires_at are demoted back to 'investigating' status
    so they get re-reviewed before re-publishing.

    Returns: {expired: int, entries: [{number, expired_at}]}
    """
    now = datetime.now(timezone.utc)
    expired = (
        db.query(KnownError)
        .options(joinedload(KnownError.problem))
        .filter(
            KnownError.is_active.is_(True),
            KnownError.expires_at.isnot(None),
            KnownError.expires_at < now,
        )
        .all()
    )
    results = []
    for known_error in expired:
        problem = known_error.problem
        try:
            known_error.is_active = False
            if problem:
                problem.status = ProblemStatus.investigating
            results.append({
                "known_error_id": known_error.id,
                "number": problem.number if problem else None,
                "expired_at": known_error.expires_at.isoformat() if known_error.expires_at else None,
            })
        except Exception as exc:
            _logger.warning("KEDB expiry: could not demote KnownError %s: %s", known_error.id, exc)

    if results:
        db.flush()
    _logger.info("KEDB expiry scan: %d entries expired and demoted to investigating", len(results))
    return {"expired": len(results), "entries": results}


# ── Stats ─────────────────────────────────────────────────────────────────────


def get_kedb_stats(db: Session) -> dict:
    """Return aggregate KEDB statistics for dashboards."""
    known_errors = get_known_errors(db)
    expiring = get_expiring_known_errors(db, within_days=30)

    scores = [k.effectiveness_score for k in known_errors if k.effectiveness_score is not None]
    avg_effectiveness = round(sum(scores) / len(scores), 1) if scores else None

    return {
        "total_known_errors": len(known_errors),
        "expiring_within_30d": len(expiring),
        "avg_effectiveness_score": avg_effectiveness,
        "with_kb_article": sum(1 for k in known_errors if k.kb_article_id),
        "with_approved_rca": sum(1 for k in known_errors if k.problem and k.problem.rca_approved_at),
    }
