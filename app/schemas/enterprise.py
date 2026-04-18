from typing import Optional, List
from datetime import date, datetime
from pydantic import BaseModel, field_validator
from app.core.config import settings

class PermissionCreate(BaseModel):
    user_id: str
    level: str = "member"
    can_see_financials: bool = False
    can_see_rates: bool = False
    can_export: bool = True
    expires_at: Optional[datetime] = None
    note: Optional[str] = None

class PermissionUpdate(BaseModel):
    level: Optional[str] = None
    can_see_financials: Optional[bool] = None
    can_see_rates: Optional[bool] = None
    can_export: Optional[bool] = None
    expires_at: Optional[datetime] = None
    note: Optional[str] = None

class WebhookCreate(BaseModel):
    name: str
    url: str
    secret: Optional[str] = None
    events: List[str]
    project_id: Optional[str] = None

class WebhookUpdate(BaseModel):
    name: Optional[str] = None
    url: Optional[str] = None
    secret: Optional[str] = None
    events: Optional[List[str]] = None
    is_active: Optional[bool] = None

class SSOCreate(BaseModel):
    provider: str
    organization_id: Optional[str] = None
    saml_entity_id: Optional[str] = None
    saml_sso_url: Optional[str] = None
    saml_slo_url: Optional[str] = None
    saml_certificate: Optional[str] = None
    saml_attribute_email: str = "email"
    saml_attribute_name: str = "displayName"
    saml_attribute_role: Optional[str] = None
    oidc_client_id: Optional[str] = None
    oidc_client_secret: Optional[str] = None
    oidc_discovery_url: Optional[str] = None
    oidc_scopes: str = "openid email profile"
    role_mapping: Optional[dict] = None
    auto_create_users: bool = True
    default_role: str = "employee"
    allowed_domains: Optional[str] = None

    @field_validator("oidc_discovery_url", "saml_sso_url", "saml_slo_url", mode="before")
    @classmethod
    def _require_https(cls, v: Optional[str]) -> Optional[str]:
        if v and not v.startswith("https://"):
            raise ValueError("Solo se permiten URLs HTTPS para configuraciones SSO/OIDC")
        return v

class SSOUpdate(SSOCreate):
    is_active: Optional[bool] = None
    is_default: Optional[bool] = None

class SubCreate(BaseModel):
    name: str
    company: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    country: Optional[str] = None
    vat_number: Optional[str] = None
    currency: str = settings.DEFAULT_CURRENCY
    notes: Optional[str] = None

class SubUpdate(SubCreate):
    is_active: Optional[bool] = None
    name: Optional[str] = None

class RateCreate(BaseModel):
    description: str
    cost_rate: float
    sell_rate: Optional[float] = None
    currency: str = settings.DEFAULT_CURRENCY
    valid_from: Optional[date] = None
    valid_until: Optional[date] = None

class AssignmentCreate(BaseModel):
    project_id: str
    worker_id: Optional[str] = None
    rate_id: Optional[str] = None
    po_number: Optional[str] = None
    po_amount: Optional[float] = None
    hours_contracted: Optional[float] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    notes: Optional[str] = None

class WorkerCreate(BaseModel):
    name: str
    role: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    cost_rate: Optional[float] = None
    sell_rate: Optional[float] = None
    currency: str = settings.DEFAULT_CURRENCY
    available_from: Optional[date] = None
    available_until: Optional[date] = None
    weekly_capacity_hours: Optional[float] = None
    notes: Optional[str] = None

class WorkerUpdate(BaseModel):
    name: Optional[str] = None
    role: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    cost_rate: Optional[float] = None
    sell_rate: Optional[float] = None
    currency: Optional[str] = None
    available_from: Optional[date] = None
    available_until: Optional[date] = None
    weekly_capacity_hours: Optional[float] = None
    is_active: Optional[bool] = None
    notes: Optional[str] = None

class WorkerSkillCreate(BaseModel):
    skill_id: str
    level: str = "intermediate"
    years_experience: Optional[float] = None
    certified: bool = False
    cert_name: Optional[str] = None
    notes: Optional[str] = None

class ForecastUpdate(BaseModel):
    revenue_planned: Optional[float] = None
    revenue_actual: Optional[float] = None
    revenue_forecast: Optional[float] = None
    cost_planned: Optional[float] = None
    cost_actual: Optional[float] = None
    hours_planned: Optional[float] = None
    hours_actual: Optional[float] = None
    notes: Optional[str] = None
