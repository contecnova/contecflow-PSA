"""Borrar o sembrar la base exige un entorno de desarrollo o pruebas (revisión 2026-11).

Medido antes: `setup.sh clean`, `setup.bat start clean`, `scripts/start.sh` y el
sembrado no miraban `ENVIRONMENT`. Todos pasan por estos dos puntos de entrada.
"""
from __future__ import annotations

import importlib.util
import runpy
from pathlib import Path

import pytest

from app.core.config import settings
from app.core.entorno import exigir_entorno_no_productivo

RAIZ = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("entorno", ["production", "staging", "", "PRODUCCION"])
def test_fuera_de_desarrollo_sale_con_2(entorno, monkeypatch):
    monkeypatch.setattr(settings, "ENVIRONMENT", entorno)
    with pytest.raises(SystemExit) as e:
        exigir_entorno_no_productivo("x")
    assert e.value.code == 2


def test_en_desarrollo_deja_pasar(monkeypatch):
    monkeypatch.setattr(settings, "ENVIRONMENT", "development")
    exigir_entorno_no_productivo("x")


def test_el_reset_no_abre_la_base_en_produccion(monkeypatch):
    monkeypatch.setattr(settings, "ENVIRONMENT", "production")
    spec = importlib.util.spec_from_file_location("reset_admin", RAIZ / "scripts" / "reset_to_admin_only.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    monkeypatch.setattr(mod, "SessionLocal", lambda: pytest.fail("abrió la base"))
    with pytest.raises(SystemExit) as e:
        mod.main()
    assert e.value.code == 2


def test_el_sembrado_no_empieza_en_produccion(monkeypatch):
    monkeypatch.setattr(settings, "ENVIRONMENT", "production")
    with pytest.raises(SystemExit) as e:
        runpy.run_module("app.db.seed", run_name="__main__")
    assert e.value.code == 2
