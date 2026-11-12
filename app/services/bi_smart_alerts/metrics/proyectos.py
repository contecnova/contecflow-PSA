"""Series de proyectos: estado, hitos, entregables, peticiones de cambio y tareas.

Parte de `app.services.bi_smart_alerts.metrics` (auditoria 2026-11, #24): se partio por responsabilidad
sin cambiar el codigo. El paquete reexporta todos los nombres.
"""
from __future__ import annotations

from collections import defaultdict
from typing import Optional

from app.services.bi_smart_alerts.metrics._contexto import _Ctx, logger


def _serie_active_projects(ctx: _Ctx) -> Optional[list[float]]:
    """Metrica `active_projects`."""
    _current, _empty_like, db, metric_key, organization_id = ctx.current, ctx.empty_like, ctx.db, ctx.key, ctx.org_id
    if metric_key == "active_projects":
        try:
            from app.models.project import Project, ProjectStatus as PS
            return _current(float(db.query(Project).filter(Project.status == PS.active).count()))
        except Exception:
            logger.debug("Failed to fetch metric %s for org=%s", metric_key, organization_id, exc_info=True)
            return _empty_like()

def _serie_projects_at_risk(ctx: _Ctx) -> Optional[list[float]]:
    """Metrica `projects_at_risk`."""
    _current, _empty_like, db, metric_key, organization_id = ctx.current, ctx.empty_like, ctx.db, ctx.key, ctx.org_id
    if metric_key == "projects_at_risk":
        try:
            from app.models.project import Project, ProjectStatus as PS, ProjectRisk as PR
            return _current(float(db.query(Project).filter(
                Project.status == PS.active, Project.risk_level.in_([PR.high, PR.critical])
            ).count()))
        except Exception:
            logger.debug("Failed to fetch metric %s for org=%s", metric_key, organization_id, exc_info=True)
            return _empty_like()

def _serie_projects_over_budget(ctx: _Ctx) -> Optional[list[float]]:
    """Metrica `projects_over_budget`."""
    _current, _empty_like, db, metric_key, organization_id = ctx.current, ctx.empty_like, ctx.db, ctx.key, ctx.org_id
    if metric_key == "projects_over_budget":
        try:
            from app.models.project import Project, ProjectStatus as PS
            from app.models.imputation import Imputation
            from sqlalchemy import func as sqf
            costs = {pid: float(c or 0) for pid, c in
                     db.query(Imputation.project_id, sqf.sum(Imputation.cost_amount)
                              ).group_by(Imputation.project_id).all() if pid}
            projects = db.query(Project.id, Project.budget_amount).filter(
                Project.status == PS.active, Project.budget_amount > 0
            ).all()
            return _current(float(sum(1 for pid, bgt in projects if costs.get(pid, 0) > float(bgt or 0))))
        except Exception:
            logger.debug("Failed to fetch metric %s for org=%s", metric_key, organization_id, exc_info=True)
            return _empty_like()

def _serie_projects_overdue(ctx: _Ctx) -> Optional[list[float]]:
    """Metrica `projects_overdue`."""
    _current, _empty_like, db, metric_key, organization_id = ctx.current, ctx.empty_like, ctx.db, ctx.key, ctx.org_id
    if metric_key == "projects_overdue":
        try:
            from app.models.project import Project, ProjectStatus as PS
            from datetime import date as dc
            today = dc.today()
            return _current(float(db.query(Project).filter(
                Project.status == PS.active,
                Project.end_date_planned != None,
                Project.end_date_planned < today
            ).count()))
        except Exception:
            logger.debug("Failed to fetch metric %s for org=%s", metric_key, organization_id, exc_info=True)
            return _empty_like()

def _serie_projects_on_hold(ctx: _Ctx) -> Optional[list[float]]:
    """Metrica `projects_on_hold`."""
    _current, _empty_like, db, metric_key, organization_id = ctx.current, ctx.empty_like, ctx.db, ctx.key, ctx.org_id
    if metric_key == "projects_on_hold":
        try:
            from app.models.project import Project, ProjectStatus as PS
            return _current(float(db.query(Project).filter(Project.status == PS.on_hold).count()))
        except Exception:
            logger.debug("Failed to fetch metric %s for org=%s", metric_key, organization_id, exc_info=True)
            return _empty_like()

def _serie_projects_cancelled(ctx: _Ctx) -> Optional[list[float]]:
    """Metrica `projects_cancelled`."""
    _current, _empty_like, db, metric_key, organization_id = ctx.current, ctx.empty_like, ctx.db, ctx.key, ctx.org_id
    if metric_key == "projects_cancelled":
        try:
            from app.models.project import Project, ProjectStatus as PS
            return _current(float(db.query(Project).filter(Project.status == PS.cancelled).count()))
        except Exception:
            logger.debug("Failed to fetch metric %s for org=%s", metric_key, organization_id, exc_info=True)
            return _empty_like()

def _serie_projects_completed_count(ctx: _Ctx) -> Optional[list[float]]:
    """Metrica `projects_completed_count`."""
    _current, _empty_like, db, metric_key, organization_id = ctx.current, ctx.empty_like, ctx.db, ctx.key, ctx.org_id
    if metric_key == "projects_completed_count":
        try:
            from app.models.project import Project, ProjectStatus as PS
            return _current(float(db.query(Project).filter(Project.status == PS.completed).count()))
        except Exception:
            logger.debug("Failed to fetch metric %s for org=%s", metric_key, organization_id, exc_info=True)
            return _empty_like()

def _serie_milestones(ctx: _Ctx) -> Optional[list[float]]:
    """Metricas que comparten consulta:

    · milestones_overdue
    · milestones_pending
    · milestones_completed
    · milestones_invoiced
    · milestones_pending_approval
    """
    _current, _empty_like, db, metric_key, organization_id = ctx.current, ctx.empty_like, ctx.db, ctx.key, ctx.org_id
    if metric_key in ("milestones_overdue","milestones_pending","milestones_completed",
                       "milestones_invoiced","milestones_pending_approval"):
        try:
            from app.models.financial import ProjectMilestone
            from datetime import date as dc
            today = dc.today()
            if metric_key == "milestones_overdue":
                return _current(float(db.query(ProjectMilestone).filter(
                    ProjectMilestone.is_completed == False,
                    ProjectMilestone.due_date != None,
                    ProjectMilestone.due_date < today
                ).count()))
            if metric_key == "milestones_pending":
                return _current(float(db.query(ProjectMilestone).filter(
                    ProjectMilestone.billing_status == "pending"
                ).count()))
            if metric_key == "milestones_completed":
                return _current(float(db.query(ProjectMilestone).filter(
                    ProjectMilestone.is_completed == True
                ).count()))
            if metric_key == "milestones_invoiced":
                return _current(float(db.query(ProjectMilestone).filter(
                    ProjectMilestone.is_billed == True
                ).count()))
            if metric_key == "milestones_pending_approval":
                return _current(float(db.query(ProjectMilestone).filter(
                    ProjectMilestone.billing_status == "pending_approval"
                ).count()))
        except Exception:
            logger.debug("Failed to fetch metric %s for org=%s", metric_key, organization_id, exc_info=True)
            return _empty_like()

def _serie_deliverables(ctx: _Ctx) -> Optional[list[float]]:
    """Metricas que comparten consulta:

    · deliverables_in_progress
    · deliverables_in_review
    · deliverables_accepted
    · deliverables_rejected
    """
    _current, _empty_like, db, metric_key, organization_id = ctx.current, ctx.empty_like, ctx.db, ctx.key, ctx.org_id
    if metric_key in ("deliverables_in_progress","deliverables_in_review",
                       "deliverables_accepted","deliverables_rejected"):
        try:
            from app.models.resources import Deliverable, DeliverableStatus
            STATUS = {"deliverables_in_progress": DeliverableStatus.in_progress,
                      "deliverables_in_review":   DeliverableStatus.in_review,
                      "deliverables_accepted":    DeliverableStatus.accepted,
                      "deliverables_rejected":    DeliverableStatus.rejected}
            return _current(float(db.query(Deliverable).filter(
                Deliverable.status == STATUS[metric_key]
            ).count()))
        except Exception:
            logger.debug("Failed to fetch metric %s for org=%s", metric_key, organization_id, exc_info=True)
            return _empty_like()

def _serie_change_requests(ctx: _Ctx) -> Optional[list[float]]:
    """Metricas que comparten consulta:

    · change_requests_total
    · change_requests_pending
    · change_requests_cost_impact
    · change_requests_schedule
    """
    _current, _empty_like, db, metric_key, organization_id = ctx.current, ctx.empty_like, ctx.db, ctx.key, ctx.org_id
    if metric_key in ("change_requests_total","change_requests_pending",
                       "change_requests_cost_impact","change_requests_schedule"):
        try:
            from app.models.resources import ChangeRequest, ChangeRequestStatus
            if metric_key == "change_requests_total":
                return _current(float(db.query(ChangeRequest).count()))
            if metric_key == "change_requests_pending":
                return _current(float(db.query(ChangeRequest).filter(
                    ChangeRequest.status.in_([ChangeRequestStatus.draft, ChangeRequestStatus.submitted])
                ).count()))
            if metric_key == "change_requests_cost_impact":
                from sqlalchemy import func as sqf
                v = db.query(sqf.sum(ChangeRequest.cost_impact)).scalar() or 0.0
                return _current(float(v))
            if metric_key == "change_requests_schedule":
                from sqlalchemy import func as sqf
                v = db.query(sqf.sum(ChangeRequest.schedule_impact_days)).scalar() or 0.0
                return _current(float(v))
        except Exception:
            logger.debug("Failed to fetch metric %s for org=%s", metric_key, organization_id, exc_info=True)
            return _empty_like()

def _serie_tasks_overdue(ctx: _Ctx) -> Optional[list[float]]:
    """Metrica `tasks_overdue`."""
    _empty_like, db, metric_key, organization_id, series, start_date = ctx.empty_like, ctx.db, ctx.key, ctx.org_id, ctx.series, ctx.start_date
    if metric_key == "tasks_overdue":
        try:
            from app.models.task import Task
            rows = db.query(Task.due_date, Task.status).filter(
                Task.due_date != None, Task.due_date >= start_date
            ).all()
            bkt: dict[str,float] = defaultdict(float)
            for dd, st in rows:
                if dd and str(getattr(st,"value",st)) not in ("done","cancelled"):
                    bkt[f"{dd.year:04d}-{dd.month:02d}"] += 1.0
            return [float(bkt.get(m["month"],0.0)) for m in series]
        except Exception:
            logger.debug("Failed to fetch metric %s for org=%s", metric_key, organization_id, exc_info=True)
            return _empty_like()

def _serie_tasks_blocked(ctx: _Ctx) -> Optional[list[float]]:
    """Metrica `tasks_blocked`."""
    _current, _empty_like, db, metric_key, organization_id = ctx.current, ctx.empty_like, ctx.db, ctx.key, ctx.org_id
    if metric_key == "tasks_blocked":
        try:
            from app.models.task import Task, TaskStatus
            return _current(float(db.query(Task).filter(Task.status == TaskStatus.blocked).count()))
        except Exception:
            logger.debug("Failed to fetch metric %s for org=%s", metric_key, organization_id, exc_info=True)
            return _empty_like()

def _serie_tasks_created(ctx: _Ctx) -> Optional[list[float]]:
    """Metrica `tasks_created`."""
    _bucket_count, _empty_like, db, metric_key, organization_id, start_date = ctx.bucket_count, ctx.empty_like, ctx.db, ctx.key, ctx.org_id, ctx.start_date
    if metric_key == "tasks_created":
        try:
            from app.models.task import Task
            rows = db.query(Task.created_at).filter(Task.created_at >= start_date).all()
            return _bucket_count(rows, start=start_date)
        except Exception:
            logger.debug("Failed to fetch metric %s for org=%s", metric_key, organization_id, exc_info=True)
            return _empty_like()

def _serie_tasks_completed(ctx: _Ctx) -> Optional[list[float]]:
    """Metrica `tasks_completed`."""
    _bucket_count, _empty_like, db, metric_key, organization_id, start_date = ctx.bucket_count, ctx.empty_like, ctx.db, ctx.key, ctx.org_id, ctx.start_date
    if metric_key == "tasks_completed":
        try:
            from app.models.task import Task, TaskStatus
            rows = db.query(Task.completed_at).filter(
                Task.status == TaskStatus.done,
                Task.completed_at != None,
                Task.completed_at >= start_date
            ).all()
            return _bucket_count(rows, start=start_date)
        except Exception:
            logger.debug("Failed to fetch metric %s for org=%s", metric_key, organization_id, exc_info=True)
            return _empty_like()
