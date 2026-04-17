"""Performance Reviews — Evaluaciones de rendimiento 360°."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import Optional
from datetime import date

from app.db.session import get_db
from app.core.deps import get_current_user, require_admin_or_hr, require_any_manager
from app.models.user import User
from app.models.performance import ReviewCycleStatus, ReviewStatus
from app.services import performance_service
from app.services.performance_service import avg_score as _avg, serialize_review as _ser_review
from app.schemas.performance import ReviewCycleIn as CycleIn, PerformanceReviewIn as ReviewIn

router = APIRouter(prefix="/performance", tags=["Performance Reviews"])


@router.get("/cycles", summary="Listar ciclos de evaluación")
def list_cycles(db: Session = Depends(get_db), cu: User = Depends(get_current_user)):
    cycles = performance_service.list_cycles(db)
    return [{"id": c.id, "name": c.name, "status": c.status,
             "start_date": str(c.start_date) if c.start_date else None,
             "end_date": str(c.end_date) if c.end_date else None,
             "total_reviews": len(c.reviews),
             "pending": sum(1 for r in c.reviews if r.status == ReviewStatus.pending),
             "submitted": sum(1 for r in c.reviews if r.status == ReviewStatus.submitted),
             } for c in cycles]


@router.post("/cycles", summary="Crear ciclo", status_code=201)
def create_cycle(payload: CycleIn, db: Session = Depends(get_db),
                 cu: User = Depends(require_admin_or_hr)):
    c = performance_service.create_cycle(db, created_by=cu.id, **payload.model_dump())
    return {"id": c.id, "name": c.name}


@router.post("/cycles/{cycle_id}/activate", summary="Activar ciclo")
def activate_cycle(cycle_id: str, db: Session = Depends(get_db),
                   cu: User = Depends(require_admin_or_hr)):
    c = performance_service.get_cycle(db, cycle_id)
    if not c:
        raise HTTPException(404, "Ciclo no encontrado")
    if c.status != ReviewCycleStatus.draft:
        raise HTTPException(400, f"Solo se puede activar un ciclo en estado 'draft', actual: '{c.status}'")
    performance_service.activate_cycle(db, c)
    return {"status": "active"}


@router.post("/cycles/{cycle_id}/close", summary="Cerrar ciclo")
def close_cycle(cycle_id: str, db: Session = Depends(get_db),
                cu: User = Depends(require_admin_or_hr)):
    c = performance_service.get_cycle(db, cycle_id)
    if not c:
        raise HTTPException(404, "Ciclo no encontrado")
    if c.status != ReviewCycleStatus.active:
        raise HTTPException(400, f"Solo se puede cerrar un ciclo activo, actual: '{c.status}'")
    performance_service.close_cycle(db, c)
    return {"status": "closed"}


@router.get("/cycles/{cycle_id}/reviews", summary="Evaluaciones de un ciclo")
def list_reviews(cycle_id: str, db: Session = Depends(get_db),
                 cu: User = Depends(require_any_manager)):
    reviews = performance_service.list_cycle_reviews(db, cycle_id)
    return [_ser_review(r) for r in reviews]


@router.get("/my-reviews", summary="Mis evaluaciones pendientes")
def my_reviews(db: Session = Depends(get_db), cu: User = Depends(get_current_user)):
    reviews = performance_service.list_my_pending_reviews(db, cu.id)
    return [_ser_review(r) for r in reviews]


@router.post("/cycles/{cycle_id}/reviews", summary="Crear evaluación", status_code=201)
def create_review(cycle_id: str, payload: dict,
                  db: Session = Depends(get_db), cu: User = Depends(require_admin_or_hr)):
    if not payload.get("reviewee_id") or not payload.get("reviewer_id"):
        raise HTTPException(422, "reviewee_id y reviewer_id son obligatorios")
    r = performance_service.create_review(
        db, cycle_id=cycle_id,
        reviewee_id=payload["reviewee_id"],
        reviewer_id=payload["reviewer_id"],
        review_type=payload.get("review_type", "peer"),
    )
    return {"id": r.id}


@router.patch("/reviews/{review_id}", summary="Guardar evaluación")
def save_review(review_id: str, payload: ReviewIn,
                db: Session = Depends(get_db), cu: User = Depends(get_current_user)):
    r = performance_service.get_review(db, review_id)
    if not r:
        raise HTTPException(404, "Evaluación no encontrada")
    if r.reviewer_id != cu.id:
        raise HTTPException(403, "Solo el evaluador puede modificar esta evaluación")
    c = performance_service.get_cycle(db, r.cycle_id)
    if c and c.status == ReviewCycleStatus.closed:
        raise HTTPException(400, "El ciclo de evaluación ya está cerrado")
    r = performance_service.save_review(db, r, payload.model_dump(exclude_unset=True))
    return _ser_review(r)


@router.post("/reviews/{review_id}/submit", summary="Enviar evaluación")
def submit_review(review_id: str, db: Session = Depends(get_db),
                  cu: User = Depends(get_current_user)):
    r = performance_service.get_review(db, review_id)
    if not r:
        raise HTTPException(404, "Evaluación no encontrada")
    if r.reviewer_id != cu.id:
        raise HTTPException(403, "Acceso denegado")
    c = performance_service.get_cycle(db, r.cycle_id)
    if c and c.status == ReviewCycleStatus.closed:
        raise HTTPException(400, "El ciclo de evaluación ya está cerrado")
    performance_service.submit_review(db, r)
    return {"status": "submitted"}


@router.get("/users/{user_id}/history", summary="Histórico de evaluaciones de un usuario")
def user_review_history(user_id: str, db: Session = Depends(get_db),
                        cu: User = Depends(require_any_manager)):
    reviews = performance_service.get_user_review_history(db, user_id)
    return [_ser_review(r) for r in reviews]
