from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.governance import ComplianceEvidence, TenantPolicyPack
from app.models.ai_chat import AIGovernanceConfig, AIActionLog
from fastapi import HTTPException
import logging

logger = logging.getLogger(__name__)


def list_tenant_policy_packs(db: Session, organization_id: str) -> list[TenantPolicyPack]:
    return (
        db.query(TenantPolicyPack)
        .filter(TenantPolicyPack.organization_id == organization_id)
        .all()
    )


def upsert_policy_pack(
    db: Session,
    organization_id: str,
    pack_key: str,
    pack_version: str,
    is_enabled: bool,
    config: Optional[dict],
    updated_by: str,
) -> TenantPolicyPack:
    row = (
        db.query(TenantPolicyPack)
        .filter(
            TenantPolicyPack.organization_id == organization_id,
            TenantPolicyPack.pack_key == pack_key,
        )
        .first()
    )
    if row is None:
        row = TenantPolicyPack(
            organization_id=organization_id,
            pack_key=pack_key,
            pack_version=pack_version,
            is_enabled=is_enabled,
            config_json=json.dumps(config or {}),
            updated_by=updated_by,
        )
        db.add(row)
    else:
        row.pack_version = pack_version
        row.is_enabled = is_enabled
        row.config_json = json.dumps(config or {})
        row.updated_by = updated_by
        row.updated_at = datetime.now(timezone.utc)
    db.commit()
    return row


def create_compliance_evidence(
    db: Session,
    organization_id: str,
    framework: str,
    control_id: str,
    evidence_type: str,
    title: str,
    description: Optional[str],
    artifact_uri: Optional[str],
    artifact_hash: Optional[str],
    metadata_json: str,
    created_by: str,
) -> ComplianceEvidence:
    evidence = ComplianceEvidence(
        organization_id=organization_id,
        framework=framework,
        control_id=control_id,
        evidence_type=evidence_type,
        title=title,
        description=description,
        artifact_uri=artifact_uri,
        artifact_hash=artifact_hash,
        metadata_json=metadata_json,
        created_by=created_by,
    )
    db.add(evidence)
    db.commit()
    db.refresh(evidence)
    return evidence


def list_compliance_evidence(
    db: Session,
    organization_id: str,
    framework: Optional[str] = None,
    control_id: Optional[str] = None,
) -> list[ComplianceEvidence]:
    q = db.query(ComplianceEvidence).filter(
        ComplianceEvidence.organization_id == organization_id
    )
    if framework:
        q = q.filter(ComplianceEvidence.framework == framework)
    if control_id:
        q = q.filter(ComplianceEvidence.control_id == control_id)
    return q.order_by(ComplianceEvidence.created_at.desc()).all()


def get_evidences_by_framework(
    db: Session,
    organization_id: str,
    framework: str,
) -> list[ComplianceEvidence]:
    return (
        db.query(ComplianceEvidence)
        .filter(
            ComplianceEvidence.organization_id == organization_id,
            ComplianceEvidence.framework == framework,
        )
        .all()
    )


# ── Tenant helpers ────────────────────────────────────────────────────────────

def get_org_id(user, *, strict: bool = True) -> Optional[str]:
    """Resolve tenant context for governance endpoints.

    strict=True keeps legacy behavior for tenant-bound operations.
    strict=False allows read-only/global views to return defaults instead of 400.
    """
    if user.organization_id:
        return user.organization_id
    if strict:
        raise HTTPException(400, "El usuario no pertenece a una organización/tenant")
    return None


# ── AI module governance ──────────────────────────────────────────────────────

def list_ai_module_configs(db: Session, organization_id: str) -> list[AIGovernanceConfig]:
    return db.query(AIGovernanceConfig).all()


def upsert_ai_module_config(
    db: Session,
    organization_id: str,
    module: str,
    is_enabled: bool,
    updated_by: str,
) -> AIGovernanceConfig:
    row = db.query(AIGovernanceConfig).filter(AIGovernanceConfig.module == module).first()
    if row is None:
        row = AIGovernanceConfig(module=module, is_enabled=is_enabled, updated_by=updated_by)
        db.add(row)
    else:
        row.is_enabled = is_enabled
        row.updated_by = updated_by
    db.commit()
    return row


def get_ai_usage_stats(db: Session, organization_id: str) -> dict:
    total_calls = db.query(func.count(AIActionLog.id)).scalar() or 0
    total_tokens = db.query(func.sum(AIActionLog.tokens_used)).scalar() or 0
    rows = (
        db.query(AIActionLog.module, func.count(AIActionLog.id), func.sum(AIActionLog.tokens_used))
        .group_by(AIActionLog.module)
        .all()
    )
    by_module = {r[0]: {"calls": r[1] or 0, "tokens": r[2] or 0} for r in rows}
    return {"total_calls": total_calls, "total_tokens": total_tokens, "by_module": by_module}


def list_ai_governance_logs(
    db: Session,
    organization_id: str,
    limit: int = 100,
    module: Optional[str] = None,
) -> list[dict]:
    q = db.query(AIActionLog)
    if module:
        q = q.filter(AIActionLog.module == module)
    rows = q.order_by(AIActionLog.created_at.desc()).limit(limit).all()
    return [
        {
            "id": r.id,
            "module": r.module,
            "action_type": r.action_type,
            "status": r.status,
            "tokens_used": r.tokens_used,
            "created_at": r.created_at,
            "user_id": r.user_id,
        }
        for r in rows
    ]
