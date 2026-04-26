from datetime import date, datetime
from typing import List, Optional

from pydantic import BaseModel

from app.schemas.common_enums import ProjectRisk, ProjectStatus, ProjectType
from app.schemas.users import UserPublic


class ProjectPhaseBase(BaseModel):
    name: str
    description: Optional[str] = None
    order: int = 0
    budget_hours: Optional[float] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    status: ProjectStatus = ProjectStatus.planning


class ProjectPhaseCreate(ProjectPhaseBase):
    pass


class ProjectPhaseOut(ProjectPhaseBase):
    id: str
    project_id: str
    created_at: datetime

    class Config:
        from_attributes = True


class ProjectBase(BaseModel):
    name: str
    code: Optional[str] = None
    description: Optional[str] = None
    project_type: ProjectType = ProjectType.internal
    client_name: Optional[str] = None
    client_id: Optional[str] = None
    department: Optional[str] = None
    is_billable: bool = False
    billing_rate: Optional[float] = None
    budget_hours: Optional[float] = None
    budget_amount: Optional[float] = None
    start_date: Optional[date] = None
    end_date_planned: Optional[date] = None
    tags: Optional[str] = None
    jira_project_key: Optional[str] = None


class ProjectCreate(ProjectBase):
    pm_id: Optional[str] = None
    phases: Optional[List[ProjectPhaseCreate]] = []


class ProjectUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    project_type: Optional[ProjectType] = None
    status: Optional[ProjectStatus] = None
    risk_level: Optional[ProjectRisk] = None
    pm_id: Optional[str] = None
    client_name: Optional[str] = None
    client_id: Optional[str] = None
    department: Optional[str] = None
    budget_hours: Optional[float] = None
    budget_amount: Optional[float] = None
    billing_rate: Optional[float] = None
    start_date: Optional[date] = None
    end_date_planned: Optional[date] = None
    end_date_real: Optional[date] = None
    tags: Optional[str] = None
    jira_project_key: Optional[str] = None


class ProjectOut(ProjectBase):
    id: str
    code: str
    status: ProjectStatus
    risk_level: ProjectRisk
    pm_id: Optional[str] = None
    client_id: Optional[str] = None
    project_manager: Optional[UserPublic] = None
    phases: List[ProjectPhaseOut] = []
    created_at: datetime
    total_hours_spent: Optional[float] = None
    total_cost_spent: Optional[float] = None
    budget_used_pct: Optional[float] = None
    progress_pct: Optional[float] = None
    team_size: int = 0
    tasks_total: int = 0
    tasks_done: int = 0

    class Config:
        from_attributes = True


class ProjectSummary(BaseModel):
    id: str
    code: str
    name: str
    project_type: ProjectType
    status: ProjectStatus
    risk_level: ProjectRisk
    pm_name: Optional[str] = None
    client_name: Optional[str] = None
    department: Optional[str] = None
    budget_amount: Optional[float] = None
    total_cost_spent: Optional[float] = 0
    budget_used_pct: Optional[float] = 0
    progress_pct: Optional[float] = 0
    team_size: int = 0
    start_date: Optional[date] = None
    end_date_planned: Optional[date] = None
