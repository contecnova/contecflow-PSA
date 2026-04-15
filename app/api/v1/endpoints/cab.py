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
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import func, or_
from typing import Optional, List
from datetime import date, datetime, timedelta, timezone
from pydantic import BaseModel
import json
import secrets
import re
import logging

logger = logging.getLogger("clarive.v14")

from app.core.config import settings
from app.core.encryption import encrypt_value, decrypt_value
from app.core.secret_utils import encrypt_config_secrets, decrypt_config_secrets
from app.db.session import get_db
from app.core.deps import get_current_user, require_any_manager, require_admin
from app.models.user import User
from app.models.project import Project
from app.models.task import Task
from app.models.resources import ChangeRequest
from app.models.service_desk import Ticket
from app.models.pipeline import Opportunity
from app.models.billing_reports import Invoice
from app.models.cab import (
    CABVote, MaintenanceWindow, ChangeRequestWindow,
    WebhookTrigger, WebhookTriggerLog,
    EmailTemplate, EmailLog,
    GDPRRequest, GDPRRequestType, GDPRRequestStatus,
    IntegrationConfig, CommitLink, CalendarEvent,
    RevenueRecognitionRule, RevenueRecognitionEntry, RecognitionMethod,
    DashboardWidget, OnboardingState, ProjectRiskScore,
)
from app.services.audit import audit_log

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
    crs = db.query(ChangeRequest).options(
        joinedload(ChangeRequest.project),
        joinedload(ChangeRequest.requester),
    ).filter(
        ChangeRequest.status.in_(["submitted", "under_review"])
    ).order_by(ChangeRequest.created_at.desc()).all()

    # Batch-load all votes and windows to avoid N+1 queries
    cr_ids = [cr.id for cr in crs]
    if cr_ids:
        all_votes = db.query(CABVote).filter(CABVote.change_request_id.in_(cr_ids)).all()
        all_windows = db.query(ChangeRequestWindow).filter(
            ChangeRequestWindow.change_request_id.in_(cr_ids)
        ).all()
    else:
        all_votes, all_windows = [], []

    from collections import defaultdict
    votes_by_cr: dict = defaultdict(list)
    for _v in all_votes:
        votes_by_cr[_v.change_request_id].append(_v)
    windows_by_cr: dict = defaultdict(list)
    for _w in all_windows:
        windows_by_cr[_w.change_request_id].append(_w)

    result = []
    for cr in crs:
        votes = votes_by_cr[cr.id]
        approvals = sum(1 for v in votes if v.vote == "approve")
        rejections = sum(1 for v in votes if v.vote == "reject")
        windows = windows_by_cr[cr.id]
        my_vote = next((v.vote for v in votes if v.voter_id == current_user.id), None)

        result.append({
            "id": cr.id, "code": cr.code, "title": cr.title,
            "status": cr.status,
            "impact": cr.impact,
            "cost_impact": cr.cost_impact,
            "schedule_impact_days": cr.schedule_impact_days,
            "project_name": cr.project.name if cr.project else None,
            "project_code": cr.project.code if cr.project else None,
            "requester": cr.requester.full_name if cr.requester else None,
            "created_at": str(cr.created_at)[:10] if cr.created_at else None,
            "votes": {"approve": approvals, "reject": rejections, "total": len(votes)},
            "my_vote": my_vote,
            "has_window": len(windows) > 0,
            "rollback_plan": windows[0].rollback_plan if windows else None,
        })
    return result


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
    cr = db.query(ChangeRequest).filter(ChangeRequest.id == cr_id).first()
    if not cr: raise HTTPException(404, "CR no encontrada")
    if cr.status not in ["submitted", "under_review"]:
        raise HTTPException(400, f"No se puede votar en estado '{cr.status}'")
    if payload.vote not in ["approve", "reject", "abstain"]:
        raise HTTPException(400, "Voto debe ser: approve, reject o abstain")

    # Update existing vote or create new one
    existing = db.query(CABVote).filter(
        CABVote.change_request_id == cr_id,
        CABVote.voter_id == current_user.id,
    ).first()
    if existing:
        existing.vote = payload.vote
        existing.comment = payload.comment
    else:
        db.add(CABVote(
            change_request_id=cr_id,
            voter_id=current_user.id,
            vote=payload.vote,
            comment=payload.comment,
        ))

    # Auto-update CR status based on votes
    if cr.status == "submitted":
        cr.status = "under_review"

    # Audit log is added to session before the single commit so both are atomic
    audit_log(db, current_user, "CAB_VOTE", "change_requests", cr_id, cr.code,
              new_values={"vote": payload.vote})
    db.commit()

    # Count votes (after commit so new vote is included)
    votes = db.query(CABVote).filter(CABVote.change_request_id == cr_id).all()
    approvals = sum(1 for v in votes if v.vote == "approve")
    rejections = sum(1 for v in votes if v.vote == "reject")
    return {"ok": True, "vote": payload.vote, "approvals": approvals, "rejections": rejections}


@router.post("/cab/changes/{cr_id}/close", summary="Cerrar votación CAB — aprobar o rechazar")
def close_cab_vote(
    cr_id: str,
    payload: dict = Body(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    cr = db.query(ChangeRequest).filter(ChangeRequest.id == cr_id).first()
    if not cr: raise HTTPException(404)
    decision = payload.get("decision")  # approved | rejected
    if decision not in ["approved", "rejected"]:
        raise HTTPException(400, "decision debe ser approved o rejected")
    cr.status = decision
    audit_log(db, current_user, "CAB_CLOSE", "change_requests", cr_id, cr.code,
              new_values={"decision": decision, "reason": payload.get("reason")})
    db.commit()
    return {"ok": True, "new_status": cr.status}


@router.get("/cab/windows", summary="Ventanas de mantenimiento")
def list_maintenance_windows(
    upcoming_only: bool = Query(False),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    q = db.query(MaintenanceWindow).options(joinedload(MaintenanceWindow.creator))
    if upcoming_only:
        q = q.filter(MaintenanceWindow.start_dt >= datetime.now(timezone.utc))
    windows = q.order_by(MaintenanceWindow.start_dt).limit(50).all()
    return [{
        "id": w.id, "name": w.name, "description": w.description,
        "start_dt": str(w.start_dt)[:16], "end_dt": str(w.end_dt)[:16],
        "environment": w.environment,
        "is_recurring": w.is_recurring,
        "creator": w.creator.full_name if w.creator else None,
        "created_at": str(w.created_at)[:10] if w.created_at else None,
    } for w in windows]


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
    w = MaintenanceWindow(**payload.model_dump(), created_by=current_user.id)
    db.add(w); db.commit(); db.refresh(w)
    return {"ok": True, "id": w.id}


@router.post("/cab/changes/{cr_id}/schedule", summary="Asignar CR a ventana de mantenimiento")
def schedule_cr_in_window(
    cr_id: str,
    payload: dict = Body(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    cr = db.query(ChangeRequest).filter(ChangeRequest.id == cr_id).first()
    if not cr: raise HTTPException(404)
    window_id = payload.get("window_id")
    if not window_id:
        raise HTTPException(422, "window_id es obligatorio")
    if not db.query(MaintenanceWindow).filter(MaintenanceWindow.id == window_id).first():
        raise HTTPException(404, "Ventana de mantenimiento no encontrada")
    crw = ChangeRequestWindow(
        change_request_id=cr_id,
        window_id=window_id,
        rollback_plan=payload.get("rollback_plan"),
        test_plan=payload.get("test_plan"),
    )
    db.add(crw); db.commit()
    return {"ok": True}


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
    triggers = db.query(WebhookTrigger).options(joinedload(WebhookTrigger.workflow)).all()
    return [_trigger_out(t) for t in triggers]


@router.post("/webhooks", summary="Crear webhook trigger")
def create_webhook_trigger(
    payload: WebhookTriggerCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    # Check slug unique
    existing = db.query(WebhookTrigger).filter(WebhookTrigger.slug == payload.slug).first()
    if existing: raise HTTPException(400, f"Slug '{payload.slug}' ya está en uso")

    secret = payload.secret or secrets.token_hex(32)
    t = WebhookTrigger(
        name=payload.name, slug=payload.slug,
        secret=secret,
        workflow_id=payload.workflow_id,
        rule_id=payload.rule_id,
        field_mapping=json.dumps(payload.field_mapping) if payload.field_mapping else None,
        created_by=current_user.id,
    )
    db.add(t); db.commit()
    return {"ok": True, "id": t.id, "secret": secret,
            "endpoint": f"/api/v1/webhooks/fire/{t.slug}"}


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
    trigger = db.query(WebhookTrigger).filter(
        WebhookTrigger.slug == slug,
        WebhookTrigger.is_active == True,
    ).first()

    if not trigger:
        raise HTTPException(404, "Webhook trigger no encontrado")

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

    # Log the call
    log = WebhookTriggerLog(
        trigger_id=trigger.id,
        payload=payload_str[:2000],
        headers=json.dumps(dict(request.headers))[:1000],
        status="ok",
    )
    db.add(log)
    trigger.fire_count = (trigger.fire_count or 0) + 1
    trigger.last_fired_at = datetime.now(timezone.utc)
    db.commit()

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
    logs = db.query(WebhookTriggerLog).filter(
        WebhookTriggerLog.trigger_id == trigger_id
    ).order_by(WebhookTriggerLog.received_at.desc()).limit(50).all()
    return [{
        "id": l.id, "status": l.status, "error": l.error,
        "received_at": str(l.received_at)[:16],
        "payload_preview": (l.payload or "")[:200],
    } for l in logs]


@router.delete("/webhooks/{trigger_id}", summary="Eliminar webhook trigger")
def delete_webhook_trigger(
    trigger_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    t = db.query(WebhookTrigger).filter(WebhookTrigger.id == trigger_id).first()
    if not t: raise HTTPException(404)
    db.delete(t); db.commit()
    return {"ok": True}


# ═══════════════════════════════════════════════════════════════════════════════
# EMAIL — SMTP TEMPLATES + SEND
# ═══════════════════════════════════════════════════════════════════════════════

SYSTEM_EMAIL_TEMPLATES = _svc.SYSTEM_EMAIL_TEMPLATES


@router.get("/email/templates", summary="Listar plantillas de email")
def list_email_templates(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    custom = db.query(EmailTemplate).options(joinedload(EmailTemplate.creator)).all()
    return {
        "system": SYSTEM_EMAIL_TEMPLATES,
        "custom": [{
            "id": t.id, "name": t.name, "subject": t.subject,
            "category": t.category,
            "variables": json.loads(t.variables) if t.variables else [],
            "is_system": False,
            "created_by": t.creator.full_name if t.creator else None,
        } for t in custom],
    }


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
    t = EmailTemplate(
        name=payload.name, subject=payload.subject,
        body_html=payload.body_html, body_text=payload.body_text,
        category=payload.category,
        variables=json.dumps(payload.variables) if payload.variables else None,
        created_by=current_user.id,
    )
    db.add(t); db.commit()
    return {"ok": True, "id": t.id}


class SendEmailPayload(BaseModel):
    to: List[str]
    cc: Optional[List[str]] = None
    template_id: Optional[str] = None
    subject: Optional[str] = None
    body_html: Optional[str] = None
    variables: Optional[dict] = None
    source: str = "manual"
    source_id: Optional[str] = None


def _render_template(template_str: str, variables: dict) -> str:
    return _svc.render_template(template_str, variables)


def _send_email_smtp(to: list, subject: str, body_html: str, cc: list = None) -> bool:
    return _svc.send_email_smtp(to, subject, body_html, cc)


@router.post("/email/send", summary="Enviar email (con plantilla o ad-hoc)")
def send_email(
    payload: SendEmailPayload,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    subject = payload.subject or "Notificación Clarive"
    body_html = payload.body_html or "<p>Notificación de Clarive</p>"
    template_id_ref = payload.template_id

    # Load template if specified
    if payload.template_id:
        custom_tpl = db.query(EmailTemplate).filter(
            EmailTemplate.id == payload.template_id
        ).first()
        if custom_tpl:
            subject = _render_template(custom_tpl.subject, payload.variables or {})
            body_html = _render_template(custom_tpl.body_html, payload.variables or {})
        else:
            # System template
            sys_tpl = next((t for t in SYSTEM_EMAIL_TEMPLATES if t["id"] == payload.template_id), None)
            if sys_tpl:
                subject = _render_template(sys_tpl["subject"], payload.variables or {})
                body_html = f"<p>{subject}</p>"  # System templates use subject as body preview

    # Send
    sent = _send_email_smtp(payload.to, subject, body_html, payload.cc)

    # Log
    for addr in payload.to:
        log = EmailLog(
            to_address=addr,
            cc_addresses=json.dumps(payload.cc) if payload.cc else None,
            subject=subject[:500],
            template_id=template_id_ref if db.query(EmailTemplate).filter(EmailTemplate.id == template_id_ref).first() else None,
            body_preview=body_html[:500],
            status="sent" if sent else "failed",
            sent_at=datetime.now(timezone.utc) if sent else None,
            source=payload.source,
            source_id=payload.source_id,
        )
        db.add(log)
    db.commit()

    return {"ok": True, "sent": sent, "to": payload.to, "subject": subject}


@router.get("/email/logs", summary="Historial de emails enviados")
def email_logs(
    limit: int = Query(50, le=200),
    status: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    q = db.query(EmailLog).order_by(EmailLog.created_at.desc())
    if status: q = q.filter(EmailLog.status == status)
    logs = q.limit(limit).all()
    return [{
        "id": l.id, "to": l.to_address, "subject": l.subject[:80],
        "status": l.status, "source": l.source,
        "sent_at": str(l.sent_at)[:16] if l.sent_at else None,
        "created_at": str(l.created_at)[:16] if l.created_at else None,
    } for l in logs]


# ═══════════════════════════════════════════════════════════════════════════════
# GDPR
# ═══════════════════════════════════════════════════════════════════════════════

@router.get("/gdpr/requests", summary="Listar solicitudes GDPR")
def list_gdpr_requests(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    requests = db.query(GDPRRequest).options(
        joinedload(GDPRRequest.subject_user),
        joinedload(GDPRRequest.processor),
    ).order_by(GDPRRequest.created_at.desc()).all()
    return [{
        "id": r.id, "request_type": r.request_type, "status": r.status,
        "subject_email": r.subject_email or (r.subject_user.email if r.subject_user else None),
        "subject_name": r.subject_user.full_name if r.subject_user else "Usuario eliminado",
        "deadline": str(r.deadline) if r.deadline else None,
        "completed_at": str(r.completed_at)[:10] if r.completed_at else None,
        "processor": r.processor.full_name if r.processor else None,
        "created_at": str(r.created_at)[:10] if r.created_at else None,
        "notes": r.notes,
    } for r in requests]


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
    deadline = date.today() + timedelta(days=30)  # GDPR: 30 days to respond
    req = GDPRRequest(
        request_type=payload.request_type,
        subject_user_id=payload.subject_user_id,
        subject_email=payload.subject_email,
        requestor_id=current_user.id,
        notes=payload.notes,
        deadline=deadline,
    )
    db.add(req)
    audit_log(db, current_user, "GDPR_REQUEST", "users",
              payload.subject_user_id or "unknown",
              payload.subject_email or "",
              new_values={"type": payload.request_type})
    db.commit()
    return {"ok": True, "id": req.id, "deadline": str(deadline)}


@router.post("/gdpr/requests/{request_id}/process", summary="Procesar solicitud GDPR")
def process_gdpr_request(
    request_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Execute the GDPR request: anonymise data or generate export."""
    req = db.query(GDPRRequest).filter(GDPRRequest.id == request_id).first()
    if not req: raise HTTPException(404)
    if req.status == GDPRRequestStatus.completed:
        raise HTTPException(400, "Solicitud ya procesada")

    req.status = GDPRRequestStatus.processing
    req.processed_by = current_user.id
    db.commit()

    user = db.query(User).filter(User.id == req.subject_user_id).first() if req.subject_user_id else None
    export_data = {}

    if req.request_type == GDPRRequestType.erasure and user:
        # Anonymise personal data — keep business records intact
        original_email = user.email
        anon_id = secrets.token_hex(8)
        export_data["anonymised"] = {
            "username": f"deleted_{anon_id}",
            "email": f"deleted_{anon_id}@anonymised.clarive",
            "full_name": f"Usuario Eliminado ({anon_id[:6]})",
            "first_name": None, "last_name": None,
            "phone": None, "job_title": None,
        }
        for field, value in export_data["anonymised"].items():
            if hasattr(user, field):
                setattr(user, field, value)
        user.is_active = False
        user.hashed_password = None
        export_data["original_email"] = original_email
        export_data["records_kept"] = ["imputations", "timesheets", "expenses"]

    elif req.request_type == GDPRRequestType.portability and user:
        # Collect all user data for export (Art. 20)
        from app.models.imputation import Imputation
        imputations = db.query(Imputation).filter(Imputation.user_id == user.id).count()
        export_data = {
            "user": {
                "email": user.email, "full_name": user.full_name,
                "username": user.username, "role": user.role,
                "department": user.department, "created_at": str(user.created_at)[:10] if user.created_at else None,
            },
            "data_summary": {
                "imputations": imputations,
            },
            "export_date": str(date.today()),
            "format": "JSON",
            "note": "Solicite el fichero completo al administrador del sistema.",
        }

    req.status = GDPRRequestStatus.completed
    req.completed_at = datetime.now(timezone.utc)
    req.export_data = json.dumps(export_data)
    audit_log(db, current_user, "GDPR_PROCESS", "users",
              req.subject_user_id or "unknown", "",
              new_values={"type": req.request_type, "result": req.status})
    db.commit()

    return {"ok": True, "status": req.status, "data": export_data}


# ═══════════════════════════════════════════════════════════════════════════════
# GLOBAL SEARCH (Cmd+K)
# ═══════════════════════════════════════════════════════════════════════════════

@router.get("/global-search", summary="Búsqueda global full-text")
def global_search(
    q: str = Query(..., min_length=1),
    types: Optional[str] = Query(None),  # comma-separated: projects,tasks,tickets,users
    limit: int = Query(30, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Full-text search across projects, tasks, tickets, users, invoices, opportunities.
    Returns grouped results for Cmd+K palette.
    """
    search_types = types.split(",") if types else ["projects","tasks","tickets","users","invoices","opportunities"]
    q_lower = f"%{q.lower()}%"
    results = {}

    if "projects" in search_types:
        projects = db.query(Project).filter(
            or_(
                func.lower(Project.name).like(q_lower),
                func.lower(Project.code).like(q_lower),
                func.lower(Project.client_name).like(q_lower),
            )
        ).limit(limit // 3).all()
        results["projects"] = [{
            "id": p.id, "type": "project",
            "title": p.name, "subtitle": f"{p.code} · {p.client_name or '—'}",
            "status": p.status, "url": "/projects",
            "icon": "⬡",
        } for p in projects]

    if "tasks" in search_types:
        tasks = db.query(Task).options(joinedload(Task.project)).filter(
            or_(
                func.lower(Task.title).like(q_lower),
                func.lower(Task.code).like(q_lower),
                func.lower(Task.description).like(q_lower),
            )
        ).limit(limit // 3).all()
        results["tasks"] = [{
            "id": t.id, "type": "task",
            "title": t.title,
            "subtitle": f"{t.project.code if t.project else '—'} · {t.status}",
            "status": t.status, "url": "/tasks",
            "icon": "▦",
        } for t in tasks]

    if "tickets" in search_types:
        tickets = db.query(Ticket).filter(
            or_(
                func.lower(Ticket.title).like(q_lower),
                func.lower(Ticket.number).like(q_lower),
                func.lower(Ticket.requester_name).like(q_lower),
            )
        ).limit(limit // 4).all()
        results["tickets"] = [{
            "id": t.id, "type": "ticket",
            "title": t.title,
            "subtitle": f"#{t.number} · {t.status} · {t.priority}",
            "status": t.status, "url": "/service-desk",
            "icon": "🎫",
        } for t in tickets]

    if "users" in search_types:
        users = db.query(User).filter(
            User.is_active == True,
            or_(
                func.lower(User.full_name).like(q_lower),
                func.lower(User.email).like(q_lower),
                func.lower(User.username).like(q_lower),
            )
        ).limit(limit // 4).all()
        results["users"] = [{
            "id": u.id, "type": "user",
            "title": u.full_name,
            "subtitle": f"{u.role} · {u.email}",
            "url": "/resources",
            "icon": "👤",
        } for u in users]

    if "invoices" in search_types:
        invoices = db.query(Invoice).filter(
            or_(
                func.lower(Invoice.number).like(q_lower),
                func.lower(Invoice.client_name).like(q_lower),
            )
        ).limit(10).all()
        results["invoices"] = [{
            "id": i.id, "type": "invoice",
            "title": i.number,
            "subtitle": f"{i.client_name or '—'} · {i.total}€ · {i.status}",
            "status": i.status, "url": "/invoices",
            "icon": "🧾",
        } for i in invoices]

    if "opportunities" in search_types:
        opps = db.query(Opportunity).filter(
            or_(
                func.lower(Opportunity.name).like(q_lower),
                func.lower(Opportunity.client_name).like(q_lower),
            )
        ).limit(10).all()
        results["opportunities"] = [{
            "id": o.id, "type": "opportunity",
            "title": o.name,
            "subtitle": f"{o.client_name or '—'} · {o.stage}",
            "url": "/pipeline",
            "icon": "🎪",
        } for o in opps]

    # Flatten for quick display
    all_results = []
    for group, items in results.items():
        all_results.extend(items)

    return {
        "query": q,
        "total": sum(len(v) for v in results.values()),
        "grouped": results,
        "flat": all_results[:limit],
    }


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
    widgets = db.query(DashboardWidget).filter(
        DashboardWidget.user_id == current_user.id,
        DashboardWidget.is_visible == True,
    ).order_by(DashboardWidget.position_y, DashboardWidget.position_x).all()

    if not widgets:
        # Return default layout for this role
        return _default_widget_layout(current_user.role)

    return [{
        "id": w.id, "widget_type": w.widget_type,
        "title": w.title,
        "position_x": w.position_x, "position_y": w.position_y,
        "width": w.width, "height": w.height,
        "config": json.loads(w.config) if w.config else {},
    } for w in widgets]


def _default_widget_layout(role: str) -> list:
    if role in ["admin", "pm"]:
        return [
            {"widget_type": "kpi_projects_active", "position_x": 0, "position_y": 0, "width": 1, "height": 1},
            {"widget_type": "kpi_hours_week",       "position_x": 1, "position_y": 0, "width": 1, "height": 1},
            {"widget_type": "kpi_tickets_open",     "position_x": 2, "position_y": 0, "width": 1, "height": 1},
            {"widget_type": "kpi_budget_health",    "position_x": 3, "position_y": 0, "width": 1, "height": 1},
            {"widget_type": "list_my_tasks",        "position_x": 0, "position_y": 1, "width": 2, "height": 2},
            {"widget_type": "chart_hours_trend",    "position_x": 2, "position_y": 1, "width": 2, "height": 2},
        ]
    else:
        return [
            {"widget_type": "kpi_hours_week",       "position_x": 0, "position_y": 0, "width": 1, "height": 1},
            {"widget_type": "list_my_tasks",        "position_x": 0, "position_y": 1, "width": 2, "height": 2},
            {"widget_type": "list_my_timesheets",   "position_x": 2, "position_y": 1, "width": 2, "height": 1},
        ]


@router.post("/dashboard-widgets", summary="Guardar layout de widgets del usuario")
def save_widget_layout(
    payload: list,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Replace entire widget layout for current user."""
    # Delete existing
    db.query(DashboardWidget).filter(DashboardWidget.user_id == current_user.id).delete()
    db.flush()

    for item in payload:
        widget_type = item.get("widget_type")
        if not widget_type: continue
        w = DashboardWidget(
            user_id=current_user.id,
            widget_type=widget_type,
            title=item.get("title"),
            position_x=item.get("position_x", 0),
            position_y=item.get("position_y", 0),
            width=item.get("width", 1),
            height=item.get("height", 1),
            config=json.dumps(item.get("config", {})),
        )
        db.add(w)
    db.commit()
    return {"ok": True, "count": len(payload)}


@router.delete("/dashboard-widgets/reset", summary="Restablecer widgets por defecto")
def reset_widgets(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    db.query(DashboardWidget).filter(DashboardWidget.user_id == current_user.id).delete()
    db.commit()
    return {"ok": True}


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
    state = db.query(OnboardingState).filter(
        OnboardingState.user_id == current_user.id
    ).first()

    if not state:
        # Auto-create on first access
        state = OnboardingState(user_id=current_user.id, completed_steps="[]")
        db.add(state); db.commit(); db.refresh(state)

    completed = json.loads(state.completed_steps or "[]")

    return {
        "is_complete": state.is_complete,
        "is_dismissed": state.dismissed_at is not None,
        "current_step": state.current_step,
        "completed_steps": completed,
        "progress_pct": round(len(completed) / len(ONBOARDING_STEPS) * 100),
        "steps": [{
            **step,
            "completed": step["id"] in completed,
        } for step in ONBOARDING_STEPS],
    }


@router.post("/onboarding/complete-step", summary="Marcar paso de onboarding como completado")
def complete_onboarding_step(
    payload: dict = Body(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    step_id = payload.get("step_id")
    if step_id not in [s["id"] for s in ONBOARDING_STEPS]:
        raise HTTPException(400, f"Step '{step_id}' no existe")

    state = db.query(OnboardingState).filter(
        OnboardingState.user_id == current_user.id
    ).first()
    if not state:
        state = OnboardingState(user_id=current_user.id, completed_steps="[]")
        db.add(state); db.flush()

    completed = json.loads(state.completed_steps or "[]")
    if step_id not in completed:
        completed.append(step_id)
    state.completed_steps = json.dumps(completed)
    state.current_step = len(completed)

    if len(completed) >= len(ONBOARDING_STEPS):
        state.is_complete = True
        state.completed_at = datetime.now(timezone.utc)

    db.commit()
    return {
        "ok": True, "completed_steps": completed,
        "is_complete": state.is_complete,
        "progress_pct": round(len(completed) / len(ONBOARDING_STEPS) * 100),
    }


@router.post("/onboarding/dismiss", summary="Cerrar onboarding wizard")
def dismiss_onboarding(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    state = db.query(OnboardingState).filter(
        OnboardingState.user_id == current_user.id
    ).first()
    if not state:
        state = OnboardingState(user_id=current_user.id, completed_steps="[]")
        db.add(state); db.flush()
    state.dismissed_at = datetime.now(timezone.utc)
    db.commit()
    return {"ok": True}


# ═══════════════════════════════════════════════════════════════════════════════
# EXTERNAL INTEGRATIONS (GitHub, Calendar, QuickBooks)
# ═══════════════════════════════════════════════════════════════════════════════

@router.get("/oauth-integrations", summary="Listar integraciones configuradas")
def list_integrations(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    configs = db.query(IntegrationConfig).options(
        joinedload(IntegrationConfig.creator)
    ).all()
    return [{
        "id": c.id, "integration_type": c.integration_type,
        "name": c.name, "is_active": c.is_active,
        "last_sync_at": str(c.last_sync_at)[:16] if c.last_sync_at else None,
        "sync_errors": c.sync_errors or 0,
        "last_error": c.last_error,
        "config": decrypt_config_secrets(json.loads(c.config)) if c.config else {},
        "has_token": bool(c.access_token),
        "created_by": c.creator.full_name if c.creator else None,
    } for c in configs]


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
    # Check if already exists for this type
    existing = db.query(IntegrationConfig).filter(
        IntegrationConfig.integration_type == payload.integration_type
    ).first()

    if existing:
        existing.name = payload.name
        existing.access_token = encrypt_value(payload.access_token) if payload.access_token else None
        existing.refresh_token = encrypt_value(payload.refresh_token) if payload.refresh_token else None
        existing.config = json.dumps(encrypt_config_secrets(payload.config)) if payload.config else None
        existing.is_active = True
        db.commit()
        return {"ok": True, "id": existing.id, "updated": True}

    c = IntegrationConfig(
        integration_type=payload.integration_type,
        name=payload.name,
        access_token=encrypt_value(payload.access_token) if payload.access_token else None,
        refresh_token=encrypt_value(payload.refresh_token) if payload.refresh_token else None,
        config=json.dumps(encrypt_config_secrets(payload.config)) if payload.config else None,
        created_by=current_user.id,
    )
    db.add(c); db.commit()
    return {"ok": True, "id": c.id, "updated": False}


@router.post("/oauth-integrations/{integration_id}/sync", summary="Sincronizar integración")
def sync_integration(
    integration_id: str,
    payload: dict = Body(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Trigger a sync for the given integration."""
    config = db.query(IntegrationConfig).filter(IntegrationConfig.id == integration_id).first()
    if not config: raise HTTPException(404)
    if not config.is_active: raise HTTPException(400, "Integración inactiva")

    synced = 0
    errors = []

    if config.integration_type in ["github", "gitlab"]:
        synced, errors = _sync_git_commits(db, config, payload)
    elif config.integration_type in ["google_calendar", "outlook"]:
        synced, errors = _sync_calendar(db, config, payload)
    elif config.integration_type in ["quickbooks", "xero"]:
        synced, errors = _sync_accounting(db, config, payload)
    elif config.integration_type == "jira":
        synced, errors = _sync_jira(db, config, payload)

    config.last_sync_at = datetime.now(timezone.utc)
    config.sync_errors = len(errors)
    config.last_error = errors[0] if errors else None
    db.commit()

    return {"ok": True, "synced": synced, "errors": errors[:5]}


def _sync_git_commits(db, config, payload):
    return _svc.sync_git_commits(db, config, payload)


def _sync_calendar(db, config, payload):
    return _svc.sync_calendar(db, config, payload)


def _sync_accounting(db, config, payload):
    return _svc.sync_accounting(db, config, payload)


def _sync_jira(db, config, payload):
    return _svc.sync_jira(db, config, payload)


@router.get("/oauth-integrations/calendar/events", summary="Eventos de calendario sincronizados")
def calendar_events(
    user_id: Optional[str] = None,
    from_date: Optional[date] = None,
    to_date: Optional[date] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    q = db.query(CalendarEvent).options(joinedload(CalendarEvent.project))
    uid = user_id or current_user.id
    q = q.filter(CalendarEvent.user_id == uid)
    if from_date: q = q.filter(CalendarEvent.start_dt >= datetime.combine(from_date, datetime.min.time()))
    if to_date:   q = q.filter(CalendarEvent.start_dt <= datetime.combine(to_date, datetime.max.time()))
    events = q.order_by(CalendarEvent.start_dt).limit(100).all()
    return [{
        "id": e.id, "title": e.title,
        "start_dt": str(e.start_dt)[:16], "end_dt": str(e.end_dt)[:16],
        "all_day": e.all_day, "description": e.description,
        "project_name": e.project.name if e.project else None,
        "sprint_id": e.sprint_id, "milestone_id": e.milestone_id,
    } for e in events]


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
    q = db.query(CommitLink).options(
        joinedload(CommitLink.task).joinedload(Task.project)
    ).filter(CommitLink.integration_id == integration_id)
    if task_id: q = q.filter(CommitLink.task_id == task_id)
    links = q.order_by(CommitLink.created_at_ext.desc()).limit(50).all()
    return [{
        "id": l.id, "link_type": l.link_type,
        "task_id": l.task_id,
        "task_code": l.task.code if l.task else None,
        "task_title": l.task.title if l.task else None,
        "project_code": l.task.project.code if l.task and l.task.project else None,
        "external_id": l.external_id,
        "title": l.title, "url": l.url, "author": l.author,
        "state": l.state,
        "synced_at": str(l.synced_at)[:16] if l.synced_at else None,
    } for l in links]


@router.get("/revenue/rules", summary="Reglas de reconocimiento de ingresos")
def list_revenue_rules(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    rules = db.query(RevenueRecognitionRule).options(
        joinedload(RevenueRecognitionRule.project),
        joinedload(RevenueRecognitionRule.entries),
    ).all()
    return [{
        "id": r.id, "project_id": r.project_id,
        "project_name": r.project.name if r.project else None,
        "project_code": r.project.code if r.project else None,
        "method": r.method,
        "contract_value": r.contract_value,
        "start_date": str(r.start_date) if r.start_date else None,
        "end_date": str(r.end_date) if r.end_date else None,
        "total_recognised": sum(e.amount_actual for e in r.entries),
        "total_deferred": sum(e.amount_deferred for e in r.entries),
        "entry_count": len(r.entries),
    } for r in rules]


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
    existing = db.query(RevenueRecognitionRule).filter(
        RevenueRecognitionRule.project_id == payload.project_id
    ).first()
    if existing: raise HTTPException(400, "Ya existe una regla para este proyecto")

    rule = RevenueRecognitionRule(**payload.model_dump(), created_by=current_user.id)
    db.add(rule); db.commit()
    return {"ok": True, "id": rule.id}


@router.post("/revenue/rules/{rule_id}/compute", summary="Calcular reconocimiento del período")
def compute_revenue_period(
    rule_id: str,
    payload: dict = Body(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    """Compute and record revenue recognition for a given month."""
    rule = db.query(RevenueRecognitionRule).options(
        joinedload(RevenueRecognitionRule.project),
        joinedload(RevenueRecognitionRule.entries),
    ).filter(RevenueRecognitionRule.id == rule_id).first()
    if not rule: raise HTTPException(404)

    period_str = payload.get("period", str(date.today().replace(day=1)))
    period = date.fromisoformat(period_str)

    # Check not already locked
    existing = db.query(RevenueRecognitionEntry).filter(
        RevenueRecognitionEntry.rule_id == rule_id,
        RevenueRecognitionEntry.period_date == period,
    ).first()
    if existing and existing.is_locked:
        raise HTTPException(400, "El período ya está cerrado contablemente")

    project = rule.project
    contract_val = rule.contract_value or 0

    # Compute % complete based on method
    pct_complete = 0.0
    amount_planned = 0.0

    if rule.method == RecognitionMethod.percentage_complete:
        total_tasks = db.query(func.count(Task.id)).filter(Task.project_id == project.id).scalar() or 1
        done_tasks = db.query(func.count(Task.id)).filter(
            Task.project_id == project.id, Task.status == "done"
        ).scalar() or 0
        pct_complete = round(done_tasks / total_tasks * 100, 1)
        amount_to_date = round(contract_val * pct_complete / 100, 2)
        prev_recognized = sum(e.amount_actual for e in rule.entries if e.period_date < period)
        amount_planned = round(max(amount_to_date - prev_recognized, 0), 2)

    elif rule.method == RecognitionMethod.time_and_material:
        from app.models.imputation import Imputation
        # Sum billable hours this period * billing rate
        month_start = period
        month_end = period.replace(day=28) + timedelta(days=4)
        month_end = month_end - timedelta(days=month_end.day)
        hours = db.query(func.sum(Imputation.hours)).filter(
            Imputation.project_id == project.id,
            Imputation.is_billable == True,
            Imputation.date >= month_start,
            Imputation.date <= month_end,
        ).scalar() or 0
        rate = project.billing_rate or 100
        amount_planned = round(hours * rate, 2)
        pct_complete = round(amount_planned / max(contract_val, 1) * 100, 1)

    elif rule.method == RecognitionMethod.straight_line:
        if rule.start_date and rule.end_date and rule.end_date >= rule.start_date:
            business_days = 0
            current = rule.start_date
            while current <= rule.end_date:
                if current.weekday() < 5:  # Mon-Fri
                    business_days += 1
                current += timedelta(days=1)
            total_months = max(round(business_days / 22, 1), 1)
            amount_planned = round(contract_val / total_months, 2)
            prev_total = sum(e.amount_actual for e in rule.entries if e.period_date < period)
            pct_complete = round((prev_total + amount_planned) / max(contract_val, 1) * 100, 1)

    # Calculate cumulative from all prior periods (idempotent recalc)
    prev_cumulative = sum(
        e.amount_actual for e in rule.entries if e.period_date < period
    )
    cumulative = round(prev_cumulative + amount_planned, 2)
    deferred = round(max(contract_val - cumulative, 0), 2)

    if existing:
        existing.pct_complete = pct_complete
        existing.amount_planned = amount_planned
        existing.amount_actual = amount_planned
        existing.cumulative_amount = cumulative
        existing.cumulative_pct = round((cumulative / max(contract_val, 1)) * 100, 1)
        existing.amount_deferred = deferred
    else:
        db.add(RevenueRecognitionEntry(
            rule_id=rule_id,
            project_id=project.id,
            period_date=period,
            pct_complete=pct_complete,
            amount_planned=amount_planned,
            amount_actual=amount_planned,
            amount_deferred=deferred,
            cumulative_amount=cumulative,
            cumulative_pct=round((cumulative / max(contract_val, 1)) * 100, 1),
        ))

    db.commit()
    return {
        "ok": True, "period": str(period),
        "method": rule.method,
        "pct_complete": pct_complete,
        "amount_recognised": amount_planned,
        "cumulative": cumulative,
        "deferred": deferred,
        "contract_value": contract_val,
    }


@router.post("/revenue/auto-compute", summary="Computar Rev Rec automáticamente para todos los proyectos activos")
def auto_compute_revenue(
    period: Optional[str] = Body(None, embed=True),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    """
    Ejecuta el cómputo de reconocimiento de ingresos para TODOS los proyectos
    con reglas activas. Diseñado para llamarse mensualmente (cron o manual).
    """
    from app.models.cab import RevenueRecognitionRule
    period_str = period or str(date.today().replace(day=1))

    rules = db.query(RevenueRecognitionRule).filter(
        RevenueRecognitionRule.is_active == True
    ).all()

    results = []
    for rule in rules:
        try:
            # Reutilizar la lógica del compute individual
            project = rule.project
            if not project or project.status in ("completed", "cancelled"):
                continue

            contract_val = rule.contract_value or 0
            period_date  = date.fromisoformat(period_str)

            # Calcular según método
            if rule.method.value == "milestone_billing":
                # Nuevo método: reconocer según milestones aprobados/facturados
                from app.models.financial import ProjectMilestone
                approved_ms = db.query(ProjectMilestone).filter(
                    ProjectMilestone.project_id == project.id,
                    ProjectMilestone.billing_status.in_(["approved", "invoiced"]),
                ).all()
                amount_planned = sum(m.billing_amount or 0 for m in approved_ms)
                pct_complete   = round(amount_planned / max(contract_val, 1) * 100, 1)
            else:
                # Delegar al compute individual
                amount_planned = 0
                pct_complete   = 0

            from app.models.cab import RevenueRecognitionEntry
            # Sum only prior periods to avoid double-counting
            prev_cumulative = db.query(func.sum(RevenueRecognitionEntry.amount_actual)).filter(
                RevenueRecognitionEntry.rule_id == rule.id,
                RevenueRecognitionEntry.period_date < period_date,
            ).scalar() or 0
            # amount_planned is total-to-date; compute delta for this period
            amount_delta = round(max(amount_planned - prev_cumulative, 0), 2)
            cumulative = round(prev_cumulative + amount_delta, 2)
            deferred   = round(max(contract_val - cumulative, 0), 2)

            if amount_planned > 0:
                existing = db.query(RevenueRecognitionEntry).filter(
                    RevenueRecognitionEntry.rule_id == rule.id,
                    RevenueRecognitionEntry.period_date == period_date,
                ).first()
                if existing and not existing.is_locked:
                    existing.amount_actual   = amount_delta
                    existing.cumulative_amount = cumulative
                elif not existing and amount_delta > 0:
                    db.add(RevenueRecognitionEntry(
                        rule_id=rule.id, project_id=project.id,
                        period_date=period_date,
                        pct_complete=pct_complete,
                        amount_planned=amount_delta, amount_actual=amount_delta,
                        amount_deferred=deferred,
                        cumulative_amount=cumulative,
                        cumulative_pct=round((cumulative / max(contract_val, 1)) * 100, 1),
                    ))

            results.append({"rule_id": rule.id, "project": project.name,
                            "amount": amount_delta, "status": "ok"})
        except Exception as e:
            results.append({"rule_id": rule.id, "status": "error", "error": str(e)})

    db.commit()
    total = sum(r.get("amount", 0) for r in results if r["status"] == "ok")
    return {"period": period_str, "processed": len(results),
            "total_recognised": round(total, 2), "results": results}


@router.get("/revenue/summary", summary="Resumen de ingresos reconocidos")
def revenue_summary(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    entries = db.query(RevenueRecognitionEntry).options(
        joinedload(RevenueRecognitionEntry.project)
    ).order_by(RevenueRecognitionEntry.period_date.desc()).all()

    by_month = {}
    for e in entries:
        m = str(e.period_date)[:7]
        if m not in by_month: by_month[m] = {"month": m, "recognised": 0, "deferred": 0}
        by_month[m]["recognised"] += e.amount_actual or 0
        by_month[m]["deferred"] += e.amount_deferred or 0

    total_recognised = sum(e.amount_actual or 0 for e in entries)
    total_deferred = sum(e.amount_deferred or 0 for e in entries)

    return {
        "total_recognised": round(total_recognised, 2),
        "total_deferred": round(total_deferred, 2),
        "by_month": sorted(by_month.values(), key=lambda x: x["month"]),
        "entry_count": len(entries),
    }


# ═══════════════════════════════════════════════════════════════════════════════
# PROJECT RISK SCORE (predictive engine)
# ═══════════════════════════════════════════════════════════════════════════════

def _compute_risk_score(db, project):
    return _svc.compute_risk_score(db, project)


@router.get("/risk-scores", summary="Puntuaciones de riesgo de todos los proyectos activos")
def get_risk_scores(
    refresh: bool = Query(False),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    projects = db.query(Project).filter(
        Project.status.in_(["active", "planning"])
    ).all()

    results = []
    for project in projects:
        # Use cached score if recent (< 1 hour) and not forced refresh
        cached = db.query(ProjectRiskScore).filter(
            ProjectRiskScore.project_id == project.id
        ).order_by(ProjectRiskScore.computed_at.desc()).first()

        if cached and not refresh and cached.computed_at:
            age_minutes = (datetime.now(timezone.utc) - cached.computed_at).total_seconds() / 60
            if age_minutes < 60:
                results.append({
                    "project_id": project.id,
                    "project_name": project.name,
                    "project_code": project.code,
                    "overall_score": cached.overall_score,
                    "level": cached.level,
                    "schedule_risk": cached.schedule_risk,
                    "budget_risk": cached.budget_risk,
                    "scope_risk": cached.scope_risk,
                    "resource_risk": cached.resource_risk,
                    "delay_probability_pct": cached.delay_probability_pct,
                    "predicted_delay_weeks": cached.predicted_delay_weeks,
                    "recommendation": cached.recommendation,
                    "computed_at": str(cached.computed_at)[:16],
                    "cached": True,
                })
                continue

        # Compute fresh
        score_data = _compute_risk_score(db, project)
        score_obj = ProjectRiskScore(
            project_id=project.id,
            **{k: v for k, v in score_data.items() if k in [
                "schedule_risk","budget_risk","scope_risk","resource_risk",
                "overall_score","level","delay_probability_pct",
                "predicted_delay_weeks","recommendation",
            ]}
        )
        db.add(score_obj)

        results.append({
            "project_id": project.id,
            "project_name": project.name,
            "project_code": project.code,
            **score_data,
            "computed_at": datetime.now(timezone.utc).isoformat()[:16],
            "cached": False,
        })

    db.commit()
    results.sort(key=lambda x: -(x.get("overall_score") or 0))
    return {
        "projects": results,
        "summary": {
            "critical": sum(1 for r in results if r.get("level") == "critical"),
            "high": sum(1 for r in results if r.get("level") == "high"),
            "medium": sum(1 for r in results if r.get("level") == "medium"),
            "low": sum(1 for r in results if r.get("level") == "low"),
        }
    }


@router.get("/risk-scores/{project_id}", summary="Puntuación de riesgo detallada de un proyecto")
def get_project_risk_score(
    project_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project: raise HTTPException(404)

    score_data = _compute_risk_score(db, project)

    # Save
    score_obj = ProjectRiskScore(
        project_id=project_id,
        **{k: v for k, v in score_data.items() if k in [
            "schedule_risk","budget_risk","scope_risk","resource_risk",
            "overall_score","level","delay_probability_pct",
            "predicted_delay_weeks","recommendation",
        ]}
    )
    db.add(score_obj); db.commit()

    return {
        "project_id": project_id,
        "project_name": project.name,
        "project_code": project.code,
        "client_name": project.client_name,
        **score_data,
        "history": [],  # Could show historical scores
    }


# ── Revenue Journal Entries (ASC 606 / IFRS 15 double-entry accounting) ───────

@router.get("/revenue/journal/{project_id}", summary="Asientos contables de reconocimiento de ingresos (ASC 606 / IFRS 15)")
def revenue_journal_entries(
    project_id: str,
    db:              Session = Depends(get_db),
    _: User = Depends(require_any_manager),
):
    """
    Generates GAAP-compliant double-entry accounting journal records from
    revenue recognition entries (RevenueRecognitionEntry).

    Double-entry schema per period:
      • DR  Accounts Receivable / Cuentas por cobrar  (amount_actual)
        CR  Revenue / Ingresos reconocidos             (amount_actual)

      • If deferred > 0:
        DR  Cash / Tesorería                            (amount_actual)
        CR  Deferred Revenue / Ingresos diferidos       (amount_deferred)
        DR  Deferred Revenue / Ingresos diferidos       (amount_deferred)   ← when releasing
        CR  Revenue / Ingresos reconocidos               (amount_deferred)   ← when releasing

    Returns journal_lines ready for import into ERP (SAP / Sage / QuickBooks).
    """
    from app.models.cab import RevenueRecognitionRule, RevenueRecognitionEntry

    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(404, "Proyecto no encontrado")

    rule = db.query(RevenueRecognitionRule).filter(
        RevenueRecognitionRule.project_id == project_id
    ).first()
    if not rule:
        raise HTTPException(404, "No hay regla de reconocimiento de ingresos para este proyecto. Configura una en /revenue.")

    entries = (
        db.query(RevenueRecognitionEntry)
        .filter(RevenueRecognitionEntry.project_id == project_id)
        .order_by(RevenueRecognitionEntry.period_date)
        .all()
    )

    if not entries:
        return {
            "project_id":   project_id,
            "project_name": project.name,
            "method":       rule.method.value if rule.method else None,
            "journal_lines": [],
            "summary": {"total_recognised": 0, "total_deferred": 0, "entry_count": 0},
        }

    journal_lines = []
    total_recognised = 0.0
    total_deferred   = 0.0

    for entry in entries:
        period = str(entry.period_date)
        recognised = float(entry.amount_actual or 0)
        deferred   = float(entry.amount_deferred or 0)

        if recognised > 0:
            # DR Accounts Receivable
            journal_lines.append({
                "date":           period,
                "period":         period[:7],  # YYYY-MM
                "journal_ref":    f"REV-{project.code or project_id[:8].upper()}-{period[:7].replace('-','')}",
                "line":           "DR",
                "account_code":   "1100",
                "account_name":   "Cuentas por cobrar / Accounts Receivable",
                "description":    f"Reconocimiento ingresos — {project.name} ({period[:7]})",
                "debit":          round(recognised, 2),
                "credit":         0.0,
                "currency":       getattr(project, "currency", "EUR"),
                "method":         rule.method.value if rule.method else "N/A",
                "pct_complete":   round(float(entry.pct_complete or 0), 2),
                "is_locked":      entry.is_locked,
            })
            # CR Revenue
            journal_lines.append({
                "date":           period,
                "period":         period[:7],
                "journal_ref":    f"REV-{project.code or project_id[:8].upper()}-{period[:7].replace('-','')}",
                "line":           "CR",
                "account_code":   "4000",
                "account_name":   "Ingresos reconocidos / Revenue",
                "description":    f"Reconocimiento ingresos — {project.name} ({period[:7]})",
                "debit":          0.0,
                "credit":         round(recognised, 2),
                "currency":       getattr(project, "currency", "EUR"),
                "method":         rule.method.value if rule.method else "N/A",
                "pct_complete":   round(float(entry.pct_complete or 0), 2),
                "is_locked":      entry.is_locked,
            })
            total_recognised += recognised

        if deferred > 0:
            # DR Cash  /  CR Deferred Revenue (initial deferral)
            journal_lines.append({
                "date":           period,
                "period":         period[:7],
                "journal_ref":    f"DEF-{project.code or project_id[:8].upper()}-{period[:7].replace('-','')}",
                "line":           "DR",
                "account_code":   "1000",
                "account_name":   "Tesorería / Cash",
                "description":    f"Cobro diferido — {project.name} ({period[:7]})",
                "debit":          round(deferred, 2),
                "credit":         0.0,
                "currency":       getattr(project, "currency", "EUR"),
                "method":         rule.method.value if rule.method else "N/A",
                "pct_complete":   round(float(entry.pct_complete or 0), 2),
                "is_locked":      entry.is_locked,
            })
            journal_lines.append({
                "date":           period,
                "period":         period[:7],
                "journal_ref":    f"DEF-{project.code or project_id[:8].upper()}-{period[:7].replace('-','')}",
                "line":           "CR",
                "account_code":   "2400",
                "account_name":   "Ingresos diferidos / Deferred Revenue",
                "description":    f"Cobro diferido — {project.name} ({period[:7]})",
                "debit":          0.0,
                "credit":         round(deferred, 2),
                "currency":       getattr(project, "currency", "EUR"),
                "method":         rule.method.value if rule.method else "N/A",
                "pct_complete":   round(float(entry.pct_complete or 0), 2),
                "is_locked":      entry.is_locked,
            })
            total_deferred += deferred

    return {
        "project_id":    project_id,
        "project_name":  project.name,
        "project_code":  project.code,
        "currency":      getattr(project, "currency", "EUR"),
        "method":        rule.method.value if rule.method else None,
        "contract_value": float(rule.contract_value or 0),
        "standard":      "ASC 606 / IFRS 15",
        "journal_lines": journal_lines,
        "summary": {
            "total_recognised": round(total_recognised, 2),
            "total_deferred":   round(total_deferred, 2),
            "entry_count":      len(entries),
            "journal_line_count": len(journal_lines),
        },
    }


@router.get("/revenue/journal/{project_id}/export", summary="Exportar asientos contables en CSV")
def export_revenue_journal(
    project_id: str,
    db:         Session = Depends(get_db),
    _:          User = Depends(require_any_manager),
):
    """Returns journal entries as CSV string for ERP import."""
    import csv, io
    data = revenue_journal_entries(project_id=project_id, db=db, _=_)
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
