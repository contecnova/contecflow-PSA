"""
Enterprise models:
  - AuditLog     : Immutable audit trail for every data change
  - ProjectPermission: Per-project role overrides (granular access)
  - Webhook      : Outbound webhook subscriptions
  - WebhookDelivery: Delivery log
  - SSOConfig    : SAML/OIDC SSO configuration per org
  - Notification  : Real-time notification queue
  - ProjectTemplate / TemplateTask: Project templates UI
  - SubcontractorRate: Subcontractor management
  - RevenueForeccast: Financial forecast snapshots
"""
from sqlalchemy import (
    Column, String, Float, DateTime, ForeignKey, Text,
    Boolean, Integer, Enum, Date, BigInteger, Index, JSON
)
from sqlalchemy import event as _sa_event
from sqlalchemy.orm import Session as _SesionBase, relationship, validates
from sqlalchemy.sql import func
import enum
import uuid
from app.db.base import Base
from app.models.money import Money, Rate
from app.core.config import settings


# ── Audit Log ─────────────────────────────────────────────────────────────────

class AuditLog(Base):
    """
    Immutable audit trail. Written on every CREATE/UPDATE/DELETE across the app.
    Never deleted, never updated — append-only.
    """
    __tablename__ = "audit_logs"

    id          = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=True, index=True)  # audit #7
    # Who
    user_id     = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    user_name   = Column(String(255), nullable=True)   # snapshot to survive user deletion
    ip_address  = Column(String(45), nullable=True)
    user_agent  = Column(String(500), nullable=True)

    # What
    action      = Column(String(50), nullable=False, index=True)   # CREATE UPDATE DELETE LOGIN LOGOUT EXPORT
    resource    = Column(String(100), nullable=False, index=True)  # projects tasks users expenses ...
    resource_id = Column(String(36), nullable=True, index=True)
    resource_name = Column(String(255), nullable=True)             # human-readable snapshot

    # Detail
    old_values  = Column(Text, nullable=True)   # JSON of changed fields before
    new_values  = Column(Text, nullable=True)   # JSON of changed fields after
    metadata_   = Column("metadata", Text, nullable=True)  # extra context JSON

    # When
    created_at  = Column(DateTime(timezone=True), server_default=func.now(), index=True)

    # Cadena a prueba de manipulación (revisión 2026-11): ver app/db/cadena_auditoria.py
    seq          = Column(BigInteger, nullable=True)
    prev_hash    = Column(String(64), nullable=True)
    entry_hash   = Column(String(64), nullable=True)
    chain_key_id = Column(String(16), nullable=True)

    __table_args__ = (Index("ix_audit_logs_org_seq", "organization_id", "seq"),)

    user = relationship("User", foreign_keys=[user_id])


@_sa_event.listens_for(AuditLog, "before_insert")
def _encadenar_auditoria(mapper, connection, target) -> None:
    from app.db.cadena_auditoria import encadenar
    encadenar(connection, target)


@_sa_event.listens_for(_SesionBase, "after_flush")
def _olvidar_cabezas_de_auditoria(session, flush_context) -> None:
    from app.db.cadena_auditoria import olvidar_cabezas
    olvidar_cabezas(session)


@_sa_event.listens_for(_SesionBase, "before_flush")
def _olvidar_cabezas_antes(session, flush_context, instances) -> None:
    from app.db.cadena_auditoria import olvidar_cabezas
    olvidar_cabezas(session)


# Externos como internos (migracion 178): `hours_logged` de las asignaciones de
# externos se recalcula cuando cambian sus imputaciones o partes. Los ganchos de
# sesion los registra `app/services/externos/horas.py` al importarse (desde
# `app/main.py` y `app/worker.py`): un modelo no importa servicios.


# ── Per-project permissions ───────────────────────────────────────────────────

class ProjectPermissionLevel(str, enum.Enum):
    none     = "none"      # Explicitly blocked
    viewer   = "viewer"    # Read-only — see tasks, timelines, no financials
    member   = "member"    # Can log work, create tasks
    manager  = "manager"   # PM-level: edit project, see financials
    owner    = "owner"     # Full control including delete


class ProjectPermission(Base):
    """
    Per-project permission override for a user.
    Supersedes the user's global role for this specific project.
    """
    __tablename__ = "project_permissions"

    id           = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=True, index=True)  # audit #7
    project_id   = Column(String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id      = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    level        = Column(Enum(ProjectPermissionLevel), nullable=False, default=ProjectPermissionLevel.member)
    is_active    = Column(Boolean, default=True, nullable=False)
    can_see_financials = Column(Boolean, default=False)   # Costs, rates, budgets
    can_see_rates      = Column(Boolean, default=False)   # Hourly rates of teammates
    can_export         = Column(Boolean, default=True)
    granted_by   = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    granted_at   = Column(DateTime(timezone=True), server_default=func.now())
    expires_at   = Column(DateTime(timezone=True), nullable=True)  # Temporary access
    note         = Column(String(500), nullable=True)

    project = relationship("Project")
    user    = relationship("User", foreign_keys=[user_id])
    granter = relationship("User", foreign_keys=[granted_by])


# ── Webhooks ──────────────────────────────────────────────────────────────────

class WebhookEvent(str, enum.Enum):
    project_created      = "project.created"
    project_updated      = "project.updated"
    project_closed       = "project.closed"
    task_created         = "task.created"
    task_status_changed  = "task.status_changed"
    task_assigned        = "task.assigned"
    sprint_started       = "sprint.started"
    sprint_closed        = "sprint.closed"
    expense_submitted    = "expense.submitted"
    expense_approved     = "expense.approved"
    ticket_created       = "ticket.created"
    ticket_resolved      = "ticket.resolved"
    timesheet_submitted  = "timesheet.submitted"
    timesheet_approved   = "timesheet.approved"
    risk_created         = "risk.created"


class Webhook(Base):
    """Outbound webhook subscription."""
    __tablename__ = "webhooks"

    id          = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=True, index=True)  # audit #7
    name        = Column(String(255), nullable=False)
    url         = Column(String(1000), nullable=False)
    secret      = Column(String(255), nullable=True)   # HMAC signing secret
    events      = Column(Text, nullable=False)          # JSON array of WebhookEvent
    is_active   = Column(Boolean, default=True)
    project_id  = Column(String(36), ForeignKey("projects.id", ondelete="SET NULL"), nullable=True, index=True)  # None = all projects

    # Stats
    total_deliveries     = Column(Integer, default=0)
    failed_deliveries    = Column(Integer, default=0)
    last_triggered_at    = Column(DateTime(timezone=True), nullable=True)

    # Circuit breaker — auto-suspends the webhook after consecutive failures
    consecutive_failures = Column(Integer, default=0, nullable=False)
    suspended_at         = Column(DateTime(timezone=True), nullable=True)

    created_by  = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    created_at  = Column(DateTime(timezone=True), server_default=func.now())
    updated_at  = Column(DateTime(timezone=True), onupdate=func.now())

    deliveries = relationship("WebhookDelivery", back_populates="webhook",
                              cascade="all, delete-orphan",
                              order_by="WebhookDelivery.created_at.desc()")
    creator  = relationship("User", foreign_keys=[created_by])
    project  = relationship("Project")


class WebhookDelivery(Base):
    """Log of each webhook delivery attempt."""
    __tablename__ = "webhook_deliveries"

    id          = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=True, index=True)  # audit #7
    webhook_id  = Column(String(36), ForeignKey("webhooks.id", ondelete="CASCADE"), nullable=False, index=True)
    event       = Column(String(100), nullable=False)
    payload     = Column(Text, nullable=True)           # JSON sent
    status_code = Column(Integer, nullable=True)
    response    = Column(Text, nullable=True)
    success     = Column(Boolean, default=False)
    error       = Column(String(500), nullable=True)
    attempt     = Column(Integer, default=1)
    duration_ms = Column(Integer, nullable=True)
    created_at  = Column(DateTime(timezone=True), server_default=func.now())

    webhook = relationship("Webhook", back_populates="deliveries")


# ── SSO Configuration ─────────────────────────────────────────────────────────

class SSOProvider(str, enum.Enum):
    saml    = "saml"
    oidc    = "oidc"
    google  = "google"
    azure   = "azure_ad"
    okta    = "okta"


class SSOConfig(Base):
    """SSO/SAML/OIDC configuration."""
    __tablename__ = "sso_configs"

    id          = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    provider    = Column(Enum(SSOProvider), nullable=False)
    is_active   = Column(Boolean, default=False)
    is_deleted  = Column(Boolean, default=False, nullable=False)
    is_default  = Column(Boolean, default=False)   # Auto-redirect to SSO on login page

    # SAML
    saml_entity_id       = Column(String(500), nullable=True)
    saml_sso_url         = Column(String(500), nullable=True)
    saml_slo_url         = Column(String(500), nullable=True)
    saml_certificate     = Column(Text, nullable=True)
    saml_attribute_email = Column(String(200), default="email")
    saml_attribute_name  = Column(String(200), default="displayName")
    saml_attribute_role  = Column(String(200), nullable=True)

    # OIDC / OAuth2
    oidc_client_id       = Column(String(500), nullable=True)
    oidc_client_secret   = Column(String(500), nullable=True)
    oidc_discovery_url   = Column(String(500), nullable=True)
    oidc_scopes          = Column(String(500), default="openid email profile")

    # Role mapping from SSO groups to Contecflow roles
    role_mapping         = Column(Text, nullable=True)  # JSON: {"SSO_GROUP": "pm", ...}
    # Auditoria 2026-11: el texto del boton del login (la pantalla lo mandaba y
    # se perdia) y el claim del id_token donde vienen los grupos del IdP.
    name                 = Column(String(120), nullable=True)
    groups_claim         = Column(String(100), nullable=True, default="groups")
    organization_id      = Column(String(36), ForeignKey("organizations.id", ondelete="SET NULL"), nullable=True, index=True)

    # Auto-provisioning
    auto_create_users    = Column(Boolean, default=True)
    default_role         = Column(String(50), default="employee")
    allowed_domains      = Column(String(500), nullable=True)  # comma-separated

    created_by  = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    created_at  = Column(DateTime(timezone=True), server_default=func.now())
    updated_at  = Column(DateTime(timezone=True), onupdate=func.now())

    organization = relationship("Organization", foreign_keys=[organization_id])


# ── In-app Notifications ──────────────────────────────────────────────────────

class NotificationType(str, enum.Enum):
    task_assigned        = "task_assigned"
    task_mentioned       = "task_mentioned"
    task_due_soon        = "task_due_soon"
    task_overdue         = "task_overdue"
    sprint_started       = "sprint_started"
    sprint_ending        = "sprint_ending"
    expense_approved     = "expense_approved"
    expense_rejected     = "expense_rejected"
    ticket_assigned      = "ticket_assigned"
    ticket_replied       = "ticket_replied"
    ticket_resolved      = "ticket_resolved"
    ticket_created       = "ticket_created"
    ticket_updated       = "ticket_updated"
    ticket_sla_warning   = "ticket_sla_warning"
    ticket_sla_breached  = "ticket_sla_breached"
    ticket_escalated     = "ticket_escalated"
    approval_requested   = "approval_requested"
    milestone_approved   = "milestone_approved"   # migracion 200
    milestone_rejected   = "milestone_rejected"   # migracion 200
    project_risk_high    = "project_risk_high"
    timesheet_reminder   = "timesheet_reminder"
    timesheet_approved   = "timesheet_approved"
    budget_warning       = "budget_warning"
    mention              = "mention"
    automation           = "automation"
    system               = "system"


class Notification(Base):
    """In-app notification for a user."""
    __tablename__ = "notifications"

    id            = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=True, index=True)  # audit #7
    user_id       = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    type          = Column(Enum(NotificationType), nullable=False, index=True)
    title         = Column(String(255), nullable=False)
    body          = Column(String(1000), nullable=True)
    icon          = Column(String(10), default="🔔")
    color         = Column(String(20), default="#00d4ff")

    # Link back to the resource
    resource      = Column(String(100), nullable=True)   # projects tasks tickets ...
    resource_id   = Column(String(36), nullable=True)
    action_url    = Column(String(500), nullable=True)   # frontend route

    is_active     = Column(Boolean, default=True, nullable=False, index=True)
    is_read       = Column(Boolean, default=False, index=True)
    read_at       = Column(DateTime(timezone=True), nullable=True)
    created_at    = Column(DateTime(timezone=True), server_default=func.now(), index=True)

    user = relationship("User", foreign_keys=[user_id])

    @validates("title")
    def _titulo_sin_emojis(self, _clave, valor):
        """Sin emojis en origen (campana, 16-11-2026): ver `app/core/sin_emojis.py`."""
        from app.core.sin_emojis import sin_emojis
        return sin_emojis(valor)


# ── Subcontractors ────────────────────────────────────────────────────────────

class Subcontractor(Base):
    """External supplier / freelancer / subcontractor company."""
    __tablename__ = "subcontractors"

    id          = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=True, index=True)  # audit #7
    code        = Column(String(20), nullable=False)      # SUB-001
    name        = Column(String(255), nullable=False)
    company     = Column(String(255), nullable=True)
    email       = Column(String(255), nullable=True)
    phone       = Column(String(50), nullable=True)
    country     = Column(String(100), nullable=True)
    vat_number  = Column(String(50), nullable=True)
    currency    = Column(String(3), default=settings.DEFAULT_CURRENCY)
    is_active   = Column(Boolean, default=True)
    notes       = Column(Text, nullable=True)
    created_at  = Column(DateTime(timezone=True), server_default=func.now())
    updated_at  = Column(DateTime(timezone=True), onupdate=func.now())
    # Proveedores y externalizacion (migracion 189, docs/PROVEEDORES_Y_EXTERNALIZACION.md).
    # `kind`: freelance (persona fisica: es su unica persona y el recurso) |
    # company. `engagement_modes`: staff_augmentation | outsourcing |
    # managed_services (combinables). `lifecycle_status`: onboarding | active |
    # suspended | offboarded.
    kind             = Column(String(20), nullable=False, default="company", server_default="company")
    engagement_modes = Column(JSON, nullable=True)
    lifecycle_status = Column(String(20), nullable=False, default="active", server_default="active")
    freelancer_worker_id = Column(String(36), ForeignKey("subcontractor_workers.id", ondelete="SET NULL", use_alter=True,
                                                         name="fk_subcontractors_freelancer_worker"), nullable=True)
    alm_vendor_id    = Column(String(36), ForeignKey("alm_vendors.id", ondelete="SET NULL"), nullable=True, index=True)
    internal_owner_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    legal_name       = Column(String(255), nullable=True)
    website          = Column(String(500), nullable=True)
    address          = Column(Text, nullable=True)
    training_enabled = Column(Boolean, default=False, nullable=False, server_default="0")
    data_access      = Column(Boolean, default=False, nullable=False, server_default="0")
    data_categories  = Column(String(500), nullable=True)
    systems_access   = Column(String(500), nullable=True)
    risk_level       = Column(String(20), nullable=True)
    risk_score       = Column(Float, nullable=True)
    next_review_date = Column(Date, nullable=True)
    suspended_at     = Column(Date, nullable=True)
    offboarded_at    = Column(Date, nullable=True)
    offboarding_reason = Column(String(255), nullable=True)

    rates       = relationship("SubcontractorRate", back_populates="subcontractor",
                               cascade="all, delete-orphan")
    assignments = relationship("SubcontractorAssignment", back_populates="subcontractor")
    workers     = relationship("SubcontractorWorker", back_populates="subcontractor",
                               foreign_keys="SubcontractorWorker.subcontractor_id",
                               cascade="all, delete-orphan")


class SubcontractorRate(Base):
    """Rate card for a subcontractor (can vary by project/skill)."""
    __tablename__ = "subcontractor_rates"

    id               = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=True, index=True)  # audit #7
    subcontractor_id = Column(String(36), ForeignKey("subcontractors.id", ondelete="CASCADE"), nullable=False, index=True)
    description      = Column(String(255), nullable=False)   # "Senior Dev", "DevOps", etc
    cost_rate        = Column(Rate, nullable=False)          # What we pay them €/h
    sell_rate        = Column(Rate, nullable=True)           # What we charge client €/h
    currency         = Column(String(3), default=settings.DEFAULT_CURRENCY)
    is_active        = Column(Boolean, default=True, nullable=False)
    valid_from       = Column(Date, nullable=True)
    valid_until      = Column(Date, nullable=True)

    subcontractor = relationship("Subcontractor", back_populates="rates")


class SubcontractorWorker(Base):
    """Individual person provided by a subcontractor company."""
    __tablename__ = "subcontractor_workers"

    id               = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=True, index=True)  # audit #7
    subcontractor_id = Column(String(36), ForeignKey("subcontractors.id", ondelete="CASCADE"), nullable=False, index=True)
    # Linked User record (resource) created automatically on worker creation
    user_id          = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    name             = Column(String(255), nullable=False)
    role             = Column(String(100), nullable=True)    # "Senior Developer", "DevOps Engineer"
    email            = Column(String(255), nullable=True)
    phone            = Column(String(50), nullable=True)
    cost_rate        = Column(Rate, nullable=True)          # €/h we pay them
    sell_rate        = Column(Rate, nullable=True)          # €/h we charge client
    currency         = Column(String(3), default=settings.DEFAULT_CURRENCY)
    available_from   = Column(Date, nullable=True)
    available_until  = Column(Date, nullable=True)
    weekly_capacity_hours = Column(Float, nullable=True)     # Hours/week capacity (default 40)
    is_active        = Column(Boolean, default=True)
    notes            = Column(Text, nullable=True)
    # Externos como internos (migracion 178). `has_access`: con login (imputa
    # el); sin el, es un recurso planificable cuyas horas registra el PM.
    # `access_until`: el acceso caduca ese dia (fin de contrato; por defecto
    # `available_until`). `internal_owner_id`: responsable interno obligatorio
    # en altas nuevas (avisos de caducidad, consumo y baja).
    has_access       = Column(Boolean, default=True, nullable=False, server_default="1")
    access_until     = Column(Date, nullable=True)
    internal_owner_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    access_expiry_notified_at = Column(Date, nullable=True)
    # Migracion 191: contacto del portal del proveedor (informes, evidencias,
    # paquetes, consumo y estado de cuenta de SU proveedor; ver proveedores.portal).
    supplier_portal  = Column(Boolean, default=False, nullable=False, server_default="0")
    created_at       = Column(DateTime(timezone=True), server_default=func.now())
    updated_at       = Column(DateTime(timezone=True), onupdate=func.now())

    subcontractor = relationship("Subcontractor", back_populates="workers", foreign_keys=[subcontractor_id])
    user          = relationship("User", foreign_keys=[user_id])
    internal_owner = relationship("User", foreign_keys=[internal_owner_id])
    assignments   = relationship("SubcontractorAssignment", back_populates="worker")


# SubcontractorWorkerSkill: retirado el 23-11-2026 (auditoria 2026-11-22, M-MOD3: sin uso fuera de app/models). La tabla `subcontractor_worker_skills` la borra la migracion de esa fecha. Las habilidades del externo son las de su usuario (`user_skills`, migracion 178).


class SubcontractorAssignment(Base):
    """Assignment of a subcontractor to a project."""
    __tablename__ = "subcontractor_assignments"

    id               = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=True, index=True)  # audit #7
    subcontractor_id = Column(String(36), ForeignKey("subcontractors.id", ondelete="RESTRICT"), nullable=False, index=True)
    worker_id        = Column(String(36), ForeignKey("subcontractor_workers.id", ondelete="SET NULL"), nullable=True, index=True)
    project_id       = Column(String(36), ForeignKey("projects.id", ondelete="RESTRICT"), nullable=False, index=True)
    rate_id          = Column(String(36), ForeignKey("subcontractor_rates.id", ondelete="SET NULL"), nullable=True, index=True)
    po_number        = Column(String(100), nullable=True)    # Purchase Order
    po_amount        = Column(Money, nullable=True)          # PO ceiling €
    hours_contracted = Column(Float, nullable=True)
    hours_logged     = Column(Float, default=0)
    start_date       = Column(Date, nullable=True)
    end_date         = Column(Date, nullable=True)
    notes            = Column(Text, nullable=True)
    # Migracion 178: la asignacion con persona crea su ProjectMember (y lo
    # cierra al terminar). `consumption_alert_pct`: ultimo umbral avisado.
    project_member_id = Column(String(36), ForeignKey("project_members.id", ondelete="SET NULL"), nullable=True, index=True)
    is_active        = Column(Boolean, default=True, nullable=False, server_default="1")
    ended_at         = Column(Date, nullable=True)
    consumption_alert_pct = Column(Float, nullable=True)
    created_at       = Column(DateTime(timezone=True), server_default=func.now())

    subcontractor = relationship("Subcontractor", back_populates="assignments")
    worker        = relationship("SubcontractorWorker", back_populates="assignments")
    project       = relationship("Project")
    rate          = relationship("SubcontractorRate")


class SubcontractorInvoice(Base):
    """Factura recibida de un subcontratista (coste a registrar)."""
    __tablename__ = "subcontractor_invoices"

    id               = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=True, index=True)  # audit #7
    subcontractor_id = Column(String(36), ForeignKey("subcontractors.id", ondelete="CASCADE"), nullable=False, index=True)
    assignment_id    = Column(String(36), ForeignKey("subcontractor_assignments.id", ondelete="SET NULL"), nullable=True, index=True)
    invoice_number   = Column(String(100), nullable=False)
    issue_date       = Column(Date, nullable=False)
    due_date         = Column(Date, nullable=True)
    amount           = Column(Money, nullable=False)          # subtotal sin IVA
    tax_pct          = Column(Float, default=settings.DEFAULT_TAX_RATE)
    total            = Column(Money, nullable=False)          # con IVA
    currency         = Column(String(3), default=settings.DEFAULT_CURRENCY)
    status           = Column(String(20), default="received") # received | approved | paid | rejected
    paid_date        = Column(Date, nullable=True)
    description      = Column(Text, nullable=True)
    file_path        = Column(String(500), nullable=True)     # adjunto PDF
    created_at       = Column(DateTime(timezone=True), server_default=func.now())
    # Migracion 189: quien la registra (segregacion: no aprueba su estado de cuenta)
    # y el contrato al que corresponde.
    created_by       = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    contract_id      = Column(String(36), ForeignKey("supplier_contracts.id", ondelete="SET NULL"), nullable=True, index=True)
    # Migracion 200 (A42): quien la aprueba y cuando (recibida -> aprobada -> pagada;
    # quien la registra no la aprueba ni la paga).
    approved_by      = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    approved_at      = Column(DateTime(timezone=True), nullable=True)

    subcontractor = relationship("Subcontractor")
    assignment    = relationship("SubcontractorAssignment")


class SubcontractorTimeLog(Base):
    """Registro de horas trabajadas por un subcontratista en un proyecto."""
    __tablename__ = "subcontractor_timelogs"

    id               = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=True, index=True)  # audit #7
    assignment_id    = Column(String(36), ForeignKey("subcontractor_assignments.id", ondelete="CASCADE"), nullable=False, index=True)
    subcontractor_id = Column(String(36), ForeignKey("subcontractors.id", ondelete="RESTRICT"), nullable=False, index=True)
    project_id       = Column(String(36), ForeignKey("projects.id", ondelete="SET NULL"), nullable=True, index=True)
    log_date         = Column(Date, nullable=False)
    hours            = Column(Float, nullable=False)
    description      = Column(String(500), nullable=True)
    task_reference   = Column(String(100), nullable=True)     # referencia a tarea o entregable
    # Migracion 178: el parte manual es solo para externos SIN acceso (o
    # importado). `worker_id`: de quien son las horas; `source`: manual | import.
    worker_id        = Column(String(36), ForeignKey("subcontractor_workers.id", ondelete="SET NULL"), nullable=True, index=True)
    source           = Column(String(20), nullable=False, default="manual", server_default="manual")
    cost_amount      = Column(Money, nullable=True)           # horas × coste_tarifa
    is_active        = Column(Boolean, default=True, nullable=False)
    is_invoiced      = Column(Boolean, default=False)         # incluido en alguna factura
    invoice_id       = Column(String(36), ForeignKey("subcontractor_invoices.id", ondelete="SET NULL"), nullable=True, index=True)
    created_at       = Column(DateTime(timezone=True), server_default=func.now())

    assignment    = relationship("SubcontractorAssignment")
    subcontractor = relationship("Subcontractor")
    project       = relationship("Project")


# ── Revenue Forecast ──────────────────────────────────────────────────────────

class RevenueForecast(Base):
    """
    Monthly revenue & margin forecast per project.
    Updated when milestones change, project status changes, or manually.
    """
    __tablename__ = "revenue_forecasts"

    id           = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=True, index=True)  # audit #7
    project_id   = Column(String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    year         = Column(Integer, nullable=False, index=True)
    month        = Column(Integer, nullable=False)        # 1-12

    # Revenue
    revenue_planned  = Column(Money, default=0)   # What we expect to bill
    revenue_actual   = Column(Money, default=0)   # What we actually billed/recognized
    revenue_forecast = Column(Money, default=0)   # Best current estimate

    # Cost
    cost_planned  = Column(Money, default=0)
    cost_actual   = Column(Money, default=0)

    # Hours
    hours_planned = Column(Float, default=0)
    hours_actual  = Column(Float, default=0)

    # Margin
    margin_pct    = Column(Float, nullable=True)  # Computed: (revenue-cost)/revenue

    notes         = Column(String(500), nullable=True)
    updated_at    = Column(DateTime(timezone=True), onupdate=func.now(), server_default=func.now())

    project = relationship("Project")
