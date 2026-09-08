"""Rellena organization_id en el modulo de desempeño, que nadie ponia.

Revision ID: 092_performance_backfill_organization
Revises: 091_rev_entries_unique_batch_period

Auditoria 2026-08 (hallazgo 22). Las **nueve** creaciones del modulo de
evaluaciones y planes de desarrollo guardaban la fila sin `organization_id`, y
esa es la columna por la que filtra la guarda de tenant de `TenantSession`
(`organization_id == org`). Una fila con NULL no la ve nadie salvo un
superadmin, asi que:

    - se creaba un ciclo y `GET /performance/cycles` devolvia CERO a su propio
      creador;
    - editar o borrar una pregunta daba 404;
    - un plan de desarrollo y sus objetivos desaparecian igual.

Medido con la sesion real de la aplicacion: ciclo creado -> 0 ciclos listados
para su organizacion, 1 para un superadmin. El modulo entero estaba muerto en un
despliegue con tenant, y no habia error en ningun log.

El codigo ya pone la organizacion (mismo commit). Esta revision arregla las
filas que ya estan guardadas, heredandola de su fila padre:

    review_questions      <- review_cycles
    performance_reviews   <- review_cycles
    review_360_campaigns  <- review_cycles
    dev_goals             <- development_plans

Y para las dos tablas sin padre —`review_cycles` y `development_plans`— se
hereda del usuario que las creo (`created_by`), que es el unico vinculo de
tenencia que la fila conserva. Si ese usuario ya no existe o no tiene
organizacion, la fila se queda como esta: inventarle una organizacion seria
peor que dejarla visible solo al superadmin, que es el estado de hoy.

Sin `downgrade` que borre datos: volver a poner NULL reintroduciria el defecto,
y no hay forma de saber cuales eran NULL antes. El `downgrade` es un no-op
declarado.
"""
from alembic import op
import sqlalchemy as sa

revision = "092_performance_backfill_organization"
down_revision = "091_rev_entries_unique_batch_period"
branch_labels = None
depends_on = None


#: (tabla hija, columna de enlace, tabla padre) — el padre siempre tiene ya su
#: organizacion, porque su propio relleno va antes en el orden de abajo.
DE_PADRE = [
    ("review_questions", "cycle_id", "review_cycles"),
    ("performance_reviews", "cycle_id", "review_cycles"),
    ("review_360_campaigns", "cycle_id", "review_cycles"),
    ("dev_goals", "plan_id", "development_plans"),
]

#: Tablas sin fila padre: se heredan del usuario que las creo.
DE_CREADOR = ["review_cycles", "development_plans"]


def _existe(tabla: str) -> bool:
    inspector = sa.inspect(op.get_bind())
    return tabla in inspector.get_table_names()


def upgrade() -> None:
    conexion = op.get_bind()

    # La consulta se construye en una variable aparte y no dentro de
    # `sa.text(...)`: la supresion del linter de abajo tiene que quedar FUERA de
    # la cadena.
    # Metido dentro se convertiria en texto SQL —y la almohadilla no es un
    # comentario SQL en Postgres ni en SQLite—, asi que la migracion reventaria
    # por esconder un aviso del linter.
    #
    # El S608 de ruff es un falso positivo aqui: los nombres de tabla y columna salen de
    # `DE_CREADOR` y `DE_PADRE`, listas de literales de este fichero. No hay
    # entrada de usuario, y un `bindparam` no sirve para un identificador.

    # 1. Las que no tienen padre, desde su creador. Va primero para que las
    #    hijas hereden un valor ya relleno.
    for tabla in DE_CREADOR:
        if not _existe(tabla):
            continue
        consulta = (
            f"UPDATE {tabla} SET organization_id = ("  # noqa: S608
            f" SELECT u.organization_id FROM users u WHERE u.id = {tabla}.created_by)"
            " WHERE organization_id IS NULL AND created_by IS NOT NULL"
        )
        conexion.execute(sa.text(consulta))

    # 2. Las hijas, desde su padre.
    for hija, enlace, padre in DE_PADRE:
        if not (_existe(hija) and _existe(padre)):
            continue
        consulta = (
            f"UPDATE {hija} SET organization_id = ("  # noqa: S608
            f" SELECT p.organization_id FROM {padre} p WHERE p.id = {hija}.{enlace})"
            f" WHERE organization_id IS NULL AND {enlace} IS NOT NULL"
        )
        conexion.execute(sa.text(consulta))


def downgrade() -> None:
    """No-op deliberado: ver el docstring del modulo."""
    pass
