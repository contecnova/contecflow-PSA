from typing import Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models.service_desk import SDSLAHoliday
from app.schemas.service_desk import HolidayIn


def list_holidays_query(db: Session, year: Optional[int] = None, country: Optional[str] = None):
    q = db.query(SDSLAHoliday)
    if year:
        q = q.filter(SDSLAHoliday.holiday_date.like(f"{year}-%"))
    if country:
        q = q.filter((SDSLAHoliday.country == country) | (SDSLAHoliday.country == None))
    return q


def list_holidays_payload(db: Session, year: Optional[int] = None, country: Optional[str] = None) -> list[dict]:
    holidays = list_holidays_query(db, year, country).order_by(SDSLAHoliday.holiday_date).all()
    return [serialize_holiday(holiday) for holiday in holidays]


def serialize_holiday(holiday: SDSLAHoliday) -> dict:
    return {
        "id": holiday.id,
        "name": holiday.name,
        "holiday_date": holiday.holiday_date,
        "country": holiday.country,
        "sla_policy_id": holiday.sla_policy_id,
    }


def build_holiday(payload: HolidayIn) -> SDSLAHoliday:
    return SDSLAHoliday(**payload.model_dump())


def create_holiday_record(db, payload: HolidayIn) -> SDSLAHoliday:
    h = build_holiday(payload)
    db.add(h)
    return h


def get_holiday_by_id(db: Session, holiday_id: str) -> SDSLAHoliday:
    holiday = db.query(SDSLAHoliday).filter(SDSLAHoliday.id == holiday_id).first()
    if not holiday:
        raise HTTPException(404)
    return holiday


def get_holiday_for_delete(db: Session, holiday_id: str) -> SDSLAHoliday:
    return get_holiday_by_id(db, holiday_id)


def delete_holiday(db: Session, holiday_id: str) -> None:
    h = get_holiday_by_id(db, holiday_id)
    db.delete(h)
