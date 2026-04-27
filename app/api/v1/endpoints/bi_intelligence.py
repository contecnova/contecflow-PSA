"""BI Intelligence endpoints.

Advanced analytics APIs: ML, connectors, realtime stream, report presets,
and scheduled delivery operations.
"""
from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.core.security import create_access_token, decode_token
from app.db.session import get_db, SessionLocal
from app.models.user import User
from app.services import bi_intelligence_service as svc

router = APIRouter()


class ConnectorPatchIn(BaseModel):
    enabled: bool


class AdvancedPreviewIn(BaseModel):
    preset_id: str = Field(..., min_length=3, max_length=120)
    limit: int = Field(50, ge=1, le=200)


@router.get("/bi/intelligence/ml/forecast/revenue", summary="Forecast de revenue BI Intelligence")
def phase2_revenue_forecast(
    months_ahead: int = Query(6, ge=1, le=18),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    org_id = getattr(current_user, "organization_id", None)
    return svc.ml_forecast_revenue(db, organization_id=org_id, months_ahead=months_ahead)


@router.get("/bi/intelligence/ml/anomalies/revenue", summary="Detección de anomalías de revenue BI Intelligence")
def phase2_revenue_anomalies(
    z_threshold: float = Query(2.0, ge=1.0, le=5.0),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    org_id = getattr(current_user, "organization_id", None)
    return svc.ml_detect_revenue_anomalies(db, organization_id=org_id, z_threshold=z_threshold)


@router.get("/bi/intelligence/connectors", summary="Estado conectores BI Intelligence")
def phase2_connectors(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    org_id = getattr(current_user, "organization_id", None)
    return {"items": svc.get_connectors(db, organization_id=org_id)}


@router.patch("/bi/intelligence/connectors/{connector}", summary="Activar/desactivar conector BI Intelligence")
def phase2_patch_connector(
    connector: str,
    payload: ConnectorPatchIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    org_id = getattr(current_user, "organization_id", None)
    try:
        data = svc.update_connector(
            db,
            organization_id=org_id,
            connector=connector,
            payload=payload.model_dump(),
        )
        return {"ok": True, "connector": connector, "config": data}
    except ValueError:
        raise HTTPException(status_code=404, detail="Conector no soportado")


@router.post("/bi/intelligence/connectors/{connector}/sync", summary="Ejecutar sync de conector BI Intelligence")
def phase2_sync_connector(
    connector: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    org_id = getattr(current_user, "organization_id", None)
    try:
        return svc.run_connector_sync(db, organization_id=org_id, connector=connector)
    except ValueError:
        raise HTTPException(status_code=404, detail="Conector no soportado")


@router.get("/bi/intelligence/reports/presets", summary="Presets de Report Builder avanzado BI Intelligence")
def phase2_report_presets(current_user: User = Depends(get_current_user)):
    _ = current_user
    return {"items": svc.list_advanced_report_presets()}


@router.post("/bi/intelligence/reports/preview", summary="Preview de preset avanzado BI Intelligence")
def phase2_report_preview(
    payload: AdvancedPreviewIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    org_id = getattr(current_user, "organization_id", None)
    try:
        return svc.preview_advanced_report(
            db,
            organization_id=org_id,
            current_user=current_user,
            preset_id=payload.preset_id,
            limit=payload.limit,
        )
    except ValueError:
        raise HTTPException(status_code=404, detail="Preset no encontrado")


@router.get("/bi/intelligence/delivery/overview", summary="Overview de scheduled delivery BI Intelligence")
def phase2_delivery_overview(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    org_id = getattr(current_user, "organization_id", None)
    return svc.delivery_overview(db, organization_id=org_id)


@router.post("/bi/intelligence/delivery/run/{report_id}", summary="Ejecutar envío de informe programado ahora")
def phase2_delivery_run_now(
    report_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _ = current_user
    return svc.run_scheduled_delivery_now(db, report_id=report_id)


@router.get("/bi/intelligence/realtime/token", summary="Token corto para stream BI en tiempo real")
def phase2_realtime_token(current_user: User = Depends(get_current_user)):
    token = create_access_token(
        subject=current_user.id,
        extra={"bi_intelligence_stream": True},
    )
    return {
        "token": token,
        "stream_url": "/api/v1/bi/intelligence/realtime/stream",
    }


@router.websocket("/bi/intelligence/realtime/stream")
async def phase2_realtime_stream(websocket: WebSocket, token: Optional[str] = Query(default=None)):
    if not token:
        await websocket.close(code=4001, reason="Token requerido")
        return

    payload = decode_token(token)
    if not payload or payload.get("type") != "access" or not payload.get("bi_intelligence_stream"):
        await websocket.close(code=4001, reason="Token inválido")
        return

    user_id = payload.get("sub")
    if not user_id:
        await websocket.close(code=4001, reason="Token inválido")
        return

    await websocket.accept()

    db = SessionLocal()
    try:
        while True:
            user = db.query(User).filter(User.id == user_id).first()
            if not user:
                await websocket.send_text(json.dumps({"type": "error", "detail": "user_not_found"}))
                break
            org_id = getattr(user, "organization_id", None)

            forecast = svc.ml_forecast_revenue(db, organization_id=org_id, months_ahead=3)
            anomalies = svc.ml_detect_revenue_anomalies(db, organization_id=org_id, z_threshold=2.0)
            delivery = svc.delivery_overview(db, organization_id=org_id)

            await websocket.send_text(json.dumps({
                "type": "bi_intelligence_snapshot",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "forecast_head": forecast.get("forecast", [])[:2],
                "anomaly_count": len(anomalies.get("items", [])),
                "delivery": delivery,
            }))
            await asyncio.sleep(8)
    except WebSocketDisconnect:
        return
    finally:
        db.close()
