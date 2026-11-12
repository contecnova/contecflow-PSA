"""Ningun `commit()` en `app/api/**`: la transaccion la decide el servicio.

Auditoria 2026-11 (#21). Medido antes: 51 llamadas a `.commit()` en 21
ficheros de endpoints (`db.commit()` y `session.commit()`). El endpoint decidia
la frontera de la transaccion, asi que la misma operacion llamada desde un
trabajo de Celery, un script o el bus de eventos no confirmaba —o confirmaba a
medias—. Se movieron, con la escritura que cerraban, a la funcion de servicio
correspondiente; el endpoint solo llama al servicio.

`PERMITIDOS` es la lista de excepciones, con su razon escrita. Hoy esta vacia:
no hizo falta ninguna. Una entrada nueva es una decision, no una salida.
"""
from __future__ import annotations

import ast
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
API = RAIZ / "app" / "api"

#: (fichero relativo a la raiz, funcion) -> razon. Vacia a proposito.
PERMITIDOS: dict[tuple[str, str], str] = {}


def _commits(raiz: Path) -> list[tuple[str, str, int]]:
    """(fichero, funcion que lo contiene, linea) por cada llamada `x.commit(...)`."""
    salida = []
    for p in sorted(raiz.rglob("*.py")):
        if "__pycache__" in p.parts:
            continue
        arbol = ast.parse(p.read_text(encoding="utf-8"))
        padres = {}
        for n in ast.walk(arbol):
            for h in ast.iter_child_nodes(n):
                padres[h] = n
        for n in ast.walk(arbol):
            if not (isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
                    and n.func.attr == "commit"):
                continue
            cur, funcion = padres.get(n), "<modulo>"
            while cur is not None:
                if isinstance(cur, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    funcion = cur.name
                    break
                cur = padres.get(cur)
            try:
                rel = p.relative_to(RAIZ).as_posix()
            except ValueError:
                rel = p.as_posix()
            salida.append((rel, funcion, n.lineno))
    return salida


def test_ningun_commit_en_la_capa_api():
    sobrantes = [c for c in _commits(API) if (c[0], c[1]) not in PERMITIDOS]
    assert not sobrantes, (
        "commit() en la capa API; la transaccion va en el servicio:\n  "
        + "\n  ".join(f"{f}:{ln} ({fn})" for f, fn, ln in sobrantes))


def test_los_permitidos_siguen_existiendo():
    """Una excepcion que ya no hace falta se borra, no se queda de alfombra."""
    reales = {(f, fn) for f, fn, _ in _commits(API)}
    obsoletos = sorted(set(PERMITIDOS) - reales)
    assert not obsoletos, f"entradas de PERMITIDOS que ya no existen: {obsoletos}"


def test_el_detector_ve_las_formas_que_habia(tmp_path):
    """El detector, contra las tres formas que se encontraron en el repo."""
    (tmp_path / "a.py").write_text(
        "def f(db):\n"
        "    db.commit()\n"
        "def g(session):\n"
        "    def interna():\n"
        "        session.commit()\n"
        "    return interna\n"
        "async def h(self):\n"
        "    self.db.commit()\n",
        encoding="utf-8",
    )
    vistos = {(fn, ln) for _, fn, ln in _commits(tmp_path)}
    assert vistos == {("f", 2), ("interna", 5), ("h", 8)}
