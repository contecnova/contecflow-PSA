"""Plantillas de correo del sistema, render, envio y registro de envios.

Parte de `app.services.cab_service` (auditoria 2026-11, #24): se partio por responsabilidad
sin cambiar el codigo. El paquete reexporta todos los nombres.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Optional
from sqlalchemy.orm import Session, joinedload
from app.core.config import settings
from app.models.cab import EmailTemplate
from app.models.cab import EmailLog

from app.services.cab_service._comun import logger


# ─── Email helpers ────────────────────────────────────────────────────────────

SYSTEM_EMAIL_TEMPLATES = [
    {
        "id": "tpl_task_overdue",
        "name": "Tarea vencida",
        "subject": "[Contecflow] Tarea vencida: {{task_title}}",
        "category": "automation",
        "variables": ["task_title", "project_name", "assignee_name", "due_date"],
        "is_system": True,
    },
    {
        "id": "tpl_budget_alert",
        "name": "Alerta de presupuesto",
        "subject": "[Contecflow] Alerta presupuesto: {{project_name}} al {{pct_used}}%",
        "category": "alert",
        "variables": ["project_name", "budget_total", "budget_used", "pct_used"],
        "is_system": True,
    },
    {
        "id": "tpl_invoice_sent",
        "name": "Factura enviada al cliente",
        "subject": "Factura {{invoice_number}} — {{client_name}}",
        "category": "invoice",
        "variables": ["invoice_number", "client_name", "amount", "due_date"],
        "is_system": True,
    },
    {
        "id": "tpl_sla_breach",
        "name": "SLA incumplido",
        "subject": "[Contecflow] SLA vencido: Ticket #{{ticket_number}}",
        "category": "alert",
        "variables": ["ticket_number", "ticket_title", "assignee_name", "sla_due"],
        "is_system": True,
    },
    {
        "id": "tpl_new_ticket",
        "name": "Nuevo ticket asignado",
        "subject": "[Service Desk] Ticket #{{ticket_number}} asignado a ti",
        "category": "automation",
        "variables": ["ticket_number", "ticket_title", "priority", "requester"],
        "is_system": True,
    },
    {
        "id": "tpl_report_ready",
        "name": "Informe programado listo",
        "subject": "[Contecflow] Informe: {{report_name}}",
        "category": "report",
        "variables": ["report_name", "generated_at", "period"],
        "is_system": True,
    },
]


def render_template(template_str: str, variables: dict) -> str:
    """Simple {{variable}} substitution — no Jinja2 required."""
    for key, value in (variables or {}).items():
        template_str = template_str.replace(f"{{{{{key}}}}}", str(value))
    return template_str


def send_email_smtp(to: list, subject: str, body_html: str, cc: list = None) -> bool:
    """Envia el correo por el emisor comun (`notification_service.enviar_correo`).

    Sin `SMTP_HOST`/`SMTP_USER` no envia y devuelve True (modo simulado, como
    siempre). Auditoria 2026-11 (hallazgo 20): ya no abre SMTP aqui.
    """
    if not (settings.SMTP_HOST and settings.SMTP_USER):
        logger.warning(f"[EMAIL SIMULATED] To: {to} | Subject: {subject}")
        return True
    from app.services.notification_service import ServidorSmtp, enviar_correo
    servidor = ServidorSmtp.del_entorno()
    resultado = enviar_correo(to, subject, body_html, cc=cc or None,
                              remitente=servidor.remitente or servidor.user, servidor=servidor)
    if not resultado.enviado:
        logger.error("SMTP error sending email: %s", resultado.error)
    return resultado.enviado


# ─── Email templates + send ───────────────────────────────────────────────────

def list_email_templates(db: Session) -> dict:
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


def create_email_template(payload, current_user_id: str, db: Session) -> dict:
    t = EmailTemplate(
        name=payload.name, subject=payload.subject,
        body_html=payload.body_html, body_text=payload.body_text,
        category=payload.category,
        variables=json.dumps(payload.variables) if payload.variables else None,
        created_by=current_user_id,
    )
    db.add(t); db.commit()
    return {"ok": True, "id": t.id}


def _resolve_email_template(db: Session, template_id: Optional[str], variables: dict,
                             default_subject: str, default_body: str) -> tuple:
    """Resolve template_id to (subject, body_html) using custom DB tpl or system tpl."""
    subject = default_subject
    body_html = default_body
    if not template_id:
        return subject, body_html
    custom_tpl = db.query(EmailTemplate).filter(EmailTemplate.id == template_id).first()
    if custom_tpl:
        subject = render_template(custom_tpl.subject, variables or {})
        body_html = render_template(custom_tpl.body_html, variables or {})
        return subject, body_html
    sys_tpl = next((t for t in SYSTEM_EMAIL_TEMPLATES if t["id"] == template_id), None)
    if sys_tpl:
        subject = render_template(sys_tpl["subject"], variables or {})
        body_html = f"<p>{subject}</p>"
    return subject, body_html


def send_email_action(payload, db: Session) -> dict:
    subject, body_html = _resolve_email_template(
        db, payload.template_id, payload.variables or {},
        payload.subject or "Notificación Contecflow",
        payload.body_html or "<p>Notificación de Contecflow</p>",
    )
    template_id_ref = payload.template_id

    sent = send_email_smtp(payload.to, subject, body_html, payload.cc)

    resolved_template_id = template_id_ref if db.query(EmailTemplate).filter(
        EmailTemplate.id == template_id_ref
    ).first() else None

    for addr in payload.to:
        log = EmailLog(
            to_address=addr,
            cc_addresses=json.dumps(payload.cc) if payload.cc else None,
            subject=subject[:500],
            template_id=resolved_template_id,
            body_preview=body_html[:500],
            status="sent" if sent else "failed",
            sent_at=datetime.now(timezone.utc) if sent else None,
            source=payload.source,
            source_id=payload.source_id,
        )
        db.add(log)
    db.commit()
    return {"ok": True, "sent": sent, "to": payload.to, "subject": subject}


def get_email_logs(limit: int, status: Optional[str], db: Session) -> list:
    q = db.query(EmailLog).order_by(EmailLog.created_at.desc())
    if status:
        q = q.filter(EmailLog.status == status)
    logs = q.limit(limit).all()
    return [{
        "id": l.id, "to": l.to_address, "subject": l.subject[:80],
        "status": l.status, "source": l.source,
        "sent_at": str(l.sent_at)[:16] if l.sent_at else None,
        "created_at": str(l.created_at)[:16] if l.created_at else None,
    } for l in logs]
