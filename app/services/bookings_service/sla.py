"""Calendarios de SLA, festivos y calculo de vencimientos.

Parte de `app.services.bookings_service` (auditoria 2026-11, #24): se partio por responsabilidad
sin cambiar el codigo. El paquete reexporta todos los nombres.
"""
from __future__ import annotations

import json
from datetime import date, datetime, time, timedelta, timezone
from app.models.bookings import SLASchedule
from app.models.bookings import SLAHoliday
from sqlalchemy.orm import joinedload
from app.core.errores import ErrorDeDominio


def serialize_schedule(s) -> dict:
    return {
        "id": s.id, "name": s.name, "timezone": s.timezone,
        "is_default": s.is_default,
        "work_days": json.loads(s.work_days) if s.work_days else [1, 2, 3, 4, 5],
        "work_start": str(s.work_start) if s.work_start else None,
        "work_end": str(s.work_end) if s.work_end else None,
        "holiday_count": len(s.holidays),
        "holidays": [{"id": h.id, "date": str(h.date), "name": h.name, "country": h.country} for h in s.holidays],
    }


# ── SLA Schedules ─────────────────────────────────────────────────────────────

def list_sla_schedules_records(db) -> list:
    return [serialize_schedule(s) for s in db.query(SLASchedule).options(joinedload(SLASchedule.holidays)).all()]


def create_sla_schedule_record(payload, db) -> dict:
    # Audit #C8: previously the UPDATE (un-setting other default schedules) and
    # the INSERT ran as two independent statements with one final commit and no
    # rollback. A failure in `db.add(s)` would leave the prior UPDATE committed
    # by the next session checkpoint, producing zero default schedules. Wrap
    # both in an `atomic()` block so they succeed or fail as a single unit.
    from app.db.transactions import atomic

    with atomic(db):
        if payload.is_default:
            db.query(SLASchedule).filter(SLASchedule.is_default == True).update({"is_default": False})
        work_start = time.fromisoformat(payload.work_start) if payload.work_start else None
        work_end   = time.fromisoformat(payload.work_end)   if payload.work_end   else None
        s = SLASchedule(
            name=payload.name, timezone=payload.timezone,
            is_default=payload.is_default,
            work_days=json.dumps(payload.work_days),
            work_start=work_start, work_end=work_end,
        )
        db.add(s)
    db.refresh(s)
    s = db.query(SLASchedule).options(joinedload(SLASchedule.holidays)).filter(SLASchedule.id == s.id).first()
    return serialize_schedule(s)


def calculate_sla_deadline_record(payload: dict, db) -> dict:
    schedule_id = payload.get("schedule_id")
    start_dt = datetime.fromisoformat(payload.get("start", datetime.now(timezone.utc).isoformat()))
    hours    = float(payload.get("hours", 8))
    schedule = None
    if schedule_id:
        schedule = db.query(SLASchedule).options(joinedload(SLASchedule.holidays)).filter(SLASchedule.id == schedule_id).first()
    if not schedule:
        deadline = start_dt + timedelta(hours=hours)
        return {"deadline": deadline.isoformat(), "business_hours": False}
    holidays_set  = {h.date for h in schedule.holidays}
    work_days     = json.loads(schedule.work_days) if schedule.work_days else [1, 2, 3, 4, 5]
    work_start_h  = schedule.work_start.hour if schedule.work_start else 9
    work_end_h    = schedule.work_end.hour   if schedule.work_end   else 17
    remaining     = hours
    current       = start_dt
    max_iterations = 365
    while remaining > 0 and max_iterations > 0:
        max_iterations -= 1
        if current.weekday() + 1 in work_days and current.date() not in holidays_set:
            day_end = current.replace(hour=work_end_h, minute=0, second=0, microsecond=0)
            if current.hour < work_start_h:
                current = current.replace(hour=work_start_h, minute=0, second=0)
            if current < day_end:
                available_today = (day_end - current).total_seconds() / 3600
                if remaining <= available_today:
                    current = current + timedelta(hours=remaining)
                    remaining = 0
                else:
                    remaining -= available_today
                    current = day_end
        if remaining > 0:
            current = (current + timedelta(days=1)).replace(hour=work_start_h, minute=0, second=0, microsecond=0)
    return {
        "deadline": current.isoformat(),
        "business_hours": True,
        "schedule_name": schedule.name,
        "timezone": schedule.timezone,
    }


def add_holidays_record(schedule_id: str, payload: dict, db) -> dict:
    schedule = db.query(SLASchedule).filter(SLASchedule.id == schedule_id).first()
    if not schedule: raise ErrorDeDominio(404)
    holidays_data = payload.get("holidays", [payload])
    added = 0
    for h in holidays_data:
        if not h.get("date"): continue
        db.add(SLAHoliday(schedule_id=schedule_id, date=date.fromisoformat(h["date"]),
                          name=h.get("name"), country=h.get("country")))
        added += 1
    db.commit()
    return {"ok": True, "added": added}


def delete_holiday_record(schedule_id: str, holiday_id: str, db) -> dict:
    h = db.query(SLAHoliday).filter(SLAHoliday.id == holiday_id, SLAHoliday.schedule_id == schedule_id).first()
    if not h: raise ErrorDeDominio(404)
    db.delete(h); db.commit()
    return {"ok": True}
