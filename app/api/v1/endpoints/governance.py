from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.deps import require_admin
from app.db.session import get_db
from app.models.user import User
from app.services.audit import audit_log
import app.services.governance_service as _gsvc

router = APIRouter(prefix="/governance", tags=["Governance"])

DEFAULT_POLICY_PACKS = {
    "access_baseline": {
        "version": "1.0",
        "description": "MFA, least privilege y revisión periódica de accesos",
        "controls": ["SOC2-CC6.1", "SOC2-CC6.2", "ISO27001-A.9.2"],
    },
    "password_strict": {
        "version": "1.0",
        "description": "Política de contraseñas robusta y lockout",
        "controls": ["SOC2-CC6.3", "ISO27001-A.5.17"],
    },
    "audit_retention": {
        "version": "1.0",
        "description": "Retención de evidencias y trazabilidad de auditoría",
        "controls": ["SOC2-CC7.2", "ISO27001-A.5.33"],
    },
}

CONTROL_CATALOG = {
    "SOC2": [
        {"control_id": "SOC2-CC6.1", "title": "Logical Access Controls"},
        {"control_id": "SOC2-CC6.2", "title": "Authentication Hardening"},
        {"control_id": "SOC2-CC7.2", "title": "Monitoring and Logging"},
    ],
    "ISO27001": [
        {"control_id": "ISO27001-A.5.17", "title": "Authentication Information"},
        {"control_id": "ISO27001-A.9.2", "title": "User Access Provisioning"},
        {"control_id": "ISO27001-A.5.33", "title": "Protection of Records"},
    ],
}


class PolicyPackUpsert(BaseModel):
    is_enabled: bool = True
    pack_version: str = "1.0"
    config: Optional[dict] = None


class EvidenceCreate(BaseModel):
    framework: str
    control_id: str
    evidence_type: str
    title: str
    description: Optional[str] = None
    artifact_uri: Optional[str] = None
    metadata: Optional[dict] = None


def _org_id(current_user: User) -> str:
    if not current_user.organization_id:
        raise HTTPException(400, "El usuario no pertenece a una organización/tenant")
    return current_user.organization_id


@router.get("/policy-packs", summary="Listar policy packs por tenant")
def list_policy_packs(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    organization_id = _org_id(current_user)
    rows = _gsvc.list_tenant_policy_packs(db, organization_id)
    by_key = {r.pack_key: r for r in rows}
    out = []
    for pack_key, baseline in DEFAULT_POLICY_PACKS.items():
        row = by_key.get(pack_key)
        out.append({
            "pack_key": pack_key,
            "description": baseline["description"],
            "baseline_controls": baseline["controls"],
            "is_enabled": row.is_enabled if row else True,
            "pack_version": row.pack_version if row else baseline["version"],
            "config": json.loads(row.config_json) if row and row.config_json else {},
            "updated_at": row.updated_at if row else None,
        })
    return out


@router.put("/policy-packs/{pack_key}", summary="Activar/configurar un policy pack del tenant")
def upsert_policy_pack(
    pack_key: str,
    payload: PolicyPackUpsert,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    if pack_key not in DEFAULT_POLICY_PACKS:
        raise HTTPException(404, "Policy pack no reconocido")
    organization_id = _org_id(current_user)
    row = _gsvc.upsert_policy_pack(
        db,
        organization_id=organization_id,
        pack_key=pack_key,
        pack_version=payload.pack_version,
        is_enabled=payload.is_enabled,
        config=payload.config,
        updated_by=current_user.id,
    )
    audit_log(
        db=db,
        user=current_user,
        action="UPDATE",
        resource="tenant_policy_packs",
        resource_id=row.id,
        resource_name=pack_key,
        new_values={"enabled": payload.is_enabled, "version": payload.pack_version},
    )
    return {"ok": True, "pack_key": pack_key}


@router.post("/compliance/evidence", summary="Registrar evidencia de compliance")
def create_evidence(
    payload: EvidenceCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    organization_id = _org_id(current_user)
    framework = payload.framework.upper()
    if framework not in CONTROL_CATALOG:
        raise HTTPException(400, "Framework no soportado. Usa SOC2 o ISO27001")

    artifact_hash = None
    if payload.artifact_uri:
        artifact_hash = hashlib.sha256(payload.artifact_uri.encode()).hexdigest()

    evidence = _gsvc.create_compliance_evidence(
        db,
        organization_id=organization_id,
        framework=framework,
        control_id=payload.control_id,
        evidence_type=payload.evidence_type,
        title=payload.title,
        description=payload.description,
        artifact_uri=payload.artifact_uri,
        artifact_hash=artifact_hash,
        metadata_json=json.dumps(payload.metadata or {}),
        created_by=current_user.id,
    )
    audit_log(
        db=db,
        user=current_user,
        action="CREATE",
        resource="compliance_evidence",
        resource_id=evidence.id,
        resource_name=payload.control_id,
        new_values={"framework": framework, "type": payload.evidence_type},
    )
    return {"id": evidence.id, "artifact_hash": evidence.artifact_hash}


@router.get("/compliance/evidence", summary="Listar evidencias SOC2/ISO del tenant")
def list_evidence(
    framework: Optional[str] = Query(default=None),
    control_id: Optional[str] = Query(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    organization_id = _org_id(current_user)
    rows = _gsvc.list_compliance_evidence(
        db,
        organization_id=organization_id,
        framework=framework.upper() if framework else None,
        control_id=control_id,
    )
    return [
        {
            "id": r.id,
            "framework": r.framework,
            "control_id": r.control_id,
            "evidence_type": r.evidence_type,
            "title": r.title,
            "artifact_uri": r.artifact_uri,
            "artifact_hash": r.artifact_hash,
            "created_at": r.created_at,
        }
        for r in rows
    ]


@router.get("/compliance/controls/status", summary="Estado de controles SOC2/ISO con evidencia")
def compliance_control_status(
    framework: str = Query(default="SOC2"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    organization_id = _org_id(current_user)
    fw = framework.upper()
    controls = CONTROL_CATALOG.get(fw)
    if controls is None:
        raise HTTPException(400, "Framework no soportado. Usa SOC2 o ISO27001")

    evidences = _gsvc.get_evidences_by_framework(db, organization_id=organization_id, framework=fw)
    by_control: dict[str, int] = {}
    for e in evidences:
        by_control[e.control_id] = by_control.get(e.control_id, 0) + 1

    rows = []
    for c in controls:
        evidence_count = by_control.get(c["control_id"], 0)
        status = "pass" if evidence_count > 0 else "attention"
        rows.append({
            "control_id": c["control_id"],
            "title": c["title"],
            "status": status,
            "evidence_count": evidence_count,
        })

    return {
        "framework": fw,
        "organization_id": organization_id,
        "generated_at": datetime.now(timezone.utc),
        "platform_security_baseline": {
            "mfa_enforced": True,
            "password_policy_min_length": settings.MIN_PASSWORD_LENGTH,
            "key_rotation_enabled": settings.KEY_ROTATION_ENABLED,
            "audit_log_enabled": True,
        },
        "controls": rows,
    }
