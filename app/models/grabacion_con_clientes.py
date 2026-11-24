"""Consentimiento de grabación de las llamadas con clientes del portal (24-11-2026, migración 214).

Docs: docs/portal/CHAT_DEL_PORTAL.md §11. Una fila por cliente y por «ronda»
(cada vez que el operador propone grabar una llamada). Es la EVIDENCIA del
consentimiento: quién, cuándo, para qué llamada, qué texto aceptó (y su huella),
en qué idioma se le enseñó, desde qué IP y navegador, y cuándo lo retiró.

Sirve a los tres chats del portal (`channel`):

- `colaboracion`: pestaña «Chat» (`collaboration_calls`); la grabación es la
  `collaboration_recordings` de siempre (`recording_id`) y la transcripción la
  `collaboration_transcripts` / el asistente de reuniones;
- `conversacion`: conversaciones formales (`portal_conversation_calls`);
- `en_vivo`: chat en vivo de Soporte (`sd_channel_calls`).

`call_id` no lleva clave ajena: apunta a una de las tres tablas según `channel`.
`client_user_id` pasa a NULL si se borra la cuenta (la supresión RGPD borra la
fila, salvo bloqueo legal).
"""
from __future__ import annotations

import uuid

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func

from app.db.base import Base

#: Los tres chats del portal.
CANALES = ("colaboracion", "conversacion", "en_vivo")
#: Estados de una fila: pendiente de respuesta, concedido, denegado, retirado
#: (lo retiró el cliente durante la llamada) o cancelado (la ronda acabó sin
#: grabar: otro cliente dijo que no, el operador la retiró o colgaron).
ESTADOS = ("pending", "granted", "denied", "withdrawn", "cancelled")
#: Para qué se pide: solo grabar, o grabar y transcribir.
FINALIDADES = ("recording", "recording_transcript")


class PortalCallRecordingConsent(Base):
    __tablename__ = "portal_call_recording_consents"
    __table_args__ = (
        UniqueConstraint("organization_id", "channel", "call_id", "client_user_id", "round",
                         name="uq_portal_rec_consent_round"),
    )

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    channel = Column(String(20), nullable=False, index=True)
    call_id = Column(String(36), nullable=False, index=True)
    conversation_id = Column(String(36), nullable=False, index=True)
    round = Column(Integer, nullable=False, default=1)
    client_user_id = Column(String(36), ForeignKey("client_users.id", ondelete="SET NULL"), nullable=True, index=True)
    proposed_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    proposed_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    purpose = Column(String(30), nullable=False, default="recording")
    notice_text = Column(Text, nullable=False)
    notice_sha256 = Column(String(64), nullable=False)
    notice_lang = Column(String(10), nullable=True)
    status = Column(String(20), nullable=False, default="pending", index=True)
    decided_at = Column(DateTime(timezone=True), nullable=True)
    withdrawn_at = Column(DateTime(timezone=True), nullable=True)
    ip_address = Column(String(64), nullable=True)
    user_agent = Column(String(400), nullable=True)
    recording_started_at = Column(DateTime(timezone=True), nullable=True)
    recording_ended_at = Column(DateTime(timezone=True), nullable=True, index=True)
    recording_id = Column(String(36), nullable=True, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)
