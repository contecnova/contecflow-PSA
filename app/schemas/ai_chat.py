"""
AI Chat – Pydantic input schemas.

Extracted from ai_chat.py so they can be tested and imported independently.

Audit #61: Pydantic validators for JSON columns declared as Text on
``app.models.ai_chat.AIMessage`` (``tool_calls`` and ``tool_results``). The
helpers ``serialize_tool_calls`` / ``deserialize_tool_calls`` (and their
``tool_results`` siblings) MUST be used by every service that writes or reads
these fields so we don't ship raw / malformed JSON to the DB.
"""
import json
import logging
from typing import Any, List, Optional

from pydantic import BaseModel, Field, ValidationError


_logger = logging.getLogger(__name__)


class ChatPayload(BaseModel):
    message: str = Field(..., description="Mensaje enviado por el usuario al asistente")
    conversation_id: Optional[str] = Field(None, description="ID de la conversación existente o None para iniciar una nueva")
    context_type: str = Field("global", description="Tipo de contexto del chat (global, project, task, etc.)")
    context_id: Optional[str] = Field(None, description="ID del recurso al que se asocia el contexto")


class AgentPayload(BaseModel):
    instruction: str = Field(..., description="Instrucción en lenguaje natural para el agente")
    auto_approve: bool = Field(False, description="Si es True, omite confirmación para herramientas de bajo riesgo")


class PromptTemplatePayload(BaseModel):
    module: str = Field(..., description="Módulo al que pertenece la plantilla de prompt")
    name: str = Field(..., description="Nombre identificativo de la plantilla")
    content: str = Field(..., description="Contenido del prompt con placeholders")
    is_active: bool = Field(True, description="Indica si la plantilla está activa")


# ── Audit #61: schemas for AIMessage.tool_calls / tool_results ──────────────

class ToolCall(BaseModel):
    """A tool invocation persisted on ``AIMessage.tool_calls`` (JSON-as-Text)."""
    name: str = Field(..., description="Nombre de la herramienta invocada")
    arguments: dict = Field(default_factory=dict, description="Argumentos pasados a la herramienta")


class ToolResult(BaseModel):
    """A tool result persisted on ``AIMessage.tool_results`` (JSON-as-Text)."""
    tool_use_id: str = Field(..., description="ID de la invocación de herramienta asociada")
    content: Any = Field(None, description="Contenido devuelto por la herramienta")
    is_error: bool = Field(False, description="Indica si la ejecución devolvió un error")


def serialize_tool_calls(tool_calls: Optional[List[dict]]) -> Optional[str]:
    """Validate ``tool_calls`` via Pydantic and return its JSON string form.

    Returns ``None`` when the input is falsy so we don't store empty strings.
    Raises ``pydantic.ValidationError`` if any entry doesn't match ``ToolCall``.
    """
    if not tool_calls:
        return None
    validated = [ToolCall(**tc).model_dump() for tc in tool_calls]
    return json.dumps(validated)


def serialize_tool_results(tool_results: Optional[List[dict]]) -> Optional[str]:
    """Validate ``tool_results`` via Pydantic and return its JSON string form."""
    if not tool_results:
        return None
    validated = [ToolResult(**tr).model_dump() for tr in tool_results]
    return json.dumps(validated)


def deserialize_tool_calls(raw: Optional[str]) -> List[dict]:
    """Parse ``AIMessage.tool_calls`` into validated dicts.

    Backwards-compatible: rows persisted before this validation existed may not
    match the schema. In that case we log a warning and fall back to the raw
    dicts so the chat history can still be rendered.
    """
    if not raw:
        return []
    try:
        items = json.loads(raw)
    except (TypeError, ValueError):
        _logger.warning("tool_calls JSON inválido, devolviendo lista vacía")
        return []
    if not isinstance(items, list):
        _logger.warning("tool_calls no es una lista, devolviendo lista vacía")
        return []
    result: List[dict] = []
    for tc in items:
        try:
            result.append(ToolCall(**tc).model_dump())
        except (ValidationError, TypeError):
            _logger.warning("tool_call no validable, fallback al dict crudo")
            result.append(tc if isinstance(tc, dict) else {"raw": tc})
    return result

