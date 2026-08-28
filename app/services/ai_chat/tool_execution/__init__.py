"""Subpaquete ``tool_execution``: definiciones y ejecución de herramientas
del ContecflowAgent.

La implementación está troceada por familias de herramientas (projects, risks,
tasks, tickets, delivery, finance, okrs, resources, crm, system). Este paquete
re-exporta la API pública histórica del antiguo módulo
``tool_execution_service``.
"""
from app.services.ai_chat.tool_execution.schema import (
    AGENT_TOOLS,
    WRITE_ACTION_TOOLS,
)
from app.services.ai_chat.tool_execution.executor import (
    _logger,
    execute_tool,
)
from app.services.ai_chat.tool_execution.prompt import (
    build_agent_system_prompt,
)

__all__ = [
    "AGENT_TOOLS",
    "WRITE_ACTION_TOOLS",
    "execute_tool",
    "build_agent_system_prompt",
    "_logger",
]
