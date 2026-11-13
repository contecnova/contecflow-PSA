"""Lo que un servicio necesita para dejar trabajo para despues de responder.

Auditoria 2026-11 (item 36): `task_service` y `semantic_feedback_service`
tipaban su parametro con `fastapi.BackgroundTasks`. Lo unico que usan es
`add_task(funcion, *args, **kwargs)`, asi que piden eso: el `BackgroundTasks`
de la peticion lo cumple, y fuera de HTTP vale cualquier objeto con ese metodo
(p. ej. uno que ejecute en el momento o que encole con `segundo_plano.encolar`).
"""
from __future__ import annotations

from typing import Any, Callable, Protocol


class ProgramadorDeTareas(Protocol):
    def add_task(self, func: Callable[..., Any], *args: Any, **kwargs: Any) -> Any: ...
