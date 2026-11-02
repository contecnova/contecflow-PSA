"""
Contecflow v21 — Modelos:
  1. Etiquetas wiki (WikiTag, WikiPageTag)
  2. Comentarios internos en tickets (campo is_internal en TicketInternalComment)
  3. CMDB: historial, descubrimiento y agentes (los CIs, en service_desk)
  4. Dashboard de agente (AgentMetricSnapshot)
  5. Wiki PDF export job (WikiExportJob)
  6. Kanban avanzado: WIP limits, swimlanes (KanbanConfig, KanbanColumn)
  7. Sprint planning IA (SprintPlan, SprintPlanTask)
  8. SLA avanzado con festivos (SLACalendar, V21SLAHoliday)
"""
import uuid
from sqlalchemy import (Column, String, Boolean, Integer, Text,
                        DateTime, ForeignKey, Float)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.db.base import Base
from app.core.config import settings


# ─── 1. ETIQUETAS WIKI ────────────────────────────────────────────────────────

class WikiTag(Base):
    __tablename__ = "wiki_tags"
    id         = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String(36), ForeignKey("organizations.id"), nullable=True, index=True)  # audit #7
    space_id   = Column(String(36), ForeignKey("wiki_spaces.id", ondelete="CASCADE"),
                        nullable=False, index=True)
    name       = Column(String(80),  nullable=False)
    color      = Column(String(20),  default="#7a8aaa")
    is_active  = Column(Boolean, default=True, nullable=False)
    created_by = Column(String(36),  ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    page_tags  = relationship("WikiPageTag", back_populates="tag",
                              cascade="all, delete-orphan")


class WikiPageTag(Base):
    __tablename__ = "wiki_page_tags"
    id      = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String(36), ForeignKey("organizations.id"), nullable=True, index=True)  # audit #7
    page_id = Column(String(36), ForeignKey("wiki_pages.id", ondelete="CASCADE"),
                     nullable=False, index=True)
    tag_id  = Column(String(36), ForeignKey("wiki_tags.id",  ondelete="CASCADE"),
                     nullable=False, index=True)
    tag     = relationship("WikiTag", back_populates="page_tags")


# ─── 2. COMENTARIOS INTERNOS EN TICKETS ──────────────────────────────────────

class TicketInternalComment(Base):
    """Comentario interno solo visible para agentes (no para el cliente)."""
    __tablename__ = "ticket_internal_comments"
    id          = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String(36), ForeignKey("organizations.id"), nullable=True, index=True)  # audit #7
    ticket_id   = Column(String(36), ForeignKey("sd_tickets.id", ondelete="CASCADE"),
                         nullable=False, index=True)
    content     = Column(Text, nullable=False)
    is_internal = Column(Boolean, default=True)   # siempre True; campo para diferenciarlo
    created_by  = Column(String(36), ForeignKey("users.id"), nullable=True)
    updated_at  = Column(DateTime(timezone=True), server_default=func.now(),
                         onupdate=func.now())
    created_at  = Column(DateTime(timezone=True), server_default=func.now())


# ─── 3. CMDB ─────────────────────────────────────────────────────────────────
# Los CIs y sus relaciones viven en `sd_configuration_items` / `sd_ci_relations`
# (app/models/service_desk/cmdb.py). Auditoria 2026-11: aqui habia una segunda
# CMDB (`cmdb_items`) que no podia elegirse en un ticket; la migracion 110 la
# fundio con la del service desk.


# ─── 4. DASHBOARD DE AGENTE ───────────────────────────────────────────────────

class AgentMetricSnapshot(Base):
    """Snapshot diario de métricas por agente de soporte."""
    __tablename__ = "agent_metric_snapshots"
    id               = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String(36), ForeignKey("organizations.id"), nullable=True, index=True)  # audit #7
    agent_id         = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"),
                               nullable=False, index=True)
    snap_date        = Column(String(10),  nullable=False, index=True)   # YYYY-MM-DD
    open_tickets     = Column(Integer, default=0)
    resolved_today   = Column(Integer, default=0)
    avg_resolution_h = Column(Float,   default=0.0)    # horas promedio resolución
    sla_compliant    = Column(Integer, default=0)      # tickets dentro de SLA
    sla_breached     = Column(Integer, default=0)      # tickets fuera de SLA
    csat_score       = Column(Float,   nullable=True)  # promedio CSAT del día
    created_at       = Column(DateTime(timezone=True), server_default=func.now())


# ─── 5. WIKI PDF EXPORT ───────────────────────────────────────────────────────

class WikiExportJob(Base):
    """Trabajo de exportación de página wiki a PDF."""
    __tablename__ = "wiki_export_jobs"
    id         = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String(36), ForeignKey("organizations.id"), nullable=True, index=True)  # audit #7
    page_id    = Column(String(36), ForeignKey("wiki_pages.id", ondelete="CASCADE"),
                        nullable=False, index=True)
    status     = Column(String(20), default="pending")   # pending, done, error
    file_path  = Column(String(500), nullable=True)
    created_by = Column(String(36), ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


# ─── 6. KANBAN AVANZADO ───────────────────────────────────────────────────────

class KanbanConfig(Base):
    """Configuración del tablero Kanban por proyecto."""
    __tablename__ = "kanban_configs"
    id              = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String(36), ForeignKey("organizations.id"), nullable=True, index=True)  # audit #7
    project_id      = Column(String(36), ForeignKey("projects.id", ondelete="CASCADE"),
                              nullable=False, unique=True, index=True)
    swimlane_by     = Column(String(30), default="none")   # none, assignee, epic, issue_type, priority
    show_subtasks   = Column(Boolean, default=True)
    card_fields     = Column(Text, nullable=True)          # JSON: qué campos mostrar en la card
    created_at      = Column(DateTime(timezone=True), server_default=func.now())
    columns         = relationship("KanbanColumn", back_populates="config",
                                   cascade="all, delete-orphan",
                                   order_by="KanbanColumn.sort_order")


class KanbanColumn(Base):
    """Columna Kanban con límite WIP."""
    __tablename__ = "kanban_columns"
    id          = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String(36), ForeignKey("organizations.id"), nullable=True, index=True)  # audit #7
    config_id   = Column(String(36), ForeignKey("kanban_configs.id", ondelete="CASCADE"),
                         nullable=False, index=True)
    status      = Column(String(50),  nullable=False)    # valor de estado del workflow
    label       = Column(String(100), nullable=True)     # etiqueta personalizada
    wip_limit   = Column(Integer, nullable=True)         # None = sin límite
    color       = Column(String(20),  nullable=True)
    is_active   = Column(Boolean, default=True, nullable=False)
    sort_order  = Column(Integer, default=0)
    config      = relationship("KanbanConfig", back_populates="columns")


# ─── 7. SPRINT PLANNING IA ───────────────────────────────────────────────────

class SprintPlan(Base):
    """Plan de sprint generado por IA."""
    __tablename__ = "sprint_plans"
    id             = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String(36), ForeignKey("organizations.id"), nullable=True, index=True)  # audit #7
    project_id     = Column(String(36), ForeignKey("projects.id", ondelete="CASCADE"),
                             nullable=False, index=True)
    sprint_id      = Column(String(36), ForeignKey("sprints.id", ondelete="CASCADE"),
                             nullable=True,  index=True)
    name           = Column(String(200), nullable=False)
    total_points   = Column(Integer,  default=0)
    team_capacity  = Column(Integer,  default=0)      # story points disponibles del equipo
    ai_reasoning   = Column(Text,     nullable=True)  # explicación de la IA
    is_active      = Column(Boolean, default=True, nullable=False)
    status         = Column(String(20), default="draft")   # draft, accepted, rejected
    created_by     = Column(String(36), ForeignKey("users.id"), nullable=True)
    created_at     = Column(DateTime(timezone=True), server_default=func.now())
    tasks          = relationship("SprintPlanTask", back_populates="plan",
                                  cascade="all, delete-orphan")


class SprintPlanTask(Base):
    """Tarea incluida en un plan de sprint."""
    __tablename__ = "sprint_plan_tasks"
    id          = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String(36), ForeignKey("organizations.id"), nullable=True, index=True)  # audit #7
    plan_id     = Column(String(36), ForeignKey("sprint_plans.id", ondelete="CASCADE"),
                         nullable=False, index=True)
    task_id     = Column(String(36), ForeignKey("tasks.id", ondelete="CASCADE"),
                         nullable=False)
    priority    = Column(Integer, default=0)        # orden sugerido por IA
    ai_note     = Column(String(500), nullable=True)
    plan        = relationship("SprintPlan", back_populates="tasks")


# ─── 8. SLA AVANZADO CON FESTIVOS ────────────────────────────────────────────

class SLACalendar(Base):
    """Calendario de servicio para cálculo de SLA."""
    __tablename__ = "sla_calendars"
    id            = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String(36), ForeignKey("organizations.id"), nullable=True, index=True)  # audit #7
    name          = Column(String(100), nullable=False)
    timezone      = Column(String(50),  default=settings.DEFAULT_TIMEZONE)
    work_start    = Column(String(5),   default="09:00")   # HH:MM
    work_end      = Column(String(5),   default="18:00")
    is_active     = Column(Boolean, default=True, nullable=False)
    work_days     = Column(String(20),  default="1,2,3,4,5")  # CSV: 1=lun … 7=dom
    created_at    = Column(DateTime(timezone=True), server_default=func.now())
    holidays      = relationship("V21SLAHoliday", back_populates="calendar",
                                 cascade="all, delete-orphan")


class V21SLAHoliday(Base):
    """Día festivo en un calendario SLA."""
    __tablename__ = "sla_calendar_holidays"
    id          = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String(36), ForeignKey("organizations.id"), nullable=True, index=True)  # audit #7
    calendar_id = Column(String(36), ForeignKey("sla_calendars.id", ondelete="CASCADE"),
                         nullable=False, index=True)
    holiday_date= Column(String(10), nullable=False)   # YYYY-MM-DD
    is_active   = Column(Boolean, default=True, nullable=False)
    name        = Column(String(100), nullable=True)
    calendar    = relationship("SLACalendar", back_populates="holidays")

class CMDBChangelog(Base):
    """Historial de cambios de un activo CMDB."""
    __tablename__ = "cmdb_changelog"
    id         = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String(36), ForeignKey("organizations.id"), nullable=True, index=True)  # audit #7
    item_id    = Column(String(36), ForeignKey("sd_configuration_items.id", ondelete="CASCADE"),
                        nullable=False, index=True)
    user_id    = Column(String(36), ForeignKey("users.id"), nullable=True)
    action     = Column(String(30), nullable=False)   # created | updated | deleted
    field      = Column(String(100), nullable=True)   # campo cambiado
    old_value  = Column(Text, nullable=True)
    new_value  = Column(Text, nullable=True)
    summary    = Column(String(500), nullable=True)   # resumen legible
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    item = relationship("ConfigurationItem", foreign_keys=[item_id])
    user = relationship("User",     foreign_keys=[user_id])


# ─── DISCOVERY (Fase 1 ITSM Enhancement) ────────────────────────────────────────────────────────

class CMDBDiscoveryProvider(Base):
    """Configuración de un proveedor de discovery automático CMDB."""
    __tablename__ = "cmdb_discovery_providers"

    id              = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name            = Column(String(100), nullable=False)               # e.g. “Prod AWS”
    provider_type   = Column(String(30),  nullable=False, index=True)   # aws | kubernetes | vmware
    is_active       = Column(Boolean, default=True)
    config_json     = Column(Text, nullable=True)  # encrypted JSON with credentials
    organization_id = Column(String(36), ForeignKey("organizations.id",
                             ondelete="CASCADE"), nullable=True, index=True)
    last_run_at     = Column(DateTime(timezone=True), nullable=True)
    last_run_status = Column(String(20),  nullable=True)   # ok | error | running
    # Cadence control (ITSM-P04)
    scan_interval_minutes = Column(Integer, default=60)                 # run every N minutes
    next_run_at           = Column(DateTime(timezone=True), nullable=True)  # next scheduled run
    created_by      = Column(String(36),  ForeignKey("users.id"), nullable=True)
    created_at      = Column(DateTime(timezone=True), server_default=func.now())
    updated_at      = Column(DateTime(timezone=True), server_default=func.now(),
                             onupdate=func.now())
    jobs            = relationship("CMDBDiscoveryJob", back_populates="provider",
                                   cascade="all, delete-orphan",
                                   order_by="CMDBDiscoveryJob.started_at.desc()")


class CMDBDiscoveryJob(Base):
    """Log de ejecución de un job de discovery CMDB."""
    __tablename__ = "cmdb_discovery_jobs"

    id          = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String(36), ForeignKey("organizations.id"), nullable=True, index=True)  # audit #7
    provider_id = Column(String(36), ForeignKey("cmdb_discovery_providers.id",
                         ondelete="CASCADE"), nullable=False, index=True)
    status      = Column(String(20), default="running")  # running | ok | error | partial
    started_at  = Column(DateTime(timezone=True), server_default=func.now())
    finished_at = Column(DateTime(timezone=True), nullable=True)
    cis_created = Column(Integer, default=0)
    cis_updated = Column(Integer, default=0)
    cis_deactivated = Column(Integer, default=0)
    error_message   = Column(Text, nullable=True)
    summary_json    = Column(Text, nullable=True)  # JSON con detalles del run
    triggered_by    = Column(String(20), default="scheduler")  # scheduler | manual
    provider        = relationship("CMDBDiscoveryProvider", back_populates="jobs")


# ── On-Premise Agent Registrations (ITSM-P10/discovery gap) ──────────────────

class CMDBAgentRegistration(Base):
    """Registered on-premise agent (one per managed host).

    The raw token is returned once at registration.  Only its SHA-256 hash
    is persisted so that a DB breach does not expose usable tokens.
    """
    __tablename__ = "cmdb_agent_registrations"

    id            = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String(36), ForeignKey("organizations.id"), nullable=True, index=True)  # audit #7
    name          = Column(String(255), nullable=False)        # friendly name, e.g. "web01.corp.local"
    description   = Column(Text,        nullable=True)
    token_hash    = Column(String(64),  nullable=False, unique=True, index=True)  # SHA-256 hex
    token_prefix  = Column(String(8),   nullable=False)        # first 8 chars for display/audit
    os_type       = Column(String(10),  nullable=True)         # windows | linux
    is_active     = Column(Boolean,     default=True)
    last_checkin_at = Column(DateTime(timezone=True), nullable=True)
    last_checkin_ip = Column(String(45), nullable=True)
    last_hostname   = Column(String(255), nullable=True)
    ci_id         = Column(String(36),  ForeignKey("sd_configuration_items.id", ondelete="SET NULL"), nullable=True)
    created_by    = Column(String(36),  ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at    = Column(DateTime(timezone=True), server_default=func.now())
    updated_at    = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    ci         = relationship("ConfigurationItem", foreign_keys=[ci_id])
    creator    = relationship("User",      foreign_keys=[created_by])

