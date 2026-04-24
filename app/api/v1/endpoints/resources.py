"""
Resource Planning API Endpoints.
Availability matrices, load scoring, skill matching, alerts, and utilization history.
"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from datetime import datetime
from typing import List, Optional, Dict
import logging

from app.core.deps import get_db, get_current_user, require_any_manager
from app.models.user import User
from app.models.resources import ResourceAlertType
from app.services.resource_analytics import (
    resource_analytics,
    get_team_user_ids as _svc_get_team_user_ids,
    get_team_health_payload as _svc_get_team_health,
    get_utilization_history_records as _svc_get_utilization_history,
    get_alerts_records as _svc_get_alerts,
    acknowledge_alert_record as _svc_acknowledge_alert,
)
from pydantic import BaseModel

router = APIRouter(tags=["resources"])
logger = logging.getLogger(__name__)


# ── Response Models ───────────────────────────────────────────────────────

class AvailabilityRecord(BaseModel):
    user_id: str
    user_name: str
    week_iso: str
    capacity_hours: float
    planned_hours: float
    actual_hours: float
    billable_hours: float
    load_pct: float
    available_hours: float

    class Config:
        from_attributes = True


class LoadScoreRecord(BaseModel):
    user_id: str
    user_name: str
    role: str
    load_pct: float
    capacity_hours: float
    allocated_hours: float
    available_hours: float
    status: str  # overloaded | at_capacity | underutilized

    class Config:
        from_attributes = True


class ResourceAlertOut(BaseModel):
    id: str
    user_id: str
    user_name: str
    alert_type: str
    context: Optional[str]
    severity: str
    triggered_at: datetime
    acknowledged_at: Optional[datetime]

    class Config:
        from_attributes = True


class UtilizationSnapshotOut(BaseModel):
    user_id: str
    user_name: str
    week_iso: str
    planned_hours: float
    actual_hours: float
    billable_hours: float
    utilization_pct: Optional[float]
    billable_pct: Optional[float]
    created_at: datetime

    class Config:
        from_attributes = True


class TeamHealthMetrics(BaseModel):
    avg_load_pct: float
    overloaded_count: int
    at_capacity_count: int
    underutilized_count: int
    total_users: int
    billable_pct: float


class SkillGapRecord(BaseModel):
    skill_id: str
    skill_name: str
    required: bool = False
    available_users: int = 0
    highest_level: Optional[str] = None


class AvailableUserBySkill(BaseModel):
    user_id: str
    user_name: str
    level: str
    available_hours: float
    load_pct: float


# ── Availability Matrix ────────────────────────────────────────────────────

@router.get("/availability-matrix", response_model=List[AvailabilityRecord], summary="Get team availability matrix")
def get_availability_matrix(
    weeks_ahead: int = Query(4, ge=1, le=12),
    project_id: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    """
    Get availability matrix for team (users × weeks).

    Shows planned hours, actual hours, load percentage, and available capacity.
    """
    team_user_ids = _svc_get_team_user_ids(db, current_user, project_id)
    availability = resource_analytics.get_team_availability(db, team_user_ids, weeks_ahead)

    return [
        AvailabilityRecord(
            user_id=a["user_id"],
            user_name=a["user_name"],
            week_iso=a["week_iso"],
            capacity_hours=a["capacity_hours"],
            planned_hours=a["planned_hours"],
            actual_hours=a["actual_hours"],
            billable_hours=a["billable_hours"],
            load_pct=a["load_pct"],
            available_hours=a["available_hours"],
        )
        for a in availability
    ]


# ── Load Scoring ───────────────────────────────────────────────────────────

@router.get("/load-scoring", response_model=List[LoadScoreRecord], summary="Get users by current load")
def get_load_scoring(
    min_load_pct: float = Query(0, ge=0),
    max_load_pct: float = Query(200, le=500),
    exclude_contractors: bool = False,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    """
    Get all users ranked by current load percentage.

    Helps identify overloaded resources and opportunities to distribute work.
    """
    scoring = resource_analytics.get_load_scoring(db)

    # Filter by load range
    filtered = [
        LoadScoreRecord(
            user_id=s["user_id"],
            user_name=s["user_name"],
            role=s["role"],
            load_pct=s["load_pct"],
            capacity_hours=s["capacity_hours"],
            allocated_hours=s["allocated_hours"],
            available_hours=s["available_hours"],
            status=s["status"],
        )
        for s in scoring
        if min_load_pct <= s["load_pct"] <= max_load_pct
    ]

    return filtered


# ── Team Health ────────────────────────────────────────────────────────────

@router.get("/team-health", response_model=TeamHealthMetrics, summary="Get team health metrics")
def get_team_health(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    """Get team utilization health metrics."""

    health = _svc_get_team_health(db)
    return TeamHealthMetrics(
        avg_load_pct=health["avg_load_pct"],
        overloaded_count=health["overloaded_count"],
        at_capacity_count=health["at_capacity_count"],
        underutilized_count=health["underutilized_count"],
        total_users=health["total_users"],
        billable_pct=health["billable_pct"],
    )


# ── Skill Gaps ─────────────────────────────────────────────────────────────

@router.get("/{project_id}/skill-gaps", response_model=List[Dict], summary="Analyze skill gaps in project")
def get_skill_gaps(
    project_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    """Analyze required vs available skills in a project."""
    gaps = resource_analytics.get_skill_gaps(db, project_id)
    return gaps


# ── Available Users by Skill ───────────────────────────────────────────────

@router.get("/available-by-skill/{skill_id}", response_model=List[AvailableUserBySkill], summary="Get users with skill ranked by availability")
def get_available_by_skill(
    skill_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    """Get all users with a skill, ranked by available hours."""
    available = resource_analytics.get_available_users_by_skill(db, skill_id)

    return [
        AvailableUserBySkill(
            user_id=a["user_id"],
            user_name=a["user_name"],
            level=a["level"],
            available_hours=a["available_hours"],
            load_pct=a["load_pct"],
        )
        for a in available
    ]


# ── Utilization History ────────────────────────────────────────────────────

@router.get("/utilization-history", response_model=List[UtilizationSnapshotOut], summary="Get historical utilization data")
def get_utilization_history(
    user_id: Optional[str] = None,
    weeks_back: int = Query(12, ge=1, le=52),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    """Get historical resource utilization snapshots."""
    snapshots = _svc_get_utilization_history(db, user_id=user_id, weeks_back=weeks_back)

    return [
        UtilizationSnapshotOut(
            user_id=s.user_id,
            user_name=s.user.full_name if s.user else "Unknown",
            week_iso=s.week_iso,
            planned_hours=s.planned_hours,
            actual_hours=s.actual_hours,
            billable_hours=s.billable_hours,
            utilization_pct=s.utilization_pct,
            billable_pct=s.billable_pct,
            created_at=s.created_at,
        )
        for s in snapshots
    ]


# ── Alerts ─────────────────────────────────────────────────────────────────

@router.get("/alerts", response_model=List[ResourceAlertOut], summary="Get resource alerts")
def get_alerts(
    acknowledged: bool = Query(False),
    alert_type: Optional[ResourceAlertType] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get resource alerts (overload, skill gaps, etc)."""
    alerts = _svc_get_alerts(db, current_user, acknowledged=acknowledged, alert_type=alert_type)

    return [
        ResourceAlertOut(
            id=a.id,
            user_id=a.user_id,
            user_name=a.user.full_name if a.user else "Unknown",
            alert_type=a.alert_type.value,
            context=a.context,
            severity=a.severity,
            triggered_at=a.triggered_at,
            acknowledged_at=a.acknowledged_at,
        )
        for a in alerts
    ]


@router.patch("/alerts/{alert_id}/acknowledge", summary="Acknowledge alert")
def acknowledge_alert(
    alert_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Acknowledge/dismiss an alert."""
    return _svc_acknowledge_alert(db, alert_id, current_user)


# ── Forecast ───────────────────────────────────────────────────────────────

@router.get("/forecast", response_model=List[AvailabilityRecord], summary="4-week availability forecast")
def get_forecast(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    """Get 4-week forward-looking availability forecast."""
    return get_availability_matrix(weeks_ahead=4, db=db, current_user=current_user)
