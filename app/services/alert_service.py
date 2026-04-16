"""
Alert service — business logic for alert generation and management.
Called by both the API endpoint and the Celery worker.
"""
from datetime import date, timedelta, datetime, timezone, time
import logging

from sqlalchemy.orm import Session
from sqlalchemy import func, or_

from app.core.config import settings
from app.models.alert import Alert, AlertType, AlertSeverity
from app.models.imputation import Imputation
from app.models.project import Project, ProjectStatus
from app.models.task import Task, TaskStatus
from app.models.user import User, UserRole, UserStatus

logger = logging.getLogger(__name__)


class AlertEngine:
    """Core engine that generates alerts based on current data state."""

    def __init__(self, db: Session):
        self.db = db

    def run_all(self) -> int:
        """Run all alert checks. Returns count of new alerts created."""
        generated = 0
        generated += self._check_overload()
        generated += self._check_budget()
        generated += self._check_blocked_tasks()
        generated += self._check_no_imputation()
        generated += self._check_deadline()
        return generated

    def _alert_exists(self, alert_type: AlertType, user_id=None, project_id=None, task_id=None) -> bool:
        """Avoid duplicate alerts for the same situation with row lock semantics."""
        q = self.db.query(Alert).filter(
            Alert.alert_type == alert_type,
            Alert.is_resolved == False,
        )
        if user_id:
            q = q.filter(Alert.user_id == user_id)
        if project_id:
            q = q.filter(Alert.project_id == project_id)
        if task_id:
            q = q.filter(Alert.task_id == task_id)

        try:
            q = q.with_for_update(read=True)
        except Exception:
            logger.debug("with_for_update not supported on this DB dialect; skipping")

        return q.first() is not None

    def _create_alert(self, alert_type, severity, title, description=None,
                      user_id=None, project_id=None, task_id=None,
                      value=None, threshold=None):
        dedup_key = f"{alert_type}:{user_id or ''}:{project_id or ''}:{task_id or ''}"[:200]
        alert = Alert(
            alert_type=alert_type,
            severity=severity,
            title=title,
            description=description,
            user_id=user_id,
            project_id=project_id,
            task_id=task_id,
            value=value,
            threshold=threshold,
            dedup_key=dedup_key,
        )
        self.db.add(alert)

    def _check_overload(self) -> int:
        today = date.today()
        week_start = today - timedelta(days=today.weekday())
        count = 0

        users = self.db.query(User).filter(
            User.is_active == True, User.status == UserStatus.active
        ).all()
        if not users:
            return 0
        user_ids = [u.id for u in users]

        hours_rows = self.db.query(
            Imputation.user_id,
            func.sum(Imputation.hours).label("hours"),
        ).filter(
            Imputation.user_id.in_(user_ids),
            Imputation.date >= week_start,
        ).group_by(Imputation.user_id).all()
        hours_by_uid = {r.user_id: float(r.hours or 0) for r in hours_rows}

        for user in users:
            hours = hours_by_uid.get(user.id, 0.0)
            capacity = user.weekly_capacity_hours or settings.DEFAULT_WEEKLY_CAPACITY_HOURS
            load_pct = (hours / capacity) * 100 if capacity > 0 else 0

            if load_pct > 100 and not self._alert_exists(AlertType.overload, user_id=user.id):
                self._create_alert(
                    AlertType.overload,
                    AlertSeverity.warning if load_pct < 120 else AlertSeverity.critical,
                    f"Sobreasignación: {user.full_name}",
                    f"{user.full_name} tiene {load_pct:.0f}% de carga esta semana ({hours:.1f}h / {capacity}h)",
                    user_id=user.id,
                    value=load_pct,
                    threshold=100.0,
                )
                count += 1
        self.db.commit()
        return count

    def _check_budget(self) -> int:
        count = 0
        projects = self.db.query(Project).filter(
            Project.status == ProjectStatus.active,
            Project.budget_amount > 0,
        ).all()
        if not projects:
            return 0
        project_ids = [p.id for p in projects]

        cost_rows = self.db.query(
            Imputation.project_id,
            func.sum(Imputation.cost_amount).label("total_cost"),
        ).filter(Imputation.project_id.in_(project_ids)).group_by(Imputation.project_id).all()
        cost_by_pid = {r.project_id: float(r.total_cost or 0) for r in cost_rows}

        for p in projects:
            total_cost = cost_by_pid.get(p.id, 0.0)
            pct = (total_cost / p.budget_amount) * 100

            if pct >= 100 and not self._alert_exists(AlertType.budget_critical, project_id=p.id):
                self._create_alert(
                    AlertType.budget_critical,
                    AlertSeverity.critical,
                    f"Presupuesto agotado: {p.name}",
                    f"El proyecto {p.code} ha consumido {pct:.0f}% del presupuesto ({total_cost:.0f}€ / {p.budget_amount:.0f}€)",
                    project_id=p.id, value=pct, threshold=100.0,
                )
                count += 1
            elif pct >= 85 and not self._alert_exists(AlertType.budget_exceeded, project_id=p.id):
                self._create_alert(
                    AlertType.budget_exceeded,
                    AlertSeverity.warning,
                    f"Presupuesto al {pct:.0f}%: {p.name}",
                    f"El proyecto {p.code} ha consumido {pct:.0f}% del presupuesto",
                    project_id=p.id, value=pct, threshold=85.0,
                )
                count += 1
        self.db.commit()
        return count

    def _check_blocked_tasks(self) -> int:
        count = 0
        two_days_ago = date.today() - timedelta(days=2)

        blocked = self.db.query(Task).filter(
            Task.status == TaskStatus.blocked,
            Task.updated_at <= datetime.combine(two_days_ago, time.min, tzinfo=timezone.utc),
        ).all()

        for task in blocked:
            if not self._alert_exists(AlertType.task_blocked, task_id=task.id):
                self._create_alert(
                    AlertType.task_blocked,
                    AlertSeverity.warning,
                    f"Tarea bloqueada: {task.code}",
                    f"'{task.title}' lleva bloqueada más de 2 días. Razón: {task.blocked_reason or 'No especificada'}",
                    task_id=task.id,
                    project_id=task.project_id,
                    user_id=task.assignee_id,
                )
                count += 1
        self.db.commit()
        return count

    def _check_no_imputation(self) -> int:
        count = 0
        two_days_ago = date.today() - timedelta(days=2)

        users = self.db.query(User).filter(
            User.is_active == True, User.status == UserStatus.active,
            User.role.in_([UserRole.employee, UserRole.subcontractor]),
        ).all()
        if not users:
            return 0
        user_ids = [u.id for u in users]

        last_rows = self.db.query(
            Imputation.user_id,
            func.max(Imputation.date).label("last_date"),
        ).filter(Imputation.user_id.in_(user_ids)).group_by(Imputation.user_id).all()
        last_by_uid = {r.user_id: r.last_date for r in last_rows}

        for user in users:
            last_imp = last_by_uid.get(user.id)

            if last_imp and last_imp < two_days_ago:
                if not self._alert_exists(AlertType.no_imputation, user_id=user.id):
                    self._create_alert(
                        AlertType.no_imputation,
                        AlertSeverity.info,
                        f"Sin imputaciones: {user.full_name}",
                        f"{user.full_name} no ha registrado horas desde {last_imp}",
                        user_id=user.id,
                        value=(date.today() - last_imp).days,
                    )
                    count += 1
        self.db.commit()
        return count

    def _check_deadline(self) -> int:
        count = 0
        today = date.today()
        warning_threshold = today + timedelta(days=7)

        at_risk = self.db.query(Project).filter(
            Project.status == ProjectStatus.active,
            Project.end_date_planned <= warning_threshold,
            Project.end_date_planned >= today,
        ).all()

        for p in at_risk:
            if not self._alert_exists(AlertType.deadline_risk, project_id=p.id):
                days_left = (p.end_date_planned - today).days
                self._create_alert(
                    AlertType.deadline_risk,
                    AlertSeverity.warning,
                    f"Deadline en {days_left} días: {p.name}",
                    f"El proyecto {p.code} tiene fecha límite el {p.end_date_planned}",
                    project_id=p.id,
                    value=days_left,
                    threshold=7.0,
                )
                count += 1
        self.db.commit()
        return count


# ── Service functions ─────────────────────────────────────────────────────────

def run_alert_engine(db: Session) -> dict:
    engine = AlertEngine(db)
    count = engine.run_all()
    return {"alerts_generated": count}


def get_alerts_query(db: Session, resolved: bool, severity, current_user: User):
    """Return a filtered, ordered Alert query scoped to the current user's permissions."""
    q = db.query(Alert).filter(Alert.is_resolved == resolved)

    if current_user.role in (UserRole.employee, UserRole.subcontractor):
        q = q.filter(Alert.user_id == current_user.id)
    elif not current_user.is_superadmin and current_user.organization_id:
        org_user_ids = db.query(User.id).filter(
            User.organization_id == current_user.organization_id
        ).scalar_subquery()
        org_project_ids = db.query(Project.id).filter(
            Project.organization_id == current_user.organization_id
        ).scalar_subquery()
        q = q.filter(
            or_(
                Alert.user_id.in_(org_user_ids),
                Alert.project_id.in_(org_project_ids),
            )
        )

    if severity:
        q = q.filter(Alert.severity == severity)

    return q.order_by(Alert.created_at.desc())


def mark_alert_read(db: Session, alert_id: str) -> None:
    """Mark an alert as read."""
    alert = db.query(Alert).filter(Alert.id == alert_id).first()
    if alert:
        alert.is_read = True
        db.commit()


def resolve_alert(db: Session, alert_id: str, resolved_by_id) -> None:
    """Mark an alert as resolved."""
    alert = db.query(Alert).filter(Alert.id == alert_id).first()
    if alert:
        alert.is_resolved = True
        alert.resolved_at = datetime.now(timezone.utc)
        alert.resolved_by = resolved_by_id
        db.commit()
