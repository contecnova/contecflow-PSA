"""El coste de cada imputación, en la moneda de la empresa.

Revisión 2026-11. `imputations.cost_amount` se guardaba en la moneda del perfil
de coste de la persona (horas × su coste/hora) y nadie lo convertía: un perfil
en USD sumaba dólares como si fueran euros en la rentabilidad, EVM y los
presupuestos. El código ya lo guarda convertido; esto convierte las filas
antiguas cuyo perfil vigente en su fecha estaba en otra moneda, con el tipo de
cambio de esa fecha (directo o inverso). Sin tipo de cambio la fila se deja.

Revision ID: 155_coste_de_imputacion_en_moneda_de_empresa
Revises: 154_bpmn_responsable_y_sla
"""
import os

import sqlalchemy as sa
from alembic import op

revision = "155_coste_de_imputacion_en_moneda_de_empresa"
down_revision = "154_bpmn_responsable_y_sla"
branch_labels = None
depends_on = None


def upgrade() -> None:
    con = op.get_bind()
    tablas = set(sa.inspect(con).get_table_names())
    if not {"imputations", "user_cost_profiles", "exchange_rates"} <= tablas:
        return
    base = (os.getenv("DEFAULT_CURRENCY") or "EUR").upper()
    filas = con.execute(sa.text("""
        SELECT i.id, i.hours, i.hourly_rate_snapshot, i.date, p.currency
        FROM imputations i
        JOIN user_cost_profiles p ON p.user_id = i.user_id
         AND p.valid_from <= i.date AND (p.valid_to IS NULL OR p.valid_to >= i.date)
        WHERE i.hourly_rate_snapshot IS NOT NULL AND p.currency IS NOT NULL AND UPPER(p.currency) <> :base
    """), {"base": base}).fetchall()
    for id_, horas, tarifa, fecha, moneda in filas:
        directo = con.execute(sa.text(
            "SELECT rate FROM exchange_rates WHERE from_currency = :d AND to_currency = :b AND effective_date <= :f "
            "ORDER BY effective_date DESC LIMIT 1"), {"d": moneda.upper(), "b": base, "f": fecha}).scalar()
        if directo:
            tipo = float(directo)
        else:
            inverso = con.execute(sa.text(
                "SELECT rate FROM exchange_rates WHERE from_currency = :b AND to_currency = :d AND effective_date <= :f "
                "ORDER BY effective_date DESC LIMIT 1"), {"d": moneda.upper(), "b": base, "f": fecha}).scalar()
            if not inverso:
                continue
            tipo = 1.0 / float(inverso)
        con.execute(sa.text("UPDATE imputations SET cost_amount = :c WHERE id = :i"),
                    {"c": round(float(horas or 0) * float(tarifa) * tipo, 2), "i": id_})


def downgrade() -> None:
    pass    # el importe original sale de horas × hourly_rate_snapshot si hiciera falta
