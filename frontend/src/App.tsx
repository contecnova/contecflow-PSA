import { Component, Suspense, lazy } from 'react'
import type { ReactNode } from 'react'
import ErrorBoundary from './components/ErrorBoundary'
import { withRouteBoundary } from './components/RouteBoundary'
import { Routes, Route, Navigate, useLocation, useParams } from 'react-router-dom'
import { useAuth } from './context/AuthContext'
import { paginaDeInicio, puedeAbrir } from './permisos/navegacion'
import Layout from './components/layout/Layout'
import AppShell from './components/layout/AppShell'
import { Button, Spinner } from './components/ui'
import TopProgressBar from './components/layout/TopProgressBar'
import { useAppT } from './hooks/useAppT'
import useOfflineSync from './hooks/useOfflineSync'
import OfflineIndicator from './components/OfflineIndicator'
import {
  SkeletonDashboard, SkeletonTable, SkeletonProjects,
  SkeletonGantt, SkeletonServiceDesk,
  SkeletonFinance,
} from './components/ui/Skeletons'
import './App.estilos.css'

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
import { SECCIONES_DE_AJUSTES } from './pages/settings/catalogoDeAjustes'
const TimesheetsPage         = lazy(() => import('./pages/TimesheetsPage'))
const CapacityPage           = lazy(() => import('./pages/CapacityPage'))
const ProfitabilityPage      = lazy(() => import('./pages/ProfitabilityPage'))
const PipelinePage           = lazy(() => import('./pages/PipelinePage'))
const ContractsPage          = lazy(() => import('./pages/ContractsPage'))
const RisksPage              = lazy(() => import('./pages/RisksPage'))
const SkillsPage             = lazy(() => import('./pages/SkillsPage'))
const AbsencesPage           = lazy(() => import('./pages/AbsencesPage'))
const HorasExtraPage         = lazy(() => import('./pages/HorasExtraPage'))
const ChangesPage            = lazy(() => import('./pages/ChangesPage'))
const DeliverablesPage       = lazy(() => import('./pages/DeliverablesPage'))
const ClientPortalPage       = lazy(() => import('./pages/ClientPortalPage'))
const CalendarPage           = lazy(() => import('./pages/CalendarPage'))
const PortalClientePage      = lazy(() => import('./pages/PortalClientePage'))
const PortalPublicViewPage   = lazy(() => import('./pages/PortalPublicViewPage'))
const ServiceDeskPage        = lazy(() => import('./pages/ServiceDeskPage'))
const InvoicesPage           = lazy(() => import('./pages/InvoicesPage'))
const SprintsPage            = lazy(() => import('./pages/SprintsPage'))
const ExpensesPage           = lazy(() => import('./pages/ExpensesPage'))
const AutomationsPage        = lazy(() => import('./pages/AutomationsPage'))
const RevenuePage            = lazy(() => import('./pages/RevenuePage'))
const ScenariosPage          = lazy(() => import('./pages/ScenariosPage'))
const BudgetsPage            = lazy(() => import('./pages/BudgetsPage'))
const ContecflowAgentPage    = lazy(() => import('./pages/NexusAgentPage'))
const OraclePage             = lazy(() => import('./pages/OraclePage'))
const MeetingsAIPage         = lazy(() => import('./pages/MeetingsAIPage'))
const ContractsAIPage        = lazy(() => import('./pages/ContractsAIPage'))
const SemanticEnginePage     = lazy(() => import('./pages/SemanticEnginePage'))
const ResourceForecastPage   = lazy(() => import('./pages/ResourceForecastPage'))
const ResourceSchedulerPage  = lazy(() => import('./pages/ResourceSchedulerPage'))
const MilestoneBillingPage   = lazy(() => import('./pages/MilestoneBillingPage'))
const ApprovalsPage          = lazy(() => import('./pages/ApprovalsPage'))
const DocumentsPage          = lazy(() => import('./pages/DocumentsPage'))
const TimerPage              = lazy(() => import('./pages/TimerPage'))
const GanttPage              = lazy(() => import('./pages/GanttPage'))
const SubcontractorsPage     = lazy(() => import('./pages/SubcontractorsPage'))
// Migración 191: portal del proveedor (externos contacto de su proveedor).
const PortalDelProveedorPage = lazy(() => import('./pages/proveedores/PortalDelProveedor'))
// Clientes internos (22-11-2026): gestión y portal «Mi departamento».
const ClientesInternosPage = lazy(() => import('./pages/internos/ClientesInternosPage'))
const MiDepartamentoPage = lazy(() => import('./pages/internos/MiDepartamentoPage'))
const WorkflowDesignerPage   = lazy(() => import('./pages/service-desk/WorkflowDesignerPage'))
const WikiPage               = lazy(() => import('./pages/WikiPage'))
const EpicsPage              = lazy(() => import('./pages/EpicsPage'))
const SearchPage             = lazy(() => import('./pages/SearchPage'))
const CumulativeFlowPage     = lazy(() => import('./pages/CumulativeFlowPage'))
const DependenciesPage       = lazy(() => import('./pages/DependenciesPage'))
const EpicGanttPage          = lazy(() => import('./pages/EpicGanttPage'))
const CMDBPage               = lazy(() => import('./pages/CMDBPage'))
const AgentDashboardPage     = lazy(() => import('./pages/AgentDashboardPage'))
const SprintPlanningPage     = lazy(() => import('./pages/SprintPlanningPage'))
const ALMPage                = lazy(() => import('./pages/ALMPage'))
// Licencias y hardware, fase 4: autoservicio para todos y altas y bajas.
const MisEquiposPage         = lazy(() => import('./pages/MisEquiposPage'))
const ALMAltasBajasPage      = lazy(() => import('./pages/ALMAltasBajasPage'))
const ClientsPage            = lazy(() => import('./pages/ClientsPage'))
const RiskScoresPage         = lazy(() => import('./pages/RiskScoresPage'))
const EVMPage                = lazy(() => import('./pages/EVMPage'))
const PortfolioPage          = lazy(() => import('./pages/PortfolioPage'))
// Proyectos — rev. 173: intake de cartera y planificación de recursos
const CarteraIntakePage      = lazy(() => import('./pages/CarteraIntakePage'))
const DemandaPage            = lazy(() => import('./pages/DemandaPage'))
const PlanificacionDeRecursosPage = lazy(() => import('./pages/PlanificacionDeRecursosPage'))
const GitPage                = lazy(() => import('./pages/GitPage'))
const SprintChartsPage       = lazy(() => import('./pages/SprintChartsPage'))
const ESignPage              = lazy(() => import('./pages/ESignPage'))
const ReportBuilderPage      = lazy(() => import('./pages/ReportBuilderPage'))
const NPSPage                = lazy(() => import('./pages/NPSPage'))
const OrgChartPage           = lazy(() => import('./pages/OrgChartPage'))
const OKRsPage               = lazy(() => import('./pages/OKRsPage'))
const PerformanceReviewsPage = lazy(() => import('./pages/PerformanceReviewsPage'))
const TrainingPage           = lazy(() => import('./pages/TrainingPage'))
const InboxPage              = lazy(() => import('./pages/InboxPage'))
const RACIPage               = lazy(() => import('./pages/RACIPage'))
const ChangelogPage          = lazy(() => import('./pages/ChangelogPage'))
const UATPage                = lazy(() => import('./pages/UATPage'))
const IntakeFormPage         = lazy(() => import('./pages/IntakeFormPage'))
const BIPage                 = lazy(() => import('./pages/BIPage'))
const BIProjectDetailPage    = lazy(() => import('./pages/BIProjectDetailPage'))
const DataExplorerPage       = lazy(() => import('./pages/DataExplorerPage'))
const PreguntarALaEmpresaPage = lazy(() => import('./pages/PreguntarALaEmpresaPage'))
const LeccionesPage = lazy(() => import('./pages/LeccionesPage'))
const PredictionsPage        = lazy(() => import('./pages/PredictionsPage'))
const DataPlatformPage       = lazy(() => import('./pages/DataPlatformPage'))
const DataGovernancePage     = lazy(() => import('./pages/DataGovernancePage'))
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
const ChatPage               = lazy(() => import('./pages/ChatPage'))
const CallPage               = lazy(() => import('./pages/CallPage'))

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
  '/tasks','/timesheets','/resources','/resources/planning','/absences','/overtime','/risks','/changes',
  '/deliverables','/contracts','/expenses','/approvals','/invoices',
  '/clients','/alerts','/exports','/import','/skills','/documents',
  '/subcontractors','/rate-cards','/sprint-charts','/cumulative-flow',
  '/risk-scores','/raci','/changelog','/uat','/alm','/cmdb','/reports',
  '/okrs','/performance-reviews','/training','/webhook-log','/notifications',
])
const FINANCE_ROUTES = new Set([
  '/profitability','/revenue','/budgets','/pipeline','/evm','/portfolio','/portfolio/intake',
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
    <div className="app-e1">
      <div className="app-e2" />
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
      <div className="app-e3">
        <div className="u-empty-icon">⚠️</div>
        <h3 className="app-e4">
          {isChunk ? this.props.t('app_errors.page_load_outdated') : this.props.t('app_errors.page_load_failed')}
        </h3>
        <p className="app-e5">
          {isChunk
            ? this.props.t('app_errors.page_outdated_desc')
            : this.props.t('app_errors.page_unexpected_desc')}
        </p>
        <div className="app-e6">
          <Button
            onClick={() => { this.setState({ error: null }); window.location.href = '/login' }}
          >
            {this.props.t('app_errors.go_login')}
          </Button>
          <Button
            variant="secondary"
            onClick={() => {
              if ('caches' in window) caches.keys().then(keys => Promise.all(keys.map(k => caches.delete(k))))
              window.location.reload()
            }}
          >
            {this.props.t('app_errors.reload')}
          </Button>
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
}
/**
 * 19-11-2026 (matriz de permisos): la capacidad que pide cada ruta no se
 * escribe aquí; sale de `permisos/navegacion.ts` (la misma declaración que
 * usa el menú). Además, el bloqueo por módulo del rol (`canOpen`).
 */
function ProtectedRoute({ children }: ProtectedRouteProps) {
  const location = useLocation()
  const { user, loading, puede, canOpen = () => true } = useAuth()
  if (loading) return (
    <div className="app-e1">
      <Spinner size={32} />
    </div>
  )
  if (!user) return <Navigate to="/login" replace />
  if (!puedeAbrir(location.pathname, puede, true) || !canOpen(location.pathname)) {
    return <Navigate to="/403" state={{ from: location.pathname }} replace />
  }
  return <>{children}</>
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
/**
 * 18-11-2026: una pantalla de configuración que tenía ruta propia (`/rate-cards`,
 * `/issue-types`, `/mfa`…) vive ahora en `/settings/<seccion>`. Se conserva la
 * query (`/enterprise?tab=sso` → `/settings/enterprise?tab=sso`) para no romper
 * enlaces ni marcadores.
 */
function RedirigirAAjustes({ seccion }: { seccion: string }) {
  const { search, hash } = useLocation()
  return <Navigate to={`/settings/${seccion}${search}${hash}`} replace />
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
  const { user, puede } = useAuth()
  // Página de inicio según las capacidades (permisos/navegacion.ts → paginaDeInicio).
  const defaultPath = paginaDeInicio(puede)

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
        <ProtectedRoute>
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
        <ProtectedRoute>
          <Layout><ResourcesPage /></Layout>
        </ProtectedRoute>
      } />

      <Route path="/alerts" element={
        <ProtectedRoute>
          <Layout><AlertsPage /></Layout>
        </ProtectedRoute>
      } />

      <Route path="/exports" element={
        <ProtectedRoute>
          <Layout><ExportsPage /></Layout>
        </ProtectedRoute>
      } />

      <Route path="/reports" element={
        <ProtectedRoute>
          <Layout><SafeReports /></Layout>
        </ProtectedRoute>
      } />

      {/* 18-11-2026: toda la configuración en /settings/:seccion (pages/settings/catalogoDeAjustes.tsx).
          La página decide qué secciones ve cada rol; las rutas sueltas de antes redirigen aquí. */}
      <Route path="/settings" element={
        <ProtectedRoute>
          <Layout><SettingsPage /></Layout>
        </ProtectedRoute>
      } />
      <Route path="/settings/:seccion" element={
        <ProtectedRoute>
          <Layout><SettingsPage /></Layout>
        </ProtectedRoute>
      } />
      {SECCIONES_DE_AJUSTES.filter(s => s.rutaAntigua).map(s => (
        <Route key={s.id} path={s.rutaAntigua} element={<RedirigirAAjustes seccion={s.id} />} />
      ))}

      <Route path="/timesheets" element={
        <ProtectedRoute>
          <Layout><TimesheetsPage /></Layout>
        </ProtectedRoute>
      } />

      <Route path="/capacity" element={
        <ProtectedRoute>
          <Layout><CapacityPage /></Layout>
        </ProtectedRoute>
      } />

      <Route path="/profitability" element={
        <ProtectedRoute>
          <Layout><ProfitabilityPage /></Layout>
        </ProtectedRoute>
      } />

      <Route path="/pipeline" element={
        <ProtectedRoute>
          <Layout><PipelinePage /></Layout>
        </ProtectedRoute>
      } />

      <Route path="/contracts" element={
        <ProtectedRoute>
          <Layout><ContractsPage /></Layout>
        </ProtectedRoute>
      } />

      <Route path="/risks" element={
        <ProtectedRoute>
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

      <Route path="/overtime" element={
        <ProtectedRoute>
          <Layout><HorasExtraPage /></Layout>
        </ProtectedRoute>
      } />

      <Route path="/changes" element={
        <ProtectedRoute>
          <Layout><ChangesPage /></Layout>
        </ProtectedRoute>
      } />

      <Route path="/deliverables" element={
        <ProtectedRoute>
          <Layout><DeliverablesPage /></Layout>
        </ProtectedRoute>
      } />

      <Route path="/client-portal" element={
        <ProtectedRoute>
          <Layout><ClientPortalPage /></Layout>
        </ProtectedRoute>
      } />

      <Route path="/support-dashboard" element={
        <ProtectedRoute>
          <Layout><SafeSupportDashboard /></Layout>
        </ProtectedRoute>
      } />

      {/* El externo (subcontractor) entra acotado: el servidor solo le da sus tickets. */}
      <Route path="/service-desk" element={
        <ProtectedRoute>
          <Layout><SafeServiceDesk /></Layout>
        </ProtectedRoute>
      } />

      <Route path="/sd/workflow-designer" element={
        <ProtectedRoute>
          <Layout><SafeWorkflowDesigner /></Layout>
        </ProtectedRoute>
      } />

      {/* External client portal – no Layout, standalone app */}
      <Route path="/invoices" element={<ProtectedRoute><Layout><InvoicesPage /></Layout></ProtectedRoute>} />
      <Route path="/portal" element={<PortalClientePage />} />
      <Route path="/portal/view/:token" element={<PortalPublicViewPage />} />

      <Route path="/sprints" element={<ProtectedRoute><Layout><SprintsPage /></Layout></ProtectedRoute>} />
      <Route path="/expenses" element={<ProtectedRoute><Layout><ExpensesPage /></Layout></ProtectedRoute>} />
      <Route path="/revenue" element={<ProtectedRoute><Layout><RevenuePage /></Layout></ProtectedRoute>} />
      <Route path="/risk-scores" element={<ProtectedRoute><Layout><RiskScoresPage /></Layout></ProtectedRoute>} />
      <Route path="/evm" element={<ProtectedRoute><Layout><EVMPage /></Layout></ProtectedRoute>} />
      <Route path="/portfolio" element={<ProtectedRoute><Layout><PortfolioPage /></Layout></ProtectedRoute>} />
      <Route path="/portfolio/intake" element={<ProtectedRoute><Layout><CarteraIntakePage /></Layout></ProtectedRoute>} />
      <Route path="/demand" element={<ProtectedRoute><Layout><DemandaPage /></Layout></ProtectedRoute>} />
      <Route path="/resources/planning" element={<ProtectedRoute><Layout><PlanificacionDeRecursosPage /></Layout></ProtectedRoute>} />
      <Route path="/git" element={<ProtectedRoute><Layout><GitPage /></Layout></ProtectedRoute>} />
      <Route path="/sprint-charts" element={<ProtectedRoute><Layout><SprintChartsPage /></Layout></ProtectedRoute>} />
      <Route path="/esign" element={<ProtectedRoute><Layout><ESignPage /></Layout></ProtectedRoute>} />
      <Route path="/report-builder" element={<ProtectedRoute><Layout><SafeReportBuilder /></Layout></ProtectedRoute>} />
      <Route path="/nps" element={<ProtectedRoute><Layout><NPSPage /></Layout></ProtectedRoute>} />
      <Route path="/automations" element={<ProtectedRoute><Layout><AutomationsPage /></Layout></ProtectedRoute>} />

      <Route path="/scenarios" element={<ProtectedRoute><Layout><ScenariosPage /></Layout></ProtectedRoute>} />
      <Route path="/budgets" element={<ProtectedRoute><Layout><BudgetsPage /></Layout></ProtectedRoute>} />
      <Route path="/nexus-agent" element={<ProtectedRoute><Layout><SafeContecflowAgent /></Layout></ProtectedRoute>} />
      <Route path="/oracle" element={<ProtectedRoute><Layout><SafeOracle /></Layout></ProtectedRoute>} />
      <Route path="/meetings-ai" element={<ProtectedRoute><Layout><SafeMeetingsAI /></Layout></ProtectedRoute>} />
      <Route path="/contracts-ai" element={<ProtectedRoute><Layout><SafeContractsAI /></Layout></ProtectedRoute>} />
      <Route path="/settings/workflows" element={<Navigate to="/settings/project-workflows" replace />} />
      <Route path="/workflows" element={<Navigate to="/settings/project-workflows" replace />} />
      <Route path="/calendar" element={<ProtectedRoute><Layout><CalendarPage /></Layout></ProtectedRoute>} />
      <Route path="/wiki" element={<ProtectedRoute><Layout><WikiPage/></Layout></ProtectedRoute>}/>
      <Route path="/epics" element={<ProtectedRoute><Layout><EpicsPage/></Layout></ProtectedRoute>}/>
      <Route path="/search" element={<ProtectedRoute><Layout><SearchPage/></Layout></ProtectedRoute>}/>
      <Route path="/cumulative-flow" element={<ProtectedRoute><Layout><CumulativeFlowPage/></Layout></ProtectedRoute>}/>
      <Route path="/dependencies"   element={<ProtectedRoute><Layout><DependenciesPage/></Layout></ProtectedRoute>}/>
      {/* Auditoria 2026-11 (#45): rutas huerfanas. La busqueda de texto completo
          se fusiono en /search (SearchPage) y las etiquetas de la wiki viven en
          /wiki (WikiTagsInline); quedan como redireccion para enlaces viejos. */}
      <Route path="/fts-search"     element={<Navigate to="/search" replace />}/>
      <Route path="/wiki-tags"      element={<Navigate to="/wiki" replace />}/>
      <Route path="/cmdb"              element={<ProtectedRoute><Layout><CMDBPage/></Layout></ProtectedRoute>}/>
      <Route path="/agent-dashboard"   element={<ProtectedRoute><Layout><SafeAgentDashboard/></Layout></ProtectedRoute>}/>
      {/* Revisión 2026-11: «Kanban» era la misma pregunta que Tareas → vista Kanban; ahora es una sola pantalla. */}
      <Route path="/kanban-advanced"   element={<Navigate to="/tasks?view=kanban" replace />}/>
      <Route path="/sprint-planning"   element={<ProtectedRoute><Layout><SprintPlanningPage/></Layout></ProtectedRoute>}/>
      <Route path="/epic-gantt"     element={<ProtectedRoute><Layout><SafeEpicGantt/></Layout></ProtectedRoute>}/>
      {/* Menciones y notificaciones viven en la bandeja (InboxPage, pestanas). */}
      <Route path="/mentions" element={<Navigate to="/inbox?tab=mentions" replace />}/>
      <Route path="/semantic-engine"  element={<ProtectedRoute><Layout><SafeSemanticEngine /></Layout></ProtectedRoute>} />
      <Route path="/resource-forecast" element={<ProtectedRoute><Layout><ResourceForecastPage /></Layout></ProtectedRoute>} />
      <Route path="/resource-scheduler" element={<ProtectedRoute><Layout><ResourceSchedulerPage /></Layout></ProtectedRoute>} />
      <Route path="/milestone-billing" element={<ProtectedRoute><Layout><MilestoneBillingPage /></Layout></ProtectedRoute>} />
      {/* Revisión 2026-11: cualquier usuario interno puede ser aprobador (rol, grupo, departamento, responsable, delegado). */}
      <Route path="/approvals" element={<ProtectedRoute><Layout><ApprovalsPage mode="inbox" /></Layout></ProtectedRoute>} />
      <Route path="/documents" element={<ProtectedRoute><Layout><DocumentsPage /></Layout></ProtectedRoute>} />
      <Route path="/timer" element={<ProtectedRoute><Layout><TimerPage /></Layout></ProtectedRoute>} />
      <Route path="/gantt" element={<ProtectedRoute><Layout><SafeGantt /></Layout></ProtectedRoute>} />
      {/* Nuevas rutas top-level (sustituyen al antiguo /bi) */}
      <Route path="/data-explorer"   element={<ProtectedRoute><Layout><SafeDataExplorer   /></Layout></ProtectedRoute>} />
      <Route path="/ask-company"     element={<ProtectedRoute><Layout><SafePreguntarALaEmpresa /></Layout></ProtectedRoute>} />
      <Route path="/lessons"         element={<ProtectedRoute><Layout><LeccionesPage /></Layout></ProtectedRoute>} />
      <Route path="/predictions"     element={<ProtectedRoute><Layout><SafePredictions    /></Layout></ProtectedRoute>} />
      <Route path="/data-platform"   element={<ProtectedRoute>     <Layout><SafeDataPlatform   /></Layout></ProtectedRoute>} />
      <Route path="/data-governance" element={<ProtectedRoute>     <Layout><SafeDataGovernance /></Layout></ProtectedRoute>} />
      <Route path="/projects/:id/analytics" element={<ProtectedRoute><Layout><SafeBIProjectDetail /></Layout></ProtectedRoute>} />
      {/* Redirects legacy */}
      <Route path="/bi" element={<Navigate to="/executive" replace />} />
      <Route path="/bi/:section" element={<BiLegacyRedirect />} />
      <Route path="/bi/project/:projectId" element={<BiProjectLegacyRedirect />} />
      <Route path="/subcontractors" element={<ProtectedRoute><Layout><SubcontractorsPage /></Layout></ProtectedRoute>} />
      <Route path="/supplier-portal" element={<ProtectedRoute><Layout><PortalDelProveedorPage /></Layout></ProtectedRoute>} />
      <Route path="/internal-clients" element={<ProtectedRoute><Layout><ClientesInternosPage /></Layout></ProtectedRoute>} />
      <Route path="/mi-departamento" element={<ProtectedRoute><Layout><MiDepartamentoPage /></Layout></ProtectedRoute>} />
      <Route path="/finance-dashboard"   element={<ProtectedRoute><Layout><SafeFinanceDashboard /></Layout></ProtectedRoute>} />
      <Route path="/team-dashboard"     element={<ProtectedRoute><Layout><SafeTeamDashboard /></Layout></ProtectedRoute>} />
      <Route path="/clients"             element={<ProtectedRoute><Layout><ClientsPage /></Layout></ProtectedRoute>} />
      <Route path="/alm"        element={<ProtectedRoute><Layout><ALMPage /></Layout></ProtectedRoute>} />
      <Route path="/alm/altas-y-bajas" element={<ProtectedRoute><Layout><ALMAltasBajasPage /></Layout></ProtectedRoute>} />
      <Route path="/my-equipment" element={<ProtectedRoute><Layout><MisEquiposPage /></Layout></ProtectedRoute>} />
      <Route path="/org-chart" element={<ProtectedRoute><Layout><OrgChartPage /></Layout></ProtectedRoute>} />
      <Route path="/okrs"                element={<ProtectedRoute><Layout><OKRsPage /></Layout></ProtectedRoute>} />
      <Route path="/performance-reviews" element={<ProtectedRoute><Layout><PerformanceReviewsPage /></Layout></ProtectedRoute>} />
      <Route path="/training"            element={<ProtectedRoute><Layout><TrainingPage /></Layout></ProtectedRoute>} />
      <Route path="/executive"           element={<ProtectedRoute><Layout><SafeBIPage /></Layout></ProtectedRoute>} />
      <Route path="/inbox"               element={<ProtectedRoute><Layout><InboxPage /></Layout></ProtectedRoute>} />
      <Route path="/notifications"       element={<Navigate to="/inbox?tab=notifications" replace />} />
      <Route path="/raci"                element={<ProtectedRoute><Layout><RACIPage /></Layout></ProtectedRoute>} />
      <Route path="/changelog"           element={<ProtectedRoute><Layout><ChangelogPage /></Layout></ProtectedRoute>} />
      <Route path="/uat"                element={<ProtectedRoute><Layout><UATPage /></Layout></ProtectedRoute>} />
      <Route path="/intake/:token"      element={<IntakeFormPage />} />
      <Route path="/bpm" element={<ProtectedRoute><Layout><BPMPage /></Layout></ProtectedRoute>} />
      <Route path="/chat" element={<ProtectedRoute><Layout><ChatPage /></Layout></ProtectedRoute>} />
      <Route path="/chat/admin" element={<ProtectedRoute><Navigate to="/settings/chat-admin" replace /></ProtectedRoute>} />
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
      className="app-e9"
    >
      {t('offline_indicator.banner_offline')}
      {pendingCount > 0 && ` ${t('offline_indicator.banner_pending', { count: pendingCount })}`}
    </div>
  )
}
