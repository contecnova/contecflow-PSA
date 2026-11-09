"""Tickets y envíos de formularios públicos: a la empresa del formulario.

Revisión 2026-11. La petición pública es anónima y el ticket se creaba con
`organization_id` vacío: ninguna empresa lo veía en su Service Desk. El código
ya los crea en su empresa; esto recoloca los que se crearon antes, siguiendo
el envío hasta su formulario. Sólo datos.

Revision ID: 145_formularios_publicos_en_su_empresa
Revises: 144_presupuestos
"""
from alembic import op

revision = "145_formularios_publicos_en_su_empresa"
down_revision = "144_presupuestos"
branch_labels = None
depends_on = None


def upgrade() -> None:
    import re
    import sqlalchemy as sa
    con = op.get_bind()
    con.execute(sa.text("""
        UPDATE public_form_submissions SET organization_id = (
            SELECT f.organization_id FROM public_forms f WHERE f.id = public_form_submissions.form_id)
        WHERE organization_id IS NULL
    """))
    # Medido en una copia: los huérfanos se numeraban contando sólo huérfanos
    # (dos INC-0004) y chocan con el INC-0004 de su empresa. El que choca toma
    # el siguiente número libre de su prefijo en esa empresa.
    huerfanos = con.execute(sa.text("""
        SELECT t.id, t.number, s.organization_id FROM sd_tickets t
        JOIN public_form_submissions s ON s.created_entity_id = t.id AND s.created_entity_type = 'ticket'
        WHERE t.source = 'public_form' AND t.organization_id IS NULL AND s.organization_id IS NOT NULL
        ORDER BY t.created_at
    """)).fetchall()
    for tid, numero, org in huerfanos:
        choca = con.execute(sa.text("SELECT 1 FROM sd_tickets WHERE organization_id = :o AND number = :n"),
                            {"o": org, "n": numero}).first()
        if choca:
            prefijo, _, cifras = numero.rpartition("-")
            usados = [r[0] for r in con.execute(sa.text(
                "SELECT number FROM sd_tickets WHERE organization_id = :o AND number LIKE :p"),
                {"o": org, "p": prefijo + "-%"})]
            siguiente = max([int(m.group(1)) for u in usados if (m := re.search(r"-(\d+)$", u))] or [0]) + 1
            numero = f"{prefijo}-{str(siguiente).zfill(len(cifras))}"
        con.execute(sa.text("UPDATE sd_tickets SET organization_id = :o, number = :n WHERE id = :i"),
                    {"o": org, "n": numero, "i": tid})


def downgrade() -> None:
    # No se puede saber cuáles estaban vacíos: volver a vaciarlos los
    # escondería otra vez. Irreversible a propósito.
    pass
