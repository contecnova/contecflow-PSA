"""ai_modules.meetings — extracted from the former ai_modules_service god-file."""

from __future__ import annotations
import json
import time
import logging
from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

from app.models.ai_chat import (
    AIMeeting, AIMeetingAction,
)
from app.models.task import Task
from app.models.user import User
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

#: Tope de transcripción que se guarda en base de datos. El análisis puede
#: usar más —va por map-reduce—, pero guardar reuniones enteras infla la tabla
#: sin que nadie las lea completas.
_TOPE_DE_TRANSCRIPCION = 50000


def _json_del_modelo(texto: str) -> Optional[dict]:
    """El JSON que venga dentro de la respuesta del modelo, o `None`.

    Endurecido a propósito: un modelo devuelve JSON casi-bien —una coma
    arrastrada, texto alrededor— y antes **una sola coma** rompía toda la
    persistencia de la reunión, que caía al `except` y se guardaba como
    «Error procesando con IA». El análisis estaba bien; lo que fallaba era el
    lector.
    """
    import re

    encontrado = re.search(r"\{.*\}", texto, re.DOTALL)
    if not encontrado:
        return None
    try:
        return json.loads(encontrado.group())
    except json.JSONDecodeError:
        try:
            return json.loads(re.sub(r",\s*([}\]])", r"\1", encontrado.group()))
        except json.JSONDecodeError:
            return None


def _resolver_responsable(db: Session, nombre: str, current_user):
    """Busca por nombre al responsable de una acción, **dentro de su organización**.

    Corrección multi-tenant: sin el filtro de organización, un «Juan» en la
    transcripción podía resolverse a un Juan de cualquier otro cliente.
    """
    q = db.query(User).filter(User.full_name.ilike(f"%{nombre}%"))
    org = getattr(current_user, "organization_id", None)
    if org and not bool(getattr(current_user, "is_superadmin", False)):
        q = q.filter(User.organization_id == org)
    return q.first()


def _guardar_analisis(db: Session, meeting, data: dict, current_user) -> None:
    """Vuelca el análisis del modelo sobre la reunión y crea sus acciones."""
    meeting.title = data.get("title", meeting.title)
    meeting.summary = data.get("summary")
    meeting.decisions = json.dumps(data.get("decisions", []))
    meeting.risks_mentioned = json.dumps(data.get("risks", []))

    for accion_data in data.get("actions", []):
        accion = AIMeetingAction(
            meeting_id=meeting.id,
            description=accion_data.get("description", ""),
            assignee_name=accion_data.get("assignee_name"),
            due_date_text=accion_data.get("due_date_text"),
        )
        nombre = accion_data.get("assignee_name")
        if nombre:
            usuario = _resolver_responsable(db, nombre, current_user)
            if usuario:
                accion.assignee_id = usuario.id
        db.add(accion)


def _crear_reunion(db: Session, payload, current_user) -> AIMeeting:
    """Crea la reunión en estado `processing`, con la transcripción recortada."""
    completa = payload.transcript or ""
    meeting = AIMeeting(
        project_id=payload.project_id,
        title=payload.title or "Reunión procesada por IA",
        platform=payload.platform,
        duration_min=payload.duration_min,
        participants=json.dumps(payload.participants or []),
        transcript=completa[:_TOPE_DE_TRANSCRIPCION],
        status="processing",
        created_by=current_user.id,
    )
    # La truncación queda anotada aunque luego se sobrescriba con el resumen:
    # deja rastro en el registro de que la transcripción guardada no es entera.
    if len(completa) > _TOPE_DE_TRANSCRIPCION:
        meeting.summary = (
            f"[TRUNCADO: transcripción original {len(completa)} chars, "
            f"guardados primeros {_TOPE_DE_TRANSCRIPCION}. "
            "Para audit completo consulta el original.]"
        )
    if payload.meeting_date:
        try:
            meeting.meeting_date = datetime.fromisoformat(payload.meeting_date)
        except ValueError:
            raise ValueError("invalid_meeting_date")

    db.add(meeting)
    db.commit()
    db.refresh(meeting)
    return meeting


#: El sistema y las instrucciones del análisis map-reduce.
_SISTEMA_DE_REUNION = (
    "Eres un asistente experto en análisis de reuniones de trabajo. "
    "Analiza el texto dado y extrae puntos clave: decisiones, acciones, riesgos."
)
_PREFIJO_DE_MAPEO = "Analiza este fragmento de transcripción de reunión:"
_SUFIJO_DE_REDUCCION = """Basándote en el análisis anterior, genera el informe final completo.

Responde SOLO con JSON:
{
  "title": "...",
  "summary": "...",
  "decisions": ["...", "..."],
  "actions": [{"description": "...", "assignee_name": "...", "due_date_text": "..."}],
  "risks": ["...", "..."]
}"""


def process_meeting(db: Session, payload, current_user) -> dict:
    """Analiza la transcripción de una reunión y extrae decisiones y acciones."""
    t0 = time.time()
    meeting = _crear_reunion(db, payload, current_user)

    try:
        texto = map_reduce_analysis(
            payload.transcript,
            map_system=_SISTEMA_DE_REUNION, map_user_prefix=_PREFIJO_DE_MAPEO,
            reduce_system=_SISTEMA_DE_REUNION, reduce_user_suffix=_SUFIJO_DE_REDUCCION,
            db=db, module="meeting_assistant", user_id=current_user.id,
            map_tokens=1500, reduce_tokens=2000,
        )
        data = _json_del_modelo(texto)
        if data:
            _guardar_analisis(db, meeting, data, current_user)
        meeting.status = "done"
    except Exception as e:
        _log.exception(
            "Meeting assistant processing failed for meeting=%s",
            getattr(meeting, "id", None),
        )
        meeting.summary = f"Error procesando con IA: {str(e)[:100]}"
        meeting.status = "failed"

    latencia = int((time.time() - t0) * 1000)
    log_action(
        db, current_user.id, "meeting_assistant", "process",
        f"transcript_len={len(payload.transcript)}", meeting.summary, latency=latencia,
    )
    db.commit()
    db.refresh(meeting)

    return {
        "meeting_id": meeting.id, "title": meeting.title, "summary": meeting.summary,
        "decisions": json.loads(meeting.decisions or "[]"),
        "risks": json.loads(meeting.risks_mentioned or "[]"),
        "actions": [
            {
                "id": a.id, "description": a.description,
                "assignee_name": a.assignee_name, "due_date_text": a.due_date_text,
            }
            for a in meeting.actions
        ],
        "status": meeting.status, "latency_ms": latencia,
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
        # Auditoria 2026-11: sin codigo la insercion fallaba (NOT NULL) y daba 500.
        from app.services.numbering import next_numbered_code
        task = Task(
            code=next_numbered_code(db, "task", prefix="TSK", padding=5),
            project_id=project_id, title=action.description[:255],
            status="todo", priority="medium",
            assignee_id=action.assignee_id, created_by=current_user.id,
            reporter_id=current_user.id,
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
