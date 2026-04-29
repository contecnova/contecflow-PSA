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


class QueryBuilderFilterIn(BaseModel):
    column: str = Field(..., min_length=1, max_length=120)
    operator: str = Field(..., min_length=1, max_length=40)
    value: Optional[object] = None


class QueryBuilderSortIn(BaseModel):
    column: str = Field(..., min_length=1, max_length=120)
    direction: str = Field("asc", pattern="^(asc|desc)$")


class VisualQueryPreviewIn(BaseModel):
    entity: str = Field(..., min_length=1, max_length=120)
    columns: list[str] = Field(default_factory=list)
    filters: list[QueryBuilderFilterIn] = Field(default_factory=list)
    sort: Optional[QueryBuilderSortIn] = None
    limit: int = Field(100, ge=1, le=500)


class VisualQueryTemplateIn(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)
    query: VisualQueryPreviewIn


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


@router.post(
    "/bi/intelligence/connectors/{connector}/sync/async",
    summary="Encolar sync de conector como tarea Celery",
)
def enqueue_connector_sync(
    connector: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Encola `sync_connector_data` en Celery y devuelve el task_id.

    El sync se ejecuta en background por el worker; usa
    `GET /bi/intelligence/connectors/{connector}/sync/log` para ver el resultado.
    """
    from app.worker import sync_connector_data

    org_id = str(getattr(current_user, "organization_id", None) or "")
    task = sync_connector_data.apply_async(
        kwargs={"connector_id": connector, "org_id": org_id or None}
    )
    return {"queued": True, "task_id": task.id, "connector": connector}


@router.get(
    "/bi/intelligence/connectors/{connector}/sync/log",
    summary="Ver log de sincronización del conector",
)
def connector_sync_log(
    connector: str,
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Devuelve las últimas *limit* entradas del log de sync para el conector indicado.

    Cada entrada incluye: ok, records_ingested, error, started_at, finished_at.
    """
    org_id = getattr(current_user, "organization_id", None)
    try:
        return svc.get_connector_sync_log(db, organization_id=org_id, connector=connector, limit=limit)
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


@router.get(
    "/bi/intelligence/query-builder/schema",
    summary="Schema del Query Builder visual (sin SQL)",
)
def phase2_visual_query_builder_schema(current_user: User = Depends(get_current_user)):
    _ = current_user
    return svc.get_visual_query_builder_schema()


@router.post(
    "/bi/intelligence/query-builder/preview",
    summary="Preview de consulta visual (sin SQL)",
)
def phase2_visual_query_builder_preview(
    payload: VisualQueryPreviewIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        return svc.preview_visual_query(
            db,
            current_user=current_user,
            entity=payload.entity,
            columns=payload.columns,
            filters=[f.model_dump() for f in payload.filters],
            sort_column=payload.sort.column if payload.sort else None,
            sort_direction=payload.sort.direction if payload.sort else "asc",
            limit=payload.limit,
        )
    except ValueError as exc:
        if str(exc) == "entity_not_found":
            raise HTTPException(status_code=404, detail="Entidad no soportada") from exc
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get(
    "/bi/intelligence/query-builder/templates",
    summary="Listar plantillas del Query Builder visual",
)
def phase2_visual_query_builder_templates(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    org_id = getattr(current_user, "organization_id", None)
    templates = svc.list_visual_query_templates(
        db,
        organization_id=org_id,
        user_id=str(current_user.id),
    )
    return {"items": templates, "count": len(templates)}


@router.post(
    "/bi/intelligence/query-builder/templates",
    summary="Guardar plantilla del Query Builder visual",
)
def phase2_save_visual_query_builder_template(
    payload: VisualQueryTemplateIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    org_id = getattr(current_user, "organization_id", None)
    try:
        item = svc.save_visual_query_template(
            db,
            organization_id=org_id,
            user_id=str(current_user.id),
            name=payload.name,
            query=payload.query.model_dump(exclude_none=True),
        )
    except ValueError as exc:
        if str(exc) == "entity_not_found":
            raise HTTPException(status_code=404, detail="Entidad no soportada") from exc
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"ok": True, "item": item}


@router.delete(
    "/bi/intelligence/query-builder/templates/{template_id}",
    summary="Eliminar plantilla del Query Builder visual",
)
def phase2_delete_visual_query_builder_template(
    template_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    org_id = getattr(current_user, "organization_id", None)
    try:
        svc.delete_visual_query_template(
            db,
            organization_id=org_id,
            user_id=str(current_user.id),
            template_id=template_id,
        )
    except ValueError as exc:
        if str(exc) == "template_not_found":
            raise HTTPException(status_code=404, detail="Plantilla no encontrada") from exc
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"ok": True, "template_id": template_id}


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


# ── BI Phase 2: ML enhanced endpoints ─────────────────────────────────────────

class ConnectorConfigIn(BaseModel):
    config: dict = Field(default_factory=dict)
    entity: str = Field("default", min_length=1, max_length=64)
    field_mapping: Optional[dict] = None


@router.get("/bi/intelligence/ml/forecast/timeseries", summary="Forecast de serie temporal (Prophet / regresión lineal)")
def phase2_timeseries_forecast(
    metric_key: str = Query("revenue", pattern="^(revenue|cost|hours)$"),
    periods: int = Query(6, ge=1, le=24),
    frequency: str = Query("MS", pattern="^(MS|W|D)$"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    org_id = getattr(current_user, "organization_id", None)
    return svc.ml_forecast_prophet(
        db,
        organization_id=org_id,
        metric_key=metric_key,
        periods=periods,
        frequency=frequency,
    )


@router.get("/bi/intelligence/ml/anomalies/multivariate", summary="Detección de anomalías multivariante (IsolationForest)")
def phase2_multivariate_anomalies(
    contamination: float = Query(0.1, ge=0.01, le=0.5),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    org_id = getattr(current_user, "organization_id", None)
    return svc.ml_detect_anomalies_multivariate(db, organization_id=org_id, contamination=contamination)


@router.get("/bi/intelligence/ml/predict/overrun", summary="Predicción de overrun de proyectos (LightGBM / heurística)")
def phase2_predict_overrun(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    org_id = getattr(current_user, "organization_id", None)
    return svc.ml_predict_project_overrun_lgbm(db, organization_id=org_id)


# ── BI Phase 2: ETL connector config + sync ────────────────────────────────────

@router.get("/bi/intelligence/connectors/{connector}/config", summary="Obtener configuración (no sensible) de conector")
def phase2_get_connector_config(
    connector: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    org_id = getattr(current_user, "organization_id", None)
    return svc.get_connector_config(db, organization_id=org_id, connector=connector)


@router.put("/bi/intelligence/connectors/{connector}/config", summary="Guardar configuración de conector (ETL)")
def phase2_save_connector_config(
    connector: str,
    payload: ConnectorConfigIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    org_id = getattr(current_user, "organization_id", None)
    saved = svc.save_connector_config(
        db,
        organization_id=org_id,
        connector=connector,
        config=payload.config,
    )
    return {"ok": True, "connector": connector, "config": saved}


@router.post("/bi/intelligence/connectors/{connector}/etl-sync", summary="Ejecutar sincronización ETL completa del conector")
def phase2_etl_sync(
    connector: str,
    payload: ConnectorConfigIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    org_id = getattr(current_user, "organization_id", None)
    try:
        return svc.run_etl_connector_sync(db, organization_id=org_id, connector=connector)
    except ValueError:
        raise HTTPException(status_code=404, detail="Conector no soportado")


@router.get("/bi/intelligence/connectors/catalog/etl", summary="Listado de conectores ETL disponibles y entidades soportadas")
def phase2_etl_catalog(current_user: User = Depends(get_current_user)):
    _ = current_user
    try:
        from app.integrations import bi_etl_connectors
        return {"connectors": bi_etl_connectors.list_connectors()}
    except Exception:
        return {"connectors": []}


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
    """BI intelligence real-time stream.

    Tries Redis Pub/Sub first (channel ``contecflow:bi:kpi:<org_id>``).
    Falls back to 8-second polling when Redis is unavailable.
    """
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
    org_id: Optional[str] = None
    try:
        user = db.query(User).filter(User.id == user_id).first()
        if user:
            org_id = getattr(user, "organization_id", None)
    finally:
        db.close()

    # ── Try Redis Pub/Sub first ────────────────────────────────────────────────
    from app.core.config import settings as _settings

    if _settings.REDIS_URL:
        try:
            import redis.asyncio as _aredis  # type: ignore

            r = _aredis.from_url(_settings.REDIS_URL, decode_responses=True)
            pubsub = r.pubsub()
            channel = f"contecflow:bi:kpi:{org_id or 'global'}"
            await pubsub.subscribe(channel)
            try:
                while True:
                    try:
                        raw = await asyncio.wait_for(pubsub.get_message(ignore_subscribe_messages=True), timeout=30.0)
                    except asyncio.TimeoutError:
                        # Send heartbeat to keep connection alive
                        await websocket.send_text(json.dumps({"type": "heartbeat", "ts": datetime.now(timezone.utc).isoformat()}))
                        continue
                    if raw and raw.get("type") == "message":
                        await websocket.send_text(raw["data"])
            except WebSocketDisconnect:
                return
            finally:
                await pubsub.unsubscribe(channel)
                await r.aclose()
        except (ImportError, Exception):
            pass  # Fall through to polling mode

    # ── Fallback: polling every 8 s ────────────────────────────────────────────
    db = SessionLocal()
    try:
        while True:
            user = db.query(User).filter(User.id == user_id).first()
            if not user:
                await websocket.send_text(json.dumps({"type": "error", "detail": "user_not_found"}))
                break
            _org_id = getattr(user, "organization_id", None)

            forecast = svc.ml_forecast_revenue(db, organization_id=_org_id, months_ahead=3)
            anomalies = svc.ml_detect_revenue_anomalies(db, organization_id=_org_id, z_threshold=2.0)
            delivery = svc.delivery_overview(db, organization_id=_org_id)

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


# ── BI Phase 2: Scheduled delivery management ──────────────────────────────────

from app.services import bi_report_delivery_service as delivery_svc  # noqa: E402


class DeliveryScheduleCreateIn(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    report_preset_id: str = Field(..., min_length=1, max_length=120)
    channels: list[str] = Field(default_factory=list)
    recipients: list[str] = Field(default_factory=list)
    frequency: str = Field("daily", pattern="^(hourly|daily|weekly|monthly)$")
    cron_expression: Optional[str] = Field(None, max_length=100)
    export_format: str = Field("xlsx", pattern="^(json|csv|xlsx|pdf)$")
    slack_webhook_url: Optional[str] = Field(None, max_length=500)
    teams_webhook_url: Optional[str] = Field(None, max_length=500)
    is_active: bool = True
    send_only_on_change: bool = False


class DeliveryScheduleUpdateIn(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=200)
    channels: Optional[list[str]] = None
    recipients: Optional[list[str]] = None
    frequency: Optional[str] = Field(None, pattern="^(hourly|daily|weekly|monthly)$")
    export_format: Optional[str] = Field(None, pattern="^(json|csv|xlsx|pdf)$")
    slack_webhook_url: Optional[str] = Field(None, max_length=500)
    teams_webhook_url: Optional[str] = Field(None, max_length=500)
    is_active: Optional[bool] = None
    send_only_on_change: Optional[bool] = None


@router.get("/bi/delivery/schedules", summary="Listar schedules de entrega programada BI")
def list_delivery_schedules(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    org_id = getattr(current_user, "organization_id", None)
    return {"items": delivery_svc.list_schedules(db, organization_id=org_id)}


@router.get("/bi/delivery/schedules/{schedule_id}", summary="Detalle de schedule de entrega BI")
def get_delivery_schedule(
    schedule_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    org_id = getattr(current_user, "organization_id", None)
    try:
        return delivery_svc.get_schedule(db, organization_id=org_id, schedule_id=schedule_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/bi/delivery/schedules", summary="Crear schedule de entrega programada BI", status_code=201)
def create_delivery_schedule(
    body: DeliveryScheduleCreateIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    org_id = getattr(current_user, "organization_id", None)
    try:
        return delivery_svc.create_schedule(
            db,
            organization_id=org_id,
            name=body.name,
            report_preset_id=body.report_preset_id,
            channels=body.channels,
            recipients=body.recipients,
            frequency=body.frequency,
            cron_expression=body.cron_expression,
            export_format=body.export_format,
            slack_webhook_url=body.slack_webhook_url,
            teams_webhook_url=body.teams_webhook_url,
            is_active=body.is_active,
            send_only_on_change=body.send_only_on_change,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.put("/bi/delivery/schedules/{schedule_id}", summary="Actualizar schedule de entrega BI")
def update_delivery_schedule(
    schedule_id: str,
    body: DeliveryScheduleUpdateIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    org_id = getattr(current_user, "organization_id", None)
    try:
        return delivery_svc.update_schedule(
            db,
            organization_id=org_id,
            schedule_id=schedule_id,
            payload=body.model_dump(exclude_none=True),
        )
    except ValueError as exc:
        code = 404 if "not_found" in str(exc) else 422
        raise HTTPException(status_code=code, detail=str(exc)) from exc


@router.delete("/bi/delivery/schedules/{schedule_id}", summary="Eliminar schedule de entrega BI", status_code=200)
def delete_delivery_schedule(
    schedule_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    org_id = getattr(current_user, "organization_id", None)
    try:
        delivery_svc.delete_schedule(db, organization_id=org_id, schedule_id=schedule_id)
        return {"ok": True, "schedule_id": schedule_id}
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/bi/delivery/schedules/{schedule_id}/send-now", summary="Ejecutar entrega BI ahora (manual)")
def send_delivery_now(
    schedule_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    org_id = getattr(current_user, "organization_id", None)
    try:
        return delivery_svc.send_schedule_now(db, organization_id=org_id, schedule_id=schedule_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/bi/delivery/schedules/{schedule_id}/diff", summary="Ver diff del reporte vs último envío")
def get_delivery_diff(
    schedule_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    org_id = getattr(current_user, "organization_id", None)
    try:
        return delivery_svc.get_schedule_report_diff(db, organization_id=org_id, schedule_id=schedule_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
