from datetime import date
from typing import Optional

from sqlalchemy.orm import Session, joinedload

from app.models.resources import Deliverable, DeliverableStatus
from app.services.numbering import next_numbered_code
import logging

logger = logging.getLogger(__name__)


def _next_code(db: Session) -> str:
    return next_numbered_code(db, "deliverable", prefix="DEL", padding=3)


def list_all_deliverables(db: Session, limit: int = 500, offset: int = 0) -> list[Deliverable]:
    return (
        db.query(Deliverable)
        .options(joinedload(Deliverable.owner), joinedload(Deliverable.project))
        .filter(Deliverable.status.notin_(["accepted"]), Deliverable.is_active == True)
        .order_by(Deliverable.planned_date)
        .offset(offset)
        .limit(limit)
        .all()
    )


def list_project_deliverables(
    db: Session, project_id: str, status: Optional[str] = None
) -> list[Deliverable]:
    q = (
        db.query(Deliverable)
        .options(joinedload(Deliverable.owner))
        .filter(Deliverable.project_id == project_id, Deliverable.is_active == True)
    )
    if status:
        q = q.filter(Deliverable.status == status)
    return q.order_by(Deliverable.sort_order, Deliverable.planned_date).all()


def get_deliverable(db: Session, del_id: str, project_id: Optional[str] = None) -> Optional[Deliverable]:
    q = db.query(Deliverable).filter(Deliverable.id == del_id, Deliverable.is_active == True)
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
    """Soft-delete a deliverable."""
    d.is_active = False
    db.commit()


# ── Status labels ─────────────────────────────────────────────────────────────

STATUS_CFG = {
    "planned":     {"label": "Planificado",  "color": "#7a8aaa", "icon": "📋"},
    "in_progress": {"label": "En curso",     "color": "#00d4ff", "icon": "🔄"},
    "in_review":   {"label": "En revisión",  "color": "#ffb800", "icon": "👁"},
    "delivered":   {"label": "Entregado",    "color": "#7c3aed", "icon": "📤"},
    "accepted":    {"label": "Aceptado",     "color": "#00e5a0", "icon": "✅"},
    "rejected":    {"label": "Rechazado",    "color": "#ff4757", "icon": "❌"},
}


# ── Serialization helper ──────────────────────────────────────────────────

def serialize_deliverable(d) -> dict:
    cfg = STATUS_CFG.get(d.status, STATUS_CFG["planned"])
    on_time = None
    if d.planned_date and d.delivered_date:
        on_time = d.delivered_date <= d.planned_date
    elif d.planned_date and d.status not in ["delivered", "accepted"]:
        on_time = date.today() <= d.planned_date
    return {
        "id": d.id, "code": d.code, "project_id": d.project_id,
        "phase_id": d.phase_id, "name": d.name, "description": d.description,
        "format": d.format,
        "status": d.status,
        "status_label": cfg["label"],
        "status_color": cfg["color"],
        "status_icon": cfg["icon"],
        "planned_date": str(d.planned_date) if d.planned_date else None,
        "delivered_date": str(d.delivered_date) if d.delivered_date else None,
        "accepted_date": str(d.accepted_date) if d.accepted_date else None,
        "owner_id": d.owner_id,
        "owner_name": d.owner.full_name if d.owner else None,
        "client_contact": d.client_contact,
        "acceptance_criteria": d.acceptance_criteria,
        "rejection_reason": d.rejection_reason,
        "milestone_id": d.milestone_id,
        "document_url": d.document_url,
        "sort_order": d.sort_order,
        "on_time": on_time,
        "overdue": d.planned_date and date.today() > d.planned_date and d.status not in ["delivered", "accepted"],
    }
