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

from app.core.deps import get_current_user
from app.core.ratelimit import limiter
from app.models.user import User
from app.services import bi_forecasting_service as svc

router = APIRouter()


class ForecastIn(BaseModel):
    metric: str = Field(..., description="Metric key to forecast")
    values: list[float] = Field(..., min_length=2, max_length=120)
    timestamps: Optional[list[str]] = Field(None, description="ISO date strings (required for prophet method)")
    horizon: int = Field(6, ge=1, le=36)
    method: str = Field("holt", description="linear_trend | holt | prophet")
    freq: str = Field("M", description="M=monthly, W=weekly, D=daily")


class MultiForecastIn(BaseModel):
    forecasts: list[ForecastIn] = Field(..., min_length=1, max_length=10)


@router.get("/bi/forecast/metrics", summary="Métricas y métodos de forecasting soportados")
@limiter.limit("60/minute")
def get_forecast_metrics(
    request: Request,
    current_user: User = Depends(get_current_user),
):
    return {
        "metrics": svc.SUPPORTED_METRICS,
        "methods": svc.SUPPORTED_METHODS,
        "prophet_available": svc._PROPHET_AVAILABLE,
    }


@router.post("/bi/forecast", summary="Ejecutar forecast para una serie de métricas")
@limiter.limit("30/minute")
def run_forecast(
    request: Request,
    body: ForecastIn,
    current_user: User = Depends(get_current_user),
):
    try:
        result = svc.forecast(
            metric=body.metric,
            values=body.values,
            timestamps=body.timestamps,
            horizon=body.horizon,
            method=body.method,
            freq=body.freq,
        )
        return result
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


@router.post("/bi/forecast/multi", summary="Batch forecast para múltiples métricas")
@limiter.limit("20/minute")
def run_multi_forecast(
    request: Request,
    body: MultiForecastIn,
    current_user: User = Depends(get_current_user),
):
    results = []
    errors = []
    for item in body.forecasts:
        try:
            r = svc.forecast(
                metric=item.metric,
                values=item.values,
                timestamps=item.timestamps,
                horizon=item.horizon,
                method=item.method,
                freq=item.freq,
            )
            results.append(r)
        except ValueError as exc:
            errors.append({"metric": item.metric, "error": str(exc)})
    return {"results": results, "errors": errors, "total": len(results)}
