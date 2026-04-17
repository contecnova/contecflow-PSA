from typing import Optional

from pydantic import BaseModel, field_validator


class WorkflowIn(BaseModel):
    name: str
    description: Optional[str] = None
    entity_type: str
    is_default: bool = False
    trigger_conditions: Optional[str] = "{}"


class StepIn(BaseModel):
    step_order: int
    name: str
    approver_type: str
    approver_role: Optional[str] = None
    approver_user_id: Optional[str] = None
    approver_department: Optional[str] = None
    is_optional: bool = False
    timeout_hours: int = 72
    on_timeout: str = "escalate"
    escalate_to_user_id: Optional[str] = None

    @field_validator("approver_user_id", "escalate_to_user_id", mode="before")
    @classmethod
    def _empty_str_to_none(cls, v):
        return None if v == "" else v


class ApprovalRequestIn(BaseModel):
    workflow_id: Optional[str] = None
    entity_type: str
    entity_id: str
    entity_summary: Optional[str] = None


class DecisionIn(BaseModel):
    decision: str
    note: Optional[str] = None
    delegate_to: Optional[str] = None
