"""Textos del sistema guardados por clave y pintados al leer (19-11-2026, migración 192).

Algunas filas guardan un texto que escribe el propio sistema: el historial del
ticket (`sd_ticket_history.new_value`: «posible duplicado de…», «resuelto con
el artículo…») y el motivo del agente autónomo
(`sd_autonomous_playbook_executions.resolution_note`). Antes se guardaba ya
escrito (en el idioma de quien lo generó o en inglés fijo) y así lo veía todo
el mundo. Ahora la fila guarda además la clave de `textos_de_salida` y sus
datos (columnas `*_key` y `*_params`), y al leer se pinta en el idioma de
quien mira:

    clave, datos = por_clave("historial.posible_duplicado", numero="TK-12")
    fila.new_value = texto(clave, idioma_de_la_empresa, numero="TK-12")  # respaldo
    fila.new_value_key, fila.new_value_params = clave, datos
    ...
    pintar(fila.new_value_key, fila.new_value_params, fila.new_value, idioma)

Un dato puede ser a su vez un texto por clave (`diferido(...)`: el nombre de un
playbook de serie): se pinta en el mismo idioma. Sin clave, con una clave que
ya no existe o con datos ilegibles, sale el texto guardado (respaldo): las
filas de antes de la migración 192 se ven como siempre.
"""
from __future__ import annotations

import json
import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)


def diferido(clave: str, **params: Any) -> dict:
    """Un dato que es otro texto por clave (se pinta en el idioma de quien lee)."""
    return {"clave": clave, "params": params}


def _es_diferido(valor: Any) -> bool:
    return isinstance(valor, dict) and "clave" in valor and set(valor) <= {"clave", "params"}


def por_clave(clave: str, **params: Any) -> tuple[str, Optional[str]]:
    """(clave, datos en JSON) para las columnas `*_key` y `*_params`."""
    return clave, (json.dumps(params, ensure_ascii=False, default=str) if params else None)


def _pintar_dato(valor: Any, idioma: Optional[str]) -> Any:
    if not _es_diferido(valor):
        return valor
    from app.services.textos_de_salida import texto
    datos = {k: _pintar_dato(v, idioma) for k, v in (valor.get("params") or {}).items()}
    return texto(valor["clave"], idioma, **datos)


def en_idioma(clave: str, idioma: Optional[str], **params: Any) -> str:
    """El texto de `clave` en `idioma`, con los datos diferidos pintados."""
    from app.services.textos_de_salida import texto
    return texto(clave, idioma, **{k: _pintar_dato(v, idioma) for k, v in params.items()})


def pintar(clave: Optional[str], params: Optional[str], respaldo: Optional[str],
           idioma: Optional[str]) -> Optional[str]:
    """El texto guardado por clave en `idioma`; si no se puede, `respaldo` (el texto guardado)."""
    if not clave:
        return respaldo
    from app.services.textos_de_salida import TEXTOS
    if clave not in TEXTOS:
        return respaldo
    try:
        datos = json.loads(params) if params else {}
    except (TypeError, ValueError):
        logger.warning("textos_guardados: datos ilegibles para %r", clave)
        return respaldo
    if not isinstance(datos, dict):
        return respaldo
    return en_idioma(clave, idioma, **datos)
