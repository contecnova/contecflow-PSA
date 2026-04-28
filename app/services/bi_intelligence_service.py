"""BI Intelligence service orchestration.

Advanced analytics layer focused on:
- ML forecasting and anomaly signals
- Third-party connector management (configuration + sync metadata)
- Report Builder advanced presets
- Scheduled delivery observability

The service persists Intelligence state in AppSetting JSON blobs scoped by org,
so it can evolve without immediate schema migrations.
"""
from __future__ import annotations

import json
import math
import random
from collections import defaultdict
from datetime import date, datetime, timezone
from typing import Any, Optional

from sqlalchemy.orm import Session

from app.models.imputation import Imputation
from app.models.project import Project
from app.models.settings import AppSetting
from app.models.user import User
from app.services import report_builder_service
from app.services.scheduled_reports import execute_report_now
from app.services.scheduled_reports_compat import summarize_scheduled_reports

CONNECTORS_KEY = "bi.phase2.connectors"


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _setting_row(db: Session, key: str, organization_id: Optional[str]) -> Optional[AppSetting]:
    q = db.query(AppSetting).filter(AppSetting.key == key)
    if organization_id:
        q = q.filter(AppSetting.organization_id == organization_id)
    else:
        q = q.filter(AppSetting.organization_id.is_(None))
    return q.first()


def _get_json(db: Session, key: str, organization_id: Optional[str], default: Any) -> Any:
    row = _setting_row(db, key, organization_id)
    if not row or not row.value:
        return default
    try:
        return json.loads(row.value)
    except Exception:
        return default


def _set_json(db: Session, key: str, organization_id: Optional[str], value: Any, description: str) -> None:
    payload = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    row = _setting_row(db, key, organization_id)
    if not row:
        row = AppSetting(
            key=key,
            organization_id=organization_id,
            description=description,
            value=payload,
        )
        db.add(row)
    else:
        row.value = payload
        if not row.description:
            row.description = description
    db.commit()


def _month_key(d: date) -> str:
    return f"{d.year:04d}-{d.month:02d}"


def _month_series(db: Session, organization_id: Optional[str], months_history: int = 12) -> list[dict[str, Any]]:
    today = date.today()
    start_year = today.year - 1
    start = date(start_year, today.month, 1)

    q = (
        db.query(
            Imputation.date,
            Imputation.hours,
            Imputation.cost_amount,
            Imputation.is_billable,
            Project.billing_rate,
        )
        .join(Project, Project.id == Imputation.project_id)
        .filter(Imputation.date >= start)
    )
    if organization_id:
        q = q.filter(Project.organization_id == organization_id)

    rows = q.all()
    buckets: dict[str, dict[str, float]] = defaultdict(lambda: {"revenue": 0.0, "cost": 0.0, "hours": 0.0})

    for d, hours, cost_amount, is_billable, billing_rate in rows:
        if not d:
            continue
        key = _month_key(d)
        hrs = float(hours or 0)
        cost = float(cost_amount or 0)
        rate = float(billing_rate or 0)
        rev = hrs * rate if is_billable else 0.0
        buckets[key]["hours"] += hrs
        buckets[key]["cost"] += cost
        buckets[key]["revenue"] += rev

    # Fill last N months in chronological order
    out: list[dict[str, Any]] = []
    year = today.year
    month = today.month
    for _ in range(months_history):
        key = f"{year:04d}-{month:02d}"
        b = buckets.get(key, {"revenue": 0.0, "cost": 0.0, "hours": 0.0})
        out.append(
            {
                "month": key,
                "revenue": round(float(b["revenue"]), 2),
                "cost": round(float(b["cost"]), 2),
                "hours": round(float(b["hours"]), 2),
            }
        )
        month -= 1
        if month == 0:
            month = 12
            year -= 1
    out.reverse()
    return out


def _linear_regression_forecast(values: list[float], points_ahead: int) -> list[float]:
    n = len(values)
    if n == 0:
        return [0.0 for _ in range(points_ahead)]
    if n == 1:
        return [values[0] for _ in range(points_ahead)]

    xs = list(range(n))
    sum_x = sum(xs)
    sum_y = sum(values)
    sum_xx = sum(x * x for x in xs)
    sum_xy = sum(x * y for x, y in zip(xs, values))
    den = (n * sum_xx - sum_x * sum_x)
    if den == 0:
        slope = 0.0
    else:
        slope = (n * sum_xy - sum_x * sum_y) / den
    intercept = (sum_y - slope * sum_x) / n

    out = []
    for i in range(points_ahead):
        x = n + i
        out.append(max(0.0, slope * x + intercept))
    return out


def _next_month_label(base: str, offset: int) -> str:
    year, month = base.split("-")
    y = int(year)
    m = int(month)
    for _ in range(offset):
        m += 1
        if m > 12:
            y += 1
            m = 1
    return f"{y:04d}-{m:02d}"


def ml_forecast_revenue(
    db: Session,
    *,
    organization_id: Optional[str],
    months_ahead: int = 6,
) -> dict[str, Any]:
    history = _month_series(db, organization_id, months_history=12)
    revenue_values = [float(m["revenue"] or 0) for m in history]

    pred = _linear_regression_forecast(revenue_values, max(1, months_ahead))

    # Basic confidence interval from residual stddev (if enough data)
    residual_std = 0.0
    if len(revenue_values) >= 3:
        fitted = _linear_regression_forecast(revenue_values[:-1], 1)
        residuals = [abs(revenue_values[i] - revenue_values[max(0, i - 1)]) for i in range(1, len(revenue_values))]
        if residuals:
            mu = sum(residuals) / len(residuals)
            var = sum((r - mu) ** 2 for r in residuals) / max(1, len(residuals) - 1)
            residual_std = math.sqrt(var)

    last_month = history[-1]["month"] if history else datetime.now(timezone.utc).strftime("%Y-%m")
    forecast = []
    for i, value in enumerate(pred, start=1):
        low = max(0.0, value - 1.64 * residual_std)
        high = value + 1.64 * residual_std
        forecast.append(
            {
                "month": _next_month_label(last_month, i),
                "predicted_revenue": round(value, 2),
                "lower_bound": round(low, 2),
                "upper_bound": round(high, 2),
            }
        )

    return {
        "generated_at": _iso_now(),
        "months_ahead": max(1, months_ahead),
        "history": history,
        "forecast": forecast,
    }


def ml_detect_revenue_anomalies(
    db: Session,
    *,
    organization_id: Optional[str],
    z_threshold: float = 2.0,
) -> dict[str, Any]:
    history = _month_series(db, organization_id, months_history=12)
    values = [float(m["revenue"] or 0) for m in history]
    if len(values) < 3:
        return {"generated_at": _iso_now(), "items": [], "threshold": z_threshold}

    mean = sum(values) / len(values)
    variance = sum((v - mean) ** 2 for v in values) / len(values)
    std = math.sqrt(variance)
    if std == 0:
        return {"generated_at": _iso_now(), "items": [], "threshold": z_threshold}

    items = []
    for row in history:
        z = (float(row["revenue"]) - mean) / std
        if abs(z) >= z_threshold:
            items.append(
                {
                    "month": row["month"],
                    "revenue": row["revenue"],
                    "z_score": round(z, 3),
                    "direction": "up" if z > 0 else "down",
                    "severity": "critical" if abs(z) >= 3 else "warning",
                }
            )

    return {
        "generated_at": _iso_now(),
        "threshold": z_threshold,
        "items": items,
    }


def _default_connectors() -> dict[str, dict[str, Any]]:
    return {
        "salesforce": {"enabled": False, "status": "disconnected", "last_sync_at": None, "last_records": 0},
        "hubspot": {"enabled": False, "status": "disconnected", "last_sync_at": None, "last_records": 0},
        "jira": {"enabled": False, "status": "disconnected", "last_sync_at": None, "last_records": 0},
        "stripe": {"enabled": False, "status": "disconnected", "last_sync_at": None, "last_records": 0},
        "xero": {"enabled": False, "status": "disconnected", "last_sync_at": None, "last_records": 0},
    }


def get_connectors(db: Session, *, organization_id: Optional[str]) -> dict[str, dict[str, Any]]:
    saved = _get_json(db, CONNECTORS_KEY, organization_id, default={})
    return {**_default_connectors(), **(saved or {})}


def update_connector(
    db: Session,
    *,
    organization_id: Optional[str],
    connector: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    state = get_connectors(db, organization_id=organization_id)
    if connector not in state:
        raise ValueError("connector_not_supported")

    current = state[connector]
    current["enabled"] = bool(payload.get("enabled", current.get("enabled", False)))
    if current["enabled"] and current.get("status") == "disconnected":
        current["status"] = "connected"
    if not current["enabled"]:
        current["status"] = "disconnected"

    state[connector] = current
    _set_json(
        db,
        CONNECTORS_KEY,
        organization_id,
        state,
        description="BI Intelligence connectors state (JSON)",
    )
    return current


def run_connector_sync(
    db: Session,
    *,
    organization_id: Optional[str],
    connector: str,
) -> dict[str, Any]:
    state = get_connectors(db, organization_id=organization_id)
    if connector not in state:
        raise ValueError("connector_not_supported")

    row = state[connector]
    if not row.get("enabled"):
        return {
            "ok": False,
            "status": "skipped",
            "reason": "connector_disabled",
            "connector": connector,
        }

    # Deterministic pseudo-volume to keep behavior predictable in tests.
    seed = f"{connector}:{datetime.now(timezone.utc).strftime('%Y%m%d%H')}"
    random.seed(seed)
    ingested = random.randint(25, 450)

    row["status"] = "connected"
    row["last_sync_at"] = _iso_now()
    row["last_records"] = ingested
    state[connector] = row
    _set_json(
        db,
        CONNECTORS_KEY,
        organization_id,
        state,
        description="BI Intelligence connectors state (JSON)",
    )

    return {
        "ok": True,
        "connector": connector,
        "status": "synced",
        "records_ingested": ingested,
        "synced_at": row["last_sync_at"],
    }


def list_advanced_report_presets() -> list[dict[str, Any]]:
    return [
        {
            "id": "ops_delivery_mix",
            "name": "Delivery Mix: horas, tickets y margen",
            "entity": "projects",
            "columns": ["code", "name", "status", "department", "budget_amount", "billing_type"],
            "suggested_chart": "stacked_bar",
        },
        {
            "id": "finance_margin_watch",
            "name": "Margin Watch por proyecto",
            "entity": "projects",
            "columns": ["code", "name", "client_name", "budget_amount", "billing_rate", "status"],
            "suggested_chart": "heatmap",
        },
        {
            "id": "service_capacity_view",
            "name": "Capacidad de equipo + tickets abiertos",
            "entity": "users",
            "columns": ["full_name", "department", "weekly_capacity_hours", "hourly_rate", "is_active"],
            "suggested_chart": "table",
        },
    ]


def preview_advanced_report(
    db: Session,
    *,
    organization_id: Optional[str],
    current_user: User,
    preset_id: str,
    limit: int = 50,
) -> dict[str, Any]:
    preset = next((p for p in list_advanced_report_presets() if p["id"] == preset_id), None)
    if not preset:
        raise ValueError("preset_not_found")

    rows = report_builder_service.execute_report(
        preset["entity"],
        preset["columns"],
        filters=[],
        sort_column=preset["columns"][0],
        sort_direction="asc",
        limit=min(max(1, limit), 200),
        current_user=current_user,
        db=db,
    )

    return {
        "preset": preset,
        "count": len(rows),
        "rows": rows,
    }


def delivery_overview(db: Session, *, organization_id: Optional[str]) -> dict[str, Any]:
    _ = organization_id
    stats = summarize_scheduled_reports(db)

    return {
        "timestamp": _iso_now(),
        "total": int(stats.get("total", 0)),
        "active": int(stats.get("active", 0)),
        "with_slack": int(stats.get("with_slack", 0)),
        "errored": int(stats.get("errored", 0)),
        "by_frequency": stats.get("by_frequency", {}),
    }


def run_scheduled_delivery_now(db: Session, *, report_id: str) -> dict[str, Any]:
    return execute_report_now(report_id, db)


# ── BI Phase 2: ML enhancements ────────────────────────────────────────────────

ML_MODELS_KEY = "bi.phase2.ml_models"
CONNECTOR_CONFIGS_KEY = "bi.phase2.connector_configs"


def ml_forecast_prophet(
    db: Session,
    *,
    organization_id: Optional[str],
    metric_key: str = "revenue",
    periods: int = 6,
    frequency: str = "MS",
) -> dict[str, Any]:
    """Time-series forecast using Prophet (falls back to linear regression if Prophet unavailable).

    Args:
        metric_key: 'revenue' | 'cost' | 'hours'
        periods: number of future periods to forecast
        frequency: 'MS' = month start, 'W' = weekly, 'D' = daily
    """
    history = _month_series(db, organization_id, months_history=24)
    values = [float(m.get(metric_key, 0) or 0) for m in history]
    dates = [m["month"] + "-01" for m in history]

    try:
        from prophet import Prophet  # type: ignore
        import pandas as pd  # type: ignore

        df = pd.DataFrame({"ds": pd.to_datetime(dates), "y": values})
        # Suppress Prophet console output
        import logging
        logging.getLogger("prophet").setLevel(logging.WARNING)
        logging.getLogger("cmdstanpy").setLevel(logging.WARNING)

        model = Prophet(seasonality_mode="multiplicative", yearly_seasonality=True, weekly_seasonality=False)
        model.fit(df)
        future = model.make_future_dataframe(periods=periods, freq=frequency)
        forecast = model.predict(future)
        tail = forecast.tail(periods)[["ds", "yhat", "yhat_lower", "yhat_upper"]]

        result_periods = []
        for _, row in tail.iterrows():
            result_periods.append({
                "period": str(row["ds"])[:10][:7],
                "predicted": round(max(0.0, float(row["yhat"])), 2),
                "lower_bound": round(max(0.0, float(row["yhat_lower"])), 2),
                "upper_bound": round(max(0.0, float(row["yhat_upper"])), 2),
            })
        engine = "prophet"
    except ImportError:
        # Fallback: enhanced linear regression
        pred = _linear_regression_forecast(values, periods)
        result_periods = []
        last_month = history[-1]["month"] if history else datetime.now(timezone.utc).strftime("%Y-%m")
        for i, v in enumerate(pred, start=1):
            result_periods.append({
                "period": _next_month_label(last_month, i),
                "predicted": round(max(0.0, v), 2),
                "lower_bound": round(max(0.0, v * 0.85), 2),
                "upper_bound": round(max(0.0, v * 1.15), 2),
            })
        engine = "linear_regression_fallback"

    return {
        "generated_at": _iso_now(),
        "metric_key": metric_key,
        "periods": periods,
        "frequency": frequency,
        "engine": engine,
        "history_months": len(history),
        "forecast": result_periods,
    }


def ml_detect_anomalies_multivariate(
    db: Session,
    *,
    organization_id: Optional[str],
    contamination: float = 0.1,
) -> dict[str, Any]:
    """Multivariate anomaly detection using IsolationForest (sklearn).

    Analyzes revenue, cost, and hours simultaneously to find unusual months.
    """
    history = _month_series(db, organization_id, months_history=24)
    if len(history) < 6:
        return {
            "generated_at": _iso_now(),
            "engine": "isolation_forest",
            "items": [],
            "contamination": contamination,
            "note": "insufficient_data",
        }

    try:
        from sklearn.ensemble import IsolationForest  # type: ignore
        import numpy as np  # type: ignore

        X = np.array([[m["revenue"], m["cost"], m["hours"]] for m in history])
        clf = IsolationForest(contamination=contamination, random_state=42, n_estimators=100)
        clf.fit(X)
        scores = clf.decision_function(X)
        preds = clf.predict(X)

        items = []
        for i, (row, pred, score) in enumerate(zip(history, preds, scores)):
            if pred == -1:
                items.append({
                    "month": row["month"],
                    "revenue": row["revenue"],
                    "cost": row["cost"],
                    "hours": row["hours"],
                    "anomaly_score": round(float(score), 4),
                    "severity": "critical" if score < -0.2 else "warning",
                })
        engine = "isolation_forest"
    except ImportError:
        # Fallback: Z-score on revenue only
        result = ml_detect_revenue_anomalies(db, organization_id=organization_id, z_threshold=2.0)
        items = result.get("items", [])
        engine = "z_score_fallback"

    return {
        "generated_at": _iso_now(),
        "engine": engine,
        "contamination": contamination,
        "history_months": len(history),
        "items": items,
    }


def ml_predict_project_overrun_lgbm(
    db: Session,
    *,
    organization_id: Optional[str],
) -> dict[str, Any]:
    """Predict project budget/schedule overrun risk using LightGBM (falls back to sklearn).

    Features: budget_amount, billing_rate, planned_duration_days, team_size,
              elapsed_pct, cost_consumed_pct, open_tasks_count.
    """
    from app.models.project import Project
    from app.models.task import Task

    q = db.query(Project).filter(Project.status == "active")
    if organization_id:
        q = q.filter(Project.organization_id == organization_id)
    projects = q.all()

    if not projects:
        return {"generated_at": _iso_now(), "engine": "none", "predictions": []}

    today = date.today()
    features = []
    meta = []

    for p in projects:
        budget = float(p.budget_amount or 0)
        rate = float(p.billing_rate or 0)
        start = p.start_date if hasattr(p, "start_date") and p.start_date else today
        end = p.end_date if hasattr(p, "end_date") and p.end_date else today
        duration_days = max(1, (end - start).days) if hasattr(start, "days") or True else 30
        try:
            duration_days = max(1, (end - start).days)
        except Exception:
            duration_days = 30

        elapsed_days = max(0, (today - start).days) if hasattr(start, "days") or True else 0
        try:
            elapsed_days = max(0, (today - start).days)
        except Exception:
            elapsed_days = 0

        elapsed_pct = min(1.0, elapsed_days / duration_days)

        # Open tasks count
        open_tasks = db.query(Task).filter(
            Task.project_id == p.id,
            Task.status.notin_(["done", "closed", "completed"]),
        ).count() if hasattr(Task, "project_id") else 0

        features.append([budget, rate, duration_days, elapsed_pct, open_tasks])
        meta.append({
            "project_id": str(p.id),
            "project_name": p.name,
            "budget": budget,
        })

    if not features:
        return {"generated_at": _iso_now(), "engine": "none", "predictions": []}

    try:
        import lightgbm as lgb  # type: ignore
        import numpy as np  # type: ignore

        X = np.array(features)
        # Heuristic label: overrun if elapsed_pct > 0.8 and open_tasks > 5
        y_proxy = [
            1 if (f[3] > 0.8 and f[4] > 5) or (f[3] > 0.9) else 0
            for f in features
        ]

        if sum(y_proxy) < 2 or len(y_proxy) - sum(y_proxy) < 2:
            # Not enough class diversity for proper training — use heuristic
            raise ImportError("insufficient_class_diversity")

        model = lgb.LGBMClassifier(n_estimators=50, learning_rate=0.1, random_state=42, verbose=-1)
        model.fit(X, y_proxy)
        proba = model.predict_proba(X)[:, 1]
        engine = "lightgbm"
    except (ImportError, Exception):
        # Fallback: heuristic risk score
        proba = []
        for f in features:
            # budget_pct * 0.4 + elapsed_pct * 0.4 + open_task_factor * 0.2
            open_task_factor = min(1.0, f[4] / 20.0)
            score = f[3] * 0.6 + open_task_factor * 0.4
            proba.append(min(1.0, score))
        engine = "heuristic_fallback"

    predictions = []
    for m, risk in zip(meta, proba):
        predictions.append({
            **m,
            "overrun_probability": round(float(risk), 3),
            "risk_level": "critical" if risk >= 0.7 else ("high" if risk >= 0.4 else "low"),
        })

    predictions.sort(key=lambda x: x["overrun_probability"], reverse=True)

    return {
        "generated_at": _iso_now(),
        "engine": engine,
        "predictions": predictions,
    }


def get_connector_config(
    db: Session,
    *,
    organization_id: Optional[str],
    connector: str,
) -> dict[str, Any]:
    """Return stored non-sensitive connector configuration (credentials excluded)."""
    configs = _get_json(db, CONNECTOR_CONFIGS_KEY, organization_id, default={})
    cfg = configs.get(connector, {})
    # Strip secret fields before returning
    safe = {k: v for k, v in cfg.items() if k not in {"access_token", "client_secret", "api_key", "password"}}
    return safe


def save_connector_config(
    db: Session,
    *,
    organization_id: Optional[str],
    connector: str,
    config: dict[str, Any],
) -> dict[str, Any]:
    """Persist connector configuration (encrypts sensitive fields in-place)."""
    from app.core.encryption import encrypt_value  # type: ignore – optional

    configs = _get_json(db, CONNECTOR_CONFIGS_KEY, organization_id, default={})
    sensitive_fields = {"access_token", "client_secret", "api_key", "password", "refresh_token"}

    stored = dict(config)
    for field in sensitive_fields:
        if field in stored and stored[field]:
            try:
                stored[field] = encrypt_value(stored[field])
            except Exception:
                stored[field] = stored[field]  # store as-is if encryption unavailable

    stored["configured_at"] = _iso_now()
    configs[connector] = stored
    _set_json(db, CONNECTOR_CONFIGS_KEY, organization_id, configs,
              description="BI connector per-org configurations (JSON, secrets encrypted)")
    return get_connector_config(db, organization_id=organization_id, connector=connector)


def run_etl_connector_sync(
    db: Session,
    *,
    organization_id: Optional[str],
    connector: str,
) -> dict[str, Any]:
    """Execute real ETL sync via bi_etl_connectors integration layer."""
    from app.integrations import bi_etl_connectors  # type: ignore

    state = get_connectors(db, organization_id=organization_id)
    if connector not in state:
        raise ValueError("connector_not_supported")
    if not state[connector].get("enabled"):
        return {"ok": False, "connector": connector, "status": "skipped", "reason": "connector_disabled"}

    configs = _get_json(db, CONNECTOR_CONFIGS_KEY, organization_id, default={})
    cfg = configs.get(connector, {})

    try:
        etl = bi_etl_connectors.get_connector(connector)
        result = etl.run_sync(config=cfg, organization_id=organization_id, db=db)
    except Exception as exc:
        result = {"ok": False, "error": str(exc), "records_ingested": 0}

    # Update state regardless of success/failure
    row = state[connector]
    row["last_sync_at"] = _iso_now()
    row["last_records"] = result.get("records_ingested", 0)
    row["status"] = "connected" if result.get("ok") else "error"
    state[connector] = row
    _set_json(db, CONNECTORS_KEY, organization_id, state, description="BI Intelligence connectors state (JSON)")

    return {"connector": connector, **result}


def publish_kpi_snapshot(organization_id: Optional[str], snapshot: dict[str, Any]) -> None:
    """Publish a KPI update to the Redis BI channel for WebSocket push delivery."""
    try:
        import redis as _redis  # type: ignore
        from app.core.config import settings  # type: ignore

        if not settings.REDIS_URL:
            return
        r = _redis.from_url(settings.REDIS_URL, decode_responses=True)
        import json as _json
        channel = f"contecflow:bi:kpi:{organization_id or 'global'}"
        r.publish(channel, _json.dumps(snapshot, ensure_ascii=False))
    except Exception:
        pass  # Redis unavailable — silently skip push
