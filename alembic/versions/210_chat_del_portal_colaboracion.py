"""Chat del portal en colaboración: rastro de ediciones y borrados del cliente (24-11-2026).

Docs: docs/portal/CHAT_DEL_PORTAL.md §9 (pestaña «Chat» del portal).

`collaboration_message_versions` gana:

- `edited_by_client_id` (nulable, FK a `client_users`, `SET NULL`, indexada):
  quién editó o borró cuando es un usuario del portal (antes solo había
  `edited_by_user_id`).
- `change_type` (`edit` | `delete`, por defecto `edit`): el borrado también deja
  el texto anterior (antes el borrado sobrescribía el cuerpo sin rastro).

Compatible con SQLite y Postgres (`batch_alter_table`). Idempotente. Deshacer
real: quita las dos columnas y el índice.

Revision ID: 210_chat_del_portal_colaboracion
Revises: 209_chat_del_portal_completo
"""
import sqlalchemy as sa
from alembic import op

revision = "210_chat_del_portal_colaboracion"
down_revision = "209_chat_del_portal_completo"
branch_labels = None
depends_on = None

TABLA = "collaboration_message_versions"
INDICE = "ix_collaboration_message_versions_edited_by_client_id"


def _insp():
    return sa.inspect(op.get_bind())


def _cols() -> set:
    if TABLA not in _insp().get_table_names():
        return set()
    return {c["name"] for c in _insp().get_columns(TABLA)}


def _indices() -> set:
    if TABLA not in _insp().get_table_names():
        return set()
    return {i["name"] for i in _insp().get_indexes(TABLA)}


def upgrade() -> None:
    cols = _cols()
    if not cols:
        return
    if "edited_by_client_id" not in cols or "change_type" not in cols:
        with op.batch_alter_table(TABLA) as b:
            if "edited_by_client_id" not in cols:
                b.add_column(sa.Column("edited_by_client_id", sa.String(36),
                                       sa.ForeignKey("client_users.id", ondelete="SET NULL",
                                                     name="fk_collab_msg_versions_client"),
                                       nullable=True))
            if "change_type" not in cols:
                b.add_column(sa.Column("change_type", sa.String(10), nullable=False, server_default="edit"))
    if INDICE not in _indices():
        op.create_index(INDICE, TABLA, ["edited_by_client_id"])


def downgrade() -> None:
    if INDICE in _indices():
        op.drop_index(INDICE, table_name=TABLA)
    presentes = [c for c in ("edited_by_client_id", "change_type") if c in _cols()]
    if presentes:
        with op.batch_alter_table(TABLA) as b:
            for c in presentes:
                b.drop_column(c)
