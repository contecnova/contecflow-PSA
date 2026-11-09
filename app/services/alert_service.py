"""
Alert service — business logic for alert generation and management.
Called by both the API endpoint and the Celery worker.
"""
from datetime import timedelta, datetime, timezone, time
import logging

from sqlalchemy.orm import Session
from sqlalchemy import func, or_, and_

from app.core.config import settings
from app.models.alert import Alert, AlertType, AlertSeverity
from app.models.imputation import Imputation
from app.models.project import Project, ProjectStatus
from app.models.task import Task, TaskStatus
from app.models.user import User, UserRole, UserStatus
from app.core import timeutil

logger = logging.getLogger(__name__)


def derive_alert_org_id(db: Session, *, user_id=None, project_id=None, task_id=None):
    """Deriva la organización de una alerta a partir de su ámbito.

    Por qué existe (auditoría 2026-08 §7): `_scope_alert_to_org` considera visibles
    para TODAS las organizaciones las alertas que tienen `organization_id`, `user_id`
    y `project_id` a NULL — un fallback pensado solo para datos anteriores a la
    migración 076. El problema es que había sitios creando alertas nuevas sin
    ninguno de los tres (p. ej. una automatización global sin project_id en su
    contexto), y esas alertas caían en ese fallback y se filtraban entre
    organizaciones.

    La solución correcta no es tocar el fallback, es dejar de crear filas
    ambiguas: si el ámbito permite deducir la organización, se persiste.
    """
    if project_id:
        org = db.query(Project.organization_id).filter(Project.id == project_id).scalar()
        if org:
            return org
    if user_id:
        org = db.query(User.organization_id).filter(User.id == user_id).scalar()
        if org:
            return org
    if task_id:
        org = (
            db.query(Project.organization_id)
            .join(Task, Task.project_id == Project.id)
            .filter(Task.id == task_id)
            .scalar()
        )
        if org:
            return org
    return None


class AlertEngine:
    """Core engine that generates alerts based on current data state.

    Revisión 2026-11: umbrales, severidad y encendido salen de Ajustes → Alertas
    (`alert_configs` de la empresa de cada elemento; si no hay fila, la global y
    después los valores por defecto del catálogo de alertas). Antes eran números
    fijos aquí (100 %, 85 %, 7 días, 2 días) y la tabla no la leía nadie.
    """

    def __init__(self, db: Session):
        self.db = db
        self._configs: dict = {}

    def _config(self, alert_type: AlertType, org_id) -> tuple:
        """(encendida, umbral, severidad) de un tipo de alerta para una empresa."""
        clave = (alert_type.value, org_id)
        if clave not in self._configs:
            from app.models.advanced_config import AlertConfig
            from app.services.advanced_config_service import DEFAULT_ALERT_CONFIGS
            filas = self.db.query(AlertConfig).filter(
                AlertConfig.alert_type == alert_type.value,
                or_(AlertConfig.organization_id == org_id, AlertConfig.organization_id.is_(None)),
            ).all()
            fila = next((f for f in filas if f.organization_id == org_id), None) or next(iter(filas), None)
            defecto = next(d for d in DEFAULT_ALERT_CONFIGS if d[0] == alert_type.value)
            if fila is None:
                self._configs[clave] = (True, float(defecto[3]), AlertSeverity(defecto[9]))
            else:
                umbral = fila.threshold_value if fila.threshold_value is not None else defecto[3]
                severidad = getattr(fila, "severity", None) or defecto[9]
                self._configs[clave] = (bool(fila.is_enabled), float(umbral), AlertSeverity(severidad))
        return self._configs[clave]

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
        """Evita alertas duplicadas para la misma situación usando bloqueo de fila."""
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
            organization_id=derive_alert_org_id(
                self.db, user_id=user_id, project_id=project_id, task_id=task_id,
            ),
            user_id=user_id,
            project_id=project_id,
            task_id=task_id,
            value=value,
            threshold=threshold,
            dedup_key=dedup_key,
        )
        self.db.add(alert)

    def _check_overload(self) -> int:
        today = timeutil.today()
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

            activa, umbral, severidad = self._config(AlertType.overload, user.organization_id)
            if activa and load_pct > umbral and not self._alert_exists(AlertType.overload, user_id=user.id):
                self._create_alert(
                    AlertType.overload,
                    severidad,
                    f"Sobreasignación: {user.full_name}",
                    f"{user.full_name} tiene {load_pct:.0f}% de carga esta semana ({hours:.1f}h / {capacity}h)",
                    user_id=user.id,
                    value=load_pct,
                    threshold=umbral,
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

            critica, umbral_critico, sev_critica = self._config(AlertType.budget_critical, p.organization_id)
            aviso, umbral_aviso, sev_aviso = self._config(AlertType.budget_exceeded, p.organization_id)
            if critica and pct >= umbral_critico and not self._alert_exists(AlertType.budget_critical, project_id=p.id):
                self._create_alert(
                    AlertType.budget_critical,
                    sev_critica,
                    f"Presupuesto agotado: {p.name}",
                    f"El proyecto {p.code} ha consumido {pct:.0f}% del presupuesto ({total_cost:.0f}€ / {p.budget_amount:.0f}€)",
                    project_id=p.id, value=pct, threshold=umbral_critico,
                )
                count += 1
            elif aviso and pct >= umbral_aviso and not self._alert_exists(AlertType.budget_exceeded, project_id=p.id):
                self._create_alert(
                    AlertType.budget_exceeded,
                    sev_aviso,
                    f"Presupuesto al {pct:.0f}%: {p.name}",
                    f"El proyecto {p.code} ha consumido {pct:.0f}% del presupuesto",
                    project_id=p.id, value=pct, threshold=umbral_aviso,
                )
                count += 1
        self.db.commit()
        return count

    def _check_blocked_tasks(self) -> int:
        count = 0
        blocked = self.db.query(Task).filter(Task.status == TaskStatus.blocked).all()

        for task in blocked:
            activa, dias, severidad = self._config(
                AlertType.task_blocked, derive_alert_org_id(self.db, task_id=task.id))
            limite = datetime.combine(timeutil.today() - timedelta(days=dias), time.min, tzinfo=timezone.utc)
            actualizada = task.updated_at
            if actualizada is not None and actualizada.tzinfo is None:
                actualizada = actualizada.replace(tzinfo=timezone.utc)
            if not activa or actualizada is None or actualizada > limite:
                continue
            if not self._alert_exists(AlertType.task_blocked, task_id=task.id):
                self._create_alert(
                    AlertType.task_blocked,
                    severidad,
                    f"Tarea bloqueada: {task.code}",
                    f"'{task.title}' lleva bloqueada más de {dias:g} días. Razón: {task.blocked_reason or 'No especificada'}",
                    task_id=task.id,
                    project_id=task.project_id,
                    user_id=task.assignee_id,
                )
                count += 1
        self.db.commit()
        return count

    def _check_no_imputation(self) -> int:
        count = 0

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
            activa, dias, severidad = self._config(AlertType.no_imputation, user.organization_id)

            if activa and last_imp and last_imp < timeutil.today() - timedelta(days=dias):
                if not self._alert_exists(AlertType.no_imputation, user_id=user.id):
                    self._create_alert(
                        AlertType.no_imputation,
                        severidad,
                        f"Sin imputaciones: {user.full_name}",
                        f"{user.full_name} no ha registrado horas desde {last_imp}",
                        user_id=user.id,
                        value=(timeutil.today() - last_imp).days,
                    )
                    count += 1
        self.db.commit()
        return count

    def _check_deadline(self) -> int:
        count = 0
        today = timeutil.today()

        at_risk = self.db.query(Project).filter(
            Project.status == ProjectStatus.active,
            Project.end_date_planned >= today,
        ).all()

        for p in at_risk:
            activa, dias, severidad = self._config(AlertType.deadline_risk, p.organization_id)
            if not activa or p.end_date_planned > today + timedelta(days=dias):
                continue
            if not self._alert_exists(AlertType.deadline_risk, project_id=p.id):
                days_left = (p.end_date_planned - today).days
                self._create_alert(
                    AlertType.deadline_risk,
                    severidad,
                    f"Deadline en {days_left} días: {p.name}",
                    f"El proyecto {p.code} tiene fecha límite el {p.end_date_planned}",
                    project_id=p.id,
                    value=days_left,
                    threshold=dias,
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


def _scope_alert_to_org(db: Session, q, current_user):
    """Audit #62 — restrict an Alert query to the current user's organization.

    Alert.organization_id (añadido en migración 076) es la fuente primaria
    de tenant. Como fallback (alertas legacy creadas antes de la migración),
    también aceptamos alertas asociadas a usuarios/proyectos de la org.
    """
    if current_user is None:
        return q
    if getattr(current_user, "is_superadmin", False):
        return q
    org_id = getattr(current_user, "organization_id", None)
    if not org_id:
        return q
    org_user_ids = db.query(User.id).filter(
        User.organization_id == org_id
    ).scalar_subquery()
    org_project_ids = db.query(Project.id).filter(
        Project.organization_id == org_id
    ).scalar_subquery()
    return q.filter(
        or_(
            Alert.organization_id == org_id,
            Alert.user_id.in_(org_user_ids),
            Alert.project_id.in_(org_project_ids),
            # Fallback para alertas legacy sin ningún campo de scope
            # (sucede solo con datos pre-migración 076).
            and_(
                Alert.organization_id.is_(None),
                Alert.user_id.is_(None),
                Alert.project_id.is_(None),
            ),
        )
    )


def mark_alert_read(db: Session, alert_id: str, current_user: User = None) -> None:
    """Mark an alert as read. Scoped to the caller's organization (audit #62)."""
    q = db.query(Alert).filter(Alert.id == alert_id)
    q = _scope_alert_to_org(db, q, current_user)
    alert = q.first()
    if alert:
        alert.is_read = True
        db.commit()


def resolve_alert(db: Session, alert_id: str, resolved_by_id, current_user: User = None) -> None:
    """Mark an alert as resolved. Scoped to the caller's organization (audit #62)."""
    q = db.query(Alert).filter(Alert.id == alert_id)
    q = _scope_alert_to_org(db, q, current_user)
    alert = q.first()
    if alert:
        alert.is_resolved = True
        alert.resolved_at = datetime.now(timezone.utc)
        alert.resolved_by = resolved_by_id
        db.commit()
