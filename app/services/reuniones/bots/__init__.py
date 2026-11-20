"""Proveedores de bots de reunión. `proveedor(db, org)` da el de la empresa o lanza.

Para añadir otro proveedor: una clase de `ProveedorDeBots` y su entrada en
`_REGISTRO` (y en `config.PROVEEDORES_DE_BOTS`).
"""
from __future__ import annotations

from typing import Callable, Optional

from app.core.codigos_de_error import ErrorConCodigo
from app.services.reuniones.bots.base import ErrorDeBot, EventoDeBot, ProveedorDeBots
from app.services.reuniones.bots.recall import RecallBots

_REGISTRO: dict[str, Callable[..., ProveedorDeBots]] = {
    "recall": lambda api_key, region: RecallBots(api_key, region),
}

#: Las pruebas sustituyen aquí el proveedor (sin red).
_SUSTITUTO: Optional[ProveedorDeBots] = None


def proveedor(db, org: Optional[str], *, exigir_activo: bool = True) -> ProveedorDeBots:
    from app.services.reuniones import config
    cfg = config.leer(db, org)["bots"]
    if exigir_activo and not cfg["enabled"]:
        raise ErrorConCodigo("reuniones_bots_desactivados")
    if exigir_activo and not cfg.get("contract_reference"):
        raise ErrorConCodigo("reuniones_proveedor_sin_contrato")
    if _SUSTITUTO is not None:
        return _SUSTITUTO
    clave = config.secreto(db, org, "bots", "api_key")
    if not clave:
        raise ErrorConCodigo("reuniones_conector_sin_credenciales", plataforma="Recall.ai")
    return _REGISTRO[cfg["provider"]](clave, cfg["region"])


__all__ = ["ErrorDeBot", "EventoDeBot", "ProveedorDeBots", "RecallBots", "proveedor"]
