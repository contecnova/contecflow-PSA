from datetime import date
from typing import List, Optional

from pydantic import BaseModel


class SprintCreate(BaseModel):
    name: str
    goal: Optional[str] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None


class SprintUpdate(BaseModel):
    name: Optional[str] = None
    goal: Optional[str] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    status: Optional[str] = None
    went_well: Optional[str] = None
    to_improve: Optional[str] = None
    action_items: Optional[str] = None


class AddTasksToSprint(BaseModel):
    task_ids: List[str]


class ReorderBacklog(BaseModel):
    task_ids: List[str]
