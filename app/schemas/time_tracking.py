"""
Time Tracking Schemas.
Support for timers, retroactive blocking, and alerts.
"""
from pydantic import BaseModel
from typing import Optional
from datetime import datetime, date


# ── Timer Schemas ──────────────────────────────────────────────────────────

class TimerSessionOut(BaseModel):
    id: str
    user_id: str
    task_id: Optional[str] = None
    project_id: str
    started_at: datetime
    paused_at: Optional[datetime] = None
    paused_duration_secs: int
    ended_at: Optional[datetime] = None
    total_elapsed_seconds: Optional[int] = None  # Calculated

    class Config:
        from_attributes = True


class TimerStartPayload(BaseModel):
    task_id: Optional[str] = None
    project_id: str


class TimerStopPayload(BaseModel):
    description: Optional[str] = None
    is_billable: bool = True


# ── Imputation Alert Schemas ───────────────────────────────────────────────

class ImputationAlertOut(BaseModel):
    id: str
    user_id: str
    alert_date: date
    alert_type: str
    created_at: datetime
    dismissed_at: Optional[datetime] = None

    class Config:
        from_attributes = True


# ── Imputation Snapshot Schemas ────────────────────────────────────────────

class ImputationSnapshotOut(BaseModel):
    user_id: str
    snapshot_date: date
    total_hours: float
    billable_hours: float
    approved_hours: float
    is_complete: bool

    class Config:
        from_attributes = True


# ── Lockout Status Schemas ─────────────────────────────────────────────────

class LockoutStatusOut(BaseModel):
    lockout_days: int
    current_date: date
    lockout_cutoff_date: date
    locked_date_ranges: list  # Dates before cutoff
    editable_date_ranges: list  # Dates after cutoff


class ImputationAnalytics(BaseModel):
    """Daily/weekly/monthly summaries."""
    period: str  # daily | weekly | monthly
    total_hours: float
    billable_hours: float
    approved_hours: float
    by_project: dict  # {project_id: {hours, billable, approved}}
    by_task: dict  # {task_id: {hours, billable, approved}}
