"""Tres columnas que la auditoria dejo anotadas como decision de producto.

Auditoria 2026-09. Las tres salieron del detector `audit_model_attrs.py`: codigo
que nombraba atributos que el esquema no tenia. En agosto se arreglo el sintoma
—que era grave: los tres reventaban con `TypeError` en la primera linea util— y
se dejo escrito que **anadir la columna era decision de producto y no de aquel
arreglo**. Esta revision toma esas tres decisiones, y cada una lleva escrito el
criterio, porque un criterio escrito se puede discutir y uno implicito no.

`sd_tickets.requester_phone` (VARCHAR(32))
    El servicio de SMS entrantes construia el ticket con `requester_phone=...`
    detras de un `hasattr` que protegia el valor y no la palabra clave, asi que
    **abrir un ticket desde un SMS fallaba siempre**. El telefono se guardaba de
    rebote en `requester_name` y en la descripcion.

    Criterio: en un ticket abierto por SMS el telefono **es** la identidad de
    quien lo abre — sin el no hay a quien responder. Eso es un campo, no una
    nota. Nullable porque los tickets que entran por otros canales no lo tienen.
    32 caracteres dan para un E.164 con extension.

`imputations.work_type` (VARCHAR(50))
    La importacion de imputaciones desde CSV pasaba `work_type=...` y la columna
    no existia: **fallaba fila por fila**.

    Criterio: media aplicacion ya contaba con este campo —el catalogo de
    informes lo ofrece y `billing_reports_service` lo lee con un respaldo a
    «development»—, asi que no se esta inventando un concepto, se esta creando
    el sitio donde guardar uno que ya se usa. Nullable y **sin valor por defecto
    en la base**: quien no lo informe se queda sin tipo de trabajo, y el
    respaldo se queda donde hace falta, en el informe que lo lee, en vez de
    inventar un dato en la fila.

`sd_tickets.major_incident_id` (FK a `sd_major_incidents`, ON DELETE SET NULL)
    La comprobacion de cumplimiento «P1 sin incidencia mayor declarada» estaba
    escrita contra `MajorIncident.tickets`, una relacion que no existia, asi que
    quedo declarada **no evaluable**.

    Criterio, que es el unico de los tres con una decision de forma detras:
    **un ticket pertenece como mucho a UNA incidencia mayor**, y una incidencia
    mayor agrupa muchos tickets. Es el modelo de ITIL y es el conservador. Una
    tabla de union permitiria que dos incidencias mayores compartieran tickets,
    y eso hay que quererlo explicitamente — no heredarlo de haber elegido la
    estructura mas flexible por costumbre. Si manana hace falta, pasar de una FK
    a una tabla de union es una migracion; al reves se pierden datos.

    `ON DELETE SET NULL` y no `CASCADE`: borrar la declaracion de una incidencia
    mayor **no** puede llevarse por delante los tickets, que son el trabajo real
    y siguen existiendo por su cuenta.

## Idempotente

Las tres se anaden solo si la tabla existe y la columna no, asi que la revision
se puede aplicar sobre una base creada desde cero con `Base.metadata.create_all`
—que las lee del modelo— sin fallar.

## Downgrade

Quita las tres columnas. Es reversible sin perder nada que existiera antes de
esta revision: las columnas no estaban. Lo que se pierde es lo que se haya
escrito en ellas desde entonces, y eso queda dicho para que la decision sea
consciente.

Revision ID: 096_columnas_de_decision_de_producto
Revises: 095_user_sessions_backfill_organization
Create Date: 2026-09-15
"""
from alembic import op
import sqlalchemy as sa


revision = "096_columnas_de_decision_de_producto"
down_revision = "095_user_sessions_backfill_organization"
branch_labels = None
depends_on = None

#: (tabla, columna, tipo, ¿indexada?)
COLUMNAS = [
    ("sd_tickets", "requester_phone", sa.String(32), False),
    ("imputations", "work_type", sa.String(50), False),
    ("sd_tickets", "major_incident_id", sa.String(36), True),
]

FK = ("sd_tickets", "major_incident_id", "sd_major_incidents", "id",
      "fk_sd_tickets_major_incident")


def _inspector():
    return sa.inspect(op.get_bind())


def _existe_tabla(tabla: str) -> bool:
    return tabla in _inspector().get_table_names()


def _existe_columna(tabla: str, columna: str) -> bool:
    return columna in {c["name"] for c in _inspector().get_columns(tabla)}


def upgrade() -> None:
    for tabla, columna, tipo, indexada in COLUMNAS:
        if not _existe_tabla(tabla) or _existe_columna(tabla, columna):
            continue
        op.add_column(tabla, sa.Column(columna, tipo, nullable=True))
        if indexada:
            op.create_index(f"ix_{tabla}_{columna}", tabla, [columna])
        print(f"[096] {tabla}.{columna} anadida")

    # La clave foranea va aparte y con su propio guardado: SQLite no soporta
    # anadir una FK a una tabla existente (`ALTER TABLE ... ADD CONSTRAINT` no
    # existe), y ahi la integridad la sostiene el ORM. En PostgreSQL si se crea.
    tabla, columna, destino, destino_col, nombre = FK
    if (_existe_tabla(tabla) and _existe_tabla(destino)
            and _existe_columna(tabla, columna)
            and op.get_bind().dialect.name != "sqlite"):
        existentes = {fk.get("name") for fk in _inspector().get_foreign_keys(tabla)}
        if nombre not in existentes:
            op.create_foreign_key(
                nombre, tabla, destino, [columna], [destino_col],
                ondelete="SET NULL")
            print(f"[096] {nombre} creada")


def downgrade() -> None:
    tabla, columna, _destino, _dc, nombre = FK
    if _existe_tabla(tabla) and op.get_bind().dialect.name != "sqlite":
        existentes = {fk.get("name") for fk in _inspector().get_foreign_keys(tabla)}
        if nombre in existentes:
            op.drop_constraint(nombre, tabla, type_="foreignkey")

    for tabla, columna, _tipo, indexada in reversed(COLUMNAS):
        if not _existe_tabla(tabla) or not _existe_columna(tabla, columna):
            continue
        if indexada:
            indices = {i["name"] for i in _inspector().get_indexes(tabla)}
            if f"ix_{tabla}_{columna}" in indices:
                op.drop_index(f"ix_{tabla}_{columna}", table_name=tabla)
        op.drop_column(tabla, columna)
