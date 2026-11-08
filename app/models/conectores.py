"""Conectores con contecmind y contecintelligence (revisión 2026-11).

Tres tablas:

- `conector_llamadas`: cada llamada a otro producto, con su resultado y su
  latencia. Es lo que enseña el panel de estado de Ajustes → Integraciones:
  sin ella, «el conector falla» sólo se sabe cuando alguien se queja.
- `enlaces_documentales`: un documento de contecmind enlazado a una ficha de
  contecflow (ticket, contrato, proyecto, artículo…). El documento vive en
  contecmind con sus versiones y permisos; aquí sólo se guarda el enlace y lo
  necesario para pintarlo sin llamar (título, tipo, tamaño).
- `carpetas_documentales`: la carpeta de contecmind de cada ficha, creada la
  primera vez que hace falta. Así los documentos de un proyecto o de un
  contrato quedan juntos también en contecmind.
"""
import uuid

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Index, Integer, String
from sqlalchemy.sql import func

from app.db.base import Base


class ConectorLlamada(Base):
    __tablename__ = "conector_llamadas"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=True, index=True)
    producto = Column(String(40), nullable=False)          # contecmind | contecintelligence
    operacion = Column(String(60), nullable=False)         # buscar | subir | preguntar | …
    ok = Column(Boolean, nullable=False, default=False)
    estado_http = Column(Integer, nullable=True)
    ms = Column(Integer, nullable=False, default=0)
    error = Column(String(500), nullable=True)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (Index("ix_conector_llamadas_producto_fecha", "producto", "created_at"),)


class EnlaceDocumental(Base):
    __tablename__ = "enlaces_documentales"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=True, index=True)
    entidad = Column(String(40), nullable=False)           # ticket | contract | project | kb_article | …
    entidad_id = Column(String(64), nullable=False)
    document_id = Column(String(64), nullable=False)
    titulo = Column(String(500), nullable=False)
    mime_type = Column(String(120), nullable=True)
    tamano = Column(Integer, nullable=True)
    origen = Column(String(20), nullable=False, default="enlazado")   # subido | enlazado | sugerido
    nota = Column(String(500), nullable=True)
    created_by = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (
        Index("uq_enlaces_documentales", "organization_id", "entidad", "entidad_id", "document_id", unique=True),
        Index("ix_enlaces_documentales_ficha", "entidad", "entidad_id"),
    )


class CarpetaDocumental(Base):
    __tablename__ = "carpetas_documentales"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=True, index=True)
    entidad = Column(String(40), nullable=False)
    entidad_id = Column(String(64), nullable=False)
    folder_id = Column(String(64), nullable=False)
    area_id = Column(String(64), nullable=False)
    ruta = Column(String(1000), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (
        Index("uq_carpetas_documentales", "organization_id", "entidad", "entidad_id", unique=True),
    )
