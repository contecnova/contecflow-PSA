"""Cierra las diferencias entre el esquema de PostgreSQL y los modelos.

Auditoria 2026-11. Al pasar por primera vez la cadena entera sobre un
PostgreSQL vacio, `compare_metadata` contra los modelos dejo 144 diferencias.
Las que son indices de mas en la base (los de claves ajenas de la 073, los
trigram de la 083 y los parciales de la 2f165b37fe82) se quedan: los crean
esas revisiones a proposito y no cambian ningun resultado. El resto se cierra
aqui:

- Enums con el nombre de tipo cruzado. `assettype` y `uatstatus` los
  compartian dos enums distintos en los modelos, y la 001 creo `assetstatus`
  con los valores de ALM para ALM y para Service Desk. Postgres crea el primer
  tipo y el segundo se queda sin sus valores: un activo de Service Desk con
  estado `in_stock` o tipo `hardware` no se podia guardar. Pasa igual en las
  bases que vienen de `create_all`. Cada columna pasa a su tipo, que se crea o
  se completa con los valores que falten (los que sobran no estorban).
- Tres UNIQUE por organizacion que la 077 no pudo crear porque la tabla aun
  no tenia `organization_id`: el codigo era unico en toda la base.
- `api_keys.key_prefix` de 8 a 16 caracteres, como el modelo.
- `users.organization_id` con ON DELETE RESTRICT, como el modelo (SET NULL
  sobre una columna NOT NULL no podia cumplirse).
- 23 fechas sin zona horaria a TIMESTAMPTZ; los valores se guardaban en UTC.
- 24 columnas de borrado logico NOT NULL (las migraciones de alineacion ya
  las creaban asi; eran los modelos los que se habian quedado atras) y
  `performance_reviews.answers_json` NOT NULL.
- 17 indices que declaran los modelos y ninguna revision creaba.

Cada paso mira antes el estado real, asi que sobre una base que ya este bien
no hace nada. SQLite no se toca: no tiene tipos enum ni ALTER COLUMN, y alli
el esquema sigue saliendo de la cadena como hasta ahora.
"""
from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "097_paridad_postgres_con_los_modelos"
down_revision: Union[str, None] = "096_columnas_de_decision_de_producto"
branch_labels = None
depends_on = None


# (tabla, columna, tipo, valores que el modelo necesita)
ENUMS = (
    ("alm_assets", "type", "alm_assettype",
     ("laptop", "desktop", "server", "mobile", "tablet", "network", "printer",
      "monitor", "peripheral", "vm", "other")),
    ("alm_assets", "status", "alm_assetstatus",
     ("in_use", "available", "in_repair", "retired", "lost", "stolen")),
    ("sd_assets", "asset_type", "assettype",
     ("hardware", "software", "license", "consumable", "cloud", "other")),
    ("sd_assets", "status", "assetstatus",
     ("in_stock", "deployed", "in_repair", "retired", "disposed", "loaned",
      "pending_order")),
    ("uat_cases", "status", "uatstatus",
     ("pending", "passed", "failed", "blocked", "skipped")),
    ("uat_sessions", "status", "uat_session_status",
     ("pending", "in_progress", "passed", "failed", "conditional")),
    ("uat_sessions", "client_result", "uat_session_status",
     ("pending", "in_progress", "passed", "failed", "conditional")),
)

# (tabla, columna, nombre nuevo)
PER_TENANT_UNIQUES = (
    ("alm_cost_centers", "code", "uq_alm_cost_center_code_per_org"),
    ("sd_assets", "code", "uq_sd_asset_code_per_org"),
    ("sd_configuration_items", "code", "uq_sd_ci_code_per_org"),
)

TIMESTAMPTZ = (
    ("abac_attribute_definitions", "created_at"),
    ("abac_attribute_definitions", "updated_at"),
    ("abac_policies", "starts_at"),
    ("abac_policies", "expires_at"),
    ("abac_policies", "created_at"),
    ("abac_policies", "updated_at"),
    ("abac_policies", "last_evaluated_at"),
    ("ai_guardrail_audit_logs", "evaluated_at"),
    ("ai_guardrail_policies", "created_at"),
    ("ai_guardrail_policies", "updated_at"),
    ("client_health_snapshots", "snapshot_at"),
    ("client_nps", "created_at"),
    ("git_deployments", "deployed_at"),
    ("git_deployments", "created_at"),
    ("git_deployments", "updated_at"),
    ("git_pull_requests", "merged_at"),
    ("git_pull_requests", "closed_at"),
    ("git_pull_requests", "created_at"),
    ("git_pull_requests", "updated_at"),
    ("policy_audit_log", "created_at"),
    ("user_attributes", "expires_at"),
    ("user_attributes", "created_at"),
    ("user_attributes", "updated_at"),
)

# (tabla, columna, valor para las filas a NULL)
NOT_NULL = (
    ("alm_assets", "is_active", "true"),
    ("alm_contracts", "is_active", "true"),
    ("alm_licenses", "is_active", "true"),
    ("alm_software_installs", "is_active", "true"),
    ("cmdb_items", "is_active", "true"),
    ("cmdb_relations", "is_active", "true"),
    ("deliverables", "is_active", "true"),
    ("imputations", "is_active", "true"),
    ("kanban_columns", "is_active", "true"),
    ("notifications", "is_active", "true"),
    ("okr_key_results", "is_active", "true"),
    ("okr_objectives", "is_active", "true"),
    ("project_permissions", "is_active", "true"),
    ("rate_entries", "is_active", "true"),
    ("sla_calendar_holidays", "is_active", "true"),
    ("sla_calendars", "is_active", "true"),
    ("sprint_plans", "is_active", "true"),
    ("sso_configs", "is_deleted", "false"),
    ("subcontractor_rates", "is_active", "true"),
    ("subcontractor_timelogs", "is_active", "true"),
    ("subcontractor_worker_skills", "is_active", "true"),
    ("wiki_tags", "is_active", "true"),
    ("workflow_states", "is_active", "true"),
    ("workflow_transitions", "is_active", "true"),
    ("performance_reviews", "answers_json", "'{}'"),
)

# (nombre, tabla, columna)
INDEXES = (
    ("ix_capacity_plans_created_by", "capacity_plans", "created_by"),
    ("ix_document_permissions_granted_by", "document_permissions", "granted_by"),
    ("ix_document_versions_created_by", "document_versions", "created_by"),
    ("ix_documents_approved_by", "documents", "approved_by"),
    ("ix_documents_updated_by", "documents", "updated_by"),
    ("ix_integration_credentials_provider", "integration_credentials", "provider"),
    ("ix_notifications_is_active", "notifications", "is_active"),
    ("ix_project_milestones_approval_requested_by", "project_milestones", "approval_requested_by"),
    ("ix_project_milestones_approved_by", "project_milestones", "approved_by"),
    ("ix_project_milestones_completed_by", "project_milestones", "completed_by"),
    ("ix_project_milestones_invoice_id", "project_milestones", "invoice_id"),
    ("ix_project_milestones_rejected_by", "project_milestones", "rejected_by"),
    ("ix_task_comments_author_id", "task_comments", "author_id"),
    ("ix_tasks_code", "tasks", "code"),
    ("ix_tasks_created_by", "tasks", "created_by"),
    ("ix_tasks_reporter_id", "tasks", "reporter_id"),
    ("ix_timesheets_reviewed_by", "timesheets", "reviewed_by"),
)


def _column(conn, table: str, column: str):
    return conn.execute(sa.text(
        "SELECT udt_name, data_type, is_nullable, character_maximum_length, column_default "
        "FROM information_schema.columns "
        "WHERE table_schema = current_schema() AND table_name = :t AND column_name = :c"
    ), {"t": table, "c": column}).first()


def _enum_labels(conn, type_name: str):
    rows = conn.execute(sa.text(
        "SELECT e.enumlabel FROM pg_type t JOIN pg_enum e ON e.enumtypid = t.oid "
        "WHERE t.typname = :n"
    ), {"n": type_name}).scalars().all()
    exists = conn.execute(sa.text("SELECT 1 FROM pg_type WHERE typname = :n"), {"n": type_name}).first()
    return set(rows) if exists else None


def _fix_enum(conn, table, column, type_name, labels) -> None:
    col = _column(conn, table, column)
    if col is None:
        return
    have = _enum_labels(conn, type_name)
    if have is None:
        values = ", ".join(f"'{v}'" for v in labels)
        op.execute(f'CREATE TYPE "{type_name}" AS ENUM ({values})')
    else:
        for v in labels:
            if v not in have:
                op.execute(f"ALTER TYPE \"{type_name}\" ADD VALUE IF NOT EXISTS '{v}'")
    if col.udt_name != type_name:
        if col.column_default is not None:
            op.execute(f'ALTER TABLE "{table}" ALTER COLUMN "{column}" DROP DEFAULT')
        op.execute(
            f'ALTER TABLE "{table}" ALTER COLUMN "{column}" TYPE "{type_name}" '
            f'USING "{column}"::text::"{type_name}"'
        )


def _fix_per_tenant_unique(conn, table, column, new_name) -> None:
    if _column(conn, table, column) is None or _column(conn, table, "organization_id") is None:
        return
    uniques = sa.inspect(conn).get_unique_constraints(table)
    if any(uc["name"] == new_name for uc in uniques):
        return
    for uc in uniques:
        if uc["column_names"] == [column]:
            op.drop_constraint(uc["name"], table, type_="unique")
    for ix in sa.inspect(conn).get_indexes(table):
        if ix.get("unique") and ix["column_names"] == [column]:
            op.drop_index(ix["name"], table_name=table)
    op.create_unique_constraint(new_name, table, ["organization_id", column])


def _fix_users_org_fk(conn) -> None:
    for fk in sa.inspect(conn).get_foreign_keys("users"):
        if fk["constrained_columns"] != ["organization_id"]:
            continue
        if (fk.get("options", {}).get("ondelete") or "").upper() == "RESTRICT":
            return
        op.drop_constraint(fk["name"], "users", type_="foreignkey")
    op.create_foreign_key(
        "users_organization_id_fkey", "users", "organizations",
        ["organization_id"], ["id"], ondelete="RESTRICT",
    )


def upgrade() -> None:
    conn = op.get_bind()
    if conn.dialect.name != "postgresql":
        return

    for table, column, type_name, labels in ENUMS:
        _fix_enum(conn, table, column, type_name, labels)

    for table, column, new_name in PER_TENANT_UNIQUES:
        _fix_per_tenant_unique(conn, table, column, new_name)

    col = _column(conn, "api_keys", "key_prefix")
    if col is not None and (col.character_maximum_length or 0) < 16:
        op.alter_column("api_keys", "key_prefix", type_=sa.String(16),
                        existing_type=sa.String(col.character_maximum_length))

    if _column(conn, "users", "organization_id") is not None:
        _fix_users_org_fk(conn)

    for table, column in TIMESTAMPTZ:
        col = _column(conn, table, column)
        if col is not None and col.data_type == "timestamp without time zone":
            op.execute(
                f'ALTER TABLE "{table}" ALTER COLUMN "{column}" TYPE TIMESTAMP WITH TIME ZONE '
                f"USING \"{column}\" AT TIME ZONE 'UTC'"
            )

    for table, column, fill in NOT_NULL:
        col = _column(conn, table, column)
        if col is not None and col.is_nullable == "YES":
            op.execute(f'UPDATE "{table}" SET "{column}" = {fill} WHERE "{column}" IS NULL')
            op.execute(f'ALTER TABLE "{table}" ALTER COLUMN "{column}" SET NOT NULL')

    existing = set(sa.inspect(conn).get_table_names())
    for name, table, column in INDEXES:
        if table in existing:
            op.execute(f'CREATE INDEX IF NOT EXISTS "{name}" ON "{table}" ("{column}")')


def downgrade() -> None:
    # Volver atras reintroduce los fallos que esta revision cierra (activos de
    # Service Desk que no se pueden guardar, codigos unicos en toda la base).
    pass
