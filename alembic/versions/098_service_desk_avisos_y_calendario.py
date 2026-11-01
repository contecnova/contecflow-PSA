"""Service Desk: bandeja de eventos de ticket, plantillas por papel y zona del SLA.

- `sd_ticket_events`: lo que le pasa a un ticket, escrito en la misma
  transaccion que el cambio y procesado despues (avisos, correo, webhooks,
  flujos). Antes ningun cambio de ticket avisaba a nadie.
- `email_templates.code`, `language`, `is_active`: las plantillas que el
  sistema busca por su papel («sd.created.requester»), por idioma, y que una
  organizacion puede apagar. El texto por defecto vive en el codigo; la fila
  solo existe si la organizacion lo personaliza.
- `sd_sla_policies.timezone`: la jornada de la politica se cuenta en su zona.
- El historial de tickets con los enums en su valor («resolved», no
  «TicketStatus.resolved»).
- Seis tipos de aviso nuevos en `notificationtype` (creado, actualizado, SLA
  en riesgo, SLA incumplido, escalado, aprobacion pedida).

Cada paso mira antes el estado real, como la 097.
"""
from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "098_service_desk_avisos_y_calendario"
down_revision: Union[str, None] = "097_paridad_postgres_con_los_modelos"
branch_labels = None
depends_on = None


def _columnas(conn, tabla: str) -> set[str]:
    insp = sa.inspect(conn)
    if tabla not in insp.get_table_names():
        return set()
    return {c["name"] for c in insp.get_columns(tabla)}


#: Tipos de aviso nuevos del Service Desk (enum `notificationtype`).
NUEVOS_TIPOS_DE_AVISO = (
    "ticket_created", "ticket_updated", "ticket_sla_warning",
    "ticket_sla_breached", "ticket_escalated", "approval_requested",
)


ENUMS_DEL_HISTORIAL = (
    "TicketStatus", "TicketPriority", "TicketUrgency", "TicketImpact",
    "TicketType", "SupportLevel", "SLAStatus",
)


def upgrade() -> None:
    conn = op.get_bind()
    insp = sa.inspect(conn)

    if conn.dialect.name == "postgresql":
        # ADD VALUE no se puede usar en la misma transaccion en que se crea.
        with op.get_context().autocommit_block():
            for valor in NUEVOS_TIPOS_DE_AVISO:
                op.execute(f"ALTER TYPE notificationtype ADD VALUE IF NOT EXISTS '{valor}'")

    if "sd_ticket_events" not in insp.get_table_names():
        op.create_table(
            "sd_ticket_events",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("organization_id", sa.String(36), sa.ForeignKey("organizations.id"), nullable=True),
            sa.Column("ticket_id", sa.String(36), sa.ForeignKey("sd_tickets.id", ondelete="CASCADE"), nullable=False),
            sa.Column("kind", sa.String(40), nullable=False),
            sa.Column("data", sa.Text(), nullable=True),
            sa.Column("actor_user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
            sa.Column("actor_client_id", sa.String(36), sa.ForeignKey("client_users.id", ondelete="SET NULL"), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("last_error", sa.String(500), nullable=True),
        )
        op.create_index("ix_sd_ticket_events_organization_id", "sd_ticket_events", ["organization_id"])
        op.create_index("ix_sd_ticket_events_ticket_id", "sd_ticket_events", ["ticket_id"])
        op.create_index("ix_sd_ticket_events_created_at", "sd_ticket_events", ["created_at"])
        op.create_index("ix_sd_ticket_events_processed_at", "sd_ticket_events", ["processed_at"])

    cols = _columnas(conn, "email_templates")
    if cols:
        with op.batch_alter_table("email_templates") as batch:
            if "code" not in cols:
                batch.add_column(sa.Column("code", sa.String(80), nullable=True))
            if "language" not in cols:
                batch.add_column(sa.Column("language", sa.String(10), nullable=True))
            if "is_active" not in cols:
                batch.add_column(sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()))
        if "ix_email_templates_code" not in {i["name"] for i in sa.inspect(conn).get_indexes("email_templates")}:
            op.create_index("ix_email_templates_code", "email_templates", ["code"])

    # El historial guardaba los enums como «TicketStatus.resolved»: se dejan
    # en su valor, que es lo que escribe ahora `log_history`.
    if "sd_ticket_history" in insp.get_table_names():
        for prefijo in ENUMS_DEL_HISTORIAL:
            for columna in ("old_value", "new_value"):  # nombres fijos, no entrada
                op.execute(sa.text(
                    f"UPDATE sd_ticket_history SET {columna} = SUBSTR({columna}, :desde) "  # noqa: S608
                    f"WHERE {columna} LIKE :patron"
                ).bindparams(desde=len(prefijo) + 2, patron=f"{prefijo}.%"))

    if "timezone" not in _columnas(conn, "sd_sla_policies"):
        with op.batch_alter_table("sd_sla_policies") as batch:
            batch.add_column(sa.Column("timezone", sa.String(64), nullable=True))


def downgrade() -> None:
    conn = op.get_bind()
    if "timezone" in _columnas(conn, "sd_sla_policies"):
        with op.batch_alter_table("sd_sla_policies") as batch:
            batch.drop_column("timezone")
    cols = _columnas(conn, "email_templates")
    if "code" in cols:
        op.drop_index("ix_email_templates_code", table_name="email_templates")
    with op.batch_alter_table("email_templates") as batch:
        for c in ("is_active", "language", "code"):
            if c in cols:
                batch.drop_column(c)
    if "sd_ticket_events" in sa.inspect(conn).get_table_names():
        op.drop_table("sd_ticket_events")
