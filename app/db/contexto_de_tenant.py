"""Quién es la sesión: empresa, superadmin, contexto de sistema declarado o nada.

Auditoría 22-11-2026 (informe 01, M8, y «causa de fondo» del informe 02). El
filtro de empresa (`app/db/session.py`) y RLS (`app/db/rls.py`) salían por la
puerta de atrás, **en silencio**, con cualquier sesión que no trajera
`is_superadmin` en `info`: trabajos de fondo, rutas anónimas, scripts. Una
consulta «por id sin empresa» era defensa en profundidad dentro de una petición
y fuga real fuera de ella.

Ahora cada sesión está en uno de estos estados, y lo deciden las dos capas con
la misma función (`estado`):

- ``empresa``: `is_superadmin=False`; se filtra por `organization_id` (o
  ninguna fila si no hay empresa).
- ``libre``: superadmin explícito (`is_superadmin=True`), `sin_filtro_de_tenant`
  o un **contexto de sistema declarado** con su motivo (`contexto_de_sistema`
  para una sesión; `trabajo_de_sistema` para todo lo que corra dentro, p. ej.
  una tarea de Celery). Sin filtro, pero declarado y con nombre.
- ``sin_contexto``: nada de lo anterior. Según `TENANT_SESION_SIN_CONTEXTO`:
  ``cerrar`` → `TenantIsolationError` en el ORM y RLS sin filas; ``avisar`` →
  sigue sin filtro pero deja un WARNING por sitio de llamada (una vez por
  proceso) y lo cuenta en `SITIOS_SIN_CONTEXTO`.

Para recorrer empresas en un trabajo, `con_empresa(db, org)` en cada iteración
(ver `app/services/trabajos_de_fondo.en_cada_organizacion`).
"""
from __future__ import annotations

import logging
import os
import sys
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Iterator, Optional

logger = logging.getLogger("contecflow.tenant")

EMPRESA = "empresa"
LIBRE = "libre"
SIN_CONTEXTO = "sin_contexto"


class TenantIsolationError(RuntimeError):
    """No se puede demostrar el aislamiento de tenant para una consulta.

    Se lanza en vez de devolver la consulta sin filtrar. Un 500 es un incidente
    que se investiga; una consulta sin filtro de tenant es una fuga silenciosa
    entre clientes que nadie ve (auditoría 2026-08, P1-7).
    """

MODO_CERRAR = "cerrar"
MODO_AVISAR = "avisar"
MODOS = (MODO_CERRAR, MODO_AVISAR)

#: Clave de `session.info` con el motivo del contexto de sistema de la sesión.
CLAVE_SISTEMA = "contexto_de_sistema"

#: Contexto de sistema del trabajo en curso (tarea de Celery, job de APScheduler,
#: script): lo heredan todas las sesiones que se usen dentro.
_TRABAJO_DE_SISTEMA: ContextVar[Optional[str]] = ContextVar("contecflow_trabajo_de_sistema", default=None)

#: Sitio de llamada → veces que una sesión sin contexto tocó datos de empresa.
SITIOS_SIN_CONTEXTO: dict[str, int] = {}


def motivo_de_sistema(info) -> Optional[str]:
    """El motivo declarado (de la sesión o del trabajo en curso), o None."""
    return (info or {}).get(CLAVE_SISTEMA) or _TRABAJO_DE_SISTEMA.get()


def estado(info) -> str:
    """`empresa`, `libre` o `sin_contexto` (ver la cabecera)."""
    info = info or {}
    if info.get("bypass_tenant_filter") is True:
        return LIBRE
    superadmin = info.get("is_superadmin", None)
    if superadmin is True:
        return LIBRE
    if superadmin is False:
        return EMPRESA
    if motivo_de_sistema(info):
        return LIBRE
    return SIN_CONTEXTO


def modo() -> str:
    from app.core.config import settings
    valor = str(getattr(settings, "TENANT_SESION_SIN_CONTEXTO", MODO_CERRAR) or MODO_CERRAR).strip().lower()

    return valor if valor in MODOS else MODO_CERRAR   # un valor desconocido no abre


def _sitio_de_llamada() -> str:
    """Primer marco fuera de SQLAlchemy y de la capa de sesión: «fichero:línea»."""
    propios = (os.sep + "sqlalchemy" + os.sep, "contexto_de_tenant.py", os.path.join("app", "db", "session.py"),
               os.path.join("app", "db", "rls.py"))
    marco = sys._getframe(1)
    while marco is not None:
        nombre = marco.f_code.co_filename
        if not any(p in nombre for p in propios) and "contextlib" not in nombre:
            ruta = nombre.replace("\\", "/")
            corte = ruta.rfind("/app/")
            return f"{ruta[corte + 1:] if corte >= 0 else ruta}:{marco.f_lineno}"
        marco = marco.f_back
    return "desconocido"


def sin_contexto(modelos) -> None:
    """Una sesión sin contexto va a tocar `modelos` de empresa: cierra o avisa."""
    nombres = ", ".join(sorted({getattr(m, "__name__", str(m)) for m in modelos})) or "?"
    sitio = _sitio_de_llamada()
    if modo() == MODO_CERRAR:
        raise TenantIsolationError(
            f"Sesión sin contexto de empresa ({nombres}) en {sitio}: publica la empresa "
            "(`con_empresa`, `publicar_contexto_de_tenant`) o declara el contexto de sistema "
            "(`contexto_de_sistema`/`trabajo_de_sistema`) con su motivo.")
    veces = SITIOS_SIN_CONTEXTO.get(sitio, 0)
    SITIOS_SIN_CONTEXTO[sitio] = veces + 1
    if veces == 0:
        logger.warning("tenant: sesión sin contexto de empresa ni de sistema en %s (%s); sin filtro. "
                       "TENANT_SESION_SIN_CONTEXTO=cerrar lo bloquea.", sitio, nombres)


@contextmanager
def contexto_de_sistema(session, motivo: str) -> Iterator:
    """Declara que esta sesión trabaja entre empresas, con su motivo."""
    if not motivo:
        raise ValueError("el contexto de sistema necesita un motivo")
    previo = session.info.get(CLAVE_SISTEMA)
    session.info[CLAVE_SISTEMA] = motivo
    try:
        yield session
    finally:
        if previo is None:
            session.info.pop(CLAVE_SISTEMA, None)
        else:
            session.info[CLAVE_SISTEMA] = previo


def declarar_sistema(session, motivo: str):
    """Una sesión creada a mano (`SessionLocal()` en un WebSocket, un hilo, un script)
    declara su contexto de sistema para TODA su vida, con su motivo.

    Auditoría 22-11-2026 (M8, `TENANT_SESION_SIN_CONTEXTO=cerrar`): es
    `contexto_de_sistema` sin bloque `with`, para la línea siguiente a
    `SessionLocal()`. Si luego se publica la empresa (`publicar_contexto_de_tenant`,
    `con_empresa`), la empresa manda. Devuelve la sesión.
    """
    if not motivo:
        raise ValueError("el contexto de sistema necesita un motivo")
    info = getattr(session, "info", None)
    if info is not None:
        info[CLAVE_SISTEMA] = motivo
    return session


def fijar_contexto(session, org_id, motivo: str):
    """Sesión creada a mano que ya sabe su empresa: en ella (filtro, sellado, RLS)
    para toda su vida; sin empresa, contexto de sistema declarado con `motivo`.

    Para tareas en segundo plano y callbacks que reciben la empresa por
    argumento (`bg_db = SessionLocal(); fijar_contexto(bg_db, org, "...")`).
    Devuelve la sesión.
    """
    if org_id:
        info = getattr(session, "info", None)
        if info is not None:
            info["organization_id"] = org_id
            info["is_superadmin"] = False
        return session
    return declarar_sistema(session, motivo)


@contextmanager
def trabajo_de_sistema(motivo: str) -> Iterator[None]:
    """Todo lo que corra dentro (y sus sesiones sin contexto) es trabajo de sistema declarado."""
    if not motivo:
        raise ValueError("el trabajo de sistema necesita un motivo")
    marca = _TRABAJO_DE_SISTEMA.set(motivo)
    try:
        yield
    finally:
        _TRABAJO_DE_SISTEMA.reset(marca)


def declarar_trabajo_de_sistema(motivo: Optional[str]):
    """Versión sin `with` para señales (Celery `task_prerun`/`task_postrun`). Devuelve la marca."""
    return _TRABAJO_DE_SISTEMA.set(motivo)


def retirar_trabajo_de_sistema(marca) -> None:
    try:
        _TRABAJO_DE_SISTEMA.reset(marca)
    except (ValueError, LookupError):
        _TRABAJO_DE_SISTEMA.set(None)


@contextmanager
def con_empresa(session, org_id) -> Iterator:
    """La sesión trabaja en la empresa `org_id` (filtro, sellado y RLS) y vuelve como estaba.

    Para los trabajos que recorren empresas: una llamada por iteración. Sin
    empresa no se abre: `ValueError` (para trabajar entre empresas, declara
    `contexto_de_sistema`).
    """
    if not org_id:
        raise ValueError("con_empresa necesita una empresa")
    claves = ("organization_id", "is_superadmin")
    previo = {k: session.info.get(k, _AUSENTE) for k in claves}
    session.info["organization_id"] = org_id
    session.info["is_superadmin"] = False
    try:
        yield session
    finally:
        for k, v in previo.items():
            if v is _AUSENTE:
                session.info.pop(k, None)
            else:
                session.info[k] = v


_AUSENTE = object()
