from datetime import date
from typing import Optional

from pydantic import BaseModel


class CourseIn(BaseModel):
    title: str
    description: Optional[str] = None
    provider: Optional[str] = None
    category: Optional[str] = None
    duration_h: Optional[float] = None
    url: Optional[str] = None
    cost: Optional[float] = None


class EnrollmentIn(BaseModel):
    course_id: str
    user_id: str
    status: str = "planned"
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    score: Optional[float] = None
    notes: Optional[str] = None


class CertificationIn(BaseModel):
    user_id: str
    name: str
    issuer: Optional[str] = None
    cert_id: Optional[str] = None
    obtained_at: Optional[date] = None
    expires_at: Optional[date] = None
    url: Optional[str] = None
    notes: Optional[str] = None
