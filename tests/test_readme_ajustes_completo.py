"""El manual lista todos los ajustes (revisión 2026-11).

Medido el 05-11-2026: la tabla «4.2 Settings fields» decía 248 y tenía 255 de
los 328 campos de `Settings`; faltaban 73, veinte de ellos recién añadidos. Esto
lo impide: cada campo de `Settings` y cada clave del registro de ajustes en vivo
tiene su fila, y el número del encabezado es el real.
"""
from pathlib import Path

from app.core.config import settings
from app.services.settings_service import RUNTIME_FLAG_GROUPS

README = (Path(__file__).resolve().parents[1] / "README.md").read_text(encoding="utf-8")


def _seccion(inicio: str, fin: str) -> str:
    i = README.index(inicio)
    return README[i:README.index(fin, i)]


def test_cada_campo_de_settings_tiene_fila_y_el_encabezado_dice_cuantos():
    campos = list(type(settings).model_fields)
    seccion = _seccion("#### 4.2 Settings fields", "#### 4.3")
    assert len(campos) > 300
    assert [c for c in campos if f"| `{c}` |" not in seccion] == []
    assert f"#### 4.2 Settings fields (`Settings`, {len(campos)})" in README


def test_cada_clave_del_registro_en_vivo_tiene_fila():
    claves = [(g, k) for g, v in RUNTIME_FLAG_GROUPS.items() for k, _, _ in v]
    assert len(claves) > 150
    assert [(g, k) for g, k in claves if f"| {g} | {k} |" not in README] == []
    assert f"**{len(RUNTIME_FLAG_GROUPS)} groups, {len(claves)} keys**" in README
