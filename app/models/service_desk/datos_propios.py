"""Datos del Service Desk que vivian en blobs JSON de `AppSetting` (migracion 200).

Auditoria 2026-11-22 (informe 03, A-MOD3 y §4.3): las sesiones de voz (telefono
y transcripcion), las fotos de un ticket al ponerlo en espera y las reglas de
los formularios dinamicos con su historial estaban en `app_settings` como
JSON: sin esquema, sin integridad referencial, fuera de la retencion y de la
supresion RGPD, y las escrituras concurrentes se pisaban (un solo blob por
empresa con TODAS las sesiones de voz).

Ahora cada cosa tiene su tabla, con `organization_id` obligatorio:

- `sd_voice_sessions`: una fila por llamada. El numero va cifrado
  (`caller_id_enc`, para mostrarlo al agente), con huella HMAC
  (`caller_id_hash`, para buscar y para el bloqueo legal / RGPD) y los 4
  ultimos digitos; entidades y transcripcion cifradas. Retencion y bloqueo
  legal: `app/db/bloqueo_legal.TIPOS["sd_voice_sessions"]`.
- `sd_ticket_hold_snapshots`: la foto del ticket al pasar a espera; se borra al
  reanudar (y en cascada con el ticket).
- `sd_dynamic_form_rules` (una por empresa) y `sd_dynamic_form_rule_history`.
"""
import uuid

from sqlalchemy import Column, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.sql import func

from app.db.base import Base


class VoiceSession(Base):
    """Sesion del agente de voz (IVR): una llamada."""
    __tablename__ = "sd_voice_sessions"

    id              = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    caller_id_hash  = Column(String(64), nullable=True, index=True)   # HMAC-SHA256 con SECRET_KEY
    caller_id_last4 = Column(String(4), nullable=True)
    caller_id_enc   = Column(Text, nullable=True)                     # encrypt_value(numero)
    channel         = Column(String(20), nullable=False, default="phone")
    status          = Column(String(20), nullable=False, default="active", index=True)
    intent          = Column(String(40), nullable=True)
    entities_enc    = Column(Text, nullable=True)                     # encrypt_value(JSON)
    transcript_enc  = Column(Text, nullable=True)                     # encrypt_value(JSON)
    ticket_id       = Column(String(36), ForeignKey("sd_tickets.id", ondelete="SET NULL"), nullable=True, index=True)
    resolution      = Column(String(40), nullable=True)
    created_at      = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at      = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    closed_at       = Column(DateTime(timezone=True), nullable=True)


class TicketHoldSnapshot(Base):
    """Estado, asignacion, nivel y prioridad de un ticket al ponerlo en espera."""
    __tablename__ = "sd_ticket_hold_snapshots"

    ticket_id       = Column(String(36), ForeignKey("sd_tickets.id", ondelete="CASCADE"), primary_key=True)
    organization_id = Column(String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    snapshot_json   = Column(Text, nullable=False)
    created_at      = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class DynamicFormRule(Base):
    """Reglas de los formularios dinamicos de una empresa (una fila por empresa)."""
    __tablename__ = "sd_dynamic_form_rules"
    __table_args__ = (Index("uq_sd_dynamic_form_rules_org", "organization_id", unique=True),)

    id              = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    regla_json      = Column(Text, nullable=False)
    version         = Column(Integer, nullable=False, default=1)
    updated_by      = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    updated_at      = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class DynamicFormRuleHistory(Base):
    """Version anterior de las reglas, guardada antes de cada cambio."""
    __tablename__ = "sd_dynamic_form_rule_history"

    id              = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    rule_id         = Column(String(36), ForeignKey("sd_dynamic_form_rules.id", ondelete="CASCADE"), nullable=False, index=True)
    regla_json      = Column(Text, nullable=False)
    reason          = Column(String(200), nullable=True)
    created_by      = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    created_at      = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)


__all__ = ["VoiceSession", "TicketHoldSnapshot", "DynamicFormRule", "DynamicFormRuleHistory"]
