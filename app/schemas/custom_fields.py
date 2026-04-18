from typing import Optional, List
from pydantic import BaseModel

class CustomFieldIn(BaseModel):
    name: str
    field_key: str
    field_type: str  # text|number|date|select|url|user|boolean
    options: Optional[List[str]] = []
    is_required: bool = False
    show_in_list: bool = True
    sort_order: int = 0

class FieldValueIn(BaseModel):
    field_id: str
    value: Optional[str] = None

class WorkflowStateIn(BaseModel):
    name: str
    value: str
    color: str = "#7a8aaa"
    icon: Optional[str] = None
    is_initial: bool = False
    is_final: bool = False
    sort_order: int = 0

class TransitionIn(BaseModel):
    from_state_id: str
    to_state_id: str
    label: Optional[str] = None
    required_role: Optional[str] = None
    requires_comment: bool = False

class TaskTransitionIn(BaseModel):
    to_state_id: str
    comment: Optional[str] = None

class PermissionIn(BaseModel):
    user_id: str
    level: str = "member"  # none|viewer|member|manager|owner
    can_see_financials: bool = False
    can_see_rates: bool = False
    can_export: bool = True
