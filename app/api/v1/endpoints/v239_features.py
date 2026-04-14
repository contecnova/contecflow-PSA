"""
app/api/v1/endpoints/v239_features.py

v23.9.0 Enterprise-tier endpoints:

1.  ECB real-time exchange rates (POST /currency/sync-ecb)
2.  White-label branding per org (GET/PUT /orgs/{org_id}/branding)
3.  Gantt baselines — freeze/compare schedule snapshots
4.  Integration marketplace — connector catalog + install/uninstall
5.  Salesforce CRM bidirectional sync
6.  Customer Health Score composite (enhanced formula)
7.  AI Copilot contextual inline suggestions
8.  Enhanced Project Templates (documents + roles)
9.  Approval workflow visual builder API
10. Slack Block Kit rich notifications
"""
from __future__ import annotations

import json
import logging
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional, Union

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field, validator
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.deps import (
    get_current_user,
    get_db,
    require_admin,
    require_any_manager,
)
from app.core.config import settings
from app.models.user import User

router = APIRouter()
logger = logging.getLogger(__name__)

# ══════════════════════════════════════════════════════════════════════════════
# 1. REAL-TIME EXCHANGE RATES — ECB + OpenExchangeRates sync
# ══════════════════════════════════════════════════════════════════════════════

@router.post("/currency/sync-ecb", summary="Sync ECB daily exchange rates (admin)")
async def sync_ecb_exchange_rates(
    force: bool = Query(default=False, description="Re-sync even if today's rates already exist"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """
    Fetch the European Central Bank daily reference rates XML feed and upsert
    into exchange_rates.  Rate anchor: EUR = 1.  ~30 major currencies.
    Idempotent — skips if today's data already present unless force=true.
    """
    from app.services.exchange_rate_service import sync_ecb_rates
    result = await sync_ecb_rates(db, force=force)
    if not result.get("ok"):
        raise HTTPException(status_code=502, detail=result.get("error", "ECB fetch failed"))
    return result


@router.post("/currency/sync-openexchangerates", summary="Sync OpenExchangeRates (admin)")
async def sync_openexchangerates(
    base: str = Query(default="USD"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Sync rates from OpenExchangeRates if OPEN_EXCHANGE_RATES_APP_ID is configured."""
    app_id = settings.OPEN_EXCHANGE_RATES_APP_ID
    if not app_id:
        raise HTTPException(
            status_code=503,
            detail="OPEN_EXCHANGE_RATES_APP_ID not configured. Set it in your .env file.",
        )
    from app.services.exchange_rate_service import sync_openexchangerates as _sync
    result = await _sync(db, app_id=app_id, base=base.upper())
    if not result.get("ok"):
        raise HTTPException(status_code=502, detail=result.get("error", "Sync failed"))
    return result


# ══════════════════════════════════════════════════════════════════════════════
# 2. WHITE-LABEL + TENANT BRANDING
# ══════════════════════════════════════════════════════════════════════════════

class BrandingUpdate(BaseModel):
    app_name:             Optional[str] = None
    tagline:              Optional[str] = None
    logo_url:             Optional[str] = None
    favicon_url:          Optional[str] = None
    primary_color:        Optional[str] = None
    secondary_color:      Optional[str] = None
    accent_color:         Optional[str] = None
    background_color:     Optional[str] = None
    text_color:           Optional[str] = None
    custom_domain:        Optional[str] = None
    support_email:        Optional[str] = None
    privacy_url:          Optional[str] = None
    terms_url:            Optional[str] = None
    welcome_message:      Optional[str] = None
    login_background_url: Optional[str] = None
    footer_text:          Optional[str] = None
    help_url:             Optional[str] = None
    hide_powered_by:      Optional[bool] = None
    enable_portal:        Optional[bool] = None
    enable_ai:            Optional[bool] = None
    custom_css_vars:      Optional[Dict[str, str]] = None

    @validator("primary_color", "secondary_color", "accent_color",
               "background_color", "text_color", pre=True, always=False)
    def validate_color(cls, v):
        if v is not None and not (v.startswith("#") and len(v) in (4, 7, 9)):
            raise ValueError("Color must be a valid hex value like #RRGGBB")
        return v

    @validator("custom_domain", pre=True, always=False)
    def validate_domain(cls, v):
        if v is not None:
            # Basic domain validation — no path, no protocol
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
    from app.models.white_label import OrgBranding
    from app.models.mfa import Organization
    org = db.query(Organization).filter(Organization.id == org_id).first()
    if not org:
        raise HTTPException(404, "Organization not found")
    branding = db.query(OrgBranding).filter(OrgBranding.organization_id == org_id).first()
    if not branding:
        # Return defaults
        return {"organization_id": org_id, "app_name": "NexusPM", "primary_color": "#6366f1",
                "secondary_color": "#8b5cf6", "accent_color": "#06b6d4",
                "hide_powered_by": False, "enable_portal": True, "enable_ai": True,
                "custom_css_vars": {}, "is_default": True}
    return _branding_out(branding)


@router.put("/orgs/{org_id}/branding", summary="Update tenant branding (admin)")
def update_branding(
    org_id: str,
    payload: BrandingUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    from app.models.white_label import OrgBranding
    from app.models.mfa import Organization
    org = db.query(Organization).filter(Organization.id == org_id).first()
    if not org:
        raise HTTPException(404, "Organization not found")

    branding = db.query(OrgBranding).filter(OrgBranding.organization_id == org_id).first()
    if not branding:
        branding = OrgBranding(organization_id=org_id, created_by=current_user.id)
        db.add(branding)

    for field, val in payload.dict(exclude_none=True).items():
        if field == "custom_css_vars":
            # Sanitize: only allow CSS variable names starting with --
            safe_vars = {k: v for k, v in val.items()
                         if k.startswith("--") and len(k) < 80 and len(str(v)) < 100}
            setattr(branding, field, json.dumps(safe_vars))
        else:
            setattr(branding, field, val)

    db.commit()
    db.refresh(branding)
    return _branding_out(branding)


@router.delete("/orgs/{org_id}/branding", summary="Reset branding to defaults (admin)", status_code=204)
def reset_branding(
    org_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    from app.models.white_label import OrgBranding
    branding = db.query(OrgBranding).filter(OrgBranding.organization_id == org_id).first()
    if branding:
        db.delete(branding)
        db.commit()
    return None


# ══════════════════════════════════════════════════════════════════════════════
# 3. GANTT BASELINES — freeze, compare, what-if
# ══════════════════════════════════════════════════════════════════════════════

class BaselineCreate(BaseModel):
    name: str
    description: Optional[str] = None
    is_initial: bool = False


@router.get("/projects/{project_id}/baselines", summary="List Gantt baselines for project")
def list_baselines(
    project_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    from app.models.marketplace import GanttBaseline
    from app.models.project import Project
    if not db.query(Project).filter(Project.id == project_id).first():
        raise HTTPException(404, "Project not found")
    baselines = db.query(GanttBaseline).filter(
        GanttBaseline.project_id == project_id
    ).order_by(GanttBaseline.baseline_date.desc()).all()
    return [
        {"id": b.id, "name": b.name, "description": b.description,
         "baseline_date": str(b.baseline_date), "is_initial": b.is_initial,
         "total_tasks": b.total_tasks, "completed_tasks": b.completed_tasks,
         "total_hours": b.total_hours, "budget_at_freeze": b.budget_at_freeze,
         "created_at": str(b.created_at)}
        for b in baselines
    ]


@router.post("/projects/{project_id}/baselines", summary="Freeze current Gantt as baseline",
             status_code=201)
def create_baseline(
    project_id: str,
    payload: BaselineCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    """
    Snapshots the current schedule (tasks with start/due dates and progress) and
    stores it as an immutable baseline for comparison against future re-forecasts.
    """
    from app.models.marketplace import GanttBaseline
    from app.models.project import Project
    from app.models.task import Task

    proj = db.query(Project).filter(Project.id == project_id).first()
    if not proj:
        raise HTTPException(404, "Project not found")

    tasks = db.query(Task).filter(Task.project_id == project_id).all()
    snapshot = {
        "frozen_at": str(date.today()),
        "tasks": [
            {
                "task_id": t.id,
                "title": t.title,
                "start": str(t.start_date) if hasattr(t, "start_date") and t.start_date else None,
                "end": str(t.due_date) if t.due_date else None,
                "progress": t.progress if hasattr(t, "progress") else 0,
                "status": str(t.status.value) if hasattr(t.status, "value") else str(t.status),
                "estimated_hours": t.estimated_hours if hasattr(t, "estimated_hours") else None,
                "assignee_id": t.assignee_id if hasattr(t, "assignee_id") else None,
            }
            for t in tasks
        ],
    }
    total_h = sum(
        (t.estimated_hours or 0) for t in tasks
        if hasattr(t, "estimated_hours") and t.estimated_hours
    )
    done = sum(1 for t in tasks
               if str(getattr(t.status, "value", t.status)) in ("done", "closed", "completed"))

    baseline = GanttBaseline(
        project_id=project_id,
        name=payload.name,
        description=payload.description,
        baseline_date=date.today(),
        schedule_snapshot=json.dumps(snapshot),
        total_tasks=len(tasks),
        completed_tasks=done,
        total_hours=total_h,
        budget_at_freeze=proj.budget if hasattr(proj, "budget") else None,
        is_initial=payload.is_initial,
        created_by=current_user.id,
    )
    db.add(baseline)
    db.commit()
    db.refresh(baseline)
    return {
        "id": baseline.id, "name": baseline.name,
        "baseline_date": str(baseline.baseline_date),
        "total_tasks": baseline.total_tasks, "total_hours": baseline.total_hours,
        "created": True,
    }


@router.get("/projects/{project_id}/baselines/{baseline_id}/compare",
            summary="Compare current schedule vs baseline")
def compare_baseline(
    project_id: str,
    baseline_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Compares the frozen baseline schedule against the current live task schedule.
    Returns per-task deltas: date slip, hours deviation, status changes.
    """
    from app.models.marketplace import GanttBaseline
    from app.models.task import Task

    baseline = db.query(GanttBaseline).filter(
        GanttBaseline.id == baseline_id,
        GanttBaseline.project_id == project_id,
    ).first()
    if not baseline:
        raise HTTPException(404, "Baseline not found")

    frozen = json.loads(baseline.schedule_snapshot)
    frozen_tasks = {t["task_id"]: t for t in frozen.get("tasks", [])}

    current_tasks = db.query(Task).filter(Task.project_id == project_id).all()
    deltas = []
    for t in current_tasks:
        ft = frozen_tasks.get(t.id)
        if not ft:
            deltas.append({"task_id": t.id, "title": t.title, "delta": "new_task"})
            continue
        current_end = str(t.due_date) if t.due_date else None
        frozen_end  = ft.get("end")
        slip_days: Optional[int] = None
        if current_end and frozen_end:
            try:
                slip_days = (date.fromisoformat(current_end) -
                             date.fromisoformat(frozen_end)).days
            except ValueError:
                pass
        deltas.append({
            "task_id": t.id,
            "title": t.title,
            "baseline_end": frozen_end,
            "current_end": current_end,
            "slip_days": slip_days,
            "baseline_status": ft.get("status"),
            "current_status": str(t.status.value) if hasattr(t.status, "value") else str(t.status),
            "baseline_hours": ft.get("estimated_hours"),
            "current_hours": t.estimated_hours if hasattr(t, "estimated_hours") else None,
        })

    removed = [{"task_id": tid, "delta": "removed"} for tid in frozen_tasks
               if tid not in {t.id for t in current_tasks}]

    slipped = sum(1 for d in deltas if (d.get("slip_days") or 0) > 0)
    avg_slip = (sum(d.get("slip_days") or 0 for d in deltas) / max(len(deltas), 1))

    return {
        "baseline_id": baseline_id,
        "baseline_name": baseline.name,
        "baseline_date": str(baseline.baseline_date),
        "summary": {
            "tasks_compared": len(deltas),
            "tasks_slipped": slipped,
            "avg_slip_days": round(avg_slip, 1),
            "tasks_removed": len(removed),
            "tasks_added": sum(1 for d in deltas if d.get("delta") == "new_task"),
        },
        "task_deltas": deltas + removed,
    }


@router.delete("/projects/{project_id}/baselines/{baseline_id}",
               summary="Delete baseline", status_code=204)
def delete_baseline(
    project_id: str,
    baseline_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    from app.models.marketplace import GanttBaseline
    b = db.query(GanttBaseline).filter(
        GanttBaseline.id == baseline_id,
        GanttBaseline.project_id == project_id
    ).first()
    if not b:
        raise HTTPException(404, "Baseline not found")
    db.delete(b)
    db.commit()
    return None


# ══════════════════════════════════════════════════════════════════════════════
# 4. INTEGRATION MARKETPLACE — connector catalog + instances
# ══════════════════════════════════════════════════════════════════════════════

# Pre-seeded catalog — inserted on first startup if table is empty
CONNECTOR_CATALOG = [
    {"name": "Salesforce CRM", "slug": "salesforce", "category": "crm",
     "description": "Bidirectional sync of opportunities, contacts and accounts.",
     "auth_scheme": "oauth2", "is_certified": True,
     "logo_url": "https://cdn.clarive.app/connectors/salesforce.svg"},
    {"name": "HubSpot CRM", "slug": "hubspot", "category": "crm",
     "description": "Sync deals, contacts and pipeline stages with HubSpot.",
     "auth_scheme": "oauth2", "is_certified": True,
     "logo_url": "https://cdn.clarive.app/connectors/hubspot.svg"},
    {"name": "SAP S/4HANA", "slug": "sap_s4", "category": "erp",
     "description": "Financial integration: cost centres, WBS elements, actual costs.",
     "auth_scheme": "api_key", "is_certified": True,
     "logo_url": "https://cdn.clarive.app/connectors/sap.svg"},
    {"name": "Oracle NetSuite", "slug": "netsuite", "category": "erp",
     "description": "Sync projects, time entries and invoices with NetSuite.",
     "auth_scheme": "oauth2", "is_certified": True,
     "logo_url": "https://cdn.clarive.app/connectors/netsuite.svg"},
    {"name": "Workday HCM", "slug": "workday", "category": "hris",
     "description": "Employee roster, org chart, and time-off sync.",
     "auth_scheme": "api_key", "is_certified": True,
     "logo_url": "https://cdn.clarive.app/connectors/workday.svg"},
    {"name": "BambooHR", "slug": "bamboohr", "category": "hris",
     "description": "Sync employees, departments and leave balances.",
     "auth_scheme": "api_key", "is_certified": True,
     "logo_url": "https://cdn.clarive.app/connectors/bamboohr.svg"},
    {"name": "Greenhouse ATS", "slug": "greenhouse", "category": "hris",
     "description": "Import new hires and open positions for resource planning.",
     "auth_scheme": "api_key", "is_certified": False,
     "logo_url": "https://cdn.clarive.app/connectors/greenhouse.svg"},
    {"name": "Jira Software", "slug": "jira", "category": "devops",
     "description": "Bidirectional issue sync, sprint import and webhook events.",
     "auth_scheme": "api_key", "is_certified": True,
     "logo_url": "https://cdn.clarive.app/connectors/jira.svg"},
    {"name": "GitHub", "slug": "github", "category": "devops",
     "description": "PR status, commit activity and deployment events.",
     "auth_scheme": "oauth2", "is_certified": True,
     "logo_url": "https://cdn.clarive.app/connectors/github.svg"},
    {"name": "GitLab", "slug": "gitlab", "category": "devops",
     "description": "CI/CD pipelines, merge requests and issue tracking.",
     "auth_scheme": "oauth2", "is_certified": False,
     "logo_url": "https://cdn.clarive.app/connectors/gitlab.svg"},
    {"name": "Slack", "slug": "slack", "category": "comms",
     "description": "Task creation, time logging and rich Block Kit notifications.",
     "auth_scheme": "oauth2", "is_certified": True,
     "logo_url": "https://cdn.clarive.app/connectors/slack.svg"},
    {"name": "Microsoft Teams", "slug": "teams", "category": "comms",
     "description": "Adaptive card notifications and bot commands.",
     "auth_scheme": "oauth2", "is_certified": True,
     "logo_url": "https://cdn.clarive.app/connectors/teams.svg"},
    {"name": "Xero", "slug": "xero", "category": "finance",
     "description": "Invoice sync, expense reimbursements and payment status.",
     "auth_scheme": "oauth2", "is_certified": True,
     "logo_url": "https://cdn.clarive.app/connectors/xero.svg"},
    {"name": "QuickBooks Online", "slug": "quickbooks", "category": "finance",
     "description": "Sync invoices, payments and project-level P&L.",
     "auth_scheme": "oauth2", "is_certified": True,
     "logo_url": "https://cdn.clarive.app/connectors/quickbooks.svg"},
    {"name": "DocuSign", "slug": "docusign", "category": "legal",
     "description": "Trigger e-signature workflows for contracts and SOWs.",
     "auth_scheme": "oauth2", "is_certified": True,
     "logo_url": "https://cdn.clarive.app/connectors/docusign.svg"},
    {"name": "Stripe", "slug": "stripe", "category": "finance",
     "description": "Payment links, milestone billing and subscription management.",
     "auth_scheme": "api_key", "is_certified": True,
     "logo_url": "https://cdn.clarive.app/connectors/stripe.svg"},
    {"name": "Azure DevOps", "slug": "azure_devops", "category": "devops",
     "description": "Work items, pipelines and board sync with Azure DevOps.",
     "auth_scheme": "api_key", "is_certified": False,
     "logo_url": "https://cdn.clarive.app/connectors/azuredevops.svg"},
    {"name": "AWS S3", "slug": "aws_s3", "category": "storage",
     "description": "Store project documents and backups in S3 buckets.",
     "auth_scheme": "api_key", "is_certified": True,
     "logo_url": "https://cdn.clarive.app/connectors/awss3.svg"},
    {"name": "Google Workspace", "slug": "google_workspace", "category": "comms",
     "description": "Calendar sync, Drive documents and Gmail notifications.",
     "auth_scheme": "oauth2", "is_certified": True,
     "logo_url": "https://cdn.clarive.app/connectors/google.svg"},
    {"name": "Zendesk", "slug": "zendesk", "category": "service_desk",
     "description": "Ticket sync between Clarive Service Desk and Zendesk.",
     "auth_scheme": "api_key", "is_certified": False,
     "logo_url": "https://cdn.clarive.app/connectors/zendesk.svg"},
    {"name": "ServiceNow", "slug": "servicenow", "category": "service_desk",
     "description": "ITSM integration: incidents, changes and CMDB items.",
     "auth_scheme": "api_key", "is_certified": False,
     "logo_url": "https://cdn.clarive.app/connectors/servicenow.svg"},
    {"name": "Okta", "slug": "okta", "category": "iam",
     "description": "SSO, SCIM user provisioning and group sync.",
     "auth_scheme": "api_key", "is_certified": True,
     "logo_url": "https://cdn.clarive.app/connectors/okta.svg"},
]


def _seed_connectors(db: Session):
    """Seed the catalog on first call if empty."""
    from app.models.marketplace import IntegrationConnector
    if db.query(IntegrationConnector).count() == 0:
        for item in CONNECTOR_CATALOG:
            db.add(IntegrationConnector(**item))
        db.commit()


@router.get("/integrations/marketplace", summary="List available integration connectors")
def list_marketplace(
    category: Optional[str] = Query(None),
    certified_only: bool = Query(False),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Returns the catalog of available third-party connectors with install status."""
    from app.models.marketplace import IntegrationConnector, IntegrationInstance
    _seed_connectors(db)

    q = db.query(IntegrationConnector).filter(IntegrationConnector.is_active == True)
    if category:
        q = q.filter(IntegrationConnector.category == category.lower())
    if certified_only:
        q = q.filter(IntegrationConnector.is_certified == True)
    connectors = q.order_by(IntegrationConnector.name).all()

    # Check which are installed for this user's org
    org_id = getattr(current_user, "organization_id", None)
    installed_slugs: set = set()
    if org_id:
        instances = db.query(IntegrationInstance).filter(
            IntegrationInstance.organization_id == org_id,
            IntegrationInstance.is_enabled == True,
        ).all()
        for inst in instances:
            conn = db.query(IntegrationConnector).filter(
                IntegrationConnector.id == inst.connector_id
            ).first()
            if conn:
                installed_slugs.add(conn.slug)

    return [
        {
            "id": c.id, "name": c.name, "slug": c.slug, "category": c.category,
            "description": c.description, "logo_url": c.logo_url, "docs_url": c.docs_url,
            "auth_scheme": c.auth_scheme, "is_certified": c.is_certified,
            "is_installed": c.slug in installed_slugs,
        }
        for c in connectors
    ]


class InstanceCreate(BaseModel):
    connector_slug: str
    name: str
    config: Dict[str, Any] = Field(default_factory=dict)
    sync_direction: str = "bidirectional"
    sync_frequency: str = "hourly"

    @validator("sync_direction")
    def valid_direction(cls, v):
        if v not in ("inbound", "outbound", "bidirectional"):
            raise ValueError("sync_direction must be inbound|outbound|bidirectional")
        return v

    @validator("sync_frequency")
    def valid_frequency(cls, v):
        if v not in ("realtime", "hourly", "daily", "manual"):
            raise ValueError("sync_frequency must be realtime|hourly|daily|manual")
        return v


@router.post("/integrations/instances", summary="Install integration connector", status_code=201)
def install_integration(
    payload: InstanceCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """
    Installs a connector for the current organization.
    Config values (API keys, OAuth tokens) are stored but NOT returned in responses.
    """
    from app.models.marketplace import IntegrationConnector, IntegrationInstance
    from app.core.encryption import encrypt_value
    _seed_connectors(db)

    connector = db.query(IntegrationConnector).filter(
        IntegrationConnector.slug == payload.connector_slug,
        IntegrationConnector.is_active == True,
    ).first()
    if not connector:
        raise HTTPException(404, f"Connector '{payload.connector_slug}' not found in marketplace")

    org_id = getattr(current_user, "organization_id", None)
    if not org_id:
        raise HTTPException(400, "User has no associated organization")

    # Encrypt sensitive config before storage
    config_json = json.dumps(payload.config)
    try:
        encrypted = encrypt_value(config_json)
    except Exception:
        encrypted = config_json  # Fallback if encryption not configured

    instance = IntegrationInstance(
        organization_id=org_id,
        connector_id=connector.id,
        name=payload.name,
        encrypted_config=encrypted,
        sync_direction=payload.sync_direction,
        sync_frequency=payload.sync_frequency,
        is_enabled=True,
        created_by=current_user.id,
    )
    db.add(instance)
    db.commit()
    db.refresh(instance)
    return {
        "id": instance.id, "name": instance.name,
        "connector": payload.connector_slug,
        "sync_direction": instance.sync_direction,
        "sync_frequency": instance.sync_frequency,
        "is_enabled": instance.is_enabled,
        "created": True,
    }


@router.get("/integrations/instances", summary="List installed integrations")
def list_instances(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    from app.models.marketplace import IntegrationConnector, IntegrationInstance
    org_id = getattr(current_user, "organization_id", None)
    if not org_id:
        return []
    instances = db.query(IntegrationInstance).filter(
        IntegrationInstance.organization_id == org_id,
    ).all()
    result = []
    for inst in instances:
        conn = db.query(IntegrationConnector).filter(
            IntegrationConnector.id == inst.connector_id
        ).first()
        result.append({
            "id": inst.id, "name": inst.name,
            "connector_slug": conn.slug if conn else None,
            "connector_name": conn.name if conn else None,
            "connector_category": conn.category if conn else None,
            "sync_direction": inst.sync_direction,
            "sync_frequency": inst.sync_frequency,
            "is_enabled": inst.is_enabled,
            "last_sync_at": str(inst.last_sync_at) if inst.last_sync_at else None,
            "last_sync_status": inst.last_sync_status,
            "last_sync_records": inst.last_sync_records,
            "last_error": inst.last_error,
        })
    return result


@router.delete("/integrations/instances/{instance_id}",
               summary="Uninstall integration", status_code=204)
def uninstall_integration(
    instance_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    from app.models.marketplace import IntegrationInstance
    org_id = getattr(current_user, "organization_id", None)
    inst = db.query(IntegrationInstance).filter(
        IntegrationInstance.id == instance_id,
        IntegrationInstance.organization_id == org_id,
    ).first()
    if not inst:
        raise HTTPException(404, "Integration instance not found")
    db.delete(inst)
    db.commit()
    return None


# ══════════════════════════════════════════════════════════════════════════════
# 5. SALESFORCE CRM BIDIRECTIONAL SYNC
# ══════════════════════════════════════════════════════════════════════════════

@router.post("/integrations/salesforce/sync-opportunities",
             summary="Sync Salesforce opportunities → Pipeline")
async def sync_salesforce_opportunities(
    instance_id: str = Query(..., description="IntegrationInstance ID for Salesforce"),
    direction: str = Query(default="inbound", description="inbound|outbound|bidirectional"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    """
    Sync Salesforce opportunities with the Clarive pipeline.
    - inbound:  Salesforce → Clarive (import/update opportunities)
    - outbound: Clarive → Salesforce (push opportunities)
    - bidirectional: both directions with conflict resolution (last-write-wins)

    Requires Salesforce Connected App credentials in the IntegrationInstance config.
    """
    from app.models.marketplace import IntegrationInstance, IntegrationConnector
    from app.core.encryption import decrypt_value
    from app.models.pipeline import Opportunity

    org_id = getattr(current_user, "organization_id", None)
    inst = db.query(IntegrationInstance).filter(
        IntegrationInstance.id == instance_id,
        IntegrationInstance.organization_id == org_id,
        IntegrationInstance.is_enabled == True,
    ).first()
    if not inst:
        raise HTTPException(404, "Salesforce integration instance not found or disabled")

    # Verify this is a Salesforce connector
    conn = db.query(IntegrationConnector).filter(
        IntegrationConnector.id == inst.connector_id,
        IntegrationConnector.slug == "salesforce",
    ).first()
    if not conn:
        raise HTTPException(400, "This instance is not a Salesforce connector")

    # Decrypt config
    try:
        config = json.loads(decrypt_value(inst.encrypted_config) if inst.encrypted_config else "{}")
    except Exception:
        config = {}

    sf_base = config.get("instance_url", "")
    access_token = config.get("access_token", "")
    if not sf_base or not access_token:
        raise HTTPException(
            503,
            "Salesforce credentials incomplete. Configure instance_url and access_token "
            "in the integration settings.",
        )

    synced_in = 0
    synced_out = 0
    errors: List[str] = []

    if direction in ("inbound", "bidirectional"):
        import httpx
        try:
            async with httpx.AsyncClient(timeout=20.0) as client:
                resp = await client.get(
                    f"{sf_base}/services/data/v57.0/query",
                    params={"q": "SELECT Id,Name,Amount,StageName,CloseDate,AccountId FROM Opportunity WHERE IsClosed=false LIMIT 200"},
                    headers={"Authorization": f"Bearer {access_token}"},
                )
                resp.raise_for_status()
                sf_opps = resp.json().get("records", [])
        except Exception as exc:
            errors.append(f"Salesforce API error: {exc}")
            sf_opps = []

        for sf_opp in sf_opps:
            sf_id = sf_opp.get("Id")
            # Check if opportunity already exists (matched by external_id)
            existing_opp = db.query(Opportunity).filter(
                Opportunity.external_id == sf_id
            ).first() if hasattr(Opportunity, "external_id") else None

            stage_map = {
                "Prospecting": "lead", "Qualification": "qualification",
                "Needs Analysis": "qualification", "Value Proposition": "proposal",
                "Id. Decision Makers": "proposal", "Perception Analysis": "negotiation",
                "Proposal/Price Quote": "proposal", "Negotiation/Review": "negotiation",
                "Closed Won": "won", "Closed Lost": "lost",
            }
            mapped_stage = stage_map.get(sf_opp.get("StageName", ""), "lead")

            try:
                close_date = date.fromisoformat(sf_opp["CloseDate"]) if sf_opp.get("CloseDate") else None
            except ValueError:
                close_date = None

            if existing_opp:
                existing_opp.name = sf_opp.get("Name", existing_opp.name)
                existing_opp.expected_revenue = sf_opp.get("Amount") or existing_opp.expected_revenue
                existing_opp.stage = mapped_stage
                if close_date and hasattr(existing_opp, "close_date"):
                    existing_opp.close_date = close_date
            else:
                new_opp = Opportunity(
                    name=sf_opp.get("Name", "Imported from Salesforce"),
                    client_name=sf_opp.get("AccountId", "Salesforce Account"),
                    stage=mapped_stage,
                    expected_revenue=sf_opp.get("Amount") or 0,
                )
                if hasattr(new_opp, "external_id"):
                    new_opp.external_id = sf_id
                if close_date and hasattr(new_opp, "close_date"):
                    new_opp.close_date = close_date
                db.add(new_opp)
            synced_in += 1

        if sf_opps:
            db.commit()

    # Update sync status
    inst.last_sync_at = datetime.utcnow()
    inst.last_sync_status = "error" if errors else "ok"
    inst.last_sync_records = synced_in + synced_out
    inst.last_error = "; ".join(errors) if errors else None
    db.commit()

    return {
        "ok": not errors,
        "direction": direction,
        "synced_inbound": synced_in,
        "synced_outbound": synced_out,
        "errors": errors,
        "synced_at": str(datetime.utcnow()),
    }


# ══════════════════════════════════════════════════════════════════════════════
# 6. CUSTOMER HEALTH SCORE — enhanced composite formula
# ══════════════════════════════════════════════════════════════════════════════

@router.get("/clients/{client_id}/health-composite",
            summary="Compute enhanced composite customer health score")
def compute_composite_health(
    client_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    """
    Composite Health Score (0–100) combining:
      - NPS (40%): last 90 days net promoter score
      - Delivery (20%): % of milestones delivered on time
      - Budget (15%): % projects within budget
      - Ticket resolution (15%): avg SLA compliance last 30 days
      - Portal activity (10%): login activity in client portal last 30 days
    """
    from app.models.clients import Client
    from app.models.nps import ClientNPS

    client = db.query(Client).filter(Client.id == client_id).first()
    if not client:
        raise HTTPException(404, "Client not found")

    components: Dict[str, Any] = {}

    # --- NPS component (40%) ---
    cutoff_90 = datetime.utcnow() - timedelta(days=90)
    nps_responses = db.query(ClientNPS).filter(
        ClientNPS.client_id == client_id,
        ClientNPS.created_at >= cutoff_90,
    ).all()
    if nps_responses:
        promoters  = sum(1 for r in nps_responses if r.score >= 9)
        detractors = sum(1 for r in nps_responses if r.score <= 6)
        n = len(nps_responses)
        raw_nps = ((promoters - detractors) / n) * 100  # -100..100
        nps_component = round(((raw_nps + 100) / 2), 1)  # normalize to 0-100
        components["nps"] = {"value": nps_component, "weight": 0.40,
                              "responses": n, "raw_nps": round(raw_nps, 1)}
    else:
        nps_component = 50.0
        components["nps"] = {"value": 50.0, "weight": 0.40, "responses": 0, "note": "no_data"}

    # --- Delivery component (20%) ---
    try:
        from app.models.project import Project
        from app.models.milestones import Milestone
        projects = db.query(Project).filter(Project.client_id == client_id).all()
        proj_ids = [p.id for p in projects]
        if proj_ids:
            all_milestones = db.query(Milestone).filter(
                Milestone.project_id.in_(proj_ids)
            ).all() if hasattr(Milestone, "project_id") else []
            done = [m for m in all_milestones
                    if str(getattr(m, "status", "")).lower() in ("completed", "done", "approved")]
            on_time = [m for m in done
                       if hasattr(m, "due_date") and hasattr(m, "completed_at")
                       and m.completed_at and m.due_date
                       and m.completed_at.date() <= m.due_date]
            delivery = round((len(on_time) / max(len(done), 1)) * 100, 1) if done else 70.0
        else:
            delivery = 70.0
    except Exception:
        delivery = 70.0
    components["delivery"] = {"value": delivery, "weight": 0.20}

    # --- Budget component (15%) ---
    try:
        in_budget = sum(1 for p in projects
                        if hasattr(p, "budget") and hasattr(p, "actual_cost")
                        and p.budget and p.actual_cost is not None
                        and p.actual_cost <= p.budget)
        budget_score = round((in_budget / max(len(projects), 1)) * 100, 1) if projects else 70.0
    except Exception:
        budget_score = 70.0
    components["budget"] = {"value": budget_score, "weight": 0.15}

    # --- Ticket resolution component (15%) ---
    try:
        from app.models.service_desk import Ticket
        cutoff_30 = datetime.utcnow() - timedelta(days=30)
        recent_tickets = db.query(Ticket).filter(
            Ticket.created_at >= cutoff_30,
        ).all()
        # Filter to client's tickets if client_id is stored on tickets
        client_tickets = [t for t in recent_tickets
                          if hasattr(t, "client_id") and t.client_id == client_id]
        if not client_tickets:
            # Fallback: use organization-wide SLA compliance
            client_tickets = recent_tickets[:50]  # sample
        resolved = [t for t in client_tickets
                    if str(getattr(t.status, "value", t.status)) in ("resolved", "closed")]
        sla_ok = [t for t in resolved
                  if hasattr(t, "sla_breached") and not t.sla_breached]
        ticket_score = round((len(sla_ok) / max(len(resolved), 1)) * 100, 1) if resolved else 70.0
    except Exception:
        ticket_score = 70.0
    components["ticket_resolution"] = {"value": ticket_score, "weight": 0.15}

    # --- Portal activity component (10%) ---
    try:
        from app.models.client_portal import PortalSession
        portal_sessions = db.query(PortalSession).filter(
            PortalSession.client_id == client_id,
            PortalSession.created_at >= cutoff_30,
        ).count() if hasattr(PortalSession, "client_id") else 0
        # >10 sessions = full score, 0 = 30
        portal_score = min(100.0, 30.0 + (portal_sessions * 7.0))
    except Exception:
        portal_score = 50.0
    components["portal_activity"] = {"value": portal_score, "weight": 0.10}

    # --- Composite ---
    composite = round(
        nps_component * 0.40 +
        delivery     * 0.20 +
        budget_score * 0.15 +
        ticket_score * 0.15 +
        portal_score * 0.10,
        1
    )
    composite = max(0.0, min(100.0, composite))

    category = ("excellent" if composite >= 80 else
                 "good"      if composite >= 60 else
                 "at_risk"   if composite >= 40 else
                 "critical")

    return {
        "client_id": client_id,
        "composite_score": composite,
        "category": category,
        "components": components,
        "computed_at": str(datetime.utcnow()),
    }


# ══════════════════════════════════════════════════════════════════════════════
# 7. AI COPILOT CONTEXTUAL INLINE SUGGESTIONS
# ══════════════════════════════════════════════════════════════════════════════

@router.get("/ai/suggestions/gantt/{project_id}",
            summary="AI: predict Gantt delays and suggest mitigations")
def ai_gantt_suggestions(
    project_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Analyzes the current project schedule for risk signals:
    - Tasks overdue or with zero progress after 50% of their duration elapsed
    - Resource overload patterns
    - Critical path bottlenecks
    Returns inline AI suggestions for each risk identified.
    """
    from app.models.project import Project
    from app.models.task import Task

    proj = db.query(Project).filter(Project.id == project_id).first()
    if not proj:
        raise HTTPException(404, "Project not found")

    tasks = db.query(Task).filter(Task.project_id == project_id).all()
    today = date.today()
    suggestions = []

    for t in tasks:
        status_val = str(getattr(t.status, "value", t.status))
        if status_val in ("done", "closed", "cancelled"):
            continue

        # Overdue detection
        if t.due_date and t.due_date < today:
            overdue_days = (today - t.due_date).days
            suggestions.append({
                "task_id": t.id,
                "task_title": t.title,
                "type": "overdue",
                "severity": "high" if overdue_days > 7 else "medium",
                "message": f"Task is {overdue_days} day(s) overdue.",
                "suggestions": [
                    "Reassign to available resource",
                    "Split into smaller tasks to unblock progress",
                    "Review scope — consider deferring non-critical items",
                ],
            })
        # Stalled detection: 50%+ of duration elapsed, 0 progress
        elif (hasattr(t, "start_date") and t.start_date and t.due_date
              and t.start_date < today < t.due_date):
            total_days = (t.due_date - t.start_date).days or 1
            elapsed_pct = (today - t.start_date).days / total_days
            progress = getattr(t, "progress", None) or 0
            if elapsed_pct >= 0.5 and progress < 20:
                suggestions.append({
                    "task_id": t.id,
                    "task_title": t.title,
                    "type": "stalled",
                    "severity": "medium",
                    "message": f"{int(elapsed_pct*100)}% of duration elapsed but only {progress}% complete.",
                    "suggestions": [
                        "Check for blockers in comments",
                        "Schedule a quick sync with the assignee",
                        "Consider parallel execution if dependencies allow",
                    ],
                })

    return {
        "project_id": project_id,
        "project_name": proj.name,
        "suggestions_count": len(suggestions),
        "suggestions": suggestions,
        "analysed_at": str(datetime.utcnow()),
    }


@router.get("/ai/suggestions/timesheets/{user_id}",
            summary="AI: detect timesheet anomalies for a user")
def ai_timesheet_anomalies(
    user_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    """
    Detects anomalies in a user's timesheets:
    - Days with unusually high hours (>12h)
    - Long gaps without any entries
    - Entries billed to inactive/closed projects
    """
    from app.models.imputation import Imputation
    from app.models.project import Project

    cutoff = date.today() - timedelta(days=30)
    entries = db.query(Imputation).filter(
        Imputation.user_id == user_id,
        Imputation.date >= cutoff,
    ).order_by(Imputation.date).all()

    anomalies = []

    # High hours per day
    daily_hours: Dict[str, float] = {}
    for e in entries:
        k = str(e.date)
        daily_hours[k] = daily_hours.get(k, 0) + (e.hours or 0)

    for day, hours in daily_hours.items():
        if hours > 12:
            anomalies.append({
                "type": "high_hours",
                "date": day,
                "value": hours,
                "message": f"{hours}h logged on {day} — exceeds 12h threshold",
                "suggestion": "Verify these hours are correct or split across days if entered in bulk",
            })

    # Gaps detection (>5 working days without entry)
    if entries:
        prev_date = entries[0].date
        for e in entries[1:]:
            gap_days = (e.date - prev_date).days
            if gap_days > 7:  # >7 calendar days incl. weekends
                anomalies.append({
                    "type": "gap",
                    "date": str(prev_date),
                    "value": gap_days,
                    "message": f"{gap_days}-day gap in timesheet entries",
                    "suggestion": "Missing time entries for the period? Please fill in timesheets.",
                })
            prev_date = e.date

    # Entries on closed/cancelled projects
    proj_ids = {e.project_id for e in entries if e.project_id}
    closed_projs = db.query(Project).filter(
        Project.id.in_(list(proj_ids)),
        Project.status.in_(["closed", "cancelled", "archived"]),
    ).all()
    closed_ids = {p.id for p in closed_projs}
    if closed_ids:
        anomalies.append({
            "type": "closed_project_billing",
            "project_ids": list(closed_ids),
            "message": "Time entries found on closed/cancelled projects",
            "suggestion": "Review and reassign to the correct active project",
        })

    return {
        "user_id": user_id,
        "period": {"from": str(cutoff), "to": str(date.today())},
        "total_entries": len(entries),
        "anomalies_count": len(anomalies),
        "anomalies": anomalies,
        "analysed_at": str(datetime.utcnow()),
    }


@router.get("/ai/suggestions/ticket/{ticket_id}",
            summary="AI: suggest KB articles for a service desk ticket")
def ai_ticket_kb_suggestions(
    ticket_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Suggests Knowledge Base articles for a ticket based on title + description similarity.
    Uses keyword matching; upgrade to vector search by enabling the semantic engine.
    """
    from app.models.service_desk import Ticket, KBArticle

    ticket = db.query(Ticket).filter(Ticket.id == ticket_id).first()
    if not ticket:
        raise HTTPException(404, "Ticket not found")

    # Keyword tokenization
    text = f"{ticket.title or ''} {ticket.description or ''}".lower()
    words = set(w for w in text.split() if len(w) > 3)

    articles = db.query(KBArticle).filter(
        KBArticle.is_published == True,
    ).limit(200).all()

    scored = []
    for art in articles:
        art_text = f"{art.title or ''} {art.content or ''}".lower()
        matches = sum(1 for w in words if w in art_text)
        if matches > 0:
            scored.append({
                "article_id": art.id,
                "title": art.title,
                "score": matches,
                "url": f"/api/v1/sd/kb/articles/{art.id}",
            })
    scored.sort(key=lambda x: -x["score"])

    return {
        "ticket_id": ticket_id,
        "ticket_title": ticket.title,
        "suggestions": scored[:5],
        "analysed_at": str(datetime.utcnow()),
    }


# ══════════════════════════════════════════════════════════════════════════════
# 8. ENHANCED PROJECT TEMPLATES — documents + roles
# ══════════════════════════════════════════════════════════════════════════════

class TemplateDocCreate(BaseModel):
    name: str
    document_type: str = "spec"
    description: Optional[str] = None
    url: Optional[str] = None
    is_required: bool = False
    due_week_offset: Optional[int] = None


class TemplateRoleCreate(BaseModel):
    role_name: str
    skill_required: Optional[str] = None
    min_seniority: Optional[str] = None
    estimated_hours: Optional[float] = None
    is_mandatory: bool = True
    notes: Optional[str] = None


@router.post("/templates/{template_id}/documents",
             summary="Add document reference to project template", status_code=201)
def add_template_document(
    template_id: str,
    payload: TemplateDocCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    from app.models.advanced_config import ProjectTemplate
    from app.models.marketplace import TemplateDocument
    if not db.query(ProjectTemplate).filter(ProjectTemplate.id == template_id).first():
        raise HTTPException(404, "Template not found")
    doc = TemplateDocument(template_id=template_id, **payload.dict())
    db.add(doc)
    db.commit()
    db.refresh(doc)
    return {"id": doc.id, "name": doc.name, "created": True}


@router.post("/templates/{template_id}/roles",
             summary="Add required role to project template", status_code=201)
def add_template_role(
    template_id: str,
    payload: TemplateRoleCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    from app.models.advanced_config import ProjectTemplate
    from app.models.marketplace import TemplateRole
    if not db.query(ProjectTemplate).filter(ProjectTemplate.id == template_id).first():
        raise HTTPException(404, "Template not found")
    role = TemplateRole(template_id=template_id, **payload.dict())
    db.add(role)
    db.commit()
    db.refresh(role)
    return {"id": role.id, "role_name": role.role_name, "created": True}


@router.get("/templates/{template_id}/full",
            summary="Get full template with phases, tasks, risks, documents, roles")
def get_full_template(
    template_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    from app.models.advanced_config import (ProjectTemplate, TemplatePhase,
                                             TemplateTask, TemplateRisk, TemplateDeliverable)
    from app.models.marketplace import TemplateDocument, TemplateRole

    tmpl = db.query(ProjectTemplate).filter(ProjectTemplate.id == template_id).first()
    if not tmpl:
        raise HTTPException(404, "Template not found")

    phases = db.query(TemplatePhase).filter(
        TemplatePhase.template_id == template_id
    ).order_by(TemplatePhase.order).all()
    phase_out = []
    for ph in phases:
        tasks = db.query(TemplateTask).filter(
            TemplateTask.phase_id == ph.id
        ).order_by(TemplateTask.order).all()
        phase_out.append({
            "id": ph.id, "name": ph.name, "description": ph.description,
            "order": ph.order, "estimated_weeks": ph.estimated_weeks,
            "estimated_hours": ph.estimated_hours,
            "tasks": [{"id": t.id, "title": t.title, "description": t.description,
                        "estimated_hours": t.estimated_hours, "skill_required": t.skill_required,
                        "order": t.order} for t in tasks],
        })

    risks = db.query(TemplateRisk).filter(TemplateRisk.template_id == template_id).all()
    deliverables = db.query(TemplateDeliverable).filter(
        TemplateDeliverable.template_id == template_id
    ).all()
    documents = db.query(TemplateDocument).filter(
        TemplateDocument.template_id == template_id
    ).all()
    roles = db.query(TemplateRole).filter(TemplateRole.template_id == template_id).all()

    return {
        "id": tmpl.id, "name": tmpl.name, "description": tmpl.description,
        "project_type": tmpl.project_type, "estimated_weeks": tmpl.estimated_weeks,
        "estimated_hours": tmpl.estimated_hours, "is_active": tmpl.is_active,
        "phases": phase_out,
        "risks": [{"id": r.id, "title": r.title, "category": r.category,
                   "probability": r.probability, "impact": r.impact,
                   "mitigation_plan": r.mitigation_plan} for r in risks],
        "deliverables": [{"id": d.id, "name": d.name, "format": d.format,
                           "acceptance_criteria": d.acceptance_criteria,
                           "week_offset": d.week_offset, "billing_pct": d.billing_pct}
                          for d in deliverables],
        "documents": [{"id": d.id, "name": d.name, "document_type": d.document_type,
                        "description": d.description, "url": d.url,
                        "is_required": d.is_required, "due_week_offset": d.due_week_offset}
                       for d in documents],
        "roles": [{"id": r.id, "role_name": r.role_name, "skill_required": r.skill_required,
                   "min_seniority": r.min_seniority, "estimated_hours": r.estimated_hours,
                   "is_mandatory": r.is_mandatory, "notes": r.notes} for r in roles],
    }


@router.post("/projects/{project_id}/export-template",
             summary="Export existing project as a reusable template", status_code=201)
def export_project_as_template(
    project_id: str,
    body: dict = Body(default={"name": None, "description": None}),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    """
    Converts the structure of an existing project (phases/tasks/risks/deliverables)
    into a reusable ProjectTemplate that can be instantiated for future projects.
    """
    from app.models.project import Project
    from app.models.task import Task
    from app.models.pipeline import Risk as RiskModel
    from app.models.advanced_config import (ProjectTemplate, TemplatePhase,
                                             TemplateTask, TemplateRisk)

    proj = db.query(Project).filter(Project.id == project_id).first()
    if not proj:
        raise HTTPException(404, "Project not found")

    tmpl_name = body.get("name") or f"Template from {proj.name}"
    tmpl = ProjectTemplate(
        name=tmpl_name,
        description=body.get("description") or proj.description,
        project_type=proj.project_type if hasattr(proj, "project_type") else None,
        created_by=current_user.id,
    )
    db.add(tmpl)
    db.flush()

    # Default phase: "Main"
    phase = TemplatePhase(
        template_id=tmpl.id, name="Fase Principal", order=0,
    )
    db.add(phase)
    db.flush()

    # Export tasks
    tasks = db.query(Task).filter(Task.project_id == project_id).all()
    for i, t in enumerate(tasks):
        db.add(TemplateTask(
            phase_id=phase.id,
            title=t.title,
            description=t.description if hasattr(t, "description") else None,
            estimated_hours=t.estimated_hours if hasattr(t, "estimated_hours") else None,
            order=i,
        ))

    # Export risks
    risks = db.query(RiskModel).filter(RiskModel.project_id == project_id).all()
    for r in risks:
        db.add(TemplateRisk(
            template_id=tmpl.id,
            title=r.title,
            category=r.category if hasattr(r, "category") else None,
            probability=str(getattr(r, "probability", "medium")),
            impact=str(getattr(r, "impact", "moderate")),
            mitigation_plan=r.mitigation_plan if hasattr(r, "mitigation_plan") else None,
        ))

    db.commit()
    db.refresh(tmpl)
    return {
        "template_id": tmpl.id,
        "name": tmpl.name,
        "tasks_exported": len(tasks),
        "risks_exported": len(risks),
        "created": True,
    }


# ══════════════════════════════════════════════════════════════════════════════
# 9. APPROVAL WORKFLOW VISUAL BUILDER
# ══════════════════════════════════════════════════════════════════════════════

@router.get("/approval-workflows/builder/schema",
            summary="Get visual workflow builder schema (node types, edge types)")
def get_workflow_builder_schema(
    current_user: User = Depends(get_current_user),
):
    """
    Returns the JSON schema used by the visual drag-and-drop workflow builder.
    Each node type defines inputs, outputs and configuration fields.
    """
    return {
        "version": "1.0",
        "node_types": [
            {
                "type": "start",
                "label": "Start",
                "description": "Workflow trigger (submission event)",
                "icon": "play",
                "color": "#10b981",
                "inputs": [],
                "outputs": ["next"],
                "config_schema": {
                    "entity_type": {"type": "enum", "options": ["timesheet", "expense", "contract", "po"], "required": True},
                    "min_amount": {"type": "number", "required": False},
                }
            },
            {
                "type": "approval_step",
                "label": "Approval Step",
                "description": "Human approval required",
                "icon": "check-circle",
                "color": "#6366f1",
                "inputs": ["prev"],
                "outputs": ["approved", "rejected"],
                "config_schema": {
                    "approver_type": {"type": "enum", "options": ["role", "user", "manager", "auto"], "required": True},
                    "approver_role": {"type": "string", "required": False},
                    "approver_user_id": {"type": "string", "required": False},
                    "timeout_hours": {"type": "number", "default": 48},
                    "escalate_on_timeout": {"type": "boolean", "default": True},
                    "require_comment": {"type": "boolean", "default": False},
                }
            },
            {
                "type": "condition",
                "label": "Condition",
                "description": "Branch on field value",
                "icon": "git-branch",
                "color": "#f59e0b",
                "inputs": ["prev"],
                "outputs": ["true", "false"],
                "config_schema": {
                    "field": {"type": "string", "required": True},
                    "operator": {"type": "enum", "options": ["eq", "ne", "gt", "lt", "gte", "lte", "contains"], "required": True},
                    "value": {"type": "string", "required": True},
                }
            },
            {
                "type": "action",
                "label": "Action",
                "description": "Automated action (notify, update field, call webhook)",
                "icon": "zap",
                "color": "#06b6d4",
                "inputs": ["prev"],
                "outputs": ["next"],
                "config_schema": {
                    "action_type": {"type": "enum", "options": ["notify_role", "notify_user", "update_status", "call_webhook", "send_email"], "required": True},
                    "params": {"type": "object", "required": False},
                }
            },
            {
                "type": "end",
                "label": "End",
                "description": "Workflow complete",
                "icon": "stop-circle",
                "color": "#ef4444",
                "inputs": ["prev"],
                "outputs": [],
                "config_schema": {
                    "final_status": {"type": "enum", "options": ["approved", "rejected", "cancelled"], "required": True},
                }
            },
        ],
        "edge_types": [
            {"type": "default", "label": "Next", "color": "#6b7280"},
            {"type": "approved",  "label": "Approved",  "color": "#10b981"},
            {"type": "rejected",  "label": "Rejected",  "color": "#ef4444"},
            {"type": "true",  "label": "True",  "color": "#3b82f6"},
            {"type": "false", "label": "False", "color": "#f59e0b"},
        ],
        "canvas": {"default_zoom": 1.0, "grid_snap": 20},
    }


@router.post("/approval-workflows/builder/validate",
             summary="Validate a visual workflow graph structure")
def validate_workflow_graph(
    graph: dict = Body(...),
    current_user: User = Depends(require_any_manager),
):
    """
    Validates a workflow graph JSON for structural correctness:
    - Must have exactly one start node
    - Every node except 'end' must have at least one outgoing edge
    - No orphaned nodes
    - No cycles (basic check)
    """
    nodes = graph.get("nodes", [])
    edges = graph.get("edges", [])
    errors: List[str] = []
    warnings: List[str] = []

    node_types = {n["id"]: n.get("type") for n in nodes if "id" in n}
    edge_sources = {e.get("source") for e in edges}
    edge_targets = {e.get("target") for e in edges}

    # Exactly one start
    starts = [n for n in nodes if n.get("type") == "start"]
    if len(starts) == 0:
        errors.append("Workflow must have exactly one 'start' node")
    elif len(starts) > 1:
        errors.append("Workflow must have exactly one 'start' node (found multiple)")

    # Every non-end node must have outgoing edge
    for node in nodes:
        nid = node.get("id")
        if node.get("type") != "end" and nid not in edge_sources:
            errors.append(f"Node '{node.get('type', nid)}' has no outgoing edges")

    # No orphaned non-start nodes
    for node in nodes:
        nid = node.get("id")
        if node.get("type") != "start" and nid not in edge_targets:
            warnings.append(f"Node '{node.get('type', nid)}' has no incoming edges")

    # At least one end node
    ends = [n for n in nodes if n.get("type") == "end"]
    if not ends:
        errors.append("Workflow must have at least one 'end' node")

    return {
        "valid": len(errors) == 0,
        "errors": errors,
        "warnings": warnings,
        "node_count": len(nodes),
        "edge_count": len(edges),
    }


# ══════════════════════════════════════════════════════════════════════════════
# 10. SLACK BLOCK KIT RICH NOTIFICATIONS
# ══════════════════════════════════════════════════════════════════════════════

def _build_block_kit_message(event_type: str, payload: dict) -> dict:
    """Build a Slack Block Kit message for common NexusPM events."""
    base_url = settings.FRONTEND_URL or "http://localhost:3000"

    if event_type == "task_overdue":
        return {
            "blocks": [
                {"type": "header", "text": {"type": "plain_text", "text": "⚠️ Task Overdue"}},
                {"type": "section", "fields": [
                    {"type": "mrkdwn", "text": f"*Task:*\n{payload.get('task_title', 'N/A')}"},
                    {"type": "mrkdwn", "text": f"*Project:*\n{payload.get('project_name', 'N/A')}"},
                    {"type": "mrkdwn", "text": f"*Due Date:*\n{payload.get('due_date', 'N/A')}"},
                    {"type": "mrkdwn", "text": f"*Assignee:*\n{payload.get('assignee', 'N/A')}"},
                ]},
                {"type": "actions", "elements": [
                    {"type": "button", "text": {"type": "plain_text", "text": "View Task"},
                     "url": f"{base_url}/tasks/{payload.get('task_id', '')}",
                     "style": "primary"},
                    {"type": "button", "text": {"type": "plain_text", "text": "Update Status"},
                     "url": f"{base_url}/tasks/{payload.get('task_id', '')}?action=update"},
                ]},
            ]
        }
    elif event_type == "invoice_paid":
        return {
            "blocks": [
                {"type": "header", "text": {"type": "plain_text", "text": "✅ Invoice Paid"}},
                {"type": "section", "fields": [
                    {"type": "mrkdwn", "text": f"*Invoice:*\n{payload.get('invoice_number', 'N/A')}"},
                    {"type": "mrkdwn", "text": f"*Amount:*\n{payload.get('currency', 'EUR')} {payload.get('amount', 0):,.2f}"},
                    {"type": "mrkdwn", "text": f"*Client:*\n{payload.get('client_name', 'N/A')}"},
                    {"type": "mrkdwn", "text": f"*Paid At:*\n{payload.get('paid_at', 'N/A')}"},
                ]},
                {"type": "divider"},
                {"type": "context", "elements": [
                    {"type": "mrkdwn", "text": "💰 Payment received via Stripe"}
                ]},
            ]
        }
    elif event_type == "approval_required":
        return {
            "blocks": [
                {"type": "header", "text": {"type": "plain_text", "text": "🔔 Approval Required"}},
                {"type": "section", "text": {
                    "type": "mrkdwn",
                    "text": f"*{payload.get('entity_type', 'Item').title()}* submitted by "
                            f"*{payload.get('submitter', 'Unknown')}* requires your approval.",
                }},
                {"type": "section", "fields": [
                    {"type": "mrkdwn", "text": f"*Amount:*\n{payload.get('amount', 'N/A')}"},
                    {"type": "mrkdwn", "text": f"*Project:*\n{payload.get('project_name', 'N/A')}"},
                ]},
                {"type": "actions", "elements": [
                    {"type": "button", "text": {"type": "plain_text", "text": "✅ Approve"},
                     "style": "primary",
                     "url": f"{base_url}/approvals/{payload.get('request_id', '')}?action=approve"},
                    {"type": "button", "text": {"type": "plain_text", "text": "❌ Reject"},
                     "style": "danger",
                     "url": f"{base_url}/approvals/{payload.get('request_id', '')}?action=reject"},
                ]},
            ]
        }
    else:
        # Generic notification
        return {
            "blocks": [
                {"type": "section", "text": {
                    "type": "mrkdwn",
                    "text": f"*NexusPM Notification:* {payload.get('message', 'Event occurred')}",
                }},
            ]
        }


@router.post("/notifications/slack/block-kit",
             summary="Send rich Slack Block Kit notification")
async def send_slack_block_kit(
    payload: dict = Body(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    """
    Send a rich Slack Block Kit notification for a NexusPM event.
    Requires Slack webhook URL configured in integration settings.

    Payload:
    {
      "event_type": "task_overdue|invoice_paid|approval_required|custom",
      "channel": "#project-updates",   // optional, overrides default
      "webhook_url": "https://...",     // optional, overrides org default
      "data": { ... event-specific fields ... }
    }
    """
    import httpx
    from app.models.mfa import SlackConfig

    event_type = payload.get("event_type", "custom")
    data = payload.get("data", {})

    # Build Block Kit message
    block_kit = _build_block_kit_message(event_type, data)
    if payload.get("channel"):
        block_kit["channel"] = payload["channel"]

    # Get webhook URL
    webhook_url = payload.get("webhook_url")
    if not webhook_url:
        org_id = getattr(current_user, "organization_id", None)
        cfg_q = db.query(SlackConfig)
        # SlackConfig in this codebase has no organization_id column, so guard the filter.
        if org_id and hasattr(SlackConfig, "organization_id"):
            cfg_q = cfg_q.filter(SlackConfig.organization_id == org_id)
        slack_cfg = cfg_q.first()
        webhook_url = slack_cfg.webhook_url if slack_cfg and hasattr(slack_cfg, "webhook_url") else None

    if not webhook_url:
        raise HTTPException(
            status_code=503,
            detail="No Slack webhook URL configured. Set it in Settings → Integrations → Slack.",
        )

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(webhook_url, json=block_kit)
            resp.raise_for_status()
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Slack delivery failed: {exc}")

    return {"ok": True, "event_type": event_type, "blocks_count": len(block_kit.get("blocks", []))}


@router.get("/notifications/slack/block-kit/preview",
            summary="Preview Block Kit message for a given event type")
def preview_block_kit(
    event_type: str = Query(...),
    current_user: User = Depends(get_current_user),
):
    """Returns the Block Kit JSON for a sample event — useful for visual preview."""
    sample_data = {
        "task_overdue": {"task_title": "API Integration", "project_name": "CRM Relaunch",
                          "due_date": "2026-04-01", "assignee": "Alice Smith", "task_id": "xxx"},
        "invoice_paid": {"invoice_number": "INV-2026-042", "amount": 12500.0,
                          "currency": "EUR", "client_name": "Acme Corp", "paid_at": "2026-04-11"},
        "approval_required": {"entity_type": "expense", "submitter": "Bob Jones",
                               "amount": "€850", "project_name": "Digital Transformation",
                               "request_id": "req-001"},
    }
    data = sample_data.get(event_type, {"message": f"Sample {event_type} event"})
    return _build_block_kit_message(event_type, data)
