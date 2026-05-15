from typing import Optional, List
from pydantic import BaseModel, Field

class PermissionUpdate(BaseModel):
    allowed: bool = Field(..., description="Indica si el permiso queda concedido o revocado")

class SodRuleIn(BaseModel):
    module_a: str = Field(..., description="Módulo de la primera acción del conflicto SoD")
    action_a: str = Field(..., description="Acción del primer módulo en conflicto")
    module_b: str = Field(..., description="Módulo de la segunda acción del conflicto SoD")
    action_b: str = Field(..., description="Acción del segundo módulo en conflicto")
    risk: str = Field("high", description="Nivel de riesgo del conflicto (low, medium, high, critical)")
    description: Optional[str] = Field(None, description="Descripción del riesgo SoD")
    roles_conflict: List[str] = Field([], description="Roles que entran en conflicto bajo esta regla")
    mitigated_by_workflow_id: Optional[str] = Field(None, description="Workflow de aprobación que mitiga el riesgo")

class ViolationResolveIn(BaseModel):
    resolution_note: Optional[str] = Field(None, description="Nota explicativa de la resolución de la violación")
