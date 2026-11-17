"""Comentarios editados o retirados en su canal y festivos por empresa (17-11-2026).

Columnas nuevas en `sd_ticket_comments`:

- `edited_at`: el mensaje de origen (hilo de Slack) se edito; `body` lleva el
  texto nuevo y el anterior queda en la auditoria.
- `retracted_at`: el mensaje de origen se borro; `body` queda vacio y el
  original queda en la auditoria.

Datos (festivos): la semilla creaba los festivos sin `organization_id` y el
horario efectivo (`app/services/horario/efectivo.py`) solo cuenta los de la
empresa, asi que no contaban. Cada festivo sin empresa se copia a cada empresa
que no tenga ya uno ese dia con ese nombre, y se borra el original sin empresa
(ninguna sesion de empresa lo veia: `holidays` no admite filas globales).

Downgrade: quita las columnas. Los festivos copiados se quedan en su empresa
(no se puede saber cuales venian de la semilla).

Revision ID: 182_comentarios_de_canal_y_festivos_por_empresa
Revises: 181_versiones_avisos_y_catalogo
"""
import uuid

import sqlalchemy as sa
from alembic import op

revision = "182_comentarios_de_canal_y_festivos_por_empresa"
down_revision = "181_versiones_avisos_y_catalogo"
branch_labels = None
depends_on = None

COMENTARIOS = "sd_ticket_comments"
COLUMNAS = ("edited_at", "retracted_at")


def _columnas(tabla) -> set:
    return {c["name"] for c in sa.inspect(op.get_bind()).get_columns(tabla)}


def festivos_por_empresa(con) -> int:
    """Copia los festivos sin empresa a cada empresa y borra los originales.
    Devuelve cuantas filas se han creado (idempotente: la segunda vez, 0)."""
    tablas = set(sa.inspect(con).get_table_names())
    if "holidays" not in tablas or "organizations" not in tablas:
        return 0
    globales = con.execute(sa.text(
        "SELECT id, name, date, type, applies_to, office_id FROM holidays WHERE organization_id IS NULL")).fetchall()
    if not globales:
        return 0
    empresas = [r[0] for r in con.execute(sa.text("SELECT id FROM organizations")).fetchall()]
    creadas = 0
    for org in empresas:
        existentes = {(r[0], str(r[1])) for r in con.execute(sa.text(
            "SELECT name, date FROM holidays WHERE organization_id = :org"), {"org": org}).fetchall()}
        for h in globales:
            if (h.name, str(h.date)) in existentes:
                continue
            con.execute(sa.text(
                "INSERT INTO holidays (id, organization_id, name, date, type, applies_to, office_id) "
                "VALUES (:id, :org, :name, :date, :type, :applies_to, NULL)"),
                {"id": str(uuid.uuid4()), "org": org, "name": h.name, "date": h.date, "type": h.type,
                 "applies_to": h.applies_to})
            creadas += 1
    if empresas:
        con.execute(sa.text("DELETE FROM holidays WHERE organization_id IS NULL"))
    return creadas


def upgrade() -> None:
    hay = _columnas(COMENTARIOS)
    for nombre in COLUMNAS:
        if nombre not in hay:
            with op.batch_alter_table(COMENTARIOS) as b:
                b.add_column(sa.Column(nombre, sa.DateTime(timezone=True), nullable=True))
    festivos_por_empresa(op.get_bind())


def downgrade() -> None:
    hay = _columnas(COMENTARIOS)
    with op.batch_alter_table(COMENTARIOS) as b:
        for nombre in COLUMNAS:
            if nombre in hay:
                b.drop_column(nombre)
