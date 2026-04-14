from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional
import hmac

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import get_password_hash
from app.db.session import get_db
from app.models.mfa import Organization
from app.models.user import User, UserRole, UserStatus

router = APIRouter(prefix="/scim/v2/{org_id}", tags=["SCIM"])


def _scim_token_expected() -> str:
    return settings.SCIM_BEARER_TOKEN or settings.CLIENT_PORTAL_SECRET


def _require_scim_token(authorization: Optional[str] = Header(default=None)) -> None:
    expected = _scim_token_expected()
    if not expected:
        raise HTTPException(status_code=503, detail="SCIM no configurado")
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Token SCIM requerido")
    provided = authorization.split(" ", 1)[1].strip()
    if not hmac.compare_digest(provided, expected):
        raise HTTPException(status_code=403, detail="Token SCIM inválido")


def _ensure_org(db: Session, org_id: str) -> Organization:
    org = db.query(Organization).filter(Organization.id == org_id, Organization.is_active == True).first()
    if not org:
        raise HTTPException(status_code=404, detail="Organización no encontrada")
    return org


def _to_scim_user(u: User) -> dict:
    given_name = u.first_name or (u.full_name.split(" ")[0] if u.full_name else "")
    family_name = u.last_name or (" ".join(u.full_name.split(" ")[1:]) if u.full_name and " " in u.full_name else "")
    role_value = u.role.value if hasattr(u.role, "value") else str(u.role)
    return {
        "schemas": ["urn:ietf:params:scim:schemas:core:2.0:User"],
        "id": u.id,
        "externalId": u.scim_external_id,
        "userName": u.username,
        "name": {
            "givenName": given_name,
            "familyName": family_name,
            "formatted": u.full_name,
        },
        "emails": [{"value": u.email, "primary": True}],
        "active": bool(u.is_active),
        "roles": [{"value": role_value}],
        "meta": {
            "resourceType": "User",
            "lastModified": u.updated_at.isoformat() if u.updated_at else None,
        },
    }


def _to_scim_group(role: str, users: list[User]) -> dict:
    return {
        "schemas": ["urn:ietf:params:scim:schemas:core:2.0:Group"],
        "id": role,
        "displayName": role,
        "members": [{"value": u.id, "display": u.email} for u in users],
    }


def _parse_role(value: Optional[str]) -> UserRole:
    if not value:
        return UserRole.employee
    try:
        return UserRole(value)
    except Exception:
        return UserRole.employee


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
    user_name = payload.get("userName")
    if not user_name:
        raise HTTPException(status_code=400, detail="userName requerido")

    name = payload.get("name") or {}
    given = name.get("givenName") or ""
    family = name.get("familyName") or ""
    full_name = (name.get("formatted") or f"{given} {family}".strip() or user_name).strip()
    emails = payload.get("emails") or []
    email = None
    if emails and isinstance(emails, list):
        email = (emails[0] or {}).get("value")
    email = email or f"{user_name}@scim.local"

    existing = db.query(User).filter((User.username == user_name) | (User.email == email)).first()
    if existing:
        raise HTTPException(status_code=409, detail="Usuario ya existe")

    role = _parse_role(((payload.get("roles") or [{}])[0] or {}).get("value"))
    active = payload.get("active", True)

    user = User(
        username=user_name,
        email=email,
        full_name=full_name,
        first_name=given or None,
        last_name=family or None,
        role=role,
        status=UserStatus.active if active else UserStatus.inactive,
        is_active=bool(active),
        hashed_password=get_password_hash(settings.DEFAULT_USER_PASSWORD),
        organization_id=org_id,
        scim_external_id=payload.get("externalId"),
        scim_last_synced_at=datetime.now(timezone.utc),
    )
    db.add(user)
    db.commit()
    db.refresh(user)
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

    name = payload.get("name") or {}
    emails = payload.get("emails") or []
    if payload.get("userName"):
        user.username = payload.get("userName")
    if emails and isinstance(emails, list) and (emails[0] or {}).get("value"):
        user.email = (emails[0] or {}).get("value")
    if name.get("formatted"):
        user.full_name = name.get("formatted")
    if name.get("givenName") is not None:
        user.first_name = name.get("givenName")
    if name.get("familyName") is not None:
        user.last_name = name.get("familyName")

    if "active" in payload:
        user.is_active = bool(payload.get("active"))
        user.status = UserStatus.active if user.is_active else UserStatus.inactive

    if payload.get("roles"):
        user.role = _parse_role(((payload.get("roles") or [{}])[0] or {}).get("value"))

    user.scim_external_id = payload.get("externalId", user.scim_external_id)
    user.scim_last_synced_at = datetime.now(timezone.utc)
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

    for op in payload.get("Operations", []) or []:
        operation = (op.get("op") or "").lower()
        path = (op.get("path") or "").lower()
        value = op.get("value")
        if operation in ("replace", "add"):
            if path == "active":
                user.is_active = bool(value)
                user.status = UserStatus.active if user.is_active else UserStatus.inactive
            elif path == "displayname" and value:
                user.full_name = str(value)
            elif path == "username" and value:
                user.username = str(value)
        if operation == "remove" and path == "active":
            user.is_active = False
            user.status = UserStatus.inactive

    user.scim_last_synced_at = datetime.now(timezone.utc)
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
    user.is_active = False
    user.status = UserStatus.inactive
    user.scim_last_synced_at = datetime.now(timezone.utc)
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
    """
    SCIM 2.0 Bulk endpoint — processes up to 100 operations per request.
    Supports Create (POST), Replace (PUT), Update (PATCH), Delete (DELETE) for Users.
    fail_on_errors: if set, stops processing after that many errors.
    """
    _ensure_org(db, org_id)
    operations = payload.get("Operations") or []
    fail_on_errors = payload.get("failOnErrors")
    if len(operations) > 100:
        raise HTTPException(status_code=400, detail="Maximum 100 operations per Bulk request")

    responses = []
    error_count = 0

    for op in operations:
        method  = (op.get("method") or "").upper()
        path    = op.get("path") or ""
        bulk_id = op.get("bulkId")
        data    = op.get("data") or {}

        try:
            if method == "POST" and path.endswith("/Users"):
                # Create user — inline the create logic
                user_name = data.get("userName")
                if not user_name:
                    raise ValueError("userName required")
                name = data.get("name") or {}
                given = name.get("givenName") or ""
                family = name.get("familyName") or ""
                full_name = (name.get("formatted") or f"{given} {family}".strip() or user_name).strip()
                emails = data.get("emails") or []
                email = ((emails[0] or {}).get("value")) if emails else None
                email = email or f"{user_name}@scim.local"
                existing = db.query(User).filter(
                    (User.username == user_name) | (User.email == email)
                ).first()
                if existing:
                    raise ValueError(f"User '{user_name}' already exists")
                from app.core.security import get_password_hash
                role = _parse_role(((data.get("roles") or [{}])[0] or {}).get("value"))
                new_user = User(
                    username=user_name, email=email, full_name=full_name,
                    hashed_password=get_password_hash(settings.DEFAULT_USER_PASSWORD),
                    role=role, is_active=bool(data.get("active", True)),
                    organization_id=org_id,
                    scim_external_id=data.get("externalId"),
                    scim_last_synced_at=datetime.now(timezone.utc),
                )
                db.add(new_user)
                db.flush()
                responses.append({
                    "method": "POST",
                    "bulkId": bulk_id,
                    "status": "201",
                    "location": f"/scim/v2/{org_id}/Users/{new_user.id}",
                    "response": _to_scim_user(new_user),
                })

            elif method in ("PUT", "PATCH") and "/Users/" in path:
                user_id = path.rsplit("/", 1)[-1]
                user = db.query(User).filter(User.id == user_id, User.organization_id == org_id).first()
                if not user:
                    raise ValueError(f"User {user_id} not found")
                if method == "PUT":
                    name = data.get("name") or {}
                    given = name.get("givenName") or user.full_name or ""
                    family = name.get("familyName") or ""
                    user.full_name = name.get("formatted") or f"{given} {family}".strip() or user.full_name
                    emails = data.get("emails") or []
                    if emails:
                        user.email = (emails[0] or {}).get("value") or user.email
                    active = data.get("active")
                    if active is not None:
                        user.is_active = bool(active)
                        user.status = UserStatus.active if active else UserStatus.inactive
                elif method == "PATCH":
                    for op_inner in (data.get("Operations") or []):
                        op_path = (op_inner.get("path") or "").lower()
                        op_val = op_inner.get("value")
                        if op_path == "active":
                            user.is_active = bool(op_val)
                            user.status = UserStatus.active if op_val else UserStatus.inactive
                        elif op_path == "username":
                            user.username = op_val
                user.scim_last_synced_at = datetime.now(timezone.utc)
                responses.append({
                    "method": method,
                    "bulkId": bulk_id,
                    "status": "200",
                    "response": _to_scim_user(user),
                })

            elif method == "DELETE" and "/Users/" in path:
                user_id = path.rsplit("/", 1)[-1]
                user = db.query(User).filter(User.id == user_id, User.organization_id == org_id).first()
                if not user:
                    raise ValueError(f"User {user_id} not found")
                user.is_active = False
                user.status = UserStatus.inactive
                user.scim_last_synced_at = datetime.now(timezone.utc)
                responses.append({"method": "DELETE", "bulkId": bulk_id, "status": "204"})

            else:
                raise ValueError(f"Unsupported bulk operation: {method} {path}")

        except Exception as exc:
            error_count += 1
            responses.append({
                "method": method,
                "bulkId": bulk_id,
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
