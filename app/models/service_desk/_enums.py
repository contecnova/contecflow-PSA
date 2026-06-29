"""Service-desk enums — shared base for the service_desk model package."""
import sqlalchemy as sa
from sqlalchemy import Column, String, Float, DateTime, ForeignKey, Text, Boolean, Integer, Enum, UniqueConstraint
from sqlalchemy.orm import relationship, synonym
from sqlalchemy.sql import func
import enum
import uuid
from app.db.base import Base
from app.core.config import settings


class TicketType(str, enum.Enum):
    incident = "incident"
    service_request = "service_request"
    change = "change"
    problem = "problem"
    question = "question"


class TicketStatus(str, enum.Enum):
    new = "new"
    assigned = "assigned"
    in_progress = "in_progress"
    pending_client = "pending_client"
    pending_third = "pending_third"
    resolved = "resolved"
    closed = "closed"
    cancelled = "cancelled"


class TicketPriority(str, enum.Enum):
    p1_critical = "p1_critical"
    p2_high = "p2_high"
    p3_medium = "p3_medium"
    p4_low = "p4_low"


class TicketUrgency(str, enum.Enum):
    critical = "critical"
    high = "high"
    medium = "medium"
    low = "low"


class TicketImpact(str, enum.Enum):
    enterprise = "enterprise"
    department = "department"
    user = "user"
    minimal = "minimal"


class SupportLevel(str, enum.Enum):
    l1 = "l1"
    l2 = "l2"
    l3 = "l3"


class SLAStatus(str, enum.Enum):
    ok = "ok"
    at_risk = "at_risk"
    breached = "breached"
    paused = "paused"


class CIType(str, enum.Enum):
    application = "application"
    server = "server"
    database = "database"
    network = "network"
    service = "service"
    module = "module"
    integration = "integration"
    other = "other"


class CIStatus(str, enum.Enum):
    operational = "operational"
    degraded = "degraded"
    maintenance = "maintenance"
    retired = "retired"


class ProblemStatus(str, enum.Enum):
    open = "open"
    investigating = "investigating"
    known_error = "known_error"
    resolved = "resolved"
    closed = "closed"


class KBStatus(str, enum.Enum):
    draft = "draft"
    published = "published"
    archived = "archived"


class TicketLinkType(str, enum.Enum):
    relates_to   = "relates_to"
    duplicates   = "duplicates"
    caused_by    = "caused_by"
    blocks       = "blocks"
    child_of     = "child_of"


class SLAEventType(str, enum.Enum):
    paused        = "paused"
    resumed       = "resumed"
    breach_warn   = "breach_warn"    # 75% del SLA consumido
    breached      = "breached"       # SLA roto
    met           = "met"            # SLA cumplido al cerrar


class CIRelationType(str, enum.Enum):
    depends_on   = "depends_on"     # A depende de B
    hosts        = "hosts"          # servidor aloja aplicación
    connects_to  = "connects_to"    # red
    backed_up_by = "backed_up_by"
    monitored_by = "monitored_by"
    part_of      = "part_of"


class ChangeType(str, enum.Enum):
    standard  = "standard"    # pre-aprobado, bajo riesgo, procedimiento documentado
    normal    = "normal"      # requiere CAB
    emergency = "emergency"   # ECAB, urgente


class ChangeRisk(str, enum.Enum):
    low    = "low"
    medium = "medium"
    high   = "high"
    critical = "critical"


class ChangeStatus(str, enum.Enum):
    draft           = "draft"
    submitted       = "submitted"
    cab_review      = "cab_review"      # pendiente aprobación CAB
    approved        = "approved"
    scheduled       = "scheduled"
    in_progress     = "in_progress"
    implemented     = "implemented"
    post_review     = "post_review"     # PIR: Post-Implementation Review
    closed_success  = "closed_success"
    closed_failed   = "closed_failed"
    cancelled       = "cancelled"


class MajorIncidentStatus(str, enum.Enum):
    active   = "active"
    resolved = "resolved"
    closed   = "closed"


class OnCallRotationType(str, enum.Enum):
    weekly   = "weekly"    # cada semana rota el agente
    daily    = "daily"     # cada día rota
    custom   = "custom"    # intervalos definidos manualmente


class EscalationTrigger(str, enum.Enum):
    sla_at_risk   = "sla_at_risk"    # SLA al 75%
    sla_breached  = "sla_breached"   # SLA roto
    idle_hours    = "idle_hours"     # Sin actividad N horas
    priority      = "priority"       # Prioridad específica sin asignar
    reopened      = "reopened"       # Ticket reabierto


class EscalationAction(str, enum.Enum):
    notify_manager    = "notify_manager"     # notificar al jefe del agente
    notify_group_lead = "notify_group_lead"  # notificar al lead del grupo
    reassign_group    = "reassign_group"     # mover a otro grupo
    elevate_priority  = "elevate_priority"   # subir prioridad
    notify_custom     = "notify_custom"      # enviar a lista custom


class AssetType(str, enum.Enum):
    hardware    = "hardware"    # servidores, PCs, móviles, periféricos
    software    = "software"    # licencias, aplicaciones
    license     = "license"     # licencia de software específica
    consumable  = "consumable"  # fungibles (cartuchos, cables...)
    cloud       = "cloud"       # recursos cloud (VMs, storage, etc.)
    other       = "other"


class AssetStatus(str, enum.Enum):
    in_stock      = "in_stock"      # en almacén
    deployed      = "deployed"      # en uso
    in_repair     = "in_repair"     # en reparación
    retired       = "retired"       # dado de baja
    disposed      = "disposed"      # eliminado / reciclado
    loaned        = "loaned"        # prestado temporalmente
    pending_order = "pending_order" # pedido pero no recibido


class StatusPageComponentStatus(str, enum.Enum):
    operational          = "operational"
    degraded_performance = "degraded_performance"
    partial_outage       = "partial_outage"
    major_outage         = "major_outage"
    maintenance          = "maintenance"
