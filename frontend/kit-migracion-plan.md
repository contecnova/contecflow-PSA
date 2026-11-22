# Migración al kit — plan de la fase 2

> Generado por `node scripts/kit_pendientes.mjs` a partir de `kit-pendientes.json`. No se edita a mano:
> al terminar un fichero, se vuelve a ejecutar el script (encoge la lista y rehace este plan).

Cada fichero tiene un cupo de incumplimientos por regla (lo que tenía al crear la lista). ESLint y el test
`kitCssSinRestos` fallan si un fichero supera su cupo o si aparece en un fichero que no está en la lista.
Objetivo: dejar cada fichero a 0 y que salga de la lista. Piezas y cuándo usarlas: `src/components/ui/DESIGN_SYSTEM.md`, «Migración al kit».

## Recuento total

| Regla | Incumplimientos | Ficheros |
|---|---:|---:|
| `contec/sin-boton-nativo` | 0 | 0 |
| `contec/sin-tabla-propia` | 0 | 0 |
| `contec/sin-select-nativo` | 0 | 0 |
| `contec/sin-casilla-suelta` | 0 | 0 |
| `contec/sin-input-nativo` | 295 | 108 |
| `contec/sin-fieldset-propio` | 0 | 0 |
| CSS `mayusculas` | 0 | 0 |
| CSS `monoespaciada` | 0 | 0 |
| CSS `colorLiteral` | 0 | 0 |
| CSS `altoFijoControl` | 0 | 0 |
| **Total** | **295** | **108** |

## Reparto

| Bloque | Ficheros | Incumplimientos |
|---|---:|---:|
| A. Operador A–L | 26 | 92 |
| B. Operador M–Z (incluido service desk) | 38 | 100 |
| C. Portal de clientes, componentes compartidos y Ajustes | 44 | 103 |

Columnas: botón = `<button>`, tabla = `<table>`, select = `<select>`, casilla = checkbox/radio suelto,
fieldset = `<fieldset>` propio, MAYÚS = text-transform, mono = letra monoespaciada, color = hex/rgb literal,
alto px = `height` fijo en un control.

## Bloque A. Operador A–L — 26 ficheros, 92 incumplimientos

| Área | Fichero | botón | tabla | select | casilla | input | fieldset | MAYÚS | mono | color | alto px | Total |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| components/aprobaciones | `components/aprobaciones/DisenadorDeFlujo.tsx` |  |  |  |  | 4 |  |  |  |  |  | 4 |
| components/invoices | `components/invoices/FichaDeFactura.tsx` |  |  |  |  | 2 |  |  |  |  |  | 2 |
| pages/AIHub | `pages/AIHubPage.tsx` |  |  |  |  | 1 |  |  |  |  |  | 1 |
| pages/alm | `pages/alm/uso/FuentesPanel.tsx` |  |  |  |  | 1 |  |  |  |  |  | 1 |
| pages/ALM | `pages/ALMPage.tsx` |  |  |  |  | 23 |  |  |  |  |  | 23 |
| pages/AprobacionPorCorreo | `pages/AprobacionPorCorreoPage.tsx` |  |  |  |  | 1 |  |  |  |  |  | 1 |
| pages/Automations | `pages/AutomationsPage.tsx` |  |  |  |  | 1 |  |  |  |  |  | 1 |
| pages/Call | `pages/CallPage.tsx` |  |  |  |  | 1 |  |  |  |  |  | 1 |
| pages/CarteraIntake | `pages/CarteraIntakePage.tsx` |  |  |  |  | 2 |  |  |  |  |  | 2 |
| pages/Changes | `pages/ChangesPage.tsx` |  |  |  |  | 6 |  |  |  |  |  | 6 |
| pages/Chat | `pages/ChatPage.tsx` |  |  |  |  | 8 |  |  |  |  |  | 8 |
| pages/clients | `pages/clients/ModalEditarContacto.tsx` |  |  |  |  | 1 |  |  |  |  |  | 1 |
| pages/clients | `pages/clients/SelectorContactoPrincipal.tsx` |  |  |  |  | 1 |  |  |  |  |  | 1 |
| pages/Clients | `pages/ClientsPage.tsx` |  |  |  |  | 2 |  |  |  |  |  | 2 |
| pages/Contracts | `pages/ContractsPage.tsx` |  |  |  |  | 8 |  |  |  |  |  | 8 |
| pages/ContractsAI | `pages/ContractsAIPage.tsx` |  |  |  |  | 1 |  |  |  |  |  | 1 |
| pages/CustomFields | `pages/CustomFieldsPage.tsx` |  |  |  |  | 1 |  |  |  |  |  | 1 |
| pages/DataGovernance | `pages/DataGovernancePage.tsx` |  |  |  |  | 6 |  |  |  |  |  | 6 |
| pages/Enterprise | `pages/EnterprisePage.tsx` |  |  |  |  | 1 |  |  |  |  |  | 1 |
| pages/ESign | `pages/ESignPage.tsx` |  |  |  |  | 3 |  |  |  |  |  | 3 |
| pages/Grc | `pages/GrcPage.tsx` |  |  |  |  | 7 |  |  |  |  |  | 7 |
| pages/Imputar | `pages/ImputarPage.tsx` |  |  |  |  | 1 |  |  |  |  |  | 1 |
| pages/IntakeForm | `pages/IntakeFormPage.tsx` |  |  |  |  | 3 |  |  |  |  |  | 3 |
| pages/JiraIntegration | `pages/JiraIntegrationPage.tsx` |  |  |  |  | 1 |  |  |  |  |  | 1 |
| pages/Lecciones | `pages/LeccionesPage.tsx` |  |  |  |  | 1 |  |  |  |  |  | 1 |
| pages/Login | `pages/LoginPage.tsx` |  |  |  |  | 5 |  |  |  |  |  | 5 |

## Bloque B. Operador M–Z (incluido service desk) — 38 ficheros, 100 incumplimientos

| Área | Fichero | botón | tabla | select | casilla | input | fieldset | MAYÚS | mono | color | alto px | Total |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| components/cmdb | `components/cmdb/CmdbMercado.tsx` |  |  |  |  | 1 |  |  |  |  |  | 1 |
| components/servicedesk | `components/servicedesk/ConfigAgenteDeVoz.tsx` |  |  |  |  | 4 |  |  |  |  |  | 4 |
| components/servicedesk | `components/servicedesk/ChangeRolloutPanel.tsx` |  |  |  |  | 2 |  |  |  |  |  | 2 |
| components/servicedesk | `components/servicedesk/BandejaDeCanales.tsx` |  |  |  |  | 1 |  |  |  |  |  | 1 |
| components/servicedesk | `components/servicedesk/Cmdb3dGraph.tsx` |  |  |  |  | 1 |  |  |  |  |  | 1 |
| components/servicedesk | `components/servicedesk/VoiceAgentPanel.tsx` |  |  |  |  | 1 |  |  |  |  |  | 1 |
| pages/M365 | `pages/M365Page.tsx` |  |  |  |  | 1 |  |  |  |  |  | 1 |
| pages/Mentions | `pages/MentionsPage.tsx` |  |  |  |  | 2 |  |  |  |  |  | 2 |
| pages/OKRs | `pages/OKRsPage.tsx` |  |  |  |  | 2 |  |  |  |  |  | 2 |
| pages/Organizations | `pages/OrganizationsPage.tsx` |  |  |  |  | 11 |  |  |  |  |  | 11 |
| pages/OrgChart | `pages/OrgChartPage.tsx` |  |  |  |  | 2 |  |  |  |  |  | 2 |
| pages/PerformanceReviews | `pages/PerformanceReviewsPage.tsx` |  |  |  |  | 2 |  |  |  |  |  | 2 |
| pages/PlanificacionDeRecursos | `pages/PlanificacionDeRecursosPage.tsx` |  |  |  |  | 1 |  |  |  |  |  | 1 |
| pages/PreguntarALaEmpresa | `pages/PreguntarALaEmpresaPage.tsx` |  |  |  |  | 2 |  |  |  |  |  | 2 |
| pages/Projects | `pages/ProjectsPage.tsx` |  |  |  |  | 1 |  |  |  |  |  | 1 |
| pages/ReportBuilder | `pages/ReportBuilderPage.tsx` |  |  |  |  | 1 |  |  |  |  |  | 1 |
| pages/Reports | `pages/ReportsPage.tsx` |  |  |  |  | 1 |  |  |  |  |  | 1 |
| pages/ResetPassword | `pages/ResetPasswordPage.tsx` |  |  |  |  | 1 |  |  |  |  |  | 1 |
| pages/ResourceForecast | `pages/ResourceForecastPage.tsx` |  |  |  |  | 1 |  |  |  |  |  | 1 |
| pages/Resources | `pages/ResourcesPage.tsx` |  |  |  |  | 1 |  |  |  |  |  | 1 |
| pages/ResourceScheduler | `pages/ResourceSchedulerPage.tsx` |  |  |  |  | 1 |  |  |  |  |  | 1 |
| pages/SemanticEngine | `pages/SemanticEnginePage.tsx` |  |  |  |  | 3 |  |  |  |  |  | 3 |
| pages/service-desk | `pages/service-desk/ConfigTab.tsx` |  |  |  |  | 24 |  |  |  |  |  | 24 |
| pages/service-desk | `pages/service-desk/TicketDetail.tsx` |  |  |  |  | 5 |  |  |  |  |  | 5 |
| pages/service-desk | `pages/service-desk/CreateTicketModal.tsx` |  |  |  |  | 4 |  |  |  |  |  | 4 |
| pages/service-desk | `pages/service-desk/ConfigSlaYCiclos.tsx` |  |  |  |  | 2 |  |  |  |  |  | 2 |
| pages/service-desk | `pages/service-desk/WorkflowDesignerPage.tsx` |  |  |  |  | 2 |  |  |  |  |  | 2 |
| pages/service-desk | `pages/service-desk/ConfigCorreoEntrante.tsx` |  |  |  |  | 1 |  |  |  |  |  | 1 |
| pages/service-desk | `pages/service-desk/ConfigGuardiasYMonitor.tsx` |  |  |  |  | 1 |  |  |  |  |  | 1 |
| pages/service-desk | `pages/service-desk/ITSMKnowledgeTab.tsx` |  |  |  |  | 1 |  |  |  |  |  | 1 |
| pages/settings | `pages/settings/CatalogosDeClave.tsx` |  |  |  |  | 2 |  |  |  |  |  | 2 |
| pages/Skills | `pages/SkillsPage.tsx` |  |  |  |  | 2 |  |  |  |  |  | 2 |
| pages/SLACalendars | `pages/SLACalendarsPage.tsx` |  |  |  |  | 1 |  |  |  |  |  | 1 |
| pages/Sprints | `pages/SprintsPage.tsx` |  |  |  |  | 1 |  |  |  |  |  | 1 |
| pages/Subcontractors | `pages/SubcontractorsPage.tsx` |  |  |  |  | 1 |  |  |  |  |  | 1 |
| pages/Tasks | `pages/TasksPage.tsx` |  |  |  |  | 4 |  |  |  |  |  | 4 |
| pages/Timesheets | `pages/TimesheetsPage.tsx` |  |  |  |  | 4 |  |  |  |  |  | 4 |
| pages/Wiki | `pages/WikiPage.tsx` |  |  |  |  | 2 |  |  |  |  |  | 2 |

## Bloque C. Portal de clientes, componentes compartidos y Ajustes — 44 ficheros, 103 incumplimientos

| Área | Fichero | botón | tabla | select | casilla | input | fieldset | MAYÚS | mono | color | alto px | Total |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| components | `components/AIInlineEditor.tsx` |  |  |  |  | 1 |  |  |  |  |  | 1 |
| components | `components/ResourceHeatmap.tsx` |  |  |  |  | 1 |  |  |  |  |  | 1 |
| components | `components/SmartScheduleModal.tsx` |  |  |  |  | 1 |  |  |  |  |  | 1 |
| components/asignacion-ia | `components/asignacion-ia/ConfigMotorSemantico.tsx` |  |  |  |  | 1 |  |  |  |  |  | 1 |
| components/ausencias | `components/ausencias/admin/EditorDeTipos.tsx` |  |  |  |  | 5 |  |  |  |  |  | 5 |
| components/ausencias | `components/ausencias/admin/EditorDeJornadas.tsx` |  |  |  |  | 1 |  |  |  |  |  | 1 |
| components/ausencias | `components/ausencias/admin/EditorDeRotaciones.tsx` |  |  |  |  | 1 |  |  |  |  |  | 1 |
| components/ausencias | `components/ausencias/admin/PersonasYSaldos.tsx` |  |  |  |  | 1 |  |  |  |  |  | 1 |
| components/ausencias | `components/ausencias/BandejaDeAusencias.tsx` |  |  |  |  | 1 |  |  |  |  |  | 1 |
| components/bi | `components/bi/BiGdprPanel.tsx` |  |  |  |  | 5 |  |  |  |  |  | 5 |
| components/bi | `components/bi/BiDashboardCollabPanel.tsx` |  |  |  |  | 2 |  |  |  |  |  | 2 |
| components/bi | `components/bi/BiQueryBuilderPanel.tsx` |  |  |  |  | 2 |  |  |  |  |  | 2 |
| components/bi | `components/bi/AskDataWidget.tsx` |  |  |  |  | 1 |  |  |  |  |  | 1 |
| components/bi | `components/bi/BiEtlPanel.tsx` |  |  |  |  | 1 |  |  |  |  |  | 1 |
| components/bi | `components/bi/SmartAlertsPanel.tsx` |  |  |  |  | 1 |  |  |  |  |  | 1 |
| components/bi | `components/bi/VisualQueryBuilderWidget.tsx` |  |  |  |  | 1 |  |  |  |  |  | 1 |
| components/conectores | `components/conectores/DocumentosDeFicha.tsx` |  |  |  |  | 2 |  |  |  |  |  | 2 |
| components/layout | `components/layout/GlobalChatPanel.tsx` |  |  |  |  | 1 |  |  |  |  |  | 1 |
| components/layout | `components/layout/GlobalSearch.tsx` |  |  |  |  | 1 |  |  |  |  |  | 1 |
| components/layout | `components/layout/NexusAssistPanel.tsx` |  |  |  |  | 1 |  |  |  |  |  | 1 |
| components/planificador | `components/planificador/EditorDeDependencias.tsx` |  |  |  |  | 1 |  |  |  |  |  | 1 |
| components/planificador | `components/planificador/PanelDeLineasBase.tsx` |  |  |  |  | 1 |  |  |  |  |  | 1 |
| components/politicas | `components/politicas/EditorDeResultados.tsx` |  |  |  |  | 6 |  |  |  |  |  | 6 |
| components/politicas | `components/politicas/EditorDePolitica.tsx` |  |  |  |  | 4 |  |  |  |  |  | 4 |
| components/politicas | `components/politicas/comun.tsx` |  |  |  |  | 2 |  |  |  |  |  | 2 |
| components/politicas | `components/politicas/EditorDeExceso.tsx` |  |  |  |  | 2 |  |  |  |  |  | 2 |
| components/politicas | `components/politicas/EditorDeTablas.tsx` |  |  |  |  | 2 |  |  |  |  |  | 2 |
| components/politicas | `components/politicas/ConstructorDeCondiciones.tsx` |  |  |  |  | 1 |  |  |  |  |  | 1 |
| components/politicas | `components/politicas/Simulador.tsx` |  |  |  |  | 1 |  |  |  |  |  | 1 |
| components/portal | `components/portal/GovernedConversations.tsx` |  |  |  |  | 1 |  |  |  |  |  | 1 |
| components/presupuestos | `components/presupuestos/SeguirPresupuesto.tsx` |  |  |  |  | 10 |  |  |  |  |  | 10 |
| components/presupuestos | `components/presupuestos/FichaDePresupuesto.tsx` |  |  |  |  | 5 |  |  |  |  |  | 5 |
| components/presupuestos | `components/presupuestos/CampanasYPlantillas.tsx` |  |  |  |  | 4 |  |  |  |  |  | 4 |
| components/presupuestos | `components/presupuestos/FormularioDePartida.tsx` |  |  |  |  | 1 |  |  |  |  |  | 1 |
| components/security | `components/security/PasskeysSection.tsx` |  |  |  |  | 2 |  |  |  |  |  | 2 |
| context | `context/ConfirmContext.tsx` |  |  |  |  | 1 |  |  |  |  |  | 1 |
| pages/ClientPortal | `pages/ClientPortalPage.tsx` |  |  |  |  | 6 |  |  |  |  |  | 6 |
| pages/portal-client | `pages/portal-client/PortalUI.tsx` |  |  |  |  | 3 |  |  |  |  |  | 3 |
| pages/portal-client | `pages/portal-client/PortalAdvancedSections.tsx` |  |  |  |  | 1 |  |  |  |  |  | 1 |
| pages/portal-client | `pages/portal-client/PortalAIChatWidget.tsx` |  |  |  |  | 1 |  |  |  |  |  | 1 |
| pages/Settings | `pages/SettingsPageSections.tsx` |  |  |  |  | 11 |  |  |  |  |  | 11 |
| pages/settings-sections | `pages/settings-sections/SettingsAdvancedSections.tsx` |  |  |  |  | 4 |  |  |  |  |  | 4 |
| pages/settings-sections | `pages/settings-sections/MarcaSection.tsx` |  |  |  |  | 1 |  |  |  |  |  | 1 |
| pages/settings-sections | `pages/settings-sections/TraduccionSection.tsx` |  |  |  |  | 1 |  |  |  |  |  | 1 |
