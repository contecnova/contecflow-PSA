from datetime import date
from typing import Optional

from pydantic import BaseModel


class ReviewCycleIn(BaseModel):
    name: str
    description: Optional[str] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    include_self: bool = True
    include_peers: bool = True
    include_manager: bool = True


class PerformanceReviewIn(BaseModel):
    score_quality: Optional[float] = None
    score_delivery: Optional[float] = None
    score_teamwork: Optional[float] = None
    score_leadership: Optional[float] = None
    score_innovation: Optional[float] = None
    score_overall: Optional[float] = None
    strengths: Optional[str] = None
    improvements: Optional[str] = None
    goals_next: Optional[str] = None
