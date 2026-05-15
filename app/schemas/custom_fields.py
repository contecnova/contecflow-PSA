from typing import Optional, List
from pydantic import BaseModel, Field

class CustomFieldIn(BaseModel):
    name: str = Field(..., description="Nombre visible del campo personalizado")
    field_key: str = Field(..., description="Clave técnica del campo (slug)")
    field_type: str = Field(..., description="Tipo de campo (text, number, date, select, url, user, boolean)")
    options: Optional[List[str]] = Field([], description="Lista de opciones para campos tipo select")
    is_required: bool = Field(False, description="Indica si el campo es obligatorio")
    show_in_list: bool = Field(True, description="Indica si se muestra en vistas de lista")
    sort_order: int = Field(0, description="Orden de visualización del campo")

class FieldValueIn(BaseModel):
    field_id: str = Field(..., description="ID del campo personalizado")
    value: Optional[str] = Field(None, description="Valor asignado al campo (serializado como string)")

class WorkflowStateIn(BaseModel):
    name: str = Field(..., description="Nombre visible del estado del workflow")
    value: str = Field(..., description="Valor técnico del estado")
    color: str = Field("#7a8aaa", description="Color del estado en formato hexadecimal")
    icon: Optional[str] = Field(None, description="Icono asociado al estado")
    is_initial: bool = Field(False, description="Indica si es el estado inicial del workflow")
    is_final: bool = Field(False, description="Indica si es un estado final del workflow")
    sort_order: int = Field(0, description="Orden de visualización del estado")

class TransitionIn(BaseModel):
    from_state_id: str = Field(..., description="ID del estado origen")
    to_state_id: str = Field(..., description="ID del estado destino")
    label: Optional[str] = Field(None, description="Etiqueta visible de la transición")
    required_role: Optional[str] = Field(None, description="Rol requerido para ejecutar la transición")
    requires_comment: bool = Field(False, description="Indica si la transición exige un comentario")

class TaskTransitionIn(BaseModel):
    to_state_id: str = Field(..., description="ID del estado destino al que mover la tarea")
    comment: Optional[str] = Field(None, description="Comentario opcional de la transición")

class PermissionIn(BaseModel):
    user_id: str = Field(..., description="ID del usuario al que se otorga el permiso")
    level: str = Field("member", description="Nivel de permiso (none, viewer, member, manager, owner)")
    can_see_financials: bool = Field(False, description="Permiso para ver datos financieros")
    can_see_rates: bool = Field(False, description="Permiso para ver tarifas")
    can_export: bool = Field(True, description="Permiso para exportar datos")
