"""La zona de la petición viaja por el contexto hasta las funciones de servicio.

Auditoría 2026-08 (P2-14). Quedaban 198 `date.today()` en la capa de servicios y
cada uno decidía el borde del día con la zona del SERVIDOR. Enhebrar un `user` o
un `zone` por esas 198 firmas —y por las que las llaman— habría contaminado media
capa de servicios con un parámetro de presentación, y habría dejado la corrección
dependiendo de que nadie se olvide de pasarlo. La zona se publica una vez por
petición en un `ContextVar` y `timeutil.today()` la lee.

Eso descansa en un detalle del framework que NO es evidente y cuyo fallo sería
silencioso: FastAPI ejecuta las dependencias SÍNCRONAS en un hilo del threadpool,
y un `ContextVar` fijado en un hilo trabajador se pierde al volver. Una versión
`def` de `bind_request_timezone` no publicaría nada, `today()` seguiría dando el
día del servidor y todo parecería correcto.

Este módulo fija las cinco filas que se midieron antes de construir nada encima,
para que ese cambio no pueda colarse sin que salte algo.
"""
from __future__ import annotations

import contextvars
import inspect
from datetime import date, datetime

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from app.core import timeutil
from app.core.timeutil import UTC, resolve_zone, today, using_zone


# ── El invariante que sostiene todo lo demás ──────────────────────────────────

def test_bind_request_timezone_es_una_corrutina():
    """Si alguien la convierte en `def`, la zona deja de publicarse EN SILENCIO.

    Es el test más importante del módulo: el resto del mecanismo es correcto y
    esta única palabra lo desactiva por completo sin producir ningún error.
    """
    from app.core.timezone_context import bind_request_timezone

    assert inspect.iscoroutinefunction(bind_request_timezone), (
        "bind_request_timezone debe ser `async def`: en versión síncrona FastAPI "
        "la ejecuta en un hilo del threadpool y el ContextVar se pierde sin dar "
        "ningún error"
    )


def test_esta_registrada_en_los_routers():
    """De nada sirve si no cuelga de las rutas. Fue exactamente el fallo de
    `ABACMiddleware`: escrito, probado y conectado a nada."""
    import app.main  # noqa: F401 — el registro ocurre al importar
    from app.core.timezone_context import bind_request_timezone

    guardas = [
        d.dependency for d in getattr(app.main, "_ROUTER_GUARDS", [])
    ]
    assert bind_request_timezone in guardas, (
        "bind_request_timezone no está en _ROUTER_GUARDS: la zona no se publicaría "
        "en ninguna petición"
    )


# ── Las cinco filas medidas ───────────────────────────────────────────────────

_VAR = contextvars.ContextVar("prueba_zona", default="SIN-PONER")


def _app_de_prueba() -> FastAPI:
    """App mínima con las cuatro combinaciones dependencia/endpoint."""
    app = FastAPI()

    def dep_sync():
        _VAR.set("dep-sync")

    async def dep_async():
        _VAR.set("dep-async")

    def servicio_profundo():
        """Emula una función de servicio: no recibe el usuario ni la zona."""
        return _VAR.get()

    @app.get("/sync-sync", dependencies=[Depends(dep_sync)])
    def a():
        return {"visto": _VAR.get()}

    @app.get("/sync-async", dependencies=[Depends(dep_sync)])
    async def b():
        return {"visto": _VAR.get()}

    @app.get("/async-sync", dependencies=[Depends(dep_async)])
    def c():
        return {"visto": _VAR.get()}

    @app.get("/async-async", dependencies=[Depends(dep_async)])
    async def d():
        return {"visto": _VAR.get()}

    @app.get("/profundo", dependencies=[Depends(dep_async)])
    def e():
        return {"visto": servicio_profundo()}

    return app


@pytest.mark.parametrize(
    "ruta,esperado",
    [
        # Una dependencia SÍNCRONA no publica nada: corre en el threadpool.
        ("/sync-sync", "SIN-PONER"),
        ("/sync-async", "SIN-PONER"),
        # Una ASÍNCRONA sí, y llega tanto al endpoint async como al sync...
        ("/async-sync", "dep-async"),
        ("/async-async", "dep-async"),
        # ...y a las funciones que el endpoint llame, que es donde están los
        # `date.today()` que se estaban arreglando. Ésta es la fila que importa.
        ("/profundo", "dep-async"),
    ],
)
def test_propagacion_del_contextvar(ruta, esperado):
    with TestClient(_app_de_prueba()) as c:
        assert c.get(ruta).json()["visto"] == esperado


# ── `today()` como sustituto de `date.today()` ────────────────────────────────

def test_today_fuera_de_peticion_equivale_a_un_servidor_en_utc():
    """Seeds, scripts y tareas sin organización en contexto: sin sorpresas."""
    assert today() == datetime.now(UTC).date()


def test_today_devuelve_un_dia_de_calendario():
    assert isinstance(today(), date)


def test_today_sigue_la_zona_del_contexto():
    """El caso de México: a las 05:30 UTC del 29 allí es todavía el 28."""
    with using_zone(resolve_zone("Pacific/Kiritimati")):  # UTC+14
        kiritimati = today()
    with using_zone(resolve_zone("Pacific/Niue")):  # UTC-11
        niue = today()
    # 25 horas de diferencia: en algún momento del día son días distintos, y
    # nunca al revés.
    assert (kiritimati - niue).days in (0, 1)
    assert kiritimati >= niue


def test_using_zone_restaura_al_salir():
    antes = timeutil.current_zone()
    with using_zone(resolve_zone("Asia/Tokyo")):
        assert str(timeutil.current_zone()) == "Asia/Tokyo"
    assert timeutil.current_zone() is antes


def test_using_zone_restaura_tambien_si_hay_excepcion():
    """Sin esto, un error dentro del bloque dejaría la zona contaminada para lo
    que viniese después en la misma tarea."""
    antes = timeutil.current_zone()
    with pytest.raises(ValueError):
        with using_zone(resolve_zone("Asia/Tokyo")):
            raise ValueError("algo falla")
    assert timeutil.current_zone() is antes


def test_using_zone_anida():
    with using_zone(resolve_zone("Europe/Madrid")):
        with using_zone(resolve_zone("Asia/Tokyo")):
            assert str(timeutil.current_zone()) == "Asia/Tokyo"
        assert str(timeutil.current_zone()) == "Europe/Madrid"


def test_using_organization_zone_lee_la_zona_de_la_organizacion():
    from app.core.timeutil import using_organization_zone

    class _Org:
        timezone = "America/Bogota"

    with using_organization_zone(_Org()):
        assert str(timeutil.current_zone()) == "America/Bogota"


def test_una_organizacion_sin_zona_cae_a_utc_sin_lanzar():
    from app.core.timeutil import using_organization_zone

    class _Org:
        timezone = None

    with using_organization_zone(_Org()):
        assert timeutil.current_zone() is UTC


# ── Que el barrido se hizo de verdad ──────────────────────────────────────────

def test_no_quedan_date_today_en_servicios_ni_api():
    """El barrido cubrió services/, api/ y core/. Este test lo mantiene.

    Se excluyen los seeds a propósito: generan datos de demostración fuera de
    cualquier petición, no hay usuario a quien preguntar y el contexto vale UTC,
    que es exactamente lo que ya hacían. Y `timeutil.py` los menciona en su propia
    documentación.
    """
    import pathlib
    import re

    raiz = pathlib.Path(__file__).resolve().parent.parent
    patron = re.compile(r"\bdate\.today\(\)")
    culpables = []
    for zona in ("app/services", "app/api", "app/core"):
        for p in (raiz / zona).rglob("*.py"):
            if p.name in ("timeutil.py", "timezone_context.py"):
                continue
            texto = p.read_text(encoding="utf-8", errors="replace")
            for i, linea in enumerate(texto.split("\n"), 1):
                # Las menciones en comentarios documentan el arreglo.
                if patron.search(linea) and not linea.lstrip().startswith(("#", "*", '"')):
                    culpables.append(f"{p.relative_to(raiz).as_posix()}:{i}")

    assert not culpables, (
        "quedan date.today() sin encaminar por timeutil.today():\n  "
        + "\n  ".join(culpables)
    )
