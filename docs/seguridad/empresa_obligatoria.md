# `organization_id` obligatorio (migración 208, 24-11-2026)

## 1. Medición previa (base real en la 207)

- 558 tablas con `organization_id`; **484** lo admitían vacío.
- 13 tablas con filas vacías: `exchange_rates` 12, `audit_logs` 10, `custom_client_industries` 10,
  `custom_expense_categories` 8, `departments` 8, `ai_governance_configs` 7, `app_settings` 5,
  `custom_project_types` 5, `custom_task_statuses` 5, `email_templates` 4, `slack_configs` 1, `budgets` 1,
  `budget_lines` 1.
- Código que creaba filas sin empresa a propósito:
  - la siembra: departamentos antes de crear la empresa; plantillas de correo, Slack, presupuesto y gobernanza de
    IA en una sesión sin empresa;
  - los catálogos y ajustes con valor común (abajo);
  - los trabajos de fondo sin empresa en la sesión, que dependían del sellado.

## 2. Decisión, caso por caso

`organization_id` es NOT NULL en todas las tablas salvo en `TABLAS_SIN_EMPRESA_PERMITIDA`
(`app/db/empresa_obligatoria.py`, con el motivo de cada una). Quedan exceptuadas solo las tablas en las que el
código lee el vacío como «común a todas las empresas»:

| Tablas | Motivo |
|---|---|
| `app_settings`, `settings_audit_log` | Ajustes del despliegue (llavero JWT, valores por defecto) y su rastro |
| `custom_project_types`, `custom_project_statuses`, `custom_task_statuses`, `custom_client_industries`, `custom_expense_categories`, `custom_supplier_service_types`, `custom_supplier_billing_units` | Catálogos de fábrica que cada empresa ve junto a los suyos |
| `ai_providers`, `integration_credentials`, `sso_configs` | Proveedor, credenciales y SSO del despliegue, como respaldo |
| `grc_role_permissions`, `alert_configs`, `sla_calendars` | Valores por defecto que la empresa sobreescribe |
| `exchange_rates`, `country_employer_costs` | Datos públicos o presets que trae el producto |
| `integration_connectors`, `bpmn_processes`, `cmdb_discovery_providers` | Catálogo y plantillas del producto |
| `audit_logs` | Sucesos sin empresa (arranque, siembra, acceso con usuario desconocido), con su propia cadena de hash |

**Por qué no se replican.** Copiar el valor común en cada empresa duplicaría el catálogo en cada alta. Además
congelaría los valores de fábrica, que ya no se podrían actualizar en un sitio. Y obligaría a reescribir las
lecturas `org == X OR org IS NULL`, que hoy aíslan bien.

**Lo que sí se corrigió:**

- `departments`, `email_templates`, `ai_governance_configs`, `slack_configs` y `budgets`/`budget_lines` no tenían
  lectura común: sus filas vacías no las veía nadie. Pasan a NOT NULL.
- La siembra crea esas filas ya con la empresa de la demo.

## 3. En ejecución

`_sellar_organizacion` (`app/db/session.py`) corre antes de cada flush:

1. Pone la empresa de la sesión.
2. Sin ella, la deduce del padre: proyecto, ticket y usuario primero, y después cualquier clave ajena a una tabla
   con empresa, incluido un padre nuevo del mismo flush (`empresa_deducida`). Si tampoco, la del superadmin que crea
   la fila.
3. Si aún queda una fila sin empresa en una tabla no exceptuada, corta el flush con `fila_sin_empresa` (500, con la
   tabla) y deja un `ERROR` en el log. Es mejor que un `IntegrityError` sin contexto. Si quien crea es un superadmin sin empresa
   elegida, 409 `empresa_requerida` (§6.3).

El aislamiento no se afloja. El filtro de tenant y la RLS son los mismos, y una fila con empresa es más estricta que
una vacía: ya no hay filas «de nadie» que solo ve un superadmin.

## 4. La migración

`208_empresa_obligatoria_y_portal`:

1. Comprueba los duplicados de correo del portal dentro de cada empresa. Si los hay, para sin tocar nada.
2. Rellena los vacíos, en este orden:
   - la empresa del padre por clave ajena (varias pasadas);
   - la de `EMPRESA_PARA_FILAS_SIN_EMPRESA`, la empresa única o, si hay varias, la única que tiene usuarios (las demás son marcadores vacíos como «Default Organization»); con varias empresas con usuarios, para;
   - si no queda ninguna opción, lista tablas, filas y empresas candidatas (con su número de usuarios) y para.
3. Rehace los índices del correo del portal y pone NOT NULL:
   - en Postgres, con `ALTER COLUMN`;
   - en SQLite, reconstruyendo cada tabla con su SQL exacto (índices de expresión y parciales incluidos), con
     `foreign_keys` apagado.
4. Deshacer: vuelve a nulable lo que no lo era ya en la 207 (los valores rellenados se quedan) y rehace el índice
   único del correo. Si el mismo correo ya está en dos empresas, para.

**Base con varias empresas.** Si la deducción no basta, la migración para; por ejemplo, con la «Default
Organization» vacía junto a la empresa real. Mira el mensaje y repite indicando la empresa:

```
set EMPRESA_PARA_FILAS_SIN_EMPRESA=<id>      (Windows)
export EMPRESA_PARA_FILAS_SIN_EMPRESA=<id>   (Linux/macOS)
```

`scripts/comprobar_esquema.py` avisa si la base marca la 208 pero sigue admitiendo `organization_id` vacío.

## 5. GRC

- **Auditoría**: la asignación por respaldo queda en el log de la migración (tabla y filas). Los cambios de los
  usuarios del portal, en `audit_log`.
- **RGPD**: no se crean datos personales nuevos. Los mensajes de la migración enmascaran el correo.
- **Retención**: sin cambios, porque cada fila conserva su política. Antes las filas sin empresa no las alcanzaba
  la purga por empresa; ahora sí.
- **Privilegios**: sin cambios. Elegir la empresa no da acceso a otra.

Pruebas: `tests/test_empresa_obligatoria.py`, `tests/test_portal_empresa_por_correo.py`,
`tests/test_empresa_en_segundo_plano_2026_11_24.py`.

## 6. Caminos sin empresa en la sesión (revisión 24-11-2026)

Riesgo: código que corre **sin empresa en la sesión** (tareas de Celery/APScheduler, hilos, webhooks, rutas
anónimas, scripts, siembra, superadmin sin empresa) y crea filas de una tabla cuya empresa **no siempre se
deduce** (sin clave ajena NOT NULL a un padre con empresa). Ahí el sellado no tiene de dónde sacarla y el
guardado se corta con `fila_sin_empresa`: un 500 en producción, o el trabajo de fondo entero deshecho.

### 6.1 Tablas en riesgo

Medido importando todos los modelos (`app.models.*`) y mirando, por tabla con `organization_id` no exceptuada,
si tiene alguna clave ajena **NOT NULL** a una tabla con empresa: **210 tablas en riesgo** (solo claves ajenas
nulables o ninguna) y 331 seguras (la empresa sale siempre del padre). En las 210 la empresa sale de la sesión,
de un padre nulable si viene relleno o del código que crea la fila.

| Módulo (`app/models`) | Tablas |
|---|---|
| `abac` | `abac_attribute_definitions`, `abac_policies`, `policy_audit_log` |
| `activity` | `activity_events` |
| `advanced_config` | `custom_fields`, `custom_roles`, `numbering_sequences`, `offices`, `project_templates`, `rate_tables`, `task_types`, `vacation_policies` |
| `ai_chat` | `ai_action_logs`, `ai_answer_feedback`, `ai_contracts`, `ai_governance_configs`, `ai_kb_articles`, `ai_meetings`, `ai_predictions`, `ai_prompt_templates`, `ask_data_examples` |
| `ai_governance` | `ai_guardrail_audit_logs`, `ai_guardrail_policies` |
| `ai_providers` | `ai_usage_logs` |
| `alert` | `alerts` |
| `alm` | `alm_assets`, `alm_contracts`, `alm_cost_centers`, `alm_eventos`, `alm_facturas_proveedor`, `alm_license_assignments`, `alm_licenses`, `alm_renewal_alerts`, `alm_renovaciones`, `alm_vendors` |
| `alm_integracion` | `alm_kits` |
| `alm_uso` | `alm_software_no_controlado`, `alm_uso_conexiones`, `alm_uso_derechos`, `alm_uso_evidencias`, `alm_uso_mapeos` |
| `ausencias` | `huecos_de_cupo`, `patrones_de_turnos`, `tipos_de_ausencia`, `tipos_de_documento_de_ausencia`, `turnos` |
| `automations` | `automation_events`, `automation_rules` |
| `bi_collaboration` | `dashboard_comments`, `dashboard_notifications`, `dashboard_versions` |
| `billing_reports` | `approval_groups`, `approval_workflows`, `automation_workflows`, `grc_audit_log`, `grc_sod_rules`, `import_jobs`, `invoices`, `report_definitions`, `scheduled_reports` |
| `bookings` | `recurring_invoices`, `sla_schedules` |
| `cab` | `calendar_events`, `email_logs`, `email_templates`, `gdpr_requests`, `integration_configs`, `maintenance_windows`, `webhook_triggers` |
| `client_portal` | `client_users` |
| `clientes_internos` | `internal_shared_costs` |
| `clients` | `clients` |
| `cmdb` | `cmdb_agent_registrations` |
| `cmdb_riesgo` | `sw_exploit_events`, `sw_risk_alert_log`, `sw_risk_snapshots`, `sw_saved_views` |
| `cmdb_software` | `sw_config`, `sw_products`, `sw_sbom_imports`, `sw_sync_runs`, `sw_vulnerabilities` |
| `collaboration` | `collaboration_audit_events`, `collaboration_legal_holds`, `collaboration_moderation_cases`, `collaboration_notifications`, `collaboration_presence_states`, `collaboration_push_subscriptions`, `collaboration_slash_command_logs`, `collaboration_workspaces` |
| `conectores` | `carpetas_documentales`, `conector_llamadas`, `enlaces_documentales` |
| `cuaderno` | `notebook_templates` |
| `demanda` | `demand_flows`, `demand_request_types`, `demand_requests` |
| `document_collab` | `document_collab_snapshots` |
| `enterprise` | `subcontractors`, `webhooks` |
| `epics` | `saved_filters`, `threaded_comments`, `wiki_spaces`, `wiki_templates` |
| `exchange_rates_log` | `currency_conversion_logs` |
| `git_integration` | `git_deployments`, `git_pull_requests` |
| `governance` | `compliance_evidence`, `legal_holds`, `retention_policies`, `tenant_policy_packs` |
| `horario` | `jornadas_laborales` |
| `horas_extra` | `config_horas_extra`, `presupuestos_de_horas_extra` |
| `issue_types` | `fts_index` |
| `jira_integration` | `sd_jira_configs` |
| `lecciones` | `lecciones` |
| `mfa` | `bi_tokens`, `budget_campaigns`, `budget_closes`, `budget_commitments`, `budget_templates`, `budget_variance_notes`, `budgets`, `pdf_export_jobs`, `scenario_models`, `slack_configs` |
| `ml_model` | `ml_models` |
| `oauth_apps` | `oauth_apps` |
| `okrs` | `okr_objectives` |
| `performance` | `review_cycles` |
| `pipeline` | `opportunities`, `pipeline_stage_configs`, `proposal_templates` |
| `pir` | `pir_configuracion`, `pir_plantillas`, `pir_revisiones` |
| `politicas` | `politica_evaluaciones`, `politicas`, `tablas_de_referencia` |
| `portal_conversations` | `portal_conversation_policies`, `portal_conversations` |
| `portfolio` | `portfolio_criteria`, `portfolio_gates`, `portfolio_proposals`, `portfolios` |
| `project` | `projects` |
| `proveedores` | `supplier_contracts` |
| `public_forms` | `public_forms` |
| `resources` | `skills` |
| `revenue` | `rev_period_closes` |
| `security_observability` | `security_detections`, `security_events`, `security_incidents`, `security_metric_snapshots` |
| `seguridad_de_cuentas` | `access_review_campaigns`, `audit_log_purge_permits`, `security_change_requests` |
| `semantic_engine` | `sem_assignments`, `sem_config`, `sem_embedding_cache`, `sem_feedback` |
| `service_desk` | `sd_agent_groups`, `sd_announcements`, `sd_autonomous_playbooks`, `sd_canned_responses`, `sd_change_blackouts`, `sd_change_requests`, `sd_channel_conversations`, `sd_ci_class_fields`, `sd_ci_classes`, `sd_compliance_reports`, `sd_configuration_items`, `sd_dynamic_form_rules`, `sd_escalation_rules`, `sd_inbound_messages`, `sd_itsm_metric_snapshots`, `sd_kb_articles`, `sd_kb_corrections`, `sd_kb_gaps`, `sd_major_incidents`, `sd_monitoring_alerts`, `sd_problem_rca_templates`, `sd_problems`, `sd_releases`, `sd_routing_feedback`, `sd_routing_rules`, `sd_service_categories`, `sd_sla_policies`, `sd_sla_rules`, `sd_standard_change_models`, `sd_status_components`, `sd_ticket_lifecycles`, `sd_ticket_templates`, `sd_tickets`, `sd_voice_sessions` |
| `service_desk_ai_governance` | `sd_ai_drift_snapshots`, `sd_ai_evaluation_runs` |
| `settings` | `areas`, `departments`, `holidays` |
| `ticket_a_pr` | `ticket_pr_runs` |
| `traduccion` | `message_translations`, `portal_content_translations`, `translation_cache`, `translation_glossary_terms` |
| `training` | `training_courses` |
| `user` | `users` |
| `white_label` | `org_brandings` |
| `workflow_designer` | `sd_workflow_blueprints` |

### 6.2 Cómo quedó cada camino

| Camino | Qué crea | Cómo queda |
|---|---|---|
| Celery beat / APScheduler (misma lista, `_replicar_celery_beat`) | casi todo | Revisadas las tareas de `app/worker.py`: «por empresa» (`en_cada_organizacion` + `con_empresa`), «por fila» (`como_organizacion` con la empresa de cada fila: aprobaciones, eventos de ticket, automatizaciones, BPMN, buzones, calidad de la KB), «por sujeto» (webhook, segundo plano, agente, conector) y «globales» (solo `app_settings`, `exchange_rates` y `audit_logs`, exceptuadas, o borrados). Sin cambios: ya estaban bien |
| Planificador de colaboración (`collaboration/_scheduler._tick`) | avisos e índice de los mensajes programados | **Arreglado**: `con_empresa(db, msg.organization_id)` por mensaje (la sesión recorre todas las empresas) |
| Temporizadores del motor de flujos (`workflow_engine.tick_waiting`) | pasos del run | Ya en `como_organizacion` del run |
| Hilo de precarga del modelo semántico (arranque) | `sem_config` | **Arreglado**: `get_or_create_config` y `SemanticAssigner` sin empresa usan la configuración por defecto en memoria, sin guardar |
| Correo entrante (webhook y `inbound_mail.procesar`) | `sd_tickets`, `sd_inbound_messages` | **Arreglado**: sin empresa destinataria, la única empresa activa; con varias, se ignora (`motivo: "sin empresa destinataria"`, 200, sin ticket) |
| SMS entrante (Twilio) | `sd_tickets` | **Arreglado**: igual que el correo (`ignored: true`, 200) |
| Agente on-premise de la CMDB (token) | CI, activos de ALM, software | **Arreglado**: `publicar_empresa(db, reg.organization_id)` tras validar el token. Además acota la búsqueda del CI por `external_id`, que corría entre empresas |
| Webhook entrante de colaboración (token) | mensaje, avisos, índice | **Arreglado**: `publicar_empresa` con la empresa del webhook |
| Webhook de Stripe | lo que creen los escuchadores al pagar | **Arreglado**: `fijar_contexto` con la empresa de la factura (sin cortar si la empresa está desactivada: Stripe reintentaría) |
| Aprobación por correo (enlace firmado) de un **superadmin** | rastro de la decisión | **Arreglado**: la sesión toma la empresa de la solicitud también para el superadmin (su ficha no se toca) |
| Git, Jira, Slack, WhatsApp, Teams, reuniones, monitorización, voz, firma electrónica, formularios públicos, SCIM, OAuth, BI embebido | tickets, PR, despliegues, eventos… | Revisadas: ya publicaban la empresa del slug, token o firma (`publicar_empresa`/`como_organizacion`) antes de crear, o solo leen |
| Login, SSO, SAML, passkey, MFA, portal (`sesion_de_sistema`) | `security_events`, usuarios JIT | Revisadas: el evento de seguridad solo se emite con empresa del usuario; el alta JIT exige empresa del proveedor (`sso_sin_empresa`) |
| WebSockets (`declarar_sistema("ws: …")`) | según el canal | Revisados: publican la empresa del usuario o cliente (`publicar_contexto_de_tenant`) tras identificarlo |
| Segundo plano (`app/core/segundo_plano.encolar`) | según la función | Corre con la empresa con que se encoló (`fijar_contexto`); sin ella, contexto de sistema (ver §6.5) |
| Siembra (`sesion_de_siembra`, `seed_full_data.py`) | demo | Publica la empresa demo (`publicar_org_de_demo`); `reset_to_admin_only.py` crea el admin con la empresa base |
| `sin_filtro_de_tenant` (92 usos) | — | Solo crean filas en `grc_role_permissions` (exceptuada) y `grc_sod_rules` (abajo) |
| Inserts que se saltan el sellado | `grc_sod_rules` (`bulk_save_objects`), `huecos_de_cupo` (insert de núcleo), `audit_log_purge_permits` (SQL) | **Arreglado**: `ensure_sod_seeded` sin empresa no siembra (ya no hay reglas globales); `cupos._asegurar` toma la de la sesión o corta con `fila_sin_empresa`; el permiso de purga siempre lleva la empresa purgada |
| Instantánea colaborativa de documento | `document_collab_snapshots` (`document_id` no es clave ajena) | **Arreglado**: la empresa del documento, explícita |
| Escalado a ticket desde el bot de colaboración | `sd_tickets` | **Arreglado**: la empresa activa de quien escribe, explícita |
| Caché de embeddings semánticos | `sem_embedding_cache` (`assigned_user_id` no es clave ajena) | **Arreglado**: la de la sesión o la de quien resolvió; sin ninguna, no se guarda |
| Registros accesorios en la sesión de quien llama | `ai_usage_logs`, `ai_action_logs`, `ai_guardrail_audit_logs`, `conector_llamadas`, `translation_cache` | **Arreglado** (`empresa_para_registro`): la empresa explícita o la de la sesión (en `ai_action_logs`, también la del usuario); sin ninguna, no se registra y queda un `WARNING`. Antes el corte del sellado se llevaba por delante el trabajo de quien llamaba (y la fila se quedaba en `session.new`, cortando cada flush siguiente) |

### 6.3 Superadmin sin empresa

Un superadmin con empresa (la de su ficha o la activa elegida) crea en ella. Sin empresa elegida, lo que cuelga
de un padre con empresa se guarda en la del padre; lo demás se corta con **409 `empresa_requerida`** («Esta
acción necesita una empresa activa», con la tabla en `params.tabla`) en vez del 500 `fila_sin_empresa`
(`empresa_obligatoria.superadmin_sin_empresa`). Nunca se elige por él una empresa al azar. El 500 queda para un
trabajo sin sujeto que no sabe su empresa: es un fallo del código y deja un `ERROR` con la tabla.

### 6.4 GRC

- **Auditoría**: sin cambios en el rastro; lo que antes quedaba «de nadie» ahora queda en su empresa y lo ve
  su auditoría. Los mensajes entrantes ignorados dejan un `WARNING` (sin direcciones ni teléfonos).
- **RGPD**: no se guardan datos nuevos; los logs nuevos no llevan datos personales (solo cuántos destinatarios).
- **Retención**: las filas que ahora llevan empresa entran en la purga y retención de su empresa.
- **Privilegios**: sin cambios. Publicar la empresa en una ruta anónima solo acota (filtro y RLS); el superadmin
  no gana acceso: se le pide elegir empresa.
- **BPM**: el proceso sembrado `multichannel_intake` gana el paso «Identificar empresa destinataria (sin ella,
  se ignora)» (es/en/zh, `docs/BPM.md` §10). Las bases ya sembradas lo reciben con `seed_catalogue(force=True)`.

### 6.5 Lo que no se cierra aquí

- Un trabajo encolado por un superadmin sin empresa (`encolar` sin `_organizacion`) que cree filas sin padre
  sigue cortándose con `fila_sin_empresa`: la petición que lo encola ya respondió y no hay a quién pedir empresa.
- Las 210 tablas se revisaron por camino de ejecución (contextos sin empresa), no servicio a servicio: lo que
  solo se llama desde peticiones con usuario de empresa (la inmensa mayoría) queda cubierto por el sellado con
  la empresa de la sesión.

### 6.x Cierre de los dos pendientes (24-11-2026)

- **Trabajo encolado por un superadmin sin empresa:** `app/core/segundo_plano.py::encolar` responde ya en la propia
  petición con 409 `empresa_requerida` cuando quien encola es un superadmin sin empresa elegida y no se indica
  `_organizacion`. Antes el trabajo fallaba después en el worker con `fila_sin_empresa`, sin nadie a quien avisar.
  Para encolar trabajo, el superadmin elige empresa en el selector de empresa.
- **Procesos BPM sembrados desfasados:** ver `docs/BPM.md` (sincronización al arrancar).
- **Plantillas BPM globales (prueba general 24-11-2026, decisión pendiente):** `bpmn_processes` admite la fila
  sin empresa (plantilla común, exceptuada), pero `bpmn_process_versions` es NOT NULL desde la 208. Por eso
  `create_process(organization_id=None)` (que crea la versión 1) se corta con `fila_sin_empresa`, y ningún camino
  del código crea ya plantillas globales: el catálogo vive en el código (`PROCESS_CATALOGUE`) y cada empresa
  siembra su copia. Si quedara una plantilla global antigua con versiones, la 208 habrá dado a esas versiones la
  empresa de respaldo y las demás empresas no las verían. En la base de desarrollo no hay ninguna (0 procesos).
  Opciones: exceptuar también `bpmn_process_versions` (nueva migración) o retirar la fila global de
  `bpmn_processes`. `tests/test_auditoria_tipado_backend_2026_11.py` crea la plantilla global sin versión.
- **Registros que ya no pueden quedar sin empresa** (tests adaptados en la prueba general): aplicación OAuth
  (la base rechaza quitarle la empresa; el 400 `oauth_app_sin_empresa` queda como defensa), festivo (el paso
  de datos de la 182 se prueba sobre una base aparte con la columna opcional) y aviso creado por un trabajo sin
  empresa y sin padre del que deducirla (`fila_sin_empresa`).
