"""Ajustes por empresa: un solo lector que sabe de qué empresa es la lectura.

18-11-2026. La moneda, el IVA, la jornada, la capacidad semanal, la zona horaria
y el idioma por defecto son ajustes por empresa (`RUNTIME_FLAG_GROUPS["locale"]`,
`DEFAULTS_DE_ORGANIZACION`), pero ~200 sitios leían `settings.DEFAULT_*`, el valor
global del entorno: una empresa con IVA 10 % facturaba un hito al 21 %.

`ajuste_de_empresa(db, clave, ...)` resuelve la empresa así:

1. `org_id` explícito;
2. la del registro (`registro.organization_id`: proyecto, usuario, factura…);
3. la de la sesión (`db.info["organization_id"]`);
4. la del usuario de la sesión (`db.info["current_user"]`), salvo superadmin;

y lee el ajuste con precedencia empresa → global → entorno (`get_runtime_*`,
con caché de 60 s). El superadmin no lleva empresa en la sesión, por eso el
registro va antes que la sesión: lo que toca es de la empresa del registro.
Sin `db` o si la lectura falla, devuelve `settings.<CLAVE>`.
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from app.core.config import settings as app_settings

logger = logging.getLogger("contecflow.settings")


def empresa_de(db=None, registro: Any = None, org_id: Optional[str] = None) -> Optional[str]:
    """La empresa a la que pertenece la lectura (ver el orden en el módulo)."""
    if org_id:
        return org_id
    org_registro = getattr(registro, "organization_id", None) if registro is not None else None
    if org_registro:
        return org_registro
    info = getattr(db, "info", None) or {}
    if info.get("organization_id"):
        return info["organization_id"]
    usuario = info.get("current_user")
    if usuario is not None and not getattr(usuario, "is_superadmin", False):
        return getattr(usuario, "organization_id", None)
    return None


def ajuste_de_empresa(db, clave: str, org_id: Optional[str] = None, *, registro: Any = None) -> Any:
    """El valor de `clave` para la empresa de la lectura, del tipo de `settings.<CLAVE>`."""
    respaldo = getattr(app_settings, clave)
    if db is None:
        return respaldo
    from app.services.settings_service.runtime import (
        get_runtime_bool, get_runtime_float, get_runtime_int, get_runtime_str,
    )
    if isinstance(respaldo, bool):
        lector = get_runtime_bool
    elif isinstance(respaldo, int):
        lector = get_runtime_int
    elif isinstance(respaldo, float):
        lector = get_runtime_float
    else:
        lector = get_runtime_str
    try:
        valor = lector(db, clave, empresa_de(db, registro, org_id))
    except Exception:
        logger.debug("ajuste_de_empresa(%s): no legible, uso el del entorno", clave, exc_info=True)
        return respaldo
    return respaldo if valor is None else valor


# ── Atajos de los ajustes más leídos ─────────────────────────────────────────

def moneda_de_empresa(db, org_id: Optional[str] = None, *, registro: Any = None) -> str:
    """`DEFAULT_CURRENCY` de la empresa, en mayúsculas."""
    # Ronda 2 auditoria 2026-11-22 (§6 Moneda): el respaldo es la moneda del
    # despliegue (`DEFAULT_CURRENCY` del entorno), no "EUR" escrito aqui.
    return str(ajuste_de_empresa(db, "DEFAULT_CURRENCY", org_id, registro=registro)
               or app_settings.DEFAULT_CURRENCY or "EUR").strip().upper()


def iva_de_empresa(db, org_id: Optional[str] = None, *, registro: Any = None) -> float:
    """`DEFAULT_TAX_RATE` de la empresa (porcentaje: 21.0 = 21 %)."""
    return float(ajuste_de_empresa(db, "DEFAULT_TAX_RATE", org_id, registro=registro))


def jornada_de_empresa(db, org_id: Optional[str] = None, *, registro: Any = None) -> float:
    """`DEFAULT_WORKING_HOURS_PER_DAY` de la empresa (horas/día)."""
    return float(ajuste_de_empresa(db, "DEFAULT_WORKING_HOURS_PER_DAY", org_id, registro=registro))


def capacidad_semanal_de_empresa(db, org_id: Optional[str] = None, *, registro: Any = None) -> float:
    """`DEFAULT_WEEKLY_CAPACITY_HOURS` de la empresa (horas/semana)."""
    return float(ajuste_de_empresa(db, "DEFAULT_WEEKLY_CAPACITY_HOURS", org_id, registro=registro))


def capacidad_semanal(db, usuario: Any) -> float:
    """La capacidad semanal de `usuario`: la suya o, si no tiene, la de su empresa."""
    propia = getattr(usuario, "weekly_capacity_hours", None)
    if propia:
        return float(propia)
    return capacidad_semanal_de_empresa(db, registro=usuario)


def zona_de_empresa(db, org_id: Optional[str] = None, *, registro: Any = None) -> str:
    """`DEFAULT_TIMEZONE` de la empresa."""
    return str(ajuste_de_empresa(db, "DEFAULT_TIMEZONE", org_id, registro=registro))


def idioma_de_empresa(db, org_id: Optional[str] = None, *, registro: Any = None) -> str:
    """`DEFAULT_LANGUAGE` de la empresa."""
    return str(ajuste_de_empresa(db, "DEFAULT_LANGUAGE", org_id, registro=registro))


def idioma_elegido_de_empresa(db, org_id: Optional[str] = None, *, registro: Any = None) -> Optional[str]:
    """El idioma que la empresa (o la plataforma, en Configuración) ELIGIÓ; `None` si nadie lo eligió.

    Incidencia 5 de usuarios (23-11-2026): la interfaz resuelve el idioma así:
    preferencia del usuario > idioma de la empresa > idioma del navegador si
    se ofrece > inglés. El `DEFAULT_LANGUAGE` del entorno (castellano en
    `.env.example`) no cuenta como elección de la empresa: con él, todo el que
    no hubiera elegido veía castellano aunque su navegador estuviera en otro
    idioma. Esto solo afecta a la interfaz; los textos de salida (correos, PDF)
    siguen con `idioma_de_empresa`.
    """
    if db is None:
        return None
    try:
        from app.services.settings_service.runtime import _read_raw
        valor = _read_raw(db, "DEFAULT_LANGUAGE", empresa_de(db, registro, org_id))
    except Exception:
        logger.debug("idioma_elegido_de_empresa: no legible", exc_info=True)
        return None
    valor = (valor or "").strip().lower()
    return valor[:10] or None


# ── Altas: columnas con `default=settings.DEFAULT_*` ─────────────────────────
#
# 18-11-2026. Varias columnas llevan de default el valor global del entorno
# (`Invoice.tax_rate`, `*.currency`, `User.weekly_capacity_hours`,
# `*.timezone`, `*.language`…). Ese default se queda de respaldo, pero en un alta
# lo que vale es el ajuste de la empresa del registro: antes de cada flush,
# a cada objeto nuevo que no trae valor se le pone `ajuste_de_empresa(...)`.
# Así lo cumplen todos los servicios que crean registros, no solo los que se
# acuerdan de hacerlo.

#: Nombre de columna -> ajuste por empresa. Solo se rellena si el default de la
#: columna es exactamente `settings.<AJUSTE>` (las demás columnas con ese
#: nombre tienen su propio default y no se tocan).
COLUMNAS_POR_EMPRESA = {
    "tax_rate": "DEFAULT_TAX_RATE",
    "tax_pct": "DEFAULT_TAX_RATE",
    "currency": "DEFAULT_CURRENCY",
    "country": "DEFAULT_COUNTRY",  # 19-11-2026: clientes y proveedores
    "weekly_capacity_hours": "DEFAULT_WEEKLY_CAPACITY_HOURS",
    "hours_per_day": "DEFAULT_WORKING_HOURS_PER_DAY",
    "timezone": "DEFAULT_TIMEZONE",
    "language": "DEFAULT_LANGUAGE",
    "default_language": "DEFAULT_LANGUAGE",
    "locale": "DEFAULT_LANGUAGE",
}

#: Tablas que no se rellenan: la empresa misma no tiene «empresa del registro».
_TABLAS_EXCLUIDAS = {"organizations"}

_columnas_por_clase: dict = {}


def _columnas_a_rellenar(clase) -> list:
    """[(atributo, ajuste)] de `clase`, calculado una vez por clase."""
    if clase in _columnas_por_clase:
        return _columnas_por_clase[clase]
    salida = []
    try:
        from sqlalchemy import inspect as _inspect
        mapper = _inspect(clase)
        tabla = getattr(getattr(mapper, "local_table", None), "name", None)
        if tabla not in _TABLAS_EXCLUIDAS:
            for atributo in mapper.column_attrs:
                for col in atributo.columns:
                    clave = COLUMNAS_POR_EMPRESA.get(col.name)
                    defecto = getattr(col, "default", None)
                    if clave is None or defecto is None or not getattr(defecto, "is_scalar", False):
                        continue
                    if defecto.arg == getattr(app_settings, clave, object()):
                        salida.append((atributo.key, clave))
    except Exception:
        logger.debug("_columnas_a_rellenar(%s): sin mapeo", clase, exc_info=True)
    _columnas_por_clase[clase] = salida
    return salida


def rellenar_altas_por_empresa(session, flush_context=None, instances=None) -> None:
    """`before_flush`: rellena con el ajuste de la empresa lo que el alta no trae."""
    for obj in list(session.new):
        for atributo, clave in _columnas_a_rellenar(type(obj)):
            if getattr(obj, atributo, None) is None:
                setattr(obj, atributo, ajuste_de_empresa(session, clave, registro=obj))


def _registrar() -> None:
    from sqlalchemy import event
    from sqlalchemy.orm import Session
    if not event.contains(Session, "before_flush", rellenar_altas_por_empresa):
        event.listen(Session, "before_flush", rellenar_altas_por_empresa)


_registrar()
