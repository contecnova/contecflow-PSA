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
    if isinstance(params, dict):
        # Migracion 200: las columnas `*_params` nuevas son JSON (llega ya un dict).
        datos = params
    else:
        try:
            datos = json.loads(params) if params else {}
        except (TypeError, ValueError):
            logger.warning("textos_guardados: datos ilegibles para %r", clave)
            return respaldo
    if not isinstance(datos, dict):
        return respaldo
    try:
        return en_idioma(clave, idioma, **datos)
    except (KeyError, IndexError, ValueError):
        logger.warning("textos_guardados: faltan datos para %r", clave)
        return respaldo


def por_clave_json(clave: str, **params: Any) -> tuple[str, Optional[dict]]:
    """(clave, datos como dict) para las columnas `*_params` de tipo JSON (migracion 200)."""
    return clave, (json.loads(json.dumps(params, ensure_ascii=False, default=str)) if params else None)


_CLAVE_IDIOMA_LECTOR = "_idioma_del_lector"


def idioma_del_lector(db) -> Optional[str]:
    """Idioma de quien hace la peticion (el `current_user` de la sesion), con cache en la sesion.

    Migracion 200: los serializadores que no reciben el usuario pintan los
    textos guardados por clave en su idioma sin cambiar sus firmas. Sin
    usuario (trabajos de fondo), el de la empresa de la sesion.
    """
    if db is None:
        return None
    info = getattr(db, "info", None)
    if info is None:
        return None
    if _CLAVE_IDIOMA_LECTOR in info:
        return info[_CLAVE_IDIOMA_LECTOR]
    from app.services.formato_regional import idioma_de_salida
    usuario = info.get("current_user")
    try:
        idioma = idioma_de_salida(db, user_id=getattr(usuario, "id", None),
                                  org_id=getattr(usuario, "organization_id", None) or info.get("organization_id"))
    except Exception:
        logger.debug("idioma_del_lector: no legible", exc_info=True)
        idioma = None
    info[_CLAVE_IDIOMA_LECTOR] = idioma
    return idioma


def pintar_campo(obj, campo: str, *, clave: Optional[str] = None, params: Optional[str] = None,
                 idioma: Optional[str] = None) -> Optional[str]:
    """`obj.<campo>` pintado desde `obj.<campo>_key`/`_params` (o `clave`/`params`) en el idioma del lector."""
    from sqlalchemy.orm import object_session
    respaldo = getattr(obj, campo, None)
    k = getattr(obj, clave or f"{campo}_key", None)
    if not k:
        return respaldo
    if idioma is None:
        idioma = idioma_del_lector(object_session(obj))
    return pintar(k, getattr(obj, params or f"{campo}_params", None), respaldo, idioma)
