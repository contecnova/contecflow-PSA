"""«Mi cuaderno»: notas personales tipo OneNote (migración 202, 23-11-2026).

Ver docs/CUADERNO.md. Nueve tablas, todas con `organization_id` (TenantSession
y RLS las acotan por empresa) y con el dueño (`owner_id`) repetido en cada
nivel para poder bloquear, exportar y suprimir por persona sin recorrer el árbol:

- `notebooks`: cuadernos de una persona (privados por defecto). `is_quick`
  marca el cuaderno de «Notas rápidas» del panel lateral.
- `notebook_sections`: secciones (pestañas de color) de un cuaderno.
- `notebook_pages`: páginas y subpáginas (`parent_id`). `content` es el JSON de
  ProseMirror (la fuente de verdad; nunca HTML del cliente) y `content_text` el
  texto plano para buscar. `version` sube con cada guardado (conflictos sin red).
- `notebook_shares`: con quién se comparte un cuaderno o una sección (persona,
  equipo `users.team` o departamento `users.department`) y con qué permiso.
- `notebook_items`: índice de casillas de tarea y etiquetas de cada página
  (lo rehace el servidor al guardar) para «Todas mis tareas y etiquetas» y los avisos.
- `notebook_links`: vínculos nota ↔ objeto (chips `#`/`@` y objetos creados
  desde la nota), para el chip vivo y el enlace de vuelta.
- `notebook_tags`: etiquetas propias de cada persona (las de la empresa van en
  la configuración, `app_settings` clave `cuaderno.config`).
- `notebook_attachments`: adjuntos, imágenes pegadas, dibujos (SVG generado en
  el servidor, trazos en `meta`) y audios; el fichero vive en el almacén común.
- `notebook_templates`: plantillas de la empresa (Configuración › Mi cuaderno).

El estado de colaboración (Yjs) se guarda en `document_collab_snapshots` con
`document_id` = id de la página (`metadata_json` `{"kind": "notebook_page"}`).
Al borrar adjuntos o páginas (a mano, papelera, retención o RGPD) sus ficheros
y sus instantáneas se borran tras confirmar (`app/db/cuaderno_borrado.py`; la baja
de una persona, `app/db/cuaderno_baja.py`; los dos se registran en `app/models/__init__.py`).
"""
import uuid

from sqlalchemy import Boolean, Column, Date, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import relationship

from app.db.base import Base


def _uuid() -> str:
    return str(uuid.uuid4())


def _org():
    return Column(String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)


def _dueno():
    return Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)


class Notebook(Base):
    __tablename__ = "notebooks"

    id = Column(String(36), primary_key=True, default=_uuid)
    organization_id = _org()
    owner_id = _dueno()
    title = Column(String(200), nullable=False)
    color = Column(String(20), nullable=True)
    sort_order = Column(Integer, nullable=False, default=0)
    is_quick = Column(Boolean, nullable=False, default=False)
    transferred_from = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    transferred_at = Column(DateTime(timezone=True), nullable=True)
    deleted_at = Column(DateTime(timezone=True), nullable=True, index=True)
    deleted_by = Column(String(36), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    sections = relationship("NotebookSection", back_populates="notebook", cascade="all, delete-orphan",
                            passive_deletes=False, order_by="NotebookSection.sort_order")
    shares = relationship("NotebookShare", cascade="all, delete-orphan", passive_deletes=False,
                          primaryjoin="Notebook.id == NotebookShare.notebook_id")


class NotebookSection(Base):
    __tablename__ = "notebook_sections"

    id = Column(String(36), primary_key=True, default=_uuid)
    organization_id = _org()
    notebook_id = Column(String(36), ForeignKey("notebooks.id", ondelete="CASCADE"), nullable=False, index=True)
    owner_id = _dueno()
    title = Column(String(200), nullable=False)
    color = Column(String(20), nullable=True)
    sort_order = Column(Integer, nullable=False, default=0)
    deleted_at = Column(DateTime(timezone=True), nullable=True, index=True)
    deleted_by = Column(String(36), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    notebook = relationship("Notebook", back_populates="sections")
    pages = relationship("NotebookPage", back_populates="section", cascade="all, delete-orphan",
                         passive_deletes=False, order_by="NotebookPage.sort_order")


class NotebookPage(Base):
    __tablename__ = "notebook_pages"

    id = Column(String(36), primary_key=True, default=_uuid)
    organization_id = _org()
    section_id = Column(String(36), ForeignKey("notebook_sections.id", ondelete="CASCADE"), nullable=False, index=True)
    notebook_id = Column(String(36), ForeignKey("notebooks.id", ondelete="CASCADE"), nullable=False, index=True)
    owner_id = _dueno()
    parent_id = Column(String(36), ForeignKey("notebook_pages.id", ondelete="SET NULL"), nullable=True, index=True)
    title = Column(String(300), nullable=False, default="")
    content = Column(Text, nullable=True)          # JSON de ProseMirror (validado en el servidor)
    content_text = Column(Text, nullable=True)     # texto plano para buscar
    sort_order = Column(Integer, nullable=False, default=0)
    version = Column(Integer, nullable=False, default=1)
    template_key = Column(String(60), nullable=True)
    created_by = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    updated_by = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    deleted_at = Column(DateTime(timezone=True), nullable=True, index=True)
    deleted_by = Column(String(36), nullable=True)

    section = relationship("NotebookSection", back_populates="pages")
    items = relationship("NotebookItem", cascade="all, delete-orphan", passive_deletes=False)
    links = relationship("NotebookLink", cascade="all, delete-orphan", passive_deletes=False)
    attachments = relationship("NotebookAttachment", cascade="all, delete-orphan", passive_deletes=False)


class NotebookShare(Base):
    __tablename__ = "notebook_shares"

    id = Column(String(36), primary_key=True, default=_uuid)
    organization_id = _org()
    notebook_id = Column(String(36), ForeignKey("notebooks.id", ondelete="CASCADE"), nullable=False, index=True)
    section_id = Column(String(36), ForeignKey("notebook_sections.id", ondelete="CASCADE"), nullable=True, index=True)
    target_type = Column(String(20), nullable=False)       # user | team | department
    target_id = Column(String(200), nullable=False, index=True)
    permission = Column(String(10), nullable=False, default="read")   # read | edit
    created_by = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class NotebookItem(Base):
    __tablename__ = "notebook_items"

    id = Column(String(36), primary_key=True, default=_uuid)
    organization_id = _org()
    page_id = Column(String(36), ForeignKey("notebook_pages.id", ondelete="CASCADE"), nullable=False, index=True)
    notebook_id = Column(String(36), ForeignKey("notebooks.id", ondelete="CASCADE"), nullable=False, index=True)
    owner_id = _dueno()
    kind = Column(String(10), nullable=False)              # todo | tag
    tag_key = Column(String(40), nullable=True, index=True)
    block_id = Column(String(40), nullable=True)
    text = Column(String(1000), nullable=False, default="")
    checked = Column(Boolean, nullable=False, default=False)
    due_date = Column(Date, nullable=True, index=True)
    remind_at = Column(DateTime(timezone=True), nullable=True, index=True)
    reminded_at = Column(DateTime(timezone=True), nullable=True)
    position = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class NotebookLink(Base):
    __tablename__ = "notebook_links"
    __table_args__ = (Index("ix_notebook_links_object", "object_type", "object_id"),)

    id = Column(String(36), primary_key=True, default=_uuid)
    organization_id = _org()
    page_id = Column(String(36), ForeignKey("notebook_pages.id", ondelete="CASCADE"), nullable=False, index=True)
    object_type = Column(String(30), nullable=False)       # task | ticket | demand | proposal | event | project | client | user
    object_id = Column(String(36), nullable=False)
    relation = Column(String(20), nullable=False, default="mention")   # mention | created
    created_by = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class NotebookTag(Base):
    __tablename__ = "notebook_tags"

    id = Column(String(36), primary_key=True, default=_uuid)
    organization_id = _org()
    owner_id = _dueno()
    key = Column(String(40), nullable=False)
    label = Column(String(80), nullable=False)
    color = Column(String(20), nullable=True)
    icon = Column(String(30), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class NotebookAttachment(Base):
    __tablename__ = "notebook_attachments"

    id = Column(String(36), primary_key=True, default=_uuid)
    organization_id = _org()
    page_id = Column(String(36), ForeignKey("notebook_pages.id", ondelete="CASCADE"), nullable=False, index=True)
    owner_id = _dueno()
    kind = Column(String(20), nullable=False, default="file")   # file | image | drawing | audio
    file_key = Column(String(500), nullable=False)
    file_name = Column(String(255), nullable=False)
    mime_type = Column(String(120), nullable=True)
    size_bytes = Column(Integer, nullable=False, default=0)
    meta = Column(Text, nullable=True)                      # JSON: trazos del dibujo, transcripción del audio
    created_by = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class NotebookTemplate(Base):
    __tablename__ = "notebook_templates"
    __table_args__ = (UniqueConstraint("organization_id", "key", name="uq_notebook_templates_org_key"),)

    id = Column(String(36), primary_key=True, default=_uuid)
    organization_id = _org()
    key = Column(String(60), nullable=False)
    name = Column(String(200), nullable=False)
    description = Column(String(500), nullable=True)
    content = Column(Text, nullable=False)                  # JSON de ProseMirror
    is_active = Column(Boolean, nullable=False, default=True)
    sort_order = Column(Integer, nullable=False, default=0)
    created_by = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    updated_by = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
