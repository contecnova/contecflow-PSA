from datetime import date
from typing import List

from pydantic import BaseModel


class DashboardKPIs(BaseModel):
    total_budget: float
    total_spent: float
    budget_used_pct: float
    projects_active: int
    projects_at_risk: int
    projects_over_budget: int
    total_resources: int
    overloaded_resources: int
    avg_load_pct: float
    tasks_open: int
    tasks_blocked: int
    tasks_overdue: int
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
