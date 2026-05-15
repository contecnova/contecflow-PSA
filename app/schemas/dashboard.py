from datetime import date
from typing import List

from pydantic import BaseModel, Field


class DashboardKPIs(BaseModel):
    total_budget: float = Field(..., description="Presupuesto total agregado de todos los proyectos")
    total_spent: float = Field(..., description="Coste total gastado hasta la fecha")
    budget_used_pct: float = Field(..., description="Porcentaje de presupuesto consumido")
    projects_active: int = Field(..., description="Número de proyectos activos")
    projects_at_risk: int = Field(..., description="Proyectos en estado de riesgo")
    projects_over_budget: int = Field(..., description="Proyectos con sobrecoste")
    total_resources: int = Field(..., description="Total de recursos asignables")
    overloaded_resources: int = Field(..., description="Recursos con sobreasignación")
    avg_load_pct: float = Field(..., description="Porcentaje promedio de carga de los recursos")
    tasks_open: int = Field(..., description="Tareas abiertas en total")
    tasks_blocked: int = Field(..., description="Tareas bloqueadas")
    tasks_overdue: int = Field(..., description="Tareas con fecha vencida")
    avg_efficiency_ratio: float = Field(..., description="Ratio medio de eficiencia (estimadas/imputadas)")
    hours_logged_this_week: float = Field(..., description="Horas imputadas durante la semana actual")


class ProjectHealthItem(BaseModel):
    project_id: str = Field(..., description="ID del proyecto evaluado")
    project_name: str = Field(..., description="Nombre del proyecto")
    project_code: str = Field(..., description="Código identificativo del proyecto")
    budget_used_pct: float = Field(..., description="Porcentaje del presupuesto consumido")
    schedule_deviation_days: int = Field(..., description="Desviación de planning en días")
    risk_level: str = Field(..., description="Nivel de riesgo cualitativo (low, medium, high, critical)")
    status: str = Field(..., description="Estado actual del proyecto")
    team_size: int = Field(..., description="Tamaño del equipo asignado")
    alerts_count: int = Field(..., description="Número de alertas activas")
    tasks_total: int = Field(0, description="Tareas totales del proyecto")
    tasks_done: int = Field(0, description="Tareas finalizadas")
    progress_pct: float = Field(0.0, description="Porcentaje de avance global")
    health_score: int = Field(100, description="Puntuación global de salud (0-100)")


class ResourceLoadItem(BaseModel):
    user_id: str = Field(..., description="ID del usuario recurso")
    user_name: str = Field(..., description="Nombre del usuario")
    department: str = Field(..., description="Departamento del usuario")
    load_pct: float = Field(..., description="Porcentaje de carga sobre su capacidad")
    hours_week: float = Field(..., description="Horas asignadas en la semana")
    active_projects: int = Field(..., description="Número de proyectos activos asignados")
    efficiency: float = Field(..., description="Ratio de eficiencia del recurso")


class ProductivityStats(BaseModel):
    user_id: str = Field(..., description="ID del usuario evaluado")
    user_name: str = Field(..., description="Nombre del usuario")
    period_start: date = Field(..., description="Inicio del periodo analizado")
    period_end: date = Field(..., description="Fin del periodo analizado")
    total_hours_logged: float = Field(..., description="Horas imputadas en el periodo")
    total_hours_estimated: float = Field(..., description="Horas estimadas en el periodo")
    efficiency_ratio: float = Field(..., description="Ratio de eficiencia (estimadas/imputadas)")
    tasks_completed: int = Field(..., description="Tareas completadas en el periodo")
    tasks_total: int = Field(..., description="Tareas totales asignadas en el periodo")
    completion_rate: float = Field(..., description="Porcentaje de tareas completadas")
    by_project: List[dict] = Field(..., description="Desglose de productividad por proyecto")
