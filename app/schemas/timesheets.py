from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, field_validator


class TimesheetOut(BaseModel):
    id: str
    user_id: str
    week_start: date
    week_end: date
    status: str
    total_hours: float
    billable_hours: float
    total_cost: float
    submitted_at: Optional[date] = None
    reviewed_at: Optional[date] = None
    review_notes: Optional[str] = None
    user_name: Optional[str] = None
    reviewer_name: Optional[str] = None
    model_config = {"from_attributes": True}

    @field_validator("submitted_at", "reviewed_at", mode="before")
    @classmethod
    def coerce_datetime_to_date(cls, v):
        if isinstance(v, datetime):
            return v.date()
        return v


class TimesheetReview(BaseModel):
    approved: bool
    notes: Optional[str] = None


class ImputationLine(BaseModel):
    id: str
    date: date
    hours: float
    billable_hours: float
    cost: float
    project_name: str
    project_code: str
    description: Optional[str] = None
    is_billable: bool
    is_approved: bool


class TimesheetSendBackPayload(BaseModel):
    notes: str = ""
