# Tareas del worker

Referencia de las tareas de fondo. Fuente de verdad: `app/worker.py`
(`celery_app`, `beat_schedule` y las tareas `@celery_app.task`). Revisado contra
el código el 2026-11-23 (59 entradas de `beat_schedule`, 63 tareas `@celery_app.task`); si algo de aquí no coincide con `app/worker.py`, manda
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

  Auditoría 22-11-2026: toda tarea corre como **trabajo de sistema declarado**
  (`app.worker.TareaDeSistema` → `trabajo_de_sistema("tarea:<nombre>")`, también
  cuando APScheduler la llama directamente), así que una sesión del worker sin
  empresa ya no pasa en silencio por el filtro (`app/db/contexto_de_tenant.py`).
  Para trabajar en una empresa, `con_empresa(db, org)` por iteración (lo usa
  `en_cada_organizacion`; no admite `None`). Fuera de una tarea (scripts), una
  sesión sin contexto falla (`TENANT_SESION_SIN_CONTEXTO=cerrar`, defecto desde
  el 23-11-2026): decláralo con `declarar_sistema(db, "motivo")` o
  `fijar_contexto(db, org, "motivo")`. `segundo_plano.encolar` sin Celery corre
  la función dentro de `trabajo_de_sistema("segundo plano: <función>")`.

- **Errores**: un fallo se registra con traza y se relanza (Celery lo marca
  FAILURE); no se devuelve `{"error": ...}`.
- **Métricas**: con APScheduler, `attach_apscheduler_metrics` mide cada trabajo
  (ver `docs/OBSERVABILIDAD.md`).

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
| `perf-reminders-daily` | `run_perf_reminders` | cada 15 min; cada empresa a su `NOTIFICATIONS_PERF_REMINDERS_TIME` local (09:00) | organización | Recordatorios de evaluaciones de desempeño pendientes |
| `run-alert-engine-daily` | `run_alert_engine` | cada 15 min; cada empresa a su `NOTIFICATIONS_ALERTS_TIME` local (08:00) | organización | Motor de alertas |
| `budget-campaign-reminder` | `recordar_campana_de_presupuestos` | cada 15 min; cada empresa a su `NOTIFICATIONS_BUDGET_CAMPAIGN_TIME` local (08:30) | organización | Aviso a responsables con presupuestos sin enviar al cerrar la campaña |
| `check-missing-imputations` | `check_missing_imputations` | cada 15 min; cada empresa a su `NOTIFICATIONS_MISSING_IMPUTATIONS_TIME` local (18:00), a quien ese día trabaja según su horario | organización | Quién no ha imputado horas hoy |
| `generate-retainer-invoices` | `generate_retainer_invoices` | diaria 07:00 | organización | Facturas de proyectos `recurring_retainer` en su día |
| `run-scheduled-reports` | `run_scheduled_reports` | cada hora :00 | organización | Informes programados vencidos |
| `run-key-rotation` | `run_scheduled_rotation` | diaria `KEY_ROTATION_RUN_HOUR`:17 (por defecto 02:17) | global | Rotación del material de claves |
| `jira-periodic-sync` | `jira_periodic_sync` | cada 30 min | organización | Trae incidencias de Jira de las organizaciones con Jira configurado |
| `process-approval-timeouts` | `process_approval_timeouts` | cada hora :00 | fila | Acciones de vencimiento de pasos de aprobación caducados (`app.services.approval_engine`) |
| `revenue-monthly-recognition` | `revenue_monthly_recognition` | diaria 02:00 | organización | ASC 606: reconoce el mes anterior donde es día 1 en su zona (idempotente) |
| `ml-model-retrain` | `ml_model_retrain` | día 1, 03:00 | organización | Reentreno del modelo de sobrecoste |
| `semantic-retrain-profiles` | `semantic_reentrenar` | cada hora :23 | organización | Asignación por IA: reconstruye los perfiles (texto desde el historial + embeddings) cuando la hora UTC es múltiplo de `SEMANTIC_RETRAIN_INTERVAL_HOURS` de la empresa (24 por defecto; 0 lo apaga). 23-11-2026 |
| `olap-nightly-etl` | `olap_nightly_etl` | diaria 01:00 | global | ETL PostgreSQL → DuckDB |
| `sla-breach-scan` | `sla_breach_scan` | cada 5 min | organización | Estado de SLA, avisos de riesgo/incumplimiento y escalado |
| `sd-leer-buzones` | `sd_leer_buzones` | cada 2 min | fila | Buzón de soporte de cada organización (IMAP o Microsoft 365) |
| `sd-ticket-events` | `sd_procesar_eventos_de_ticket` | cada minuto (y al confirmar) | fila | Bandeja de eventos de ticket: avisos, correo, webhooks, flujos |
| `automations-events` | `automations_procesar_eventos` | cada minuto | fila | Reglas de automatización de los eventos anotados |
| `automations-scan` | `automations_escanear` | cada `AUTOMATIONS_SCAN_MINUTES` (15) | fila | Disparadores de fecha y umbral |
| `bpmn-timers` | `bpmn_vencer_temporizadores` | cada minuto | fila | Temporizadores BPMN vencidos |
| `problem-auto-detect` | `problem_auto_detect` | cada hora :05 | organización | Crea Problems por incidentes repetidos |
| `cmdb-discovery` | `cmdb_discovery_run` | cada 15 min | organización | Discovery de CMDB de los proveedores cuya ventana venció |
| `cmdb-software-diario` | `cmdb_software_diario` | diario 04:20 | organización | CMDB de software: avisos (si `auto_sync`), reevaluación de hallazgos y SLA, caducidad de excepciones, ticket automático (docs/CMDB_SOFTWARE_Y_VULNERABILIDADES.md) |
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
| `evm-curva-s-diaria` | `guardar_puntos_de_curva_s` | diaria 02:25 | organización | Un punto diario de la curva S (PV, EV, AC) de cada proyecto activo (migración 173) |
| `externos-caducidad` | `externos_caducidad` | diaria 06:30 | organización | Externos: aviso de fin de acceso, accesos caducados y asignaciones vencidas (migración 178) |
| `seguridad-de-cuentas-diario` | `seguridad_de_cuentas_diario` | diaria 06:40 | organización | Políticas de cuenta (migración 199): desactiva cuentas inactivas, avisa de la caducidad de contraseñas y caduca dispositivos de confianza |
| `alm-altas-y-bajas` | `alm_altas_y_bajas` | diaria 06:50 | organización | Licencias y hardware, fase 4: bajas programadas y fines de contrato, licencias tras la baja y devoluciones |
| `alm-daily` | `alm_daily` | diaria 07:10 | organización | Licencias y hardware: asignaciones vencidas, renovaciones (`auto_renew`, decisiones), preavisos y préstamos |
| `alm-uso-sincronizar` | `alm_uso_sincronizar` | cada hora :35 | organización | Licencias, fase 2: lee cada fuente de uso activa cuyo intervalo (`ALM_USAGE_SYNC_INTERVAL_HOURS`) venció |
| `alm-uso-pasada-diaria` | `alm_uso_pasada_diaria` | diaria 07:40 | organización | Licencias, fase 2: software no controlado en gastos y recuperación de licencias sin uso |
| `reuniones-sondeo` | `reuniones_sondeo` | cada 15 min | organización | Asistente de reuniones: recoge Teams/Meet terminadas, manda bots de calendario y renueva la suscripción de Graph |
| `reuniones-retencion` | `reuniones_retencion` | diaria 03:40 | organización | Asistente de reuniones: borra audio y transcripciones caducados (respeta el bloqueo legal) |
| `demanda-plazos` | `demanda_plazos` | cada hora :10 | organización | Flujo de demanda: avisa al acercarse y al vencer el plazo de cada fase (migración 195) |
| `cert-vencimientos` | `cert_vencimientos` | diaria 07:35 | organización | Certificaciones (migración 212, docs/CERTIFICACIONES.md): avisos de certificados por vencer y auditoría del ciclo, evidencias que caducan y CAPA vencidas (una vez cada uno); evidencia de las tareas enlazadas cerradas |
| `cert-nis2-relojes` | `cert_nis2_relojes` | cada 15 min | organización | Certificaciones: avisos de los relojes NIS2 (6 h antes y al vencer la alerta de 24 h, la notificación de 72 h y el informe final), una vez cada uno |
| `pir-vencidas` | `pir_vencidas` | diaria 07:20 | organización | PIR (migración 206, docs/PIR.md): aviso previo (`aviso_dias_antes`) y aviso de vencida, una vez cada uno, al responsable y al dueño del cambio o PM |

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
