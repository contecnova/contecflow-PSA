"""Tema y densidad: todo lo que ofrece la pantalla se puede guardar.

Auditoria 2026-11: las columnas eran `String(10)` y en Postgres el tema
`high-contrast` y la densidad `comfortable` fallaban al guardar. SQLite no
mide la longitud, asi que la prueba la compara con la del modelo.
"""
from __future__ import annotations

import pytest

from tests.conftest import auth


@pytest.mark.parametrize("columna, valores", [("theme_mode", "TEMAS"), ("ui_density", "DENSIDADES")])
def test_cada_valor_valido_cabe_en_su_columna(columna, valores):
    from app.models.user import UserPreference
    from app.services import user_service
    largo = UserPreference.__table__.c[columna].type.length
    assert all(len(v) <= largo for v in getattr(user_service, valores)), (columna, largo)


def test_los_temas_del_servidor_son_los_de_la_pantalla():
    import pathlib
    import re
    from app.services.user_service import TEMAS
    panel = pathlib.Path("frontend/src/components/layout/UserProfilePanel.tsx").read_text()
    bloque = panel.split("const THEMES = [", 1)[1].split("]", 1)[0]
    assert set(re.findall(r"id: '([\w-]+)'", bloque)) == set(TEMAS)


def test_un_tema_desconocido_se_rechaza_y_uno_valido_se_guarda(client, admin_token):
    url = "/api/v1/users/me/preferences"
    assert client.patch(url, headers=auth(admin_token), json={"theme_mode": "neon"}).status_code == 422
    assert client.patch(url, headers=auth(admin_token), json={"ui_density": "enorme"}).status_code == 422
    r = client.patch(url, headers=auth(admin_token), json={"theme_mode": "high-contrast", "ui_density": "comfortable"})
    assert r.status_code == 200, r.text
    prefs = client.get(url, headers=auth(admin_token)).json()
    prefs = prefs.get("data", prefs)
    assert (prefs["theme_mode"], prefs["ui_density"]) == ("high-contrast", "comfortable")
