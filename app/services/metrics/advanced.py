"""Advanced metrics: forecast_revenue, burnout_index."""
from datetime import date, timedelta
from typing import Optional
from sqlalchemy import func
from sqlalchemy.orm import Session

from . import register_metric


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
    """
    Forecast de ingresos a 90 días: combina pipeline + proyectos activos + horas estimadas.
    Requiere modelos: Opportunity (pipeline), Project (horas restantes), Contract (vigentes).
    """
    try:
        from app.models.pipeline import Opportunity, Contract
        from app.models.project import Project
        from app.models.imputation import Imputation

        today = date.today()
        forecast_days = 90
        forecast_end = today + timedelta(days=forecast_days)

        # 1. Pipeline opportunities (weighted by probability)
        pipeline_revenue = 0
        opportunities = db.query(Opportunity).filter(
            Opportunity.stage.notin_(["won", "lost"]),
            Opportunity.created_at >= d_from
        ).all()

        for opp in opportunities:
            weighted = (opp.expected_revenue or 0) * (opp.probability or 0) / 100
            if opp.created_at:
                days_left = (forecast_end - opp.created_at.date()).days
                if days_left > 0:
                    pipeline_revenue += weighted

        # 2. Active projects: hours remaining * rate (batch query)
        project_revenue = 0
        active_projects_q = db.query(Project).filter(Project.status == "active")
        if project_ids is not None:
            active_projects_q = active_projects_q.filter(Project.id.in_(project_ids))
        active_projects = active_projects_q.all()
        billing_project_ids = [p.id for p in active_projects if p.estimated_hours and p.billing_rate]
        imputations_by_project = {r[0]: r[1] or 0 for r in db.query(Imputation.project_id, func.sum(Imputation.hours))
            .filter(Imputation.project_id.in_(billing_project_ids), Imputation.date.between(d_from, d_to))
            .group_by(Imputation.project_id).all()} if billing_project_ids else {}
        for proj in active_projects:
            if proj.estimated_hours and proj.billing_rate:
                imputations = imputations_by_project.get(proj.id, 0)
                hours_remaining = max(0, proj.estimated_hours - imputations)
                revenue = hours_remaining * proj.billing_rate
                project_revenue += revenue

        # 3. Active contracts revenue remaining
        contract_revenue = 0
        contracts_q = db.query(Contract).filter(
            Contract.status == "active",
            Contract.end_date >= today
        )
        if project_ids is not None:
            contracts_q = contracts_q.filter(Contract.project_id.in_(project_ids))
        contracts = contracts_q.all()

        for contract in contracts:
            if contract.end_date:
                days_left = (contract.end_date - today).days
                if days_left > 0:
                    monthly_value = (contract.total_amount or 0) / 12
                    monthly_days = 30
                    revenue_per_day = monthly_value / monthly_days
                    contract_revenue += revenue_per_day * days_left

        rows = [
            {
                "label": "Ingreso pipeline (ponderado)",
                "value": round(pipeline_revenue, 0),
                "percentage": round(pipeline_revenue / (pipeline_revenue + project_revenue + contract_revenue) * 100, 1) if (pipeline_revenue + project_revenue + contract_revenue) > 0 else 0,
                "type": "pipeline"
            },
            {
                "label": "Ingreso proyectos activos",
                "value": round(project_revenue, 0),
                "percentage": round(project_revenue / (pipeline_revenue + project_revenue + contract_revenue) * 100, 1) if (pipeline_revenue + project_revenue + contract_revenue) > 0 else 0,
                "type": "projects"
            },
            {
                "label": "Ingreso contratos vigentes",
                "value": round(contract_revenue, 0),
                "percentage": round(contract_revenue / (pipeline_revenue + project_revenue + contract_revenue) * 100, 1) if (pipeline_revenue + project_revenue + contract_revenue) > 0 else 0,
                "type": "contracts"
            },
        ]

        meta_patch = {"forecast_days": forecast_days, "forecast_end": str(forecast_end)}
        return rows, meta_patch
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

        today = date.today()
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
