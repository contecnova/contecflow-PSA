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
