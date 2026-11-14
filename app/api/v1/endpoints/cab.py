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
from app.core import timeutil
from app.core.constantes import MAX_TAMANO_DE_PAGINA

logger = logging.getLogger("contecflow.v14")

from app.db.session import get_db
from app.core.deps import get_current_user, require_admin, require_any_manager
from app.core.ratelimit import limiter
from app.core.responses import APIListResponse, APIResponse
from app.models.user import User
from app.core.abac_enforce import enforce_abac

router = APIRouter()
import app.services.cab_service as _svc


# ═══════════════════════════════════════════════════════════════════════════════
# CHANGE ADVISORY BOARD (CAB)
# ═══════════════════════════════════════════════════════════════════════════════

@router.get("/cab/changes", response_model=APIListResponse[dict], summary="CRs pendientes de revisión CAB")
def cab_pending_changes(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=MAX_TAMANO_DE_PAGINA),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    """All change requests that need CAB review."""
    items = _svc.get_cab_pending_changes(db, current_user.id)
    return APIListResponse.ok(items=items, page=page, page_size=page_size)


class CABVoteCreate(BaseModel):
    vote: str  # approve | reject | abstain
    comment: Optional[str] = None


@router.post("/cab/changes/{cr_id}/vote", summary="Votar en CAB sobre una CR")
@limiter.limit("20/minute")
def cast_cab_vote(
    cr_id: str,
    payload: CABVoteCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    try:
        return APIResponse.ok(data=_svc.cast_cab_vote(cr_id, payload.vote, payload.comment, current_user, db))
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.post("/cab/changes/{cr_id}/close", summary="Cerrar votación CAB — aprobar o rechazar")
@limiter.limit("20/minute")
def close_cab_vote(
    cr_id: str,
    payload: dict = Body(...),
    request: Request = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    try:
        return APIResponse.ok(data=_svc.close_cab_vote(cr_id, payload.get("decision"), payload.get("reason"), current_user, db))
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.get("/cab/windows", response_model=APIListResponse[dict], summary="Ventanas de mantenimiento")
def list_maintenance_windows(
    upcoming_only: bool = Query(False),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=MAX_TAMANO_DE_PAGINA),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    items = _svc.list_maintenance_windows(upcoming_only, db)
    return APIListResponse.ok(items=items, page=page, page_size=page_size)


class WindowCreate(BaseModel):
    name: str
    description: Optional[str] = None
    start_dt: datetime
    end_dt: datetime
    environment: str = "production"
    is_recurring: bool = False
    recurrence: Optional[str] = None


@router.post("/cab/windows", summary="Crear ventana de mantenimiento")
@limiter.limit("20/minute")
def create_maintenance_window(
    payload: WindowCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    return APIResponse.ok(data=_svc.create_maintenance_window(payload, current_user.id, db))


@router.post("/cab/changes/{cr_id}/schedule", summary="Asignar CR a ventana de mantenimiento")
@limiter.limit("20/minute")
def schedule_cr_in_window(
    cr_id: str,
    payload: dict = Body(...),
    request: Request = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    window_id = payload.get("window_id")
    if not window_id:
        raise HTTPException(422, "window_id es obligatorio")
    try:
        return APIResponse.ok(data=_svc.schedule_cr_in_window(cr_id, window_id, payload.get("rollback_plan"), payload.get("test_plan"), db))
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


@router.get("/webhooks", response_model=APIListResponse[dict], summary="Listar webhook triggers configurados")
def list_webhook_triggers(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=MAX_TAMANO_DE_PAGINA),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    items = _svc.list_webhook_triggers(db)
    return APIListResponse.ok(items=items, page=page, page_size=page_size)


@router.post("/webhooks", summary="Crear webhook trigger")
def create_webhook_trigger(
    payload: WebhookTriggerCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    try:
        return APIResponse.ok(data=_svc.create_webhook_trigger(payload, current_user.id, db))
    except ValueError as e:
        raise HTTPException(400, str(e))


_SENSIBLES = ("authorization", "cookie", "signature", "token", "secret", "api-key", "apikey", "password", "x-auth")


def _cabecera_sensible(nombre: str) -> bool:
    n = nombre.lower()
    return any(x in n for x in _SENSIBLES)


@router.post("/webhooks/fire/{slug}", summary="Disparar webhook — endpoint público")
@limiter.limit("20/minute")
async def fire_webhook(
    slug: str,
    request: Request,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    """
    External systems POST here to trigger automations.
    Verifiable via X-Contecflow-Signature HMAC header.
    """
    from app.core.async_db import run_db  # local import to avoid bootstrap cost on cold paths

    # Audit #C7: this endpoint is legitimately `async` because it needs the raw
    # request body (`await request.body()`) for HMAC verification. All DB ops
    # are now offloaded to the threadpool via `run_db` so they don't block the
    # event loop.
    trigger = await run_db(_svc.get_active_webhook_trigger_by_slug, db, slug)
    body = await request.body()
    payload_str = body.decode("utf-8") if body else "{}"
    try:
        payload_json = json.loads(payload_str)
    except Exception:
        logger.warning("Payload JSON inválido en webhook CAB slug=%s", slug, exc_info=True)
        payload_json = {}

    # Verify HMAC signature — all triggers must be signed
    import hmac as _hmac
    import hashlib as _hashlib
    signature_header = request.headers.get("X-Contecflow-Signature")
    if not trigger.secret:
        # Trigger without a secret must not be callable — reject silently to avoid enumeration
        raise HTTPException(401, "Webhook trigger no autorizado")
    if not signature_header:
        raise HTTPException(401, "Se requiere cabecera X-Contecflow-Signature")
    expected = "sha256=" + _hmac.new(
        trigger.secret.encode(), body, _hashlib.sha256
    ).hexdigest()
    if not _hmac.compare_digest(signature_header, expected):
        raise HTTPException(401, "Firma HMAC inválida")

    # Log the call and update fire stats (DB op → threadpool)
    # Revisión 2026-11: sin credenciales en el log (antes se guardaban todas las
    # cabeceras, con Authorization, Cookie y la firma).
    cabeceras = {k: ("[oculto]" if _cabecera_sensible(k) else v) for k, v in request.headers.items()}
    await run_db(_svc.log_webhook_fire, trigger, payload_str, json.dumps(cabeceras), db)

    # Fire the workflow/rule in background
    if trigger.workflow_id:
        background_tasks.add_task(_execute_workflow_from_webhook, trigger.workflow_id, payload_json,
                                  trigger.organization_id)

    return APIResponse.ok(data={"ok": True, "fired": True, "trigger": trigger.name})


def _execute_workflow_from_webhook(workflow_id: str, context: dict, organization_id: str | None = None):
    return _svc.execute_workflow_from_webhook(workflow_id, context, organization_id)


@router.get("/webhooks/{trigger_id}/logs", summary="Historial de llamadas al webhook")
def webhook_logs(
    trigger_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    return APIListResponse.ok(items=_svc.get_webhook_logs(trigger_id, db))


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
        datos = _svc.rotate_webhook_trigger_slug(trigger_id, expires_in_days, db)
    except ValueError as e:
        raise HTTPException(404, str(e))
    # Revisión GRC 2026-11b: rotar la URL secreta del webhook no dejaba rastro.
    from app.services.audit import auditar_y_confirmar
    auditar_y_confirmar(db, current_user, "SECRET_ROTATED", "webhook_trigger", trigger_id,
                        new_values={"expires_in_days": expires_in_days})
    return APIResponse.ok(data=datos)


@router.delete("/webhooks/{trigger_id}", summary="Eliminar webhook trigger")
def delete_webhook_trigger(
    trigger_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    enforce_abac(db, current_user, "cab_webhook", trigger_id, action="delete")
    try:
        return APIResponse.ok(data=_svc.delete_webhook_trigger(trigger_id, db))
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
    return APIResponse.ok(data=_svc.list_email_templates(db))


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
    return APIResponse.ok(data=_svc.create_email_template(payload, current_user.id, db))


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
    return APIResponse.ok(data=_svc.send_email_action(payload, db))


@router.get("/email/logs", summary="Historial de emails enviados")
def email_logs(
    limit: int = Query(50, le=MAX_TAMANO_DE_PAGINA),
    status: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    return APIListResponse.ok(items=_svc.get_email_logs(limit, status, db))


# ═══════════════════════════════════════════════════════════════════════════════
# GDPR
# ═══════════════════════════════════════════════════════════════════════════════

@router.get("/gdpr/requests", response_model=APIListResponse[dict], summary="Listar solicitudes GDPR")
def list_gdpr_requests(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=MAX_TAMANO_DE_PAGINA),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    items = _svc.list_gdpr_requests(db)
    return APIListResponse.ok(items=items, page=page, page_size=page_size)


class GDPRRequestCreate(BaseModel):
    request_type: str  # erasure | portability | access | rectification
    subject_user_id: Optional[str] = None
    subject_email: Optional[str] = None
    notes: Optional[str] = None


@router.post("/gdpr/requests", summary="Crear solicitud GDPR")
@limiter.limit("10/minute")
def create_gdpr_request(
    payload: GDPRRequestCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    return APIResponse.ok(data=_svc.create_gdpr_request(payload, current_user, db))


@router.post("/gdpr/requests/{request_id}/process", summary="Procesar solicitud GDPR")
@limiter.limit("5/minute")
def process_gdpr_request(
    request_id: str,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Execute the GDPR request: anonymise data or generate export."""
    try:
        return APIResponse.ok(data=_svc.process_gdpr_request(request_id, current_user, db))
    except ValueError as e:
        raise HTTPException(400, str(e))


# ═══════════════════════════════════════════════════════════════════════════════
# GLOBAL SEARCH (Cmd+K)
# ═══════════════════════════════════════════════════════════════════════════════

@router.get("/global-search", summary="Búsqueda global full-text")
@limiter.limit("30/minute")
def global_search(
    q: str = Query(..., min_length=1),
    types: Optional[str] = Query(None),
    limit: int = Query(30, le=100),
    request: Request = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Full-text search across projects, tasks, tickets, users, invoices, opportunities."""
    return APIResponse.ok(data=_svc.global_search(q, types, limit, db))


# ═══════════════════════════════════════════════════════════════════════════════
# DASHBOARD WIDGETS (personalisation)
# ═══════════════════════════════════════════════════════════════════════════════

AVAILABLE_WIDGETS = _svc.AVAILABLE_WIDGETS


@router.get("/dashboard-widgets/catalog", summary="Catálogo de widgets disponibles")
def widget_catalog(current_user: User = Depends(get_current_user)):
    return APIListResponse.ok(items=AVAILABLE_WIDGETS)


@router.get("/dashboard-widgets", summary="Widgets del usuario actual")
def get_user_widgets(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return APIListResponse.ok(items=_svc.get_user_widgets(current_user, db))


@router.post("/dashboard-widgets", summary="Guardar layout de widgets del usuario")
def save_widget_layout(
    payload: list,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return APIResponse.ok(data=_svc.save_widget_layout(payload, current_user.id, db))


@router.delete("/dashboard-widgets/reset", summary="Restablecer widgets por defecto")
def reset_widgets(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    enforce_abac(db, current_user, "dashboard_widget", str(current_user.id), action="delete")
    return APIResponse.ok(data=_svc.reset_widgets(current_user.id, db))


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
    return APIResponse.ok(data=_svc.get_onboarding(current_user, db))


@router.post("/onboarding/complete-step", summary="Marcar paso de onboarding como completado")
def complete_onboarding_step(
    payload: dict = Body(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _rol: User = Depends(require_admin),  # auditoria 2026-09: sus hermanas del fichero usan esa guarda
):
    try:
        return APIResponse.ok(data=_svc.complete_onboarding_step(payload.get("step_id"), current_user, db))
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.post("/onboarding/dismiss", summary="Cerrar onboarding wizard")
def dismiss_onboarding(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return APIResponse.ok(data=_svc.dismiss_onboarding(current_user, db))


# ═══════════════════════════════════════════════════════════════════════════════
# EXTERNAL INTEGRATIONS (GitHub, Calendar, QuickBooks)
# ═══════════════════════════════════════════════════════════════════════════════

@router.get("/oauth-integrations", summary="Listar integraciones configuradas")
def list_integrations(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    return APIListResponse.ok(items=_svc.list_integrations(db))


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
    return APIResponse.ok(data=_svc.create_integration(payload, current_user.id, db,
                                                       organization_id=current_user.organization_id))


@router.delete("/oauth-integrations/{integration_id}", summary="Desactivar integración")
def delete_integration(
    integration_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Auditoria 2026-08 (hallazgo 37): esta ruta **no existia**.

    Habia `GET` y `POST`, asi que se podia configurar una integracion OAuth y
    **no quitarla**. Desactiva y borra los tokens; el porque esta en el
    docstring de `desactivar_integracion`.
    """
    return APIResponse.ok(data=_svc.desactivar_integracion(db, integration_id))


@router.post("/oauth-integrations/{integration_id}/sync", summary="Sincronizar integración")
def sync_integration(
    integration_id: str,
    payload: dict = Body(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    try:
        return APIResponse.ok(data=_svc.run_integration_sync(integration_id, payload, db))
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
    return APIListResponse.ok(items=_svc.get_calendar_events(user_id or current_user.id, from_date, to_date, db))


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
    return APIListResponse.ok(items=_svc.get_commit_links(integration_id, task_id, db))


@router.get("/risk-scores", summary="Puntuaciones de riesgo de todos los proyectos activos")
def get_risk_scores(
    refresh: bool = Query(False),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    return APIResponse.ok(data=_svc.get_risk_scores(refresh, db))


@router.get("/risk-scores/{project_id}", summary="Puntuación de riesgo detallada de un proyecto")
def get_project_risk_score(
    project_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    try:
        return APIResponse.ok(data=_svc.get_project_risk_score(project_id, db))
    except ValueError as e:
        raise HTTPException(404, str(e))


