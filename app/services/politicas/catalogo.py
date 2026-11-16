"""Catálogo tipado de campos que cada dominio registra (tarea #26).

El motor NO conoce ningún dominio. Un dominio (gastos, ausencias, compras…) se
registra con `registrar(Dominio(...))` y declara:

- sus campos, cada uno con tipo, operadores y de dónde salen sus valores
  (lista cerrada, selector de entidad, importe con moneda, fecha, número,
  texto, país, ciudad, sí/no);
- cómo convertir una entidad suya en un CONTEXTO (`contexto`): un diccionario
  con el valor de cada campo y los atributos del sujeto (quién pide) para el
  ámbito de la política;
- cómo cargar una entidad, listar las históricas (simulador), saber de quién
  es (explicación) y, opcionalmente, qué campos se pueden fijar
  (`set_field`) y cómo comprobar los requisitos (justificante, justificación).

Ver `dominios/gastos.py` como ejemplo completo, y DOCS.md («Motor de
políticas») para registrar un dominio nuevo.
"""
from __future__ import annotations

from typing import Optional

from app.core.errores import ErrorDeDominio
from app.services.politicas.registro import (  # noqa: F401 (API pública del catálogo)
    DOS_VALORES, ENTIDADES, LISTA, OPERADORES_POR_TIPO, SIN_VALOR, TIPOS_DE_PARAMETRO, Campo, Dominio, Opcion,
    Parametro, ResultadoPropio, _REGISTRO, registrar,
)


def _cargar_dominios_incluidos() -> None:
    # Los dominios del repositorio se registran al importarse. Uno nuevo se
    # añade a esta lista (y a DOCS.md); ver «Extension points» en el README.
    from app.services.politicas.dominios import gastos  # noqa: F401
    from app.services.politicas.dominios import ausencias  # noqa: F401
    from app.services.politicas.dominios import catalogo  # noqa: F401  (service desk, 16-11-2026)
    from app.services.politicas.dominios import licencias  # noqa: F401  (fase 2 de licencias: recuperación)


def dominios() -> list[Dominio]:
    _cargar_dominios_incluidos()
    return sorted(_REGISTRO.values(), key=lambda d: d.clave)


def dominio(clave: str) -> Dominio:
    _cargar_dominios_incluidos()
    d = _REGISTRO.get(clave)
    if d is None:
        raise ErrorDeDominio(404, f"Dominio de políticas desconocido: {clave}")
    return d


def dominio_de_aprobacion(entity_type: str) -> Optional[Dominio]:
    """El dominio cuyo `tipo_de_aprobacion` es este entity_type de approval_engine."""
    _cargar_dominios_incluidos()
    return next((d for d in _REGISTRO.values() if d.tipo_de_aprobacion == entity_type), None)
