"""Registro de metricas, separado del paquete (auditoria 2026-11).

Los submodulos hacian `from . import register_metric`, que importa el
`__init__` del paquete, y el `__init__` importa cada submodulo: 19 modulos en
un ciclo de import. El registro vive aqui y el paquete lo reexporta.
"""
from typing import Callable

# Type for metric handler function
MetricHandler = Callable[..., tuple[list[dict], dict]]

# Central registry: metric_id -> handler function
# Populated via @register_metric decorator at import time.
METRICS_REGISTRY: dict[str, MetricHandler] = {}


def register_metric(metric_id: str):
    """Decorator to register a metric handler."""
    def decorator(func: MetricHandler) -> MetricHandler:
        METRICS_REGISTRY[metric_id] = func
        return func
    return decorator


def register_metrics_from_module(module):
    """Auto-register all @register_metric decorated functions in a module."""
    for name in dir(module):
        attr = getattr(module, name)
        if callable(attr) and hasattr(attr, "_metric_id"):
            metric_id = attr._metric_id
            METRICS_REGISTRY[metric_id] = attr
