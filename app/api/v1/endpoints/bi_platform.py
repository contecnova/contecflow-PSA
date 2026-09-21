"""BI Platform endpoints.

Platform-scale APIs: embedded SDK, connector marketplace, custom connector
framework, governance lineage, and dataset versioning.
"""
from __future__ import annotations

from datetime import timedelta
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, require_admin
from app.core.responses import APIListResponse, APIResponse
from app.core.security import create_access_token
from app.db.session import get_db
from app.models.user import User
from app.core.abac_enforce import enforce_abac
from app.services import bi_platform_service as svc

router = APIRouter()


class EmbedSettingsPatchIn(BaseModel):
    allowed_origins: Optional[list[str]] = None
    default_theme: Optional[str] = Field(None, max_length=30)
    allow_export: Optional[bool] = None
    allow_drilldown: Optional[bool] = None
    token_ttl_minutes: Optional[int] = Field(None, ge=5, le=1440)


class EmbedTokenIn(BaseModel):
    dashboard_key: str = Field(..., min_length=2, max_length=120)
    external_user_id: Optional[str] = Field(None, max_length=120)
    expires_minutes: int = Field(60, ge=5, le=1440)


class ConnectorPatchIn(BaseModel):
    enabled: Optional[bool] = None
    status: Optional[str] = Field(None, pattern="^(available|active|error|disabled)$")


class CustomConnectorIn(BaseModel):
    name: str = Field(..., min_length=2, max_length=120)
    kind: str = Field("rest", min_length=2, max_length=30)
    endpoint: str = Field(..., min_length=8, max_length=500)
    auth_type: str = Field("api_key", min_length=2, max_length=40)
    enabled: bool = True


class LineageEdgeIn(BaseModel):
    source_table: str = Field(..., min_length=2, max_length=120)
    target_table: str = Field(..., min_length=2, max_length=120)
    transformation_sql: str = Field(..., min_length=2, max_length=4000)


class AccessAuditIn(BaseModel):
    entity_type: str = Field(..., min_length=2, max_length=40)
    entity_id: str = Field(..., min_length=1, max_length=120)
    action: str = Field(..., min_length=2, max_length=40)
    extra: Optional[dict[str, Any]] = None


class DatasetSnapshotIn(BaseModel):
    payload: dict[str, Any]


class FieldSensitivityIn(BaseModel):
    dataset_id: str = Field(..., min_length=1, max_length=120)
    field_name: str = Field(..., min_length=1, max_length=120)
    sensitivity_level: str = Field(..., pattern="^(public|internal|confidential|restricted)$")
    pii_types: Optional[list[str]] = Field(default_factory=list)
    requires_approval: bool = False


@router.get("/bi/platform/embed/sdk", summary="Manifest del SDK embebido BI Platform")
def phase3_embed_sdk(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    org_id = getattr(current_user, "organization_id", None)
    return APIResponse.ok(data=svc.get_sdk_manifest(db, organization_id=org_id))


@router.get("/bi/platform/embed/settings", summary="Configuración embed BI Platform")
def phase3_embed_settings(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    org_id = getattr(current_user, "organization_id", None)
    return APIResponse.ok(data=svc.get_embed_settings(db, organization_id=org_id))


@router.patch("/bi/platform/embed/settings", summary="Actualizar configuración embed BI Platform")
def phase3_patch_embed_settings(
    payload: EmbedSettingsPatchIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _rol: User = Depends(require_admin),  # auditoria 2026-09: sensible: plataforma de datos
):
    org_id = getattr(current_user, "organization_id", None)
    data = {k: v for k, v in payload.model_dump().items() if v is not None}
    return APIResponse.ok(data=svc.update_embed_settings(db, organization_id=org_id, payload=data))


@router.post("/bi/platform/embed/token", summary="Emitir token SSO para embed BI")
def phase3_embed_token(
    payload: EmbedTokenIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _rol: User = Depends(require_admin),  # auditoria 2026-09: sensible: plataforma de datos
):
    org_id = getattr(current_user, "organization_id", None)
    settings = svc.get_embed_settings(db, organization_id=org_id)
    token = create_access_token(
        subject=current_user.id,
        extra={
            "bi_embed": True,
            "dashboard_key": payload.dashboard_key,
            "external_user_id": payload.external_user_id,
            "organization_id": org_id,
        },
        expires_delta=timedelta(minutes=payload.expires_minutes),
    )
    return APIResponse.ok(data={
        "token": token,
        "expires_minutes": payload.expires_minutes,
        "dashboard_key": payload.dashboard_key,
        "settings": settings,
    })


@router.get("/bi/platform/connectors/catalog", summary="Catálogo de conectores BI Platform (20+)")
def phase3_connector_catalog(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    org_id = getattr(current_user, "organization_id", None)
    catalog = svc.get_connector_catalog(db, organization_id=org_id)
    return APIResponse.ok(data={"count": len(catalog), "items": catalog})


@router.patch("/bi/platform/connectors/catalog/{connector}", summary="Actualizar estado de conector catálogo")
def phase3_patch_connector_catalog(
    connector: str,
    payload: ConnectorPatchIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _rol: User = Depends(require_admin),  # auditoria 2026-09: sensible: plataforma de datos
):
    org_id = getattr(current_user, "organization_id", None)
    data = {k: v for k, v in payload.model_dump().items() if v is not None}
    try:
        row = svc.patch_connector_catalog(
            db,
            organization_id=org_id,
            connector=connector,
            payload=data,
        )
        return APIResponse.ok(data={"ok": True, "connector": connector, "config": row})
    except ValueError:
        raise HTTPException(status_code=404, detail="Conector no encontrado")


@router.get("/bi/platform/connectors/custom", summary="Listar conectores custom")
def phase3_list_custom_connectors(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    org_id = getattr(current_user, "organization_id", None)
    return APIListResponse.ok(items=svc.list_custom_connectors(db, organization_id=org_id))


@router.post("/bi/platform/connectors/custom", summary="Crear conector custom")
def phase3_create_custom_connector(
    payload: CustomConnectorIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _rol: User = Depends(require_admin),  # auditoria 2026-09: sensible: plataforma de datos
):
    org_id = getattr(current_user, "organization_id", None)
    try:
        row = svc.create_custom_connector(
            db,
            organization_id=org_id,
            payload=payload.model_dump(),
            current_user=current_user,
        )
        return APIResponse.ok(data={"ok": True, "connector": row})
    except ValueError:
        raise HTTPException(status_code=400, detail="Payload de conector inválido")


@router.delete("/bi/platform/connectors/custom/{connector_id}", summary="Eliminar conector custom")
def phase3_delete_custom_connector(
    connector_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _rol: User = Depends(require_admin),  # auditoria 2026-09: sensible: plataforma de datos
):
    enforce_abac(db, current_user, "bi_custom_connector", connector_id, action="delete")
    org_id = getattr(current_user, "organization_id", None)
    deleted = svc.delete_custom_connector(db, organization_id=org_id, connector_id=connector_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Conector custom no encontrado")
    return APIResponse.ok(data={"ok": True})


@router.post("/bi/platform/connectors/custom/{connector_id}/test", summary="Test de conector custom")
def phase3_test_custom_connector(
    connector_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _rol: User = Depends(require_admin),  # auditoria 2026-09: sensible: plataforma de datos
):
    org_id = getattr(current_user, "organization_id", None)
    try:
        return APIResponse.ok(data=svc.test_custom_connector(db, organization_id=org_id, connector_id=connector_id))
    except ValueError:
        raise HTTPException(status_code=404, detail="Conector custom no encontrado")


@router.get("/bi/platform/governance/lineage", summary="Lineage + auditoría BI Platform")
def phase3_governance_lineage(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    org_id = getattr(current_user, "organization_id", None)
    return APIResponse.ok(data=svc.get_lineage(db, organization_id=org_id))


@router.post("/bi/platform/governance/lineage/edges", summary="Crear/actualizar edge de lineage")
def phase3_upsert_lineage_edge(
    payload: LineageEdgeIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _rol: User = Depends(require_admin),  # auditoria 2026-09: sensible: plataforma de datos
):
    org_id = getattr(current_user, "organization_id", None)
    return APIResponse.ok(data=svc.upsert_lineage_edge(
        db,
        organization_id=org_id,
        source_table=payload.source_table,
        target_table=payload.target_table,
        transformation_sql=payload.transformation_sql,
        current_user=current_user,
    ))


@router.post("/bi/platform/governance/audit/access", summary="Registrar acceso en auditoría BI")
def phase3_log_access(
    payload: AccessAuditIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _rol: User = Depends(require_admin),  # auditoria 2026-09: sensible: plataforma de datos
):
    org_id = getattr(current_user, "organization_id", None)
    return APIResponse.ok(data=svc.log_access_event(
        db,
        organization_id=org_id,
        current_user=current_user,
        entity_type=payload.entity_type,
        entity_id=payload.entity_id,
        action=payload.action,
        extra=payload.extra,
    ))


@router.post("/bi/platform/versioning/{dataset_key}/snapshots", summary="Crear snapshot de dataset")
def phase3_create_dataset_snapshot(
    dataset_key: str,
    payload: DatasetSnapshotIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _rol: User = Depends(require_admin),  # auditoria 2026-09: sensible: plataforma de datos
):
    org_id = getattr(current_user, "organization_id", None)
    return APIResponse.ok(data=svc.create_dataset_snapshot(
        db,
        organization_id=org_id,
        dataset_key=dataset_key,
        payload=payload.payload,
        current_user=current_user,
    ))


@router.get("/bi/platform/versioning/{dataset_key}/snapshots", summary="Listar snapshots de dataset")
def phase3_list_dataset_snapshots(
    dataset_key: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    org_id = getattr(current_user, "organization_id", None)
    return APIListResponse.ok(
        items=svc.list_dataset_snapshots(db, organization_id=org_id, dataset_key=dataset_key)
    )


@router.get("/bi/platform/versioning/{dataset_key}/diff", summary="Diff entre snapshots")
def phase3_diff_dataset_snapshots(
    dataset_key: str,
    from_id: str = Query(..., min_length=36, max_length=36),
    to_id: str = Query(..., min_length=36, max_length=36),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    org_id = getattr(current_user, "organization_id", None)
    try:
        return APIResponse.ok(data=svc.diff_snapshots(
            db,
            organization_id=org_id,
            dataset_key=dataset_key,
            from_id=from_id,
            to_id=to_id,
        ))
    except ValueError:
        raise HTTPException(status_code=404, detail="Snapshot no encontrado")


# ── Field-level sensitivity ───────────────────────────────────────────────────

@router.get("/bi/platform/governance/field-sensitivity", summary="Listar clasificación de sensibilidad de campos BI")
def phase3_list_field_sensitivity(
    dataset_id: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    org_id = getattr(current_user, "organization_id", None)
    items = svc.list_field_sensitivity(db, organization_id=org_id, dataset_id=dataset_id)
    return APIListResponse.ok(items=items)


@router.put("/bi/platform/governance/field-sensitivity", summary="Crear/actualizar clasificación de sensibilidad de campo")
def phase3_upsert_field_sensitivity(
    payload: FieldSensitivityIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _rol: User = Depends(require_admin),  # auditoria 2026-09: sensible: plataforma de datos
):
    org_id = getattr(current_user, "organization_id", None)
    try:
        row = svc.upsert_field_sensitivity(
            db,
            organization_id=org_id,
            dataset_id=payload.dataset_id,
            field_name=payload.field_name,
            sensitivity_level=payload.sensitivity_level,
            pii_types=payload.pii_types,
            requires_approval=payload.requires_approval,
            current_user=current_user,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return APIResponse.ok(data={"ok": True, "field": row})


@router.delete("/bi/platform/governance/field-sensitivity/{sensitivity_id}", summary="Eliminar clasificación de sensibilidad de campo")
def phase3_delete_field_sensitivity(
    sensitivity_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _rol: User = Depends(require_admin),  # auditoria 2026-09: sensible: plataforma de datos
):
    enforce_abac(db, current_user, "bi_field_sensitivity", sensitivity_id, action="delete")
    org_id = getattr(current_user, "organization_id", None)
    deleted = svc.delete_field_sensitivity(db, organization_id=org_id, sensitivity_id=sensitivity_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Clasificación de campo no encontrada")
    return APIResponse.ok(data={"ok": True})


@router.get("/bi/platform/governance/field-sensitivity/summary", summary="Resumen de clasificación de sensibilidad BI")
def phase3_field_sensitivity_summary(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    org_id = getattr(current_user, "organization_id", None)
    return APIResponse.ok(data=svc.get_sensitivity_summary(db, organization_id=org_id))
