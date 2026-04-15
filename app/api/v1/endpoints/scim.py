from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.user import User, UserRole
from app.services.scim_service import (
    ensure_org as _ensure_org,
    to_scim_user as _to_scim_user,
    to_scim_group as _to_scim_group,
    parse_role as _parse_role,
    create_scim_user as _create_scim_user,
    update_scim_user as _update_scim_user,
    deactivate_scim_user as _deactivate_scim_user,
    require_scim_token,
    process_bulk_operation,
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
    q = db.query(User).filter(User.organization_id == org_id)
    # SCIM 2.0 filter grammar (RFC 7644 §3.4.2) — support common Okta filter patterns
    if filter:
        f = filter.strip()
        if "userName eq " in f:
            val = f.split("userName eq ", 1)[1].strip().strip('"\'')
            q = q.filter(User.username == val)
        elif "emails.value eq " in f or "emails[value eq " in f:
            val = f.split(" eq ", 1)[1].strip().strip('"]\'')
            q = q.filter(User.email == val)
        elif "externalId eq " in f:
            val = f.split("externalId eq ", 1)[1].strip().strip('"\'')
            q = q.filter(User.scim_external_id == val)
        elif "active eq " in f:
            val = f.split("active eq ", 1)[1].strip().lower()
            is_active = val not in ("false", "0")
            q = q.filter(User.is_active == is_active)
        elif "userName sw " in f:
            val = f.split("userName sw ", 1)[1].strip().strip('"\'')
            q = q.filter(User.username.ilike(f"{val}%"))
    total = q.count()
    users = q.offset(startIndex - 1).limit(count).all()
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
    user = db.query(User).filter(User.id == user_id, User.organization_id == org_id).first()
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
    user = db.query(User).filter(User.id == user_id, User.organization_id == org_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    _update_scim_user(user, payload, "PUT")
    db.commit()
    db.refresh(user)
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
    user = db.query(User).filter(User.id == user_id, User.organization_id == org_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    _update_scim_user(user, payload, "PATCH")
    db.commit()
    db.refresh(user)
    return _to_scim_user(user)


@router.delete("/Users/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_scim_user(
    org_id: str,
    user_id: str,
    db: Session = Depends(get_db),
    _auth: None = Depends(_require_scim_token),
):
    _ensure_org(db, org_id)
    user = db.query(User).filter(User.id == user_id, User.organization_id == org_id).first()
    if not user:
        return None
    _deactivate_scim_user(user, db)
    db.commit()
    return None


@router.get("/Groups")
def list_scim_groups(
    org_id: str,
    db: Session = Depends(get_db),
    _auth: None = Depends(_require_scim_token),
):
    _ensure_org(db, org_id)
    groups = []
    for role in UserRole:
        members = db.query(User).filter(User.organization_id == org_id, User.role == role, User.is_active == True).all()
        groups.append(_to_scim_group(role.value, members))
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
    for op in payload.get("Operations", []) or []:
        operation = (op.get("op") or "").lower()
        value = op.get("value") or {}
        members = value.get("members") if isinstance(value, dict) else None
        if not isinstance(members, list):
            continue
        member_ids = [m.get("value") for m in members if isinstance(m, dict) and m.get("value")]
        if not member_ids:
            continue
        users = db.query(User).filter(User.organization_id == org_id, User.id.in_(member_ids)).all()
        for user in users:
            if operation in ("add", "replace"):
                user.role = target_role
            elif operation == "remove" and user.role == target_role:
                user.role = UserRole.employee
            user.scim_last_synced_at = datetime.now(timezone.utc)
    db.commit()
    members = db.query(User).filter(User.organization_id == org_id, User.role == target_role, User.is_active == True).all()
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

    responses = []
    error_count = 0

    for op in operations:
        try:
            responses.append(process_bulk_operation(org_id, op, db))
        except Exception as exc:
            error_count += 1
            responses.append({
                "method": (op.get("method") or "").upper(),
                "bulkId": op.get("bulkId"),
                "status": "400",
                "response": {
                    "schemas": ["urn:ietf:params:scim:api:messages:2.0:Error"],
                    "status": "400",
                    "detail": str(exc),
                },
            })
            if fail_on_errors and error_count >= fail_on_errors:
                break

    db.commit()
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
    members = db.query(User).filter(
        User.organization_id == org_id,
        User.role == target_role,
        User.is_active == True,
    ).all()
    return _to_scim_group(target_role.value, members)
