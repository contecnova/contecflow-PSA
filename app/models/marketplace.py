"""Gantt baseline and what-if scheduling scenario models.

A baseline is a frozen snapshot of the project schedule at a specific point in
time (e.g. at kick-off, at end of sprint 1). Multiple baselines per project
allow comparing original plan vs re-forecast vs actual.

WhatIfScenario lets PMs simulate the scheduling impact of adding/removing
resources or changing task durations without touching the live plan.
"""
from sqlalchemy import Column, String, Float, DateTime, ForeignKey, Text, Boolean, Integer, Date
from sqlalchemy.sql import func
import uuid

from app.db.base import Base


class GanttBaseline(Base):
    """Frozen schedule snapshot. Each row = one baseline version of a project."""
    __tablename__ = "gantt_baselines"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String(36), ForeignKey("organizations.id"), nullable=True, index=True)  # audit #7
    project_id   = Column(String(36), ForeignKey("projects.id", ondelete="CASCADE"),
                          nullable=False, index=True)
    name         = Column(String(100), nullable=False)           # "Kick-off Baseline", "End Sprint 3"
    description  = Column(Text, nullable=True)
    baseline_date = Column(Date, nullable=False)                 # Date the baseline was frozen

    # Frozen schedule snapshot stored as JSON
    # Schema: {"tasks": [{"task_id":..., "title":..., "start":..., "end":..., "progress":...}], ...}
    schedule_snapshot = Column(Text, nullable=False)             # JSON

    # Summary stats at freeze time
    total_tasks     = Column(Integer, default=0)
    completed_tasks = Column(Integer, default=0)
    total_hours     = Column(Float, default=0)
    budget_at_freeze = Column(Float, nullable=True)

    is_initial  = Column(Boolean, default=False)                 # True = the "contract baseline"
    created_by  = Column(String(36), ForeignKey("users.id"), nullable=True)
    created_at  = Column(DateTime(timezone=True), server_default=func.now())


class WhatIfTask(Base):
    """A simulated task modification inside a what-if scheduling scenario."""
    __tablename__ = "whatif_tasks"

    id          = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String(36), ForeignKey("organizations.id"), nullable=True, index=True)  # audit #7
    scenario_id = Column(String(36), ForeignKey("scenario_models.id", ondelete="CASCADE"),
                         nullable=False, index=True)
    task_id     = Column(String(36), ForeignKey("tasks.id"), nullable=True)   # NULL = new hypothetical task
    title       = Column(String(255), nullable=False)
    start_date  = Column(Date, nullable=True)
    end_date    = Column(Date, nullable=True)
    estimated_hours = Column(Float, nullable=True)
    assigned_user_id = Column(String(36), ForeignKey("users.id"), nullable=True)
    # Overrides: what changes from the real plan
    delta_days  = Column(Integer, nullable=True)   # shift ±n days from original
    delta_hours = Column(Float, nullable=True)     # extra/fewer hours

    created_at  = Column(DateTime(timezone=True), server_default=func.now())


class IntegrationConnector(Base):
    """
    Registry of available third-party integration connectors.
    One row per connector type (Salesforce, HubSpot, SAP, Workday, Bamboo HR, …).
    An organization installs the connector via IntegrationInstance.
    """
    __tablename__ = "integration_connectors"

    # Auditoria 2026-08. Catalogo GLOBAL con personalizacion por organizacion:
    # las filas con `organization_id = NULL` son los valores que trae el
    # producto y se siembran perezosamente desde una peticion; las que llevan
    # organizacion son las que ese cliente ha añadido.
    #
    # Sin esta bandera pasaban dos cosas, las dos comprobadas: el filtro de
    # tenant es `organization_id == org`, asi que una fila global **no la veia
    # nadie** —el catalogo aparecia vacio—; y con el sellado de la organizacion
    # en el `flush`, el sembrado perezoso desde la peticion de un cliente
    # marcaba el catalogo entero como suyo y los demas veian cero.
    #
    # Con ella, el filtro lee `org == X OR org IS NULL` y el sellado la deja en
    # paz. Misma semantica que `AppSetting`.
    _tenant_filter_include_global = True

    id          = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String(36), ForeignKey("organizations.id"), nullable=True, index=True)  # audit #7
    name        = Column(String(100), unique=True, nullable=False)   # "Salesforce CRM"
    slug        = Column(String(50),  unique=True, nullable=False)   # "salesforce"
    category    = Column(String(50),  nullable=False)                # crm|erp|hris|devops|comms
    description = Column(Text, nullable=True)
    logo_url    = Column(String(500), nullable=True)
    docs_url    = Column(String(500), nullable=True)

    # Authentication scheme: oauth2 | api_key | basic | webhook
    auth_scheme = Column(String(20), default="api_key")
    # JSON schema for required config fields
    config_schema = Column(Text, nullable=True)

    is_active   = Column(Boolean, default=True)
    is_certified = Column(Boolean, default=False)   # Official partner certification
    created_at  = Column(DateTime(timezone=True), server_default=func.now())


class IntegrationInstance(Base):
    """
    An organization's configured instance of an integration connector.
    Credentials are stored encrypted; only config metadata shown in API.
    """
    __tablename__ = "integration_instances"

    id             = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String(36), ForeignKey("organizations.id", ondelete="CASCADE"),
                             nullable=False, index=True)
    connector_id   = Column(String(36), ForeignKey("integration_connectors.id"), nullable=False)
    name           = Column(String(100), nullable=False)             # "Production Salesforce"

    # Stored encrypted in prod; NULL in config response
    encrypted_config = Column(Text, nullable=True)

    # Non-sensitive config
    sync_direction = Column(String(20), default="bidirectional")    # inbound|outbound|bidirectional
    sync_frequency = Column(String(20), default="hourly")           # realtime|hourly|daily|manual
    last_sync_at   = Column(DateTime(timezone=True), nullable=True)
    last_sync_status = Column(String(20), nullable=True)             # ok|error|partial
    last_sync_records = Column(Integer, nullable=True)
    last_error      = Column(Text, nullable=True)

    is_enabled      = Column(Boolean, default=True)
    created_by      = Column(String(36), ForeignKey("users.id"), nullable=True)
    created_at      = Column(DateTime(timezone=True), server_default=func.now())
    updated_at      = Column(DateTime(timezone=True), onupdate=func.now())


class TemplateDocument(Base):
    """Document reference / template attachment associated with a ProjectTemplate."""
    __tablename__ = "template_documents"

    id          = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String(36), ForeignKey("organizations.id"), nullable=True, index=True)  # audit #7
    template_id = Column(String(36), ForeignKey("project_templates.id", ondelete="CASCADE"),
                         nullable=False, index=True)
    name        = Column(String(255), nullable=False)
    document_type = Column(String(50), default="spec")              # spec|contract|report|other
    description = Column(Text, nullable=True)
    url         = Column(String(500), nullable=True)                # External link or storage path
    is_required = Column(Boolean, default=False)
    due_week_offset = Column(Integer, nullable=True)                # Due in N weeks from project start
    created_at  = Column(DateTime(timezone=True), server_default=func.now())


class TemplateRole(Base):
    """Required role/skill defined within a ProjectTemplate."""
    __tablename__ = "template_roles"

    id          = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String(36), ForeignKey("organizations.id"), nullable=True, index=True)  # audit #7
    template_id = Column(String(36), ForeignKey("project_templates.id", ondelete="CASCADE"),
                         nullable=False, index=True)
    role_name   = Column(String(100), nullable=False)               # "Senior Developer", "BA"
    skill_required = Column(String(100), nullable=True)
    min_seniority  = Column(String(50), nullable=True)              # junior|mid|senior|lead
    estimated_hours = Column(Float, nullable=True)
    is_mandatory    = Column(Boolean, default=True)
    notes           = Column(Text, nullable=True)
    created_at      = Column(DateTime(timezone=True), server_default=func.now())
