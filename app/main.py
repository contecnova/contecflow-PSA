from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, Response
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import logging
import os
import time
from app.core.config import settings

# ── Logging rico ──────────────────────────────────────────────────────────────
_log_level_name = (settings.LOG_LEVEL or os.environ.get("LOG_LEVEL", "INFO")).upper()
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
    )
    logger.info(f"✅ Sentry inicializado (env={settings.SENTRY_ENVIRONMENT})")


# ── Rate Limiter (P0-1) ────────────────────────────────────────────────────────
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from app.core.ratelimit import limiter


@asynccontextmanager
async def lifespan(_app: FastAPI):
    logger.info("━" * 54)
    logger.info("  ◈  CONTECFLOW PSA — Iniciando servidor")
    logger.info(f"     Versión : {settings.VERSION}")
    logger.info(f"     API Base: {settings.API_V1_STR}")
    logger.info(f"     BD      : {settings.DATABASE_URL.split('/')[-1]}")
    logger.info("━" * 54)

    # ── Migrations ────────────────────────────────────────────────────────────
    # In production, Alembic migrations are run by the migrate init-container
    # (see docker-compose.yml) BEFORE the backend starts, so multiple replicas
    # don't race on schema changes during a rolling deploy.
    #
    # In development / SQLite mode we still run them here for convenience.
    # SKIP_STARTUP_MIGRATIONS=1 lets the init-container pattern opt out.
    import os as _os
    _skip_migrations = _os.getenv("SKIP_STARTUP_MIGRATIONS", "0") == "1" or _os.getenv("TESTING", "0") == "1"
    if not _skip_migrations:
        logger.info("🔄 Ejecutando migraciones Alembic (startup)...")
        alembic_cfg = None
        try:
            import asyncio as _asyncio
            import sys as _sys
            import subprocess as _subprocess
            from app.db.base import Base
            from app.core.config import settings as _settings
            from alembic.config import Config as AlembicConfig
            from alembic import command as alembic_command
            from sqlalchemy import create_engine as _ce
            from sqlalchemy.pool import NullPool as _NullPool

            # create_all for fresh DBs using an isolated NullPool engine
            _tmp_engine = _ce(_settings.DATABASE_URL, poolclass=_NullPool)
            Base.metadata.create_all(bind=_tmp_engine)
            _tmp_engine.dispose()
            del _tmp_engine

            # Run alembic upgrade in a subprocess so it is fully isolated from
            # uvicorn's process/asyncio context, preventing SQLite WAL lock hangs.
            _project_root = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))
            _proc = await _asyncio.create_subprocess_exec(
                _sys.executable, "-m", "alembic", "upgrade", "head",
                cwd=_project_root,
                stdout=_asyncio.subprocess.PIPE,
                stderr=_asyncio.subprocess.STDOUT,
            )
            _out, _ = await _proc.communicate()
            if _out:
                for _line in _out.decode(errors='replace').splitlines():
                    logger.info("   alembic: %s", _line)
            if _proc.returncode != 0:
                raise RuntimeError(f"alembic upgrade head exited with code {_proc.returncode}")
            logger.info("   ✅ Alembic migrations applied")
        except Exception as _ae:
            _err = str(_ae).lower()
            _is_sqlite = settings.DATABASE_URL.lower().startswith("sqlite")
            _known_local_schema_drift = (
                "already exists" in _err
                or "duplicate column" in _err
                or "no such table" in _err
            )
            if _is_sqlite and _known_local_schema_drift:
                logger.warning(
                    "   ⚠️  Alembic detectó esquema local preexistente/inconsistente "
                    "(SQLite). Marcando head y continuando startup..."
                )
                try:
                    _stamp_proc = await _asyncio.create_subprocess_exec(
                        _sys.executable, "-m", "alembic", "stamp", "head",
                        cwd=_project_root,
                        stdout=_asyncio.subprocess.PIPE,
                        stderr=_asyncio.subprocess.STDOUT,
                    )
                    await _stamp_proc.communicate()
                    logger.info("   ✅ Alembic stamp head aplicado (SQLite local)")
                except Exception as _se:
                    logger.warning(f"   ⚠️  No se pudo hacer Alembic stamp: {_se}")
            else:
                logger.error(f"   ❌ Alembic upgrade error: {_ae}")
                raise
    else:
        logger.info("⏭️  Migraciones omitidas (testing/init-container)")

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

    # Scheduler (optional): keep disabled when Celery beat is active in deployment.
    _scheduler = None
    _enable_apscheduler = os.getenv("ENABLE_APSCHEDULER", "1") == "1"
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
            _scheduler.start()
            logger.info("   ✅ Scheduler activo (informes + rotación de claves)")
        except Exception as e:
            logger.warning(f"   ⚠️  Scheduler no iniciado: {e}")
    else:
        logger.info("⏭️  APScheduler deshabilitado (ENABLE_APSCHEDULER=0)")

    # Contar endpoints registrados
    total_routes = len([r for r in _app.routes if hasattr(r, 'methods')])
    logger.info("━" * 54)
    logger.info(f"🚀 Contecflow PSA listo — {total_routes} endpoints")
    logger.info(f"   📖 Docs: {settings.BACKEND_URL}{settings.API_V1_STR}/docs")
    logger.info(f"   🔍 Health: {settings.BACKEND_URL}/health")
    logger.info("━" * 54)

    yield

    logger.info("🛑 Apagando Contecflow PSA...")
    if _scheduler:
        try:
            _scheduler.shutdown(wait=False)
        except Exception as e:
            logger.warning(f"Scheduler shutdown error: {e}", exc_info=True)
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

# Registrar el middleware global de excepciones
app.add_middleware(ExceptionHandlerMiddleware)

# Rate limiter state + 429 handler
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

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
    if path.startswith(settings.API_V2_STR):
        response.headers["x-api-version"] = "2"
    elif path.startswith(settings.API_V1_STR):
        response.headers["x-api-version"] = "1"
        # Si v2 está montada, marcamos v1 como deprecated
        response.headers["x-api-deprecated"] = "true"
        response.headers["deprecation"] = "true"

    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    if is_docs_route:
        # Swagger/ReDoc HTML uses CDN assets and an inline bootstrap script.
        response.headers["Content-Security-Policy"] = (
            "default-src 'self' https://cdn.jsdelivr.net https://fastapi.tiangolo.com; "
            "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
            "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://fonts.googleapis.com; "
            "img-src 'self' data: blob: https://fastapi.tiangolo.com; "
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
            "font-src 'self' data: https://fonts.gstatic.com; "
            "connect-src 'self' ws: wss:; "
            "frame-ancestors 'none'; "
            "object-src 'none'; "
            "base-uri 'self';"
        )
    return response

app.include_router(api_router, prefix=settings.API_V1_STR)
app.include_router(api_v2_router, prefix=settings.API_V2_STR)


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

    # Ignorar rutas de health y assets estáticos
    if path in ("/health", "/favicon.ico") or path.startswith("/static"):
        return response

    # Color según status
    # 401 on /auth/me is expected (session probe at startup) — log as INFO
    _expected_401 = (status == 401 and path.endswith("/auth/me"))
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
            logger.debug(f"JWT decode failed in request logging: {e}")

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
