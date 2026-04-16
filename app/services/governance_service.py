from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

from app.models.governance import ComplianceEvidence, TenantPolicyPack


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
