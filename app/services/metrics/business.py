"""Business metrics: pipeline_by_stage, pipeline_evolution, contracts_by_status,
win_rate_evolution, change_requests_status."""
from datetime import date
from typing import Optional
from sqlalchemy import func
from sqlalchemy.orm import Session

from . import register_metric
from app.models.resources import ChangeRequest


STAGE_LABELS = {
    "lead": "Lead",
    "qualification": "Cualificación",
    "proposal": "Propuesta",
    "negotiation": "Negociación",
    "won": "Ganada",
    "lost": "Perdida"
}

CONTRACT_STATUS_LABELS = {
    "draft": "Borrador",
    "active": "Activo",
    "completed": "Completado",
    "cancelled": "Cancelado"
}

CR_STATUS_LABELS = {
    "draft": "Borrador",
    "submitted": "Enviado",
    "under_review": "En revisión",
    "approved": "Aprobado",
    "rejected": "Rechazado",
    "implemented": "Implementado"
}


@register_metric("pipeline_by_stage")
def metric_pipeline_by_stage(
    db: Session,
    d_from: date,
    d_to: date,
    top_n: int,
    project_id: Optional[str] = None,
    user_id: Optional[str] = None,
    project_ids: Optional[list[str]] = None,
    **kwargs
) -> tuple[list[dict], dict]:
    """Pipeline por etapa comercial: valor ponderado por probabilidad."""
    try:
        from app.models.pipeline import Opportunity

        q = db.query(
            Opportunity.stage,
            func.count(Opportunity.id).label("count"),
            func.sum(Opportunity.expected_revenue).label("revenue"),
            func.avg(Opportunity.probability).label("avg_prob")
        ).group_by(Opportunity.stage)

        rows = []
        for r in q.all():
            weighted = (r.revenue or 0) * (r.avg_prob or 0) / 100
            rows.append({
                "label": STAGE_LABELS.get(r.stage, r.stage),
                "count": r.count,
                "revenue": round(r.revenue or 0, 0),
                "weighted": round(weighted, 0),
                "value": round(weighted, 0)
            })
    except ImportError:
        rows = []

    return rows, {}


@register_metric("pipeline_evolution")
def metric_pipeline_evolution(
    db: Session,
    d_from: date,
    d_to: date,
    top_n: int,
    project_id: Optional[str] = None,
    user_id: Optional[str] = None,
    project_ids: Optional[list[str]] = None,
    **kwargs
) -> tuple[list[dict], dict]:
    """Evolución mensual del valor del pipeline."""
    try:
        from app.models.pipeline import Opportunity

        monthly = {}
        for opp in db.query(Opportunity).filter(Opportunity.created_at >= d_from).all():
            k = str(opp.created_at)[:7] if opp.created_at else "unknown"
            if k not in monthly:
                monthly[k] = 0
            weighted = (opp.expected_revenue or 0) * (opp.probability or 0) / 100
            monthly[k] += weighted

        rows = [
            {"label": k, "value": round(v, 0)}
            for k, v in sorted(monthly.items())[-12:]
        ]
    except ImportError:
        rows = []

    return rows, {}


@register_metric("contracts_by_status")
def metric_contracts_by_status(
    db: Session,
    d_from: date,
    d_to: date,
    top_n: int,
    project_id: Optional[str] = None,
    user_id: Optional[str] = None,
    project_ids: Optional[list[str]] = None,
    **kwargs
) -> tuple[list[dict], dict]:
    """Contratos por estado: cantidad y valor total."""
    try:
        from app.models.pipeline import Contract

        rows_raw = db.query(
            Contract.status,
            func.count(Contract.id).label("n"),
            func.sum(Contract.total_amount).label("total")
        ).group_by(Contract.status).all()

        rows = [
            {
                "label": CONTRACT_STATUS_LABELS.get(r.status, r.status),
                "value": round(r.total or 0, 0),
                "count": r.n
            }
            for r in rows_raw
        ]
    except ImportError:
        rows = []

    return rows, {}


@register_metric("win_rate_evolution")
def metric_win_rate_evolution(
    db: Session,
    d_from: date,
    d_to: date,
    top_n: int,
    project_id: Optional[str] = None,
    user_id: Optional[str] = None,
    project_ids: Optional[list[str]] = None,
    **kwargs
) -> tuple[list[dict], dict]:
    """Tasa de éxito comercial por mes: % ganadas de las cerradas."""
    try:
        from app.models.pipeline import Opportunity

        monthly = {}
        for opp in db.query(Opportunity).filter(Opportunity.created_at >= d_from).all():
            k = str(opp.created_at)[:7] if opp.created_at else "unknown"
            if k not in monthly:
                monthly[k] = {"won": 0, "lost": 0, "total": 0}
            monthly[k]["total"] += 1
            if str(opp.stage) in ("won", "Stage.won"):
                monthly[k]["won"] += 1
            elif str(opp.stage) in ("lost", "Stage.lost"):
                monthly[k]["lost"] += 1

        rows = []
        for k in sorted(monthly.keys())[-12:]:
            m = monthly[k]
            closed = m["won"] + m["lost"]
            pct = round(m["won"] / closed * 100, 1) if closed > 0 else 0
            rows.append({
                "label": k,
                "value": pct,
                "won": m["won"],
                "total": m["total"]
            })
    except ImportError:
        rows = []

    return rows, {}


@register_metric("change_requests_status")
def metric_change_requests_status(
    db: Session,
    d_from: date,
    d_to: date,
    top_n: int,
    project_id: Optional[str] = None,
    user_id: Optional[str] = None,
    project_ids: Optional[list[str]] = None,
    **kwargs
) -> tuple[list[dict], dict]:
    """Control de cambios: cantidad y impactos por estado."""

    q = db.query(
        ChangeRequest.status,
        func.count(ChangeRequest.id).label("count"),
        func.sum(ChangeRequest.cost_impact).label("cost"),
        func.sum(ChangeRequest.schedule_impact_days).label("days")
    ).group_by(ChangeRequest.status)

    if project_ids:
        q = q.filter(ChangeRequest.project_id.in_(project_ids))

    rows = [
        {
            "label": CR_STATUS_LABELS.get(r.status, r.status),
            "value": r.count,
            "cost_impact": round(r.cost or 0, 0),
            "days_impact": r.days or 0
        }
        for r in q.all()
    ]
    return rows, {}
