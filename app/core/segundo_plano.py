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
"""
from __future__ import annotations

import importlib
import logging
import os
from typing import Any, Callable

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


def _hay_cola() -> bool:
    from app.core.config import settings

    return bool(settings.REDIS_URL) and os.getenv("TESTING") != "1"


def encolar(funcion: Callable, *args: Any, **kwargs: Any) -> None:
    """Ejecuta `funcion(*args, **kwargs)` en el worker, o aqui si no hay cola."""
    # Una closure no se puede mandar a la cola; en linea si se puede ejecutar.
    if _hay_cola() and "<locals>" not in getattr(funcion, "__qualname__", "<locals>"):
        try:
            from app.worker import ejecutar_en_segundo_plano

            ejecutar_en_segundo_plano.apply_async(args=[ruta_de(funcion), list(args), kwargs], retry=False)
            return
        except Exception as exc:
            logger.warning("encolar: sin cola para %s, se ejecuta en la peticion (%s)", ruta_de(funcion), exc)
    funcion(*args, **kwargs)
