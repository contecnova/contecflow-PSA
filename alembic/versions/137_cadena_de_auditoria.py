"""Cadena a prueba de manipulación en `audit_logs` (seq, prev_hash, entry_hash, chain_key_id).

Revisión 2026-11 (lo que contecmind y contecintelligence tenían). Las filas que
ya existían se encadenan aquí, por empresa y en orden de creación: la cadena
garantiza que nada cambió DESDE este momento, no antes.
"""
from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "137_cadena_auditoria"
down_revision: Union[str, None] = "136_valoracion_respuestas"
branch_labels = None
depends_on = None

COLUMNAS = (("seq", sa.BigInteger()), ("prev_hash", sa.String(64)), ("entry_hash", sa.String(64)),
            ("chain_key_id", sa.String(16)))


def upgrade() -> None:
    bind = op.get_bind()
    hay = {c["name"] for c in sa.inspect(bind).get_columns("audit_logs")}
    for nombre, tipo in COLUMNAS:
        if nombre not in hay:
            op.add_column("audit_logs", sa.Column(nombre, tipo, nullable=True))
    indices = {i["name"] for i in sa.inspect(bind).get_indexes("audit_logs")}
    if "ix_audit_logs_org_seq" not in indices:
        op.create_index("ix_audit_logs_org_seq", "audit_logs", ["organization_id", "seq"])
    if bind.dialect.name == "postgresql":
        # Dos filas con el mismo seq en una empresa serían una cadena bifurcada.
        op.execute("CREATE UNIQUE INDEX IF NOT EXISTS ux_audit_logs_cadena "
                   "ON audit_logs (COALESCE(organization_id, ''), seq) WHERE seq IS NOT NULL")
    from app.services.cadena_auditoria import encadenar_existentes
    encadenar_existentes(bind)


def downgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        op.execute("DROP INDEX IF EXISTS ux_audit_logs_cadena")
    op.drop_index("ix_audit_logs_org_seq", table_name="audit_logs")
    for nombre, _ in reversed(COLUMNAS):
        op.drop_column("audit_logs", nombre)
