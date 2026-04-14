"""
E-firma endpoint — create, list, track and receive webhook callbacks for
DocuSign and Adobe Sign envelopes linked to documents.

Since DocuSign/Adobe Sign OAuth flows require user-specific tokens that live
outside NexusPM's server, this module uses the "service account" / JWT
grant flow (DocuSign) or the refresh-token approach (Adobe Sign).

For a minimal integration (common for internal PM tools), the flow is:
  1. Admin configures keys in Settings → E-firma
  2. A user clicks "Request signatures" on a document
  3. NexusPM calls the provider API to create an envelope
  4. The provider sends a webhook back when status changes
  5. NexusPM updates the envelope status and notifies the document owner

When NO provider keys are configured:
  - Envelopes are created in "manual" mode — NexusPM manages state only.
"""

import logging
from datetime import datetime, timedelta
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.deps import get_current_user, get_db
from app.models.documents import Document
from app.models.esign import ESignEnvelope, ESignProvider, ESignSigner, ESignStatus
from app.models.user import User

router = APIRouter()
_logger = logging.getLogger(__name__)


# ── Schemas ───────────────────────────────────────────────────────────────────

class SignerIn(BaseModel):
    name:          str
    email:         str
    routing_order: int = 1
    user_id:       Optional[int] = None


class EnvelopeCreate(BaseModel):
    document_id:  int
    subject:      str
    message:      Optional[str] = None
    provider:     ESignProvider = ESignProvider.manual
    signers:      List[SignerIn]
    expires_days: int = 7


class SignerOut(BaseModel):
    id:            int
    name:          str
    email:         str
    routing_order: int
    signed:        bool
    signed_at:     Optional[datetime]
    signing_url:   Optional[str]

    class Config:
        from_attributes = True


class EnvelopeOut(BaseModel):
    id:               int
    document_id:      int
    provider:         str
    subject:          Optional[str]
    message:          Optional[str]
    status:           str
    signing_url:      Optional[str]
    completed_pdf_path: Optional[str]
    sent_at:          Optional[datetime]
    completed_at:     Optional[datetime]
    expires_at:       Optional[datetime]
    created_at:       datetime
    signers:          List[SignerOut]

    class Config:
        from_attributes = True


# ── Provider helpers (stub-based — real OAuth requires external setup) ─────────

def _docusign_configured() -> bool:
    return bool(settings.DOCUSIGN_INTEGRATION_KEY and settings.DOCUSIGN_ACCOUNT_ID)


def _adobe_configured() -> bool:
    return bool(settings.ADOBE_SIGN_CLIENT_ID)


def _create_provider_envelope(envelope: ESignEnvelope, doc: Document) -> dict:
    """
    Attempt to create an envelope via the configured provider.
    Returns dict with {provider_envelope_id, signing_url, status} or raises.

    In this implementation, provider API calls are stubbed unless keys are set.
    Real implementation would use provider SDKs / HTTP calls here.
    """
    if envelope.provider == ESignProvider.docusign and _docusign_configured():
        # TODO: implement using DocuSign SDK (python-docusign-esign)
        # Placeholder — logs intent but does not call external API
        _logger.info(
            f"[eSign] DocuSign envelope intent for doc {doc.id}, "
            f"subject: {envelope.subject}"
        )
        return {
            "provider_envelope_id": None,
            "signing_url": None,
            "status": ESignStatus.draft,
            "is_stub": True,
            "stub_note": "Integración DocuSign pendiente de implementación. El sobre se ha registrado pero no se ha enviado al proveedor.",
        }

    if envelope.provider == ESignProvider.adobe_sign and _adobe_configured():
        _logger.info(
            f"[eSign] Adobe Sign envelope intent for doc {doc.id}, "
            f"subject: {envelope.subject}"
        )
        return {
            "provider_envelope_id": None,
            "signing_url": None,
            "status": ESignStatus.draft,
            "is_stub": True,
            "stub_note": "Integración Adobe Sign pendiente de implementación. El sobre se ha registrado pero no se ha enviado al proveedor.",
        }

    # Manual mode — no external provider
    return {
        "provider_envelope_id": None,
        "signing_url": None,
        "status": ESignStatus.draft,
    }


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("", response_model=List[EnvelopeOut], summary="Listar solicitudes de firma")
def list_envelopes(
    document_id: Optional[int] = Query(None),
    status:      Optional[str] = Query(None),
    limit:       int           = Query(50, le=200),
    db:          Session       = Depends(get_db),
    current_user: User         = Depends(get_current_user),
):
    q = db.query(ESignEnvelope)
    if not current_user.is_superadmin:
        q = q.filter(ESignEnvelope.created_by_id == current_user.id)
    if document_id: q = q.filter(ESignEnvelope.document_id == document_id)
    if status:      q = q.filter(ESignEnvelope.status == status)
    return q.order_by(ESignEnvelope.created_at.desc()).limit(limit).all()


@router.post("", response_model=EnvelopeOut, summary="Crear solicitud de firma")
def create_envelope(
    body:         EnvelopeCreate,
    db:           Session = Depends(get_db),
    current_user: User    = Depends(get_current_user),
):
    if not body.signers:
        raise HTTPException(400, "Al menos un firmante es obligatorio")

    doc = db.query(Document).filter(Document.id == body.document_id).first()
    if not doc:
        raise HTTPException(404, "Documento no encontrado")

    envelope = ESignEnvelope(
        document_id   = body.document_id,
        created_by_id = current_user.id,
        provider      = body.provider,
        subject       = body.subject,
        message       = body.message,
        expires_at    = datetime.utcnow() + timedelta(days=body.expires_days),
    )
    db.add(envelope)
    db.flush()

    # Add signers
    for s in body.signers:
        signer = ESignSigner(
            envelope_id   = envelope.id,
            name          = s.name,
            email         = s.email,
            routing_order = s.routing_order,
            user_id       = s.user_id,
        )
        db.add(signer)

    db.flush()

    # Attempt provider envelope creation
    provider_result = _create_provider_envelope(envelope, doc)
    envelope.provider_envelope_id = provider_result.get("provider_envelope_id")
    envelope.signing_url          = provider_result.get("signing_url")
    envelope.status               = provider_result.get("status", ESignStatus.draft)
    if envelope.status == ESignStatus.sent:
        envelope.sent_at = datetime.utcnow()

    db.commit()
    db.refresh(envelope)
    return envelope


@router.get("/{envelope_id}", response_model=EnvelopeOut, summary="Detalle de solicitud")
def get_envelope(
    envelope_id: int,
    db:          Session = Depends(get_db),
    _:           User    = Depends(get_current_user),
):
    env = db.query(ESignEnvelope).filter(ESignEnvelope.id == envelope_id).first()
    if not env:
        raise HTTPException(404, "Solicitud no encontrada")
    return env


@router.patch("/{envelope_id}/status", summary="Actualizar estado (manual o desde proveedor)")
def update_status(
    envelope_id: int,
    status:      str,
    db:          Session = Depends(get_db),
    _:           User    = Depends(get_current_user),
):
    try:
        new_status = ESignStatus(status)
    except ValueError:
        raise HTTPException(400, f"Estado inválido: {status}")

    env = db.query(ESignEnvelope).filter(ESignEnvelope.id == envelope_id).first()
    if not env:
        raise HTTPException(404)

    env.status     = new_status
    env.updated_at = datetime.utcnow()
    if new_status == ESignStatus.completed and not env.completed_at:
        env.completed_at = datetime.utcnow()
    if new_status == ESignStatus.sent and not env.sent_at:
        env.sent_at = datetime.utcnow()

    db.commit()
    return {"id": envelope_id, "status": env.status}


@router.patch("/{envelope_id}/signers/{signer_id}/signed", summary="Marcar firmante como firmado")
def mark_signer_signed(
    envelope_id: int,
    signer_id:   int,
    db:          Session = Depends(get_db),
    _:           User    = Depends(get_current_user),
):
    signer = db.query(ESignSigner).filter(
        ESignSigner.id          == signer_id,
        ESignSigner.envelope_id == envelope_id,
    ).first()
    if not signer:
        raise HTTPException(404, "Firmante no encontrado")

    signer.signed    = True
    signer.signed_at = datetime.utcnow()

    # Check if all signers have signed → auto-complete envelope
    envelope = db.query(ESignEnvelope).filter(ESignEnvelope.id == envelope_id).first()
    if envelope:
        all_signed = all(
            s.signed for s in db.query(ESignSigner).filter(ESignSigner.envelope_id == envelope_id).all()
        )
        if all_signed:
            envelope.status       = ESignStatus.completed
            envelope.completed_at = datetime.utcnow()

    db.commit()
    return {"signer_id": signer_id, "signed": True}


@router.delete("/{envelope_id}", summary="Anular solicitud de firma")
def void_envelope(
    envelope_id: int,
    db:          Session = Depends(get_db),
    _:           User    = Depends(get_current_user),
):
    env = db.query(ESignEnvelope).filter(ESignEnvelope.id == envelope_id).first()
    if not env:
        raise HTTPException(404)
    if env.status == ESignStatus.completed:
        raise HTTPException(400, "No se puede anular una solicitud ya completada")
    env.status     = ESignStatus.voided
    env.updated_at = datetime.utcnow()
    db.commit()
    return {"id": envelope_id, "status": "voided"}


# ── Provider webhooks (DocuSign Connect / Adobe Sign Webhooks) ────────────────

@router.post("/webhooks/docusign", summary="Webhook de DocuSign Connect")
async def docusign_webhook(
    request: Request,
    db:      Session = Depends(get_db),
):
    """
    DocuSign sends XML connect events. We parse the minimal subset needed
    to update envelope status. Signature validation requires Basic Auth or
    HMAC (DocuSign HMAC-SHA256) configured via DocuSign Connect console.
    """
    try:
        body = await request.body()
        payload_str = body.decode("utf-8", errors="replace")

        # Minimal XML parse — extract envelopeId and status
        import re
        m_id  = re.search(r'<EnvelopeID[^>]*>([^<]+)<', payload_str)
        m_st  = re.search(r'<Status[^>]*>([^<]+)<', payload_str)

        if m_id and m_st:
            provider_id = m_id.group(1).strip()
            raw_status  = m_st.group(1).strip().lower()
            status_map  = {
                "sent": ESignStatus.sent.value,
                "delivered": ESignStatus.delivered.value,
                "completed": ESignStatus.completed.value,
                "declined": ESignStatus.declined.value,
                "voided": ESignStatus.voided.value,
            }
            new_status = status_map.get(raw_status)
            if new_status:
                env = db.query(ESignEnvelope).filter(
                    ESignEnvelope.provider_envelope_id == provider_id
                ).first()
                if env:
                    env.status = new_status
                    if new_status == ESignStatus.completed.value and not env.completed_at:
                        env.completed_at = datetime.utcnow()
                    db.commit()
                    _logger.info(f"[eSign] DocuSign webhook: envelope {provider_id} → {new_status}")
    except Exception as e:
        _logger.warning(f"[eSign] DocuSign webhook parse error: {e}")

    return {"status": "ok"}


@router.post("/webhooks/adobe", summary="Webhook de Adobe Sign")
async def adobe_webhook(
    request: Request,
    db:      Session = Depends(get_db),
):
    try:
        payload = await request.json()
        agreement  = payload.get("agreement", {})
        provider_id = agreement.get("id")
        raw_status  = agreement.get("status", "").lower()

        status_map = {
            "out_for_signature": ESignStatus.sent.value,
            "signed":     ESignStatus.completed.value,
            "completed":  ESignStatus.completed.value,
            "declined":   ESignStatus.declined.value,
            "cancelled":  ESignStatus.voided.value,
        }
        new_status = status_map.get(raw_status)
        if new_status and provider_id:
            env = db.query(ESignEnvelope).filter(
                ESignEnvelope.provider_envelope_id == provider_id
            ).first()
            if env:
                env.status = new_status
                if new_status == ESignStatus.completed.value and not env.completed_at:
                    env.completed_at = datetime.utcnow()
                db.commit()
                _logger.info(f"[eSign] Adobe Sign webhook: agreement {provider_id} → {new_status}")
    except Exception as e:
        _logger.warning(f"[eSign] Adobe webhook parse error: {e}")

    return {"status": "ok"}


# ── Summary ───────────────────────────────────────────────────────────────────

@router.get("/summary/stats", summary="Resumen de firma electrónica")
def esign_stats(
    db: Session = Depends(get_db),
    _:  User    = Depends(get_current_user),
):
    from sqlalchemy import func
    rows = (
        db.query(ESignEnvelope.status, func.count().label("count"))
        .group_by(ESignEnvelope.status)
        .all()
    )
    total = sum(r.count for r in rows)
    by_status = {r.status: r.count for r in rows}
    return {
        "total":     total,
        "completed": by_status.get(ESignStatus.completed, 0),
        "pending":   by_status.get(ESignStatus.sent, 0) + by_status.get(ESignStatus.delivered, 0),
        "draft":     by_status.get(ESignStatus.draft, 0),
        "declined":  by_status.get(ESignStatus.declined, 0),
        "by_status": by_status,
        "providers": {
            "docusign_configured":  _docusign_configured(),
            "adobe_configured":     _adobe_configured(),
        },
    }
