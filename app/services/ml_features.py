"""
ml_features.py — Feature engineering for project overrun prediction.

Feature vector (FEATURE_COLUMNS order must match ml_trainer.py):
  0  cpi                    — earned value / actual cost (>1 = under budget)
  1  spi                    — earned value / planned value (>1 = ahead)
  2  budget_used_pct        — actual cost / budget * 100
  3  elapsed_pct            — days elapsed / planned duration * 100
  4  task_completion_pct    — done tasks / total tasks * 100
  5  overdue_ratio          — overdue tasks / total tasks
  6  team_size              — number of assigned users
  7  budget_log             — log1p(budget_amount) — compressed budget scale
  8  duration_days          — planned duration in days (clamped 1–3650)

Label for training (binary):
  did_overrun = 1 if actual_cost > budget * 1.10  OR  end_date_real > end_date_planned
"""
from __future__ import annotations

import math
from datetime import date
from typing import Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.imputation import Imputation
from app.models.project import Project, ProjectStatus
from app.models.task import Task
from app.core import timeutil

FEATURE_COLUMNS = [
    "cpi", "spi", "budget_used_pct", "elapsed_pct",
    "task_completion_pct", "overdue_ratio", "team_size",
    "budget_log", "duration_days",
]
MIN_TRAINING_SAMPLES = 5


def extract_project_features(db: Session, project_id: str, reference_date: Optional[date] = None) -> Optional[dict]:
    """
    Compute feature dict for a single project.
    Returns None if insufficient data (no tasks, no budget).
    """
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        return None

    today = reference_date or timeutil.today()
    tasks = db.query(Task).filter(Task.project_id == project_id).all()
    if not tasks:
        return None

    total_tasks   = len(tasks)
    done_tasks    = sum(1 for t in tasks if t.status in ("done", "closed", "cancelled"))
    overdue_tasks = sum(
        1 for t in tasks
        if t.due_date and str(t.due_date) < str(today)
        and t.status not in ("done", "closed", "cancelled")
    )

    task_completion_pct = done_tasks / total_tasks * 100
    overdue_ratio       = overdue_tasks / total_tasks

    budget = float(project.budget_amount or 0)
    # actual_cost en EUROS. Si Imputation.cost_amount está populado (rate
    # × hours por imputación), lo usamos; si no, calculamos hours × tarifa
    # media. NUNCA sumamos hours como si fueran euros (bug histórico).
    cost_sum = db.query(func.sum(Imputation.cost_amount)).filter(
        Imputation.project_id == project_id,
        Imputation.cost_amount.isnot(None),
    ).scalar()
    if cost_sum is not None and cost_sum > 0:
        actual_cost = float(cost_sum)
    else:
        hours = float(db.query(func.sum(Imputation.hours)).filter(
            Imputation.project_id == project_id,
        ).scalar() or 0)
        from app.core.config import settings as _settings
        rate = float(getattr(_settings, "AI_REVENUE_HOURLY_RATE_FALLBACK", 85.0) or 85.0)
        actual_cost = hours * rate

    budget_used_pct = (actual_cost / budget * 100) if budget > 0 else 0

    start = project.start_date
    end   = project.end_date_planned
    if start and end and end > start:
        total_days   = max((end - start).days, 1)
        elapsed_days = min((today - start).days, total_days)
        elapsed_pct  = elapsed_days / total_days * 100
        duration_days = float(total_days)
    else:
        elapsed_pct   = task_completion_pct
        duration_days = 90.0

    duration_days = max(1.0, min(duration_days, 3650.0))

    budget_per_task = budget / total_tasks if budget > 0 and total_tasks > 0 else 0
    ev = budget_per_task * done_tasks
    pv = budget * elapsed_pct / 100 if budget > 0 else 0
    ac = actual_cost

    cpi = ev / ac if ac > 0 else 1.0
    spi = ev / pv if pv > 0 else 1.0

    # Team size: distinct users with imputations on this project
    team_size = float(
        db.query(func.count(func.distinct(Imputation.user_id)))
        .filter(Imputation.project_id == project_id)
        .scalar()
        or 0
    )

    return {
        "project_id":             project_id,
        "cpi":                    round(min(cpi,  5.0), 4),
        "spi":                    round(min(spi,  5.0), 4),
        "budget_used_pct":        round(min(budget_used_pct, 200.0), 2),
        "elapsed_pct":            round(elapsed_pct, 2),
        "task_completion_pct":    round(task_completion_pct, 2),
        "overdue_ratio":          round(overdue_ratio, 4),
        "team_size":              team_size,
        "budget_log":             round(math.log1p(budget), 4),
        "duration_days":          duration_days,
    }


def feature_vector(features: dict) -> list:
    """Convert feature dict to ordered list matching FEATURE_COLUMNS."""
    return [features[col] for col in FEATURE_COLUMNS]


def extract_training_dataset(db: Session, organization_id: Optional[str] = None):
    """
    Build (X, y) training data from completed projects.
    Returns (X: list[list[float]], y: list[int], project_ids: list[str])
    """
    q = db.query(Project).filter(Project.status == ProjectStatus.completed)
    if organization_id:
        q = q.filter(Project.organization_id == organization_id)
    completed = q.all()

    X, y, ids = [], [], []
    for proj in completed:
        # Use the real end date as reference to get final EVM snapshot
        ref = proj.end_date_real or proj.end_date_planned or timeutil.today()
        features = extract_project_features(db, proj.id, reference_date=ref)
        if features is None:
            continue

        # Label: overrun if actual cost > 110% of budget OR finished late
        budget = proj.budget_amount or 0
        actual_cost = float(
            db.query(func.sum(Imputation.cost_amount))
            .filter(Imputation.project_id == proj.id, Imputation.cost_amount.isnot(None))
            .scalar()
            or db.query(func.sum(Imputation.hours))
            .filter(Imputation.project_id == proj.id)
            .scalar()
            or 0
        )
        cost_overrun = (budget > 0) and (actual_cost > budget * 1.10)
        late = (
            proj.end_date_real is not None
            and proj.end_date_planned is not None
            and proj.end_date_real > proj.end_date_planned
        )
        label = 1 if (cost_overrun or late) else 0

        X.append(feature_vector(features))
        y.append(label)
        ids.append(proj.id)

    return X, y, ids
