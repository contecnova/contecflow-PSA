"""
Metrics service: Declarative metric registry and handler system.

Each metric is defined as an independent function with standardized signature:
    def metric_handler(db: Session, d_from: date, d_to: date, top_n: int,
                      project_id: Optional[str], user_id: Optional[str],
                      project_ids: Optional[list[str]], **kwargs) -> tuple[list[dict], dict]

Returns:
    (rows: list[dict], meta_patch: dict)
    - rows: List of data points with {"label", "value", ...}
    - meta_patch: Optional metadata overrides (e.g., chart type)
"""
from typing import Callable, Optional
from sqlalchemy.orm import Session
from datetime import date

# Type for metric handler function
MetricHandler = Callable[..., tuple[list[dict], dict]]

# Central registry: metric_id -> handler function
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


# ──────────────────────────────────────────────────────────────────────────────

# Import metric modules to trigger registration (auto-register via @register_metric)
from . import hours
from . import costs
from . import projects
from . import capacity
from . import service_desk
from . import rrhh
from . import business
from . import alm
from . import remaining
from . import advanced

__all__ = ["METRICS_REGISTRY", "register_metric"]
