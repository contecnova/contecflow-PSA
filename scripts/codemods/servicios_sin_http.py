"""Codemod (auditoria 2026-11): los servicios lanzan `ErrorDeDominio`, no `HTTPException`.

Tres pasos, todos por posicion del AST (no por regex sobre el texto):

1. En todo `app/` y `tests/`: `except HTTPException` pasa a capturar tambien
   `ErrorDeDominio`, y `pytest.raises(HTTPException)` a aceptar ambos. Asi
   quien capturaba el error de un servicio lo sigue capturando.
2. En `app/services/`: cada llamada `HTTPException(...)` pasa a
   `ErrorDeDominio(...)` con los mismos argumentos (misma firma).
3. Imports: se anade `ErrorDeDominio` donde se usa y se quita `HTTPException`
   del import de fastapi donde ya no queda ninguna referencia.

Uso: python scripts/codemods/servicios_sin_http.py [--dry-run]
Idempotente: una segunda pasada no cambia nada.
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
IMPORT = "from app.core.errores import ErrorDeDominio"


def _leer(p: Path) -> tuple[str, str]:
    crudo = p.read_text(encoding="utf-8")
    with open(p, encoding="utf-8", newline="") as f:
        nl = "\r\n" if "\r\n" in f.read() else "\n"
    return crudo, nl


def _offsets(texto: str) -> list[int]:
    offs = [0]
    for linea in texto.split("\n"):
        offs.append(offs[-1] + len(linea) + 1)
    return offs


def _aplicar(texto: str, cambios: list[tuple[int, int, str]]) -> str:
    for ini, fin, nuevo in sorted(cambios, reverse=True):
        texto = texto[:ini] + nuevo + texto[fin:]
    return texto


def _es_http(n) -> bool:
    return isinstance(n, ast.Name) and n.id == "HTTPException"


def _paso_capturas(texto: str, es_test: bool) -> str:
    arbol = ast.parse(texto)
    offs = _offsets(texto)
    pos = lambda n: (offs[n.lineno - 1] + n.col_offset, offs[n.end_lineno - 1] + n.end_col_offset)  # noqa: E731
    cambios = []
    for n in ast.walk(arbol):
        if isinstance(n, ast.ExceptHandler) and n.type is not None:
            if _es_http(n.type):
                cambios.append((*pos(n.type), "(HTTPException, ErrorDeDominio)"))
            elif isinstance(n.type, ast.Tuple) and any(_es_http(e) for e in n.type.elts) \
                    and not any(isinstance(e, ast.Name) and e.id == "ErrorDeDominio" for e in n.type.elts):
                ultimo = n.type.elts[-1]
                fin = pos(ultimo)[1]
                cambios.append((fin, fin, ", ErrorDeDominio"))
        if es_test and isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) \
                and n.func.attr == "raises" and n.args and _es_http(n.args[0]):
            cambios.append((*pos(n.args[0]), "(HTTPException, ErrorDeDominio)"))
    return _aplicar(texto, cambios)


def _paso_llamadas(texto: str) -> str:
    arbol = ast.parse(texto)
    offs = _offsets(texto)
    cambios = []
    for n in ast.walk(arbol):
        if isinstance(n, ast.Call) and _es_http(n.func):
            ini = offs[n.func.lineno - 1] + n.func.col_offset
            cambios.append((ini, ini + len("HTTPException"), "ErrorDeDominio"))
    return _aplicar(texto, cambios)


def _paso_imports(texto: str) -> str:
    arbol = ast.parse(texto)
    usa_dominio = any(isinstance(n, ast.Name) and n.id == "ErrorDeDominio" for n in ast.walk(arbol))
    usa_http = any(isinstance(n, ast.Name) and n.id == "HTTPException" for n in ast.walk(arbol))
    offs = _offsets(texto)
    cambios = []
    if not usa_http:
        for n in ast.walk(arbol):
            if isinstance(n, ast.ImportFrom) and n.module == "fastapi" and any(a.name == "HTTPException" and not a.asname for a in n.names):
                resto = [a for a in n.names if a.name != "HTTPException" or a.asname]
                ini = offs[n.lineno - 1] + n.col_offset
                fin = offs[n.end_lineno - 1] + n.end_col_offset
                if resto:
                    nombres = ", ".join(a.name + (f" as {a.asname}" if a.asname else "") for a in resto)
                    cambios.append((ini, fin, f"from fastapi import {nombres}"))
                else:
                    # Quita la linea entera (incluido el salto) si queda vacia.
                    linea_ini = offs[n.lineno - 1]
                    if texto[linea_ini:ini].strip() == "":
                        cambios.append((linea_ini, offs[n.end_lineno], ""))
                    else:
                        cambios.append((ini, fin, "pass"))
    texto = _aplicar(texto, cambios)
    if usa_dominio and IMPORT not in texto:
        arbol = ast.parse(texto)
        lineas = texto.split("\n")
        tope = [n for n in arbol.body if isinstance(n, (ast.Import, ast.ImportFrom))]
        if tope:
            # Tras el bloque inicial de imports (hasta el primer hueco grande).
            fin_bloque = tope[0].end_lineno
            for n in tope[1:]:
                if n.lineno <= fin_bloque + 2:
                    fin_bloque = max(fin_bloque, n.end_lineno)
                else:
                    break
            despues = fin_bloque
        else:
            despues = 0
            if arbol.body and isinstance(arbol.body[0], ast.Expr) and isinstance(getattr(arbol.body[0], "value", None), ast.Constant):
                despues = arbol.body[0].end_lineno
        lineas.insert(despues, IMPORT)
        texto = "\n".join(lineas)
    return texto


def procesar(p: Path, dry: bool) -> bool:
    original, nl = _leer(p)
    texto = original.replace("\r\n", "\n")
    rel = p.relative_to(RAIZ).as_posix()
    es_test = rel.startswith("tests/")
    if "HTTPException" not in texto:
        return False
    nuevo = _paso_capturas(texto, es_test)
    if rel.startswith("app/services/"):
        nuevo = _paso_llamadas(nuevo)
    if nuevo != texto:
        nuevo = _paso_imports(nuevo)
    ast.parse(nuevo)  # nunca se escribe un fichero roto
    if nuevo == texto:
        return False
    if not dry:
        with open(p, "w", encoding="utf-8", newline="") as f:
            f.write(nuevo.replace("\n", nl))
    return True


def main() -> None:
    dry = "--dry-run" in sys.argv
    tocados = [p for d in ("app", "tests") for p in sorted((RAIZ / d).rglob("*.py"))
               if "__pycache__" not in p.parts and p.name != "errores.py" and procesar(p, dry)]
    print(f"{len(tocados)} ficheros {'a cambiar' if dry else 'cambiados'}")
    for p in tocados:
        print(" ", p.relative_to(RAIZ).as_posix())


if __name__ == "__main__":
    main()
