"""Portal en 8 idiomas (16-11-2026): los tickets que abre el sistema (plantillas
de `textos_del_sistema`) se ven en el portal en el idioma de la ficha del
cliente, aunque se escribieran en otro."""
import json
from types import SimpleNamespace

import pytest

from app.services.traduccion import textos_del_sistema as tds
from app.services.traduccion.idiomas import IDIOMAS_DEL_PORTAL


def _ticket(codigo="alm_breakdown", params=None):
    params = params or {"name": "Portátil 14", "tag": "A-12", "serial": "SN1", "text": "No arranca"}
    return SimpleNamespace(system_template=codigo, system_params=json.dumps(params))


@pytest.mark.parametrize("idioma", list(IDIOMAS_DEL_PORTAL))
def test_plantilla_en_el_idioma_del_cliente(idioma):
    ticket = _ticket()
    salida = tds.en_idioma({"title": "Avería: Portátil 14 (A-12)", "description": "x"}, ticket, idioma)
    esperado = tds.renderizar("alm_breakdown", tds.params_de(ticket), idioma)
    assert (salida["title"], salida["description"]) == esperado
    assert "Portátil 14" in salida["title"]


def test_las_plantillas_estan_en_los_8_idiomas_del_portal():
    for codigo, plantilla in tds.PLANTILLAS.items():
        assert set(IDIOMAS_DEL_PORTAL) <= set(plantilla), codigo


def test_sin_plantilla_o_sin_idioma_sale_tal_cual():
    salida = {"title": "Escrito por una persona", "description": "texto"}
    assert tds.en_idioma(dict(salida), SimpleNamespace(system_template=None, system_params=None), "fr") == salida
    assert tds.en_idioma(dict(salida), _ticket(), None) == salida
    assert tds.en_idioma(dict(salida), _ticket(codigo="no_existe"), "de") == salida
