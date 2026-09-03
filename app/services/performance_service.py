"""Service layer for Performance Reviews."""
from sqlalchemy.orm import Session, joinedload
from datetime import datetime, timezone
import logging
import statistics
import uuid as _uuid

from app.models.performance import (
    ReviewCycle, PerformanceReview, ReviewCycleStatus, ReviewStatus,
    ReviewQuestion, QuestionKind,
    Review360Campaign, Review360CampaignStatus,
)
from app.models.user import User
from app.models.enterprise import Notification, NotificationType

logger = logging.getLogger(__name__)


# Plantilla por defecto que se siembra al crear un ciclo (clonable después).
DEFAULT_QUESTIONS = [
    {"key": "score_quality",    "label": "Calidad del trabajo",
     "hint": "Precisión, rigor y atención al detalle",
     "kind": QuestionKind.rating_5, "order": 0, "required": True,
     "scale_min": 1, "scale_max": 5},
    {"key": "score_delivery",   "label": "Cumplimiento de plazos",
     "hint": "Entregas a tiempo y compromiso con fechas",
     "kind": QuestionKind.rating_5, "order": 1, "required": True,
     "scale_min": 1, "scale_max": 5},
    {"key": "score_teamwork",   "label": "Trabajo en equipo",
     "hint": "Colaboración, comunicación y disponibilidad",
     "kind": QuestionKind.rating_5, "order": 2, "required": True,
     "scale_min": 1, "scale_max": 5},
    {"key": "score_leadership", "label": "Liderazgo",
     "hint": "Influencia, mentoría y toma de decisiones",
     "kind": QuestionKind.rating_5, "order": 3, "required": False,
     "scale_min": 1, "scale_max": 5},
    {"key": "score_innovation", "label": "Innovación",
     "hint": "Propuestas de mejora y pensamiento creativo",
     "kind": QuestionKind.rating_5, "order": 4, "required": False,
     "scale_min": 1, "scale_max": 5},
    {"key": "strengths",        "label": "Puntos fuertes",
     "hint": "¿Qué hace especialmente bien?",
     "kind": QuestionKind.text_long, "order": 5, "required": False,
     "scale_min": None, "scale_max": None},
    {"key": "improvements",     "label": "Áreas de mejora",
     "hint": "¿Qué podría mejorar?",
     "kind": QuestionKind.text_long, "order": 6, "required": False,
     "scale_min": None, "scale_max": None},
    {"key": "goals_next",       "label": "Objetivos próximo período",
     "hint": "¿En qué debería focalizarse?",
     "kind": QuestionKind.text_long, "order": 7, "required": False,
     "scale_min": None, "scale_max": None},
]


def list_cycles(db: Session, *, limit: int = 50, offset: int = 0):
    q = db.query(ReviewCycle).order_by(ReviewCycle.created_at.desc())
    total = q.count()
    items = q.limit(limit).offset(offset).all()
    return items, total


def create_cycle(db: Session, created_by: str, *, seed_default_questions: bool = True,
                 clone_questions_from_cycle_id: str | None = None,
                 **kwargs) -> ReviewCycle:
    c = ReviewCycle(id=str(_uuid.uuid4()), created_by=created_by, **kwargs)
    db.add(c)
    db.flush()
    # Si se pide clonar de un ciclo previo, copiamos preguntas (ignorando defaults).
    if clone_questions_from_cycle_id:
        clone_questions(db, source_cycle_id=clone_questions_from_cycle_id, dest_cycle=c)
    elif seed_default_questions:
        seed_default_questions_for_cycle(db, c)
    db.commit()
    db.refresh(c)
    return c


# ── Questions CRUD ────────────────────────────────────────────────────────────

def list_questions(db: Session, cycle_id: str):
    return (
        db.query(ReviewQuestion)
        .filter(ReviewQuestion.cycle_id == cycle_id)
        .order_by(ReviewQuestion.order, ReviewQuestion.label)
        .all()
    )


def seed_default_questions_for_cycle(db: Session, cycle: ReviewCycle) -> None:
    for q in DEFAULT_QUESTIONS:
        db.add(ReviewQuestion(
            id=str(_uuid.uuid4()), cycle_id=cycle.id,
            key=q["key"], label=q["label"], hint=q["hint"],
            kind=q["kind"], order=q["order"], required=q["required"],
            scale_min=q["scale_min"], scale_max=q["scale_max"],
        ))


def clone_questions(db: Session, *, source_cycle_id: str, dest_cycle: ReviewCycle) -> int:
    src = list_questions(db, source_cycle_id)
    for q in src:
        db.add(ReviewQuestion(
            id=str(_uuid.uuid4()), cycle_id=dest_cycle.id,
            key=q.key, label=q.label, hint=q.hint, kind=q.kind, order=q.order,
            required=q.required, scale_min=q.scale_min, scale_max=q.scale_max,
        ))
    return len(src)


def add_question(db: Session, cycle: ReviewCycle, data: dict) -> ReviewQuestion:
    if cycle.status != ReviewCycleStatus.draft:
        raise ValueError("Las preguntas solo se pueden modificar en ciclos en borrador")
    # Asignamos un order incremental si no llega
    if data.get("order") is None:
        max_order = max((q.order for q in cycle.questions), default=-1)
        data["order"] = max_order + 1
    q = ReviewQuestion(id=str(_uuid.uuid4()), cycle_id=cycle.id, **data)
    db.add(q)
    db.flush()
    return q


def update_question(db: Session, question: ReviewQuestion, updates: dict) -> ReviewQuestion:
    cycle = question.cycle
    if cycle.status != ReviewCycleStatus.draft:
        raise ValueError("Las preguntas solo se pueden modificar en ciclos en borrador")
    for k, v in updates.items():
        setattr(question, k, v)
    db.flush()
    return question


def delete_question(db: Session, question: ReviewQuestion) -> None:
    cycle = question.cycle
    if cycle.status != ReviewCycleStatus.draft:
        raise ValueError("Las preguntas solo se pueden modificar en ciclos en borrador")
    db.delete(question)
    db.flush()


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


def get_cycle(db: Session, cycle_id: str):
    return db.query(ReviewCycle).filter(ReviewCycle.id == cycle_id).first()


def activate_cycle(db: Session, c: ReviewCycle) -> ReviewCycle:
    c.status = ReviewCycleStatus.active
    db.commit()
    return c


def close_cycle(db: Session, c: ReviewCycle) -> ReviewCycle:
    c.status = ReviewCycleStatus.closed
    db.commit()
    return c


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
        if hasattr(r, k):
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


def serialize_question(q: ReviewQuestion) -> dict:
    return {
        "id": q.id, "cycle_id": q.cycle_id,
        "key": q.key, "label": q.label, "hint": q.hint,
        "kind": q.kind.value if hasattr(q.kind, "value") else q.kind,
        "order": q.order, "required": q.required,
        "scale_min": q.scale_min, "scale_max": q.scale_max,
    }


# ── 360° Campaigns ────────────────────────────────────────────────────────────

def get_campaign(db: Session, campaign_id: str) -> Review360Campaign | None:
    return db.query(Review360Campaign).filter(Review360Campaign.id == campaign_id).first()


def list_cycle_campaigns(db: Session, cycle_id: str,
                         *, limit: int = 100, offset: int = 0):
    q = (
        db.query(Review360Campaign)
        .options(joinedload(Review360Campaign.subject))
        .filter(Review360Campaign.cycle_id == cycle_id)
        .order_by(Review360Campaign.created_at.desc())
    )
    total = q.count()
    items = q.limit(limit).offset(offset).all()
    return items, total


# ── Campañas de evaluación 360° ──────────────────────────────────────────────
#
# Auditoria 2026-08 (hallazgo 18). `create_campaign` era complejidad 18. Las
# tres validaciones de elegibilidad —manager, pares y upward— eran el MISMO
# bloque copiado tres veces: pedir los elegibles al organigrama, restar, y
# lanzar si sobra alguno. Solo cambiaba el tipo y el mensaje.
#
# Que sea una tabla importa aqui mas que en otros sitios: la elegibilidad es lo
# que impide que alguien se monte una campana con los evaluadores que le
# convengan. Tres copias son tres sitios donde olvidar la comprobacion.


# El mensaje de error de cada bloque que se valida por lista. El manager va
# aparte: es uno solo y su mensaje no lleva recuento.
_MENSAJES_DE_ELEGIBILIDAD = {
    "peer": "{n} par(es) no son del mismo equipo/departamento",
    "upward": "{n} reportes upward no figuran como reportes directos",
}


def _elegibles(db: Session, subject: User, review_type: str) -> set:
    """Los identificadores que el organigrama admite para ese tipo de evaluación."""
    return {
        u.id for u in eligible_reviewers(db, reviewee=subject, review_type=review_type)
    }


def _validar_lista_de_evaluadores(db: Session, subject: User, review_type: str,
                                  ids: list[str]) -> None:
    """Comprueba que todos los evaluadores de la lista son elegibles.

    Lanza nombrando CUANTOS sobran y no cuales: el mensaje va a la interfaz, y
    listar identificadores de personas ahi no ayuda a quien lo lee.
    """
    if not ids:
        return
    sobran = [r for r in ids if r not in _elegibles(db, subject, review_type)]
    if sobran:
        raise ValueError(_MENSAJES_DE_ELEGIBILIDAD[review_type].format(n=len(sobran)))


def _sin_duplicados(ids: list[str] | None) -> list[str]:
    """Quita repetidos conservando el orden.

    Importa porque un evaluador repetido generaria DOS evaluaciones para la
    misma persona, y el umbral de anonimato cuenta evaluaciones: duplicar una
    bajaria artificialmente la barrera que protege el anonimato.
    """
    return list(dict.fromkeys(ids or []))


def _validar_campana(db: Session, cycle_id: str, subject_id: str,
                     self_review: bool, manager_reviewer_id: str | None,
                     peer_reviewer_ids: list[str],
                     upward_reviewer_ids: list[str]):
    """Comprueba ciclo, persona evaluada y elegibilidad. Devuelve (ciclo, persona)."""
    cycle = get_cycle(db, cycle_id)
    if not cycle:
        raise ValueError("Ciclo no encontrado")
    if cycle.status == ReviewCycleStatus.closed:
        raise ValueError("No se puede crear una campaña en un ciclo cerrado")

    subject = db.query(User).filter(User.id == subject_id).first()
    if not subject:
        raise ValueError("Persona evaluada no encontrada")

    if manager_reviewer_id and manager_reviewer_id not in _elegibles(db, subject, "manager"):
        raise ValueError(
            "El manager indicado no figura como manager directo en el organigrama"
        )
    _validar_lista_de_evaluadores(db, subject, "peer", peer_reviewer_ids)
    _validar_lista_de_evaluadores(db, subject, "upward", upward_reviewer_ids)

    if not (self_review or manager_reviewer_id or peer_reviewer_ids or upward_reviewer_ids):
        raise ValueError("La campaña debe incluir al menos un evaluador")

    return cycle, subject


def _evaluaciones_de_la_campana(camp, cycle_id: str, subject_id: str,
                                self_review: bool, manager_reviewer_id: str | None,
                                peer_reviewer_ids: list[str],
                                upward_reviewer_ids: list[str]) -> list:
    """Las evaluaciones que cuelgan de la campaña, en el orden en que se crean.

    El orden es el que ve quien administra la campaña —autoevaluación, manager,
    pares, upward— y se conserva.
    """
    def nueva(reviewer_id: str, rtype: str) -> PerformanceReview:
        return PerformanceReview(
            id=str(_uuid.uuid4()),
            cycle_id=cycle_id,
            campaign_id=camp.id,
            reviewee_id=subject_id,
            reviewer_id=reviewer_id,
            review_type=rtype,
            answers_json={},
        )

    salida = []
    if self_review:
        salida.append(nueva(subject_id, "self"))
    if manager_reviewer_id:
        salida.append(nueva(manager_reviewer_id, "manager"))
    salida += [nueva(rid, "peer") for rid in peer_reviewer_ids]
    salida += [nueva(rid, "upward") for rid in upward_reviewer_ids]
    return salida


def create_campaign(
    db: Session, *,
    cycle_id: str, subject_id: str, created_by: str,
    self_review: bool = True,
    manager_reviewer_id: str | None = None,
    peer_reviewer_ids: list[str] | None = None,
    upward_reviewer_ids: list[str] | None = None,
    anonymity_threshold: int = 3,
    auto_activate: bool = True,
) -> Review360Campaign:
    """Crea una campaña 360° y todas las PerformanceReview asociadas en una sola
    operación. Valida elegibilidad de cada reviewer contra el organigrama."""
    peer_reviewer_ids = _sin_duplicados(peer_reviewer_ids)
    upward_reviewer_ids = _sin_duplicados(upward_reviewer_ids)

    _cycle, subject = _validar_campana(
        db, cycle_id, subject_id, self_review, manager_reviewer_id,
        peer_reviewer_ids, upward_reviewer_ids,
    )

    camp = Review360Campaign(
        id=str(_uuid.uuid4()),
        cycle_id=cycle_id, subject_id=subject_id,
        status=Review360CampaignStatus.active if auto_activate
               else Review360CampaignStatus.draft,
        # Nunca por debajo de 1: un umbral de cero desactivaria el anonimato sin
        # que nadie lo hubiera pedido.
        anonymity_threshold=max(1, int(anonymity_threshold)),
        created_by=created_by,
    )
    db.add(camp)
    db.flush()

    new_reviews = _evaluaciones_de_la_campana(
        camp, cycle_id, subject_id, self_review, manager_reviewer_id,
        peer_reviewer_ids, upward_reviewer_ids,
    )
    for r in new_reviews:
        db.add(r)

    # Notificaciones in-app a cada evaluador (omitimos si el ciclo aún está
    # en draft — el subject sólo debería recibir aviso cuando se "active").
    if camp.status == Review360CampaignStatus.active:
        _notify_reviewers(db, subject=subject, reviews=new_reviews)

    db.commit()
    db.refresh(camp)
    return camp


def _notify_reviewers(db: Session, *, subject: User, reviews: list[PerformanceReview]) -> None:
    """Encola Notification para cada reviewer y, si SMTP está configurado,
    envía además un email."""
    type_label = {
        "self":    "tu autoevaluación",
        "manager": "tu evaluación como manager",
        "peer":    "una evaluación entre pares",
        "upward":  "una evaluación upward",
    }
    # Pre-cargamos los reviewers para poder mandar email (si lo hay)
    reviewer_ids = list({r.reviewer_id for r in reviews})
    reviewers_by_id = {
        u.id: u for u in db.query(User).filter(User.id.in_(reviewer_ids)).all()
    } if reviewer_ids else {}

    # Import diferido para no romper si la infra de email cambia
    try:
        from app.services.notification_service import NotificationService
        send_email = NotificationService.send_email
    except Exception:  # pragma: no cover
        send_email = None

    for r in reviews:
        label = type_label.get(r.review_type, "una evaluación")
        title = (
            f"Tienes pendiente {label} para ti mismo"
            if r.review_type == "self"
            else f"Tienes pendiente {label} de {subject.full_name}"
        )
        body = "Accede al módulo de evaluaciones para completarla."
        db.add(Notification(
            user_id=r.reviewer_id,
            type=NotificationType.system,
            title=title,
            body=body,
            icon="⭐",
            color="#9b59b6",
            resource="performance_review",
            resource_id=r.id,
            action_url="/performance-reviews",
        ))
        # Email (best-effort, no bloquea si SMTP no está configurado)
        reviewer = reviewers_by_id.get(r.reviewer_id)
        if send_email and reviewer and getattr(reviewer, "email", None):
            html = (
                f"<p>Hola {reviewer.full_name},</p>"
                f"<p>{title}.</p>"
                f"<p>{body}</p>"
                f"<p><a href='/performance-reviews'>Abrir evaluaciones</a></p>"
            )
            try:
                send_email(to=reviewer.email, subject=title, html_body=html)
            except Exception as exc:  # pragma: no cover
                logger.warning(
                    "Email best-effort failed for reviewer=%s review=%s: %s",
                    reviewer.id, r.id, exc,
                )


def close_campaign(db: Session, camp: Review360Campaign) -> Review360Campaign:
    camp.status = Review360CampaignStatus.closed
    camp.closed_at = datetime.now(timezone.utc)
    db.commit()
    return camp


def serialize_campaign(camp: Review360Campaign, *, include_progress: bool = True) -> dict:
    out = {
        "id": camp.id, "cycle_id": camp.cycle_id,
        "subject_id": camp.subject_id,
        "subject_name": camp.subject.full_name if camp.subject else None,
        "status": camp.status.value if hasattr(camp.status, "value") else camp.status,
        "anonymity_threshold": camp.anonymity_threshold,
        "created_at": str(camp.created_at)[:16] if camp.created_at else None,
        "closed_at":  str(camp.closed_at)[:16]  if camp.closed_at  else None,
    }
    if include_progress:
        reviews = camp.reviews or []
        out["total_reviewers"] = len(reviews)
        out["submitted"] = sum(1 for r in reviews if r.status == ReviewStatus.submitted)
        out["pending"]   = sum(1 for r in reviews if r.status == ReviewStatus.pending)
        out["by_type"] = {
            t: sum(1 for r in reviews if r.review_type == t)
            for t in ("self", "manager", "peer", "upward")
        }
    return out


# ── Anonymized aggregation for the dashboard ──────────────────────────────────

def _is_rating_kind(kind) -> bool:
    val = kind.value if hasattr(kind, "value") else kind
    return val in ("rating_5", "rating_10", "scale_likert")


def _coerce_number(v):
    try:
        return float(v) if v is not None and v != "" else None
    except (TypeError, ValueError):
        return None


def aggregate_campaign(db: Session, camp: Review360Campaign) -> dict:
    """Construye el dashboard agregado de una campaña 360°.

    Estructura devuelta:
      {
        campaign: {...serialize_campaign},
        questions: [{id, key, label, kind, ...}],
        groups: {
          self|manager|peer|upward: {
            count, submitted_count, anonymized: bool,
            ratings_by_question: { key: {avg, min, max, n} },
            text_by_question:    { key: [{anonymous?: true, text: str}, ...] }
          }
        },
        comparison: {
          # solo para preguntas tipo rating: comparación self vs others
          key: { self: float|null, manager: float|null, peers: float|null, upward: float|null }
        }
      }

    Anonimización: cuando el grupo tiene < anonymity_threshold respuestas
    enviadas (excluyendo `self`, que siempre es 1), las respuestas de texto
    individuales se omiten y solo se exponen agregados numéricos.
    """
    questions = list_questions(db, camp.cycle_id)

    submitted = [r for r in (camp.reviews or []) if r.status == ReviewStatus.submitted]
    by_type: dict[str, list[PerformanceReview]] = {"self": [], "manager": [], "peer": [], "upward": []}
    for r in submitted:
        by_type.setdefault(r.review_type, []).append(r)

    threshold = camp.anonymity_threshold or 3
    groups = {}
    comparison: dict[str, dict] = {}

    for gtype, rvs in by_type.items():
        # `self` no tiene anonimización: siempre se muestra
        is_self = gtype == "self"
        anonymized = (not is_self) and (len(rvs) < threshold)

        ratings_agg: dict[str, dict] = {}
        text_agg:    dict[str, list] = {}

        for q in questions:
            if _is_rating_kind(q.kind):
                vals = [_coerce_number((r.answers_json or {}).get(q.key)) for r in rvs]
                vals = [v for v in vals if v is not None]
                if vals:
                    ratings_agg[q.key] = {
                        "avg": round(statistics.mean(vals), 2),
                        "min": min(vals),
                        "max": max(vals),
                        "n":   len(vals),
                    }
                    comparison.setdefault(q.key, {})
                    # Etiqueta de comparación: peers (plural), upward (plural), manager (singular), self
                    label = {"self": "self", "manager": "manager", "peer": "peers", "upward": "upward"}[gtype]
                    comparison[q.key][label] = round(statistics.mean(vals), 2)
            else:
                # text_short / text_long / yes_no
                texts = []
                for r in rvs:
                    v = (r.answers_json or {}).get(q.key)
                    if v in (None, ""):
                        continue
                    if anonymized:
                        # No exponemos el texto cuando el grupo es demasiado pequeño
                        continue
                    texts.append({"text": v})
                if texts or (not anonymized and rvs):
                    text_agg[q.key] = texts

        groups[gtype] = {
            "count": len(rvs),
            "anonymized": anonymized,
            "ratings_by_question": ratings_agg,
            "text_by_question":    text_agg,
        }

    return {
        "campaign": serialize_campaign(camp),
        "questions": [serialize_question(q) for q in questions],
        "groups": groups,
        "comparison": comparison,
        "anonymity_threshold": threshold,
        "total_submitted": len(submitted),
        "total_assigned":  len(camp.reviews or []),
    }


def history_360_for_subject(db: Session, subject_id: str) -> dict:
    """Histórico de campañas 360° para un subject a lo largo de varios ciclos.

    Para cada campaña con respuestas enviadas, devuelve una serie ordenada
    cronológicamente por fecha del ciclo, con la media global por pregunta de
    rating (todas las respuestas excepto self) — lo que permite trazar la
    evolución como un line chart en el frontend.
    """
    subject = db.query(User).filter(User.id == subject_id).first()
    if not subject:
        return {"subject_id": subject_id, "subject_name": None, "series": []}

    camps = (
        db.query(Review360Campaign)
        .options(
            joinedload(Review360Campaign.cycle),
            joinedload(Review360Campaign.reviews),
        )
        .filter(Review360Campaign.subject_id == subject_id)
        .order_by(Review360Campaign.created_at.asc())
        .all()
    )

    # Batch-load: una sola query para todas las preguntas de todos los ciclos
    # involucrados (resuelve el N+1 que existía al llamar list_questions por
    # cada campaña).
    cycle_ids = {c.cycle_id for c in camps if c.cycle_id}
    questions_by_cycle: dict[str, list[ReviewQuestion]] = {cid: [] for cid in cycle_ids}
    if cycle_ids:
        for q in (
            db.query(ReviewQuestion)
            .filter(ReviewQuestion.cycle_id.in_(cycle_ids))
            .order_by(ReviewQuestion.order, ReviewQuestion.label)
            .all()
        ):
            questions_by_cycle.setdefault(q.cycle_id, []).append(q)

    series = []
    for camp in camps:
        questions = questions_by_cycle.get(camp.cycle_id, [])
        rating_qs = [q for q in questions if _is_rating_kind(q.kind)]
        # Media de "others" (excluye self) por pregunta
        per_question = {}
        for q in rating_qs:
            others = [
                _coerce_number((r.answers_json or {}).get(q.key))
                for r in (camp.reviews or [])
                if r.status == ReviewStatus.submitted and r.review_type != "self"
            ]
            others = [v for v in others if v is not None]
            self_vals = [
                _coerce_number((r.answers_json or {}).get(q.key))
                for r in (camp.reviews or [])
                if r.status == ReviewStatus.submitted and r.review_type == "self"
            ]
            self_vals = [v for v in self_vals if v is not None]
            if not others and not self_vals:
                continue
            per_question[q.key] = {
                "label": q.label,
                "scale_max": q.scale_max or (10 if q.kind == QuestionKind.rating_10 else 5),
                "self":   round(statistics.mean(self_vals), 2) if self_vals else None,
                "others": round(statistics.mean(others), 2) if others else None,
            }
        if not per_question:
            continue
        series.append({
            "campaign_id": camp.id,
            "cycle_id": camp.cycle_id,
            "cycle_name": camp.cycle.name if camp.cycle else None,
            "created_at": str(camp.created_at)[:10] if camp.created_at else None,
            "status": camp.status.value if hasattr(camp.status, "value") else camp.status,
            "ratings": per_question,
        })

    return {
        "subject_id": subject_id,
        "subject_name": subject.full_name,
        "series": series,
    }


def can_launch_campaign_for(db: Session, *, current_user: User, subject_id: str) -> bool:
    """Quién puede lanzar campañas 360°:

      - Admin / HR / superadmin → para cualquiera
      - PM / Team Lead         → solo si el subject los tiene como manager directo
    """
    if getattr(current_user, "is_superadmin", False):
        return True
    role = current_user.role
    if role in ("admin", "hr"):
        return True
    if role in ("pm", "team_lead"):
        subject = db.query(User).filter(User.id == subject_id).first()
        return bool(subject and subject.manager_id == current_user.id)
    return False
