"""Cada grupo de ajustes en vivo tiene su pestaña en Admin (revisión 2026-11).

Medido el 05-11-2026: la pantalla de «Configuración dinámica» lista sus grupos a
mano y le faltaban dos de los veinte del servidor —`audit` (6 ajustes) y
`conectores` (11)—: existían, se leían en vivo y nadie podía cambiarlos desde
Admin. Esto lo impide.
"""
import re
from pathlib import Path

from app.services.settings_service import RUNTIME_FLAG_GROUPS

PANTALLA = (Path(__file__).resolve().parents[1] / "frontend/src/pages/settings-sections/SettingsAdvancedSections.tsx")


def test_cada_grupo_del_servidor_esta_en_la_pantalla():
    texto = PANTALLA.read_text(encoding="utf-8")
    i = texto.index("const RUNTIME_GROUPS = [")
    ids = re.findall(r"id: '([a-z_]+)'", texto[i:texto.index("]\n", i)])
    assert len(ids) >= 18
    assert [g for g in RUNTIME_FLAG_GROUPS if g not in ids] == []
    assert [g for g in ids if g not in RUNTIME_FLAG_GROUPS] == []
