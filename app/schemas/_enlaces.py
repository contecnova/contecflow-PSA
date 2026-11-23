"""Enlaces guardados que luego se pintan como ``href`` (auditoría 22-11-2026).

A6 del 04 y A3 del 04b: ``file_url`` y ``test_environment`` del portal de
clientes eran texto libre y llegaban como enlace al portal externo; un
``javascript:`` o ``data:`` guardado por un operador viajaba al cliente.

``EnlaceSeguro`` admite:
- ``http://`` y ``https://``;
- rutas propias que empiezan por ``/`` (``/api/v1/uploads/...``);
- texto sin esquema (``staging``, ``entorno de pruebas``): no es un enlace.

Rechaza cualquier otro esquema (``javascript:``, ``data:``, ``vbscript:``,
``file:``…). El frontend, además, sanea al pintar (``utils/security.ts``,
``sanitizeUrl``).
"""
from __future__ import annotations

import re
from typing import Annotated, Optional

from pydantic import AfterValidator

_ESQUEMA = re.compile(r"^([a-zA-Z][a-zA-Z0-9+.\-]*):")


def validar_enlace(valor: Optional[str]) -> Optional[str]:
    if valor is None:
        return None
    limpio = valor.strip()
    if not limpio:
        return None
    # Caracteres de control: el navegador los ignora dentro del esquema (`java\tscript:`).
    sin_control = re.sub(r"[\x00-\x1f]", "", limpio)
    m = _ESQUEMA.match(sin_control)
    if m and m.group(1).lower() not in ("http", "https"):
        raise ValueError("El enlace debe empezar por http:// o https://")
    return limpio


EnlaceSeguro = Annotated[Optional[str], AfterValidator(validar_enlace)]
