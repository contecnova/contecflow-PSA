"""ai_modules.oracle — extracted from the former ai_modules_service god-file."""

from __future__ import annotations
import json
import time
import logging
from datetime import datetime, timedelta, date, timezone
from app.core.timeutil import utcnow
from typing import Optional

from sqlalchemy.orm import Session
from sqlalchemy import func

from app.core.config import settings
from app.services.ai_dispatch import call_ai
from app.core.security import verify_client_token
from app.models.ai_chat import (
    AIActionLog, AIPrediction, AIVoiceCommand,
    AIMeeting, AIMeetingAction, AIContract, AIContractClause,
    AIKBArticle, AIClientChatSession, AIClientChatMessage,
    AIAgentExecution as _ExecRecord,
)
from app.models.imputation import Imputation
from app.models.project import Project
from app.models.service_desk import Ticket
from app.models.task import Task
from app.models.user import User
from app.worker import run_agent_task
from sqlalchemy import or_
from sqlalchemy.orm import joinedload

_log = logging.getLogger(__name__)


from app.services.ai_modules._base import (
    _project_internal_cost, _severity_from_probability, burnout_score, _scope_query_by_org, log_action,
)

def _oracle_project_delay(db: Session, projects: list, now: datetime) -> list:
    """Sección 1 de Oracle: detección de riesgo de retraso por proyecto.

    Devuelve la lista de alertas generadas (dicts) y muta la DB añadiendo /
    actualizando ``AIPrediction(prediction_type='project_delay')``. No commit.
    """
    from app.core.config import settings as _s  # noqa: PLC0415
    _rate_fb = float(getattr(_s, "AI_REVENUE_HOURLY_RATE_FALLBACK", 85.0) or 85.0)

    generated: list = []
    for p in projects:
        tasks = db.query(Task).filter(Task.project_id == p.id).all()
        if not tasks:
            continue
        done    = sum(1 for t in tasks if t.status == "done")
        overdue = sum(1 for t in tasks if t.status != "done" and t.due_date and t.due_date < now.date())
        pct_done = done / len(tasks)

        hours_total = db.query(func.sum(Imputation.hours)).filter(Imputation.project_id == p.id).scalar() or 0
        budget = p.budget_amount or 1
        # Tarifa: si el proyecto define billing_rate, ese gana. Si no, usar el
        # fallback global configurable (antes 100 aquí y 85 en run_oracle_health
        # → inconsistente). Centralizamos en AI_REVENUE_HOURLY_RATE_FALLBACK.
        revenue_consumed_pct = (hours_total * (getattr(p, "billing_rate", _rate_fb) or _rate_fb)) / max(budget, 1)
        # Item #83: añadimos coste interno como segunda métrica. El riesgo se
        # dispara con el PEOR de los dos — un proyecto que quema horas más
        # rápido de lo que factura debe surgir aunque parezca OK por revenue.
        cost_info_d = _project_internal_cost(db, p.id)
        cost_consumed_pct = (float(cost_info_d["cost_eur"]) / max(budget, 1)) if budget else 0.0
        budget_consumed_pct = max(revenue_consumed_pct, cost_consumed_pct)

        risk_score = 0
        if overdue > 0:
            risk_score += min(overdue / max(len(tasks), 1) * 50, 40)
        if pct_done < 0.3 and p.end_date_planned and p.end_date_planned < (now + timedelta(days=14)).date():
            risk_score += 35
        if budget_consumed_pct > 0.9:
            risk_score += 25

        probability = min(round(risk_score / 100, 2), 0.99)
        if probability < 0.25:
            continue

        severity = _severity_from_probability(probability)
        title = f"Riesgo de retraso — {p.name}"
        explanation = (
            f"El proyecto tiene {overdue} tareas vencidas de {len(tasks)} totales "
            f"({round(pct_done*100)}% completado). "
            f"Consumo facturable: {round(revenue_consumed_pct*100)}%, "
            f"coste interno: {round(cost_consumed_pct*100)}% "
            f"(método={cost_info_d['method']}, cobertura={cost_info_d['coverage_pct']}%)."
        )
        action = "Revisar tareas bloqueadas con el PM. Considerar reasignación de recursos."

        existing = db.query(AIPrediction).filter(
            AIPrediction.entity_id == p.id,
            AIPrediction.prediction_type == "project_delay",
            AIPrediction.is_acknowledged == False,
        ).first()
        if existing:
            existing.probability = probability
            existing.severity = severity
            existing.explanation = explanation
            existing.recommended_action = action
        else:
            pred = AIPrediction(
                prediction_type="project_delay", entity_type="project", entity_id=p.id,
                probability=probability, severity=severity,
                title=title, explanation=explanation, recommended_action=action,
                features_used=json.dumps({
                    "overdue_ratio": round(overdue / max(len(tasks), 1), 2),
                    "pct_done": round(pct_done, 2),
                    "budget_consumed": round(budget_consumed_pct, 2),
                    # Item #83: ambas vistas explícitas para auditoría
                    "revenue_consumed_pct": round(revenue_consumed_pct, 2),
                    "cost_consumed_pct": round(cost_consumed_pct, 2),
                    "cost_method": cost_info_d["method"],
                    "cost_coverage_pct": cost_info_d["coverage_pct"],
                }),
            )
            db.add(pred)
            generated.append({"type": "project_delay", "entity": p.name, "probability": probability})
    return generated

def _oracle_sla_breach(db: Session, open_tickets: list, now: datetime) -> list:
    """Sección 2 de Oracle: detección de riesgo de incumplimiento SLA por ticket."""
    from app.core.config import settings as _env  # noqa: PLC0415
    from app.services.settings_service import get_runtime_namespace
    _s = get_runtime_namespace(db, {
        "SLA_PREDICTION_HOURS_CRITICAL": "int",
        "SLA_PREDICTION_HOURS_HIGH": "int",
        "SLA_PREDICTION_HOURS_MEDIUM": "int",
        "SLA_PREDICTION_HOURS_LOW": "int",
        "SLA_PREDICTION_WARNING_PCT": "float",
        "SLA_PREDICTION_SEVERITY_CRITICAL_H": "float",
        "SLA_PREDICTION_SEVERITY_HIGH_H": "float",
    })
    _sla_hours = {
        "critical": _s.SLA_PREDICTION_HOURS_CRITICAL or _env.SLA_PREDICTION_HOURS_CRITICAL,
        "high":     _s.SLA_PREDICTION_HOURS_HIGH or _env.SLA_PREDICTION_HOURS_HIGH,
        "medium":   _s.SLA_PREDICTION_HOURS_MEDIUM or _env.SLA_PREDICTION_HOURS_MEDIUM,
        "low":      _s.SLA_PREDICTION_HOURS_LOW or _env.SLA_PREDICTION_HOURS_LOW,
    }

    generated: list = []
    for t in open_tickets:
        if not t.created_at:
            continue
        created_aware = t.created_at.replace(tzinfo=timezone.utc) if t.created_at.tzinfo is None else t.created_at
        age_hours = (now - created_aware).total_seconds() / 3600
        sla_limit = _sla_hours.get(t.priority or "medium", _sla_hours["medium"])
        warn_pct = _s.SLA_PREDICTION_WARNING_PCT or _env.SLA_PREDICTION_WARNING_PCT
        if age_hours < sla_limit * warn_pct:
            continue

        remaining   = sla_limit - age_hours
        probability = min(round(age_hours / sla_limit, 2), 0.99)
        crit_h      = _s.SLA_PREDICTION_SEVERITY_CRITICAL_H or _env.SLA_PREDICTION_SEVERITY_CRITICAL_H
        high_h      = _s.SLA_PREDICTION_SEVERITY_HIGH_H or _env.SLA_PREDICTION_SEVERITY_HIGH_H
        severity    = ("critical" if remaining < crit_h
                       else "high" if remaining < high_h
                       else "medium")
        existing   = db.query(AIPrediction).filter(
            AIPrediction.entity_id == t.id,
            AIPrediction.prediction_type == "sla_breach",
            AIPrediction.is_acknowledged == False,
        ).first()
        if not existing:
            db.add(AIPrediction(
                prediction_type="sla_breach", entity_type="ticket", entity_id=t.id,
                probability=probability, severity=severity,
                title=f"Riesgo de incumplimiento SLA — Ticket {t.number}",
                explanation=f"Llevas {round(age_hours,1)}h abierto. Límite SLA para prioridad '{t.priority}': {sla_limit}h. Quedan {round(remaining,1)}h.",
                recommended_action="Asignar o escalar el ticket inmediatamente.",
            ))
            generated.append({"type": "sla_breach", "entity": t.number, "probability": probability})
    return generated

def _oracle_burnout(db: Session, active_users: list, now: datetime) -> list:
    """Sección 3 de Oracle: detección de burnout por usuario activo."""
    week_starts = [(now - timedelta(weeks=i)).date() for i in range(4)]

    generated: list = []
    for u in active_users:
        weekly = []
        for ws in week_starts:
            we = ws + timedelta(days=6)
            h  = db.query(func.sum(Imputation.hours)).filter(
                Imputation.user_id == u.id,
                Imputation.date >= ws, Imputation.date <= we,
            ).scalar() or 0
            weekly.append(h)
        probability = burnout_score(weekly)
        if probability < 0.25:
            continue
        avg   = sum(weekly) / max(len(weekly), 1)
        max_w = max(weekly)
        trend = weekly[0] - weekly[-1] if len(weekly) > 1 else 0
        trend_txt = f" Tendencia: {'↑ creciente' if trend > 3 else '→ estable'}." if len(weekly) > 1 else ""
        severity = _severity_from_probability(probability)
        existing = db.query(AIPrediction).filter(
            AIPrediction.entity_id == u.id,
            AIPrediction.prediction_type == "burnout",
            AIPrediction.is_acknowledged == False,
        ).first()
        if existing:
            existing.probability = probability
            existing.severity    = severity
        else:
            db.add(AIPrediction(
                prediction_type="burnout", entity_type="user", entity_id=u.id,
                probability=probability,
                severity=severity,
                title=f"Riesgo de burnout — {u.full_name}",
                explanation=(
                    f"Media ponderada (semanas recientes 2×): {round(avg,1)}h/sem. "
                    f"Pico: {round(max_w,1)}h.{trend_txt} "
                    f"Semanas con >42h: {sum(1 for h in weekly if h > 42)}."
                ),
                recommended_action="Revisar asignaciones. Redistribuir carga de trabajo.",
            ))
            generated.append({"type": "burnout", "entity": u.full_name, "probability": probability})
    return generated

def _oracle_budget_overrun(db: Session, projects: list) -> list:
    """Sección 4 de Oracle: detección de desviación presupuestaria.

    Item #83: dos métricas:
      - revenue_ratio = hours × billing_rate / budget (lo facturable al cliente)
      - cost_ratio    = internal_cost / budget       (lo que NOS cuesta, vía UserCostProfile)
    Alerta dispara cuando CUALQUIERA supera 85%. Severidad usa el peor ratio.
    Si cost_ratio > revenue_ratio + 0.10, marcamos margen erosionado.
    """
    from app.core.config import settings as _s_oracle  # noqa: PLC0415
    _rate_fb_oracle = float(getattr(_s_oracle, "AI_REVENUE_HOURLY_RATE_FALLBACK", 85.0) or 85.0)

    generated: list = []
    for p in projects:
        if not p.budget_amount:
            continue
        hours = db.query(func.sum(Imputation.hours)).filter(Imputation.project_id == p.id).scalar() or 0
        # Revenue (lo que facturas)
        rate  = getattr(p, "billing_rate", _rate_fb_oracle) or _rate_fb_oracle
        revenue_spent = hours * rate
        revenue_ratio = revenue_spent / p.budget_amount
        # Internal cost (lo que gastas)
        cost_info = _project_internal_cost(db, p.id)
        cost_spent = float(cost_info["cost_eur"] or 0.0)
        cost_ratio = cost_spent / p.budget_amount if p.budget_amount else 0.0
        # Decisión: la peor de las dos manda
        worst_ratio = max(revenue_ratio, cost_ratio)
        if worst_ratio < 0.85:
            continue
        margin_eroded = cost_ratio > revenue_ratio + 0.10  # >10pp de gap = mal margen
        existing = db.query(AIPrediction).filter(
            AIPrediction.entity_id == p.id,
            AIPrediction.prediction_type == "budget_overrun",
            AIPrediction.is_acknowledged == False,
        ).first()
        if not existing:
            margin_note = ""
            if margin_eroded:
                margin_note = (
                    f" ⚠ Margen erosionado: coste interno {round(cost_ratio*100)}% > "
                    f"facturación {round(revenue_ratio*100)}% → posibles pérdidas reales."
                )
            db.add(AIPrediction(
                prediction_type="budget_overrun", entity_type="project", entity_id=p.id,
                probability=min(worst_ratio - 0.5, 0.99),
                severity="critical" if worst_ratio > 1 else "high",
                title=f"Desviación presupuestaria — {p.name}",
                explanation=(
                    f"Consumo facturable: {round(revenue_ratio*100)}% "
                    f"({round(revenue_spent/1000,1)}k€ de {round(p.budget_amount/1000,1)}k€). "
                    f"Coste interno: {round(cost_ratio*100)}% "
                    f"({round(cost_spent/1000,1)}k€, método={cost_info['method']}, "
                    f"cobertura datos reales={cost_info['coverage_pct']}%)."
                    f"{margin_note}"
                ),
                recommended_action=(
                    "Revisar alcance con el cliente. Preparar change order si hay trabajo extra."
                    + (" Auditar costes internos y replantear pricing del proyecto." if margin_eroded else "")
                ),
                features_used=json.dumps({
                    "revenue_ratio": round(revenue_ratio, 3),
                    "cost_ratio": round(cost_ratio, 3),
                    "hours_total": round(hours, 1),
                    "budget_eur": round(p.budget_amount, 2),
                    "revenue_eur": round(revenue_spent, 2),
                    "cost_eur": round(cost_spent, 2),
                    "cost_method": cost_info["method"],
                    "cost_coverage_pct": cost_info["coverage_pct"],
                    "margin_eroded": margin_eroded,
                }),
            ))
            generated.append({
                "type": "budget_overrun", "entity": p.name,
                "probability": round(worst_ratio - 0.5, 2),
                "revenue_ratio": round(revenue_ratio, 2),
                "cost_ratio": round(cost_ratio, 2),
                "margin_eroded": margin_eroded,
            })
    return generated

def run_oracle_analysis(db: Session, current_user) -> dict:
    """
    Runs all rule-based risk analyses and stores results as AIPrediction records.
    Returns { ok, methodology, alerts_generated, alerts, run_at }.

    Multi-tenant: cuando ``current_user.is_superadmin`` es False, todas las
    queries se filtran por ``current_user.organization_id``. Antes este job
    iteraba proyectos / tickets / users globalmente.

    Refactor #25: delega cada sección a un helper privado
    (``_oracle_project_delay``, ``_oracle_sla_breach``, ``_oracle_burnout``,
    ``_oracle_budget_overrun``) para reducir complejidad ciclomática.
    """
    now      = datetime.now(timezone.utc)
    is_super = bool(getattr(current_user, "is_superadmin", False))
    user_org = None if is_super else getattr(current_user, "organization_id", None)

    projects = _scope_query_by_org(
        db.query(Project).filter(Project.status.in_(["active", "planning"])),
        Project, user_org,
    ).all()
    open_tickets = _scope_query_by_org(
        db.query(Ticket).filter(Ticket.status.in_(["open", "in_progress"])),
        Ticket, user_org,
    ).all()
    active_users = _scope_query_by_org(
        db.query(User).filter(User.is_active == True),
        User, user_org,
    ).all()

    generated: list = []
    generated.extend(_oracle_project_delay(db, projects, now))
    generated.extend(_oracle_sla_breach(db, open_tickets, now))
    generated.extend(_oracle_burnout(db, active_users, now))
    generated.extend(_oracle_budget_overrun(db, projects))

    log_action(db, current_user.id, "contecfloworacle", "run",
               "oracle_full_analysis", f"Generated {len(generated)} predictions")
    db.commit()

    return {
        "ok": True,
        "methodology": "rules_based",
        "alerts_generated": len(generated),
        "alerts": generated,
        "run_at": datetime.now(timezone.utc).isoformat(),
    }
