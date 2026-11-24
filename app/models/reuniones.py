"""Asistente de reuniones: participantes, transcripción, audio, traducciones (19-11-2026).

Amplía `ai_meetings` / `ai_meeting_actions` (`app/models/ai_chat.py`). Diseño en
`docs/ASISTENTE_DE_REUNIONES.md`. Todas las tablas llevan `organization_id`
(filtro de tenant y RLS) y cuelgan de la reunión con borrado en cascada.
"""
from __future__ import annotations

import uuid

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.db.base import Base


def _id():
    return str(uuid.uuid4())


def _org():
    return Column(String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)


def _reunion():
    return Column(String(36), ForeignKey("ai_meetings.id", ondelete="CASCADE"), nullable=False, index=True)


class AIMeetingParticipant(Base):
    """Asistente o hablante de una reunión (de la empresa o externo) y su consentimiento."""
    __tablename__ = "ai_meeting_participants"

    id = Column(String(36), primary_key=True, default=_id)
    organization_id = _org()
    meeting_id = _reunion()
    user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    name = Column(String(255), nullable=True)
    email = Column(String(255), nullable=True, index=True)
    role = Column(String(20), nullable=False, default="asistente")   # organizador | asistente | hablante
    consent = Column(Boolean, nullable=True)                          # None = sin respuesta
    consent_method = Column(String(20), nullable=True)                # self | verbal | written | platform
    consent_at = Column(DateTime(timezone=True), nullable=True)
    consent_by = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    language = Column(String(10), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    meeting = relationship("AIMeeting", back_populates="participantes")


class AIMeetingSegment(Base):
    """Un turno de la transcripción: hablante, marcas de tiempo, texto e idioma."""
    __tablename__ = "ai_meeting_segments"
    __table_args__ = (Index("ix_ai_meeting_segments_meeting_order", "meeting_id", "orden"),)

    id = Column(String(36), primary_key=True, default=_id)
    organization_id = _org()
    meeting_id = _reunion()
    orden = Column(Integer, nullable=False, default=0)
    speaker = Column(String(255), nullable=True)
    participant_id = Column(String(36), ForeignKey("ai_meeting_participants.id", ondelete="SET NULL"),
                            nullable=True, index=True)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    start_ms = Column(Integer, nullable=True)
    end_ms = Column(Integer, nullable=True)
    text = Column(Text, nullable=False, default="")
    language = Column(String(10), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    meeting = relationship("AIMeeting", back_populates="segmentos")


class AIMeetingTranslation(Base):
    """Caché del análisis y la transcripción traducidos a un idioma."""
    __tablename__ = "ai_meeting_translations"
    __table_args__ = (UniqueConstraint("meeting_id", "language", name="uq_ai_meeting_translations_meeting_lang"),)

    id = Column(String(36), primary_key=True, default=_id)
    organization_id = _org()
    meeting_id = _reunion()
    language = Column(String(10), nullable=False)
    contenido = Column(Text, nullable=False)          # JSON: summary, decisions, risks, open_questions, actions, segments
    provider = Column(String(30), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    meeting = relationship("AIMeeting", back_populates="traducciones")


class AIMeetingAudio(Base):
    """Un trozo de audio guardado (retención corta, `expires_at`)."""
    __tablename__ = "ai_meeting_audio"

    id = Column(String(36), primary_key=True, default=_id)
    organization_id = _org()
    meeting_id = _reunion()
    seq = Column(Integer, nullable=False, default=0)
    storage_key = Column(String(500), nullable=False)
    bytes = Column(Integer, nullable=False, default=0)
    mime = Column(String(100), nullable=True)
    offset_ms = Column(Integer, nullable=False, default=0)
    transcribed = Column(Boolean, nullable=False, default=False)
    stt_provider = Column(String(30), nullable=True)
    expires_at = Column(DateTime(timezone=True), nullable=True, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    meeting = relationship("AIMeeting", back_populates="audios")


class AIMeetingEvent(Base):
    """Línea de tiempo de la reunión (estado, bot, consentimiento, escuchas, borrados)."""
    __tablename__ = "ai_meeting_events"

    id = Column(String(36), primary_key=True, default=_id)
    organization_id = _org()
    meeting_id = _reunion()
    tipo = Column(String(40), nullable=False)
    actor_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    datos = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)

    meeting = relationship("AIMeeting", back_populates="eventos")


class AIMeetingUserPrefs(Base):
    """Preferencias de cada persona: recoger sus reuniones y mandar el bot."""
    __tablename__ = "ai_meeting_user_prefs"
    # 23-11-2026: única POR empresa (una persona puede pertenecer a varias y
    # cada una tiene sus preferencias; la global daba 500 al guardar en la
    # segunda). Requiere migración: uq_ai_meeting_user_prefs_user -> _org_user.
    __table_args__ = (UniqueConstraint("organization_id", "user_id", name="uq_ai_meeting_user_prefs_org_user"),)

    id = Column(String(36), primary_key=True, default=_id)
    organization_id = _org()
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    collect_teams = Column(Boolean, nullable=False, default=False)
    collect_meet = Column(Boolean, nullable=False, default=False)
    # 19-11-2026: activado por defecto (el bot entra en las reuniones del calendario
    # de cada persona salvo que ella lo desactive en «Mis preferencias»).
    bot_for_my_calendar = Column(Boolean, nullable=False, default=True)
    language = Column(String(10), nullable=True)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
