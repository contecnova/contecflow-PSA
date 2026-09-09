"""Cuenta los puntos de acceso a base de datos en la capa API, por AST.

Auditoria 2026-08 (hallazgo 22). El recuento se venia haciendo con `grep`:

    grep -rc 'db\\.query\\|db\\.add\\|db\\.commit\\|db\\.delete\\|db\\.flush' app/api/v1/endpoints/

Y eso **cuenta tambien las menciones en comentarios y docstrings**. En cuanto
las tandas empezaron a documentar en el propio codigo lo que habia antes —«esto
hacia `db.query(Asset).all()`»— el numero dejo de bajar al ritmo real: cada
explicacion escrita se contaba como un punto de acceso que sigue ahi.

Esto lo mide por arbol de sintaxis, asi que solo cuenta llamadas de verdad.
Distingue ademas dos cosas que no son lo mismo y conviene no sumar:

  · **acceso a datos**: `query`, `add`, `add_all`, `delete`, `flush`, `merge`,
    `execute`, `scalar`, `scalars`, `get` — lo que el hallazgo 22 pide mover a
    la capa de servicio;
  · **frontera de transaccion**: `commit`, `rollback`, `begin`, `close` y
    tambien **`refresh`** — que es legitimo que viva en el endpoint y se trata
    aparte.

`refresh` esta en el segundo grupo a proposito, y es una decision que conviene
justificar: no es una consulta que el endpoint elija hacer, es releer la fila
que el servicio acaba de devolver para recoger los valores que pone la base
(`id`, `created_at`, `server_default`). Va siempre pegado a un `commit`, asi que
pertenece a la frontera y no al acceso. Contarlo como acceso infla el numero con
**44 llamadas** —medidas, no estimadas— que no hay donde mover: ponerlas en el
servicio obligaria a que el servicio confirme, que es exactamente lo contrario
de lo que estas tandas hacen.

Uso:

    python scripts/audit_db_access_in_api.py             # resumen
    python scripts/audit_db_access_in_api.py --detalle    # linea a linea
    python scripts/audit_db_access_in_api.py --json
"""
from __future__ import annotations

import argparse
import ast
import json
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
DIRECTORIO = RAIZ / "app" / "api"

#: Los nombres de variable que son una sesion de SQLAlchemy en este repositorio.
NOMBRES_DE_SESION = {"db", "session", "_db"}

#: Metodos que son acceso a datos: lo que el hallazgo 22 pide mover.
ACCESO = {
    "query", "add", "add_all", "delete", "flush", "merge",
    "execute", "scalar", "scalars", "get",
}

#: Metodos que son frontera de transaccion: legitimos en el endpoint.
#: `refresh` esta aqui y no arriba; el porque, en el docstring del modulo.
TRANSACCION = {
    "commit", "rollback", "begin", "begin_nested", "close", "refresh",
}


def _puntos_de_un_fichero(ruta: Path) -> list[tuple[int, str, str]]:
    """(linea, metodo, clase) de cada llamada a la sesion en el fichero."""
    try:
        arbol = ast.parse(ruta.read_text(encoding="utf-8"))
    except SyntaxError as exc:  # pragma: no cover - no deberia pasar
        print(f"AVISO: {ruta} no se puede analizar: {exc}", file=sys.stderr)
        return []

    puntos = []
    for nodo in ast.walk(arbol):
        if not isinstance(nodo, ast.Call):
            continue
        funcion = nodo.func
        if not isinstance(funcion, ast.Attribute):
            continue
        objeto = funcion.value
        if not isinstance(objeto, ast.Name) or objeto.id not in NOMBRES_DE_SESION:
            continue
        metodo = funcion.attr
        if metodo in ACCESO:
            puntos.append((nodo.lineno, metodo, "acceso"))
        elif metodo in TRANSACCION:
            puntos.append((nodo.lineno, metodo, "transaccion"))
    return puntos


def medir() -> dict:
    por_fichero = {}
    for ruta in sorted(DIRECTORIO.rglob("*.py")):
        if "__pycache__" in ruta.parts:
            continue
        puntos = _puntos_de_un_fichero(ruta)
        if not puntos:
            continue
        relativa = ruta.relative_to(RAIZ).as_posix()
        por_fichero[relativa] = {
            "acceso": sum(1 for _, _, c in puntos if c == "acceso"),
            "transaccion": sum(1 for _, _, c in puntos if c == "transaccion"),
            "puntos": [
                {"linea": ln, "metodo": m, "clase": c} for ln, m, c in puntos
            ],
        }

    return {
        "ficheros": por_fichero,
        "total_acceso": sum(v["acceso"] for v in por_fichero.values()),
        "total_transaccion": sum(v["transaccion"] for v in por_fichero.values()),
        "ficheros_con_acceso": sum(
            1 for v in por_fichero.values() if v["acceso"]),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--detalle", action="store_true",
                        help="una linea por punto de acceso")
    parser.add_argument("--json", action="store_true", dest="como_json")
    args = parser.parse_args()

    datos = medir()
    if args.como_json:
        print(json.dumps(datos, indent=2, ensure_ascii=False))
        return 0

    print(f"Acceso a datos en la capa API: {datos['total_acceso']} puntos "
          f"en {datos['ficheros_con_acceso']} ficheros")
    print(f"Fronteras de transaccion:      {datos['total_transaccion']} "
          f"(legitimas en el endpoint, se tratan aparte)")
    print()

    filas = sorted(
        ((v["acceso"], v["transaccion"], f) for f, v in datos["ficheros"].items()),
        reverse=True,
    )
    for acceso, transaccion, fichero in filas:
        if not acceso:
            continue
        print(f"  {acceso:3d} acceso  {transaccion:3d} tx   {fichero}")
        if args.detalle:
            for punto in datos["ficheros"][fichero]["puntos"]:
                if punto["clase"] == "acceso":
                    print(f"        :{punto['linea']:<5d} db.{punto['metodo']}()")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
