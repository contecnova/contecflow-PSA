
"""
bookings.py router — thin delegates to bookings_service.
"""
from fastapi import APIRouter, Depends, Query, Body
from sqlalchemy.orm import Session
from typing import Optional

from app.db.session import get_db
from app.core.deps import get_current_user, require_any_manager, require_admin
from app.models.user import User
from app.schemas.bookings import (
    BookingCreate,
    BookingUpdate,
    SLAScheduleCreate,
    ApiKeyCreate,
    RecurringCreate,
)
from app.services import bookings_service as svc

from app.services import v238_service

router = APIRouter()


# ── Capacity: Conflicts & Gantt Leveling (v238) ─────────────────────────────
@router.get("/conflicts")
def get_booking_conflicts(
    user_id: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    threshold_pct: float = Query(100.0, ge=0, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    from datetime import date
    # Parse dates if provided
    sd = date.fromisoformat(start_date) if start_date else None
    ed = date.fromisoformat(end_date) if end_date else None
    return v238_service.get_booking_conflicts(user_id, sd, ed, threshold_pct, db)

@router.get("/gantt-leveling")
def get_gantt_leveling(
    project_id: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    from datetime import date
    sd = date.fromisoformat(start_date) if start_date else None
    ed = date.fromisoformat(end_date) if end_date else None
    return v238_service.get_gantt_leveling(project_id, sd, ed, db)





# ── Resource Bookings ─────────────────────────────────────────────────────────

@router.get("")
def list_bookings(
    user_id: Optional[str] = None,
    project_id: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    booking_type: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    return svc.list_bookings_records(user_id, project_id, start_date, end_date,
                                     booking_type, current_user.organization_id, db)


@router.get("/heatmap")
def bookings_heatmap(weeks: int = Query(12, ge=1, le=52),
                     db: Session = Depends(get_db),
                     current_user: User = Depends(require_any_manager)):
    return svc.get_bookings_heatmap(weeks, current_user.organization_id, db)


@router.post("")
def create_booking(payload: BookingCreate, db: Session = Depends(get_db),
                   current_user: User = Depends(require_any_manager)):
    return svc.create_booking_record(payload, current_user.id, db)


@router.patch("/{booking_id}")
def update_booking(booking_id: str, payload: BookingUpdate,
                   db: Session = Depends(get_db),
                   current_user: User = Depends(require_any_manager)):
    return svc.update_booking_record(booking_id, payload, db)


@router.delete("/{booking_id}")
def delete_booking(booking_id: str, db: Session = Depends(get_db),
                   current_user: User = Depends(require_any_manager)):
    return svc.delete_booking_record(booking_id, db)


# ── SLA Schedules ─────────────────────────────────────────────────────────────

@router.get("/sla-schedules")
def list_sla_schedules(db: Session = Depends(get_db),
                       current_user: User = Depends(get_current_user)):
    return svc.list_sla_schedules_records(db)


@router.post("/sla-schedules")
def create_sla_schedule(payload: SLAScheduleCreate, db: Session = Depends(get_db),
                        current_user: User = Depends(require_admin)):
    return svc.create_sla_schedule_record(payload, db)


@router.post("/sla-schedules/calculate-deadline")
def calculate_sla_deadline(payload: dict = Body(...), db: Session = Depends(get_db),
                           current_user: User = Depends(get_current_user)):
    return svc.calculate_sla_deadline_record(payload, db)


@router.post("/sla-schedules/{schedule_id}/holidays")
def add_holidays(schedule_id: str, payload: dict = Body(...),
                 db: Session = Depends(get_db),
                 current_user: User = Depends(require_admin)):
    return svc.add_holidays_record(schedule_id, payload, db)


@router.delete("/sla-schedules/{schedule_id}/holidays/{holiday_id}")
def delete_holiday(schedule_id: str, holiday_id: str,
                   db: Session = Depends(get_db),
                   current_user: User = Depends(require_admin)):
    return svc.delete_holiday_record(schedule_id, holiday_id, db)


# ── API Keys ──────────────────────────────────────────────────────────────────

@router.get("/api-keys")
def list_api_keys(db: Session = Depends(get_db),
                  current_user: User = Depends(get_current_user)):
    is_superadmin = getattr(current_user, "role", "") in ("superadmin", "admin")
    return svc.list_api_keys_records(current_user.id, is_superadmin, db)


@router.post("/api-keys")
def create_api_key(payload: ApiKeyCreate, db: Session = Depends(get_db),
                   current_user: User = Depends(get_current_user)):
    return svc.create_api_key_record(payload, current_user.id, db)


@router.delete("/api-keys/{key_id}")
def revoke_api_key(key_id: str, db: Session = Depends(get_db),
                   current_user: User = Depends(get_current_user)):
    return svc.revoke_api_key_record(key_id, current_user.id, db)


@router.post("/api-keys/verify")
def verify_api_key_endpoint(payload: dict = Body(...), db: Session = Depends(get_db)):
    return svc.verify_api_key_record(payload.get("key", ""), db)


# ── Recurring Invoices ────────────────────────────────────────────────────────

@router.get("/recurring")
def list_recurring(db: Session = Depends(get_db),
                   current_user: User = Depends(require_any_manager)):
    return svc.list_recurring_records(db)


@router.post("/recurring")
def create_recurring(payload: RecurringCreate, db: Session = Depends(get_db),
                     current_user: User = Depends(require_any_manager)):
    return svc.create_recurring_record(payload, current_user.id, db)


@router.patch("/recurring/{rec_id}")
def update_recurring(rec_id: str, payload: dict = Body(...),
                     db: Session = Depends(get_db),
                     current_user: User = Depends(require_any_manager)):
    return svc.update_recurring_record(rec_id, payload, db)


@router.post("/recurring/process-due")
def process_due_recurring(db: Session = Depends(get_db),
                          current_user: User = Depends(require_admin)):
    return svc.process_due_recurring_records(db, current_user)


@router.post("/recurring/{rec_id}/generate-now")
def generate_recurring_now(rec_id: str, db: Session = Depends(get_db),
                           current_user: User = Depends(require_any_manager)):
    return svc.generate_recurring_now_record(rec_id, db, current_user)


# ── Pipeline Ops ──────────────────────────────────────────────────────────────

@router.post("/pipeline/convert/{opportunity_id}")
def convert_opportunity_to_project(opportunity_id: str, payload: dict = Body(default={}),
                                   db: Session = Depends(get_db),
                                   current_user: User = Depends(require_any_manager)):
    return svc.convert_opportunity_to_project_record(opportunity_id, payload, current_user, db)


@router.get("/pipeline/revenue-forecast")
def pipeline_revenue_forecast(db: Session = Depends(get_db),
                              current_user: User = Depends(require_any_manager)):
    return svc.get_pipeline_revenue_forecast(db)


# ── ITSM Aging ────────────────────────────────────────────────────────────────

@router.get("/itsm/aging")
def ticket_aging_report(db: Session = Depends(get_db),
                        current_user: User = Depends(require_any_manager)):
    return svc.get_ticket_aging_report(db)


@router.get("/itsm/wallboard")
def get_wallboard(db: Session = Depends(get_db),
                  current_user: User = Depends(require_any_manager)):
    return svc.get_wallboard_data(db)


# ── SSO ───────────────────────────────────────────────────────────────────────

@router.get("/sso/initiate/{config_id}")
def initiate_sso(config_id: str, redirect_to: str = Query(""),
                 db: Session = Depends(get_db)):
    return svc.initiate_sso_record(config_id, redirect_to, db)


@router.post("/sso/saml/callback")
def saml_callback(payload: dict = Body(...), db: Session = Depends(get_db)):
    return svc.process_saml_callback(payload, db)


@router.post("/sso/oidc/callback")
def oidc_callback(payload: dict = Body(...), db: Session = Depends(get_db)):
    return svc.process_oidc_callback(payload, db)


# ── Workflow Engine ───────────────────────────────────────────────────────────

@router.post("/workflows/enqueue")
def enqueue_workflow(payload: dict = Body(...), db: Session = Depends(get_db),
                     current_user: User = Depends(get_current_user)):
    return svc.enqueue_workflow_record(payload, current_user.id, db)


@router.post("/workflows/process-queue")
def process_workflow_queue(db: Session = Depends(get_db),
                           current_user: User = Depends(require_admin)):
    return svc.process_workflow_queue_record(db)
