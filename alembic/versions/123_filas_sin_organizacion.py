"""Filas sin organizacion: se asignan a la suya (y la decision del cliente sobre una factura).

Auditoria 2026-11. La siembra de demo, todo lo que creaba un superadmin y lo
que creaban algunos jobs quedaba con `organization_id` NULL (en una base de
demo medida: 225 imputaciones, hitos, entregables, tickets, KB, catalogo…).
El filtro de tenant esconde esas filas a todos los usuarios que no son
superadmin y al portal de cliente: el cliente veia 0 horas y 0 hitos.

Desde este cambio el sellado deriva la organizacion del proyecto o del usuario
(`db/session.py: _org_del_registro`) y la siembra la publica. Esta migracion
arregla lo que ya existe, en este orden:

1. por proyecto (`project_id` -> projects.organization_id);
2. por usuario (`user_id` -> users.organization_id);
3. por ticket (`ticket_id` -> sd_tickets.organization_id);
4. si la instalacion tiene UNA sola organizacion con datos (usuarios que no
   son superadmin), lo que queda NULL pasa a ella, salvo las tablas donde NULL
   significa «valor global del despliegue» (ajustes, proveedores de IA,
   catalogos globales) y las exentas del filtro;
5. un superadmin que vive en la organizacion «default» vacia (lo que deja el
   modo «clean») pasa a esa organizacion con datos.

Con varias organizaciones con datos, el paso 4 y el 5 no hacen nada: no hay
forma segura de saber de quien es una fila sin proyecto ni usuario.
"""
from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "123_filas_sin_organizacion"
down_revision: Union[str, None] = "122_sso_nombre_y_grupos"
branch_labels = None
depends_on = None

# NULL = global del despliegue (o catalogos de la plataforma): no se tocan.
# Los de `_tenant_filter_include_global` y `_tenant_exempt` en los modelos
# (medido el 04-11-2026), mas catalogos de plataforma que se leen sin filtro.
_GLOBALES = {
    "ai_providers", "app_settings", "custom_project_statuses", "custom_project_types",
    "custom_task_statuses", "integration_connectors", "settings_audit_log", "organizations",
    "exchange_rates", "grc_role_permissions", "sso_configs", "alembic_version",
}


def _tablas_con(insp, columna: str) -> list[str]:
    return [t for t in insp.get_table_names()
            if "organization_id" in {c["name"] for c in insp.get_columns(t)}
            and columna in {c["name"] for c in insp.get_columns(t)}]


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    tablas = set(insp.get_table_names())

    # Decision del cliente sobre la factura en el portal (no se guardaba).
    if "invoices" in tablas and "client_approval_status" not in {c["name"] for c in insp.get_columns("invoices")}:
        with op.batch_alter_table("invoices") as batch:
            batch.add_column(sa.Column("client_approval_status", sa.String(20), nullable=True))

    def por(columna: str, origen: str) -> None:
        if origen not in tablas:
            return
        for t in _tablas_con(insp, columna):
            if t in _GLOBALES or t == origen:
                continue
            bind.execute(sa.text(
                f'UPDATE "{t}" SET organization_id = (SELECT o.organization_id FROM "{origen}" o '
                f'WHERE o.id = "{t}".{columna}) WHERE organization_id IS NULL AND {columna} IS NOT NULL'))

    por("project_id", "projects")
    por("user_id", "users")
    por("ticket_id", "sd_tickets")

    if "users" not in tablas or "organizations" not in tablas:
        return
    con_datos = [r[0] for r in bind.execute(sa.text(
        "SELECT DISTINCT organization_id FROM users WHERE organization_id IS NOT NULL "
        "AND (is_superadmin IS NULL OR is_superadmin = :f)"), {"f": False})]
    if len(con_datos) != 1:
        return
    unica = con_datos[0]
    for t in sorted(tablas):
        if t in _GLOBALES:
            continue
        if "organization_id" not in {c["name"] for c in insp.get_columns(t)}:
            continue
        bind.execute(sa.text(f'UPDATE "{t}" SET organization_id = :o WHERE organization_id IS NULL'), {"o": unica})

    bind.execute(sa.text(
        "UPDATE users SET organization_id = :o WHERE is_superadmin = :v AND organization_id IN ("
        "  SELECT g.id FROM organizations g WHERE g.slug = 'default'"
        "  AND NOT EXISTS (SELECT 1 FROM projects p WHERE p.organization_id = g.id))"), {"o": unica, "v": True})


def downgrade() -> None:
    # Las organizaciones asignadas no se deshacen: no se sabe cuales eran NULL.
    cols = {c["name"] for c in sa.inspect(op.get_bind()).get_columns("invoices")}
    if "client_approval_status" in cols:
        with op.batch_alter_table("invoices") as batch:
            batch.drop_column("client_approval_status")
