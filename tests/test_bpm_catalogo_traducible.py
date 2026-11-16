"""Los procesos que el backend siembra en castellano son traducibles en el frontend.

`PROCESS_CATALOGUE` siembra 55 procesos con nombre, descripción y pasos en
castellano. 16 tienen diagrama propio en el catálogo del frontend
(`pages/bpm/catalogo/estructura.ts`); los otros 39 viven en
`estructuraLineal.ts` con sus textos por idioma en `textosLineales/`. Si se
añade un proceso a la semilla sin darle textos en los tres idiomas, o se cambia
su castellano en un sitio y no en el otro, este test lo detecta.
"""
import json
import re
from pathlib import Path

import pytest

from app.services.bpmn_process_service import PROCESS_CATALOGUE

CATALOGO = Path(__file__).resolve().parents[1] / "frontend" / "src" / "pages" / "bpm" / "catalogo"


def _ids_estructura() -> set[str]:
    texto = (CATALOGO / "estructura.ts").read_text(encoding="utf8")
    return set(re.findall(r"^    id: '([^']+)'", texto, re.M))


def _lineales() -> dict[str, dict]:
    texto = (CATALOGO / "estructuraLineal.ts").read_text(encoding="utf8")
    return {
        m.group(1): {"category": m.group(2), "pasos": int(m.group(3))}
        for m in re.finditer(r"\{ id: '([^']+)', category: '([^']+)', pasos: (\d+) \}", texto)
    }


def _textos(idioma: str) -> dict[str, dict]:
    texto = (CATALOGO / "textosLineales" / f"{idioma}.ts").read_text(encoding="utf8")
    cuerpo = texto.split("const textos: TextosLineales = ", 1)[1].rsplit("\n\nexport default", 1)[0]
    return json.loads(cuerpo)


def test_cada_proceso_sembrado_tiene_diagrama_propio_o_es_lineal():
    propios = _ids_estructura()
    lineales = _lineales()
    claves = {e["key"] for e in PROCESS_CATALOGUE}
    assert claves <= propios | set(lineales)
    # Ninguno queda sin traducir: los que no tienen diagrama propio son los lineales.
    assert set(lineales) == claves - propios
    assert len(lineales) == 39


@pytest.mark.parametrize("idioma", ("es", "en", "zh"))
def test_los_textos_lineales_cubren_cada_proceso_y_paso(idioma):
    lineales = _lineales()
    textos = _textos(idioma)
    assert set(textos) == set(lineales)
    for clave, x in textos.items():
        assert x["name"].strip() and x["description"].strip(), clave
        assert len(x["steps"]) == lineales[clave]["pasos"], clave
        assert all(p.strip() for p in x["steps"]), clave


def test_el_castellano_de_los_textos_es_el_de_la_semilla():
    textos = _textos("es")
    for e in PROCESS_CATALOGUE:
        if e["key"] not in textos:
            continue
        assert textos[e["key"]]["name"] == e["name"], e["key"]
        assert textos[e["key"]]["description"] == e["description"], e["key"]
        assert textos[e["key"]]["steps"] == e["steps"], e["key"]


def _categorias_frontend() -> dict[str, str]:
    """Categoría de cada proceso en el catálogo del frontend (con diagrama propio y lineales)."""
    propios = (CATALOGO / "estructura.ts").read_text(encoding="utf8")
    cats = {m.group(1): m.group(2)
            for m in re.finditer(r"^    id: '([^']+)',\n    category: '([^']+)'", propios, re.M)}
    cats.update({k: v["category"] for k, v in _lineales().items()})
    return cats


def test_la_categoria_sembrada_es_la_del_catalogo_del_frontend():
    """Revisión BPM 2026-11-16: el backend sembraba con categorías propias
    (incident, ai-ml, governance…) que no existen en la barra lateral de /bpm."""
    cats = _categorias_frontend()
    distintas = {e["key"]: (e["category"], cats.get(e["key"])) for e in PROCESS_CATALOGUE
                 if e["category"] != cats.get(e["key"])}
    assert distintas == {}
