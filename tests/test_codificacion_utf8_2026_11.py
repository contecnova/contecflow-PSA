"""Todo el texto del repositorio es UTF-8 válido (23-11-2026).

`docs/seguridad/guardas_por_capacidad.md` tenía un «m\\xe9todo» en Latin-1
(escrito desde Windows sin `encoding="utf-8"`): GitHub, los editores y los
scripts que lo leen con `encoding="utf-8"` lo mostraban con el carácter de
sustitución o fallaban. Barrido de .md, .py, .ts, .tsx y .mjs: era el único. Esta prueba
impide que vuelva a pasar.
"""
from __future__ import annotations

import os
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
EXTENSIONES = (".md", ".py", ".ts", ".tsx", ".mjs")
SE_SALTAN = {"node_modules", ".git", ".venv", "venv", "dist", "__pycache__", ".mypy_cache",
             ".pytest_cache", "htmlcov", "backups", "uploads", "test-results", "playwright-report"}


def test_todos_los_ficheros_de_texto_son_utf8_valido():
    malos = []
    for raiz, dirs, ficheros in os.walk(RAIZ):
        dirs[:] = [d for d in dirs if d not in SE_SALTAN]
        for nombre in ficheros:
            if not nombre.endswith(EXTENSIONES):
                continue
            ruta = Path(raiz) / nombre
            datos = ruta.read_bytes()
            try:
                texto = datos.decode("utf-8")
            except UnicodeDecodeError as e:
                malos.append(f"{ruta.relative_to(RAIZ)}: byte {e.start}")
                continue
            if chr(0xFFFD) in texto:
                malos.append(f"{ruta.relative_to(RAIZ)}: carácter de sustitución U+FFFD")
    assert not malos, "Ficheros que no son UTF-8 válido:\n" + "\n".join(malos)
