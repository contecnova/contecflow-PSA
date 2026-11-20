"""Cada evento del asistente de reuniones tiene etiqueta en es/en/zh (19-11-2026).

El historial de una reunión (`DetalleDeReunion.tsx`) pinta
`t('reuniones.evento.<tipo>')`; sin etiqueta salía el código en crudo
(`linked`, `asked`, `gdpr_erased`). Este test lee los tipos que escribe el
servidor (`evento(db, x, "tipo"...)` y los que se eligen en una variable,
como `listen`/`download_audio`) y exige su etiqueta en los tres idiomas.
"""
from __future__ import annotations

import re
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
FUENTES = list((RAIZ / "app" / "services" / "reuniones").rglob("*.py")) + [
    RAIZ / "app" / "api" / "v1" / "endpoints" / "reuniones.py"]
LLAMADA = re.compile(r"\bevento\(\s*\w+\s*,\s*\w+\s*,\s*\"([a-z_]+)\"")
#: Tipos que se eligen en una variable antes de llamar a `evento`.
VARIABLES = {"listen", "download_audio", "error"}


def _tipos() -> set[str]:
    tipos = set(VARIABLES)
    for f in FUENTES:
        tipos |= set(LLAMADA.findall(f.read_text(encoding="utf-8")))
    return tipos


def _etiquetas(idioma: str) -> set[str]:
    texto = (RAIZ / "frontend" / "src" / "i18n" / "langs" / f"{idioma}.mjs").read_text(encoding="utf-8")
    # El bloque `evento: { ... }` dentro de `reuniones`.
    i = texto.index("reuniones: {")
    j = texto.index("evento: {", i)
    fin = texto.index("}", j)
    return set(re.findall(r"^\s*([a-z_]+):", texto[j + len("evento: {"):fin], re.M))


def test_hay_tipos():
    assert {"linked", "asked", "gdpr_erased"} <= _tipos()


def test_todos_los_eventos_tienen_etiqueta():
    tipos = _tipos()
    for idioma in ("es", "en", "zh"):
        assert sorted(tipos - _etiquetas(idioma)) == [], idioma
