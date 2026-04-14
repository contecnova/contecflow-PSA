from pydantic import BaseModel, EmailStr, Field, validator
from typing import Optional, List
from datetime import datetime, date
from enum import Enum


# ── Enums (mirroring models) ──────────────────────────────────────────────────

class UserRole(str, Enum):
    admin = "admin"
    pm = "pm"
    team_lead = "team_lead"
    hr = "hr"
    employee = "employee"
    subcontractor = "subcontractor"

class UserStatus(str, Enum):
    active = "active"
    inactive = "inactive"
    vacation = "vacation"
    leave = "leave"

class ProjectType(str, Enum):
    development = "development"
    maintenance = "maintenance"
    rd = "rd"
    internal = "internal"
    consulting = "consulting"

class ProjectStatus(str, Enum):
    planning  = "planning"
    active    = "active"
    on_hold   = "on_hold"
    paused    = "paused"
    completed = "completed"
    closed    = "closed"
    cancelled = "cancelled"
    archived  = "archived"

class ProjectRisk(str, Enum):
    low = "low"
    medium = "medium"
    high = "high"
    critical = "critical"

class TaskStatus(str, Enum):
    backlog = "backlog"
    todo = "todo"
    in_progress = "in_progress"
    blocked = "blocked"
    in_review = "in_review"
    review = "review"
    done = "done"
    cancelled = "cancelled"

class TaskPriority(str, Enum):
    critical = "critical"
    high = "high"
    medium = "medium"
    low = "low"


# ── Auth ──────────────────────────────────────────────────────────────────────

class LoginRequest(BaseModel):
    username: str
    password: str

class TokenResponse(BaseModel):
    access_token: Optional[str] = None
    refresh_token: Optional[str] = None
    token_type: str = "bearer"
    user: "UserPublic"
    mfa_required: bool = False
    mfa_challenge_token: Optional[str] = None
    mfa_methods: Optional[list[str]] = None

class RefreshRequest(BaseModel):
    refresh_token: str


class ActiveSessionOut(BaseModel):
    id: str
    ip_address: Optional[str] = None
    ip_asn: Optional[str] = None
    ip_org: Optional[str] = None
    country_code: Optional[str] = None
    region: Optional[str] = None
    city: Optional[str] = None
    user_agent: Optional[str] = None
    device_name: Optional[str] = None
    risk_score: int = 0
    risk_level: str = "low"
    risk_reasons: List[str] = Field(default_factory=list)
    auth_method: Optional[str] = None
    last_seen_at: Optional[datetime] = None
    expires_at: datetime
    created_at: Optional[datetime] = None
    is_current: bool = False


# ── User ──────────────────────────────────────────────────────────────────────

class UserBase(BaseModel):
    username: str
    email: EmailStr
    full_name: str
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    department: Optional[str] = None
    job_title: Optional[str] = None
    role: UserRole = UserRole.employee
    status: UserStatus = UserStatus.active
    weekly_capacity_hours: float = 40.0

class UserCreate(UserBase):
    password: Optional[str] = None  # Optional for LDAP users

class UserUpdate(BaseModel):
    full_name: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    department: Optional[str] = None
    job_title: Optional[str] = None
    role: Optional[UserRole] = None
    status: Optional[UserStatus] = None
    weekly_capacity_hours: Optional[float] = None
    hourly_rate: Optional[float] = None  # Only admin can set this
    phone: Optional[str] = None
    avatar_url: Optional[str] = None
    manager_id: Optional[str] = None
    timezone: Optional[str] = None

class UserSelfUpdate(BaseModel):
    """Campos que el propio usuario puede editar (sin privilegios)."""
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    full_name: Optional[str] = None
    phone: Optional[str] = None
    job_title: Optional[str] = None
    avatar_url: Optional[str] = None
    timezone: Optional[str] = None

class UserPublic(UserBase):
    id: str
    is_active: bool = True
    avatar_url: Optional[str] = None
    last_login: Optional[datetime] = None
    created_at: datetime
    manager_id: Optional[str] = None
    manager_name: Optional[str] = None
    phone: Optional[str] = None

    class Config:
        from_attributes = True

class UserWithRate(UserPublic):
    """Extended view for admin/hr — includes confidential rate."""
    hourly_rate: Optional[float] = None
    ldap_dn: Optional[str] = None

class UserLoad(BaseModel):
    user: UserPublic
    current_load_pct: float
    hours_this_week: float
    hours_this_month: float
    active_tasks: int
    active_projects: int


# ── Project ───────────────────────────────────────────────────────────────────

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
    client_id:   Optional[str] = None
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
    client_id:   Optional[str] = None
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
    # Computed
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


# ── Task ──────────────────────────────────────────────────────────────────────

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


# ── Imputation ────────────────────────────────────────────────────────────────

class ImputationCreate(BaseModel):
    task_id: Optional[str] = None
    project_id: str
    date: date
    hours: float = Field(..., gt=0, le=24)
    description: Optional[str] = None
    is_billable: bool = False

    @validator("hours")
    def hours_precision(cls, v):
        return round(v * 2) / 2  # Round to nearest 0.5h

class ImputationUpdate(BaseModel):
    hours: Optional[float] = Field(None, gt=0, le=24, description="Horas (debe ser positivo, máx 24)")
    description: Optional[str] = None
    is_billable: Optional[bool] = None

class ImputationOut(BaseModel):
    id: str
    user: UserPublic
    task: Optional[TaskOut] = None
    project: Optional[ProjectSummary] = None
    date: date
    hours: float
    cost_amount: Optional[float] = None
    description: Optional[str] = None
    is_billable: bool
    is_approved: bool
    timer_session_id: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True

class WeekSummary(BaseModel):
    user_id: str
    week_start: date
    week_end: date
    total_hours: float
    capacity_hours: float
    load_pct: float
    by_project: List[dict]
    by_day: List[dict]


# ── Dashboard / Analytics ─────────────────────────────────────────────────────

class DashboardKPIs(BaseModel):
    # Budget
    total_budget: float
    total_spent: float
    budget_used_pct: float
    # Projects
    projects_active: int
    projects_at_risk: int
    projects_over_budget: int
    # Resources
    total_resources: int
    overloaded_resources: int
    avg_load_pct: float
    # Tasks
    tasks_blocked: int
    tasks_overdue: int
    # Efficiency
    avg_efficiency_ratio: float
    hours_logged_this_week: float

class ProjectHealthItem(BaseModel):
    project_id: str
    project_name: str
    project_code: str
    budget_used_pct: float
    schedule_deviation_days: int
    risk_level: str
    status: str
    team_size: int
    alerts_count: int
    tasks_total: int = 0
    tasks_done: int = 0
    progress_pct: float = 0.0
    health_score: int = 100

class ResourceLoadItem(BaseModel):
    user_id: str
    user_name: str
    department: str
    load_pct: float
    hours_week: float
    active_projects: int
    efficiency: float

class ProductivityStats(BaseModel):
    user_id: str
    user_name: str
    period_start: date
    period_end: date
    total_hours_logged: float
    total_hours_estimated: float
    efficiency_ratio: float
    tasks_completed: int
    tasks_total: int
    completion_rate: float
    by_project: List[dict]


# ── Alerts ────────────────────────────────────────────────────────────────────

class AlertOut(BaseModel):
    id: str
    alert_type: str
    severity: str
    title: str
    description: Optional[str] = None
    value: Optional[float] = None
    threshold: Optional[float] = None
    user: Optional[UserPublic] = None
    project: Optional[ProjectSummary] = None
    is_read: bool
    is_resolved: bool
    created_at: datetime

    class Config:
        from_attributes = True


# ── Export ────────────────────────────────────────────────────────────────────

class ExportRequest(BaseModel):
    project_ids: Optional[List[str]] = None
    user_ids: Optional[List[str]] = None
    date_from: Optional[date] = None
    date_to: Optional[date] = None
    include_costs: bool = False  # Only for admin role
    format: str = "xlsx"  # xlsx, csv


# ── Pagination ────────────────────────────────────────────────────────────────

class PaginatedResponse(BaseModel):
    items: list
    total: int
    page: int
    page_size: int
    pages: int
