"""Asignacion de campos desde payloads del cliente sin mass-assignment.

Auditoria 2026-11: varios servicios hacian `if hasattr(obj, k): setattr(obj, k, v)`
con el `dict` crudo del cuerpo. `hasattr` es cierto para `organization_id`,
`id`, `created_by`... y tambien para relaciones y metodos, asi que el cliente
podia mover un registro a otra organizacion o falsear la auditoria.
"""
from __future__ import annotations

from collections.abc import Iterable

from sqlalchemy import inspect as sa_inspect

#: Campos que son del servidor, nunca del payload: tenant, identidad y auditoria.
CAMPOS_PROTEGIDOS = frozenset({
    "id",
    "organization_id",
    "created_at",
    "updated_at",
    "created_by",
    "created_by_id",
    "deleted_at",
})


def campos_asignables(modelo, datos: dict, protegidos: Iterable[str] = ()) -> dict:
    """Las claves de `datos` que son columnas de `modelo` y no estan protegidas.

    `modelo` puede ser la clase o una instancia. Las relaciones, propiedades y
    metodos se descartan: solo cuentan las columnas mapeadas.
    """
    clase = modelo if isinstance(modelo, type) else type(modelo)
    columnas = {a.key for a in sa_inspect(clase).column_attrs}
    fuera = CAMPOS_PROTEGIDOS | set(protegidos)
    return {k: v for k, v in (datos or {}).items() if k in columnas and k not in fuera}


def es_asignable(modelo, campo: str, protegidos: Iterable[str] = ()) -> bool:
    """Si `campo` se puede asignar desde un payload (ver `campos_asignables`)."""
    return bool(campos_asignables(modelo, {campo: None}, protegidos))
