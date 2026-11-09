"""Lecciones aprendidas: la base de la mejora continua (revisión 2026-11).

Tres tablas:

- `lecciones`: qué pasó, por qué, qué hacer (o evitar) la próxima vez, con su
  origen (proyecto, ticket, problema, incidente grave, sprint, incidente de
  seguridad o a mano) y los HECHOS medidos de ese origen guardados al crearla.
  El ámbito —cliente, tipo de proyecto, etiquetas, servicio del catálogo, CI— es lo que
  permite recomendarla en casos parecidos.
- `leccion_usos`: cada vez que alguien dice si una recomendación le sirvió
  («útil», «aplicada», «no aplica»), en qué contexto. Es la medida de si la
  base de lecciones sirve de algo.
- `leccion_acciones`: las acciones de mejora que salen de una lección, con
  responsable, plazo y resultado. Una lección sin acción es una anécdota.
"""
import uuid

from sqlalchemy import Column, Date, DateTime, ForeignKey, Index, String, Text
from sqlalchemy.sql import func

from app.db.base import Base


class Leccion(Base):
    __tablename__ = "lecciones"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=True, index=True)
    codigo = Column(String(20), nullable=False)                    # LEC-0001
    titulo = Column(String(300), nullable=False)
    tipo = Column(String(10), nullable=False, default="evitar")     # evitar | repetir
    categoria = Column(String(40), nullable=False)                 # de LESSONS_CATEGORIES
    severidad = Column(String(10), nullable=False, default="media")  # baja | media | alta
    que_paso = Column(Text, nullable=False)
    causa = Column(Text, nullable=True)
    impacto = Column(Text, nullable=True)
    recomendacion = Column(Text, nullable=False)
    estado = Column(String(15), nullable=False, default="borrador", index=True)  # borrador | en_revision | validada | archivada

    # Origen y hechos medidos al crearla
    origen_tipo = Column(String(20), nullable=False, default="manual")  # project | ticket | problem | major_incident | sprint | security_incident | manual
    origen_id = Column(String(64), nullable=True)
    origen_ref = Column(String(120), nullable=True)                # código legible del origen (PRJ-0007, INC-0012…)
    hechos = Column(Text, nullable=True)                           # JSON

    # Ámbito: con qué casos se parece
    proyecto_id = Column(String(36), ForeignKey("projects.id", ondelete="SET NULL"), nullable=True, index=True)
    cliente_id = Column(String(36), ForeignKey("clients.id", ondelete="SET NULL"), nullable=True, index=True)
    tipo_proyecto = Column(String(30), nullable=True)
    etiquetas = Column(String(500), nullable=True)                 # separadas por comas
    servicio_id = Column(String(36), nullable=True)                 # servicio del catálogo (ticket.service_item_id)
    ci_id = Column(String(36), nullable=True)
    vector = Column(Text, nullable=True)                           # JSON, si hay modelo de embeddings

    autor_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    validada_por = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    validada_en = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    __table_args__ = (
        Index("uq_lecciones_org_codigo", "organization_id", "codigo", unique=True),
        Index("ix_lecciones_origen", "origen_tipo", "origen_id"),
    )


class LeccionUso(Base):
    __tablename__ = "leccion_usos"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=True, index=True)
    leccion_id = Column(String(36), ForeignKey("lecciones.id", ondelete="CASCADE"), nullable=False, index=True)
    contexto_tipo = Column(String(20), nullable=False)             # project | ticket | change | nuevo_proyecto
    contexto_id = Column(String(64), nullable=True)
    valor = Column(String(12), nullable=False)                     # util | aplicada | no_aplica
    nota = Column(String(500), nullable=True)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (Index("ix_leccion_usos_contexto", "contexto_tipo", "contexto_id"),)


class LeccionAccion(Base):
    __tablename__ = "leccion_acciones"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=True, index=True)
    leccion_id = Column(String(36), ForeignKey("lecciones.id", ondelete="CASCADE"), nullable=False, index=True)
    descripcion = Column(Text, nullable=False)
    responsable_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    fecha_limite = Column(Date, nullable=True)
    estado = Column(String(12), nullable=False, default="abierta", index=True)  # abierta | en_curso | hecha | descartada
    resultado = Column(Text, nullable=True)
    cerrada_en = Column(DateTime(timezone=True), nullable=True)
    created_by = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
