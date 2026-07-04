"""
Service layer for e-sign (ESignEnvelope / ESignSigner) database operations.
All db.query/add/commit/flush calls live here; the router only calls these functions.
"""
import logging
import os
from datetime import timedelta
from app.core.timeutil import utcnow
from typing import List, Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.documents import Document
from app.models.esign import ESignEnvelope, ESignProvider, ESignSigner, ESignStatus
from app.models.settings import AppSetting
from app.core.config import settings

_log = logging.getLogger(__name__)


# ── Inbound webhook authentication ──────────────────────────────────────────────
# Provider webhooks mutate envelope state (incl. legally-binding "completed"),
# so they MUST be authenticated. Both verifiers fail CLOSED: when the relevant
# secret is not configured, every request is rejected — never silently trusted.

def verify_docusign_signature(body: bytes, signature_headers: List[str]) -> bool:
    """Verify a DocuSign Connect HMAC-SHA256 signature.

    DocuSign sends one ``X-DocuSign-Signature-N`` header per active HMAC key
    (base64 of HMAC-SHA256 over the raw request body). We accept the request if
    any provided signature matches our configured key, using a constant-time
    comparison. Returns False when no key is configured (fail-closed).
    """
    import hmac
    import hashlib
    import base64

    secret = settings.DOCUSIGN_CONNECT_HMAC_KEY
    if not secret:
        return False
    expected = base64.b64encode(
        hmac.new(secret.encode(), body, hashlib.sha256).digest()
    ).decode()
    for header in signature_headers:
        if header and hmac.compare_digest(expected, header.strip()):
            return True
    return False


def verify_adobe_client_id(client_id_header: Optional[str]) -> bool:
    """Verify an Adobe Sign webhook via the ``X-AdobeSign-ClientId`` header.

    Adobe Sign authenticates webhooks by echoing the registered OAuth client id
    in every callback (and in the intent-verification handshake). We compare it
    in constant time against ``ADOBE_SIGN_CLIENT_ID``. Returns False when the
    client id is not configured (fail-closed).
    """
    import hmac

    expected = settings.ADOBE_SIGN_CLIENT_ID
    if not expected:
        return False
    if not client_id_header:
        return False
    return hmac.compare_digest(expected, client_id_header.strip())


# ── Read helpers ──────────────────────────────────────────────────────────────

def list_envelopes(
    db: Session,
    *,
    created_by_id: Optional[int] = None,
    document_id: Optional[int] = None,
    status: Optional[str] = None,
    limit: int = 50,
) -> List[ESignEnvelope]:
    q = db.query(ESignEnvelope)
    if created_by_id is not None:
        q = q.filter(ESignEnvelope.created_by_id == created_by_id)
    if document_id:
        q = q.filter(ESignEnvelope.document_id == document_id)
    if status:
        q = q.filter(ESignEnvelope.status == status)
    return q.order_by(ESignEnvelope.created_at.desc()).limit(limit).all()


def get_envelope(db: Session, envelope_id: int) -> Optional[ESignEnvelope]:
    return db.query(ESignEnvelope).filter(ESignEnvelope.id == envelope_id).first()


def get_envelope_by_provider_id(db: Session, provider_envelope_id: str) -> Optional[ESignEnvelope]:
    return (
        db.query(ESignEnvelope)
        .filter(ESignEnvelope.provider_envelope_id == provider_envelope_id)
        .first()
    )


def get_document(db: Session, document_id: int) -> Optional[Document]:
    return db.query(Document).filter(Document.id == document_id).first()


def get_signer(db: Session, signer_id: int, envelope_id: int) -> Optional[ESignSigner]:
    return (
        db.query(ESignSigner)
        .filter(ESignSigner.id == signer_id, ESignSigner.envelope_id == envelope_id)
        .first()
    )


def get_signers_for_envelope(db: Session, envelope_id: int) -> List[ESignSigner]:
    return db.query(ESignSigner).filter(ESignSigner.envelope_id == envelope_id).all()


def get_stats(db: Session) -> dict:
    rows = (
        db.query(ESignEnvelope.status, func.count().label("count"))
        .group_by(ESignEnvelope.status)
        .all()
    )
    total = sum(r.count for r in rows)
    by_status = {r.status: r.count for r in rows}
    return {
        "total": total,
        "by_status": by_status,
        "completed": by_status.get(ESignStatus.completed, 0),
        "pending": by_status.get(ESignStatus.sent, 0) + by_status.get(ESignStatus.delivered, 0),
        "draft": by_status.get(ESignStatus.draft, 0),
        "declined": by_status.get(ESignStatus.declined, 0),
    }


# ── Write helpers ─────────────────────────────────────────────────────────────

def create_envelope(
    db: Session,
    *,
    document_id: int,
    created_by_id: int,
    provider: ESignProvider,
    subject: str,
    message: Optional[str],
    expires_days: int,
    signers: list,
    provider_result: dict,
) -> ESignEnvelope:
    envelope = ESignEnvelope(
        document_id=document_id,
        created_by_id=created_by_id,
        provider=provider,
        subject=subject,
        message=message,
        expires_at=utcnow() + timedelta(days=expires_days),
    )
    db.add(envelope)
    db.flush()

    for s in signers:
        signer = ESignSigner(
            envelope_id=envelope.id,
            name=s.name,
            email=s.email,
            routing_order=s.routing_order,
            user_id=s.user_id,
        )
        db.add(signer)

    db.flush()

    envelope.provider_envelope_id = provider_result.get("provider_envelope_id")
    envelope.signing_url = provider_result.get("signing_url")
    envelope.status = provider_result.get("status", ESignStatus.draft)
    if envelope.status == ESignStatus.sent:
        envelope.sent_at = utcnow()

    db.commit()
    db.refresh(envelope)
    return envelope


def update_envelope_status(
    db: Session,
    envelope: ESignEnvelope,
    new_status: ESignStatus,
) -> ESignEnvelope:
    envelope.status = new_status
    envelope.updated_at = utcnow()
    if new_status == ESignStatus.completed and not envelope.completed_at:
        envelope.completed_at = utcnow()
    if new_status == ESignStatus.sent and not envelope.sent_at:
        envelope.sent_at = utcnow()
    db.commit()
    return envelope


def mark_signer_signed(
    db: Session,
    signer: ESignSigner,
    envelope: ESignEnvelope,
) -> None:
    signer.signed = True
    signer.signed_at = utcnow()

    all_signed = all(s.signed for s in get_signers_for_envelope(db, envelope.id))
    if all_signed:
        envelope.status = ESignStatus.completed
        envelope.completed_at = utcnow()

    db.commit()


def void_envelope(db: Session, envelope: ESignEnvelope) -> ESignEnvelope:
    envelope.status = ESignStatus.voided
    envelope.updated_at = utcnow()
    db.commit()
    return envelope


def update_envelope_from_webhook(
    db: Session,
    envelope: ESignEnvelope,
    new_status: str,
) -> None:
    envelope.status = new_status
    if new_status == ESignStatus.completed.value and not envelope.completed_at:
        envelope.completed_at = utcnow()
    db.commit()


# ── AppSetting helpers for e-sign config ──────────────────────────────────────

def _get_db_setting(db: Optional[Session], key: str) -> Optional[str]:
    """Read an AppSetting KV value; returns None if db is None or key missing."""
    if db is None:
        return None
    row = db.query(AppSetting).filter(AppSetting.key == key).first()
    return row.value if row and row.value else None


def _set_db_setting(db: Session, key: str, value: str) -> None:
    row = db.query(AppSetting).filter(AppSetting.key == key).first()
    if row:
        row.value = value
    else:
        db.add(AppSetting(key=key, value=value, description=f"E-firma config: {key}"))
    db.commit()


def _get_docusign_config(db: Optional[Session]) -> dict:
    """Merge env-var config with DB-stored config; DB takes precedence."""
    return {
        "integration_key": _get_db_setting(db, "esign.docusign_integration_key") or settings.DOCUSIGN_INTEGRATION_KEY,
        "secret_key": _get_db_setting(db, "esign.docusign_secret_key") or settings.DOCUSIGN_SECRET_KEY,
        "account_id": _get_db_setting(db, "esign.docusign_account_id") or settings.DOCUSIGN_ACCOUNT_ID,
        "base_url": _get_db_setting(db, "esign.docusign_base_url") or settings.DOCUSIGN_BASE_URL or "https://na1.docusign.net",
        "access_token": _get_db_setting(db, "esign.docusign_access_token"),
        "refresh_token": _get_db_setting(db, "esign.docusign_refresh_token"),
        "is_demo": (_get_db_setting(db, "esign.docusign_is_demo") or "true").lower() == "true",
    }


def _get_adobe_config(db: Optional[Session]) -> dict:
    """Merge env-var config with DB-stored config; DB takes precedence."""
    return {
        "client_id": _get_db_setting(db, "esign.adobe_sign_client_id") or settings.ADOBE_SIGN_CLIENT_ID,
        "client_secret": _get_db_setting(db, "esign.adobe_sign_client_secret") or settings.ADOBE_SIGN_CLIENT_SECRET,
        "base_url": _get_db_setting(db, "esign.adobe_sign_base_url") or settings.ADOBE_SIGN_BASE_URL,
        "access_token": _get_db_setting(db, "esign.adobe_sign_access_token"),
        "refresh_token": _get_db_setting(db, "esign.adobe_sign_refresh_token"),
    }


def _ensure_docusign_token(db: Session, cfg: dict) -> Optional[str]:
    """Return a valid DocuSign access token, refreshing if needed."""
    from app.services.esign_providers import docusign_refresh_token as _ds_refresh

    token = cfg.get("access_token")
    if token:
        return token

    refresh = cfg.get("refresh_token")
    if refresh and cfg.get("integration_key") and cfg.get("secret_key"):
        result = _ds_refresh(
            cfg["integration_key"], cfg["secret_key"], refresh,
            is_demo=cfg.get("is_demo", True),
        )
        if result["ok"]:
            _set_db_setting(db, "esign.docusign_access_token", result["access_token"])
            if result.get("refresh_token"):
                _set_db_setting(db, "esign.docusign_refresh_token", result["refresh_token"])
            _log.info("[eSign] DocuSign access token refreshed successfully")
            return result["access_token"]
        _log.warning("[eSign] DocuSign token refresh failed: %s", result.get("error"))

    return None


def _ensure_adobe_token(db: Session, cfg: dict) -> Optional[str]:
    """Return a valid Adobe Sign access token, refreshing if needed."""
    from app.services.esign_providers import adobe_sign_refresh_token as _ab_refresh

    token = cfg.get("access_token")
    if token:
        return token

    refresh = cfg.get("refresh_token")
    if refresh and cfg.get("client_id") and cfg.get("client_secret"):
        result = _ab_refresh(
            cfg["client_id"], cfg["client_secret"], refresh,
            base_url=cfg.get("base_url"),
        )
        if result["ok"]:
            _set_db_setting(db, "esign.adobe_sign_access_token", result["access_token"])
            if result.get("refresh_token"):
                _set_db_setting(db, "esign.adobe_sign_refresh_token", result["refresh_token"])
            _log.info("[eSign] Adobe Sign access token refreshed successfully")
            return result["access_token"]
        _log.warning("[eSign] Adobe Sign token refresh failed: %s", result.get("error"))

    return None


def _read_document_bytes(doc: Document, db: Optional[Session]) -> tuple[bytes, str, str]:
    """Return (file_content_bytes, file_name, file_extension) for the document's latest version.

    Tries S3 first, then local filesystem. Falls back to a 1-byte placeholder
    on error so the envelope is still registered.
    """
    # Get latest version
    latest_version = None
    if doc.versions:
        latest_version = sorted(doc.versions, key=lambda v: v.version_num, reverse=True)[0]
    elif db is not None:
        from app.models.documents import DocumentVersion  # noqa: PLC0415
        latest_version = (
            db.query(DocumentVersion)
            .filter(DocumentVersion.document_id == doc.id)
            .order_by(DocumentVersion.version_num.desc())
            .first()
        )

    if latest_version is None:
        _log.error("[eSign] Document %s has no stored versions; cannot send for signature", doc.id)
        raise ValueError(
            f"Document {doc.id} has no content to sign (no stored versions)."
        )

    file_name = latest_version.file_name or "document.pdf"
    ext = os.path.splitext(file_name)[1].lstrip(".").lower() or "pdf"
    file_key = latest_version.file_key

    # Try S3
    try:
        import boto3  # noqa: PLC0415
        bucket = getattr(settings, "AWS_S3_BUCKET", None) or os.environ.get("AWS_S3_BUCKET")
        if bucket and file_key:
            s3 = boto3.client("s3")
            obj = s3.get_object(Bucket=bucket, Key=file_key)
            return obj["Body"].read(), file_name, ext
    except Exception as exc:
        _log.debug("[eSign] S3 read failed, trying local: %s", exc)

    # Try local filesystem
    upload_root = getattr(settings, "UPLOAD_DIR", None) or os.environ.get("UPLOAD_DIR", "uploads")
    local_path = os.path.join(upload_root, file_key.lstrip("/"))
    if os.path.exists(local_path):
        with open(local_path, "rb") as fh:
            return fh.read(), file_name, ext

    _log.error("[eSign] Could not read document %s from S3 or local path %s", doc.id, local_path)
    raise ValueError(
        f"Document {doc.id} content could not be retrieved from storage; refusing "
        f"to send an empty document for signature."
    )


# ── Provider helpers ───────────────────────────────────────────────────────────

def docusign_configured(db: Optional[Session] = None) -> bool:
    cfg = _get_docusign_config(db)
    return bool(cfg["integration_key"] and cfg["account_id"])


def adobe_configured(db: Optional[Session] = None) -> bool:
    cfg = _get_adobe_config(db)
    return bool(cfg["client_id"])


def create_provider_envelope(envelope, doc, db: Optional[Session] = None) -> dict:
    """
    Create an envelope/agreement via the configured provider.
    Returns dict with {provider_envelope_id, signing_url, status}.
    Falls back to manual mode when provider is not configured or API call fails.
    """
    from app.services.esign_providers import (  # noqa: PLC0415
        docusign_create_envelope as _ds_create,
        adobe_sign_create_agreement as _ab_create,
    )

    # ── DocuSign ──────────────────────────────────────────────────────────────
    if envelope.provider == ESignProvider.docusign:
        cfg = _get_docusign_config(db)
        if not cfg["integration_key"] or not cfg["account_id"]:
            _log.info("[eSign] DocuSign not configured; falling back to manual mode")
            return {"provider_envelope_id": None, "signing_url": None, "status": ESignStatus.draft}

        token = _ensure_docusign_token(db, cfg) if db else cfg.get("access_token")
        if not token:
            raise ValueError(
                "DocuSign access token not available. Complete OAuth at /esign/auth/docusign/authorize"
            )

        doc_bytes, doc_name, doc_ext = _read_document_bytes(doc, db)
        signers = _envelope_signers_from_envelope(envelope, db)

        result = _ds_create(
            access_token=token,
            account_id=cfg["account_id"],
            base_url=cfg["base_url"],
            subject=envelope.subject or "Document for signature",
            message=envelope.message,
            signers=signers,
            doc_name=doc_name,
            doc_content=doc_bytes,
            doc_extension=doc_ext,
            send_immediately=True,
        )

        if not result["ok"]:
            # If 401, token expired — clear stored token so next call will refresh
            if "401" in str(result.get("error", "")):
                if db:
                    _set_db_setting(db, "esign.docusign_access_token", "")
            raise ValueError(f"DocuSign envelope creation failed: {result.get('error')}")

        _log.info("[eSign] DocuSign envelope created: %s", result.get("envelope_id"))
        return {
            "provider_envelope_id": result["envelope_id"],
            "signing_url": None,
            "status": ESignStatus.sent,
        }

    # ── Adobe Sign ────────────────────────────────────────────────────────────
    if envelope.provider == ESignProvider.adobe_sign:
        cfg = _get_adobe_config(db)
        if not cfg["client_id"]:
            _log.info("[eSign] Adobe Sign not configured; falling back to manual mode")
            return {"provider_envelope_id": None, "signing_url": None, "status": ESignStatus.draft}

        token = _ensure_adobe_token(db, cfg) if db else cfg.get("access_token")
        if not token:
            raise ValueError(
                "Adobe Sign access token not available. Complete OAuth at /esign/auth/adobe/authorize"
            )

        doc_bytes, doc_name, doc_ext = _read_document_bytes(doc, db)
        signers = _envelope_signers_from_envelope(envelope, db)

        result = _ab_create(
            access_token=token,
            base_url=cfg["base_url"],
            subject=envelope.subject or "Document for signature",
            message=envelope.message,
            signers=signers,
            doc_name=doc_name,
            doc_content=doc_bytes,
            doc_extension=doc_ext,
        )

        if not result["ok"]:
            if "401" in str(result.get("error", "")):
                if db:
                    _set_db_setting(db, "esign.adobe_sign_access_token", "")
            raise ValueError(f"Adobe Sign agreement creation failed: {result.get('error')}")

        _log.info("[eSign] Adobe Sign agreement created: %s", result.get("agreement_id"))
        return {
            "provider_envelope_id": result["agreement_id"],
            "signing_url": None,
            "status": ESignStatus.sent,
        }

    # ── Manual / unknown provider ─────────────────────────────────────────────
    return {"provider_envelope_id": None, "signing_url": None, "status": ESignStatus.draft}


def _envelope_signers_from_envelope(envelope, db: Optional[Session]) -> list:
    """Extract signer dicts from the envelope's signers relationship or DB query."""
    signers_list = []
    if hasattr(envelope, "signers") and envelope.signers:
        for s in envelope.signers:
            signers_list.append({
                "name": s.name,
                "email": s.email,
                "routing_order": s.routing_order,
            })
    return signers_list
