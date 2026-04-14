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

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.deps import get_db, get_current_user
from app.core.security import verify_admin_or_governance_role
from app.models.user import User
from app.models.ai_governance import AIGuardrailPolicyModel, AIGuardrailAuditLog
from app.services.ai_governance import (
    check_prompt, check_output, _PII_PATTERNS,
)

router = APIRouter(prefix="/ai-governance", tags=["AI Governance"])


def _org(user: User) -> str:
    if not user.organization_id:
        raise HTTPException(400, "User has no organization")
    return str(user.organization_id)


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

@router.post("/policies", response_model=PolicyOut, status_code=status.HTTP_201_CREATED)
def create_policy(
    body: PolicyIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    verify_admin_or_governance_role(current_user)
    _validate_policy(body)
    policy = AIGuardrailPolicyModel(
        id                  = str(uuid.uuid4()),
        org_id              = _org(current_user),
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
        created_by          = str(current_user.id),
    )
    db.add(policy)
    db.commit()
    db.refresh(policy)
    return PolicyOut.model_validate(policy)


@router.get("/policies", response_model=List[PolicyOut])
def list_policies(
    active_only: bool = Query(False),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    verify_admin_or_governance_role(current_user)
    q = db.query(AIGuardrailPolicyModel).filter(
        AIGuardrailPolicyModel.org_id == _org(current_user)
    )
    if active_only:
        q = q.filter(AIGuardrailPolicyModel.is_active == True)  # noqa
    policies = q.order_by(AIGuardrailPolicyModel.priority.desc(),
                          AIGuardrailPolicyModel.created_at.desc()).all()
    return [PolicyOut.model_validate(p) for p in policies]


@router.get("/policies/{policy_id}", response_model=PolicyOut)
def get_policy(
    policy_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    verify_admin_or_governance_role(current_user)
    p = db.query(AIGuardrailPolicyModel).filter(
        AIGuardrailPolicyModel.id     == policy_id,
        AIGuardrailPolicyModel.org_id == _org(current_user),
    ).first()
    if not p:
        raise HTTPException(404, "Policy not found")
    return PolicyOut.model_validate(p)


@router.patch("/policies/{policy_id}", response_model=PolicyOut)
def update_policy(
    policy_id: str,
    body: PolicyUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    verify_admin_or_governance_role(current_user)
    p = db.query(AIGuardrailPolicyModel).filter(
        AIGuardrailPolicyModel.id     == policy_id,
        AIGuardrailPolicyModel.org_id == _org(current_user),
    ).first()
    if not p:
        raise HTTPException(404, "Policy not found")
    for field, val in body.model_dump(exclude_unset=True).items():
        setattr(p, field, val)
    db.commit()
    db.refresh(p)
    return PolicyOut.model_validate(p)


@router.delete("/policies/{policy_id}")
def deactivate_policy(
    policy_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    verify_admin_or_governance_role(current_user)
    p = db.query(AIGuardrailPolicyModel).filter(
        AIGuardrailPolicyModel.id     == policy_id,
        AIGuardrailPolicyModel.org_id == _org(current_user),
    ).first()
    if not p:
        raise HTTPException(404, "Policy not found")
    p.is_active = False
    db.commit()
    return {"ok": True, "deactivated": policy_id}


# ── Audit log ─────────────────────────────────────────────────────────────────

@router.get("/audit-log", response_model=Dict[str, Any])
def get_audit_log(
    module:       Optional[str] = Query(None),
    scope:        Optional[str] = Query(None),
    action_taken: Optional[str] = Query(None),
    was_blocked:  Optional[bool] = Query(None),
    user_id:      Optional[str] = Query(None),
    hours:        int = Query(168, ge=1, le=8760),
    page:         int = Query(1, ge=1),
    page_size:    int = Query(50, ge=1, le=200),
    db: Session        = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    verify_admin_or_governance_role(current_user)
    since = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(hours=hours)

    q = db.query(AIGuardrailAuditLog).filter(
        AIGuardrailAuditLog.org_id       == _org(current_user),
        AIGuardrailAuditLog.evaluated_at >= since,
    )
    if module:       q = q.filter(AIGuardrailAuditLog.module       == module)
    if scope:        q = q.filter(AIGuardrailAuditLog.scope        == scope)
    if action_taken: q = q.filter(AIGuardrailAuditLog.action_taken == action_taken)
    if was_blocked is not None:
        q = q.filter(AIGuardrailAuditLog.was_blocked == was_blocked)
    if user_id:      q = q.filter(AIGuardrailAuditLog.user_id      == user_id)

    total = q.count()
    items = q.order_by(AIGuardrailAuditLog.evaluated_at.desc()) \
             .offset((page - 1) * page_size).limit(page_size).all()
    return {
        "total":     total,
        "page":      page,
        "page_size": page_size,
        "items":     [AuditLogOut.model_validate(r).model_dump() for r in items],
    }


@router.get("/audit-log/stats", summary="PII detection & blocking statistics")
def audit_stats(
    days: int = Query(30, ge=1, le=365),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    verify_admin_or_governance_role(current_user)
    since = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=days)
    org = _org(current_user)

    base = db.query(AIGuardrailAuditLog).filter(
        AIGuardrailAuditLog.org_id       == org,
        AIGuardrailAuditLog.evaluated_at >= since,
    )
    total          = base.count()
    total_blocked  = base.filter(AIGuardrailAuditLog.was_blocked == True).count()  # noqa
    total_redacted = base.filter(AIGuardrailAuditLog.action_taken == "redacted").count()
    total_warned   = base.filter(AIGuardrailAuditLog.action_taken == "warned").count()

    # By module
    by_module = {}
    rows = db.query(
        AIGuardrailAuditLog.module, func.count(AIGuardrailAuditLog.id)
    ).filter(
        AIGuardrailAuditLog.org_id == org,
        AIGuardrailAuditLog.evaluated_at >= since,
    ).group_by(AIGuardrailAuditLog.module).all()
    for module, cnt in rows:
        by_module[module] = cnt

    # Most common PII types (from JSON arrays — computed in Python for SQLite compat)
    pii_counter: Dict[str, int] = {}
    all_pii = db.query(AIGuardrailAuditLog.pii_types_found).filter(
        AIGuardrailAuditLog.org_id       == org,
        AIGuardrailAuditLog.evaluated_at >= since,
        AIGuardrailAuditLog.pii_types_found.isnot(None),
    ).all()
    for (types_list,) in all_pii:
        if isinstance(types_list, list):
            for t in types_list:
                pii_counter[t] = pii_counter.get(t, 0) + 1

    top_pii = sorted(pii_counter.items(), key=lambda x: -x[1])[:10]

    return {
        "window_days":        days,
        "total_evaluations":  total,
        "total_blocked":      total_blocked,
        "total_redacted":     total_redacted,
        "total_warned":       total_warned,
        "block_rate":         round(total_blocked / total, 4) if total else 0,
        "by_module":          by_module,
        "top_pii_types":      [{"type": t, "count": c} for t, c in top_pii],
    }


# ── Interactive check (admin test tool) ──────────────────────────────────────

@router.post("/check/prompt", summary="Test a prompt against active policies")
def test_prompt(
    body: CheckRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    verify_admin_or_governance_role(current_user)
    result = check_prompt(body.text, current_user, body.module, db)
    return {
        "allowed":      result.allowed,
        "action_taken": result.action_taken,
        "redacted_text":result.redacted_text,
        "pii_found":    [{"type": m.entity_type, "value_masked": f"{m.value[:2]}***"} for m in result.pii_found],
        "warnings":     result.warnings,
        "blocked_by":   result.blocked_by,
    }


@router.post("/check/output", summary="Test AI output against active policies")
def test_output(
    body: CheckRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    verify_admin_or_governance_role(current_user)
    result = check_output(body.text, current_user, body.module, db)
    return {
        "allowed":      result.allowed,
        "action_taken": result.action_taken,
        "redacted_text":result.redacted_text,
        "pii_found":    [{"type": m.entity_type, "value_masked": f"{m.value[:2]}***"} for m in result.pii_found],
        "warnings":     result.warnings,
        "blocked_by":   result.blocked_by,
    }


# ── PII type reference ────────────────────────────────────────────────────────

@router.get("/pii-types", summary="List supported PII entity types")
def pii_types():
    return {"pii_types": [label for label, _ in _PII_PATTERNS]}


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
