"""Informes del sistema, informes programados y definiciones de informe.

Parte de `app.services.billing_reports_service` (auditoria 2026-11, #24): se partio por responsabilidad
sin cambiar el codigo. El paquete reexporta todos los nombres.
"""
from __future__ import annotations

import json
from datetime import timedelta
from sqlalchemy.orm import Session, joinedload
from app.models.service_desk._enums import ESTADOS_DE_TICKET_RESUELTOS
from app.core.config import settings
from app.models.user import User
from app.models.project import Project
from app.models.imputation import Imputation
from app.models.project import Project as _Project
from app.models.financial import CapacityPlan
from app.models.billing_reports import ReportDefinition, ScheduledReport
from app.models.service_desk import Ticket
from app.models.expenses import Expense
from app.services.billing_reports.data_source_service import run_skills_report, run_pipeline_report
from app.core import timeutil
from app.core.errores import ErrorDeDominio


# ═══════════════════════════════════════════════════════════════════════════════
# REPORT RUNNERS
# ═══════════════════════════════════════════════════════════════════════════════

def run_projects_report(db: Session, filters: dict, group_by, date_from, date_to, org_id=None) -> dict:
    projects_q = db.query(Project).options(
        joinedload(Project.project_manager),
        joinedload(Project.imputations).joinedload(Imputation.user),
    )
    if org_id:
        projects_q = projects_q.filter(Project.organization_id == org_id)
    projects = projects_q.all()

    rows = []
    for p in projects:
        active_imps = [i for i in p.imputations if i.is_active]
        hours = sum(i.hours for i in active_imps)
        # Use the per-imputation cost snapshot (cost_amount) for historical accuracy;
        # fall back to live rate only if no snapshot was recorded.
        cost = sum(
            i.cost_amount if i.cost_amount is not None
            else i.hours * ((i.user.hourly_rate or 0) if i.user else 0)
            for i in active_imps
        )
        revenue = p.contract_amount or 0
        margin = round((revenue - cost) / revenue * 100, 1) if revenue > 0 else None
        budget_pct = round(cost / p.budget_amount * 100, 1) if p.budget_amount else None

        rows.append({
            "code": p.code, "name": p.name, "status": p.status,
            "client_name": p.client_name or "—",
            "pm_name": p.project_manager.full_name if p.project_manager else "—",
            "budget_amount": p.budget_amount or 0,
            "budget_used_pct": budget_pct,
            "hours_logged": round(hours, 1),
            "cost": round(cost, 2),
            "revenue": revenue,
            "margin_pct": margin,
            "start_date": str(p.start_date) if p.start_date else None,
            "end_date_planned": str(p.end_date_planned) if p.end_date_planned else None,
            "risk_level": p.risk_level,
            "health": "critical" if (budget_pct or 0) > 90 else "warning" if (budget_pct or 0) > 75 else "ok",
        })

    if filters.get("status"):
        rows = [r for r in rows if r["status"] == filters["status"]]

    total_revenue = sum(r["revenue"] for r in rows)
    total_cost = sum(r["cost"] for r in rows)
    avg_margin = round((total_revenue - total_cost) / total_revenue * 100, 1) if total_revenue > 0 else None

    return {
        "rows": rows,
        "totals": {"revenue": round(total_revenue, 2), "cost": round(total_cost, 2), "margin_pct": avg_margin, "count": len(rows)},
        "chart_data": [{"name": r["name"][:20], "cost": r["cost"], "revenue": r["revenue"], "margin": r["margin_pct"]} for r in rows if r["revenue"] > 0][:15],
    }


def run_imputations_report(db: Session, filters: dict, group_by, date_from, date_to, project_id, org_id=None) -> dict:
    q = db.query(Imputation).options(
        joinedload(Imputation.user), joinedload(Imputation.project)
    )
    if org_id:
        org_project_ids = [r.id for r in db.query(_Project.id).filter(
            _Project.organization_id == org_id
        ).all()]
        q = q.filter(Imputation.project_id.in_(org_project_ids))
    q = q.filter(Imputation.is_active == True)
    if date_from: q = q.filter(Imputation.date >= date_from)
    if date_to:   q = q.filter(Imputation.date <= date_to)
    if project_id: q = q.filter(Imputation.project_id == project_id)
    imps = q.order_by(Imputation.date.desc()).all()

    rows = [{
        "date": str(i.date), "user_name": i.user.full_name if i.user else "—",
        "project_name": i.project.name if i.project else "—",
        "project_code": i.project.code if i.project else "—",
        "hours": i.hours, "is_billable": i.is_billable,
        "work_type": i.work_type or "development",
        "description": (i.description or "")[:80],
        "cost": round(
            i.cost_amount if i.cost_amount is not None
            else (i.hours * (i.user.hourly_rate or 0) if i.user else 0),
            2,
        ),
    } for i in imps]

    by_user = {}
    for r in rows:
        name = r["user_name"]
        if name not in by_user:
            by_user[name] = {"name": name, "billable": 0, "non_billable": 0, "total": 0}
        if r["is_billable"]: by_user[name]["billable"] += r["hours"]
        else: by_user[name]["non_billable"] += r["hours"]
        by_user[name]["total"] += r["hours"]

    by_month = {}
    for r in rows:
        m = r["date"][:7]
        if m not in by_month: by_month[m] = {"month": m, "hours": 0, "cost": 0}
        by_month[m]["hours"] += r["hours"]
        by_month[m]["cost"] += r["cost"]

    return {
        "rows": rows[:500],
        "by_user": sorted(by_user.values(), key=lambda x: -x["total"]),
        "by_month": sorted(by_month.values(), key=lambda x: x["month"]),
        "totals": {
            "hours": round(sum(r["hours"] for r in rows), 1),
            "billable": round(sum(r["hours"] for r in rows if r["is_billable"]), 1),
            "cost": round(sum(r["cost"] for r in rows), 2),
        }
    }


def run_tickets_report(db: Session, filters: dict, group_by, date_from, date_to, org_id=None) -> dict:
    q = db.query(Ticket).options(joinedload(Ticket.assigned_to))
    if org_id:
        org_agent_ids = [r.id for r in db.query(User.id).filter(
            User.organization_id == org_id
        ).all()]
        q = q.filter(Ticket.assigned_to_user_id.in_(org_agent_ids))
    if date_from: q = q.filter(Ticket.created_at >= date_from)
    if date_to:   q = q.filter(Ticket.created_at <= date_to)
    if filters.get("priority"): q = q.filter(Ticket.priority == filters["priority"])

    tickets = q.all()
    rows = []
    for t in tickets:
        mttr = None
        if t.resolved_at and t.created_at:
            mttr = round((t.resolved_at - t.created_at).total_seconds() / 3600, 1)
        rows.append({
            "number": t.number, "title": t.title[:60], "status": t.status,
            "priority": t.priority, "ticket_type": t.ticket_type,
            "assigned_to": t.assigned_to.full_name if t.assigned_to else "—",
            "created_at": str(t.created_at)[:10],
            "resolved_at": str(t.resolved_at)[:10] if t.resolved_at else None,
            "mttr_hours": mttr,
            "sla_status": t.sla_resolution_status or "ok",
            "csat_score": t.csat_score,
        })

    total = len(rows)
    breached = sum(1 for r in rows if r["sla_status"] == "breached")
    resolved = sum(1 for r in rows if r["status"] in ESTADOS_DE_TICKET_RESUELTOS)
    mttr_avg = round(
        sum(r["mttr_hours"] for r in rows if r["mttr_hours"]) /
        max(len([r for r in rows if r["mttr_hours"]]), 1), 1)
    csat_rows = [r for r in rows if r["csat_score"]]
    csat_avg = round(sum(r["csat_score"] for r in csat_rows) / len(csat_rows), 1) if csat_rows else None
    by_priority = {}
    for r in rows:
        p = r["priority"]
        by_priority[p] = by_priority.get(p, 0) + 1

    return {
        "rows": rows[:200],
        "totals": {
            "total": total, "resolved": resolved,
            "sla_compliance_pct": round((total - breached) / max(total, 1) * 100, 1),
            "mttr_hours": mttr_avg, "avg_csat": csat_avg,
        },
        "chart_data": [{"priority": k, "count": v} for k, v in by_priority.items()],
    }


def run_expenses_report(db: Session, filters: dict, group_by, date_from, date_to, project_id, org_id=None) -> dict:
    q = db.query(Expense).options(joinedload(Expense.user), joinedload(Expense.project)).filter(
        Expense.status.in_(["approved", "reimbursed"]),
        Expense.is_active == True,
    )
    if org_id:
        org_proj_ids = [r.id for r in db.query(_Project.id).filter(
            _Project.organization_id == org_id
        ).all()]
        q = q.filter(Expense.project_id.in_(org_proj_ids))
    if date_from: q = q.filter(Expense.expense_date >= date_from)
    if date_to:   q = q.filter(Expense.expense_date <= date_to)
    from app.services.gastos_avanzados import del_proyecto, importe_por_proyecto
    if project_id: q = q.filter(del_proyecto(project_id))

    expenses = q.all()
    # Con proyecto, cada gasto cuenta por la parte que le toca (reparto entre proyectos).
    pares = importe_por_proyecto(db, expenses, project_id) if project_id else [(e, e.amount) for e in expenses]
    rows = [{
        "code": e.code, "user_name": e.user.full_name if e.user else "—",
        "project_name": e.project.name if e.project else "Sin proyecto",
        "category": e.category, "description": e.description[:60],
        "amount": importe, "currency": e.currency,
        "expense_date": str(e.expense_date), "is_billable": e.is_billable,
        "status": e.status,
    } for e, importe in pares]

    by_cat: dict = {}
    for r in rows:
        by_cat[r["category"]] = round(by_cat.get(r["category"], 0) + r["amount"], 2)

    return {
        "rows": rows,
        "by_category": [{"category": k, "amount": v} for k, v in sorted(by_cat.items(), key=lambda x: -x[1])],
        "totals": {
            "total": round(sum(r["amount"] for r in rows), 2),
            "billable": round(sum(r["amount"] for r in rows if r["is_billable"]), 2),
            "count": len(rows),
        }
    }


def run_capacity_report(db: Session, filters: dict, date_from, date_to, org_id=None) -> dict:

    users_q = db.query(User).filter(User.is_active == True)
    if org_id:
        users_q = users_q.filter(User.organization_id == org_id)
    users = users_q.all()
    cap_user_ids = [u.id for u in users]

    plans = db.query(CapacityPlan).options(
        joinedload(CapacityPlan.user), joinedload(CapacityPlan.project)
    ).filter(CapacityPlan.user_id.in_(cap_user_ids)).all()

    by_user: dict = {}
    for u in users:
        user_plans = [p for p in plans if p.user_id == u.id]
        total_assigned = sum(p.allocated_hours or 0 for p in user_plans)
        capacity = (u.weekly_capacity_hours or settings.DEFAULT_WEEKLY_CAPACITY_HOURS) * 12
        util_pct = round(total_assigned / capacity * 100, 1) if capacity > 0 else 0
        by_user[u.id] = {
            "user_id": u.id, "user_name": u.full_name, "role": u.role,
            "capacity_hours": capacity, "assigned_hours": round(total_assigned, 1),
            "available_hours": round(max(capacity - total_assigned, 0), 1),
            "utilization_pct": util_pct,
            "status": "overloaded" if util_pct > 100 else "high" if util_pct > 85 else "ok" if util_pct > 50 else "under",
        }

    return {
        "by_user": sorted(by_user.values(), key=lambda x: -x["utilization_pct"]),
        "totals": {
            "avg_utilization": round(sum(u["utilization_pct"] for u in by_user.values()) / max(len(by_user), 1), 1),
            "overloaded": sum(1 for u in by_user.values() if u["status"] == "overloaded"),
            "under_utilized": sum(1 for u in by_user.values() if u["status"] == "under"),
        }
    }


#: Informe del catálogo → qué generador lo produce y con qué agrupación.
#:
#: Auditoría 2026-09 (hallazgo 18): eran diez `if` con `return`, que es una
#: tabla de despacho escrita como código. Como tabla se ve de un vistazo qué
#: informes existen y cuáles comparten generador —tres van a
#: `run_projects_report` con agrupaciones distintas—, que es justo lo que hay
#: que saber para añadir uno.
#:
#: `fechas` a `False` marca los dos generadores que no admiten rango: el de
#: habilidades y el de pipeline son fotos del momento, no series.
_INFORMES_DEL_SISTEMA: dict[str, tuple] = {
    "utilization_by_person": ("imputations", "user", True),
    "margin_by_project":     ("projects", "project", True),
    "wip_report":            ("projects", None, True),
    "timesheet_hours_trend": ("imputations", "month", True),
    "sla_compliance":        ("tickets", None, True),
    "ticket_volume_trend":   ("tickets", "week", True),
    "expense_by_project":    ("expenses", "project", True),
    "capacity_forecast_12w": ("capacity", None, True),
    "resource_skills_matrix": ("skills", None, False),
    "pipeline_health":       ("pipeline", None, False),
}


def run_system_report(db: Session, report_id: str, filters: dict, date_from, date_to) -> dict:
    """Ejecuta uno de los informes del catálogo del sistema.

    Un `report_id` desconocido cae al informe de proyectos sin agrupar, que es
    lo que hacía: es la vista más general y no deja al usuario sin respuesta.
    """
    hoy = timeutil.today()
    desde = date_from or str(hoy - timedelta(days=90))
    hasta = date_to or str(hoy)

    generador, agrupacion, con_fechas = _INFORMES_DEL_SISTEMA.get(
        report_id, ("projects", None, True),
    )

    if generador == "imputations":
        return run_imputations_report(db, filters, agrupacion, desde, hasta, None)
    if generador == "tickets":
        return run_tickets_report(db, filters, agrupacion, desde, hasta)
    if generador == "expenses":
        return run_expenses_report(db, filters, agrupacion, desde, hasta, None)
    if generador == "capacity":
        return run_capacity_report(db, filters, desde, hasta)
    if generador == "skills":
        return run_skills_report(db, filters)
    if generador == "pipeline":
        return run_pipeline_report(db, filters)
    return run_projects_report(db, filters, agrupacion, desde, hasta)


# ═══════════════════════════════════════════════════════════════════════════════
# SCHEDULED REPORTS CRUD
# ═══════════════════════════════════════════════════════════════════════════════

def create_scheduled_report(payload, current_user: User, db: Session) -> dict:
    from app.services.scheduled_reports import proxima_ejecucion
    r = ScheduledReport(
        name=payload.name,
        metric=payload.metric,
        frequency=payload.frequency,
        recipients=json.dumps(payload.recipients),
        include_pdf=payload.include_pdf,
        filters_json=payload.filters_json or "{}",
        report_type=payload.report_type or "custom",
        include_narrative=payload.include_narrative,
        day_of_week=payload.day_of_week,
        day_of_month=payload.day_of_month,
        send_hour=8 if payload.send_hour is None else payload.send_hour,
        recipients_extra=json.dumps(payload.recipients_extra),
        created_by=current_user.id,
    )
    r.next_run_at = proxima_ejecucion(r)
    db.add(r)
    db.commit()
    db.refresh(r)
    return {"ok": True, "id": r.id}


# Lo que se puede cambiar de un informe programado. Auditoria 2026-11: se
# copiaba cualquier campo del cuerpo, `organization_id` y `created_by` incluidos.
CAMPOS_EDITABLES_INFORME = {
    "name", "metric", "frequency", "recipients", "is_active", "include_pdf", "filters_json",
    "report_type", "include_narrative", "day_of_week", "day_of_month", "send_hour", "recipients_extra",
}


def update_scheduled_report(report_id: str, payload: dict, db: Session) -> dict:
    r = db.query(ScheduledReport).filter(ScheduledReport.id == report_id).first()
    if not r:
        raise ErrorDeDominio(404, "Informe no encontrado")
    ajenos = sorted(set(payload) - CAMPOS_EDITABLES_INFORME)
    if ajenos:
        raise ErrorDeDominio(422, f"Campos no editables: {', '.join(ajenos)}")
    for k, v in payload.items():
        if k in ("recipients", "recipients_extra"):
            setattr(r, k, json.dumps(v))
        else:
            setattr(r, k, v)
    if {"frequency", "send_hour", "day_of_week", "day_of_month"} & set(payload):
        from app.services.scheduled_reports import proxima_ejecucion
        r.next_run_at = proxima_ejecucion(r)
    db.commit()
    return serialize_scheduled_report(r)


def delete_scheduled_report(report_id: str, db: Session) -> dict:
    r = db.query(ScheduledReport).filter(ScheduledReport.id == report_id).first()
    if not r:
        raise ErrorDeDominio(404)
    db.delete(r)
    db.commit()
    return {"ok": True}


def list_scheduled_reports(db: Session) -> list:
    reports = db.query(ScheduledReport).order_by(ScheduledReport.created_at.desc()).all()
    return [serialize_scheduled_report(r) for r in reports]


def save_report_definition(payload, current_user: User, db: Session) -> dict:
    r = ReportDefinition(
        name=payload.name, description=payload.description,
        category=payload.category, icon=payload.icon,
        is_public=payload.is_public, data_source=payload.data_source,
        filters=json.dumps(payload.filters) if payload.filters else None,
        columns=json.dumps(payload.columns) if payload.columns else None,
        group_by=payload.group_by, chart_type=payload.chart_type,
        chart_x=payload.chart_x, chart_y=payload.chart_y,
        schedule_cron=payload.schedule_cron,
        schedule_emails=json.dumps(payload.schedule_emails) if payload.schedule_emails else None,
        created_by=current_user.id,
    )
    db.add(r)
    db.commit()
    return {"ok": True, "id": r.id}


def delete_report_definition(report_id: str, current_user_id: str, db: Session) -> dict:
    r = db.query(ReportDefinition).filter(
        ReportDefinition.id == report_id,
        ReportDefinition.created_by == current_user_id,
        ReportDefinition.is_system == False,
    ).first()
    if not r:
        raise ErrorDeDominio(404)
    db.delete(r)
    db.commit()
    return {"ok": True}


def get_scheduled_report_by_id(report_id: str, db: Session):
    r = db.query(ScheduledReport).filter(ScheduledReport.id == report_id).first()
    if not r:
        raise ErrorDeDominio(404)
    return r


def serialize_scheduled_report(r) -> dict:
    return {
        "id": r.id,
        "name": r.name,
        "metric": r.metric,
        "frequency": r.frequency,
        "recipients": json.loads(r.recipients or "[]"),
        "include_pdf": r.include_pdf,
        "is_active": r.is_active,
        "last_run_at": str(r.last_run_at)[:16] if r.last_run_at else None,
        "next_run_at": str(r.next_run_at)[:16] if r.next_run_at else None,
        "created_at": str(r.created_at)[:16] if r.created_at else None,
    }
