"""Un solo motor de reconocimiento de ingresos (ASC 606).

Revisión 2026-11. Había dos motores que escribían en tablas distintas y no
cuadraban entre sí: el antiguo (reglas por proyecto, `revenue_recognition_*`),
que sólo leía su propia pantalla, y el ASC 606 (`rev_*`), que es el que leen la
analítica, las métricas y la conversión de oportunidades. Queda el ASC 606:

- `ascmethod` gana `percentage_complete` y `completed_contract` (los dos métodos
  que sólo tenía el antiguo).
- Cada regla antigua pasa a ser un contrato (time_and_material → over_time;
  milestone y milestone_billing → milestone; el resto, igual) y cada entrada
  con importe reconocido, un asiento `recognized` de su mes.
- Las tablas antiguas se retiran.

Revision ID: 156_un_solo_motor_de_ingresos
Revises: 155_coste_de_imputacion_en_moneda_de_empresa
"""
import os
import uuid

import sqlalchemy as sa
from alembic import op

revision = "156_un_solo_motor_de_ingresos"
down_revision = "155_coste_de_imputacion_en_moneda_de_empresa"
branch_labels = None
depends_on = None

_METODO = {"time_and_material": "over_time", "milestone_billing": "milestone", "milestone": "milestone",
           "percentage_complete": "percentage_complete", "completed_contract": "completed_contract",
           "straight_line": "straight_line"}


def upgrade() -> None:
    con = op.get_bind()
    if con.dialect.name == "postgresql":
        with op.get_context().autocommit_block():
            for v in ("percentage_complete", "completed_contract"):
                op.execute(f"ALTER TYPE ascmethod ADD VALUE IF NOT EXISTS '{v}'")
    tablas = set(sa.inspect(con).get_table_names())
    if "revenue_recognition_rules" not in tablas:
        return
    reglas = con.execute(sa.text("""
        SELECT r.id, COALESCE(r.organization_id, p.organization_id), r.project_id, r.method, r.contract_value,
               r.start_date, r.end_date, r.notes, p.name, p.client_id, p.currency
        FROM revenue_recognition_rules r JOIN projects p ON p.id = r.project_id""")).fetchall()
    contrato_de = {}
    base = (os.getenv("DEFAULT_CURRENCY") or "EUR").upper()
    for rid, org, pid, metodo, valor, ini, fin, notas, nombre, cliente, moneda in reglas:
        if not org:
            continue
        cid = str(uuid.uuid4())
        moneda = (moneda or base).upper()
        contrato_de[rid] = (cid, org, moneda)
        metodo = str(metodo).split(".")[-1]
        con.execute(sa.text("""
            INSERT INTO rev_contracts (id, organization_id, project_id, client_id, name, contract_value, currency,
                                       method, start_date, end_date, is_active, notes, created_at, updated_at)
            VALUES (:id, :org, :pid, :cli, :name, :valor, :moneda, :metodo, :ini, :fin, :activo, :notas,
                    CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"""),
            {"id": cid, "org": org, "pid": pid, "cli": cliente, "name": f"{nombre} (regla migrada)",
             "valor": float(valor or 0), "moneda": moneda, "metodo": _METODO.get(metodo, "over_time"),
             "ini": ini, "fin": fin, "activo": True, "notas": notas})
    if "revenue_recognition_entries" in tablas:
        for rid, periodo, importe, notas in con.execute(sa.text(
                "SELECT rule_id, period_date, amount_actual, notes FROM revenue_recognition_entries "
                "WHERE amount_actual IS NOT NULL AND amount_actual <> 0")).fetchall():
            if rid not in contrato_de or periodo is None:
                continue
            cid, org, moneda = contrato_de[rid]
            anio, mes = (periodo.year, periodo.month) if hasattr(periodo, "year") else (int(str(periodo)[:4]), int(str(periodo)[5:7]))
            con.execute(sa.text("""
                INSERT INTO rev_entries (id, organization_id, rev_contract_id, entry_type, amount, currency,
                                         period_year, period_month, description, created_at)
                VALUES (:id, :org, :cid, 'recognized', :imp, :moneda, :a, :m, :d, CURRENT_TIMESTAMP)"""),
                {"id": str(uuid.uuid4()), "org": org, "cid": cid, "imp": float(importe), "moneda": moneda, "a": anio, "m": mes,
                 "d": f"Migrado del motor antiguo{': ' + notas if notas else ''}"})
    op.drop_table("revenue_recognition_entries")
    op.drop_table("revenue_recognition_rules")
    if con.dialect.name == "postgresql":
        op.execute("DROP TYPE IF EXISTS recognitionmethod")


def downgrade() -> None:
    # Vuelve la estructura del motor antiguo, vacía: sus datos ya viven en rev_contracts/rev_entries.
    op.create_table(
        "revenue_recognition_rules",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("organization_id", sa.String(36), sa.ForeignKey("organizations.id"), nullable=True),
        sa.Column("project_id", sa.String(36), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("method", sa.String(30), nullable=False),
        sa.Column("contract_value", sa.Numeric(14, 2), nullable=True),
        sa.Column("start_date", sa.Date(), nullable=True),
        sa.Column("end_date", sa.Date(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
    )
    op.create_table(
        "revenue_recognition_entries",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("organization_id", sa.String(36), sa.ForeignKey("organizations.id"), nullable=True),
        sa.Column("rule_id", sa.String(36), sa.ForeignKey("revenue_recognition_rules.id", ondelete="CASCADE")),
        sa.Column("project_id", sa.String(36), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("period_date", sa.Date(), nullable=False),
        sa.Column("amount_actual", sa.Numeric(14, 2), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
    )
