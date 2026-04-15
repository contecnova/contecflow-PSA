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

logger = logging.getLogger("clarive.client_portal")

CLIENT_TOKEN_EXPIRE_HOURS = 72
CLIENT_TOKEN_SECRET = settings.CLIENT_PORTAL_SECRET
PORTAL_SHARE_LINK_EXPIRE_HOURS = 72
ALGORITHM = "HS256"


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
    from app.models.client_portal import ClientMessage
    from app.models.resources import Deliverable, DeliverableStatus

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


def fr_out(fr) -> dict:
    STATUS_LABELS = {
        "new": "Nueva", "reviewing": "En revisión", "estimated": "Presupuestada",
        "approved": "Aprobada", "rejected": "Rechazada",
        "in_development": "En desarrollo", "done": "Completada",
    }
    PRIORITY_LABELS = {"low": "Baja", "medium": "Media", "high": "Alta", "critical": "Crítica"}
    PRIORITY_COLORS = {"low": "#00e5a0", "medium": "#00d4ff", "high": "#ffb800", "critical": "#ff4757"}
    STATUS_COLORS = {
        "new": "#7a8aaa", "reviewing": "#00d4ff", "estimated": "#ffb800",
        "approved": "#00e5a0", "rejected": "#ff4757",
        "in_development": "#7c3aed", "done": "#00e5a0",
    }
    cr_status = cr_status_label = cr_status_color = None
    if getattr(fr, "change_request_id", None):
        from app.models.resources import ChangeRequest
        cr = (
            fr.change_request_id
            and fr.__dict__.get("_sa_instance_state")
            and fr._sa_instance_state.session.query(ChangeRequest).filter(
                ChangeRequest.id == fr.change_request_id
            ).first()
        )
        if cr:
            CR_STATUS_LABELS = {
                "draft": "Borrador", "submitted": "Enviado",
                "under_review": "En revisión", "approved": "Aprobado",
                "rejected": "Rechazado", "implemented": "Implementado",
            }
            CR_STATUS_COLORS = {
                "draft": "#7a8aaa", "submitted": "#00d4ff",
                "under_review": "#ffb800", "approved": "#00e5a0",
                "rejected": "#ff4757", "implemented": "#7c3aed",
            }
            cr_status = cr.status
            cr_status_label = CR_STATUS_LABELS.get(cr.status, cr.status)
            cr_status_color = CR_STATUS_COLORS.get(cr.status, "#7a8aaa")
    return {
        "id": fr.id, "code": fr.code, "project_id": fr.project_id,
        "project_name": fr.project.name if fr.project else "—",
        "client_id": fr.client_id,
        "title": fr.title, "description": fr.description,
        "business_justification": fr.business_justification,
        "affected_area": fr.affected_area,
        "priority": fr.priority,
        "priority_label": PRIORITY_LABELS.get(fr.priority, fr.priority),
        "priority_color": PRIORITY_COLORS.get(fr.priority, "#7a8aaa"),
        "status": fr.status,
        "status_label": STATUS_LABELS.get(fr.status, fr.status),
        "status_color": STATUS_COLORS.get(fr.status, "#7a8aaa"),
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


def uat_out(s) -> dict:
    STATUS_LABELS = {
        "pending": "Pendiente", "in_progress": "En progreso",
        "passed": "Aprobado", "failed": "Rechazado",
        "conditional": "Aprobado con reservas",
    }
    STATUS_COLORS = {
        "pending": "#7a8aaa", "in_progress": "#00d4ff",
        "passed": "#00e5a0", "failed": "#ff4757", "conditional": "#ffb800",
    }
    passed = sum(1 for tc in s.test_cases if tc.status == "passed")
    failed = sum(1 for tc in s.test_cases if tc.status == "failed")
    total = len(s.test_cases)
    return {
        "id": s.id, "code": s.code, "project_id": s.project_id,
        "deliverable_id": s.deliverable_id,
        "title": s.title, "description": s.description,
        "test_environment": s.test_environment,
        "test_credentials": s.test_credentials,
        "test_guide_url": s.test_guide_url,
        "status": s.status,
        "status_label": STATUS_LABELS.get(s.status, s.status),
        "status_color": STATUS_COLORS.get(s.status, "#7a8aaa"),
        "available_from": str(s.available_from) if s.available_from else None,
        "deadline": str(s.deadline) if s.deadline else None,
        "completed_at": str(s.completed_at)[:10] if s.completed_at else None,
        "client_result": s.client_result,
        "client_notes": s.client_notes,
        "test_cases": [
            {
                "id": tc.id, "title": tc.title, "steps": tc.steps,
                "expected_result": tc.expected_result, "actual_result": tc.actual_result,
                "status": tc.status, "notes": tc.notes, "order": tc.order,
            }
            for tc in sorted(s.test_cases, key=lambda x: x.order)
        ],
        "issues": [
            {
                "id": i.id, "title": i.title, "description": i.description,
                "severity": i.severity, "status": i.status,
                "steps_to_reproduce": i.steps_to_reproduce,
            }
            for i in s.issues
        ],
        "stats": {"total": total, "passed": passed, "failed": failed, "pending": total - passed - failed},
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
