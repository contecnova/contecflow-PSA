"""Reservas de recursos: listado, mapa de calor y control de capacidad.

Parte de `app.services.bookings_service` (auditoria 2026-11, #24): se partio por responsabilidad
sin cambiar el codigo. El paquete reexporta todos los nombres.
"""
from __future__ import annotations

from datetime import timedelta
from app.core.config import settings
from app.models.bookings import ResourceBooking
from app.models.bookings import BookingType
from app.models.user import User
from sqlalchemy.orm import joinedload
from app.core import timeutil
from app.core.errores import ErrorDeDominio


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
def list_bookings_records(user_id, project_id, start_date, end_date, booking_type, org_id, db) -> list:
    q = db.query(ResourceBooking).options(
        joinedload(ResourceBooking.user),
        joinedload(ResourceBooking.project),
    ).filter(ResourceBooking.is_active == True)
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
    today = timeutil.today()
    monday = today - timedelta(days=today.weekday())
    users_q = db.query(User).filter(User.is_active == True)
    if org_id:
        users_q = users_q.filter(User.organization_id == org_id)
    users = users_q.order_by(User.full_name).all()
    heatmap_user_ids = [u.id for u in users]
    bookings = db.query(ResourceBooking).filter(
        ResourceBooking.is_active == True,
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
            # Revisión 2026-11: la capacidad de la semana descuenta ausencias aprobadas y festivos,
            # igual que la comprobación al reservar (antes el mapa no los veía).
            from app.services.resource_analytics import get_user_week_hours
            hw = get_user_week_hours(db, user.id, week_start)
            capacity = max(0.0, (user.weekly_capacity_hours or settings.DEFAULT_WEEKLY_CAPACITY_HOURS)
                           - hw["absence_hours"] - hw["holiday_hours"])
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


def _horas_en_semana(inicio, fin, horas_dia, lunes) -> float:
    from datetime import timedelta
    domingo = lunes + timedelta(days=6)
    a, b = max(inicio, lunes), min(fin, domingo)
    return sum(1 for i in range(max(0, (b - a).days + 1)) if (a + timedelta(days=i)).weekday() < 5) * horas_dia


def comprobar_capacidad(db, user_id, inicio, fin, horas_dia, tipo, excluir=None) -> None:
    """Una reserva firme no pasa de la capacidad de ninguna de sus semanas (400).

    Revisión 2026-11: crear y mover no comprobaban nada. La capacidad de la
    semana descuenta ausencias aprobadas y festivos; una reserva `soft` es
    tentativa y no bloquea. `excluir`: la propia reserva al editarla.
    """
    from datetime import timedelta
    from app.core.config import settings
    from app.models.user import User
    from app.services.resource_analytics import get_user_week_hours
    if str(getattr(tipo, "value", tipo)) == "soft":
        return
    usuario = db.query(User).filter(User.id == user_id).first()
    base = (getattr(usuario, "weekly_capacity_hours", None) or settings.DEFAULT_WEEKLY_CAPACITY_HOURS)
    lunes = inicio - timedelta(days=inicio.weekday())
    while lunes <= fin:
        hw = get_user_week_hours(db, user_id, lunes)
        ya = hw["committed_hours"]
        if excluir is not None and str(getattr(excluir.booking_type, "value", excluir.booking_type)) != "soft":
            ya -= _horas_en_semana(excluir.start_date, excluir.end_date, excluir.hours_per_day or 0, lunes)
        capacidad = max(0.0, base - hw["absence_hours"] - hw["holiday_hours"])
        nuevas = _horas_en_semana(inicio, fin, horas_dia, lunes)
        if nuevas and ya + nuevas > capacidad + 1e-6:
            raise ErrorDeDominio(400, (
                f"Semana del {lunes}: ya tiene {ya:g} h comprometidas y esta reserva suma {nuevas:g} h; "
                f"su capacidad es {capacidad:g} h. Resérvala como tentativa (soft) o ajusta las horas."))
        lunes += timedelta(days=7)


def create_booking_record(payload, created_by_id, db) -> dict:
    # Only block exact duplicate: same user + same project already booked in overlapping dates
    if payload.project_id:
        duplicate = db.query(ResourceBooking).filter(
            ResourceBooking.is_active == True,
            ResourceBooking.user_id == payload.user_id,
            ResourceBooking.project_id == payload.project_id,
            ResourceBooking.start_date <= payload.end_date,
            ResourceBooking.end_date >= payload.start_date,
        ).first()
        if duplicate:
            raise ErrorDeDominio(400, "Este usuario ya tiene una reserva para este proyecto en las fechas indicadas.")
    if payload.end_date < payload.start_date:
        raise ErrorDeDominio(400, "La fecha fin no puede ser anterior al inicio")
    comprobar_capacidad(db, payload.user_id, payload.start_date, payload.end_date,
                        payload.hours_per_day, payload.booking_type)
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
    b = db.query(ResourceBooking).filter(
        ResourceBooking.id == booking_id,
        ResourceBooking.is_active == True,
    ).first()
    if not b: raise ErrorDeDominio(404)
    updates = payload.model_dump(exclude_unset=True)
    if "end_date" in updates and "start_date" in updates and updates["end_date"] < updates["start_date"]:
        raise ErrorDeDominio(400, "La fecha fin no puede ser anterior al inicio")
    if "end_date" in updates and "start_date" not in updates and updates["end_date"] < b.start_date:
        raise ErrorDeDominio(400, "La fecha fin no puede ser anterior al inicio")
    if "start_date" in updates and "end_date" not in updates and updates["start_date"] > b.end_date:
        raise ErrorDeDominio(400, "La fecha inicio no puede ser posterior al fin")
    comprobar_capacidad(db, updates.get("user_id", b.user_id), updates.get("start_date", b.start_date),
                        updates.get("end_date", b.end_date), updates.get("hours_per_day", b.hours_per_day),
                        updates.get("booking_type", b.booking_type), excluir=b)
    for k, v in updates.items():
        setattr(b, k, v)
    b.total_hours = ((b.end_date - b.start_date).days + 1) * (b.hours_per_day or 0)
    db.commit()
    return serialize_booking(db.query(ResourceBooking).options(
        joinedload(ResourceBooking.user), joinedload(ResourceBooking.project)
    ).filter(
        ResourceBooking.id == booking_id,
        ResourceBooking.is_active == True,
    ).first())


def delete_booking_record(booking_id: str, db) -> dict:
    b = db.query(ResourceBooking).filter(
        ResourceBooking.id == booking_id,
        ResourceBooking.is_active == True,
    ).first()
    if not b: raise ErrorDeDominio(404)
    b.is_active = False
    db.commit()
    return {"ok": True, "message": "Reserva eliminada correctamente"}
