"""
ai_core_service — Core AI chat functions: action logging, demo responses, chat persistence.
"""
import json
import logging
from typing import Optional
from sqlalchemy.orm import Session

from app.models.ai_chat import AIActionLog, AIMessage
from app.schemas.ai_chat import (
    serialize_tool_calls,
    serialize_tool_results,
    deserialize_tool_calls,
    deserialize_tool_results,
)
from app.services.ai_chat.prompt_service import get_prompt
from app.services.ai_chat.context_service import build_tenant_context

_logger = logging.getLogger("v16_core")


def log_action(
    db: Session,
    user_id: str,
    module: str,
    action_type: str,
    input_s: str = None,
    output_s: str = None,
    entities: list = None,
    tokens: int = 0,
    latency: int = 0,
    status: str = "success",
) -> None:
    """Log an AI action to the audit log."""
    db.add(AIActionLog(
        user_id=user_id, module=module, action_type=action_type,
        input_summary=(input_s or "")[:300],
        output_summary=(output_s or "")[:300],
        entities_affected=json.dumps(entities or []),
        tokens_used=tokens, latency_ms=latency, status=status,
    ))


def demo_response(message: str, ctx: dict) -> str:
    """Fallback responses when no AI provider is configured."""
    msg = message.lower()
    losses = ctx.get("projects_at_loss", [])
    if any(w in msg for w in ["pérdida", "perdidas", "margen", "rentab", "beneficio", "profit"]):
        if losses:
            names = ", ".join(f"**{x['project']}** ({x['margin']:+.0f}€)" for x in losses[:5])
            return (f"Proyectos actualmente **en pérdidas**: {names}.\n\n"
                    f"El contexto incluye datos de coste (horas × tarifa + gastos) vs facturado. "
                    f"Configura un proveedor IA para análisis detallado.")
        return ("No se detectan proyectos en pérdidas con los datos disponibles. "
                "Configura un proveedor IA en IA & Conectores para análisis completo.")
    if any(w in msg for w in ["proyecto", "project", "riesgo", "risk"]):
        return (f"Según los datos del sistema, tienes **{ctx['active_projects']} proyectos activos**, "
                f"**{ctx['overdue_tasks']} tareas con retraso** y **{ctx['open_tickets']} tickets abiertos**. "
                f"Para análisis detallado de riesgos, visita la sección Predicciones de ContecflowOracle.")
    if any(w in msg for w in ["hora", "imput", "timesheet"]):
        return (f"Esta semana se han registrado **{ctx['hours_this_week']} horas** en total. "
                f"Accede a Timesheets para el detalle por proyecto y persona.")
    if any(w in msg for w in ["ticket", "soport", "incidencia"]):
        return (f"Hay **{ctx['open_tickets']} tickets abiertos** en el Service Desk.")
    return (f"Hola, soy ContecflowAssist 👋 Tengo acceso a los datos de tu empresa: "
            f"**{ctx['active_projects']} proyectos activos**, "
            f"**{ctx['open_tickets']} tickets** abiertos, "
            f"**{ctx['hours_this_week']}h** imputadas esta semana.\n\n"
            f"Configura un proveedor IA en **IA & Conectores** (Google Gemini, OpenAI, Anthropic…) para respuestas completas.\n\n"
            f"Prueba: *¿Cuáles son los proyectos en pérdidas?* o *¿Qué tickets llevan más de 48h sin respuesta?*")


def _pagina_del_usuario(db: Session, context_type, context_id) -> str:
    """Lo que el usuario tiene abierto (proyecto, ticket, sprint) para el prompt.

    El panel lo enviaba y se guardaba en la conversacion, pero nunca llegaba al
    modelo: «¿como va este proyecto?» no sabia de que proyecto hablaba.
    """
    if not context_type or not context_id:
        return ""
    from app.models.project import Project
    from app.models.service_desk import Ticket
    from app.models.sprints import Sprint
    modelos = {"project": Project, "ticket": Ticket, "sprint": Sprint}
    modelo = modelos.get(context_type)
    fila = db.query(modelo).filter(modelo.id == context_id).first() if modelo else None
    if fila is None:
        return ""
    datos = {k: str(getattr(fila, k)) for k in ("code", "number", "name", "title", "status", "priority",
                                                  "start_date", "end_date", "end_date_planned", "goal")
             if getattr(fila, k, None) not in (None, "")}
    return (f"\n\nEl usuario esta viendo este {context_type} (id {context_id}); "
            f"si pregunta por «este», se refiere a el: {json.dumps(datos, ensure_ascii=False)}")


def prepare_chat(db: Session, conversation_id, user_id: str, context_type=None, context_id=None,
                  effective_message: str = "", system_template: str = "", commit: bool = False):
    """Create/get conversation, persist user message, build history + system prompt.
    Returns (conv, messages, system)."""
    from app.services.ai_chat.conversation_service import get_or_create_conversation
    from app.models.user import User

    conv = get_or_create_conversation(db, conversation_id, user_id, context_type, context_id)

    user_msg = AIMessage(conversation_id=conv.id, role="user", content=effective_message)
    db.add(user_msg); db.flush()

    # Obtener el objeto User para pasar a build_tenant_context
    user = db.query(User).filter(User.id == user_id).first()
    ctx = build_tenant_context(db, user)
    # Revisión 2026-11: la base del Service Desk (antes `ai_kb_articles`, vacía),
    # con la corrección del experto delante y los artículos para citar.
    from app.services.service_desk.kb_calidad import contexto as contexto_kb
    kb = contexto_kb(db, effective_message, solo_publico=False)
    conv.fuentes_kb = {"sources": kb["sources"], "correction": kb["correction"]}
    system = get_prompt(db, "contecflowassist", system_template).format(
        context=json.dumps(ctx, ensure_ascii=False)
    ) + kb["prompt"] + _pagina_del_usuario(  # la pagina de ahora; si no llega, la de la conversacion
        db, context_type or conv.context_type, context_id if context_type else conv.context_id)

    if conv.context_type == "inline_editor":
        history = []  # cada reescritura es independiente de las anteriores
    else:
        history = db.query(AIMessage).filter(
            AIMessage.conversation_id == conv.id,
            AIMessage.id != user_msg.id,
        ).order_by(AIMessage.created_at.desc()).limit(10).all()
        history.reverse()

    messages = [{"role": m.role, "content": m.content} for m in history]
    messages.append({"role": "user", "content": effective_message})

    if not conv.title:
        conv.title = effective_message[:60] + ("..." if len(effective_message) > 60 else "")

    if commit:
        db.commit()

    return conv, messages, system


def persist_chat_response(
    db: Session,
    conv_id: str,
    user_id: str,
    original_message: str,
    assistant_text: str,
    latency: int,
    tool_calls: Optional[list] = None,
    tool_results: Optional[list] = None,
):
    """Persist assistant message and action log after chat call.

    ``tool_calls`` and ``tool_results`` are validated via Pydantic schemas
    (audit #61) before being serialized to the JSON-as-Text columns. Pass raw
    dicts shaped as ``{"name": ..., "arguments": {...}}`` /
    ``{"tool_use_id": ..., "content": ..., "is_error": False}``.
    """
    ai_msg = AIMessage(
        conversation_id=conv_id, role="assistant",
        content=assistant_text, tokens_used=0, latency_ms=latency,
        tool_calls=serialize_tool_calls(tool_calls),
        tool_results=serialize_tool_results(tool_results),
    )
    db.add(ai_msg)
    log_action(db, user_id, "contecflowassist", "chat",
               original_message[:200], assistant_text[:200], latency=latency)
    db.commit()
    return ai_msg.id   # revisión 2026-11: el panel lo usa para valorar la respuesta


def load_message_tool_calls(msg: AIMessage) -> list:
    """Read ``AIMessage.tool_calls`` as validated dicts (audit #61)."""
    return deserialize_tool_calls(msg.tool_calls)


def load_message_tool_results(msg: AIMessage) -> list:
    """Read ``AIMessage.tool_results`` as validated dicts (audit #61)."""
    return deserialize_tool_results(msg.tool_results)
