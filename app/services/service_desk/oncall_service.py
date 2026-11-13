from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session, joinedload

from app.models.service_desk import OnCallEntry, OnCallSchedule
from app.schemas.service_desk import OnCallEntryIn, OnCallScheduleIn
import logging
from app.core.errores import ErrorDeDominio

logger = logging.getLogger(__name__)


def list_oncall_schedules_query(db: Session, group_id: Optional[str] = None):
    q = db.query(OnCallSchedule).options(
        joinedload(OnCallSchedule.group),
        joinedload(OnCallSchedule.entries).joinedload(OnCallEntry.user),
    )
    if group_id:
        q = q.filter(OnCallSchedule.group_id == group_id)
    return q


def list_oncall_schedules_payload(db: Session, group_id: Optional[str] = None) -> list[dict]:
    schedules = list_oncall_schedules_query(db, group_id).order_by(OnCallSchedule.name).all()
    return [serialize_oncall_schedule(schedule) for schedule in schedules]


def serialize_oncall_schedule(schedule: OnCallSchedule) -> dict:
    return {
        "id": schedule.id,
        "name": schedule.name,
        "group_id": schedule.group_id,
        "group_name": schedule.group.name if schedule.group else None,
        "rotation": schedule.rotation,
        "timezone": schedule.timezone,
        "is_active": schedule.is_active,
        "description": schedule.description,
        "entries": [
            {
                "id": entry.id,
                "user_id": entry.user_id,
                "user_name": entry.user.full_name if entry.user else None,
                "start_dt": entry.start_dt.isoformat(),
                "end_dt": entry.end_dt.isoformat(),
                "notes": entry.notes,
            }
            for entry in (schedule.entries or [])
        ],
    }


def build_oncall_schedule(payload: OnCallScheduleIn) -> OnCallSchedule:
    return OnCallSchedule(**payload.model_dump())


def create_oncall_schedule_record(db, payload: OnCallScheduleIn) -> OnCallSchedule:
    s = build_oncall_schedule(payload)
    db.add(s)
    return s


def get_oncall_schedule_by_id(db: Session, schedule_id: str) -> OnCallSchedule:
    schedule = db.query(OnCallSchedule).filter(OnCallSchedule.id == schedule_id).first()
    if not schedule:
        raise ErrorDeDominio(404)
    return schedule


def apply_oncall_schedule_update(schedule: OnCallSchedule, payload: OnCallScheduleIn) -> None:
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(schedule, key, value)


def update_oncall_schedule_record(db: Session, schedule_id: str, payload: OnCallScheduleIn) -> OnCallSchedule:
    schedule = get_oncall_schedule_by_id(db, schedule_id)
    apply_oncall_schedule_update(schedule, payload)
    return schedule


def delete_oncall_schedule(db: Session, schedule_id: str) -> None:
    s = get_oncall_schedule_by_id(db, schedule_id)
    db.delete(s)


def validate_oncall_entry_dates(payload: OnCallEntryIn) -> None:
    if payload.start_dt >= payload.end_dt:
        raise ErrorDeDominio(400, "start_dt must be before end_dt")


def build_oncall_entry(schedule_id: str, payload: OnCallEntryIn) -> OnCallEntry:
    return OnCallEntry(schedule_id=schedule_id, **payload.model_dump())


def create_oncall_entry_record(db: Session, schedule_id: str, payload: OnCallEntryIn) -> OnCallEntry:
    get_oncall_schedule_by_id(db, schedule_id)
    validate_oncall_entry_dates(payload)
    entry = build_oncall_entry(schedule_id, payload)
    db.add(entry)
    return entry


def get_oncall_entry_by_id(db: Session, entry_id: str) -> OnCallEntry:
    entry = db.query(OnCallEntry).filter(OnCallEntry.id == entry_id).first()
    if not entry:
        raise ErrorDeDominio(404)
    return entry


def delete_oncall_entry(db: Session, entry_id: str) -> None:
    entry = get_oncall_entry_by_id(db, entry_id)
    db.delete(entry)


def list_current_oncall_entries_query(db: Session, group_id: Optional[str] = None):
    now = datetime.now(timezone.utc)
    q = db.query(OnCallEntry).options(
        joinedload(OnCallEntry.user),
        joinedload(OnCallEntry.schedule).joinedload(OnCallSchedule.group),
    ).filter(
        OnCallEntry.start_dt <= now,
        OnCallEntry.end_dt > now,
    )
    if group_id:
        q = q.join(OnCallSchedule).filter(OnCallSchedule.group_id == group_id)
    return q


def list_current_oncall_payload(db: Session, group_id: Optional[str] = None) -> list[dict]:
    entries = list_current_oncall_entries_query(db, group_id).all()
    return [serialize_current_oncall_entry(entry) for entry in entries]


def serialize_current_oncall_entry(entry: OnCallEntry) -> dict:
    return {
        "schedule_id": entry.schedule_id,
        "schedule_name": entry.schedule.name if entry.schedule else None,
        "group_name": entry.schedule.group.name if entry.schedule and entry.schedule.group else None,
        "user_id": entry.user_id,
        "user_name": entry.user.full_name if entry.user else None,
        "user_email": entry.user.email if entry.user else None,
        "until": entry.end_dt.isoformat(),
    }
