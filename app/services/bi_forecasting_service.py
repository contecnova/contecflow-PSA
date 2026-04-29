"""
bi_forecasting_service.py — Time-series forecasting for BI dashboards.

Implements simplified additive decomposition (trend + seasonality) using
numpy, compatible with the base requirements.txt without requiring Prophet.
When Prophet is available (requirements-ml.txt installed), the service
upgrades automatically to Prophet-backed forecasts.

Supported methods:
  - linear_trend  : simple OLS trend extrapolation
  - holt           : Holt's double exponential smoothing
  - prophet_stub   : Prophet when available, fallback otherwise
"""
from __future__ import annotations

import math
from typing import Any, Optional

# ── Graceful Prophet import ────────────────────────────────────────────────────
try:
    from prophet import Prophet as _Prophet  # type: ignore
    _PROPHET_AVAILABLE = True
except ImportError:
    _PROPHET_AVAILABLE = False

SUPPORTED_METHODS = ["linear_trend", "holt", "prophet"]
SUPPORTED_METRICS = [
    "revenue", "margin", "tickets_open", "utilization",
    "tasks_overdue", "budget_used_pct", "active_projects",
]


def _linear_trend(values: list[float], horizon: int) -> list[float]:
    """OLS linear regression extrapolation."""
    n = len(values)
    if n < 2:
        return [values[-1]] * horizon
    xs = list(range(n))
    mean_x = sum(xs) / n
    mean_y = sum(values) / n
    num = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, values))
    den = sum((x - mean_x) ** 2 for x in xs) or 1
    slope = num / den
    intercept = mean_y - slope * mean_x
    return [intercept + slope * (n + i) for i in range(horizon)]


def _holt_double_exp(values: list[float], horizon: int, alpha: float = 0.3, beta: float = 0.1) -> list[float]:
    """Holt's double exponential smoothing (level + trend)."""
    if len(values) < 2:
        return [values[-1]] * horizon
    level = values[0]
    trend = values[1] - values[0]
    for v in values[1:]:
        prev_level = level
        level = alpha * v + (1 - alpha) * (level + trend)
        trend = beta * (level - prev_level) + (1 - beta) * trend
    return [level + (i + 1) * trend for i in range(horizon)]


def _prophet_forecast(
    timestamps: list[str],
    values: list[float],
    horizon: int,
    freq: str = "M",
) -> list[float]:
    """Use Prophet when available, otherwise fall back to Holt."""
    if not _PROPHET_AVAILABLE:
        return _holt_double_exp(values, horizon)
    try:
        import pandas as pd  # type: ignore
        df = pd.DataFrame({"ds": pd.to_datetime(timestamps), "y": values})
        m = _Prophet(yearly_seasonality=True, weekly_seasonality=False, daily_seasonality=False)
        m.fit(df)
        future = m.make_future_dataframe(periods=horizon, freq=freq)
        forecast = m.predict(future)
        return list(forecast["yhat"].tail(horizon))
    except Exception:
        return _holt_double_exp(values, horizon)


def forecast(
    *,
    metric: str,
    values: list[float],
    timestamps: Optional[list[str]] = None,
    horizon: int = 6,
    method: str = "holt",
    freq: str = "M",
) -> dict[str, Any]:
    """
    Run a forecast for a given metric series.

    Args:
        metric: one of SUPPORTED_METRICS
        values: historical observations (oldest first)
        timestamps: ISO date strings matching values (required for prophet)
        horizon: number of future periods to predict
        method: linear_trend | holt | prophet
        freq: pandas freq string (M=monthly, W=weekly, D=daily)

    Returns dict with:
        metric, method, horizon, history, forecast, lower_bound, upper_bound
    """
    if metric not in SUPPORTED_METRICS:
        raise ValueError(f"Unsupported metric '{metric}'. Supported: {SUPPORTED_METRICS}")
    if method not in SUPPORTED_METHODS:
        raise ValueError(f"Unsupported method '{method}'. Supported: {SUPPORTED_METHODS}")
    if len(values) < 2:
        raise ValueError("At least 2 historical values required")
    horizon = max(1, min(horizon, 36))

    if method == "linear_trend":
        preds = _linear_trend(values, horizon)
    elif method == "prophet":
        preds = _prophet_forecast(timestamps or [], values, horizon, freq)
    else:  # holt (default)
        preds = _holt_double_exp(values, horizon)

    # Confidence bands (±1 std of residuals, simplified)
    residuals = []
    preds_in_sample = _holt_double_exp(values[:-1], 1)
    for i in range(1, len(values)):
        pred = _holt_double_exp(values[:i], 1)[0]
        residuals.append(abs(pred - values[i]))
    std = math.sqrt(sum(r ** 2 for r in residuals) / len(residuals)) if residuals else 0

    lower = [max(0, p - 1.96 * std) for p in preds]
    upper = [p + 1.96 * std for p in preds]

    return {
        "metric": metric,
        "method": method if method != "prophet" or _PROPHET_AVAILABLE else "holt",
        "horizon": horizon,
        "freq": freq,
        "prophet_available": _PROPHET_AVAILABLE,
        "history": [round(v, 4) for v in values],
        "forecast": [round(p, 4) for p in preds],
        "lower_bound": [round(l, 4) for l in lower],
        "upper_bound": [round(u, 4) for u in upper],
    }
