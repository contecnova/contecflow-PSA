"""Auditoria 2026-11 (#25): ningun `except Exception` se traga el error sin dejar rastro.

Antes: 207 manejadores amplios sin log ni re-raise (p. ej. en metricas un fallo
de BD se pintaba como "sin datos"). Este codemod mete como primera linea del
manejador un log con la traza:

- `warning` si el `try` hace E/S (BD, HTTP, SMTP, ficheros): es un fallo real;
- `debug` si no (conversiones y fallbacks esperables), para no llenar el log.

No cambia el flujo: el manejador sigue devolviendo lo mismo. Idempotente.
Uso: python scripts/codemods/except_silenciosos.py [--dry-run]
"""
from __future__ import annotations

import ast
import pathlib
import re
import sys

IO = re.compile(r"\.(query|execute|scalar|scalars|all|first|one|commit|flush|refresh|get|post|put|patch|delete|request|send|sendmail|send_message|urlopen|open|read|write|connect)\(|httpx|requests\.|urlopen|smtplib|abrir\(")
LOG = {"debug", "info", "warning", "error", "exception", "critical", "log", "print_exc", "capture_exception", "warn"}


def amplio(t) -> bool:
    if t is None:
        return True
    n = t.id if isinstance(t, ast.Name) else (t.attr if isinstance(t, ast.Attribute) else None)
    return n in ("Exception", "BaseException")


def deja_rastro(body) -> bool:
    for nodo in ast.walk(ast.Module(body=body, type_ignores=[])):
        if isinstance(nodo, ast.Raise):
            return True
        if isinstance(nodo, ast.Call):
            f = nodo.func
            if (f.attr if isinstance(f, ast.Attribute) else getattr(f, "id", "")) in LOG:
                return True
    return False


def logger_del_modulo(arbol) -> str | None:
    for n in arbol.body:
        if isinstance(n, ast.Assign) and len(n.targets) == 1 and isinstance(n.targets[0], ast.Name):
            v = n.value
            if isinstance(v, ast.Call) and isinstance(v.func, ast.Attribute) and v.func.attr == "getLogger":
                return n.targets[0].id
    return None


def procesar(ruta: pathlib.Path, seco: bool) -> int:
    texto = ruta.read_text(encoding="utf-8")
    crlf = "\r\n" in texto
    lineas = texto.replace("\r\n", "\n").split("\n")
    arbol = ast.parse(texto)
    padres = {}
    for p in ast.walk(arbol):
        for h in ast.iter_child_nodes(p):
            padres[h] = p
    objetivos = []
    for n in ast.walk(arbol):
        if isinstance(n, ast.Try):
            for h in n.handlers:
                if amplio(h.type) and not deja_rastro(h.body):
                    cuerpo_try = "\n".join(lineas[n.body[0].lineno - 1: h.lineno - 1])
                    nivel = "warning" if IO.search(cuerpo_try) else "debug"
                    p, func = padres.get(n), "<modulo>"
                    while p is not None:
                        if isinstance(p, (ast.FunctionDef, ast.AsyncFunctionDef)):
                            func = p.name
                            break
                        p = padres.get(p)
                    objetivos.append((h, nivel, func))
    if not objetivos:
        return 0
    nombre = logger_del_modulo(arbol)
    llamada = nombre or "logging.getLogger(__name__)"
    for h, nivel, func in sorted(objetivos, key=lambda x: -x[0].lineno):
        sentencia = f'{llamada}.{nivel}("{func}: excepcion ignorada", exc_info=True)'
        b0 = h.body[0]
        if b0.lineno == h.lineno:  # `except Exception: algo` en una linea
            linea = lineas[h.lineno - 1]
            cab, resto = linea[: b0.col_offset].rstrip(), linea[b0.col_offset:]
            ind = " " * (h.col_offset + 4)
            nuevas = [cab, ind + sentencia]
            if resto.strip() != "pass":
                nuevas.append(ind + resto)
            lineas[h.lineno - 1: h.lineno] = nuevas
        else:
            ind = " " * b0.col_offset
            if len(h.body) == 1 and isinstance(b0, ast.Pass) and lineas[b0.lineno - 1].strip().startswith("pass"):
                coment = lineas[b0.lineno - 1].strip()[4:].strip()
                lineas[b0.lineno - 1] = ind + sentencia + (f"  {coment}" if coment else "")
            else:
                lineas.insert(b0.lineno - 1, ind + sentencia)
    nuevo = "\n".join(lineas)
    if not nombre and not re.search(r"^import loggingb", nuevo, re.M):
        # Antes del primer import real (despues de `from __future__`), segun el AST.
        arbol2 = ast.parse(nuevo)
        imports = [n for n in arbol2.body if isinstance(n, (ast.Import, ast.ImportFrom))]
        futuros = [n for n in imports if isinstance(n, ast.ImportFrom) and n.module == "__future__"]
        ls = nuevo.split(chr(10))
        if futuros:
            ls.insert(futuros[-1].end_lineno, "import logging")
        elif imports:
            ls.insert(imports[0].lineno - 1, "import logging")
        else:
            ls.insert(0, "import logging")
        nuevo = chr(10).join(ls)
    ast.parse(nuevo)  # nunca dejar un fichero roto
    if not seco:
        ruta.write_text(nuevo.replace("\n", "\r\n") if crlf else nuevo, encoding="utf-8", newline="")
    return len(objetivos)


if __name__ == "__main__":
    seco = "--dry-run" in sys.argv
    total = ficheros = 0
    for f in sorted(pathlib.Path("app").rglob("*.py")):
        n = procesar(f, seco)
        if n:
            total += n
            ficheros += 1
    print(f"{'(seco) ' if seco else ''}{total} manejadores en {ficheros} ficheros")
