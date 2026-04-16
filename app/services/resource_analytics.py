"""
Resource analytics service — calculations for availability, load scoring, skill matching, etc.
"""
from datetime import datetime, timedelta, date
from typing import List, Dict, Optional, Tuple
from sqlalchemy.orm import Session
from sqlalchemy import and_, func
import logging

from app.models.user import User
from app.models.project import Project, ProjectMember
from app.models.financial import CapacityPlan
from app.models.imputation import Imputation
from app.models.resources import (
    UserSkill, ResourceAlert, ResourceAlertType, ResourceUtilizationSnapshot
)

logger = logging.getLogger(__name__)


class ResourceAnalyticsService:
    """Service for resource planning analytics and forecasting."""

    @staticmethod
    def get_week_iso(dt: date) -> str:
        """Get ISO week format (e.g., '2024-W15')."""
        if isinstance(dt, datetime):
            dt = dt.date()
        iso = dt.isocalendar()
        return f"{iso[0]}-W{iso[1]:02d}"

    @staticmethod
    def get_week_date_range(week_iso: str) -> Tuple[date, date]:
        """
        Convert ISO week string (e.g., '2026-W14') to start and end dates.

        Returns:
            (Monday, Sunday) of that week
        """
        try:
            year, week_num = week_iso.split('-W')
            year = int(year)
            week_num = int(week_num)

            # ISO 8601: Week 1 is the week with the first Thursday of the year
            # Monday of week 1
            jan_4 = date(year, 1, 4)
            week_1_monday = jan_4 - timedelta(days=jan_4.weekday())

            # Get Monday of target week
            target_monday = week_1_monday + timedelta(weeks=week_num - 1)
            target_sunday = target_monday + timedelta(days=6)

            return target_monday, target_sunday
        except (ValueError, AttributeError) as e:
            logger.error(f"Invalid week_iso format: {week_iso}. Error: {e}")
            # Return current week as fallback
            today = date.today()
            monday = today - timedelta(days=today.weekday())
            return monday, monday + timedelta(days=6)

    @staticmethod
    def get_user_availability(db: Session, user_id: str, week_iso: str) -> Dict:
        """
        Get user availability for a specific week.

        Returns:
            {
                'user_id': str,
                'week_iso': str,
                'capacity_hours': float,
                'planned_hours': float,
                'actual_hours': float,
                'billable_hours': float,
                'load_pct': float,  # (planned + actual) / capacity * 100
                'available_hours': float,
            }
        """
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            return None

        capacity_hours = user.weekly_capacity_hours or 40.0

        # Get from snapshot if available
        snapshot = db.query(ResourceUtilizationSnapshot).filter(
            and_(
                ResourceUtilizationSnapshot.user_id == user_id,
                ResourceUtilizationSnapshot.week_iso == week_iso,
            )
        ).first()

        if snapshot:
            planned = snapshot.planned_hours
            actual = snapshot.actual_hours
            billable = snapshot.billable_hours
        else:
            # Calculate from CapacityPlan + Imputation
            # Get date range for ISO week
            week_start, week_end = ResourceAnalyticsService.get_week_date_range(week_iso)

            plans = db.query(func.sum(CapacityPlan.planned_hours)).filter(
                and_(
                    CapacityPlan.user_id == user_id,
                    CapacityPlan.week_start >= week_start,
                    CapacityPlan.week_start <= week_end,
                )
            ).scalar() or 0.0

            from sqlalchemy import case as sa_case
            imputations_result = db.query(
                func.sum(Imputation.hours),
                func.sum(sa_case((Imputation.is_billable == True, Imputation.hours), else_=0))
            ).filter(
                and_(
                    Imputation.user_id == user_id,
                    Imputation.date >= week_start,
                    Imputation.date <= week_end,
                )
            ).first()

            actual = imputations_result[0] or 0.0
            billable = imputations_result[1] or 0.0
            planned = plans

        load_pct = ((planned + actual) / capacity_hours * 100) if capacity_hours > 0 else 0.0
        available_hours = max(0, capacity_hours - planned - actual)

        return {
            "user_id": user_id,
            "user_name": user.full_name,
            "week_iso": week_iso,
            "capacity_hours": capacity_hours,
            "planned_hours": float(planned),
            "actual_hours": float(actual),
            "billable_hours": float(billable),
            "load_pct": round(load_pct, 2),
            "available_hours": round(available_hours, 2),
        }

    @staticmethod
    def get_team_availability(db: Session, team_user_ids: List[str], weeks_ahead: int = 4) -> List[Dict]:
        """
        Get team availability for next N weeks.

        Args:
            team_user_ids: List of user IDs
            weeks_ahead: Number of future weeks to return

        Returns:
            List of availability records per user per week
        """
        result = []
        today = date.today()

        for i in range(weeks_ahead):
            week_start = today + timedelta(weeks=i)
            week_iso = ResourceAnalyticsService.get_week_iso(week_start)

            for user_id in team_user_ids:
                avail = ResourceAnalyticsService.get_user_availability(db, user_id, week_iso)
                if avail:
                    result.append(avail)

        return result

    @staticmethod
    def get_load_scoring(db: Session, exclude_user_ids: Optional[List[str]] = None) -> List[Dict]:
        """
        Get all users ranked by current load percentage.

        Returns:
            List sorted by load_pct (descending)
        """
        users = db.query(User).filter(User.is_active == True)
        if exclude_user_ids:
            users = users.filter(~User.id.in_(exclude_user_ids))
        users = users.all()

        scoring = []
        current_week = ResourceAnalyticsService.get_week_iso(date.today())

        for user in users:
            avail = ResourceAnalyticsService.get_user_availability(db, user.id, current_week)
            if avail:
                scoring.append({
                    "user_id": user.id,
                    "user_name": user.full_name,
                    "role": user.role.value,
                    "load_pct": avail["load_pct"],
                    "capacity_hours": avail["capacity_hours"],
                    "allocated_hours": avail["planned_hours"] + avail["actual_hours"],
                    "available_hours": avail["available_hours"],
                    "status": "overloaded" if avail["load_pct"] > 100 else (
                        "at_capacity" if avail["load_pct"] >= 80 else "underutilized"
                    ),
                })

        return sorted(scoring, key=lambda x: x["load_pct"], reverse=True)

    @staticmethod
    def get_skill_gaps(db: Session, project_id: str) -> List[Dict]:
        """
        Analyze skill gaps in a project.

        Returns required skills vs available team skills.
        """
        project = db.query(Project).filter(Project.id == project_id).first()
        if not project:
            return []

        # For now, this returns team skills
        # In a full implementation, you'd have ProjectSkillRequirement model
        team_members = db.query(ProjectMember).filter(
            ProjectMember.project_id == project_id
        ).all()

        user_ids = [m.user_id for m in team_members]
        available_skills = db.query(UserSkill).filter(
            UserSkill.user_id.in_(user_ids)
        ).all()

        skills_by_user = {}
        for skill in available_skills:
            if skill.user_id not in skills_by_user:
                skills_by_user[skill.user_id] = []
            skills_by_user[skill.user_id].append({
                "skill_id": skill.skill_id,
                "skill_name": skill.skill.name,
                "level": skill.level.value,
            })

        return [
            {
                "user_id": uid,
                "skills": skills,
            }
            for uid, skills in skills_by_user.items()
        ]

    @staticmethod
    def get_available_users_by_skill(db: Session, skill_id: str) -> List[Dict]:
        """
        Get all users with a specific skill, ranked by availability.

        Returns:
            List of users sorted by available_hours (descending)
        """
        user_skills = db.query(UserSkill).filter(
            UserSkill.skill_id == skill_id
        ).all()

        result = []
        current_week = ResourceAnalyticsService.get_week_iso(date.today())

        for us in user_skills:
            avail = ResourceAnalyticsService.get_user_availability(db, us.user_id, current_week)
            if avail:
                result.append({
                    "user_id": avail["user_id"],
                    "user_name": avail["user_name"],
                    "level": us.level.value,
                    "available_hours": avail["available_hours"],
                    "load_pct": avail["load_pct"],
                })

        return sorted(result, key=lambda x: x["available_hours"], reverse=True)

    @staticmethod
    def create_overload_alerts(db: Session) -> int:
        """
        Auto-scan for overloaded users and create alerts.

        Returns: Number of alerts created
        """
        users = db.query(User).filter(User.is_active == True).all()
        current_week = ResourceAnalyticsService.get_week_iso(date.today())
        count = 0

        for user in users:
            avail = ResourceAnalyticsService.get_user_availability(db, user.id, current_week)
            if avail and avail["load_pct"] > 100:
                # Check if alert already exists
                existing = db.query(ResourceAlert).filter(
                    and_(
                        ResourceAlert.user_id == user.id,
                        ResourceAlert.alert_type == ResourceAlertType.overload_warning,
                        ResourceAlert.acknowledged_at == None,
                    )
                ).first()

                if not existing:
                    alert = ResourceAlert(
                        user_id=user.id,
                        alert_type=ResourceAlertType.overload_warning,
                        context=f'{{"week": "{current_week}", "load_pct": {avail["load_pct"]}}}',
                        severity="critical" if avail["load_pct"] > 150 else "warning",
                    )
                    db.add(alert)
                    count += 1

        if count > 0:
            db.commit()
            logger.info(f"Created {count} overload alerts")

        return count

    @staticmethod
    def update_utilization_snapshots(db: Session, week_iso: str) -> int:
        """
        Update resource utilization snapshots for a specific week.

        Returns: Number of snapshots updated
        """
        users = db.query(User).filter(User.is_active == True).all()
        count = 0

        for user in users:
            # Delete old snapshot if exists
            db.query(ResourceUtilizationSnapshot).filter(
                and_(
                    ResourceUtilizationSnapshot.user_id == user.id,
                    ResourceUtilizationSnapshot.week_iso == week_iso,
                )
            ).delete()

            avail = ResourceAnalyticsService.get_user_availability(db, user.id, week_iso)
            if avail:
                snapshot = ResourceUtilizationSnapshot(
                    user_id=user.id,
                    week_iso=week_iso,
                    planned_hours=avail["planned_hours"],
                    actual_hours=avail["actual_hours"],
                    billable_hours=avail["billable_hours"],
                    utilization_pct=avail["load_pct"],
                    billable_pct=(avail["billable_hours"] / avail["actual_hours"] * 100)
                    if avail["actual_hours"] > 0
                    else 0,
                )
                db.add(snapshot)
                count += 1

        if count > 0:
            db.commit()
            logger.info(f"Updated {count} utilization snapshots for week {week_iso}")

        return count


# Singleton instance
resource_analytics = ResourceAnalyticsService()


def get_team_user_ids(db: Session, current_user: User, project_id: Optional[str] = None) -> List[str]:
    """
    Devuelve los IDs de usuarios del equipo visibles para current_user.
    Si se proporciona project_id, filtra a los miembros de ese proyecto.
    """
    q = db.query(User.id).filter(User.is_active == True)  # noqa: E712

    if current_user.organization_id:
        q = q.filter(User.organization_id == current_user.organization_id)

    if project_id:
        member_user_ids = (
            db.query(ProjectMember.user_id)
            .filter(ProjectMember.project_id == project_id)
            .scalar_subquery()
        )
        q = q.filter(User.id.in_(member_user_ids))

    return [row[0] for row in q.all()]


def get_team_health_payload(db: Session) -> Dict:
    """Devuelve métricas de salud del equipo: cargas promedio, recuentos por estado."""
    scores = resource_analytics.get_load_scoring(db)
    total = len(scores)
    if total == 0:
        return {
            "avg_load_pct": 0.0,
            "overloaded_count": 0,
            "at_capacity_count": 0,
            "underutilized_count": 0,
            "total_users": 0,
            "billable_pct": 0.0,
        }
    overloaded = sum(1 for s in scores if s.get("load_pct", 0) > 100)
    at_capacity = sum(1 for s in scores if 80 <= s.get("load_pct", 0) <= 100)
    underutilized = sum(1 for s in scores if s.get("load_pct", 0) < 50)
    avg_load = sum(s.get("load_pct", 0) for s in scores) / total

    # billable_pct: fraction of users whose billable_hours > 0
    billable_count = sum(1 for s in scores if s.get("billable_hours", 0) > 0)
    billable_pct = round((billable_count / total) * 100, 1)

    return {
        "avg_load_pct": round(avg_load, 1),
        "overloaded_count": overloaded,
        "at_capacity_count": at_capacity,
        "underutilized_count": underutilized,
        "total_users": total,
        "billable_pct": billable_pct,
    }


def get_utilization_history_records(
    db: Session,
    user_id: Optional[str] = None,
    weeks_back: int = 12,
) -> List:
    """Devuelve snapshots históricos de utilización."""
    from app.models.resources import ResourceUtilizationSnapshot

    # Calcular el week_iso más antiguo a incluir
    cutoff = date.today() - timedelta(weeks=weeks_back)
    cutoff_iso = f"{cutoff.isocalendar()[0]}-W{cutoff.isocalendar()[1]:02d}"

    q = db.query(ResourceUtilizationSnapshot).filter(
        ResourceUtilizationSnapshot.week_iso >= cutoff_iso
    )
    if user_id:
        q = q.filter(ResourceUtilizationSnapshot.user_id == user_id)

    return q.order_by(ResourceUtilizationSnapshot.week_iso.desc()).all()


def get_alerts_records(
    db: Session,
    current_user: User,
    acknowledged: bool = False,
    alert_type=None,
) -> List:
    """Devuelve alertas de recursos filtradas por estado y tipo."""
    from app.models.resources import ResourceAlert

    q = db.query(ResourceAlert)

    if current_user.organization_id:
        org_user_ids = (
            db.query(User.id)
            .filter(User.organization_id == current_user.organization_id)
            .scalar_subquery()
        )
        q = q.filter(ResourceAlert.user_id.in_(org_user_ids))

    if acknowledged:
        q = q.filter(ResourceAlert.acknowledged_at.isnot(None))
    else:
        q = q.filter(ResourceAlert.acknowledged_at.is_(None))

    if alert_type is not None:
        q = q.filter(ResourceAlert.alert_type == alert_type)

    return q.order_by(ResourceAlert.triggered_at.desc()).all()


def acknowledge_alert_record(db: Session, alert_id: str, current_user: User) -> Dict:
    """Marca una alerta como reconocida."""
    from app.models.resources import ResourceAlert
    from fastapi import HTTPException
    from datetime import timezone

    alert = db.query(ResourceAlert).filter(ResourceAlert.id == alert_id).first()
    if not alert:
        raise HTTPException(status_code=404, detail="Alerta no encontrada")

    alert.acknowledged_at = datetime.now(timezone.utc)
    alert.acknowledged_by = str(current_user.id)
    db.commit()
    return {"status": "acknowledged", "alert_id": alert_id}




def get_user_week_hours(db: Session, user_id: str, week_start: date) -> dict:
    """Returns committed/booking/capacity/absence hours for a user in a given week."""
    from app.models.bookings import ResourceBooking
    from app.models.financial import CapacityPlan

    week_end = week_start + timedelta(days=6)

    bookings = db.query(ResourceBooking).filter(
        ResourceBooking.user_id == user_id,
        ResourceBooking.start_date <= week_end,
        ResourceBooking.end_date >= week_start,
    ).all()

    booking_hours = 0.0
    booking_projects: dict = {}
    for b in bookings:
        overlap_start = max(b.start_date, week_start)
        overlap_end = min(b.end_date, week_end)
        days = max(0, (overlap_end - overlap_start).days + 1)
        work_days = sum(
            1 for i in range(days)
            if (overlap_start + timedelta(days=i)).weekday() < 5
        )
        h = work_days * (b.hours_per_day or 8)
        booking_hours += h
        pid = str(b.project_id) if b.project_id else "unassigned"
        booking_projects[pid] = booking_projects.get(pid, 0) + h

    cp = db.query(CapacityPlan).filter(
        CapacityPlan.user_id == user_id,
        CapacityPlan.week_start == week_start,
    ).all()
    capacity_hours = sum(c.planned_hours for c in cp)
    for c in cp:
        pid = str(c.project_id) if c.project_id else "unassigned"
        booking_projects[pid] = booking_projects.get(pid, 0) + c.planned_hours

    try:
        from app.models.resources import Absence as AbsenceModel
        absences = db.query(AbsenceModel).filter(
            AbsenceModel.user_id == user_id,
            AbsenceModel.status == "approved",
            AbsenceModel.start_date <= week_end,
            AbsenceModel.end_date >= week_start,
        ).all()
        absence_hours = 0.0
        for a in absences:
            ov_start = max(a.start_date, week_start)
            ov_end = min(a.end_date, week_end)
            days = max(0, (ov_end - ov_start).days + 1)
            work_days = sum(
                1 for i in range(days)
                if (ov_start + timedelta(days=i)).weekday() < 5
            )
            absence_hours += work_days * 8
    except Exception:
        absence_hours = 0.0

    total = booking_hours + capacity_hours
    return {
        "committed_hours": round(total, 1),
        "booking_hours": round(booking_hours, 1),
        "capacity_hours": round(capacity_hours, 1),
        "absence_hours": round(absence_hours, 1),
        "projects": {k: round(v, 1) for k, v in booking_projects.items()},
    }


def get_forecast_active_users(
    db: Session,
    department: Optional[str] = None,
    role: Optional[str] = None,
    user_id: Optional[str] = None,
) -> List:
    """Return active User objects, optionally filtered by department, role, or a specific user_id."""
    q = db.query(User).filter(User.is_active == True)
    if department:
        q = q.filter(User.department == department)
    if role:
        q = q.filter(User.role == role)
    if user_id:
        q = q.filter(User.id == user_id)
    return q.order_by(User.full_name).all()


def get_forecast_user_by_id(db: Session, user_id: str):
    """Return a single User by id, or None."""
    return db.query(User).filter(User.id == user_id).first()


def get_forecast_project_names(db: Session) -> Dict:
    """Return {str(project_id): project_name} for all projects."""
    from app.models.project import Project
    return {str(p.id): p.name for p in db.query(Project).all()}


def get_forecast_past_imputations(
    db: Session, user_ids: List[str], date_from: date, date_to: date
) -> List:
    """
    Return aggregated imputation rows (user_id, date, hours) for the given
    users within [date_from, date_to).
    """
    from app.models.imputation import Imputation
    from sqlalchemy import func as sqlfunc

    return (
        db.query(
            Imputation.user_id,
            Imputation.date,
            sqlfunc.sum(Imputation.hours).label("hours"),
        )
        .filter(
            Imputation.user_id.in_(user_ids),
            Imputation.date >= date_from,
            Imputation.date < date_to,
        )
        .group_by(Imputation.user_id, Imputation.date)
        .all()
    )


# ── Date utility helpers ──────────────────────────────────────────────────────

def monday(d: "date") -> "date":
    """Return the Monday of the week containing *d*."""
    from datetime import timedelta
    return d - timedelta(days=d.weekday())


def weeks_range(start: "date", n: int) -> list:
    """Return a list of *n* Monday dates starting from the week of *start*."""
    from datetime import timedelta
    mon = monday(start)
    return [mon + timedelta(weeks=i) for i in range(n)]


def week_label(d: "date") -> str:
    """ISO week label, e.g. '2025-W22'."""
    return d.strftime("%Y-W%V")

