"""La referencia de ajustes lista todos los ajustes (revisión 2026-11).

Medido el 05-11-2026: la tabla «4.2 Settings fields» del README decía 248 y
tenía 255 de los 328 campos de `Settings`; faltaban 73, veinte de ellos recién
añadidos. Esto lo impide: cada campo de `Settings` y cada clave del registro de
ajustes en vivo tiene su fila, y el número del encabezado es el real.

23-11-2026: la tabla salió del README a `docs/REFERENCIA_DE_AJUSTES.md` (el
README es la guía; la lista exhaustiva, más de 1.100 filas, va aparte y el
README la enlaza). Mismas comprobaciones, mismo rigor: además se exige que el
README enlace la referencia.
"""
from pathlib import Path

from app.core.config import settings
from app.services.settings_service import RUNTIME_FLAG_GROUPS

RAIZ = Path(__file__).resolve().parents[1]
REFERENCIA = (RAIZ / "docs" / "REFERENCIA_DE_AJUSTES.md").read_text(encoding="utf-8")
README = (RAIZ / "README.md").read_text(encoding="utf-8")


def _seccion(inicio: str, fin: str) -> str:
    i = REFERENCIA.index(inicio)
    return REFERENCIA[i:REFERENCIA.index(fin, i)]


def test_cada_campo_de_settings_tiene_fila_y_el_encabezado_dice_cuantos():
    campos = list(type(settings).model_fields)
    seccion = _seccion("## 2. Variables de entorno (`Settings`)", "## 3. Ajustes en vivo")
    assert len(campos) > 300
    assert [c for c in campos if f"| `{c}` |" not in seccion] == []
    assert f"Total medido: **{len(campos)} campos de `Settings`**." in seccion


def test_cada_clave_del_registro_en_vivo_tiene_fila():
    claves = [(g, k) for g, v in RUNTIME_FLAG_GROUPS.items() for k, _, _ in v]
    seccion = _seccion("## 3. Ajustes en vivo", "## 4. Variables leídas fuera de `Settings`")
    assert len(claves) > 150
    assert [(g, k) for g, k in claves if f"| {g} | {k} |" not in seccion] == []
    assert f"**{len(RUNTIME_FLAG_GROUPS)} grupos, {len(claves)} claves**" in seccion


def test_el_readme_enlaza_la_referencia():
    assert "docs/REFERENCIA_DE_AJUSTES.md" in README
