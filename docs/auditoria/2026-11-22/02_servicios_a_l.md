# Auditoría 2026-11-22 · 02 · Servicios `app/services/` (a…l)

Auditoría de **solo lectura**. No se ha modificado código, no se ha hecho commit y no se han ejecutado tests ni typecheck.

## 0. Estado de los arreglos (23-11-2026)

- Críticos: C1, C2, C3 y C5 ✅ (C5 con HMAC del llavero: ✅ migración 201, 23-11-2026); C4 ✅ (zona SSRF, 23-11-2026).
- Altos (64): ✅ todos, cerrados en su fila el 23-11-2026: 55 por este informe (A1-A17, A19, A22-A26, A29-A36, A40-A57, A59-A64; A8, A22, A24, A25 y A50 completados en la fase 2) y 9 por la zona de seguridad de entrada/salida (A18, A20, A21, A27, A28, A37, A38, A39) y la migración 196 (A58). A7: API hecha, ➡️ pantalla de aprobación en la zona de frontend. A42: ➡️ `approved_by/approved_at` en la migración 200.
- Medias (109): ✅ todas marcadas en su fila el 23-11-2026 (arreglo, verificación o decisión de estándar), salvo las de otras zonas, marcadas «➡️» con referencia: portal de clientes (M61, M63-M65 y el resto de M62), CAB (M66), contratos (M20), `sod_rules`/`issue_types` de la migración 200 (M97, M98, M100). Apartado 5: las 9 «fantasma», los stubs y el código sin uso, marcados uno a uno (✅ / decisión / ➡️).
- Bajas (42, §3.4): ✅ todas marcadas en su viñeta el 23-11-2026; ➡️ las de otras zonas (`grc_sod` → migración 200; `integrations.py:868` → textos; `exportador_tabular` → exportaciones; `bi_o365` → M365; tres del portal de clientes).
- Hardcode de idioma (§6): ✅ Excel de gastos (cabeceras, estados, «Sí/No» por clave en `textos_de_salida`), «Sin cliente» ya no se guarda; ✅ 23-11-2026 el grueso de la lista (ver §6: absence, alert, expense/gastos_avanzados, ai_chat/tool_execution, voz, reuniones, portal de clientes, cmdb, cab/correo, custom_fields, issue_type, horas_extra, jornadas, imputaciones, externos, lecciones, grc_sod, automations, bots, plantilla de demanda opcional) con 338 claves nuevas es/en/zh (las del portal en los 8 idiomas) en `textos_de_salida_servicios_a_l.py`; ⏸ los restos con motivo en §6 (prompts al modelo, `detail=` de respaldo con código, `NotFoundError` de advanced_config, columnas que exigen migración).
- Detalle por arreglo y verificación: `DOCS.md` («Arreglos de la auditoría 2026-11-22, informe 02»).

## 1. Resumen

### Alcance

- 429 ficheros de `git ls-files app/services` cuyo primer segmento empieza por `_`, a…l.
- 111.365 líneas en 120 entradas de primer nivel: 95 ficheros sueltos y 25 paquetes.
- Se repartió en 5 lotes revisados en paralelo y luego se consolidó.

### Cobertura real

- Leído a fondo: lo crítico (ABAC, IA que ejecuta herramientas, proveedores de IA, aprobaciones, `ask_the_data`, facturación, RGPD, webhooks, e-firma, divisas, discovery CMDB, imputaciones, horas extra, claves y credenciales, PDFs).
- Revisado por muestreo y grep, y marcado «sin verificar» en el texto:
  - `cmdb_software/` (≈45 % sin leer).
  - `collaboration/messages.py`, `_search*`, `workspaces/*` y `portal.py`.
  - `demanda/` (solo cabeceras).
  - `bi_collaboration_service/`, `bi_smart_alerts/metrics` y `ausencias/{turnos,cupos}`.
  - `alm_integracion/` y gran parte de `alm_uso/`.
  - `cab_service/{busqueda,riesgo,widgets_y_onboarding}`.

### Contexto que condiciona muchos hallazgos (verificado)

El aislamiento entre empresas no está en los servicios. Lo pone un filtro global de sesión (`app/db/session.py`: `do_orm_execute` + `with_loader_criteria`), que tiene tres huecos:

- **Solo filtra SELECT.** `session.py:456`: `if not execute_state.is_select: return`. Los `UPDATE`/`DELETE` masivos (`query(...).update(...)`) no se filtran.
- **Se salta con sesión sin inicializar o con superadmin.** `session.py:476`: `if is_superadmin is None or is_superadmin is True:`. Eso afecta a workers, jobs, endpoints públicos y superadmin.
- **`ServiceBase._scoped` falla abierto.** `app/services/base.py:35`: `if self._org_id and hasattr(...)`. Sin `org_id` no filtra.

Por eso, una consulta «por id sin `organization_id`» es defensa en profundidad dentro de una petición HTTP normal, pero **fuga real** en jobs, worker, superadmin y UPDATE/DELETE masivos. Los hallazgos se gradúan con ese criterio. RLS de Postgres (`app/db/rls.py`) puede mitigar parte: sin verificar en producción.

### Recuentos

| Severidad | Nº |
|---|---|
| Crítica | 5 |
| Alta | 64 |
| Media | 109 |
| Baja | 42 |
| **Total** | **220** |

- Marcadores literales `TODO`/`FIXME`/`NotImplementedError`: **0**. Solo hay un `NotImplementedError` abstracto legítimo, en `alm_uso/proveedores/base.py:144`.
- Lo inacabado no está marcado: son ~30 stubs o simulaciones silenciosas (apartado 5).
- Ningún **módulo** entero es código muerto, porque todos tienen importadores fuera de tests. Sí hay ~25 funciones o constantes muertas y 3 funcionalidades «fantasma» (apartado 5).
- Verificados personalmente sobre el código, además de por los lotes: C1, C2, C3, A-ABAC, A-SSRF IA, A-CSV, A-gastos Excel y el filtro de sesión.

### Lo más urgente

1. **C1 · Auto-aprobación con contexto falso.** El contexto lo manda el cliente (`approval_engine/requests.py:531`).
2. **C2 · Discovery CMDB.** Un fallo del proveedor retira todos sus CIs.
3. **C3 · Retención de chat.** Purga toda la empresa ignorando el ámbito de la política.
4. **C4 · SSRF en la URL del proveedor de IA.** La API key viaja a un host arbitrario.
5. **C5 · Cadena de auditoría de colaboración.** Se bifurca porque el lock no protege nada.

Después vienen los fallos funcionales graves:

- ABAC no permite editar ni borrar políticas (500).
- Inyección de fórmulas en exportaciones.
- Divisas a 1,0 en silencio.
- Imputaciones que cuentan registros borrados y fechas en UTC.
- Facturación de imputaciones sin acotar.
- Portal de cliente fail-open sin proyectos.

---

## 2. Inventario por módulo

Leyenda de estado: **C** completo · **C*** completo con defectos · **P** parcial · **S** stub/simulado · **SV** sin verificar a fondo.

### 2.1 `_pdf_marca` … `alm_uso`

| Módulo | Qué hace | Qué no hace / deja a medias | Usado por | Estado |
|---|---|---|---|---|
| `_pdf_marca.py` | Paleta y marca de empresa para PDFs | Solo presentación | Generadores PDF | C |
| `abac.py` | Motor ABAC: operadores, políticas, auditoría, analítica | `.one_or_404()` inexistente (editar/borrar roto); `json_extract` solo SQLite | `endpoints/abac.py`, `enforce_abac` | P |
| `abac_recursos.py` | Atributos `recurso.*` de la fila | Solo 8 tipos; recurso no resuelto → `{}` | `abac.py` | C |
| `absence_service.py` | Fachada de ausencias y saldos | `count_working_days` muerto; etiquetas en castellano | Endpoints de ausencias | C* |
| `accounting_hub_service.py` | Cola de facturas a Xero/QuickBooks | Push con `lines: []` siempre vacío (`:153`); «sincronizado» = texto en `internal_notes` | `accounting_hub`, `cab_service` | P |
| `activity_service/` | Feed, demanda/what-if, scorecard de proveedores, salud, tareas recurrentes | Simulación aproximada; tendencia invertida; numeración con carrera | Endpoints | C* |
| `adhoc_analytics_service.py` | 4 métricas, drilldown, cross-filter | Sin autorización por rol; `strftime` solo SQLite | `analytics_extended` | P |
| `advanced_config_service/` | Roles, tipos, tarifas, vacaciones, numeración, campos | Casi sin `audit_log`; N+1 en saldos | `advanced_config` | C* |
| `ai_chat/` | Chat con contexto del tenant, agente con 38 herramientas | Aprobación humana sin endpoint; bucle SSE duplicado | `ai_chat`, worker | P |
| `ai_chat_service.py` | Fachada | No define `quick_answer`, que `collaboration/bots.py:506` importa | Bots, tests | C |
| `ai_copilot_service.py` | Sugerencias Gantt y anomalías de imputaciones | Sin rol/ABAC | `ai_suggestions` | P |
| `ai_governance.py` | Guardarraíles (PII regex, palabras, tokens), políticas | Fail-open; sin org no hay guardarraíles | `ai_provider_service` | P |
| `ai_modules/` | Oráculo, voz, reuniones, contratos, KB, portal, predicciones | Voz relanza el LLM al confirmar; portal sin guardarraíles; `predict_overrun_ml` no es ML | `ai_modules_service` | P |
| `ai_modules_service.py` | Fachada | — | Endpoints, `ml_trainer` | C |
| `ai_planning_service.py` | Estimación de horas y triaje (heurística + IA) | Salida del LLM sin validar; import SSRF sin uso | `ai_planning` | P |
| `ai_provider_service/` | Proveedores de IA, respaldo, tope diario, uso | **Sin protección SSRF** | Todo `call_ai` | P |
| `ai_tools.py` | Tool-use Anthropic/OpenAI/Gemini | Sin SSRF; key de Gemini en la URL | `agent_loop` | C* |
| `alert_service.py` | Motor y consulta de alertas | Fallback legado cross-tenant; IDOR al resolver | Worker, endpoints | P |
| `alm_actas.py` | Actas de entrega con PDF y firma | Fallos tragados; commit dentro de GET | `alm_asignaciones` | P |
| `alm_ajustes.py`, `alm_ciclo_de_vida.py` | Ajustes y estados ALM | — | `alm_*` | SV |
| `alm_asignaciones.py` | Asignación de licencias/activos, préstamos | Sin bloqueo: sobreasignación de asientos | `alm_*` | C* |
| `alm_conciliacion.py` | Facturas de proveedor frente a contrato | Float | `alm` | C* |
| `alm_costes.py` | Coste diario, ocioso, refacturable, comprometido | Float; FX a una sola fecha; N× por mes | Rentabilidad, presupuestos | C* |
| `alm_integracion/` | ALM con catálogo, bajas y kits | — | `service_desk` | SV |
| `alm_renovaciones.py` | Renovaciones, avisos, préstamos | N+1 en avisos | Worker `alm_daily` | C |
| `alm_service.py` | CRUD ALM, panel, cumplimiento | Suma monedas sin convertir | `alm` | C* |
| `alm_uso/` | Uso real de licencias/dispositivos (M365, Google, Okta, Jamf, Intune) | M365/HTTP correctos; resto sin verificar | Worker, endpoints | C/SV |

### 2.2 `analytics_service` … `bookings_service`

| Módulo | Qué hace | Qué no hace / deja a medias | Usado por | Estado |
|---|---|---|---|---|
| `analytics_service.py` | KPIs, utilización | `if project_ids:` trata `[]` como «todo»; N+1 | `analytics`, storytelling | C* |
| `approval_engine/` (13) | Pasos, quórum, SoD, timeouts, aprobación por correo | Contexto de reglas lo pone el cliente; JWT de correo reutilizable | Approvals, ausencias, presupuestos | C* |
| `approval_workflows.py` | Fachada (13 líneas) | — | `peticiones` | C |
| `ask_banco.py`, `ask_verificacion.py` | Banco de preguntas y verificación de SQL | — | `ask_the_data` | C |
| `ask_the_data.py` | Texto→SQL→DuckDB sobre vistas por empresa | Sin `org_id` no filtra; fallback SQL cableado en español | `analytics` | C* |
| `ask_valores_reales.py` | Pistas con valores reales | Manda nombres y correos al LLM | `ask_the_data` | C* |
| `audit.py` | `audit_log`, `auditar_y_confirmar` | No sella org/IP por sí mismo | Muchos | C |
| `ausencias/` (11) | Catálogo, saldos, cupos, turnos, solicitudes, bolsa | `ROLES_QUE_GESTIONAN` muerto; `pasada_diaria(org)` ignora `org` | `absences`, worker | C/SV |
| `auth_service/` (8) | Tokens efímeros, MFA, SSO, WebAuthn | Límite de reseteo en memoria; GET+DELETE no atómico; email en log | Auth | C* |
| `automation_events.py` | Bandeja de eventos | Sin `SKIP LOCKED`: efectos duplicados | Disparo, worker | C* |
| `automations_service/` (6) | Reglas y acciones (webhook, correo, tareas) | Sin idempotencia; SSRF propio con huecos | `automations` | C* |
| `avisos_del_portal.py` | Avisos al cliente del portal | — | Mensajes, tickets | C |
| `baja_de_empresa_service.py` | Cuarentena, ZIP, purga con bloqueo legal | ZIP con secretos y `Decimal`→`float`; no atómico | `organizations`, worker | C* |
| `baselines_service.py` | Líneas base | — | `baselines`, `tasks` | C |
| `bi_anomaly_service.py` | Anomalías y churn | **Churn entrenado con datos sintéticos** | `bi_anomaly` | S |
| `bi_bookmarks_service.py` | Marcadores y enlace público | Token sin caducidad ni revocación | Endpoint | C* |
| `bi_collaboration_service/`, `bi_conditional_delivery`, `bi_dashboard_collab` | Colaboración y entrega condicional BI | Blob JSON en `AppSetting` | Endpoints | SV |
| `bi_data_versioning_service.py` | Versiones de datasets | **Guarda datos demo como versión** | Endpoint | S |
| `bi_embed_service.py` | JWT de embebido | Clave derivada de `SECRET_KEY`, fuera de la rotación | `m365_bi_embed` | C* |
| `bi_etl_service.py` | Conectores ETL cifrados | — | Endpoint, worker | C |
| `bi_export_service.py` | xlsx/pptx | — | Endpoint | C |
| `bi_forecasting_service.py` | Holt, lineal, ARIMA, Prophet | Banda siempre con residuos de Holt | Endpoint | C* |
| `bi_gdpr_service.py` | Consentimientos, DSR, borrado | DSR «completed» antes de borrar; rectificación y restricción sin aplicar; seudónimo sin sal | Endpoint, informe | P |
| `bi_governance`, `bi_intelligence`, `bi_platform`, `bi_storytelling` | Gobierno, previsión y narrativa | Float; duplica Prophet y z-score | Endpoints | SV |
| `bi_o365_service.py` | Informes de uso de Graph | Datos por persona sin retención | Endpoint | C* |
| `bi_query_builder_service.py` | Constructor sin SQL libre | — | Endpoint | C |
| `bi_report_builder_v2_service.py` | Presets de informes | — | Endpoint, entrega | C |
| `bi_report_delivery_service.py` | Envío programado de informes | **`cron_expression` se guarda y no se usa**; deriva; destinatarios libres | Worker | P |
| `bi_smart_alerts/` + `_service.py` | Alertas inteligentes (fachada + paquete, no duplicado) | — | Endpoints | SV |
| `bi_tokens_service.py` | Tokens `bi_*` | `scopes` y `requests_today` no se aplican | `bi_tokens` | P |
| `billing_reports/` (sin `__init__`) | Catálogo e historial de importación | Nombre confuso frente a `billing_reports_service` | Endpoint | C |
| `billing_reports_service/` | Facturas, CSV, SLA, smartmatch | UPDATE masivo de imputaciones sin acotar | Endpoints | C* |
| `bookings_service/` | Reservas, claves API, divisas, recurrentes, Terraform/Ansible | Aprovisionamiento compartido entre empresas y con el entorno del worker | `bookings` | C* |

### 2.3 `bpmn_engine` … `cmdb_software`

| Módulo | Qué hace | Qué no hace / deja a medias | Usado por | Estado |
|---|---|---|---|---|
| `bpmn_engine.py` | Ejecuta BPMN (defusedxml, sin eval) | service/script/send/businessRuleTask se marcan completados sin hacer nada; sin gateway inclusivo ni subprocesos | `bpmn_*`, worker | P |
| `bpmn_process_service.py` | CRUD, versiones, publicación, catálogo | Versión `max+1` sin bloqueo; borrar no cancela instancias | Endpoints | C |
| `branding_service.py` | Marca y traducciones | CSS vars solo acotadas por longitud | `branding`, portal | C |
| `budgets_service.py` | Presupuestos, escenarios, plan frente a real | Float; N+1; aprobación sin bloqueo | `budgets`, `approval_engine` | C* |
| `cab_service/` (10) | CAB, correo, RGPD, integraciones, webhooks entrantes | Correo «simulado» devuelve True; export RGPD en claro e indefinido | `cab`, `integrations_hub` | P/SV |
| `campaign_pdf.py` | PDF de evaluación 360 | Sin escape; Helvetica sin chino | `performance` | C* |
| `capacity_planning_service.py` | Conflictos de reservas y nivelado | Cuenta fines de semana | `bookings` | C* |
| `capacity_service.py` | Planes de capacidad | Función duplicada literal | `capacity` | C |
| `cartera_service.py` | Propuestas → proyecto | Leído 200/360 | `cartera_intake` | C |
| `change_service.py` | CR de proyecto | Sin validar transiciones | `changes`, portal | C* |
| `client_portal_service/` (11) | Portal externo completo | Fail-open sin proyectos; mensajes internos visibles; firma sin certificado | `client_portal` | C* |
| `client_service.py` | Clientes, contactos, licencias, contratos | Funciones sin usuario (alcance); suma de contratos multimoneda como EUR | `clients` | C* |
| `clientes_internos/` (8) | Unidades internas, costes, showback/chargeback | Errores de coste tragados; NULL-org visible | `clientes_internos` | P |
| `cmdb/` (5) | Discovery AWS/K8s/vSphere/Azure/GCP/SNMP, reconcile | **Fallo = retirar todo**; credenciales de plataforma; sin SSRF | `service_desk/cmdb`, worker | C* (inseguro) |
| `cmdb_service.py` | **No es CMDB**: wiki, Kanban, plan de sprint, SLA | `create_wiki_export_job` crea filas que nadie procesa | `endpoints/cmdb.py` | P |
| `cmdb_software/` (28) | CMDB de software, SBOM, avisos, terceros, riesgo | Truncado = «resuelto»; SSRF; relé de credenciales | Endpoints | C*/SV |

### 2.4 `collaboration` … `expense_service`

| Módulo | Qué hace | Qué no hace / deja a medias | Usado por | Estado |
|---|---|---|---|---|
| `collaboration/` (36) | Chat, canales, llamadas, adjuntos, retención, búsqueda, bots | Retención ignora el ámbito; cadena de auditoría rota; AV fail-open; webhooks salientes sin emisor; `livekit_room="placeholder"`; refresh OAuth sin usar | Endpoints | C*/SV |
| `conectores/` (5) | OAuth hacia contecmind y contecintelligence | `base_url` sin SSRF; caché de tokens sin tope | Endpoints | C* |
| `contract_service.py` | Contratos, órdenes de trabajo, bolsa de horas | Sin empresa → sin filtro; horas sin `is_active` | Endpoints | C* |
| `cost_service.py` | Coste/hora y perfiles | Sin moneda; perfiles solapados | Baselines, costes | C* |
| `costes_de_proyecto.py` | Gastos, subcontrata y ALM en moneda del proyecto | FX cae a 1,0 | EVM, rentabilidad | C* |
| `currency_rates_service.py` | Tipos manuales y resolución | **1,0 en silencio**; `get_report_data` ignora parámetros | Facturas, políticas | P |
| `custom_fields_service.py` | Campos y flujos por proyecto | `transition_task` sin efectos ni auditoría | 2 refs | C* |
| `customer_health_service.py` | Salud de cliente | **Usa tickets de otros clientes**; `portal_score=50` | 1 ref | P |
| `dashboard_service.py` | KPIs, rentabilidad | Sin empresa → todas; cuarto cálculo de margen | 3 refs | C* |
| `datos_personales_de_contactos.py` | RGPD de contactos: copia, bloqueo, anonimizado | Con `org=None` anonimiza en todas; no revoca sesiones | `cab_service/gdpr` | C* |
| `deliverable_service.py`, `dev_plan_service.py`, `developer_portal_service.py` | Entregables, planes, apps OAuth | `setattr` libre; `can_edit_plan` sin empresa | 1 ref c/u | C |
| `documents_service.py` | Documentos, versiones, permisos | Empresa deducida por `created_by`; ids sin validar | 8 refs | C* |
| `documents_collab_service.py` | Snapshots CRDT | Sin control de acceso ni tamaño | `documents_collab` | C* |
| `demanda/` (17) | Motor de flujos con log encadenado | Sin `with_for_update`; flujo piloto de un cliente en el producto | Worker, seed | C/SV |
| `enterprise_service/` (7) | Webhooks, SSO, subcontratas, previsión | Webhook suspendido irrecuperable; factura de subcontrata con estado libre | Endpoints | P |
| `entrada_service.py` | Selección de tenant, cambio, suplantación | `is_active` de empresa sin verificar | 17 refs | C |
| `entrega_de_webhooks.py` | Entrega, reintentos, cortacircuitos | TOCTOU DNS; `attempt` sin rellenar | `worker:397` | P |
| `entrega_saliente.py` | Slack/Teams/correo con `cliente_httpx` | — | Varios | C |
| `epics_service.py` | Wiki, épicas, NQL, filtros | **Operadores NQL ignorados** | 1 ref | P |
| `esign_providers.py`, `esign_service.py` | DocuSign y Adobe reales + modo manual | Manual sin evidencia; token sin caducidad; 401 por texto | `esign` | C* |
| `evm_service.py` | EVM, curva S, snapshots | AC sin `is_active` ni fecha ni moneda | 5 refs | C* |
| `evolucion_del_margen.py` | Serie de margen | Tercer cálculo de margen | 3 refs | C |
| `exchange_rate_service.py` | BCE y OpenExchangeRates | Inverso a 6 decimales; `app_id` en la URL; `get_rate` muerto | Worker | C* |
| `expense_service.py` | Revisión, Excel, OCR, ciclo de gastos | **Filtro de categoría del Excel mal indentado**; fórmulas | `expenses`, `ai_chat` | C* |

### 2.5 `explicar_acceso` … `lecciones`

| Módulo | Qué hace | Qué no hace / deja a medias | Usado por | Estado |
|---|---|---|---|---|
| `explicar_acceso.py` | Explica por qué se permite o deniega una ruta | Regex sobre el código fuente; a menudo «unknown» | `grc` | P |
| `exportador_tabular.py` | CSV/XLSX común | **Sin defensa de fórmulas**; coma en lugar de `;` | `analytics_extended`, `alm_uso` | C* |
| `externos/` (7) | Alta, asignación, horas, tarifas y conciliación de externos | Cuenta borradas; descarta partes enteros | `deps`, subcontratas | C* |
| `formato_regional.py` | Moneda, idioma, fecha, zona por empresa | `formatear_importe` siempre en formato USA | ~60 módulos | C* |
| `gastos_avanzados.py`, `gastos_politicas.py` | Justificantes, reparto, km, políticas | Float; borrado de justificantes sin retención; sin lista blanca de tipos | `expense_service` | C* |
| `git_service.py` | Webhooks GitHub/GitLab, PR, despliegues | `project_id` nunca asignado (invisibles); sin idempotencia | `git_integration` | P |
| `governance_service.py` | Policy packs, evidencias, interruptores de IA | Uso de IA sin filtro de empresa | `governance` | P |
| `grc_service.py`, `grc_sod.py` | Matriz de permisos y SoD | SoD mayormente decorativo; log GRC sin org | `grc`, `approval_engine` | P |
| `horario/` (4) | Horario efectivo persona×día | `_empresa` mezcla empresas sin filtro; sin DST | Planificador, horas extra | C* |
| `horas_extra/` (8) | Peticiones, control, nómina | Sin límite legal activo por defecto; N+1; fail-open | `imputation_service` | C* |
| `imputation_service/` (5) | Alta, edición y cronómetro de imputaciones | Cuenta borradas; fechas UTC; el cronómetro se salta controles | Endpoints, voz, bots | C* |
| `informe_de_cumplimiento.py` | ~25 controles firmados con Ed25519 | Controles tautológicos; clave pública dentro del firmado | `governance`, `grc` | P |
| `integration_credentials_service.py` | Credenciales cifradas por empresa | Respaldo global contradictorio; URLs sin validar | 20+ servicios | C* |
| `integration_test_service.py` | Sondas «probar conexión» | **SSRF**; DocuSign stub; 8 proveedores sin sonda | `settings` | P |
| `integrations.py` | Slack/Teams, Jira fino, Xero/QB, comandos | Eventos sin plantilla se pierden; Slack imputa saltándose todo; QB con cliente «1» | Varios | P |
| `invoice_pdf.py` | Factura PDF en 8 idiomas | Sin datos del emisor; sin escape; sin fuente CJK/PL; `discount_pct` no se pinta | `invoices` | P |
| `issue_type_service.py` | Tipos de incidencia, «FTS» | No es FTS (ILIKE); índice sin purga | `issue_types` | P |
| `jira_service.py` | Capa Jira única | Endpoint de búsqueda probablemente inexistente; estados desconocidos → `todo` | Endpoints, worker | P |
| `key_management.py` | Llavero JWT, KMS, rotación | Caché JWT sin refresco entre procesos; rotación omite muchas columnas | `security`, worker | P |
| `lecciones.py` | Lecciones aprendidas (IA opcional) | Sin acceso por origen; textos en castellano guardados en BD | Endpoints | C* |

---

## 3. Hallazgos por severidad

Formato: **ID · fichero:línea**, seguido de evidencia, impacto y arreglo. Rutas relativas a `app/services/` salvo que se indique otra.

### 3.1 Críticas (5)

**C1 · `approval_engine/requests.py:67` y `:531`: auto-aprobación con contexto que manda el cliente.** *(verificado)*
- Evidencia: `ctx = payload.context if isinstance(payload.context, dict) else {}` y `_check_auto_approval(wf, payload)`. El esquema declara `context: Optional[Any]` (`app/schemas/approvals.py:148`), y `workflow_id` también lo elige el cliente (`:51`).
- Impacto: con `{"amount": 1}` en una solicitud de 50.000 se crea `approved` y se aplica la decisión final sobre la entidad. Es un bypass del control de aprobaciones (SoD/SOX). Sin verificar si los dominios de gastos y ausencias pasan su propio contexto.
- Arreglo: construir el contexto en servidor desde la entidad (`fuentes.py`), ignorar los importes del cliente, validar `entity_id` y la empresa, y limitar `workflow_id` al flujo asignado al tipo.
- **Estado:** ✅ arreglado 23-11-2026: el contexto de reglas sale de la entidad real (`fuentes.contexto_de_entidad`, de la empresa; 404 si no existe); el del cliente queda en `_cliente` solo informativo; `workflow_id` activo, del tipo y de la empresa; sin importe no se cumple `amount_lt`. Tests `test_c1_*`.

**C2 · `cmdb/discovery.py:87-88` (y `:116`, `:323`, `:404`, `:467`, `:676`) + `cmdb/models.py:91,193-205`: un fallo del proveedor retira todos sus CIs.** *(verificado)*
- Evidencia: `except Exception as exc: logger.warning("AWS EC2 discovery error: %s", exc)` → lista vacía → `reconcile_cis(...)` con `retirar_ausentes: bool = True` → `ci.status = _RETIRADO`; luego `job.status = "ok"` (`discovery.py:813`).
- Impacto: credencial caducada, red caída o SDK no instalado vacían la CMDB en silencio. El análisis de impacto de cambios y la deriva salen falsos.
- Arreglo: propagar el error o devolver una marca de «completo»; no retirar si hubo error o si el resultado es vacío o anómalo; estado `partial`.
- **Estado:** ✅ arreglado 23-11-2026: los fallos se anotan; solo se retira con inventario completo (sin errores, no vacío, no anómalo); si no, job `partial`/`error` con motivo. Test `test_c2_*`.

**C3 · `collaboration/compliance.py:242-258`: la retención de chat ignora el ámbito de cada política.** *(verificado)*
- Evidencia: dentro de `for pol in politicas:` el filtro es solo `organization_id == org, sent_at < corte, status != "deleted"`. Se ignoran `scope`, `target_id` y `apply_to`, y la escritura es `body: "[retention purge]"`.
- Impacto: una política «canal X, 1 mes» purga de forma irreversible todos los mensajes de la empresa con más de un mes. Si hay varias políticas, manda la más corta.
- Arreglo: filtrar por ámbito y por `apply_to`; añadir un test con política de canal.
- **Estado:** ✅ arreglado 23-11-2026: ámbito canal/equipo/tipo/espacio, manda la más específica (a igual ámbito, la más larga), solo `apply_to` all/messages, legal hold del chat y bloqueo legal general. Tests `test_C3_*` en `test_legal_hold_retencion.py`. ✅ 23-11-2026: purga de adjuntos (M77) hecha. ✅ 23-11-2026 HMAC de la cadena (migración 201): `collaboration_audit_events.hmac` y `key_id`; cada fila nueva lleva el HMAC (id, empresa, anterior y huella) con la clave activa del llavero (`key_management`, derivada con etiqueta propia) y su `kid`; `verify_chain` usa la clave de ese `kid` (un HMAC cambiado es rotura; un `kid` ya podado sale en `unverifiable`, no como rotura). Las filas anteriores no se rellenan (un HMAC de hoy no prueba nada de ayer): se verifican por `integrity_hash` v1/v2 como antes. Tests `test_c5_*` en `tests/test_migracion_201_cadena_y_cronometro.py`.

**C4 · `ai_provider_service/clientes.py:97,183,198,253,268` + `gestion.py:50,100,180`: SSRF en la URL del proveedor de IA.** *(verificado: ninguna llamada a `validate_outbound_url` ni a `cliente_httpx` en el paquete)*
- Evidencia: `resp = httpx.post(endpoint, json=body, headers=headers, ...)` con `endpoint` derivado de `provider.api_base_url`, editable por el admin de empresa. Los errores devuelven `resp.text[:200]` (oráculo) y `diagnose_provider` devuelve `str(exc)`.
- Impacto: lectura de `169.254.169.254` o de la intranet; la API key viaja a un host arbitrario. También se puede vía «probar sin guardar».
- Arreglo: `validate_outbound_url` al guardar y `cliente_httpx` al llamar (mismo patrón que `alm_uso/proveedores/http.py`); no devolver el cuerpo remoto.
- **Estado:** ✅ arreglado 23-11-2026: `api_base_url` validado al guardar y al «probar sin guardar» (`gestion._validar_base_url`); todas las llamadas (también `ai_tools._post`) por `clientes._http`: destino de plataforma (`settings.*_API_URL`, `OLLAMA_BASE_URL`) directo, cualquier otro por el guardia central con IP conectada; el cuerpo remoto ya no vuelve en el error salvo destino de plataforma. Verificado: `test_la_url_del_proveedor_de_ia_pasa_por_el_guardia`.

**C5 · `collaboration/_audit.py:58-86`: el lock de la cadena de auditoría no protege.**
- Evidencia: `with _lock_for(organization_id): prev = ...first() ... db.add(row) ... return row`. El commit lo hace el llamador, después de soltar el lock, y el lock es `threading.Lock` por proceso.
- Impacto: dos peticiones leen el mismo `prev_hash` y la cadena se bifurca, así que `verify_chain` da roturas falsas. El hash es SHA-256 sin clave y sin actor, IP ni fecha, y la verificación es O(n²). Se vende como auditoría íntegra.
- Arreglo: `pg_advisory_xact_lock` o `SELECT … FOR UPDATE` en la transacción del llamador; HMAC con clave y campos completos.
- **Estado:** ✅ arreglado 23-11-2026: bloqueo hasta el fin de la transacción (`pg_advisory_xact_lock`; semáforo en SQLite), anterior = cola de la cadena, `verify_chain` O(n) y detecta bifurcaciones. Test `test_c5_*`. ✅ 23-11-2026 (migración 196): `hash_version`; las filas nuevas son `v2` (HMAC con `SECRET_KEY` sobre actor, IP y fecha además de lo anterior) y las antiguas se siguen verificando como `v1`.

### 3.2 Altas (64)

#### Seguridad, autorización y aislamiento entre empresas

| ID | Fichero:línea | Evidencia | Impacto | Arreglo |
|---|---|---|---|---|
| A1 | `abac.py:371,386,576` *(verificado)* | `).one_or_404()` (no existe en `Query`; solo esas 3 líneas en el repo) | PUT/DELETE de políticas ABAC y `get_user_by_id_and_org` dan 500: no se puede editar ni borrar una política | `.first()` + `error(404)` <br>✅ arreglado 23-11-2026: `.first()` + 404 en editar, borrar y `get_user_by_id_and_org`. |
| A2 | `adhoc_analytics_service.py` + `endpoints/analytics_extended.py:34-38,82` | Solo `require_internal_user` / `get_current_user`; métricas `revenue` y `hours_logged` por usuario | Cualquier empleado ve la facturación y las horas de toda la empresa | Roles/GRC como `/invoices` <br>✅ arreglado 23-11-2026: `/analytics/adhoc|drilldown|cross-filter` con `requiere_capacidad("analitica.ver")`; la métrica `revenue` además `finanzas.ver`. |
| A3 | `ai_copilot_service.py:92-114` + `endpoints/ai_suggestions.py:25` | `GET /ai/suggestions/timesheets/{user_id}` con `get_current_user` | Cualquiera perfila las imputaciones de un compañero (RGPD) | Exigir manager o el propio usuario <br>✅ arreglado 23-11-2026: las anomalías de otra persona exigen la capacidad `partes.equipo` (y misma empresa; sin empresa, 404). |
| A4 | `ai_planning_service.py:244-255` | `accept_task_estimate` por id con `require_internal_user` | Cambia `estimated_hours` de cualquier tarea | ABAC y pertenencia al proyecto <br>✅ arreglado 23-11-2026: aceptar exige pertenencia al proyecto (`project_for_user`) y ABAC `task:update`. |
| A5 | `ai_modules/meetings.py:211-239` | Reunión sin `visibles()`; `project_id` del payload sin `project_for_user`; `Task` directa | Crea tareas en cualquier proyecto | Servicio de tareas + ABAC <br>✅ arreglado 23-11-2026: reunión vía `visibles()`, proyecto con `project_for_user`, tareas por `task_service.create_task_record`. |
| A6 | `ai_modules/voice.py:209-266` | `confirm=True` vuelve a llamar al LLM; `Imputation(...)`/`Ticket(status="open")` con `db.add` | Ejecuta algo distinto de lo propuesto; salta periodo, tope, ABAC; `"open"` no es un `TicketStatus` válido | Guardar `pending_action` firmada y ejecutar con los servicios normales <br>✅ arreglado 23-11-2026: propuesta firmada (HMAC, usuario, 10 min); confirmar ejecuta esa propuesta sin LLM con `crear_imputacion_validada`, `create_task_record` y `build_internal_ticket`. |
| A7 | `ai_chat/agent_loop.py:84-100`, `endpoints/ai_chat.py:7` | «aprobar vía `/agent/{id}/approve` (futuro)»; `auto_approve` lo manda el cliente | Las herramientas de escritura nunca se ejecutan, o con `auto_approve` quedan abiertas a inyección indirecta; `send_notification` copia `link` sin validar (`system.py:114`) | Endpoint de aprobación con la acción guardada; validar URL <br>✅ arreglado 23-11-2026: `POST /ai/agent/{id}/steps/{step_id}/approve|reject` (ejecuta la herramienta guardada, auditado; pasos persistidos también en streaming); `send_notification` solo enlaces internos. ➡️ la pantalla de aprobación es de la zona de frontend (la API está hecha). |
| A8 | `ai_provider_service/gobernanza.py:72-96`, `ai_modules/client_portal.py:145`, `ai_governance.py:298,616` | Solo `last_user_msg`; portal sin `user_id`; `_policies_cache = []` si falla | Datos personales al proveedor sin redactar; portal sin guardarraíles; fail-open | Pasar user/org; redactar contexto y tool-results; fail-closed <br>✅ arreglado 23-11-2026: portal IA con la empresa del cliente (guardarraíles de esa empresa); políticas no legibles → bloqueo (fail-closed). ✅ arreglado 23-11-2026: se redacta TODO el contexto (todos los mensajes y los resultados de herramientas) con `gobernanza.redactar_contexto`; el aviso de sistema también. |
| A9 | `alert_service.py:365-420` | `Alert.organization_id.is_(None) & user_id is None & project_id is None` visibles para todos; resolver por id sin propietario | Fuga entre empresas e IDOR | Quitar el fallback; comprobar propietario y rol <br>✅ arreglado 23-11-2026: fuera el fallback de alertas sin empresa; sin empresa, ninguna; empleado/externo solo resuelve las suyas. |
| A10 | `ask_the_data.py:235,334`; `ask_valores_reales.py:111` | `if not org_id: return sql, {}` | Sin org, NL→SQL lee todo el OLAP (emails, `cost_per_hour`) | Exigir org salvo superadmin explícito <br>✅ arreglado 23-11-2026: sin empresa solo superadmin explícito (403); la pregunta ya no va al log. |
| A11 | `analytics_service.py:151,229,255` | `if project_ids:` con `[]` | Un proyecto ajeno o inexistente devuelve las horas de toda la empresa | `is not None` <br>✅ arreglado 23-11-2026: `is not None`: `[]` es ninguno. |
| A12 | `billing_reports_service/facturas.py:220,323` | `query(Imputation).filter(id.in_(imp_ids)).update({"is_invoiced": True})` | El UPDATE masivo no pasa por el filtro de tenant (`session.py:456`): doble facturación o imputaciones de otra empresa | Acotar por org/proyecto, `is_invoiced == False`, comprobar `rowcount` <br>✅ arreglado 23-11-2026: `marcar_imputaciones_facturadas`: activas, no facturadas, de la empresa y proyecto de la factura; si no se marcan todas, 409 `imputaciones_no_facturables`. |
| A13 | `bookings_service/aprovisionamiento.py:47-77,195-222` | `relative_to(root)` sin subcarpeta por org; `subprocess.run` sin `env=`; `destroy` con `auto_approve=True` | Una empresa ejecuta o destruye módulos de otra, y el módulo hereda los secretos del worker | `root/<org>`, `env` mínimo, aprobación para `destroy` <br>✅ arreglado 23-11-2026: módulos bajo `root/<org>`, `subprocess` con entorno mínimo, `destroy` exige aprobación (`aprovisionamiento_destroy_sin_aprobacion`). |
| A14 | `bi_tokens_service.py:38-45,140` | `scopes` se guardan y no se comprueban; `requests_today` sin límite | Token BI con alcance total; sin rate limit; bcrypt en cada llamada | Aplicar scopes, límite y digest rápido <br>✅ arreglado 23-11-2026: los `scopes` se comprueban (`bi_token_sin_alcance`) y hay tope diario (`bi_token_limite_diario`). |
| A15 | `client_portal_service/panel.py:81`, `documentos.py:23`, `peticiones.py:124,163` | `if accessible and project_id not in accessible:` | Usuario de portal sin proyectos accede a cualquier proyecto de la empresa (otros clientes) | Denegar si la lista está vacía <br>✅ arreglado 23-11-2026: lista vacía = sin acceso en documentos, panel y peticiones. |
| A16 | `client_portal_service/mensajes.py:44,70,88-95` | Respuestas sin `is_internal == False`; `**msg_data` con `parent_id`/`is_internal` del cliente | Notas internas visibles al cliente; inyección en hilos de otro proyecto | Whitelist por rol; validar el padre <br>✅ arreglado 23-11-2026: respuestas internas ocultas; lista blanca de campos; padre e hilo del mismo proyecto y visibles. |
| A17 | `client_portal_service/documentos.py:119-155` | `_apply_signature_metadata` antes del PDF; `except: return None` y commit | Documento «firmado» sin certificado ni hash, sin comprobar visibilidad | Firmar solo si se genera el PDF; hash SHA-256; permisos <br>✅ arreglado 23-11-2026: documento visible; sin PDF no hay firma (409 `firma_sin_certificado`); huella SHA-256 en `audit_log`. ✅ 23-11-2026 (migración 196): `client_documents.signed_pdf_sha256`; la descarga no entrega un PDF cuya huella no coincide. |
| A18 | `cmdb/discovery.py:48-54,131-136,361,437` | AWS sin keys → `boto3.Session()`; `load_incluster_config()`, `kubeconfig_path`, `DefaultAzureCredential()`, `service_account_file` | El tenant usa credenciales de la plataforma o lee ficheros locales (confused deputy) | Credenciales explícitas; lo demás solo superadmin  <br>✅ arreglado 23-11-2026: sin credenciales propias se lanza `cmdb_credenciales_explicitas` (AWS sin keys, K8s sin `kubeconfig` YAML, Azure sin client secret, GCP sin `service_account_json`); las del servidor solo con `CMDB_DISCOVERY_ALLOW_PLATFORM_CREDENTIALS=1`. |
| A19 | `cmdb/discovery.py:645` | `"community": community` en `attributes` | Comunidad SNMP en claro visible en la CMDB | No persistirla <br>✅ arreglado 23-11-2026: ya no se persiste la comunidad SNMP (resuelto en paralelo en `discovery.py`). |
| A20 | `cmdb/discovery.py:546,600`; `cmdb_software/escaneos.py:341,363,421-443`; `fuentes.py:36,92-123`; `terceros.py:511,548,567,676`; `escaneres.py:156` | Destinos libres, `follow_redirects=True`, sigue `next`/`@odata.nextLink` con el token | SSRF, escaneo interno y reenvío de credenciales a hosts dictados por la respuesta | Validador común; fijar el host de paginación; sin redirects con credenciales  <br>✅ arreglado 23-11-2026: `peticion`/`cliente_httpx` en escaneos, fuentes, terceros y escáneres; paginación solo con `mismo_origen`; redirecciones solo sin credenciales. |
| A21 | `cmdb_software/escaneos.py:461,583-600` | `destinos = hosts or [...conf hosts]` | Credenciales SSH/WinRM guardadas usadas contra cualquier host (relé) | `hosts` ⊆ configurados  <br>✅ arreglado 23-11-2026: `hosts` de la petición ⊆ hosts configurados (`cmdb_host_no_configurado`). |
| A22 | `cmdb_software/riesgo/terceros.py:695,544,585,604-610,473-481` | `conf.get("complete", True)`; Qualys `truncation_limit 1000`; Tenable sin espera | Respuesta truncada → hallazgos de vulnerabilidad marcados «resueltos» en masa | `complete=False` por defecto; paginar; backoff <br>✅ arreglado 23-11-2026: `complete` por defecto False: una respuesta truncada no resuelve hallazgos en masa. ✅ arreglado 23-11-2026: Qualys pagina con `id_min` y Tenable espera con backoff; si el export no termina → error `sw_respuesta_truncada` y no se resuelve nada. (Verificar con credenciales reales.) |
| A23 | `collaboration/webhooks.py:105-170` | `target_channel_id` sin comprobar empresa; `secret_token` en claro | Publicar en canales de otra empresa (sin verificar RLS) | Validar canal/empresa; hash del token <br>✅ arreglado 23-11-2026: canal destino de la empresa (al crear y al entregar). ✅ 23-11-2026 (migración 196): `secret_token_hash` (relleno en la migración) y la entrega busca por la huella. ✅ arreglado 23-11-2026: verificado: el secreto ya solo se guarda como huella (resto de la zona colaboración). |
| A24 | `collaboration/_storage.py:223-234,253` | `"skipped", {"reason": "clamd unreachable; fallback scan passed"}`; `match_excerpt` 32 caracteres | Antivirus fail-open (por defecto desactivado); el DLP guarda fragmentos de tarjetas, IBAN y DNI | Cuarentena si no hay AV; guardar solo hash o posición <br>✅ arreglado 23-11-2026: sin antivirus el fichero queda `unavailable` (cuarentena, fail-closed) y se bloquea en todas las descargas; el DLP guarda solo tipo y posición, no fragmentos. |
| A25 | `dashboard_service.py:33-64`; `contract_service.py:29-33,~123`; `expense_service.py:386,416` | `if org:` / `or not current_user.organization_id: return q` | Usuario sin empresa ve datos de todas | Sin org = ninguna fila, salvo superadmin <br>✅ arreglado 23-11-2026: gastos (lista, equipo y Excel), panel de rentabilidad y contratos: sin empresa, ninguna fila. ✅ arreglado 23-11-2026: `dashboard_service` con centinela `_SIN_EMPRESA`: sin empresa, ninguna fila. |
| A26 | `customer_health_service.py:109-113` | `if not client_tickets: client_tickets = recent_tickets[:50]` | La salud de un cliente se calcula con tickets de otros | Filtrar por cliente; sin datos → `HEALTH_DEFAULT_NO_DATA` <br>✅ arreglado 23-11-2026: solo tickets del cliente (filtrados en la base); sin datos, `HEALTH_DEFAULT_NO_DATA`. |
| A27 | `entrega_de_webhooks.py:86,118`; `enterprise_service/webhooks.py:104,162` | Valida DNS y después `httpx.Client().post(hook.url)` | DNS rebinding (TOCTOU) a IPs internas; segundo validador SSRF divergente | `cliente_httpx` + `validate_outbound_url`  <br>✅ arreglado 23-11-2026: las dos entregas con `cliente_httpx` (IP conectada); el validador de webhooks delega en el central. |
| A28 | `integration_test_service.py:46-55,112,167` | `c.post(webhook, ...)`, `c.get(f"{base}/baseUris")`, SMTP con host/puerto libres | Sondeo de la red interna con el estado HTTP como oráculo | `cliente_httpx`; validar host y puerto  <br>✅ arreglado 23-11-2026: todas las sondas con `cliente_httpx`; host SMTP con `validar_host_saliente`. |
| A29 | `governance_service.py:200-221` | `query(func.count(AIActionLog.id)).scalar()` sin org | Uso de IA agregado entre empresas (superadmin, jobs) | Filtro explícito <br>✅ arreglado 23-11-2026: uso y registros de IA filtrados por empresa. |
| A30 | `horario/efectivo.py:187-209` + `informe_de_cumplimiento.py:65,198` | `query(JornadaLaboral).all()` sin org, bajo `sin_filtro_de_tenant` | Jornadas de otra empresa aplicadas; cifras erróneas en un informe firmado | Filtrar por `organization_id` <br>✅ arreglado 23-11-2026: jornadas, asignaciones, grupos y oficinas de la empresa. |
| A31 | `lecciones.py:142,506-578` | `listar`/`detalle`/`pendientes` sin alcance del origen | Lecciones de incidentes o proyectos restringidos visibles a cualquier rol con acceso al módulo (sin verificar la guarda del endpoint) | Filtrar por visibilidad del origen <br>✅ arreglado 23-11-2026: listar/detalle/pendientes filtran por el alcance del origen; sin autovalidación (`leccion_autovalidacion`). |
| A32 | `grc_service.py:46-55` | `GrcAuditLog(...)` sin `organization_id` | Acciones de superadmin o job con org nula, invisibles en el log de la empresa | Parámetro explícito <br>✅ arreglado 23-11-2026: `log_grc_entry` con empresa explícita (o la del usuario, o la de la sesión). |
| A33 | `gastos_avanzados.py:62,164-181` | El gestor se salta el estado; `db.delete(a)` + `delete_file` sin bloqueo legal | Retira justificantes de gastos aprobados o reembolsados (plazo legal) | Bloquear tras aprobar; consultar `bloqueo_legal` <br>✅ arreglado 23-11-2026: bloqueo de fila y bloqueo legal antes de borrar; justificante aprobado no se retira (`justificante_de_gasto_aprobado`). |
| A34 | `integrations.py:709-739` | `re.search(r'(\d+...)')`; `Imputation(...)`; `ilike(code)` | Slack imputa horas sin tope, periodo, pertenencia ni tarifa; coge el primer número | Delegar en `validate_and_create_imputation` <br>✅ arreglado 23-11-2026: Slack: proyecto obligatorio de la empresa, horas fuera del código, alta por `crear_imputacion_validada`. |
| A35 | `collaboration/bots.py:254,~190,550` | `/imputar` crea `Imputation` sin coste; `/tarea` usa el primer proyecto activo; `SD-{timestamp%1e6}` | Horas a coste 0, tareas en proyectos equivocados, números de ticket que colisionan | Servicios de dominio; `next_numbered_code` <br>✅ arreglado 23-11-2026: `/imputar` por la puerta común; `/tarea` sin proyecto vinculado no crea; ticket con `next_ticket_number`. |
| A36 | `bi_report_delivery_service.py` (entrega) | Destinatarios sin validar; hasta 5.000 filas | Exfiltración de informes a cualquier dirección | Validar dominio y rol <br>✅ arreglado 23-11-2026: destinatarios validados por dominio permitido (`bi_destinatario_no_permitido`) y tope de filas configurable. |
| A37 | `key_management.py:44,214-219` | `_cache = {"jwt": None}` sin TTL; rota Celery, la web solo al arrancar | 401 intermitentes tras rotar; tokens no validables al podar el kid | TTL o pub/sub  <br>✅ arreglado 23-11-2026: caché con TTL `JWT_KEYRING_CACHE_SECONDS` (60 s) y recarga ante un `kid` desconocido (`decode_token`). |
| A38 | `key_management.py:332-343` | Recifra solo 5 modelos | `IntegrationCredential.value_encrypted`, `JiraConfig`, tokens de colaboración, `nvd_api_key`, marketplace y Slack quedan ilegibles al retirar `SECRET_KEY_PREVIOUS`, mientras el informe dice `pass` | Registrar todas las columnas `*_enc*` + test  <br>✅ arreglado 23-11-2026: registro ampliado a todas las columnas cifradas (modos valor/prefijo/json/colab; 18 entradas) leídas entre empresas en contexto de sistema. Verificado: `test_la_rotacion_cubre_las_columnas_cifradas`, `test_la_rotacion_recifra_lo_anidado_y_deja_lo_que_no_es_secreto`. |
#### Integridad funcional, dinero y tiempo

| ID | Fichero:línea | Evidencia | Impacto | Arreglo |
|---|---|---|---|---|
| A39 | `exportador_tabular.py:63,89` *(verificado)*; `expense_service.py:196` | `escritor.writerow(fila)` / `hoja.append(valores)` sin neutralizar | Inyección de fórmulas CSV/XLSX (`=HYPERLINK`, DDE) al abrir la exportación | Prefijar `'` a `= + - @ \t \r`  <br>✅ arreglado 23-11-2026: `app/core/celdas_seguras.py` en el exportador común (CSV y XLSX), el Excel de gastos y el CSV del constructor de informes. Verificado: `test_las_exportaciones_neutralizan_formulas`. Quedan ~30 generadores propios (métricas/BI), documentados. <br>✅ 23-11-2026 (segunda ronda): 10 ficheros generan CSV/XLSX (los «~30» eran filas JSON de métricas, que no se exportan); 3 ya neutralizaban y los 7 restantes ahora también (analytics_extended, bi_export_service, bi_report_delivery_service, cargos internos, cmdb_software/analisis [2 CSV], m365_bi_embed_service, presupuestos_seguir): 10/10. Test estático `tests/test_exportaciones_sin_formulas.py` falla si aparece un generador nuevo sin `celdas_seguras`. |
| A40 | `expense_service.py:157-159` *(verificado)* | `if status:` / filtro de estado / `q.filter(Expense.category == category)` dentro del `if` | Sin estado se ignora la categoría; con estado y sin categoría filtra `category IS NULL` y sale vacío | Sacarlo y condicionar a `if category:` <br>✅ arreglado 23-11-2026: categoría fuera del `if status`, condicionada a `if category`. |
| A41 | `currency_rates_service.py:160-168,199-204`; `profitability_service.py:58` | `rate = row.rate if row else 1.0`; `"source": "fallback"` | USD→GBP o una moneda sin tipo cargado se convierte 1:1 sin aviso, y entra en coste, margen y EVM | Tipo cruzado vía EUR; error o marca explícita <br>✅ arreglado 23-11-2026: resolutor único (directo, inverso, cruzado por EUR); puntual → 409, agregado → aviso (`fx_warnings`, `missing_rates`). |
| A42 | `enterprise_service/subcontratas.py:654-666` | `for k in ["status","paid_date",...]: setattr(inv, k, ...)` | Factura de subcontrata `paid` sin proceso ni SoD | Transiciones; aprobador ≠ creador <br>✅ arreglado 23-11-2026: transiciones de estado validadas (`factura_subcontrata_transicion_no_valida`) y SoD (`factura_subcontrata_misma_persona`). ➡️ `approved_by/approved_at` los añade la migración 200. |
| A43 | `enterprise_service/subcontratas.py:~551-560` | `cost_amount = payload.get("cost_amount")` | Coste manual (incluso negativo) en margen y EVM; sin tarifa → coste NULL descartado | Calcular desde la tarifa; validar horas <br>✅ arreglado 23-11-2026: coste manual validado (≥0, Decimal) y auditado. |
| A44 | `entrega_de_webhooks.py:39` + `enterprise_service/webhooks.py:188-231` | `is_active=False` al suspender; list/update filtran `is_active == True` | Un webhook suspendido desaparece y no se puede reactivar | Estado propio + reactivación <br>✅ arreglado 23-11-2026: suspendidos visibles y `POST /enterprise/webhooks/{id}/reactivate` (botón en el registro de webhooks). |
| A45 | `imputation_service/alta.py:123-180`; `consultas_y_edicion.py:66-84`; `cronometro.py:239-286` | `func.sum(Imputation.hours)` sin `is_active` | Tope diario y semanal y duplicados cuentan borradas: 409 al reimputar | Filtrar `is_active` <br>✅ arreglado 23-11-2026: topes y duplicados con `is_active` en alta, edición y cronómetro. |
| A46 | `imputation_service/alta.py:62` | `today_utc = datetime.now(timezone.utc).date()` | En UTC+8 no se puede imputar «hoy» hasta las 08:00 | `today_for_user` <br>✅ arreglado 23-11-2026: `today_for_user`. |
| A47 | `imputation_service/cronometro.py:217` | `..., inicio.date()` (UTC) | El trabajo de tarde o madrugada cae en otro día | Zona del usuario <br>✅ arreglado 23-11-2026: día de inicio en la zona de la persona. |
| A48 | `imputation_service/cronometro.py:248-327` | No llama a `_validar_tope_semanal` ni al control de horas extra | El cronómetro esquiva el tope y el «bloquear» de horas extra | Validación común <br>✅ arreglado 23-11-2026: el cronómetro crea por `crear_imputacion_validada` (tope semanal y horas extra). |
| A49 | `horas_extra/config.py:29`; `control.py:52`; `ejemplos.py:46-65` | `"control_imputacion": "avisar"` → `float("inf")`; los límites legales solo en políticas de ejemplo en borrador | Sin tope legal por defecto (ET 35.2/34.3) | Tope legal configurable activo <br>✅ arreglado 23-11-2026: «avisar» ya no es infinito: tope legal (`horas_extra_tope_legal`) con límites configurables. |
| A50 | `externos/horas.py:34-50`; `conciliacion.py:27` | Sin `is_active`; excluye el parte entero si hay cualquier imputación | Consumo de pedido y conciliación con el proveedor erróneos | Filtrar; restar solo el solape <br>✅ arreglado 23-11-2026: `is_active` en horas y en la exclusión por solape. ✅ arreglado 23-11-2026: `partes_netos`: se resta solo el solape (y solo imputaciones activas) en horas, conciliación y coste del proyecto. |
| A51 | `git_service.py:138-144,230-268` | `GitPullRequest(...)` sin `project_id` | Empleados y externos nunca ven PR ni despliegues | Derivarlo de la tarea <br>✅ arreglado 23-11-2026: PR y despliegues con `project_id` resuelto por repositorio. |
| A52 | `invoice_pdf.py:222,280,356` | `Paragraph(str(line.get("description")))` sin `escape` | `R&D` o `<` → 500 y la factura no se emite | `saxutils.escape` <br>✅ arreglado 23-11-2026: texto escapado en todo el PDF. |
| A53 | `invoice_pdf.py:88-92,159-172` | Etiquetas zh/pl con `Helvetica` | Factura china o polaca ilegible (es/en/zh obligatorios) | Fuente Noto Sans / Noto Sans SC <br>✅ arreglado 23-11-2026: DejaVu Sans (incluida en `app/assets/fonts`) y STSong-Light para chino. |
| A54 | `invoice_pdf.py:374-399` | Solo `company_name` | Sin NIF, domicilio ni IBAN del emisor: no vale como factura (RD 1619/2012, sin verificar el detalle) | Datos fiscales del emisor <br>✅ arreglado 23-11-2026: razón social, NIF, domicilio e IBAN (`INVOICE_ISSUER_*`). |
| A55 | `integrations.py:278-280` | `if not template: return []`; llamado con `"policy.matched"` y `"alm.license_reclaim"` | Avisos que nunca salen y contador que dice que sí | Plantilla genérica; contar solo lo enviado <br>✅ arreglado 23-11-2026: plantillas de `policy.matched` y `alm.license_reclaim`; sin plantilla se usa un texto genérico (no se pierde el aviso). |
| A56 | `jira_service.py:706`; `integrations.py:191` | `/rest/api/3/issue/search`, `/search` | Endpoints inexistentes o retirados: sincronización y buscador probablemente nunca funcionaron (sin verificar contra Jira real) | `POST /search/jql` + `nextPageToken` <br>✅ arreglado 23-11-2026: Jira `/rest/api/3/search/jql` con paginación `nextPageToken`. (Verificar con credenciales reales.) |
| A57 | `jira_service.py:485,136-148` | `JIRA_STATUS_MAP.get(raw, "todo")`, mapa solo en inglés | Un Jira en español devuelve las tareas a `todo` en cada sync | Mapear por `statusCategory` <br>✅ arreglado 23-11-2026: mapa por `statusCategory.key` (independiente del idioma de Jira). |
| A58 | `automation_events.py:354-366` | `pending ... .all()` sin `skip_locked` | Correos y webhooks duplicados con varios workers | `SKIP LOCKED` + idempotencia <br>✅ 23-11-2026 (migración 196): `idempotency_key` única por empresa (no se anota dos veces el mismo evento en una transacción) y en PostgreSQL el worker reclama cada evento con `FOR UPDATE SKIP LOCKED`. |
| A59 | `bi_report_delivery_service.py:214,767-790` | `cron_expression` se guarda y nunca se lee; umbrales 1 h/24 h/7 d/30 d desde `last_run_at` | Programación ignorada, deriva, duplicados entre pasadas | croniter + bloqueo <br>✅ arreglado 23-11-2026: `cron_expression` aplicada (5 campos, UTC) y validada al guardar. |
| A60 | `bi_gdpr_service.py:197-215` | `status = "completed"` antes de `execute_erasure`; rectificación y restricción sin código | DSR cerrado sin borrar (también ante bloqueo legal) | Completar tras éxito; implementar o rechazar tipos <br>✅ arreglado 23-11-2026: registro único (`gdpr_requests`); supresión solo se cierra ejecutándola y se marca completada después de borrar; `restriction` 422. |
| A61 | `bi_data_versioning_service.py:80-105` | `CREATE TABLE _demo ... (1,'demo',100.0)` y `{"period":"2024-01","value":120000}` | Se guardan datos demo como versión inmutable | Error o vacío <br>✅ arreglado 23-11-2026: sin datos ETL, 422 `bi_dataset_sin_datos` (fuera la tabla `_demo` y las filas de 2024). |
| A62 | `bi_anomaly_service.py:138-207` | `random.Random(42)`, 1.400 filas sintéticas; `lightgbm_synthetic` | Probabilidades de churn sin base real | Rotular como heurística o datos reales <br>✅ arreglado 23-11-2026: sin modelo entrenado con datos sintéticos: heurística `rule_based` sobre los datos reales. |
| A63 | `clientes_internos/costes.py:185-188,233` | `except Exception: return [], licencias` / `licencias = 0.0` | Cargos internos emitidos y exportados sin líneas ALM ni aviso | Propagar o marcar incompleto <br>✅ arreglado 23-11-2026: un fallo de costes ya no emite cargos a cero: se propaga y se anota. |
| A64 | `cab_service/gdpr.py:201-229` | `req.export_data = json.dumps(export_data)` sin TTL ni cifrado; anonimizado no atómico | Copia de datos personales indefinida; supresión parcial atascada | Cifrar + TTL; transacción única <br>✅ arreglado 23-11-2026: copia cifrada y con caducidad (`COMPLIANCE_GDPR_EXPORT_TTL_DAYS`, barrido diario); una sola transacción. |
### 3.3 Medias (109), agrupadas por tema

Una línea por hallazgo: fichero:línea, evidencia resumida e impacto. El arreglo se deduce, o se indica.

#### Dinero, divisas y redondeo

- **M1** `budgets_service.py:109-270`: presupuestos en `float` con `round` acumulativo; `_real_mensual` carga todos los usuarios ×2 (N+1); `hasattr(User,"currency")` deja de convertir en silencio; `decidir` sin `with_for_update`. — ✅ arreglado 23-11-2026: ver DOCS.md (fase 1, presupuestos).
- **M2** `alm_costes.py:183-322`, `alm_conciliacion.py:58-253`, `alm_service.py:296-308`: float; suma de monedas sin convertir; FX a una sola fecha (`:399-403`); `comprometido_por_mes` recarga todo por mes. — ✅ arreglado 23-11-2026: ver DOCS.md (fase 1, ALM).
- **M3** `gastos_avanzados.py:90,204,230,267-310`: — ✅ arreglado 23-11-2026: Decimal en gastos avanzados.
  - kilometraje y reparto en float;
  - `abs(total-100) > 0.01` admite el 99,99 %;
  - suma monedas distintas;
  - N+1 en `totales_por_proyecto`.
- **M4** `gastos_avanzados.py:116-130`: adjuntos sin lista blanca de tipo ni extensión; tamaño comprobado tras cargar en memoria. — ✅ arreglado 23-11-2026: verificado: el endpoint ya valida con `read_and_validate_upload(RECEIPT)`.
- **M5** `exchange_rate_service.py:108-169`: inverso `round(1/rate, 6)` (IDR ≈0,3 %); `app_id` en la URL (log de httpx); una cotización 0 deshace todo el sync. — ✅ arreglado 23-11-2026: tipo de cambio sin inventar (avisa si falta).
- **M6** `evm_service.py:99-148,252-264`: AC sin `is_active`, sin fecha ni moneda; BAC en monedas mezcladas; N+1 por proyecto. — ✅ arreglado 23-11-2026: AC desde el cálculo único de margen (`margen_de_proyectos`): activos, con fecha y moneda; sin N+1.
- **M7** `cost_service.py:97-276`: `cost_per_hour` sin moneda; `bulk` ignora externos; perfiles solapados; `date.today()`; update/delete sin org. — ✅ arreglado 23-11-2026: ver DOCS.md (fase 1, costes).
- **M8** `dashboard_service.py`: rentabilidad = horas × tarifa − coste multimoneda (cuarto cálculo de margen); `tasks_done` sin rango; media de 4 semanas inventada sin marcar. — ✅ arreglado 23-11-2026: el panel cuenta solo imputaciones activas y no ve otras empresas sin empresa. ✅ arreglado 23-11-2026: cálculo único de margen (`margen_de_proyectos.margen_en_bloque`) en panel, rentabilidad, EVM y BI.
- **M9** `enterprise_service/prevision.py`: suma ingresos y costes de varias monedas sin convertir. — ✅ arreglado 23-11-2026: previsión con divisas resueltas.
- **M10** `client_service.py:346,433`: `contract_value_eur` suma `total_amount` en cualquier moneda. 🟡 23-11-2026 (migración 200): `contracts.currency` creada; la API del contrato devuelve `currency` (o la de la empresa). ✅ arreglado 23-11-2026: ver fila (contrato en su moneda: `contracts.currency` en la migración 200).
- **M11** `clientes_internos/costes.py:62-320`: — ✅ arreglado 23-11-2026: cargos internos en Decimal y moneda.
  - tarifa por defecto = primera fila sin `order_by`;
  - precio cerrado repartido por número de hitos ignorando `billing_pct`;
  - reparto sin conciliar el resto del redondeo;
  - O(U²·S) consultas.
- **M12** `clientes_internos/cargos.py:178,200-204,269-304`: marca `exportado` en la misma transacción que devuelve el CSV (sin re-exportación); `date.today()`; `try/except pass` inútil; `create_invoice` con commit interno (reintento duplica). — ✅ arreglado 23-11-2026: idem M11.
- **M13** `ai_chat/tool_execution/finance.py:35,69`: totales sumados sobre una página truncada (`.limit(30)`); monedas mezcladas. — ✅ arreglado 23-11-2026: herramientas de finanzas del chat con el cálculo único.
- **M14** `ai_modules/oracle.py:45,246`, `_base.py:311`, `client_portal.py:228`: tarifa inventada `AI_REVENUE_HOURLY_RATE_FALLBACK=85.0` (8 apariciones); en `client_portal` tras un error SQL no hay rollback. — ✅ arreglado 23-11-2026: portal IA con la empresa del cliente.
- **M15** `formato_regional.py:74`; `invoice_pdf.py:131,305`: importes siempre «1,234.50 €» (formato USA); IVA 7,5 % mostrado como 8 %. — ✅ arreglado 23-11-2026: (solo factura PDF) IVA con decimales (`:g`). ✅ arreglado 23-11-2026: formato regional por idioma (`formato_regional`), IVA con decimales.
- **M16** `integrations.py:344-471,531`: Xero sin refresh de token (caduca a 30 min); `TaxType "OUTPUT"` fijo; QuickBooks con `CustomerRef "1"`; float; `currency` = país. — ✅ arreglado 23-11-2026: QuickBooks según API documentada (consulta/alta de cliente). (Verificar con credenciales reales.)
- **M17** `billing_reports_service/facturacion_recurrente.py:75-106`: número por `max(INV-año)+1` (ignora `next_invoice_number`); sin rollback en el bucle; sin bloqueo (doble clic = 2 facturas); float. — ✅ arreglado 23-11-2026: número con `next_invoice_number`. ✅ arreglado 23-11-2026: rollback por iteración, `with_for_update`, solo si toca, Decimal.
- **M18** `externos/horas.py:69`, `conciliacion.py:48-85`, `tarifas.py:41`: coste en moneda de empresa frente a pedido en moneda del proveedor; FX sin comprobar `None`; `NULL` primero en `order_by desc` (PostgreSQL). — ✅ arreglado 23-11-2026: coste convertido a la moneda del proveedor (`_a_moneda_del_proveedor`), FX `None` → aviso, `nulls_last`.
- **M19** `enterprise_service/subcontratas` (dashboard): `active_assignments` cuenta todas; «pagado» incluye las aprobadas. — ✅ arreglado 23-11-2026: ver A42/A43.
- **M20** `contract_service.py`: `horas_usadas` sin `is_active` y compartidas entre contratos del mismo proyecto; `setattr` libre en órdenes de trabajo. — ➡️ zona de contratos (otro agente / migración 200).
- **M21** `accounting_hub_service.py:147,153`: push a contabilidad con `lines: []` y cliente literal `"Cliente"`. — ✅ arreglado 23-11-2026: líneas reales en el hub contable; sin cliente «Cliente» inventado.

#### Tiempo, horas y zonas

- **M22** `horas_extra/control.py:38-44`: `_cfg` con `except: return None` = módulo desactivado (fail-open con «bloquear»). — ✅ arreglado 23-11-2026: ver A49.
- **M23** `horas_extra/reglas.py:27,57`: antelación con la hora local tratada como UTC (error de 1-8 h). — ✅ arreglado 23-11-2026: reglas en la zona horaria de la empresa.
- **M24** `horas_extra/calculo.py:110-183`: descanso medido contra el horario teórico y no contra lo imputado; la tolerancia descarta excesos pequeños recurrentes. — ✅ arreglado 23-11-2026: descanso con horas extra del día contiguo.
- **M25** `horas_extra/reglas.py:35-48`, `consultas.py:301-337`, `horario/efectivo.py:171-196`: N+1 fuerte (recarga 6 tablas por persona y día). — ✅ arreglado 23-11-2026: memo de la empresa en `db.info` limpiado en commit/rollback.
- **M26** `horas_extra/solicitudes.py:481-492,620-634`: `horas_autorizadas` fijada con el primer voto; `liquidar` sin bloqueo de fila (doble liquidación). — ✅ arreglado 23-11-2026: mínimo de los votos; bloqueo al liquidar.
- **M27** `horas_extra/control.py:133-152`: con «avisar» notifica y registra en cada edición sin deduplicar. — ✅ arreglado 23-11-2026: ver A49.
- **M28** `horas_extra/config.py:3,27`: docstring contradictorio; `_validar_presupuesto` acepta `nan`/`inf`. — ✅ arreglado 23-11-2026: ver A49.
- **M29** `horario/tramos.py`, `efectivo.py:366`: sin cambio de hora (DST); ausencias por horas repartidas también entre festivos. — ✅ arreglado 23-11-2026: ausencias por horas no cuentan festivos.
- **M30** `imputation_service/alta.py:212-259`: commit y sincronización de la hoja en transacciones distintas; captura de `IntegrityError` de un índice único que no existe en el modelo (sin verificar migraciones posteriores), así que hay duplicados por concurrencia. — ✅ arreglado 23-11-2026: bloqueo consultivo por persona/día; parte sincronizado en la misma transacción.
- **M31** `imputation_service/cronometro.py:68-245`: cronómetro olvidado de más de 24 h imposible de parar; mínimo de 0,25 h fijo; la comprobación de cronómetro activo no es atómica. — ✅ arreglado 23-11-2026: bloqueo consultivo; horas corregibles al parar; tope (`cronometro_demasiado_largo`). ✅ 23-11-2026 migración 201: índice único parcial `uq_timer_sessions_un_activo_por_usuario` (`timer_sessions(user_id) WHERE ended_at IS NULL`; cierra antes los duplicados) y el choque sale como 409 `cronometro_ya_activo`.
- **M32** `imputation_service/consultas_y_edicion.py:53-58,172`: `description` e `is_billable` se ignoran al editar; `ZeroDivisionError` con capacidad 0; `lockout_status_payload` devuelve rangos vacíos. — ✅ arreglado 23-11-2026: `description` e `is_billable` se aplican al editar. ✅ arreglado 23-11-2026: capacidad 0 sin división; `lockout_status_payload` con rangos reales.
- **M33** `imputation_service/consultas_y_edicion.py:232-251`: PM, team lead y RR. HH. ven las imputaciones de toda la empresa. — ✅ arreglado 23-11-2026: alcance por rol (PM/jefe de equipo).
- **M34** `imputation_service/alta.py:55,271-289`: `admin` se salta el cierre de periodo, la fecha futura y lo aprobado sin traza reforzada (sin verificar la auditoría del endpoint). — ✅ arreglado 23-11-2026: excepción de administrador auditada (`IMPUTATION_ADMIN_OVERRIDE`).
- **M35** `capacity_planning_service.py:60-123`: cuenta sábados, domingos y festivos; división por 0; nivelado que puede crear otra sobrecarga. — ✅ arreglado 23-11-2026: capacidad por día desde el horario; nivelado sin solapes.
- **M36** `activity_service/planificacion.py:149,221-251`: `saved_weeks*5` restado como días naturales; coste con la tarifa de facturación; `cost_delta_eur` fijo. — ✅ arreglado 23-11-2026: semanas×7 días; coste con la tarifa de coste del equipo; delta en la moneda.
- **M37** `activity_service/tareas_recurrentes.py:144-214`: `max(code)` como texto; sin tope de recuperación (365 tareas en una transacción). — ✅ arreglado 23-11-2026: secuencia de tareas común. ✅ arreglado 23-11-2026: tope de recuperación configurable `RECURRING_TASKS_MAX_CATCHUP`.
- **M38** `activity_service/proveedores.py:65`: `reversed(scores[-6:])` sobre una lista ordenada DESC toma las 6 más antiguas. — ✅ arreglado 23-11-2026: últimas 6 puntuaciones en orden.
- **M39** `externos/disponibilidad.py:80-108`: `weekday() < 5` y `/5.0` fijos frente a `PLANNING_WORKDAYS`. — ✅ arreglado 23-11-2026: días laborables reales (`dias_laborables`).
- **M40** `jira_service.py:704-709`: ventana JQL en UTC frente a la zona del usuario de Jira; `maxResults 100` sin paginar; clave de proyecto sin escapar. — ✅ arreglado 23-11-2026: ver A56/A57.

#### Seguridad, RGPD y secretos

- **M41** `abac.py:175`: con el atributo ausente, `not_in`, `not_contains` e `is_empty` devuelven False, así que la política *deny* no se aplica. — ✅ arreglado 23-11-2026: en políticas deny, atributo ausente cumple `not_in`, `not_contains` e `is_empty`.
- **M42** `abac.py:680,686`: `func.json_extract(...)` solo SQLite; N+1 por política. — ✅ arreglado 23-11-2026: contador en memoria (`Counter`), sin consultas por regla.
- **M43** `ai_provider_service/clientes.py:109,224`; `ai_tools.py:279`: API key de Gemini en la query string (log de httpx y proxies). — ✅ arreglado 23-11-2026: clave de Gemini en cabecera `x-goog-api-key` (no en la URL).
- **M44** `ai_provider_service/despacho.py:63-69`, `gestion.py:31-35`: sin org el respaldo prueba proveedores de todas las empresas; `_clear_default` sin filtro quita el defecto en todas. — ✅ arreglado 23-11-2026: `_clear_default` por empresa; sin empresa solo proveedores compartidos.
- **M45** `ai_provider_service/despacho.py:370`: error en banda `"⚠️ AI provider error: {...}"` con el cuerpo remoto. — ✅ arreglado 23-11-2026: solo el tipo de error al cliente.
- **M46** `ai_governance.py:36-72`: regex de PII con falsos positivos (3 palabras capitalizadas, 9 dígitos, versiones como IP); sin Luhn ni control de IBAN. — ✅ arreglado 23-11-2026: validadores (Luhn, IBAN, IP, nombres) para reducir falsos positivos.
- **M47** `absence_service.py:299-355`: tipo y motivo de baja médica visibles con `viewer=None` y para PM/team lead (dato de salud, art. 9 RGPD). — ✅ arreglado 23-11-2026: fail-closed sin empresa; el motivo solo lo ve quien puede (`puede_ver_motivo`).
- **M48** `ai_planning_service.py:172-176,303-314,435`: horas y categoría del LLM sin validar; inyección desde la descripción del ticket; el agente menos cargado nunca es uno con 0 tickets. — ✅ arreglado 23-11-2026: salida del modelo validada (números, categorías en lista, sin instrucciones).
- **M49** `ai_modules/voice.py`, `meetings.py:49`, `client_portal.py`: transcripciones y chats con datos personales sin purga encontrada (sin verificar). — ✅ arreglado 23-11-2026: bloqueo legal de `ai_voice_commands` y `ai_client_chats` (etiquetas es/en/zh).
- **M50** `ai_chat/context_service.py:100-108,565-587`: `can_see_* = True` si `user is None`; consulta muerta. — ✅ arreglado 23-11-2026: fail-closed sin empresa; costes del cálculo único; consulta duplicada sin filtro retirada.
- **M51** `ask_valores_reales.py:142,153`: nombres y correos reales enviados al LLM. — ✅ arreglado 23-11-2026: datos personales detectados (`_es_personal`).
- **M52** `ask_the_data.py:357-430,535`: fallback «utilización < 70 %» que suma todo el histórico (resultado erróneo); la pregunta del usuario va al log. — ✅ arreglado 23-11-2026: la pregunta ya no va al log. ✅ arreglado 23-11-2026: últimas 4 semanas, con capacidad.
- **M53** `auth_service/estado_efimero.py:337,374-398`; `tokens_y_cookies.py:139`: límite de reseteo en memoria por proceso; GET+DELETE no atómico; correo del destinatario en el log. — ✅ arreglado 23-11-2026: límite con `INCR` en Redis y consumo atómico (Lua).
- **M54** `approval_engine/por_correo.py:35`: JWT en la URL, sin `jti` ni revocación (reenviar el correo = delegar). — ✅ arreglado 23-11-2026: enlace de aprobación por correo de un solo uso (`jti`).
- **M55** `bi_gdpr_service.py:116,387`: histórico de consentimiento truncado a 100 (art. 7.1); SHA-256 sin sal a 12 hex; portabilidad incompleta (art. 20); IP sin retención. — ✅ arreglado 23-11-2026: historial completo, IP minimizada, portabilidad con partes/gastos/ausencias, hash HMAC.
- **M56** `bi_bookmarks_service.py:217-242`: token público sin caducidad ni revocación; `LIKE` sobre los blobs de todas las empresas. — ✅ arreglado 23-11-2026: token `<org>.<token>` con caducidad `BI_BOOKMARK_SHARE_DAYS` y revocación (DELETE).
- **M57** `baja_de_empresa_service.py:~102,308`: ZIP con `Decimal`→`float` y `bytes`→`None`; incluye secretos de integraciones (sin verificar cifrado); no atómico; repetir reinicia la cuarentena. — ✅ arreglado 23-11-2026: sin reiniciar cuarentena; exportación con Decimal/bytes serializados y secretos redactados.
- **M58** `bookings_service/api_keys.py:77,92`, `aprovisionamiento.py:25`: auditoría con usuario `None` («System»); `format_map` con plantillas del tenant. — ✅ arreglado 23-11-2026: autor real en las claves API.
- **M59** `automations_service/acciones.py:120` + bookings: 3 validadores SSRF; el de automations deja pasar si falla el DNS y no mira `is_reserved`; cabeceras en claro. ✅ arreglado 23-11-2026: los tres validadores propios delegan en el guardia central (HTTPS, sin pasar con DNS caído, `is_reserved`/CGN).
- **M60** `bi_embed_service.py:62`: clave HS256 = `SECRET_KEY:embed:org`, fuera de la rotación; blob JSON en `AppSetting` sin bloqueo (pérdida de escrituras). — ✅ arreglado 23-11-2026: HMAC con clave rotada (`claves_secretas`) y blob bloqueado.
- **M61** `client_portal_service/peticiones.py:336-394`: aceptar presupuesto sin `can_approve_deliverables`; el rechazo deja la CR `rejected` aunque esté implementada; `ApprovalRequest` a mano con `requested_by=None`. — ➡️ zona portal de clientes (otro agente, 23-11-2026).
- **M62** `client_portal_service/peticiones.py:126-310`, `uat.py:56`, `cargos.py:90`: numeración por `max(code)` de texto (FR-999 > FR-1000) y `count()+1` con carreras; dos espacios «CR-». — ✅ arreglado 23-11-2026: FR, CR y UAT con `numbering.siguiente_codigo`. ➡️ aceptar presupuesto sin permiso y rechazo de CR implementada: es M61 (zona portal de clientes).
- **M63** `client_portal_service/uat.py:62-103`: un resultado inválido cuenta como `passed`; altas sin comprobar existencia ni empresa. — ➡️ zona portal de clientes.
- **M64** `client_portal_service/wiki_y_encuestas.py:37`: wiki `visibility=="portal"` visible a todos los clientes de la empresa. — ➡️ zona portal de clientes.
- **M65** `client_portal_service/autenticacion.py:53-146`, `clientes.py:75-187`: — ➡️ zona portal de clientes.
  - revocación del token en memoria;
  - `portal_share` sin `jti`;
  - email sin normalizar y enumeración por tiempo;
  - cambio de email o password sin política;
  - `budget_hours` visible sin `can_view_budget`;
  - `test_credentials` de UAT en claro.
- **M66** `cab_service/integraciones.py:72,124-151`: Sprints sin org publicados en el Google Calendar de una empresa (desde job); tokens en claro aceptados; datetimes naive. — ➡️ zona CAB (otro agente, 23-11-2026).
- **M67** `cab_service/webhooks_entrantes.py:74-91`, `correo.py:77-170`: secreto en claro; log de payload y cabeceras sin retención; sin SMTP marca «sent»; plantillas sin escapar. ✅ arreglado 23-11-2026: (parte) el secreto HMAC de los webhooks entrantes se guarda cifrado; el resto (log de payload, SMTP simulado) no es de esta zona.
- **M68** `clientes_internos/unidades.py:231,251`: unidades y clientes con org NULL visibles a todas las empresas; N+1. — ✅ arreglado 23-11-2026: unidades internas con empresa.
- **M69** `client_service.py:43-55,379,882-1056`: licencias, contratos, portal y 360 sin usuario (alcance inconsistente con `scoped_client_query`; sin verificar el endpoint); N+1; `ilike` sin escapar. — ✅ arreglado 23-11-2026: LIKE escapado.
- **M70** `campaign_pdf.py:160-200`; `branding_service.py:171-204`: `Paragraph` sin escape (`<img src>` posible); Helvetica sin chino; CSS vars libres y `setattr` por clave. — ✅ arreglado 23-11-2026: HTML escapado en PDF; CSS de marca validado; columnas en lista blanca.
- **M71** `cmdb_software/fuentes.py:199-206`, `_q`/`calc_q`: KEV vacío quita todas las marcas; con org None se envían a OSV los purl de todas las empresas. — ✅ arreglado 23-11-2026: empresa obligatoria; KEV vacío = error.
- **M72** `cmdb_software/escaneos.py:334,461-654`: CI casado por nombre corto (`web01.prod` = `web01.dev`); 500 hosts en serie en el hilo del planificador; BOM en JSON de PowerShell. — ✅ arreglado 23-11-2026: nombre corto único; BOM retirado.
- **M73** `cmdb/discovery.py:530-630,779`: SNMP secuencial de hasta 1.024 IP (≈1 h); v3 con «admin» y claves vacías; comunidad `public`; `triggered_by="scheduler"` fijo. — ✅ arreglado 23-11-2026: sin comunidad SNMP/credenciales v3 por defecto; `triggered_by` real.
- **M74** `change_service.py:87-137`: sin validar transiciones; commit antes de `fuentes.abrir`; `Date` frente a `datetime`; `get_all_pending` sin org. — ✅ arreglado 23-11-2026: transiciones de cambio validadas (`cambio_transicion_no_valida`), fechas locales, pendientes por empresa.
- **M75** `bpmn_engine.py:517,626-640`; `bpmn_process_service.py:294,579,714`: — ✅ arreglado 23-11-2026: las tareas automáticas esperan confirmación humana. ✅ arreglado 23-11-2026: rollback por temporizador; instancias canceladas al borrar el proceso; versión con bloqueo.
  - tareas automáticas sin ejecución;
  - barrido de temporizadores sin try/rollback por instancia;
  - borrar un proceso no cancela instancias;
  - globales `NULL` incoherentes con el filtro (sin verificar).
- **M76** `collaboration/_transcription.py:85`: `os.path.join(td, audio.filename)` (path traversal con `WHISPER_LOCAL`). — ✅ arreglado 23-11-2026: nombre de fichero saneado.
- **M77** `collaboration/compliance.py:59`: la retención solo corre a mano (sin tarea programada); no purga adjuntos, versiones ni índice. — ✅ arreglado 23-11-2026: retención por empresa con purga de adjuntos (worker).
- **M78** `collaboration/tus.py`: temporales `.tus` nunca limpiados; meta sin lock; todo en memoria. — ✅ arreglado 23-11-2026: metadatos atómicos y purga de subidas caducadas `COLLAB_TUS_TTL_HOURS`.
- **M79** `collaboration/_permissions.py`: caché positiva de 30 s por proceso; una revocación no se propaga entre workers. — ✅ arreglado 23-11-2026: época de permisos en Redis (varios workers).
- **M80** `conectores/anfitrion.py`: `base_url` sin `validate_outbound_url` (con `client_secret` en el cuerpo); cachés de tokens sin tope. ✅ arreglado 23-11-2026: `base_url` validada en `configuracion()` y todas las llamadas por `_SalidaSegura` (`cliente_httpx`).
- **M81** `datos_personales_de_contactos.py:44-99`: con `org=None` anonimiza por email en todas las empresas; no revoca sesiones ni toca `company`. — ✅ arreglado 23-11-2026: empresa obligatoria; empresa del contacto limpiada.
- **M82** `documents_service.py:1-140`: empresa deducida por `created_by` aunque exista `organization_id`; listado y acceso incoherentes; ids vinculados sin validar; fichero huérfano; permisos sin auditoría. — ✅ arreglado 23-11-2026: documentos por empresa, vínculos validados, auditoría de permisos, fichero borrado.
- **M83** `documents_collab_service.py`: sin control de acceso, tamaño ni historial; reloj de Lamport sin lock. — ✅ arreglado 23-11-2026: tope de tamaño, bloqueo e historial podado `DOC_COLLAB_HISTORY_MAX`.
- **M84** `enterprise_service/sso.py:~76-86`: admin sin org crea SSO global (`None == None`). — ✅ arreglado 23-11-2026: ver DOCS.md (SSO).
- **M85** `enterprise_service/webhooks.py`: update sin auditoría; firma sin timestamp en cabecera; `decrypt_value(...) or hook.secret` firma con el cifrado. — ✅ arreglado 23-11-2026: secreto ilegible = fallo; firma v2 con marca de tiempo; auditoría al editar.
- **M86** `epics_service.py:138-148,675-705`: operadores NQL (`!=`, `IN`, `>`) ignorados; `ilike` sin escapar. — ✅ arreglado 23-11-2026: NQL con condiciones seguras y LIKE escapado.
- **M87** `esign_service.py:185-231,407`, `esign_providers.py:45,291,428,492`: — ✅ arreglado 23-11-2026: evidencia manual, transiciones del webhook ordenadas, ruta comprobada.
  - modo manual = clic sin evidencia;
  - estados de webhook sin transición;
  - token sin caducidad;
  - 401 detectado por texto;
  - `filename` y `envelope_id` sin sanear;
  - `os.path.join` sin comprobar `..`.
- **M88** `expense_service.py:76-133,581-596`: aprobar el gasto propio sin bloqueo (sin verificar el endpoint); reembolso sin auditoría. — ✅ arreglado 23-11-2026: bloqueo, SoD y auditoría al revisar/reembolsar.
- **M89** `alm_asignaciones.py:221-254`: asientos de licencia sin `with_for_update` (sobreasignación). — ✅ arreglado 23-11-2026: bloqueo de licencia/pool.
- **M90** `alm_actas.py:240-259,460-497`: fallo de PDF o firma tragado; `serializar` hace commit dentro de un GET. — ✅ arreglado 23-11-2026: fallos anotados; sincronizar con confirmación.
- **M91** `advanced_config_service/*`: roles, tarifas y secuencias sin `audit_log`; `reset_numbering_seq` a 0 provoca duplicados; saldo de vacaciones distinto según la pantalla (`settings` frente a ajuste de empresa). — ✅ arreglado 23-11-2026: auditoría de configuración en `before_flush`; reinicio de numeración en uso rechazado (`numeracion_reset_no_permitido`).
- **M92** `demanda/motor.py`: sin `with_for_update` en la última transición (cadena hash bifurcable). — ✅ arreglado 23-11-2026: bloqueo de la petición.
- **M93** `integration_credentials_service.py:297-307`: respaldo a la fila global que contradice el registro; auditoría tras el commit, tragada (`:521-537`). — ✅ arreglado 23-11-2026: sin respaldo global para secretos sensibles; auditoría en la misma transacción.
- **M94** `integration_credentials_service.py:45-250`: campos URL (`base_url`, `webhook_url`, …) sin validar al guardar. ✅ arreglado 23-11-2026: `set_credential` valida todo campo `*url*`/`host` al guardar.
- **M95** `integrations.py:283-296,550-565`: `format(**entity)` → KeyError que corta el bucle; `get_slack_webhook_url` sin org elige cualquiera; `issue_key` sin escapar. — ✅ arreglado 23-11-2026: ver A55 (fase 1).
- **M96** `jira_service.py:209-267,337,487-579`: — ✅ arreglado 23-11-2026: ver A56/A57.
  - `decrypt_value(x) or x` envía el criptograma;
  - guardar con token vacío lo borra;
  - estados sin reglas de transición;
  - `due_date` como cadena.
- **M97** `grc_sod.py:144-150` + `grc.py:429`: SoD decorativo (solo autoaprobación del mismo módulo; `roles_conflict` no se evalúa). — ➡️ `sod_rules`: agente de la migración 200.
- **M98** `grc_service.py:390-428`: borrar regla con `db.delete`; resolver una violación sin `resolved_by`. — ➡️ `sod_rules`: agente de la migración 200.
- **M99** `informe_de_cumplimiento.py:118-174`: controles tautológicos (`hasattr`); `secrets_encryption: pass` sin KMS; la clave pública va dentro del documento firmado. — ✅ arreglado 23-11-2026: revocación de sesiones con evidencia; KMS obligatorio; huella de la clave pública.
- **M100** `issue_type_service.py:120-377`: `index_entity` sobrescribe entradas ajenas; «FTS» = ILIKE sin escapar, sin purga y con relevancia tras el LIMIT; tipos desactivados chocan; épicas sin detección de ciclos. — ➡️ `issue_types`: agente de la migración 200.
- **M101** `integration_test_service.py:61-77,153`: sonda S3 con la cadena de credenciales del servidor; DocuSign `ok` solo con `account_id`. — ✅ arreglado 23-11-2026: S3 exige claves; OER con cabecera; ContextVar restaurada.
- **M102** `externos/ciclo.py:95-133`: email ficticio `@subcontractor.internal`; contraseña temporal en la respuesta; revocación de sesiones duplicada. — ✅ arreglado 23-11-2026: email duplicado = 409 (`email_ya_registrado`); cambio de contraseña obligado; revocación delegada.
- **M103** `git_service.py:48-55,190-194`: sin idempotencia (reintentos duplican); GitLab no cierra la tarea; `draft` ignorado. — ✅ arreglado 23-11-2026: ver A51.
- **M104** `lecciones.py:482-490,723`: el autor valida su propia lección; `editar_accion` sin comprobar la empresa del responsable. — ✅ arreglado 23-11-2026: ver A31.
- **M105** `lecciones.py:132-178,605`: hechos y recomendaciones en castellano persistidos en BD; recorrido de tablas enteras. — ✅ arreglado 23-11-2026: ver A31.
- **M106** `gastos_politicas.py:139-163`: commit y luego `fuentes.abrir` (gasto enviado sin solicitud si falla). — ✅ arreglado 23-11-2026: una sola transacción en gastos/políticas.
- **M107** `explicar_acceso.py:87-97`: capa de rol por regex sobre el código fuente. — ✅ arreglado 23-11-2026: decisión: introspección + regex solo como pista (estándar).
- **M108** `cmdb_service.py:201-210`: `create_wiki_export_job` deja filas `pending` que ningún worker procesa (stub). — ✅ arreglado 23-11-2026: `POST /cmdb/wiki-export/{page_id}` retirada.
- **M109** `ai_chat/tool_execution/crm.py:41-65` (subida a media): `get_clients` devuelve email y teléfono de todos los clientes con política `None`. — ✅ arreglado 23-11-2026: consulta de clientes con alcance; contactos recortados.

### 3.4 Bajas (42), resumen

- **`key_management.py:189,253,91-99`**: kid por segundo (colisión); rotación web y Celery sin bloqueo; descifra todo el llavero en cada `decode_token` (KMS por petición). — ✅ arreglado 23-11-2026: `kid` con sufijo aleatorio (`_nuevo_kid`), rotación con bloqueo consultivo, material descifrado en caché (`_materiales`); referencia colgante «legacy-secret-key» retirada.
- **`grc_sod.py:36`**: severidad siempre `critical`. — ➡️ `sod_rules`: agente de la migración 200.
- **`grc_service.py:92-132`**: módulos nuevos nacen `allowed=True`; reset en dos pasos con una ventana vacía. — ✅ arreglado 23-11-2026: reset en una transacción (sin ventana vacía). Decisión: los módulos nuevos nacen permitidos (estándar: alta por plan/licencia, no por GRC).
- **`horario/jornadas.py:109`**: `pausa_minutos` sin tope; `int()` revienta con texto. — ✅ arreglado 23-11-2026: pausa validada (0..jornada) con código `jornada.error_pausa_no_valida`.
- **`horario/tramos.py:38`**: excepción doble. — ✅ arreglado 23-11-2026: un solo error con código al no poder leer el tramo.
- **`informe_de_cumplimiento.py:254`**: usa API privada de `cadena_auditoria`. — ✅ arreglado 23-11-2026: usa la API pública de `cadena_auditoria` (`firmar_bytes`, `huella_de_clave_publica`, `canonico`).
- **`integration_test_service.py:238`**: ContextVar sin restablecer. — ✅ arreglado 23-11-2026: ContextVar restaurada (ver M101).
- **`invoice_pdf.py:363`**: `datetime.now()` local; `discount_pct` no se pinta; `:g` con `None` revienta. — ✅ arreglado 23-11-2026: fecha local (`now_local`), descuento pintado y `None` sin reventar.
- **`jira_service.py:80-106`**: descifra los secretos de todas las empresas por webhook sin `?org=`. — ✅ arreglado 23-11-2026: secretos descifrados en caché por empresa; con `?org=` solo esa (ver A56).
- **`integrations.py:868`**: «NexusPM» (marca antigua) y textos en inglés. — ➡️ zona de textos (otro agente, 23-11-2026).
- **`externos/asignaciones.py:21`**: `ValueError` → 500. — ✅ arreglado 23-11-2026: 422 con código (rol no válido) en vez de 500.
- **`exportador_tabular.py:58-147`**: CSV con coma; `filename` sin comillas; todo en memoria. — ➡️ zona de exportaciones (otro agente, 23-11-2026; ver A39).
- **`lecciones.py:221`**: `MajorIncident` sin alcance. — ✅ arreglado 23-11-2026: `MajorIncident` con alcance (ver A31).
- **`horas_extra/consultas.py:283,544,563`**: `json.loads` sin try; 0,8 y 15 fijos. — ✅ arreglado 23-11-2026: `_json_o_vacio` tolera JSON roto; 0,8 y 15 salen de la configuración por defecto (`DEFECTO`).
- **`ai_planning_service.py:20`**: import `validate_outbound_url` sin uso (aparenta protección); `model_used="claude_api"` fijo (`:202`). — ✅ arreglado 23-11-2026: import retirado; `model_used` del proveedor real (ver M48).
- **`ai_chat/agent_execution_service.py:15`**: ejecución sin `organization_id`. — ✅ arreglado 23-11-2026: ejecución con `organization_id`.
- **`ai_chat/agent_loop.py`** frente a **`endpoints/ai_chat.py:524`**: bucle duplicado. — ✅ decisión 23-11-2026: se mantienen los dos caminos (SSE en el endpoint, worker en el bucle) porque sirven transportes distintos; comparten herramientas y aprobación (A7). Documentado.
- **`ai_chat/core_service.py:20`** frente a **`ai_modules/_base.py:120`**: `log_action` duplicada. — ✅ arreglado 23-11-2026: una sola `log_action` (con empresa).
- **`ai_provider_service/clientes.py:157`**: `SessionLocal()` por llamada HTTP. — ✅ arreglado 23-11-2026: espera leída una vez por minuto (`espera_de_ia`, caché 60 s), sin `SessionLocal()` por llamada.
- **`adhoc_analytics_service.py:266,367`**: `strftime` solo SQLite; cross-filter en memoria. — ✅ arreglado 23-11-2026: rango por mes portable (PG/SQLite). Decisión: el cross-filter en memoria se queda (acotado por el tope de filas).
- **`ai_modules/contracts.py:112`**: PDF sin límite de páginas. — ✅ arreglado 23-11-2026: tope `AI_CONTRACT_MAX_PAGES` (ajuste, 200).
- **`alm_uso/sincronizacion.py:177`**: N+1 en picos. — ✅ arreglado 23-11-2026: picos en una consulta (sin N+1).
- **`ai_modules/predictions.py:19,177`**: «ML» que son umbrales; predicción de burnout por persona (RGPD art. 22, sin verificar base legal). — ✅ arreglado 23-11-2026: `method: rule_based` (no se presenta como ML). Decisión RGPD: la predicción de burnout es orientativa, sin decisión automatizada (art. 22 no aplica); la base legal y la DPIA las documenta el responsable.
- **`bi_anomaly_service.py:55`**: `contamination=0.1` marca siempre el 10 %. — ✅ arreglado 23-11-2026: `contamination="auto"`.
- **`bookings_service/divisas.py:46`**: `to_currency="USD"` por defecto. — ✅ arreglado 23-11-2026: moneda de la empresa por defecto (resolutor único de divisas).
- **`automations_service/acciones.py:550`**: nombre invertido `_TAREA_ABIERTA`; niveles comparados como texto. — ✅ arreglado 23-11-2026: `_TAREA_TERMINADA` y niveles por orden, no por texto.
- **`auth_service`**: `organizacion_exige_mfa` fail-open si no existe la organización. — ✅ arreglado 23-11-2026: sin organización → MFA exigido (fail-closed).
- **`bi_o365_service.py`**: datos de Graph por persona sin retención. — ➡️ zona M365 (otro agente, 23-11-2026).
- **`capacity_service.py:29,57,143`**: función duplicada; sin org no filtra; formato de semana distinto en PG y SQLite. — ✅ arreglado 23-11-2026: duplicado retirado; semana en Python (igual en PG y SQLite); horas de las personas de la empresa.
- **`cmdb_service.py:40,358-441`**: `_404` con `que` erróneo; «IA» que es un voraz. — ✅ arreglado 23-11-2026: `que` correcto por entidad (`_QUE`); el plan de sprint dice `method: greedy_by_priority`. Esquema propuesto: renombrar `sprint_plans.ai_reasoning`/`sprint_plan_tasks.ai_note` (migración 200).
- **`cmdb_software/gestion.py:271-362`**: textos fijos; `date.today()`; `except: pass` deja excepciones sin aprobador. — ✅ arreglado 23-11-2026: textos por clave y `timeutil.today()` (ya estaban); la excepción de vulnerabilidad abre su aprobación con `propagar=True` (sin `except` que la deje sin aprobador).
- **`client_portal_service/serializacion.py:84-175`**: etiquetas en castellano. — ➡️ zona portal de clientes (textos, 23-11-2026).
- **`client_portal_service/facturas.py:72`**: el cliente reescribe `internal_notes` sin auditoría. — ➡️ zona portal de clientes.
- **`client_portal_service/panel.py:347`**: NPS medio sesgado. — ➡️ zona portal de clientes.
- **`clientes_internos/paneles.py:21`**, **`peticiones.py:40`**: duck-typing que oculta fallos. — ✅ arreglado 23-11-2026: sin duck-typing: importación directa del flujo de demanda.
- **`client_service.py:1016-1107`**: sección vacía; defaults de portal distintos; `json.loads(None)`. — ✅ arreglado 23-11-2026: un solo valor por defecto (`MODULOS_DEL_PORTAL_POR_DEFECTO`); `json.loads(None)` evitado.
- **`bpmn_process_service.py:649`**: versión sin bloqueo. — ✅ arreglado 23-11-2026: versión con bloqueo (ver M75).
- **`cmdb/parser.py:171`**: `.upper()` sobre un no-texto. — ✅ arreglado 23-11-2026: `str(os_type).upper()`.
- **`cmdb_software/formatos.py:706`**: truncado silencioso a 300 ficheros. — ✅ arreglado 23-11-2026: más de `ZIP_MAX_FICHEROS` → error (`FormatoNoReconocido`), no truncado silencioso.
- **`exchange_rate_service.py:71`**: `httpx.Client` directo. — ✅ decisión 23-11-2026: `httpx` directo admitido (hosts fijos BCE/OER, revisado por la zona de salidas: `_SALIDAS_REVISADAS`).
- **`currency_rates_service.get_report_data`**: parámetros ignorados. — ✅ arreglado 23-11-2026: usa `ref_date` y los parámetros (ver M8).
- **`collaboration/livekit`**: token `dev:` si faltan claves. — ✅ arreglado 23-11-2026: token `dev:` solo con `ENVIRONMENT=development`; si no, 503 `integracion_no_configurada`.

---

## 4. Patrones transversales (medidos)

| Patrón | Medida | Ejemplos |
|---|---|---|
| `if org:` / `if org_id:` → sin filtro si falta (fail-open) | ≥15 sitios en el alcance | `base.py:35`, `dashboard_service`, `contract_service:29`, `expense_service:386`, `ask_the_data:235`, `analytics_service:151,197,314`, `capacity_service:29`, `datos_personales_de_contactos:44`, `cmdb_software/_q`, `calc_q` |
| Imputaciones sin `is_active` | ≥10 consultas | `imputation_service/*` (6), `externos/horas`, `evm_service:99`, `lecciones:142`, `contract_service.horas_usadas` |
| Dinero en `float` | Decenas, todos los lotes | budgets, alm_*, gastos_*, cost_service, evm, facturación recurrente, integraciones contables |
| Suma de importes en monedas distintas | ≥8 módulos | `alm_service`, `client_service`, `dashboard`, `prevision`, `finance` (IA), `gastos_avanzados`, `evm`, `ai_modules/client_portal` |
| Validadores SSRF | 3 propios + 1 común; ≥8 rutas HTTP sin validar | `ai_provider_service`, `ai_tools`, `integration_test_service`, `conectores`, `cmdb/discovery`, `cmdb_software`, `entrega_de_webhooks` (TOCTOU) |
| `ReportLab Paragraph` sin escape y fuente sin CJK | 3 generadores | `invoice_pdf`, `campaign_pdf` (`pdf_export_service` sí escapa) |
| Numeración por `max(code)+1` o `count()+1` | ≥7 sitios | portal (FR, CR, UAT), `cargos`, `tareas_recurrentes`, facturación recurrente, `bots` (`SD-timestamp`), `integrations` (INC) |
| Sin bloqueo de concurrencia en decisiones o cupos | ≥8 sitios | `budgets.decidir`, `alm_asignaciones`, `horas_extra.liquidar`, `automation_events`, `demanda/motor`, `bpmn` versión, `expense review`, `cronometro` |
| Excepciones tragadas que alteran el resultado | ≥12 sitios | discovery (C2), `clientes_internos/costes`, `alm_actas`, `horas_extra/_cfg`, `documentos` firma, `gestion`, `cargos`, `ai_governance` políticas |
| Escrituras que se saltan la capa de dominio | 6 caminos | voz, reuniones, Slack (`integrations`), bots `/imputar`, `/tarea`, `custom_fields.transition_task`, Jira sync |

---

## 5. Código muerto, stubs y funcionalidades fantasma

### Funcionalidades fantasma (parecen existir y no funcionan)

1. La aprobación humana del agente IA (`/ai/agent/{id}/approve`) no existe: `agent_loop.py:88`, `endpoints/ai_chat.py:7`. — ✅ arreglado 23-11-2026 (ver §0).
2. `quick_answer` no existe en `ai_chat_service`: la rama IA de los bots de colaboración nunca responde (`collaboration/bots.py:506`). — ✅ arreglado 23-11-2026 (ver §0).
3. Los webhooks salientes de colaboración se guardan y nada los entrega (`collaboration/webhooks.py`). — ✅ arreglado 23-11-2026 (ver §0).
4. `cron_expression` de la entrega de informes se guarda y no se lee. — ✅ arreglado 23-11-2026 (ver §0).
5. Los `scopes` y `requests_today` de los tokens BI no se aplican. — ✅ arreglado 23-11-2026 (A14).
6. DSR de rectificación y restricción: se aceptan y no se aplican (`bi_gdpr_service`). — ✅ decisión 23-11-2026: rectificación y restricción se confirman a mano (estándar; restricción 422 con motivo) (ver M55).
7. `WikiExportJob`: filas `pending` que nadie procesa (`cmdb_service.py:201`). — ✅ arreglado 23-11-2026 (ver §0).
8. Tareas automáticas BPMN (service, script, send, businessRule) se completan sin hacer nada (`bpmn_engine.py:517`). — ✅ arreglado 23-11-2026 (ver §0).
9. El refresco OAuth de colaboración (`refresh_token_enc`) se escribe y nunca se usa. — ➡️ zona M365/Jira/red (otro agente, 23-11-2026).

### Stubs y datos simulados

| Dónde | Qué |
|---|---|
| `bi_data_versioning_service.py:80-105` | Tabla `_demo` y datos de 2024 — ✅ A61 (sin datos reales → 422) |
| `bi_anomaly_service.py:138-207` | Churn con dataset sintético `random.Random(42)` — ✅ A62 (sin modelo sintético) |
| `ai_modules/predictions.py:19` | `predict_overrun_ml` sin ML — ✅ `method: rule_based` |
| `cmdb_service.py:358` | `generate_sprint_plan` «IA» que es un algoritmo voraz — ✅ `method: greedy_by_priority` |
| `cab_service/correo.py:84-99` | Modo simulado que devuelve `True` — ➡️ zona CAB |
| `collaboration/bots.py:379`, `calls.py:98` | `livekit_room="placeholder"` — ✅ decisión: valor de paso antes del `flush` (NOT NULL); un solo nombre de sala (`_prefijo_de_sala`) |
| `collaboration/livekit` | Token `dev:` — ✅ solo en desarrollo |
| `collaboration/_storage.py` | AV desactivado por defecto («AV disabled (dev)») — ✅ decisión: AV desactivable por configuración (marcado «skipped»); activado y caído → `unavailable` (A24) |
| `integration_test_service.py:153` | Sonda DocuSign stub — ✅ sonda real (zona salidas) |
| `integrations.py:447` | QuickBooks «simplificado» con cliente `"1"` — ✅ M16 |
| `accounting_hub_service.py:153` | `lines: []` — ✅ M21 |
| `esign_service` | Modo manual sin evidencia — ✅ M87 |
| `customer_health_service` | `portal_score = 50.0` — ✅ base configurable y `available: false` |
| `ai_modules/*` | Tarifa 85 €/h por defecto — ✅ decisión: ajuste `AI_REVENUE_HOURLY_RATE_FALLBACK` (solo si no hay tarifa) |

### Funciones y constantes sin uso (búsqueda por referencias fuera del módulo y de tests)

- **absence y ausencias:** — ✅ arreglado 23-11-2026: las tres retiradas (`count_working_days`, `ROLES_QUE_GESTIONAN`; `pasada_diaria` usa la empresa).
  - `absence_service.count_working_days` (`:270`)
  - `ausencias/solicitudes.ROLES_QUE_GESTIONAN` (`:46`)
  - parámetro `org` de `pasada_diaria` (`:741`)
- **integrations y jira:** — ✅ arreglado 23-11-2026: `update_jira_issue`, `slack_create_ticket_from_text` y `tiene_secreto_de_webhook` retiradas.
  - `integrations.update_jira_issue` (`:159`)
  - `integrations.slack_create_ticket_from_text` (`:742`)
  - `jira_service.tiene_secreto_de_webhook` (`:121`)
- **git_service:** `git_service.get_task` (`:383`). — ✅ verificado 23-11-2026: `get_task` sí se usa (falso positivo).
- **externos:** `disponibilidad.capacidad_en_dia` y `fraccion_de_semana` (`:73,80`). — ✅ arreglado 23-11-2026: retiradas.
- **imputation_service:** `imputation_service._comun.compute_cost`, solo reexportada. — ✅ arreglado 23-11-2026: `compute_cost` retirada (y su reexportación).
- **cmdb y capacity:** — ✅ arreglado 23-11-2026: `_CI_SPECIFIC` y `get_plans_for_leveling` retiradas.
  - `cmdb_service._CI_SPECIFIC` (`:30`)
  - `capacity_service.get_plans_for_leveling` (`:143`), duplicado literal de `:36`
- **divisas y costes:** — ✅ arreglado 23-11-2026: `ECB_CURRENCIES` y `DEFAULT_COUNTRY_PRESETS` retiradas; `get_rate` se queda (delega en el resolutor único y la usan las pruebas).
  - `exchange_rate_service.ECB_CURRENCIES` (incluye HRK retirada) y `get_rate` (`:197`)
  - `cost_service.DEFAULT_COUNTRY_PRESETS`
- **documentos:** argumento `content` de `documents_service.create_document_version`. — ✅ arreglado 23-11-2026: argumento `content` retirado (servicio y endpoint).
- **collaboration/_integrations_clients.py:** `jira_create_issue`, `github_create_issue`, `gitlab_create_issue`, `google_calendar_create`, `m365_calendar_list` y `m365_send_mail`. Solo `google_calendar_list` tiene uso. — ✅ arreglado 23-11-2026: las cinco sin uso retiradas; quedan `google_calendar_list` y `m365_calendar_list` (en uso).
- **ai_chat:** — ✅ arreglado 23-11-2026: consulta duplicada retirada (M50) y `rag_service.kb_rag_context` (verificado sin llamadas) borrado con su módulo.
  - consulta `q_inv`/`inv_rows` (`context_service.py:565-572`)
  - `rag_service.kb_rag_context` (sin verificar)
- **ai_planning_service:** import `validate_outbound_url` (`:20`). — ✅ arreglado 23-11-2026: import retirado.
- **key_management:** referencia colgante `"legacy-secret-key"` (`:259`). — ✅ arreglado 23-11-2026: referencia colgante retirada.
- **`pass` ociosos:** — ✅ arreglado 23-11-2026: los cuatro anotan con `logger.warning` (o propagan).
  - `approval_engine/diagrama.py:70`
  - `approval_engine/_base.py:189`
  - `ausencias/turnos.py:90`
  - `clientes_internos/cargos.py:200-203`

---

## 6. Hardcode

### Idioma: textos en castellano visibles o persistidos

Contradicen la regla de operadores es/en/zh obligatorios. Más de 40 sitios:

- **ausencias, alertas y configuración:**
  - `absence_service.py:257-267,312`
  - `alert_service.py:315`
  - `advanced_config_service/tarifas_y_vacaciones.py:185`
  - `roles_y_tipos.py:71,92`
- **proveedores y ALM:**
  - `activity_service/proveedores.py:51,108`
  - `alm_service.py:960`
- **ai_chat:** `ai_chat/tool_execution/*` (19 mensajes de error, existiendo ya `textos_de_salida`).
- **ai_modules:**
  - `ai_modules/voice.py:86-196`
  - `meetings.py:114-186`
  - `client_portal.py:31-76`
- **ai_planning_service:** `ai_planning_service.py:266-280` (palabras clave solo en español).
- **ask_the_data:** `ask_the_data.py:357-430`.
- **facturación:** `billing_reports_service/facturas.py:162` («Sin cliente»).
- **portal de clientes:**
  - `client_portal_service/serializacion.py:84-175`
  - `peticiones.py:82`
  - `clientes.py:126,319`
  - `facturas.py:74`
- **client_service:** `client_service.py:441,529,877,935,1011`.
- **cmdb:**
  - `cmdb_service.py:209,368-408`
  - `cmdb_software/gestion.py:271-277`
- **cab_service:** `cab_service/correo.py:61-69,152`.
- **gastos:**
  - `expense_service.py:53-71,160-209`
  - `gastos_avanzados.py:32-41` (duplicado de `expense_service`)
  - `gastos_politicas.py:139-146`
- **custom_fields_service:** `custom_fields_service.py:303-327`.
- **grc_sod:** `grc_sod.py:109-120` (en BD).
- **horario y horas extra:**
  - `horas_extra/ejemplos.py:47-79`
  - `control.py:144`
  - `horario/jornadas.py:104-115`
- **imputaciones y externos:**
  - `imputation_service/_comun.py:125`
  - `consultas_y_edicion.py:72,90`
  - `externos/horas.py:90`
  - `ciclo.py:199`
- **issue_type_service:** `issue_type_service.py:25-33`.
- **lecciones:** `lecciones.py:132-302,605` (en BD).
- **automations_service:** `automations_service/reglas.py`.
- **collaboration/bots:** `collaboration/bots.py` (`"assignee": "soporte"`).
- **campaign_pdf:** `campaign_pdf.py:190`.

### Estado del hardcode de idioma (✅ 23-11-2026)

Recuento de líneas con texto castellano fijo (cadenas con acentos/ñ, sin docstrings/comentarios/logger) en los 55 ficheros de la lista: **246 antes → 118 después**; sin las tablas multilingües es/en/zh de `demanda/` (65 líneas, que son contenido legítimo en tres idiomas) son **181 → 53**. Los 53 restantes son prompts que se le dan al modelo, `detail=` de respaldo de errores que ya llevan código traducible y alguna palabra clave de detección.

- ✅ **ausencias, alertas y configuración:** `absence_service` (etiquetas de tipo y estado por clave `ausencia.*`, en el idioma de quien mira), `alert_service` (sobrecarga, tarea bloqueada y fecha límite en el idioma de la empresa, `alerta.*`). ⏸ `advanced_config_service/roles_y_tipos.py:71,92,171`: `NotFoundError("Rol/Configuración no encontrada")` se re-emite con su texto en 6 endpoints (`advanced_config.py`); exige cambiar esos endpoints a `error(404, "no_encontrado", que=...)`. `tarifas_y_vacaciones.py`, `activity_service/proveedores.py`, `alm_service.py` ya no tenían el literal (arreglados antes).
- ✅ **ai_chat:** las salidas de error de `tool_execution/*` (`crm`, `executor`, `projects`, `risks`, `meetings`, `tickets`, `software`) salen de `ia_tool.*` en el idioma del usuario (`tool_execution/textos.py`). El resto de ficheros de la carpeta ya no tenían literales.
- ✅ **ai_modules:** `voice.py` (todas las acciones/propuestas, `voz.*`), `client_portal.py` (respuesta sin IA en el idioma de la ficha del cliente, `portal_ia.*`), `meetings.py` (título por defecto y nota de truncado guardados en el idioma de la empresa, `reunion.*`). ⏸ los prompts de sistema al modelo (`_CLIENT_AI_SYSTEM`, `_SISTEMA_DE_REUNION`, `_SUFIJO_DE_REDUCCION`, `ask_the_data.py:258`, `lecciones._SISTEMA`) siguen en castellano: son instrucciones al modelo, no texto de salida (el modelo responde en el idioma del usuario).
- ✅ **ai_planning_service:** palabras clave de prioridad, categoría y estimación con variantes en inglés y chino; razones de la estimación y del triaje por clave (`planificacion.*`). Las etiquetas de categoría («Acceso y seguridad»…) son datos del ticket y no se tocan.
- ⏸ **ask_the_data:** el `detail` de `_verificar` no lo pinta la interfaz (usa `verdict` y `name`, con claves `askdatawidget.verif_*`); queda como texto técnico.
- ✅ **portal de clientes:** `serializacion.py` y `peticiones.py` (etiquetas de estado, prioridad, impacto y categoría en los 8 idiomas del portal, `portal_etiqueta.*`; `fr_out`/`doc_out` reciben el idioma del cliente), `panel.py` (mensajes), `clientes.py` (correo de acceso en 8 idiomas). ⏸ `facturas.py:74` y los listados del equipo (`list_all_feature_requests`) siguen en castellano porque no hay cliente delante (idioma del operador no disponible en el servicio). «Sin cliente» de facturas ya estaba ✅.
- ✅ **client_service** (alertas de la ficha 360, `cliente.alerta.*`); ⏸ `client_service.py:1175`: el `detail=` de respaldo del error con código.
- ✅ **cmdb:** `cmdb_service.generate_sprint_plan` (razonamiento guardado en el idioma del usuario, `plan_sprint.*`), `cmdb_software/gestion.py` (título y cuerpo de los tickets, problemas y cambios de remediación y la solicitud de excepción, `sw_remediacion.*`).
- ✅ **cab_service/correo:** plantillas de correo de serie (`plantilla_correo.*`, `plantillas_de_serie(idioma)`) y asunto por defecto.
- ✅ **gastos:** una sola fuente de categorías (`gastos_avanzados.etiqueta_de_categoria`; `expense_service` ya no tiene su diccionario duplicado ni `_STATUS_LABELS`), avisos de aprobación/rechazo al propietario en su idioma y texto del historial de aprobaciones (`gasto.*`). El Excel de gastos ya estaba ✅ (cabeceras, estados y Sí/No). `gastos_politicas.py` ya no tenía el literal.
- ✅ **custom_fields_service** (estados y transiciones del flujo de serie en el idioma de la empresa, `flujo.*`), **issue_type_service** (tipos de serie, `tipo_incidencia.*`). ⏸ los `detail=` de respaldo con código.
- ✅ **grc_sod:** las 10 descripciones de serie son claves `sod.*` y `grc_service.ensure_sod_seeded` las guarda en el idioma de la empresa. Las reglas ya sembradas en castellano no cambian.
- ✅ **horas extra y horario:** `horas_extra/ejemplos.py` (políticas de ejemplo en el idioma de quien las carga, `horas_extra.ej.*`), `control.py` (aviso a cada destinatario en su idioma), `horario/jornadas.py` (errores de validación).
- ✅ **imputaciones y externos:** `_comun.py` (aviso de imputación forzada al responsable en su idioma), `externos/horas.py` (aviso de consumo). ⏸ `consultas_y_edicion.py`: sus `detail=` ya llevan código (`imputar_mas_de_24h`, `imputar_supera_capacidad`, `sin_permiso`). `externos/ciclo.py` ya no tenía el literal.
- ✅ **lecciones:** las etiquetas de los hechos son claves `leccion.hecho.*` (el borrador y la lista de hechos salen en el idioma de quien mira), frase de recomendación y avisos de la IA. ⏸ los `detail=` de respaldo con código y el prompt al modelo.
- ✅ **automations_service/reglas:** frases de «Probar» (`automatizacion.efecto.*`), plantillas de automatización (`plantilla_auto.*`, el endpoint pasa el idioma). Las reglas ya creadas por empresas no cambian.
- ✅ **collaboration/bots:** salidas de los slash commands, ayuda (`slash_help(idioma)`), bienvenida, resúmenes y `"assignee": "soporte"` (ahora `None`; el texto dice «soporte» en el idioma). ⏸ `GET /collaboration/slash/help` no pasa idioma (sin usuario en el endpoint): la ayuda sale en castellano hasta que se añada la dependencia.
- ✅ **campaign_pdf.py:190:** ya no tenía el literal.
- ⏸ **Portal en fr/de/it/pt/pl:** solo las etiquetas del portal, los mensajes del panel y el correo de acceso están en los 8 idiomas; `portal_ia.*` y el resto de claves están en es/en/zh (el portal cae al castellano en los otros cinco).

### Negocio de un cliente concreto dentro del producto (✅ 23-11-2026)

`demanda/plantillas.py` y `biblioteca.py`: la plantilla «piloto» pasa a ser **opcional** (`biblioteca.PLANTILLAS["nueva_funcionalidad"]`, «Nueva funcionalidad con CAB y comité»; la clave antigua `piloto_digital` se acepta como alias y se reconoce en las empresas que ya la instalaron). Los grupos son genéricos y traducibles («Triaje de solicitudes», «Equipo de análisis», «CAB», «Comité de dirección»; es/en/zh) y se crean en el idioma de la empresa. Nada se crea por defecto: `seed_demanda()` ya no siembra y `_sembrar_demo()` de la migración 195 retorna sin hacer nada (solo afectaba a la empresa demo; las empresas que ya la tenían conservan sus grupos y flujo).

### Migraciones / esquema que exigiría completar lo pendiente

- Los textos de serie que se guardan una vez (nombres de grupos, reglas SoD, tipos de incidencia, flujos de serie, plantillas de automatización, razonamiento del plan de sprint) quedan en el idioma de la empresa **al crearse**: no hay columna `clave`/`parametros` para pintarlos luego en el idioma de cada lector. Hacerlo exigiría añadir `nombre_clave` (y `parametros` JSON) a `sod_rules`, `issue_types`, `workflow_states`, `workflow_transitions` y `approval_groups`, y un `ai_reasoning_params` a `sprint_plans`. **No se ha creado ninguna migración.** ✅ 23-11-2026 (migración 200): creadas (`texto_clave`/`texto_params`, uno por tabla: en `grc_sod_rules` el de la descripción, que es lo que se lee). Cableadas en SoD, tipos de incidencia y flujos de serie; `approval_groups` solo lectura/edición (la demanda siembra con su propio diccionario) y `sprint_plans.ai_reasoning_params` preparada (el razonamiento es un texto compuesto).

### Monedas

- `"EUR"`: `formato_regional.py:51`, clave `cost_delta_eur` en `planificacion.py:267`, `contract_value_eur` en `client_service.py:433`.
- `"USD"`: `bookings_service/divisas.py:46`.
- Tarifa 85 €/h: `ai_modules/*` (8 sitios).

### Umbrales y valores legales en código

| Valor | Dónde |
|---|---|
| 24 h/día | `alta.py:127`, `consultas_y_edicion.py:71`, `cronometro.py:243` |
| Mínimo 0,25 h | `cronometro.py:217` |
| Tolerancia 15 y 0,8 | `horas_extra/config.py:29`, `consultas.py:544,563` |
| 09:00 y 8 h | `horario/efectivo.py:182` |
| `weekday() < 5` | `externos/disponibilidad.py:86,107` |
| 65 min y `maxResults 100` | `jira_service.py:683,706` |
| Esperas `(60,300,1800)` y umbral 5 | `entrega_de_webhooks.py:23,35` |
| Pesos de avance EVM 0,8 y 0,5 | `evm_service.py:115-123` |
| Pesos del scorecard | `activity_service/proveedores.py:26` |
| Factor `*0.7` | `planificacion.py:221` |
| `contamination=0.1`, z 2,5 | `bi_anomaly_service` |
| 1.024 IP, `public`, puerto 161 | `cmdb/discovery.py:530,599-601` |
| 500 hosts | `escaneos.py:465` |
| 300 ficheros / 60 MB | `formatos.py:690` |
| 60 días y puntos de riesgo | `client_service.py:362-442` |
| 72 h | `client_portal_service/autenticacion.py:18` |
| `MAX_ROWS 200` | `ask_the_data.py:24-30` |
| Umbral 70 % | `ask_the_data` (fallback) |
| 5.000 filas | Entrega de informes |
| Posición de firma `x100`, `y650` | `esign_providers.py:222` |

### Estados como cadenas en lugar de enums

- `bpmn_engine.py:64-75,444`
- `budgets_service.py:40,598`
- `change_service.py:25`
- `client_portal_service/peticiones.py:252`, `uat.py:151`, `wiki_y_encuestas.py:51`
- `clientes_internos/paneles.py:56`
- `context_service.py:144,569`
- `finance.py:70-126`
- `alm_service.py:217`
- `alm_conciliacion.py:191`
- `voice.py:126` (`"open"`, que además es inválido)
- `subcontratas.py:~660`
- `deliverable_service`
- `horas_extra` (`VIVOS`)
- `lecciones.ESTADOS`
- `automations_service/catalogo.py:69`
- Roles `("admin","hr","pm","team_lead")`: `solicitudes.py:54`, `consultas.py:36`, `config.py:65`, `jornadas.py:238`, `lecciones.py:264`, `client_service.py:143,457`

### URLs y valores de proveedor

- `anthropic-version 2023-06-01`: `integration_test_service.py:188`.
- Rutas `/rest/api/3` y `"Task"`/`"Medium"`: `integrations.py:116-130`.
- Xero `"OUTPUT"`/`"AUTHORISED"`: `integrations.py:423,430`.
- QuickBooks `minorversion=65`: `integrations.py:390`.
- `login.microsoftonline.com`: `terceros.py:558`.
- Google Calendar v3: `cab_service/integraciones.py:124`.
- BCE y OpenExchangeRates: `exchange_rate_service.py:34,168`.
- Prefijo `nxpm_`: `developer_portal_service`, `bookings/api_keys`.
- Dominio `@subcontractor.internal`: `externos/ciclo.py:96`.
- Precios por modelo fijos en `PROVIDER_CATALOG`.

---

## 7. Arquitectura y duplicaciones

1. **Aislamiento implícito con huecos.** Todo cuelga del filtro de sesión, que no cubre UPDATE/DELETE masivos, jobs ni superadmin, y del helper `_scoped`, que falla abierto. Unos servicios filtran explícitamente (`esign`, `collaboration`, `entrada`, `cartera`) y otros no. Propuesta:
   - un helper único `de_la_empresa(q, Model, org)` que **falle cerrado** si `org` es None (salvo superadmin explícito);
   - extender el listener a `is_update`/`is_delete`.
2. **Cuatro cálculos de margen** que pueden dar cifras distintas en pantallas distintas: `dashboard_service.get_profitability`, `profitability_service`, `evolucion_del_margen` y `enterprise_service/prevision`.
3. **Cuatro resolutores de tipo de cambio:**
   - `currency_rates_service.get_rate`;
   - `currency_rates_service.resolve_rate` / `_with_snapshot`, que devuelven 1,0;
   - `exchange_rate_service.get_rate`, que devuelve None y está muerto;
   - `profitability_service.get_fx_rate`, que devuelve 1,0 sin inversa.

   Unificar con tipo cruzado vía EUR y error explícito.
4. **Coste ALM en tres sitios** con semánticas distintas: `alm_service.coste_anual_vigente`, `alm_costes.lineas` y `alm_asignaciones._coste_anual_estimado`.
5. **SSRF: un validador común** (`app/core/outbound_url` + `cliente_httpx`, buen patrón en `alm_uso/proveedores/http.py` y `entrega_saliente`) **y tres propios** (`enterprise_service/webhooks._BLOCKED_NETWORKS`, `automations_service/acciones._motivo_de_rechazo_ssrf`, `bookings._validate_provision_url`), además de ≥8 rutas sin ninguno.
6. **Credenciales en seis almacenes** (`integration_credentials`, `IntegrationConfig.config`, `slack_configs`, `sd_jira_configs`, `AppSetting`, entorno), con rotación parcial (A38) y cuatro rutas de «probar conexión».
7. **Cuatro caminos de Slack**: `integrations.send_slack_message`, `slack_service`, `entrega_saliente` y `canal_slack`.
8. **Tres sistemas de webhooks**: `entrega_de_webhooks`, `collaboration/webhooks` y los webhooks entrantes de `cab_service`.
9. **Imputaciones: cuatro caminos de alta** (alta, cronómetro, Slack y bots/voz) con reglas distintas. El tope diario está en 3 sitios y el semanal en 2. La capacidad semanal se calcula de 3 formas: `capacidad_semanal`, `horario/efectivo` y `externos/disponibilidad`.
10. **Numeración de códigos.** `numbering.next_numbered_code` / `NumberingSequence` y `next_invoice_number` conviven con ≥7 implementaciones ad hoc.
11. **Dos «cambios»**: `change_service` (CR de proyecto) y `service_desk/change_service` (ITIL). El portal crea además CR con su propia numeración y su propia aprobación.
12. **Nombres engañosos:**
    - `cmdb_service.py` no es CMDB (wiki, Kanban, sprint, SLA); la CMDB real está repartida en `cmdb/`, `service_desk/cmdb_service` y `cmdb_software/`.
    - `capacity_service` y `capacity_planning_service` son dominios distintos con nombres casi iguales.
    - `billing_reports/` (sin `__init__`) convive con `billing_reports_service/`.
13. **Transacciones repartidas.** Más de 100 `db.commit()` dentro de servicios, solo en el lote de BI y facturación. Hay commits antes de abrir la aprobación (`change_service`, `gastos_politicas`, `pedir_baja`), escrituras dentro de GET (`alm_actas.serializar`, `list_roles` siembra) y auditoría fuera de la transacción (`integration_credentials_service`). El contrato de transacción es heterogéneo.
14. **Estado en `AppSetting` como blob JSON** en ~14 ficheros `bi_*`, con lectura-modificación-escritura sin bloqueo (pérdida de escrituras) y crecimiento sin límite.
15. **Fachadas que reexportan privados** (`ai_chat_service`, `ai_modules_service`, `enterprise_service/__init__`, `client_portal_service`, `cab_service`) para mantener tests con monkeypatch. Acoplan la API interna.
16. **Duplicados de detección y predicción:** Prophet en `bi_forecasting` y en `bi_intelligence`; z-score en tres sitios; dos bucles de agente IA; `log_action` duplicada; `CATEGORY_LABELS` de gastos duplicado.
17. **Tres bitácoras de auditoría** (`audit_log`, `GrcAuditLog`, `settings_audit`) y una cadena de colaboración aparte (C5). La integridad no es homogénea.

---

## 8. Orden de arreglo recomendado

1. C1, C2, C3, C4, C5.
2. Aislamiento: helper fail-closed y listener en UPDATE/DELETE. Cubre A10-A12, A25, A29-A30 y M-patrón.
3. SSRF unificado: A20, A21, A27, A28, M80, M94.
4. A1 (ABAC roto), A39 (fórmulas), A40 (filtro de gastos), A41 (FX 1,0).
5. Imputaciones: A45-A48, A34, A35, A6.
6. Portal de cliente: A15-A17.
7. RGPD: A60, A64, M47, M55, M81.
8. Claves: A37, A38.
9. Dinero en `Decimal` y numeración centralizada.
10. Hardcode de idioma (es/en/zh).
