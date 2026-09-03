#!/usr/bin/env python
"""Gate: lo instalado coincide con lo fijado en requirements.txt.

Auditoría 2026-08 (hallazgo 22). `pip check` sólo detecta CONFLICTOS declarados
entre paquetes. No detecta que lo instalado sea simplemente **distinto** de lo
fijado, y esa deriva silenciosa costó una sesión entera:

  fastapi        fijado 0.135.3   instalado 0.139.2   ← más nuevo
  pydantic       fijado 2.12.5    instalado 2.10.4    ← más viejo
  pytest         fijado 9.0.3     instalado 8.3.4     ← más viejo
  pytest-cov     fijado 7.1.0     instalado 6.0.0     ← más viejo
  pytest-asyncio sin fijar        instalado 0.25.0

Los efectos, ninguno de ellos con un mensaje de error que apuntase a la causa:

  · `pytest` 8 no trae `_pytest.subtests`, que `schemathesis` 4.25 importa, así
    que **pytest no arrancaba en absoluto** — fallaba al cargar el plugin, antes
    de recoger un solo test.
  · `fastapi` 0.139 volvió `include_router` PEREZOSO: guarda un marcador
    `_IncludedRouter` en lugar de copiar las rutas. La aplicación sigue
    sirviéndolas, pero `app.routes` ya no las enumera, así que los 19 tests que
    verifican el registro de rutas fallaban diciendo «no hay ruta registrada»
    para rutas que sí existen. 2.051 rutas pasaron a verse como 9.

De esos dos, el segundo es el peligroso: la suite falla señalando un problema de
producto que no existe, y quien lo lea buscará el fallo en el código.

Uso:
  python scripts/check_pinned_versions.py            # gate, sale 1 si difiere
  python scripts/check_pinned_versions.py --report   # informe, sale 0
"""
from __future__ import annotations

import argparse
import re
import sys
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
REQUIREMENTS = RAIZ / "requirements.txt"

# `nombre==version`, capturando aparte el marcador de entorno.
FIJADO = re.compile(r"^([A-Za-z0-9._-]+)\s*==\s*([^\s;#]+)\s*(?:;\s*(?P<marcador>[^#]+))?")


def normalizar(nombre: str) -> str:
    """Nombre canónico de paquete: guiones y minúsculas (PEP 503)."""
    return re.sub(r"[-_.]+", "-", nombre).lower()


def leer_fijados() -> dict[str, str]:
    fijados: dict[str, str] = {}
    for linea in REQUIREMENTS.read_text(encoding="utf-8").splitlines():
        linea = linea.strip()
        if not linea or linea.startswith("#"):
            continue
        m = FIJADO.match(linea)
        if not m:
            continue
        # Los marcadores de entorno se respetan: `uvloop; sys_platform != 'win32'`
        # no esta instalado en Windows a proposito, y contarlo como ausente seria
        # un falso positivo permanente en el gate.
        marcador = (m.group("marcador") or "").strip()
        if marcador and not _marcador_aplica(marcador):
            continue
        fijados[normalizar(m.group(1))] = m.group(2)
    return fijados


def _marcador_aplica(marcador: str) -> bool:
    """Evalua un marcador de entorno PEP 508 con la maquinaria de packaging.

    Si no se puede evaluar, se asume que aplica: es mejor un aviso de mas que
    dejar de comprobar un paquete en silencio.
    """
    try:
        from packaging.markers import Marker

        return bool(Marker(marcador).evaluate())
    except Exception:  # noqa: BLE001
        return True



# ── Los paquetes cuya deriva ROMPE la verificación, no sólo la ensucia ────────
#
# Con éstos desalineados no es que la suite dé otro resultado: es que NO SE PUEDE
# EJECUTAR. Ha pasado dos veces.
#
#   · `pytest` — `schemathesis` 4.25 importa `_pytest.subtests`, que sólo existe
#     en pytest 9. Con pytest 8 instalado, pytest no arranca: falla al cargar los
#     plugins y ningún test llega a ejecutarse.
#   · `pytest-asyncio`, `pytest-cov` — se instalan juntos con pytest y arrastran
#     su versión al resolver dependencias, así que son parte del mismo desajuste.
#   · `fastapi`, `starlette` — con fastapi 0.139 en vez del 0.135 fijado,
#     `include_router` pasó a ser PEREZOSO: `app.routes` enumera **9 rutas en vez
#     de 2.051**. La suite no deja de arrancar; se llena de fallos que culpan al
#     producto de un problema que no existe. Es peor que un fallo ruidoso.
#
# Los cinco son de PARCHE o MENOR, así que alinearlos es seguro. Y hay una
# lección de cómo se rompió la segunda vez: instalar sólo `pytest==9.0.3`
# arrastró fastapi de 0.135.3 a 0.139.2 al resolver dependencias, sin decir nada.
# Después de CUALQUIER `pip install` en este proyecto, vuelve a ejecutar este
# script.
#
# El resto de la deriva (numpy, pydantic, redis…) sigue siendo INFORMATIVA a
# propósito: ahí sí hay saltos mayores, algunos a la baja, y forzarlos de golpe
# puede romper la suite. Ver la nota del gate en `scripts/ci_local.sh`.
PAQUETES_CRITICOS = frozenset({
    "pytest", "pytest-asyncio", "pytest-cov",   # sin estos, pytest no arranca
    "fastapi", "starlette",                     # sin estos, 2.051 rutas se ven como 9
})


def main() -> int:
    # La consola de Windows usa cp1252: sin esto, cualquier caracter fuera de ese
    # juego revienta el gate con UnicodeEncodeError en lugar de informar.
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception as exc:  # noqa: BLE001 - si no se puede, se sigue en ASCII
        # No se silencia del todo: si esto falla, los nombres de paquete con
        # acentos saldran mal y conviene saber por que.
        print(f"aviso: no se pudo fijar la salida a UTF-8 ({exc}); se sigue en ASCII")

    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--report", action="store_true", help="informa y sale con 0")
    p.add_argument(
        "--solo-criticos", action="store_true",
        help="mira sólo los paquetes de PAQUETES_CRITICOS; sale con 1 si alguno deriva",
    )
    args = p.parse_args()

    fijados = leer_fijados()
    if not fijados:
        print(f"ERROR: no se pudo leer ninguna versión fijada de {REQUIREMENTS}")
        return 1

    if args.solo_criticos:
        fijados = {k: v for k, v in fijados.items() if k in PAQUETES_CRITICOS}
        faltan_del_conjunto = PAQUETES_CRITICOS - set(fijados)
        if faltan_del_conjunto:
            print(
                "ERROR: estos paquetes están en PAQUETES_CRITICOS pero no fijados "
                f"en requirements.txt: {sorted(faltan_del_conjunto)}"
            )
            return 1

    difieren: list[tuple[str, str, str]] = []
    ausentes: list[tuple[str, str]] = []

    for paquete, esperada in sorted(fijados.items()):
        try:
            instalada = version(paquete)
        except PackageNotFoundError:
            ausentes.append((paquete, esperada))
            continue
        if instalada != esperada:
            difieren.append((paquete, esperada, instalada))

    print(f"{len(fijados)} paquetes fijados en requirements.txt")
    print(f"  coinciden:  {len(fijados) - len(difieren) - len(ausentes)}")
    print(f"  difieren:   {len(difieren)}")
    print(f"  no están:   {len(ausentes)}")

    if not difieren and not ausentes:
        print("\n✓ el entorno coincide con requirements.txt")
        return 0

    if difieren:
        print("\n✗ versiones distintas de las fijadas:")
        for paquete, esperada, instalada in difieren:
            señal = "más nuevo" if instalada > esperada else "más viejo"
            print(f"    {paquete:<34} fijado {esperada:<14} instalado {instalada}  ({señal})")
    if ausentes:
        print("\n✗ fijados pero no instalados:")
        for paquete, esperada in ausentes:
            print(f"    {paquete:<34} {esperada}")

    print(
        "\nSe corrige con:  pip install -r requirements.txt\n"
        "Y si la versión nueva es la que se quiere, hay que ACTUALIZAR el pin —\n"
        "no dejar el entorno y el fichero discrepando."
    )
    return 0 if args.report else 1


if __name__ == "__main__":
    sys.exit(main())
