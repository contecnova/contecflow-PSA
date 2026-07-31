"""
bi_forecasting.py — BI Forecasting REST endpoints.

Routes:
  POST /bi/forecast                 — run a forecast for a metric series
  GET  /bi/forecast/metrics         — list supported metrics and methods
  POST /bi/forecast/multi           — batch forecast (multiple metrics in one call)
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.core.ratelimit import limiter
from app.core.responses import APIResponse
from app.db.session import get_db
from app.models.user import User
from app.services import bi_forecasting_service as svc

router = APIRouter()


class ForecastIn(BaseModel):
    metric: str = Field(..., description="Metric key to forecast")
    values: list[float] = Field(default_factory=list, min_length=0, max_length=120)
    timestamps: Optional[list[str]] = Field(None, description="ISO date strings (required for prophet method)")
    horizon: int = Field(6, ge=1, le=36)
    method: str = Field("holt", description="linear_trend | holt | prophet")
    freq: str = Field("M", description="M=monthly, W=weekly, D=daily")
    periods: Optional[int] = Field(None, ge=1, le=36)


class MultiForecastIn(BaseModel):
    forecasts: list[ForecastIn] = Field(default_factory=list, min_length=0, max_length=10)
    metrics: list[str] = Field(default_factory=list, min_length=0, max_length=10)
    method: Optional[str] = None
    periods: Optional[int] = None


@router.get("/bi/forecast/metrics", summary="Métricas y métodos de forecasting soportados")
@limiter.limit("60/minute")
def get_forecast_metrics(
    request: Request,
    current_user: User = Depends(get_current_user),
):
    return APIResponse.ok(data={
        "metrics": svc.SUPPORTED_METRICS,
        "methods": svc.SUPPORTED_METHODS,
        "prophet_available": svc._PROPHET_AVAILABLE,
        "arima_available": svc._STATSMODELS_AVAILABLE,
    })


@router.post("/bi/forecast", summary="Ejecutar forecast para una serie de métricas")
@limiter.limit("30/minute")
def run_forecast(
    request: Request,
    body: ForecastIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        method = body.method
        if method == "linear":
            method = "linear_trend"

        metric = body.metric
        metric_aliases = {
            "tickets": "tickets_open",
            "hours": "utilization",
            "response_time": "budget_used_pct",
        }
        metric = metric_aliases.get(metric, metric)

        values = list(body.values or [])
        if not values:
            from app.services.bi_smart_alerts_service import _fetch_metric_series  # noqa: PLC0415

            org_id = getattr(current_user, "organization_id", None)
            values = _fetch_metric_series(db, metric, org_id)

        if len(values) < 2:
            raise ValueError("At least 2 historical values required")

        horizon = body.periods or body.horizon
        timestamps = body.timestamps
        if method == "prophet" and not timestamps:
            # Synthesize monthly timestamps ending at the current month (handles
            # len(values) > 12 correctly, unlike a fixed-year/month formatting).
            from datetime import date as _date
            _today = _date.today()
            _base = _today.year * 12 + (_today.month - 1)
            _n = len(values)
            timestamps = []
            for _i in range(_n):
                _idx = _base - (_n - 1 - _i)
                _y, _m = divmod(_idx, 12)
                timestamps.append(f"{_y:04d}-{_m + 1:02d}-01")

        result = svc.forecast(
            metric=metric,
            values=values,
            timestamps=timestamps,
            horizon=horizon,
            method=method,
            freq=body.freq,
        )
        return APIResponse.ok(data=result)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


@router.post("/bi/forecast/multi", summary="Batch forecast para múltiples métricas")
@limiter.limit("20/minute")
def run_multi_forecast(
    request: Request,
    body: MultiForecastIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    items = list(body.forecasts or [])
    if not items and body.metrics:
        items = [
            ForecastIn(metric=metric, method=body.method or "holt", periods=body.periods or 6)
            for metric in body.metrics
        ]

    results = []
    errors = []
    for item in items:
        try:
            payload = run_forecast(request, item, db, current_user)
            r = payload.data
            results.append(r)
        except ValueError as exc:
            errors.append({"metric": item.metric, "error": str(exc)})
    return APIResponse.ok(data={"results": results, "forecasts": results, "errors": errors, "total": len(results)})
