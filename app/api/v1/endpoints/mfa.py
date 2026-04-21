"""
mfa: thin router delegating to app.services.mfa_service
"""
from fastapi import APIRouter, Depends, HTTPException, Query, Request, BackgroundTasks, Body
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import func
from typing import Optional, List
from datetime import date, datetime, timedelta, timezone
from pydantic import BaseModel
import json
import logging
import secrets
import io

_logger = logging.getLogger(__name__)

from app.db.session import get_db
from app.core.deps import get_current_user, require_any_manager, require_admin
from app.core.encryption import encrypt_value, decrypt_value
from app.models.user import User
from app.models.project import Project
from app.models.task import Task
from app.models.service_desk import Ticket
from app.models.imputation import Imputation
from app.models.mfa import (
    Organization, MFAConfig, MFABackupCode,
    SlackConfig, SlackNotificationLog,
    Budget, BudgetEntry,
    AITaskEstimate, AITicketTriage,
    ScenarioModel, ScenarioProject,
    PDFExportJob, BIToken,
)
from app.core.config import settings
from app.services.audit import audit_log
import app.services.mfa_service as _svc

router = APIRouter()

# Quitar usuario de organización
@router.delete("/organizations/{org_id}/remove-user/{user_id}", summary="Quitar usuario de organización")
def remove_user_from_org(
    org_id: str,
    user_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    try:
        return _svc.remove_user_from_org(org_id, user_id, db)
    except ValueError as e:
        msg = str(e)
        if msg.startswith("404:"):
            raise HTTPException(404, msg[4:])
        raise HTTPException(400, msg)

# Local aliases kept for backward compatibility with any tests that patch these names
def _get_totp_lib():
    return _svc.get_totp_lib()

def _send_slack_message(config, text, channel=None):
    return _svc.send_slack_message(config, text, channel)

def _budget_by_dept(budgets):
    return _svc.budget_by_dept(budgets)

def _generate_pdf(export_type, source_id, params, db):
    return _svc.generate_pdf(export_type, source_id, params, db)

def _verify_bi_token(token, db):
    return _svc.verify_bi_token(token, db)


# ═══════════════════════════════════════════════════════════════════════════════
# MFA / 2FA — TOTP
# ═══════════════════════════════════════════════════════════════════════════════

@router.get("/mfa/status", summary="Estado MFA del usuario actual")
def mfa_status(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return _svc.get_mfa_status(current_user.id, db)


@router.post("/mfa/setup", summary="Iniciar configuración MFA — genera secret y QR URL")
def mfa_setup(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        return _svc.setup_mfa(current_user, db)
    except ValueError as e:
        msg = str(e)
        if "pyotp" in msg:
            raise HTTPException(
                501,
                "MFA TOTP no disponible: falta la librería pyotp. Instala con 'pip install pyotp' y reinicia el backend."
            )
        raise HTTPException(400, msg)


class MFAVerifyPayload(BaseModel):
    code: str


@router.post("/mfa/verify", summary="Verificar código TOTP y activar MFA")
def mfa_verify(
    payload: MFAVerifyPayload,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        return _svc.verify_and_activate_mfa(current_user, payload.code, db)
    except ValueError as e:
        msg = str(e)
        if "pyotp" in msg:
            raise HTTPException(
                501,
                "MFA TOTP no disponible: falta la librería pyotp. Instala con 'pip install pyotp' y reinicia el backend."
            )
        raise HTTPException(400, msg)


@router.post("/mfa/validate", summary="Validar código MFA durante el login")
def mfa_validate(
    payload: MFAVerifyPayload,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        return _svc.validate_mfa_code(current_user, payload.code, db)
    except ValueError as e:
        msg = str(e)
        if "pyotp" in msg:
            raise HTTPException(503, msg)
        raise HTTPException(401, msg)


@router.delete("/mfa/disable", summary="Desactivar MFA")
def mfa_disable(
    payload: MFAVerifyPayload,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        return _svc.disable_mfa(current_user, payload.code, db)
    except ValueError as e:
        msg = str(e)
        if "pyotp" in msg:
            raise HTTPException(503, msg)
        raise HTTPException(400, msg)


# ═══════════════════════════════════════════════════════════════════════════════
# MULTI-TENANCY — Organizations
# ═══════════════════════════════════════════════════════════════════════════════

@router.get("/organizations", summary="Listar organizaciones (super-admin)")
def list_organizations(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    return _svc.list_organizations(db)


class OrgCreate(BaseModel):
    name: str
    slug: str
    plan: str = "starter"
    max_users: int = 25
    max_projects: int = 100
    admin_email: Optional[str] = None
    timezone: str = settings.DEFAULT_TIMEZONE
    locale: str = settings.DEFAULT_LANGUAGE
    primary_color: Optional[str] = None


@router.post("/organizations", summary="Crear nueva organización (tenant)")
def create_organization(
    payload: OrgCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    try:
        return _svc.create_organization(payload.model_dump(), current_user, db)
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.get("/organizations/{org_id}", summary="Detalle de organización")
def get_organization(
    org_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    try:
        return _svc.get_organization(org_id, db)
    except ValueError:
        raise HTTPException(404)


@router.patch("/organizations/{org_id}", summary="Actualizar organización")
def update_organization(
    org_id: str,
    payload: dict = Body(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    try:
        return _svc.update_organization(org_id, payload, db)
    except ValueError:
        raise HTTPException(404)


@router.post("/organizations/{org_id}/assign-user", summary="Asignar usuario a organización")
def assign_user_to_org(
    org_id: str,
    payload: dict = Body(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    try:
        return _svc.assign_user_to_org(org_id, payload.get("user_id"), db)
    except ValueError as e:
        msg = str(e)
        if msg.startswith("404:"):
            raise HTTPException(404, msg[4:])
        raise HTTPException(400, msg)


# ═══════════════════════════════════════════════════════════════════════════════
# SLACK / TEAMS
# ═══════════════════════════════════════════════════════════════════════════════

@router.get("/slack/config", summary="Configuración Slack/Teams")
def get_slack_config(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    return _svc.get_slack_config(db)


class SlackConfigCreate(BaseModel):
    platform: str = "slack"
    workspace_name: Optional[str] = None
    bot_token: Optional[str] = None
    webhook_url: Optional[str] = None
    default_channel: str = "#clarive-alerts"
    subscriptions: Optional[List[str]] = None


@router.post("/slack/config", summary="Crear/actualizar configuración Slack")
def create_slack_config(
    payload: SlackConfigCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    return _svc.create_or_update_slack_config(payload.model_dump(), db)


@router.post("/slack/test", summary="Enviar mensaje de prueba a Slack/Teams")
def test_slack(
    payload: dict = Body(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    try:
        config_id = payload.get("config_id")
        message = payload.get("message", "🔔 Mensaje de prueba desde Clarive v15")
        channel = payload.get("channel", "#clarive-alerts")
        return _svc.test_slack_config(config_id, message, channel, db)
    except ValueError:
        raise HTTPException(404)


@router.post("/slack/notify", summary="Enviar notificación de evento Slack")
def slack_notify(
    payload: dict = Body(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    try:
        return _svc.notify_slack(
            payload.get("event_type", "manual"),
            payload.get("message", "Notificación de Clarive"),
            payload.get("channel"),
            payload.get("source_id"),
            db,
        )
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.get("/slack/logs", summary="Historial de notificaciones Slack")
def slack_logs(
    limit: int = Query(50, le=200),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    return _svc.get_slack_logs(limit, db)


# ═══════════════════════════════════════════════════════════════════════════════
# MULTI-PERIOD BUDGETS
# ═══════════════════════════════════════════════════════════════════════════════

@router.get("/budgets", summary="Listar presupuestos")
def list_budgets(
    year: Optional[int] = None,
    department: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    return _svc.list_budgets(year, department, db)


class BudgetCreate(BaseModel):
    name: str
    year: int
    department: Optional[str] = None
    project_id: Optional[str] = None
    total_amount: float = 0
    currency: str = settings.DEFAULT_CURRENCY
    notes: Optional[str] = None
    monthly_planned: Optional[List[float]] = None


@router.post("/budgets", summary="Crear presupuesto anual")
def create_budget(
    payload: BudgetCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    return _svc.create_budget(payload.model_dump(), current_user.id, db)


@router.patch("/budgets/{budget_id}/entry", summary="Actualizar entrada mensual de presupuesto")
def update_budget_entry(
    budget_id: str,
    payload: dict = Body(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    try:
        return _svc.update_budget_entry(budget_id, payload, db)
    except ValueError as e:
        msg = str(e)
        if msg == "not_found":
            raise HTTPException(404)
        raise HTTPException(400, msg)


@router.post("/budgets/{budget_id}/approve", summary="Aprobar presupuesto")
def approve_budget(
    budget_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    try:
        return _svc.approve_budget(budget_id, current_user, db)
    except ValueError:
        raise HTTPException(404)


@router.get("/budgets/summary", summary="Resumen anual de presupuestos")
def budget_summary(
    year: int = Query(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    return _svc.get_budget_summary(year, db)


# ═══════════════════════════════════════════════════════════════════════════════
# AI — TASK ESTIMATION
# ═══════════════════════════════════════════════════════════════════════════════

@router.post("/ai-planning/estimate/{task_id}", summary="Estimar horas de tarea con IA")
def estimate_task_hours(
    task_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        return _svc.estimate_task_hours(task_id, db)
    except ValueError:
        raise HTTPException(404)


@router.post("/ai-planning/estimate/{task_id}/accept", summary="Aceptar o rechazar estimación IA")
def accept_estimate(
    task_id: str,
    payload: dict = Body(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        return _svc.accept_task_estimate(task_id, payload.get("accepted", True), db)
    except ValueError:
        raise HTTPException(404)


# ═══════════════════════════════════════════════════════════════════════════════
# AI — TICKET TRIAGE
# ═══════════════════════════════════════════════════════════════════════════════

@router.post("/ai-planning/triage/{ticket_id}", summary="Triaje automático de ticket con IA")
def ai_triage_ticket(
    ticket_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        return _svc.triage_ticket(ticket_id, db)
    except ValueError:
        raise HTTPException(404)


@router.post("/ai-planning/triage/{ticket_id}/accept", summary="Aplicar triaje IA al ticket")
def accept_triage(
    ticket_id: str,
    payload: dict = Body(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    try:
        return _svc.accept_ticket_triage(ticket_id, payload.get("accepted", True), current_user.id, db)
    except ValueError:
        raise HTTPException(404)


# ═══════════════════════════════════════════════════════════════════════════════
# SCENARIO PLANNING / WHAT-IF
# ═══════════════════════════════════════════════════════════════════════════════

@router.get("/scenarios", summary="Listar escenarios what-if")
def list_scenarios(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    return _svc.list_scenarios(db)


class ScenarioCreate(BaseModel):
    name: str
    description: Optional[str] = None
    base_date: Optional[date] = None
    horizon_weeks: int = 12
    projects: Optional[List[dict]] = None


@router.post("/scenarios", summary="Crear escenario what-if")
def create_scenario(
    payload: ScenarioCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    return _svc.create_scenario(payload.model_dump(), current_user.id, db)


@router.post("/scenarios/{scenario_id}/compute", summary="Calcular impacto del escenario")
def compute_scenario(
    scenario_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    try:
        return _svc.compute_scenario(scenario_id, db)
    except ValueError:
        raise HTTPException(404)


@router.get("/scenarios/{scenario_id}", summary="Detalle de escenario")
def get_scenario(
    scenario_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    try:
        return _svc.get_scenario(scenario_id, db)
    except ValueError:
        raise HTTPException(404)


@router.delete("/scenarios/{scenario_id}", summary="Eliminar escenario")
def delete_scenario(
    scenario_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    try:
        return _svc.delete_scenario(scenario_id, db)
    except ValueError:
        raise HTTPException(404)


# ═══════════════════════════════════════════════════════════════════════════════
# PDF EXPORT
# ═══════════════════════════════════════════════════════════════════════════════

@router.post("/pdf/export", summary="Exportar informe o factura a PDF con logo")
def export_pdf(
    background_tasks: BackgroundTasks,
    payload: dict = Body(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    export_type = payload.get("export_type", "generic")
    source_id = payload.get("source_id")
    params = {
        "company_name": payload.get("company_name", "Clarive"),
        "primary_color": payload.get("primary_color", "#1C2833"),
        "logo_b64": payload.get("logo_b64"),
    }

    try:
        pdf_bytes, filename = _svc.create_and_run_pdf_export(
            export_type, source_id, params, current_user.id, db
        )
        return StreamingResponse(
            io.BytesIO(pdf_bytes),
            media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
    except ValueError as e:
        raise HTTPException(500, str(e))


@router.get("/pdf/jobs", summary="Historial de exportaciones PDF")
def list_pdf_jobs(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return _svc.list_pdf_jobs(current_user.id, db)


# ═══════════════════════════════════════════════════════════════════════════════
# BI CONNECTOR
# ═══════════════════════════════════════════════════════════════════════════════

@router.get("/bi/tokens", summary="Listar tokens BI")
def list_bi_tokens(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    return _svc.list_bi_tokens(db)


class BITokenCreate(BaseModel):
    name: str
    tool: str = "powerbi"
    scopes: Optional[List[str]] = None
    expires_days: Optional[int] = None


@router.post("/bi/tokens", summary="Crear token BI")
def create_bi_token(
    payload: BITokenCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    return _svc.create_bi_token(payload.model_dump(), current_user.id, db)


@router.delete("/bi/tokens/{token_id}", summary="Revocar token BI")
def revoke_bi_token(
    token_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    try:
        return _svc.revoke_bi_token(token_id, db)
    except ValueError:
        raise HTTPException(404)


@router.get("/bi/data/projects", summary="Datos de proyectos para BI")
def bi_data_projects(
    request: Request,
    db: Session = Depends(get_db),
    token: Optional[str] = Query(None),
):
    auth_header = request.headers.get("Authorization", "")
    raw_token = token or (auth_header.replace("Bearer bi_", "bi_") if "bi_" in auth_header else None)
    try:
        return _svc.bi_data_projects(raw_token, db)
    except ValueError:
        raise HTTPException(401, "Token BI inválido o caducado")


@router.get("/bi/data/timesheets", summary="Datos de imputaciones para BI")
def bi_data_timesheets(
    request: Request,
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(500, ge=1, le=5000),
    db: Session = Depends(get_db),
    token: Optional[str] = Query(None),
):
    auth_header = request.headers.get("Authorization", "")
    raw_token = token or (auth_header if "bi_" in auth_header else None)
    try:
        return _svc.bi_data_timesheets(raw_token, date_from, date_to, page, page_size, db)
    except ValueError:
        raise HTTPException(401, "Token BI inválido")


@router.get("/bi/data/kpis", summary="KPIs globales para BI")
def bi_data_kpis(
    request: Request,
    db: Session = Depends(get_db),
    token: Optional[str] = Query(None),
):
    auth_header = request.headers.get("Authorization", "")
    raw_token = token or (auth_header if "bi_" in auth_header else None)
    try:
        return _svc.bi_data_kpis(raw_token, db)
    except ValueError:
        raise HTTPException(401, "Token BI inválido")


