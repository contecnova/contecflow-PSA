"""
Clients — Empresas/organizaciones cliente
Entidad central que vincula proyectos, oportunidades y portal de acceso externo.
"""
import uuid
import enum
from sqlalchemy import Column, String, Float, Boolean, DateTime, Text, ForeignKey, Enum, Integer
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.db.base import Base
from app.core.config import settings


class ClientStatus(str, enum.Enum):
    prospect  = "prospect"   # En fase de captación
    active    = "active"     # Cliente activo con proyectos
    inactive  = "inactive"   # Sin actividad reciente
    churned   = "churned"    # Perdido


class ClientIndustry(str, enum.Enum):
    technology    = "technology"
    finance       = "finance"
    healthcare    = "healthcare"
    retail        = "retail"
    manufacturing = "manufacturing"
    education     = "education"
    consulting    = "consulting"
    real_estate   = "real_estate"
    media         = "media"
    other         = "other"


class Client(Base):
    __tablename__ = "clients"

    id          = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String(36), ForeignKey("organizations.id"), nullable=True, index=True)  # audit #7
    name        = Column(String(255), nullable=False, index=True)
    short_name  = Column(String(50),  nullable=True)   # Alias / nombre corto
    tax_id      = Column(String(50),  nullable=True)   # CIF / NIF / VAT
    industry    = Column(Enum(ClientIndustry), default=ClientIndustry.other)
    status      = Column(Enum(ClientStatus),   default=ClientStatus.active)

    # Contacto principal
    contact_name  = Column(String(200), nullable=True)
    contact_email = Column(String(200), nullable=True)
    contact_phone = Column(String(50),  nullable=True)
    contact_role  = Column(String(100), nullable=True)  # Cargo del contacto

    # Empresa
    website     = Column(String(500), nullable=True)
    address     = Column(Text,        nullable=True)
    city        = Column(String(100), nullable=True)
    country     = Column(String(3),   default="ES")

    # Relación interna
    account_manager_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    # Económico
    billing_address = Column(Text,        nullable=True)
    payment_terms   = Column(String(100), nullable=True)  # "30 días", "inmediato"
    credit_limit    = Column(Float,       nullable=True)
    currency        = Column(String(3),   default=settings.DEFAULT_CURRENCY)
    sla_policy_id   = Column(String(36), ForeignKey("sd_sla_policies.id"), nullable=True)

    notes      = Column(Text,    nullable=True)
    is_active  = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    created_by = Column(String(36), ForeignKey("users.id"), nullable=True)

    account_manager = relationship("User", foreign_keys=[account_manager_id])
    projects        = relationship("Project", back_populates="client",
                                   foreign_keys="Project.client_id")
    contacts        = relationship("ClientContact", back_populates="client",
                                   cascade="all, delete-orphan", order_by="ClientContact.is_primary.desc()")
    portal_config   = relationship("ClientPortalConfig", back_populates="client",
                                   uselist=False, cascade="all, delete-orphan")
    license_links   = relationship("ClientLicenseLink", back_populates="client",
                                   cascade="all, delete-orphan")
    contract_links  = relationship("ClientContractLink", back_populates="client",
                                   cascade="all, delete-orphan")
    sla_policy      = relationship("SLAPolicy", foreign_keys=[sla_policy_id])


class ClientContactRole(str, enum.Enum):
    primary      = "primary"       # Contacto principal
    billing      = "billing"       # Facturación
    technical    = "technical"     # Contacto técnico
    executive    = "executive"     # Ejecutivo / sponsor
    support      = "support"       # Contacto de soporte
    other        = "other"


class ClientContact(Base):
    """Múltiples contactos por cliente, cada uno con su rol."""
    __tablename__ = "client_contacts"

    id         = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String(36), ForeignKey("organizations.id"), nullable=True, index=True)  # audit #7
    client_id  = Column(String(36), ForeignKey("clients.id", ondelete="CASCADE"), nullable=False, index=True)

    full_name  = Column(String(255), nullable=False)
    email      = Column(String(255), nullable=True)
    phone      = Column(String(50),  nullable=True)
    job_title  = Column(String(150), nullable=True)
    role       = Column(Enum(ClientContactRole), default=ClientContactRole.other)
    is_primary = Column(Boolean, default=False)
    notes      = Column(Text, nullable=True)
    is_active  = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    client = relationship("Client", back_populates="contacts")


class ClientServiceAccess(str, enum.Enum):
    """Qué módulos puede ver / usar el cliente en el portal."""
    service_desk  = "service_desk"
    projects      = "projects"
    documents     = "documents"
    invoices      = "invoices"
    reports       = "reports"
    knowledge_base = "knowledge_base"


class ClientPortalConfig(Base):
    """Configuración del portal por cliente: permisos, branding, accesos."""
    __tablename__ = "client_portal_configs"

    id         = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String(36), ForeignKey("organizations.id"), nullable=True, index=True)  # audit #7
    client_id  = Column(String(36), ForeignKey("clients.id", ondelete="CASCADE"), nullable=False, unique=True)

    # Accesos habilitados (JSON list de ClientServiceAccess)
    enabled_modules = Column(Text, default='["service_desk","projects","documents"]')

    # Acceso al service desk sin proyecto vinculado
    sd_without_project = Column(Boolean, default=True)

    # SLA tier para este cliente
    sla_tier    = Column(String(50), nullable=True)  # gold, silver, bronze, enterprise

    # Branding
    logo_url    = Column(String(500), nullable=True)
    accent_color = Column(String(10), nullable=True)  # hex

    # Idioma por defecto para nuevos usuarios del portal
    default_language    = Column(String(10), default=settings.DEFAULT_LANGUAGE)

    # Qué puede editar el cliente desde su perfil
    allow_profile_edit  = Column(Boolean, default=True)   # puede editar nombre, tel, idioma
    allow_pwd_change    = Column(Boolean, default=True)   # puede cambiar su contraseña

    # Límites
    max_portal_users    = Column(Integer, default=10)
    max_open_tickets    = Column(Integer, nullable=True)  # None = sin límite

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    client = relationship("Client", back_populates="portal_config", uselist=False)


class ClientLicenseLink(Base):
    """Vincula una licencia ALM a un cliente."""
    __tablename__ = "client_license_links"

    id         = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String(36), ForeignKey("organizations.id"), nullable=True, index=True)  # audit #7
    client_id  = Column(String(36), ForeignKey("clients.id", ondelete="CASCADE"), nullable=False, index=True)
    license_id = Column(String(36), ForeignKey("alm_licenses.id", ondelete="CASCADE"), nullable=False, index=True)
    is_active  = Column(Boolean, default=True)
    notes      = Column(Text, nullable=True)
    linked_at  = Column(DateTime(timezone=True), server_default=func.now())

    client  = relationship("Client", back_populates="license_links")


class ClientContractLink(Base):
    """Vincula un contrato (pipeline) a un cliente de la entidad Client."""
    __tablename__ = "client_contract_links"

    id          = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String(36), ForeignKey("organizations.id"), nullable=True, index=True)  # audit #7
    client_id   = Column(String(36), ForeignKey("clients.id", ondelete="CASCADE"), nullable=False, index=True)
    contract_id = Column(String(36), ForeignKey("contracts.id", ondelete="CASCADE"), nullable=False, index=True)
    is_active   = Column(Boolean, default=True)
    linked_at   = Column(DateTime(timezone=True), server_default=func.now())

    client   = relationship("Client", back_populates="contract_links")
