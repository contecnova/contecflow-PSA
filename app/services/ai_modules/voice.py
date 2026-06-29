"""ai_modules.voice — extracted from the former ai_modules_service god-file."""

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
    call_ai_unified, log_action,
)

def _voice_parse_intent(db, transcript: str, current_user) -> tuple:
    """Llama al LLM con el transcript y extrae (intent, entities, action_description).

    Devuelve siempre una tupla 3 — fallback a ("unknown", {}, "...") si el LLM
    falla o el JSON no parsea.
    """
    import re as _re
    intent = "unknown"
    entities: dict = {}
    action_taken = ""
    try:
        prompt = f"""Analiza este comando de voz de un usuario de Contecflow y extrae:
- intent: log_hours | create_ticket | query_hours | create_task | get_summary | other
- entities: objetos relevantes (project_name, hours, task_name, date, ticket_title, priority, etc.)

Comando: "{transcript}"
Usuario: {current_user.full_name}
Hoy: {datetime.now(timezone.utc).strftime('%Y-%m-%d')}

Responde SOLO con JSON: {{"intent": "...", "entities": {{...}}, "action_description": "..."}}"""
        text = call_ai_unified(
            db, [{"role": "user", "content": prompt}],
            module="voice", user_id=current_user.id, max_tokens=300
        )
        match = _re.search(r'\{.*\}', text, _re.DOTALL)
        if match:
            try:
                data = json.loads(match.group())
                intent = data.get("intent", "unknown")
                entities = data.get("entities", {})
                action_taken = data.get("action_description", "")
            # intentional: best-effort fallback, log noise outweighs diagnostic value
            except json.JSONDecodeError:
                pass
    except Exception as e:
        _log.warning(f"Voice command parsing failed: {e}")
        intent = "unknown"
        action_taken = "Error en IA, modo fallback activado"
    return intent, entities, action_taken

def _voice_find_project_scoped(db, name_pattern: str, cu_org, is_super_cu: bool):
    """Busca un Project por ``name ilike %pattern%`` filtrado por organization."""
    q = db.query(Project).filter(Project.name.ilike(f"%{name_pattern}%"))
    if cu_org and not is_super_cu:
        q = q.filter(Project.organization_id == cu_org)
    return q.first()

def _voice_handle_log_hours(db, current_user, transcript: str, entities: dict,
                            project, confirm: bool, result: dict) -> None:
    """Handler para intent ``log_hours``. Muta ``result`` in place."""
    if not project:
        result["action"] = f"No encontré el proyecto '{entities['project_name']}'."
        return
    if not confirm:
        result["action"] = (
            f"⏳ Propuesta: registrar {entities['hours']}h en {project.name}. "
            f"Confirma para ejecutar."
        )
        result["pending_action"] = {
            "type": "log_hours",
            "project_id": project.id,
            "project_name": project.name,
            "hours": float(entities["hours"]),
        }
        return
    imp = Imputation(
        user_id=current_user.id, project_id=project.id,
        hours=float(entities["hours"]),
        date=date.today(),
        description=f"Imputado por voz: {transcript[:100]}",
        is_billable=True,
    )
    db.add(imp)
    result["action"] = f"✓ Registradas {entities['hours']}h en {project.name}"

def _voice_handle_create_ticket(db, current_user, entities: dict,
                                confirm: bool, result: dict) -> None:
    """Handler para intent ``create_ticket``. Muta ``result`` in place."""
    if not confirm:
        result["action"] = (
            f"⏳ Propuesta: crear ticket '{entities['ticket_title']}'. Confirma para ejecutar."
        )
        result["pending_action"] = {
            "type": "create_ticket",
            "title": entities["ticket_title"],
            "priority": entities.get("priority", "medium"),
        }
        return
    ticket = Ticket(
        title=entities["ticket_title"],
        priority=entities.get("priority", "medium"),
        status="open",
        requester_user_id=current_user.id,
    )
    db.add(ticket); db.flush()
    result["action"] = f"✓ Ticket creado: {ticket.title}"

def _voice_handle_query_hours(db, current_user, result: dict) -> None:
    """Handler para intent ``query_hours`` (sólo lectura, no requiere confirm)."""
    week_start = (date.today() - timedelta(days=date.today().weekday()))
    hours = db.query(func.sum(Imputation.hours)).filter(
        Imputation.user_id == current_user.id,
        Imputation.date >= week_start,
    ).scalar() or 0
    result["action"] = f"Esta semana llevas {round(hours, 1)} horas imputadas."

def _voice_handle_create_task(db, current_user, entities: dict, project,
                              confirm: bool, result: dict) -> None:
    """Handler para intent ``create_task``. Muta ``result`` in place."""
    if not confirm:
        result["action"] = (
            f"⏳ Propuesta: crear tarea '{entities['task_name']}'"
            + (f" en {project.name}" if project else "")
            + ". Confirma para ejecutar."
        )
        result["pending_action"] = {
            "type": "create_task",
            "title": entities["task_name"][:255],
            "project_id": project.id if project else None,
            "project_name": project.name if project else None,
            "priority": entities.get("priority", "medium"),
        }
        return
    task = Task(
        title=entities["task_name"][:255],
        project_id=project.id if project else None,
        status="todo",
        priority=entities.get("priority", "medium"),
        created_by=current_user.id,
    )
    db.add(task); db.flush()
    result["action"] = f"✓ Tarea creada: {task.title}"
    if project:
        result["action"] += f" en {project.name}"

def _voice_handle_get_summary(db, entities: dict, result: dict) -> None:
    """Handler para intent ``get_summary`` (sólo lectura)."""
    project = db.query(Project).filter(
        Project.name.ilike(f"%{entities['project_name']}%")
    ).first()
    if project:
        tasks = db.query(Task).filter(Task.project_id == project.id).all()
        done = sum(1 for t in tasks if t.status == "done")
        open_tasks = sum(1 for t in tasks if t.status != "done")
        result["action"] = (
            f"Proyecto '{project.name}': {round(done / max(len(tasks), 1) * 100)}% completado, "
            f"{open_tasks} tareas pendientes, estado: {project.status}."
        )
    else:
        result["action"] = f"No encontré el proyecto '{entities['project_name']}'."

def _voice_handle_other(db, current_user, transcript: str, result: dict) -> None:
    """Handler para intent ``other`` (>20 chars): dispara agente async."""
    exec_record = _ExecRecord(
        user_id=current_user.id,
        instruction=transcript,
        status="queued",
    )
    db.add(exec_record); db.flush()
    run_agent_task.delay(str(exec_record.id), transcript, str(current_user.id))
    result["action"] = (
        f"Comando enviado al agente (ID: {str(exec_record.id)[:8]}). "
        "Revisa el historial de ContecflowAgent para el resultado."
    )
    result["execution_id"] = str(exec_record.id)

def process_voice_core(transcript: str, db, current_user,
                       *, confirm: bool = False) -> dict:
    """Shared voice command processing logic.

    Modo "dry-run" (``confirm=False``, default): el LLM extrae intent +
    entities, busca el target (project/task), pero NO ejecuta la acción.
    Devuelve un resumen para que el cliente muestre confirmación humana.

    Modo "confirm" (``confirm=True``): ejecuta la acción sugerida.

    Antes este servicio ejecutaba directamente — un Whisper que
    transcribiera mal "3h" → "30h" registraba 30h sin confirmación.

    Refactor #25: extracción a helpers ``_voice_*`` por intent para reducir
    complejidad ciclomática (de >15 a ~6).
    """
    t0 = time.time()
    status = "done"

    intent, entities, action_taken = _voice_parse_intent(db, transcript, current_user)

    result: dict = {
        "intent": intent, "entities": entities, "action": action_taken,
        "confirmed": confirm,
    }

    # Multi-tenant: limitar matching de proyectos a la org del current_user
    cu_org = getattr(current_user, "organization_id", None)
    is_super_cu = bool(getattr(current_user, "is_superadmin", False))

    if intent == "log_hours" and entities.get("hours") and entities.get("project_name"):
        project = _voice_find_project_scoped(db, entities['project_name'], cu_org, is_super_cu)
        _voice_handle_log_hours(db, current_user, transcript, entities, project, confirm, result)
    elif intent == "create_ticket" and entities.get("ticket_title"):
        _voice_handle_create_ticket(db, current_user, entities, confirm, result)
    elif intent == "query_hours":
        _voice_handle_query_hours(db, current_user, result)
    elif intent == "create_task" and entities.get("task_name"):
        project = None
        if entities.get("project_name"):
            project = _voice_find_project_scoped(db, entities['project_name'], cu_org, is_super_cu)
        _voice_handle_create_task(db, current_user, entities, project, confirm, result)
    elif intent == "get_summary" and entities.get("project_name"):
        _voice_handle_get_summary(db, entities, result)
    elif intent == "other" and len(transcript.strip()) > 20:
        _voice_handle_other(db, current_user, transcript, result)

    latency = int((time.time() - t0) * 1000)
    vc = AIVoiceCommand(
        user_id=current_user.id,
        transcript=transcript,
        intent=intent,
        entities=json.dumps(entities),
        action_taken=result.get("action", ""),
        status=status,
    )
    db.add(vc)
    log_action(db, current_user.id, "voice", "command", transcript[:200],
               result.get("action", ""), latency=latency)
    db.commit()

    return {
        "transcript": transcript,
        "intent": intent,
        "entities": entities,
        "action": result.get("action", action_taken),
        "status": status,
        "latency_ms": latency,
    }
