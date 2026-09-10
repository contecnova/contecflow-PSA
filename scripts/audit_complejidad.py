"""Mide la complejidad ciclomática de `app/` y la devuelve como datos.

Auditoría 2026-08 (hallazgo 18). El repositorio no tenía **ninguna** medida de
complejidad: `ruff.toml` selecciona `E, F, W, S, B` y `C901` no está entre
ellas, así que una función podía crecer sin que nada dijera nada. Este script y
su guardián (`tests/test_complejidad_no_empeora.py`) son el trinquete.

── Por qué llama a ruff en vez de calcular McCabe ────────────────────────────
Porque la regla ya existe y reimplementarla sería inventarse una segunda
definición de «complejidad» que podría discrepar de la que usa el linter. El
resto de detectores de esta auditoría son AST puro porque la regla que aplican
**no existía**; aquí sí existe, y la definición canónica es `C901` de ruff. Lo
que hace falta no es otra implementación, es que alguien la mire.

── Cómo se usa ───────────────────────────────────────────────────────────────
    python scripts/audit_complejidad.py            # informe legible
    python scripts/audit_complejidad.py --lista    # el dict para el guardián

`medir()` devuelve `{(fichero, función): complejidad}` con el fichero en
formato POSIX, para que la lista registrada valga igual en Windows y en Linux.
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
UMBRAL = 10

_LINEA = re.compile(
    r"^(?P<fichero>.+?):(?P<linea>\d+):\d+: C901 "
    r"`(?P<funcion>.+?)` is too complex \((?P<valor>\d+) > (?P<umbral>\d+)\)$"
)


def medir(ruta: str = "app/") -> dict[tuple[str, str], int]:
    """Las funciones de `ruta` por encima del umbral, con su complejidad."""
    proc = subprocess.run(
        [sys.executable, "-m", "ruff", "check", ruta,
         "--select", "C901", "--output-format", "concise",
         "--isolated", f"--config", f"lint.mccabe.max-complexity={UMBRAL}"],
        cwd=RAIZ, capture_output=True, text=True,
    )
    # ruff sale con 1 cuando encuentra hallazgos: es lo normal aquí.
    if proc.returncode not in (0, 1):
        raise RuntimeError(f"ruff falló ({proc.returncode}):\n{proc.stderr}")

    fuera = {}
    for linea in proc.stdout.splitlines():
        m = _LINEA.match(linea.strip())
        if not m:
            continue
        fichero = Path(m.group("fichero")).as_posix()
        fuera[(fichero, m.group("funcion"))] = int(m.group("valor"))
    return fuera


def _informe() -> int:
    encontradas = medir()
    if not encontradas:
        print(f"Ninguna función de app/ por encima de {UMBRAL}.")
        return 0
    exceso = sum(v - UMBRAL for v in encontradas.values())
    print(f"{len(encontradas)} funciones por encima de {UMBRAL} "
          f"— exceso acumulado {exceso}, máximo {max(encontradas.values())}\n")
    for (fichero, funcion), valor in sorted(
            encontradas.items(), key=lambda kv: (-kv[1], kv[0])):
        print(f"  {valor:3}  {fichero}  {funcion}")
    return 0


def _lista() -> int:
    encontradas = medir()
    print("CONOCIDAS = {")
    for (fichero, funcion), valor in sorted(encontradas.items()):
        print(f'    ("{fichero}", "{funcion}"): {valor},')
    print("}")
    return 0


if __name__ == "__main__":
    raise SystemExit(_lista() if "--lista" in sys.argv else _informe())
