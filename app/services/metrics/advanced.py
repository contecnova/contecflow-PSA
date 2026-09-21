"""Advanced metrics: forecast_revenue, burnout_index."""
from datetime import date, timedelta
from typing import Optional
from sqlalchemy import func
from sqlalchemy.orm import Session

from . import register_metric
from app.core import timeutil


def _ingreso_de_pipeline(db: Session, d_from: date) -> float:
    """Oportunidades abiertas, ponderadas por su probabilidad de cierre.

    Ponderar es lo que hace que esto sea un forecast y no una lista de deseos:
    una oportunidad al 20 % aporta una quinta parte de su importe.
    """
    from app.models.pipeline import Opportunity

    return sum(
        (opp.expected_revenue or 0) * (opp.probability or 0) / 100
        for opp in db.query(Opportunity).filter(
            Opportunity.stage.notin_(["won", "lost"]),
            Opportunity.created_at >= d_from,
        ).all()
        if opp.created_at
    )


def _ingreso_de_proyectos(db: Session, d_from: date, d_to: date,
                          project_ids: Optional[list[str]]) -> float:
    """Horas que quedan por imputar en proyectos activos, a su tarifa.

    Las imputaciones se traen **en una sola consulta agrupada** y no una por
    proyecto: con una cartera grande, lo segundo son cientos de viajes a la
    base de datos para sumar un número.
    """
    from app.models.imputation import Imputation
    from app.models.project import Project

    q = db.query(Project).filter(Project.status == "active")
    if project_ids is not None:
        q = q.filter(Project.id.in_(project_ids))
    proyectos = q.all()

    facturables = [p.id for p in proyectos if p.estimated_hours and p.billing_rate]
    if not facturables:
        return 0.0

    imputadas = {
        fila[0]: fila[1] or 0
        for fila in db.query(Imputation.project_id, func.sum(Imputation.hours))
        .filter(
            Imputation.project_id.in_(facturables),
            Imputation.date.between(d_from, d_to),
        )
        .group_by(Imputation.project_id).all()
    }
    return sum(
        max(0, p.estimated_hours - imputadas.get(p.id, 0)) * p.billing_rate
        for p in proyectos if p.estimated_hours and p.billing_rate
    )


def _ingreso_de_contratos(db: Session, hoy: date, project_ids: Optional[list[str]]) -> float:
    """Lo que queda por devengar de los contratos vigentes.

    Se prorratea el importe anual a días: es una aproximación declarada, y la
    alternativa —leer el calendario de facturación real— es otra métrica.
    """
    from app.models.pipeline import Contract

    q = db.query(Contract).filter(Contract.status == "active", Contract.end_date >= hoy)
    if project_ids is not None:
        q = q.filter(Contract.project_id.in_(project_ids))

    total = 0.0
    for contrato in q.all():
        if not contrato.end_date:
            continue
        dias = (contrato.end_date - hoy).days
        if dias > 0:
            total += ((contrato.total_amount or 0) / 12 / 30) * dias
    return total


@register_metric("forecast_revenue")
def metric_forecast_revenue(
    db: Session,
    d_from: date,
    d_to: date,
    top_n: int,
    project_id: Optional[str] = None,
    user_id: Optional[str] = None,
    project_ids: Optional[list[str]] = None,
    **kwargs
) -> tuple[list[dict], dict]:
    """Forecast de ingresos a 90 días: pipeline + proyectos activos + contratos.

    Devuelve vacío si falta algún modelo: esta métrica vive en un catálogo del
    que se piden varias a la vez, y una que reviente tumbaría la pantalla.
    """
    try:
        hoy = timeutil.today()
        DIAS = 90

        pipeline = _ingreso_de_pipeline(db, d_from)
        proyectos = _ingreso_de_proyectos(db, d_from, d_to, project_ids)
        contratos = _ingreso_de_contratos(db, hoy, project_ids)
        total = pipeline + proyectos + contratos

        def porcentaje(parte: float) -> float:
            return round(parte / total * 100, 1) if total > 0 else 0

        filas = [
            {"label": "Ingreso pipeline (ponderado)", "value": round(pipeline, 0),
             "percentage": porcentaje(pipeline), "type": "pipeline"},
            {"label": "Ingreso proyectos activos", "value": round(proyectos, 0),
             "percentage": porcentaje(proyectos), "type": "projects"},
            {"label": "Ingreso contratos vigentes", "value": round(contratos, 0),
             "percentage": porcentaje(contratos), "type": "contracts"},
        ]
        return filas, {"forecast_days": DIAS, "forecast_end": str(hoy + timedelta(days=DIAS))}
    except (ImportError, Exception):
        return [], {}


@register_metric("burnout_index")
def metric_burnout_index(
    db: Session,
    d_from: date,
    d_to: date,
    top_n: int,
    project_id: Optional[str] = None,
    user_id: Optional[str] = None,
    project_ids: Optional[list[str]] = None,
    organization_id: Optional[str] = None,
    **kwargs
) -> tuple[list[dict], dict]:
    """
    Burnout index por persona (0-100 score):
    Combina: utilización actual + trend últimas 4 semanas + ausencias pendientes + tareas bloqueadas.
    Score alto = riesgo de burnout.
    """
    try:
        from app.models.user import User
        from app.models.imputation import Imputation
        from app.models.resources import Absence, AbsenceStatus
        from app.models.task import Task
        from app.core.config import settings

        today = timeutil.today()
        four_weeks_ago = today - timedelta(days=28)
        seven_weeks_ago = today - timedelta(days=49)

        users_q = db.query(User).filter(User.is_active == True)
        if organization_id:
            users_q = users_q.filter(User.organization_id == organization_id)
        users = users_q.all()
        user_ids = [u.id for u in users]
        {u.id: u for u in users}

        # 1. Utilización actual y previa (últimas 4 y 4 previas)
        hours_4w = {r[0]: r[1] for r in db.query(Imputation.user_id, func.sum(Imputation.hours))
            .filter(Imputation.user_id.in_(user_ids), Imputation.date.between(four_weeks_ago, today))
            .group_by(Imputation.user_id).all()}
        hours_prev4w = {r[0]: r[1] for r in db.query(Imputation.user_id, func.sum(Imputation.hours))
            .filter(Imputation.user_id.in_(user_ids), Imputation.date.between(seven_weeks_ago, four_weeks_ago))
            .group_by(Imputation.user_id).all()}

        # 2. Ausencias pendientes
        absences = {r[0]: r[1] for r in db.query(Absence.user_id, func.sum(Absence.working_days))
            .filter(Absence.user_id.in_(user_ids), Absence.status.in_([AbsenceStatus.pending, AbsenceStatus.approved]), Absence.start_date >= today)
            .group_by(Absence.user_id).all()}

        # 3. Tareas bloqueadas
        blocked = {r[0]: r[1] for r in db.query(Task.assignee_id, func.count(Task.id))
            .filter(Task.assignee_id.in_(user_ids), Task.status == "blocked")
            .group_by(Task.assignee_id).all()}

        rows = []
        for user in users[:top_n]:
            total_hours_4w = hours_4w.get(user.id, 0) or 0
            prev_4w_hours = hours_prev4w.get(user.id, 0) or 0
            pending_absences = absences.get(user.id, 0) or 0
            blocked_tasks = blocked.get(user.id, 0) or 0

            capacity_per_day = (user.weekly_capacity_hours or settings.DEFAULT_WEEKLY_CAPACITY_HOURS) / 5
            capacity_4w = capacity_per_day * 22  # ~22 working days
            utilization_pct = min(100, round((total_hours_4w / capacity_4w) * 100, 1)) if capacity_4w > 0 else 0

            trend = 10 if prev_4w_hours > total_hours_4w else (-10 if prev_4w_hours < total_hours_4w else 0)
            absences_penalty = min(30, pending_absences * 2)  # Max 30pts
            blocked_penalty = min(20, blocked_tasks * 1.5)  # Max 20pts

            score = utilization_pct * 0.4 + trend + absences_penalty + blocked_penalty
            score = max(0, min(100, round(score, 1)))

            severity = "critical" if score >= 80 else "warning" if score >= 60 else "ok"

            rows.append({
                "label": user.full_name or "Desconocido",
                "value": score,
                "severity": severity,
                "utilization": utilization_pct,
                "trend": trend,
                "absences_pending": int(pending_absences),
                "blocked_tasks": blocked_tasks,
                "metadata": {
                    "hours_4w": round(total_hours_4w, 1),
                    "capacity_4w": round(capacity_4w, 1)
                }
            })

        rows.sort(key=lambda x: -x["value"])
        return rows, {}
    except (ImportError, Exception):
        return [], {}
