"""
billing_reports — — all new v12 features:
  reports          — Report builder + saved reports + scheduling
  import           — Bulk CSV/Excel import
  invoices         — Basic invoicing
  itsm             — ITSM advanced: SLA engine, metrics, breach log
  workflows        — Multi-step automation workflows
  templates        — Project templates with full UI
  smartmatch       — AI resource recommendation
"""
from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File, Body, Response
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import func, or_
from typing import Any, Dict, Optional, List
from datetime import date, datetime, timedelta, timezone
import json
import csv
import io

from app.db.session import get_db
from app.core.config import settings
from app.core.deps import get_current_user, require_any_manager
from app.models.user import User
from app.models.project import Project
from app.models.task import Task
from app.models.imputation import Imputation
from app.models.resources import UserSkill
from app.models.billing_reports import (
    AutomationWorkflow, WorkflowStep, WorkflowExecution,
    ImportJob, ImportStatus, Invoice, InvoiceLine, ReportDefinition, WorkflowStatus
)
from app.services.audit import audit_log
from app.services.billing_reports.history_service import (
    get_import_jobs,
    get_workflow_executions,
)
from app.services.billing_reports.report_catalog_service import (
    build_report_catalog,
    dispatch_report,
    get_data_sources,
)
from app.services.billing_reports.data_source_service import (
    run_skills_report,
    run_pipeline_report,
)
from app.services.psa_flows import build_invoice_preview_from_timesheets_flow
from app.services.numbering import next_numbered_code
from app.schemas.billing_reports import (
    ReportSave,
    InvoiceCreate,
    WorkflowCreate,
    TemplateCreate,
    ScheduledReportCreate,
    InvoiceOut,
    InvoiceSummaryOut,
    InvoiceStatusUpdateOut,
    ReportSaveOut,
    ImportTemplateOut,
    ImportValidateOut,
    ImportExecuteOut,
    ImportJobHistoryOut,
    SlaDashboardOut,
    AgentPerformanceOut,
    SlaPauseResumeOut,
    AutomationWorkflowOut,
    WorkflowExecutionOut,
    ScheduledReportOut,
    ScheduledReportCreateOut,
    ScheduledReportRunOut,
    ProjectTemplateOut,
    TemplateCreateOut,
    TemplateInstantiateOut,
    SmartMatchOut,
    OkResponse,
)

router = APIRouter()


# ═══════════════════════════════════════════════════════════════════════════════
# REPORT BUILDER
# ═══════════════════════════════════════════════════════════════════════════════

# Report catalog/data sources are now centralized in report_catalog_service.


@router.get("/report-catalog/catalog", response_model=Dict[str, Any], summary="Catálogo de informes disponibles")
def report_catalog(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    """Return system reports + saved custom reports."""
    return build_report_catalog(db, current_user)


@router.get("/report-catalog/data-sources", response_model=Dict[str, Any], summary="Fuentes de datos disponibles")
def report_data_sources(current_user: User = Depends(require_any_manager)):
    return get_data_sources()


@router.post("/report-catalog/run", response_model=Dict[str, Any], summary="Ejecutar un informe con filtros")
def run_report(
    payload: dict = Body(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    """Execute a report query and return data for rendering."""
    report_id = payload.get("report_id")
    data_source = payload.get("data_source", "projects")
    filters = payload.get("filters", {})
    group_by = payload.get("group_by")
    date_from = payload.get("date_from")
    date_to = payload.get("date_to")
    project_id = payload.get("project_id")

    org_id = current_user.organization_id
    return dispatch_report(
        data_source=data_source,
        report_id=report_id,
        filters=filters,
        group_by=group_by,
        date_from=date_from,
        date_to=date_to,
        project_id=project_id,
        org_id=org_id,
        runners={
            "projects": lambda f, g, d1, d2, org_id=None: _run_projects_report(db, f, g, d1, d2, org_id=org_id),
            "imputations": lambda f, g, d1, d2, p, org_id=None: _run_imputations_report(db, f, g, d1, d2, p, org_id=org_id),
            "tickets": lambda f, g, d1, d2, org_id=None: _run_tickets_report(db, f, g, d1, d2, org_id=org_id),
            "expenses": lambda f, g, d1, d2, p, org_id=None: _run_expenses_report(db, f, g, d1, d2, p, org_id=org_id),
            "capacity": lambda f, d1, d2, org_id=None: _run_capacity_report(db, f, d1, d2, org_id=org_id),
            "skills": lambda f, org_id=None: run_skills_report(db, f, org_id=org_id),
            "pipeline": lambda f, org_id=None: run_pipeline_report(db, f, org_id=org_id),
            "system": lambda rid, f, d1, d2: _run_system_report(db, rid, f, d1, d2),
        },
    )


def _run_projects_report(db, filters, group_by, date_from, date_to, org_id=None):
    from app.models.project import Project
    from app.models.imputation import Imputation

    projects_q = db.query(Project).options(
        joinedload(Project.project_manager),
        joinedload(Project.imputations).joinedload(Imputation.user),
    )
    if org_id:
        projects_q = projects_q.filter(Project.organization_id == org_id)
    projects = projects_q.all()

    rows = []
    for p in projects:
        hours = sum(i.hours for i in p.imputations)
        cost = sum(i.hours * (i.user.hourly_rate or 0) for i in p.imputations if i.user)
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

    # Apply filters
    if filters.get("status"):
        rows = [r for r in rows if r["status"] == filters["status"]]

    total_revenue = sum(r["revenue"] for r in rows)
    total_cost = sum(r["cost"] for r in rows)
    avg_margin = round((total_revenue - total_cost) / total_revenue * 100, 1) if total_revenue > 0 else None

    return {
        "rows": rows,
        "totals": {"revenue": round(total_revenue,2), "cost": round(total_cost,2), "margin_pct": avg_margin, "count": len(rows)},
        "chart_data": [{"name": r["name"][:20], "cost": r["cost"], "revenue": r["revenue"], "margin": r["margin_pct"]} for r in rows if r["revenue"] > 0][:15],
    }


def _run_imputations_report(db, filters, group_by, date_from, date_to, project_id, org_id=None):
    from app.models.imputation import Imputation
    from app.models.project import Project as _Project

    q = db.query(Imputation).options(
        joinedload(Imputation.user), joinedload(Imputation.project)
    )
    if org_id:
        org_project_ids = [r.id for r in db.query(_Project.id).filter(
            _Project.organization_id == org_id
        ).all()]
        q = q.filter(Imputation.project_id.in_(org_project_ids))
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
        "cost": round(i.hours * (i.user.hourly_rate or 0), 2) if i.user else 0,
    } for i in imps]

    # Group by user
    by_user = {}
    for r in rows:
        name = r["user_name"]
        if name not in by_user: by_user[name] = {"name": name, "billable": 0, "non_billable": 0, "total": 0}
        if r["is_billable"]: by_user[name]["billable"] += r["hours"]
        else: by_user[name]["non_billable"] += r["hours"]
        by_user[name]["total"] += r["hours"]

    # Group by month
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


def _run_tickets_report(db, filters, group_by, date_from, date_to, org_id=None):
    from app.models.service_desk import Ticket

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
    resolved = sum(1 for r in rows if r["status"] in ["resolved","closed"])
    mttr_avg = round(sum(r["mttr_hours"] for r in rows if r["mttr_hours"]) / max(len([r for r in rows if r["mttr_hours"]]),1), 1)
    csat_avg = None
    csat_rows = [r for r in rows if r["csat_score"]]
    if csat_rows: csat_avg = round(sum(r["csat_score"] for r in csat_rows) / len(csat_rows), 1)

    by_priority = {}
    for r in rows:
        p = r["priority"]
        by_priority[p] = by_priority.get(p, 0) + 1

    return {
        "rows": rows[:200],
        "totals": {
            "total": total, "resolved": resolved,
            "sla_compliance_pct": round((total-breached)/max(total,1)*100, 1),
            "mttr_hours": mttr_avg, "avg_csat": csat_avg,
        },
        "chart_data": [{"priority": k, "count": v} for k, v in by_priority.items()],
    }


def _run_expenses_report(db, filters, group_by, date_from, date_to, project_id, org_id=None):
    from app.models.expenses import Expense
    from app.models.project import Project as _Project

    q = db.query(Expense).options(joinedload(Expense.user), joinedload(Expense.project)).filter(
        Expense.status.in_(["approved","reimbursed"])
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

    by_cat = {}
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


def _run_capacity_report(db, filters, date_from, date_to, org_id=None):
    from app.models.financial import CapacityPlan

    users_q = db.query(User).filter(User.is_active == True)
    if org_id:
        users_q = users_q.filter(User.organization_id == org_id)
    users = users_q.all()
    cap_user_ids = [u.id for u in users]

    plans = db.query(CapacityPlan).options(
        joinedload(CapacityPlan.user), joinedload(CapacityPlan.project)
    ).filter(CapacityPlan.user_id.in_(cap_user_ids)).all()

    # Aggregate by user
    by_user = {}
    for u in users:
        user_plans = [p for p in plans if p.user_id == u.id]
        total_assigned = sum(p.allocated_hours or 0 for p in user_plans)
        capacity = (u.weekly_capacity_hours or 40) * 12  # 12 weeks
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


def _run_system_report(db, report_id, filters, date_from, date_to):
    """Route to the right data function for system reports."""
    today = date.today()
    df = date_from or str(today - timedelta(days=90))
    dt = date_to or str(today)
    if report_id == "utilization_by_person": return _run_imputations_report(db, filters, "user", df, dt, None)
    if report_id == "margin_by_project":     return _run_projects_report(db, filters, "project", df, dt)
    if report_id == "wip_report":            return _run_projects_report(db, filters, None, df, dt)
    if report_id == "timesheet_hours_trend": return _run_imputations_report(db, filters, "month", df, dt, None)
    if report_id == "sla_compliance":        return _run_tickets_report(db, filters, None, df, dt)
    if report_id == "ticket_volume_trend":   return _run_tickets_report(db, filters, "week", df, dt)
    if report_id == "expense_by_project":    return _run_expenses_report(db, filters, "project", df, dt, None)
    if report_id == "capacity_forecast_12w": return _run_capacity_report(db, filters, df, dt)
    if report_id == "resource_skills_matrix": return run_skills_report(db, filters)
    if report_id == "pipeline_health":       return run_pipeline_report(db, filters)
    return _run_projects_report(db, filters, None, df, dt)


@router.post("/report-catalog/save", response_model=ReportSaveOut, summary="Guardar informe personalizado")
def save_report(
    payload: ReportSave,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
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
    db.add(r); db.commit()
    return {"ok": True, "id": r.id}


@router.delete("/report-catalog/{report_id}", response_model=OkResponse, summary="Eliminar informe guardado")
def delete_report(
    report_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    r = db.query(ReportDefinition).filter(
        ReportDefinition.id == report_id,
        ReportDefinition.created_by == current_user.id,
        ReportDefinition.is_system == False,
    ).first()
    if not r: raise HTTPException(404)
    db.delete(r); db.commit()
    return {"ok": True}


# ═══════════════════════════════════════════════════════════════════════════════
# BULK IMPORT
# ═══════════════════════════════════════════════════════════════════════════════

IMPORT_TEMPLATES = {
    "projects": {
        "columns": ["code","name","client_name","project_type","status","start_date","end_date_planned","budget_amount","billing_type","pm_email"],
        "example": [["PRJ-001","Proyecto Ejemplo","Cliente SA","consulting","active","2025-01-01","2025-06-30","50000","time_material","pm@empresa.com"]],
    },
    "tasks": {
        "columns": ["project_code","title","description","status","priority","assignee_email","due_date","estimated_hours","story_points"],
        "example": [["PRJ-001","Tarea ejemplo","Descripción...","todo","medium","dev@empresa.com","2025-03-31","8","5"]],
    },
    "users": {
        "columns": ["username","email","full_name","first_name","last_name","role","department","job_title","weekly_capacity_hours","hourly_rate"],
        "example": [["jdoe","jdoe@empresa.com","John Doe","John","Doe","employee","Engineering","Developer","40","65"]],
    },
    "imputations": {
        "columns": ["user_email","project_code","date","hours","description","is_billable","work_type"],
        "example": [["dev@empresa.com","PRJ-001","2025-01-15","4","Desarrollo módulo login","true","development"]],
    },
    "expenses": {
        "columns": ["user_email","project_code","category","description","amount","currency","expense_date","is_billable"],
        "example": [["dev@empresa.com","PRJ-001","travel","Vuelo Madrid-Barcelona","187.50","EUR","2025-01-20","true"]],
    },
}


@router.get("/import/template/{entity_type}", response_model=ImportTemplateOut, summary="Plantilla CSV para importación")
def get_import_template(
    entity_type: str,
    current_user: User = Depends(require_any_manager),
):
    if entity_type not in IMPORT_TEMPLATES:
        raise HTTPException(400, f"Tipo no válido. Opciones: {list(IMPORT_TEMPLATES.keys())}")
    tpl = IMPORT_TEMPLATES[entity_type]
    return {
        "entity_type": entity_type,
        "columns": tpl["columns"],
        "example": tpl["example"],
        "instructions": "Descarga esta plantilla, rellena los datos y sube el fichero CSV en el importador. La primera fila debe ser la cabecera.",
    }


@router.post("/import/validate", response_model=ImportValidateOut, summary="Validar CSV antes de importar")
def validate_import(
    entity_type: str,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    """Parse and validate CSV without writing to DB."""
    MAX_IMPORT_BYTES = 5 * 1024 * 1024  # 5 MB
    content = file.file.read()
    if len(content) > MAX_IMPORT_BYTES:
        raise HTTPException(status_code=413, detail="Fichero demasiado grande (máx 5 MB)")
    try:
        text = content.decode("utf-8-sig")  # Handle BOM
    except Exception:
        raise HTTPException(400, "El fichero debe ser UTF-8")

    reader = csv.DictReader(io.StringIO(text))
    rows = list(reader)
    if not rows:
        raise HTTPException(400, "El fichero está vacío")

    if entity_type not in IMPORT_TEMPLATES:
        raise HTTPException(400, "Tipo no válido")

    expected_cols = set(IMPORT_TEMPLATES[entity_type]["columns"])
    actual_cols = set(reader.fieldnames or [])
    missing = expected_cols - actual_cols
    extra = actual_cols - expected_cols

    errors = []
    warnings = []
    if missing: warnings.append(f"Columnas no encontradas: {missing}. Se usarán valores por defecto.")
    if extra:   warnings.append(f"Columnas adicionales ignoradas: {extra}")

    # Row-level validation
    for i, row in enumerate(rows[:10], 1):  # Preview first 10
        if entity_type == "projects":
            if not row.get("name"): errors.append({"row": i, "field": "name", "error": "Nombre obligatorio"})
            if not row.get("project_type"): errors.append({"row": i, "field": "project_type", "error": "Tipo obligatorio"})
        elif entity_type == "users":
            if not row.get("email"): errors.append({"row": i, "field": "email", "error": "Email obligatorio"})
            if not row.get("full_name"): errors.append({"row": i, "field": "full_name", "error": "Nombre completo obligatorio"})
        elif entity_type == "imputations":
            if not row.get("hours"): errors.append({"row": i, "field": "hours", "error": "Horas obligatorio"})
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


@router.post("/import/execute", response_model=ImportExecuteOut, summary="Ejecutar importación masiva")
def execute_import(
    entity_type: str,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    """Import data from CSV. Returns a job ID for progress tracking."""
    MAX_IMPORT_BYTES = 5 * 1024 * 1024  # 5 MB
    content = file.file.read()
    if len(content) > MAX_IMPORT_BYTES:
        raise HTTPException(status_code=413, detail="Fichero demasiado grande (máx 5 MB)")
    try:
        text = content.decode("utf-8-sig")
    except Exception:
        raise HTTPException(400, "El fichero debe ser UTF-8")

    reader = csv.DictReader(io.StringIO(text))
    rows = list(reader)

    job = ImportJob(
        entity_type=entity_type,
        filename=file.filename,
        status=ImportStatus.processing,
        total_rows=len(rows),
        created_by=current_user.id,
    )
    db.add(job); db.commit(); db.refresh(job)

    # Process import
    succeeded = 0; failed_rows = 0; errors = []

    if entity_type == "projects":
        for i, row in enumerate(rows, 1):
            try:
                p = Project(
                    code=row.get("code") or f"IMP-{i:04d}",
                    name=row["name"],
                    client_name=row.get("client_name"),
                    project_type=row.get("project_type", settings.DEFAULT_PROJECT_TYPE),
                    status=row.get("status", "planning"),
                    start_date=row.get("start_date") or None,
                    end_date_planned=row.get("end_date_planned") or None,
                    budget_amount=float(row["budget_amount"]) if row.get("budget_amount") else None,
                    billing_type=row.get("billing_type", settings.DEFAULT_BILLING_TYPE),
                    created_by=current_user.id,
                )
                db.add(p); succeeded += 1
            except Exception as e:
                failed_rows += 1
                errors.append({"row": i, "error": str(e)[:100]})

    elif entity_type == "users":
        from app.core.security import get_password_hash
        for i, row in enumerate(rows, 1):
            try:
                existing = db.query(User).filter(User.email == row["email"]).first()
                if existing:
                    errors.append({"row": i, "error": f"Email ya existe: {row['email']}"})
                    failed_rows += 1; continue
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
                    hashed_password=get_password_hash(settings.DEFAULT_USER_PASSWORD),  # Default password
                )
                db.add(u); succeeded += 1
            except Exception as e:
                failed_rows += 1; errors.append({"row": i, "error": str(e)[:100]})

    elif entity_type == "imputations":
        from app.models.imputation import Imputation
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
                db.add(imp); succeeded += 1
            except Exception as e:
                failed_rows += 1; errors.append({"row": i, "error": str(e)[:100]})

    # Finalize job
    job.status = ImportStatus.completed if failed_rows == 0 else (ImportStatus.partial if succeeded > 0 else ImportStatus.failed)
    job.processed = len(rows)
    job.succeeded = succeeded
    job.failed_rows = failed_rows
    job.errors = json.dumps(errors[:50])
    job.completed_at = datetime.now(timezone.utc)
    try:
        db.commit()
        audit_log(db, current_user, "IMPORT", entity_type, job.id, f"{file.filename}",
                  new_values={"succeeded": succeeded, "failed": failed_rows})
        db.commit()
    except Exception:
        db.rollback()
        raise HTTPException(500, "Error al finalizar la importación")

    return {
        "job_id": job.id,
        "status": job.status,
        "total": len(rows), "succeeded": succeeded, "failed": failed_rows,
        "errors": errors[:10],
    }


@router.get("/import/jobs", response_model=List[ImportJobHistoryOut], summary="Historial de importaciones")
def import_jobs(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    response: Response = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    return get_import_jobs(db, page, page_size, response)


# ═══════════════════════════════════════════════════════════════════════════════
# INVOICING
# ═══════════════════════════════════════════════════════════════════════════════

def _next_invoice_number(db: Session) -> str:
    return next_numbered_code(
        db,
        "invoice",
        prefix="INV",
        padding=4,
        include_year=True,
        reset_yearly=True,
    )


def _invoice_out(inv: Invoice) -> dict:
    return {
        "id": inv.id, "number": inv.number,
        "project_id": inv.project_id, "client_id": inv.client_id,
        "project_name": inv.project.name if inv.project else None,
        "project_code": inv.project.code if inv.project else None,
        "client_name": inv.client_name, "client_email": inv.client_email,
        "client_vat": inv.client_vat,
        "subtotal": inv.subtotal, "tax_rate": inv.tax_rate,
        "tax_amount": inv.tax_amount, "total": inv.total,
        "currency": inv.currency,
        "issue_date": str(inv.issue_date) if inv.issue_date else None,
        "due_date": str(inv.due_date) if inv.due_date else None,
        "paid_date": str(inv.paid_date) if inv.paid_date else None,
        "status": inv.status, "notes": inv.notes,
        "po_reference": inv.po_reference,
        "period_from": str(inv.period_from) if inv.period_from else None,
        "period_to": str(inv.period_to) if inv.period_to else None,
        "lines": [{
            "id": l.id, "order": l.order, "description": l.description,
            "quantity": l.quantity, "unit": l.unit,
            "unit_price": l.unit_price, "discount_pct": l.discount_pct,
            "amount": l.amount, "source_type": l.source_type,
        } for l in inv.lines],
        "created_at": str(inv.created_at)[:10] if inv.created_at else None,
    }


@router.get("/invoices", response_model=List[InvoiceOut], summary="Listar facturas")
def list_invoices(
    project_id: Optional[str] = None,
    status: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    q = db.query(Invoice).options(joinedload(Invoice.project), joinedload(Invoice.lines))
    if project_id: q = q.filter(Invoice.project_id == project_id)
    if status: q = q.filter(Invoice.status == status)
    invoices = q.order_by(Invoice.issue_date.desc()).all()
    return [_invoice_out(i) for i in invoices]


@router.post("/invoices/from-timesheets", response_model=Dict[str, Any], summary="Generar factura desde timesheets aprobados")
def invoice_from_timesheets(
    payload: dict = Body(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    """Auto-generate invoice lines from approved timesheets in a date range."""
    return build_invoice_preview_from_timesheets_flow(
        db=db,
        project_id=payload.get("project_id"),
        date_from=payload.get("date_from"),
        date_to=payload.get("date_to"),
        tax_rate=payload.get("tax_rate"),
    )


@router.post("/invoices", response_model=InvoiceOut, status_code=201, summary="Crear factura")
def create_invoice(
    payload: InvoiceCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    # Auto-fill client from project
    project = None
    if payload.project_id:
        project = db.query(Project).filter(Project.id == payload.project_id).first()

    client_name = payload.client_name or (project.client_name if project else None) or "Sin cliente"

    # Calculate totals
    subtotal = sum(l.get("amount", 0) for l in payload.lines)
    tax_amount = round(subtotal * payload.tax_rate / 100, 2)
    total = round(subtotal + tax_amount, 2)

    inv = Invoice(
        number=_next_invoice_number(db),
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
    db.add(inv); db.flush()

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

    # Mark imputations as invoiced so they cannot be re-included in a future invoice
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
    db.commit()
    inv = db.query(Invoice).options(joinedload(Invoice.project), joinedload(Invoice.lines)).filter(Invoice.id == inv.id).first()
    return _invoice_out(inv)


@router.patch("/invoices/{invoice_id}/status", response_model=InvoiceStatusUpdateOut, summary="Cambiar estado de factura")
def update_invoice_status(
    invoice_id: str,
    payload: dict = Body(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    inv = db.query(Invoice).filter(Invoice.id == invoice_id).first()
    if not inv: raise HTTPException(404)
    old_status = inv.status
    inv.status = payload.get("status", inv.status)
    if payload.get("status") == "paid":
        inv.paid_date = date.today()
    audit_log(db, current_user, "UPDATE", "invoices", inv.id, inv.number,
              old_values={"status": old_status}, new_values={"status": inv.status})
    db.commit()
    return {"ok": True, "status": inv.status}


@router.get(
    "/invoices/{invoice_id}/pdf",
    summary="Descargar factura en PDF",
    responses={200: {"content": {"application/pdf": {}}}},
)
def download_invoice_pdf(
    invoice_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    """Genera y devuelve el PDF de una factura."""
    from fastapi.responses import Response
    from app.services.invoice_pdf import generate_invoice_pdf

    inv = db.query(Invoice).filter(Invoice.id == invoice_id).first()
    if not inv:
        raise HTTPException(404, "Factura no encontrada")
    lines = db.query(InvoiceLine).filter(InvoiceLine.invoice_id == invoice_id).order_by(InvoiceLine.order).all()

    line_dicts = [
        {
            "description": l.description,
            "unit": l.unit,
            "quantity": l.quantity,
            "unit_price": l.unit_price,
            "amount": l.amount,
            "discount_pct": l.discount_pct,
        }
        for l in lines
    ]

    pdf_bytes = generate_invoice_pdf(
        invoice_number=inv.number,
        issue_date=inv.issue_date,
        due_date=inv.due_date,
        client_name=inv.client_name or "",
        client_address=inv.client_address,
        client_vat=inv.client_vat,
        client_email=inv.client_email,
        lines=line_dicts,
        subtotal=inv.subtotal or 0,
        tax_rate=inv.tax_rate or 0,
        tax_amount=inv.tax_amount or 0,
        total=inv.total or 0,
        currency=inv.currency or "EUR",
        notes=inv.notes,
        po_reference=inv.po_reference,
        period_from=inv.period_from,
        period_to=inv.period_to,
        company_name=settings.PROJECT_NAME,
        generated_by="Clarive PSA",
    )

    filename = f"factura_{inv.number.replace('/', '-')}.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/invoices/summary", response_model=InvoiceSummaryOut, summary="Resumen financiero de facturas")
def invoice_summary(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    invoices = db.query(Invoice).all()
    by_status = {}
    for inv in invoices:
        s = inv.status
        if s not in by_status: by_status[s] = {"count": 0, "total": 0}
        by_status[s]["count"] += 1
        by_status[s]["total"] += inv.total or 0

    overdue = [i for i in invoices if i.status == "sent" and i.due_date and i.due_date < date.today()]
    return {
        "by_status": {k: {"count": v["count"], "total": round(v["total"], 2)} for k, v in by_status.items()},
        "total_invoiced": round(sum(i.total or 0 for i in invoices), 2),
        "total_paid": round(sum(i.total or 0 for i in invoices if i.status == "paid"), 2),
        "total_pending": round(sum(i.total or 0 for i in invoices if i.status in ["sent","overdue"]), 2),
        "overdue_count": len(overdue),
        "overdue_amount": round(sum(i.total or 0 for i in overdue), 2),
    }


# ═══════════════════════════════════════════════════════════════════════════════
# ITSM ADVANCED METRICS
# ═══════════════════════════════════════════════════════════════════════════════

@router.get("/itsm-metrics/sla-dashboard", response_model=SlaDashboardOut, summary="Dashboard SLA en tiempo real")
def sla_dashboard(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    from app.models.service_desk import Ticket

    now = datetime.now(timezone.utc)
    open_statuses = ["new","assigned","in_progress","pending_client"]

    open_tickets = db.query(Ticket).filter(Ticket.status.in_(open_statuses)).all()

    breached = [t for t in open_tickets if t.sla_resolution_due and t.sla_resolution_due < now]
    at_risk_2h = [t for t in open_tickets if t.sla_resolution_due and now < t.sla_resolution_due <= now + timedelta(hours=2)]
    at_risk_4h = [t for t in open_tickets if t.sla_resolution_due and now + timedelta(hours=2) < t.sla_resolution_due <= now + timedelta(hours=4)]
    healthy = [t for t in open_tickets if not t.sla_resolution_due or t.sla_resolution_due > now + timedelta(hours=4)]

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

    # SLA compliance by priority (last 30 days)
    since = now - timedelta(days=30)
    past_tickets = db.query(Ticket).filter(Ticket.created_at >= since).all()
    compliance_by_priority = {}
    for pri in ["p1_critical","p2_high","p3_medium","p4_low"]:
        t_pri = [t for t in past_tickets if t.priority == pri]
        breached_pri = sum(1 for t in t_pri if t.sla_resolution_status == "breached" or (t.sla_resolution_due and t.resolved_at and t.resolved_at > t.sla_resolution_due))
        compliance_by_priority[pri] = {
            "total": len(t_pri),
            "breached": breached_pri,
            "compliance_pct": round((len(t_pri) - breached_pri) / max(len(t_pri), 1) * 100, 1),
        }

    # Heatmap: tickets by hour of day and day of week (last 30d)
    heatmap = {}
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
            "healthy": len(healthy),
        },
        "breached_tickets": [ticket_mini(t) for t in sorted(breached, key=lambda x: x.sla_resolution_due or now)[:10]],
        "at_risk_tickets": [ticket_mini(t) for t in sorted(at_risk_2h + at_risk_4h, key=lambda x: x.sla_resolution_due or now)[:10]],
        "compliance_by_priority": compliance_by_priority,
        "volume_heatmap": [{"day": int(k.split("_")[0]), "hour": int(k.split("_")[1]), "count": v} for k, v in heatmap.items()],
    }


@router.get("/itsm-metrics/agent-performance", response_model=List[AgentPerformanceOut], summary="Rendimiento por agente")
def agent_performance(
    days: int = Query(30),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    from app.models.service_desk import Ticket

    since = datetime.now(timezone.utc) - timedelta(days=days)
    tickets = db.query(Ticket).options(joinedload(Ticket.assigned_to)).filter(
        Ticket.created_at >= since,
        Ticket.assigned_to_user_id != None,
    ).all()

    by_agent = {}
    for t in tickets:
        aid = t.assigned_to_user_id
        if aid not in by_agent:
            by_agent[aid] = {
                "user_id": aid,
                "user_name": t.assigned_to.full_name if t.assigned_to else "—",
                "total": 0, "resolved": 0, "breached": 0,
                "total_mttr": 0, "csat_sum": 0, "csat_count": 0,
                "open": 0,
            }
        a = by_agent[aid]
        a["total"] += 1
        if t.status in ["resolved","closed"]:
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


def _business_minutes_between(start: datetime, end: datetime) -> int:
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
            # skip weekend to next Monday
            days_to_monday = 7 - current.weekday()
            current = (current + timedelta(days=days_to_monday)).replace(hour=0, minute=0, second=0, microsecond=0)
    return total


@router.post("/itsm-metrics/pause-sla/{ticket_id}", response_model=SlaPauseResumeOut, summary="Pausar/reanudar SLA (pendiente cliente)")
def pause_resume_sla(
    ticket_id: str,
    payload: dict = Body(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    from app.models.service_desk import Ticket
    ticket = db.query(Ticket).filter(Ticket.id == ticket_id).first()
    if not ticket: raise HTTPException(404)

    action = payload.get("action", "pause")  # pause | resume
    now = datetime.now(timezone.utc)

    if action == "pause" and not ticket.sla_paused_at:
        ticket.sla_paused_at = now
        ticket.sla_resolution_status = "paused"
        msg = "SLA pausado — esperando respuesta del cliente"
    elif action == "resume" and ticket.sla_paused_at:
        paused_minutes = _business_minutes_between(ticket.sla_paused_at, now)
        ticket.sla_pause_minutes = (ticket.sla_pause_minutes or 0) + paused_minutes
        # Extend SLA due by the paused time (business-only)
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
    return {"ok": True, "message": msg, "sla_resolution_due": str(ticket.sla_resolution_due)[:16] if ticket.sla_resolution_due else None}


# ═══════════════════════════════════════════════════════════════════════════════
# AUTOMATION WORKFLOWS (multi-step)
# ═══════════════════════════════════════════════════════════════════════════════

def _workflow_out(w: AutomationWorkflow) -> dict:
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


@router.get("/automation-workflows", response_model=List[AutomationWorkflowOut], summary="Listar workflows multi-paso")
def list_workflows(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    workflows = db.query(AutomationWorkflow).options(
        joinedload(AutomationWorkflow.steps),
        joinedload(AutomationWorkflow.project),
    ).order_by(AutomationWorkflow.created_at.desc()).all()
    return [_workflow_out(w) for w in workflows]


@router.post("/automation-workflows", response_model=AutomationWorkflowOut, status_code=201, summary="Crear workflow")
def create_workflow(
    payload: WorkflowCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    wf = AutomationWorkflow(
        name=payload.name, description=payload.description,
        project_id=payload.project_id, is_global=payload.is_global,
        trigger_type=payload.trigger_type,
        trigger_conditions=json.dumps(payload.trigger_conditions) if payload.trigger_conditions else None,
        status=WorkflowStatus.draft,
        created_by=current_user.id,
    )
    db.add(wf); db.flush()

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
    wf = db.query(AutomationWorkflow).options(joinedload(AutomationWorkflow.steps), joinedload(AutomationWorkflow.project)).filter(AutomationWorkflow.id == wf.id).first()
    return _workflow_out(wf)


@router.patch("/automation-workflows/{wf_id}", response_model=AutomationWorkflowOut, summary="Actualizar workflow")
def update_workflow(
    wf_id: str, payload: dict = Body(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    wf = db.query(AutomationWorkflow).filter(AutomationWorkflow.id == wf_id).first()
    if not wf: raise HTTPException(404)
    for k, v in payload.items():
        if k == "trigger_conditions" and v is not None: v = json.dumps(v)
        if hasattr(wf, k): setattr(wf, k, v)
    if "steps" in payload:
        for s in wf.steps: db.delete(s)
        db.flush()
        for i, step_data in enumerate(payload["steps"]):
            step = WorkflowStep(
                workflow_id=wf.id, order=i,
                step_type=step_data.get("step_type","action"),
                name=step_data.get("name"),
                config=json.dumps(step_data.get("config",{})),
                next_step_yes=step_data.get("next_step_yes"),
                next_step_no=step_data.get("next_step_no"),
            )
            db.add(step)
    db.commit()
    wf = db.query(AutomationWorkflow).options(joinedload(AutomationWorkflow.steps), joinedload(AutomationWorkflow.project)).filter(AutomationWorkflow.id == wf_id).first()
    return _workflow_out(wf)


@router.delete("/automation-workflows/{wf_id}", response_model=OkResponse, summary="Eliminar workflow")
def delete_workflow(wf_id: str, db: Session = Depends(get_db), current_user: User = Depends(require_any_manager)):
    wf = db.query(AutomationWorkflow).filter(AutomationWorkflow.id == wf_id).first()
    if not wf: raise HTTPException(404)
    db.delete(wf); db.commit()
    return {"ok": True}


@router.get("/automation-workflows/{wf_id}/executions", response_model=List[WorkflowExecutionOut], summary="Historial de ejecuciones")
def workflow_executions(
    wf_id: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    response: Response = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    return get_workflow_executions(db, wf_id, page, page_size, response)


# ═══════════════════════════════════════════════════════════════════════════════
# PROJECT TEMPLATES (full UI)
# ═══════════════════════════════════════════════════════════════════════════════

@router.get("/templates", response_model=List[ProjectTemplateOut], summary="Listar plantillas de proyecto")
def list_templates(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    from app.models.advanced_config import ProjectTemplate, TemplatePhase
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


@router.post("/templates", response_model=TemplateCreateOut, status_code=201, summary="Crear plantilla de proyecto")
def create_template(
    payload: TemplateCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    from app.models.advanced_config import ProjectTemplate, TemplatePhase, TemplateTask, TemplateRisk, TemplateDeliverable

    t = ProjectTemplate(
        name=payload.name, description=payload.description,
        project_type=payload.project_type,
        estimated_weeks=payload.estimated_weeks,
        estimated_hours=payload.estimated_hours,
        created_by=current_user.id,
    )
    db.add(t); db.flush()

    for i, ph_data in enumerate(payload.phases):
        phase_order = ph_data.get("phase_order", i)
        ph = TemplatePhase(
            template_id=t.id, name=ph_data["name"],
            description=ph_data.get("description"),
            order=phase_order, estimated_weeks=ph_data.get("estimated_weeks", 1),
        )
        db.add(ph); db.flush()
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


@router.post("/templates/{template_id}/instantiate", response_model=TemplateInstantiateOut, summary="Crear proyecto desde plantilla")
def instantiate_template(
    template_id: str,
    payload: dict = Body(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    """Create a real project from a template, copying phases/tasks/risks/deliverables."""
    from app.models.advanced_config import ProjectTemplate, TemplatePhase
    from app.models.project import ProjectPhase
    from app.models.task import Task

    tpl = db.query(ProjectTemplate).options(
        joinedload(ProjectTemplate.phases).joinedload(TemplatePhase.tasks),
        joinedload(ProjectTemplate.risks), joinedload(ProjectTemplate.deliverables),
    ).filter(ProjectTemplate.id == template_id).first()
    if not tpl: raise HTTPException(404, "Plantilla no encontrada")

    # Create project
    project_name = payload.get("name", f"{tpl.name} — {date.today()}")
    start = date.fromisoformat(payload["start_date"]) if payload.get("start_date") else date.today()

    # Get next code
    last = db.query(Project).order_by(Project.created_at.desc()).first()
    next_num = 1
    if last and last.code and last.code.startswith("PRJ-"):
        parts = last.code.split("-")
        if len(parts) > 1 and parts[1].isdigit():
            next_num = int(parts[1]) + 1
    code = f"PRJ-{next_num:03d}"

    project = Project(
        code=payload.get("code", code),
        name=project_name,
        description=payload.get("description", tpl.description),
        project_type=tpl.project_type or settings.DEFAULT_PROJECT_TYPE,
        client_name=payload.get("client_name"),
        pm_id=payload.get("pm_id"),
        start_date=start,
        end_date_planned=start + timedelta(weeks=tpl.estimated_weeks or 12) if tpl.estimated_weeks else None,
        budget_hours=tpl.estimated_hours,
        budget_amount=payload.get("budget_amount"),
        billing_type=payload.get("billing_type", settings.DEFAULT_BILLING_TYPE),
        is_billable=payload.get("is_billable", True),
        created_by=current_user.id,
    )
    db.add(project); db.flush()

    # Copy phases + tasks
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
        db.add(ph); db.flush()

        for tk_tpl in ph_tpl.tasks:
            task_due = phase_start + timedelta(weeks=ph_tpl.estimated_weeks or 1)
            db.add(Task(
                project_id=project.id,
                phase_id=ph.id,
                code=f"{project.code}-T{db.query(func.count(Task.id)).filter(Task.project_id == project.id).scalar()+1:03d}",
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
# SMARTMATCH — Resource recommendation
# ═══════════════════════════════════════════════════════════════════════════════

@router.post("/smartmatch", response_model=SmartMatchOut, summary="SmartMatch — sugerir mejores recursos para una tarea/proyecto")
def smartmatch(
    payload: dict = Body(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    """
    Recommend top resources for a project slot based on:
    - Required skills
    - Current availability (capacity - assigned hours)
    - Cost rate
    - Current workload (number of active tasks)
    """
    required_skills = payload.get("skills", [])       # list of skill names
    required_role   = payload.get("role")              # optional role filter
    start_date      = payload.get("start_date")
    end_date        = payload.get("end_date")
    hours_needed    = payload.get("hours_needed", 40)
    max_rate        = payload.get("max_hourly_rate")
    project_id      = payload.get("project_id") # noqa: F841 F401

    # Base query
    users = db.query(User).options(
        joinedload(User.task_assignments),
    ).filter(User.is_active == True)
    if required_role: users = users.filter(User.role == required_role)
    users = users.all()

    # Get skills index
    user_skills = db.query(UserSkill).options(joinedload(UserSkill.skill)).all()
    skill_map = {}  # user_id -> [skill names]
    skill_level_map = {}  # (user_id, skill_name) -> level
    for us in user_skills:
        if us.skill:
            skill_map.setdefault(us.user_id, []).append(us.skill.name.lower())
            skill_level_map[(us.user_id, us.skill.name.lower())] = us.level

    # Get active tasks count
    active_tasks = db.query(
        Task.assignee_id,
        func.count(Task.id).label("count")
    ).filter(Task.status.notin_(["done","cancelled"])).group_by(Task.assignee_id).all()
    task_count_map = {r.assignee_id: r.count for r in active_tasks}

    results = []
    for user in users:
        # Skill matching score
        user_skill_names = skill_map.get(user.id, [])
        required_lower = [s.lower() for s in required_skills]
        matched_skills = [s for s in required_lower if s in user_skill_names]
        skill_score = len(matched_skills) / max(len(required_lower), 1) if required_lower else 1.0
        _LEVEL_NUM = {"basic": 1, "intermediate": 2, "advanced": 3, "expert": 4}
        def _lvl(v):
            if isinstance(v, int): return v
            if hasattr(v, 'value'): return _LEVEL_NUM.get(v.value, 1)
            return _LEVEL_NUM.get(str(v), 1)
        avg_skill_level = sum(_lvl(skill_level_map.get((user.id, s), 1)) for s in matched_skills) / max(len(matched_skills), 1) if matched_skills else 1.0

        # Availability score
        capacity = user.weekly_capacity_hours or settings.DEFAULT_WEEKLY_CAPACITY_HOURS
        active_task_load = task_count_map.get(user.id, 0)
        # Rough availability: capacity * weeks in range
        weeks = max((timedelta(weeks=2)).days / 7, 1)
        if start_date and end_date:
            try:
                d1 = date.fromisoformat(start_date); d2 = date.fromisoformat(end_date)
                weeks = max((d2 - d1).days / 7, 0.5)
            except ValueError:
                raise HTTPException(400, "Formato de fecha inválido en start_date/end_date, se espera YYYY-MM-DD")
        total_available = capacity * weeks
        availability_score = min(total_available / max(hours_needed, 1), 1.0)

        # Cost score (lower cost = higher score, unless max_rate set)
        rate = user.hourly_rate or 0
        if max_rate and rate > max_rate: continue  # Filter out
        cost_score = 1.0 if rate == 0 else min(1.0, 1 - (rate / 200))  # normalized vs max 200

        # Workload score (fewer tasks = higher score)
        workload_score = max(0, 1 - active_task_load / 20)

        # Composite score (weighted)
        score = (skill_score * 0.4 + availability_score * 0.3 + workload_score * 0.2 + cost_score * 0.1)

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
            "recommendation": "🟢 Excelente" if score > 0.75 else "🟡 Buena opción" if score > 0.5 else "🟠 Posible" if score > 0.25 else "🔴 No recomendado",
        })

    results.sort(key=lambda x: -x["scores"]["overall"])
    top = results[:5]

    return {
        "query": {"skills": required_skills, "role": required_role, "hours_needed": hours_needed, "start_date": start_date, "end_date": end_date},
        "candidates": top,
        "total_evaluated": len(results),
        "message": f"Se evaluaron {len(results)} recursos. Top {len(top)} recomendados." if results else "No se encontraron recursos con los criterios indicados.",
    }

# ── Scheduled Reports (persistentes en BD) ────────────────────────────────────

def _sr_out(r) -> dict:
    import json as _json
    return {
        "id":           r.id,
        "name":         r.name,
        "metric":       r.metric,
        "frequency":    r.frequency,
        "recipients":   _json.loads(r.recipients or "[]"),
        "include_pdf":  r.include_pdf,
        "is_active":    r.is_active,
        "last_run_at":  str(r.last_run_at)[:16] if r.last_run_at else None,
        "next_run_at":  str(r.next_run_at)[:16] if r.next_run_at else None,
        "created_at":   str(r.created_at)[:16]  if r.created_at  else None,
    }


@router.get("/scheduled-reports", response_model=List[ScheduledReportOut], summary="Listar informes programados")
def list_scheduled_reports(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    from app.models.billing_reports import ScheduledReport
    reports = db.query(ScheduledReport).order_by(ScheduledReport.created_at.desc()).all()
    return [_sr_out(r) for r in reports]


@router.post("/scheduled-reports", response_model=ScheduledReportCreateOut, status_code=201, summary="Crear informe programado")
def create_scheduled_report(
    payload: ScheduledReportCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    from app.models.billing_reports import ScheduledReport
    from app.services.scheduled_reports import _get_next_run
    import json as _json
    r = ScheduledReport(
        name         = payload.name,
        metric       = payload.metric,
        frequency    = payload.frequency,
        recipients   = _json.dumps(payload.recipients),
        include_pdf  = payload.include_pdf,
        filters_json = payload.filters_json or "{}",
        next_run_at  = _get_next_run(payload.frequency),
        created_by   = current_user.id,
    )
    db.add(r); db.commit(); db.refresh(r)
    return {"ok": True, "id": r.id}


@router.patch("/scheduled-reports/{report_id}", response_model=ScheduledReportOut, summary="Actualizar informe programado")
def update_scheduled_report(
    report_id: str,
    payload: dict = Body(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    from app.models.billing_reports import ScheduledReport
    import json as _json
    r = db.query(ScheduledReport).filter(ScheduledReport.id == report_id).first()
    if not r: raise HTTPException(404, "Informe no encontrado")
    for k, v in payload.items():
        if k == "recipients": setattr(r, k, _json.dumps(v))
        elif hasattr(r, k):   setattr(r, k, v)
    db.commit()
    return _sr_out(r)


@router.delete("/scheduled-reports/{report_id}", response_model=OkResponse, summary="Eliminar informe programado")
def delete_scheduled_report(
    report_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    from app.models.billing_reports import ScheduledReport
    r = db.query(ScheduledReport).filter(ScheduledReport.id == report_id).first()
    if not r: raise HTTPException(404)
    db.delete(r); db.commit()
    return {"ok": True}


@router.post("/scheduled-reports/{report_id}/run", response_model=ScheduledReportRunOut, summary="Ejecutar informe ahora")
def run_scheduled_report(
    report_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    from app.services.scheduled_reports import execute_report_now
    result = execute_report_now(report_id, db)
    if not result["ok"]:
        raise HTTPException(500, result.get("error", "Error al ejecutar"))
    return result


@router.get(
    "/scheduled-reports/{report_id}/preview-pdf",
    summary="Previsualizar PDF del informe",
    responses={200: {"content": {"application/pdf": {}}}},
)
def preview_report_pdf(
    report_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    from app.models.billing_reports import ScheduledReport
    from app.services.report_pdf import generate_report_pdf
    from fastapi.responses import Response

    r = db.query(ScheduledReport).filter(ScheduledReport.id == report_id).first()
    if not r: raise HTTPException(404)

    pdf_bytes = generate_report_pdf(
        title=r.name,
        metric_label=(r.metric or "").replace("_", " ").title(),
        data=[{"Ejemplo": "Datos de previsualización", "Valor": "—"}],
        summary={"Estado": "Previsualización", "Métrica": r.metric or "—"},
    )
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="preview_{r.id}.pdf"'}
    )
