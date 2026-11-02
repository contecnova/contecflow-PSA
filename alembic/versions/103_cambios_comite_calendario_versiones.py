"""Cambios: comite con votos, ventanas de congelacion y versiones.

- `sd_change_approvals`: el voto de cada miembro del CAB. Antes el comite era
  un JSON en `app_settings`, sin pantalla ni consulta posible.
- `sd_change_blackouts`: ventanas en las que no se programan cambios.
- `sd_releases` y `sd_change_requests.release_id`: versiones que agrupan cambios.
- `sd_change_requests`: quorum, reunion y quien implementa.
"""
from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "103_cambios_comite_calendario_versiones"
down_revision: Union[str, None] = "102_aprobacion_del_catalogo"
branch_labels = None
depends_on = None


def _id(nombre: str):
    return sa.Column(nombre, sa.String(36), primary_key=True)


def _org():
    return sa.Column("organization_id", sa.String(36), sa.ForeignKey("organizations.id"), nullable=True)


def upgrade() -> None:
    conn = op.get_bind()
    tablas = set(sa.inspect(conn).get_table_names())
    if "sd_releases" not in tablas:
        op.create_table(
            "sd_releases", _id("id"), _org(),
            sa.Column("name", sa.String(200), nullable=False),
            sa.Column("version", sa.String(50), nullable=True),
            sa.Column("status", sa.String(20), nullable=False, server_default="planned"),
            sa.Column("planned_date", sa.DateTime(timezone=True), nullable=True),
            sa.Column("released_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("notes", sa.Text(), nullable=True),
            sa.Column("owner_id", sa.String(36), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        )
        op.create_index("ix_sd_releases_organization_id", "sd_releases", ["organization_id"])
        op.create_index("ix_sd_releases_planned_date", "sd_releases", ["planned_date"])
    if "sd_change_approvals" not in tablas:
        op.create_table(
            "sd_change_approvals", _id("id"), _org(),
            sa.Column("change_id", sa.String(36), sa.ForeignKey("sd_change_requests.id", ondelete="CASCADE"), nullable=False),
            sa.Column("approver_user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
            sa.Column("decision", sa.String(20), nullable=False, server_default="pending"),
            sa.Column("note", sa.Text(), nullable=True),
            sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        )
        for col in ("organization_id", "change_id", "approver_user_id"):
            op.create_index(f"ix_sd_change_approvals_{col}", "sd_change_approvals", [col])
    if "sd_change_blackouts" not in tablas:
        op.create_table(
            "sd_change_blackouts", _id("id"), _org(),
            sa.Column("name", sa.String(200), nullable=False),
            sa.Column("reason", sa.Text(), nullable=True),
            sa.Column("start_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("end_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        )
        for col in ("organization_id", "start_at", "end_at"):
            op.create_index(f"ix_sd_change_blackouts_{col}", "sd_change_blackouts", [col])

    cols = {c["name"] for c in sa.inspect(conn).get_columns("sd_change_requests")}
    with op.batch_alter_table("sd_change_requests") as batch:
        if "cab_quorum" not in cols:
            batch.add_column(sa.Column("cab_quorum", sa.Integer(), nullable=True))
        if "cab_meeting_at" not in cols:
            batch.add_column(sa.Column("cab_meeting_at", sa.DateTime(timezone=True), nullable=True))
        if "cab_agenda" not in cols:
            batch.add_column(sa.Column("cab_agenda", sa.Text(), nullable=True))
        if "implementer_id" not in cols:
            batch.add_column(sa.Column("implementer_id", sa.String(36), nullable=True))
            batch.create_foreign_key("fk_sd_change_requests_implementer_id", "users",
                                     ["implementer_id"], ["id"], ondelete="SET NULL")
        if "release_id" not in cols:
            batch.add_column(sa.Column("release_id", sa.String(36), nullable=True))
            batch.create_foreign_key("fk_sd_change_requests_release_id", "sd_releases",
                                     ["release_id"], ["id"], ondelete="SET NULL")
    if "release_id" not in cols:
        op.create_index("ix_sd_change_requests_release_id", "sd_change_requests", ["release_id"])


def downgrade() -> None:
    conn = op.get_bind()
    cols = {c["name"] for c in sa.inspect(conn).get_columns("sd_change_requests")}
    if "release_id" in cols:
        op.drop_index("ix_sd_change_requests_release_id", table_name="sd_change_requests")
    with op.batch_alter_table("sd_change_requests") as batch:
        for fk in ("fk_sd_change_requests_release_id", "fk_sd_change_requests_implementer_id"):
            col = fk.replace("fk_sd_change_requests_", "")
            if col in cols:
                batch.drop_constraint(fk, type_="foreignkey")
        for col in ("release_id", "implementer_id", "cab_agenda", "cab_meeting_at", "cab_quorum"):
            if col in cols:
                batch.drop_column(col)
    tablas = set(sa.inspect(conn).get_table_names())
    for t in ("sd_change_blackouts", "sd_change_approvals", "sd_releases"):
        if t in tablas:
            op.drop_table(t)
