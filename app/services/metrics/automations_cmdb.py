"""Automations, CMDB, Clients and Pipeline owner metrics:
automation_success_rate, automation_run_stats, cmdb_items_by_status,
cmdb_items_by_environment, cmdb_items_by_type, clients_by_industry,
opportunity_by_owner."""
from datetime import date
from typing import Optional
from sqlalchemy import func
from sqlalchemy.orm import Session

from . import register_metric


@register_metric("automation_success_rate")
def metric_automation_success_rate(
    db: Session,
    d_from: date,
    d_to: date,
    top_n: int,
    project_id: Optional[str] = None,
    user_id: Optional[str] = None,
    project_ids: Optional[list[str]] = None,
    **kwargs
) -> tuple[list[dict], dict]:
    """Tasa de éxito de ejecuciones de automatización."""
    try:
        from app.models.automations import AutomationExecution

        q = db.query(
            AutomationExecution.success,
            func.count(AutomationExecution.id).label("cnt"),
        ).filter(
            AutomationExecution.executed_at >= d_from,
            AutomationExecution.executed_at <= d_to,
        ).group_by(AutomationExecution.success)

        rows = []
        for r in q.all():
            rows.append({
                "label": "Exitosa" if r.success else "Fallida",
                "value": r.cnt,
            })
    except Exception:
        rows = []
    return rows, {}


@register_metric("automation_run_stats")
def metric_automation_run_stats(
    db: Session,
    d_from: date,
    d_to: date,
    top_n: int,
    project_id: Optional[str] = None,
    user_id: Optional[str] = None,
    project_ids: Optional[list[str]] = None,
    **kwargs
) -> tuple[list[dict], dict]:
    """Estadísticas de ejecución (run_count, success_count, error_count) por regla de automatización."""
    try:
        from app.models.billing_reports import AutomationWorkflow

        q = db.query(AutomationWorkflow).filter(
            AutomationWorkflow.status == "active",
        ).order_by(AutomationWorkflow.run_count.desc()).limit(top_n)

        rows = []
        for aw in q.all():
            total = aw.run_count or 0
            success = aw.success_count or 0
            error = aw.error_count or 0
            rate = round(success / total * 100, 1) if total else 0
            rows.append({
                "label": aw.name,
                "value": total,
                "success": success,
                "errors": error,
                "success_rate": rate,
            })
    except Exception:
        rows = []
    return rows, {"y_label": "Ejecuciones totales"}


@register_metric("cmdb_items_by_status")
def metric_cmdb_items_by_status(
    db: Session,
    d_from: date,
    d_to: date,
    top_n: int,
    project_id: Optional[str] = None,
    user_id: Optional[str] = None,
    project_ids: Optional[list[str]] = None,
    **kwargs
) -> tuple[list[dict], dict]:
    """Distribución de ítems CMDB por estado."""
    try:
        from app.models.service_desk import ConfigurationItem as CI

        q = db.query(CI.status, func.count(CI.id).label("cnt")).filter(
            CI.is_active.is_(True)
        ).group_by(
            CI.status
        ).order_by(func.count(CI.id).desc())

        rows = [{"label": getattr(r.status, "value", r.status) or "Sin estado", "value": r.cnt} for r in q.all()]
    except Exception:
        rows = []
    return rows, {}


@register_metric("cmdb_items_by_environment")
def metric_cmdb_items_by_environment(
    db: Session,
    d_from: date,
    d_to: date,
    top_n: int,
    project_id: Optional[str] = None,
    user_id: Optional[str] = None,
    project_ids: Optional[list[str]] = None,
    **kwargs
) -> tuple[list[dict], dict]:
    """Distribución de ítems CMDB por entorno (production, staging, etc.)."""
    try:
        from app.models.service_desk import ConfigurationItem as CI

        q = db.query(CI.environment, func.count(CI.id).label("cnt")).filter(
            CI.environment.isnot(None), CI.is_active.is_(True)
        ).group_by(CI.environment).order_by(func.count(CI.id).desc())

        rows = [{"label": r.environment, "value": r.cnt} for r in q.all()]
    except Exception:
        rows = []
    return rows, {}


@register_metric("cmdb_items_by_type")
def metric_cmdb_items_by_type(
    db: Session,
    d_from: date,
    d_to: date,
    top_n: int,
    project_id: Optional[str] = None,
    user_id: Optional[str] = None,
    project_ids: Optional[list[str]] = None,
    **kwargs
) -> tuple[list[dict], dict]:
    """Distribución de ítems CMDB por tipo de CI."""
    try:
        from app.models.service_desk import ConfigurationItem as CI

        q = db.query(CI.ci_type, func.count(CI.id).label("cnt")).filter(
            CI.is_active.is_(True)
        ).group_by(
            CI.ci_type
        ).order_by(func.count(CI.id).desc()).limit(top_n)

        rows = [{"label": getattr(r.ci_type, "value", r.ci_type) or "Sin tipo", "value": r.cnt} for r in q.all()]
    except Exception:
        rows = []
    return rows, {}


@register_metric("clients_by_industry")
def metric_clients_by_industry(
    db: Session,
    d_from: date,
    d_to: date,
    top_n: int,
    project_id: Optional[str] = None,
    user_id: Optional[str] = None,
    project_ids: Optional[list[str]] = None,
    **kwargs
) -> tuple[list[dict], dict]:
    """Distribución de clientes activos por sector industrial."""
    try:
        from app.models.clients import Client

        q = db.query(Client.industry, func.count(Client.id).label("cnt")).filter(
            Client.is_active == True,
        ).group_by(Client.industry).order_by(func.count(Client.id).desc()).limit(top_n)

        rows = [{"label": r.industry or "Sin sector", "value": r.cnt} for r in q.all()]
    except Exception:
        rows = []
    return rows, {}


@register_metric("opportunity_by_owner")
def metric_opportunity_by_owner(
    db: Session,
    d_from: date,
    d_to: date,
    top_n: int,
    project_id: Optional[str] = None,
    user_id: Optional[str] = None,
    project_ids: Optional[list[str]] = None,
    **kwargs
) -> tuple[list[dict], dict]:
    """Pipeline comercial (valor ponderado) por propietario de la oportunidad."""
    try:
        from app.models.pipeline import Opportunity
        from app.models.user import User

        q = db.query(
            Opportunity.owner_id,
            func.count(Opportunity.id).label("cnt"),
            func.sum(Opportunity.expected_revenue).label("revenue"),
            func.avg(Opportunity.probability).label("avg_prob"),
        ).filter(
            Opportunity.stage.notin_(["won", "lost"]),
        ).group_by(Opportunity.owner_id).order_by(func.sum(Opportunity.expected_revenue).desc()).limit(top_n)

        owner_ids = [r.owner_id for r in q.all() if r.owner_id]
        users_map = {u.id: u.full_name or u.email for u in db.query(User).filter(User.id.in_(owner_ids)).all()} if owner_ids else {}

        rows = []
        for r in q.all():
            weighted = (r.revenue or 0) * (r.avg_prob or 0) / 100
            rows.append({
                "label": users_map.get(r.owner_id, "Sin propietario"),
                "value": round(float(weighted), 0),
                "opportunities": r.cnt,
                "total_revenue": round(float(r.revenue or 0), 0),
            })
    except Exception:
        rows = []
    return rows, {"y_label": "Pipeline ponderado (€)"}
