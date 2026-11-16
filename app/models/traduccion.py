"""Traduccion en tiempo real (16-11-2026, migracion 175).

Lo que se guarda de la traduccion operador <-> cliente. Todo por empresa
(`organization_id`): ni la cache ni el glosario se comparten entre empresas.

- `TranslationCacheEntry` (`translation_cache`): cada texto traducido una vez,
  por (texto, origen, destino, glosario). La segunda vez no se paga. La clave es
  un SHA-256; el texto original NO se guarda aqui (ya esta en su mensaje).
- `MessageTranslation` (`message_translations`): la traduccion de un campo de
  un mensaje a un idioma — comentario de ticket, ticket (titulo y descripcion),
  mensaje de un canal, mensaje del chat interno. Una fila por
  (mensaje, campo, idioma destino). `origin` dice de donde sale: `auto` (el
  servicio) o `author` (lo que escribio de verdad el operador cuando lo que se
  envio al cliente es la traduccion). Si el operador corrigio la vista previa
  antes de enviar, lo dice la auditoria (`TRANSLATE`, `origin=edited`). Es el
  rastro auditable: quien, cuando y con que proveedor.
- `TranslationGlossaryTerm` (`translation_glossary_terms`): terminos de la
  empresa que no se traducen (`translations` vacio) o que se traducen siempre
  igual (`translations` = {idioma: texto}).
- `KBArticleTranslation` (`sd_kb_article_translations`): la version de un
  articulo de la base de conocimiento en un idioma del portal, con su revision
  (`draft` -> `in_review` -> `published` | `rejected`). El portal solo sirve las
  publicadas; `source_updated_at` dice si el original cambio despues.
"""
import uuid

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.sql import func

from app.db.base import Base


def _id():
    return str(uuid.uuid4())


class TranslationCacheEntry(Base):
    __tablename__ = "translation_cache"
    __table_args__ = (UniqueConstraint("organization_id", "cache_key", name="uq_translation_cache_org_key"),)

    id = Column(String(36), primary_key=True, default=_id)
    organization_id = Column(String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=True, index=True)
    cache_key = Column(String(64), nullable=False)
    source_language = Column(String(16), nullable=True)
    target_language = Column(String(16), nullable=False)
    translated_text = Column(Text, nullable=False)
    provider = Column(String(30), nullable=False)
    characters = Column(Integer, nullable=False, default=0, server_default="0")
    hits = Column(Integer, nullable=False, default=0, server_default="0")
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    last_used_at = Column(DateTime(timezone=True), nullable=True, index=True)


class MessageTranslation(Base):
    __tablename__ = "message_translations"
    __table_args__ = (UniqueConstraint("organization_id", "message_type", "message_id", "field", "target_language",
                                       name="uq_message_translation"),)

    id = Column(String(36), primary_key=True, default=_id)
    organization_id = Column(String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=True, index=True)
    # ticket_comment | ticket | channel_message | chat_message
    message_type = Column(String(30), nullable=False)
    message_id = Column(String(36), nullable=False, index=True)
    field = Column(String(30), nullable=False, default="body", server_default="body")
    source_language = Column(String(16), nullable=True)
    target_language = Column(String(16), nullable=False)
    text = Column(Text, nullable=False)
    # auto | author
    origin = Column(String(10), nullable=False, default="auto", server_default="auto")
    provider = Column(String(30), nullable=True)
    created_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class TranslationGlossaryTerm(Base):
    __tablename__ = "translation_glossary_terms"
    __table_args__ = (UniqueConstraint("organization_id", "term", name="uq_translation_glossary_org_term"),)

    id = Column(String(36), primary_key=True, default=_id)
    organization_id = Column(String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=True, index=True)
    term = Column(String(200), nullable=False)
    # JSON {idioma: texto}; vacio: el termino no se traduce.
    translations = Column(Text, nullable=True)
    case_sensitive = Column(Boolean, nullable=False, default=False, server_default="0")
    notes = Column(String(500), nullable=True)
    is_active = Column(Boolean, nullable=False, default=True, server_default="1")
    created_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())


class KBArticleTranslation(Base):
    __tablename__ = "sd_kb_article_translations"
    __table_args__ = (UniqueConstraint("article_id", "language", name="uq_sd_kb_article_translation_lang"),)

    id = Column(String(36), primary_key=True, default=_id)
    organization_id = Column(String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=True, index=True)
    article_id = Column(String(36), ForeignKey("sd_kb_articles.id", ondelete="CASCADE"), nullable=False, index=True)
    language = Column(String(16), nullable=False)
    title = Column(String(500), nullable=False)
    summary = Column(String(500), nullable=True)
    body = Column(Text, nullable=False)
    # draft | in_review | published | rejected
    status = Column(String(12), nullable=False, default="draft", server_default="draft", index=True)
    provider = Column(String(30), nullable=True)
    # `updated_at` (o `created_at`) del articulo cuando se genero: si el
    # original cambia despues, la version esta desfasada.
    source_updated_at = Column(DateTime(timezone=True), nullable=True)
    generated_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    reviewed_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    reviewed_at = Column(DateTime(timezone=True), nullable=True)
    review_comment = Column(String(500), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())


# El idioma de los mensajes nuevos se detecta al guardar (local, sin red).
from app.services.traduccion.deteccion import registrar as _registrar_deteccion  # noqa: E402

_registrar_deteccion()
