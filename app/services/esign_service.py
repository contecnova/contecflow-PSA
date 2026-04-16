"""
Service layer for e-sign (ESignEnvelope / ESignSigner) database operations.
All db.query/add/commit/flush calls live here; the router only calls these functions.
"""
from datetime import datetime, timedelta
from typing import List, Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.documents import Document
from app.models.esign import ESignEnvelope, ESignProvider, ESignSigner, ESignStatus


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
        expires_at=datetime.utcnow() + timedelta(days=expires_days),
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
        envelope.sent_at = datetime.utcnow()

    db.commit()
    db.refresh(envelope)
    return envelope


def update_envelope_status(
    db: Session,
    envelope: ESignEnvelope,
    new_status: ESignStatus,
) -> ESignEnvelope:
    envelope.status = new_status
    envelope.updated_at = datetime.utcnow()
    if new_status == ESignStatus.completed and not envelope.completed_at:
        envelope.completed_at = datetime.utcnow()
    if new_status == ESignStatus.sent and not envelope.sent_at:
        envelope.sent_at = datetime.utcnow()
    db.commit()
    return envelope


def mark_signer_signed(
    db: Session,
    signer: ESignSigner,
    envelope: ESignEnvelope,
) -> None:
    signer.signed = True
    signer.signed_at = datetime.utcnow()

    all_signed = all(s.signed for s in get_signers_for_envelope(db, envelope.id))
    if all_signed:
        envelope.status = ESignStatus.completed
        envelope.completed_at = datetime.utcnow()

    db.commit()


def void_envelope(db: Session, envelope: ESignEnvelope) -> ESignEnvelope:
    envelope.status = ESignStatus.voided
    envelope.updated_at = datetime.utcnow()
    db.commit()
    return envelope


def update_envelope_from_webhook(
    db: Session,
    envelope: ESignEnvelope,
    new_status: str,
) -> None:
    envelope.status = new_status
    if new_status == ESignStatus.completed.value and not envelope.completed_at:
        envelope.completed_at = datetime.utcnow()
    db.commit()
