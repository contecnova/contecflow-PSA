from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from sqlalchemy.orm import Session

from app.models.settings import AppSetting
from app.models.service_desk import Ticket, TicketStatus
from app.models.user import User
from app.services import bi_intelligence_service
from app.services.service_desk import predictive_analytics_service
import logging

logger = logging.getLogger(__name__)

ITSM_META_KEY = "predictive.retraining.itsm.meta"
BI_META_KEY = "predictive.retraining.bi.meta"
LAST_EVAL_KEY = "predictive.retraining.last_eval"


def _iso_now() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


def _parse_dt(raw: Optional[str]) -> Optional[datetime]:
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except Exception:
        return None


def _setting_row(db: Session, key: str, organization_id: Optional[str]) -> Optional[AppSetting]:
    q = db.query(AppSetting).filter(AppSetting.key == key)
    if organization_id:
        q = q.filter(AppSetting.organization_id == organization_id)
    else:
        q = q.filter(AppSetting.organization_id.is_(None))
    return q.first()


def _get_json(db: Session, key: str, organization_id: Optional[str], default: dict | None = None) -> dict:
    row = _setting_row(db, key, organization_id)
    if not row or not row.value:
        return default or {}
    try:
        payload = json.loads(row.value)
    except Exception:
        return default or {}
    return payload if isinstance(payload, dict) else (default or {})


def _set_json(db: Session, key: str, organization_id: Optional[str], value: dict, description: str) -> None:
    row = _setting_row(db, key, organization_id)
    payload = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    if not row:
        db.add(AppSetting(key=key, organization_id=organization_id, value=payload, description=description))
    else:
        row.value = payload
        if not row.description:
            row.description = description
    db.flush()


def _org_user_ids(db: Session, organization_id: Optional[str]) -> list[str]:
    if not organization_id:
        return []
    rows = db.query(User.id).filter(User.organization_id == organization_id).all()
    return [str(r[0]) for r in rows]


def evaluate_itsm_model_health(db: Session, *, organization_id: Optional[str], lookback_days: int = 30) -> dict[str, Any]:
    cutoff = datetime.now(tz=timezone.utc) - timedelta(days=max(1, lookback_days))
    q = db.query(Ticket).filter(
        Ticket.status.in_([TicketStatus.resolved.value, TicketStatus.closed.value]),
        Ticket.prediction_generated_at.isnot(None),
        Ticket.prediction_generated_at >= cutoff,
    )
    org_users = _org_user_ids(db, organization_id)
    if org_users:
        q = q.filter(
            (Ticket.requester_user_id.in_(org_users))
            | (Ticket.assigned_to_user_id.in_(org_users))
            | (Ticket.created_by_user_id.in_(org_users))
        )

    rows = q.all()
    evaluated = 0
    mae_sum = 0.0
    severity_hits = 0
    severity_total = 0

    for t in rows:
        pred = getattr(t, "predicted_resolution_minutes", None)
        actual = getattr(t, "resolution_minutes", None)
        if pred is not None and actual is not None and float(actual) > 0:
            mae_sum += abs(float(pred) - float(actual))
            evaluated += 1

        pred_s = (getattr(t, "predicted_severity", None) or "").lower()
        priority = str(getattr(getattr(t, "priority", None), "value", getattr(t, "priority", ""))).lower()
        if pred_s and priority:
            severity_total += 1
            if (pred_s == "critical" and "critical" in priority) or (pred_s == "high" and "high" in priority):
                severity_hits += 1
            elif pred_s == "medium" and ("medium" in priority or "normal" in priority):
                severity_hits += 1
            elif pred_s == "low" and "low" in priority:
                severity_hits += 1

    mae = round(mae_sum / evaluated, 2) if evaluated else None
    severity_acc = round(severity_hits / severity_total, 4) if severity_total else None

    score = 1.0
    if mae is not None:
        score -= min(0.7, mae / 1200.0)
    if severity_acc is not None:
        score -= (1.0 - severity_acc) * 0.3
    score = round(max(0.0, min(1.0, score)), 4)

    status = "healthy"
    if evaluated < 10 or (mae is not None and mae > 360) or (severity_acc is not None and severity_acc < 0.45):
        status = "attention"
    if evaluated == 0:
        status = "insufficient_data"

    return {
        "model": "itsm_predictive",
        "organization_id": organization_id,
        "lookback_days": lookback_days,
        "samples": len(rows),
        "evaluated_resolution": evaluated,
        "mae_minutes": mae,
        "severity_accuracy": severity_acc,
        "score": score,
        "status": status,
        "evaluated_at": _iso_now(),
    }


def evaluate_bi_model_health(db: Session, *, organization_id: Optional[str]) -> dict[str, Any]:
    forecast = bi_intelligence_service.ml_forecast_prophet(
        db,
        organization_id=organization_id,
        metric_key="revenue",
        periods=2,
        frequency="MS",
    )
    overrun = bi_intelligence_service.ml_predict_project_overrun_lgbm(db, organization_id=organization_id)

    forecast_engine = str(forecast.get("engine", "unknown"))
    overrun_engine = str(overrun.get("engine", "unknown"))
    history_months = int(forecast.get("history_months", 0) or 0)

    # Check whether optional ML libraries are installed.
    # A fallback due to a missing library is an infrastructure issue, not a model quality issue.
    # Penalise lightly (-0.10) instead of heavily (-0.35) so the score reflects
    # model quality rather than deployment completeness.
    prophet_available = True
    try:
        import prophet  # noqa: F401
    except (ImportError, OSError):
        prophet_available = False

    lgbm_available = True
    try:
        import lightgbm  # noqa: F401
    except (ImportError, OSError):
        lgbm_available = False

    score = 1.0
    if "fallback" in forecast_engine:
        # Heavy penalty only if Prophet IS installed but still falling back (data problem).
        # Light penalty if it is a pure library-availability issue.
        score -= 0.10 if not prophet_available else 0.35
    if "heuristic" in overrun_engine:
        score -= 0.10 if not lgbm_available else 0.35
    score = round(max(0.0, min(1.0, score)), 4)

    # Forecasting quality is not meaningful with too little history.
    if history_months < 6:
        status = "insufficient_data"
    else:
        status = "healthy" if score >= 0.65 else "attention"

    return {
        "model": "bi_predictive",
        "organization_id": organization_id,
        "forecast_engine": forecast_engine,
        "overrun_engine": overrun_engine,
        "history_months": history_months,
        "forecast_library_available": prophet_available,
        "overrun_library_available": lgbm_available,
        "score": score,
        "status": status,
        "evaluated_at": _iso_now(),
    }


def _should_retrain(meta: dict, evaluation: dict, *, max_age_days: int, attention_status: str = "attention") -> bool:
    last_retrained = _parse_dt(meta.get("last_retrained_at"))
    stale = True
    if last_retrained is not None:
        stale = last_retrained < (datetime.now(tz=timezone.utc) - timedelta(days=max_age_days))
    return stale or evaluation.get("status") == attention_status


def run_periodic_evaluation_and_retraining(db: Session) -> dict[str, Any]:
    orgs = [r[0] for r in db.query(User.organization_id).filter(User.organization_id.isnot(None)).distinct().all()]
    if not orgs:
        orgs = [None]

    summary = {
        "evaluated_at": _iso_now(),
        "organizations": 0,
        "itsm_retrained": 0,
        "bi_retrained": 0,
        "results": [],
    }

    for org_id in orgs:
        itsm_eval = evaluate_itsm_model_health(db, organization_id=org_id)
        bi_eval = evaluate_bi_model_health(db, organization_id=org_id)

        itsm_meta = _get_json(db, ITSM_META_KEY, org_id, default={})
        bi_meta = _get_json(db, BI_META_KEY, org_id, default={})

        itsm_trigger = _should_retrain(itsm_meta, itsm_eval, max_age_days=7)
        bi_trigger = _should_retrain(bi_meta, bi_eval, max_age_days=14)

        if itsm_trigger:
            baseline = predictive_analytics_service.recompute_predictive_baselines(db, organization_id=org_id)
            itsm_meta = {
                "last_retrained_at": _iso_now(),
                "reason": "attention_or_stale",
                "baseline_samples": baseline.get("samples", 0),
            }
            _set_json(db, ITSM_META_KEY, org_id, itsm_meta, "ITSM predictive retraining metadata")
            summary["itsm_retrained"] += 1

        if bi_trigger:
            bi_intelligence_service.ml_detect_anomalies_multivariate(db, organization_id=org_id)
            bi_intelligence_service.ml_predict_project_overrun_lgbm(db, organization_id=org_id)
            bi_meta = {
                "last_retrained_at": _iso_now(),
                "reason": "attention_or_stale",
                "forecast_engine": bi_eval.get("forecast_engine"),
                "overrun_engine": bi_eval.get("overrun_engine"),
            }
            _set_json(db, BI_META_KEY, org_id, bi_meta, "BI predictive retraining metadata")
            summary["bi_retrained"] += 1

        summary["results"].append(
            {
                "organization_id": org_id,
                "itsm": {"evaluation": itsm_eval, "triggered": itsm_trigger},
                "bi": {"evaluation": bi_eval, "triggered": bi_trigger},
            }
        )

    _set_json(db, LAST_EVAL_KEY, None, summary, "Predictive evaluation cycle summary")
    db.commit()
    summary["organizations"] = len(summary["results"])
    return summary
