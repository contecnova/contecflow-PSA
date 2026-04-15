"""
billing_reports — thin router delegating to app.services.billing_reports_service
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
from app.models.project import Project as _Project, ProjectPhase
from app.models.financial import CapacityPlan
from app.models.resources import UserSkill
from app.models.billing_reports import (
    AutomationWorkflow, WorkflowStep, WorkflowExecution,
    ImportJob, ImportStatus, Invoice, InvoiceLine, ReportDefinition, WorkflowStatus,
    ScheduledReport,
)
from app.models.service_desk import Ticket
from app.models.expenses import Expense
from app.models.advanced_config import ProjectTemplate, TemplatePhase, TemplateTask, TemplateRisk, TemplateDeliverable
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
    InvoiceOut,
    InvoiceLineOut,
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
import app.services.billing_reports_service as _svc

router = APIRouter()

# Local aliases kept for backward compatibility
def _run_projects_report(db, filters, group_by, date_from, date_to, org_id=None):
    return _svc.run_projects_report(db, filters, group_by, date_from, date_to, org_id=org_id)

def _run_imputations_report(db, filters, group_by, date_from, date_to, project_id, org_id=None):
    return _svc.run_imputations_report(db, filters, group_by, date_from, date_to, project_id, org_id=org_id)

def _run_tickets_report(db, filters, group_by, date_from, date_to, org_id=None):
    return _svc.run_tickets_report(db, filters, group_by, date_from, date_to, org_id=org_id)

def _run_expenses_report(db, filters, group_by, date_from, date_to, project_id, org_id=None):
    return _svc.run_expenses_report(db, filters, group_by, date_from, date_to, project_id, org_id=org_id)

def _run_capacity_report(db, filters, date_from, date_to, org_id=None):
    return _svc.run_capacity_report(db, filters, date_from, date_to, org_id=org_id)

def _run_system_report(db, report_id, filters, date_from, date_to):
    return _svc.run_system_report(db, report_id, filters, date_from, date_to)

def _next_invoice_number(db):
    return _svc.next_invoice_number(db)

def _invoice_out(inv):
    return _svc.invoice_out(inv)

def _business_minutes_between(start, end):
    return _svc.business_minutes_between(start, end)

def _workflow_out(w):
    return _svc.serialize_workflow(w)

def _sr_out(r):
    return _svc.serialize_scheduled_report(r)

IMPORT_TEMPLATES = _svc.IMPORT_TEMPLATES


# ═══════════════════════════════════════════════════════════════════════════════
# REPORT BUILDER
# ═══════════════════════════════════════════════════════════════════════════════

@router.get("/report-catalog/catalog", response_model=Dict[str, Any], summary="Catálogo de informes disponibles")
def report_catalog(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
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
    content = file.file.read()
    try:
        return _svc.validate_import_csv(entity_type, content)
    except ValueError as e:
        msg = str(e)
        if msg == "too_large":    raise HTTPException(413, "Fichero demasiado grande (máx 5 MB)")
        if msg == "not_utf8":     raise HTTPException(400, "El fichero debe ser UTF-8")
        if msg == "empty":        raise HTTPException(400, "El fichero está vacío")
        if msg == "invalid_type": raise HTTPException(400, "Tipo no válido")
        raise HTTPException(400, msg)


@router.post("/import/execute", response_model=ImportExecuteOut, summary="Ejecutar importación masiva")
def execute_import(
    entity_type: str,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    content = file.file.read()
    try:
        return _svc.execute_import_csv(entity_type, content, file.filename, current_user, db)
    except ValueError as e:
        msg = str(e)
        if msg == "too_large": raise HTTPException(413, "Fichero demasiado grande (máx 5 MB)")
        if msg == "not_utf8":  raise HTTPException(400, "El fichero debe ser UTF-8")
        raise HTTPException(400, msg)
    except RuntimeError:
        raise HTTPException(500, "Error al finalizar la importación")


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
    project = None
    if payload.project_id:
        project = db.query(Project).filter(Project.id == payload.project_id).first()

    client_name = payload.client_name or (project.client_name if project else None) or "Sin cliente"

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
    by_status: dict = {}
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
        "total_pending": round(sum(i.total or 0 for i in invoices if i.status in ["sent", "overdue"]), 2),
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
    now = datetime.now(timezone.utc)
    open_statuses = ["new", "assigned", "in_progress", "pending_client"]

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


@router.post("/itsm-metrics/pause-sla/{ticket_id}", response_model=SlaPauseResumeOut, summary="Pausar/reanudar SLA (pendiente cliente)")
def pause_resume_sla(
    ticket_id: str,
    payload: dict = Body(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    ticket = db.query(Ticket).filter(Ticket.id == ticket_id).first()
    if not ticket: raise HTTPException(404)

    action = payload.get("action", "pause")
    now = datetime.now(timezone.utc)

    if action == "pause" and not ticket.sla_paused_at:
        ticket.sla_paused_at = now
        ticket.sla_resolution_status = "paused"
        msg = "SLA pausado — esperando respuesta del cliente"
    elif action == "resume" and ticket.sla_paused_at:
        paused_minutes = _business_minutes_between(ticket.sla_paused_at, now)
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
    return {"ok": True, "message": msg, "sla_resolution_due": str(ticket.sla_resolution_due)[:16] if ticket.sla_resolution_due else None}


# ═══════════════════════════════════════════════════════════════════════════════
# AUTOMATION WORKFLOWS
# ═══════════════════════════════════════════════════════════════════════════════

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
    wf = db.query(AutomationWorkflow).options(
        joinedload(AutomationWorkflow.steps), joinedload(AutomationWorkflow.project)
    ).filter(AutomationWorkflow.id == wf.id).first()
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
    return _workflow_out(wf)


@router.delete("/automation-workflows/{wf_id}", response_model=OkResponse, summary="Eliminar workflow")
def delete_workflow(
    wf_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
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
# PROJECT TEMPLATES
# ═══════════════════════════════════════════════════════════════════════════════

@router.get("/templates", response_model=List[ProjectTemplateOut], summary="Listar plantillas de proyecto")
def list_templates(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
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
    try:
        return _svc.instantiate_template(template_id, payload, current_user, db)
    except ValueError:
        raise HTTPException(404, "Plantilla no encontrada")


# ═══════════════════════════════════════════════════════════════════════════════
# SMARTMATCH
# ═══════════════════════════════════════════════════════════════════════════════

@router.post("/smartmatch", response_model=SmartMatchOut, summary="SmartMatch — sugerir mejores recursos para una tarea/proyecto")
def smartmatch(
    payload: dict = Body(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    return _svc.smartmatch(payload, db)


# ── Scheduled Reports ──────────────────────────────────────────────────────────

@router.get("/scheduled-reports", response_model=List[ScheduledReportOut], summary="Listar informes programados")
def list_scheduled_reports(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    reports = db.query(ScheduledReport).order_by(ScheduledReport.created_at.desc()).all()
    return [_sr_out(r) for r in reports]


@router.post("/scheduled-reports", response_model=ScheduledReportCreateOut, status_code=201, summary="Crear informe programado")
def create_scheduled_report(
    payload: ScheduledReportCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    from app.services.scheduled_reports import _get_next_run
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
    db.add(r); db.commit(); db.refresh(r)
    return {"ok": True, "id": r.id}


@router.patch("/scheduled-reports/{report_id}", response_model=ScheduledReportOut, summary="Actualizar informe programado")
def update_scheduled_report(
    report_id: str,
    payload: dict = Body(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    r = db.query(ScheduledReport).filter(ScheduledReport.id == report_id).first()
    if not r: raise HTTPException(404, "Informe no encontrado")
    for k, v in payload.items():
        if k == "recipients": setattr(r, k, json.dumps(v))
        elif hasattr(r, k): setattr(r, k, v)
    db.commit()
    return _sr_out(r)


@router.delete("/scheduled-reports/{report_id}", response_model=OkResponse, summary="Eliminar informe programado")
def delete_scheduled_report(
    report_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
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
