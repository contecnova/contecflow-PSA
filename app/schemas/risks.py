from datetime import date
from typing import Optional

from pydantic import BaseModel


class RiskIn(BaseModel):
    title: str
    description: Optional[str] = None
    category: Optional[str] = None
    probability: str
    impact: str
    status: str = "identified"
    mitigation_plan: Optional[str] = None
    contingency_plan: Optional[str] = None
    response_type: Optional[str] = None
    owner_id: Optional[str] = None
    review_date: Optional[date] = None
    cost_impact_min: Optional[float] = None
    cost_impact_max: Optional[float] = None
    schedule_impact_days: Optional[int] = None
    notes: Optional[str] = None


class RiskUpdate(RiskIn):
    title: Optional[str] = None
    probability: Optional[str] = None
    impact: Optional[str] = None
    closed_date: Optional[date] = None
