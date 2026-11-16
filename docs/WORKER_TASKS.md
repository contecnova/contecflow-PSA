# Tareas del worker

Referencia de las tareas de fondo. Fuente de verdad: `app/worker.py`
(`celery_app`, `beat_schedule` y las tareas `@celery_app.task`). Revisado contra
el código el 2026-11-16; si algo de aquí no coincide con `app/worker.py`, manda
el código.

## Cómo se ejecutan

- **Celery**: broker y backend de resultados = `REDIS_URL`; todas las tareas
  viven en `app.worker` (`include=["app.worker"]`). Zona horaria del calendario:
  `DEFAULT_TIMEZONE` (por defecto `Europe/Madrid`), no UTC.
- **Dos planificadores, uno solo activo**:
  - `ENABLE_APSCHEDULER=1` (por defecto): APScheduler dentro del proceso de la
    API. `_replicar_celery_beat` (`app/main.py`) registra cada entrada de
    `beat_schedule` con la misma cadencia (id `beat_<clave>`,
    `max_instances=1`, `coalesce=True`) y ejecuta el cuerpo de la tarea en el
    propio proceso. Job store SQLAlchemy sobre `DATABASE_URL`; no da bloqueo
    distribuido entre varios procesos de API.
  - `ENABLE_CELERY_BEAT=1` (alias heredado `CELERY_BEAT`): proceso `celery beat`
    aparte (servicio `beat` de `docker-compose.yml`, singleton) más el servicio
    `worker` (`--concurrency=${WORKER_CONCURRENCY:-4}`). Recomendado en
    producción con más de una réplica de la API.
  - Los dos a la vez: el arranque aborta (`_enforce_scheduler_mode_safety`)
    salvo `FAIL_ON_DUAL_SCHEDULER=0`.
- **Contexto de organización**: cada tarea está en una de cuatro formas,
  declaradas en `app/worker.py` y comprobadas por
  `tests/test_auditoria_2026_11_arquitectura_c2.py`:
  - *por organización*: `en_cada_organizacion` (`app/services/trabajos_de_fondo.py`)
    corre el trabajo una vez por organización activa, con su sesión y su tenant;
  - *por sujeto* (`TAREAS_POR_SUJETO`): el contexto sale del argumento;
  - *por fila* (`TAREAS_POR_FILA`): el servicio publica la organización de cada
    fila que procesa;
  - *global* (`TAREAS_GLOBALES`): mantenimiento de plataforma.
- **Errores**: un fallo se registra con traza y se relanza (Celery lo marca
  FAILURE); no se devuelve `{"error": ...}`.
- **Métricas**: con APScheduler, `attach_apscheduler_metrics` mide cada trabajo
  (ver `docs/OBSERVABILITY_PROMETHEUS.md`).

## Tareas bajo demanda (sin calendario)

| Tarea (nombre Celery) | Forma | Qué hace |
|---|---|---|
| `app.worker.deliver_webhook` (`deliver_webhook_task`) | sujeto | Entrega un webhook; `max_retries=3`, reintentos a 60 s, 300 s y 1800 s |
| `app.worker.ejecutar_en_segundo_plano` | sujeto | Ejecuta lo encolado con `app.core.segundo_plano.encolar` |
| `app.worker.run_agent_task` | sujeto | NexusAgent en segundo plano; `max_retries=0`, `time_limit=CELERY_AGENT_TASK_TIME_LIMIT` (300 s), `soft_time_limit=CELERY_AGENT_TASK_SOFT_TIME_LIMIT` (280 s) |
| `app.worker.sync_connector_data` | sujeto | Sincroniza un conector ETL de BI de una organización (lo encola `sincronizar_conectores_etl`) |

## Calendario (`beat_schedule`)

Horas en `DEFAULT_TIMEZONE`. Día de la semana en notación Celery (0 = domingo).

| Clave beat | Tarea | Cadencia | Forma | Qué hace |
|---|---|---|---|---|
| `perf-reminders-daily` | `run_perf_reminders` | diaria 09:00 | organización | Recordatorios de evaluaciones de desempeño pendientes |
| `run-alert-engine-daily` | `run_alert_engine` | diaria 08:00 | organización | Motor de alertas |
| `budget-campaign-reminder` | `recordar_campana_de_presupuestos` | diaria 08:30 | organización | Aviso a responsables con presupuestos sin enviar al cerrar la campaña |
| `check-missing-imputations` | `check_missing_imputations` | lun–vie 18:00 | organización | Quién no ha imputado horas hoy |
| `generate-retainer-invoices` | `generate_retainer_invoices` | diaria 07:00 | organización | Facturas de proyectos `recurring_retainer` en su día |
| `run-scheduled-reports` | `run_scheduled_reports` | cada hora :00 | organización | Informes programados vencidos |
| `run-key-rotation` | `run_scheduled_rotation` | diaria `KEY_ROTATION_RUN_HOUR`:17 (por defecto 02:17) | global | Rotación del material de claves |
| `jira-periodic-sync` | `jira_periodic_sync` | cada 30 min | organización | Trae incidencias de Jira de las organizaciones con Jira configurado |
| `process-approval-timeouts` | `process_approval_timeouts` | cada hora :00 | fila | Acciones de vencimiento de pasos de aprobación caducados (`app.services.approval_engine`) |
| `revenue-monthly-recognition` | `revenue_monthly_recognition` | diaria 02:00 | organización | ASC 606: reconoce el mes anterior donde es día 1 en su zona (idempotente) |
| `ml-model-retrain` | `ml_model_retrain` | día 1, 03:00 | organización | Reentreno del modelo de sobrecoste |
| `olap-nightly-etl` | `olap_nightly_etl` | diaria 01:00 | global | ETL PostgreSQL → DuckDB |
| `sla-breach-scan` | `sla_breach_scan` | cada 5 min | organización | Estado de SLA, avisos de riesgo/incumplimiento y escalado |
| `sd-leer-buzones` | `sd_leer_buzones` | cada 2 min | fila | Buzón de soporte de cada organización (IMAP o Microsoft 365) |
| `sd-ticket-events` | `sd_procesar_eventos_de_ticket` | cada minuto (y al confirmar) | fila | Bandeja de eventos de ticket: avisos, correo, webhooks, flujos |
| `automations-events` | `automations_procesar_eventos` | cada minuto | fila | Reglas de automatización de los eventos anotados |
| `automations-scan` | `automations_escanear` | cada `AUTOMATIONS_SCAN_MINUTES` (15) | fila | Disparadores de fecha y umbral |
| `bpmn-timers` | `bpmn_vencer_temporizadores` | cada minuto | fila | Temporizadores BPMN vencidos |
| `problem-auto-detect` | `problem_auto_detect` | cada hora :05 | organización | Crea Problems por incidentes repetidos |
| `cmdb-discovery` | `cmdb_discovery_run` | cada 15 min | organización | Discovery de CMDB de los proveedores cuya ventana venció |
| `change-impact-batch-score` | `change_impact_batch_score` | cada 10 min | organización | Puntúa cambios pendientes de CAB |
| `routing-outcome-scan` | `routing_outcome_scan` | cada hora :20 | organización | Resultado de asignaciones de tickets cerrados |
| `predictive-scan` | `predictive_scan` | cada 30 min | organización | Predicciones sobre tickets abiertos |
| `predictive-model-eval-retrain` | `predictive_model_eval_retrain` | cada 6 h, :10 | organización | Salud de modelos predictivos y reentreno condicional |
| `asset-expiry-scan` | `asset_expiry_scan` | diaria 07:05 | organización | Ticket de renovación de activos que vencen (`SD_ASSET_REFRESH_DAYS`) |
| `analytics-snapshot` | `analytics_snapshot` | cada hora :50 | organización | Instantánea de KPIs ITSM |
| `compliance-check` | `compliance_check` | lunes 06:00 | organización | Informe ITIL/ISO 20000 |
| `bi-scheduled-delivery` | `bi_scheduled_delivery_run` | cada hora :45 | organización | Entregas programadas de BI |
| `bi-kpi-push` | `bi_kpi_push` | cada 5 min | organización | KPIs de BI al canal de Redis |
| `bi-ml-retrain` | `bi_ml_retrain` | domingo 03:30 | organización | Precalienta modelos de anomalías de BI |
| `purgar-empresas-caducadas` | `purgar_empresas_caducadas` | diaria 02:40 | global | Borra empresas cuya cuarentena de baja venció |
| `actualizar-tipos-de-cambio` | `actualizar_tipos_de_cambio` | diaria 16:30 | global | Tipos del BCE si `EXCHANGE_RATES_AUTO_UPDATE` está activo |
| `aplicar-retencion` | `aplicar_retencion` | diaria 02:55 | organización | Políticas de retención (respetan el bloqueo legal) |
| `ausencias-pasada-diaria` | `ausencias_pasada_diaria` | diaria 07:10 | organización | Ausencias: repetir, recordar, vencer, escalar, lista de espera |
| `purgar-cache-de-traducciones` | `purgar_cache_de_traducciones` | diaria 03:25 | por empresa | Borra la caché de traducciones sin usar más de `TRANSLATION_CACHE_RETENTION_DAYS` (180; 0: nunca) |
| `purgar-registro-de-conectores` | `purgar_registro_de_conectores` | diaria 03:05 | global | Borra llamadas a conectores más antiguas que `CONECTOR_LOG_RETENTION_DAYS` (30) |
| `resumen-diario-de-avisos` | `resumen_diario_de_avisos` | cada hora :05 | organización | Resumen diario de avisos (una vez al día por usuario desde `NOTIFICATIONS_DIGEST_HOUR`) |
| `kb-calidad` | `kb_pasada_de_calidad` | diaria 03:10 | fila | Artículos sin revisar y pares contradictorios de la KB |
| `autonomous-agent-scan` | `autonomous_agent_scan` | cada 5 min | organización | Agente autónomo sobre tickets nuevos |
| `kedb-expiry-scan` | `kedb_expiry_scan` | diaria 06:30 | organización | Errores conocidos caducados vuelven a investigación |
| `kedb-effectiveness-scan` | `kedb_effectiveness_scan` | diaria 07:00 | organización | Efectividad de cada error conocido |
| `alert-correlation-scan` | `alert_correlation_scan` | cada 30 min | organización | Agrupa alertas abiertas y crea Problems |
| `bi-connector-sync` | `sincronizar_conectores_etl` | cada hora :01 | global | Encola `sync_connector_data` por cada conector ETL activo |

## Límites y reintentos

Solo los declarados en cada tarea: `deliver_webhook` (3 reintentos) y
`run_agent_task` (límites de tiempo de arriba, sin reintentos). El resto no
fija `time_limit` ni `max_retries`: usa los valores por defecto de Celery. No hay
configuración global de `result_expires`, prefetch ni pool en `app/worker.py`.

## Uso manual

```python
from app.worker import run_alert_engine
run_alert_engine.delay()   # por Celery (requiere worker)
run_alert_engine()         # en el propio proceso
```

```bash
celery -A app.worker.celery_app inspect active
celery -A app.worker.celery_app inspect scheduled
```

Añadir una tarea periódica: definirla en `app/worker.py` en una de las cuatro
formas, añadir su entrada en `beat_schedule` y, si es por sujeto, por fila o
global, registrarla en su diccionario (`TAREAS_*`); APScheduler la replica sin tocar `app/main.py`.
