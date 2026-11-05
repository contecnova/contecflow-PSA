from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from app.schemas.governance import PolicyPackUpsert, EvidenceCreate
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.deps import require_admin
from app.core.responses import APIListResponse, APIResponse
from app.db.session import get_db
from app.models.user import User
from app.services.audit import audit_log
import app.services.governance_service as _gsvc
_org_id = _gsvc.get_org_id

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






# _org_id delegated to _gsvc.get_org_id (see import above)


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
    return APIListResponse.ok(items=out)


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
    return APIResponse.ok(data={"ok": True, "pack_key": pack_key})


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
    return APIResponse.ok(data={"id": evidence.id, "artifact_hash": evidence.artifact_hash})


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
    items = [
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
    return APIListResponse.ok(items=items)


def _linea_base_medida(db, org) -> dict:
    from app.services.informe_de_cumplimiento import generar
    c = {x["id"]: x["measured"] for x in generar(db, org)["controls"]}
    return {"mfa_enforced": c["mfa_required"]["require_mfa"],
            "password_policy_min_length": c["password_policy"]["min_length"],
            "key_rotation_enabled": c["secrets_encryption"]["key_rotation_enabled"],
            "audit_log_enabled": c["audit_chain"]["rows_checked"] > 0,
            "audit_chain_ok": c["audit_chain"]["ok"]}


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

    return APIResponse.ok(data={
        "framework": fw,
        "organization_id": organization_id,
        "generated_at": datetime.now(timezone.utc),
        # Revisión 2026-11: antes `mfa_enforced` y `audit_log_enabled` eran
        # `True` escritos a mano. Ahora salen del informe medido.
        "platform_security_baseline": _linea_base_medida(db, organization_id),
        "controls": rows,
    })


# ── Retención y bloqueo legal (revisión 2026-11) ─────────────────────────────
class PoliticaIn(BaseModel):
    keep_days: int = Field(..., ge=1, le=36500)
    is_active: bool = False


class BloqueoIn(BaseModel):
    case_reference: str = Field(..., min_length=2, max_length=120)
    reason: Optional[str] = Field(None, max_length=2000)
    entity: str = Field("*", max_length=40)
    field: str = Field(..., max_length=60)
    value: str = Field(..., min_length=1, max_length=255)


@router.get("/retention/policies", summary="Políticas de retención de la empresa (admin)")
def retention_policies(db: Session = Depends(get_db), current_user: User = Depends(require_admin)):
    from app.services import retencion
    return APIResponse.ok(data={"policies": retencion.politicas(db, current_user.organization_id),
                                "min_days": retencion.minimo_de_dias(db, current_user.organization_id)})


@router.put("/retention/policies/{entity}", summary="Guardar la política de un tipo (admin)")
def save_retention_policy(entity: str, payload: PoliticaIn, db: Session = Depends(get_db),
                          current_user: User = Depends(require_admin)):
    from app.services import retencion
    return APIResponse.ok(data=retencion.guardar_politica(db, current_user.organization_id, current_user, entity,
                                                          payload.keep_days, payload.is_active))


@router.get("/retention/preview", summary="Cuánto borraría hoy una política (admin)")
def retention_preview(entity: str, keep_days: int = Query(..., ge=1, le=36500), db: Session = Depends(get_db),
                      current_user: User = Depends(require_admin)):
    from app.services import retencion
    if entity not in retencion.TIPOS:
        raise HTTPException(422, f"Tipo desconocido: {entity}")
    return APIResponse.ok(data=retencion.vista_previa(db, current_user.organization_id, entity, keep_days))


@router.post("/retention/run", summary="Aplicar ahora las políticas activas (admin)")
def retention_run(db: Session = Depends(get_db), current_user: User = Depends(require_admin)):
    from app.services import retencion
    return APIResponse.ok(data=retencion.aplicar(db, current_user.organization_id, current_user))


@router.get("/legal-holds", summary="Bloqueos legales de la empresa (admin)")
def legal_holds(db: Session = Depends(get_db), current_user: User = Depends(require_admin)):
    from app.db.session import sin_filtro_de_tenant
    from app.models.governance import LegalHold
    with sin_filtro_de_tenant(db):
        filas = db.query(LegalHold).filter(LegalHold.organization_id == current_user.organization_id) \
            .order_by(LegalHold.created_at.desc()).all()
    return APIResponse.ok(data=[{
        "id": h.id, "case_reference": h.case_reference, "reason": h.reason, "entity": h.entity, "field": h.field,
        "value": h.value, "is_active": h.is_active, "created_at": h.created_at, "released_at": h.released_at,
    } for h in filas])


@router.post("/legal-holds", summary="Crear un bloqueo legal (admin)")
def create_legal_hold(payload: BloqueoIn, db: Session = Depends(get_db), current_user: User = Depends(require_admin)):
    from app.models.governance import LegalHold
    from app.services import retencion
    from app.services.audit import audit_log
    retencion.validar_bloqueo(payload.entity, payload.field)
    h = LegalHold(organization_id=current_user.organization_id, created_by=current_user.id, **payload.model_dump())
    db.add(h)
    db.flush()
    audit_log(db, current_user, "LEGAL_HOLD", "legal_hold", h.id, h.case_reference, new_values=payload.model_dump())
    db.commit()
    return APIResponse.ok(data={"id": h.id})


@router.post("/legal-holds/{hold_id}/release", summary="Levantar un bloqueo legal (admin)")
def release_legal_hold(hold_id: str, db: Session = Depends(get_db), current_user: User = Depends(require_admin)):
    from app.db.session import sin_filtro_de_tenant
    from app.models.governance import LegalHold
    from app.services.audit import audit_log
    with sin_filtro_de_tenant(db):
        h = db.query(LegalHold).filter(LegalHold.id == hold_id,
                                       LegalHold.organization_id == current_user.organization_id).first()
    if h is None:
        raise HTTPException(404, "No existe")
    h.is_active, h.released_at, h.released_by = False, datetime.now(timezone.utc), current_user.id
    audit_log(db, current_user, "LEGAL_HOLD_RELEASED", "legal_hold", h.id, h.case_reference)
    db.commit()
    return APIResponse.ok(data={"id": h.id, "is_active": False})


# ── AI module governance ───────────────────────────────────────────────────────

AI_MODULES = [
    "nexusassist", "nexusagent", "nexusoracle", "meeting_assistant",
    "sprint_planning", "contract_intelligence", "knowledge_base", "portal_ai", "voice",
    "mcp",
]
#: Sin fila, apagados: abren una puerta hacia fuera (revisión 2026-11).
APAGADOS_SIN_CONFIGURAR = {"mcp"}


@router.get("/config", summary="Configuración de módulos de IA gobernados")
def get_ai_module_config(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    rows = _gsvc.list_ai_module_configs(db, _org_id(current_user, strict=False))
    by_module = {r.module: r for r in rows}
    return APIListResponse.ok(items=[
        {
            "module": m,
            "is_enabled": by_module[m].is_enabled if m in by_module else m not in APAGADOS_SIN_CONFIGURAR,
        }
        for m in AI_MODULES
    ])


@router.patch("/config/{module}", summary="Activar/desactivar módulo de IA")
def patch_ai_module_config(
    module: str,
    payload: dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    if module not in AI_MODULES:
        raise HTTPException(404, "Módulo no reconocido")
    is_enabled = payload.get("is_enabled", True)
    _gsvc.upsert_ai_module_config(db, _org_id(current_user), module, is_enabled, current_user.id)
    audit_log(db=db, user=current_user, action="UPDATE", resource="ai_module_config",
              resource_id=None, resource_name=module, new_values={"is_enabled": is_enabled})
    return APIResponse.ok(data={"ok": True, "module": module, "is_enabled": is_enabled})


@router.get("/stats", summary="Estadísticas de uso de módulos de IA")
def get_ai_governance_stats(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    stats = _gsvc.get_ai_usage_stats(db, _org_id(current_user, strict=False))
    return APIResponse.ok(data=stats)


@router.get("/logs", summary="Historial de llamadas a módulos de IA gobernados")
def get_ai_governance_logs(
    limit: int = Query(default=100, le=500),
    module: Optional[str] = Query(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    logs = _gsvc.list_ai_governance_logs(db, _org_id(current_user, strict=False), limit=limit, module=module)
    return APIListResponse.ok(items=logs)
