# Migración al kit — plan de la fase 2

> Generado por `node scripts/kit_pendientes.mjs` a partir de `kit-pendientes.json`. No se edita a mano:
> al terminar un fichero, se vuelve a ejecutar el script (encoge la lista y rehace este plan).

Cada fichero tiene un cupo de incumplimientos por regla (lo que tenía al crear la lista). ESLint y el test
`kitCssSinRestos` fallan si un fichero supera su cupo o si aparece en un fichero que no está en la lista.
Objetivo: dejar cada fichero a 0 y que salga de la lista. Piezas y cuándo usarlas: `src/components/ui/DESIGN_SYSTEM.md`, «Migración al kit».

## Recuento total

| Regla | Incumplimientos | Ficheros |
|---|---:|---:|
| `contec/sin-boton-nativo` | 476 | 160 |
| `contec/sin-tabla-propia` | 83 | 61 |
| `contec/sin-select-nativo` | 610 | 154 |
| `contec/sin-casilla-suelta` | 159 | 79 |
| `contec/sin-fieldset-propio` | 31 | 18 |
| CSS `mayusculas` | 278 | 124 |
| CSS `monoespaciada` | 187 | 88 |
| CSS `colorLiteral` | 22 | 13 |
| CSS `altoFijoControl` | 45 | 23 |
| **Total** | **1891** | **404** |

## Reparto

| Bloque | Ficheros | Incumplimientos |
|---|---:|---:|
| A. Operador A–L | 124 | 629 |
| B. Operador M–Z (incluido service desk) | 145 | 688 |
| C. Portal de clientes, componentes compartidos y Ajustes | 135 | 574 |

Columnas: botón = `<button>`, tabla = `<table>`, select = `<select>`, casilla = checkbox/radio suelto,
fieldset = `<fieldset>` propio, MAYÚS = text-transform, mono = letra monoespaciada, color = hex/rgb literal,
alto px = `height` fijo en un control.

## Bloque A. Operador A–L — 124 ficheros, 629 incumplimientos

| Área | Fichero | botón | tabla | select | casilla | fieldset | MAYÚS | mono | color | alto px | Total |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| components/alm | `components/alm/AsignarModal.tsx` | 1 |  | 3 |  |  |  |  |  |  | 4 |
| components/alm | `components/alm/almFases.tsx` | 1 |  | 1 | 1 |  |  |  |  |  | 3 |
| components/alm | `components/alm/CerrarAsignacionModal.tsx` | 1 |  | 1 | 1 |  |  |  |  |  | 3 |
| components/alm | `components/alm/FichaActivo.tsx` | 1 |  | 2 |  |  |  |  |  |  | 3 |
| components/alm | `components/alm/almFases.css` |  |  |  |  |  |  | 1 |  | 1 | 2 |
| components/alm | `components/alm/ConfirmarBajaModal.tsx` |  |  |  | 1 |  |  |  |  |  | 1 |
| components/alm | `components/alm/FichaLicencia.tsx` | 1 |  |  |  |  |  |  |  |  | 1 |
| components/aprobaciones | `components/aprobaciones/DisenadorDeFlujo.tsx` | 1 |  | 1 | 1 |  |  |  |  |  | 3 |
| components/aprobaciones | `components/aprobaciones/CondicionesDelFlujo.tsx` |  |  | 2 |  |  |  |  |  |  | 2 |
| components/aprobaciones | `components/aprobaciones/CondicionesSimples.tsx` |  |  | 1 |  | 1 |  |  |  |  | 2 |
| components/externos | `components/externos/FormularioDeExterno.css` |  |  |  |  |  |  | 1 |  |  | 1 |
| components/externos | `components/externos/FormularioDeExterno.tsx` |  |  |  | 1 |  |  |  |  |  | 1 |
| components/flujos | `components/flujos/flujos.css` |  |  |  |  |  | 1 |  | 1 |  | 2 |
| components/gastos | `components/gastos/DetalleDeGasto.tsx` | 1 |  | 3 |  |  |  |  |  |  | 4 |
| components/gastos | `components/gastos/gastos-politicas.css` |  |  |  |  |  | 1 | 1 |  |  | 2 |
| components/invoices | `components/invoices/FichaDeFactura.css` |  |  |  |  |  | 1 | 3 |  |  | 4 |
| components/invoices | `components/invoices/FichaDeFactura.tsx` |  | 1 |  |  |  |  |  |  |  | 1 |
| pages/Absences | `pages/AbsencesPage.tsx` | 1 | 1 |  |  |  |  |  |  |  | 2 |
| pages/AgentDashboard | `pages/AgentDashboardPage.tsx` |  |  | 1 |  |  |  |  |  |  | 1 |
| pages/AIHub | `pages/AIHubPage.tsx` | 3 |  | 2 | 1 |  |  |  |  |  | 6 |
| pages/AIHub | `pages/AIHubPage.css` |  |  |  |  |  | 2 |  |  |  | 2 |
| pages/alm | `pages/alm/uso/AjustePanel.tsx` |  |  | 2 | 2 | 1 |  |  |  |  | 5 |
| pages/alm | `pages/alm/uso/FuentesPanel.tsx` |  |  | 2 | 1 | 2 |  |  |  |  | 5 |
| pages/alm | `pages/alm/AsignacionesTab.tsx` | 1 |  | 2 | 1 |  |  |  |  |  | 4 |
| pages/alm | `pages/alm/ConciliacionTab.tsx` |  |  | 3 |  |  |  |  |  |  | 3 |
| pages/alm | `pages/alm/ActasTab.tsx` |  |  | 1 |  |  |  |  |  |  | 1 |
| pages/alm | `pages/alm/CostesTab.tsx` |  |  | 1 |  |  |  |  |  |  | 1 |
| pages/alm | `pages/alm/RenovacionesTab.tsx` | 1 |  |  |  |  |  |  |  |  | 1 |
| pages/alm | `pages/alm/uso/NoControladoPanel.tsx` |  |  | 1 |  |  |  |  |  |  | 1 |
| pages/alm | `pages/alm/uso/UsoPanel.tsx` | 1 |  |  |  |  |  |  |  |  | 1 |
| pages/ALM | `pages/ALMPage.tsx` | 20 |  | 26 | 3 |  |  |  |  |  | 49 |
| pages/ALM | `pages/ALMPage.css` |  |  |  |  |  | 2 | 2 |  |  | 4 |
| pages/ALMAltasBajas | `pages/ALMAltasBajasPage.tsx` | 1 |  |  | 2 |  |  |  |  |  | 3 |
| pages/Approvals | `pages/ApprovalsPage.tsx` | 1 | 1 | 21 | 9 | 2 |  |  |  |  | 34 |
| pages/Approvals | `pages/ApprovalsPage.css` |  |  |  |  |  | 4 | 3 |  |  | 7 |
| pages/Automations | `pages/AutomationsPage.tsx` |  |  | 8 | 2 |  |  |  |  |  | 10 |
| pages/Automations | `pages/AutomationsPage.css` |  |  |  |  |  | 2 | 1 |  |  | 3 |
| pages/BI | `pages/BIPage.tsx` |  | 1 |  |  |  |  |  |  |  | 1 |
| pages/BIProjectDetail | `pages/BIProjectDetailPage.tsx` | 1 | 1 |  |  |  |  |  |  |  | 2 |
| pages/BIProjectDetail | `pages/BIProjectDetailPage.css` |  |  |  |  |  |  | 1 |  |  | 1 |
| pages/bpm | `pages/bpm/BpmRunPanel.tsx` |  | 2 | 1 |  |  |  |  |  |  | 3 |
| pages/bpm | `pages/bpm/BpmRunPanel.css` |  |  |  |  |  |  | 2 |  |  | 2 |
| pages/bpm | `pages/bpm/BpmVersionsModal.tsx` |  | 1 |  |  |  |  |  |  |  | 1 |
| pages/BPM | `pages/BPMPage.tsx` | 2 |  | 1 |  |  |  |  |  |  | 3 |
| pages/BPM | `pages/BPMPage.css` |  |  |  |  |  | 1 |  |  |  | 1 |
| pages/Budgets | `pages/BudgetsPage.tsx` | 2 |  | 12 | 1 | 1 |  |  |  |  | 16 |
| pages/Budgets | `pages/BudgetsPage.css` |  |  |  |  |  | 1 | 1 |  |  | 2 |
| pages/Calendar | `pages/CalendarPage.css` |  |  |  |  |  | 1 |  |  |  | 1 |
| pages/Calendar | `pages/CalendarPage.tsx` |  |  | 1 |  |  |  |  |  |  | 1 |
| pages/Call | `pages/CallPage.tsx` | 6 |  |  |  |  |  |  |  |  | 6 |
| pages/Call | `pages/CallPage.css` |  |  |  |  |  |  | 1 |  |  | 1 |
| pages/Capacity | `pages/CapacityPage.tsx` | 1 |  | 4 |  |  |  |  |  |  | 5 |
| pages/Capacity | `pages/CapacityPage.css` |  |  |  |  |  | 1 |  |  |  | 1 |
| pages/CarteraIntake | `pages/CarteraIntakePage.tsx` | 1 | 4 | 2 | 3 |  |  |  |  |  | 10 |
| pages/Changelog | `pages/ChangelogPage.css` |  |  |  |  |  | 1 | 1 |  |  | 2 |
| pages/Changelog | `pages/ChangelogPage.tsx` |  |  | 2 |  |  |  |  |  |  | 2 |
| pages/Changes | `pages/ChangesPage.tsx` |  |  | 2 |  |  |  |  |  |  | 2 |
| pages/Changes | `pages/ChangesPage.css` |  |  |  |  |  | 1 |  |  |  | 1 |
| pages/Chat | `pages/ChatPage.tsx` | 23 |  | 2 |  |  |  |  |  |  | 25 |
| pages/Chat | `pages/ChatPage.css` |  |  |  |  |  | 4 | 1 |  | 1 | 6 |
| pages/ChatAdmin | `pages/ChatAdminPage.tsx` | 2 |  | 4 |  |  |  |  |  |  | 6 |
| pages/ChatAdmin | `pages/ChatAdminPage.css` |  |  |  |  |  | 1 | 1 |  |  | 2 |
| pages/clients | `pages/clients/ClientsPageTabs.tsx` |  | 1 | 9 | 4 |  |  |  |  |  | 14 |
| pages/clients | `pages/clients/PortalUsersTab.tsx` |  |  | 2 | 2 |  |  |  |  |  | 4 |
| pages/clients | `pages/clients/ClientsPageTabs.css` |  |  |  |  |  | 2 | 1 |  |  | 3 |
| pages/clients | `pages/clients/PortalUsersTab.css` |  |  |  |  |  | 2 | 1 |  |  | 3 |
| pages/Clients | `pages/ClientsPage.tsx` | 3 |  | 6 |  |  |  |  |  |  | 9 |
| pages/Clients | `pages/ClientsPage.css` |  |  |  |  |  | 2 |  |  |  | 2 |
| pages/CMDB | `pages/CMDBPage.tsx` | 1 | 2 | 13 |  |  |  |  |  |  | 16 |
| pages/CMDB | `pages/CMDBPage.css` |  |  |  |  |  | 5 | 5 |  | 1 | 11 |
| pages/Contracts | `pages/ContractsPage.tsx` | 4 |  | 5 |  |  |  |  |  |  | 9 |
| pages/Contracts | `pages/ContractsPage.css` |  |  |  |  |  | 4 | 3 |  |  | 7 |
| pages/ContractsAI | `pages/ContractsAIPage.css` |  |  |  |  |  | 3 |  |  |  | 3 |
| pages/ContractsAI | `pages/ContractsAIPage.tsx` |  |  | 1 |  |  |  |  |  |  | 1 |
| pages/CumulativeFlow | `pages/CumulativeFlowPage.tsx` |  | 1 | 1 |  |  |  |  |  |  | 2 |
| pages/CumulativeFlow | `pages/CumulativeFlowPage.css` |  |  |  |  |  | 1 |  |  |  | 1 |
| pages/CustomFields | `pages/CustomFieldsPage.tsx` | 2 | 1 | 1 | 2 |  |  |  |  |  | 6 |
| pages/CustomFields | `pages/CustomFieldsPage.css` |  |  |  |  |  | 3 | 2 |  |  | 5 |
| pages/DataGovernance | `pages/DataGovernancePage.tsx` |  |  | 3 | 1 |  |  |  |  |  | 4 |
| pages/DataGovernance | `pages/DataGovernancePage.css` |  |  |  |  |  | 1 |  |  |  | 1 |
| pages/DataPlatform | `pages/DataPlatformPage.css` |  |  |  |  |  | 1 |  |  |  | 1 |
| pages/DataPlatform | `pages/DataPlatformPage.tsx` |  |  | 1 |  |  |  |  |  |  | 1 |
| pages/Deliverables | `pages/DeliverablesPage.tsx` | 2 |  | 2 |  |  |  |  |  |  | 4 |
| pages/Deliverables | `pages/DeliverablesPage.css` |  |  |  |  |  | 3 |  |  |  | 3 |
| pages/Dependencies | `pages/DependenciesPage.tsx` | 1 | 1 | 3 |  |  |  |  |  |  | 5 |
| pages/Dependencies | `pages/DependenciesPage.css` |  |  |  |  |  | 4 |  |  |  | 4 |
| pages/DeveloperPortal | `pages/DeveloperPortalPage.css` |  |  |  |  |  | 2 | 3 |  |  | 5 |
| pages/DeveloperPortal | `pages/DeveloperPortalPage.tsx` | 1 |  |  |  |  |  |  |  |  | 1 |
| pages/Documents | `pages/DocumentsPage.css` |  |  |  |  |  | 8 | 7 | 1 | 9 | 25 |
| pages/Documents | `pages/DocumentsPage.tsx` | 11 | 1 | 10 | 2 |  |  |  |  |  | 24 |
| pages/Enterprise | `pages/EnterprisePage.tsx` | 1 |  | 7 | 2 |  |  |  |  |  | 10 |
| pages/Enterprise | `pages/EnterprisePage.css` |  |  |  |  |  | 5 | 3 |  |  | 8 |
| pages/EpicGantt | `pages/EpicGanttPage.tsx` | 1 |  | 3 |  |  |  |  |  |  | 4 |
| pages/EpicGantt | `pages/EpicGanttPage.css` |  |  |  |  |  | 1 |  |  |  | 1 |
| pages/Epics | `pages/EpicsPage.tsx` | 1 |  | 4 |  |  |  |  |  |  | 5 |
| pages/Epics | `pages/EpicsPage.css` |  |  |  |  |  | 1 |  |  | 2 | 3 |
| pages/ESign | `pages/ESignPage.tsx` | 1 | 1 | 2 |  |  |  |  |  |  | 4 |
| pages/ESign | `pages/ESignPage.css` |  |  |  |  |  | 2 |  |  |  | 2 |
| pages/EVM | `pages/EVMPage.css` |  |  |  |  |  | 2 |  | 1 |  | 3 |
| pages/EVM | `pages/EVMPage.tsx` |  | 1 |  |  |  |  |  |  |  | 1 |
| pages/Expenses | `pages/ExpensesPage.tsx` | 1 |  | 6 | 1 |  |  |  |  |  | 8 |
| pages/Expenses | `pages/ExpensesPage.css` |  |  |  |  |  | 2 | 1 |  |  | 3 |
| pages/Exports | `pages/ExportsPage.tsx` |  |  | 1 | 2 |  |  |  |  |  | 3 |
| pages/FinanceDashboard | `pages/FinanceDashboardPage.css` |  |  |  |  |  | 1 |  |  |  | 1 |
| pages/FinanceDashboard | `pages/FinanceDashboardPage.tsx` |  | 1 |  |  |  |  |  |  |  | 1 |
| pages/Git | `pages/GitPage.css` |  |  |  |  |  |  | 2 |  |  | 2 |
| pages/Governance | `pages/GovernancePage.css` |  |  |  |  |  | 2 |  |  | 2 | 4 |
| pages/Governance | `pages/GovernancePage.tsx` | 1 |  |  |  |  |  |  |  |  | 1 |
| pages/Grc | `pages/GrcPage.tsx` |  | 6 | 12 |  |  |  |  |  |  | 18 |
| pages/Grc | `pages/GrcPage.css` |  |  |  |  |  | 10 | 6 |  |  | 16 |
| pages/Import | `pages/ImportPage.css` |  |  |  |  |  | 2 | 1 |  |  | 3 |
| pages/Import | `pages/ImportPage.tsx` |  | 1 | 1 |  |  |  |  |  |  | 2 |
| pages/Imputar | `pages/ImputarPage.css` |  |  |  |  |  | 2 | 4 |  | 2 | 8 |
| pages/Imputar | `pages/ImputarPage.tsx` |  |  | 2 | 3 |  |  |  |  |  | 5 |
| pages/IntakeForm | `pages/IntakeFormPage.tsx` | 1 |  | 1 |  |  |  |  |  |  | 2 |
| pages/Invoices | `pages/InvoicesPage.css` |  |  |  |  |  | 3 | 2 |  | 1 | 6 |
| pages/Invoices | `pages/InvoicesPage.tsx` | 1 |  | 4 |  |  |  |  |  |  | 5 |
| pages/IssueTypes | `pages/IssueTypesPage.css` |  |  |  |  |  | 2 | 2 |  | 2 | 6 |
| pages/IssueTypes | `pages/IssueTypesPage.tsx` | 1 | 1 | 1 | 2 |  |  |  |  |  | 5 |
| pages/JiraIntegration | `pages/JiraIntegrationPage.css` |  |  |  |  |  | 2 | 4 |  |  | 6 |
| pages/Lecciones | `pages/LeccionesPage.tsx` | 3 |  | 3 | 1 |  |  |  |  |  | 7 |
| pages/Lecciones | `pages/LeccionesPage.css` |  |  |  |  |  | 1 | 3 |  |  | 4 |
| pages/Login | `pages/LoginPage.tsx` | 12 |  |  |  |  |  |  |  |  | 12 |
| pages/Login | `pages/LoginPage.css` |  |  |  |  |  | 1 |  |  |  | 1 |

## Bloque B. Operador M–Z (incluido service desk) — 145 ficheros, 688 incumplimientos

| Área | Fichero | botón | tabla | select | casilla | fieldset | MAYÚS | mono | color | alto px | Total |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| components/cmdb | `components/cmdb/CmdbMercado.tsx` |  |  | 2 | 1 |  |  |  |  |  | 3 |
| components/cmdb | `components/cmdb/CMDBTopologyGraph.tsx` | 2 |  |  |  |  |  |  |  |  | 2 |
| components/cmdb | `components/cmdb/CMDBTopologyGraph.css` |  |  |  |  |  | 1 |  |  |  | 1 |
| components/servicedesk | `components/servicedesk/VoiceAgentPanel.tsx` | 3 |  | 6 |  |  |  |  |  |  | 9 |
| components/servicedesk | `components/servicedesk/AgenteAutonomoPanel.tsx` |  |  | 3 | 4 |  |  |  |  |  | 7 |
| components/servicedesk | `components/servicedesk/AnalisisDelCambio.tsx` |  |  | 4 | 1 | 1 |  |  |  |  | 6 |
| components/servicedesk | `components/servicedesk/AlertCorrelationPanel.css` |  |  |  |  |  |  | 3 |  |  | 3 |
| components/servicedesk | `components/servicedesk/ChangeRolloutPanel.css` |  |  |  |  |  | 2 | 1 |  |  | 3 |
| components/servicedesk | `components/servicedesk/GestionDelProblema.tsx` |  |  | 1 | 2 |  |  |  |  |  | 3 |
| components/servicedesk | `components/servicedesk/RcaWizardModal.css` |  |  |  |  |  | 3 |  |  |  | 3 |
| components/servicedesk | `components/servicedesk/AlertCorrelationPanel.tsx` | 2 |  |  |  |  |  |  |  |  | 2 |
| components/servicedesk | `components/servicedesk/AutoResolutionPanel.tsx` | 2 |  |  |  |  |  |  |  |  | 2 |
| components/servicedesk | `components/servicedesk/BandejaDeCanales.tsx` | 2 |  |  |  |  |  |  |  |  | 2 |
| components/servicedesk | `components/servicedesk/ChangeRolloutPanel.tsx` | 1 |  | 1 |  |  |  |  |  |  | 2 |
| components/servicedesk | `components/servicedesk/ColaPorRiesgo.tsx` | 1 | 1 |  |  |  |  |  |  |  | 2 |
| components/servicedesk | `components/servicedesk/PanelDelCab.tsx` | 1 | 1 |  |  |  |  |  |  |  | 2 |
| components/servicedesk | `components/servicedesk/CatalogoInteligente.tsx` | 1 |  |  |  |  |  |  |  |  | 1 |
| components/servicedesk | `components/servicedesk/Cmdb3dGraph.css` |  |  |  |  |  | 1 |  |  |  | 1 |
| components/servicedesk | `components/servicedesk/Cmdb3dGraph.tsx` |  |  | 1 |  |  |  |  |  |  | 1 |
| components/servicedesk | `components/servicedesk/ContextoDelCliente.tsx` | 1 |  |  |  |  |  |  |  |  | 1 |
| components/servicedesk | `components/servicedesk/EstadoDeCicloDeVida.tsx` |  |  | 1 |  |  |  |  |  |  | 1 |
| components/servicedesk | `components/servicedesk/IncidentAssignmentPanel.tsx` |  |  | 1 |  |  |  |  |  |  | 1 |
| components/servicedesk | `components/servicedesk/MiPanel.tsx` | 1 |  |  |  |  |  |  |  |  | 1 |
| components/servicedesk | `components/servicedesk/RcaWizardModal.tsx` |  |  |  | 1 |  |  |  |  |  | 1 |
| components/servicedesk | `components/servicedesk/sdMercado.css` |  |  |  |  |  |  | 1 |  |  | 1 |
| components/servicedesk | `components/servicedesk/VistaDeDatos.tsx` |  | 1 |  |  |  |  |  |  |  | 1 |
| components/servicedesk | `components/servicedesk/VoiceAgentPanel.css` |  |  |  |  |  |  |  |  | 1 | 1 |
| pages/M365 | `pages/M365Page.css` |  |  |  |  |  |  | 3 |  |  | 3 |
| pages/M365 | `pages/M365Page.tsx` | 1 |  |  |  |  |  |  |  |  | 1 |
| pages/MeetingsAI | `pages/MeetingsAIPage.tsx` | 1 |  |  |  |  |  |  |  |  | 1 |
| pages/Mentions | `pages/MentionsPage.tsx` | 5 |  | 1 | 1 |  |  |  |  |  | 7 |
| pages/Mentions | `pages/MentionsPage.css` |  |  |  |  |  | 2 |  |  |  | 2 |
| pages/NexusAgent | `pages/NexusAgentPage.tsx` | 2 |  |  | 2 |  |  |  |  |  | 4 |
| pages/NexusAgent | `pages/NexusAgentPage.css` |  |  |  |  |  | 1 |  |  |  | 1 |
| pages/Notifications | `pages/NotificationsPage.css` |  |  |  |  |  | 1 | 1 |  |  | 2 |
| pages/Notifications | `pages/NotificationsPage.tsx` | 1 |  |  |  |  |  |  |  |  | 1 |
| pages/NPS | `pages/NPSPage.tsx` | 3 |  |  |  |  |  |  |  |  | 3 |
| pages/NPS | `pages/NPSPage.css` |  |  |  |  |  | 1 |  |  |  | 1 |
| pages/OKRs | `pages/OKRsPage.tsx` |  |  | 9 |  |  |  |  |  |  | 9 |
| pages/Organizations | `pages/OrganizationsPage.tsx` |  |  | 2 | 1 |  |  |  |  |  | 3 |
| pages/Organizations | `pages/OrganizationsPage.css` |  |  |  |  |  |  | 1 |  |  | 1 |
| pages/OrgChart | `pages/OrgChartPage.tsx` | 3 |  | 3 |  |  |  |  |  |  | 6 |
| pages/PerformanceReviews | `pages/PerformanceReviewsPage.tsx` | 8 |  | 7 | 2 |  |  |  |  |  | 17 |
| pages/PerformanceReviews | `pages/PerformanceReviewsPage.css` |  |  |  |  |  |  | 2 |  | 1 | 3 |
| pages/Pipeline | `pages/PipelinePage.css` |  |  |  |  |  | 5 | 1 |  |  | 6 |
| pages/Pipeline | `pages/PipelinePage.tsx` |  |  | 1 |  |  |  |  |  |  | 1 |
| pages/PlanificacionDeRecursos | `pages/PlanificacionDeRecursosPage.tsx` | 1 | 3 | 2 | 1 |  |  |  |  |  | 7 |
| pages/Politicas | `pages/PoliticasPage.tsx` | 1 |  |  |  |  |  |  |  |  | 1 |
| pages/Portfolio | `pages/PortfolioPage.tsx` | 3 | 1 |  |  |  |  |  |  |  | 4 |
| pages/Portfolio | `pages/PortfolioPage.css` |  |  |  |  |  | 1 |  |  |  | 1 |
| pages/PreguntarALaEmpresa | `pages/PreguntarALaEmpresaPage.tsx` | 1 | 1 | 2 |  |  |  |  |  |  | 4 |
| pages/Profitability | `pages/ProfitabilityPage.tsx` | 1 |  | 1 | 1 |  |  |  |  |  | 3 |
| pages/Profitability | `pages/ProfitabilityPage.css` |  |  |  |  |  | 1 |  |  | 1 | 2 |
| pages/ProjectDetail | `pages/ProjectDetailPage.css` |  |  |  |  |  | 8 | 3 | 1 |  | 12 |
| pages/ProjectDetail | `pages/ProjectDetailPage.tsx` | 7 |  | 1 |  |  |  |  |  |  | 8 |
| pages/ProjectPermissions | `pages/ProjectPermissionsPage.tsx` | 1 | 1 | 2 | 3 |  |  |  |  |  | 7 |
| pages/ProjectPermissions | `pages/ProjectPermissionsPage.css` |  |  |  |  |  | 1 |  |  |  | 1 |
| pages/Projects | `pages/ProjectsPage.tsx` | 13 |  | 13 |  |  |  |  |  |  | 26 |
| pages/Projects | `pages/ProjectsPage.css` |  |  |  |  |  | 7 | 4 |  |  | 11 |
| pages/ProjectTemplates | `pages/ProjectTemplatesPage.tsx` | 1 |  |  |  |  |  |  |  |  | 1 |
| pages/PublicForms | `pages/PublicFormsPage.tsx` |  |  | 3 | 1 |  |  |  |  |  | 4 |
| pages/PublicForms | `pages/PublicFormsPage.css` |  |  |  |  |  |  | 1 |  |  | 1 |
| pages/RACI | `pages/RACIPage.tsx` | 2 | 1 | 4 |  |  |  |  |  |  | 7 |
| pages/RACI | `pages/RACIPage.css` |  |  |  |  |  | 1 |  |  | 1 | 2 |
| pages/RateCards | `pages/RateCardsPage.tsx` | 3 | 1 |  | 1 |  |  |  |  |  | 5 |
| pages/RateCards | `pages/RateCardsPage.css` |  |  |  |  |  | 1 |  |  |  | 1 |
| pages/ReportBuilder | `pages/ReportBuilderPage.tsx` | 3 | 1 | 5 | 1 |  |  |  |  |  | 10 |
| pages/ReportBuilder | `pages/ReportBuilderPage.css` |  |  |  |  |  | 1 |  |  |  | 1 |
| pages/Reports | `pages/ReportsPage.tsx` | 8 | 1 | 6 | 1 |  |  |  |  |  | 16 |
| pages/Reports | `pages/ReportsPage.css` |  |  |  |  |  | 7 | 3 |  | 2 | 12 |
| pages/ResetPassword | `pages/ResetPasswordPage.css` |  |  |  |  |  | 1 |  | 1 | 3 | 5 |
| pages/ResetPassword | `pages/ResetPasswordPage.tsx` | 2 |  |  |  |  |  |  |  |  | 2 |
| pages/ResourceForecast | `pages/ResourceForecastPage.tsx` |  | 1 |  |  |  |  |  |  |  | 1 |
| pages/Resources | `pages/ResourcesPage.css` |  |  |  |  |  | 4 | 5 |  |  | 9 |
| pages/Resources | `pages/ResourcesPage.tsx` | 3 |  | 4 |  |  |  |  |  |  | 7 |
| pages/ResourceScheduler | `pages/ResourceSchedulerPage.tsx` | 1 |  | 3 |  |  |  |  |  |  | 4 |
| pages/ResourceScheduler | `pages/ResourceSchedulerPage.css` |  |  |  |  |  | 2 |  |  |  | 2 |
| pages/Revenue | `pages/RevenuePage.tsx` | 3 | 1 | 9 |  |  |  |  |  |  | 13 |
| pages/Revenue | `pages/RevenuePage.css` |  |  |  |  |  | 3 | 1 |  |  | 4 |
| pages/Risks | `pages/RisksPage.tsx` | 2 | 1 | 9 |  |  |  |  |  |  | 12 |
| pages/Risks | `pages/RisksPage.css` |  |  |  |  |  | 2 | 1 |  |  | 3 |
| pages/RiskScores | `pages/RiskScoresPage.tsx` | 2 |  | 1 |  |  |  |  |  |  | 3 |
| pages/RiskScores | `pages/RiskScoresPage.css` |  |  |  |  |  | 2 |  |  |  | 2 |
| pages/Scenarios | `pages/ScenariosPage.css` |  |  |  |  |  | 1 |  |  |  | 1 |
| pages/Scenarios | `pages/ScenariosPage.tsx` | 1 |  |  |  |  |  |  |  |  | 1 |
| pages/Search | `pages/SearchPage.tsx` | 6 |  | 1 |  |  |  |  |  |  | 7 |
| pages/Search | `pages/SearchPage.css` |  |  |  |  |  |  | 1 |  |  | 1 |
| pages/SemanticEngine | `pages/SemanticEnginePage.css` |  |  |  |  |  | 3 | 2 |  | 2 | 7 |
| pages/SemanticEngine | `pages/SemanticEnginePage.tsx` | 2 |  | 1 |  |  |  |  |  |  | 3 |
| pages/service-desk | `pages/service-desk/ConfigTab.tsx` | 2 | 1 | 16 | 4 |  |  |  |  |  | 23 |
| pages/service-desk | `pages/service-desk/QueueAndRoutingSections.tsx` | 4 | 2 | 13 |  |  |  |  |  |  | 19 |
| pages/service-desk | `pages/service-desk/TicketDetail.tsx` | 6 |  | 8 | 2 |  |  |  |  |  | 16 |
| pages/service-desk | `pages/service-desk/ConfigSlaYCiclos.tsx` |  | 2 | 6 | 5 |  |  |  |  |  | 13 |
| pages/service-desk | `pages/service-desk/ConfigEscaladoYAvisos.tsx` | 1 | 1 | 5 | 2 | 2 |  |  |  |  | 11 |
| pages/service-desk | `pages/service-desk/CreateTicketModal.tsx` |  |  | 10 |  |  |  |  |  |  | 10 |
| pages/service-desk | `pages/service-desk/ChangeManagementTab.tsx` | 2 | 1 | 6 |  |  |  |  |  |  | 9 |
| pages/service-desk | `pages/service-desk/ITSMKnowledgeTab.tsx` |  |  | 5 | 2 |  |  |  |  |  | 7 |
| pages/service-desk | `pages/service-desk/TicketDetail.css` |  |  |  |  |  | 5 | 2 |  |  | 7 |
| pages/service-desk | `pages/service-desk/WorkflowDesignerPage.tsx` | 2 | 1 | 4 |  |  |  |  |  |  | 7 |
| pages/service-desk | `pages/service-desk/CambiosPlanificacion.css` |  |  |  |  |  | 4 |  |  |  | 4 |
| pages/service-desk | `pages/service-desk/ChangeManagementTab.css` |  |  |  |  |  | 4 |  |  |  | 4 |
| pages/service-desk | `pages/service-desk/ITSMKnowledgeTab.css` |  |  |  |  |  | 4 |  |  |  | 4 |
| pages/service-desk | `pages/service-desk/WorkflowDesignerPage.css` |  |  |  |  |  | 3 | 1 |  |  | 4 |
| pages/service-desk | `pages/service-desk/CambiosPlanificacion.tsx` | 2 |  | 1 |  |  |  |  |  |  | 3 |
| pages/service-desk | `pages/service-desk/ConfigEscaladoYAvisos.css` |  |  |  |  |  | 2 | 1 |  |  | 3 |
| pages/service-desk | `pages/service-desk/ConfigGuardiasYMonitor.tsx` |  | 1 | 2 |  |  |  |  |  |  | 3 |
| pages/service-desk | `pages/service-desk/ConfigPaginaDeEstado.tsx` |  |  | 2 | 1 |  |  |  |  |  | 3 |
| pages/service-desk | `pages/service-desk/ConfigTab.css` |  |  |  |  |  | 1 | 1 |  | 1 | 3 |
| pages/service-desk | `pages/service-desk/ConfigCorreoEntrante.css` |  |  |  |  |  | 1 | 1 |  |  | 2 |
| pages/service-desk | `pages/service-desk/ConfigGuardiasYMonitor.css` |  |  |  |  |  | 1 | 1 |  |  | 2 |
| pages/service-desk | `pages/service-desk/ConfigCorreoEntrante.tsx` |  | 1 |  |  |  |  |  |  |  | 1 |
| pages/service-desk | `pages/service-desk/ConfigPaginaDeEstado.css` |  |  |  |  |  | 1 |  |  |  | 1 |
| pages/service-desk | `pages/service-desk/MetricsDashboardTab.css` |  |  |  |  |  | 1 |  |  |  | 1 |
| pages/service-desk | `pages/service-desk/MetricsDashboardTab.tsx` |  | 1 |  |  |  |  |  |  |  | 1 |
| pages/service-desk | `pages/service-desk/QueueAndRoutingSections.css` |  |  |  |  |  | 1 |  |  |  | 1 |
| pages/ServiceDesk | `pages/ServiceDeskPage.tsx` | 1 |  |  |  |  |  |  |  |  | 1 |
| pages/Skills | `pages/SkillsPage.tsx` | 4 | 1 | 4 | 1 |  |  |  |  |  | 10 |
| pages/Skills | `pages/SkillsPage.css` |  |  |  |  |  | 2 |  |  |  | 2 |
| pages/SLACalendars | `pages/SLACalendarsPage.tsx` | 1 |  | 1 | 1 | 1 |  |  |  |  | 4 |
| pages/SLACalendars | `pages/SLACalendarsPage.css` |  |  |  |  |  | 1 |  |  |  | 1 |
| pages/SprintCharts | `pages/SprintChartsPage.tsx` |  |  | 2 |  |  |  |  |  |  | 2 |
| pages/SprintPlanning | `pages/SprintPlanningPage.tsx` |  |  | 2 |  |  |  |  |  |  | 2 |
| pages/SprintPlanning | `pages/SprintPlanningPage.css` |  |  |  |  |  |  | 1 |  |  | 1 |
| pages/Sprints | `pages/SprintsPage.tsx` | 4 |  | 1 | 2 |  |  |  |  |  | 7 |
| pages/Sprints | `pages/SprintsPage.css` |  |  |  |  |  |  | 1 |  |  | 1 |
| pages/Subcontractors | `pages/SubcontractorsPage.tsx` | 1 | 2 | 10 | 1 |  |  |  |  |  | 14 |
| pages/Subcontractors | `pages/SubcontractorsPage.css` |  |  |  |  |  |  | 4 |  |  | 4 |
| pages/Tasks | `pages/TasksPage.tsx` | 7 |  | 19 | 5 |  |  |  |  |  | 31 |
| pages/Tasks | `pages/TasksPage.css` |  |  |  |  |  |  | 3 | 1 |  | 4 |
| pages/Timer | `pages/TimerPage.tsx` |  |  | 3 | 3 |  |  |  |  |  | 6 |
| pages/Timer | `pages/TimerPage.css` |  |  |  |  |  |  | 3 |  | 1 | 4 |
| pages/Timesheets | `pages/TimesheetsPage.tsx` |  | 2 | 2 |  |  |  |  |  |  | 4 |
| pages/Timesheets | `pages/TimesheetsPage.css` |  |  |  |  |  | 2 |  |  |  | 2 |
| pages/Training | `pages/TrainingPage.css` |  |  |  |  |  | 1 | 1 |  |  | 2 |
| pages/Training | `pages/TrainingPage.tsx` |  |  | 1 |  |  |  |  |  |  | 1 |
| pages/UAT | `pages/UATPage.tsx` |  |  | 5 |  |  |  |  |  |  | 5 |
| pages/UAT | `pages/UATPage.css` |  |  |  |  |  | 1 | 1 |  |  | 2 |
| pages/UserCosts | `pages/UserCostsPage.css` |  |  |  |  |  | 2 | 2 |  |  | 4 |
| pages/UserCosts | `pages/UserCostsPage.tsx` |  | 1 | 1 |  |  |  |  |  |  | 2 |
| pages/WebhookLog | `pages/WebhookLogPage.css` |  |  |  |  |  | 1 | 2 |  |  | 3 |
| pages/WebhookLog | `pages/WebhookLogPage.tsx` |  |  | 3 |  |  |  |  |  |  | 3 |
| pages/Wiki | `pages/WikiPage.tsx` | 10 |  | 3 | 2 |  |  |  |  |  | 15 |
| pages/Wiki | `pages/WikiPage.css` |  |  |  |  |  | 2 | 4 |  |  | 6 |
| pages/Workflows | `pages/WorkflowsPage.tsx` | 4 |  | 4 | 3 |  |  |  |  |  | 11 |
| pages/Workflows | `pages/WorkflowsPage.css` |  |  |  |  |  | 1 | 1 |  | 1 | 3 |

## Bloque C. Portal de clientes, componentes compartidos y Ajustes — 135 ficheros, 574 incumplimientos

| Área | Fichero | botón | tabla | select | casilla | fieldset | MAYÚS | mono | color | alto px | Total |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| App | `App.tsx` | 2 |  |  |  |  |  |  |  |  | 2 |
| components | `components/AIInlineEditor.tsx` | 6 |  |  |  |  |  |  |  |  | 6 |
| components | `components/ResourceHeatmap.tsx` |  |  | 4 |  |  |  |  |  |  | 4 |
| components | `components/GanttChart.css` |  |  |  |  |  | 3 |  |  |  | 3 |
| components | `components/SmartScheduleModal.tsx` | 1 |  |  | 2 |  |  |  |  |  | 3 |
| components | `components/DocumentsPanel.tsx` | 1 |  | 1 |  |  |  |  |  |  | 2 |
| components | `components/RouteBoundary.tsx` | 2 |  |  |  |  |  |  |  |  | 2 |
| components | `components/DocumentsPanel.css` |  |  |  |  |  |  | 1 |  |  | 1 |
| components | `components/ErrorBoundary.tsx` | 1 |  |  |  |  |  |  |  |  | 1 |
| components | `components/GanttChart.tsx` | 1 |  |  |  |  |  |  |  |  | 1 |
| components | `components/LangSelector.tsx` | 1 |  |  |  |  |  |  |  |  | 1 |
| components | `components/OfflineIndicator.tsx` | 1 |  |  |  |  |  |  |  |  | 1 |
| components | `components/ResourceHeatmap.css` |  |  |  |  |  | 1 |  |  |  | 1 |
| components | `components/SmartScheduleModal.css` |  |  |  |  |  | 1 |  |  |  | 1 |
| components/ausencias | `components/ausencias/admin/EditorDeTipos.tsx` | 2 |  | 7 |  | 4 |  |  |  |  | 13 |
| components/ausencias | `components/ausencias/FormularioDeAusencia.tsx` |  | 1 | 2 | 3 | 2 |  |  |  |  | 8 |
| components/ausencias | `components/ausencias/admin/EditorDeTurnos.tsx` | 1 |  | 3 | 1 | 1 |  |  |  |  | 6 |
| components/ausencias | `components/ausencias/admin/EditorDeRotaciones.tsx` | 1 |  | 1 |  | 2 |  |  |  |  | 4 |
| components/ausencias | `components/ausencias/admin/comun.tsx` |  |  |  | 1 | 1 |  |  |  |  | 2 |
| components/ausencias | `components/ausencias/admin/EjemplosDeAusencias.tsx` | 2 |  |  |  |  |  |  |  |  | 2 |
| components/ausencias | `components/ausencias/admin/MapaDeCobertura.tsx` |  |  | 2 |  |  |  |  |  |  | 2 |
| components/ausencias | `components/ausencias/BandejaDeAusencias.tsx` | 1 | 1 |  |  |  |  |  |  |  | 2 |
| components/ausencias | `components/ausencias/DetalleDeAusencia.tsx` |  |  | 2 |  |  |  |  |  |  | 2 |
| components/ausencias | `components/ausencias/admin/CuadranteDeTurnos.tsx` | 1 |  |  |  |  |  |  |  |  | 1 |
| components/ausencias | `components/ausencias/admin/EditorDeDocumentos.tsx` | 1 |  |  |  |  |  |  |  |  | 1 |
| components/ausencias | `components/ausencias/ausencias.css` |  |  |  |  |  |  |  |  | 1 | 1 |
| components/avisos | `components/avisos/BandejaDesplegable.css` |  |  |  |  |  |  |  |  | 2 | 2 |
| components/avisos | `components/avisos/BandejaDesplegable.tsx` | 1 |  |  |  |  |  |  |  |  | 1 |
| components/bi | `components/bi/BiGdprPanel.tsx` | 3 |  | 4 |  |  |  |  |  |  | 7 |
| components/bi | `components/bi/BiQueryBuilderPanel.tsx` |  |  | 7 |  |  |  |  |  |  | 7 |
| components/bi | `components/bi/VisualQueryBuilderWidget.tsx` | 1 |  | 5 | 1 |  |  |  |  |  | 7 |
| components/bi | `components/bi/BiGovernancePanel.css` |  |  |  |  |  | 3 | 2 |  |  | 5 |
| components/bi | `components/bi/BiO365Panel.css` |  |  |  |  |  | 2 | 1 |  |  | 3 |
| components/bi | `components/bi/SmartAlertsPanel.tsx` |  |  | 3 |  |  |  |  |  |  | 3 |
| components/bi | `components/bi/AskDataWidget.tsx` | 2 |  |  |  |  |  |  |  |  | 2 |
| components/bi | `components/bi/BiConditionalDeliveryPanel.tsx` | 2 |  |  |  |  |  |  |  |  | 2 |
| components/bi | `components/bi/BiEtlPanel.css` |  |  |  |  |  |  | 2 |  |  | 2 |
| components/bi | `components/bi/BiGdprPanel.css` |  |  |  |  |  |  | 2 |  |  | 2 |
| components/bi | `components/bi/AskDataWidget.css` |  |  |  |  |  |  | 1 |  |  | 1 |
| components/bi | `components/bi/BiDashboardCollabPanel.css` |  |  |  |  |  | 1 |  |  |  | 1 |
| components/bi | `components/bi/BiDashboardCollabPanel.tsx` |  |  | 1 |  |  |  |  |  |  | 1 |
| components/bi | `components/bi/BiEtlPanel.tsx` |  |  | 1 |  |  |  |  |  |  | 1 |
| components/bi | `components/bi/BiGovernancePanel.tsx` |  |  |  | 1 |  |  |  |  |  | 1 |
| components/bi | `components/bi/BiO365Panel.tsx` |  |  |  | 1 |  |  |  |  |  | 1 |
| components/bi | `components/bi/NarrativeCard.tsx` | 1 |  |  |  |  |  |  |  |  | 1 |
| components/conectores | `components/conectores/DocumentosDeFicha.tsx` | 3 |  |  |  |  |  |  |  |  | 3 |
| components/conectores | `components/conectores/EstadoDeConectores.css` |  |  |  |  |  |  | 2 |  |  | 2 |
| components/conectores | `components/conectores/EstadoDeConectores.tsx` | 1 | 1 |  |  |  |  |  |  |  | 2 |
| components/conectores | `components/conectores/DocumentoContecmind.css` |  |  |  |  |  |  | 1 |  |  | 1 |
| components/conectores | `components/conectores/DocumentoContecmind.tsx` |  | 1 |  |  |  |  |  |  |  | 1 |
| components/conectores | `components/conectores/DocumentosDeFicha.css` |  |  |  |  |  | 1 |  |  |  | 1 |
| components/dashboard | `components/dashboard/DashKit.css` |  |  |  |  |  | 4 |  |  |  | 4 |
| components/layout | `components/layout/UserProfilePanel.tsx` | 13 |  |  | 2 |  |  |  |  |  | 15 |
| components/layout | `components/layout/NexusAssistPanel.tsx` | 10 |  |  | 1 |  |  |  |  |  | 11 |
| components/layout | `components/layout/Layout.tsx` | 10 |  |  |  |  |  |  |  |  | 10 |
| components/layout | `components/layout/VoiceCommandModal.tsx` | 8 |  |  |  |  |  |  |  |  | 8 |
| components/layout | `components/layout/GlobalChatPanel.tsx` | 3 |  | 1 | 1 |  |  |  |  |  | 5 |
| components/layout | `components/layout/QuickCreateMenu.tsx` | 4 |  | 1 |  |  |  |  |  |  | 5 |
| components/layout | `components/layout/UserProfilePanel.css` |  |  |  |  |  | 4 | 1 |  |  | 5 |
| components/layout | `components/layout/AlertsDrawer.css` |  |  |  |  |  | 2 | 1 |  |  | 3 |
| components/layout | `components/layout/AlertsDrawer.tsx` | 3 |  |  |  |  |  |  |  |  | 3 |
| components/layout | `components/layout/GlobalSearch.tsx` | 3 |  |  |  |  |  |  |  |  | 3 |
| components/layout | `components/layout/Layout.css` |  |  |  |  |  | 2 | 1 |  |  | 3 |
| components/layout | `components/layout/GlobalSearch.css` |  |  |  |  |  | 2 |  |  |  | 2 |
| components/layout | `components/layout/NexusAssistPanel.css` |  |  |  |  |  |  |  |  | 2 | 2 |
| components/layout | `components/layout/PageHeader.css` |  |  |  |  |  | 2 |  |  |  | 2 |
| components/layout | `components/layout/PageHeader.tsx` | 2 |  |  |  |  |  |  |  |  | 2 |
| components/layout | `components/layout/VoiceCommandModal.css` |  |  |  |  |  | 1 |  | 1 |  | 2 |
| components/layout | `components/layout/QuickCreateMenu.css` |  |  |  |  |  | 1 |  |  |  | 1 |
| components/layout | `components/layout/SelectorDeEmpresa.tsx` |  |  | 1 |  |  |  |  |  |  | 1 |
| components/lecciones | `components/lecciones/FormularioDeLeccion.tsx` |  | 1 | 3 |  |  |  |  |  |  | 4 |
| components/lecciones | `components/lecciones/FichaDeLeccion.css` |  |  |  |  |  | 1 | 1 |  |  | 2 |
| components/lecciones | `components/lecciones/FichaDeLeccion.tsx` |  |  | 1 |  |  |  |  |  |  | 1 |
| components/lecciones | `components/lecciones/FormularioDeLeccion.css` |  |  |  |  |  | 1 |  |  |  | 1 |
| components/lecciones | `components/lecciones/LeccionesDeOrigen.css` |  |  |  |  |  |  | 1 |  |  | 1 |
| components/lecciones | `components/lecciones/LeccionesDeOrigen.tsx` | 1 |  |  |  |  |  |  |  |  | 1 |
| components/lecciones | `components/lecciones/LeccionesQueAplican.css` |  |  |  |  |  |  | 1 |  |  | 1 |
| components/lecciones | `components/lecciones/LeccionesQueAplican.tsx` | 1 |  |  |  |  |  |  |  |  | 1 |
| components/planificador | `components/planificador/EditorDeDependencias.tsx` |  | 1 | 5 |  |  |  |  |  |  | 6 |
| components/planificador | `components/planificador/VistasDeTrabajo.tsx` | 1 |  | 3 | 1 |  |  |  |  |  | 5 |
| components/planificador | `components/planificador/PanelDeLineasBase.tsx` |  | 2 | 1 | 1 |  |  |  |  |  | 4 |
| components/planificador | `components/planificador/PanelDelPlan.tsx` |  | 1 | 1 |  |  |  |  |  |  | 2 |
| components/planificador | `components/planificador/PanelDeNivelacion.tsx` |  | 1 |  | 1 |  |  |  |  |  | 2 |
| components/planificador | `components/planificador/ModalAutoPlanificar.tsx` |  | 1 |  |  |  |  |  |  |  | 1 |
| components/planificador | `components/planificador/PanelIaDelProyecto.tsx` |  | 1 |  |  |  |  |  |  |  | 1 |
| components/politicas | `components/politicas/EditorDeResultados.tsx` |  |  | 5 | 3 | 2 |  |  |  |  | 10 |
| components/politicas | `components/politicas/comun.tsx` | 1 |  | 5 | 1 |  |  |  |  |  | 7 |
| components/politicas | `components/politicas/ConstructorDeCondiciones.tsx` |  |  | 6 | 1 |  |  |  |  |  | 7 |
| components/politicas | `components/politicas/EditorDePolitica.tsx` | 2 |  |  | 2 | 1 |  |  |  |  | 5 |
| components/politicas | `components/politicas/EditorDeTablas.tsx` | 1 | 1 | 3 |  |  |  |  |  |  | 5 |
| components/politicas | `components/politicas/Simulador.tsx` |  |  |  | 3 |  |  |  |  |  | 3 |
| components/politicas | `components/politicas/politicas.css` |  |  |  |  |  | 1 |  | 1 |  | 2 |
| components/politicas | `components/politicas/EditorDeExceso.tsx` |  |  | 1 |  |  |  |  |  |  | 1 |
| components/politicas | `components/politicas/PoliticaDeLaSolicitud.tsx` | 1 |  |  |  |  |  |  |  |  | 1 |
| components/portal | `components/portal/GovernedConversations.tsx` | 1 |  | 7 | 2 |  |  |  |  |  | 10 |
| components/portal | `components/portal/GovernedConversations.css` |  |  |  |  |  | 2 |  |  |  | 2 |
| components/presupuestos | `components/presupuestos/FichaDePresupuesto.tsx` | 1 | 6 | 2 |  |  |  |  |  |  | 9 |
| components/presupuestos | `components/presupuestos/SeguirPresupuesto.tsx` | 1 | 1 | 7 |  |  |  |  |  |  | 9 |
| components/presupuestos | `components/presupuestos/FichaDePresupuesto.css` |  |  |  |  |  | 1 | 4 |  |  | 5 |
| components/presupuestos | `components/presupuestos/FormularioDePartida.tsx` | 1 |  | 4 |  |  |  |  |  |  | 5 |
| components/presupuestos | `components/presupuestos/SeguirPresupuesto.css` |  |  |  |  |  |  | 5 |  |  | 5 |
| components/presupuestos | `components/presupuestos/CampanasYPlantillas.tsx` |  |  | 1 |  |  |  |  |  |  | 1 |
| components/security | `components/security/PasskeysSection.tsx` | 4 |  |  |  |  |  |  |  |  | 4 |
| components/traduccion | `components/traduccion/VersionesKbPanel.tsx` |  |  |  | 1 | 1 |  |  |  |  | 2 |
| components/traduccion | `components/traduccion/TextoTraducido.tsx` | 1 |  |  |  |  |  |  |  |  | 1 |
| components/traduccion | `components/traduccion/VistaPreviaDeSalida.tsx` |  |  | 1 |  |  |  |  |  |  | 1 |
| context | `context/AuthContext.tsx` | 2 |  |  |  |  |  |  |  |  | 2 |
| context | `context/ToastContext.tsx` | 1 |  |  |  |  |  |  |  |  | 1 |
| main | `main.tsx` | 1 |  |  |  |  |  |  |  |  | 1 |
| pages/ClientPortal | `pages/ClientPortalPage.tsx` | 3 |  | 7 | 4 | 3 |  |  |  |  | 17 |
| pages/ClientPortal | `pages/ClientPortalPage.css` |  |  |  |  |  | 5 | 1 |  |  | 6 |
| pages/portal-client | `pages/portal-client/PortalUI.css` |  |  |  |  |  | 6 | 3 | 6 |  | 15 |
| pages/portal-client | `pages/portal-client/PortalUI.tsx` | 8 |  | 1 |  |  |  |  |  |  | 9 |
| pages/portal-client | `pages/portal-client/PortalDashboard.css` |  |  |  |  |  | 2 | 5 |  |  | 7 |
| pages/portal-client | `pages/portal-client/PortalAIChatWidget.tsx` | 6 |  |  |  |  |  |  |  |  | 6 |
| pages/portal-client | `pages/portal-client/PortalSupportDesk.css` |  |  |  |  |  | 3 |  | 3 |  | 6 |
| pages/portal-client | `pages/portal-client/portalClientContext.css` |  |  |  |  |  | 2 |  | 2 |  | 4 |
| pages/portal-client | `pages/portal-client/PortalSurveys.css` |  |  |  |  |  | 1 | 2 | 1 |  | 4 |
| pages/portal-client | `pages/portal-client/PortalAdvancedSections.css` |  |  |  |  |  | 1 | 2 |  |  | 3 |
| pages/portal-client | `pages/portal-client/PortalAIChatWidget.css` |  |  |  |  |  | 1 |  | 2 |  | 3 |
| pages/portal-client | `pages/portal-client/PortalDashboard.tsx` | 2 |  |  |  |  |  |  |  |  | 2 |
| pages/portal-client | `pages/portal-client/PortalQuickCreateMenu.tsx` | 2 |  |  |  |  |  |  |  |  | 2 |
| pages/portal-client | `pages/portal-client/PortalSurveys.tsx` | 2 |  |  |  |  |  |  |  |  | 2 |
| pages/portal-client | `pages/portal-client/PortalAdvancedSections.tsx` | 1 |  |  |  |  |  |  |  |  | 1 |
| pages/portal-client | `pages/portal-client/portalClientContext.tsx` | 1 |  |  |  |  |  |  |  |  | 1 |
| pages/portal-client | `pages/portal-client/PortalQuickCreateMenu.css` |  |  |  |  |  | 1 |  |  |  | 1 |
| pages/portal-client | `pages/portal-client/PortalSupportDesk.tsx` | 1 |  |  |  |  |  |  |  |  | 1 |
| pages/portal-client | `pages/portal-client/TraduccionAutomatica.tsx` | 1 |  |  |  |  |  |  |  |  | 1 |
| pages/PortalCliente | `pages/PortalClientePage.tsx` | 2 |  |  |  |  |  |  |  |  | 2 |
| pages/PortalPublicView | `pages/PortalPublicViewPage.css` |  |  |  |  |  | 1 |  |  |  | 1 |
| pages/Settings | `pages/SettingsPageSections.tsx` | 43 |  | 24 | 10 |  |  |  |  |  | 77 |
| pages/Settings | `pages/SettingsPageSections.css` |  |  |  |  |  | 8 | 9 |  | 5 | 22 |
| pages/settings-sections | `pages/settings-sections/TraduccionSection.tsx` |  |  | 6 | 5 | 3 |  |  |  |  | 14 |
| pages/settings-sections | `pages/settings-sections/SettingsAdvancedSections.tsx` | 6 |  | 2 |  |  |  |  |  |  | 8 |
| pages/settings-sections | `pages/settings-sections/SettingsAdvancedSections.css` |  |  |  |  |  | 3 | 4 |  |  | 7 |
