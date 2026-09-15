"""Busca funciones casi idénticas en `app/`, que es donde vive el defecto.

Auditoría 2026-09. La duplicación ha sido **el detector más productivo de toda
esta auditoría**, y hasta ahora se encontraba de casualidad, mirando otra cosa:

  · `task_service.py` y el subpaquete `tasks/` — cuatro funciones, y a una le
    faltaba la comprobación ABAC que la otra sí tenía (§3.novodecies);
  · dos marketplaces de integraciones, y cada uno era mejor en algo distinto:
    uno validaba la frecuencia y cifraba credenciales, el otro evitaba el N+1;
  · dos generadores de factura, y el que usaba la interfaz **no llevaba el NIF**;
  · `execute_report` y `execute_report_paginated`: 41 de 50 líneas idénticas;
  · `PUT` y `PATCH` de SCIM cubriendo campos distintos;
  · dos copias del sondeo SNMP que habían divergido.

El patrón se repite y es siempre el mismo: **dos copias no divergen a la vez, y
la que se arregla no suele ser la que se ejecuta**. Por eso un número de líneas
duplicadas no dice nada y una pareja concreta sí.

── Cómo mide ────────────────────────────────────────────────────────────────
Normaliza cada función a su **esqueleto de AST**: los nombres de variables
locales, las constantes y los comentarios desaparecen; quedan la forma de las
sentencias y los nombres que no son locales (atributos, llamadas, modelos). Dos
copias con las variables renombradas siguen saliendo iguales, que es justo el
caso que un `diff` de texto no ve.

Compara sólo funciones de tamaño parecido y con al menos `--min-sentencias`
sentencias, porque por debajo de eso el parecido no significa nada: cinco líneas
de `getattr` se repiten en todas partes y no son una copia, son un idioma.

── Lo que NO es ─────────────────────────────────────────────────────────────
No es un linter y no tiene un umbral que haya que dejar en cero. Dos funciones
parecidas pueden ser correctas —un CRUD por entidad se parece a otro—, así que
esto **señala parejas para mirar**, y lo que hay que preguntarle a cada una es
la pregunta que encontró todos los defectos de arriba: *¿en qué se diferencian,
y esa diferencia está puesta a propósito?*

    python scripts/audit_funciones_duplicadas.py            # informe
    python scripts/audit_funciones_duplicadas.py --umbral 0.95
"""
from __future__ import annotations

import argparse
import ast
import io
import sys
from collections import Counter, defaultdict
from difflib import SequenceMatcher
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent

#: Por debajo de esto el parecido es ruido: un `getattr` con respaldo, un
#: `raise HTTPException(404)`, un serializador de cuatro campos.
MIN_SENTENCIAS = 12

#: Dos funciones cuyo tamaño difiere más de esto no se comparan. Ahorra el 90 %
#: de las comparaciones sin perder ninguna pareja real: una copia con un bloque
#: de más sigue estando cerca, una reescritura no.
TOLERANCIA_TAMANO = 0.30

UMBRAL = 0.92


def _importados(nodo: ast.AST) -> set[str]:
    """Los nombres que la función importa dentro de su propio cuerpo.

    Este repositorio importa los modelos dentro de la función —para evitar
    ciclos—, así que `Task` y `Epic` son nombres **importados**, no variables
    locales. Distinguirlos importa, y el porqué está en `_esqueleto`.
    """
    nombres: set[str] = set()
    for hijo in ast.walk(nodo):
        if isinstance(hijo, (ast.Import, ast.ImportFrom)):
            for alias in hijo.names:
                nombres.add(alias.asname or alias.name.split(".")[0])
    return nombres


def _esqueleto(nodo: ast.AST) -> list[str]:
    """La forma de una función, sin nombres locales ni constantes.

    Se queda con el tipo de cada nodo y con los nombres que **no** son
    variables locales —atributos, funciones llamadas, palabras clave y lo que
    la función importa—, porque ésos son los que dicen qué hace. Un
    `for tarea in tareas` y un `for t in lista` producen el mismo esqueleto; un
    `db.commit()` y un `db.rollback()`, no.

    ## Por qué los nombres importados cuentan

    Lo aprendí usándolo: la primera versión los descartaba y dio como
    **idénticas** a `metric_tasks_by_status` y `metric_epics_by_status`, que son
    correctas y distintas — una consulta `Task` y la otra `Epic`. Como este
    repositorio importa los modelos dentro de la función, ambos eran
    `ast.Name` sin más, y la única diferencia real desaparecía en la
    normalización.

    Conservar el nombre importado arregla eso sin romper lo que el detector
    busca: renombrar una variable local sigue sin cambiar el esqueleto, que es
    lo que permite ver una copia con las variables cambiadas de nombre.
    """
    importados = _importados(nodo)
    piezas: list[str] = []
    for hijo in ast.walk(nodo):
        etiqueta = type(hijo).__name__
        if isinstance(hijo, ast.Attribute):
            etiqueta += f":{hijo.attr}"
        elif isinstance(hijo, ast.keyword) and hijo.arg:
            etiqueta += f":{hijo.arg}"
        elif isinstance(hijo, ast.Call) and isinstance(hijo.func, ast.Name):
            etiqueta += f":{hijo.func.id}"
        elif isinstance(hijo, ast.Name) and hijo.id in importados:
            etiqueta += f":{hijo.id}"
        elif isinstance(hijo, ast.alias):
            etiqueta += f":{hijo.asname or hijo.name}"
        piezas.append(etiqueta)
    return piezas


def _funciones(fichero: Path):
    try:
        arbol = ast.parse(io.open(fichero, encoding="utf-8").read())
    except (SyntaxError, UnicodeDecodeError):
        return
    for nodo in ast.walk(arbol):
        if not isinstance(nodo, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        sentencias = sum(1 for n in ast.walk(nodo) if isinstance(n, ast.stmt))
        if sentencias < MIN_SENTENCIAS:
            continue
        esqueleto = _esqueleto(nodo)
        yield {
            "fichero": fichero.relative_to(RAIZ).as_posix(),
            "nombre": nodo.name,
            "linea": nodo.lineno,
            "sentencias": sentencias,
            "esqueleto": esqueleto,
            # Prefiltro: el mismo esqueleto visto como bolsa de piezas. Comparar
            # dos bolsas es lineal; comparar dos secuencias con
            # `SequenceMatcher` es cuadratico. Y la bolsa es una **cota
            # superior** del parecido de las secuencias —reordenar no puede
            # subirlo—, asi que descartar por bolsa no pierde ninguna pareja.
            "bolsa": Counter(esqueleto),
        }


def parejas(ruta: str = "app", umbral: float = UMBRAL):
    """Las parejas de funciones con esqueleto casi idéntico, de más parecida a menos."""
    todas = [f for p in sorted((RAIZ / ruta).rglob("*.py")) for f in _funciones(p)]

    # Agrupar por tamaño para no comparar todas contra todas: son ~4.000
    # funciones, y la comparación completa serían ocho millones de pares.
    por_tamano: dict[int, list] = defaultdict(list)
    for f in todas:
        por_tamano[f["sentencias"]].append(f)

    vistas = set()
    fuera = []
    for f in todas:
        minimo = int(f["sentencias"] * (1 - TOLERANCIA_TAMANO))
        maximo = int(f["sentencias"] * (1 + TOLERANCIA_TAMANO)) + 1
        for tamano in range(minimo, maximo + 1):
            for g in por_tamano.get(tamano, ()):
                if f is g:
                    continue
                clave = tuple(sorted([
                    (f["fichero"], f["nombre"], f["linea"]),
                    (g["fichero"], g["nombre"], g["linea"]),
                ]))
                if clave in vistas:
                    continue
                vistas.add(clave)

                # Cota superior barata: si ni siquiera comparten esa proporcion
                # de piezas, ordenarlas no va a acercarlas.
                comunes = sum((f["bolsa"] & g["bolsa"]).values())
                cota = 2.0 * comunes / (len(f["esqueleto"]) + len(g["esqueleto"]))
                if cota < umbral:
                    continue

                # `autojunk=False`: con secuencias largas, la heuristica de
                # "elementos basura" de difflib descarta las piezas que se
                # repiten mucho —y en un esqueleto de AST eso es justo lo
                # estructural—, dando parecidos falsamente bajos.
                ratio = SequenceMatcher(
                    None, f["esqueleto"], g["esqueleto"], autojunk=False).ratio()
                if ratio >= umbral:
                    fuera.append((ratio, f, g))
    fuera.sort(key=lambda t: -t[0])
    return fuera, len(todas)


def _informe(umbral: float) -> int:
    encontradas, total = parejas(umbral=umbral)
    print(f"{total} funciones de >= {MIN_SENTENCIAS} sentencias en app/; "
          f"{len(encontradas)} parejas con esqueleto >= {umbral:.0%} igual\n")
    for ratio, f, g in encontradas:
        iguales = "IDENTICAS" if ratio == 1.0 else f"{ratio:.1%}"
        print(f"  {iguales:>9}  {f['fichero']}:{f['linea']} {f['nombre']}")
        print(f"             {g['fichero']}:{g['linea']} {g['nombre']}")
    if encontradas:
        print("\nLa pregunta para cada pareja: ¿en qué se diferencian, y esa "
              "diferencia está puesta a propósito?")
    return 0


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--umbral", type=float, default=UMBRAL)
    args = p.parse_args()
    raise SystemExit(_informe(args.umbral))
