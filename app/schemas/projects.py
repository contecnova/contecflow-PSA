from datetime import date, datetime
from typing import List, Optional

from pydantic import BaseModel, Field

from app.schemas.common_enums import ProjectRisk, ProjectStatus, ProjectType
from app.schemas.users import UserPublic


class ProjectPhaseBase(BaseModel):
    name: str = Field(..., description="Nombre de la fase del proyecto")
    description: Optional[str] = Field(default=None, description="Descripción de la fase")
    order: int = Field(default=0, description="Orden de la fase dentro del proyecto")
    budget_hours: Optional[float] = Field(default=None, description="Horas presupuestadas para la fase")
    start_date: Optional[date] = Field(default=None, description="Fecha de inicio planificada")
    end_date: Optional[date] = Field(default=None, description="Fecha de fin planificada")
    status: ProjectStatus = Field(default=ProjectStatus.planning, description="Estado actual de la fase")


class ProjectPhaseCreate(ProjectPhaseBase):
    pass


class ProjectPhaseOut(ProjectPhaseBase):
    id: str = Field(..., description="Identificador único de la fase")
    project_id: str = Field(..., description="ID del proyecto al que pertenece la fase")
    created_at: datetime = Field(..., description="Fecha de creación de la fase")

    class Config:
        from_attributes = True


class ProjectBase(BaseModel):
    name: str = Field(..., description="Nombre del proyecto")
    code: Optional[str] = Field(default=None, description="Código identificativo del proyecto")
    description: Optional[str] = Field(default=None, description="Descripción del proyecto")
    project_type: ProjectType = Field(default=ProjectType.internal, description="Tipo de proyecto")
    client_name: Optional[str] = Field(default=None, description="Nombre del cliente")
    client_id: Optional[str] = Field(default=None, description="ID del cliente asociado")
    department: Optional[str] = Field(default=None, description="Departamento responsable")
    is_billable: bool = Field(default=False, description="Indica si el proyecto es facturable")
    billing_rate: Optional[float] = Field(default=None, description="Tarifa horaria de facturación")
    budget_hours: Optional[float] = Field(default=None, description="Horas presupuestadas")
    budget_amount: Optional[float] = Field(default=None, description="Importe presupuestado en euros")
    start_date: Optional[date] = Field(default=None, description="Fecha de inicio del proyecto")
    end_date_planned: Optional[date] = Field(default=None, description="Fecha de fin planificada")
    tags: Optional[str] = Field(default=None, description="Etiquetas separadas por comas")
    jira_project_key: Optional[str] = Field(default=None, description="Clave del proyecto en Jira")


class ProjectCreate(ProjectBase):
    pm_id: Optional[str] = Field(default=None, description="ID del project manager asignado")
    phases: Optional[List[ProjectPhaseCreate]] = Field(default=[], description="Lista de fases del proyecto")


class ProjectUpdate(BaseModel):
    name: Optional[str] = Field(default=None, description="Nombre del proyecto")
    description: Optional[str] = Field(default=None, description="Descripción del proyecto")
    project_type: Optional[ProjectType] = Field(default=None, description="Tipo de proyecto")
    status: Optional[ProjectStatus] = Field(default=None, description="Estado del proyecto")
    risk_level: Optional[ProjectRisk] = Field(default=None, description="Nivel de riesgo del proyecto")
    pm_id: Optional[str] = Field(default=None, description="ID del project manager")
    client_name: Optional[str] = Field(default=None, description="Nombre del cliente")
    client_id: Optional[str] = Field(default=None, description="ID del cliente")
    department: Optional[str] = Field(default=None, description="Departamento responsable")
    budget_hours: Optional[float] = Field(default=None, description="Horas presupuestadas")
    budget_amount: Optional[float] = Field(default=None, description="Importe presupuestado en euros")
    billing_rate: Optional[float] = Field(default=None, description="Tarifa horaria de facturación")
    start_date: Optional[date] = Field(default=None, description="Fecha de inicio del proyecto")
    end_date_planned: Optional[date] = Field(default=None, description="Fecha de fin planificada")
    end_date_real: Optional[date] = Field(default=None, description="Fecha de fin real")
    tags: Optional[str] = Field(default=None, description="Etiquetas separadas por comas")
    jira_project_key: Optional[str] = Field(default=None, description="Clave del proyecto en Jira")


class ProjectOut(ProjectBase):
    id: str = Field(..., description="Identificador único del proyecto")
    code: str = Field(..., description="Código identificativo del proyecto")
    status: ProjectStatus = Field(..., description="Estado actual del proyecto")
    risk_level: ProjectRisk = Field(..., description="Nivel de riesgo del proyecto")
    pm_id: Optional[str] = Field(default=None, description="ID del project manager")
    client_id: Optional[str] = Field(default=None, description="ID del cliente")
    project_manager: Optional[UserPublic] = Field(default=None, description="Datos públicos del project manager")
    phases: List[ProjectPhaseOut] = Field(default=[], description="Lista de fases del proyecto")
    created_at: datetime = Field(..., description="Fecha de creación del proyecto")
    total_hours_spent: Optional[float] = Field(default=None, description="Total de horas imputadas")
    total_cost_spent: Optional[float] = Field(default=None, description="Coste total imputado")
    budget_used_pct: Optional[float] = Field(default=None, description="Porcentaje de presupuesto consumido")
    progress_pct: Optional[float] = Field(default=None, description="Porcentaje de avance del proyecto")
    team_size: int = Field(default=0, description="Tamaño del equipo asignado")
    tasks_total: int = Field(default=0, description="Total de tareas del proyecto")
    tasks_done: int = Field(default=0, description="Total de tareas completadas")

    class Config:
        from_attributes = True


class ProjectSummary(BaseModel):
    id: str = Field(..., description="Identificador único del proyecto")
    code: str = Field(..., description="Código identificativo del proyecto")
    name: str = Field(..., description="Nombre del proyecto")
    project_type: ProjectType = Field(..., description="Tipo de proyecto")
    status: ProjectStatus = Field(..., description="Estado actual del proyecto")
    risk_level: ProjectRisk = Field(..., description="Nivel de riesgo del proyecto")
    pm_name: Optional[str] = Field(default=None, description="Nombre del project manager")
    client_name: Optional[str] = Field(default=None, description="Nombre del cliente")
    department: Optional[str] = Field(default=None, description="Departamento responsable")
    budget_amount: Optional[float] = Field(default=None, description="Importe presupuestado en euros")
    total_cost_spent: Optional[float] = Field(default=0, description="Coste total imputado")
    budget_used_pct: Optional[float] = Field(default=0, description="Porcentaje de presupuesto consumido")
    progress_pct: Optional[float] = Field(default=0, description="Porcentaje de avance del proyecto")
    team_size: int = Field(default=0, description="Tamaño del equipo asignado")
    start_date: Optional[date] = Field(default=None, description="Fecha de inicio del proyecto")
    end_date_planned: Optional[date] = Field(default=None, description="Fecha de fin planificada")
