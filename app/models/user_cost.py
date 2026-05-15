"""
User cost models — versioned cost-per-hour calculation per person plus
country-level employer-cost presets.

Tables:
  country_employer_costs   — per-country defaults (SS empresa %, productive hours)
  user_cost_profiles       — versioned cost profile per user (valid_from/valid_to)

The cost-per-hour is derived:
   total_annual_cost = gross_annual_salary * (1 + employer_cost_pct) + extra_annual_costs
   cost_per_hour     = total_annual_cost / productive_hours_year
"""
from __future__ import annotations

import uuid

from sqlalchemy import Boolean, Column, Date, DateTime, Float, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.db.base import Base


class CountryEmployerCost(Base):
    """Per-country default values for employer cost calculations.

    The admin can override these per organisation via `organization_id`.
    A row with `organization_id = NULL` is a global default and acts as fallback.
    """
    __tablename__ = "country_employer_costs"
    __table_args__ = (
        UniqueConstraint("country_code", "organization_id", name="ux_country_org"),
    )

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String(36), ForeignKey("organizations.id", ondelete="CASCADE"),
                             nullable=True, index=True)
    country_code = Column(String(2), nullable=False, index=True)   # ISO-3166 alpha-2
    country_name = Column(String(80), nullable=False)
    currency = Column(String(3), nullable=False, default="EUR")    # default currency for that country
    employer_cost_pct = Column(Float, nullable=False, default=0.32)         # SS empresa + others
    productive_hours_year = Column(Float, nullable=False, default=1700)     # billable hrs/year
    notes = Column(Text, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    is_active = Column(Boolean, default=True, nullable=False, server_default="1", index=True)  # audit #36 soft-delete


class UserCostProfile(Base):
    """Versioned cost profile per user.

    A user can have many profiles over time (one per salary review or job change).
    The active profile on a given date is the one whose [valid_from, valid_to]
    interval contains it (valid_to NULL = open-ended).
    """
    __tablename__ = "user_cost_profiles"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"),
                     nullable=False, index=True)
    organization_id = Column(String(36), ForeignKey("organizations.id", ondelete="CASCADE"),
                             nullable=True, index=True)

    # Country drives the default employer cost % when creating the profile
    country_code = Column(String(2), nullable=True, index=True)
    currency = Column(String(3), nullable=False, default="EUR")

    # Inputs
    gross_annual_salary = Column(Float, nullable=False)              # salary in `currency`
    employer_cost_pct = Column(Float, nullable=False, default=0.32)  # 0.32 = 32%
    extra_annual_costs = Column(Float, nullable=False, default=0.0)  # bonus, gear, training prorated
    productive_hours_year = Column(Float, nullable=False, default=1700)

    # Derived (cached at write to avoid recomputing on every read)
    total_annual_cost = Column(Float, nullable=False)
    cost_per_hour = Column(Float, nullable=False)

    # Vigency
    valid_from = Column(Date, nullable=False, index=True)
    valid_to = Column(Date, nullable=True, index=True)               # NULL = current

    notes = Column(Text, nullable=True)

    created_by_user_id = Column(String(36), ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    is_active = Column(Boolean, default=True, nullable=False, server_default="1", index=True)  # audit #36 soft-delete

    user = relationship("User", foreign_keys=[user_id])
