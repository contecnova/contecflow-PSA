from typing import Optional, Any

from pydantic import BaseModel, field_validator


class WorkflowIn(BaseModel):
    name: str
    description: Optional[str] = None
    entity_type: str
    is_default: bool = False
    trigger_conditions: Optional[str] = "{}"
    # v2 enterprise
    chain_on_approval_workflow_id: Optional[str] = None
    sla_block_on_breach: bool = False
    auto_approval_rules: Optional[str] = None


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
    # v2 enterprise
    approver_group_id: Optional[str] = None
    parallel_quorum: bool = False
    required_approvals: int = 1
    step_condition: Optional[str] = None
    requires_attachment: bool = False
    reminder_hours: Optional[int] = None

    @field_validator("approver_user_id", "escalate_to_user_id", "approver_group_id", mode="before")
    @classmethod
    def _empty_str_to_none(cls, v):
        return None if v == "" else v


class ApprovalRequestIn(BaseModel):
    workflow_id: Optional[str] = None
    entity_type: str
    entity_id: str
    entity_summary: Optional[str] = None
    context: Optional[Any] = None


class DecisionIn(BaseModel):
    decision: str
    note: Optional[str] = None
    delegate_to: Optional[str] = None
    attachment_url: Optional[str] = None
