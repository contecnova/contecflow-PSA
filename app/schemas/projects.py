from datetime import date, datetime
from typing import List, Literal, Optional

from pydantic import BaseModel, Field, model_validator

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


#: Modos de facturacion que ofrece el formulario (frontend/src/constants/constants.json,
#: BILLING_TYPES). `recurring_retainer` es el que factura app/worker.py cada mes.
BillingType = Literal["time_material", "fixed_price", "hourly_bag", "recurring_retainer", "retainer", "milestone"]


def _retainer_es_facturable(modelo):
    """Un retainer recurrente se factura por definicion: el worker
    (generate_retainer_invoices) solo mira proyectos con `is_billable`. Si el
    cliente no lo dice explicitamente, se marca facturable."""
    if modelo.billing_type == "recurring_retainer" and "is_billable" not in modelo.model_fields_set:
        modelo.is_billable = True
    return modelo


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
    # Auditoria 2026-11 (#25): el formulario de alta los mandaba y pydantic los descartaba.
    status: ProjectStatus = Field(default=ProjectStatus.planning, description="Estado inicial del proyecto")
    risk_level: ProjectRisk = Field(default=ProjectRisk.low, description="Nivel de riesgo inicial")
    billing_type: BillingType = Field(default="time_material", description="Modo de facturacion")
    retainer_amount: Optional[float] = Field(default=None, ge=0, description="Importe mensual del retainer recurrente")
    retainer_day: Optional[int] = Field(default=None, ge=1, le=28, description="Dia del mes en que se factura el retainer (1-28)")

    @model_validator(mode="after")
    def _retainer_facturable(self):
        return _retainer_es_facturable(self)


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
    # Auditoria 2026-11 (#25): sin ellos la facturacion recurrente no se podia configurar desde la UI.
    is_billable: Optional[bool] = Field(default=None, description="Indica si el proyecto es facturable")
    billing_type: Optional[BillingType] = Field(default=None, description="Modo de facturacion")
    retainer_amount: Optional[float] = Field(default=None, ge=0, description="Importe mensual del retainer recurrente")
    retainer_day: Optional[int] = Field(default=None, ge=1, le=28, description="Dia del mes en que se factura el retainer (1-28)")

    @model_validator(mode="after")
    def _retainer_facturable(self):
        return _retainer_es_facturable(self)


class ProjectOut(ProjectBase):
    id: str = Field(..., description="Identificador único del proyecto")
    code: str = Field(..., description="Código identificativo del proyecto")
    status: ProjectStatus = Field(..., description="Estado actual del proyecto")
    risk_level: ProjectRisk = Field(..., description="Nivel de riesgo del proyecto")
    pm_id: Optional[str] = Field(default=None, description="ID del project manager")
    client_id: Optional[str] = Field(default=None, description="ID del cliente")
    project_manager: Optional[UserPublic] = Field(default=None, description="Datos públicos del project manager")
    # Auditoria 2026-11 (#25): el detalle lo leia como en el listado (ProjectSummary).
    pm_name: Optional[str] = Field(default=None, description="Nombre del project manager")
    billing_type: Optional[str] = Field(default=None, description="Modo de facturacion")
    retainer_amount: Optional[float] = Field(default=None, description="Importe mensual del retainer recurrente")
    retainer_day: Optional[int] = Field(default=None, description="Dia del mes en que se factura el retainer")
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

    @model_validator(mode="after")
    def _nombre_del_pm(self):
        if self.pm_name is None and self.project_manager is not None:
            self.pm_name = self.project_manager.full_name
        return self


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
