from datetime import date
from typing import Optional

from pydantic import BaseModel


class MilestoneIn(BaseModel):
    name: str
    description: Optional[str] = None
    due_date: Optional[date] = None
    billing_amount: Optional[float] = None
    billing_pct: Optional[float] = None
    sort_order: int = 0


class MilestoneOut(MilestoneIn):
    id: str
    project_id: str
    is_completed: bool
    completed_date: Optional[date] = None
    is_billed: bool
    billed_at: Optional[date] = None
    model_config = {"from_attributes": True}


class MilestoneUpdate(BaseModel):
    is_completed: Optional[bool] = None
    completed_date: Optional[date] = None
    is_billed: Optional[bool] = None
    billed_at: Optional[date] = None
    name: Optional[str] = None
    due_date: Optional[date] = None
    billing_amount: Optional[float] = None


class MilestoneApprovalRequestIn(BaseModel):
    message: Optional[str] = None


class MilestoneApprovalDecisionIn(BaseModel):
    approved: bool
    rejection_reason: Optional[str] = None
