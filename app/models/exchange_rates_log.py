"""
Currency conversion audit log — tracks all FX conversions applied to financial records.
The ExchangeRate model itself is defined in app/models/bookings.py.
"""
from sqlalchemy import Column, String, Float, DateTime, Date, ForeignKey
from sqlalchemy.sql import func
import uuid
from app.db.base import Base


class CurrencyConversionLog(Base):
    """Audit log of currency conversions applied to financial transactions."""
    __tablename__ = "currency_conversion_logs"

    id              = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String(36), ForeignKey("organizations.id"), nullable=True, index=True)  # audit #7
    entity_type     = Column(String(50), nullable=False)  # expense | invoice | budget
    entity_id       = Column(String(36), nullable=False)
    from_currency   = Column(String(3), nullable=False)
    to_currency     = Column(String(3), nullable=False)
    original_amount = Column(Float, nullable=False)
    converted_amount = Column(Float, nullable=False)
    rate_used       = Column(Float, nullable=False)
    rate_date       = Column(Date, nullable=False)
    created_at      = Column(DateTime(timezone=True), server_default=func.now())
