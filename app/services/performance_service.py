"""Service layer for Performance Reviews."""
from sqlalchemy.orm import Session, joinedload
from datetime import datetime, timezone
import uuid as _uuid

from app.models.performance import ReviewCycle, PerformanceReview, ReviewCycleStatus, ReviewStatus


def list_cycles(db: Session):
    return db.query(ReviewCycle).order_by(ReviewCycle.created_at.desc()).all()


def create_cycle(db: Session, created_by: str, **kwargs) -> ReviewCycle:
    c = ReviewCycle(id=str(_uuid.uuid4()), created_by=created_by, **kwargs)
    db.add(c)
    db.commit()
    db.refresh(c)
    return c


def get_cycle(db: Session, cycle_id: str):
    return db.query(ReviewCycle).filter(ReviewCycle.id == cycle_id).first()


def activate_cycle(db: Session, c: ReviewCycle) -> ReviewCycle:
    c.status = ReviewCycleStatus.active
    db.commit()
    return c


def close_cycle(db: Session, c: ReviewCycle) -> ReviewCycle:
    c.status = ReviewCycleStatus.closed
    db.commit()
    return c


def list_cycle_reviews(db: Session, cycle_id: str):
    return (
        db.query(PerformanceReview)
        .options(joinedload(PerformanceReview.reviewee), joinedload(PerformanceReview.reviewer))
        .filter(PerformanceReview.cycle_id == cycle_id)
        .all()
    )


def list_my_pending_reviews(db: Session, reviewer_id: str):
    return (
        db.query(PerformanceReview)
        .options(joinedload(PerformanceReview.reviewee), joinedload(PerformanceReview.reviewer))
        .filter(
            PerformanceReview.reviewer_id == reviewer_id,
            PerformanceReview.status == ReviewStatus.pending,
        )
        .all()
    )


def create_review(db: Session, cycle_id: str, reviewee_id: str, reviewer_id: str,
                  review_type: str = "peer") -> PerformanceReview:
    r = PerformanceReview(
        id=str(_uuid.uuid4()),
        cycle_id=cycle_id,
        reviewee_id=reviewee_id,
        reviewer_id=reviewer_id,
        review_type=review_type,
    )
    db.add(r)
    db.commit()
    return r


def get_review(db: Session, review_id: str):
    return db.query(PerformanceReview).filter(PerformanceReview.id == review_id).first()


def save_review(db: Session, r: PerformanceReview, updates: dict) -> PerformanceReview:
    for k, v in updates.items():
        setattr(r, k, v)
    db.commit()
    db.refresh(r)
    return r


def submit_review(db: Session, r: PerformanceReview) -> PerformanceReview:
    r.status = ReviewStatus.submitted
    r.submitted_at = datetime.now(timezone.utc)
    db.commit()
    return r


def get_user_review_history(db: Session, user_id: str):
    return (
        db.query(PerformanceReview)
        .options(joinedload(PerformanceReview.reviewer))
        .filter(
            PerformanceReview.reviewee_id == user_id,
            PerformanceReview.status == ReviewStatus.submitted,
        )
        .order_by(PerformanceReview.submitted_at.desc())
        .all()
    )


# ── Serialization helpers ─────────────────────────────────────────────────────

def avg_score(*scores) -> object:
    """Return the rounded mean of non-None score values, or None."""
    vals = [s for s in scores if s is not None]
    return round(sum(vals) / len(vals), 2) if vals else None


def serialize_review(r) -> dict:
    return {
        "id": r.id, "cycle_id": r.cycle_id,
        "reviewee_id": r.reviewee_id,
        "reviewee_name": r.reviewee.full_name if r.reviewee else None,
        "reviewer_id": r.reviewer_id,
        "reviewer_name": r.reviewer.full_name if r.reviewer else None,
        "review_type": r.review_type, "status": r.status,
        "score_quality": r.score_quality, "score_delivery": r.score_delivery,
        "score_teamwork": r.score_teamwork, "score_leadership": r.score_leadership,
        "score_innovation": r.score_innovation,
        "score_overall": r.score_overall or avg_score(
            r.score_quality, r.score_delivery, r.score_teamwork,
            r.score_leadership, r.score_innovation,
        ),
        "strengths": r.strengths, "improvements": r.improvements,
        "goals_next": r.goals_next,
        "submitted_at": str(r.submitted_at)[:16] if r.submitted_at else None,
    }
