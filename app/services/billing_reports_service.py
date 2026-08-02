"""
billing_reports_service — business logic extracted from billing_reports.py router.
Covers: report runners, invoice helpers, SLA helpers, workflow/scheduled-report
serializers, SmartMatch, template instantiation, bulk import helpers.
"""

from __future__ import annotations

import csv
import enum
import io
import json
import logging
import secrets
from datetime import date, datetime, timedelta, timezone

from fastapi import HTTPException
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import func, text
from sqlalchemy.exc import OperationalError

from app.core.config import settings
from app.models.user import User
from app.models.project import Project, ProjectPhase
from app.models.task import Task
from app.models.imputation import Imputation
from app.models.project import Project as _Project
from app.models.financial import CapacityPlan
from app.models.resources import UserSkill
from app.models.billing_reports import (
    AutomationWorkflow, WorkflowStep, ImportJob, ImportStatus, Invoice, InvoiceLine, ReportDefinition,
    WorkflowStatus, ScheduledReport,
)
from app.models.service_desk import Ticket
from app.models.expenses import Expense
from app.models.advanced_config import (
    ProjectTemplate, TemplatePhase, TemplateTask, TemplateRisk, TemplateDeliverable,
)
from app.services.audit import audit_log
from app.services.numbering import next_numbered_code
from app.schemas.billing_reports import InvoiceOut, InvoiceLineOut
from app.core.security import get_password_hash
from app.models.billing_reports import InvoiceLine as _InvoiceLine
from app.services.billing_reports.data_source_service import run_skills_report, run_pipeline_report
from app.services.scheduled_reports import _get_next_run
from app.db.session import is_postgres

_logger = logging.getLogger(__name__)


def _tenant_org_id(db: Session):
    return db.info.get("organization_id")


def _is_superadmin(db: Session) -> bool:
    return bool(db.info.get("is_superadmin", False))


def _query_project_for_org(db: Session, project_id: str):
    q = db.query(Project).filter(Project.id == project_id)
    org_id = _tenant_org_id(db)
    if not _is_superadmin(db) and org_id is not None:
        q = q.filter(Project.organization_id == org_id)
    return q


def _lock_project_for_update(db: Session, project_id: str):
    q = _query_project_for_org(db, project_id)
    if is_postgres():
        q = q.with_for_update()
    return q.first()


def _set_serializable_if_postgres(db: Session) -> None:
    # Transaction-level hardening for financial writes in PostgreSQL.
    if is_postgres():
        db.execute(text("SET LOCAL TRANSACTION ISOLATION LEVEL SERIALIZABLE"))


def _is_serialization_failure(exc: OperationalError) -> bool:
    code = getattr(getattr(exc, "orig", None), "pgcode", None)
    return str(code) == "40001"


def _scope_invoice_query(db: Session):
    q = db.query(Invoice)
    org_id = _tenant_org_id(db)
    if _is_superadmin(db):
        return q
    if org_id is None:
        return q.filter(Invoice.id == "__no_access__")
    return q.filter(Invoice.organization_id == org_id)


# Obtener una factura por ID
def get_invoice_by_id(db: Session, invoice_id: str):
    return _scope_invoice_query(db).filter(Invoice.id == invoice_id).first()


# Devuelve un query filtrable y el total para paginación de facturas
def query_invoices(db: Session, project_id=None, status=None):
    q = _scope_invoice_query(db)
    if project_id:
        q = q.filter(Invoice.project_id == project_id)
    if status:
        q = q.filter(Invoice.status == status)
    total = q.count()
    return q.order_by(Invoice.issue_date.desc()), total


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
        q = q.filter(Ticket.assigned_to_id.in_(org_agent_ids))
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
    resolved = sum(1 for r in rows if r["status"] in ["resolved", "closed"])
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
    if project_id: q = q.filter(Expense.project_id == project_id)

    expenses = q.all()
    rows = [{
        "code": e.code, "user_name": e.user.full_name if e.user else "—",
        "project_name": e.project.name if e.project else "Sin proyecto",
        "category": e.category, "description": e.description[:60],
        "amount": e.amount, "currency": e.currency,
        "expense_date": str(e.expense_date), "is_billable": e.is_billable,
        "status": e.status,
    } for e in expenses]

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


def run_system_report(db: Session, report_id: str, filters: dict, date_from, date_to) -> dict:

    today = date.today()
    df = date_from or str(today - timedelta(days=90))
    dt = date_to or str(today)
    if report_id == "utilization_by_person":  return run_imputations_report(db, filters, "user", df, dt, None)
    if report_id == "margin_by_project":      return run_projects_report(db, filters, "project", df, dt)
    if report_id == "wip_report":             return run_projects_report(db, filters, None, df, dt)
    if report_id == "timesheet_hours_trend":  return run_imputations_report(db, filters, "month", df, dt, None)
    if report_id == "sla_compliance":         return run_tickets_report(db, filters, None, df, dt)
    if report_id == "ticket_volume_trend":    return run_tickets_report(db, filters, "week", df, dt)
    if report_id == "expense_by_project":     return run_expenses_report(db, filters, "project", df, dt, None)
    if report_id == "capacity_forecast_12w":  return run_capacity_report(db, filters, df, dt)
    if report_id == "resource_skills_matrix": return run_skills_report(db, filters)
    if report_id == "pipeline_health":        return run_pipeline_report(db, filters)
    return run_projects_report(db, filters, None, df, dt)


# ═══════════════════════════════════════════════════════════════════════════════
# INVOICE HELPERS
# ═══════════════════════════════════════════════════════════════════════════════

def next_invoice_number(db: Session) -> str:
    return next_numbered_code(
        db,
        "invoice",
        prefix="INV",
        padding=4,
        include_year=True,
        reset_yearly=True,
        year_separator="-",
    )


def invoice_out(inv: Invoice) -> dict:
    return InvoiceOut(
        id=inv.id,
        number=inv.number,
        project_id=inv.project_id,
        client_id=inv.client_id,
        project_name=inv.project.name if inv.project else None,
        project_code=inv.project.code if inv.project else None,
        client_name=inv.client_name,
        client_email=inv.client_email,
        client_vat=inv.client_vat,
        subtotal=inv.subtotal,
        tax_rate=inv.tax_rate,
        tax_amount=inv.tax_amount,
        total=inv.total,
        currency=inv.currency,
        issue_date=inv.issue_date,
        due_date=inv.due_date,
        paid_date=inv.paid_date,
        status=inv.status,
        notes=inv.notes,
        po_reference=inv.po_reference,
        period_from=inv.period_from,
        period_to=inv.period_to,
        lines=[
            InvoiceLineOut(
                id=l.id, order=l.order, description=l.description,
                quantity=l.quantity, unit=l.unit,
                unit_price=l.unit_price, discount_pct=l.discount_pct,
                amount=l.amount, source_type=l.source_type,
            )
            for l in inv.lines
        ],
        created_at=inv.created_at.date() if inv.created_at else None,
    ).model_dump()


# ═══════════════════════════════════════════════════════════════════════════════
# SLA HELPER
# ═══════════════════════════════════════════════════════════════════════════════

def business_minutes_between(start: datetime, end: datetime) -> int:
    """Roughly calculate elapsed minutes in business days (Mon-Fri)."""
    if start >= end:
        return 0
    total = 0
    current = start
    while current < end:
        if current.weekday() < 5:
            next_day = (current + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
            segment_end = min(end, next_day)
            total += int((segment_end - current).total_seconds() / 60)
            current = segment_end
        else:
            days_to_monday = 7 - current.weekday()
            current = (current + timedelta(days=days_to_monday)).replace(hour=0, minute=0, second=0, microsecond=0)
    return total


# ═══════════════════════════════════════════════════════════════════════════════
# INVOICE CRUD
# ═══════════════════════════════════════════════════════════════════════════════

def create_invoice(payload, current_user: User, db: Session) -> dict:
    _set_serializable_if_postgres(db)
    project = None
    if payload.project_id:
        project = _lock_project_for_update(db, payload.project_id)
        if not project:
            raise HTTPException(status_code=404, detail="Proyecto no encontrado o no accesible")

    client_name = payload.client_name or (project.client_name if project else None) or "Sin cliente"
    subtotal = sum(l.get("amount", 0) for l in payload.lines)
    tax_amount = round(subtotal * payload.tax_rate / 100, 2)
    total = round(subtotal + tax_amount, 2)

    inv = Invoice(
        number=next_invoice_number(db),
        organization_id=(getattr(current_user, "organization_id", None) if not getattr(current_user, "is_superadmin", False) else getattr(project, "organization_id", None)),
        project_id=payload.project_id,
        contract_id=payload.contract_id,
        client_name=client_name,
        client_address=payload.client_address,
        client_vat=payload.client_vat,
        client_email=payload.client_email,
        issue_date=payload.issue_date,
        due_date=payload.due_date,
        tax_rate=payload.tax_rate,
        tax_amount=tax_amount,
        subtotal=round(subtotal, 2),
        total=total,
        currency=payload.currency,
        notes=payload.notes,
        po_reference=payload.po_reference,
        period_from=payload.period_from,
        period_to=payload.period_to,
        created_by=current_user.id,
    )
    db.add(inv)
    db.flush()

    for i, line_data in enumerate(payload.lines):
        line = InvoiceLine(
            invoice_id=inv.id, order=i,
            description=line_data.get("description", ""),
            quantity=line_data.get("quantity", 1),
            unit=line_data.get("unit", "h"),
            unit_price=line_data.get("unit_price", 0),
            discount_pct=line_data.get("discount_pct", 0),
            amount=line_data.get("amount", 0),
            source_type=line_data.get("source_type"),
            source_ids=json.dumps(line_data.get("source_ids", [])),
        )
        db.add(line)

    for line_data in payload.lines:
        if line_data.get("source_type") == "timesheet":
            raw_ids = line_data.get("source_ids", [])
            imp_ids = json.loads(raw_ids) if isinstance(raw_ids, str) else raw_ids
            if imp_ids:
                db.query(Imputation).filter(Imputation.id.in_(imp_ids)).update(
                    {"is_invoiced": True, "invoiced_invoice_id": inv.id},
                    synchronize_session=False,
                )

    audit_log(db, current_user, "CREATE", "invoices", inv.id, inv.number)
    try:
        db.commit()
    except OperationalError as exc:
        db.rollback()
        if _is_serialization_failure(exc):
            raise HTTPException(status_code=409, detail="Concurrent financial update detected. Please retry.")
        raise
    try:
        from app.core.metrics import invoices_created_total
        _status = getattr(inv, "status", None)
        invoices_created_total.labels(
            tenant_id=str(getattr(inv, "organization_id", None) or "unknown"),
            status=str(getattr(_status, "value", _status) or "draft"),
        ).inc()
    except Exception:
        _logger.debug("create_invoice: fallo best-effort ignorado", exc_info=True)
    inv = db.query(Invoice).options(
        joinedload(Invoice.project), joinedload(Invoice.lines)
    ).filter(Invoice.id == inv.id).first()
    return invoice_out(inv)


def update_invoice_status(invoice_id: str, payload: dict, current_user: User, db: Session) -> dict:
    _set_serializable_if_postgres(db)
    inv_q = _scope_invoice_query(db).filter(Invoice.id == invoice_id)
    if is_postgres():
        inv_q = inv_q.with_for_update()
    inv = inv_q.first()
    if not inv:
        raise HTTPException(404)
    old_status = inv.status.value if isinstance(inv.status, enum.Enum) else str(inv.status)
    new_status = payload.get("status", old_status)
    # Definir transiciones válidas
    allowed_transitions = {
        "draft":    ["sent", "cancelled"],
        "sent":     ["paid", "overdue", "cancelled"],
        "overdue":  ["paid", "cancelled"],
        "paid":     [],
        "cancelled": [],
    }
    if new_status == old_status:
        db.commit()
        return invoice_out(inv)
    if new_status not in allowed_transitions.get(old_status, []):
        raise HTTPException(400, f"Transición de estado no permitida: {old_status} → {new_status}")
    # Assign as Enum if possible
    from app.models.billing_reports import InvoiceStatus
    try:
        inv.status = InvoiceStatus(new_status)
    except Exception:
        _logger.warning("Estado de factura no es enum válido, usando string crudo: %s", new_status)
        inv.status = new_status
    if new_status == "paid":
        inv.paid_date = date.today()
    audit_log(db, current_user, "UPDATE", "invoices", inv.id, inv.number,
              old_values={"status": old_status}, new_values={"status": inv.status.value if isinstance(inv.status, enum.Enum) else str(inv.status)})
    try:
        db.commit()
    except OperationalError as exc:
        db.rollback()
        if _is_serialization_failure(exc):
            raise HTTPException(status_code=409, detail="Concurrent financial update detected. Please retry.")
        raise
    return invoice_out(inv)


def get_invoice_summary(db: Session) -> dict:
    invoices = _scope_invoice_query(db).all()
    by_status: dict = {}
    for inv in invoices:
        s = inv.status
        if s not in by_status:
            by_status[s] = {"count": 0, "total": 0}
        by_status[s]["count"] += 1
        by_status[s]["total"] += inv.total or 0

    overdue = [i for i in invoices if i.status == "sent" and i.due_date and i.due_date < date.today()]
    return {
        "by_status": {k: {"count": v["count"], "total": round(v["total"], 2)} for k, v in by_status.items()},
        "total_invoiced": round(sum(i.total or 0 for i in invoices), 2),
        "total_paid": round(sum(i.total or 0 for i in invoices if i.status == "paid"), 2),
        "total_pending": round(sum(i.total or 0 for i in invoices if i.status in ["sent", "overdue"]), 2),
        "overdue_count": len(overdue),
        "overdue_amount": round(sum(i.total or 0 for i in overdue), 2),
    }


# ═══════════════════════════════════════════════════════════════════════════════
# ITSM METRICS
# ═══════════════════════════════════════════════════════════════════════════════

def get_sla_dashboard(db: Session) -> dict:
    now = datetime.now(timezone.utc)
    open_statuses = ["new", "assigned", "in_progress", "pending_client"]
    open_tickets = db.query(Ticket).filter(Ticket.status.in_(open_statuses)).all()

    breached = [t for t in open_tickets if t.sla_resolution_due and t.sla_resolution_due < now]
    at_risk_2h = [t for t in open_tickets if t.sla_resolution_due and now < t.sla_resolution_due <= now + timedelta(hours=2)]
    at_risk_4h = [t for t in open_tickets if t.sla_resolution_due and now + timedelta(hours=2) < t.sla_resolution_due <= now + timedelta(hours=4)]

    def ticket_mini(t):
        breach_minutes = int((now - t.sla_resolution_due).total_seconds() / 60) if t.sla_resolution_due and t.sla_resolution_due < now else None
        remaining_minutes = int((t.sla_resolution_due - now).total_seconds() / 60) if t.sla_resolution_due and t.sla_resolution_due > now else None
        return {
            "id": t.id, "number": t.number, "title": t.title[:60],
            "priority": t.priority, "status": t.status,
            "assigned_to": t.assigned_to_user_id,
            "sla_due": str(t.sla_resolution_due)[:16] if t.sla_resolution_due else None,
            "breach_minutes": breach_minutes,
            "remaining_minutes": remaining_minutes,
            "requester": t.requester_name,
        }

    since = now - timedelta(days=30)
    past_tickets = db.query(Ticket).filter(Ticket.created_at >= since).all()
    compliance_by_priority: dict = {}
    for pri in ["p1_critical", "p2_high", "p3_medium", "p4_low"]:
        t_pri = [t for t in past_tickets if t.priority == pri]
        breached_pri = sum(1 for t in t_pri if t.sla_resolution_status == "breached" or (
            t.sla_resolution_due and t.resolved_at and t.resolved_at > t.sla_resolution_due))
        compliance_by_priority[pri] = {
            "total": len(t_pri),
            "breached": breached_pri,
            "compliance_pct": round((len(t_pri) - breached_pri) / max(len(t_pri), 1) * 100, 1),
        }

    heatmap: dict = {}
    for t in past_tickets:
        if t.created_at:
            key = f"{t.created_at.weekday()}_{t.created_at.hour}"
            heatmap[key] = heatmap.get(key, 0) + 1

    return {
        "real_time": {
            "open": len(open_tickets),
            "breached": len(breached),
            "at_risk_2h": len(at_risk_2h),
            "at_risk_4h": len(at_risk_4h),
            "healthy": len([t for t in open_tickets if not t.sla_resolution_due or t.sla_resolution_due > now + timedelta(hours=4)]),
        },
        "breached_tickets": [ticket_mini(t) for t in sorted(breached, key=lambda x: x.sla_resolution_due or now)[:10]],
        "at_risk_tickets": [ticket_mini(t) for t in sorted(at_risk_2h + at_risk_4h, key=lambda x: x.sla_resolution_due or now)[:10]],
        "compliance_by_priority": compliance_by_priority,
        "volume_heatmap": [{"day": int(k.split("_")[0]), "hour": int(k.split("_")[1]), "count": v} for k, v in heatmap.items()],
    }


def get_agent_performance(days: int, db: Session) -> list:
    since = datetime.now(timezone.utc) - timedelta(days=days)
    tickets = db.query(Ticket).options(joinedload(Ticket.assigned_to)).filter(
        Ticket.created_at >= since,
        Ticket.assigned_to_user_id != None,
    ).all()

    by_agent: dict = {}
    for t in tickets:
        aid = t.assigned_to_user_id
        if aid not in by_agent:
            by_agent[aid] = {
                "user_id": aid,
                "user_name": t.assigned_to.full_name if t.assigned_to else "—",
                "total": 0, "resolved": 0, "breached": 0,
                "total_mttr": 0, "csat_sum": 0, "csat_count": 0, "open": 0,
            }
        a = by_agent[aid]
        a["total"] += 1
        if t.status in ["resolved", "closed"]:
            a["resolved"] += 1
            if t.resolved_at and t.created_at:
                a["total_mttr"] += (t.resolved_at - t.created_at).total_seconds() / 3600
        else:
            a["open"] += 1
        if t.sla_resolution_status == "breached":
            a["breached"] += 1
        if t.csat_score:
            a["csat_sum"] += t.csat_score
            a["csat_count"] += 1

    result = []
    for a in by_agent.values():
        result.append({
            **a,
            "avg_mttr_hours": round(a["total_mttr"] / max(a["resolved"], 1), 1),
            "avg_csat": round(a["csat_sum"] / max(a["csat_count"], 1), 1) if a["csat_count"] else None,
            "sla_compliance_pct": round((a["total"] - a["breached"]) / max(a["total"], 1) * 100, 1),
            "resolution_rate_pct": round(a["resolved"] / max(a["total"], 1) * 100, 1),
        })
    return sorted(result, key=lambda x: -x["total"])


def pause_resume_sla(ticket_id: str, payload: dict, db: Session) -> dict:
    ticket = db.query(Ticket).filter(Ticket.id == ticket_id).first()
    if not ticket:
        raise HTTPException(404)

    action = payload.get("action", "pause")
    now = datetime.now(timezone.utc)

    if action == "pause" and not ticket.sla_paused_at:
        ticket.sla_paused_at = now
        ticket.sla_resolution_status = "paused"
        msg = "SLA pausado — esperando respuesta del cliente"
    elif action == "resume" and ticket.sla_paused_at:
        paused_minutes = business_minutes_between(ticket.sla_paused_at, now)
        ticket.sla_pause_minutes = (ticket.sla_pause_minutes or 0) + paused_minutes
        if ticket.sla_resolution_due:
            ticket.sla_resolution_due = ticket.sla_resolution_due + timedelta(minutes=paused_minutes)
        if ticket.sla_response_due:
            ticket.sla_response_due = ticket.sla_response_due + timedelta(minutes=paused_minutes)
        ticket.sla_paused_at = None
        ticket.sla_resolution_status = "ok"
        msg = f"SLA reanudado. {paused_minutes} minutos de horario laboral añadidos al plazo."
    else:
        return {"ok": False, "message": "Estado SLA no permite esta acción"}

    db.commit()
    return {
        "ok": True, "message": msg,
        "sla_resolution_due": str(ticket.sla_resolution_due)[:16] if ticket.sla_resolution_due else None,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# WORKFLOW CRUD
# ═══════════════════════════════════════════════════════════════════════════════

def create_workflow(payload, current_user: User, db: Session) -> dict:
    wf = AutomationWorkflow(
        name=payload.name, description=payload.description,
        project_id=payload.project_id, is_global=payload.is_global,
        trigger_type=payload.trigger_type,
        trigger_conditions=json.dumps(payload.trigger_conditions) if payload.trigger_conditions else None,
        status=WorkflowStatus.draft,
        created_by=current_user.id,
    )
    db.add(wf)
    db.flush()

    for i, step_data in enumerate(payload.steps):
        step = WorkflowStep(
            workflow_id=wf.id, order=i,
            step_type=step_data.get("step_type", "action"),
            name=step_data.get("name"),
            config=json.dumps(step_data.get("config", {})),
            next_step_yes=step_data.get("next_step_yes"),
            next_step_no=step_data.get("next_step_no"),
        )
        db.add(step)

    db.commit()
    wf = db.query(AutomationWorkflow).options(
        joinedload(AutomationWorkflow.steps), joinedload(AutomationWorkflow.project)
    ).filter(AutomationWorkflow.id == wf.id).first()
    return serialize_workflow(wf)


def update_workflow(wf_id: str, payload: dict, db: Session) -> dict:
    wf = db.query(AutomationWorkflow).filter(AutomationWorkflow.id == wf_id).first()
    if not wf:
        raise HTTPException(404)
    for k, v in payload.items():
        if k == "trigger_conditions" and v is not None:
            v = json.dumps(v)
        if hasattr(wf, k):
            setattr(wf, k, v)
    if "steps" in payload:
        for s in wf.steps:
            db.delete(s)
        db.flush()
        for i, step_data in enumerate(payload["steps"]):
            step = WorkflowStep(
                workflow_id=wf.id, order=i,
                step_type=step_data.get("step_type", "action"),
                name=step_data.get("name"),
                config=json.dumps(step_data.get("config", {})),
                next_step_yes=step_data.get("next_step_yes"),
                next_step_no=step_data.get("next_step_no"),
            )
            db.add(step)
    db.commit()
    wf = db.query(AutomationWorkflow).options(
        joinedload(AutomationWorkflow.steps), joinedload(AutomationWorkflow.project)
    ).filter(AutomationWorkflow.id == wf_id).first()
    return serialize_workflow(wf)


# ═══════════════════════════════════════════════════════════════════════════════
# PROJECT TEMPLATE CRUD
# ═══════════════════════════════════════════════════════════════════════════════

def create_template(payload, current_user: User, db: Session) -> dict:
    t = ProjectTemplate(
        name=payload.name, description=payload.description,
        project_type=payload.project_type,
        estimated_weeks=payload.estimated_weeks,
        estimated_hours=payload.estimated_hours,
        created_by=current_user.id,
    )
    db.add(t)
    db.flush()

    for i, ph_data in enumerate(payload.phases):
        phase_order = ph_data.get("phase_order", i)
        ph = TemplatePhase(
            template_id=t.id, name=ph_data["name"],
            description=ph_data.get("description"),
            order=phase_order, estimated_weeks=ph_data.get("estimated_weeks", 1),
        )
        db.add(ph)
        db.flush()
        for j, tk_data in enumerate(ph_data.get("tasks", [])):
            task_order = tk_data.get("task_order", j)
            db.add(TemplateTask(
                phase_id=ph.id, title=tk_data["title"],
                description=tk_data.get("description"),
                estimated_hours=tk_data.get("estimated_hours", 0),
                skill_required=tk_data.get("skill_required") or tk_data.get("role_required"),
                order=task_order,
            ))

    for rk_data in payload.risks:
        db.add(TemplateRisk(
            template_id=t.id,
            title=rk_data.get("title", "Riesgo"),
            category=rk_data.get("category"),
            probability=rk_data.get("probability", "medium"),
            impact=rk_data.get("impact", "moderate"),
            mitigation_plan=rk_data.get("mitigation_plan"),
        ))
    for dl_data in payload.deliverables:
        db.add(TemplateDeliverable(
            template_id=t.id,
            name=dl_data.get("name") or dl_data.get("title") or "Entregable",
            format=dl_data.get("format"),
            acceptance_criteria=dl_data.get("acceptance_criteria"),
            week_offset=dl_data.get("week_offset") if dl_data.get("week_offset") is not None else dl_data.get("deliverable_order"),
            billing_pct=dl_data.get("billing_pct"),
        ))

    audit_log(db, current_user, "CREATE", "project_templates", t.id, t.name)
    db.commit()
    return {"ok": True, "id": t.id}


# ═══════════════════════════════════════════════════════════════════════════════
# SCHEDULED REPORTS CRUD
# ═══════════════════════════════════════════════════════════════════════════════

def create_scheduled_report(payload, current_user: User, db: Session) -> dict:
    r = ScheduledReport(
        name=payload.name,
        metric=payload.metric,
        frequency=payload.frequency,
        recipients=json.dumps(payload.recipients),
        include_pdf=payload.include_pdf,
        filters_json=payload.filters_json or "{}",
        next_run_at=_get_next_run(payload.frequency),
        created_by=current_user.id,
    )
    db.add(r)
    db.commit()
    db.refresh(r)
    return {"ok": True, "id": r.id}


def update_scheduled_report(report_id: str, payload: dict, db: Session) -> dict:
    r = db.query(ScheduledReport).filter(ScheduledReport.id == report_id).first()
    if not r:
        raise HTTPException(404, "Informe no encontrado")
    for k, v in payload.items():
        if k == "recipients":
            setattr(r, k, json.dumps(v))
        elif hasattr(r, k):
            setattr(r, k, v)
    db.commit()
    return serialize_scheduled_report(r)


def delete_scheduled_report(report_id: str, db: Session) -> dict:
    r = db.query(ScheduledReport).filter(ScheduledReport.id == report_id).first()
    if not r:
        raise HTTPException(404)
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
        raise HTTPException(404)
    db.delete(r)
    db.commit()
    return {"ok": True}


def list_invoices(project_id: str | None, status: str | None, db: Session) -> list:
    q = db.query(Invoice).options(joinedload(Invoice.project), joinedload(Invoice.lines))
    if project_id:
        q = q.filter(Invoice.project_id == project_id)
    if status:
        q = q.filter(Invoice.status == status)
    return [invoice_out(i) for i in q.order_by(Invoice.issue_date.desc()).all()]


def list_workflows_all(db: Session) -> list:
    workflows = db.query(AutomationWorkflow).options(
        joinedload(AutomationWorkflow.steps),
        joinedload(AutomationWorkflow.project),
    ).order_by(AutomationWorkflow.created_at.desc()).all()
    return [serialize_workflow(w) for w in workflows]


def delete_workflow(wf_id: str, db: Session) -> dict:
    wf = db.query(AutomationWorkflow).filter(AutomationWorkflow.id == wf_id).first()
    if not wf:
        raise HTTPException(404)
    db.delete(wf)
    db.commit()
    return {"ok": True}


def list_templates_all(db: Session) -> list:
    templates = db.query(ProjectTemplate).options(
        joinedload(ProjectTemplate.phases).joinedload(TemplatePhase.tasks),
        joinedload(ProjectTemplate.risks),
        joinedload(ProjectTemplate.deliverables),
    ).filter(ProjectTemplate.is_active == True).all()
    return [{
        "id": t.id, "name": t.name, "description": t.description,
        "project_type": t.project_type,
        "estimated_weeks": t.estimated_weeks,
        "estimated_hours": t.estimated_hours,
        "phases": [{
            "id": ph.id, "name": ph.name, "order": ph.order,
            "estimated_weeks": ph.estimated_weeks,
            "tasks": [{
                "id": tk.id, "title": tk.title, "estimated_hours": tk.estimated_hours,
                "skill_required": tk.skill_required,
            } for tk in ph.tasks],
        } for ph in sorted(t.phases, key=lambda x: x.order)],
        "risk_count": len(t.risks),
        "deliverable_count": len(t.deliverables),
    } for t in templates]


def get_invoice_for_pdf(invoice_id: str, db: Session):
    inv = db.query(Invoice).filter(Invoice.id == invoice_id).first()
    if not inv:
        raise HTTPException(404, "Factura no encontrada")
    lines = db.query(_InvoiceLine).filter(_InvoiceLine.invoice_id == invoice_id).order_by(_InvoiceLine.order).all()
    return inv, lines


def get_scheduled_report_by_id(report_id: str, db: Session):
    r = db.query(ScheduledReport).filter(ScheduledReport.id == report_id).first()
    if not r:
        raise HTTPException(404)
    return r


# ═══════════════════════════════════════════════════════════════════════════════
# SERIALIZERS
# ═══════════════════════════════════════════════════════════════════════════════

def serialize_workflow(w: AutomationWorkflow) -> dict:
    return {
        "id": w.id, "name": w.name, "description": w.description,
        "project_id": w.project_id,
        "project_name": w.project.name if w.project else None,
        "is_global": w.is_global, "status": w.status,
        "trigger_type": w.trigger_type,
        "trigger_conditions": json.loads(w.trigger_conditions) if w.trigger_conditions else None,
        "steps": [{
            "id": s.id, "order": s.order, "step_type": s.step_type,
            "name": s.name,
            "config": json.loads(s.config) if s.config else {},
            "next_step_yes": s.next_step_yes,
            "next_step_no": s.next_step_no,
        } for s in w.steps],
        "run_count": w.run_count or 0,
        "success_count": w.success_count or 0,
        "error_count": w.error_count or 0,
        "last_run_at": str(w.last_run_at)[:16] if w.last_run_at else None,
    }


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


# ═══════════════════════════════════════════════════════════════════════════════
# SMARTMATCH
# ═══════════════════════════════════════════════════════════════════════════════

def smartmatch(payload: dict, db: Session) -> dict:
    """Recommend top resources based on skills, availability, cost, workload."""
    required_skills = payload.get("skills", [])
    required_role = payload.get("role")
    start_date = payload.get("start_date")
    end_date = payload.get("end_date")
    hours_needed = payload.get("hours_needed", 40)
    max_rate = payload.get("max_hourly_rate")

    users = db.query(User).options(
        joinedload(User.task_assignments),
    ).filter(User.is_active == True)
    if required_role:
        users = users.filter(User.role == required_role)
    users = users.all()

    user_skills = db.query(UserSkill).options(joinedload(UserSkill.skill)).all()
    skill_map: dict = {}
    skill_level_map: dict = {}
    for us in user_skills:
        if us.skill:
            skill_map.setdefault(us.user_id, []).append(us.skill.name.lower())
            skill_level_map[(us.user_id, us.skill.name.lower())] = us.level

    active_tasks = db.query(
        Task.assignee_id,
        func.count(Task.id).label("count")
    ).filter(Task.status.notin_(["done", "cancelled"])).group_by(Task.assignee_id).all()
    task_count_map = {r.assignee_id: r.count for r in active_tasks}

    _LEVEL_NUM = {"basic": 1, "intermediate": 2, "advanced": 3, "expert": 4}

    def _lvl(v):
        if isinstance(v, int): return v
        if hasattr(v, "value"): return _LEVEL_NUM.get(v.value, 1)
        return _LEVEL_NUM.get(str(v), 1)

    results = []
    for user in users:
        user_skill_names = skill_map.get(user.id, [])
        required_lower = [s.lower() for s in required_skills]
        matched_skills = [s for s in required_lower if s in user_skill_names]
        skill_score = len(matched_skills) / max(len(required_lower), 1) if required_lower else 1.0
        avg_skill_level = (
            sum(_lvl(skill_level_map.get((user.id, s), 1)) for s in matched_skills) /
            max(len(matched_skills), 1)
        ) if matched_skills else 1.0

        capacity = user.weekly_capacity_hours or settings.DEFAULT_WEEKLY_CAPACITY_HOURS
        active_task_load = task_count_map.get(user.id, 0)
        weeks = max((timedelta(weeks=2)).days / 7, 1)
        if start_date and end_date:
            try:
                d1 = date.fromisoformat(start_date)
                d2 = date.fromisoformat(end_date)
                weeks = max((d2 - d1).days / 7, 0.5)
            except ValueError:
                raise HTTPException(400, "Formato de fecha inválido en start_date/end_date, se espera YYYY-MM-DD")
        total_available = capacity * weeks
        availability_score = min(total_available / max(hours_needed, 1), 1.0)

        rate = user.hourly_rate or 0
        if max_rate and rate > max_rate:
            continue
        cost_score = 1.0 if rate == 0 else min(1.0, 1 - (rate / 200))
        workload_score = max(0, 1 - active_task_load / 20)

        score = skill_score * 0.4 + availability_score * 0.3 + workload_score * 0.2 + cost_score * 0.1

        results.append({
            "user_id": user.id,
            "user_name": user.full_name,
            "role": user.role,
            "department": user.department,
            "job_title": user.job_title,
            "hourly_rate": rate,
            "weekly_capacity": capacity,
            "active_tasks": active_task_load,
            "matched_skills": matched_skills,
            "missing_skills": [s for s in required_lower if s not in user_skill_names],
            "avg_skill_level": round(avg_skill_level, 1),
            "availability_hours": round(total_available, 1),
            "scores": {
                "overall": round(score * 100, 1),
                "skills": round(skill_score * 100, 1),
                "availability": round(availability_score * 100, 1),
                "workload": round(workload_score * 100, 1),
                "cost": round(cost_score * 100, 1),
            },
            "recommendation": (
                "🟢 Excelente" if score > 0.75
                else "🟡 Buena opción" if score > 0.5
                else "🟠 Posible" if score > 0.25
                else "🔴 No recomendado"
            ),
        })

    results.sort(key=lambda x: -x["scores"]["overall"])
    top = results[:5]
    return {
        "query": {"skills": required_skills, "role": required_role, "hours_needed": hours_needed,
                  "start_date": start_date, "end_date": end_date},
        "candidates": top,
        "total_evaluated": len(results),
        "message": (
            f"Se evaluaron {len(results)} recursos. Top {len(top)} recomendados."
            if results else "No se encontraron recursos con los criterios indicados."
        ),
    }


# ═══════════════════════════════════════════════════════════════════════════════
# TEMPLATE INSTANTIATION
# ═══════════════════════════════════════════════════════════════════════════════

def instantiate_template(template_id: str, payload: dict, current_user: User, db: Session) -> dict:
    """Create a real project from a template, copying phases/tasks/risks/deliverables."""
    tpl = db.query(ProjectTemplate).options(
        joinedload(ProjectTemplate.phases).joinedload(TemplatePhase.tasks),
        joinedload(ProjectTemplate.risks),
        joinedload(ProjectTemplate.deliverables),
    ).filter(ProjectTemplate.id == template_id).first()
    if not tpl:
        raise ValueError("template_not_found")

    project_name = payload.get("name", f"{tpl.name} — {date.today()}")
    start = date.fromisoformat(payload["start_date"]) if payload.get("start_date") else date.today()

    last = db.query(Project).order_by(Project.created_at.desc()).first()
    next_num = 1
    if last and last.code and last.code.startswith("PRJ-"):
        parts = last.code.split("-")
        if len(parts) > 1 and parts[1].isdigit():
            next_num = int(parts[1]) + 1
    code = f"PRJ-{next_num:03d}"

    from app.services.settings_service import get_runtime_str
    _proj_type = get_runtime_str(db, "DEFAULT_PROJECT_TYPE") or settings.DEFAULT_PROJECT_TYPE
    _bill_type = get_runtime_str(db, "DEFAULT_BILLING_TYPE") or settings.DEFAULT_BILLING_TYPE
    project = Project(
        code=payload.get("code", code),
        name=project_name,
        description=payload.get("description", tpl.description),
        project_type=tpl.project_type or _proj_type,
        client_name=payload.get("client_name"),
        pm_id=payload.get("pm_id"),
        start_date=start,
        end_date_planned=start + timedelta(weeks=tpl.estimated_weeks or 12) if tpl.estimated_weeks else None,
        budget_hours=tpl.estimated_hours,
        budget_amount=payload.get("budget_amount"),
        billing_type=payload.get("billing_type", _bill_type),
        is_billable=payload.get("is_billable", True),
        created_by=current_user.id,
    )
    db.add(project)
    db.flush()

    phase_offset = 0
    for ph_tpl in sorted(tpl.phases, key=lambda x: x.order):
        phase_start = start + timedelta(weeks=phase_offset)
        ph = ProjectPhase(
            project_id=project.id,
            name=ph_tpl.name,
            description=ph_tpl.description,
            order=ph_tpl.order,
            start_date=phase_start,
            end_date=phase_start + timedelta(weeks=ph_tpl.estimated_weeks or 1),
        )
        db.add(ph)
        db.flush()

        for tk_tpl in ph_tpl.tasks:
            task_due = phase_start + timedelta(weeks=ph_tpl.estimated_weeks or 1)
            db.add(Task(
                project_id=project.id,
                phase_id=ph.id,
                code=f"{project.code}-T{db.query(func.count(Task.id)).filter(Task.project_id == project.id).scalar() + 1:03d}",
                title=tk_tpl.title,
                description=tk_tpl.description,
                estimated_hours=tk_tpl.estimated_hours,
                priority="medium",
                due_date=task_due,
                created_by=current_user.id,
            ))

        phase_offset += ph_tpl.estimated_weeks or 1

    db.commit()
    audit_log(db, current_user, "CREATE_FROM_TEMPLATE", "projects", project.id, project.name,
              new_values={"template_id": template_id, "template_name": tpl.name})
    db.commit()

    return {
        "ok": True, "project_id": project.id, "project_code": project.code,
        "project_name": project.name,
        "phases_created": len(tpl.phases),
        "tasks_created": sum(len(ph.tasks) for ph in tpl.phases),
    }


# ═══════════════════════════════════════════════════════════════════════════════
# BULK IMPORT
# ═══════════════════════════════════════════════════════════════════════════════

IMPORT_TEMPLATES = {
    "projects": {
        "columns": ["code", "name", "client_name", "project_type", "status", "start_date",
                    "end_date_planned", "budget_amount", "billing_type", "pm_email"],
        "example": [["PRJ-001", "Proyecto Ejemplo", "Cliente SA", "consulting", "active",
                     "2025-01-01", "2025-06-30", "50000", "time_material", "pm@empresa.com"]],
    },
    "tasks": {
        "columns": ["project_code", "title", "description", "status", "priority",
                    "assignee_email", "due_date", "estimated_hours", "story_points"],
        "example": [["PRJ-001", "Tarea ejemplo", "Descripción...", "todo", "medium",
                     "dev@empresa.com", "2025-03-31", "8", "5"]],
    },
    "users": {
        "columns": ["username", "email", "full_name", "first_name", "last_name", "role",
                    "department", "job_title", "weekly_capacity_hours", "hourly_rate"],
        "example": [["jdoe", "jdoe@empresa.com", "John Doe", "John", "Doe", "employee",
                     "Engineering", "Developer", "40", "65"]],
    },
    "imputations": {
        "columns": ["user_email", "project_code", "date", "hours", "description",
                    "is_billable", "work_type"],
        "example": [["dev@empresa.com", "PRJ-001", "2025-01-15", "4",
                     "Desarrollo módulo login", "true", "development"]],
    },
    "expenses": {
        "columns": ["user_email", "project_code", "category", "description",
                    "amount", "currency", "expense_date", "is_billable"],
        "example": [["dev@empresa.com", "PRJ-001", "travel", "Vuelo Madrid-Barcelona",
                     "187.50", "EUR", "2025-01-20", "true"]],
    },
}


def validate_import_csv(entity_type: str, content: bytes) -> dict:
    MAX_IMPORT_BYTES = 5 * 1024 * 1024
    if len(content) > MAX_IMPORT_BYTES:
        raise ValueError("too_large")
    try:
        text = content.decode("utf-8-sig")
    except Exception:
        _logger.warning("CSV import validation rejected non-UTF8 payload", exc_info=True)
        raise ValueError("not_utf8")

    reader = csv.DictReader(io.StringIO(text))
    rows = list(reader)
    if not rows:
        raise ValueError("empty")

    if entity_type not in IMPORT_TEMPLATES:
        raise ValueError("invalid_type")

    expected_cols = set(IMPORT_TEMPLATES[entity_type]["columns"])
    actual_cols = set(reader.fieldnames or [])
    missing = expected_cols - actual_cols
    extra = actual_cols - expected_cols

    errors = []
    warnings = []
    if missing:  warnings.append(f"Columnas no encontradas: {missing}. Se usarán valores por defecto.")
    if extra:    warnings.append(f"Columnas adicionales ignoradas: {extra}")

    for i, row in enumerate(rows[:10], 1):
        if entity_type == "projects":
            if not row.get("name"):          errors.append({"row": i, "field": "name", "error": "Nombre obligatorio"})
            if not row.get("project_type"):  errors.append({"row": i, "field": "project_type", "error": "Tipo obligatorio"})
        elif entity_type == "users":
            if not row.get("email"):         errors.append({"row": i, "field": "email", "error": "Email obligatorio"})
            if not row.get("full_name"):     errors.append({"row": i, "field": "full_name", "error": "Nombre completo obligatorio"})
        elif entity_type == "imputations":
            if not row.get("hours"):         errors.append({"row": i, "field": "hours", "error": "Horas obligatorio"})
            try:
                if row.get("hours"): float(row["hours"])
            except ValueError:
                errors.append({"row": i, "field": "hours", "error": f"Valor inválido: {row.get('hours')}"})

    return {
        "valid": len(errors) == 0,
        "total_rows": len(rows),
        "errors": errors,
        "warnings": warnings,
        "preview": rows[:5],
    }


def execute_import_csv(entity_type: str, content: bytes, filename: str, current_user: User, db: Session) -> dict:
    MAX_IMPORT_BYTES = 5 * 1024 * 1024
    if len(content) > MAX_IMPORT_BYTES:
        raise ValueError("too_large")
    try:
        text = content.decode("utf-8-sig")
    except Exception:
        _logger.warning("CSV import execution rejected non-UTF8 payload (filename=%s)", filename, exc_info=True)
        raise ValueError("not_utf8")

    reader = csv.DictReader(io.StringIO(text))
    rows = list(reader)

    job = ImportJob(
        entity_type=entity_type,
        filename=filename,
        status=ImportStatus.processing,
        total_rows=len(rows),
        created_by=current_user.id,
    )
    db.add(job)
    db.commit()
    db.refresh(job)

    succeeded = 0
    failed_rows = 0
    errors = []

    if entity_type == "projects":
        from app.services.settings_service import get_runtime_str
        _proj_type = get_runtime_str(db, "DEFAULT_PROJECT_TYPE") or settings.DEFAULT_PROJECT_TYPE
        _bill_type = get_runtime_str(db, "DEFAULT_BILLING_TYPE") or settings.DEFAULT_BILLING_TYPE
        for i, row in enumerate(rows, 1):
            try:
                p = Project(
                    code=row.get("code") or f"IMP-{i:04d}",
                    name=row["name"],
                    client_name=row.get("client_name"),
                    project_type=row.get("project_type", _proj_type),
                    status=row.get("status", "planning"),
                    start_date=row.get("start_date") or None,
                    end_date_planned=row.get("end_date_planned") or None,
                    budget_amount=float(row["budget_amount"]) if row.get("budget_amount") else None,
                    billing_type=row.get("billing_type", _bill_type),
                    created_by=current_user.id,
                )
                db.add(p)
                succeeded += 1
            except Exception as e:
                _logger.warning("CSV import row %s failed for projects: %s", i, e, exc_info=True)
                failed_rows += 1
                errors.append({"row": i, "error": str(e)[:100]})

    elif entity_type == "users":
        for i, row in enumerate(rows, 1):
            try:
                existing = db.query(User).filter(User.email == row["email"]).first()
                if existing:
                    errors.append({"row": i, "error": f"Email ya existe: {row['email']}"})
                    failed_rows += 1
                    continue
                u = User(
                    username=row.get("username") or row["email"].split("@")[0],
                    email=row["email"],
                    full_name=row["full_name"],
                    first_name=row.get("first_name"),
                    last_name=row.get("last_name"),
                    role=row.get("role", "employee"),
                    department=row.get("department"),
                    job_title=row.get("job_title"),
                    weekly_capacity_hours=float(row["weekly_capacity_hours"]) if row.get("weekly_capacity_hours") else settings.DEFAULT_WEEKLY_CAPACITY_HOURS,
                    hourly_rate=float(row["hourly_rate"]) if row.get("hourly_rate") else None,
                    # Seguridad: cada usuario importado recibe una contraseña ALEATORIA y única
                    # (no la DEFAULT_USER_PASSWORD compartida y conocida). El usuario debe
                    # establecerla vía "olvidé mi contraseña"; así una importación masiva no
                    # crea cuentas accesibles con una credencial por defecto compartida.
                    hashed_password=get_password_hash(secrets.token_urlsafe(24)),
                )
                db.add(u)
                succeeded += 1
            except Exception as e:
                _logger.warning("CSV import row %s failed for users: %s", i, e, exc_info=True)
                failed_rows += 1
                errors.append({"row": i, "error": str(e)[:100]})

    elif entity_type == "imputations":
        for i, row in enumerate(rows, 1):
            try:
                user = db.query(User).filter(User.email == row.get("user_email")).first()
                project = db.query(Project).filter(Project.code == row.get("project_code")).first()
                if not user: raise ValueError(f"Usuario no encontrado: {row.get('user_email')}")
                if not project: raise ValueError(f"Proyecto no encontrado: {row.get('project_code')}")
                imp = Imputation(
                    user_id=user.id,
                    project_id=project.id,
                    date=row["date"],
                    hours=float(row["hours"]),
                    description=row.get("description", ""),
                    is_billable=row.get("is_billable", "true").lower() == "true",
                    work_type=row.get("work_type", "development"),
                )
                db.add(imp)
                succeeded += 1
            except Exception as e:
                _logger.warning("CSV import row %s failed for imputations: %s", i, e, exc_info=True)
                failed_rows += 1
                errors.append({"row": i, "error": str(e)[:100]})

    job.status = ImportStatus.completed if failed_rows == 0 else (
        ImportStatus.partial if succeeded > 0 else ImportStatus.failed
    )
    job.processed = len(rows)
    job.succeeded = succeeded
    job.failed_rows = failed_rows
    job.errors = json.dumps(errors[:50])
    job.completed_at = datetime.now(timezone.utc)
    try:
        db.commit()
        audit_log(db, current_user, "IMPORT", entity_type, job.id, filename,
                  new_values={"succeeded": succeeded, "failed": failed_rows})
        db.commit()
    except Exception:
        _logger.exception("Fallo finalizando import CSV (entity=%s, job=%s)", entity_type, job.id)
        db.rollback()
        raise RuntimeError("finalize_failed")

    return {
        "job_id": job.id,
        "status": job.status,
        "total": len(rows), "succeeded": succeeded, "failed": failed_rows,
        "errors": errors[:10],
    }
