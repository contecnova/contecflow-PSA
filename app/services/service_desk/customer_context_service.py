from datetime import timezone

from sqlalchemy.orm import Session

from app.models.service_desk import Ticket
import logging

logger = logging.getLogger(__name__)


def get_customer_context_payload(db: Session, requester_id: str) -> dict:
    recent_tickets = db.query(Ticket).filter(
        Ticket.requester_user_id == requester_id
    ).order_by(Ticket.created_at.desc()).limit(10).all()

    open_tickets = [
        t for t in recent_tickets if t.status.value not in ("resolved", "closed", "cancelled")
    ]
    resolved = [t for t in recent_tickets if t.resolved_at]

    csat_scores = [t.csat_score for t in recent_tickets if t.csat_score]
    avg_csat = round(sum(csat_scores) / len(csat_scores), 2) if csat_scores else None

    mttr = 0
    if resolved:
        def _norm(dt):
            return dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)

        mttr = round(
            sum((_norm(t.resolved_at) - _norm(t.created_at)).total_seconds() / 60 for t in resolved)
            / len(resolved),
            0,
        )

    return {
        "requester_id": requester_id,
        "open_tickets": len(open_tickets),
        "total_tickets_30d": len(recent_tickets),
        "avg_csat": avg_csat,
        "mttr_minutes": mttr,
        "recent_tickets": [
            {
                "id": t.id,
                "number": t.number,
                "title": t.title,
                "status": t.status.value,
                "priority": t.priority.value,
                "created_at": str(t.created_at),
            }
            for t in recent_tickets[:5]
        ],
    }
