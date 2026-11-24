"""BPM: cada código que manda el motor tiene texto en cada idioma ofrecido.

Revisión BPM 2026-11-16. La pantalla construye las claves en tiempo de
ejecución (`bpm.problema_<code>`, `bpm.error_<code>`, `bpm.tipo_<tipo>`,
`bpm.rol_<rol>`, `bpm.estado_<estado>`; ver `frontend/src/pages/bpm/textos.ts`),
así que el análisis estático de claves no las ve. Aquí se leen los códigos de la
fuente de verdad (`app/services/bpmn_engine.py`) y se exige su texto.
"""
from __future__ import annotations

import re

from app.services import bpmn_engine as motor

from ._i18n_langs import RAIZ, fichero_de, idiomas_ofrecidos

_FUENTE = (RAIZ / "app" / "services" / "bpmn_engine.py").read_text(encoding="utf-8")


def _bloque_bpm(lang: str) -> str:
    texto = fichero_de(lang).read_text(encoding="utf-8")
    m = re.search(r"\n  bpm: \{(.*?)\n  \},", texto, re.S)
    assert m, f"no está el módulo bpm en {lang}"
    return m.group(1)


def _claves() -> list[str]:
    # 23-11-2026: también los problemas que anota `_comprobar` (`mal("código", …)`)
    # y los fallos que marca la corrida (`_fallar(self.inst, …)`).
    problemas = set(re.findall(r'(?:Problema|mal)\(\s*"([a-z_]+)"', _FUENTE))
    errores = set(re.findall(r'_fallar\(\s*(?:self\.)?inst,\s*"([a-z_]+)"', _FUENTE))
    assert len(problemas) >= 10 and errores >= {"no_route", "loop_limit"}
    tipos = motor._SOPORTADOS
    roles = set(motor._ALIAS_DE_ROL) | {"cualquiera"}
    estados = set(motor.ESTADOS_DE_INSTANCIA) | {"active"}
    esperas = {motor.ESPERA_TAREA, motor.ESPERA_DECISION, motor.ESPERA_TEMPORIZADOR, motor.ESPERA_UNION,
               motor.ESPERA_MENSAJE, motor.ESPERA_SUBPROCESO, motor.ESPERA_LLAMADA, motor.ESPERA_TRABAJO,
               motor.ESPERA_REINTENTO, motor.ESPERA_INCIDENTE, motor.ESPERA_APROBACION}
    return sorted([f"problema_{c}" for c in problemas] + [f"error_{c}" for c in errores]
                  + [f"tipo_{t}" for t in tipos] + [f"rol_{r}" for r in roles]
                  + [f"estado_{e}" for e in estados] + [f"espera_{e}" for e in esperas]
                  + [f"vartipo_{t}" for t in motor.TIPOS_DE_VARIABLE])


def test_los_codigos_del_motor_tienen_texto_en_cada_idioma():
    claves = _claves()
    faltan = {}
    for lang in idiomas_ofrecidos():
        cuerpo = _bloque_bpm(lang)
        sin = [k for k in claves if not re.search(r"\n    " + re.escape(k) + r":", cuerpo)]
        if sin:
            faltan[lang] = sin
    assert faltan == {}


def test_la_pestana_procesos_de_la_bandeja_tiene_texto():
    for lang in idiomas_ofrecidos():
        assert re.search(r"\n +tab_processes:", fichero_de(lang).read_text(encoding="utf-8")), lang
