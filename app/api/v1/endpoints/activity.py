"""
activity — New market-leader endpoints:
  1. Activity Feed           GET /activity/{entity_type}/{entity_id}
                             POST /activity  (internal helper for other modules)
  2. @Mentions               POST /mentions/parse  (parse comment, emit notifs)
                             GET  /mentions/my
  3. Project Health Score    GET  /projects/{id}/health
                             POST /projects/{id}/health/compute
  4. Recurring Tasks         CRUD /recurring-tasks
                             POST /recurring-tasks/materialize
  5. CPM Critical Path       GET  /projects/{id}/critical-path
  6. SSE Live Updates        GET  /events/stream
  7. Resource Demand         GET  /pipeline/resource-demand
                             CRUD /pipeline/resource-demand-lines
  8. Vendor Scorecard        GET  /alm/vendors/{id}/scorecard
                             POST /alm/vendors/{id}/scores
  9. What-if Simulation      POST /projects/{id}/simulate
"""
from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from typing import Optional, List
from datetime import datetime, timezone
from pydantic import BaseModel
import json
import asyncio

from app.db.session import get_db
from app.core.deps import get_current_user, require_any_manager
from app.models.user import User
from app.services.activity_service import (
    activity_feed_payload,
    project_activity_payload,
    parse_and_store_mentions,
    my_mentions_payload,
    mark_mention_read_record,
    project_health_payload,
    save_health_snapshot_record,
    portfolio_health_payload,
    list_recurring_tasks_payload,
    create_recurring_task_record,
    update_recurring_task_record,
    delete_recurring_task_record,
    materialize_recurring_tasks_cmd,
    critical_path_payload,
    resource_demand_payload,
    create_demand_line_record,
    delete_demand_line_record,
    vendor_scorecard_payload,
    add_vendor_score_record,
    vendor_scorecard_ranking_payload,
    simulate_project_payload,
    get_new_notifications,
    get_new_activity_events,
)

router = APIRouter()


# ═══════════════════════════════════════════════════════════════════════════════
# 1. ACTIVITY FEED
# ═══════════════════════════════════════════════════════════════════════════════

@router.get("/activity/{entity_type}/{entity_id}", summary="Feed de actividad de una entidad", tags=["Activity Feed"])
def get_activity_feed(
    entity_type: str,
    entity_id: str,
    limit: int = Query(50, le=200),
    before: Optional[str] = None,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    return activity_feed_payload(db, entity_type, entity_id, limit, before)


@router.get("/activity/project/{project_id}", summary="Feed de actividad completo del proyecto (tareas + tickets)", tags=["Activity Feed"])
def get_project_activity(
    project_id: str,
    limit: int = Query(100, le=500),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """Aggregated feed: project events + all tasks of the project."""
    return project_activity_payload(db, project_id, limit)


# ═══════════════════════════════════════════════════════════════════════════════
# 2. @MENTIONS
# ═══════════════════════════════════════════════════════════════════════════════

class ParseMentionIn(BaseModel):
    content: str
    entity_type: str
    entity_id: str
    action_url: Optional[str] = None


@router.post("/mentions/parse", summary="Parsear @menciones en un texto y enviar notificaciones", tags=["Mentions"])
def parse_mentions(
    payload: ParseMentionIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Llamar después de guardar comentarios/descripciones con @mentions. Idempotente por entity_id.
    """
    ids = parse_and_store_mentions(
        db, payload.content, current_user,
        payload.entity_type, payload.entity_id, payload.action_url,
    )
    return {"mentioned_user_ids": ids, "count": len(ids)}


@router.get("/mentions/my", summary="Mis menciones recientes", tags=["Mentions"])
def my_mentions(
    unread_only: bool = False,
    limit: int = Query(30, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return my_mentions_payload(db, current_user, unread_only, limit)


@router.post("/mentions/{mention_id}/read", summary="Marcar mención como leída", tags=["Mentions"])
def mark_mention_read(
    mention_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return mark_mention_read_record(db, mention_id, current_user)


# ═══════════════════════════════════════════════════════════════════════════════
# 3. PROJECT HEALTH SCORE
# ═══════════════════════════════════════════════════════════════════════════════

@router.get("/projects/{project_id}/health", summary="Puntuación de salud del proyecto (0-100)", tags=["Project Health"])
def get_project_health(
    project_id: str,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    return project_health_payload(db, project_id)


@router.post("/projects/{project_id}/health/compute", summary="Calcular y guardar snapshot de salud", tags=["Project Health"])
def compute_and_save_health(
    project_id: str,
    db: Session = Depends(get_db),
    _: User = Depends(require_any_manager),
):
    return save_health_snapshot_record(db, project_id)


@router.get("/projects/health/portfolio", summary="Semáforo de salud de todos los proyectos activos", tags=["Project Health"])
def portfolio_health(
    db: Session = Depends(get_db),
    _: User = Depends(require_any_manager),
):
    """Returns health summary for all active projects — useful for dashboard."""
    return portfolio_health_payload(db)


# ═══════════════════════════════════════════════════════════════════════════════
# 4. RECURRING TASKS
# ═══════════════════════════════════════════════════════════════════════════════

class RecurringTaskIn(BaseModel):
    project_id: str
    title: str
    description: Optional[str] = None
    priority: str = "medium"
    assignee_id: Optional[str] = None
    estimated_hours: Optional[float] = None
    story_points: Optional[int] = None
    freq: str = "weekly"
    interval_days: int = 7
    weekday_mask: Optional[int] = None
    start_date: str
    end_date: Optional[str] = None
    due_offset_days: int = 0
    is_active: bool = True


@router.get("/recurring-tasks", summary="Listar tareas recurrentes", tags=["Recurring Tasks"])
def list_recurring_tasks(
    project_id: Optional[str] = None,
    is_active: Optional[bool] = None,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    return list_recurring_tasks_payload(db, project_id, is_active)


@router.post("/recurring-tasks", summary="Crear tarea recurrente", status_code=201, tags=["Recurring Tasks"])
def create_recurring_task(
    payload: RecurringTaskIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    return create_recurring_task_record(db, payload, current_user)


@router.patch("/recurring-tasks/{rt_id}", summary="Actualizar tarea recurrente", tags=["Recurring Tasks"])
def update_recurring_task(
    rt_id: str,
    payload: RecurringTaskIn,
    db: Session = Depends(get_db),
    _: User = Depends(require_any_manager),
):
    return update_recurring_task_record(db, rt_id, payload)


@router.delete("/recurring-tasks/{rt_id}", summary="Eliminar tarea recurrente", tags=["Recurring Tasks"])
def delete_recurring_task(
    rt_id: str,
    db: Session = Depends(get_db),
    _: User = Depends(require_any_manager),
):
    return delete_recurring_task_record(db, rt_id)


@router.post("/recurring-tasks/materialize", summary="Materializar ocurrencias pendientes de todas las reglas activas", tags=["Recurring Tasks"])
def materialize_recurring_tasks(
    dry_run: bool = False,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    """
    Called by cron daily (or manually). Creates concrete Task records
    for each RecurringTask whose next occurrence is today or past.
    """
    return materialize_recurring_tasks_cmd(db, dry_run, current_user)


# ═══════════════════════════════════════════════════════════════════════════════
# 5. CPM — CRITICAL PATH METHOD
# ═══════════════════════════════════════════════════════════════════════════════

@router.get("/projects/{project_id}/critical-path", summary="Camino crítico CPM del proyecto", tags=["Critical Path"])
def get_critical_path(
    project_id: str,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """
    Computes Early Start / Early Finish / Late Start / Late Finish / Total Float
    for every task in the project using a topological CPM forward + backward pass.
    Tasks with Float = 0 are on the critical path.
    """
    return critical_path_payload(db, project_id)


# ═══════════════════════════════════════════════════════════════════════════════
# 6. SSE — LIVE UPDATES
# ═══════════════════════════════════════════════════════════════════════════════

@router.get("/events/stream", summary="Server-Sent Events — actualizaciones en tiempo real", tags=["Live Updates"])
async def sse_stream(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Persistent SSE stream for the authenticated user.
    Delivers new Notification rows created after the connection.
    Frontend: const es = new EventSource('/api/v1/events/stream?token=...')
    """
    user_id = current_user.id
    last_check = datetime.now(timezone.utc)

    async def event_generator():
        nonlocal last_check
        yield f"event: connected\ndata: {json.dumps({'user_id': user_id})}\n\n"

        while True:
            if await request.is_disconnected():
                break

            new_notifs = get_new_notifications(db, user_id, last_check)

            for n in new_notifs:
                payload = json.dumps({
                    "id": n.id,
                    "type": n.type.value,
                    "title": n.title,
                    "body": n.body,
                    "resource": n.resource,
                    "resource_id": n.resource_id,
                    "action_url": n.action_url,
                })
                yield f"event: notification\ndata: {payload}\n\n"

            new_events = get_new_activity_events(db, user_id, last_check)

            for ev in new_events:
                payload = json.dumps({
                    "entity_type": ev.entity_type,
                    "entity_id": ev.entity_id,
                    "entity_code": ev.entity_code,
                    "actor_name": ev.actor_name,
                    "verb": ev.verb,
                    "detail": ev.detail,
                })
                yield f"event: activity\ndata: {payload}\n\n"

            last_check = datetime.now(timezone.utc)
            yield ": heartbeat\n\n"
            await asyncio.sleep(30)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


# ═══════════════════════════════════════════════════════════════════════════════
# 7. RESOURCE DEMAND FROM PIPELINE
# ═══════════════════════════════════════════════════════════════════════════════

class DemandLineIn(BaseModel):
    opportunity_id: str
    role_or_skill: str
    hours_required: float
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    notes: Optional[str] = None


@router.get("/pipeline/resource-demand", summary="Demanda de recursos del pipeline (ponderada por probabilidad)", tags=["Resource Demand"])
def get_resource_demand(
    horizon_months: int = Query(6, ge=1, le=24),
    min_probability: float = Query(20.0, ge=0, le=100),
    db: Session = Depends(get_db),
    _: User = Depends(require_any_manager),
):
    return resource_demand_payload(db, horizon_months, min_probability)


@router.post("/pipeline/resource-demand-lines", summary="Añadir línea de demanda a una oportunidad", status_code=201, tags=["Resource Demand"])
def create_demand_line(
    payload: DemandLineIn,
    db: Session = Depends(get_db),
    _: User = Depends(require_any_manager),
):
    return create_demand_line_record(db, payload)


@router.delete("/pipeline/resource-demand-lines/{line_id}", summary="Eliminar línea de demanda", tags=["Resource Demand"])
def delete_demand_line(
    line_id: str,
    db: Session = Depends(get_db),
    _: User = Depends(require_any_manager),
):
    return delete_demand_line_record(db, line_id)


# ═══════════════════════════════════════════════════════════════════════════════
# 8. VENDOR SCORECARD
# ═══════════════════════════════════════════════════════════════════════════════

class VendorScoreIn(BaseModel):
    period: str
    sla_score: Optional[float] = None
    quality_score: Optional[float] = None
    support_score: Optional[float] = None
    price_score: Optional[float] = None
    innovation_score: Optional[float] = None
    compliance_score: Optional[float] = None
    incidents_count: int = 0
    notes: Optional[str] = None


@router.get("/alm/vendors/{vendor_id}/scorecard", summary="Scorecard de rendimiento del proveedor", tags=["Vendor Scorecard"])
def get_vendor_scorecard(
    vendor_id: str,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    return vendor_scorecard_payload(db, vendor_id)


@router.post("/alm/vendors/{vendor_id}/scores", summary="Registrar evaluación de proveedor", status_code=201, tags=["Vendor Scorecard"])
def add_vendor_score(
    vendor_id: str,
    payload: VendorScoreIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    return add_vendor_score_record(db, vendor_id, payload, current_user)


@router.get("/alm/vendors/scorecard/ranking", summary="Ranking de todos los proveedores por composite score", tags=["Vendor Scorecard"])
def vendor_scorecard_ranking(
    db: Session = Depends(get_db),
    _: User = Depends(require_any_manager),
):
    """Returns the latest composite score for every vendor that has been evaluated."""
    return vendor_scorecard_ranking_payload(db)


# ═══════════════════════════════════════════════════════════════════════════════
# 9. WHAT-IF SIMULATION
# ═══════════════════════════════════════════════════════════════════════════════

class SimulationIn(BaseModel):
    add_resources: Optional[List[dict]] = None
    remove_resource_ids: Optional[List[str]] = None
    delay_days: Optional[int] = None
    compress_pct: Optional[float] = None
    defer_task_ids: Optional[List[str]] = None
    cut_task_ids: Optional[List[str]] = None


@router.post("/projects/{project_id}/simulate", summary="Simulación what-if de impacto en el proyecto", tags=["What-If Simulation"])
def simulate_project(
    project_id: str,
    payload: SimulationIn,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """
    Pure read-only simulation — nothing is persisted.
    Returns projected end date, critical path impact, cost delta, and at-risk tasks
    given the hypothetical changes.
    """
    return simulate_project_payload(db, project_id, payload)
