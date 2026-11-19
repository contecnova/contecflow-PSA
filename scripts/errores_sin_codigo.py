"""Errores que ve el usuario sin codigo traducible: recuento y cuota (19-11-2026).

Un error del servidor que llega a la pantalla tiene que llevar `code` (y sus
`params`) del catalogo `app/core/codigos_de_error.py` para que la interfaz lo
pinte en el idioma del usuario; `detail` sigue en castellano por compatibilidad.
Este script cuenta, por fichero de `app/`, lo que todavia sale sin codigo:

- `dominio`: `ErrorDeDominio(...)` sin `code=`.
- `http`: `HTTPException(..., detail=<texto>)` (no admite codigo; usar
  `error(...)` de `app/core/codigos_de_error.py`). No cuenta los que no llevan
  `detail` ni los que llevan un dict (ya estructurado).
- `valor`: `raise ValueError(<texto>)` en `app/services` y `app/api` (acaban de
  `detail` via `except ValueError` + `str(e)`); usar `ErrorConCodigo(...)`.

La cuota vive en `scripts/errores-sin-codigo.json` ({fichero: total}). El test
`tests/test_errores_sin_codigo.py` falla si un fichero supera su cuota o si
aparece un fichero nuevo con errores sin codigo: la lista solo puede encoger.

Uso:
    python scripts/errores_sin_codigo.py              # resumen y top de ficheros
    python scripts/errores_sin_codigo.py --detalle    # ademas, cada linea
    python scripts/errores_sin_codigo.py --encoger    # baja la cuota a lo medido
                                                      # (nunca la sube)
"""
from __future__ import annotations

import ast
import json
import re
import sys
from collections import Counter
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
APP = RAIZ / "app"
CUOTA = RAIZ / "scripts" / "errores-sin-codigo.json"
#: Donde un `raise ValueError(texto)` acaba como `detail` de la respuesta.
_CON_VALOR = ("app/services/", "app/api/")
#: El propio catalogo (su `desde_valor` reenvia el texto de un `ValueError` ajeno).
_FUERA = {"app/core/codigos_de_error.py", "app/core/errores.py"}


def _nombre(func: ast.expr) -> str:
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return ""


#: `detail` que ya es un codigo estable que traduce la interfaz (`alm_*`,
#: `trad_*`...): `"alm_licencia_vencida"` o `f"alm_fecha_invalida:{campo}"`.
_CODIGO = re.compile(r"[a-z]+(?:_[a-z0-9]+)+")


def _es_texto(n: ast.expr | None) -> bool:
    """Texto libre: literal, f-string, `str(e)`, concatenacion, variable...
    No cuenta `None`, un dict (ya estructurado) ni un codigo `snake_case`."""
    if n is None:
        return False
    if isinstance(n, ast.Constant):
        return isinstance(n.value, str) and not _CODIGO.fullmatch(n.value.split(":", 1)[0])
    if isinstance(n, ast.Name) and n.id in ("codigo", "code"):
        return False  # variable que ya lleva un codigo (`alm_*`, `almint_*`)
    if isinstance(n, ast.JoinedStr) and n.values and isinstance(n.values[0], ast.Constant):
        cabeza = str(n.values[0].value)
        if ":" in cabeza and _CODIGO.fullmatch(cabeza.split(":", 1)[0]):
            return False
    return not isinstance(n, (ast.Dict, ast.DictComp))


def _detail(call: ast.Call, pos: int) -> ast.expr | None:
    for kw in call.keywords:
        if kw.arg == "detail":
            return kw.value
    return call.args[pos] if len(call.args) > pos else None


def hallazgos(ruta: Path) -> list[tuple[int, str]]:
    """[(linea, categoria)] de un fichero."""
    try:
        arbol = ast.parse(ruta.read_text(encoding="utf-8"))
    except (SyntaxError, UnicodeDecodeError):
        return []
    rel = ruta.relative_to(RAIZ).as_posix()
    con_valor = rel.startswith(_CON_VALOR)
    fuera: list[tuple[int, str]] = []
    for n in ast.walk(arbol):
        if isinstance(n, ast.Call):
            nombre = _nombre(n.func)
            if nombre == "ErrorDeDominio":
                if not any(kw.arg == "code" for kw in n.keywords) and _es_texto(_detail(n, 1)):
                    fuera.append((n.lineno, "dominio"))
            elif nombre == "HTTPException":
                if _es_texto(_detail(n, 1)):
                    fuera.append((n.lineno, "http"))
        elif con_valor and isinstance(n, ast.Raise) and isinstance(n.exc, ast.Call):
            if _nombre(n.exc.func) == "ValueError" and n.exc.args and _es_texto(n.exc.args[0]):
                fuera.append((n.lineno, "valor"))
    return sorted(fuera)


def medir() -> dict[str, list[tuple[int, str]]]:
    """{fichero relativo: hallazgos} de todo `app/` (solo los que tienen alguno)."""
    res = {}
    for f in sorted(APP.rglob("*.py")):
        if f.relative_to(RAIZ).as_posix() in _FUERA:
            continue
        h = hallazgos(f)
        if h:
            res[f.relative_to(RAIZ).as_posix()] = h
    return res


def totales(medido: dict[str, list]) -> dict[str, int]:
    return {f: len(h) for f, h in medido.items()}


def leer_cuota() -> dict[str, int]:
    if not CUOTA.exists():
        return {}
    return json.loads(CUOTA.read_text(encoding="utf-8"))


def escribir_cuota(cuota: dict[str, int]) -> None:
    CUOTA.write_text(json.dumps(dict(sorted(cuota.items())), ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


def encoger(medido: dict[str, list], cuota: dict[str, int], *, primera_vez: bool = False) -> dict[str, int]:
    """Nueva cuota: lo medido, sin superar nunca la anterior (salvo la primera vez)."""
    nueva = {}
    for f, n in totales(medido).items():
        nueva[f] = n if primera_vez else min(n, cuota.get(f, 0))
    return {f: n for f, n in nueva.items() if n > 0}


def main(argv: list[str]) -> int:
    medido = medir()
    por_cat = Counter(c for h in medido.values() for _, c in h)
    print(f"Ficheros con errores sin codigo: {len(medido)} · total {sum(por_cat.values())} "
          f"(dominio {por_cat['dominio']}, http {por_cat['http']}, valor {por_cat['valor']})")
    for f, n in sorted(totales(medido).items(), key=lambda x: -x[1])[:25]:
        print(f"  {n:4d}  {f}")
    if "--detalle" in argv:
        for f, h in medido.items():
            for linea, cat in h:
                print(f"{f}:{linea}: {cat}")
    if "--encoger" in argv:
        cuota = leer_cuota()
        nueva = encoger(medido, cuota, primera_vez=not CUOTA.exists())
        escribir_cuota(nueva)
        print(f"Cuota: {sum(cuota.values())} -> {sum(nueva.values())}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
