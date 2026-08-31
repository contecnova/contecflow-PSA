"""Las métricas mensuales agrupan en la zona de quien mira, no en UTC.

Auditoría 2026-08 (P2-14), último fleco. Tres métricas mensuales agrupaban con
`extract("month", columna)` sobre columnas de fecha-HORA que guardan UTC:

  · `SLABreachLog.breached_at`  — incumplimientos de SLA por mes
  · `ClientNPS.created_at`      — NPS medio por mes
  · `Task.completed_at`         — tareas completadas por mes

Así se agrupaba por el mes en que la fila está ALMACENADA, no por el mes en que
ocurrió para quien mira el informe. Las filas de las primeras o últimas horas de
un mes caían en el mes contiguo.

El traspaso decía que faltaba enganchar `period_bounds_for_client` en
`billing_reports_service`. **Ese consejo era incorrecto** y se comprobó columna
por columna: los cortes de facturación operan sobre columnas `Date`
—`Invoice.issue_date`, `period_from`, `period_to`, `Imputation.date`—, que son
días de calendario sin instante. No tienen zona que aplicar y su `extract` ya era
correcto; usar un ayudante de límites *datetime* ahí habría sido un error. Lo que
sí estaba mal eran estas tres, y son las que se han arreglado.
"""
from __future__ import annotations

import pathlib
from datetime import datetime

import pytest

from app.core.timeutil import UTC, month_key_in, month_label_in, resolve_zone, using_zone
from app.services.metrics._monthly import agrupar_por_mes, serie_de_cuentas


# ── El ayudante de zona ───────────────────────────────────────────────────────

def test_el_mes_de_un_instante_depende_de_la_zona():
    """El desfase, en dos aserciones.

    Almacenado: 22:30 UTC del 31 de julio. En UTC sigue siendo julio; en Madrid
    (UTC+2 en verano) son ya las 00:30 del 1 de agosto.
    """
    madrid = resolve_zone("Europe/Madrid")
    instante = datetime(2026, 7, 31, 22, 30, tzinfo=UTC)
    assert month_key_in(instante, UTC) == (2026, 7), "en UTC cae en julio"
    assert month_key_in(instante, madrid) == (2026, 8), "para Madrid ya es agosto"


def test_el_desfase_tambien_ocurre_hacia_atras():
    """Una organización al oeste de UTC ve el mes anterior donde UTC ve el nuevo."""
    mexico = resolve_zone("America/Mexico_City")  # UTC-6
    # 01:00 del 1 de agosto UTC = 19:00 del 31 de JULIO en México.
    instante = datetime(2026, 8, 1, 1, 0, tzinfo=UTC)
    assert month_key_in(instante, UTC) == (2026, 8)
    assert month_key_in(instante, mexico) == (2026, 7)


def test_un_instante_sin_zona_se_interpreta_como_utc():
    """Es lo que los datos almacenados son de verdad; ver la cabecera de timeutil."""
    assert month_key_in(datetime(2026, 7, 15, 12, 0), UTC) == (2026, 7)


def test_la_etiqueta_usa_el_formato_de_los_informes():
    assert month_label_in(datetime(2026, 3, 9, tzinfo=UTC), UTC) == "2026-03"


def test_month_key_in_rechaza_none():
    """No hay mes al que asignar un instante ausente, y elegir uno lo falsearía."""
    with pytest.raises(ValueError):
        month_key_in(None, UTC)


def test_sin_zona_explicita_usa_la_del_contexto():
    """Así una petición agrupa en el calendario de quien la hizo, sin que cada
    métrica tenga que resolver la zona por su cuenta."""
    instante = datetime(2026, 7, 31, 22, 30, tzinfo=UTC)
    with using_zone(resolve_zone("Europe/Madrid")):
        assert month_key_in(instante) == (2026, 8)
    with using_zone(UTC):
        assert month_key_in(instante) == (2026, 7)


# ── El agrupador compartido ───────────────────────────────────────────────────

def _fila(iso, valor=None):
    return (datetime.fromisoformat(iso), valor)


def test_agrupar_cuenta_filas_cuando_no_se_da_valor():
    filas = [
        _fila("2026-07-05T10:00+00:00"),
        _fila("2026-07-20T10:00+00:00"),
        _fila("2026-08-02T10:00+00:00"),
    ]
    cubos = agrupar_por_mes(filas, lambda r: r[0], zone=UTC)
    assert cubos == {"2026-07": (2.0, 2), "2026-08": (1.0, 1)}


def test_agrupar_acumula_el_valor_cuando_se_da():
    filas = [_fila("2026-07-05T10:00+00:00", 8), _fila("2026-07-20T10:00+00:00", 10)]
    cubos = agrupar_por_mes(filas, lambda r: r[0], valor=lambda r: r[1], zone=UTC)
    # Suma y número de filas: la media la calcula quien la necesita.
    assert cubos == {"2026-07": (18.0, 2)}


def test_agrupar_descarta_las_filas_sin_instante():
    """Una fila sin fecha no tiene mes; colocarla en uno inventado falsearía la
    serie, así que se descarta en lugar de contarse."""
    filas = [_fila("2026-07-05T10:00+00:00"), (None, None)]
    cubos = agrupar_por_mes(filas, lambda r: r[0], zone=UTC)
    assert cubos == {"2026-07": (1.0, 1)}


def test_el_agrupador_mueve_la_fila_de_frontera_al_mes_correcto():
    """El fallo completo, en una sola prueba.

    Una incidencia registrada a las 22:30 UTC del 31 de julio ocurrió ya en
    agosto para una organización en Madrid.
    """
    filas = [_fila("2026-07-31T22:30+00:00")]
    assert agrupar_por_mes(filas, lambda r: r[0], zone=UTC) == {"2026-07": (1.0, 1)}
    assert agrupar_por_mes(
        filas, lambda r: r[0], zone=resolve_zone("Europe/Madrid")
    ) == {"2026-08": (1.0, 1)}


def test_la_serie_sale_ordenada_por_mes():
    cubos = {"2026-08": (1.0, 1), "2026-07": (2.0, 2), "2025-12": (3.0, 3)}
    assert [f["label"] for f in serie_de_cuentas(cubos)] == [
        "2025-12", "2026-07", "2026-08",
    ]
    assert [f["value"] for f in serie_de_cuentas(cubos)] == [3, 2, 1]


def test_la_serie_de_cuentas_devuelve_enteros():
    """Un conteo con decimales en una gráfica delata que se ha colado una suma."""
    serie = serie_de_cuentas({"2026-07": (2.0, 2)})
    assert isinstance(serie[0]["value"], int)


# ── Que las tres métricas ya no usan extract sobre fecha-hora ─────────────────

@pytest.mark.parametrize(
    "fichero,columna",
    [
        ("app/services/metrics/invoices_alerts.py", "breached_at"),
        ("app/services/metrics/okr_nps.py", "created_at"),
        ("app/services/metrics/sprints_tasks.py", "completed_at"),
    ],
)
def test_ninguna_de_las_tres_agrupa_con_extract_sobre_fecha_hora(fichero, columna):
    """Impide la regresión: volver a `extract` reintroduce el desfase en silencio,
    porque la gráfica sigue saliendo y sólo cambian los valores de frontera."""
    raiz = pathlib.Path(__file__).resolve().parent.parent
    texto = (raiz / fichero).read_text(encoding="utf-8", errors="replace")
    culpables = [
        linea.strip()
        for linea in texto.split("\n")
        if "extract(" in linea
        and columna in linea
        and not linea.lstrip().startswith("#")
    ]
    assert not culpables, (
        f"{fichero} vuelve a agrupar {columna} con extract: {culpables}"
    )


def test_las_columnas_date_siguen_sin_tocarse():
    """Contra-test: las otras métricas mensuales NO estaban afectadas.

    `Invoice.issue_date`, `Timesheet.week_start`, `Expense.expense_date` e
    `Imputation.date` son `Date` — días de calendario sin instante. Aplicarles una
    conversión de zona sería introducir un error donde no había ninguno.
    """
    from app.models.billing_reports import Invoice
    from app.models.expenses import Expense
    from app.models.financial import Timesheet
    from app.models.imputation import Imputation

    for modelo, col in (
        (Invoice, "issue_date"),
        (Invoice, "period_from"),
        (Invoice, "period_to"),
        (Timesheet, "week_start"),
        (Expense, "expense_date"),
        (Imputation, "date"),
    ):
        tipo = type(modelo.__table__.columns[col].type).__name__
        assert tipo == "Date", (
            f"{modelo.__name__}.{col} ya no es Date sino {tipo}: si ahora guarda "
            f"un instante, su agrupación mensual SÍ necesita zona"
        )
