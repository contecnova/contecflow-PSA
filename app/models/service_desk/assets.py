"""service_desk.assets models — split from the former 1385-LOC god-file."""

from sqlalchemy import Column, String, Float, DateTime, ForeignKey, Text, Integer, Enum, UniqueConstraint
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import uuid
from app.db.base import Base
from app.core.config import settings


from app.models.service_desk._enums import AssetStatus, AssetType

class Asset(Base):
    """Activo de IT (hardware o software) con lifecycle completo."""
    __tablename__ = "sd_assets"

    id          = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String(36), ForeignKey("organizations.id"), nullable=True, index=True)  # audit #7
    code        = Column(String(30), nullable=False)   # ASSET-0001 (unique per-tenant — ver __table_args__)
    name        = Column(String(255), nullable=False)
    asset_type  = Column(Enum(AssetType), nullable=False)
    status      = Column(Enum(AssetStatus), default=AssetStatus.in_stock, index=True)

    # Identificación física / software
    serial_number   = Column(String(100), nullable=True, index=True)
    model           = Column(String(255), nullable=True)
    manufacturer    = Column(String(100), nullable=True)
    part_number     = Column(String(100), nullable=True)

    # Licencias de software
    license_key     = Column(String(500), nullable=True)
    license_seats   = Column(Integer, nullable=True)          # número de licencias
    license_used    = Column(Integer, default=0)              # cuántas en uso

    # Fechas del ciclo de vida
    purchase_date   = Column(String(10), nullable=True)       # YYYY-MM-DD
    warranty_expiry = Column(String(10), nullable=True)
    eol_date        = Column(String(10), nullable=True)       # End of Life
    lease_expiry    = Column(String(10), nullable=True)

    # Financiero
    purchase_price  = Column(Float, nullable=True)
    current_value   = Column(Float, nullable=True)
    currency        = Column(String(3), default=settings.DEFAULT_CURRENCY)
    po_number       = Column(String(100), nullable=True)
    vendor          = Column(String(100), nullable=True)
    vendor_contract = Column(String(100), nullable=True)

    # Ubicación / Asignación
    location        = Column(String(255), nullable=True)
    assigned_user_id = Column(String(36), ForeignKey("users.id"), nullable=True, index=True)
    department      = Column(String(100), nullable=True)

    # Vínculo con CMDB
    ci_id           = Column(String(36), ForeignKey("sd_configuration_items.id"), nullable=True)

    # Metadatos
    tags            = Column(String(500), nullable=True)      # comma-separated
    notes           = Column(Text, nullable=True)
    managed_by_user_id = Column(String(36), ForeignKey("users.id"), nullable=True)

    # Phase 2 — Asset Lifecycle
    depreciation_type = Column(String(20), nullable=True)   # linear|declining|none
    depreciation_rate = Column(Float, nullable=True)        # annual % for declining balance
    next_maintenance_date = Column(String(10), nullable=True)  # YYYY-MM-DD
    maintenance_contract = Column(String(255), nullable=True)

    created_at  = Column(DateTime(timezone=True), server_default=func.now())
    updated_at  = Column(DateTime(timezone=True), onupdate=func.now())

    # audit #38: unique per-tenant
    __table_args__ = (
        UniqueConstraint("organization_id", "code", name="uq_sd_asset_code_per_org"),
    )

    assigned_user = relationship("User", foreign_keys=[assigned_user_id])
    managed_by    = relationship("User", foreign_keys=[managed_by_user_id])
    ci            = relationship("ConfigurationItem")
    history       = relationship("AssetHistory", back_populates="asset",
                                 cascade="all, delete-orphan", order_by="AssetHistory.changed_at")

class AssetHistory(Base):
    """Historial de cambios de un activo (asignación, estado, reparaciones...)."""
    __tablename__ = "sd_asset_history"

    id          = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String(36), ForeignKey("organizations.id"), nullable=True, index=True)  # audit #7
    asset_id    = Column(String(36), ForeignKey("sd_assets.id", ondelete="CASCADE"), nullable=False, index=True)
    field_name  = Column(String(100), nullable=False)    # status | assigned_user_id | location...
    old_value   = Column(String(500), nullable=True)
    new_value   = Column(String(500), nullable=True)
    changed_by  = Column(String(36), ForeignKey("users.id"), nullable=True)
    note        = Column(String(255), nullable=True)
    changed_at  = Column(DateTime(timezone=True), server_default=func.now())

    asset      = relationship("Asset", back_populates="history")
    changed_by_user = relationship("User", foreign_keys=[changed_by])
