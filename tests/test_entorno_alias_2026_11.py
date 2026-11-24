"""ENVIRONMENT: los alias que aceptan los scripts arrancan la API (23-11-2026).

setup.sh, setup.bat y `app/core/entorno.py` dan por buenos `dev`, `local`,
`demo` y `testing`; `Settings` los rechazaba y la API no arrancaba. Ahora se
normalizan al valor canónico y lo desconocido se sigue rechazando.
"""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.core.config import Settings
from app.core.entorno import ENTORNOS_SEGUROS


@pytest.mark.parametrize(
    ("bruto", "canonico"),
    [
        ("development", "development"),
        ("dev", "development"),
        ("local", "development"),
        ("demo", "development"),
        ("DEV", "development"),
        (" Local ", "development"),
        ("test", "test"),
        ("testing", "test"),
    ],
)
def test_alias_locales_se_normalizan(monkeypatch, bruto, canonico):
    monkeypatch.setenv("ENVIRONMENT", bruto)
    assert Settings().ENVIRONMENT == canonico


def test_valor_desconocido_se_rechaza(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "desarrollo-de-pepe")
    with pytest.raises(ValidationError):
        Settings()


def test_todo_entorno_seguro_de_los_scripts_es_aceptado_por_settings():
    # Si un script acepta un valor, Settings también: la lista de la puerta
    # destructiva no puede contener nada que haga fallar el arranque.
    for valor in ENTORNOS_SEGUROS:
        assert valor in Settings.ENVIRONMENT_ALIASES
        assert Settings.ENVIRONMENT_ALIASES[valor] in {"development", "test"}


def test_alias_de_produccion_no_bajan_el_endurecimiento():
    assert Settings.ENVIRONMENT_ALIASES["prod"] == "production"
    assert Settings.ENVIRONMENT_ALIASES["preprod"] == "staging"
