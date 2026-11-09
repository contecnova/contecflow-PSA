from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import Any, Dict, Optional

from app.db.session import get_db
from app.core.deps import get_current_user, require_any_manager
from app.core.abac_enforce import enforce_abac
from app.core.responses import APIListResponse, APIResponse
from app.models.user import User, UserRole
from app.services import deliverable_service
from app.services.deliverable_service import serialize_deliverable as _del_out
from app.schemas.deliverables import DeliverableIn, DeliverableUpdate

router = APIRouter()


@router.get("/all/overview", response_model=APIListResponse[Dict[str, Any]], summary="Vista global de entregables")
def get_all_deliverables(
    page: int = Query(1, ge=1),
    page_size: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    deliverables = deliverable_service.list_all_deliverables(
        db, limit=page_size, offset=(page - 1) * page_size
    )
    result = []
    for d in deliverables:
        row = _del_out(d)
        row["project_name"] = d.project.name if d.project else "—"
        row["project_code"] = d.project.code if d.project else "—"
        result.append(row)
    return APIListResponse.ok(items=result, page=page, page_size=page_size)


@router.get("/{project_id}", summary="Entregables de un proyecto")
def get_deliverables(
    project_id: str,
    status: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    deliverables = deliverable_service.list_project_deliverables(db, project_id, status)
    result = [_del_out(d) for d in deliverables]

    return APIResponse.ok(data={
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
    })


@router.post("/{project_id}", summary="Crear entregable")
def create_deliverable(
    project_id: str,
    payload: DeliverableIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _rol: User = Depends(require_any_manager),  # auditoria 2026-09: sus hermanas del fichero usan esa guarda
):
    if current_user.role not in [UserRole.admin, UserRole.pm]:
        raise HTTPException(403, "Acceso denegado")
    d = deliverable_service.create_deliverable(db, project_id, **payload.model_dump())
    return APIResponse.ok(data=_del_out(d))


@router.patch("/{project_id}/{del_id}", summary="Actualizar entregable")
def update_deliverable(
    project_id: str,
    del_id: str,
    payload: DeliverableUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _rol: User = Depends(require_any_manager),  # auditoria 2026-09: sus hermanas del fichero usan esa guarda
):
    if current_user.role not in [UserRole.admin, UserRole.pm]:
        raise HTTPException(403, "Solo administradores y PMs pueden actualizar entreables")
    d = deliverable_service.get_deliverable(db, del_id, project_id)
    if not d:
        raise HTTPException(404, "Entregable no encontrado")
    enforce_abac(db, current_user, "deliverable", del_id, action="update")
    cambios = payload.model_dump(exclude_unset=True)
    # Revisión 2026-11: aceptar y rechazar tienen su regla (sólo un entregado);
    # editando el estado a mano se la saltaba.
    if cambios.get("status") in ("accepted", "rejected") and cambios["status"] != str(getattr(d.status, "value", d.status)) \
            and str(getattr(d.status, "value", d.status)) != "delivered":
        raise HTTPException(400, "Sólo se acepta o rechaza un entregable entregado")
    d = deliverable_service.update_deliverable(db, d, cambios)
    return APIResponse.ok(data=_del_out(d))


@router.post("/{project_id}/{del_id}/deliver", summary="Marcar como entregado")
def deliver(
    project_id: str,
    del_id: str,
    document_url: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _rol: User = Depends(require_any_manager),  # auditoria 2026-09: sus hermanas del fichero usan esa guarda
):
    d = deliverable_service.get_deliverable(db, del_id, project_id)
    if not d:
        raise HTTPException(404, "No encontrado")
    enforce_abac(db, current_user, "deliverable", del_id, action="update")
    d = deliverable_service.mark_delivered(db, d, document_url)
    return APIResponse.ok(data=_del_out(d))


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
    enforce_abac(db, current_user, "deliverable", del_id, action="update")
    d = deliverable_service.mark_accepted(db, d)
    return APIResponse.ok(data=_del_out(d))


@router.post("/{project_id}/{del_id}/reject", summary="Rechazar entregable")
def reject(
    project_id: str,
    del_id: str,
    reason: str = Query(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    d = deliverable_service.get_deliverable(db, del_id, project_id)
    if not d:
        raise HTTPException(404, "No encontrado")
    if d.status != "delivered":
        raise HTTPException(400, "Solo se pueden rechazar entregables entregados")
    enforce_abac(db, current_user, "deliverable", del_id, action="update")
    d = deliverable_service.mark_rejected(db, d, reason)
    return APIResponse.ok(data=_del_out(d))


@router.delete("/{project_id}/{del_id}", summary="Eliminar entregable (soft delete)")
def delete_deliverable(
    project_id: str,
    del_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    d = deliverable_service.get_deliverable(db, del_id, project_id)
    if not d:
        raise HTTPException(404, "No encontrado")
    enforce_abac(db, current_user, "deliverable", del_id, action="delete")
    deliverable_service.delete_deliverable(db, d)
    return APIResponse.ok(data={"ok": True, "message": f"Entregable '{d.name}' eliminado"})
