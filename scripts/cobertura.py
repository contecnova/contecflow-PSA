"""Informe de cobertura de backend y frontend, sin umbrales (24-11-2026).

Se ejecuta a mano (`make cobertura`, `setup.bat cobertura`, `./setup.sh cobertura`);
no bloquea nada: sale con el código de los tests, nunca por un porcentaje.

Deja todo en `cobertura/` (ignorada por git):

    cobertura/backend/html/index.html     HTML de pytest-cov (fichero a fichero)
    cobertura/backend/coverage.json       datos crudos
    cobertura/backend/informe.txt         texto, un fichero por línea
    cobertura/frontend/index.html         HTML de @vitest/coverage-v8
    cobertura/frontend/coverage-summary.json
    cobertura/frontend/informe.txt        texto, un fichero por línea
    cobertura/resumen.txt                 resumen por módulo de los dos

Módulo = las dos primeras carpetas de la ruta (`app/services`, `src/pages`…);
`--profundidad 3` baja un nivel más.

Uso:
    python scripts/cobertura.py                       backend (suite entera, -n auto) + frontend
    python scripts/cobertura.py --solo backend tests/test_okrs.py
    python scripts/cobertura.py --solo frontend
    python scripts/cobertura.py --solo resumen        rehace resumen.txt con lo que ya hay

Lo que no reconoce se pasa a pytest (por defecto: `tests/ -n auto --tb=short -q`).
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
SALIDA = RAIZ / "cobertura"
BACK = SALIDA / "backend"
FRONT = SALIDA / "frontend"
PYTEST_POR_DEFECTO = ["tests/", "-n", "auto", "--tb=short", "-q"]


def _pct(cubiertas: int, total: int) -> float:
    return 100.0 * cubiertas / total if total else 100.0


def _tabla(filas: list[tuple[str, int, int]], titulo: str) -> list[str]:
    """filas: (nombre, cubiertas, total) → líneas de texto alineadas."""
    ancho = max([len(n) for n, _, _ in filas] + [len("TOTAL"), 10])
    lineas = [titulo, f"{'':{ancho}}  {'líneas':>8}  {'cubiertas':>9}  {'%':>6}"]
    for nombre, cub, tot in filas:
        lineas.append(f"{nombre:{ancho}}  {tot:>8}  {cub:>9}  {_pct(cub, tot):>5.1f}%")
    cub, tot = sum(f[1] for f in filas), sum(f[2] for f in filas)
    lineas.append(f"{'TOTAL':{ancho}}  {tot:>8}  {cub:>9}  {_pct(cub, tot):>5.1f}%")
    return lineas


def _agrupar(por_fichero: dict[str, tuple[int, int]], profundidad: int) -> list[tuple[str, int, int]]:
    grupos: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    for ruta, (cub, tot) in por_fichero.items():
        partes = ruta.split("/")
        clave = "/".join(partes[:min(profundidad, len(partes) - 1)] or partes[:1])
        grupos[clave][0] += cub
        grupos[clave][1] += tot
    return sorted((k, v[0], v[1]) for k, v in grupos.items())


def ficheros_backend() -> dict[str, tuple[int, int]]:
    datos = json.loads((BACK / "coverage.json").read_text(encoding="utf-8"))
    salida = {}
    for ruta, info in datos["files"].items():
        r = info["summary"]
        salida[Path(ruta).as_posix()] = (r["covered_lines"], r["num_statements"])
    return salida


def ficheros_frontend() -> dict[str, tuple[int, int]]:
    datos = json.loads((FRONT / "coverage-summary.json").read_text(encoding="utf-8"))
    raiz = (RAIZ / "frontend").resolve()
    salida = {}
    for ruta, info in datos.items():
        if ruta == "total":
            continue
        try:
            rel = Path(ruta).resolve().relative_to(raiz).as_posix()
        except ValueError:
            rel = Path(ruta).as_posix()
        salida[rel] = (info["lines"]["covered"], info["lines"]["total"])
    return salida


def escribir_informe(por_fichero: dict[str, tuple[int, int]], destino: Path, titulo: str) -> None:
    filas = sorted((r, c, t) for r, (c, t) in por_fichero.items())
    destino.write_text("\n".join(_tabla(filas, titulo)) + "\n", encoding="utf-8")


def backend(args_pytest: list[str]) -> int:
    BACK.mkdir(parents=True, exist_ok=True)
    shutil.rmtree(BACK / "html", ignore_errors=True)
    env = dict(os.environ, PYTHONUTF8="1", COVERAGE_FILE=str(BACK / ".coverage"))
    orden = [sys.executable, "-m", "pytest", *args_pytest,
             "--cov=app", "--cov-branch",
             f"--cov-report=html:{BACK / 'html'}",
             f"--cov-report=json:{BACK / 'coverage.json'}"]
    print("[cobertura] backend: pytest " + " ".join(args_pytest), flush=True)
    codigo = subprocess.run(orden, cwd=RAIZ, env=env).returncode
    if (BACK / "coverage.json").exists():
        escribir_informe(ficheros_backend(), BACK / "informe.txt", "Backend (líneas de app/)")
    return codigo


def frontend() -> int:
    npm = "npm.cmd" if os.name == "nt" else "npm"
    print("[cobertura] frontend: npm run test:coverage", flush=True)
    codigo = subprocess.run([npm, "run", "test:coverage"], cwd=RAIZ / "frontend").returncode
    if (FRONT / "coverage-summary.json").exists():
        escribir_informe(ficheros_frontend(), FRONT / "informe.txt", "Frontend (líneas de src/)")
    return codigo


def resumen(profundidad: int) -> None:
    lineas: list[str] = []
    if (BACK / "coverage.json").exists():
        lineas += _tabla(_agrupar(ficheros_backend(), profundidad), "== Backend, por módulo ==") + [""]
    if (FRONT / "coverage-summary.json").exists():
        lineas += _tabla(_agrupar(ficheros_frontend(), profundidad), "== Frontend, por módulo ==") + [""]
    if not lineas:
        print("[cobertura] no hay datos todavía en cobertura/")
        return
    lineas.append("Detalle: cobertura/backend/html/index.html y cobertura/frontend/index.html")
    texto = "\n".join(lineas) + "\n"
    SALIDA.mkdir(exist_ok=True)
    (SALIDA / "resumen.txt").write_text(texto, encoding="utf-8")
    print(texto)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(allow_abbrev=False, description="Cobertura de backend y frontend (sin umbrales).",
                                epilog="Lo que no reconoce se pasa a pytest.")
    p.add_argument("--solo", choices=["backend", "frontend", "resumen"], help="solo una parte")
    p.add_argument("--profundidad", type=int, default=2, help="carpetas que forman un módulo (2)")
    a, resto = p.parse_known_args(argv)
    codigo = 0
    if a.solo in (None, "backend"):
        codigo = backend(resto or PYTEST_POR_DEFECTO) or codigo
    if a.solo in (None, "frontend"):
        codigo = frontend() or codigo
    resumen(a.profundidad)
    return codigo


if __name__ == "__main__":
    sys.exit(main())
