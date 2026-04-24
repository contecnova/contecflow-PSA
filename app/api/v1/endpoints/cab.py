"""
cab — all P2 pending features:
  cab              — Change Advisory Board flow + maintenance windows
  webhooks         — Incoming webhook triggers
  email            — SMTP email templates + send actions
  gdpr             — GDPR right to erasure + data portability
  search           — Global full-text search (Cmd+K)
  dashboard-widgets— Per-user dashboard personalisation
  onboarding       — Onboarding wizard state
  integrations     — GitHub/GitLab/Jira/Calendar/QuickBooks connectors
  revenue          — ASC 606/IFRS 15 revenue recognition
  risk-scores      — Project risk prediction engine
"""
from fastapi import APIRouter, Depends, HTTPException, Query, Request, BackgroundTasks, Body
from sqlalchemy.orm import Session
from typing import Optional, List
from datetime import date, datetime
from pydantic import BaseModel
import json
import logging

logger = logging.getLogger("clarive.v14")

from app.db.session import get_db
from app.core.deps import get_current_user, require_any_manager, require_admin
from app.models.user import User
from app.models.cab import (
    WebhookTrigger,
)

router = APIRouter()
import app.services.cab_service as _svc


# ═══════════════════════════════════════════════════════════════════════════════
# CHANGE ADVISORY BOARD (CAB)
# ═══════════════════════════════════════════════════════════════════════════════

@router.get("/cab/changes", summary="CRs pendientes de revisión CAB")
def cab_pending_changes(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    """All change requests that need CAB review."""
    return _svc.get_cab_pending_changes(db, current_user.id)


class CABVoteCreate(BaseModel):
    vote: str  # approve | reject | abstain
    comment: Optional[str] = None


@router.post("/cab/changes/{cr_id}/vote", summary="Votar en CAB sobre una CR")
def cast_cab_vote(
    cr_id: str,
    payload: CABVoteCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    try:
        return _svc.cast_cab_vote(cr_id, payload.vote, payload.comment, current_user, db)
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.post("/cab/changes/{cr_id}/close", summary="Cerrar votación CAB — aprobar o rechazar")
def close_cab_vote(
    cr_id: str,
    payload: dict = Body(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    try:
        return _svc.close_cab_vote(cr_id, payload.get("decision"), payload.get("reason"), current_user, db)
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.get("/cab/windows", summary="Ventanas de mantenimiento")
def list_maintenance_windows(
    upcoming_only: bool = Query(False),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return _svc.list_maintenance_windows(upcoming_only, db)


class WindowCreate(BaseModel):
    name: str
    description: Optional[str] = None
    start_dt: datetime
    end_dt: datetime
    environment: str = "production"
    is_recurring: bool = False
    recurrence: Optional[str] = None


@router.post("/cab/windows", summary="Crear ventana de mantenimiento")
def create_maintenance_window(
    payload: WindowCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    return _svc.create_maintenance_window(payload, current_user.id, db)


@router.post("/cab/changes/{cr_id}/schedule", summary="Asignar CR a ventana de mantenimiento")
def schedule_cr_in_window(
    cr_id: str,
    payload: dict = Body(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    window_id = payload.get("window_id")
    if not window_id:
        raise HTTPException(422, "window_id es obligatorio")
    try:
        return _svc.schedule_cr_in_window(cr_id, window_id, payload.get("rollback_plan"), payload.get("test_plan"), db)
    except ValueError as e:
        raise HTTPException(404, str(e))


# ═══════════════════════════════════════════════════════════════════════════════
# INCOMING WEBHOOK TRIGGERS
# ═══════════════════════════════════════════════════════════════════════════════

class WebhookTriggerCreate(BaseModel):
    name: str
    slug: str
    secret: Optional[str] = None
    workflow_id: Optional[str] = None
    rule_id: Optional[str] = None
    field_mapping: Optional[dict] = None


def _trigger_out(t: WebhookTrigger) -> dict:
    return _svc.trigger_out(t)


@router.get("/webhooks", summary="Listar webhook triggers configurados")
def list_webhook_triggers(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    return _svc.list_webhook_triggers(db)


@router.post("/webhooks", summary="Crear webhook trigger")
def create_webhook_trigger(
    payload: WebhookTriggerCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    try:
        return _svc.create_webhook_trigger(payload, current_user.id, db)
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.post("/webhooks/fire/{slug}", summary="Disparar webhook — endpoint público")
async def fire_webhook(
    slug: str,
    request: Request,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    """
    External systems POST here to trigger automations.
    Verifiable via X-Clarive-Signature HMAC header.
    """
    trigger = _svc.get_active_webhook_trigger_by_slug(db, slug)
    # Read body
    body = await request.body()
    payload_str = body.decode("utf-8") if body else "{}"
    try:
        payload_json = json.loads(payload_str)
    except Exception:
        payload_json = {}

    # Verify HMAC signature — all triggers must be signed
    import hmac as _hmac
    import hashlib as _hashlib
    signature_header = request.headers.get("X-Clarive-Signature")
    if not trigger.secret:
        # Trigger without a secret must not be callable — reject silently to avoid enumeration
        raise HTTPException(401, "Webhook trigger no autorizado")
    if not signature_header:
        raise HTTPException(401, "Se requiere cabecera X-Clarive-Signature")
    expected = "sha256=" + _hmac.new(
        trigger.secret.encode(), body, _hashlib.sha256
    ).hexdigest()
    if not _hmac.compare_digest(signature_header, expected):
        raise HTTPException(401, "Firma HMAC inválida")

    # Log the call and update fire stats
    _svc.log_webhook_fire(trigger, payload_str, json.dumps(dict(request.headers)), db)

    # Fire the workflow/rule in background
    if trigger.workflow_id:
        background_tasks.add_task(_execute_workflow_from_webhook, trigger.workflow_id, payload_json)

    return {"ok": True, "fired": True, "trigger": trigger.name}


def _execute_workflow_from_webhook(workflow_id: str, context: dict):
    return _svc.execute_workflow_from_webhook(workflow_id, context)


@router.get("/webhooks/{trigger_id}/logs", summary="Historial de llamadas al webhook")
def webhook_logs(
    trigger_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    return _svc.get_webhook_logs(trigger_id, db)


@router.post("/webhooks/{trigger_id}/rotate", summary="Rotar slug del webhook trigger")
def rotate_webhook_trigger_slug(
    trigger_id: str,
    expires_in_days: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Regenerates the slug immediately, invalidating the previous URL.

    Query param `expires_in_days`: if provided, the new slug will expire after
    that many days. Omit for a non-expiring slug.
    """
    try:
        return _svc.rotate_webhook_trigger_slug(trigger_id, expires_in_days, db)
    except ValueError as e:
        raise HTTPException(404, str(e))


@router.delete("/webhooks/{trigger_id}", summary="Eliminar webhook trigger")
def delete_webhook_trigger(
    trigger_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    try:
        return _svc.delete_webhook_trigger(trigger_id, db)
    except ValueError as e:
        raise HTTPException(404, str(e))


# ═══════════════════════════════════════════════════════════════════════════════
# EMAIL — SMTP TEMPLATES + SEND
# ═══════════════════════════════════════════════════════════════════════════════

SYSTEM_EMAIL_TEMPLATES = _svc.SYSTEM_EMAIL_TEMPLATES


@router.get("/email/templates", summary="Listar plantillas de email")
def list_email_templates(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    return _svc.list_email_templates(db)


class EmailTemplateCreate(BaseModel):
    name: str
    subject: str
    body_html: str
    body_text: Optional[str] = None
    category: str = "automation"
    variables: Optional[List[str]] = None


@router.post("/email/templates", summary="Crear plantilla de email")
def create_email_template(
    payload: EmailTemplateCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    return _svc.create_email_template(payload, current_user.id, db)


class SendEmailPayload(BaseModel):
    to: List[str]
    cc: Optional[List[str]] = None
    template_id: Optional[str] = None
    subject: Optional[str] = None
    body_html: Optional[str] = None
    variables: Optional[dict] = None
    source: str = "manual"
    source_id: Optional[str] = None


@router.post("/email/send", summary="Enviar email (con plantilla o ad-hoc)")
def send_email(
    payload: SendEmailPayload,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    return _svc.send_email_action(payload, db)


@router.get("/email/logs", summary="Historial de emails enviados")
def email_logs(
    limit: int = Query(50, le=200),
    status: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    return _svc.get_email_logs(limit, status, db)


# ═══════════════════════════════════════════════════════════════════════════════
# GDPR
# ═══════════════════════════════════════════════════════════════════════════════

@router.get("/gdpr/requests", summary="Listar solicitudes GDPR")
def list_gdpr_requests(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    return _svc.list_gdpr_requests(db)


class GDPRRequestCreate(BaseModel):
    request_type: str  # erasure | portability | access | rectification
    subject_user_id: Optional[str] = None
    subject_email: Optional[str] = None
    notes: Optional[str] = None


@router.post("/gdpr/requests", summary="Crear solicitud GDPR")
def create_gdpr_request(
    payload: GDPRRequestCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    return _svc.create_gdpr_request(payload, current_user, db)


@router.post("/gdpr/requests/{request_id}/process", summary="Procesar solicitud GDPR")
def process_gdpr_request(
    request_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Execute the GDPR request: anonymise data or generate export."""
    try:
        return _svc.process_gdpr_request(request_id, current_user, db)
    except ValueError as e:
        raise HTTPException(400, str(e))


# ═══════════════════════════════════════════════════════════════════════════════
# GLOBAL SEARCH (Cmd+K)
# ═══════════════════════════════════════════════════════════════════════════════

@router.get("/global-search", summary="Búsqueda global full-text")
def global_search(
    q: str = Query(..., min_length=1),
    types: Optional[str] = Query(None),
    limit: int = Query(30, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Full-text search across projects, tasks, tickets, users, invoices, opportunities."""
    return _svc.global_search(q, types, limit, db)


# ═══════════════════════════════════════════════════════════════════════════════
# DASHBOARD WIDGETS (personalisation)
# ═══════════════════════════════════════════════════════════════════════════════

AVAILABLE_WIDGETS = _svc.AVAILABLE_WIDGETS


@router.get("/dashboard-widgets/catalog", summary="Catálogo de widgets disponibles")
def widget_catalog(current_user: User = Depends(get_current_user)):
    return AVAILABLE_WIDGETS


@router.get("/dashboard-widgets", summary="Widgets del usuario actual")
def get_user_widgets(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return _svc.get_user_widgets(current_user, db)


@router.post("/dashboard-widgets", summary="Guardar layout de widgets del usuario")
def save_widget_layout(
    payload: list,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return _svc.save_widget_layout(payload, current_user.id, db)


@router.delete("/dashboard-widgets/reset", summary="Restablecer widgets por defecto")
def reset_widgets(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return _svc.reset_widgets(current_user.id, db)


# ═══════════════════════════════════════════════════════════════════════════════
# ONBOARDING WIZARD
# ═══════════════════════════════════════════════════════════════════════════════

ONBOARDING_STEPS = [
    {"id": "create_project",   "title": "Crea tu primer proyecto",      "description": "Configura el nombre, cliente y fechas de tu primer proyecto.",      "action": "/projects", "icon": "⬡"},
    {"id": "invite_team",      "title": "Invita a tu equipo",           "description": "Añade los miembros del equipo que van a trabajar en el proyecto.",   "action": "/settings", "icon": "👥"},
    {"id": "configure_sla",    "title": "Configura el SLA",             "description": "Define el horario laboral y los festivos para el cálculo de SLAs.",  "action": "/settings", "icon": "🎯"},
    {"id": "create_sprint",    "title": "Lanza tu primer sprint",       "description": "Crea un sprint con tareas y fija las fechas de inicio y fin.",       "action": "/sprints",  "icon": "⚡"},
    {"id": "first_timesheet",  "title": "Imputa tus primeras horas",    "description": "Registra las horas trabajadas hoy en el proyecto que acabas de crear.", "action": "/imputar", "icon": "⏱"},
]


@router.get("/onboarding", summary="Estado del onboarding del usuario")
def get_onboarding(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return _svc.get_onboarding(current_user, db)


@router.post("/onboarding/complete-step", summary="Marcar paso de onboarding como completado")
def complete_onboarding_step(
    payload: dict = Body(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        return _svc.complete_onboarding_step(payload.get("step_id"), current_user, db)
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.post("/onboarding/dismiss", summary="Cerrar onboarding wizard")
def dismiss_onboarding(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return _svc.dismiss_onboarding(current_user, db)


# ═══════════════════════════════════════════════════════════════════════════════
# EXTERNAL INTEGRATIONS (GitHub, Calendar, QuickBooks)
# ═══════════════════════════════════════════════════════════════════════════════

@router.get("/oauth-integrations", summary="Listar integraciones configuradas")
def list_integrations(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    return _svc.list_integrations(db)


class IntegrationCreate(BaseModel):
    integration_type: str
    name: str
    access_token: Optional[str] = None
    refresh_token: Optional[str] = None
    config: Optional[dict] = None


@router.post("/oauth-integrations", summary="Crear/configurar integración")
def create_integration(
    payload: IntegrationCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    return _svc.create_integration(payload, current_user.id, db)


@router.post("/oauth-integrations/{integration_id}/sync", summary="Sincronizar integración")
def sync_integration(
    integration_id: str,
    payload: dict = Body(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    try:
        return _svc.run_integration_sync(integration_id, payload, db)
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.get("/oauth-integrations/calendar/events", summary="Eventos de calendario sincronizados")
def calendar_events(
    user_id: Optional[str] = None,
    from_date: Optional[date] = None,
    to_date: Optional[date] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return _svc.get_calendar_events(user_id or current_user.id, from_date, to_date, db)


# ═══════════════════════════════════════════════════════════════════════════════
# REVENUE RECOGNITION (ASC 606 / IFRS 15)
# ═══════════════════════════════════════════════════════════════════════════════

@router.get("/oauth-integrations/{integration_id}/commits", summary="Commits vinculados a tareas")
def get_commit_links(
    integration_id: str,
    task_id: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return _svc.get_commit_links(integration_id, task_id, db)


@router.get("/revenue/rules", summary="Reglas de reconocimiento de ingresos")
def list_revenue_rules(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    return _svc.list_revenue_rules(db)


class RevenueRuleCreate(BaseModel):
    project_id: str
    method: str = "percentage_complete"
    contract_value: Optional[float] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    notes: Optional[str] = None


@router.post("/revenue/rules", summary="Crear regla de reconocimiento")
def create_revenue_rule(
    payload: RevenueRuleCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    try:
        return _svc.create_revenue_rule(payload, current_user.id, db)
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.post("/revenue/rules/{rule_id}/compute", summary="Calcular reconocimiento del período")
def compute_revenue_period(
    rule_id: str,
    payload: dict = Body(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    """Compute and record revenue recognition for a given month."""
    period_str = payload.get("period", str(date.today().replace(day=1)))
    try:
        return _svc.compute_revenue_period(rule_id, period_str, db)
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.post("/revenue/auto-compute", summary="Computar Rev Rec automáticamente para todos los proyectos activos")
def auto_compute_revenue(
    period: Optional[str] = Body(None, embed=True),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    period_str = period or str(date.today().replace(day=1))
    return _svc.auto_compute_revenue(period_str, db)


@router.get("/revenue/summary", summary="Resumen de ingresos reconocidos")
def revenue_summary(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    return _svc.get_revenue_summary(db)


# ═══════════════════════════════════════════════════════════════════════════════
# PROJECT RISK SCORE (predictive engine)
# ═══════════════════════════════════════════════════════════════════════════════

@router.get("/risk-scores", summary="Puntuaciones de riesgo de todos los proyectos activos")
def get_risk_scores(
    refresh: bool = Query(False),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    return _svc.get_risk_scores(refresh, db)


@router.get("/risk-scores/{project_id}", summary="Puntuación de riesgo detallada de un proyecto")
def get_project_risk_score(
    project_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    try:
        return _svc.get_project_risk_score(project_id, db)
    except ValueError as e:
        raise HTTPException(404, str(e))


# ── Revenue Journal Entries (ASC 606 / IFRS 15 double-entry accounting) ───────

@router.get("/revenue/journal/{project_id}", summary="Asientos contables de reconocimiento de ingresos (ASC 606 / IFRS 15)")
def revenue_journal_entries(
    project_id: str,
    db:              Session = Depends(get_db),
    _: User = Depends(require_any_manager),
):
    try:
        return _svc.get_revenue_journal(project_id, db)
    except ValueError as e:
        raise HTTPException(404, str(e))


@router.get("/revenue/journal/{project_id}/export", summary="Exportar asientos contables en CSV")
def export_revenue_journal(
    project_id: str,
    db:         Session = Depends(get_db),
    _:          User = Depends(require_any_manager),
):
    """Returns journal entries as CSV string for ERP import."""
    import csv, io
    try:
        data = _svc.get_revenue_journal(project_id, db)
    except ValueError as e:
        raise HTTPException(404, str(e))
    lines = data["journal_lines"]
    if not lines:
        return {"csv": "", "message": "Sin asientos que exportar"}

    buf = io.StringIO()
    fields = ["date", "period", "journal_ref", "line", "account_code", "account_name",
              "description", "debit", "credit", "currency", "method", "pct_complete"]
    writer = csv.DictWriter(buf, fieldnames=fields, extrasaction="ignore")
    writer.writeheader()
    writer.writerows(lines)
    return {"csv": buf.getvalue(), "row_count": len(lines)}
