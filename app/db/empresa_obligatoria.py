"""`organization_id` obligatorio: las tablas exceptuadas y la empresa de una fila nueva (24-11-2026).

Migración `208_empresa_obligatoria_y_portal`. Docs: docs/seguridad/empresa_obligatoria.md.

Hasta la 207, 484 de las 558 tablas con `organization_id` lo admitían vacío. Una
fila sin empresa no la ve nadie (el filtro de tenant es `organization_id == org`)
o, peor, la ven todas si la tabla trae `_tenant_filter_include_global`. Desde la
208 la columna es NOT NULL en todas, salvo en las de esta lista: catálogos y
ajustes del sistema donde el NULL significa, a propósito y con código que lo lee
así, «valor de fábrica o del despliegue, común a todas las empresas».

Criterio, caso por caso (se replicaría por empresa si el NULL no lo leyera nadie
como valor común; aquí todas lo leen así):

- NULL = valor por defecto que la empresa puede sobreescribir con una fila
  propia (la suya pasa delante): replicarlo por empresa duplicaría el catálogo
  en cada alta y rompería la actualización de los valores de fábrica.
- NULL = suceso o dato del sistema que no es de ninguna empresa (auditoría del
  arranque, la siembra o un acceso con usuario desconocido).

`tests/test_empresa_obligatoria.py` vigila que la lista y los modelos casen:
toda tabla con `organization_id` nulable está aquí con su motivo, y ninguna de
aquí es NOT NULL. Añadir una tabla a la lista exige motivo y revisar el aislamiento.
"""
from __future__ import annotations

import logging
from functools import lru_cache
from typing import Optional

from sqlalchemy.orm.exc import UnmappedColumnError

logger = logging.getLogger("contecflow.tenant")

#: Tabla -> por qué puede tener filas sin empresa (NULL = común a todas).
TABLAS_SIN_EMPRESA_PERMITIDA: dict[str, str] = {
    # ── Catálogos y ajustes con `_tenant_filter_include_global` ───────────────
    "app_settings": "Ajustes del despliegue (llavero JWT, rotación de secretos, valores por defecto de "
                    "ejecución): NULL = valor global; la fila de la empresa manda si existe.",
    "settings_audit_log": "Rastro de los cambios de ajustes globales (los de NULL en app_settings).",
    "custom_project_types": "Catálogo de fábrica de tipos de proyecto, común a todas las empresas junto a los suyos.",
    "custom_project_statuses": "Catálogo de fábrica de estados de proyecto, común a todas las empresas junto a los suyos.",
    "custom_task_statuses": "Catálogo de fábrica de estados de tarea (todo, in_progress…), común a todas las empresas.",
    "custom_client_industries": "Catálogo de fábrica de sectores de cliente, común a todas las empresas.",
    "custom_expense_categories": "Catálogo de fábrica de categorías de gasto, común a todas las empresas.",
    "custom_supplier_service_types": "Catálogo de fábrica de tipos de servicio de proveedor, común a todas las empresas.",
    "custom_supplier_billing_units": "Catálogo de fábrica de unidades de facturación de proveedor, común a todas.",
    "ai_providers": "Proveedor de IA compartido del despliegue (respaldo cuando la empresa no tiene el suyo).",
    "grc_role_permissions": "Matriz de permisos por defecto de GRC; la empresa la sobreescribe con sus filas.",
    "exchange_rates": "Tipos de cambio públicos (BCE) comunes; los propios de la empresa pasan delante.",
    "integration_connectors": "Catálogo de conectores del marketplace que trae el producto.",
    # ── NULL leído como valor común por el código (sin la bandera) ────────────
    "integration_credentials": "Credenciales del despliegue (respaldo cuando la empresa no tiene las suyas; "
                               "`integration_credentials_service`).",
    "sso_configs": "SSO del despliegue (respaldo de `auth_service.sso`/`saml` si la empresa no tiene el suyo).",
    "alert_configs": "Umbrales de alertas por defecto (respaldo de `alert_service`).",
    "sla_calendars": "Calendario laboral de respaldo del SLA (`sla_service.calendario_sla`).",
    "country_employer_costs": "Presets de coste empleador por país que trae el producto (`cost_service`).",
    "bpmn_processes": "Procesos BPMN de plantilla, visibles para todas las empresas (`bpmn_process_service`).",
    "cmdb_discovery_providers": "Plantillas de proveedor de descubrimiento de la CMDB (`cmdb.discovery`).",
    # ── Sucesos del sistema ───────────────────────────────────────────────────
    "audit_logs": "Sucesos sin empresa (arranque, siembra, acceso con usuario desconocido); cadena de hash "
                  "propia para NULL (`app/db/cadena_auditoria.py`).",
}

#: Columnas de enlace por las que se deduce primero la empresa (proyecto, ticket, usuario).
PRIORIDAD_DE_DEDUCCION = ("project_id", "ticket_id", "user_id")


def exceptuada(tabla: str) -> bool:
    return tabla in TABLAS_SIN_EMPRESA_PERMITIDA


def _clase_de_tabla(tabla) -> Optional[type]:
    from app.db.base import Base
    for m in Base.registry.mappers:
        if m.local_table is tabla:
            return m.class_
    return None


@lru_cache(maxsize=None)
def _enlaces(cls) -> tuple:
    """(atributo, clase padre) de cada clave ajena a una tabla con `organization_id`, por prioridad."""
    import sqlalchemy as sa
    mapper = sa.inspect(cls)
    tabla = mapper.local_table
    enlaces = []
    for fk in tabla.foreign_keys:
        col, destino = fk.parent, fk.column.table
        if col.name == "organization_id" or destino.name == "organizations" or "organization_id" not in destino.c:
            continue
        if list(destino.primary_key.columns) != [fk.column]:
            continue  # `session.get` necesita la clave primaria
        padre = _clase_de_tabla(destino)
        if padre is None:
            continue
        try:
            atributo = mapper.get_property_by_column(col).key
        except UnmappedColumnError:  # columna sin propiedad mapeada
            continue
        enlaces.append((col.name, atributo, padre))
    orden = {n: i for i, n in enumerate(PRIORIDAD_DE_DEDUCCION)}
    enlaces.sort(key=lambda e: (orden.get(e[0], len(orden)), e[0]))
    relaciones = []
    for rel in mapper.relationships:
        if rel.direction.name == "MANYTOONE" and hasattr(rel.mapper.class_, "organization_id"):
            relaciones.append(rel.key)
    return tuple((a, p) for _, a, p in enlaces), tuple(relaciones)


def empresa_deducida(session, obj) -> Optional[str]:
    """La empresa de la fila nueva `obj` a partir de su proyecto, ticket, usuario o cualquier
    otro padre con empresa. None si no sale de ninguno."""
    cls = type(obj)
    try:
        enlaces, relaciones = _enlaces(cls)
    except Exception:
        logger.debug("sin enlaces deducibles en %s", cls.__name__, exc_info=True)
        return None
    # Primero lo ya cargado en memoria (el padre puede ser nuevo en este mismo flush).
    for rel in relaciones:
        padre = obj.__dict__.get(rel)
        org = getattr(padre, "organization_id", None) if padre is not None else None
        if org:
            return org
    for atributo, padre_cls in enlaces:
        ref = getattr(obj, atributo, None)
        if not ref:
            continue
        with session.no_autoflush:
            padre = session.get(padre_cls, ref)
        org = getattr(padre, "organization_id", None)
        if org:
            return org
    return None


def exigir_empresa(session) -> None:
    """Corta el flush si queda una fila nueva sin empresa en una tabla no exceptuada.

    Mejor un error con código y la tabla en el mensaje que un `IntegrityError`
    de NOT NULL sin contexto (o, en una base sin la 208, una fila que nadie ve).
    """
    for obj in list(session.new):
        cls = type(obj)
        if getattr(cls, "_tenant_exempt", False):
            continue
        definicion = getattr(cls, "__table__", None)
        if definicion is None or "organization_id" not in definicion.c or exceptuada(definicion.name):
            continue
        tabla = definicion.name
        try:
            vacia = getattr(obj, "organization_id", None) is None
        except Exception:
            logger.debug("no se pudo leer organization_id de %s", tabla, exc_info=True)
            continue
        if vacia:
            from app.core.codigos_de_error import error
            if superadmin_sin_empresa(session):
                # 24-11-2026: un superadmin sin empresa elegida que crea algo que
                # no cuelga de ningún padre con empresa. No es un fallo del
                # servidor: tiene que elegir empresa (selector de empresa) y
                # repetir. Nunca se elige por él una empresa al azar.
                logger.warning("tenant: superadmin sin empresa elegida creando en %s", tabla)
                raise error(409, "empresa_requerida", tabla=tabla)
            logger.error("tenant: fila nueva sin empresa en %s (no deducible del proyecto, ticket ni usuario)", tabla)
            raise error(500, "fila_sin_empresa", tabla=tabla)


def superadmin_sin_empresa(session) -> bool:
    """La sesión es la de una petición de un superadmin que no tiene empresa elegida."""
    info = getattr(session, "info", None) or {}
    if info.get("organization_id"):
        return False
    sujeto = info.get("current_user")
    return bool(sujeto is not None and getattr(sujeto, "is_superadmin", False)
                and not getattr(sujeto, "organization_id", None))


def empresa_para_registro(session, *candidatas) -> Optional[str]:
    """La empresa de una fila de REGISTRO (uso de IA, llamada a un conector,
    acción de IA, caché de traducción): la primera candidata con valor y, si
    no, la de la sesión. None si no hay ninguna.

    24-11-2026 (migración 208): estos registros se añaden a la sesión de quien
    llama. Sin empresa, el sellado cortaría su flush (`fila_sin_empresa`) y con
    él el trabajo principal, que no tiene la culpa. Quien llama, con None, no
    registra (y lo deja en el log): un registro sin empresa no lo vería nadie.
    """
    for candidata in candidatas:
        if candidata:
            return str(candidata)
    info = getattr(session, "info", None) or {}
    org = info.get("organization_id")
    return str(org) if org else None
