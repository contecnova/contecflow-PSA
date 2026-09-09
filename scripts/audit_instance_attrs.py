"""Detector: atributos de INSTANCIA que la clase no tiene.

Uso:  python scripts/audit_instance_attrs.py

El tercero de la familia, despues de `audit_enum_members.py` (valores de
enumerado) y `audit_model_attrs.py` (atributos accedidos sobre la clase). Los
tres responden a la misma pregunta —«existe lo que este codigo esta
nombrando?»— sobre tres formas distintas de nombrarlo.

El frente que dejo abierto el caso de `art.content` —el cuerpo de un articulo
de la base de conocimiento es `art.body`—, y que el detector de clases no podia
ver: `art` es una instancia, no una clase.

La inferencia de tipos completa no hace falta. Con tres formas se cubre casi
todo el codigo real de este repositorio:

  1. **El bucle sobre una consulta.**
         for t in db.query(Ticket)...:  ->  `t` es un Ticket
     Tambien `for t in db.query(Ticket).filter(...).all()`.

  2. **La comprehension sobre una consulta.** Igual que el bucle.

  3. **La asignacion desde una consulta.**
         t = db.query(Ticket).filter(...).first()  ->  `t` es un Ticket
     y `.one()`, `.one_or_none()`, `.scalar()`, `.get()`.

  4. **El parametro anotado.**
         def f(ticket: Ticket):  ->  `ticket` es un Ticket

Lo que **no** cubre, y queda dicho: variables que vienen de una llamada a un
servicio (`ticket = svc.get_ticket(...)`), que es donde haria falta seguir el
tipo de retorno. Un detector que se equivoca por defecto sirve; uno que se
equivoca por exceso, no.

Sobre `db.query(Modelo.columna)` **no se opina**: eso devuelve filas de tuplas
con nombre, no instancias, y sus atributos son los de la propia consulta.
"""
from __future__ import annotations

import ast
import io
from pathlib import Path

import app.models  # noqa: F401  — registra todos los mapeadores
from app.db.base import Base

CLASES = {m.class_.__name__: m.class_ for m in Base.registry.mappers}

#: Los metodos de consulta que devuelven **una instancia**.
_DEVUELVEN_UNA = {"first", "one", "one_or_none", "scalar", "get"}

#: Atributos que existen en cualquier objeto y no son del modelo.
_UNIVERSALES = {"metadata", "registry"}


def _modelo_de_query(nodo) -> str | None:
    """Si `nodo` es una cadena `db.query(Modelo)...`, devuelve `Modelo`.

    Devuelve `None` cuando la consulta pide columnas (`db.query(Ticket.id)`) o
    varias entidades: en esos casos el resultado no es una instancia.
    """
    actual = nodo
    # Se desenrolla la cadena de llamadas hasta encontrar el `.query(...)`.
    while isinstance(actual, ast.Call):
        f = actual.func
        if isinstance(f, ast.Attribute) and f.attr == "query":
            if len(actual.args) != 1:
                return None
            arg = actual.args[0]
            if isinstance(arg, ast.Name) and arg.id in CLASES:
                return arg.id
            return None
        if isinstance(f, ast.Attribute):
            actual = f.value
            continue
        return None
    if isinstance(actual, ast.Attribute):
        return _modelo_de_query(actual.value)
    return None


def _ultimo_metodo(nodo) -> str | None:
    if isinstance(nodo, ast.Call) and isinstance(nodo.func, ast.Attribute):
        return nodo.func.attr
    return None


def _tipos_locales(funcion) -> dict[str, str]:
    """Nombre de variable -> nombre de modelo, dentro de una funcion.

    Un nombre ligado **mas de una vez** en la misma funcion se descarta, por
    cualquier via: reutilizar la variable hace que el tipo inferido de una
    ligadura se aplique a los usos de otra. Paso por ahi dos veces:

      1. En `_get_capacity_plans`, `p` es primero el `Project` de una
         comprehension y despues el `CapacityPlan` de un `for p in plans`.
         **Diez avisos de veinte eran ese unico caso.**
      2. Y descartar solo los nombres ligados a dos MODELOS distintos no basta:
         la segunda ligadura de `p` no es una consulta, asi que el detector no
         le asignaba tipo y no veia el conflicto. Hay que contar **todas** las
         ligaduras, no solo las que se saben tipar.

    Un detector que se equivoca por defecto sirve; uno que se equivoca por
    exceso, no.
    """
    tipos: dict[str, str] = {}

    # Cuantas veces se liga cada nombre en la funcion, por cualquier via. Un
    # nombre ligado mas de una vez se descarta al final.
    ligaduras: dict[str, int] = {}
    for nodo in ast.walk(funcion):
        if isinstance(nodo, ast.Name) and isinstance(nodo.ctx, ast.Store):
            ligaduras[nodo.id] = ligaduras.get(nodo.id, 0) + 1

    def _ligar(nombre: str, modelo: str) -> None:
        tipos[nombre] = modelo

    for arg in list(funcion.args.args) + list(funcion.args.kwonlyargs):
        anotacion = arg.annotation
        texto = ""
        if isinstance(anotacion, ast.Name):
            texto = anotacion.id
        elif isinstance(anotacion, ast.Constant) and isinstance(
                anotacion.value, str):
            texto = anotacion.value
        if texto in CLASES:
            _ligar(arg.arg, texto)

    for nodo in ast.walk(funcion):
        # for x in db.query(Modelo)...
        if isinstance(nodo, (ast.For, ast.AsyncFor)):
            if isinstance(nodo.target, ast.Name):
                modelo = _modelo_de_query(nodo.iter)
                metodo = _ultimo_metodo(nodo.iter)
                if modelo and metodo not in _DEVUELVEN_UNA:
                    _ligar(nodo.target.id, modelo)
        # [x.algo for x in db.query(Modelo)...]
        elif isinstance(nodo, (ast.ListComp, ast.GeneratorExp, ast.SetComp,
                               ast.DictComp)):
            for gen in nodo.generators:
                if isinstance(gen.target, ast.Name):
                    modelo = _modelo_de_query(gen.iter)
                    metodo = _ultimo_metodo(gen.iter)
                    if modelo and metodo not in _DEVUELVEN_UNA:
                        _ligar(gen.target.id, modelo)
        # x = db.query(Modelo)....first()
        elif isinstance(nodo, ast.Assign) and len(nodo.targets) == 1:
            destino = nodo.targets[0]
            if isinstance(destino, ast.Name):
                modelo = _modelo_de_query(nodo.value)
                metodo = _ultimo_metodo(nodo.value)
                if modelo and metodo in _DEVUELVEN_UNA:
                    _ligar(destino.id, modelo)
    return {n: m for n, m in tipos.items() if ligaduras.get(n, 1) <= 1}


def analizar():
    sospechosos = []
    for ruta in sorted(Path("app").rglob("*.py")):
        if "__pycache__" in ruta.parts:
            continue
        try:
            arbol = ast.parse(io.open(ruta, encoding="utf-8").read())
        except SyntaxError:
            continue
        for funcion in ast.walk(arbol):
            if not isinstance(funcion, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            tipos = _tipos_locales(funcion)
            if not tipos:
                continue
            for nodo in ast.walk(funcion):
                if not (isinstance(nodo, ast.Attribute)
                        and isinstance(nodo.value, ast.Name)):
                    continue
                modelo = tipos.get(nodo.value.id)
                if not modelo:
                    continue
                cls = CLASES[modelo]
                if nodo.attr.startswith("_") or nodo.attr in _UNIVERSALES:
                    continue
                if hasattr(cls, nodo.attr):
                    continue
                sospechosos.append(
                    (ruta.as_posix(), nodo.lineno, funcion.name,
                     nodo.value.id, modelo, nodo.attr))
    return sospechosos


if __name__ == "__main__":
    filas = analizar()
    print(f"{len(CLASES)} clases mapeadas")
    print()
    print("=" * 78)
    print("ATRIBUTOS DE INSTANCIA QUE LA CLASE NO TIENE")
    print("=" * 78)
    for ruta, linea, funcion, var, modelo, attr in filas:
        print(f"  {ruta}:{linea}  ({funcion})")
        print(f"       {var}.{attr}   donde {var} es {modelo}")
    print()
    print(f">>> {len(filas)} accesos")
