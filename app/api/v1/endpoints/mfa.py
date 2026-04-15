"""
mfa — thin router delegating to app.services.mfa_service
"""
from app.core.config import settings
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
from app.services.audit import audit_log
import app.services.mfa_service as _svc

router = APIRouter()

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
            raise HTTPException(503, msg)
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
            raise HTTPException(503, msg)
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
    orgs = db.query(Organization).order_by(Organization.name).limit(200).all()
    return [_svc.serialize_organization(o, db) for o in orgs]


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
    existing = db.query(Organization).filter(Organization.slug == payload.slug).first()
    if existing:
        raise HTTPException(400, f"Slug '{payload.slug}' ya está en uso")
    org = Organization(**payload.model_dump())
    db.add(org); db.commit(); db.refresh(org)
    audit_log(db, current_user, "ORG_CREATED", "organizations", org.id, org.name)
    db.commit()
    return {"ok": True, "id": org.id, "slug": org.slug}


@router.get("/organizations/{org_id}", summary="Detalle de organización")
def get_organization(
    org_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    org = db.query(Organization).filter(Organization.id == org_id).first()
    if not org: raise HTTPException(404)
    users = db.query(User).filter(User.organization_id == org_id).all()
    return {
        "id": org.id, "name": org.name, "slug": org.slug,
        "plan": org.plan, "is_active": org.is_active,
        "max_users": org.max_users, "max_projects": org.max_projects,
        "admin_email": org.admin_email, "timezone": org.timezone,
        "locale": org.locale, "primary_color": org.primary_color,
        "users": [{"id": u.id, "full_name": u.full_name, "email": u.email, "role": u.role} for u in users],
    }


@router.patch("/organizations/{org_id}", summary="Actualizar organización")
def update_organization(
    org_id: str,
    payload: dict = Body(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    org = db.query(Organization).filter(Organization.id == org_id).first()
    if not org: raise HTTPException(404)
    allowed = {"name", "plan", "max_users", "max_projects", "is_active", "admin_email",
               "timezone", "locale", "primary_color", "logo_url"}
    for k, v in payload.items():
        if k in allowed: setattr(org, k, v)
    db.commit()
    return {"ok": True}


@router.post("/organizations/{org_id}/assign-user", summary="Asignar usuario a organización")
def assign_user_to_org(
    org_id: str,
    payload: dict = Body(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    org = db.query(Organization).filter(Organization.id == org_id).first()
    if not org: raise HTTPException(404, "Organización no encontrada")
    user = db.query(User).filter(User.id == payload.get("user_id")).first()
    if not user: raise HTTPException(404, "Usuario no encontrado")
    try:
        _svc.check_org_user_limit(org, db)
    except ValueError as e:
        raise HTTPException(400, str(e))
    user.organization_id = org_id
    db.commit()
    return {"ok": True, "user": user.full_name, "org": org.name}


# ═══════════════════════════════════════════════════════════════════════════════
# SLACK / TEAMS
# ═══════════════════════════════════════════════════════════════════════════════

@router.get("/slack/config", summary="Configuración Slack/Teams")
def get_slack_config(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    configs = db.query(SlackConfig).all()
    return [{
        "id": c.id, "platform": c.platform,
        "workspace_name": c.workspace_name,
        "default_channel": c.default_channel,
        "is_active": c.is_active,
        "has_token": bool(c.bot_token),
        "subscriptions": json.loads(c.subscriptions or "[]"),
        "last_ping_at": str(c.last_ping_at)[:16] if c.last_ping_at else None,
    } for c in configs]


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
    existing = db.query(SlackConfig).filter(SlackConfig.platform == payload.platform).first()
    subs = json.dumps(payload.subscriptions or ["task_overdue", "budget_alert", "ticket_sla"])
    if existing:
        existing.workspace_name = payload.workspace_name
        existing.bot_token = payload.bot_token
        existing.webhook_url = payload.webhook_url
        existing.default_channel = payload.default_channel
        existing.subscriptions = subs
        existing.is_active = True
        db.commit()
        return {"ok": True, "id": existing.id, "updated": True}
    config = SlackConfig(
        platform=payload.platform,
        workspace_name=payload.workspace_name,
        bot_token=payload.bot_token,
        webhook_url=payload.webhook_url,
        default_channel=payload.default_channel,
        subscriptions=subs,
    )
    db.add(config); db.commit()
    return {"ok": True, "id": config.id, "updated": False}


@router.post("/slack/test", summary="Enviar mensaje de prueba a Slack/Teams")
def test_slack(
    payload: dict = Body(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    config_id = payload.get("config_id")
    config = db.query(SlackConfig).filter(SlackConfig.id == config_id).first()
    if not config: raise HTTPException(404)

    message = payload.get("message", "🔔 Mensaje de prueba desde Clarive v15")
    channel = payload.get("channel", config.default_channel)

    sent, error = _send_slack_message(config, message, channel)

    log = SlackNotificationLog(
        config_id=config.id,
        channel=channel,
        event_type="test",
        message=message,
        status="sent" if sent else "failed",
        error=error,
    )
    db.add(log)
    if sent:
        config.last_ping_at = datetime.now(timezone.utc)
    db.commit()
    return {"ok": sent, "error": error, "platform": config.platform}


@router.post("/slack/notify", summary="Enviar notificación de evento Slack")
def slack_notify(
    payload: dict = Body(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    event_type = payload.get("event_type", "manual")
    message = payload.get("message", "Notificación de Clarive")
    channel = payload.get("channel")
    source_id = payload.get("source_id")

    config = db.query(SlackConfig).filter(SlackConfig.is_active == True).first()
    if not config:
        raise HTTPException(400, "No hay integración Slack/Teams activa")

    subs = json.loads(config.subscriptions or "[]")
    if event_type not in subs and event_type != "manual":
        return {"ok": True, "skipped": True, "reason": f"Event '{event_type}' not subscribed"}

    sent, error = _send_slack_message(config, message, channel or config.default_channel)
    db.add(SlackNotificationLog(
        config_id=config.id, channel=channel or config.default_channel,
        event_type=event_type, message=message[:500],
        status="sent" if sent else "failed", error=error, source_id=source_id,
    ))
    db.commit()
    return {"ok": sent, "error": error}


@router.get("/slack/logs", summary="Historial de notificaciones Slack")
def slack_logs(
    limit: int = Query(50, le=200),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    logs = db.query(SlackNotificationLog).order_by(
        SlackNotificationLog.sent_at.desc()
    ).limit(limit).all()
    return [{
        "id": l.id, "platform": l.config.platform if l.config else "—",
        "channel": l.channel, "event_type": l.event_type,
        "status": l.status, "error": l.error,
        "sent_at": str(l.sent_at)[:16] if l.sent_at else None,
        "message": (l.message or "")[:80],
    } for l in logs]


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
    q = db.query(Budget).options(joinedload(Budget.entries))
    if year: q = q.filter(Budget.year == year)
    if department: q = q.filter(Budget.department == department)
    budgets = q.order_by(Budget.year.desc(), Budget.name).limit(200).all()
    return [{
        "id": b.id, "name": b.name, "year": b.year,
        "department": b.department,
        "total_amount": b.total_amount, "currency": b.currency,
        "is_approved": b.is_approved,
        "planned_total": sum(e.planned for e in b.entries),
        "actual_total": sum(e.actual for e in b.entries),
        "deviation": sum(e.actual for e in b.entries) - sum(e.planned for e in b.entries),
        "deviation_pct": round((sum(e.actual for e in b.entries) - sum(e.planned for e in b.entries)) / max(b.total_amount, 1) * 100, 1),
        "entries": [{
            "month": e.month, "planned": e.planned,
            "actual": e.actual, "committed": e.committed,
            "is_locked": e.is_locked,
        } for e in sorted(b.entries, key=lambda x: x.month)],
    } for b in budgets]


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
    b = Budget(
        name=payload.name, year=payload.year,
        department=payload.department, project_id=payload.project_id,
        total_amount=payload.total_amount, currency=payload.currency,
        notes=payload.notes, created_by=current_user.id,
    )
    db.add(b); db.flush()

    monthly = payload.monthly_planned or []
    if not monthly:
        monthly = [round(payload.total_amount / 12, 2)] * 12

    for month in range(1, 13):
        planned = monthly[month - 1] if month <= len(monthly) else 0
        db.add(BudgetEntry(budget_id=b.id, month=month, planned=planned))

    db.commit()
    return {"ok": True, "id": b.id}


@router.patch("/budgets/{budget_id}/entry", summary="Actualizar entrada mensual de presupuesto")
def update_budget_entry(
    budget_id: str,
    payload: dict = Body(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    month = payload.get("month")
    entry = db.query(BudgetEntry).filter(
        BudgetEntry.budget_id == budget_id,
        BudgetEntry.month == month,
    ).first()
    if not entry: raise HTTPException(404)
    if entry.is_locked: raise HTTPException(400, "Mes cerrado contablemente")
    for field in ["planned", "actual", "committed", "notes"]:
        if field in payload: setattr(entry, field, payload[field])
    db.commit()
    return {"ok": True}


@router.post("/budgets/{budget_id}/approve", summary="Aprobar presupuesto")
def approve_budget(
    budget_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    b = db.query(Budget).filter(Budget.id == budget_id).first()
    if not b: raise HTTPException(404)
    b.is_approved = True
    b.approved_by = current_user.id
    b.approved_at = datetime.now(timezone.utc)
    audit_log(db, current_user, "BUDGET_APPROVED", "budgets", b.id, b.name)
    db.commit()
    return {"ok": True}


@router.get("/budgets/summary", summary="Resumen anual de presupuestos")
def budget_summary(
    year: int = Query(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    yr = year or datetime.now().year
    budgets = db.query(Budget).options(joinedload(Budget.entries)).filter(
        Budget.year == yr
    ).all()
    total_planned = sum(e.planned for b in budgets for e in b.entries)
    total_actual = sum(e.actual for b in budgets for e in b.entries)
    by_month = {}
    for b in budgets:
        for e in b.entries:
            if e.month not in by_month:
                by_month[e.month] = {"month": e.month, "planned": 0, "actual": 0}
            by_month[e.month]["planned"] += e.planned
            by_month[e.month]["actual"] += e.actual
    return {
        "year": yr,
        "total_planned": round(total_planned, 2),
        "total_actual": round(total_actual, 2),
        "deviation": round(total_actual - total_planned, 2),
        "deviation_pct": round((total_actual - total_planned) / max(total_planned, 1) * 100, 1),
        "budgets_count": len(budgets),
        "approved_count": sum(1 for b in budgets if b.is_approved),
        "by_month": [by_month[m] for m in sorted(by_month.keys())],
        "by_department": _budget_by_dept(budgets),
    }


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
    scenarios = db.query(ScenarioModel).options(
        joinedload(ScenarioModel.projects),
        joinedload(ScenarioModel.creator),
    ).order_by(ScenarioModel.created_at.desc()).all()
    return [{
        "id": s.id, "name": s.name, "description": s.description,
        "status": s.status, "horizon_weeks": s.horizon_weeks,
        "project_count": len(s.projects),
        "creator": s.creator.full_name if s.creator else None,
        "created_at": str(s.created_at)[:10] if s.created_at else None,
        "computed_at": str(s.computed_at)[:16] if s.computed_at else None,
        "has_results": bool(s.results),
    } for s in scenarios]


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
    s = ScenarioModel(
        name=payload.name,
        description=payload.description,
        base_date=payload.base_date or date.today(),
        horizon_weeks=payload.horizon_weeks,
        created_by=current_user.id,
    )
    db.add(s); db.flush()

    for p in (payload.projects or []):
        db.add(ScenarioProject(
            scenario_id=s.id,
            name=p.get("name", "Proyecto hipotético"),
            project_id=p.get("project_id"),
            start_date=date.fromisoformat(p["start_date"]) if p.get("start_date") else None,
            end_date=date.fromisoformat(p["end_date"]) if p.get("end_date") else None,
            total_hours=p.get("total_hours", 0),
            skill_demand=json.dumps(p.get("skill_demand", {})),
            is_existing=bool(p.get("project_id")),
        ))
    db.commit()
    return {"ok": True, "id": s.id}


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
    s = db.query(ScenarioModel).options(
        joinedload(ScenarioModel.projects)
    ).filter(ScenarioModel.id == scenario_id).first()
    if not s: raise HTTPException(404)
    return {
        "id": s.id, "name": s.name, "description": s.description,
        "status": s.status, "horizon_weeks": s.horizon_weeks,
        "base_date": str(s.base_date) if s.base_date else None,
        "computed_at": str(s.computed_at)[:16] if s.computed_at else None,
        "results": json.loads(s.results) if s.results else None,
        "projects": [{
            "id": p.id, "name": p.name,
            "start_date": str(p.start_date) if p.start_date else None,
            "end_date": str(p.end_date) if p.end_date else None,
            "total_hours": p.total_hours,
            "is_existing": p.is_existing,
        } for p in s.projects],
    }


@router.delete("/scenarios/{scenario_id}", summary="Eliminar escenario")
def delete_scenario(
    scenario_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    s = db.query(ScenarioModel).filter(ScenarioModel.id == scenario_id).first()
    if not s: raise HTTPException(404)
    db.delete(s); db.commit()
    return {"ok": True}


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

    job = PDFExportJob(
        export_type=export_type,
        source_id=source_id,
        status="generating",
        params=json.dumps(params),
        requested_by=current_user.id,
    )
    db.add(job); db.commit(); db.refresh(job)

    try:
        pdf_bytes = _generate_pdf(export_type, source_id, params, db)
        job.status = "ready"
        job.file_size = len(pdf_bytes)
        job.completed_at = datetime.now(timezone.utc)
        db.commit()

        filename = f"clarive_{export_type}_{source_id or 'export'}_{datetime.now().strftime('%Y%m%d')}.pdf"
        return StreamingResponse(
            io.BytesIO(pdf_bytes),
            media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
    except Exception as e:
        job.status = "failed"
        job.error = str(e)[:500]
        db.commit()
        raise HTTPException(500, f"Error generando PDF: {str(e)}")


@router.get("/pdf/jobs", summary="Historial de exportaciones PDF")
def list_pdf_jobs(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    jobs = db.query(PDFExportJob).filter(
        PDFExportJob.requested_by == current_user.id
    ).order_by(PDFExportJob.created_at.desc()).limit(50).all()
    return [{
        "id": j.id, "export_type": j.export_type,
        "source_id": j.source_id, "status": j.status,
        "file_size": j.file_size,
        "error": j.error,
        "created_at": str(j.created_at)[:16] if j.created_at else None,
        "completed_at": str(j.completed_at)[:16] if j.completed_at else None,
    } for j in jobs]


# ═══════════════════════════════════════════════════════════════════════════════
# BI CONNECTOR
# ═══════════════════════════════════════════════════════════════════════════════

@router.get("/bi/tokens", summary="Listar tokens BI")
def list_bi_tokens(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    tokens = db.query(BIToken).options(joinedload(BIToken.creator)).all()
    return [{
        "id": t.id, "name": t.name, "tool": t.tool,
        "token_prefix": t.token_prefix,
        "scopes": json.loads(t.scopes or '["read"]'),
        "is_active": t.is_active,
        "expires_at": str(t.expires_at)[:10] if t.expires_at else None,
        "last_used_at": str(t.last_used_at)[:16] if t.last_used_at else None,
        "requests_today": t.requests_today or 0,
        "created_by": t.creator.full_name if t.creator else None,
    } for t in tokens]


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
    import bcrypt
    raw_token = "bi_" + secrets.token_hex(24)
    prefix = raw_token[:10]
    hashed = bcrypt.hashpw(raw_token.encode(), bcrypt.gensalt()).decode()
    expires_at = None
    if payload.expires_days:
        expires_at = datetime.now(timezone.utc) + timedelta(days=payload.expires_days)

    t = BIToken(
        name=payload.name, tool=payload.tool,
        token_hash=hashed, token_prefix=prefix,
        scopes=json.dumps(payload.scopes or ["read"]),
        expires_at=expires_at, created_by=current_user.id,
    )
    db.add(t); db.commit()
    return {"ok": True, "id": t.id, "token": raw_token,
            "warning": "Guarda este token. No se mostrará de nuevo."}


@router.delete("/bi/tokens/{token_id}", summary="Revocar token BI")
def revoke_bi_token(
    token_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    t = db.query(BIToken).filter(BIToken.id == token_id).first()
    if not t: raise HTTPException(404)
    t.is_active = False
    db.commit()
    return {"ok": True}


@router.get("/bi/data/projects", summary="Datos de proyectos para BI")
def bi_data_projects(
    request: Request,
    db: Session = Depends(get_db),
    token: Optional[str] = Query(None),
    current_user: Optional[User] = Depends(lambda db=Depends(get_db): None),
):
    auth_header = request.headers.get("Authorization", "")
    raw_token = token or (auth_header.replace("Bearer bi_", "bi_") if "bi_" in auth_header else None)
    if raw_token:
        bt = _verify_bi_token(raw_token, db)
        if not bt: raise HTTPException(401, "Token BI inválido o caducado")
        db.commit()
    else:
        raise HTTPException(401, "Se requiere autenticación: token BI o JWT")

    projects = db.query(Project).filter(Project.status != "archived").all()
    return [{
        "id": p.id, "code": p.code, "name": p.name,
        "client_name": p.client_name, "status": p.status,
        "start_date": str(p.start_date) if p.start_date else None,
        "end_date_planned": str(p.end_date_planned) if p.end_date_planned else None,
        "budget_amount": p.budget_amount, "billing_rate": p.billing_rate,
        "total_hours_logged": db.query(func.sum(Imputation.hours)).filter(
            Imputation.project_id == p.id).scalar() or 0,
    } for p in projects]


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
    if raw_token:
        bt = _verify_bi_token(raw_token, db)
        if not bt: raise HTTPException(401, "Token BI inválido")
        db.commit()

    q = db.query(Imputation).options(
        joinedload(Imputation.user), joinedload(Imputation.project)
    )
    if date_from: q = q.filter(Imputation.date >= date.fromisoformat(date_from))
    if date_to: q = q.filter(Imputation.date <= date.fromisoformat(date_to))
    imputations = (
        q.order_by(Imputation.date.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )

    return [{
        "date": str(i.date),
        "user_name": i.user.full_name if i.user else "—",
        "user_role": i.user.role if i.user else "—",
        "project_code": i.project.code if i.project else "—",
        "project_name": i.project.name if i.project else "—",
        "hours": i.hours,
        "is_billable": i.is_billable,
        "description": i.description,
    } for i in imputations]


@router.get("/bi/data/kpis", summary="KPIs globales para BI")
def bi_data_kpis(
    request: Request,
    db: Session = Depends(get_db),
    token: Optional[str] = Query(None),
):
    auth_header = request.headers.get("Authorization", "")
    raw_token = token or (auth_header if "bi_" in auth_header else None)
    if raw_token:
        bt = _verify_bi_token(raw_token, db)
        if not bt: raise HTTPException(401, "Token BI inválido")
        db.commit()

    active_projects = db.query(func.count(Project.id)).filter(Project.status == "active").scalar()
    total_users = db.query(func.count(User.id)).filter(User.is_active == True).scalar()
    this_week_start = date.today() - timedelta(days=date.today().weekday())
    hours_this_week = db.query(func.sum(Imputation.hours)).filter(
        Imputation.date >= this_week_start
    ).scalar() or 0
    total_budget = db.query(func.sum(Project.budget_amount)).filter(
        Project.status.in_(["active", "planning"])
    ).scalar() or 0

    return {
        "active_projects": active_projects,
        "total_users": total_users,
        "hours_this_week": round(hours_this_week, 1),
        "total_budget_active": round(total_budget, 2),
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
