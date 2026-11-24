"""Bucle de aprendizaje del motor semántico, preguntas sin respuesta como tareas y memoria de Ask-the-Data (23-11-2026).

Lo traído de contecmind y contecintelligence (README, «Conectores con contecmind
y contecintelligence» y «Motor semántico»):

1. `sem_feedback.correction_kind` (String(30), nulo): el tipo de corrección
   (`correccion` | `confirmacion_responsable`). Antes `POST /semantic/feedback`
   guardaba `corrected_by = "manager_confirm:<uuid>"` (52 caracteres) en una
   columna `String(36)` con FK a `users.id`. Datos: las filas con ese prefijo
   pasan a `corrected_by = <uuid>` y `correction_kind = confirmacion_responsable`;
   el resto con `corrected_by` a `correccion`.
2. `sd_kb_gaps`: `owner_id` (FK users, SET NULL), `due_date`, `follow_status`
   (no nulo, `pendiente`) y `task_id` (FK tasks, SET NULL), con índice en
   `owner_id` y `task_id`. Las preguntas ya respondidas o descartadas quedan en
   `hecho`.
3. Tablas nuevas `ask_data_conversations` y `ask_data_turns` (con
   `organization_id`; la RLS la aplica `env.py` tras el `upgrade`).

Compatible con SQLite (`batch_alter_table`) y Postgres. Idempotente: mira antes
cada tabla, columna e índice.

Deshacer real: borra las dos tablas (con sus filas: las conversaciones se
pierden), quita las cuatro columnas de `sd_kb_gaps` (responsable, plazo,
seguimiento y tarea se pierden; la tarea creada se queda) y `correction_kind`
(los `corrected_by` ya corregidos se quedan como uuid: es un valor válido
también en el esquema anterior; no se reconstruye el texto erróneo).

Revision ID: 207_conectores_y_semantico
Revises: 206_pir
"""
import logging

import sqlalchemy as sa
from alembic import op

revision = "207_conectores_y_semantico"
down_revision = "206_pir"
branch_labels = None
depends_on = None

logger = logging.getLogger("alembic.207")

_TZ = sa.DateTime(timezone=True)
FEEDBACK = "sem_feedback"
HUECOS = "sd_kb_gaps"
CONVERSACIONES = "ask_data_conversations"
TURNOS = "ask_data_turns"
_PREFIJO = "manager_confirm:"


def _insp():
    return sa.inspect(op.get_bind())


def _tablas() -> set:
    return set(_insp().get_table_names())


def _cols(tabla: str) -> set:
    if tabla not in _tablas():
        return set()
    return {c["name"] for c in _insp().get_columns(tabla)}


def _indices(tabla: str) -> set:
    if tabla not in _tablas():
        return set()
    return {i["name"] for i in _insp().get_indexes(tabla)}


def _org():
    return sa.Column("organization_id", sa.String(36), sa.ForeignKey("organizations.id", ondelete="CASCADE"),
                     nullable=True)


# ── 1. sem_feedback.correction_kind ───────────────────────────────────────────

def _feedback_upgrade() -> None:
    if not _cols(FEEDBACK) or "correction_kind" in _cols(FEEDBACK):
        return
    with op.batch_alter_table(FEEDBACK) as b:
        b.add_column(sa.Column("correction_kind", sa.String(30), nullable=True))
    bind = op.get_bind()
    t = sa.table(FEEDBACK, sa.column("id", sa.String), sa.column("corrected_by", sa.String),
                 sa.column("correction_kind", sa.String))
    arregladas = 0
    for fila in bind.execute(sa.select(t.c.id, t.c.corrected_by).where(t.c.corrected_by.like(_PREFIJO + "%"))).all():
        uuid_ = (fila.corrected_by or "")[len(_PREFIJO):][:36] or None
        bind.execute(t.update().where(t.c.id == fila.id).values(corrected_by=uuid_,
                                                                 correction_kind="confirmacion_responsable"))
        arregladas += 1
    bind.execute(t.update().where(t.c.correction_kind.is_(None), t.c.corrected_by.isnot(None))
                 .values(correction_kind="correccion"))
    logger.info("207: sem_feedback.correction_kind; %s filas con «manager_confirm:» corregidas", arregladas)


def _feedback_downgrade() -> None:
    if "correction_kind" in _cols(FEEDBACK):
        with op.batch_alter_table(FEEDBACK) as b:
            b.drop_column("correction_kind")


# ── 2. sd_kb_gaps: seguimiento como tarea ─────────────────────────────────────

_COLS_HUECO = ("owner_id", "due_date", "follow_status", "task_id")


def _huecos_upgrade() -> None:
    hay = _cols(HUECOS)
    if not hay:
        return
    faltan = [c for c in _COLS_HUECO if c not in hay]
    if faltan:
        with op.batch_alter_table(HUECOS) as b:
            if "owner_id" in faltan:
                b.add_column(sa.Column("owner_id", sa.String(36), sa.ForeignKey(
                    "users.id", ondelete="SET NULL", name="fk_sd_kb_gaps_owner_id_users"), nullable=True))
            if "due_date" in faltan:
                b.add_column(sa.Column("due_date", sa.Date(), nullable=True))
            if "follow_status" in faltan:
                b.add_column(sa.Column("follow_status", sa.String(20), nullable=False, server_default="pendiente"))
            if "task_id" in faltan:
                b.add_column(sa.Column("task_id", sa.String(36), sa.ForeignKey(
                    "tasks.id", ondelete="SET NULL", name="fk_sd_kb_gaps_task_id_tasks"), nullable=True))
        if "follow_status" in faltan:
            op.get_bind().execute(sa.text(
                "UPDATE sd_kb_gaps SET follow_status = 'hecho' WHERE status IN ('answered', 'dismissed')"))
    existentes = _indices(HUECOS)
    for col in ("owner_id", "task_id"):
        if f"ix_{HUECOS}_{col}" not in existentes:
            op.create_index(f"ix_{HUECOS}_{col}", HUECOS, [col])


def _huecos_downgrade() -> None:
    existentes = _indices(HUECOS)
    for col in ("owner_id", "task_id"):
        if f"ix_{HUECOS}_{col}" in existentes:
            op.drop_index(f"ix_{HUECOS}_{col}", table_name=HUECOS)
    hay = [c for c in _COLS_HUECO if c in _cols(HUECOS)]
    if hay:
        with op.batch_alter_table(HUECOS) as b:
            for c in hay:
                b.drop_column(c)


# ── 3. Conversaciones de Ask-the-Data ─────────────────────────────────────────

def _ask_upgrade() -> None:
    hay = _tablas()
    if CONVERSACIONES not in hay:
        op.create_table(
            CONVERSACIONES,
            sa.Column("id", sa.String(36), primary_key=True), _org(),
            sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
            sa.Column("title", sa.String(200), nullable=False, server_default=""),
            sa.Column("created_at", _TZ, server_default=sa.func.now(), nullable=True),
            sa.Column("updated_at", _TZ, server_default=sa.func.now(), nullable=True),
        )
    if TURNOS not in hay:
        op.create_table(
            TURNOS,
            sa.Column("id", sa.String(36), primary_key=True), _org(),
            sa.Column("conversation_id", sa.String(36),
                      sa.ForeignKey(f"{CONVERSACIONES}.id", ondelete="CASCADE"), nullable=False),
            sa.Column("question", sa.Text(), nullable=False),
            sa.Column("sql", sa.Text(), nullable=True),
            sa.Column("row_count", sa.Integer(), nullable=True),
            sa.Column("error", sa.Text(), nullable=True),
            sa.Column("created_at", _TZ, server_default=sa.func.now(), nullable=True),
        )
    indices = {
        CONVERSACIONES: [(f"ix_{CONVERSACIONES}_organization_id", ["organization_id"]),
                         (f"ix_{CONVERSACIONES}_user_id", ["user_id"]),
                         (f"ix_{CONVERSACIONES}_updated_at", ["updated_at"]),
                         (f"ix_{CONVERSACIONES}_org_user", ["organization_id", "user_id", "updated_at"])],
        TURNOS: [(f"ix_{TURNOS}_organization_id", ["organization_id"]),
                 (f"ix_{TURNOS}_conversation_id", ["conversation_id"])],
    }
    for tabla, lista in indices.items():
        existentes = _indices(tabla)
        for nombre, cols in lista:
            if nombre not in existentes:
                op.create_index(nombre, tabla, cols)


def _ask_downgrade() -> None:
    hay = _tablas()
    for tabla in (TURNOS, CONVERSACIONES):
        if tabla in hay:
            op.drop_table(tabla)


def upgrade() -> None:
    _feedback_upgrade()
    _huecos_upgrade()
    _ask_upgrade()
    logger.info("207: conectores y motor semántico listos")


def downgrade() -> None:
    _ask_downgrade()
    _huecos_downgrade()
    _feedback_downgrade()
