# Auditoría 04b — Frontend: páginas raíz F–Z y subcarpetas

Fecha: 2026-11-23 · Alcance: 82 páginas raíz de `frontend/src/pages` de la F a la Z, y las subcarpetas `alm/`, `bpm/`, `clients/`, `internos/`, `portal-client/`, `profitability/`, `proveedores/`, `service-desk/`, `settings/` y `settings-sections/`. En total son 182 ficheros (166 `.tsx` y 16 `.ts`, sin tests) y 67.451 líneas. · Modo: solo lectura. No se ejecutaron tests, lint, typecheck ni build. · Complementa a `04_frontend_paginas_ux.md`, cuyos hallazgos no se repiten. Donde un hallazgo amplía uno del 04, se cita (A6, A8, A9, M4, M5, M7, B3, B9).

## Resumen

**Método (honesto):**
- **Scripts sobre los 182 ficheros:**
  - Endpoints y servicios llamados.
  - Claves `t('…')` literales con todos los alias de traductor (`t`, `traducir`, `tApp`, `tr`, `ts`, `_t`). Son 8.442 claves, comprobadas contra `i18n/langs/{es,en,zh}.mjs`. Las del portal se comprobaron contra `i18n/portal/*.ts`.
  - Prefijos dinámicos (`t(\`x_${…}\`)` y `t('x_' + …)`), paridad es/en/zh de los 178 módulos usados y valores vacíos.
  - `queryKey` repetidas con `queryFn` distintos (en todo `src/`).
  - `useMutation` sin `onError` (460 mutaciones).
  - `href`/`src` con datos, borrados sin confirmación y `useEffect` (84 extraídos y revisados uno a uno).
  - Exportaciones y funciones sin uso, literales en JSX, colores y monedas fijos.
- **Lectura dirigida:**
  - Completa: GovernancePage, IntakeFormPage, UsoRealTab, ResetPasswordPage (parcial) y las zonas de acción de SettingsPageSections, TicketDetail, OrganizationsPage, PortalUsersTab, TimerPage, WikiPage, ResourceSchedulerPage, ClientsPageTabs, WorkflowDesignerPage, FuentesPanel, PipelinePage y PortalClientePage.
  - Del resto: handlers, mutaciones y efectos localizados por los scripts.
  - No se leyó línea a línea todo el JSX de las páginas de más de 800 líneas. Lo no comprobado se marca «sin verificar».
- **Contraste con el backend:** cuando un hallazgo dependía del servidor, se miró el endpoint (`users.py`, `client_portal.py`, `public_forms.py`, `proveedores/portal.py`, `okrs.py`, `invoices.py`).

**Lo bueno, medido:**
- **i18n.** De 8.442 claves literales, solo 2 no resuelven a texto (ver «Claves i18n que faltan»). Los 178 módulos usados tienen paridad total es/en/zh, con la única excepción de 3 claves de `demanda` fuera de `pages/`. Las 59 claves del portal usadas aquí existen en los 8 idiomas. Las 72 secciones de Configuración tienen su `ajustes.s_*`.
- **Rutas y código vivo.** Todas las páginas del alcance tienen ruta, sección en `/settings/:seccion` o padre que las monta. No hay páginas huérfanas nuevas.
- **Confirmaciones.** Las mutaciones destructivas grandes piden confirmación del kit: OKR, Pipeline, Training, UAT, Archivar flujo, Cambios, Organizaciones con motivo y Proveedores. Solo 14 de 460 mutaciones no tienen `onError`, y 4 de ellas pintan `isError`.
- **Errores de consulta.** Hay un `onError` global en `QueryCache` (`main.tsx:137-140`), así que las consultas que fallan avisan por toast. El A9 del 04 afecta solo a los `.catch(() => [])`, que se saltan ese aviso.
- **Configuración centralizada.** Git, Horas extra, Semantic Engine y Service Desk redirigen `?tab=config` a `/settings/...`. Los avisos contextuales (Reuniones, Proveedores, Políticas, Recuperación ALM) enlazan con permiso.
- **Seguridad.** Los adjuntos que sube el proveedor desde su portal se validan como `http(s)` en el backend (`app/services/proveedores/portal.py:188-193`). TrainingPage usa `sanitizeUrl`. No hay tokens en `localStorage`.

**Recuento de hallazgos nuevos:** críticos 0 · altos 4 · medios 10 · bajos 8.

**Altos:**
1. **ALTA. «Activar» un usuario lo desactiva otra vez.** `SettingsPageSections.tsx:306` llama a `deactivate(u.id)`, que hace `DELETE /users/{id}`. Así se relanza la baja de ALM y no hay forma de reactivar a nadie desde la interfaz.
2. **ALTA. Fuga de WebSocket en la ficha de cliente.** En `clients/ClientsPageTabs.tsx:634-659`, el `onclose` reconecta incluso después de desmontar: el cierre de la limpieza programa una reconexión. Se acumulan sockets en cada cambio de cliente o idioma.
3. **ALTA. `test_environment` sin sanear en `href`.** El campo es texto libre (`client_portal.py:139`) y se pinta en el portal externo (`PortalAdvancedSections.tsx:302`) y en la ficha interna (`ClientsPageTabs.tsx:607`). Es el mismo vector que el A6 del 04, pero en otro campo.
4. **ALTA. Configuración dentro de un módulo.** La pestaña «Fuentes» de ALM → Uso real (`alm/uso/UsoRealTab.tsx:73`, `FuentesPanel.tsx:25-50,214-215`) tiene un botón «Configurar» por fuente, credenciales y opciones, en vez de estar en `/settings/:seccion`.

## Mapa de páginas

`Ruta / dónde se monta`: ruta de `App.tsx`, sección de `settings/catalogoDeAjustes.tsx` o componente padre. `Endpoints`: servicios de `services/api` o llamadas directas `api.*`, con un máximo de 4. `Estado`: «completa» significa que no se encontró nada roto ni a medias en lo revisado. Las referencias (A1, M3…) son las de este documento.

| Fichero | Ruta / dónde se monta | Qué hace | Endpoints (servicios) | Estado |
|---|---|---|---|---|
| `FinanceDashboardPage.tsx` | /finance-dashboard | Panel financiero: rentabilidad, cartera de clientes, pipeline, facturas, tipos de cambio y costes del periodo. | profitabilityApi, invoicesApi, currencyApi, userCostsApi | completa |
| `ForbiddenPage.tsx` | /403 | Pantalla 403 (sin permiso). | — | completa |
| `GanttPage.tsx` | /gantt | GanttPage — delegated to GanttChart v2 component. | projectsApi, tasksApi, taskDependenciesApi, aiCopilotApi | errores crudos (M2) → ✅ arreglado 23-11-2026 |
| `GitPage.tsx` | /git | GitPage — bidirectional Git integration dashboard | gitApi | enlaces con recarga (M6) → ✅ arreglado 23-11-2026 |
| `GovernancePage.tsx` | /settings/ai-governance | Gobernanza de IA: módulos (encender/apagar), uso por módulo y auditoría. | governanceApi, aiProvidersApi | completa |
| `GrcPage.tsx` | /settings/grc | GrcPage — Governance, Risk & Compliance (backbone de seguridad) | grcApi, approvalsApi, governanceApi, usersApi | enlace con recarga (M6); `grc.los` vacío en zh (B1) → ✅ arreglado 23-11-2026 |
| `HorasExtraPage.tsx` | /overtime | Horas extra (18-11-2026): petición previa o declaración posterior, | — | completa |
| `ImportPage.tsx` | /settings/import | ImportPage — Importación masiva de datos desde CSV/Excel | importApi | errores crudos (M2) → ✅ arreglado 23-11-2026 |
| `ImputarPage.tsx` | /imputar | Imputación de horas del día/semana, con temporizador y sugerencias de IA. | projectsApi, tasksApi, imputationsApi, aiCopilotApi | errores crudos (M2); `['projects']` (M5) → ✅ arreglado 23-11-2026 |
| `InboxPage.tsx` | /inbox | InboxPage — Bandeja unificada de Notificaciones, Menciones y Aprobaciones. | — | completa |
| `IntakeFormPage.tsx` | /intake/:token | IntakeFormPage — Public-facing form, no auth required. | GET /forms/public/${token}, POST /forms/public/${token}/submit | parcial: falla sin correo (M3) → ✅ arreglado 23-11-2026 |
| `InvoicesPage.tsx` | /invoices | InvoicesPage — Facturación: crear, gestionar y hacer seguimiento de facturas | accountingApi, invoicesApi, projectsApi, clientsApi | `_PALETTE` sin uso (código muerto); `['projects']` (M5) → ✅ arreglado 23-11-2026 |
| `IssueTypesPage.tsx` | /settings/issue-types | Tipos de incidencia por proyecto y sus campos personalizados. | issueTypesApi, projectsApi, customFieldsApi | completa |
| `JiraIntegrationPage.tsx` | /settings/jira | Conexión con Jira: credenciales, importación y secreto del webhook. | jiraApi | autocompletado de contraseña en el token (B3) → ✅ arreglado 23-11-2026 |
| `LeccionesPage.tsx` | /lessons | Lecciones aprendidas — la base de la mejora continua (revisión 2026-11). | leccionesApi | completa |
| `LoginPage.tsx` | /login | Inicio de sesión: contraseña, SSO, passkey, segundo factor y selector de empresa. | authApi | completa |
| `M365Page.tsx` | /settings/m365 | M365Page — integración con Microsoft 365: calendario (leer eventos, llevar | — | completa (sección de Ajustes) |
| `MFAPage.tsx` | /settings/mfa | MFAPage — Configuración de autenticación en dos pasos (TOTP) | mfaApi | completa |
| `MeetingsAIPage.tsx` | /meetings-ai | MeetingsAIPage — Asistente de reuniones (rehecha el 19-11-2026). | reunionesApi | completa |
| `MentionsPage.tsx` | dentro de InboxPage.tsx | Pestaña «Menciones» de la bandeja: menciones recibidas, marcar leídas y responder. | mentionsApi | completa |
| `MilestoneBillingPage.tsx` | /milestone-billing | MilestoneBillingPage — Facturación por hito. | milestonesApi, projectsApi | mensaje del servidor sin traducir (M2) → ✅ arreglado 23-11-2026 |
| `MisEquiposPage.tsx` | /my-equipment | Mis equipos y licencias — autoservicio de cada persona (licencias y hardware, fase 4). | almIntegracionApi | etiqueta `almint.urgencia` sin traducir (B2) → ✅ arreglado 23-11-2026 |
| `NPSPage.tsx` | /nps | NPSPage — Customer NPS & Health trend dashboard | npsApi, clientsApi | recalcular salud sin `onError` (M1) → ✅ arreglado 23-11-2026 |
| `NexusAgentPage.tsx` | /nexus-agent | NexusAgentPage — el agente que ejecuta instrucciones en lenguaje natural. | aiProvidersApi, nexusAgentApi | completa |
| `NotFoundPage.tsx` | * | Pantalla 404. | — | completa; TODO de tipado (ya en B9) → ✅ cerrado 23-11-2026 |
| `NotificationsPage.tsx` | dentro de InboxPage.tsx | NotificationsPage — Bandeja de entrada de notificaciones | alertsApi, avisosApi, GET /enterprise/notifications, POST /enterprise/notifications/${id}/read | marcar leído sin `onError` (M1) → ✅ arreglado 23-11-2026 |
| `OKRsPage.tsx` | /okrs | OKRsPage — Objectives & Key Results | okrsApi, usersApi, projectsApi, settingsApi | completa |
| `OraclePage.tsx` | /oracle | OraclePage — NexusOracle: riesgos y anomalías detectados por reglas. | oracleApi | completa |
| `OrgChartPage.tsx` | /org-chart | OrgChartPage — Organigrama, posiciones y cadenas de aprobación | settingsApi, usersApi | completa |
| `OrganizationsPage.tsx` | /settings/organizations | OrganizationsPage — Gestión multi-tenant de organizaciones | organizationsApi, usersApi | completa |
| `PerformanceReviewsPage.tsx` | /performance-reviews | PerformanceReviewsPage — Evaluaciones de rendimiento 360° | performanceApi, usersApi | completa |
| `PipelinePage.tsx` | /pipeline | PipelinePage — embudo comercial (oportunidades por etapa). | pipelineApi | solo tablero, sin lista (M9) → ✅ arreglado 23-11-2026 |
| `PlanificacionDeRecursosPage.tsx` | /resources/planning | Planificación de recursos: asignaciones por persona y proyecto. | projectsApi, skillsApi, usersApi, recursosApi | completa |
| `PoliticasPage.tsx` | /settings/policies | Políticas y reglas (tarea #26): el motor común de gastos, ausencias y lo que | politicasApi | completa |
| `PortalClientePage.tsx` | /portal | PortalClientePage — Portal externo del cliente. | GET /portal/branding, GET /portal/surveys, GET /portal/dashboard, GET /sd/tickets/client/my | completa |
| `PortalPublicViewPage.tsx` | /portal/view/:token | Vista pública del estado de un proyecto por enlace con token (sin sesión). | GET /portal/view/${token} | completa; TODO de tipado (ya en B9) → ✅ cerrado 23-11-2026 |
| `PortfolioPage.tsx` | /portfolio | PortfolioPage — Gestión de carteras de proyectos | projectsApi, portfolioApi | completa |
| `PredictionsPage.tsx` | /predictions | PredictionsPage — Inteligencia predictiva. | — | completa |
| `PreguntarALaEmpresaPage.tsx` | /ask-company | Preguntar a la empresa — analítica conversacional con contecintelligence (revisión 2026-11). | conectoresApi | completa |
| `ProfitabilityPage.tsx` | /profitability | ProfitabilityPage — rentabilidad por proyecto (/profitability). | profitabilityApi | completa |
| `ProjectDetailPage.tsx` | /projects/:id | Ficha de proyecto con pestañas (resumen, Gantt, sprints, hitos, RACI, UAT, riesgos). | projectsApi, plantillasApi | completa |
| `ProjectPermissionsPage.tsx` | /settings/project-permissions | ProjectPermissionsPage — permisos de acceso por proyecto (/project-permissions). | permissionsApi, projectsApi, usersApi | colisión `['users']` (M5) → ✅ arreglado 23-11-2026 |
| `ProjectTemplatesPage.tsx` | /settings/project-templates | Plantillas de proyecto: crear, editar e instanciar. | templatesApi | errores crudos (M2) → ✅ arreglado 23-11-2026 |
| `ProjectsDashboardPage.tsx` | /projects-dashboard | ProjectsDashboardPage — panel de proyectos (/projects-dashboard). | dashboardApi, analyticsApi, risksApi | completa |
| `ProjectsPage.tsx` | /projects | Lista y tablero de proyectos: alta, edición, miembros, fases y solicitudes. | projectsApi, settingsApi, usersApi, portalApi | completa |
| `PublicFormsPage.tsx` | /settings/public-forms | PublicFormsPage — Manage public ticket intake forms | projectsApi, formsApi | completa |
| `RACIPage.tsx` | /raci | RACIPage — Matriz de responsabilidades por proyecto (R/A/C/I) | projectsApi, usersApi, PUT /projects/${projectId}/raci, GET /projects/${selectedProject}/raci | completa |
| `RateCardsPage.tsx` | /settings/rates | RateCardsPage — tablas de tarifas por rol, departamento o cliente (/rate-cards). | rateCardsApi | completa |
| `ReportBuilderPage.tsx` | /report-builder | ReportBuilderPage — No-code parametric report builder | reportBuilderApi | borrado sin `onError` (M1) → ✅ arreglado 23-11-2026 |
| `ReportsPage.tsx` | /reports | ReportsPage — informes (/reports): métricas, explorador, plantillas, | analyticsApi, scheduledReportsApi, GET /users/me/preferences, PATCH /users/me/preferences | completa |
| `ResetPasswordPage.tsx` | /reset-password | Restablecer contraseña con el token del correo (pública). | authApi | mensaje del servidor sin traducir (M2) → ✅ arreglado 23-11-2026 |
| `ResourceForecastPage.tsx` | /resource-forecast | ResourceForecastPage — previsión de carga del equipo por semanas. | forecastApi | completa |
| `ResourceSchedulerPage.tsx` | /resource-scheduler | ResourceSchedulerPage — visual resource scheduler (Runn/Parallax-style) | projectsApi, GET /resource-forecast/weeks, GET /bookings, POST /bookings | Retroceso borra la reserva al escribir (M8); errores crudos (M2) → ✅ arreglado 23-11-2026 |
| `ResourcesPage.tsx` | /resources | Recursos: cuadrícula/lista de personas, carga, habilidades y edición. | burnoutRiskApi, settingsApi, usersApi, skillsApi | completa |
| `RevenuePage.tsx` | /revenue | RevenuePage — Reconocimiento de ingresos ASC 606 / IFRS 15 | revenueRecognitionApi, projectsApi | completa |
| `RiskScoresPage.tsx` | /risk-scores | RiskScoresPage — Predicción de riesgo por proyecto | predictionsApi, GET /risk-scores, GET /risk-scores/${selected}, GET /risk-scores?refresh=true | completa |
| `RisksPage.tsx` | /risks | RisksPage — registro y matriz de riesgos. | usersApi, risksApi, projectsApi | completa |
| `SLACalendarsPage.tsx` | /settings/sla-calendars | SLACalendarsPage — calendarios laborables y festivos para el cómputo de SLA. | slaCalendarsApi | completa |
| `ScenariosPage.tsx` | /scenarios | ScenariosPage — Scenario planning / What-if capacity | scenariosApi | completa |
| `SearchPage.tsx` | /search | SearchPage v23 — Búsqueda unificada (NQL + Full-text) | conectoresApi, projectsApi, tasksApi, clientsApi | completa |
| `SemanticEnginePage.tsx` | /semantic-engine | SemanticEnginePage — asignación de tareas y tickets con IA. | semanticApi, usersApi | completa |
| `ServiceDeskPage.tsx` | /service-desk | ServiceDeskPage — ITIL/ITSM completo | sdApprovalsApi | completa |
| `SettingsPage.tsx` | /settings, /settings/:seccion | Configuración: una sola entrada para toda la configuración del operador | — | completa |
| `SettingsPageSections.tsx` | secciones de /settings (general, users, roles, offices, depts, areas, numbering, custom-fields, alert-config, metrics, esign, session…) | Secciones de Configuración: usuarios, roles, sedes, departamentos, áreas, numeración, campos, alertas, métricas, firma y sesión. | settingsApi, usersApi, advancedConfigApi, organizationsApi | ROTA «Activar usuario» (A1); borrados sin confirmar (M4) → ✅ arreglado 23-11-2026 |
| `SkillsPage.tsx` | /skills | SkillsPage — habilidades del equipo: matriz, perfiles, búsqueda de personas | skillsApi, usersApi | completa |
| `SprintChartsPage.tsx` | /sprint-charts | SprintChartsPage — Burnup chart + Velocity trend per project | projectsApi, projectSprintsApi | completa |
| `SprintPlanningPage.tsx` | /sprint-planning | SprintPlanningPage — planes de sprint generados por IA, por proyecto. | tasksApi, semanticApi, sprintsApi, sprintPlansApi | errores crudos (M2); `['projects']` (M5) → ✅ arreglado 23-11-2026 |
| `SprintsPage.tsx` | /sprints | SprintsPage — Full Scrum sprint management | projectSprintsApi, projectsApi, tasksApi | completa |
| `SubcontractorsPage.tsx` | /subcontractors | SubcontractorsPage — subcontratistas, sus personas, asignaciones, horas y facturas. | skillsApi, enterpriseSubsApi, projectsApi, subcontractorsApi | completa |
| `SupportDashboardPage.tsx` | /support-dashboard | SupportDashboardPage — Panel de soporte (estado del soporte e ITSM). | — | completa |
| `TasksPage.tsx` | /tasks | TasksPage — tareas: tablero, lista y vistas del planificador. | tasksApi, projectWorkflowsApi, usersApi, issueTypesApi | errores crudos (M2); `['projects']` (M5) → ✅ arreglado 23-11-2026 |
| `TeamDashboardPage.tsx` | /team-dashboard | Panel del equipo: KPIs de carga, horas y tareas del equipo. | usersApi, analyticsApi, okrsApi, performanceApi | completa |
| `TimePage.tsx` | /time | Contenedor «Tiempo» con pestañas Imputar / Temporizador / Partes. | — | completa |
| `TimerPage.tsx` | /timer | Timer Page — Seguimiento de tiempo con cronómetro activo e historial | projectsApi, tasksApi, imputationsApi | errores crudos (M2); historial truncado (B4) → ✅ arreglado 23-11-2026 |
| `TimesheetsPage.tsx` | /timesheets | Partes de horas: los míos, pendientes de aprobar y del equipo; edición en línea. | timesheetsApi, imputationsApi | completa |
| `TrainingPage.tsx` | /training | TrainingPage — Formación y Certificaciones | trainingApi, usersApi | borrados sin `onError` (M1) → ✅ arreglado 23-11-2026 |
| `UATPage.tsx` | /uat | UATPage — Gestión de casos UAT (User Acceptance Testing) | projectsApi, tasksApi, uatApi | completa |
| `UserCostsPage.tsx` | /settings/user-costs | UserCostsPage — admin/HR view to manage employer cost calculations. | userCostsApi, usersApi | completa |
| `WebhookLogPage.tsx` | /settings/webhook-log | WebhookLogPage — Log de eventos webhook salientes | enterpriseApi | completa |
| `WikiPage.tsx` | /wiki | Wiki por espacios: páginas en bloques, edición colaborativa, versiones, etiquetas y mejora con IA. | wikiApi, projectsApi, POST /ai/chat | prompt de IA en castellano fijo (M7) → ✅ arreglado 23-11-2026 |
| `WorkDashboardPage.tsx` | /work-dashboard | «Mi trabajo»: tareas abiertas, horas de la semana, aprobaciones y métricas personales. | tasksApi, analyticsApi, approvalsApi, expensesApi | completa |
| `WorkflowsPage.tsx` | /settings/project-workflows | WorkflowsPage — flujos de estado de las tareas de cada proyecto. | projectWorkflowsApi, projectsApi | completa |
| `alm/ActasTab.tsx` | dentro de ALMPage.tsx | Actas de entrega y devolución (fase 1): las pendientes de firma y el resto, con PDF y fotos. */ | almApi | completa |
| `alm/AsignacionesTab.tsx` | dentro de ALMPage.tsx | Asignaciones y préstamos (licencias y hardware, fase 1): quién tiene qué ahora | almApi | completa |
| `alm/ConciliacionTab.tsx` | dentro de ALMPage.tsx | Conciliación contrato ↔ factura de proveedor ↔ gasto (fase 3). | almExtApi, vendorsApi, almApi | módulo i18n `gastos` inexistente (B2) → ✅ arreglado 23-11-2026 |
| `alm/CostesTab.tsx` | dentro de ALMPage.tsx | Costes de licencias y equipos (fase 3): coste por titular y día del periodo, | almApi | completa |
| `alm/RenovacionesTab.tsx` | dentro de ALMPage.tsx | Renovaciones (fase 3): contratos y licencias que renuevan, con la fecha | almApi | completa |
| `alm/uso/AjustePanel.tsx` | dentro de alm/uso/UsoRealTab.tsx | Ajuste de nivel: propuestas de bajar de licencia con su ahorro y las reglas que las generan. */ | licensesApi, almUsoApi | completa |
| `alm/uso/CumplimientoPanel.tsx` | dentro de alm/uso/UsoRealTab.tsx | Cumplimiento real: derechos frente a consumo por licencia, con exportación para la auditoría del fabricante. * | almUsoApi | completa |
| `alm/uso/FuentesPanel.tsx` | dentro de alm/uso/UsoRealTab.tsx | Conexiones de fuentes de uso: credenciales, prueba, sincronización, registro y mapeo de productos. */ | almUsoApi, licensesApi | configuración dentro del módulo (A4) → ✅ arreglado 23-11-2026 |
| `alm/uso/NoControladoPanel.tsx` | dentro de alm/uso/UsoRealTab.tsx | Software no controlado: candidatos vistos en gastos, accesos SSO o inventario que no están en ALM. */ | almUsoApi | completa |
| `alm/uso/RecuperacionPanel.tsx` | dentro de alm/uso/UsoRealTab.tsx | Recuperación de licencias sin uso: procesos en curso, decisiones y simulador de la política actual. */ | almUsoApi | completa |
| `alm/uso/UsoPanel.tsx` | dentro de alm/uso/UsoRealTab.tsx | Uso real: KPIs, uso por licencia (con el detalle de cada asignación) y uso de los equipos. */ | almUsoApi | completa |
| `alm/uso/UsoRealTab.tsx` | dentro de ALMPage.tsx | Licencias y hardware — fase 2: uso real (16-11-2026). | almUsoApi | pestaña «Fuentes» de configuración (A4) → ✅ arreglado 23-11-2026 |
| `alm/uso/comun.tsx` | dentro de alm/uso/* | Piezas comunes de las pantallas de uso real de licencias (fase 2, 16-11-2026): | — | completa |
| `bpm/BpmRunPanel.tsx` | dentro de BPMPage.tsx, InboxPage.tsx | Ejecución de procesos BPMN: bandeja de pasos humanos e instancias. | bpmnInstancesApi | completa |
| `bpm/BpmVersionsModal.tsx` | dentro de BPMPage.tsx | Versiones de un proceso BPM: cuál se ejecuta, publicar otra y abrirla. | bpmnProcessesApi | completa |
| `bpm/catalogo/estructura.ts` | dentro de bpm/catalogo/index.ts | Estructura del catálogo de procesos BPM: lo que NO depende del idioma (ids, | — | completa |
| `bpm/catalogo/estructuraLineal.ts` | dentro de bpm/catalogo/index.ts | Procesos del catálogo que son una cadena lineal de pasos (los que el backend | — | completa |
| `bpm/catalogo/index.ts` | dentro de BPMPage.tsx (catálogo de procesos) | Catálogo de procesos BPM del sistema. Estructura (ids, orden, SLA numérico, | — | completa |
| `bpm/catalogo/textos/en.ts` | dentro de bpm/catalogo/index.ts | BPM process catalogue texts — en. Same shape as es.ts (see ../tipos.ts). | — | completa |
| `bpm/catalogo/textos/es.ts` | dentro de bpm/catalogo/index.ts | Textos del catálogo de procesos BPM — es. Misma forma que es.ts (ver tipos.ts). | — | completa |
| `bpm/catalogo/textos/zh.ts` | dentro de bpm/catalogo/index.ts | BPM 流程目录文本 — zh。结构与 es.ts 相同（见 ../tipos.ts）。 | — | completa |
| `bpm/catalogo/textosLineales/en.ts` | dentro de bpm/catalogo/index.ts | Textos de los procesos lineales del catálogo BPM — en. Misma forma en los tres | — | completa |
| `bpm/catalogo/textosLineales/es.ts` | dentro de bpm/catalogo/index.ts | Textos de los procesos lineales del catálogo BPM — es. Misma forma en los tres | — | completa |
| `bpm/catalogo/textosLineales/zh.ts` | dentro de bpm/catalogo/index.ts | Textos de los procesos lineales del catálogo BPM — zh. Misma forma en los tres | — | completa |
| `bpm/catalogo/tipos.ts` | dentro de bpm/catalogo/* | Tipos del catálogo de procesos BPM (estructura sin idioma + textos por idioma). | — | completa |
| `bpm/generadorBpmn.ts` | dentro de bpm/catalogo/index.ts, BPMPage.tsx | Generador de XML BPMN (layout por columnas/filas). Sin textos: los nombres llegan ya traducidos. | — | completa |
| `bpm/textos.ts` | dentro de bpm/BpmRunPanel.tsx, bpm/BpmVersionsModal.tsx | Textos de BPM construidos con códigos del backend (`app/services/bpmn_engine.py`). | — | completa |
| `clients/CamposInternos.tsx` | dentro de ClientsPage.tsx | Ficha del cliente (22-11-2026, clientes internos): campo «Tipo» y, si es | — | completa |
| `clients/ClientsPageTabs.tsx` | dentro de ClientsPage.tsx | Pestañas de la ficha de cliente: proyectos, contactos, licencias, contratos, portal (config, UAT, solicitudes, mensajes, documentos), facturas. | clientExtApi, clientsApi, licensesApi, contractsApi | fuga de WebSocket (A2); `test_environment` sin sanear (A3); desvincular sin confirmar (M4) → ✅ arreglado 23-11-2026 |
| `clients/ModalEditarContacto.tsx` | dentro de clients/ClientsPageTabs.tsx, ClientsPage.tsx | Edición de un contacto (persona) del cliente. La abren la pestaña Contactos | clientExtApi | completa |
| `clients/PortalUsersTab.tsx` | dentro de clients/ClientsPageTabs.tsx | Usuarios del portal de un cliente: alta con contraseña, permisos, activar/pausar, cambiar contraseña. | portalClientsApi, clientsApi | contraseña del cliente en claro y al portapapeles (M10) → ✅ arreglado 23-11-2026 |
| `clients/SelectorContactoPrincipal.tsx` | dentro de ClientsPage.tsx | Sección «Contacto principal» del alta/edición de cliente. El contacto es una | — | completa |
| `clients/contactosCliente.ts` | dentro de clients/ClientsPageTabs.tsx, clients/ModalEditarContacto.tsx | Piezas comunes de los contactos (personas) de un cliente: la ficha, la | — | completa |
| `internos/BeneficiosDeProyecto.tsx` | dentro de internos/ClientesInternosPage.tsx, internos/SeccionesDelPortal.tsx | Clientes internos (22-11-2026): caso de negocio y beneficios de un proyecto | clientesInternosApi, projectsApi | completa |
| `internos/ClientesInternosPage.tsx` | /internal-clients | Clientes internos (`/internal-clients`, capacidad `interno.gestionar`, 22-11-2026). | clientesInternosApi | completa |
| `internos/ConfigClientesInternos.tsx` | /settings/clientes-internos | Configuración → Finanzas → Clientes internos (22-11-2026, capacidad `interno.cargos`). | clientsApi, clientesInternosApi, settingsApi | moneda `EUR` fija (hardcode) → ✅ arreglado 23-11-2026 |
| `internos/CuadroDeDireccion.tsx` | dentro de internos/ClientesInternosPage.tsx | Clientes internos (22-11-2026): cuadro de dirección (`GET /internal-clients/overview?year=`). | clientesInternosApi | completa |
| `internos/FichaDeUnidad.tsx` | dentro de internos/ClientesInternosPage.tsx, internos/SeccionesDelPortal.tsx | Clientes internos (22-11-2026): ficha de gestión de una unidad interna. | clientesInternosApi | completa |
| `internos/MiDepartamentoPage.tsx` | /mi-departamento | Portal interno «Mi departamento» (`/mi-departamento`, capacidad `interno.portal`, 22-11-2026). | portalInternoApi | completa |
| `internos/PestanaCargos.tsx` | dentro de internos/ClientesInternosPage.tsx | Clientes internos (22-11-2026): cargos internos (chargeback/showback). | clientesInternosApi | completa |
| `internos/SeccionesDelPortal.tsx` | dentro de internos/MiDepartamentoPage.tsx | Portal interno (`/mi-departamento`, 22-11-2026): secciones de una unidad. | portalInternoApi | completa |
| `internos/comunes.tsx` | dentro de internos/* | Clientes internos (22-11-2026): piezas de pantalla compartidas por la | clientesInternosApi | completa |
| `internos/logica.ts` | dentro de internos/* | Clientes internos (22-11-2026): lógica pura compartida por la gestión | — | completa |
| `portal-client/CampanaDelPortal.tsx` | dentro de portal-client/PortalNotificaciones.tsx, portal-client/PortalSupportDesk.tsx | CampanaDelPortal — campana de avisos de la cabecera del portal de clientes. | portalAvisosApi, GET /portal/collaboration/notifications/unread-count, GET /portal/collaboration/notifications, POST /portal/collaboration/notifications/${id}/read | completa |
| `portal-client/PortalAIChatWidget.tsx` | dentro de PortalClientePage.tsx | PortalAIChatWidget — Item I26 (UI del Client Portal AI Chat). | GET /portal/ai-chat/${sessionId}/messages, POST /portal/ai-chat, POST /portal/ai-chat/messages/${id}/feedback | completa |
| `portal-client/PortalAdvancedSections.tsx` | dentro de PortalClientePage.tsx | PortalAdvancedSections — todas las páginas internas del portal cliente | GET /portal/uat, POST /portal/uat/${sessionId}/submit-result, POST /portal/uat/${selected?.id}/issues, GET /portal/demand/types | `test_environment` sin sanear en el portal externo (A3) → ✅ arreglado 23-11-2026 |
| `portal-client/PortalAsistenteYChat.tsx` | dentro de portal-client/PortalSupportDesk.tsx | PortalAsistenteYChat — en el portal de clientes (mejoras de mercado 16-11-2026): | POST /sd/portal-assistant/intent, POST /sd/portal-assistant/actions/${accion.id}/confirm, POST /sd/portal-assistant/actions/${accion.id}/cancel, POST /sd/channels/livechat | completa |
| `portal-client/PortalDashboard.tsx` | dentro de PortalClientePage.tsx | PortalDashboard – pizarra del cliente totalmente rediseñada. | GET /portal/dashboard, GET /portal/project, GET /portal/invoices, GET /sd/tickets/client/my | completa |
| `portal-client/PortalDemandas.tsx` | dentro de portal-client/PortalAdvancedSections.tsx | PortalDemandas — «Demandas» del portal de clientes (22-11-2026). | POST /portal/demand/requests, PATCH /portal/demand/requests/${d.id}, GET /portal/demand/requests/${id}, POST /portal/demand/requests/${id}/submit | completa |
| `portal-client/PortalKbArticulo.tsx` | dentro de portal-client/PortalAdvancedSections.tsx, portal-client/PortalSupportDesk.tsx | Lectura de un artículo de la base de conocimiento en el portal (revisión 2026-11). | GET /sd/kb/${id}, POST /sd/kb/${id}/helpful | voto sin `onError` (M1) → ✅ arreglado 23-11-2026 |
| `portal-client/PortalNotificaciones.tsx` | dentro de PortalClientePage.tsx | PortalNotificaciones — todos los avisos del cliente («Ver todas» de la | portalAvisosApi | completa |
| `portal-client/PortalQuickCreateMenu.tsx` | dentro de portal-client/PortalUI.tsx | PortalQuickCreateMenu — réplica del QuickCreateMenu del backoffice. | — | completa |
| `portal-client/PortalSupportDesk.tsx` | dentro de PortalClientePage.tsx | PortalSupportDesk — service desk del cliente con el lenguaje del backoffice. | GET /sd/tickets/client/my, GET /sd/catalog, GET /sd/kb, GET /sd/announcements | completa |
| `portal-client/PortalSurveys.tsx` | dentro de PortalClientePage.tsx | PortalSurveys — encuestas de satisfacción del portal cliente. | GET /portal/surveys, POST /portal/surveys/${id}/respond | completa |
| `portal-client/PortalUI.tsx` | dentro de portal-client/* | Kit visual del portal: shell, navegación, tarjetas, KPIs, botones, campos, modales y gráficos. | — | completa |
| `portal-client/TraduccionAutomatica.tsx` | dentro de portal-client/PortalAdvancedSections.tsx, portal-client/PortalDashboard.tsx | Marca «Traducido automáticamente» del portal de clientes (16-11-2026). | — | completa |
| `portal-client/portalClientContext.tsx` | dentro de PortalClientePage y todo portal-client/* | Contexto del portal: sesión por cookie, cliente API, idioma, textos, login y aviso de inactividad. | GET /portal/branding, GET /portal/auth/me, POST /portal/auth/login, POST /portal/auth/logout | completa |
| `portal-client/usePortalEnVivo.ts` | dentro de portal-client/PortalAsistenteYChat.tsx, PortalClientePage.tsx | usePortalEnVivo — el WebSocket del portal (`/ws/portal-notifications`), | GET /ws/portal-ticket | completa |
| `profitability/EvolucionDelMargen.tsx` | dentro de ProfitabilityPage.tsx | EvolucionDelMargen — ingreso, coste y margen por tramo en Rentabilidad | — | completa |
| `proveedores/AltaDeProveedor.tsx` | dentro de proveedores/ClasificacionModal.tsx, proveedores/FormulariosDeContrato.tsx | Alta de proveedor con elección de tipo (19-11-2026, migración 189). | proveedoresApi, subcontractorsApi | completa |
| `proveedores/ClasificacionModal.tsx` | dentro de proveedores/PestanaResumen.tsx | Editar la clasificación de un proveedor (19-11-2026): tipo, modos, responsable | vendorsApi, proveedoresApi | completa |
| `proveedores/ConfigProveedores.tsx` | /settings/proveedores | Configuración → Finanzas → Proveedores (19-11-2026, migración 189). | proveedoresApi, settingsApi | completa |
| `proveedores/ContactosDelPortal.tsx` | dentro de proveedores/PestanaCumplimiento.tsx | Ficha del proveedor → Cumplimiento → Portal del proveedor (migración 191). | proveedoresApi | completa |
| `proveedores/FormulariosDeContrato.tsx` | dentro de proveedores/ConfigProveedores.tsx, proveedores/PestanaContratos.tsx | Contratos y líneas de precio de proveedor (19-11-2026). Los usan la ficha | proveedoresApi | quitar línea de precio sin confirmar (M4) → ✅ arreglado 23-11-2026 |
| `proveedores/PestanaConsumo.tsx` | dentro de SubcontractorsPage.tsx | Ficha del proveedor → Consumo y facturación (19-11-2026), la parte nueva: | proveedoresApi | completa |
| `proveedores/PestanaContratos.tsx` | dentro de SubcontractorsPage.tsx | Ficha del proveedor → Contratos y precios (19-11-2026). | proveedoresApi | completa |
| `proveedores/PestanaCumplimiento.tsx` | dentro de SubcontractorsPage.tsx | Ficha del proveedor → Cumplimiento (GRC de terceros, 19-11-2026). | proveedoresApi, enterpriseSubsApi | completa |
| `proveedores/PestanaPaquetes.tsx` | dentro de proveedores/PestanaServicios.tsx, proveedores/PortalDelProveedor.tsx | Ficha del proveedor → Paquetes de trabajo (outsourcing, 19-11-2026). | proveedoresApi, projectsApi, milestonesApi, deliverablesApi | completa |
| `proveedores/PestanaRendimiento.tsx` | dentro de SubcontractorsPage.tsx | Ficha del proveedor → Rendimiento (19-11-2026): cuadro de mando del periodo. | proveedoresApi | completa |
| `proveedores/PestanaResumen.tsx` | dentro de SubcontractorsPage.tsx | Ficha del proveedor → Resumen (19-11-2026): perfil, contadores, cumplimiento, | proveedoresApi | completa |
| `proveedores/PestanaServicios.tsx` | dentro de SubcontractorsPage.tsx | Ficha del proveedor → Servicios gestionados (19-11-2026). | proveedoresApi, sdGroupsApi | completa |
| `proveedores/PestanaSolicitudes.tsx` | dentro de DemandaPage.tsx, proveedores/PortalDelProveedor.tsx | Portal del proveedor: sus solicitudes del flujo de demanda (migración 195, | — | completa |
| `proveedores/PortalDelProveedor.tsx` | /supplier-portal | Portal del proveedor (`/supplier-portal`, migración 191). | portalProveedorApi | completa |
| `proveedores/comunes.tsx` | dentro de proveedores/*, SubcontractorsPage | Proveedores (19-11-2026): piezas compartidas por la lista, la ficha y Configuración. | proveedoresApi, projectsApi | completa |
| `proveedores/logica.ts` | dentro de proveedores/*, SubcontractorsPage | Proveedores y externalización (19-11-2026): reglas de pantalla sin React. | — | completa |
| `service-desk/CambiosPlanificacion.tsx` | dentro de service-desk/ChangeManagementTab.tsx | Planificación de cambios: calendario (con choques y congelaciones), | sdChangePlanningApi | borrados sin `onError` (M1) → ✅ arreglado 23-11-2026 |
| `service-desk/ChangeManagementTab.tsx` | dentro de ServiceDeskPage.tsx | Gestión de cambios del service desk (pestaña «Cambios»). | changesApi, cmdbApi, sdChangePlanningApi | completa |
| `service-desk/ConfigCanales.tsx` | dentro de service-desk/ConfigTab.tsx | ConfigCanales — qué canales tiene la empresa y qué dirección configurar en | — | completa |
| `service-desk/ConfigCorreoEntrante.tsx` | dentro de service-desk/ConfigTab.tsx | Canal de correo entrante: buzón, pasarela y lo último que ha entrado. | sdInboundApi | enlace con recarga (M6) → ✅ arreglado 23-11-2026 |
| `service-desk/ConfigEscaladoYAvisos.tsx` | dentro de service-desk/ConfigTab.tsx | Configuración del Service Desk: reglas de escalado y textos de los avisos. | sdEscalationApi, sdGroupsApi, usersApi, sdNotificationTemplatesApi | completa |
| `service-desk/ConfigGuardiasYMonitor.tsx` | dentro de service-desk/ConfigTab.tsx | Guardias (quién atiende fuera de horas, por cola) y entrada de alertas de | sdOnCallApi, sdGroupsApi, usersApi, sdMonitoringApi | enlace con recarga (M6); quitar turno sin confirmar (M4) → ✅ arreglado 23-11-2026 |
| `service-desk/ConfigPaginaDeEstado.tsx` | dentro de service-desk/ConfigTab.tsx | Página de estado pública: componentes, su estado y los incidentes que ven | sdStatusPageApi | completa |
| `service-desk/ConfigSlaYCiclos.tsx` | dentro de service-desk/ConfigTab.tsx | ConfigSlaYCiclos — SLA condicionales, OLA por prioridad y ciclos de vida por | sdCatalogApi, clientsApi, contractsApi, sdSlaPoliciesApi | completa |
| `service-desk/ConfigTab.tsx` | /settings/sd | Configuración del Service Desk: catálogo, colas, grupos, SLA, canales, escalado, guardias, página de estado, avisos. | sdCatalogApi, usersApi, approvalsApi, sdGroupsApi | errores crudos (M2); quitar miembro sin confirmar (M4) → ✅ arreglado 23-11-2026 |
| `service-desk/CreateTicketModal.tsx` | dentro de ServiceDeskPage.tsx | CreateTicketModal — alta de un ticket. | clientsApi, sdCatalogApi, usersApi, sdDynamicFormsApi | completa |
| `service-desk/ITSMKnowledgeTab.tsx` | dentro de ServiceDeskPage.tsx | Problemas, errores conocidos y base de conocimiento del service desk. | sdKbApi, problemsApi | errores crudos (M2) → ✅ arreglado 23-11-2026 |
| `service-desk/KanbanTicketsTab.tsx` | dentro de ServiceDeskPage.tsx | KanbanTicketsTab — tablero de tickets por estado (arrastrar y soltar). | ticketsApi | errores crudos (M2) → ✅ arreglado 23-11-2026 |
| `service-desk/MetricsDashboardTab.tsx` | dentro de SupportDashboardPage.tsx | MetricsDashboardTab — métricas ITIL del service desk (se muestra en | sdMetricsApi | completa |
| `service-desk/QueueAndRoutingSections.tsx` | dentro de service-desk/ConfigTab.tsx, ServiceDeskPage.tsx | QueueAndRoutingSections — lista de tickets («Mi cola» y «Todos»), incidentes | ticketsApi, sdRoutingApi, sdGroupsApi, usersApi | completa |
| `service-desk/TicketDetail.tsx` | dentro de ServiceDeskPage.tsx | TicketDetail — ficha del ticket (panel lateral del Service Desk). | sdCannedApi, ticketsApi, usersApi, almExtApi | fusionar sin confirmar (M4); enlaces con recarga (M6) → ✅ arreglado 23-11-2026 |
| `service-desk/WorkflowDesignerPage.tsx` | /sd/workflow-designer | WorkflowDesignerPage — diseñador visual de workflows para Service Desk. | sdWorkflowDesignerApi | cancelar ejecución sin `onError` (M1); errores crudos (M2) → ✅ arreglado 23-11-2026 |
| `service-desk/sdUtils.tsx` | dentro de service-desk/* y components/servicedesk/* | Shared constants, styles, and tiny presentational components | — | completa |
| `settings-sections/MarcaSection.tsx` | /settings/branding | Marca de la empresa en los documentos (revisión 2026-11). | settingsApi | completa |
| `settings-sections/PuestaEnMarchaSection.tsx` | /settings/setup | Puesta en marcha de la empresa (revisión 2026-11, lo que contecmind tenía). | settingsApi | completa |
| `settings-sections/SeccionDeAjustes.tsx` | dentro de internos/ConfigClientesInternos.tsx, proveedores/ConfigProveedores.tsx | Bloque de una pantalla de Ajustes: tarjeta con icono, titulo y descripcion. | — | completa |
| `settings-sections/SettingsAdvancedSections.tsx` | /settings/idiomas, /settings/integrations, /settings/runtime-flags, /settings/log-level, /settings/system-state | Secciones avanzadas de /settings (idiomas, registro, estado del sistema, | portalClientsApi, settingsApi, ajustesGeneralesApi | completa |
| `settings-sections/TraduccionSection.tsx` | /settings/traduccion | TraduccionSection — administración de la traducción en tiempo real operador ↔ cliente | aiProvidersApi, settingsApi, traduccionApi | completa |
| `settings/CamposPersonalizados.tsx` | /settings/custom-fields | Configuración → Proyectos y trabajo → Campos personalizados (18-11-2026). | — | completa |
| `settings/CatalogosDeClave.tsx` | /settings/catalogos | Configuración → Catálogos (19-11-2026): tipos de proyecto, sectores de | catalogosApi | borrado sin confirmar (M4) → ✅ arreglado 23-11-2026 |
| `settings/catalogoDeAjustes.tsx` | lo usan App.tsx y SettingsPage.tsx | Catálogo único de secciones de Configuración, grupos, capacidades e ids antiguos. | — | completa |

## Hallazgos por severidad

Formato: **fichero:línea**, evidencia, impacto y arreglo.

### Crítica

Ninguna nueva.

### Alta

**A1. `frontend/src/pages/SettingsPageSections.tsx:306` — «Activar» llama a desactivar**
- **Estado:** ✅ arreglado 23-11-2026: `POST /users/{id}/reactivate` (`requiere_capacidad("org.administrar")`, misma empresa y ABAC, cupo del plan, `audit_log`) y `usersApi.reactivate`; el botón «Activar» confirma y usa esa vía. No relanza la baja de ALM ni reasigna licencias/equipos.
- **Evidencia:** para un usuario inactivo se pinta `<Pulsable onClick={() => deactivate(u.id)}>{t('settings_sections.activar')}</Pulsable>`. `deactivate` (línea 224) es `usersApi.deactivate`, que hace `api.delete('/users/{id}')` (`services/api/users.ts:206-207`). En el backend, ese endpoint (`app/api/v1/endpoints/users.py:236-252`) llama a `deactivate_user_record`, que pone `is_active=False` y ejecuta `alm_personas.al_desactivar(...)` (`app/services/user_service.py:817-827`). `UserUpdate` no tiene `is_active` (`app/schemas/users.py:35-55`), así que no hay otra vía en pantalla.
- **Impacto:**
  - No se puede reactivar a nadie desde Configuración → Usuarios.
  - Cada clic en «Activar» relanza la baja de ALM: liberación de licencias y devolución de equipos.
  - Sin verificar si `al_dar_de_baja` es idempotente. Si no lo es, se duplican procesos de baja.
- **Arreglo:** crear `POST /users/{id}/reactivate` o admitir `is_active` en `UserUpdate` con auditoría, y usar `usersApi.reactivate` en ese botón. Con riesgo de ALM, pedir confirmación.

**A2. `frontend/src/pages/clients/ClientsPageTabs.tsx:634-659` — WebSocket que no se cierra**
- **Estado:** ✅ arreglado 23-11-2026: bandera `cerrado`, `ws.onclose = null` antes de `close()`, sin abrir sockets tras desmontar y reintento acotado del ticket.
- **Evidencia:** `ws.onclose = () => { reconnectTimer = setTimeout(connectWS, WS_RECONNECT_DELAY_MS) }` y la limpieza `return () => { if (ws) ws.close(); clearTimeout(reconnectTimer) }`.
  - `close()` dispara `onclose` de forma asíncrona, después del `clearTimeout`. Se programa una reconexión que nadie cancela, y el socket nuevo tampoco se cierra.
  - Si la limpieza llega antes de que `wsApi.ticket()` responda, `ws` es `undefined` y el socket se crea después de desmontar.
  - `wsApi.ticket()` no tiene `.catch`.
  - Dependencias: `[cid, loading, qc, toast, user, traducir]`. Cada cambio de cliente o de idioma deja otro socket vivo.
- **Impacto:** conexiones `/ws/notifications` acumuladas en el navegador y en el servidor. Llegan toasts «cr_cambio_estado» duplicados y de clientes que ya no se miran, e invalidan `['portal-frs-client', cidViejo]`. Además, el rechazo sin capturar del ticket corta la reconexión.
- **Arreglo:** usar una bandera `cerrado = true` en la limpieza y comprobarla en `onclose` y tras el `ticket()`. Poner `ws.onclose = null` antes de `close()`. Añadir `.catch` con reintento acotado. Mejor aún, usar el hook común de avisos en vivo, si existe (sin verificar).

**A3. `frontend/src/pages/portal-client/PortalAdvancedSections.tsx:302` y `clients/ClientsPageTabs.tsx:607` — `test_environment` sin sanear**
- **Estado:** ✅ arreglado 23-11-2026: validación http(s) en backend (`EnlaceSeguro`) y enlace solo si es http(s) (si no, texto) en portal y ficha.
- **Evidencia:** `<a href={selected.test_environment} target="_blank">` (portal externo) y `<a href={s.test_environment} …>` (ficha interna). En el backend: `test_environment: Optional[str] = Field(None, max_length=200)` (`app/api/v1/endpoints/client_portal.py:139`), sin validar el esquema, en la columna `client_portal.py:175` («URL/env where to test»).
- **Impacto:** un valor `javascript:` o `data:` guardado por un operador llega como enlace al usuario del cliente. Es el mismo vector almacenado que el A6 del 04 (`file_url`), en otro campo que el A6 no listaba.
- **Arreglo:** validar `http(s)` en el esquema del backend y envolver en `sanitizeUrl` (`utils/security.ts`) los dos `href`.

**A4. `frontend/src/pages/alm/uso/UsoRealTab.tsx:73` + `alm/uso/FuentesPanel.tsx:25-50,214-215` — configuración dentro del módulo**
- **Estado:** ✅ arreglado 23-11-2026: pestaña «Fuentes» retirada de ALM → Uso real; sección `/settings/alm-fuentes` (Integraciones, `org.administrar`); en ALM solo el aviso «sin fuentes» con botón para administración.
- **Evidencia:** la pestaña `fuentes` (solo `org.administrar`) muestra un `<Button icon={<Settings2/>}>{t('alm_uso.configurar')}</Button>` por fuente. Abre un modal `Configurar` con credenciales (`creds`), fiabilidad y opciones (`almUsoApi.guardarConexion`), además de activar o desactivar, probar y sincronizar.
- **Impacto:** incumple la regla «sin botón Configurar en módulos; la configuración va en `/settings/:seccion`». Es más grave que el A7 del 04 porque aquí se editan secretos dentro del módulo.
- **Arreglo:** mover «Fuentes de uso» a una sección `/settings/alm-fuentes` del grupo Integraciones con capacidad `org.administrar`. En ALM queda solo el estado de sincronización y un aviso contextual con `<Link>` condicionado a `puede`.

### Media

**M1. Mutaciones sin `onError` (fallan en silencio)**
- **Estado:** ✅ arreglado 23-11-2026: `MutationCache.onError` global en `main.tsx`: toda mutación sin `onError` propio avisa traducido.
- **Evidencia:** no hay `onError` global de mutaciones (`main.tsx:148-150`). Casos:
  - `TrainingPage.tsx:183,187` (borrar curso y certificación).
  - `ReportBuilderPage.tsx:448` (borrar plantilla).
  - `service-desk/CambiosPlanificacion.tsx:128,196` (borrar congelación y versión).
  - `service-desk/WorkflowDesignerPage.tsx:692` (cancelar ejecución).
  - `NotificationsPage.tsx:240,245` (marcar leída y marcar todas).
  - `NPSPage.tsx:174` (recalcular salud).
  - `portal-client/PortalKbArticulo.tsx:28` (voto «útil»).
- **Impacto:** tras confirmar un borrado, si el servidor responde 403 o 409 no pasa nada visible. El usuario cree que se ha hecho.
- **Arreglo:** añadir `onError: e => toast.error(extractErr(e))`, o poner un `MutationCache({ onError })` global como el de consultas.

**M2. Errores del servidor pintados sin `extractErr` (~35 sitios)**
- **Estado:** ✅ arreglado 23-11-2026: todos los sitios citados pasan por `extractErr` (y otros encontrados en los mismos ficheros).
- **Evidencia:** `toast.error(e?.response?.data?.detail || …)` en:
  - `TimerPage.tsx:231,236,241,251,268` y `ResourceSchedulerPage.tsx:298,304,310`.
  - `TasksPage.tsx:941,1643` e `ImputarPage.tsx:301`.
  - `InvoicesPage.tsx:91` y `ProjectTemplatesPage.tsx:133,344`.
  - `SprintPlanningPage.tsx:76` y `GanttPage.tsx:168,182`.
  - `service-desk/ConfigTab.tsx:964,969,974`, `ITSMKnowledgeTab.tsx:187`, `KanbanTicketsTab.tsx:87` y `WorkflowDesignerPage.tsx:186,196,365,690,866`.
  - Con `String(detail)`: `ImportPage.tsx:70,91` e `IntakeFormPage.tsx:35`.
  - Mensajes del servidor tal cual: `MilestoneBillingPage.tsx:103-106` (`data.message`), `ResetPasswordPage.tsx:56` y `PerformanceReviewsPage.tsx:374` (`reason_blocked`).
- **Impacto:**
  - `extractErr` (`utils/helpers.ts:194-214`) traduce los códigos `err_srv.*` y resume los 422. Al saltárselo, en/zh reciben el texto del backend en castellano.
  - Con un 422 de Pydantic (`detail` es un array), el toast recibe un array de objetos. React no puede pintar objetos como hijos: según la implementación del toast, falla el render o sale `[object Object]` (sin verificar cuál de las dos).
- **Arreglo:** usar siempre `extractErr(e, t('…'))` y `resumenDeValidacion` en los formularios.

**M3. `frontend/src/pages/IntakeFormPage.tsx:57-66,32-36` — el formulario público falla sin correo**
- **Estado:** ✅ arreglado 23-11-2026: solo se envían las claves con valor; error con `extractErr`; inputs del kit.
- **Evidencia:** el estado inicial envía `submitter_email: ''`. El backend declara `submitter_email: Optional[EmailStr] = None` (`app/api/v1/endpoints/public_forms.py:69`). Pydantic rechaza la cadena vacía como correo y responde 422. El error se pinta con `String(detail)`, que sobre la lista de errores da `[object Object]`.
- **Impacto:** quien deja el correo vacío (el campo no está marcado como obligatorio) no puede abrir el ticket y no entiende el motivo. El canal público de intake se rompe en el caso más común.
- **Arreglo:** no enviar las claves vacías (`submitter_email: v || undefined`) o marcar el campo como obligatorio, y pintar el error con `extractErr`/`resumenDeValidacion`.

**M4. Borrados sin confirmación (más casos del M4 del 04)**
- **Estado:** ✅ arreglado 23-11-2026: confirmación en todos los citados (rol, campo, sede, departamento, área, catálogo, línea de precio, miembro de grupo, turno de guardia, desvincular proyecto/licencia/contrato, fusionar tickets) y además altas para el reseteo de formularios (B5).
- **Evidencia:**
  - `SettingsPageSections.tsx`: rol (502), campo personalizado (895), sede (982), departamento (1051) y área (1098).
  - `settings/CatalogosDeClave.tsx:78` (valor de catálogo).
  - `proveedores/FormulariosDeContrato.tsx:311` (línea de precio del contrato).
  - `service-desk/ConfigTab.tsx:748` (quitar miembro de un grupo).
  - `service-desk/ConfigGuardiasYMonitor.tsx:83` (quitar turno de guardia).
  - `clients/ClientsPageTabs.tsx:421,495` (desvincular proyecto o contrato).
  - `service-desk/TicketDetail.tsx:935` (fusionar tickets, irreversible).
- **Impacto:** se borran datos de referencia con un clic. Un rol o un departamento borrado puede dejar personas sin asignar (sin verificar el `ON DELETE` del backend).
- **Arreglo:** usar `openConfirmGlobal({ danger: true })`, como en `AlertConfigSection` (`SettingsPageSections.tsx:670`).

**M5. Colisiones de `queryKey` (amplía el A8 del 04)**
- **Estado:** ✅ arreglado 23-11-2026: `useListaDeProyectos`/`useListaDeUsuarios` con params en la clave en todos los citados.
- **`['projects']`:** además de los 16 sitios del A8, aparece en `ImputarPage.tsx:225`, `InvoicesPage.tsx:111`, `IssueTypesPage.tsx:154`, `PlanificacionDeRecursosPage.tsx:37`, `ProjectPermissionsPage.tsx:171`, `RACIPage.tsx:184`, `ResourceSchedulerPage.tsx:267`, `RevenuePage.tsx:232`, `SprintPlanningPage.tsx:217`, `SubcontractorsPage.tsx:391` (lee `.items`), `TasksPage.tsx:1066` y `UATPage.tsx:198`. `CapacityPage:123` guarda en esa clave una lista **filtrada por estado**, y Facturas, Ingresos, UAT o RACI pueden recibirla.
- **`['users']`:** `ProjectPermissionsPage.tsx:177` pide `page_size: FULL_LIST_SIZE`, mientras que `GrcPage.tsx:1024`, `OrganizationsPage.tsx:139`, `SemanticEnginePage.tsx:230`, `ConfigEscaladoYAvisos.tsx:68`, `ConfigGuardiasYMonitor.tsx:45` y `QueueAndRoutingSections.tsx:368,496` usan el tamaño por defecto.
- **Impacto:** quien abra primero llena la caché, y los permisos por proyecto pueden mostrar una lista de personas truncada (o al revés).
- **Arreglo:** incluir los parámetros en la clave (`['users', { page_size }]`) y usar un hook único `useUsuarios()`/`useProyectos()`.

**M6. Navegación interna con recarga completa (mismo patrón que el M7 del 04)**
- **Estado:** ✅ arreglado 23-11-2026: `<Link>` en Git, GRC, ConfigCorreoEntrante, ConfigGuardiasYMonitor y TicketDetail.
- **Evidencia:** `<a href=…>` hacia rutas propias en `GitPage.tsx:142,171` (`/tasks?id=`), `GrcPage.tsx:657` (`/approvals`), `service-desk/ConfigCorreoEntrante.tsx:112`, `ConfigGuardiasYMonitor.tsx:184` y `TicketDetail.tsx:505,513` (`/service-desk?ticket=`).
- **Impacto:** la SPA se recarga, se pierde la caché y el estado, y desde la ficha del ticket se sale del panel.
- **Arreglo:** usar `<Link to=…>`.

**M7. `frontend/src/pages/WikiPage.tsx:155-157` — prompt de IA en castellano fijo**
- **Estado:** ✅ arreglado 23-11-2026: instrucción en el idioma del operador (`wiki.ia_mejorar_redaccion`) y aviso si falla. ✅ (segunda ronda, 23-11-2026): la petición va por `POST /ai/texto` (`nexusAgentApi.texto`, módulo `inline_editor`: gobernanza, tope de gasto y registro, sin abrir conversación; sin IA devuelve 503 y el texto no se toca), como el editor en línea.
- **Evidencia:** `api.post('/ai/chat',{message:\`Mejora la redacción y claridad del siguiente texto…\`})` con `.catch(()=>{})`, llamando a la API directamente desde la página.
- **Impacto:** con un operador en o zh, la IA recibe la instrucción en castellano y puede devolver el bloque traducido al castellano. Si falla, no hay aviso. El prompt queda fuera de la gobernanza de prompts del backend.
- **Arreglo:** usar un endpoint con acción `mejorar_redaccion` y el idioma del operador (el prompt en el servidor), además de `toast.error`.

**M8. `frontend/src/pages/ResourceSchedulerPage.tsx:336-351` — Retroceso dentro del panel borra la reserva**
- **Estado:** ✅ arreglado 23-11-2026: el atajo sale si el foco está en `input, textarea, select, [contenteditable]`.
- **Evidencia:** el `keydown` global abre «¿eliminar reserva?» con `Delete` o `Backspace` si hay `selectedBooking`, sin mirar si el foco está en un campo. Al pulsar una reserva se selecciona y se abre `BookingPanel` (líneas 645-647), que tiene el campo numérico «horas/día» (línea 212).
- **Impacto:** al corregir las horas con Retroceso se cierra el panel (`setPanel(null)`) y salta la confirmación de borrado.
- **Arreglo:** salir si `e.target` está dentro de `input, textarea, select, [contenteditable]`, como hace `TasksPage.tsx:1172`.

**M9. `frontend/src/pages/PipelinePage.tsx:589-600` — solo tablero**
- **Estado:** ✅ arreglado 23-11-2026: `ViewToggle` tablero/lista con `DataTable` ordenable (se recuerda la vista). Canceladas: ✅ (segunda ronda, 23-11-2026) estándar de mercado: fuera del pipeline abierto y del ponderado, tasa de éxito = ganadas/(ganadas+perdidas), «Sin decisión (canceladas)» aparte con recuento e importe y filtro por estado; misma regla en el backend (`app/models/pipeline.py`, `pipeline_service.resumir_pipeline`, OLAP, métricas, informes e IA). Ver `docs/PIPELINE_COMERCIAL.md`.
- **Evidencia:** las oportunidades se pintan únicamente en columnas por etapa (`STAGES.map`). No hay `ViewToggle` ni tabla.
- **Impacto:** incumple la regla «kanban + lista donde aplique». No se puede ordenar por importe, fecha o probabilidad ni exportar la vista. Además, «cerradas» (línea 465) cuenta ganadas y perdidas pero no canceladas, mientras que «abiertas» (464) las excluye: las canceladas no se cuentan en ninguna parte (sin verificar si es intencionado).
- **Arreglo:** añadir `ViewToggle` con `DataTable`, como Service Desk (`ServiceDeskPage.tsx:191`).

**M10. `frontend/src/pages/clients/PortalUsersTab.tsx:110-117,159-164,293` — el operador conoce la contraseña del cliente**
- **Estado:** ✅ arreglado 23-11-2026: el equipo ya no escribe ni ve la contraseña: el servidor la genera y la envía al titular por correo (`enviar_acceso`); «Reenviar acceso» (`POST /portal/clients/{id}/send-access`, auditado). No existe flujo de invitación con enlace en el portal; ✅ ronda 2 (23-11-2026): cambio obligatorio en el primer acceso y tras «Reenviar acceso» (`client_users.must_change_password`, migración 198): el login y `/portal/auth/me` devuelven el estado, el resto de rutas del portal responden 403 `portal_cambio_de_contrasena_obligatorio` (8 idiomas) y el portal enseña solo la pantalla de cambio (`CambioDeContrasenaObligatorio.tsx`). Sigue sin invitación con enlace de un solo uso.
- **Evidencia:** el alta de un usuario del portal exige que el operador escriba la contraseña. Después se muestra en claro (`{credenciales.password}`) y se copia al portapapeles junto al correo y la URL (`navigator.clipboard.writeText(...)`, sin `catch`). El restablecimiento también lo fija el operador.
- **Impacto:** GRC/RGPD. Una credencial personal del cliente queda conocida por un tercero, pasa por el portapapeles y se envía por canales sin control. No hay forma de demostrar que solo el titular la conoce.
- **Arreglo:** usar una invitación con enlace de un solo uso para que el cliente fije la contraseña (el flujo `reset-password` ya existe) y forzar el cambio en el primer acceso.

### Baja

**B1. `frontend/src/i18n/langs/zh.mjs` — `grc.los` y `approvals.steps_suffix_plural` vacíos**
- **Estado:** ✅ arreglado 23-11-2026: `grc.los` en zh = «这些»; pasos con `approvals.pasos_uno`/`pasos_varios` (se retira `steps_suffix_plural`).
- **Evidencia:** `zh.grc.los === ""` y `zh.approvals.steps_suffix_plural === ""`. `resolveTranslation` trata la cadena vacía como ausente y cae al inglés.
- **Impacto:** en zh, `GrcPage.tsx:656` muestra «The 审批流程…» y `ApprovalsPage.tsx:1496` muestra «3 步s». La frase troceada en tres claves (artículo + negrita + resto) no es traducible bien.
- **Arreglo:** usar una sola clave con interpolación (`{flujos}`) y renderizar con `<Trans>` o en partes.

**B2. Etiquetas que nunca se traducen**
- **Estado:** ✅ arreglado 23-11-2026: `almint.urgencia_label` y `expenses.cat_*`.
- **Evidencia:**
  - `MisEquiposPage.tsx:236` usa `t('almint.urgencia')`, que en los tres idiomas es un **objeto** (`{low, medium, high, critical}`, `es.mjs:1074`). El traductor lo humaniza y siempre pinta «Urgencia».
  - `alm/ConciliacionTab.tsx:114` usa `t(\`gastos.categoria_${g.category}\`, g.category)`, pero el módulo `gastos` no existe. Las categorías están en `expenses.cat_*`, así que siempre sale el código crudo (`travel`, `meals`…).
- **Arreglo:** usar `almint.urgencia_label` y `expenses.cat_${…}`.

**B3. `frontend/src/pages/JiraIntegrationPage.tsx:249-251`**
- **Estado:** ✅ arreglado 23-11-2026: `autoComplete="off"`.
- **Evidencia:** el token de Jira usa `autoComplete="current-password"`.
- **Impacto:** el gestor de contraseñas puede rellenarlo con la contraseña del operador y proponer guardarla como credencial del sitio.
- **Arreglo:** usar `autoComplete="off"` o `new-password`.

**B4. `frontend/src/pages/TimerPage.tsx:209-214`**
- **Estado:** ✅ arreglado 23-11-2026 (segunda ronda): `GET /imputations?only_timer=true` (`list_imputations_query(..., solo_temporizador=True)` filtra `timer_session_id IS NOT NULL` en la base) y `/timer` lo usa. Test: `tests/test_historial_temporizador_2026_11_23.py`.
- **Evidencia:** el historial filtra `imp.timer_session_id` en el cliente sobre la primera página (`page_size: DEFAULT_PAGE_SIZE`).
- **Impacto:** si en esa página hay muchas imputaciones manuales, el historial del temporizador sale corto o vacío.
- **Arreglo:** filtrar en el servidor (`only_timer=true`).

**B5. `frontend/src/pages/SettingsPageSections.tsx:924,994,1063,1090,1108`**
- **Estado:** ✅ arreglado 23-11-2026: los formularios se vacían solo en `onSuccess`; `ejecutar` devuelve si fue bien.
- **Evidencia:** los formularios de alta (campo, sede, departamento, área) se vacían justo después de `create(form)`, sin esperar el resultado. `ejecutar` (línea 1077) captura el error y el `.then(() => setEditando(null))` se ejecuta igual.
- **Impacto:** si el servidor rechaza el alta, se pierde lo escrito o se cierra la edición.
- **Arreglo:** resetear en `onSuccess`.

**B6. `navigator.clipboard.writeText` sin `catch` y literal**
- **Estado:** ✅ arreglado 23-11-2026: portapapeles con aviso de fallo; el literal `Portal:` desaparece con el modal de credenciales.
- **Evidencia:** `clients/PortalUsersTab.tsx:117,222,276`. Además, `Portal:` es un literal sin traducir (línea 117).
- **Impacto:** en contexto no seguro o sin permiso, el rechazo queda sin capturar y no hay aviso.
- **Arreglo:** `try/catch` + toast, y clave i18n.

**B7. `frontend/src/pages/portal-client/PortalAdvancedSections.tsx:1095-1099`**
- **Estado:** ✅ arreglado 23-11-2026: `revokeObjectURL` en `setTimeout(…, 0)`.
- **Evidencia:** `a.click(); URL.revokeObjectURL(url)` en la misma vuelta.
- **Impacto:** en algunos navegadores la descarga del PDF firmado se cancela (sin verificar en los navegadores objetivo).
- **Arreglo:** revocar en un `setTimeout(…, 0)` o tras el evento.

**B8. Configuración del portal por cliente dentro del módulo Clientes (opinión)**
- **Estado:** ✅ decidido 23-11-2026 (segunda ronda): se queda en la ficha del cliente. Son datos de la entidad (módulos, SLA, usuarios, idioma y permisos de ese cliente), no configuración del operador ni un botón «Configurar» de módulo.
- **Evidencia:** `clients/ClientsPageTabs.tsx:530` tiene la subpestaña `config` (módulos, SLA, usuarios máximos, idioma, permisos de perfil).
- **Impacto:** son datos de la entidad, así que es aceptable. Pero mezcla configuración y gestión. Valorar si los valores por defecto deben vivir en `/settings/portal-*` (sin verificar si ya existen).
- **Arreglo:** decisión de producto.

## Claves i18n que faltan

Comprobado con script contra `i18n/langs/{es,en,zh}.mjs` (8.442 claves literales) y `i18n/portal/*.ts` (59 claves del portal).

| Clave | Idiomas | Dónde | Nota |
|---|---|---|---|
| `almint.urgencia` | es, en, zh (es objeto, no texto) | `MisEquiposPage.tsx:236` | B2 |
| `gastos.categoria_*` | módulo inexistente | `alm/ConciliacionTab.tsx:114` | B2 (usar `expenses.cat_*`) |
| `grc.los` | zh (vacía → cae al inglés) | `GrcPage.tsx:656` | B1 |
| `approvals.steps_suffix_plural` | zh (vacía) | `ApprovalsPage.tsx:1496` (fuera del lote F–Z) | B1 |
| `demanda.retirar`, `demanda.retirada`, `demanda.motivo_retirada` | en, zh | `components/demanda/DetalleDemanda.tsx:136,163` (fuera de `pages/`) | detectado al comprobar la paridad del módulo |
| `alm.action_assign_hint`, `settingsadvanced.service_desk_voz_ml_auto_resolucion` | vacías en los 3 | sin uso en `src/` | claves muertas |

Sin verificar sufijo a sufijo: 179 claves dinámicas (`t(\`…${x}\`)`). Todos sus prefijos tienen claves en los tres idiomas, salvo `gastos.categoria_`. `login_feat_*` es del portal y existe. Se comprobaron las enumeraciones de `sprints.prioridad_*`, `sprint_planning.prioridad_*|status_*`, `skills.cat_*`, `itsmknowledge.origen_*` y `puesta.*`.

Literales visibles en JSX del lote: solo siglas y marcas (`NPS`, `EAC`, `ETC`, `VAC`, `CPI`, `SPI`, `CSV`, `PNG`, `PDF`, `WIP`, `DocuSign Connect:`, `Adobe Sign:`, `Freight Pro`, `Midnight`, `Slate`). También etiquetas técnicas de credenciales en `SettingsPageSections.tsx:1301-1315` (`Integration Key (Client ID)`, `Secret Key`, `Base URL`), aceptables como términos del proveedor. Faltan además `Portal:` (B6) y `'General'` (Hardcode).

## Código muerto

| Elemento | Evidencia | Acción |
|---|---|---|
| `_PALETTE` | `InvoicesPage.tsx`: constante definida y sin ninguna referencia | Borrar |
| `textoDeEstado` | `alm/uso/comun.tsx`: exportada y sin uso en `src/` | Borrar o usar en `Estado` |
| `useMetaProveedores` | `proveedores/comunes.tsx`: exportado y sin uso | Borrar |
| `UNIDADES_DEL_SISTEMA`, `TIPOS_DE_SERVICIO_DEL_SISTEMA` | `proveedores/logica.ts`: exportadas y sin uso | Borrar o usar en `PestanaServicios` |
| `_reiniciarPortalEnVivo` | `portal-client/usePortalEnVivo.ts`: solo lo usa el test | Aceptable (ayuda de test) |
| Claves i18n vacías sin uso | `alm.action_assign_hint`, `settingsadvanced.service_desk_voz_ml_auto_resolucion` | Borrar de los 3 idiomas |
| Páginas sin ruta | Ninguna en el lote. Las 20 páginas raíz F–Z sin ruta propia (17 secciones de `/settings/:seccion` en `catalogoDeAjustes.tsx`, Mentions y Notifications dentro de `InboxPage`, y SettingsPageSections) están montadas (verificado) | — |

## Hardcode

| Tipo | Dónde | Nota |
|---|---|---|
| Prompt de IA en castellano | `WikiPage.tsx:155` | M7 |
| Moneda por defecto `'EUR'` | `internos/ConfigClientesInternos.tsx:50,62` | Usar la moneda de la empresa (`fmtMoneda.moneda`, como en `FinanceDashboardPage.tsx:108`) |
| Idioma por defecto `'es'` | `clients/ClientsPageTabs.tsx:906,916` (idioma del portal del cliente), `service-desk/ConfigEscaladoYAvisos.tsx:275` (vista previa de avisos) | Usar el idioma por defecto de la empresa |
| Texto enviado al backend en inglés | `service-desk/WorkflowDesignerPage.tsx:693` (`'cancelled by user'`) | Queda en el historial de la ejecución. Usar un código |
| Categoría `'General'` literal | `service-desk/TicketDetail.tsx:86` | Clave i18n |
| Literal `Portal:` | `clients/PortalUsersTab.tsx:117` | B6 |
| Colores | `settings-sections/MarcaSection.tsx:62,69` (`'#000000'`, `'#1f2937'`, `'#ffffff'`, ya citados en el M14 del 04), `portal-client/PortalUI.tsx:743-745`, `PortalDashboard.tsx:609-610`, `portalClientContext.tsx:414` | Ya en el M14 del 04 |
| Estados como cadena | `PipelinePage.tsx:37,464-466` (`'won'`, `'lost'`, `'cancelled'`), `TicketDetail.tsx:480,493` (`'in_progress'`, `'closed'`) | Constantes compartidas con el backend |

## Permisos y diseño (sin verificar botón a botón)

- **`puede()`.** Lo usan 45 de los 166 `.tsx` del lote. Otros 74 tienen mutaciones y no usan `puede()`. Las páginas raíz son: Governance, Imputar, Invoices, IssueTypes, MFA, Mentions, MilestoneBilling, MisEquipos, NPS, NexusAgent, OKRs, Oracle, Organizations, PlanificacionDeRecursos, Politicas, Portfolio, Profitability, ProjectPermissions, ProjectTemplates, PublicForms, RACI, RateCards, ReportBuilder, ResourceScheduler, Revenue, RiskScores, Risks, SLACalendars, Scenarios, Search, SprintPlanning, Sprints, Timer, UAT, UserCosts, Wiki y Workflows. Muchas son secciones de Ajustes, protegidas por la capacidad de la sección.
- **Muestreo.** OKRs (`recursos.ver` = admin/PM/RR. HH.) frente a `require_any_manager` en `okrs.py:68,103`. Facturas (`finanzas.ver`) frente a `require_any_manager` en `invoices.py`. Son coherentes en apariencia. El resto queda sin verificar.
- **Kanban + lista.**
  - Bien en Service Desk, Tareas, Recursos (`ViewToggle`) y Sprints (tablero + backlog).
  - Falta en Pipeline (M9).
  - En `UATPage.tsx` no hay `ViewToggle` ni vista tablero. El 04 la contaba como vista doble; sin verificar visualmente. Para casos de prueba, la lista basta.
- **Inputs nativos.** Siguen en el lote (M5 del 04). Destacan `service-desk/ConfigTab.tsx` (24), `OrganizationsPage.tsx` (11), `SettingsPageSections.tsx` (11), `IntakeFormPage.tsx:112-122` (página pública con estilos inline `FS`/`LS`) y `TicketDetail.tsx:931,933`.
- **Formularios que se resetean con cada refresco.** No es un hallazgo. Los `useEffect(() => setForm(data), [data])` (MarcaSection, ConfigProveedores, SettingsAdvanced, Traduccion, Jira, ClientsPageTabs) solo se reejecutan si los datos cambian, gracias al structural sharing de react-query. `refetchOnWindowFocus: true` (`main.tsx:145`) podría pisar una edición en curso solo si otro usuario cambia el mismo ajuste.

## Estado de los arreglos (23-11-2026)

Cada hallazgo de arriba lleva su línea **Estado**. Tablas:
- **Claves i18n que faltan:** todas resueltas (`almint.urgencia_label`, `expenses.cat_*`, `grc.los` en zh, pasos con singular/plural, 3 `demanda.*` en en/zh); las dos claves vacías sin uso, borradas. Paridad es/en/zh medida tras el arreglo: mismo número de claves y 0 vacías.
- **Código muerto:** `_PALETTE`, `textoDeEstado`, `useMetaProveedores`, `UNIDADES_DEL_SISTEMA` y `TIPOS_DE_SERVICIO_DEL_SISTEMA` borrados (0 usos verificados). `META_POR_DEFECTO`: ✅ borrado (segunda ronda), y con él 4 constantes que solo usaba él (`CICLO`, `ESTADOS_DE_CONTRATO`, `ESTADOS_DE_PAQUETE`, `NIVELES_DE_RIESGO`; 0 usos medidos).
- **Hardcode:** prompt de la wiki en el idioma del operador; moneda de la empresa (`useFormatoMoneda`) en clientes internos; idioma por defecto con `IDIOMA_POR_DEFECTO` (`i18n/portalTranslations.ts`) en la ficha del cliente y el del operador en la vista previa de avisos; `'cancelled by user'` ya no se envía; `'General'` y `Portal:` fuera. Colores ✅ (M14 del 04, segunda ronda). Estados como cadena ✅: Pipeline con `constants/pipelineStages.ts` (y `app/models/pipeline.py` en el backend) y TicketDetail con `constants/estadosDeTicket.ts` (mismos valores que `TicketStatus`).
- **Segunda ronda (23-11-2026):** ninguna fila queda sin estado. Mapa de páginas: cada fila con hallazgo lleva «→ ✅».
