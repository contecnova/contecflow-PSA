"""Licencias y hardware, fases 1 y 3: titulares, ciclo de vida, actas, costes, renovaciones y conciliación.

Revisión 16-11-2026.

- `alm_license_assignments` se amplía EN EL SITIO (mismos ids: lo que ya
  apunta a una asignación sigue valiendo) y pasa a ser la asignación universal
  (`ALMAsignacion`): recurso licencia o activo; titular persona, proyecto,
  departamento, cliente o dispositivo; modo asignación, préstamo o bolsa;
  estado e intervalo; motivo, aprobación, cierre e imputación del coste.
  Columnas renombradas: user_id → holder_user_id, project_id →
  holder_project_id, asset_id (el equipo titular) → holder_asset_id,
  expires_at → valid_to; `asset_id` vuelve como el ACTIVO asignado.
  `is_active` se convierte en `status` (activa → active; inactiva → ended).
- Migración de datos: cada activo con `assigned_to_id` pasa a tener su
  asignación vigente; cada asignación migrada deja su evento en el historial.
- Tablas nuevas: `alm_eventos` (historial inmutable), `alm_actas`,
  `alm_adjuntos`, `alm_picos_concurrencia`, `alm_renovaciones`,
  `alm_facturas_proveedor`.
- `alm_licenses`: métrica, SKU, nivel, pico concurrente, amortización,
  refacturable y la clave CIFRADA (los valores en claro se cifran aquí con
  `app.core.encryption`; `license_key_hint` guarda los 4 últimos caracteres).
- `alm_assets`: residual, renting, refacturable y baja; estados nuevos
  `ordered`, `on_loan`, `disposed`.
- `alm_renewal_alerts` (estaba muerta) pasa a registro de avisos enviados:
  `kind`, `reference_date` y unicidad.

Downgrade: deshace columnas y tablas, borra las asignaciones de activos,
devuelve `is_active` y las claves en claro. En PostgreSQL los valores nuevos
del tipo `alm_assetstatus` no se pueden quitar: los activos con esos estados
vuelven a `available`, `in_use` o `retired`.

Revision ID: 170_alm_titulares_ciclo_y_costes
Revises: 169_bpmn_decisiones_y_codigos_de_error
"""
import json
import uuid
from datetime import date, datetime

import sqlalchemy as sa
from alembic import op

revision = "170_alm_titulares_ciclo_y_costes"
down_revision = "169_bpmn_decisiones_y_codigos_de_error"
branch_labels = None
depends_on = None

T = "alm_license_assignments"


def _cols(con, tabla):
    return {c["name"] for c in sa.inspect(con).get_columns(tabla)}


def _tablas(con):
    return set(sa.inspect(con).get_table_names())


def _fecha(v):
    if v is None:
        return None
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    try:
        return date.fromisoformat(str(v)[:10])
    except ValueError:
        return None


def _id():
    return sa.Column("id", sa.String(36), primary_key=True)


def _org():
    return sa.Column("organization_id", sa.String(36), sa.ForeignKey("organizations.id"), nullable=True, index=True)


# ── Upgrade ───────────────────────────────────────────────────────────────────

def _ampliar_asignaciones(con):
    cols = _cols(con, T)
    if "holder_type" in cols:
        return
    # Los índices de las columnas que cambian de nombre se rehacen con el nombre nuevo.
    renombradas = {"user_id": "holder_user_id", "project_id": "holder_project_id", "asset_id": "holder_asset_id"}
    for ix in sa.inspect(con).get_indexes(T):
        if set(ix["column_names"]) & set(renombradas):
            op.drop_index(ix["name"], table_name=T)
    with op.batch_alter_table(T) as t:
        t.alter_column("user_id", new_column_name="holder_user_id", existing_type=sa.String(36))
        t.alter_column("project_id", new_column_name="holder_project_id", existing_type=sa.String(36))
        t.alter_column("asset_id", new_column_name="holder_asset_id", existing_type=sa.String(36))
        t.alter_column("expires_at", new_column_name="valid_to", existing_type=sa.Date())
        t.alter_column("license_id", existing_type=sa.String(36), nullable=True)
    with op.batch_alter_table(T) as t:
        t.add_column(sa.Column("resource_type", sa.String(10), nullable=True))
        t.add_column(sa.Column("asset_id", sa.String(36), nullable=True))
        t.add_column(sa.Column("holder_type", sa.String(12), nullable=True))
        t.add_column(sa.Column("holder_department_id", sa.String(36), nullable=True))
        t.add_column(sa.Column("holder_client_id", sa.String(36), nullable=True))
        t.add_column(sa.Column("mode", sa.String(12), nullable=True))
        t.add_column(sa.Column("parent_id", sa.String(36), nullable=True))
        t.add_column(sa.Column("quantity", sa.Integer(), nullable=True))
        t.add_column(sa.Column("status", sa.String(12), nullable=True))
        t.add_column(sa.Column("valid_from", sa.Date(), nullable=True))
        t.add_column(sa.Column("ended_on", sa.Date(), nullable=True))
        t.add_column(sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True))
        t.add_column(sa.Column("ended_by", sa.String(36), nullable=True))
        t.add_column(sa.Column("end_kind", sa.String(12), nullable=True))
        t.add_column(sa.Column("end_reason", sa.Text(), nullable=True))
        t.add_column(sa.Column("reason", sa.Text(), nullable=True))
        t.add_column(sa.Column("source", sa.String(30), nullable=True))
        t.add_column(sa.Column("approved_by", sa.String(36), nullable=True))
        t.add_column(sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True))
        t.add_column(sa.Column("charge_project_id", sa.String(36), nullable=True))
        t.add_column(sa.Column("charge_cost_center_id", sa.String(36), nullable=True))
        t.add_column(sa.Column("charge_client_id", sa.String(36), nullable=True))
        t.add_column(sa.Column("rebillable", sa.Boolean(), nullable=True))

    # Datos: las asignaciones de licencia que había.
    hoy = date.today()
    filas = con.execute(sa.text(
        f"SELECT id, holder_user_id, holder_project_id, holder_asset_id, assigned_at, valid_to, is_active FROM {T}"
    )).fetchall()
    for f in filas:
        if f.holder_user_id:
            tipo, modo = "user", "assignment"
        elif f.holder_asset_id:
            tipo, modo = "asset", "assignment"
        elif f.holder_project_id:
            tipo, modo = "project", "pool"
        else:
            tipo, modo = "user", "assignment"    # el titular se borró: queda cerrada
        desde = _fecha(f.assigned_at) or hoy
        activa = bool(f.is_active) and (f.holder_user_id or f.holder_asset_id or f.holder_project_id)
        fin = None if activa else (_fecha(f.valid_to) or desde)
        if fin is not None and fin < desde:
            fin = desde
        con.execute(sa.text(
            f"UPDATE {T} SET resource_type='license', holder_type=:tipo, mode=:modo, quantity=1, "
            "status=:estado, valid_from=:desde, ended_on=:fin, end_kind=:fk, source='migration' WHERE id=:id"),
            {"tipo": tipo, "modo": modo, "estado": "active" if activa else "ended", "desde": desde,
             "fin": fin, "fk": None if activa else "released", "id": f.id})

    with op.batch_alter_table(T) as t:
        t.alter_column("resource_type", existing_type=sa.String(10), nullable=False)
        t.alter_column("holder_type", existing_type=sa.String(12), nullable=False)
        t.alter_column("mode", existing_type=sa.String(12), nullable=False, server_default="assignment")
        t.alter_column("quantity", existing_type=sa.Integer(), nullable=False, server_default="1")
        t.alter_column("status", existing_type=sa.String(12), nullable=False, server_default="active")
        t.alter_column("valid_from", existing_type=sa.Date(), nullable=False)
        t.alter_column("source", existing_type=sa.String(30), nullable=False, server_default="manual")
        t.drop_column("is_active")
        t.create_foreign_key("fk_alm_asig_asset", "alm_assets", ["asset_id"], ["id"], ondelete="CASCADE")
        t.create_foreign_key("fk_alm_asig_dep", "departments", ["holder_department_id"], ["id"], ondelete="SET NULL")
        t.create_foreign_key("fk_alm_asig_client", "clients", ["holder_client_id"], ["id"], ondelete="SET NULL")
        t.create_foreign_key("fk_alm_asig_parent", T, ["parent_id"], ["id"], ondelete="CASCADE")
        t.create_foreign_key("fk_alm_asig_ended_by", "users", ["ended_by"], ["id"], ondelete="SET NULL")
        t.create_foreign_key("fk_alm_asig_approved_by", "users", ["approved_by"], ["id"], ondelete="SET NULL")
        t.create_foreign_key("fk_alm_asig_charge_project", "projects", ["charge_project_id"], ["id"], ondelete="SET NULL")
        t.create_foreign_key("fk_alm_asig_charge_cc", "alm_cost_centers", ["charge_cost_center_id"], ["id"], ondelete="SET NULL")
        t.create_foreign_key("fk_alm_asig_charge_client", "clients", ["charge_client_id"], ["id"], ondelete="SET NULL")
    for nombre, columnas in (("ix_alm_license_assignments_holder_user_id", ["holder_user_id"]),
                             ("ix_alm_license_assignments_holder_project_id", ["holder_project_id"]),
                             ("ix_alm_license_assignments_holder_asset_id", ["holder_asset_id"]),
                             ("ix_alm_license_assignments_asset_id", ["asset_id"]),
                             ("ix_alm_license_assignments_holder_department_id", ["holder_department_id"]),
                             ("ix_alm_license_assignments_holder_client_id", ["holder_client_id"]),
                             ("ix_alm_license_assignments_parent_id", ["parent_id"]),
                             ("ix_alm_license_assignments_status", ["status"]),
                             ("ix_alm_license_assignments_ended_by", ["ended_by"]),
                             ("ix_alm_license_assignments_charge_project_id", ["charge_project_id"]),
                             ("ix_alm_license_assignments_charge_cost_center_id", ["charge_cost_center_id"]),
                             ("ix_alm_license_assignments_charge_client_id", ["charge_client_id"]),
                             ("ix_alm_asignaciones_licencia_estado", ["license_id", "status"]),
                             ("ix_alm_asignaciones_activo_estado", ["asset_id", "status"])):
        op.create_index(nombre, T, columnas)


def _crear_tablas(con):
    tablas = _tablas(con)
    if "alm_eventos" not in tablas:
        op.create_table(
            "alm_eventos", _id(), _org(),
            sa.Column("resource_type", sa.String(10), nullable=False),
            sa.Column("license_id", sa.String(36), sa.ForeignKey("alm_licenses.id", ondelete="SET NULL"), index=True),
            sa.Column("asset_id", sa.String(36), sa.ForeignKey("alm_assets.id", ondelete="SET NULL"), index=True),
            sa.Column("contract_id", sa.String(36), sa.ForeignKey("alm_contracts.id", ondelete="SET NULL"), index=True),
            sa.Column("assignment_id", sa.String(36), sa.ForeignKey(f"{T}.id", ondelete="SET NULL"), index=True),
            sa.Column("event", sa.String(30), nullable=False),
            sa.Column("holder_type", sa.String(12)), sa.Column("holder_id", sa.String(36)),
            sa.Column("holder_name", sa.String(200)),
            sa.Column("actor_id", sa.String(36), sa.ForeignKey("users.id", ondelete="SET NULL"), index=True),
            sa.Column("reason", sa.Text()), sa.Column("data", sa.Text()),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), index=True),
        )
        op.create_index("ix_alm_eventos_titular", "alm_eventos", ["holder_type", "holder_id"])
    if "alm_facturas_proveedor" not in tablas:
        op.create_table(
            "alm_facturas_proveedor", _id(), _org(),
            sa.Column("vendor_id", sa.String(36), sa.ForeignKey("alm_vendors.id", ondelete="SET NULL"), index=True),
            sa.Column("contract_id", sa.String(36), sa.ForeignKey("alm_contracts.id", ondelete="SET NULL"), index=True),
            sa.Column("license_id", sa.String(36), sa.ForeignKey("alm_licenses.id", ondelete="SET NULL"), index=True),
            sa.Column("number", sa.String(100), nullable=False),
            sa.Column("issue_date", sa.Date(), nullable=False),
            sa.Column("period_from", sa.Date()), sa.Column("period_to", sa.Date()),
            sa.Column("amount", sa.Float(), nullable=False), sa.Column("tax_amount", sa.Float()),
            sa.Column("currency", sa.String(3)),
            sa.Column("expense_id", sa.String(36), sa.ForeignKey("expenses.id", ondelete="SET NULL"), index=True),
            sa.Column("status", sa.String(12), nullable=False, server_default="pending", index=True),
            sa.Column("expected_amount", sa.Float()), sa.Column("difference", sa.Float()),
            sa.Column("issues", sa.Text()), sa.Column("notes", sa.Text()),
            sa.Column("reconciled_by", sa.String(36), sa.ForeignKey("users.id", ondelete="SET NULL")),
            sa.Column("reconciled_at", sa.DateTime(timezone=True)),
            sa.Column("created_by", sa.String(36), sa.ForeignKey("users.id", ondelete="SET NULL")),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.UniqueConstraint("organization_id", "vendor_id", "number", name="uq_alm_factura_numero_por_proveedor"),
        )
    if "alm_actas" not in tablas:
        op.create_table(
            "alm_actas", _id(), _org(),
            sa.Column("kind", sa.String(10), nullable=False),
            sa.Column("assignment_id", sa.String(36), sa.ForeignKey(f"{T}.id", ondelete="CASCADE"), nullable=False, index=True),
            sa.Column("asset_id", sa.String(36), sa.ForeignKey("alm_assets.id", ondelete="CASCADE"), nullable=False, index=True),
            sa.Column("signer_user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="SET NULL"), index=True),
            sa.Column("issued_by", sa.String(36), sa.ForeignKey("users.id", ondelete="SET NULL")),
            sa.Column("checklist", sa.Text()), sa.Column("condition", sa.String(10)),
            sa.Column("observations", sa.Text()),
            sa.Column("document_id", sa.String(36), sa.ForeignKey("documents.id", ondelete="SET NULL")),
            sa.Column("envelope_id", sa.String(36), sa.ForeignKey("esign_envelopes.id", ondelete="SET NULL")),
            sa.Column("status", sa.String(20), nullable=False, server_default="pending_signature"),
            sa.Column("signed_at", sa.DateTime(timezone=True)),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        )
    if "alm_adjuntos" not in tablas:
        op.create_table(
            "alm_adjuntos", _id(), _org(),
            sa.Column("asset_id", sa.String(36), sa.ForeignKey("alm_assets.id", ondelete="CASCADE"), index=True),
            sa.Column("act_id", sa.String(36), sa.ForeignKey("alm_actas.id", ondelete="CASCADE"), index=True),
            sa.Column("invoice_id", sa.String(36), sa.ForeignKey("alm_facturas_proveedor.id", ondelete="CASCADE"), index=True),
            sa.Column("document_id", sa.String(36), sa.ForeignKey("documents.id", ondelete="CASCADE"), nullable=False),
            sa.Column("kind", sa.String(30), nullable=False, server_default="photo"),
            sa.Column("uploaded_by", sa.String(36), sa.ForeignKey("users.id", ondelete="SET NULL")),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        )
    if "alm_picos_concurrencia" not in tablas:
        op.create_table(
            "alm_picos_concurrencia", _id(), _org(),
            sa.Column("license_id", sa.String(36), sa.ForeignKey("alm_licenses.id", ondelete="CASCADE"), nullable=False, index=True),
            sa.Column("measured_at", sa.DateTime(timezone=True), nullable=False, index=True),
            sa.Column("peak", sa.Integer(), nullable=False),
            sa.Column("source", sa.String(40), nullable=False, server_default="manual"),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        )
    if "alm_renovaciones" not in tablas:
        op.create_table(
            "alm_renovaciones", _id(), _org(),
            sa.Column("entity_type", sa.String(10), nullable=False),
            sa.Column("contract_id", sa.String(36), sa.ForeignKey("alm_contracts.id", ondelete="CASCADE"), index=True),
            sa.Column("license_id", sa.String(36), sa.ForeignKey("alm_licenses.id", ondelete="CASCADE"), index=True),
            sa.Column("term_date", sa.Date(), nullable=False),
            sa.Column("decision", sa.String(10), nullable=False),
            sa.Column("new_seats", sa.Integer()), sa.Column("new_annual_cost", sa.Float()),
            sa.Column("reason", sa.Text()), sa.Column("usage_snapshot", sa.Text()),
            sa.Column("status", sa.String(12), nullable=False, server_default="pending"),
            sa.Column("decided_by", sa.String(36), sa.ForeignKey("users.id", ondelete="SET NULL")),
            sa.Column("decided_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column("applied_at", sa.DateTime(timezone=True)),
        )


def _licencias(con):
    cols = _cols(con, "alm_licenses")
    with op.batch_alter_table("alm_licenses") as t:
        if "metric" not in cols:
            t.add_column(sa.Column("metric", sa.String(20), nullable=False, server_default="named_user"))
        for nombre, tipo in (("sku", sa.String(100)), ("tier", sa.String(100)), ("tier_rank", sa.Integer()),
                             ("concurrent_peak", sa.Integer()), ("concurrent_peak_at", sa.DateTime(timezone=True)),
                             ("amortization_months", sa.Integer()), ("license_key_hint", sa.String(8))):
            if nombre not in cols:
                t.add_column(sa.Column(nombre, tipo, nullable=True))
        if "rebillable" not in cols:
            t.add_column(sa.Column("rebillable", sa.Boolean(), nullable=False, server_default=sa.false()))
        t.alter_column("license_key", existing_type=sa.String(1000), type_=sa.Text(), existing_nullable=True)
    con.execute(sa.text("UPDATE alm_licenses SET metric='device' WHERE type='device'"))
    con.execute(sa.text("UPDATE alm_licenses SET metric='concurrent' WHERE type='concurrent'"))
    con.execute(sa.text("UPDATE alm_licenses SET metric='volume' WHERE type='volume'"))
    # Cifrar las claves que estaban en claro.
    from app.core.encryption import encrypt_value
    for fila in con.execute(sa.text("SELECT id, license_key FROM alm_licenses WHERE license_key IS NOT NULL")).fetchall():
        valor = fila.license_key or ""
        if not valor.strip() or valor.startswith(("v2:", "kmsv1:")):
            continue
        con.execute(sa.text("UPDATE alm_licenses SET license_key=:c, license_key_hint=:h WHERE id=:id"),
                    {"c": encrypt_value(valor.strip()), "h": valor.strip()[-4:], "id": fila.id})


def _activos(con):
    if con.dialect.name == "postgresql":
        with op.get_context().autocommit_block():
            for valor in ("ordered", "on_loan", "disposed"):
                op.execute(f"ALTER TYPE alm_assetstatus ADD VALUE IF NOT EXISTS '{valor}'")
    cols = _cols(con, "alm_assets")
    with op.batch_alter_table("alm_assets") as t:
        for nombre, tipo in (("residual_value", sa.Float()), ("lease_monthly_cost", sa.Float()),
                             ("disposal_date", sa.Date()), ("disposal_reason", sa.String(30)),
                             ("disposal_method", sa.String(30)), ("disposal_value", sa.Float())):
            if nombre not in cols:
                t.add_column(sa.Column(nombre, tipo, nullable=True))
        if "rebillable" not in cols:
            t.add_column(sa.Column("rebillable", sa.Boolean(), nullable=False, server_default=sa.false()))


def _asignaciones_de_activos(con):
    """Cada activo con persona asignada pasa a tener su asignación (y su evento)."""
    hoy = date.today()
    filas = con.execute(sa.text(
        "SELECT id, organization_id, assigned_to_id, status, created_at, updated_at FROM alm_assets "
        "WHERE assigned_to_id IS NOT NULL AND is_active = :t"), {"t": True}).fetchall()
    for f in filas:
        ya = con.execute(sa.text(f"SELECT 1 FROM {T} WHERE asset_id=:a AND status='active'"), {"a": f.id}).first()
        if ya:
            continue
        aid = str(uuid.uuid4())
        desde = _fecha(f.updated_at) or _fecha(f.created_at) or hoy
        con.execute(sa.text(
            f"INSERT INTO {T} (id, organization_id, resource_type, asset_id, holder_type, holder_user_id, mode, "
            "quantity, status, valid_from, source) VALUES (:id, :org, 'asset', :a, 'user', :u, 'assignment', 1, "
            "'active', :d, 'migration')"), {"id": aid, "org": f.organization_id, "a": f.id, "u": f.assigned_to_id, "d": desde})
        estado = str(f.status or "")
        if estado not in ("in_use", "AssetStatus.in_use", "ALMAssetStatus.in_use"):
            con.execute(sa.text("UPDATE alm_assets SET status='in_use' WHERE id=:a"), {"a": f.id})
    # Activos «en uso» sin persona pero con proyecto o departamento: ese es su titular.
    for f in con.execute(sa.text(
            "SELECT id, organization_id, project_id, department_id, created_at, updated_at FROM alm_assets "
            "WHERE assigned_to_id IS NULL AND is_active = :t AND status = 'in_use' "
            "AND (project_id IS NOT NULL OR department_id IS NOT NULL)"), {"t": True}).fetchall():
        tipo, col, titular = (("project", "holder_project_id", f.project_id) if f.project_id
                              else ("department", "holder_department_id", f.department_id))
        con.execute(sa.text(
            f"INSERT INTO {T} (id, organization_id, resource_type, asset_id, holder_type, {col}, mode, quantity, "
            "status, valid_from, source) VALUES (:id, :org, 'asset', :a, :tipo, :h, 'assignment', 1, 'active', :d, "
            "'migration')"), {"id": str(uuid.uuid4()), "org": f.organization_id, "a": f.id, "tipo": tipo,
                              "h": titular, "d": _fecha(f.updated_at) or _fecha(f.created_at) or hoy})
    # Un evento «assigned» por asignación migrada, para que el historial empiece con ella.
    for f in con.execute(sa.text(
            f"SELECT id, organization_id, resource_type, license_id, asset_id, holder_type, holder_user_id, "
            f"holder_project_id, holder_asset_id, status FROM {T} WHERE source='migration'")).fetchall():
        titular = f.holder_user_id or f.holder_project_id or f.holder_asset_id
        con.execute(sa.text(
            "INSERT INTO alm_eventos (id, organization_id, resource_type, license_id, asset_id, assignment_id, event, "
            "holder_type, holder_id, data) VALUES (:id, :org, :rt, :l, :a, :asig, 'assigned', :ht, :hid, :d)"),
            {"id": str(uuid.uuid4()), "org": f.organization_id, "rt": f.resource_type, "l": f.license_id,
             "a": f.asset_id, "asig": f.id, "ht": f.holder_type, "hid": titular,
             "d": json.dumps({"source": "migration", "status": f.status})})


def _avisos(con):
    cols = _cols(con, "alm_renewal_alerts")
    with op.batch_alter_table("alm_renewal_alerts") as t:
        if "kind" not in cols:
            t.add_column(sa.Column("kind", sa.String(20), nullable=False, server_default="notice"))
        if "reference_date" not in cols:
            t.add_column(sa.Column("reference_date", sa.Date(), nullable=True))
        t.create_unique_constraint("uq_alm_renewal_alert_once", ["organization_id", "entity_type", "entity_id",
                                                                  "kind", "reference_date"])


def upgrade() -> None:
    con = op.get_bind()
    _licencias(con)
    _activos(con)
    _ampliar_asignaciones(con)
    _crear_tablas(con)
    _asignaciones_de_activos(con)
    _avisos(con)


# ── Downgrade ─────────────────────────────────────────────────────────────────

def downgrade() -> None:
    con = op.get_bind()
    with op.batch_alter_table("alm_renewal_alerts") as t:
        t.drop_constraint("uq_alm_renewal_alert_once", type_="unique")
        t.drop_column("reference_date")
        t.drop_column("kind")
    for tabla in ("alm_adjuntos", "alm_actas", "alm_facturas_proveedor", "alm_picos_concurrencia",
                  "alm_renovaciones", "alm_eventos"):
        op.drop_table(tabla)

    # Asignaciones: fuera las de activos (el activo conserva `assigned_to_id`) y las bolsas hijas.
    con.execute(sa.text(f"DELETE FROM {T} WHERE parent_id IS NOT NULL"))
    con.execute(sa.text(f"DELETE FROM {T} WHERE resource_type='asset'"))
    with op.batch_alter_table(T) as t:
        t.add_column(sa.Column("is_active", sa.Boolean(), nullable=True))
    con.execute(sa.text(f"UPDATE {T} SET is_active = CASE WHEN status IN ('active','pending') THEN :t ELSE :f END"),
                {"t": True, "f": False})
    for nombre in ("ix_alm_license_assignments_holder_user_id", "ix_alm_license_assignments_holder_project_id",
                   "ix_alm_license_assignments_holder_asset_id",
                   "ix_alm_license_assignments_asset_id", "ix_alm_license_assignments_holder_department_id",
                   "ix_alm_license_assignments_holder_client_id", "ix_alm_license_assignments_parent_id",
                   "ix_alm_license_assignments_status", "ix_alm_license_assignments_ended_by",
                   "ix_alm_license_assignments_charge_project_id", "ix_alm_license_assignments_charge_cost_center_id",
                   "ix_alm_license_assignments_charge_client_id", "ix_alm_asignaciones_licencia_estado",
                   "ix_alm_asignaciones_activo_estado"):
        op.drop_index(nombre, table_name=T)
    with op.batch_alter_table(T) as t:
        for fk in ("fk_alm_asig_asset", "fk_alm_asig_dep", "fk_alm_asig_client", "fk_alm_asig_parent",
                   "fk_alm_asig_ended_by", "fk_alm_asig_approved_by", "fk_alm_asig_charge_project",
                   "fk_alm_asig_charge_cc", "fk_alm_asig_charge_client"):
            t.drop_constraint(fk, type_="foreignkey")
        for col in ("resource_type", "asset_id", "holder_type", "holder_department_id", "holder_client_id", "mode",
                    "parent_id", "quantity", "status", "valid_from", "ended_on", "ended_at", "ended_by", "end_kind",
                    "end_reason", "reason", "source", "approved_by", "approved_at", "charge_project_id",
                    "charge_cost_center_id", "charge_client_id", "rebillable"):
            t.drop_column(col)
    with op.batch_alter_table(T) as t:
        t.alter_column("holder_user_id", new_column_name="user_id", existing_type=sa.String(36))
        t.alter_column("holder_project_id", new_column_name="project_id", existing_type=sa.String(36))
        t.alter_column("holder_asset_id", new_column_name="asset_id", existing_type=sa.String(36))
        t.alter_column("valid_to", new_column_name="expires_at", existing_type=sa.Date())
    for viejo in ("user_id", "project_id", "asset_id"):
        op.create_index(f"ix_{T}_{viejo}", T, [viejo])

    # Activos: estados que la versión anterior no conoce.
    con.execute(sa.text("UPDATE alm_assets SET status='available' WHERE status='ordered'"))
    con.execute(sa.text("UPDATE alm_assets SET status='in_use' WHERE status='on_loan'"))
    con.execute(sa.text("UPDATE alm_assets SET status='retired' WHERE status='disposed'"))
    with op.batch_alter_table("alm_assets") as t:
        for col in ("residual_value", "lease_monthly_cost", "rebillable", "disposal_date", "disposal_reason",
                    "disposal_method", "disposal_value"):
            t.drop_column(col)

    # Licencias: claves en claro otra vez (la versión anterior las leía así).
    from app.core.encryption import decrypt_value
    for fila in con.execute(sa.text("SELECT id, license_key FROM alm_licenses WHERE license_key IS NOT NULL")).fetchall():
        if str(fila.license_key).startswith(("v2:", "kmsv1:")):
            con.execute(sa.text("UPDATE alm_licenses SET license_key=:c WHERE id=:id"),
                        {"c": (decrypt_value(fila.license_key) or "")[:1000], "id": fila.id})
    with op.batch_alter_table("alm_licenses") as t:
        for col in ("metric", "sku", "tier", "tier_rank", "concurrent_peak", "concurrent_peak_at",
                    "amortization_months", "rebillable", "license_key_hint"):
            t.drop_column(col)
        t.alter_column("license_key", existing_type=sa.Text(), type_=sa.String(1000), existing_nullable=True)
