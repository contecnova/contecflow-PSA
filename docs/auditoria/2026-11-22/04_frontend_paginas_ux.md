# Auditoría 04 — Frontend: páginas, enrutado, menú y UX

Fecha: 2026-11-22/23 · Alcance: `frontend/src/pages` (386 ficheros: 231 .ts/.tsx + 155 .css, 123.566 líneas), `frontend/src/App.tsx`, `frontend/src/permisos/*`, `frontend/src/components/layout/*` · Modo: solo lectura (sin tests, lint ni typecheck).

## Resumen

**Método y cobertura (honesto):**
- **Lectura por página.** Se leyeron las 41 páginas raíz de la A a la E (de AIHubPage a ExpensesPage): estructura, handlers, llamadas a la API y JSX. De las 8 de más de 800 líneas solo se revisaron estructura y handlers.
- **El resto.** Las 190 páginas y módulos restantes (raíz F–Z, `service-desk/`, `settings*/`, `bpm/`, `portal-client/`, `proveedores/`, `internos/`, `alm/`, `clients/`) se auditaron con métricas automáticas en los 386 ficheros y comprobaciones dirigidas. No hubo lectura completa línea a línea. Lo que no se ha comprobado aparece como «sin verificar».
- **Rutas del backend.** Se volcaron las 2.745 rutas reales de FastAPI (`app.routes`) y se cruzaron con 2.061 llamadas literales `api.get/post/…` del front.
- **Comprobaciones con script.** Paridad de claves i18n del menú (es/en/zh) y del portal (8 idiomas), rutas de `App.tsx` frente a `permisos/navegacion.ts` frente al menú, y enlaces entrantes de cada ruta.

**Lo bueno, medido:**
- **Permisos de rutas.** Las 100 rutas protegidas están declaradas en `navegacion.ts` (0 sin declarar). Por eso `ProtectedRoute`, el menú y la página de inicio comparten fuente.
- **Configuración.** `/settings/:seccion` filtra por capacidad (`puedeVerSeccion`, `SettingsPage.tsx:45`). Una sección sin permiso redirige a `/403`.
- **Endpoints.** Ninguna llamada del front apunta a una ruta inexistente en el backend. Las 5 coincidencias del script eran falsos positivos de plantillas `${...}`.
- **i18n.** Hay 0 claves de menú sin traducir en es/en/zh. El portal tiene las 8 traducciones con 1.287 claves cada una (paridad total) y las 290 claves que usa existen.
- **Kit y patrones prohibidos.** En pages hay 0 `dangerouslySetInnerHTML`, 0 `<button>` nativos fuera de un comentario, 0 `<select>` nativos (2 apariciones son comentarios), 0 `console.log`, 0 `alert/confirm` del navegador, 0 colores hex/rgb en los 155 CSS y 0 `user.role === 'admin'`/`hasRole`.

**Recuento de hallazgos:** críticos 1 · altos 9 · medios 17 · bajos 12.

**Críticos y altos:**
1. **CRÍTICA. La firma electrónica no puede crear solicitudes.** `ESignPage.tsx:140` convierte un id UUID con `Number()`.
2. **ALTA. Páginas huérfanas.** `/client-portal` (1.061 líneas) y `/esign` no tienen entrada de menú ni enlace en toda la app. `/search` solo es accesible por la redirección `/fts-search`.
3. **ALTA. Acciones rápidas sin traducir y sin permisos.** La paleta global (`GlobalSearch.tsx:25-34`) y el menú «Crear» (`QuickCreateMenu.tsx:15-26`) tienen textos en castellano fijos, visibles en todas las pantallas. No filtran por permiso: «Nueva factura» o «Nuevo contrato» se ofrecen a quien recibirá 403.
4. **ALTA. Credenciales LiveKit aceptadas desde la URL.** `CallPage.tsx:83-85` las toma de `?token=&url=&room=` aunque el comentario diga lo contrario.
5. **ALTA. Acciones destructivas o de cumplimiento de un clic.** En `ChatAdminPage.tsx:233,315,353` la purga de retención, la liberación de un legal hold y el borrado de una integración no piden confirmación ni tienen `onError`.
6. **ALTA. URL de documento del portal sin validar.** `file_url` es texto libre (backend `client_portal.py:185`: `Optional[str]`, sin esquema) y se pinta como `href` en el portal externo (`PortalAdvancedSections.tsx:1146`) y en dos vistas internas, sin `sanitizeUrl`.
7. **ALTA. Botón «Configurar» en un módulo.** `DemandaPage.tsx:237` incumple la regla de diseño.
8. **ALTA. Colisión de `queryKey`.** `['integrations']` lo usan ChatAdmin y Enterprise con datos distintos. Además, `['projects']` aparece en ≥16 páginas con `queryFn` distintos (respuesta cruda, filtrada o con `.catch(()=>[])`).
9. **ALTA. Errores tragados de forma masiva.** Hay 118 `catch` vacíos o `.catch(()=>[]|null)` en 46 ficheros. Un fallo del servidor se ve como «sin datos».

## Mapa de páginas

Generado de `App.tsx` + `permisos/navegacion.ts` + `NAV_GROUPS` + métricas por fichero (117 rutas; 100 protegidas, todas declaradas; las 17 no declaradas son públicas o redirecciones). «catch vacíos» = errores tragados medidos. Las páginas montadas solo dentro de Configuración están en «Código muerto» (no lo son).

| Ruta | Página | Capacidad | En menú | Líneas | catch vacíos | Qué hace (cabecera del fichero) | Estado |
|---|---|---|---|---|---|---|---|
| /login | LoginPage | pública/sin declarar | no | 724 | 2 | Una respuesta de login (contraseña, SSO, passkey o empresa elegida): sesión, segundo factor o selector. | completa (métricas; detalle sin verificar salvo lote A–E) |
| /reset-password | ResetPasswordPage | pública/sin declarar | no | 185 | 0 | Logo } | completa (métricas; detalle sin verificar salvo lote A–E) |
| /approvals/decide | AprobacionPorCorreoPage | pública/sin declarar | no | 70 | 0 | Aprobar o rechazar desde el enlace del correo, sin entrar (revisión 2026-11). | completa (métricas; detalle sin verificar salvo lote A–E) |
| /403 | ForbiddenPage | (sesión) | no | 44 | 0 |  | completa (métricas; detalle sin verificar salvo lote A–E) |
| / | (redirección) | (sesión) | no |  | 0 |  | redirección |
| /work-dashboard | WorkDashboardPage | (sesión) | sí | 420 | 0 | 16-11-2026: cabecera con el nombre del menú (nav.work_dashboard); fecha con el | completa (métricas; detalle sin verificar salvo lote A–E) |
| /projects | ProjectsPage | proyectos.ver | sí | 1227 | 0 | Cambio de un campo de texto, select, textarea o DateInput. | completa (métricas; detalle sin verificar salvo lote A–E) |
| /projects/:id | ProjectDetailPage | proyectos.ver | no | 534 | 0 | ProjectOut (app/schemas/projects.py), tal como lo tipa el slice de proyectos. | completa (métricas; detalle sin verificar salvo lote A–E) |
| /projects-dashboard | ProjectsDashboardPage | proyectos.panel | sí | 234 | 2 | ProjectsDashboardPage — panel de proyectos (/projects-dashboard). | completa (métricas; detalle sin verificar salvo lote A–E) |
| /tasks | TasksPage | (sesión) | sí | 1817 | 6 | TasksPage — tareas: tablero, lista y vistas del planificador. | completa (métricas; detalle sin verificar salvo lote A–E) |
| /time | TimePage | (sesión) | sí | 66 | 0 | 16-11-2026: la cabecera de la página ("Tiempo", como el menú) va arriba y a | completa (métricas; detalle sin verificar salvo lote A–E) |
| /imputar | ImputarPage | (sesión) | no | 643 | 1 | Horas escritas a mano: «2,25», «2.25» o «2». Devuelve null si no es un número entre 0 y 24. | completa (métricas; detalle sin verificar salvo lote A–E) |
| /resources | ResourcesPage | recursos.ver | sí | 603 | 0 | 16-11-2026: pasada de diseño. KPIs con KpiCard (antes cifra monoespaciada | completa (métricas; detalle sin verificar salvo lote A–E) |
| /alerts | AlertsPage | alertas.ver | sí | 202 | 0 | Summary cards } | completa (métricas; detalle sin verificar salvo lote A–E) |
| /exports | ExportsPage | exportar.ver | sí | 202 | 0 | Auditoría 2026-09: la etiqueta dice el formato que de verdad se descarga. } | completa (métricas; detalle sin verificar salvo lote A–E) |
| /reports | ReportsPage | colaboracion.ver | sí | 1233 | 6 | ReportsPage — informes (/reports): métricas, explorador, plantillas, | completa (métricas; detalle sin verificar salvo lote A–E) |
| /settings | SettingsPage | (sesión) | sí | 152 | 0 | Configuración: una sola entrada para toda la configuración del operador | completa (métricas; detalle sin verificar salvo lote A–E) |
| /settings/:seccion | SettingsPage | (sesión) | no | 152 | 0 | Configuración: una sola entrada para toda la configuración del operador | completa (métricas; detalle sin verificar salvo lote A–E) |
| /timesheets | TimesheetsPage | (sesión) | no | 498 | 0 | ── Modo edición inline ── | completa (métricas; detalle sin verificar salvo lote A–E) |
| /capacity | CapacityPage | recursos.ver | sí | 435 | 0 | CapacityPage — Planificador visual de recursos con drag-and-drop | completa (métricas; detalle sin verificar salvo lote A–E) |
| /profitability | ProfitabilityPage | finanzas.ver | sí | 388 | 0 | ProfitabilityPage — rentabilidad por proyecto (/profitability). | completa (métricas; detalle sin verificar salvo lote A–E) |
| /pipeline | PipelinePage | finanzas.ver | sí | 719 | 0 | PipelinePage — embudo comercial (oportunidades por etapa). | completa (métricas; detalle sin verificar salvo lote A–E) |
| /contracts | ContractsPage | finanzas.ver | sí | 599 | 0 | Color de datos → custom property que consumen las clases .ctr-*. | completa (métricas; detalle sin verificar salvo lote A–E) |
| /risks | RisksPage | proyectos.gobierno | sí | 454 | 0 | RisksPage — registro y matriz de riesgos. | completa (métricas; detalle sin verificar salvo lote A–E) |
| /skills | SkillsPage | colaboracion.ver | sí | 566 | 0 | SkillsPage — habilidades del equipo: matriz, perfiles, búsqueda de personas | completa (métricas; detalle sin verificar salvo lote A–E) |
| /absences | AbsencesPage | (sesión) | sí | 138 | 0 | Ausencias gobernadas por reglas (tarea #25, revisión 167). | completa (métricas; detalle sin verificar salvo lote A–E) |
| /overtime | HorasExtraPage | (sesión) | sí | 63 | 0 | Horas extra (18-11-2026): petición previa o declaración posterior, | completa (métricas; detalle sin verificar salvo lote A–E) |
| /changes | ChangesPage | proyectos.gobierno | sí | 533 | 0 | Color dinámico (impacto/estado) como propiedad CSS que consume .chg-tone. | completa (métricas; detalle sin verificar salvo lote A–E) |
| /deliverables | DeliverablesPage | proyectos.gobierno | sí | 343 | 0 | Estados del entregable; la etiqueta es deliverables.estado_<clave>. | completa (métricas; detalle sin verificar salvo lote A–E) |
| /client-portal | ClientPortalPage | finanzas.ver | no | 1061 | 0 | ClientPortalPage – Internal PM view for managing the client portal: | huérfana (sin menú ni enlace) → ✅ arreglado 23-11-2026 |
| /support-dashboard | SupportDashboardPage | soporte.panel | sí | 34 | 0 | SupportDashboardPage — Panel de soporte (estado del soporte e ITSM). | completa (métricas; detalle sin verificar salvo lote A–E) |
| /service-desk | ServiceDeskPage | sd.ver | sí | 291 | 1 | ServiceDeskPage — ITIL/ITSM completo | completa (config en /settings/sd) |
| /sd/workflow-designer | service-desk/WorkflowDesignerPage | sd.disenar_flujos | no | 1120 | 1 | WorkflowDesignerPage — diseñador visual de workflows para Service Desk. | completa (métricas; detalle sin verificar salvo lote A–E) |
| /invoices | InvoicesPage | finanzas.ver | sí | 368 | 1 | InvoicesPage — Facturación: crear, gestionar y hacer seguimiento de facturas | completa (métricas; detalle sin verificar salvo lote A–E) |
| /portal | PortalClientePage | pública/sin declarar | no | 515 | 3 | PortalClientePage — Portal externo del cliente. | completa (métricas; detalle sin verificar salvo lote A–E) |
| /portal/view/:token | PortalPublicViewPage | pública/sin declarar | no | 127 | 1 | Idioma de la vista pública (16-11-2026): la de un enlace no tiene sesión, | completa (métricas; detalle sin verificar salvo lote A–E) |
| /sprints | SprintsPage | proyectos.trabajo | sí | 666 | 0 | SprintsPage — Full Scrum sprint management | completa (métricas; detalle sin verificar salvo lote A–E) |
| /expenses | ExpensesPage | gastos.ver | sí | 773 | 0 | ExpensesPage — gestión completa de gastos con flujo de aprobación | completa (métricas; detalle sin verificar salvo lote A–E) |
| /revenue | RevenuePage | finanzas.ver | sí | 699 | 0 | RevenuePage — Reconocimiento de ingresos ASC 606 / IFRS 15 | completa (métricas; detalle sin verificar salvo lote A–E) |
| /risk-scores | RiskScoresPage | analitica.ver | sí | 484 | 2 | RiskScoresPage — Predicción de riesgo por proyecto | completa (métricas; detalle sin verificar salvo lote A–E) |
| /evm | EVMPage | analitica.ver | sí | 313 | 0 | EVMPage — Earned Value Management | completa (métricas; detalle sin verificar salvo lote A–E) |
| /portfolio | PortfolioPage | analitica.ver | sí | 480 | 0 | PortfolioPage — Gestión de carteras de proyectos | completa (métricas; detalle sin verificar salvo lote A–E) |
| /portfolio/intake | CarteraIntakePage | colaboracion.ver | sí | 244 | 0 | CarteraIntakePage — /portfolio/intake (rev. 173). | completa (métricas; detalle sin verificar salvo lote A–E) |
| /demand | DemandaPage | (sesión) | sí | 253 | 0 | DemandaPage — /demand (22-11-2026): pantalla de trabajo del motor de flujos de | completa; botón «Configurar» (regla) → ✅ arreglado 23-11-2026 |
| /resources/planning | PlanificacionDeRecursosPage | equipo.ver | sí | 202 | 0 | PlanificacionDeRecursosPage — /resources/planning (rev. 173). | completa (métricas; detalle sin verificar salvo lote A–E) |
| /git | GitPage | proyectos.gobierno | sí | 186 | 0 | GitPage — bidirectional Git integration dashboard | completa (métricas; detalle sin verificar salvo lote A–E) |
| /sprint-charts | SprintChartsPage | analitica.ver | sí | 244 | 0 | SprintChartsPage — Burnup chart + Velocity trend per project | completa (métricas; detalle sin verificar salvo lote A–E) |
| /esign | ESignPage | proyectos.gobierno | no | 403 | 0 | ESignPage — Electronic signature management dashboard | ROTA (crear firma) + huérfana → ✅ arreglado 23-11-2026 |
| /report-builder | ReportBuilderPage | analitica.ver | sí | 632 | 3 | ReportBuilderPage — No-code parametric report builder | completa (métricas; detalle sin verificar salvo lote A–E) |
| /nps | NPSPage | finanzas.ver | sí | 334 | 0 | NPSPage — Customer NPS & Health trend dashboard | completa (métricas; detalle sin verificar salvo lote A–E) |
| /automations | AutomationsPage | ia.ver | sí | 649 | 0 | AutomationsPage — reglas SI [disparador] [condición] ENTONCES [acciones]. | completa (métricas; detalle sin verificar salvo lote A–E) |
| /scenarios | ScenariosPage | finanzas.ver | sí | 231 | 0 | ScenariosPage — Scenario planning / What-if capacity | completa (métricas; detalle sin verificar salvo lote A–E) |
| /budgets | BudgetsPage | finanzas.ver | sí | 283 | 0 | Presupuestos (revisión 2026-11): de proyecto (existente o previsto), de | completa (métricas; detalle sin verificar salvo lote A–E) |
| /nexus-agent | NexusAgentPage | ia.ver | sí | 424 | 1 | NexusAgentPage — el agente que ejecuta instrucciones en lenguaje natural. | completa (métricas; detalle sin verificar salvo lote A–E) |
| /oracle | OraclePage | ia.ver | sí | 252 | 0 | OraclePage — NexusOracle: riesgos y anomalías detectados por reglas. | completa (métricas; detalle sin verificar salvo lote A–E) |
| /meetings-ai | MeetingsAIPage | reuniones.usar | sí | 220 | 0 | MeetingsAIPage — Asistente de reuniones (rehecha el 19-11-2026). | completa (métricas; detalle sin verificar salvo lote A–E) |
| /contracts-ai | ContractsAIPage | ia.ver | no | 405 | 0 | ContractsAIPage — H22 (Item H22 cerrado). | completa (métricas; detalle sin verificar salvo lote A–E) |
| /settings/workflows | → /settings/project-workflows |  | no |  | 0 |  | redirección |
| /workflows | → /settings/project-workflows |  | no |  | 0 |  | redirección |
| /calendar | CalendarPage | colaboracion.ver | no | 226 | 4 | CalendarPage v23 — Vista calendario global unificada | parcial (errores tragados, sin carga/error) → ✅ arreglado 23-11-2026 |
| /wiki | WikiPage | colaboracion.ver | sí | 748 | 8 | 16-11-2026: pestañas Wiki / Etiquetas con Tabs bajo la cabecera (antes un | completa (métricas; detalle sin verificar salvo lote A–E) |
| /epics | EpicsPage | proyectos.trabajo | sí | 400 | 1 | epics_service.serialize_epic; progress solo llega en el roadmap (get_roadmap_data). | completa (métricas; detalle sin verificar salvo lote A–E) |
| /search | SearchPage | colaboracion.ver | no | 298 | 0 | SearchPage v23 — Búsqueda unificada (NQL + Full-text) | huérfana (solo redirección /fts-search) → ✅ arreglado 23-11-2026 |
| /cumulative-flow | CumulativeFlowPage | analitica.ver | sí | 207 | 1 | epics_service.get_cfd_data: una fila por día con date y el recuento de cada estado. | completa (métricas; detalle sin verificar salvo lote A–E) |
| /dependencies | DependenciesPage | proyectos.trabajo | sí | 400 | 2 | task_service.list_task_dependencies (sin nota: la tabla task_dependencies no la tiene). | completa (métricas; detalle sin verificar salvo lote A–E) |
| /fts-search | → /search |  | no |  | 0 |  | redirección |
| /wiki-tags | → /wiki |  | no |  | 0 |  | redirección |
| /cmdb | CMDBPage | cmdb.ver | sí | 945 | 0 | Color de la etiqueta (dato): lo consume .cmdb-chip vía --cmdb-chip. | completa (métricas; detalle sin verificar salvo lote A–E) |
| /agent-dashboard | AgentDashboardPage | cmdb.ver | sí | 176 | 0 | Filters } | parcial (sin estado de error) → ✅ arreglado 23-11-2026 |
| /kanban-advanced | → /tasks?view=kanban |  | no |  | 0 |  | redirección |
| /sprint-planning | SprintPlanningPage | ia.ver | sí | 329 | 2 | SprintPlanningPage — planes de sprint generados por IA, por proyecto. | completa (métricas; detalle sin verificar salvo lote A–E) |
| /epic-gantt | EpicGanttPage | proyectos.trabajo | sí | 330 | 1 | epics_service.get_roadmap_data. | completa (métricas; detalle sin verificar salvo lote A–E) |
| /mentions | → /inbox?tab=mentions |  | no |  | 0 |  | redirección |
| /semantic-engine | SemanticEnginePage | ia.asignacion | sí | 498 | 0 | SemanticEnginePage — asignación de tareas y tickets con IA. | completa (métricas; detalle sin verificar salvo lote A–E) |
| /resource-forecast | ResourceForecastPage | recursos.prevision | sí | 339 | 0 | ResourceForecastPage — previsión de carga del equipo por semanas. | completa (métricas; detalle sin verificar salvo lote A–E) |
| /resource-scheduler | ResourceSchedulerPage | recursos.prevision | sí | 796 | 0 | ResourceSchedulerPage — visual resource scheduler (Runn/Parallax-style) | completa (métricas; detalle sin verificar salvo lote A–E) |
| /milestone-billing | MilestoneBillingPage | finanzas.ver | sí | 401 | 0 | MilestoneBillingPage — Facturación por hito. | completa (métricas; detalle sin verificar salvo lote A–E) |
| /approvals | ApprovalsPage | colaboracion.ver | sí | 1655 | 1 | Aprobaciones: bandeja (/approvals) y configuración de flujos (/settings/approval-workflows). | completa (métricas; detalle sin verificar salvo lote A–E) |
| /documents | DocumentsPage | colaboracion.ver | sí | 1463 | 0 | DocumentsPage — Rediseño completo del hub de gestión documental | completa (métricas; detalle sin verificar salvo lote A–E) |
| /timer | TimerPage | (sesión) | no | 392 | 0 | Timer Page — Seguimiento de tiempo con cronómetro activo e historial | completa (métricas; detalle sin verificar salvo lote A–E) |
| /gantt | GanttPage | proyectos.trabajo | sí | 300 | 0 | GanttPage — delegated to GanttChart v2 component. | completa (métricas; detalle sin verificar salvo lote A–E) |
| /data-explorer | DataExplorerPage | analitica.ver | sí | 42 | 0 | DataExplorerPage — Exploración interactiva de datos. | completa (métricas; detalle sin verificar salvo lote A–E) |
| /ask-company | PreguntarALaEmpresaPage | colaboracion.ver | sí | 336 | 0 | Preguntar a la empresa — analítica conversacional con contecintelligence (revisión 2026-11). | completa (métricas; detalle sin verificar salvo lote A–E) |
| /lessons | LeccionesPage | proyectos.trabajo | sí | 193 | 0 | Lecciones aprendidas — la base de la mejora continua (revisión 2026-11). | completa (métricas; detalle sin verificar salvo lote A–E) |
| /predictions | PredictionsPage | analitica.ver | sí | 49 | 0 | PredictionsPage — Inteligencia predictiva. | completa (métricas; detalle sin verificar salvo lote A–E) |
| /data-platform | DataPlatformPage | datos.plataforma | sí | 172 | 8 | DataPlatformPage — Plataforma de datos: ETL, conectores, | parcial (errores tragados) → ✅ arreglado 23-11-2026 |
| /data-governance | DataGovernancePage | datos.plataforma | sí | 478 | 5 | DataGovernancePage — Gobernanza de datos. | parcial (borrado sin confirmar) → ✅ arreglado 23-11-2026 |
| /projects/:id/analytics | BIProjectDetailPage | analitica.ver | no | 408 | 5 |  | parcial (sin estado de error) → ✅ arreglado 23-11-2026 |
| /bi | → /executive |  | no |  | 0 |  | redirección |
| /bi/:section | (redirección) |  | no |  | 0 |  | redirección |
| /bi/project/:projectId | (redirección) |  | no |  | 0 |  | redirección |
| /subcontractors | SubcontractorsPage | proveedores.ver | sí | 1095 | 0 | SubcontractorsPage — subcontratistas, sus personas, asignaciones, horas y facturas. | completa (métricas; detalle sin verificar salvo lote A–E) |
| /supplier-portal | proveedores/PortalDelProveedor | proveedores.portal | sí | 364 | 0 | Portal del proveedor (/supplier-portal, migración 191). | completa (métricas; detalle sin verificar salvo lote A–E) |
| /internal-clients | internos/ClientesInternosPage | interno.gestionar | sí | 72 | 0 | Clientes internos (/internal-clients, capacidad interno.gestionar, 22-11-2026). | completa (métricas; detalle sin verificar salvo lote A–E) |
| /mi-departamento | internos/MiDepartamentoPage | interno.portal | sí | 81 | 0 | Portal interno «Mi departamento» (/mi-departamento, capacidad interno.portal, 22-11-2026). | completa (métricas; detalle sin verificar salvo lote A–E) |
| /finance-dashboard | FinanceDashboardPage | finanzas.ver | sí | 393 | 0 | Periodo: filtro bajo la cabecera, no en ella. } | completa (métricas; detalle sin verificar salvo lote A–E) |
| /team-dashboard | TeamDashboardPage | equipo.ver | sí | 239 | 2 | 16-11-2026: cabecera con el nombre del menú (nav.team_dashboard), KPIs con el | completa (métricas; detalle sin verificar salvo lote A–E) |
| /clients | ClientsPage | finanzas.ver | sí | 629 | 0 | Tamaño de página de la lista de clientes (#22: el backend pagina con page/page_size). | completa (métricas; detalle sin verificar salvo lote A–E) |
| /alm | ALMPage | alm.ver | sí | 1657 | 0 | Entorno de una licencia → clave de su etiqueta ('all' no se enseña). | completa (métricas; detalle sin verificar salvo lote A–E) |
| /alm/altas-y-bajas | ALMAltasBajasPage | equipo.ver | sí | 469 | 0 | Altas y bajas de licencias y equipos (licencias y hardware, fase 4). | completa (métricas; detalle sin verificar salvo lote A–E) |
| /my-equipment | MisEquiposPage | (sesión) | sí | 310 | 0 | Mis equipos y licencias — autoservicio de cada persona (licencias y hardware, fase 4). | completa (métricas; detalle sin verificar salvo lote A–E) |
| /org-chart | OrgChartPage | recursos.ver | sí | 658 | 0 | OrgChartPage — Organigrama, posiciones y cadenas de aprobación | completa (métricas; detalle sin verificar salvo lote A–E) |
| /okrs | OKRsPage | recursos.ver | sí | 507 | 0 | OKRsPage — Objectives & Key Results | completa (métricas; detalle sin verificar salvo lote A–E) |
| /performance-reviews | PerformanceReviewsPage | recursos.ver | sí | 2131 | 4 | PerformanceReviewsPage — Evaluaciones de rendimiento 360° | completa (métricas; detalle sin verificar salvo lote A–E) |
| /training | TrainingPage | colaboracion.ver | sí | 326 | 0 | TrainingPage — Formación y Certificaciones | completa (métricas; detalle sin verificar salvo lote A–E) |
| /executive | BIPage | analitica.ver | sí | 171 | 0 |  | parcial (sin estado de error) → ✅ arreglado 23-11-2026 |
| /inbox | InboxPage | (sesión) | sí | 83 | 0 | InboxPage — Bandeja unificada de Notificaciones, Menciones y Aprobaciones. | completa (métricas; detalle sin verificar salvo lote A–E) |
| /notifications | → /inbox?tab=notifications |  | no |  | 0 |  | redirección |
| /raci | RACIPage | proyectos.trabajo | sí | 335 | 0 | RACIPage — Matriz de responsabilidades por proyecto (R/A/C/I) | completa (métricas; detalle sin verificar salvo lote A–E) |
| /changelog | ChangelogPage | proyectos.trabajo | sí | 350 | 0 | ChangelogPage — Release notes y changelog por proyecto | completa (métricas; detalle sin verificar salvo lote A–E) |
| /uat | UATPage | proyectos.trabajo | sí | 419 | 0 | UATPage — Gestión de casos UAT (User Acceptance Testing) | completa (métricas; detalle sin verificar salvo lote A–E) |
| /intake/:token | IntakeFormPage | pública/sin declarar | no | 170 | 0 | IntakeFormPage — Public-facing form, no auth required. | completa (métricas; detalle sin verificar salvo lote A–E) |
| /bpm | BPMPage | recursos.prevision | sí | 763 | 2 | Diagrama en blanco con sus tres nodos de ejemplo en el idioma de la interfaz. | completa (métricas; detalle sin verificar salvo lote A–E) |
| /chat | ChatPage | colaboracion.ver | no | 2013 | 4 | ChatPage — Teams-like internal chat for Contecflow PSA. | completa (métricas; detalle sin verificar salvo lote A–E) |
| /chat/admin | → /settings/chat-admin | org.administrar | no |  | 0 |  | redirección |
| /chat/call/:callId | CallPage | colaboracion.ver | no | 605 | 11 | CallPage — vista de videollamada (Mockup §6.2). | completa; fallo seguridad (token por URL) → ✅ arreglado 23-11-2026 |
| * | NotFoundPage | pública/sin declarar | no | 41 | 0 |  | completa (métricas; detalle sin verificar salvo lote A–E) |

## Hallazgos por severidad

Formato: **fichero:línea**. Para cada uno: evidencia, impacto y arreglo.

### Crítica

**C1. `frontend/src/pages/ESignPage.tsx:140`**
- **Estado:** ✅ arreglado 23-11-2026: ids como texto (UUID) en `ESignPage` (tipos `Envelope`/`Signer`, mutaciones y `POST /esign` sin `Number()`); error con `extractErr`.
- **Evidencia:** `api.post('/esign', { ...form, document_id: Number(form.document_id), ... })`. `documents.id` es `String(36)` UUID (`app/models/documents.py:46`) y el backend espera `document_id: str` (`app/api/v1/endpoints/esign.py:80,103`). `Envelope.id` está tipado como `number` en las líneas 37, 233 y 241.
- **Impacto:** `Number(uuid)` da `NaN`, que se serializa como `null`, y el backend responde 422. No se puede crear ninguna solicitud de firma.
- **Arreglo:** enviar el id tal cual, tipar los ids como `string` y quitar los `Number()`.

### Alta

**A1. `frontend/src/App.tsx:494` (`/client-portal`) y `App.tsx:535` (`/esign`) — páginas huérfanas**
- **Estado:** ✅ arreglado 23-11-2026: entradas de menú «Firma electrónica» (`/esign`, Proyectos) y «Portal de clientes» (`/client-portal`, Clientes y finanzas) en `Layout.tsx`; capacidades ya declaradas en `navegacion.ts`. Medido: `/client-portal` no es duplicado de la ficha del cliente (crea UAT, documentos y casos de prueba; la ficha no), así que se enlaza en vez de retirarla. `/search`: ✅ (segunda ronda) enlazado desde la paleta ⌘K («Ver todos los resultados» e Intro → `/search?q=…`, con `puedeAbrir`).
- **Evidencia:** no aparecen en `NAV_GROUPS` (`Layout.tsx:190-298`). Un grep en `src/` excluyendo tests no encuentra ningún `to=`/`navigate`/`href` hacia ellas: solo `App.tsx` y `navegacion.ts`.
- **Impacto:** ClientPortalPage (1.061 líneas, gestión interna del portal) y ESignPage solo se abren tecleando la URL. Es código muerto funcional; ESign, además, está roto (C1).
- **Arreglo:** decidir. O se añaden al menú (Clientes y finanzas → «Portal de clientes»; Proyectos → «Firma electrónica»), o se retiran ruta, permiso y página.

**A2. `frontend/src/components/layout/GlobalSearch.tsx:25-34,164-165` — paleta global**
- **Estado:** ✅ arreglado 23-11-2026: acciones con claves `globalsearch.accion_*`/`pista_*` (es/en/zh), iconos lucide y filtro `puedeAbrir` + `canOpen`; input del kit.
- **Evidencia:** `QUICK_ACTIONS` con `label: 'Nueva tarea'`, `'Imputar horas'`, `'Calendario'`, `hint: 'Ver calendario'`… se pintan tal cual (`{action.label}`, `{action.hint}`). Los iconos son emojis.
- **Impacto:** castellano fijo para los operadores en/zh en la paleta (⌘K) de todas las pantallas. Además, «Configuración» y «Gastos» aparecen sin comprobar `puedeAbrir`.
- **Arreglo:** usar claves `globalsearch.accion_*` en es/en/zh, filtrar con `puedeAbrir(path, puede)` y usar iconos lucide.

**A3. `frontend/src/components/layout/QuickCreateMenu.tsx:15-26,142-150` — menú «Crear»**
- **Estado:** ✅ arreglado 23-11-2026: textos `quickcreatemenu.accion_*`, «Creando…/Crear tarea» traducidos y cada acción filtrada por la capacidad de su ruta.
- **Evidencia:** `label: 'Nueva factura'`, `'Nuevo contrato'`, `'Auto-planificar tareas IA'`… usados como `ariaLabel`, `title` y texto visible. Ningún filtro por capacidad.
- **Impacto:** textos sin traducir. Un empleado ve «Nueva factura» y «Nuevo riesgo» y acaba en `/403`.
- **Arreglo:** traducir y filtrar cada acción con `puedeAbrir(path, puede)` o con la capacidad de creación.

**A4. `frontend/src/pages/CallPage.tsx:83-85` — credenciales LiveKit**
- **Estado:** ✅ arreglado 23-11-2026: sin fallback a `searchParams`; sin credenciales en sessionStorage se piden a `POST /collaboration/calls/{id}/join` (`collabApi.joinCall`). De paso: las credenciales se leen una vez (estado) y no en cada render (antes se perdían en el segundo render).
- **Evidencia:** `_stored.token || params.get('token')`, y lo mismo con `url` y `room`. El comentario de la línea 75 dice «nunca desde URL».
- **Impacto:** el token puede acabar en el historial, los logs y el Referer. Además, `url` es controlable por un enlace y conectaría el cliente a un servidor LiveKit ajeno.
- **Arreglo:** quitar el fallback a `searchParams` para `token`, `url` y `room`.

**A5. `frontend/src/pages/ChatAdminPage.tsx:233,315,353` — acciones destructivas**
- **Estado:** ✅ arreglado 23-11-2026: purga, liberar legal hold y borrar integración con `openConfirmGlobal({ danger })`; consultas con carga y `EstadoDeError`; errores por el `onError` global de mutaciones.
- **Evidencia:** `onClick={() => run.mutate()}` (purga de retención), `release.mutate(h.id)` (liberar legal hold) y borrado de integración. El fichero no usa ningún confirm y las mutaciones no tienen `onError`. Las 6 queries no tienen estado de carga ni de error.
- **Impacto:** acciones irreversibles o de cumplimiento (RGPD y eDiscovery) con un solo clic y sin aviso si fallan.
- **Arreglo:** `openConfirmGlobal({ danger: true })`, `toast.error` en `onError` y estados de carga y error.

**A6. `file_url` sin validar — `frontend/src/pages/portal-client/PortalAdvancedSections.tsx:1146`, `ClientPortalPage.tsx:878`, `clients/ClientsPageTabs.tsx:883`**
- **Estado:** ✅ arreglado 23-11-2026: backend `EnlaceSeguro` (`app/schemas/_enlaces.py`, solo http/https o rutas propias) en `file_url`, `test_environment`, `test_guide_url`, `receipt_url` y `document_url`; `sanitizeUrl`/`isSafeUrl` en portal externo, ClientPortalPage, ficha del cliente y en Expenses, ESign, Git, MisEquipos, proveedores, Documents y Chat.
- **Evidencia:** `href={doc.file_url}`, que el operador teclea (input en `ClientPortalPage.tsx:897`). En el backend es `file_url: Optional[str] = Field(None, max_length=500)` (`app/api/v1/endpoints/client_portal.py:185`), sin validar el esquema. `sanitizeUrl` (`utils/security.ts:19`) solo se usa en 3 sitios.
- **Impacto:** una URL `javascript:` o `data:` guardada llega al portal externo del cliente. La explotabilidad depende del navegador, porque `target=_blank` la mitiga, pero es un vector almacenado que cruza de operador a cliente.
- **Arreglo:** validar `http(s)` en el esquema del backend y envolver en `sanitizeUrl` todos los `href` de datos.
- **Mismo patrón (media):** `ExpensesPage.tsx:149,405`, `ESignPage.tsx:383`, `GitPage.tsx:131`, `MisEquiposPage.tsx:298`, `proveedores/PestanaCumplimiento.tsx:265`, `proveedores/PestanaPaquetes.tsx:272`, `DocumentsPage.tsx:279,348,894…` y `ChatPage.tsx:1645,1935`.

**A7. `frontend/src/pages/DemandaPage.tsx:237` — botón «Configurar»**
- **Estado:** ✅ arreglado 23-11-2026: sin botón; aviso contextual cuando no hay tipos de solicitud con `<Link to="/settings/demanda">` solo con `demanda.config`.
- **Evidencia:** `<Button variant="secondary" icon={<Settings/>} onClick={() => navigate('/settings/demanda')}>{t('demanda.configurar')}</Button>`.
- **Impacto:** incumple la regla «los módulos no tienen botón Configurar». Es el único caso encontrado: Ausencias, Horas extra, Cartera, Git, Service desk, Reuniones, Proveedores y Asignación IA ya redirigen o usan aviso contextual.
- **Arreglo:** sustituirlo por un aviso contextual (por ejemplo, cuando no hay tipos de solicitud) con `<Link>` condicionado a `puede('demanda.config')`, como `proveedores/comunes.tsx:65-71`.

**A8. Colisiones de `queryKey`**
- **Estado:** ✅ arreglado 23-11-2026: `hooks/useListas.ts` (`useListaDeProyectos`/`useListaDeUsuarios`, params en la clave) en todas las páginas citadas; `['integrations']` → `['chat-admin','integraciones']` y `['oauth-integraciones']`. `['audit']`/`['webhooks']`: ✅ medido 23-11-2026 (segunda ronda): solo las usaba `ChatAdminPage`, sin colisión real; renombradas a `['chat-admin','auditoria']` y `['chat-admin','webhooks']`.
- **Evidencia:**
  - `['integrations']` lo usan `ChatAdminPage.tsx:204` (collabApi) y `EnterprisePage.tsx:382` (oauthIntegrationsApi), con datos de distinta forma. `['audit']` y `['webhooks']` son igual de genéricas.
  - `['projects']` aparece en ≥16 páginas con `queryFn` distintos: Epics:267, EpicGantt:219, Dependencies:242, CumulativeFlow:58, Contracts:120, Expenses:229/619, Automations:198, Capacity:123, Deliverables:171, Budgets:167, Changelog:259, Changes:369, ContractsAI:208, ClientPortal:1014, CustomFields:172 y WikiPage:505 (este con `.catch(()=>[])`).
- **Impacto:** react-query comparte la caché. Una pantalla recibe datos con la forma de otra, o un `[]` cacheado por un error tragado en otra página.
- **Arreglo:** usar claves con prefijo de módulo o `constants/queryKeys`, y un hook único `useProyectos()`.

**A9. Errores tragados en 46 ficheros**
- **Estado:** ✅ arreglado 23-11-2026: unos 135 `catch` tragados quitados o convertidos en aviso (`EstadoDeError` en consultas, `toast.error(extractErr)` en acciones); los que quedan son accesorios (presencia, sockets, almacenamiento, telemetría) y llevan `/* accesorio: … */`.
- **Evidencia:** 118 `catch {}` o `.catch(() => [] | null | {})`. Los que más: CallPage 11, DataPlatformPage 8, WikiPage 8 (líneas 157, 390, 394, 505, 508, 512, 513, 528), ReportsPage 6 (613, 829, 865), TasksPage 6 (347, 419, 425, 431, 476, 1580), BIProjectDetailPage 5, DataGovernancePage 5, CalendarPage 4 y PerformanceReviewsPage 4 (1169, 1242, 1984, 1988).
- **Impacto:** un fallo del servidor o un 403 se muestra como «no hay datos». El usuario no sabe que algo falla y la caché guarda el vacío.
- **Arreglo:** dejar que la query falle y pintar `isError` con reintento. El `.catch` solo es aceptable en llamadas de presencia o telemetría.

### Media

**M1. `frontend/src/App.tsx:280` + `pages/LoginPage.tsx:258` — se pierde el enlace profundo**
- **Estado:** ✅ arreglado 23-11-2026: `ProtectedRoute` guarda la ruta (`utils/destinoTrasLogin.ts`, solo internas) y el login/`/login` vuelven a ella; sobrevive al SSO.
- **Evidencia:** `ProtectedRoute` redirige con `<Navigate to="/login" replace />` sin guardar `from`, y el login siempre navega a `paginaDeInicio(...)`.
- **Impacto:** un enlace profundo (correo, notificación, marcador a `/projects/123`) sin sesión acaba en el inicio, no en el destino.
- **Arreglo:** pasar `state={{ from: location }}` y, tras el login, volver a `from` si es una ruta interna (que empiece por `/` y no por `//`) para evitar una redirección abierta.

**M2. `frontend/src/components/layout/Layout.tsx:96-142,674` — sección de las migas**
- **Estado:** ✅ arreglado 23-11-2026: fuera `ROUTE_LABELS` y `ROUTE_SECTION`; rutas fuera del menú con su `nav.group_*`; «Detalle», «Inicio», «Proyecto/Tarea» traducidos.
- **Evidencia:** `ROUTE_SECTION` (`'My Work'`, `'Finance'`, `'Settings'`, `'/projects/:id': 'Detalle de proyecto'`) es el fallback de la sección cuando la ruta no está en el menú (`/calendar`, `/timer`, `/chat`, `/search`, `/esign`, `/client-portal`, `/projects/:id`).
- **Impacto:** literales en inglés o castellano mezclados en la cabecera para operadores zh, es o en.
- **Arreglo:** usar claves `nav.group_*` y añadir el grupo a las rutas fuera del menú.

**M3. `frontend/src/components/layout/NexusAssistPanel.tsx:48-55`**
- **Estado:** ✅ arreglado 23-11-2026: etiqueta con `nav.<ruta>`.
- **Evidencia:** `PAGE_LABELS` con `'Proyectos'`, `'Tareas'`, `'Imputaciones'`… se pintan en la línea 179.
- **Impacto:** sin traducir.
- **Arreglo:** reutilizar `getNavLabel`.

**M4. `frontend/src/pages/service-desk/QueueAndRoutingSections.tsx:437`, `ALMAltasBajasPage.tsx:314,445`, `DataGovernancePage.tsx:434` — borrados sin confirmar**
- **Estado:** ✅ arreglado 23-11-2026: regla de enrutado, altas/bajas ALM, marcador de DataGovernance y el resto de borrados de los ficheros revisados piden confirmación del kit.
- **Evidencia:** `onClick={() => deleteRule(rule.id)}`, `borrar.mutate(f.id)` y `biBookmarksApi.delete(bm.id)`, sin confirmación.
- **Impacto:** se borra con un clic (reglas de enrutado de tickets, filas de altas y bajas, marcadores).
- **Arreglo:** usar `openConfirmGlobal`.
- **Contexto medido:** 113 ficheros con `useMutation` y sin ningún confirm del kit. No todos borran, así que hace falta revisarlos uno a uno (sin verificar).

**M5. Controles nativos en vez del kit**
- **Estado:** ✅ arreglado 23-11-2026: inputs/textarea nativos migrados al kit; `node scripts/kit_pendientes.mjs --comprobar` sale 0 (pendientes del cupo `contec/sin-input-nativo`: 295 en 108 ficheros → 0).
- **Evidencia:** en 69 ficheros hay 206 `<input>` y en 15 ficheros 23 `<textarea>`. Unos 180 no son `file`, `color`, `range`, `checkbox` o `radio`. Los que más: ALMPage 23, service-desk/ConfigTab 20, SettingsPageSections 12, OrganizationsPage 11, ContractsPage 8, GrcPage 7, ChatPage 7, DataGovernancePage 6, ClientPortalPage 6, LoginPage 5, TimesheetsPage 4 y ChangesPage 4. Ejemplo: `ConfigTab.tsx:229,346,358,601,606,630`, que usan `className={IS}` con label manual.
- **Impacto:** incumple la regla del kit. Los estilos, la validación (`useErroresDeCampo`) y la accesibilidad quedan duplicados a mano.
- **Arreglo:** migrar a `Input` y `Textarea`, empezando por los ficheros con más casos.

**M6. `frontend/src/pages/CalendarPage.tsx:77-122`, `DataPlatformPage.tsx:42-100`, `BIPage.tsx`, `BIProjectDetailPage.tsx:130-185`, `AgentDashboardPage.tsx` — estados de carga y error**
- **Estado:** ✅ arreglado 23-11-2026: Calendar, DataPlatform, BIProjectDetail, AgentDashboard con `EstadoDeError`; snapshots de DataPlatform avisan.
- **Evidencia:** queries sin `isLoading`/`isError` y con `.catch(()=>[])`. En DataPlatform, `catch (_) { /* ignore */ }` en crear y comparar snapshots.
- **Impacto:** pantallas vacías ambiguas y acciones que fallan en silencio.
- **Arreglo:** usar `EmptyState`, `ErrorState` y `toast.error`.

**M7. `frontend/src/pages/ESignPage.tsx:264-266` y `pages/service-desk/ConfigCorreoEntrante.tsx:66` — navegación con recarga**
- **Estado:** ✅ arreglado 23-11-2026: ESign con `<Link>` y `puede('org.administrar')`; ConfigCorreoEntrante con `navigate`; UserProfilePanel a `/settings/mfa`; Imputar con `<Link to="/timer">`.
- **Evidencia:** `window.location.href = '/settings/esign'` y `= '/settings/integrations'`. Lo mismo en `components/layout/UserProfilePanel.tsx:444` (`'/mfa'`, que además redirige a `/settings/mfa`) y en `pages/ImputarPage.tsx:388` (`<a href="/timer">`).
- **Impacto:** recarga completa de la SPA, se pierde el estado y la caché, y hay un parpadeo. El aviso de ESign se muestra sin `puede()`.
- **Arreglo:** usar `<Link>` o `navigate` hacia la ruta final y condicionar a la capacidad.

**M8. `frontend/src/components/layout/Layout.tsx:1024`**
- **Estado:** ✅ arreglado 23-11-2026: directo a `/settings/organizations` (recarga completa a propósito: cambia la sesión).
- **Evidencia:** `salirDeSuplantacion` termina con `window.location.href = '/organizations'`, que redirige a `/settings/organizations`.
- **Impacto:** funciona para el superadmin, pero depende de una ruta antigua y de dos redirecciones.
- **Arreglo:** ir directamente a `/settings/organizations`.

**M9. `frontend/src/pages/OrganizationsPage.tsx:99-103`**
- **Estado:** ✅ arreglado 23-11-2026: mensaje por `response.data.code` (`usuario_ultima_empresa`, `empresa_ultimo_usuario`) o `extractErr`.
- **Evidencia:** decide el mensaje buscando `'última organización'` o `'último usuario'` en el texto del error del servidor.
- **Impacto:** se rompe si cambia el idioma o la redacción del backend.
- **Arreglo:** usar el `code` estable del error.

**M10. `frontend/src/pages/DataPlatformPage.tsx:32,35`, `DataGovernancePage.tsx:78` — cadenas mágicas**
- **Estado:** ✅ arreglado 23-11-2026: preset del primero recibido y constantes con nombre (`DATASET_POR_DEFECTO`, `PANEL_BI_COMPARTIDO`).
- **Evidencia:** `'ops_delivery_mix'`, `'olap.fact_projects'` y `dashboard_key: 'executive'`.
- **Impacto:** fallo silencioso si el backend renombra el preset.
- **Arreglo:** usar constantes compartidas o el primer preset recibido.

**M11. `frontend/src/pages/BIProjectDetailPage.tsx:80-98` — impresión**
- **Estado:** ✅ arreglado 23-11-2026 (segunda ronda): sin ventana nueva ni `document.write`; se imprime el nodo en la propia página con `@media print` (`body.bi-imprimiendo`, `BIProjectDetailPage.css`) y color `var(--text-1)`.
- **Evidencia:** `w.document.write(...node.outerHTML...)` en una ventana nueva y `color:#111` fijo.
- **Impacto:** se reinyecta el DOM propio (riesgo bajo) y el color está fuera de token.
- **Arreglo:** usar `@media print` o un iframe aislado, y un token de color.

**M12. Componentes enormes**
- **Estado:** ✅ arreglado 23-11-2026 (segunda ronda), sin cambio de comportamiento y con los mismos exports. Medido (líneas antes → después del principal): PerformanceReviews 2130→222, Chat 2012→259, Tasks 1816→572, Approvals 1654→310, ALM 1656→119, SettingsPageSections 1532→39, Documents 1462→283, Reports 1232→267, ConfigTab 1185→82, Grc 1136→72, WorkflowDesigner 1125→73, ClientsPageTabs 1096→15, Subcontractors 1091→276, Enterprise 1072→77, ClientPortal 1053→71, AIHub 1033→479, SettingsAdvancedSections 1025→344, CMDB 944→396, TicketDetail 941→548, PortalAdvancedSections 1338→17, PortalDashboard 903→653, PortalUI 875→467, PortalSupportDesk 839→686, GovernedConversations 824→357. Ningún fichero nuevo pasa de 800 (el mayor, `evaluaciones/Campanas360.tsx`, 656). ✅ 23-11-2026 (tercera ronda): `ProjectsPage` 1237→255 (con `contract_amount` del alta y edición), en `pages/proyectos/`: `compartido.tsx` 170, `TarjetaDeProyecto` 109, `FormularioDeProyecto` 251, `DetalleDeProyecto` 361, `PlantillasDeProyecto` 153 y `GanttConDependencias` 20. Fuera: `bpm/catalogo/estructura.ts`, que son datos, no un componente.
- **Evidencia:** 25 ficheros de más de 800 líneas: PerformanceReviewsPage 2.131, ChatPage 2.013, TasksPage 1.817, ALMPage 1.657, ApprovalsPage 1.655, SettingsPageSections 1.533, DocumentsPage 1.463, PortalAdvancedSections 1.335, ReportsPage 1.233, ProjectsPage 1.227, ConfigTab 1.208, GrcPage 1.136, WorkflowDesignerPage 1.120, SubcontractorsPage 1.095, ClientsPageTabs 1.092, EnterprisePage 1.077, ClientPortalPage 1.061, bpm/catalogo/estructura.ts 1.056 (datos), SettingsAdvancedSections 1.048, AIHubPage 1.035, CMDBPage 945, TicketDetail 940, PortalDashboard 896, PortalUI 887 y PortalSupportDesk 840.
- **Impacto:** mantenibilidad, revisiones y tiempo de carga del chunk.
- **Arreglo:** trocear por pestaña o subcomponente.

**M13. `style={{…}}` inline**
- **Estado:** ✅ verificado 23-11-2026 (segunda ronda): la regla `contec/solo-variables-css-en-style` (error) y el test `estilosEnLinea` ya solo admiten custom properties; en los 24 ficheros troceados no quedaba ningún `style` constante (todos `'--x': dato`). Lo que queda (424 en 124 ficheros, medido) son colores y medidas de datos, el patrón aceptado.
- **Evidencia:** 289 apariciones en 72 ficheros. Los que más: ResourceSchedulerPage 22, GrcPage 14, ProjectsPage 14, ClientsPageTabs 13, PerformanceReviewsPage 13, PortalUI 13, DocumentsPage 12 y DependenciesPage 11. Muchos son custom properties para colores de datos, que es un patrón aceptado; el resto, sin verificar.
- **Impacto:** estilos fuera de las hojas y de los tokens.
- **Arreglo:** revisar y dejar solo `--var` de datos.

**M14. Colores en TSX/JS fuera de tokens**
- **Estado:** ✅ arreglado 23-11-2026 (segunda ronda): `rgba` del portal (PortalUI, PortalDashboard, portalClientContext) y de LoginPage a tokens (`--warning-bg`…, `--on-dark-faint-xs`); degradados del Avatar del kit a `--avatar-fin-*`; hex por defecto a `constants/theme.ts` (`COLOR_DATO_POR_DEFECTO` en IssueTypes, `COLOR_CATEGORIA_POR_DEFECTO` en ConfigTab, `MARCA_POR_DEFECTO` en MarcaSection, `PALETA_DE_ACENTO`/`ACENTO_POR_DEFECTO` del perfil). Medido: fuera de `constants/theme.ts` y `charts/useChartTheme.ts` quedan 0 hex/rgba en TS/TSX salvo el valor `PALETTE[0]` de informes (dato de `<input type="color">`).
- **Evidencia:** `portal-client/PortalUI.tsx` tiene 6 `rgba(`, `PortalDashboard.tsx` 2, `portalClientContext.tsx` 1 y `LoginPage.tsx` 1. Hay hex por defecto en `IssueTypesPage.tsx:49` (`'#7a8aaa'`), `ReportsPage.tsx:587` y `service-desk/ConfigTab.tsx:221` (`'#4f8ef7'`), y `MarcaSection.tsx:69` (`'#1f2937'`, `'#ffffff'`). Los de marca y selector de color son legítimos.
- **Impacto:** el tema oscuro y el de marca no se aplican en esos puntos.
- **Arreglo:** usar tokens `var(--…)` o constantes de paleta de datos.

**M15. 21 páginas llaman a `api.get/post` directamente**
- **Estado:** ✅ arreglado 23-11-2026 (segunda ronda): 36 llamadas en 13 ficheros pasan a servicios (`services/api/pantallasSueltas.ts`: `solicitudesDeFirmaApi`, `reservasApi`, `changelogApi`, `raciApi`, `puntuacionesDeRiesgoApi`, `aprobacionPorCorreoApi`, `preferenciasDeAvisosApi`, `armazonApi`; y `avisosApi.listar`, `wsApi.ticket`, `pipelineApi.list`, `nexusAgentApi.texto`, `usersApi.preferencias`). ✅ 23-11-2026 (tercera ronda): las 3 de `components/security/EstadoDeCuenta.tsx` pasan a `seguridadApi.cambiarContrasena` y `seguridadApi.yo` (`services/api/seguridadDeCuentas.ts`).
- **Evidencia:** por ejemplo `ESignPage.tsx:140,225,230,234,242`, `ChangelogPage` y `AprobacionPorCorreoPage`, en vez de servicios en `services/api/*`.
- **Impacto:** las rutas y los tipos están dispersos (el error de C1 habría salido tipando el servicio).
- **Arreglo:** mover las llamadas a servicios tipados.

**M16. `frontend/src/permisos/navegacion.ts:48,63,33` — capacidades por ruta poco coherentes con el menú**
- **Estado:** ✅ arreglado 23-11-2026 (segunda ronda), contrastado con `app/core/capacidades.py` y las guardas: `/bpm` → `bpm.usar` (API BPMN: `bpm.usar`/`bpm.gestionar`), `/agent-dashboard` → `cmdb.gestionar` (`GET /cmdb/agent-dashboard/{id}` lo exige; con `cmdb.ver` abría y daba 403), `/portfolio/intake` → `cartera.usar` (API del intake). `/reports` se queda en `colaboracion.ver`: su API (`/analytics/catalogue|query`) la abre cualquiera con sesión y la pestaña de programados ya pide `informes.programar`. Documentado en `permisos/navegacion.ts`; test `rutasConCapacidadDeSuApi.test.ts`.
- **Evidencia:** `/bpm` (grupo «IA y automatización») pide `recursos.prevision`. `/agent-dashboard` (Soporte) pide `cmdb.ver` y no `sd.*`. `/reports` y `/portfolio/intake` (grupo Analítica) piden `colaboracion.ver`.
- **Impacto:** sin verificar si es intencionado. Los agentes de service desk sin `cmdb.ver` no verían su panel.
- **Arreglo:** contrastar con `app/core/capacidades.py` y con las guardas de esos endpoints.

**M17. `frontend/src/pages/ESignPage.tsx:225-245`**
- **Estado:** ✅ arreglado 23-11-2026: lista con `EstadoDeError`; `voidEnv`/`markSigned` avisan por el `onError` global; enlace de configuración condicionado a `puede()`.
- **Evidencia:** las queries no tratan `isError` y las mutaciones `voidEnv` y `markSigned` no tienen `onError`. La página no usa `puede()`.
- **Impacto:** fallos silenciosos.
- **Arreglo:** añadir `onError` con toast.

### Baja

**B1. `frontend/src/components/layout/Layout.tsx:43-94`**
- **Estado:** ✅ arreglado 23-11-2026: podadas las tablas de rutas retiradas (`ROUTE_LABELS`, `ROUTE_SECTION`).
- **Evidencia:** `ROUTE_LABELS` contiene ~20 rutas que ya no existen como página: `/rate-cards`, `/ai-hub`, `/issue-types`, `/m365`, `/governance`, `/grc`, `/organizations`, `/enterprise`, `/webhook-log`, `/jira-integration`, `/project-templates`, `/public-forms`, `/developer`, `/sla-calendars`, `/custom-fields`, `/project-permissions`, `/mfa` e `/import`. Lo mismo en `PATH_NAV_KEY` (`/kanban`, `/ai-hub`…).
- **Impacto:** código muerto y fallbacks en inglés.
- **Arreglo:** podar.

**B2. `frontend/src/components/layout/Layout.tsx:857`**
- **Estado:** ✅ arreglado 23-11-2026: sin fallback literal.
- **Evidencia:** fallback `'Cerrar sesión'` si `t` no existe.
- **Impacto:** mínimo.
- **Arreglo:** eliminar el fallback.

**B3. `frontend/src/components/layout/Layout.tsx:945,972`**
- **Estado:** ✅ arreglado 23-11-2026: try/catch en Layout, PortalDashboard, PortalUI y PortalClientePage.
- **Evidencia:** `localStorage.getItem/setItem(NAV_WORKSPACE_KEY)` sin `try/catch`. También en `PortalDashboard.tsx:173,184,199,280,452`, `PortalUI.tsx:120,125` y `PortalClientePage.tsx:278-282,475-480`.
- **Impacto:** con el almacenamiento bloqueado (modo privado o política) la pantalla lanza una excepción.
- **Arreglo:** envolver en `try/catch`, como ya se hace en `ServiceDeskPage.tsx:62`.

**B4. `frontend/src/App.tsx:237-241`**
- **Estado:** ✅ arreglado 23-11-2026: «Ir al inicio» (`/`) en vez de «Ir a login».
- **Evidencia:** el error de render de cualquier página ofrece como acción principal «Ir al login» (`window.location.href = '/login'`).
- **Impacto:** confuso con la sesión abierta (el login redirige al inicio).
- **Arreglo:** usar «Volver al inicio» o `navigate(-1)` y dejar «Recargar» como secundaria.

**B5. `frontend/src/App.tsx:192`**
- **Estado:** ✅ arreglado 23-11-2026 (segunda ronda): fuera el `<style>`; `@keyframes spin` ya estaba en `index.css`.
- **Evidencia:** `<style>{'@keyframes spin…'}</style>` inyectado en cada `PageLoader`.
- **Impacto:** estilo inline repetido.
- **Arreglo:** moverlo a `App.estilos.css`.

**B6. `frontend/src/pages/SemanticEnginePage.tsx:14`**
- **Estado:** ✅ arreglado 23-11-2026: comentario corregido.
- **Evidencia:** el comentario dice que hay «el botón «Configurar» para quien tiene `ia.asignacion_config`», pero en el código no existe (solo la redirección de `?tab=config`, línea 268).
- **Impacto:** la documentación interna está desfasada.
- **Arreglo:** corregir el comentario.

**B7. `frontend/src/pages/service-desk/WorkflowDesignerPage.tsx:992,1015`**
- **Estado:** ✅ arreglado 23-11-2026: placeholders traducidos.
- **Evidencia:** `placeholder="manager"` y `placeholder="support"`, sin traducir.
- **Impacto:** mínimo.
- **Arreglo:** pasarlos a i18n.

**B8. `frontend/src/pages/ChatAdminPage.tsx:385-388`, `ESignPage.tsx:176`**
- **Estado:** ✅ arreglado 23-11-2026 (segunda ronda): «Service Desk» traducido (`chat_admin.integracion_service_desk`, es/en/zh); Google Calendar, Microsoft 365, Nexus AI y Adobe Sign se quedan como nombres propios.
- **Evidencia:** `<option>` con marcas literales («Google Calendar», «Service Desk», «Nexus AI», «Adobe Sign»).
- **Impacto:** son nombres propios, aceptable. «Service Desk» sí debería traducirse.
- **Arreglo:** pasar a i18n lo que no sea marca.

**B9. TODO pendientes**
- **Estado:** ✅ cerrado 23-11-2026 (segunda ronda): los `// TODO type:` citados eran restos de la migración a TS (los tipos ya están declarados al lado); retirados en BIProjectDetail, NotFound, PortalPublicView, GlobalSearch, QuickCreateMenu, Layout, main y App. El de AIHub (`queryKeys`) se retira: la clave `['ai-governance', …]` ya tiene prefijo de módulo.
- **Evidencia:** `AIHubPage.tsx:378`, `BIProjectDetailPage.tsx:108`, `NotFoundPage.tsx:2`, `PortalPublicViewPage.tsx:17`, y en layout `GlobalSearch.tsx:36`, `QuickCreateMenu.tsx:29`, `App.tsx:201` y `Layout.tsx:313,343`.
- **Impacto:** tipado pendiente.
- **Arreglo:** cerrarlos.

**B10. `frontend/src/pages/ChatPage.tsx:1167-1174`**
- **Estado:** ✅ arreglado 23-11-2026: si `window.open` falla se borran las credenciales y se avisa (`chat.err_call_popup`).
- **Evidencia:** credenciales de llamada en `sessionStorage` para la ventana hija.
- **Impacto:** si `window.open` falla, no se limpian.
- **Arreglo:** limpiarlas cuando la apertura falle.

**B11. `frontend/src/pages/BPMPage.tsx:100`**
- **Estado:** ✅ arreglado 23-11-2026: `toast.error(extractErr)`.
- **Evidencia:** `console.error('BPMN import error:', err)`.
- **Impacto:** ruido en consola sin feedback al usuario.
- **Arreglo:** usar logger y toast.

**B12. `frontend/src/services/api/_core.ts:940-942`**
- **Estado:** ✅ arreglado 23-11-2026 (segunda ronda): las 13 rutas `epics/wiki/...` de `_core.ts` con `/` inicial.
- **Evidencia:** `wikiApi.portal*` usa rutas sin `/` inicial (`'epics/wiki/...'`).
- **Impacto:** funciona, pero es incoherente.
- **Arreglo:** añadir la `/` inicial.

## Código muerto

| Elemento | Evidencia | Acción |
|---|---|---|
| `/client-portal` → ClientPortalPage.tsx (1.061 líneas) | Sin entrada de menú ni enlace entrante en `src/` | Enlazar o retirar (A1) |
| `/esign` → ESignPage.tsx (403 líneas) | Sin entrada de menú ni enlace. La sección `/settings/esign` existe, pero no enlaza a la página | Enlazar o retirar, y arreglar C1 |
| `/search` → SearchPage.tsx (298 líneas) | Solo se llega por la redirección `/fts-search`. La paleta ⌘K no tiene «ver todos los resultados» hacia `/search` (sin verificar en detalle) | Enlazar desde GlobalSearch |
| Entradas de `ROUTE_LABELS`, `ROUTE_SECTION` y `PATH_NAV_KEY` de rutas retiradas | `Layout.tsx:43-170` (B1) | Podar |
| Rutas de redirección legacy | `/bi*`, `/workflows`, `/settings/workflows`, `/kanban-advanced`, `/mentions`, `/notifications`, `/fts-search`, `/wiki-tags`, `/chat/admin` y las `rutaAntigua` del catálogo | Mantener (marcadores). Revisar su uso con métricas de acceso (sin verificar) |
| Páginas sin ruta propia montadas en Ajustes | `catalogoDeAjustes.tsx:88-186` monta Organizations, ProjectTemplates, IssueTypes, Workflows, ProjectPermissions, SLACalendars, RateCards, UserCosts, Politicas, AIHub, Governance, M365, Jira, Enterprise, WebhookLog, DeveloperPortal, Import, MFA, Grc, ChatAdmin y PublicForms. MentionsPage y NotificationsPage las monta InboxPage | **No son código muerto** (verificado) |

Rutas fuera del menú pero **enlazadas** (no son huérfanas): `/calendar` y `/timer` (iconos de la cabecera, `Layout.tsx:807-814`), `/imputar` (QuickCreate y WorkDashboard), `/timesheets` (WorkDashboard:314), `/chat` (`Layout.tsx:1182` y panel de chat), `/contracts-ai` (`ProjectDetailPage.tsx:471`), `/chat/call/:id` (`ChatPage.tsx:1174`), `/sd/workflow-designer` (sección `sd-workflows` de Ajustes) y `/projects/:id` y `/projects/:id/analytics` (desde las listas).

## Hardcode

| Tipo | Medida | Dónde |
|---|---|---|
| Textos visibles sin traducir en el armazón | 3 componentes | `GlobalSearch.tsx:25-34` (8 acciones con su pista), `QuickCreateMenu.tsx:15-26` (10 acciones), `NexusAssistPanel.tsx:48-55` (16 etiquetas) y `Layout.tsx:96-142` (secciones en inglés como fallback de las migas) |
| Textos visibles sin traducir en pages | casi 0 | El script de literales en JSX y atributos (`placeholder`, `title`, `aria-label`, `label`) da 2 placeholders (B7) y 4 `<option>` de marcas (B8). `SettingsAdvancedSections.tsx:739-770` lleva literales en castellano solo como fallback de `t('settingsadvanced.rt_*')`, con las 58 claves presentes en es/en/zh |
| Mensajes del servidor interpretados por texto | 1 | `OrganizationsPage.tsx:99-103` (M9) |
| Colores fuera de tokens | 0 en los 155 CSS; 10 `rgba` y 6 hex en TSX | M14 |
| Cadenas mágicas de negocio | 3 | `DataPlatformPage.tsx:32,35` y `DataGovernancePage.tsx:78` (M10) |
| URLs absolutas | 22 en 8 ficheros | Casi todas son plantillas OIDC de ejemplo (`EnterprisePage.tsx:861-864`), namespaces BPMN (`BPMPage.tsx`, `bpm/generadorBpmn.ts`), enlaces de documentación de proveedores IA (`AIHubPage`) y de M365. Ninguna apunta a un backend fijo |
| Idiomas | sin hardcode | El portal usa `PORTAL_LANGUAGES` (8 idiomas) y el operador usa es/en/zh. El portal cae a `'es'` si no hay preferencia (`PortalClientePage.tsx:478`), que es aceptable |
| Estados como cadenas | extendido; sin verificar uno a uno | Por ejemplo, `PipelinePage.tsx:359` `['lost','cancelled'].includes(...)` y `GitPage.tsx:78-81` `'open'`, `'merged'`, `'success'`, `'failure'`. Las etiquetas sí salen de i18n (`pipeline.stage_*`) |

## Diseño y usabilidad

- **Configuración centralizada: cumple salvo A7.** Cada módulo que tenía «Configurar» redirige `?tab=config` a `/settings/<id>`: Ausencias:61, HorasExtra:48, Cartera:46, Git:95, ServiceDesk:150 y SemanticEngine:268. Los avisos contextuales enlazan con capacidad (`MeetingsAIPage.tsx:121`, `ExpensesPage.tsx:749`, `proveedores/comunes.tsx:71`, `alm/uso/RecuperacionPanel.tsx:141`). `GitPage.tsx:86` muestra «Conectar repositorios» solo con datos vacíos y con permiso (`configura`): es un aviso contextual, válido.
- **Permisos en pantalla.** 33 de 127 `*Page.tsx` usan `puede()`/`usePermiso`. El resto se apoya en la ruta y en el backend. Sin verificar botón a botón si se ofrecen acciones que acabarán en 403; QuickCreate y GlobalSearch sí lo hacen (A2 y A3).
- **Kanban + lista.** Hay vista doble en Tareas (`/tasks?view=kanban`), Service desk (`ServiceDeskPage.tsx:62`, recordada), Riesgos (`ViewToggle`), Proyectos, Demanda, Epics, UAT y Subcontratistas. Sin verificar si Pipeline (columnas por etapa), Sprints (tablero), Cambios y Entregables ofrecen también la lista.
- **Carga, vacío y error.** Hay un patrón de kit (`EmptyState`, `Spinner`, `Skeletons` por tipo de ruta en `App.tsx:163-186`), pero 118 errores tragados (A9) lo anulan en 46 ficheros.
- **Accesibilidad.** El armazón tiene skip link (`Layout.tsx:1028`), diálogo de atajos con trampa de foco y `aria-modal` (`Layout.tsx:382-426`), `aria-live` en el banner offline (`App.tsx:643`) y atajos ⌘/Ctrl según la plataforma. Los inputs nativos llevan casi todos `label htmlFor` y `aria-labelledby` (muestreo en ConfigTab y Organizations). El contraste por clases y el foco visible no se verificaron.
- **Confirmaciones.** Hay 55 usos de confirm del kit en pages y ningún `confirm()` nativo. Faltan confirmaciones en A5 y M4.
- **Navegación.** El menú tiene 83 entradas en 8 grupos más el filtro por «espacio de trabajo» (`Layout.tsx:174-185`). Grupos muy largos: Analítica 16, Proyectos 19, Clientes y finanzas 13. Valorar si conviene agrupar o plegar (opinión, no defecto).
- **Rutas públicas.** `/login`, `/reset-password`, `/approvals/decide` (token firmado), `/portal`, `/portal/view/:token`, `/intake/:token` y `*`. Sus endpoints existen (`/forms/public/{token}`, `/portal/view/{token}`, `/approvals/email-decision`). El token del portal no se guarda en `localStorage`: solo `client_user` como pista de sesión, y la sesión va por cookie (`portalClientContext.tsx:265-309`). La Referrer-Policy de las páginas con token en la URL queda sin verificar.

## Sin verificar (pendiente)

- Lectura línea a línea de las páginas raíz F–Z y de las subcarpetas (solo métricas y comprobaciones dirigidas).
- Paridad de todas las claves i18n de las páginas en es/en/zh. Solo se comprobaron las del menú, las del portal y las `rt_*`.
- Contraste, foco visible y comportamiento visual real (no se ejecutó la app).
- Si las capacidades por ruta de M16 son intencionadas.
- Que `file_url` y `receipt_url` se validen en otros esquemas del backend aparte de `client_portal.py:185`.

## Estado de los arreglos (23-11-2026)

Cada hallazgo de arriba lleva su línea **Estado** (✅ arreglado / ⏸ pendiente). Tablas:
- **Código muerto:** `/client-portal` y `/esign` enlazados en el menú (A1); `ROUTE_LABELS`/`ROUTE_SECTION` podados (B1). `/search` ✅ enlazado desde la paleta (segunda ronda).
- **Hardcode:** acciones rápidas, migas y NexusAssist traducidos (A2, A3, M2, M3); mensaje por código en Organizaciones (M9); cadenas mágicas de BI con constantes (M10). Colores en TSX (M14) ✅ (segunda ronda). Estados como cadena del Pipeline ✅ (constantes `constants/pipelineStages.ts`, segunda ronda).
- **Medición final:** `npx tsc --noEmit -p .` sin errores; ESLint `--quiet` limpio en los 229 ficheros tocados; `node scripts/kit_pendientes.mjs --comprobar` sale 0 y el cupo `contec/sin-input-nativo` queda en 0 (de 295 en 108 ficheros).
- **Segunda ronda (23-11-2026):** ninguna fila queda sin estado. Verificación medida: `npx eslint --quiet` de los ficheros tocados 0 errores; `node scripts/kit_pendientes.mjs --comprobar` sale 0; reglas `jsx-a11y` en error con 0 avisos en `src` (pasada solo de accesibilidad). Typecheck y tests: los pasa el coordinador al final (lista en el informe de la ronda).
