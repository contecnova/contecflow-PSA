"""Catálogo GRC — módulos y acciones DERIVADOS de las rutas reales.

Auditoría 2026-08 (hallazgos 27 y 28). Antes, la matriz de permisos de GRC
enumeraba 15 módulos escritos a mano en un diccionario, frente a los 126 dominios
que expone la API. Aunque se hubiera aplicado, 111 dominios no tenían ni una
casilla que configurar.

Este módulo elimina esa lista. Las dos dimensiones de un permiso se CALCULAN a
partir de la propia petición:

  módulo  ← el primer segmento del path bajo /api/vN  (/api/v1/invoices → invoices)
  acción  ← el método HTTP, más el path para distinguir aprobar y exportar

La consecuencia es que la cobertura no puede quedarse atrás: un dominio nuevo
aparece en el catálogo el día que se añade su primera ruta, sin que nadie tenga
que acordarse de registrarlo. No hay mapeo que mantener ni que se pueda podrir.

── Exenciones ────────────────────────────────────────────────────────────────
No se crea una segunda lista: se reutiliza `ABAC_EXEMPT_PREFIXES`, que ya
enumera con su motivo los prefijos sin principal `User` (login, portal de
cliente, webhooks firmados, SCIM, WebSocket, catálogos públicos). Esos motivos
valen igual para GRC, y `tests/test_abac_coverage.py` ya vigila que la lista no
acumule prefijos obsoletos. Una sola fuente de verdad para las exenciones.
"""
from __future__ import annotations

from typing import Iterable, Optional

from app.core.abac_registry import ABAC_EXEMPT_PREFIXES

# Las seis acciones del modelo GRC. Es el vocabulario de la matriz, no una
# lista de rutas: no crece con el producto.
GRC_ACTIONS: tuple[str, ...] = ("ver", "crear", "editar", "eliminar", "aprobar", "exportar")

# Señales en el path que indican una acción de negocio distinta de la que
# sugeriría el método HTTP por sí solo. Un POST a /approve es "aprobar", no
# "crear"; un GET a /export es "exportar", no "ver".
_APPROVAL_HINTS: tuple[str, ...] = ("approve", "aprob", "reject", "rechaz", "sign-off", "signoff")
_EXPORT_HINTS: tuple[str, ...] = ("export", "download", "/pdf", "excel", "xlsx", "/csv", "report-file")


def is_exempt(path: str) -> bool:
    """¿Está el path fuera del alcance de GRC, con motivo declarado?"""
    return any(path == p or path.startswith(p + "/") for p in ABAC_EXEMPT_PREFIXES)


def module_for_path(path: str) -> Optional[str]:
    """Módulo GRC de un path de API, o None si no procede.

    `/api/v1/invoices/{id}/lines` → `invoices`. Se toma el primer segmento tras
    la versión porque es el límite natural de dominio en esta API: cada uno de
    los 126 prefijos corresponde a un módulo funcional del producto.
    """
    if not path.startswith("/api/v"):
        return None
    if is_exempt(path):
        return None
    parts = path.split("/")
    if len(parts) < 4 or not parts[3]:
        return None
    modulo = parts[3]
    # Rutas de infraestructura de la propia documentación: no son dominios.
    if modulo in {"openapi.json", "docs", "redoc"}:
        return None
    return modulo


def action_for(method: str, path: str) -> Optional[str]:
    """Acción GRC de un método HTTP sobre un path.

    El método da la intención general y el path la matiza: sin esa segunda
    señal, `POST /approvals/{id}/approve` se clasificaría como "crear" y la
    acción `aprobar` de la matriz no se usaría nunca — justo el tipo de casilla
    decorativa que esta auditoría está eliminando.
    """
    m = (method or "").upper()
    if m in ("HEAD", "OPTIONS"):
        return None
    low = path.lower()
    if any(h in low for h in _APPROVAL_HINTS):
        return "aprobar"
    if any(h in low for h in _EXPORT_HINTS):
        return "exportar"
    if m == "GET":
        return "ver"
    if m == "POST":
        return "crear"
    if m in ("PUT", "PATCH"):
        return "editar"
    if m == "DELETE":
        return "eliminar"
    return None


def discover_modules(app) -> list[str]:
    """Todos los módulos GRC alcanzables en la aplicación, ordenados.

    Se lee del router en tiempo de ejecución: es la definición de "todas las
    funcionalidades de la solución" que la matriz debe cubrir.
    """
    out: set[str] = set()
    for route in getattr(app, "routes", []):
        modulo = module_for_path(getattr(route, "path", "") or "")
        if modulo:
            out.add(modulo)
    return sorted(out)


def discover_module_actions(app) -> dict[str, set[str]]:
    """Acciones realmente alcanzables en cada módulo.

    Sirve para no crear casillas que no corresponden a nada: si un módulo sólo
    expone GET, su fila tendrá `ver` y no las otras cinco. Una matriz con
    casillas inertes es indistinguible de una matriz con casillas que no se
    aplican, y el objetivo es que todo lo que se ve gobierne algo.
    """
    out: dict[str, set[str]] = {}
    for route in getattr(app, "routes", []):
        path = getattr(route, "path", "") or ""
        modulo = module_for_path(path)
        if not modulo:
            continue
        for method in (getattr(route, "methods", None) or set()):
            accion = action_for(method, path)
            if accion:
                out.setdefault(modulo, set()).add(accion)
    return out


__all__: Iterable[str] = (
    "GRC_ACTIONS",
    "action_for",
    "discover_module_actions",
    "discover_modules",
    "is_exempt",
    "module_for_path",
)
