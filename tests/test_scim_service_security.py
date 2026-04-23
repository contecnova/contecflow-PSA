import pytest
from fastapi import HTTPException

from app.core.config import settings
from app.services.scim_service import require_scim_token, scim_token_expected


def test_scim_token_expected_uses_only_scim_token(monkeypatch):
    monkeypatch.setattr(settings, "SCIM_BEARER_TOKEN", "scim-secret", raising=False)
    monkeypatch.setattr(settings, "CLIENT_PORTAL_SECRET", "portal-secret", raising=False)

    assert scim_token_expected() == "scim-secret"


def test_require_scim_token_returns_503_when_scim_not_configured(monkeypatch):
    monkeypatch.setattr(settings, "SCIM_BEARER_TOKEN", "", raising=False)
    monkeypatch.setattr(settings, "CLIENT_PORTAL_SECRET", "portal-secret", raising=False)

    with pytest.raises(HTTPException) as exc:
        require_scim_token("Bearer portal-secret")

    assert exc.value.status_code == 503


def test_require_scim_token_accepts_dedicated_token(monkeypatch):
    monkeypatch.setattr(settings, "SCIM_BEARER_TOKEN", "scim-secret", raising=False)

    require_scim_token("Bearer scim-secret")
