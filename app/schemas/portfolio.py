from datetime import date
from typing import Optional

from pydantic import BaseModel


class PortfolioIn(BaseModel):
    name: str
    description: Optional[str] = None
    status: Optional[str] = "active"
    budget_total: Optional[float] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None


class PortfolioProjectIn(BaseModel):
    project_id: str
    rag_override: Optional[str] = None
    display_order: Optional[float] = 0.0
