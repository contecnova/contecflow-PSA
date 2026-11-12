"""Ningun ciclo de imports a nivel de modulo en `app/` (auditoria 2026-11).

Medido antes: un ciclo de 19 modulos (`app.services.metrics` y sus
submodulos, por el registro). Se rompio sacando el registro a
`metrics/_registro.py`. Los imports dentro de funciones no cuentan: son la
forma aceptada de diferir una dependencia, y no rompen la carga del modulo.
"""
import ast
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]


def _modulos() -> dict[str, Path]:
    mods = {}
    for p in (RAIZ / "app").rglob("*.py"):
        if "__pycache__" in p.parts:
            continue
        partes = list(p.relative_to(RAIZ).with_suffix("").parts)
        if partes[-1] == "__init__":
            partes = partes[:-1]
        mods[".".join(partes)] = p
    return mods


def _grafo(mods: dict[str, Path]) -> dict[str, set[str]]:
    def resolver(nombre: str):
        while nombre and nombre not in mods:
            nombre = nombre.rsplit(".", 1)[0] if "." in nombre else ""
        return nombre or None

    aristas = {m: set() for m in mods}
    for m, p in mods.items():
        paquete = m if p.name == "__init__.py" else m.rsplit(".", 1)[0]
        for n in ast.parse(p.read_text(encoding="utf-8")).body:
            destinos = []
            if isinstance(n, ast.Import):
                destinos = [a.name for a in n.names]
            elif isinstance(n, ast.ImportFrom):
                base = n.module or ""
                if n.level:
                    partes = paquete.split(".")
                    base = ".".join(partes[: len(partes) - n.level + 1] + ([n.module] if n.module else []))
                destinos = [f"{base}.{a.name}" for a in n.names]
            for d in destinos:
                t = resolver(d)
                if t and t != m:
                    aristas[m].add(t)
    return aristas


def _ciclos(aristas: dict[str, set[str]]) -> list[list[str]]:
    sys.setrecursionlimit(max(sys.getrecursionlimit(), 10000))
    indice, bajo, en_pila, pila, salida, contador = {}, {}, set(), [], [], [0]

    def visitar(v):
        indice[v] = bajo[v] = contador[0]
        contador[0] += 1
        pila.append(v)
        en_pila.add(v)
        for w in aristas[v]:
            if w not in indice:
                visitar(w)
                bajo[v] = min(bajo[v], bajo[w])
            elif w in en_pila:
                bajo[v] = min(bajo[v], indice[w])
        if bajo[v] == indice[v]:
            comp = []
            while True:
                w = pila.pop()
                en_pila.discard(w)
                comp.append(w)
                if w == v:
                    break
            if len(comp) > 1:
                salida.append(sorted(comp))

    for v in aristas:
        if v not in indice:
            visitar(v)
    return salida


def test_no_hay_ciclos_de_import_a_nivel_de_modulo():
    ciclos = _ciclos(_grafo(_modulos()))
    assert ciclos == [], f"Ciclos de import a nivel de modulo: {ciclos}"
