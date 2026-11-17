"""Errores con codigo del operador: turnos, ausencias por horas, jornadas y avisos.

Lo que se mide: que cada codigo de `MENSAJES_DEL_OPERADOR` tiene su traduccion
en es/en/zh con los mismos `{datos}`, que no se pisa el catalogo del portal y
que los servicios lanzan el error con su codigo y el castellano de siempre.
"""
from __future__ import annotations

import re
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.core.codigos_de_error import MENSAJES, MENSAJES_DEL_OPERADOR
from app.core.errores import ErrorDeDominio

LANGS = Path(__file__).resolve().parents[1] / "frontend" / "src" / "i18n" / "langs"


def _err_srv(idioma: str) -> dict[str, str]:
    texto = (LANGS / f"{idioma}.mjs").read_text(encoding="utf-8")
    ini = texto.index("err_srv: {")
    fin = texto.index("\n  },", ini)
    cuerpo = texto[ini:fin]
    return {m.group(1): m.group(2) for m in re.finditer(r'^\s+(\w+):\s*"((?:[^"\\]|\\.)*)",?\s*$', cuerpo, re.M)}


def _datos(plantilla: str) -> set[str]:
    return set(re.findall(r"\{(\w+)\}", plantilla))


@pytest.mark.parametrize("idioma", ["es", "en", "zh"])
def test_cada_codigo_del_operador_esta_traducido(idioma):
    dic = _err_srv(idioma)
    faltan = [c for c in MENSAJES_DEL_OPERADOR if c not in dic]
    assert not faltan, f"{idioma}: faltan {faltan}"
    for codigo, plantilla in MENSAJES_DEL_OPERADOR.items():
        assert _datos(dic[codigo]) == _datos(plantilla), f"{idioma}.{codigo}: los {{datos}} no coinciden"


def test_el_castellano_de_la_interfaz_es_el_del_catalogo():
    es = _err_srv("es")
    for codigo, plantilla in MENSAJES_DEL_OPERADOR.items():
        assert es[codigo] == plantilla, codigo


def test_los_catalogos_no_se_pisan():
    assert not set(MENSAJES) & set(MENSAJES_DEL_OPERADOR)


def test_turnos_lanza_con_codigo():
    from app.services.ausencias import turnos
    usuario = SimpleNamespace(organization_id="1")
    with pytest.raises(ErrorDeDominio) as e:
        turnos.guardar_turno(None, usuario, {"nombre": "Mañana", "hora_inicio": "08:00", "hora_fin": "08:00"})
    assert e.value.code == "turno_misma_hora"
    assert e.value.detail == "El turno empieza y acaba a la misma hora"


def test_jornadas_lanza_con_codigo_y_datos():
    from app.services.horario import jornadas
    with pytest.raises(ErrorDeDominio) as e:
        jornadas._fecha("no-es-fecha", "desde")
    assert e.value.code == "fecha_no_valida_en"
    assert e.value.params == {"nombre": "desde"}
    assert e.value.detail == "Fecha no válida en «desde»"


def test_solicitudes_hora_no_valida_con_codigo():
    from app.services.ausencias import solicitudes
    with pytest.raises(ErrorDeDominio) as e:
        solicitudes._hora("zz", "hora de inicio")
    assert e.value.code == "hora_no_valida_en"
    assert e.value.detail == "Hora no válida en «hora de inicio» (HH:MM)"


def test_movimientos_persona_inexistente_con_codigo():
    from app.services.ausencias import movimientos
    with pytest.raises(ErrorDeDominio) as e:
        movimientos.crear(None, SimpleNamespace(id="u", organization_id="1"), {"user_id": None})
    assert e.value.code == "persona_no_existe_en_empresa"
    assert e.value.status_code == 422
