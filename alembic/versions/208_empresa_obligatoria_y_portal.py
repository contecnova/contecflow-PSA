"""`organization_id` obligatorio y correo del portal único por empresa (24-11-2026).

Docs: docs/seguridad/empresa_obligatoria.md y README §«Multiempresa» / §«Portal de clientes».

1. **Correo del portal único POR EMPRESA.** `client_users.email` era único en toda
   la base y comparando tal cual (`ix_client_users_email`, único). Pasa a:
   `ix_client_users_email` sin unicidad y `uq_client_users_org_email`, único en
   (`organization_id`, `lower(email)`). Antes de crearlo se buscan duplicados
   dentro de una misma empresa (sin distinguir mayúsculas): si los hay **no se
   borra nada**; la migración los lista (correo enmascarado) y para.
2. **`organization_id` NOT NULL** en todas las tablas que lo tienen, salvo las
   exceptuadas (`EXCEPTUADAS`, copia congelada de
   `app/db/empresa_obligatoria.TABLAS_SIN_EMPRESA_PERMITIDA`, con su motivo allí;
   `tests/test_empresa_obligatoria.py` comprueba que casan). Medido en la 207:
   558 tablas con la columna, 484 nulables, 21 exceptuadas → 463 pasan a NOT NULL.
3. **Relleno de los NULL** antes de poner NOT NULL, por este orden:
   a) la empresa del padre por cada clave ajena a una tabla con empresa
      (proyecto, ticket y usuario primero; varias pasadas, porque el padre
      también puede estar rellenándose); sin clave ajena declarada,
      `project_id`→`projects`, `ticket_id`→`sd_tickets`, `user_id`/`created_by`→`users`;
   b) lo que quede: la empresa indicada en la variable de entorno
      `EMPRESA_PARA_FILAS_SIN_EMPRESA` (id de una empresa que exista) o, sin
      ella, la empresa única si solo hay una, o la única que tiene usuarios;
   c) si aún queda algo y hay varias empresas: informa (tabla y filas, y las
      empresas candidatas) y **para** sin tocar nada.

Compatible con SQLite y Postgres. En Postgres, `ALTER COLUMN ... SET/DROP NOT NULL`.
En SQLite, la reconstrucción de 12 pasos de la documentación de SQLite (tabla
nueva con el mismo `CREATE TABLE` salvo la restricción, copia, borrado,
renombrado y los mismos índices y disparadores con su SQL exacto): conserva
índices de expresión y parciales, que `batch_alter_table` reflejaría mal. Exige
`PRAGMA foreign_keys=OFF` (lo está en la conexión de Alembic: `alembic/env.py`
no lo enciende) para que borrar la tabla vieja no dispare los `ON DELETE CASCADE`.

Las migraciones corren con el rol dueño: la RLS de Postgres no las filtra.
`env.py` rehace las políticas al terminar.

Deshacer real: vuelve a nulable `organization_id` en las tablas que no eran ya
NOT NULL en la 207 (`YA_OBLIGATORIAS_EN_207`); los valores rellenados se quedan
(también son válidos en la 207). Quita `uq_client_users_org_email` y rehace
`ix_client_users_email` único; si el mismo correo exacto está ya en dos empresas,
lo informa y para sin borrar nada.

Revision ID: 208_empresa_obligatoria_y_portal
Revises: 207_conectores_y_semantico
"""
import logging
import os
import re

import sqlalchemy as sa
from alembic import op

revision = "208_empresa_obligatoria_y_portal"
down_revision = "207_conectores_y_semantico"
branch_labels = None
depends_on = None

logger = logging.getLogger("alembic.208")

COL = "organization_id"
USUARIOS_PORTAL = "client_users"
IX_EMAIL = "ix_client_users_email"
UQ_EMAIL = "uq_client_users_org_email"
VARIABLE_EMPRESA = "EMPRESA_PARA_FILAS_SIN_EMPRESA"

#: Copia congelada de `TABLAS_SIN_EMPRESA_PERMITIDA` (motivos en `app/db/empresa_obligatoria.py`).
EXCEPTUADAS = frozenset({
    "app_settings", "settings_audit_log",
    "custom_project_types", "custom_project_statuses", "custom_task_statuses", "custom_client_industries",
    "custom_expense_categories", "custom_supplier_service_types", "custom_supplier_billing_units",
    "ai_providers", "grc_role_permissions", "exchange_rates", "integration_connectors",
    "integration_credentials", "sso_configs", "alert_configs", "sla_calendars", "country_employer_costs",
    "bpmn_processes", "cmdb_discovery_providers", "audit_logs",
})

#: Tablas con `organization_id` ya NOT NULL en la 207 (el deshacer no las afloja).
YA_OBLIGATORIAS_EN_207 = frozenset({
    "abac_attribute_definitions", "abac_policies", "access_review_campaigns", "access_review_items",
    "ai_guardrail_audit_logs", "ai_guardrail_policies", "audit_log_purge_permits",
    "collaboration_attachment_versions", "collaboration_attachments", "collaboration_audit_events",
    "collaboration_bot_apps", "collaboration_bot_executions", "collaboration_call_participants",
    "collaboration_calls", "collaboration_channel_members", "collaboration_channels",
    "collaboration_conversation_members", "collaboration_conversations", "collaboration_direct_conversations",
    "collaboration_drafts", "collaboration_group_conversations", "collaboration_integrations",
    "collaboration_legal_holds", "collaboration_mentions", "collaboration_message_versions",
    "collaboration_messages", "collaboration_moderation_cases", "collaboration_notification_rules",
    "collaboration_notifications", "collaboration_pinned_messages", "collaboration_presence_states",
    "collaboration_push_subscriptions", "collaboration_reactions", "collaboration_reads",
    "collaboration_recordings", "collaboration_retention_policies", "collaboration_saved_messages",
    "collaboration_saved_searches", "collaboration_slash_command_logs", "collaboration_team_members",
    "collaboration_teams", "collaboration_threads", "collaboration_transcripts", "collaboration_webhooks",
    "collaboration_workspaces", "compliance_evidence", "integration_instances", "login_anomalies", "ml_models",
    "ml_prediction_logs", "org_brandings", "policy_audit_log", "portal_conversation_audits",
    "portal_conversation_messages", "portal_conversation_policies", "portal_conversations",
    "proposal_templates", "rev_contracts", "rev_entries", "rev_obligations", "rev_period_closes",
    "sd_dynamic_form_rule_history", "sd_dynamic_form_rules", "sd_ticket_hold_snapshots", "sd_voice_sessions",
    "security_change_requests", "security_detections", "security_events", "security_incidents",
    "security_metric_snapshots", "tenant_policy_packs", "user_attributes", "user_organization_memberships",
    "users",
})

#: Columna de enlace -> tabla padre, cuando la clave ajena no está declarada.
ENLACES_POR_NOMBRE = (("project_id", "projects"), ("ticket_id", "sd_tickets"),
                      ("user_id", "users"), ("created_by", "users"))
PRIORIDAD = ("project_id", "ticket_id", "user_id")
PASADAS = 6


class MigracionParada(RuntimeError):
    """La 208 no puede seguir sin decisión humana; no ha cambiado nada."""


# ── Utilidades ────────────────────────────────────────────────────────────────

def _q(conn, nombre: str) -> str:
    return conn.dialect.identifier_preparer.quote(nombre)


def _columnas(insp, tabla: str) -> dict:
    return {c["name"]: c for c in insp.get_columns(tabla)}


def tablas_con_empresa(conn) -> dict:
    """{tabla: nulable} de las tablas con `organization_id`."""
    insp = sa.inspect(conn)
    salida = {}
    for t in insp.get_table_names():
        cols = _columnas(insp, t)
        if COL in cols:
            salida[t] = bool(cols[COL]["nullable"])
    return salida


def _enmascarar(correo: str) -> str:
    usuario, _, dominio = (correo or "").partition("@")
    return f"{usuario[:1]}***@{dominio}" if dominio else "***"


# ── 1. Duplicados de correo del portal ───────────────────────────────────────

def duplicados_del_portal(conn) -> list:
    """[(empresa, correo en minúsculas, filas)] con el mismo correo dos veces en una empresa."""
    if USUARIOS_PORTAL not in sa.inspect(conn).get_table_names():
        return []
    return [tuple(r) for r in conn.execute(sa.text(
        f"SELECT {COL}, lower(email) AS correo, count(*) AS n FROM {USUARIOS_PORTAL} "
        f"GROUP BY {COL}, lower(email) HAVING count(*) > 1 ORDER BY 1, 2")).fetchall()]


def _exigir_sin_duplicados(conn) -> None:
    dup = duplicados_del_portal(conn)
    if not dup:
        return
    lineas = [f"  - empresa {org or '(sin empresa)'}: {_enmascarar(correo)} ({n} usuarios)" for org, correo, n in dup]
    raise MigracionParada(
        "208: hay usuarios del portal con el MISMO correo (sin distinguir mayúsculas) dentro de una misma "
        "empresa, y el correo pasa a ser único por empresa. No se ha borrado ni cambiado nada.\n"
        + "\n".join(lineas)
        + "\nResuélvelo en Portal > Usuarios (cambia el correo, o archiva/elimina el sobrante) y vuelve a "
          "ejecutar la migración.")


# ── 2. Relleno de los NULL ───────────────────────────────────────────────────

def enlaces(conn, tabla: str, con_empresa: dict) -> list:
    """[(columna, tabla padre, columna padre)] por los que se puede deducir la empresa, por prioridad."""
    insp = sa.inspect(conn)
    salida, vistos = [], set()
    for fk in insp.get_foreign_keys(tabla):
        cols, ref, ref_cols = fk.get("constrained_columns") or [], fk.get("referred_table"), fk.get("referred_columns") or []
        if len(cols) != 1 or len(ref_cols) != 1 or cols[0] == COL or ref not in con_empresa:
            continue
        if cols[0] not in vistos:
            salida.append((cols[0], ref, ref_cols[0]))
            vistos.add(cols[0])
    propias = _columnas(insp, tabla)
    for col, ref in ENLACES_POR_NOMBRE:
        if col in propias and col not in vistos and ref in con_empresa and ref != tabla:
            salida.append((col, ref, "id"))
            vistos.add(col)
    orden = {n: i for i, n in enumerate(PRIORIDAD)}
    salida.sort(key=lambda e: (orden.get(e[0], len(orden)), e[0]))
    return salida


def _nulos(conn, tabla: str) -> int:
    return int(conn.execute(sa.text(f"SELECT count(*) FROM {_q(conn, tabla)} WHERE {COL} IS NULL")).scalar() or 0)


def _empresa_de_respaldo(conn) -> tuple:
    """(id, cómo) de la empresa para lo no deducible, o (None, motivo)."""
    elegida = (os.environ.get(VARIABLE_EMPRESA) or "").strip()
    if elegida:
        existe = conn.execute(sa.text("SELECT id FROM organizations WHERE id = :i"), {"i": elegida}).first()
        if not existe:
            raise MigracionParada(f"208: {VARIABLE_EMPRESA}={elegida} no es el id de ninguna empresa.")
        return elegida, f"{VARIABLE_EMPRESA}"
    ids = [r[0] for r in conn.execute(sa.text("SELECT id FROM organizations")).fetchall()]
    if len(ids) == 1:
        return ids[0], "empresa única"
    # 24-11-2026: si solo UNA empresa tiene usuarios, las demás son marcadores
    # vacíos (p. ej. «Default Organization» de la instalación) y lo huérfano
    # —siembra antigua sin empresa— es de la única que trabaja. Así setup no se
    # para en una instalación normal; con varias empresas con usuarios, para.
    con_usuarios = [r[0] for r in conn.execute(sa.text(
        "SELECT o.id FROM organizations o WHERE EXISTS (SELECT 1 FROM users u WHERE u.organization_id = o.id)")).fetchall()]
    if len(con_usuarios) == 1:
        return con_usuarios[0], "única empresa con usuarios"
    return None, f"{len(ids)} empresas ({len(con_usuarios)} con usuarios)"


def rellenar(conn, objetivo: list) -> dict:
    """Rellena `organization_id` en `objetivo`. Devuelve {tabla: {"deducidas": n, "respaldo": n}}."""
    con_empresa = tablas_con_empresa(conn)
    cuenta = {t: {"deducidas": 0, "respaldo": 0} for t in objetivo}
    pendientes = {t for t in objetivo if _nulos(conn, t)}
    enlaces_de = {t: enlaces(conn, t, con_empresa) for t in pendientes}
    for _ in range(PASADAS):
        cambio = False
        for t in sorted(pendientes):
            for col, ref, ref_col in enlaces_de[t]:
                qt, qr = _q(conn, t), _q(conn, ref)
                r = conn.execute(sa.text(
                    f"UPDATE {qt} SET {COL} = (SELECT p.{COL} FROM {qr} p WHERE p.{_q(conn, ref_col)} = {qt}.{_q(conn, col)}) "
                    f"WHERE {COL} IS NULL AND {_q(conn, col)} IS NOT NULL AND EXISTS "
                    f"(SELECT 1 FROM {qr} p WHERE p.{_q(conn, ref_col)} = {qt}.{_q(conn, col)} AND p.{COL} IS NOT NULL)"))
                if r.rowcount and r.rowcount > 0:
                    cuenta[t]["deducidas"] += r.rowcount
                    cambio = True
        pendientes = {t for t in pendientes if _nulos(conn, t)}
        if not cambio or not pendientes:
            break
    if not pendientes:
        return cuenta
    quedan = {t: _nulos(conn, t) for t in sorted(pendientes)}
    empresa, como = _empresa_de_respaldo(conn)
    if empresa is None:
        orgs = conn.execute(sa.text(
            "SELECT o.id, o.name, (SELECT count(*) FROM users u WHERE u.organization_id = o.id) "
            "FROM organizations o ORDER BY o.name")).fetchall()
        raise MigracionParada(
            f"208: quedan filas sin empresa que no se pueden deducir del proyecto, ticket ni usuario, y hay {como}. "
            "No se ha cambiado nada.\n"
            + "\n".join(f"  - {t}: {n} filas" for t, n in quedan.items())
            + "\nEmpresas (id, nombre, usuarios):\n"
            + "\n".join(f"  - {o[0]}  {o[1]}  ({o[2]} usuarios)" for o in orgs)
            + f"\nSi todas son de una misma empresa, indica cuál y repite: {VARIABLE_EMPRESA}=<id> "
              "(Windows: set; Linux: export). Si no, asígnalas a mano antes de migrar.")
    for t, n in quedan.items():
        conn.execute(sa.text(f"UPDATE {_q(conn, t)} SET {COL} = :e WHERE {COL} IS NULL"), {"e": empresa})
        cuenta[t]["respaldo"] += n
    logger.warning("208: %s filas sin empresa deducible asignadas a %s (%s)", sum(quedan.values()), empresa, como)
    return cuenta


# ── 3. NOT NULL ───────────────────────────────────────────────────────────────

_DEF_COLUMNA = re.compile(r'((?<![\w"])"?organization_id"?\s+[A-Za-z]+(?:\(\d+\))?)(\s+NOT\s+NULL)?', re.I)


def sql_con_restriccion(sql: str, obligatoria: bool) -> str:
    """El `CREATE TABLE` de SQLite con `organization_id` NOT NULL (o sin ello)."""
    m = _DEF_COLUMNA.search(sql)
    if not m:
        raise MigracionParada(f"208: no se encuentra la definición de {COL} en: {sql[:120]}…")
    nueva = m.group(1) + (" NOT NULL" if obligatoria else "")
    return sql[:m.start()] + nueva + sql[m.end():]


def _reconstruir_sqlite(conn, tabla: str, obligatoria: bool) -> None:
    fila = conn.execute(sa.text("SELECT sql FROM sqlite_master WHERE type='table' AND name=:t"), {"t": tabla}).first()
    anexos = [r[0] for r in conn.execute(sa.text(
        "SELECT sql FROM sqlite_master WHERE tbl_name=:t AND type IN ('index','trigger') AND sql IS NOT NULL"),
        {"t": tabla}).fetchall()]
    temporal = f"_tmp208_{tabla}"
    sql = sql_con_restriccion(fila[0], obligatoria)
    sql = re.sub(r'^\s*CREATE\s+TABLE\s+("[^"]+"|\S+)', f'CREATE TABLE "{temporal}"', sql, count=1, flags=re.I)
    conn.exec_driver_sql(sql)
    conn.exec_driver_sql(f'INSERT INTO "{temporal}" SELECT * FROM "{tabla}"')
    conn.exec_driver_sql(f'DROP TABLE "{tabla}"')
    conn.exec_driver_sql(f'ALTER TABLE "{temporal}" RENAME TO "{tabla}"')
    for a in anexos:
        conn.exec_driver_sql(a)


def poner_restriccion(conn, tablas: list, obligatoria: bool) -> None:
    if conn.dialect.name == "sqlite":
        if conn.exec_driver_sql("PRAGMA foreign_keys").scalar():
            raise MigracionParada("208: la conexión SQLite tiene PRAGMA foreign_keys=ON; rehacer las tablas "
                                  "dispararía los ON DELETE CASCADE. Migra con `scripts/migrar.py`/Alembic.")
        previo = conn.exec_driver_sql("PRAGMA legacy_alter_table").scalar()
        conn.exec_driver_sql("PRAGMA legacy_alter_table=ON")  # renombrar sin revalidar el resto del esquema
        try:
            for t in tablas:
                _reconstruir_sqlite(conn, t, obligatoria)
        finally:
            conn.exec_driver_sql(f"PRAGMA legacy_alter_table={'ON' if previo else 'OFF'}")
        return
    for t in tablas:
        op.alter_column(t, COL, existing_type=sa.String(36), nullable=not obligatoria)


# ── upgrade / downgrade ───────────────────────────────────────────────────────

def upgrade() -> None:
    conn = op.get_bind()
    con_empresa = tablas_con_empresa(conn)
    objetivo = sorted(t for t, nulable in con_empresa.items() if nulable and t not in EXCEPTUADAS)

    _exigir_sin_duplicados(conn)                  # antes de cambiar nada
    cuenta = rellenar(conn, objetivo)
    _exigir_sin_duplicados(conn)                  # el relleno puede juntar dos filas en una empresa
    rellenadas = {t: c for t, c in cuenta.items() if c["deducidas"] or c["respaldo"]}
    for t, c in sorted(rellenadas.items()):
        logger.info("208: %s: %s deducidas, %s por respaldo", t, c["deducidas"], c["respaldo"])

    insp = sa.inspect(conn)
    if USUARIOS_PORTAL in insp.get_table_names():
        indices = {i["name"]: i for i in insp.get_indexes(USUARIOS_PORTAL)}
        if IX_EMAIL in indices and indices[IX_EMAIL].get("unique"):
            op.drop_index(IX_EMAIL, table_name=USUARIOS_PORTAL)
            indices.pop(IX_EMAIL)
        if IX_EMAIL not in indices:
            op.create_index(IX_EMAIL, USUARIOS_PORTAL, ["email"], unique=False)

    poner_restriccion(conn, objetivo, True)

    if USUARIOS_PORTAL in sa.inspect(conn).get_table_names() and UQ_EMAIL not in {
            i["name"] for i in sa.inspect(conn).get_indexes(USUARIOS_PORTAL)}:
        op.create_index(UQ_EMAIL, USUARIOS_PORTAL, [COL, sa.text("lower(email)")], unique=True)
    logger.info("208: %s tablas con %s NOT NULL; %s exceptuadas; %s filas rellenadas",
                len(objetivo), COL, len(EXCEPTUADAS),
                sum(c["deducidas"] + c["respaldo"] for c in cuenta.values()))


def downgrade() -> None:
    conn = op.get_bind()
    insp = sa.inspect(conn)
    if USUARIOS_PORTAL in insp.get_table_names():
        repetidos = conn.execute(sa.text(
            f"SELECT email, count(*) FROM {USUARIOS_PORTAL} GROUP BY email HAVING count(*) > 1")).fetchall()
        if repetidos:
            raise MigracionParada(
                "208 (deshacer): el mismo correo está ya en varias empresas y la 207 lo exige único en toda la "
                "base. No se ha borrado ni cambiado nada:\n"
                + "\n".join(f"  - {_enmascarar(r[0])} ({r[1]} usuarios)" for r in repetidos)
                + "\nCambia o archiva los sobrantes antes de bajar de revisión.")
    con_empresa = tablas_con_empresa(conn)
    aflojar = sorted(t for t, nulable in con_empresa.items()
                     if not nulable and t not in YA_OBLIGATORIAS_EN_207 and t not in EXCEPTUADAS)
    if USUARIOS_PORTAL in insp.get_table_names():
        indices = {i["name"]: i for i in insp.get_indexes(USUARIOS_PORTAL)}
        if UQ_EMAIL in indices:
            op.drop_index(UQ_EMAIL, table_name=USUARIOS_PORTAL)
    poner_restriccion(conn, aflojar, False)
    if USUARIOS_PORTAL in sa.inspect(conn).get_table_names():
        indices = {i["name"]: i for i in sa.inspect(conn).get_indexes(USUARIOS_PORTAL)}
        if IX_EMAIL in indices and not indices[IX_EMAIL].get("unique"):
            op.drop_index(IX_EMAIL, table_name=USUARIOS_PORTAL)
            indices.pop(IX_EMAIL)
        if IX_EMAIL not in indices:
            op.create_index(IX_EMAIL, USUARIOS_PORTAL, ["email"], unique=True)
