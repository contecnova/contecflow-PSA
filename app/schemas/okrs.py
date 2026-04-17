from datetime import date
from typing import Optional

from pydantic import BaseModel


class ObjectiveIn(BaseModel):
    title: str
    description: Optional[str] = None
    owner_id: Optional[str] = None
    team_id: Optional[str] = None
    project_id: Optional[str] = None
    period: str = "Q1"
    year: int = 2025
    status: str = "draft"


class KeyResultIn(BaseModel):
    objective_id: str
    title: str
    kr_type: str = "percentage"
    target_value: float = 100
    current_value: float = 0
    unit: Optional[str] = None
    owner_id: Optional[str] = None
    due_date: Optional[date] = None
    notes: Optional[str] = None


class ObjectiveUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    owner_id: Optional[str] = None
    team_id: Optional[str] = None
    project_id: Optional[str] = None
    period: Optional[str] = None
    year: Optional[int] = None
    status: Optional[str] = None


class KeyResultUpdate(BaseModel):
    title: Optional[str] = None
    kr_type: Optional[str] = None
    target_value: Optional[float] = None
    current_value: Optional[float] = None
    unit: Optional[str] = None
    owner_id: Optional[str] = None
    due_date: Optional[date] = None
    notes: Optional[str] = None


class OKRCheckinIn(BaseModel):
    value: float
    note: Optional[str] = None
