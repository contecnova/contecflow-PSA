from datetime import date, datetime
from typing import List, Optional

from pydantic import BaseModel

from app.core.config import settings


class DependencyCreate(BaseModel):
    predecessor_id: str
    successor_id: str
    dependency_type: str = "FS"
    lag_days: int = 0


class BookingCreate(BaseModel):
    user_id: str
    project_id: Optional[str] = None
    task_id: Optional[str] = None
    booking_type: str = "hard"
    start_date: date
    end_date: date
    hours_per_day: float = settings.DEFAULT_WORKING_HOURS_PER_DAY
    note: Optional[str] = None


class BookingUpdate(BaseModel):
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    hours_per_day: Optional[float] = None
    project_id: Optional[str] = None
    task_id: Optional[str] = None
    booking_type: Optional[str] = None
    note: Optional[str] = None


class SLAScheduleCreate(BaseModel):
    name: str
    timezone: str = settings.DEFAULT_TIMEZONE
    is_default: bool = False
    work_days: List[int] = [1, 2, 3, 4, 5]
    work_start: Optional[str] = "09:00"
    work_end: Optional[str] = "17:00"


class ApiKeyCreate(BaseModel):
    name: str
    scopes: List[str] = ["read"]
    rate_limit_per_hour: int = 1000
    rate_limit_per_day: int = 10000
    expires_at: Optional[datetime] = None


class RecurringCreate(BaseModel):
    name: str
    project_id: Optional[str] = None
    contract_id: Optional[str] = None
    frequency: str = "monthly"
    next_date: date
    end_date: Optional[date] = None
    client_name: Optional[str] = None
    client_email: Optional[str] = None
    client_vat: Optional[str] = None
    amount: float
    tax_rate: float = settings.DEFAULT_TAX_RATE
    currency: str = settings.DEFAULT_CURRENCY
    description: Optional[str] = None
    payment_terms_days: int = 30
