"""
Asset & License Management (ALM) — Enterprise Grade
Gestión de proveedores, contratos, licencias, activos y suscripciones.
"""
import uuid
import enum
from sqlalchemy import (Column, String, Float, Integer, Boolean, Date,
                        DateTime, Text, ForeignKey, Enum, UniqueConstraint)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.db.base import Base
from app.core.config import settings


# ── Enums ──────────────────────────────────────────────────────────────────────

class VendorCategory(str, enum.Enum):
    software   = "software"
    hardware   = "hardware"
    saas       = "saas"
    cloud      = "cloud"
    telecom    = "telecom"
    consulting = "consulting"
    other      = "other"

class ALMContractType(str, enum.Enum):
    purchase     = "purchase"
    subscription = "subscription"
    maintenance  = "maintenance"
    support      = "support"
    lease        = "lease"
    enterprise   = "enterprise"

class ALMContractStatus(str, enum.Enum):
    active    = "active"
    expired   = "expired"
    cancelled = "cancelled"
    pending   = "pending"
    draft     = "draft"

class BillingCycle(str, enum.Enum):
    one_time   = "one_time"
    monthly    = "monthly"
    quarterly  = "quarterly"
    annual     = "annual"
    biennial   = "biennial"

class LicenseType(str, enum.Enum):
    perpetual    = "perpetual"
    subscription = "subscription"
    concurrent   = "concurrent"
    named        = "named"
    device       = "device"
    trial        = "trial"
    free         = "free"
    oem          = "oem"
    volume       = "volume"

class LicenseStatus(str, enum.Enum):
    active         = "active"
    expired        = "expired"
    unassigned     = "unassigned"
    overallocated  = "overallocated"
    cancelled      = "cancelled"

class LicensePlatform(str, enum.Enum):
    windows = "windows"
    mac     = "mac"
    linux   = "linux"
    web     = "web"
    mobile  = "mobile"
    any     = "any"

class AssetType(str, enum.Enum):
    laptop     = "laptop"
    desktop    = "desktop"
    server     = "server"
    mobile     = "mobile"
    tablet     = "tablet"
    network    = "network"
    printer    = "printer"
    monitor    = "monitor"
    peripheral = "peripheral"
    vm         = "vm"
    other      = "other"

class ALMAssetStatus(str, enum.Enum):
    in_use    = "in_use"
    available = "available"
    in_repair = "in_repair"
    retired   = "retired"
    lost      = "lost"
    stolen    = "stolen"

class AssetCondition(str, enum.Enum):
    new  = "new"
    good = "good"
    fair = "fair"
    poor = "poor"


# ── Modelos ────────────────────────────────────────────────────────────────────

class ALMCostCenter(Base):
    """Centro de coste para asignación de gastos de licencias/activos."""
    __tablename__ = "alm_cost_centers"

    id             = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String(36), ForeignKey("organizations.id"), nullable=True, index=True)  # audit #7
    code           = Column(String(20), nullable=False)  # CC-001 (unique per-tenant — ver __table_args__)
    name           = Column(String(200), nullable=False)
    description    = Column(Text, nullable=True)
    department_id  = Column(String(36), ForeignKey("departments.id", ondelete="SET NULL"), nullable=True)
    manager_id     = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    budget_annual  = Column(Float, nullable=True)   # € presupuesto anual
    currency       = Column(String(3), default=settings.DEFAULT_CURRENCY)
    is_active      = Column(Boolean, default=True)
    created_at     = Column(DateTime(timezone=True), server_default=func.now())

    # audit #38: unique per-tenant
    __table_args__ = (
        UniqueConstraint("organization_id", "code", name="uq_alm_cost_center_code_per_org"),
    )

    manager   = relationship("User",       foreign_keys=[manager_id])
    contracts = relationship("ALMContract", back_populates="cost_center")
    licenses  = relationship("ALMLicense",  back_populates="cost_center")


class ALMVendor(Base):
    """Proveedor de software, hardware, SaaS o servicios."""
    __tablename__ = "alm_vendors"

    id               = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String(36), ForeignKey("organizations.id"), nullable=True, index=True)  # audit #7
    name             = Column(String(200), nullable=False)
    category         = Column(Enum(VendorCategory), default=VendorCategory.software)
    website          = Column(String(500), nullable=True)
    support_email    = Column(String(200), nullable=True)
    support_phone    = Column(String(50),  nullable=True)
    support_url      = Column(String(500), nullable=True)
    account_manager  = Column(String(200), nullable=True)   # Nombre del Account Manager
    account_number   = Column(String(100), nullable=True)   # Nº cliente en el proveedor
    tax_id           = Column(String(50),  nullable=True)   # CIF/NIF del proveedor
    address          = Column(Text, nullable=True)
    country          = Column(String(3),   default="ES")
    notes            = Column(Text, nullable=True)
    is_active        = Column(Boolean, default=True)
    created_at       = Column(DateTime(timezone=True), server_default=func.now())
    updated_at       = Column(DateTime(timezone=True), onupdate=func.now())

    contracts = relationship("ALMContract", back_populates="vendor")
    licenses  = relationship("ALMLicense",  back_populates="vendor")
    assets    = relationship("ALMAsset",    back_populates="vendor")


class ALMContract(Base):
    """Contrato con un proveedor (compra, suscripción, mantenimiento…)."""
    __tablename__ = "alm_contracts"

    id               = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String(36), ForeignKey("organizations.id"), nullable=True, index=True)  # audit #7
    vendor_id        = Column(String(36), ForeignKey("alm_vendors.id", ondelete="SET NULL"), nullable=True)
    title            = Column(String(300), nullable=False)
    reference        = Column(String(100), nullable=True)   # Nº contrato interno
    type             = Column(Enum(ALMContractType), nullable=False)
    status           = Column(Enum(ALMContractStatus), default=ALMContractStatus.active)
    is_active        = Column(Boolean, default=True)

    # Fechas
    start_date       = Column(Date, nullable=True)
    end_date         = Column(Date, nullable=True)
    renewal_date     = Column(Date, nullable=True)
    auto_renew       = Column(Boolean, default=False)
    notice_days      = Column(Integer, default=30)  # días de preaviso para cancelar

    # Económico
    total_value      = Column(Float, nullable=True)    # Valor total del contrato €
    annual_value     = Column(Float, nullable=True)    # Coste anual €
    billing_cycle    = Column(Enum(BillingCycle), default=BillingCycle.annual)
    currency         = Column(String(3), default=settings.DEFAULT_CURRENCY)
    payment_method   = Column(String(50), nullable=True)  # tarjeta, transferencia...
    po_number        = Column(String(100), nullable=True)  # Purchase Order
    invoice_email    = Column(String(200), nullable=True)

    # Responsabilidad
    cost_center_id   = Column(String(36), ForeignKey("alm_cost_centers.id", ondelete="SET NULL"), nullable=True)
    owner_id         = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    project_id       = Column(String(36), ForeignKey("projects.id",  ondelete="SET NULL"), nullable=True)

    # Documentos
    document_url     = Column(String(1000), nullable=True)
    invoice_url      = Column(String(1000), nullable=True)

    notes            = Column(Text, nullable=True)
    tags             = Column(String(500), nullable=True)  # comma-separated
    created_at       = Column(DateTime(timezone=True), server_default=func.now())
    updated_at       = Column(DateTime(timezone=True), onupdate=func.now())
    created_by       = Column(String(36), ForeignKey("users.id"), nullable=True)

    vendor      = relationship("ALMVendor",     back_populates="contracts")
    cost_center = relationship("ALMCostCenter", back_populates="contracts")
    owner       = relationship("User",          foreign_keys=[owner_id])
    licenses    = relationship("ALMLicense",    back_populates="contract", cascade="all, delete-orphan")


class ALMLicense(Base):
    """Licencia de software con asignaciones a usuarios o dispositivos."""
    __tablename__ = "alm_licenses"

    id                   = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String(36), ForeignKey("organizations.id"), nullable=True, index=True)  # audit #7
    contract_id          = Column(String(36), ForeignKey("alm_contracts.id", ondelete="SET NULL"), nullable=True)
    vendor_id            = Column(String(36), ForeignKey("alm_vendors.id",   ondelete="SET NULL"), nullable=True)

    name                 = Column(String(300), nullable=False)
    product_name         = Column(String(200), nullable=True)
    version              = Column(String(50),  nullable=True)
    edition              = Column(String(100), nullable=True)  # Professional, Enterprise...
    type                 = Column(Enum(LicenseType), nullable=False)
    platform             = Column(Enum(LicensePlatform), default=LicensePlatform.any)
    status               = Column(Enum(LicenseStatus), default=LicenseStatus.active)
    is_active            = Column(Boolean, default=True)

    # Seats / tokens
    total_seats          = Column(Integer, nullable=True)    # null = ilimitado
    # used_seats se calcula desde assignments

    # Claves y fechas
    license_key          = Column(String(1000), nullable=True)  # cifrado en prod
    purchase_date        = Column(Date, nullable=True)
    expiry_date          = Column(Date, nullable=True)
    purchase_price       = Column(Float, nullable=True)
    annual_cost          = Column(Float, nullable=True)

    # Responsabilidad
    cost_center_id       = Column(String(36), ForeignKey("alm_cost_centers.id", ondelete="SET NULL"), nullable=True)
    project_id           = Column(String(36), ForeignKey("projects.id", ondelete="SET NULL"), nullable=True)
    environment          = Column(String(20), default="all")  # prod|staging|dev|all
    is_compliance_req    = Column(Boolean, default=False)

    notes                = Column(Text, nullable=True)
    created_at           = Column(DateTime(timezone=True), server_default=func.now())
    updated_at           = Column(DateTime(timezone=True), onupdate=func.now())

    contract    = relationship("ALMContract",         back_populates="licenses")
    vendor      = relationship("ALMVendor",           back_populates="licenses")
    cost_center = relationship("ALMCostCenter",       back_populates="licenses")
    assignments = relationship("ALMLicenseAssignment", back_populates="license", cascade="all, delete-orphan")
    installs    = relationship("ALMSoftwareInstall",   back_populates="license", cascade="all, delete-orphan")


class ALMLicenseAssignment(Base):
    """Asignación de una licencia a un usuario, dispositivo o proyecto."""
    __tablename__ = "alm_license_assignments"

    id           = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String(36), ForeignKey("organizations.id"), nullable=True, index=True)  # audit #7
    license_id   = Column(String(36), ForeignKey("alm_licenses.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id      = Column(String(36), ForeignKey("users.id",        ondelete="SET NULL"), nullable=True, index=True)
    asset_id     = Column(String(36), ForeignKey("alm_assets.id",   ondelete="SET NULL"), nullable=True, index=True)
    project_id   = Column(String(36), ForeignKey("projects.id",     ondelete="SET NULL"), nullable=True)
    assigned_at  = Column(DateTime(timezone=True), server_default=func.now())
    assigned_by  = Column(String(36), ForeignKey("users.id"), nullable=True)
    expires_at   = Column(Date, nullable=True)
    notes        = Column(String(500), nullable=True)
    is_active    = Column(Boolean, default=True)

    license      = relationship("ALMLicense", back_populates="assignments")
    user         = relationship("User",       foreign_keys=[user_id])
    assignor     = relationship("User",       foreign_keys=[assigned_by])
    asset        = relationship("ALMAsset",   back_populates="license_assignments")


class ALMAsset(Base):
    """Activo físico o virtual (laptop, servidor, VM, móvil…)."""
    __tablename__ = "alm_assets"

    id                  = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String(36), ForeignKey("organizations.id"), nullable=True, index=True)  # audit #7
    name                = Column(String(200), nullable=False)
    type                = Column(Enum(AssetType), nullable=False)
    brand               = Column(String(100), nullable=True)
    model               = Column(String(200), nullable=True)
    serial_number       = Column(String(200), nullable=True, unique=True)
    asset_tag           = Column(String(100), nullable=True, unique=True)  # etiqueta física

    status              = Column(Enum(ALMAssetStatus, name='alm_assetstatus'), default=ALMAssetStatus.available)
    condition           = Column(Enum(AssetCondition), default=AssetCondition.good)
    is_active           = Column(Boolean, default=True)

    # Asignación
    assigned_to_id      = Column(String(36), ForeignKey("users.id",        ondelete="SET NULL"), nullable=True)
    department_id       = Column(String(36), ForeignKey("departments.id",  ondelete="SET NULL"), nullable=True)
    project_id          = Column(String(36), ForeignKey("projects.id",     ondelete="SET NULL"), nullable=True)
    location            = Column(String(200), nullable=True)  # Oficina / sala / rack

    # Financiero
    vendor_id           = Column(String(36), ForeignKey("alm_vendors.id", ondelete="SET NULL"), nullable=True)
    purchase_date       = Column(Date, nullable=True)
    purchase_price      = Column(Float, nullable=True)
    currency            = Column(String(3), default=settings.DEFAULT_CURRENCY)
    warranty_expiry     = Column(Date, nullable=True)
    depreciation_years  = Column(Integer, default=3)
    cost_center_id      = Column(String(36), ForeignKey("alm_cost_centers.id", ondelete="SET NULL"), nullable=True)

    # IP / red (para servidores/VMs)
    ip_address          = Column(String(50),  nullable=True)
    hostname            = Column(String(200), nullable=True)
    os                  = Column(String(100), nullable=True)
    cpu                 = Column(String(100), nullable=True)
    ram_gb              = Column(Integer,     nullable=True)
    storage_gb          = Column(Integer,     nullable=True)

    notes               = Column(Text, nullable=True)
    created_at          = Column(DateTime(timezone=True), server_default=func.now())
    updated_at          = Column(DateTime(timezone=True), onupdate=func.now())

    assigned_to         = relationship("User",       foreign_keys=[assigned_to_id])
    vendor              = relationship("ALMVendor",  back_populates="assets")
    license_assignments = relationship("ALMLicenseAssignment", back_populates="asset")
    installs            = relationship("ALMSoftwareInstall",   back_populates="asset", cascade="all, delete-orphan")


class ALMSoftwareInstall(Base):
    """Instalación de un software (licencia) en un activo."""
    __tablename__ = "alm_software_installs"

    id           = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String(36), ForeignKey("organizations.id"), nullable=True, index=True)  # audit #7
    license_id   = Column(String(36), ForeignKey("alm_licenses.id", ondelete="CASCADE"), nullable=False, index=True)
    asset_id     = Column(String(36), ForeignKey("alm_assets.id",   ondelete="CASCADE"), nullable=False, index=True)
    installed_at = Column(DateTime(timezone=True), server_default=func.now())
    installed_by = Column(String(36), ForeignKey("users.id"), nullable=True)
    version      = Column(String(50), nullable=True)
    is_active    = Column(Boolean, default=True)
    notes        = Column(String(500), nullable=True)

    license      = relationship("ALMLicense", back_populates="installs")
    asset        = relationship("ALMAsset",   back_populates="installs")


class ALMRenewalAlert(Base):
    """Alertas de renovación/vencimiento de contratos y licencias."""
    __tablename__ = "alm_renewal_alerts"

    id           = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String(36), ForeignKey("organizations.id"), nullable=True, index=True)  # audit #7
    entity_type  = Column(String(20), nullable=False)   # contract | license | asset_warranty
    entity_id    = Column(String(36), nullable=False)
    alert_date   = Column(Date, nullable=False)          # cuándo debe dispararse
    days_before  = Column(Integer, nullable=False)       # cuántos días antes del vencimiento
    is_sent      = Column(Boolean, default=False)
    sent_at      = Column(DateTime(timezone=True), nullable=True)
    recipient_id = Column(String(36), ForeignKey("users.id"), nullable=True)
    created_at   = Column(DateTime(timezone=True), server_default=func.now())
