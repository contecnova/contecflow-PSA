from datetime import date
from typing import Optional

from pydantic import BaseModel


class AbsenceIn(BaseModel):
    type: str
    start_date: date
    end_date: date
    reason: Optional[str] = None


class AbsenceReview(BaseModel):
    approved: bool
    rejection_reason: Optional[str] = None
