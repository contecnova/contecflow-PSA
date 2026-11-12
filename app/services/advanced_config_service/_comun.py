"""Logger y la excepcion `NotFoundError`, compartidos.

Parte de `app.services.advanced_config_service` (auditoria 2026-11, #24): se partio por responsabilidad
sin cambiar el codigo. El paquete reexporta todos los nombres.
"""
from __future__ import annotations

import logging


logger = logging.getLogger("app.services.advanced_config_service")


# ── Custom exceptions ─────────────────────────────────────────────────────────

class NotFoundError(ValueError):
    pass
