"""Dispatcher central: ``execute_tool`` enruta cada llamada a su handler."""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models.user import User, UserRole
from app.services.ai_chat.tool_execution import (
    crm,
    delivery,
    finance,
    okrs,
    projects,
    resources,
    risks,
    system,
    tasks,
    tickets,
)

_logger = logging.getLogger("v16_core")

# Registro tool_name -> handler(tool_input, db, user, now, is_financial_role).
_HANDLERS: dict = {}
for _mod in (
    projects,
    risks,
    tasks,
    tickets,
    delivery,
    finance,
    okrs,
    resources,
    crm,
    system,
):
    _HANDLERS.update(_mod.HANDLERS)


def execute_tool(tool_name: str, tool_input: dict, db: Session, user: User) -> dict:
    """Execute a tool call from the agent."""
    # Control de acceso para herramientas financieras
    is_financial_role = (
        getattr(user, "is_superadmin", False)
        or getattr(user, "role", None) in (UserRole.admin, UserRole.hr)
    )
    now = datetime.now(timezone.utc)
    try:
        handler = _HANDLERS.get(tool_name)
        if handler is None:
            return {"error": f"Herramienta desconocida: {tool_name}"}
        return handler(tool_input, db, user, now, is_financial_role)
    except Exception as e:
        return {"error": str(e)[:300]}
