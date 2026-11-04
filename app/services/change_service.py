from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session, joinedload

from app.models.resources import ChangeRequest, ChangeRequestStatus
from app.services.numbering import next_numbered_code
import logging

logger = logging.getLogger(__name__)


def _next_code(db: Session) -> str:
    return next_numbered_code(db, "change_request", prefix="CR", padding=3)


def get_all_pending(db: Session) -> list[ChangeRequest]:
    return (
        db.query(ChangeRequest)
        .options(
            joinedload(ChangeRequest.requester),
            joinedload(ChangeRequest.project),
        )
        .filter(ChangeRequest.status.in_(["submitted", "under_review"]))
        .filter(ChangeRequest.is_active == True)
        .order_by(ChangeRequest.created_at.desc())
        .all()
    )


def list_by_project(
    db: Session,
    project_id: str,
    status: Optional[str] = None,
) -> list[ChangeRequest]:
    q = (
        db.query(ChangeRequest)
        .options(
            joinedload(ChangeRequest.requester),
            joinedload(ChangeRequest.approver_user),
        )
        .filter(ChangeRequest.project_id == project_id)
        .filter(ChangeRequest.is_active == True)
    )
    if status:
        q = q.filter(ChangeRequest.status == status)
    return q.order_by(ChangeRequest.created_at.desc()).all()


def create_change_request(
    db: Session,
    project_id: str,
    requested_by: str,
    **fields,
) -> ChangeRequest:
    cr = ChangeRequest(
        project_id=project_id,
        code=_next_code(db),
        requested_by=requested_by,
        **fields,
    )
    db.add(cr)
    db.commit()
    db.refresh(cr)
    return cr


def get_by_id(db: Session, cr_id: str, project_id: Optional[str] = None) -> Optional[ChangeRequest]:
    q = db.query(ChangeRequest).filter(ChangeRequest.id == cr_id, ChangeRequest.is_active == True)
    if project_id is not None:
        q = q.filter(ChangeRequest.project_id == project_id)
    return q.first()


def update_change_request(db: Session, cr: ChangeRequest, **fields) -> ChangeRequest:
    for k, v in fields.items():
        setattr(cr, k, v)
    db.commit()
    db.refresh(cr)
    return cr


def submit_change_request(db: Session, cr: ChangeRequest) -> ChangeRequest:
    cr.status = ChangeRequestStatus.submitted
    cr.submitted_at = datetime.now(timezone.utc)
    db.commit()
    # Auditoria 2026-11: con flujo por defecto, a la bandeja de aprobaciones.
    from app.services.approval_engine import fuentes
    solicitante = cr.requested_by or getattr(db.info.get("current_user"), "id", None)
    if solicitante:
        fuentes.abrir(db, "change_request", cr.id, f"{cr.code} — {cr.title}", solicitante,
                      {"cost_impact": cr.cost_impact or 0, "schedule_impact_days": cr.schedule_impact_days or 0,
                       "impact": getattr(cr.impact, "value", cr.impact), "project_id": cr.project_id})
    return cr


def review_change_request(
    db: Session,
    cr: ChangeRequest,
    approved: bool,
    reviewer_id: str,
    resolution_notes: Optional[str] = None,
) -> ChangeRequest:
    cr.status = ChangeRequestStatus.approved if approved else ChangeRequestStatus.rejected
    cr.reviewed_by = reviewer_id
    cr.approved_by = reviewer_id if approved else None
    cr.approved_at = datetime.now(timezone.utc) if approved else None
    cr.resolution_notes = resolution_notes
    from app.services.approval_engine import fuentes
    fuentes.cerrar(db, "change_request", cr.id, "approved" if approved else "rejected",
                   resolution_notes or "Revisado en Cambios")
    db.commit()
    return cr


def implement_change_request(db: Session, cr: ChangeRequest) -> ChangeRequest:
    cr.status = ChangeRequestStatus.implemented
    cr.implemented_at = datetime.now(timezone.utc)
    db.commit()
    return cr


def delete_change_request(db: Session, cr: ChangeRequest) -> None:
    if cr.status in [ChangeRequestStatus.approved, ChangeRequestStatus.implemented]:
        raise ValueError("No se puede eliminar una CR aprobada o implementada")
    cr.is_active = False
    db.commit()
