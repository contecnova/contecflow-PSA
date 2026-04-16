from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import Optional
from datetime import date
from pydantic import BaseModel

from app.db.session import get_db
from app.core.deps import get_current_user, require_any_manager
from app.models.user import User, UserRole
from app.models.resources import DeliverableStatus
from app.services import deliverable_service

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


def _del_out(d) -> dict:
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
    deliverables = deliverable_service.list_all_deliverables(db)
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
    deliverables = deliverable_service.list_project_deliverables(db, project_id, status)
    result = [_del_out(d) for d in deliverables]

    return {
        "deliverables": result,
        "summary": {
            "total": len(result),
            "accepted": sum(1 for d in result if d["status"] == "accepted"),
            "delivered": sum(1 for d in result if d["status"] == "delivered"),
            "overdue": sum(1 for d in result if d["overdue"]),
            "completion_pct": round(
                sum(1 for d in result if d["status"] in ["delivered", "accepted"]) / max(len(result), 1) * 100, 1
            ),
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
    d = deliverable_service.create_deliverable(db, project_id, **payload.model_dump())
    return _del_out(d)


@router.patch("/{project_id}/{del_id}", summary="Actualizar entregable")
def update_deliverable(
    project_id: str,
    del_id: str,
    payload: DeliverableUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role not in [UserRole.admin, UserRole.pm]:
        raise HTTPException(403, "Solo administradores y PMs pueden actualizar entreables")
    d = deliverable_service.get_deliverable(db, del_id, project_id)
    if not d:
        raise HTTPException(404, "Entregable no encontrado")
    d = deliverable_service.update_deliverable(db, d, payload.model_dump(exclude_unset=True))
    return _del_out(d)


@router.post("/{project_id}/{del_id}/deliver", summary="Marcar como entregado")
def deliver(
    project_id: str,
    del_id: str,
    document_url: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    d = deliverable_service.get_deliverable(db, del_id, project_id)
    if not d:
        raise HTTPException(404, "No encontrado")
    d = deliverable_service.mark_delivered(db, d, document_url)
    return _del_out(d)


@router.post("/{project_id}/{del_id}/accept", summary="Aceptar entregable")
def accept(
    project_id: str,
    del_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    d = deliverable_service.get_deliverable(db, del_id, project_id)
    if not d:
        raise HTTPException(404, "No encontrado")
    if d.status != "delivered":
        raise HTTPException(400, "Solo se pueden aceptar entregables entregados")
    d = deliverable_service.mark_accepted(db, d)
    return _del_out(d)


@router.post("/{project_id}/{del_id}/reject", summary="Rechazar entregable")
def reject(
    project_id: str,
    del_id: str,
    reason: str = Query(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    d = deliverable_service.get_deliverable(db, del_id)
    if not d:
        raise HTTPException(404, "No encontrado")
    d = deliverable_service.mark_rejected(db, d, reason)
    return _del_out(d)


@router.delete("/{project_id}/{del_id}", summary="Eliminar entregable")
def delete_deliverable(
    project_id: str,
    del_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    d = deliverable_service.get_deliverable(db, del_id)
    if not d:
        raise HTTPException(404, "No encontrado")
    deliverable_service.delete_deliverable(db, d)
    return {"ok": True}
