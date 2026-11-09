"""Cada módulo de IA con un solo nombre: el de Gobierno de IA.

Revisión 2026-11. Los registros de acciones se guardaban como
`contecflowassist`, `contecflowagent` y `contecfloworacle`, y Gobierno de IA
cuenta `nexusassist`, `nexusagent` y `nexusoracle`: el uso por módulo salía
vacío y el tope diario no saltaba nunca. Se renombran los registros, y se
quitan las configuraciones con los nombres viejos (las creaba un servicio que
nadie llamaba y ningún interruptor las leía).

Revision ID: 149_modulos_de_ia_con_un_nombre
Revises: 148_importe_facturado_en_el_hito
"""
import sqlalchemy as sa
from alembic import op

revision = "149_modulos_de_ia_con_un_nombre"
down_revision = "148_importe_facturado_en_el_hito"
branch_labels = None
depends_on = None

NOMBRES = {"contecflowassist": "nexusassist", "contecflowagent": "nexusagent", "contecfloworacle": "nexusoracle"}


def upgrade() -> None:
    con = op.get_bind()
    tablas = set(sa.inspect(con).get_table_names())
    if "ai_action_logs" in tablas:
        for viejo, nuevo in NOMBRES.items():
            con.execute(sa.text("UPDATE ai_action_logs SET module = :n WHERE module = :v"), {"n": nuevo, "v": viejo})
    if "ai_governance_configs" in tablas:
        for viejo in NOMBRES:
            con.execute(sa.text("DELETE FROM ai_governance_configs WHERE module = :v"), {"v": viejo})


def downgrade() -> None:
    con = op.get_bind()
    for viejo, nuevo in NOMBRES.items():
        con.execute(sa.text("UPDATE ai_action_logs SET module = :v WHERE module = :n"), {"n": nuevo, "v": viejo})
