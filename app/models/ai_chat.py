"""
v16 models — Contecflow AI layer (all 12 modules)

NexusAssist  : AIConversation, AIMessage
NexusAgent   : AIAgentExecution, AIAgentStep, AIAgentTool
NexusOracle  : AIPrediction, AIAnomaly
AI Governance: AIGovernanceConfig, AIActionLog
Meeting Asst : AIMeeting, AIMeetingAction
Contract IA  : AIContract, AIContractClause
Knowledge IA : AIKBArticleGenerated
Voice        : AIVoiceCommand
Resource AI  : AIResourceInsight
Financial AI : AIFinancialInsight
Client Portal: AIClientSession, AIClientMessage
"""
from sqlalchemy import Index
from sqlalchemy import (
    Column, String, Float, DateTime, ForeignKey, Text,
    Boolean, Integer
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import uuid
from app.db.base import Base
from app.core.config import settings


# ── NexusAssist ───────────────────────────────────────────────────────────────

class AIConversation(Base):
    """A chat session between a user and NexusAssist."""
    __tablename__ = "ai_conversations"

    id           = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String(36), ForeignKey("organizations.id"), nullable=True, index=True)  # audit #7
    user_id      = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    title        = Column(String(255), nullable=True)          # auto-generated from first message
    context_type = Column(String(50), default="global")        # global | project | ticket | sprint | invoice
    context_id   = Column(String(36), nullable=True)           # id of the context entity
    model_used   = Column(String(80), default=lambda: settings.CONTECFLOW_AI_MODEL)
    total_tokens = Column(Integer, default=0)
    is_archived  = Column(Boolean, default=False)
    created_at   = Column(DateTime(timezone=True), server_default=func.now())
    updated_at   = Column(DateTime(timezone=True), onupdate=func.now())

    messages = relationship("AIMessage", back_populates="conversation",
                            cascade="all, delete-orphan", order_by="AIMessage.created_at")
    user     = relationship("User", foreign_keys=[user_id])


class AIMessage(Base):
    """A single message within an AIConversation."""
    __tablename__ = "ai_messages"

    id              = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String(36), ForeignKey("organizations.id"), nullable=True, index=True)  # audit #7
    conversation_id = Column(String(36), ForeignKey("ai_conversations.id", ondelete="CASCADE"),
                             nullable=False, index=True)
    role            = Column(String(20), nullable=False)       # user | assistant | tool
    content         = Column(Text, nullable=False)
    tool_calls      = Column(Text, nullable=True)              # JSON: list of tool calls made
    tool_results    = Column(Text, nullable=True)              # JSON: results from tools
    tokens_used     = Column(Integer, default=0)
    latency_ms      = Column(Integer, default=0)
    created_at      = Column(DateTime(timezone=True), server_default=func.now())

    conversation = relationship("AIConversation", back_populates="messages")


# ── NexusAgent ────────────────────────────────────────────────────────────────

class AIAgentExecution(Base):
    """A full agentic task execution — one user instruction → N steps."""
    __tablename__ = "ai_agent_executions"

    id           = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String(36), ForeignKey("organizations.id"), nullable=True, index=True)  # audit #7
    user_id      = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    instruction  = Column(Text, nullable=False)                # original user instruction
    status       = Column(String(20), default="pending")       # pending|running|awaiting_approval|done|failed
    result       = Column(Text, nullable=True)                 # final summary
    steps_count  = Column(Integer, default=0)
    approved_by  = Column(String(36), ForeignKey("users.id"), nullable=True)
    approved_at  = Column(DateTime(timezone=True), nullable=True)
    error        = Column(String(500), nullable=True)
    total_tokens = Column(Integer, default=0)
    created_at   = Column(DateTime(timezone=True), server_default=func.now())
    completed_at = Column(DateTime(timezone=True), nullable=True)

    steps    = relationship("AIAgentStep", back_populates="execution",
                            cascade="all, delete-orphan", order_by="AIAgentStep.step_number")
    user     = relationship("User", foreign_keys=[user_id])
    approver = relationship("User", foreign_keys=[approved_by])


class AIAgentStep(Base):
    """One step within an agent execution (one tool call + result)."""
    __tablename__ = "ai_agent_steps"

    id           = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String(36), ForeignKey("organizations.id"), nullable=True, index=True)  # audit #7
    execution_id = Column(String(36), ForeignKey("ai_agent_executions.id", ondelete="CASCADE"),
                          nullable=False, index=True)
    step_number  = Column(Integer, nullable=False)
    tool_name    = Column(String(100), nullable=False)         # e.g. create_task, assign_resource
    tool_input   = Column(Text, nullable=True)                 # JSON
    tool_output  = Column(Text, nullable=True)                 # JSON
    status       = Column(String(20), default="done")          # done|failed|skipped
    requires_approval = Column(Boolean, default=False)
    is_approved  = Column(Boolean, nullable=True)
    error        = Column(String(500), nullable=True)
    executed_at  = Column(DateTime(timezone=True), server_default=func.now())

    execution = relationship("AIAgentExecution", back_populates="steps")


# ── NexusOracle ───────────────────────────────────────────────────────────────

class AIPrediction(Base):
    """A predictive insight generated by NexusOracle."""
    __tablename__ = "ai_predictions"

    id              = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String(36), ForeignKey("organizations.id"), nullable=True, index=True)  # audit #7
    prediction_type = Column(String(50), nullable=False, index=True)
    # project_delay | sla_breach | budget_overrun | burnout | anomaly | revenue_forecast
    entity_type     = Column(String(30), nullable=True)        # project | user | ticket | invoice
    entity_id       = Column(String(36), nullable=True, index=True)
    probability     = Column(Float, nullable=True)             # 0-1
    severity        = Column(String(20), default="medium")     # low | medium | high | critical
    title           = Column(String(255), nullable=False)
    explanation     = Column(Text, nullable=True)              # why the model predicts this
    recommended_action = Column(Text, nullable=True)
    features_used   = Column(Text, nullable=True)              # JSON: {feature: weight}
    is_acknowledged = Column(Boolean, default=False)
    acknowledged_by = Column(String(36), ForeignKey("users.id"), nullable=True)
    acknowledged_at = Column(DateTime(timezone=True), nullable=True)
    expires_at      = Column(DateTime(timezone=True), nullable=True)
    created_at      = Column(DateTime(timezone=True), server_default=func.now())

    acknowledger = relationship("User", foreign_keys=[acknowledged_by])


class AIAnomaly(Base):
    """A detected anomaly in operational data."""
    __tablename__ = "ai_anomalies"

    id           = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String(36), ForeignKey("organizations.id"), nullable=True, index=True)  # audit #7
    anomaly_type = Column(String(50), nullable=False)
    # billing_fraud | duplicate_hours | orphan_task | sla_pattern | resource_overload
    entity_type  = Column(String(30), nullable=True)
    entity_id    = Column(String(36), nullable=True)
    description  = Column(Text, nullable=False)
    severity     = Column(String(20), default="medium")
    data_snapshot = Column(Text, nullable=True)                # JSON: relevant data at detection time
    is_resolved  = Column(Boolean, default=False)
    resolved_by  = Column(String(36), ForeignKey("users.id"), nullable=True)
    resolved_at  = Column(DateTime(timezone=True), nullable=True)
    created_at   = Column(DateTime(timezone=True), server_default=func.now())

    resolver = relationship("User", foreign_keys=[resolved_by])


# ── AI Governance ─────────────────────────────────────────────────────────────

class AIGovernanceConfig(Base):
    """Per-module AI governance settings (trust levels, approval requirements)."""
    __tablename__ = "ai_governance_configs"
    # Unico por organizacion (revision multitenant 2026-11): antes era global y
    # una segunda empresa no podia repetir el codigo/nombre de otra.
    __table_args__ = (Index("uq_ai_governance_configs_org_module", "organization_id", "module", unique=True),)

    id              = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String(36), ForeignKey("organizations.id"), nullable=True, index=True)  # audit #7
    module          = Column(String(50), nullable=False)
    # nexusassist | nexusagent | nexusoracle | meeting_assistant | contract_intelligence | ...
    is_enabled      = Column(Boolean, default=True)
    requires_approval_for = Column(Text, default='[]')         # JSON: list of tool names requiring approval
    max_actions_per_day   = Column(Integer, nullable=True)     # rate limit per user
    allowed_roles   = Column(Text, default='["admin","pm"]')   # JSON: list of roles that can use this module
    model_override  = Column(String(80), nullable=True)        # override default model for this module
    updated_by      = Column(String(36), ForeignKey("users.id"), nullable=True)
    updated_at      = Column(DateTime(timezone=True), onupdate=func.now())

    updater = relationship("User", foreign_keys=[updated_by])


class AIActionLog(Base):
    """Immutable audit log of every AI action (Governance dashboard source)."""
    __tablename__ = "ai_action_logs"

    id           = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String(36), ForeignKey("organizations.id"), nullable=True, index=True)  # audit #7
    user_id      = Column(String(36), ForeignKey("users.id"), nullable=True, index=True)
    module       = Column(String(50), nullable=False, index=True)
    action_type  = Column(String(100), nullable=False)         # tool name or event type
    input_summary = Column(Text, nullable=True)                # truncated user instruction
    output_summary = Column(Text, nullable=True)               # truncated AI response/action
    entities_affected = Column(Text, nullable=True)            # JSON: [{type, id, name}]
    tokens_used  = Column(Integer, default=0)
    latency_ms   = Column(Integer, default=0)
    status       = Column(String(20), default="success")       # success | failed | rejected
    ip_address   = Column(String(45), nullable=True)
    created_at   = Column(DateTime(timezone=True), server_default=func.now(), index=True)

    user = relationship("User", foreign_keys=[user_id])


# ── Smart Meeting Assistant ───────────────────────────────────────────────────

class AIMeeting(Base):
    """A processed meeting with transcript, summary and extracted actions."""
    __tablename__ = "ai_meetings"

    id           = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String(36), ForeignKey("organizations.id"), nullable=True, index=True)  # audit #7
    project_id   = Column(String(36), ForeignKey("projects.id"), nullable=True, index=True)
    title        = Column(String(255), nullable=True)
    meeting_date = Column(DateTime(timezone=True), nullable=True)
    platform     = Column(String(30), nullable=True)           # teams | zoom | meet | upload
    duration_min = Column(Integer, nullable=True)
    participants = Column(Text, nullable=True)                 # JSON: list of names/emails
    transcript   = Column(Text, nullable=True)                 # full transcript
    summary      = Column(Text, nullable=True)                 # AI-generated executive summary
    decisions    = Column(Text, nullable=True)                 # JSON: list of decisions made
    risks_mentioned = Column(Text, nullable=True)              # JSON: risks mentioned
    status       = Column(String(20), default="processing")    # processing | done | failed
    pdf_path     = Column(String(500), nullable=True)          # generated PDF minutes
    created_by   = Column(String(36), ForeignKey("users.id"), nullable=True)
    created_at   = Column(DateTime(timezone=True), server_default=func.now())

    actions  = relationship("AIMeetingAction", back_populates="meeting",
                            cascade="all, delete-orphan")
    project  = relationship("Project")
    creator  = relationship("User", foreign_keys=[created_by])


class AIMeetingAction(Base):
    """An action item extracted from a meeting transcript."""
    __tablename__ = "ai_meeting_actions"

    id           = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String(36), ForeignKey("organizations.id"), nullable=True, index=True)  # audit #7
    meeting_id   = Column(String(36), ForeignKey("ai_meetings.id", ondelete="CASCADE"),
                          nullable=False, index=True)
    description  = Column(Text, nullable=False)
    assignee_name = Column(String(255), nullable=True)         # name as mentioned in transcript
    assignee_id  = Column(String(36), ForeignKey("users.id"), nullable=True)
    due_date_text = Column(String(100), nullable=True)         # "next Friday", "end of month"
    due_date     = Column(DateTime(timezone=True), nullable=True)
    task_id      = Column(String(36), ForeignKey("tasks.id"), nullable=True)  # if created in Contecflow
    is_created   = Column(Boolean, default=False)              # True if task created in Contecflow
    created_at   = Column(DateTime(timezone=True), server_default=func.now())

    meeting  = relationship("AIMeeting", back_populates="actions")
    assignee = relationship("User", foreign_keys=[assignee_id])


# ── AI Contract Intelligence ──────────────────────────────────────────────────

class AIContract(Base):
    """A contract document analyzed by AI."""
    __tablename__ = "ai_contracts"

    id           = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String(36), ForeignKey("organizations.id"), nullable=True, index=True)  # audit #7
    project_id   = Column(String(36), ForeignKey("projects.id"), nullable=True, index=True)
    client_name  = Column(String(255), nullable=True)
    filename     = Column(String(500), nullable=True)
    file_content = Column(Text, nullable=True)                 # base64 or extracted text
    status       = Column(String(20), default="analyzing")    # analyzing | done | failed
    total_value  = Column(Float, nullable=True)
    start_date   = Column(DateTime(timezone=True), nullable=True)
    end_date     = Column(DateTime(timezone=True), nullable=True)
    scope_summary = Column(Text, nullable=True)
    risk_level   = Column(String(20), nullable=True)           # low | medium | high
    scope_creep_alerts = Column(Integer, default=0)
    created_by   = Column(String(36), ForeignKey("users.id"), nullable=True)
    created_at   = Column(DateTime(timezone=True), server_default=func.now())

    clauses  = relationship("AIContractClause", back_populates="contract",
                            cascade="all, delete-orphan")
    project  = relationship("Project")
    creator  = relationship("User", foreign_keys=[created_by])


class AIContractClause(Base):
    """A significant clause extracted from a contract."""
    __tablename__ = "ai_contract_clauses"

    id           = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String(36), ForeignKey("organizations.id"), nullable=True, index=True)  # audit #7
    contract_id  = Column(String(36), ForeignKey("ai_contracts.id", ondelete="CASCADE"),
                          nullable=False, index=True)
    clause_type  = Column(String(50), nullable=False)
    # penalty | deliverable | milestone | sla | termination | payment | scope | confidentiality
    title        = Column(String(255), nullable=False)
    description  = Column(Text, nullable=True)
    original_text = Column(Text, nullable=True)               # verbatim from contract
    impact_amount = Column(Float, nullable=True)              # financial impact if applicable
    due_date     = Column(DateTime(timezone=True), nullable=True)
    is_at_risk   = Column(Boolean, default=False)
    risk_reason  = Column(String(500), nullable=True)
    created_at   = Column(DateTime(timezone=True), server_default=func.now())

    contract = relationship("AIContract", back_populates="clauses")


# ── AI Knowledge Base ─────────────────────────────────────────────────────────

class AIKBArticle(Base):
    """An AI-generated or AI-enriched knowledge base article.

    **Item #62 — Duplicidad con ``KBArticle`` (service_desk):**
    Existen DOS sistemas KB en paralelo:
    - ``KBArticle`` (service_desk) — KB humano del módulo SD, sin embedding precalculado.
    - ``AIKBArticle`` (este) — KB generado/curado por IA, con ``embedding`` JSON.

    Razón histórica: cada flow (humano vs. AI auto-gen) creció separado. La
    consecuencia es que la UI de KB del Service Desk solo edita ``KBArticle``
    mientras que ``ai_auto_resolution_service._search_kb`` consulta ambos.

    Migración futura: unificar en ``KBArticle`` añadiendo ``is_ai_generated``,
    ``embedding`` y mover la lógica de embedding background a un job común.
    No urgente; tracked como deuda P2.
    """
    __tablename__ = "ai_kb_articles"

    id             = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String(36), ForeignKey("organizations.id"), nullable=True, index=True)  # audit #7
    source_ticket_id = Column(String(36), ForeignKey("sd_tickets.id"), nullable=True)
    title          = Column(String(255), nullable=False)
    content        = Column(Text, nullable=False)
    tags           = Column(Text, nullable=True)               # JSON: list of tags
    category       = Column(String(100), nullable=True)
    embedding_text = Column(Text, nullable=True)               # text used for semantic search
    embedding      = Column(Text, nullable=True)               # JSON float[] — pre-computed vector
    view_count     = Column(Integer, default=0)
    helpful_votes  = Column(Integer, default=0)
    is_published   = Column(Boolean, default=False)
    is_ai_generated = Column(Boolean, default=True)
    reviewed_by    = Column(String(36), ForeignKey("users.id"), nullable=True)
    created_at     = Column(DateTime(timezone=True), server_default=func.now())
    updated_at     = Column(DateTime(timezone=True), onupdate=func.now())

    reviewer = relationship("User", foreign_keys=[reviewed_by])


# ── AI Voice Commands ─────────────────────────────────────────────────────────

class AIVoiceCommand(Base):
    """A voice command processed by the voice interface."""
    __tablename__ = "ai_voice_commands"

    id           = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String(36), ForeignKey("organizations.id"), nullable=True, index=True)  # audit #7
    user_id      = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    transcript   = Column(Text, nullable=False)                # what was said
    intent       = Column(String(100), nullable=True)          # log_hours | create_ticket | query | ...
    entities     = Column(Text, nullable=True)                 # JSON: extracted entities
    action_taken = Column(Text, nullable=True)                 # description of what was done
    status       = Column(String(20), default="done")          # done | failed | clarification_needed
    created_at   = Column(DateTime(timezone=True), server_default=func.now())

    user = relationship("User", foreign_keys=[user_id])


# ── AI Client Portal ──────────────────────────────────────────────────────────

class AIClientChatSession(Base):
    """A chat session in the AI-powered client portal."""
    __tablename__ = "ai_client_chat_sessions"

    id             = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String(36), ForeignKey("organizations.id"), nullable=True, index=True)  # audit #7
    client_user_id = Column(String(36), ForeignKey("client_users.id", ondelete="CASCADE"),
                            nullable=False, index=True)
    project_id     = Column(String(36), ForeignKey("projects.id"), nullable=True)
    created_at     = Column(DateTime(timezone=True), server_default=func.now())

    messages = relationship("AIClientChatMessage", back_populates="session",
                            cascade="all, delete-orphan", order_by="AIClientChatMessage.created_at")


class AIClientChatMessage(Base):
    """A message in the AI client portal chat."""
    __tablename__ = "ai_client_chat_messages"

    id         = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String(36), ForeignKey("organizations.id"), nullable=True, index=True)  # audit #7
    session_id = Column(String(36), ForeignKey("ai_client_chat_sessions.id", ondelete="CASCADE"),
                        nullable=False, index=True)
    role       = Column(String(20), nullable=False)            # user | assistant
    content    = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    session = relationship("AIClientChatSession", back_populates="messages")


# ── AI Prompt Templates (versioning) ─────────────────────────────────────────

class AIPromptTemplate(Base):
    """Versioned system prompt templates for AI modules.

    Allows admins to customise and iterate on prompts without code deploys.
    The active template (is_active=True, highest version) is loaded at runtime;
    all other code falls back to the hardcoded default if no template exists.
    """
    __tablename__ = "ai_prompt_templates"

    id         = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String(36), ForeignKey("organizations.id"), nullable=True, index=True)  # audit #7
    module     = Column(String(100), nullable=False, index=True)
    # nexusassist | nexusagent | voice | oracle | meeting | contract | portal | ...
    name       = Column(String(255), nullable=False)
    content    = Column(Text, nullable=False)
    version    = Column(Integer, default=1, nullable=False)
    is_active  = Column(Boolean, default=True)
    created_by = Column(String(36), ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    creator = relationship("User", foreign_keys=[created_by])


class MCPPendingAction(Base):
    """Escritura pedida por un agente externo (MCP) que espera aprobación humana.

    Revisión 2026-11: con `MCP_WRITE_MODE=approval` la herramienta que escribe no
    se ejecuta al llamarla; se abre una aprobación (`entity_type="mcp_action"`)
    y, si se aprueba, se ejecuta entonces como el dueño de la credencial.
    """
    __tablename__ = "mcp_pending_actions"

    id              = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String(36), ForeignKey("organizations.id"), nullable=True, index=True)
    user_id         = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    tool            = Column(String(80), nullable=False)
    arguments       = Column(Text, nullable=False, default="{}")       # JSON
    status          = Column(String(20), nullable=False, default="pending", index=True)  # pending | executed | failed | rejected
    result          = Column(Text, nullable=True)                      # JSON de la herramienta al ejecutarse
    approval_request_id = Column(String(36), nullable=True, index=True)
    created_at      = Column(DateTime(timezone=True), server_default=func.now())
    decided_at      = Column(DateTime(timezone=True), nullable=True)


class AIAnswerFeedback(Base):
    """👍 / 👎 de una respuesta de IA (asistente interno o chat del portal).

    Revisión 2026-11 (lo que contecmind tenía): un 👎 lleva la pregunta a la
    lista de «preguntas sin respuesta» de la base de conocimiento.
    """
    __tablename__ = "ai_answer_feedback"
    __table_args__ = (Index("uq_ai_answer_feedback_org_msg", "organization_id", "channel", "message_id", unique=True),)

    id              = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String(36), ForeignKey("organizations.id"), nullable=True, index=True)
    channel         = Column(String(20), nullable=False)        # assistant | portal
    message_id      = Column(String(36), nullable=False)
    question        = Column(Text, nullable=True)
    helpful         = Column(Boolean, nullable=False)
    comment         = Column(Text, nullable=True)
    user_id         = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    client_user_id  = Column(String(36), nullable=True)
    created_at      = Column(DateTime(timezone=True), server_default=func.now())


class AskDataExample(Base):
    """Pregunta → consulta validada de Ask-the-Data, de una empresa.

    Revisión 2026-11 (lo que contecintelligence tenía): una respuesta que alguien
    marca como correcta se guarda; la misma pregunta la reutiliza sin llamar al
    modelo, y las parecidas se le dan al modelo como ejemplos. La consulta se
    guarda como la escribió el modelo (sin el filtro de empresa ni el LIMIT, que
    se añaden siempre al ejecutar).
    """
    __tablename__ = "ask_data_examples"
    __table_args__ = (Index("uq_ask_data_examples_org_q", "organization_id", "question_norm", unique=True),)

    id              = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String(36), ForeignKey("organizations.id"), nullable=True, index=True)
    question        = Column(Text, nullable=False)
    question_norm   = Column(String(500), nullable=False)
    sql             = Column(Text, nullable=False)
    created_by      = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at      = Column(DateTime(timezone=True), server_default=func.now())
    times_used      = Column(Integer, nullable=False, default=0, server_default="0")
    last_used_at    = Column(DateTime(timezone=True), nullable=True)
