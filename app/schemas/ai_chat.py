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
    message: str
    conversation_id: Optional[str] = None
    context_type: str = "global"
    context_id:   Optional[str] = None


class AgentPayload(BaseModel):
    instruction: str
    auto_approve: bool = False   # if True, skip confirmation for low-risk tools


class PromptTemplatePayload(BaseModel):
    module: str
    name: str
    content: str
    is_active: bool = True


# ── Audit #61: schemas for AIMessage.tool_calls / tool_results ──────────────

class ToolCall(BaseModel):
    """A tool invocation persisted on ``AIMessage.tool_calls`` (JSON-as-Text)."""
    name: str
    arguments: dict = Field(default_factory=dict)


class ToolResult(BaseModel):
    """A tool result persisted on ``AIMessage.tool_results`` (JSON-as-Text)."""
    tool_use_id: str
    content: Any = None
    is_error: bool = False


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


def deserialize_tool_results(raw: Optional[str]) -> List[dict]:
    """Parse ``AIMessage.tool_results`` into validated dicts (BC fallback)."""
    if not raw:
        return []
    try:
        items = json.loads(raw)
    except (TypeError, ValueError):
        _logger.warning("tool_results JSON inválido, devolviendo lista vacía")
        return []
    if not isinstance(items, list):
        _logger.warning("tool_results no es una lista, devolviendo lista vacía")
        return []
    result: List[dict] = []
    for tr in items:
        try:
            result.append(ToolResult(**tr).model_dump())
        except (ValidationError, TypeError):
            _logger.warning("tool_result no validable, fallback al dict crudo")
            result.append(tr if isinstance(tr, dict) else {"raw": tr})
    return result
