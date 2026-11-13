"""
AI Governance Admin API — manage guardrail policies, view audit log, analytics.

Endpoints:
  POST   /ai-governance/policies                   — create policy
  GET    /ai-governance/policies                   — list policies
  GET    /ai-governance/policies/{id}              — get policy
  PATCH  /ai-governance/policies/{id}              — update policy
  DELETE /ai-governance/policies/{id}              — deactivate policy
  GET    /ai-governance/audit-log                  — paginated audit log
  GET    /ai-governance/audit-log/stats            — PII/block stats
  POST   /ai-governance/check/prompt               — test a prompt against policies
  POST   /ai-governance/check/output               — test output against policies
  GET    /ai-governance/pii-types                  — list supported PII entity types
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, get_db, require_admin
from app.core.responses import APIListResponse, APIResponse
from app.core.security import verify_admin_or_governance_role
from app.models.user import User
from app.core.abac_enforce import enforce_abac
from app.services.ai_governance import (
    check_prompt, check_output, _PII_PATTERNS,
    create_policy as svc_create_policy,
    list_policies as svc_list_policies,
    get_policy as svc_get_policy,
    update_policy as svc_update_policy,
    deactivate_policy as svc_deactivate_policy,
    get_audit_log as svc_get_audit_log,
    get_audit_stats as svc_get_audit_stats,
    get_org_id as _org,
)
from app.core.constantes import MAX_TAMANO_DE_PAGINA

router = APIRouter(tags=["AI Governance"])


# _org delegated to ai_governance.get_org_id (see import above)


# ── Pydantic schemas ──────────────────────────────────────────────────────────

class PolicyIn(BaseModel):
    name: str
    description: Optional[str] = None
    applies_to_modules: List[str] = Field(default_factory=lambda: ["*"])
    applies_to_roles:   List[str] = Field(default_factory=lambda: ["*"])
    scope: str = "both"
    action: str = "redact"
    pii_entity_types:   List[str] = Field(default_factory=list)
    redact_strategy: str = "mask"
    forbidden_keywords: List[str] = Field(default_factory=list)
    max_prompt_tokens: int = 0
    priority: int = 0
    is_active: bool = True


class PolicyUpdate(BaseModel):
    """All fields optional for partial PATCH updates."""
    name: Optional[str] = None
    description: Optional[str] = None
    applies_to_modules: Optional[List[str]] = None
    applies_to_roles:   Optional[List[str]] = None
    scope: Optional[str] = None
    action: Optional[str] = None
    pii_entity_types:   Optional[List[str]] = None
    redact_strategy: Optional[str] = None
    forbidden_keywords: Optional[List[str]] = None
    max_prompt_tokens: Optional[int] = None
    priority: Optional[int] = None
    is_active: Optional[bool] = None


class PolicyOut(BaseModel):
    id: str
    name: str
    description: Optional[str] = None
    applies_to_modules: List[str]
    applies_to_roles:   List[str]
    scope: str
    action: str
    pii_entity_types:   List[str]
    redact_strategy: str
    forbidden_keywords: List[str]
    max_prompt_tokens: int
    priority: int
    is_active: bool
    created_at: datetime

    class Config:
        from_attributes = True


class AuditLogOut(BaseModel):
    id: str
    user_id: Optional[str] = None
    module: str
    scope: str
    policy_id: Optional[str] = None
    action_taken: str
    pii_types_found: List[str]
    was_blocked: bool
    blocked_reason: Optional[str] = None
    original_length: int
    warnings: List[str]
    evaluated_at: datetime

    class Config:
        from_attributes = True


class CheckRequest(BaseModel):
    text: str
    module: str = "nexusassist"


# ── Policy CRUD ───────────────────────────────────────────────────────────────

@router.post("/policies", response_model=APIResponse[PolicyOut], status_code=status.HTTP_201_CREATED)
def create_policy(
    body: PolicyIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _rol: User = Depends(require_admin),  # auditoria 2026-09: sensible: politicas y guardrails de IA
):
    verify_admin_or_governance_role(current_user)
    _validate_policy(body)
    policy = svc_create_policy(
        db,
        org_id              = _org(current_user),
        created_by          = str(current_user.id),
        name                = body.name,
        description         = body.description,
        applies_to_modules  = body.applies_to_modules,
        applies_to_roles    = body.applies_to_roles,
        scope               = body.scope,
        action              = body.action,
        pii_entity_types    = body.pii_entity_types,
        redact_strategy     = body.redact_strategy,
        forbidden_keywords  = body.forbidden_keywords,
        max_prompt_tokens   = body.max_prompt_tokens,
        priority            = body.priority,
        is_active           = body.is_active,
    )
    return APIResponse.ok(data=PolicyOut.model_validate(policy))


@router.get("/policies", response_model=APIListResponse[PolicyOut])
def list_policies(
    active_only: bool = Query(False),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    verify_admin_or_governance_role(current_user)
    policies = svc_list_policies(db, org_id=_org(current_user), active_only=active_only)
    items = [PolicyOut.model_validate(p) for p in policies]
    return APIListResponse.ok(items=items, total=len(items))


@router.get("/policies/{policy_id}", response_model=APIResponse[PolicyOut])
def get_policy(
    policy_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    verify_admin_or_governance_role(current_user)
    p = svc_get_policy(db, policy_id=policy_id, org_id=_org(current_user))
    if not p:
        raise HTTPException(404, "Policy not found")
    return APIResponse.ok(data=PolicyOut.model_validate(p))


@router.patch("/policies/{policy_id}", response_model=APIResponse[PolicyOut])
def update_policy(
    policy_id: str,
    body: PolicyUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _rol: User = Depends(require_admin),  # auditoria 2026-09: sensible: politicas y guardrails de IA
):
    verify_admin_or_governance_role(current_user)
    p = svc_get_policy(db, policy_id=policy_id, org_id=_org(current_user))
    if not p:
        raise HTTPException(404, "Policy not found")
    p = svc_update_policy(db, p, body.model_dump(exclude_unset=True))
    return APIResponse.ok(data=PolicyOut.model_validate(p))


@router.delete("/policies/{policy_id}")
def deactivate_policy(
    policy_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _rol: User = Depends(require_admin),  # auditoria 2026-09: sensible: politicas y guardrails de IA
):
    verify_admin_or_governance_role(current_user)
    enforce_abac(db, current_user, "ai_governance_policy", policy_id, action="delete")
    p = svc_get_policy(db, policy_id=policy_id, org_id=_org(current_user))
    if not p:
        raise HTTPException(404, "Policy not found")
    svc_deactivate_policy(db, p)
    return APIResponse.ok(data={"ok": True, "deactivated": policy_id})


# ── Audit log ─────────────────────────────────────────────────────────────────

@router.get("/audit-log", response_model=APIListResponse[Dict[str, Any]])
def get_audit_log(
    module:       Optional[str] = Query(None),
    scope:        Optional[str] = Query(None),
    action_taken: Optional[str] = Query(None),
    was_blocked:  Optional[bool] = Query(None),
    user_id:      Optional[str] = Query(None),
    hours:        int = Query(168, ge=1, le=8760),
    page:         int = Query(1, ge=1),
    page_size:    int = Query(50, ge=1, le=MAX_TAMANO_DE_PAGINA),
    db: Session        = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    verify_admin_or_governance_role(current_user)
    since = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(hours=hours)
    total, items = svc_get_audit_log(
        db, org_id=_org(current_user), since=since,
        module=module, scope=scope, action_taken=action_taken,
        was_blocked=was_blocked, user_id=user_id,
        page=page, page_size=page_size,
    )
    return APIListResponse.ok(
        items=[AuditLogOut.model_validate(r).model_dump() for r in items],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/audit-log/stats", summary="PII detection & blocking statistics")
def audit_stats(
    days: int = Query(30, ge=1, le=365),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    verify_admin_or_governance_role(current_user)
    since = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=days)
    stats = svc_get_audit_stats(db, org_id=_org(current_user), since=since)
    total = stats["total"]
    return APIResponse.ok(data={
        "window_days":        days,
        "total_evaluations":  total,
        "total_blocked":      stats["total_blocked"],
        "total_redacted":     stats["total_redacted"],
        "total_warned":       stats["total_warned"],
        "block_rate":         round(stats["total_blocked"] / total, 4) if total else 0,
        "by_module":          stats["by_module"],
        "top_pii_types":      [{"type": t, "count": c} for t, c in stats["top_pii"]],
    })


# ── Interactive check (admin test tool) ──────────────────────────────────────

@router.post("/check/prompt", summary="Test a prompt against active policies")
def test_prompt(
    body: CheckRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _rol: User = Depends(require_admin),  # auditoria 2026-09: sensible: politicas y guardrails de IA
):
    verify_admin_or_governance_role(current_user)
    result = check_prompt(body.text, current_user, body.module, db)
    return APIResponse.ok(data={
        "allowed":      result.allowed,
        "action_taken": result.action_taken,
        "redacted_text":result.redacted_text,
        "pii_found":    [{"type": m.entity_type, "value_masked": f"{m.value[:2]}***"} for m in result.pii_found],
        "warnings":     result.warnings,
        "blocked_by":   result.blocked_by,
    })


@router.post("/check/output", summary="Test AI output against active policies")
def test_output(
    body: CheckRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _rol: User = Depends(require_admin),  # auditoria 2026-09: sensible: politicas y guardrails de IA
):
    verify_admin_or_governance_role(current_user)
    result = check_output(body.text, current_user, body.module, db)
    return APIResponse.ok(data={
        "allowed":      result.allowed,
        "action_taken": result.action_taken,
        "redacted_text":result.redacted_text,
        "pii_found":    [{"type": m.entity_type, "value_masked": f"{m.value[:2]}***"} for m in result.pii_found],
        "warnings":     result.warnings,
        "blocked_by":   result.blocked_by,
    })


# ── PII type reference ────────────────────────────────────────────────────────

@router.get("/pii-types", summary="List supported PII entity types")
def pii_types():
    return APIResponse.ok(data={"pii_types": [label for label, _ in _PII_PATTERNS]})


# ── Validation helper ─────────────────────────────────────────────────────────

def _validate_policy(body: PolicyIn) -> None:
    valid_scopes   = {"prompt", "output", "both"}
    valid_actions  = {"block", "redact", "warn", "log"}
    valid_strats   = {"mask", "hash", "partial", "remove"}
    valid_pii      = {label for label, _ in _PII_PATTERNS}

    if body.scope not in valid_scopes:
        raise HTTPException(422, f"scope must be one of {valid_scopes}")
    if body.action not in valid_actions:
        raise HTTPException(422, f"action must be one of {valid_actions}")
    if body.redact_strategy not in valid_strats:
        raise HTTPException(422, f"redact_strategy must be one of {valid_strats}")
    for et in body.pii_entity_types:
        if et not in valid_pii:
            raise HTTPException(422, f"Unknown PII entity type: '{et}'")
