from datetime import date
from typing import Optional

from pydantic import BaseModel


class CapacityPlanIn(BaseModel):
    user_id: str
    project_id: Optional[str] = None
    week_start: date
    planned_hours: float
    notes: Optional[str] = None


class CapacityPlanOut(CapacityPlanIn):
    id: str
    user_name: Optional[str] = None
    project_name: Optional[str] = None
    project_code: Optional[str] = None
    model_config = {"from_attributes": True}
