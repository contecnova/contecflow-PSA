"""Inbound webhook authentication — Jira, DocuSign, Adobe Sign.

These webhooks mutate state (incl. legally-binding e-signature completion and
cross-tenant ticket changes), so they MUST be authenticated. Each verifier
fails CLOSED: when its secret is not configured, every request is rejected.
"""
import base64
import hashlib
import hmac

import pytest

from app.core.config import settings
from app.services import esign_service, jira_service


# ── Jira ────────────────────────────────────────────────────────────────────

def test_jira_webhook_rejected_when_secret_unset(monkeypatch):
    monkeypatch.setattr(settings, "JIRA_WEBHOOK_SECRET", "")
    assert jira_service.verify_jira_webhook(b"{}", "anything", None) is False
    assert jira_service.verify_jira_webhook(b"{}", None, "sha256=deadbeef") is False


def test_jira_webhook_accepts_matching_shared_token(monkeypatch):
    monkeypatch.setattr(settings, "JIRA_WEBHOOK_SECRET", "s3cret-token")
    assert jira_service.verify_jira_webhook(b"{}", "s3cret-token", None) is True
    assert jira_service.verify_jira_webhook(b"{}", "wrong", None) is False
    assert jira_service.verify_jira_webhook(b"{}", None, None) is False


def test_jira_webhook_accepts_matching_body_hmac(monkeypatch):
    secret = "s3cret-token"
    monkeypatch.setattr(settings, "JIRA_WEBHOOK_SECRET", secret)
    body = b'{"webhookEvent":"jira:issue_updated"}'
    sig = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    assert jira_service.verify_jira_webhook(body, None, sig) is True
    # tampered body fails
    assert jira_service.verify_jira_webhook(b"tampered", None, sig) is False


# ── DocuSign Connect HMAC ─────────────────────────────────────────────────────

def test_docusign_rejected_when_key_unset(monkeypatch):
    monkeypatch.setattr(settings, "DOCUSIGN_CONNECT_HMAC_KEY", "")
    assert esign_service.verify_docusign_signature(b"<xml/>", ["whatever"]) is False


def test_docusign_accepts_valid_signature(monkeypatch):
    key = "connect-hmac-key"
    monkeypatch.setattr(settings, "DOCUSIGN_CONNECT_HMAC_KEY", key)
    body = b"<DocuSignEnvelopeInformation/>"
    good = base64.b64encode(hmac.new(key.encode(), body, hashlib.sha256).digest()).decode()
    # one bad + one good header (DocuSign emits one per active key)
    assert esign_service.verify_docusign_signature(body, ["bad", good]) is True
    assert esign_service.verify_docusign_signature(body, ["bad", "still-bad"]) is False
    assert esign_service.verify_docusign_signature(b"tampered", [good]) is False


# ── Adobe Sign client-id ──────────────────────────────────────────────────────

def test_adobe_rejected_when_client_id_unset(monkeypatch):
    monkeypatch.setattr(settings, "ADOBE_SIGN_CLIENT_ID", "")
    assert esign_service.verify_adobe_client_id("some-id") is False


def test_adobe_accepts_matching_client_id(monkeypatch):
    monkeypatch.setattr(settings, "ADOBE_SIGN_CLIENT_ID", "client-123")
    assert esign_service.verify_adobe_client_id("client-123") is True
    assert esign_service.verify_adobe_client_id("client-999") is False
    assert esign_service.verify_adobe_client_id(None) is False
