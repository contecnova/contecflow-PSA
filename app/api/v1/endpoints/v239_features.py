"""
app/api/v1/endpoints/v239_features.py  — thin router (delegates to v239_service)

v23.9.0 Enterprise-tier endpoints:

1.  ECB real-time exchange rates (POST /currency/sync-ecb)               — currency_sync.py
2.  White-label branding per org (GET/PUT /orgs/{org_id}/branding)        — branding sub-router
3.  Gantt baselines — freeze/compare schedule snapshots                   — baselines sub-router
4.  Integration marketplace — connector catalog + install/uninstall
5.  Salesforce CRM bidirectional sync                                     — salesforce_sync.py
6.  Customer Health Score composite (enhanced formula)
7.  AI Copilot contextual inline suggestions
8.  Enhanced Project Templates (documents + roles)
9.  Approval workflow visual builder API                                   — approval_builder sub-router
10. Slack Block Kit rich notifications
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Query  # noqa: F401
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session

from app.core.deps import (
    get_current_user,
    get_db,
    require_admin,
    require_any_manager,
)
from app.models.user import User
from app.api.v1.endpoints.v239.branding import router as branding_router
from app.api.v1.endpoints.v239.baselines import router as baselines_router
from app.api.v1.endpoints.v239.approval_builder import router as approval_builder_router
import app.services.v239_service as _svc

router = APIRouter()

# Currency sync endpoints were extracted to `currency_sync.py`.
router.include_router(branding_router)
router.include_router(baselines_router)
router.include_router(approval_builder_router)


# ──────────────────────────────────────────────────────────────────────────────
# INTEGRATION MARKETPLACE
# ──────────────────────────────────────────────────────────────────────────────

@router.get("/integrations/marketplace", summary="List available integration connectors")
def list_marketplace(
    category: Optional[str] = Query(None),
    certified_only: bool = Query(False),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    org_id = getattr(current_user, "organization_id", None)
    return _svc.list_marketplace_connectors(category, certified_only, org_id, db)


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
    org_id = getattr(current_user, "organization_id", None)
    return _svc.install_integration_connector(
        payload.connector_slug, payload.name, payload.config,
        payload.sync_direction, payload.sync_frequency,
        org_id, str(current_user.id), db,
    )


@router.get("/integrations/instances", summary="List installed integrations")
def list_instances(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    org_id = getattr(current_user, "organization_id", None)
    return _svc.list_integration_instances(org_id, db)


@router.delete("/integrations/instances/{instance_id}",
               summary="Uninstall integration", status_code=204)
def uninstall_integration(
    instance_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    org_id = getattr(current_user, "organization_id", None)
    _svc.uninstall_integration_connector(instance_id, org_id, db)
    return None


# ──────────────────────────────────────────────────────────────────────────────
# CUSTOMER HEALTH SCORE
# ──────────────────────────────────────────────────────────────────────────────

@router.get("/clients/{client_id}/health-composite",
            summary="Compute enhanced composite customer health score")
def compute_composite_health(
    client_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    return _svc.compute_composite_health(client_id, db)


# ──────────────────────────────────────────────────────────────────────────────
# AI COPILOT SUGGESTIONS
# ──────────────────────────────────────────────────────────────────────────────

@router.get("/ai/suggestions/gantt/{project_id}",
            summary="AI: predict Gantt delays and suggest mitigations")
def ai_gantt_suggestions(
    project_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return _svc.get_ai_gantt_suggestions(project_id, db)


@router.get("/ai/suggestions/timesheets/{user_id}",
            summary="AI: detect timesheet anomalies for a user")
def ai_timesheet_anomalies(
    user_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    return _svc.get_ai_timesheet_anomalies(user_id, db)


@router.get("/ai/suggestions/ticket/{ticket_id}",
            summary="AI: suggest KB articles for a service desk ticket")
def ai_ticket_kb_suggestions(
    ticket_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return _svc.get_ai_ticket_kb_suggestions(ticket_id, db)


# ──────────────────────────────────────────────────────────────────────────────
# ENHANCED PROJECT TEMPLATES
# ──────────────────────────────────────────────────────────────────────────────

class TemplateDocCreate(BaseModel):
    name: str
    document_type: Optional[str] = None
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
             summary="Add document to project template", status_code=201)
def add_template_document(
    template_id: str,
    payload: TemplateDocCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    return _svc.add_template_document(template_id, payload, db)


@router.post("/templates/{template_id}/roles",
             summary="Add role requirement to project template", status_code=201)
def add_template_role(
    template_id: str,
    payload: TemplateRoleCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    return _svc.add_template_role(template_id, payload, db)


@router.get("/templates/{template_id}/full",
            summary="Get full template with phases, tasks, risks, documents and roles")
def get_full_template(
    template_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return _svc.get_full_template(template_id, db)


@router.post("/projects/{project_id}/export-template",
             summary="Export existing project as a reusable template", status_code=201)
def export_project_as_template(
    project_id: str,
    body: dict = Body(default={"name": None, "description": None}),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    return _svc.export_project_as_template(
        project_id, body.get("name"), body.get("description"), str(current_user.id), db
    )
