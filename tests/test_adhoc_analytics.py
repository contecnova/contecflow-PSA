"""La consulta analítica ad-hoc devuelve datos reales (auditoría 2026-08, P1-9).

Dos defectos encadenados hacían que este endpoint no funcionase, y ninguno daba
error:

1. `POST /api/v1/analytics/adhoc` comprobaba
   `hasattr(adhoc_analytics_service, "run_analytics_adhoc")`. Esa función NO EXISTE — la
   implementación real se llama `run_adhoc_query`. El hasattr era False siempre,
   así que el endpoint respondía 200 con `{"results": [], "total_rows": 0}`
   pasara lo que pasara.

2. `run_adhoc_query`, cuando por fin se llamaba, hacía `q.limit(limit).all()` y
   sumaba en Python DESPUÉS. Con más filas que el límite los totales salían
   incompletos en silencio.

Los tests que había en tests/test_business_logic_v238.py sólo comprobaban
`"results" in data`, así que un endpoint que siempre devolvía vacío pasaba en
verde. Este fichero exige datos: sin él, cualquiera de los dos defectos puede
volver sin que nadie se entere.
"""
from __future__ import annotations

import uuid
from datetime import date, timedelta

import pytest

from app.services import adhoc_analytics_service
from app.core.errores import ErrorDeDominio


@pytest.fixture()
def imputaciones(db):
    """Imputaciones conocidas repartidas en dos meses y dos proyectos."""
    from app.models.imputation import Imputation
    from app.models.project import Project, ProjectStatus, ProjectType
    from app.models.user import User

    user = db.query(User).filter(User.username == "dev_test").first()
    assert user is not None, "el fixture db debe crear dev_test"

    proyectos = []
    for nombre in ("Adhoc A", "Adhoc B"):
        pr = Project(
            id=str(uuid.uuid4()),
            code=f"AD-{uuid.uuid4().hex[:6]}",
            name=nombre,
            status=ProjectStatus.active,
            project_type=ProjectType.internal,
            organization_id="1",
        )
        db.add(pr)
        proyectos.append(pr)
    db.commit()

    hoy = date.today()
    # HOY y no el día 15 del mes en curso. El fixture usaba `hoy.replace(day=15)`
    # y eso hacía que `test_el_filtro_de_fechas_se_aplica_con_cadenas_iso` sólo
    # pasara del 15 en adelante: ese test acota `[día 1, hoy]`, y antes del 15 las
    # imputaciones caían en el FUTURO y quedaban fuera con razón. Se escribió a
    # finales de agosto, pasó en verde, y desde el día 1 siguiente mentía.
    #
    # `hoy` está siempre dentro de `[primero de mes, hoy]`, incluso el día 1.
    este_mes = hoy
    mes_pasado = (hoy.replace(day=1) - timedelta(days=1)).replace(day=15)

    # 10 imputaciones de 3h en el proyecto A este mes  → 30h
    # 5  imputaciones de 2h en el proyecto B mes pasado → 10h
    for _ in range(10):
        db.add(Imputation(
            id=str(uuid.uuid4()), user_id=user.id, project_id=proyectos[0].id,
            date=este_mes, hours=3.0, description="adhoc test",
        ))
    for _ in range(5):
        db.add(Imputation(
            id=str(uuid.uuid4()), user_id=user.id, project_id=proyectos[1].id,
            date=mes_pasado, hours=2.0, description="adhoc test",
        ))
    db.commit()
    return {"proyectos": proyectos, "este_mes": este_mes, "mes_pasado": mes_pasado, "total": 40.0}


# ── El bug del truncamiento ───────────────────────────────────────────────────

def test_el_total_no_depende_del_limite(db, imputaciones):
    """El caso exacto que producía cifras erróneas.

    Con limit=2 y 15 filas, la versión anterior sumaba sólo 2 registros. El
    límite debe acotar las filas AGRUPADAS del resultado, no las de entrada.
    """
    con_limite_bajo = adhoc_analytics_service.run_adhoc_query(
        metric="hours_logged", dimensions=[], filters={},
        date_from=None, date_to=None, limit=2, db=db,
    )
    con_limite_alto = adhoc_analytics_service.run_adhoc_query(
        metric="hours_logged", dimensions=[], filters={},
        date_from=None, date_to=None, limit=10_000, db=db,
    )
    total_bajo = con_limite_bajo["results"][0]["total_hours"]
    total_alto = con_limite_alto["results"][0]["total_hours"]
    assert total_bajo == total_alto, (
        f"el total cambia con el límite ({total_bajo} vs {total_alto}): "
        "se está agregando sobre filas truncadas"
    )
    assert total_alto >= imputaciones["total"]


def test_el_total_global_incluye_todas_las_horas(db, imputaciones):
    res = adhoc_analytics_service.run_adhoc_query(
        metric="hours_logged", dimensions=[], filters={},
        date_from=None, date_to=None, limit=100, db=db,
    )
    assert res["results"][0]["total_hours"] >= imputaciones["total"]


def test_agrupado_por_mes_devuelve_datos(db, imputaciones):
    res = adhoc_analytics_service.run_adhoc_query(
        metric="hours_logged", dimensions=["month"], filters={},
        date_from=None, date_to=None, limit=100, db=db,
    )
    assert res["results"], "el agrupado por mes no devolvió nada"
    meses = {r["month"]: r["hours"] for r in res["results"]}
    clave_actual = imputaciones["este_mes"].strftime("%Y-%m")
    assert clave_actual in meses, f"falta el mes {clave_actual} en {list(meses)}"
    assert meses[clave_actual] >= 30.0


def test_agrupado_por_proyecto_suma_por_grupo(db, imputaciones):
    res = adhoc_analytics_service.run_adhoc_query(
        metric="hours_logged", dimensions=["project_id"], filters={},
        date_from=None, date_to=None, limit=100, db=db,
    )
    por_proyecto = {r["project_id"]: r["hours"] for r in res["results"]}
    pid_a = imputaciones["proyectos"][0].id
    assert por_proyecto.get(pid_a) == 30.0, f"proyecto A debía sumar 30h: {por_proyecto.get(pid_a)}"


def test_el_filtro_de_proyecto_se_aplica(db, imputaciones):
    pid_b = imputaciones["proyectos"][1].id
    res = adhoc_analytics_service.run_adhoc_query(
        metric="hours_logged", dimensions=[], filters={"project_id": pid_b},
        date_from=None, date_to=None, limit=100, db=db,
    )
    assert res["results"][0]["total_hours"] == 10.0


def test_el_filtro_de_fechas_se_aplica_con_cadenas_iso(db, imputaciones):
    """El endpoint recibe JSON, así que las fechas llegan como cadenas.

    La firma anterior se anotaba `Optional[date]` y comparaba directamente: con
    una cadena la comparación no fallaba, simplemente no filtraba lo esperado.
    """
    inicio = imputaciones["este_mes"].replace(day=1).isoformat()
    res = adhoc_analytics_service.run_adhoc_query(
        metric="hours_logged", dimensions=[], filters={},
        date_from=inicio, date_to=date.today().isoformat(), limit=100, db=db,
    )
    assert res["results"][0]["total_hours"] == 30.0, (
        "el filtro de fechas por cadena ISO no acotó al mes en curso"
    )


def test_fecha_no_valida_da_400(db):
    from fastapi import HTTPException

    with pytest.raises((HTTPException, ErrorDeDominio)) as exc:
        adhoc_analytics_service.run_adhoc_query(
            metric="hours_logged", dimensions=[], filters={},
            date_from="no-es-una-fecha", date_to=None, limit=100, db=db,
        )
    assert exc.value.status_code == 400


def test_metrica_no_soportada_da_400_no_vacio(db):
    """Antes una métrica inválida devolvía 200 con lista vacía: indistinguible
    de «no hay datos». Ahora se rechaza explícitamente."""
    from fastapi import HTTPException

    with pytest.raises((HTTPException, ErrorDeDominio)) as exc:
        adhoc_analytics_service.run_adhoc_query(
            metric="metrica_inexistente", dimensions=[], filters={},
            date_from=None, date_to=None, limit=100, db=db,
        )
    assert exc.value.status_code == 400


def test_recuento_de_tareas_funciona(db):
    res = adhoc_analytics_service.run_adhoc_query(
        metric="task_count", dimensions=["status"], filters={},
        date_from=None, date_to=None, limit=100, db=db,
    )
    assert "results" in res
    for fila in res["results"]:
        assert isinstance(fila["count"], int)


# ── El endpoint HTTP, que era el que siempre devolvía vacío ───────────────────

def test_el_endpoint_devuelve_datos_no_una_lista_vacia(client, admin_token, imputaciones):
    from tests.conftest import auth

    res = client.post(
        "/api/v1/analytics/adhoc",
        json={"metric": "hours_logged", "dimensions": ["month"]},
        headers=auth(admin_token),
    )
    assert res.status_code == 200
    data = res.json()["data"]
    assert data["results"], (
        "el endpoint sigue devolviendo results=[]. Era el síntoma del hasattr "
        "sobre una función que no existe."
    )
    assert data["total_rows"] > 0


def test_el_endpoint_rechaza_una_metrica_invalida(client, admin_token):
    from tests.conftest import auth

    res = client.post(
        "/api/v1/analytics/adhoc",
        json={"metric": "no_existe_esta_metrica", "dimensions": []},
        headers=auth(admin_token),
    )
    assert res.status_code == 400


def test_la_funcion_mal_nombrada_sigue_sin_existir(db):
    """Fija la causa raíz: nadie debe reintroducir el nombre equivocado.

    Si alguien añade `run_analytics_adhoc` como alias, el endpoint volvería a
    tener dos caminos y el hasattr podría reaparecer. La implementación se llama
    `run_adhoc_query` y se invoca directamente.
    """
    assert hasattr(adhoc_analytics_service, "run_adhoc_query")
    assert not hasattr(adhoc_analytics_service, "run_analytics_adhoc"), (
        "no crear alias: el endpoint llama directamente a run_adhoc_query"
    )
