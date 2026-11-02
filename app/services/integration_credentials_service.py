"""Per-organization integration credential storage with field-level encryption.

This service is the storage half of Phase 2 of the env → UI migration (see
docs/CONFIG_MIGRATION_INVENTORY.md). It exposes a declarative provider
registry: each provider lists the keys it owns and which ones are secret.
Secret values are encrypted with :func:`app.core.encryption.encrypt_value`
before persistence; reads expose a ``masked=True`` flag instead of the
plaintext so the UI can show "•••• set" without ever revealing the secret
again.

Consumers should call ``get_credential(db, provider, key, org_id)`` (or its
batch sibling ``get_provider_config``) and treat the result as the source of
truth: if the DB row is missing the helper falls back to the legacy env
variable so we can migrate provider-by-provider without breaking anything.
"""
from __future__ import annotations

import logging
import threading
import time
from typing import Any, Optional

from sqlalchemy.orm import Session

from app.core.config import settings as _env_settings
from app.core.encryption import decrypt_value, encrypt_value
from app.models.settings import IntegrationCredential

logger = logging.getLogger("contecflow.integrations")

_CACHE_TTL_SECONDS = 60.0
_cache: dict[tuple[str, str, Optional[str]], tuple[float, Optional[str]]] = {}
_cache_lock = threading.Lock()


# ── Provider registry ─────────────────────────────────────────────────────────
# Each provider lists its fields as (key, type, secret?, label, env_fallback).
# ``env_fallback`` is the name of the corresponding setting in app.core.config —
# used to keep behaviour identical until a DB row exists. ``type`` is one of
# "str" | "int" | "bool" — drives UI input rendering and validation.

ProviderField = tuple[str, str, bool, str, Optional[str]]

PROVIDER_REGISTRY: dict[str, dict[str, Any]] = {
    "smtp": {
        "label": "SMTP (outbound email)",
        "fields": [
            ("host",     "str",  False, "Host",        "SMTP_HOST"),
            ("port",     "int",  False, "Port",        "SMTP_PORT"),
            ("user",     "str",  False, "User",        "SMTP_USER"),
            ("password", "str",  True,  "Password",    "SMTP_PASS"),
            ("from",     "str",  False, "From address","SMTP_FROM"),
        ],
    },
    "sd_mailbox": {
        "label": "Service Desk mailbox (inbound email)",
        "fields": [
            ("protocol", "str",  False, "Protocol: imap or graph", None),
            ("host",     "str",  False, "IMAP host",               None),
            ("port",     "int",  False, "IMAP port (993)",         None),
            ("user",     "str",  False, "IMAP user",               None),
            ("password", "str",  True,  "IMAP password",           None),
            ("folder",   "str",  False, "Folder (INBOX)",          None),
            ("mailbox",  "str",  False, "Microsoft 365 mailbox (graph)", None),
        ],
    },
    "contecmind": {
        "label": "contecmind (document search)",
        "fields": [
            ("base_url",      "str", False, "Base URL",      None),
            ("client_id",     "str", False, "Client ID",     None),
            ("client_secret", "str", True,  "Client secret", None),
        ],
    },
    "monitoring": {
        "label": "Monitoring alerts (inbound)",
        "fields": [
            ("ingest_token", "str", True, "Ingest token (X-Contecflow-Event-Token)", None),
        ],
    },
    "aws_s3": {
        "label": "AWS S3 (documents)",
        "fields": [
            ("bucket",     "str", False, "Bucket",     "AWS_S3_BUCKET"),
            ("region",     "str", False, "Region",     "AWS_REGION"),
            ("access_key", "str", True,  "Access key", "AWS_ACCESS_KEY"),
            ("secret_key", "str", True,  "Secret key", "AWS_SECRET_KEY"),
        ],
    },
    "ms_graph": {
        "label": "Microsoft 365 / Graph",
        "fields": [
            ("tenant_id",         "str", False, "Tenant ID",          "AZURE_TENANT_ID"),
            ("client_id",         "str", False, "Client ID",          "AZURE_CLIENT_ID"),
            ("client_secret",     "str", True,  "Client secret",      "AZURE_CLIENT_SECRET"),
            ("teams_webhook",     "str", True,  "Teams webhook URL",  "TEAMS_WEBHOOK_URL"),
            ("teams_bot_app_id",  "str", False, "Teams bot App ID",   "TEAMS_BOT_APP_ID"),
            ("sharepoint_site_id","str", False, "SharePoint site ID", "SHAREPOINT_SITE_ID"),
        ],
    },
    "slack": {
        "label": "Slack",
        "fields": [
            ("webhook_url",    "str", True, "Webhook URL",    "SLACK_WEBHOOK_URL"),
            ("signing_secret", "str", True, "Signing secret", "SLACK_SIGNING_SECRET"),
        ],
    },
    "twilio": {
        "label": "Twilio (SMS / WhatsApp)",
        "fields": [
            ("account_sid", "str", False, "Account SID",  None),
            ("auth_token",  "str", True,  "Auth token",   None),
            ("from_number", "str", False, "From number",  None),
        ],
    },
    "stripe": {
        "label": "Stripe (payments)",
        "fields": [
            ("publishable_key", "str", False, "Publishable key", "STRIPE_PUBLISHABLE_KEY"),
            ("secret_key",      "str", True,  "Secret key",      "STRIPE_SECRET_KEY"),
            ("webhook_secret",  "str", True,  "Webhook secret",  "STRIPE_WEBHOOK_SECRET"),
        ],
    },
    "docusign": {
        "label": "DocuSign (e-signature)",
        "fields": [
            ("integration_key", "str", True,  "Integration key", "DOCUSIGN_INTEGRATION_KEY"),
            ("secret_key",      "str", True,  "Secret key",      "DOCUSIGN_SECRET_KEY"),
            ("account_id",      "str", False, "Account ID",      "DOCUSIGN_ACCOUNT_ID"),
            ("base_url",        "str", False, "Base URL",        "DOCUSIGN_BASE_URL"),
        ],
    },
    "adobe_sign": {
        "label": "Adobe Sign (e-signature)",
        "fields": [
            ("client_id",     "str", False, "Client ID",     "ADOBE_SIGN_CLIENT_ID"),
            ("client_secret", "str", True,  "Client secret", "ADOBE_SIGN_CLIENT_SECRET"),
            ("base_url",      "str", False, "Base URL",      "ADOBE_SIGN_BASE_URL"),
        ],
    },
    "ai_providers": {
        "label": "AI provider keys",
        "fields": [
            ("anthropic_api_key", "str", True, "Anthropic API key", "ANTHROPIC_API_KEY"),
            ("openai_api_key",    "str", True, "OpenAI API key",    "OPENAI_API_KEY"),
            ("azure_speech_key",  "str", True, "Azure Speech key",  "AZURE_SPEECH_KEY"),
            ("google_stt_api_key","str", True, "Google STT API key","GOOGLE_STT_API_KEY"),
        ],
    },
    "webhooks": {
        "label": "Inbound webhooks (signing secrets)",
        "fields": [
            ("webhook_secret",      "str", True, "Outbound webhook signing secret",  "WEBHOOK_SECRET"),
            ("inbound_email_secret","str", True, "Inbound email relay secret",       "INBOUND_EMAIL_SECRET"),
            ("github_secret",       "str", True, "GitHub webhook secret",            "GITHUB_WEBHOOK_SECRET"),
            ("gitlab_secret",       "str", True, "GitLab webhook secret",            "GITLAB_WEBHOOK_SECRET"),
            ("scim_bearer_token",   "str", True, "SCIM bearer token",                "SCIM_BEARER_TOKEN"),
        ],
    },
    "open_exchange_rates": {
        "label": "OpenExchangeRates (currency)",
        "fields": [
            ("app_id", "str", True, "App ID", "OPEN_EXCHANGE_RATES_APP_ID"),
        ],
    },
}


def _field_spec(provider: str, key: str) -> Optional[ProviderField]:
    spec = PROVIDER_REGISTRY.get(provider)
    if spec is None:
        return None
    return next((f for f in spec["fields"] if f[0] == key), None)


def _coerce(value: str, type_: str) -> Any:
    if value is None or value == "":
        return None
    if type_ == "int":
        return int(value)
    if type_ == "bool":
        return str(value).strip().lower() in {"1", "true", "yes", "on", "y"}
    return value


def _env_value(env_name: Optional[str]) -> Any:
    if not env_name:
        return None
    return getattr(_env_settings, env_name, None)


def _invalidate_cache_local(provider: Optional[str] = None) -> None:
    """In-process only. Called by the pub/sub subscriber after a remote write."""
    with _cache_lock:
        if provider is None:
            _cache.clear()
            return
        for ck in list(_cache.keys()):
            if ck[0] == provider:
                _cache.pop(ck, None)


def invalidate_cache(provider: Optional[str] = None) -> None:
    """Drop cache entries locally AND broadcast to other workers via Redis pub/sub."""
    _invalidate_cache_local(provider)
    try:
        from app.core.settings_pubsub import publish_invalidation
        publish_invalidation("integration", provider)
    except Exception:
        logger.debug("invalidate_cache: fallo best-effort ignorado", exc_info=True)


def _read_row(db: Session, provider: str, key: str, org_id: Optional[str]) -> Optional[IntegrationCredential]:
    q = db.query(IntegrationCredential).filter(
        IntegrationCredential.provider == provider,
        IntegrationCredential.key == key,
    )
    if org_id is None:
        return q.filter(IntegrationCredential.organization_id.is_(None)).first()
    row = q.filter(IntegrationCredential.organization_id == org_id).first()
    if row is not None:
        return row
    return q.filter(IntegrationCredential.organization_id.is_(None)).first()


def _resolve_value(row: Optional[IntegrationCredential], field: ProviderField) -> Any:
    _, type_, is_secret, _, env_name = field
    if row is not None:
        raw = decrypt_value(row.value_encrypted) if is_secret else row.value
        if raw is not None and raw != "":
            return _coerce(raw, type_)
    return _env_value(env_name)


def get_credential(db: Session, provider: str, key: str, org_id: Optional[str] = None) -> Any:
    """Return the effective value (DB row → env fallback). Cached per (provider,key,org)."""
    field = _field_spec(provider, key)
    if field is None:
        raise ValueError(f"unknown integration field: {provider}.{key}")

    ck = (provider, key, org_id)
    now = time.time()
    with _cache_lock:
        entry = _cache.get(ck)
        if entry is not None and entry[0] > now:
            return entry[1]

    row = _read_row(db, provider, key, org_id)
    value = _resolve_value(row, field)
    with _cache_lock:
        _cache[ck] = (now + _CACHE_TTL_SECONDS, value)
    return value


def get_provider_config(db: Session, provider: str, org_id: Optional[str] = None) -> dict[str, Any]:
    """Bulk-load every key of a provider as ``{key: value}``."""
    spec = PROVIDER_REGISTRY.get(provider)
    if spec is None:
        raise ValueError(f"unknown provider: {provider}")
    return {f[0]: get_credential(db, provider, f[0], org_id) for f in spec["fields"]}


# ── Read for UI: never returns secrets in plaintext ──────────────────────────

def describe_provider(db: Session, provider: str, org_id: Optional[str] = None) -> dict[str, Any]:
    spec = PROVIDER_REGISTRY.get(provider)
    if spec is None:
        raise ValueError(f"unknown provider: {provider}")

    items: list[dict[str, Any]] = []
    for key, type_, is_secret, label, env_name in spec["fields"]:
        row = _read_row(db, provider, key, org_id)
        has_db_value = row is not None and (
            (row.value_encrypted not in (None, "")) if is_secret else (row.value not in (None, ""))
        )
        env_val = _env_value(env_name)
        items.append({
            "key": key,
            "type": type_,
            "label": label,
            "is_secret": is_secret,
            # Never echo a secret back. For non-secret fields show the value so
            # the admin can see what's configured.
            "value": (None if is_secret else (_coerce(row.value, type_) if has_db_value else env_val)),
            "configured": bool(has_db_value or (env_val is not None and env_val != "")),
            "source": "db" if has_db_value else ("env" if (env_val is not None and env_val != "") else "unset"),
        })
    return {"provider": provider, "label": spec["label"], "items": items}


def list_providers() -> list[dict[str, Any]]:
    return [{"provider": p, "label": spec["label"]} for p, spec in PROVIDER_REGISTRY.items()]


# ── Write ────────────────────────────────────────────────────────────────────

def _upsert_credential(
    db: Session,
    provider: str,
    key: str,
    value: Optional[str],
    org_id: Optional[str],
    updated_by: Optional[str],
) -> IntegrationCredential:
    field = _field_spec(provider, key)
    if field is None:
        raise ValueError(f"unknown integration field: {provider}.{key}")
    _, type_, is_secret, _, _ = field

    # Validate type by attempting a coercion (raises ValueError on bad input).
    if value not in (None, ""):
        try:
            _coerce(value, type_)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"invalid value for {provider}.{key} (expected {type_}): {exc}") from exc

    row = (
        db.query(IntegrationCredential)
        .filter(
            IntegrationCredential.provider == provider,
            IntegrationCredential.key == key,
            IntegrationCredential.organization_id == org_id if org_id is not None
            else IntegrationCredential.organization_id.is_(None),
        )
        .first()
    )

    is_blank = value is None or value == ""

    if row is None:
        if is_blank:
            return None  # nothing to write — admin cleared an already-empty field
        row = IntegrationCredential(
            provider=provider,
            key=key,
            organization_id=org_id,
            is_secret=is_secret,
            updated_by=updated_by,
        )
        if is_secret:
            row.value_encrypted = encrypt_value(value)
        else:
            row.value = value
        db.add(row)
    else:
        if is_blank:
            # Blank → admin wants to reset and fall back to env.
            db.delete(row)
            db.commit()
            return None
        if is_secret:
            row.value_encrypted = encrypt_value(value)
            row.value = None
        else:
            row.value = value
            row.value_encrypted = None
        row.is_secret = is_secret
        row.updated_by = updated_by

    db.commit()
    if row.id is not None:
        db.refresh(row)
    return row


def set_credential(
    db: Session,
    provider: str,
    key: str,
    value: Optional[str],
    org_id: Optional[str],
    updated_by: Optional[str] = None,
    *,
    actor_ip: Optional[str] = None,
    actor_ua: Optional[str] = None,
) -> dict[str, Any]:
    field = _field_spec(provider, key)
    if field is None:
        raise ValueError(f"unknown integration field: {provider}.{key}")
    _, type_, is_secret, _, _ = field

    # Capture old value pre-write (raw — encrypted form for secrets).
    pre_row = _read_row(db, provider, key, org_id)
    if pre_row is not None:
        old_raw = pre_row.value_encrypted if is_secret else pre_row.value
    else:
        old_raw = None

    row = _upsert_credential(db, provider, key, value, org_id, updated_by)
    invalidate_cache(provider)

    # Persistent audit log. For secrets we pass the ENCRYPTED ciphertext to
    # record_change as the "raw" — the audit service hashes it (sha256), so
    # the plaintext never reaches the audit table either.
    new_raw: Optional[str] = None
    if row is not None:
        new_raw = row.value_encrypted if is_secret else row.value

    logger.info(
        "integration_credential_changed provider=%s key=%s org=%s by=%s reset=%s secret=%s",
        provider, key, org_id, updated_by, row is None, is_secret,
    )

    try:
        from app.services.settings_audit_service import record_change
        record_change(
            db,
            scope="integration",
            provider=provider,
            key=key,
            is_secret=is_secret,
            old_value=old_raw,
            new_value=new_raw,
            actor_id=updated_by,
            actor_ip=actor_ip,
            actor_ua=actor_ua,
            organization_id=org_id,
        )
    except Exception:
        logger.debug("set_credential: fallo best-effort ignorado", exc_info=True)

    if row is None:
        return {"provider": provider, "key": key, "configured": False, "source": "unset"}
    return {
        "provider": provider,
        "key": key,
        "configured": True,
        "source": "db",
        "is_secret": is_secret,
    }


__all__ = [
    "PROVIDER_REGISTRY",
    "list_providers",
    "describe_provider",
    "get_credential",
    "get_provider_config",
    "set_credential",
    "invalidate_cache",
]
