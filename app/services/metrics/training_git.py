"""Training and Git metrics: training_completion_rate, certifications_by_user,
prs_by_author, prs_by_project, pr_cycle_time, deployments_by_env, deployment_success_rate."""
from datetime import date
from typing import Optional
from sqlalchemy import func
from sqlalchemy.orm import Session

from . import register_metric


@register_metric("training_completion_rate")
def metric_training_completion_rate(
    db: Session,
    d_from: date,
    d_to: date,
    top_n: int,
    project_id: Optional[str] = None,
    user_id: Optional[str] = None,
    project_ids: Optional[list[str]] = None,
    **kwargs
) -> tuple[list[dict], dict]:
    """Tasa de finalización de cursos por curso."""
    try:
        from app.models.training import Course, CourseEnrollment

        courses = db.query(Course).limit(top_n).all()
        course_ids = [c.id for c in courses]
        course_map = {c.id: c.title for c in courses}

        totals = {r[0]: r[1] for r in db.query(
            CourseEnrollment.course_id, func.count(CourseEnrollment.id)
        ).filter(CourseEnrollment.course_id.in_(course_ids)).group_by(CourseEnrollment.course_id).all()}

        completed = {r[0]: r[1] for r in db.query(
            CourseEnrollment.course_id, func.count(CourseEnrollment.id)
        ).filter(
            CourseEnrollment.course_id.in_(course_ids),
            CourseEnrollment.status == "completed"
        ).group_by(CourseEnrollment.course_id).all()}

        rows = []
        for cid in course_ids:
            total = totals.get(cid, 0)
            done = completed.get(cid, 0)
            rate = round(done / total * 100, 1) if total else 0
            rows.append({
                "label": course_map.get(cid, str(cid)),
                "value": rate,
                "total_enrolled": total,
                "completed": done,
            })
        rows.sort(key=lambda x: x["value"], reverse=True)
    except Exception:
        rows = []

    return rows, {"y_label": "Tasa finalización (%)"}


@register_metric("certifications_by_user")
def metric_certifications_by_user(
    db: Session,
    d_from: date,
    d_to: date,
    top_n: int,
    project_id: Optional[str] = None,
    user_id: Optional[str] = None,
    project_ids: Optional[list[str]] = None,
    **kwargs
) -> tuple[list[dict], dict]:
    """Número de certificaciones obtenidas por persona en el período."""
    try:
        from app.models.training import Certification
        from app.models.user import User

        q = db.query(
            Certification.user_id,
            func.count(Certification.id).label("certs"),
        ).filter(
            Certification.created_at >= d_from,
            Certification.created_at <= d_to,
        ).group_by(Certification.user_id).order_by(func.count(Certification.id).desc()).limit(top_n)

        user_ids = [r.user_id for r in q.all()]
        users_map = {u.id: u.full_name or u.email for u in db.query(User).filter(User.id.in_(user_ids)).all()} if user_ids else {}

        rows = []
        for r in q.all():
            rows.append({
                "label": users_map.get(r.user_id, str(r.user_id)),
                "value": r.certs,
            })
    except Exception:
        rows = []

    return rows, {"y_label": "Certificaciones"}


@register_metric("prs_by_author")
def metric_prs_by_author(
    db: Session,
    d_from: date,
    d_to: date,
    top_n: int,
    project_id: Optional[str] = None,
    user_id: Optional[str] = None,
    project_ids: Optional[list[str]] = None,
    **kwargs
) -> tuple[list[dict], dict]:
    """Pull requests abiertos por autor en el período."""
    try:
        from app.models.git_integration import GitPullRequest

        q = db.query(
            GitPullRequest.author_login,
            func.count(GitPullRequest.id).label("prs"),
        ).filter(
            GitPullRequest.created_at >= d_from,
            GitPullRequest.created_at <= d_to,
        ).group_by(GitPullRequest.author_login).order_by(func.count(GitPullRequest.id).desc()).limit(top_n)

        rows = [{"label": r.author_login or "Desconocido", "value": r.prs} for r in q.all()]
    except Exception:
        rows = []

    return rows, {"y_label": "Pull Requests"}


@register_metric("prs_by_project")
def metric_prs_by_project(
    db: Session,
    d_from: date,
    d_to: date,
    top_n: int,
    project_id: Optional[str] = None,
    user_id: Optional[str] = None,
    project_ids: Optional[list[str]] = None,
    **kwargs
) -> tuple[list[dict], dict]:
    """Pull requests por proyecto en el período."""
    try:
        from app.models.git_integration import GitPullRequest
        from app.models.project import Project

        q_base = db.query(
            GitPullRequest.project_id,
            func.count(GitPullRequest.id).label("prs"),
        ).filter(
            GitPullRequest.created_at >= d_from,
            GitPullRequest.created_at <= d_to,
        )
        if project_ids:
            q_base = q_base.filter(GitPullRequest.project_id.in_(project_ids))
        q_base = q_base.group_by(GitPullRequest.project_id).order_by(func.count(GitPullRequest.id).desc()).limit(top_n)

        proj_ids = [r.project_id for r in q_base.all()]
        proj_map = {p.id: p.name for p in db.query(Project).filter(Project.id.in_(proj_ids)).all()} if proj_ids else {}

        rows = []
        for r in q_base.all():
            rows.append({
                "label": proj_map.get(r.project_id, str(r.project_id)),
                "value": r.prs,
            })
    except Exception:
        rows = []

    return rows, {"y_label": "Pull Requests"}


@register_metric("pr_cycle_time")
def metric_pr_cycle_time(
    db: Session,
    d_from: date,
    d_to: date,
    top_n: int,
    project_id: Optional[str] = None,
    user_id: Optional[str] = None,
    project_ids: Optional[list[str]] = None,
    **kwargs
) -> tuple[list[dict], dict]:
    """Tiempo medio de ciclo de PRs (horas desde apertura hasta merge) por proyecto."""
    try:
        from app.models.git_integration import GitPullRequest
        from app.models.project import Project
        from sqlalchemy import cast, Float

        prs = db.query(GitPullRequest).filter(
            GitPullRequest.merged_at.isnot(None),
            GitPullRequest.created_at >= d_from,
            GitPullRequest.created_at <= d_to,
        ).all()

        from collections import defaultdict
        project_times: dict = defaultdict(list)
        for pr in prs:
            if pr.merged_at and pr.created_at:
                hours = (pr.merged_at - pr.created_at).total_seconds() / 3600
                project_times[pr.project_id].append(hours)

        proj_ids = list(project_times.keys())
        proj_map = {p.id: p.name for p in db.query(Project).filter(Project.id.in_(proj_ids)).all()} if proj_ids else {}

        rows = []
        for pid, times in sorted(project_times.items(), key=lambda x: sum(x[1]) / len(x[1]))[:top_n]:
            avg_h = round(sum(times) / len(times), 1)
            rows.append({
                "label": proj_map.get(pid, str(pid)),
                "value": avg_h,
                "pr_count": len(times),
            })
    except Exception:
        rows = []

    return rows, {"y_label": "Horas (media ciclo PR)"}


@register_metric("deployments_by_env")
def metric_deployments_by_env(
    db: Session,
    d_from: date,
    d_to: date,
    top_n: int,
    project_id: Optional[str] = None,
    user_id: Optional[str] = None,
    project_ids: Optional[list[str]] = None,
    **kwargs
) -> tuple[list[dict], dict]:
    """Número de despliegues por entorno en el período."""
    try:
        from app.models.git_integration import GitDeployment

        q = db.query(
            GitDeployment.environment,
            func.count(GitDeployment.id).label("deploys"),
        ).filter(
            GitDeployment.created_at >= d_from,
            GitDeployment.created_at <= d_to,
        ).group_by(GitDeployment.environment).order_by(func.count(GitDeployment.id).desc())

        rows = [{"label": r.environment or "Sin entorno", "value": r.deploys} for r in q.all()]
    except Exception:
        rows = []

    return rows, {"y_label": "Despliegues"}


@register_metric("deployment_success_rate")
def metric_deployment_success_rate(
    db: Session,
    d_from: date,
    d_to: date,
    top_n: int,
    project_id: Optional[str] = None,
    user_id: Optional[str] = None,
    project_ids: Optional[list[str]] = None,
    **kwargs
) -> tuple[list[dict], dict]:
    """Tasa de éxito de despliegues por entorno."""
    try:
        from app.models.git_integration import GitDeployment, DeployStatus

        total_q = {r[0]: r[1] for r in db.query(
            GitDeployment.environment, func.count(GitDeployment.id)
        ).filter(
            GitDeployment.created_at >= d_from,
            GitDeployment.created_at <= d_to,
        ).group_by(GitDeployment.environment).all()}

        success_q = {r[0]: r[1] for r in db.query(
            GitDeployment.environment, func.count(GitDeployment.id)
        ).filter(
            GitDeployment.created_at >= d_from,
            GitDeployment.created_at <= d_to,
            GitDeployment.status == DeployStatus.success,
        ).group_by(GitDeployment.environment).all()}

        rows = []
        for env, total in sorted(total_q.items(), key=lambda x: x[1], reverse=True):
            success = success_q.get(env, 0)
            rate = round(success / total * 100, 1) if total else 0
            rows.append({
                "label": env or "Sin entorno",
                "value": rate,
                "total": total,
                "success": success,
            })
    except Exception:
        rows = []

    return rows, {"y_label": "Tasa éxito (%)"}
