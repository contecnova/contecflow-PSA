from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.core.ratelimit import limiter
from app.db.session import get_db
from app.models.user import User
from app.services import bi_governance_service as svc

router = APIRouter()

GOVERNANCE_CONFIG_KEY = "bi.governance.config"
GOVERNANCE_POLICIES_KEY = "bi.governance.policies"

_DEFAULT_CONFIG = {
    "require_approval_for_publish": False,
    "data_retention_days": 90,
}


class GovernanceConfigIn(BaseModel):
    require_approval_for_publish: Optional[bool] = None
    data_retention_days: Optional[int] = Field(None, ge=1, le=3650)


class PolicyIn(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)
    resource_type: str = Field(..., min_length=1, max_length=60)
    resource_id: str = Field(..., min_length=1, max_length=120)
    allowed_roles: list[str] = Field(default_factory=list)
    deny_roles: list[str] = Field(default_factory=list)


@router.get('/bi/governance/config', summary='Leer configuración de governance BI')
@limiter.limit("60/minute")
def get_governance_config(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    org_id = getattr(current_user, 'organization_id', None)
    return svc._get_json(db, GOVERNANCE_CONFIG_KEY, org_id, _DEFAULT_CONFIG)


@router.put('/bi/governance/config', summary='Actualizar configuración de governance BI')
@limiter.limit("30/minute")
def update_governance_config(
    payload: GovernanceConfigIn,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    org_id = getattr(current_user, 'organization_id', None)
    current = svc._get_json(db, GOVERNANCE_CONFIG_KEY, org_id, dict(_DEFAULT_CONFIG))
    if payload.require_approval_for_publish is not None:
        current["require_approval_for_publish"] = payload.require_approval_for_publish
    if payload.data_retention_days is not None:
        current["data_retention_days"] = payload.data_retention_days
    svc._set_json(db, GOVERNANCE_CONFIG_KEY, org_id, current, "BI governance config")
    return current


@router.get('/bi/governance/policies', summary='Listar políticas de acceso BI')
@limiter.limit("60/minute")
def list_policies(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    org_id = getattr(current_user, 'organization_id', None)
    policies = svc._get_json(db, GOVERNANCE_POLICIES_KEY, org_id, [])
    return policies


@router.post('/bi/governance/policies', summary='Crear política de acceso BI', status_code=201)
@limiter.limit("30/minute")
def create_policy(
    payload: PolicyIn,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    import uuid as _uuid
    org_id = getattr(current_user, 'organization_id', None)
    policies = svc._get_json(db, GOVERNANCE_POLICIES_KEY, org_id, [])
    new_policy = {
        "id": str(_uuid.uuid4()),
        "name": payload.name,
        "resource_type": payload.resource_type,
        "resource_id": payload.resource_id,
        "allowed_roles": payload.allowed_roles,
        "deny_roles": payload.deny_roles,
        "created_at": svc._iso_now(),
    }
    policies.append(new_policy)
    svc._set_json(db, GOVERNANCE_POLICIES_KEY, org_id, policies, "BI governance policies")
    return new_policy


@router.get('/bi/governance/audit-log', summary='Consultar log de auditoría BI governance')
@limiter.limit("60/minute")
def get_audit_log(
    request: Request,
    days: int = Query(30, ge=1, le=90),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    org_id = getattr(current_user, 'organization_id', None)
    items = svc.get_access_history(db, organization_id=org_id, days=days)
    return {"items": items, "count": len(items)}


class AuditAccessIn(BaseModel):
    entity_type: str = Field(..., min_length=2, max_length=40)
    entity_id: str = Field(..., min_length=1, max_length=120)
    action: str = Field(..., min_length=2, max_length=40)
    before_state: Optional[dict[str, Any]] = None
    after_state: Optional[dict[str, Any]] = None
    extra: Optional[dict[str, Any]] = None


class LineageIn(BaseModel):
    source_table: str = Field(..., min_length=2, max_length=120)
    target_table: str = Field(..., min_length=2, max_length=120)
    transformation_sql: str = Field(..., min_length=2, max_length=5000)


class FieldSensitivityIn(BaseModel):
    dataset_id: str = Field(..., min_length=1, max_length=120)
    field_name: str = Field(..., min_length=1, max_length=120)
    sensitivity_level: str = Field(..., pattern="^(public|internal|confidential|restricted)$")
    pii_fields: list[str] = Field(default_factory=list)
    requires_approval: bool = False


@router.post('/bi/governance/audit/access', summary='Registrar evento de acceso BI con before/after + metadata cliente')
@limiter.limit("30/minute")
def log_access(
    payload: AuditAccessIn,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    org_id = getattr(current_user, 'organization_id', None)
    row = svc.log_bi_access(
        db,
        organization_id=org_id,
        current_user=current_user,
        entity_type=payload.entity_type,
        entity_id=payload.entity_id,
        action=payload.action,
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get('user-agent'),
        before_state=payload.before_state,
        after_state=payload.after_state,
        extra=payload.extra,
    )
    return {'ok': True, 'audit': row}


@router.get('/bi/governance/audit/access', summary='Consultar auditoria BI por ventana temporal')
@limiter.limit("60/minute")
def list_access_history(
    request: Request,
    days: int = Query(30, ge=1, le=90),
    user_id: Optional[str] = Query(None),
    entity_type: Optional[str] = Query(None),
    action: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    org_id = getattr(current_user, 'organization_id', None)
    items = svc.get_access_history(
        db,
        organization_id=org_id,
        days=days,
        user_id=user_id,
        entity_type=entity_type,
        action=action,
    )
    return {'items': items, 'count': len(items)}


@router.get('/bi/governance/lineage', summary='Listar data lineage BI')
@limiter.limit("60/minute")
def list_lineage(
    request: Request,
    target_table: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    org_id = getattr(current_user, 'organization_id', None)
    items = svc.list_lineage(db, organization_id=org_id, target_table=target_table)
    return {'items': items, 'count': len(items)}


@router.post('/bi/governance/lineage', summary='Registrar/actualizar data lineage BI')
@limiter.limit("30/minute")
def track_lineage(
    payload: LineageIn,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    org_id = getattr(current_user, 'organization_id', None)
    row = svc.track_data_lineage(
        db,
        organization_id=org_id,
        current_user=current_user,
        source_table=payload.source_table,
        target_table=payload.target_table,
        transformation_sql=payload.transformation_sql,
    )
    return {'ok': True, 'edge': row}


@router.get('/bi/governance/field-sensitivity', summary='Listar sensibilidad de campos BI')
@limiter.limit("60/minute")
def list_fields(
    request: Request,
    dataset_id: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    org_id = getattr(current_user, 'organization_id', None)
    items = svc.list_field_sensitivity(db, organization_id=org_id, dataset_id=dataset_id)
    return {'items': items, 'count': len(items)}


@router.put('/bi/governance/field-sensitivity', summary='Crear/actualizar sensibilidad de campo BI')
@limiter.limit("30/minute")
def upsert_field(
    payload: FieldSensitivityIn,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    org_id = getattr(current_user, 'organization_id', None)
    try:
        row = svc.upsert_field_sensitivity(
            db,
            organization_id=org_id,
            dataset_id=payload.dataset_id,
            field_name=payload.field_name,
            sensitivity_level=payload.sensitivity_level,
            pii_fields=payload.pii_fields,
            requires_approval=payload.requires_approval,
            current_user=current_user,
        )
    except ValueError:
        raise HTTPException(status_code=400, detail='sensitivity_level invalido')
    return {'ok': True, 'field': row}
