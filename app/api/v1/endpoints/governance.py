from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from app.schemas.governance import PolicyPackUpsert, EvidenceCreate
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.deps import require_admin
from app.core.paginacion import Paginacion, lista_paginada, paginacion
from app.core.responses import APIListResponse, APIResponse
from app.db.session import get_db
from app.models.user import User
from app.services.audit import auditar_y_confirmar
import app.services.governance_service as _gsvc
from app.core.codigos_de_error import error_http
_org_id = _gsvc.get_org_id

router = APIRouter(prefix="/governance", tags=["Governance"])

# Revisión GRC 16-11-2026: el catálogo de controles y los paquetes viven en
# app/core/marcos_de_cumplimiento.py (una fuente, edición ISO 27001:2022).
from app.core import marcos_de_cumplimiento as marcos  # noqa: E402
DEFAULT_POLICY_PACKS = marcos.PAQUETES


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
        raise error_http(404, "policy_pack_no_reconocido", detail="Policy pack no reconocido")
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
    auditar_y_confirmar(
        db=db,
        user=current_user,
        action="UPDATE",
        resource="tenant_policy_packs",
        resource_id=row.id,
        resource_name=pack_key,
        new_values={"enabled": payload.is_enabled, "version": payload.pack_version},
    )
    return APIResponse.ok(data={"ok": True, "pack_key": pack_key})


def _marco(framework: str) -> str:
    fw = framework.upper()
    if fw not in marcos.CONTROLES:
        raise error_http(422, "framework_no_soportado", detail=f"Framework no soportado. Usa {' o '.join(marcos.CONTROLES)}", opciones=' o '.join(marcos.CONTROLES))
    return fw


@router.get("/compliance/frameworks", summary="Marcos, controles y tipos de evidencia admitidos")
def compliance_frameworks(current_user: User = Depends(require_admin)):
    return APIResponse.ok(data={"frameworks": {fw: list(ids) for fw, ids in marcos.CONTROLES.items()},
                                "evidence_types": list(marcos.TIPOS_DE_EVIDENCIA)})


@router.post("/compliance/evidence", summary="Registrar evidencia de compliance")
def create_evidence(
    payload: EvidenceCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    organization_id = _org_id(current_user)
    framework = _marco(payload.framework)
    # Revisión GRC 16-11-2026: el control se comprobaba contra nada (se podía
    # registrar evidencia para un control inexistente, que no contaba en ningún
    # estado) y `artifact_hash` era el SHA-256 del TEXTO de la URI, no del
    # artefacto: no probaba la integridad de nada. Ahora el hash lo da quien
    # tiene el fichero (`artifact_sha256`) o no se guarda.
    control_id = marcos.canonico(payload.control_id)
    if control_id not in marcos.CONTROLES[framework]:
        raise error_http(422, "control_desconocido", marco=framework, control=payload.control_id)

    evidence = _gsvc.create_compliance_evidence(
        db,
        organization_id=organization_id,
        framework=framework,
        control_id=control_id,
        evidence_type=payload.evidence_type,
        title=payload.title,
        description=payload.description,
        artifact_uri=payload.artifact_uri,
        artifact_hash=payload.artifact_sha256.lower() if payload.artifact_sha256 else None,
        metadata_json=json.dumps(payload.metadata or {}),
        created_by=current_user.id,
    )
    auditar_y_confirmar(
        db=db,
        user=current_user,
        action="CREATE",
        resource="compliance_evidence",
        resource_id=evidence.id,
        resource_name=control_id,
        new_values={"framework": framework, "type": payload.evidence_type},
    )
    return APIResponse.ok(data={"id": evidence.id, "artifact_hash": evidence.artifact_hash})


@router.get("/compliance/evidence", summary="Listar evidencias SOC2/ISO del tenant")
def list_evidence(
    framework: Optional[str] = Query(default=None, max_length=30),
    control_id: Optional[str] = Query(default=None, max_length=50),
    response: Response = None,
    pagina: Paginacion = Depends(paginacion),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    organization_id = _org_id(current_user)
    rows = _gsvc.list_compliance_evidence(
        db,
        organization_id=organization_id,
        framework=framework.upper() if framework else None,
        control_ids=marcos.con_alias(marcos.canonico(control_id)) if control_id else None,
        pagina=pagina,
    )
    return lista_paginada(response, rows.mapear(lambda r: {
            "id": r.id,
            "framework": r.framework,
            "control_id": marcos.canonico(r.control_id),
            "evidence_type": r.evidence_type,
            "title": r.title,
            "description": r.description,
            "artifact_uri": r.artifact_uri,
            "artifact_hash": r.artifact_hash,
            "created_at": r.created_at,
        }))


def _medidos_por_control(informe: dict) -> dict[str, list[dict]]:
    """Controles del informe medido agrupados por la referencia del marco que citan."""
    salida: dict[str, list[dict]] = {}
    for c in informe["controls"]:
        for ref in c["frameworks"]:
            salida.setdefault(marcos.del_informe(ref), []).append({"id": c["id"], "status": c["status"]})
    return salida


def _linea_base_medida(informe: dict) -> dict:
    c = {x["id"]: x["measured"] for x in informe["controls"]}
    return {"mfa_enforced": c["mfa_required"]["require_mfa"],
            "password_policy_min_length": c["password_policy"]["min_length"],
            "key_rotation_enabled": c["secrets_encryption"]["key_rotation_enabled"],
            "audit_log_enabled": c["audit_chain"]["rows_checked"] > 0,
            "audit_chain_ok": c["audit_chain"]["ok"]}


@router.get("/compliance/controls/status", summary="Estado de controles SOC2/ISO con evidencia")
def compliance_control_status(
    framework: str = Query(default="SOC2", max_length=30),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    from app.services.informe_de_cumplimiento import generar
    organization_id = _org_id(current_user)
    fw = _marco(framework)
    evidencias: dict[str, int] = {}
    for cid, n in _gsvc.count_evidences_by_control(db, organization_id=organization_id, framework=fw).items():
        evidencias[marcos.canonico(cid)] = evidencias.get(marcos.canonico(cid), 0) + n
    informe = generar(db, organization_id)
    medidos = _medidos_por_control(informe)

    # Revisión GRC 16-11-2026: antes «pass» era «hay al menos una evidencia
    # subida», aunque el sistema midiera ese mismo control en rojo (p. ej.
    # SOC2-CC6.1 con MFA sin exigir). Ahora un control medido en «attention»
    # pide atención aunque tenga evidencias; sin nada medido, decide la
    # evidencia manual.
    rows = []
    for cid in marcos.CONTROLES[fw]:
        evidence_count = evidencias.get(cid, 0)
        medido = medidos.get(cid, [])
        if any(m["status"] == "attention" for m in medido):
            status = "attention"
        elif evidence_count > 0 or any(m["status"] == "pass" for m in medido):
            status = "pass"
        else:
            status = "attention"
        rows.append({
            "control_id": cid,
            "status": status,
            "evidence_count": evidence_count,
            "measured": medido,
        })

    return APIResponse.ok(data={
        "framework": fw,
        "organization_id": organization_id,
        "generated_at": datetime.now(timezone.utc),
        # Revisión 2026-11: antes `mfa_enforced` y `audit_log_enabled` eran
        # `True` escritos a mano. Ahora salen del informe medido.
        "platform_security_baseline": _linea_base_medida(informe),
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
        raise error_http(422, "tipo_desconocido", tipo=entity)
    return APIResponse.ok(data=retencion.vista_previa(db, current_user.organization_id, entity, keep_days))


@router.post("/retention/run", summary="Aplicar ahora las políticas activas (admin)")
def retention_run(db: Session = Depends(get_db), current_user: User = Depends(require_admin)):
    from app.services import retencion
    return APIResponse.ok(data=retencion.aplicar(db, current_user.organization_id, current_user))


@router.get("/legal-holds", summary="Bloqueos legales de la empresa (admin)")
def legal_holds(db: Session = Depends(get_db), current_user: User = Depends(require_admin)):
    from app.services import retencion
    return APIResponse.ok(data=retencion.lista_de_bloqueos(db, current_user.organization_id))


@router.post("/legal-holds", summary="Crear un bloqueo legal (admin)")
def create_legal_hold(payload: BloqueoIn, db: Session = Depends(get_db), current_user: User = Depends(require_admin)):
    from app.services import retencion
    return APIResponse.ok(data={"id": retencion.crear_bloqueo(db, current_user, payload.model_dump())})


@router.post("/legal-holds/{hold_id}/release", summary="Levantar un bloqueo legal (admin)")
def release_legal_hold(hold_id: str, db: Session = Depends(get_db), current_user: User = Depends(require_admin)):
    from app.services import retencion
    retencion.levantar_bloqueo(db, current_user, hold_id)
    return APIResponse.ok(data={"id": hold_id, "is_active": False})


# ── AI module governance ───────────────────────────────────────────────────────

AI_MODULES = [
    "nexusassist", "nexusagent", "nexusoracle", "meeting_assistant",
    "contract_intelligence", "knowledge_base", "portal_ai", "voice",
    "mcp",
]
APAGADOS_SIN_CONFIGURAR = _gsvc.APAGADOS_SIN_CONFIGURAR


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


class ModuloDeIaIn(BaseModel):
    is_enabled: bool = True


@router.patch("/config/{module}", summary="Activar/desactivar módulo de IA")
def patch_ai_module_config(
    module: str,
    payload: ModuloDeIaIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    if module not in AI_MODULES:
        raise error_http(404, "modulo_no_reconocido")
    # Revisión GRC 16-11-2026: era un `dict` y cualquier valor se guardaba
    # tal cual en una columna booleana.
    is_enabled = payload.is_enabled
    _gsvc.upsert_ai_module_config(db, _org_id(current_user), module, is_enabled, current_user.id)
    auditar_y_confirmar(db=db, user=current_user, action="UPDATE", resource="ai_module_config",
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
