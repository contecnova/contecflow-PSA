"""
v23.8 Features Endpoint — thin router delegating to v238_service.
"""
from fastapi import APIRouter, Depends, Query, Request, Body, Header
from sqlalchemy.orm import Session
from typing import Optional, List
from datetime import date
from pydantic import BaseModel

from app.db.session import get_db
from app.core.deps import get_current_user, require_any_manager, require_admin
from app.models.user import User
import app.services.v238_service as svc

router = APIRouter()


# ──────────────────────────────────────────────────────────────────────────────
# PIPELINE — stage configs + forecast
# ──────────────────────────────────────────────────────────────────────────────

class StageConfigCreate(BaseModel):
    stage_key:           str
    label:               str
    description:         Optional[str] = None
    color:               Optional[str] = "#6B7280"
    order:               Optional[int] = 0
    probability_default: Optional[float] = 50
    is_terminal:         Optional[bool] = False
    is_won:              Optional[bool] = False


@router.get("/pipeline/stage-configs", summary="List configurable pipeline stages")
def list_stage_configs(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return svc.get_stage_configs(db)


@router.post("/pipeline/stage-configs", summary="Create custom pipeline stage", status_code=201)
def create_stage_config(
    payload: StageConfigCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    return svc.create_stage_config_record(
        stage_key=payload.stage_key,
        label=payload.label,
        description=payload.description,
        color=payload.color,
        order=payload.order,
        probability_default=payload.probability_default,
        is_terminal=payload.is_terminal,
        is_won=payload.is_won,
        db=db,
    )


@router.delete("/pipeline/stage-configs/{stage_key}", summary="Delete custom pipeline stage", status_code=204)
def delete_stage_config(
    stage_key: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    svc.delete_stage_config_record(stage_key, db)


@router.get("/pipeline/forecast", summary="Weighted revenue forecast by month")
def pipeline_forecast(
    months_ahead: int = Query(default=6, ge=1, le=24),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return svc.get_pipeline_forecast(months_ahead, db)


# ──────────────────────────────────────────────────────────────────────────────
# CAPACITY — conflict detection + gantt leveling
# ──────────────────────────────────────────────────────────────────────────────

@router.get("/bookings/conflicts", summary="Detect double-booking conflicts")
def detect_booking_conflicts(
    user_id: Optional[str] = Query(None),
    start_date: Optional[date] = Query(None),
    end_date: Optional[date] = Query(None),
    threshold_pct: float = Query(default=100.0),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    return svc.get_booking_conflicts(user_id, start_date, end_date, threshold_pct, db)


@router.get("/bookings/gantt-leveling", summary="Gantt resource leveling — overload analysis + reschedule suggestions")
def gantt_resource_leveling(
    project_id: Optional[str] = Query(None),
    start_date: Optional[date] = Query(None),
    end_date: Optional[date] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    return svc.get_gantt_leveling(project_id, start_date, end_date, db)


# ──────────────────────────────────────────────────────────────────────────────
# AUTOMATIONS — trigger/action types + custom field trigger test
# ──────────────────────────────────────────────────────────────────────────────

@router.get("/automations/trigger-types", summary="List available trigger types with metadata")
def list_trigger_types(current_user: User = Depends(get_current_user)):
    return svc.list_trigger_types_data()


@router.get("/automations/action-types", summary="List available action types with metadata")
def list_action_types(current_user: User = Depends(get_current_user)):
    return svc.list_action_types_data()


@router.post("/automations/test-trigger", summary="Test custom_field_changed trigger evaluation")
def test_custom_field_trigger(
    payload: dict = Body(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    return svc.test_custom_field_trigger_record(payload, db)


# ──────────────────────────────────────────────────────────────────────────────
# BI — ad-hoc query, drilldown, cross-filter
# ──────────────────────────────────────────────────────────────────────────────

class AdhocQuery(BaseModel):
    metric:     str
    dimensions: Optional[List[str]] = None
    filters:    Optional[dict] = None
    date_from:  Optional[date] = None
    date_to:    Optional[date] = None
    limit:      Optional[int] = 100


@router.post("/analytics/adhoc", summary="Ad-hoc analytics query")
def adhoc_query(
    payload: AdhocQuery,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    return svc.run_adhoc_query(
        metric=payload.metric,
        dimensions=payload.dimensions or [],
        filters=payload.filters or {},
        date_from=payload.date_from,
        date_to=payload.date_to,
        limit=min(payload.limit or 100, 1000),
        db=db,
    )


@router.get("/analytics/drilldown", summary="BI drilldown — get detail rows for a metric/dimension value")
def analytics_drilldown(
    metric:    str = Query(...),
    dimension: str = Query(...),
    value:     str = Query(...),
    date_from: Optional[date] = Query(None),
    date_to:   Optional[date] = Query(None),
    page:      int = Query(default=1, ge=1),
    page_size: int = Query(default=50, le=200),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    return svc.run_analytics_drilldown(metric, dimension, value, date_from, date_to, page, page_size, db)


@router.post("/analytics/cross-filter", summary="BI cross-filter — apply multiple dimension filters simultaneously")
def analytics_cross_filter(
    payload: dict = Body(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    return svc.run_analytics_cross_filter(payload, db)


# ──────────────────────────────────────────────────────────────────────────────
# STRIPE — payment links + webhook
# ──────────────────────────────────────────────────────────────────────────────

@router.post("/invoices/{invoice_id}/payment-link", summary="Create Stripe payment link for invoice")
def create_payment_link(
    invoice_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    return svc.create_payment_link_record(invoice_id, db)


@router.post("/invoices/stripe-webhook", summary="Stripe webhook — mark invoice as paid on checkout.session.completed")
async def stripe_webhook(
    request: Request,
    stripe_signature: Optional[str] = Header(default=None, alias="stripe-signature"),
    db: Session = Depends(get_db),
):
    body = await request.body()
    return svc.handle_stripe_webhook(body, stripe_signature, db)


# ──────────────────────────────────────────────────────────────────────────────
# COLLABORATIVE DOCS — CRDT snapshots
# ──────────────────────────────────────────────────────────────────────────────

@router.post("/documents/{document_id}/collab/snapshot", summary="Save CRDT state snapshot")
async def save_collab_snapshot(
    document_id: str,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    body = await request.body()
    return svc.save_collab_snapshot_record(document_id, body, current_user.id, db)


@router.get("/documents/{document_id}/collab/snapshot", summary="Load latest CRDT state snapshot")
def load_collab_snapshot(
    document_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return svc.load_collab_snapshot_record(document_id, db)


@router.get("/documents/{document_id}/collab/history", summary="List CRDT snapshot history")
def list_collab_snapshots(
    document_id: str,
    limit: int = Query(default=20, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    return svc.list_collab_snapshots_records(document_id, limit, db)


# ──────────────────────────────────────────────────────────────────────────────
# SCIM helpers (exported for scim.py)
# ──────────────────────────────────────────────────────────────────────────────

_scim_bulk_error = svc.scim_bulk_error
