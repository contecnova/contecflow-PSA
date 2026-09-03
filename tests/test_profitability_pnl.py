"""La cuenta de resultados de un proyecto: `calc_project_profitability`.

Auditoría 2026-08 (P3-18). Complejidad **23**, devuelve **38 cifras de dinero**
y no tenía un solo test de valor: la cobertura que había era de endpoint —
códigos de estado y casos borde vía HTTP— y no comprobaba ni una cifra.

La estrategia de verificación aquí es en dos capas, y la distinción importa:

  · las cifras **primarias** (horas, coste interno, ingreso, progreso, PV, EV,
    AC) están calculadas a mano a partir de datos fijos;
  · las **derivadas** se comprueban contra las identidades EVM estándar —
    CPI = EV/AC, SPI = EV/PV, EAC = AC + (BAC−EV)/CPI, ETC = EAC−AC,
    VAC = BAC−EAC, CV = EV−AC, SV = EV−PV.

Comprobar una identidad no es una tautología: no reimplementa el cálculo, exige
que el resultado cumpla la definición del indicador. Es exactamente lo que caza
un refactor que intercambie operandos —EV/AC por AC/EV, EV−PV por PV−EV— que es
el error de verdad probable al mover este código, y el que ningún test de código
de estado vería.

Las fechas se fijan **relativas a hoy** (`hoy − 50` / `hoy + 50`) y no absolutas:
`planned_pct` depende del día en que se ejecuta el test, y un literal lo dejaría
verde hoy y rojo dentro de un mes. Es la misma clase de test que deja de
verificar y que esta auditoría encontró cuatro veces.
"""
from __future__ import annotations

import uuid
from datetime import timedelta

import pytest

from app.core import timeutil
from app.models.imputation import Imputation
from app.models.project import Project, ProjectStatus, ProjectType
from app.models.task import Task, TaskStatus
from app.services.profitability_service import calc_project_profitability

# Con estas fechas el calendario va justo por la mitad, sea cuando sea hoy.
DIAS_TRANSCURRIDOS = 50
DIAS_RESTANTES = 50


def _proyecto(db, **campos) -> Project:
    hoy = timeutil.today()
    base = dict(
        id=str(uuid.uuid4()),
        organization_id="1",
        code=f"PNL-{uuid.uuid4().hex[:6].upper()}",
        name="Proyecto P&L",
        project_type=ProjectType.consulting,
        status=ProjectStatus.active,
        currency="EUR",
        is_billable=True,
        client_name="Cliente",
        department="Ingeniería",
        start_date=hoy - timedelta(days=DIAS_TRANSCURRIDOS),
        end_date_planned=hoy + timedelta(days=DIAS_RESTANTES),
    )
    base.update(campos)
    p = Project(**base)
    db.add(p)
    db.commit()
    db.refresh(p)
    return p


def _imputacion(db, proyecto, *, horas, coste, facturable=True):
    db.add(Imputation(
        id=str(uuid.uuid4()),
        organization_id="1",
        project_id=proyecto.id,
        user_id="admin-test-id",
        date=timeutil.today() - timedelta(days=10),
        hours=horas,
        cost_amount=coste,
        is_billable=facturable,
        is_active=True,
    ))


def _tarea(db, proyecto, estado):
    db.add(Task(
        id=str(uuid.uuid4()),
        organization_id="1",
        project_id=proyecto.id,
        code=f"T-{uuid.uuid4().hex[:6].upper()}",
        title=f"Tarea {estado}",
        status=estado,
    ))


# ── Un proyecto por tiempo y materiales, cifra a cifra ────────────────────────

@pytest.fixture
def proyecto_tm(db):
    """T&M con tarifa 100 €/h, presupuesto 10.000 € y 100 h presupuestadas.

    Dos imputaciones de 10 h y 400 € cada una, las dos facturables:
        horas totales    20
        horas facturables 20
        coste interno    800 €

    Cuatro tareas, una por peso distinto:
        done 1,0 + in_review 0,8 + in_progress 0,5 + todo 0,0 = 2,3
        progreso = 2,3 / 4 = 57,5 %
    """
    p = _proyecto(db, billing_rate=100.0, budget_amount=10_000.0, budget_hours=100.0)
    _imputacion(db, p, horas=10.0, coste=400.0)
    _imputacion(db, p, horas=10.0, coste=400.0)
    for estado in (TaskStatus.done, TaskStatus.in_review,
                   TaskStatus.in_progress, TaskStatus.todo):
        _tarea(db, p, estado)
    db.commit()
    db.refresh(p)
    return p


def test_las_horas_y_el_coste_interno(db, proyecto_tm):
    r = calc_project_profitability(proyecto_tm, db)
    assert r["total_hours"] == 20.0
    assert r["billable_hours"] == 20.0
    assert r["internal_cost"] == 800.0
    assert r["avg_cost_rate"] == 40.0            # 800 / 20
    assert r["hours_used_pct"] == 20.0           # 20 de 100 presupuestadas


def test_el_ingreso_sale_de_la_tarifa_por_horas_facturables(db, proyecto_tm):
    r = calc_project_profitability(proyecto_tm, db)
    assert r["billing_revenue"] == 2_000.0       # 100 €/h × 20 h


def test_el_margen_bruto_y_su_porcentaje(db, proyecto_tm):
    r = calc_project_profitability(proyecto_tm, db)
    assert r["gross_margin"] == 1_200.0          # 2.000 − 800
    assert r["margin_pct"] == 60.0               # 1.200 / 2.000


def test_el_presupuesto_consumido(db, proyecto_tm):
    r = calc_project_profitability(proyecto_tm, db)
    assert r["budget_used_pct"] == 8.0           # 800 de 10.000


def test_el_progreso_pondera_por_estado_de_tarea(db, proyecto_tm):
    """(1,0 + 0,8 + 0,5 + 0,0) / 4 = 57,5 %. Los pesos no son iguales a
    propósito: una tarea en revisión está más cerca de acabada que una en curso."""
    r = calc_project_profitability(proyecto_tm, db)
    assert r["progress_pct"] == 57.5


def test_las_tres_cifras_primarias_del_evm(db, proyecto_tm):
    """PV, EV y AC calculadas a mano; de aquí salen todos los indicadores.

    PV = presupuesto × planificado = 10.000 × 50 % = 5.000
    EV = presupuesto × progreso    = 10.000 × 57,5 % = 5.750
    AC = coste real                = 800
    """
    r = calc_project_profitability(proyecto_tm, db)
    assert r["pv"] == 5_000.0
    assert r["ev"] == 5_750.0
    assert r["ac"] == 800.0
    assert r["evm_no_schedule"] is False


def test_los_indicadores_evm_cumplen_sus_identidades(db, proyecto_tm):
    """La capa que caza un intercambio de operandos.

    No reimplementa el cálculo: exige que cada indicador cumpla su definición a
    partir de PV, EV y AC, que ya se han fijado a mano arriba.
    """
    r = calc_project_profitability(proyecto_tm, db)
    pv, ev, ac = r["pv"], r["ev"], r["ac"]
    bac = r["budget_amount"]

    assert r["cpi"] == pytest.approx(round(ev / ac, 3))
    assert r["spi"] == pytest.approx(round(ev / pv, 3))
    assert r["cv"] == pytest.approx(round(ev - ac, 2))
    assert r["sv"] == pytest.approx(round(ev - pv, 2))
    assert r["eac"] == pytest.approx(round(ac + (bac - ev) / r["cpi"], 2))
    assert r["etc"] == pytest.approx(round(max(r["eac"] - ac, 0), 2))
    assert r["vac"] == pytest.approx(round(bac - r["eac"], 2))


def test_el_signo_de_cv_y_sv_no_esta_invertido(db, proyecto_tm):
    """Con EV (5.750) por encima de AC (800) y de PV (5.000), las dos varianzas
    son positivas. Un intercambio de operandos las dejaría negativas y el panel
    diría que el proyecto va mal cuando va bien."""
    r = calc_project_profitability(proyecto_tm, db)
    assert r["cv"] > 0
    assert r["sv"] > 0
    assert r["cpi"] > 1
    assert r["spi"] > 1


def test_el_coste_previsto_extrapola_por_progreso(db, proyecto_tm):
    """Con 57,5 % de avance y 800 € gastados:
    800 + 800 × 42,5 / 57,5 = 800 + 591,30 = 1.391,30."""
    r = calc_project_profitability(proyecto_tm, db)
    assert r["forecast_cost"] == pytest.approx(1_391.3, abs=0.01)


def test_el_margen_al_cierre_usa_el_eac(db, proyecto_tm):
    r = calc_project_profitability(proyecto_tm, db)
    esperado = round((r["billing_revenue"] - r["eac"]) / r["billing_revenue"] * 100, 1)
    assert r["margin_at_completion"] == esperado


# ── Precio cerrado: el ingreso sale de los hitos ──────────────────────────────

def test_a_precio_cerrado_el_ingreso_sale_de_los_hitos_facturados(db):
    """Sin `billing_rate` manda `contract_amount`, y el ingreso son los hitos
    que se han facturado — no el importe del contrato entero."""
    p = _proyecto(db, contract_amount=50_000.0, budget_amount=40_000.0)
    _imputacion(db, p, horas=10.0, coste=500.0)
    db.commit()
    r = calc_project_profitability(p, db, billed_milestones_total=12_000.0)
    assert r["billing_revenue"] == 12_000.0
    assert r["contract_amount"] == 50_000.0


def test_la_tarifa_por_hora_manda_sobre_el_contrato(db):
    """El orden del original: si hay tarifa Y horas facturables, gana la tarifa
    aunque también haya `contract_amount`."""
    p = _proyecto(db, billing_rate=90.0, contract_amount=50_000.0,
                  budget_amount=40_000.0)
    _imputacion(db, p, horas=10.0, coste=500.0)
    db.commit()
    r = calc_project_profitability(p, db, billed_milestones_total=12_000.0)
    assert r["billing_revenue"] == 900.0     # 90 × 10, no los 12.000 de hitos


def test_con_tarifa_pero_sin_horas_facturables_se_cae_a_los_hitos(db):
    """`if project.billing_rate and billable_hours` — hacen falta las dos. Con
    tarifa pero todo no facturable, el ingreso son los hitos."""
    p = _proyecto(db, billing_rate=90.0, contract_amount=50_000.0)
    _imputacion(db, p, horas=10.0, coste=500.0, facturable=False)
    db.commit()
    r = calc_project_profitability(p, db, billed_milestones_total=7_000.0)
    assert r["billable_hours"] == 0.0
    assert r["billing_revenue"] == 7_000.0


# ── Los casos en que no se puede saber ────────────────────────────────────────

def test_sin_fechas_no_hay_planificado_ni_spi(db):
    """La diferencia entre «va en plazo» y «no se puede saber».

    Sin fechas, PV, SPI y SV son None y el resultado lo marca con
    `evm_no_schedule`. Devolver 0 en su lugar sería un SPI inventado.
    """
    p = _proyecto(db, budget_amount=10_000.0, start_date=None, end_date_planned=None)
    _imputacion(db, p, horas=10.0, coste=500.0)
    _tarea(db, p, TaskStatus.done)
    db.commit()
    r = calc_project_profitability(p, db)
    assert r["pv"] is None
    assert r["spi"] is None
    assert r["sv"] is None
    assert r["evm_no_schedule"] is True


def test_una_fecha_de_fin_anterior_a_la_de_inicio_tampoco_vale(db):
    """El original exige `end_date_planned > start_date`. Un rango invertido
    daría días negativos y un planificado sin sentido."""
    hoy = timeutil.today()
    p = _proyecto(db, budget_amount=10_000.0,
                  start_date=hoy, end_date_planned=hoy - timedelta(days=10))
    db.commit()
    assert calc_project_profitability(p, db)["evm_no_schedule"] is True


def test_sin_tareas_el_progreso_es_cero(db):
    """Y arrastra al EV, que es correcto: un proyecto sin tareas no tiene valor
    ganado que medir."""
    p = _proyecto(db, budget_amount=10_000.0)
    _imputacion(db, p, horas=10.0, coste=500.0)
    db.commit()
    r = calc_project_profitability(p, db)
    assert r["progress_pct"] == 0.0
    assert r["ev"] == 0


def test_sin_imputaciones_no_hay_cpi_pero_si_resultado(db):
    """Con AC = 0 el CPI es None (no infinito ni cero). El resultado sigue
    saliendo completo: es el estado normal de un proyecto recién abierto."""
    p = _proyecto(db, budget_amount=10_000.0, billing_rate=100.0)
    r = calc_project_profitability(p, db)
    assert r["ac"] == 0.0
    assert r["cpi"] is None
    assert r["avg_cost_rate"] == 0
    assert r["margin_pct"] == 0


def test_un_proyecto_sin_presupuesto_no_divide_por_cero(db):
    p = _proyecto(db, billing_rate=100.0, budget_amount=None, budget_hours=None)
    _imputacion(db, p, horas=10.0, coste=500.0)
    db.commit()
    r = calc_project_profitability(p, db)
    assert r["budget_used_pct"] == 0
    assert r["hours_used_pct"] is None


# ── La bandera de riesgo ──────────────────────────────────────────────────────

def test_un_margen_al_cierre_negativo_es_critico(db):
    """Coste real muy por encima del ingreso: el proyecto pierde dinero."""
    p = _proyecto(db, billing_rate=10.0, budget_amount=1_000.0)
    _imputacion(db, p, horas=10.0, coste=5_000.0)
    _tarea(db, p, TaskStatus.done)
    db.commit()
    r = calc_project_profitability(p, db)
    assert r["margin_at_completion"] < 0
    assert r["risk_flag"] == "critical"


def test_un_proyecto_holgado_sale_ok(db, proyecto_tm):
    r = calc_project_profitability(proyecto_tm, db)
    assert r["risk_flag"] == "ok"


def test_un_margen_entre_cero_y_diez_es_aviso(db):
    """El umbral del 10 % de margen previsto: por debajo avisa aunque el CPI
    esté bien."""
    p = _proyecto(db, billing_rate=100.0, budget_amount=1_000.0)
    _imputacion(db, p, horas=10.0, coste=950.0)
    _tarea(db, p, TaskStatus.done)
    db.commit()
    r = calc_project_profitability(p, db)
    assert 0 <= r["margin_at_completion"] < 10
    assert r["risk_flag"] == "warning"


# ── Propiedades estructurales del resultado ───────────────────────────────────

CLAVES = {
    "project_id", "project_code", "project_name", "client_name", "department",
    "status", "billing_type", "is_billable", "project_currency",
    "reporting_currency", "total_hours", "billable_hours", "budget_hours",
    "hours_used_pct", "internal_cost", "billing_revenue", "gross_margin",
    "margin_pct", "budget_amount", "contract_amount", "budget_used_pct",
    "forecast_cost", "billing_rate", "avg_cost_rate", "progress_pct",
    "pv", "ev", "ac", "cpi", "spi", "cv", "sv", "evm_no_schedule",
    "eac", "etc", "vac", "margin_at_completion", "risk_flag",
}


def test_el_resultado_trae_las_38_claves_exactas(db, proyecto_tm):
    """Lo consume la API y lo pinta el panel: una clave que desaparezca en un
    refactor no rompe nada aquí, deja un hueco en la pantalla del cliente."""
    r = calc_project_profitability(proyecto_tm, db)
    assert set(r) == CLAVES, (
        f"faltan: {CLAVES - set(r)}; sobran: {set(r) - CLAVES}"
    )
    assert len(CLAVES) == 38


def test_la_tabla_de_pesos_cubre_todos_los_estados():
    """Que un estado de tarea nuevo no entre valiendo cero sin que nadie lo
    decida. En la cadena de `elif` original ese caso caía al final en silencio;
    ahora hay una tabla y esto la cruza con el enum."""
    from app.services.profitability_service import _PESO_DE_PROGRESO

    faltan = set(TaskStatus) - set(_PESO_DE_PROGRESO)
    assert not faltan, f"estados sin peso definido: {[e.name for e in faltan]}"
    sobran = set(_PESO_DE_PROGRESO) - set(TaskStatus)
    assert not sobran, f"pesos de estados que no existen: {sobran}"


def test_los_totales_precalculados_se_respetan(db):
    """El atajo del listado: cuando el llamante ya trae los totales sumados y la
    moneda coincide, no se vuelve a consultar la base."""
    p = _proyecto(db, billing_rate=50.0, budget_amount=10_000.0)
    _imputacion(db, p, horas=99.0, coste=9_999.0)
    db.commit()
    r = calc_project_profitability(p, db, imputation_totals={
        "total_hours": 8.0, "billable_hours": 8.0, "internal_cost": 400.0,
    })
    assert r["total_hours"] == 8.0          # los precalculados, no las 99 reales
    assert r["internal_cost"] == 400.0
    assert r["billing_revenue"] == 400.0    # 50 × 8


def test_una_moneda_distinta_ignora_los_totales_precalculados(db):
    """La razón de que la condición mire la moneda: los totales precalculados
    vienen sin convertir, y usarlos daría el coste en la moneda equivocada.
    Es un error que no falla — sólo sale una cifra mal."""
    p = _proyecto(db, billing_rate=50.0, budget_amount=10_000.0, currency="USD")
    _imputacion(db, p, horas=99.0, coste=9_999.0)
    db.commit()
    r = calc_project_profitability(p, db, imputation_totals={
        "total_hours": 8.0, "billable_hours": 8.0, "internal_cost": 400.0,
    })
    assert r["total_hours"] == 99.0         # recalculado desde las imputaciones
    assert r["project_currency"] == "USD"
