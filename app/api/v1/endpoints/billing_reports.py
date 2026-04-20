"""
billing_reports — thin router delegating to app.services.billing_reports_service
"""
from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File, Body, Response
from sqlalchemy.orm import Session
from typing import Any, Dict, Optional, List

from app.db.session import get_db
from app.core.config import settings
from app.core.deps import get_current_user, require_any_manager
from app.models.user import User
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
from app.schemas.billing_reports import (
    ReportSave,
    InvoiceCreate,
    InvoiceOut,
    WorkflowCreate,
    TemplateCreate,
    ScheduledReportCreate,
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

# Local aliases — pass `db` into lambdas used by dispatch_report runners
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
    return _svc.save_report_definition(payload, current_user, db)


@router.delete("/report-catalog/{report_id}", response_model=OkResponse, summary="Eliminar informe guardado")
def delete_report(
    report_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    return _svc.delete_report_definition(report_id, current_user.id, db)


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
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    response: Response = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    q, total = _svc.query_invoices(db, project_id, status)
    invoices = q.offset((page - 1) * page_size).limit(page_size).all()
    if response is not None:
        response.headers["X-Total-Count"] = str(total)
        response.headers["X-Page"] = str(page)
        response.headers["X-Page-Size"] = str(page_size)
    from app.services.billing_reports_service import invoice_out
    return [invoice_out(inv) for inv in invoices]


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
    return _svc.create_invoice(payload, current_user, db)


@router.patch("/invoices/{invoice_id}/status", response_model=InvoiceOut, summary="Cambiar estado de factura")
def update_invoice_status(
    invoice_id: str,
    payload: dict = Body(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    return _svc.update_invoice_status(invoice_id, payload, current_user, db)


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

    inv, lines = _svc.get_invoice_for_pdf(invoice_id, db)

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
    return _svc.get_invoice_summary(db)


# ═══════════════════════════════════════════════════════════════════════════════
# ITSM ADVANCED METRICS
# ═══════════════════════════════════════════════════════════════════════════════

@router.get("/itsm-metrics/sla-dashboard", response_model=SlaDashboardOut, summary="Dashboard SLA en tiempo real")
def sla_dashboard(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return _svc.get_sla_dashboard(db)


@router.get("/itsm-metrics/agent-performance", response_model=List[AgentPerformanceOut], summary="Rendimiento por agente")
def agent_performance(
    days: int = Query(30),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    return _svc.get_agent_performance(days, db)


@router.post("/itsm-metrics/pause-sla/{ticket_id}", response_model=SlaPauseResumeOut, summary="Pausar/reanudar SLA (pendiente cliente)")
def pause_resume_sla(
    ticket_id: str,
    payload: dict = Body(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return _svc.pause_resume_sla(ticket_id, payload, db)


# ═══════════════════════════════════════════════════════════════════════════════
# AUTOMATION WORKFLOWS
# ═══════════════════════════════════════════════════════════════════════════════

@router.get("/automation-workflows", response_model=List[AutomationWorkflowOut], summary="Listar workflows multi-paso")
def list_workflows(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    return _svc.list_workflows_all(db)


@router.post("/automation-workflows", response_model=AutomationWorkflowOut, status_code=201, summary="Crear workflow")
def create_workflow(
    payload: WorkflowCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    return _svc.create_workflow(payload, current_user, db)


@router.patch("/automation-workflows/{wf_id}", response_model=AutomationWorkflowOut, summary="Actualizar workflow")
def update_workflow(
    wf_id: str, payload: dict = Body(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    return _svc.update_workflow(wf_id, payload, db)


@router.delete("/automation-workflows/{wf_id}", response_model=OkResponse, summary="Eliminar workflow")
def delete_workflow(
    wf_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    return _svc.delete_workflow(wf_id, db)


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
    return _svc.list_templates_all(db)


@router.post("/templates", response_model=TemplateCreateOut, status_code=201, summary="Crear plantilla de proyecto")
def create_template(
    payload: TemplateCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    return _svc.create_template(payload, current_user, db)


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
    return _svc.list_scheduled_reports(db)


@router.post("/scheduled-reports", response_model=ScheduledReportCreateOut, status_code=201, summary="Crear informe programado")
def create_scheduled_report(
    payload: ScheduledReportCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    return _svc.create_scheduled_report(payload, current_user, db)


@router.patch("/scheduled-reports/{report_id}", response_model=ScheduledReportOut, summary="Actualizar informe programado")
def update_scheduled_report(
    report_id: str,
    payload: dict = Body(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    return _svc.update_scheduled_report(report_id, payload, db)


@router.delete("/scheduled-reports/{report_id}", response_model=OkResponse, summary="Eliminar informe programado")
def delete_scheduled_report(
    report_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    return _svc.delete_scheduled_report(report_id, db)


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

    r = _svc.get_scheduled_report_by_id(report_id, db)

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
