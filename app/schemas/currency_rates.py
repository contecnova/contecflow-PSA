from datetime import date
from typing import Optional

from pydantic import BaseModel


class ExchangeRateCreate(BaseModel):
    from_currency: str
    to_currency: str
    rate: float
    effective_date: Optional[date] = None
    source: Optional[str] = "manual"
