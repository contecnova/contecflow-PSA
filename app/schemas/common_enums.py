from enum import Enum


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
    planning = "planning"
    active = "active"
    on_hold = "on_hold"
    paused = "paused"
    completed = "completed"
    closed = "closed"
    cancelled = "cancelled"
    archived = "archived"


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
    done = "done"
    cancelled = "cancelled"


class TaskPriority(str, Enum):
    critical = "critical"
    high = "high"
    medium = "medium"
    low = "low"
