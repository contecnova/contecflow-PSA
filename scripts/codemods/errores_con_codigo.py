"""Errores con codigo traducible: catalogo generado y conversion de llamadas (19-11-2026).

Los textos de error libres (`ErrorDeDominio(404, "Épica no encontrada")`,
`HTTPException(400, "...")`, `raise ValueError("...")`) se pintaban en castellano
(o en ingles) a cualquier usuario. Este codemod los pasa a codigos del catalogo
`app/core/codigos_de_error.py`, que la interfaz traduce (`err_srv.<codigo>`).

Fuente: `scripts/codemods/errores_con_codigo/*.json`, cada uno con

    {"codigos": {"<codigo>": {"es": "...", "en": "...", "zh": "..."}},
     "que":     {"<entidad>": {"es": "...", "en": "...", "zh": "..."}},
     "textos":  {"<texto o plantilla>": {"code": "<codigo>", "params": {...},
                                         "vars": ["<dato>", ...]}},
     "entidades": {"<nombre en el texto>": "<entidad>"}}

- `textos`: la clave es el literal exacto o, para f-strings, la plantilla con
  `{}` por cada hueco; `vars` nombra cada hueco en orden (`{"code":
  "estado_no_valido", "vars": ["estado"]}` para `f"Estado no válido: {x}"`).
- `entidades`: "<X> no encontrado/a" / "<X> not found" pasa solo a
  `no_encontrado` con `que=<entidad>` si `<X>` esta aqui.

Modos:
    --sincronizar          regenera los bloques marcados del catalogo (Python)
                           y de `err_srv` en `frontend/src/i18n/langs/{es,en,zh}.mjs`.
    --aplicar [rutas...]   convierte las llamadas que casan (por defecto, todo
                           `app/api` y `app/services`); deja `detail=` con el
                           texto de siempre cuando difiere del catalogo.
    --pendientes [rutas]   lista los textos que aun no casan con nada.

Idempotente. Cada fichero tocado pasa `py_compile`.
"""
from __future__ import annotations

import ast
import json
import py_compile
import re
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
FUENTES = Path(__file__).resolve().parent / "errores_con_codigo"
CATALOGO = RAIZ / "app" / "core" / "codigos_de_error.py"
LANGS = RAIZ / "frontend" / "src" / "i18n" / "langs"
IDIOMAS = ("es", "en", "zh")

#: Como en `scripts/errores_sin_codigo.py`: `raise ValueError` solo cuenta aqui.
_CON_VALOR = ("app/services/", "app/api/")
_CODIGO = re.compile(r"[a-z]+(?:_[a-z0-9]+)+(?::.*)?", re.S)


def _ya_es_codigo(plantilla: str) -> bool:
    """`"alm_licencia_vencida"` o `"alm_fecha_invalida:{}"`: ya lo traduce la interfaz."""
    return bool(_CODIGO.fullmatch(plantilla))


_NO_ENCONTRADO = re.compile(r"^(?P<x>.+?)\s+(?:no encontrad[oa]s?|not found)\.?$", re.I)


# ── fuentes ──────────────────────────────────────────────────────────────────

def cargar() -> dict:
    res = {"codigos": {}, "que": {}, "textos": {}, "entidades": {}}
    for f in sorted(FUENTES.glob("*.json")):
        datos = json.loads(f.read_text(encoding="utf-8"))
        for sec in res:
            for k, v in (datos.get(sec) or {}).items():
                if k in res[sec] and res[sec][k] != v:
                    raise SystemExit(f"{f.name}: '{k}' de {sec} choca con otro fichero")
                res[sec][k] = v
    return res


# ── sincronizar ──────────────────────────────────────────────────────────────

def _bloque(texto: str, marca: str, lineas: list[str], sangria: str) -> str:
    ini = re.search(rf"^[ \t]*(?://|#) >>> {marca}\b.*$", texto, re.M)
    fin = re.search(rf"^[ \t]*(?://|#) <<< {marca}\s*$", texto, re.M)
    if not ini or not fin:
        raise SystemExit(f"faltan las marcas {marca}")
    cuerpo = "".join(f"{sangria}{l}\n" for l in lineas)
    return texto[: ini.end() + 1] + cuerpo + texto[fin.start():]


def _asegurar_marcas_mjs(texto: str) -> str:
    if "// >>> errores_con_codigo" in texto:
        return texto
    ini = texto.index("  err_srv: {")
    fin = texto.index("\n  },", ini)
    marcas = ("\n    // >>> errores_con_codigo (generado: scripts/codemods/errores_con_codigo.py --sincronizar)"
              "\n    // <<< errores_con_codigo")
    return texto[:fin] + marcas + texto[fin:]


def sincronizar() -> None:
    src = cargar()
    from importlib import reload
    sys.path.insert(0, str(RAIZ))
    import app.core.codigos_de_error as cat
    reload(cat)
    a_mano = {k: v for k, v in {**cat.MENSAJES, **cat.MENSAJES_DEL_OPERADOR}.items()}
    generados_antes = set(_generados_py())
    for c in src["codigos"]:
        if c in cat.MENSAJES:  # el portal tiene su texto en 8 idiomas: no se pisa
            raise SystemExit(f"el codigo '{c}' es del portal (MENSAJES): usa otro nombre para el operador")
        if c in a_mano and c not in generados_antes:
            raise SystemExit(f"el codigo '{c}' ya existe a mano en el catalogo: reutilizalo sin redefinirlo")
    py = CATALOGO.read_text(encoding="utf-8")
    py = _bloque(py, "errores_con_codigo",
                 [f"{json.dumps(c)}: {json.dumps(t['es'], ensure_ascii=False)}," for c, t in sorted(src["codigos"].items())],
                 "    ")
    py = _bloque(py, "que",
                 [f"{json.dumps(c)}: {json.dumps(t['es'], ensure_ascii=False)}," for c, t in sorted(src["que"].items())],
                 "    ")
    CATALOGO.write_text(py, encoding="utf-8")
    py_compile.compile(str(CATALOGO), doraise=True)
    for lang in IDIOMAS:
        f = LANGS / f"{lang}.mjs"
        texto = _asegurar_marcas_mjs(f.read_text(encoding="utf-8"))
        lineas = [f"{c}: {json.dumps(t[lang], ensure_ascii=False)}," for c, t in sorted(src["codigos"].items())]
        lineas += [f"que_{c}: {json.dumps(t[lang], ensure_ascii=False)}," for c, t in sorted(src["que"].items())]
        f.write_text(_bloque(texto, "errores_con_codigo", lineas, "    "), encoding="utf-8")
    print(f"sincronizado: {len(src['codigos'])} codigos, {len(src['que'])} entidades")


def _generados_py() -> list[str]:
    py = CATALOGO.read_text(encoding="utf-8")
    m = re.search(r">>> errores_con_codigo.*?\n(.*?)\n[ \t]*# <<< errores_con_codigo", py, re.S)
    return re.findall(r'^\s*"(\w+)":', m.group(1), re.M) if m else []


# ── aplicar ──────────────────────────────────────────────────────────────────

def _nombre(func: ast.expr) -> str:
    return func.id if isinstance(func, ast.Name) else (func.attr if isinstance(func, ast.Attribute) else "")


def _plantilla(n: ast.expr) -> tuple[str, list[ast.expr]] | None:
    """('texto con {}', [expresiones]) de un literal o f-string; None si no lo es."""
    if isinstance(n, ast.Constant) and isinstance(n.value, str):
        return n.value, []
    if isinstance(n, ast.JoinedStr):
        partes, exprs = [], []
        for v in n.values:
            if isinstance(v, ast.Constant):
                partes.append(str(v.value))
            elif isinstance(v, ast.FormattedValue):
                partes.append("{}")
                exprs.append(v.value)
            else:
                return None
        return "".join(partes), exprs
    return None


def _regla(src: dict, plantilla: str, n_exprs: int) -> dict | None:
    r = src["textos"].get(plantilla)
    if r:
        return r if (len(r.get("vars", [])) == n_exprs or r.get("ignora_huecos")) else None
    # "<X> no encontrado", "<X> '{}' no encontrada", "<X> {} not found": el
    # identificador no hace falta en el texto traducido (sigue en `detail`).
    limpio = re.sub(r"\s+", " ", re.sub(r"[#(]?'?\{\}'?\)?", "", plantilla)).strip(" :")
    m = _NO_ENCONTRADO.match(limpio)
    if m and m.group("x").strip() in src["entidades"]:
        return {"code": "no_encontrado", "params": {"que": src["entidades"][m.group("x").strip()]}}
    return None


def _texto_es(src: dict, code: str, params: dict) -> str | None:
    t = src["codigos"].get(code, {}).get("es")
    if t is None:
        sys.path.insert(0, str(RAIZ))
        from app.core.codigos_de_error import TODOS
        t = TODOS.get(code)
    if t is None:
        return None
    try:
        return t.format(**params)
    except (KeyError, IndexError, ValueError):
        return t


def _nombres_ligados(arbol: ast.AST) -> set[str]:
    nombres = set()
    for n in ast.walk(arbol):
        if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Store):
            nombres.add(n.id)
        elif isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            nombres.add(n.name)
        elif isinstance(n, ast.arg):
            nombres.add(n.arg)
        elif isinstance(n, ast.ExceptHandler) and n.name:
            nombres.add(n.name)
        elif isinstance(n, ast.alias):
            nombres.add((n.asname or n.name).split(".")[0])
    return nombres


def _import_existente(arbol: ast.Module, que: str) -> str | None:
    for n in ast.walk(arbol):
        if isinstance(n, ast.ImportFrom) and n.module == "app.core.codigos_de_error":
            for a in n.names:
                if a.name == que:
                    return a.asname or a.name
    return None


def _sin_http(texto: str) -> bool:
    """WebSockets: un `HTTPException` alli no pasa por el manejador; se deja."""
    return "WebSocket" in texto


def _offset(lineas: list[str], linea: int, col_bytes: int) -> int:
    """Indice de caracter absoluto a partir de (linea 1-based, columna en bytes)."""
    base = sum(len(l) for l in lineas[: linea - 1])
    return base + len(lineas[linea - 1].encode("utf-8")[:col_bytes].decode("utf-8"))


def _leer(ruta: Path) -> str:
    """Con sus finales de linea tal cual (CRLF o LF): no se reescribe el fichero entero."""
    with open(ruta, encoding="utf-8", newline="") as f:
        return f.read()


def _escribir(ruta: Path, texto: str) -> None:
    with open(ruta, "w", encoding="utf-8", newline="") as f:
        f.write(texto)


def convertir(ruta: Path, src: dict, pendientes: list | None = None) -> int:
    texto = _leer(ruta)
    try:
        arbol = ast.parse(texto)
    except SyntaxError:
        return 0
    lineas = texto.splitlines(keepends=True)
    ligados = _nombres_ligados(arbol)
    nombre_error = _import_existente(arbol, "error") or ("error" if "error" not in ligados else "error_con_codigo")
    nombre_valor = _import_existente(arbol, "ErrorConCodigo") or "ErrorConCodigo"
    cambios: list[tuple[int, int, str]] = []
    nombre_http = _import_existente(arbol, "error_http") or "error_http"
    usa_error = usa_valor = usa_http = False
    rel = ruta.relative_to(RAIZ).as_posix()
    for n in ast.walk(arbol):
        es_valor = es_http = False
        if isinstance(n, ast.Raise) and isinstance(n.exc, ast.Call) and _nombre(n.exc.func) == "ValueError":
            call, es_valor = n.exc, True
            if not call.args:
                continue
            det = call.args[0]
            status = None
        elif isinstance(n, ast.Call) and _nombre(n.func) in ("ErrorDeDominio", "HTTPException"):
            call = n
            es_http = _nombre(n.func) == "HTTPException"
            if es_http and _sin_http(texto):
                continue
            if any(k.arg == "code" for k in call.keywords):
                continue
            det = next((k.value for k in call.keywords if k.arg == "detail"), call.args[1] if len(call.args) > 1 else None)
            st = next((k.value for k in call.keywords if k.arg == "status_code"), call.args[0] if call.args else None)
            if det is None or st is None:
                continue
            status = ast.get_source_segment(texto, st)
        else:
            continue
        if es_valor and not rel.startswith(_CON_VALOR):
            continue
        pl = _plantilla(det)
        if pl is None or _ya_es_codigo(pl[0]):
            continue
        plantilla, exprs = pl
        regla = _regla(src, plantilla, len(exprs))
        if regla is None:
            if pendientes is not None:
                pendientes.append((rel, call.lineno, plantilla))
            continue
        code = regla["code"]
        params = dict(regla.get("params") or {})
        args = [json.dumps(code)]
        if es_valor:
            pass
        else:
            args.insert(0, status)
            cabeceras = next((k.value for k in call.keywords if k.arg == "headers"), call.args[2] if len(call.args) > 2 else None)
            if cabeceras is not None:
                args.append(ast.get_source_segment(texto, cabeceras))
        # El texto de siempre si el catalogo no lo da tal cual.
        if exprs:
            ref = _texto_es(src, code, {**params, **{v: "{}" for v in regla.get("vars", [])}})
            if ref is not None:
                ref = re.sub(r"\{\w+\}", "{}", ref)
            if ref != plantilla:
                args.append(f"detail={ast.get_source_segment(texto, det)}")
        else:
            if _texto_es(src, code, params) != plantilla:
                args.append(f"detail={json.dumps(plantilla, ensure_ascii=False)}")
        args += [f"{k}={json.dumps(v, ensure_ascii=False)}" for k, v in params.items()]
        args += [f"{v}={ast.get_source_segment(texto, e)}" for v, e in zip(regla.get("vars", []), exprs)]
        funcion = nombre_valor if es_valor else (nombre_http if es_http else nombre_error)
        nuevo = f"{funcion}({', '.join(args)})"
        ini = _offset(lineas, call.lineno, call.col_offset)
        fin = _offset(lineas, call.end_lineno, call.end_col_offset)
        cambios.append((ini, fin, nuevo))
        usa_valor |= es_valor
        usa_http |= es_http
        usa_error |= not es_valor and not es_http
    if not cambios:
        return 0
    for ini, fin, nuevo in sorted(cambios, reverse=True):
        texto = texto[:ini] + nuevo + texto[fin:]
    nuevos = []
    if usa_error and not _import_existente(arbol, "error"):
        nuevos.append("error" if nombre_error == "error" else "error as error_con_codigo")
    if usa_http and not _import_existente(arbol, "error_http"):
        nuevos.append("error_http")
    if usa_valor and not _import_existente(arbol, "ErrorConCodigo"):
        nuevos.append("ErrorConCodigo")
    if nuevos:
        texto = _anadir_import(texto, arbol, f"from app.core.codigos_de_error import {', '.join(nuevos)}")
    _escribir(ruta, texto)
    py_compile.compile(str(ruta), doraise=True)
    return len(cambios)


def _anadir_import(texto: str, arbol: ast.Module, linea: str) -> str:
    """Tras el ultimo import de cabecera (antes de cualquier otra sentencia)."""
    ultimo = None
    for n in arbol.body:
        if isinstance(n, (ast.Import, ast.ImportFrom)):
            ultimo = n
        elif isinstance(n, ast.Expr) and isinstance(n.value, ast.Constant) and ultimo is None:
            continue
        elif ultimo is not None:
            break
    lineas = texto.splitlines(keepends=True)
    pos = ultimo.end_lineno if ultimo else 0
    if ultimo is None and arbol.body and isinstance(arbol.body[0], ast.Expr):
        pos = arbol.body[0].end_lineno
    lineas.insert(pos, linea + ("\r\n" if "\r\n" in texto else "\n"))
    return "".join(lineas)


def _rutas(argv: list[str]) -> list[Path]:
    rutas = [Path(a) if Path(a).is_absolute() else RAIZ / a for a in argv if not a.startswith("--")]
    if not rutas:
        rutas = [RAIZ / "app" / "api", RAIZ / "app" / "services", RAIZ / "app" / "core"]
    res = []
    for r in rutas:
        res += sorted(r.rglob("*.py")) if r.is_dir() else [r]
    fuera = {CATALOGO.resolve(), (RAIZ / "app" / "core" / "errores.py").resolve()}
    return [r for r in res if r.resolve() not in fuera]


def main(argv: list[str]) -> int:
    if "--sincronizar" in argv:
        sincronizar()
    if "--aplicar" in argv or "--pendientes" in argv:
        src = cargar()
        pendientes: list = []
        total = 0
        for r in _rutas(argv):
            if "--aplicar" in argv:
                total += convertir(r, src, pendientes)
            else:
                convertir_sin_escribir(r, r.read_text(encoding="utf-8"), src, pendientes)
        if "--aplicar" in argv:
            print(f"convertidas: {total}")
        out = sys.stdout
        for rel, linea, pl in pendientes:
            out.buffer.write(f"{rel}:{linea}: {pl}\n".encode("utf-8"))
    return 0


def convertir_sin_escribir(ruta: Path, texto: str, src: dict, pendientes: list) -> None:
    try:
        arbol = ast.parse(texto)
    except SyntaxError:
        return
    rel = ruta.relative_to(RAIZ).as_posix()
    for n in ast.walk(arbol):
        if isinstance(n, ast.Raise) and isinstance(n.exc, ast.Call) and _nombre(n.exc.func) == "ValueError" and n.exc.args:
            det, call = n.exc.args[0], n.exc
        elif isinstance(n, ast.Call) and _nombre(n.func) in ("ErrorDeDominio", "HTTPException") \
                and not any(k.arg == "code" for k in n.keywords):
            call = n
            det = next((k.value for k in n.keywords if k.arg == "detail"), n.args[1] if len(n.args) > 1 else None)
        else:
            continue
        if _nombre(call.func) == "ValueError" and not rel.startswith(_CON_VALOR):
            continue
        pl = _plantilla(det) if det is not None else None
        if pl and not _ya_es_codigo(pl[0]) and _regla(src, pl[0], len(pl[1])) is None:
            pendientes.append((rel, call.lineno, pl[0]))


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
