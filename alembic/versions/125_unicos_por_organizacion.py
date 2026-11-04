"""Unicidad por organizacion: codigos y nombres de negocio que cada empresa repite.

Revision multitenant 2026-11. Estos campos eran unicos en TODA la base. Con
mas de una organizacion, la segunda no podia tener su «PRJ-0001», su factura
«INV-2026-001», sus tipos de tarea («bug» ya existia: la pantalla de tipos
daba 500 al sembrarlos) ni su departamento «Ventas». Medido con una segunda
organizacion en una copia de la base.

Ademas, los campos dinamicos de cada ticket (`app_settings`) pasan a la
organizacion de su ticket: guardados como globales, salian en los ajustes
generales de todas las empresas.

Pasan a ser unicos por (organization_id, campo). Se mantienen globales, a
proposito: el correo y el usuario (identidad de acceso), tokens y digests,
credenciales, el slug de los webhooks entrantes (es la URL publica) y las
filas que ya son unicas dentro de su entidad padre.

En SQLite las restricciones sin nombre no se pueden quitar (como en la 120);
la base de produccion y la local son Postgres.
"""
from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "125_unicos_por_organizacion"
down_revision: Union[str, None] = "124_integraciones_reales"
branch_labels = None
depends_on = None

# tabla -> columnas que pasan a ser unicas por organizacion
_POR_ORGANIZACION = {
    "ai_governance_configs": ["module"],
    "alert_configs": ["alert_type"],
    "alm_assets": ["serial_number", "asset_tag"],
    "contracts": ["code"],
    "invoices": ["number"],
    "opportunities": ["code"],
    "projects": ["code"],
    "sd_change_requests": ["number"],
    "skills": ["name"],
    "task_types": ["value", "name"],
    "wiki_spaces": ["slug"],
    "work_orders": ["code"],
    "sem_embedding_cache": ["text_hash"],
}

# Los parciales «solo los activos» (2f165b37fe82): mismo criterio, por organizacion.
_PARCIALES = {
    "uq_project_status_value_active": ("custom_project_statuses", "value"),
    "uq_project_type_value_active": ("custom_project_types", "value"),
    "uq_task_status_value_active": ("custom_task_statuses", "value"),
    "uq_department_name_active": ("departments", "name"),
}


def _unicos_de(insp, tabla: str, columna: str) -> tuple[list[str], list[str]]:
    restr = [u["name"] for u in insp.get_unique_constraints(tabla)
             if u.get("column_names") == [columna] and u.get("name")]
    indices = [i["name"] for i in insp.get_indexes(tabla)
               if i.get("unique") and i.get("column_names") == [columna]
               and not i.get("duplicates_constraint") and i["name"] not in restr]
    return restr, indices


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    tablas = set(insp.get_table_names())

    for tabla, columnas in _POR_ORGANIZACION.items():
        if tabla not in tablas:
            continue
        existentes = {i["name"] for i in insp.get_indexes(tabla)}
        with op.batch_alter_table(tabla, recreate="auto") as batch:
            for columna in columnas:
                restr, indices = _unicos_de(insp, tabla, columna)
                for nombre in restr:
                    batch.drop_constraint(nombre, type_="unique")
                for nombre in indices:
                    batch.drop_index(nombre)
                    # `ix_<tabla>_<col>` era el indice unico del modelo
                    # (`unique=True, index=True`): queda como indice normal.
                    if nombre == f"ix_{tabla}_{columna}":
                        batch.create_index(nombre, [columna])
                nuevo = f"uq_{tabla}_org_{columna}"
                if nuevo not in existentes:
                    batch.create_index(nuevo, ["organization_id", columna], unique=True)

    for nombre, (tabla, columna) in _PARCIALES.items():
        if tabla not in tablas:
            continue
        op.execute(f"DROP INDEX IF EXISTS {nombre}")
        op.execute(
            f"CREATE UNIQUE INDEX IF NOT EXISTS {nombre} ON {tabla} "
            f"(organization_id, {columna}) WHERE is_active = true")

    # Los ajustes por ticket (campos dinamicos e instantanea de «en espera») se
    # guardaban como ajuste GLOBAL (organizacion vacia) y salian en los
    # ajustes generales de todas las empresas: pasan a la de su ticket.
    if {"app_settings", "sd_tickets"} <= tablas:
        for prefijo in ("sd.ticket.dynamic_fields.", "sd.ticket.pending_snapshot."):
            op.execute(sa.text(
                "UPDATE app_settings SET organization_id = (SELECT t.organization_id FROM sd_tickets t "
                "WHERE :p || t.id = app_settings.key) "
                "WHERE organization_id IS NULL AND substr(key, 1, length(:p)) = :p").bindparams(p=prefijo))


def downgrade() -> None:
    # Volver a la unicidad global fallaria en cuanto dos empresas repitan un
    # codigo: no se deshace.
    pass
