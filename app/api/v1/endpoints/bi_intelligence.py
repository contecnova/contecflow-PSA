"""BI Intelligence endpoints.

Advanced analytics APIs: ML, connectors, realtime stream, report presets,
and scheduled delivery operations.
"""
from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.abac_enforce import enforce_abac
from app.core.deps import require_admin_or_pm, get_current_user, require_admin, require_internal_user
from app.core.responses import APIListResponse, APIResponse
from app.services.ws_service import (
    get_active_user_by_id as _usuario_activo,
)
from app.db.session import get_db, SessionLocal, publicar_contexto_de_tenant
from app.models.user import User
from app.services import bi_intelligence_service as svc
from app.core.constantes import MAX_TAMANO_DE_PAGINA

logger = logging.getLogger(__name__)

router = APIRouter()




class AdvancedPreviewIn(BaseModel):
    preset_id: str = Field(..., min_length=3, max_length=120)
    limit: int = Field(50, ge=1, le=MAX_TAMANO_DE_PAGINA)


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
    return APIResponse.ok(data=svc.ml_forecast_revenue(db, organization_id=org_id, months_ahead=months_ahead))


@router.get("/bi/intelligence/ml/anomalies/revenue", summary="Detección de anomalías de revenue BI Intelligence")
def phase2_revenue_anomalies(
    z_threshold: float = Query(2.0, ge=1.0, le=5.0),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    org_id = getattr(current_user, "organization_id", None)
    return APIResponse.ok(data=svc.ml_detect_revenue_anomalies(db, organization_id=org_id, z_threshold=z_threshold))












@router.get("/bi/intelligence/reports/presets", summary="Presets de Report Builder avanzado BI Intelligence")
def phase2_report_presets(current_user: User = Depends(require_admin)):
    _ = current_user
    return APIListResponse.ok(items=svc.list_advanced_report_presets())


@router.post("/bi/intelligence/reports/preview", summary="Preview de preset avanzado BI Intelligence")
def phase2_report_preview(
    payload: AdvancedPreviewIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
    _rol: User = Depends(require_internal_user),  # auditoria 2026-09: trabajo diario: la forma de la ruta manda sobre el fichero
):
    org_id = getattr(current_user, "organization_id", None)
    try:
        return APIResponse.ok(data=svc.preview_advanced_report(
            db,
            organization_id=org_id,
            current_user=current_user,
            preset_id=payload.preset_id,
            limit=payload.limit,
        ))
    except ValueError:
        raise HTTPException(status_code=404, detail="Preset no encontrado")


@router.get(
    "/bi/intelligence/query-builder/schema",
    summary="Schema del Query Builder visual (sin SQL)",
)
def phase2_visual_query_builder_schema(current_user: User = Depends(get_current_user),
                                       db: Session = Depends(get_db)):
    return APIResponse.ok(data=svc.get_visual_query_builder_schema(db, current_user.organization_id))


@router.post(
    "/bi/intelligence/query-builder/preview",
    summary="Preview de consulta visual (sin SQL)",
)
def phase2_visual_query_builder_preview(
    payload: VisualQueryPreviewIn,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin_or_pm),
    _rol: User = Depends(require_internal_user),  # auditoria 2026-09: trabajo diario: la forma de la ruta manda sobre el fichero
):
    from app.services.bi_governance_service import registrar_acceso
    registrar_acceso(db, request, current_user, "entity", payload.entity, "view", {"columns": list(payload.columns or [])})
    try:
        return APIResponse.ok(data=svc.preview_visual_query(
            db,
            current_user=current_user,
            entity=payload.entity,
            columns=payload.columns,
            filters=[f.model_dump() for f in payload.filters],
            sort_column=payload.sort.column if payload.sort else None,
            sort_direction=payload.sort.direction if payload.sort else "asc",
            limit=payload.limit,
        ))
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
    return APIListResponse.ok(items=templates)


@router.post(
    "/bi/intelligence/query-builder/templates",
    summary="Guardar plantilla del Query Builder visual",
)
def phase2_save_visual_query_builder_template(
    payload: VisualQueryTemplateIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _rol: User = Depends(require_internal_user),  # auditoria 2026-09: dominio: analitica interna
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
    return APIResponse.ok(data={"ok": True, "item": item})


@router.delete(
    "/bi/intelligence/query-builder/templates/{template_id}",
    summary="Eliminar plantilla del Query Builder visual",
)
def phase2_delete_visual_query_builder_template(
    template_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _rol: User = Depends(require_internal_user),  # auditoria 2026-09: dominio: analitica interna
):
    enforce_abac(db, current_user, "bi_visual_query_template", template_id, action="delete")
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
    return APIResponse.ok(data={"ok": True, "template_id": template_id})


@router.get("/bi/intelligence/delivery/overview", summary="Overview de scheduled delivery BI Intelligence")
def phase2_delivery_overview(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    org_id = getattr(current_user, "organization_id", None)
    return APIResponse.ok(data=svc.delivery_overview(db, organization_id=org_id))


@router.post("/bi/intelligence/delivery/run/{report_id}", summary="Ejecutar envío de informe programado ahora")
def phase2_delivery_run_now(
    report_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _rol: User = Depends(require_internal_user),  # auditoria 2026-09: dominio: analitica interna
):
    _ = current_user
    # Segunda auditoria 2026-11 (n.º 20): informe (PDF) + SMTP al worker. Con
    # cola: 202 `{status: "queued", recipients}`. Sin cola, como siempre.
    from app.core.segundo_plano import EN_COLA, encolar, respuesta_en_cola
    from app.services.scheduled_reports import destinatarios_del_informe
    destinatarios = destinatarios_del_informe(report_id, db)
    if destinatarios is None:
        return APIResponse.ok(data={"ok": False, "error": "Informe no encontrado"})
    resultado = encolar(svc.run_scheduled_delivery_now, report_id=report_id, _sesion=db)
    if resultado is EN_COLA:
        return respuesta_en_cola(report_id=report_id, recipients=destinatarios)
    return APIResponse.ok(data=resultado)


# ── BI Phase 2: ML enhanced endpoints ─────────────────────────────────────────



@router.get("/bi/intelligence/ml/forecast/timeseries", summary="Forecast de serie temporal (Prophet / regresión lineal)")
def phase2_timeseries_forecast(
    metric_key: str = Query("revenue", pattern="^(revenue|cost|hours)$"),
    periods: int = Query(6, ge=1, le=24),
    frequency: str = Query("MS", pattern="^(MS|W|D)$"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    org_id = getattr(current_user, "organization_id", None)
    return APIResponse.ok(data=svc.ml_forecast_prophet(
        db,
        organization_id=org_id,
        metric_key=metric_key,
        periods=periods,
        frequency=frequency,
    ))


@router.get("/bi/intelligence/ml/anomalies/multivariate", summary="Detección de anomalías multivariante (IsolationForest)")
def phase2_multivariate_anomalies(
    contamination: float = Query(0.1, ge=0.01, le=0.5),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    org_id = getattr(current_user, "organization_id", None)
    return APIResponse.ok(data=svc.ml_detect_anomalies_multivariate(db, organization_id=org_id, contamination=contamination))


@router.get("/bi/intelligence/ml/predict/overrun", summary="Predicción de overrun de proyectos (LightGBM / heurística)")
def phase2_predict_overrun(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    org_id = getattr(current_user, "organization_id", None)
    return APIResponse.ok(data=svc.ml_predict_project_overrun_lgbm(db, organization_id=org_id))


# ── BI Phase 2: ETL connector config + sync ────────────────────────────────────











async def _autorizar_flujo_de_bi(websocket: WebSocket, ticket: Optional[str], token: Optional[str]) -> Optional[str]:
    """El id de usuario de la conexión, o `None` si ya se cerró el socket.

    Revisión 2026-11: usa el mismo preámbulo que el resto de WebSockets —ticket
    de un solo uso (`GET /ws/ticket`), y el JWT en la URL sólo fuera de
    producción—. Antes pedía un token propio en la URL, que en producción y en
    preproducción se rechaza con 4003: la pantalla reconectaba cada 2 s sin
    llegar a recibir nada.
    """
    from app.api.v1.endpoints.ws import _identidad_de_la_conexion

    with SessionLocal() as db:
        return await _identidad_de_la_conexion(websocket, db, ticket=ticket, token=token)


async def _organizacion_del_usuario(user_id: str) -> Optional[str]:
    """La organización del usuario, con una sesión que se abre y se cierra aquí."""
    from app.core.async_db import run_db

    db = SessionLocal()
    try:
        user = await run_db(_usuario_activo, db, user_id)
        if not user:
            return None
        # Auditoría 2026-08 (hallazgo 22): esta sesión es un `SessionLocal()`
        # creado a mano, y sin esto `TenantSession` la trata como «no
        # inicializada» y **no filtra nada**. Va después de resolver al usuario:
        # la búsqueda por id no sabe todavía de qué organización es.
        publicar_contexto_de_tenant(db, user)
        return getattr(user, "organization_id", None)
    finally:
        db.close()


async def _emitir_desde_redis(websocket: WebSocket, org_id: Optional[str]) -> bool:
    """Reenvía el canal Pub/Sub al socket. Devuelve `False` si no pudo usarse.

    `False` significa «Redis no está disponible, usa el sondeo»; si llega a
    emitir, no vuelve hasta que el cliente se desconecta.
    """
    from app.core.config import settings as _settings

    if not _settings.REDIS_URL:
        return False
    try:
        import redis.asyncio as _aredis  # type: ignore

        r = _aredis.from_url(_settings.REDIS_URL, decode_responses=True)
        pubsub = r.pubsub()
        channel = f"contecflow:bi:kpi:{org_id or 'global'}"
        await pubsub.subscribe(channel)
        try:
            while True:
                try:
                    raw = await asyncio.wait_for(
                        pubsub.get_message(ignore_subscribe_messages=True), timeout=30.0,
                    )
                except asyncio.TimeoutError:
                    # Latido: sin tráfico durante 30 s un proxy intermedio
                    # cortaría la conexión por inactividad.
                    await websocket.send_text(json.dumps({
                        "type": "heartbeat",
                        "ts": datetime.now(timezone.utc).isoformat(),
                    }))
                    continue
                if raw and raw.get("type") == "message":
                    await websocket.send_text(raw["data"])
        except WebSocketDisconnect:
            return True
        finally:
            await pubsub.unsubscribe(channel)
            await r.aclose()
    except (ImportError, Exception):
        logger.debug("phase2_realtime_stream: Fall through to polling mode", exc_info=True)
        return False


async def _instantanea_de_bi(db, org_id: Optional[str]) -> dict:
    """Un tic, fuera del bucle de eventos (el mismo marco que publica el worker)."""
    from app.core.async_db import run_db

    return await run_db(svc.instantanea_kpi, db, org_id)


async def _emitir_por_sondeo(websocket: WebSocket, user_id: str) -> None:
    """Respaldo sin Redis: una instantánea cada ocho segundos."""
    from app.core.async_db import run_db

    db = SessionLocal()
    try:
        while True:
            user = await run_db(_usuario_activo, db, user_id)
            if not user:
                await websocket.send_text(json.dumps({"type": "error", "detail": "user_not_found"}))
                return
            # Se republica en cada tic: el bucle llama a tres servicios que leen
            # datos de negocio, y la sesión es de larga vida.
            publicar_contexto_de_tenant(db, user)
            await websocket.send_text(json.dumps(
                await _instantanea_de_bi(db, getattr(user, "organization_id", None)),
            ))
            await asyncio.sleep(8)
    except WebSocketDisconnect:
        return
    finally:
        db.close()


@router.websocket("/bi/intelligence/realtime/stream")
async def phase2_realtime_stream(websocket: WebSocket, ticket: Optional[str] = Query(default=None),
                                 token: Optional[str] = Query(default=None)):
    """Flujo de KPIs de BI en tiempo real.

    Intenta Redis Pub/Sub (canal ``contecflow:bi:kpi:<org_id>``) y, si no está
    disponible, cae a un sondeo de 8 segundos.

    Auditoría 2026-09 (hallazgo 18): esto era una sola función de complejidad 15
    con tres trabajos dentro —autorizar, reenviar Pub/Sub y sondear—. No se ha
    partido por partir: cada trozo tiene un nombre que dice qué hace y ninguno
    necesita mirar a los otros.
    """
    user_id = await _autorizar_flujo_de_bi(websocket, ticket, token)
    if not user_id:
        return

    await websocket.accept()
    org_id = await _organizacion_del_usuario(user_id)

    if await _emitir_desde_redis(websocket, org_id):
        return
    await _emitir_por_sondeo(websocket, user_id)


# ── BI Phase 2: Scheduled delivery management ──────────────────────────────────

from app.services import bi_report_delivery_service as delivery_svc


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
    return APIListResponse.ok(items=delivery_svc.list_schedules(db, organization_id=org_id))


@router.get("/bi/delivery/schedules/{schedule_id}", summary="Detalle de schedule de entrega BI")
def get_delivery_schedule(
    schedule_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    org_id = getattr(current_user, "organization_id", None)
    try:
        return APIResponse.ok(data=delivery_svc.get_schedule(db, organization_id=org_id, schedule_id=schedule_id))
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/bi/delivery/schedules", summary="Crear schedule de entrega programada BI", status_code=201)
def create_delivery_schedule(
    body: DeliveryScheduleCreateIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _rol: User = Depends(require_internal_user),  # auditoria 2026-09: dominio: analitica interna
):
    org_id = getattr(current_user, "organization_id", None)
    try:
        return APIResponse.ok(data=delivery_svc.create_schedule(
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
        ))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.put("/bi/delivery/schedules/{schedule_id}", summary="Actualizar schedule de entrega BI")
def update_delivery_schedule(
    schedule_id: str,
    body: DeliveryScheduleUpdateIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _rol: User = Depends(require_internal_user),  # auditoria 2026-09: dominio: analitica interna
):
    org_id = getattr(current_user, "organization_id", None)
    try:
        return APIResponse.ok(data=delivery_svc.update_schedule(
            db,
            organization_id=org_id,
            schedule_id=schedule_id,
            payload=body.model_dump(exclude_none=True),
        ))
    except ValueError as exc:
        code = 404 if "not_found" in str(exc) else 422
        raise HTTPException(status_code=code, detail=str(exc)) from exc


@router.delete("/bi/delivery/schedules/{schedule_id}", summary="Eliminar schedule de entrega BI", status_code=200)
def delete_delivery_schedule(
    schedule_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _rol: User = Depends(require_internal_user),  # auditoria 2026-09: dominio: analitica interna
):
    enforce_abac(db, current_user, "bi_delivery_schedule", schedule_id, action="delete")
    org_id = getattr(current_user, "organization_id", None)
    try:
        delivery_svc.delete_schedule(db, organization_id=org_id, schedule_id=schedule_id)
        return APIResponse.ok(data={"ok": True, "schedule_id": schedule_id})
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/bi/delivery/schedules/{schedule_id}/send-now", summary="Ejecutar entrega BI ahora (manual)")
def send_delivery_now(
    schedule_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _rol: User = Depends(require_internal_user),  # auditoria 2026-09: dominio: analitica interna
):
    org_id = getattr(current_user, "organization_id", None)
    # Segunda auditoria 2026-11 (n.º 20): generar el informe + adjunto y
    # repartirlo (correo, Slack, Teams) va al worker. Con cola: 202
    # `{status: "queued", schedule_id}`; el resultado queda en el registro de
    # entregas. Sin cola, como siempre.
    from app.core.segundo_plano import EN_COLA, encolar, respuesta_en_cola
    try:
        delivery_svc.get_schedule(db, organization_id=org_id, schedule_id=schedule_id)
        resultado = encolar(delivery_svc.send_schedule_now, organization_id=org_id,
                            schedule_id=schedule_id, _organizacion=org_id, _sesion=db)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if resultado is EN_COLA:
        return respuesta_en_cola(schedule_id=schedule_id)
    return APIResponse.ok(data=resultado)


@router.get("/bi/delivery/schedules/{schedule_id}/diff", summary="Ver diff del reporte vs último envío")
def get_delivery_diff(
    schedule_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    org_id = getattr(current_user, "organization_id", None)
    try:
        return APIResponse.ok(data=delivery_svc.get_schedule_report_diff(db, organization_id=org_id, schedule_id=schedule_id))
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
