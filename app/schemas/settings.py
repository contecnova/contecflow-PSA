from datetime import date as date_type
from typing import Optional

from pydantic import BaseModel, Field


class SettingOut(BaseModel):
    key: str = Field(..., description="Clave identificativa del ajuste")
    value: Optional[str] = Field(None, description="Valor actual del ajuste")
    description: Optional[str] = Field(None, description="Descripción del ajuste")
    model_config = {"from_attributes": True}


class SettingUpdate(BaseModel):
    value: str = Field(..., description="Nuevo valor a asignar al ajuste")


class ProjectTypeIn(BaseModel):
    value: str = Field(..., description="Clave técnica del tipo de proyecto")
    label: str = Field(..., description="Etiqueta visible del tipo de proyecto")
    color: str = Field("#7a8aaa", description="Color asociado en hexadecimal")
    sort_order: int = Field(0, description="Orden de visualización del tipo")


class ProjectTypeOut(ProjectTypeIn):
    id: str
    is_active: bool = Field(..., description="Indica si el tipo está activo")
    model_config = {"from_attributes": True}


class ProjectStatusIn(BaseModel):
    value: str = Field(..., description="Clave técnica del estado de proyecto")
    label: str = Field(..., description="Etiqueta visible del estado")
    color: str = Field("#7a8aaa", description="Color asociado en hexadecimal")
    is_default: bool = Field(False, description="Indica si es el estado por defecto")
    sort_order: int = Field(0, description="Orden de visualización del estado")


class ProjectStatusOut(ProjectStatusIn):
    id: str
    is_active: bool = Field(..., description="Indica si el estado está activo")
    model_config = {"from_attributes": True}


class TaskStatusIn(BaseModel):
    value: str = Field(..., description="Clave técnica del estado de tarea")
    label: str = Field(..., description="Etiqueta visible del estado")
    color: str = Field("#7a8aaa", description="Color asociado en hexadecimal")
    is_default: bool = Field(False, description="Indica si es el estado por defecto")
    sort_order: int = Field(0, description="Orden de visualización del estado")


class TaskStatusOut(TaskStatusIn):
    id: str
    is_active: bool = Field(..., description="Indica si el estado está activo")
    model_config = {"from_attributes": True}


class DepartmentIn(BaseModel):
    name: str = Field(..., description="Nombre del departamento")
    description: Optional[str] = Field(None, description="Descripción del departamento")
    manager_id: Optional[str] = Field(None, description="ID del manager responsable")


class DepartmentOut(DepartmentIn):
    id: str
    is_active: bool = Field(..., description="Indica si el departamento está activo")
    model_config = {"from_attributes": True}


class HolidayIn(BaseModel):
    name: str = Field(..., description="Nombre del festivo")
    date: date_type = Field(..., description="Fecha del festivo")
    type: str = Field("public", description="Tipo de festivo (public, regional, company)")
    applies_to: Optional[str] = Field(None, description="Ámbito al que aplica (organización, departamento, etc.)")


class HolidayOut(HolidayIn):
    id: str
    model_config = {"from_attributes": True}


class LogLevelPayload(BaseModel):
    level: str = Field(..., description="Nuevo nivel de log (DEBUG, INFO, WARNING, ERROR)")
    logger: Optional[str] = Field(None, description="Nombre del logger específico al que aplicar el nivel")
