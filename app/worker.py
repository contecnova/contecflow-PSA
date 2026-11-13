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
    # Recordatorio de la campaña de presupuestos (revisión 2026-11)
    "budget-campaign-reminder": {
        "task": "app.worker.recordar_campana_de_presupuestos",
        "schedule": crontab(hour=8, minute=30),
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
        "schedule": crontab(hour=settings.KEY_ROTATION_RUN_HOUR, minute=17),
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
    # organizaciones al oeste de UTC: a las 02:00 del día 1 en Madrid, en UTC−6 es
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
        "schedule": crontab(hour=2, minute=0),  # a diario a las 02:00 de DEFAULT_TIMEZONE
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
    # Revision multitenant 2026-11: borra las empresas cuya cuarentena de baja vencio.
    "purgar-empresas-caducadas": {
        "task": "app.worker.purgar_empresas_caducadas",
        "schedule": crontab(hour=2, minute=40),
    },
    # Tipos de cambio del BCE (auditoria 2026-11: EXCHANGE_RATES_AUTO_UPDATE se
    # editaba en Ajustes y no habia ningun trabajo que lo leyera).
    "actualizar-tipos-de-cambio": {
        "task": "app.worker.actualizar_tipos_de_cambio",
        "schedule": crontab(hour=16, minute=30),  # el BCE publica hacia las 16:00 CET
    },
    # Retención y bloqueo legal (revisión 2026-11).
    "aplicar-retencion": {
        "task": "app.worker.aplicar_retencion",
        "schedule": crontab(hour=2, minute=55),
    },
    # Registro de llamadas de los conectores contecmind/contecintelligence (revisión 2026-11).
    "purgar-registro-de-conectores": {
        "task": "app.worker.purgar_registro_de_conectores",
        "schedule": crontab(hour=3, minute=5),
    },
    # Resumen diario de avisos: corre cada hora; cada usuario lo recibe una vez
    # al día a partir de NOTIFICATIONS_DIGEST_HOUR en su zona (revisión 2026-11).
    "resumen-diario-de-avisos": {
        "task": "app.worker.resumen_diario_de_avisos",
        "schedule": crontab(minute=5),
    },
    # Base de conocimiento: artículos caducados y contradictorios (revisión 2026-11).
    "kb-calidad": {
        "task": "app.worker.kb_pasada_de_calidad",
        "schedule": crontab(hour=3, minute=10),
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
    # ── Conectores ETL de BI (revisión 2026-11) ───────────────────────────────
    # Una entrada que recorre lo activo de cada organización. Antes eran 21
    # fijas, una por proveedor, que no incluían las fuentes REST de nadie.
    "bi-connector-sync": {
        "task": "app.worker.sincronizar_conectores_etl",
        "schedule": crontab(minute=1),
    },
}

celery_app.conf.timezone = settings.DEFAULT_TIMEZONE

import logging as _logging
_worker_logger = _logging.getLogger(__name__)

# Los cambios de ticket que hace el worker (escalado, flujos) tambien pasan por
# la bandeja de eventos: registra sus escuchadores en la sesion.
import app.services.service_desk.ticket_events  # noqa: F401,E402
import app.services.automation_events  # noqa: F401,E402
import app.services.preferencias_de_aviso  # noqa: F401,E402


# ── Reglas de las tareas (segunda auditoria 2026-11, #33 y #37) ──────────────
#
# Cada tarea es un envoltorio: la logica vive en `app/services`. Y cada tarea
# esta en UNA de estas cuatro formas de tratar la organizacion (lo comprueba
# `tests/test_auditoria_2026_11_arquitectura_c2.py`):
#
#   · por organizacion: `en_cada_organizacion` corre el trabajo una vez por
#     organizacion activa, con su sesion y su contexto de tenant publicado;
#   · por sujeto: el contexto es el del usuario, webhook u organizacion que
#     llega como argumento;
#   · por fila: el servicio recorre filas de varias organizaciones y publica la
#     de cada fila (`como_organizacion`) antes de tocarla;
#   · global: mantenimiento de plataforma, entre organizaciones por diseño.
#
# Un fallo no se devuelve como `{"error": ...}` (Celery lo marcaba SUCCESS, sin
# reintento ni traza): se registra con su traza y se relanza.

#: Mantenimiento de plataforma: no hay una organizacion a la que pertenezca.
TAREAS_GLOBALES = {
    "app.worker.run_scheduled_rotation": "rota el material de claves de la plataforma",
    "app.worker.olap_nightly_etl": "reconstruye el almacen OLAP de todas las organizaciones "
                                   "(cada hecho lleva su organizacion como dimension)",
    "app.worker.sincronizar_conectores_etl": "solo reparte: lee los pares (organizacion, conector) "
                                             "activos y encola `sync_connector_data` con su organizacion",
    "app.worker.purgar_empresas_caducadas": "borra organizaciones enteras cuya baja vencio",
    "app.worker.actualizar_tipos_de_cambio": "tipos del BCE: filas globales (sin organizacion) que ven todas",
    "app.worker.purgar_registro_de_conectores": "retencion tecnica del registro de llamadas, por antiguedad",
}

#: El contexto lo da el argumento de la tarea.
TAREAS_POR_SUJETO = {
    "app.worker.deliver_webhook": "la organizacion del webhook (`entrega_de_webhooks`)",
    "app.worker.ejecutar_en_segundo_plano": "la organizacion con la que se encolo "
                                            "(`segundo_plano._ejecutar_con_contexto`)",
    "app.worker.run_agent_task": "el usuario que pidio la ejecucion (`publicar_contexto_de_tenant`)",
    "app.worker.sync_connector_data": "la organizacion del conector (`como_organizacion`)",
}

#: El servicio publica la organizacion de cada fila que procesa.
TAREAS_POR_FILA = {
    "app.worker.process_approval_timeouts": "app.services.approval_engine.timeouts",
    "app.worker.sd_procesar_eventos_de_ticket": "app.services.service_desk.ticket_event_processor",
    "app.worker.automations_procesar_eventos": "app.services.automation_events",
    "app.worker.automations_escanear": "app.services.automations_service.disparo",
    "app.worker.bpmn_vencer_temporizadores": "app.services.bpmn_engine",
    "app.worker.sd_leer_buzones": "app.services.service_desk.inbound_mail",
    "app.worker.kb_pasada_de_calidad": "app.services.service_desk.kb_calidad",
}


def _por_organizacion(tarea: str, trabajo, **kw):
    from app.services.trabajos_de_fondo import en_cada_organizacion
    return en_cada_organizacion(tarea, trabajo, **kw)


# ── Por sujeto ────────────────────────────────────────────────────────────────

@celery_app.task(bind=True, name="app.worker.deliver_webhook", max_retries=3)
def deliver_webhook_task(self, webhook_id: int, body: str, event: str):
    """Entrega un webhook; reintenta los fallos transitorios a los 60 s, 300 s y 1800 s."""
    from app.services.entrega_de_webhooks import entregar_webhook

    resultado = entregar_webhook(webhook_id, body, event, intento=self.request.retries)
    if "reintentar_en" in resultado:
        raise self.retry(exc=resultado.pop("motivo"), countdown=resultado["reintentar_en"])
    return resultado


@celery_app.task(name="app.worker.ejecutar_en_segundo_plano")
def ejecutar_en_segundo_plano(ruta: str, args: list, kwargs: dict):
    """Ejecuta lo que `app.core.segundo_plano.encolar` saco de una peticion."""
    from app.core.segundo_plano import resolver
    return resolver(ruta)(*args, **kwargs)


@celery_app.task(
    name="app.worker.run_agent_task",
    bind=True,
    max_retries=0,
    time_limit=settings.CELERY_AGENT_TASK_TIME_LIMIT,
    soft_time_limit=settings.CELERY_AGENT_TASK_SOFT_TIME_LIMIT,
)
def run_agent_task(self, execution_id: str, instruction: str, user_id: str, auto_approve: bool = False):
    """NexusAgent en segundo plano, en la empresa de quien lo pidio."""
    from app.services.ai_chat.agente_en_segundo_plano import ejecutar_agente
    return ejecutar_agente(execution_id, instruction, user_id, auto_approve)


@celery_app.task(name="app.worker.sync_connector_data")
def sync_connector_data(connector_id: str, org_id: str | None = None):
    """Sincroniza un conector ETL de BI de una organización.

    El resultado (registros o el error) queda en su estado y en su registro;
    la pantalla lo enseña tal cual.
    """
    from app.db.session import worker_db_session
    from app.services import bi_etl_service
    from app.services.service_desk.ticket_events import como_organizacion

    with worker_db_session() as db, como_organizacion(db, org_id):
        try:
            r = bi_etl_service.sincronizar(db, org_id, connector_id)
        except (LookupError, ValueError) as exc:
            # Quitado o desactivado desde la ultima pasada: no es un fallo.
            _worker_logger.info("Conector %s de %s omitido: %s", connector_id, org_id, exc)
            return {"connector_id": connector_id, "org_id": org_id, "ok": False, "error": str(exc)}
        return {"org_id": org_id, **r}


# ── Por organizacion ─────────────────────────────────────────────────────────

@celery_app.task(name="app.worker.run_alert_engine")
def run_alert_engine():
    from app.services.alert_service import run_alert_engine as _alertas
    return _por_organizacion("run_alert_engine", lambda db, org: _alertas(db))


@celery_app.task(name="app.worker.run_perf_reminders")
def run_perf_reminders():
    """Recordatorios de evaluaciones de desempeño pendientes."""
    from app.services.perf_reminder_service import send_pending_review_reminders
    return _por_organizacion("run_perf_reminders", lambda db, org: send_pending_review_reminders(db))


@celery_app.task(name="app.worker.check_missing_imputations")
def check_missing_imputations():
    """Quien no ha imputado sus horas de hoy (el «hoy» de cada empleado)."""
    from app.services.trabajos_de_fondo import imputaciones_pendientes_de_hoy
    return _por_organizacion("check_missing_imputations", imputaciones_pendientes_de_hoy)


@celery_app.task(name="app.worker.generate_retainer_invoices")
def generate_retainer_invoices():
    """Facturas mensuales de los proyectos `recurring_retainer` (dia en la zona del cliente)."""
    from app.services.trabajos_de_fondo import generar_facturas_de_retainer
    return _por_organizacion("generate_retainer_invoices", generar_facturas_de_retainer)


@celery_app.task(name="app.worker.run_scheduled_reports")
def run_scheduled_reports():
    """Informes programados vencidos. Cada hora."""
    from app.services.scheduled_reports import ejecutar_informes_vencidos
    return _por_organizacion("run_scheduled_reports", lambda db, org: ejecutar_informes_vencidos(db))


@celery_app.task(name="app.worker.jira_periodic_sync")
def jira_periodic_sync():
    """Trae las incidencias de Jira actualizadas, organizacion a organizacion.

    Auditoria 2026-11 (#14): cada organizacion con su configuracion; la global
    (sin organizacion) no se sincroniza: no hay a que organizacion asignar sus
    tareas.
    """
    from app.db.session import worker_db_session
    from app.services import jira_service

    with worker_db_session() as db:
        organizaciones = jira_service.organizaciones_con_jira(db)
    if not organizaciones:
        return {"skipped": "Jira not configured for any organization"}
    r = _por_organizacion("jira_periodic_sync", jira_service.sincronizar_organizacion,
                          organizaciones=organizaciones)
    porg = r["por_organizacion"].values()
    return {"synced": sum(x.get("synced", 0) for x in porg),
            "errors": sum(x.get("errors", 0) for x in porg),
            "organizations": r["organizaciones"]}


@celery_app.task(name="app.worker.revenue_monthly_recognition")
def revenue_monthly_recognition():
    """ASC 606 / IFRS 15: a diario; reconoce el mes anterior donde es dia 1 en su zona."""
    from app.services.trabajos_de_fondo import reconocer_ingresos_si_es_dia_1
    return _por_organizacion("revenue_monthly_recognition", reconocer_ingresos_si_es_dia_1)


@celery_app.task(name="app.worker.ml_model_retrain")
def ml_model_retrain():
    """Reentrena el modelo de sobrecoste de cada organizacion (dia 1, 03:00)."""
    from app.services.ml_trainer import train_model
    return _por_organizacion("ml_model_retrain", train_model)


@celery_app.task(name="app.worker.sla_breach_scan")
def sla_breach_scan():
    """Estado del SLA, avisos de riesgo e incumplimiento, y escalado."""
    from app.services.service_desk.sla_monitor_service import escanear
    return _por_organizacion("sla_breach_scan", lambda db, org: escanear(db))


@celery_app.task(name="app.worker.problem_auto_detect")
def problem_auto_detect():
    """Un Problem (con RCA de IA, gobernada por la organizacion) por grupo de incidentes repetidos."""
    from app.services.trabajos_de_fondo import crear_problemas_recurrentes
    return _por_organizacion("problem_auto_detect", crear_problemas_recurrentes)


@celery_app.task(name="app.worker.kedb_expiry_scan")
def kedb_expiry_scan():
    """ITSM-P02: los errores conocidos caducados vuelven a investigacion."""
    from app.services.service_desk.known_error_service import run_kedb_expiry_scan
    return _por_organizacion("kedb_expiry_scan", lambda db, org: run_kedb_expiry_scan(db))


@celery_app.task(name="app.worker.kedb_effectiveness_scan")
def kedb_effectiveness_scan():
    """ITSM-P02: recalcula la efectividad de cada error conocido."""
    from app.services.service_desk.known_error_service import run_kedb_effectiveness_scan
    return _por_organizacion("kedb_effectiveness_scan", lambda db, org: run_kedb_effectiveness_scan(db))


@celery_app.task(name="app.worker.alert_correlation_scan")
def alert_correlation_scan():
    """ITSM-P03: agrupa alertas abiertas y crea Problems para los grupos claros."""
    from app.services.service_desk.alert_correlation_service import run_correlation_scan_job
    return _por_organizacion("alert_correlation_scan",
                             lambda db, org: run_correlation_scan_job(db, organization_id=org))


@celery_app.task(name="app.worker.cmdb_discovery_run")
def cmdb_discovery_run():
    """ITSM-P04: discovery de la CMDB para los proveedores cuya ventana vencio."""
    from app.services.service_desk.cmdb_discovery_service import run_due_discoveries
    return _por_organizacion("cmdb_discovery_run", lambda db, org: run_due_discoveries(db))


@celery_app.task(name="app.worker.change_impact_batch_score")
def change_impact_batch_score():
    """ITSM-P05: puntua los cambios pendientes de CAB; aprueba los estandar de bajo riesgo."""
    from app.services.trabajos_de_fondo import puntuar_cambios_pendientes
    return _por_organizacion("change_impact_batch_score", puntuar_cambios_pendientes)


@celery_app.task(name="app.worker.routing_outcome_scan")
def routing_outcome_scan():
    """ITSM-P07: completa el resultado de las asignaciones de tickets cerrados."""
    from app.services.service_desk.ml_routing_service import run_outcome_scan
    return _por_organizacion("routing_outcome_scan", lambda db, org: run_outcome_scan(db))


@celery_app.task(name="app.worker.predictive_scan")
def predictive_scan():
    """Riesgo de escalado, severidad y tiempo de resolucion previsto de los tickets abiertos."""
    from app.services.service_desk.predictive_analytics_service import run_predictive_scan
    return _por_organizacion("predictive_scan", lambda db, org: run_predictive_scan(db))


@celery_app.task(name="app.worker.predictive_model_eval_retrain")
def predictive_model_eval_retrain():
    """Salud de los modelos predictivos y reentreno condicional; el resumen queda global."""
    from app.db.session import worker_db_session
    from app.services.predictive_retraining_service import (
        evaluar_y_reentrenar_organizacion, guardar_resumen_de_evaluacion,
    )
    r = _por_organizacion("predictive_model_eval_retrain", evaluar_y_reentrenar_organizacion)
    with worker_db_session() as db:
        resumen = guardar_resumen_de_evaluacion(db, list(r["por_organizacion"].values()))
    return {k: resumen[k] for k in ("organizations", "itsm_retrained", "bi_retrained")}


@celery_app.task(name="app.worker.asset_expiry_scan")
def asset_expiry_scan():
    """Un ticket de renovacion por activo de ALM que vence pronto (`SD_ASSET_REFRESH_DAYS`)."""
    from app.services.alm_ciclo_de_vida import escanear_vencimientos
    return _por_organizacion("asset_expiry_scan", lambda db, org: escanear_vencimientos(db))


@celery_app.task(name="app.worker.analytics_snapshot")
def analytics_snapshot():
    """Instantanea horaria de KPIs ITSM de cada organizacion con tickets."""
    from app.services.trabajos_de_fondo import instantanea_itsm
    return _por_organizacion("analytics_snapshot", instantanea_itsm)


@celery_app.task(name="app.worker.compliance_check")
def compliance_check():
    """Auditoria ITIL/ISO 20000 semanal: un informe por organizacion, guardado en ella."""
    from app.services.service_desk.governance_compliance_service import schedule_compliance_check
    return _por_organizacion("compliance_check", lambda db, org: schedule_compliance_check(db))


@celery_app.task(name="app.worker.bi_scheduled_delivery_run")
def bi_scheduled_delivery_run():
    """Entregas programadas de BI vencidas (Slack / Teams / correo / PDF / Excel)."""
    from app.services.bi_report_delivery_service import run_due_deliveries
    return _por_organizacion("bi_scheduled_delivery_run", lambda db, org: run_due_deliveries(db))


@celery_app.task(name="app.worker.bi_kpi_push")
def bi_kpi_push():
    """KPIs de BI de cada organizacion al canal de Redis. Cada 5 minutos."""
    from app.services.trabajos_de_fondo import publicar_kpis_de_bi
    return _por_organizacion("bi_kpi_push", publicar_kpis_de_bi)


@celery_app.task(name="app.worker.aplicar_retencion")
def aplicar_retencion():
    """Politicas de retencion activas de cada empresa (respetan el bloqueo legal)."""
    from app.services.retencion import aplicar
    return _por_organizacion("aplicar_retencion", aplicar)


@celery_app.task(name="app.worker.resumen_diario_de_avisos")
def resumen_diario_de_avisos():
    """Un correo al dia con lo no leido, a quien lo tenga activado."""
    from app.services.resumen_de_avisos import enviar
    return _por_organizacion("resumen_diario_de_avisos", lambda db, org: {"enviados": enviar(db)})


@celery_app.task(name="app.worker.bi_ml_retrain")
def bi_ml_retrain():
    """Precalienta los modelos de anomalias de BI de cada organizacion (domingos 03:30)."""
    from app.services.trabajos_de_fondo import calentar_modelos_de_bi
    return _por_organizacion("bi_ml_retrain", calentar_modelos_de_bi)


@celery_app.task(name="app.worker.autonomous_agent_scan")
def autonomous_agent_scan():
    """Agente autonomo sobre los tickets nuevos: resuelve o deja una primera respuesta."""
    from app.services.service_desk.autonomous_agent_service import run_autonomous_scan
    return _por_organizacion("autonomous_agent_scan", lambda db, org: run_autonomous_scan(db))


@celery_app.task(name="app.worker.recordar_campana_de_presupuestos")
def recordar_campana_de_presupuestos():
    """Avisa a los responsables de presupuestos sin enviar cuando cierra su campaña."""
    from app.services.presupuestos_preparar import recordar_campana
    return _por_organizacion("recordar_campana_de_presupuestos", lambda db, org: {"avisos": recordar_campana(db)})


# ── Por fila (el servicio publica la organizacion de cada fila) ──────────────

def _en_sesion(funcion):
    from app.db.session import worker_db_session
    with worker_db_session() as db:
        return funcion(db)


@celery_app.task(name="app.worker.process_approval_timeouts")
def process_approval_timeouts():
    """Acciones de vencimiento (escalar, aprobar, rechazar) de los pasos de aprobacion caducados."""
    from app.services.approval_engine import process_approval_timeouts as _vencer
    return _en_sesion(_vencer)


@celery_app.task(name="app.worker.sd_leer_buzones")
def sd_leer_buzones():
    """Lee el buzon de soporte de cada organizacion (IMAP o Microsoft 365)."""
    from app.services.service_desk.buzones import leer_todos
    # Un buzon que falla no para a los demas: `leer_todos` deja su traza
    # (`logger.exception`) y su error en el resultado de esa organizacion.
    return _en_sesion(leer_todos)


@celery_app.task(name="app.worker.sd_procesar_eventos_de_ticket")
def sd_procesar_eventos_de_ticket():
    """Bandeja de eventos de ticket: avisos, correo, webhooks y flujos (red del encolado al confirmar)."""
    from app.services.service_desk.ticket_event_processor import procesar_pendientes
    return _en_sesion(procesar_pendientes)


@celery_app.task(name="app.worker.automations_procesar_eventos")
def automations_procesar_eventos():
    """Ejecuta las reglas de los eventos anotados (`automation_events`)."""
    from app.services.automation_events import procesar_pendientes
    return _en_sesion(procesar_pendientes)


@celery_app.task(name="app.worker.automations_escanear")
def automations_escanear():
    """Disparadores de fecha y umbral: tareas vencidas o que vencen, presupuesto, partes."""
    from app.services.automations_service import escanear
    return _en_sesion(escanear)


@celery_app.task(name="app.worker.bpmn_vencer_temporizadores")
def bpmn_vencer_temporizadores():
    """Despierta los temporizadores BPMN vencidos y sigue cada instancia."""
    from app.services.bpmn_engine import vencer_temporizadores
    return _en_sesion(vencer_temporizadores)


@celery_app.task(name="app.worker.kb_pasada_de_calidad")
def kb_pasada_de_calidad():
    """Avisa de articulos sin revisar y de pares que se contradicen."""
    from app.services.service_desk.kb_calidad import pasada_diaria
    return _en_sesion(pasada_diaria)


# ── Globales ──────────────────────────────────────────────────────────────────

@celery_app.task(name="app.worker.run_scheduled_rotation")
def run_scheduled_rotation():
    """Rotacion programada del material de claves."""
    from app.services.key_management import run_scheduled_rotation as _rotar
    _rotar()
    return {"ok": True}


@celery_app.task(name="app.worker.olap_nightly_etl")
def olap_nightly_etl():
    """ETL nocturno PostgreSQL -> DuckDB (01:00). Ultimos 2 dias de imputaciones y dimensiones."""
    from app.services.olap.etl import run_full_etl
    return _en_sesion(run_full_etl)


@celery_app.task(name="app.worker.sincronizar_conectores_etl")
def sincronizar_conectores_etl():
    """Lanza una sincronización por cada conector activo de cada organización."""
    from app.db.session import sin_filtro_de_tenant, worker_db_session
    from app.services import bi_etl_service

    with worker_db_session() as db, sin_filtro_de_tenant(db):
        pares = bi_etl_service.activos(db)
    for org_id, connector_id in pares:
        sync_connector_data.delay(connector_id, org_id)
    return {"lanzadas": len(pares)}


@celery_app.task(name="app.worker.purgar_empresas_caducadas")
def purgar_empresas_caducadas():
    """Borra los datos de las empresas cuya cuarentena de baja ha vencido."""
    from app.services.baja_de_empresa_service import purgar_caducadas_job
    purgar_caducadas_job()


@celery_app.task(name="app.worker.actualizar_tipos_de_cambio")
def actualizar_tipos_de_cambio():
    """Descarga los tipos del BCE si EXCHANGE_RATES_AUTO_UPDATE esta activo."""
    from app.db.session import worker_db_session
    from app.services.exchange_rate_service import sync_ecb_rates
    from app.services.settings_service import get_runtime_bool
    with worker_db_session() as db:
        if not get_runtime_bool(db, "EXCHANGE_RATES_AUTO_UPDATE", default=False):
            return {"skipped": "EXCHANGE_RATES_AUTO_UPDATE desactivado"}
        resultado = sync_ecb_rates(db)
        if not resultado.get("ok"):
            raise RuntimeError(f"tipos de cambio BCE: {resultado}")
        return resultado


@celery_app.task(name="app.worker.purgar_registro_de_conectores")
def purgar_registro_de_conectores():
    """Borra las llamadas a los conectores más antiguas que CONECTOR_LOG_RETENTION_DAYS."""
    from app.services.conectores.estado import purgar
    borradas = _en_sesion(purgar)
    _worker_logger.info("conectores: %s llamadas antiguas borradas", borradas)
    return {"borradas": borradas}
