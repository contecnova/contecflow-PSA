"""
client_portal_service.py — Business logic extracted from client_portal router.
"""
from datetime import datetime, timedelta, timezone, date
from typing import Optional
import logging

import bcrypt
from jose import jwt, JWTError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.billing_reports import Invoice
from app.models.billing_reports import InvoiceStatus
from app.models.billing_reports import ApprovalRequest
from app.models.client_portal import ClientMessage
from app.models.client_portal import ClientUser, client_user_projects
from app.models.client_portal import UATSession, UATStatus, FeatureRequest, FeatureRequestStatus
from app.models.client_portal import UATTestCase
from app.models.client_portal import UATIssue
from app.models.client_portal import ClientDocument
from app.models.client_portal import ClientSurvey
from app.models.clients import ClientPortalConfig, Client
from app.models.clients import Client as ClientOrg
from app.models.settings import AppSetting
from app.models.epics import WikiPage, WikiSpace
from app.models.financial import ProjectMilestone
from app.models.imputation import Imputation
from app.models.project import Project as ProjectModel
from app.models.resources import Deliverable, DeliverableStatus
from app.models.resources import ChangeRequest, ChangeRequestStatus
from app.models.resources import ChangeRequestImpact
from app.models.service_desk import Ticket, TicketStatus
from app.services.approval_workflows import find_default_workflow
from app.services.realtime_notifications import publish_user_notification
from sqlalchemy import and_, false, func, or_
from sqlalchemy.orm import joinedload

logger = logging.getLogger("contecflow.client_portal")

CLIENT_TOKEN_EXPIRE_HOURS = getattr(settings, "CLIENT_TOKEN_EXPIRE_HOURS", 72)
CLIENT_TOKEN_SECRET = settings.CLIENT_PORTAL_SECRET
PORTAL_SHARE_LINK_EXPIRE_HOURS = getattr(settings, "PORTAL_SHARE_LINK_EXPIRE_HOURS", 72)
ALGORITHM = getattr(settings, "JWT_ALGORITHM", "HS256")


# ── Auth helpers ──────────────────────────────────────────────────────────────

def hash_password(p: str) -> str:
    return bcrypt.hashpw(p.encode(), bcrypt.gensalt()).decode()


def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode(), hashed.encode())


def create_client_token(client_id: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(hours=CLIENT_TOKEN_EXPIRE_HOURS)
    return jwt.encode(
        {"sub": client_id, "exp": expire, "type": "client"},
        CLIENT_TOKEN_SECRET,
        algorithm=ALGORITHM,
    )


def get_portal_session_config(db: Session) -> dict:
    """Return idle-timeout session policy for the client portal."""
    defaults = {
        "idle_timeout_enabled": "false",
        "idle_timeout_minutes": "30",
    }
    rows = db.query(AppSetting).filter(
        AppSetting.organization_id.is_(None),
        AppSetting.key.in_(list(defaults.keys())),
    ).all()
    values = {r.key: r.value for r in rows}

    enabled_raw = (values.get("idle_timeout_enabled") or defaults["idle_timeout_enabled"]).strip().lower()
    minutes_raw = values.get("idle_timeout_minutes") or defaults["idle_timeout_minutes"]
    try:
        minutes = max(1, int(minutes_raw))
    except Exception:
        logger.warning("Invalid idle_timeout_minutes=%r in portal settings; using default", minutes_raw, exc_info=True)
        minutes = int(defaults["idle_timeout_minutes"])

    return {
        "idle_timeout_enabled": enabled_raw in ("true", "1", "yes", "on"),
        "idle_timeout_minutes": minutes,
    }


def create_portal_share_token(project_id: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(hours=PORTAL_SHARE_LINK_EXPIRE_HOURS)
    return jwt.encode(
        {"project_id": project_id, "exp": expire, "type": "portal_share"},
        CLIENT_TOKEN_SECRET,
        algorithm=ALGORITHM,
    )


def decode_portal_share_token(token: str) -> Optional[str]:
    try:
        payload = jwt.decode(token, CLIENT_TOKEN_SECRET, algorithms=[ALGORITHM])
        if payload.get("type") != "portal_share":
            return None
        return payload.get("project_id")
    except JWTError:
        return None


# ── Serializers ───────────────────────────────────────────────────────────────

def get_recent_activity(project_id: str, db: Session) -> list:

    activity = []
    msgs = db.query(ClientMessage).filter(
        ClientMessage.project_id == project_id,
        ClientMessage.is_internal == False,
        ClientMessage.sender_user_id != None,
    ).order_by(ClientMessage.created_at.desc()).limit(3).all()
    for m in msgs:
        name = m.sender_user.full_name if m.sender_user else "Equipo"
        activity.append({
            "type": "message",
            "text": f"Mensaje de {name}: {m.body[:60]}...",
            "date": str(m.created_at)[:10],
        })

    dels = db.query(Deliverable).filter(
        Deliverable.project_id == project_id,
        Deliverable.status.in_([DeliverableStatus.delivered, DeliverableStatus.accepted])
    ).order_by(Deliverable.updated_at.desc()).limit(2).all()
    for d in dels:
        activity.append({
            "type": "deliverable",
            "text": f"Entregable disponible: {d.name}",
            "date": str(d.updated_at or d.created_at)[:10],
        })

    activity.sort(key=lambda x: x["date"], reverse=True)
    return activity[:5]


_FR_STATUS_LABELS = {
    "new": "Nueva", "reviewing": "En revisión", "estimated": "Presupuestada",
    "approved": "Aprobada", "rejected": "Rechazada",
    "in_development": "En desarrollo", "done": "Completada",
}
_FR_PRIORITY_LABELS = {"low": "Baja", "medium": "Media", "high": "Alta", "critical": "Crítica"}
_FR_PRIORITY_COLORS = {"low": "#00e5a0", "medium": "#00d4ff", "high": "#ffb800", "critical": "#ff4757"}
_FR_STATUS_COLORS = {
    "new": "#7a8aaa", "reviewing": "#00d4ff", "estimated": "#ffb800",
    "approved": "#00e5a0", "rejected": "#ff4757",
    "in_development": "#7c3aed", "done": "#00e5a0",
}
_CR_STATUS_LABELS = {
    "draft": "Borrador", "submitted": "Enviado",
    "under_review": "En revisión", "approved": "Aprobado",
    "rejected": "Rechazado", "implemented": "Implementado",
}
_CR_STATUS_COLORS = {
    "draft": "#7a8aaa", "submitted": "#00d4ff",
    "under_review": "#ffb800", "approved": "#00e5a0",
    "rejected": "#ff4757", "implemented": "#7c3aed",
}


def _resolve_fr_cr_status(fr):
    """Return (cr_status, cr_status_label, cr_status_color) for a FeatureRequest's linked CR."""
    if not getattr(fr, "change_request_id", None):
        return None, None, None
    cr = (
        fr.change_request_id
        and fr.__dict__.get("_sa_instance_state")
        and fr._sa_instance_state.session.query(ChangeRequest).filter(
            ChangeRequest.id == fr.change_request_id
        ).first()
    )
    if not cr:
        return None, None, None
    return (
        cr.status,
        _CR_STATUS_LABELS.get(cr.status, cr.status),
        _CR_STATUS_COLORS.get(cr.status, "#7a8aaa"),
    )


def fr_out(fr) -> dict:
    cr_status, cr_status_label, cr_status_color = _resolve_fr_cr_status(fr)
    return {
        "id": fr.id, "code": fr.code, "project_id": fr.project_id,
        "project_name": fr.project.name if fr.project else "—",
        "client_id": fr.client_id,
        "title": fr.title, "description": fr.description,
        "business_justification": fr.business_justification,
        "affected_area": fr.affected_area,
        "priority": fr.priority,
        "priority_label": _FR_PRIORITY_LABELS.get(fr.priority, fr.priority),
        "priority_color": _FR_PRIORITY_COLORS.get(fr.priority, "#7a8aaa"),
        "status": fr.status,
        "status_label": _FR_STATUS_LABELS.get(fr.status, fr.status),
        "status_color": _FR_STATUS_COLORS.get(fr.status, "#7a8aaa"),
        "pm_response": fr.pm_response,
        "estimated_hours": fr.estimated_hours,
        "estimated_cost": fr.estimated_cost,
        "estimated_delivery_weeks": fr.estimated_delivery_weeks,
        "client_approved": fr.client_approved,
        "client_approved_at": str(fr.client_approved_at)[:10] if fr.client_approved_at else None,
        "submitted_at": str(fr.submitted_at)[:10] if fr.submitted_at else None,
        "updated_at": str(fr.updated_at)[:16] if fr.updated_at else None,
        "change_request_id": getattr(fr, "change_request_id", None),
        "cr_status": cr_status,
        "cr_status_label": cr_status_label,
        "cr_status_color": cr_status_color,
    }


_UAT_STATUS_LABELS = {
    "pending": "Pendiente", "in_progress": "En progreso",
    "passed": "Aprobado", "failed": "Rechazado",
    "conditional": "Aprobado con reservas",
}
_UAT_STATUS_COLORS = {
    "pending": "#7a8aaa", "in_progress": "#00d4ff",
    "passed": "#00e5a0", "failed": "#ff4757", "conditional": "#ffb800",
}


def _uat_stats(test_cases) -> dict:
    """Compute pass/fail/pending counters for a UATSession's test cases."""
    passed = sum(1 for tc in test_cases if tc.status == "passed")
    failed = sum(1 for tc in test_cases if tc.status == "failed")
    total = len(test_cases)
    return {"total": total, "passed": passed, "failed": failed, "pending": total - passed - failed}


def _uat_test_cases_out(test_cases) -> list:
    return [
        {
            "id": tc.id, "title": tc.title, "steps": tc.steps,
            "expected_result": tc.expected_result, "actual_result": tc.actual_result,
            "status": tc.status, "notes": tc.notes, "order": tc.order,
        }
        for tc in sorted(test_cases, key=lambda x: x.order)
    ]


def _uat_issues_out(issues) -> list:
    return [
        {
            "id": i.id, "title": i.title, "description": i.description,
            "severity": i.severity, "status": i.status,
            "steps_to_reproduce": i.steps_to_reproduce,
        }
        for i in issues
    ]


def uat_out(s) -> dict:
    return {
        "id": s.id, "code": s.code, "project_id": s.project_id,
        "deliverable_id": s.deliverable_id,
        "title": s.title, "description": s.description,
        "test_environment": s.test_environment,
        "test_credentials": s.test_credentials,
        "test_guide_url": s.test_guide_url,
        "status": s.status,
        "status_label": _UAT_STATUS_LABELS.get(s.status, s.status),
        "status_color": _UAT_STATUS_COLORS.get(s.status, "#7a8aaa"),
        "available_from": str(s.available_from) if s.available_from else None,
        "deadline": str(s.deadline) if s.deadline else None,
        "completed_at": str(s.completed_at)[:10] if s.completed_at else None,
        "client_result": s.client_result,
        "client_notes": s.client_notes,
        "test_cases": _uat_test_cases_out(s.test_cases),
        "issues": _uat_issues_out(s.issues),
        "stats": _uat_stats(s.test_cases),
        "overdue": s.deadline and date.today() > s.deadline and s.status in ["pending", "in_progress"],
    }


def msg_out(m) -> dict:
    return {
        "id": m.id, "project_id": m.project_id,
        "thread_id": m.thread_id or m.id,
        "parent_id": m.parent_id,
        "subject": m.subject, "body": m.body,
        "is_internal": m.is_internal,
        "sender_name": (
            m.sender_client.full_name if m.sender_client
            else (m.sender_user.full_name if m.sender_user else "Sistema")
        ),
        "sender_type": "client" if m.sender_client_id else "team",
        "is_read_by_client": m.is_read_by_client,
        "is_read_by_team": m.is_read_by_team,
        "feature_request_id": m.feature_request_id,
        "uat_session_id": m.uat_session_id,
        "created_at": str(m.created_at)[:16],
        "replies": [],
    }


def doc_out(d) -> dict:
    CAT_LABELS = {
        "contract": "Contrato", "deliverable": "Entregable",
        "meeting_notes": "Acta reunión", "report": "Informe", "other": "Otro",
    }
    return {
        "id": d.id, "title": d.title, "description": d.description,
        "category": d.category, "category_label": CAT_LABELS.get(d.category, d.category),
        "file_url": d.file_url, "file_name": d.file_name, "file_size_kb": d.file_size_kb,
        "requires_signature": d.requires_signature, "signed_by_client": d.signed_by_client,
        "is_visible_to_client": d.is_visible_to_client,
        "created_at": str(d.created_at)[:10],
    }


def survey_out(s) -> dict:
    return {
        "id": s.id, "title": s.title, "status": s.status,
        "overall_satisfaction": s.overall_satisfaction,
        "communication_score": s.communication_score,
        "quality_score": s.quality_score,
        "deadline_score": s.deadline_score,
        "nps_score": s.nps_score,
        "comments": s.comments,
        "would_recommend": s.would_recommend,
        "sent_at": str(s.sent_at)[:10],
        "completed_at": str(s.completed_at)[:10] if s.completed_at else None,
    }


# ── Client Management ─────────────────────────────────────────────────────────

def list_clients(project_id: Optional[str], client_org_id: Optional[str], db: Session) -> list:
    import sqlalchemy as sa

    q = db.query(ClientUser).options(joinedload(ClientUser.project), joinedload(ClientUser.projects))
    if project_id:
        q = q.outerjoin(
            client_user_projects,
            ClientUser.id == client_user_projects.c.client_user_id,
        ).filter(
            sa.or_(
                ClientUser.project_id == project_id,
                client_user_projects.c.project_id == project_id,
            )
        ).distinct()
    if client_org_id:
        q = q.filter(ClientUser.client_org_id == client_org_id)
    clients = q.order_by(ClientUser.full_name).all()
    return [{
        "id": c.id,
        "project_id": c.project_id,
        "project_ids": c.get_project_ids(),
        "project_name": c.project.name if c.project else (c.projects[0].name if c.projects else None),
        "client_org_id": c.client_org_id,
        "full_name": c.full_name, "email": c.email,
        "job_title": c.job_title, "company": c.company,
        "phone": c.phone,
        "is_active": c.is_active,
        "can_approve_deliverables": c.can_approve_deliverables,
        "can_request_changes": c.can_request_changes,
        "can_view_budget": c.can_view_budget,
        "can_view_team": c.can_view_team,
        "last_login": str(c.last_login)[:16] if c.last_login else None,
        "created_at": str(c.created_at)[:10],
        "portal_url": "/portal",
    } for c in clients]


def create_client(payload, db: Session) -> dict:

    all_project_ids = list(dict.fromkeys([
        *(payload.project_ids or []),
        *([payload.project_id] if payload.project_id else [])
    ]))
    if not all_project_ids and not payload.client_org_id:
        raise ValueError("Debe especificar al menos un proyecto o una empresa cliente")
    if db.query(ClientUser).filter(ClientUser.email == payload.email).first():
        raise ValueError("Ya existe un usuario de portal con ese email")
    company = payload.company
    if payload.client_org_id and not company:
        org = db.query(ClientOrg).filter(ClientOrg.id == payload.client_org_id).first()
        if org:
            company = org.name
    create_data = {k: v for k, v in payload.model_dump().items()
                   if k not in ("password", "company", "project_ids", "project_id")}
    client = ClientUser(
        **create_data,
        project_id=payload.project_id or (all_project_ids[0] if all_project_ids else None),
        company=company,
        hashed_password=hash_password(payload.password),
        avatar_initials=payload.full_name[:2].upper(),
    )
    db.add(client)
    db.flush()
    if all_project_ids:
        for pid in all_project_ids:
            proj = db.query(ProjectModel).filter(ProjectModel.id == pid).first()
            if proj and proj not in client.projects:
                client.projects.append(proj)
    db.commit()
    db.refresh(client)
    return {
        "id": client.id,
        "email": client.email,
        "project_ids": client.get_project_ids(),
        "portal_url": "/portal",
        "message": f"Usuario creado. Puede acceder en /portal con {client.email} y la contraseña indicada."
    }


def update_client(client_id: str, payload: dict, db: Session) -> dict:

    client = db.query(ClientUser).filter(ClientUser.id == client_id).first()
    if not client:
        raise ValueError("Cliente no encontrado")
    allowed = ["full_name", "email", "job_title", "company", "phone", "is_active", "project_id",
               "can_approve_deliverables", "can_request_changes", "can_view_budget", "can_view_team", "language"]
    project_ids_payload = None
    if "project_ids" in payload:
        project_ids_payload = [pid for pid in (payload.get("project_ids") or []) if pid]
    elif "project_id" in payload:
        project_ids_payload = [payload["project_id"]] if payload.get("project_id") else []
    for k, v in payload.items():
        if k in allowed and k != "project_id":
            setattr(client, k, v)
    if "password" in payload:
        client.hashed_password = hash_password(payload["password"])
    if project_ids_payload is not None:
        ordered_ids = list(dict.fromkeys(project_ids_payload))
        client.projects.clear()
        valid_ids = []
        for pid in ordered_ids:
            proj = db.query(ProjectModel).filter(ProjectModel.id == pid).first()
            if proj:
                client.projects.append(proj)
                valid_ids.append(pid)
        client.project_id = valid_ids[0] if valid_ids else None
    db.commit()
    return {"ok": True, "project_ids": client.get_project_ids()}


def delete_client(client_id: str, db: Session) -> dict:

    client = db.query(ClientUser).filter(ClientUser.id == client_id).first()
    if not client:
        raise ValueError("Cliente no encontrado")
    db.delete(client)
    db.commit()
    return {"ok": True}


# ── Auth ──────────────────────────────────────────────────────────────────────

def get_active_client_by_id(db: Session, client_id: str) -> Optional[ClientUser]:
    """Return an active ClientUser by id, or None if not found / inactive."""
    return db.query(ClientUser).filter(ClientUser.id == client_id, ClientUser.is_active == True).first()


def client_login(email: str, password: str, db: Session) -> dict:

    client = db.query(ClientUser).filter(ClientUser.email == email, ClientUser.is_active == True).first()
    if not client or not client.hashed_password:
        raise ValueError("Email o contraseña incorrectos")
    if not verify_password(password, client.hashed_password):
        raise ValueError("Email o contraseña incorrectos")
    client.last_login = datetime.now(timezone.utc)
    db.commit()
    token = create_client_token(client.id)
    project_ids = client.get_project_ids()
    projects = []
    if project_ids:
        projects = [{"id": p.id, "name": p.name, "code": p.code, "status": p.status}
                    for p in db.query(ProjectModel).filter(ProjectModel.id.in_(project_ids)).all()]
    return {
        "token": token,
        "client": {
            "id": client.id, "full_name": client.full_name, "email": client.email,
            "project_id": client.project_id,
            "can_approve_deliverables": client.can_approve_deliverables,
            "can_request_changes": client.can_request_changes,
            "can_view_budget": client.can_view_budget,
            "can_view_team": client.can_view_team,
            "language": client.language,
            "project_ids": project_ids,
            "projects": projects,
        }
    }


def get_me(current_client, db: Session) -> dict:

    project_ids = current_client.get_project_ids()
    projects_info = []
    if project_ids:
        projs = db.query(ProjectModel).filter(ProjectModel.id.in_(project_ids)).all()
        projects_info = [{"id": p.id, "name": p.name, "code": p.code, "status": p.status} for p in projs]
    return {
        "id": current_client.id, "full_name": current_client.full_name,
        "email": current_client.email, "job_title": current_client.job_title,
        "company": current_client.company, "project_id": current_client.project_id,
        "project_ids": project_ids,
        "projects": projects_info,
        "can_approve_deliverables": current_client.can_approve_deliverables,
        "can_request_changes": current_client.can_request_changes,
        "can_view_budget": current_client.can_view_budget,
        "can_view_team": current_client.can_view_team,
        "language": current_client.language,
    }


def get_portal_branding(current_client, db: Session) -> dict:

    cfg = None
    client_name = current_client.company
    if current_client.client_org_id:
        cfg = db.query(ClientPortalConfig).filter(
            ClientPortalConfig.client_id == current_client.client_org_id
        ).first()
        client_org = db.query(Client).filter(Client.id == current_client.client_org_id).first()
        if client_org and client_org.name:
            client_name = client_org.name
    return {
        "brand_name": client_name or "Portal Cliente",
        "logo_url": cfg.logo_url if cfg else None,
        "primary_color": cfg.accent_color if cfg and cfg.accent_color else "#00d4ff",
    }


def update_my_profile(payload: dict, current_client, db: Session, min_password_length: int = 8) -> dict:

    cfg = None
    if current_client.client_org_id:
        cfg = db.query(ClientPortalConfig).filter(
            ClientPortalConfig.client_id == current_client.client_org_id
        ).first()

    allow_edit = cfg.allow_profile_edit if cfg else True
    allow_pwd  = cfg.allow_pwd_change   if cfg else True

    SAFE_FIELDS = {"full_name", "phone", "language", "job_title"}
    has_safe_fields = any(k in SAFE_FIELDS for k in payload if k != "password")
    if not allow_edit and has_safe_fields:
        raise ValueError("Edición de perfil deshabilitada para este portal")
    BLOCKED = {"email", "hashed_password", "can_approve_deliverables",
               "can_request_changes", "can_view_budget", "can_view_team",
               "project_id", "client_org_id", "is_active", "id"}

    for k, v in payload.items():
        if k in BLOCKED:
            continue
        if k == "password":
            if not allow_pwd:
                raise ValueError("El cambio de contraseña está desactivado")
            if len(str(v)) < min_password_length:
                raise ValueError(f"La contraseña debe tener al menos {min_password_length} caracteres")
            current_client.hashed_password = hash_password(str(v))
        elif k in SAFE_FIELDS:
            setattr(current_client, k, v)

    db.commit()
    db.refresh(current_client)
    return {
        "id": current_client.id,
        "full_name": current_client.full_name,
        "email": current_client.email,
        "phone": current_client.phone,
        "job_title": current_client.job_title,
        "language": current_client.language,
        "message": "Perfil actualizado correctamente",
    }


# ── Invoices ──────────────────────────────────────────────────────────────────

def list_client_invoices(status: Optional[str], current_client, db: Session) -> list:

    accessible = current_client.get_project_ids()
    if not accessible:
        return []
    q = db.query(Invoice).filter(Invoice.project_id.in_(accessible))
    if status:
        q = q.filter(Invoice.status == status)
    invoices = q.order_by(Invoice.issue_date.desc()).limit(200).all()
    return [{
        "id": i.id, "number": i.number, "project_id": i.project_id,
        "client_name": i.client_name, "status": i.status.value if hasattr(i.status, "value") else str(i.status),
        "subtotal": i.subtotal, "tax_amount": i.tax_amount, "total": i.total,
        "currency": i.currency,
        "issue_date": str(i.issue_date) if i.issue_date else None,
        "due_date": str(i.due_date) if i.due_date else None,
        "paid_date": str(i.paid_date) if i.paid_date else None,
        "notes": i.notes,
    } for i in invoices]


def approve_client_invoice(invoice_id: str, approved: bool, reason: str, current_client, db: Session) -> dict:

    accessible = current_client.get_project_ids()
    if not accessible:
        raise ValueError("No hay proyectos asignados a este cliente")
    inv = db.query(Invoice).filter(
        Invoice.id == invoice_id,
        Invoice.project_id.in_(accessible),
    ).first()
    if not inv:
        raise ValueError("Factura no encontrada")

    action = "APROBADA" if approved else "RECHAZADA"
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")
    note_line = f"[{stamp}] Cliente {current_client.full_name} ({current_client.email}) {action}."
    if reason:
        note_line += f" Motivo: {reason}"

    existing = (inv.internal_notes or "").strip()
    inv.internal_notes = f"{existing}\n{note_line}".strip() if existing else note_line
    if approved and inv.status == InvoiceStatus.draft:
        inv.status = InvoiceStatus.sent

    db.add(ClientMessage(
        project_id=inv.project_id,
        subject=f"Factura {inv.number} {action.lower()}",
        body=note_line,
        sender_client_id=current_client.id,
        is_read_by_team=False,
        is_read_by_client=True,
    ))
    db.commit()
    return {
        "ok": True, "invoice_id": inv.id, "approved": approved,
        "status": inv.status.value if hasattr(inv.status, "value") else str(inv.status),
    }


# ── Share links ───────────────────────────────────────────────────────────────

def create_public_share_link(project_id: str, db: Session) -> dict:

    project = db.query(ProjectModel).filter(ProjectModel.id == project_id).first()
    if not project:
        raise ValueError("Proyecto no encontrado")
    token = create_portal_share_token(project_id)
    return {
        "ok": True, "token": token,
        "url": f"/portal/view/{token}",
        "expires_in_hours": PORTAL_SHARE_LINK_EXPIRE_HOURS,
    }


def view_public_project_status(token: str, db: Session) -> dict:

    project_id = decode_portal_share_token(token)
    if not project_id:
        raise ValueError("Token inválido o expirado")
    project = db.query(ProjectModel).filter(ProjectModel.id == project_id).first()
    if not project:
        raise ValueError("Proyecto no encontrado")
    milestones = db.query(ProjectMilestone).filter(
        ProjectMilestone.project_id == project.id
    ).order_by(ProjectMilestone.sort_order).all()
    deliverables = db.query(Deliverable).filter(
        Deliverable.project_id == project.id
    ).order_by(Deliverable.sort_order).all()
    return {
        "project": {
            "id": project.id, "code": project.code, "name": project.name,
            "status": project.status,
            "start_date": str(project.start_date) if project.start_date else None,
            "end_date_planned": str(project.end_date_planned) if project.end_date_planned else None,
        },
        "milestones": [{
            "id": m.id, "name": m.name,
            "due_date": str(m.due_date) if m.due_date else None,
            "is_completed": m.is_completed,
        } for m in milestones],
        "deliverables": [{
            "id": d.id, "name": d.name, "status": d.status,
            "planned_date": str(d.planned_date) if d.planned_date else None,
            "delivered_date": str(d.delivered_date) if d.delivered_date else None,
        } for d in deliverables],
    }


# ── Dashboard ─────────────────────────────────────────────────────────────────

_OPEN_TICKET_STATUSES = [
    TicketStatus.new,
    TicketStatus.assigned,
    TicketStatus.in_progress,
    TicketStatus.pending_client,
    TicketStatus.pending_third,
]


def _resolve_dashboard_project(project_id: Optional[str], current_client, db: Session):
    """Resolve which project the dashboard should target.

    Returns a tuple (early_response, project). When early_response is not None,
    the dashboard endpoint must short-circuit and return it directly.
    """
    accessible_ids = current_client.get_project_ids()
    if len(accessible_ids) > 1 and not project_id:
        projs = db.query(ProjectModel).filter(ProjectModel.id.in_(accessible_ids)).all()
        return {
            "needs_project_selection": True,
            "projects": [{"id": p.id, "name": p.name, "code": p.code, "status": p.status} for p in projs],
        }, None
    effective_id = project_id or (accessible_ids[0] if accessible_ids else None)
    if effective_id and accessible_ids and effective_id not in accessible_ids:
        raise ValueError("No tienes acceso a este proyecto")
    if not effective_id:
        return {"project": None, "no_project": True,
                "message": "Este usuario del portal no tiene ningún proyecto asignado."}, None
    project = db.query(ProjectModel).filter(ProjectModel.id == effective_id).first()
    if not project:
        return {"project": None, "no_project": True,
                "message": "El proyecto asignado no existe."}, None
    return None, project


def _dashboard_budget_and_milestones(project, db: Session):
    total_hours = db.query(func.sum(Imputation.hours)).filter(
        Imputation.project_id == project.id
    ).scalar() or 0
    budget_pct = round(total_hours / project.budget_hours * 100, 1) if project.budget_hours else None
    milestones = db.query(ProjectMilestone).filter(
        ProjectMilestone.project_id == project.id
    ).order_by(ProjectMilestone.sort_order).all()
    return total_hours, budget_pct, milestones


def _dashboard_deliverables_and_uat(project, db: Session) -> dict:
    deliverables = db.query(Deliverable).filter(Deliverable.project_id == project.id).all()
    uat_sessions = db.query(UATSession).filter(UATSession.project_id == project.id).all()
    return {
        "deliverables_total": len(deliverables),
        "del_accepted": sum(1 for d in deliverables if d.status == DeliverableStatus.accepted),
        "del_pending_uat": sum(1 for d in deliverables if d.status == DeliverableStatus.delivered),
        "uat_total": len(uat_sessions),
        "uat_passed": sum(1 for s in uat_sessions if s.status in [UATStatus.passed, UATStatus.conditional]),
        "uat_pending": sum(1 for s in uat_sessions if s.status in [UATStatus.pending, UATStatus.in_progress]),
    }


def _dashboard_fr_and_unread(project, db: Session):
    fr_open = db.query(FeatureRequest).filter(
        FeatureRequest.project_id == project.id,
        FeatureRequest.status.in_([
            FeatureRequestStatus.new,
            FeatureRequestStatus.reviewing,
            FeatureRequestStatus.estimated
        ])
    ).count()
    unread = db.query(ClientMessage).filter(
        ClientMessage.project_id == project.id,
        ClientMessage.is_read_by_client == False,
        ClientMessage.sender_client_id == None,
        ClientMessage.is_internal == False,
    ).count()
    return fr_open, unread


def _dashboard_ticket_counts(ticket_query) -> dict:
    return {
        "tickets_open": ticket_query.filter(Ticket.status.in_(_OPEN_TICKET_STATUSES)).count(),
        "tickets_pending_client": ticket_query.filter(Ticket.status == TicketStatus.pending_client).count(),
        "tickets_resolved": ticket_query.filter(
            Ticket.status.in_([TicketStatus.resolved, TicketStatus.closed])
        ).count(),
    }


def _dashboard_sla_stats(project, current_client, ticket_query, db: Session) -> dict:
    avg_first_response_minutes = db.query(func.avg(Ticket.first_response_minutes)).filter(
        Ticket.requester_client_id == current_client.id,
        Ticket.project_id == project.id,
        Ticket.first_response_minutes.isnot(None),
        Ticket.first_response_minutes > 0,
    ).scalar()
    avg_resolution_minutes = db.query(func.avg(Ticket.resolution_minutes)).filter(
        Ticket.requester_client_id == current_client.id,
        Ticket.project_id == project.id,
        Ticket.resolution_minutes.isnot(None),
        Ticket.resolution_minutes > 0,
    ).scalar()
    resolved_ticket_count = ticket_query.filter(
        Ticket.status.in_([TicketStatus.resolved, TicketStatus.closed]),
        Ticket.resolution_minutes.isnot(None),
    ).count()
    breached_ticket_count = ticket_query.filter(
        Ticket.status.in_([TicketStatus.resolved, TicketStatus.closed]),
        Ticket.sla_resolution_breached == True,
    ).count()
    response_breached_open = ticket_query.filter(
        Ticket.status.in_(_OPEN_TICKET_STATUSES),
        Ticket.sla_response_breached == True,
    ).count()
    resolution_breached_open = ticket_query.filter(
        Ticket.status.in_(_OPEN_TICKET_STATUSES),
        Ticket.sla_resolution_breached == True,
    ).count()
    csat_avg = db.query(func.avg(Ticket.csat_score)).filter(
        Ticket.requester_client_id == current_client.id,
        Ticket.project_id == project.id,
        Ticket.csat_score.isnot(None),
    ).scalar()
    sla_compliance_pct = (
        round(((resolved_ticket_count - breached_ticket_count) / resolved_ticket_count) * 100, 1)
        if resolved_ticket_count else None
    )
    return {
        "avg_first_response_minutes": round(float(avg_first_response_minutes), 1) if avg_first_response_minutes is not None else None,
        "avg_resolution_minutes": round(float(avg_resolution_minutes), 1) if avg_resolution_minutes is not None else None,
        "sla_compliance_pct": sla_compliance_pct,
        "response_breached_open": response_breached_open,
        "resolution_breached_open": resolution_breached_open,
        "csat_avg": round(float(csat_avg), 1) if csat_avg is not None else None,
    }


def _dashboard_progress_pct(project) -> float:
    days_elapsed = (date.today() - project.start_date).days if project.start_date else 0
    days_total = (
        (project.end_date_planned - project.start_date).days
        if project.end_date_planned and project.start_date else None
    )
    progress_pct = round(days_elapsed / days_total * 100, 1) if days_total and days_total > 0 else 0
    return min(progress_pct, 100)


def _dashboard_next_milestone(milestones) -> Optional[dict]:
    nm = next((m for m in milestones if not m.is_completed and m.due_date), None)
    if not nm:
        return None
    return {
        "name": nm.name,
        "title": nm.name,
        "due_date": str(nm.due_date),
        "days_remaining": (nm.due_date - date.today()).days,
    }


def get_client_dashboard(project_id: Optional[str], current_client, db: Session) -> dict:
    early, project = _resolve_dashboard_project(project_id, current_client, db)
    if early is not None:
        return early

    total_hours, budget_pct, milestones = _dashboard_budget_and_milestones(project, db)
    milestones_done = sum(1 for m in milestones if m.is_completed)
    del_uat = _dashboard_deliverables_and_uat(project, db)
    fr_open, unread = _dashboard_fr_and_unread(project, db)

    ticket_query = db.query(Ticket).filter(
        Ticket.requester_client_id == current_client.id,
        Ticket.project_id == project.id,
    )
    ticket_counts = _dashboard_ticket_counts(ticket_query)
    sla = _dashboard_sla_stats(project, current_client, ticket_query, db)

    return {
        "project": {
            "id": project.id, "code": project.code, "name": project.name,
            "status": project.status,
            "start_date": str(project.start_date) if project.start_date else None,
            "end_date_planned": str(project.end_date_planned) if project.end_date_planned else None,
            "progress_pct": _dashboard_progress_pct(project),
        },
        "kpis": {
            "budget_hours": project.budget_hours,
            "hours_consumed": round(total_hours, 1),
            "budget_pct": budget_pct,
            "budget_total": project.budget_hours,
            "budget_spent": round(total_hours, 1),
            "milestones_total": len(milestones),
            "milestones_done": milestones_done,
            "deliverables_accepted": del_uat["del_accepted"],
            "deliverables_approved": del_uat["del_accepted"],
            "deliverables_total": del_uat["deliverables_total"],
            "deliverables_pending_uat": del_uat["del_pending_uat"],
            "uat_total": del_uat["uat_total"],
            "uat_passed": del_uat["uat_passed"],
            "uat_pending": del_uat["uat_pending"],
            "feature_requests_open": fr_open,
            "tickets_open": ticket_counts["tickets_open"],
            "tickets_pending_client": ticket_counts["tickets_pending_client"],
            "tickets_resolved": ticket_counts["tickets_resolved"],
            "unread_messages": unread,
        },
        "service_desk": {
            "tickets_open": ticket_counts["tickets_open"],
            "tickets_pending_client": ticket_counts["tickets_pending_client"],
            "tickets_resolved": ticket_counts["tickets_resolved"],
            **sla,
        },
        "next_milestone": _dashboard_next_milestone(milestones),
        "recent_activity": get_recent_activity(project.id, db),
    }


# ── Feature Requests ──────────────────────────────────────────────────────────

def list_feature_requests(status: Optional[str], current_client, db: Session) -> list:

    accessible = current_client.get_project_ids()
    q = db.query(FeatureRequest).filter(
        FeatureRequest.project_id.in_(accessible) if len(accessible) > 1
        else FeatureRequest.project_id == accessible[0] if accessible
        else FeatureRequest.project_id == None
    )
    if status:
        q = q.filter(FeatureRequest.status == status)
    frs = q.order_by(FeatureRequest.submitted_at.desc()).all()
    result = []
    for f in frs:
        item = fr_out(f)
        item["can_edit_by_client"] = f.client_id == current_client.id and str(f.status) in {
            FeatureRequestStatus.new.value, FeatureRequestStatus.reviewing.value,
        }
        result.append(item)
    return result


def list_all_feature_requests(
    project_id: Optional[str], client_id: Optional[str],
    client_org_id: Optional[str], status: Optional[str],
    current_user, db: Session
) -> list:

    q = db.query(FeatureRequest).options(
        joinedload(FeatureRequest.client), joinedload(FeatureRequest.project)
    )
    if getattr(current_user, "organization_id", None) and not getattr(current_user, "is_superadmin", False):
        q = q.filter(FeatureRequest.project.has(ProjectModel.organization_id == current_user.organization_id))
    if project_id:
        q = q.filter(FeatureRequest.project_id == project_id)
    if client_id:
        q = q.filter(FeatureRequest.client_id == client_id)
    if client_org_id:
        q = q.filter(FeatureRequest.client.has(ClientUser.client_org_id == client_org_id))
    if status:
        q = q.filter(FeatureRequest.status == status)
    frs = q.order_by(FeatureRequest.submitted_at.desc()).all()
    result = []
    for f in frs:
        d = fr_out(f)
        d["project_name"] = f.project.name if f.project else "—"
        d["client_name"] = f.client.full_name if f.client else "—"
        result.append(d)
    return result


def create_feature_request(payload, current_client, db: Session) -> dict:
    import re as _re

    if not current_client.can_request_changes:
        raise ValueError("No tienes permisos para solicitar cambios")
    accessible = current_client.get_project_ids()
    target_project_id = getattr(payload, "project_id", None) or (accessible[0] if accessible else None)
    if not target_project_id:
        raise ValueError("No tienes un proyecto asignado para enviar solicitudes")
    if accessible and target_project_id not in accessible:
        raise ValueError("No tienes acceso a ese proyecto")
    max_fr = db.query(func.max(FeatureRequest.code)).filter(
        FeatureRequest.project_id == target_project_id
    ).scalar()
    if max_fr:
        _m = _re.search(r"(\d+)$", max_fr)
        next_fr_num = (int(_m.group(1)) + 1) if _m else 1
    else:
        next_fr_num = 1
    fr_data = payload.model_dump()
    fr_data.pop("project_id", None)
    fr = FeatureRequest(
        code=f"FR-{next_fr_num:03d}",
        project_id=target_project_id,
        client_id=current_client.id,
        **fr_data,
    )
    db.add(fr)
    db.commit()
    db.refresh(fr)
    return fr_out(fr)


def update_feature_request(fr_id: str, payload, current_client, db: Session) -> dict:

    accessible = current_client.get_project_ids()
    fr = db.query(FeatureRequest).filter(
        FeatureRequest.id == fr_id,
        FeatureRequest.client_id == current_client.id,
        FeatureRequest.project_id.in_(accessible) if accessible else FeatureRequest.project_id == None,
    ).first()
    if not fr:
        raise ValueError("FR no encontrada")
    if str(fr.status) not in {FeatureRequestStatus.new.value, FeatureRequestStatus.reviewing.value}:
        raise ValueError("Solo puedes editar solicitudes nuevas o en revisión")
    data = payload.model_dump(exclude_unset=True)
    target_project_id = data.pop("project_id", None)
    if target_project_id is not None:
        if accessible and target_project_id not in accessible:
            raise ValueError("No tienes acceso a ese proyecto")
        fr.project_id = target_project_id
    for key, value in data.items():
        setattr(fr, key, value)
    db.commit()
    db.refresh(fr)
    item = fr_out(fr)
    item["can_edit_by_client"] = True
    return item


def withdraw_feature_request(fr_id: str, reason: Optional[str], current_client, db: Session) -> dict:

    accessible = current_client.get_project_ids()
    fr = db.query(FeatureRequest).filter(
        FeatureRequest.id == fr_id,
        FeatureRequest.client_id == current_client.id,
        FeatureRequest.project_id.in_(accessible) if accessible else FeatureRequest.project_id == None,
    ).first()
    if not fr:
        raise ValueError("FR no encontrada")
    if str(fr.status) not in {FeatureRequestStatus.new.value, FeatureRequestStatus.reviewing.value}:
        raise ValueError("Solo puedes retirar solicitudes nuevas o en revisión")
    fr.status = FeatureRequestStatus.rejected
    fr.client_approved = False
    fr.client_rejection_reason = reason or "Retirada por el cliente desde el portal"
    fr.client_approved_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(fr)
    return fr_out(fr)


def respond_to_fr(fr_id: str, payload, current_user, db: Session) -> dict:

    fr = db.query(FeatureRequest).filter(FeatureRequest.id == fr_id).first()
    if not fr:
        raise ValueError("FR no encontrada")
    if getattr(current_user, "organization_id", None) and not getattr(current_user, "is_superadmin", False):
        project = db.query(ProjectModel).filter(ProjectModel.id == fr.project_id).first()
        if not project or project.organization_id != current_user.organization_id:
            raise ValueError("FR no encontrada")
    if payload.status == "estimated" and not payload.pm_response:
        raise ValueError("pm_response es obligatorio para presupuestar una solicitud")
    data = payload.model_dump(exclude_unset=True, exclude_none=True)
    for k, v in data.items():
        setattr(fr, k, v)
    cr = None
    if fr.change_request_id:
        cr = db.query(ChangeRequest).filter(ChangeRequest.id == fr.change_request_id).first()
        if cr:
            if fr.status == FeatureRequestStatus.in_development:
                cr.status = ChangeRequestStatus.approved
            elif fr.status == FeatureRequestStatus.done:
                cr.status = ChangeRequestStatus.implemented
            elif fr.status == FeatureRequestStatus.rejected:
                cr.status = ChangeRequestStatus.rejected
            db.commit()
    db.commit()
    db.refresh(fr)
    try:
        user_id = str(fr.client_id)
        notif = {
            "type": "cr_state_changed",
            "feature_request_id": fr.id,
            "change_request_id": getattr(fr, "change_request_id", None),
            "fr_status": fr.status,
            "cr_status": cr.status if cr else None,
            "title": fr.title,
            "ts": datetime.now(timezone.utc).isoformat(),
        }
        import asyncio
        asyncio.create_task(publish_user_notification(user_id, notif))
    except Exception as e:
        logger.warning(f"No se pudo enviar notificación WS: {e}")
    return fr_out(fr)


def _next_cr_code(project_id: str, db: Session) -> str:
    import re as _re
    max_cr = db.query(func.max(ChangeRequest.code)).filter(
        ChangeRequest.project_id == project_id
    ).scalar()
    if max_cr:
        _m = _re.search(r"(\d+)$", max_cr)
        next_num = (int(_m.group(1)) + 1) if _m else 1
    else:
        next_num = 1
    return f"CR-{next_num:03d}"


def _create_cr_from_fr(fr, db: Session):
    """Create a ChangeRequest mirroring a FeatureRequest and the matching approval request."""
    import uuid

    cr = ChangeRequest(
        id=str(uuid.uuid4()),
        code=_next_cr_code(fr.project_id, db),
        project_id=fr.project_id,
        title=fr.title,
        description=fr.description,
        justification=fr.business_justification,
        impact=ChangeRequestImpact[fr.priority] if fr.priority else ChangeRequestImpact.medium,
        cost_impact=fr.estimated_cost,
        schedule_impact_days=fr.estimated_delivery_weeks * 7 if fr.estimated_delivery_weeks else None,
        scope_impact=fr.affected_area,
        status=ChangeRequestStatus.submitted,
        submitted_at=datetime.now(timezone.utc),
    )
    db.add(cr)
    db.flush()
    fr.change_request_id = cr.id
    wf = find_default_workflow("change_request", db)
    if wf:
        db.add(ApprovalRequest(
            id=str(uuid.uuid4()),
            workflow_id=wf.id,
            entity_type="change_request",
            entity_id=cr.id,
            entity_summary=cr.title,
            requested_by=None,
            current_step=1,
            status="pending",
        ))
    return cr


def _apply_client_fr_approval(fr, db: Session) -> None:
    """Handle FR approval path: ensure CR exists and mark it approved."""
    fr.status = FeatureRequestStatus.approved
    if not fr.change_request_id:
        cr = _create_cr_from_fr(fr, db)
    else:
        cr = db.query(ChangeRequest).filter(ChangeRequest.id == fr.change_request_id).first()
    if cr:
        cr.status = ChangeRequestStatus.approved
        db.commit()


def _apply_client_fr_rejection(fr, db: Session) -> None:
    """Handle FR rejection path: mark FR rejected and linked CR if any."""
    fr.status = FeatureRequestStatus.rejected
    if fr.change_request_id:
        cr = db.query(ChangeRequest).filter(ChangeRequest.id == fr.change_request_id).first()
        if cr:
            cr.status = ChangeRequestStatus.rejected
            db.commit()


def client_decide_fr(fr_id: str, payload, current_client, db: Session) -> dict:
    accessible = current_client.get_project_ids()
    fr = db.query(FeatureRequest).filter(
        FeatureRequest.id == fr_id,
        FeatureRequest.project_id.in_(accessible) if accessible else FeatureRequest.project_id == None
    ).first()
    if not fr:
        raise ValueError("FR no encontrada")
    if fr.status != FeatureRequestStatus.estimated:
        raise ValueError("Solo se pueden aprobar FRs con estimación del equipo")
    fr.client_approved = payload.approved
    fr.client_approved_at = datetime.now(timezone.utc)
    fr.client_rejection_reason = payload.reason
    if payload.approved:
        _apply_client_fr_approval(fr, db)
    else:
        _apply_client_fr_rejection(fr, db)
    db.commit()
    return fr_out(fr)


# ── UAT ───────────────────────────────────────────────────────────────────────

def list_uat_client(status: Optional[str], current_client, db: Session) -> list:

    q = db.query(UATSession).options(
        joinedload(UATSession.test_cases), joinedload(UATSession.issues)
    ).filter(
        UATSession.project_id.in_(current_client.get_project_ids())
        if current_client.get_project_ids()
        else UATSession.project_id == None
    )
    if status:
        q = q.filter(UATSession.status == status)
    return [uat_out(s) for s in q.order_by(UATSession.created_at.desc()).all()]


def list_uat_team(project_id: Optional[str], db: Session) -> list:

    q = db.query(UATSession).options(
        joinedload(UATSession.test_cases),
        joinedload(UATSession.issues),
        joinedload(UATSession.project)
    )
    if project_id:
        q = q.filter(UATSession.project_id == project_id)
    result = []
    for s in q.order_by(UATSession.created_at.desc()).all():
        d = uat_out(s)
        d["project_name"] = s.project.name if s.project else "—"
        result.append(d)
    return result


def create_uat_for_project(project_id: str, payload, db: Session) -> dict:
    import re as _re

    max_uat = db.query(func.max(UATSession.code)).filter(UATSession.project_id == project_id).scalar()
    if max_uat:
        _m = _re.search(r"(\d+)$", max_uat)
        next_uat_num = (int(_m.group(1)) + 1) if _m else 1
    else:
        next_uat_num = 1
    session = UATSession(project_id=project_id, code=f"UAT-{next_uat_num:03d}", **payload.model_dump())
    db.add(session)
    db.commit()
    db.refresh(session)
    return uat_out(session)


def add_test_case(uat_id: str, payload, db: Session) -> dict:

    tc = UATTestCase(session_id=uat_id, **payload.model_dump())
    db.add(tc)
    db.commit()
    db.refresh(tc)
    return {"id": tc.id, "title": tc.title}


def submit_uat_result(uat_id: str, payload, current_client, db: Session) -> dict:

    session = db.query(UATSession).options(
        joinedload(UATSession.test_cases)
    ).filter(
        UATSession.id == uat_id,
        UATSession.project_id.in_(current_client.get_project_ids())
        if current_client.get_project_ids()
        else UATSession.project_id == None
    ).first()
    if not session:
        raise ValueError("UAT no encontrada")
    session.client_result = payload.result
    session.client_notes = payload.notes
    session.status = UATStatus(payload.result) if payload.result in [s.value for s in UATStatus] else UATStatus.passed
    session.completed_at = datetime.now(timezone.utc)
    session.client_signed_by = current_client.id
    session.client_signed_at = datetime.now(timezone.utc)
    if payload.test_cases:
        for tc_data in payload.test_cases:
            tc = next((t for t in session.test_cases if t.id == tc_data.get("id")), None)
            if tc:
                tc.status = tc_data.get("status", tc.status)
                tc.actual_result = tc_data.get("actual_result", tc.actual_result)
                tc.notes = tc_data.get("notes", tc.notes)
                tc.tested_at = datetime.now(timezone.utc)
    db.commit()
    return uat_out(session)


def report_uat_issue(uat_id: str, payload, current_client, db: Session) -> dict:
    import sqlalchemy as sa

    accessible = current_client.get_project_ids()
    session = db.query(UATSession).filter(
        UATSession.id == uat_id,
        UATSession.project_id.in_(accessible) if accessible else sa.false(),
    ).first()
    if not session:
        raise ValueError("No tienes acceso a esta sesión UAT")
    issue = UATIssue(session_id=uat_id, reported_by=current_client.id, **payload.model_dump())
    db.add(issue)
    db.commit()
    db.refresh(issue)
    return {"id": issue.id, "title": issue.title}


def update_uat_issue(issue_id: str, status: str, current_user, db: Session) -> dict:
    """Actualiza el estado de una incidencia de UAT (equipo interno).

    current_user es OBLIGATORIO: sin acotar por organización, un manager de la
    organización A podía cambiar el estado de una incidencia de la organización B
    conociendo su id (auditoría 2026-08, docs/AUDIT_2026_08_SECOND_PASS.md §7).

    El scoping va por session -> project -> organization, no por
    UATIssue.organization_id: esa columna existe pero NO se rellena al crear la
    incidencia, así que filtrar por ella dejaría fuera todas las filas.
    Mismo criterio que `respond_to_fr`.
    """
    issue = db.query(UATIssue).filter(UATIssue.id == issue_id).first()
    if not issue:
        raise ValueError("Incidencia no encontrada")

    if getattr(current_user, "organization_id", None) and not getattr(current_user, "is_superadmin", False):
        owner_org = (
            db.query(ProjectModel.organization_id)
            .join(UATSession, UATSession.project_id == ProjectModel.id)
            .filter(UATSession.id == issue.session_id)
            .scalar()
        )
        if owner_org and owner_org != current_user.organization_id:
            raise ValueError("Incidencia no encontrada")
    issue.status = status
    if status == "fixed":
        issue.fixed_at = datetime.now(timezone.utc)
    db.commit()
    return {"ok": True}


# ── Messaging ─────────────────────────────────────────────────────────────────

def get_client_messages(thread_id: Optional[str], current_client, db: Session) -> list:

    q = db.query(ClientMessage).options(
        joinedload(ClientMessage.sender_client),
        joinedload(ClientMessage.sender_user),
    ).filter(
        ClientMessage.project_id.in_(current_client.get_project_ids())
        if current_client.get_project_ids()
        else ClientMessage.project_id == None,
        ClientMessage.is_internal == False,
        ClientMessage.parent_id == None,
    )
    if thread_id:
        q = q.filter(ClientMessage.thread_id == thread_id)
    msgs = q.order_by(ClientMessage.created_at.desc()).all()
    _acc = current_client.get_project_ids()
    db.query(ClientMessage).filter(
        ClientMessage.project_id.in_(_acc) if _acc else ClientMessage.project_id == None,
        ClientMessage.sender_user_id != None,
        ClientMessage.is_read_by_client == False,
    ).update({"is_read_by_client": True})
    db.commit()
    result = []
    for m in msgs:
        d = msg_out(m)
        replies = db.query(ClientMessage).options(
            joinedload(ClientMessage.sender_client), joinedload(ClientMessage.sender_user)
        ).filter(ClientMessage.parent_id == m.id).order_by(ClientMessage.created_at).all()
        d["replies"] = [msg_out(r) for r in replies]
        result.append(d)
    return result


def get_team_messages(project_id: str, db: Session) -> list:

    msgs = db.query(ClientMessage).options(
        joinedload(ClientMessage.sender_client),
        joinedload(ClientMessage.sender_user),
    ).filter(
        ClientMessage.project_id == project_id,
        ClientMessage.parent_id == None,
    ).order_by(ClientMessage.created_at.desc()).all()
    db.query(ClientMessage).filter(
        ClientMessage.project_id == project_id,
        ClientMessage.sender_client_id != None,
        ClientMessage.is_read_by_team == False,
    ).update({"is_read_by_team": True})
    db.commit()
    result = []
    for m in msgs:
        d = msg_out(m)
        replies = db.query(ClientMessage).options(
            joinedload(ClientMessage.sender_client), joinedload(ClientMessage.sender_user)
        ).filter(ClientMessage.parent_id == m.id).order_by(ClientMessage.created_at).all()
        d["replies"] = [msg_out(r) for r in replies]
        result.append(d)
    return result


def send_client_message(payload, current_client, db: Session) -> dict:
    import uuid

    accessible = current_client.get_project_ids()
    if not accessible:
        raise ValueError("No hay proyectos asignados a este cliente")
    msg_project_id = (
        payload.project_id if (hasattr(payload, "project_id") and payload.project_id)
        else accessible[0]
    )
    if accessible and msg_project_id and msg_project_id not in accessible:
        raise ValueError("No tienes acceso a ese proyecto")
    msg_data = payload.model_dump(exclude_unset=True)
    msg_data.pop("project_id", None)
    msg = ClientMessage(
        project_id=msg_project_id,
        sender_client_id=current_client.id,
        is_read_by_team=False,
        is_read_by_client=True,
        **msg_data,
    )
    if not msg.thread_id:
        msg.thread_id = str(uuid.uuid4())
    db.add(msg)
    db.commit()
    db.refresh(msg)
    return msg_out(msg)


def send_team_message(payload, current_user, db: Session) -> dict:
    import uuid

    msg = ClientMessage(
        sender_user_id=current_user.id,
        is_read_by_team=True,
        is_read_by_client=False,
        **payload.model_dump(exclude_unset=True),
    )
    if not msg.thread_id:
        msg.thread_id = str(uuid.uuid4())
    db.add(msg)
    db.commit()
    db.refresh(msg)
    return msg_out(msg)


# ── Project info ──────────────────────────────────────────────────────────────

def get_project_info(project_id: Optional[str], current_client, db: Session) -> dict:

    accessible = current_client.get_project_ids()
    if not accessible:
        raise ValueError("No hay proyectos asignados a este cliente")
    effective_id = project_id or accessible[0]
    if accessible and effective_id and effective_id not in accessible:
        raise ValueError("No tienes acceso a ese proyecto")
    project = db.query(ProjectModel).filter(ProjectModel.id == effective_id).first()
    if not project:
        raise ValueError("Proyecto no encontrado")
    milestones = db.query(ProjectMilestone).filter(
        ProjectMilestone.project_id == project.id
    ).order_by(ProjectMilestone.sort_order).all()
    deliverables = db.query(Deliverable).filter(
        Deliverable.project_id == project.id
    ).order_by(Deliverable.sort_order).all()
    total_hours = db.query(func.sum(Imputation.hours)).filter(
        Imputation.project_id == project.id
    ).scalar() or 0
    return {
        "project": {
            "id": project.id, "code": project.code, "name": project.name,
            "description": project.description, "status": project.status,
            "start_date": str(project.start_date) if project.start_date else None,
            "end_date_planned": str(project.end_date_planned) if project.end_date_planned else None,
            "client_name": project.client_name,
        },
        "milestones": [{
            "id": m.id, "name": m.name,
            "due_date": str(m.due_date) if m.due_date else None,
            "is_completed": m.is_completed,
            "completed_date": str(m.completed_date) if m.completed_date else None,
            "billing_pct": m.billing_pct,
        } for m in milestones],
        "deliverables": [{
            "id": d.id, "code": d.code, "name": d.name, "format": d.format,
            "status": d.status,
            "planned_date": str(d.planned_date) if d.planned_date else None,
            "delivered_date": str(d.delivered_date) if d.delivered_date else None,
            "accepted_date": str(d.accepted_date) if d.accepted_date else None,
        } for d in deliverables],
        "budget": {
            "hours_budget": project.budget_hours, "hours_consumed": round(total_hours, 1),
            "pct_consumed": round(total_hours / project.budget_hours * 100, 1) if project.budget_hours else None,
        } if current_client.can_view_budget else None,
    }


# ── Documents ─────────────────────────────────────────────────────────────────

def get_client_documents(project_id: Optional[str], current_client, db: Session) -> list:

    accessible = current_client.get_project_ids()
    if project_id:
        if accessible and project_id not in accessible:
            raise ValueError("No tienes acceso a ese proyecto")
        q = db.query(ClientDocument).filter(ClientDocument.project_id == project_id)
    elif accessible:
        q = db.query(ClientDocument).filter(ClientDocument.project_id.in_(accessible))
    else:
        q = db.query(ClientDocument).filter(ClientDocument.project_id == None)
    docs = q.filter(ClientDocument.is_visible_to_client == True).order_by(ClientDocument.created_at.desc()).all()
    return [doc_out(d) for d in docs]


def get_all_documents(project_id: str, db: Session) -> list:

    docs = db.query(ClientDocument).filter(
        ClientDocument.project_id == project_id
    ).order_by(ClientDocument.created_at.desc()).all()
    return [doc_out(d) for d in docs]


def upload_document(payload, project_id: str, current_user, db: Session) -> dict:

    doc = ClientDocument(project_id=project_id, uploaded_by=current_user.id, **payload.model_dump())
    db.add(doc)
    db.commit()
    db.refresh(doc)
    return doc_out(doc)


def _load_signable_document(doc_id: str, current_client, db: Session):
    _acc = current_client.get_project_ids()
    if not _acc:
        raise ValueError("No hay proyectos asignados a este cliente")
    doc = db.query(ClientDocument).filter(
        ClientDocument.id == doc_id,
        ClientDocument.project_id.in_(_acc)
    ).first()
    if not doc:
        raise ValueError("Documento no encontrado")
    if doc.signed_by_client:
        raise ValueError("El documento ya fue firmado")
    return doc


def _apply_signature_metadata(doc, signer_name: str, signer_job_title: Optional[str], ip: str, now: datetime) -> None:
    doc.signed_by_client    = True
    doc.signed_at           = now
    doc.signed_by_name      = signer_name
    doc.signed_by_job_title = signer_job_title
    doc.signature_ip        = ip


def _resolve_doc_project_name(doc, db: Session) -> str:
    try:
        proj = db.query(ProjectModel).filter(ProjectModel.id == doc.project_id).first()
        if proj:
            return proj.name
    except Exception:
        logger.warning("Failed to resolve project name for portal doc=%s", getattr(doc, "id", None), exc_info=True)
    return "—"


def _generate_and_store_signature_pdf(
    doc, doc_id: str, signer_name: str, signer_email: str, signer_job_title: Optional[str],
    ip: str, signature_pdf_path_root: str, project_name: str, now: datetime,
) -> Optional[str]:
    """Generate the signature PDF, persist it on disk, set doc.signed_pdf_path,
    and return the base64-encoded PDF bytes. Logs (and swallows) generation
    errors but propagates ValueError for explicit invalid-path conditions."""
    try:
        from app.services.signature_pdf import generate_signed_pdf
        from pathlib import Path
        import base64

        pdf_bytes = generate_signed_pdf(
            document_title=doc.title,
            document_description=doc.description or "",
            signer_name=signer_name,
            signer_email=signer_email,
            signer_job_title=signer_job_title or "",
            project_name=project_name,
            signed_at=now,
            signature_ip=ip,
            original_file_name=doc.file_name or "",
        )
        pdf_dir = Path(signature_pdf_path_root)
        pdf_dir.mkdir(parents=True, exist_ok=True)
        pdf_path = (pdf_dir / f"signed_{doc_id}.pdf").resolve()
        if pdf_dir.resolve() not in pdf_path.parents:
            raise ValueError("Ruta de PDF inválida")
        with open(str(pdf_path), "wb") as f:
            f.write(pdf_bytes)
        doc.signed_pdf_path = str(pdf_path)
        return base64.b64encode(pdf_bytes).decode()
    except ValueError:
        raise
    except Exception as e:
        logger.error(f"Error generating PDF signature: {e}", exc_info=True)
        return None


def sign_document(doc_id: str, signer_name: str, signer_email: str, signer_job_title: Optional[str],
                  ip: str, signature_pdf_path_root: str, current_client, db: Session) -> dict:
    doc = _load_signable_document(doc_id, current_client, db)
    now = datetime.now(timezone.utc)
    _apply_signature_metadata(doc, signer_name, signer_job_title, ip, now)
    project_name = _resolve_doc_project_name(doc, db)
    pdf_b64 = _generate_and_store_signature_pdf(
        doc, doc_id, signer_name, signer_email, signer_job_title,
        ip, signature_pdf_path_root, project_name, now,
    )
    db.commit()
    return {"ok": True, "signed_at": str(now)[:16], "signer_name": doc.signed_by_name, "pdf_b64": pdf_b64}


def download_signed_pdf(doc_id: str, current_client, db: Session) -> bytes:
    import os

    _acc = current_client.get_project_ids()
    if not _acc:
        raise ValueError("No hay proyectos asignados a este cliente")
    doc = db.query(ClientDocument).filter(
        ClientDocument.id == doc_id,
        ClientDocument.project_id.in_(_acc),
        ClientDocument.signed_by_client == True
    ).first()
    if not doc:
        raise ValueError("Documento no encontrado")
    if not doc.signed_pdf_path:
        raise ValueError("PDF de firma no disponible")
    if not os.path.exists(doc.signed_pdf_path):
        raise ValueError("Archivo de firma no encontrado en el servidor")
    with open(doc.signed_pdf_path, "rb") as f:
        return f.read(), doc.title


# ── Wiki ──────────────────────────────────────────────────────────────────────

def _portal_visible_wiki_filter(current_client):
    """Condición de tenencia para el wiki visible desde el portal.

    `visibility == "portal"` solo dice que la página es apta para clientes; NO dice
    de QUÉ cliente. Sin acotar además por tenencia, cualquier cliente del portal
    podía listar y leer el wiki de portal de todas las organizaciones
    (auditoría 2026-08, docs/AUDIT_2026_08_SECOND_PASS.md §1).

    Un espacio wiki es o de proyecto o de organización (ver WikiSpace), así que se
    admiten los dos casos y se deniega por defecto todo lo demás.
    """
    accessible = current_client.get_project_ids()
    org_id = getattr(current_client, "organization_id", None)

    clauses = []
    if accessible:
        clauses.append(WikiSpace.project_id.in_(accessible))
    if org_id:
        # Espacio organizacional (sin proyecto) de la propia organización del cliente.
        clauses.append(and_(WikiSpace.project_id.is_(None), WikiSpace.organization_id == org_id))

    if not clauses:
        # Cliente sin proyectos ni organización: no ve nada.
        return false()
    return or_(*clauses)


def portal_wiki_pages(current_client, db: Session) -> list:

    pages = (
        db.query(WikiPage)
        .join(WikiSpace, WikiSpace.id == WikiPage.space_id)
        .filter(
            WikiPage.visibility == "portal",
            WikiPage.is_published == True,
            _portal_visible_wiki_filter(current_client),
        )
        .order_by(WikiPage.title)
        .all()
    )
    return [{"id": p.id, "title": p.title, "slug": p.slug, "space_id": p.space_id,
             "updated_at": str(p.updated_at)} for p in pages]


def portal_wiki_page_detail(page_id: str, current_client, db: Session) -> dict:

    page = (
        db.query(WikiPage)
        .join(WikiSpace, WikiSpace.id == WikiPage.space_id)
        .filter(
            WikiPage.id == page_id,
            WikiPage.visibility == "portal",
            _portal_visible_wiki_filter(current_client),
        )
        .first()
    )
    if not page:
        raise ValueError("Página no encontrada o no visible")
    return {"id": page.id, "title": page.title, "content": page.content,
            "updated_at": str(page.updated_at), "space_id": page.space_id}


# ── Surveys ───────────────────────────────────────────────────────────────────

def get_surveys(current_client, db: Session) -> list:

    surveys = db.query(ClientSurvey).filter(
        ClientSurvey.client_id == current_client.id
    ).order_by(ClientSurvey.sent_at.desc()).all()
    return [survey_out(s) for s in surveys]


def create_survey(project_id: str, client_id: str, title: str, db: Session) -> dict:

    survey = ClientSurvey(project_id=project_id, client_id=client_id, title=title)
    db.add(survey)
    db.commit()
    db.refresh(survey)
    return survey_out(survey)


def respond_survey(survey_id: str, payload, current_client, db: Session) -> dict:

    survey = db.query(ClientSurvey).filter(
        ClientSurvey.id == survey_id, ClientSurvey.client_id == current_client.id
    ).first()
    if not survey:
        raise ValueError("Encuesta no encontrada")
    if survey.status != "pending":
        raise ValueError("Esta encuesta ya ha sido respondida")
    for k, v in payload.model_dump().items():
        setattr(survey, k, v)
    survey.status = "completed"
    survey.completed_at = datetime.now(timezone.utc)
    db.commit()
    return survey_out(survey)


# ── Stats ─────────────────────────────────────────────────────────────────────

def _portal_stats_client_count(project_id: str, db: Session) -> int:
    import sqlalchemy as sa
    legacy_ids = {r[0] for r in db.execute(
        sa.select(ClientUser.id).where(ClientUser.project_id == project_id)
    ).fetchall()}
    m2m_ids = {r[0] for r in db.execute(
        sa.select(client_user_projects.c.client_user_id).where(
            client_user_projects.c.project_id == project_id
        )
    ).fetchall()}
    return len(legacy_ids | m2m_ids)


def _portal_stats_survey_aggregates(surveys) -> dict:
    if not surveys:
        return {"survey_count": 0, "avg_nps": None, "avg_satisfaction": None}
    n = max(len(surveys), 1)
    return {
        "survey_count": len(surveys),
        "avg_nps": round(sum(s.nps_score for s in surveys if s.nps_score) / n, 1),
        "avg_satisfaction": round(
            sum(s.overall_satisfaction for s in surveys if s.overall_satisfaction) / n, 1
        ),
    }


def get_portal_stats(project_id: str, db: Session) -> dict:
    clients = _portal_stats_client_count(project_id, db)
    unread_from_client = db.query(ClientMessage).filter(
        ClientMessage.project_id == project_id,
        ClientMessage.sender_client_id != None,
        ClientMessage.is_read_by_team == False,
    ).count()
    fr_pending = db.query(FeatureRequest).filter(
        FeatureRequest.project_id == project_id,
        FeatureRequest.status.in_(["new", "reviewing"]),
    ).count()
    uat_pending = db.query(UATSession).filter(
        UATSession.project_id == project_id,
        UATSession.status.in_(["pending", "in_progress"]),
    ).count()
    surveys = db.query(ClientSurvey).filter(
        ClientSurvey.project_id == project_id,
        ClientSurvey.status == "completed",
    ).all()
    survey_stats = _portal_stats_survey_aggregates(surveys)
    return {
        "client_count": clients,
        "unread_messages": unread_from_client,
        "fr_pending_review": fr_pending,
        "uat_pending": uat_pending,
        **survey_stats,
    }
