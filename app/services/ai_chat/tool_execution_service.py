# ruff: noqa: F401
"""
ai_tool_execution_service — Agent tool definitions and execution.

Barrel de compatibilidad. La implementación se ha trasladado al subpaquete
``app.services.ai_chat.tool_execution`` (troceado por familias de herramientas).
Este módulo re-exporta la API pública histórica —y el namespace importable
completo— para no romper imports existentes.
"""
from __future__ import annotations

import json
import logging
import uuid as _uuid
from datetime import datetime, timezone, timedelta

from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.alert import Alert
from app.models.billing_reports import Invoice, ApprovalRequest
from app.models.clients import Client
from app.models.expenses import Expense
from app.models.financial import ProjectMilestone, Timesheet
from app.models.git_integration import GitPullRequest
from app.models.imputation import Imputation
from app.models.okrs import Objective, KeyResult
from app.models.pipeline import Risk, Contract, Opportunity
from app.models.project import Project
from app.models.resources import ChangeRequest, Deliverable, Skill, UserSkill, Absence
from app.models.service_desk import Ticket
from app.models.sprints import Sprint
from app.models.task import Task
from app.models.user import User, UserRole
from app.services.ai_chat.context_service import build_tenant_context

from app.services.ai_chat.tool_execution import (
    AGENT_TOOLS,
    WRITE_ACTION_TOOLS,
    build_agent_system_prompt,
    execute_tool,
    _logger,
)
