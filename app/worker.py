from celery import Celery
from app.core.timeutil import utcnow
from celery.schedules import crontab
from app.core.config import settings

celery_app = Celery(
    "contecflow",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
    # Todas las tareas @celery_app.task viven en este mismo módulo (app.worker),
    # no en "app.tasks" (que no existe). Apuntamos include al módulo real para que
    # el worker las descubra al arrancar. Ver beat_schedule ("app.worker.<task>").
    include=["app.worker"],
)

celery_app.conf.beat_schedule = {
    # Run alert engine every day at 8am
    "perf-reminders-daily": {
        "task": "app.worker.run_perf_reminders",
        "schedule": crontab(hour=9, minute=0),  # misma hora que en APScheduler
    },
    "run-alert-engine-daily": {
        "task": "app.worker.run_alert_engine",
        "schedule": crontab(hour=8, minute=0),
    },
    # Weekly load report every Monday at 9am
    "weekly-load-report": {
        "task": "app.worker.send_weekly_report",
        "schedule": crontab(hour=9, minute=0, day_of_week=1),
    },
    # Check missing imputations every weekday at 18:00
    "check-missing-imputations": {
        "task": "app.worker.check_missing_imputations",
        "schedule": crontab(hour=18, minute=0, day_of_week="1-5"),
    },
    # Recurring retainer invoices — runs daily at 07:00, checks retainer_day
    "generate-retainer-invoices": {
        "task": "app.worker.generate_retainer_invoices",
        "schedule": crontab(hour=7, minute=0),
    },
    # Scheduled reports — check every hour
    "run-scheduled-reports": {
        "task": "app.worker.run_scheduled_reports",
        "schedule": crontab(minute=0),  # every hour at :00
    },
    # Key material rotation
    "run-key-rotation": {
        "task": "app.worker.run_scheduled_rotation",
        "schedule": crontab(hour=settings.KEY_ROTATION_RUN_HOUR_UTC, minute=17),
    },
    # Jira bidirectional sync — pull updated issues every 30 minutes
    "jira-periodic-sync": {
        "task": "app.worker.jira_periodic_sync",
        "schedule": crontab(minute="*/30"),
    },
    # Approval timeout escalation — check every hour
    "process-approval-timeouts": {
        "task": "app.worker.process_approval_timeouts",
        "schedule": crontab(minute=0),  # every hour at :00
    },
    # Reconocimiento ASC 606: se COMPRUEBA a diario, no una vez al mes.
    #
    # Auditoría 2026-08. Antes era `crontab(day_of_month=1, hour=2)`, un único
    # disparo para todo el mundo, y eso desplazaba el periodo de las
    # organizaciones al oeste de UTC: a las 02:00 UTC del día 1, en UTC−6 es
    # todavía el día 31 del mes anterior, así que su «mes anterior» salía un mes
    # antes de lo debido y el mes que de verdad acababa de cerrar no se reconocía
    # nunca. La tarea recorre ahora las organizaciones y sólo actúa sobre las que
    # están en su día 1, así que cada una recibe exactamente un cierre por mes.
    #
    # Correr a diario es seguro porque el lote es idempotente: la guarda de
    # `revenue_service._ya_reconocido` más el índice único de la revisión 091.
    # Antes de ese arreglo, repetirlo duplicaba ingresos.
    "revenue-monthly-recognition": {
        "task": "app.worker.revenue_monthly_recognition",
        "schedule": crontab(hour=2, minute=0),  # a diario a las 02:00 UTC
    },
    # ML model retraining — 1st of every month at 03:00 (after revenue recognition)
    "ml-model-retrain": {
        "task": "app.worker.ml_model_retrain",
        "schedule": crontab(day_of_month=1, hour=3, minute=0),
    },
    # OLAP nightly ETL — incremental load PostgreSQL → DuckDB every night at 01:00
    "olap-nightly-etl": {
        "task": "app.worker.olap_nightly_etl",
        "schedule": crontab(hour=1, minute=0),
    },
    # ── Fase 1 ITSM tasks ──────────────────────────────────────────────────────
    # SLA: estado, avisos y escalado — cada 5 minutos. Con 15, un P1 de una
    # hora podia pasar de «en riesgo» a incumplido sin aviso intermedio.
    "sla-breach-scan": {
        "task": "app.worker.sla_breach_scan",
        "schedule": crontab(minute="*/5"),
    },
    # Correo entrante: buzon de soporte de cada organizacion.
    "sd-leer-buzones": {
        "task": "app.worker.sd_leer_buzones",
        "schedule": crontab(minute="*/2"),
    },
    # Bandeja de eventos de ticket: red de seguridad del encolado al confirmar.
    "sd-ticket-events": {
        "task": "app.worker.sd_procesar_eventos_de_ticket",
        "schedule": crontab(minute="*"),
    },
    # Automatizaciones: bandeja de eventos (red del encolado al confirmar) y
    # barrido de fechas y umbrales cada AUTOMATIONS_SCAN_MINUTES.
    "automations-events": {
        "task": "app.worker.automations_procesar_eventos",
        "schedule": crontab(minute="*"),
    },
    "automations-scan": {
        "task": "app.worker.automations_escanear",
        "schedule": crontab(minute=f"*/{max(1, settings.AUTOMATIONS_SCAN_MINUTES)}"),
    },
    # BPM: temporizadores vencidos de las instancias de proceso.
    "bpmn-timers": {
        "task": "app.worker.bpmn_vencer_temporizadores",
        "schedule": crontab(minute="*"),
    },
    # Problem auto-detection — every hour at :05
    "problem-auto-detect": {
        "task": "app.worker.problem_auto_detect",
        "schedule": crontab(minute=5),
    },
    # CMDB auto-discovery — every 15 min; per-provider cadence respected via next_run_at (ITSM-P04)
    "cmdb-discovery": {
        "task": "app.worker.cmdb_discovery_run",
        "schedule": crontab(minute="*/15"),
    },
    # ITSM-P05: Change Impact — batch-score pending changes every 10 minutes
    "change-impact-batch-score": {
        "task": "app.worker.change_impact_batch_score",
        "schedule": crontab(minute="*/10"),
    },
    # ITSM-P07: ML Routing outcome backfill — every hour at :20
    "routing-outcome-scan": {
        "task": "app.worker.routing_outcome_scan",
        "schedule": crontab(minute=20),
    },
    # Phase 2 — Predictive Intelligence scan — every 30 minutes
    "predictive-scan": {
        "task": "app.worker.predictive_scan",
        "schedule": crontab(minute="*/30"),
    },
    # Phase 2 — Predictive model evaluation/retraining trigger — every 6 hours
    "predictive-model-eval-retrain": {
        "task": "app.worker.predictive_model_eval_retrain",
        "schedule": crontab(minute=10, hour="*/6"),
    },
    # Phase 2 — Asset expiry scan — daily at 07:05
    "asset-expiry-scan": {
        "task": "app.worker.asset_expiry_scan",
        "schedule": crontab(hour=7, minute=5),
    },
    # Phase 3 — ITSM metric snapshot — every hour at :50
    "analytics-snapshot": {
        "task": "app.worker.analytics_snapshot",
        "schedule": crontab(minute=50),
    },
    # Phase 3 — Catalog popularity recalc — every 6 hours
    "catalog-popularity": {
        "task": "app.worker.catalog_popularity_update",
        "schedule": crontab(minute=0, hour="*/6"),
    },
    # Phase 3 — Compliance check — weekly on Mondays at 06:00
    "compliance-check": {
        "task": "app.worker.compliance_check",
        "schedule": crontab(hour=6, minute=0, day_of_week=1),
    },
    # ── BI Phase 2 tasks ──────────────────────────────────────────────────────
    # BI scheduled delivery — check every hour at :45
    "bi-scheduled-delivery": {
        "task": "app.worker.bi_scheduled_delivery_run",
        "schedule": crontab(minute=45),
    },
    # BI KPI snapshot push via Redis — every 5 minutes
    "bi-kpi-push": {
        "task": "app.worker.bi_kpi_push",
        "schedule": crontab(minute="*/5"),
    },
    # BI ML model retrain (Prophet / LightGBM) — weekly on Sundays at 03:30
    "bi-ml-retrain": {
        "task": "app.worker.bi_ml_retrain",
        "schedule": crontab(hour=3, minute=30, day_of_week=0),
    },
    # ── ITSM Fase 3 tasks ─────────────────────────────────────────────────────
    # Autonomous agent scan — every 5 minutes
    "autonomous-agent-scan": {
        "task": "app.worker.autonomous_agent_scan",
        "schedule": crontab(minute="*/5"),
    },
    # ITSM-P02 — KEDB expiry scan — daily at 06:30
    "kedb-expiry-scan": {
        "task": "app.worker.kedb_expiry_scan",
        "schedule": crontab(hour=6, minute=30),
    },
    # ITSM-P02 — KEDB effectiveness recompute — daily at 07:00
    "kedb-effectiveness-scan": {
        "task": "app.worker.kedb_effectiveness_scan",
        "schedule": crontab(hour=7, minute=0),
    },
    # ITSM-P03 — Alert correlation scan — every 30 minutes
    "alert-correlation-scan": {
        "task": "app.worker.alert_correlation_scan",
        "schedule": crontab(minute="*/30"),
    },
    # ── BI ETL Connector sync ──────────────────────────────────────────────────
    # Each connector fires once per hour at a staggered minute offset
    # to distribute load and avoid thundering herd.
    "bi-connector-sync-salesforce": {
        "task": "app.worker.sync_connector_data",
        "schedule": crontab(minute=1),
        "kwargs": {"connector_id": "salesforce"},
    },
    "bi-connector-sync-hubspot": {
        "task": "app.worker.sync_connector_data",
        "schedule": crontab(minute=2),
        "kwargs": {"connector_id": "hubspot"},
    },
    "bi-connector-sync-jira": {
        "task": "app.worker.sync_connector_data",
        "schedule": crontab(minute=3),
        "kwargs": {"connector_id": "jira"},
    },
    "bi-connector-sync-stripe": {
        "task": "app.worker.sync_connector_data",
        "schedule": crontab(minute=4),
        "kwargs": {"connector_id": "stripe"},
    },
    "bi-connector-sync-xero": {
        "task": "app.worker.sync_connector_data",
        "schedule": crontab(minute=5),
        "kwargs": {"connector_id": "xero"},
    },
    "bi-connector-sync-zendesk": {
        "task": "app.worker.sync_connector_data",
        "schedule": crontab(minute=6),
        "kwargs": {"connector_id": "zendesk"},
    },
    "bi-connector-sync-freshdesk": {
        "task": "app.worker.sync_connector_data",
        "schedule": crontab(minute=7),
        "kwargs": {"connector_id": "freshdesk"},
    },
    "bi-connector-sync-servicenow": {
        "task": "app.worker.sync_connector_data",
        "schedule": crontab(minute=8),
        "kwargs": {"connector_id": "servicenow"},
    },
    "bi-connector-sync-pipedrive": {
        "task": "app.worker.sync_connector_data",
        "schedule": crontab(minute=9),
        "kwargs": {"connector_id": "pipedrive"},
    },
    "bi-connector-sync-zoho-crm": {
        "task": "app.worker.sync_connector_data",
        "schedule": crontab(minute=10),
        "kwargs": {"connector_id": "zoho_crm"},
    },
    "bi-connector-sync-quickbooks": {
        "task": "app.worker.sync_connector_data",
        "schedule": crontab(minute=11),
        "kwargs": {"connector_id": "quickbooks"},
    },
    "bi-connector-sync-github": {
        "task": "app.worker.sync_connector_data",
        "schedule": crontab(minute=12),
        "kwargs": {"connector_id": "github"},
    },
    "bi-connector-sync-gitlab": {
        "task": "app.worker.sync_connector_data",
        "schedule": crontab(minute=13),
        "kwargs": {"connector_id": "gitlab"},
    },
    "bi-connector-sync-datadog": {
        "task": "app.worker.sync_connector_data",
        "schedule": crontab(minute=14),
        "kwargs": {"connector_id": "datadog"},
    },
    "bi-connector-sync-monday": {
        "task": "app.worker.sync_connector_data",
        "schedule": crontab(minute=15),
        "kwargs": {"connector_id": "monday"},
    },
    "bi-connector-sync-asana": {
        "task": "app.worker.sync_connector_data",
        "schedule": crontab(minute=16),
        "kwargs": {"connector_id": "asana"},
    },
    "bi-connector-sync-trello": {
        "task": "app.worker.sync_connector_data",
        "schedule": crontab(minute=17),
        "kwargs": {"connector_id": "trello"},
    },
    "bi-connector-sync-shopify": {
        "task": "app.worker.sync_connector_data",
        "schedule": crontab(minute=18),
        "kwargs": {"connector_id": "shopify"},
    },
    "bi-connector-sync-intercom": {
        "task": "app.worker.sync_connector_data",
        "schedule": crontab(minute=19),
        "kwargs": {"connector_id": "intercom"},
    },
    "bi-connector-sync-clickup": {
        "task": "app.worker.sync_connector_data",
        "schedule": crontab(minute=20),
        "kwargs": {"connector_id": "clickup"},
    },
    "bi-connector-sync-google-analytics": {
        "task": "app.worker.sync_connector_data",
        "schedule": crontab(minute=21),
        "kwargs": {"connector_id": "google_analytics"},
    },
}

celery_app.conf.timezone = settings.DEFAULT_TIMEZONE

import logging as _logging
_worker_logger = _logging.getLogger(__name__)

# Los cambios de ticket que hace el worker (escalado, flujos) tambien pasan por
# la bandeja de eventos: registra sus escuchadores en la sesion.
import app.services.service_desk.ticket_events  # noqa: F401,E402
import app.services.automation_events  # noqa: F401,E402


def _aplicar_cortacircuitos(hook) -> None:
    """Suspende un webhook tras N fallos seguidos, y avisa a los administradores.

    Auditoría 2026-09 (hallazgo 18): esto vivía dentro de la tarea de entrega,
    anidado a cuatro niveles. Es una decisión con nombre propio —«este destino
    está muerto, deja de intentarlo»— y aquí se puede probar sola.

    Suspender no es tirar la configuración: el webhook se queda inactivo con su
    `suspended_at`, y alguien lo reactiva desde el panel cuando arregle el
    destino. Sin esto, un endpoint muerto recibe reintentos para siempre.

    El evento de aviso usa **su propia sesión** porque la de la entrega puede
    estar a medias de una transacción que todavía no se ha confirmado.
    """
    from datetime import datetime, timezone

    umbral = getattr(settings, "WEBHOOK_CB_THRESHOLD", 5)
    if hook.consecutive_failures < umbral or not hook.is_active:
        return

    hook.is_active = False
    hook.suspended_at = datetime.now(timezone.utc)
    _worker_logger.error(
        "Circuit breaker: webhook %s (%s) suspended after %d consecutive "
        "failures. Re-enable via the admin panel once the endpoint is fixed.",
        hook.id, hook.url, hook.consecutive_failures,
    )
    try:
        from app.core.events import emit_event
        from app.db.session import worker_db_session

        with worker_db_session() as _db:
            emit_event(_db, "webhook.suspended", {
                "webhook_id": hook.id,
                "webhook_name": hook.name,
                "url": hook.url,
                "consecutive_failures": hook.consecutive_failures,
            })
    except Exception as exc:
        # El aviso es cortesía: que no se pueda emitir no debe impedir la
        # suspensión, que es lo que de verdad protege al destino.
        _worker_logger.debug("Could not emit webhook.suspended event: %s", exc)


@celery_app.task(
    bind=True,
    name="app.worker.deliver_webhook",
    max_retries=3,
)
def deliver_webhook_task(self, webhook_id: int, body: str, event: str):
    """Deliver a single outbound webhook with automatic retry on network errors.

    Retry schedule: 60s → 300s → 1800s (attempt 1 → 2 → 3).
    Each attempt is logged as a WebhookDelivery row regardless of outcome.
    """
    import httpx
    import time
    from datetime import datetime, timezone
    from app.db.session import worker_db_session
    from app.models.enterprise import Webhook, WebhookDelivery
    from app.core.encryption import decrypt_value
    from app.services.webhooks import _sign_payload
    from app.services.enterprise_service import _validate_webhook_url

    # Explicit retry schedule requested for transient webhook failures.
    retry_schedule = (60, 300, 1800)
    transient_statuses = {408, 425, 429, 500, 502, 503, 504}

    with worker_db_session() as db:
        hook = db.query(Webhook).filter(
            Webhook.id == webhook_id,
            Webhook.is_active == True,
        ).first()

        if not hook:
            return {"skipped": True, "reason": "webhook not found or inactive"}

        status_code = None
        response_text = None
        success = False
        error = None
        duration_ms = None
        http_exc = None

        # ── SSRF guard — re-validate at delivery time (defense in depth) ──────
        # The URL is validated on create/update, but DNS can be re-pointed at an
        # internal address afterwards (DNS rebinding / TOCTOU). Re-check here, in
        # the worker, immediately before any outbound network I/O.
        try:
            _validate_webhook_url(hook.url)
        except ValueError as exc:
            _worker_logger.warning(
                "Webhook delivery blocked by SSRF guard: hook_id=%s url=%r reason=%s",
                hook.id, hook.url, exc,
            )
            db.add(WebhookDelivery(
                webhook_id=hook.id, event=event, payload=body[:10000],
                status_code=None, response=None, success=False,
                error=f"blocked: unsafe destination ({exc})"[:500],
            ))
            db.commit()
            return {"skipped": True, "blocked": True, "reason": "unsafe_destination"}

        try:
            headers = {
                "Content-Type": "application/json",
                "User-Agent": "Contecflow-Webhooks/1.0",
                "X-Contecflow-Event": event,
            }
            if hook.secret:
                secret = decrypt_value(hook.secret) or hook.secret
                headers["X-Contecflow-Signature"] = _sign_payload(secret, body)

            start = time.time()
            with httpx.Client(timeout=10.0) as client:
                resp = client.post(hook.url, content=body, headers=headers)
            duration_ms = int((time.time() - start) * 1000)
            status_code = resp.status_code
            response_text = resp.text[:500]
            success = 200 <= resp.status_code < 300

        except httpx.HTTPError as exc:
            error = str(exc)[:500]
            http_exc = exc
        except Exception as exc:
            error = str(exc)[:500]

        # Log every attempt — including failed ones — before deciding to retry.
        delivery = WebhookDelivery(
            webhook_id=hook.id,
            event=event,
            payload=body[:10000],
            status_code=status_code,
            response=response_text,
            success=success,
            error=error,
            duration_ms=duration_ms,
        )
        db.add(delivery)
        hook.total_deliveries = (hook.total_deliveries or 0) + 1
        hook.last_triggered_at = datetime.now(timezone.utc)

        if success:
            # Cualquier entrega correcta reinicia el contador del cortacircuitos.
            hook.consecutive_failures = 0
        else:
            hook.failed_deliveries = (hook.failed_deliveries or 0) + 1
            hook.consecutive_failures = (hook.consecutive_failures or 0) + 1
            _aplicar_cortacircuitos(hook)

        db.commit()

        # Retry transient failures with fixed exponential backoff schedule.
        # Only retry if the circuit breaker has not tripped (hook still active after commit).
        should_retry = (
            hook.is_active
            and (
                http_exc is not None
                or (status_code in transient_statuses)
            )
        )
        if should_retry:
            if self.request.retries < len(retry_schedule):
                countdown = retry_schedule[self.request.retries]
                retry_reason = http_exc or RuntimeError(f"HTTP {status_code}")
                _worker_logger.warning(
                    "Webhook %s transient failure (attempt %d/%d), retrying in %ds: %s",
                    webhook_id,
                    self.request.retries + 1,
                    self.max_retries + 1,
                    countdown,
                    retry_reason,
                )
                raise self.retry(exc=retry_reason, countdown=countdown)
            _worker_logger.error(
                "Webhook %s transient failure exhausted retries (attempt %d/%d). Last status=%s error=%s",
                webhook_id,
                self.request.retries + 1,
                self.max_retries + 1,
                status_code,
                error,
            )

        return {"success": success, "status_code": status_code, "suspended": not hook.is_active}


@celery_app.task(name="app.worker.run_alert_engine")
def run_alert_engine():
    from app.db.session import worker_db_session
    from app.services.alert_service import run_alert_engine as _run_alert_engine
    with worker_db_session() as db:
        return _run_alert_engine(db)


@celery_app.task(name="app.worker.run_perf_reminders")
def run_perf_reminders():
    """Recordatorios de evaluaciones de desempeno pendientes.

    Auditoria 2026-11: solo estaba en APScheduler; con Celery beat (el modo de
    ejecucion unica) no corria nunca.
    """
    from app.services.perf_reminder_service import run_perf_reminders_job
    run_perf_reminders_job()


@celery_app.task(name="app.worker.check_missing_imputations")
def check_missing_imputations():
    """Aviso a quien no ha imputado sus horas de hoy.

    «Hoy» es el día de CADA empleado, no el del servidor (auditoría 2026-08,
    P2-14). Antes esta tarea calculaba un único `date.today()` y además cortaba
    en seco los fines de semana con `today.weekday() >= 5`, así que en el sábado
    del servidor **nadie recibía aviso** — incluidos los empleados en zonas donde
    todavía era viernes por la tarde. Ahora la zona se resuelve por empleado y el
    descarte de fin de semana también, que es lo que el aviso quiere decir.
    """
    from sqlalchemy import func

    from app.core import timeutil
    from app.core.timeutil import using_zone, zone_for_user
    from app.db.session import worker_db_session
    from app.models.imputation import Imputation
    from app.models.user import User, UserRole, UserStatus

    with worker_db_session() as db:
        employees = db.query(User).filter(
            User.is_active.is_(True),
            User.status == UserStatus.active,
            User.role == UserRole.employee,
        ).all()

        # Las organizaciones se cachean: sin esto sería una consulta por empleado
        # sólo para leer su zona.
        orgs: dict = {}

        def _org(org_id):
            if org_id and org_id not in orgs:
                from app.models.mfa import Organization

                orgs[org_id] = db.query(Organization).filter(
                    Organization.id == org_id
                ).first()
            return orgs.get(org_id)

        missing = []
        for emp in employees:
            zona = zone_for_user(emp, _org(getattr(emp, "organization_id", None)))
            with using_zone(zona):
                hoy = timeutil.today()
                if hoy.weekday() >= 5:  # su fin de semana, no el del servidor
                    continue
                # Capacidad diaria = capacidad semanal / 5 días laborables
                daily_capacity = (
                    emp.weekly_capacity_hours or settings.DEFAULT_WEEKLY_CAPACITY_HOURS
                ) / 5
                hours_today = db.query(func.sum(Imputation.hours)).filter(
                    Imputation.user_id == emp.id,
                    Imputation.date == hoy,
                ).scalar() or 0.0
                if hours_today < daily_capacity:
                    missing.append(emp.email)

        return {"missing_today": len(missing), "users": missing}


@celery_app.task(name="app.worker.send_weekly_report")
def send_weekly_report():
    """Send weekly load summary to managers."""
    from app.db.session import worker_db_session
    from app.models.user import User, UserRole
    with worker_db_session() as db:
        admins = db.query(User).filter(
            User.role.in_([UserRole.admin, UserRole.hr]),
            User.is_active == True,
        ).all()
        # Here you would generate and send the report
        return {"report_sent_to": [u.email for u in admins]}


@celery_app.task(name="app.worker.generate_retainer_invoices")
def generate_retainer_invoices():
    """
    Auto-generate monthly invoices for recurring_retainer projects.
    Runs daily; only creates an invoice if today matches project.retainer_day
    and no invoice has been created this month yet.

    El día se resuelve en la zona del CLIENTE del proyecto (auditoría 2026-08,
    P2-14). Con un único `date.today()` del servidor, un proyecto con
    `retainer_day = 1` y cliente en Asia se facturaba el día equivocado: cuando
    para el cliente es ya día 1, para un servidor en UTC todavía es día 30, así
    que la comparación `retainer_day != today.day` fallaba ese día y acertaba al
    siguiente. El mes de `period_from` tenía el mismo desfase.
    """
    import uuid
    from datetime import date

    from app.core import timeutil
    from app.core.timeutil import using_zone, zone_for_client
    from app.db.session import worker_db_session
    from app.models.billing_reports import Invoice, InvoiceStatus
    from app.models.project import Project

    generated = []
    with worker_db_session() as db:
        retainer_projects = db.query(Project).filter(
            Project.billing_type == "recurring_retainer",
            Project.retainer_amount != None,
            Project.retainer_day != None,
            Project.is_billable == True,
        ).all()

        # Cachés: sin ellas serían dos consultas por proyecto sólo para la zona.
        clientes: dict = {}
        orgs: dict = {}

        def _zona_de(proj):
            # `app.models.client` no existe: el modulo es `clients`, en
            # plural. Al ser un importe diferido no reventaba al arrancar —
            # fallaba cuando alguien llamaba a esta funcion. Auditoria 2026-08.
            from app.models.clients import Client
            from app.models.mfa import Organization

            cid = getattr(proj, "client_id", None)
            if cid and cid not in clientes:
                clientes[cid] = db.query(Client).filter(Client.id == cid).first()
            oid = getattr(proj, "organization_id", None)
            if oid and oid not in orgs:
                orgs[oid] = db.query(Organization).filter(Organization.id == oid).first()
            return zone_for_client(clientes.get(cid), orgs.get(oid))

        for proj in retainer_projects:
            # El `with` se acota a resolver el día porque es lo único del cuerpo
            # que depende de la zona: `next_numbered_code` fija su año en UTC de
            # forma explícita y no lee el contexto. Ese año de la numeración se
            # deja como está a propósito — cambiarlo desplazaría secuencias de
            # numeración de facturas ya emitidas, que es un asunto contable, no
            # una corrección de zona horaria.
            with using_zone(_zona_de(proj)):
                today = timeutil.today()
            if proj.retainer_day != today.day:
                continue
            # Evitar facturas duplicadas este mes
            try:
                existing = db.query(Invoice).filter(
                    Invoice.project_id == proj.id,
                    Invoice.period_from >= date(today.year, today.month, 1),
                ).first()
                if existing:
                    continue

                # Generate invoice number via the locked numbering service
                from app.services.numbering import next_numbered_code
                inv_number = next_numbered_code(
                    db,
                    "invoice",
                    prefix="INV",
                    padding=4,
                    include_year=True,
                    reset_yearly=True,
                    year_separator="-",
                )

                # Obtener datos del cliente si están disponibles
                client_name = getattr(proj, "client_name", None)
                client_email = getattr(proj, "client_email", None)
                client_address = getattr(proj, "client_address", None)
                # Si el proyecto no tiene estos datos, intentar obtenerlos del cliente
                if not all([client_name, client_email, client_address]) and proj.client_id:
                    # Idem que arriba: el modulo es `clients`, en plural.
                    from app.models.clients import Client
                    client = db.query(Client).filter(Client.id == proj.client_id).first()
                    if client:
                        client_name = client_name or getattr(client, "name", None)
                        client_email = client_email or getattr(client, "email", None)
                        client_address = client_address or getattr(client, "address", None)
                inv = Invoice(
                    id=str(uuid.uuid4()),
                    number=inv_number,
                    project_id=proj.id,
                    client_id=proj.client_id,
                    client_name=client_name,
                    client_email=client_email,
                    client_address=client_address,
                    total=proj.retainer_amount,
                    currency=proj.currency or settings.DEFAULT_CURRENCY,
                    issue_date=today,
                    period_from=date(today.year, today.month, 1),
                    period_to=today,
                    status=InvoiceStatus.draft,
                    notes=f"Retainer mensual automático — {today.strftime('%B %Y')}",
                )
                db.add(inv)
                generated.append(proj.code)
            except Exception as inv_err:
                import logging
                logging.getLogger(__name__).error(f"Retainer invoice error for {proj.code}: {inv_err}")

        db.commit()
        return {"generated": generated, "count": len(generated)}


@celery_app.task(name="app.worker.run_scheduled_reports")
def run_scheduled_reports():
    """Execute due scheduled reports. Called every hour."""
    from app.services.scheduled_reports import run_due_reports
    run_due_reports()
    return {"ok": True}


@celery_app.task(name="app.worker.run_scheduled_rotation")
def run_scheduled_rotation():
    """Execute key material rotation checks on schedule."""
    from app.services.key_management import run_scheduled_rotation as _run
    _run()
    return {"ok": True}


@celery_app.task(
    name="app.worker.run_agent_task",
    bind=True,
    max_retries=0,
    time_limit=settings.CELERY_AGENT_TASK_TIME_LIMIT,
    soft_time_limit=settings.CELERY_AGENT_TASK_SOFT_TIME_LIMIT,
)
def run_agent_task(
    self,
    execution_id: str,
    instruction: str,
    user_id: str,
    auto_approve: bool = False,
):
    """
    Run the ContecflowAgent agentic loop in a Celery worker.
    Writes results back to AIAgentExecution.  Called by run_agent() via .delay().
    """
    import json
    import time
    from datetime import datetime, timezone

    from app.db.session import worker_db_session
    from app.models.ai_chat import AIAgentExecution, AIAgentStep
    from app.models.user import User
    from app.core.config import settings
    from app.services.ai_chat_service import (
        execute_tool as _execute_tool,
        AGENT_TOOLS,
        build_agent_system_prompt as _build_agent_system_prompt,
        log_action as _log_action,
    )
    from app.services.ai_client import (
        get_api_key as _api_key,
    )

    with worker_db_session() as db:
        execution = None
        step_num = 0
        result_summary = ""

        try:
            execution = db.query(AIAgentExecution).filter(
                AIAgentExecution.id == execution_id
            ).first()
            if not execution:
                return {"error": "execution not found"}

            current_user = db.query(User).filter(User.id == user_id).first()
            if not current_user:
                execution.status = "failed"
                execution.error = "User not found"
                db.commit()
                return {"error": "user not found"}

            execution.status = "running"
            db.commit()

            t0 = time.time()
            SYSTEM = _build_agent_system_prompt(db, current_user)

            # `get_default_provider` esta en el SERVICIO, no en el endpoint: el
            # modulo de endpoints no lo define y este import fallaba en cada
            # ejecucion de agente. De paso desaparece una dependencia del
            # worker hacia la capa de API, que no deberia existir.
            # Auditoria 2026-08.
            from app.services.ai_provider_service import get_default_provider as _gdp
            from app.services.ai_provider_service import call_ai
            from app.services import ai_tools as _herr
            from app.core.encryption import decrypt_value

            active_prov = _gdp(db)
            # Auditoria 2026-09: esto preguntaba por la MARCA —«es anthropic?»—
            # y con cualquier otro proveedor el agente no ejecutaba nada. Ahora
            # pregunta por la CAPACIDAD; la traduccion de dialectos vive en
            # `app.services.ai_tools`.
            agent_proveedor = (active_prov.provider if active_prov else "anthropic")
            # La clave viaja cifrada venga de la base o del entorno, y
            # `decrypt_value` deja intacto lo que no lo este. Antes se pasaba
            # TAL CUAL: con un proveedor guardado desde la interfaz, eso mandaba
            # el cifrado `v2:...` como API key.
            agent_clave = (
                decrypt_value(active_prov.api_key) if (active_prov and active_prov.api_key)
                else _api_key()
            )
            agent_base_url = (getattr(active_prov, "api_base_url", "") or "") if active_prov else ""
            if not agent_base_url and agent_proveedor in _herr.FAMILIA_OPENAI:
                agent_base_url = _herr.base_url_por_defecto(agent_proveedor)

            has_anthropic_tools = bool(
                _herr.soporta_herramientas(agent_proveedor) and agent_clave
            )

            if not has_anthropic_tools:
                try:
                    result_summary = call_ai(
                        db,
                        messages=[{"role": "user", "content": instruction}],
                        system=SYSTEM + "\n\nNota: ejecuta un análisis y plan de acción sin usar herramientas reales.",
                        module="contecflowagent", user_id=user_id, max_tokens=800,
                    )
                except Exception:
                    result_summary = (
                        f"⚠ Sin proveedor IA configurado. Instrucción recibida: *{instruction}*\n\n"
                        f"Configura un proveedor en IA & Conectores para ejecutar instrucciones reales."
                    )
                execution.status = "done"
                execution.result = result_summary
                execution.completed_at = datetime.now(timezone.utc)
                _log_action(db, current_user.id, "contecflowagent", "execute",
                            instruction[:200], result_summary[:200], status="success")
                db.commit()
                return {"ok": True}

            agent_api_key = agent_clave
            agent_model = (
                (active_prov.default_model if active_prov else None)
                or settings.CONTECFLOW_AI_MODEL
            )

            # Loop centralizado (item #54). Antes este loop estaba duplicado
            # respecto al SSE endpoint en ai_chat.py. El endpoint mantiene su
            # versión inline por necesidad de yield mid-iteration; aquí (Celery
            # background, sin streaming) usamos el helper directamente.
            from app.services.ai_chat.agent_loop import run_tool_use_loop
            from app.services.ai_chat.tool_execution_service import WRITE_ACTION_TOOLS

            def _persist_step(step_data: dict):
                tool_result = step_data["output"]
                step = AIAgentStep(
                    execution_id=execution.id,
                    step_number=step_data["step"],
                    tool_name=step_data["tool"],
                    tool_input=json.dumps(step_data["input"]),
                    tool_output=json.dumps(tool_result),
                    status="done" if "error" not in tool_result else "failed",
                )
                db.add(step)
                db.flush()

            result_summary, _steps, step_num = run_tool_use_loop(
                execute_tool=_execute_tool,
                instruction=instruction,
                system=SYSTEM,
                tools=AGENT_TOOLS,
                db=db,
                current_user=current_user,
                model=agent_model,
                api_key=agent_api_key,
                max_tokens=4096,
                max_steps=20,
                auto_approve=bool(auto_approve),
                write_action_tools=WRITE_ACTION_TOOLS,
                on_step_done=_persist_step,
                provider=agent_proveedor,
                base_url=agent_base_url,
            )

            latency = int((time.time() - t0) * 1000)
            execution.status = "done"
            execution.result = result_summary
            execution.steps_count = step_num
            execution.completed_at = datetime.now(timezone.utc)
            _log_action(db, current_user.id, "contecflowagent", "execute",
                        instruction[:200], result_summary[:200],
                        tokens=0, latency=latency, status="success")
            db.commit()
            return {"ok": True, "steps": step_num}

        except Exception as exc:
            if execution:
                execution.status = "failed"
                execution.error = str(exc)[:500]
                execution.completed_at = datetime.now(timezone.utc)
                try:
                    db.commit()
                except Exception:
                    db.rollback()
            raise


@celery_app.task(name="app.worker.jira_periodic_sync")
def jira_periodic_sync():
    """
    Periodically pull updated Jira issues into local tasks.

    Runs every 30 minutes (configured in beat_schedule).  For each integration
    setting that has Jira configured, fetches issues updated in the last hour so
    the window overlaps between runs and avoids gaps.
    """
    import logging
    import datetime
    import httpx

    from app.db.session import worker_db_session
    from app.models.settings import AppSetting
    from app.models.task import Task, TaskStatus, TaskPriority
    import uuid

    log = logging.getLogger(__name__)
    synced = 0
    errors = 0

    PRIORITY_MAP = {
        "Highest": TaskPriority.critical,
        "High": TaskPriority.high,
        "Medium": TaskPriority.medium,
        "Low": TaskPriority.low,
        "Lowest": TaskPriority.low,
    }
    STATUS_MAP = {
        "To Do": TaskStatus.todo,
        "In Progress": TaskStatus.in_progress,
        "Done": TaskStatus.done,
        "In Review": TaskStatus.in_review,
        "Blocked": TaskStatus.blocked,
    }

    def _jira_headers(email: str, token: str) -> dict:
        import base64
        creds = base64.b64encode(f"{email}:{token}".encode()).decode()
        return {"Authorization": f"Basic {creds}", "Content-Type": "application/json"}

    with worker_db_session() as db:
        def _get(key):
            # Worker has no request context; read only global (org-independent) settings.
            row = db.query(AppSetting).filter(
                AppSetting.key == key, AppSetting.organization_id.is_(None)
            ).first()
            return (row.value or "").strip() if row else ""

        try:
            jira_url   = _get("jira_url").rstrip("/")
            jira_email = _get("jira_email")
            jira_token = _get("jira_api_token")
            project_key = _get("jira_project_key")

            if not all([jira_url, jira_email, jira_token, project_key]):
                return {"skipped": "Jira not configured or incomplete configuration"}

            # Fetch issues updated in the last 65 minutes (overlap buffer)
            cutoff = (utcnow() - datetime.timedelta(minutes=65)).strftime("%Y-%m-%d %H:%M")
            jql = f"project = {project_key} AND updated >= '{cutoff}' ORDER BY updated DESC"

            resp = httpx.post(
                f"{jira_url}/rest/api/3/issue/search",
                headers=_jira_headers(jira_email, jira_token),
                json={"jql": jql, "maxResults": 100,
                      "fields": ["summary", "status", "priority", "description",
                                  "duedate", "assignee", "issuetype", "labels"]},
                timeout=25,
            )
            resp.raise_for_status()
            issues = resp.json().get("issues", [])

            for issue in issues:
                try:
                    key = issue["key"]
                    fields = issue.get("fields", {})
                    title = fields.get("summary", key)
                    status_name = (fields.get("status") or {}).get("name", "To Do")
                    priority_name = (fields.get("priority") or {}).get("name", "Medium")
                    due_raw = fields.get("duedate")
                    due_date = datetime.date.fromisoformat(due_raw) if due_raw else None

                    task_status = STATUS_MAP.get(status_name, TaskStatus.todo)
                    task_priority = PRIORITY_MAP.get(priority_name, TaskPriority.medium)

                    existing = db.query(Task).filter(Task.jira_issue_key == key).first()
                    if existing:
                        existing.title = title
                        existing.status = task_status
                        existing.priority = task_priority
                        if due_date:
                            existing.due_date = due_date
                        synced += 1
                    else:
                        new_task = Task(
                            id=str(uuid.uuid4()),
                            title=title,
                            status=task_status,
                            priority=task_priority,
                            due_date=due_date,
                            jira_issue_key=key,
                        )
                        db.add(new_task)
                        synced += 1
                except Exception as task_err:
                    log.warning(f"Jira sync: skipped issue {issue.get('key', '?')}: {task_err}")
                    errors += 1

            db.commit()
            log.info(f"Jira periodic sync: {synced} issues synced, {errors} errors")
            return {"synced": synced, "errors": errors}

        except Exception as exc:
            log.error(f"Jira periodic sync failed: {exc}")
            db.rollback()
            raise


@celery_app.task(name="app.worker.process_approval_timeouts")
def process_approval_timeouts():
    """
    Scan all pending ApprovalRequests and fire timeout actions for overdue steps.

    Runs every hour (configured in beat_schedule).  For each step that has
    exceeded its timeout_hours, applies on_timeout: escalate | auto_approve | reject.
    """
    from app.db.session import worker_db_session
    from app.services.approval_engine import process_approval_timeouts as _process

    with worker_db_session() as db:
        result = _process(db)
        return result


@celery_app.task(name="app.worker.revenue_monthly_recognition")
def revenue_monthly_recognition():
    """
    ASC 606 / IFRS 15 monthly recognition batch.
    Runs on the 1st of each month at 02:00 UTC.
    Processes over_time, consumption, and straight_line contracts for the
    previous calendar month across all organizations.
    Milestone-method contracts are skipped (recognized on milestone completion).
    """
    from app.core.timeutil import resolve_zone, today_in
    from app.db.session import worker_db_session
    from app.services.revenue_service import run_monthly_recognition

    with worker_db_session() as db:
        from app.models.mfa import Organization

        organizaciones = db.query(Organization).filter(
            Organization.is_active.is_(True)
        ).all()

        resultados = {}
        for org in organizaciones:
            hoy = today_in(resolve_zone(getattr(org, "timezone", None)))
            # Sólo se reconoce cuando es día 1 EN SU zona. La tarea corre a diario
            # a propósito: con la ejecución mensual a las 02:00 UTC del día 1, una
            # organización en UTC−6 estaba todavía en el día 31 del mes anterior,
            # así que su «mes anterior» salía desplazado un mes y ese periodo no
            # se reconocía nunca. Repartir el disparo por zonas es lo que da
            # exactamente una ejecución correcta por organización y mes.
            if hoy.day != 1:
                continue
            if hoy.month == 1:
                year, month = hoy.year - 1, 12
            else:
                year, month = hoy.year, hoy.month - 1

            # El lote es idempotente (revenue_service._ya_reconocido + el índice
            # único de la revisión 091), así que un disparo repetido no duplica
            # ingresos. Antes sí lo hacía.
            resultados[org.id] = run_monthly_recognition(
                db, year, month, organization_id=org.id
            )

        if resultados:
            _worker_logger.info(
                "ASC 606: reconocido para %d organizaciones: %s",
                len(resultados), resultados,
            )
        return resultados


@celery_app.task(name="app.worker.olap_nightly_etl")
def olap_nightly_etl():
    """
    Nightly incremental ETL: PostgreSQL → DuckDB OLAP star schema.
    Runs at 01:00 UTC. Loads last 2 days of imputations + full dim/fact refresh.
    Pass since=date(2023,1,1) in a manual call for a full historical load.
    """
    from app.db.session import worker_db_session
    from app.services.olap.etl import run_full_etl

    with worker_db_session() as db:
        result = run_full_etl(db)
        _worker_logger.info("OLAP ETL result: %s", result)
        return result


@celery_app.task(name="app.worker.ml_model_retrain")
def ml_model_retrain():
    """
    Retrain overrun prediction ML models for all active organizations.
    Runs on the 1st of each month at 03:00 UTC, after revenue recognition.
    Skips orgs with fewer than MIN_TRAINING_SAMPLES completed projects.
    Requires scikit-learn; skips gracefully if not available.
    """
    from app.db.session import worker_db_session
    from app.services.ml_trainer import train_all_orgs

    with worker_db_session() as db:
        results = train_all_orgs(db)
        trained = sum(1 for r in results if r.get("status") == "trained")
        skipped = sum(1 for r in results if r.get("status") == "skipped")
        _worker_logger.info("ML retrain: %d trained, %d skipped", trained, skipped)
        return {"trained": trained, "skipped": skipped, "results": results}


# ── Fase 1 ITSM Tasks ─────────────────────────────────────────────────────────

@celery_app.task(name="app.worker.sla_breach_scan")
def sla_breach_scan():
    """Vigila el SLA: guarda el estado, avisa del riesgo y del incumplimiento, y escala.

    Auditoria 2026-11: antes solo contaba los tickets en riesgo y lo dejaba en
    el log. Ver `sla_monitor_service`.
    """
    from app.db.session import worker_db_session
    from app.services.service_desk.sla_monitor_service import escanear

    with worker_db_session() as db:
        resultado = escanear(db)
        _worker_logger.info("SLA: %s", resultado)
        return resultado


@celery_app.task(name="app.worker.sd_leer_buzones")
def sd_leer_buzones():
    """Lee el buzon de soporte de cada organizacion (IMAP o Microsoft 365)."""
    from app.db.session import worker_db_session
    from app.services.service_desk.buzones import leer_todos

    with worker_db_session() as db:
        resultado = leer_todos(db)
        _worker_logger.info("Buzones de soporte: %s", resultado)
        return resultado


@celery_app.task(name="app.worker.sd_procesar_eventos_de_ticket")
def sd_procesar_eventos_de_ticket():
    """Procesa la bandeja de eventos de ticket: avisos, correo, webhooks y flujos.

    La encola cada `commit` que deja eventos (`ticket_events._tras_confirmar`);
    la entrada del beat es la red para cuando el broker no estaba.
    """
    from app.db.session import worker_db_session
    from app.services.service_desk.ticket_event_processor import procesar_pendientes

    with worker_db_session() as db:
        return procesar_pendientes(db)


@celery_app.task(name="app.worker.automations_procesar_eventos")
def automations_procesar_eventos():
    """Ejecuta las reglas de los eventos anotados (`automation_events`)."""
    from app.db.session import worker_db_session
    from app.services.automation_events import procesar_pendientes

    with worker_db_session() as db:
        return procesar_pendientes(db)


@celery_app.task(name="app.worker.automations_escanear")
def automations_escanear():
    """Disparadores de fecha y umbral: tareas vencidas o que vencen, presupuesto, partes."""
    from app.db.session import worker_db_session
    from app.services.automations_service import escanear

    with worker_db_session() as db:
        return escanear(db)


@celery_app.task(name="app.worker.bpmn_vencer_temporizadores")
def bpmn_vencer_temporizadores():
    """Despierta los temporizadores BPMN vencidos y sigue cada instancia."""
    from app.db.session import worker_db_session
    from app.services.bpmn_engine import vencer_temporizadores

    with worker_db_session() as db:
        return vencer_temporizadores(db)


@celery_app.task(name="app.worker.problem_auto_detect")
def problem_auto_detect():
    """Auto-detect recurring incident clusters and create Problem records.

    Runs every hour at :05. Uses detect_recurring_incidents() to find clusters
    of >=3 open incidents in the same category+priority within 24h, then calls
    create_problem_from_correlation() to create a Problem + AI RCA suggestion.
    """
    from app.db.session import worker_db_session
    from app.services.service_desk.incident_intelligence_service import (
        detect_recurring_incidents,
    )
    from app.services.service_desk.problem_service import create_problem_from_correlation

    with worker_db_session() as db:
        problems_created = 0
        try:
            clusters = detect_recurring_incidents(db)
            _worker_logger.info("Problem auto-detect: %d clusters found", len(clusters))

            for cluster in clusters:
                try:
                    problem = create_problem_from_correlation(
                        db=db,
                        ticket_ids=cluster["ticket_ids"],
                        category=cluster["category"],
                        priority=cluster["priority"],
                        auto_rca=True,
                    )
                    db.commit()
                    _worker_logger.info(
                        "Auto-created problem %s for category=%s priority=%s (%d tickets)",
                        problem.number,
                        cluster["category"],
                        cluster["priority"],
                        len(cluster["ticket_ids"]),
                    )
                    problems_created += 1
                except Exception as exc:
                    db.rollback()
                    _worker_logger.error("Failed to create problem for cluster %s: %s", cluster, exc)

            return {"clusters_found": len(clusters), "problems_created": problems_created}
        except Exception as exc:
            _worker_logger.error("problem_auto_detect error: %s", exc)
            return {"error": str(exc)}


@celery_app.task(name="app.worker.kedb_expiry_scan")
def kedb_expiry_scan():
    """ITSM-P02: Demote expired KEDB entries back to investigating.

    Runs daily at 06:30. Any Known Error entry whose kedb_expires_at has passed
    is returned to 'investigating' status so it gets re-reviewed before republishing.
    """
    from app.db.session import worker_db_session
    from app.services.service_desk.known_error_service import run_kedb_expiry_scan

    with worker_db_session() as db:
        try:
            result = run_kedb_expiry_scan(db)
            db.commit()
            _worker_logger.info("KEDB expiry scan: %d entries expired", result.get("expired", 0))
            return result
        except Exception as exc:
            db.rollback()
            _worker_logger.error("kedb_expiry_scan error: %s", exc)
            return {"error": str(exc)}


@celery_app.task(name="app.worker.kedb_effectiveness_scan")
def kedb_effectiveness_scan():
    """ITSM-P02: Recompute effectiveness scores for all KEDB entries.

    Runs daily at 07:00. For each Known Error computes the percentage of linked
    tickets that were resolved after the entry was published (proxy for workaround
    effectiveness) and persists the score.
    """
    from app.db.session import worker_db_session
    from app.services.service_desk.known_error_service import run_kedb_effectiveness_scan

    with worker_db_session() as db:
        try:
            result = run_kedb_effectiveness_scan(db)
            db.commit()
            _worker_logger.info("KEDB effectiveness scan: %d entries updated", result.get("updated", 0))
            return result
        except Exception as exc:
            db.rollback()
            _worker_logger.error("kedb_effectiveness_scan error: %s", exc)
            return {"error": str(exc)}


@celery_app.task(name="app.worker.alert_correlation_scan")
def alert_correlation_scan():
    """ITSM-P03: Cluster open alerts and auto-create Problems for high-confidence groups.

    Runs every 30 minutes. Clusters open tickets by CI + category + temporal proximity
    + semantic similarity. Automatically creates Problem records for clusters with
    correlation_score >= 0.65 and size >= 3 that are not already linked to a Problem.
    """
    from app.db.session import worker_db_session
    from app.services.service_desk.alert_correlation_service import run_correlation_scan_job

    with worker_db_session() as db:
        try:
            result = run_correlation_scan_job(db)
            _worker_logger.info(
                "Alert correlation scan: %d clusters, %d problems created, %d errors",
                result.get("clusters_found", 0),
                result.get("problems_created", 0),
                result.get("errors", 0),
            )
            return result
        except Exception as exc:
            _worker_logger.error("alert_correlation_scan error: %s", exc)
            return {"error": str(exc)}


@celery_app.task(name="app.worker.cmdb_discovery_run")
def cmdb_discovery_run():
    """Run CMDB auto-discovery for providers whose scan window has expired (ITSM-P04).

    Runs every 15 minutes via beat schedule. Only executes providers where
    next_run_at <= now, respecting per-provider scan_interval_minutes cadence.
    Detects config drift, writes CMDBChangelog entries, and updates next_run_at.
    """
    from app.db.session import worker_db_session
    from app.services.service_desk.cmdb_discovery_service import (
        run_due_discoveries,
    )

    with worker_db_session() as db:
        try:
            results = run_due_discoveries(db)
            _worker_logger.info("CMDB discovery run: %d providers due/processed", len(results))
            drifted = sum(1 for r in results if r.get("drift_detected") and r.get("updated", 0) > 0)
            if drifted:
                _worker_logger.warning("CMDB drift detected in %d provider scan(s)", drifted)
            return {"providers_run": len(results), "results": results}
        except Exception as exc:
            _worker_logger.error("cmdb_discovery_run error: %s", exc)
            return {"error": str(exc)}


@celery_app.task(name="app.worker.change_impact_batch_score")
def change_impact_batch_score():
    """Batch-score Change Requests that haven't been analyzed yet (ITSM-P05).

    Targets changes pending CAB decision with no auto_risk_score.
    Also auto-approves standard changes with low risk score.
    Runs every 10 minutes via beat schedule.

    Auditoria 2026-08: esta tarea referenciaba `ChangeStatus.in_approval`, que
    **no existe en el enum del modelo**, asi que **fallaba en cada tic** con un
    `AttributeError` atrapado por el `except` de abajo — una linea de log y
    nada mas. Los estados que espera el CAB salen ahora de
    `ESTADOS_PENDIENTES_DE_CAB`, que se construye desde el enum. El detalle
    esta en el comentario de esa constante.
    """
    from app.db.session import worker_db_session
    from app.models.service_desk import ITSMChangeRequest
    from app.services.service_desk.change_impact_service import (
        ESTADOS_PENDIENTES_DE_CAB, score_and_persist,
    )
    from app.services.service_desk.change_service import _maybe_auto_approve

    scored = auto_approved = errors = 0
    with worker_db_session() as db:
        try:
            pending = (
                db.query(ITSMChangeRequest)
                .filter(
                    ITSMChangeRequest.status.in_(ESTADOS_PENDIENTES_DE_CAB),
                    ITSMChangeRequest.auto_risk_score.is_(None),
                )
                .limit(50)  # process up to 50 per tick to avoid long task
                .all()
            )
            for change in pending:
                try:
                    score_and_persist(db, change.id)
                    if _maybe_auto_approve(db, change, system_user_id="system-batch-score"):
                        auto_approved += 1
                    db.commit()
                    scored += 1
                except Exception as exc:
                    db.rollback()
                    errors += 1
                    _worker_logger.warning(
                        "change_impact_batch_score: failed for %s: %s", change.id, exc
                    )

            _worker_logger.info(
                "change_impact_batch_score: scored=%d auto_approved=%d errors=%d",
                scored, auto_approved, errors,
            )
            return {"scored": scored, "auto_approved": auto_approved, "errors": errors}
        except Exception as exc:
            _worker_logger.error("change_impact_batch_score error: %s", exc)
            return {"error": str(exc)}


@celery_app.task(name="app.worker.routing_outcome_scan")
def routing_outcome_scan():
    """Fill in routing outcome data for recently closed tickets (ITSM-P07).

    Finds RoutingFeedback rows missing outcome_recorded_at and backfills
    resolution_minutes + csat_score from the linked Ticket.
    Runs every hour via beat schedule.
    """
    from app.db.session import worker_db_session
    from app.services.service_desk.ml_routing_service import run_outcome_scan

    with worker_db_session() as db:
        try:
            result = run_outcome_scan(db)
            _worker_logger.info(
                "routing_outcome_scan: processed=%d updated=%d errors=%d",
                result.get("processed", 0), result.get("updated", 0), result.get("errors", 0),
            )
            return result
        except Exception as exc:
            _worker_logger.error("routing_outcome_scan error: %s", exc)
            return {"error": str(exc)}


@celery_app.task(name="app.worker.predictive_scan")
def predictive_scan():
    """Run predictive intelligence scan on all open tickets.

    Computes escalation risk, severity label, and predicted resolution time.
    Runs every 30 minutes via beat schedule.
    """
    from app.db.session import worker_db_session
    from app.services.service_desk.predictive_analytics_service import (
        run_predictive_scan,
    )

    with worker_db_session() as db:
        try:
            result = run_predictive_scan(db)
            _worker_logger.info(
                "Predictive scan: processed=%d predicted=%d",
                result.get("processed", 0),
                result.get("predicted", 0),
            )
            return result
        except Exception as exc:
            _worker_logger.error("predictive_scan error: %s", exc)
            return {"error": str(exc)}


@celery_app.task(name="app.worker.predictive_model_eval_retrain")
def predictive_model_eval_retrain():
    """Evaluate ITSM/BI predictive model health and trigger conditional retraining.

    Runs every 6 hours. Uses quality and staleness thresholds to avoid blind retrains.
    """
    from app.db.session import worker_db_session
    from app.services.predictive_retraining_service import run_periodic_evaluation_and_retraining

    with worker_db_session() as db:
        try:
            result = run_periodic_evaluation_and_retraining(db)
            _worker_logger.info(
                "predictive_model_eval_retrain: orgs=%d itsm_retrained=%d bi_retrained=%d",
                result.get("organizations", 0),
                result.get("itsm_retrained", 0),
                result.get("bi_retrained", 0),
            )
            return result
        except Exception as exc:
            _worker_logger.error("predictive_model_eval_retrain error: %s", exc)
            return {"error": str(exc)}


@celery_app.task(
    bind=True,
    name="app.worker.sync_connector_data",
    max_retries=3,
    default_retry_delay=120,
)
def sync_connector_data(self, connector_id: str, org_id: str | None = None):
    """Celery task: sync external data for a BI ETL connector.

    Implements the roadmap pattern:
        get_connector_config → get_connector_class → authenticate →
        extract → transform → load → log_sync

    If *org_id* is None, iterates all organizations that have the connector
    enabled (same pattern as jira_periodic_sync). Per-connector beat schedule
    entries call this with only connector_id; manual invocations may pass
    a specific org_id.
    """
    import logging

    from app.db.session import worker_db_session
    from app.services.bi_intelligence_service import (
        CONNECTORS_KEY,
        get_connectors,
        CONNECTOR_CONFIGS_KEY,
        _get_json,
    )
    from app.integrations import bi_etl_connectors

    log = logging.getLogger(__name__)
    results = []

    with worker_db_session() as db:
        try:
            # Determine which org_ids to process
            if org_id:
                org_ids = [org_id]
            else:
                # Collect all orgs that have this connector enabled in their state blob
                from app.models.settings import AppSetting
                rows = db.query(AppSetting).filter(
                    AppSetting.key == CONNECTORS_KEY,
                ).all()
                org_ids = [str(row.organization_id) if row.organization_id else None for row in rows]
                if not org_ids:
                    org_ids = [None]  # global / single-tenant

            for oid in org_ids:
                try:
                    state = get_connectors(db, organization_id=oid)
                    if connector_id not in state:
                        log.debug("sync_connector_data: %s not in state for org=%s, skipping", connector_id, oid)
                        continue
                    if not state[connector_id].get("enabled"):
                        log.debug("sync_connector_data: %s disabled for org=%s, skipping", connector_id, oid)
                        continue

                    configs = _get_json(db, CONNECTOR_CONFIGS_KEY, oid, default={})
                    cfg = configs.get(connector_id, {})

                    connector = bi_etl_connectors.get_connector(connector_id)
                    result = connector.run_sync(config=cfg, organization_id=oid, db=db)

                    # Mirror state back to bi_intelligence connectors blob
                    row = state[connector_id]
                    row["last_sync_at"] = result.get("finished_at")
                    row["last_records"] = result.get("records_ingested", 0)
                    row["status"] = "connected" if result.get("ok") else "error"
                    state[connector_id] = row
                    from app.services.bi_intelligence_service import _set_json as _bi_set_json, CONNECTORS_KEY
                    _bi_set_json(db, CONNECTORS_KEY, oid, state, "BI Intelligence connectors state (JSON)")

                    results.append({"org_id": oid, **result})
                    log.info(
                        "sync_connector_data: connector=%s org=%s ok=%s records=%d",
                        connector_id, oid, result.get("ok"), result.get("records_ingested", 0),
                    )
                except Exception as exc:
                    log.warning("sync_connector_data: error for connector=%s org=%s: %s", connector_id, oid, exc)
                    results.append({"org_id": oid, "ok": False, "error": str(exc)})

            return {"connector_id": connector_id, "orgs_processed": len(org_ids), "results": results}

        except Exception as exc:
            log.error("sync_connector_data fatal error connector=%s: %s", connector_id, exc)
            try:
                raise self.retry(exc=exc)
            except self.MaxRetriesExceededError:
                return {"error": str(exc), "connector_id": connector_id}


@celery_app.task(name="app.worker.asset_expiry_scan")
def asset_expiry_scan():
    """Un ticket de renovacion por activo de ALM que vence pronto.

    «Pronto» es `SD_ASSET_REFRESH_DAYS` de cada organizacion. Corre a diario a
    las 07:05. La logica esta en `alm_ciclo_de_vida.escanear_vencimientos`.
    """
    from app.db.session import worker_db_session
    from app.services.alm_ciclo_de_vida import escanear_vencimientos

    with worker_db_session() as db:
        try:
            resultado = escanear_vencimientos(db)
            db.commit()
            _worker_logger.info("Asset expiry scan: %s", resultado)
            return resultado
        except Exception as exc:
            db.rollback()
            _worker_logger.error("asset_expiry_scan error: %s", exc)
            return {"error": str(exc)}


@celery_app.task(name="app.worker.analytics_snapshot")
def analytics_snapshot():
    """Persist hourly ITSM KPI snapshot for trend analytics (Phase 3).

    Computes 24h rolling metrics and writes to sd_itsm_metric_snapshots.
    Runs every hour at :50.
    """
    from app.db.session import worker_db_session
    from app.services.service_desk.analytics_service import persist_metric_snapshot

    with worker_db_session() as db:
        try:
            result = persist_metric_snapshot(db)
            _worker_logger.info(
                "Analytics snapshot saved: tickets=%d sla=%.1f%%",
                result.get("tickets_total", 0),
                result.get("sla_compliance_pct", 0),
            )
            return result
        except Exception as exc:
            _worker_logger.error("analytics_snapshot error: %s", exc)
            return {"error": str(exc)}


@celery_app.task(name="app.worker.catalog_popularity_update")
def catalog_popularity_update():
    """Recalculate service catalog popularity scores (Phase 3).

    Writes popularity_score to ServiceItem based on last 4 weeks of ticket volume.
    Runs every 6 hours.
    """
    from app.db.session import worker_db_session
    from app.services.service_desk.smart_catalog_service import update_service_popularity

    with worker_db_session() as db:
        try:
            result = update_service_popularity(db)
            db.commit()
            _worker_logger.info(
                "Catalog popularity updated: %d services", result.get("updated", 0)
            )
            return result
        except Exception as exc:
            db.rollback()
            _worker_logger.error("catalog_popularity_update error: %s", exc)
            return {"error": str(exc)}


@celery_app.task(name="app.worker.compliance_check")
def compliance_check():
    """Run full ITIL/ISO 20000 compliance audit and persist report (Phase 3).

    Runs weekly on Mondays at 06:00.
    """
    from app.db.session import worker_db_session
    from app.services.service_desk.governance_compliance_service import schedule_compliance_check

    with worker_db_session() as db:
        try:
            result = schedule_compliance_check(db)
            _worker_logger.info(
                "Compliance check complete: score=%d CMM=%d findings=%d",
                result.get("overall_score", 0),
                result.get("cmm_level", 0),
                result.get("findings_count", 0),
            )
            return result
        except Exception as exc:
            _worker_logger.error("compliance_check error: %s", exc)
            return {"error": str(exc)}


# ── BI Phase 2 Celery tasks ────────────────────────────────────────────────────

@celery_app.task(name="app.worker.bi_scheduled_delivery_run")
def bi_scheduled_delivery_run():
    """Evaluate and run all due BI report delivery schedules (Slack / Teams / Email / PDF / Excel).

    Runs every hour at :45.
    """
    from app.db.session import worker_db_session
    from app.services.bi_report_delivery_service import run_due_deliveries

    with worker_db_session() as db:
        try:
            result = run_due_deliveries(db)
            _worker_logger.info(
                "BI delivery run: %d delivered, %d errors",
                result.get("total_run", 0),
                result.get("total_errors", 0),
            )
            return result
        except Exception as exc:
            _worker_logger.error("bi_scheduled_delivery_run error: %s", exc)
            return {"error": str(exc)}


@celery_app.task(name="app.worker.bi_kpi_push")
def bi_kpi_push():
    """Compute fresh KPI snapshot for each active org and publish to Redis BI channel.

    Subscribed WebSocket clients receive the snapshot without polling.
    Runs every 5 minutes.
    """
    from app.db.session import worker_db_session
    from app.models.settings import AppSetting
    from app.services.bi_intelligence_service import (
        CONNECTORS_KEY,
        ml_forecast_revenue,
        ml_detect_revenue_anomalies,
        publish_kpi_snapshot,
    )

    pushed = 0
    with worker_db_session() as db:
        try:
            # Collect distinct org IDs that have BI connector state
            org_ids = [
                row.organization_id
                for row in db.query(AppSetting.organization_id)
                .filter(AppSetting.key == CONNECTORS_KEY)
                .distinct()
                .all()
            ]
            org_ids = list({oid for oid in org_ids})  # deduplicate (includes None)
            if not org_ids:
                org_ids = [None]

            for org_id in org_ids:
                try:
                    forecast = ml_forecast_revenue(db, organization_id=org_id, months_ahead=3)
                    anomalies = ml_detect_revenue_anomalies(db, organization_id=org_id, z_threshold=2.0)
                    snapshot = {
                        "type": "bi_kpi_snapshot",
                        "organization_id": org_id,
                        "forecast_head": forecast.get("forecast", [])[:3],
                        "anomaly_count": len(anomalies.get("items", [])),
                        "generated_at": forecast.get("generated_at"),
                    }
                    publish_kpi_snapshot(org_id, snapshot)
                    pushed += 1
                except Exception as exc:
                    _worker_logger.debug("bi_kpi_push skip [org=%s]: %s", org_id, exc)

            _worker_logger.info("bi_kpi_push: pushed %d org snapshots", pushed)
            return {"pushed": pushed}
        except Exception as exc:
            _worker_logger.error("bi_kpi_push error: %s", exc)
            return {"error": str(exc)}


@celery_app.task(name="app.worker.bi_ml_retrain")
def bi_ml_retrain():
    """Refresh ML model training data stored as AppSetting JSON blobs.

    Logs retraining stats per org. The actual model artifacts are ephemeral
    (recomputed on demand); this task pre-warms the history series cache.
    Runs weekly on Sundays at 03:30.
    """
    from app.db.session import worker_db_session
    from app.models.settings import AppSetting
    from app.services.bi_intelligence_service import CONNECTORS_KEY, ml_detect_anomalies_multivariate

    retrained = 0
    with worker_db_session() as db:
        try:
            org_ids = list({
                row.organization_id
                for row in db.query(AppSetting.organization_id)
                .filter(AppSetting.key == CONNECTORS_KEY)
                .distinct()
                .all()
            })
            if not org_ids:
                org_ids = [None]
            for org_id in org_ids:
                try:
                    # Run anomaly detection to exercise IsolationForest training path
                    ml_detect_anomalies_multivariate(db, organization_id=org_id, contamination=0.1)
                    retrained += 1
                except Exception as exc:
                    _worker_logger.debug("bi_ml_retrain skip [org=%s]: %s", org_id, exc)

            _worker_logger.info("bi_ml_retrain: warmed models for %d orgs", retrained)
            return {"retrained": retrained}
        except Exception as exc:
            _worker_logger.error("bi_ml_retrain error: %s", exc)
            return {"error": str(exc)}


# ── ITSM Fase 3 — Autonomous Agent scan ──────────────────────────────────────

@celery_app.task(name="app.worker.autonomous_agent_scan")
def autonomous_agent_scan():
    """Process all newly created open tickets with the autonomous agent.

    Runs every 5 minutes. Tickets eligible for autonomous resolution are
    handled immediately; others receive playbook-assisted first responses.
    """
    from app.db.session import worker_db_session
    from app.services.service_desk.autonomous_agent_service import run_autonomous_scan

    with worker_db_session() as db:
        try:
            result = run_autonomous_scan(db)
            _worker_logger.info(
                "autonomous_agent_scan: evaluated=%d auto_resolved=%d assisted=%d skipped=%d",
                result.get("evaluated", 0),
                result.get("auto_resolved", 0),
                result.get("assisted", 0),
                result.get("skipped", 0),
            )
            return result
        except Exception as exc:
            _worker_logger.error("autonomous_agent_scan error: %s", exc)
            return {"error": str(exc)}

