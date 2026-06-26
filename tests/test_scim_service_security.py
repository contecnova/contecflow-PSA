import uuid

import pytest
from fastapi import HTTPException

from app.core.config import settings
from app.models.mfa import Organization
from app.services.scim_service import (
    generate_scim_token,
    hash_scim_token,
    require_scim_token,
    scim_token_expected,
)


def _make_org(db, name="Org A"):
    org = Organization(id=str(uuid.uuid4()), name=name, slug=f"slug-{uuid.uuid4().hex[:8]}", is_active=True)
    db.add(org)
    db.commit()
    db.refresh(org)
    return org


def test_scim_token_expected_uses_only_scim_token(monkeypatch):
    monkeypatch.setattr(settings, "SCIM_BEARER_TOKEN", "scim-secret", raising=False)
    monkeypatch.setattr(settings, "CLIENT_PORTAL_SECRET", "portal-secret", raising=False)

    assert scim_token_expected() == "scim-secret"


def test_per_org_token_authenticates_matching_org(db):
    org = _make_org(db)
    token = generate_scim_token(db, org.id)

    # Hash is stored, plaintext is not.
    assert org.scim_token_hash == hash_scim_token(token)

    resolved = require_scim_token(db, f"Bearer {token}", org.id)
    assert resolved.id == org.id


def test_per_org_token_rejected_for_other_org(db):
    org_a = _make_org(db, "Org A")
    org_b = _make_org(db, "Org B")
    token_a = generate_scim_token(db, org_a.id)

    # Token of org A must NOT administer org B → 403 cross-tenant.
    with pytest.raises(HTTPException) as exc:
        require_scim_token(db, f"Bearer {token_a}", org_b.id)
    assert exc.value.status_code == 403


def test_missing_bearer_token_returns_401(db):
    org = _make_org(db)
    generate_scim_token(db, org.id)

    with pytest.raises(HTTPException) as exc:
        require_scim_token(db, None, org.id)
    assert exc.value.status_code == 401


def test_unknown_token_returns_403(db, monkeypatch):
    # No global token; a per-org token exists so SCIM is "configured".
    org = _make_org(db)
    generate_scim_token(db, org.id)
    monkeypatch.setattr(settings, "SCIM_BEARER_TOKEN", "", raising=False)

    with pytest.raises(HTTPException) as exc:
        require_scim_token(db, "Bearer totally-wrong", org.id)
    assert exc.value.status_code == 403


def test_returns_503_when_scim_not_configured(db, monkeypatch):
    # No global token and no per-org tokens at all.
    org = _make_org(db)
    monkeypatch.setattr(settings, "SCIM_BEARER_TOKEN", "", raising=False)

    with pytest.raises(HTTPException) as exc:
        require_scim_token(db, "Bearer something", org.id)
    assert exc.value.status_code == 503


def test_legacy_global_token_dev_test_any_org(db, monkeypatch):
    # In dev/testing the legacy global token still works for any org (compat).
    org = _make_org(db)
    monkeypatch.setattr(settings, "SCIM_BEARER_TOKEN", "global-secret", raising=False)
    monkeypatch.setattr(settings, "SCIM_ALLOWED_ORG_ID", "", raising=False)

    resolved = require_scim_token(db, "Bearer global-secret", org.id)
    assert resolved.id == org.id


def test_legacy_global_token_bound_to_allowed_org(db, monkeypatch):
    org_a = _make_org(db, "A")
    org_b = _make_org(db, "B")
    monkeypatch.setattr(settings, "SCIM_BEARER_TOKEN", "global-secret", raising=False)
    monkeypatch.setattr(settings, "SCIM_ALLOWED_ORG_ID", org_a.id, raising=False)

    # Bound org works...
    assert require_scim_token(db, "Bearer global-secret", org_a.id).id == org_a.id
    # ...other org is rejected even with the valid global token.
    with pytest.raises(HTTPException) as exc:
        require_scim_token(db, "Bearer global-secret", org_b.id)
    assert exc.value.status_code == 403


def test_legacy_global_token_rejected_in_prod_without_allowed_org(db, monkeypatch):
    import os
    org = _make_org(db)
    monkeypatch.setattr(settings, "SCIM_BEARER_TOKEN", "global-secret", raising=False)
    monkeypatch.setattr(settings, "SCIM_ALLOWED_ORG_ID", "", raising=False)
    monkeypatch.setattr(settings, "ENVIRONMENT", "production", raising=False)
    monkeypatch.delenv("TESTING", raising=False)
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)

    with pytest.raises(HTTPException) as exc:
        require_scim_token(db, "Bearer global-secret", org.id)
    # Prod + no SCIM_ALLOWED_ORG_ID → legacy global token is NOT honoured.
    assert exc.value.status_code == 403
