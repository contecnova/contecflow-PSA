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

from fastapi import FastAPI, HTTPException, Request

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
            pass


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
            pass

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
            pass

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

    multiproc_dir = os.environ.get("PROMETHEUS_MULTIPROC_DIR")

    def _current_token() -> Optional[str]:
        try:
            from app.db.session import SessionLocal
            from app.services.settings_service import get_runtime_str
            db = SessionLocal()
            try:
                t = get_runtime_str(db, "METRICS_AUTH_TOKEN")
                return t if t else env_auth_token
            finally:
                db.close()
        except Exception:
            return env_auth_token

    @app.get("/metrics", include_in_schema=False)
    def metrics_endpoint(request: Request) -> Response:
        active_token = _current_token()
        if active_token:
            header = request.headers.get("Authorization", "")
            if not header.startswith("Bearer ") or header[7:] != active_token:
                raise HTTPException(status_code=401, detail="Unauthorized")

        if multiproc_dir:
            registry = CollectorRegistry()
            multiprocess.MultiProcessCollector(registry)
            payload = generate_latest(registry)
        else:
            payload = generate_latest(REGISTRY)
        return Response(content=payload, media_type=CONTENT_TYPE_LATEST)


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

    try:
        app_info.labels(
            version=settings.VERSION,
            environment=settings.ENVIRONMENT,
        ).set(1)
    except Exception:
        pass

    auth_state = "with Bearer auth" if settings.METRICS_AUTH_TOKEN else "unauthenticated"
    logger.info("✅ Prometheus metrics activos en /metrics (%s)", auth_state)
    return True


__all__ = [
    "setup_metrics",
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
