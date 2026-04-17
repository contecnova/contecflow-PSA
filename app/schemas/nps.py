from typing import Optional

from pydantic import BaseModel, Field


class NPSCreate(BaseModel):
    score: int = Field(..., ge=0, le=10)
    comment: Optional[str] = None
    respondent: Optional[str] = None
    source: str = "manual"


class HealthSnapshotCreate(BaseModel):
    health_score: float = Field(..., ge=0, le=100)
    nps_component: Optional[float] = None
    delivery_component: Optional[float] = None
    budget_component: Optional[float] = None
    activity_component: Optional[float] = None
    note: Optional[str] = None
