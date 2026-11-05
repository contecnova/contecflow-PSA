"""Calidad de la base de conocimiento (revisión 2026-11, lo que contecmind ya tenía).

- `KBCorrection`: la respuesta buena que un experto deja para una pregunta. Se
  aplica al momento a las preguntas parecidas, por delante de los artículos.
- `KBGap`: preguntas que llegaron sin ningún artículo que las respondiera. Es
  la lista de trabajo de quien escribe la base.
- `KBFinding`: avisos de la pasada diaria: artículos caducados y pares de
  artículos que se contradicen.
"""
import uuid

from sqlalchemy import Boolean, Column, DateTime, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.sql import func

from app.db.base import Base


class KBCorrection(Base):
    __tablename__ = "sd_kb_corrections"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String(36), ForeignKey("organizations.id"), nullable=True, index=True)
    question = Column(Text, nullable=False)
    answer = Column(Text, nullable=False)
    question_vec = Column(Text, nullable=True)       # JSON; vacío sin modelo de frases (se compara por palabras)
    is_public = Column(Boolean, default=False, nullable=False)   # también para los clientes del portal
    status = Column(String(20), default="active", nullable=False, index=True)  # active | archived
    article_id = Column(String(36), ForeignKey("sd_kb_articles.id", ondelete="SET NULL"), nullable=True)
    gap_id = Column(String(36), nullable=True)
    usage_count = Column(Integer, default=0, nullable=False)
    last_used_at = Column(DateTime(timezone=True), nullable=True)
    created_by = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class KBGap(Base):
    __tablename__ = "sd_kb_gaps"
    __table_args__ = (Index("uq_sd_kb_gaps_org_key", "organization_id", "question_key", unique=True),)

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String(36), ForeignKey("organizations.id"), nullable=True, index=True)
    question_key = Column(String(255), nullable=False)    # la pregunta normalizada (agrupa repeticiones)
    question = Column(Text, nullable=False)               # la última forma en que se preguntó
    source = Column(String(30), nullable=False)           # portal_chat | portal_bot | assistant
    times_asked = Column(Integer, default=1, nullable=False)
    status = Column(String(20), default="open", nullable=False, index=True)   # open | answered | dismissed
    article_id = Column(String(36), ForeignKey("sd_kb_articles.id", ondelete="SET NULL"), nullable=True)
    correction_id = Column(String(36), ForeignKey("sd_kb_corrections.id", ondelete="SET NULL"), nullable=True)
    first_asked_at = Column(DateTime(timezone=True), server_default=func.now())
    last_asked_at = Column(DateTime(timezone=True), server_default=func.now())
    closed_by = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)


class KBFinding(Base):
    __tablename__ = "sd_kb_findings"
    __table_args__ = (Index("uq_sd_kb_findings_org_key", "organization_id", "dedupe_key", unique=True),)

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String(36), ForeignKey("organizations.id"), nullable=True, index=True)
    kind = Column(String(20), nullable=False, index=True)        # stale | contradiction
    article_id = Column(String(36), ForeignKey("sd_kb_articles.id", ondelete="CASCADE"), nullable=False)
    other_article_id = Column(String(36), ForeignKey("sd_kb_articles.id", ondelete="CASCADE"), nullable=True)
    detail = Column(Text, nullable=True)
    score = Column(Float, nullable=True)
    dedupe_key = Column(String(255), nullable=False)
    status = Column(String(20), default="open", nullable=False, index=True)   # open | resolved | dismissed
    first_seen_at = Column(DateTime(timezone=True), server_default=func.now())
    last_seen_at = Column(DateTime(timezone=True), server_default=func.now())
    closed_by = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
