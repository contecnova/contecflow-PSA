"""Menú lateral personalizable: forma de la preferencia y menú por defecto por rol (23-11-2026).

Feedback de usuarios («menú personalizable»). Cada persona puede reordenar las
categorías del menú lateral (y las pestañas dentro de cada una) y ocultar las
pestañas que no usa. Se guarda en dos sitios, con la MISMA forma:

* **La de la persona**: `user_preferences.extra["menu"]` (`PATCH
  /users/me/preferences`); le sigue en cualquier equipo.
* **La de su rol** (por empresa): ajuste `menu.por_defecto` en `app_settings`
  (fila de la empresa; sin migración), que fija el administrador en
  Configuración › «Menú por defecto» (`org.administrar`). Queda en `audit_log`.

Forma (`version` = `VERSION`)::

    {"version": 1,
     "orden": ["trabajo", "proyectos", ...],          # ids de categoría
     "ocultas": {"proyectos": ["/gantt", ...]},       # rutas ocultas por categoría
     "orden_pestanas": {"proyectos": ["/projects", ...]}}

Tolerancia: el frontend (`frontend/src/permisos/menuPersonal.ts`) ignora los
ids y rutas que ya no existen y pone al final, visibles, las categorías y
pestañas nuevas. Por eso aquí solo se valida la forma (no la lista de rutas del
menú, que vive en el frontend). Ocultar no quita permisos: el menú se filtra
antes por la matriz de permisos y la ruta oculta se sigue abriendo.
"""
from __future__ import annotations
import logging

import json
import re
from typing import Any, Optional

from sqlalchemy.orm import Session

from app.core.codigos_de_error import error

#: Versión del esquema de la preferencia de menú.
VERSION = 1
#: Clave en `app_settings` (con punto: estado interno, fuera de la pantalla General).
CLAVE = "menu.por_defecto"

_ID = re.compile(r"^[a-z][a-z0-9_]{0,39}$")
_RUTA = re.compile(r"^/[A-Za-z0-9/_:.-]{0,120}$")
_MAX_CATEGORIAS = 40
_MAX_RUTAS = 100


def _no_valido(detalle: str):
    # Código genérico del catálogo (`valor_no_valido`): la interfaz ya lo traduce.
    return error(422, "valor_no_valido", detail=f"Menú: {detalle}", valor=detalle)


def _lista(valor: Any, patron: re.Pattern, maximo: int, que: str) -> list[str]:
    if valor is None:
        return []
    if not isinstance(valor, list):
        raise _no_valido(f"{que}: se esperaba una lista")
    salida: list[str] = []
    for v in valor:
        if not isinstance(v, str) or not patron.match(v):
            raise _no_valido(f"{que}: valor no válido {v!r}")
        if v not in salida:
            salida.append(v)
    if len(salida) > maximo:
        raise _no_valido(f"{que}: como mucho {maximo}")
    return salida


def _por_categoria(valor: Any, que: str) -> dict[str, list[str]]:
    if valor is None:
        return {}
    if not isinstance(valor, dict):
        raise _no_valido(f"{que}: se esperaba un objeto por categoría")
    if len(valor) > _MAX_CATEGORIAS:
        raise _no_valido(f"{que}: demasiadas categorías")
    salida: dict[str, list[str]] = {}
    for cat, rutas in valor.items():
        if not isinstance(cat, str) or not _ID.match(cat):
            raise _no_valido(f"{que}: categoría no válida {cat!r}")
        lista = _lista(rutas, _RUTA, _MAX_RUTAS, f"{que}.{cat}")
        if lista:
            salida[cat] = lista
    return salida


def normalizar_menu(valor: Any) -> dict:
    """La preferencia de menú validada y limpia (422 `valor_no_valido` si la forma no vale).

    Se quitan las claves desconocidas y los duplicados; `version` pasa a la actual
    (la v1 es la primera: no hay nada que migrar todavía).
    """
    if not isinstance(valor, dict):
        raise _no_valido("el menú es un objeto")
    version = valor.get("version", VERSION)
    if not isinstance(version, int) or version < 1:
        raise _no_valido("versión no válida")
    return {
        "version": VERSION,
        "orden": _lista(valor.get("orden"), _ID, _MAX_CATEGORIAS, "orden"),
        "ocultas": _por_categoria(valor.get("ocultas"), "ocultas"),
        "orden_pestanas": _por_categoria(valor.get("orden_pestanas"), "orden_pestanas"),
    }


def normalizar_por_rol(valor: Any) -> dict:
    """`{"version": 1, "roles": {rol: menú}}` con roles reales (`users.role`)."""
    from app.core.capacidades import ROLES
    if not isinstance(valor, dict):
        raise _no_valido("se esperaba un objeto")
    roles = valor.get("roles") or {}
    if not isinstance(roles, dict):
        raise _no_valido("roles: se esperaba un objeto por rol")
    salida: dict[str, dict] = {}
    for rol, menu in roles.items():
        if rol not in ROLES:
            raise _no_valido(f"rol desconocido {rol!r}")
        if menu is None:
            continue  # sin menú propio: el del código
        salida[rol] = normalizar_menu(menu)
    return {"version": VERSION, "roles": salida}


def leer(db: Session, org_id: Optional[str]) -> dict:
    """El menú por defecto de cada rol de la empresa (vacío si no hay o no se lee)."""
    from app.services.settings_service.runtime import _read_raw
    crudo = _read_raw(db, CLAVE, org_id)
    if not crudo:
        return {"version": VERSION, "roles": {}}
    try:
        return normalizar_por_rol(json.loads(crudo))
    except Exception:  # fila antigua o dañada: como si no hubiera
        logging.getLogger(__name__).debug("leer: excepcion ignorada", exc_info=True)
        return {"version": VERSION, "roles": {}}


def del_rol(db: Session, org_id: Optional[str], rol: Optional[str]) -> Optional[dict]:
    """El menú por defecto del rol (`None`: el orden del código, todo visible)."""
    rol = str(getattr(rol, "value", rol) or "")
    return leer(db, org_id)["roles"].get(rol)


def guardar(db: Session, org_id: Optional[str], valor: Any, usuario: Any = None,
            ip: Optional[str] = None, agente: Optional[str] = None) -> dict:
    """Guarda el menú por defecto de los roles de la empresa y lo deja en `audit_log`."""
    from app.models.settings import AppSetting
    from app.services.audit import audit_log
    from app.services.settings_service.runtime import invalidate_cache
    nuevo = normalizar_por_rol(valor)
    anterior = leer(db, org_id)
    consulta = db.query(AppSetting).filter(AppSetting.key == CLAVE)
    fila = (consulta.filter(AppSetting.organization_id == org_id) if org_id is not None
            else consulta.filter(AppSetting.organization_id.is_(None))).first()
    texto = json.dumps(nuevo, ensure_ascii=False, separators=(",", ":"))
    if fila is None:
        db.add(AppSetting(key=CLAVE, value=texto, organization_id=org_id,
                          description="Menú lateral por defecto de cada rol (orden y pestañas ocultas)"))
    else:
        fila.value = texto
    audit_log(db, usuario, "UPDATE", "menu_por_defecto", resource_id=org_id, resource_name=CLAVE,
              old_values=anterior, new_values=nuevo, ip_address=ip, user_agent=agente)
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise
    invalidate_cache(CLAVE)
    return nuevo
