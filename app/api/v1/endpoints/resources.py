"""
Resource Planning API Endpoints.
Availability matrices, load scoring, skill matching, alerts, and utilization history.
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import and_, func
from sqlalchemy.orm import Session
from datetime import datetime, timezone
from typing import List, Optional, Dict
import logging

from app.core.deps import get_db, get_current_user, require_any_manager
from app.models.user import User, UserRole
from app.models.resources import ResourceAlert, ResourceAlertType, ResourceUtilizationSnapshot
from app.services.resource_analytics import resource_analytics
from pydantic import BaseModel

router = APIRouter(prefix="/resources", tags=["resources"])
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
    # Get team users
    team_user_ids = []
    if project_id:
        from app.models.project import ProjectMember, Project
        # Verify project belongs to user's organization
        project = db.query(Project).filter(
            and_(Project.id == project_id, Project.organization_id == current_user.organization_id)
        ).first()
        if not project:
            raise HTTPException(status_code=404, detail="Project not found or access denied")

        members = db.query(ProjectMember).filter(
            ProjectMember.project_id == project_id
        ).all()
        team_user_ids = [m.user_id for m in members]
    else:
        # All users in current organization only
        team_user_ids = [
            u.id for u in db.query(User).filter(
                and_(User.organization_id == current_user.organization_id, User.is_active == True)
            ).all()
        ]

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
    from app.models.imputation import Imputation
    from datetime import datetime, timedelta, timezone

    scoring = resource_analytics.get_load_scoring(db)

    overloaded = len([s for s in scoring if s["load_pct"] > 100])
    at_capacity = len([s for s in scoring if 80 <= s["load_pct"] <= 100])
    underutilized = len([s for s in scoring if s["load_pct"] < 80])
    total = len(scoring)

    avg_load = sum(s["load_pct"] for s in scoring) / total if total > 0 else 0

    # Calculate actual billable percentage for current week
    today = datetime.now(timezone.utc).date()
    week_start = today - timedelta(days=today.weekday())
    week_end = week_start + timedelta(days=6)

    total_hours = db.query(func.sum(Imputation.hours)).filter(
        and_(Imputation.date >= week_start, Imputation.date <= week_end)
    ).scalar() or 0

    billable_hours = db.query(func.sum(Imputation.hours)).filter(
        and_(
            Imputation.date >= week_start,
            Imputation.date <= week_end,
            Imputation.is_billable == True
        )
    ).scalar() or 0

    billable_pct = (billable_hours / total_hours * 100) if total_hours > 0 else 0

    return TeamHealthMetrics(
        avg_load_pct=round(avg_load, 2),
        overloaded_count=overloaded,
        at_capacity_count=at_capacity,
        underutilized_count=underutilized,
        total_users=total,
        billable_pct=round(billable_pct, 2),
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
    q = db.query(ResourceUtilizationSnapshot)

    if user_id:
        q = q.filter(ResourceUtilizationSnapshot.user_id == user_id)

    snapshots = q.order_by(
        ResourceUtilizationSnapshot.created_at.desc()
    ).limit(weeks_back).all()

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
    q = db.query(ResourceAlert)

    if current_user.role != UserRole.admin:
        q = q.filter(ResourceAlert.user_id == current_user.id)

    if not acknowledged:
        q = q.filter(ResourceAlert.acknowledged_at == None)

    if alert_type:
        q = q.filter(ResourceAlert.alert_type == alert_type)

    alerts = q.order_by(ResourceAlert.triggered_at.desc()).all()

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
    alert = db.query(ResourceAlert).filter(ResourceAlert.id == alert_id).first()
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")

    if alert.user_id != current_user.id and current_user.role != UserRole.admin:
        raise HTTPException(status_code=403, detail="Cannot acknowledge another user's alert")

    alert.acknowledged_at = datetime.now(timezone.utc)
    alert.acknowledged_by = current_user.id
    db.commit()

    return {"status": "acknowledged"}


# ── Forecast ───────────────────────────────────────────────────────────────

@router.get("/forecast", response_model=List[AvailabilityRecord], summary="4-week availability forecast")
def get_forecast(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    """Get 4-week forward-looking availability forecast."""
    return get_availability_matrix(weeks_ahead=4, db=db, current_user=current_user)
