"""AI Copilot contextual suggestions service.

Provides inline AI suggestions for Gantt scheduling, timesheet anomaly
detection and service-desk KB article recommendations.
"""
from __future__ import annotations

import logging
from datetime import timedelta
from app.models.task import ESTADOS_DE_TAREA_TERMINADOS
from app.core.timeutil import utcnow
from typing import Dict

from sqlalchemy.orm import Session
from app.models.imputation import Imputation
from app.models.project import Project
from app.models.task import Task
from app.core import timeutil
from app.core.errores import ErrorDeDominio

logger = logging.getLogger(__name__)


def get_ai_gantt_suggestions(project_id: str, db: Session, current_user=None) -> dict:
    # Multi-tenant: solo permitimos sugerencias sobre proyectos visibles para el
    # caller. Superadmin bypassa el filtro org. Sin esta verificación un user
    # de org A podría ver tasks/títulos de org B vía suggestions.
    proj = db.query(Project).filter(Project.id == project_id).first()
    if not proj:
        raise ErrorDeDominio(404, "Project not found")
    if current_user is not None and not bool(getattr(current_user, "is_superadmin", False)):
        cu_org = getattr(current_user, "organization_id", None)
        if cu_org and getattr(proj, "organization_id", None) and proj.organization_id != cu_org:
            raise ErrorDeDominio(404, "Project not found")

    tasks = db.query(Task).filter(Task.project_id == project_id).all()
    today = timeutil.today()
    suggestions = []

    for t in tasks:
        status_val = str(getattr(t.status, "value", t.status))
        if status_val in ESTADOS_DE_TAREA_TERMINADOS:
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
        "analysed_at": str(utcnow()),
    }


def _autorizar_consulta_de_anomalias(db: Session, user_id: str, current_user) -> None:
    """Sólo las propias, o las de alguien de la misma organización.

    Sin esta comprobación un empleado podría enumerar las imputaciones de
    cualquier usuario del sistema con
    `/ai/suggestions/timesheets/{cualquier_uuid}`.

    El usuario de otra organización se responde con **404 y no 403**: un 403
    confirmaría que ese identificador existe.
    """
    if current_user is None or bool(getattr(current_user, "is_superadmin", False)):
        return
    if str(user_id) == str(getattr(current_user, "id", None)):
        return

    from app.models.user import User as _User

    objetivo = db.query(_User).filter(_User.id == user_id).first()
    if not objetivo:
        raise ErrorDeDominio(404, "User not found")
    organizacion = getattr(current_user, "organization_id", None)
    if organizacion and getattr(objetivo, "organization_id", None) != organizacion:
        raise ErrorDeDominio(404, "User not found")


def _umbral_de_horas(horas_por_dia: dict) -> tuple[float, str]:
    """El umbral de «demasiadas horas en un día», y cómo se ha obtenido.

    Item #67: el umbral sale del patrón **del propio usuario**, no de un número
    global. Media más dos desviaciones típicas sobre los días con imputación
    —la regla del 95 %—, con 12 h como suelo duro: por debajo de eso no es una
    anomalía por mucho que se salga de la media de quien imputa dos horas al día.

    Con menos de siete días de histórico no hay muestra para hablar de
    desviación, y se usa el umbral fijo.
    """
    import statistics as _stats

    positivos = [h for h in horas_por_dia.values() if h > 0]
    if len(positivos) < 7:
        return 12.0, "umbral fijo 12h (sin histórico suficiente, n<7)"

    media = _stats.mean(positivos)
    desviacion = _stats.pstdev(positivos) or 0.0
    umbral = max(12.0, media + 2 * desviacion) if desviacion > 0 else 12.0
    return umbral, f"media {media:.1f}h ± {desviacion:.1f}h, umbral={umbral:.1f}h"


def _huecos_de_imputacion(entries) -> list[dict]:
    """Saltos de más de una semana entre imputaciones consecutivas."""
    if not entries:
        return []
    anomalias = []
    anterior = entries[0].date
    for e in entries[1:]:
        dias = (e.date - anterior).days
        if dias > 7:
            anomalias.append({
                "type": "gap", "date": str(anterior), "value": dias,
                "message": f"{dias} días sin imputaciones",
                "suggestion": "¿Faltan imputaciones del periodo? Completa los partes.",
            })
        anterior = e.date
    return anomalias


def _imputaciones_en_proyectos_cerrados(db: Session, entries) -> list[dict]:
    """Horas cargadas a proyectos que ya no admiten carga."""
    ids = {e.project_id for e in entries if e.project_id}
    if not ids:
        return []
    cerrados = db.query(Project).filter(
        Project.id.in_(list(ids)),
        Project.status.in_(["closed", "cancelled", "archived"]),
    ).all()
    if not cerrados:
        return []
    return [{
        "type": "closed_project_billing",
        "project_ids": [p.id for p in cerrados],
        "message": "Imputaciones encontradas en proyectos cerrados/cancelados",
        "suggestion": "Revisa y reasigna al proyecto activo correcto.",
    }]


def get_ai_timesheet_anomalies(user_id: str, db: Session, current_user=None) -> dict:
    """Anomalías en las imputaciones de los últimos 30 días de un usuario."""
    _autorizar_consulta_de_anomalias(db, user_id, current_user)

    corte = timeutil.today() - timedelta(days=30)
    entries = db.query(Imputation).filter(
        Imputation.user_id == user_id,
        Imputation.date >= corte,
    ).order_by(Imputation.date).all()

    horas_por_dia: Dict[str, float] = {}
    for e in entries:
        horas_por_dia[str(e.date)] = horas_por_dia.get(str(e.date), 0) + (e.hours or 0)

    umbral, nota = _umbral_de_horas(horas_por_dia)
    anomalias = [
        {
            "type": "high_hours", "date": dia, "value": horas,
            "message": f"{horas}h imputadas el {dia} — supera el umbral ({nota}).",
            "suggestion": (
                "Verifica que las horas sean correctas o repártelas si se cargaron en bloque."
            ),
        }
        for dia, horas in horas_por_dia.items() if horas > umbral
    ]
    anomalias += _huecos_de_imputacion(entries)
    anomalias += _imputaciones_en_proyectos_cerrados(db, entries)

    return {
        "user_id": user_id,
        "period": {"from": str(corte), "to": str(timeutil.today())},
        "total_entries": len(entries),
        "anomalies_count": len(anomalias),
        "anomalies": anomalias,
        "analysed_at": str(utcnow()),
    }

