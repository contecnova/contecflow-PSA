"""SCIM service — provisioning helpers (RFC 7644)."""
from __future__ import annotations

import hashlib
import hmac
import secrets
from datetime import datetime, timezone
from typing import Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import get_password_hash
from app.models.mfa import Organization
from app.models.user import User, UserRole, UserStatus


def scim_token_expected() -> str:
    return settings.SCIM_BEARER_TOKEN


def hash_scim_token(token: str) -> str:
    """Return the storage hash (SHA-256 hex) for a SCIM plaintext token."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def generate_scim_token(db: Session, org_id: str) -> str:
    """Generate, store (hashed) and return a new per-org SCIM token (plaintext).

    The plaintext is returned ONCE for the caller to hand to the IdP; only the
    hash is persisted.
    """
    org = (
        db.query(Organization)
        .filter(Organization.id == org_id, Organization.is_active == True)
        .first()
    )
    if not org:
        raise HTTPException(status_code=404, detail="Organización no encontrada")
    token = secrets.token_urlsafe(32)
    org.scim_token_hash = hash_scim_token(token)
    db.commit()
    return token


def _is_dev_or_test() -> bool:
    import os
    if os.environ.get("TESTING") == "1" or os.environ.get("PYTEST_CURRENT_TEST"):
        return True
    env = (settings.ENVIRONMENT or "").lower()
    return env in ("development", "dev", "test", "testing", "local")


def _legacy_global_token_allows(org_id: str, provided: str) -> bool:
    """Backward-compat: honour the legacy global SCIM_BEARER_TOKEN.

    Binding rules:
      * If SCIM_ALLOWED_ORG_ID is set, the global token is valid ONLY for that
        single org (any environment).
      * If SCIM_ALLOWED_ORG_ID is unset, the global token is valid for ANY org
        ONLY in development/testing — never silently in production.
    """
    expected = scim_token_expected()
    if not expected or not hmac.compare_digest(provided, expected):
        return False
    allowed_org = (settings.SCIM_ALLOWED_ORG_ID or "").strip()
    if allowed_org:
        return hmac.compare_digest(org_id, allowed_org)
    return _is_dev_or_test()


def require_scim_token(
    db: Session, authorization: Optional[str], org_id: str
) -> Organization:
    """Authenticate a SCIM request and bind it to ``org_id``.

    Resolution order:
      1. Per-org token: hash the presented bearer and look up the Organization
         whose ``scim_token_hash`` matches AND whose id equals ``org_id``.
      2. Legacy global token (backward compat, see _legacy_global_token_allows).

    Returns the resolved Organization. Raises:
      * 503 if no SCIM auth is configured at all,
      * 401 if no/blank bearer token is presented,
      * 403 if the token does not authorise ``org_id`` (cross-tenant attempt),
      * 404 if the bound org does not exist / is inactive.
    """
    legacy_configured = bool(scim_token_expected())

    # Is there ANY SCIM auth configured at all (global token OR per-org tokens)?
    any_per_org = (
        db.query(Organization.id)
        .filter(Organization.scim_token_hash.isnot(None))
        .first()
        is not None
    )
    if not legacy_configured and not any_per_org:
        raise HTTPException(status_code=503, detail="SCIM no configurado")

    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Token SCIM requerido")
    provided = authorization.split(" ", 1)[1].strip()
    if not provided:
        raise HTTPException(status_code=401, detail="Token SCIM requerido")

    # 1) Per-org token: resolve the org by the presented token's hash.
    token_hash = hash_scim_token(provided)
    matched = (
        db.query(Organization)
        .filter(Organization.scim_token_hash.isnot(None))
        .all()
    )
    resolved: Optional[Organization] = None
    for org in matched:
        if hmac.compare_digest(org.scim_token_hash or "", token_hash):
            resolved = org
            break

    if resolved is not None:
        # Token is valid for SOME org — it must be the one in the path.
        if not hmac.compare_digest(resolved.id, org_id):
            raise HTTPException(status_code=403, detail="Token SCIM inválido para esta organización")
        if not resolved.is_active:
            raise HTTPException(status_code=404, detail="Organización no encontrada")
        return resolved

    # 2) Legacy global token (backward compat).
    if _legacy_global_token_allows(org_id, provided):
        return ensure_org(db, org_id)

    raise HTTPException(status_code=403, detail="Token SCIM inválido")


def ensure_org(db: Session, org_id: str) -> Organization:
    org = (
        db.query(Organization)
        .filter(Organization.id == org_id, Organization.is_active == True)
        .first()
    )
    if not org:
        raise HTTPException(status_code=404, detail="Organización no encontrada")
    return org


def to_scim_user(u: User) -> dict:
    given_name = u.first_name or (u.full_name.split(" ")[0] if u.full_name else "")
    family_name = u.last_name or (
        " ".join(u.full_name.split(" ")[1:]) if u.full_name and " " in u.full_name else ""
    )
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


def to_scim_group(role: str, users: list[User]) -> dict:
    return {
        "schemas": ["urn:ietf:params:scim:schemas:core:2.0:Group"],
        "id": role,
        "displayName": role,
        "members": [{"value": u.id, "display": u.email} for u in users],
    }


def parse_role(value: Optional[str]) -> UserRole:
    if not value:
        return UserRole.employee
    try:
        return UserRole(value)
    except Exception:
        return UserRole.employee


def create_scim_user(org_id: str, payload: dict, db: Session) -> User:
    """Create a new SCIM-provisioned user.  Raises 400/409 on validation errors."""
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

    existing = db.query(User).filter(
        (User.username == user_name) | (User.email == email)
    ).first()
    if existing:
        raise HTTPException(status_code=409, detail="Usuario ya existe")

    role = parse_role(((payload.get("roles") or [{}])[0] or {}).get("value"))
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
        hashed_password=get_password_hash(secrets.token_urlsafe(20)),
        organization_id=org_id,
        scim_external_id=payload.get("externalId"),
        scim_last_synced_at=datetime.now(timezone.utc),
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def update_scim_user(user: User, payload: dict, method: str) -> None:
    """Apply a PUT or PATCH update to *user* in-place (caller must commit)."""
    if method == "PUT":
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
            user.role = parse_role(((payload.get("roles") or [{}])[0] or {}).get("value"))
        user.scim_external_id = payload.get("externalId", user.scim_external_id)
    elif method == "PATCH":
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


def deactivate_scim_user(user: User, db: Session) -> None:
    """Soft-delete: mark user inactive (caller must commit)."""
    user.is_active = False
    user.status = UserStatus.inactive
    user.scim_last_synced_at = datetime.now(timezone.utc)


def process_bulk_operation(
    org_id: str,
    op: dict,
    db: Session,
) -> dict:
    """Process a single SCIM bulk operation entry.  Returns a response dict."""
    method = (op.get("method") or "").upper()
    path = op.get("path") or ""
    bulk_id = op.get("bulkId")
    data = op.get("data") or {}

    if method == "POST" and path.endswith("/Users"):
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
        role = parse_role(((data.get("roles") or [{}])[0] or {}).get("value"))
        new_user = User(
            username=user_name,
            email=email,
            full_name=full_name,
            hashed_password=get_password_hash(secrets.token_urlsafe(20)),
            role=role,
            is_active=bool(data.get("active", True)),
            organization_id=org_id,
            scim_external_id=data.get("externalId"),
            scim_last_synced_at=datetime.now(timezone.utc),
        )
        db.add(new_user)
        db.flush()
        return {
            "method": "POST",
            "bulkId": bulk_id,
            "status": "201",
            "location": f"/scim/v2/{org_id}/Users/{new_user.id}",
            "response": to_scim_user(new_user),
        }

    elif method in ("PUT", "PATCH") and "/Users/" in path:
        user_id = path.rsplit("/", 1)[-1]
        user = db.query(User).filter(
            User.id == user_id, User.organization_id == org_id
        ).first()
        if not user:
            raise ValueError(f"User {user_id} not found")
        update_scim_user(user, data, method)
        return {
            "method": method,
            "bulkId": bulk_id,
            "status": "200",
            "response": to_scim_user(user),
        }

    elif method == "DELETE" and "/Users/" in path:
        user_id = path.rsplit("/", 1)[-1]
        user = db.query(User).filter(
            User.id == user_id, User.organization_id == org_id
        ).first()
        if not user:
            raise ValueError(f"User {user_id} not found")
        deactivate_scim_user(user, db)
        return {"method": "DELETE", "bulkId": bulk_id, "status": "204"}

    else:
        raise ValueError(f"Unsupported bulk operation: {method} {path}")


# ── Higher-level service helpers (used by router) ────────────────────────────

def list_scim_users_filtered(
    db: Session,
    org_id: str,
    filter_str: Optional[str],
    start_index: int,
    count: int,
) -> tuple[int, list[User]]:
    """Return (total, users) applying SCIM 2.0 filter grammar."""
    q = db.query(User).filter(User.organization_id == org_id)
    if filter_str:
        f = filter_str.strip()
        if "userName eq " in f:
            val = f.split("userName eq ", 1)[1].strip().strip("\"'")
            q = q.filter(User.username == val)
        elif "emails.value eq " in f or "emails[value eq " in f:
            val = f.split(" eq ", 1)[1].strip().strip('"\']')
            q = q.filter(User.email == val)
        elif "externalId eq " in f:
            val = f.split("externalId eq ", 1)[1].strip().strip("\"'")
            q = q.filter(User.scim_external_id == val)
        elif "active eq " in f:
            val = f.split("active eq ", 1)[1].strip().lower()
            is_active = val not in ("false", "0")
            q = q.filter(User.is_active == is_active)
        elif "userName sw " in f:
            val = f.split("userName sw ", 1)[1].strip().strip("\"'")
            q = q.filter(User.username.ilike(f"{val}%"))
    total = q.count()
    users = q.offset(start_index - 1).limit(count).all()
    return total, users


def get_user_by_id_and_org(db: Session, user_id: str, org_id: str) -> Optional[User]:
    return (
        db.query(User)
        .filter(User.id == user_id, User.organization_id == org_id)
        .first()
    )


def put_scim_user_record(db: Session, user_id: str, org_id: str, payload: dict) -> Optional[User]:
    user = get_user_by_id_and_org(db, user_id, org_id)
    if not user:
        return None
    update_scim_user(user, payload, "PUT")
    db.commit()
    db.refresh(user)
    return user


def patch_scim_user_record(db: Session, user_id: str, org_id: str, payload: dict) -> Optional[User]:
    user = get_user_by_id_and_org(db, user_id, org_id)
    if not user:
        return None
    update_scim_user(user, payload, "PATCH")
    db.commit()
    db.refresh(user)
    return user


def delete_scim_user_record(db: Session, user_id: str, org_id: str) -> bool:
    user = get_user_by_id_and_org(db, user_id, org_id)
    if not user:
        return False
    deactivate_scim_user(user, db)
    db.commit()
    return True


def list_role_groups(db: Session, org_id: str) -> list[dict]:
    groups = []
    for role in UserRole:
        members = (
            db.query(User)
            .filter(User.organization_id == org_id, User.role == role, User.is_active == True)
            .all()
        )
        groups.append(to_scim_group(role.value, members))
    return groups


def get_role_group_members(db: Session, org_id: str, role: UserRole) -> list[User]:
    return (
        db.query(User)
        .filter(User.organization_id == org_id, User.role == role, User.is_active == True)
        .all()
    )


def patch_role_group(
    db: Session,
    org_id: str,
    target_role: UserRole,
    operations: list,
) -> list[User]:
    for op in operations or []:
        operation = (op.get("op") or "").lower()
        value = op.get("value") or {}
        members = value.get("members") if isinstance(value, dict) else None
        if not isinstance(members, list):
            continue
        member_ids = [
            m.get("value") for m in members if isinstance(m, dict) and m.get("value")
        ]
        if not member_ids:
            continue
        users = (
            db.query(User)
            .filter(User.organization_id == org_id, User.id.in_(member_ids))
            .all()
        )
        for user in users:
            if operation in ("add", "replace"):
                user.role = target_role
            elif operation == "remove" and user.role == target_role:
                user.role = UserRole.employee
            user.scim_last_synced_at = datetime.now(timezone.utc)
    db.commit()
    return get_role_group_members(db, org_id, target_role)


def process_bulk_operations(
    org_id: str,
    operations: list,
    fail_on_errors,
    db: Session,
) -> list[dict]:
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
    return responses


# ── Errores de operaciones en bloque ─────────────────────────────────────────
# Auditoría 2026-08 (hallazgo 22). Esta función vivía en `v238_service.py`, un
# módulo nombrado por número de versión con seis dominios dentro. SCIM es su
# dominio y aquí es donde se busca.
#
# Aviso honesto: comprobado en todo el repositorio, tiene CERO llamantes. Se
# conserva porque el aprovisionamiento SCIM en bloque es una funcionalidad
# declarada de la plataforma, pero nadie la invoca hoy — no asumir que está en
# uso.
def scim_bulk_error(bulk_id, status, detail) -> dict:
    return {
        "method": "UNKNOWN",
        "bulkId": bulk_id,
        "status": str(status),
        "response": {
            "schemas": ["urn:ietf:params:scim:api:messages:2.0:Error"],
            "status": str(status),
            "detail": detail,
        }
    }
