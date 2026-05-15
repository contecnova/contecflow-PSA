from datetime import date
from typing import List, Optional

from pydantic import BaseModel, Field


class SprintCreate(BaseModel):
    name: str = Field(..., description="Nombre del sprint")
    goal: Optional[str] = Field(default=None, description="Objetivo del sprint")
    start_date: Optional[date] = Field(default=None, description="Fecha de inicio del sprint")
    end_date: Optional[date] = Field(default=None, description="Fecha de fin del sprint")


class SprintUpdate(BaseModel):
    name: Optional[str] = Field(default=None, description="Nombre del sprint")
    goal: Optional[str] = Field(default=None, description="Objetivo del sprint")
    start_date: Optional[date] = Field(default=None, description="Fecha de inicio del sprint")
    end_date: Optional[date] = Field(default=None, description="Fecha de fin del sprint")
    status: Optional[str] = Field(default=None, description="Estado del sprint")
    went_well: Optional[str] = Field(default=None, description="Aspectos positivos identificados en la retrospectiva")
    to_improve: Optional[str] = Field(default=None, description="Aspectos a mejorar identificados en la retrospectiva")
    action_items: Optional[str] = Field(default=None, description="Acciones acordadas en la retrospectiva")


class AddTasksToSprint(BaseModel):
    task_ids: List[str] = Field(..., description="Lista de IDs de tareas a añadir al sprint")


class ReorderBacklog(BaseModel):
    task_ids: List[str] = Field(..., description="Lista de IDs de tareas en el orden deseado del backlog")
