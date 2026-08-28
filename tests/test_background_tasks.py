"""Tareas de segundo plano con referencia fuerte (auditoría 2026-08, P2-15).

Había cinco `create_task(...)` cuyo resultado se descartaba. No es estilo:
**asyncio sólo guarda una referencia débil a la tarea**, así que el recolector de
basura puede destruirla antes de que acabe. El síntoma es de los peores de
diagnosticar — notificaciones y mensajes de chat que se pierden a veces, sin
error y sin patrón reproducible.
"""
from __future__ import annotations

import asyncio
import gc

import pytest

from app.core.background import pending_count, spawn


@pytest.fixture
def anyio_backend():
    """Sólo asyncio: `spawn` se apoya en el bucle de asyncio a propósito.

    anyio ejecuta por defecto cada test con asyncio y con trio; bajo trio no hay
    bucle de asyncio y `spawn` devuelve None por diseño.
    """
    return "asyncio"


@pytest.mark.anyio
async def test_la_tarea_termina_aunque_no_se_guarde_el_retorno():
    """El caso que fallaba: nadie conserva la referencia y se fuerza un GC."""
    visto: list[str] = []

    async def trabajo() -> None:
        await asyncio.sleep(0.01)
        visto.append("hecho")

    spawn(trabajo(), name="prueba-gc")  # se descarta el retorno a propósito
    gc.collect()                        # el escenario que destruía la tarea
    await asyncio.sleep(0.05)

    assert visto == ["hecho"], (
        "la tarea no llegó a ejecutarse: sin referencia fuerte el GC se la lleva"
    )


@pytest.mark.anyio
async def test_la_referencia_se_libera_al_terminar():
    """El conjunto no debe crecer sin límite: sería una fuga de memoria."""
    antes = pending_count()

    async def trabajo() -> None:
        await asyncio.sleep(0.01)

    for _ in range(5):
        spawn(trabajo(), name="prueba-limpieza")
    assert pending_count() >= antes + 5

    await asyncio.sleep(0.08)
    assert pending_count() == antes, (
        "las tareas terminadas no se descartaron del conjunto"
    )


@pytest.mark.anyio
async def test_una_excepcion_en_la_tarea_no_se_pierde(caplog):
    """Antes, una tarea lanzada y olvidada que fallara no dejaba rastro."""

    async def revienta() -> None:
        raise ValueError("fallo de prueba en segundo plano")

    with caplog.at_level("WARNING", logger="contecflow.background"):
        spawn(revienta(), name="prueba-error")
        await asyncio.sleep(0.05)

    assert any("fallo de prueba en segundo plano" in r.message or
               "prueba-error" in r.message for r in caplog.records), (
        "la excepción de la tarea debe quedar registrada, no desaparecer"
    )


def test_sin_bucle_de_eventos_no_revienta_ni_deja_corrutinas_pendientes():
    """Muchos servicios se llaman desde código sincrónico (y desde tests).

    Debe devolver None y cerrar la corrutina limpiamente, sin el aviso
    "coroutine was never awaited".
    """
    async def trabajo() -> None:  # pragma: no cover - no se ejecuta a propósito
        await asyncio.sleep(0)

    assert spawn(trabajo()) is None


def _create_tasks_huerfanos(ruta) -> list[int]:
    """Líneas con `create_task(...)` cuyo resultado se DESCARTA.

    Se usa AST y no una expresión regular: un `asyncio.create_task(x)` dentro de
    una lista (`tasks = [create_task(a), create_task(b)]`) sí conserva la
    referencia y es correcto. Lo que delata al huérfano es que la llamada sea una
    sentencia de expresión por sí sola — nadie recoge el valor.
    """
    import ast

    tree = ast.parse(ruta.read_text(encoding="utf-8"))
    fuera: list[int] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Expr):
            continue
        call = node.value
        if isinstance(call, ast.Call) and getattr(call.func, "attr", None) == "create_task":
            fuera.append(node.lineno)
    return fuera


def test_los_cinco_puntos_usan_spawn():
    """Inventario: si alguien vuelve a un create_task huérfano, este test avisa."""
    import pathlib

    repo = pathlib.Path(__file__).resolve().parents[1]
    afectados = [
        "app/api/v1/endpoints/collaboration/ws.py",
        "app/services/client_portal_service.py",
        "app/services/collaboration/_queue.py",
        "app/services/collaboration/bots.py",
        "app/services/collaboration/messages.py",
    ]
    for rel in afectados:
        ruta = repo / rel
        assert "spawn(" in ruta.read_text(encoding="utf-8"), f"{rel} ya no usa spawn"
        huerfanas = _create_tasks_huerfanos(ruta)
        assert not huerfanas, (
            f"{rel} descarta el retorno de create_task en las líneas {huerfanas}; "
            "usa app.core.background.spawn para conservar la referencia"
        )


def test_el_inventario_no_marca_las_tareas_que_si_guardan_referencia():
    """Contrapeso del test anterior: evita que vuelva a dar falsos positivos.

    En ws.py hay tres `create_task` dentro de una lista `tasks = [...]` que luego
    se espera con `asyncio.wait`. Son correctos y no deben contarse. La primera
    versión de este inventario los marcaba con una regex — el error era del test.
    """
    import pathlib

    ws = pathlib.Path(__file__).resolve().parents[1] / "app/api/v1/endpoints/collaboration/ws.py"
    txt = ws.read_text(encoding="utf-8")
    assert txt.count("asyncio.create_task(") >= 3, (
        "se esperaban los create_task de la lista `tasks` en ws.py"
    )
    assert not _create_tasks_huerfanos(ws), (
        "los create_task de la lista `tasks` no deben contarse como huérfanos"
    )
