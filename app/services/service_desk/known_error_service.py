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

import json
import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy.orm import Session, joinedload

from app.models.service_desk import (
    KBArticle,
    KBStatus,
    Problem,
    ProblemStatus,
    Ticket,
    TicketStatus,
)

_logger = logging.getLogger(__name__)

# Days until a KEDB entry should be reviewed after publication
KEDB_DEFAULT_REVIEW_DAYS = 90


# ── Query helpers ─────────────────────────────────────────────────────────────


def get_known_errors(db: Session) -> list[Problem]:
    """Return all active KEDB entries (status=known_error with workaround)."""
    return (
        db.query(Problem)
        .options(joinedload(Problem.ci), joinedload(Problem.related_tickets))
        .filter(
            Problem.status == ProblemStatus.known_error,
            Problem.workaround.isnot(None),
        )
        .order_by(Problem.kedb_published_at.desc().nullslast(), Problem.created_at.desc())
        .all()
    )


def get_expiring_known_errors(db: Session, within_days: int = 7) -> list[Problem]:
    """Return KEDB entries whose review date falls within the next N days."""
    now = datetime.now(timezone.utc)
    deadline = now + timedelta(days=within_days)
    return (
        db.query(Problem)
        .filter(
            Problem.status == ProblemStatus.known_error,
            Problem.kedb_expires_at.isnot(None),
            Problem.kedb_expires_at <= deadline,
            Problem.kedb_expires_at >= now,
        )
        .all()
    )


def serialize_known_error(problem: Problem) -> dict:
    """Serialize a KEDB entry for API responses."""
    tickets = problem.related_tickets or []
    return {
        "id": problem.id,
        "number": problem.number,
        "title": problem.title,
        "description": problem.description,
        "workaround": problem.workaround,
        "root_cause": problem.root_cause,
        "rca_type": problem.rca_type,
        "rca_evidence": problem.rca_evidence,
        "rca_approved_at": problem.rca_approved_at.isoformat() if problem.rca_approved_at else None,
        "ci": problem.ci.name if problem.ci else None,
        "ci_id": problem.ci_id,
        "priority": problem.priority.value if problem.priority else None,
        "affected_tickets": len(tickets),
        "kedb_published_at": problem.kedb_published_at.isoformat() if problem.kedb_published_at else None,
        "kedb_expires_at": problem.kedb_expires_at.isoformat() if problem.kedb_expires_at else None,
        "kedb_reviewed_at": problem.kedb_reviewed_at.isoformat() if problem.kedb_reviewed_at else None,
        "kedb_effectiveness_score": problem.kedb_effectiveness_score,
        "kb_article_id": problem.kb_article_id,
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

    db.flush()
    _logger.info("Problem %s promoted to Known Error (KEDB)", problem.number)
    return serialize_known_error(problem)


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
    tickets: list[Ticket] = problem.related_tickets or []
    if not tickets:
        return 0.0

    published = problem.kedb_published_at
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
    for problem in known_errors:
        try:
            score = recompute_effectiveness(db, problem)
            updated.append({"number": problem.number, "score": score})
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
        db.query(Problem)
        .filter(
            Problem.status == ProblemStatus.known_error,
            Problem.kedb_expires_at.isnot(None),
            Problem.kedb_expires_at < now,
        )
        .all()
    )
    results = []
    for problem in expired:
        try:
            problem.status = ProblemStatus.investigating
            results.append({
                "number": problem.number,
                "expired_at": problem.kedb_expires_at.isoformat() if problem.kedb_expires_at else None,
            })
        except Exception as exc:
            _logger.warning("KEDB expiry: could not demote Problem %s: %s", problem.number, exc)

    if results:
        db.flush()
    _logger.info("KEDB expiry scan: %d entries expired and demoted to investigating", len(results))
    return {"expired": len(results), "entries": results}


# ── Stats ─────────────────────────────────────────────────────────────────────


def get_kedb_stats(db: Session) -> dict:
    """Return aggregate KEDB statistics for dashboards."""
    known_errors = get_known_errors(db)
    expiring = get_expiring_known_errors(db, within_days=30)

    scores = [p.kedb_effectiveness_score for p in known_errors if p.kedb_effectiveness_score is not None]
    avg_effectiveness = round(sum(scores) / len(scores), 1) if scores else None

    return {
        "total_known_errors": len(known_errors),
        "expiring_within_30d": len(expiring),
        "avg_effectiveness_score": avg_effectiveness,
        "with_kb_article": sum(1 for p in known_errors if p.kb_article_id),
        "with_approved_rca": sum(1 for p in known_errors if p.rca_approved_at),
    }
