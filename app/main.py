from typing import Optional

from fastapi import Depends, FastAPI, Request, HTTPException, Query
from sqlalchemy.orm import Session
from fastapi.exceptions import RequestValidationError
from fastapi.encoders import jsonable_encoder
from fastapi.responses import HTMLResponse, Response
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import logging
import time
from pathlib import Path
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
# Registra la bandeja de eventos de ticket en la sesion (avisos, webhooks...).
import app.services.service_desk.ticket_events  # noqa: F401,E402
import app.services.automation_events  # noqa: F401,E402
import app.services.preferencias_de_aviso  # noqa: F401,E402  (filtro de avisos por preferencia)


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
        logger.debug("_read_alembic_heads: excepcion ignorada", exc_info=True)
        return None


def _scheduler_flags() -> tuple[bool, bool]:
    """Return scheduler enablement flags (`settings.ENABLE_APSCHEDULER`, `ENABLE_CELERY_BEAT`/`CELERY_BEAT`)."""
    enable_apscheduler = bool(settings.ENABLE_APSCHEDULER)
    celery_beat_enabled = bool(settings.ENABLE_CELERY_BEAT or settings.CELERY_BEAT)
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
    fail_on_dual = bool(settings.FAIL_ON_DUAL_SCHEDULER)
    if fail_on_dual:
        raise RuntimeError(
            "Dual scheduler mode detected (APScheduler + Celery Beat). "
            "Disable one scheduler (ENABLE_APSCHEDULER=0 or ENABLE_CELERY_BEAT=0). "
            f"[env={settings.ENVIRONMENT}]"
        )


def _enforce_superadmin_bypass_safety() -> None:
    """Audit #C3: refuse to boot if ENABLE_SUPERADMIN_BYPASS=1 outside development.

    The bypass path in auth_core has multiple defence-in-depth gates, but an
    early hard-fail at startup prevents a misconfigured env from silently
    allowing the bypass to take effect at request time.
    """
    if not settings.ENABLE_SUPERADMIN_BYPASS:
        return
    if settings.ENVIRONMENT != "development":
        raise RuntimeError(
            "ENABLE_SUPERADMIN_BYPASS=1 is only allowed when ENVIRONMENT=development "
            f"(current: {settings.ENVIRONMENT}). Refusing to boot."
        )
    if not (settings.DATABASE_URL or "").startswith("sqlite"):
        raise RuntimeError(
            "ENABLE_SUPERADMIN_BYPASS=1 requires a SQLite DATABASE_URL. "
            "Refusing to boot against a non-SQLite database."
        )


def _enforce_security_switches_safety() -> None:
    """Segunda auditoría 2026-11 (hallazgo 16): interruptores de seguridad en producción.

    `DISABLE_CSRF_MIDDLEWARE` en staging/producción no arranca (el bypass de
    superadmin ya lo impide `_enforce_superadmin_bypass_safety` fuera de
    development). Apagar el filtro o el sellado de tenant se deja arrancar —es
    la vía documentada para aislar un fallo— pero queda en CRITICAL.
    """
    if settings.ENVIRONMENT not in {"production", "staging"}:
        return
    if settings.DISABLE_CSRF_MIDDLEWARE:
        raise RuntimeError(
            f"DISABLE_CSRF_MIDDLEWARE=1 is not allowed when ENVIRONMENT={settings.ENVIRONMENT}. "
            "Refusing to boot."
        )
    for interruptor in ("TENANT_AUTO_FILTER_GLOBAL", "TENANT_AUTO_STAMP_ON_INSERT"):
        if not getattr(settings, interruptor):
            logger.critical("%s=0 in %s: tenant isolation relies on RLS and explicit filters only.",
                            interruptor, settings.ENVIRONMENT)


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


# ── Fases del arranque ───────────────────────────────────────────────────────
#
# Auditoria 2026-08 (hallazgo 18). `lifespan` eran 216 lineas de complejidad 29
# en el ARRANQUE de la aplicacion y sin ningun test propio. Dos bloques se
# llevaban la mitad: la comprobacion de deriva de esquema (40 lineas) y el
# arranque del planificador (76).
#
# Los cuerpos se movieron verbatim. La red aqui no son tests propios sino la
# suite completa: el TestClient ejecuta `lifespan` en cada fixture, asi que un
# fallo en el arranque lo nota todo a la vez.


def _comprobar_deriva_de_esquema(_is_testing, _expected_rev, _enforce_drift) -> None:
    """Comprueba que el esquema de la base coincide con la revision esperada.

    En modo de pruebas se omite: la base de test la crea la propia fixture y no
    pasa por Alembic. Ver el hallazgo 11 para por que esta comprobacion existe —
    el esquema se construia por dos caminos y solo uno estaba completo.
    """
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


# Ids de los `add_job` propios que duplicaban 7 entradas de beat (segunda
# auditoria 2026-11, #45). El job store es SQLAlchemy y persiste: sin retirarlos
# seguirian corriendo junto a su copia `beat_<clave>`.
_TRABAJOS_RETIRADOS = (
    "scheduled_reports", "scheduled_key_rotation", "scheduled_alert_engine",
    "scheduled_perf_reminders", "automations_events", "automations_scan", "bpmn_timers",
)
_DIAS_CELERY = {"0": "sun", "1": "mon", "2": "tue", "3": "wed", "4": "thu", "5": "fri", "6": "sat", "7": "sun"}


def _dias_de_celery(valor: str) -> str:
    """`day_of_week` de Celery (0 = domingo) a APScheduler (nombres de dia)."""
    import re as _re
    return _re.sub(r"\d", lambda m: _DIAS_CELERY[m.group(0)], str(valor))


def _replicar_celery_beat(scheduler) -> int:
    """Registra en APScheduler cada entrada de `beat_schedule` con la misma cadencia.

    La tarea de Celery se llama en el propio proceso (`task(*args, **kwargs)`
    ejecuta su cuerpo). Una sola fuente de verdad: lo que se anada a beat
    corre tambien aqui sin tocar este fichero.
    """
    from apscheduler.triggers.cron import CronTrigger
    from app.worker import celery_app
    n = 0
    for clave, entrada in celery_app.conf.beat_schedule.items():
        c = entrada["schedule"]
        try:
            trigger = CronTrigger(
                minute=c._orig_minute, hour=c._orig_hour, day=c._orig_day_of_month,
                month=c._orig_month_of_year, day_of_week=_dias_de_celery(c._orig_day_of_week),
            )
        except (AttributeError, ValueError):
            logger.warning("Entrada de beat %s sin crontab convertible; no se replica", clave)
            continue
        tarea = entrada["task"].rsplit(".", 1)[-1]
        scheduler.add_job(
            f"app.worker:{tarea}", trigger, id=f"beat_{clave}",
            args=list(entrada.get("args") or []), kwargs=dict(entrada.get("kwargs") or {}),
            replace_existing=True, misfire_grace_time=300, coalesce=True, max_instances=1,
        )
        n += 1
    return n


def _retirar_trabajos_duplicados(scheduler) -> list:
    """Quita del job store (ya arrancado) los ids de `_TRABAJOS_RETIRADOS`."""
    from apscheduler.jobstores.base import JobLookupError
    quitados = []
    for viejo in _TRABAJOS_RETIRADOS:
        try:
            scheduler.remove_job(viejo)
            quitados.append(viejo)
        except JobLookupError:
            pass
    return quitados


def _arrancar_planificador(_enable_apscheduler, _celery_beat_enabled):
    """Levanta APScheduler si `ENABLE_APSCHEDULER=1`. Devuelve el planificador o None.

    `_celery_beat_enabled` NO decide aqui: llegar con los dos activos ya lo
    impide `_enforce_scheduler_mode_safety()`, que aborta el arranque en modo
    dual en todos los entornos (levantar los dos ejecutaria cada tarea dos
    veces: informes enviados dos veces, rotacion de claves dos veces). Aqui solo
    sirve para elegir el aviso y el modo que se loguea.
    """
    _scheduler = None
    if _enable_apscheduler:
        # APScheduler in-process es adecuado para dev y para un despliegue de un solo
        # worker. En producción multi-worker, el SQLAlchemyJobStore compartido reduce
        # pero NO garantiza la ejecución única entre procesos (APScheduler no hace
        # locking distribuido como Celery Beat). Recomendación: en prod multi-worker,
        # ENABLE_APSCHEDULER=0 + ENABLE_CELERY_BEAT=1 (un único proceso beat).
        if settings.ENVIRONMENT == "production" and not _celery_beat_enabled:
            logger.warning(
                "⚠️  APScheduler activo en producción. Con >1 worker las tareas "
                "programadas pueden ejecutarse más de una vez. Usa Celery Beat "
                "(ENABLE_APSCHEDULER=0, ENABLE_CELERY_BEAT=1) para ejecución única."
            )
        logger.info("⏰ Iniciando scheduler de informes...")
        try:
            from apscheduler.schedulers.background import BackgroundScheduler
            from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore

            # Use a SQLAlchemy job store so that in multi-worker deployments only
            # one worker executes each job (the others see it already locked/run).
            jobstores = {
                "default": SQLAlchemyJobStore(url=settings.DATABASE_URL)
            }
            _scheduler = BackgroundScheduler(
                jobstores=jobstores,
                timezone=settings.DEFAULT_TIMEZONE,
            )
            # Una sola fuente de verdad: el calendario de Celery beat, replicado
            # entero (segunda auditoria 2026-11, #45). Antes 7 entradas tenian
            # ademas su propio `add_job` aqui (y `automation_jobs.py` copiaba el
            # cuerpo de 3 tareas): dos definiciones que podian divergir.
            _replicar_celery_beat(_scheduler)
            try:
                from app.core.metrics import attach_apscheduler_metrics
                attach_apscheduler_metrics(_scheduler)
            except Exception as _metrics_exc:
                logger.warning("APScheduler metrics hook not attached: %s", _metrics_exc)
            # En pausa hasta retirar del job store persistente los ids viejos,
            # para que no lleguen a dispararse junto a su copia `beat_<clave>`.
            _scheduler.start(paused=True)
            if _scheduler.running:
                _retirar_trabajos_duplicados(_scheduler)
                _scheduler.resume()
            logger.info("   ✅ Scheduler activo (informes, rotación, alertas, recordatorios, automatizaciones, analítica y ML)")
            logger.info("✅ Modo scheduler: APScheduler")
        except Exception as e:
            logger.warning(f"   ⚠️  Scheduler no iniciado: {e}")
    elif _celery_beat_enabled:
        logger.info("✅ Modo scheduler: Celery Beat")
    else:
        logger.info("✅ Modo scheduler: Ninguno (modo manual)")
        logger.info("⏭️  APScheduler deshabilitado (ENABLE_APSCHEDULER=0)")
    return _scheduler



# ── Fases del arranque y la parada (continuacion) ────────────────────────────
#
# Segunda tanda del hallazgo 18. Tras sacar la deriva de esquema y el
# planificador, `lifespan` quedaba en complejidad 16: lo que sumaba eran cinco
# bloques try/except, cada uno con su propio manejo de errores porque un
# servicio de apoyo caido no debe impedir el arranque.


def _comprobar_dependencias_opcionales() -> None:
    """Avisa si faltan las dependencias del segundo factor.

    No aborta a proposito: sin ellas la aplicacion funciona y solo el MFA queda
    sin poder configurarse.
    """
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


def _arrancar_servicios_de_apoyo() -> None:
    """Arranca los servicios de apoyo del proceso web.

    Cada uno en su propio try a proposito: que falte uno no debe impedir que
    arranque la aplicacion. Un servicio de apoyo caido degrada una funcionalidad;
    un arranque abortado tumba el servicio entero.
    """
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


def _arrancar_planificador_de_colaboracion(_is_testing) -> None:
    """Levanta el planificador de sesiones de colaboracion.

    Se omite en la suite de pruebas: son tareas periodicas en hilo aparte que
    tocarian la base mientras cada test monta y desmonta la suya.
    """
    if not _is_testing:
        try:
            from app.services.collaboration._scheduler import start as _collab_start
            _collab_start()
        except Exception as _exc:
            logger.warning("Collab scheduler no inicializado: %s", _exc)


def _parar_planificador_de_colaboracion() -> None:
    """Detiene el planificador de colaboracion que levanto el arranque."""
    try:
        from app.services.collaboration._scheduler import stop as _collab_stop
        _collab_stop()
    except Exception:
        logger.debug("lifespan: fallo best-effort ignorado", exc_info=True)


def _parar_servicios(_scheduler) -> None:
    """Para el planificador y cierra lo que quede abierto.

    Cada paso lleva su propio try: un fallo al parar un servicio no puede
    impedir que se paren los demas.
    """
    try:
        from app.core.settings_pubsub import stop_subscriber as _stop_settings_sub
        _stop_settings_sub()
    except Exception:
        logger.debug("lifespan: fallo best-effort ignorado", exc_info=True)
    if _scheduler:
        try:
            if _scheduler.running:
                _scheduler.shutdown(wait=False)
            else:
                logger.info("   ⏭️  Scheduler ya detenido; se omite shutdown")
        except Exception as e:
            logger.warning(f"Scheduler shutdown error: {e}")
    logger.info("   ✅ Shutdown completo")


def _avisar_si_rls_desarmada() -> None:
    """Revisión 2026-11: se mide el rol de conexión, no solo que haya políticas."""
    try:
        from app.db import rls
        from app.db.session import engine
        with engine.connect() as conexion:
            estado = rls.estado(conexion)
        if estado.get("reason") and estado["reason"] != "no es Postgres":
            logger.warning("   ⚠️  Aislamiento en la base (RLS) desarmado: %s. Ver README, «Database isolation».",
                           estado["reason"])
        elif estado.get("armed"):
            logger.info("   🔒 RLS armado: %s tablas, rol %s", estado["tables_with_rls"], estado["role"])
    except Exception:
        logger.debug("lifespan: no se pudo medir RLS", exc_info=True)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    # ── Dependency preflight check ─────────────────────────────────────────
    _comprobar_dependencias_opcionales()

    logger.info("━" * 54)
    logger.info("  ◈  CONTECFLOW PSA — Iniciando servidor")
    logger.info(f"     Versión : {settings.VERSION}")
    logger.info(f"     API Base: {settings.API_V1_STR}")
    logger.info(f"     BD      : {settings.DATABASE_URL.split('/')[-1]}")
    logger.info("━" * 54)

    # ── Schema preflight (no in-process migrations) ──────────────────────────
    # Migrations must run outside application startup (CI/CD, init-container, or
    # explicit operator action). Startup only checks for obvious schema drift.
    from app.core.entorno import en_pruebas
    _is_testing = en_pruebas()
    _expected_rev = (settings.EXPECTED_ALEMBIC_REVISION or "").strip() or None
    _enforce_drift = (
        settings.ENVIRONMENT in {"production", "staging"}
        if settings.FAIL_ON_SCHEMA_DRIFT is None else bool(settings.FAIL_ON_SCHEMA_DRIFT)
    )

    _comprobar_deriva_de_esquema(_is_testing, _expected_rev, _enforce_drift)
    _avisar_si_rls_desarmada()

    # Key management bootstrap (JWT keyring + integration secret rotation policy)
    _arrancar_servicios_de_apoyo()

    # Scheduler (optional): keep disabled when Celery beat is active in deployment.
    _scheduler = None
    _enable_apscheduler, _celery_beat_enabled = _scheduler_flags()
    try:
        _enforce_scheduler_mode_safety()
        _enforce_superadmin_bypass_safety()
        _enforce_security_switches_safety()
    except RuntimeError as _sched_exc:
        logger.error("❌ Startup safety check failed: %s", _sched_exc)
        raise
    _scheduler = _arrancar_planificador(_enable_apscheduler, _celery_beat_enabled)

    # Contar endpoints registrados
    total_routes = len([r for r in _app.routes if hasattr(r, 'methods')])
    logger.info("━" * 54)
    logger.info(f"🚀 Contecflow PSA listo — {total_routes} endpoints")
    logger.info(f"   📖 Docs: {settings.BACKEND_URL}{settings.API_V1_STR}/docs")
    logger.info(f"   🔍 Health: {settings.BACKEND_URL}/health")
    logger.info("━" * 54)

    # Collaboration: scheduled message dispatcher
    _arrancar_planificador_de_colaboracion(_is_testing)

    yield

    _parar_planificador_de_colaboracion()

    logger.info("🛑 Apagando Contecflow PSA...")
    _parar_servicios(_scheduler)



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

# Audit #C2: API docs (Swagger/ReDoc/openapi.json) leak full surface area.
# Disabled in production unless EXPOSE_API_DOCS=1 is explicitly set.
_expose_docs = (
    settings.ENVIRONMENT != "production"
    or settings.EXPOSE_API_DOCS
)
app = FastAPI(
    title=settings.PROJECT_NAME,
    redirect_slashes=False,
    version=settings.VERSION,
    openapi_url=f"{settings.API_V1_STR}/openapi.json" if _expose_docs else None,
    docs_url=f"{settings.API_V1_STR}/docs" if _expose_docs else None,
    redoc_url=f"{settings.API_V1_STR}/redoc" if _expose_docs else None,
    lifespan=lifespan,
)
if not _expose_docs:
    logger.info("🔒 API docs disabled (production). Set EXPOSE_API_DOCS=1 to override.")

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
# Revisión 2026-11: sin este middleware `RATE_LIMIT_DEFAULT` no se aplicaba a
# nada; sólo limitaban las rutas con su propio `@limiter.limit` (117 de ~2.000).
from slowapi.middleware import SlowAPIMiddleware  # noqa: E402
app.add_middleware(SlowAPIMiddleware)


# Revisión 2026-11: tope diario de gasto en IA de la empresa (AI_DAILY_BUDGET_USD).
from app.services.ai_provider_service import PresupuestoDeIAAgotado as _PresupuestoDeIAAgotado  # noqa: E402


@app.exception_handler(_PresupuestoDeIAAgotado)
async def _presupuesto_de_ia_agotado(_request, exc):
    from fastapi.responses import JSONResponse
    return JSONResponse(status_code=429, content={"detail": str(exc)})


from app.core.errores import ErrorDeDominio  # noqa: E402


@app.exception_handler(HTTPException)
@app.exception_handler(ErrorDeDominio)  # auditoria 2026-11: los servicios ya no lanzan HTTPException
async def http_exception_sanitizer(_request: Request, exc: HTTPException):
    safe_detail = sanitize_http_detail(exc.status_code, exc.detail)
    if safe_detail != exc.detail:
        logger.warning("Sanitized HTTPException detail (status=%s)", exc.status_code)
    # Revisión 2026-11: las cabeceras de la excepción se perdían aquí (el
    # `WWW-Authenticate` de un 401, el código de fallo de los conectores).
    return JSONResponse(status_code=exc.status_code, content={"detail": safe_detail},
                        headers=getattr(exc, "headers", None))


@app.exception_handler(RequestValidationError)
async def validation_exception_sanitizer(_request: Request, exc: RequestValidationError):
    # Keep standard validation structure; sanitize only if it unexpectedly contains a string payload.
    # jsonable_encoder mirrors FastAPI's default handler: pydantic v2 error dicts may carry a
    # non-serializable ValueError under `ctx` (raised by custom field validators), which would
    # otherwise blow up json.dumps and turn a 422 into a 500.
    safe_detail = sanitize_http_detail(422, jsonable_encoder(exc.errors()))
    return JSONResponse(status_code=422, content={"detail": safe_detail})

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization", "X-Request-ID", "X-Requested-With"],
    expose_headers=["X-Conector-Codigo", "Content-Disposition"],
)

# Audit #C1: CSRF protection — Origin/Referer check (always on) + optional
# double-submit token via CSRF_DOUBLE_SUBMIT=1. Exempts third-party webhooks
# (HMAC-verified) and Authorization-header-only requests.
from app.core.csrf import CSRFMiddleware
app.add_middleware(CSRFMiddleware)
# Revisión 2026-11: la petición previa de las rutas públicas de los widgets,
# por fuera de CORS (ver app/core/cors_publico.py).
from app.core.cors_publico import CorsPublico  # noqa: E402
app.add_middleware(CorsPublico)

# ABACMiddleware retirado en la auditoría 2026-08 (hallazgo P1-5).
#
# Era un no-op absoluto: comprobaba `request.state.user` y se saltaba el chequeo
# cuando era None, pero NINGUNA línea del proyecto asignaba ese atributo. La
# autenticación vive en una dependencia de FastAPI (app/core/deps.py), que corre
# DESPUÉS del middleware, así que los 110 prefijos del registro nunca se
# comprobaron ni una vez.
#
# No se cableó, se borró, por dos razones de diseño:
#   1. Poblar request.state.user obligaría a decodificar el JWT en el middleware:
#      una segunda vía de autenticación en paralelo a la dependencia. Dos caminos
#      de auth es peor arquitectura que uno.
#   2. El registro mapeaba TODOS los prefijos a action="read", así que un DELETE
#      se habría comprobado como lectura. El permiso evaluado era el equivocado.
#
# El control real son los 233 `enforce_abac(...)` a nivel de endpoint, que sí
# reciben el resource_type y la action correctos. La cobertura de esos puntos la
# vigila tests/test_abac_coverage.py.

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
    # Revisión 2026-11: v1 es la API. Antes toda respuesta salía marcada como
    # obsoleta por un /api/v2 de tres rutas que nadie usaba; ahora sólo lleva
    # `Deprecation` la ruta que de verdad tiene sucesora (y la dice en `Link`).
    if path.startswith(settings.API_V1_STR):
        response.headers["x-api-version"] = "1"

    response.headers["X-Content-Type-Options"] = "nosniff"
    # Document file/preview endpoints need to render inside the SPA's iframe (same origin).
    # Everything else stays DENY for click-jacking protection.
    is_doc_file_route = (
        path.startswith(f"{docs_base}/documents/file/")
        or (path.startswith(f"{docs_base}/documents/") and path.endswith("/preview"))
    )
    # La página de incrustación de BI trae su propio `frame-ancestors` (los
    # dominios de la empresa, Teams, SharePoint…): aquí no se pisa.
    es_pagina_de_incrustacion = path == f"{settings.API_V1_STR}/bi/embed/view"
    if not es_pagina_de_incrustacion:
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
    # El widget de estado lo carga la web de un cliente: otro origen.
    response.headers["Cross-Origin-Resource-Policy"] = (
        "cross-origin" if path in ("/status/embed.js", "/widget/ticket.js") else "same-origin")
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
    elif es_pagina_de_incrustacion:
        pass
    else:
        frame_ancestors = "'self'" if is_doc_file_route else "'none'"
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
            # Segunda auditoría 2026-11: DocumentsPage muestra el PDF en un
            # <iframe> con la URL de /documents/file/ (almacenamiento local). Con
            # 'none' el navegador lo bloqueaba aunque X-Frame-Options ya fuera
            # SAMEORIGIN: CSP manda. Solo esas rutas admiten el propio origen.
            f"frame-ancestors {frame_ancestors}; "
            "object-src 'none'; "
            "base-uri 'self';"
        )
    return response

# ABAC por ruta, vía dependencia (auditoría 2026-08, P1-5). Reemplaza al
# ABACMiddleware borrado: una dependencia se resuelve en la misma fase que
# get_current_user, así que el usuario autenticado sí está disponible — que es
# exactamente lo que el middleware nunca tuvo. Registrarla aquí hace que
# ABAC_COVERED_PREFIXES vuelva a ser configuración con efecto real, en vez de una
# lista de intenciones. Ver app/core/abac_dependency.py.
from app.core.abac_dependency import apply_abac_for_route

# Matriz de permisos GRC, ahora APLICADA (auditoría 2026-08, hallazgo 27). Era una
# pantalla de administración que escribía en una tabla que nadie leía:
# grc.check_permission() decía "Used by other API endpoints to enforce GRC" y
# tenía cero invocaciones. Es un control aditivo — sólo puede quitar permiso, no
# dar — y sus dos dimensiones se derivan de la ruta, así que cubre los 126
# dominios de la API sin ninguna lista que mantener.
# Ver app/core/grc_enforce.py y app/core/grc_catalog.py.
from app.core.grc_enforce import enforce_grc_matrix

# Zona horaria de la petición (auditoría 2026-08, P2-14). Publica
# `usuario → organización → UTC` en un ContextVar para que `timeutil.today()`
# devuelva el día de QUIEN pregunta y no el del servidor. Va primero a propósito:
# ABAC y GRC pueden evaluar condiciones con fecha, así que necesitan la zona ya
# resuelta. Ver app/core/timezone_context.py — tiene que ser `async def` o el
# ContextVar se pierde en el threadpool, en silencio.
from app.core.timezone_context import bind_request_timezone

_ROUTER_GUARDS = [
    Depends(bind_request_timezone),
    Depends(apply_abac_for_route),
    Depends(enforce_grc_matrix),
]

app.include_router(
    api_router,
    prefix=settings.API_V1_STR,
    dependencies=_ROUTER_GUARDS,
)

# ── Prometheus metrics (opt-in via METRICS_ENABLED) ────────────────────────
# Registers RED HTTP metrics + exposes /metrics. Must run after routers are
# included so the instrumentator can introspect templated paths.
from app.core.metrics import setup_metrics
setup_metrics(app)


from app.db.session import get_db as _get_db  # noqa: E402


@app.get("/status", response_class=HTMLResponse)
def public_status_page(org: Optional[str] = Query(None, max_length=100), db: Session = Depends(_get_db)):
    """Página de estado pública de una empresa (?org=<slug>), en su idioma."""
    from app.services.service_desk import pagina_de_estado_publica as pagina
    from app.services.service_desk.status_page_service import organizacion_de_la_pagina
    return HTMLResponse(pagina.pagina(pagina.idioma_de(db, organizacion_de_la_pagina(db, org))))


@app.get("/status/page.js")
def public_status_page_js():
    """El código de la página: aparte, porque la CSP no admite código en línea."""
    from app.services.service_desk.pagina_de_estado_publica import guion_de_pagina
    return Response(content=guion_de_pagina(settings.API_V1_STR), media_type="application/javascript; charset=utf-8")


@app.get("/status/embed.js")
def status_embed_js():
    """Widget de estado para la web de un cliente (se carga desde otro origen)."""
    from app.services.service_desk.pagina_de_estado_publica import guion_del_widget
    return Response(content=guion_del_widget(settings.API_V1_STR), media_type="application/javascript; charset=utf-8")


@app.get("/widget/ticket.js")
def ticket_widget_js():
    """Widget de solicitudes para la web de un cliente (va con el token de un formulario público)."""
    from app.services.widget_de_formulario import guion
    return Response(content=guion(settings.API_V1_STR), media_type="application/javascript; charset=utf-8")



# ── Middleware de logging de peticiones ───────────────────────────────────────
#
# Auditoria 2026-08 (hallazgo 18): `request_logger` estaba en complejidad 11 y se
# ejecuta en CADA peticion. Las tres decisiones que tomaba —nivel de log, pista
# de usuario y saneado de la URL— salieron a funciones propias, y los dos
# conjuntos literales pasaron a constantes de modulo: antes se reconstruian en
# cada peticion.

# 401 que son normales y esperados en el uso corriente de la aplicacion, no un
# problema: el sondeo de sesion al arrancar, y las consultas que salen en
# paralelo mientras el interceptor renueva la cookie de acceso caducada. Se
# loguean como INFO para que un log a nivel WARNING no se llene de ruido.
_PETICIONES_CON_401_ESPERADO = frozenset({
    "/api/v1/auth/me",
    "/api/v1/users/me/preferences",
    "/api/v1/alerts",
    "/api/v1/approvals/requests/pending-my-action",
    "/api/v1/activity/mentions/my",
    "/api/v1/imputations/timer/current",
    "/api/v1/settings/log-level",
    "/api/v1/sd/auto-resolution/stats",
    "/api/v1/sd/auto-resolution/config",
})

# Rutas que no se loguean: ruido de sondas y de assets.
_RUTAS_SIN_LOG = frozenset({"/health", "/ready", "/metrics", "/favicon.ico"})

# Parametros de query que nunca deben acabar en un fichero de log.
_PARAMETROS_SECRETOS = ("token", "access_token", "refresh_token", "code", "state", "id_token")


def _nivel_y_icono(status: int, path: str) -> tuple[int, str]:
    """Nivel de log e icono para un codigo de respuesta."""
    if status < 300:
        return logging.INFO, "✅"
    if status < 400:
        return logging.INFO, "↩️ "
    if status == 401 and path in _PETICIONES_CON_401_ESPERADO:
        return logging.INFO, "🔑"
    if status < 500:
        return logging.WARNING, "⚠️ "
    return logging.ERROR, "❌"


def _pista_de_usuario(request: Request) -> str:
    """Los 8 primeros caracteres del sujeto del token, si viene y es valido.

    Devuelve cadena vacia ante cualquier problema: un token ilegible no puede
    tumbar el logging de la peticion.
    """
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        return ""
    try:
        from app.core.security import decode_token
        payload = decode_token(auth[7:])
    except Exception as e:
        logger.debug("JWT decode failed in request logging: %s", e)
        return ""
    if not payload:
        return ""
    return f" | user:{payload.get('sub','?')[:8]}"


def _url_sin_secretos(request: Request) -> str:
    """La URL de la peticion con los parametros sensibles tapados."""
    import re as _re
    safe_url = str(request.url)
    for _k in _PARAMETROS_SECRETOS:
        safe_url = _re.sub(rf"(?<=[?&]){_k}=[^&]*", f"{_k}=[REDACTED]", safe_url)
    return safe_url


@app.middleware("http")
async def request_logger(request: Request, call_next):
    start = time.time()
    response = await call_next(request)
    duration = round((time.time() - start) * 1000)

    path   = request.url.path
    method = request.method
    status = response.status_code

    if path in _RUTAS_SIN_LOG or path.startswith("/static"):
        return response

    level, icon = _nivel_y_icono(status, path)
    user_hint = _pista_de_usuario(request)
    logger.log(level, f"{icon} {method:6} {path:<45} {status} [{duration}ms]{user_hint}")

    if status >= 400:
        logger.log(level, f"   └─ {method} {_url_sin_secretos(request)}")

    return response


@app.get("/health", tags=["Health"])
def health():
    from app.db.session import engine
    from sqlalchemy import text
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        db_status = "ok"
    except Exception:
        # Auditoria 2026-11: /health es publico; el error (host, usuario de la
        # BD, ruta del fichero) va al log, no a la respuesta.
        logger.exception("health: la BD no responde")
        db_status = "error"
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
    except Exception:
        logger.exception("ready: la BD no responde")
        checks["db"] = {"status": "error", "detail": "unreachable"}
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
        except Exception:
            logger.exception("ready: Redis no responde")
            checks["redis"] = {"status": "error", "detail": "unreachable"}
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
