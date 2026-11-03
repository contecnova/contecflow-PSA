"""Un solo inventario de activos: ALM.

Auditoria 2026-11: habia dos. ALM (`alm_assets`) tiene pantalla, proveedores,
contratos, licencias, instalaciones y centros de coste. Los activos del
Service Desk (`sd_assets`) no tenian pantalla, pero eran los unicos con enlace
al CI, historial de cambios, fechas de ciclo de vida y el escaneo diario que
abre un ticket de renovacion.

Manda ALM. Esta migracion:

- anade a `alm_assets` el CI, el fin de vida, el fin de leasing, el proximo
  mantenimiento, su contrato y el ticket de renovacion abierto;
- crea `alm_asset_history`;
- copia `sd_assets` conservando el id. Si ya hay un activo de ALM con el mismo
  numero de serie, se funde con el. Lo que ALM no tiene como columna (codigo,
  numero de pedido, proveedor en texto, licencia, etiquetas) va a las notas;
- copia el historial y borra `sd_asset_history` y `sd_assets`.
"""
from __future__ import annotations

from datetime import date
from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "111_un_solo_inventario"
down_revision: Union[str, None] = "110_una_sola_cmdb"
branch_labels = None
depends_on = None

TIPO = {"cloud": "vm"}  # el resto (hardware, software, licencia, fungible...) -> other
ESTADO = {"in_stock": "available", "deployed": "in_use", "in_repair": "in_repair",
          "retired": "retired", "disposed": "retired", "loaned": "in_use", "pending_order": "available"}

COLUMNAS = (
    sa.Column("ci_id", sa.String(36), nullable=True),
    sa.Column("eol_date", sa.Date, nullable=True),
    sa.Column("lease_expiry", sa.Date, nullable=True),
    sa.Column("next_maintenance_date", sa.Date, nullable=True),
    sa.Column("maintenance_contract", sa.String(255), nullable=True),
    sa.Column("refresh_ticket_id", sa.String(36), nullable=True),
)


def _fecha(valor):
    """Las fechas de `sd_assets` eran texto `AAAA-MM-DD`; lo ilegible se pierde."""
    if not valor:
        return None
    try:
        return date.fromisoformat(str(valor)[:10])
    except ValueError:
        return None


def _valor(v):
    return getattr(v, "value", v)


def upgrade() -> None:
    bind = op.get_bind()

    with op.batch_alter_table("alm_assets") as batch:
        for c in COLUMNAS:
            batch.add_column(c.copy())
        batch.create_index("ix_alm_assets_ci_id", ["ci_id"])
        batch.create_foreign_key("fk_alm_assets_ci", "sd_configuration_items", ["ci_id"], ["id"], ondelete="SET NULL")
        batch.create_foreign_key("fk_alm_assets_refresh_ticket", "sd_tickets", ["refresh_ticket_id"], ["id"], ondelete="SET NULL")

    op.create_table(
        "alm_asset_history",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("organization_id", sa.String(36), sa.ForeignKey("organizations.id"), nullable=True, index=True),
        sa.Column("asset_id", sa.String(36), sa.ForeignKey("alm_assets.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("field_name", sa.String(100), nullable=False),
        sa.Column("old_value", sa.String(500), nullable=True),
        sa.Column("new_value", sa.String(500), nullable=True),
        sa.Column("changed_by", sa.String(36), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("note", sa.String(255), nullable=True),
        sa.Column("changed_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    if not sa.inspect(bind).has_table("sd_assets"):
        return

    equivalente: dict[str, str] = {}
    por_serie = {s: i for i, s in bind.execute(sa.text(
        "SELECT id, serial_number FROM alm_assets WHERE serial_number IS NOT NULL"))}
    etiquetas = {t for (t,) in bind.execute(sa.text("SELECT asset_tag FROM alm_assets WHERE asset_tag IS NOT NULL"))}

    # Medido: segun como se creo la base faltan columnas (en una creada con
    # alembic `sd_asset_history` no tiene `organization_id`). Se lee con `get`.
    for v in bind.execute(sa.text("SELECT * FROM sd_assets")).mappings().all():
        extra = [f"{k}: {v[k]}" for k in ("code", "po_number", "vendor", "vendor_contract", "part_number",
                                          "license_key", "license_seats", "department", "tags") if v.get(k)]
        notas = "\n".join(x for x in (v.get("notes"), "[Service Desk] " + " · ".join(extra) if extra else None) if x)
        fechas = {k: _fecha(v[k]) for k in ("purchase_date", "warranty_expiry", "eol_date", "lease_expiry",
                                            "next_maintenance_date")}
        destino = por_serie.get(v.get("serial_number")) if v.get("serial_number") else None
        if destino:
            # Se funde: lo que ALM no tenia, sin pisar lo que ya habia.
            datos = {**fechas, "ci_id": v.get("ci_id"), "maintenance_contract": v.get("maintenance_contract"),
                     "location": v.get("location"), "assigned_to_id": v.get("assigned_user_id")}
            sets = ", ".join(f"{k} = COALESCE({k}, :{k})" for k in datos)
            if notas:
                sets += ", notes = CASE WHEN notes IS NULL THEN :notas ELSE notes || :salto || :notas END"
            bind.execute(sa.text(f"UPDATE alm_assets SET {sets} WHERE id = :id"),
                         {**datos, "id": destino, "notas": notas, "salto": "\n"})
            equivalente[v.get("id")] = destino
            continue
        etiqueta = v.get("code") if v.get("code") and v.get("code") not in etiquetas else None
        if etiqueta:
            etiquetas.add(etiqueta)
        bind.execute(sa.text("""
            INSERT INTO alm_assets
              (id, organization_id, name, type, model, brand, serial_number, asset_tag, status, condition,
               is_active, assigned_to_id, location, purchase_date, purchase_price, currency, warranty_expiry,
               depreciation_years, notes, created_at, ci_id, eol_date, lease_expiry, next_maintenance_date,
               maintenance_contract)
            VALUES (:id, :org, :name, :tipo, :model, :brand, :serie, :etiqueta, :estado, 'good',
               :activo, :asignado, :location, :purchase_date, :precio, :moneda, :warranty_expiry,
               3, :notas, COALESCE(:creado, CURRENT_TIMESTAMP), :ci, :eol_date, :lease_expiry,
               :next_maintenance_date, :contrato)"""), {
            **fechas, "id": v.get("id"), "org": v.get("organization_id"), "name": v.get("name"),
            "tipo": TIPO.get(_valor(v.get("asset_type")), "other"), "model": v.get("model"),
            "brand": v.get("manufacturer"), "serie": v.get("serial_number"), "etiqueta": etiqueta,
            "estado": ESTADO.get(_valor(v.get("status")), "available"),
            "activo": _valor(v.get("status")) not in ("retired", "disposed"),
            "asignado": v.get("assigned_user_id"), "location": v.get("location"), "precio": v.get("purchase_price"),
            "moneda": v.get("currency"), "notas": notas or None, "creado": v.get("created_at"), "ci": v.get("ci_id"),
            "contrato": v.get("maintenance_contract"),
        })
        if v.get("serial_number"):
            por_serie[v.get("serial_number")] = v.get("id")
        equivalente[v.get("id")] = v.get("id")

    for h in bind.execute(sa.text("SELECT * FROM sd_asset_history")).mappings().all():
        if h.get("asset_id") not in equivalente:
            continue
        bind.execute(sa.text("""
            INSERT INTO alm_asset_history
              (id, organization_id, asset_id, field_name, old_value, new_value, changed_by, note, changed_at)
            VALUES (:id, :org, :asset, :campo, :antes, :despues, :quien, :nota, :cuando)"""), {
            "id": h.get("id"), "org": h.get("organization_id"), "asset": equivalente[h.get("asset_id")],
            "campo": h.get("field_name"), "antes": h.get("old_value"), "despues": h.get("new_value"),
            "quien": h.get("changed_by"), "nota": h.get("note"), "cuando": h.get("changed_at")})

    op.drop_table("sd_asset_history")
    op.drop_table("sd_assets")
    if bind.dialect.name == "postgresql":
        op.execute("DROP TYPE IF EXISTS assettype")
        op.execute("DROP TYPE IF EXISTS assetstatus")


def downgrade() -> None:
    """No se recrea el inventario duplicado: los datos ya viven en ALM."""
    op.drop_table("alm_asset_history")
    with op.batch_alter_table("alm_assets") as batch:
        batch.drop_constraint("fk_alm_assets_refresh_ticket", type_="foreignkey")
        batch.drop_constraint("fk_alm_assets_ci", type_="foreignkey")
        batch.drop_index("ix_alm_assets_ci_id")
        for c in COLUMNAS:
            batch.drop_column(c.name)
