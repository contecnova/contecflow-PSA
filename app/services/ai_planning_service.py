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


def _tareas_similares(db: Session, task, task_id: str) -> list[tuple]:
    """Tareas parecidas ya cerradas, con sus **horas reales**.

    Devuelve pares `(tarea, horas_reales)`.

    Auditoría 2026-08: `Task.actual_hours` **no existe**. Las horas reales de
    una tarea son la suma de sus imputaciones, así que se calculan con una
    subconsulta y sólo se piden las que tienen alguna. Antes esto reventaba con
    `AttributeError` y la estimación caía SIEMPRE en la heurística por palabras
    del título: la parte de «basado en tareas similares completadas» no se
    ejecutó nunca.
    """
    from app.models.imputation import Imputation

    palabras = [w for w in (task.title or "").lower().split() if len(w) > 3]
    if not palabras:
        return []

    horas_reales = (
        db.query(
            Imputation.task_id.label("task_id"),
            func.sum(Imputation.hours).label("reales"),
        )
        .filter(Imputation.task_id.isnot(None))
        .group_by(Imputation.task_id)
        .subquery()
    )
    return (
        db.query(Task, horas_reales.c.reales)
        .join(horas_reales, horas_reales.c.task_id == Task.id)
        .filter(
            Task.status == "done",
            Task.estimated_hours.isnot(None),
            horas_reales.c.reales > 0,
            Task.id != task_id,
            sql_or(*[func.lower(Task.title).contains(kw) for kw in palabras[:5]]),
        )
        .limit(10)
        .all()
    )


def _estimar_por_historial(similares: list[tuple]) -> tuple[float, int, str, list]:
    """Media de horas reales ponderada por lo bien que se estimó cada una.

    La precisión histórica es el peso: una tarea que se estimó bien pesa más
    que una que se pasó por el triple. El suelo de 0,1 evita que una estimación
    pésima quede en peso cero y desaparezca del cálculo.
    """
    estimaciones = []
    ids = []
    for tarea, reales in similares:
        reales = float(reales or 0)
        precision = 1 - abs(reales - tarea.estimated_hours) / max(tarea.estimated_hours, 1)
        estimaciones.append((reales, max(precision, 0.1)))
        ids.append(tarea.id)

    peso_total = sum(w for _, w in estimaciones)
    horas = round(sum(h * w for h, w in estimaciones) / peso_total, 1)
    confianza = min(round(len(similares) / 10 * 70 + 20), 85)
    return horas, confianza, (
        f"Basado en {len(similares)} tareas similares completadas. "
        "Promedio ponderado por precisión histórica."
    ), ids


#: Palabras del título que mueven la estimación heurística, y cuánto. Un `+N`
#: suma sobre la base; un número suelto la **sustituye**, porque un arreglo o
#: una prueba son trabajos acotados por naturaleza. La última que encaje manda.
_HEURISTICA_DE_TITULO: tuple[tuple[tuple[str, ...], str, float], ...] = (
    (("implementar", "desarrollar", "crear", "diseñar"), "suma", 4),
    (("integración", "migración", "refactor"), "suma", 6),
    (("fix", "corrección", "bug", "error"), "fija", 2),
    (("test", "prueba", "validar"), "fija", 3),
)


def _estimar_por_heuristica(task) -> tuple[float, int, str, list]:
    """Estimación por las palabras del título, cuando no hay historial."""
    titulo = (task.title or "").lower()
    horas = 4.0
    for palabras, modo, valor in _HEURISTICA_DE_TITULO:
        if any(w in titulo for w in palabras):
            horas = horas + valor if modo == "suma" else valor
    return round(horas, 1), 30, (
        "Sin tareas similares en el historial. Estimación heurística por tipo de tarea."
    ), []


def _afinar_estimacion_con_claude(task, similares: list[tuple], horas, confianza, razon):
    """Pide a Claude una segunda opinión sobre la estimación.

    Auditoría 2026-09 (hallazgo 18): al sacar esto a su propia función se vio
    que **nunca había funcionado**. El contexto se construía con
    `for t in similar_tasks[:5]` leyendo `t.title` y `t.actual_hours`, pero
    `similar_tasks` son filas `(Task, horas_reales)`: `t.title` levantaba
    `AttributeError` sobre la fila, y `actual_hours` es justo la columna que el
    hallazgo de 2026-08 ya documentó como inexistente. Las dos excepciones caían
    en el `except Exception` de abajo, que registraba un aviso y seguía con la
    estimación anterior. El resultado era correcto por accidente; el refinamiento
    no se ha ejecutado jamás.

    Ahora el par se desempaqueta como par, y las horas reales salen de donde
    salen: de la suma de imputaciones que ya trae la consulta.
    """
    api_key = settings.ANTHROPIC_API_KEY or None
    if not api_key or not similares:
        return horas, confianza, razon

    try:
        import urllib.request

        contexto = "\n".join([
            f"- '{tarea.title}': estimado {tarea.estimated_hours}h, real {float(reales or 0)}h"
            for tarea, reales in similares[:5]
        ])
        prompt = f"""Tarea a estimar: "{task.title}"
Proyecto: {task.project.name if task.project else "—"}
Descripción: {(task.description or "Sin descripción")[:200]}

Tareas similares completadas:
{contexto}

Responde SOLO con JSON: {{"hours": <número>, "confidence": <0-100>, "reasoning": "<explicación breve>"}}"""

        data = json.dumps({
            "model": settings.CONTECFLOW_AI_MODEL,
            "max_tokens": 200,
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
            parsed = json.loads(json.loads(resp.read())["content"][0]["text"])
        return (
            parsed["hours"],
            parsed.get("confidence", confianza),
            parsed.get("reasoning", razon) + " [Claude API]",
        )
    except Exception:
        _logger.warning(
            "Fallo llamando a Claude API para estimación de horas; usando fallback",
            exc_info=True,
        )
        return horas, confianza, razon


def _guardar_estimacion(db: Session, task_id: str, *, horas, confianza, razon,
                        ids_similares: list, con_api: bool) -> None:
    """Escribe o actualiza la estimación. Una tarea tiene una, no un historial."""
    existente = db.query(AITaskEstimate).filter(AITaskEstimate.task_id == task_id).first()
    if existente:
        existente.estimated_hours = horas
        existente.confidence_pct = confianza
        existente.reasoning = razon
        existente.similar_tasks = json.dumps(ids_similares)
        db.commit()
        return
    db.add(AITaskEstimate(
        task_id=task_id,
        estimated_hours=horas,
        confidence_pct=confianza,
        reasoning=razon,
        similar_tasks=json.dumps(ids_similares),
        model_used="claude_api" if con_api else "rule_based",
    ))
    db.commit()


def estimate_task_hours(task_id: str, db: Session) -> dict:
    """Estima las horas de una tarea con el historial, o con heurística si no hay."""
    from sqlalchemy.orm import joinedload

    task = (
        db.query(Task).options(joinedload(Task.project))
        .filter(Task.id == task_id).first()
    )
    if not task:
        raise ValueError("task_not_found")

    similares = _tareas_similares(db, task, task_id)
    if similares:
        horas, confianza, razon, ids = _estimar_por_historial(similares)
    else:
        horas, confianza, razon, ids = _estimar_por_heuristica(task)

    horas, confianza, razon = _afinar_estimacion_con_claude(
        task, similares, horas, confianza, razon,
    )

    _guardar_estimacion(
        db, task_id, horas=horas, confianza=confianza, razon=razon,
        ids_similares=ids, con_api=bool(settings.ANTHROPIC_API_KEY),
    )

    return {
        "task_id": task_id,
        "task_title": task.title,
        "estimated_hours": horas,
        "confidence_pct": confianza,
        "reasoning": razon,
        "similar_count": len(similares),
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
            if triage.suggested_priority:
                from app.services.service_desk.ticket_update_service import cambiar_prioridad
                cambiar_prioridad(db, ticket, triage.suggested_priority)
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
