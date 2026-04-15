from datetime import date, datetime
from typing import List, Optional

from pydantic import BaseModel, Field, field_validator

from app.schemas.projects import ProjectSummary
from app.schemas.tasks import TaskOut
from app.schemas.users import UserPublic


class ImputationCreate(BaseModel):
    task_id: Optional[str] = None
    project_id: str
    date: date
    hours: float = Field(..., gt=0, le=24)
    description: Optional[str] = None
    is_billable: bool = False

    @field_validator("hours")
    @classmethod
    def hours_precision(cls, v: float) -> float:
        return round(v * 2) / 2


class ImputationUpdate(BaseModel):
    hours: Optional[float] = Field(None, gt=0, le=24, description="Horas (debe ser positivo, max 24)")
    description: Optional[str] = None
    is_billable: Optional[bool] = None


class ImputationOut(BaseModel):
    id: str
    user: UserPublic
    task: Optional[TaskOut] = None
    project: Optional[ProjectSummary] = None
    date: date
    hours: float
    cost_amount: Optional[float] = None
    description: Optional[str] = None
    is_billable: bool
    is_approved: bool
    is_invoiced: bool = False
    invoiced_invoice_id: Optional[str] = None
    timer_session_id: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True


class WeekSummary(BaseModel):
    user_id: str
    week_start: date
    week_end: date
    total_hours: float
    capacity_hours: float
    load_pct: float
    by_project: List[dict]
    by_day: List[dict]
