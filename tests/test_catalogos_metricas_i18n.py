"""Los nombres de los catálogos de métricas del backend están en los tres diccionarios.

El frontend traduce por código (`etiquetaCodigo`) los nombres que manda el
backend: catálogo de analítica (etiqueta, descripción y categoría) y métricas
del motor de alertas del BI. Si se añade una métrica o se cambia su texto en
castellano sin tocar el diccionario, este test lo detecta.
"""
import json
import re
import unicodedata
from pathlib import Path

import pytest

from app.api.v1.endpoints.analytics import CATALOGUE
from app.services.bi_smart_alerts.constants import SUPPORTED_METRICS

LANGS = Path(__file__).resolve().parents[1] / "frontend" / "src" / "i18n" / "langs"
IDIOMAS = ("es", "en", "zh")


def _modulo(idioma: str, nombre: str) -> dict[str, str]:
    """Claves `clave: "texto"` de un módulo de primer nivel del diccionario."""
    texto = (LANGS / f"{idioma}.mjs").read_text(encoding="utf8")
    m = re.search(rf"^  {nombre}: \{{\r?\n(.*?)^  \}},", texto, re.S | re.M)
    assert m, f"falta el módulo {nombre} en {idioma}.mjs"
    out: dict[str, str] = {}
    for linea in m.group(1).splitlines():
        par = re.match(r'^\s+([A-Za-z0-9_]+): (".*"),\s*$', linea)
        if par:
            out[par.group(1)] = json.loads(par.group(2))
    return out


def _seg(texto: str) -> str:
    sin_tildes = "".join(c for c in unicodedata.normalize("NFD", texto) if not unicodedata.combining(c))
    return re.sub(r"^_+|_+$", "", re.sub(r"[^a-z0-9_]+", "_", sin_tildes.strip().lower()))


@pytest.mark.parametrize("idioma", IDIOMAS)
def test_cada_metrica_del_catalogo_tiene_etiqueta_y_descripcion(idioma):
    etiquetas = _modulo(idioma, "catalogo_metrica")
    descripciones = _modulo(idioma, "catalogo_metrica_descripcion")
    assert set(etiquetas) == set(CATALOGUE)
    assert set(descripciones) == set(CATALOGUE)
    assert all(v.strip() for v in etiquetas.values())
    assert all(v.strip() for v in descripciones.values())


def test_el_castellano_del_diccionario_es_el_del_backend():
    etiquetas = _modulo("es", "catalogo_metrica")
    descripciones = _modulo("es", "catalogo_metrica_descripcion")
    for clave, meta in CATALOGUE.items():
        assert etiquetas[clave] == meta["label"], clave
        assert descripciones[clave] == meta["description"], clave


@pytest.mark.parametrize("idioma", IDIOMAS)
def test_cada_categoria_del_catalogo_esta_traducida(idioma):
    categorias = _modulo(idioma, "catalogo_categoria")
    esperadas = {_seg(m["category"]) for m in CATALOGUE.values()}
    assert esperadas <= set(categorias)


@pytest.mark.parametrize("idioma", IDIOMAS)
def test_cada_metrica_de_alertas_esta_traducida(idioma):
    bi = _modulo(idioma, "catalogo_metrica_bi")
    assert set(SUPPORTED_METRICS) <= set(bi)
    if idioma == "es":
        for clave, etiqueta in SUPPORTED_METRICS.items():
            assert bi[clave] == etiqueta, clave


@pytest.mark.parametrize("idioma", ("en", "zh"))
def test_las_etiquetas_con_moneda_conservan_el_marcador(idioma):
    """`¤` lo sustituye el frontend por el símbolo de la empresa: no puede perderse."""
    bi = _modulo(idioma, "catalogo_metrica_bi")
    for clave, etiqueta in SUPPORTED_METRICS.items():
        assert ("¤" in bi[clave]) == ("¤" in etiqueta), clave
