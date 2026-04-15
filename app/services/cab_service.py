"""
cab_service — Business logic extracted from app/api/v1/endpoints/cab.py.

Provides:
  - trigger_out               — serialize WebhookTrigger to dict
  - execute_workflow_from_webhook — background task: enqueue workflow
  - SYSTEM_EMAIL_TEMPLATES    — built-in email templates
  - render_template           — {{variable}} substitution
  - send_email_smtp           — SMTP email dispatch
  - AVAILABLE_WIDGETS         — dashboard widget catalog
  - default_widget_layout     — default layout by role
  - compute_risk_score        — rule-based project risk engine
  - sync_git_commits          — GitHub/GitLab commit sync
  - sync_calendar             — Google Calendar / Outlook sync
  - sync_accounting           — QuickBooks/Xero sync
  - sync_jira                 — Jira bidirectional sync
"""
from __future__ import annotations

import json
import logging
import re
from datetime import date, datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload

from app.core.config import settings
from app.core.secret_utils import decrypt_config_secrets
from app.models.billing_reports import Invoice
from app.models.cab import (
    CalendarEvent, CommitLink, WebhookTrigger, WebhookTriggerLog,
)
from app.models.project import Project
from app.models.resources import ChangeRequest
from app.models.task import Task
from app.models.imputation import Imputation
from app.models.pipeline import Risk

logger = logging.getLogger("clarive.v14")


# ─── WebhookTrigger serializer ────────────────────────────────────────────────

def trigger_out(t: WebhookTrigger) -> dict:
    return {
        "id": t.id, "name": t.name, "slug": t.slug,
        "workflow_id": t.workflow_id,
        "is_active": t.is_active,
        "fire_count": t.fire_count or 0,
        "last_fired_at": str(t.last_fired_at)[:16] if t.last_fired_at else None,
        "endpoint": f"/api/v1/webhooks/fire/{t.slug}",
    }


# ─── Webhook background task ──────────────────────────────────────────────────

def execute_workflow_from_webhook(workflow_id: str, context: dict) -> None:
    """Background task: enqueue workflow triggered by incoming webhook."""
    from app.models.bookings import WorkflowQueueItem
    from app.db.session import SessionLocal
    bg_db = SessionLocal()
    try:
        item = WorkflowQueueItem(
            workflow_id=workflow_id,
            trigger_data=json.dumps(context),
            execute_at=datetime.now(timezone.utc),
            status="pending",
        )
        bg_db.add(item); bg_db.commit()
    except Exception as e:
        bg_db.rollback()
        logger.error(f"Failed to create webhook trigger: {e}", exc_info=True)
    finally:
        bg_db.close()


# ─── Email helpers ────────────────────────────────────────────────────────────

SYSTEM_EMAIL_TEMPLATES = [
    {
        "id": "tpl_task_overdue",
        "name": "Tarea vencida",
        "subject": "[Clarive] Tarea vencida: {{task_title}}",
        "category": "automation",
        "variables": ["task_title", "project_name", "assignee_name", "due_date"],
        "is_system": True,
    },
    {
        "id": "tpl_budget_alert",
        "name": "Alerta de presupuesto",
        "subject": "[Clarive] Alerta presupuesto: {{project_name}} al {{pct_used}}%",
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
        "subject": "[Clarive] SLA vencido: Ticket #{{ticket_number}}",
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
        "subject": "[Clarive] Informe: {{report_name}}",
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
    """
    Send email via SMTP.
    In production: configure SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASS env vars.
    """
    smtp_host = settings.SMTP_HOST
    smtp_user = settings.SMTP_USER

    if smtp_host and smtp_user:
        try:
            import smtplib
            from email.mime.multipart import MIMEMultipart
            from email.mime.text import MIMEText
            smtp_port = settings.SMTP_PORT
            smtp_pass = settings.SMTP_PASS
            sender = settings.SMTP_FROM or smtp_user

            msg = MIMEMultipart("alternative")
            msg["Subject"] = subject
            msg["From"] = sender
            msg["To"] = ", ".join(to)
            if cc: msg["Cc"] = ", ".join(cc)
            msg.attach(MIMEText(body_html, "html", "utf-8"))

            with smtplib.SMTP(smtp_host, smtp_port) as server:
                server.ehlo()
                server.starttls()
                server.login(smtp_user, smtp_pass)
                recipients = to + (cc or [])
                server.sendmail(sender, recipients, msg.as_string())
            return True
        except Exception as e:
            logger.error(f"SMTP error sending email: {e}", exc_info=True)
            return False
    else:
        logger.warning(f"[EMAIL SIMULATED] To: {to} | Subject: {subject}")
        return True


# ─── Dashboard widget helpers ─────────────────────────────────────────────────

AVAILABLE_WIDGETS = [
    {"type": "kpi_hours_week",    "label": "Horas esta semana",          "category": "time",      "default_w": 1, "default_h": 1},
    {"type": "kpi_projects_active","label": "Proyectos activos",          "category": "projects",  "default_w": 1, "default_h": 1},
    {"type": "kpi_tickets_open",  "label": "Tickets abiertos",           "category": "itsm",      "default_w": 1, "default_h": 1},
    {"type": "kpi_budget_health", "label": "Salud presupuesto",          "category": "finance",   "default_w": 1, "default_h": 1},
    {"type": "chart_hours_trend", "label": "Tendencia horas (14d)",      "category": "time",      "default_w": 2, "default_h": 2},
    {"type": "chart_pipeline",    "label": "Pipeline por fase",          "category": "sales",     "default_w": 2, "default_h": 2},
    {"type": "chart_sla",         "label": "SLA compliance (30d)",       "category": "itsm",      "default_w": 2, "default_h": 1},
    {"type": "list_my_tasks",     "label": "Mis tareas pendientes",      "category": "tasks",     "default_w": 2, "default_h": 2},
    {"type": "list_alerts",       "label": "Alertas recientes",          "category": "alerts",    "default_w": 2, "default_h": 1},
    {"type": "list_my_timesheets","label": "Mis imputaciones recientes", "category": "time",      "default_w": 2, "default_h": 1},
    {"type": "calendar_week",     "label": "Calendario semanal",         "category": "calendar",  "default_w": 4, "default_h": 2},
    {"type": "chart_budget_gauge","label": "Gauge presupuesto",          "category": "finance",   "default_w": 1, "default_h": 1},
]


def default_widget_layout(role: str) -> list:
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
        ]


# ─── Project risk scoring ─────────────────────────────────────────────────────

def compute_risk_score(db: Session, project: Project) -> dict:
    """
    Rule-based risk scoring. Returns score components and overall risk level.
    """
    today = date.today()
    score = {}

    # ── Schedule risk ─────────────────────────────────────────────
    schedule_risk = 0
    if project.start_date and project.end_date_planned:
        total_days = (project.end_date_planned - project.start_date).days
        elapsed_days = (today - project.start_date).days
        if total_days > 0:
            time_pct = elapsed_days / total_days * 100
            total_tasks = db.query(func.count(Task.id)).filter(Task.project_id == project.id).scalar() or 1
            done_tasks = db.query(func.count(Task.id)).filter(
                Task.project_id == project.id, Task.status == "done"
            ).scalar() or 0
            completion_pct = done_tasks / total_tasks * 100
            behind_pct = max(time_pct - completion_pct, 0)
            schedule_risk = min(behind_pct * 1.5, 100)
    score["schedule_risk"] = round(schedule_risk, 1)

    # ── Budget risk ───────────────────────────────────────────────
    budget_risk = 0
    if project.budget_amount and project.budget_amount > 0:
        spent = db.query(func.sum(Imputation.hours)).filter(
            Imputation.project_id == project.id
        ).scalar() or 0
        avg_rate = 80
        cost_estimate = spent * avg_rate
        budget_pct = cost_estimate / project.budget_amount * 100
        if budget_pct > 100: budget_risk = min((budget_pct - 100) * 2, 100)
        elif budget_pct > 85: budget_risk = (budget_pct - 85) * 3
    score["budget_risk"] = round(budget_risk, 1)

    # ── Scope risk (open CRs) ────────────────────────────────────
    open_crs = db.query(func.count(ChangeRequest.id)).filter(
        ChangeRequest.project_id == project.id,
        ChangeRequest.status.in_(["submitted", "under_review"]),
    ).scalar() or 0
    score["scope_risk"] = min(open_crs * 20, 100)

    # ── Resource risk (open high-priority risks) ─────────────────
    high_risks = db.query(func.count(Risk.id)).filter(
        Risk.project_id == project.id,
        Risk.status == "open",
        Risk.probability.in_(["high", "very_high"]),
    ).scalar() if hasattr(Risk, 'project_id') else 0
    score["resource_risk"] = min((high_risks or 0) * 25, 100)

    # ── Overloaded members ────────────────────────────────────────
    score["overloaded_members"] = 0

    # ── Overall weighted score ────────────────────────────────────
    overall = (
        score["schedule_risk"] * 0.40 +
        score["budget_risk"] * 0.30 +
        score["scope_risk"] * 0.15 +
        score["resource_risk"] * 0.15
    )
    score["overall_score"] = round(overall, 1)

    level = "critical" if overall >= 75 else "high" if overall >= 50 else "medium" if overall >= 25 else "low"
    score["level"] = level

    delay_prob = min(overall * 0.8, 95)
    score["delay_probability_pct"] = round(delay_prob, 1)
    score["predicted_delay_weeks"] = round(delay_prob / 20, 1) if delay_prob > 20 else None

    if level == "critical":
        score["recommendation"] = "Escalar inmediatamente a dirección. Revisar alcance y recursos."
    elif level == "high":
        score["recommendation"] = "Revisar con el PM en la próxima reunión. Considerar ajuste de fechas."
    elif level == "medium":
        score["recommendation"] = "Monitorizar semanalmente. Resolver CRs pendientes."
    else:
        score["recommendation"] = "Proyecto en buen estado. Mantener ritmo actual."

    return score


# ─── Integration sync helpers ─────────────────────────────────────────────────

def sync_git_commits(db: Session, config, payload: dict):
    """Simulate GitHub/GitLab commit sync."""
    cfg = decrypt_config_secrets(json.loads(config.config or "{}"))
    repo = cfg.get("repo", "org/repo")
    task_pattern = re.compile(r'([A-Z]{2,5}-\d{3}-T\d{3})', re.IGNORECASE)  # noqa: F841

    tasks = db.query(Task).options(joinedload(Task.project)).filter(Task.code != None).limit(5).all()
    synced = 0
    for task in tasks:
        if task.code:
            existing = db.query(CommitLink).filter(
                CommitLink.task_id == task.id,
                CommitLink.external_id == f"demo_{task.code}",
            ).first()
            if not existing:
                db.add(CommitLink(
                    task_id=task.id,
                    integration_id=config.id,
                    link_type="commit",
                    external_id=f"demo_{task.code}",
                    title=f"feat: implement {task.title[:50]}",
                    url=f"https://github.com/{repo}/commit/abc123def456",
                    author="developer@empresa.com",
                    state="merged",
                ))
                synced += 1
    db.flush()
    return synced, []


def sync_calendar(db: Session, config, payload: dict):
    """Simulate Google Calendar / Outlook sync."""
    from app.models.sprints import Sprint
    sprints = db.query(Sprint).filter(
        Sprint.start_date != None,
        Sprint.end_date != None,
    ).limit(10).all()
    synced = 0
    for sprint in sprints:
        external_id = f"clarive_sprint_{sprint.id}"
        existing = db.query(CalendarEvent).filter(
            CalendarEvent.external_id == external_id
        ).first()
        if not existing:
            db.add(CalendarEvent(
                integration_id=config.id,
                external_id=external_id,
                title=f"Sprint: {sprint.name}",
                start_dt=datetime.combine(sprint.start_date, datetime.min.time()),
                end_dt=datetime.combine(sprint.end_date, datetime.min.time()),
                all_day=True,
                sprint_id=sprint.id,
                project_id=sprint.project_id,
                sync_direction="push",
            ))
            synced += 1
    db.flush()
    return synced, []


def sync_accounting(db: Session, config, payload: dict):
    """Simulate QuickBooks/Xero sync."""
    invoices = db.query(Invoice).filter(
        Invoice.status == "sent",
    ).limit(5).all()
    synced = len(invoices)
    return synced, []


def sync_jira(db: Session, config, payload: dict):
    """Sync Jira bidireccional: actualiza estados de tareas con jira_issue_key."""
    from app.services.integrations import get_jira_issue, update_jira_issue

    cfg_dict = decrypt_config_secrets(json.loads(config.config or "{}"))
    tasks_with_jira = db.query(Task).filter(Task.jira_issue_key != None).limit(50).all()

    synced = 0
    errors = []
    STATUS_MAP = {
        "done": "Done", "in_progress": "In Progress",
        "todo": "To Do", "review": "In Review",
    }
    for task in tasks_with_jira:
        result = get_jira_issue(cfg_dict, task.jira_issue_key)
        if result.get("ok"):
            jira_status = result["data"].get("fields", {}).get("status", {}).get("name", "")
            nexus_status = STATUS_MAP.get(str(task.status).lower(), str(task.status))
            if jira_status.lower() != nexus_status.lower():
                update_jira_issue(cfg_dict, task.jira_issue_key, {"summary": task.title})
            synced += 1
        elif "error" in result:
            errors.append(f"{task.jira_issue_key}: {result['error'][:100]}")
    return synced, errors[:5]
