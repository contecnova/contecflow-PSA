"""
ml_trainer.py — Train, persist, and serve the project overrun prediction model.

Architecture:
  - GradientBoostingClassifier per organization (scikit-learn)
  - Model bytes serialized with joblib and stored in MLModel.model_bytes
  - When scikit-learn is unavailable or there aren't enough samples,
    falls back to the rule-based heuristic from ai_modules_service.predict_overrun_ml
  - Minimum MIN_TRAINING_SAMPLES = 5 completed projects required to train
  - Retraining triggered: (1) manually via /predictions/train endpoint,
    (2) monthly via Celery beat on the 1st
"""
from __future__ import annotations

import io
import json
import uuid
from typing import Optional

from sqlalchemy.orm import Session

from app.models.ml_model import MLModel, MLModelType, MLPredictionLog
from app.models.project import Project
from app.services.ml_features import (
    FEATURE_COLUMNS, MIN_TRAINING_SAMPLES,
    extract_project_features, extract_training_dataset, feature_vector,
)

_SKLEARN_AVAILABLE = False
try:
    import joblib
    import numpy as np
    from sklearn.ensemble import GradientBoostingClassifier
    from sklearn.model_selection import cross_val_score
    from sklearn.preprocessing import StandardScaler
    from sklearn.pipeline import Pipeline
    _SKLEARN_AVAILABLE = True
except ImportError:
    pass


# ── Model persistence ──────────────────────────────────────────────────────────

def _serialize_model(model) -> bytes:
    buf = io.BytesIO()
    joblib.dump(model, buf)
    return buf.getvalue()


def _deserialize_model(data: bytes):
    return joblib.load(io.BytesIO(data))


def _get_active_model(db: Session, organization_id: str) -> Optional[MLModel]:
    return (
        db.query(MLModel)
        .filter(
            MLModel.organization_id == organization_id,
            MLModel.model_type == MLModelType.overrun,
            MLModel.is_active == True,
        )
        .order_by(MLModel.trained_at.desc())
        .first()
    )


# ── Training ───────────────────────────────────────────────────────────────────

def train_model(db: Session, organization_id: str) -> dict:
    """
    Train a new overrun prediction model for the given organization.
    Returns a dict with training results.
    """
    X, y, project_ids = extract_training_dataset(db, organization_id)
    n = len(X)

    if n < MIN_TRAINING_SAMPLES:
        return {
            "status": "skipped",
            "reason": f"Se necesitan al menos {MIN_TRAINING_SAMPLES} proyectos completados (hay {n})",
            "samples": n,
        }

    if not _SKLEARN_AVAILABLE:
        return {
            "status": "skipped",
            "reason": "scikit-learn no está instalado",
            "samples": n,
        }

    X_arr = np.array(X, dtype=np.float32)
    y_arr = np.array(y, dtype=np.int32)

    # Build pipeline: scale → GBM
    clf = Pipeline([
        ("scaler", StandardScaler()),
        ("clf", GradientBoostingClassifier(
            n_estimators=100, max_depth=3, learning_rate=0.1,
            subsample=0.8, random_state=42,
        )),
    ])

    # ROC-AUC via stratified k-fold (k=min(3,n//2))
    cv = min(3, max(2, n // 2))
    try:
        scores = cross_val_score(clf, X_arr, y_arr, cv=cv, scoring="roc_auc")
        accuracy = float(scores.mean())
    except Exception:
        accuracy = None

    clf.fit(X_arr, y_arr)
    model_bytes = _serialize_model(clf)

    # Deactivate previous active model
    db.query(MLModel).filter(
        MLModel.organization_id == organization_id,
        MLModel.model_type == MLModelType.overrun,
        MLModel.is_active == True,
    ).update({"is_active": False})

    # Persist new version
    prev = db.query(MLModel).filter(
        MLModel.organization_id == organization_id,
        MLModel.model_type == MLModelType.overrun,
    ).order_by(MLModel.version.desc()).first()

    new_version = (prev.version + 1) if prev else 1
    ml_model = MLModel(
        id=str(uuid.uuid4()),
        organization_id=organization_id,
        model_type=MLModelType.overrun,
        version=new_version,
        samples_used=n,
        accuracy=accuracy,
        feature_names=json.dumps(FEATURE_COLUMNS),
        model_bytes=model_bytes,
        is_active=True,
    )
    db.add(ml_model)
    db.commit()

    return {
        "status": "trained",
        "model_id": ml_model.id,
        "version": new_version,
        "samples": n,
        "accuracy_roc_auc": round(accuracy, 4) if accuracy else None,
    }


def train_all_orgs(db: Session) -> list:
    """Train models for all organizations that have completed projects."""
    from app.models.mfa import Organization
    orgs = db.query(Organization).filter(Organization.is_active == True).all()
    results = []
    for org in orgs:
        try:
            r = train_model(db, org.id)
            results.append({"org_id": org.id, "org_name": org.name, **r})
        except Exception as e:
            results.append({"org_id": org.id, "error": str(e)})
    return results


# ── Prediction ─────────────────────────────────────────────────────────────────

def _risk_level(cost_prob: float, sched_prob: float) -> str:
    p = max(cost_prob, sched_prob)
    if p >= 0.70: return "critical"
    if p >= 0.50: return "high"
    if p >= 0.30: return "medium"
    return "low"


def predict_project(db: Session, project_id: str, organization_id: str) -> dict:
    """
    Return overrun prediction for a project.
    Uses trained ML model when available; falls back to heuristic otherwise.
    """
    from app.services.ai_modules_service import predict_overrun_ml, get_overrun_prediction_data

    # Extract EVM features
    try:
        data = get_overrun_prediction_data(db, project_id)
    except ValueError:
        return {"error": "Datos insuficientes para predicción"}

    project = data["project"]

    # ── Try ML model ──────────────────────────────────────────────────────────
    used_heuristic = True
    ml_model_id = None
    feature_dict = extract_project_features(db, project_id)
    ml_result = None

    if feature_dict and _SKLEARN_AVAILABLE:
        ml_record = _get_active_model(db, organization_id)
        if ml_record and ml_record.model_bytes:
            try:
                clf = _deserialize_model(ml_record.model_bytes)
                X = np.array([feature_vector(feature_dict)], dtype=np.float32)
                proba = clf.predict_proba(X)[0]
                # proba[1] = probability of overrun
                overrun_prob = float(proba[1])
                # Separate cost/schedule signals from heuristic but scale by ML prob
                heuristic = predict_overrun_ml(
                    cpi=data["cpi"], spi=data["spi"],
                    budget_used_pct=data["budget_used_pct"],
                    elapsed_pct=data["elapsed_pct"],
                    task_completion_pct=data["task_completion_pct"],
                    overdue_task_ratio=data["overdue_ratio"],
                    team_load_pct=85.0,
                )
                # Blend: ML gives overall probability; heuristic weights split cost vs schedule
                total = (heuristic["cost_overrun_prob"] + heuristic["schedule_overrun_prob"]) or 1
                w_cost  = heuristic["cost_overrun_prob"]  / total if total > 0 else 0.5
                w_sched = heuristic["schedule_overrun_prob"] / total if total > 0 else 0.5
                ml_result = {
                    **heuristic,
                    "cost_overrun_prob":     round(overrun_prob * w_cost,  3),
                    "schedule_overrun_prob": round(overrun_prob * w_sched, 3),
                    "ml_overrun_prob": round(overrun_prob, 3),
                    "model_version": ml_record.version,
                    "model_accuracy": ml_record.accuracy,
                }
                used_heuristic = False
                ml_model_id = ml_record.id
            except Exception:
                pass  # Fall through to heuristic

    # ── Heuristic fallback ────────────────────────────────────────────────────
    if ml_result is None:
        ml_result = predict_overrun_ml(
            cpi=data["cpi"], spi=data["spi"],
            budget_used_pct=data["budget_used_pct"],
            elapsed_pct=data["elapsed_pct"],
            task_completion_pct=data["task_completion_pct"],
            overdue_task_ratio=data["overdue_ratio"],
            team_load_pct=85.0,
        )
        ml_result["ml_overrun_prob"] = None
        ml_result["model_version"] = None
        ml_result["model_accuracy"] = None

    risk = _risk_level(ml_result["cost_overrun_prob"], ml_result["schedule_overrun_prob"])

    # Persist prediction log (best-effort)
    try:
        log = MLPredictionLog(
            id=str(uuid.uuid4()),
            organization_id=organization_id,
            ml_model_id=ml_model_id,
            project_id=project_id,
            features_json=json.dumps(feature_dict) if feature_dict else None,
            cost_overrun_prob=ml_result["cost_overrun_prob"],
            schedule_overrun_prob=ml_result["schedule_overrun_prob"],
            risk_level=risk,
            used_heuristic=used_heuristic,
        )
        db.add(log)
        db.commit()
    except Exception:
        db.rollback()

    return {
        "project_id":    project_id,
        "project_name":  project.name,
        "cpi":           round(data["cpi"], 3),
        "spi":           round(data["spi"], 3),
        "budget_used_pct":      round(data["budget_used_pct"], 1),
        "elapsed_pct":          round(data["elapsed_pct"], 1),
        "task_completion_pct":  round(data["task_completion_pct"], 1),
        "overdue_ratio":        round(data["overdue_ratio"], 3),
        "risk_level":           risk,
        "used_heuristic":       used_heuristic,
        **ml_result,
    }


def portfolio_risk_summary(db: Session, organization_id: str) -> dict:
    """
    Compute risk levels for all active projects in the org.
    Returns aggregated counts + list of at-risk projects.
    """
    from app.models.project import Project, ProjectStatus

    active_projects = (
        db.query(Project)
        .filter(
            Project.organization_id == organization_id,
            Project.status.in_([ProjectStatus.active, ProjectStatus.on_hold]),
        )
        .all()
    )

    counts = {"critical": 0, "high": 0, "medium": 0, "low": 0}
    at_risk = []

    for proj in active_projects:
        try:
            result = predict_project(db, proj.id, organization_id)
            level = result.get("risk_level", "low")
            counts[level] = counts.get(level, 0) + 1
            if level in ("critical", "high"):
                at_risk.append({
                    "project_id":    proj.id,
                    "project_name":  proj.name,
                    "project_code":  proj.code,
                    "risk_level":    level,
                    "cost_overrun_prob":     result.get("cost_overrun_prob"),
                    "schedule_overrun_prob": result.get("schedule_overrun_prob"),
                    "recommendation": result.get("recommendation"),
                })
        except Exception:
            pass

    total = sum(counts.values())
    return {
        "total_projects": total,
        "risk_counts":    counts,
        "at_risk_projects": sorted(at_risk, key=lambda x: x["cost_overrun_prob"] or 0, reverse=True),
    }


# ── Model listing ──────────────────────────────────────────────────────────────

def list_models(db: Session, organization_id: str) -> list:
    models = (
        db.query(MLModel)
        .filter(
            MLModel.organization_id == organization_id,
            MLModel.model_type == MLModelType.overrun,
        )
        .order_by(MLModel.version.desc())
        .all()
    )
    return [
        {
            "id":           m.id,
            "version":      m.version,
            "samples_used": m.samples_used,
            "accuracy":     m.accuracy,
            "is_active":    m.is_active,
            "trained_at":   str(m.trained_at)[:19] if m.trained_at else None,
            "features":     json.loads(m.feature_names) if m.feature_names else FEATURE_COLUMNS,
        }
        for m in models
    ]
