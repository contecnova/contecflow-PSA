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
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, get_db
from app.models.esign import ESignEnvelope, ESignProvider, ESignStatus
from app.models.user import User
from app.services import esign_service

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

from app.services.esign_service import (
    docusign_configured as _docusign_configured,
    adobe_configured as _adobe_configured,
    create_provider_envelope as _create_provider_envelope,
)


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("", response_model=List[EnvelopeOut], summary="Listar solicitudes de firma")
def list_envelopes(
    document_id: Optional[int] = Query(None),
    status:      Optional[str] = Query(None),
    limit:       int           = Query(50, le=200),
    db:          Session       = Depends(get_db),
    current_user: User         = Depends(get_current_user),
):
    created_by_id = None if current_user.is_superadmin else current_user.id
    return esign_service.list_envelopes(
        db,
        created_by_id=created_by_id,
        document_id=document_id,
        status=status,
        limit=limit,
    )


@router.post("", response_model=EnvelopeOut, summary="Crear solicitud de firma")
def create_envelope(
    body:         EnvelopeCreate,
    db:           Session = Depends(get_db),
    current_user: User    = Depends(get_current_user),
):
    if not body.signers:
        raise HTTPException(400, "Al menos un firmante es obligatorio")

    doc = esign_service.get_document(db, body.document_id)
    if not doc:
        raise HTTPException(404, "Documento no encontrado")

    # Build a temporary envelope object for provider helper (no db write yet)
    _tmp = ESignEnvelope(
        document_id=body.document_id,
        provider=body.provider,
        subject=body.subject,
    )
    provider_result = _create_provider_envelope(_tmp, doc)

    return esign_service.create_envelope(
        db,
        document_id=body.document_id,
        created_by_id=current_user.id,
        provider=body.provider,
        subject=body.subject,
        message=body.message,
        expires_days=body.expires_days,
        signers=body.signers,
        provider_result=provider_result,
    )


@router.get("/{envelope_id}", response_model=EnvelopeOut, summary="Detalle de solicitud")
def get_envelope(
    envelope_id: int,
    db:          Session = Depends(get_db),
    _:           User    = Depends(get_current_user),
):
    env = esign_service.get_envelope(db, envelope_id)
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

    env = esign_service.get_envelope(db, envelope_id)
    if not env:
        raise HTTPException(404)

    env = esign_service.update_envelope_status(db, env, new_status)
    return {"id": envelope_id, "status": env.status}


@router.patch("/{envelope_id}/signers/{signer_id}/signed", summary="Marcar firmante como firmado")
def mark_signer_signed(
    envelope_id: int,
    signer_id:   int,
    db:          Session = Depends(get_db),
    _:           User    = Depends(get_current_user),
):
    signer = esign_service.get_signer(db, signer_id, envelope_id)
    if not signer:
        raise HTTPException(404, "Firmante no encontrado")

    envelope = esign_service.get_envelope(db, envelope_id)
    esign_service.mark_signer_signed(db, signer, envelope)
    return {"signer_id": signer_id, "signed": True}


@router.delete("/{envelope_id}", summary="Anular solicitud de firma")
def void_envelope(
    envelope_id: int,
    db:          Session = Depends(get_db),
    _:           User    = Depends(get_current_user),
):
    env = esign_service.get_envelope(db, envelope_id)
    if not env:
        raise HTTPException(404)
    if env.status == ESignStatus.completed:
        raise HTTPException(400, "No se puede anular una solicitud ya completada")
    esign_service.void_envelope(db, env)
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
        import re
        body = await request.body()
        payload_str = body.decode("utf-8", errors="replace")

        m_id = re.search(r'<EnvelopeID[^>]*>([^<]+)<', payload_str)
        m_st = re.search(r'<Status[^>]*>([^<]+)<', payload_str)

        if m_id and m_st:
            provider_id = m_id.group(1).strip()
            raw_status  = m_st.group(1).strip().lower()
            status_map  = {
                "sent":      ESignStatus.sent.value,
                "delivered": ESignStatus.delivered.value,
                "completed": ESignStatus.completed.value,
                "declined":  ESignStatus.declined.value,
                "voided":    ESignStatus.voided.value,
            }
            new_status = status_map.get(raw_status)
            if new_status:
                env = esign_service.get_envelope_by_provider_id(db, provider_id)
                if env:
                    esign_service.update_envelope_from_webhook(db, env, new_status)
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
        payload     = await request.json()
        agreement   = payload.get("agreement", {})
        provider_id = agreement.get("id")
        raw_status  = agreement.get("status", "").lower()

        status_map = {
            "out_for_signature": ESignStatus.sent.value,
            "signed":            ESignStatus.completed.value,
            "completed":         ESignStatus.completed.value,
            "declined":          ESignStatus.declined.value,
            "cancelled":         ESignStatus.voided.value,
        }
        new_status = status_map.get(raw_status)
        if new_status and provider_id:
            env = esign_service.get_envelope_by_provider_id(db, provider_id)
            if env:
                esign_service.update_envelope_from_webhook(db, env, new_status)
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
    stats = esign_service.get_stats(db)
    return {
        **stats,
        "providers": {
            "docusign_configured": _docusign_configured(),
            "adobe_configured":    _adobe_configured(),
        },
    }
