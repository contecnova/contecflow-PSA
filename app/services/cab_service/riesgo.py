"""Puntuacion de riesgo de proyecto (plazo, presupuesto, alcance, recursos) y su cache.

Parte de `app.services.cab_service` (auditoria 2026-11, #24): se partio por responsabilidad
sin cambiar el codigo. El paquete reexporta todos los nombres.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from types import SimpleNamespace
from sqlalchemy import func
from sqlalchemy.orm import Session
from app.core.config import settings
from app.models.project import Project
from app.models.resources import ChangeRequest
from app.models.task import Task
from app.models.pipeline import Risk
from app.models.cab import ProjectRiskScore
from app.core import timeutil


# ─── Project risk scoring ─────────────────────────────────────────────────────

_CLAVES_DE_RIESGO = {
    "RISK_WEIGHT_SCHEDULE": "float", "RISK_WEIGHT_BUDGET": "float",
    "RISK_WEIGHT_SCOPE": "float", "RISK_WEIGHT_RESOURCE": "float",
    "RISK_LEVEL_CRITICAL": "float", "RISK_LEVEL_HIGH": "float", "RISK_LEVEL_MEDIUM": "float",
    "RISK_SCHEDULE_FACTOR": "float", "RISK_BUDGET_WARN_PCT": "float",
    "RISK_BUDGET_WARN_FACTOR": "float", "RISK_BUDGET_OVER_FACTOR": "float",
    "RISK_POINTS_PER_OPEN_CR": "float", "RISK_POINTS_PER_HIGH_RISK": "float",
    "RISK_DELAY_FACTOR": "float", "RISK_DELAY_MAX_PCT": "float", "RISK_DELAY_PCT_PER_WEEK": "float",
    "RISK_CACHE_MINUTES": "int", "RISK_HISTORY_POINTS": "int",
}


def _ajustes_de_riesgo(db: Session, org_id=None) -> SimpleNamespace:
    """Pesos y umbrales de la puntuacion (Admin → Ajustes → risk; si no, `.env`).

    Revision 2026-11: estaban escritos en las funciones de abajo. Se leen una
    vez por calculo, no una por regla.
    """
    from app.services.settings_service import get_runtime_namespace
    leidos = get_runtime_namespace(db, _CLAVES_DE_RIESGO, org_id)
    return SimpleNamespace(**{
        k: (getattr(leidos, k, None) if getattr(leidos, k, None) is not None else getattr(settings, k))
        for k in _CLAVES_DE_RIESGO})

def _risk_schedule(db: Session, project: Project, today: date, aj=None) -> float:
    """Compute schedule risk component (0-100)."""
    if not (project.start_date and project.end_date_planned):
        return 0.0
    total_days = (project.end_date_planned - project.start_date).days
    elapsed_days = (today - project.start_date).days
    if total_days <= 0:
        return 0.0
    time_pct = elapsed_days / total_days * 100
    total_tasks = db.query(func.count(Task.id)).filter(Task.project_id == project.id).scalar() or 1
    done_tasks = db.query(func.count(Task.id)).filter(
        Task.project_id == project.id, Task.status == "done"
    ).scalar() or 0
    completion_pct = done_tasks / total_tasks * 100
    behind_pct = max(time_pct - completion_pct, 0)
    aj = aj or _ajustes_de_riesgo(db, project.organization_id)
    return min(behind_pct * aj.RISK_SCHEDULE_FACTOR, 100)


def _risk_budget(db: Session, project: Project, aj=None) -> float:
    """Compute budget risk component (0-100)."""
    if not (project.budget_amount and project.budget_amount > 0):
        return 0.0
    # Coste interno real (antes horas × 80 €/h escrito aqui).
    from app.services.ml_features import coste_real
    budget_pct = coste_real(db, project.id) / project.budget_amount * 100
    aj = aj or _ajustes_de_riesgo(db, project.organization_id)
    if budget_pct > 100:
        return min((budget_pct - 100) * aj.RISK_BUDGET_OVER_FACTOR, 100)
    if budget_pct > aj.RISK_BUDGET_WARN_PCT:
        return min((budget_pct - aj.RISK_BUDGET_WARN_PCT) * aj.RISK_BUDGET_WARN_FACTOR, 100)
    return 0.0


def _risk_scope(db: Session, project: Project, aj=None) -> float:
    """Compute scope risk (open CRs)."""
    open_crs = db.query(func.count(ChangeRequest.id)).filter(
        ChangeRequest.project_id == project.id,
        ChangeRequest.status.in_(["submitted", "under_review"]),
    ).scalar() or 0
    aj = aj or _ajustes_de_riesgo(db, project.organization_id)
    return min(open_crs * aj.RISK_POINTS_PER_OPEN_CR, 100)


def _risk_resource(db: Session, project: Project, aj=None) -> float:
    """Compute resource risk (open high-priority risks)."""
    high_risks = db.query(func.count(Risk.id)).filter(
        Risk.project_id == project.id,
        Risk.status.in_(["identified", "analyzing", "mitigating", "monitoring"]),
        Risk.probability.in_(["high", "very_high"]),
    ).scalar() if hasattr(Risk, 'project_id') else 0
    aj = aj or _ajustes_de_riesgo(db, project.organization_id)
    return min((high_risks or 0) * aj.RISK_POINTS_PER_HIGH_RISK, 100)


def _risk_recommendation(level: str) -> str:
    """Return human-readable recommendation for a risk level."""
    if level == "critical":
        return "Escalar inmediatamente a dirección. Revisar alcance y recursos."
    if level == "high":
        return "Revisar con el PM en la próxima reunión. Considerar ajuste de fechas."
    if level == "medium":
        return "Monitorizar semanalmente. Resolver CRs pendientes."
    return "Proyecto en buen estado. Mantener ritmo actual."


def compute_risk_score(db: Session, project: Project) -> dict:
    from app.services.ml_features import carga_del_equipo
    """
    Rule-based risk scoring. Returns score components and overall risk level.
    """
    today = timeutil.today()
    aj = _ajustes_de_riesgo(db, project.organization_id)
    score = {
        "schedule_risk": round(_risk_schedule(db, project, today, aj), 1),
        "budget_risk": round(_risk_budget(db, project, aj), 1),
        "scope_risk": _risk_scope(db, project, aj),
        "resource_risk": _risk_resource(db, project, aj),
        # Antes siempre 0: quienes imputan al proyecto y pasan de su capacidad.
        "overloaded_members": carga_del_equipo(db, project.id, today)["overloaded_members"],
    }

    overall = (
        score["schedule_risk"] * aj.RISK_WEIGHT_SCHEDULE +
        score["budget_risk"] * aj.RISK_WEIGHT_BUDGET +
        score["scope_risk"] * aj.RISK_WEIGHT_SCOPE +
        score["resource_risk"] * aj.RISK_WEIGHT_RESOURCE
    )
    score["overall_score"] = round(overall, 1)

    level = ("critical" if overall >= aj.RISK_LEVEL_CRITICAL else "high" if overall >= aj.RISK_LEVEL_HIGH
             else "medium" if overall >= aj.RISK_LEVEL_MEDIUM else "low")
    score["level"] = level

    delay_prob = min(overall * aj.RISK_DELAY_FACTOR, aj.RISK_DELAY_MAX_PCT)
    por_semana = aj.RISK_DELAY_PCT_PER_WEEK or 1
    score["delay_probability_pct"] = round(delay_prob, 1)
    score["predicted_delay_weeks"] = round(delay_prob / por_semana, 1) if delay_prob > por_semana else None
    score["recommendation"] = _risk_recommendation(level)

    return score


# ─── Risk scores ──────────────────────────────────────────────────────────────

_RISK_SCORE_FIELDS = [
    "schedule_risk", "budget_risk", "scope_risk", "resource_risk",
    "overall_score", "level", "delay_probability_pct",
    "predicted_delay_weeks", "recommendation",
]


def _is_risk_cache_fresh(cached, ttl_minutes: int = 60) -> bool:
    """Return True if the cached risk score is younger than ttl_minutes."""
    if not (cached and cached.computed_at):
        return False
    computed_at = cached.computed_at
    if computed_at.tzinfo is None:
        computed_at = computed_at.replace(tzinfo=timezone.utc)
    age_minutes = (datetime.now(timezone.utc) - computed_at).total_seconds() / 60
    return age_minutes < ttl_minutes


def _serialize_cached_risk(project, cached) -> dict:
    """Serialize a ProjectRiskScore row plus the project label fields."""
    return {
        "project_id": project.id,
        "project_name": project.name,
        "project_code": project.code,
        "overall_score": cached.overall_score,
        "level": cached.level,
        "schedule_risk": cached.schedule_risk,
        "budget_risk": cached.budget_risk,
        "scope_risk": cached.scope_risk,
        "resource_risk": cached.resource_risk,
        "delay_probability_pct": cached.delay_probability_pct,
        "predicted_delay_weeks": cached.predicted_delay_weeks,
        "recommendation": cached.recommendation,
        "computed_at": str(cached.computed_at)[:16],
        "cached": True,
    }


def _persist_risk_score(db: Session, project_id: str, score_data: dict) -> None:
    """Persist a ProjectRiskScore row from a score dict (no commit)."""
    score_obj = ProjectRiskScore(
        project_id=project_id,
        **{k: v for k, v in score_data.items() if k in _RISK_SCORE_FIELDS}
    )
    db.add(score_obj)


def get_risk_scores(refresh: bool, db: Session) -> dict:
    projects = db.query(Project).filter(
        Project.status.in_(["active", "planning"])
    ).all()
    results = []
    for project in projects:
        cached = db.query(ProjectRiskScore).filter(
            ProjectRiskScore.project_id == project.id
        ).order_by(ProjectRiskScore.computed_at.desc()).first()
        ttl = _ajustes_de_riesgo(db, project.organization_id).RISK_CACHE_MINUTES
        if not refresh and _is_risk_cache_fresh(cached, ttl):
            results.append(_serialize_cached_risk(project, cached))
            continue
        score_data = compute_risk_score(db, project)
        _persist_risk_score(db, project.id, score_data)
        results.append({
            "project_id": project.id,
            "project_name": project.name,
            "project_code": project.code,
            **score_data,
            "computed_at": datetime.now(timezone.utc).isoformat()[:16],
            "cached": False,
        })
    db.commit()
    results.sort(key=lambda x: -(x.get("overall_score") or 0))
    return {
        "projects": results,
        "summary": {
            "critical": sum(1 for r in results if r.get("level") == "critical"),
            "high": sum(1 for r in results if r.get("level") == "high"),
            "medium": sum(1 for r in results if r.get("level") == "medium"),
            "low": sum(1 for r in results if r.get("level") == "low"),
        }
    }


def get_project_risk_score(project_id: str, db: Session) -> dict:
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise ValueError("Proyecto no encontrado")
    score_data = compute_risk_score(db, project)
    aj = _ajustes_de_riesgo(db, project.organization_id)
    previas = db.query(ProjectRiskScore).filter(
        ProjectRiskScore.project_id == project_id,
    ).order_by(ProjectRiskScore.computed_at.desc()).limit(max(1, aj.RISK_HISTORY_POINTS)).all()
    # Antes cada apertura del detalle insertaba una fila. Ahora solo si la
    # puntuacion cambia o la ultima ya ha caducado: el historial es de cambios.
    ultima = previas[0] if previas else None
    if not (ultima and ultima.overall_score == score_data["overall_score"]
            and _is_risk_cache_fresh(ultima, aj.RISK_CACHE_MINUTES)):
        _persist_risk_score(db, project_id, score_data)
        db.commit()
    historial = [{"computed_at": str(r.computed_at)[:16], "overall_score": r.overall_score, "level": r.level}
                 for r in reversed(previas)]
    return {
        "project_id": project_id,
        "project_name": project.name,
        "project_code": project.code,
        "client_name": project.client_name,
        **score_data,
        "history": historial,
    }
