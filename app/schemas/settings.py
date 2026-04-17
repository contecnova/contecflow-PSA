from datetime import date as date_type
from typing import Optional

from pydantic import BaseModel


class SettingOut(BaseModel):
    key: str
    value: Optional[str]
    description: Optional[str]
    model_config = {"from_attributes": True}


class SettingUpdate(BaseModel):
    value: str


class ProjectTypeIn(BaseModel):
    value: str
    label: str
    color: str = "#7a8aaa"
    sort_order: int = 0


class ProjectTypeOut(ProjectTypeIn):
    id: str
    is_active: bool
    model_config = {"from_attributes": True}


class ProjectStatusIn(BaseModel):
    value: str
    label: str
    color: str = "#7a8aaa"
    is_default: bool = False
    sort_order: int = 0


class ProjectStatusOut(ProjectStatusIn):
    id: str
    is_active: bool
    model_config = {"from_attributes": True}


class TaskStatusIn(BaseModel):
    value: str
    label: str
    color: str = "#7a8aaa"
    is_default: bool = False
    sort_order: int = 0


class TaskStatusOut(TaskStatusIn):
    id: str
    is_active: bool
    model_config = {"from_attributes": True}


class DepartmentIn(BaseModel):
    name: str
    description: Optional[str] = None
    manager_id: Optional[str] = None


class DepartmentOut(DepartmentIn):
    id: str
    is_active: bool
    model_config = {"from_attributes": True}


class HolidayIn(BaseModel):
    name: str
    date: date_type
    type: str = "public"
    applies_to: Optional[str] = None


class HolidayOut(HolidayIn):
    id: str
    model_config = {"from_attributes": True}


class LogLevelPayload(BaseModel):
    level: str
    logger: Optional[str] = None
