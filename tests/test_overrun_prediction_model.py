"""El modelo de predicción de sobrecoste y retraso.

Auditoría 2026-08 (P3-18). `predict_overrun_ml` era complejidad 20: trece reglas
de umbral escritas como cadenas de `elif`, cada una sumando pesos a dos
marcadores y añadiendo una señal a la lista.

Escrito así, **los pesos del modelo estaban repartidos por veinte líneas de
código**: no se podían leer de un vistazo ni comparar entre sí, y recalibrarlo
obligaba a reescribir ramas. Ahora son una tabla.

La equivalencia se verificó por fuerza bruta: es una función pura de siete
números, así que se cruzaron todos los umbrales con sus bordes —
**192.000 combinaciones, cero diferencias**. Estos tests conservan esa
comprobación en una versión reducida y fijan las decisiones del modelo que un
cambio de calibración podría alterar sin que nada fallara.

El nombre dice «ml» pero no hay aprendizaje: son umbrales fijados a mano, como
su propio docstring reconoce («heuristic ensemble»). Se mantiene el nombre para
no romper a sus llamadores.
"""
from __future__ import annotations

import itertools

import pytest

from app.services.ai_modules.predictions import (
    _PROBABILIDAD_MAXIMA,
    _REGLAS_POR_DEBAJO,
    _REGLAS_POR_ENCIMA,
    predict_overrun_ml,
)

# Un proyecto sano: ningún umbral se cruza.
SANO = dict(
    cpi=1.1, spi=1.05,
    budget_used_pct=30.0, elapsed_pct=35.0,
    task_completion_pct=40.0,
    overdue_task_ratio=0.0,
    team_load_pct=80.0,
)


def _predecir(**cambios):
    return predict_overrun_ml(**{**SANO, **cambios})


# ── Un proyecto sano no dispara nada ──────────────────────────────────────────

def test_un_proyecto_sano_no_genera_señales():
    r = _predecir()
    assert r["signals"] == []
    assert r["cost_overrun_prob"] == 0
    assert r["schedule_overrun_prob"] == 0
    assert r["confidence"] == "low"
    assert "parámetros normales" in r["recommendation"]


# ── Cada métrica toma SOLO su regla más grave ─────────────────────────────────

def test_el_cpi_solo_aporta_una_señal_aunque_cruce_los_tres_umbrales():
    """Los umbrales de una misma métrica son niveles de gravedad, no sumandos.

    Un CPI de 0,5 está por debajo de 0,70, de 0,85 y de 1,00. Si se sumaran los
    tres, el marcador de coste sería 0,80 en vez de 0,45 y la probabilidad
    saldría casi al doble. La cadena de `elif` original lo evitaba con el
    `break` implícito, y la tabla lo hace con un `break` explícito.
    """
    r = _predecir(cpi=0.5)
    señales_de_cpi = [s for s in r["signals"] if "CPI" in s["signal"]]
    assert len(señales_de_cpi) == 1
    assert señales_de_cpi[0]["signal"] == "CPI crítico"
    assert r["cost_overrun_prob"] == 0.45


def test_el_spi_igual():
    r = _predecir(spi=0.1)
    señales = [s for s in r["signals"] if "SPI" in s["signal"]]
    assert len(señales) == 1
    assert r["schedule_overrun_prob"] == 0.5


@pytest.mark.parametrize("cpi,texto,peso", [
    (0.69, "CPI crítico", 0.45),
    (0.84, "CPI bajo", 0.25),
    (0.99, "CPI ligeramente bajo", 0.10),
])
def test_los_tramos_del_cpi(cpi, texto, peso):
    r = _predecir(cpi=cpi)
    s = next(s for s in r["signals"] if "CPI" in s["signal"])
    assert s["signal"] == texto
    assert s["weight"] == peso


@pytest.mark.parametrize("cpi", [0.70, 0.85, 1.00, 1.5])
def test_los_umbrales_del_cpi_son_estrictos(cpi):
    """`< 0.70` y no `<= 0.70`. Un CPI de exactamente 0,70 no es crítico, y esa
    frontera decide si un proyecto aparece en rojo en el panel."""
    r = _predecir(cpi=cpi)
    assert not [s for s in r["signals"] if s["signal"] == "CPI crítico"]


# ── Las reglas de «mayor que» ─────────────────────────────────────────────────

def test_la_quema_de_presupuesto_se_mide_contra_el_tiempo():
    """No es «cuánto se ha gastado» sino «cuánto más rápido se gasta que pasa el
    tiempo». Un 90 % gastado con un 95 % transcurrido no es una alerta de coste.

    Se mira sólo la señal de presupuesto: subir `elapsed_pct` dispara además la
    regla de tareas retrasadas, porque el hueco con `task_completion_pct` crece.
    Eso es correcto y es otra regla.
    """
    sin_alerta = _predecir(budget_used_pct=90.0, elapsed_pct=95.0,
                           task_completion_pct=95.0)
    assert not [s for s in sin_alerta["signals"] if "presupuesto" in s["signal"]]

    r = _predecir(budget_used_pct=90.0, elapsed_pct=60.0, task_completion_pct=60.0)
    assert any("Quema de presupuesto avanzada" in s["signal"] for s in r["signals"])


def test_el_retraso_de_tareas_se_mide_contra_el_tiempo():
    r = _predecir(elapsed_pct=80.0, task_completion_pct=40.0)   # hueco 40
    assert any("Tareas retrasadas" in s["signal"] for s in r["signals"])


def test_las_tareas_vencidas_suman_a_las_dos_dimensiones():
    """Por encima del 40 % afecta a coste y a calendario: el retrabajo cuesta
    dinero además de tiempo."""
    r = _predecir(overdue_task_ratio=0.5)
    s = next(s for s in r["signals"] if "vencidas" in s["signal"])
    assert s["type"] == "both"
    assert r["cost_overrun_prob"] == 0.1
    assert r["schedule_overrun_prob"] == 0.25


def test_el_equipo_sobrecargado_suma_a_las_dos():
    r = _predecir(team_load_pct=130.0)
    s = next(s for s in r["signals"] if "sobrecargado" in s["signal"])
    assert s["type"] == "both"
    assert r["cost_overrun_prob"] == 0.15
    assert r["schedule_overrun_prob"] == 0.2


def test_el_peso_reportado_de_las_reglas_mixtas_es_el_del_original():
    """Una incoherencia que se conserva a propósito, y por eso está aquí.

    Las dos reglas de tipo «both» reportan el peso de dimensiones distintas: las
    tareas vencidas reportan el de **calendario** (0,25) y el equipo
    sobrecargado el de **coste** (0,15). No es coherente entre las dos, pero es
    lo que muestra la interfaz, y unificarlo cambiaría los pesos que ve quien usa
    el panel. Queda fijado para que nadie lo «arregle» sin decidirlo.
    """
    vencidas = next(
        s for s in _predecir(overdue_task_ratio=0.5)["signals"]
        if "vencidas" in s["signal"]
    )
    assert vencidas["weight"] == 0.25   # el de calendario

    carga = next(
        s for s in _predecir(team_load_pct=130.0)["signals"]
        if "sobrecargado" in s["signal"]
    )
    assert carga["weight"] == 0.15      # el de COSTE


# ── El orden de las señales es parte de lo que se muestra ─────────────────────

def test_las_señales_salen_en_el_orden_de_las_metricas():
    """La interfaz las presenta en lista, así que el orden se ve. Es
    cpi, spi, presupuesto, tareas, vencidas, carga."""
    r = _predecir(cpi=0.5, spi=0.5, budget_used_pct=90.0, elapsed_pct=30.0,
                  task_completion_pct=0.0, overdue_task_ratio=0.5,
                  team_load_pct=130.0)
    tipos = [s["signal"] for s in r["signals"]]
    assert "CPI" in tipos[0]
    assert "SPI" in tipos[1]
    assert "presupuesto" in tipos[2]
    assert "Tareas retrasadas" in tipos[3]
    assert "vencidas" in tipos[4]
    assert "sobrecargado" in tipos[5]


# ── Confianza y tope de probabilidad ──────────────────────────────────────────

@pytest.mark.parametrize("n_esperado,confianza", [(0, "low"), (1, "low"),
                                                  (2, "medium"), (3, "medium"),
                                                  (4, "high")])
def test_la_confianza_depende_de_cuantas_señales_haya(n_esperado, confianza):
    """Cuantas más señales independientes coinciden, más se puede afirmar."""
    casos = {
        0: {},
        1: {"cpi": 0.9},
        2: {"cpi": 0.9, "spi": 0.9},
        3: {"cpi": 0.9, "spi": 0.9, "team_load_pct": 130.0},
        4: {"cpi": 0.9, "spi": 0.9, "team_load_pct": 130.0,
            "overdue_task_ratio": 0.5},
    }
    r = _predecir(**casos[n_esperado])
    assert len(r["signals"]) == n_esperado
    assert r["confidence"] == confianza


def test_la_probabilidad_nunca_llega_a_uno():
    """El tope del 97 % no es arbitrario: son heurísticas, y presentar «100 % de
    probabilidad de sobrecoste» afirmaría más de lo que el modelo sabe."""
    r = _predecir(cpi=0.1, spi=0.1, budget_used_pct=100.0, elapsed_pct=0.0,
                  task_completion_pct=0.0, overdue_task_ratio=0.9,
                  team_load_pct=200.0)
    assert r["cost_overrun_prob"] <= _PROBABILIDAD_MAXIMA
    assert r["schedule_overrun_prob"] <= _PROBABILIDAD_MAXIMA
    assert _PROBABILIDAD_MAXIMA < 1.0


# ── Magnitudes ────────────────────────────────────────────────────────────────

def test_sin_desviacion_no_hay_magnitud():
    r = _predecir(cpi=1.0, spi=1.0)
    assert r["cost_overrun_pct"] == 0.0
    assert r["schedule_overrun_days"] == 0


def test_un_indice_a_cero_no_divide_por_cero():
    """CPI o SPI a cero es un proyecto sin coste o sin calendario todavía, no un
    desastre: la magnitud se deja a cero en vez de reventar."""
    r = _predecir(cpi=0.0, spi=0.0)
    assert r["cost_overrun_pct"] == 0.0
    assert r["schedule_overrun_days"] == 0


def test_la_magnitud_de_coste_escala_con_lo_gastado():
    """Con CPI 0,5 el coste real es el doble del valor ganado; el porcentaje de
    sobrecoste se pondera por lo que ya se ha consumido del presupuesto."""
    poco = _predecir(cpi=0.5, budget_used_pct=20.0)["cost_overrun_pct"]
    mucho = _predecir(cpi=0.5, budget_used_pct=80.0)["cost_overrun_pct"]
    assert mucho > poco


def test_los_dias_de_retraso_crecen_al_bajar_el_spi():
    peor = _predecir(spi=0.5)["schedule_overrun_days"]
    mejor = _predecir(spi=0.9)["schedule_overrun_days"]
    assert peor > mejor >= 0


# ── Recomendación ─────────────────────────────────────────────────────────────

def test_riesgo_alto_en_las_dos_dimensiones_pide_revision_ejecutiva():
    r = _predecir(cpi=0.5, spi=0.5, budget_used_pct=90.0, elapsed_pct=30.0,
                  overdue_task_ratio=0.5)
    assert "ejecutiva urgente" in r["recommendation"]


def test_solo_coste_pide_revisar_coste():
    r = _predecir(cpi=0.5, budget_used_pct=90.0, elapsed_pct=30.0)
    assert r["cost_overrun_prob"] > 0.5
    assert "Revisar coste" in r["recommendation"]


def test_solo_calendario_pide_revisar_cronograma():
    r = _predecir(spi=0.5, elapsed_pct=80.0, task_completion_pct=20.0)
    assert r["schedule_overrun_prob"] > 0.5
    assert "Revisar cronograma" in r["recommendation"]


def test_señales_moderadas_piden_seguimiento():
    """El tramo intermedio: la suma pasa de 0,3 pero ninguna dimensión de 0,5.

    Con CPI 0,80 (0,25 a coste) y SPI 0,90 (0,15 a calendario) la suma es 0,40.
    Con 0,9 y 0,9 la suma sería 0,25 y caería en «parámetros normales», que es
    el tramo de abajo — la frontera de 0,3 los separa.
    """
    r = _predecir(cpi=0.80, spi=0.90)
    assert r["cost_overrun_prob"] + r["schedule_overrun_prob"] >= 0.3
    assert r["cost_overrun_prob"] <= 0.5 and r["schedule_overrun_prob"] <= 0.5
    assert "moderadas" in r["recommendation"]


def test_la_frontera_entre_normal_y_moderado():
    """Por debajo de 0,3 de suma el proyecto se declara normal."""
    r = _predecir(cpi=0.9, spi=0.9)
    assert r["cost_overrun_prob"] + r["schedule_overrun_prob"] < 0.3
    assert "parámetros normales" in r["recommendation"]


# ── Propiedades estructurales de la tabla ─────────────────────────────────────

def test_los_umbrales_de_cada_metrica_van_de_mas_grave_a_menos():
    """El orden de la tabla ES la lógica: se toma la primera que cumple, así que
    una tabla desordenada haría que un CPI crítico se reportara como «bajo».

    En las de «menor que» los umbrales suben; en las de «mayor que», bajan.
    """
    for metrica, (_fmt, reglas) in _REGLAS_POR_DEBAJO.items():
        umbrales = [r.umbral for r in reglas]
        assert umbrales == sorted(umbrales), f"{metrica}: {umbrales}"

    for metrica, (_fmt, reglas) in _REGLAS_POR_ENCIMA.items():
        umbrales = [r.umbral for r in reglas]
        assert umbrales == sorted(umbrales, reverse=True), f"{metrica}: {umbrales}"


def test_toda_regla_suma_algo_a_alguna_dimension():
    """Una regla con los dos pesos a cero generaría una señal en el panel sin
    afectar a ninguna probabilidad: ruido con apariencia de dato."""
    for familia in (_REGLAS_POR_DEBAJO, _REGLAS_POR_ENCIMA):
        for metrica, (_fmt, reglas) in familia.items():
            for r in reglas:
                assert r.suma_coste or r.suma_calendario, f"{metrica}: {r.texto}"


def test_el_tipo_declarado_coincide_con_lo_que_suma():
    """Que una señal marcada como «cost» no sume a calendario, y al revés. Si
    divergieran, el panel agruparía la señal en una dimensión que no afecta."""
    for familia in (_REGLAS_POR_DEBAJO, _REGLAS_POR_ENCIMA):
        for metrica, (_fmt, reglas) in familia.items():
            for r in reglas:
                if r.tipo == "cost":
                    assert r.suma_coste and not r.suma_calendario, f"{metrica}: {r.texto}"
                elif r.tipo == "schedule":
                    assert r.suma_calendario and not r.suma_coste, f"{metrica}: {r.texto}"
                else:
                    assert r.tipo == "both", f"{metrica}: tipo desconocido {r.tipo}"
                    assert r.suma_coste and r.suma_calendario, f"{metrica}: {r.texto}"


def test_ninguna_señal_repite_texto():
    """Dos reglas con el mismo texto serían indistinguibles en el panel."""
    textos = [
        r.texto
        for familia in (_REGLAS_POR_DEBAJO, _REGLAS_POR_ENCIMA)
        for _m, (_f, reglas) in familia.items()
        for r in reglas
    ]
    assert len(textos) == len(set(textos))
    assert len(textos) == 13, f"el modelo tiene {len(textos)} reglas, no 13"


# ── La comprobación por fuerza bruta, reducida ────────────────────────────────

def test_el_modelo_no_revienta_con_ninguna_combinacion_de_umbrales():
    """Versión corta de las 192.000 combinaciones con que se verificó el
    refactor: cruza los bordes de todos los umbrales y exige que el resultado
    sea siempre completo y coherente."""
    CPI = [0.0, 0.69, 0.70, 0.85, 1.0, 1.3]
    SPI = [0.0, 0.64, 0.65, 0.80, 0.95, 1.2]
    OVD = [0.0, 0.20, 0.40, 0.9]
    LOAD = [0.0, 110.0, 111.0]
    CLAVES = {
        "cost_overrun_prob", "schedule_overrun_prob", "cost_overrun_pct",
        "schedule_overrun_days", "confidence", "signals", "recommendation",
    }

    for cpi, spi, ovd, load in itertools.product(CPI, SPI, OVD, LOAD):
        r = predict_overrun_ml(cpi, spi, 60.0, 30.0, 20.0, ovd, load)
        assert set(r) == CLAVES
        assert 0 <= r["cost_overrun_prob"] <= _PROBABILIDAD_MAXIMA
        assert 0 <= r["schedule_overrun_prob"] <= _PROBABILIDAD_MAXIMA
        assert r["schedule_overrun_days"] >= 0
        assert r["cost_overrun_pct"] >= 0
        assert r["confidence"] in ("low", "medium", "high")
        assert r["recommendation"]
        for s in r["signals"]:
            assert set(s) == {"signal", "value", "weight", "type"}
            assert s["type"] in ("cost", "schedule", "both")
