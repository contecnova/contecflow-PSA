"""Planificador (rev. 173): calendario laboral y camino crítico, sin base de datos.

Las fechas son fijas y conocidas: el lunes 2 de noviembre de 2026 es día 1.
"""
from __future__ import annotations

from datetime import date

import pytest

from app.services.planificador.calendario import Calendario, interpretar_dias_laborables
from app.services.planificador.cpm import TareaPlan, Vinculo, calcular, fin_maximo, inicio_minimo

LUNES = date(2026, 11, 2)
L_V = frozenset({1, 2, 3, 4, 5})


def cal(**kw) -> Calendario:
    return Calendario(dias_laborables=L_V, **kw)


# ── Calendario ───────────────────────────────────────────────────────────────

def test_interpretar_dias_laborables():
    assert interpretar_dias_laborables("1,2,3,4,5") == L_V
    assert interpretar_dias_laborables(" 1; 3 ;9;x") == frozenset({1, 3})
    with pytest.raises(ValueError):
        interpretar_dias_laborables("8,0")


def test_un_calendario_sin_dias_no_se_puede_crear():
    with pytest.raises(ValueError):
        Calendario(dias_laborables=frozenset())


def test_aritmetica_salta_fin_de_semana_y_festivos():
    festivo = date(2026, 11, 4)  # miércoles
    c = cal(no_laborables=frozenset({festivo}))
    assert c.adelante(LUNES, 2) == date(2026, 11, 5)          # mar, (mié festivo), jue
    assert c.atras(date(2026, 11, 9), 1) == date(2026, 11, 6)  # lunes − 1 = viernes
    assert c.siguiente(date(2026, 11, 7)) == date(2026, 11, 9)  # sábado → lunes
    assert c.laborables_en(LUNES, date(2026, 11, 8)) == 4       # semana con festivo
    assert c.distancia(LUNES, date(2026, 11, 9)) == 4
    assert c.distancia(date(2026, 11, 9), LUNES) == -4
    assert c.fin_desde(LUNES, 5) == date(2026, 11, 9)
    assert c.inicio_desde(date(2026, 11, 9), 5) == LUNES


def test_con_ausencias_quita_dias_de_la_persona():
    c = cal().con_ausencias([date(2026, 11, 3)], horas_por_dia=6)
    assert not c.es_laborable(date(2026, 11, 3))
    assert c.horas_por_dia == 6


# ── Un vínculo ───────────────────────────────────────────────────────────────

@pytest.mark.parametrize("tipo,desfase,esperado", [
    ("FS", 0, date(2026, 11, 5)),   # pred lun-mié → empieza jueves
    ("FS", 2, date(2026, 11, 9)),   # + 2 laborables → lunes
    ("FS", -1, date(2026, 11, 4)),  # solape de un día
    ("SS", 1, date(2026, 11, 3)),   # empieza un día después del inicio
    ("FF", 0, date(2026, 11, 3)),   # sucesora de 2 días acaba el miércoles
    ("SF", 0, date(2026, 10, 29)),  # sucesora de 2 días acaba el viernes anterior
])
def test_inicio_minimo_por_tipo(tipo, desfase, esperado):
    c = cal()
    assert inicio_minimo(tipo, desfase, LUNES, date(2026, 11, 4), c, c, 2) == esperado


def test_fin_maximo_es_el_inverso_de_fs():
    c = cal()
    # La sucesora empieza el jueves 5: la predecesora puede acabar el miércoles 4.
    assert fin_maximo("FS", 0, date(2026, 11, 5), date(2026, 11, 6), c, c, 3) == date(2026, 11, 4)


# ── El cálculo ───────────────────────────────────────────────────────────────

def _t(tid, d, c=None, **kw):
    return TareaPlan(id=tid, duracion=d, calendario=c or cal(), **kw)


def test_camino_critico_y_holguras():
    """A(3) → B(2) → D(1); A → C(1) → D. C tiene 1 día de holgura total y libre."""
    tareas = [_t("A", 3), _t("B", 2), _t("C", 1), _t("D", 1)]
    vinculos = [Vinculo("A", "B"), Vinculo("A", "C"), Vinculo("B", "D"), Vinculo("C", "D")]
    r = calcular(tareas, vinculos, LUNES, cal())
    assert r.tareas["A"].inicio_temprano == LUNES
    assert r.tareas["B"].inicio_temprano == date(2026, 11, 5)
    assert r.tareas["D"].inicio_temprano == date(2026, 11, 9)
    assert r.fin_proyecto == date(2026, 11, 9)
    assert r.tareas["C"].holgura_total == 1
    assert r.tareas["C"].holgura_libre == 1
    assert not r.tareas["C"].critica
    assert r.camino_critico == ["A", "B", "D"]


def test_ss_con_desfase_y_ff():
    tareas = [_t("A", 5), _t("B", 3), _t("C", 2)]
    vinculos = [Vinculo("A", "B", "SS", 2), Vinculo("A", "C", "FF", 0)]
    r = calcular(tareas, vinculos, LUNES, cal())
    assert r.tareas["B"].inicio_temprano == date(2026, 11, 4)
    assert r.tareas["C"].fin_temprano == r.tareas["A"].fin_temprano


def test_restriccion_no_empezar_antes_de():
    r = calcular([_t("A", 2, restriccion="snet", fecha_restriccion=date(2026, 11, 7))], [], LUNES, cal())
    assert r.tareas["A"].inicio_temprano == date(2026, 11, 9)   # sábado → lunes


def test_restriccion_no_terminar_despues_da_holgura_negativa():
    """Si el plan no llega a la fecha, la holgura es negativa y la tarea crítica."""
    tareas = [_t("A", 5), _t("B", 3, restriccion="fnlt", fecha_restriccion=date(2026, 11, 10))]
    r = calcular(tareas, [Vinculo("A", "B")], LUNES, cal())
    assert r.tareas["B"].fin_temprano == date(2026, 11, 11)
    assert r.tareas["B"].holgura_total == -1
    assert r.tareas["B"].critica and r.tareas["A"].critica


def test_calendario_de_la_persona_alarga_su_tarea():
    persona = cal().con_ausencias([date(2026, 11, 3)])
    r = calcular([_t("A", 2, persona)], [], LUNES, cal())
    assert r.tareas["A"].fin_temprano == date(2026, 11, 4)


def test_un_ciclo_no_rompe_el_calculo():
    tareas = [_t("A", 1), _t("B", 1)]
    r = calcular(tareas, [Vinculo("A", "B"), Vinculo("B", "A")], LUNES, cal())
    assert set(r.ciclo) == {"A", "B"}
    assert set(r.tareas) == {"A", "B"}


def test_una_tarea_terminada_queda_fija():
    t = _t("A", 3, fijada=True, inicio_real=date(2026, 10, 26), fin_real=date(2026, 10, 27))
    r = calcular([t, _t("B", 1)], [Vinculo("A", "B")], LUNES, cal())
    assert r.tareas["A"].inicio_temprano == date(2026, 10, 26)
    assert not r.tareas["A"].critica
    assert r.tareas["B"].inicio_temprano == LUNES
