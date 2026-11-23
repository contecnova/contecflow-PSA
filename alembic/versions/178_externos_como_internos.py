"""Externos como internos, con seguridad de externo (16-11-2026).

Un externo (trabajador de subcontrata) trabaja como un interno: es miembro de
los proyectos a los que se le asigna, imputa como todos y su coste sale de la
tarifa del proveedor vigente. Ver `app/services/externos/`.

Columnas nuevas:

- `subcontractor_workers`: `has_access` (con login o recurso sin acceso),
  `access_until` (caducidad del acceso), `internal_owner_id` (responsable
  interno) y `access_expiry_notified_at` (aviso previo ya enviado).
- `subcontractor_assignments`: `project_member_id` (el miembro que crea la
  asignacion), `is_active`, `ended_at` y `consumption_alert_pct` (ultimo umbral
  de consumo avisado).
- `subcontractor_timelogs`: `worker_id` (de quien son las horas del parte
  manual) y `source` (`manual` | `import`).

Datos:

- `access_until` = `available_until` en los trabajadores existentes.
- Habilidades: las de `subcontractor_worker_skills` (activas, de trabajadores
  con usuario) se copian a `user_skills` del usuario si no tiene ya esa
  habilidad. Desde aqui la unica fuente es `user_skills` (SmartMatch, analisis
  y prevision ya leen de ahi). La tabla vieja se conserva para el downgrade.
- Asignaciones con persona (y usuario): se crea su `project_members` activo si
  no lo era ya, con las fechas de la asignacion, y se enlaza.
- Partes manuales: `worker_id` = el de su asignacion; `source` = `manual`.

Downgrade: quita las columnas. Las habilidades copiadas y los miembros creados
se quedan (son datos validos por si mismos; no se distinguen de los manuales).

Revision ID: 178_externos_como_internos
Revises: 177_portal_idiomas_restos
"""
import uuid

import sqlalchemy as sa
from alembic import op

revision = "178_externos_como_internos"
down_revision = "177_portal_idiomas_restos"
branch_labels = None
depends_on = None

_NIVELES = {"basic": "basic", "beginner": "basic", "intermediate": "intermediate",
            "advanced": "advanced", "expert": "expert"}


def _columnas(con, tabla: str) -> set[str]:
    return {c["name"] for c in sa.inspect(con).get_columns(tabla)}


def _tablas(con) -> set[str]:
    return set(sa.inspect(con).get_table_names())


def nivel(valor) -> str:
    """Nivel de `user_skills` para un nivel libre del trabajador."""
    return _NIVELES.get(str(valor or "").strip().lower(), "intermediate")


def _copiar_habilidades(con) -> None:
    # 23-11-2026: retirado el modelo (la 196 borra la tabla), la 080/082 ya no le
    # añaden `organization_id` en una base nueva: sin la columna, NULL.
    cols = {c["name"] for c in sa.inspect(con).get_columns("subcontractor_worker_skills")}
    org = "s.organization_id" if "organization_id" in cols else "NULL"
    filas = con.execute(sa.text(
        "SELECT w.user_id, s.skill_id, s.level, s.years_experience, s.certified, s.cert_name, s.notes, "
        f"{org} FROM subcontractor_worker_skills s JOIN subcontractor_workers w ON w.id = s.worker_id "
        "WHERE w.user_id IS NOT NULL AND s.is_active = :t"), {"t": True}).fetchall()
    for user_id, skill_id, lvl, anos, cert, cert_name, notas, org in filas:
        ya = con.execute(sa.text("SELECT 1 FROM user_skills WHERE user_id = :u AND skill_id = :s"),
                         {"u": user_id, "s": skill_id}).first()
        if ya:
            continue
        con.execute(sa.text(
            "INSERT INTO user_skills (id, organization_id, user_id, skill_id, level, years_experience, certified, "
            "cert_name, notes) VALUES (:id, :org, :u, :s, :lvl, :anos, :cert, :cn, :n)"),
            {"id": str(uuid.uuid4()), "org": org, "u": user_id, "s": skill_id, "lvl": nivel(lvl),
             "anos": anos, "cert": bool(cert), "cn": cert_name, "n": notas})


def _crear_miembros(con) -> None:
    filas = con.execute(sa.text(
        "SELECT a.id, a.project_id, w.user_id, a.start_date, a.end_date, a.organization_id "
        "FROM subcontractor_assignments a JOIN subcontractor_workers w ON w.id = a.worker_id "
        "WHERE w.user_id IS NOT NULL AND a.project_member_id IS NULL")).fetchall()
    for aid, pid, uid, ini, fin, org in filas:
        miembro = con.execute(sa.text(
            "SELECT id FROM project_members WHERE project_id = :p AND user_id = :u"), {"p": pid, "u": uid}).first()
        if miembro:
            mid = miembro[0]
        else:
            mid = str(uuid.uuid4())
            con.execute(sa.text(
                "INSERT INTO project_members (id, organization_id, project_id, user_id, is_active, role, "
                "allocation_pct, start_date, end_date, notes) VALUES (:id, :org, :p, :u, :act, 'developer', 100, "
                ":ini, :fin, :n)"),
                {"id": mid, "org": org, "p": pid, "u": uid, "act": True, "ini": ini, "fin": fin,
                 "n": "Externo (asignacion de subcontrata)"})
        con.execute(sa.text("UPDATE subcontractor_assignments SET project_member_id = :m WHERE id = :a"),
                    {"m": mid, "a": aid})


def upgrade() -> None:
    con = op.get_bind()
    tablas = _tablas(con)
    if "subcontractor_workers" not in tablas:
        return
    cw = _columnas(con, "subcontractor_workers")
    with op.batch_alter_table("subcontractor_workers") as t:
        if "has_access" not in cw:
            t.add_column(sa.Column("has_access", sa.Boolean(), nullable=False, server_default=sa.true()))
        if "access_until" not in cw:
            t.add_column(sa.Column("access_until", sa.Date(), nullable=True))
        if "internal_owner_id" not in cw:
            t.add_column(sa.Column("internal_owner_id", sa.String(36), nullable=True))
            t.create_foreign_key("fk_subcontractor_workers_internal_owner", "users",
                                 ["internal_owner_id"], ["id"], ondelete="SET NULL")
            t.create_index("ix_subcontractor_workers_internal_owner_id", ["internal_owner_id"])
        if "access_expiry_notified_at" not in cw:
            t.add_column(sa.Column("access_expiry_notified_at", sa.Date(), nullable=True))

    ca = _columnas(con, "subcontractor_assignments")
    with op.batch_alter_table("subcontractor_assignments") as t:
        if "project_member_id" not in ca:
            t.add_column(sa.Column("project_member_id", sa.String(36), nullable=True))
            t.create_foreign_key("fk_subcontractor_assignments_member", "project_members",
                                 ["project_member_id"], ["id"], ondelete="SET NULL")
            t.create_index("ix_subcontractor_assignments_project_member_id", ["project_member_id"])
        if "is_active" not in ca:
            t.add_column(sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()))
        if "ended_at" not in ca:
            t.add_column(sa.Column("ended_at", sa.Date(), nullable=True))
        if "consumption_alert_pct" not in ca:
            t.add_column(sa.Column("consumption_alert_pct", sa.Float(), nullable=True))

    ct = _columnas(con, "subcontractor_timelogs")
    with op.batch_alter_table("subcontractor_timelogs") as t:
        if "worker_id" not in ct:
            t.add_column(sa.Column("worker_id", sa.String(36), nullable=True))
            t.create_foreign_key("fk_subcontractor_timelogs_worker", "subcontractor_workers",
                                 ["worker_id"], ["id"], ondelete="SET NULL")
            t.create_index("ix_subcontractor_timelogs_worker_id", ["worker_id"])
        if "source" not in ct:
            t.add_column(sa.Column("source", sa.String(20), nullable=False, server_default="manual"))

    con.execute(sa.text("UPDATE subcontractor_workers SET access_until = available_until "
                        "WHERE access_until IS NULL AND available_until IS NOT NULL"))
    con.execute(sa.text(
        "UPDATE subcontractor_timelogs SET worker_id = (SELECT a.worker_id FROM subcontractor_assignments a "
        "WHERE a.id = subcontractor_timelogs.assignment_id) WHERE worker_id IS NULL"))
    if {"subcontractor_worker_skills", "user_skills"} <= tablas:
        _copiar_habilidades(con)
    if "project_members" in tablas:
        _crear_miembros(con)


def downgrade() -> None:
    con = op.get_bind()
    if "subcontractor_workers" not in _tablas(con):
        return
    with op.batch_alter_table("subcontractor_timelogs") as t:
        t.drop_index("ix_subcontractor_timelogs_worker_id")
        t.drop_constraint("fk_subcontractor_timelogs_worker", type_="foreignkey")
        t.drop_column("worker_id")
        t.drop_column("source")
    with op.batch_alter_table("subcontractor_assignments") as t:
        t.drop_index("ix_subcontractor_assignments_project_member_id")
        t.drop_constraint("fk_subcontractor_assignments_member", type_="foreignkey")
        for c in ("project_member_id", "is_active", "ended_at", "consumption_alert_pct"):
            t.drop_column(c)
    with op.batch_alter_table("subcontractor_workers") as t:
        t.drop_index("ix_subcontractor_workers_internal_owner_id")
        t.drop_constraint("fk_subcontractor_workers_internal_owner", type_="foreignkey")
        for c in ("has_access", "access_until", "internal_owner_id", "access_expiry_notified_at"):
            t.drop_column(c)
