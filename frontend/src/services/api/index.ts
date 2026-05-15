/**
 * Barrel re-export for `services/api`.
 *
 * Imports like `from '../services/api'` resolve to this file once the legacy
 * `services/api.js` is removed (Vite / TS prefer the package-style folder).
 *
 * Each sub-module groups a set of related axios calls (auth, users, tasks,
 * service-desk, BI, …). When typing a hook against one of these helpers,
 * import the typed namespace directly:
 *
 *     import { tasksApi } from '@/services/api'
 *     const res = await tasksApi.list({ project_id: pid })   // AxiosResponse<unknown>
 *     const tasks = unwrapList<Task>(res)                    // Task[]
 */

// Axios instance & types
export { default, api } from './client'
export type { AxiosRequestConfig } from './client'
export * from './types'
export { unwrapList, unwrapData, apiErrorMsg } from './helpers'

// Per-resource APIs
export { authApi, mfaApi, userCostsApi } from './auth'
export type { LoginCredentials, ForgotPasswordPayload, ResetPasswordPayload, ChangePasswordPayload } from './auth'

export { usersApi } from './users'
export type { UserUpdatePayload } from './users'

export {
  projectsApi,
  projectChangesApi,
  projectWorkflowsApi,
  projectSprintsApi,
  dependenciesApi,
  sprintPlansApi,
  portfolioApi,
} from './projects'
export type { ProjectCreatePayload } from './projects'

export {
  tasksApi,
  taskDependenciesApi,
  issueTypesApi,
  permissionsApi,
  customFieldsApi,
} from './tasks'
export type { TaskCreatePayload } from './tasks'

export { imputationsApi, timesheetsApi } from './imputations'
export type { ImputationCreatePayload } from './imputations'

export {
  clientsApi,
  clientExtApi,
  portalClientsApi,
  portalApi,
  portalConversationsApi,
} from './clients'
export type { ClientCreatePayload } from './clients'

export { expensesApi } from './expenses'
export { absencesApi } from './absences'

export {
  invoicesApi,
  accountingApi,
  revenueApi,
  revenueRecognitionApi,
  budgetsApi,
  templatesApi,
  billingSmartMatchApi,
} from './invoices'

export { documentsApi, esignApi } from './documents'

export {
  bookingsApi,
  resourceForecastApi,
  forecastApi,
  capacityApi,
  profitabilityApi,
  burnoutRiskApi,
  resourcesApi,
} from './bookings'

export { sprintsApi, epicsApi, epicDependenciesApi } from './sprints'

export { risksApi, riskScoresApi, oracleApi } from './risks'

export { okrsApi } from './okrs'

export { deliverablesApi, milestonesApi } from './deliverables'

export { rateCardsApi } from './rateCards'

export { contractsApi } from './contracts'

export { approvalsApi, uatApi } from './approvals'

export {
  ticketsApi,
  problemsApi,
  changesApi,
  sdDynamicFormsApi,
  sdMetricsApi,
  sdCatalogApi,
  sdSlaPoliciesApi,
  sdGroupsApi,
  sdTemplatesApi,
  sdCannedApi,
  sdAnnouncementsApi,
  sdRoutingApi,
  sdKbApi,
  sdWorkflowDesignerApi,
  majorIncidentsApi,
  sdMajorIncidentsApi,
  slaSchedulesApi,
  slaCalendarsApi,
  autoResolutionApi,
  alertClustersApi,
  changeRolloutApi,
  cabApi,
  voiceAgentApi,
  incidentAssignmentApi,
  wsApi,
} from './serviceDesk'

export { assetsApi, licensesApi, vendorsApi, almExtApi } from './assets'

export { cmdbApi, cmdb3dApi } from './cmdb'

export {
  analyticsApi,
  biCollaborationApi,
  biIntelligenceApi,
  biPlatformApi,
  biSmartAlertsApi,
  biBookmarksApi,
  biGovernanceAuditApi,
  biReportBuilderV2Api,
  biForecastingApi,
  biAnomalyApi,
  biGdprApi,
  biDashboardCollabApi,
  biQueryBuilderApi,
  biConditionalDeliveryApi,
  biEtlApi,
  biO365Api,
  predictiveObservabilityApi,
  predictionsApi,
} from './bi'

export { pipelineApi, npsApi, scenariosApi, performanceApi } from './pipeline'

export { subcontractorsApi, enterpriseSubsApi } from './subcontractors'

export { trainingApi, skillsApi } from './training'

export { dashboardApi, alertsApi, aiCopilotApi } from './dashboard'

export {
  integrationsApi,
  jiraApi,
  m365Api,
  oauthIntegrationsApi,
  integrationsHubApi,
  apiKeysApi,
  webhooksApi,
  emailApi,
  currencyApi,
  importApi,
} from './integrations'

export {
  meetingsAIApi,
  contractsAIApi,
  voiceApi,
  smartScheduleApi,
  semanticApi,
  nexusAgentApi,
  aiProvidersApi,
} from './ai'

export {
  automationsApi,
  autoWorkflowsApi,
  workflowsLegacyApi,
  scheduledReportsApi,
} from './automation'

export {
  enterpriseApi,
  organizationsApi,
  gdprApi,
  governanceApi,
  grcApi,
  developerAppsApi,
  formsApi,
} from './enterprise'

export {
  settingsApi,
  settingsAdminApi,
  onboardingApi,
  searchApi,
  gitApi,
  reportBuilderApi,
  wikiApi,
  mentionsApi,
  bpmnProcessesApi,
} from './misc'
