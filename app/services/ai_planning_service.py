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
from app.models.service_desk import Ticket, TicketStatus
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
        # Auditoria 2026-08: `Task.actual_hours` **no existe**. Las horas
        # reales de una tarea son la suma de sus imputaciones, asi que se
        # calculan con una subconsulta y se piden solo las que tienen alguna.
        # Antes esto reventaba con `AttributeError` y la estimacion caia
        # SIEMPRE en la heuristica por palabras del titulo, que es el `else`
        # de mas abajo: la parte de «basado en tareas similares completadas»
        # no se ejecuto nunca.
        from app.models.imputation import Imputation

        horas_reales = (
            db.query(
                Imputation.task_id.label("task_id"),
                func.sum(Imputation.hours).label("reales"),
            )
            .filter(Imputation.task_id.isnot(None))
            .group_by(Imputation.task_id)
            .subquery()
        )
        similar_tasks = (
            db.query(Task, horas_reales.c.reales)
            .join(horas_reales, horas_reales.c.task_id == Task.id)
            .filter(
                Task.status == "done",
                Task.estimated_hours.isnot(None),
                horas_reales.c.reales > 0,
                Task.id != task_id,
                filters,
            )
            .limit(10)
            .all()
        )

    estimated_hours = None
    confidence = 0
    reasoning = ""
    similar_ids = []

    if similar_tasks:
        estimates = []
        # `similar_tasks` son pares (tarea, horas reales): las reales vienen de
        # la subconsulta de imputaciones, no de una columna de la tarea.
        for st, reales in similar_tasks:
            reales = float(reales or 0)
            accuracy = 1 - abs(reales - st.estimated_hours) / max(st.estimated_hours, 1)
            estimates.append((reales, max(accuracy, 0.1)))
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


#: Palabras que marcan prioridad, de más grave a menos. El orden **es** la
#: precedencia: gana la primera lista que encaje, así que un ticket que dice
#: «lento» y «producción caída» sale crítico.
#:
#: Auditoría 2026-09 (hallazgo 18): esto eran dos cascadas de `if/elif` con las
#: listas escritas en línea. Como tabla se ve de un vistazo que ninguna palabra
#: está repetida entre grupos, que era imposible de comprobar antes.
_PALABRAS_DE_PRIORIDAD: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("critical", ("caído", "down", "producción", "bloqueado", "urgente", "crítico",
                  "no funciona", "error 500")),
    ("high",     ("lento", "fallo", "problema", "no puedo", "imposible", "impide")),
    ("low",      ("consulta", "pregunta", "cómo", "información", "mejora", "sugerencia")),
)

#: Palabras que marcan categoría. Igual: gana la primera que encaje.
_PALABRAS_DE_CATEGORIA: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("Acceso y seguridad",          ("contraseña", "acceso", "login", "usuario", "permisos")),
    ("Instalación y configuración", ("instalar", "instalación", "configurar", "setup")),
    ("Red y conectividad",          ("red", "internet", "conexión", "wifi", "vpn")),
    ("Hardware y periféricos",      ("impres", "escaner", "periférico", "hardware")),
    ("Software de oficina",         ("excel", "word", "office", "correo", "email", "outlook")),
    ("Rendimiento",                 ("lento", "rendimiento", "cuelga", "memoria")),
)


def _primera_que_encaje(texto: str, tabla, por_defecto: str) -> str:
    """La primera etiqueta de la tabla cuya lista de palabras aparezca en el texto."""
    for etiqueta, palabras in tabla:
        if any(palabra in texto for palabra in palabras):
            return etiqueta
    return por_defecto


def _agente_menos_cargado(db: Session):
    """El agente con menos tickets abiertos, o `None` si no hay ninguno asignado.

    Auditoría 2026-08. Dos defectos en esta consulta:

      · `Ticket.assignee_id` **no existe**: la columna se llama
        `assigned_to_user_id`. `assignee_id` es el nombre que usa `Task`, y de
        ahí venía la confusión. Reventaba con `AttributeError`.
      · `Ticket.status.in_(["open", "in_progress"])`: **`open` no es un valor de
        `TicketStatus`**. Los abiertos son todos los que no están en `resolved`,
        `closed` ni `cancelled`, que es como lo expresa el resto del módulo.
    """
    cargas = db.query(
        Ticket.assigned_to_user_id, func.count(Ticket.id).label("open_count")
    ).filter(
        Ticket.status.notin_([
            TicketStatus.resolved, TicketStatus.closed, TicketStatus.cancelled,
        ]),
        Ticket.assigned_to_user_id.isnot(None),
    ).group_by(Ticket.assigned_to_user_id).order_by("open_count").limit(5).all()
    return cargas[0].assigned_to_user_id if cargas else None


def _afinar_con_claude(ticket, categoria: str, prioridad: str, razonamiento: str):
    """Pide a Claude una segunda opinión. Devuelve la heurística si algo falla.

    El fallo es silencioso a propósito —se registra pero no se propaga—: el
    triaje heurístico ya dio un resultado utilizable, y dejar un ticket sin
    clasificar porque la API de un tercero no responde es peor que clasificarlo
    con reglas.
    """
    api_key = settings.ANTHROPIC_API_KEY or None
    if not api_key:
        return categoria, prioridad, 60, razonamiento

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
            "messages": [{"role": "user", "content": prompt}],
        }).encode()
        req = urllib.request.Request(  # noqa: S310
            validate_outbound_url(settings.ANTHROPIC_API_URL, field="ANTHROPIC_API_URL"),
            data=data,
            headers={
                "Content-Type": "application/json",
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
            },
        )
        with urllib.request.urlopen(req, timeout=10) as resp:  # noqa: S310
            respuesta = json.loads(resp.read())
            parsed = json.loads(respuesta["content"][0]["text"])
        return (
            parsed.get("category", categoria),
            parsed.get("priority", prioridad),
            parsed.get("confidence", 75),
            parsed.get("reasoning", razonamiento) + " [Claude API]",
        )
    except Exception:
        _logger.warning(
            "Fallo llamando a Claude API para triage de ticket; usando fallback", exc_info=True,
        )
        return categoria, prioridad, 60, razonamiento


def _guardar_triaje(db: Session, ticket_id: str, *, categoria: str, prioridad: str,
                    agente_id, confianza: int, razonamiento: str) -> None:
    """Escribe o actualiza el triaje. Un ticket tiene uno, no un historial."""
    existente = db.query(AITicketTriage).filter(AITicketTriage.ticket_id == ticket_id).first()
    if existente:
        existente.suggested_category = categoria
        existente.suggested_priority = prioridad
        existente.suggested_agent_id = agente_id
        existente.confidence_pct = confianza
        existente.reasoning = razonamiento
    else:
        db.add(AITicketTriage(
            ticket_id=ticket_id,
            suggested_category=categoria,
            suggested_priority=prioridad,
            suggested_agent_id=agente_id,
            confidence_pct=confianza,
            reasoning=razonamiento,
        ))
    db.commit()


def triage_ticket(ticket_id: str, db: Session) -> dict:
    """Triaje asistido: propone categoría, prioridad y agente para un ticket."""
    ticket = db.query(Ticket).filter(Ticket.id == ticket_id).first()
    if not ticket:
        raise ValueError("ticket_not_found")

    texto = f"{(ticket.title or '').lower()} {(ticket.description or '').lower()}"
    prioridad = _primera_que_encaje(texto, _PALABRAS_DE_PRIORIDAD, "medium")
    categoria = _primera_que_encaje(texto, _PALABRAS_DE_CATEGORIA, "General")
    razonamiento = "Clasificación por reglas heurísticas."

    agente_id = _agente_menos_cargado(db)
    categoria, prioridad, confianza, razonamiento = _afinar_con_claude(
        ticket, categoria, prioridad, razonamiento,
    )

    _guardar_triaje(
        db, ticket_id, categoria=categoria, prioridad=prioridad,
        agente_id=agente_id, confianza=confianza, razonamiento=razonamiento,
    )

    agente = db.query(User).filter(User.id == agente_id).first() if agente_id else None
    return {
        "ticket_id": ticket_id,
        "ticket_title": ticket.title,
        "suggested_category": categoria,
        "suggested_priority": prioridad,
        "suggested_agent": agente.full_name if agente else None,
        "suggested_agent_id": agente_id,
        "confidence_pct": confianza,
        "reasoning": razonamiento,
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
            # Auditoria 2026-08: aqui habia `ticket.assignee_id = ...`, y esa
            # columna **no existe** en `sd_tickets` —`assignee_id` es la de
            # `Task`—. Y esto es una **asignacion**, no una lectura: SQLAlchemy
            # no se queja, se queda un atributo de Python que no persiste. Asi
            # que aceptar un triaje de IA cambiaba la prioridad y el tipo del
            # ticket y **no lo asignaba a nadie**, sin un solo error. Un fallo
            # silencioso es peor que un 500.
            if triage.suggested_agent_id:
                ticket.assigned_to_user_id = triage.suggested_agent_id
    db.commit()
    return {"ok": True, "accepted": accepted}
