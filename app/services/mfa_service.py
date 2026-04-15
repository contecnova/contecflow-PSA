"""
mfa_service — business logic extracted from app/api/v1/endpoints/mfa.py
Covers: MFA TOTP, organizations, Slack/Teams, budgets, AI estimation,
        AI triage, scenario planning, PDF export, BI tokens.
"""
from __future__ import annotations

import io
import json
import logging
import secrets
from datetime import date, datetime, timedelta, timezone
from typing import Optional

from sqlalchemy.orm import Session
from sqlalchemy import func

from app.core.config import settings
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

_logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════════
# MFA / TOTP
# ═══════════════════════════════════════════════════════════════════════════════

def get_totp_lib():
    try:
        import pyotp
        return pyotp
    except ImportError:
        return None


def get_mfa_status(user_id: str, db: Session) -> dict:
    config = db.query(MFAConfig).filter(MFAConfig.user_id == user_id).first()
    if not config:
        return {"enabled": False, "has_config": False}
    backup_count = db.query(func.count(MFABackupCode.id)).filter(
        MFABackupCode.mfa_id == config.id,
        MFABackupCode.used_at == None,
    ).scalar()
    return {
        "enabled": config.is_enabled,
        "has_config": True,
        "verified_at": str(config.verified_at)[:16] if config.verified_at else None,
        "last_used_at": str(config.last_used_at)[:16] if config.last_used_at else None,
        "backup_codes_remaining": backup_count or 0,
    }


def setup_mfa(user: User, db: Session) -> dict:
    pyotp = get_totp_lib()
    if not pyotp:
        raise ValueError("pyotp no instalado — ejecuta: pip install pyotp")

    existing = db.query(MFAConfig).filter(MFAConfig.user_id == user.id).first()
    if existing and existing.is_enabled:
        raise ValueError("MFA ya está activado. Desactívalo antes de reconfigurar.")
    if existing:
        db.delete(existing)
        db.flush()

    secret = pyotp.random_base32()
    totp = pyotp.TOTP(secret)
    uri = totp.provisioning_uri(name=user.email, issuer_name="Clarive")

    config = MFAConfig(
        user_id=user.id,
        totp_secret=encrypt_value(secret),
        is_enabled=False,
    )
    db.add(config)
    db.commit()

    return {
        "secret": secret,
        "provisioning_uri": uri,
        "qr_url": f"{settings.GOOGLE_CHART_URL}?chs=200x200&chld=M|0&cht=qr&chl={uri}",
        "instructions": "Escanea el QR con Google Authenticator, Authy o similar. Luego llama a POST /mfa/verify con el código de 6 dígitos para activar.",
    }


def verify_and_activate_mfa(user: User, code: str, db: Session) -> dict:
    import bcrypt
    pyotp = get_totp_lib()
    if not pyotp:
        raise ValueError("pyotp no instalado")

    config = db.query(MFAConfig).filter(MFAConfig.user_id == user.id).first()
    if not config:
        raise ValueError("Primero llama a /mfa/setup")

    totp = pyotp.TOTP(decrypt_value(config.totp_secret) or config.totp_secret)
    if not totp.verify(code, valid_window=1):
        raise ValueError("Código incorrecto o caducado")

    config.is_enabled = True
    config.verified_at = datetime.now(timezone.utc)
    config.last_used_at = datetime.now(timezone.utc)

    backup_codes = []
    for _ in range(8):
        raw = secrets.token_hex(4).upper()
        hashed = bcrypt.hashpw(raw.encode(), bcrypt.gensalt()).decode()
        db.add(MFABackupCode(mfa_id=config.id, code_hash=hashed))
        backup_codes.append(raw)

    audit_log(db, user, "MFA_ENABLED", "users", user.id, user.email)
    db.commit()

    return {
        "ok": True,
        "message": "MFA activado correctamente",
        "backup_codes": backup_codes,
        "warning": "Guarda estos códigos en un lugar seguro. Solo se muestran una vez.",
    }


def validate_mfa_code(user: User, code: str, db: Session) -> dict:
    import bcrypt
    pyotp = get_totp_lib()
    config = db.query(MFAConfig).filter(
        MFAConfig.user_id == user.id,
        MFAConfig.is_enabled == True,
    ).first()
    if not config:
        return {"ok": True, "mfa_required": False}
    if not pyotp:
        raise ValueError("pyotp no instalado — ejecuta: pip install pyotp")

    totp = pyotp.TOTP(decrypt_value(config.totp_secret) or config.totp_secret)
    if totp.verify(code, valid_window=1):
        config.last_used_at = datetime.now(timezone.utc)
        db.commit()
        return {"ok": True, "valid": True}

    backup_codes = db.query(MFABackupCode).filter(
        MFABackupCode.mfa_id == config.id,
        MFABackupCode.used_at == None,
    ).all()
    for bc in backup_codes:
        if bcrypt.checkpw(code.upper().encode(), bc.code_hash.encode()):
            bc.used_at = datetime.now(timezone.utc)
            config.last_used_at = datetime.now(timezone.utc)
            db.commit()
            remaining = db.query(func.count(MFABackupCode.id)).filter(
                MFABackupCode.mfa_id == config.id, MFABackupCode.used_at == None,
            ).scalar()
            return {"ok": True, "valid": True, "used_backup_code": True,
                    "backup_codes_remaining": remaining}

    raise ValueError("Código MFA inválido")


def disable_mfa(user: User, code: str, db: Session) -> dict:
    pyotp = get_totp_lib()
    if not pyotp:
        raise ValueError("pyotp no instalado — ejecuta: pip install pyotp")
    config = db.query(MFAConfig).filter(
        MFAConfig.user_id == user.id, MFAConfig.is_enabled == True,
    ).first()
    if not config:
        raise ValueError("MFA no está activado")
    totp = pyotp.TOTP(decrypt_value(config.totp_secret) or config.totp_secret)
    if not totp.verify(code, valid_window=1):
        raise ValueError("Código incorrecto")
    config.is_enabled = False
    audit_log(db, user, "MFA_DISABLED", "users", user.id, user.email)
    db.commit()
    return {"ok": True}


# ═══════════════════════════════════════════════════════════════════════════════
# ORGANIZATIONS
# ═══════════════════════════════════════════════════════════════════════════════

def serialize_organization(org: Organization, db: Session) -> dict:
    return {
        "id": org.id, "name": org.name, "slug": org.slug,
        "plan": org.plan, "is_active": org.is_active,
        "max_users": org.max_users, "max_projects": org.max_projects,
        "admin_email": org.admin_email,
        "created_at": str(org.created_at)[:10] if org.created_at else None,
        "user_count": db.query(func.count(User.id)).filter(User.organization_id == org.id).scalar(),
        "project_count": db.query(func.count(Project.id)).filter(Project.organization_id == org.id).scalar() if hasattr(Project, 'organization_id') else 0,
    }


def check_org_user_limit(org: Organization, db: Session) -> None:
    count = db.query(func.count(User.id)).filter(User.organization_id == org.id).scalar()
    if count >= org.max_users:
        raise ValueError(f"Límite de {org.max_users} usuarios alcanzado para este plan")


# ═══════════════════════════════════════════════════════════════════════════════
# SLACK / TEAMS
# ═══════════════════════════════════════════════════════════════════════════════

def send_slack_message(config: SlackConfig, text: str, channel: str = None) -> tuple:
    """
    Send a message to Slack or Teams.
    Returns (success: bool, error: str|None)
    """
    import urllib.request
    import urllib.error

    ch = channel or config.default_channel or "#general"

    if config.platform == "slack" and config.bot_token:
        try:
            data = json.dumps({
                "channel": ch,
                "text": text,
                "username": "Clarive",
                "icon_emoji": ":rocket:",
            }).encode("utf-8")
            req = urllib.request.Request(
                f"{settings.SLACK_API_BASE}/chat.postMessage",
                data=data,
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {config.bot_token}",
                }
            )
            with urllib.request.urlopen(req, timeout=5) as resp:
                result = json.loads(resp.read())
                if result.get("ok"):
                    return True, None
                return False, result.get("error", "Slack API error")
        except Exception:
            pass

    if config.webhook_url:
        try:
            if config.platform == "teams":
                body = json.dumps({"text": text}).encode("utf-8")
            else:
                body = json.dumps({"text": text, "channel": ch}).encode("utf-8")
            req = urllib.request.Request(
                config.webhook_url, data=body,
                headers={"Content-Type": "application/json"}
            )
            with urllib.request.urlopen(req, timeout=5) as resp:
                return resp.status in (200, 201), None
        except Exception as e:
            return False, str(e)

    _logger.info("[SLACK SIMULATED] %s → %s: %s", config.platform, ch, text)
    return True, None


# ═══════════════════════════════════════════════════════════════════════════════
# BUDGETS
# ═══════════════════════════════════════════════════════════════════════════════

def budget_by_dept(budgets) -> list:
    dept_map = {}
    for b in budgets:
        dept = b.department or "Sin departamento"
        if dept not in dept_map:
            dept_map[dept] = {"department": dept, "planned": 0, "actual": 0}
        for e in b.entries:
            dept_map[dept]["planned"] += e.planned
            dept_map[dept]["actual"] += e.actual
    for d in dept_map.values():
        d["deviation_pct"] = round((d["actual"] - d["planned"]) / max(d["planned"], 1) * 100, 1)
    return list(dept_map.values())


# ═══════════════════════════════════════════════════════════════════════════════
# AI — TASK ESTIMATION
# ═══════════════════════════════════════════════════════════════════════════════

def estimate_task_hours(task_id: str, db: Session) -> dict:
    """Estimate task hours using historical similar tasks or heuristics + optional Claude API."""
    from sqlalchemy import or_ as sql_or

    task = db.query(Task).options(__import__('sqlalchemy.orm', fromlist=['joinedload']).joinedload(Task.project)).filter(Task.id == task_id).first()
    if not task:
        raise ValueError("task_not_found")

    keywords = [w for w in (task.title or "").lower().split() if len(w) > 3]
    similar_tasks = []
    if keywords:
        filters = sql_or(*[
            func.lower(Task.title).contains(kw) for kw in keywords[:5]
        ])
        similar_tasks = db.query(Task).filter(
            Task.status == "done",
            Task.estimated_hours != None,
            Task.actual_hours != None,
            Task.id != task_id,
            filters,
        ).limit(10).all()

    estimated_hours = None
    confidence = 0
    reasoning = ""
    similar_ids = []

    if similar_tasks:
        estimates = []
        for st in similar_tasks:
            accuracy = 1 - abs(st.actual_hours - st.estimated_hours) / max(st.estimated_hours, 1)
            estimates.append((st.actual_hours, max(accuracy, 0.1)))
            similar_ids.append(st.id)

        total_weight = sum(w for _, w in estimates)
        estimated_hours = round(sum(h * w for h, w in estimates) / total_weight, 1)
        confidence = min(round(len(similar_tasks) / 10 * 70 + 20), 85)
        reasoning = f"Basado en {len(similar_tasks)} tareas similares completadas. Promedio ponderado por precisión histórica."
    else:
        title_lower = (task.title or "").lower()
        base = 4.0
        if any(w in title_lower for w in ["implementar", "desarrollar", "crear", "diseñar"]): base += 4
        if any(w in title_lower for w in ["integración", "migración", "refactor"]): base += 6
        if any(w in title_lower for w in ["fix", "corrección", "bug", "error"]): base = 2
        if any(w in title_lower for w in ["test", "prueba", "validar"]): base = 3
        estimated_hours = round(base, 1)
        confidence = 30
        reasoning = "Sin tareas similares en el historial. Estimación heurística por tipo de tarea."

    api_key = settings.ANTHROPIC_API_KEY or None
    if api_key and similar_tasks:
        try:
            import urllib.request
            similar_context = "\n".join([
                f"- '{t.title}': estimado {t.estimated_hours}h, real {t.actual_hours}h"
                for t in similar_tasks[:5]
            ])
            prompt = f"""Tarea a estimar: "{task.title}"
Proyecto: {task.project.name if task.project else "—"}
Descripción: {(task.description or "Sin descripción")[:200]}

Tareas similares completadas:
{similar_context}

Responde SOLO con JSON: {{"hours": <número>, "confidence": <0-100>, "reasoning": "<explicación breve>"}}"""

            data = json.dumps({
                "model": settings.NEXUS_AI_MODEL,
                "max_tokens": 200,
                "messages": [{"role": "user", "content": prompt}]
            }).encode()
            req = urllib.request.Request(
                settings.ANTHROPIC_API_URL,
                data=data,
                headers={
                    "Content-Type": "application/json",
                    "x-api-key": api_key,
                    "anthropic-version": "2023-06-01",
                }
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                result = json.loads(resp.read())
                text = result["content"][0]["text"]
                parsed = json.loads(text)
                estimated_hours = parsed["hours"]
                confidence = parsed.get("confidence", confidence)
                reasoning = parsed.get("reasoning", reasoning) + " [Claude API]"
        except Exception:
            pass

    existing = db.query(AITaskEstimate).filter(AITaskEstimate.task_id == task_id).first()
    if existing:
        existing.estimated_hours = estimated_hours
        existing.confidence_pct = confidence
        existing.reasoning = reasoning
        existing.similar_tasks = json.dumps(similar_ids)
    else:
        db.add(AITaskEstimate(
            task_id=task_id,
            estimated_hours=estimated_hours,
            confidence_pct=confidence,
            reasoning=reasoning,
            similar_tasks=json.dumps(similar_ids),
            model_used="claude_api" if api_key else "rule_based",
        ))
    db.commit()

    return {
        "task_id": task_id,
        "task_title": task.title,
        "estimated_hours": estimated_hours,
        "confidence_pct": confidence,
        "reasoning": reasoning,
        "similar_count": len(similar_tasks),
        "current_estimate": task.estimated_hours,
    }


def accept_task_estimate(task_id: str, accepted: bool, db: Session) -> dict:
    estimate = db.query(AITaskEstimate).filter(AITaskEstimate.task_id == task_id).first()
    if not estimate:
        raise ValueError("estimate_not_found")
    estimate.accepted = accepted
    estimate.accepted_at = datetime.now(timezone.utc)
    if accepted:
        task = db.query(Task).filter(Task.id == task_id).first()
        if task:
            task.estimated_hours = estimate.estimated_hours
    db.commit()
    return {"ok": True, "accepted": accepted}


# ═══════════════════════════════════════════════════════════════════════════════
# AI — TICKET TRIAGE
# ═══════════════════════════════════════════════════════════════════════════════

def triage_ticket(ticket_id: str, db: Session) -> dict:
    """AI triage: suggest category, priority, agent for a ticket."""
    ticket = db.query(Ticket).filter(Ticket.id == ticket_id).first()
    if not ticket:
        raise ValueError("ticket_not_found")

    title_lower = (ticket.title or "").lower()
    desc_lower = (ticket.description or "").lower()
    full_text = f"{title_lower} {desc_lower}"

    suggested_priority = "medium"
    suggested_category = "General"
    reasoning = "Clasificación por reglas heurísticas."

    critical_kw = ["caído", "down", "producción", "bloqueado", "urgente", "crítico", "no funciona", "error 500"]
    high_kw = ["lento", "fallo", "problema", "no puedo", "imposible", "impide"]
    low_kw = ["consulta", "pregunta", "cómo", "información", "mejora", "sugerencia"]

    if any(kw in full_text for kw in critical_kw): suggested_priority = "critical"
    elif any(kw in full_text for kw in high_kw): suggested_priority = "high"
    elif any(kw in full_text for kw in low_kw): suggested_priority = "low"

    if any(kw in full_text for kw in ["contraseña", "acceso", "login", "usuario", "permisos"]):
        suggested_category = "Acceso y seguridad"
    elif any(kw in full_text for kw in ["instalar", "instalación", "configurar", "setup"]):
        suggested_category = "Instalación y configuración"
    elif any(kw in full_text for kw in ["red", "internet", "conexión", "wifi", "vpn"]):
        suggested_category = "Red y conectividad"
    elif any(kw in full_text for kw in ["impres", "escaner", "periférico", "hardware"]):
        suggested_category = "Hardware y periféricos"
    elif any(kw in full_text for kw in ["excel", "word", "office", "correo", "email", "outlook"]):
        suggested_category = "Software de oficina"
    elif any(kw in full_text for kw in ["lento", "rendimiento", "cuelga", "memoria"]):
        suggested_category = "Rendimiento"

    agent_loads = db.query(
        Ticket.assignee_id, func.count(Ticket.id).label("open_count")
    ).filter(
        Ticket.status.in_(["open", "in_progress"]),
        Ticket.assignee_id != None,
    ).group_by(Ticket.assignee_id).order_by("open_count").limit(5).all()

    suggested_agent_id = agent_loads[0].assignee_id if agent_loads else None
    confidence = 60

    api_key = settings.ANTHROPIC_API_KEY or None
    if api_key:
        try:
            import urllib.request
            prompt = f"""Analiza este ticket de soporte y clasifícalo.

Título: {ticket.title}
Descripción: {(ticket.description or "Sin descripción")[:300]}

Responde SOLO con JSON:
{{"category": "<categoría>", "priority": "critical|high|medium|low", "confidence": <0-100>, "reasoning": "<explicación breve en español>"}}"""

            data = json.dumps({
                "model": settings.NEXUS_AI_MODEL,
                "max_tokens": 300,
                "messages": [{"role": "user", "content": prompt}]
            }).encode()
            req = urllib.request.Request(
                settings.ANTHROPIC_API_URL,
                data=data,
                headers={
                    "Content-Type": "application/json",
                    "x-api-key": api_key,
                    "anthropic-version": "2023-06-01",
                }
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                result = json.loads(resp.read())
                parsed = json.loads(result["content"][0]["text"])
                suggested_category = parsed.get("category", suggested_category)
                suggested_priority = parsed.get("priority", suggested_priority)
                confidence = parsed.get("confidence", 75)
                reasoning = parsed.get("reasoning", reasoning) + " [Claude API]"
        except Exception:
            pass

    existing = db.query(AITicketTriage).filter(AITicketTriage.ticket_id == ticket_id).first()
    if existing:
        existing.suggested_category = suggested_category
        existing.suggested_priority = suggested_priority
        existing.suggested_agent_id = suggested_agent_id
        existing.confidence_pct = confidence
        existing.reasoning = reasoning
    else:
        db.add(AITicketTriage(
            ticket_id=ticket_id,
            suggested_category=suggested_category,
            suggested_priority=suggested_priority,
            suggested_agent_id=suggested_agent_id,
            confidence_pct=confidence,
            reasoning=reasoning,
        ))
    db.commit()

    agent = db.query(User).filter(User.id == suggested_agent_id).first() if suggested_agent_id else None
    return {
        "ticket_id": ticket_id,
        "ticket_title": ticket.title,
        "suggested_category": suggested_category,
        "suggested_priority": suggested_priority,
        "suggested_agent": agent.full_name if agent else None,
        "suggested_agent_id": suggested_agent_id,
        "confidence_pct": confidence,
        "reasoning": reasoning,
    }


def accept_ticket_triage(ticket_id: str, accepted: bool, current_user_id: str, db: Session) -> dict:
    triage = db.query(AITicketTriage).filter(AITicketTriage.ticket_id == ticket_id).first()
    if not triage:
        raise ValueError("triage_not_found")
    triage.accepted = accepted
    triage.accepted_by = current_user_id
    triage.accepted_at = datetime.now(timezone.utc)
    if accepted:
        ticket = db.query(Ticket).filter(Ticket.id == ticket_id).first()
        if ticket:
            if triage.suggested_priority: ticket.priority = triage.suggested_priority
            if triage.suggested_category: ticket.ticket_type = triage.suggested_category
            if triage.suggested_agent_id: ticket.assignee_id = triage.suggested_agent_id
    db.commit()
    return {"ok": True, "accepted": accepted}


# ═══════════════════════════════════════════════════════════════════════════════
# SCENARIO PLANNING
# ═══════════════════════════════════════════════════════════════════════════════

def compute_scenario(scenario_id: str, db: Session) -> dict:
    """Simulate capacity impact of scenario projects against current team capacity."""
    from sqlalchemy.orm import joinedload as jl

    scenario = db.query(ScenarioModel).options(
        jl(ScenarioModel.projects)
    ).filter(ScenarioModel.id == scenario_id).first()
    if not scenario:
        raise ValueError("scenario_not_found")

    base_date = scenario.base_date or date.today()
    horizon_end = base_date + timedelta(weeks=scenario.horizon_weeks)

    active_users = db.query(User).filter(User.is_active == True).count()
    hours_per_week_per_person = settings.DEFAULT_WEEKLY_CAPACITY_HOURS
    weekly_capacity = active_users * hours_per_week_per_person

    total_demand_hours = 0
    weekly_demand = {}
    overloaded_weeks = []
    project_breakdown = []

    for sp in scenario.projects:
        if not sp.start_date or not sp.end_date:
            continue
        duration_weeks = max((sp.end_date - sp.start_date).days / 7, 1)
        hours_per_week = sp.total_hours / duration_weeks

        current = sp.start_date
        while current < sp.end_date and current < horizon_end:
            week_key = current.strftime("%Y-W%W")
            weekly_demand[week_key] = weekly_demand.get(week_key, 0) + hours_per_week
            current += timedelta(weeks=1)

        total_demand_hours += sp.total_hours
        project_breakdown.append({
            "name": sp.name,
            "total_hours": sp.total_hours,
            "hours_per_week": round(hours_per_week, 1),
            "start": str(sp.start_date),
            "end": str(sp.end_date),
            "is_existing": sp.is_existing,
        })

    capacity_timeline = []
    for week_key, demand in sorted(weekly_demand.items()):
        utilization_pct = round(demand / max(weekly_capacity, 1) * 100, 1)
        is_overloaded = utilization_pct > 100
        if is_overloaded:
            overloaded_weeks.append(week_key)
        capacity_timeline.append({
            "week": week_key,
            "demand": round(demand, 1),
            "capacity": weekly_capacity,
            "utilization_pct": utilization_pct,
            "is_overloaded": is_overloaded,
        })

    avg_utilization = sum(c["utilization_pct"] for c in capacity_timeline) / max(len(capacity_timeline), 1)
    feasible = len(overloaded_weeks) == 0
    risk_level = "low" if feasible else ("medium" if len(overloaded_weeks) <= 3 else "high")

    results = {
        "feasible": feasible,
        "risk_level": risk_level,
        "avg_utilization_pct": round(avg_utilization, 1),
        "peak_utilization_pct": max((c["utilization_pct"] for c in capacity_timeline), default=0),
        "overloaded_weeks_count": len(overloaded_weeks),
        "overloaded_weeks": overloaded_weeks[:10],
        "total_demand_hours": round(total_demand_hours, 1),
        "team_size": active_users,
        "weekly_capacity": weekly_capacity,
        "horizon_weeks": scenario.horizon_weeks,
        "project_breakdown": project_breakdown,
        "capacity_timeline": capacity_timeline[:24],
        "recommendation": (
            "El equipo tiene capacidad suficiente para asumir todos los proyectos del escenario." if feasible
            else f"Se detectan {len(overloaded_weeks)} semanas con sobrecarga. Considera retrasar proyectos o ampliar equipo."
        ),
    }

    scenario.results = json.dumps(results)
    scenario.status = "computed"
    scenario.computed_at = datetime.now(timezone.utc)
    db.commit()
    return results


# ═══════════════════════════════════════════════════════════════════════════════
# PDF EXPORT
# ═══════════════════════════════════════════════════════════════════════════════

def generate_pdf(export_type: str, source_id: Optional[str], params: dict, db: Session) -> bytes:
    """Generate PDF using reportlab, or a minimal fallback if not installed."""
    try:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.units import mm
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable
        from reportlab.platypus import KeepTogether  # noqa: F841

        buf = io.BytesIO()
        doc = SimpleDocTemplate(buf, pagesize=A4,
                                rightMargin=20 * mm, leftMargin=20 * mm,
                                topMargin=20 * mm, bottomMargin=20 * mm)
        styles = getSampleStyleSheet()

        title_style = ParagraphStyle("NexusTitle", parent=styles["Heading1"],
                                     fontSize=20, textColor=colors.HexColor("#1C2833"),
                                     spaceAfter=4)
        subtitle_style = ParagraphStyle("NexusSubtitle", parent=styles["Normal"],
                                        fontSize=10, textColor=colors.HexColor("#7F8C8D"),
                                        spaceAfter=12)
        section_style = ParagraphStyle("NexusSection", parent=styles["Heading2"],
                                       fontSize=13, textColor=colors.HexColor("#1A5276"),
                                       spaceBefore=12, spaceAfter=6)
        body_style = ParagraphStyle("NexusBody", parent=styles["Normal"],
                                    fontSize=9, textColor=colors.HexColor("#2C3E50"),
                                    leading=14)

        elements = []

        logo_b64 = params.get("logo_b64")  # noqa: F841
        company_name = params.get("company_name", "Clarive")
        primary_color = params.get("primary_color", "#1C2833")

        elements.append(Paragraph(f"<b>{company_name}</b>", title_style))
        elements.append(HRFlowable(width="100%", thickness=2,
                                   color=colors.HexColor(primary_color), spaceAfter=8))

        now_str = datetime.now().strftime("%d/%m/%Y %H:%M")
        elements.append(Paragraph(f"Generado: {now_str}", subtitle_style))

        if export_type == "project_summary" and source_id:
            project = db.query(Project).filter(Project.id == source_id).first()
            if project:
                elements.append(Paragraph(f"Resumen del proyecto: {project.name}", section_style))
                data = [
                    ["Campo", "Valor"],
                    ["Código", project.code or "—"],
                    ["Cliente", project.client_name or "—"],
                    ["Estado", project.status or "—"],
                    ["Presupuesto", f"{project.budget_amount:,.0f} €" if project.budget_amount else "—"],
                    ["Inicio", str(project.start_date) if project.start_date else "—"],
                    ["Fin previsto", str(project.end_date_planned) if project.end_date_planned else "—"],
                ]
                tasks = db.query(Task).filter(Task.project_id == source_id).all()
                done = sum(1 for t in tasks if t.status == "done")
                data.append(["Tareas", f"{done}/{len(tasks)} completadas"])
                t = Table(data, colWidths=[60 * mm, 110 * mm])
                t.setStyle(TableStyle([
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor(primary_color)),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("FONTSIZE", (0, 0), (-1, -1), 9),
                    ("ROWBACKGROUNDS", (0, 1), (-1, -1),
                     [colors.HexColor("#F7F9FC"), colors.white]),
                    ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#D0D7E0")),
                    ("PADDING", (0, 0), (-1, -1), 6),
                ]))
                elements.append(t)

        elif export_type == "invoice" and source_id:
            from app.models.billing_reports import Invoice, InvoiceLine
            invoice = db.query(Invoice).filter(Invoice.id == source_id).first()
            if invoice:
                elements.append(Paragraph(f"Factura {invoice.number}", section_style))
                data = [
                    ["Cliente", invoice.client_name or "—"],
                    ["Fecha emisión", str(invoice.issue_date) if invoice.issue_date else "—"],
                    ["Vencimiento", str(invoice.due_date) if invoice.due_date else "—"],
                    ["Estado", invoice.status or "—"],
                ]
                t = Table(data, colWidths=[60 * mm, 110 * mm])
                t.setStyle(TableStyle([
                    ("FONTSIZE", (0, 0), (-1, -1), 9),
                    ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#D0D7E0")),
                    ("PADDING", (0, 0), (-1, -1), 6),
                ]))
                elements.append(t)
                elements.append(Spacer(1, 10 * mm))

                lines = db.query(InvoiceLine).filter(InvoiceLine.invoice_id == source_id).all()
                if lines:
                    line_data = [["Concepto", "Horas", "Tarifa", "Total"]]
                    for ln in lines:
                        line_data.append([
                            ln.description or "—",
                            f"{ln.quantity:.1f}h" if ln.quantity else "—",
                            f"{ln.unit_price:.2f}€" if ln.unit_price else "—",
                            f"{ln.total:.2f}€" if ln.total else "—",
                        ])
                    line_data.append(["", "", "TOTAL", f"{invoice.total:.2f}€" if invoice.total else "—"])
                    t2 = Table(line_data, colWidths=[90 * mm, 25 * mm, 25 * mm, 30 * mm])
                    t2.setStyle(TableStyle([
                        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor(primary_color)),
                        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                        ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
                        ("FONTSIZE", (0, 0), (-1, -1), 9),
                        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#D0D7E0")),
                        ("PADDING", (0, 0), (-1, -1), 5),
                        ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
                    ]))
                    elements.append(t2)

        else:
            elements.append(Paragraph(f"Tipo: {export_type}", section_style))
            elements.append(Paragraph("Exportación generada por Clarive v15.", body_style))

        elements.append(Spacer(1, 15 * mm))
        elements.append(HRFlowable(width="100%", thickness=0.5,
                                   color=colors.HexColor("#D0D7E0")))
        elements.append(Paragraph(
            f"<font color='#95A5A6' size=8>Generado por Clarive v15 · {now_str} · Documento confidencial</font>",
            body_style
        ))

        doc.build(elements)
        return buf.getvalue()

    except ImportError:
        content = f"""%PDF-1.4
1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj
2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj
3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 595 842]/Contents 4 0 R/Resources<</Font<</F1 5 0 R>>>>>>endobj
4 0 obj<</Length 120>>
stream
BT /F1 14 Tf 50 780 Td (Clarive v15 - {export_type}) Tj 0 -25 Td /F1 10 Tf (Generado: {datetime.now().strftime('%d/%m/%Y')}) Tj ET
endstream
endobj
5 0 obj<</Type/Font/Subtype/Type1/BaseFont/Helvetica>>endobj
xref
0 6
0000000000 65535 f
0000000009 00000 n
0000000058 00000 n
0000000115 00000 n
0000000266 00000 n
0000000438 00000 n
trailer<</Size 6/Root 1 0 R>>
startxref
521
%%EOF"""
        return content.encode()


# ═══════════════════════════════════════════════════════════════════════════════
# BI CONNECTOR
# ═══════════════════════════════════════════════════════════════════════════════

def verify_bi_token(token: str, db: Session) -> Optional[BIToken]:
    if not token or not token.startswith("bi_"):
        return None
    import bcrypt
    prefix = token[:10]
    candidates = db.query(BIToken).filter(
        BIToken.token_prefix == prefix,
        BIToken.is_active == True,
    ).all()
    for bt in candidates:
        if bcrypt.checkpw(token.encode(), bt.token_hash.encode()):
            bt_exp = bt.expires_at.replace(tzinfo=timezone.utc) if bt.expires_at and not bt.expires_at.tzinfo else bt.expires_at
            if bt_exp and bt_exp < datetime.now(timezone.utc):
                return None
            bt.last_used_at = datetime.now(timezone.utc)
            bt.requests_today = (bt.requests_today or 0) + 1
            return bt
    return None
