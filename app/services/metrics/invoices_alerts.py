"""Invoice, Alert and SLA breach metrics:
invoices_by_status, invoice_amount_by_month, invoice_amount_by_client,
invoice_overdue_amount, alerts_by_severity, alerts_by_type,
unresolved_alerts_by_project, sla_breach_trend, sla_breach_by_type."""
from datetime import date
from typing import Optional
from sqlalchemy import func
from sqlalchemy.orm import Session

from . import register_metric
from app.core import timeutil


@register_metric("invoices_by_status")
def metric_invoices_by_status(
    db: Session,
    d_from: date,
    d_to: date,
    top_n: int,
    project_id: Optional[str] = None,
    user_id: Optional[str] = None,
    project_ids: Optional[list[str]] = None,
    **kwargs
) -> tuple[list[dict], dict]:
    """Número e importe de facturas por estado."""
    try:
        from app.models.billing_reports import Invoice

        q = db.query(
            Invoice.status,
            func.count(Invoice.id).label("cnt"),
            func.sum(Invoice.total).label("total"),
        ).filter(
            Invoice.issue_date >= d_from,
            Invoice.issue_date <= d_to,
        ).group_by(Invoice.status).order_by(func.sum(Invoice.total).desc())

        rows = [
            {
                "label": r.status or "Sin estado",
                "value": round(float(r.total or 0), 2),
                "count": r.cnt,
            }
            for r in q.all()
        ]
    except Exception:
        rows = []
    return rows, {"y_label": "Importe (€)"}


@register_metric("invoice_amount_by_month")
def metric_invoice_amount_by_month(
    db: Session,
    d_from: date,
    d_to: date,
    top_n: int,
    project_id: Optional[str] = None,
    user_id: Optional[str] = None,
    project_ids: Optional[list[str]] = None,
    **kwargs
) -> tuple[list[dict], dict]:
    """Evolución mensual del importe total facturado."""
    try:
        from app.models.billing_reports import Invoice
        from sqlalchemy import extract

        q = db.query(
            extract("year", Invoice.issue_date).label("year"),
            extract("month", Invoice.issue_date).label("month"),
            func.sum(Invoice.total).label("total"),
            func.count(Invoice.id).label("cnt"),
        ).filter(
            Invoice.issue_date >= d_from,
            Invoice.issue_date <= d_to,
        )
        if project_ids:
            q = q.filter(Invoice.project_id.in_(project_ids))
        q = q.group_by("year", "month").order_by("year", "month")

        rows = [
            {"label": f"{int(r.year)}-{int(r.month):02d}", "value": round(float(r.total or 0), 2), "count": r.cnt}
            for r in q.all()
        ]
    except Exception:
        rows = []
    return rows, {"y_label": "Facturado (€)"}


@register_metric("invoice_amount_by_client")
def metric_invoice_amount_by_client(
    db: Session,
    d_from: date,
    d_to: date,
    top_n: int,
    project_id: Optional[str] = None,
    user_id: Optional[str] = None,
    project_ids: Optional[list[str]] = None,
    **kwargs
) -> tuple[list[dict], dict]:
    """Total facturado por cliente en el período."""
    try:
        from app.models.billing_reports import Invoice

        q = db.query(
            Invoice.client_id,
            Invoice.client_name,
            func.sum(Invoice.total).label("total"),
            func.count(Invoice.id).label("cnt"),
        ).filter(
            Invoice.issue_date >= d_from,
            Invoice.issue_date <= d_to,
        ).group_by(Invoice.client_id, Invoice.client_name).order_by(
            func.sum(Invoice.total).desc()
        ).limit(top_n)

        rows = [
            {
                "label": r.client_name or str(r.client_id),
                "value": round(float(r.total or 0), 2),
                "invoices": r.cnt,
            }
            for r in q.all()
        ]
    except Exception:
        rows = []
    return rows, {"y_label": "Facturado (€)"}


@register_metric("invoice_overdue_amount")
def metric_invoice_overdue_amount(
    db: Session,
    d_from: date,
    d_to: date,
    top_n: int,
    project_id: Optional[str] = None,
    user_id: Optional[str] = None,
    project_ids: Optional[list[str]] = None,
    **kwargs
) -> tuple[list[dict], dict]:
    """Facturas vencidas (no pagadas) por cliente: importe y días de retraso."""
    try:
        from app.models.billing_reports import Invoice

        today = timeutil.today()
        q = db.query(Invoice).filter(
            Invoice.status.in_(["sent", "overdue"]),
            Invoice.due_date < today,
        ).order_by(Invoice.total.desc()).limit(top_n)

        rows = []
        for inv in q.all():
            days_late = (today - inv.due_date).days if inv.due_date else 0
            rows.append({
                "label": inv.client_name or str(inv.client_id),
                "value": round(float(inv.total or 0), 2),
                "days_late": days_late,
                "invoice_number": inv.number,
            })
    except Exception:
        rows = []
    return rows, {"y_label": "Importe vencido (€)"}


@register_metric("alerts_by_severity")
def metric_alerts_by_severity(
    db: Session,
    d_from: date,
    d_to: date,
    top_n: int,
    project_id: Optional[str] = None,
    user_id: Optional[str] = None,
    project_ids: Optional[list[str]] = None,
    **kwargs
) -> tuple[list[dict], dict]:
    """Distribución de alertas por severidad."""
    try:
        from app.models.alert import Alert

        q = db.query(Alert.severity, func.count(Alert.id).label("cnt")).filter(
            Alert.created_at >= d_from,
            Alert.created_at <= d_to,
        )
        if project_id:
            q = q.filter(Alert.project_id == project_id)
        elif project_ids:
            q = q.filter(Alert.project_id.in_(project_ids))
        q = q.group_by(Alert.severity).order_by(func.count(Alert.id).desc())

        SEVERITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}
        rows = sorted(
            [{"label": r.severity or "Sin severidad", "value": r.cnt} for r in q.all()],
            key=lambda x: SEVERITY_ORDER.get(x["label"], 99)
        )
    except Exception:
        rows = []
    return rows, {}


@register_metric("alerts_by_type")
def metric_alerts_by_type(
    db: Session,
    d_from: date,
    d_to: date,
    top_n: int,
    project_id: Optional[str] = None,
    user_id: Optional[str] = None,
    project_ids: Optional[list[str]] = None,
    **kwargs
) -> tuple[list[dict], dict]:
    """Distribución de alertas por tipo."""
    try:
        from app.models.alert import Alert

        q = db.query(Alert.alert_type, func.count(Alert.id).label("cnt")).filter(
            Alert.created_at >= d_from,
            Alert.created_at <= d_to,
        ).group_by(Alert.alert_type).order_by(func.count(Alert.id).desc()).limit(top_n)

        rows = [{"label": r.alert_type or "Sin tipo", "value": r.cnt} for r in q.all()]
    except Exception:
        rows = []
    return rows, {}


@register_metric("unresolved_alerts_by_project")
def metric_unresolved_alerts_by_project(
    db: Session,
    d_from: date,
    d_to: date,
    top_n: int,
    project_id: Optional[str] = None,
    user_id: Optional[str] = None,
    project_ids: Optional[list[str]] = None,
    **kwargs
) -> tuple[list[dict], dict]:
    """Alertas no resueltas por proyecto."""
    try:
        from app.models.alert import Alert
        from app.models.project import Project

        q = db.query(Alert.project_id, func.count(Alert.id).label("cnt")).filter(
            Alert.is_resolved == False,
            Alert.project_id.isnot(None),
        )
        if project_ids:
            q = q.filter(Alert.project_id.in_(project_ids))
        q = q.group_by(Alert.project_id).order_by(func.count(Alert.id).desc()).limit(top_n)

        proj_ids = [r.project_id for r in q.all()]
        proj_map = {p.id: p.name for p in db.query(Project).filter(Project.id.in_(proj_ids)).all()} if proj_ids else {}

        rows = [
            {"label": proj_map.get(r.project_id, str(r.project_id)), "value": r.cnt}
            for r in q.all()
        ]
    except Exception:
        rows = []
    return rows, {"y_label": "Alertas no resueltas"}


@register_metric("sla_breach_trend")
def metric_sla_breach_trend(
    db: Session,
    d_from: date,
    d_to: date,
    top_n: int,
    project_id: Optional[str] = None,
    user_id: Optional[str] = None,
    project_ids: Optional[list[str]] = None,
    **kwargs
) -> tuple[list[dict], dict]:
    """Evolución mensual de incumplimientos de SLA."""
    try:
        from app.models.billing_reports import SLABreachLog
        from sqlalchemy import extract

        q = db.query(
            extract("year", SLABreachLog.breached_at).label("year"),
            extract("month", SLABreachLog.breached_at).label("month"),
            func.count(SLABreachLog.id).label("cnt"),
        ).filter(
            SLABreachLog.breached_at >= d_from,
            SLABreachLog.breached_at <= d_to,
        ).group_by("year", "month").order_by("year", "month")

        rows = [
            {"label": f"{int(r.year)}-{int(r.month):02d}", "value": r.cnt}
            for r in q.all()
        ]
    except Exception:
        rows = []
    return rows, {"y_label": "Incumplimientos SLA"}


@register_metric("sla_breach_by_type")
def metric_sla_breach_by_type(
    db: Session,
    d_from: date,
    d_to: date,
    top_n: int,
    project_id: Optional[str] = None,
    user_id: Optional[str] = None,
    project_ids: Optional[list[str]] = None,
    **kwargs
) -> tuple[list[dict], dict]:
    """Distribución de incumplimientos SLA por tipo."""
    try:
        from app.models.billing_reports import SLABreachLog

        q = db.query(
            SLABreachLog.breach_type,
            func.count(SLABreachLog.id).label("cnt"),
            func.avg(SLABreachLog.breach_minutes).label("avg_mins"),
        ).filter(
            SLABreachLog.breached_at >= d_from,
            SLABreachLog.breached_at <= d_to,
        ).group_by(SLABreachLog.breach_type).order_by(func.count(SLABreachLog.id).desc())

        rows = [
            {
                "label": r.breach_type or "Sin tipo",
                "value": r.cnt,
                "avg_breach_minutes": round(float(r.avg_mins or 0), 0),
            }
            for r in q.all()
        ]
    except Exception:
        rows = []
    return rows, {}
