from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import func
from typing import Optional
from datetime import date
from pydantic import BaseModel

from app.db.session import get_db
from app.core.deps import get_current_user, require_any_manager
from app.models.user import User, UserRole
from app.models.project import Project
from app.models.resources import Deliverable, DeliverableStatus
from app.services.numbering import next_numbered_code

router = APIRouter()

STATUS_CFG = {
    "planned":     {"label": "Planificado",  "color": "#7a8aaa", "icon": "📋"},
    "in_progress": {"label": "En curso",     "color": "#00d4ff", "icon": "🔄"},
    "in_review":   {"label": "En revisión",  "color": "#ffb800", "icon": "👁"},
    "delivered":   {"label": "Entregado",    "color": "#7c3aed", "icon": "📤"},
    "accepted":    {"label": "Aceptado",     "color": "#00e5a0", "icon": "✅"},
    "rejected":    {"label": "Rechazado",    "color": "#ff4757", "icon": "❌"},
}


class DeliverableIn(BaseModel):
    name: str
    description: Optional[str] = None
    format: Optional[str] = None
    planned_date: Optional[date] = None
    owner_id: Optional[str] = None
    client_contact: Optional[str] = None
    acceptance_criteria: Optional[str] = None
    milestone_id: Optional[str] = None
    phase_id: Optional[str] = None
    sort_order: int = 0

class DeliverableUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    format: Optional[str] = None
    status: Optional[str] = None
    planned_date: Optional[date] = None
    delivered_date: Optional[date] = None
    accepted_date: Optional[date] = None
    owner_id: Optional[str] = None
    client_contact: Optional[str] = None
    acceptance_criteria: Optional[str] = None
    rejection_reason: Optional[str] = None
    document_url: Optional[str] = None
    sort_order: Optional[int] = None


def _next_code(project_id: str, db: Session) -> str:
    return next_numbered_code(db, "deliverable", prefix="DEL", padding=3)


def _del_out(d: Deliverable) -> dict:
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



@router.get("/all/overview", summary="Vista global de entregables")
def get_all_deliverables(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    deliverables = db.query(Deliverable).options(
        joinedload(Deliverable.owner),
        joinedload(Deliverable.project),
    ).filter(Deliverable.status.notin_(["accepted"])).order_by(Deliverable.planned_date).all()

    result = []
    for d in deliverables:
        row = _del_out(d)
        row["project_name"] = d.project.name if d.project else "—"
        row["project_code"] = d.project.code if d.project else "—"
        result.append(row)
    return result

@router.get("/{project_id}", summary="Entregables de un proyecto")
def get_deliverables(
    project_id: str,
    status: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    q = db.query(Deliverable).options(joinedload(Deliverable.owner)).filter(
        Deliverable.project_id == project_id
    )
    if status:
        q = q.filter(Deliverable.status == status)
    deliverables = q.order_by(Deliverable.sort_order, Deliverable.planned_date).all()
    result = [_del_out(d) for d in deliverables]

    return {
        "deliverables": result,
        "summary": {
            "total": len(result),
            "accepted": sum(1 for d in result if d["status"] == "accepted"),
            "delivered": sum(1 for d in result if d["status"] == "delivered"),
            "overdue": sum(1 for d in result if d["overdue"]),
            "completion_pct": round(sum(1 for d in result if d["status"] in ["delivered", "accepted"]) / max(len(result), 1) * 100, 1),
        }
    }


@router.post("/{project_id}", summary="Crear entregable")
def create_deliverable(
    project_id: str,
    payload: DeliverableIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role not in [UserRole.admin, UserRole.pm]:
        raise HTTPException(403, "Acceso denegado")
    d = Deliverable(
        project_id=project_id,
        code=_next_code(project_id, db),
        **payload.model_dump(),
    )
    db.add(d); db.commit(); db.refresh(d)
    return _del_out(d)


@router.patch("/{project_id}/{del_id}", summary="Actualizar entregable")
def update_deliverable(
    project_id: str,
    del_id: str,
    payload: DeliverableUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    d = db.query(Deliverable).filter(Deliverable.id == del_id, Deliverable.project_id == project_id).first()
    if current_user.role not in [UserRole.admin, UserRole.pm]:
        raise HTTPException(403, "Solo administradores y PMs pueden actualizar entreables")
    if not d: raise HTTPException(404, "Entregable no encontrado")

    for k, v in payload.model_dump(exclude_unset=True).items():
        setattr(d, k, v)

    # Auto-set dates on status change
    if payload.status == "delivered" and not d.delivered_date:
        d.delivered_date = date.today()
    if payload.status == "accepted" and not d.accepted_date:
        d.accepted_date = date.today()

    db.commit(); db.refresh(d)
    return _del_out(d)


@router.post("/{project_id}/{del_id}/deliver", summary="Marcar como entregado")
def deliver(
    project_id: str,
    del_id: str,
    document_url: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    d = db.query(Deliverable).filter(Deliverable.id == del_id, Deliverable.project_id == project_id).first()
    if not d: raise HTTPException(404, "No encontrado")
    d.status = DeliverableStatus.delivered
    d.delivered_date = date.today()
    if document_url: d.document_url = document_url
    db.commit()
    return _del_out(d)


@router.post("/{project_id}/{del_id}/accept", summary="Aceptar entregable")
def accept(
    project_id: str,
    del_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    d = db.query(Deliverable).filter(Deliverable.id == del_id, Deliverable.project_id == project_id).first()
    if not d: raise HTTPException(404, "No encontrado")
    if d.status != "delivered": raise HTTPException(400, "Solo se pueden aceptar entregables entregados")
    d.status = DeliverableStatus.accepted
    d.accepted_date = date.today()
    db.commit()
    return _del_out(d)


@router.post("/{project_id}/{del_id}/reject", summary="Rechazar entregable")
def reject(
    project_id: str,
    del_id: str,
    reason: str = Query(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    d = db.query(Deliverable).filter(Deliverable.id == del_id).first()
    if not d: raise HTTPException(404, "No encontrado")
    d.status = DeliverableStatus.rejected
    d.rejection_reason = reason
    db.commit()
    return _del_out(d)


@router.delete("/{project_id}/{del_id}", summary="Eliminar entregable")
def delete_deliverable(
    project_id: str,
    del_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    d = db.query(Deliverable).filter(Deliverable.id == del_id).first()
    if not d: raise HTTPException(404, "No encontrado")
    db.delete(d); db.commit()
    return {"ok": True}

