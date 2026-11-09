from sqlalchemy import Column, String, Boolean, Text, DateTime, Integer, Date, ForeignKey, UniqueConstraint, Index
from sqlalchemy.sql import func
import uuid
from app.db.base import Base


class AppSetting(Base):
    """Key-value settings store.

    Rows with ``organization_id=NULL`` are global/system-level defaults.
    Rows with a non-NULL ``organization_id`` are tenant-specific overrides
    (e.g. per-tenant Jira URL, M365 tenant ID).
    Queries for a tenant return *both* global and tenant-specific rows so
    callers can prefer the tenant value and fall back to the global default.
    The composite unique index on (key, organization_id) enforces uniqueness.
    """
    __tablename__ = "app_settings"
    # Flag consumed by TenantSession: include global (org_id IS NULL) rows
    # alongside tenant-specific ones instead of strict == filtering.
    _tenant_filter_include_global = True

    id              = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String(36), ForeignKey("organizations.id", ondelete="CASCADE"),
                             nullable=True, index=True)
    key             = Column(String(100), nullable=False, index=True)
    value           = Column(Text, nullable=True)
    description     = Column(String(255), nullable=True)
    updated_at      = Column(DateTime(timezone=True), onupdate=func.now(), server_default=func.now())

    __table_args__ = (
        UniqueConstraint("key", "organization_id", name="uq_app_settings_key_org"),
    )


class CustomProjectType(Base):
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

    __tablename__ = "custom_project_types"
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String(36), ForeignKey("organizations.id"), nullable=True, index=True)  # audit #7
    value = Column(String(50), nullable=False)
    label = Column(String(100), nullable=False)
    color = Column(String(20), default="#7a8aaa")
    is_active = Column(Boolean, default=True)
    sort_order = Column(Integer, default=0)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class CustomProjectStatus(Base):
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

    __tablename__ = "custom_project_statuses"
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String(36), ForeignKey("organizations.id"), nullable=True, index=True)  # audit #7
    value = Column(String(50), nullable=False)
    label = Column(String(100), nullable=False)
    color = Column(String(20), default="#7a8aaa")
    is_active = Column(Boolean, default=True)
    is_default = Column(Boolean, default=False)
    sort_order = Column(Integer, default=0)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class CustomTaskStatus(Base):
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

    __tablename__ = "custom_task_statuses"
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String(36), ForeignKey("organizations.id"), nullable=True, index=True)  # audit #7
    value = Column(String(50), nullable=False)
    label = Column(String(100), nullable=False)
    color = Column(String(20), default="#7a8aaa")
    is_active = Column(Boolean, default=True)
    is_default = Column(Boolean, default=False)
    sort_order = Column(Integer, default=0)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class Area(Base):
    """Un área agrupa departamentos (revisión 2026-11): la base de su presupuesto."""
    __tablename__ = "areas"
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String(36), ForeignKey("organizations.id"), nullable=True, index=True)
    name = Column(String(120), nullable=False)
    description = Column(String(255), nullable=True)
    manager_id = Column(String(36), ForeignKey("users.id"), nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class Department(Base):
    __tablename__ = "departments"
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String(36), ForeignKey("organizations.id"), nullable=True, index=True)  # audit #7
    area_id = Column(String(36), ForeignKey("areas.id", ondelete="SET NULL"), nullable=True, index=True)
    name = Column(String(100), nullable=False)
    description = Column(String(255), nullable=True)
    manager_id = Column(String(36), ForeignKey("users.id"), nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class Holiday(Base):
    __tablename__ = "holidays"
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String(36), ForeignKey("organizations.id"), nullable=True, index=True)  # audit #7
    name = Column(String(100), nullable=False)
    date = Column(Date, nullable=False)
    type = Column(String(20), default="public")
    applies_to = Column(String(50), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class SettingsAuditLog(Base):
    """Append-only audit trail for every settings & integration-credential change.

    Critical for compliance and incident forensics: when a runtime flag or
    encrypted credential is modified via the UI we want to know **who** did it,
    **when**, **from where** and **what changed**. Secret values are NEVER
    stored — only a SHA-256 hash of (old, new) so admins can verify after a
    breach that "the value was/wasn't X" without exposing the secret here.
    """
    __tablename__ = "settings_audit_log"
    _tenant_filter_include_global = True

    id              = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    # Microsecond-precise Python default; server_default would round to seconds
    # in SQLite and break ordering for tests / fast successive writes.
    created_at      = Column(
        DateTime(timezone=True),
        default=lambda: __import__("datetime").datetime.now(__import__("datetime").timezone.utc),
        server_default=func.now(),
        index=True,
    )
    actor_id        = Column(String(36), nullable=True, index=True)
    actor_ip        = Column(String(64), nullable=True)
    actor_ua        = Column(String(255), nullable=True)
    organization_id = Column(String(36), ForeignKey("organizations.id", ondelete="SET NULL"), nullable=True, index=True)
    scope           = Column(String(20), nullable=False, index=True)   # runtime | integration
    provider        = Column(String(40), nullable=True, index=True)    # filled for scope=integration
    key             = Column(String(80), nullable=False, index=True)
    action          = Column(String(16), nullable=False)               # set | clear
    is_secret       = Column(Boolean, default=False, nullable=False)
    old_value       = Column(Text, nullable=True)   # plaintext for non-secret; NULL for secret
    new_value       = Column(Text, nullable=True)   # plaintext for non-secret; NULL for secret
    old_value_hash  = Column(String(64), nullable=True)
    new_value_hash  = Column(String(64), nullable=True)

    __table_args__ = (
        Index("ix_settings_audit_scope_key", "scope", "key"),
        Index("ix_settings_audit_created_at_desc", "created_at"),
    )


class IntegrationCredential(Base):
    """Encrypted per-organization integration credentials.

    One row per (organization_id, provider, key). Non-secret fields (e.g. an
    SMTP host or AWS region) are stored as plaintext in ``value``. Secret
    fields (passwords, tokens, signing secrets) go into ``value_encrypted``
    after being wrapped by :func:`app.core.encryption.encrypt_value`.

    Use the registry in :mod:`app.services.integration_credentials_service` to
    drive which provider exposes which keys and whether they're secret.
    """
    __tablename__ = "integration_credentials"

    id              = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=True, index=True)
    provider        = Column(String(40), nullable=False, index=True)
    key             = Column(String(80), nullable=False)
    value           = Column(Text, nullable=True)
    value_encrypted = Column(Text, nullable=True)
    is_secret       = Column(Boolean, default=False, nullable=False)
    updated_at      = Column(DateTime(timezone=True), onupdate=func.now(), server_default=func.now())
    updated_by      = Column(String(36), nullable=True)

    __table_args__ = (
        UniqueConstraint("organization_id", "provider", "key", name="uq_integration_credential"),
        Index("ix_integration_credential_provider", "provider"),
    )
