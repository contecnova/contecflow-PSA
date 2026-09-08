"""Llamadas del frontend a rutas que el backend no atiende.

Auditoría 2026-08. La pregunta espejo de `test_importes_diferidos.py`: en vez de
«¿el backend importa algo que no existe?», **«¿el frontend llama a rutas que no
existen?»**. Cada una es una acción de la interfaz que devuelve 404 y no puede
funcionar.

Salieron **69 de 1.140** llamadas con ruta literal — el **6 %**. Pero el número
en bruto engaña, y la parte que importa es la clasificación:

- **53 no las alcanza ninguna pantalla**: viven en código de cliente muerto. El
  caso que lo destapó fue `useAbsences.ts`, cuyos **nueve hooks no los usa ningún
  componente** — `AbsencesPage` llama directamente a las variantes `*My`, que sí
  existen. Reportar 69 «pantallas rotas» habría sido falso;
- **16 sí son alcanzables** desde una pantalla viva, y de ésas **7 eran sólo un
  prefijo o un nombre equivocado y están corregidas** (de ahí que la cifra baje a
  62), y **9 son endpoints que no existen** — trabajo de producto, listado en el
  traspaso.

El patrón que se repite en las siete corregidas: **el miembro correcto estaba al
lado del roto**. `epicsApi.roadmap` apuntaba a `/roadmap` y
`epicsApi.roadmapByProject`, la línea siguiente, a `/epics/roadmap`. Hay dos
clientes de subcontratistas, uno con el prefijo bueno y otro sin él. Es la misma
forma que los dos generadores de facturas del hallazgo 34.

| Corregido | Pasaba a | Pantalla |
|---|---|---|
| `GET/POST/PATCH/DELETE /wiki-tags/…` | `/cmdb/wiki-tags/…` | `WikiPage` — **toda** la gestión de etiquetas |
| `GET /roadmap` | `/epics/roadmap` | `EpicsPage` |
| `GET /subcontractors` | `/enterprise/subcontractors` | `EntitySelect` |
| `POST …/promote-known-error` | `…/promote-kedb` | `ITSMKnowledgeTab` |

## Por qué este test fija el número en vez de exigir cero

Las 62 que quedan **no se pueden verificar desde aquí**: hay 89 tests de frontend
y ninguno ejercita estas pantallas. Las siete corregidas lo están porque el
endpoint destino era inequívoco —mismo recurso, mismo sufijo, sólo el prefijo— y
porque las cuatro del wiki eran las cuatro operaciones del mismo recurso. Para
las demás, cambiar la ruta a ciegas puede sustituir el 404 por un error de
renderizado si la respuesta tiene otra forma, y sin abrir la interfaz no hay
manera de saber cuál de las dos cosas pasa.

Así que el trabajo se entrega **medido y listado**, para hacerlo pantalla por
pantalla con la interfaz delante, y este test impide que la cifra **crezca**: una
llamada nueva a una ruta inexistente lo pone en rojo con fichero y línea.

## La segunda tanda (2026-09): de 62 a 11

Se cerró el resto del código de cliente muerto y los remapeos inequívocos, y la
cifra baja de **62 a 11**.

**La causa raíz confirmada: clientes duplicados.** `projectSprintsApi` (12
métodos, todos correctos, lo usa `SprintsPage`) frente a `sprintsApi` (8 de 9
rotos, sin un solo consumidor). `deliverablesApi.listByProject` frente a `list`.
`absencesApi.review`/`updateMy`/`deleteMy` frente a `approve`/`reject`/`update`/
`delete`. Y `authApi.syncLdap` estaba **dos veces**, en `_core.ts` y en `auth.ts`,
las dos sin usar. Los seis módulos de hooks que consumían las versiones rotas
—`useSprints`, `useExpenses`, `useOKRs`, `useDeliverables`, `useAbsences`,
`useTickets`— no los importa ningún componente: sólo los reexporta el barrel.
Comprobado uno a uno.

Se fueron 53 líneas de método y 24 funciones de hook, `useDeliverables.ts`
completo, y se reescribieron 11 líneas. `tsc --noEmit` y `eslint` en verde.

**Un arreglo con efecto visible:** `dependenciesApi.get` pedía
`/dependencies/{id}` cuando el router es `/task-dependencies/{project_id}`.
Alimenta las dependencias del Gantt de proyecto, y la página trata la respuesta
fallida como lista vacía, así que el Gantt se dibujaba **sin dependencias y sin
error**.

**Las 11 que quedan son endpoints que no existen**, y con un patrón: el cliente
ofrece «traer uno» o «borrar» donde el backend sólo implementó el listado o el
`PATCH`. Dos son silenciosas como la del Gantt: el botón de borrar de un problema
y el de un cambio no borran nada. Implementarlas —o quitar el botón— es decisión
de producto, y por eso siguen aquí en vez de arregladas a ciegas.

> **Aviso, y viene de equivocarme yo.** Al medir esto por mi cuenta conté
> **declaraciones de método en `_core.ts`**, no puntos de llamada, y me dejé
> fuera `auth.ts`. Este test cuenta pares (verbo, ruta) de **todo** el frontend
> y empareja con el router real: es la cifra que vale. Las dos medidas coinciden
> ahora en 11, pero no coincidían al empezar.

## El detector usa el emparejador de Starlette, no una regex mía

`route.matches(scope)` es la autoridad sobre si una petición encuentra ruta. Mis
dos detectores anteriores en esta auditoría estuvieron mal por comparar formas a
mano, así que aquí la comparación la hace el propio router.
"""
from __future__ import annotations

import pathlib
import re

import pytest

#: Cuántas llamadas del frontend no encuentran ruta hoy. **No subir este número
#: para que el test pase**: si sube, hay una pantalla nueva que no puede
#: funcionar. Bajarlo es el objetivo, y cada bajada va con su pantalla
#: comprobada en la interfaz.
#:
#: 2026-09: baja de 62 a 11. Ver la sección «La segunda tanda» del docstring.
DESAJUSTES_CONOCIDOS = 11

_VERBOS = {"get": "GET", "post": "POST", "put": "PUT", "patch": "PATCH",
           "delete": "DELETE"}
_LLAMADA = re.compile(r"\bapi\.(get|post|put|patch|delete)\(\s*([`'\"])([^`'\"]*)\2")

#: El prefijo que el cliente de axios pone delante de todo
#: (`_core.ts`: `BASE_URL = import.meta.env.VITE_API_URL || '/api/v1'`).
_BASE = "/api/v1"


def _llamadas_del_frontend() -> dict[tuple[str, str], set[str]]:
    """Las llamadas con ruta literal, con `${…}` sustituido por un valor.

    Se saltan las que llevan plantillas anidadas o construyen la ruta por
    concatenación: no se pueden resolver estáticamente, y un test que bloquea
    debe equivocarse por defecto y no por exceso.
    """
    raiz = pathlib.Path("frontend/src")
    if not raiz.exists():
        pytest.skip("no hay frontend en este árbol de trabajo")

    llamadas: dict[tuple[str, str], set[str]] = {}
    for f in sorted(raiz.rglob("*.ts*")):
        txt = f.read_text(encoding="utf-8", errors="replace")
        for m in _LLAMADA.finditer(txt):
            verbo, ruta = m.group(1), m.group(3)
            if not ruta.startswith("/"):
                continue
            # plantilla anidada: la lectura estática no es fiable
            if re.sub(r"\$\{[^}]*\}", "", ruta).count("${"):
                continue
            ruta = ruta.split("?")[0]
            concreta = _BASE + re.sub(r"\$\{[^}]*\}", "x", ruta)
            clave = (_VERBOS[verbo], concreta.rstrip("/") or "/")
            linea = txt[:m.start()].count("\n") + 1
            llamadas.setdefault(clave, set()).add(f"{f.as_posix()}:{linea}")
    return llamadas


def _sin_ruta(llamadas) -> list[str]:
    """Las que ninguna ruta atiende, según el router de la propia aplicación."""
    from starlette.routing import Match

    from app.main import app

    faltan = []
    for (verbo, ruta), donde in sorted(llamadas.items()):
        scope = {"type": "http", "method": verbo, "path": ruta,
                 "root_path": "", "headers": [], "query_string": b""}
        if any(r.matches(scope)[0] == Match.FULL for r in app.router.routes):
            continue
        faltan.append(f"{verbo:6} {ruta}   ({sorted(donde)[0]})")
    return faltan


def test_EL_ESTRUCTURAL_no_aparecen_llamadas_nuevas_a_rutas_inexistentes():
    """El que impide que la cifra crezca.

    Una llamada nueva a una ruta que no existe es una pantalla que no puede
    funcionar, y hoy eso no lo detecta nada: el 404 sólo se ve abriendo esa
    pantalla concreta.
    """
    faltan = _sin_ruta(_llamadas_del_frontend())
    assert len(faltan) <= DESAJUSTES_CONOCIDOS, (
        "el frontend llama a %d rutas que no existen (conocidas: %d).\n"
        "Las nuevas están entre estas:\n  %s\n\n"
        "Cada una es una acción de la interfaz que devuelve 404. Corrige la ruta "
        "en el cliente de API, o añade el endpoint si de verdad falta."
        % (len(faltan), DESAJUSTES_CONOCIDOS, "\n  ".join(faltan))
    )


def test_la_cifra_conocida_no_esta_desfasada_a_la_baja():
    """Si se corrigen rutas, hay que bajar la constante.

    Sin esto, `DESAJUSTES_CONOCIDOS` se queda alto para siempre y el test deja de
    apretar: permitiría volver a introducir las que ya se arreglaron. Es el mismo
    razonamiento que la lista que caduca en `test_importes_diferidos.py`.
    """
    faltan = _sin_ruta(_llamadas_del_frontend())
    assert len(faltan) == DESAJUSTES_CONOCIDOS, (
        "hay %d desajustes y la constante dice %d: si has corregido rutas, baja "
        "`DESAJUSTES_CONOCIDOS` a %d para que el test siga apretando."
        % (len(faltan), DESAJUSTES_CONOCIDOS, len(faltan))
    )


def test_el_detector_lee_de_verdad_el_cliente_de_api():
    """Control de que el detector mira. Si leyera cero llamadas, los dos test de
    arriba pasarían sin comprobar nada — y eso es lo que hace inútil un
    estructural."""
    llamadas = _llamadas_del_frontend()
    assert len(llamadas) > 500, (
        "sólo se han leído %d llamadas del frontend: el detector está roto"
        % len(llamadas)
    )


def test_el_detector_reconoce_una_ruta_que_SI_existe():
    """La otra dirección: que no marque como inexistente algo que sí está.

    `GET /api/v1/projects` es de las más básicas; si el detector la diera por
    ausente, su cifra entera sería ruido.
    """
    assert _sin_ruta({("GET", "/api/v1/projects"): {"control"}}) == []


def test_el_detector_marca_una_ruta_inventada():
    inventada = {("GET", "/api/v1/no-existe-esta-ruta-de-ninguna-manera"): {"control"}}
    assert len(_sin_ruta(inventada)) == 1
