"""
Asset & License Management (ALM) — Enterprise Grade
Gestión de proveedores, contratos, licencias, activos y suscripciones.

Fases 1 y 3 de licencias y hardware (16-11-2026)
================================================

**Asignación universal** (`ALMAsignacion`, tabla `alm_license_assignments`). Amplía
`alm_license_assignments` (misma tabla, mismos ids) y sustituye a la asignación implícita del activo
(`assigned_to_id`, que se mantiene como reflejo del titular persona vigente).
Una fila = un recurso (licencia o activo) en manos de un titular durante un
intervalo:

- ``resource_type``: ``license`` | ``asset``; con ``license_id`` o ``asset_id``.
- ``holder_type``: ``user`` | ``project`` | ``department`` | ``client`` |
  ``asset`` (dispositivo), con su columna tipada (``holder_user_id``,
  ``holder_project_id``, ``holder_department_id``, ``holder_client_id``,
  ``holder_asset_id``). ``holder_id`` devuelve la que toque.
- ``mode``: ``assignment`` | ``loan`` (préstamo de un activo; ``valid_to`` es la
  devolución prevista) | ``pool`` (bolsa de asientos de un proyecto,
  departamento o cliente que se reparte con asignaciones hijas, ``parent_id``).
- ``status``: ``pending`` (espera aprobación) | ``active`` | ``ended`` |
  ``rejected`` | ``cancelled``; ``end_kind`` dice cómo acabó (``returned``,
  ``revoked``, ``released``, ``expired``, ``lost``, ``transferred``).
- ``valid_from`` / ``valid_to`` (previsto) / ``ended_on`` (real, incluido): el
  intervalo con el que se calcula el coste por día (fase 3).

Nunca se borra una asignación: se cierra. Cada paso deja un `ALMEvento`
(tabla `alm_eventos`), inmutable: «quién tuvo qué, cuándo y por qué».

**Interfaz para la fase 2 (uso real).** Solo lectura del modelo; para
escribir, las funciones de servicio:

- `app.services.alm_asignaciones.titulares_vigentes(db, license_id, dia=None)`
  → asignaciones activas de una licencia ese día (las hijas de una bolsa
  incluidas; ``holder_user_id`` es la persona, ``holder_asset_id`` el equipo).
- `app.services.alm_asignaciones.asignaciones_de_usuario(db, user_id)`.
- `ALMLicense.metric` (``named_user`` | ``device`` | ``concurrent`` |
  ``volume`` | ``site``), ``tier`` / ``tier_rank`` (mayor rango = nivel más
  alto) y ``sku``; ``product_name`` agrupa los niveles de un mismo producto.
- Pico concurrente: `app.services.alm_asignaciones.registrar_pico(db,
  license_id, pico, medido_en=None, fuente=...)`.
- Liberar una licencia sin uso: `alm_asignaciones.liberar(db, asignacion_id,
  actor=None, motivo=..., tipo="released", origen="usage")`.
- La fase 2 implementa `app.services.alm_uso.uso_de_licencia(db, license_id)`;
  lo lee `app.services.alm_renovaciones.uso_de_licencia` (ver su docstring).

**Interfaz para la fase 4 (altas, bajas, autoservicio, catálogo).**
`app.services.alm_asignaciones`: ``asignar``, ``liberar``,
``liberar_licencias_de_usuario``, ``prestar``, ``devolver``,
``equipos_de_usuario``, ``asignaciones_de_usuario``. Ver sus docstrings.
"""
import uuid
import enum
from sqlalchemy import Index
from sqlalchemy import (Column, String, Float, Integer, Boolean, Date,
                        DateTime, Text, ForeignKey, Enum, UniqueConstraint)
from sqlalchemy import event as _event
from sqlalchemy.orm import relationship, synonym
from sqlalchemy.ext.hybrid import hybrid_property
from sqlalchemy.sql import func
from app.db.base import Base
from app.models.money import Money
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
    """Plazo comercial (y, por compatibilidad, algunas métricas). La métrica de
    asientos es `ALMLicense.metric` (`LicenseMetric`)."""
    perpetual    = "perpetual"
    subscription = "subscription"
    concurrent   = "concurrent"
    named        = "named"
    device       = "device"
    trial        = "trial"
    free         = "free"
    oem          = "oem"
    volume       = "volume"

class LicenseMetric(str, enum.Enum):
    """Qué cuenta un asiento."""
    named_user = "named_user"   # una persona por asiento
    device     = "device"       # un dispositivo por asiento
    concurrent = "concurrent"   # cuenta el pico de uso simultáneo, no las asignaciones
    volume     = "volume"       # unidades; cada asignación consume su `quantity`
    site       = "site"         # sin límite de asientos (sitio o empresa)

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
    """Ciclo de vida: ordered (comprado) → available (almacén) → in_use |
    on_loan → in_repair → retired (baja) → disposed (reciclado, donado,
    vendido o destruido). `lost` / `stolen` salen de un estado con titular."""
    ordered   = "ordered"
    available = "available"
    in_use    = "in_use"
    on_loan   = "on_loan"
    in_repair = "in_repair"
    retired   = "retired"
    disposed  = "disposed"
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
    organization_id = Column(String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=True, index=True)  # audit #7
    code           = Column(String(20), nullable=False)  # CC-001 (unique per-tenant — ver __table_args__)
    name           = Column(String(200), nullable=False)
    description    = Column(Text, nullable=True)
    department_id  = Column(String(36), ForeignKey("departments.id", ondelete="SET NULL"), nullable=True, index=True)
    manager_id     = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    budget_annual  = Column(Money, nullable=True)   # € presupuesto anual
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
    organization_id = Column(String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=True, index=True)  # audit #7
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
    country          = Column(String(3),   default=settings.DEFAULT_COUNTRY)  # 19-11-2026: país de la empresa en el alta
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
    organization_id = Column(String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=True, index=True)  # audit #7
    vendor_id        = Column(String(36), ForeignKey("alm_vendors.id", ondelete="SET NULL"), nullable=True, index=True)
    title            = Column(String(300), nullable=False)
    reference        = Column(String(100), nullable=True)   # Nº contrato interno
    type             = Column(Enum(ALMContractType), nullable=False)
    status           = Column(Enum(ALMContractStatus), default=ALMContractStatus.active)
    is_active        = Column(Boolean, default=True, nullable=False)

    # Fechas
    start_date       = Column(Date, nullable=True)
    end_date         = Column(Date, nullable=True)
    renewal_date     = Column(Date, nullable=True)
    # Fase 3: al llegar la renovación sin decisión de cancelar, el barrido
    # diario la prorroga un periodo (`alm_renovaciones`).
    auto_renew       = Column(Boolean, default=False)
    # Días de preaviso para cancelar: el aviso de renovación se calcula sobre
    # renovación − preaviso (`alm_renovaciones`).
    notice_days      = Column(Integer, default=30)

    # Económico
    total_value      = Column(Money, nullable=True)    # Valor total del contrato €
    annual_value     = Column(Money, nullable=True)    # Coste anual €
    billing_cycle    = Column(Enum(BillingCycle), default=BillingCycle.annual)
    currency         = Column(String(3), default=settings.DEFAULT_CURRENCY)
    payment_method   = Column(String(50), nullable=True)  # tarjeta, transferencia...
    po_number        = Column(String(100), nullable=True)  # Purchase Order
    invoice_email    = Column(String(200), nullable=True)

    # Responsabilidad
    cost_center_id   = Column(String(36), ForeignKey("alm_cost_centers.id", ondelete="SET NULL"), nullable=True, index=True)
    owner_id         = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    project_id       = Column(String(36), ForeignKey("projects.id",  ondelete="SET NULL"), nullable=True, index=True)

    # Documentos
    document_url     = Column(String(1000), nullable=True)
    invoice_url      = Column(String(1000), nullable=True)

    notes            = Column(Text, nullable=True)
    tags             = Column(String(500), nullable=True)  # comma-separated
    # UC: plazo de resolucion que el proveedor se compromete a cumplir cuando
    # un ticket queda pendiente de el. Vacio: el contrato no es de soporte.
    resolution_hours = Column(Float, nullable=True)
    # Y en cuanto tiempo tiene que contestar (vacio: sin plazo de respuesta).
    response_hours = Column(Float, nullable=True)
    created_at       = Column(DateTime(timezone=True), server_default=func.now())
    updated_at       = Column(DateTime(timezone=True), onupdate=func.now())
    created_by       = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)

    vendor      = relationship("ALMVendor",     back_populates="contracts")
    cost_center = relationship("ALMCostCenter", back_populates="contracts")
    owner       = relationship("User",          foreign_keys=[owner_id])
    licenses    = relationship("ALMLicense",    back_populates="contract", cascade="all, delete-orphan")


class ALMLicense(Base):
    """Licencia de software con asignaciones a personas, equipos, proyectos, departamentos o clientes."""
    __tablename__ = "alm_licenses"

    id                   = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=True, index=True)  # audit #7
    contract_id          = Column(String(36), ForeignKey("alm_contracts.id", ondelete="SET NULL"), nullable=True, index=True)
    vendor_id            = Column(String(36), ForeignKey("alm_vendors.id",   ondelete="SET NULL"), nullable=True, index=True)

    name                 = Column(String(300), nullable=False)
    product_name         = Column(String(200), nullable=True)
    version              = Column(String(50),  nullable=True)
    edition              = Column(String(100), nullable=True)  # Professional, Enterprise...
    type                 = Column(Enum(LicenseType), nullable=False)
    platform             = Column(Enum(LicensePlatform), default=LicensePlatform.any)
    status               = Column(Enum(LicenseStatus), default=LicenseStatus.active)
    is_active            = Column(Boolean, default=True, nullable=False)

    # Seats / tokens
    total_seats          = Column(Integer, nullable=True)    # null = ilimitado
    # used_seats se calcula desde las asignaciones (`alm_asignaciones.asientos_usados`)

    # Métrica y niveles (fase 1)
    metric               = Column(String(20), nullable=False, default=LicenseMetric.named_user.value,
                                  server_default=LicenseMetric.named_user.value)
    sku                  = Column(String(100), nullable=True)
    tier                 = Column(String(100), nullable=True)   # E3, E5, Pro, Enterprise...
    tier_rank            = Column(Integer, nullable=True)       # mayor = nivel más alto (y más caro)
    # Pico de uso simultáneo medido (licencias concurrentes); lo alimenta la fase 2.
    concurrent_peak      = Column(Integer, nullable=True)
    concurrent_peak_at   = Column(DateTime(timezone=True), nullable=True)
    # Amortización de una licencia perpetua (meses); vacío: ALM_PERPETUAL_AMORTIZATION_MONTHS.
    amortization_months  = Column(Integer, nullable=True)
    # Por defecto, sus asignaciones se refacturan al cliente (fase 3).
    rebillable           = Column(Boolean, nullable=False, default=False, server_default="0")

    # Clave cifrada en reposo (`app.core.encryption`): la columna guarda el
    # texto cifrado; la propiedad `license_key` cifra al escribir y descifra al
    # leer. `license_key_hint`: los 4 últimos caracteres, para reconocerla.
    _license_key         = Column("license_key", Text, nullable=True)
    license_key_hint     = Column(String(8), nullable=True)
    purchase_date        = Column(Date, nullable=True)
    expiry_date          = Column(Date, nullable=True)
    purchase_price       = Column(Money, nullable=True)
    annual_cost          = Column(Money, nullable=True)

    # Responsabilidad
    cost_center_id       = Column(String(36), ForeignKey("alm_cost_centers.id", ondelete="SET NULL"), nullable=True, index=True)
    project_id           = Column(String(36), ForeignKey("projects.id", ondelete="SET NULL"), nullable=True, index=True)
    environment          = Column(String(20), default="all")  # prod|staging|dev|all
    is_compliance_req    = Column(Boolean, default=False)

    notes                = Column(Text, nullable=True)
    created_at           = Column(DateTime(timezone=True), server_default=func.now())
    updated_at           = Column(DateTime(timezone=True), onupdate=func.now())

    contract    = relationship("ALMContract",         back_populates="licenses")
    vendor      = relationship("ALMVendor",           back_populates="licenses")
    cost_center = relationship("ALMCostCenter",       back_populates="licenses")
    assignments = relationship("ALMAsignacion", foreign_keys="ALMAsignacion.license_id",
                               back_populates="license", cascade="all, delete-orphan")
    installs    = relationship("ALMSoftwareInstall",   back_populates="license", cascade="all, delete-orphan")

    @property
    def license_key(self):
        """La clave en claro. Solo sale por `GET /alm/licenses/{id}/key` (gestores, queda en el historial)."""
        if not self._license_key:
            return None
        from app.core.encryption import decrypt_value
        return decrypt_value(self._license_key)

    @license_key.setter
    def license_key(self, valor):
        texto = "" if valor is None else str(valor).strip()
        if not texto:
            self._license_key = None
            self.license_key_hint = None
            return
        from app.core.encryption import encrypt_value
        self._license_key = encrypt_value(texto)
        self.license_key_hint = texto[-4:]


# ── Asignación universal (fase 1) ──────────────────────────────────────────────
# Ver la cabecera del módulo: es la interfaz que leen las fases 2 y 4.

#: Tipo de titular → columna que guarda su id.
COLUMNA_DE_TITULAR = {
    "user": "holder_user_id",
    "project": "holder_project_id",
    "department": "holder_department_id",
    "client": "holder_client_id",
    "asset": "holder_asset_id",
}
TIPOS_DE_TITULAR = tuple(COLUMNA_DE_TITULAR)
ESTADOS_DE_ASIGNACION = ("pending", "active", "ended", "rejected", "cancelled")
MODOS_DE_ASIGNACION = ("assignment", "loan", "pool")
FINALES_DE_ASIGNACION = ("returned", "revoked", "released", "expired", "lost", "transferred")


class ALMAsignacion(Base):
    """Un recurso (licencia o activo) en manos de un titular durante un intervalo.

    Tabla: `alm_license_assignments` (nombre histórico). La migración 170 la
    amplía en el sitio, conservando los ids, para que lo que ya apunta a una
    asignación (la fase 2) siga valiendo. Ojo con el cambio de sentido:
    ``asset_id`` es ahora el ACTIVO asignado (recurso); el equipo que tiene
    una licencia por dispositivo es ``holder_asset_id``.
    """
    __tablename__ = "alm_license_assignments"
    __table_args__ = (
        Index("ix_alm_asignaciones_licencia_estado", "license_id", "status"),
        Index("ix_alm_asignaciones_activo_estado", "asset_id", "status"),
    )

    id                    = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id       = Column(String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=True, index=True)
    resource_type         = Column(String(10), nullable=False)            # license | asset
    license_id            = Column(String(36), ForeignKey("alm_licenses.id", ondelete="CASCADE"), nullable=True, index=True)
    asset_id              = Column(String(36), ForeignKey("alm_assets.id", ondelete="CASCADE"), nullable=True, index=True)

    holder_type           = Column(String(12), nullable=False)            # user | project | department | client | asset
    holder_user_id        = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    holder_project_id     = Column(String(36), ForeignKey("projects.id", ondelete="SET NULL"), nullable=True, index=True)
    holder_department_id  = Column(String(36), ForeignKey("departments.id", ondelete="SET NULL"), nullable=True, index=True)
    holder_client_id      = Column(String(36), ForeignKey("clients.id", ondelete="SET NULL"), nullable=True, index=True)
    holder_asset_id       = Column(String(36), ForeignKey("alm_assets.id", ondelete="SET NULL"), nullable=True, index=True)

    mode                  = Column(String(12), nullable=False, default="assignment")   # assignment | loan | pool
    parent_id             = Column(String(36), ForeignKey("alm_license_assignments.id", ondelete="CASCADE"), nullable=True, index=True)
    quantity              = Column(Integer, nullable=False, default=1)
    status                = Column(String(12), nullable=False, default="active", index=True)

    valid_from            = Column(Date, nullable=False)
    valid_to              = Column(Date, nullable=True)        # fin previsto (devolución de un préstamo)
    ended_on              = Column(Date, nullable=True)        # fin real; el coste cuenta hasta aquí, incluido
    ended_at              = Column(DateTime(timezone=True), nullable=True)
    ended_by              = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    end_kind              = Column(String(12), nullable=True)
    end_reason            = Column(Text, nullable=True)

    reason                = Column(Text, nullable=True)        # por qué se asigna
    # manual | migration | onboarding | offboarding | catalog | usage | system
    source                = Column(String(30), nullable=False, default="manual")
    assigned_by           = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    assigned_at           = Column(DateTime(timezone=True), server_default=func.now())
    approved_by           = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    approved_at           = Column(DateTime(timezone=True), nullable=True)

    # Imputación del coste (fase 3). Vacío: se deduce del titular y del recurso
    # (`alm_costes.cargo_de`).
    charge_project_id     = Column(String(36), ForeignKey("projects.id", ondelete="SET NULL"), nullable=True, index=True)
    charge_cost_center_id = Column(String(36), ForeignKey("alm_cost_centers.id", ondelete="SET NULL"), nullable=True, index=True)
    charge_client_id      = Column(String(36), ForeignKey("clients.id", ondelete="SET NULL"), nullable=True, index=True)
    rebillable            = Column(Boolean, nullable=True)     # None: lo que diga la licencia o el activo
    notes                 = Column(String(500), nullable=True)

    license      = relationship("ALMLicense", foreign_keys=[license_id], back_populates="assignments")
    asset        = relationship("ALMAsset", foreign_keys=[asset_id], back_populates="assignments")
    holder_user  = relationship("User", foreign_keys=[holder_user_id])
    holder_asset = relationship("ALMAsset", foreign_keys=[holder_asset_id])
    assignor     = relationship("User", foreign_keys=[assigned_by])
    parent       = relationship("ALMAsignacion", remote_side=[id], back_populates="children")
    children     = relationship("ALMAsignacion", back_populates="parent")

    @property
    def holder_id(self):
        columna = COLUMNA_DE_TITULAR.get(self.holder_type)
        return getattr(self, columna) if columna else None

    # Compatibilidad con el modelo anterior (`ALMLicenseAssignment`).
    user_id    = synonym("holder_user_id")
    project_id = synonym("holder_project_id")
    expires_at = synonym("valid_to")

    @hybrid_property
    def is_active(self) -> bool:
        """Ocupa asiento: activa o pendiente de aprobar (una pendiente reserva su asiento)."""
        return self.status in ("active", "pending")

    @is_active.expression
    def is_active(cls):
        return cls.status.in_(("active", "pending"))

    def vigente_en(self, dia) -> bool:
        """Cuenta ese día: activa (o ya terminada) y dentro de su intervalo real."""
        if self.status not in ("active", "ended"):
            return False
        if self.valid_from and dia < self.valid_from:
            return False
        if self.status == "ended":
            return self.ended_on is not None and dia <= self.ended_on
        return True


#: Nombre anterior del modelo (las asignaciones solo eran de licencias).
ALMLicenseAssignment = ALMAsignacion


class ALMEvento(Base):
    """Historial inmutable de licencias y activos: una fila por paso; ni se cambia ni se borra."""
    __tablename__ = "alm_eventos"
    __table_args__ = (
        Index("ix_alm_eventos_titular", "holder_type", "holder_id"),
    )

    id              = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=True, index=True)
    resource_type   = Column(String(10), nullable=False)
    license_id      = Column(String(36), ForeignKey("alm_licenses.id", ondelete="SET NULL"), nullable=True, index=True)
    asset_id        = Column(String(36), ForeignKey("alm_assets.id", ondelete="SET NULL"), nullable=True, index=True)
    contract_id     = Column(String(36), ForeignKey("alm_contracts.id", ondelete="SET NULL"), nullable=True, index=True)
    assignment_id   = Column(String(36), ForeignKey("alm_license_assignments.id", ondelete="SET NULL"), nullable=True, index=True)
    # Código del paso (lo traduce la interfaz: `alm.ev_<event>`). Ver
    # `alm_asignaciones.EVENTOS`.
    event           = Column(String(30), nullable=False)
    holder_type     = Column(String(12), nullable=True)
    holder_id       = Column(String(36), nullable=True)
    holder_name     = Column(String(200), nullable=True)    # el nombre del titular en ese momento
    actor_id        = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    reason          = Column(Text, nullable=True)
    data            = Column(Text, nullable=True)           # JSON
    created_at      = Column(DateTime(timezone=True), server_default=func.now(), index=True)

    actor = relationship("User", foreign_keys=[actor_id])


class ALMAsset(Base):
    """Activo físico o virtual (laptop, servidor, VM, móvil…)."""
    __tablename__ = "alm_assets"
    # Unico por organizacion (revision multitenant 2026-11): antes era global y
    # una segunda empresa no podia repetir el codigo/nombre de otra.
    __table_args__ = (Index("uq_alm_assets_org_serial_number", "organization_id", "serial_number", unique=True), Index("uq_alm_assets_org_asset_tag", "organization_id", "asset_tag", unique=True),)

    id                  = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=True, index=True)  # audit #7
    name                = Column(String(200), nullable=False)
    type                = Column(Enum(AssetType, name='alm_assettype'), nullable=False)
    brand               = Column(String(100), nullable=True)
    model               = Column(String(200), nullable=True)
    serial_number       = Column(String(200), nullable=True)
    asset_tag           = Column(String(100), nullable=True)  # etiqueta física

    status              = Column(Enum(ALMAssetStatus, name='alm_assetstatus'), default=ALMAssetStatus.available)
    condition           = Column(Enum(AssetCondition), default=AssetCondition.good)
    is_active           = Column(Boolean, default=True, nullable=False)

    # Asignación. Fase 1: el titular está en `ALMAsignacion`; estas tres
    # columnas son su reflejo (persona, departamento o proyecto vigente) para
    # quien ya las leía (CMDB, filtros, informes). Las mantiene el servicio.
    assigned_to_id      = Column(String(36), ForeignKey("users.id",        ondelete="SET NULL"), nullable=True, index=True)
    department_id       = Column(String(36), ForeignKey("departments.id",  ondelete="SET NULL"), nullable=True, index=True)
    project_id          = Column(String(36), ForeignKey("projects.id",     ondelete="SET NULL"), nullable=True, index=True)
    location            = Column(String(200), nullable=True)  # Oficina / sala / rack

    # Financiero
    vendor_id           = Column(String(36), ForeignKey("alm_vendors.id", ondelete="SET NULL"), nullable=True, index=True)
    purchase_date       = Column(Date, nullable=True)
    purchase_price      = Column(Money, nullable=True)
    currency            = Column(String(3), default=settings.DEFAULT_CURRENCY)
    warranty_expiry     = Column(Date, nullable=True)
    depreciation_years  = Column(Integer, default=3)
    cost_center_id      = Column(String(36), ForeignKey("alm_cost_centers.id", ondelete="SET NULL"), nullable=True, index=True)
    # Fase 3: amortización lineal de (precio − residual) en `depreciation_years`,
    # o la cuota de un renting/leasing.
    residual_value      = Column(Money, nullable=True)
    lease_monthly_cost  = Column(Money, nullable=True)
    rebillable          = Column(Boolean, nullable=False, default=False, server_default="0")

    # IP / red (para servidores/VMs)
    ip_address          = Column(String(50),  nullable=True)
    hostname            = Column(String(200), nullable=True)
    os                  = Column(String(100), nullable=True)
    cpu                 = Column(String(100), nullable=True)
    ram_gb              = Column(Integer,     nullable=True)
    storage_gb          = Column(Integer,     nullable=True)

    # Ciclo de vida y CMDB (antes en `sd_assets`; migracion 111)
    ci_id               = Column(String(36), ForeignKey("sd_configuration_items.id", ondelete="SET NULL"), nullable=True, index=True)
    eol_date            = Column(Date, nullable=True)        # fin de vida del fabricante
    lease_expiry        = Column(Date, nullable=True)
    next_maintenance_date = Column(Date, nullable=True)
    maintenance_contract = Column(String(255), nullable=True)
    # El ticket de renovacion abierto: el escaneo diario no abre otro mientras siga abierto.
    refresh_ticket_id   = Column(String(36), ForeignKey("sd_tickets.id", ondelete="SET NULL"), nullable=True, index=True)

    # Baja y reciclaje (fase 1)
    disposal_date       = Column(Date, nullable=True)
    disposal_reason     = Column(String(30), nullable=True)   # obsolete | broken | lost | stolen | sold | other
    disposal_method     = Column(String(30), nullable=True)   # recycle | donate | sell | destroy
    disposal_value      = Column(Money, nullable=True)

    notes               = Column(Text, nullable=True)
    created_at          = Column(DateTime(timezone=True), server_default=func.now())
    updated_at          = Column(DateTime(timezone=True), onupdate=func.now())

    assigned_to         = relationship("User",       foreign_keys=[assigned_to_id])
    ci                  = relationship("ConfigurationItem", foreign_keys=[ci_id])
    history             = relationship("ALMAssetHistory", back_populates="asset", cascade="all, delete-orphan",
                                       order_by="ALMAssetHistory.changed_at")
    vendor              = relationship("ALMVendor",  back_populates="assets")
    # Las asignaciones y préstamos del propio activo (no las licencias asignadas a él).
    assignments         = relationship("ALMAsignacion", foreign_keys="ALMAsignacion.asset_id",
                                       back_populates="asset", cascade="all, delete-orphan")
    installs            = relationship("ALMSoftwareInstall",   back_populates="asset", cascade="all, delete-orphan")


class ALMAssetHistory(Base):
    """Cada cambio de un activo: estado, asignacion, ubicacion, CI, fechas..."""
    __tablename__ = "alm_asset_history"

    id          = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=True, index=True)
    asset_id    = Column(String(36), ForeignKey("alm_assets.id", ondelete="CASCADE"), nullable=False, index=True)
    field_name  = Column(String(100), nullable=False)
    old_value   = Column(String(500), nullable=True)
    new_value   = Column(String(500), nullable=True)
    changed_by  = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    note        = Column(String(255), nullable=True)
    changed_at  = Column(DateTime(timezone=True), server_default=func.now())

    asset       = relationship("ALMAsset", back_populates="history")
    changed_by_user = relationship("User", foreign_keys=[changed_by])


class ALMSoftwareInstall(Base):
    """Instalación de un software (licencia) en un activo."""
    __tablename__ = "alm_software_installs"

    id           = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=True, index=True)  # audit #7
    license_id   = Column(String(36), ForeignKey("alm_licenses.id", ondelete="CASCADE"), nullable=False, index=True)
    asset_id     = Column(String(36), ForeignKey("alm_assets.id",   ondelete="CASCADE"), nullable=False, index=True)
    installed_at = Column(DateTime(timezone=True), server_default=func.now())
    installed_by = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    version      = Column(String(50), nullable=True)
    is_active    = Column(Boolean, default=True, nullable=False)
    notes        = Column(String(500), nullable=True)

    license      = relationship("ALMLicense", back_populates="installs")
    asset        = relationship("ALMAsset",   back_populates="installs")


class ALMRenewalAlert(Base):
    """Avisos enviados de renovación, vencimiento y préstamos (fase 3).

    Era una tabla muerta; ahora es el registro de lo avisado por el barrido
    diario (`alm_renovaciones.escanear`): una fila por (entidad, tipo de aviso,
    fecha de referencia), así el aviso no se repite cada día y, si la fecha
    cambia (se prorroga), se vuelve a avisar.
    """
    __tablename__ = "alm_renewal_alerts"
    __table_args__ = (
        UniqueConstraint("organization_id", "entity_type", "entity_id", "kind", "reference_date",
                         name="uq_alm_renewal_alert_once"),
    )

    id           = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=True, index=True)  # audit #7
    entity_type  = Column(String(20), nullable=False)   # contract | license | loan
    entity_id    = Column(String(36), nullable=False)
    # notice (se acerca el preaviso) | deadline (vence el preaviso) | expired |
    # auto_renewed | loan_due | loan_overdue
    kind         = Column(String(20), nullable=False, default="notice")
    reference_date = Column(Date, nullable=True)         # la fecha de renovación o de devolución avisada
    alert_date   = Column(Date, nullable=False)          # cuándo se avisó
    days_before  = Column(Integer, nullable=False)       # días que faltaban (negativo: ya pasada)
    is_sent      = Column(Boolean, default=False)
    sent_at      = Column(DateTime(timezone=True), nullable=True)
    recipient_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    created_at   = Column(DateTime(timezone=True), server_default=func.now())


# ── Actas de entrega y devolución (fase 1) ────────────────────────────────────

class ALMActa(Base):
    """Acta de entrega o devolución de un activo: checklist, estado, PDF y firma."""
    __tablename__ = "alm_actas"

    id                = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id   = Column(String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=True, index=True)
    kind              = Column(String(10), nullable=False)          # delivery | return
    assignment_id     = Column(String(36), ForeignKey("alm_license_assignments.id", ondelete="CASCADE"), nullable=False, index=True)
    asset_id          = Column(String(36), ForeignKey("alm_assets.id", ondelete="CASCADE"), nullable=False, index=True)
    signer_user_id    = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    issued_by         = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    checklist         = Column(Text, nullable=True)                 # JSON [{item, ok, note}]
    condition         = Column(String(10), nullable=True)           # new | good | fair | poor
    observations      = Column(Text, nullable=True)
    document_id       = Column(String(36), ForeignKey("documents.id", ondelete="SET NULL"), nullable=True)
    envelope_id       = Column(String(36), ForeignKey("esign_envelopes.id", ondelete="SET NULL"), nullable=True)
    # pending_signature | signed | void | unsigned (sin persona que firme: proyecto, cliente...)
    status            = Column(String(20), nullable=False, default="pending_signature")
    signed_at         = Column(DateTime(timezone=True), nullable=True)
    created_at        = Column(DateTime(timezone=True), server_default=func.now())

    assignment = relationship("ALMAsignacion", foreign_keys=[assignment_id])
    asset      = relationship("ALMAsset", foreign_keys=[asset_id])
    signer     = relationship("User", foreign_keys=[signer_user_id])


class ALMAdjunto(Base):
    """Documento de un activo, de un acta o de una factura (foto del estado, certificado, PDF...)."""
    __tablename__ = "alm_adjuntos"

    id              = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=True, index=True)
    asset_id        = Column(String(36), ForeignKey("alm_assets.id", ondelete="CASCADE"), nullable=True, index=True)
    act_id          = Column(String(36), ForeignKey("alm_actas.id", ondelete="CASCADE"), nullable=True, index=True)
    invoice_id      = Column(String(36), ForeignKey("alm_facturas_proveedor.id", ondelete="CASCADE"), nullable=True, index=True)
    document_id     = Column(String(36), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False)
    kind            = Column(String(30), nullable=False, default="photo")  # photo | disposal_certificate | invoice | other
    uploaded_by     = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at      = Column(DateTime(timezone=True), server_default=func.now())


# ── Pico concurrente (fase 1; lo alimenta la fase 2) ──────────────────────────

class ALMPicoConcurrencia(Base):
    """Una medida del uso simultáneo de una licencia concurrente."""
    __tablename__ = "alm_picos_concurrencia"

    id              = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=True, index=True)
    license_id      = Column(String(36), ForeignKey("alm_licenses.id", ondelete="CASCADE"), nullable=False, index=True)
    measured_at     = Column(DateTime(timezone=True), nullable=False, index=True)
    peak            = Column(Integer, nullable=False)
    source          = Column(String(40), nullable=False, default="manual")
    created_at      = Column(DateTime(timezone=True), server_default=func.now())


# ── Renovaciones y conciliación (fase 3) ──────────────────────────────────────

class ALMRenovacion(Base):
    """Decisión sobre la próxima renovación de un contrato o licencia: renovar, reducir o cancelar."""
    __tablename__ = "alm_renovaciones"

    id              = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=True, index=True)
    entity_type     = Column(String(10), nullable=False)        # contract | license
    contract_id     = Column(String(36), ForeignKey("alm_contracts.id", ondelete="CASCADE"), nullable=True, index=True)
    license_id      = Column(String(36), ForeignKey("alm_licenses.id", ondelete="CASCADE"), nullable=True, index=True)
    term_date       = Column(Date, nullable=False)              # la renovación a la que se refiere
    decision        = Column(String(10), nullable=False)        # renew | reduce | cancel
    new_seats       = Column(Integer, nullable=True)
    new_annual_cost = Column(Money, nullable=True)
    reason          = Column(Text, nullable=True)
    usage_snapshot  = Column(Text, nullable=True)               # JSON: el uso que se vio al decidir
    status          = Column(String(12), nullable=False, default="pending")   # pending | applied | superseded
    decided_by      = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    decided_at      = Column(DateTime(timezone=True), server_default=func.now())
    applied_at      = Column(DateTime(timezone=True), nullable=True)

    decider = relationship("User", foreign_keys=[decided_by])


class ALMFacturaProveedor(Base):
    """Factura de un proveedor, conciliada con su contrato y con el gasto que la paga."""
    __tablename__ = "alm_facturas_proveedor"
    __table_args__ = (
        UniqueConstraint("organization_id", "vendor_id", "number", name="uq_alm_factura_numero_por_proveedor"),
    )

    id              = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=True, index=True)
    vendor_id       = Column(String(36), ForeignKey("alm_vendors.id", ondelete="SET NULL"), nullable=True, index=True)
    contract_id     = Column(String(36), ForeignKey("alm_contracts.id", ondelete="SET NULL"), nullable=True, index=True)
    license_id      = Column(String(36), ForeignKey("alm_licenses.id", ondelete="SET NULL"), nullable=True, index=True)
    number          = Column(String(100), nullable=False)
    issue_date      = Column(Date, nullable=False)
    period_from     = Column(Date, nullable=True)
    period_to       = Column(Date, nullable=True)
    amount          = Column(Money, nullable=False)              # base imponible
    tax_amount      = Column(Money, nullable=True)
    currency        = Column(String(3), default=settings.DEFAULT_CURRENCY)
    expense_id      = Column(String(36), ForeignKey("expenses.id", ondelete="SET NULL"), nullable=True, index=True)
    # pending | matched | discrepancy | accepted (discrepancia aceptada con nota)
    status          = Column(String(12), nullable=False, default="pending", index=True)
    expected_amount = Column(Money, nullable=True)
    difference      = Column(Float, nullable=True)
    issues          = Column(Text, nullable=True)                # JSON: códigos de discrepancia
    notes           = Column(Text, nullable=True)
    reconciled_by   = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    reconciled_at   = Column(DateTime(timezone=True), nullable=True)
    created_by      = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    is_active       = Column(Boolean, nullable=False, default=True, server_default="1")
    created_at      = Column(DateTime(timezone=True), server_default=func.now())

    vendor   = relationship("ALMVendor", foreign_keys=[vendor_id])
    contract = relationship("ALMContract", foreign_keys=[contract_id])
    license  = relationship("ALMLicense", foreign_keys=[license_id])


# ── El historial no se toca ───────────────────────────────────────────────────

@_event.listens_for(ALMEvento, "before_update")
def _evento_inmutable_al_cambiar(mapper, connection, target):
    raise ValueError("alm_eventos es inmutable: una fila del historial no se cambia")


@_event.listens_for(ALMEvento, "before_delete")
def _evento_inmutable_al_borrar(mapper, connection, target):
    raise ValueError("alm_eventos es inmutable: una fila del historial no se borra")
