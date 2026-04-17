from datetime import date
from typing import Optional

from pydantic import BaseModel


class DeliverableIn(BaseModel):
    name: str
    description: Optional[str] = None
    format: Optional[str] = None
    planned_date: Optional[date] = None
    owner_id: Optional[str] = None
    client_contact: Optional[str] = None
    acceptance_criteria: Optional[str] = None
    milestone_id: Optional[str] = None
    phase_id: Optional[str] = None
    sort_order: int = 0


class DeliverableUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    format: Optional[str] = None
    status: Optional[str] = None
    planned_date: Optional[date] = None
    delivered_date: Optional[date] = None
    accepted_date: Optional[date] = None
    owner_id: Optional[str] = None
    client_contact: Optional[str] = None
    acceptance_criteria: Optional[str] = None
    rejection_reason: Optional[str] = None
    document_url: Optional[str] = None
    sort_order: Optional[int] = None
