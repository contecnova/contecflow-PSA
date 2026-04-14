"""Performance Reviews — Evaluaciones de rendimiento 360°."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session, joinedload
from typing import Optional
from pydantic import BaseModel
from datetime import date, datetime, timezone
import uuid as _uuid

from app.db.session import get_db
from app.core.deps import get_current_user, require_admin_or_hr, require_any_manager
from app.models.user import User
from app.models.performance import ReviewCycle, PerformanceReview, ReviewCycleStatus, ReviewStatus

router = APIRouter(prefix="/performance", tags=["Performance Reviews"])


class CycleIn(BaseModel):
    name: str
    description: Optional[str] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    include_self: bool = True
    include_peers: bool = True
    include_manager: bool = True

class ReviewIn(BaseModel):
    score_quality: Optional[float] = None
    score_delivery: Optional[float] = None
    score_teamwork: Optional[float] = None
    score_leadership: Optional[float] = None
    score_innovation: Optional[float] = None
    score_overall: Optional[float] = None
    strengths: Optional[str] = None
    improvements: Optional[str] = None
    goals_next: Optional[str] = None


def _avg(*scores):
    vals = [s for s in scores if s is not None]
    return round(sum(vals) / len(vals), 2) if vals else None

def _ser_review(r: PerformanceReview) -> dict:
    return {
        "id": r.id, "cycle_id": r.cycle_id,
        "reviewee_id": r.reviewee_id,
        "reviewee_name": r.reviewee.full_name if r.reviewee else None,
        "reviewer_id": r.reviewer_id,
        "reviewer_name": r.reviewer.full_name if r.reviewer else None,
        "review_type": r.review_type, "status": r.status,
        "score_quality": r.score_quality, "score_delivery": r.score_delivery,
        "score_teamwork": r.score_teamwork, "score_leadership": r.score_leadership,
        "score_innovation": r.score_innovation,
        "score_overall": r.score_overall or _avg(r.score_quality, r.score_delivery,
                                                   r.score_teamwork, r.score_leadership,
                                                   r.score_innovation),
        "strengths": r.strengths, "improvements": r.improvements,
        "goals_next": r.goals_next,
        "submitted_at": str(r.submitted_at)[:16] if r.submitted_at else None,
    }


@router.get("/cycles", summary="Listar ciclos de evaluación")
def list_cycles(db: Session = Depends(get_db), cu: User = Depends(get_current_user)):
    cycles = db.query(ReviewCycle).order_by(ReviewCycle.created_at.desc()).all()
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
    c = ReviewCycle(id=str(_uuid.uuid4()), created_by=cu.id, **payload.model_dump())
    db.add(c); db.commit(); db.refresh(c)
    return {"id": c.id, "name": c.name}


@router.post("/cycles/{cycle_id}/activate", summary="Activar ciclo")
def activate_cycle(cycle_id: str, db: Session = Depends(get_db),
                   cu: User = Depends(require_admin_or_hr)):
    c = db.query(ReviewCycle).filter(ReviewCycle.id == cycle_id).first()
    if not c: raise HTTPException(404, "Ciclo no encontrado")
    if c.status != ReviewCycleStatus.draft:
        raise HTTPException(400, f"Solo se puede activar un ciclo en estado 'draft', actual: '{c.status}'")
    c.status = ReviewCycleStatus.active
    db.commit()
    return {"status": "active"}


@router.post("/cycles/{cycle_id}/close", summary="Cerrar ciclo")
def close_cycle(cycle_id: str, db: Session = Depends(get_db),
                cu: User = Depends(require_admin_or_hr)):
    c = db.query(ReviewCycle).filter(ReviewCycle.id == cycle_id).first()
    if not c: raise HTTPException(404, "Ciclo no encontrado")
    if c.status != ReviewCycleStatus.active:
        raise HTTPException(400, f"Solo se puede cerrar un ciclo activo, actual: '{c.status}'")
    c.status = ReviewCycleStatus.closed
    db.commit()
    return {"status": "closed"}


@router.get("/cycles/{cycle_id}/reviews", summary="Evaluaciones de un ciclo")
def list_reviews(cycle_id: str, db: Session = Depends(get_db),
                 cu: User = Depends(require_any_manager)):
    reviews = (db.query(PerformanceReview)
               .options(joinedload(PerformanceReview.reviewee),
                        joinedload(PerformanceReview.reviewer))
               .filter(PerformanceReview.cycle_id == cycle_id).all())
    return [_ser_review(r) for r in reviews]


@router.get("/my-reviews", summary="Mis evaluaciones pendientes")
def my_reviews(db: Session = Depends(get_db), cu: User = Depends(get_current_user)):
    reviews = (db.query(PerformanceReview)
               .options(joinedload(PerformanceReview.reviewee),
                        joinedload(PerformanceReview.reviewer))
               .filter(PerformanceReview.reviewer_id == cu.id,
                       PerformanceReview.status == ReviewStatus.pending).all())
    return [_ser_review(r) for r in reviews]


@router.post("/cycles/{cycle_id}/reviews", summary="Crear evaluación", status_code=201)
def create_review(cycle_id: str, payload: dict,
                  db: Session = Depends(get_db), cu: User = Depends(require_admin_or_hr)):
    if not payload.get("reviewee_id") or not payload.get("reviewer_id"):
        raise HTTPException(422, "reviewee_id y reviewer_id son obligatorios")
    r = PerformanceReview(
        id=str(_uuid.uuid4()), cycle_id=cycle_id,
        reviewee_id=payload["reviewee_id"],
        reviewer_id=payload["reviewer_id"],
        review_type=payload.get("review_type", "peer"),
    )
    db.add(r); db.commit()
    return {"id": r.id}


@router.patch("/reviews/{review_id}", summary="Guardar evaluación")
def save_review(review_id: str, payload: ReviewIn,
                db: Session = Depends(get_db), cu: User = Depends(get_current_user)):
    r = db.query(PerformanceReview).filter(PerformanceReview.id == review_id).first()
    if not r: raise HTTPException(404, "Evaluación no encontrada")
    if r.reviewer_id != cu.id:
        raise HTTPException(403, "Solo el evaluador puede modificar esta evaluación")
    cycle = db.query(ReviewCycle).filter(ReviewCycle.id == r.cycle_id).first()
    if cycle and cycle.status == ReviewCycleStatus.closed:
        raise HTTPException(400, "El ciclo de evaluación ya está cerrado")
    for k, v in payload.model_dump(exclude_unset=True).items():
        setattr(r, k, v)
    db.commit(); db.refresh(r)
    return _ser_review(r)


@router.post("/reviews/{review_id}/submit", summary="Enviar evaluación")
def submit_review(review_id: str, db: Session = Depends(get_db),
                  cu: User = Depends(get_current_user)):
    r = db.query(PerformanceReview).filter(PerformanceReview.id == review_id).first()
    if not r: raise HTTPException(404, "Evaluación no encontrada")
    if r.reviewer_id != cu.id: raise HTTPException(403, "Acceso denegado")
    cycle = db.query(ReviewCycle).filter(ReviewCycle.id == r.cycle_id).first()
    if cycle and cycle.status == ReviewCycleStatus.closed:
        raise HTTPException(400, "El ciclo de evaluación ya está cerrado")
    r.status = ReviewStatus.submitted
    r.submitted_at = datetime.now(timezone.utc)
    db.commit()
    return {"status": "submitted"}


@router.get("/users/{user_id}/history", summary="Histórico de evaluaciones de un usuario")
def user_review_history(user_id: str, db: Session = Depends(get_db),
                        cu: User = Depends(require_any_manager)):
    reviews = (db.query(PerformanceReview)
               .options(joinedload(PerformanceReview.reviewer))
               .filter(PerformanceReview.reviewee_id == user_id,
                       PerformanceReview.status == ReviewStatus.submitted)
               .order_by(PerformanceReview.submitted_at.desc()).all())
    return [_ser_review(r) for r in reviews]
