"""
v15 models — all remaining pending features:
  Organization          : Multi-tenancy root — every entity belongs to an org
  MFAConfig             : TOTP/2FA per user
  MFABackupCode         : One-time backup codes for MFA
  SlackConfig           : Slack/Teams workspace connection
  SlackNotificationLog  : Audit of Slack messages sent
  Budget                : Multi-period department budgets
  BudgetLine            : Budget line with its monthly split (revision 2026-11)
  AITaskEstimate        : AI-suggested hour estimates for tasks
  AITicketTriage        : AI triage result per SD ticket
  ScenarioModel         : What-if capacity scenario
  ScenarioProject       : Simulated project inside a scenario
  PDFExportJob          : Queued/completed PDF export jobs
  BIToken               : BI connector tokens (Power BI / Tableau)
"""
from sqlalchemy import (
    Column, String, Float, DateTime, ForeignKey, Text,
    Boolean, Integer, Date, UniqueConstraint
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import uuid
from app.db.base import Base
from app.core.config import settings


# ── Multi-tenancy ─────────────────────────────────────────────────────────────

class Organization(Base):
    """Root tenant entity — every org has its own isolated data space."""
    __tablename__ = "organizations"

    # Exención explícita del filtro automático de tenant (auditoría 2026-08, P1-7).
    # Organization ES el tenant, así que no tiene columna de tenant a la que
    # filtrar. TenantSession ya no deja pasar sin filtrar a un modelo sólo porque
    # le falte la columna — eso era un fail-open silencioso —, así que la exención
    # tiene que declararse aquí, donde se ve al leer el modelo.
    #
    # Consecuencia: cualquier endpoint que reciba un organization_id del cliente y
    # lo use contra este modelo DEBE guardarlo a mano, con require_superadmin (si
    # la operación es legítimamente entre tenants) o con assert_org_id_is_own (si
    # es del propio tenant). El inventario de esas rutas está cerrado por
    # tests/test_organization_tenant_isolation.py.
    _tenant_exempt = True
    _tenant_exempt_reason = "Organization es la propia entidad tenant; no hay columna a la que filtrar"

    id           = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name         = Column(String(255), nullable=False)
    slug         = Column(String(100), nullable=False, unique=True, index=True)
    # Dominio propio de la empresa (modo de entrada `subdomain`): app.cliente.com
    domain       = Column(String(255), nullable=True, unique=True)
    # Por que esta suspendida (se pide al suspender y se borra al reactivar).
    suspension_reason = Column(Text, nullable=True)
    # Baja definitiva (app/services/baja_de_empresa_service.py): cuando se pidio,
    # desde cuando se pueden borrar sus datos y quien la pidio.
    deletion_requested_at = Column(DateTime(timezone=True), nullable=True)
    deletion_purge_after = Column(DateTime(timezone=True), nullable=True)
    deletion_requested_by = Column(String(36), nullable=True)
    plan         = Column(String(20), default="starter")  # starter | pro | enterprise
    is_active    = Column(Boolean, default=True)
    max_users    = Column(Integer, default=25)
    max_projects = Column(Integer, default=100)
    logo_url     = Column(String(500), nullable=True)
    primary_color = Column(String(7), nullable=True)    # hex e.g. #1a73e8
    timezone     = Column(String(50), default=settings.DEFAULT_TIMEZONE)
    locale       = Column(String(10), default=settings.DEFAULT_LANGUAGE)
    admin_email  = Column(String(255), nullable=True)
    # Política de seguridad: si está activa, todos los usuarios de esta
    # organización deben tener MFA habilitada para poder completar el login.
    # Aplicado en auth_core.py durante el flujo de password+MFA.
    require_mfa  = Column(Boolean, default=False, nullable=False, server_default="0")
    # Per-organization SCIM bearer token (SHA-256 hex hash; the plaintext token
    # is shown to the admin once at generation time and never stored). Used to
    # authenticate SCIM provisioning calls scoped to THIS org only.
    scim_token_hash = Column(String(64), nullable=True)
    created_at   = Column(DateTime(timezone=True), server_default=func.now())
    updated_at   = Column(DateTime(timezone=True), onupdate=func.now())

    users    = relationship("User", back_populates="organization",
                            foreign_keys="User.organization_id")
    user_memberships = relationship(
        "UserOrganizationMembership",
        foreign_keys="UserOrganizationMembership.organization_id",
        cascade="all, delete-orphan",
        overlaps="organization",  # SAWarning: overlaps con UserOrganizationMembership.organization
    )
    member_users = relationship(
        "User",
        secondary="user_organization_memberships",
        primaryjoin="Organization.id == UserOrganizationMembership.organization_id",
        secondaryjoin="User.id == UserOrganizationMembership.user_id",
        viewonly=True,
    )

    def __repr__(self) -> str:
        return f"<Organization id={self.id!r} name={self.name!r}>"


# ── MFA / 2FA ─────────────────────────────────────────────────────────────────

class MFAConfig(Base):
    """TOTP-based MFA configuration per user."""
    __tablename__ = "mfa_configs"

    id           = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String(36), ForeignKey("organizations.id"), nullable=True, index=True)  # audit #7
    user_id      = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"),
                          nullable=False, unique=True, index=True)
    totp_secret  = Column(String(512), nullable=False)  # Fernet-encrypted base32 secret (v2:<salt>.<token>)
    is_enabled   = Column(Boolean, default=False)       # False until first verification
    verified_at  = Column(DateTime(timezone=True), nullable=True)
    last_used_at = Column(DateTime(timezone=True), nullable=True)
    created_at   = Column(DateTime(timezone=True), server_default=func.now())

    user         = relationship("User", foreign_keys=[user_id])
    backup_codes = relationship("MFABackupCode", back_populates="mfa_config",
                                cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<MFAConfig id={self.id!r} user_id={self.user_id!r}>"


class MFABackupCode(Base):
    """One-time backup codes (8 per user, each usable once)."""
    __tablename__ = "mfa_backup_codes"

    id         = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String(36), ForeignKey("organizations.id"), nullable=True, index=True)  # audit #7
    mfa_id     = Column(String(36), ForeignKey("mfa_configs.id", ondelete="CASCADE"),
                        nullable=False, index=True)
    code_hash  = Column(String(128), nullable=False)    # bcrypt hash of 8-char code
    used_at    = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    mfa_config = relationship("MFAConfig", back_populates="backup_codes")


class WebAuthnCredential(Base):
    """Registered passkey / FIDO2 credential for a user."""
    __tablename__ = "webauthn_credentials"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String(36), ForeignKey("organizations.id"), nullable=True, index=True)  # audit #7
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    credential_id = Column(String(255), nullable=False, unique=True, index=True)
    public_key = Column(Text, nullable=False)  # base64url encoded COSE public key bytes
    sign_count = Column(Integer, nullable=False, default=0)
    transports = Column(Text, nullable=True)  # JSON list
    name = Column(String(100), nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    last_used_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    user = relationship("User", foreign_keys=[user_id])


class MFAChallenge(Base):
    """One-time MFA login challenge used to prevent replay of short-lived JWTs."""
    __tablename__ = "mfa_challenges"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String(36), ForeignKey("organizations.id"), nullable=True, index=True)  # audit #7
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    token_jti = Column(String(36), nullable=False, unique=True, index=True)
    expires_at = Column(DateTime(timezone=True), nullable=False, index=True)
    consumed_at = Column(DateTime(timezone=True), nullable=True, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    user = relationship("User", foreign_keys=[user_id])


# ── Slack / Teams ─────────────────────────────────────────────────────────────

class SlackConfig(Base):
    """Slack or Microsoft Teams workspace integration."""
    __tablename__ = "slack_configs"

    id            = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String(36), ForeignKey("organizations.id"), nullable=True, index=True)  # audit #7
    platform      = Column(String(10), default="slack")  # slack | teams
    workspace_name = Column(String(255), nullable=True)
    bot_token     = Column(Text, nullable=True)          # xoxb-... (stored encrypted)
    webhook_url   = Column(Text, nullable=True)          # incoming webhook fallback
    default_channel = Column(String(100), nullable=True) # #contecflow-alerts
    is_active     = Column(Boolean, default=True)
    # Event subscriptions (JSON list of enabled events)
    subscriptions = Column(Text, default='["task_overdue","budget_alert","ticket_sla"]')
    # Slash command token for verification
    slash_token   = Column(String(255), nullable=True)
    last_ping_at  = Column(DateTime(timezone=True), nullable=True)
    created_at    = Column(DateTime(timezone=True), server_default=func.now())

    notifications = relationship("SlackNotificationLog", back_populates="config",
                                 cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<SlackConfig id={self.id!r} platform={self.platform!r}>"


class SlackNotificationLog(Base):
    """Audit log of every Slack/Teams message sent."""
    __tablename__ = "slack_notification_logs"

    id         = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String(36), ForeignKey("organizations.id"), nullable=True, index=True)  # audit #7
    config_id  = Column(String(36), ForeignKey("slack_configs.id", ondelete="CASCADE"),
                        nullable=False, index=True)
    channel    = Column(String(100), nullable=True)
    event_type = Column(String(50), nullable=True)   # task_overdue | budget_alert | ...
    message    = Column(Text, nullable=True)
    status     = Column(String(20), default="sent")  # sent | failed
    error      = Column(String(500), nullable=True)
    sent_at    = Column(DateTime(timezone=True), server_default=func.now())
    source_id  = Column(String(36), nullable=True)   # task/ticket/project id

    config = relationship("SlackConfig", back_populates="notifications")


# ── Multi-period Budgets ──────────────────────────────────────────────────────

class Budget(Base):
    """Presupuesto de un proyecto (existente o previsto), un departamento o un área.

    Revisión 2026-11: el plan sale de sus partidas (`budget_lines`, por meses);
    el real se calcula (imputaciones y gastos), no se teclea. Versiones: cada
    reprevisión es una fila nueva con `version` + 1 y el mismo `origen_id`.
    """
    __tablename__ = "budgets"

    id          = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String(36), ForeignKey("organizations.id"), nullable=True, index=True)  # audit #7
    name        = Column(String(255), nullable=False)
    year        = Column(Integer, nullable=False, index=True)
    department  = Column(String(100), nullable=True)
    project_id  = Column(String(36), ForeignKey("projects.id"), nullable=True)
    total_amount = Column(Float, nullable=False, default=0)
    currency    = Column(String(3), default=settings.DEFAULT_CURRENCY)
    notes       = Column(Text, nullable=True)
    # Revisión 2026-11
    ambito      = Column(String(20), nullable=False, default="departamento", server_default="departamento")  # proyecto | proyecto_previsto | departamento | area
    area        = Column(String(255), nullable=True)            # área: departamentos separados por comas
    cliente_id  = Column(String(36), ForeignKey("clients.id", ondelete="SET NULL"), nullable=True)
    tipo_proyecto = Column(String(30), nullable=True)
    periodo_desde = Column(Date, nullable=True)                 # primer día del primer mes
    periodo_hasta = Column(Date, nullable=True)                 # primer día del último mes
    version     = Column(Integer, nullable=False, default=1, server_default="1")
    origen_id   = Column(String(36), nullable=True, index=True) # la primera versión de la cadena
    estado      = Column(String(15), nullable=False, default="borrador", server_default="borrador", index=True)  # borrador | enviado | aprobado | rechazado | sustituido
    motivo_rechazo = Column(Text, nullable=True)
    is_approved = Column(Boolean, default=False)
    approved_by = Column(String(36), ForeignKey("users.id"), nullable=True)
    approved_at = Column(DateTime(timezone=True), nullable=True)
    created_by  = Column(String(36), ForeignKey("users.id"), nullable=True)
    created_at  = Column(DateTime(timezone=True), server_default=func.now())
    # Revisión 2026-11 (preparar en profundidad)
    area_id     = Column(String(36), ForeignKey("areas.id", ondelete="SET NULL"), nullable=True, index=True)
    padre_id    = Column(String(36), nullable=True, index=True)   # el presupuesto (origen) que consume: área > departamento > proyecto
    techo       = Column(Float, nullable=True)                   # lo que pueden sumar los presupuestos hijos
    responsable_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    campana_id  = Column(String(36), ForeignKey("budget_campaigns.id", ondelete="SET NULL"), nullable=True, index=True)
    escenario   = Column(String(40), nullable=False, default="base", server_default="base")
    supuestos   = Column(Text, nullable=False, default="{}", server_default="{}")  # {"inflacion_pct": 3, ...}
    # Revisión 2026-11 (seguir a fondo): reprevisión por tipo {"licencias": {"metodo": "plan|ritmo|manual", "meses": {...}}}
    prevision   = Column(Text, nullable=False, default="{}", server_default="{}")

    lines      = relationship("BudgetLine", back_populates="budget", cascade="all, delete-orphan",
                              order_by="BudgetLine.created_at")
    approver   = relationship("User", foreign_keys=[approved_by])
    creator    = relationship("User", foreign_keys=[created_by])
    project    = relationship("Project")


class BudgetLine(Base):
    """Una partida del presupuesto con su reparto por meses (`meses`: {"2026-01": 1000.0, …})."""
    __tablename__ = "budget_lines"

    id          = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=True, index=True)
    budget_id   = Column(String(36), ForeignKey("budgets.id", ondelete="CASCADE"), nullable=False, index=True)
    tipo        = Column(String(30), nullable=False)            # de BUDGET_LINE_TYPES
    descripcion = Column(String(500), nullable=False)
    user_id     = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)  # personal: una persona…
    perfil      = Column(String(120), nullable=True)            # …o un perfil (para un proyecto que aún no tiene equipo)
    horas       = Column(Float, nullable=True)
    coste_hora  = Column(Float, nullable=True)
    importe     = Column(Float, nullable=False, default=0)
    meses       = Column(Text, nullable=False, default="{}")
    created_at  = Column(DateTime(timezone=True), server_default=func.now())
    # Revisión 2026-11 (preparar en profundidad)
    sentido     = Column(String(10), nullable=False, default="gasto", server_default="gasto")   # gasto | ingreso
    naturaleza  = Column(String(10), nullable=False, default="opex", server_default="opex")     # opex | capex
    vida_meses  = Column(Integer, nullable=True)        # capex: meses de amortización
    unidades    = Column(Float, nullable=True)          # conductor: unidades × precio
    precio_unitario = Column(Float, nullable=True)
    recurrencia = Column(String(12), nullable=True)     # unica | mensual | trimestral | anual
    mes_desde   = Column(String(7), nullable=True)      # "YYYY-MM": desde cuándo aplica la partida
    mes_hasta   = Column(String(7), nullable=True)
    dedicacion_pct = Column(Float, nullable=True)       # personal por coste cargado: % de dedicación
    fecha_alta  = Column(Date, nullable=True)           # vacante: cuándo se incorpora
    pais        = Column(String(2), nullable=True)      # vacante: país (cargas sociales)
    salario_anual = Column(Float, nullable=True)        # vacante: bruto anual
    justificacion = Column(Text, nullable=True)

    budget = relationship("Budget", back_populates="lines")
    user   = relationship("User")


class BudgetCampaign(Base):
    """Campaña de presupuestos de un ejercicio, con su fecha límite de envío."""
    __tablename__ = "budget_campaigns"

    id          = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=True, index=True)
    nombre      = Column(String(200), nullable=False)
    year        = Column(Integer, nullable=False)
    fecha_limite = Column(Date, nullable=False)
    abierta     = Column(Boolean, nullable=False, default=True, server_default="1")
    instrucciones = Column(Text, nullable=True)
    created_at  = Column(DateTime(timezone=True), server_default=func.now())


class BudgetCommitment(Base):
    """Pedido comprometido contra un presupuesto (revisión 2026-11).

    Mientras está `comprometido`, cuenta como comprometido (resta del disponible);
    `facturado`, pasa a real en el mes de su factura; `anulado`, no cuenta.
    """
    __tablename__ = "budget_commitments"

    id          = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=True, index=True)
    origen_id   = Column(String(36), nullable=False, index=True)    # la cadena de versiones del presupuesto
    tipo        = Column(String(30), nullable=False)
    descripcion = Column(String(500), nullable=False)
    proveedor   = Column(String(200), nullable=True)
    referencia  = Column(String(100), nullable=True)               # nº de pedido
    importe     = Column(Float, nullable=False)
    mes         = Column(String(7), nullable=False)                # mes previsto del gasto "YYYY-MM"
    estado      = Column(String(12), nullable=False, default="comprometido", server_default="comprometido")
    fecha_factura = Column(Date, nullable=True)
    importe_facturado = Column(Float, nullable=True)
    created_by  = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at  = Column(DateTime(timezone=True), server_default=func.now())


class BudgetClose(Base):
    """Cierre mensual: congela el real del mes (por tipo) de una cadena de presupuestos."""
    __tablename__ = "budget_closes"
    __table_args__ = (UniqueConstraint("origen_id", "mes", name="uq_budget_closes_origen_mes"),)

    id          = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=True, index=True)
    origen_id   = Column(String(36), nullable=False, index=True)
    mes         = Column(String(7), nullable=False)
    real        = Column(Text, nullable=False, default="{}")       # {tipo: importe}
    cerrado_por = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    cerrado_at  = Column(DateTime(timezone=True), server_default=func.now())


class BudgetVarianceNote(Base):
    """Explicación de una desviación de un tipo en un mes."""
    __tablename__ = "budget_variance_notes"
    __table_args__ = (UniqueConstraint("origen_id", "mes", "tipo", name="uq_budget_variance_origen_mes_tipo"),)

    id          = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=True, index=True)
    origen_id   = Column(String(36), nullable=False, index=True)
    mes         = Column(String(7), nullable=False)
    tipo        = Column(String(30), nullable=False)
    explicacion = Column(Text, nullable=False)
    autor_id    = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at  = Column(DateTime(timezone=True), server_default=func.now())


class BudgetTransfer(Base):
    """Traspaso entre partidas (o ampliación, sin origen) de un presupuesto aprobado."""
    __tablename__ = "budget_transfers"

    id          = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=True, index=True)
    budget_id   = Column(String(36), ForeignKey("budgets.id", ondelete="CASCADE"), nullable=False, index=True)
    desde_linea_id = Column(String(36), nullable=True)             # vacío: ampliación
    hacia_linea_id = Column(String(36), nullable=True)             # vacío: partida nueva de `hacia_tipo`
    hacia_tipo  = Column(String(30), nullable=True)
    hacia_descripcion = Column(String(500), nullable=True)
    importe     = Column(Float, nullable=False)
    motivo      = Column(Text, nullable=False)
    estado      = Column(String(12), nullable=False, default="pendiente", server_default="pendiente")
    solicitante_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    decisor_id  = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    decidido_at = Column(DateTime(timezone=True), nullable=True)
    motivo_rechazo = Column(Text, nullable=True)
    created_at  = Column(DateTime(timezone=True), server_default=func.now())


class BudgetTemplate(Base):
    """Plantilla de partidas para empezar un presupuesto (por ámbito y tipo de proyecto)."""
    __tablename__ = "budget_templates"

    id          = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=True, index=True)
    nombre      = Column(String(200), nullable=False)
    ambito      = Column(String(20), nullable=True)
    tipo_proyecto = Column(String(30), nullable=True)
    partidas    = Column(Text, nullable=False, default="[]")   # [{tipo, descripcion, ...campos de partida}]
    created_by  = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at  = Column(DateTime(timezone=True), server_default=func.now())


# ── AI Task Estimation ────────────────────────────────────────────────────────

class AITaskEstimate(Base):
    """AI-generated hour estimate for a task, based on historical similar tasks."""
    __tablename__ = "ai_task_estimates"

    id              = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String(36), ForeignKey("organizations.id"), nullable=True, index=True)  # audit #7
    task_id         = Column(String(36), ForeignKey("tasks.id", ondelete="CASCADE"),
                             nullable=False, index=True)
    estimated_hours = Column(Float, nullable=False)
    confidence_pct  = Column(Float, default=0)      # 0-100
    similar_tasks   = Column(Text, nullable=True)   # JSON: list of similar task ids
    reasoning       = Column(Text, nullable=True)   # AI explanation
    model_used      = Column(String(50), default="rule_based")
    accepted        = Column(Boolean, nullable=True) # PM accepted/rejected
    accepted_at     = Column(DateTime(timezone=True), nullable=True)
    created_at      = Column(DateTime(timezone=True), server_default=func.now())

    task = relationship("Task")


# ── AI Ticket Triage ──────────────────────────────────────────────────────────

class AITicketTriage(Base):
    """AI-suggested triage for a service desk ticket."""
    __tablename__ = "ai_ticket_triages"

    id                   = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String(36), ForeignKey("organizations.id"), nullable=True, index=True)  # audit #7
    ticket_id            = Column(String(36), ForeignKey("sd_tickets.id", ondelete="CASCADE"),
                                  nullable=False, index=True)
    suggested_category   = Column(String(100), nullable=True)
    suggested_priority   = Column(String(20), nullable=True)
    suggested_agent_id   = Column(String(36), ForeignKey("users.id"), nullable=True)
    suggested_kb_article = Column(String(36), nullable=True)
    confidence_pct       = Column(Float, default=0)
    reasoning            = Column(Text, nullable=True)
    accepted             = Column(Boolean, nullable=True)
    accepted_by          = Column(String(36), ForeignKey("users.id"), nullable=True)
    accepted_at          = Column(DateTime(timezone=True), nullable=True)
    created_at           = Column(DateTime(timezone=True), server_default=func.now())

    suggested_agent = relationship("User", foreign_keys=[suggested_agent_id])
    acceptor        = relationship("User", foreign_keys=[accepted_by])


# ── Scenario Planning / What-if ───────────────────────────────────────────────

class ScenarioModel(Base):
    """What-if capacity scenario — simulate impact of new projects."""
    __tablename__ = "scenario_models"

    id          = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String(36), ForeignKey("organizations.id"), nullable=True, index=True)  # audit #7
    name        = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    base_date   = Column(Date, nullable=True)
    horizon_weeks = Column(Integer, default=12)
    status      = Column(String(20), default="draft")  # draft | computed | archived
    created_by  = Column(String(36), ForeignKey("users.id"), nullable=True)
    created_at  = Column(DateTime(timezone=True), server_default=func.now())
    computed_at = Column(DateTime(timezone=True), nullable=True)
    # Computed results stored as JSON
    results     = Column(Text, nullable=True)   # JSON: capacity gaps, overload weeks

    creator  = relationship("User", foreign_keys=[created_by])
    projects = relationship("ScenarioProject", back_populates="scenario",
                            cascade="all, delete-orphan")


class ScenarioProject(Base):
    """Simulated project inside a what-if scenario."""
    __tablename__ = "scenario_projects"

    id            = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String(36), ForeignKey("organizations.id"), nullable=True, index=True)  # audit #7
    scenario_id   = Column(String(36), ForeignKey("scenario_models.id", ondelete="CASCADE"),
                           nullable=False, index=True)
    # Either link to existing project OR define a hypothetical one
    project_id    = Column(String(36), ForeignKey("projects.id"), nullable=True)
    name          = Column(String(255), nullable=False)
    start_date    = Column(Date, nullable=True)
    end_date      = Column(Date, nullable=True)
    total_hours   = Column(Float, default=0)
    # Required skill breakdown (JSON: {skill_name: hours})
    skill_demand  = Column(Text, nullable=True)
    is_existing   = Column(Boolean, default=False)  # True = real project, False = hypothetical

    scenario = relationship("ScenarioModel", back_populates="projects")
    project  = relationship("Project")


# ── PDF Export Jobs ───────────────────────────────────────────────────────────

class PDFExportJob(Base):
    """Queued/completed PDF export request."""
    __tablename__ = "pdf_export_jobs"

    id          = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String(36), ForeignKey("organizations.id"), nullable=True, index=True)  # audit #7
    export_type = Column(String(50), nullable=False)  # report | invoice | project_summary
    source_id   = Column(String(36), nullable=True)   # report_id / invoice_id / project_id
    status      = Column(String(20), default="queued")  # queued | generating | ready | failed
    file_path   = Column(String(500), nullable=True)  # server path when ready
    file_size   = Column(Integer, nullable=True)
    params      = Column(Text, nullable=True)         # JSON: filters, date range, etc.
    error       = Column(String(500), nullable=True)
    requested_by = Column(String(36), ForeignKey("users.id"), nullable=True)
    created_at  = Column(DateTime(timezone=True), server_default=func.now())
    completed_at = Column(DateTime(timezone=True), nullable=True)

    requester = relationship("User", foreign_keys=[requested_by])


# ── BI Connector Tokens ───────────────────────────────────────────────────────

class BIToken(Base):
    """Access token for BI tools (Power BI, Tableau, Metabase)."""
    __tablename__ = "bi_tokens"

    id          = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String(36), ForeignKey("organizations.id"), nullable=True, index=True)  # audit #7
    name        = Column(String(255), nullable=False)
    tool        = Column(String(30), default="powerbi")  # powerbi | tableau | metabase | generic
    token_hash  = Column(String(128), nullable=False)    # bcrypt
    token_prefix = Column(String(16), nullable=True)     # bi_xxxxx
    scopes      = Column(Text, default='["read"]')       # JSON
    is_active   = Column(Boolean, default=True)
    expires_at  = Column(DateTime(timezone=True), nullable=True)
    last_used_at = Column(DateTime(timezone=True), nullable=True)
    requests_today = Column(Integer, default=0)
    created_by  = Column(String(36), ForeignKey("users.id"), nullable=True)
    created_at  = Column(DateTime(timezone=True), server_default=func.now())

    creator = relationship("User", foreign_keys=[created_by])
