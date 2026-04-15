"""
Bookings service — business logic extracted from bookings.py endpoint.
Covers: task dependencies, resource bookings, exchange rates, SLA schedules,
        API keys, recurring invoices, pipeline ops, ITSM aging, SSO, workflows.
"""
from __future__ import annotations

import json
import logging
import secrets
from datetime import date, datetime, time, timedelta, timezone
from typing import Optional

logger = logging.getLogger(__name__)

SUPPORTED_CURRENCIES = ["EUR", "USD", "GBP", "PLN", "CHF", "SEK", "DKK", "NOK", "JPY", "CAD", "AUD", "MXN", "BRL"]


# ── Serialisers ───────────────────────────────────────────────────────────────

def serialize_booking(b) -> dict:
    days = (b.end_date - b.start_date).days + 1
    return {
        "id": b.id,
        "user_id": b.user_id,
        "user_name": b.user.full_name if b.user else None,
        "project_id": b.project_id,
        "project_name": b.project.name if b.project else None,
        "project_code": b.project.code if b.project else None,
        "booking_type": b.booking_type,
        "start_date": str(b.start_date),
        "end_date": str(b.end_date),
        "hours_per_day": b.hours_per_day,
        "total_hours": round(days * b.hours_per_day, 1),
        "note": b.note,
    }


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


def serialize_recurring(r) -> dict:
    return {
        "id": r.id, "name": r.name,
        "project_id": r.project_id,
        "project_name": r.project.name if r.project else None,
        "frequency": r.frequency,
        "next_date": str(r.next_date) if r.next_date else None,
        "end_date": str(r.end_date) if r.end_date else None,
        "is_active": r.is_active,
        "client_name": r.client_name,
        "client_email": r.client_email,
        "amount": r.amount, "tax_rate": r.tax_rate,
        "total": round(r.amount * (1 + r.tax_rate / 100), 2),
        "currency": r.currency,
        "description": r.description,
        "payment_terms_days": r.payment_terms_days,
        "last_generated_at": str(r.last_generated_at)[:10] if r.last_generated_at else None,
        "total_generated": r.total_generated or 0,
    }


# ── API key helpers ───────────────────────────────────────────────────────────

def _hash_api_key(key: str) -> str:
    import bcrypt as _bcrypt
    return _bcrypt.hashpw(key.encode(), _bcrypt.gensalt()).decode()


def _verify_api_key(key: str, hashed: str) -> bool:
    import bcrypt as _bcrypt
    try:
        return _bcrypt.checkpw(key.encode(), hashed.encode())
    except Exception:
        return False


# ── Task Dependencies ─────────────────────────────────────────────────────────

def get_project_dependencies(project_id: str, db) -> list:
    from sqlalchemy.orm import joinedload
    from app.models.task import Task
    from app.models.bookings import TaskDependency
    tasks = db.query(Task).filter(Task.project_id == project_id).all()
    task_ids = {t.id for t in tasks}
    deps = db.query(TaskDependency).options(
        joinedload(TaskDependency.predecessor),
        joinedload(TaskDependency.successor),
    ).filter(TaskDependency.predecessor_id.in_(task_ids)).all()
    return [{
        "id": d.id,
        "predecessor_id": d.predecessor_id,
        "predecessor_title": d.predecessor.title if d.predecessor else None,
        "successor_id": d.successor_id,
        "successor_title": d.successor.title if d.successor else None,
        "dependency_type": d.dependency_type,
        "lag_days": d.lag_days,
    } for d in deps]


def create_task_dependency(payload, created_by_id, db) -> dict:
    from fastapi import HTTPException
    from app.models.bookings import TaskDependency
    if payload.predecessor_id == payload.successor_id:
        raise HTTPException(400, "Una tarea no puede depender de sí misma")
    if db.query(TaskDependency).filter(
        TaskDependency.predecessor_id == payload.successor_id,
        TaskDependency.successor_id == payload.predecessor_id,
    ).first():
        raise HTTPException(400, "Esta dependencia crearía un ciclo")
    if db.query(TaskDependency).filter(
        TaskDependency.predecessor_id == payload.predecessor_id,
        TaskDependency.successor_id == payload.successor_id,
    ).first():
        raise HTTPException(400, "Esta dependencia ya existe")
    dep = TaskDependency(
        predecessor_id=payload.predecessor_id,
        successor_id=payload.successor_id,
        dependency_type=payload.dependency_type,
        lag_days=payload.lag_days,
        created_by=created_by_id,
    )
    db.add(dep); db.commit()
    return {"ok": True, "id": dep.id}


def delete_task_dependency(dep_id: str, db) -> dict:
    from fastapi import HTTPException
    from app.models.bookings import TaskDependency
    dep = db.query(TaskDependency).filter(TaskDependency.id == dep_id).first()
    if not dep: raise HTTPException(404)
    db.delete(dep); db.commit()
    return {"ok": True}


# ── Resource Bookings ─────────────────────────────────────────────────────────

def list_bookings_records(user_id, project_id, start_date, end_date, booking_type, org_id, db) -> list:
    from sqlalchemy.orm import joinedload
    from app.models.user import User
    from app.models.bookings import ResourceBooking
    q = db.query(ResourceBooking).options(
        joinedload(ResourceBooking.user),
        joinedload(ResourceBooking.project),
    )
    if org_id:
        org_user_ids = [r.id for r in db.query(User.id).filter(User.organization_id == org_id).all()]
        q = q.filter(ResourceBooking.user_id.in_(org_user_ids))
    if user_id:       q = q.filter(ResourceBooking.user_id == user_id)
    if project_id:    q = q.filter(ResourceBooking.project_id == project_id)
    if start_date:    q = q.filter(ResourceBooking.end_date >= start_date)
    if end_date:      q = q.filter(ResourceBooking.start_date <= end_date)
    if booking_type:  q = q.filter(ResourceBooking.booking_type == booking_type)
    return [serialize_booking(b) for b in q.order_by(ResourceBooking.start_date).all()]


def get_bookings_heatmap(weeks: int, org_id, db) -> dict:
    from app.core.config import settings
    from app.models.user import User
    from app.models.bookings import ResourceBooking, BookingType
    today = date.today()
    monday = today - timedelta(days=today.weekday())
    users_q = db.query(User).filter(User.is_active == True)
    if org_id:
        users_q = users_q.filter(User.organization_id == org_id)
    users = users_q.order_by(User.full_name).all()
    heatmap_user_ids = [u.id for u in users]
    bookings = db.query(ResourceBooking).filter(
        ResourceBooking.start_date <= monday + timedelta(weeks=weeks),
        ResourceBooking.end_date >= monday,
        ResourceBooking.user_id.in_(heatmap_user_ids),
    ).all()
    result = []
    for user in users:
        weekly = []
        for w in range(weeks):
            week_start = monday + timedelta(weeks=w)
            week_end = week_start + timedelta(days=4)
            capacity = (user.weekly_capacity_hours or settings.DEFAULT_WEEKLY_CAPACITY_HOURS)
            hard_hours = 0
            soft_hours = 0
            for b in bookings:
                if b.user_id != user.id: continue
                overlap_start = max(b.start_date, week_start)
                overlap_end   = min(b.end_date, week_end)
                if overlap_start <= overlap_end:
                    overlap_days = min((overlap_end - overlap_start).days + 1, 5)
                    hours = overlap_days * b.hours_per_day
                    if b.booking_type == BookingType.hard:
                        hard_hours += hours
                    else:
                        soft_hours += hours
            util_pct = round(hard_hours / capacity * 100, 0) if capacity > 0 else 0
            status = "overloaded" if util_pct > 100 else "high" if util_pct > 85 else "ok" if util_pct >= 20 else "free"
            weekly.append({
                "week": str(week_start),
                "week_label": f"{week_start.day}/{week_start.month}",
                "capacity": capacity,
                "hard_hours": round(hard_hours, 1),
                "soft_hours": round(soft_hours, 1),
                "available": round(max(capacity - hard_hours, 0), 1),
                "utilization_pct": util_pct,
                "status": status,
            })
        result.append({
            "user_id": user.id,
            "user_name": user.full_name,
            "role": user.role,
            "department": user.department,
            "capacity_per_week": user.weekly_capacity_hours or settings.DEFAULT_WEEKLY_CAPACITY_HOURS,
            "weeks": weekly,
            "avg_utilization": round(sum(w["utilization_pct"] for w in weekly) / weeks, 1),
        })
    return {
        "weeks": weeks,
        "start_date": str(monday),
        "users": result,
        "week_labels": [(monday + timedelta(weeks=w)).strftime("%d/%m") for w in range(weeks)],
    }


def create_booking_record(payload, created_by_id, db) -> dict:
    from fastapi import HTTPException
    from sqlalchemy.orm import joinedload
    from app.models.bookings import ResourceBooking
    if payload.end_date < payload.start_date:
        raise HTTPException(400, "La fecha fin no puede ser anterior al inicio")
    days = (payload.end_date - payload.start_date).days + 1
    booking = ResourceBooking(
        user_id=payload.user_id,
        project_id=payload.project_id,
        task_id=payload.task_id,
        booking_type=payload.booking_type,
        start_date=payload.start_date,
        end_date=payload.end_date,
        hours_per_day=payload.hours_per_day,
        total_hours=days * payload.hours_per_day,
        note=payload.note,
        created_by=created_by_id,
    )
    db.add(booking); db.commit(); db.refresh(booking)
    booking = db.query(ResourceBooking).options(
        joinedload(ResourceBooking.user), joinedload(ResourceBooking.project)
    ).filter(ResourceBooking.id == booking.id).first()
    return serialize_booking(booking)


def update_booking_record(booking_id: str, payload, db) -> dict:
    from fastapi import HTTPException
    from sqlalchemy.orm import joinedload
    from app.models.bookings import ResourceBooking
    b = db.query(ResourceBooking).filter(ResourceBooking.id == booking_id).first()
    if not b: raise HTTPException(404)
    updates = payload.model_dump(exclude_unset=True)
    if "end_date" in updates and "start_date" in updates and updates["end_date"] < updates["start_date"]:
        raise HTTPException(400, "La fecha fin no puede ser anterior al inicio")
    if "end_date" in updates and "start_date" not in updates and updates["end_date"] < b.start_date:
        raise HTTPException(400, "La fecha fin no puede ser anterior al inicio")
    if "start_date" in updates and "end_date" not in updates and updates["start_date"] > b.end_date:
        raise HTTPException(400, "La fecha inicio no puede ser posterior al fin")
    for k, v in updates.items():
        setattr(b, k, v)
    db.commit()
    return serialize_booking(db.query(ResourceBooking).options(
        joinedload(ResourceBooking.user), joinedload(ResourceBooking.project)
    ).filter(ResourceBooking.id == booking_id).first())


def delete_booking_record(booking_id: str, db) -> dict:
    from fastapi import HTTPException
    from app.models.bookings import ResourceBooking
    b = db.query(ResourceBooking).filter(ResourceBooking.id == booking_id).first()
    if not b: raise HTTPException(404)
    db.delete(b); db.commit()
    return {"ok": True}


# ── Exchange Rates ────────────────────────────────────────────────────────────

def get_exchange_rates_data(base: str, db) -> dict:
    from sqlalchemy import func
    from app.models.bookings import ExchangeRate
    latest_rates = {}
    for row in db.query(
        ExchangeRate.from_currency, ExchangeRate.to_currency,
        func.max(ExchangeRate.effective_date).label("max_date")
    ).filter(ExchangeRate.from_currency == base).group_by(
        ExchangeRate.from_currency, ExchangeRate.to_currency
    ).all():
        rate = db.query(ExchangeRate).filter(
            ExchangeRate.from_currency == row.from_currency,
            ExchangeRate.to_currency == row.to_currency,
            ExchangeRate.effective_date == row.max_date,
        ).first()
        if rate:
            latest_rates[rate.to_currency] = {
                "rate": rate.rate,
                "effective_date": str(rate.effective_date),
                "source": rate.source,
            }
    latest_rates[base] = {"rate": 1.0, "effective_date": str(date.today()), "source": "base"}
    return {"base": base, "rates": latest_rates, "currencies": SUPPORTED_CURRENCIES}


def upsert_exchange_rate_record(payload: dict, db) -> dict:
    from fastapi import HTTPException
    from app.core.config import settings
    from app.models.bookings import ExchangeRate
    from_currency = payload.get("from_currency", settings.DEFAULT_CURRENCY).upper()
    to_currency   = payload.get("to_currency", "USD").upper()
    rate_value    = float(payload.get("rate", 1.0))
    if rate_value <= 0:
        raise HTTPException(400, "El tipo de cambio debe ser mayor que cero")
    effective_date = date.fromisoformat(payload.get("effective_date", str(date.today())))
    for fc, tc, r in [(from_currency, to_currency, rate_value), (to_currency, from_currency, round(1 / rate_value, 6))]:
        existing = db.query(ExchangeRate).filter(
            ExchangeRate.from_currency == fc,
            ExchangeRate.to_currency == tc,
            ExchangeRate.effective_date == effective_date,
        ).first()
        if existing:
            existing.rate = r
        else:
            db.add(ExchangeRate(from_currency=fc, to_currency=tc, rate=r, effective_date=effective_date, source="manual"))
    db.commit()
    return {"ok": True}


def convert_currency_amount(payload: dict, db) -> dict:
    from fastapi import HTTPException
    from app.core.config import settings
    from app.models.bookings import ExchangeRate
    amount    = float(payload.get("amount", 0))
    from_curr = payload.get("from", settings.DEFAULT_CURRENCY).upper()
    to_curr   = payload.get("to", settings.DEFAULT_CURRENCY).upper()
    on_date   = date.fromisoformat(payload.get("date", str(date.today()))) if payload.get("date") else date.today()
    if from_curr == to_curr:
        return {"amount": amount, "from": from_curr, "to": to_curr, "rate": 1.0, "converted": amount}
    rate_row = db.query(ExchangeRate).filter(
        ExchangeRate.from_currency == from_curr,
        ExchangeRate.to_currency == to_curr,
        ExchangeRate.effective_date <= on_date,
    ).order_by(ExchangeRate.effective_date.desc()).first()
    if not rate_row:
        raise HTTPException(404, f"Sin tipo de cambio {from_curr}→{to_curr}. Configura los tipos en Configuración → Monedas.")
    converted = round(amount * rate_row.rate, 2)
    return {
        "amount": amount, "from": from_curr, "to": to_curr,
        "rate": rate_row.rate, "converted": converted,
        "effective_date": str(rate_row.effective_date),
    }


# ── SLA Schedules ─────────────────────────────────────────────────────────────

def list_sla_schedules_records(db) -> list:
    from sqlalchemy.orm import joinedload
    from app.models.bookings import SLASchedule
    return [serialize_schedule(s) for s in db.query(SLASchedule).options(joinedload(SLASchedule.holidays)).all()]


def create_sla_schedule_record(payload, db) -> dict:
    from sqlalchemy.orm import joinedload
    from app.models.bookings import SLASchedule
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
    db.add(s); db.commit(); db.refresh(s)
    s = db.query(SLASchedule).options(joinedload(SLASchedule.holidays)).filter(SLASchedule.id == s.id).first()
    return serialize_schedule(s)


def calculate_sla_deadline_record(payload: dict, db) -> dict:
    from sqlalchemy.orm import joinedload
    from app.models.bookings import SLASchedule
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
    from fastapi import HTTPException
    from app.models.bookings import SLASchedule, SLAHoliday
    schedule = db.query(SLASchedule).filter(SLASchedule.id == schedule_id).first()
    if not schedule: raise HTTPException(404)
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
    from fastapi import HTTPException
    from app.models.bookings import SLAHoliday
    h = db.query(SLAHoliday).filter(SLAHoliday.id == holiday_id, SLAHoliday.schedule_id == schedule_id).first()
    if not h: raise HTTPException(404)
    db.delete(h); db.commit()
    return {"ok": True}


# ── API Keys ──────────────────────────────────────────────────────────────────

def list_api_keys_records(user_id, is_superadmin: bool, db) -> list:
    from app.models.bookings import ApiKey
    q = db.query(ApiKey)
    if not is_superadmin:
        q = q.filter(ApiKey.user_id == user_id)
    return [{
        "id": k.id, "name": k.name,
        "key_prefix": k.key_prefix,
        "scopes": json.loads(k.scopes) if k.scopes else [],
        "is_active": k.is_active,
        "rate_limit_per_hour": k.rate_limit_per_hour,
        "rate_limit_per_day": k.rate_limit_per_day,
        "requests_today": k.requests_today or 0,
        "last_used_at": str(k.last_used_at)[:16] if k.last_used_at else None,
        "expires_at": str(k.expires_at)[:10] if k.expires_at else None,
        "created_at": str(k.created_at)[:10] if k.created_at else None,
    } for k in q.order_by(ApiKey.created_at.desc()).all()]


def create_api_key_record(payload, user_id, db) -> dict:
    from app.models.bookings import ApiKey
    from app.services.audit import audit_log as _audit
    raw_key    = f"nxpm_{secrets.token_hex(24)}"
    key_prefix = raw_key[:12]
    api_key = ApiKey(
        name=payload.name,
        key_hash=_hash_api_key(raw_key),
        key_prefix=key_prefix,
        user_id=user_id,
        scopes=json.dumps(payload.scopes),
        rate_limit_per_hour=payload.rate_limit_per_hour,
        rate_limit_per_day=payload.rate_limit_per_day,
        expires_at=payload.expires_at,
    )
    db.add(api_key)
    db.flush()
    _audit(db, None, "CREATE", "api_keys", api_key.id, payload.name)
    db.commit()
    return {
        "id": api_key.id,
        "name": api_key.name,
        "key": raw_key,
        "key_prefix": key_prefix,
        "warning": "Copia esta clave ahora. No se mostrará de nuevo.",
    }


def revoke_api_key_record(key_id: str, user_id, db) -> dict:
    from fastapi import HTTPException
    from app.models.bookings import ApiKey
    from app.services.audit import audit_log as _audit
    key = db.query(ApiKey).filter(ApiKey.id == key_id, ApiKey.user_id == user_id).first()
    if not key: raise HTTPException(404)
    key.is_active = False
    _audit(db, None, "REVOKE", "api_keys", key.id, key.name)
    db.commit()
    return {"ok": True}


def verify_api_key_record(raw_key: str, db) -> dict:
    from fastapi import HTTPException
    from app.models.bookings import ApiKey
    if not raw_key.startswith("nxpm_"):
        raise HTTPException(401, "API key inválida")
    prefix = raw_key[:12]
    keys = db.query(ApiKey).filter(ApiKey.key_prefix == prefix, ApiKey.is_active == True).all()
    for key in keys:
        if _verify_api_key(raw_key, key.key_hash):
            if key.expires_at and key.expires_at < datetime.now(timezone.utc):
                raise HTTPException(401, "API key expirada")
            if key.requests_today >= key.rate_limit_per_day:
                raise HTTPException(429, "Límite diario de requests alcanzado")
            if key.requests_this_hour >= key.rate_limit_per_hour:
                raise HTTPException(429, "Límite por hora de requests alcanzado")
            key.last_used_at      = datetime.now(timezone.utc)
            key.requests_today    = (key.requests_today or 0) + 1
            key.requests_this_hour = (key.requests_this_hour or 0) + 1
            db.commit()
            return {"valid": True, "user_id": key.user_id,
                    "scopes": json.loads(key.scopes) if key.scopes else [], "name": key.name}
    raise HTTPException(401, "API key inválida o inactiva")


# ── Recurring Invoices ────────────────────────────────────────────────────────

def list_recurring_records(db) -> list:
    from sqlalchemy.orm import joinedload
    from app.models.bookings import RecurringInvoice
    items = db.query(RecurringInvoice).options(joinedload(RecurringInvoice.project)).order_by(RecurringInvoice.next_date).all()
    return [serialize_recurring(r) for r in items]


def create_recurring_record(payload, created_by_id, db) -> dict:
    from app.models.bookings import RecurringInvoice
    r = RecurringInvoice(created_by=created_by_id, **payload.model_dump())
    db.add(r); db.commit(); db.refresh(r)
    return serialize_recurring(r)


def update_recurring_record(rec_id: str, payload: dict, db) -> dict:
    from fastapi import HTTPException
    from app.models.bookings import RecurringInvoice
    r = db.query(RecurringInvoice).filter(RecurringInvoice.id == rec_id).first()
    if not r: raise HTTPException(404)
    for k, v in payload.items():
        if hasattr(r, k): setattr(r, k, v)
    db.commit()
    return {"ok": True}


def process_due_recurring_records(db, current_user) -> dict:
    from app.models.bookings import RecurringInvoice
    today = date.today()
    due = db.query(RecurringInvoice).filter(
        RecurringInvoice.is_active == True,
        RecurringInvoice.next_date <= today,
    ).all()
    generated = []
    for r in due:
        try:
            generate_recurring_now_record(r.id, db, current_user)
            generated.append(r.id)
        except Exception as e:
            logger.warning(f"Failed to generate recurring item {r.id}: {e}", exc_info=True)
    return {"processed": len(due), "generated": len(generated)}


def generate_recurring_now_record(rec_id: str, db, current_user) -> dict:
    import re as _re
    import calendar as _cal
    from fastapi import HTTPException
    from sqlalchemy import func
    from sqlalchemy.orm import joinedload
    from app.models.bookings import RecurringInvoice
    from app.models.billing_reports import Invoice, InvoiceLine
    r = db.query(RecurringInvoice).options(joinedload(RecurringInvoice.project)).filter(RecurringInvoice.id == rec_id).first()
    if not r: raise HTTPException(404)
    if not r.is_active: raise HTTPException(400, "Factura recurrente inactiva")
    year = datetime.now(timezone.utc).year
    max_inv = db.query(func.max(Invoice.number)).filter(Invoice.number.like(f"INV-{year}-%")).scalar()
    if max_inv:
        _m = _re.search(r"(\d+)$", max_inv)
        next_inv_num = (int(_m.group(1)) + 1) if _m else 1
    else:
        next_inv_num = 1
    inv_number = f"INV-{year}-{next_inv_num:04d}"
    subtotal   = r.amount
    tax_amount = round(subtotal * r.tax_rate / 100, 2)
    total      = round(subtotal + tax_amount, 2)
    inv = Invoice(
        number=inv_number, project_id=r.project_id, contract_id=r.contract_id,
        client_name=r.client_name or (r.project.client_name if r.project else None),
        client_email=r.client_email, client_vat=r.client_vat,
        issue_date=date.today(),
        due_date=date.today() + timedelta(days=r.payment_terms_days),
        tax_rate=r.tax_rate, tax_amount=tax_amount,
        subtotal=subtotal, total=total, currency=r.currency,
        notes=f"Generada automáticamente de serie: {r.name}",
        created_by=current_user.id,
    )
    db.add(inv); db.flush()
    if r.description:
        db.add(InvoiceLine(
            invoice_id=inv.id, order=0,
            description=r.description or r.name,
            quantity=1, unit="servicio",
            unit_price=subtotal, discount_pct=0, amount=subtotal,
            source_type="recurring",
        ))
    freq = r.frequency.value if hasattr(r.frequency, "value") else str(r.frequency)
    if freq == "weekly":
        r.next_date = r.next_date + timedelta(weeks=1)
    elif freq == "monthly":
        m = r.next_date.month + 1
        y = r.next_date.year + (m - 1) // 12
        m = ((m - 1) % 12) + 1
        day = min(r.next_date.day, _cal.monthrange(y, m)[1])
        r.next_date = r.next_date.replace(year=y, month=m, day=day)
    elif freq == "quarterly":
        m = r.next_date.month + 3
        y = r.next_date.year + (m - 1) // 12
        m = ((m - 1) % 12) + 1
        day = min(r.next_date.day, _cal.monthrange(y, m)[1])
        r.next_date = r.next_date.replace(year=y, month=m, day=day)
    elif freq == "annually":
        y   = r.next_date.year + 1
        day = min(r.next_date.day, _cal.monthrange(y, r.next_date.month)[1])
        r.next_date = r.next_date.replace(year=y, day=day)
    if r.end_date and r.next_date > r.end_date:
        r.is_active = False
    r.last_generated_at = datetime.now(timezone.utc)
    r.total_generated   = (r.total_generated or 0) + 1
    db.commit()
    return {"ok": True, "invoice_id": inv.id, "invoice_number": inv_number, "next_date": str(r.next_date)}


# ── Pipeline Ops ──────────────────────────────────────────────────────────────

def convert_opportunity_to_project_record(opportunity_id: str, payload: dict, current_user, db) -> dict:
    from fastapi import HTTPException
    from app.core.config import settings
    from app.models.pipeline import Opportunity, OpportunityStage
    from app.models.project import Project, ProjectStatus
    from app.services.audit import audit_log as _audit
    opp = db.query(Opportunity).filter(Opportunity.id == opportunity_id).first()
    if not opp: raise HTTPException(404, "Oportunidad no encontrada")
    if opp.stage not in [OpportunityStage.closed_won, "closed_won"]:
        opp.stage = OpportunityStage.closed_won
    last = db.query(Project).order_by(Project.created_at.desc()).first()
    next_num = 1
    if last and last.code and last.code.startswith("PRJ-"):
        parts = last.code.split("-")
        if len(parts) > 1 and parts[1].isdigit():
            next_num = int(parts[1]) + 1
    code    = payload.get("code") or f"PRJ-{next_num:03d}"
    project = Project(
        code=code,
        name=payload.get("name") or opp.name,
        client_name=opp.client_name,
        client_id=getattr(opp, "client_id", None),
        project_type=payload.get("project_type", settings.DEFAULT_PROJECT_TYPE),
        status=ProjectStatus.planning,
        start_date=date.fromisoformat(payload["start_date"]) if payload.get("start_date") else date.today(),
        end_date_planned=date.fromisoformat(payload["end_date"]) if payload.get("end_date") else None,
        budget_amount=opp.amount,
        billing_type=payload.get("billing_type", settings.DEFAULT_BILLING_TYPE),
        is_billable=True,
        pm_id=payload.get("pm_id"),
        contract_amount=opp.amount,
        currency=payload.get("currency", settings.DEFAULT_CURRENCY),
        description=opp.description,
        created_by=current_user.id,
    )
    db.add(project)
    opp.project_id = project.id
    _audit(db, current_user, "CONVERT_OPPORTUNITY", "projects", project.id, project.name,
           new_values={"opportunity_id": opportunity_id, "amount": opp.amount})
    db.commit()
    return {"ok": True, "project_id": project.id, "project_code": project.code, "project_name": project.name}


def get_pipeline_revenue_forecast(db) -> dict:
    from app.models.pipeline import Opportunity
    opps = db.query(Opportunity).filter(Opportunity.stage.notin_(["closed_won", "closed_lost"])).all()
    by_month: dict = {}
    total_weighted = 0
    total_pipeline = 0
    for opp in opps:
        if not opp.expected_close_date or not opp.amount: continue
        prob     = (opp.probability_pct or 0) / 100
        weighted = round(opp.amount * prob, 2)
        total_weighted += weighted
        total_pipeline += opp.amount or 0
        month_key = opp.expected_close_date.strftime("%Y-%m")
        if month_key not in by_month:
            by_month[month_key] = {"month": month_key, "pipeline": 0, "weighted": 0, "count": 0}
        by_month[month_key]["pipeline"] += opp.amount or 0
        by_month[month_key]["weighted"] += weighted
        by_month[month_key]["count"]    += 1
    return {
        "total_pipeline": round(total_pipeline, 2),
        "total_weighted": round(total_weighted, 2),
        "by_month": sorted(by_month.values(), key=lambda x: x["month"]),
        "opportunities": len(opps),
        "avg_probability": round(sum(o.probability_pct or 0 for o in opps) / max(len(opps), 1), 1),
    }


# ── ITSM Aging ────────────────────────────────────────────────────────────────

def get_ticket_aging_report(db) -> dict:
    from sqlalchemy.orm import joinedload
    from app.models.service_desk import Ticket
    open_statuses = ["new", "assigned", "in_progress", "pending_client"]
    tickets = db.query(Ticket).options(joinedload(Ticket.assignee)).filter(Ticket.status.in_(open_statuses)).all()
    now = datetime.now(timezone.utc)
    aging_buckets = {
        "0-4h":  {"label": "0-4 horas",  "color": "#00e5a0", "tickets": []},
        "4-8h":  {"label": "4-8 horas",  "color": "#7a8aaa", "tickets": []},
        "8-24h": {"label": "8-24 horas", "color": "#ffb800", "tickets": []},
        "1-3d":  {"label": "1-3 días",   "color": "#f97316", "tickets": []},
        "3d+":   {"label": "+3 días",    "color": "#ff4757", "tickets": []},
    }
    for t in tickets:
        age_hours = (now - t.created_at).total_seconds() / 3600 if t.created_at else 0
        mini = {
            "id": t.id, "number": t.number, "title": t.title[:50],
            "priority": t.priority, "status": t.status,
            "assignee": t.assignee.full_name if t.assignee else "Sin asignar",
            "age_hours": round(age_hours, 1),
            "age_label": f"{int(age_hours)}h" if age_hours < 48 else f"{int(age_hours/24)}d",
            "sla_due": str(t.sla_resolution_due)[:16] if t.sla_resolution_due else None,
            "sla_breached": t.sla_resolution_due and t.sla_resolution_due < now,
        }
        if age_hours < 4:    aging_buckets["0-4h"]["tickets"].append(mini)
        elif age_hours < 8:  aging_buckets["4-8h"]["tickets"].append(mini)
        elif age_hours < 24: aging_buckets["8-24h"]["tickets"].append(mini)
        elif age_hours < 72: aging_buckets["1-3d"]["tickets"].append(mini)
        else:                aging_buckets["3d+"]["tickets"].append(mini)
    for bucket in aging_buckets.values():
        bucket["count"] = len(bucket["tickets"])
        bucket["tickets"].sort(key=lambda x: -x["age_hours"])
    wall_board = {
        "open_total": len(tickets),
        "sla_breached": sum(1 for t in tickets if t.sla_resolution_due and t.sla_resolution_due < now),
        "unassigned": sum(1 for t in tickets if not t.assigned_to_user_id),
        "oldest_hours": round(max(((now - t.created_at).total_seconds() / 3600 for t in tickets), default=0), 1),
    }
    return {"aging_buckets": aging_buckets, "wall_board": wall_board, "generated_at": now.isoformat()}


def get_wallboard_data(db) -> dict:
    from datetime import time as _time
    from sqlalchemy.orm import joinedload
    from app.models.service_desk import Ticket
    now = datetime.now(timezone.utc)
    today = now.date()
    open_statuses = ["new", "assigned", "in_progress", "pending_client"]
    tickets_open  = db.query(Ticket).filter(Ticket.status.in_(open_statuses)).all()
    today_start   = datetime.combine(today, _time(0, 0, 0), tzinfo=timezone.utc)
    today_end     = today_start + timedelta(days=1)
    tickets_today = db.query(Ticket).filter(Ticket.created_at >= today_start, Ticket.created_at < today_end).all()
    resolved_today = db.query(Ticket).filter(
        Ticket.resolved_at >= today_start, Ticket.resolved_at < today_end,
        Ticket.status.in_(["resolved", "closed"])
    ).all()
    sla_breached = [t for t in tickets_open if t.sla_resolution_due and t.sla_resolution_due < now]
    sla_at_risk  = [t for t in tickets_open if t.sla_resolution_due and now < t.sla_resolution_due <= now + timedelta(hours=2)]
    by_priority  = {pri: sum(1 for t in tickets_open if t.priority == pri)
                    for pri in ["p1_critical", "p2_high", "p3_medium", "p4_low"]}
    by_agent: dict = {}
    for t in tickets_open:
        if t.assigned_to_user_id:
            name = t.assignee.full_name if t.assignee else t.assigned_to_user_id
            by_agent[name] = by_agent.get(name, 0) + 1
    return {
        "timestamp": now.isoformat(),
        "open": len(tickets_open),
        "created_today": len(tickets_today),
        "resolved_today": len(resolved_today),
        "sla_breached": len(sla_breached),
        "sla_at_risk": len(sla_at_risk),
        "unassigned": sum(1 for t in tickets_open if not t.assigned_to_user_id),
        "by_priority": by_priority,
        "by_agent": sorted(by_agent.items(), key=lambda x: -x[1])[:8],
        "critical_tickets": [{
            "number": t.number, "title": t.title[:50],
            "priority": t.priority,
            "age_hours": round((now - t.created_at).total_seconds() / 3600, 1),
            "sla_due": str(t.sla_resolution_due)[:16] if t.sla_resolution_due else None,
        } for t in sorted(sla_breached, key=lambda x: x.priority)[:5]],
    }


# ── SSO ───────────────────────────────────────────────────────────────────────

def initiate_sso_record(config_id: str, redirect_to: str, db) -> dict:
    from fastapi import HTTPException
    from app.core.config import settings
    from app.models.enterprise import SSOConfig
    from app.models.bookings import OAuthState
    config = db.query(SSOConfig).filter(SSOConfig.id == config_id, SSOConfig.is_active == True).first()
    if not config: raise HTTPException(404, "Configuración SSO no encontrada o inactiva")
    state = secrets.token_urlsafe(32)
    oauth_state = OAuthState(
        state=state, sso_config_id=config_id, redirect_to=redirect_to,
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=10),
    )
    db.add(oauth_state); db.commit()
    if config.provider == "saml":
        acs_url = f"{settings.BACKEND_URL}/api/v1/sso/saml/callback"
        redirect_url = f"{config.saml_sso_url}?SAMLRequest=DEMO_ENCODED_REQUEST&RelayState={state}"
    elif config.provider in ["google", "azure_ad", "okta", "oidc"]:
        discovery_url = config.oidc_discovery_url or {
            "google": settings.GOOGLE_OAUTH_BASE,
            "azure_ad": f"{settings.MICROSOFT_OAUTH_BASE}/common/v2.0",
            "okta": "https://your-domain.okta.com",
        }.get(config.provider, "")
        redirect_url = (
            f"{discovery_url}/authorize"
            f"?client_id={config.oidc_client_id}"
            f"&redirect_uri={settings.BACKEND_URL}/api/v1/sso/oidc/callback"
            f"&response_type=code"
            f"&scope={config.oidc_scopes or 'openid email profile'}"
            f"&state={state}"
        )
    else:
        raise HTTPException(400, f"Proveedor no soportado: {config.provider}")
    return {"redirect_url": redirect_url, "state": state, "provider": config.provider,
            "note": "Redirige al usuario a redirect_url para completar la autenticación SSO"}


def sso_create_or_login_user(db, email, name, role_from_sso, config, redirect_to) -> dict:
    from fastapi import HTTPException
    from app.models.user import User
    from app.core.security import create_access_token
    user = db.query(User).filter(User.email == email).first()
    if not user:
        if not config.auto_create_users:
            raise HTTPException(403, "Usuario no existe y auto-provisioning está desactivado")
        role = config.default_role or "employee"
        if role_from_sso and config.role_mapping:
            try:
                mapping = json.loads(config.role_mapping)
                role = mapping.get(role_from_sso, role)
            except Exception:
                pass
        username = email.split("@")[0]
        if db.query(User).filter(User.username == username).first():
            username = f"{username}_{secrets.token_hex(4)}"
        user = User(username=username, email=email, full_name=name or email,
                    role=role, hashed_password=None)
        db.add(user)
    user.last_login = datetime.now(timezone.utc)
    db.commit()
    token = create_access_token(subject=user.id, extra={"role": user.role, "sso": True})
    return {
        "access_token": token, "token_type": "bearer",
        "user": {"id": user.id, "email": user.email, "full_name": user.full_name, "role": user.role},
        "redirect_to": redirect_to,
        "is_new_user": user.created_at and (datetime.now(timezone.utc) - user.created_at).total_seconds() < 10,
    }


def process_saml_callback(payload: dict, db) -> dict:
    from fastapi import HTTPException
    from app.models.enterprise import SSOConfig
    from app.models.bookings import OAuthState
    relay_state = payload.get("RelayState") or payload.get("state")
    state_obj = db.query(OAuthState).filter(
        OAuthState.state == relay_state,
        OAuthState.used == False,
        OAuthState.expires_at > datetime.now(timezone.utc),
    ).first()
    if not state_obj: raise HTTPException(400, "Estado SSO inválido o expirado")
    config = db.query(SSOConfig).filter(SSOConfig.id == state_obj.sso_config_id).first()
    if not config: raise HTTPException(400, "Configuración SSO no encontrada")
    state_obj.used = True
    user_email    = payload.get("email") or payload.get("attributes", {}).get(config.saml_attribute_email)
    user_name     = payload.get("name") or payload.get("attributes", {}).get(config.saml_attribute_name, user_email)
    user_role_sso = payload.get("role") or payload.get("attributes", {}).get(config.saml_attribute_role)
    if not user_email: raise HTTPException(400, "El IdP no proporcionó un email en la respuesta SAML")
    if config.allowed_domains:
        allowed = [d.strip() for d in config.allowed_domains.split(",")]
        domain  = user_email.split("@")[-1] if "@" in user_email else ""
        if domain not in allowed:
            raise HTTPException(403, f"Dominio {domain} no autorizado para este SSO")
    return sso_create_or_login_user(db, user_email, user_name, user_role_sso, config, state_obj.redirect_to)


def process_oidc_callback(payload: dict, db) -> dict:
    from fastapi import HTTPException
    from app.models.enterprise import SSOConfig
    from app.models.bookings import OAuthState
    state = payload.get("state")
    state_obj = db.query(OAuthState).filter(
        OAuthState.state == state,
        OAuthState.used == False,
        OAuthState.expires_at > datetime.now(timezone.utc),
    ).first()
    if not state_obj: raise HTTPException(400, "Estado OIDC inválido o expirado")
    config = db.query(SSOConfig).filter(SSOConfig.id == state_obj.sso_config_id).first()
    state_obj.used = True
    user_email    = payload.get("email")
    user_name     = payload.get("name") or user_email
    user_role_sso = payload.get("role")
    if not user_email: raise HTTPException(400, "No se pudo obtener el email del usuario desde el IdP OIDC")
    return sso_create_or_login_user(db, user_email, user_name, user_role_sso, config, state_obj.redirect_to)


# ── Workflow Queue ────────────────────────────────────────────────────────────

def enqueue_workflow_record(payload: dict, user_id, db) -> dict:
    from fastapi import HTTPException
    from app.models.billing_reports import AutomationWorkflow
    from app.models.bookings import WorkflowQueueItem
    workflow_id = payload.get("workflow_id")
    wf = db.query(AutomationWorkflow).filter(AutomationWorkflow.id == workflow_id).first()
    if not wf: raise HTTPException(404, "Workflow no encontrado")
    execute_at = datetime.now(timezone.utc)
    if payload.get("delay_minutes"):
        execute_at += timedelta(minutes=int(payload["delay_minutes"]))
    item = WorkflowQueueItem(
        workflow_id=workflow_id,
        trigger_data=json.dumps(payload.get("context", {})),
        execute_at=execute_at,
        status="pending",
    )
    db.add(item); db.commit()
    return {"ok": True, "queue_id": item.id, "execute_at": execute_at.isoformat()}


def process_workflow_queue_record(db) -> dict:
    from sqlalchemy.orm import joinedload
    from app.models.billing_reports import AutomationWorkflow, WorkflowExecution
    from app.models.bookings import WorkflowQueueItem
    now = datetime.now(timezone.utc)
    pending = db.query(WorkflowQueueItem).filter(
        WorkflowQueueItem.status == "pending",
        WorkflowQueueItem.execute_at <= now,
        WorkflowQueueItem.attempts < 3,
    ).limit(20).all()
    processed = 0
    errors = 0
    for item in pending:
        item.status  = "processing"
        item.attempts += 1
        db.commit()
        try:
            wf = db.query(AutomationWorkflow).options(
                joinedload(AutomationWorkflow.steps)
            ).filter(AutomationWorkflow.id == item.workflow_id).first()
            if not wf or wf.status != "active":
                item.status = "done"; db.commit(); continue
            context = json.loads(item.trigger_data) if item.trigger_data else {}
            steps   = sorted(wf.steps, key=lambda s: s.order)
            results = []
            for step in steps[item.step_index:]:
                config     = json.loads(step.config) if step.config else {}
                step_result = {"step": step.name or step.step_type, "ok": True}
                if step.step_type == "action":
                    action_type = config.get("type", "create_alert")
                    if action_type == "create_alert":
                        from app.models.alert import Alert
                        db.add(Alert(alert_type="workflow",
                                     message=config.get("message", "Workflow ejecutado"),
                                     severity=config.get("severity", "info"),
                                     project_id=context.get("project_id")))
                    elif action_type == "notify_role":
                        from app.services.notifications import notify_role
                        notify_role(db, config.get("role", "admin"), "automation",
                                    config.get("message", "Workflow ejecutado"))
                elif step.step_type == "wait":
                    delay_minutes = config.get("duration", 60)
                    unit = config.get("unit", "minutes")
                    if unit == "hours": delay_minutes *= 60
                    elif unit == "days": delay_minutes *= 1440
                    new_item = WorkflowQueueItem(
                        workflow_id=item.workflow_id,
                        trigger_data=item.trigger_data,
                        execute_at=now + timedelta(minutes=delay_minutes),
                        step_index=steps.index(step) + 1,
                        status="pending",
                    )
                    db.add(new_item)
                    item.status = "done"
                    step_result["waiting_until"] = (now + timedelta(minutes=delay_minutes)).isoformat()
                    results.append(step_result)
                    db.commit()
                    break
                elif step.step_type == "condition":
                    field = config.get("field"); operator = config.get("operator", "equals"); value = config.get("value")
                    ctx_val = context.get(field)
                    condition_met = (
                        (operator == "equals"       and str(ctx_val) == str(value)) or
                        (operator == "not_equals"   and str(ctx_val) != str(value)) or
                        (operator == "greater_than" and float(ctx_val or 0) > float(value or 0)) or
                        (operator == "less_than"    and float(ctx_val or 0) < float(value or 0))
                    )
                    step_result["condition_met"] = condition_met
                elif step.step_type == "webhook":
                    try:
                        import httpx
                        url = config.get("url")
                        if url:
                            with httpx.Client(timeout=5.0) as client:
                                resp = client.post(url, json={"event": config.get("event"), "context": context})
                            step_result["http_status"] = resp.status_code
                    except Exception as e:
                        step_result["ok"] = False; step_result["error"] = str(e)[:100]
                results.append(step_result)
            exec_log = WorkflowExecution(
                workflow_id=item.workflow_id, trigger_context=item.trigger_data,
                status="completed", steps_log=json.dumps(results), completed_at=now,
            ) if not item.execution_id else None
            if exec_log: db.add(exec_log)
            wf.run_count     = (wf.run_count or 0) + 1
            wf.success_count = (wf.success_count or 0) + 1
            wf.last_run_at   = now
            item.status      = "done"
            item.processed_at = now
            processed += 1
            db.commit()
        except Exception as e:
            item.status     = "failed" if item.attempts >= 3 else "pending"
            item.last_error = str(e)[:500]
            errors += 1
            db.commit()
    return {"processed": processed, "errors": errors,
            "remaining": db.query(WorkflowQueueItem).filter(WorkflowQueueItem.status == "pending").count()}
