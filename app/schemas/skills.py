from datetime import date
from typing import List, Optional

from pydantic import BaseModel


class SkillIn(BaseModel):
    name: str
    category: str
    description: Optional[str] = None


class UserSkillIn(BaseModel):
    skill_id: str
    level: str
    years_experience: Optional[float] = None
    certified: bool = False
    cert_name: Optional[str] = None
    cert_expiry: Optional[date] = None
    notes: Optional[str] = None


class StaffingQuery(BaseModel):
    skill_ids: List[str]
    min_level: str = "basic"
    available_from: Optional[date] = None
    available_weeks: int = 1
