"""Tres columnas que el codigo leia y el esquema no tenia.

Auditoria 2026-08 (hallazgo 22). Salieron de `scripts/audit_model_attrs.py`, un
detector que recorre `app/` por AST y comprueba con `hasattr` sobre la clase
mapeada de verdad que cada `Modelo.atributo` exista. De 43 candidatos, tres eran
columnas que **hacen falta** —no nombres equivocados— y cada una rompia una
funcion completa:

`deliverables.billing_pct` (FLOAT)
    La plantilla de proyecto declara `template_deliverables.billing_pct` y
    `advanced_config_service` lo pasaba al construir el entregable. La columna no
    existia, y SQLAlchemy responde `TypeError` a una palabra clave que no es
    columna: **aplicar una plantilla de proyecto fallaba** en cuanto la plantilla
    traia un entregable. Se anade la columna en vez de tirar el dato: la
    plantilla lo declara porque el dato existe en el dominio.

`opportunities.external_id` (VARCHAR(255), indexada)
    `salesforce_service.find_opportunity_by_external_id` empezaba con
    `if not hasattr(Opportunity, "external_id"): return None`. Un `hasattr`
    **correcto** sobre una columna ausente, asi que la funcion devolvia
    **siempre None** y la sincronizacion con Salesforce no reconocia nunca una
    oportunidad ya importada: **duplicaba todas en cada pasada**.

`revenue_recognition_rules.is_active` (BOOLEAN NOT NULL, por defecto true)
    `auto_compute_revenue` filtra por `is_active == True` y la columna no
    existia, asi que el calculo automatico de reconocimiento de ingresos
    reventaba con `AttributeError`. Se anade con relleno a `true`, que es lo que
    significa una regla que hoy esta en la tabla.

## Idempotente

Las tres se anaden solo si la tabla existe y la columna no. Asi la revision se
puede aplicar sobre una base que ya las tenga —por ejemplo una creada desde cero
con `Base.metadata.create_all`, que las lee del modelo— sin fallar.

## Downgrade

Quita las tres columnas. A diferencia de los rellenos de las revisiones 092 y
093, aqui el `downgrade` **si** es reversible sin perder informacion que
existiera antes: estas columnas no existian, asi que lo unico que se pierde es
lo que se haya escrito desde que se aplico esta revision. Queda dicho para que
la decision sea consciente.

Revision ID: 094_columnas_que_el_codigo_leia_sin_existir
Revises: 093_tickets_backfill_organization
Create Date: 2026-09-09
"""
from alembic import op
import sqlalchemy as sa


revision = "094_columnas_que_el_codigo_leia_sin_existir"
down_revision = "093_tickets_backfill_organization"
branch_labels = None
depends_on = None


#: (tabla, columna, tipo, ¿nulable?, valor de relleno)
COLUMNAS = [
    ("deliverables", "billing_pct", sa.Float(), True, None),
    ("opportunities", "external_id", sa.String(255), True, None),
    ("revenue_recognition_rules", "is_active", sa.Boolean(), False, True),
]

#: Las que llevan indice, y con que nombre.
INDICES = [
    ("opportunities", "external_id", "ix_opportunities_external_id"),
    ("revenue_recognition_rules", "is_active",
     "ix_revenue_recognition_rules_is_active"),
]


def _inspector():
    return sa.inspect(op.get_bind())


def _existe_tabla(tabla: str) -> bool:
    return tabla in _inspector().get_table_names()


def _existe_columna(tabla: str, columna: str) -> bool:
    return columna in {c["name"] for c in _inspector().get_columns(tabla)}


def _existe_indice(tabla: str, nombre: str) -> bool:
    return nombre in {i["name"] for i in _inspector().get_indexes(tabla)}


def upgrade() -> None:
    conexion = op.get_bind()

    for tabla, columna, tipo, nulable, relleno in COLUMNAS:
        if not _existe_tabla(tabla) or _existe_columna(tabla, columna):
            continue

        # Se anade nulable siempre: una columna NOT NULL sin `server_default`
        # no se puede anadir a una tabla con filas. Se rellena y despues se
        # endurece.
        with op.batch_alter_table(tabla) as lote:
            lote.add_column(sa.Column(columna, tipo, nullable=True))

        if relleno is not None:
            # El S608 de ruff es un falso positivo: el nombre de tabla y de
            # columna salen de la lista de literales de arriba, y el valor va
            # como parametro ligado.
            consulta = (
                f"UPDATE {tabla} SET {columna} = :valor "  # noqa: S608
                f"WHERE {columna} IS NULL"
            )
            conexion.execute(sa.text(consulta), {"valor": relleno})

        if not nulable:
            with op.batch_alter_table(tabla) as lote:
                lote.alter_column(columna, existing_type=tipo, nullable=False)

    for tabla, columna, nombre in INDICES:
        if not _existe_tabla(tabla) or not _existe_columna(tabla, columna):
            continue
        if _existe_indice(tabla, nombre):
            continue
        op.create_index(nombre, tabla, [columna])


def downgrade() -> None:
    for tabla, _columna, nombre in INDICES:
        if _existe_tabla(tabla) and _existe_indice(tabla, nombre):
            op.drop_index(nombre, table_name=tabla)

    for tabla, columna, _tipo, _nulable, _relleno in COLUMNAS:
        if _existe_tabla(tabla) and _existe_columna(tabla, columna):
            with op.batch_alter_table(tabla) as lote:
                lote.drop_column(columna)
