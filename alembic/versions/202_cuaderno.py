"""«Mi cuaderno»: notas personales tipo OneNote (23-11-2026, docs/CUADERNO.md).

Tablas nuevas (todas con `organization_id`; la RLS la aplica `env.py` tras el
`upgrade`): `notebooks`, `notebook_sections`, `notebook_pages`,
`notebook_shares`, `notebook_items`, `notebook_links`, `notebook_tags`,
`notebook_attachments` y `notebook_templates`. Índices por empresa, dueño,
padre, papelera (`deleted_at`), fechas de tarea y aviso, y objeto enlazado.

No hay datos que migrar: las plantillas de fábrica y las etiquetas por defecto
viven en el código hasta que la empresa las cambia en Configuración.

Deshacer real: borra las nueve tablas (con sus filas) y las instantáneas de
colaboración de las páginas (`document_collab_snapshots` con
`metadata_json` de tipo `notebook_page`). Los ficheros del almacén no se tocan:
quedan huérfanos y se listan en el log.

Idempotente: cada tabla e índice mira antes si ya existe.

Revision ID: 202_cuaderno
Revises: 201_cadena_colaboracion_y_cronometro
"""
import logging

import sqlalchemy as sa
from alembic import op

revision = "202_cuaderno"
down_revision = "201_cadena_colaboracion_y_cronometro"
branch_labels = None
depends_on = None

logger = logging.getLogger("alembic.202")

_TZ = sa.DateTime(timezone=True)

#: Orden de creación (padres antes); el borrado va al revés.
TABLAS = ("notebooks", "notebook_sections", "notebook_pages", "notebook_shares", "notebook_items",
          "notebook_links", "notebook_tags", "notebook_attachments", "notebook_templates")


def _insp():
    return sa.inspect(op.get_bind())


def _tablas() -> set:
    return set(_insp().get_table_names())


def _org():
    return sa.Column("organization_id", sa.String(36), sa.ForeignKey("organizations.id", ondelete="CASCADE"),
                     nullable=True)


def _dueno():
    return sa.Column("owner_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False)


def _por_usuario(nombre: str):
    return sa.Column(nombre, sa.String(36), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True)


def _creado():
    return sa.Column("created_at", _TZ, server_default=sa.func.now(), nullable=True)


def _actualizado():
    return sa.Column("updated_at", _TZ, nullable=True)


def _columnas() -> dict:
    """Definición de cada tabla (la misma que `app/models/cuaderno.py`)."""
    return {
        "notebooks": [
            sa.Column("id", sa.String(36), primary_key=True), _org(), _dueno(),
            sa.Column("title", sa.String(200), nullable=False),
            sa.Column("color", sa.String(20), nullable=True),
            sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("is_quick", sa.Boolean(), nullable=False, server_default=sa.false()),
            _por_usuario("transferred_from"),
            sa.Column("transferred_at", _TZ, nullable=True),
            sa.Column("deleted_at", _TZ, nullable=True),
            sa.Column("deleted_by", sa.String(36), nullable=True),
            _creado(), _actualizado(),
        ],
        "notebook_sections": [
            sa.Column("id", sa.String(36), primary_key=True), _org(),
            sa.Column("notebook_id", sa.String(36), sa.ForeignKey("notebooks.id", ondelete="CASCADE"), nullable=False),
            _dueno(),
            sa.Column("title", sa.String(200), nullable=False),
            sa.Column("color", sa.String(20), nullable=True),
            sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("deleted_at", _TZ, nullable=True),
            sa.Column("deleted_by", sa.String(36), nullable=True),
            _creado(), _actualizado(),
        ],
        "notebook_pages": [
            sa.Column("id", sa.String(36), primary_key=True), _org(),
            sa.Column("section_id", sa.String(36), sa.ForeignKey("notebook_sections.id", ondelete="CASCADE"),
                      nullable=False),
            sa.Column("notebook_id", sa.String(36), sa.ForeignKey("notebooks.id", ondelete="CASCADE"), nullable=False),
            _dueno(),
            sa.Column("parent_id", sa.String(36), sa.ForeignKey("notebook_pages.id", ondelete="SET NULL"),
                      nullable=True),
            sa.Column("title", sa.String(300), nullable=False, server_default=""),
            sa.Column("content", sa.Text(), nullable=True),
            sa.Column("content_text", sa.Text(), nullable=True),
            sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("template_key", sa.String(60), nullable=True),
            _por_usuario("created_by"), _por_usuario("updated_by"),
            _creado(), _actualizado(),
            sa.Column("deleted_at", _TZ, nullable=True),
            sa.Column("deleted_by", sa.String(36), nullable=True),
        ],
        "notebook_shares": [
            sa.Column("id", sa.String(36), primary_key=True), _org(),
            sa.Column("notebook_id", sa.String(36), sa.ForeignKey("notebooks.id", ondelete="CASCADE"), nullable=False),
            sa.Column("section_id", sa.String(36), sa.ForeignKey("notebook_sections.id", ondelete="CASCADE"),
                      nullable=True),
            sa.Column("target_type", sa.String(20), nullable=False),
            sa.Column("target_id", sa.String(200), nullable=False),
            sa.Column("permission", sa.String(10), nullable=False, server_default="read"),
            _por_usuario("created_by"), _creado(),
        ],
        "notebook_items": [
            sa.Column("id", sa.String(36), primary_key=True), _org(),
            sa.Column("page_id", sa.String(36), sa.ForeignKey("notebook_pages.id", ondelete="CASCADE"), nullable=False),
            sa.Column("notebook_id", sa.String(36), sa.ForeignKey("notebooks.id", ondelete="CASCADE"), nullable=False),
            _dueno(),
            sa.Column("kind", sa.String(10), nullable=False),
            sa.Column("tag_key", sa.String(40), nullable=True),
            sa.Column("block_id", sa.String(40), nullable=True),
            sa.Column("text", sa.String(1000), nullable=False, server_default=""),
            sa.Column("checked", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("due_date", sa.Date(), nullable=True),
            sa.Column("remind_at", _TZ, nullable=True),
            sa.Column("reminded_at", _TZ, nullable=True),
            sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
            _creado(),
        ],
        "notebook_links": [
            sa.Column("id", sa.String(36), primary_key=True), _org(),
            sa.Column("page_id", sa.String(36), sa.ForeignKey("notebook_pages.id", ondelete="CASCADE"), nullable=False),
            sa.Column("object_type", sa.String(30), nullable=False),
            sa.Column("object_id", sa.String(36), nullable=False),
            sa.Column("relation", sa.String(20), nullable=False, server_default="mention"),
            _por_usuario("created_by"), _creado(),
        ],
        "notebook_tags": [
            sa.Column("id", sa.String(36), primary_key=True), _org(), _dueno(),
            sa.Column("key", sa.String(40), nullable=False),
            sa.Column("label", sa.String(80), nullable=False),
            sa.Column("color", sa.String(20), nullable=True),
            sa.Column("icon", sa.String(30), nullable=True),
            _creado(),
        ],
        "notebook_attachments": [
            sa.Column("id", sa.String(36), primary_key=True), _org(),
            sa.Column("page_id", sa.String(36), sa.ForeignKey("notebook_pages.id", ondelete="CASCADE"), nullable=False),
            _dueno(),
            sa.Column("kind", sa.String(20), nullable=False, server_default="file"),
            sa.Column("file_key", sa.String(500), nullable=False),
            sa.Column("file_name", sa.String(255), nullable=False),
            sa.Column("mime_type", sa.String(120), nullable=True),
            sa.Column("size_bytes", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("meta", sa.Text(), nullable=True),
            _por_usuario("created_by"), _creado(),
        ],
        "notebook_templates": [
            sa.Column("id", sa.String(36), primary_key=True), _org(),
            sa.Column("key", sa.String(60), nullable=False),
            sa.Column("name", sa.String(200), nullable=False),
            sa.Column("description", sa.String(500), nullable=True),
            sa.Column("content", sa.Text(), nullable=False),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
            _por_usuario("created_by"), _por_usuario("updated_by"),
            _creado(), _actualizado(),
            sa.UniqueConstraint("organization_id", "key", name="uq_notebook_templates_org_key"),
        ],
    }


#: Índices `ix_<tabla>_<columna>` (los de `index=True` del modelo) y el compuesto del objeto enlazado.
INDICES: dict = {
    "notebooks": ("organization_id", "owner_id", "deleted_at"),
    "notebook_sections": ("organization_id", "notebook_id", "owner_id", "deleted_at"),
    "notebook_pages": ("organization_id", "section_id", "notebook_id", "owner_id", "parent_id", "deleted_at"),
    "notebook_shares": ("organization_id", "notebook_id", "section_id", "target_id"),
    "notebook_items": ("organization_id", "page_id", "notebook_id", "owner_id", "tag_key", "due_date", "remind_at"),
    "notebook_links": ("organization_id", "page_id"),
    "notebook_tags": ("organization_id", "owner_id"),
    "notebook_attachments": ("organization_id", "page_id", "owner_id"),
    "notebook_templates": ("organization_id",),
}
COMPUESTOS = {"notebook_links": (("ix_notebook_links_object", ("object_type", "object_id")),)}


def upgrade() -> None:
    hay = _tablas()
    columnas = _columnas()
    for tabla in TABLAS:
        if tabla not in hay:
            op.create_table(tabla, *columnas[tabla])
        existentes = {i["name"] for i in _insp().get_indexes(tabla)}
        for col in INDICES[tabla]:
            nombre = f"ix_{tabla}_{col}"
            if nombre not in existentes:
                op.create_index(nombre, tabla, [col])
        for nombre, cols in COMPUESTOS.get(tabla, ()):
            if nombre not in existentes:
                op.create_index(nombre, tabla, list(cols))
    logger.info("202: tablas del cuaderno listas")


def downgrade() -> None:
    bind = op.get_bind()
    hay = _tablas()
    if "notebook_attachments" in hay:
        n = bind.execute(sa.text("SELECT COUNT(*) FROM notebook_attachments")).scalar() or 0
        if n:
            logger.warning("202 (deshacer): %s ficheros de adjuntos del cuaderno quedan huérfanos en el almacén", n)
    if "notebook_pages" in hay and "document_collab_snapshots" in hay:
        bind.execute(sa.text(
            "DELETE FROM document_collab_snapshots WHERE document_id IN (SELECT id FROM notebook_pages)"))
    for tabla in reversed(TABLAS):
        if tabla in hay:
            for i in _insp().get_indexes(tabla):
                if i["name"] and i["name"].startswith("ix_"):
                    op.drop_index(i["name"], table_name=tabla)
            op.drop_table(tabla)
