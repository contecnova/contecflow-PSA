"""service_desk.ops models — split from the former 1385-LOC god-file."""

from sqlalchemy import Column, String, Float, DateTime, ForeignKey, Text, Boolean, Integer, Enum
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import uuid
from app.db.base import Base


from app.models.service_desk._enums import StatusPageComponentStatus

class ITSMMetricSnapshot(Base):
    """Hourly ITSM KPI snapshot for trend analytics and dashboards."""
    __tablename__ = "sd_itsm_metric_snapshots"

    id                  = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String(36), ForeignKey("organizations.id"), nullable=True, index=True)  # audit #7
    snapshot_at         = Column(DateTime(timezone=True), nullable=False, index=True)
    period_hours        = Column(Integer, default=24)
    tickets_total       = Column(Integer, default=0)
    tickets_open        = Column(Integer, default=0)
    tickets_resolved    = Column(Integer, default=0)
    sla_compliance_pct  = Column(Float, nullable=True)
    mttr_minutes        = Column(Float, nullable=True)
    fcr_pct             = Column(Float, nullable=True)
    avg_csat            = Column(Float, nullable=True)
    breached_sla        = Column(Integer, default=0)

class ComplianceReport(Base):
    """Persisted ITIL/ISO 20000 compliance report generated periodically."""
    __tablename__ = "sd_compliance_reports"

    id           = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String(36), ForeignKey("organizations.id"), nullable=True, index=True)  # audit #7
    generated_at = Column(DateTime(timezone=True), nullable=False, index=True)
    period_days  = Column(Integer, default=30)
    overall_score = Column(Integer, default=0)   # 0-100
    cmm_level    = Column(Integer, default=1)    # 1-5
    report_json  = Column(Text, nullable=True)   # full JSON report

class StatusPageComponent(Base):
    """Componente visible en la página pública de estado del servicio."""
    __tablename__ = "sd_status_components"

    id          = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String(36), ForeignKey("organizations.id"), nullable=True, index=True)  # audit #7
    name        = Column(String(255), nullable=False)
    description = Column(String(500), nullable=True)
    group_name  = Column(String(100), nullable=True)     # agrupación (ej: "API", "Frontend")
    sort_order  = Column(Integer, default=0)
    status      = Column(Enum(StatusPageComponentStatus), default=StatusPageComponentStatus.operational)
    is_public   = Column(Boolean, default=True)

    # Vínculo con CI (sincroniza el estado automáticamente)
    ci_id       = Column(String(36), ForeignKey("sd_configuration_items.id"), nullable=True)

    uptime_30d_pct = Column(Float, nullable=True)        # calculado periódicamente
    created_at  = Column(DateTime(timezone=True), server_default=func.now())
    updated_at  = Column(DateTime(timezone=True), onupdate=func.now())

    ci = relationship("ConfigurationItem")
    incidents = relationship("StatusPageIncident", back_populates="component",
                             cascade="all, delete-orphan")

class StatusPageIncident(Base):
    """Incidente publicado en la página de estado (comunicación externa)."""
    __tablename__ = "sd_status_incidents"

    id           = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String(36), ForeignKey("organizations.id"), nullable=True, index=True)  # audit #7
    component_id = Column(String(36), ForeignKey("sd_status_components.id", ondelete="CASCADE"), nullable=False, index=True)
    title        = Column(String(500), nullable=False)
    # JSON: [{time, status, message}] — timeline de actualizaciones
    updates      = Column(Text, default="[]")
    status       = Column(String(30), default="investigating")  # investigating|identified|monitoring|resolved
    impact       = Column(Enum(StatusPageComponentStatus), default=StatusPageComponentStatus.partial_outage)
    started_at   = Column(DateTime(timezone=True), server_default=func.now())
    resolved_at  = Column(DateTime(timezone=True), nullable=True)

    # Ticket ITSM vinculado
    ticket_id    = Column(String(36), ForeignKey("sd_tickets.id"), nullable=True)

    component = relationship("StatusPageComponent", back_populates="incidents")
    ticket    = relationship("Ticket")


class MonitoringAlert(Base):
    """Una alerta de monitorizacion y la incidencia que abrio.

    `dedupe_key` identifica la alerta en su origen (la huella de Alertmanager,
    o la clave que mande el sistema): mientras siga abierta, las repeticiones
    suman en `occurrences` y no abren otra incidencia.
    """
    __tablename__ = "sd_monitoring_alerts"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String(36), ForeignKey("organizations.id"), nullable=True, index=True)
    source = Column(String(50), nullable=False)
    dedupe_key = Column(String(255), nullable=False, index=True)
    status = Column(String(20), default="firing", nullable=False, index=True)  # firing | resolved
    severity = Column(String(30), nullable=True)
    title = Column(String(500), nullable=False)
    description = Column(Text, nullable=True)
    ci_id = Column(String(36), ForeignKey("sd_configuration_items.id", ondelete="SET NULL"), nullable=True)
    ticket_id = Column(String(36), ForeignKey("sd_tickets.id", ondelete="SET NULL"), nullable=True, index=True)
    occurrences = Column(Integer, default=1, nullable=False)
    first_seen_at = Column(DateTime(timezone=True), server_default=func.now())
    last_seen_at = Column(DateTime(timezone=True), server_default=func.now())
    resolved_at = Column(DateTime(timezone=True), nullable=True)
