"""Service desk — mejoras de mercado (16-11-2026).

Tablas nuevas (modelos en `app/models/service_desk/mercado.py`):

- `sd_service_item_tasks`: tareas de ejecucion estructuradas de un servicio del
  catalogo (cola, persona, SLA propio y etapa). Se rellena con el JSON
  `sd_service_items.fulfillment_tasks`, que queda vacio.
- `sd_sla_rules`: SLA condicionales; `sd_ola_targets`: OLA por prioridad.
- `sd_ticket_lifecycles`, `sd_ticket_lifecycle_states`,
  `sd_ticket_lifecycle_transitions`: estados y ciclos de vida por tipo.
- `sd_channel_conversations`, `sd_channel_messages`: WhatsApp, chat en vivo y
  Slack con su ticket y el traspaso a un agente.
- `sd_ci_classes`: clases de CI de la empresa sobre una clase base.
- `sd_portal_assistant_actions`: lo que el asistente del portal propone y el
  cliente confirma.

Columnas nuevas:

- `sd_service_items.approval_mode` (single | engine) y `approval_workflow_id`.
- `sd_tickets.fulfillment_task_id` y `lifecycle_state`.
- `sd_configuration_items.ci_class`.
- `cmdb_discovery_providers.config_json` se cifra (llevaba credenciales en claro).
- `sd_autonomous_playbook_executions`: `mode`, `playbook_id`, `action`,
  `actions_json`, `decided_by_user_id`, `decided_at`.
- `sla_calendars.applies_to_all` y `sla_calendar_holidays.sla_policy_id`.

Datos:

- `sd_sla_holidays` desaparece: sus festivos pasan a un calendario SLA
  «Festivos generales» por empresa (`applies_to_all`), con la politica en el
  festivo cuando era de una politica. Asi cuentan exactamente igual que antes.
- El agente autonomo estrena modo (`SD_AUTONOMOUS_AGENT_MODE`, por defecto
  `suggest`). Las empresas que ya lo tenian encendido conservan lo que hacia
  (ejecutar): se les guarda `execute`.

Revision ID: 174_service_desk_mercado
Revises: 173_proyectos_planificador_y_hub
"""
import json
import uuid

import sqlalchemy as sa
from alembic import op

revision = "174_service_desk_mercado"
down_revision = "173_proyectos_planificador_y_hub"
branch_labels = None
depends_on = None

_NOMBRE_CALENDARIO_GENERAL = "Festivos generales"


def _tablas(con) -> set[str]:
    return set(sa.inspect(con).get_table_names())


def _columnas(con, tabla: str) -> set[str]:
    return {c["name"] for c in sa.inspect(con).get_columns(tabla)}


def _id() -> str:
    return str(uuid.uuid4())


def _org_fk():
    return sa.ForeignKey("organizations.id")


def _crear_tablas(tablas: set[str]) -> None:
    if "sd_service_item_tasks" not in tablas:
        op.create_table(
            "sd_service_item_tasks",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("organization_id", sa.String(36), _org_fk(), nullable=True),
            sa.Column("service_item_id", sa.String(36), sa.ForeignKey("sd_service_items.id", ondelete="CASCADE"), nullable=False),
            sa.Column("title", sa.String(300), nullable=False),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("group_id", sa.String(36), sa.ForeignKey("sd_agent_groups.id", ondelete="SET NULL"), nullable=True),
            sa.Column("assignee_user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
            sa.Column("sla_hours", sa.Float(), nullable=True),
            sa.Column("stage", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        )
        for col in ("organization_id", "service_item_id", "group_id", "assignee_user_id"):
            op.create_index(f"ix_sd_service_item_tasks_{col}", "sd_service_item_tasks", [col])

    if "sd_sla_rules" not in tablas:
        op.create_table(
            "sd_sla_rules",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("organization_id", sa.String(36), _org_fk(), nullable=True),
            sa.Column("name", sa.String(150), nullable=False),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default="1"),
            sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("service_item_id", sa.String(36), sa.ForeignKey("sd_service_items.id", ondelete="CASCADE"), nullable=True),
            sa.Column("ticket_type", sa.String(30), nullable=True),
            sa.Column("client_id", sa.String(36), sa.ForeignKey("clients.id", ondelete="CASCADE"), nullable=True),
            sa.Column("contract_id", sa.String(36), sa.ForeignKey("contracts.id", ondelete="CASCADE"), nullable=True),
            sa.Column("priority", sa.String(20), nullable=True),
            sa.Column("response_hours", sa.Float(), nullable=True),
            sa.Column("resolution_hours", sa.Float(), nullable=True),
            sa.Column("sla_policy_id", sa.String(36), sa.ForeignKey("sd_sla_policies.id", ondelete="SET NULL"), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        )
        for col in ("organization_id", "service_item_id", "client_id", "contract_id"):
            op.create_index(f"ix_sd_sla_rules_{col}", "sd_sla_rules", [col])

    if "sd_ola_targets" not in tablas:
        op.create_table(
            "sd_ola_targets",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("organization_id", sa.String(36), _org_fk(), nullable=True),
            sa.Column("group_id", sa.String(36), sa.ForeignKey("sd_agent_groups.id", ondelete="CASCADE"), nullable=False),
            sa.Column("priority", sa.String(20), nullable=False),
            sa.Column("hours", sa.Float(), nullable=False),
            sa.UniqueConstraint("group_id", "priority", name="uq_sd_ola_targets_group_priority"),
        )
        for col in ("organization_id", "group_id"):
            op.create_index(f"ix_sd_ola_targets_{col}", "sd_ola_targets", [col])

    if "sd_ticket_lifecycles" not in tablas:
        op.create_table(
            "sd_ticket_lifecycles",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("organization_id", sa.String(36), _org_fk(), nullable=True),
            sa.Column("ticket_type", sa.String(30), nullable=False),
            sa.Column("name", sa.String(150), nullable=False),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default="1"),
            sa.Column("restrict_transitions", sa.Boolean(), nullable=False, server_default="0"),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.UniqueConstraint("organization_id", "ticket_type", name="uq_sd_lifecycle_org_type"),
        )
        op.create_index("ix_sd_ticket_lifecycles_organization_id", "sd_ticket_lifecycles", ["organization_id"])

    if "sd_ticket_lifecycle_states" not in tablas:
        op.create_table(
            "sd_ticket_lifecycle_states",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("organization_id", sa.String(36), _org_fk(), nullable=True),
            sa.Column("lifecycle_id", sa.String(36), sa.ForeignKey("sd_ticket_lifecycles.id", ondelete="CASCADE"), nullable=False),
            sa.Column("key", sa.String(50), nullable=False),
            sa.Column("label", sa.String(100), nullable=False),
            sa.Column("base_status", sa.String(20), nullable=False),
            sa.Column("is_initial", sa.Boolean(), nullable=False, server_default="0"),
            sa.Column("color", sa.String(30), nullable=True),
            sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
            sa.UniqueConstraint("lifecycle_id", "key", name="uq_sd_lifecycle_state_key"),
        )
        for col in ("organization_id", "lifecycle_id"):
            op.create_index(f"ix_sd_ticket_lifecycle_states_{col}", "sd_ticket_lifecycle_states", [col])

    if "sd_ticket_lifecycle_transitions" not in tablas:
        op.create_table(
            "sd_ticket_lifecycle_transitions",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("organization_id", sa.String(36), _org_fk(), nullable=True),
            sa.Column("lifecycle_id", sa.String(36), sa.ForeignKey("sd_ticket_lifecycles.id", ondelete="CASCADE"), nullable=False),
            sa.Column("from_key", sa.String(50), nullable=False),
            sa.Column("to_key", sa.String(50), nullable=False),
            sa.UniqueConstraint("lifecycle_id", "from_key", "to_key", name="uq_sd_lifecycle_transition"),
        )
        for col in ("organization_id", "lifecycle_id"):
            op.create_index(f"ix_sd_ticket_lifecycle_transitions_{col}", "sd_ticket_lifecycle_transitions", [col])

    if "sd_channel_conversations" not in tablas:
        op.create_table(
            "sd_channel_conversations",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("organization_id", sa.String(36), _org_fk(), nullable=True),
            sa.Column("channel", sa.String(20), nullable=False),
            sa.Column("external_id", sa.String(255), nullable=True),
            sa.Column("ticket_id", sa.String(36), sa.ForeignKey("sd_tickets.id", ondelete="SET NULL"), nullable=True),
            sa.Column("client_user_id", sa.String(36), sa.ForeignKey("client_users.id", ondelete="SET NULL"), nullable=True),
            sa.Column("visitor_name", sa.String(255), nullable=True),
            sa.Column("language", sa.String(8), nullable=True),
            sa.Column("status", sa.String(20), nullable=False, server_default="bot"),
            sa.Column("assigned_user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
            sa.Column("last_message_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        )
        for col in ("organization_id", "channel", "external_id", "ticket_id", "client_user_id", "status", "assigned_user_id"):
            op.create_index(f"ix_sd_channel_conversations_{col}", "sd_channel_conversations", [col])

    if "sd_channel_messages" not in tablas:
        op.create_table(
            "sd_channel_messages",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("organization_id", sa.String(36), _org_fk(), nullable=True),
            sa.Column("conversation_id", sa.String(36), sa.ForeignKey("sd_channel_conversations.id", ondelete="CASCADE"), nullable=False),
            sa.Column("direction", sa.String(3), nullable=False),
            sa.Column("author_type", sa.String(10), nullable=False),
            sa.Column("author_user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
            sa.Column("body", sa.Text(), nullable=False),
            sa.Column("external_message_id", sa.String(255), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.UniqueConstraint("conversation_id", "external_message_id", name="uq_sd_channel_message_ext"),
        )
        for col in ("organization_id", "conversation_id", "created_at"):
            op.create_index(f"ix_sd_channel_messages_{col}", "sd_channel_messages", [col])

    if "sd_ci_classes" not in tablas:
        op.create_table(
            "sd_ci_classes",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("organization_id", sa.String(36), _org_fk(), nullable=True),
            sa.Column("key", sa.String(50), nullable=False),
            sa.Column("label", sa.String(100), nullable=False),
            sa.Column("base_type", sa.String(30), nullable=False),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default="1"),
            sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.UniqueConstraint("organization_id", "key", name="uq_sd_ci_class_org_key"),
        )
        op.create_index("ix_sd_ci_classes_organization_id", "sd_ci_classes", ["organization_id"])

    if "sd_portal_assistant_actions" not in tablas:
        op.create_table(
            "sd_portal_assistant_actions",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("organization_id", sa.String(36), _org_fk(), nullable=True),
            sa.Column("client_user_id", sa.String(36), sa.ForeignKey("client_users.id", ondelete="CASCADE"), nullable=False),
            sa.Column("action", sa.String(40), nullable=False),
            sa.Column("params_json", sa.Text(), nullable=True),
            sa.Column("status", sa.String(12), nullable=False, server_default="proposed"),
            sa.Column("result_json", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        )
        for col in ("organization_id", "client_user_id"):
            op.create_index(f"ix_sd_portal_assistant_actions_{col}", "sd_portal_assistant_actions", [col])


def _anadir_columnas(con, tablas: set[str]) -> None:
    if "sd_service_items" in tablas:
        cols = _columnas(con, "sd_service_items")
        with op.batch_alter_table("sd_service_items") as t:
            if "approval_mode" not in cols:
                t.add_column(sa.Column("approval_mode", sa.String(10), nullable=False, server_default="single"))
            if "approval_workflow_id" not in cols:
                t.add_column(sa.Column("approval_workflow_id", sa.String(36), nullable=True))
                t.create_foreign_key("fk_sd_service_items_approval_workflow_id", "approval_workflows",
                                     ["approval_workflow_id"], ["id"], ondelete="SET NULL")
    if "sd_tickets" in tablas:
        cols = _columnas(con, "sd_tickets")
        with op.batch_alter_table("sd_tickets") as t:
            if "fulfillment_task_id" not in cols:
                t.add_column(sa.Column("fulfillment_task_id", sa.String(36), nullable=True))
                t.create_foreign_key("fk_sd_tickets_fulfillment_task_id", "sd_service_item_tasks",
                                     ["fulfillment_task_id"], ["id"], ondelete="SET NULL")
                t.create_index("ix_sd_tickets_fulfillment_task_id", ["fulfillment_task_id"])
            if "lifecycle_state" not in cols:
                t.add_column(sa.Column("lifecycle_state", sa.String(50), nullable=True))
    if "sd_configuration_items" in tablas and "ci_class" not in _columnas(con, "sd_configuration_items"):
        with op.batch_alter_table("sd_configuration_items") as t:
            t.add_column(sa.Column("ci_class", sa.String(50), nullable=True))
            t.create_index("ix_sd_configuration_items_ci_class", ["ci_class"])
    if "sd_autonomous_playbook_executions" in tablas:
        cols = _columnas(con, "sd_autonomous_playbook_executions")
        with op.batch_alter_table("sd_autonomous_playbook_executions") as t:
            for nombre, tipo in (("mode", sa.String(10)), ("playbook_id", sa.String(64)), ("action", sa.String(30)),
                                 ("actions_json", sa.Text()), ("decided_at", sa.DateTime(timezone=True))):
                if nombre not in cols:
                    t.add_column(sa.Column(nombre, tipo, nullable=True))
            if "decided_by_user_id" not in cols:
                t.add_column(sa.Column("decided_by_user_id", sa.String(36), nullable=True))
                t.create_foreign_key("fk_sd_autonomous_exec_decided_by", "users",
                                     ["decided_by_user_id"], ["id"], ondelete="SET NULL")
    if "sla_calendars" in tablas and "applies_to_all" not in _columnas(con, "sla_calendars"):
        with op.batch_alter_table("sla_calendars") as t:
            t.add_column(sa.Column("applies_to_all", sa.Boolean(), nullable=False, server_default="0"))
    if "sla_calendar_holidays" in tablas and "sla_policy_id" not in _columnas(con, "sla_calendar_holidays"):
        with op.batch_alter_table("sla_calendar_holidays") as t:
            t.add_column(sa.Column("sla_policy_id", sa.String(36), nullable=True))
            t.create_foreign_key("fk_sla_calendar_holidays_sla_policy_id", "sd_sla_policies",
                                 ["sla_policy_id"], ["id"], ondelete="CASCADE")
            t.create_index("ix_sla_calendar_holidays_sla_policy_id", ["sla_policy_id"])


def _tareas_a_filas(con) -> None:
    """`sd_service_items.fulfillment_tasks` (JSON) -> `sd_service_item_tasks`."""
    filas = con.execute(sa.text(
        "SELECT id, organization_id, fulfillment_tasks FROM sd_service_items "
        "WHERE fulfillment_tasks IS NOT NULL AND fulfillment_tasks <> ''")).fetchall()
    tareas = sa.table("sd_service_item_tasks", sa.column("id"), sa.column("organization_id"),
                      sa.column("service_item_id"), sa.column("title"), sa.column("group_id"),
                      sa.column("stage"), sa.column("sort_order"))
    grupos = {r[0] for r in con.execute(sa.text("SELECT id FROM sd_agent_groups")).fetchall()}
    for item_id, org_id, crudo in filas:
        try:
            lista = json.loads(crudo)
        except (TypeError, ValueError):
            continue
        if not isinstance(lista, list):
            continue
        nuevas = []
        for i, t in enumerate(lista):
            if not isinstance(t, dict) or not str(t.get("title") or "").strip():
                continue
            grupo = t.get("group_id") if t.get("group_id") in grupos else None
            nuevas.append({"id": _id(), "organization_id": org_id, "service_item_id": item_id,
                           "title": str(t["title"]).strip()[:300], "group_id": grupo, "stage": 1, "sort_order": i})
        if nuevas:
            op.bulk_insert(tareas, nuevas)
        con.execute(sa.text("UPDATE sd_service_items SET fulfillment_tasks = NULL WHERE id = :i"), {"i": item_id})


def _festivos_a_calendarios(con) -> None:
    """`sd_sla_holidays` -> un calendario «Festivos generales» por empresa."""
    if "sd_sla_holidays" not in _tablas(con):
        return
    # `organization_id` de `sd_sla_holidays` lo añadía la 080 recorriendo
    # `Base.metadata`, y esta revisión retira el modelo: en una base nueva la
    # columna no existe. La empresa sale entonces de su política de SLA.
    inspector = sa.inspect(con)
    if "organization_id" in {c["name"] for c in inspector.get_columns("sd_sla_holidays")}:
        org = "organization_id"
    elif "organization_id" in {c["name"] for c in inspector.get_columns("sd_sla_policies")}:
        org = "(SELECT p.organization_id FROM sd_sla_policies p WHERE p.id = sd_sla_holidays.sla_policy_id)"
    else:
        org = "NULL"
    festivos = con.execute(sa.text(
        f"SELECT id, {org} AS organization_id, name, holiday_date, sla_policy_id FROM sd_sla_holidays")).fetchall()
    calendario_de: dict = {}
    calendarios = sa.table("sla_calendars", sa.column("id"), sa.column("organization_id"), sa.column("name"),
                           sa.column("timezone"), sa.column("work_start"), sa.column("work_end"),
                           sa.column("work_days"), sa.column("is_active"), sa.column("applies_to_all"))
    dias = sa.table("sla_calendar_holidays", sa.column("id"), sa.column("organization_id"),
                    sa.column("calendar_id"), sa.column("holiday_date"), sa.column("is_active"),
                    sa.column("name"), sa.column("sla_policy_id"))
    from app.core.config import settings as _settings
    for hid, org, nombre, fecha, politica in festivos:
        if org not in calendario_de:
            cal_id = _id()
            op.bulk_insert(calendarios, [{
                "id": cal_id, "organization_id": org, "name": _NOMBRE_CALENDARIO_GENERAL,
                "timezone": _settings.DEFAULT_TIMEZONE, "work_start": "09:00", "work_end": "18:00",
                "work_days": "1,2,3,4,5", "is_active": True, "applies_to_all": True}])
            calendario_de[org] = cal_id
        op.bulk_insert(dias, [{"id": hid, "organization_id": org, "calendar_id": calendario_de[org],
                               "holiday_date": fecha, "is_active": True, "name": (nombre or "")[:100] or None,
                               "sla_policy_id": politica}])
    op.drop_table("sd_sla_holidays")


def _modo_del_agente(con) -> None:
    """Las empresas con el agente encendido siguen ejecutando (antes no habia modo)."""
    if "app_settings" not in _tablas(con):
        return
    encendidas = con.execute(sa.text(
        "SELECT organization_id, value FROM app_settings WHERE key = 'SD_AUTONOMOUS_AGENT_ENABLED'")).fetchall()
    ajustes = sa.table("app_settings", sa.column("id"), sa.column("organization_id"), sa.column("key"),
                       sa.column("value"), sa.column("description"))
    ya = {r[0] for r in con.execute(sa.text(
        "SELECT organization_id FROM app_settings WHERE key = 'SD_AUTONOMOUS_AGENT_MODE'")).fetchall()}
    nuevas = [{"id": _id(), "organization_id": org, "key": "SD_AUTONOMOUS_AGENT_MODE", "value": "execute",
               "description": "Migracion 174: el agente ya ejecutaba"}
              for org, valor in encendidas
              if (valor or "").strip().lower() in {"1", "true", "yes", "on", "y"} and org not in ya]
    if nuevas:
        op.bulk_insert(ajustes, nuevas)


def _cifrar_configs_de_discovery(con, cifrar: bool) -> None:
    """La configuracion de los proveedores de discovery lleva credenciales: se cifra."""
    if "cmdb_discovery_providers" not in _tablas(con):
        return
    from app.core.encryption import decrypt_value, encrypt_value
    for pid, cfg in con.execute(sa.text("SELECT id, config_json FROM cmdb_discovery_providers "
                                        "WHERE config_json IS NOT NULL")).fetchall():
        en_claro = (cfg or "").lstrip().startswith("{")
        if cifrar and en_claro:
            nuevo = encrypt_value(cfg)
        elif not cifrar and not en_claro:
            nuevo = decrypt_value(cfg) or "{}"
        else:
            continue
        con.execute(sa.text("UPDATE cmdb_discovery_providers SET config_json = :c WHERE id = :i"),
                    {"c": nuevo, "i": pid})


def upgrade() -> None:
    con = op.get_bind()
    tablas = _tablas(con)
    _crear_tablas(tablas)
    _anadir_columnas(con, _tablas(con))
    if "sd_service_items" in tablas:
        _tareas_a_filas(con)
    _festivos_a_calendarios(con)
    _modo_del_agente(con)
    _cifrar_configs_de_discovery(con, True)


def downgrade() -> None:
    con = op.get_bind()
    _cifrar_configs_de_discovery(con, False)
    # Festivos: vuelven a `sd_sla_holidays` los de los calendarios generales.
    op.create_table(
        "sd_sla_holidays",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("organization_id", sa.String(36), sa.ForeignKey("organizations.id"), nullable=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("holiday_date", sa.String(10), nullable=False),
        sa.Column("country", sa.String(2), nullable=True),
        sa.Column("sla_policy_id", sa.String(36), sa.ForeignKey("sd_sla_policies.id", ondelete="CASCADE"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_sd_sla_holidays_organization_id", "sd_sla_holidays", ["organization_id"])
    op.create_index("ix_sd_sla_holidays_sla_policy_id", "sd_sla_holidays", ["sla_policy_id"])
    con.execute(sa.text(
        "INSERT INTO sd_sla_holidays (id, organization_id, name, holiday_date, sla_policy_id) "
        "SELECT h.id, h.organization_id, COALESCE(h.name, ''), h.holiday_date, h.sla_policy_id "
        "FROM sla_calendar_holidays h JOIN sla_calendars c ON c.id = h.calendar_id WHERE c.applies_to_all = :si"),
        {"si": True})
    con.execute(sa.text(
        "DELETE FROM sla_calendar_holidays WHERE calendar_id IN "
        "(SELECT id FROM sla_calendars WHERE applies_to_all = :si AND name = :n)"),
        {"si": True, "n": _NOMBRE_CALENDARIO_GENERAL})
    con.execute(sa.text("DELETE FROM sla_calendars WHERE applies_to_all = :si AND name = :n"),
                {"si": True, "n": _NOMBRE_CALENDARIO_GENERAL})

    # Tareas: vuelven al JSON del servicio.
    filas = con.execute(sa.text(
        "SELECT service_item_id, title, group_id FROM sd_service_item_tasks ORDER BY service_item_id, stage, sort_order"
    )).fetchall()
    por_item: dict = {}
    for item_id, titulo, grupo in filas:
        por_item.setdefault(item_id, []).append({"title": titulo, "group_id": grupo})
    for item_id, lista in por_item.items():
        con.execute(sa.text("UPDATE sd_service_items SET fulfillment_tasks = :j WHERE id = :i"),
                    {"j": json.dumps(lista), "i": item_id})
    con.execute(sa.text("DELETE FROM app_settings WHERE key IN "
                        "('SD_AUTONOMOUS_AGENT_MODE', 'SD_AUTONOMOUS_DISABLED_PLAYBOOKS')"))

    with op.batch_alter_table("sla_calendar_holidays") as t:
        t.drop_index("ix_sla_calendar_holidays_sla_policy_id")
        t.drop_constraint("fk_sla_calendar_holidays_sla_policy_id", type_="foreignkey")
        t.drop_column("sla_policy_id")
    with op.batch_alter_table("sla_calendars") as t:
        t.drop_column("applies_to_all")
    with op.batch_alter_table("sd_autonomous_playbook_executions") as t:
        t.drop_constraint("fk_sd_autonomous_exec_decided_by", type_="foreignkey")
        for nombre in ("decided_by_user_id", "decided_at", "actions_json", "action", "playbook_id", "mode"):
            t.drop_column(nombre)
    with op.batch_alter_table("sd_configuration_items") as t:
        t.drop_index("ix_sd_configuration_items_ci_class")
        t.drop_column("ci_class")
    with op.batch_alter_table("sd_tickets") as t:
        t.drop_index("ix_sd_tickets_fulfillment_task_id")
        t.drop_constraint("fk_sd_tickets_fulfillment_task_id", type_="foreignkey")
        t.drop_column("fulfillment_task_id")
        t.drop_column("lifecycle_state")
    with op.batch_alter_table("sd_service_items") as t:
        t.drop_constraint("fk_sd_service_items_approval_workflow_id", type_="foreignkey")
        t.drop_column("approval_workflow_id")
        t.drop_column("approval_mode")

    for tabla in ("sd_portal_assistant_actions", "sd_ci_classes", "sd_channel_messages", "sd_channel_conversations",
                  "sd_ticket_lifecycle_transitions", "sd_ticket_lifecycle_states", "sd_ticket_lifecycles",
                  "sd_ola_targets", "sd_sla_rules", "sd_service_item_tasks"):
        op.drop_table(tabla)
