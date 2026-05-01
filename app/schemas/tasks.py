from datetime import date, datetime
from typing import List, Optional

from pydantic import BaseModel, Field

from app.schemas.common_enums import TaskPriority, TaskStatus
from app.schemas.users import UserPublic


class TaskBase(BaseModel):
    title: str
    description: Optional[str] = None
    project_id: str
    phase_id: Optional[str] = None
    parent_task_id: Optional[str] = None
    assignee_id: Optional[str] = None
    status: TaskStatus = TaskStatus.todo
    priority: TaskPriority = TaskPriority.medium
    estimated_hours: Optional[float] = Field(None, gt=0, description="Horas estimadas (debe ser positivo)")
    story_points: Optional[int] = Field(None, gt=0, description="Story points (debe ser positivo)")
    start_date: Optional[date] = None
    due_date: Optional[date] = None


class TaskCreate(TaskBase):
    pass


class TaskUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    phase_id: Optional[str] = None
    assignee_id: Optional[str] = None
    status: Optional[TaskStatus] = None
    priority: Optional[TaskPriority] = None
    estimated_hours: Optional[float] = Field(None, gt=0, description="Horas estimadas (debe ser positivo)")
    due_date: Optional[date] = None
    blocked_reason: Optional[str] = None
    tags: Optional[str] = None
    move_reason: Optional[str] = Field(None, max_length=500, description="Motivo del movimiento (para trazabilidad)")


class BulkTaskUpdatePayload(BaseModel):
    task_ids: List[str] = Field(..., min_length=1, max_length=200)
    status: Optional[TaskStatus] = None
    assignee_id: Optional[str] = None
    priority: Optional[TaskPriority] = None


class TaskCommentCreate(BaseModel):
    content: str


class TaskCommentOut(BaseModel):
    id: str
    task_id: str
    author: Optional[UserPublic] = None
    content: str
    created_at: datetime

    class Config:
        from_attributes = True


class TaskOut(TaskBase):
    id: str
    code: str
    assignee: Optional[UserPublic] = None
    reporter: Optional[UserPublic] = None
    real_hours: float = 0
    efficiency_ratio: Optional[float] = None
    jira_issue_key: Optional[str] = None
    blocked_reason: Optional[str] = None
    comments: List[TaskCommentOut] = []
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class TaskMovementLogOut(BaseModel):
    id: str
    task_id: str
    project_id: str
    from_status: Optional[str] = None
    to_status: str
    reason: Optional[str] = None
    moved_at: datetime
    moved_by: Optional[UserPublic] = None

    class Config:
        from_attributes = True
