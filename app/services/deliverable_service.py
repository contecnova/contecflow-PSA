from datetime import date
from typing import Optional

from sqlalchemy.orm import Session, joinedload

from app.models.resources import Deliverable, DeliverableStatus
from app.services.numbering import next_numbered_code


def _next_code(db: Session) -> str:
    return next_numbered_code(db, "deliverable", prefix="DEL", padding=3)


def list_all_deliverables(db: Session) -> list[Deliverable]:
    return (
        db.query(Deliverable)
        .options(joinedload(Deliverable.owner), joinedload(Deliverable.project))
        .filter(Deliverable.status.notin_(["accepted"]))
        .order_by(Deliverable.planned_date)
        .all()
    )


def list_project_deliverables(
    db: Session, project_id: str, status: Optional[str] = None
) -> list[Deliverable]:
    q = (
        db.query(Deliverable)
        .options(joinedload(Deliverable.owner))
        .filter(Deliverable.project_id == project_id)
    )
    if status:
        q = q.filter(Deliverable.status == status)
    return q.order_by(Deliverable.sort_order, Deliverable.planned_date).all()


def get_deliverable(db: Session, del_id: str, project_id: Optional[str] = None) -> Optional[Deliverable]:
    q = db.query(Deliverable).filter(Deliverable.id == del_id)
    if project_id is not None:
        q = q.filter(Deliverable.project_id == project_id)
    return q.first()


def create_deliverable(
    db: Session,
    project_id: str,
    **fields,
) -> Deliverable:
    d = Deliverable(
        project_id=project_id,
        code=_next_code(db),
        **fields,
    )
    db.add(d)
    db.commit()
    db.refresh(d)
    return d


def update_deliverable(db: Session, d: Deliverable, updates: dict) -> Deliverable:
    for k, v in updates.items():
        setattr(d, k, v)

    if updates.get("status") == "delivered" and not d.delivered_date:
        d.delivered_date = date.today()
    if updates.get("status") == "accepted" and not d.accepted_date:
        d.accepted_date = date.today()

    db.commit()
    db.refresh(d)
    return d


def mark_delivered(
    db: Session, d: Deliverable, document_url: Optional[str] = None
) -> Deliverable:
    d.status = DeliverableStatus.delivered
    d.delivered_date = date.today()
    if document_url:
        d.document_url = document_url
    db.commit()
    return d


def mark_accepted(db: Session, d: Deliverable) -> Deliverable:
    d.status = DeliverableStatus.accepted
    d.accepted_date = date.today()
    db.commit()
    return d


def mark_rejected(db: Session, d: Deliverable, reason: str) -> Deliverable:
    d.status = DeliverableStatus.rejected
    d.rejection_reason = reason
    db.commit()
    return d


def delete_deliverable(db: Session, d: Deliverable) -> None:
    db.delete(d)
    db.commit()
