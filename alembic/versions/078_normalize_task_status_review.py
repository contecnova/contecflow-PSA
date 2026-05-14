"""normalize TaskStatus.review legacy → in_review

Audit #60 — el enum `TaskStatus` mantenía dos valores semánticamente equivalentes:
    in_review = "in_review"   # nombre canónico
    review    = "review"      # legacy alias kept for backward compat

Mantener ambos genera divergencia: UIs distintas usan uno u otro, los servicios
de progreso (okr_service, profitability_service) sólo cuentan `review` (no
`in_review`), y nuevos endpoints pesan unos vs otros de forma inconsistente.

Esta migración consolida toda fila con `status='review'` a `status='in_review'`
para que el alias legacy pueda eliminarse del enum en el mismo commit.

Downgrade: revierte filas `in_review` → `review` (reversible para safety,
aunque después de eliminar el alias del enum no es totalmente reversible sin
re-añadir el valor).

Revision ID: 078_normalize_task_status_review
Revises: 077_soft_delete_constraints
Create Date: 2026-05-14
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "078_normalize_task_status_review"
down_revision = "077_soft_delete_constraints"
branch_labels = None
depends_on = None


def _table_exists(conn, table_name: str) -> bool:
    insp = sa.inspect(conn)
    return table_name in insp.get_table_names()


def upgrade() -> None:
    conn = op.get_bind()
    if not _table_exists(conn, "tasks"):
        return

    # Count antes de actualizar (solo informativo en logs).
    result = conn.execute(
        sa.text("SELECT COUNT(*) FROM tasks WHERE status = 'review'")
    ).scalar()
    if result:
        print(f"[078_normalize_task_status_review] Normalizando {result} fila(s) "
              f"'review' → 'in_review'.")

    conn.execute(
        sa.text("UPDATE tasks SET status = 'in_review' WHERE status = 'review'")
    )


def downgrade() -> None:
    conn = op.get_bind()
    if not _table_exists(conn, "tasks"):
        return

    # Reversible para safety. Ten en cuenta que tras eliminar el valor `review`
    # del enum en el código, esta reversión requeriría re-añadirlo manualmente.
    conn.execute(
        sa.text("UPDATE tasks SET status = 'review' WHERE status = 'in_review'")
    )
