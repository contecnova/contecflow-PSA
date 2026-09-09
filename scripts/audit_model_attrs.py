"""Detector: accesos a atributos de modelo que no existen.

Uso:  python scripts/audit_model_attrs.py

**Devuelve candidatos, no defectos.** Cada linea hay que verificarla: el lado de
la clase se resuelve con `hasattr` sobre la clase mapeada de verdad, asi que un
falso positivo es raro, pero **un acceso puede estar en una rama muerta**, y
entonces no hace dano hoy aunque este mal escrito. La diferencia importa y no la
puede decidir un script.

Misma pregunta que la de los enumerados, aplicada a las clases mapeadas. Salio
de dos defectos que el detector de enumerados no podia ver:

  · `SLAPolicy.response_hours` — las columnas son `p1_response_hours` ...
    `p4_response_hours`, una por prioridad;
  · `Ticket.requester_phone` — no existe, y estaba detras de un `hasattr` que
    solo protege el valor y no la palabra clave.

La comprobacion del lado de la clase se hace con `hasattr` sobre la clase
mapeada de verdad, no por AST: asi cubre columnas, relaciones, propiedades
hibridas, metodos y todo lo heredado, con muy pocos falsos positivos.
"""
from __future__ import annotations

import ast
import io
from pathlib import Path

import app.models  # noqa: F401  — registra todos los mapeadores
from app.db.base import Base

# Todas las clases mapeadas, por nombre.
clases = {}
for mapeador in Base.registry.mappers:
    cls = mapeador.class_
    clases[cls.__name__] = cls

print(f"{len(clases)} clases mapeadas")

sospechosos = []
for ruta in sorted(Path("app").rglob("*.py")):
    if "__pycache__" in ruta.parts:
        continue
    try:
        arbol = ast.parse(io.open(ruta, encoding="utf-8").read())
    except SyntaxError:
        continue
    for nodo in ast.walk(arbol):
        if not (isinstance(nodo, ast.Attribute)
                and isinstance(nodo.value, ast.Name)):
            continue
        nombre = nodo.value.id
        cls = clases.get(nombre)
        if cls is None:
            continue
        if nodo.attr.startswith("_") or nodo.attr in ("metadata", "registry"):
            continue
        if hasattr(cls, nodo.attr):
            continue
        sospechosos.append((ruta.as_posix(), nodo.lineno, nombre, nodo.attr))

print()
print("=" * 78)
print("ACCESOS A UN ATRIBUTO QUE LA CLASE MAPEADA NO TIENE")
print("=" * 78)
for fichero, linea, nombre, attr in sospechosos:
    print(f"  {fichero}:{linea} -> {nombre}.{attr}")
print(f"\n>>> {len(sospechosos)} accesos")

# Y el caso hermano: palabras clave en el constructor que no son columnas.
print()
print("=" * 78)
print("CONSTRUCTORES CON UNA PALABRA CLAVE QUE NO ES ATRIBUTO DE LA CLASE")
print("=" * 78)
malos_kwargs = []
for ruta in sorted(Path("app").rglob("*.py")):
    if "__pycache__" in ruta.parts:
        continue
    try:
        arbol = ast.parse(io.open(ruta, encoding="utf-8").read())
    except SyntaxError:
        continue
    for nodo in ast.walk(arbol):
        if not (isinstance(nodo, ast.Call) and isinstance(nodo.func, ast.Name)):
            continue
        cls = clases.get(nodo.func.id)
        if cls is None:
            continue
        for kw in nodo.keywords:
            if kw.arg is None:  # **kwargs
                continue
            if not hasattr(cls, kw.arg):
                malos_kwargs.append(
                    (ruta.as_posix(), nodo.lineno, nodo.func.id, kw.arg))

for fichero, linea, nombre, kw in malos_kwargs:
    print(f"  {fichero}:{linea} -> {nombre}({kw}=...)")
print(f"\n>>> {len(malos_kwargs)} constructores")
