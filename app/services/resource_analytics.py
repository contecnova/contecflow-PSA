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
