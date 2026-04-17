from datetime import date
from typing import Optional

from pydantic import BaseModel


class ContractIn(BaseModel):
    name: str
    project_id: str
    client_name: str
    contract_type: str
    total_amount: Optional[float] = None
    hourly_rate: Optional[float] = None
    hours_bag: Optional[float] = None
    monthly_retainer: Optional[float] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    signed_date: Optional[date] = None
    client_contact: Optional[str] = None
    payment_terms: Optional[str] = None
    notes: Optional[str] = None


class ContractUpdate(BaseModel):
    name: Optional[str] = None
    status: Optional[str] = None
    total_amount: Optional[float] = None
    hourly_rate: Optional[float] = None
    hours_bag: Optional[float] = None
    monthly_retainer: Optional[float] = None
    end_date: Optional[date] = None
    signed_date: Optional[date] = None
    payment_terms: Optional[str] = None
    notes: Optional[str] = None


class WorkOrderIn(BaseModel):
    name: str
    amount: Optional[float] = None
    hours: Optional[float] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    description: Optional[str] = None
