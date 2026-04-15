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
from pydantic import BaseModel, Field, field_validator
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
from app.api.v1.endpoints.v239.branding import router as branding_router
from app.api.v1.endpoints.v239.baselines import router as baselines_router
from app.api.v1.endpoints.v239.approval_builder import router as approval_builder_router

router = APIRouter()
logger = logging.getLogger(__name__)

# Currency sync endpoints were extracted to `currency_sync.py`.
router.include_router(branding_router)
router.include_router(baselines_router)
router.include_router(approval_builder_router)


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

    @field_validator("sync_direction")
    @classmethod
    def valid_direction(cls, v: str) -> str:
        if v not in ("inbound", "outbound", "bidirectional"):
            raise ValueError("sync_direction must be inbound|outbound|bidirectional")
        return v

    @field_validator("sync_frequency")
    @classmethod
    def valid_frequency(cls, v: str) -> str:
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


# Salesforce sync endpoint was extracted to `salesforce_sync.py`.


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
        from app.models.financial import ProjectMilestone
        projects = db.query(Project).filter(Project.client_id == client_id).all()
        proj_ids = [p.id for p in projects]
        if proj_ids:
            all_milestones = db.query(ProjectMilestone).filter(
                ProjectMilestone.project_id.in_(proj_ids)
            ).all() if hasattr(ProjectMilestone, "project_id") else []
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


# Slack Block Kit endpoints were extracted to `slack_block_kit.py`.
