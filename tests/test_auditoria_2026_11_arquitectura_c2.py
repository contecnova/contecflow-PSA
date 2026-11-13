"""Segunda auditoria 2026-11: guardas de arquitectura (bloque C2).

Cada item va en su propia seccion (`# ── Item N: ... ──`).
"""
from __future__ import annotations

import pytest


# ── Item 36: HTTP fuera de servicios/core ──
#
# Medido antes: 27 importaciones de `fastapi`/`starlette` en 22 ficheros de
# `app/services` y `app/db` (la auditoria contaba 16), 44 `raise HTTPException`
# en `app/core` + `app/db`, y 11 `except (HTTPException, ErrorDeDominio)` en
# servicios. Los servicios devuelven datos (`Descarga`, cabeceras en un
# `ConCabeceras`, un `ProgramadorDeTareas`) y lanzan `ErrorDeDominio`, que
# `app/main.py` traduce a la misma respuesta (status, detail y cabeceras).

import ast as _ast36
import pathlib as _pathlib36

_RAIZ36 = _pathlib36.Path(__file__).resolve().parent.parent

#: Ficheros de `app/services` y `app/db` que pueden importar FastAPI/Starlette.
_IMPORTS_HTTP_PERMITIDOS = {
    # Explica que capa deniega una RUTA: recorre la tabla de rutas de la app
    # (`route.matches(scope)` y su `Match`) y el arbol de dependencias de
    # FastAPI. Su entrada es el enrutador HTTP; sin Starlette no hay nada que explicar.
    "app/services/explicar_acceso.py",
}

#: Ficheros de `app/core` y `app/db` que pueden lanzar `HTTPException`.
_RAISES_HTTP_PERMITIDOS = {
    # Las dependencias FastAPI de autenticacion y rol (`get_current_user`,
    # `RequireRole`, `get_current_client`...): son la frontera HTTP.
    "app/core/deps.py",
    # Dependencia de router (`Depends`, `Request`) de la matriz GRC.
    "app/core/grc_enforce.py",
    # Define el endpoint `/metrics` (`@app.get`), con su 401.
    "app/core/metrics.py",
}


def _py36(*carpetas):
    for carpeta in carpetas:
        for ruta in sorted((_RAIZ36 / carpeta).rglob("*.py")):
            yield ruta.relative_to(_RAIZ36).as_posix(), _ast36.parse(ruta.read_text(encoding="utf-8"))


def _importa_http(nodo) -> bool:
    if isinstance(nodo, _ast36.Import):
        return any(a.name.split(".")[0] in ("fastapi", "starlette") for a in nodo.names)
    if isinstance(nodo, _ast36.ImportFrom):
        return (nodo.module or "").split(".")[0] in ("fastapi", "starlette") and not nodo.level
    return False


def _lanza_http(nodo) -> bool:
    if not isinstance(nodo, _ast36.Raise) or nodo.exc is None:
        return False
    exc = nodo.exc.func if isinstance(nodo.exc, _ast36.Call) else nodo.exc
    nombre = exc.attr if isinstance(exc, _ast36.Attribute) else getattr(exc, "id", None)
    return nombre == "HTTPException"


def test_36_servicios_y_db_no_importan_fastapi_ni_starlette():
    """Tambien cuentan los imports locales y los de `TYPE_CHECKING` (AST, no texto)."""
    malos = [f"{ruta}:{n.lineno}" for ruta, arbol in _py36("app/services", "app/db")
             if ruta not in _IMPORTS_HTTP_PERMITIDOS
             for n in _ast36.walk(arbol) if _importa_http(n)]
    assert not malos, (
        "Un servicio no construye respuestas ni lee peticiones: devuelve datos "
        "(`app.core.descargas.Descarga`...) y la capa API monta la respuesta:\n" + "\n".join(malos))


def test_36_core_y_db_no_lanzan_httpexception():
    malos = [f"{ruta}:{n.lineno}" for ruta, arbol in _py36("app/core", "app/db")
             if ruta not in _RAISES_HTTP_PERMITIDOS
             for n in _ast36.walk(arbol) if _lanza_http(n)]
    assert not malos, (
        "Fuera de las dependencias HTTP, `raise ErrorDeDominio(status, detail)` "
        "(app/core/errores.py): corre tambien en Celery y scripts:\n" + "\n".join(malos))


def test_36_las_listas_permitidas_no_se_quedan_viejas():
    """Si un fichero permitido deja de necesitarlo (o desaparece), sale de la lista."""
    imports = {r for r, a in _py36("app/services", "app/db") if any(_importa_http(n) for n in _ast36.walk(a))}
    raises = {r for r, a in _py36("app/core", "app/db") if any(_lanza_http(n) for n in _ast36.walk(a))}
    assert _IMPORTS_HTTP_PERMITIDOS <= imports, _IMPORTS_HTTP_PERMITIDOS - imports
    assert _RAISES_HTTP_PERMITIDOS <= raises, _RAISES_HTTP_PERMITIDOS - raises


def test_36_ningun_servicio_atrapa_ya_httpexception():
    """Los servicios ya no reciben `HTTPException` de `app/core`: basta `except ErrorDeDominio`."""
    malos = []
    for ruta, arbol in _py36("app/services"):
        for n in _ast36.walk(arbol):
            if isinstance(n, _ast36.ExceptHandler) and n.type is not None:
                tipos = n.type.elts if isinstance(n.type, _ast36.Tuple) else [n.type]
                if any(getattr(t, "id", getattr(t, "attr", None)) == "HTTPException" for t in tipos):
                    malos.append(f"{ruta}:{n.lineno}")
    assert not malos, malos


def test_36_error_de_dominio_de_core_da_la_misma_respuesta_http():
    """El 403 de empresa desactivada (antes `HTTPException` en app/db) sale igual por la API."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    import app.main as principal
    from app.core.errores import ErrorDeDominio

    app_prueba = FastAPI()
    app_prueba.add_exception_handler(ErrorDeDominio, principal.http_exception_sanitizer)

    @app_prueba.get("/x")
    def _x():
        raise ErrorDeDominio(401, "Token requerido", headers={"WWW-Authenticate": "Bearer"})

    r = TestClient(app_prueba).get("/x")
    assert r.status_code == 401
    assert r.json() == {"detail": "Token requerido"}
    assert r.headers["www-authenticate"] == "Bearer"


def test_36_exigir_organizacion_activa_lanza_error_de_dominio():
    from app.core.errores import ErrorDeDominio
    from app.db.session import exigir_organizacion_activa

    class _Org:
        is_active = False

    class _Sesion:
        def get(self, _modelo, _id):
            return _Org()

    with pytest.raises(ErrorDeDominio) as e:
        exigir_organizacion_activa(_Sesion(), "org-1")
    assert (e.value.status_code, e.value.detail) == (403, "La organización está desactivada")


def test_36_descarga_se_sirve_igual_que_el_streamingresponse_de_antes():
    import asyncio

    from app.api.descargas import respuesta_de_descarga
    from app.services.exportador_tabular import respuesta_tabular

    r = respuesta_de_descarga(respuesta_tabular("csv", nombre="x", cabecera=["a"], filas=[[1]]))
    assert r.media_type == "text/csv"
    assert r.headers["content-disposition"] == "attachment; filename=x.csv"

    async def _leer():
        return b"".join([t async for t in r.body_iterator])
    assert asyncio.run(_leer()) == "a\r\n1\r\n".encode("utf-8-sig")


# ── Items 33, 37 y 45 (worker): contexto de tenant, envoltorios y calendario ──
#
# Medido antes: 46 tareas; 36 abrian `worker_db_session` sin contexto de
# tenant; 22 db.query/add/delete/execute y 16 commits en `app/worker.py`; 17
# manejadores devolvian `{"error": ...}` sin relanzar (Celery: SUCCESS).
# `catalog_popularity_update` no guardaba nada; 7 entradas de beat tenian
# ademas su `add_job` propio en APScheduler.

import ast as _ast33
import inspect as _inspect33
from contextlib import contextmanager as _cm33

_WORKER = _RAIZ36 / "app" / "worker.py"


def _tareas_del_worker():
    import app.worker as w
    return w, {n: t for n, t in w.celery_app.tasks.items() if n.startswith("app.worker.")}


def _sesion_de_pruebas(monkeypatch, db):
    @_cm33
    def _s():
        yield db
    monkeypatch.setattr("app.db.session.worker_db_session", _s)


def test_33_cada_tarea_esta_en_una_sola_forma_de_tratar_la_organizacion():
    w, tareas = _tareas_del_worker()
    listas = [set(w.TAREAS_GLOBALES), set(w.TAREAS_POR_SUJETO), set(w.TAREAS_POR_FILA)]
    declaradas = set().union(*listas)
    assert sum(map(len, listas)) == len(declaradas), "una tarea en dos listas"
    assert declaradas <= set(tareas), f"listas viejas: {declaradas - set(tareas)}"
    por_org = {n for n, t in tareas.items() if "_por_organizacion(" in _inspect33.getsource(t.run)}
    assert not (por_org & declaradas)
    sin_forma = set(tareas) - declaradas - por_org
    assert not sin_forma, (
        "cada tarea nueva recorre las organizaciones (`_por_organizacion`) o va a una "
        f"lista con su razon: {sorted(sin_forma)}")
    assert len(por_org) >= 25, "el detector no esta mirando"


def test_33_las_tareas_por_fila_publican_la_organizacion_de_cada_fila():
    import importlib
    w, _ = _tareas_del_worker()
    for tarea, modulo in w.TAREAS_POR_FILA.items():
        fuente = _inspect33.getsource(importlib.import_module(modulo))
        assert "como_organizacion" in fuente or "publicar_contexto_de_tenant" in fuente, tarea


def test_33_en_cada_organizacion_publica_el_contexto_de_cada_una(db, monkeypatch, seed_multitenant):
    from app.services.trabajos_de_fondo import en_cada_organizacion

    _sesion_de_pruebas(monkeypatch, db)
    antes = dict(db.info)
    vistos = []
    r = en_cada_organizacion("prueba", lambda s, org: vistos.append(
        (org, s.info.get("organization_id"), s.info.get("is_superadmin"))) or org)
    assert vistos == [("org-a-test", "org-a-test", False), ("org-b-test", "org-b-test", False)]
    assert r == {"organizaciones": 2, "por_organizacion": {"org-a-test": "org-a-test", "org-b-test": "org-b-test"}}
    assert dict(db.info) == antes, "el contexto se devuelve como estaba"


def test_33_37_un_fallo_no_para_a_las_demas_deja_traza_y_la_tarea_falla(db, monkeypatch, seed_multitenant, caplog):
    import logging
    from app.services.trabajos_de_fondo import FalloEnOrganizaciones, en_cada_organizacion

    _sesion_de_pruebas(monkeypatch, db)
    hechas = []

    def trabajo(s, org):
        if org == "org-a-test":
            raise ValueError("roto")
        hechas.append(org)

    with caplog.at_level(logging.ERROR), pytest.raises(FalloEnOrganizaciones) as e:
        en_cada_organizacion("prueba", trabajo)
    assert hechas == ["org-b-test"]
    assert isinstance(e.value.__cause__, ValueError) and list(e.value.fallos) == ["org-a-test"]
    assert any(r.exc_info for r in caplog.records if "org-a-test" in r.getMessage())


def test_33_EL_HALLAZGO_compliance_check_guarda_un_informe_en_cada_organizacion(db, monkeypatch, seed_multitenant):
    """Antes: un informe con los datos de todas, con `organization_id` NULL (no lo veia nadie)."""
    from app.db.session import sin_filtro_de_tenant
    from app.models.service_desk import ComplianceReport
    from app.worker import compliance_check

    _sesion_de_pruebas(monkeypatch, db)
    r = compliance_check.run()
    assert r["organizaciones"] == 2
    with sin_filtro_de_tenant(db):
        orgs = sorted(o for (o,) in db.query(ComplianceReport.organization_id))
    assert orgs == ["org-a-test", "org-b-test"]


def test_33_EL_HALLAZGO_la_rca_automatica_lleva_la_organizacion_a_call_ai(monkeypatch):
    """`problem_auto_detect` -> `suggest_rca_from_ai`: sin usuario ni organizacion no aplicaba
    el tope de gasto ni el proveedor de la empresa."""
    from types import SimpleNamespace
    from unittest.mock import MagicMock

    from app.services.service_desk import problem_service

    vistos = {}

    def call_ai(**k):
        vistos.update(k)
        return {"content": '{"root_cause": "x", "rca_type": "software", "confidence": 50}'}
    monkeypatch.setattr("app.services.ai_provider_service.call_ai", call_ai)
    problema = SimpleNamespace(id="p1", title="t", description="d", organization_id="org-x",
                               rca_ai_suggestion=None, rca_type=None, root_cause=None,
                               workaround=None)
    problem_service.suggest_rca_from_ai(MagicMock(), problema)
    assert vistos["organization_id"] == "org-x"


def test_37_worker_sin_logica_de_negocio_ni_errores_tragados():
    arbol = _ast33.parse(_WORKER.read_text(encoding="utf-8"))
    accesos = [f"{n.lineno}:{n.func.attr}" for n in _ast33.walk(arbol)
               if isinstance(n, _ast33.Call) and isinstance(n.func, _ast33.Attribute)
               and n.func.attr in {"query", "add", "delete", "execute", "commit", "rollback"}]
    assert not accesos, f"acceso a BD en app/worker.py (va en un servicio): {accesos}"
    largas = [f"{n.name} ({n.end_lineno - n.lineno + 1})" for n in arbol.body
              if isinstance(n, _ast33.FunctionDef) and n.end_lineno - n.lineno + 1 > 30]
    assert not largas, f"tareas que no son envoltorios: {largas}"
    tragados = [h.lineno for h in _ast33.walk(arbol) if isinstance(h, _ast33.ExceptHandler)
                and (h.type is None or getattr(h.type, "id", "") in {"Exception", "BaseException"})
                and not any(isinstance(x, _ast33.Raise) for x in _ast33.walk(h))]
    assert not tragados, f"`except Exception` sin relanzar en app/worker.py: {tragados}"


def test_37_la_entrega_de_webhook_se_reintenta_desde_la_tarea(monkeypatch):
    from app.worker import deliver_webhook_task

    monkeypatch.setattr("app.services.entrega_de_webhooks.entregar_webhook",
                        lambda *a, **k: {"success": False, "reintentar_en": 60, "motivo": RuntimeError("x")})
    llamadas = {}

    def retry(**k):
        llamadas.update(k)
        raise RuntimeError("reintento")
    monkeypatch.setattr(deliver_webhook_task, "retry", retry)
    with pytest.raises(RuntimeError, match="reintento"):
        deliver_webhook_task.run(1, "{}", "e")
    assert llamadas["countdown"] == 60


def test_37_ejecucion_de_agente_inexistente_falla_en_vez_de_salir_bien(db, monkeypatch):
    from app.services.ai_chat.agente_en_segundo_plano import EjecucionNoEncontrada
    from app.worker import run_agent_task

    _sesion_de_pruebas(monkeypatch, db)
    with pytest.raises(EjecucionNoEncontrada):
        run_agent_task.run("no-existe", "hola", "nadie")


def test_45_la_popularidad_del_catalogo_ya_no_se_programa():
    """No hay columna donde guardarla (`updated` siempre 0) y nadie leia el resultado:
    la popularidad se calcula al pedirla (`get_popular_services`)."""
    w, tareas = _tareas_del_worker()
    assert "app.worker.catalog_popularity_update" not in tareas
    assert all("catalog_popularity" not in e["task"] for e in w.celery_app.conf.beat_schedule.values())


def test_45_apscheduler_solo_replica_beat_y_retira_los_duplicados():
    from apscheduler.schedulers.background import BackgroundScheduler
    from apscheduler.triggers.cron import CronTrigger

    import app.main as m

    assert not hasattr(m, "_BEAT_YA_EN_APSCHEDULER")
    assert not (_RAIZ36 / "app" / "services" / "automation_jobs.py").exists()
    s = BackgroundScheduler()
    s.start(paused=True)
    try:
        for viejo in ("scheduled_reports", "bpmn_timers"):
            s.add_job(print, CronTrigger(minute=0), id=viejo)
        n = m._replicar_celery_beat(s)
        assert sorted(m._retirar_trabajos_duplicados(s)) == ["bpmn_timers", "scheduled_reports"]
        ids = {j.id for j in s.get_jobs()}
        from app.worker import celery_app
        assert ids == {f"beat_{k}" for k in celery_app.conf.beat_schedule} and n == len(ids)
    finally:
        s.shutdown(wait=False)


def _tareas_por_organizacion():
    import app.worker as w
    return sorted(n for n, t in w.celery_app.tasks.items()
                  if n.startswith("app.worker.") and "_por_organizacion(" in _inspect33.getsource(t.run))


@pytest.mark.parametrize("nombre", _tareas_por_organizacion())
def test_33_cada_tarea_por_organizacion_corre_con_el_filtro_de_tenant_puesto(nombre, db, monkeypatch, seed_multitenant):
    """Con el contexto publicado el filtro actua: un modelo sin columna de tenant
    (`TenantIsolationError`) o una consulta entre organizaciones saldrian aqui."""
    import app.worker as w

    _sesion_de_pruebas(monkeypatch, db)
    monkeypatch.setattr("app.services.bi_intelligence_service.publish_kpi_snapshot", lambda *a, **k: None)
    r = w.celery_app.tasks[nombre].run()
    assert r.get("skipped") or 2 in (r.get("organizaciones"), r.get("organizations")), r