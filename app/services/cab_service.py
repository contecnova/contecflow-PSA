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
  - sync_git_commits          — GitHub: pull requests reales
  - sync_calendar             — Google Calendar: sprints como eventos
  - sync_accounting           — QuickBooks/Xero: envio de facturas
  - sync_jira                 — Jira → tareas: estado
"""
from __future__ import annotations

import json
import logging
import re
from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace
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
from app.core.encryption import encrypt_value
from app.core.secret_utils import encrypt_config_secrets
from app.db.session import SessionLocal
from app.models.billing_reports import Invoice as Inv
from app.models.bookings import WorkflowQueueItem
from app.models.cab import CABVote, ChangeRequestWindow
from app.models.cab import MaintenanceWindow
from app.models.cab import EmailTemplate
from app.models.cab import EmailLog
from app.models.cab import GDPRRequest
from app.models.cab import GDPRRequestType, GDPRRequestStatus
from app.models.cab import DashboardWidget
from app.models.cab import OnboardingState
from app.models.cab import IntegrationConfig
from app.models.cab import CalendarEvent as CE
from app.models.cab import CommitLink as CL
from app.models.cab import ProjectRiskScore
from app.models.imputation import Imputation as Imp
from app.models.pipeline import Opportunity as Opp
from app.models.service_desk import Ticket
from app.models.sprints import Sprint
from app.models.user import User as UserModel
from app.services.audit import audit_log
from app.services.integrations import get_jira_issue
from collections import defaultdict
from fastapi import HTTPException
from sqlalchemy import or_ as _or
from app.core import timeutil

logger = logging.getLogger("contecflow.v14")


# ─── WebhookTrigger serializer ────────────────────────────────────────────────

def desactivar_integracion(db, integration_id: str) -> dict:
    """Desactiva una integracion OAuth. Es el boton de borrar de la interfaz.

    Auditoria 2026-08 (hallazgo 37): `DELETE /oauth-integrations/{id}` **no
    existia** — habia `GET` y `POST`, asi que se podia configurar una
    integracion y no quitarla.

    **No borra la fila**: `IntegrationConfig` tiene `is_active`, que es la
    convencion de borrado logico de este repositorio, y la fila guarda el
    historial de sincronizacion (`last_sync_at`, `sync_errors`, `last_error`)
    que sirve para diagnosticar. Se desactiva y **se borran los tokens**, que es
    lo que de verdad hay que quitar: dejar un `access_token` de un tercero en
    una fila desactivada es guardar una credencial que ya no se usa.
    """
    from fastapi import HTTPException

    fila = (
        db.query(IntegrationConfig)
        .filter(IntegrationConfig.id == integration_id)
        .first()
    )
    if not fila:
        raise HTTPException(404, "Integración no encontrada")

    fila.is_active = False
    fila.access_token = None
    fila.refresh_token = None
    fila.token_expires_at = None
    db.commit()
    return {"ok": True, "id": integration_id, "deactivated": True}


def trigger_out(t: WebhookTrigger) -> dict:
    return {
        "id": t.id, "name": t.name, "slug": t.slug,
        "workflow_id": t.workflow_id,
        "is_active": t.is_active,
        "fire_count": t.fire_count or 0,
        "last_fired_at": str(t.last_fired_at)[:16] if t.last_fired_at else None,
        "slug_rotated_at": str(t.slug_rotated_at)[:19] if t.slug_rotated_at else None,
        "slug_expires_at": str(t.slug_expires_at)[:19] if t.slug_expires_at else None,
        "endpoint": f"/api/v1/webhooks/fire/{t.slug}",
    }


# ─── Webhook background task ──────────────────────────────────────────────────

def execute_workflow_from_webhook(workflow_id: str, context: dict) -> None:
    """Background task: enqueue workflow triggered by incoming webhook."""
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

_CLAVES_DE_RIESGO = {
    "RISK_WEIGHT_SCHEDULE": "float", "RISK_WEIGHT_BUDGET": "float",
    "RISK_WEIGHT_SCOPE": "float", "RISK_WEIGHT_RESOURCE": "float",
    "RISK_LEVEL_CRITICAL": "float", "RISK_LEVEL_HIGH": "float", "RISK_LEVEL_MEDIUM": "float",
    "RISK_SCHEDULE_FACTOR": "float", "RISK_BUDGET_WARN_PCT": "float",
    "RISK_BUDGET_WARN_FACTOR": "float", "RISK_BUDGET_OVER_FACTOR": "float",
    "RISK_POINTS_PER_OPEN_CR": "float", "RISK_POINTS_PER_HIGH_RISK": "float",
    "RISK_DELAY_FACTOR": "float", "RISK_DELAY_MAX_PCT": "float", "RISK_DELAY_PCT_PER_WEEK": "float",
    "RISK_CACHE_MINUTES": "int", "RISK_HISTORY_POINTS": "int",
}


def _ajustes_de_riesgo(db: Session, org_id=None) -> SimpleNamespace:
    """Pesos y umbrales de la puntuacion (Admin → Ajustes → risk; si no, `.env`).

    Revision 2026-11: estaban escritos en las funciones de abajo. Se leen una
    vez por calculo, no una por regla.
    """
    from app.services.settings_service import get_runtime_namespace
    leidos = get_runtime_namespace(db, _CLAVES_DE_RIESGO, org_id)
    return SimpleNamespace(**{
        k: (getattr(leidos, k, None) if getattr(leidos, k, None) is not None else getattr(settings, k))
        for k in _CLAVES_DE_RIESGO})

def _risk_schedule(db: Session, project: Project, today: date, aj=None) -> float:
    """Compute schedule risk component (0-100)."""
    if not (project.start_date and project.end_date_planned):
        return 0.0
    total_days = (project.end_date_planned - project.start_date).days
    elapsed_days = (today - project.start_date).days
    if total_days <= 0:
        return 0.0
    time_pct = elapsed_days / total_days * 100
    total_tasks = db.query(func.count(Task.id)).filter(Task.project_id == project.id).scalar() or 1
    done_tasks = db.query(func.count(Task.id)).filter(
        Task.project_id == project.id, Task.status == "done"
    ).scalar() or 0
    completion_pct = done_tasks / total_tasks * 100
    behind_pct = max(time_pct - completion_pct, 0)
    aj = aj or _ajustes_de_riesgo(db, project.organization_id)
    return min(behind_pct * aj.RISK_SCHEDULE_FACTOR, 100)


def _risk_budget(db: Session, project: Project, aj=None) -> float:
    """Compute budget risk component (0-100)."""
    if not (project.budget_amount and project.budget_amount > 0):
        return 0.0
    # Coste interno real (antes horas × 80 €/h escrito aqui).
    from app.services.ml_features import coste_real
    budget_pct = coste_real(db, project.id) / project.budget_amount * 100
    aj = aj or _ajustes_de_riesgo(db, project.organization_id)
    if budget_pct > 100:
        return min((budget_pct - 100) * aj.RISK_BUDGET_OVER_FACTOR, 100)
    if budget_pct > aj.RISK_BUDGET_WARN_PCT:
        return min((budget_pct - aj.RISK_BUDGET_WARN_PCT) * aj.RISK_BUDGET_WARN_FACTOR, 100)
    return 0.0


def _risk_scope(db: Session, project: Project, aj=None) -> float:
    """Compute scope risk (open CRs)."""
    open_crs = db.query(func.count(ChangeRequest.id)).filter(
        ChangeRequest.project_id == project.id,
        ChangeRequest.status.in_(["submitted", "under_review"]),
    ).scalar() or 0
    aj = aj or _ajustes_de_riesgo(db, project.organization_id)
    return min(open_crs * aj.RISK_POINTS_PER_OPEN_CR, 100)


def _risk_resource(db: Session, project: Project, aj=None) -> float:
    """Compute resource risk (open high-priority risks)."""
    high_risks = db.query(func.count(Risk.id)).filter(
        Risk.project_id == project.id,
        Risk.status.in_(["identified", "analyzing", "mitigating", "monitoring"]),
        Risk.probability.in_(["high", "very_high"]),
    ).scalar() if hasattr(Risk, 'project_id') else 0
    aj = aj or _ajustes_de_riesgo(db, project.organization_id)
    return min((high_risks or 0) * aj.RISK_POINTS_PER_HIGH_RISK, 100)


def _risk_recommendation(level: str) -> str:
    """Return human-readable recommendation for a risk level."""
    if level == "critical":
        return "Escalar inmediatamente a dirección. Revisar alcance y recursos."
    if level == "high":
        return "Revisar con el PM en la próxima reunión. Considerar ajuste de fechas."
    if level == "medium":
        return "Monitorizar semanalmente. Resolver CRs pendientes."
    return "Proyecto en buen estado. Mantener ritmo actual."


def compute_risk_score(db: Session, project: Project) -> dict:
    from app.services.ml_features import carga_del_equipo
    """
    Rule-based risk scoring. Returns score components and overall risk level.
    """
    today = timeutil.today()
    aj = _ajustes_de_riesgo(db, project.organization_id)
    score = {
        "schedule_risk": round(_risk_schedule(db, project, today, aj), 1),
        "budget_risk": round(_risk_budget(db, project, aj), 1),
        "scope_risk": _risk_scope(db, project, aj),
        "resource_risk": _risk_resource(db, project, aj),
        # Antes siempre 0: quienes imputan al proyecto y pasan de su capacidad.
        "overloaded_members": carga_del_equipo(db, project.id, today)["overloaded_members"],
    }

    overall = (
        score["schedule_risk"] * aj.RISK_WEIGHT_SCHEDULE +
        score["budget_risk"] * aj.RISK_WEIGHT_BUDGET +
        score["scope_risk"] * aj.RISK_WEIGHT_SCOPE +
        score["resource_risk"] * aj.RISK_WEIGHT_RESOURCE
    )
    score["overall_score"] = round(overall, 1)

    level = ("critical" if overall >= aj.RISK_LEVEL_CRITICAL else "high" if overall >= aj.RISK_LEVEL_HIGH
             else "medium" if overall >= aj.RISK_LEVEL_MEDIUM else "low")
    score["level"] = level

    delay_prob = min(overall * aj.RISK_DELAY_FACTOR, aj.RISK_DELAY_MAX_PCT)
    por_semana = aj.RISK_DELAY_PCT_PER_WEEK or 1
    score["delay_probability_pct"] = round(delay_prob, 1)
    score["predicted_delay_weeks"] = round(delay_prob / por_semana, 1) if delay_prob > por_semana else None
    score["recommendation"] = _risk_recommendation(level)

    return score


# ─── Integration sync helpers ─────────────────────────────────────────────────

# Revision 2026-11: `sync_git_commits`, `sync_calendar` y `sync_accounting`
# eran simulaciones: creaban enlaces a commits inventados
# («abc123def456», «developer@empresa.com») en las cinco primeras tareas,
# eventos de calendario que no se enviaban a ningun sitio y una cuenta de
# facturas que no se mandaban. `sync_jira` reescribia el titulo y nunca traia
# el estado. Ahora cada una llama al servicio de verdad, o dice que no puede.

def _config_de(config) -> dict:
    """La configuracion de la integracion, con sus secretos descifrados."""
    from app.core.encryption import decrypt_value
    cfg = decrypt_config_secrets(json.loads(config.config or "{}"))
    if not cfg.get("access_token") and config.access_token:
        cfg["access_token"] = decrypt_value(config.access_token) or config.access_token
    return cfg


def _espera(db: Session) -> float:
    from app.services.settings_service import outbound_http_timeout
    return outbound_http_timeout(db)


def sync_git_commits(db: Session, config, payload: dict):
    """GitHub: trae los pull requests del repositorio y los procesa como el webhook."""
    import httpx
    from app.services.git_service import handle_github_pr
    if config.integration_type != "github":
        return 0, ["GitLab se integra por webhook: Configuración → Git."]
    cfg = _config_de(config)
    repo, token = (cfg.get("repo") or "").strip(), cfg.get("access_token")
    if not repo or not token:
        return 0, ["Faltan el repositorio (owner/repo) o el token."]
    try:
        r = httpx.get(f"https://api.github.com/repos/{repo}/pulls",
                      params={"state": "all", "per_page": 50},
                      headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"},
                      timeout=_espera(db))
    except httpx.HTTPError as exc:
        return 0, [f"GitHub: {exc}"[:200]]
    if r.status_code != 200:
        return 0, [f"GitHub {r.status_code}: {r.text[:150]}"]
    synced = 0
    for pr in r.json():
        pr = dict(pr, merged=bool(pr.get("merged_at")))
        handle_github_pr(db, {"action": "closed" if pr.get("closed_at") else "opened",
                              "pull_request": pr, "repository": {"full_name": repo}})
        synced += 1
    db.flush()
    return synced, []


def sync_calendar(db: Session, config, payload: dict):
    """Google Calendar: publica los sprints con fechas como eventos de dia completo.

    Cada evento se recuerda por su id de Google: la siguiente vez se actualiza
    en vez de duplicarse.
    """
    import httpx
    if config.integration_type != "google_calendar":
        return 0, ["Outlook se integra con Microsoft 365: Configuración → Microsoft 365."]
    cfg = _config_de(config)
    calendario, token = (cfg.get("calendar_id") or "primary").strip(), cfg.get("access_token")
    if not token:
        return 0, ["Falta el token de acceso de Google."]
    base = f"https://www.googleapis.com/calendar/v3/calendars/{calendario}/events"
    cabeceras = {"Authorization": f"Bearer {token}"}
    sprints = db.query(Sprint).filter(Sprint.start_date != None, Sprint.end_date != None).all()
    ya = {e.sprint_id: e for e in db.query(CalendarEvent).filter(
        CalendarEvent.integration_id == config.id, CalendarEvent.sprint_id != None).all()}
    synced, errors = 0, []
    for sprint in sprints:
        cuerpo = {"summary": f"Sprint: {sprint.name}",
                  "start": {"date": sprint.start_date.isoformat()},
                  "end": {"date": (sprint.end_date + timedelta(days=1)).isoformat()}}
        previo = ya.get(sprint.id)
        try:
            if previo:
                r = httpx.put(f"{base}/{previo.external_id}", json=cuerpo, headers=cabeceras, timeout=_espera(db))
            else:
                r = httpx.post(base, json=cuerpo, headers=cabeceras, timeout=_espera(db))
        except httpx.HTTPError as exc:
            errors.append(f"Google: {exc}"[:200])
            continue
        if r.status_code not in (200, 201):
            errors.append(f"Google {r.status_code}: {r.text[:150]}")
            continue
        if previo is None:
            db.add(CalendarEvent(
                integration_id=config.id, external_id=r.json().get("id"),
                title=cuerpo["summary"], all_day=True, sprint_id=sprint.id, project_id=sprint.project_id,
                start_dt=datetime.combine(sprint.start_date, datetime.min.time()),
                end_dt=datetime.combine(sprint.end_date, datetime.min.time()),
                sync_direction="push",
            ))
        synced += 1
    db.flush()
    return synced, errors


def sync_accounting(db: Session, config, payload: dict):
    """Xero / QuickBooks: envia las facturas pendientes (lo mismo que Contabilidad)."""
    from app.services.accounting_hub_service import enviar_facturas_pendientes
    filas = enviar_facturas_pendientes(db, config.integration_type, _config_de(config))
    errores = [f"{f['invoice_number']}: {f.get('error')}"[:200] for f in filas if f["status"] == "error"]
    return sum(1 for f in filas if f["status"] == "synced"), errores


_ESTADO_DESDE_JIRA = {"done": "done", "in progress": "in_progress", "to do": "todo", "in review": "in_review"}


def sync_jira(db: Session, config, payload: dict):
    """Jira → Contecflow: el estado de cada incidencia enlazada pasa a su tarea."""
    cfg_dict = _config_de(config)
    synced, errors = 0, []
    for task in db.query(Task).filter(Task.jira_issue_key != None).limit(200).all():
        result = get_jira_issue(cfg_dict, task.jira_issue_key)
        if not result.get("ok"):
            errors.append(f"{task.jira_issue_key}: {str(result.get('error', ''))[:100]}")
            continue
        nombre = (result["data"].get("fields", {}).get("status", {}).get("name") or "").lower()
        nuevo = _ESTADO_DESDE_JIRA.get(nombre)
        if nuevo and str(getattr(task.status, "value", task.status)) != nuevo:
            task.status = nuevo
        synced += 1
    db.flush()
    return synced, errors[:5]


# ─── CAB Vote helpers ─────────────────────────────────────────────────────────

def get_cab_pending_changes(db: Session, current_user_id: str) -> list:
    crs = db.query(ChangeRequest).options(
        joinedload(ChangeRequest.project),
        joinedload(ChangeRequest.requester),
    ).filter(
        ChangeRequest.status.in_(["submitted", "under_review"])
    ).order_by(ChangeRequest.created_at.desc()).all()

    cr_ids = [cr.id for cr in crs]
    if cr_ids:
        all_votes = db.query(CABVote).filter(CABVote.change_request_id.in_(cr_ids)).all()
        all_windows = db.query(ChangeRequestWindow).filter(
            ChangeRequestWindow.change_request_id.in_(cr_ids)
        ).all()
    else:
        all_votes, all_windows = [], []

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
        my_vote = next((v.vote for v in votes if v.voter_id == current_user_id), None)
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


def cast_cab_vote(cr_id: str, vote: str, comment: Optional[str], current_user, db: Session) -> dict:
    cr = db.query(ChangeRequest).filter(ChangeRequest.id == cr_id).first()
    if not cr:
        raise ValueError("CR no encontrada")
    if cr.status not in ["submitted", "under_review"]:
        raise ValueError(f"No se puede votar en estado '{cr.status}'")
    if vote not in ["approve", "reject", "abstain"]:
        raise ValueError("Voto debe ser: approve, reject o abstain")

    existing = db.query(CABVote).filter(
        CABVote.change_request_id == cr_id,
        CABVote.voter_id == current_user.id,
    ).first()
    if existing:
        existing.vote = vote
        existing.comment = comment
    else:
        db.add(CABVote(
            change_request_id=cr_id,
            voter_id=current_user.id,
            vote=vote,
            comment=comment,
        ))

    if cr.status == "submitted":
        cr.status = "under_review"

    audit_log(db, current_user, "CAB_VOTE", "change_requests", cr_id, cr.code,
              new_values={"vote": vote})
    db.commit()

    votes = db.query(CABVote).filter(CABVote.change_request_id == cr_id).all()
    approvals = sum(1 for v in votes if v.vote == "approve")
    rejections = sum(1 for v in votes if v.vote == "reject")
    return {"ok": True, "vote": vote, "approvals": approvals, "rejections": rejections}


def close_cab_vote(cr_id: str, decision: str, reason: Optional[str], current_user, db: Session) -> dict:
    cr = db.query(ChangeRequest).filter(ChangeRequest.id == cr_id).first()
    if not cr:
        raise ValueError("CR no encontrada")
    if decision not in ["approved", "rejected"]:
        raise ValueError("decision debe ser approved o rejected")
    # Revisión 2026-11: sólo se cierra una votación abierta, y una decisión que
    # va contra el recuento (o con empate) necesita su motivo, que queda auditado.
    estado = str(getattr(cr.status, "value", cr.status))
    if estado not in ("submitted", "under_review"):
        raise ValueError(f"Sólo se cierra una votación abierta; esta CR está «{estado}»")
    votos = [v.vote for v in db.query(CABVote).filter(CABVote.change_request_id == cr_id).all()]
    a_favor, en_contra = votos.count("approve"), votos.count("reject")
    mayoria = "approved" if a_favor > en_contra else "rejected" if en_contra > a_favor else None
    if decision != mayoria and not (reason or "").strip():
        raise ValueError(f"La decisión no sigue la votación ({a_favor} a favor, {en_contra} en contra): indica el motivo")
    cr.status = decision
    audit_log(db, current_user, "CAB_CLOSE", "change_requests", cr_id, cr.code,
              new_values={"decision": decision, "reason": reason, "a_favor": a_favor, "en_contra": en_contra})
    db.commit()
    return {"ok": True, "new_status": cr.status}


# ─── Maintenance windows ──────────────────────────────────────────────────────

def list_maintenance_windows(upcoming_only: bool, db: Session) -> list:
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


def create_maintenance_window(payload, current_user_id: str, db: Session) -> dict:
    w = MaintenanceWindow(**payload.model_dump(), created_by=current_user_id)
    db.add(w); db.commit(); db.refresh(w)
    return {"ok": True, "id": w.id}


def schedule_cr_in_window(cr_id: str, window_id: str, rollback_plan: Optional[str], test_plan: Optional[str], db: Session) -> dict:
    cr = db.query(ChangeRequest).filter(ChangeRequest.id == cr_id).first()
    if not cr:
        raise ValueError("CR no encontrada")
    if not db.query(MaintenanceWindow).filter(MaintenanceWindow.id == window_id).first():
        raise ValueError("Ventana de mantenimiento no encontrada")
    crw = ChangeRequestWindow(
        change_request_id=cr_id,
        window_id=window_id,
        rollback_plan=rollback_plan,
        test_plan=test_plan,
    )
    db.add(crw); db.commit()
    return {"ok": True}


# ─── Webhook CRUD ─────────────────────────────────────────────────────────────

def list_webhook_triggers(db: Session) -> list:
    triggers = db.query(WebhookTrigger).options(joinedload(WebhookTrigger.workflow)).all()
    return [trigger_out(t) for t in triggers]


def create_webhook_trigger(payload, current_user_id: str, db: Session) -> dict:
    import secrets as _secrets
    existing = db.query(WebhookTrigger).filter(WebhookTrigger.slug == payload.slug).first()
    if existing:
        raise ValueError(f"Slug '{payload.slug}' ya está en uso")
    secret = payload.secret or _secrets.token_hex(32)
    t = WebhookTrigger(
        name=payload.name, slug=payload.slug,
        secret=secret,
        workflow_id=payload.workflow_id,
        rule_id=payload.rule_id,
        field_mapping=json.dumps(payload.field_mapping) if payload.field_mapping else None,
        created_by=current_user_id,
    )
    db.add(t); db.commit()
    return {"ok": True, "id": t.id, "secret": secret,
            "endpoint": f"/api/v1/webhooks/fire/{t.slug}"}


def log_webhook_fire(trigger, payload_str: str, headers_str: str, db: Session) -> None:
    log = WebhookTriggerLog(
        trigger_id=trigger.id,
        payload=payload_str[:2000],
        headers=headers_str[:1000],
        status="ok",
    )
    db.add(log)
    trigger.fire_count = (trigger.fire_count or 0) + 1
    trigger.last_fired_at = datetime.now(timezone.utc)
    db.commit()


def get_active_webhook_trigger_by_slug(db: Session, slug: str) -> WebhookTrigger:
    trigger = db.query(WebhookTrigger).filter(
        WebhookTrigger.slug == slug,
        WebhookTrigger.is_active == True,
    ).first()
    if not trigger:
        raise HTTPException(404, "Webhook trigger no encontrado")
    if trigger.slug_expires_at and trigger.slug_expires_at < datetime.now(timezone.utc):
        raise HTTPException(410, "Webhook trigger slug expirado — rota el slug para reactivarlo")
    return trigger


def rotate_webhook_trigger_slug(trigger_id: str, expires_in_days: int | None, db: Session) -> dict:
    """Generate a new random slug for the trigger, invalidating the old one immediately.

    expires_in_days: if provided, sets slug_expires_at that many days from now.
                     Pass None (or omit) for a non-expiring slug.
    """
    import secrets as _secrets
    t = db.query(WebhookTrigger).filter(WebhookTrigger.id == trigger_id).first()
    if not t:
        raise ValueError("Trigger no encontrado")
    new_slug = _secrets.token_urlsafe(16)
    # Ensure uniqueness (collision extremely unlikely but guard anyway)
    while db.query(WebhookTrigger).filter(WebhookTrigger.slug == new_slug).first():
        new_slug = _secrets.token_urlsafe(16)
    t.slug = new_slug
    t.slug_rotated_at = datetime.now(timezone.utc)
    if expires_in_days is not None:
        from datetime import timedelta
        t.slug_expires_at = t.slug_rotated_at + timedelta(days=expires_in_days)
    else:
        t.slug_expires_at = None
    db.commit()
    return {
        "ok": True, "id": t.id, "slug": t.slug,
        "slug_rotated_at": str(t.slug_rotated_at)[:19],
        "slug_expires_at": str(t.slug_expires_at)[:19] if t.slug_expires_at else None,
        "endpoint": f"/api/v1/webhooks/fire/{t.slug}",
    }


def get_webhook_logs(trigger_id: str, db: Session) -> list:
    logs = db.query(WebhookTriggerLog).filter(
        WebhookTriggerLog.trigger_id == trigger_id
    ).order_by(WebhookTriggerLog.received_at.desc()).limit(50).all()
    return [{
        "id": l.id, "status": l.status, "error": l.error,
        "received_at": str(l.received_at)[:16],
        "payload_preview": (l.payload or "")[:200],
    } for l in logs]


def delete_webhook_trigger(trigger_id: str, db: Session) -> dict:
    t = db.query(WebhookTrigger).filter(WebhookTrigger.id == trigger_id).first()
    if not t:
        raise ValueError("Trigger no encontrado")
    db.delete(t); db.commit()
    return {"ok": True}


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


# ─── GDPR ─────────────────────────────────────────────────────────────────────

def list_gdpr_requests(db: Session) -> list:
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


def create_gdpr_request(payload, current_user, db: Session) -> dict:
    deadline = timeutil.today() + timedelta(days=30)
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


def _gdpr_erase_user(db: Session, user) -> dict:
    """Supresión de una persona (el mismo borrado que Gobierno del dato). No guarda su correo original."""
    from app.services.supresion_service import suprimir_persona
    detalle = suprimir_persona(db, user)
    return {"anonymised": True, "tablas": detalle["tablas"], "credenciales": detalle["credenciales"],
            "almacen": detalle["almacen"], "records_kept": ["imputations", "timesheets", "expenses"]}


def _gdpr_portability_export(db: Session, user) -> dict:
    """Build a portability export payload for a user."""
    imputations = db.query(Imp).filter(Imp.user_id == user.id).count()
    return {
        "user": {
            "email": user.email, "full_name": user.full_name,
            "username": user.username, "role": user.role,
            "department": user.department,
            "created_at": str(user.created_at)[:10] if user.created_at else None,
        },
        "data_summary": {"imputations": imputations},
        "export_date": str(timeutil.today()),
        "format": "JSON",
        "note": "Solicite el fichero completo al administrador del sistema.",
    }


def process_gdpr_request(request_id: str, current_user, db: Session) -> dict:
    req = db.query(GDPRRequest).filter(GDPRRequest.id == request_id).first()
    if not req:
        raise ValueError("Solicitud no encontrada")
    if req.status == GDPRRequestStatus.completed:
        raise ValueError("Solicitud ya procesada")

    req.status = GDPRRequestStatus.processing
    req.processed_by = current_user.id
    db.commit()

    user = db.query(UserModel).filter(UserModel.id == req.subject_user_id).first() if req.subject_user_id else None
    export_data: dict = {}

    if req.request_type == GDPRRequestType.erasure and user:
        export_data = _gdpr_erase_user(db, user)
    elif req.request_type == GDPRRequestType.portability and user:
        export_data = _gdpr_portability_export(db, user)

    req.status = GDPRRequestStatus.completed
    req.completed_at = datetime.now(timezone.utc)
    req.export_data = json.dumps(export_data)
    audit_log(db, current_user, "GDPR_PROCESS", "users",
              req.subject_user_id or "unknown", "",
              new_values={"type": req.request_type, "result": req.status})
    db.commit()
    return {"ok": True, "status": req.status, "data": export_data}


# ─── Global Search ────────────────────────────────────────────────────────────

def _search_projects(db: Session, q_lower: str, limit: int) -> list:
    projects = db.query(Project).filter(
        _or(
            func.lower(Project.name).like(q_lower),
            func.lower(Project.code).like(q_lower),
            func.lower(Project.client_name).like(q_lower),
        )
    ).limit(limit).all()
    return [{
        "id": p.id, "type": "project",
        "title": p.name, "subtitle": f"{p.code} · {p.client_name or '—'}",
        "status": p.status, "url": "/projects",
        "icon": "⬡",
    } for p in projects]


def _search_tasks(db: Session, q_lower: str, limit: int) -> list:
    tasks = db.query(Task).options(joinedload(Task.project)).filter(
        _or(
            func.lower(Task.title).like(q_lower),
            func.lower(Task.code).like(q_lower),
            func.lower(Task.description).like(q_lower),
        )
    ).limit(limit).all()
    return [{
        "id": t.id, "type": "task",
        "title": t.title,
        "subtitle": f"{t.project.code if t.project else '—'} · {t.status}",
        "status": t.status, "url": "/tasks",
        "icon": "▦",
    } for t in tasks]


def _search_tickets(db: Session, q_lower: str, limit: int) -> list:
    tickets = db.query(Ticket).filter(
        _or(
            func.lower(Ticket.title).like(q_lower),
            func.lower(Ticket.number).like(q_lower),
            func.lower(Ticket.requester_name).like(q_lower),
        )
    ).limit(limit).all()
    return [{
        "id": t.id, "type": "ticket",
        "title": t.title,
        "subtitle": f"#{t.number} · {t.status} · {t.priority}",
        "status": t.status, "url": "/service-desk",
        "icon": "🎫",
    } for t in tickets]


def _search_users(db: Session, q_lower: str, limit: int) -> list:
    users = db.query(UserModel).filter(
        UserModel.is_active == True,
        _or(
            func.lower(UserModel.full_name).like(q_lower),
            func.lower(UserModel.email).like(q_lower),
            func.lower(UserModel.username).like(q_lower),
        )
    ).limit(limit).all()
    return [{
        "id": u.id, "type": "user",
        "title": u.full_name,
        "subtitle": f"{u.role} · {u.email}",
        "url": "/resources",
        "icon": "👤",
    } for u in users]


def _search_invoices(db: Session, q_lower: str, limit: int) -> list:
    invoices = db.query(Inv).filter(
        _or(
            func.lower(Inv.number).like(q_lower),
            func.lower(Inv.client_name).like(q_lower),
        )
    ).limit(limit).all()
    return [{
        "id": i.id, "type": "invoice",
        "title": i.number,
        "subtitle": f"{i.client_name or '—'} · {i.total}€ · {i.status}",
        "status": i.status, "url": "/invoices",
        "icon": "🧾",
    } for i in invoices]


def _search_opportunities(db: Session, q_lower: str, limit: int) -> list:
    opps = db.query(Opp).filter(
        _or(
            func.lower(Opp.name).like(q_lower),
            func.lower(Opp.client_name).like(q_lower),
        )
    ).limit(limit).all()
    return [{
        "id": o.id, "type": "opportunity",
        "title": o.name,
        "subtitle": f"{o.client_name or '—'} · {o.stage}",
        "url": "/pipeline",
        "icon": "🎪",
    } for o in opps]


def global_search(q: str, types: Optional[str], limit: int, db: Session) -> dict:

    search_types = types.split(",") if types else ["projects", "tasks", "tickets", "users", "invoices", "opportunities"]
    q_lower = f"%{q.lower()}%"
    results = {}

    if "projects" in search_types:
        results["projects"] = _search_projects(db, q_lower, limit // 3)
    if "tasks" in search_types:
        results["tasks"] = _search_tasks(db, q_lower, limit // 3)
    if "tickets" in search_types:
        results["tickets"] = _search_tickets(db, q_lower, limit // 4)
    if "users" in search_types:
        results["users"] = _search_users(db, q_lower, limit // 4)
    if "invoices" in search_types:
        results["invoices"] = _search_invoices(db, q_lower, 10)
    if "opportunities" in search_types:
        results["opportunities"] = _search_opportunities(db, q_lower, 10)

    all_results = []
    for items in results.values():
        all_results.extend(items)
    return {
        "query": q,
        "total": sum(len(v) for v in results.values()),
        "grouped": results,
        "flat": all_results[:limit],
    }


# ─── Dashboard Widgets ────────────────────────────────────────────────────────

def get_user_widgets(current_user, db: Session) -> list:
    widgets = db.query(DashboardWidget).filter(
        DashboardWidget.user_id == current_user.id,
        DashboardWidget.is_visible == True,
    ).order_by(DashboardWidget.position_y, DashboardWidget.position_x).all()

    if not widgets:
        return default_widget_layout(current_user.role)

    return [{
        "id": w.id, "widget_type": w.widget_type,
        "title": w.title,
        "position_x": w.position_x, "position_y": w.position_y,
        "width": w.width, "height": w.height,
        "config": json.loads(w.config) if w.config else {},
    } for w in widgets]


def save_widget_layout(payload: list, current_user_id: str, db: Session) -> dict:
    db.query(DashboardWidget).filter(DashboardWidget.user_id == current_user_id).delete()
    db.flush()
    for item in payload:
        widget_type = item.get("widget_type")
        if not widget_type:
            continue
        w = DashboardWidget(
            user_id=current_user_id,
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


def reset_widgets(current_user_id: str, db: Session) -> dict:
    db.query(DashboardWidget).filter(DashboardWidget.user_id == current_user_id).delete()
    db.commit()
    return {"ok": True}


# ─── Onboarding ───────────────────────────────────────────────────────────────

ONBOARDING_STEPS = [
    {"id": "create_project",  "title": "Crea tu primer proyecto",      "description": "Configura el nombre, cliente y fechas de tu primer proyecto.",      "action": "/projects", "icon": "⬡"},
    {"id": "invite_team",     "title": "Invita a tu equipo",           "description": "Añade los miembros del equipo que van a trabajar en el proyecto.",   "action": "/settings", "icon": "👥"},
    {"id": "configure_sla",   "title": "Configura el SLA",             "description": "Define el horario laboral y los festivos para el cálculo de SLAs.",  "action": "/settings", "icon": "🎯"},
    {"id": "create_sprint",   "title": "Lanza tu primer sprint",       "description": "Crea un sprint con tareas y fija las fechas de inicio y fin.",       "action": "/sprints",  "icon": "⚡"},
    {"id": "first_timesheet", "title": "Imputa tus primeras horas",    "description": "Registra las horas trabajadas hoy en el proyecto que acabas de crear.", "action": "/imputar", "icon": "⏱"},
]


def get_onboarding(current_user, db: Session) -> dict:
    state = db.query(OnboardingState).filter(
        OnboardingState.user_id == current_user.id
    ).first()
    if not state:
        state = OnboardingState(user_id=current_user.id, completed_steps="[]")
        db.add(state); db.commit(); db.refresh(state)

    completed = json.loads(state.completed_steps or "[]")
    return {
        "is_complete": state.is_complete,
        "is_dismissed": state.dismissed_at is not None,
        "current_step": state.current_step,
        "completed_steps": completed,
        "progress_pct": round(len(completed) / len(ONBOARDING_STEPS) * 100),
        "steps": [{**step, "completed": step["id"] in completed} for step in ONBOARDING_STEPS],
    }


def complete_onboarding_step(step_id: str, current_user, db: Session) -> dict:
    if step_id not in [s["id"] for s in ONBOARDING_STEPS]:
        raise ValueError(f"Step '{step_id}' no existe")
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


def dismiss_onboarding(current_user, db: Session) -> dict:
    state = db.query(OnboardingState).filter(
        OnboardingState.user_id == current_user.id
    ).first()
    if not state:
        state = OnboardingState(user_id=current_user.id, completed_steps="[]")
        db.add(state); db.flush()
    state.dismissed_at = datetime.now(timezone.utc)
    db.commit()
    return {"ok": True}


# ─── Integrations ─────────────────────────────────────────────────────────────

def list_integrations(db: Session) -> list:
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


def create_integration(payload, current_user_id: str, db: Session) -> dict:
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
        created_by=current_user_id,
    )
    db.add(c); db.commit()
    return {"ok": True, "id": c.id, "updated": False}


def run_integration_sync(integration_id: str, payload: dict, db: Session) -> dict:
    config = db.query(IntegrationConfig).filter(IntegrationConfig.id == integration_id).first()
    if not config:
        raise ValueError("Integración no encontrada")
    if not config.is_active:
        raise ValueError("Integración inactiva")

    synced = 0
    errors = []
    if config.integration_type in ["github", "gitlab"]:
        synced, errors = sync_git_commits(db, config, payload)
    elif config.integration_type in ["google_calendar", "outlook"]:
        synced, errors = sync_calendar(db, config, payload)
    elif config.integration_type in ["quickbooks", "xero"]:
        synced, errors = sync_accounting(db, config, payload)
    elif config.integration_type == "jira":
        synced, errors = sync_jira(db, config, payload)
    else:
        # Slack y Teams solo envian avisos: no hay nada que sincronizar.
        raise ValueError(f"La integración «{config.integration_type}» no tiene sincronización; usa «Probar».")

    config.last_sync_at = datetime.now(timezone.utc)
    config.sync_errors = len(errors)
    config.last_error = errors[0] if errors else None
    db.commit()
    if errors and not synced:
        # Antes respondia «ok» y la pantalla decia «Sincronización completada».
        raise ValueError(errors[0])
    return {"ok": True, "synced": synced, "errors": errors[:5]}


def get_calendar_events(user_id: str, from_date, to_date, db: Session) -> list:
    q = db.query(CE).options(joinedload(CE.project))
    q = q.filter(CE.user_id == user_id)
    if from_date:
        q = q.filter(CE.start_dt >= datetime.combine(from_date, datetime.min.time()))
    if to_date:
        q = q.filter(CE.start_dt <= datetime.combine(to_date, datetime.max.time()))
    events = q.order_by(CE.start_dt).limit(100).all()
    return [{
        "id": e.id, "title": e.title,
        "start_dt": str(e.start_dt)[:16], "end_dt": str(e.end_dt)[:16],
        "all_day": e.all_day, "description": e.description,
        "project_name": e.project.name if e.project else None,
        "sprint_id": e.sprint_id, "milestone_id": e.milestone_id,
    } for e in events]


def get_commit_links(integration_id: str, task_id: Optional[str], db: Session) -> list:
    q = db.query(CL).options(
        joinedload(CL.task).joinedload(Task.project)
    ).filter(CL.integration_id == integration_id)
    if task_id:
        q = q.filter(CL.task_id == task_id)
    links = q.order_by(CL.created_at_ext.desc()).limit(50).all()
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


# ─── Risk scores ──────────────────────────────────────────────────────────────

_RISK_SCORE_FIELDS = [
    "schedule_risk", "budget_risk", "scope_risk", "resource_risk",
    "overall_score", "level", "delay_probability_pct",
    "predicted_delay_weeks", "recommendation",
]


def _is_risk_cache_fresh(cached, ttl_minutes: int = 60) -> bool:
    """Return True if the cached risk score is younger than ttl_minutes."""
    if not (cached and cached.computed_at):
        return False
    computed_at = cached.computed_at
    if computed_at.tzinfo is None:
        computed_at = computed_at.replace(tzinfo=timezone.utc)
    age_minutes = (datetime.now(timezone.utc) - computed_at).total_seconds() / 60
    return age_minutes < ttl_minutes


def _serialize_cached_risk(project, cached) -> dict:
    """Serialize a ProjectRiskScore row plus the project label fields."""
    return {
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
    }


def _persist_risk_score(db: Session, project_id: str, score_data: dict) -> None:
    """Persist a ProjectRiskScore row from a score dict (no commit)."""
    score_obj = ProjectRiskScore(
        project_id=project_id,
        **{k: v for k, v in score_data.items() if k in _RISK_SCORE_FIELDS}
    )
    db.add(score_obj)


def get_risk_scores(refresh: bool, db: Session) -> dict:
    projects = db.query(Project).filter(
        Project.status.in_(["active", "planning"])
    ).all()
    results = []
    for project in projects:
        cached = db.query(ProjectRiskScore).filter(
            ProjectRiskScore.project_id == project.id
        ).order_by(ProjectRiskScore.computed_at.desc()).first()
        ttl = _ajustes_de_riesgo(db, project.organization_id).RISK_CACHE_MINUTES
        if not refresh and _is_risk_cache_fresh(cached, ttl):
            results.append(_serialize_cached_risk(project, cached))
            continue
        score_data = compute_risk_score(db, project)
        _persist_risk_score(db, project.id, score_data)
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


def get_project_risk_score(project_id: str, db: Session) -> dict:
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise ValueError("Proyecto no encontrado")
    score_data = compute_risk_score(db, project)
    aj = _ajustes_de_riesgo(db, project.organization_id)
    previas = db.query(ProjectRiskScore).filter(
        ProjectRiskScore.project_id == project_id,
    ).order_by(ProjectRiskScore.computed_at.desc()).limit(max(1, aj.RISK_HISTORY_POINTS)).all()
    # Antes cada apertura del detalle insertaba una fila. Ahora solo si la
    # puntuacion cambia o la ultima ya ha caducado: el historial es de cambios.
    ultima = previas[0] if previas else None
    if not (ultima and ultima.overall_score == score_data["overall_score"]
            and _is_risk_cache_fresh(ultima, aj.RISK_CACHE_MINUTES)):
        _persist_risk_score(db, project_id, score_data)
        db.commit()
    historial = [{"computed_at": str(r.computed_at)[:16], "overall_score": r.overall_score, "level": r.level}
                 for r in reversed(previas)]
    return {
        "project_id": project_id,
        "project_name": project.name,
        "project_code": project.code,
        "client_name": project.client_name,
        **score_data,
        "history": historial,
    }
