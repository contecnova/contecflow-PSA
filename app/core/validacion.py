"""Errores de validacion de la peticion con codigo traducible (17-11-2026).

Antes, un 422 de FastAPI (``RequestValidationError``) salia con la lista cruda
de Pydantic (``[{"type", "loc", "msg", "input", "ctx"}]``): mensajes en ingles,
tipos internos de Pydantic y, de propina, el valor enviado (``input``), que
puede ser una contrasena. Ninguna pantalla podia traducirlo ni ponerlo junto a
su campo.

Ahora sale con el mismo contrato que el resto de errores con codigo
(``app/core/codigos_de_error.py``)::

    {"detail": "Revisa los datos: nombre (obligatorio)",   # castellano
     "code": "validacion",
     "params": {"errores": [{"campo": "nombre", "tipo": "obligatorio",
                             "origen": "body"}, ...]}}

- ``campo``: la ruta del dato sin el origen (``body``/``query``/``path``…),
  con puntos (``lineas.0.importe``); ``""`` si el error es del cuerpo entero.
- ``origen``: ``body``, ``query``, ``path``, ``header`` o ``cookie``.
- ``tipo``: uno de ``TIPOS`` (lista cerrada, estable): la interfaz lo
  traduce con ``validacion.<tipo>`` en los 3 idiomas de operador y en los 8
  del portal (``frontend/src/utils/erroresDeValidacion.ts``).
- Segun el tipo, ``min``, ``max`` (limites numericos o de longitud) y
  ``permitidos`` (valores admitidos de un enum/literal).

Nunca se devuelve el valor enviado ni el texto libre de un validador propio
(podria llevar datos): solo el tipo normalizado y sus limites.
"""
from __future__ import annotations

import logging
from typing import Any, Iterable

logger = logging.getLogger(__name__)

CODIGO = "validacion"

ORIGENES = ("body", "query", "path", "header", "cookie")

#: Tipo normalizado -> texto en castellano (``detail``). Cada tipo tiene su
#: clave ``validacion.<tipo>`` en los diccionarios de la interfaz.
TIPOS: dict[str, str] = {
    "obligatorio": "obligatorio",
    "formato": "formato no válido",
    "numero": "debe ser un número",
    "entero": "debe ser un número entero",
    "fecha": "fecha no válida",
    "booleano": "debe ser sí o no",
    "minimo": "mínimo {min}",
    "mayor_que": "debe ser mayor que {min}",
    "maximo": "máximo {max}",
    "menor_que": "debe ser menor que {max}",
    "longitud_minima": "al menos {min} caracteres",
    "longitud_maxima": "como mucho {max} caracteres",
    "elementos_minimos": "al menos {min} elementos",
    "elementos_maximos": "como mucho {max} elementos",
    "valor_no_permitido": "valor no permitido",
    "campo_no_permitido": "campo no admitido",
    "tipo_incorrecto": "tipo de dato incorrecto",
    "json_invalido": "JSON mal formado",
    "no_valido": "no válido",
}

# Tipos de Pydantic v2 -> tipo normalizado. Lo que no esta aqui es `no_valido`.
_POR_TIPO: dict[str, str] = {
    "missing": "obligatorio",
    "missing_argument": "obligatorio",
    "missing_keyword_only_argument": "obligatorio",
    "missing_positional_only_argument": "obligatorio",
    "string_pattern_mismatch": "formato",
    "url_parsing": "formato",
    "url_syntax_violation": "formato",
    "url_type": "formato",
    "url_scheme": "formato",
    "uuid_parsing": "formato",
    "uuid_type": "formato",
    "uuid_version": "formato",
    "ip_v4_address": "formato",
    "ip_v6_address": "formato",
    "ip_any_address": "formato",
    "int_parsing": "entero",
    "int_type": "entero",
    "int_from_float": "entero",
    "int_parsing_size": "entero",
    "float_parsing": "numero",
    "float_type": "numero",
    "decimal_parsing": "numero",
    "decimal_type": "numero",
    "decimal_max_digits": "numero",
    "decimal_max_places": "numero",
    "decimal_whole_digits": "numero",
    "finite_number": "numero",
    "bool_parsing": "booleano",
    "bool_type": "booleano",
    "date_parsing": "fecha",
    "date_type": "fecha",
    "date_from_datetime_parsing": "fecha",
    "date_from_datetime_inexact": "fecha",
    "datetime_parsing": "fecha",
    "datetime_type": "fecha",
    "datetime_from_date_parsing": "fecha",
    "datetime_object_invalid": "fecha",
    "time_parsing": "fecha",
    "time_type": "fecha",
    "time_delta_parsing": "fecha",
    "time_delta_type": "fecha",
    "timezone_naive": "fecha",
    "timezone_aware": "fecha",
    "date_past": "fecha",
    "date_future": "fecha",
    "datetime_past": "fecha",
    "datetime_future": "fecha",
    "greater_than_equal": "minimo",
    "greater_than": "mayor_que",
    "less_than_equal": "maximo",
    "less_than": "menor_que",
    "string_too_short": "longitud_minima",
    "string_too_long": "longitud_maxima",
    "bytes_too_short": "longitud_minima",
    "bytes_too_long": "longitud_maxima",
    "too_short": "elementos_minimos",
    "too_long": "elementos_maximos",
    "literal_error": "valor_no_permitido",
    "enum": "valor_no_permitido",
    "extra_forbidden": "campo_no_permitido",
    "string_type": "tipo_incorrecto",
    "string_unicode": "tipo_incorrecto",
    "bytes_type": "tipo_incorrecto",
    "list_type": "tipo_incorrecto",
    "tuple_type": "tipo_incorrecto",
    "set_type": "tipo_incorrecto",
    "dict_type": "tipo_incorrecto",
    "model_type": "tipo_incorrecto",
    "model_attributes_type": "tipo_incorrecto",
    "dataclass_type": "tipo_incorrecto",
    "none_required": "tipo_incorrecto",
    "is_instance_of": "tipo_incorrecto",
    "json_invalid": "json_invalido",
    "json_type": "json_invalido",
}

# Limites que trae Pydantic en `ctx` segun el tipo.
_MIN = {"greater_than_equal": "ge", "greater_than": "gt", "string_too_short": "min_length",
        "bytes_too_short": "min_length", "too_short": "min_length"}
_MAX = {"less_than_equal": "le", "less_than": "lt", "string_too_long": "max_length",
        "bytes_too_long": "max_length", "too_long": "max_length"}

#: Tope de errores devueltos (un cuerpo enorme y mal formado no infla la respuesta).
MAX_ERRORES = 50


def _escalar(v: Any) -> Any:
    """Solo numeros y textos cortos: los limites de `ctx` (nunca el valor enviado)."""
    if isinstance(v, bool) or v is None:
        return v
    if isinstance(v, (int, float)):
        return v
    try:
        # Decimal, date…: su forma de texto.
        texto = str(v)
    except Exception:  # pragma: no cover - defensivo
        logger.debug("_escalar: valor sin forma de texto", exc_info=True)
        return None
    return texto[:60]


def _permitidos(ctx: dict) -> list[str] | None:
    """Valores admitidos de un literal/enum: Pydantic los da como texto
    (``"'a', 'b' or 'c'"``); se devuelven como lista."""
    esperado = ctx.get("expected")
    if not isinstance(esperado, str) or not esperado:
        return None
    partes = esperado.replace(" or ", ", ").split(", ")
    valores = [p.strip().strip("'\"") for p in partes if p.strip()]
    return valores[:30] or None


def normalizar_error(e: dict) -> dict:
    """Un error de Pydantic -> ``{campo, tipo, origen[, min, max, permitidos]}``."""
    loc = list(e.get("loc") or ())
    origen = str(loc[0]) if loc and str(loc[0]) in ORIGENES else None
    ruta = loc[1:] if origen else loc
    campo = ".".join(str(p) for p in ruta)
    tipo_pydantic = str(e.get("type") or "")
    tipo = _POR_TIPO.get(tipo_pydantic, "no_valido")
    ctx = e.get("ctx") if isinstance(e.get("ctx"), dict) else {}
    # Un validador propio que dice «email» es un formato (EmailStr y similares).
    if tipo_pydantic == "value_error" and "email" in str(e.get("msg") or "").lower():
        tipo = "formato"
    salida: dict[str, Any] = {"campo": campo, "tipo": tipo}
    if origen:
        salida["origen"] = origen
    if tipo_pydantic in _MIN and _MIN[tipo_pydantic] in ctx:
        salida["min"] = _escalar(ctx[_MIN[tipo_pydantic]])
    if tipo_pydantic in _MAX and _MAX[tipo_pydantic] in ctx:
        salida["max"] = _escalar(ctx[_MAX[tipo_pydantic]])
    if tipo == "valor_no_permitido":
        permitidos = _permitidos(ctx)
        if permitidos:
            salida["permitidos"] = permitidos
    return salida


def normalizar_errores(errores: Iterable[dict]) -> list[dict]:
    vistos: set[tuple] = set()
    salida: list[dict] = []
    for e in errores:
        n = normalizar_error(e)
        clave = (n["campo"], n["tipo"], n.get("origen"))
        # Una union (`int | None`…) da un error por rama del mismo campo: basta uno.
        if clave in vistos:
            continue
        vistos.add(clave)
        salida.append(n)
        if len(salida) >= MAX_ERRORES:
            break
    return salida


def _texto(error: dict) -> str:
    plantilla = TIPOS.get(error["tipo"], TIPOS["no_valido"])
    try:
        texto = plantilla.format(min=error.get("min", ""), max=error.get("max", ""))
    except Exception:  # pragma: no cover - defensivo
        logger.debug("_texto: plantilla sin formatear", exc_info=True)
        texto = plantilla
    return f"{error['campo']} ({texto})" if error["campo"] else texto


def detalle(errores: list[dict]) -> str:
    """El ``detail`` en castellano (lo que leen el operador y los clientes antiguos)."""
    if not errores:
        return "Datos no válidos"
    return "Revisa los datos: " + "; ".join(_texto(e) for e in errores[:10])


def cuerpo(errores_de_pydantic: Iterable[dict]) -> dict:
    """La respuesta 422 completa."""
    errores = normalizar_errores(errores_de_pydantic)
    return {"detail": detalle(errores), "code": CODIGO, "params": {"errores": errores}}
