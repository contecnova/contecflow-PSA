"""
Prometheus metrics — RED HTTP metrics via prometheus-fastapi-instrumentator
plus a small set of domain counters/histograms that other modules can import
and increment.

Activation: set `METRICS_ENABLED=1`. The /metrics endpoint can be protected
with `METRICS_AUTH_TOKEN` (Bearer). For multi-worker deployments set
`PROMETHEUS_MULTIPROC_DIR` to a writable directory before the server starts.

Usage from other modules:

    from app.core.metrics import business_event_total
    business_event_total.labels(event="ticket_created", tenant_id=str(t.id)).inc()
"""
from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, Request
from app.core.codigos_de_error import error_http

logger = logging.getLogger("contecflow.metrics")


# ── Prometheus client objects ────────────────────────────────────────────────
# Imported eagerly so other modules can import the metric handles even when the
# /metrics endpoint is disabled (the counters become no-op writers that cost
# almost nothing).
from prometheus_client import CollectorRegistry, Counter, Gauge, Histogram

# Module-level metrics. Labels intentionally low cardinality.
app_info = Gauge(
    "contecflow_app_info",
    "Contecflow PSA build info (always 1; labels carry version/env).",
    labelnames=("version", "environment"),
)

business_event_total = Counter(
    "contecflow_business_event_total",
    "Business-level events (ticket_created, invoice_generated, sla_breach, ...).",
    labelnames=("event", "tenant_id"),
)

tickets_created_total = Counter(
    "contecflow_tickets_created_total",
    "Service-desk tickets created.",
    labelnames=("tenant_id", "ticket_type", "priority", "source"),
)

invoices_created_total = Counter(
    "contecflow_invoices_created_total",
    "Invoices created.",
    labelnames=("tenant_id", "status"),
)

scheduled_job_duration_seconds = Histogram(
    "contecflow_scheduled_job_duration_seconds",
    "Wall-clock duration of background/scheduled jobs.",
    labelnames=("job_name", "status"),
    buckets=(0.1, 0.5, 1, 2.5, 5, 10, 30, 60, 120, 300, 600),
)

abac_denials_total = Counter(
    "contecflow_abac_denials_total",
    "ABAC enforcement denials grouped by resource/action.",
    labelnames=("resource_type", "action"),
)

external_api_calls_total = Counter(
    "contecflow_external_api_calls_total",
    "Outbound calls to third-party APIs (Jira, Xero, Twilio, Graph, ...).",
    labelnames=("provider", "outcome"),
)

external_api_latency_seconds = Histogram(
    "contecflow_external_api_latency_seconds",
    "Latency of outbound calls to third-party APIs.",
    labelnames=("provider",),
    buckets=(0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10, 30),
)


class track_external_call:
    """Context manager that records latency + outcome for outbound API calls.

    Usage:
        with track_external_call("jira"):
            resp = client.post(...)

    Outcome is "ok" by default, or "error" if the wrapped block raises.
    The wrapper never swallows exceptions and never raises on its own.
    """

    __slots__ = ("provider", "_start", "_outcome")

    def __init__(self, provider: str) -> None:
        self.provider = provider or "unknown"
        self._start = 0.0
        self._outcome = "ok"

    def __enter__(self) -> "track_external_call":
        import time as _t

        self._start = _t.perf_counter()
        return self

    def mark_outcome(self, outcome: str) -> None:
        """Override the recorded outcome (e.g. \"4xx\", \"5xx\", \"timeout\")."""
        self._outcome = outcome

    def __exit__(self, exc_type, exc, tb) -> None:
        import time as _t

        elapsed = _t.perf_counter() - self._start
        outcome = self._outcome if exc_type is None else "error"
        try:
            external_api_latency_seconds.labels(provider=self.provider).observe(elapsed)
            external_api_calls_total.labels(provider=self.provider, outcome=outcome).inc()
        except Exception:
            logger.debug("__exit__: fallo best-effort ignorado", exc_info=True)


def attach_apscheduler_metrics(scheduler) -> None:
    """Wire APScheduler events to record job duration + success/failure.

    Records to `contecflow_scheduled_job_duration_seconds{job_name,status}`.
    Safe to call even if scheduler is None (no-op).
    """
    if scheduler is None:
        return
    try:
        from apscheduler.events import (
            EVENT_JOB_ERROR,
            EVENT_JOB_EXECUTED,
            EVENT_JOB_SUBMITTED,
        )
    except Exception as exc:  # pragma: no cover
        logger.warning("APScheduler not available — metrics hook skipped: %s", exc)
        return

    import time as _t

    _starts: dict[str, float] = {}

    def _on_submitted(event) -> None:
        try:
            _starts[event.job_id] = _t.perf_counter()
        except Exception:
            logger.debug("_on_submitted: fallo best-effort ignorado", exc_info=True)

    def _on_finished(event) -> None:
        try:
            start = _starts.pop(event.job_id, None)
            if start is None:
                return
            elapsed = _t.perf_counter() - start
            status = "error" if getattr(event, "exception", None) else "ok"
            scheduled_job_duration_seconds.labels(
                job_name=event.job_id, status=status
            ).observe(elapsed)
        except Exception:
            logger.debug("_on_finished: fallo best-effort ignorado", exc_info=True)

    scheduler.add_listener(_on_submitted, EVENT_JOB_SUBMITTED)
    scheduler.add_listener(_on_finished, EVENT_JOB_EXECUTED | EVENT_JOB_ERROR)


def _ensure_multiproc_dir(path: Optional[str]) -> None:
    """Create the multiproc directory if configured, so worker processes can share state."""
    if not path:
        return
    try:
        Path(path).mkdir(parents=True, exist_ok=True)
        os.environ.setdefault("PROMETHEUS_MULTIPROC_DIR", path)
    except Exception as exc:  # pragma: no cover
        logger.warning("Could not create PROMETHEUS_MULTIPROC_DIR=%s: %s", path, exc)


def _multiproc_dir() -> Optional[str]:
    """El directorio multiproceso tal y como lo ve prometheus_client: del entorno."""
    return os.environ.get("PROMETHEUS_MULTIPROC_DIR") or None


def marcar_worker_terminado(pid: Optional[int] = None) -> None:
    """`mark_process_dead` para un worker de uvicorn (por defecto, este proceso).

    Segunda auditoría 2026-11: con `--workers N` cada worker deja en el
    directorio sus ficheros `gauge_live*_<pid>.db` (p. ej. las peticiones en
    curso del instrumentador, en modo `livesum`). Sin esta llamada, al terminar
    un worker su último valor se seguía sumando para siempre. El supervisor de
    uvicorn no ofrece ganchos (en la 0.54 reinicia el worker que muere, con
    otro PID, pero no avisa), así que lo hace el propio worker al cerrar su
    `lifespan`, con su `os.getpid()`. Best-effort: nunca impide el apagado.
    """
    directorio = _multiproc_dir()
    if not directorio:
        return
    try:
        from prometheus_client import multiprocess

        multiprocess.mark_process_dead(os.getpid() if pid is None else pid, directorio)
    except Exception:
        logger.warning("mark_process_dead falló (pid=%s)", pid, exc_info=True)


def _limpiar_workers_muertos(directorio: str) -> None:
    """Marca como muertos los workers que terminaron sin `lifespan` (SIGKILL, OOM).

    Esos no ejecutan `marcar_worker_terminado`; se detectan en cada scrape por
    su PID en los ficheros `gauge_live*_<pid>.db`. Solo en POSIX: en Windows
    `os.kill(pid, 0)` no comprueba, termina el proceso.
    """
    if os.name != "posix":
        return
    pids: set[int] = set()
    for fichero in Path(directorio).glob("gauge_live*_*.db"):
        try:
            pids.add(int(fichero.stem.rsplit("_", 1)[1]))
        except ValueError:
            continue
    for pid in pids - {os.getpid()}:
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            marcar_worker_terminado(pid)
        except PermissionError:
            continue  # existe, pero es de otro usuario


def _build_instrumentator():
    """Configure the FastAPI instrumentator with sensible defaults."""
    from prometheus_fastapi_instrumentator import Instrumentator, metrics

    # Paths that pollute metrics without value (health probes, static, docs JSON).
    excluded = (
        r"/metrics",
        r"/health",
        r"/ready",
        r"/favicon\.ico",
        r"/static.*",
        r"/api/v1/docs.*",
        r"/api/v1/redoc.*",
        r"/api/v1/openapi\.json",
    )

    inst = Instrumentator(
        should_group_status_codes=True,
        should_ignore_untemplated=True,
        should_respect_env_var=False,
        should_instrument_requests_inprogress=True,
        excluded_handlers=list(excluded),
        inprogress_name="contecflow_http_requests_inprogress",
        inprogress_labels=True,
    )

    # Default metrics: requests total + latency histogram + size.
    inst.add(metrics.default())
    inst.add(metrics.latency(buckets=(0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10)))
    inst.add(metrics.requests())
    return inst


def _install_metrics_route(app: FastAPI, env_auth_token: Optional[str]) -> None:
    """Register GET /metrics, with optional Bearer auth resolved per-request.

    The Bearer token is read from `app_settings` (key METRICS_AUTH_TOKEN) on
    every scrape so admins can rotate it via the UI without redeploy. Empty
    value in either DB or env disables auth.
    """
    from prometheus_client import (
        CONTENT_TYPE_LATEST,
        REGISTRY,
        generate_latest,
        multiprocess,
    )
    from starlette.responses import Response

    multiproc_dir = _multiproc_dir()

    def _current_token() -> Optional[str]:
        try:
            from app.db.session import SessionLocal
            from app.services.settings_service import get_runtime_str
            db = SessionLocal()
            from app.db.contexto_de_tenant import declarar_sistema as _declarar_sistema
            _declarar_sistema(db, "métricas: token global")  # auditoría 22-11-2026: TENANT_SESION_SIN_CONTEXTO=cerrar
            try:
                t = get_runtime_str(db, "METRICS_AUTH_TOKEN")
                return t if t else env_auth_token
            finally:
                db.close()
        except Exception:
            logger.debug("_current_token: excepcion ignorada", exc_info=True)
            return env_auth_token

    @app.get("/metrics", include_in_schema=False)
    def metrics_endpoint(request: Request) -> Response:
        import hmac
        from app.core.config import settings as _s

        active_token = _current_token()
        if active_token:
            header = request.headers.get("Authorization", "")
            if not header.startswith("Bearer ") or not hmac.compare_digest(header[7:], active_token):
                raise error_http(401, "token_no_valido", detail="Unauthorized")
        elif _s.ENVIRONMENT not in ("development", "test", "testing"):
            # Auditoria 2026-11: sin token, /metrics quedaba abierto en produccion
            # (rutas, volumen y errores de cada endpoint). Sin token, cerrado.
            raise error_http(401, "integracion_no_configurada", detail="METRICS_AUTH_TOKEN no configurado", nombre="Métricas")

        if multiproc_dir:
            _limpiar_workers_muertos(multiproc_dir)
            registry = CollectorRegistry()
            multiprocess.MultiProcessCollector(registry)
            # Las métricas de negocio no son de un proceso: las calcula, con caché,
            # el worker que atiende el scrape (app/core/metricas_negocio.py).
            if _s.METRICS_BUSINESS_ENABLED:
                from app.core.metricas_negocio import colector
                registry.register(colector())
            payload = generate_latest(registry)
        else:
            payload = generate_latest(REGISTRY)
        return Response(content=payload, media_type=CONTENT_TYPE_LATEST)


_colector_registrado = False


def _registrar_colector_de_negocio() -> None:
    """En modo de un proceso, el colector va al registro global (una vez)."""
    global _colector_registrado
    if _colector_registrado:
        return
    try:
        from prometheus_client import REGISTRY
        from app.core.metricas_negocio import colector
        REGISTRY.register(colector())
        _colector_registrado = True
    except Exception:
        logger.warning("No se pudo registrar el colector de métricas de negocio", exc_info=True)


def setup_metrics(app: FastAPI) -> bool:
    """Initialize Prometheus instrumentation on the given FastAPI app.

    Returns True if metrics were activated, False otherwise.
    """
    from app.core.config import settings

    if not settings.METRICS_ENABLED:
        logger.info("Metrics disabled (METRICS_ENABLED=0)")
        return False

    _ensure_multiproc_dir(settings.METRICS_MULTIPROC_DIR)

    try:
        inst = _build_instrumentator()
        inst.instrument(app)
    except Exception as exc:  # pragma: no cover
        logger.error("Prometheus instrumentation failed: %s", exc, exc_info=True)
        return False

    _install_metrics_route(app, settings.METRICS_AUTH_TOKEN)

    # Observabilidad por empresa (22-11-2026, docs/OBSERVABILIDAD.md): peticiones,
    # latencia y errores por empresa (etiqueta acotada), y métricas de negocio
    # leídas de la base con caché.
    try:
        from app.core.metricas_empresa import MetricasPorEmpresaMiddleware
        app.add_middleware(MetricasPorEmpresaMiddleware)
    except Exception:
        logger.warning("No se pudo instalar el middleware de métricas por empresa", exc_info=True)
    if settings.METRICS_BUSINESS_ENABLED and not _multiproc_dir():
        _registrar_colector_de_negocio()

    try:
        app_info.labels(
            version=settings.VERSION,
            environment=settings.ENVIRONMENT,
        ).set(1)
    except Exception:
        logger.debug("setup_metrics: fallo best-effort ignorado", exc_info=True)

    auth_state = "with Bearer auth" if settings.METRICS_AUTH_TOKEN else "unauthenticated"
    logger.info("✅ Prometheus metrics activos en /metrics (%s)", auth_state)
    return True


__all__ = [
    "setup_metrics",
    "marcar_worker_terminado",
    "track_external_call",
    "attach_apscheduler_metrics",
    "app_info",
    "business_event_total",
    "tickets_created_total",
    "invoices_created_total",
    "scheduled_job_duration_seconds",
    "abac_denials_total",
    "external_api_calls_total",
    "external_api_latency_seconds",
]
