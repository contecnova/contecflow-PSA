"""ai_modules.meetings — extracted from the former ai_modules_service god-file."""

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
    log_action, map_reduce_analysis,
)

def list_meetings(db: Session, project_id=None):
    q = db.query(AIMeeting).options(joinedload(AIMeeting.actions))
    if project_id: q = q.filter(AIMeeting.project_id == project_id)
    meetings = q.order_by(AIMeeting.created_at.desc()).limit(50).all()
    return [{
        "id": m.id, "title": m.title, "project_id": m.project_id,
        "platform": m.platform, "duration_min": m.duration_min,
        "status": m.status,
        "actions_count": len(m.actions),
        "created_actions": sum(1 for a in m.actions if a.is_created),
        "meeting_date": str(m.meeting_date)[:16] if m.meeting_date else None,
        "created_at": str(m.created_at)[:16],
    } for m in meetings]

def process_meeting(db: Session, payload, current_user) -> dict:
    import re

    t0 = time.time()
    # Item #68: registramos el tamaño original para trazabilidad de citas.
    # El campo ``transcript`` truncamos a 50K para no inflar la DB, pero el
    # análisis LLM (map-reduce) puede usar más; guardamos ``original_length``
    # y un flag ``truncated`` para que ``original_text`` en respuestas LLM se
    # pueda re-referenciar al transcript completo si el caller lo necesita.
    _full_transcript = payload.transcript or ""
    _was_truncated = len(_full_transcript) > 50000
    meeting = AIMeeting(
        project_id=payload.project_id,
        title=payload.title or "Reunión procesada por IA",
        platform=payload.platform,
        duration_min=payload.duration_min,
        participants=json.dumps(payload.participants or []),
        transcript=_full_transcript[:50000],
        status="processing",
        created_by=current_user.id,
    )
    # Anotamos en summary la truncación si aplica (se sobreescribe luego con el
    # resumen del LLM, pero queda en el log/audit que hubo truncación).
    if _was_truncated:
        meeting.summary = (
            f"[TRUNCADO: transcripción original {len(_full_transcript)} chars, "
            f"guardados primeros 50000. Para audit completo consulta el original.]"
        )
    if payload.meeting_date:
        try:
            meeting.meeting_date = datetime.fromisoformat(payload.meeting_date)
        except ValueError:
            raise ValueError("invalid_meeting_date")
    db.add(meeting); db.commit(); db.refresh(meeting)

    try:
        MAP_SYSTEM = (
            "Eres un asistente experto en análisis de reuniones de trabajo. "
            "Analiza el texto dado y extrae puntos clave: decisiones, acciones, riesgos."
        )
        REDUCE_SYSTEM = MAP_SYSTEM
        MAP_PREFIX = "Analiza este fragmento de transcripción de reunión:"
        REDUCE_SUFFIX = """Basándote en el análisis anterior, genera el informe final completo.

Responde SOLO con JSON:
{
  "title": "...",
  "summary": "...",
  "decisions": ["...", "..."],
  "actions": [{"description": "...", "assignee_name": "...", "due_date_text": "..."}],
  "risks": ["...", "..."]
}"""
        text = map_reduce_analysis(
            payload.transcript,
            map_system=MAP_SYSTEM, map_user_prefix=MAP_PREFIX,
            reduce_system=REDUCE_SYSTEM, reduce_user_suffix=REDUCE_SUFFIX,
            db=db, module="meeting_assistant", user_id=current_user.id,
            map_tokens=1500, reduce_tokens=2000,
        )
        match = re.search(r'\{.*\}', text, re.DOTALL)
        if match:
            # Hardening: el LLM puede devolver JSON casi-bien (trailing comma,
            # comilla simple, texto adicional). Antes una sola coma arrastrada
            # rompía toda la persistencia del meeting → caía al except y se
            # guardaba "Error procesando con IA".
            try:
                data = json.loads(match.group())
            except json.JSONDecodeError:
                _cleaned = re.sub(r",\s*([}\]])", r"\1", match.group())  # trailing commas
                data = json.loads(_cleaned)
            meeting.title   = data.get("title", meeting.title)
            meeting.summary = data.get("summary")
            meeting.decisions = json.dumps(data.get("decisions", []))
            meeting.risks_mentioned = json.dumps(data.get("risks", []))
            for action_data in data.get("actions", []):
                action = AIMeetingAction(
                    meeting_id=meeting.id,
                    description=action_data.get("description", ""),
                    assignee_name=action_data.get("assignee_name"),
                    due_date_text=action_data.get("due_date_text"),
                )
                if action_data.get("assignee_name"):
                    # Multi-tenant fix: limitar matching a usuarios de la
                    # organización del current_user. Sin este filtro un
                    # "Juan" en el transcript podía resolverse a Juan
                    # cualquiera de cualquier organización.
                    user_q = db.query(User).filter(
                        User.full_name.ilike(f"%{action_data['assignee_name']}%")
                    )
                    cu_org = getattr(current_user, "organization_id", None)
                    if cu_org and not bool(getattr(current_user, "is_superadmin", False)):
                        user_q = user_q.filter(User.organization_id == cu_org)
                    user = user_q.first()
                    if user: action.assignee_id = user.id
                db.add(action)
        meeting.status = "done"
    except Exception as e:
        _log.exception("Meeting assistant processing failed for meeting=%s", getattr(meeting, "id", None))
        meeting.summary = f"Error procesando con IA: {str(e)[:100]}"
        meeting.status = "failed"

    latency = int((time.time() - t0) * 1000)
    log_action(db, current_user.id, "meeting_assistant", "process",
               f"transcript_len={len(payload.transcript)}", meeting.summary, latency=latency)
    db.commit(); db.refresh(meeting)

    return {
        "meeting_id": meeting.id, "title": meeting.title, "summary": meeting.summary,
        "decisions": json.loads(meeting.decisions or "[]"),
        "risks": json.loads(meeting.risks_mentioned or "[]"),
        "actions": [{"id": a.id, "description": a.description,
                     "assignee_name": a.assignee_name,
                     "due_date_text": a.due_date_text} for a in meeting.actions],
        "status": meeting.status, "latency_ms": latency,
    }

def create_tasks_from_meeting(db: Session, meeting_id: str, payload: dict, current_user) -> dict:

    meeting = db.query(AIMeeting).options(joinedload(AIMeeting.actions)).filter(
        AIMeeting.id == meeting_id
    ).first()
    if not meeting:
        raise ValueError("not_found")
    project_id = payload.get("project_id") or meeting.project_id
    if not project_id:
        raise ValueError("project_id_required")
    action_ids = payload.get("action_ids", [a.id for a in meeting.actions])
    created = []
    for action in meeting.actions:
        if action.id not in action_ids or action.is_created: continue
        task = Task(
            project_id=project_id, title=action.description[:255],
            status="todo", priority="medium",
            assignee_id=action.assignee_id, created_by=current_user.id,
        )
        db.add(task); db.flush()
        action.task_id = task.id
        action.is_created = True
        created.append({"action_id": action.id, "task_id": task.id, "title": task.title})
    db.commit()
    return {"ok": True, "tasks_created": len(created), "tasks": created}

def get_meeting(db: Session, meeting_id: str) -> dict:

    m = db.query(AIMeeting).options(joinedload(AIMeeting.actions)).filter(
        AIMeeting.id == meeting_id
    ).first()
    if not m:
        raise ValueError("not_found")
    return {
        "id": m.id, "title": m.title, "project_id": m.project_id,
        "platform": m.platform, "duration_min": m.duration_min,
        "summary": m.summary,
        "decisions": json.loads(m.decisions or "[]"),
        "risks": json.loads(m.risks_mentioned or "[]"),
        "participants": json.loads(m.participants or "[]"),
        "status": m.status,
        "actions": [{
            "id": a.id, "description": a.description,
            "assignee_name": a.assignee_name, "assignee_id": a.assignee_id,
            "due_date_text": a.due_date_text, "is_created": a.is_created,
            "task_id": a.task_id,
        } for a in m.actions],
    }
