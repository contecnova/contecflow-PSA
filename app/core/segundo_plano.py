"""Mandar trabajo lento a Celery desde la peticion (auditoria 2026-11).

Medido: solo 1 modulo de la API encolaba en Celery; el resto mandaba correos,
generaba PDFs o llamaba a terceros dentro de la peticion. `encolar` es la
forma comun de sacar ese trabajo cuando su resultado no hace falta para
responder (dispara y olvida).

    from app.core.segundo_plano import encolar
    encolar(NotificationService.send_email, to=..., subject=..., html_body=...)

La funcion se identifica por su ruta (`modulo:nombre`) y los argumentos viajan
en JSON, asi que solo vale para funciones de modulo o metodos estaticos con
argumentos serializables (nada de sesiones de BD ni objetos ORM: se pasan ids).

Sin broker (`REDIS_URL` vacio), en tests (`TESTING=1`) o si el envio a la cola
falla, se ejecuta en el momento: el comportamiento de siempre, nunca se pierde.

Contexto de empresa (segunda auditoria 2026-11). Lo que se encola es
`_ejecutar_con_contexto(ruta, organizacion, args, kwargs)`, no la funcion
directamente, asi la tarea del worker no cambia de firma:

    encolar(run_incremental_sync, config_id=cfg.id, _sesion=db)
    encolar(enviar_informe, informe_id, _organizacion=org_id)

  · `_organizacion` (explicita) o la de `_sesion.info` dicen en que empresa
    corre el trabajo. Ninguna de las dos llega a la funcion.
  · Si la funcion tiene un parametro `db` que nadie pasa, se le abre una sesion
    propia (`worker_db_session`) con el contexto publicado (`organization_id`,
    `is_superadmin=False`): el filtro de tenant aplica igual que en la peticion.
    Sin organizacion la sesion queda «no inicializada» (trabajo de plataforma).
    Si `db` es el primer parametro va en posicion; el resto, mejor por nombre.
  · En linea (sin cola) y con `_sesion`, se usa esa sesion: se ejecuta dentro
    de la peticion, que sigue viva.
  · `organizacion_en_curso()` la expone a funciones sin `db` que abran la suya.

`enviar_tarea("app.worker.<tarea>", args=[...])` encola una tarea del worker por
su nombre (Celery `send_task`) sin importar `app.worker`: ni `app/core` ni
`app/services` dependen del worker (auditoria 2026-11, #43).
"""
from __future__ import annotations

import contextvars
import importlib
import inspect
import logging
import sys
from app.core.entorno import en_pruebas
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)


def ruta_de(funcion: Callable) -> str:
    """`modulo:Clase.metodo` de una funcion importable."""
    return f"{funcion.__module__}:{funcion.__qualname__}"


def resolver(ruta: str) -> Callable:
    modulo, _, nombre = ruta.partition(":")
    # Solo codigo propio: un mensaje de la cola no puede pedir `os:system`.
    if not modulo.startswith("app.") or not nombre:
        raise ValueError(f"encolar: ruta no permitida {ruta!r}")
    objeto: Any = importlib.import_module(modulo)
    for parte in nombre.split("."):
        objeto = getattr(objeto, parte)
    return objeto


_cliente_celery = None


def _celery():
    """La app Celery del worker si ya esta cargada; si no, un cliente solo para
    encolar con el mismo broker que `app.worker.celery_app` (`REDIS_URL`)."""
    global _cliente_celery
    worker = sys.modules.get("app.worker")
    if worker is not None and hasattr(worker, "celery_app"):
        return worker.celery_app
    if _cliente_celery is None:
        from celery import Celery
        from app.core.config import settings

        _cliente_celery = Celery("contecflow", broker=settings.REDIS_URL, backend=settings.REDIS_URL)
    return _cliente_celery


def enviar_tarea(nombre: str, args: list | tuple = (), kwargs: Optional[dict] = None, **opciones: Any):
    """Encola la tarea `nombre` del worker (p. ej. `app.worker.deliver_webhook`).

    Mismo efecto que `tarea.apply_async(args=..., **opciones)`; lanza si el
    broker no responde, como aquel: quien llama decide que hacer.
    """
    return _celery().send_task(nombre, args=list(args), kwargs=kwargs or {}, **opciones)


def _hay_cola() -> bool:
    from app.core.config import settings

    return bool(settings.REDIS_URL) and not en_pruebas()


class _EnCola:
    """Lo que devuelve `encolar` cuando el trabajo se fue a la cola."""

    def __repr__(self) -> str:
        return "EN_COLA"


#: `encolar` devuelve esto si el trabajo va al worker; en linea, el resultado.
EN_COLA = _EnCola()


def respuesta_en_cola(**datos: Any):
    """202 con `{"data": {"ok": true, "status": "queued", ...}}`.

    `status: "queued"` es la forma que la interfaz ya entiende (auto-resolucion
    del service desk). Sin cola el endpoint devuelve el resultado de siempre.
    """
    from fastapi.responses import JSONResponse

    return JSONResponse(status_code=202, content={
        "data": {"ok": True, "status": "queued", **datos}, "meta": None})


_ORGANIZACION: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    "segundo_plano_organizacion", default=None)


def organizacion_en_curso() -> Optional[str]:
    """La empresa del trabajo de fondo que se esta ejecutando (o None)."""
    return _ORGANIZACION.get()


def _parametro_db(funcion: Callable) -> Optional[str]:
    """'posicion' si `db` es el primer parametro, 'nombre' si esta en otro sitio."""
    try:
        params = list(inspect.signature(funcion).parameters)
    except (TypeError, ValueError):
        return None
    if params and params[0] == "db":
        return "posicion"
    return "nombre" if "db" in params else None


def _publicar(sesion, organizacion: Optional[str]) -> None:
    if organizacion:
        sesion.info["organization_id"] = organizacion
        sesion.info["is_superadmin"] = False


def _llamar(funcion: Callable, organizacion: Optional[str], args: list, kwargs: dict,
            sesion=None) -> Any:
    marca = _ORGANIZACION.set(organizacion)
    try:
        donde = _parametro_db(funcion) if "db" not in kwargs else None
        if donde is None:
            return funcion(*args, **kwargs)
        if sesion is not None:  # en linea: la sesion de la peticion sigue viva
            return _con_sesion(funcion, donde, sesion, args, kwargs)
        from app.db.session import worker_db_session

        with worker_db_session() as propia:
            _publicar(propia, organizacion)
            return _con_sesion(funcion, donde, propia, args, kwargs)
    finally:
        _ORGANIZACION.reset(marca)


def _con_sesion(funcion, donde, sesion, args, kwargs):
    if donde == "posicion":
        return funcion(sesion, *args, **kwargs)
    return funcion(*args, db=sesion, **kwargs)


def _ejecutar_con_contexto(ruta: str, organizacion: Optional[str], args: list, kwargs: dict) -> Any:
    """Lo que ejecuta el worker: resuelve `ruta` y la llama en su empresa."""
    return _llamar(resolver(ruta), organizacion, list(args), dict(kwargs))


def encolar(funcion: Callable, *args: Any, _organizacion: Optional[str] = None,
            _sesion: Any = None, **kwargs: Any) -> Any:
    """Ejecuta `funcion(*args, **kwargs)` en el worker, o aqui si no hay cola.

    Devuelve `EN_COLA` si se encolo, o el resultado si se ejecuto en linea.

    `_organizacion` / `_sesion`: de donde sale la empresa del trabajo (ver el
    docstring del modulo). No se pasan a `funcion`.
    """
    organizacion = _organizacion
    if organizacion is None and _sesion is not None:
        organizacion = getattr(_sesion, "info", {}).get("organization_id")
    # Una closure no se puede mandar a la cola; en linea si se puede ejecutar.
    if _hay_cola() and "<locals>" not in getattr(funcion, "__qualname__", "<locals>"):
        try:
            enviar_tarea(
                "app.worker.ejecutar_en_segundo_plano",
                args=[ruta_de(_ejecutar_con_contexto),
                      [ruta_de(funcion), organizacion, list(args), kwargs], {}],
                retry=False)
            return EN_COLA
        except Exception as exc:
            logger.warning("encolar: sin cola para %s, se ejecuta en la peticion (%s)", ruta_de(funcion), exc)
    return _llamar(funcion, organizacion, list(args), kwargs, sesion=_sesion)
