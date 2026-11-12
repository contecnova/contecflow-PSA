"""Ciclos de evaluacion y sus preguntas: alta, siembra, clonado, edicion y estado del ciclo.

Parte de `app.services.performance_service` (auditoria 2026-11, #24): se partio por responsabilidad
sin cambiar el codigo. El paquete reexporta todos los nombres.
"""
from sqlalchemy.orm import Session
import uuid as _uuid
from app.models.performance import ReviewCycle, ReviewCycleStatus, ReviewQuestion, QuestionKind
from app.core.errores import ErrorDeDominio

from app.services.performance_service.guardas import pregunta_propia


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
                 organization_id: str | None = None,
                 **kwargs) -> ReviewCycle:
    """Crea un ciclo de evaluacion.

    Auditoria 2026-08: `organization_id` no se ponia **en ninguna** de las nueve
    creaciones de este modulo, y la columna existe y es la que usa la guarda de
    tenant. Efecto medido: un ciclo creado por el endpoint quedaba con
    `organization_id = NULL`, y como el filtro de `TenantSession` es
    `organization_id == org`, una fila NULL no la ve nadie salvo un superadmin.
    Es decir, **se creaba el ciclo y desaparecia**: `GET /performance/cycles`
    devolvia cero a su propio creador. El modulo entero de evaluaciones estaba
    muerto en un despliegue con tenant, y no habia error en ningun log.

    Un ciclo no tiene fila padre de la que heredarla, asi que la trae quien
    llama. Las preguntas, evaluaciones y campañas la heredan de su ciclo.
    """
    c = ReviewCycle(id=str(_uuid.uuid4()), created_by=created_by,
                    organization_id=organization_id, **kwargs)
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
            organization_id=cycle.organization_id,
            key=q["key"], label=q["label"], hint=q["hint"],
            kind=q["kind"], order=q["order"], required=q["required"],
            scale_min=q["scale_min"], scale_max=q["scale_max"],
        ))


def clone_questions(db: Session, *, source_cycle_id: str, dest_cycle: ReviewCycle) -> int:
    src = list_questions(db, source_cycle_id)
    for q in src:
        db.add(ReviewQuestion(
            id=str(_uuid.uuid4()), cycle_id=dest_cycle.id,
            organization_id=dest_cycle.organization_id,
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
    q = ReviewQuestion(
        id=str(_uuid.uuid4()), cycle_id=cycle.id,
        organization_id=cycle.organization_id, **data)
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


# ── Las mismas operaciones, como las piden los endpoints: validan y confirman ─

def anadir_pregunta(db: Session, cycle_id: str, data: dict) -> ReviewQuestion:
    c = get_cycle(db, cycle_id)
    if not c:
        raise ErrorDeDominio(404, "Ciclo no encontrado")
    try:
        q = add_question(db, c, data)
    except ValueError as e:
        raise ErrorDeDominio(400, str(e))
    db.commit()
    db.refresh(q)
    return q


def actualizar_pregunta(db: Session, user, question_id: str, updates: dict) -> ReviewQuestion:
    q = pregunta_propia(db, user, question_id)
    try:
        q = update_question(db, q, updates)
    except ValueError as e:
        raise ErrorDeDominio(400, str(e))
    db.commit()
    db.refresh(q)
    return q


def borrar_pregunta(db: Session, user, question_id: str) -> None:
    q = pregunta_propia(db, user, question_id)
    try:
        delete_question(db, q)
    except ValueError as e:
        raise ErrorDeDominio(400, str(e))
    db.commit()


def sembrar_preguntas_por_defecto(db: Session, cycle_id: str) -> None:
    c = get_cycle(db, cycle_id)
    if not c:
        raise ErrorDeDominio(404, "Ciclo no encontrado")
    if c.status != ReviewCycleStatus.draft:
        raise ErrorDeDominio(400, "Solo se pueden añadir preguntas a ciclos en borrador")
    seed_default_questions_for_cycle(db, c)
    db.commit()


def clonar_preguntas(db: Session, cycle_id: str, source_cycle_id: str) -> int:
    dest = get_cycle(db, cycle_id)
    if not dest:
        raise ErrorDeDominio(404, "Ciclo destino no encontrado")
    if dest.status != ReviewCycleStatus.draft:
        raise ErrorDeDominio(400, "Solo se pueden añadir preguntas a ciclos en borrador")
    src = get_cycle(db, source_cycle_id)
    if not src:
        raise ErrorDeDominio(404, "Ciclo origen no encontrado")
    n = clone_questions(db, source_cycle_id=source_cycle_id, dest_cycle=dest)
    db.commit()
    return n


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


def serialize_question(q: ReviewQuestion) -> dict:
    return {
        "id": q.id, "cycle_id": q.cycle_id,
        "key": q.key, "label": q.label, "hint": q.hint,
        "kind": q.kind.value if hasattr(q.kind, "value") else q.kind,
        "order": q.order, "required": q.required,
        "scale_min": q.scale_min, "scale_max": q.scale_max,
    }
