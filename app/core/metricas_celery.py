"""Métricas del worker y del beat de Celery (22-11-2026).

La API no ve lo que pasa en el worker (otro proceso, otro contenedor), así que
el worker y el beat exponen su propio `/metrics` con `CELERY_METRICS_PORT`
(0 = apagado, el defecto: en desarrollo local no se abre ningún puerto).
docker-compose.yml lo enciende en el 9808 (worker) y el 9809 (beat), SOLO en la
red interna de compose: no se publican en el host y por eso no llevan token.

* Worker: tareas por nombre y resultado, duración, reintentos. Con el pool
  prefork cada hijo escribe en `PROMETHEUS_MULTIPROC_DIR` y el servidor del
  proceso padre los suma (MultiProcessCollector).
* Beat: tareas publicadas por nombre. Que el beat esté vivo lo dice el `up` de
  Prometheus sobre su puerto (la regla `CeleryBeatCaido`).

Etiquetas: solo el nombre de la tarea (código, acotado). Nunca argumentos.
"""
from __future__ import annotations

import logging
import time

from prometheus_client import Counter, Histogram

logger = logging.getLogger("contecflow.metrics")

celery_tareas_total = Counter(
    "contecflow_celery_tareas_total",
    "Tareas de Celery terminadas por nombre y resultado (ok | error | reintento | rechazada).",
    labelnames=("tarea", "resultado"),
)

celery_duracion_seconds = Histogram(
    "contecflow_celery_tarea_duracion_seconds",
    "Duración de las tareas de Celery.",
    labelnames=("tarea",),
    buckets=(0.1, 0.5, 1, 2.5, 5, 10, 30, 60, 120, 300, 600, 1800),
)

celery_publicadas_total = Counter(
    "contecflow_celery_tareas_publicadas_total",
    "Tareas publicadas en la cola (por el beat u otros procesos) por nombre.",
    labelnames=("tarea",),
)

_inicios: dict = {}
_instalado = False


def _nombre(tarea) -> str:
    nombre = getattr(tarea, "name", None) or str(tarea or "desconocida")
    return nombre[:120]


def _al_empezar(task_id=None, task=None, **_kw) -> None:
    try:
        _inicios[task_id] = time.perf_counter()
    except Exception:
        logger.debug("metricas_celery: prerun best-effort", exc_info=True)


def _al_terminar(task_id=None, task=None, state=None, **_kw) -> None:
    try:
        inicio = _inicios.pop(task_id, None)
        nombre = _nombre(task)
        if inicio is not None:
            celery_duracion_seconds.labels(tarea=nombre).observe(time.perf_counter() - inicio)
        resultado = {"SUCCESS": "ok", "FAILURE": "error", "RETRY": "reintento"}.get(str(state or ""), None)
        if resultado:
            celery_tareas_total.labels(tarea=nombre, resultado=resultado).inc()
    except Exception:
        logger.debug("metricas_celery: postrun best-effort", exc_info=True)


def _al_rechazar(message=None, **_kw) -> None:
    try:
        cabeceras = getattr(message, "headers", None) or {}
        celery_tareas_total.labels(tarea=str(cabeceras.get("task") or "desconocida")[:120],
                                   resultado="rechazada").inc()
    except Exception:
        logger.debug("metricas_celery: rejected best-effort", exc_info=True)


def _al_publicar(sender=None, **_kw) -> None:
    try:
        celery_publicadas_total.labels(tarea=str(sender or "desconocida")[:120]).inc()
    except Exception:
        logger.debug("metricas_celery: publish best-effort", exc_info=True)


def _servidor(puerto: int, *, multiproceso: bool) -> None:
    from prometheus_client import CollectorRegistry, start_http_server
    from app.core.config import settings

    directorio = settings.METRICS_MULTIPROC_DIR if multiproceso else None
    if directorio:
        from prometheus_client import multiprocess
        registro = CollectorRegistry()
        multiprocess.MultiProcessCollector(registro, path=directorio)
        start_http_server(puerto, registry=registro)
    else:
        start_http_server(puerto)
    logger.info("Métricas de Celery en :%s/metrics (multiproceso=%s)", puerto, bool(directorio))


def _al_arrancar_worker(**_kw) -> None:
    from app.core.config import settings
    try:
        if int(settings.CELERY_METRICS_PORT or 0) > 0:
            _servidor(int(settings.CELERY_METRICS_PORT), multiproceso=True)
    except Exception:
        logger.warning("No se pudo abrir el servidor de métricas del worker", exc_info=True)


def _al_arrancar_beat(**_kw) -> None:
    from app.core.config import settings
    try:
        if int(settings.CELERY_METRICS_PORT or 0) > 0:
            _servidor(int(settings.CELERY_METRICS_PORT), multiproceso=False)
    except Exception:
        logger.warning("No se pudo abrir el servidor de métricas del beat", exc_info=True)


def instalar() -> None:
    """Conecta las señales de Celery. Idempotente; la llama `app/worker.py`."""
    global _instalado
    if _instalado:
        return
    from celery import signals

    signals.task_prerun.connect(_al_empezar, weak=False)
    signals.task_postrun.connect(_al_terminar, weak=False)
    signals.task_rejected.connect(_al_rechazar, weak=False)
    signals.before_task_publish.connect(_al_publicar, weak=False)
    signals.worker_ready.connect(_al_arrancar_worker, weak=False)
    signals.beat_init.connect(_al_arrancar_beat, weak=False)
    _instalado = True


__all__ = ["instalar", "celery_tareas_total", "celery_duracion_seconds", "celery_publicadas_total"]
