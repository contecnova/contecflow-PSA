"""Regenera SECRET_KEY en .env si falta o es insegura (22-11-2026).

Lo llama setup.bat. Antes era una línea de PowerShell dentro del `.bat`; con
`EnableDelayedExpansion` y los `!`, `^` y `|` de su expresión, `cmd` la partía
y salía «Falta la cadena en el terminador». Aquí, sin comillas que escapar.

Imprime `ROTATED` si la ha cambiado y `OK` si no. Nunca imprime la clave.
"""
from __future__ import annotations

import os
import re
import secrets
import sys

INSEGURAS = {"contecflow-secret-key-change-in-production-min32chars!!"}
PLANTILLA = re.compile(r"^(?i:CHANGE_ME|REPLACE_ME)")


def main(ruta: str = ".env") -> int:
    if not os.path.exists(ruta):
        print("OK")
        return 0
    with open(ruta, encoding="utf-8", errors="replace", newline="") as f:
        lineas = f.read().splitlines()
    actual = ""
    for linea in lineas:
        if linea.startswith("SECRET_KEY="):
            actual = linea[len("SECRET_KEY="):]
    if len(actual) >= 32 and not PLANTILLA.match(actual) and actual not in INSEGURAS:
        print("OK")
        return 0
    nueva = secrets.token_hex(32)
    vista = False
    salida = []
    for linea in lineas:
        if linea.startswith("SECRET_KEY="):
            salida.append("SECRET_KEY=" + nueva)
            vista = True
        else:
            salida.append(linea)
    if not vista:
        salida.append("SECRET_KEY=" + nueva)
    with open(ruta, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(salida) + "\n")
    print("ROTATED")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else ".env"))
