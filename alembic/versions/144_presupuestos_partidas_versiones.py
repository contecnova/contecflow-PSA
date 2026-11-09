"""Presupuestos: ámbito, periodo, versiones, estado de aprobación y partidas por meses.

Revisión 2026-11. Los meses de `budget_entries` pasan a una partida «otros» de
cada presupuesto (su plan; el «real» que había se tecleaba a mano y ahora se
calcula, así que no se copia) y la tabla se retira: ya no la lee nadie.
"""
import json
from datetime import date
from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "144_presupuestos"
down_revision: Union[str, None] = "143_gastos_avanzados"
branch_labels = None
depends_on = None

_NUEVAS = (
    ("ambito", sa.String(20), "departamento"), ("area", sa.String(255), None),
    ("cliente_id", sa.String(36), None), ("tipo_proyecto", sa.String(30), None),
    ("periodo_desde", sa.Date(), None), ("periodo_hasta", sa.Date(), None),
    ("version", sa.Integer(), "1"), ("origen_id", sa.String(36), None),
    ("estado", sa.String(15), "borrador"), ("motivo_rechazo", sa.Text(), None),
)


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    columnas = {c["name"] for c in insp.get_columns("budgets")}
    with op.batch_alter_table("budgets") as t:
        for nombre, tipo, defecto in _NUEVAS:
            if nombre not in columnas:
                t.add_column(sa.Column(nombre, tipo, nullable=defecto is None,
                                       server_default=defecto))
    if "budget_lines" not in insp.get_table_names():
        op.create_table(
            "budget_lines",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("organization_id", sa.String(36), sa.ForeignKey("organizations.id", ondelete="CASCADE"),
                      nullable=True, index=True),
            sa.Column("budget_id", sa.String(36), sa.ForeignKey("budgets.id", ondelete="CASCADE"), nullable=False,
                      index=True),
            sa.Column("tipo", sa.String(30), nullable=False),
            sa.Column("descripcion", sa.String(500), nullable=False),
            sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
            sa.Column("perfil", sa.String(120), nullable=True),
            sa.Column("horas", sa.Float(), nullable=True),
            sa.Column("coste_hora", sa.Float(), nullable=True),
            sa.Column("importe", sa.Float(), nullable=False, server_default="0"),
            sa.Column("meses", sa.Text(), nullable=False, server_default="{}"),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        )
    # Datos: estado, ámbito y periodo de los que ya había, y sus meses como partida.
    presupuestos = bind.execute(sa.text(
        "SELECT id, organization_id, year, project_id, is_approved FROM budgets")).fetchall()
    for bid, _org, anio, proyecto, aprobado in presupuestos:
        bind.execute(sa.text(
            "UPDATE budgets SET estado = :e, ambito = :a, periodo_desde = :d, periodo_hasta = :h, origen_id = id "
            "WHERE id = :i"), {"e": "aprobado" if aprobado else "borrador", "a": "proyecto" if proyecto else "departamento",
                                "d": date(int(anio), 1, 1), "h": date(int(anio), 12, 1), "i": bid})
    if "budget_entries" in insp.get_table_names():
        for bid, org, anio, _p, _a in presupuestos:
            filas = bind.execute(sa.text("SELECT month, planned FROM budget_entries WHERE budget_id = :b"),
                                 {"b": bid}).fetchall()
            meses = {f"{int(anio)}-{int(m):02d}": float(pl or 0) for m, pl in filas if (pl or 0)}
            if meses:
                import uuid
                bind.execute(sa.text(
                    "INSERT INTO budget_lines (id, organization_id, budget_id, tipo, descripcion, importe, meses) "
                    "VALUES (:id, :o, :b, 'otros', 'Plan mensual anterior', :imp, :m)"),
                    {"id": str(uuid.uuid4()), "o": org, "b": bid, "imp": round(sum(meses.values()), 2),
                     "m": json.dumps(meses)})
        op.drop_table("budget_entries")


def downgrade() -> None:
    op.drop_table("budget_lines")
    with op.batch_alter_table("budgets") as t:
        for nombre, _, _ in _NUEVAS:
            t.drop_column(nombre)
