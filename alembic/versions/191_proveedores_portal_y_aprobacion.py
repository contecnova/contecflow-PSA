"""Proveedores: portal del proveedor, aprobación por importe y fuentes de medición (19-11-2026).

Ver `docs/PROVEEDORES_Y_EXTERNALIZACION.md` §13-§15.

Columnas nuevas (ninguna tabla nueva):

- `subcontractor_workers.supplier_portal`: la persona externa es contacto del
  portal de su proveedor (informes, partes, evidencias de SLA, paquetes,
  consumo y estado de cuenta, solo de su proveedor). Por defecto, no.
- `supplier_services.metering_source` (`manual` | `cmdb` | `external`),
  `metering_config` (JSON: filtros de la CMDB o sistema externo, agregación),
  `metering_last_at`, `metering_last_quantity`, `metering_last_error`.
- `supplier_usage_records.detail` (JSON: muestras, máximo, media, último,
  sistema) y `source_system` (CMDB, SIEM…). `source` admite `cmdb` y `api`.
- `supplier_reports.report_type` (`progress` | `periodic` | `service_log` |
  `sla_evidence`), `attachments` (JSON: evidencias) y `submitted_via`
  (`internal` | `portal`).
- `supplier_statements.approval_request_id`: solicitud del motor de
  aprobaciones (estado `pending_approval` mientras está en la bandeja).

Idempotente: cada columna se crea solo si no existe. Downgrade: las quita.

Revision ID: 191_proveedores_portal_y_aprobacion
Revises: 190_cmdb_software_y_vulnerabilidades
"""
import sqlalchemy as sa
from alembic import op

revision = "191_proveedores_portal_y_aprobacion"
down_revision = "190_cmdb_software_y_vulnerabilidades"
branch_labels = None
depends_on = None

COLUMNAS = (
    ("subcontractor_workers", sa.Column("supplier_portal", sa.Boolean(), nullable=False, server_default=sa.false())),
    ("supplier_services", sa.Column("metering_source", sa.String(20), nullable=True)),
    ("supplier_services", sa.Column("metering_config", sa.JSON(), nullable=True)),
    ("supplier_services", sa.Column("metering_last_at", sa.DateTime(timezone=True), nullable=True)),
    ("supplier_services", sa.Column("metering_last_quantity", sa.Float(), nullable=True)),
    ("supplier_services", sa.Column("metering_last_error", sa.String(255), nullable=True)),
    ("supplier_usage_records", sa.Column("detail", sa.JSON(), nullable=True)),
    ("supplier_usage_records", sa.Column("source_system", sa.String(100), nullable=True)),
    ("supplier_reports", sa.Column("report_type", sa.String(20), nullable=False, server_default="progress")),
    ("supplier_reports", sa.Column("attachments", sa.JSON(), nullable=True)),
    ("supplier_reports", sa.Column("submitted_via", sa.String(10), nullable=False, server_default="internal")),
    ("supplier_statements", sa.Column("approval_request_id", sa.String(36), nullable=True)),
)


def _columnas(tabla: str) -> set:
    insp = sa.inspect(op.get_bind())
    if tabla not in insp.get_table_names():
        return set()
    return {c["name"] for c in insp.get_columns(tabla)}


def _existe(tabla: str) -> bool:
    return tabla in sa.inspect(op.get_bind()).get_table_names()


def upgrade() -> None:
    for tabla, columna in COLUMNAS:
        if _existe(tabla) and columna.name not in _columnas(tabla):
            op.add_column(tabla, columna.copy())
    # Los informes que ya habia: de servicio = periodico; de paquete = avance.
    if _existe("supplier_reports"):
        op.execute("UPDATE supplier_reports SET report_type = 'periodic' "
                   "WHERE service_id IS NOT NULL AND report_type = 'progress'")
    if _existe("supplier_statements") and "approval_request_id" in _columnas("supplier_statements"):
        indices = {i["name"] for i in sa.inspect(op.get_bind()).get_indexes("supplier_statements")}
        if "ix_supplier_statements_approval_request_id" not in indices:
            op.create_index("ix_supplier_statements_approval_request_id", "supplier_statements",
                            ["approval_request_id"])


def downgrade() -> None:
    if _existe("supplier_statements"):
        indices = {i["name"] for i in sa.inspect(op.get_bind()).get_indexes("supplier_statements")}
        if "ix_supplier_statements_approval_request_id" in indices:
            op.drop_index("ix_supplier_statements_approval_request_id", table_name="supplier_statements")
    for tabla, columna in reversed(COLUMNAS):
        if columna.name in _columnas(tabla):
            with op.batch_alter_table(tabla) as b:
                b.drop_column(columna.name)
