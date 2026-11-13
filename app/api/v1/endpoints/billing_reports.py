"""
billing_reports — thin router delegating to app.services.billing_reports_service
"""
import logging
from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File, Body, Response
from sqlalchemy.orm import Session
from typing import Any, Dict, Optional

from app.core.abac_enforce import enforce_abac
from app.core.uploads import UploadProfile, read_and_validate_upload_sync
from app.db.session import get_db
from app.core.config import settings
from app.core.deps import get_current_user, require_any_manager, require_internal_user
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
from app.core.constantes import NOMBRE_COMPLETO_DEL_PRODUCTO
from app.core.constantes import MAX_TAMANO_DE_PAGINA


def _company_display_name(db) -> str:
    """El nombre de la PLATAFORMA: override en caliente → variable de entorno.

    Es el respaldo, no el nombre que debe encabezar el documento de un cliente:
    para eso está `_marca_del_documento`, que mira primero `OrgBranding`.
    """
    try:
        from app.services.settings_service import get_runtime_str
        return get_runtime_str(db, "PROJECT_NAME") or settings.PROJECT_NAME
    except Exception:
        logging.getLogger(__name__).debug("_company_display_name: excepcion ignorada", exc_info=True)
        return settings.PROJECT_NAME


def _marca_del_documento(db, current_user, *, base):
    """La marca con la que hay que dibujar un documento de este usuario.

    Auditoría 2026-08 (hallazgo 32). Antes los generadores no recibían ni el
    `organization_id`, así que un cliente configuraba su marca, la veía en la
    web, y **sus facturas salían con los colores y el nombre de Contecflow**.
    Decisión de producto: el documento lleva la marca del tenant.

    El nombre de la plataforma queda como respaldo para la organización que
    nunca la configuró y para el superadministrador, que no tiene una.
    """
    from app.services._pdf_marca import marca_de_organizacion

    return marca_de_organizacion(
        db, getattr(current_user, "organization_id", None),
        base=base, nombre_por_defecto=_company_display_name(db),
    )

from app.services.psa_flows import build_invoice_preview_from_timesheets_flow
from app.services import bookings_service as _bookings_svc
from app.schemas.billing_reports import (
    ReportSave,
    InvoiceCreate,
    InvoiceOut,
    WorkflowCreate,
    TemplateCreate,
    ScheduledReportCreate,
    InvoiceSummaryOut,
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
from app.core.responses import APIListResponse, APIResponse

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

@router.get("/report-catalog/catalog", response_model=APIResponse[Dict[str, Any]], summary="Catálogo de informes disponibles")
def report_catalog(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    return APIResponse.ok(data=build_report_catalog(db, current_user))


@router.get("/report-catalog/data-sources", response_model=APIResponse[Dict[str, Any]], summary="Fuentes de datos disponibles")
def report_data_sources(current_user: User = Depends(require_any_manager), db: Session = Depends(get_db)):
    return APIResponse.ok(data=get_data_sources(db, current_user.organization_id))


@router.post("/report-catalog/run", response_model=APIResponse[Dict[str, Any]], summary="Ejecutar un informe con filtros")
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
    return APIResponse.ok(data=dispatch_report(
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
    ))


@router.post("/report-catalog/save", response_model=APIResponse[ReportSaveOut], summary="Guardar informe personalizado")
def save_report(
    payload: ReportSave,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    return APIResponse.ok(data=_svc.save_report_definition(payload, current_user, db))


@router.delete("/report-catalog/{report_id}", response_model=APIResponse[OkResponse], summary="Eliminar informe guardado")
def delete_report(
    report_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    enforce_abac(db, current_user, "billing_report_definition", report_id, action="delete")
    return APIResponse.ok(data=_svc.delete_report_definition(report_id, current_user.id, db))


# ═══════════════════════════════════════════════════════════════════════════════
# BULK IMPORT
# ═══════════════════════════════════════════════════════════════════════════════

@router.get("/import/template/{entity_type}", response_model=APIResponse[ImportTemplateOut], summary="Plantilla CSV para importación")
def get_import_template(
    entity_type: str,
    current_user: User = Depends(require_any_manager),
):
    if entity_type not in IMPORT_TEMPLATES:
        raise HTTPException(400, f"Tipo no válido. Opciones: {list(IMPORT_TEMPLATES.keys())}")
    tpl = IMPORT_TEMPLATES[entity_type]
    return APIResponse.ok(data={
        "entity_type": entity_type,
        "columns": tpl["columns"],
        "example": tpl["example"],
        "instructions": "Descarga esta plantilla, rellena los datos y sube el fichero CSV en el importador. La primera fila debe ser la cabecera.",
    })


@router.post("/import/validate", response_model=APIResponse[ImportValidateOut], summary="Validar CSV antes de importar")
def validate_import(
    entity_type: str,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    # Auditoría 2026-08 (P1-8): tope y validación de tipo centralizados. Antes
    # se leía el fichero completo sin límite y el corte de 5 MB llegaba dentro
    # del servicio, ya con todo en memoria.
    content = read_and_validate_upload_sync(file, UploadProfile.CSV_IMPORT)
    try:
        return APIResponse.ok(data=_svc.validate_import_csv(entity_type, content))
    except ValueError as e:
        msg = str(e)
        if msg == "too_large":    raise HTTPException(413, "Fichero demasiado grande (máx 5 MB)")
        if msg == "not_utf8":     raise HTTPException(400, "El fichero debe ser UTF-8")
        if msg == "empty":        raise HTTPException(400, "El fichero está vacío")
        if msg == "invalid_type": raise HTTPException(400, "Tipo no válido")
        raise HTTPException(400, msg)


@router.post("/import/execute", response_model=APIResponse[ImportExecuteOut], summary="Ejecutar importación masiva")
def execute_import(
    entity_type: str,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    # Auditoría 2026-08 (P1-8): tope y validación de tipo centralizados. Antes
    # se leía el fichero completo sin límite y el corte de 5 MB llegaba dentro
    # del servicio, ya con todo en memoria.
    content = read_and_validate_upload_sync(file, UploadProfile.CSV_IMPORT)
    try:
        return APIResponse.ok(data=_svc.execute_import_csv(entity_type, content, file.filename, current_user, db))
    except ValueError as e:
        msg = str(e)
        if msg == "too_large": raise HTTPException(413, "Fichero demasiado grande (máx 5 MB)")
        if msg == "not_utf8":  raise HTTPException(400, "El fichero debe ser UTF-8")
        raise HTTPException(400, msg)
    except RuntimeError:
        raise HTTPException(500, "Error al finalizar la importación")


@router.get("/import/jobs", response_model=APIListResponse[ImportJobHistoryOut], summary="Historial de importaciones")
def import_jobs(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=MAX_TAMANO_DE_PAGINA),
    response: Response = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    items = get_import_jobs(db, page, page_size, response)
    return APIListResponse.ok(items=items, total=len(items), page=page, page_size=page_size)


# ═══════════════════════════════════════════════════════════════════════════════
# INVOICING
# ═══════════════════════════════════════════════════════════════════════════════


@router.get("/invoices", response_model=APIListResponse[InvoiceOut], summary="Listar facturas")
def list_invoices(
    project_id: Optional[str] = None,
    status: Optional[str] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=MAX_TAMANO_DE_PAGINA),
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
    items = [invoice_out(inv) for inv in invoices]
    return APIListResponse.ok(items=items, total=total, page=page, page_size=page_size)


@router.post("/invoices/from-timesheets", response_model=APIResponse[Dict[str, Any]], summary="Generar factura desde timesheets aprobados")
def invoice_from_timesheets(
    payload: dict = Body(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    return APIResponse.ok(data=build_invoice_preview_from_timesheets_flow(
        db=db,
        project_id=payload.get("project_id"),
        date_from=payload.get("date_from"),
        date_to=payload.get("date_to"),
        tax_rate=payload.get("tax_rate"),
    ))


@router.post("/invoices", response_model=APIResponse[InvoiceOut], status_code=201, summary="Crear factura")
def create_invoice(
    payload: InvoiceCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    return APIResponse.ok(data=_svc.create_invoice(payload, current_user, db))


@router.patch("/invoices/{invoice_id}/status", response_model=APIResponse[InvoiceOut], summary="Cambiar estado de factura")
def update_invoice_status(
    invoice_id: str,
    payload: dict = Body(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    return APIResponse.ok(data=_svc.update_invoice_status(invoice_id, payload, current_user, db))


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
    from app.services import invoice_pdf as _invoice_pdf
    from app.services._pdf_marca import PALETA_DE_FACTURA

    inv, lines = _svc.get_invoice_for_pdf(invoice_id, db)
    marca = _marca_del_documento(db, current_user, base=PALETA_DE_FACTURA)

    pdf_bytes = _invoice_pdf.pdf_de_factura(
        db, inv, lines, org_id=current_user.organization_id,
        company_name=marca.nombre, paleta=marca.paleta, generated_by=NOMBRE_COMPLETO_DEL_PRODUCTO,
    )

    filename = f"factura_{inv.number.replace('/', '-')}.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/invoices/summary", response_model=APIResponse[InvoiceSummaryOut], summary="Resumen financiero de facturas")
def invoice_summary(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    return APIResponse.ok(data=_svc.get_invoice_summary(db))


# ═══════════════════════════════════════════════════════════════════════════════
# ITSM ADVANCED METRICS
# ═══════════════════════════════════════════════════════════════════════════════

@router.get("/itsm-metrics/sla-dashboard", response_model=APIResponse[SlaDashboardOut], summary="Dashboard SLA en tiempo real")
def sla_dashboard(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return APIResponse.ok(data=_svc.get_sla_dashboard(db))


@router.get("/itsm-metrics/agent-performance", response_model=APIListResponse[AgentPerformanceOut], summary="Rendimiento por agente")
def agent_performance(
    days: int = Query(30),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    items = _svc.get_agent_performance(days, db)
    return APIListResponse.ok(items=items, total=len(items))


@router.post("/itsm-metrics/pause-sla/{ticket_id}", response_model=APIResponse[SlaPauseResumeOut], summary="Pausar/reanudar SLA (pendiente cliente)")
def pause_resume_sla(
    ticket_id: str,
    payload: dict = Body(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _rol: User = Depends(require_internal_user),  # auditoria 2026-09: excepcion revisada: gestion del SLA por el agente
):
    return APIResponse.ok(data=_svc.pause_resume_sla(ticket_id, payload, db))


# ═══════════════════════════════════════════════════════════════════════════════
# AUTOMATION WORKFLOWS
# ═══════════════════════════════════════════════════════════════════════════════

@router.get("/automation-workflows", response_model=APIListResponse[AutomationWorkflowOut], summary="Listar workflows multi-paso")
def list_workflows(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    items = _svc.list_workflows_all(db)
    return APIListResponse.ok(items=items, total=len(items))


@router.post("/automation-workflows", response_model=APIResponse[AutomationWorkflowOut], status_code=201, summary="Crear workflow")
def create_workflow(
    payload: WorkflowCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    return APIResponse.ok(data=_svc.create_workflow(payload, current_user, db))


@router.patch("/automation-workflows/{wf_id}", response_model=APIResponse[AutomationWorkflowOut], summary="Actualizar workflow")
def update_workflow(
    wf_id: str, payload: dict = Body(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    return APIResponse.ok(data=_svc.update_workflow(wf_id, payload, db))


@router.delete("/automation-workflows/{wf_id}", response_model=APIResponse[OkResponse], summary="Eliminar workflow")
def delete_workflow(
    wf_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    enforce_abac(db, current_user, "billing_automation_workflow", wf_id, action="delete")
    return APIResponse.ok(data=_svc.delete_workflow(wf_id, db))


@router.get("/automation-workflows/{wf_id}/executions", response_model=APIListResponse[WorkflowExecutionOut], summary="Historial de ejecuciones")
def workflow_executions(
    wf_id: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=MAX_TAMANO_DE_PAGINA),
    response: Response = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    items = get_workflow_executions(db, wf_id, page, page_size, response)
    return APIListResponse.ok(items=items, total=len(items), page=page, page_size=page_size)


@router.post("/automation-workflows/{wf_id}/run", response_model=APIResponse[Dict[str, Any]], summary="Ejecutar workflow ahora")
def run_workflow_now(
    wf_id: str,
    payload: dict = Body(default={}),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    context = payload.get("context") or {}
    return APIResponse.ok(data=_bookings_svc.execute_workflow_now_record(wf_id, context, current_user.id, db))


@router.patch("/automation-workflows/{wf_id}/steps/{step_id}/retries", response_model=APIResponse[Dict[str, Any]], summary="Configurar reintentos por step")
def update_workflow_step_retries(
    wf_id: str,
    step_id: str,
    payload: dict = Body(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    return APIResponse.ok(data=_bookings_svc.configurar_reintentos_de_paso(
        db, current_user, wf_id, step_id, payload))


# ═══════════════════════════════════════════════════════════════════════════════
# PROJECT TEMPLATES
# ═══════════════════════════════════════════════════════════════════════════════

@router.get("/templates", response_model=APIListResponse[ProjectTemplateOut], summary="Listar plantillas de proyecto")
def list_templates(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    items = _svc.list_templates_all(db)
    return APIListResponse.ok(items=items, total=len(items))


@router.post("/templates", response_model=APIResponse[TemplateCreateOut], status_code=201, summary="Crear plantilla de proyecto")
def create_template(
    payload: TemplateCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    return APIResponse.ok(data=_svc.create_template(payload, current_user, db))


@router.post("/templates/{template_id}/instantiate", response_model=APIResponse[TemplateInstantiateOut], summary="Crear proyecto desde plantilla")
def instantiate_template(
    template_id: str,
    payload: dict = Body(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    try:
        return APIResponse.ok(data=_svc.instantiate_template(template_id, payload, current_user, db))
    except ValueError:
        raise HTTPException(404, "Plantilla no encontrada")


# ═══════════════════════════════════════════════════════════════════════════════
# SMARTMATCH
# ═══════════════════════════════════════════════════════════════════════════════

@router.post("/smartmatch", response_model=APIResponse[SmartMatchOut], summary="SmartMatch — sugerir mejores recursos para una tarea/proyecto")
def smartmatch(
    payload: dict = Body(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    return APIResponse.ok(data=_svc.smartmatch(payload, db))


# ── Scheduled Reports ──────────────────────────────────────────────────────────

@router.get("/scheduled-reports", response_model=APIListResponse[ScheduledReportOut], summary="Listar informes programados")
def list_scheduled_reports(
    db: Session = Depends(get_db),
    # Auditoria 2026-11: los mismos roles que crean (antes cualquiera veia los
    # informes de su organizacion y sus destinatarios).
    current_user: User = Depends(require_any_manager),
):
    items = _svc.list_scheduled_reports(db)
    return APIListResponse.ok(items=items, total=len(items))


@router.post("/scheduled-reports", response_model=APIResponse[ScheduledReportCreateOut], status_code=201, summary="Crear informe programado")
def create_scheduled_report(
    payload: ScheduledReportCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    return APIResponse.ok(data=_svc.create_scheduled_report(payload, current_user, db))


@router.patch("/scheduled-reports/{report_id}", response_model=APIResponse[ScheduledReportOut], summary="Actualizar informe programado")
def update_scheduled_report(
    report_id: str,
    payload: dict = Body(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    enforce_abac(db, current_user, "scheduled_report", report_id, action="update")
    return APIResponse.ok(data=_svc.update_scheduled_report(report_id, payload, db))


@router.delete("/scheduled-reports/{report_id}", response_model=APIResponse[OkResponse], summary="Eliminar informe programado")
def delete_scheduled_report(
    report_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    enforce_abac(db, current_user, "scheduled_report", report_id, action="delete")
    return APIResponse.ok(data=_svc.delete_scheduled_report(report_id, db))


@router.post("/scheduled-reports/{report_id}/run", response_model=APIResponse[ScheduledReportRunOut], summary="Ejecutar informe ahora")
def run_scheduled_report(
    report_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    # Segunda auditoria 2026-11 (n.º 20): generar el PDF y mandarlo por SMTP
    # va al worker. Con cola: 202 `{status: "queued", recipients}`; el resultado
    # queda en `last_status`/`last_error` del informe. Sin cola, como siempre.
    from app.core.segundo_plano import EN_COLA, encolar, respuesta_en_cola
    from app.services.scheduled_reports import destinatarios_del_informe, execute_report_now
    destinatarios = destinatarios_del_informe(report_id, db)
    if destinatarios is None:
        raise HTTPException(404, "Informe no encontrado")
    result = encolar(execute_report_now, report_id, _sesion=db)
    if result is EN_COLA:
        return respuesta_en_cola(report_id=report_id, recipients=destinatarios)
    if not result["ok"]:
        err = result.get("error", "Error al ejecutar")
        # "Informe no encontrado" → 404; cualquier otro fallo de ejecución → 500
        if "no encontrado" in err.lower() or "not found" in err.lower():
            raise HTTPException(404, err)
        raise HTTPException(500, err)
    return APIResponse.ok(data=result)


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
    # Revisión 2026-11: pintaba filas de ejemplo; ahora es el PDF que se envía.
    from fastapi.responses import Response
    from app.services.report_pdf_service import build_report_pdf

    r = _svc.get_scheduled_report_by_id(report_id, db)
    if r is None:
        raise HTTPException(404, "Informe no encontrado")
    try:
        pdf_bytes = build_report_pdf(r, db, org_id=current_user.organization_id)
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="preview_{r.id}.pdf"'}
    )
