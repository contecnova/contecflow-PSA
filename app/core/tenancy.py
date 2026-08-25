"""Tenant-isolation helpers.

A single, audited place for "fetch this row by id, but only if it belongs to
the caller's organization". Returns 404 (never 403) on a cross-tenant hit so
the existence of another tenant's resource is never leaked. Mirrors the
semantics of the hand-written get_*_scoped_or_404 helpers (clients, projects,
CMDB CI) so every router can enforce isolation the same way.
"""
from __future__ import annotations

from typing import Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session


def org_scoped_or_404(
    db: Session,
    model,
    obj_id,
    current_user,
    *,
    id_attr: str = "id",
    org_attr: str = "organization_id",
    detail: str = "Not found",
):
    """Fetch ``model`` by id, enforcing organization isolation.

    Raises 404 when the row is missing OR belongs to a different organization.
    Superadmins bypass the org check. Rows whose org column is NULL (legacy,
    pre-tenancy data) are treated as global and remain accessible, matching the
    existing scoped-helper behaviour.
    """
    obj = db.query(model).filter(getattr(model, id_attr) == obj_id).first()
    if obj is None:
        raise HTTPException(404, detail)
    if not _can_access(current_user, getattr(obj, org_attr, None)):
        raise HTTPException(404, detail)
    return obj


def assert_same_org(current_user, row_org_id: Optional[str], *, detail: str = "Not found") -> None:
    """Raise 404 if ``row_org_id`` is set and differs from the caller's org.

    Use when you already loaded a row (e.g. via a service) and just need the
    isolation gate. Superadmins and NULL-org rows pass.
    """
    if not _can_access(current_user, row_org_id):
        raise HTTPException(404, detail)


def assert_org_id_is_own(current_user, org_id: Optional[str], *, detail: str = "Not found") -> None:
    """Gate for a **client-supplied** organisation id (path or query parameter).

    Deliberately stricter than ``assert_same_org``, and not interchangeable with
    it. ``assert_same_org`` guards a row that was already fetched through the
    tenant-scoped session, so it can afford to let a NULL org through as legacy
    global data. This function guards a raw identifier that the caller chose, so
    every permissive branch is an authorisation bypass:

    - a caller with no organisation gets 404, never a free pass;
    - a NULL/blank ``org_id`` gets 404, so an omitted parameter cannot widen access;
    - only an exact match, or a platform superadmin, proceeds.

    Endpoints that legitimately operate across tenants must use
    ``require_superadmin`` instead of calling this.
    """
    if getattr(current_user, "is_superadmin", False):
        return
    user_org = getattr(current_user, "organization_id", None)
    if not org_id or not user_org or str(org_id) != str(user_org):
        raise HTTPException(404, detail)


def _can_access(current_user, row_org_id: Optional[str]) -> bool:
    if getattr(current_user, "is_superadmin", False):
        return True
    user_org = getattr(current_user, "organization_id", None)
    # NULL row org → legacy/global, accessible. Otherwise must match.
    if row_org_id is None or user_org is None:
        return True
    return row_org_id == user_org
