from datetime import date
from typing import Optional

from pydantic import BaseModel

from app.core.config import settings


class ExpenseIn(BaseModel):
    user_id: Optional[str] = None
    project_id: Optional[str] = None
    category: Optional[str] = None
    amount: Optional[float] = None
    currency: Optional[str] = None
    expense_date: Optional[date] = None
    description: Optional[str] = None
    notes: Optional[str] = None
    receipt_url: Optional[str] = None
    status: Optional[str] = None
    is_billable: Optional[bool] = None


class ExpenseCreate(BaseModel):
    project_id: Optional[str] = None
    contract_id: Optional[str] = None
    category: str
    description: str
    amount: float
    currency: str = settings.DEFAULT_CURRENCY
    expense_date: date
    is_billable: bool = True
    receipt_name: Optional[str] = None
    notes: Optional[str] = None


class ExpenseUpdate(BaseModel):
    category: Optional[str] = None
    description: Optional[str] = None
    amount: Optional[float] = None
    expense_date: Optional[date] = None
    is_billable: Optional[bool] = None
    notes: Optional[str] = None


class ExpenseReviewPayload(BaseModel):
    approved: bool
    rejection_reason: Optional[str] = None
