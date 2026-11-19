"""Tipos de proyecto, sectores de cliente y categorías de gasto editables por empresa (19-11-2026).

Auditoría de hardcodeados: `projects.project_type`, `clients.industry` y
`expenses.category` eran enums de BD cerrados (`projecttype`, `clientindustry`,
`expensecategory`). Desde aquí guardan la CLAVE (VARCHAR(50)) de su catálogo:

* `custom_project_types` (ya existía; se siembran los cinco tipos si está vacío);
* `custom_client_industries` (nueva) con los diez sectores de siempre;
* `custom_expense_categories` (nueva) con las ocho categorías de siempre.

Las filas sembradas son globales (`organization_id` NULL) y tienen las mismas
claves que el enum: los datos y el API existentes siguen valiendo tal cual.
Cada empresa añade las suyas desde Configuración
(`/settings/client-industries`, `/settings/expense-categories`, `/settings/project-types`).

Idempotente: tablas solo si faltan, semillas solo si el catálogo está vacío,
columnas solo si aún son enum. Downgrade: las claves propias de una empresa no
caben en el enum: pasan a `other` (sector, categoría) o `internal` (tipo).

Revision ID: 186_catalogos_de_tipo_sector_y_categoria
Revises: 185_ajustes_generales_una_fuente
"""
import uuid

import sqlalchemy as sa
from alembic import op

revision = "186_catalogos_de_tipo_sector_y_categoria"
down_revision = "185_ajustes_generales_una_fuente"
branch_labels = None
depends_on = None

TIPOS = (("development", "Desarrollo", "#00d4ff"), ("maintenance", "Mantenimiento", "#ffb800"),
         ("rd", "I+D", "#7c3aed"), ("internal", "Interno", "#7a8aaa"), ("consulting", "Consultoría", "#00e5a0"))
SECTORES = (("technology", "Tecnología", "#00d4ff"), ("finance", "Finanzas", "#00e5a0"),
            ("healthcare", "Salud", "#ec4899"), ("retail", "Comercio", "#ffb800"),
            ("manufacturing", "Industria", "#7c3aed"), ("education", "Educación", "#38bdf8"),
            ("consulting", "Consultoría", "#2dd4bf"), ("real_estate", "Inmobiliario", "#84cc16"),
            ("media", "Medios", "#f97316"), ("other", "Otro", "#7a8aaa"))
CATEGORIAS = (("travel", "Viajes", "#00d4ff"), ("accommodation", "Alojamiento", "#7c3aed"),
              ("meals", "Comidas", "#ffb800"), ("software", "Software", "#38bdf8"),
              ("hardware", "Hardware", "#2dd4bf"), ("training", "Formación", "#00e5a0"),
              ("subcontract", "Subcontratación", "#ec4899"), ("other", "Otro", "#7a8aaa"))

#: (tabla, columna, tipo enum en PG, nulo, valores, respaldo del downgrade)
COLUMNAS = (
    ("projects", "project_type", "projecttype", False, TIPOS, "internal"),
    ("clients", "industry", "clientindustry", True, SECTORES, "other"),
    ("expenses", "category", "expensecategory", False, CATEGORIAS, "other"),
)


def _tablas() -> set:
    return set(sa.inspect(op.get_bind()).get_table_names())


def _crear_catalogo(nombre: str) -> None:
    if nombre in _tablas():
        return
    op.create_table(
        nombre,
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("organization_id", sa.String(36), sa.ForeignKey("organizations.id", name=f"{nombre}_organization_id_fkey"), nullable=True),
        sa.Column("value", sa.String(50), nullable=False),
        sa.Column("label", sa.String(100), nullable=False),
        sa.Column("color", sa.String(20), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=True),
        sa.Column("sort_order", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
    )
    op.create_index(f"ix_{nombre}_organization_id", nombre, ["organization_id"])


def _sembrar(nombre: str, valores) -> None:
    bind = op.get_bind()
    if bind.execute(sa.text(f"SELECT 1 FROM {nombre}")).first() is not None:
        return
    for i, (value, label, color) in enumerate(valores):
        bind.execute(sa.text(
            f"INSERT INTO {nombre} (id, organization_id, value, label, color, is_active, sort_order) "
            "VALUES (:id, NULL, :v, :l, :c, :a, :o)"
        ), {"id": str(uuid.uuid4()), "v": value, "l": label, "c": color, "a": True, "o": i})


def _a_texto(tabla: str, columna: str, tipo_pg: str, nulo: bool) -> None:
    bind = op.get_bind()
    if tabla not in _tablas():
        return
    col = next((c for c in sa.inspect(bind).get_columns(tabla) if c["name"] == columna), None)
    if col is None:
        return
    if bind.dialect.name == "postgresql":
        if isinstance(col["type"], sa.Enum) or not isinstance(col["type"], sa.String):
            op.execute(f"ALTER TABLE {tabla} ALTER COLUMN {columna} DROP DEFAULT")
            op.execute(f"ALTER TABLE {tabla} ALTER COLUMN {columna} TYPE VARCHAR(50) USING {columna}::text")
            op.execute(f"DROP TYPE IF EXISTS {tipo_pg}")
    else:
        # SQLite: el enum ya es texto; se cambia el tipo declarado (y se quita un CHECK si lo hubiera).
        with op.batch_alter_table(tabla) as b:
            b.alter_column(columna, type_=sa.String(50), existing_nullable=nulo)


def upgrade() -> None:
    _crear_catalogo("custom_client_industries")
    _crear_catalogo("custom_expense_categories")
    if "custom_project_types" in _tablas():
        _sembrar("custom_project_types", TIPOS)
    _sembrar("custom_client_industries", SECTORES)
    _sembrar("custom_expense_categories", CATEGORIAS)
    for tabla, columna, tipo_pg, nulo, _, _ in COLUMNAS:
        _a_texto(tabla, columna, tipo_pg, nulo)


def downgrade() -> None:
    bind = op.get_bind()
    pg = bind.dialect.name == "postgresql"
    for tabla, columna, tipo_pg, nulo, valores, respaldo in COLUMNAS:
        if tabla not in _tablas():
            continue
        claves = tuple(v[0] for v in valores)
        lista = ", ".join(f"'{c}'" for c in claves)
        op.execute(f"UPDATE {tabla} SET {columna} = '{respaldo}' WHERE {columna} IS NOT NULL AND {columna} NOT IN ({lista})")
        if pg:
            op.execute(f"CREATE TYPE {tipo_pg} AS ENUM ({lista})")
            op.execute(f"ALTER TABLE {tabla} ALTER COLUMN {columna} TYPE {tipo_pg} USING {columna}::{tipo_pg}")
        else:
            with op.batch_alter_table(tabla) as b:
                b.alter_column(columna, type_=sa.Enum(*claves, name=tipo_pg), existing_nullable=nulo)
    for nombre in ("custom_expense_categories", "custom_client_industries"):
        if nombre in _tablas():
            op.drop_index(f"ix_{nombre}_organization_id", table_name=nombre)
            op.drop_table(nombre)
