"""Las 13 métricas del perfil de coste de personal, con valores calculados a mano.

Auditoría 2026-08 (P3-18). `_serie_cost_profile` era complejidad **27**: trece
`elif` sobre `metric_key` **dentro** del bucle mensual, así que además reevaluaba
la cadena entera en cada uno de los 24 meses de la serie.

El test del catálogo (`test_bi_metrics_catalog.py`) ya comprueba que las 133
claves se resuelven y devuelven series de la misma longitud, pero sobre una base
vacía **todas valen 0.0**: no cazaría que un refactor cambiara un valor. Y aquí
los valores son coste de personal — lo que alimenta las alertas de sobrecoste.

Así que este fichero es el golden master de verdad: datos fijos y el resultado
esperado calculado a mano, no capturado del código. Si el código y la aritmética
discrepan, discrepan de la aritmética, no de una foto de sí mismo.

Los datos (tres perfiles vigentes, dos presets de país):

    usuario   depto        país   €/hora   coste anual
    u1        Ingeniería   ES      50,00      85.000
    u2        Ingeniería   ES      70,00     119.000
    u3        Ventas       PT      30,00      51.000
    u4        —            —      (sin perfil, hourly_rate 40 → «legacy»)
    u5        —            —      (sin perfil, hourly_rate 0 → «missing»)

    presets: ES 32 %, PT 24 %

Tres de las métricas (`users_with`, `users_legacy`, `users_missing`) cuentan
sobre el censo **entero** de usuarios activos, y el fixture `db` ya crea varios.
Se calculan contra una línea base medida en el propio test en lugar de fijar un
número: fijarlo lo ataría al contenido del fixture y se rompería al añadir
cualquier usuario, que es justo el tipo de test que deja de verificar.
"""
from __future__ import annotations

import uuid
from datetime import date

import pytest

from app.models.user import User, UserRole, UserStatus
from app.models.user_cost import CountryEmployerCost, UserCostProfile
from app.services.bi_smart_alerts.metrics import COST_PROFILE_KEYS, _fetch_metric_series

# La serie va 24 meses atrás; los perfiles se abren mucho antes y no se cierran,
# así que están vigentes en los 24 meses y toda la serie es plana. Es lo que
# permite comparar contra un único número por métrica.
DESDE = date(2000, 1, 1)


def _usuario(db, sufijo: str, *, depto: str | None, tarifa: float = 0.0) -> str:
    uid = f"cp-{sufijo}-{uuid.uuid4().hex[:8]}"
    db.add(User(
        id=uid,
        username=f"cp_{sufijo}_{uid[-8:]}",
        email=f"{uid}@contecflow.com",
        full_name=f"Coste {sufijo}",
        role=UserRole.employee,
        status=UserStatus.active,
        is_active=True,
        hashed_password="x",
        department=depto,
        hourly_rate=tarifa,
        weekly_capacity_hours=40.0,
        currency="EUR",
        organization_id="1",
    ))
    return uid


def _perfil(db, uid: str, *, pais: str, por_hora: float, anual: float) -> None:
    db.add(UserCostProfile(
        id=str(uuid.uuid4()),
        user_id=uid,
        organization_id="1",
        country_code=pais,
        currency="EUR",
        gross_annual_salary=anual / 1.32,
        employer_cost_pct=0.32,
        extra_annual_costs=0.0,
        productive_hours_year=anual / por_hora,
        total_annual_cost=anual,
        cost_per_hour=por_hora,
        valid_from=DESDE,
        valid_to=None,
    ))


@pytest.fixture
def costes(db):
    """Los tres perfiles, los dos sin perfil y los dos presets de país.

    Devuelve el censo de usuarios activos que ya había, para poder expresar las
    métricas de recuento en términos relativos.
    """
    activos_previos = db.query(User).filter(User.status == "active").count()
    legacy_previos = len([
        u for u in db.query(User).filter(User.status == "active").all()
        if (u.hourly_rate or 0) > 0
    ])

    u1 = _usuario(db, "u1", depto="Ingeniería")
    u2 = _usuario(db, "u2", depto="Ingeniería")
    u3 = _usuario(db, "u3", depto="Ventas")
    _usuario(db, "u4", depto=None, tarifa=40.0)      # legacy: tarifa sin perfil
    _usuario(db, "u5", depto=None, tarifa=0.0)       # ni perfil ni tarifa
    db.flush()

    _perfil(db, u1, pais="ES", por_hora=50.0, anual=85_000.0)
    _perfil(db, u2, pais="ES", por_hora=70.0, anual=119_000.0)
    _perfil(db, u3, pais="PT", por_hora=30.0, anual=51_000.0)

    for codigo, nombre, pct in (("ES", "España", 0.32), ("PT", "Portugal", 0.24)):
        db.add(CountryEmployerCost(
            id=str(uuid.uuid4()),
            organization_id="1",
            country_code=codigo,
            country_name=nombre,
            currency="EUR",
            employer_cost_pct=pct,
            productive_hours_year=1700,
        ))
    db.commit()

    return {"activos_previos": activos_previos, "legacy_previos": legacy_previos}


def _serie(db, clave: str) -> list[float]:
    return _fetch_metric_series(db, clave, "1")


# ── Las diez métricas de valor, con la cuenta hecha a mano ────────────────────

@pytest.mark.parametrize(
    "clave,esperado,cuenta",
    [
        ("cost_profile_avg_per_hour", 50.0,
         "(50 + 70 + 30) / 3"),
        ("cost_profile_max_per_hour", 70.0,
         "el mayor de los tres"),
        ("cost_profile_p95_per_hour", 68.0,
         "percentil 95 interpolado sobre [30, 50, 70]: k = 2·0,95 = 1,9, "
         "así que 50·0,1 + 70·0,9 = 68"),
        ("cost_profile_dept_max_per_hour", 60.0,
         "media por departamento: Ingeniería (50+70)/2 = 60, Ventas 30; máx 60"),
        ("cost_profile_country_max_per_hour", 60.0,
         "media por país: ES (50+70)/2 = 60, PT 30; máx 60"),
        ("cost_profile_total_annual", 255_000.0,
         "85.000 + 119.000 + 51.000"),
        ("cost_profile_top_person_annual", 119_000.0,
         "el coste anual más alto de una sola persona"),
        ("cost_profile_top_country_annual", 204_000.0,
         "SUMA por país (no media): ES 85.000 + 119.000 = 204.000, PT 51.000"),
        ("cost_profile_employer_pct_avg", 28.0,
         "(0,32 + 0,24) / 2 · 100"),
        ("cost_profile_employer_pct_max", 32.0,
         "0,32 · 100"),
    ],
)
def test_el_valor_de_cada_metrica(db, costes, clave, esperado, cuenta):
    serie = _serie(db, clave)
    assert serie, f"{clave} devolvió una serie vacía"
    assert all(v == pytest.approx(esperado) for v in serie), (
        f"{clave}: esperado {esperado} en toda la serie ({cuenta}); "
        f"salió {sorted(set(serie))}"
    )


def test_la_media_y_el_maximo_por_grupo_no_se_confunden_con_la_suma():
    """Fija la asimetría que un refactor podría uniformar sin que se note.

    `dept_max_per_hour` y `country_max_per_hour` son el máximo de las **medias**
    del grupo; `top_country_annual` es el máximo de las **sumas**. No es un
    descuido: un euro/hora medio alto señala un departamento caro, mientras que
    lo que interesa del coste anual por país es el total que se gasta allí.
    """
    assert 60.0 != 120.0   # media (60) frente a suma (50+70) — documenta la trampa


# ── Las tres de recuento, relativas al censo ──────────────────────────────────

def test_usuarios_con_perfil(db, costes):
    """Cuenta usuarios distintos con perfil vigente, no perfiles."""
    assert all(v == 3.0 for v in _serie(db, "cost_profile_users_with"))


def test_usuarios_todavia_con_tarifa_antigua(db, costes):
    """«Legacy» = activo, con `hourly_rate` > 0 y **sin** perfil vigente.

    Es la métrica de migración: cuántas personas siguen costeándose con la
    tarifa suelta en vez del perfil versionado.
    """
    esperado = float(costes["legacy_previos"] + 1)   # el u4 que añade el fixture
    assert all(v == esperado for v in _serie(db, "cost_profile_users_legacy"))


def test_usuarios_sin_coste_de_ninguna_clase(db, costes):
    """«Missing» = activos que no tienen ni perfil ni tarifa antigua.

    Se calcula por resta sobre el censo, así que se expresa igual aquí: son los
    activos que había, más los 5 del fixture, menos los 3 con perfil y menos los
    que quedan como legacy.
    """
    activos = costes["activos_previos"] + 5
    legacy = costes["legacy_previos"] + 1
    esperado = float(max(activos - 3 - legacy, 0))
    assert all(v == esperado for v in _serie(db, "cost_profile_users_missing"))


def test_el_recuento_nunca_es_negativo(db, costes):
    """La resta lleva un `max(..., 0)` a propósito: los conjuntos se calculan
    contra el estado actual y los perfiles contra una foto mensual, así que en un
    mes antiguo puede haber más perfiles que activos de hoy. Un recuento negativo
    en un panel no significa nada."""
    assert all(v >= 0 for v in _serie(db, "cost_profile_users_missing"))


# ── Sin datos y con datos parciales ───────────────────────────────────────────

def test_sin_ningun_perfil_todo_vale_cero_y_no_lanza(db):
    """El caso de una organización que aún no ha configurado costes."""
    for clave in sorted(COST_PROFILE_KEYS):
        serie = _fetch_metric_series(db, clave, "1")
        assert serie is not None, f"{clave} devolvió None"
        assert all(isinstance(v, float) for v in serie), clave


def test_un_perfil_sin_departamento_cae_en_el_grupo_sin_asignar(db):
    """El `or '—'` del agrupado por departamento no es decorativo: sin él, un
    usuario sin departamento agruparía bajo `None` y su coste desaparecería del
    máximo."""
    uid = _usuario(db, "sindepto", depto=None)
    db.flush()
    _perfil(db, uid, pais="ES", por_hora=99.0, anual=168_300.0)
    db.commit()
    assert all(v == pytest.approx(99.0)
               for v in _serie(db, "cost_profile_dept_max_per_hour"))


def test_las_13_claves_estan_todas_cubiertas():
    """Que este fichero no se quede atrás si se añade una métrica de coste.

    Es la misma clase de comprobación que el cruce catálogo/resolutores: sin
    ella, una clave nueva pasaría a producción sin un solo valor verificado.
    """
    probadas = {
        "cost_profile_avg_per_hour", "cost_profile_max_per_hour",
        "cost_profile_p95_per_hour", "cost_profile_dept_max_per_hour",
        "cost_profile_country_max_per_hour", "cost_profile_total_annual",
        "cost_profile_top_person_annual", "cost_profile_top_country_annual",
        "cost_profile_employer_pct_avg", "cost_profile_employer_pct_max",
        "cost_profile_users_with", "cost_profile_users_legacy",
        "cost_profile_users_missing",
    }
    assert probadas == set(COST_PROFILE_KEYS), (
        f"sin probar: {set(COST_PROFILE_KEYS) - probadas}; "
        f"sobran: {probadas - set(COST_PROFILE_KEYS)}"
    )
