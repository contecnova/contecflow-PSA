"""Jira: una sola fuente de configuracion (`sd_jira_configs`).

Auditoria 2026-11 (#34). La conexion de Jira de las TAREAS de proyecto vivia en
cuatro `app_settings` (`jira_url`, `jira_email`, `jira_api_token`,
`jira_project_key`) y las del service desk en `sd_jira_configs`. Ahora todo esta
en `sd_jira_configs`; la de las tareas es la fila `usar_para_tareas`.

upgrade:
  * anade `sd_jira_configs.usar_para_tareas` (si no esta);
  * por cada organizacion con `jira_url` y `jira_api_token` en `app_settings`
    y sin conexion de tareas, crea la fila (el token se copia tal cual: los dos
    sitios cifran con `encrypt_value`, y lo antiguo en claro sigue leyendose);
  * las filas globales (`organization_id` NULL) se asignan a la organizacion si
    solo hay una; si hay varias no se sabe de quien son y se dejan (ya no se leen);
  * borra las `app_settings` migradas. El secreto del webhook
    (`jira_webhook_secret`) se queda: es de la organizacion, no de una conexion.

Idempotente: repetirla no duplica filas ni falla. SQLite y PostgreSQL.
"""
import uuid

import sqlalchemy as sa
from alembic import op

revision = "159_jira_una_sola_configuracion"
down_revision = "158_obligaciones_asc606_precio_y_metodo"
branch_labels = None
depends_on = None

_CLAVES = ("jira_url", "jira_email", "jira_api_token", "jira_project_key")
_NOMBRE = "Proyectos (tareas)"


def _tablas(con) -> set[str]:
    return set(sa.inspect(con).get_table_names())


def _columnas(con, tabla: str) -> set[str]:
    return {c["name"] for c in sa.inspect(con).get_columns(tabla)}


def upgrade() -> None:
    con = op.get_bind()
    tablas = _tablas(con)
    if "sd_jira_configs" not in tablas:
        return
    if "usar_para_tareas" not in _columnas(con, "sd_jira_configs"):
        with op.batch_alter_table("sd_jira_configs") as lote:
            lote.add_column(sa.Column("usar_para_tareas", sa.Boolean(), nullable=False,
                                      server_default=sa.false()))
    if "app_settings" not in tablas:
        return

    filas = con.execute(sa.text(
        "SELECT organization_id, key, value FROM app_settings WHERE key IN "
        "('jira_url', 'jira_email', 'jira_api_token', 'jira_project_key')"
    )).fetchall()
    por_org: dict = {}
    for org, clave, valor in filas:
        por_org.setdefault(org, {})[clave] = valor

    globales = por_org.pop(None, None)
    if globales:
        orgs = [r[0] for r in con.execute(sa.text("SELECT id FROM organizations")).fetchall()] \
            if "organizations" in tablas else []
        if len(orgs) == 1 and orgs[0] not in por_org:
            por_org[orgs[0]] = globales
            por_org[orgs[0]]["_global"] = True

    for org, cfg in por_org.items():
        if not cfg.get("jira_url") or not cfg.get("jira_api_token"):
            continue
        ya = con.execute(sa.text(
            "SELECT 1 FROM sd_jira_configs WHERE organization_id = :o AND usar_para_tareas = :t"
        ), {"o": org, "t": True}).first()
        if not ya:
            con.execute(sa.text(
                "INSERT INTO sd_jira_configs (id, organization_id, name, jira_base_url, jira_email, "
                "jira_api_token_enc, jira_project_key, jira_issue_type_incident, "
                "jira_issue_type_service_request, jira_issue_type_change, jira_issue_type_problem, "
                "sync_direction, sync_comments, sync_status_changes, sync_priority_changes, "
                "sync_assignments, sync_interval_minutes, is_active, usar_para_tareas) VALUES "
                "(:id, :o, :n, :u, :e, :tok, :k, 'Incident', 'Service Request', 'Change', 'Problem', "
                "'bidirectional', :v, :v, :v, :f, 5, :v, :v)"
            ), {"id": str(uuid.uuid4()), "o": org, "n": _NOMBRE,
                "u": (cfg["jira_url"] or "").rstrip("/")[:500], "e": (cfg.get("jira_email") or "")[:255],
                "tok": cfg["jira_api_token"], "k": (cfg.get("jira_project_key") or "")[:50],
                "v": True, "f": False})
        filtro_org = "organization_id IS NULL" if cfg.get("_global") else "organization_id = :o"
        con.execute(sa.text(
            "DELETE FROM app_settings WHERE " + filtro_org + " AND key IN "  # noqa: S608 (constantes)
            "('jira_url', 'jira_email', 'jira_api_token', 'jira_project_key')"
        ), {"o": org})


def downgrade() -> None:
    """Devuelve la conexion de tareas a `app_settings` y quita la columna."""
    con = op.get_bind()
    tablas = _tablas(con)
    if "sd_jira_configs" not in tablas or "usar_para_tareas" not in _columnas(con, "sd_jira_configs"):
        return
    if "app_settings" in tablas:
        filas = con.execute(sa.text(
            "SELECT organization_id, jira_base_url, jira_email, jira_api_token_enc, jira_project_key "
            "FROM sd_jira_configs WHERE usar_para_tareas = :t"
        ), {"t": True}).fetchall()
        for org, url, email, token, clave_proyecto in filas:
            valores = dict(zip(_CLAVES, (url, email, token, clave_proyecto)))
            for clave, valor in valores.items():
                existe = con.execute(sa.text(
                    "SELECT 1 FROM app_settings WHERE key = :k AND organization_id = :o"
                ), {"k": clave, "o": org}).first()
                if not existe:
                    con.execute(sa.text(
                        "INSERT INTO app_settings (id, key, value, organization_id, description) "
                        "VALUES (:id, :k, :v, :o, :d)"
                    ), {"id": str(uuid.uuid4()), "k": clave, "v": valor, "o": org, "d": f"Jira integration: {clave}"})
        sin_enlaces = ("AND id NOT IN (SELECT config_id FROM sd_jira_sync_map)"
                       if "sd_jira_sync_map" in tablas else "")
        con.execute(sa.text(
            "DELETE FROM sd_jira_configs WHERE usar_para_tareas = :t AND name = :n " + sin_enlaces
        ), {"t": True, "n": _NOMBRE})
    with op.batch_alter_table("sd_jira_configs") as lote:
        lote.drop_column("usar_para_tareas")
