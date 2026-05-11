from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.services.scim_service import (
    ensure_org as _ensure_org,
    to_scim_user as _to_scim_user,
    to_scim_group as _to_scim_group,
    parse_role as _parse_role,
    create_scim_user as _create_scim_user,
    require_scim_token,
    list_scim_users_filtered as _list_scim_users_filtered,
    get_user_by_id_and_org as _get_user_by_id_and_org,
    put_scim_user_record as _put_scim_user_record,
    patch_scim_user_record as _patch_scim_user_record,
    delete_scim_user_record as _delete_scim_user_record,
    list_role_groups as _list_role_groups,
    get_role_group_members as _get_role_group_members,
    patch_role_group as _patch_role_group,
    process_bulk_operations as _process_bulk_operations,
)

router = APIRouter(prefix="/scim/v2/{org_id}", tags=["SCIM"])


def _require_scim_token(authorization: Optional[str] = Header(default=None)) -> None:
    require_scim_token(authorization)


@router.get("/ServiceProviderConfig")
def service_provider_config(
    org_id: str,
    _auth: None = Depends(_require_scim_token),
):
    return {
        "schemas": ["urn:ietf:params:scim:schemas:core:2.0:ServiceProviderConfig"],
        "patch": {"supported": True},
        "bulk": {"supported": True, "maxOperations": 100, "maxPayloadSize": 1048576},
        "filter": {"supported": True, "maxResults": 200},
        "changePassword": {"supported": False},
        "sort": {"supported": False},
        "etag": {"supported": False},
        "authenticationSchemes": [{
            "type": "oauthbearertoken",
            "name": "Bearer Token",
            "description": "Static bearer token for SCIM provisioning",
            "primary": True,
        }],
    }


@router.get("/ResourceTypes")
def list_resource_types(
    org_id: str,
    _auth: None = Depends(_require_scim_token),
):
    return {
        "schemas": ["urn:ietf:params:scim:api:messages:2.0:ListResponse"],
        "totalResults": 2,
        "startIndex": 1,
        "itemsPerPage": 2,
        "Resources": [
            {
                "schemas": ["urn:ietf:params:scim:schemas:core:2.0:ResourceType"],
                "id": "User", "name": "User", "endpoint": "/Users",
                "schema": "urn:ietf:params:scim:schemas:core:2.0:User",
            },
            {
                "schemas": ["urn:ietf:params:scim:schemas:core:2.0:ResourceType"],
                "id": "Group", "name": "Group", "endpoint": "/Groups",
                "schema": "urn:ietf:params:scim:schemas:core:2.0:Group",
            },
        ],
    }


@router.get("/Schemas")
def list_scim_schemas(
    org_id: str,
    _auth: None = Depends(_require_scim_token),
):
    return {
        "schemas": ["urn:ietf:params:scim:api:messages:2.0:ListResponse"],
        "totalResults": 2,
        "Resources": [
            {"id": "urn:ietf:params:scim:schemas:core:2.0:User", "name": "User"},
            {"id": "urn:ietf:params:scim:schemas:core:2.0:Group", "name": "Group"},
        ],
    }



@router.get("/Users")
def list_scim_users(
    org_id: str,
    startIndex: int = Query(default=1, ge=1),
    count: int = Query(default=100, ge=1, le=200),
    filter: Optional[str] = Query(default=None),
    db: Session = Depends(get_db),
    _auth: None = Depends(_require_scim_token),
):
    _ensure_org(db, org_id)
    total, users = _list_scim_users_filtered(db, org_id, filter, startIndex, count)
    return {
        "schemas": ["urn:ietf:params:scim:api:messages:2.0:ListResponse"],
        "totalResults": total,
        "startIndex": startIndex,
        "itemsPerPage": len(users),
        "Resources": [_to_scim_user(u) for u in users],
    }


@router.post("/Users", status_code=status.HTTP_201_CREATED)
def create_scim_user(
    org_id: str,
    payload: dict,
    db: Session = Depends(get_db),
    _auth: None = Depends(_require_scim_token),
):
    _ensure_org(db, org_id)
    user = _create_scim_user(org_id, payload, db)
    return _to_scim_user(user)


@router.get("/Users/{user_id}")
def get_scim_user(
    org_id: str,
    user_id: str,
    db: Session = Depends(get_db),
    _auth: None = Depends(_require_scim_token),
):
    _ensure_org(db, org_id)
    user = _get_user_by_id_and_org(db, user_id, org_id)
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    return _to_scim_user(user)


@router.put("/Users/{user_id}")
def put_scim_user(
    org_id: str,
    user_id: str,
    payload: dict,
    db: Session = Depends(get_db),
    _auth: None = Depends(_require_scim_token),
):
    _ensure_org(db, org_id)
    user = _put_scim_user_record(db, user_id, org_id, payload)
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    return _to_scim_user(user)


@router.patch("/Users/{user_id}")
def patch_scim_user(
    org_id: str,
    user_id: str,
    payload: dict,
    db: Session = Depends(get_db),
    _auth: None = Depends(_require_scim_token),
):
    _ensure_org(db, org_id)
    user = _patch_scim_user_record(db, user_id, org_id, payload)
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    return _to_scim_user(user)


@router.delete("/Users/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_scim_user(
    org_id: str,
    user_id: str,
    db: Session = Depends(get_db),
    _auth: None = Depends(_require_scim_token),
):
    # SCIM se autentica con un bearer token estático: no hay current_user
    # contra el que evaluar ABAC. La capa de servicio ya valida que el user
    # pertenece al org_id (get_user_by_id_and_org). Para que cualquier
    # deactivation provisionada vía SCIM quede trazada, dejamos un audit
    # log explícito — la idempotencia 204 del estándar SCIM no nos ayuda
    # a detectar abusos sin esta pista.
    _ensure_org(db, org_id)
    deleted = _delete_scim_user_record(db, user_id, org_id)
    try:
        import json
        from app.models.enterprise import AuditLog
        db.add(AuditLog(
            user_id=None,  # SCIM token, sin user humano
            action="DELETE",
            resource="users",
            resource_id=user_id,
            metadata_=json.dumps({
                "source": "scim",
                "org_id": org_id,
                "applied": bool(deleted),
            }),
        ))
        db.commit()
    except Exception:  # pragma: no cover — audit best-effort
        import logging
        logging.getLogger(__name__).exception("SCIM delete audit failed")
    return None


@router.get("/Groups")
def list_scim_groups(
    org_id: str,
    db: Session = Depends(get_db),
    _auth: None = Depends(_require_scim_token),
):
    _ensure_org(db, org_id)
    groups = _list_role_groups(db, org_id)
    return {
        "schemas": ["urn:ietf:params:scim:api:messages:2.0:ListResponse"],
        "totalResults": len(groups),
        "startIndex": 1,
        "itemsPerPage": len(groups),
        "Resources": groups,
    }


@router.patch("/Groups/{group_id}")
def patch_scim_group(
    org_id: str,
    group_id: str,
    payload: dict,
    db: Session = Depends(get_db),
    _auth: None = Depends(_require_scim_token),
):
    _ensure_org(db, org_id)
    target_role = _parse_role(group_id)
    members = _patch_role_group(db, org_id, target_role, payload.get("Operations", []) or [])
    return _to_scim_group(target_role.value, members)


# ── SCIM 2.0 Bulk Operations (RFC 7644 §3.7) ─────────────────────────────────

@router.post("/Bulk", status_code=status.HTTP_200_OK)
def scim_bulk(
    org_id: str,
    payload: dict,
    db: Session = Depends(get_db),
    _auth: None = Depends(_require_scim_token),
):
    _ensure_org(db, org_id)
    operations = payload.get("Operations") or []
    fail_on_errors = payload.get("failOnErrors")
    if len(operations) > 100:
        raise HTTPException(status_code=400, detail="Maximum 100 operations per Bulk request")
    responses = _process_bulk_operations(org_id, operations, fail_on_errors, db)
    return {
        "schemas": ["urn:ietf:params:scim:api:messages:2.0:BulkResponse"],
        "Operations": responses,
    }


@router.get("/Groups/{group_id}", summary="Get a SCIM group by id (role)")
def get_scim_group(
    org_id: str,
    group_id: str,
    db: Session = Depends(get_db),
    _auth: None = Depends(_require_scim_token),
):
    _ensure_org(db, org_id)
    target_role = _parse_role(group_id)
    members = _get_role_group_members(db, org_id, target_role)
    return _to_scim_group(target_role.value, members)
