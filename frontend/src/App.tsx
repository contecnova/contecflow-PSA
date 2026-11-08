import { Component, Suspense, lazy } from 'react'
import type { ReactNode } from 'react'
import ErrorBoundary from './components/ErrorBoundary'
import { withRouteBoundary } from './components/RouteBoundary'
import { Routes, Route, Navigate, useLocation, useParams } from 'react-router-dom'
import { useAuth } from './context/AuthContext'
import type { Role } from './context/AuthContext'
import Layout from './components/layout/Layout'
import AppShell from './components/layout/AppShell'
import { Spinner } from './components/ui'
import TopProgressBar from './components/layout/TopProgressBar'
import { useAppT } from './hooks/useAppT'
import useOfflineSync from './hooks/useOfflineSync'
import OfflineIndicator from './components/OfflineIndicator'
import OfflineConflictResolver from './components/OfflineConflictResolver'
import {
  SkeletonDashboard, SkeletonTable, SkeletonProjects,
  SkeletonGantt, SkeletonServiceDesk,
  SkeletonFinance,
} from './components/ui/Skeletons'

// ── Lazy page imports (code-splitting) ────────────────────────────────────────
const LoginPage              = lazy(() => import('./pages/LoginPage'))
const ResetPasswordPage      = lazy(() => import('./pages/ResetPasswordPage'))
const AprobacionPorCorreoPage = lazy(() => import('./pages/AprobacionPorCorreoPage'))
const ProjectsPage           = lazy(() => import('./pages/ProjectsPage'))
const TasksPage              = lazy(() => import('./pages/TasksPage'))
const ImputarPage            = lazy(() => import('./pages/ImputarPage'))
const ResourcesPage          = lazy(() => import('./pages/ResourcesPage'))
const AlertsPage             = lazy(() => import('./pages/AlertsPage'))
const ExportsPage            = lazy(() => import('./pages/ExportsPage'))
const ReportsPage            = lazy(() => import('./pages/ReportsPage'))
const SettingsPage           = lazy(() => import('./pages/SettingsPage'))
const TimesheetsPage         = lazy(() => import('./pages/TimesheetsPage'))
const CapacityPage           = lazy(() => import('./pages/CapacityPage'))
const ProfitabilityPage      = lazy(() => import('./pages/ProfitabilityPage'))
const PipelinePage           = lazy(() => import('./pages/PipelinePage'))
const ContractsPage          = lazy(() => import('./pages/ContractsPage'))
const RisksPage              = lazy(() => import('./pages/RisksPage'))
const SkillsPage             = lazy(() => import('./pages/SkillsPage'))
const AbsencesPage           = lazy(() => import('./pages/AbsencesPage'))
const ChangesPage            = lazy(() => import('./pages/ChangesPage'))
const DeliverablesPage       = lazy(() => import('./pages/DeliverablesPage'))
const ClientPortalPage       = lazy(() => import('./pages/ClientPortalPage'))
const CalendarPage           = lazy(() => import('./pages/CalendarPage'))
const PortalClientePage      = lazy(() => import('./pages/PortalClientePage'))
const PortalPublicViewPage   = lazy(() => import('./pages/PortalPublicViewPage'))
const ServiceDeskPage        = lazy(() => import('./pages/ServiceDeskPage'))
const EnterprisePage         = lazy(() => import('./pages/EnterprisePage'))
const InvoicesPage           = lazy(() => import('./pages/InvoicesPage'))
const ImportPage             = lazy(() => import('./pages/ImportPage'))
const SprintsPage            = lazy(() => import('./pages/SprintsPage'))
const ExpensesPage           = lazy(() => import('./pages/ExpensesPage'))
const AutomationsPage        = lazy(() => import('./pages/AutomationsPage'))
const RevenuePage            = lazy(() => import('./pages/RevenuePage'))
const MFAPage                = lazy(() => import('./pages/MFAPage'))
const OrganizationsPage      = lazy(() => import('./pages/OrganizationsPage'))
const ScenariosPage          = lazy(() => import('./pages/ScenariosPage'))
const BudgetsPage            = lazy(() => import('./pages/BudgetsPage'))
const AIHubPage              = lazy(() => import('./pages/AIHubPage'))
const ContecflowAgentPage    = lazy(() => import('./pages/NexusAgentPage'))
const OraclePage             = lazy(() => import('./pages/OraclePage'))
const MeetingsAIPage         = lazy(() => import('./pages/MeetingsAIPage'))
const ContractsAIPage        = lazy(() => import('./pages/ContractsAIPage'))
const SemanticEnginePage     = lazy(() => import('./pages/SemanticEnginePage'))
const ResourceForecastPage   = lazy(() => import('./pages/ResourceForecastPage'))
const ResourceSchedulerPage  = lazy(() => import('./pages/ResourceSchedulerPage'))
const RateCardsPage          = lazy(() => import('./pages/RateCardsPage'))
const MilestoneBillingPage   = lazy(() => import('./pages/MilestoneBillingPage'))
const ApprovalsPage          = lazy(() => import('./pages/ApprovalsPage'))
const DocumentsPage          = lazy(() => import('./pages/DocumentsPage'))
const TimerPage              = lazy(() => import('./pages/TimerPage'))
const GanttPage              = lazy(() => import('./pages/GanttPage'))
const SubcontractorsPage     = lazy(() => import('./pages/SubcontractorsPage'))
const GovernancePage         = lazy(() => import('./pages/GovernancePage'))
const CustomFieldsPage       = lazy(() => import('./pages/CustomFieldsPage'))
const WorkflowsPage          = lazy(() => import('./pages/WorkflowsPage'))
const WorkflowDesignerPage   = lazy(() => import('./pages/service-desk/WorkflowDesignerPage'))
const ProjectPermissionsPage = lazy(() => import('./pages/ProjectPermissionsPage'))
const WikiPage               = lazy(() => import('./pages/WikiPage'))
const EpicsPage              = lazy(() => import('./pages/EpicsPage'))
const SearchPage             = lazy(() => import('./pages/SearchPage'))
const CumulativeFlowPage     = lazy(() => import('./pages/CumulativeFlowPage'))
const MentionsPage           = lazy(() => import('./pages/MentionsPage'))
const IssueTypesPage         = lazy(() => import('./pages/IssueTypesPage'))
const DependenciesPage       = lazy(() => import('./pages/DependenciesPage'))
const FullTextSearchPage     = lazy(() => import('./pages/FullTextSearchPage'))
const EpicGanttPage          = lazy(() => import('./pages/EpicGanttPage'))
const WikiTagsPage           = lazy(() => import('./pages/WikiTagsPage'))
const InternalCommentsPage   = lazy(() => import('./pages/InternalCommentsPage'))
const CMDBPage               = lazy(() => import('./pages/CMDBPage'))
const AgentDashboardPage     = lazy(() => import('./pages/AgentDashboardPage'))
const SprintPlanningPage     = lazy(() => import('./pages/SprintPlanningPage'))
const SLACalendarsPage       = lazy(() => import('./pages/SLACalendarsPage'))
const ALMPage                = lazy(() => import('./pages/ALMPage'))
const ClientsPage            = lazy(() => import('./pages/ClientsPage'))
const RiskScoresPage         = lazy(() => import('./pages/RiskScoresPage'))
const EVMPage                = lazy(() => import('./pages/EVMPage'))
const PortfolioPage          = lazy(() => import('./pages/PortfolioPage'))
const GitPage                = lazy(() => import('./pages/GitPage'))
const SprintChartsPage       = lazy(() => import('./pages/SprintChartsPage'))
const ESignPage              = lazy(() => import('./pages/ESignPage'))
const ReportBuilderPage      = lazy(() => import('./pages/ReportBuilderPage'))
const NPSPage                = lazy(() => import('./pages/NPSPage'))
const M365Page               = lazy(() => import('./pages/M365Page'))
const OrgChartPage           = lazy(() => import('./pages/OrgChartPage'))
const GrcPage                = lazy(() => import('./pages/GrcPage'))
const OKRsPage               = lazy(() => import('./pages/OKRsPage'))
const PerformanceReviewsPage = lazy(() => import('./pages/PerformanceReviewsPage'))
const TrainingPage           = lazy(() => import('./pages/TrainingPage'))
const WebhookLogPage         = lazy(() => import('./pages/WebhookLogPage'))
const NotificationsPage      = lazy(() => import('./pages/NotificationsPage'))
const InboxPage              = lazy(() => import('./pages/InboxPage'))
const RACIPage               = lazy(() => import('./pages/RACIPage'))
const ChangelogPage          = lazy(() => import('./pages/ChangelogPage'))
const UATPage                = lazy(() => import('./pages/UATPage'))
const PublicFormsPage        = lazy(() => import('./pages/PublicFormsPage'))
const IntakeFormPage         = lazy(() => import('./pages/IntakeFormPage'))
const DeveloperPortalPage    = lazy(() => import('./pages/DeveloperPortalPage'))
const BIPage                 = lazy(() => import('./pages/BIPage'))
const BIProjectDetailPage    = lazy(() => import('./pages/BIProjectDetailPage'))
const DataExplorerPage       = lazy(() => import('./pages/DataExplorerPage'))
const PreguntarALaEmpresaPage = lazy(() => import('./pages/PreguntarALaEmpresaPage'))
const PredictionsPage        = lazy(() => import('./pages/PredictionsPage'))
const DataPlatformPage       = lazy(() => import('./pages/DataPlatformPage'))
const DataGovernancePage     = lazy(() => import('./pages/DataGovernancePage'))
const JiraIntegrationPage    = lazy(() => import('./pages/JiraIntegrationPage'))
const ProjectTemplatesPage   = lazy(() => import('./pages/ProjectTemplatesPage'))
const ForbiddenPage          = lazy(() => import('./pages/ForbiddenPage'))
const NotFoundPage           = lazy(() => import('./pages/NotFoundPage'))
const WorkDashboardPage      = lazy(() => import('./pages/WorkDashboardPage'))
const TimePage               = lazy(() => import('./pages/TimePage'))
const ProjectDetailPage      = lazy(() => import('./pages/ProjectDetailPage'))
const ProjectsDashboardPage  = lazy(() => import('./pages/ProjectsDashboardPage'))
const TeamDashboardPage      = lazy(() => import('./pages/TeamDashboardPage'))
const FinanceDashboardPage   = lazy(() => import('./pages/FinanceDashboardPage'))
const SupportDashboardPage   = lazy(() => import('./pages/SupportDashboardPage'))
const BPMPage                = lazy(() => import('./pages/BPMPage'))
const UserCostsPage          = lazy(() => import('./pages/UserCostsPage'))
const ChatPage               = lazy(() => import('./pages/ChatPage'))
const CallPage               = lazy(() => import('./pages/CallPage'))
const ChatAdminPage          = lazy(() => import('./pages/ChatAdminPage'))

// ── Per-section Error Boundaries (audit #84) ─────────────────────────────────
// Pages especially prone to render-time failures (heavy dashboards, AI views,
// complex data viz, service desk) are wrapped in their own RouteBoundary so
// a crash in one section never derails the rest of the app.
const SafeBIPage              = withRouteBoundary(BIPage, 'BI')
const SafeBIProjectDetail     = withRouteBoundary(BIProjectDetailPage, 'BI')
const SafeDataExplorer        = withRouteBoundary(DataExplorerPage, 'BI')
const SafePreguntarALaEmpresa = withRouteBoundary(PreguntarALaEmpresaPage, 'BI')
const SafePredictions         = withRouteBoundary(PredictionsPage, 'BI')
const SafeDataPlatform        = withRouteBoundary(DataPlatformPage, 'BI')
const SafeDataGovernance      = withRouteBoundary(DataGovernancePage, 'BI')
const SafeAIHub               = withRouteBoundary(AIHubPage, 'AI')
const SafeContecflowAgent     = withRouteBoundary(ContecflowAgentPage, 'AI')
const SafeOracle              = withRouteBoundary(OraclePage, 'AI')
const SafeMeetingsAI          = withRouteBoundary(MeetingsAIPage, 'AI')
const SafeContractsAI         = withRouteBoundary(ContractsAIPage, 'AI')
const SafeSemanticEngine      = withRouteBoundary(SemanticEnginePage, 'AI')
const SafeServiceDesk         = withRouteBoundary(ServiceDeskPage, 'ServiceDesk')
const SafeWorkflowDesigner    = withRouteBoundary(WorkflowDesignerPage, 'ServiceDesk')
const SafeAgentDashboard      = withRouteBoundary(AgentDashboardPage, 'ServiceDesk')
const SafeSupportDashboard    = withRouteBoundary(SupportDashboardPage, 'Dashboards')
const SafeProjectsDashboard   = withRouteBoundary(ProjectsDashboardPage, 'Dashboards')
const SafeFinanceDashboard    = withRouteBoundary(FinanceDashboardPage, 'Dashboards')
const SafeTeamDashboard       = withRouteBoundary(TeamDashboardPage, 'Dashboards')
const SafeWorkDashboard       = withRouteBoundary(WorkDashboardPage, 'Dashboards')
const SafeReports             = withRouteBoundary(ReportsPage, 'Reports')
const SafeReportBuilder       = withRouteBoundary(ReportBuilderPage, 'Reports')
const SafeGantt               = withRouteBoundary(GanttPage, 'Gantt')
const SafeEpicGantt           = withRouteBoundary(EpicGanttPage, 'Gantt')

// ── Fallback de carga para lazy pages — skeleton por tipo de módulo ───────────
const TABLE_ROUTES = new Set([
  '/tasks','/timesheets','/resources','/absences','/risks','/changes',
  '/deliverables','/contracts','/expenses','/approvals','/invoices',
  '/clients','/alerts','/exports','/import','/skills','/documents',
  '/subcontractors','/rate-cards','/sprint-charts','/cumulative-flow',
  '/risk-scores','/raci','/changelog','/uat','/alm','/cmdb','/reports',
  '/okrs','/performance-reviews','/training','/webhook-log','/notifications',
])
const FINANCE_ROUTES = new Set([
  '/profitability','/revenue','/budgets','/pipeline','/evm','/portfolio',
  '/scenarios','/nps','/report-builder','/milestone-billing',
  '/data-explorer','/ask-company','/predictions','/data-platform','/data-governance',
])

function SmartPageLoader() {
  const { pathname } = useLocation()
  if (pathname === '/executive') return <SkeletonDashboard />
  if (pathname === '/projects')                 return <SkeletonProjects />
  if (pathname === '/gantt' || pathname === '/epic-gantt') return <SkeletonGantt />
  if (pathname === '/service-desk')             return <SkeletonServiceDesk />
  if (TABLE_ROUTES.has(pathname))               return <SkeletonTable />
  if (FINANCE_ROUTES.has(pathname))             return <SkeletonFinance />
  return <PageLoader />
}

function PageLoader() {
  return (
    <div style={{
      minHeight: '100vh', display: 'flex', alignItems: 'center',
      justifyContent: 'center', background: 'var(--surface-0)'
    }}>
      <div style={{
        width: 36, height: 36, border: '3px solid #1e2d45',
        borderTopColor: 'var(--accent)', borderRadius: '50%',
        animation: 'spin 0.8s linear infinite'
      }} />
      <style>{'@keyframes spin { to { transform: rotate(360deg) } }'}</style>
    </div>
  )
}

// ── ErrorBoundary por página — captura errores de una page sin derribar el layout ─
interface PageErrorBoundaryProps {
  children?: ReactNode
  resetKey: string
  // i18n translator — TODO type: useAppT().t signature
  t: (key: string, vars?: Record<string, unknown>) => string
}
interface PageErrorBoundaryState {
  error: Error | null
}
class PageErrorBoundary extends Component<PageErrorBoundaryProps, PageErrorBoundaryState> {
  constructor(props: PageErrorBoundaryProps) {
    super(props)
    this.state = { error: null }
  }
  static getDerivedStateFromError(error: Error): PageErrorBoundaryState { return { error } }
  componentDidUpdate(prevProps: PageErrorBoundaryProps) {
    // Reset boundary when navigation changes so one broken page does not
    // keep the whole app section in an error state.
    if (this.state.error && this.props.resetKey !== prevProps.resetKey) {
      this.setState({ error: null })
    }
  }
  componentDidCatch(error: Error) { console.error('[Contecflow] Page render error:', error) }
  render() {
    if (!this.state.error) return this.props.children
    const isChunk = this.state.error?.message?.includes('Failed to fetch dynamically imported module')
      || this.state.error?.message?.includes('Loading chunk')
    return (
      <div style={{
        display: 'flex', flexDirection: 'column', alignItems: 'center',
        justifyContent: 'center', minHeight: '60vh', padding: 40, textAlign: 'center'
      }}>
        <div style={{ fontSize: "var(--text-6xl)", marginBottom: 16 }}>⚠️</div>
        <h3 style={{ color: 'var(--danger)', marginBottom: 8 }}>
          {isChunk ? this.props.t('app_errors.page_load_outdated') : this.props.t('app_errors.page_load_failed')}
        </h3>
        <p style={{ color: 'var(--text-2)', marginBottom: 20, maxWidth: 480 }}>
          {isChunk
            ? this.props.t('app_errors.page_outdated_desc')
            : this.props.t('app_errors.page_unexpected_desc')}
        </p>
        <div style={{ display: 'flex', gap: 12 }}>
          <button
            onClick={() => { this.setState({ error: null }); window.location.href = '/login' }}
            style={{ padding: '10px 22px', background: 'var(--accent)', border: 'none', borderRadius: 8, color: 'var(--on-accent)', cursor: 'pointer', fontWeight: 600 }}
          >
            {this.props.t('app_errors.go_login')}
          </button>
          <button
            onClick={() => {
              if ('caches' in window) caches.keys().then(keys => Promise.all(keys.map(k => caches.delete(k))))
              window.location.reload()
            }}
            style={{ padding: '10px 22px', background: 'var(--surface-2)', border: '1px solid var(--border)', borderRadius: 8, color: 'var(--text-1)', cursor: 'pointer', fontWeight: 600 }}
          >
            {this.props.t('app_errors.reload')}
          </button>
        </div>
      </div>
    )
  }
}

function RouteScopedBoundary({ children }: { children?: ReactNode }) {
  const { pathname } = useLocation()
  const { t } = useAppT()
  const legacyT = (key: string, vars?: Record<string, unknown>) => String(t(key as never, vars as never))
  return <PageErrorBoundary resetKey={pathname} t={legacyT}>{children}</PageErrorBoundary>
}

interface ProtectedRouteProps {
  children?: ReactNode
  roles?: Role[]
}
function ProtectedRoute({ children, roles }: ProtectedRouteProps) {
  const location = useLocation()
  const { user, loading, hasRole, canOpen = () => true } = useAuth()
  if (loading) return (
    <div style={{ minHeight: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center', background: 'var(--surface-0)' }}>
      <Spinner size={32} />
    </div>
  )
  if (!user) return <Navigate to="/login" replace />
  if ((roles && !hasRole(...roles)) || !canOpen(location.pathname)) {
    return <Navigate to="/403" state={{ from: location.pathname }} replace />
  }
  return <>{children}</>
}

// Default landing per role — aligns with PSA market standard:
//   employee   → /work-dashboard ("My Day": tasks + timer + approvals)
//   hr         → /team-dashboard (people, OKRs, performance, training)
//   admin/pm/team_lead → /projects-dashboard (portfolio health + KPIs)
//   fallback   → /tasks
function landingPathFor(role: Role | undefined): string {
  switch (role) {
    case 'employee':           return '/work-dashboard'
    case 'hr':                 return '/team-dashboard'
    case 'admin':
    case 'pm':
    case 'team_lead':          return '/projects-dashboard'
    default:                   return '/tasks'
  }
}

// ── Redirects para rutas /bi/* legacy ─────────────────────────────────────
const BI_LEGACY_TARGETS: Record<string, string> = {
  explore:        '/data-explorer',
  analytics:      '/data-explorer',
  intelligence:   '/predictions',
  data:           '/data-platform',
  'data-sources': '/data-platform',
  govern:         '/data-governance',
  governance:     '/data-governance',
  collaboration:  '/data-governance',
  dashboard:      '/executive',
  hub:            '/executive',
}
function BiLegacyRedirect() {
  const { section } = useParams<{ section: string }>()
  return <Navigate to={(section && BI_LEGACY_TARGETS[section]) || '/executive'} replace />
}
function BiProjectLegacyRedirect() {
  const { projectId } = useParams<{ projectId: string }>()
  return <Navigate to={`/projects/${projectId}/analytics`} replace />
}

function AppRoutes() {
  const { user } = useAuth()
  const defaultPath = landingPathFor(user?.role)

  return (
    <>
    <TopProgressBar />
    <RouteScopedBoundary>
    <Suspense fallback={<SmartPageLoader />}>
    <Routes>
      <Route path="/login" element={user ? <Navigate to={defaultPath} replace /> : <LoginPage />} />
      <Route path="/reset-password" element={user ? <Navigate to={defaultPath} replace /> : <ResetPasswordPage />} />
      {/* Aprobar desde el correo: sin sesión, el enlace firmado identifica al aprobador. */}
      <Route path="/approvals/decide" element={<AprobacionPorCorreoPage />} />
      <Route path="/403" element={<ProtectedRoute><ForbiddenPage /></ProtectedRoute>} />

      <Route path="/" element={
        <ProtectedRoute>
          <Layout>
            <Navigate to={defaultPath} replace />
          </Layout>
        </ProtectedRoute>
      } />

      <Route path="/work-dashboard" element={
        <ProtectedRoute>
          <Layout><SafeWorkDashboard /></Layout>
        </ProtectedRoute>
      } />

      <Route path="/projects" element={
        <ProtectedRoute>
          <Layout><ProjectsPage /></Layout>
        </ProtectedRoute>
      } />

      <Route path="/projects/:id" element={
        <ProtectedRoute>
          <Layout><ProjectDetailPage /></Layout>
        </ProtectedRoute>
      } />

      <Route path="/projects-dashboard" element={
        <ProtectedRoute roles={['admin','pm','team_lead']}>
          <Layout><SafeProjectsDashboard /></Layout>
        </ProtectedRoute>
      } />

      <Route path="/tasks" element={
        <ProtectedRoute>
          <Layout><TasksPage /></Layout>
        </ProtectedRoute>
      } />

      <Route path="/time" element={
        <ProtectedRoute>
          <Layout><TimePage /></Layout>
        </ProtectedRoute>
      } />

      <Route path="/imputar" element={
        <ProtectedRoute>
          <Layout><ImputarPage /></Layout>
        </ProtectedRoute>
      } />

      <Route path="/resources" element={
        <ProtectedRoute roles={['admin', 'hr', 'pm']}>
          <Layout><ResourcesPage /></Layout>
        </ProtectedRoute>
      } />

      <Route path="/alerts" element={
        <ProtectedRoute roles={['admin', 'pm', 'hr']}>
          <Layout><AlertsPage /></Layout>
        </ProtectedRoute>
      } />

      <Route path="/exports" element={
        <ProtectedRoute roles={['admin', 'pm', 'hr']}>
          <Layout><ExportsPage /></Layout>
        </ProtectedRoute>
      } />

      <Route path="/reports" element={
        <ProtectedRoute>
          <Layout><SafeReports /></Layout>
        </ProtectedRoute>
      } />

      <Route path="/settings" element={
        <ProtectedRoute roles={['admin', 'hr', 'pm']}>
          <Layout><SettingsPage /></Layout>
        </ProtectedRoute>
      } />

      <Route path="/timesheets" element={
        <ProtectedRoute>
          <Layout><TimesheetsPage /></Layout>
        </ProtectedRoute>
      } />

      <Route path="/capacity" element={
        <ProtectedRoute roles={['admin', 'pm', 'hr']}>
          <Layout><CapacityPage /></Layout>
        </ProtectedRoute>
      } />

      <Route path="/profitability" element={
        <ProtectedRoute roles={['admin', 'pm']}>
          <Layout><ProfitabilityPage /></Layout>
        </ProtectedRoute>
      } />

      <Route path="/pipeline" element={
        <ProtectedRoute roles={['admin', 'pm']}>
          <Layout><PipelinePage /></Layout>
        </ProtectedRoute>
      } />

      <Route path="/contracts" element={
        <ProtectedRoute roles={['admin', 'pm']}>
          <Layout><ContractsPage /></Layout>
        </ProtectedRoute>
      } />

      <Route path="/risks" element={
        <ProtectedRoute roles={['admin', 'pm']}>
          <Layout><RisksPage /></Layout>
        </ProtectedRoute>
      } />

      <Route path="/skills" element={
        <ProtectedRoute>
          <Layout><SkillsPage /></Layout>
        </ProtectedRoute>
      } />

      <Route path="/absences" element={
        <ProtectedRoute>
          <Layout><AbsencesPage /></Layout>
        </ProtectedRoute>
      } />

      <Route path="/changes" element={
        <ProtectedRoute roles={['admin', 'pm']}>
          <Layout><ChangesPage /></Layout>
        </ProtectedRoute>
      } />

      <Route path="/deliverables" element={
        <ProtectedRoute roles={['admin', 'pm']}>
          <Layout><DeliverablesPage /></Layout>
        </ProtectedRoute>
      } />

      <Route path="/client-portal" element={
        <ProtectedRoute roles={['admin', 'pm']}>
          <Layout><ClientPortalPage /></Layout>
        </ProtectedRoute>
      } />

      <Route path="/support-dashboard" element={
        <ProtectedRoute roles={['admin','pm','employee','hr','team_lead']}>
          <Layout><SafeSupportDashboard /></Layout>
        </ProtectedRoute>
      } />

      <Route path="/service-desk" element={
        <ProtectedRoute roles={['admin', 'pm', 'employee', 'hr']}>
          <Layout><SafeServiceDesk /></Layout>
        </ProtectedRoute>
      } />

      <Route path="/sd/workflow-designer" element={
        <ProtectedRoute roles={['admin', 'pm']}>
          <Layout><SafeWorkflowDesigner /></Layout>
        </ProtectedRoute>
      } />

      {/* External client portal – no Layout, standalone app */}
      <Route path="/enterprise" element={<ProtectedRoute roles={['admin']}><Layout><EnterprisePage /></Layout></ProtectedRoute>} />
      <Route path="/invoices" element={<ProtectedRoute roles={['admin','pm']}><Layout><InvoicesPage /></Layout></ProtectedRoute>} />
      <Route path="/import" element={<ProtectedRoute roles={['admin','pm']}><Layout><ImportPage /></Layout></ProtectedRoute>} />
      <Route path="/portal" element={<PortalClientePage />} />
      <Route path="/portal/view/:token" element={<PortalPublicViewPage />} />

      <Route path="/sprints" element={<ProtectedRoute><Layout><SprintsPage /></Layout></ProtectedRoute>} />
      <Route path="/expenses" element={<ProtectedRoute><Layout><ExpensesPage /></Layout></ProtectedRoute>} />
      <Route path="/revenue" element={<ProtectedRoute roles={['admin','pm']}><Layout><RevenuePage /></Layout></ProtectedRoute>} />
      <Route path="/risk-scores" element={<ProtectedRoute roles={['admin','pm']}><Layout><RiskScoresPage /></Layout></ProtectedRoute>} />
      <Route path="/evm" element={<ProtectedRoute roles={['admin','pm']}><Layout><EVMPage /></Layout></ProtectedRoute>} />
      <Route path="/portfolio" element={<ProtectedRoute roles={['admin','pm']}><Layout><PortfolioPage /></Layout></ProtectedRoute>} />
      <Route path="/git" element={<ProtectedRoute roles={['admin','pm']}><Layout><GitPage /></Layout></ProtectedRoute>} />
      <Route path="/sprint-charts" element={<ProtectedRoute roles={['admin','pm']}><Layout><SprintChartsPage /></Layout></ProtectedRoute>} />
      <Route path="/esign" element={<ProtectedRoute roles={['admin','pm']}><Layout><ESignPage /></Layout></ProtectedRoute>} />
      <Route path="/report-builder" element={<ProtectedRoute roles={['admin','pm']}><Layout><SafeReportBuilder /></Layout></ProtectedRoute>} />
      <Route path="/nps" element={<ProtectedRoute roles={['admin','pm']}><Layout><NPSPage /></Layout></ProtectedRoute>} />
      <Route path="/m365" element={<ProtectedRoute roles={['admin']}><Layout><M365Page /></Layout></ProtectedRoute>} />
      <Route path="/automations" element={<ProtectedRoute roles={['admin','pm']}><Layout><AutomationsPage /></Layout></ProtectedRoute>} />

      <Route path="/mfa" element={<ProtectedRoute><Layout><MFAPage /></Layout></ProtectedRoute>} />
      <Route path="/organizations" element={<ProtectedRoute roles={['admin']}><Layout><OrganizationsPage /></Layout></ProtectedRoute>} />
      <Route path="/scenarios" element={<ProtectedRoute roles={['admin','pm']}><Layout><ScenariosPage /></Layout></ProtectedRoute>} />
      <Route path="/budgets" element={<ProtectedRoute roles={['admin','pm']}><Layout><BudgetsPage /></Layout></ProtectedRoute>} />
      <Route path="/ai-hub" element={<ProtectedRoute roles={['admin','pm']}><Layout><SafeAIHub /></Layout></ProtectedRoute>} />
      <Route path="/nexus-agent" element={<ProtectedRoute roles={['admin','pm']}><Layout><SafeContecflowAgent /></Layout></ProtectedRoute>} />
      <Route path="/oracle" element={<ProtectedRoute roles={['admin','pm']}><Layout><SafeOracle /></Layout></ProtectedRoute>} />
      <Route path="/meetings-ai" element={<ProtectedRoute><Layout><SafeMeetingsAI /></Layout></ProtectedRoute>} />
      <Route path="/contracts-ai" element={<ProtectedRoute roles={['admin','pm']}><Layout><SafeContractsAI /></Layout></ProtectedRoute>} />
      <Route path="/custom-fields" element={
        <ProtectedRoute roles={['admin','pm']}>
          <Layout><CustomFieldsPage /></Layout>
        </ProtectedRoute>
      } />
      <Route path="/settings/project-workflows" element={
        <ProtectedRoute roles={['admin','pm']}>
          <Layout><WorkflowsPage /></Layout>
        </ProtectedRoute>
      } />
      <Route path="/settings/workflows" element={<Navigate to="/settings/project-workflows" replace />} />
      <Route path="/workflows" element={<Navigate to="/settings/project-workflows" replace />} />
      <Route path="/calendar" element={<ProtectedRoute><Layout><CalendarPage /></Layout></ProtectedRoute>} />
      <Route path="/wiki" element={<ProtectedRoute><Layout><WikiPage/></Layout></ProtectedRoute>}/>
      <Route path="/epics" element={<ProtectedRoute><Layout><EpicsPage/></Layout></ProtectedRoute>}/>
      <Route path="/search" element={<ProtectedRoute><Layout><SearchPage/></Layout></ProtectedRoute>}/>
      <Route path="/cumulative-flow" element={<ProtectedRoute><Layout><CumulativeFlowPage/></Layout></ProtectedRoute>}/>
      <Route path="/issue-types"    element={<ProtectedRoute roles={['admin','pm']}><Layout><IssueTypesPage/></Layout></ProtectedRoute>}/>
      <Route path="/dependencies"   element={<ProtectedRoute><Layout><DependenciesPage/></Layout></ProtectedRoute>}/>
      <Route path="/fts-search"     element={<ProtectedRoute><Layout><FullTextSearchPage/></Layout></ProtectedRoute>}/>
      <Route path="/wiki-tags"          element={<ProtectedRoute><Layout><WikiTagsPage/></Layout></ProtectedRoute>}/>
      <Route path="/internal-comments" element={<ProtectedRoute><Layout><InternalCommentsPage/></Layout></ProtectedRoute>}/>
      <Route path="/cmdb"              element={<ProtectedRoute roles={['admin','pm']}><Layout><CMDBPage/></Layout></ProtectedRoute>}/>
      <Route path="/agent-dashboard"   element={<ProtectedRoute roles={['admin','pm']}><Layout><SafeAgentDashboard/></Layout></ProtectedRoute>}/>
      {/* Revisión 2026-11: «Kanban» era la misma pregunta que Tareas → vista Kanban; ahora es una sola pantalla. */}
      <Route path="/kanban-advanced"   element={<Navigate to="/tasks?view=kanban" replace />}/>
      <Route path="/sprint-planning"   element={<ProtectedRoute><Layout><SprintPlanningPage/></Layout></ProtectedRoute>}/>
      <Route path="/sla-calendars"     element={<ProtectedRoute roles={['admin','pm']}><Layout><SLACalendarsPage/></Layout></ProtectedRoute>}/>
      <Route path="/epic-gantt"     element={<ProtectedRoute><Layout><SafeEpicGantt/></Layout></ProtectedRoute>}/>
      <Route path="/mentions" element={<ProtectedRoute><Layout><MentionsPage/></Layout></ProtectedRoute>}/>
      <Route path="/project-permissions" element={
        <ProtectedRoute roles={['admin','pm']}>
          <Layout><ProjectPermissionsPage /></Layout>
        </ProtectedRoute>
      } />
      <Route path="/semantic-engine"  element={<ProtectedRoute roles={['admin','pm']}><Layout><SafeSemanticEngine /></Layout></ProtectedRoute>} />
      <Route path="/resource-forecast" element={<ProtectedRoute roles={['admin','pm','team_lead']}><Layout><ResourceForecastPage /></Layout></ProtectedRoute>} />
      <Route path="/resource-scheduler" element={<ProtectedRoute roles={['admin','pm','team_lead']}><Layout><ResourceSchedulerPage /></Layout></ProtectedRoute>} />
      <Route path="/rate-cards"        element={<ProtectedRoute roles={['admin','pm']}><Layout><RateCardsPage /></Layout></ProtectedRoute>} />
      <Route path="/milestone-billing" element={<ProtectedRoute roles={['admin','pm']}><Layout><MilestoneBillingPage /></Layout></ProtectedRoute>} />
      {/* Revisión 2026-11: cualquier usuario interno puede ser aprobador (rol, grupo, departamento, responsable, delegado). */}
      <Route path="/approvals" element={<ProtectedRoute roles={['admin','pm','team_lead','hr','employee']}><Layout><ApprovalsPage mode="inbox" /></Layout></ProtectedRoute>} />
      <Route path="/settings/approval-workflows" element={<ProtectedRoute roles={['admin','pm','team_lead']}><Layout><ApprovalsPage mode="config" /></Layout></ProtectedRoute>} />
      <Route path="/documents" element={<ProtectedRoute><Layout><DocumentsPage /></Layout></ProtectedRoute>} />
      <Route path="/timer" element={<ProtectedRoute><Layout><TimerPage /></Layout></ProtectedRoute>} />
      <Route path="/gantt" element={<ProtectedRoute roles={['admin','pm','team_lead','employee']}><Layout><SafeGantt /></Layout></ProtectedRoute>} />
      {/* Nuevas rutas top-level (sustituyen al antiguo /bi) */}
      <Route path="/data-explorer"   element={<ProtectedRoute roles={['admin','pm']}><Layout><SafeDataExplorer   /></Layout></ProtectedRoute>} />
      <Route path="/ask-company"     element={<ProtectedRoute roles={['admin','pm','team_lead','hr','employee']}><Layout><SafePreguntarALaEmpresa /></Layout></ProtectedRoute>} />
      <Route path="/predictions"     element={<ProtectedRoute roles={['admin','pm']}><Layout><SafePredictions    /></Layout></ProtectedRoute>} />
      <Route path="/data-platform"   element={<ProtectedRoute roles={['admin']}>     <Layout><SafeDataPlatform   /></Layout></ProtectedRoute>} />
      <Route path="/data-governance" element={<ProtectedRoute roles={['admin']}>     <Layout><SafeDataGovernance /></Layout></ProtectedRoute>} />
      <Route path="/projects/:id/analytics" element={<ProtectedRoute roles={['admin','pm']}><Layout><SafeBIProjectDetail /></Layout></ProtectedRoute>} />
      {/* Redirects legacy */}
      <Route path="/bi" element={<Navigate to="/executive" replace />} />
      <Route path="/bi/:section" element={<BiLegacyRedirect />} />
      <Route path="/bi/project/:projectId" element={<BiProjectLegacyRedirect />} />
      <Route path="/subcontractors" element={<ProtectedRoute roles={['admin','pm']}><Layout><SubcontractorsPage /></Layout></ProtectedRoute>} />
      <Route path="/governance" element={<ProtectedRoute roles={['admin']}><Layout><GovernancePage /></Layout></ProtectedRoute>} />
      <Route path="/finance-dashboard"   element={<ProtectedRoute roles={['admin','pm']}><Layout><SafeFinanceDashboard /></Layout></ProtectedRoute>} />
      <Route path="/team-dashboard"     element={<ProtectedRoute roles={['admin','pm','hr','team_lead']}><Layout><SafeTeamDashboard /></Layout></ProtectedRoute>} />
      <Route path="/clients"             element={<ProtectedRoute roles={['admin','pm']}><Layout><ClientsPage /></Layout></ProtectedRoute>} />
      <Route path="/alm"        element={<ProtectedRoute roles={['admin','pm']}><Layout><ALMPage /></Layout></ProtectedRoute>} />
      <Route path="/org-chart" element={<ProtectedRoute roles={['admin','pm','hr']}><Layout><OrgChartPage /></Layout></ProtectedRoute>} />
      <Route path="/grc" element={<ProtectedRoute roles={['admin']}><Layout><GrcPage /></Layout></ProtectedRoute>} />
      <Route path="/okrs"                element={<ProtectedRoute roles={['admin','pm','hr']}><Layout><OKRsPage /></Layout></ProtectedRoute>} />
      <Route path="/performance-reviews" element={<ProtectedRoute roles={['admin','pm','hr']}><Layout><PerformanceReviewsPage /></Layout></ProtectedRoute>} />
      <Route path="/training"            element={<ProtectedRoute><Layout><TrainingPage /></Layout></ProtectedRoute>} />
      <Route path="/executive"           element={<ProtectedRoute roles={['admin','pm']}><Layout><SafeBIPage /></Layout></ProtectedRoute>} />
      <Route path="/webhook-log"         element={<ProtectedRoute roles={['admin']}><Layout><WebhookLogPage /></Layout></ProtectedRoute>} />
      <Route path="/inbox"               element={<ProtectedRoute><Layout><InboxPage /></Layout></ProtectedRoute>} />
      <Route path="/notifications"       element={<ProtectedRoute><Layout><NotificationsPage /></Layout></ProtectedRoute>} />
      <Route path="/raci"                element={<ProtectedRoute><Layout><RACIPage /></Layout></ProtectedRoute>} />
      <Route path="/changelog"           element={<ProtectedRoute><Layout><ChangelogPage /></Layout></ProtectedRoute>} />
      <Route path="/uat"                element={<ProtectedRoute><Layout><UATPage /></Layout></ProtectedRoute>} />
      <Route path="/public-forms"       element={<ProtectedRoute roles={['admin','pm']}><Layout><PublicFormsPage /></Layout></ProtectedRoute>} />
      <Route path="/intake/:token"      element={<IntakeFormPage />} />
      <Route path="/developer"          element={<ProtectedRoute roles={['admin','pm']}><Layout><DeveloperPortalPage /></Layout></ProtectedRoute>} />
      <Route path="/jira-integration"   element={<ProtectedRoute roles={['admin','pm']}><Layout><JiraIntegrationPage /></Layout></ProtectedRoute>} />
        <Route path="/project-templates"   element={<ProtectedRoute roles={['admin','pm']}><Layout><ProjectTemplatesPage /></Layout></ProtectedRoute>} />
      <Route path="/bpm" element={<ProtectedRoute roles={['admin','pm','team_lead']}><Layout><BPMPage /></Layout></ProtectedRoute>} />
      <Route path="/user-costs" element={<ProtectedRoute roles={['admin','hr']}><Layout><UserCostsPage /></Layout></ProtectedRoute>} />
      <Route path="/chat" element={<ProtectedRoute><Layout><ChatPage /></Layout></ProtectedRoute>} />
      <Route path="/settings/chat-admin" element={<ProtectedRoute roles={['admin']}><Layout><ChatAdminPage /></Layout></ProtectedRoute>} />
      <Route path="/chat/admin" element={<ProtectedRoute roles={['admin']}><Navigate to="/settings/chat-admin" replace /></ProtectedRoute>} />
      <Route path="/chat/call/:callId" element={<ProtectedRoute><CallPage /></ProtectedRoute>} />
      <Route path="*" element={<NotFoundPage />} />
    </Routes>
    </Suspense>
    </RouteScopedBoundary>
    </>
  )
}


export default function App() {
  // Toast/Confirm providers live in AppProviders (main.tsx). They were previously
  // duplicated here, creating a second parallel provider tree so AuthContext toasts
  // and component toasts landed in different containers.
  return (
    <ErrorBoundary>
      <AppShell>
        <OfflineBanner />
        <OfflineIndicator />
        <OfflineConflictResolver />
        <AppRoutes />
      </AppShell>
    </ErrorBoundary>
  )
}

function OfflineBanner() {
  const { isOnline, pendingCount } = useOfflineSync()
  const { t } = useAppT()
  if (isOnline) return null
  return (
    <div
      role="status"
      aria-live="polite"
      style={{
        position: 'fixed',
        top: 0,
        left: 0,
        right: 0,
        zIndex: 'var(--z-banner)',
        background: 'var(--warning)',
        color: '#000',
        textAlign: 'center',
        padding: '6px 12px',
        fontSize: "var(--text-base)",
        fontWeight: 600,
      }}
    >
      {t('offline_indicator.banner_offline')}
      {pendingCount > 0 && ` ${t('offline_indicator.banner_pending', { count: pendingCount })}`}
    </div>
  )
}
