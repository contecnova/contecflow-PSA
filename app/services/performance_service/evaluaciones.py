"""Evaluaciones individuales: evaluadores elegibles, alta, guardado, envio e historial.

Parte de `app.services.performance_service` (auditoria 2026-11, #24): se partio por responsabilidad
sin cambiar el codigo. El paquete reexporta todos los nombres.
"""
from sqlalchemy.orm import Session, joinedload
from datetime import datetime, timezone
import uuid as _uuid
from app.models.performance import ReviewCycle, PerformanceReview, ReviewStatus
from app.models.user import User
from app.core.asignacion import es_asignable


# ── Eligible reviewers ────────────────────────────────────────────────────────

def eligible_reviewers(db: Session, *, reviewee: User, review_type: str) -> list[User]:
    """Devuelve los evaluadores válidos para un reviewee según el tipo.

      - self    → la propia persona
      - manager → solo el manager directo (manager_id) si existe
      - peer    → mismo equipo o departamento, excluyendo a la persona y a su manager
      - upward  → personas cuyo manager_id == reviewee.id (sus reportes directos)
    """
    if review_type == "self":
        return [reviewee]

    if review_type == "manager":
        if not reviewee.manager_id:
            return []
        manager = db.query(User).filter(User.id == reviewee.manager_id, User.is_active == True).first()
        return [manager] if manager else []

    if review_type == "peer":
        # Filtramos por team si lo hay; si no, por department.
        q = db.query(User).filter(
            User.is_active == True,
            User.organization_id == reviewee.organization_id,
            User.id != reviewee.id,
        )
        if reviewee.team:
            q = q.filter(User.team == reviewee.team)
        elif reviewee.department:
            q = q.filter(User.department == reviewee.department)
        else:
            return []
        users = q.all()
        # Excluimos al manager del pool de pares
        return [u for u in users if u.id != reviewee.manager_id]

    if review_type == "upward":
        return db.query(User).filter(
            User.is_active == True,
            User.manager_id == reviewee.id,
        ).all()

    return []


def list_cycle_reviews(db: Session, cycle_id: str,
                       *, limit: int = 100, offset: int = 0):
    q = (
        db.query(PerformanceReview)
        .options(joinedload(PerformanceReview.reviewee),
                 joinedload(PerformanceReview.reviewer))
        .filter(PerformanceReview.cycle_id == cycle_id)
        .order_by(PerformanceReview.created_at.desc())
    )
    total = q.count()
    items = q.limit(limit).offset(offset).all()
    return items, total


def list_my_pending_reviews(db: Session, reviewer_id: str):
    return (
        db.query(PerformanceReview)
        .options(joinedload(PerformanceReview.reviewee), joinedload(PerformanceReview.reviewer))
        .filter(
            PerformanceReview.reviewer_id == reviewer_id,
            PerformanceReview.status == ReviewStatus.pending,
        )
        .all()
    )


def _organizacion_del_ciclo(db: Session, cycle_id: str) -> "str | None":
    """La organizacion del ciclo al que cuelga una evaluacion.

    Se resuelve por id y no se pide como parametro para no cambiar la firma de
    `create_review`, que tiene ocho llamantes. Es una consulta de una columna.
    """
    return (
        db.query(ReviewCycle.organization_id)
        .filter(ReviewCycle.id == cycle_id)
        .scalar()
    )


def create_review(db: Session, cycle_id: str, reviewee_id: str, reviewer_id: str,
                  review_type: str = "peer", *, validate_eligibility: bool = True) -> PerformanceReview:
    if validate_eligibility:
        reviewee = db.query(User).filter(User.id == reviewee_id).first()
        if not reviewee:
            raise ValueError("Persona evaluada no encontrada")
        valid = eligible_reviewers(db, reviewee=reviewee, review_type=review_type)
        valid_ids = {u.id for u in valid}
        if reviewer_id not in valid_ids:
            # Mensajes específicos para que la UI pueda explicar el porqué
            if review_type == "manager" and not reviewee.manager_id:
                raise ValueError("Esta persona no tiene manager configurado en el organigrama")
            if review_type == "peer" and not reviewee.department and not reviewee.team:
                raise ValueError("Esta persona no tiene equipo ni departamento — no es posible asignar pares")
            if review_type == "upward":
                raise ValueError("Esta persona no tiene reportes directos en el organigrama")
            raise ValueError(f"El evaluador no es elegible para el tipo '{review_type}'")
    r = PerformanceReview(
        id=str(_uuid.uuid4()),
        cycle_id=cycle_id,
        organization_id=_organizacion_del_ciclo(db, cycle_id),
        reviewee_id=reviewee_id,
        reviewer_id=reviewer_id,
        review_type=review_type,
        answers_json={},
    )
    db.add(r)
    db.commit()
    return r


def get_review(db: Session, review_id: str):
    return db.query(PerformanceReview).filter(PerformanceReview.id == review_id).first()


def save_review(db: Session, r: PerformanceReview, updates: dict) -> PerformanceReview:
    """Aplica updates a la evaluación. Si llega `answers`, lo merge sobre answers_json
    en lugar de reemplazar el dict completo (permite guardar parcialmente)."""
    if "answers" in updates:
        merged = dict(r.answers_json or {})
        merged.update(updates.pop("answers") or {})
        r.answers_json = merged
        # Mantenemos los score_* legacy en sync por si código viejo los lee
        for k in ("score_quality", "score_delivery", "score_teamwork",
                  "score_leadership", "score_innovation"):
            if k in merged:
                try: setattr(r, k, float(merged[k]) if merged[k] is not None else None)
                except (TypeError, ValueError): pass
        for k in ("strengths", "improvements", "goals_next"):
            if k in merged:
                setattr(r, k, merged[k])
    for k, v in updates.items():
        if es_asignable(r, k):
            setattr(r, k, v)
    db.commit()
    db.refresh(r)
    return r


def submit_review(db: Session, r: PerformanceReview) -> PerformanceReview:
    r.status = ReviewStatus.submitted
    r.submitted_at = datetime.now(timezone.utc)
    db.commit()
    return r


def get_user_review_history(db: Session, user_id: str):
    return (
        db.query(PerformanceReview)
        .options(joinedload(PerformanceReview.reviewer))
        .filter(
            PerformanceReview.reviewee_id == user_id,
            PerformanceReview.status == ReviewStatus.submitted,
        )
        .order_by(PerformanceReview.submitted_at.desc())
        .all()
    )


# ── Serialization helpers ─────────────────────────────────────────────────────

def avg_score(*scores) -> object:
    """Return the rounded mean of non-None score values, or None."""
    vals = [s for s in scores if s is not None]
    return round(sum(vals) / len(vals), 2) if vals else None


def serialize_review(r) -> dict:
    answers = dict(r.answers_json or {})
    # Backfill legacy → answers para reviews creadas antes de las preguntas dinámicas
    for k in ("score_quality", "score_delivery", "score_teamwork",
              "score_leadership", "score_innovation",
              "strengths", "improvements", "goals_next"):
        legacy = getattr(r, k, None)
        if legacy is not None and k not in answers:
            answers[k] = legacy
    return {
        "id": r.id, "cycle_id": r.cycle_id,
        "reviewee_id": r.reviewee_id,
        "reviewee_name": r.reviewee.full_name if r.reviewee else None,
        "reviewer_id": r.reviewer_id,
        "reviewer_name": r.reviewer.full_name if r.reviewer else None,
        "review_type": r.review_type, "status": r.status,
        "answers": answers,
        # Legacy fields conservados para retrocompat de UIs antiguas
        "score_quality": r.score_quality, "score_delivery": r.score_delivery,
        "score_teamwork": r.score_teamwork, "score_leadership": r.score_leadership,
        "score_innovation": r.score_innovation,
        "score_overall": r.score_overall or avg_score(
            r.score_quality, r.score_delivery, r.score_teamwork,
            r.score_leadership, r.score_innovation,
        ),
        "strengths": r.strengths, "improvements": r.improvements,
        "goals_next": r.goals_next,
        "submitted_at": str(r.submitted_at)[:16] if r.submitted_at else None,
    }
