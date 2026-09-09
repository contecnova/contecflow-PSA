"""Detector: clases con el mismo nombre y contenido distinto, e importaciones cruzadas.

La pregunta que dejo abierta el hallazgo de `ChangeStatus`: hay dos enumerados
con el mismo nombre y valores distintos, uno de ellos muerto, y tres sitios
usaban un miembro que su enumerado no tiene. El modo de fallo es un
`AttributeError` en un camino que nadie ejercita.

Este detector hace dos pasadas:

  1. **Homonimos.** Clases con el mismo nombre definidas en mas de un modulo,
     con conjuntos de miembros DISTINTOS. Son las trampas.
  2. **Accesos imposibles.** Para cada `Nombre.miembro` donde `Nombre` es una
     clase definida en el repositorio, comprueba que `miembro` exista en alguna
     de las definiciones de ese nombre — y, si hay homonimos, en la que el
     fichero importa de verdad.
"""
from __future__ import annotations

import ast
import io
from collections import defaultdict
from pathlib import Path

RAIZ = Path("app")


def _miembros_de_clase(nodo: ast.ClassDef) -> set[str]:
    """Los nombres asignados directamente en el cuerpo de la clase."""
    nombres = set()
    for hijo in nodo.body:
        if isinstance(hijo, ast.Assign):
            for destino in hijo.targets:
                if isinstance(destino, ast.Name):
                    nombres.add(destino.id)
        elif isinstance(hijo, ast.AnnAssign) and isinstance(hijo.target, ast.Name):
            nombres.add(hijo.target.id)
        elif isinstance(hijo, (ast.FunctionDef, ast.AsyncFunctionDef)):
            nombres.add(hijo.name)
    return nombres


def _es_enum(nodo: ast.ClassDef) -> bool:
    for base in nodo.bases:
        nombre = base.id if isinstance(base, ast.Name) else getattr(base, "attr", "")
        if "Enum" in str(nombre):
            return True
    return False


# ── Pasada 1: recoger todas las clases ──────────────────────────────────────
definiciones: dict[str, list[tuple[str, set[str], bool]]] = defaultdict(list)
arboles: dict[str, ast.Module] = {}

for ruta in sorted(RAIZ.rglob("*.py")):
    if "__pycache__" in ruta.parts:
        continue
    try:
        arbol = ast.parse(io.open(ruta, encoding="utf-8").read())
    except SyntaxError:
        continue
    arboles[ruta.as_posix()] = arbol
    for nodo in ast.walk(arbol):
        if isinstance(nodo, ast.ClassDef):
            definiciones[nodo.name].append(
                (ruta.as_posix(), _miembros_de_clase(nodo), _es_enum(nodo)))

# ── Homonimos con contenido distinto ────────────────────────────────────────
print("=" * 78)
print("1. CLASES HOMONIMAS CON MIEMBROS DISTINTOS")
print("=" * 78)
homonimos = {}
for nombre, defs in sorted(definiciones.items()):
    if len(defs) < 2:
        continue
    conjuntos = [m for _, m, _ in defs]
    if all(c == conjuntos[0] for c in conjuntos):
        continue  # identicas: duplicacion, no trampa
    homonimos[nombre] = defs
    hay_enum = any(e for _, _, e in defs)
    print(f"\n{nombre}{'  [enum]' if hay_enum else ''}")
    for fichero, miembros, _es_enum in defs:
        print(f"    {fichero}")
        solo = miembros - set.intersection(*conjuntos) if len(conjuntos) > 1 else miembros
        if solo:
            print(f"        solo aqui: {sorted(solo)[:8]}")

print(f"\n>>> {len(homonimos)} nombres de clase con definiciones distintas")

# ── Pasada 2: accesos a miembros que no existen en ninguna definicion ──────
print()
print("=" * 78)
print("2. ACCESOS A UN MIEMBRO QUE NINGUNA DEFINICION DE ESE NOMBRE TIENE")
print("=" * 78)
imposibles = []
for fichero, arbol in arboles.items():
    for nodo in ast.walk(arbol):
        if not (isinstance(nodo, ast.Attribute) and isinstance(nodo.value, ast.Name)):
            continue
        nombre = nodo.value.id
        if nombre not in definiciones:
            continue
        # Solo clases que parecen enums o contenedores de constantes: si la
        # clase tiene metodos, los atributos de instancia no se ven por AST.
        defs = definiciones[nombre]
        if not any(e for _, _, e in defs):
            continue
        todos = set().union(*(m for _, m, _ in defs))
        if nodo.attr not in todos and not nodo.attr.startswith("_"):
            imposibles.append((fichero, nodo.lineno, nombre, nodo.attr))

for fichero, linea, nombre, miembro in imposibles:
    print(f"  {fichero}:{linea} -> {nombre}.{miembro}")
print(f"\n>>> {len(imposibles)} accesos imposibles en cualquier definicion")

# ── Pasada 3: el caso peligroso de verdad ──────────────────────────────────
print()
print("=" * 78)
print("3. HOMONIMOS DONDE UN FICHERO USA UN MIEMBRO QUE **SU** IMPORT NO TIENE")
print("=" * 78)


def _origen_importado(arbol: ast.Module, nombre: str) -> str | None:
    """De que modulo importa este fichero la clase `nombre`."""
    for nodo in ast.walk(arbol):
        if isinstance(nodo, ast.ImportFrom) and nodo.module:
            for alias in nodo.names:
                if (alias.asname or alias.name) == nombre:
                    return nodo.module
    return None


cruzados = []
for nombre, defs in homonimos.items():
    if not any(e for _, _, e in defs):
        continue
    for fichero, arbol in arboles.items():
        modulo = _origen_importado(arbol, nombre)
        if not modulo:
            continue
        # Que definicion corresponde a ese modulo.
        ruta_esperada = modulo.replace(".", "/")
        miembros_suyos = None
        for ruta_def, miembros, _ in defs:
            base = ruta_def[:-3]  # sin .py
            if base == ruta_esperada or base.endswith("/" + ruta_esperada) \
                    or base == ruta_esperada + "/__init__":
                miembros_suyos = miembros
                break
        if miembros_suyos is None:
            continue
        for nodo in ast.walk(arbol):
            if (isinstance(nodo, ast.Attribute)
                    and isinstance(nodo.value, ast.Name)
                    and nodo.value.id == nombre
                    and nodo.attr not in miembros_suyos
                    and not nodo.attr.startswith("_")):
                cruzados.append(
                    (fichero, nodo.lineno, nombre, nodo.attr, modulo))

for fichero, linea, nombre, miembro, modulo in cruzados:
    print(f"  {fichero}:{linea}")
    print(f"      usa {nombre}.{miembro}, pero importa {nombre} de {modulo},")
    print("      y esa definicion NO tiene ese miembro")
print(f"\n>>> {len(cruzados)} usos cruzados")
