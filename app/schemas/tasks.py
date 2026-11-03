from datetime import date, datetime
from typing import List, Optional

from pydantic import BaseModel, Field

from app.schemas.common_enums import TaskPriority, TaskStatus
from app.schemas.users import UserPublic


class TaskBase(BaseModel):
    title: str = Field(..., description="Título de la tarea")
    description: Optional[str] = Field(default=None, description="Descripción detallada de la tarea")
    project_id: str = Field(..., description="ID del proyecto al que pertenece la tarea")
    phase_id: Optional[str] = Field(default=None, description="ID de la fase del proyecto a la que pertenece la tarea")
    parent_task_id: Optional[str] = Field(default=None, description="ID de la tarea padre (para subtareas)")
    assignee_id: Optional[str] = Field(default=None, description="ID del usuario asignado a la tarea")
    status: TaskStatus = Field(default=TaskStatus.todo, description="Estado actual de la tarea")
    priority: TaskPriority = Field(default=TaskPriority.medium, description="Prioridad de la tarea")
    estimated_hours: Optional[float] = Field(None, gt=0, description="Horas estimadas (debe ser positivo)")
    story_points: Optional[int] = Field(None, gt=0, description="Story points (debe ser positivo)")
    start_date: Optional[date] = Field(default=None, description="Fecha de inicio planificada de la tarea")
    due_date: Optional[date] = Field(default=None, description="Fecha límite de la tarea")
    # Auditoria 2026-11: la columna existia y ningun esquema la exponia.
    issue_type: Optional[str] = Field(default=None, description="Tipo de incidencia (catalogo /issue-types del proyecto)")


class TaskCreate(TaskBase):
    pass


class TaskUpdate(BaseModel):
    title: Optional[str] = Field(default=None, description="Título de la tarea")
    description: Optional[str] = Field(default=None, description="Descripción detallada de la tarea")
    phase_id: Optional[str] = Field(default=None, description="ID de la fase del proyecto a la que pertenece la tarea")
    assignee_id: Optional[str] = Field(default=None, description="ID del usuario asignado a la tarea")
    status: Optional[TaskStatus] = Field(default=None, description="Estado actual de la tarea")
    priority: Optional[TaskPriority] = Field(default=None, description="Prioridad de la tarea")
    estimated_hours: Optional[float] = Field(None, gt=0, description="Horas estimadas (debe ser positivo)")
    due_date: Optional[date] = Field(default=None, description="Fecha límite de la tarea")
    blocked_reason: Optional[str] = Field(default=None, description="Motivo por el cual la tarea está bloqueada")
    tags: Optional[str] = Field(default=None, description="Etiquetas asociadas a la tarea")
    issue_type: Optional[str] = Field(default=None, description="Tipo de incidencia (catalogo /issue-types del proyecto)")
    move_reason: Optional[str] = Field(None, max_length=500, description="Motivo del movimiento (para trazabilidad)")


class BulkTaskUpdatePayload(BaseModel):
    task_ids: List[str] = Field(..., min_length=1, max_length=200, description="Lista de IDs de tareas a actualizar")
    status: Optional[TaskStatus] = Field(default=None, description="Nuevo estado a aplicar a las tareas")
    assignee_id: Optional[str] = Field(default=None, description="Nuevo asignado a aplicar a las tareas")
    priority: Optional[TaskPriority] = Field(default=None, description="Nueva prioridad a aplicar a las tareas")


class TaskCommentCreate(BaseModel):
    content: str = Field(..., description="Contenido del comentario")


class TaskCommentOut(BaseModel):
    id: str = Field(..., description="Identificador del comentario")
    task_id: str = Field(..., description="ID de la tarea asociada al comentario")
    author: Optional[UserPublic] = Field(default=None, description="Autor del comentario")
    content: str = Field(..., description="Contenido del comentario")
    created_at: datetime = Field(..., description="Fecha y hora de creación del comentario")

    class Config:
        from_attributes = True


class TaskOut(TaskBase):
    id: str = Field(..., description="Identificador de la tarea")
    code: str = Field(..., description="Código corto identificador de la tarea")
    assignee: Optional[UserPublic] = Field(default=None, description="Usuario asignado a la tarea")
    reporter: Optional[UserPublic] = Field(default=None, description="Usuario que creó la tarea")
    real_hours: float = Field(default=0, description="Horas reales registradas en la tarea")
    efficiency_ratio: Optional[float] = Field(default=None, description="Ratio de eficiencia (real vs estimado)")
    jira_issue_key: Optional[str] = Field(default=None, description="Clave del issue de Jira vinculado")
    blocked_reason: Optional[str] = Field(default=None, description="Motivo por el cual la tarea está bloqueada")
    comments: List[TaskCommentOut] = Field(default=[], description="Comentarios asociados a la tarea")
    created_at: datetime = Field(..., description="Fecha y hora de creación de la tarea")
    updated_at: Optional[datetime] = Field(default=None, description="Fecha y hora de última actualización")

    class Config:
        from_attributes = True


class TaskMovementLogOut(BaseModel):
    id: str = Field(..., description="Identificador del registro de movimiento")
    task_id: str = Field(..., description="ID de la tarea movida")
    project_id: str = Field(..., description="ID del proyecto al que pertenece la tarea")
    from_status: Optional[str] = Field(default=None, description="Estado de origen antes del movimiento")
    to_status: str = Field(..., description="Estado de destino tras el movimiento")
    reason: Optional[str] = Field(default=None, description="Motivo del movimiento")
    moved_at: datetime = Field(..., description="Fecha y hora del movimiento")
    moved_by: Optional[UserPublic] = Field(default=None, description="Usuario que realizó el movimiento")

    class Config:
        from_attributes = True
