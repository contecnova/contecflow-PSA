"""Proyectos — planificador, hub y vistas (16-11-2026).

Esquema:
  · tasks: progress_pct, constraint_type/constraint_date (restricciones del
    planificador) y el resultado del camino crítico (early_*/late_*,
    total_float_days, free_float_days, is_critical, schedule_computed_at);
  · task_dependencies: link_type (schedule | relates_to | duplicates |
    cloned_from) y note — un solo modelo de vínculos entre tareas;
  · gantt_baselines: is_current (la línea base vigente de cada proyecto) y
    schedule_snapshot pasa a admitir NULL; nueva gantt_baseline_tasks (la foto
    por tarea);
  · evm_snapshots: la curva S diaria del valor ganado;
  · saved_filters: view_type, config, project_id, updated_at (vistas guardadas);
  · portfolio_criteria, portfolio_gates, portfolio_proposals (intake,
    puntuación y stage-gate);
  · template_tasks: role_name, duration_days; nueva template_task_dependencies.

Datos (duplicados que se eliminan):
  · task_dependency_meta → task_dependencies: «blocks» es FS, «blocked_by» es
    FS al revés, relates_to/duplicates/cloned_from quedan como vínculos
    informativos (`link_type`). Un par que ya existía no se duplica. Después se
    borra la tabla (y su tipo enum en PostgreSQL).
  · gantt_baselines.schedule_snapshot (JSON) → gantt_baseline_tasks. La línea
    base más reciente de cada proyecto queda como vigente.

Downgrade: recrea task_dependency_meta y le devuelve los vínculos
informativos (los FS que vinieron de «blocks» no se distinguen de los demás y
se quedan en task_dependencies); quita columnas y tablas nuevas. Las líneas
base conservan su JSON.

Revision ID: 173_proyectos_planificador_y_hub
Revises: 172_alm_altas_bajas_y_autoservicio
"""
from __future__ import annotations

import json
import uuid
from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "173_proyectos_planificador_y_hub"
down_revision: Union[str, None] = "172_alm_altas_bajas_y_autoservicio"
branch_labels = None
depends_on = None

#: Lo que guarda la columna Enum de `task_dependencies.dependency_type` (el nombre del miembro).
_FS = "finish_to_start"
_INFORMATIVOS = ("relates_to", "duplicates", "cloned_from")


def _tablas(con) -> set[str]:
    return set(sa.inspect(con).get_table_names())


def _columnas(con, tabla: str) -> set[str]:
    return {c["name"] for c in sa.inspect(con).get_columns(tabla)}


def _anadir(con, tabla: str, columnas: list[sa.Column]) -> None:
    existentes = _columnas(con, tabla)
    nuevas = [c for c in columnas if c.name not in existentes]
    if not nuevas:
        return
    with op.batch_alter_table(tabla) as t:
        for c in nuevas:
            t.add_column(c)


# ── upgrade ──────────────────────────────────────────────────────────────────

def upgrade() -> None:
    con = op.get_bind()
    tablas = _tablas(con)

    # 1. Tareas: avance, restricciones y resultado del CPM.
    _anadir(con, "tasks", [
        sa.Column("progress_pct", sa.Float(), nullable=True),
        sa.Column("constraint_type", sa.String(10), nullable=True),
        sa.Column("constraint_date", sa.Date(), nullable=True),
        sa.Column("early_start", sa.Date(), nullable=True),
        sa.Column("early_finish", sa.Date(), nullable=True),
        sa.Column("late_start", sa.Date(), nullable=True),
        sa.Column("late_finish", sa.Date(), nullable=True),
        sa.Column("total_float_days", sa.Integer(), nullable=True),
        sa.Column("free_float_days", sa.Integer(), nullable=True),
        sa.Column("is_critical", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("schedule_computed_at", sa.DateTime(timezone=True), nullable=True),
    ])

    # 2. Un solo modelo de dependencias.
    _anadir(con, "task_dependencies", [
        sa.Column("link_type", sa.String(20), nullable=False, server_default="schedule"),
        sa.Column("note", sa.String(500), nullable=True),
    ])
    if "task_dependency_meta" in tablas:
        _migrar_dependencias_duplicadas(con)
        with op.batch_alter_table("task_dependency_meta") as t:
            t.drop_index("ix_task_dependency_meta_from_task_id")
            t.drop_index("ix_task_dependency_meta_to_task_id")
        op.drop_table("task_dependency_meta")
        if con.dialect.name == "postgresql":
            op.execute("DROP TYPE IF EXISTS taskdeptype")

    # 3. Líneas base: vigente y foto por tarea.
    _anadir(con, "gantt_baselines", [
        sa.Column("is_current", sa.Boolean(), nullable=False, server_default=sa.false()),
    ])
    with op.batch_alter_table("gantt_baselines") as t:
        t.alter_column("schedule_snapshot", existing_type=sa.Text(), nullable=True)
        t.create_index("ix_gantt_baselines_is_current", ["is_current"])
    if "gantt_baseline_tasks" not in tablas:
        op.create_table(
            "gantt_baseline_tasks",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("organization_id", sa.String(36), sa.ForeignKey("organizations.id"), nullable=True),
            sa.Column("baseline_id", sa.String(36),
                      sa.ForeignKey("gantt_baselines.id", ondelete="CASCADE"), nullable=False),
            sa.Column("task_id", sa.String(36), nullable=False),
            sa.Column("title", sa.String(500), nullable=True),
            sa.Column("start_date", sa.Date(), nullable=True),
            sa.Column("end_date", sa.Date(), nullable=True),
            sa.Column("estimated_hours", sa.Float(), nullable=True),
            sa.Column("planned_cost", sa.Float(), nullable=True),
            sa.Column("status", sa.String(30), nullable=True),
            sa.Column("assignee_id", sa.String(36), nullable=True),
            sa.Column("progress_pct", sa.Float(), nullable=True),
        )
        op.create_index("ix_gantt_baseline_tasks_organization_id", "gantt_baseline_tasks", ["organization_id"])
        op.create_index("ix_gantt_baseline_tasks_baseline_id", "gantt_baseline_tasks", ["baseline_id"])
        op.create_index("ix_gantt_baseline_tasks_task_id", "gantt_baseline_tasks", ["task_id"])
        _migrar_fotos_de_lineas_base(con)

    # 4. Curva S.
    if "evm_snapshots" not in tablas:
        op.create_table(
            "evm_snapshots",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("organization_id", sa.String(36),
                      sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=True),
            sa.Column("project_id", sa.String(36), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
            sa.Column("snapshot_date", sa.Date(), nullable=False),
            sa.Column("baseline_id", sa.String(36), nullable=True),
            sa.Column("bac", sa.Float(), nullable=True),
            sa.Column("pv", sa.Float(), nullable=True),
            sa.Column("ev", sa.Float(), nullable=True),
            sa.Column("ac", sa.Float(), nullable=True),
            sa.Column("cpi", sa.Float(), nullable=True),
            sa.Column("spi", sa.Float(), nullable=True),
            sa.Column("pct_complete", sa.Float(), nullable=True),
            sa.Column("pct_planned", sa.Float(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.UniqueConstraint("project_id", "snapshot_date", name="uq_evm_snapshot_dia"),
        )
        op.create_index("ix_evm_snapshots_organization_id", "evm_snapshots", ["organization_id"])
        op.create_index("ix_evm_snapshots_project_id", "evm_snapshots", ["project_id"])
        op.create_index("ix_evm_snapshots_snapshot_date", "evm_snapshots", ["snapshot_date"])

    # 5. Vistas guardadas sobre `saved_filters`.
    _anadir(con, "saved_filters", [
        sa.Column("view_type", sa.String(20), nullable=True),
        sa.Column("config", sa.Text(), nullable=True),
        sa.Column("project_id", sa.String(36), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    ])
    with op.batch_alter_table("saved_filters") as t:
        t.alter_column("nql_query", existing_type=sa.Text(), nullable=False, server_default="")
        t.create_foreign_key("fk_saved_filters_project_id", "projects", ["project_id"], ["id"], ondelete="CASCADE")
        t.create_index("ix_saved_filters_project_id", ["project_id"])

    # 6. Cartera: intake, puntuación y fases.
    if "portfolio_criteria" not in tablas:
        op.create_table(
            "portfolio_criteria",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("organization_id", sa.String(36),
                      sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=True, index=True),
            sa.Column("name", sa.String(120), nullable=False),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("weight", sa.Float(), nullable=False, server_default="1"),
            sa.Column("inverse", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        )
    if "portfolio_gates" not in tablas:
        op.create_table(
            "portfolio_gates",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("organization_id", sa.String(36),
                      sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=True, index=True),
            sa.Column("name", sa.String(120), nullable=False),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("workflow_id", sa.String(36),
                      sa.ForeignKey("approval_workflows.id", ondelete="SET NULL"), nullable=True, index=True),
            sa.Column("min_score", sa.Float(), nullable=True),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        )
    if "portfolio_proposals" not in tablas:
        op.create_table(
            "portfolio_proposals",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("organization_id", sa.String(36),
                      sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=True, index=True),
            sa.Column("portfolio_id", sa.String(36),
                      sa.ForeignKey("portfolios.id", ondelete="SET NULL"), nullable=True, index=True),
            sa.Column("title", sa.String(255), nullable=False),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("requested_by", sa.String(36), sa.ForeignKey("users.id", ondelete="SET NULL"),
                      nullable=True, index=True),
            sa.Column("sponsor_id", sa.String(36), sa.ForeignKey("users.id", ondelete="SET NULL"),
                      nullable=True, index=True),
            sa.Column("client_id", sa.String(36), sa.ForeignKey("clients.id", ondelete="SET NULL"),
                      nullable=True, index=True),
            sa.Column("estimated_budget", sa.Float(), nullable=True),
            sa.Column("estimated_hours", sa.Float(), nullable=True),
            sa.Column("wanted_start", sa.Date(), nullable=True),
            sa.Column("wanted_end", sa.Date(), nullable=True),
            sa.Column("roles_needed", sa.Text(), nullable=True),
            sa.Column("scores", sa.Text(), nullable=True),
            sa.Column("score", sa.Float(), nullable=True),
            sa.Column("status", sa.String(20), nullable=False, server_default="draft", index=True),
            sa.Column("gate_index", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("decision_note", sa.Text(), nullable=True),
            sa.Column("project_id", sa.String(36), sa.ForeignKey("projects.id", ondelete="SET NULL"),
                      nullable=True, index=True),
            sa.Column("template_id", sa.String(36),
                      sa.ForeignKey("project_templates.id", ondelete="SET NULL"), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        )

    # 7. Plantillas: rol y duración de cada tarea y dependencias entre tareas.
    _anadir(con, "template_tasks", [
        sa.Column("role_name", sa.String(100), nullable=True),
        sa.Column("duration_days", sa.Integer(), nullable=True),
    ])
    if "template_task_dependencies" not in tablas:
        op.create_table(
            "template_task_dependencies",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("organization_id", sa.String(36), sa.ForeignKey("organizations.id"),
                      nullable=True, index=True),
            sa.Column("template_id", sa.String(36),
                      sa.ForeignKey("project_templates.id", ondelete="CASCADE"), nullable=False, index=True),
            sa.Column("predecessor_id", sa.String(36),
                      sa.ForeignKey("template_tasks.id", ondelete="CASCADE"), nullable=False, index=True),
            sa.Column("successor_id", sa.String(36),
                      sa.ForeignKey("template_tasks.id", ondelete="CASCADE"), nullable=False, index=True),
            sa.Column("dependency_type", sa.String(2), nullable=False, server_default="FS"),
            sa.Column("lag_days", sa.Integer(), nullable=False, server_default="0"),
        )
    # Datos: una tarea de plantilla cuyo `skill_required` coincide con un rol de
    # su plantilla queda asignada a ese rol (antes el rol y la tarea iban por
    # separado y aplicar la plantilla no los relacionaba).
    con.execute(sa.text(
        "UPDATE template_tasks SET role_name = ("
        " SELECT MIN(r.role_name) FROM template_roles r JOIN template_phases p ON p.template_id = r.template_id"
        " WHERE p.id = template_tasks.phase_id AND r.skill_required = template_tasks.skill_required)"
        " WHERE role_name IS NULL AND skill_required IS NOT NULL"))


def _migrar_dependencias_duplicadas(con) -> None:
    """task_dependency_meta → task_dependencies (ver el docstring del módulo).

    `organization_id` de `task_dependency_meta` no lo crea ninguna migración con
    nombre: lo añadía la 080 recorriendo `Base.metadata`, y esta revisión retira
    el modelo. En una base nueva la columna no existe; la organización sale
    entonces de la tarea de origen, que es la misma.
    """
    columnas = {c["name"] for c in sa.inspect(con).get_columns("task_dependency_meta")}
    org = ("organization_id" if "organization_id" in columnas else
           "(SELECT t.organization_id FROM tasks t WHERE t.id = task_dependency_meta.from_task_id)")
    filas = con.execute(sa.text(
        f"SELECT id, {org} AS organization_id, from_task_id, to_task_id, dep_type, lag_days, note, created_by, "
        "created_at FROM task_dependency_meta")).mappings().all()
    existentes = {(p, s) for p, s in con.execute(sa.text(
        "SELECT predecessor_id, successor_id FROM task_dependencies")).all()}
    for f in filas:
        tipo = str(f["dep_type"] or "blocks")
        pred, suc, vinculo = f["from_task_id"], f["to_task_id"], "schedule"
        if tipo == "blocked_by":
            pred, suc = suc, pred
        elif tipo in _INFORMATIVOS:
            vinculo = tipo
        if pred == suc or (pred, suc) in existentes:
            continue
        existentes.add((pred, suc))
        con.execute(sa.text(
            "INSERT INTO task_dependencies (id, organization_id, predecessor_id, successor_id, dependency_type, "
            "is_active, lag_days, link_type, note, created_by, created_at) VALUES "
            "(:id, :org, :pred, :suc, :tipo, :activo, :lag, :vinculo, :nota, :autor, :creado)"),
            {"id": str(uuid.uuid4()), "org": f["organization_id"], "pred": pred, "suc": suc, "tipo": _FS,
             "activo": True, "lag": f["lag_days"] or 0, "vinculo": vinculo, "nota": f["note"],
             "autor": f["created_by"], "creado": f["created_at"]})


def _migrar_fotos_de_lineas_base(con) -> None:
    """El JSON de cada línea base a filas; la más reciente de cada proyecto, vigente."""
    from datetime import date

    def _fecha(v):
        try:
            return date.fromisoformat(v) if v else None
        except (TypeError, ValueError):
            return None

    lineas = con.execute(sa.text(
        "SELECT id, organization_id, project_id, schedule_snapshot, baseline_date, created_at "
        "FROM gantt_baselines")).mappings().all()
    ultima: dict = {}
    for b in lineas:
        clave = (b["baseline_date"], b["created_at"])
        if b["project_id"] not in ultima or clave > ultima[b["project_id"]][0]:
            ultima[b["project_id"]] = (clave, b["id"])
        try:
            foto = json.loads(b["schedule_snapshot"] or "{}")
        except ValueError:
            continue
        for t in foto.get("tasks", []) or []:
            if not t.get("task_id"):
                continue
            con.execute(sa.text(
                "INSERT INTO gantt_baseline_tasks (id, organization_id, baseline_id, task_id, title, start_date, "
                "end_date, estimated_hours, status, assignee_id, progress_pct) VALUES "
                "(:id, :org, :b, :t, :titulo, :ini, :fin, :horas, :estado, :persona, :avance)"),
                {"id": str(uuid.uuid4()), "org": b["organization_id"], "b": b["id"], "t": t["task_id"],
                 "titulo": (t.get("title") or "")[:500], "ini": _fecha(t.get("start")), "fin": _fecha(t.get("end")),
                 "horas": t.get("estimated_hours"), "estado": t.get("status"), "persona": t.get("assignee_id"),
                 "avance": t.get("progress") if isinstance(t.get("progress"), (int, float)) else None})
    for _clave, baseline_id in ultima.values():
        con.execute(sa.text("UPDATE gantt_baselines SET is_current = :si WHERE id = :id"),
                    {"si": True, "id": baseline_id})


# ── downgrade ────────────────────────────────────────────────────────────────

def downgrade() -> None:
    con = op.get_bind()
    tablas = _tablas(con)

    if "template_task_dependencies" in tablas:
        op.drop_table("template_task_dependencies")
    with op.batch_alter_table("template_tasks") as t:
        t.drop_column("duration_days")
        t.drop_column("role_name")

    for tabla in ("portfolio_proposals", "portfolio_gates", "portfolio_criteria"):
        if tabla in tablas:
            op.drop_table(tabla)

    with op.batch_alter_table("saved_filters") as t:
        t.drop_index("ix_saved_filters_project_id")
        t.drop_constraint("fk_saved_filters_project_id", type_="foreignkey")
        t.drop_column("updated_at")
        t.drop_column("project_id")
        t.drop_column("config")
        t.drop_column("view_type")

    if "evm_snapshots" in tablas:
        op.drop_table("evm_snapshots")

    if "gantt_baseline_tasks" in tablas:
        op.drop_table("gantt_baseline_tasks")
    # Las líneas base creadas después de la 173 no tienen JSON: se les pone uno vacío.
    con.execute(sa.text(
        "UPDATE gantt_baselines SET schedule_snapshot = '{\"tasks\": []}' WHERE schedule_snapshot IS NULL"))
    with op.batch_alter_table("gantt_baselines") as t:
        t.drop_index("ix_gantt_baselines_is_current")
        t.drop_column("is_current")
        t.alter_column("schedule_snapshot", existing_type=sa.Text(), nullable=False)

    # task_dependency_meta vuelve con los vínculos informativos.
    op.create_table(
        "task_dependency_meta",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("organization_id", sa.String(36), sa.ForeignKey("organizations.id"), nullable=True, index=True),
        sa.Column("from_task_id", sa.String(36), sa.ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False),
        sa.Column("to_task_id", sa.String(36), sa.ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False),
        sa.Column("dep_type", sa.Enum("blocks", "blocked_by", "relates_to", "duplicates", "cloned_from",
                                      name="taskdeptype"), nullable=False),
        sa.Column("lag_days", sa.Integer(), nullable=True),
        sa.Column("note", sa.String(500), nullable=True),
        sa.Column("created_by", sa.String(36), sa.ForeignKey("users.id"), nullable=True, index=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_task_dependency_meta_from_task_id", "task_dependency_meta", ["from_task_id"])
    op.create_index("ix_task_dependency_meta_to_task_id", "task_dependency_meta", ["to_task_id"])
    informativos = con.execute(sa.text(
        "SELECT id, organization_id, predecessor_id, successor_id, link_type, lag_days, note, created_by, created_at "
        "FROM task_dependencies WHERE link_type <> 'schedule'")).mappings().all()
    for f in informativos:
        con.execute(sa.text(
            "INSERT INTO task_dependency_meta (id, organization_id, from_task_id, to_task_id, dep_type, lag_days, "
            "note, created_by, created_at) VALUES (:id, :org, :de, :a, :tipo, :lag, :nota, :autor, :creado)"),
            {"id": f["id"], "org": f["organization_id"], "de": f["predecessor_id"], "a": f["successor_id"],
             "tipo": f["link_type"], "lag": f["lag_days"], "nota": f["note"], "autor": f["created_by"],
             "creado": f["created_at"]})
    con.execute(sa.text("DELETE FROM task_dependencies WHERE link_type <> 'schedule'"))
    with op.batch_alter_table("task_dependencies") as t:
        t.drop_column("note")
        t.drop_column("link_type")

    with op.batch_alter_table("tasks") as t:
        for c in ("schedule_computed_at", "is_critical", "free_float_days", "total_float_days", "late_finish",
                  "late_start", "early_finish", "early_start", "constraint_date", "constraint_type",
                  "progress_pct"):
            t.drop_column(c)
