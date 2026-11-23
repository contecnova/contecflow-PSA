"""
Clients — Empresas/organizaciones cliente
Entidad central que vincula proyectos, oportunidades y portal de acceso externo.
"""
import uuid
import enum
from sqlalchemy import Column, String, Boolean, DateTime, Text, ForeignKey, Enum, Integer, Float
from app.models.money import Money
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
    """Empresa/organización cliente: entidad central que agrupa proyectos y contactos."""
    __tablename__ = "clients"

    id          = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=True, index=True)  # audit #7
    name        = Column(String(255), nullable=False, index=True)
    short_name  = Column(String(50),  nullable=True)   # Alias / nombre corto
    tax_id      = Column(String(50),  nullable=True)   # CIF / NIF / VAT
    industry    = Column(String(50), default=ClientIndustry.other.value)  # clave de `custom_client_industries` (19-11-2026)
    status      = Column(Enum(ClientStatus),   default=ClientStatus.active)

    # Datos propios de la empresa (18-11-2026): centralita y email general.
    # No son los del contacto principal (esos, abajo).
    phone       = Column(String(50),  nullable=True)
    email       = Column(String(200), nullable=True)

    # Contacto principal: REFLEJO de solo lectura del contacto `is_primary`
    # (`client_service._reflejar_en_cliente`); la fuente es el contacto.
    contact_name  = Column(String(200), nullable=True)
    contact_email = Column(String(200), nullable=True)
    contact_phone = Column(String(50),  nullable=True)
    contact_role  = Column(String(100), nullable=True)  # Cargo del contacto

    # Zona horaria del cliente (auditoría 2026-08, hallazgo 14). Decide los
    # cortes de periodo de SU facturación e informes: el cierre de agosto de un
    # cliente es agosto en su zona, no en la del servidor ni en la de la sede.
    # NULL → se hereda la de la organización. Ver app/core/timeutil.py.
    timezone    = Column(String(50),  nullable=True)   # p. ej. 'Europe/Madrid'

    # Empresa
    website     = Column(String(500), nullable=True)
    address     = Column(Text,        nullable=True)
    city        = Column(String(100), nullable=True)
    country     = Column(String(3),   default=settings.DEFAULT_COUNTRY)  # 19-11-2026: en el alta, el país de la empresa (por_empresa)

    # Relación interna
    account_manager_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)

    # Económico
    billing_address = Column(Text,        nullable=True)
    payment_terms   = Column(String(100), nullable=True)  # "30 días", "inmediato"
    credit_limit    = Column(Money,       nullable=True)
    currency        = Column(String(3),   default=settings.DEFAULT_CURRENCY)
    sla_policy_id   = Column(String(36), ForeignKey("sd_sla_policies.id", ondelete="SET NULL"), nullable=True, index=True)

    # Clientes internos (rev. 193, docs/CLIENTES_INTERNOS.md): un solo modelo
    # con `kind`. Interno = departamento, unidad de negocio, filial o centro de
    # coste de la propia compañía; no se le factura (salvo intercompañía): se
    # le informa (showback) o se le carga (chargeback) lo que cuesta.
    kind          = Column(String(10), nullable=False, default="externo", server_default="externo", index=True)
    internal_type = Column(String(20), nullable=True)   # departamento | unidad_negocio | filial | centro_coste
    department_id = Column(String(36), ForeignKey("departments.id", ondelete="SET NULL"), nullable=True, index=True)
    area_id       = Column(String(36), ForeignKey("areas.id", ondelete="SET NULL"), nullable=True, index=True)
    cost_center_id = Column(String(36), ForeignKey("alm_cost_centers.id", ondelete="SET NULL"), nullable=True, index=True)
    group_organization_id = Column(String(36), ForeignKey("organizations.id", ondelete="SET NULL"), nullable=True)  # empresa del grupo (intercompañía)
    business_owner_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    finance_mode  = Column(String(15), nullable=True)   # showback | chargeback | intercompania
    cost_method   = Column(String(20), nullable=True)   # horas_coste | tarifa_interna | precio_cerrado | catalogo
    internal_rate_table_id = Column(String(36), ForeignKey("rate_tables.id", ondelete="SET NULL"), nullable=True)
    transfer_markup_pct = Column(Float, nullable=True)  # intercompañía: margen del precio de transferencia
    erp_account   = Column(String(40), nullable=True)   # cuenta / centro del asiento en el ERP

    notes      = Column(Text,    nullable=True)
    is_active  = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    created_by = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)

    account_manager = relationship("User", foreign_keys=[account_manager_id])
    business_owner  = relationship("User", foreign_keys=[business_owner_id])  # TODO #56: inverse en User (user.py)
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
    sla_policy      = relationship("SLAPolicy", foreign_keys=[sla_policy_id])  # TODO #56: inverse en SLAPolicy (service_desk/*)

    def __repr__(self) -> str:
        return f"<Client id={self.id!r} name={self.name!r}>"


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
    organization_id = Column(String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=True, index=True)  # audit #7
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
    # Usuario del portal que es esta persona (18-11-2026): cada usuario del
    # portal de un cliente existe también como contacto suyo.
    portal_user_id = Column(String(36), ForeignKey("client_users.id", ondelete="SET NULL"),
                            nullable=True, index=True)
    # Desde cuándo está desactivado: de ahí cuenta su retención (`bloqueo_legal.TIPOS`).
    deactivated_at = Column(DateTime(timezone=True), nullable=True)

    client = relationship("Client", back_populates="contacts")

    def __repr__(self) -> str:
        return f"<ClientContact id={self.id!r} full_name={self.full_name!r}>"


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
    organization_id = Column(String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=True, index=True)  # audit #7
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

    # Idioma por defecto del portal de este cliente. Incidencia 5 (23-11-2026):
    # vacío = sin elegir (el de la empresa proveedora, el del navegador o inglés);
    # antes se rellenaba con el `DEFAULT_LANGUAGE` del entorno (castellano).
    default_language    = Column(String(10), nullable=True)

    # Qué puede editar el cliente desde su perfil
    allow_profile_edit  = Column(Boolean, default=True)   # puede editar nombre, tel, idioma
    allow_pwd_change    = Column(Boolean, default=True)   # puede cambiar su contraseña

    # Límites
    max_portal_users    = Column(Integer, default=10)
    max_open_tickets    = Column(Integer, nullable=True)  # None = sin límite

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    client = relationship("Client", back_populates="portal_config", uselist=False)

    def __repr__(self) -> str:
        return f"<ClientPortalConfig id={self.id!r}>"


class ClientLicenseLink(Base):
    """Vincula una licencia ALM a un cliente."""
    __tablename__ = "client_license_links"

    id         = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=True, index=True)  # audit #7
    client_id  = Column(String(36), ForeignKey("clients.id", ondelete="CASCADE"), nullable=False, index=True)
    license_id = Column(String(36), ForeignKey("alm_licenses.id", ondelete="CASCADE"), nullable=False, index=True)
    is_active  = Column(Boolean, default=True)
    notes      = Column(Text, nullable=True)
    linked_at  = Column(DateTime(timezone=True), server_default=func.now())

    client  = relationship("Client", back_populates="license_links")

    def __repr__(self) -> str:
        return f"<ClientLicenseLink id={self.id!r}>"


class ClientContractLink(Base):
    """Vincula un contrato (pipeline) a un cliente de la entidad Client."""
    __tablename__ = "client_contract_links"

    id          = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=True, index=True)  # audit #7
    client_id   = Column(String(36), ForeignKey("clients.id", ondelete="CASCADE"), nullable=False, index=True)
    contract_id = Column(String(36), ForeignKey("contracts.id", ondelete="CASCADE"), nullable=False, index=True)
    is_active   = Column(Boolean, default=True)
    linked_at   = Column(DateTime(timezone=True), server_default=func.now())

    client   = relationship("Client", back_populates="contract_links")

    def __repr__(self) -> str:
        return f"<ClientContractLink id={self.id!r}>"
