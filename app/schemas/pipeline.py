from datetime import date
from typing import Optional

from pydantic import BaseModel


class OpportunityIn(BaseModel):
    name: str
    client_name: str
    stage: str = "lead"
    probability: float = 50
    expected_revenue: Optional[float] = None
    expected_margin_pct: Optional[float] = None
    expected_hours: Optional[float] = None
    expected_close_date: Optional[date] = None
    expected_start_date: Optional[date] = None
    expected_duration_weeks: Optional[int] = None
    description: Optional[str] = None
    contact_name: Optional[str] = None
    contact_email: Optional[str] = None
    owner_id: Optional[str] = None
    notes: Optional[str] = None


class OpportunityUpdate(OpportunityIn):
    name: Optional[str] = None
    client_name: Optional[str] = None
    lost_reason: Optional[str] = None
    project_id: Optional[str] = None


class PipelineActivityIn(BaseModel):
    type: str = "note"
    content: str


class StageConfigIn(BaseModel):
    stage_key: str
    label: str
    description: Optional[str] = None
    color: str = "#6B7280"
    order: int = 0
    probability_default: float = 50
    is_terminal: bool = False
    is_won: bool = False
