"""Una sola CMDB: `sd_configuration_items`.

Auditoria 2026-11: habia dos. La pantalla CMDB y el descubrimiento escribian
en `cmdb_items`; los tickets, problemas, cambios, errores conocidos, la
monitorizacion y el analisis de impacto apuntaban a `sd_configuration_items`.
Lo que se descubria no se podia elegir en un ticket.

Manda `sd_configuration_items` (siete claves ajenas la usan). Esta migracion:

- le anade lo que solo tenia la otra: red, atributos, descubrimiento y deriva;
- anade al tipo de CI las clases que la otra admitia;
- copia `cmdb_items` conservando el id. Si ya habia un CI con el mismo nombre
  en la misma organizacion, se funde con el en vez de duplicarlo;
- copia las relaciones (`runs_on` A->B pasa a `hosts` B->A);
- repunta el historial de cambios y los agentes a la CMDB que queda;
- rellena la organizacion de los CIs que no la tenian, desde su responsable o
  su proyecto;
- borra `cmdb_relations`, `cmdb_items` y `cmdb_categories` (sin pantalla para
  crear categorias; 0 filas medidas).
"""
from __future__ import annotations

import uuid
from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "110_una_sola_cmdb"
down_revision: Union[str, None] = "109_preferencias_que_caben"
branch_labels = None
depends_on = None

TIPOS_NUEVOS = ("virtual_machine", "container", "cloud", "endpoint", "storage")
TIPOS = {"application", "server", "database", "network", "service", "module",
         "integration", "other", *TIPOS_NUEVOS}
ESTADOS = {"active": "operational", "maintenance": "maintenance",
           "decommissioned": "retired", "operational": "operational",
           "degraded": "degraded", "retired": "retired"}
RELACIONES = {"depends_on", "hosts", "connects_to", "backed_up_by", "monitored_by", "part_of"}

COLUMNAS = (
    sa.Column("ip_address", sa.String(45), nullable=True),
    sa.Column("hostname", sa.String(200), nullable=True),
    sa.Column("attributes", sa.Text, nullable=True),
    sa.Column("external_id", sa.String(255), nullable=True),
    sa.Column("discovery_provider", sa.String(50), nullable=True),
    sa.Column("discovery_provider_id", sa.String(36), nullable=True),
    sa.Column("last_discovered_at", sa.DateTime(timezone=True), nullable=True),
    sa.Column("is_discovered", sa.Boolean, nullable=False, server_default=sa.false()),
    sa.Column("config_hash", sa.String(64), nullable=True),
    sa.Column("drift_detected_at", sa.DateTime(timezone=True), nullable=True),
    sa.Column("baseline_attributes", sa.Text, nullable=True),
)


def _tiene(bind, tabla: str) -> bool:
    return sa.inspect(bind).has_table(tabla)


def _siguiente_codigo(bind) -> int:
    codigos = [c for (c,) in bind.execute(sa.text("SELECT code FROM sd_configuration_items"))]
    numeros = [int(c[3:]) for c in codigos if c and c.startswith("CI-") and c[3:].isdigit()]
    return max(numeros, default=0) + 1


def upgrade() -> None:
    bind = op.get_bind()
    pg = bind.dialect.name == "postgresql"

    if pg:
        with op.get_context().autocommit_block():
            for t in TIPOS_NUEVOS:
                op.execute(f"ALTER TYPE citype ADD VALUE IF NOT EXISTS '{t}'")

    with op.batch_alter_table("sd_configuration_items") as batch:
        for c in COLUMNAS:
            batch.add_column(c.copy())
        batch.create_index("ix_sd_configuration_items_external_id", ["external_id"])
        batch.create_foreign_key("fk_sd_ci_discovery_provider", "cmdb_discovery_providers",
                                 ["discovery_provider_id"], ["id"], ondelete="SET NULL")

    # La organizacion que faltaba: la del responsable, o la del proyecto.
    bind.execute(sa.text("""
        UPDATE sd_configuration_items SET organization_id =
          (SELECT u.organization_id FROM users u WHERE u.id = sd_configuration_items.owner_user_id)
        WHERE organization_id IS NULL AND owner_user_id IS NOT NULL"""))
    bind.execute(sa.text("""
        UPDATE sd_configuration_items SET organization_id =
          (SELECT p.organization_id FROM projects p WHERE p.id = sd_configuration_items.project_id)
        WHERE organization_id IS NULL AND project_id IS NOT NULL"""))
    # Sin responsable ni proyecto: la de los tickets que lo citan, si es una sola.
    bind.execute(sa.text("""
        UPDATE sd_configuration_items SET organization_id =
          (SELECT MIN(t.organization_id) FROM sd_tickets t WHERE t.ci_id = sd_configuration_items.id)
        WHERE organization_id IS NULL
          AND (SELECT COUNT(DISTINCT t.organization_id) FROM sd_tickets t
               WHERE t.ci_id = sd_configuration_items.id AND t.organization_id IS NOT NULL) = 1"""))
    # Y si la instalacion tiene una sola organizacion, no hay duda posible.
    organizaciones = [o for (o,) in bind.execute(sa.text("SELECT id FROM organizations"))]
    if len(organizaciones) == 1:
        bind.execute(sa.text("UPDATE sd_configuration_items SET organization_id = :o WHERE organization_id IS NULL"),
                     {"o": organizaciones[0]})
    bind.execute(sa.text("UPDATE sd_configuration_items SET environment = 'production' WHERE environment = 'prod'"))

    if not _tiene(bind, "cmdb_items"):
        return

    # ── Los CIs ──────────────────────────────────────────────────────────────
    equivalente: dict[str, str] = {}
    existentes = {
        ((org or ""), (nombre or "").strip().lower()): cid
        for cid, org, nombre in bind.execute(sa.text(
            "SELECT id, organization_id, name FROM sd_configuration_items"))
    }
    siguiente = _siguiente_codigo(bind)
    # Medido: en una base creada con alembic `cmdb_items` y `cmdb_relations`
    # no tienen `organization_id` (el modelo la declaraba; solo create_all la
    # creaba). Se lee si existe y, si no, la del responsable.
    def _org(tabla: str, alias: str = "") -> str:
        cols = {c["name"] for c in sa.inspect(bind).get_columns(tabla)}
        return f"{alias}organization_id" if "organization_id" in cols else "NULL"

    viejos = bind.execute(sa.text(f"""
        SELECT i.id, COALESCE({_org("cmdb_items", "i.")}, u.organization_id) AS organization_id,
               i.name, i.ci_type, i.is_active, i.status, i.environment, i.owner_id,
               i.description, i.attributes, i.ip_address, i.hostname, i.version, i.external_id,
               i.discovery_provider, i.last_discovered_at, i.is_discovered, i.config_hash,
               i.drift_detected_at, i.baseline_attributes, i.created_at
        FROM cmdb_items i LEFT JOIN users u ON u.id = i.owner_id""")).mappings().all()
    for v in viejos:
        datos = {
            "ip_address": v["ip_address"], "hostname": v["hostname"], "attributes": v["attributes"],
            "external_id": v["external_id"], "discovery_provider": v["discovery_provider"],
            "last_discovered_at": v["last_discovered_at"], "is_discovered": bool(v["is_discovered"]),
            "config_hash": v["config_hash"], "drift_detected_at": v["drift_detected_at"],
            "baseline_attributes": v["baseline_attributes"],
        }
        clave = ((v["organization_id"] or ""), (v["name"] or "").strip().lower())
        destino = existentes.get(clave)
        if destino:
            # Se funde: lo que la otra no tenia, sin pisar lo que ya habia.
            sets = ", ".join(f"{k} = COALESCE({k}, :{k})" for k in datos if k != "is_discovered")
            bind.execute(sa.text(
                f"UPDATE sd_configuration_items SET {sets}, is_discovered = is_discovered OR :is_discovered "
                "WHERE id = :id"), {**datos, "id": destino})
            equivalente[v["id"]] = destino
            continue
        tipo = (v["ci_type"] or "other").lower()
        bind.execute(sa.text("""
            INSERT INTO sd_configuration_items
              (id, organization_id, is_active, code, name, ci_type, status, description,
               owner_user_id, environment, version, criticality, created_at,
               ip_address, hostname, attributes, external_id, discovery_provider,
               last_discovered_at, is_discovered, config_hash, drift_detected_at, baseline_attributes)
            VALUES (:id, :org, :activo, :code, :name, :tipo, :estado, :descr, :owner, :env, :version,
               'medium', COALESCE(:creado, CURRENT_TIMESTAMP), :ip_address, :hostname, :attributes,
               :external_id, :discovery_provider, :last_discovered_at, :is_discovered,
               :config_hash, :drift_detected_at, :baseline_attributes)"""), {
            **datos, "id": v["id"], "org": v["organization_id"],
            "activo": v["is_active"] if v["is_active"] is not None else True,
            "code": f"CI-{siguiente:04d}", "name": v["name"],
            "tipo": tipo if tipo in TIPOS else "other",
            "estado": ESTADOS.get((v["status"] or "active").lower(), "operational"),
            "descr": v["description"], "owner": v["owner_id"],
            "env": "production" if v["environment"] == "prod" else v["environment"],
            "version": v["version"], "creado": v["created_at"],
        })
        siguiente += 1
        existentes[clave] = v["id"]
        equivalente[v["id"]] = v["id"]

    # ── Las relaciones ───────────────────────────────────────────────────────
    for r in bind.execute(sa.text(
            f"SELECT {_org('cmdb_relations')} AS organization_id, from_item_id, to_item_id, rel_type FROM cmdb_relations "
            "WHERE is_active IS NULL OR is_active = :si"), {"si": True}).mappings():
        origen, destino = equivalente.get(r["from_item_id"]), equivalente.get(r["to_item_id"])
        tipo = (r["rel_type"] or "depends_on").lower()
        if tipo == "runs_on":
            origen, destino, tipo = destino, origen, "hosts"
        if not origen or not destino or origen == destino:
            continue
        bind.execute(sa.text("""
            INSERT INTO sd_ci_relations (id, organization_id, source_ci_id, target_ci_id, relation_type)
            VALUES (:id, :org, :o, :d, :t)"""), {
            "id": str(uuid.uuid4()), "org": r["organization_id"], "o": origen, "d": destino,
            "t": tipo if tipo in RELACIONES else "depends_on"})

    # ── El historial y los agentes, a la CMDB que queda ──────────────────────
    # Primero se suelta la clave vieja: el id fundido no existe en `cmdb_items`.
    # SQLite no nombra las claves ajenas: el lote las refleja con este nombre.
    convencion = {"fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s"}
    claves = (
        ("cmdb_changelog", "item_id", "CASCADE", "fk_cmdb_changelog_ci"),
        ("cmdb_agent_registrations", "ci_id", "SET NULL", "fk_cmdb_agent_ci"),
    )
    for tabla, columna, _, _ in claves:
        vieja = f"{tabla}_{columna}_fkey" if pg else f"fk_{tabla}_{columna}_cmdb_items"
        with op.batch_alter_table(tabla, naming_convention=convencion) as batch:
            batch.drop_constraint(vieja, type_="foreignkey")
    for viejo, nuevo in equivalente.items():
        if viejo != nuevo:
            bind.execute(sa.text("UPDATE cmdb_changelog SET item_id = :n WHERE item_id = :v"), {"n": nuevo, "v": viejo})
            bind.execute(sa.text("UPDATE cmdb_agent_registrations SET ci_id = :n WHERE ci_id = :v"), {"n": nuevo, "v": viejo})
    for tabla, columna, borrar, nombre in claves:
        with op.batch_alter_table(tabla) as batch:
            batch.create_foreign_key(nombre, "sd_configuration_items", [columna], ["id"], ondelete=borrar)

    op.drop_table("cmdb_relations")
    op.drop_table("cmdb_items")
    op.drop_table("cmdb_categories")


def downgrade() -> None:
    """No se recrea la CMDB duplicada: los datos ya viven en una sola.

    Se quitan las columnas anadidas; los valores de `citype` se quedan
    (Postgres no permite quitar valores de un enum).
    """
    with op.batch_alter_table("sd_configuration_items") as batch:
        batch.drop_constraint("fk_sd_ci_discovery_provider", type_="foreignkey")
        batch.drop_index("ix_sd_configuration_items_external_id")
        for c in COLUMNAS:
            batch.drop_column(c.name)
