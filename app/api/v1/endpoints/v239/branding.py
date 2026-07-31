from __future__ import annotations

import json
from typing import Dict, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, field_validator
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, get_db, require_admin
from app.core.responses import APIResponse
from app.models.user import User
from app.core.abac_enforce import enforce_abac

router = APIRouter()


class BrandingUpdate(BaseModel):
    app_name: Optional[str] = None
    tagline: Optional[str] = None
    logo_url: Optional[str] = None
    favicon_url: Optional[str] = None
    primary_color: Optional[str] = None
    secondary_color: Optional[str] = None
    accent_color: Optional[str] = None
    background_color: Optional[str] = None
    text_color: Optional[str] = None
    custom_domain: Optional[str] = None
    support_email: Optional[str] = None
    privacy_url: Optional[str] = None
    terms_url: Optional[str] = None
    welcome_message: Optional[str] = None
    login_background_url: Optional[str] = None
    footer_text: Optional[str] = None
    help_url: Optional[str] = None
    hide_powered_by: Optional[bool] = None
    enable_portal: Optional[bool] = None
    enable_ai: Optional[bool] = None
    custom_css_vars: Optional[Dict[str, str]] = None

    @field_validator(
        "primary_color",
        "secondary_color",
        "accent_color",
        "background_color",
        "text_color",
        mode="before",
    )
    @classmethod
    def validate_color(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and not (v.startswith("#") and len(v) in (4, 7, 9)):
            raise ValueError("Color must be a valid hex value like #RRGGBB")
        return v

    @field_validator("custom_domain", mode="before")
    @classmethod
    def validate_domain(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            if "/" in v or " " in v:
                raise ValueError("custom_domain must be a bare hostname, e.g. pm.company.com")
        return v


def _branding_out(b) -> dict:
    return {
        "id": b.id,
        "organization_id": b.organization_id,
        "app_name": b.app_name,
        "tagline": b.tagline,
        "logo_url": b.logo_url,
        "favicon_url": b.favicon_url,
        "primary_color": b.primary_color,
        "secondary_color": b.secondary_color,
        "accent_color": b.accent_color,
        "background_color": b.background_color,
        "text_color": b.text_color,
        "custom_domain": b.custom_domain,
        "support_email": b.support_email,
        "privacy_url": b.privacy_url,
        "terms_url": b.terms_url,
        "welcome_message": b.welcome_message,
        "login_background_url": b.login_background_url,
        "footer_text": b.footer_text,
        "help_url": b.help_url,
        "hide_powered_by": b.hide_powered_by,
        "enable_portal": b.enable_portal,
        "enable_ai": b.enable_ai,
        "custom_css_vars": json.loads(b.custom_css_vars) if b.custom_css_vars else {},
        "updated_at": str(b.updated_at) if b.updated_at else None,
    }


@router.get("/orgs/{org_id}/branding", summary="Get tenant branding config")
def get_branding(
    org_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    from app.models.mfa import Organization
    from app.models.white_label import OrgBranding

    org = db.query(Organization).filter(Organization.id == org_id).first()
    if not org:
        raise HTTPException(404, "Organization not found")
    branding = db.query(OrgBranding).filter(OrgBranding.organization_id == org_id).first()
    if not branding:
        return APIResponse.ok(data={
            "organization_id": org_id,
            "app_name": "NexusPM",
            "primary_color": "#6366f1",
            "secondary_color": "#8b5cf6",
            "accent_color": "#06b6d4",
            "hide_powered_by": False,
            "enable_portal": True,
            "enable_ai": True,
            "custom_css_vars": {},
            "is_default": True,
        })
    return APIResponse.ok(data=_branding_out(branding))


@router.put("/orgs/{org_id}/branding", summary="Update tenant branding (admin)")
def update_branding(
    org_id: str,
    payload: BrandingUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    from app.models.mfa import Organization
    from app.models.white_label import OrgBranding

    org = db.query(Organization).filter(Organization.id == org_id).first()
    if not org:
        raise HTTPException(404, "Organization not found")

    branding = db.query(OrgBranding).filter(OrgBranding.organization_id == org_id).first()
    if not branding:
        branding = OrgBranding(organization_id=org_id, created_by=current_user.id)
        db.add(branding)

    for field, val in payload.dict(exclude_none=True).items():
        if field == "custom_css_vars":
            safe_vars = {
                k: v
                for k, v in val.items()
                if k.startswith("--") and len(k) < 80 and len(str(v)) < 100
            }
            setattr(branding, field, json.dumps(safe_vars))
        else:
            setattr(branding, field, val)

    db.commit()
    db.refresh(branding)
    return APIResponse.ok(data=_branding_out(branding))


@router.delete("/orgs/{org_id}/branding", summary="Reset branding to defaults (admin)", status_code=204)
def reset_branding(
    org_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    from app.models.white_label import OrgBranding

    enforce_abac(db, current_user, "org_branding", org_id, action="delete")
    branding = db.query(OrgBranding).filter(OrgBranding.organization_id == org_id).first()
    if branding:
        db.delete(branding)
        db.commit()
    return None
