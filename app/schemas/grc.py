from typing import Literal, Optional, List
from pydantic import BaseModel, Field

#: Niveles de riesgo de una regla SoD. Revisión GRC 16-11-2026: era texto libre
#: y la pantalla pintaba color y nombre sólo para estos cuatro.
NivelDeRiesgo = Literal["critical", "high", "medium", "low"]


class PermissionUpdate(BaseModel):
    allowed: bool = Field(..., description="Indica si el permiso queda concedido o revocado")


class SodRuleIn(BaseModel):
    module_a: str = Field(..., min_length=1, max_length=80, description="Módulo de la primera acción del conflicto SoD")
    action_a: str = Field(..., min_length=1, max_length=30, description="Acción del primer módulo en conflicto")
    module_b: str = Field(..., min_length=1, max_length=80, description="Módulo de la segunda acción del conflicto SoD")
    action_b: str = Field(..., min_length=1, max_length=30, description="Acción del segundo módulo en conflicto")
    risk: NivelDeRiesgo = Field("high", description="Nivel de riesgo del conflicto (low, medium, high, critical)")
    description: Optional[str] = Field(None, max_length=2000, description="Descripción del riesgo SoD")
    roles_conflict: List[str] = Field([], max_length=20, description="Roles que entran en conflicto bajo esta regla")
    mitigated_by_workflow_id: Optional[str] = Field(None, max_length=36,
                                                    description="Workflow de aprobación que mitiga el riesgo")


class SodRuleUpdate(BaseModel):
    """PATCH de una regla SoD: sólo los campos enviados.

    Revisión GRC 16-11-2026: era un `dict` sin validar (cualquier `risk`, un
    `is_active` de cualquier tipo) y los módulos y acciones se ignoraban en
    silencio aunque la pantalla de edición dejaba cambiarlos.
    """
    module_a: Optional[str] = Field(None, min_length=1, max_length=80)
    action_a: Optional[str] = Field(None, min_length=1, max_length=30)
    module_b: Optional[str] = Field(None, min_length=1, max_length=80)
    action_b: Optional[str] = Field(None, min_length=1, max_length=30)
    risk: Optional[NivelDeRiesgo] = None
    description: Optional[str] = Field(None, max_length=2000)
    is_active: Optional[bool] = None
    roles_conflict: Optional[List[str]] = Field(None, max_length=20)
    mitigated_by_workflow_id: Optional[str] = Field(None, max_length=36)


class ViolationResolveIn(BaseModel):
    resolution_note: Optional[str] = Field(None, max_length=2000,
                                           description="Nota explicativa de la resolución de la violación")
