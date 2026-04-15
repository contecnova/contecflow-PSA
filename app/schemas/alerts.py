from datetime import datetime
from typing import Optional

from pydantic import BaseModel

from app.schemas.projects import ProjectSummary
from app.schemas.users import UserPublic


class AlertOut(BaseModel):
    id: str
    alert_type: str
    severity: str
    title: str
    description: Optional[str] = None
    value: Optional[float] = None
    threshold: Optional[float] = None
    user: Optional[UserPublic] = None
    project: Optional[ProjectSummary] = None
    is_read: bool
    is_resolved: bool
    created_at: datetime

    class Config:
        from_attributes = True
