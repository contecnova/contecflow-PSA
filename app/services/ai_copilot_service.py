"""AI Copilot contextual suggestions service.

Provides inline AI suggestions for Gantt scheduling, timesheet anomaly
detection and service-desk KB article recommendations.
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timedelta
from typing import Dict

from fastapi import HTTPException
from sqlalchemy.orm import Session
from app.models.imputation import Imputation
from app.models.project import Project
from app.models.service_desk import Ticket, KBArticle
from app.models.task import Task

logger = logging.getLogger(__name__)


def get_ai_gantt_suggestions(project_id: str, db: Session, current_user=None) -> dict:
    # Multi-tenant: solo permitimos sugerencias sobre proyectos visibles para el
    # caller. Superadmin bypassa el filtro org. Sin esta verificación un user
    # de org A podría ver tasks/títulos de org B vía suggestions.
    proj = db.query(Project).filter(Project.id == project_id).first()
    if not proj:
        raise HTTPException(404, "Project not found")
    if current_user is not None and not bool(getattr(current_user, "is_superadmin", False)):
        cu_org = getattr(current_user, "organization_id", None)
        if cu_org and getattr(proj, "organization_id", None) and proj.organization_id != cu_org:
            raise HTTPException(404, "Project not found")

    tasks = db.query(Task).filter(Task.project_id == project_id).all()
    today = date.today()
    suggestions = []

    for t in tasks:
        status_val = str(getattr(t.status, "value", t.status))
        if status_val in ("done", "closed", "cancelled"):
            continue

        if t.due_date and t.due_date < today:
            overdue_days = (today - t.due_date).days
            # Item #66: outputs en español (sistema mayoritariamente ES).
            suggestions.append({
                "task_id": t.id, "task_title": t.title,
                "type": "overdue",
                "severity": "high" if overdue_days > 7 else "medium",
                "message": f"La tarea lleva {overdue_days} día(s) de retraso.",
                "suggestions": [
                    "Reasignar a un recurso disponible",
                    "Dividir en sub-tareas para desbloquear el progreso",
                    "Revisar alcance — diferir ítems no críticos",
                ],
            })
        elif (hasattr(t, "start_date") and t.start_date and t.due_date
              and t.start_date < today < t.due_date):
            total_days = (t.due_date - t.start_date).days or 1
            elapsed_pct = (today - t.start_date).days / total_days
            progress = getattr(t, "progress", None) or 0
            if elapsed_pct >= 0.5 and progress < 20:
                suggestions.append({
                    "task_id": t.id, "task_title": t.title,
                    "type": "stalled",
                    "severity": "medium",
                    "message": f"{int(elapsed_pct*100)}% de la duración consumida pero solo {progress}% completada.",
                    "suggestions": [
                        "Revisar bloqueos en los comentarios",
                        "Agendar sincronización rápida con el responsable",
                        "Considerar ejecución paralela si las dependencias lo permiten",
                    ],
                })

    return {
        "project_id": project_id,
        "project_name": proj.name,
        "suggestions_count": len(suggestions),
        "suggestions": suggestions,
        "analysed_at": str(datetime.utcnow()),
    }


def get_ai_timesheet_anomalies(user_id: str, db: Session, current_user=None) -> dict:
    # Multi-tenant: solo se permite consultar anomalías propias O de users de la
    # misma organización (managers). Superadmin bypassa. Sin este check, un
    # employee podría enumerar imputaciones de cualquier user del sistema vía
    # /ai/suggestions/timesheets/{cualquier_uuid}.
    if current_user is not None:
        is_super = bool(getattr(current_user, "is_superadmin", False))
        cu_id = getattr(current_user, "id", None)
        if not is_super and str(user_id) != str(cu_id):
            from app.models.user import User as _User  # noqa: PLC0415
            target = db.query(_User).filter(_User.id == user_id).first()
            if not target:
                raise HTTPException(404, "User not found")
            cu_org = getattr(current_user, "organization_id", None)
            if cu_org and getattr(target, "organization_id", None) != cu_org:
                raise HTTPException(404, "User not found")

    cutoff = date.today() - timedelta(days=30)
    entries = db.query(Imputation).filter(
        Imputation.user_id == user_id,
        Imputation.date >= cutoff,
    ).order_by(Imputation.date).all()

    anomalies = []
    daily_hours: Dict[str, float] = {}
    for e in entries:
        k = str(e.date)
        daily_hours[k] = daily_hours.get(k, 0) + (e.hours or 0)

    # Item #67: anomalía basada en el patrón del propio usuario, no en un
    # umbral global rígido. Calculamos media + desviación típica sobre días
    # con imputación >0 y marcamos los días que se desvían >2σ (regla 95%).
    # Mantenemos el umbral 12h como límite duro absoluto para casos sin
    # suficiente histórico (n<7).
    import statistics as _stats  # noqa: PLC0415
    positive = [h for h in daily_hours.values() if h > 0]
    if len(positive) >= 7:
        mean_h = _stats.mean(positive)
        stdev_h = _stats.pstdev(positive) or 0.0
        threshold = max(12.0, mean_h + 2 * stdev_h) if stdev_h > 0 else 12.0
        baseline_note = f"media {mean_h:.1f}h ± {stdev_h:.1f}h, umbral={threshold:.1f}h"
    else:
        threshold = 12.0
        baseline_note = "umbral fijo 12h (sin histórico suficiente, n<7)"

    for day, hours in daily_hours.items():
        if hours > threshold:
            anomalies.append({
                "type": "high_hours", "date": day, "value": hours,
                "message": (
                    f"{hours}h imputadas el {day} — supera el umbral "
                    f"({baseline_note})."
                ),
                "suggestion": "Verifica que las horas sean correctas o repártelas si se cargaron en bloque.",
            })

    if entries:
        prev_date = entries[0].date
        for e in entries[1:]:
            gap_days = (e.date - prev_date).days
            if gap_days > 7:
                anomalies.append({
                    "type": "gap", "date": str(prev_date), "value": gap_days,
                    "message": f"{gap_days} días sin imputaciones",
                    "suggestion": "¿Faltan imputaciones del periodo? Completa los partes.",
                })
            prev_date = e.date

    proj_ids = {e.project_id for e in entries if e.project_id}
    closed_projs = db.query(Project).filter(
        Project.id.in_(list(proj_ids)),
        Project.status.in_(["closed", "cancelled", "archived"]),
    ).all()
    closed_ids = {p.id for p in closed_projs}
    if closed_ids:
        anomalies.append({
            "type": "closed_project_billing",
            "project_ids": list(closed_ids),
            "message": "Imputaciones encontradas en proyectos cerrados/cancelados",
            "suggestion": "Revisa y reasigna al proyecto activo correcto.",
        })

    return {
        "user_id": user_id,
        "period": {"from": str(cutoff), "to": str(date.today())},
        "total_entries": len(entries),
        "anomalies_count": len(anomalies),
        "anomalies": anomalies,
        "analysed_at": str(datetime.utcnow()),
    }


def get_ai_ticket_kb_suggestions(ticket_id: str, db: Session) -> dict:

    ticket = db.query(Ticket).filter(Ticket.id == ticket_id).first()
    if not ticket:
        raise HTTPException(404, "Ticket not found")

    text = f"{ticket.title or ''} {ticket.description or ''}".lower()
    words = set(w for w in text.split() if len(w) > 3)
    articles = db.query(KBArticle).filter(KBArticle.is_published == True).limit(200).all()

    scored = []
    for art in articles:
        art_text = f"{art.title or ''} {art.content or ''}".lower()
        matches = sum(1 for w in words if w in art_text)
        if matches > 0:
            scored.append({
                "article_id": art.id,
                "title": art.title,
                "score": matches,
                "url": f"/api/v1/sd/kb/articles/{art.id}",
            })
    scored.sort(key=lambda x: -x["score"])

    return {
        "ticket_id": ticket_id,
        "ticket_title": ticket.title,
        "suggestions": scored[:5],
        "analysed_at": str(datetime.utcnow()),
    }
