from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import func
from typing import Optional
from datetime import datetime, timezone
from pydantic import BaseModel

from app.db.session import get_db
from app.core.deps import get_current_user, require_any_manager
from app.models.user import User
from app.models.resources import ChangeRequest, ChangeRequestStatus

router = APIRouter()

IMPACT_CFG = {
    "low":      {"label": "Bajo",     "color": "#00e5a0"},
    "medium":   {"label": "Medio",    "color": "#00d4ff"},
    "high":     {"label": "Alto",     "color": "#ffb800"},
    "critical": {"label": "Crítico",  "color": "#ff4757"},
}
STATUS_CFG = {
    "draft":         {"label": "Borrador",       "color": "#7a8aaa"},
    "submitted":     {"label": "Enviado",         "color": "#00d4ff"},
    "under_review":  {"label": "En revisión",    "color": "#ffb800"},
    "approved":      {"label": "Aprobado",        "color": "#00e5a0"},
    "rejected":      {"label": "Rechazado",       "color": "#ff4757"},
    "implemented":   {"label": "Implementado",   "color": "#7c3aed"},
}


class CRIn(BaseModel):
    title: str
    description: str
    justification: Optional[str] = None
    impact: str = "medium"
    cost_impact: Optional[float] = None
    schedule_impact_days: Optional[int] = None
    scope_impact: Optional[str] = None

class CRReview(BaseModel):
    approved: bool
    resolution_notes: Optional[str] = None


def _next_code(project_id: str, db: Session) -> str:
    import re
    max_code = db.query(func.max(ChangeRequest.code)).filter(ChangeRequest.project_id == project_id).scalar()
    if max_code:
        m = re.search(r"(\d+)$", max_code)
        next_num = (int(m.group(1)) + 1) if m else 1
    else:
        next_num = 1
    return f"CR-{next_num:03d}"


def _cr_out(cr: ChangeRequest) -> dict:
    return {
        "id": cr.id, "code": cr.code, "project_id": cr.project_id,
        "title": cr.title, "description": cr.description, "justification": cr.justification,
        "impact": cr.impact,
        "impact_label": IMPACT_CFG.get(cr.impact, {}).get("label", cr.impact),
        "impact_color": IMPACT_CFG.get(cr.impact, {}).get("color", "#7a8aaa"),
        "cost_impact": cr.cost_impact,
        "schedule_impact_days": cr.schedule_impact_days,
        "scope_impact": cr.scope_impact,
        "status": cr.status,
        "status_label": STATUS_CFG.get(cr.status, {}).get("label", cr.status),
        "status_color": STATUS_CFG.get(cr.status, {}).get("color", "#7a8aaa"),
        "requested_by": cr.requested_by,
        "requester_name": cr.requester.full_name if cr.requester else None,
        "reviewed_by": cr.reviewed_by,
        "approved_by": cr.approved_by,
        "approver_name": cr.approver_user.full_name if cr.approver_user else None,
        "submitted_at": str(cr.submitted_at) if cr.submitted_at else None,
        "approved_at": str(cr.approved_at) if cr.approved_at else None,
        "implemented_at": str(cr.implemented_at) if cr.implemented_at else None,
        "resolution_notes": cr.resolution_notes,
        "created_at": str(cr.created_at)[:10] if cr.created_at else None,
    }


@router.get("/all/pending", summary="Todas las CRs pendientes")
def get_all_pending(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    crs = db.query(ChangeRequest).options(
        joinedload(ChangeRequest.requester),
        joinedload(ChangeRequest.project),
    ).filter(ChangeRequest.status.in_(["submitted", "under_review"])).order_by(ChangeRequest.created_at.desc()).all()
    result = []
    for cr in crs:
        d = _cr_out(cr)
        d["project_name"] = cr.project.name if cr.project else "—"
        d["project_code"] = cr.project.code if cr.project else "—"
        result.append(d)
    return result



@router.get("/{project_id}", summary="Solicitudes de cambio de un proyecto")
def get_change_requests(
    project_id: str,
    status: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    q = db.query(ChangeRequest).options(
        joinedload(ChangeRequest.requester),
        joinedload(ChangeRequest.approver_user),
    ).filter(ChangeRequest.project_id == project_id)
    if status:
        q = q.filter(ChangeRequest.status == status)
    crs = q.order_by(ChangeRequest.created_at.desc()).all()
    return {
        "change_requests": [_cr_out(cr) for cr in crs],
        "summary": {
            "total": len(crs),
            "pending": sum(1 for cr in crs if cr.status in ["submitted", "under_review"]),
            "approved": sum(1 for cr in crs if cr.status == "approved"),
            "total_cost_impact": sum(cr.cost_impact or 0 for cr in crs if cr.status == "approved"),
            "total_schedule_impact": sum(cr.schedule_impact_days or 0 for cr in crs if cr.status == "approved"),
        }
    }


@router.post("/{project_id}", summary="Crear solicitud de cambio")
def create_change_request(
    project_id: str,
    payload: CRIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    cr = ChangeRequest(
        project_id=project_id,
        code=_next_code(project_id, db),
        requested_by=current_user.id,
        **payload.model_dump(),
    )
    db.add(cr); db.commit(); db.refresh(cr)
    return _cr_out(cr)


@router.patch("/{project_id}/{cr_id}", summary="Actualizar CR")
def update_change_request(
    project_id: str,
    cr_id: str,
    payload: CRIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    cr = db.query(ChangeRequest).filter(ChangeRequest.id == cr_id, ChangeRequest.project_id == project_id).first()
    if not cr: raise HTTPException(404, "CR no encontrada")
    if cr.status not in ["draft", "submitted"]:
        raise HTTPException(400, "Solo se pueden editar CRs en borrador o enviadas")
    for k, v in payload.model_dump(exclude_unset=True).items():
        setattr(cr, k, v)
    db.commit(); db.refresh(cr)
    return _cr_out(cr)


@router.post("/{project_id}/{cr_id}/submit", summary="Enviar CR para revisión")
def submit_cr(
    project_id: str,
    cr_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    cr = db.query(ChangeRequest).filter(ChangeRequest.id == cr_id).first()
    if not cr: raise HTTPException(404, "CR no encontrada")
    if cr.status != "draft": raise HTTPException(400, "Solo se pueden enviar CRs en borrador")
    cr.status = ChangeRequestStatus.submitted
    cr.submitted_at = datetime.now(timezone.utc)
    db.commit()
    return {"message": "CR enviada para revisión", "status": cr.status}


@router.post("/{project_id}/{cr_id}/review", summary="Aprobar o rechazar CR")
def review_cr(
    project_id: str,
    cr_id: str,
    payload: CRReview,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    cr = db.query(ChangeRequest).filter(ChangeRequest.id == cr_id).first()
    if not cr: raise HTTPException(404, "CR no encontrada")
    if cr.status not in ["submitted", "under_review"]:
        raise HTTPException(400, "Solo se pueden revisar CRs enviadas")

    cr.status = ChangeRequestStatus.approved if payload.approved else ChangeRequestStatus.rejected
    cr.reviewed_by = current_user.id
    cr.approved_by = current_user.id if payload.approved else None
    cr.approved_at = datetime.now(timezone.utc) if payload.approved else None
    cr.resolution_notes = payload.resolution_notes
    db.commit()
    return {"message": "CR aprobada" if payload.approved else "CR rechazada", "status": cr.status}


@router.post("/{project_id}/{cr_id}/implement", summary="Marcar CR como implementada")
def implement_cr(
    project_id: str,
    cr_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    cr = db.query(ChangeRequest).filter(ChangeRequest.id == cr_id).first()
    if not cr: raise HTTPException(404, "CR no encontrada")
    if cr.status != "approved": raise HTTPException(400, "Solo se pueden implementar CRs aprobadas")
    cr.status = ChangeRequestStatus.implemented
    cr.implemented_at = datetime.now(timezone.utc)
    db.commit()
    return {"message": "CR marcada como implementada"}


@router.delete("/{project_id}/{cr_id}", summary="Eliminar CR")
def delete_cr(
    project_id: str,
    cr_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    cr = db.query(ChangeRequest).filter(ChangeRequest.id == cr_id).first()
    if not cr: raise HTTPException(404, "CR no encontrada")
    db.delete(cr); db.commit()
    return {"ok": True}
