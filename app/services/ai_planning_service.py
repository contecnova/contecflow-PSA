"""Planificacion asistida: estimacion de tareas y triaje de tickets.

Auditoria 2026-08 (hallazgo 22). Este codigo vivia en `mfa_service.py`, un
fichero de 1.435 lineas que contenia OCHO dominios sin relacion entre si —MFA,
organizaciones, Slack, presupuestos, planificacion asistida, escenarios, PDF y
tokens de BI— servidos ademas por un unico router llamado `mfa.py` con 38 rutas.

El reparto se pudo hacer mecanicamente porque los ocho dominios nunca estuvieron
acoplados, solo apilados: se comprobo por AST que no habia ni una llamada entre
grupos ni un solo ciclo. Los cuerpos se movieron verbatim.
"""

import json
import logging
from datetime import datetime, timezone
from sqlalchemy.orm import Session
from sqlalchemy import func
from app.core.config import settings
from app.core.outbound_url import validate_outbound_url
from app.models.user import User
from app.models.task import Task
from app.models.service_desk import Ticket
from app.models.mfa import (
    AITaskEstimate, AITicketTriage,
)
from sqlalchemy import or_ as sql_or

_logger = logging.getLogger(__name__)


def estimate_task_hours(task_id: str, db: Session) -> dict:
    """Estimate task hours using historical similar tasks or heuristics + optional Claude API."""

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
                "model": settings.CONTECFLOW_AI_MODEL,
                "max_tokens": 200,
                "messages": [{"role": "user", "content": prompt}]
            }).encode()
            req = urllib.request.Request(  # noqa: S310
                validate_outbound_url(settings.ANTHROPIC_API_URL, field="ANTHROPIC_API_URL"),
                data=data,
                headers={
                    "Content-Type": "application/json",
                    "x-api-key": api_key,
                    "anthropic-version": "2023-06-01",
                }
            )
            with urllib.request.urlopen(req, timeout=10) as resp:  # noqa: S310
                result = json.loads(resp.read())
                text = result["content"][0]["text"]
                parsed = json.loads(text)
                estimated_hours = parsed["hours"]
                confidence = parsed.get("confidence", confidence)
                reasoning = parsed.get("reasoning", reasoning) + " [Claude API]"
        except Exception:
            _logger.warning("Fallo llamando a Claude API para estimación de horas; usando fallback", exc_info=True)

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
                "model": settings.CONTECFLOW_AI_MODEL,
                "max_tokens": 300,
                "messages": [{"role": "user", "content": prompt}]
            }).encode()
            req = urllib.request.Request(  # noqa: S310
                validate_outbound_url(settings.ANTHROPIC_API_URL, field="ANTHROPIC_API_URL"),
                data=data,
                headers={
                    "Content-Type": "application/json",
                    "x-api-key": api_key,
                    "anthropic-version": "2023-06-01",
                }
            )
            with urllib.request.urlopen(req, timeout=10) as resp:  # noqa: S310
                result = json.loads(resp.read())
                parsed = json.loads(result["content"][0]["text"])
                suggested_category = parsed.get("category", suggested_category)
                suggested_priority = parsed.get("priority", suggested_priority)
                confidence = parsed.get("confidence", 75)
                reasoning = parsed.get("reasoning", reasoning) + " [Claude API]"
        except Exception:
            _logger.warning("Fallo llamando a Claude API para triage de ticket; usando fallback", exc_info=True)

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
