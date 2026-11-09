"""Presupuestos, seguir a fondo: comprometido, cierres, desviaciones, traspasos y previsión.

Revisión 2026-11.
- `budget_commitments`: pedidos comprometidos contra un presupuesto.
- `budget_closes`: cierre mensual que congela el real del mes por tipo.
- `budget_variance_notes`: explicación de una desviación (tipo y mes).
- `budget_transfers`: traspasos entre partidas y ampliaciones, con aprobación.
- `budgets.prevision`: reprevisión por tipo (plan, ritmo real o a mano).
- Alerta nueva `budget_forecast_overrun` (previsión al cierre por encima del plan).

Revision ID: 152_presupuestos_seguir_a_fondo
Revises: 151_presupuestos_preparar_a_fondo
"""
import sqlalchemy as sa
from alembic import op

revision = "152_presupuestos_seguir_a_fondo"
down_revision = "151_presupuestos_preparar_a_fondo"
branch_labels = None
depends_on = None


def _org():
    return sa.Column("organization_id", sa.String(36), sa.ForeignKey("organizations.id", ondelete="CASCADE"),
                     nullable=True, index=True)


def upgrade() -> None:
    con = op.get_bind()
    tablas = set(sa.inspect(con).get_table_names())
    if "budget_commitments" not in tablas:
        op.create_table(
            "budget_commitments",
            sa.Column("id", sa.String(36), primary_key=True), _org(),
            sa.Column("origen_id", sa.String(36), nullable=False, index=True),
            sa.Column("tipo", sa.String(30), nullable=False),
            sa.Column("descripcion", sa.String(500), nullable=False),
            sa.Column("proveedor", sa.String(200), nullable=True),
            sa.Column("referencia", sa.String(100), nullable=True),
            sa.Column("importe", sa.Float(), nullable=False),
            sa.Column("mes", sa.String(7), nullable=False),
            sa.Column("estado", sa.String(12), nullable=False, server_default="comprometido"),
            sa.Column("fecha_factura", sa.Date(), nullable=True),
            sa.Column("importe_facturado", sa.Float(), nullable=True),
            sa.Column("created_by", sa.String(36), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        )
    if "budget_closes" not in tablas:
        op.create_table(
            "budget_closes",
            sa.Column("id", sa.String(36), primary_key=True), _org(),
            sa.Column("origen_id", sa.String(36), nullable=False, index=True),
            sa.Column("mes", sa.String(7), nullable=False),
            sa.Column("real", sa.Text(), nullable=False, server_default="{}"),
            sa.Column("cerrado_por", sa.String(36), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
            sa.Column("cerrado_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.UniqueConstraint("origen_id", "mes", name="uq_budget_closes_origen_mes"),
        )
    if "budget_variance_notes" not in tablas:
        op.create_table(
            "budget_variance_notes",
            sa.Column("id", sa.String(36), primary_key=True), _org(),
            sa.Column("origen_id", sa.String(36), nullable=False, index=True),
            sa.Column("mes", sa.String(7), nullable=False),
            sa.Column("tipo", sa.String(30), nullable=False),
            sa.Column("explicacion", sa.Text(), nullable=False),
            sa.Column("autor_id", sa.String(36), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.UniqueConstraint("origen_id", "mes", "tipo", name="uq_budget_variance_origen_mes_tipo"),
        )
    if "budget_transfers" not in tablas:
        op.create_table(
            "budget_transfers",
            sa.Column("id", sa.String(36), primary_key=True), _org(),
            sa.Column("budget_id", sa.String(36), sa.ForeignKey("budgets.id", ondelete="CASCADE"), nullable=False, index=True),
            sa.Column("desde_linea_id", sa.String(36), nullable=True),
            sa.Column("hacia_linea_id", sa.String(36), nullable=True),
            sa.Column("hacia_tipo", sa.String(30), nullable=True),
            sa.Column("hacia_descripcion", sa.String(500), nullable=True),
            sa.Column("importe", sa.Float(), nullable=False),
            sa.Column("motivo", sa.Text(), nullable=False),
            sa.Column("estado", sa.String(12), nullable=False, server_default="pendiente"),
            sa.Column("solicitante_id", sa.String(36), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
            sa.Column("decisor_id", sa.String(36), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
            sa.Column("decidido_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("motivo_rechazo", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        )
    if "prevision" not in {c["name"] for c in sa.inspect(con).get_columns("budgets")}:
        with op.batch_alter_table("budgets") as t:
            t.add_column(sa.Column("prevision", sa.Text(), nullable=False, server_default="{}"))
    if con.dialect.name == "postgresql":
        existe = con.execute(sa.text("SELECT 1 FROM pg_type WHERE typname = 'alerttype'")).first()
        if existe:
            op.execute("ALTER TYPE alerttype ADD VALUE IF NOT EXISTS 'budget_forecast_overrun'")


def downgrade() -> None:
    with op.batch_alter_table("budgets") as t:
        t.drop_column("prevision")
    for tabla in ("budget_transfers", "budget_variance_notes", "budget_closes", "budget_commitments"):
        op.drop_table(tabla)
    # El valor del tipo de alerta se queda: Postgres no quita valores de un enum.
