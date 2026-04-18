from typing import Optional, List
from pydantic import BaseModel

class PermissionUpdate(BaseModel):
    allowed: bool

class SodRuleIn(BaseModel):
    module_a:    str
    action_a:    str
    module_b:    str
    action_b:    str
    risk:        str = "high"
    description: Optional[str] = None
    roles_conflict: List[str] = []
    mitigated_by_workflow_id: Optional[str] = None

class ViolationResolveIn(BaseModel):
    resolution_note: Optional[str] = None
