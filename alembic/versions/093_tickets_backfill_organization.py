"""Rellena `organization_id` en los tickets y en las 17 tablas que cuelgan de ellos.

Auditoria 2026-08, misma clase de defecto que la 092 y con el alcance mas
grande de todas: **el Service Desk entero**.

El filtro de aislamiento de `TenantSession` es `organization_id = <org>`, asi
que una fila con NULL en esa columna **no la ve su propia organizacion**: solo
un superadmin. Medido con la clase de sesion real de la aplicacion:

    ticket con organization_id = NULL     usuario de ORG-A -> []   superadmin -> [el ticket]
    ticket con organization_id = 'ORG-A'  usuario de ORG-A -> [el ticket]

Y **ningun sitio de creacion de tickets pone la columna**: se comprobaron los
seis (`ai_modules/voice`, `collaboration/bots`, `integrations`,
`public_forms_service`, `service_desk/asset_service`,
`service_desk/inbound_email_service`) y ninguno la pasa. Uno de ellos lleva
ademas un comentario que afirma que `Ticket` **no tiene** esa columna, y si la
tiene — ese comentario es de cuando no la tenia y nadie lo reviso al anadirla.

## Por que las filas viejas si tienen organizacion y las nuevas no

La 076 hizo el relleno original, pero con una lista de nombres de tabla
adivinados: incluia `tickets`, y la tabla real se llama `sd_tickets`, asi que se
la salto. La 080 lo arreglo por introspeccion y relleno `sd_tickets` con la
organizacion por defecto. **Todo lo creado despues de la 080 quedo en NULL**, y
eso es todo el trafico normal de la aplicacion desde entonces.

El codigo ya no puede volver a crear un ticket sin organizacion: el escuchador
`before_flush` de `app/db/session.py` sella la organizacion de la sesion en las
filas nuevas. Esta revision arregla las que ya estan guardadas.

## De donde se hereda

Del creador si lo hay, y si no de la cadena de personas y de las entidades
padre, en este orden: quien lo creo, quien lo pidio, a quien esta asignado, su
proyecto, su cliente, y el usuario de portal que lo pidio. Se usa `COALESCE`
sobre subconsultas para que el orden se respete en una sola pasada, y funciona
igual en PostgreSQL y en SQLite.

**No se usa la organizacion por defecto como respaldo**, que es lo que hicieron
la 076 y la 080. En un despliegue con varios clientes eso le entregaria al
primero las filas de los demas. Un ticket sin ninguna de las seis referencias se
queda en NULL: no hay de donde deducirlo, e inventarlo seria peor.

## Downgrade

No-op deliberado. Volver a poner NULL solo puede hacer dano: no hay forma de
distinguir las filas que esta revision toco de las que ya tenian su
organizacion, y dejarlas en NULL las haria invisibles otra vez.

Revision ID: 093_tickets_backfill_organization
Revises: 092_performance_backfill_organization
Create Date: 2026-09-09
"""
from alembic import op
import sqlalchemy as sa


revision = "093_tickets_backfill_organization"
down_revision = "092_performance_backfill_organization"
branch_labels = None
depends_on = None


#: De donde hereda un ticket su organizacion, en orden de preferencia:
#: (columna del ticket, tabla referenciada).
ORIGENES_DEL_TICKET = [
    ("created_by_user_id", "users"),
    ("requester_user_id", "users"),
    ("assigned_to_user_id", "users"),
    ("project_id", "projects"),
    ("client_id", "clients"),
    ("requester_client_id", "client_users"),
]

#: Las tablas que cuelgan de un ticket por `ticket_id`. Su relleno va DESPUES
#: del de `sd_tickets`, asi que heredan un valor ya puesto.
#:
#: La lista se comprobo contra `Base.metadata`: son todas las tablas que tienen
#: a la vez `organization_id` y `ticket_id`.
HIJAS_DEL_TICKET = [
    "ai_ticket_triages",
    "documents",
    "sd_autonomous_playbook_executions",
    "sd_escalation_logs",
    "sd_incident_to_problem",
    "sd_jira_sync_log",
    "sd_jira_sync_map",
    "sd_known_error_tickets",
    "sd_routing_feedback",
    "sd_sla_events",
    "sd_status_incidents",
    "sd_ticket_comments",
    "sd_ticket_history",
    "sd_ticket_time_logs",
    "sd_ticket_watchers",
    "sla_breach_logs",
    "ticket_internal_comments",
]


def _existe(tabla: str) -> bool:
    inspector = sa.inspect(op.get_bind())
    return tabla in inspector.get_table_names()


def _columna(tabla: str, columna: str) -> bool:
    inspector = sa.inspect(op.get_bind())
    return columna in {c["name"] for c in inspector.get_columns(tabla)}


def upgrade() -> None:
    conexion = op.get_bind()

    # Las consultas se construyen en variables aparte y no dentro de
    # `sa.text(...)`: la supresion del linter tiene que quedar FUERA de la
    # cadena. Metida dentro se convertiria en texto SQL, y la almohadilla no es
    # un comentario SQL ni en PostgreSQL ni en SQLite.
    #
    # El S608 de ruff es un falso positivo: los nombres de tabla y de columna
    # salen de las dos listas de literales de arriba. No hay entrada de usuario,
    # y un `bindparam` no sirve para un identificador.

    if not _existe("sd_tickets"):
        return

    # 1. Los tickets, de su creador y de sus entidades padre.
    origenes = [
        (col, tabla) for col, tabla in ORIGENES_DEL_TICKET
        if _existe(tabla) and _columna("sd_tickets", col)
    ]
    if origenes:
        ramas = ",".join(
            f" (SELECT o.organization_id FROM {tabla} o"
            f"  WHERE o.id = sd_tickets.{col})"
            for col, tabla in origenes
        )
        consulta = (
            f"UPDATE sd_tickets SET organization_id = COALESCE({ramas})"  # noqa: S608
            " WHERE organization_id IS NULL"
        )
        conexion.execute(sa.text(consulta))

    # 2. Las hijas, de su ticket.
    for hija in HIJAS_DEL_TICKET:
        if not _existe(hija) or not _columna(hija, "ticket_id"):
            continue
        consulta = (
            f"UPDATE {hija} SET organization_id = ("  # noqa: S608
            " SELECT t.organization_id FROM sd_tickets t"
            f" WHERE t.id = {hija}.ticket_id)"
            " WHERE organization_id IS NULL AND ticket_id IS NOT NULL"
        )
        conexion.execute(sa.text(consulta))


def downgrade() -> None:
    """No-op deliberado: ver el docstring del modulo."""
    pass
