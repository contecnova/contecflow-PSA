"""Jira del hub de integraciones: de `integration_configs` a `sd_jira_configs`.

Segunda auditoria 2026-11 (#23). `/integrations-hub/jira/*` y el formulario
Empresa → Integraciones guardaban las credenciales de Jira en
`integration_configs` (tipo `jira`, JSON `{base_url, email, api_token}`),
mientras el resto de Jira usa la conexion de tareas de la organizacion
(`sd_jira_configs.usar_para_tareas`, migracion 159). Ahora el hub usa esa fila.

upgrade:
  * por cada fila `integration_configs` de tipo `jira` con organizacion, si la
    organizacion no tiene conexion de tareas, se crea con su URL, email, token
    (se copia cifrado tal cual: los dos sitios usan `encrypt_value`) y clave de
    proyecto. Si ya la tiene, gana la existente;
  * la fila antigua se desactiva y se le borran el token y el JSON (ya no se
    lee: dejar la credencial seria guardar una copia que nadie usa);
  * filas sin organizacion: se asignan si solo hay una organizacion; si no, se
    dejan como estan (no se sabe de quien son).

Idempotente (repetirla no duplica: la segunda vez la organizacion ya tiene su
conexion). SQLite y PostgreSQL. downgrade: no restaura (migracion de datos).
"""
import json
import uuid

import sqlalchemy as sa
from alembic import op

revision = "161_jira_hub_a_jira_config"
down_revision = "160_mfa_un_solo_sistema"
branch_labels = None
depends_on = None

_NOMBRE = "Proyectos (tareas)"


def upgrade() -> None:
    con = op.get_bind()
    insp = sa.inspect(con)
    tablas = set(insp.get_table_names())
    if "integration_configs" not in tablas or "sd_jira_configs" not in tablas:
        return
    if "usar_para_tareas" not in {c["name"] for c in insp.get_columns("sd_jira_configs")}:
        return

    filas = con.execute(sa.text(
        "SELECT id, organization_id, name, config, access_token, is_active "
        "FROM integration_configs WHERE integration_type = 'jira'"
    )).fetchall()
    if not filas:
        return

    orgs = [r[0] for r in con.execute(sa.text("SELECT id FROM organizations")).fetchall()] \
        if "organizations" in tablas else []
    unica = orgs[0] if len(orgs) == 1 else None

    for fila_id, org, nombre, config_json, access_token, activa in filas:
        org = org or unica
        if not org:
            continue
        try:
            cfg = json.loads(config_json) if config_json else {}
        except (TypeError, ValueError):
            cfg = {}
        if not isinstance(cfg, dict):
            cfg = {}
        url = (cfg.get("base_url") or cfg.get("jira_url") or "").rstrip("/")
        token = cfg.get("api_token") or access_token
        ya = con.execute(sa.text(
            "SELECT 1 FROM sd_jira_configs WHERE organization_id = :o AND usar_para_tareas = :t"
        ), {"o": org, "t": True}).first()
        if not ya and url and token:
            con.execute(sa.text(
                "INSERT INTO sd_jira_configs (id, organization_id, name, jira_base_url, jira_email, "
                "jira_api_token_enc, jira_project_key, jira_issue_type_incident, "
                "jira_issue_type_service_request, jira_issue_type_change, jira_issue_type_problem, "
                "sync_direction, sync_comments, sync_status_changes, sync_priority_changes, "
                "sync_assignments, sync_interval_minutes, is_active, usar_para_tareas) VALUES "
                "(:id, :o, :n, :u, :e, :tok, :k, 'Incident', 'Service Request', 'Change', 'Problem', "
                "'bidirectional', :v, :v, :v, :f, 5, :act, :v)"
            ), {"id": str(uuid.uuid4()), "o": org, "n": (nombre or _NOMBRE)[:100],
                "u": url[:500], "e": (cfg.get("email") or "")[:255], "tok": token,
                "k": (cfg.get("project_key") or "")[:50], "v": True, "f": False,
                "act": bool(activa) if activa is not None else True})
        con.execute(sa.text(
            "UPDATE integration_configs SET is_active = :f, access_token = NULL, "
            "refresh_token = NULL, config = NULL WHERE id = :id"
        ), {"f": False, "id": fila_id})


def downgrade() -> None:
    """Migracion de datos: no se vuelven a copiar las credenciales a `integration_configs`."""
