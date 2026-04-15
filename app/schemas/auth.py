from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field

from app.schemas.users import UserPublic


class LoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: Optional[str] = None
    refresh_token: Optional[str] = None
    token_type: str = "bearer"
    user: UserPublic
    mfa_required: bool = False
    mfa_challenge_token: Optional[str] = None
    mfa_methods: Optional[list[str]] = None


class RefreshRequest(BaseModel):
    refresh_token: str


class PasswordForgotRequest(BaseModel):
    email_or_username: str


class PasswordResetRequest(BaseModel):
    token: str
    new_password: str


class ActiveSessionOut(BaseModel):
    id: str
    ip_address: Optional[str] = None
    ip_asn: Optional[str] = None
    ip_org: Optional[str] = None
    country_code: Optional[str] = None
    region: Optional[str] = None
    city: Optional[str] = None
    user_agent: Optional[str] = None
    device_name: Optional[str] = None
    risk_score: int = 0
    risk_level: str = "low"
    risk_reasons: List[str] = Field(default_factory=list)
    auth_method: Optional[str] = None
    last_seen_at: Optional[datetime] = None
    expires_at: datetime
    created_at: Optional[datetime] = None
    is_current: bool = False
