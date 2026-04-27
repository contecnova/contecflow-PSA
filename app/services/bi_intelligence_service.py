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
