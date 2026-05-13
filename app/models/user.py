from sqlalchemy import Column, String, Boolean, Float, DateTime, Enum, Text, ForeignKey, UniqueConstraint
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import enum
import uuid
from app.db.base import Base
from app.core.config import settings


class UserRole(str, enum.Enum):
    admin = "admin"             # Dirección — ve todo incluyendo costes
    pm = "pm"                   # Project Manager — ve sus proyectos
    team_lead = "team_lead"     # Responsable de equipo
    hr = "hr"                   # RRHH — cargas y disponibilidad
    employee = "employee"       # Solo sus tareas e imputaciones
    subcontractor = "subcontractor"  # Persona de empresa subcontratada (recurso externo)


class UserStatus(str, enum.Enum):
    active = "active"
    inactive = "inactive"
    vacation = "vacation"
    leave = "leave"


class UserOrganizationMembership(Base):
    __tablename__ = "user_organization_memberships"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    organization_id = Column(String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        UniqueConstraint("user_id", "organization_id", name="uq_user_org_membership"),
    )

    user = relationship("User", foreign_keys=[user_id])
    organization = relationship("Organization", foreign_keys=[organization_id])


class User(Base):
    __tablename__ = "users"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    username = Column(String(100), unique=True, nullable=False, index=True)
    email = Column(String(255), unique=True, nullable=False, index=True)
    hashed_password = Column(String(255), nullable=True)  # Null if LDAP-only

    # Profile
    full_name = Column(String(255), nullable=False)
    first_name = Column(String(100))
    last_name = Column(String(100))
    department = Column(String(100), index=True)
    # Sub-equipo dentro del departamento (p.ej. dept=Engineering, team=Frontend).
    # Usado por evaluaciones 360° para acotar el pool de "peers".
    team = Column(String(120), nullable=True, index=True)
    job_title = Column(String(150))
    avatar_url = Column(String(500))
    phone = Column(String(50))

    # Role and status
    role = Column(String(100), default="employee", nullable=False, index=True)
    status = Column(Enum(UserStatus), default=UserStatus.active, nullable=False, index=True)

    # Capacity and cost (confidential — visible only to admin/hr)
    weekly_capacity_hours = Column(Float, default=settings.DEFAULT_WEEKLY_CAPACITY_HOURS)   # Standard working hours/week
    hourly_rate = Column(Float, nullable=True)             # Internal cost €/hour
    currency = Column(String(3), default=settings.DEFAULT_CURRENCY)

    # LDAP info
    ldap_dn = Column(String(500), nullable=True)
    ldap_synced_at = Column(DateTime(timezone=True), nullable=True)

    # Auth
    is_active = Column(Boolean, default=True)
    is_superadmin = Column(Boolean, default=False)
    last_login = Column(DateTime(timezone=True), nullable=True)

    # Timezone per-user (overrides org default)
    timezone = Column(String(50), nullable=True)  # e.g. 'Europe/Madrid', 'America/New_York'

    # Multi-tenancy (v15)
    organization_id = Column(String(36), ForeignKey("organizations.id", ondelete="SET NULL"), nullable=True, index=True)
    manager_id      = Column(String(36), ForeignKey("users.id",         ondelete="SET NULL"), nullable=True, index=True)

    # Timestamps
    sso_provider = Column(String(30), nullable=True)   # azure_ad | okta | google | saml
    sso_subject  = Column(String(255), nullable=True)  # sub claim del token OIDC
    mfa_enabled  = Column(Boolean, default=False)
    mfa_secret   = Column(String(512), nullable=True)  # Fernet-encrypted TOTP secret
    scim_external_id = Column(String(255), nullable=True, index=True)
    scim_last_synced_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    organization = relationship('Organization', back_populates='users', foreign_keys='User.organization_id')
    organization_memberships = relationship(
        "UserOrganizationMembership",
        foreign_keys="UserOrganizationMembership.user_id",
        cascade="all, delete-orphan",
    )
    organizations = relationship(
        "Organization",
        secondary="user_organization_memberships",
        primaryjoin="User.id == UserOrganizationMembership.user_id",
        secondaryjoin="Organization.id == UserOrganizationMembership.organization_id",
        viewonly=True,
    )
    managed_projects = relationship("Project", back_populates="project_manager", foreign_keys="Project.pm_id")
    @property
    def manager_name(self):
        return self.manager.full_name if self.manager else None

    manager          = relationship("User", remote_side="User.id", foreign_keys="User.manager_id", back_populates="direct_reports")
    direct_reports   = relationship("User", foreign_keys="User.manager_id", back_populates="manager")
    task_assignments = relationship("Task", back_populates="assignee", foreign_keys="Task.assignee_id")
    imputations = relationship("Imputation", back_populates="user", foreign_keys="Imputation.user_id")
    alerts = relationship("Alert", back_populates="user", foreign_keys="Alert.user_id")

    @property
    def organization_ids(self):
        ids = set()
        if self.organization_id:
            ids.add(str(self.organization_id))
        for m in self.organization_memberships or []:
            if m.organization_id:
                ids.add(str(m.organization_id))
        return sorted(ids)

    @property
    def organizations_summary(self):
        return [
            {"id": str(o.id), "name": o.name, "slug": o.slug}
            for o in (self.organizations or [])
        ]

    def belongs_to_organization(self, org_id: str) -> bool:
        if not org_id:
            return False
        if str(self.organization_id) == str(org_id):
            return True
        return any(str(m.organization_id) == str(org_id) for m in (self.organization_memberships or []))

    def __repr__(self):
        return f"<User {self.username} ({self.role})>"

class UserPreference(Base):
    """Preferencias de UI persistentes por usuario."""
    __tablename__ = "user_preferences"

    id          = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String(36), ForeignKey("organizations.id"), nullable=True, index=True)  # audit #7
    user_id     = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"),
                         nullable=False, unique=True, index=True)
    # Dashboard configurable
    dashboard_widgets  = Column(Text, nullable=True)   # JSON: lista ordenada de widgets con size/visible
    # Theming
    accent_color       = Column(String(20), default="#4f8ef7")  # CSS hex
    theme_mode         = Column(String(10), default="freight")  # freight | dark | light | system
    sidebar_collapsed  = Column(Boolean, default=False)
    # Idioma
    language           = Column(String(10), default=settings.DEFAULT_LANGUAGE)
    # Densidad UI
    ui_density         = Column(String(10), default="normal")   # compact | normal | comfortable
    # Otros
    extra              = Column(Text, nullable=True)            # JSON libre para futuras prefs

    created_at  = Column(DateTime(timezone=True), server_default=func.now())
    updated_at  = Column(DateTime(timezone=True), onupdate=func.now())

    user = relationship("User", foreign_keys=[user_id])

