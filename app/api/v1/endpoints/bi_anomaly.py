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

from app.core.deps import get_current_user, require_internal_user
from app.core.responses import APIResponse
from app.db.session import get_db
from app.core.ratelimit import limiter
from app.models.user import User
from app.services import bi_anomaly_service as svc
from sqlalchemy.orm import Session

router = APIRouter()


class AnomalyDetectIn(BaseModel):
    values: list[float] = Field(default_factory=list, min_length=0, max_length=500)
    contamination: float = Field(0.1, ge=0.01, le=0.5)
    method: str = Field("auto", description="auto | isolation_forest | zscore")
    metric: str | None = None
    data_points: list[float] | None = None


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
    clients: list[ClientFeaturesIn] = Field(default_factory=list, min_length=0, max_length=200)
    client_id: str | None = None
    client_name: str = ""
    features: dict[str, Any] | None = None


@router.get("/bi/anomaly/info", summary="Información sobre capacidades de detección de anomalías")
@limiter.limit("60/minute")
def anomaly_info(
    request: Request,
    current_user: User = Depends(get_current_user),
):
    return APIResponse.ok(data={
        "sklearn_available": svc._SKLEARN_AVAILABLE,
        "lgbm_available": svc._LGBM_AVAILABLE,
        "methods": ["auto", "isolation_forest", "zscore"],
        "churn_features": svc.CHURN_FEATURES,
    })


@router.post("/bi/anomaly/detect", summary="Detectar anomalías en una serie temporal")
@limiter.limit("30/minute")
def detect_anomalies(
    request: Request,
    body: AnomalyDetectIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _rol: User = Depends(require_internal_user),  # auditoria 2026-09: dominio: analitica interna
):
    try:
        values = [float(v) for v in (body.values or [])]
        if not values and body.data_points:
            values = [float(v) for v in body.data_points]

        if not values and body.metric:
            from app.services.bi_smart_alerts_service import _fetch_metric_series

            org_id = getattr(current_user, "organization_id", None)
            values = _fetch_metric_series(db, str(body.metric), org_id)

        if len(values) < 4:
            raise ValueError("At least 4 data points required for anomaly detection")

        result = svc.detect_anomalies(
            values=values,
            contamination=body.contamination,
            method=body.method,
        )
        # Backward compatibility with legacy frontend/tests.
        result["anomalies"] = [
            {
                "index": idx,
                "value": round(float(values[idx]), 4),
                "score": result["anomaly_scores"][idx],
            }
            for idx in result["anomaly_indices"]
        ]
        return APIResponse.ok(data=result)
    except ValueError as exc:
        from fastapi import HTTPException
        raise HTTPException(status_code=422, detail=str(exc))


@router.post("/bi/churn/predict", summary="Predicción de churn de clientes con LightGBM")
@limiter.limit("20/minute")
def predict_churn(
    request: Request,
    body: ChurnPredictIn,
    current_user: User = Depends(get_current_user),
    _rol: User = Depends(require_internal_user),  # auditoria 2026-09: dominio: analitica interna
):
    clients_data: list[dict[str, Any]] = [c.model_dump() for c in (body.clients or [])]

    # Legacy single-client contract: {client_id, features: {...}}
    if not clients_data and body.client_id:
        raw_features = body.features or {}
        clients_data = [
            {
                "client_id": body.client_id,
                "client_name": body.client_name,
                "tickets_last_30d": raw_features.get("support_tickets_last_90d", raw_features.get("tickets_last_30d", 0)),
                "response_time_avg_h": raw_features.get("response_time_avg_h", 0),
                "nps_score": raw_features.get("nps_score", 7),
                "contract_renewal_days": raw_features.get("contract_months_remaining", 6) * 30,
                "support_escalations": raw_features.get("support_escalations", 0),
                "last_login_days_ago": max(0, 30 - float(raw_features.get("logins_last_30d", 0))),
                "active_projects": raw_features.get("active_projects", 0),
            }
        ]

    if not clients_data:
        from fastapi import HTTPException

        raise HTTPException(status_code=422, detail="clients_required")

    out = svc.predict_churn(clients=clients_data)
    if body.client_id and out.get("clients"):
        first = dict(out["clients"][0])
        first["method_used"] = out.get("method_used")
        return APIResponse.ok(data=first)
    return APIResponse.ok(data=out)
