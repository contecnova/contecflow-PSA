"""ai_modules.voice — extracted from the former ai_modules_service god-file."""

from __future__ import annotations
import json
import time
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import func

from app.core.constantes import NOMBRE_DEL_PRODUCTO
from app.models.ai_chat import (
    AIVoiceCommand, AIAgentExecution as _ExecRecord,
)
from app.models.imputation import Imputation
from app.models.project import Project
from app.models.service_desk import Ticket
from app.models.task import Task
from app.core.segundo_plano import enviar_tarea
from app.core import timeutil
from app.core.config import settings  # topes de tokens de IA (19-11-2026)

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
        prompt = f"""Analiza este comando de voz de un usuario de {NOMBRE_DEL_PRODUCTO} y extrae:
- intent: log_hours | create_ticket | query_hours | create_task | get_summary | other
- entities: objetos relevantes (project_name, hours, task_name, date, ticket_title, priority, etc.)

Comando: "{transcript}"
Usuario: {current_user.full_name}
Hoy: {datetime.now(timezone.utc).strftime('%Y-%m-%d')}

Responde SOLO con JSON: {{"intent": "...", "entities": {{...}}, "action_description": "..."}}"""
        text = call_ai_unified(
            db, [{"role": "user", "content": prompt}],
            module="voice", user_id=current_user.id, max_tokens=settings.AI_BRIEF_ANSWER_MAX_TOKENS
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

def _voice_find_project_scoped(db, name_pattern: str, current_user):
    """Busca un Project por ``name ilike %pattern%`` entre los que el usuario ve.

    Segunda auditoria 2026-11: se filtraba solo por organizacion (y el resumen
    `get_summary` ni eso), asi que un empleado obtenia por voz el avance de
    cualquier proyecto. Ahora pasa por `scope_projects_query`, la misma regla
    de organizacion + rol + permisos por proyecto que el listado.
    """
    from app.services.project_service import scope_projects_query
    q = db.query(Project).filter(Project.name.ilike(f"%{name_pattern}%"))
    return scope_projects_query(q, db, current_user).order_by(Project.name).first()

# ── Propuesta firmada (auditoría 22-11-2026, A6) ─────────────────────────────
#
# Antes `confirm=True` volvía a llamar al LLM con la transcripción y ejecutaba
# lo que saliera esta vez (podía ser otra cosa que lo propuesto), con
# `Imputation(...)`/`Task(...)`/`Ticket(status="open")` a mano: sin cierre de
# periodo, topes ni pertenencia, y con un estado de ticket que no existe.
# Ahora la propuesta (`pending_action`) va FIRMADA (HMAC con la clave del
# servidor, el usuario y una caducidad) y confirmar ejecuta exactamente esa
# propuesta, sin LLM, con los servicios normales de cada dominio.

_VIGENCIA_DE_LA_PROPUESTA_S = 600


def _clave_de_firma() -> bytes:
    return (str(settings.SECRET_KEY) + ":voz:propuesta").encode()


def _firmar_propuesta(accion: dict, user_id: str) -> str:
    import base64
    import hashlib
    import hmac
    cuerpo = dict(accion, _u=user_id, _exp=int(time.time()) + _VIGENCIA_DE_LA_PROPUESTA_S)
    datos = base64.urlsafe_b64encode(json.dumps(cuerpo, sort_keys=True, default=str).encode()).decode()
    firma = hmac.new(_clave_de_firma(), datos.encode(), hashlib.sha256).hexdigest()
    return f"{datos}.{firma}"


def _verificar_propuesta(token: str, user_id: str) -> dict:
    import base64
    import hashlib
    import hmac
    from app.core.codigos_de_error import error
    try:
        datos, firma = (token or "").rsplit(".", 1)
        esperada = hmac.new(_clave_de_firma(), datos.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(firma, esperada):
            raise ValueError("voz_firma_no_valida")
        cuerpo = json.loads(base64.urlsafe_b64decode(datos.encode()))
    except Exception:
        raise error(400, "voz_propuesta_no_valida")
    if cuerpo.get("_u") != user_id or int(cuerpo.get("_exp") or 0) < int(time.time()):
        raise error(400, "voz_propuesta_no_valida")
    return cuerpo


def _t(db, current_user, clave: str, **params) -> str:
    """Texto `voz.<clave>` en el idioma de la persona (23-11-2026: antes castellano fijo)."""
    from app.services.formato_regional import idioma_de_salida
    from app.services.textos_de_salida import texto
    idioma = idioma_de_salida(db, user_id=getattr(current_user, "id", None),
                              org_id=getattr(current_user, "organization_id", None))
    return texto(f"voz.{clave}", idioma, **params)


def _proponer(result: dict, accion: dict, current_user) -> None:
    result["pending_action"] = dict(accion, token=_firmar_propuesta(accion, current_user.id))


def _ejecutar_propuesta(db, current_user, accion: dict, transcript: str) -> str:
    """Ejecuta la propuesta firmada con el servicio de su dominio. Devuelve el texto."""
    from app.services.project_service import scope_projects_query
    tipo = accion.get("type")
    if tipo == "log_hours":
        from app.services.imputation_service.alta import crear_imputacion_validada
        proyecto = scope_projects_query(db.query(Project).filter(Project.id == accion.get("project_id")),
                                        db, current_user).first()
        if not proyecto:
            from app.core.codigos_de_error import error
            raise error(404, "no_encontrado", que="proyecto")
        crear_imputacion_validada(current_user, db, project_id=proyecto.id, fecha=timeutil.today_for_user(current_user),
                                  horas=float(accion.get("hours") or 0),
                                  description=f"Imputado por voz: {transcript[:100]}",
                                  is_billable=bool(proyecto.is_billable))
        return _t(db, current_user, "registradas", horas=accion.get("hours"), proyecto=proyecto.name)
    if tipo == "create_task":
        from app.schemas.tasks import TaskCreate
        from app.services.task_service import create_task_record
        if not accion.get("project_id"):
            from app.core.codigos_de_error import error
            raise error(400, "elige_proyecto")
        prioridad = accion.get("priority") if accion.get("priority") in ("low", "medium", "high", "critical") else "medium"
        task = create_task_record(db, TaskCreate(title=str(accion.get("title") or "")[:255],
                                                 project_id=accion["project_id"], priority=prioridad), current_user)
        return (_t(db, current_user, "tarea_creada_en", titulo=task.title, proyecto=accion["project_name"])
                if accion.get("project_name") else _t(db, current_user, "tarea_creada", titulo=task.title))
    if tipo == "create_ticket":
        from app.schemas.service_desk import TicketCreateIn
        from app.services.service_desk.ticket_creation_service import build_internal_ticket
        urgencia = accion.get("priority") if accion.get("priority") in ("low", "medium", "high", "critical") else "medium"
        titulo = str(accion.get("title") or "")[:255]
        ticket = build_internal_ticket(db, TicketCreateIn(title=titulo, description=titulo, urgency=urgencia),
                                       current_user.id)
        db.add(ticket)
        db.flush()
        return _t(db, current_user, "ticket_creado", ticket=ticket.number or ticket.title)
    from app.core.codigos_de_error import error
    raise error(400, "voz_propuesta_no_valida")


def _voice_handle_log_hours(db, current_user, transcript: str, entities: dict,
                            project, confirm: bool, result: dict) -> None:
    """Handler para intent ``log_hours`` (solo propone: ver `_ejecutar_propuesta`)."""
    if not project:
        result["action"] = _t(db, current_user, "proyecto_no_encontrado", nombre=entities['project_name'])
        return
    result["action"] = _t(db, current_user, "propuesta_horas", horas=entities['hours'], proyecto=project.name)
    _proponer(result, {
        "type": "log_hours",
        "project_id": project.id,
        "project_name": project.name,
        "hours": float(entities["hours"]),
    }, current_user)

def _voice_handle_create_ticket(db, current_user, entities: dict,
                                confirm: bool, result: dict) -> None:
    """Handler para intent ``create_ticket`` (solo propone)."""
    result["action"] = _t(db, current_user, "propuesta_ticket", titulo=entities['ticket_title'])
    _proponer(result, {
        "type": "create_ticket",
        "title": entities["ticket_title"],
        "priority": entities.get("priority", "medium"),
    }, current_user)

def _voice_handle_query_hours(db, current_user, result: dict) -> None:
    """Handler para intent ``query_hours`` (sólo lectura, no requiere confirm)."""
    hoy = timeutil.today_for_user(current_user)
    week_start = hoy - timedelta(days=hoy.weekday())
    hours = db.query(func.sum(Imputation.hours)).filter(
        Imputation.user_id == current_user.id,
        Imputation.date >= week_start,
        Imputation.is_active.is_(True),
    ).scalar() or 0
    result["action"] = _t(db, current_user, "horas_semana", horas=round(hours, 1))

def _voice_handle_create_task(db, current_user, entities: dict, project,
                              confirm: bool, result: dict) -> None:
    """Handler para intent ``create_task`` (solo propone)."""
    result["action"] = (
        _t(db, current_user, "propuesta_tarea_en", titulo=entities['task_name'], proyecto=project.name)
        if project else _t(db, current_user, "propuesta_tarea", titulo=entities['task_name'])
    )
    _proponer(result, {
        "type": "create_task",
        "title": entities["task_name"][:255],
        "project_id": project.id if project else None,
        "project_name": project.name if project else None,
        "priority": entities.get("priority", "medium"),
    }, current_user)

def _voice_handle_get_summary(db, current_user, entities: dict, result: dict) -> None:
    """Handler para intent ``get_summary`` (sólo lectura)."""
    project = _voice_find_project_scoped(db, entities['project_name'], current_user)
    if project:
        tasks = db.query(Task).filter(Task.project_id == project.id).all()
        done = sum(1 for t in tasks if t.status == "done")
        open_tasks = sum(1 for t in tasks if t.status != "done")
        result["action"] = _t(db, current_user, "resumen_proyecto", proyecto=project.name,
                              pct=round(done / max(len(tasks), 1) * 100), abiertas=open_tasks, estado=project.status)
    else:
        result["action"] = _t(db, current_user, "proyecto_no_encontrado", nombre=entities['project_name'])

def _voice_handle_other(db, current_user, transcript: str, result: dict) -> None:
    """Handler para intent ``other`` (>20 chars): dispara agente async."""
    exec_record = _ExecRecord(
        user_id=current_user.id,
        instruction=transcript,
        status="queued",
    )
    db.add(exec_record); db.flush()
    enviar_tarea("app.worker.run_agent_task", args=[str(exec_record.id), transcript, str(current_user.id)])
    result["action"] = _t(db, current_user, "enviado_al_agente", id=str(exec_record.id)[:8],
                          producto=NOMBRE_DEL_PRODUCTO)
    result["execution_id"] = str(exec_record.id)

def process_voice_core(transcript: str, db, current_user,
                       *, confirm: bool = False, accion_firmada: str | None = None) -> dict:
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

    if confirm:
        # A6: se ejecuta la propuesta firmada, tal cual, sin volver a llamar al LLM.
        if not accion_firmada:
            from app.core.codigos_de_error import error
            raise error(400, "voz_propuesta_no_valida")
        accion = _verificar_propuesta(accion_firmada, current_user.id)
        intent = accion.get("type") or "unknown"
        entities = {k: v for k, v in accion.items() if not k.startswith("_")}
        action_taken = _ejecutar_propuesta(db, current_user, accion, transcript)
        result: dict = {"intent": intent, "entities": entities, "action": action_taken, "confirmed": True}
    else:
        intent, entities, action_taken = _voice_parse_intent(db, transcript, current_user)
        result = {
            "intent": intent, "entities": entities, "action": action_taken,
            "confirmed": confirm,
        }

    if confirm:
        pass
    elif intent == "log_hours" and entities.get("hours") and entities.get("project_name"):
        project = _voice_find_project_scoped(db, entities['project_name'], current_user)
        _voice_handle_log_hours(db, current_user, transcript, entities, project, confirm, result)
    elif intent == "create_ticket" and entities.get("ticket_title"):
        _voice_handle_create_ticket(db, current_user, entities, confirm, result)
    elif intent == "query_hours":
        _voice_handle_query_hours(db, current_user, result)
    elif intent == "create_task" and entities.get("task_name"):
        project = None
        if entities.get("project_name"):
            project = _voice_find_project_scoped(db, entities['project_name'], current_user)
        _voice_handle_create_task(db, current_user, entities, project, confirm, result)
    elif intent == "get_summary" and entities.get("project_name"):
        _voice_handle_get_summary(db, current_user, entities, result)
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
        # Segunda auditoría 2026-11: el panel de voz pinta la propuesta y su botón
        # «Confirmar» con `pending_action`, que se calculaba y no se devolvía.
        "confirmed": confirm,
        "pending_action": result.get("pending_action"),
        "execution_id": result.get("execution_id"),
    }
