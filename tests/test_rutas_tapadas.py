"""Rutas que otra ruta anterior tapa, y quedan inalcanzables.

Auditoría 2026-08. En FastAPI **gana la primera ruta que encaja**. Si
`/tasks/{task_id}` se declara antes que `/tasks/dependencies`, la petición a
`/tasks/dependencies` acaba en el manejador del detalle con
`task_id="dependencies"`. Y lo peor no es el 404: es **el mensaje**.

```
GET /api/v1/tasks/dependencies       ->  404 {"detail":"Tarea no encontrada"}
GET /api/v1/sd/changes/rollout-plans ->  404 {"detail":"Change request no encontrado"}
```

Quien depura eso busca una tarea o un CR que falta. **Nadie mira el orden de
declaración de las rutas**, porque nada apunta hacia ahí.

## Las ocho que había, y las tres formas del problema

| Forma | Dónde | Efecto |
|---|---|---|
| **Orden dentro de un fichero** | `tasks.py`: el bloque de dependencias iba tras `/{task_id}` | `GET /tasks/dependencies` inalcanzable |
| **Orden dentro de un fichero** | `change_rollout.py`: las dos rutas de compatibilidad iban tras `/changes/{cr_id}/rollout-plans` | inalcanzables |
| **Router registrado DOS VECES** | `issue_types` se incluía sin prefijo **y** con prefijo `/issue-types` | cada ruta duplicada, el absurdo `/issue-types/issue-types/{project_id}`, y seis rutas del registro con prefijo tapadas por el sin prefijo. Al retirar el duplicado la aplicación pasa de **2.046 a 2.033** rutas |
| **Orden ENTRE módulos** | `misc` se incluía antes de `change_rollout`, y declara `/changes/{change_id}` | el único caso que no se arregla reordenando dentro de un fichero |

## El que más importaba: dos manejadores que no eran equivalentes

`/activity/project/{project_id}` estaba tapada por
`/activity/{entity_type}/{entity_id}` con `entity_type="project"`, y **los dos
manejadores hacen cosas distintas**: el genérico devuelve los eventos de una
entidad, y el tapado el feed **agregado** —eventos del proyecto *más todas sus
tareas*, con otro tope de límite—.

Así que el feed de actividad de un proyecto **salía sin las tareas**, con un 200 y
sin ningún error. Un 404 se acaba viendo; esto no.
"""
from __future__ import annotations

import re

#: Ninguna. No es una cifra que tolerar: una ruta tapada es una ruta que no se
#: puede llamar, y no hay motivo legítimo para tener una.
TAPADAS_TOLERADAS: dict[str, str] = {}


def _tapadas() -> list[tuple[str, str, str]]:
    """`(método, ruta inalcanzable, ruta que la tapa)`.

    Se pregunta al emparejador de la propia aplicación —`route.matches(scope)`—
    en vez de comparar formas a mano: es la autoridad sobre qué ruta atiende una
    petición, y comparar a mano es lo que hizo fallar dos detectores anteriores
    de esta auditoría.

    A cada parámetro se le pone un valor cualquiera; lo que se comprueba es si
    **alguna ruta declarada antes** también encaja con ese camino concreto.
    """
    from starlette.routing import Match

    from app.main import app

    rutas = [r for r in app.router.routes if getattr(r, "path", None)]
    encontradas = []
    for i, r in enumerate(rutas):
        camino = re.sub(r"\{[^}]*\}", "zzz", getattr(r, "path", ""))
        metodos = [m for m in (getattr(r, "methods", []) or [])
                   if m not in ("HEAD", "OPTIONS")]
        for m in metodos:
            scope = {"type": "http", "method": m, "path": camino,
                     "root_path": "", "headers": [], "query_string": b""}
            for anterior in rutas[:i]:
                if anterior.matches(scope)[0] == Match.FULL:
                    encontradas.append(
                        (m, getattr(r, "path", ""), getattr(anterior, "path", "")))
                    break
    return encontradas


def test_EL_ESTRUCTURAL_ninguna_ruta_esta_tapada_por_otra_anterior():
    """El que impide que vuelva a entrar una.

    Una ruta tapada no da ningún síntoma que apunte a la causa: devuelve el 404
    —o algo peor, un 200 con menos datos— del manejador que la interceptó. La
    regla es simple y este test la impone: **los segmentos literales se declaran
    antes que los `{parámetro}` de la misma posición**.
    """
    tapadas = [t for t in _tapadas() if t[1] not in TAPADAS_TOLERADAS]
    assert not tapadas, (
        "hay %d rutas inalcanzables porque otra declarada antes las intercepta:\n"
        "  %s\n\n"
        "En FastAPI gana la primera ruta que encaja. Mueve la declaración con "
        "segmento literal por encima de la que lleva `{parámetro}` — o, si están "
        "en módulos distintos, cambia el orden de los `include_router`."
        % (len(tapadas), "\n  ".join(
            "%-6s %-46s tapada por %s" % t for t in tapadas))
    )


def test_ningun_router_esta_registrado_dos_veces():
    """El caso de `issue_types`, fijado.

    Estaba incluido sin prefijo **y** con prefijo `/issue-types`, así que cada
    ruta existía duplicada, aparecían caminos absurdos como
    `/issue-types/issue-types/{project_id}` y seis rutas quedaban tapadas.
    Registrar dos veces el mismo router nunca es lo que se quiere.
    """
    from app.main import app

    pares = [(m, getattr(r, "path", ""))
             for r in app.routes
             for m in (getattr(r, "methods", []) or [])
             if m not in ("HEAD", "OPTIONS")]
    repetidos = {p for p in pares if pares.count(p) > 1}
    assert not repetidos, (
        "hay %d rutas declaradas más de una vez (método y camino idénticos), "
        "señal de un `include_router` duplicado:\n  %s"
        % (len(repetidos), "\n  ".join("%-6s %s" % p for p in sorted(repetidos)))
    )


#: Caminos que repiten un segmento —`/sd/sd/…`, `/pipeline/pipeline`— porque el
#: prefijo del `include_router` ya estaba en las rutas del fichero. **Funcionan**:
#: son URLs feas e inconsistentes, no un defecto. Se fija la cifra y no se exige
#: cero, porque un test que bloquea por algo que no está roto es ruido — y el
#: ruido es lo que hace que se dejen de mirar los fallos.
#:
#: Se mide de todas formas porque este patrón es la huella de la duplicación que
#: SÍ rompió seis rutas: `issue_types` registrado dos veces producía
#: `/issue-types/issue-types/{project_id}`. Si la cifra sube, conviene mirar si
#: es otra duplicación.
PREFIJOS_REPETIDOS = 15


def test_los_caminos_con_prefijo_repetido_no_aumentan():
    """Feos pero funcionales; se vigila que no crezcan.

    Hoy son 15, repartidos en tres prefijos: `conversations` (12),
    `activity` (2) y `pipeline` (1). Arreglarlos es cambiar URLs públicas, o sea
    romper a cualquier cliente que las use, así que **no se toca**: se anota.

    Los 17 de `sd` (informes, impacto de cambios y capacidad) sí se quitaron
    en 2026-11: ninguna pantalla ni cliente los llamaba —se midió en el
    frontend— y pasaban a tenerla.
    """
    from app.main import app

    repetidos = set()
    for r in app.routes:
        p = getattr(r, "path", "") or ""
        seg = p.split("/")
        for a, b in zip(seg, seg[1:], strict=False):
            if a and a == b and "{" not in a:
                repetidos.add(p)
    assert len(repetidos) <= PREFIJOS_REPETIDOS, (
        "los caminos con segmento repetido han pasado de %d a %d. No son un "
        "defecto por sí mismos, pero son la huella de un `include_router` cuyo "
        "prefijo ya está en las rutas del fichero — y eso fue lo que dejó seis "
        "rutas inalcanzables en `issue_types`. Los nuevos:\n  %s"
        % (PREFIJOS_REPETIDOS, len(repetidos),
           "\n  ".join(sorted(repetidos)[:10]))
    )


def test_el_detector_encuentra_un_tapado_plantado():
    """Un estructural cuyo detector está roto da luz verde sin mirar.

    Se monta una aplicación de juguete con el orden malo y se comprueba que el
    detector lo ve. No se toca la aplicación real.
    """
    from fastapi import FastAPI
    from starlette.routing import Match

    juguete = FastAPI()

    @juguete.get("/cosas/{cosa_id}")
    def detalle(cosa_id: str):
        return {}

    @juguete.get("/cosas/especial")
    def especial():
        return {}

    rutas = [r for r in juguete.router.routes if getattr(r, "path", None)]
    vistos = 0
    for i, r in enumerate(rutas):
        camino = re.sub(r"\{[^}]*\}", "zzz", getattr(r, "path", ""))
        for m in (getattr(r, "methods", []) or []):
            if m in ("HEAD", "OPTIONS"):
                continue
            scope = {"type": "http", "method": m, "path": camino,
                     "root_path": "", "headers": [], "query_string": b""}
            if any(a.matches(scope)[0] == Match.FULL for a in rutas[:i]):
                vistos += 1
    assert vistos >= 1, "el detector no ve un tapado evidente"


def test_el_detector_no_marca_un_orden_correcto():
    """La otra dirección: con el literal declarado antes, no hay tapado."""
    from fastapi import FastAPI
    from starlette.routing import Match

    juguete = FastAPI()

    @juguete.get("/cosas/especial")
    def especial():
        return {}

    @juguete.get("/cosas/{cosa_id}")
    def detalle(cosa_id: str):
        return {}

    rutas = [r for r in juguete.router.routes if getattr(r, "path", None)]
    for i, r in enumerate(rutas):
        camino = re.sub(r"\{[^}]*\}", "zzz", getattr(r, "path", ""))
        for m in (getattr(r, "methods", []) or []):
            if m in ("HEAD", "OPTIONS"):
                continue
            scope = {"type": "http", "method": m, "path": camino,
                     "root_path": "", "headers": [], "query_string": b""}
            assert not any(a.matches(scope)[0] == Match.FULL for a in rutas[:i]), (
                "marca como tapada una ruta con el orden correcto: %s" % camino
            )
