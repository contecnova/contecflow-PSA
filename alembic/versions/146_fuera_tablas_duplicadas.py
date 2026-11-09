"""Fuera dos tablas que duplicaban o que nadie leía.

Revisión 2026-11.
- `ticket_internal_comments`: la página `/internal-comments` (fuera del menú)
  guardaba notas internas aparte; las del panel del ticket viven en
  `sd_ticket_comments` con `is_public = False` y generan sus eventos. Las que
  hubiera se pasan allí antes de borrar la tabla.
- `agent_metric_snapshots`: el panel de agente se calcula desde los tickets;
  la tabla no la escribe ni la lee nadie.

Revision ID: 146_fuera_tablas_duplicadas
Revises: 145_formularios_publicos_en_su_empresa
"""
import sqlalchemy as sa
from alembic import op

revision = "146_fuera_tablas_duplicadas"
down_revision = "145_formularios_publicos_en_su_empresa"
branch_labels = None
depends_on = None


def upgrade() -> None:
    con = op.get_bind()
    tablas = set(sa.inspect(con).get_table_names())
    if "ticket_internal_comments" in tablas:
        filas = con.execute(sa.text(
            "SELECT id, organization_id, ticket_id, content, created_by, created_at FROM ticket_internal_comments")).fetchall()
        for f in filas:
            con.execute(sa.text(
                "INSERT INTO sd_ticket_comments (id, organization_id, ticket_id, body, is_public, is_solution, author_user_id, created_at) "
                "VALUES (:id, :org, :t, :b, :pub, :sol, :u, :c)"),
                {"id": f.id, "org": f.organization_id, "t": f.ticket_id, "b": f.content,
                 "pub": False, "sol": False, "u": f.created_by, "c": f.created_at})
        op.drop_table("ticket_internal_comments")
    if "agent_metric_snapshots" in tablas:
        op.drop_table("agent_metric_snapshots")


def downgrade() -> None:
    # Las notas ya están en sd_ticket_comments; no se devuelven a una tabla que
    # nadie lee. Irreversible a propósito.
    pass
