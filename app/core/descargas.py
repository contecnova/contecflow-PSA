"""Un fichero para descargar, sin objetos HTTP.

Auditoria 2026-11 (item 36): tres servicios (`exportador_tabular`,
`expense_service`, `report_builder_service`) construian un `StreamingResponse`
de FastAPI. Un servicio llamado desde Celery o un script no tiene respuesta que
devolver. Ahora devuelven una `Descarga` (los bytes, el tipo y las cabeceras) y
la capa API la convierte con `app.api.descargas.respuesta_de_descarga`.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Descarga:
    contenido: bytes
    media_type: str
    cabeceras: dict[str, str] = field(default_factory=dict)

    @property
    def nombre_de_fichero(self) -> str | None:
        """El `filename` de `Content-Disposition`, sin comillas, si lo hay."""
        disposicion = self.cabeceras.get("Content-Disposition", "")
        if "filename=" not in disposicion:
            return None
        return disposicion.split("filename=", 1)[1].strip().strip('"')
