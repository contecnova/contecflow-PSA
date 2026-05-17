from fastapi import FastAPI, Request, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.responses import HTMLResponse, Response
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import logging
import os
import time
from pathlib import Path
from urllib.parse import unquote
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.pool import NullPool
from app.core.config import settings
from app.core.error_sanitizer import sanitize_http_detail

# ── Logging rico ──────────────────────────────────────────────────────────────
_log_level_name = (settings.LOG_LEVEL or "INFO").upper()
_log_level = getattr(logging, _log_level_name, logging.INFO)
logging.basicConfig(
    level=_log_level,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
    force=True,
)
logger = logging.getLogger("contecflow")
logging.getLogger().setLevel(_log_level)
logging.getLogger("contecflow").setLevel(_log_level)
logging.getLogger("uvicorn").setLevel(_log_level)
logging.getLogger("uvicorn.error").setLevel(_log_level)

# Silenciar uvicorn access log estándar (lo reemplazamos con el nuestro)
logging.getLogger("uvicorn.access").setLevel(logging.WARNING)

from app.api.v1.router import api_router
from app.api.v2.router import api_v2_router


def _read_alembic_revisions(database_url: str) -> set[str] | None:
    """Read current Alembic revision set from DB without mutating schema."""
    is_sqlite = database_url.startswith("sqlite")
    retries = 3 if is_sqlite else 1
    last_exc: Exception | None = None

    for attempt in range(1, retries + 1):
        engine = create_engine(database_url, poolclass=NullPool)
        try:
            inspector = inspect(engine)
            if not inspector.has_table("alembic_version"):
                return None
            with engine.connect() as conn:
                rows = conn.execute(text("SELECT version_num FROM alembic_version")).fetchall()
                revisions = {str(row[0]) for row in rows if row and row[0]}
                return revisions or None
        except OperationalError as exc:
            last_exc = exc
            msg = str(exc).lower()
            transient_sqlite_error = "disk i/o error" in msg or "database is locked" in msg
            if is_sqlite and transient_sqlite_error and attempt < retries:
                logger.warning(
                    "⚠️  SQLite preflight transient error (attempt %s/%s): %s",
                    attempt,
                    retries,
                    exc,
                )
                time.sleep(0.25 * attempt)
                continue
            raise
        finally:
            engine.dispose()

    if last_exc is not None:
        raise RuntimeError(f"Unable to read alembic revisions: {last_exc}")
    return None


def _read_alembic_heads() -> set[str] | None:
    """Read Alembic script heads from local migration repository."""
    try:
        from alembic.config import Config
        from alembic.script import ScriptDirectory

        cfg = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
        script = ScriptDirectory.from_config(cfg)
        heads = set(script.get_heads())
        return heads or None
    except Exception:
        return None


def _scheduler_flags() -> tuple[bool, bool]:
    """Return scheduler enablement flags from environment variables."""
    enable_apscheduler = os.getenv("ENABLE_APSCHEDULER", "1") == "1"
    celery_beat_enabled = (
        os.getenv("ENABLE_CELERY_BEAT", "0") == "1"
        or os.getenv("CELERY_BEAT", "0") == "1"
    )
    return enable_apscheduler, celery_beat_enabled


def _scheduler_mode() -> str:
    """Resolve active scheduler mode for observability and readiness checks."""
    enable_apscheduler, celery_beat_enabled = _scheduler_flags()
    if enable_apscheduler and celery_beat_enabled:
        return "dual"
    if enable_apscheduler:
        return "apscheduler"
    if celery_beat_enabled:
        return "celery_beat"
    return "none"


def _enforce_scheduler_mode_safety() -> None:
    """Prevent unsafe dual scheduling in ALL environments unless explicitly overridden.

    In production/staging the default is to fail immediately.  In development the
    default is also to fail so that dual-scheduler bugs are caught early; the check
    can be bypassed by setting FAIL_ON_DUAL_SCHEDULER=0 explicitly.
    """
    if _scheduler_mode() != "dual":
        return
    # Default to fail in every environment — dev included.
    fail_on_dual = os.getenv("FAIL_ON_DUAL_SCHEDULER", "1") == "1"
    if fail_on_dual:
        raise RuntimeError(
            "Dual scheduler mode detected (APScheduler + Celery Beat). "
            "Disable one scheduler (ENABLE_APSCHEDULER=0 or ENABLE_CELERY_BEAT=0). "
            f"[env={settings.ENVIRONMENT}]"
        )


# ── Sentry (P1-3) ─────────────────────────────────────────────────────────────
if settings.SENTRY_DSN:
    import sentry_sdk
    from sentry_sdk.integrations.fastapi import FastApiIntegration
    from sentry_sdk.integrations.sqlalchemy import SqlalchemyIntegration
    sentry_sdk.init(
        dsn=settings.SENTRY_DSN,
        environment=settings.SENTRY_ENVIRONMENT,
        integrations=[FastApiIntegration(), SqlalchemyIntegration()],
        traces_sample_rate=0.1,
        profiles_sample_rate=0.05,
        send_default_pii=False,
    )
    logger.info(f"✅ Sentry inicializado (env={settings.SENTRY_ENVIRONMENT})")


# ── OpenTelemetry distributed tracing (optional) ──────────────────────────────
if settings.OTEL_ENABLED and settings.OTEL_EXPORTER_OTLP_ENDPOINT:
    try:
        from opentelemetry import trace
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
        from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor

        resource = Resource.create({"service.name": settings.OTEL_SERVICE_NAME})
        provider = TracerProvider(resource=resource)
        exporter = OTLPSpanExporter(
            endpoint=settings.OTEL_EXPORTER_OTLP_ENDPOINT,
            headers=settings.OTEL_EXPORTER_OTLP_HEADERS,
        )
        provider.add_span_processor(BatchSpanProcessor(exporter))
        trace.set_tracer_provider(provider)

        _OTEL_READY = True
    except Exception as exc:  # pragma: no cover
        _OTEL_READY = False
        logger.warning("⚠️ OpenTelemetry no inicializado: %s", exc)
else:
    _OTEL_READY = False


# ── Rate Limiter (P0-1) ────────────────────────────────────────────────────────
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from app.core.ratelimit import limiter


@asynccontextmanager
async def lifespan(_app: FastAPI):
    # ── Dependency preflight check ─────────────────────────────────────────
    _missing_deps: list[str] = []
    for _dep in ("qrcode", "pyotp", "PIL"):
        try:
            __import__(_dep)
        except ImportError:
            _missing_deps.append(_dep)
    if _missing_deps:
        logger.warning(
            "⚠️  MFA dependencies missing — MFA setup will return HTTP 500: %s. "
            "Run: pip install qrcode[pil] pyotp",
            ", ".join(_missing_deps),
        )

    logger.info("━" * 54)
    logger.info("  ◈  CONTECFLOW PSA — Iniciando servidor")
    logger.info(f"     Versión : {settings.VERSION}")
    logger.info(f"     API Base: {settings.API_V1_STR}")
    logger.info(f"     BD      : {settings.DATABASE_URL.split('/')[-1]}")
    logger.info("━" * 54)

    # ── Schema preflight (no in-process migrations) ──────────────────────────
    # Migrations must run outside application startup (CI/CD, init-container, or
    # explicit operator action). Startup only checks for obvious schema drift.
    import os as _os
    _is_testing = _os.getenv("TESTING", "0") == "1"
    _expected_rev = (_os.getenv("EXPECTED_ALEMBIC_REVISION") or "").strip() or None
    _enforce_drift = _os.getenv("FAIL_ON_SCHEMA_DRIFT", "1" if settings.ENVIRONMENT in {"production", "staging"} else "0") == "1"

    if _is_testing:
        logger.info("⏭️  Schema preflight omitido en testing")
    else:
        try:
            _current_revs = _read_alembic_revisions(settings.DATABASE_URL)
            _heads = _read_alembic_heads()

            if _current_revs is None:
                _msg = (
                    "No existe tabla alembic_version. Ejecuta migraciones fuera del startup "
                    "(p.ej. `python -m alembic upgrade heads`) antes de arrancar."
                )
                if _enforce_drift:
                    raise RuntimeError(_msg)
                logger.warning("⚠️  %s", _msg)
            elif _expected_rev and _expected_rev not in _current_revs:
                _msg = (
                    f"Schema drift detectado: expected={_expected_rev} current={sorted(_current_revs)}. "
                    "Aplica migraciones fuera del proceso web."
                )
                if _enforce_drift:
                    raise RuntimeError(_msg)
                logger.warning("⚠️  %s", _msg)
            elif _heads and _current_revs != _heads:
                _missing = sorted(_heads - _current_revs)
                _extra = sorted(_current_revs - _heads)
                _msg = (
                    "Schema drift detectado entre revisiones aplicadas y heads de Alembic: "
                    f"current={sorted(_current_revs)} heads={sorted(_heads)} "
                    f"missing={_missing} extra={_extra}. "
                    "Aplica migraciones fuera del proceso web (p.ej. `python -m alembic upgrade heads`)."
                )
                if _enforce_drift:
                    raise RuntimeError(_msg)
                logger.warning("⚠️  %s", _msg)
            else:
                logger.info("✅ Schema preflight OK (alembic_revisions=%s)", sorted(_current_revs))
        except Exception as _schema_exc:
            logger.error("❌ Schema preflight failed: %s", _schema_exc)
            raise

    # Key management bootstrap (JWT keyring + integration secret rotation policy)
    try:
        from app.services.key_management import refresh_caches, rotate_due_materials
        rotate_due_materials()
        refresh_caches()
        logger.info("🔐 Key management inicializado")
    except Exception as _ke:
        logger.error(f"❌ Key management init failed: {_ke}", exc_info=True)
        if settings.ENVIRONMENT == "production":
            raise

    # Cross-worker settings cache invalidation (Redis pub/sub).
    # No-op if REDIS_URL is unset.
    try:
        from app.core.settings_pubsub import start_subscriber as _start_settings_sub
        if _start_settings_sub():
            logger.info("📡 Settings pub/sub subscriber iniciado")
    except Exception as _pse:
        logger.warning("⚠️  Settings pub/sub no inicializado: %s", _pse)

    # Scheduler (optional): keep disabled when Celery beat is active in deployment.
    _scheduler = None
    _enable_apscheduler, _celery_beat_enabled = _scheduler_flags()
    try:
        _enforce_scheduler_mode_safety()
    except RuntimeError as _sched_exc:
        logger.error("❌ Scheduler safety check failed: %s", _sched_exc)
        raise
    if _enable_apscheduler:
        logger.info("⏰ Iniciando scheduler de informes...")
        try:
            from apscheduler.schedulers.background import BackgroundScheduler
            from apscheduler.triggers.cron import CronTrigger
            from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
            from app.services.scheduled_reports import run_due_reports
            from app.services.key_management import run_scheduled_rotation

            # Use a SQLAlchemy job store so that in multi-worker deployments only
            # one worker executes each job (the others see it already locked/run).
            jobstores = {
                "default": SQLAlchemyJobStore(url=settings.DATABASE_URL)
            }
            _scheduler = BackgroundScheduler(
                jobstores=jobstores,
                timezone=settings.DEFAULT_TIMEZONE,
            )
            _scheduler.add_job(
                run_due_reports,
                CronTrigger(minute=0),
                id="scheduled_reports",
                replace_existing=True,
                misfire_grace_time=300,
                coalesce=True,
            )
            _scheduler.add_job(
                run_scheduled_rotation,
                CronTrigger(hour=settings.KEY_ROTATION_RUN_HOUR_UTC, minute=17),
                id="scheduled_key_rotation",
                replace_existing=True,
                misfire_grace_time=900,
                coalesce=True,
            )
            _scheduler.add_job(
                "app.services.alert_jobs:run_alert_engine_job",
                CronTrigger(hour=8, minute=0),
                id="scheduled_alert_engine",
                replace_existing=True,
                misfire_grace_time=900,
                coalesce=True,
            )
            _scheduler.add_job(
                "app.services.perf_reminder_service:run_perf_reminders_job",
                CronTrigger(hour=9, minute=0),
                id="scheduled_perf_reminders",
                replace_existing=True,
                misfire_grace_time=900,
                coalesce=True,
            )
            try:
                from app.core.metrics import attach_apscheduler_metrics
                attach_apscheduler_metrics(_scheduler)
            except Exception as _metrics_exc:
                logger.warning("APScheduler metrics hook not attached: %s", _metrics_exc)
            _scheduler.start()
            logger.info("   ✅ Scheduler activo (informes + rotación + alertas + recordatorios perf)")
            logger.info("✅ Modo scheduler: APScheduler")
        except Exception as e:
            logger.warning(f"   ⚠️  Scheduler no iniciado: {e}")
    elif _celery_beat_enabled:
        logger.info("✅ Modo scheduler: Celery Beat")
    else:
        logger.info("✅ Modo scheduler: Ninguno (modo manual)")
        logger.info("⏭️  APScheduler deshabilitado (ENABLE_APSCHEDULER=0)")

    # Contar endpoints registrados
    total_routes = len([r for r in _app.routes if hasattr(r, 'methods')])
    logger.info("━" * 54)
    logger.info(f"🚀 Contecflow PSA listo — {total_routes} endpoints")
    logger.info(f"   📖 Docs: {settings.BACKEND_URL}{settings.API_V1_STR}/docs")
    logger.info(f"   🔍 Health: {settings.BACKEND_URL}/health")
    logger.info("━" * 54)

    # Collaboration: scheduled message dispatcher
    if not _is_testing:
        try:
            from app.services.collaboration._scheduler import start as _collab_start
            _collab_start()
        except Exception as _exc:
            logger.warning("Collab scheduler no inicializado: %s", _exc)

    yield

    try:
        from app.services.collaboration._scheduler import stop as _collab_stop
        _collab_stop()
    except Exception:
        pass

    logger.info("🛑 Apagando Contecflow PSA...")
    try:
        from app.core.settings_pubsub import stop_subscriber as _stop_settings_sub
        _stop_settings_sub()
    except Exception:
        pass
    if _scheduler:
        try:
            if _scheduler.running:
                _scheduler.shutdown(wait=False)
            else:
                logger.info("   ⏭️  Scheduler ya detenido; se omite shutdown")
        except Exception as e:
            logger.warning(f"Scheduler shutdown error: {e}")
    logger.info("   ✅ Shutdown completo")



# ── Middleware global de manejo de errores ─────────────────────────────
import uuid as _uuid
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

class ExceptionHandlerMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        try:
            return await call_next(request)
        except Exception:
            req_id = str(_uuid.uuid4())
            logger.error("❌ Unhandled exception [req_id=%s]", req_id, exc_info=True)
            return JSONResponse(
                status_code=500,
                content={
                    "detail": "Internal Server Error",
                    "request_id": req_id,
                },
            )

app = FastAPI(
    title=settings.PROJECT_NAME,
    redirect_slashes=False,
    version=settings.VERSION,
    openapi_url=f"{settings.API_V1_STR}/openapi.json",
    docs_url=f"{settings.API_V1_STR}/docs",
    redoc_url=f"{settings.API_V1_STR}/redoc",
    lifespan=lifespan,
)

if _OTEL_READY:
    try:
        FastAPIInstrumentor.instrument_app(app)
        SQLAlchemyInstrumentor().instrument()
        logger.info("✅ OpenTelemetry tracing activo")
    except Exception as exc:  # pragma: no cover
        logger.warning("⚠️ Error activando instrumentación OpenTelemetry: %s", exc)

# Registrar el middleware global de excepciones
app.add_middleware(ExceptionHandlerMiddleware)

# Rate limiter state + 429 handler
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)


@app.exception_handler(HTTPException)
async def http_exception_sanitizer(_request: Request, exc: HTTPException):
    safe_detail = sanitize_http_detail(exc.status_code, exc.detail)
    if safe_detail != exc.detail:
        logger.warning("Sanitized HTTPException detail (status=%s)", exc.status_code)
    return JSONResponse(status_code=exc.status_code, content={"detail": safe_detail})


@app.exception_handler(RequestValidationError)
async def validation_exception_sanitizer(_request: Request, exc: RequestValidationError):
    # Keep standard validation structure; sanitize only if it unexpectedly contains a string payload.
    safe_detail = sanitize_http_detail(422, exc.errors())
    return JSONResponse(status_code=422, content={"detail": safe_detail})

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization", "X-Request-ID", "X-Requested-With"],
)

# ABAC middleware — opt-in route-level ABAC enforcement via ABAC_ROUTE_REGISTRY.
# Must be added AFTER the auth middleware so request.state.user is populated.
from app.core.abac_middleware import ABACMiddleware
app.add_middleware(ABACMiddleware)

@app.middleware("http")
async def security_headers_middleware(request: Request, call_next):
    response = await call_next(request)
    path = request.url.path
    docs_base = settings.API_V1_STR
    is_docs_route = (
        path.startswith(f"{docs_base}/docs")
        or path.startswith(f"{docs_base}/redoc")
        or path.startswith(f"{docs_base}/openapi.json")
        or path.startswith("/docs/oauth2-redirect")
    )

    # --- API version header logic ---
    # En producción solo se expone el número major (v1/v2) sin patch — no se
    # revela el SemVer exacto para no facilitar el fingerprinting de versiones.
    if path.startswith(settings.API_V2_STR):
        response.headers["x-api-version"] = "2"
    elif path.startswith(settings.API_V1_STR):
        response.headers["x-api-version"] = "1"
        # Si v2 está montada, marcamos v1 como deprecated
        response.headers["x-api-deprecated"] = "true"
        response.headers["deprecation"] = "true"

    response.headers["X-Content-Type-Options"] = "nosniff"
    # Document file/preview endpoints need to render inside the SPA's iframe (same origin).
    # Everything else stays DENY for click-jacking protection.
    is_doc_file_route = (
        path.startswith(f"{docs_base}/documents/file/")
        or (path.startswith(f"{docs_base}/documents/") and path.endswith("/preview"))
    )
    response.headers["X-Frame-Options"] = "SAMEORIGIN" if is_doc_file_route else "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    if settings.ENVIRONMENT == "production":
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains; preload"
    # Permissions-Policy: el voice modal (Item I25) necesita el micrófono en
    # same-origin para grabar comandos. Cámara y geo siguen denegadas.
    response.headers["Permissions-Policy"] = "camera=(), microphone=(self), geolocation=()"
    # Cross-Origin isolation hardening (Spectre / side-channel mitigation).
    # COOP same-origin evita que ventanas abiertas con window.open compartan
    # browsing context con el origen actual. CORP same-origin restringe los
    # subresources a same-origin (los docs preview son same-origin igual).
    response.headers["Cross-Origin-Opener-Policy"] = "same-origin"
    response.headers["Cross-Origin-Resource-Policy"] = "same-origin"
    # Legacy Flash/PDF cross-domain policy: ningún dominio puede leerlo.
    response.headers["X-Permitted-Cross-Domain-Policies"] = "none"
    if is_docs_route:
        # Swagger/ReDoc HTML uses CDN assets and an inline bootstrap script.
        response.headers["Content-Security-Policy"] = (
            "default-src 'self' https://cdn.jsdelivr.net https://fastapi.tiangolo.com; "
            "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
            "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://fonts.googleapis.com; "
            "img-src 'self' data: blob: https://fastapi.tiangolo.com; "
            "media-src 'self' blob:; "
            "font-src 'self' data: https://fonts.gstatic.com; "
            "connect-src 'self' ws: wss:; "
            "frame-ancestors 'none'; "
            "object-src 'none'; "
            "base-uri 'self';"
        )
    else:
        # Content-Security-Policy: the Vite production build emits a single
        # bundled script — no unsafe-inline or unsafe-eval needed for scripts.
        # Inline styles are still needed for dynamic CSS-in-JS (e.g. Tailwind).
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "script-src 'self'; "
            "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
            "img-src 'self' data: blob:; "
            # Item I25: media-src blob: necesario para preview de audio
            # grabado con MediaRecorder en el voice command modal.
            "media-src 'self' blob:; "
            "font-src 'self' data: https://fonts.gstatic.com; "
            "connect-src 'self' ws: wss:; "
            "frame-ancestors 'none'; "
            "object-src 'none'; "
            "base-uri 'self';"
        )
    return response

app.include_router(api_router, prefix=settings.API_V1_STR)
app.include_router(api_v2_router, prefix=settings.API_V2_STR)

# ── Prometheus metrics (opt-in via METRICS_ENABLED) ────────────────────────
# Registers RED HTTP metrics + exposes /metrics. Must run after routers are
# included so the instrumentator can introspect templated paths.
from app.core.metrics import setup_metrics
setup_metrics(app)


@app.get("/status", response_class=HTMLResponse)
def public_status_page():
        """Public status page without authentication."""
        api_path = f"{settings.API_V1_STR}/sd/status-page"
        return f"""
<!doctype html>
<html lang=\"en\">
<head>
    <meta charset=\"utf-8\" />
    <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
    <title>Status</title>
    <style>
        :root {{ --bg:#0f172a; --card:#111827; --line:#24324a; --txt:#e5e7eb; --muted:#93a3b8; --ok:#22c55e; --warn:#f59e0b; --bad:#ef4444; --maint:#6366f1; }}
        body {{ margin:0; background:radial-gradient(circle at top,#13213d 0%,#0b1220 55%,#060b14 100%); color:var(--txt); font:14px/1.5 ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, Ubuntu; }}
        .wrap {{ max-width:980px; margin:0 auto; padding:32px 20px 40px; }}
        .head {{ display:flex; justify-content:space-between; align-items:center; gap:12px; margin-bottom:20px; }}
        .title {{ font-size:30px; font-weight:800; letter-spacing:.3px; }}
        .badge {{ padding:6px 12px; border-radius:999px; border:1px solid var(--line); background:#0b1324; font-size:12px; }}
        .group {{ margin-top:20px; border:1px solid var(--line); border-radius:14px; overflow:hidden; background:rgba(17,24,39,.75); backdrop-filter: blur(4px); }}
        .group h2 {{ margin:0; padding:12px 16px; font-size:13px; text-transform:uppercase; letter-spacing:.08em; color:var(--muted); border-bottom:1px solid var(--line); }}
        .row {{ display:flex; justify-content:space-between; gap:10px; padding:12px 16px; border-bottom:1px solid #1b2940; }}
        .row:last-child {{ border-bottom:0; }}
        .name {{ font-weight:700; }}
        .desc {{ color:var(--muted); font-size:12px; margin-top:2px; }}
        .status {{ font-weight:700; font-size:12px; text-transform:uppercase; }}
        .operational {{ color:var(--ok); }} .degraded_performance {{ color:var(--warn); }} .partial_outage,.major_outage {{ color:var(--bad); }} .maintenance {{ color:var(--maint); }}
        .foot {{ margin-top:14px; color:var(--muted); font-size:12px; }}
        .err {{ border:1px solid #7f1d1d; color:#fecaca; background:rgba(127,29,29,.25); border-radius:10px; padding:10px 12px; }}
    </style>
</head>
<body>
    <div class=\"wrap\">
        <div class=\"head\">
            <div class=\"title\">Service Status</div>
            <div id=\"overall\" class=\"badge\">Loading...</div>
        </div>
        <div id=\"content\"></div>
        <div id=\"foot\" class=\"foot\"></div>
    </div>
    <script>
        const api = {api_path!r};
        const $content = document.getElementById('content');
        const $overall = document.getElementById('overall');
        const $foot = document.getElementById('foot');

        function label(s) {{ return String(s || '').replaceAll('_',' '); }}
        function esc(v) {{ return String(v ?? '').replace(/[&<>\"']/g, m => ({{'&':'&amp;','<':'&lt;','>':'&gt;','\"':'&quot;',"'":'&#39;'}})[m]); }}

        fetch(api)
            .then(r => r.ok ? r.json() : Promise.reject(new Error('HTTP ' + r.status)))
            .then(data => {{
                $overall.className = 'badge ' + data.overall_status;
                $overall.textContent = 'Overall: ' + label(data.overall_status);
                const groups = data.groups || {{}};
                const html = Object.keys(groups).map(g => `
                    <section class=\"group\">
                        <h2>${{esc(g)}}</h2>
                        ${{groups[g].map(c => `
                            <div class=\"row\">
                                <div>
                                    <div class=\"name\">${{esc(c.name)}}</div>
                                    <div class=\"desc\">${{esc(c.description || '')}}</div>
                                </div>
                                <div class=\"status ${{esc(c.status)}}\">${{esc(label(c.status))}}</div>
                            </div>`).join('')}}
                    </section>`).join('');
                $content.innerHTML = html || '<div class=\"err\">No public components configured.</div>';
                $foot.textContent = data.generated_at ? 'Updated: ' + new Date(data.generated_at).toLocaleString() : '';
            }})
            .catch(err => {{
                $content.innerHTML = '<div class=\"err\">Could not load status page: ' + esc(err.message) + '</div>';
                $overall.textContent = 'Unavailable';
            }});
    </script>
</body>
</html>
"""


@app.get("/status/embed.js")
def status_embed_js():
        """Embeddable status widget script for customer websites."""
        js = f"""
(function() {{
    var script = document.currentScript;
    var apiBase = (script && script.getAttribute('data-api-base')) || window.location.origin + '{settings.API_V1_STR}';
    var targetSel = (script && script.getAttribute('data-target')) || null;
    var target = targetSel ? document.querySelector(targetSel) : null;
    if (!target) {{
        target = document.createElement('div');
        script.parentNode.insertBefore(target, script.nextSibling);
    }}
    target.style.fontFamily = "ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto";
    target.style.border = "1px solid #d1d5db";
    target.style.borderRadius = "10px";
    target.style.padding = "12px";
    target.style.maxWidth = "420px";
    target.innerHTML = "<div style='font-weight:700;margin-bottom:6px'>Service Status</div><div style='font-size:12px;color:#6b7280'>Loading...</div>";

    fetch(apiBase + '/sd/status-page')
        .then(function(r) {{ return r.json(); }})
        .then(function(data) {{
            var groups = data.groups || {{}};
            var rows = [];
            Object.keys(groups).forEach(function(g) {{
                groups[g].forEach(function(c) {{
                    rows.push("<div style='display:flex;justify-content:space-between;gap:8px;padding:6px 0;border-top:1px solid #eef2f7'><span>" +
                                        c.name + "</span><strong style='text-transform:uppercase;font-size:11px'>" +
                                        String(c.status || '').replaceAll('_',' ') + "</strong></div>");
                }});
            }});
            target.innerHTML = "<div style='font-weight:700;margin-bottom:8px'>Service Status</div>" +
                "<div style='font-size:12px;color:#4b5563;margin-bottom:8px'>Overall: <strong style='text-transform:uppercase'>" +
                String(data.overall_status || 'unknown').replaceAll('_',' ') + "</strong></div>" + rows.join('');
        }})
        .catch(function() {{
            target.innerHTML = "<div style='color:#b91c1c;font-size:12px'>Status unavailable</div>";
        }});
}})();
"""
        return Response(content=js, media_type="application/javascript")


@app.get("/widget/ticket.js")
def ticket_widget_js():
        """Embeddable ticket creation widget for client portal tokens."""
        js = f"""
(function() {{
    var s = document.currentScript;
    var token = s && s.getAttribute('data-client-token');
    var apiBase = (s && s.getAttribute('data-api-base')) || window.location.origin + '{settings.API_V1_STR}';
    if (!token) {{ console.error('Contecflow widget: data-client-token is required'); return; }}

    var btn = document.createElement('button');
    btn.textContent = 'Abrir soporte';
    btn.style.cssText = 'position:fixed;right:18px;bottom:18px;z-index:99999;background:#0ea5e9;color:#fff;border:0;border-radius:999px;padding:11px 16px;font:600 13px ui-sans-serif,system-ui;cursor:pointer;box-shadow:0 10px 25px rgba(2,132,199,.35)';
    var panel = document.createElement('div');
    panel.style.cssText = 'position:fixed;right:18px;bottom:68px;width:340px;max-width:calc(100vw - 24px);background:#fff;border:1px solid #d1d5db;border-radius:12px;z-index:99999;padding:12px;display:none;font:13px ui-sans-serif,system-ui;box-shadow:0 18px 40px rgba(0,0,0,.2)';
    panel.innerHTML = "<div style='font-weight:700;margin-bottom:8px'>Nuevo ticket</div>" +
        "<input id='cw-title' placeholder='Asunto' style='width:100%;box-sizing:border-box;padding:8px;border:1px solid #d1d5db;border-radius:8px;margin-bottom:8px'/>" +
        "<textarea id='cw-body' rows='4' placeholder='Describe el problema' style='width:100%;box-sizing:border-box;padding:8px;border:1px solid #d1d5db;border-radius:8px;margin-bottom:8px'></textarea>" +
        "<div style='display:flex;gap:8px'><button id='cw-send' style='flex:1;padding:8px;border:0;border-radius:8px;background:#0ea5e9;color:#fff;cursor:pointer'>Enviar</button><button id='cw-close' style='padding:8px 10px;border:1px solid #d1d5db;background:#fff;border-radius:8px;cursor:pointer'>Cerrar</button></div>" +
        "<div id='cw-msg' style='font-size:12px;color:#6b7280;margin-top:8px'></div>";

    document.body.appendChild(btn);
    document.body.appendChild(panel);
    btn.onclick = function() {{ panel.style.display = panel.style.display === 'none' ? 'block' : 'none'; }};
    panel.querySelector('#cw-close').onclick = function() {{ panel.style.display = 'none'; }};
    panel.querySelector('#cw-send').onclick = function() {{
        var title = panel.querySelector('#cw-title').value.trim();
        var body = panel.querySelector('#cw-body').value.trim();
        var msg = panel.querySelector('#cw-msg');
        if (!title || !body) {{ msg.textContent = 'Completa asunto y descripción.'; return; }}
        msg.textContent = 'Enviando...';
        fetch(apiBase + '/sd/tickets/client', {{
            method: 'POST',
            headers: {{ 'Content-Type': 'application/json', 'Authorization': 'Bearer ' + token }},
            body: JSON.stringify({{ title: title, description: body, ticket_type: 'incident' }})
        }})
        .then(function(r) {{ return r.json().then(function(d) {{ return {{ ok:r.ok, data:d }}; }}); }})
        .then(function(res) {{
            if (!res.ok) throw new Error(res.data && (res.data.detail || res.data.message) || 'Error');
            msg.textContent = 'Ticket creado: ' + (res.data.number || res.data.id);
            panel.querySelector('#cw-title').value = '';
            panel.querySelector('#cw-body').value = '';
        }})
        .catch(function(e) {{ msg.textContent = 'No se pudo crear el ticket: ' + e.message; }});
    }};
}})();
"""
        return Response(content=js, media_type="application/javascript")



# ── Middleware de logging de peticiones ───────────────────────────────────────
@app.middleware("http")
async def request_logger(request: Request, call_next):
    start = time.time()
    response = await call_next(request)
    duration = round((time.time() - start) * 1000)

    path   = request.url.path
    method = request.method
    status = response.status_code

    # Ignorar rutas de health, métricas y assets estáticos
    if path in ("/health", "/ready", "/metrics", "/favicon.ico") or path.startswith("/static"):
        return response

    # Color según status
    # Some 401s are expected and short-lived in normal UX:
    # - startup session probe (/auth/me)
    # - concurrent queries while interceptor refreshes expired access cookie
    # - activity/imputations/settings queries during token rotation or early app startup
    _expected_401_paths = {
        "/api/v1/auth/me",
        "/api/v1/users/me/preferences",
        "/api/v1/alerts",
        "/api/v1/approvals/requests/pending-my-action",
        "/api/v1/activity/mentions/my",
        "/api/v1/imputations/timer/current",
        "/api/v1/settings/log-level",
        "/api/v1/sd/auto-resolution/stats",
        "/api/v1/sd/auto-resolution/config",
    }
    _expected_401 = (status == 401 and path in _expected_401_paths)
    if status < 300:
        level = logging.INFO
        icon  = "✅"
    elif status < 400:
        level = logging.INFO
        icon  = "↩️ "
    elif _expected_401:
        level = logging.INFO
        icon  = "🔑"
    elif status < 500:
        level = logging.WARNING
        icon  = "⚠️ "
    else:
        level = logging.ERROR
        icon  = "❌"

    # Loguear usuario si hay Authorization
    user_hint = ""
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        try:
            from app.core.security import decode_token
            payload = decode_token(auth[7:])
            if payload:
                user_hint = f" | user:{payload.get('sub','?')[:8]}"
        except Exception as e:
            logger.debug("JWT decode failed in request logging: %s", e)

    logger.log(level, f"{icon} {method:6} {path:<45} {status} [{duration}ms]{user_hint}")

    # Log extra en errores 4xx/5xx (redact token-like params to avoid leakage)
    if status >= 400:
        import re as _re
        safe_url = str(request.url)
        for _k in ("token", "access_token", "refresh_token", "code", "state", "id_token"):
            safe_url = _re.sub(rf"(?<=[?&]){_k}=[^&]*", f"{_k}=[REDACTED]", safe_url)
        logger.log(level, f"   └─ {method} {safe_url}")

    return response


@app.get("/health", tags=["Health"])
def health():
    from app.db.session import engine
    from sqlalchemy import text
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        db_status = "ok"
    except Exception as e:
        db_status = f"error: {e}"
    return {
        "status": "ok",
        "version": settings.VERSION,
        "project": settings.PROJECT_NAME,
        "db": db_status,
    }


@app.get("/ready", tags=["Health"])
def readiness():
    """Readiness probe with orchestration dependencies visibility."""
    from app.db.session import engine
    from sqlalchemy import text

    checks: dict[str, dict] = {}
    http_status = 200

    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        checks["db"] = {"status": "ok"}
    except Exception as e:
        checks["db"] = {"status": "error", "detail": str(e)}
        http_status = 503

    redis_url = settings.REDIS_URL
    if redis_url:
        try:
            import redis  # type: ignore

            client = redis.from_url(redis_url, socket_connect_timeout=1, socket_timeout=1)
            client.ping()
            client.close()
            checks["redis"] = {"status": "ok"}
            checks["celery_broker"] = {"status": "ok"}
        except Exception as e:
            checks["redis"] = {"status": "error", "detail": str(e)}
            checks["celery_broker"] = {"status": "error", "detail": "unreachable"}
            http_status = 503
    else:
        checks["redis"] = {"status": "disabled", "detail": "REDIS_URL not configured"}
        checks["celery_broker"] = {"status": "disabled", "detail": "REDIS_URL not configured"}

    mode = _scheduler_mode()
    scheduler_status = "ok"
    scheduler_detail = None
    if mode == "dual":
        scheduler_status = "error"
        scheduler_detail = "APScheduler and Celery Beat are active simultaneously"
        if settings.ENVIRONMENT in {"production", "staging"}:
            http_status = 503
    checks["scheduler"] = {
        "status": scheduler_status,
        "mode": mode,
        "detail": scheduler_detail,
    }

    payload = {
        "status": "ok" if http_status == 200 else "error",
        "environment": settings.ENVIRONMENT,
        "checks": checks,
    }
    return JSONResponse(status_code=http_status, content=payload)
