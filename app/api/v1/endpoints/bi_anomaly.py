"""
bi_anomaly.py — BI Anomaly Detection and Churn Prediction endpoints.

Routes:
  POST /bi/anomaly/detect         — detect anomalies in a metric series
  POST /bi/churn/predict          — predict churn for a list of clients
  GET  /bi/anomaly/info           — capabilities info
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field

from app.core.deps import get_current_user
from app.core.ratelimit import limiter
from app.models.user import User
from app.services import bi_anomaly_service as svc

router = APIRouter()


class AnomalyDetectIn(BaseModel):
    values: list[float] = Field(..., min_length=4, max_length=500)
    contamination: float = Field(0.1, ge=0.01, le=0.5)
    method: str = Field("auto", description="auto | isolation_forest | zscore")


class ClientFeaturesIn(BaseModel):
    client_id: str
    client_name: str = ""
    tickets_last_30d: float = 0
    response_time_avg_h: float = 0
    nps_score: float = 7
    contract_renewal_days: float = 90
    support_escalations: float = 0
    last_login_days_ago: float = 0
    active_projects: float = 0


class ChurnPredictIn(BaseModel):
    clients: list[ClientFeaturesIn] = Field(..., min_length=1, max_length=200)


@router.get("/bi/anomaly/info", summary="Información sobre capacidades de detección de anomalías")
@limiter.limit("60/minute")
def anomaly_info(
    request: Request,
    current_user: User = Depends(get_current_user),
):
    return {
        "sklearn_available": svc._SKLEARN_AVAILABLE,
        "lgbm_available": svc._LGBM_AVAILABLE,
        "methods": ["auto", "isolation_forest", "zscore"],
        "churn_features": svc.CHURN_FEATURES,
    }


@router.post("/bi/anomaly/detect", summary="Detectar anomalías en una serie temporal")
@limiter.limit("30/minute")
def detect_anomalies(
    request: Request,
    body: AnomalyDetectIn,
    current_user: User = Depends(get_current_user),
):
    try:
        return svc.detect_anomalies(
            values=body.values,
            contamination=body.contamination,
            method=body.method,
        )
    except ValueError as exc:
        from fastapi import HTTPException
        raise HTTPException(status_code=422, detail=str(exc))


@router.post("/bi/churn/predict", summary="Predicción de churn de clientes con LightGBM")
@limiter.limit("20/minute")
def predict_churn(
    request: Request,
    body: ChurnPredictIn,
    current_user: User = Depends(get_current_user),
):
    clients_data: list[dict[str, Any]] = [c.model_dump() for c in body.clients]
    return svc.predict_churn(clients=clients_data)
