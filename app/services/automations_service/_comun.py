"""Logger y `_v` (valor de un enum o el propio valor), compartidos.

Parte de `app.services.automations_service` (auditoria 2026-11, #24): se partio por responsabilidad
sin cambiar el codigo. El paquete reexporta todos los nombres.
"""
import logging


logger = logging.getLogger("app.services.automations_service")


def _v(x):
    return getattr(x, "value", x)
