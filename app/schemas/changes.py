from typing import Optional

from pydantic import BaseModel


class CRIn(BaseModel):
    title: str
    description: str
    justification: Optional[str] = None
    impact: str = "medium"
    cost_impact: Optional[float] = None
    schedule_impact_days: Optional[int] = None
    scope_impact: Optional[str] = None


class CRReview(BaseModel):
    approved: bool
    resolution_notes: Optional[str] = None


class ChangeRequestOut(BaseModel):
    id: str
    code: str
    project_id: str
    title: str
    description: str
    justification: Optional[str] = None
    impact: str
    impact_label: str = ""
    impact_color: str = "#7a8aaa"
    cost_impact: Optional[float] = None
    schedule_impact_days: Optional[int] = None
    scope_impact: Optional[str] = None
    status: str
    status_label: str = ""
    status_color: str = "#7a8aaa"
    requested_by: Optional[str] = None
