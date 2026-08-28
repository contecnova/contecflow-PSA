"""Recordatorios automáticos a evaluadores con reviews pendientes.

Estrategia: una notificación in-app diaria por reviewer y ciclo cuando el
ciclo se acerca al cierre (`end_date - today <= REMINDER_WINDOW_DAYS`) o
cuando el ciclo lleva mucho tiempo activo sin enviar respuesta.

Idempotencia: antes de crear, comprobamos si ya existe una notificación
similar dentro de las últimas 20h para evitar spam.
"""
from __future__ import annotations
from datetime import date, datetime, timedelta, timezone
import logging

from sqlalchemy.orm import Session

from app.models.performance import (
    ReviewCycle, ReviewCycleStatus, PerformanceReview, ReviewStatus,
)
from app.models.enterprise import Notification, NotificationType
from app.models.user import User
from app.core import timeutil

logger = logging.getLogger(__name__)

REMINDER_WINDOW_DAYS = 7      # avisamos cuando el ciclo cierra en N días o menos
DEDUP_WINDOW_HOURS   = 20     # no reenviamos al mismo (user, cycle) en N horas


def _has_recent_reminder(db: Session, *, user_id: str, cycle_id: str) -> bool:
    cutoff = datetime.now(timezone.utc) - timedelta(hours=DEDUP_WINDOW_HOURS)
    q = (
        db.query(Notification)
        .filter(
            Notification.user_id == user_id,
            Notification.resource == "performance_reminder",
            Notification.resource_id == cycle_id,
            Notification.created_at >= cutoff,
        )
        .first()
    )
    return q is not None


def send_pending_review_reminders(db: Session, *, today: date | None = None) -> dict:
    """Envía recordatorios a reviewers con reviews pendientes en ciclos próximos
    al cierre. Devuelve estadísticas de la ejecución."""
    today = today or timeutil.today()
    horizon = today + timedelta(days=REMINDER_WINDOW_DAYS)

    cycles = (
        db.query(ReviewCycle)
        .filter(
            ReviewCycle.status == ReviewCycleStatus.active,
            # Ciclos con end_date dentro de la ventana O sin end_date pero antiguos
            (
                (ReviewCycle.end_date.isnot(None) & (ReviewCycle.end_date <= horizon))
                | (ReviewCycle.end_date.is_(None))
            ),
        )
        .all()
    )

    sent = 0
    skipped = 0
    cycles_processed = 0

    for c in cycles:
        cycles_processed += 1
        # Si end_date es None, solo enviamos si el ciclo lleva activo > 30 días
        if c.end_date is None:
            created = c.created_at
            if created is None:
                continue
            created_d = created.date() if hasattr(created, "date") else created
            if (today - created_d).days < 30:
                continue
            days_left_label = "sin fecha de cierre"
        else:
            days_left = (c.end_date - today).days
            if days_left < 0:
                continue  # ciclo vencido, lo gestionará HR a mano
            days_left_label = (
                "hoy" if days_left == 0
                else f"en {days_left} día(s) ({c.end_date.isoformat()})"
            )

        # Agrupamos pending por reviewer
        pending = (
            db.query(PerformanceReview)
            .filter(
                PerformanceReview.cycle_id == c.id,
                PerformanceReview.status == ReviewStatus.pending,
            )
            .all()
        )
        by_reviewer: dict[str, list[PerformanceReview]] = {}
        for r in pending:
            by_reviewer.setdefault(r.reviewer_id, []).append(r)

        for reviewer_id, revs in by_reviewer.items():
            if _has_recent_reminder(db, user_id=reviewer_id, cycle_id=c.id):
                skipped += 1
                continue
            n = len(revs)
            title = (
                f"Tienes {n} evaluación pendiente — cierra {days_left_label}"
                if n == 1
                else f"Tienes {n} evaluaciones pendientes — el ciclo cierra {days_left_label}"
            )
            db.add(Notification(
                user_id=reviewer_id,
                type=NotificationType.system,
                title=title,
                body=f"Ciclo: {c.name}. Accede al módulo de evaluaciones para completarlas.",
                icon="⏰",
                color="#f59e0b",
                resource="performance_reminder",
                resource_id=c.id,
                action_url="/performance-reviews",
            ))
            sent += 1

    db.commit()
    return {
        "cycles_processed": cycles_processed,
        "reminders_sent":   sent,
        "reminders_skipped_dedup": skipped,
        "ran_at": datetime.now(timezone.utc).isoformat(),
    }


# ── KPIs por ciclo y agregados ────────────────────────────────────────────────

def cycle_kpis(db: Session, cycle_id: str) -> dict:
    """Métricas operativas de un ciclo: completado, días al cierre, breakdown."""
    c = db.query(ReviewCycle).filter(ReviewCycle.id == cycle_id).first()
    if not c:
        return {}

    reviews = list(c.reviews or [])
    total = len(reviews)
    submitted = [r for r in reviews if r.status == ReviewStatus.submitted]
    pending   = [r for r in reviews if r.status == ReviewStatus.pending]

    # Tiempo medio de completado (created_at → submitted_at) en días
    days = []
    for r in submitted:
        if r.created_at and r.submitted_at:
            delta = (r.submitted_at - r.created_at).total_seconds() / 86400.0
            if delta >= 0:
                days.append(delta)
    avg_days = round(sum(days) / len(days), 2) if days else None

    # Breakdown por tipo de review
    by_type = {}
    for t in ("self", "manager", "peer", "upward"):
        sub = [r for r in reviews if r.review_type == t]
        if not sub:
            continue
        by_type[t] = {
            "total": len(sub),
            "submitted": sum(1 for r in sub if r.status == ReviewStatus.submitted),
        }

    # Reviewers que tienen >=1 review pendiente (top stalkers a perseguir)
    pending_by_user: dict[str, int] = {}
    for r in pending:
        pending_by_user[r.reviewer_id] = pending_by_user.get(r.reviewer_id, 0) + 1
    user_names = {}
    if pending_by_user:
        users = db.query(User).filter(User.id.in_(pending_by_user.keys())).all()
        user_names = {u.id: u.full_name for u in users}
    top_stalled = sorted(
        ({"user_id": uid, "user_name": user_names.get(uid, "?"), "pending": n}
         for uid, n in pending_by_user.items()),
        key=lambda x: -x["pending"],
    )[:10]

    today = timeutil.today()
    days_to_close = (c.end_date - today).days if c.end_date else None

    return {
        "cycle_id": c.id,
        "cycle_name": c.name,
        "status": c.status.value if hasattr(c.status, "value") else c.status,
        "total_reviews": total,
        "submitted": len(submitted),
        "pending":   len(pending),
        "completion_rate": round(len(submitted) / total * 100, 1) if total else 0.0,
        "avg_days_to_submit": avg_days,
        "by_type": by_type,
        "days_to_close": days_to_close,
        "end_date": c.end_date.isoformat() if c.end_date else None,
        "top_stalled_reviewers": top_stalled,
    }


def org_perf_kpis(db: Session) -> dict:
    """KPIs agregados a nivel organización para el panel de HR."""
    cycles = db.query(ReviewCycle).all()
    active   = [c for c in cycles if c.status == ReviewCycleStatus.active]
    closed   = [c for c in cycles if c.status == ReviewCycleStatus.closed]

    # Completion global solo sobre ciclos activos
    total_active = sum(len(c.reviews or []) for c in active)
    submitted_active = sum(
        sum(1 for r in (c.reviews or []) if r.status == ReviewStatus.submitted)
        for c in active
    )
    pending_active = total_active - submitted_active

    # Ciclos atascados: activos con completion <50% y end_date pasada o
    # creados hace más de 45 días sin mucho avance
    today = timeutil.today()
    stalled = []
    for c in active:
        total = len(c.reviews or [])
        if total == 0:
            continue
        sub = sum(1 for r in c.reviews if r.status == ReviewStatus.submitted)
        rate = sub / total * 100
        is_overdue = c.end_date is not None and c.end_date < today
        is_old = (
            c.created_at is not None and
            (today - (c.created_at.date() if hasattr(c.created_at, "date") else c.created_at)).days > 45
        )
        if rate < 50 and (is_overdue or is_old):
            stalled.append({
                "cycle_id": c.id, "cycle_name": c.name,
                "completion_rate": round(rate, 1),
                "end_date": c.end_date.isoformat() if c.end_date else None,
                "overdue": is_overdue,
            })

    # Tiempo medio de cierre del ciclo (created_at → cualquier submitted)
    # más útil: tiempo medio de completado de reviews enviadas en ciclos cerrados
    closed_days = []
    for c in closed:
        for r in (c.reviews or []):
            if r.status == ReviewStatus.submitted and r.created_at and r.submitted_at:
                d = (r.submitted_at - r.created_at).total_seconds() / 86400.0
                if d >= 0:
                    closed_days.append(d)
    avg_closed = round(sum(closed_days) / len(closed_days), 2) if closed_days else None

    return {
        "total_cycles": len(cycles),
        "active_cycles": len(active),
        "closed_cycles": len(closed),
        "draft_cycles": sum(1 for c in cycles if c.status == ReviewCycleStatus.draft),
        "total_reviews_active": total_active,
        "submitted_reviews_active": submitted_active,
        "pending_reviews_active": pending_active,
        "global_completion_rate": (
            round(submitted_active / total_active * 100, 1) if total_active else 0.0
        ),
        "stalled_cycles": stalled,
        "avg_days_to_submit_closed": avg_closed,
    }


# ── APScheduler hook ─────────────────────────────────────────────────────────

def run_perf_reminders_job() -> None:
    """Punto de entrada para APScheduler. Abre su propia sesión."""
    from app.db.session import SessionLocal
    db = SessionLocal()
    try:
        logger.info("perf-reminders job: start")
        result = send_pending_review_reminders(db)
        logger.info(
            "perf-reminders job: end cycles=%s sent=%s skipped=%s",
            result.get("cycles_processed"),
            result.get("reminders_sent"),
            result.get("reminders_skipped_dedup"),
        )
    except Exception:
        logger.exception("perf-reminders job: failed")
        raise
    finally:
        db.close()
