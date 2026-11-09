"""Presupuestos, preparar a fondo: áreas, jerarquía, campaña, plantillas y partidas con conductores.

Revisión 2026-11. Lo pidió el usuario: el presupuesto es la base de las áreas y
de los proyectos, y prepararlo tiene que ser mucho más profundo.
- `areas` (un área agrupa departamentos: `departments.area_id`).
- `budgets`: área, presupuesto padre (área > departamento > proyecto) y techo,
  responsable, campaña, escenario y supuestos.
- `budget_lines`: ingreso o gasto, OPEX o CAPEX con vida, conductores
  (unidades × precio, recurrencia, meses), dedicación, vacantes (alta, país,
  salario) y justificación.
- `budget_campaigns` y `budget_templates`.
Los presupuestos de área guardaban los departamentos como texto separado por
comas: se crea un área por cada uno y sus departamentos sin área pasan a ella.

Revision ID: 151_presupuestos_preparar_a_fondo
Revises: 150_ajustes_y_alertas_sin_lector
"""
import uuid

import sqlalchemy as sa
from alembic import op

revision = "151_presupuestos_preparar_a_fondo"
down_revision = "150_ajustes_y_alertas_sin_lector"
branch_labels = None
depends_on = None


def _cols(con, tabla):
    return {c["name"] for c in sa.inspect(con).get_columns(tabla)}


def upgrade() -> None:
    con = op.get_bind()
    tablas = set(sa.inspect(con).get_table_names())
    if "areas" not in tablas:
        op.create_table(
            "areas",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("organization_id", sa.String(36), sa.ForeignKey("organizations.id"), nullable=True, index=True),
            sa.Column("name", sa.String(120), nullable=False),
            sa.Column("description", sa.String(255), nullable=True),
            sa.Column("manager_id", sa.String(36), sa.ForeignKey("users.id"), nullable=True),
            sa.Column("is_active", sa.Boolean(), server_default=sa.true()),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        )
    if "budget_campaigns" not in tablas:
        op.create_table(
            "budget_campaigns",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("organization_id", sa.String(36), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=True, index=True),
            sa.Column("nombre", sa.String(200), nullable=False),
            sa.Column("year", sa.Integer(), nullable=False),
            sa.Column("fecha_limite", sa.Date(), nullable=False),
            sa.Column("abierta", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("instrucciones", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        )
    if "budget_templates" not in tablas:
        op.create_table(
            "budget_templates",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("organization_id", sa.String(36), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=True, index=True),
            sa.Column("nombre", sa.String(200), nullable=False),
            sa.Column("ambito", sa.String(20), nullable=True),
            sa.Column("tipo_proyecto", sa.String(30), nullable=True),
            sa.Column("partidas", sa.Text(), nullable=False, server_default="[]"),
            sa.Column("created_by", sa.String(36), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        )
    if "area_id" not in _cols(con, "departments"):
        with op.batch_alter_table("departments") as t:
            t.add_column(sa.Column("area_id", sa.String(36), sa.ForeignKey("areas.id", ondelete="SET NULL", name="fk_departments_area_id"), nullable=True))
        op.create_index("ix_departments_area_id", "departments", ["area_id"])

    nuevas_b = [
        sa.Column("area_id", sa.String(36), sa.ForeignKey("areas.id", ondelete="SET NULL", name="fk_budgets_area_id"), nullable=True),
        sa.Column("padre_id", sa.String(36), nullable=True),
        sa.Column("techo", sa.Float(), nullable=True),
        sa.Column("responsable_id", sa.String(36), sa.ForeignKey("users.id", ondelete="SET NULL", name="fk_budgets_responsable_id"), nullable=True),
        sa.Column("campana_id", sa.String(36), sa.ForeignKey("budget_campaigns.id", ondelete="SET NULL", name="fk_budgets_campana_id"), nullable=True),
        sa.Column("escenario", sa.String(40), nullable=False, server_default="base"),
        sa.Column("supuestos", sa.Text(), nullable=False, server_default="{}"),
    ]
    tiene = _cols(con, "budgets")
    with op.batch_alter_table("budgets") as t:
        for c in nuevas_b:
            if c.name not in tiene:
                t.add_column(c)
    for c in ("area_id", "padre_id", "campana_id"):
        op.create_index(f"ix_budgets_{c}", "budgets", [c])

    nuevas_l = [
        sa.Column("sentido", sa.String(10), nullable=False, server_default="gasto"),
        sa.Column("naturaleza", sa.String(10), nullable=False, server_default="opex"),
        sa.Column("vida_meses", sa.Integer(), nullable=True),
        sa.Column("unidades", sa.Float(), nullable=True),
        sa.Column("precio_unitario", sa.Float(), nullable=True),
        sa.Column("recurrencia", sa.String(12), nullable=True),
        sa.Column("mes_desde", sa.String(7), nullable=True),
        sa.Column("mes_hasta", sa.String(7), nullable=True),
        sa.Column("dedicacion_pct", sa.Float(), nullable=True),
        sa.Column("fecha_alta", sa.Date(), nullable=True),
        sa.Column("pais", sa.String(2), nullable=True),
        sa.Column("salario_anual", sa.Float(), nullable=True),
        sa.Column("justificacion", sa.Text(), nullable=True),
    ]
    tiene = _cols(con, "budget_lines")
    with op.batch_alter_table("budget_lines") as t:
        for c in nuevas_l:
            if c.name not in tiene:
                t.add_column(c)

    # El área como texto pasa a un área de verdad.
    filas = con.execute(sa.text(
        "SELECT id, organization_id, name, area FROM budgets WHERE ambito = 'area' AND area IS NOT NULL AND area <> ''")).fetchall()
    for bid, org, nombre, texto in filas:
        area_id = str(uuid.uuid4())
        con.execute(sa.text("INSERT INTO areas (id, organization_id, name, is_active) VALUES (:i, :o, :n, :a)"),
                    {"i": area_id, "o": org, "n": (nombre or "Área")[:120], "a": True})
        con.execute(sa.text("UPDATE budgets SET area_id = :a WHERE id = :b OR origen_id = :b"), {"a": area_id, "b": bid})
        for dep in [d.strip() for d in texto.split(",") if d.strip()]:
            con.execute(sa.text("UPDATE departments SET area_id = :a WHERE name = :n AND area_id IS NULL "
                                "AND (organization_id = :o OR (organization_id IS NULL AND :o IS NULL))"),
                        {"a": area_id, "n": dep, "o": org})


def downgrade() -> None:
    with op.batch_alter_table("budget_lines") as t:
        for c in ("sentido", "naturaleza", "vida_meses", "unidades", "precio_unitario", "recurrencia", "mes_desde",
                  "mes_hasta", "dedicacion_pct", "fecha_alta", "pais", "salario_anual", "justificacion"):
            t.drop_column(c)
    for c in ("area_id", "padre_id", "campana_id"):
        op.drop_index(f"ix_budgets_{c}", "budgets")
    with op.batch_alter_table("budgets") as t:
        for c in ("area_id", "padre_id", "techo", "responsable_id", "campana_id", "escenario", "supuestos"):
            t.drop_column(c)
    op.drop_index("ix_departments_area_id", "departments")
    with op.batch_alter_table("departments") as t:
        t.drop_column("area_id")
    op.drop_table("budget_templates")
    op.drop_table("budget_campaigns")
    op.drop_table("areas")
