"""Errores de dominio: lo que los servicios lanzan en lugar de `HTTPException`.

Auditoria 2026-11: 930 `raise HTTPException` en 138 ficheros de `app/services`
ataban la logica de negocio a FastAPI. Un servicio llamado desde Celery, un
script o el bus de eventos lanzaba una excepcion HTTP que alli no significa
nada. `ErrorDeDominio` lleva lo mismo (`status_code`, `detail`, `headers`) sin
depender del framework; `app/main.py` lo traduce a la misma respuesta HTTP que
daba antes `HTTPException`, asi que la API no cambia.

La firma es la de `HTTPException` a proposito: el paso fue mecanico
(`scripts/codemods/servicios_sin_http.py`).
"""
from __future__ import annotations

from typing import Any, Optional


class ErrorDeDominio(Exception):
    """Fallo de negocio con el codigo HTTP que le corresponde si sale por la API.

    16-11-2026: `code` y `params` (opcionales) viajan en la respuesta junto a
    `detail` (`{"detail", "code", "params"}`) para que el portal de clientes
    pinte el error en el idioma del cliente (`err_srv.<code>`); `detail` sigue
    siendo el texto de siempre. Catalogo: `app/core/codigos_de_error.py`.
    """

    def __init__(self, status_code: int, detail: Any = None, headers: Optional[dict] = None, *,
                 code: Optional[str] = None, params: Optional[dict] = None) -> None:
        self.status_code = status_code
        self.detail = detail
        self.headers = headers
        self.code = code
        self.params = params
        super().__init__(detail if detail is not None else status_code)

    def __repr__(self) -> str:
        return f"{type(self).__name__}(status_code={self.status_code!r}, detail={self.detail!r})"
