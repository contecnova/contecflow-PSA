from datetime import datetime
from typing import Optional

from pydantic import BaseModel, EmailStr

from app.schemas.common_enums import UserRole, UserStatus


class UserBase(BaseModel):
    username: str
    email: EmailStr
    full_name: str
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    department: Optional[str] = None
    job_title: Optional[str] = None
    role: UserRole = UserRole.employee
    status: UserStatus = UserStatus.active
    weekly_capacity_hours: float = 40.0


class UserCreate(UserBase):
    password: Optional[str] = None  # Optional for LDAP users


class UserUpdate(BaseModel):
    full_name: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    department: Optional[str] = None
    job_title: Optional[str] = None
    role: Optional[UserRole] = None
    status: Optional[UserStatus] = None
    weekly_capacity_hours: Optional[float] = None
    hourly_rate: Optional[float] = None  # Only admin can set this
    phone: Optional[str] = None
    avatar_url: Optional[str] = None
    manager_id: Optional[str] = None
    timezone: Optional[str] = None


class UserSelfUpdate(BaseModel):
    """Campos que el propio usuario puede editar (sin privilegios)."""

    first_name: Optional[str] = None
    last_name: Optional[str] = None
    full_name: Optional[str] = None
    phone: Optional[str] = None
    job_title: Optional[str] = None
    avatar_url: Optional[str] = None
    timezone: Optional[str] = None


class UserPublic(UserBase):
    id: str
    is_active: bool = True
    avatar_url: Optional[str] = None
    last_login: Optional[datetime] = None
    created_at: datetime
    manager_id: Optional[str] = None
    manager_name: Optional[str] = None
    phone: Optional[str] = None

    class Config:
        from_attributes = True


class UserWithRate(UserPublic):
    """Extended view for admin/hr — includes confidential rate."""

    hourly_rate: Optional[float] = None
    ldap_dn: Optional[str] = None


class UserLoad(BaseModel):
    user: UserPublic
    current_load_pct: float
    hours_this_week: float
    hours_this_month: float
    active_tasks: int
    active_projects: int
