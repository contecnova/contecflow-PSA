"""Los hitos facturados guardan el importe que se facturó.

Revisión 2026-11. Un hito definido sólo por porcentaje se facturaba con su
importe calculado, pero el hito se quedaba sin `billing_amount` y Rentabilidad
(que suma ese campo) lo contaba como 0. Desde ahora la factura lo fija; aquí se
rellenan los ya facturados con el importe de su línea de factura.

Revision ID: 148_importe_facturado_en_el_hito
Revises: 147_bloqueo_de_imputaciones_en_ajustes
"""
import sqlalchemy as sa
from alembic import op

revision = "148_importe_facturado_en_el_hito"
down_revision = "147_bloqueo_de_imputaciones_en_ajustes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    con = op.get_bind()
    hitos = con.execute(sa.text(
        "SELECT id, invoice_id FROM project_milestones "
        "WHERE billing_amount IS NULL AND is_billed = :t AND invoice_id IS NOT NULL"), {"t": True}).fetchall()
    for hito_id, factura_id in hitos:
        importe = con.execute(sa.text(
            "SELECT amount FROM invoice_lines WHERE invoice_id = :f AND source_type = 'milestone' "
            "AND source_ids LIKE :s"), {"f": factura_id, "s": f'%"{hito_id}"%'}).scalar()
        if importe is not None:
            con.execute(sa.text("UPDATE project_milestones SET billing_amount = :a WHERE id = :i"),
                        {"a": importe, "i": hito_id})


def downgrade() -> None:
    # Es el importe que se facturó: no hay un estado anterior que devolver.
    pass
