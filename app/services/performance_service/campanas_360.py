"""Campanas 360: validacion, alta, avisos a evaluadores, cierre, agregado e historial.

Parte de `app.services.performance_service` (auditoria 2026-11, #24): se partio por responsabilidad
sin cambiar el codigo. El paquete reexporta todos los nombres.
"""
from sqlalchemy.orm import Session, joinedload
from datetime import datetime, timezone
import logging
import statistics
import uuid as _uuid
from app.models.performance import (
    PerformanceReview,
    ReviewCycleStatus,
    ReviewStatus,
    ReviewQuestion,
    QuestionKind,
    Review360Campaign,
    Review360CampaignStatus,
)
from app.models.user import User
from app.models.enterprise import Notification, NotificationType

from app.services.performance_service.evaluaciones import eligible_reviewers
from app.services.performance_service.ciclos_y_preguntas import (
    get_cycle,
    list_questions,
    serialize_question,
)


logger = logging.getLogger("app.services.performance_service")


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
            organization_id=camp.organization_id,
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
        organization_id=_cycle.organization_id,
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
        logger.debug("_notify_reviewers: excepcion ignorada", exc_info=True)
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
                from app.core.segundo_plano import encolar
                encolar(send_email, to=reviewer.email, subject=title, html_body=html)
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
