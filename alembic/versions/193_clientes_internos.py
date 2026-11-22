"""Clientes internos: unidades de la propia compañía con showback/chargeback (22-11-2026).

Un solo modelo de cliente con `kind` externo|interno. Las filas que ya había
son externas (server_default). Diseño completo en `docs/CLIENTES_INTERNOS.md`.

Columnas nuevas en `clients`:

- `kind` (externo|interno, NOT NULL, por defecto externo) e `internal_type`
  (departamento|unidad_negocio|filial|centro_coste).
- Vínculo con la estructura: `department_id`, `area_id`, `cost_center_id`
  (`alm_cost_centers`) y `group_organization_id` (empresa del grupo, para
  intercompañía).
- `business_owner_id`: responsable de negocio (firma hitos, aprueba excesos).
- Finanzas internas: `finance_mode` (showback|chargeback|intercompania),
  `cost_method` (horas_coste|tarifa_interna|precio_cerrado|catalogo),
  `internal_rate_table_id` (`rate_tables`), `transfer_markup_pct` (margen del
  precio de transferencia) y `erp_account` (cuenta/centro para el asiento).

En `sd_service_items`: `internal_price` (precio del catálogo interno por
petición atendida). En `uat_sessions`: `internal_signed_by` (el empleado que
firma la UAT en el portal interno; `client_signed_by` es de `client_users`).

En `client_nps`: `survey_type` (nps|csat) y `respondent_user_id` (empleado que
responde en el portal interno; dato personal: base legal relación laboral,
retención la de la respuesta).

Tablas nuevas:

- `internal_client_roles`: designaciones explícitas (usuario clave de UAT,
  finanzas de la unidad, delegado del responsable). Los usuarios de la unidad
  NO se dan de alta: salen de `users.department` / centro de coste.
- `internal_shared_costs`: servicios compartidos a repartir por criterio
  (usuarios, tickets, licencias, software, fijo).
- `internal_charges` + `internal_charge_lines`: informe de showback, nota de
  cargo interna (sin IVA ni factura legal) o cargo intercompañía (enlaza la
  factura de `invoices`).
- `project_benefits`: caso de negocio y seguimiento de beneficios por proyecto.
- `internal_adoption_items`: plan de adopción y formación por proyecto/unidad.

Idempotente: cada tabla/columna/índice solo se crea si no existe. Downgrade:
quita tablas y columnas (los datos de clientes externos no se tocan).

Revision ID: 193_clientes_internos
Revises: 192_textos_por_clave_y_cierre
"""
import sqlalchemy as sa
from alembic import op

revision = "193_clientes_internos"
down_revision = "192_textos_por_clave_y_cierre"
branch_labels = None
depends_on = None


def _fk(tabla: str, ondelete: str = "SET NULL"):
    return sa.ForeignKey(f"{tabla}.id", ondelete=ondelete)


def _columnas_nuevas():
    return (
        ("clients", sa.Column("kind", sa.String(10), nullable=False, server_default="externo")),
        ("clients", sa.Column("internal_type", sa.String(20), nullable=True)),
        ("clients", sa.Column("department_id", sa.String(36), nullable=True)),
        ("clients", sa.Column("area_id", sa.String(36), nullable=True)),
        ("clients", sa.Column("cost_center_id", sa.String(36), nullable=True)),
        ("clients", sa.Column("group_organization_id", sa.String(36), nullable=True)),
        ("clients", sa.Column("business_owner_id", sa.String(36), nullable=True)),
        ("clients", sa.Column("finance_mode", sa.String(15), nullable=True)),
        ("clients", sa.Column("cost_method", sa.String(20), nullable=True)),
        ("clients", sa.Column("internal_rate_table_id", sa.String(36), nullable=True)),
        ("clients", sa.Column("transfer_markup_pct", sa.Float(), nullable=True)),
        ("clients", sa.Column("erp_account", sa.String(40), nullable=True)),
        ("client_nps", sa.Column("survey_type", sa.String(10), nullable=False, server_default="nps")),
        ("client_nps", sa.Column("respondent_user_id", sa.String(36), nullable=True)),
        ("sd_service_items", sa.Column("internal_price", sa.Float(), nullable=True)),
        ("uat_sessions", sa.Column("internal_signed_by", sa.String(36), nullable=True)),
    )


INDICES = (
    ("ix_clients_kind", "clients", ["kind"]),
    ("ix_clients_department_id", "clients", ["department_id"]),
    ("ix_clients_area_id", "clients", ["area_id"]),
    ("ix_clients_cost_center_id", "clients", ["cost_center_id"]),
    ("ix_clients_business_owner_id", "clients", ["business_owner_id"]),
    ("ix_client_nps_respondent_user_id", "client_nps", ["respondent_user_id"]),
    ("ix_uat_sessions_internal_signed_by", "uat_sessions", ["internal_signed_by"]),
)


def _tablas():
    org = lambda: sa.Column("organization_id", sa.String(36), _fk("organizations", "CASCADE"), nullable=True, index=True)  # noqa: E731
    creado = lambda: sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now())  # noqa: E731
    return (
        ("internal_client_roles", (
            sa.Column("id", sa.String(36), primary_key=True),
            org(),
            sa.Column("client_id", sa.String(36), _fk("clients", "CASCADE"), nullable=False, index=True),
            sa.Column("user_id", sa.String(36), _fk("users", "CASCADE"), nullable=False, index=True),
            sa.Column("role", sa.String(20), nullable=False),  # usuario_clave | finanzas | delegado
            sa.Column("created_by", sa.String(36), _fk("users"), nullable=True),
            creado(),
            sa.UniqueConstraint("client_id", "user_id", "role", name="uq_internal_client_role"),
        )),
        ("internal_shared_costs", (
            sa.Column("id", sa.String(36), primary_key=True),
            org(),
            sa.Column("name", sa.String(200), nullable=False),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("monthly_amount", sa.Float(), nullable=False, server_default="0"),
            sa.Column("currency", sa.String(3), nullable=True),
            sa.Column("criterion", sa.String(15), nullable=False, server_default="usuarios"),
            sa.Column("fixed_shares", sa.Text(), nullable=False, server_default="{}"),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("created_by", sa.String(36), _fk("users"), nullable=True),
            creado(),
        )),
        ("internal_charges", (
            sa.Column("id", sa.String(36), primary_key=True),
            org(),
            sa.Column("client_id", sa.String(36), _fk("clients", "CASCADE"), nullable=False, index=True),
            sa.Column("number", sa.String(30), nullable=False),
            sa.Column("period", sa.String(7), nullable=False, index=True),  # YYYY-MM
            sa.Column("mode", sa.String(15), nullable=False),  # showback | chargeback | intercompania
            sa.Column("status", sa.String(15), nullable=False, server_default="borrador", index=True),
            sa.Column("total", sa.Float(), nullable=False, server_default="0"),
            sa.Column("currency", sa.String(3), nullable=True),
            sa.Column("invoice_id", sa.String(36), _fk("invoices"), nullable=True, index=True),
            sa.Column("erp_reference", sa.String(80), nullable=True),
            sa.Column("notes", sa.Text(), nullable=True),
            sa.Column("created_by", sa.String(36), _fk("users"), nullable=True),
            sa.Column("issued_by", sa.String(36), _fk("users"), nullable=True),
            sa.Column("issued_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("exported_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
            creado(),
            sa.UniqueConstraint("organization_id", "number", name="uq_internal_charge_number"),
        )),
        ("internal_charge_lines", (
            sa.Column("id", sa.String(36), primary_key=True),
            org(),
            sa.Column("charge_id", sa.String(36), _fk("internal_charges", "CASCADE"), nullable=False, index=True),
            sa.Column("source", sa.String(20), nullable=False),
            sa.Column("source_ref", sa.String(36), nullable=True),
            sa.Column("project_id", sa.String(36), _fk("projects"), nullable=True, index=True),
            sa.Column("description", sa.String(500), nullable=False),
            sa.Column("quantity", sa.Float(), nullable=True),
            sa.Column("unit_amount", sa.Float(), nullable=True),
            sa.Column("amount", sa.Float(), nullable=False, server_default="0"),
        )),
        ("project_benefits", (
            sa.Column("id", sa.String(36), primary_key=True),
            org(),
            sa.Column("project_id", sa.String(36), _fk("projects", "CASCADE"), nullable=False, index=True),
            sa.Column("name", sa.String(200), nullable=False),
            sa.Column("kind", sa.String(15), nullable=False, server_default="ahorro"),  # ahorro | ingreso | riesgo | intangible
            sa.Column("unit", sa.String(30), nullable=True),
            sa.Column("baseline", sa.Float(), nullable=True),
            sa.Column("target", sa.Float(), nullable=True),
            sa.Column("actual", sa.Float(), nullable=True),
            sa.Column("target_date", sa.Date(), nullable=True),
            sa.Column("measured_at", sa.Date(), nullable=True),
            sa.Column("owner_id", sa.String(36), _fk("users"), nullable=True, index=True),
            sa.Column("notes", sa.Text(), nullable=True),
            creado(),
        )),
        ("internal_adoption_items", (
            sa.Column("id", sa.String(36), primary_key=True),
            org(),
            sa.Column("client_id", sa.String(36), _fk("clients", "CASCADE"), nullable=False, index=True),
            sa.Column("project_id", sa.String(36), _fk("projects"), nullable=True, index=True),
            sa.Column("course_id", sa.String(36), _fk("training_courses"), nullable=True),
            sa.Column("kind", sa.String(15), nullable=False, server_default="formacion"),  # formacion | comunicacion | soporte | hito
            sa.Column("title", sa.String(200), nullable=False),
            sa.Column("due_date", sa.Date(), nullable=True),
            sa.Column("status", sa.String(15), nullable=False, server_default="pendiente"),  # pendiente | en_curso | hecho
            sa.Column("target_users", sa.Integer(), nullable=True),
            sa.Column("reached_users", sa.Integer(), nullable=True),
            creado(),
        )),
    )


def _bind():
    return op.get_bind()


def _existe(tabla: str) -> bool:
    return tabla in sa.inspect(_bind()).get_table_names()


def _columnas(tabla: str) -> set:
    if not _existe(tabla):
        return set()
    return {c["name"] for c in sa.inspect(_bind()).get_columns(tabla)}


def _indices(tabla: str) -> set:
    if not _existe(tabla):
        return set()
    return {i["name"] for i in sa.inspect(_bind()).get_indexes(tabla)}


def upgrade() -> None:
    for tabla, columna in _columnas_nuevas():
        if _existe(tabla) and columna.name not in _columnas(tabla):
            op.add_column(tabla, columna)
    for nombre, tabla, cols in INDICES:
        if _existe(tabla) and nombre not in _indices(tabla):
            op.create_index(nombre, tabla, cols)
    for nombre, columnas in _tablas():
        if not _existe(nombre):
            op.create_table(nombre, *columnas)


def downgrade() -> None:
    for nombre, _ in reversed(_tablas()):
        if _existe(nombre):
            op.drop_table(nombre)
    for nombre, tabla, _ in INDICES:
        if nombre in _indices(tabla):
            op.drop_index(nombre, table_name=tabla)
    for tabla, columna in reversed(_columnas_nuevas()):
        if columna.name in _columnas(tabla):
            with op.batch_alter_table(tabla) as b:
                b.drop_column(columna.name)
