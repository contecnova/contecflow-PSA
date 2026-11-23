# Auditoría 2026-11-22 · 03 · Servicios m–z, modelos y esquemas

Solo lectura: no se ha modificado código ni ejecutado tests o typecheck.

**Alcance**
- `app/services/` con primer componente de la m a la z: 320 ficheros, 82.358 líneas. Se reparte así:
  - m–p: 27.088 líneas.
  - r–z sin `service_desk`: 25.681.
  - `service_desk/`: 105 ficheros, 29.305 líneas.
- `app/models` y `app/schemas` completos: 144 ficheros, 22.259 líneas. Hay 537 tablas mapeadas.

**Método**
- Revisión en 4 bloques: m–p, r–z, `service_desk` y modelos/esquemas.
- De los críticos y altos se han vuelto a comprobar en el código, por separado, los que están marcados ✔. Lo que no se pudo comprobar dice «sin verificar».
- **Refs** = ficheros de `app/` (incluido `app/worker.py`) que importan el módulo, sin contar el propio / ficheros de `tests/`.
- Medidas de modelos: análisis AST de `app/models` y `git grep`.

**Contexto de aislamiento comprobado**
- `app/db/session.py:440-560` añade `with_loader_criteria` por `organization_id` y también por `org_id` (`_iter_org_id_models`, l.417 y 569). Lo hace solo en SELECT ORM.
- Se salta el filtro en estos casos:
  - `session.info["is_superadmin"]` vale `None` (worker o sesión sin inicializar) o `True`.
  - Con `bypass_tenant_filter` activo.
  - En cargas de relaciones.
  - En `text()`, `update()` y `delete()`.
- La RLS (`app/db/rls.py`) solo actúa si el rol de base de datos no tiene BYPASSRLS.
- Por eso las fugas reales aparecen en el worker, en canales sin empresa, en sesiones de superadmin, en SQL crudo y al aceptar ids de otra empresa en claves ajenas.

---

## 1. Resumen

| Severidad | m–p | r–z | service_desk | modelos/esquemas | Total |
|---|---|---|---|---|---|
| Crítica | 0 | 0 | 5 | 0 | **5** |
| Alta | 10 | 8 | 20 | 3 | **41** |
| Media | 13 | 20 | ~30 | 5 | **~68** |
| Baja | 10 | 12 | ~10 | 3 | **~35** |

**Lo más grave**
1. **IA que actúa sola sin control.**
   - El agente autónomo tiene un error de escala (0-100 sumado a 0-1) que anula los umbrales.
   - La auto-resolución con LLM toma la confianza que declara el propio LLM y publica la respuesta como pública sin revisión humana. Además va sin `user_id`, así que sin guardrails ni redacción de datos personales.
2. **ITSM sin máquina de estados.** El CAB se puede saltar con un PATCH de estado o arrancando un despliegue. El informe semanal de cumplimiento da datos falsos (`approver_id` nunca se escribe; el estado `"failed"` no existe).
3. **Reloj de SLA inconsistente.**
   - La pausa manual se cuenta dos veces.
   - Las pausas se cuentan en reloj de pared sobre vencimientos en horario laboral.
   - Al pasar de una espera a otra se pierde el tiempo ya pausado.
   - La prioridad que fija el enrutado no recalcula el SLA.

   En todos los casos se ocultan incumplimientos.
4. **Dinero.**
   - Margen calculado con monedas mezcladas.
   - Tipo de cambio de otra empresa en el worker, o 1,0 en silencio si falta.
   - Hitos facturados sobre el presupuesto de coste.
   - Retainer que no se factura los días 29-31.
   - Reconocimiento de ingresos con huecos y duplicados.
   - Stripe con una única cuenta global.
   - 89 columnas de dinero en `Float` frente a 24 `Money`/`Rate`.
5. **Identidad y canales.**
   - Remitente del correo entrante falsificable.
   - Usuario de Slack identificado por su nombre (lo elige él).
   - Adjuntos de correo sin validar.
   - `NameError` en la descarga de adjuntos de canal.
6. **M365 global para todas las empresas.** Cualquier usuario sube los Excel de BI a cualquier OneDrive del tenant, y los KPI de todas las empresas van al mismo webhook de Teams.
7. **RGPD.**
   - La supresión reescribe filas sin empresa y las tablas `org_id` de toda la base.
   - El certificado de firma afirma una integridad que no da.
   - 7 tablas con datos personales no tienen retención.
   - El `bot_token` de Slack se guarda en claro.

**Lo que está bien**
- Hay columna de empresa en 536 de 537 tablas. Solo `organizations` no la tiene, y es lo esperado.
- `traduccion/` y `reuniones/` son ejemplares: credenciales por empresa, SSRF controlado y firmas con ventana y comparación en tiempo constante.
- `numbering` bloquea con `FOR UPDATE`.
- `oauth_state` está bien firmado, es de un solo uso y va ligado a usuario y empresa.
- El webhook de Stripe exige firma.
- `mcp_service` tiene modos de escritura y auditoría.

---

## 2. Inventario por módulo

Estados posibles: OK, parcial, stub, roto, peligroso (funciona, pero hace daño tal como está) y muerto.

### 2.1 m–p

| Módulo | Qué hace | Qué no hace o deja a medias | Refs app/tests | Estado |
|---|---|---|---|---|
| m365_bi_embed_service | Pestaña de Teams, tarjeta adaptativa, SharePoint, exportación a Excel/RTF, OneDrive | Credenciales `AZURE_*` globales. `/me/drive` es imposible con token de aplicación. Token de incrustación en la URL | 2/2 | parcial |
| m365_service | Token y llamadas a Graph; guarda de buzón por empresa | Pide un token nuevo en cada llamada. `graph_patch` muerto | 3/2 | OK |
| marketplace_service | Catálogo de 22 conectores e instalación con configuración cifrada | 7 conectores sin código (sap_s4, netsuite, workday, bamboohr, greenhouse, azure_devops, google_workspace) marcados `is_certified: True`. Si falla el cifrado, guarda en claro | 2/1 | parcial |
| mcp_service | Servidor MCP JSON-RPC con modos off/approval/direct y auditoría | — | 2/1 | OK |
| metrics/ (19 ficheros, 117 métricas) | Registro declarativo de métricas | Etiquetas en castellano fijas. `except (ImportError, Exception): return [], {}` | 3/5 | OK (revisado por encima) |
| milestone_service | Hito: completar → aprobar → facturar | Un hito por % se calcula sobre `budget_amount`, que es coste. Duplica el CRUD de profitability | 3/1 | parcial |
| ml_features / ml_trainer | GBM de sobrecoste por empresa, firmado con HMAC | `train_all_orgs` muerto. Umbral 1.10 fijo. Supone «cost_eur» | 3/1 · 2/3 | OK |
| notification_service | Envío SMTP | STARTTLS/SSL sin verificar el certificado (✅ 23-11-2026: verificado, `SMTP_TLS_VERIFY`). Los avisos usan el SMTP del `.env` | 16/6 | OK |
| notifications | Aviso en la app + Redis | Abre una conexión Redis por aviso. Empuja antes del commit (✅ 23-11-2026: cliente único y empujón tras el commit) | 35/6 | OK |
| nps_service | NPS y salud del cliente | — | 1/1 | OK |
| numbering | Secuencias por empresa con FOR UPDATE | Año calculado en UTC (✅ 23-11-2026: zona de la empresa) | 22/1 | OK |
| oauth_state | `state` OAuth firmado y de un solo uso | — | 3/1 | OK |
| okr_service | OKR y KR | Sin línea base ni KR decrecientes. Copia de los pesos de EVM | 2/1 | OK |
| olap/ | ETL a DuckDB con respaldo en PostgreSQL | Sin `org_id` no filtra. N+1 en el respaldo | 8/5 | OK |
| organizations_service | Alta de empresa, cupos y miembros | La auditoría registra como actor al usuario afectado (✅ 23-11-2026: actor real). N+1 | 5/1 | OK |
| pagination_service | Paginación por cabeceras | Duplica `app/core/paginacion` (7 usos frente a 28) | 6/0 | OK |
| payments_service | Webhook de Stripe con firma | No comprueba el importe ni la moneda cobrados | 1/1 | OK |
| pdf_export_service | PDF con reportlab | `project_summary` siempre falla ✔ | 1/1 | roto en parte |
| perf_reminder_service | Recordatorios de evaluaciones | `Notification` creada a mano, sin preferencias ni WS (✅ 23-11-2026: `notify_user`) | 2/3 | OK |
| performance_service/ | Ciclos, 360 y evaluaciones | Sin verificar a fondo | 1/1 | OK |
| pipeline_service | Oportunidades → proyecto | Usa el ingreso como presupuesto de coste. No copia la moneda. Actividades sin comprobar la propiedad (✅ 23-11-2026) | 4/1 | parcial |
| planificador/ | CPM, nivelación y calendario | 8 h/día por defecto | 11/6 | OK |
| plantillas_de_proyecto | Plantillas de proyecto | — | 5/1 | OK |
| politica_de_visibilidad | Quién ve a quién | — | 34/4 | OK |
| politicas/ | Motor de políticas con lógica de tres valores | Importación XLSX/CSV sin límite (✅ 23-11-2026: 5 MB, filas y columnas acotadas) | 17/6 | OK |
| portal_conversation_service/ | Conversaciones del portal | Redacción débil (DNI, IBAN o teléfono con espacios) (✅ 23-11-2026) | 1/0 | OK |
| portfolio_service | Carteras | — | 1/3 | OK |
| predictive_retraining_service | Salud y reentreno de modelos | — | 2/2 | OK |
| preferencias_de_aviso | Preferencias por canal | — | 8/0 | OK |
| presets_de_pais | Presets de coste por país | — | 1/0 | OK |
| presupuestos_preparar | Partidas, techo y campaña | Dinero en float | 4/1 | OK |
| presupuestos_seguir | Comprometido, cierres, previsión, traspasos y alertas | Alertas cruzadas entre empresas en el worker. Pedido sin máquina de estados (✅ 23-11-2026) | 5/0 | parcial |
| profitability_service | Cuenta de resultados, EVM, tipo de cambio, hitos | Monedas mezcladas. Tipo de cambio 1,0 si falta | 12/8 | parcial |
| project_service | Código, EVM y alta de proyecto | `build_code` roto en Postgres ✔ | 20/3 | parcial |
| proposal_service | Plantillas SOW | Plantilla por defecto solo en castellano | 2/0 | OK |
| proveedores/ (15 ficheros) | Contratos, consumo, facturación, portal y GRC | El tope cuenta estados de cuenta disputados. Una factura se puede conciliar dos veces (✅ 23-11-2026: las dos) | 15/2 | OK |
| psa_flows | Aprobación de imputaciones y partes de horas, prefactura | Partes de horas sin segregación ni ámbito | 9/1 | parcial |
| public_forms_service | Formulario público → ticket o tarea | No valida que el destino sea de la empresa (✅ 23-11-2026) | 1/1 | parcial |
| puesta_en_marcha | Lista de configuración pendiente | — | 1/0 | OK |

### 2.2 r–z (sin service_desk)

| Módulo | Qué hace | Qué no hace o deja a medias | Refs app/tests | Estado |
|---|---|---|---|---|
| raci_service | RACI, changelog, UAT, retrospectiva y riesgo de agotamiento | N+1 (16 consultas por persona). Textos y umbrales fijos. Perfilado de bienestar sin base RGPD ✅ 23-11-2026: sin división por cero con capacidad 0. | 1/2 | OK con deuda |
| rate_card_service | Tarifas, excepciones, escalado, `tarifa_de_facturacion` | Las excepciones no miran si la tabla está activa. Una tarifa 0 cae a la de respaldo ✅ 23-11-2026: excepciones solo de tablas activas; tarifa 0 respetada. | 4/1 | parcial |
| report_builder_service | Constructor de informes y CSV | CSV sin neutralizar fórmulas | 4/5 | OK |
| report_pdf / report_pdf_service | PDF tabular / PDF BI | Si falla OLAP, sale un PDF vacío sin error ✅ 23-11-2026: si OLAP falla, 503 `informe_bi_sin_datos`. | 2/4 · 2/4 | parcial |
| reserva_de_documentos | Reserva de documentos (423) | — | 4/0 | OK, sin tests |
| resource_analytics | Disponibilidad, carga y skills | N+1 (personas × semanas) | 6/4 | OK, lento |
| resumen_de_avisos | Correo diario de avisos | Marca el envío antes de enviar. Texto en castellano | 1/2 | parcial |
| retencion | Políticas de retención y bloqueo legal (24 tipos) | Ver 3.4: 7 tablas con datos personales fuera | 4/3 | OK |
| reuniones/ (20 ficheros) | Asistente de reuniones (Teams, Zoom, Meet, Recall, STT) | Audio solo en disco local. Borra el fichero antes del commit. Integraciones no probadas contra servicios reales | 12/3 | OK |
| revenue_service | ASC 606 | Float. Las horas aprobadas tarde se pierden. Hitos sin idempotencia. Sin auditoría | 3/3 | parcial |
| risk_scoring / risk_service | Riesgos | — | 3/0 · 2/0 | OK, sin tests |
| s3_service | S3 o disco local | `reload_from_db` sin llamantes: el S3 por empresa nunca se aplica ✅ 23-11-2026: `reload_from_db` retirado; S3 por empresa ⏸ (migración, ver 4.3). | 11/7 | parcial |
| salesforce_service | Importa oportunidades | Alta rota (falta `code` NOT NULL). Saliente es un stub. Sin refresco OAuth. SSRF | 1/1 | roto / stub |
| scenarios_service | Simulación de capacidad | Demanda inflada | 1/2 | parcial |
| scheduled_reports / _compat | Informes programados / resumen por SQL crudo | Hora en UTC. Reenvía a quien ya lo recibió si falla a medias ✅ 23-11-2026: hora local de la empresa, sin reenvío en envío parcial, HTML escapado; `_compat` sin contexto no cuenta nada. | 6/6 · 2/1 | parcial |
| scim_service | SCIM 2.0 | `generate_scim_token` solo lo usan los tests: en producción solo vale el token global. Bulk sin savepoints ✅ 23-11-2026: token por empresa cableado (`POST /organizations/{id}/scim-token`), búsqueda por hash y bulk con savepoint. | 1/4 | parcial |
| security_observability/ | Eventos de seguridad y SOC | Reglas de exportación masiva y sesiones concurrentes inexistentes. Umbral de credential stuffing ignorado ✅ 23-11-2026: umbrales `SOC_*` configurables, constantes sin regla retiradas, evento en sesión propia. | 3/1 | parcial |
| semantic_classifier / semantic_engine_service | Asignación semántica | TF-IDF global del proceso, reajustado por cada empresa ✅ 23-11-2026: sin el nombre del tercero. | 12/6 · 2/2 | defectuoso |
| session_security | Sesiones y riesgo | Se fía de cabeceras falsificables ✅ 23-11-2026: cabeceras de geo solo de proxy de confianza. | 4/1 | OK con riesgo |
| settings_audit_service | Auditoría de ajustes | SHA-256 de los secretos sin sal ✅ 23-11-2026: HMAC con `SECRET_KEY`. | 3/1 | OK |
| settings_service/ | Ajustes por empresa | `"EUR"` de respaldo | 212/60 | OK |
| signature_pdf | Certificado de firma | El hash no incluye el documento | 1/1 | engañoso |
| skill / sprint / training | CRUD | — | 1/0 · 3/0 · 1/0 | OK, sin tests |
| sla_service | SLA, numeración, historial, token del portal | Módulo cajón. Pausa en reloj de pared. `next_ci_number` global sin bloqueo ✅ 23-11-2026: `next_ci_number` por empresa con cerrojo. | 29/9 | OK con deuda |
| slack_service | Configuración Slack/Teams y envío | `bot_token` en claro. «SIMULATED» devuelve éxito ✅ 23-11-2026: sin token ni webhook ya no es éxito. | 1/2 | parcial |
| stripe_service | Checkout | Una única cuenta global. Enlaces caducados que se reutilizan | 1/0 | parcial |
| stt/ | Voz a texto con respaldo | Coste 0, así que el tope de gasto no frena. Región de Azure sin validar ✅ 23-11-2026: coste estimado (`STT_COSTE_USD_POR_MINUTO`); región validada. | 6/8 | parcial |
| supresion_service | Derecho de supresión | Ver hallazgo A-RZ1 | 3/3 | peligroso |
| task_service + tasks/ | Dominio de tareas | 5 funciones duplicadas en los dos sitios ✅ 23-11-2026: la masiva valida prioridad y asignado. | 6+8/5+4 | deuda |
| teams_bot | Bot de Teams | No probado contra Azure (lo dice el propio docstring) ✅ 23-11-2026: token de aplicación bajo cerrojo. | 1/1 | parcial |
| textos_de_salida(_itsm), textos_guardados | i18n del servidor | — | 26/3 · 1/1 · 5/1 | OK |
| timesheet_service | Listados | `reviewer_name` siempre None | 1/1 | parcial |
| trabajos_de_fondo | Trabajos por empresa | Retainer de los días 29-31. Sin recuperación ✅ 23-11-2026: resultado de Celery sin correos; mes sin locale. | 2/4 | parcial |
| traduccion/ | Traducción | — | 40/7 | OK (ejemplar) |
| traffic_control_service | Cuotas | No atómico. Hace commit de la sesión del llamante ✅ 23-11-2026: sesión propia con `FOR UPDATE`; no confirma la del llamante. | 5/1 | parcial |
| user_service | Usuarios | Ver M-RZ 15-17 ✅ 23-11-2026: `manager_id` validado, `audit_log` de campos sensibles, correo propio solo por admin, bloqueo legal en el borrado. | 3/4 | OK con agujeros |
| valoracion / vistas_guardadas / widget_de_formulario | Utilidades | — | 2/0 · 1/1 · 2/0 | OK |
| webhooks | Encola entregas | — | 2/3 | OK |
| ws_manager / ws_service | WebSocket | Contador del portal sin acotar. Dict en memoria con varios procesos ✅ 23-11-2026: contador del portal acotado a los proyectos del cliente. | 4/0 · 4/0 | parcial |

### 2.3 service_desk/ (105 ficheros)

| Módulo | Qué hace | Qué no hace o deja a medias | Refs | Estado |
|---|---|---|---|---|
| ticket_creation_service | Alta interna, portal, canal y cumplimiento | No recalcula el SLA tras el enrutado. Sin empresa usa candidatos y reglas globales. Portal sin validar `contract_id`/`ci_id` | 11/2 | parcial |
| ticket_update_service | PATCH, primera respuesta, resolución, pausa | Sin máquina de estados. Pausa sobre pausa. Reloj de pared | 15/2 | parcial |
| sla_del_ticket / sla_event_service / sla_monitor_service / reglas_sla / sla_policy / sla_assignment | Reloj del SLA, pausa manual, monitor, reglas y políticas | Reanudar a mano cuenta la pausa dos veces ✔ | 2/0 · 2/1 · 3/3 · 4/1 · 1/0 · 1/1 | `sla_event` roto; el resto OK |
| escalation_service | Escalado | N+1. Destinos sin validar. Sin historial | 2/1 | parcial |
| routing_rule_service | Enrutado | Horas en UTC. Rangos que cruzan medianoche nunca casan. Acciones sin validar | 2/2 | parcial |
| incident_assignment / ml_routing / workload | Asignación (por reglas; lo declara, no es ML) | ~10 consultas por agente | 1/1 · 7/1 · — | parcial |
| scoping | Alcance de tickets, problemas, CIs y KB | Empresa de la ficha, no la activa. Sin empresa y no superadmin → sin filtro (l.114) | 33/5 | OK con riesgo |
| ticket_query / ticket_read / ticket_ops / status_compat | Listado, detalle, operaciones | UPDATE crudo de todas las empresas y commit en cada GET | 1/1 · 2/2 · 16/2 · 3/0 | parcial |
| workflow_engine / workflow_designer / workflow_triggers | Motor de grafos | Nodo `action` no implementado. Rama por defecto = primera arista. Evento sin empresa dispara flujos de todas | 4 · 1 · 1 | parcial |
| governance_compliance_service | Auditorías ITIL/CMM e informe semanal | Dos indicadores siempre falsos ✔ | 2/0 | parcial |
| change_service / change_management / change_calendar / change_rollout / cab_workflow / change_impact/ | Cambios ITSM y CAB | CAB evitable ✔. Plan de despliegue inventado. Script bash con inyección | 6 · 1 · 2 · 1 · 2 · 4 | peligroso |
| autonomous_agent_service | Playbooks por palabra clave | Error de escala ✔. Coincidencia por subcadena | 3/4 | peligroso |
| ai_auto_resolution_service / auto_resolucion_operaciones | Auto-resolución con LLM | Confianza declarada por el LLM. Publica en público. Sin auditoría. Aprende solo de éxitos | 3/6 · 1/5 | peligroso |
| ai_suggest / asistente_del_portal(_ia) | Borrador y asistente | `call_ai` sin `user_id` en el portal | 1/2 · 3/3 | OK con reservas |
| predictive_analytics / incident_intelligence | Percentiles y reglas presentados como «predicción» | Recalcula los embeddings de todo el KB en cada llamada | 4/3 · 8/1 | heurística |
| rca_wizard / problem_service / problem_management / known_error / major_incident | Problemas, RCA, KEDB, incidente mayor | La RCA con IA falla siempre. El KB se publica sin revisión. El incidente mayor nunca agrupa tickets | 2 · 7 · 1 · 2 · 1 | parcial |
| smart_catalog / catalog_* / fulfillment / dynamic_* | Catálogo y aprovisionamiento | Secretos legibles. Jinja en Ansible. Editar tareas rompe las peticiones en curso | 2 · 3-7 | parcial |
| canal_slack / canal_whatsapp / inbound_mail / buzones / correo / adjuntos_de_canal / multichannel / sms | Canales | Identidad falsificable. Adjuntos sin validar. `NameError` ✔. SSRF por IMAP. Un ticket por SMS | 4 · 3 · 4 · 5 · 2 · 3 · 1 · 5 | parcial |
| jira_sync_service | Jira | La salida está muerta. Estado entrante sin pasar por el flujo central | 2/4 | parcial |
| ticket_events / ticket_event_processor | Bandeja de eventos | No idempotente: reenvía correos y SMS | 30/1 · 6/6 | parcial |
| alert_correlation / monitoring_ingest | Correlación y Alertmanager | Ámbito por usuarios, no por empresa | 6/3 · 1/2 | parcial / OK |
| cmdb_* | CIs, relaciones, 3D, discovery | Blast radius 3D al revés. 5 de 6 proveedores de discovery sin dependencia instalada | 1-2 | parcial |
| voice_agent_service | IVR por reglas | Datos personales en JSON de AppSetting sin retención | 1/1 | parcial |
| kb_* / semantic_feedback | KB, pgvector, calidad RAG | `SessionLocal()` sin empresa. ✅ arreglado 23-11-2026: las tres tareas de `semantic_feedback_service` reciben la empresa del ticket (`org_id`, `tickets.py`) y abren su sesión con `fijar_contexto`; `kb_calidad.pasada` corre como tarea o con `segundo_plano` (contexto declarado). Con `TENANT_SESION_SIN_CONTEXTO=cerrar` (defecto) una sesión sin contexto ya no pasa (docs/seguridad/rutas_anonimas.md §4) | varios | OK |
| status_page / pagina_de_estado_publica / portal_auth | Página de estado y autenticación del portal | Sin tests | 2-3/0 | OK |
| plantillas_aviso / notification_template / announcement | Textos de aviso | Sin `zh` (32 entradas es/en, 0 zh) | 1-2/0 | parcial |
| merge_split / link / watcher / comment / csat / customer_context / oncall / metrics / dashboard / canned / template / agent_group / duplicados | Auxiliares | La fusión mezcla clientes. FCR con `is_client` inexistente. CSAT sin rango | 1-5 | mixto |

Ningún módulo de los tres bloques está muerto entero. Lo muerto son funciones (sección 5).

---

## 3. Modelos y esquemas

### 3.1 Medidas

| Medida | Valor |
|---|---|
| Tablas mapeadas | 537 |
| Sin columna de empresa | 1 (`organizations`, lo esperado) |
| Con `org_id` en lugar de `organization_id` | 11 (`abac_*`, `user_attributes`, `policy_audit_log`, `ai_guardrail_*`, `security_*`, `login_anomalies`). El filtro ORM sí las cubre (`session.py:569`) |
| `organization_id` nullable | 470 de 525 |
| FK totales / sin `ondelete` | 1.593 / 625 (39 %) |
| FK a `organizations` sin `ondelete` | 353 (129 con) |
| FK a `users` sin `ondelete` | 174 (252 con) |
| Columnas de dinero en `Float` / en `Money`/`Rate` | 89 / 24 |
| Modelos sin uso fuera de `app/models` | 5 |
| Esquemas: campos `str` / con `max_length` o `constr` / `Literal` o `Enum` / `EmailStr` | 1.410 / 121 / 51 / 8 |
| Esquemas: campos de dinero en `float` / `Decimal` | 98 / 0 |

### 3.2 Hallazgos de modelos

**A-MOD1 (alta). 625 FK sin `ondelete`.**
- ✅ 23-11-2026 (migración 200): las 440 que quedaban, en modelos y base: hacia `organizations` `CASCADE`, nullable `SET NULL`, si no `RESTRICT`; `tests/datos_auditoria_mz_modelos.json` con `fk_sin_ondelete` vacía.
- **Estado:** ⏸ pendiente: migración (la hace el coordinador; ver «Migraciones» en el informe de arreglos). Ronda 2 (23-11-2026): medido sobre `Base.metadata` tras importar `app.main`: **451 columnas FK sin `ondelete` en 359 tablas** (539 tablas; el coordinador ya está bajando la cifra en los modelos). ✅ Test de detección sin migración: `test_a_mod1_y_a_mod2_ninguna_fk_sin_ondelete_ni_dinero_float_nuevos` (`tests/test_auditoria_2026_11_22_mz_ronda2.py`) falla si aparece una FK nueva sin `ondelete`; la lista medida está en `tests/datos_auditoria_mz_modelos.json` y solo puede encoger. Migración exacta: por cada FK de la lista, `ALTER TABLE t DROP CONSTRAINT fk; ALTER TABLE t ADD CONSTRAINT fk FOREIGN KEY (col) REFERENCES ref(id) ON DELETE <política>` con la política: `CASCADE` en hijas sin vida propia (líneas, comentarios, miembros, adjuntos); `SET NULL` en autoría opcional (`created_by`, `assignee_id`, `owner_*`) si la columna es nullable; `RESTRICT` en evidencia obligatoria (aprobaciones, votos, horas facturadas: `user_service.historial_que_retiene` ya lo respeta); hacia `organizations`, `CASCADE` (la baja de empresa purga). Orden: primero hijas de `organizations` (para que `baja_de_empresa_service.purgar` pueda simplificarse), después `users`, después el resto; cada lote en su revisión y con el modelo cambiado a la vez; quitar de la lista JSON las que se migren.
- 174 apuntan a `users` y 353 a `organizations`.
- `user_service.py:830` hace `db.delete(user); db.commit()`. En Postgres, el borrado de un usuario con historial falla por FK (500). En SQLite deja huérfanos (sin verificar si `PRAGMA foreign_keys` está activo).
- La baja de empresa (`baja_de_empresa_service.purgar`) tiene que borrar tabla a tabla en el orden correcto. Sin verificar que cubra las 353.
- Arreglo:
  - Decidir la política por FK: `SET NULL` en autoría y `CASCADE` en hijas.
  - Hacer un test que recorra `Base.metadata` y falle si hay FK sin `ondelete`.

**A-MOD2 (alta). Dinero en `Float`: 89 columnas.**
- ✅ 23-11-2026 (migración 200): `invoices.tax_rate` y `recurring_invoices.tax_rate` a `Rate` (Numeric 18,6) y `rev_obligations.standalone_price` a `Money`. `absences.amount` es cantidad en días/horas (no dinero): se queda.
- **Estado:** ⏸ pendiente: migración por dominios (plan en el informe de arreglos). Ronda 2 (23-11-2026): medido con la heurística de nombres de dinero del test: quedan **8 columnas `Float`** (`absences.amount`, `invoices.tax_rate`, `recurring_invoices.tax_rate`, `rev_obligations.standalone_price` y 4 que no son dinero aunque casen por nombre: `client_health_snapshots.budget_component`, `ml_prediction_logs.cost_overrun_prob`, `project_risk_scores.budget_risk`, `security_metric_snapshots.auth_failure_rate`). ✅ El mismo test falla con una columna de dinero nueva en `Float` (lista en `tests/datos_auditoria_mz_modelos.json`). Migración exacta para las 4 de dinero: `ALTER COLUMN ... TYPE NUMERIC(18,2) USING round(col::numeric, 2)` (`amount`, `standalone_price`) y `NUMERIC(9,4)` para `tax_rate` (`Rate`), modelo a `Money`/`Rate` a la vez, y los esquemas de esas entidades a `Decimal` serializado como número. ⏸ Los 98 campos `float` de esquemas: por dominio, con el frontend.
- `alm.py` 10, `enterprise.py` 12, `proveedores.py` 12, `mfa.py` 8, `project.py` 5, `user_cost.py` 5, `revenue.py` 3 (`models/revenue.py:53,161`), entre otras.
- Ya existe `app/models/money.py` (`Money = Numeric(18,2)`), pero solo se usa en 24 columnas.
- En los esquemas hay 98 campos de dinero `float` y ningún `Decimal`.
- Arreglo: migrar a `Money`/`Rate` por dominios, empezando por facturación, ingresos y proveedores.

**A-MOD3 (alta). Datos personales sin retención ni purga.**
- ✅ 23-11-2026 (migración 200): voz → `sd_voice_sessions` (cifrada, huella HMAC), esperas → `sd_ticket_hold_snapshots`, formularios dinámicos → `sd_dynamic_form_rules`/`_history`, con copia de datos y borrado de la clave solo tras copiarla; lectores y escritores cambiados; `sd_voice_sessions` y `sd_kb_gaps` en `bloqueo_legal.TIPOS`; voz en la copia y la supresión RGPD. ⏸ etiquetas de retención en el frontend.
- **Estado:** ✅ arreglado 23-11-2026: 9 tablas en `bloqueo_legal.TIPOS` (`public_form_submissions`, `user_sessions`, `security_events`, `security_detections`, `login_anomalies`, `document_access_logs`, `ai_action_logs`, `collaboration_audit_events`, `jira_sync_logs`), con `columna_empresa` para las `org_id`; textos es/en/zh. ⏸ pendiente: blobs de `AppSetting` (voz, snapshots, campos dinámicos, KBGap) a tablas propias. Ronda 2 (23-11-2026), migración propuesta para los blobs de `AppSetting` (no creada): (1) voz → `sd_voice_sessions` (descrita en 4.3 service_desk); (2) snapshots de espera (`sd.ticket.pending_snapshot.<ticket>`) → columnas `pending_snapshot_json` (Text) en `sd_tickets` o tabla `sd_ticket_hold_snapshots` (`ticket_id` PK/FK CASCADE, `organization_id` NOT NULL, `snapshot_json`, `created_at`), que se borra al reanudar; (3) campos dinámicos e historial (`sd.dynamic_forms.rules`/`.history`) → `sd_dynamic_form_rules` (`id`, `organization_id` NOT NULL, `regla_json`, `updated_by` FK users SET NULL, `updated_at`) e historial `sd_dynamic_form_rule_history` (FK CASCADE); (4) `KBGap` ya es tabla (`kb_calidad`): solo falta darla de alta en `TIPOS` con fecha `created_at`. Orden: crear tablas → copiar desde `AppSetting` por `organization_id` → cambiar lectores/escritores → borrar las claves de `AppSetting` → alta en `bloqueo_legal.TIPOS` y en la supresión RGPD (`_COLUMNAS_DE_IDENTIDAD`). Es zona service_desk: los lectores los cambia ese agente.
- `retencion`/`bloqueo_legal.TIPOS` cubre 24 tipos. No cubre estas tablas, y no hay borrado programado de ninguna (grep sin resultados):

| Tabla | Datos personales |
|---|---|
| `public_form_submissions` | `submitter_email`, `ip_address` |
| `user_sessions` | `ip_address` |
| `security_events`, `security_detections`, `login_anomalies` | IP |
| `document_access_logs` | IP |
| `ai_action_logs` | IP |
| `collaboration_audit_events` | IP |
| `sd_jira_sync_logs` | payloads con datos personales |

- Además hay datos personales en blobs JSON de `AppSetting`, fuera de cualquier retención o supresión: sesiones de voz (teléfono y transcripción), snapshots de espera, campos dinámicos y `KBGap`.
- Arreglo: añadir esas tablas a `TIPOS` y sacar los datos personales de `AppSetting` a tablas propias.

**M-MOD1 (media). `organization_id` nullable en 470 tablas.**
- 🟡 23-11-2026 (migración 200): pasos (1)-(2): relleno desde `project_id`/`ticket_id` (en la base local no había huérfanas de empresa: las 2 642 filas NULL son de catálogos globales). ⏸ (4)-(5) `SET NOT NULL`: los trabajos de fondo aún crean filas sin empresa a propósito (`app/db/session.py`); por dominios.
- **Estado:** ⏸ pendiente: migración (no se crean en esta ronda). Migración exacta propuesta: (1) consulta de huérfanas por tabla (`SELECT count(*) WHERE organization_id IS NULL`) en las tablas que NO declaran `_tenant_filter_include_global`; (2) rellenar las que se puedan deducir por su padre (`tickets` → `projects`/`clients`, hijas por su FK) con `UPDATE ... FROM padre`; (3) mover el resto a una tabla de cuarentena o borrarlas tras revisión; (4) `ALTER COLUMN organization_id SET NOT NULL` por lotes de dominio (ITSM, proyectos, finanzas, personas), cada uno en su revisión de Alembic, y `nullable=False` en el modelo a la vez; (5) la RLS pasa a `WITH CHECK (organization_id = current_setting('app.tenant'))` sin la rama NULL. Los canales/worker ya rechazan org None (A-SD5, `TENANT_SESION_SIN_CONTEXTO=cerrar`), así que no nacen filas nuevas sin empresa.
- Las filas con NULL son invisibles para un usuario normal, pero:
  - el WITH CHECK de la RLS las admite (`rls.py`);
  - los únicos compuestos `(organization_id, code)` no chocan con NULL en Postgres.
- Una fila creada sin empresa por un canal o por el worker (ver A-SD5) queda huérfana y fuera de retención.
- Arreglo: `nullable=False` en las tablas que no son catálogo global (las que no declaran `_tenant_filter_include_global`, 15 casos).

**M-MOD2 (media). Únicos globales que deberían ser por empresa.**
- 🟡 23-11-2026 (migración 200): `integration_connectors` hecho (`UNIQUE (organization_id, slug)` + parcial global; la instalación prefiere el conector de la empresa). ⏸ `client_users`: exige antes que el login del portal elija empresa (si no, un correo repetido entra en la empresa equivocada).
- **Estado:** ⏸ pendiente: migración + zona del portal (migración 198, otro agente). Migración exacta: `client_users`: `DROP CONSTRAINT` del único de `email` y `CREATE UNIQUE INDEX uq_client_users_org_email ON client_users (organization_id, lower(email))`; a la vez, `client_portal_service/clientes.create_client` debe comprobar el duplicado con `organization_id` (hoy busca global y su error revela que el correo existe en otra empresa) y el login del portal elegir empresa por subdominio/slug cuando el correo exista en varias. `integration_connectors`: quitar `unique` de `name`/`slug` y crear `UNIQUE (organization_id, slug)` más un índice parcial `UNIQUE (slug) WHERE organization_id IS NULL` para el catálogo global.
- `client_portal.py:41`: `ClientUser.email unique=True`. Un contacto con el mismo correo en dos empresas es imposible, y el error de duplicado revela que el correo existe en otra empresa.
- `marketplace.py:119-120`: `name`/`slug` únicos globales en un modelo `include_global`.

**M-MOD3 (media). Modelos sin uso fuera de `app/models`.**
- **Estado:** ✅ arreglado 23-11-2026: retirados los 5 modelos (`AIAnomaly`, `OAuthState`, `SubcontractorWorkerSkill`, `ImputationSnapshot`, `WhatIfTask`); DROP en la migración `196_auditoria_2026_11_22` (con `wiki_export_jobs`).
- Cinco, y su tabla tampoco aparece en SQL crudo: `AIAnomaly` (`ai_chat.py`), `OAuthState` (`bookings.py:283`; `oauth_state` usa `state` firmado), `SubcontractorWorkerSkill` (`enterprise.py:437`; solo una relación), `ImputationSnapshot` (`imputation.py:152`) y `WhatIfTask` (`marketplace.py:75`).
- Arreglo: borrarlos con una migración, o documentar para qué se conservan.

**M-MOD4 (media). El docstring de `models/mfa.py:164` dice que `SlackConfig.bot_token` se guarda cifrado. No es así** (ver A-RZ2). ✅ arreglado 23-11-2026: el docstring ya es cierto: `bot_token` se cifra (ver A-RZ2).

**M-MOD5 (media). `approved_by` es FK a `users`, y `trabajos_de_fondo.py:347` escribe `"system-batch-score"`.** Probablemente falla el commit en Postgres. Sin verificar contra la migración.
- **Estado:** ✅ arreglado 23-11-2026: `trabajos_de_fondo` ya no pasa `"system-batch-score"` como `approved_by`.

**B-MOD1 (baja). 11 tablas usan `org_id` en vez de `organization_id`.** ✅ 23-11-2026 (migración 200): columna renombrada con sus índices; el modelo deja `org_id` como sinónimo (las ~30 consultas siguen valiendo); `bloqueo_legal` ya no necesita `columna_empresa`. El filtro las cubre, pero el código de servicios filtra a mano (unas 30 consultas, todas correctas). Es una incoherencia de nombres. **Estado:** ⏸ pendiente (sin fallo funcional): renombrar es migración (`ALTER TABLE ... RENAME COLUMN org_id TO organization_id` en `abac_*`, `user_attributes`, `policy_audit_log`, `ai_guardrail_*`, `security_*`, `login_anomalies`, con sus índices y políticas RLS) y tocar ~30 consultas y `session._iter_org_id_models`; el filtro ORM y la RLS ya las cubren.

### 3.3 Esquemas

**M-SCH1 (media). Validación de entrada débil.**
- **Estado:** 🟡 parcial 23-11-2026: `UserUpdate`/`UserSelfUpdate`: `avatar_url` solo http(s) o ruta propia (`_url_de_avatar`; antes `javascript:`/`data:`), `phone` ≤ 40, `avatar_url` ≤ 1000, `hourly_rate` ≥ 0; `UserUpdate.role` ya se valida contra `UserRole` en el servicio (422 `valor_no_valido`); la masiva de tareas valida prioridad y asignado. Test en `tests/test_auditoria_2026_11_22_mz_ronda2.py`. ⏸ El resto (1.410 `str` sin límite, estados como texto en otros esquemas) es un barrido por dominio: cada `max_length` debe casar con la columna y cambiarlo sin revisar el frontend rompe formularios.
- De 1.410 campos `str`, solo 121 llevan límite de longitud. Solo hay 51 `Literal`/`Enum`.
- Ejemplos:
  - `UserUpdate.role: Optional[str]`, validado después en el servicio (`user_service.py:508`).
  - `avatar_url: Optional[str]` sin validar el esquema de la URL.
  - `phone` libre.
- Estados y prioridades llegan como texto y se validan (o no) en cada servicio. Con un enum inválido, varios servicios dan 500 en el flush (A-SD4).

**B-SCH1 (baja).** **Estado:** ⏸ aceptado: `extra: "allow"` de `AutoApprovalRule` es a propósito y está documentado; los 53 `dict`/`Any` son cargas libres (configuración de conectores, reglas, metadatos JSON) que validan sus servicios; tiparlos es trabajo por dominio sin fallo concreto.
- `approvals.py:39`: `extra: "allow"` en `AutoApprovalRule`, a propósito y documentado.
- 53 campos `dict`/`Any` sin forma.

**Comprobado sin problema.** `organization_id` en `UserUpdate`/`SSOCreate`: `user_service._autorizar_y_validar_organizaciones` (l.449-481) limita a las empresas del administrador.

---

## 4. Hallazgos por severidad

Formato: **ID (severidad) Título** — fichero:línea — evidencia — impacto — arreglo. Los ✔ se han vuelto a comprobar por separado.

### 4.1 Críticos

**C-SD1. El agente autónomo resuelve todo lo que casa con un playbook ✔**
- **Estado:** ✅ arreglado 23-11-2026: `score_auto_resolution` (0-100) se divide entre 100; palabras clave por palabra completa (`_patron_de_palabra`), una categoría sola no basta, «security/seguridad» fuera de `pw-reset` y `PALABRAS_DE_SEGURIDAD` manda a revisión humana (`autonomo.motivo.seguridad`). Tests: `tests/test_auditoria_2026_11_22_servicios_m_z.py`.
- Dónde: `service_desk/autonomous_agent_service.py:508,521`.
- Evidencia: `ai_score = aii.get("score", 0.0)` … `composite = min(1.0, ai_score + playbook_boost)`. `score_auto_resolution` devuelve 0-100 (`incident_intelligence_service.py:138,169,182`).
- Impacto: `composite` vale siempre 1,0 y los umbrales `SD_AUTONOMY_*` no actúan. La coincidencia es por subcadena: «seguridad»/«acceso» casan con `pw-reset` (l.127). Hoy está apagado y en modo `suggest` por defecto.
- Arreglo: dividir entre 100, casar por palabra completa contra `trigger_keywords` y excluir seguridad.

**C-SD2. Auto-resolución con LLM sin control humano**
- **Estado:** ✅ arreglado 23-11-2026: la confianza ya no la declara el LLM (KB 60 % + histórico 40 %); publicar y resolver solo con la regla explícita `auto_publish` de la empresa, con KB y sin sospecha de inyección; si no, borrador interno (`is_public=False`); ticket delimitado (`<ticket>`, `_sin_delimitadores`) y `check_prompt_injection`; `call_ai` con la empresa del ticket y `is_superadmin=False`; `call_ai` sin usuario aplica las políticas de la empresa con `SujetoDeSistema` (guardarraíles y redacción). Tests.
- Dónde: `ai_auto_resolution_service.py:623-631` (la descripción del ticket va en el prompt), `:652` (`ai_json.get("confidence",0)/100.0`: la confianza la declara el LLM), `:808` (`is_public=True`), `:950` (sin `user_id`). `gobernanza.py:52`: `if skip_guardrails or not user_id: return None`.
- Impacto: inyección de prompt. El solicitante redacta la respuesta pública y el ticket se resuelve. Sin guardrails ni redacción de datos personales.
- Arreglo: no usar la confianza del LLM, revisión humana antes de publicar, y un usuario de sistema para la gobernanza.

**C-SD3. CAB evitable por PATCH ✔**
- **Estado:** ✅ arreglado 23-11-2026: máquina de estados `TRANSICIONES_DE_CAMBIO` (`_enums.py`) y `exigir_transicion_de_cambio` en `change_service._aplicar_estado`; `approved` solo lo escriben CAB, decisión de administrador o auto-aprobación. Tests.
- Dónde: `service_desk/change_service.py:298-335`.
- Evidencia: `_SOLO_POR_EL_CAB = {"approved"}`. Se admite `draft → in_progress → closed_success`.
- Arreglo: tabla de transiciones.

**C-SD4. Arrancar un despliegue aprueba de hecho el cambio**
- **Estado:** ✅ arreglado 23-11-2026: `start_rollout_execution`: 404 si el cambio no existe y 409 (`cambio_no_aprobado_para_desplegar`) si no está en `ESTADOS_DE_CAMBIO_IMPLANTABLES`; el estado se cambia antes de guardar. Tests.
- Dónde: `change_management_service.py:411-465`.
- Evidencia: `change.status = ChangeStatus.in_progress` sin mirar el estado anterior. Si el cambio no existe, devuelve 201 igualmente.
- Arreglo: exigir `approved`/`scheduled` y devolver 404 si no existe.

**C-SD5. El informe de cumplimiento es falso**
- **Estado:** ✅ arreglado 23-11-2026: usa `approved_by` (y no cuenta la auto-aprobación del solicitante), `ChangeStatus.closed_failed` por valor y los estados del filtro por enum (incluye `post_review`). Tests.
- Dónde: `governance_compliance_service.py:263`: `if not c.approver_id`. Nadie escribe `approver_id`; el CAB escribe `approved_by`. En `:276`: `str(c.status) in ("failed",)`; el enum tiene `closed_failed`, y además `str(enum)` devuelve `"ChangeStatus.x"`.
- Impacto: el 100 % de los cambios sale «sin CAB» y la tasa de fallos es 0.
- Arreglo: usar `approved_by` y `ChangeStatus.closed_failed`.

### 4.2 Altos

#### service_desk

**A-SD1. Reanudar el SLA a mano cuenta la pausa dos veces**
- **Estado:** ✅ arreglado 23-11-2026: `resume_ticket_sla` usa `_reanudar_sla_pausado` (no mueve vencimientos) y la pausa manual deja historial y usa `TicketStatus.pending_client`. Test.
- Dónde: `sla_event_service.py:55-62`. Suma `sla_pause_minutes` y además mueve `sla_resolution_due`. Los lectores vuelven a sumar la pausa (`sla_service.py:441-445`).
- Además, en l.27-28 cambia el estado sin historial.

**A-SD2. Pausas en reloj de pared**
- **Estado:** ✅ arreglado 23-11-2026: `sla_pause_minutes` se acumula en minutos del calendario del SLA (`horas_sla_entre`) y `vencimiento_efectivo(due, pausa, cal)` los suma con `sumar_horas_sla` (`_vencido`, monitor y OLA con su calendario); `comment_service` y `conversaciones` usan la misma reanudación; resolver un ticket en espera cierra la pausa. `ticket_out` (sin sesión) sigue sumando minutos de pared: misma cifra salvo cruces de noche/festivo. ✅ 23-11-2026 (ronda 2 SD): `ticket_out` usa el calendario del ticket (`object_session`) cuando hay pausa y el vencimiento a pelo ya pasó. ⏸ pendiente: `billing_reports_service/sla.py:185` (zona a-l) aún acumula en pared.
- Dónde: `ticket_update_service.py:79`, `sla_service.py:445`, `sla_del_ticket.py:487`.
- Impacto: una espera de viernes 17:00 a lunes 9:00 añade unas 64 h. Se ocultan incumplimientos.
- Arreglo: acumular en horas de calendario (`horas_sla_entre`/`sumar_horas_sla`).

**A-SD3. Pasar de una espera a otra pierde la pausa**
- **Estado:** ✅ arreglado 23-11-2026: `pausar_sla` no reinicia una pausa abierta y `_estado_en_espera` no repite la instantánea. Test.
- Dónde: `ticket_update_service.py:111-118`: `sla_paused_at = now` sin reanudar antes.

**A-SD4. El enrutado cambia la prioridad sin recalcular el SLA**
- **Estado:** ✅ arreglado 23-11-2026: `ticket_creation_service._enrutar` recalcula vencimientos si el enrutado cambia la prioridad (interno, portal y canal); acciones validadas (`TicketPriority`, `SupportLevel`, grupo/agente de la empresa). Tests en `tests/test_routing_rules.py`.
- Dónde: `ticket_creation_service.py:278,312` y `routing_rule_service.py:257`.
- Las acciones `set_priority`/`assign_*` no se validan: un enum inválido da 500 y se aceptan ids de otra empresa.

**A-SD5. Sin empresa se asignan agentes y reglas de cualquier empresa**
- **Estado:** ✅ arreglado 23-11-2026: candidatos (`_candidatos_de_asignacion`) y reglas (`apply_routing_rules`) acotados a la empresa del ticket (o de la sesión); sin empresa, ninguno.
- Dónde: `ticket_creation_service.py:145`: `db.query(AgentGroupMember).all()`. También `routing_rule_service.py:307`.
- Cuándo: buzón global (`buzones.py:56`), secreto global de correo (`inbound_email_service.py:292`), Slack sin vincular y `como_organizacion(db, None)` (`ticket_events.py:54`).

**A-SD6. Remitente del correo falsificable ✔**
- **Estado:** ✅ arreglado 23-11-2026: `remitente_fiable`: con `SD_INBOUND_REQUIRE_SENDER_AUTH` (por defecto sí) hace falta SPF/DKIM/DMARC alineados; `SD_INBOUND_AUTHSERV_ID` fija el servidor cuya cabecera vale. Ajustes en Settings, catálogo, README, docs/SERVICE_DESK.md y .env.example.
- Dónde: `inbound_mail.py:419`: `fiable = autenticacion_del_remitente(correo) is not False`. Sin cabecera `Authentication-Results` se da por fiable.
- Impacto: un `From:` de un agente comenta y cambia el estado.

**A-SD7. Slack identifica por nombre**
- **Estado:** ✅ arreglado 23-11-2026: `canal_slack.usuario_de_slack`: ID de Slack → `users.info` → correo → usuario único de la empresa del workspace (botones y slash commands). `integrations.find_user_by_slack_name` queda sin llamantes en app (fichero de la zona a-l: retirarlo allí).
- Dónde: `canal_slack.py:221` y `integrations.py:646-655`: `User.username == nombre | email LIKE 'nombre@%'`.
- Arreglo: identificar por el id de Slack con `users.info`, como ya hace `_quien` (l.487).

**A-SD8. Adjuntos de correo sin validar**
- **Estado:** ✅ arreglado 23-11-2026: `_guardar_adjuntos`: `safe_filename`, tope `min(SD_MAIL_MAX_ATTACHMENT_MB, CHANNEL)` y `validate_upload(CHANNEL)`; el rechazado se anota y el correo sigue.
- **Estado:** ⏸ pendiente: zona del agente de subidas/SSRF.
- Dónde: `inbound_mail.py:351-384`. Sin `validate_upload`, sin antivirus y sin límite.
- Arreglo: reutilizar `adjuntos_de_canal.guardar`.

**A-SD9. `NameError` en `descargar_acotado` ✔**
- **Estado:** ✅ arreglado (otro agente, 22-11-2026).
- Dónde: `adjuntos_de_canal.py:181,185`. Usa `error_con_codigo`, que solo se importa dentro de otra función (l.127).
- Impacto: 500 en Slack y WhatsApp (Meta reintenta).

**A-SD10. La RCA con IA no funciona nunca ✔**
- **Estado:** ✅ arreglado 23-11-2026: `problem_service.suggest_rca_from_ai` y `rca_wizard_service.ai_assist_step` tratan el texto de `call_ai`; sin JSON (aviso, bloqueo) no se escribe como causa raíz.
- Dónde: `problem_service.py:209` y `rca_wizard_service.py:445`. Hacen `result.get(...)` sobre el `str` que devuelve `call_ai`.

**A-SD11. Resoluciones de IA fuera del flujo central**
- **Estado:** ✅ arreglado 23-11-2026: `ticket_update_service.cambiar_estado_por_automatismo` (vía `apply_ticket_update` + `audit_log`) en auto-resolución LLM, operación «auto-resolver», agente autónomo y pasos `status_change` del catálogo; retirados los imports de `record_sla_event`/`notify_watchers`.
- Dónde: `ai_auto_resolution_service.py:825-831`, `auto_resolucion_operaciones.py:60-74`, `autonomous_agent_service.py:387-402`, `smart_catalog_service.py:647-656`.
- No dejan historial ni `audit_log`, ni `resolved_at`, ni SLA, ni CSAT.

**A-SD12. El bucle de aprendizaje solo suma éxitos**
- **Estado:** ✅ arreglado 23-11-2026: `run_auto_close_job` valida una vez cada auto-resuelto pasada su ventana (éxito o fallo, marca `auto_resolution_validation` en ambos) y después cierra sin volver a contar.
- Dónde: `ai_auto_resolution_service.py:519,532-534`. La ventana 72 h / 48 h queda siempre vacía.

**A-SD13. Empresa de la ficha y no la activa**
- **Estado:** ✅ arreglado 23-11-2026: `scoping.empresa_activa` (empresa del token en `db.info`) en endpoints de auto-resolución, agente autónomo y catálogo, y en `scope_ticket_query`; sin empresa y sin superadmin no se ve nada.
- Dónde: endpoints `ai_auto_resolution.py:76`, `autonomous.py:44`, `smart_catalog.py:106` y `scoping.py:97-103`.
- Un superadmin puede usar el proveedor de IA (y la clave) de otra empresa.

**A-SD14. Secretos de aprovisionamiento legibles**
- **Estado:** ✅ arreglado 23-11-2026: `GET /services/{id}/provisioning` exige administración. ⏸ pendiente: salida de Terraform con `-var` y Jinja en `--extra-vars` (`bookings_service/aprovisionamiento.py`, zona a-l).
- Dónde: `smart_catalog_service.py:509-514`. `GET /services/{id}/provisioning` solo exige `get_current_user`. La salida de Terraform muestra los `-var` (l.666-671).
- Jinja en `--extra-vars` (`aprovisionamiento.py:254`): sin verificar en ejecución.

**A-SD15. La fusión mezcla clientes**
- **Estado:** ✅ arreglado 23-11-2026: `ensure_same_customer`: misma empresa y mismo cliente (409 `ticket_fusionar_otra_empresa`/`ticket_fusionar_otro_cliente`).
- Dónde: `merge_split_service.py:31-34`: `update({"ticket_id": target})` sin comprobar cliente ni empresa.

**A-SD16. El KB se publica en el portal sin revisión**
- **Estado:** ✅ arreglado 23-11-2026: el artículo nace `in_review`, `is_public=False`, con empresa y numeración `next_kb_number`; sin la evidencia interna de la RCA.
- Dónde: `known_error_service.py:282-294` (`rca_evidence` interna, `is_public=True`).

**A-SD17. El incidente mayor nunca agrupa tickets**
- **Estado:** ✅ arreglado 23-11-2026: `escalate_linked_tickets_to_major_incident` escribe `major_incident_id` (solo tickets de la empresa del incidente) tras `flush`.
- Dónde: `major_incident_service.py:108-114`. Ninguna escritura de `major_incident_id` en `app/`.

**A-SD18. Workflows**
- **Estado:** ✅ arreglado 23-11-2026: rama sin arista → error del run (salvo salida única o arista `default`); evento sin empresa no lanza flujos; punto de guardado en vez de `rollback()` global; `approver_role` exigido en la reanudación (`_exigir_aprobador`).
- Una rama sin conectar sigue por la primera arista (`workflow_engine.py:861-870`).
- `workflow_triggers.py:93`: un evento sin empresa dispara los flujos de todas.
- `rollback()` global (l.816).
- La aprobación no comprueba `approver_role`.

**A-SD19. CAB sin separación de funciones**
- **Estado:** ✅ arreglado 23-11-2026: el solicitante no es miembro ni vota (`exigir_que_no_sea_suyo`); un CAB ya votado no se reinicia (`cab_ya_votado`) y `cab_review` no vuelve a borrador; el fast-track abre un ECAB con los aprobadores (sin el solicitante) en vez de aprobar con una persona. ✅ 23-11-2026 (ronda 2): catálogo de cambios estándar por empresa (`sd_standard_change_models`, migración 198): un cambio solo es estándar si referencia un modelo aprobado por el CAB (miembro o admin que no lo propuso), vigente (revisión periódica) y cuyo alcance y riesgo lo cubren; el tipo lo fija el servidor; suspensión automática por tasa de fallo (`SD_STANDARD_CHANGE_MAX_FAILURE_PCT`); auditado (`cambios_estandar_service.py`, docs/SERVICE_DESK.md).
- El solicitante vota su propio cambio (`cab_workflow_service.py:96-178`).
- Reiniciar el CAB borra los votos (l.118).
- El fast-track lo aprueba una sola persona (`change_management_service.py:661-719`).
- La auto-aprobación la decide el propio solicitante (`change_service.py:362-402`).

**A-SD20. Blast radius 3D al revés**
- **Estado:** ✅ arreglado 23-11-2026: BFS de destino a origen y con los tipos de `cmdb_relation_service` (`depends_on`, `hosts`, `part_of`).
- Dónde: `cmdb_3d_service.py:147-150`.

#### m–p

**A-MP1. El PDF de resumen de proyecto falla siempre ✔**
- **Estado:** ✅ arreglado (otro agente, 22-11-2026).
- Dónde: `pdf_export_service.py:154`: `t = Table(...)` pisa `def t(clave, **datos)` (l.94). Después, l.175 llama a `t('pdfexp.pie', ...)` → TypeError.
- Arreglo: renombrar la variable a `tabla`.

**A-MP2. OneDrive de cualquier persona**
- **Estado:** ✅ arreglado 23-11-2026: UPN validado con `buzon_de_la_organizacion`; quien no administra solo su OneDrive; exportaciones con `requiere_capacidad("analitica.ver")` y empresa activa; sin UPN no se sube (`/me/drive` retirado).
- Dónde: `m365_bi_embed_service.py:684-716` y endpoints `m365_bi.py:224,264`.
- Evidencia: `f"/users/{user_upn}/drive"` con `user_upn` sin `buzon_de_la_organizacion`, y solo `get_current_user`.
- Impacto: datos financieros subidos a cualquier OneDrive del tenant.

**A-MP3. Equipos, canales y sitios ajenos**
- **Estado:** ✅ arreglado 23-11-2026 (segunda ronda): `m365_service.credenciales_de_graph(db, empresa)` lee la credencial cifrada `ms_graph` de la empresa activa y el token se cachea por credencial. Los `AZURE_*` solo se usan como credencial de plataforma con `M365_PLATFORM_CREDENTIALS_ENABLED` (desactivado), y una credencial a medias no se completa con ella. Lo usan todos los endpoints de `m365.py`/`m365_bi.py`, el buzón Graph y el informe de uso de O365. `tenant_id`, equipo, canal, sitio y plan se validan (`id_de_graph`). Verificado: `tests/test_ronda2_transversal_2026_11_23.py` (credencial, plataforma opt-in, a medias, caché, identificadores, ningún `settings.AZURE_*` fuera de `m365_service`). Doc: `docs/seguridad/entrada_y_salida.md` §11.
- Dónde: `m365_bi_embed_service.py:146-160,254-280,421-430`. Credenciales `AZURE_*` globales e identificadores de Graph sin validar.

**A-MP4. Webhook de Teams global**
- **Estado:** ✅ arreglado 23-11-2026: `webhook_de_teams_de_la_empresa` (credencial `ms_graph.teams_webhook` o ajuste `TEAMS_WEBHOOK_URL` de la empresa, validado HTTPS; nunca el global) en BI y en `/m365/teams/notify*`; envío con `cliente_httpx`.
- Dónde: `m365_bi_embed_service.py:290-322`: `settings.TEAMS_WEBHOOK_URL`. Los KPI de todas las empresas van al mismo canal.

**A-MP5. Alta de proyecto en Postgres ✔ (lectura)**
- **Estado:** ✅ arreglado 23-11-2026: `build_code` usa `next_numbered_code("project")` (FOR UPDATE sobre la fila de la secuencia).
- Dónde: `project_service.py:58`: `select(func.max(Project.code)).with_for_update()`. Postgres no admite FOR UPDATE con agregados. Además `max` sobre texto ordena "PRJ-9999" > "PRJ-10000" y choca con `next_numbered_code("project")`.
- Arreglo: usar `next_numbered_code`.

**A-MP6. Margen con monedas mezcladas**
- **Estado:** ⏸ pendiente: zona del agente a-l (divisas/margen).
- Dónde: `profitability_service.py:188-194,330-339`. El ingreso va en la moneda del proyecto y el coste en la de la empresa.

**A-MP7. Tipo de cambio de otra empresa, o 1,0**
- **Estado:** ⏸ pendiente: zona del agente a-l (resolutor de tipo de cambio).
- Dónde: `profitability_service.py:48-58`: sin filtro de empresa en el worker (`presupuestos_seguir`, `olap`), y `rate = row.rate if row else 1.0`.

**A-MP8. Alertas de presupuesto entre empresas**
- **Estado:** ✅ arreglado 23-11-2026: `_departamentos_del_ambito`/`_centros_de_coste` acotados a la empresa del presupuesto; última versión por `version` ascendente.
- Dónde: `presupuestos_seguir.py:101-108,664-705`. `Department.name.in_(nombres)` en el worker. Además `ultimas[origen(b)] = b` sin ordenar por versión.

**A-MP9. Partes de horas sin segregación**
- **Estado:** ✅ arreglado 23-11-2026: SoD (`exigir_que_no_sea_suyo`); admin/RR. HH./responsable directo deciden el parte entero, un PM solo las imputaciones de sus proyectos y el parte se aprueba cuando no queda ninguna pendiente.
- Dónde: `psa_flows.py:84-121` (endpoint `timesheets.py:120`). Un manager se aprueba a sí mismo, y aprobar marca todas las imputaciones de la semana de cualquier proyecto. Eso alimenta la facturación.

**A-MP10. Hito por % facturado sobre el coste**
- **Estado:** ✅ arreglado 23-11-2026: base = contratos del proyecto o `contract_amount`; sin base, `None` (→ `hito_sin_importe`). De paso, total = base + cuota redondeada. Ronda 2: `contract_amount` en `ProjectCreate`/`ProjectUpdate`/`ProjectOut` y en el formulario de alta/edición de proyecto (moneda de la empresa), para que la base se pueda fijar desde la pantalla.
- Dónde: `milestone_service.py:103-117`: `or getattr(proj, "budget_amount", None)`.
- Arreglo: base = `contract_amount`, o error si no hay.

#### r–z

**A-RZ1. La supresión RGPD alcanza datos fuera de la persona ✔ (rebajada de crítica)**
- **Estado:** ✅ arreglado 23-11-2026: ámbito obligatorio (`organization_id` u `org_id` de sus empresas; sin NULL; sin empresas no se reescribe nada), nombre y usuario solo en columnas de identidad (`_COLUMNAS_DE_IDENTIDAD`), seudónimo HMAC con `SECRET_KEY`.
- Dónde: `supresion_service.py:136-146`.
- Evidencia: `ambito = None`; `if "organization_id" in cols and empresas: ambito = or_(...in_(empresas), ...is_(None))`; `cond = c == original if ambito is None else ...`, todo dentro de `sin_filtro_de_tenant`.
- Medido: 536 de 537 tablas tienen columna de empresa, así que el alcance sin límite queda en:
  - las 11 tablas `org_id`;
  - las filas con `organization_id` NULL;
  - toda la base si la persona no tiene empresas.
- Sustituye por `[ERASED]` cualquier texto exactamente igual al nombre o al usuario: un «Juan García» homónimo, etiquetas…
- Además, l.46-47: `sha256(email)[:16]` sin sal. Es seudonimización reversible por diccionario.
- Arreglo: lista blanca de columnas de identidad, ámbito obligatorio (también `org_id`), y HMAC con secreto.

**A-RZ2. `bot_token` de Slack en claro**
- **Estado:** ✅ arreglado 23-11-2026: se cifra al guardar y se descifra al usar; sin la clave en el formulario se conserva; la rotación cifra los antiguos en claro. Verificado: `test_el_bot_token_de_slack_se_guarda_cifrado`.
- **Estado:** ⏸ pendiente: zona del agente de cifrado de secretos.
- Dónde: `slack_service.py:103,114`, usado en l.46. 0 `encrypt_value`.

**A-RZ3. TF-IDF global y reajustado por cada empresa**
- **Estado:** ✅ arreglado 23-11-2026: TF-IDF por empresa (`_ENCODERS_POR_EMPRESA` con cerrojo, corpus de la empresa, `rebuild_profiles` sustituye el de su empresa); el transformer sigue compartido.
- Dónde: `semantic_classifier.py:40-60,296-302`. Los embeddings guardados quedan en otro espacio vectorial, el vocabulario de una empresa afecta a otra, y hay carreras entre hilos.

**A-RZ4. Salesforce roto y con SSRF**
- **Estado:** ✅ arreglado 23-11-2026: (parte SSRF) `instance_url` HTTPS + guardia central + `cliente_httpx`; el error ya no devuelve el texto remoto. El alta sin `code` y el stub saliente no son de esta zona.
- **Estado:** ⏸ pendiente: zona del agente de SSRF (Salesforce).
- Dónde: `salesforce_service.py:62-67`: `Opportunity(...)` sin `code` (NOT NULL, `models/pipeline.py:50`). En `:146-153`, `instance_url` sin `cliente_httpx`, con Bearer. La sincronización saliente es un stub.

**A-RZ5. El certificado de firma no garantiza integridad**
- **Estado:** ✅ arreglado 23-11-2026: `codigo_de_evidencia`: HMAC-SHA256 con `SECRET_KEY` sobre la huella del documento (`huella_del_documento`: bytes si está en `UPLOAD_DIR`, ficha si es un enlace) y los datos de la firma; `verificar_evidencia`.
- Dónde: `signature_pdf.py:151-152`: `f"{document_title}|{signer_email}|{signed_at}|{signature_ip}"`, sin el hash del documento ni clave. El texto del PDF dice «garantiza la integridad».

**A-RZ6. Stripe**
- **Estado:** ✅ arreglado 23-11-2026: clave y secreto de webhook por empresa (`stripe_service.clave_secreta`/`secreto_del_webhook`, sin caer a la global); el webhook verifica con el secreto de la empresa de la factura y comprueba importe y moneda; el enlace solo se reutiliza si la sesión sigue abierta con el mismo importe (`sesion_reutilizable`). ⏸ pendiente: importes en Float (A-MOD2).
- Dónde: `stripe_service.py:37-39,91`: solo `settings.STRIPE_SECRET_KEY`, una cuenta global para todas las empresas.
- `billing_reports_service/facturas.py:57-58` reutiliza el enlace de cobro (caduca a las 24 h y no se actualiza si cambia el total).
- Importes en Float.

**A-RZ7. Retainer**
- **Estado:** ✅ arreglado 23-11-2026: día efectivo = min(día, último del mes) y se factura en cuanto se alcanza (recupera días perdidos); solo bloquea el retainer del mes (marca `retainer:AAAA-MM` en `internal_notes`); la factura lleva `organization_id`.
- Dónde: `trabajos_de_fondo.py:266`: `if proj.retainer_day != hoy.day: continue`.
- Los días 29-31 no se factura, un día perdido no se recupera, y cualquier factura del mes bloquea la del retainer (l.270).

**A-RZ8. Ingresos ASC 606**
- **Estado:** ✅ arreglado 23-11-2026: reconocimiento acumulado en T&M/consumo y lineal (horas aprobadas tarde y periodos revertidos se recuperan en el periodo siguiente; el índice único del lote impide reescribir el mismo periodo); hitos una sola vez y con tope; cierre y reapertura auditados.
- Dónde: `revenue_service.py`.
- l.462: horas aprobadas tarde → nunca se reconocen.
- l.542: tras una reversión, el periodo no se puede volver a reconocer.
- l.348-358: hitos sin idempotencia ni tope.
- `close_period`/`reopen_period` sin auditoría.

### 4.3 Medios (resumen; detalle en los informes de bloque)

**m–p**
- Si falla el cifrado, el marketplace guarda en claro (`marketplace_service.py:236-245`). ✅ arreglado 23-11-2026: ya no hay respaldo en claro.
- Formularios públicos con destino de otra empresa (`public_forms_service.py:39-90`). ✅ arreglado 23-11-2026: `destino_de_la_empresa`: proyecto y grupo destino de la empresa del formulario al crear/editar (`formulario_destino_ajeno`) y, para formularios antiguos, al recibir el envío (se guarda el envío sin crear nada). Test.
- SMTP sin verificar el certificado (`notification_service.py:155-162`). ✅ arreglado 23-11-2026: `contexto_tls()` (`ssl.create_default_context`) en `SMTP_SSL` y `starttls`; `SMTP_TLS_VERIFY` (por defecto sí; `seguridad_salida_config`, .env.example, README) solo para un relay interno autofirmado. Test.
- Auditoría con el actor equivocado (`organizations_service.py:172,211`). ✅ arreglado 23-11-2026: `assign_user_to_org`/`remove_user_from_org` reciben `actor` (el superadmin del endpoint); el afectado va en la descripción. Test.
- Factura de hito: total ≠ subtotal + IVA (`milestone_service.py:290-292`). ✅ 23-11-2026: total = base + cuota redondeada.
- Webhook de Stripe sin comprobar el importe (`payments_service.py:80-101`). ✅ 23-11-2026: importe y moneda comprobados.
- Precalculado y recalculado no cuadran (`profitability_service.py:110-115`). ✅ arreglado (agente a-l): `calc_project_profitability` ya no usa los totales precalculados (`imputation_totals`, `billed_milestones_total`); todo sale de `margen_de_proyectos.margen_en_bloque`.
- Tope de proveedor y doble conciliación (`proveedores/facturacion.py:183-191,288-318`). ✅ arreglado 23-11-2026: `_gastado_antes` no cuenta estados `disputed`; `conciliar` da 409 `proveedor_factura_ya_conciliada` si la factura ya concilia otro estado de cuenta. Tests.
- OLAP: cualquier usuario ve márgenes y utilización (`endpoints/analytics.py:1119-1210`). ✅ arreglado 23-11-2026 (ronda 2, guardas): `requiere_capacidad("analitica.ver")` (admin + PM, como /executive y `margin-evolution`) en `GET /analytics/olap/kpis`, `/olap/pipeline-funnel`, `/olap/portfolio-health` y `/olap/utilization` (antes solo `get_current_user`). La pantalla que los usa (`/executive`) ya pedía `analitica.ver`.
- Actividades de pipeline sin comprobar la propiedad (`pipeline_service.py:166-188`). ✅ arreglado 23-11-2026: `add_activity` y `list_activities` (con el usuario, desde el endpoint) pasan por `oportunidad_propia` (404 si no se ve o está borrada). Test.
- Pedido de presupuesto sin estados, y commit antes del flujo (`presupuestos_seguir.py:483-499`). ✅ arreglado 23-11-2026: `TRANSICIONES_DE_PEDIDO` (solo `comprometido` → `facturado`/`anulado`; 409 `transicion_no_permitida`); `solicitar_traspaso` hace `flush`, abre el flujo y luego `commit`; el alta del pedido audita con su id. Tests.
- `Notification` a mano (`perf_reminder_service.py:112-124`). ✅ arreglado 23-11-2026: por `notify_user` (preferencias de aviso y WebSocket); solo cuenta los enviados. Test.
- Importación sin límite (`politicas/servicio.py:536-548`). ✅ arreglado 23-11-2026: `importar` corta en 5 MB (413 `fichero_supera_mb`), lee como mucho `MAX_FILAS`+2 filas y 50 columnas (`islice`, sin materializar el XLSX) y da 422 `importacion_demasiadas_filas`. Test.

**r–z**
- SCIM por empresa inalcanzable y bulk sin savepoint (`scim_service.py:78,649-676`). ✅ arreglado 23-11-2026: `POST /organizations/{org_id}/scim-token` (superadmin, como el resto de `organizations.py`) llama a `scim_service.rotar_token_scim` (= `generate_scim_token` + `AuditLog` `SCIM_TOKEN_ROTATE`, sin guardar el token); `process_bulk_operations` con `begin_nested()` por operación (la fallida se deshace sola). Tests en `tests/test_auditoria_2026_11_22_mz_ronda2.py`.
- Región de Azure STT inyectable en el host (`stt/azure_stt.py:62,74`). ✅ ya arreglado (otro agente, 23-11-2026): la región se valida como etiqueta DNS antes de montar el host (`STTError` si no).
- La voz cuesta 0 (`stt/__init__.py:116`). ✅ arreglado 23-11-2026: `stt.coste_estimado_usd`: minutos (`duration_ms` del proveedor o tamaño a 16 kB/s) × `STT_COSTE_USD_POR_MINUTO` (0,006; por empresa); cuenta para el tope diario de IA. Ajuste en `ai_config`, `.env.example` y README. Test.
- Contador del portal sin acotar (`ws_service.py:158-163`). ✅ arreglado 23-11-2026: `get_portal_poll_data` cuenta solo los mensajes del equipo (`sender_client_id` NULL) en los proyectos del cliente (`client_user_projects`); antes `!= client_id` (que además excluía los NULL) sobre toda la empresa.
- Excepciones de tablas de tarifas inactivas (`rate_card_service.py:206-222,361`). ✅ arreglado 23-11-2026: excepciones con `join` a `RateTable.is_active` (consulta y precarga `TarifasPrecargadas`); una tarifa 0 pactada ya no cae a la de respaldo (`is not None`); una entrada solo de coste devuelve `None`, no 0. Tests.
- La cuota hace commit de la sesión del llamante (`traffic_control_service.py:356`). ✅ arreglado 23-11-2026: `consume_quota` cuenta en una sesión propia (misma clase y contexto de empresa/RLS que la del llamante) con `FOR UPDATE` sobre la fila. Test.
- `manager_id` sin validar y 0 `audit_log` de rol o tarifa (`user_service.py:528-540`). ✅ arreglado 23-11-2026: `_validar_responsable` (existe, misma empresa, sin ciclo ni él mismo) también en `update_user_record`; `_auditar_campos_sensibles` deja `audit_log` de rol, rol personalizado, tarifa, responsable, correo y estado (también en `set_manager_record` y `/users/me`). Tests.
- Cambio de correo sin verificar (`user_service.py:790-810`). ✅ arreglado 23-11-2026 (mínimo seguro): cambiar el correo propio sin ser administrador da 403 `correo_solo_admin` (mandar el mismo no cuenta) y todo cambio queda en `audit_log`. ⏸ pendiente (producto): verificación por enlace al correo nuevo y aviso al antiguo (tabla de cambios pendientes → migración).
- Borrado permanente sin bloqueo legal ni auditoría (`user_service.py:830`). ✅ arreglado 23-11-2026: auditoría y bloqueo legal ya estaban en la rama de anonimizar (migración 196); la de borrado sin historial ahora también exige `exigir_sin_bloqueo_legal` (409) antes del `delete`.
- Cabeceras de geo falsificables (`session_security.py:132-136`). ✅ arreglado 23-11-2026: `cf-ipcountry`/`x-asn`/`x-isp`/`x-org` solo si la petición llega de un proxy de confianza (`network.cabeceras_de_proxy_fiables`: `TRUST_PROXY_HEADERS` + `TRUSTED_PROXY_CIDRS`). Test.
- Informes programados: UTC, reenvío y HTML sin escapar (`scheduled_reports.py:56,170,332-338`). ✅ arreglado 23-11-2026: `_get_next_run(..., zona=)` calcula en la hora local de la empresa y devuelve UTC (`proxima_ejecucion` toma la zona de la sesión del informe si no se pasa; `HORA_DE_ENVIO_POR_DEFECTO` = 8); un envío parcial (`EnvioParcial`) pasa a la siguiente ejecución en vez de reenviar a todos; nombre y marca con `html.escape`. Tests.
- PDF BI vacío sin error (`report_pdf_service.py:85-118`). ✅ arreglado 23-11-2026: si OLAP lanza, `_sin_datos_olap` da 503 `informe_bi_sin_datos` (el informe programado queda en error y se reintenta); «sin datos» sigue siendo un PDF válido. Test.
- CSV con fórmulas (`report_builder_service.py:859`). ✅ arreglado 23-11-2026: `dict_seguro` de `app/core/celdas_seguras.py`. ✅ 23-11-2026 (segunda ronda): 10 ficheros generan CSV/XLSX (los «~30» eran filas JSON de métricas, que no se exportan); 3 ya neutralizaban y los 7 restantes ahora también (analytics_extended, bi_export_service, bi_report_delivery_service, cargos internos, cmdb_software/analisis [2 CSV], m365_bi_embed_service, presupuestos_seguir): 10/10. Test estático `tests/test_exportaciones_sin_formulas.py` falla si aparece un generador nuevo sin `celdas_seguras`.
- Slack «SIMULATED» = éxito (`slack_service.py:62-63`). ✅ arreglado 23-11-2026: sin token ni webhook devuelve `(False, "slack_sin_configurar")`; si falla el token y no hay webhook, también falla. Canal por defecto `SLACK_CANAL_POR_DEFECTO` (automations_config, `.env.example`, README). Test.
- S3 por empresa nunca aplicado (`s3_service.py:157,273-280`). ⏸ pendiente (migración + diseño): exige guardar en cada fichero en qué almacén se escribió (columna `storage_backend`/`bucket` en documentos, adjuntos de ausencias, gastos, demanda, proveedores y actas ALM) para seguir leyendo los ya subidos, y una instancia por empresa (`almacen_de(db, org)`) en vez del `file_storage` global. ✅ 23-11-2026: retirado `S3Service.reload_from_db` (0 llamantes y, llamado, mutaba el cliente global para todas las empresas). Test.
- `next_ci_number` global (`sla_service.py:558-560`). ✅ arreglado 23-11-2026: `next_ci_number(db, org_id)` usa `_siguiente_numero` (cerrojo `pg_advisory_xact_lock` por empresa y máximo con empresa explícita, columna `code`); `cmdb/models.py` y el seed pasan la empresa. Test.
- División por cero en agotamiento (`raci_service.py:272`; sin verificar si la capacidad puede ser 0). ✅ arreglado 23-11-2026: capacidad 0 → `load_pct` 0 (100 si hay horas). Test.
- Asignación masiva sin validar (`tasks/bulk.py:101-102`). ✅ arreglado 23-11-2026: prioridad fuera de `TaskPriority` → 422 `valor_no_valido`; asignado inexistente o de baja → 422; tarea de una empresa que no es del asignado → `skipped` `assignee_other_org`. Test.
- Umbrales de seguridad sin usar y commit en `record()` (`security_observability/eventos.py:30-32,145,262`). ✅ arreglado 23-11-2026: umbrales como ajustes `SOC_*` (`umbral_soc`, por empresa; `seguridad_de_cuentas_config`, `.env.example`, README); `CRED_STUFFING_THRESHOLD` (20, sin usar) sustituido por `SOC_CRED_STUFFING_USUARIOS`=3 (lo que medía la regla); retirados `MASS_EXPORT_THRESHOLD` y `SESSION_CONCURRENT_LIMIT` (sin regla ni evento; las sesiones las limita `SESSION_MAX_CONCURRENT`); `emit` escribe en sesión propia (no confirma la del llamante y el evento sobrevive a su rollback). Tests.
- De paso: `entrega_de_webhooks.py:116` usa `httpx.Client` normal tras validar la URL (DNS rebinding) y admite secretos en claro. ✅ arreglado 23-11-2026: `cliente_httpx` (IP conectada).

**service_desk**
- `sanitize_legacy_ticket_statuses`: UPDATE crudo de todas las empresas y commit en cada GET (`ticket_read_service.py:61,94,150,186,203,234`; `status_compat.py:36-44`). ✅ arreglado 23-11-2026: fuera de los 6 GET de `ticket_read_service`; la función queda como reparación de mantenimiento sin commit, con punto de guardado y acotable con `org_id`. Test.
- Filtro `sla_breached` sin pausas (`ticket_query_service.py:83-89`). ✅ arreglado 23-11-2026: `_ids_con_sla_incumplido`: criba en SQL (vencimiento < ahora o marca guardada) y veredicto con `_vencido` (pausa en el calendario del SLA, reloj parado si está en espera); la respuesta ya dada cuenta por su marca. Test.
- El portal no valida `contract_id`/`ci_id` (`ticket_creation_service.py:332-360`). ✅ arreglado 23-11-2026: `_validar_referencias_del_portal`: contrato de su cliente y empresa; CI de su empresa y su proyecto; lo ajeno, 404 como lo inexistente. Test.
- Escalado: N+1, sin historial y con destinos sin validar (`escalation_service.py:184,215-233`). ✅ arreglado 23-11-2026: últimos disparos en una consulta y tickets agrupados por empresa; reasignación y subida de prioridad con `TicketHistory`; cola y personas de la empresa al guardar (422 `escalado_cola_ajena`/`escalado_destinatario_ajeno`) y al ejecutar (se omite la cola ajena y se filtran destinatarios). Tests.
- Enrutado en UTC y rangos de medianoche (`routing_rule_service.py:114,203-212`). ✅ arreglado 23-11-2026: hora y día en `DEFAULT_TIMEZONE` de la empresa (`formato_regional.zona_horaria`); «22:00-06:00» casa de noche. Test.
- `scoping.py:114`: sin filtro si no hay empresa. ✅ 23-11-2026: `false()`.
- Sugerencia de IA publicada como comentario público (l.684, 808). ✅ 23-11-2026: borrador interno.
- Fechas de cambios que pierden la zona (`service_desk/change_service.py:96,98,263,265,295`). ✅ arreglado 23-11-2026: `_a_utc`: con zona se convierte (antes `.replace` pisaba el desfase); sin zona, UTC como antes; ilegible → 422 `fecha_no_valida`. Test.
- Slack global de cambios. ✅ arreglado 23-11-2026: `_notify_change_stakeholders` usa el webhook de la empresa del cambio (`secreto_propio_de_la_organizacion`: credencial `slack.webhook_url` o ajuste `SLACK_WEBHOOK_URL`); nunca el global. Test.
- HTML sin escapar en correos (`change_management_service.py:499-505,643-648`). ✅ arreglado 23-11-2026: `_esc` (html.escape) en número, motivo, fase y usuario de los tres correos. Test. (Los textos en inglés fijos siguen: §6 «Idioma», otro agente.)
- Script bash de marcha atrás con inyección (`:294-328`). ✅ arreglado 23-11-2026: id del cambio limitado a `[A-Za-z0-9._-]`; el plan de marcha atrás sale comentado (`# `) para revisarlo y activarlo a mano. Test.
- Recálculo del KB en cada llamada (`incident_intelligence_service.py:97-117`; `ai_auto_resolution_service.py:734`). ✅ arreglado 23-11-2026: `embedding_de_articulo`: caché por (id, sha256 del texto) con cerrojo y tope de 5.000; la usan los dos sitios. Test.
- BFS con unas 4.000 consultas (`cmdb_relation_service.py:144-182`). ✅ arreglado 23-11-2026: `get_ci_impact_payload` por niveles: una consulta de relaciones y una de CIs por nivel (≤ 2·`max_depth`); cada CI sale una vez, en su nivel más cercano. Test.
- Avisos duplicados al reintentar (`ticket_event_processor.py:524-531`). ✅ arreglado 23-11-2026: `procesar_evento` hace primero lo transaccional (webhook, flujos, cierre de la petición) y al final los avisos; el SMS de guardia sale con los correos, tras el bucle. Queda la ventana de un fallo del propio commit tras enviar (sin marca persistente: exigiría columna nueva). Test.
- Jira: estado fuera del flujo, naive frente a aware y logs con datos personales (`jira_sync_service.py:325,386`). ✅ arreglado 23-11-2026: estado por `cambiar_estado_por_automatismo` (origen `jira`); fechas con `aware`; `JiraSyncLog` guarda solo estado, prioridad y fecha (`_campos_para_el_registro`); logs y `sync_error` con la clase del error. Tests.
- IMAP sin `validate_outbound_url` y con `str(exc)` (`buzones.py:66,187`). ✅ arreglado 23-11-2026: host ya validado (`_host_imap`, otro agente); `leer_todos` y `probar_buzon` devuelven la clase del error, no su texto (sonda de red). Test. ✅ Segunda ronda: se conecta a la IP validada, sin volver a resolver (`Imap4SslFijado`), y con certificado verificado (`contexto_tls`; antes imaplib no verificaba).
- Correlación por usuarios (`alert_correlation_service.py:46-64`). ✅ arreglado 23-11-2026: `_apply_org_scope` filtra por `Ticket.organization_id`. De paso, la prioridad dominante comparaba `str(enum)` y siempre ganaba la primera. Test.
- FCR con `is_client` inexistente (`metrics_service.py:56`). ✅ arreglado 23-11-2026: cuentan los comentarios con autor interno (`author_user_id` sin `author_client_id`). Test.
- Tareas canceladas cuentan como hechas (`fulfillment_service.py:74-77,140`). ✅ arreglado 23-11-2026: con alguna tarea cancelada la petición no se resuelve sola ni abre la etapa siguiente; decide el agente. Test.
- CSAT sin rango (`csat_service.py:31`). ✅ arreglado 23-11-2026: 1-5 (`CSAT_MIN`/`CSAT_MAX`); fuera, 422 `interno_puntuacion_fuera_de_rango`. Test.
- Correos en `governance_compliance_service.py:451`. ✅ arreglado 23-11-2026: la muestra de cuentas inactivas lleva ids, no correos, y se acota a la empresa del informe.
- Voz con datos personales en `AppSetting` (`voice_agent_service.py:141-180`). ✅ 23-11-2026 (migración 200): `sd_voice_sessions` creada y cableada (ver A-MOD3). Antes: ⏸ pendiente: necesita tabla propia (no se crean migraciones en esta ronda). Migración propuesta: `sd_voice_sessions` (`id` PK, `organization_id` FK NOT NULL + índice, `caller_id_hash` HMAC con `SECRET_KEY` y `caller_id_last4`, `channel`, `status`, `intent`, `entities_json` cifrado, `transcript_json` cifrado, `ticket_id` FK `sd_tickets` SET NULL, `resolution`, `created_at`, `updated_at`, `closed_at`); alta como tipo retenible en `app/db/bloqueo_legal.TIPOS` (fecha `closed_at`/`created_at`; campos de bloqueo `ticket_id`, `caller_id_hash`) con retención por defecto de 90 días; copiar y borrar la clave `sd.voice_agent.sessions` de `AppSetting`.
- `call_ai` sin `user_id` en portal, RCA, catálogo y riesgo. ✅ arreglado 23-11-2026: RCA (`suggest_rca_from_ai`, `ai_assist_step`), catálogo (`suggest_service_for_query`, también con empresa) y riesgo (`assess_change_risk_ai`, con empresa) reciben el usuario desde sus endpoints. Portal: el cliente no es `User`; ya pasa la empresa y se aplican sus políticas con `SujetoDeSistema` (C-SD2). Test.

**Modelos y esquemas:** M-MOD1 a M-MOD5 y M-SCH1 (sección 3).

### 4.4 Bajos (resumen)

- `str(enum)` mostrado o guardado como `"TicketStatus.x"`: `autonomous_agent_service.py:389`, `incident_intelligence_service.py:236`, `problem_service.py:361`, `known_error_service.py:91`, `dynamic_forms_service.py:365-376`, `multichannel_service.py:227`. ✅ arreglado 23-11-2026 (service_desk): `problem_service`, `known_error_service`, `dynamic_forms_service` (`_valor_de_enum`), `multichannel_service` y `alert_correlation_service`; `autonomous_agent_service` e `incident_intelligence_service` ya estaban. ⏸ `ai_auto_resolution_service._bucket_key` guarda «TicketPriority.x» como clave de estadísticas: cambiarla pierde el histórico aprendido (decidir si migrar las claves).
- `ilike(f"%{search}%")` sin escapar los comodines (`ticket_query_service.py:92`). ✅ arreglado 23-11-2026: `escapar_like` con `escape`. Test.
- `text.format(**ctx)` permite recorrer atributos (`workflow_engine.py:483`). ✅ arreglado 23-11-2026: `_render_template` solo sustituye `{nombre}`/`{nombre.clave}` sobre diccionarios, sin `_`. Test.
- Commits dentro de servicios y en GET: `reglas_sla:422,430,459`, `ciclos_de_vida:170,180`, `textos:228,279`, `dynamic_forms:125`. ✅ arreglado 23-11-2026: `reglas_sla` y `ciclos_de_vida` hacen `flush` (confirma el endpoint con `auditar_y_confirmar`); `dynamic_forms.reglas_o_sembrar` ya no escribe en el GET (devuelve las de por defecto). Test. ⏸ `change_impact_service/textos.py:228,279`: el commit guarda la caché de traducciones y el gasto de IA ya pagado aunque la petición sea GET; pasarlo a sesión propia es zona SessionLocal (otro agente).
- Teléfonos en logs: `sms_service.py:68,71`, `canal_whatsapp.py:269`. ✅ arreglado 23-11-2026: `telefono_enmascarado` (3 últimos dígitos) y clase del error. Test.
- Fechas naive: `pdf_export_service.py:189,231`, `report_pdf.py:231,260`, `report_pdf_service.py:196`, `demanda.py:64`. ✅ 23-11-2026 (`pdf_export_service`): `timeutil.now_local()`. Test. ✅ 23-11-2026 (resto): `report_pdf` y `report_pdf_service` con `formato_regional.ahora_local()`; `politicas/dominios/demanda.py:64` con `timeutil.today()`.
- Año de numeración en UTC (`numbering.py:15`). ✅ arreglado 23-11-2026: `_current_year(db, org)` en la zona `DEFAULT_TIMEZONE` de la empresa (UTC si no se puede leer). Test.
- Redis abierto por aviso y push antes del commit (`notifications.py:41,127`). ✅ arreglado 23-11-2026: un cliente Redis por proceso (`_redis`, con cerrojo); el empujón se encola en `db.info` y sale en `after_commit` (se descarta en `after_rollback`). Tests.
- Redacción débil en el portal (`portal_conversation_service/politicas.py:36-38`). ✅ arreglado 23-11-2026: `_redact_sensitive` redacta IBAN con espacios/guiones, DNI/NIE y teléfonos con separadores (≥ 9 dígitos, sin tocar fechas ISO). Tests.
- `ml_trainer.py:99-176`: una sola clase en `y` → ValueError. ✅ arreglado 23-11-2026: `train_model` devuelve `skipped`/`single_class`. Test.
- `presupuestos_seguir.py:454-458`: `int(mes[:4])` → 500. ✅ arreglado 23-11-2026: `_anio_mes` valida `AAAA-MM` (400 `mes_formato_no_valido`) en `crear_pedido` y `detalle_del_real`. Test.
- SHA-256 sin sal en la auditoría de ajustes (`settings_audit_service.py:30`). ✅ arreglado 23-11-2026: HMAC-SHA256 con `SECRET_KEY` (mismo largo; dos filas con el mismo valor siguen coincidiendo). Los hashes antiguos no se recalculan. Test.
- `scheduled_reports_compat.py:64`: `db.info.get("is_superadmin", True)`, falla abierto. ✅ arreglado 23-11-2026: decide `contexto_de_tenant.estado` (libre → todo; empresa → su empresa; sin contexto → resumen vacío). Test.
- `strftime('%B %Y')` según el locale (`trabajos_de_fondo.py:289`). ✅ arreglado 23-11-2026: `%m/%Y` (sin locale). El texto «Retainer mensual automático» es de §6 Idioma (otro agente).
- Datos personales en el resultado de Celery (`trabajos_de_fondo.py:209-210`). ✅ arreglado 23-11-2026: `imputaciones_pendientes_de_hoy` devuelve solo `missing_today`; la lista está en `personas_sin_imputar_hoy` (no viaja al backend de resultados). Test (y `test_semana_laboral_2026_11_19.py` adaptado).
- Token en un dict global sin cerrojo (`teams_bot.py:198`). ✅ arreglado 23-11-2026: `_TOKEN_LOCK` alrededor de leer/renovar el token de aplicación. Test.
- SCIM recorre todas las empresas en vez de buscar por hash (`scim_service.py:159-168`). ✅ arreglado 23-11-2026: `filter(Organization.scim_token_hash == hash)`.
- «Ficosa» (nombre de un tercero) aparece 12 veces en `semantic_classifier.py`. ✅ arreglado 23-11-2026: sustituido por «sistema de origen» (0 apariciones). Test.
- B-MOD1 y B-SCH1. ⏸ ver §3.2/§3.3 (estado en cada hallazgo).

**Descartado tras comprobarlo**
- «`revenue_service.py` no es UTF-8»: se lee sin error como UTF-8. ✅ descartado (comprobado).
- «Las tablas de seguridad con `org_id` quedan fuera del filtro»: falso, `session.py:569` las filtra. ✅ descartado (comprobado; desde el 23-11-2026 las dos únicas vías del filtro son `organization_id` y `org_id`).

---

## 5. Código muerto

**Estado 23-11-2026:** ✅ retirados `graph_patch`, `train_all_orgs`, la instancia `notification_service`, `borrar_reunion`, `mismo_idioma`, `auto_resolve_ticket`, `enrich_catalog_with_stats`, `push_comment_to_jira`, `_resolve_status_to_jira`, `jira_base_url_segura`, `get_executive_dashboard`, `select_best_agent_ml`, `select_best_agent_id_by_open_load`, los imports inexistentes de `ai_auto_resolution_service`, el comentario huérfano de `scim_service` y los 5 modelos. ⏸ Se quedan: `update_service_popularity` (tiene test que fija su contrato), `generate_scim_token` y `S3Service.reload_from_db` (no son código muerto sino funciones sin cablear: SCIM y S3 por empresa, hallazgos medios), los umbrales de `security_observability` (hallazgo medio), `_fx_cache` y `persist_metric_snapshot` (zona a-l), `compile_rules_from_graph` (escribe una columna; decidir si el motor la lee) y los alias `_PROVIDER_*` de discovery (reexportados a propósito). **Ronda 2 (23-11-2026):** ✅ `generate_scim_token` cableado (`POST /organizations/{org_id}/scim-token` → `rotar_token_scim`); ✅ `S3Service.reload_from_db` retirado (mutaba el almacén global; el S3 por empresa queda ⏸ por migración, ver 4.3); ✅ umbrales de `security_observability` convertidos en ajustes `SOC_*` y retiradas las dos constantes sin regla. ⏸ `compile_rules_from_graph`/`rules_json`: está en `service_desk/workflow_designer_service` (zona service_desk, otro agente); decisión pendiente: o el motor lee `rules_json` o se deja de escribir la columna (retirarla es migración).

| Símbolo | Evidencia |
|---|---|
| `m365_service.graph_patch` | 0 usos; solo un comentario en `endpoints/m365.py:47` |
| `ml_trainer.train_all_orgs` | 0; el worker usa `_por_organizacion(..., train_model)` (`worker.py:537`) |
| `notification_service.notification_service` (instancia) | 0 importadores |
| `profitability_service._fx_cache` | solo `tests/test_exchange_rates.py:225` |
| `reuniones/almacen.borrar_reunion` | 0 en app y en tests |
| `traduccion/idiomas.mismo_idioma` | 0 en app y en tests |
| `scim_service.generate_scim_token` | 0 en app, 5 en tests |
| `s3_service.S3Service.reload_from_db` | 0 llamantes |
| `security_observability` `MASS_EXPORT_THRESHOLD`, `SESSION_CONCURRENT_LIMIT`, `CRED_STUFFING_THRESHOLD` | solo se reexportan; el umbral real está fijo en `>= 3` (`eventos.py:262`) |
| `incident_intelligence_service.auto_resolve_ticket` (l.205) | 0 |
| `smart_catalog_service.update_service_popularity` (l.101), `enrich_catalog_with_stats` (l.416) | 0 |
| `ai_auto_resolution_service.py:866-894` | importa `record_sla_event` y `notify_watchers`, que no existen (`ImportError` siempre) |
| `jira_sync_service.push_comment_to_jira` (l.240), `_resolve_status_to_jira` (l.72), `jira_base_url_segura` (l.49) | 0; `sync_comments` sin efecto |
| `governance_compliance_service.get_executive_dashboard` (l.706); tabla `ComplianceReport` | 0; se escribe y nadie la lee |
| `workflow_designer_service.compile_rules_from_graph`, `rules_json` | se escriben; el motor nunca los lee |
| `workload_service.select_best_agent_ml` (l.195), `select_best_agent_id_by_open_load` (l.83) | 0 |
| `analytics_service.persist_metric_snapshot` (l.146) | solo tests |
| `cmdb_discovery_service._PROVIDER_*`, `_SUPPORTED_PROVIDERS` | 0; k8s, vSphere, Azure, GCP y SNMP sin dependencia |
| Comentario huérfano en `scim_service.py:679-686` | describe una función que ya no existe |
| Modelos `AIAnomaly`, `OAuthState`, `SubcontractorWorkerSkill`, `ImputationSnapshot`, `WhatIfTask` | 0 usos fuera de `app/models` y su tabla no aparece en SQL |

**Stubs o integraciones sin probar de verdad**
- Salesforce: la salida no hace nada. 🔶 23-11-2026: prueba real `POST /salesforce-sync/integrations/salesforce/test` (`/limits` y lectura de `Opportunity`), que declara `salida: no_implementada`. Tabla de todos los conectores en `docs/integraciones/pruebas_de_conexion.md`.
- 7 conectores del marketplace sin código. ⏸ otro agente (integraciones; ya no se marcan `is_certified` sin código, ver la fila de marketplace_service).
- `teams_bot`: no probado contra Azure; lo dice su docstring. ⏸ requiere un tenant de Azure real (fuera de esta ronda); token con cerrojo ✅ 23-11-2026.
- Bots de reuniones. ⏸ requieren cuentas reales de Teams/Zoom/Meet/Recall; webhooks firmados y con empresa ✅ (M8).
- 5 proveedores de discovery CMDB. ⏸ sin dependencia instalada (k8s, vSphere, Azure, GCP); decisión de producto si se instalan.
- `slack_service` en modo simulado. ✅ 23-11-2026: ya no simula éxito (`slack_sin_configurar`).

**Sin tests** (0 ficheros en `tests/` por nombre)
- r–z: `reserva_de_documentos`, `risk_scoring`, `risk_service`, `skill_service`, `sprint_service`, `stripe_service`, `training_service`, `valoracion_de_respuestas`, `widget_de_formulario`, `ws_manager`, `ws_service`. ⏸ inventario de cobertura; cada arreglo de esta ronda trae su test (ronda 2 m–z y SD).
- m–p: `pagination_service`, `presupuestos_seguir`, `proposal_service`, `preferencias_de_aviso`, `presets_de_pais`, `puesta_en_marcha`, `portal_conversation_service`. ⏸ inventario de cobertura (`presupuestos_seguir` ya tiene test: `test_presupuestos_seguir_2026_11.py`).
- service_desk: `sla_del_ticket`, `sla_policy_service`, `status_compat`, `ciclos_de_vida`, `kb_service`, `status_page_service`, `portal_auth_service`, `plantillas_aviso` y la mayoría de los CRUD auxiliares. ⏸ inventario de cobertura (SLA y `status_compat` con tests en la ronda 2 de service_desk).

---

## 6. Valores fijos

**Idioma**
- `IDIOMA_DE_RESPALDO = "es"` en `textos_de_salida.py:29`. ⏸ aceptado 23-11-2026: es el último respaldo cuando ni la persona ni la empresa tienen idioma; el idioma de salida sale de `formato_regional.idioma_de_salida` (otro agente: textos).
- Textos en castellano dentro de servicios (revisión 23-11-2026; claves nuevas en `app/services/textos_de_salida_servicios_m_z.py`, 283 claves es/en/zh, mezcladas en `TEXTOS`; helpers `texto_para` y `aviso_de`):
  - ✅ 23-11-2026 `presupuestos_preparar.py` (aviso de campaña por clave en el idioma de quien lo recibe; el `detail` del error con código es solo respaldo), `presupuestos_seguir.py` (motivo de rechazo de bandeja, título de traspaso/ampliación, títulos y detalle de las alertas de presupuesto, en el idioma de la empresa).
  - ✅ 23-11-2026 `milestone_service.py`: nota de factura y los 4 avisos por `aviso_de`. ⏸ Los avisos usan los tipos `expense_approved`/`expense_rejected` (y `system`) porque `NotificationType` no tiene tipos de hito; añadir `milestone_approved`/`milestone_rejected` exige ampliar el enum de BD (migración, no creada). ✅ 23-11-2026 (migración 200): tipos añadidos y usados por los avisos de hito.
  - ✅ 23-11-2026 `perf_reminder_service.py`, `proveedores/portal.py`, `psa_flows.py` (aviso de imputación, motivos de bandeja, prefijo `[Devuelto para corrección]` guardado en el idioma de quien devuelve).
  - ✅ 23-11-2026 `metrics/projects.py`: etiquetas de estado/tipo/riesgo por clave en el idioma de la empresa (`organization_id` que ya recibía el manejador).
  - ✅ 23-11-2026 `session_security.py`: los motivos de riesgo se guardan como códigos (`ip_change`, `asn_change`...) y `parse_risk_reasons(raw, idioma)` los pinta; las filas antiguas (texto) salen tal cual. El router `auth_sessions.py` pasa el idioma del usuario.
  - ✅ 23-11-2026 `raci_service.py` (reglas de retrospectiva, señales de agotamiento, mensaje de changelog), `scenarios_service.py`, `resumen_de_avisos.py` (correo del resumen diario en el idioma de cada destinatario), `teams_bot.py` (respuestas y «Fuentes:»; ⏸ el prompt de sistema al modelo queda en castellano: no lo ve el usuario), `revenue_service.py` (descripciones de los asientos en el idioma de la empresa).
  - ✅ 23-11-2026 `canal_slack.py`: botones, usos, confirmaciones y notas de adjunto por clave (la tarjeta recibe `idioma`). `sla_event_service.py`: notas de pausa/reanudación.
  - ✅ (ya estaba) `autonomous_agent_service.py`: nombres y avisos de los playbooks de serie por clave desde la pasada del 19-11-2026; el comentario al cliente se traduce al publicarlo (`publicar_texto_del_operador`). ⏸ Quedan en el código los textos de origen en castellano/inglés (id de playbook, palabras clave de detección y el cuerpo del comentario) por ser datos de origen, no salida directa.
  - ✅ 23-11-2026 `rca_wizard_service.py`: pasos del asistente (etiqueta y pregunta, 15 pasos) y nombre/descripción de las plantillas por clave; el estado del asistente guarda el `idioma` con el que se arrancó. ⏸ Los prompts al modelo (`Eres un gestor de problemas ITIL…`, `You are an ITIL problem manager…`) quedan fijos: no son texto de salida. ⏸ Las plantillas de serie sembradas en BD (migración 045) siguen en castellano en la tabla; en el listado salen por clave mientras sean de sistema.
- Textos en inglés fijos:
  - ✅ 23-11-2026 `change_management_service.py`: fases/pasos/comprobaciones del plan de despliegue, puertas manuales, motivos, correos de reversión y de éxito, marca de fast-track, descripción del ajuste de estado (idioma de la empresa del contexto). ⏸ El script de reversión generado (`generate_rollback_automation_script`) y el prompt de evaluación de riesgo con IA siguen en inglés: son un artefacto técnico y un prompt.
  - ✅ 23-11-2026 `governance_compliance_service.py`: hallazgos, resúmenes, niveles CMM y recomendaciones por clave; la puntuación de SLA se reconoce por el código `sla_resolution_breach` y no por el texto del título.
  - ✅ 23-11-2026 `problem_service.py`: causa raíz de respaldo, título/descripción de problemas autodetectados, RFC (título, descripción, justificación, impacto, vuelta atrás). ⏸ Prompts de IA fijos.
  - ✅ 23-11-2026 catálogo del marketplace (`marketplace_service.py`): la descripción sembrada (inglés en BD) sale por `marketplace.desc.<slug>` mientras no la haya cambiado la empresa. ⏸ El texto sembrado sigue en inglés en `integration_connectors.description`.
- ✅ 23-11-2026 `plantillas_aviso.py`: chino (`zh`) en las 15 plantillas (asunto y cuerpo) y en `ETIQUETAS`; el resto del código ya admitía `IDIOMAS` ampliado.
- ⏸ Necesita esquema (migración, no creada): `SLAEvent.note` y `Alert.title/description`, `Invoice.notes`, `RevenueEntry.description` y `review_notes` guardan el texto ya escrito en el idioma de la empresa/usuario que lo generó; para pintarlo al leer en el idioma de quien mira hacen falta columnas `*_key`/`*_params` (patrón de `textos_guardados`). Tipos de aviso de hito en el enum `NotificationType`. ✅ 23-11-2026 (migración 200): columnas creadas y cableadas (escritura y lectura en el idioma del lector) salvo los textos que no salen de una clave (ver DOCS.md, «Migración 200»).

**Moneda**
- `"EUR"` de respaldo en `settings_service/por_empresa.py:74`. ✅ arreglado 23-11-2026: respaldo `DEFAULT_CURRENCY` del entorno ("EUR" solo si tampoco existe).
- «cost_eur» en `ml_features.py:165-171`. ⏸ pendiente: la clave `cost_eur` la devuelve `ai_modules._base._project_internal_cost` (zona a-l); el importe ya es en la moneda de la empresa, solo el nombre engaña. Renombrarla toca sus llamantes de esa zona.
- Docstrings con «€/h». ⏸ pendiente (cosmético): solo comentarios/docstrings (`rate_card_service`, `models/project.py`, `models/advanced_config.py`); sin efecto en ejecución. Se cambian al tocar cada fichero (lo hace el agente de textos).

**Estados como cadenas**
- `"done"`: metrics, olap y `pdf_export_service.py:152`. ✅ arreglado 23-11-2026: `TaskStatus.done` en `metrics/projects.py`, `metrics/remaining.py` (2), `metrics/sprints_tasks.py`, `olap/query_engine.py` y `pdf_export_service.py`.
- `"aprobado"/"borrador"/"facturado"/"comprometido"`: presupuestos. ✅ arreglado 23-11-2026: `presupuestos_preparar.BORRADOR/ENVIADO/APROBADO/RECHAZADO` y `presupuestos_seguir.PEDIDO_*` (pedido, fork m–p) en todas las comparaciones y asignaciones; quedan como texto las claves de los diccionarios de salida (`"comprometido"` como importe), que no son estados.
- `"approved"/"invoiced"`: hitos. ✅ arreglado 23-11-2026: `milestone_service.HITO_*` (pendiente, completado, pendiente de aprobar, aprobado, rechazado, facturado) en todas las transiciones.
- `"pending_client"`: `sla_event_service.py:28`. ✅ (A-SD1: ya usa `TicketStatus.pending_client`).
- `"in_progress"`: `ticket_ops_service.py:131`. ✅ arreglado 23-11-2026: `TicketStatus.in_progress.value`.
- Tuplas de estados abiertos duplicadas en `escalation_service.py:137` y `sla_monitor_service.py:45`, aunque existe `ESTADOS_DE_TICKET_ABIERTOS`. ✅ arreglado 23-11-2026: las dos son `ESTADOS_DE_TICKET_ABIERTOS`. Test.
- `["new","assigned"]`: `autonomous_agent_service.py:717`. ✅ ya usa `TicketStatus.new`/`assigned` (l.766).
- `"recurring_retainer"`: `trabajos_de_fondo.py:248`. ✅ arreglado 23-11-2026: `models.project.FACTURACION_RETAINER`. Test.
- Roles `("admin","hr")`: `user_service.py:174`, `report_builder_service.py:691`. ✅ arreglado 23-11-2026: `user_service.ROLES_QUE_VEN_TARIFAS` (enum `UserRole`) en los dos sitios. Test.
- `"p3_medium"` por defecto en 5 sitios; `"l1"` en `ticket_creation_service.py:291`. ✅ arreglado 23-11-2026 en `ticket_creation_service` (`TicketPriority.p3_medium`, `SupportLevel.l1`) y `alert_correlation_service`. ⏸ restan como valores de configuración o plantilla (playbooks de `autonomous_agent_service`, `metrics_service.priority_matrix`, `monitoring_ingest`, `change_service`): mismo valor, sin error funcional.
- `smart_catalog_service.py:368-383` usa urgencias `"u1_critical"` que no existen. ✅ arreglado 23-11-2026: `TicketUrgency`/`TicketPriority`. Test.

**Umbrales**
- Estado (service_desk) 23-11-2026: auto-resolución con LLM (`AUTO_CONFIG_SETTING_KEY`) y agente autónomo (`SD_AUTONOMY_*_THRESHOLD`) ya son ajustes por empresa; 0,85/0,65/0,80 son solo sus valores por defecto. ⏸ pendiente: `incident_intelligence_service`, `ml_routing_service` y `predictive_analytics_service`: hacerlos ajustes exige declarar claves nuevas en `config_groups/service_desk_config.py` y en el catálogo de ajustes (zona de configuración compartida) y decidir sus valores por defecto.
- IA:
  - `ai_auto_resolution_service.py:37-38` (0,85/0,65) y `:357-361`
  - `auto_resolucion_operaciones.py:54` (0,80)
  - `autonomous_agent_service.py:520,705`
  - `incident_intelligence_service.py:43-50,166-179`
  - `ml_routing_service.py:43-49`
  - `predictive_analytics_service.py:46-75`
- Riesgo: `riesgo.py:284-289` (75/55/30, distintos de `nivel_de_riesgo`, que es configurable). ⏸ otro agente: `cab_service/riesgo.py` es zona CAB (migración 198) y `service_desk/change_impact_service/riesgo.py` es service_desk.
- Presupuestos y margen: `presupuestos_seguir.py:719` (85), `profitability_service.py:305` (10 %), `ml_features` (1,10). ✅ 23-11-2026: el ámbar del cuadro de presupuestos usa `umbrales.cortes("presupuesto")` (aviso de la empresa, `UMBRAL_PRESUPUESTO_AVISO_PCT`; las alertas ya usaban `AlertRule`); `ML_FACTOR_DE_SOBRECOSTE` (1,10 por defecto; ai_config, `.env.example`, README). ⏸ `profitability_service` 10 %: zona a-l (margen/divisas).
- Proveedores: tolerancia 2,0 (`proveedores/facturacion.py:275`). ✅ ya configurable por empresa: `PROVEEDORES_TOLERANCIA_CONCILIACION_PCT` (Settings + catálogo); el 2,0 es solo el respaldo.
- Seguridad: `security_observability/eventos.py:28-33,262`. ✅ arreglado 23-11-2026: ajustes `SOC_*` (ver 4.3 r–z).
- Webhooks: `webhooks.py:189-190` (120 por 60 s). ✅ arreglado 23-11-2026: `WEBHOOK_OUTBOUND_PER_MIN` (automations_config, `.env.example`, README).
- Horas y jornada: `scheduled_reports.py:56` (hora 8), `sla_service.py:189-190` (8-18), `ticket_ops_service.py:21` y `planificador/calendario.py:63` (8 h). ✅ 23-11-2026 `scheduled_reports`: `HORA_DE_ENVIO_POR_DEFECTO` y en hora local de la empresa (el informe fija `send_hour`). ⏸ `sla_service.add_working_hours` (8-18) y `planificador/calendario` (8 h) son valores por defecto de firma/clase: el SLA usa su calendario (`horas_sla_entre`) y el planificador el horario efectivo de cada persona; quitar el defecto obliga a revisar todos los llamantes. `ticket_ops_service`: service_desk (otro agente).
- Tamaño de adjuntos: `adjuntos_de_canal.py:33` (16 MB). ⏸ otro agente (service_desk).

**URLs, versiones y marca**
- Versiones de API fijas: Salesforce `v57.0` (`salesforce_service.py:148`), WhatsApp `v20.0` (`canal_whatsapp.py:59`). ✅ 23-11-2026 Salesforce: `SALESFORCE_API_VERSION` (automations_config, `.env.example`, README). ⏸ WhatsApp: service_desk (otro agente).
- Canales de Slack: `#contecflow-alerts` y `#general` (`slack_service.py:38,105,116`). ✅ arreglado 23-11-2026: `SLACK_CANAL_POR_DEFECTO`.
- Regiones fijas: `eu-central-1` (`recall.py:74`), `westeurope` (`azure_stt.py:62`). ✅ (comprobado 23-11-2026) ya configurables: Recall por empresa en la configuración de reuniones (`reuniones/config.py`, `bots.region`) y Azure con `AZURE_SPEECH_REGION` (por empresa); los literales son solo el valor por defecto.
- Rutas: `/var/log/changes` (`change_management_service.py:325`); `/portal` y `/service-desk` sobre el `FRONTEND_URL` global (`ticket_event_processor.py:144-147`). ⏸ otro agente (service_desk).
- Ventana `"22:00-06:00"` (`change_rollout_service.py:260`). ⏸ otro agente (service_desk).
- Prefijos de numeración `"INV"` y `"PRJ"` repetidos en 3 y 6 sitios. ✅ arreglado 23-11-2026: `numbering.PREFIJO_PROYECTO`/`PREFIJO_FACTURA` (solo al crear la secuencia de la empresa; la configurada manda) en `cartera_service`, `demanda/ejecucion`, `milestone_service`, `pipeline_service`, `plantillas_de_proyecto`, `project_service` y `trabajos_de_fondo`. ⏸ `billing_reports_service/facturas.py` (zona a-l) y las semillas (`seed_parts/core.py`, `advanced_config_service/semillas.py`, que son la definición).

---

## 7. Arquitectura

1. **El estado del ticket no tiene una vía única.** `apply_ticket_update` es el camino central, pero 13 módulos escriben `status` directamente: SLA, ops, comentarios, CSAT, fusión, conversaciones, Jira, los dos motores de IA, catálogo, carga de trabajo, voz y escalado. Los cambios tampoco tienen máquina de estados. Hace falta una función de transición con validación, historial, SLA, auditoría y eventos. — 🟡 parcial (otro agente, service_desk, 23-11-2026): `cambiar_estado_por_automatismo` para los automatismos (A-SD11) y máquina de estados de cambios `TRANSICIONES_DE_CAMBIO` (C-SD3); los demás escritores directos siguen en su zona.
2. **El reloj del SLA está implementado en 6 sitios con criterios distintos:** `_vencido`, `vencimiento_efectivo`, `sla_event.resume`, el filtro de consulta, `predictive` y `comment_service`. — 🟡 parcial (otro agente, 23-11-2026): pausas en minutos del calendario y `vencimiento_efectivo` común (A-SD2); queda `billing_reports_service/sla.py` (zona a-l).
3. **Funciones duplicadas.** — ⏸ pendiente (refactor de arquitectura, sin cambio funcional en esta ronda): unificar exige elegir la implementación buena de cada fila y migrar llamantes de varias zonas. Hecho de paso: la RCA con LLM ya no está rota en ninguno de los dos sitios (A-SD10) y el blast radius va en el mismo sentido (A-SD20).

   | Función | Implementaciones |
   |---|---|
   | Auto-resolución | 2 motores (playbooks y LLM) que no se hablan |
   | Búsqueda semántica en el KB | 3 |
   | Asignación de agente | 4 (`ml_routing`, `workload`, `incident_assignment`, `SemanticAssigner`) |
   | Puntuación de riesgo de cambios | 4 |
   | Seguimiento de despliegue | 3 |
   | Blast radius | 2, con resultados opuestos |
   | RCA con LLM | 2 (las dos rotas igual) |
   | CRUD de hitos | 3 |
   | Paginación | 2 |
   | Funciones de tareas | 5, copiadas en `task_service` y `tasks/` |
   | Caminos de Slack | 3 (`slack_service`, `integrations`, `entrega_saliente`) |
   | Programadores de informes | 2 (`scheduled_reports`, `bi_report_delivery_service`) |
   | Motores de flujo | 5 |

   Además, dos módulos llamados `change_service.py` y dos CAB.
4. **Credenciales globales en una plataforma multiempresa.** — 🟡 parcial 23-11-2026: por empresa ya `TEAMS_WEBHOOK_URL` (A-MP4), `STRIPE_SECRET_KEY` (A-RZ6), Slack de cambios (service_desk) y SCIM (token por empresa cableado; el global solo vale con `SCIM_ALLOWED_ORG_ID` o en desarrollo). ✅ `AZURE_*`/Graph (A-MP3, 23-11-2026, segunda ronda); ⏸ SMTP de los avisos, Twilio de envío y S3 (migración).
   - Del `.env`: `AZURE_*`, `TEAMS_WEBHOOK_URL`, `STRIPE_SECRET_KEY`, `SCIM_BEARER_TOKEN`, el SMTP de los avisos, el Twilio de envío y el Slack de cambios.
   - Hay registro de credenciales por empresa (`integration_credentials_service`), pero estos módulos no lo usan.
5. **El aislamiento depende del contexto.** `get_fx_rate`, `seguimiento`, `_centros_de_coste`, la creación de tickets y `workflow_triggers` funcionan bien en una petición, pero fugan en el worker o con org None. Arreglo de raíz: pasar `org_id` explícito en todos los servicios que llama el worker y rechazar org None en los canales.
   - 🟡 parcial 23-11-2026: la red de debajo ya está. `TENANT_SESION_SIN_CONTEXTO=cerrar` es el defecto: una sesión sin empresa ni contexto de sistema declarado lanza `TenantIsolationError` en vez de leer sin filtro. Las tareas de Celery declaran `tarea:<nombre>`, `segundo_plano` declara lo que ejecuta en línea, y las `SessionLocal()` a mano de `app/` (50 sitios)
 y las 93 rutas anónimas declaran su contexto o publican su empresa (docs/seguridad/rutas_anonimas.md). Falta lo que este punto pide servicio a servicio: pasar `org_id` explícito en `get_fx_rate`, `seguimiento`, `_centros_de_coste` y `workflow_triggers` cuando corren en una tarea declarada de sistema (ahí siguen sin filtro, pero declarados y con nombre). Son servicios de este informe que arreglan otros agentes.

6. **Datos de negocio y personales en blobs JSON de `AppSetting`:** voz, aprovisionamiento con secretos, despliegues, formularios, campos dinámicos, snapshots y cuotas. No tienen esquema ni integridad referencial, quedan fuera de retención y supresión, y las escrituras se pisan. — ⏸ pendiente: migración (ver A-MOD3 en §3.2, con las tablas propuestas). Las cuotas (`traffic_control`) siguen en `AppSetting` pero ya en sesión propia con `FOR UPDATE` (no se pisan ni confirman la sesión del llamante).
7. **Gobernanza de IA desigual.** Solo `ai_suggest` pasa `user_id` a `call_ai`. El resto pierde guardrails y redacción de datos personales sin que se note. Arreglo: hacer `user_id` (o un usuario de sistema) obligatorio en `call_ai`. — ✅ 23-11-2026 (otro agente, C-SD2): `call_ai` sin usuario aplica las políticas de la empresa con `SujetoDeSistema` (guardarraíles y redacción); RCA, catálogo y riesgo pasan el usuario.
8. **Commits dentro de servicios auxiliares** (`traffic_control`, `security_observability.record`, `teams_bot`, `reglas_sla`, `status_compat`), incluso en GET. Rompen la atomicidad del llamante. — ✅ 23-11-2026: `traffic_control.consume_quota` y `security_observability.emit` en sesión propia (no confirman la del llamante); `reglas_sla` y `status_compat`, otro agente (service_desk). ⏸ `teams_bot.respuesta_de_la_base`: su commit es el fin de la petición del webhook del bot (hace de endpoint), se deja.
9. **Dinero en float de punta a punta:** 89 columnas `Float`, 98 campos de esquema `float`, y `round(...,2)` repartido por el código, sin `Decimal`. — ⏸ pendiente: migración por dominios (A-MOD2; plan y test de detección en §3.2).
10. **Excepciones silenciadas:** 101 `except Exception` solo en m–p. `metrics` y `olap` devuelven `[]`/`{}` sin distinguir «sin datos» de «error». — 🟡 parcial 23-11-2026: el PDF BI distingue «error de OLAP» (503 `informe_bi_sin_datos`) de «sin datos». ⏸ `metrics` y `olap` siguen devolviendo `[]`/`{}`: cambiarlo afecta a todos los paneles (decidir el contrato `{datos, error}` con frontend).

**Sin verificar**
- Si `Session.get` pasa por el filtro de tenant cuando el objeto no está en el mapa de identidad. ⏸ sin verificar (no ejecutado en esta ronda).
- La FK de `approved_by` en la migración. ✅ M-MOD5: ya no se escribe un texto en `approved_by`.
- El valor real de `SD_CHANGE_AUTO_APPROVE_MAX_RISK`. ⏸ sin verificar (valor por empresa en producción).
- Si hay tickets con `organization_id` NULL en producción. ⏸ sin verificar (dato de producción; M-MOD1 describe la cuarentena).
- Si `PRAGMA foreign_keys` está activo en SQLite. ⏸ sin verificar.
- Si `baja_de_empresa_service.purgar` cubre las 353 FK a `organizations` sin `ondelete`. ⏸ sin verificar (A-MOD1 describe la migración `ondelete`).
