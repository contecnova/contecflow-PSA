"""Índice único parcial que impide reconocer dos veces el mismo periodo.

Auditoría 2026-08. `run_monthly_recognition` no era idempotente: no comprobaba si
ya existía asiento para (contrato, periodo), así que un reintento de Celery, un
disparo manual del lote o —hasta el arreglo del hallazgo 12— varios `beat`
simultáneos reconocían otra vez los mismos ingresos.

La guarda de código (`revenue_service._ya_reconocido`) cubre el caso secuencial,
pero no la concurrencia: dos transacciones pueden leer «no hay asiento» y ambas
insertar. Sólo un índice único lo impide de verdad.

── Por qué PARCIAL y no un único normal ──────────────────────────────────────
Un único sobre (contrato, año, mes, tipo) habría roto dos caminos legítimos:

  · el reconocimiento por HITOS crea varios asientos `recognized` del mismo
    contrato y periodo, uno por obligación satisfecha;
  · una REVERSIÓN comparte periodo con el asiento que revierte.

Las filas que genera el lote mensual son exactamente las que llevan
`milestone_id` NULL y tipo `recognized`, así que el índice se limita a ese
conjunto. PostgreSQL y SQLite (≥ 3.8) admiten índices parciales, que es el motivo
de poder resolverlo así en lugar de con una tabla auxiliar de control.

── Sobre los datos existentes ────────────────────────────────────────────────
Si un histórico real ya tiene duplicados, esta revisión ABORTA con el detalle en
vez de borrarlos. `RevenueEntry` está documentado como registro contable
inmutable —«nunca se elimina; las correcciones crean una entrada de tipo
reversal»— así que resolverlo silenciosamente sería falsificar contabilidad. La
corrección correcta es que alguien emita las reversiones y vuelva a aplicar.

En la práctica no debería haber duplicados: la vía `over_time`/`consumption`
reconocía siempre 0 € por leer un campo inexistente (ver
`revenue_service._recognize_over_time`) y la vía `straight_line` ya tenía su
propia guarda. Pero eso es una deducción, no una garantía sobre una base ajena,
y de ahí la comprobación.
"""
from typing import Union

from alembic import op
from sqlalchemy import text

revision: str = "091_rev_entries_unique_batch_period"
down_revision: Union[str, None] = "090_client_timezone"
branch_labels = None
depends_on = None

INDICE = "uq_rev_entries_lote_periodo"

# El conjunto de filas del lote mensual, y sólo ése.
FILTRO = "milestone_id IS NULL AND entry_type = 'recognized'"

_SQL_DUPLICADOS = f"""
SELECT rev_contract_id, period_year, period_month, COUNT(*) AS n
  FROM rev_entries
 WHERE {FILTRO}
 GROUP BY rev_contract_id, period_year, period_month
HAVING COUNT(*) > 1
"""


def upgrade() -> None:
    bind = op.get_bind()

    duplicados = bind.execute(text(_SQL_DUPLICADOS)).fetchall()
    if duplicados:
        detalle = "\n".join(
            f"  contrato {c} · periodo {y}-{m:02d} · {n} asientos"
            for c, y, m, n in duplicados
        )
        raise RuntimeError(
            "No se puede crear el índice único: ya hay periodos con más de un "
            "asiento de reconocimiento del lote mensual. Son ingresos "
            "contabilizados dos veces y hay que corregirlos emitiendo las "
            "reversiones correspondientes (POST /revenue/entries/{id}/reverse), "
            "NO borrando filas: el registro es inmutable por diseño.\n\n"
            f"Periodos afectados:\n{detalle}\n"
        )

    # `op.create_index` con *_where genera el índice parcial en ambos motores.
    op.create_index(
        INDICE,
        "rev_entries",
        ["rev_contract_id", "period_year", "period_month"],
        unique=True,
        sqlite_where=text(FILTRO),
        postgresql_where=text(FILTRO),
    )


def downgrade() -> None:
    op.drop_index(INDICE, table_name="rev_entries")
