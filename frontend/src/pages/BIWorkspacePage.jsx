/**
 * BIWorkspacePage — BI Hub con navegación por tabs
 *
 * Tabs:
 *   dashboard     → KPIs ejecutivos, gauges, rentabilidad, top proyectos
 *   analytics     → NLP, query builder, viz avanzada, report builder
 *   intelligence  → Forecasting, anomalías, entrega condicional, alertas inteligentes
 *   data-sources  → ETL, O365, conectores, plataforma, streaming
 *   governance    → GDPR, gobernanza, auditoría, linaje, sensibilidad de campos
 *   collaboration → Vistas compartidas, comentarios, bookmarks, dashboard collab
 */
import { useEffect, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useNavigate, useParams } from 'react-router-dom'
import api, {
  dashboardApi,
  biCollaborationApi,
  biIntelligenceApi,
  biPlatformApi,
  biSmartAlertsApi,
  biBookmarksApi,
  biReportBuilderV2Api,
  biGovernanceAuditApi,
} from '../services/api'
import { Spinner, Tabs } from '../components/ui'
import PageShell from '../components/layout/PageShell'
import {
  PieChart as PieChartIcon,
  LayoutDashboard, BarChart2, Brain, Database, Shield, Users2,
} from 'lucide-react'
import { ResponsiveContainer, Sankey, Tooltip as SankeyTooltip } from 'recharts'
import { useAppT, useAppLang } from '../i18n/AppLangContext'
import { COLOR } from '../constants/theme'
import NarrativeCard        from '../components/bi/NarrativeCard'
import AskDataWidget        from '../components/bi/AskDataWidget'
import VisualQueryBuilderWidget from '../components/bi/VisualQueryBuilderWidget'
import BiAdvancedViz        from '../components/bi/BiAdvancedViz'
import BiForecastingPanel   from '../components/bi/BiForecastingPanel'
import BiAnomalyPanel       from '../components/bi/BiAnomalyPanel'
import BiGdprPanel          from '../components/bi/BiGdprPanel'
import BiConditionalDeliveryPanel from '../components/bi/BiConditionalDeliveryPanel'
import BiEtlPanel           from '../components/bi/BiEtlPanel'
import BiDashboardCollabPanel from '../components/bi/BiDashboardCollabPanel'
import BiGovernancePanel    from '../components/bi/BiGovernancePanel'
import BiO365Panel          from '../components/bi/BiO365Panel'
import BiQueryBuilderPanel  from '../components/bi/BiQueryBuilderPanel'

/* ─── Helpers ─────────────────────────────────────────────────────────────── */
function dateRange(days) {
  const d_to   = new Date().toISOString().slice(0, 10)
  const d_from = new Date(Date.now() - days * 86_400_000).toISOString().slice(0, 10)
  return { date_from: d_from, date_to: d_to }
}
const getLocale = (lang) => (lang === 'en' ? 'en-US' : 'es-ES')
function fmtCur(v, lang = 'es') {
  if (v == null) return '—'
  return new Intl.NumberFormat(getLocale(lang), {
    style: 'currency', currency: 'EUR', maximumFractionDigits: 0,
  }).format(v)
}
function toFiniteNumber(value, fallback = 0) {
  if (typeof value === 'number') return Number.isFinite(value) ? value : fallback
  if (typeof value === 'string') {
    const n = Number(value.trim().replace(/\s/g, '').replace(/\.(?=\d{3}(?:\D|$))/g, '').replace(',', '.'))
    return Number.isFinite(n) ? n : fallback
  }
  return fallback
}
function useIsMobile(maxWidth = 900) {
  const [isMobile, setIsMobile] = useState(() =>
    typeof window !== 'undefined' ? window.matchMedia(`(max-width: ${maxWidth}px)`).matches : false
  )
  useEffect(() => {
    if (typeof window === 'undefined') return undefined
    const mq = window.matchMedia(`(max-width: ${maxWidth}px)`)
    const onChange = (e) => setIsMobile(e.matches)
    setIsMobile(mq.matches)
    mq.addEventListener('change', onChange)
    return () => mq.removeEventListener('change', onChange)
  }, [maxWidth])
  return isMobile
}

/* ─── Design tokens ───────────────────────────────────────────────────────── */
const S = {
  card:        { background: 'var(--surface-2)', border: '1px solid var(--surface-4)', borderRadius: 14, overflow: 'hidden' },
  cardPad:     { padding: '20px 24px' },
  sectionTitle:{ fontSize: "var(--text-xs)", fontWeight: 700, color: 'var(--text-3)', textTransform: 'uppercase', letterSpacing: '0.09em', margin: 0 },
  input:       { background: 'var(--surface-3)', border: '1px solid var(--surface-4)', color: 'var(--text-1)', borderRadius: 8, padding: '9px 13px', fontSize: "var(--text-base)", fontFamily: 'inherit', outline: 'none', width: '100%' },
  btnPrimary:  { padding: '7px 16px', borderRadius: 8, background: COLOR.accent, color: '#fff', border: 'none', cursor: 'pointer', fontSize: "var(--text-sm)", fontWeight: 600, fontFamily: 'inherit' },
  btnSecondary:{ padding: '7px 16px', borderRadius: 8, border: '1px solid var(--surface-4)', background: 'transparent', color: 'var(--text-2)', cursor: 'pointer', fontSize: "var(--text-sm)", fontFamily: 'inherit' },
  btnAccentOutline: (c = COLOR.accent) => ({ padding: '7px 14px', borderRadius: 8, border: `1px solid ${c}`, background: `${c}18`, color: c, cursor: 'pointer', fontSize: "var(--text-sm)", fontWeight: 600, fontFamily: 'inherit' }),
}

/* ─── Pure sub-components ─────────────────────────────────────────────────── */
function PeriodButton({ active, label, onClick }) {
  return (
    <button onClick={onClick} style={{
      padding: '7px 18px', borderRadius: 8,
      border: `1px solid ${active ? COLOR.accent : 'var(--surface-4)'}`,
      background: active ? COLOR.accentMuted : 'transparent',
      color: active ? COLOR.accent : 'var(--text-2)',
      fontSize: "var(--text-sm)", fontWeight: 600, cursor: 'pointer', fontFamily: 'inherit', transition: 'all 0.15s',
    }}>{label}</button>
  )
}

function KpiCard({ label, value, sub, color, icon, accentBar }) {
  const bar = accentBar ?? color ?? COLOR.accent
  return (
    <div style={{ ...S.card, display: 'flex', flexDirection: 'column' }}>
      <div style={{ height: 3, background: bar, borderRadius: '14px 14px 0 0' }} />
      <div style={{ ...S.cardPad, flex: 1, display: 'flex', flexDirection: 'column', gap: 6 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          {icon && <span style={{ fontSize: "var(--text-lg-em)", background: `${bar}18`, borderRadius: 8, padding: '5px 7px', lineHeight: 1 }}>{icon}</span>}
          <span style={{ fontSize: "var(--text-2xs)", fontWeight: 700, color: 'var(--text-3)', textTransform: 'uppercase', letterSpacing: '0.09em' }}>{label}</span>
        </div>
        <div style={{ fontSize: "var(--text-34)", fontWeight: 700, color: color || 'var(--text-1)', lineHeight: 1.1, letterSpacing: '-0.5px' }}>{value ?? '—'}</div>
        {sub && <div style={{ fontSize: "var(--text-xs)", color: 'var(--text-3)', lineHeight: 1.4 }}>{sub}</div>}
      </div>
    </div>
  )
}

function RingGauge({ value, color, size = 64 }) {
  const r    = (size - 8) / 2
  const circ = 2 * Math.PI * r
  const progress = Math.min(Math.max(value ?? 0, 0), 100) / 100
  return (
    <svg width={size} height={size} style={{ transform: 'rotate(-90deg)', flexShrink: 0 }}>
      <circle cx={size/2} cy={size/2} r={r} fill="none" stroke="var(--surface-4)" strokeWidth={7} />
      <circle cx={size/2} cy={size/2} r={r} fill="none" stroke={color} strokeWidth={7}
        strokeDasharray={circ} strokeDashoffset={circ * (1 - progress)} strokeLinecap="round" />
    </svg>
  )
}

function GaugeCard({ label, value, color, suffix = '%', sub }) {
  return (
    <div style={{ ...S.card, ...S.cardPad, display: 'flex', alignItems: 'center', gap: 16 }}>
      <div style={{ position: 'relative', flexShrink: 0 }}>
        <RingGauge value={typeof value === 'number' ? value : 0} color={color} size={68} />
        <div style={{ position: 'absolute', inset: 0, display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: "var(--text-sm)", fontWeight: 700, color }}>{value != null ? value : '—'}</div>
      </div>
      <div>
        <div style={{ fontSize: "var(--text-2xs)", fontWeight: 700, color: 'var(--text-3)', textTransform: 'uppercase', letterSpacing: '0.09em', marginBottom: 4 }}>{label}</div>
        <div style={{ fontSize: "var(--text-2xl-em)", fontWeight: 700, color, lineHeight: 1, letterSpacing: '-0.5px' }}>{value != null ? `${value}${suffix}` : '—'}</div>
        {sub && <div style={{ fontSize: "var(--text-xs)", color: 'var(--text-3)', marginTop: 4 }}>{sub}</div>}
      </div>
    </div>
  )
}

function BarRow({ label, count, total, color, fmt }) {
  const pct = total > 0 ? Math.round((count / total) * 100) : 0
  const displayVal = fmt ? fmt(count) : count
  return (
    <div style={{ marginBottom: 14 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 6 }}>
        <span style={{ fontSize: "var(--text-sm)", color: 'var(--text-2)', textTransform: 'capitalize' }}>{label.replace(/_/g, ' ')}</span>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <span style={{ fontSize: "var(--text-xs)", fontWeight: 700, color: 'var(--text-1)', background: 'var(--surface-4)', borderRadius: 6, padding: '2px 7px' }}>{displayVal}</span>
          <span style={{ fontSize: "var(--text-xs)", color: 'var(--text-3)', minWidth: 32, textAlign: 'right' }}>{pct}%</span>
        </div>
      </div>
      <div style={{ height: 7, background: 'var(--surface-4)', borderRadius: 4, overflow: 'hidden' }}>
        <div style={{ width: `${pct}%`, height: '100%', background: color, borderRadius: 4, transition: 'width 0.6s cubic-bezier(0.4,0,0.2,1)' }} />
      </div>
    </div>
  )
}

function ProjectAvatar({ name, code }) {
  const initials = (code || name || '?').slice(0, 2).toUpperCase()
  const colors = [COLOR.accent, COLOR.success, COLOR.warning, COLOR.purple, '#2dd4bf', 'var(--orange)']
  const idx = (name || '').charCodeAt(0) % colors.length
  return (
    <div style={{ width: 32, height: 32, borderRadius: 8, background: `${colors[idx]}22`, border: `1.5px solid ${colors[idx]}44`, display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: "var(--text-xs)", fontWeight: 700, color: colors[idx], flexShrink: 0 }}>
      {initials}
    </div>
  )
}

function MarginBar({ margin, revenue }) {
  const pct   = revenue > 0 ? Math.round((margin / revenue) * 100) : 0
  const color = pct >= 30 ? COLOR.success : pct >= 15 ? COLOR.warning : COLOR.danger
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 8, minWidth: 120 }}>
      <div style={{ flex: 1, height: 5, background: 'var(--surface-4)', borderRadius: 3 }}>
        <div style={{ width: `${Math.max(0, Math.min(pct, 100))}%`, height: '100%', background: color, borderRadius: 3, transition: 'width 0.5s ease' }} />
      </div>
      <span style={{ fontSize: "var(--text-xs)", fontWeight: 700, color, minWidth: 36 }}>{pct}%</span>
    </div>
  )
}

function RevenueFlowSankey({ data }) {
  const nodes = Array.isArray(data?.nodes) ? data.nodes : []
  const links = Array.isArray(data?.links)
    ? data.links
        .map((l) => ({ ...l, source: toFiniteNumber(l?.source, -1), target: toFiniteNumber(l?.target, -1), value: toFiniteNumber(l?.value, 0) }))
        .filter((l) => Number.isInteger(l.source) && Number.isInteger(l.target) && l.source >= 0 && l.target >= 0 && l.source < nodes.length && l.target < nodes.length && l.value > 0)
    : []
  if (!nodes.length || !links.length) return <div style={{ textAlign: 'center', color: 'var(--text-3)', fontSize: "var(--text-sm)", padding: '16px 0' }}>Sin datos</div>
  return (
    <div style={{ width: '100%', height: 240 }}>
      <ResponsiveContainer width="100%" height="100%">
        <Sankey data={{ nodes, links }} nodePadding={30} margin={{ top: 10, right: 18, bottom: 10, left: 18 }} linkCurvature={0.5}>
          <SankeyTooltip />
        </Sankey>
      </ResponsiveContainer>
    </div>
  )
}

function SectionHeading({ title, description }) {
  return (
    <div style={{ marginBottom: 20 }}>
      <h2 style={{ fontSize: "var(--text-md-em)", fontWeight: 700, color: 'var(--text-1)', margin: '0 0 4px' }}>{title}</h2>
      {description && <p style={{ fontSize: "var(--text-sm)", color: 'var(--text-3)', margin: 0 }}>{description}</p>}
    </div>
  )
}

function TabEmpty({ icon, title, description }) {
  return (
    <div style={{ textAlign: 'center', padding: '80px 24px' }}>
      <div style={{ fontSize: "var(--text-6xl)", marginBottom: 16, opacity: 0.35 }}>{icon}</div>
      <div style={{ fontSize: "var(--text-md-em)", fontWeight: 600, marginBottom: 8, color: 'var(--text-2)' }}>{title}</div>
      {description && <div style={{ fontSize: "var(--text-base)", maxWidth: 300, margin: '0 auto', lineHeight: 1.6, color: 'var(--text-3)' }}>{description}</div>}
    </div>
  )
}

/* ─── Tab navigation ──────────────────────────────────────────────────────── */
const TABS = [
  { id: 'dashboard',     label: 'Dashboard',          Icon: LayoutDashboard },
  { id: 'analytics',     label: 'Analytics',          Icon: BarChart2 },
  { id: 'intelligence',  label: 'Intelligence',       Icon: Brain },
  { id: 'data-sources',  label: 'Fuentes de datos',   Icon: Database },
  { id: 'governance',    label: 'Governance',         Icon: Shield },
  { id: 'collaboration', label: 'Colaboración',       Icon: Users2 },
]
const TAB_IDS = new Set(TABS.map((tab) => tab.id))

const HUB_SECTIONS = [
  {
    id: 'dashboard',
    title: 'Dashboard Ejecutivo',
    description: 'KPIs de negocio, salud de proyectos y rentabilidad en una vista operativa.',
  },
  {
    id: 'analytics',
    title: 'Analytics',
    description: 'Exploración de datos con consultas, visualizaciones y report builder.',
  },
  {
    id: 'intelligence',
    title: 'Intelligence',
    description: 'Forecasting, anomalías y alertas inteligentes accionables.',
  },
  {
    id: 'data-sources',
    title: 'Fuentes de Datos',
    description: 'Conectores, ETL, plataforma BI y capacidades de streaming.',
  },
  {
    id: 'governance',
    title: 'Governance',
    description: 'Privacidad, auditoría y trazabilidad de datos de extremo a extremo.',
  },
  {
    id: 'collaboration',
    title: 'Colaboración',
    description: 'Comentarios de widgets, vistas compartidas y bookmarks de equipo.',
  },
]

function HubSectionCard({ section, onOpen }) {
  return (
    <button
      type="button"
      onClick={() => onOpen(section.id)}
      style={{
        ...S.card,
        padding: '18px 20px',
        textAlign: 'left',
        cursor: 'pointer',
        display: 'flex',
        flexDirection: 'column',
        gap: 10,
        background: 'linear-gradient(180deg, var(--surface-2), var(--surface-3))',
      }}
    >
      <div style={{ fontSize: "var(--text-lg)", fontWeight: 700, color: 'var(--text-1)' }}>{section.title}</div>
      <div style={{ fontSize: "var(--text-sm)", color: 'var(--text-2)', lineHeight: 1.5 }}>{section.description}</div>
      <span style={{ fontSize: "var(--text-xs)", fontWeight: 700, color: 'var(--accent)', textTransform: 'uppercase', letterSpacing: '0.06em' }}>
        Abrir modulo
      </span>
    </button>
  )
}

function TabNav({ activeTab, onTabChange }) {
  const items = TABS.map(({ id, label, Icon }) => ({
    id, label, icon: <Icon size={14} />,
  }))
  return (
    <Tabs
      items={items}
      active={activeTab}
      onChange={onTabChange}
      ariaLabel="BI Workspace sections"
      style={{ marginBottom: 24, overflowX: 'auto' }}
    />
  )
}

/* ─── Main component ──────────────────────────────────────────────────────── */
export default function BIWorkspacePage() {
  const t         = useAppT()
  const { lang }  = useAppLang()
  const isMobile  = useIsMobile(900)
  const navigate = useNavigate()
  const { section } = useParams()

  const routeTab = section && TAB_IDS.has(section) ? section : 'hub'

  const [activeTab, setActiveTab] = useState(routeTab)
  const [days,      setDays]      = useState(30)

  useEffect(() => {
    setActiveTab(routeTab)
  }, [routeTab])

  useEffect(() => {
    if (section && routeTab === 'hub') {
      navigate('/bi', { replace: true })
    }
  }, [section, routeTab, navigate])

  function handleTabChange(nextTab) {
    if (!TAB_IDS.has(nextTab)) return
    setActiveTab(nextTab)
    navigate(`/bi/${nextTab}`)
  }

  /* ── Collaboration state ── */
  const [commentWidget,          setCommentWidget]          = useState('kpi_grid')
  const [commentText,            setCommentText]            = useState('')
  const [sharedViewName,         setSharedViewName]         = useState('')
  const [sharedViewsSearch,      setSharedViewsSearch]      = useState('')
  const [sharedViewsSort,        setSharedViewsSort]        = useState('date_desc')
  const [showInactiveSharedViews,setShowInactiveSharedViews]= useState(false)
  const [rulesDraft,             setRulesDraft]             = useState(null)
  const [sharedViewsTick,        setSharedViewsTick]        = useState(0)

  /* ── Data Sources state ── */
  const [phase2Tick,          setPhase2Tick]          = useState(0)
  const [presetId,            setPresetId]            = useState('ops_delivery_mix')
  const [streamLive,          setStreamLive]          = useState(false)
  const [streamSnapshot,      setStreamSnapshot]      = useState(null)
  const [phase3Tick,          setPhase3Tick]          = useState(0)
  const [embedToken,          setEmbedToken]          = useState('')
  const [customConnectorName, setCustomConnectorName] = useState('')
  const [customConnectorEndpoint, setCustomConnectorEndpoint] = useState('')
  const [datasetKey,          setDatasetKey]          = useState('olap.fact_projects')
  const [snapshotDiff,        setSnapshotDiff]        = useState(null)
  const [govRunTick,          setGovRunTick]          = useState(0)

  /* ── Intelligence state ── */
  const [alertsTick,        setAlertsTick]        = useState(0)
  const [newAlertName,      setNewAlertName]       = useState('')
  const [newAlertMetric,    setNewAlertMetric]     = useState('revenue')
  const [newAlertCondition, setNewAlertCondition]  = useState('trend_down')
  const [newAlertSeverity,  setNewAlertSeverity]   = useState('warning')

  /* ── Analytics state ── */
  const [rbv2Tick,              _setRbv2Tick]             = useState(0)
  const [rbv2SelectedPreset,    setRbv2SelectedPreset]    = useState('finance_revenue_by_client')
  const [rbv2PreviewData,       setRbv2PreviewData]       = useState(null)

  /* ── Collaboration (bookmarks) state ── */
  const [bookmarksTick,    setBookmarksTick]    = useState(0)
  const [newBookmarkName,  setNewBookmarkName]  = useState('')

  /* ── Governance state ── */
  const [govAuditTick,         setGovAuditTick]         = useState(0)
  const [govAuditUserFilter,   setGovAuditUserFilter]   = useState('')
  const [newLineageSource,     setNewLineageSource]     = useState('')
  const [newLineageTarget,     setNewLineageTarget]     = useState('')
  const [newFieldName,         setNewFieldName]         = useState('')
  const [newFieldSensitivity,  setNewFieldSensitivity]  = useState('low')
  const [newFieldDataset,      setNewFieldDataset]      = useState('')

  const params = dateRange(days)
  const isHub       = activeTab === 'hub'
  const isDashboard = activeTab === 'dashboard'
  const isCollab    = activeTab === 'collaboration'
  const isIntel     = activeTab === 'intelligence'
  const isDataSrc   = activeTab === 'data-sources'
  const isAnalytics = activeTab === 'analytics'
  const isGov       = activeTab === 'governance'

  /* ── Dashboard queries (always active) ── */
  const { data: kpis,    isLoading: loadingKpis  } = useQuery({
    queryKey: ['bi-exec-kpis', days],
    queryFn:  () => dashboardApi.kpis(params).then(r => r.data).catch(() => ({})),
    staleTime: 60_000,
    enabled: isDashboard,
  })
  const { data: health = [], isLoading: loadingHealth } = useQuery({
    queryKey: ['bi-exec-health', days],
    queryFn:  () => dashboardApi.projectsHealth(params).then(r => r.data).catch(() => []),
    staleTime: 60_000,
    enabled: isDashboard,
  })
  const { data: profitSummary } = useQuery({
    queryKey: ['bi-exec-profit', days],
    queryFn:  () => api.get('/profitability/summary', { params: { ...params, period: 'custom' } }).then(r => r.data).catch(() => null),
    staleTime: 60_000,
    enabled: isDashboard,
  })
  const { data: topProjects = [] } = useQuery({
    queryKey: ['bi-exec-top-projects', days],
    queryFn:  () => api.get('/profitability/projects', { params }).then(r => r.data).catch(() => []),
    staleTime: 60_000,
    enabled: isDashboard,
  })
  const { data: byType = [] } = useQuery({
    queryKey: ['bi-exec-by-type', days],
    queryFn:  () => api.get('/analytics/query/projects_by_type', { params }).then(r => r.data?.rows || []).catch(() => []),
    staleTime: 60_000,
    enabled: isDashboard,
  })
  const { data: utilData } = useQuery({
    queryKey: ['bi-exec-utilization', days],
    queryFn:  () => api.get('/analytics/utilization/advanced', { params }).then(r => r.data).catch(() => null),
    staleTime: 60_000,
    enabled: isDashboard,
  })
  const { data: funnel = [] } = useQuery({
    queryKey: ['bi-exec-funnel', days],
    queryFn:  () => api.get('/analytics/olap/pipeline-funnel').then(r => r.data).catch(() => []),
    staleTime: 60_000,
    enabled: isDashboard,
  })

  /* ── Collaboration queries ── */
  const { data: commentsData, refetch: refetchComments } = useQuery({
    queryKey: ['bi-phase1-comments', commentWidget],
    queryFn:  () => biCollaborationApi.listComments({ dashboard_key: 'executive', widget_id: commentWidget }).then(r => r.data).catch(() => ({ items: [] })),
    staleTime: 15_000, enabled: isCollab,
  })
  const { data: sharedViewsData, refetch: refetchSharedViews } = useQuery({
    queryKey: ['bi-phase3-shared-views', sharedViewsTick, showInactiveSharedViews],
    queryFn:  () => biCollaborationApi.listSharedViews({ include_inactive: showInactiveSharedViews }).then(r => r.data).catch(() => ({ items: [] })),
    staleTime: 15_000, enabled: isCollab,
  })
  const { data: governance } = useQuery({
    queryKey: ['bi-phase1-governance-overview'],
    queryFn:  () => biCollaborationApi.governanceOverview().then(r => r.data).catch(() => null),
    staleTime: 30_000, enabled: isCollab,
  })
  const { data: governanceRules, refetch: refetchRules } = useQuery({
    queryKey: ['bi-phase1-governance-rules'],
    queryFn:  () => biCollaborationApi.governanceRules().then(r => r.data).catch(() => null),
    staleTime: 30_000, enabled: isCollab,
  })
  const { data: governanceRun, refetch: refetchGovRun } = useQuery({
    queryKey: ['bi-phase1-governance-run', govRunTick],
    queryFn:  () => biCollaborationApi.lastGovernanceRun().then(r => r.data?.result || null).catch(() => null),
    staleTime: 10_000, enabled: isCollab,
  })

  /* ── Intelligence queries ── */
  const { data: _forecastRevenue } = useQuery({
    queryKey: ['bi-phase2-forecast'],
    queryFn:  () => biIntelligenceApi.revenueForecast({ months_ahead: 6 }).then(r => r.data).catch(() => null),
    staleTime: 30_000, enabled: isIntel,
  })
  const { data: _revenueAnomalies } = useQuery({
    queryKey: ['bi-phase2-anomalies'],
    queryFn:  () => biIntelligenceApi.revenueAnomalies({ z_threshold: 2.0 }).then(r => r.data).catch(() => ({ items: [] })),
    staleTime: 30_000, enabled: isIntel,
  })
  const { data: alertRules } = useQuery({
    queryKey: ['bi-alert-rules', alertsTick],
    queryFn:  () => biSmartAlertsApi.listRules().then(r => r.data).catch(() => ({ items: [] })),
    staleTime: 30_000, enabled: isIntel,
  })
  const { data: alertHistory } = useQuery({
    queryKey: ['bi-alert-history', alertsTick],
    queryFn:  () => biSmartAlertsApi.getHistory(50).then(r => r.data).catch(() => ({ items: [] })),
    staleTime: 30_000, enabled: isIntel,
  })
  const { data: alertSupportedMetrics } = useQuery({
    queryKey: ['bi-alert-supported-metrics'],
    queryFn:  () => biSmartAlertsApi.supportedMetrics().then(r => r.data).catch(() => ({ metrics: [], conditions: [] })),
    staleTime: 600_000, enabled: isIntel,
  })

  /* ── Data Sources queries ── */
  const { data: connectorsData, refetch: refetchConnectors } = useQuery({
    queryKey: ['bi-phase2-connectors', phase2Tick],
    queryFn:  () => biIntelligenceApi.listConnectors().then(r => r.data).catch(() => ({ items: {} })),
    staleTime: 15_000, enabled: isDataSrc,
  })
  const { data: reportPresets } = useQuery({
    queryKey: ['bi-phase2-report-presets'],
    queryFn:  () => biIntelligenceApi.reportPresets().then(r => r.data).catch(() => ({ items: [] })),
    staleTime: 60_000, enabled: isDataSrc,
  })
  const { data: previewData, refetch: refetchPreview } = useQuery({
    queryKey: ['bi-phase2-preview', presetId, phase2Tick],
    queryFn:  () => biIntelligenceApi.previewPreset({ preset_id: presetId, limit: 20 }).then(r => r.data).catch(() => null),
    staleTime: 20_000, enabled: isDataSrc,
  })
  const { data: deliveryOverview } = useQuery({
    queryKey: ['bi-phase2-delivery', phase2Tick],
    queryFn:  () => biIntelligenceApi.deliveryOverview().then(r => r.data).catch(() => null),
    staleTime: 20_000, enabled: isDataSrc,
  })
  const { data: phase3Manifest } = useQuery({
    queryKey: ['bi-phase3-manifest'],
    queryFn:  () => biPlatformApi.sdkManifest().then(r => r.data).catch(() => null),
    staleTime: 60_000, enabled: isDataSrc,
  })
  const { data: phase3Catalog, refetch: refetchPhase3Catalog } = useQuery({
    queryKey: ['bi-phase3-catalog', phase3Tick],
    queryFn:  () => biPlatformApi.connectorCatalog().then(r => r.data).catch(() => ({ count: 0, items: {} })),
    staleTime: 20_000, enabled: isDataSrc,
  })
  const { data: phase3Custom, refetch: refetchPhase3Custom } = useQuery({
    queryKey: ['bi-phase3-custom', phase3Tick],
    queryFn:  () => biPlatformApi.listCustomConnectors().then(r => r.data).catch(() => ({ items: [] })),
    staleTime: 20_000, enabled: isDataSrc,
  })
  const { data: phase3Lineage, refetch: refetchPhase3Lineage } = useQuery({
    queryKey: ['bi-phase3-lineage', phase3Tick],
    queryFn:  () => biPlatformApi.lineage().then(r => r.data).catch(() => ({ edges: [], audit: [] })),
    staleTime: 20_000, enabled: isDataSrc,
  })
  const { data: phase3Snapshots, refetch: refetchPhase3Snapshots } = useQuery({
    queryKey: ['bi-phase3-snapshots', datasetKey, phase3Tick],
    queryFn:  () => biPlatformApi.listSnapshots(datasetKey).then(r => r.data).catch(() => ({ items: [] })),
    staleTime: 20_000, enabled: isDataSrc,
  })

  /* ── Analytics queries ── */
  const { data: rbv2Presets } = useQuery({
    queryKey: ['bi-rbv2-presets', rbv2Tick],
    queryFn:  () => biReportBuilderV2Api.listPresets({ grouped: false }).then(r => r.data).catch(() => ({ items: [] })),
    staleTime: 60_000, enabled: isAnalytics,
  })

  /* ── Governance queries ── */
  const { data: govAuditData, refetch: _refetchGovAudit } = useQuery({
    queryKey: ['bi-gov-audit', govAuditTick, govAuditUserFilter],
    queryFn:  () => biGovernanceAuditApi.getAccessHistory(
      govAuditUserFilter.trim() ? { user_id: govAuditUserFilter.trim(), limit: 50 } : { limit: 50 }
    ).then(r => r.data).catch(() => ({ items: [] })),
    staleTime: 15_000, enabled: isGov,
  })
  const { data: govLineageData, refetch: refetchGovLineage } = useQuery({
    queryKey: ['bi-gov-lineage', govAuditTick],
    queryFn:  () => biGovernanceAuditApi.listLineage().then(r => r.data).catch(() => ({ items: [] })),
    staleTime: 15_000, enabled: isGov,
  })
  const { data: govFieldData, refetch: refetchGovFields } = useQuery({
    queryKey: ['bi-gov-fields', govAuditTick],
    queryFn:  () => biGovernanceAuditApi.listFieldSensitivity().then(r => r.data).catch(() => ({ items: [] })),
    staleTime: 15_000, enabled: isGov,
  })

  /* ── Bookmarks (collaboration) ── */
  const { data: bookmarks } = useQuery({
    queryKey: ['bi-bookmarks', bookmarksTick],
    queryFn:  () => biBookmarksApi.list().then(r => r.data).catch(() => ({ items: [] })),
    staleTime: 30_000, enabled: isCollab,
  })

  /* ── WebSocket realtime stream ── */
  useEffect(() => {
    if (!streamLive) return undefined
    let ws = null
    let closed = false
    async function connect() {
      try {
        const tokenRes = await biIntelligenceApi.realtimeToken()
        const token = tokenRes?.data?.token
        if (!token) return
        const proto = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
        ws = new WebSocket(`${proto}//${window.location.host}/api/v1/bi/intelligence/realtime/stream?token=${encodeURIComponent(token)}`)
        ws.onmessage = (ev) => {
          try {
            const data = JSON.parse(ev.data)
            if (data?.type === 'bi_intelligence_snapshot') setStreamSnapshot(data)
          } catch (_e) { /* ignore malformed frames */ }
        }
        ws.onclose = () => { if (!closed && streamLive) setTimeout(connect, 2000) }
      } catch (_e) { /* keep UI responsive */ }
    }
    connect()
    return () => { closed = true; if (ws) ws.close() }
  }, [streamLive])

  /* ── Governance rules sync ── */
  useEffect(() => { if (governanceRules) setRulesDraft(governanceRules) }, [governanceRules])

  /* ── Dashboard derived values ── */
  const isLoading    = isDashboard && (loadingKpis || loadingHealth)
  const totalProjects = health.length
  const critProj     = health.filter(p => p.schedule_deviation_days > 0 || p.budget_used_pct > 100).length
  const warnProj     = health.filter(p => p.budget_used_pct > 80 || p.alerts_count > 0).length
  const okProj       = totalProjects - critProj - warnProj
  const onTimePct    = totalProjects > 0 ? Math.round((okProj / totalProjects) * 100) : 0
  const revenue      = toFiniteNumber(profitSummary?.total_revenue, 0)
  const costs        = toFiniteNumber(profitSummary?.total_cost, 0)
  const margin       = revenue - costs
  const marginPct    = revenue > 0 ? Math.round((margin / revenue) * 100) : 0
  const marginColor  = marginPct >= 30 ? COLOR.success : marginPct >= 15 ? COLOR.warning : COLOR.danger
  const onTimeColor  = onTimePct >= 80 ? COLOR.success : onTimePct >= 60 ? COLOR.warning : COLOR.danger
  const totalByType  = byType.reduce((s, r) => s + (r.value || 0), 0)
  const typePalette  = [COLOR.accent, COLOR.success, COLOR.warning, COLOR.purple, '#2dd4bf', 'var(--orange)']
  const healthRows   = [
    { label: 'En tiempo y presupuesto', count: okProj,   color: COLOR.success },
    { label: 'En riesgo',               count: warnProj, color: COLOR.warning },
    { label: 'Crítico',                 count: critProj, color: COLOR.danger  },
  ]
  const utilPctRaw       = utilData?.avg_utilization_pct
  const utilPct          = utilPctRaw == null ? null : toFiniteNumber(utilPctRaw, null)
  const normalizedUtilPct = utilPct == null ? null : Math.max(0, Math.min(100, utilPct))

  const funnelRevenue    = funnel.reduce((sum, f) => sum + toFiniteNumber(f?.weighted_revenue, 0), 0)
  const sourceValue      = Math.max(0, Math.round(toFiniteNumber(funnelRevenue || revenue, 0)))
  const costsValue       = Math.max(0, Math.round(toFiniteNumber(costs, 0)))
  const marginValue      = Math.max(0, Math.round(toFiniteNumber(margin, 0)))
  const outgoingTotal    = costsValue + marginValue
  const normalizedSrc    = outgoingTotal > sourceValue ? outgoingTotal : sourceValue
  const sankeyData       = {
    nodes: [{ name: 'Pipeline' }, { name: 'Ingresos' }, { name: 'Costes' }, { name: 'Margen' }],
    links: [
      { source: 0, target: 1, value: normalizedSrc },
      { source: 1, target: 2, value: costsValue },
      { source: 1, target: 3, value: marginValue },
    ],
  }

  /* ── Collaboration derived ── */
  const comments         = commentsData?.items || []
  const sharedViews      = sharedViewsData?.items || []
  const sharedViewsQuery = sharedViewsSearch.trim().toLowerCase()
  const filteredSharedViews = sharedViews.filter(v => !sharedViewsQuery || String(v?.name || '').toLowerCase().includes(sharedViewsQuery))
  const sortedSharedViews   = [...filteredSharedViews].sort((a, b) => {
    if (sharedViewsSort === 'name_asc')   return String(a?.name || '').localeCompare(String(b?.name || ''), 'es', { sensitivity: 'base' })
    if (sharedViewsSort === 'author_asc') return String(a?.created_by_name || '').localeCompare(String(b?.created_by_name || ''), 'es', { sensitivity: 'base' })
    const tA = Date.parse(a?.created_at || '') || 0
    const tB = Date.parse(b?.created_at || '') || 0
    return sharedViewsSort === 'date_asc' ? tA - tB : tB - tA
  })
  const activeSharedViews   = sharedViews.filter(v => v.active !== false).length
  const inactiveSharedViews = sharedViews.length - activeSharedViews
  const connectors           = Object.entries(connectorsData?.items || {})
  const phase3CatalogEntries = Object.entries(phase3Catalog?.items || {})
  const phase3CustomItems    = phase3Custom?.items || []
  const phase3LineageEdges   = phase3Lineage?.edges || []
  const phase3SnapshotItems  = phase3Snapshots?.items || []
  const govScheduledActive   = typeof governance?.scheduled_reports === 'object'
    ? toFiniteNumber(governance?.scheduled_reports?.active, 0)
    : toFiniteNumber(governance?.scheduled_reports, 0)

  /* ── Handlers ─────────────────────────────────────────────────────────────── */
  async function handleCreateComment() {
    const trimmed = (commentText || '').trim()
    if (!trimmed) return
    await biCollaborationApi.createComment({ dashboard_key: 'executive', widget_id: commentWidget, message: trimmed })
    setCommentText('')
    await refetchComments()
  }
  async function handleResolveComment(commentId) {
    await biCollaborationApi.resolveComment(commentId)
    await refetchComments()
  }
  async function handleCreateSharedView() {
    const name = (sharedViewName || '').trim()
    if (!name) return
    await biCollaborationApi.createSharedView({ name, dashboard_key: 'executive', filters: { days, widget_id: commentWidget } })
    setSharedViewName('')
    setSharedViewsTick(x => x + 1)
    await refetchSharedViews()
  }
  async function handleToggleSharedView(view) {
    await biCollaborationApi.patchSharedView(view.id, { active: !view.active })
    setSharedViewsTick(x => x + 1)
    await refetchSharedViews()
  }
  function handleApplySharedView(view) {
    const f = view?.filters || {}
    const nd = toFiniteNumber(f.days, days)
    if (nd > 0) setDays(nd)
    if (typeof f.widget_id === 'string' && f.widget_id.trim()) setCommentWidget(f.widget_id)
  }
  async function handleRunGovernance() {
    await biCollaborationApi.runGovernanceChecks()
    setGovRunTick(x => x + 1)
    await refetchGovRun()
  }
  async function _handleSaveGovernanceRules() {
    if (!rulesDraft) return
    await biCollaborationApi.updateGovernanceRules(rulesDraft)
    await refetchRules()
  }
  async function handleToggleConnector(name, enabled) {
    await biIntelligenceApi.patchConnector(name, { enabled })
    setPhase2Tick(x => x + 1)
    await refetchConnectors()
  }
  async function handleSyncConnector(name) {
    await biIntelligenceApi.syncConnector(name)
    setPhase2Tick(x => x + 1)
    await refetchConnectors()
  }
  async function handleIssueEmbedToken() {
    const res = await biPlatformApi.embedToken({ dashboard_key: 'executive', expires_minutes: 60 })
    setEmbedToken(res?.data?.token || '')
  }
  async function handleToggleCatalogConnector(name, enabled) {
    await biPlatformApi.patchCatalogConnector(name, { enabled })
    setPhase3Tick(x => x + 1)
    await refetchPhase3Catalog()
  }
  async function handleCreateCustomConnector() {
    const name     = customConnectorName.trim()
    const endpoint = customConnectorEndpoint.trim()
    if (!name || !endpoint) return
    await biPlatformApi.createCustomConnector({ name, endpoint, kind: 'rest', auth_type: 'api_key', enabled: true })
    setCustomConnectorName(''); setCustomConnectorEndpoint('')
    setPhase3Tick(x => x + 1)
    await refetchPhase3Custom()
  }
  async function handleTestCustomConnector(id) {
    await biPlatformApi.testCustomConnector(id)
    setPhase3Tick(x => x + 1)
    await refetchPhase3Custom()
  }
  async function handleCreateSnapshot() {
    await biPlatformApi.createSnapshot(datasetKey, { payload: { captured_at: new Date().toISOString(), revenue, margin, projects: totalProjects } })
    setPhase3Tick(x => x + 1)
    await refetchPhase3Snapshots()
  }
  async function handleDiffLastSnapshots() {
    const items = phase3Snapshots?.items || []
    if (items.length < 2) return
    const fromId = items[items.length - 2]?.id
    const toId   = items[items.length - 1]?.id
    if (!fromId || !toId) return
    const res = await biPlatformApi.diffSnapshots(datasetKey, fromId, toId)
    setSnapshotDiff(res?.data || null)
  }
  async function handleLogGovAuditEvent() {
    await biGovernanceAuditApi.logAccessEvent({ user_id: govAuditUserFilter.trim() || 'console', resource: 'bi_dashboard', action: 'view' }).catch(() => null)
    setGovAuditTick(x => x + 1)
  }
  async function handleAddLineageEdge() {
    const src = newLineageSource.trim()
    const tgt = newLineageTarget.trim()
    if (!src || !tgt) return
    await biGovernanceAuditApi.trackLineage({ source_table: src, target_table: tgt }).catch(() => null)
    setNewLineageSource(''); setNewLineageTarget('')
    setGovAuditTick(x => x + 1)
  }
  async function handleUpsertFieldSensitivity() {
    const field   = newFieldName.trim()
    const dataset = newFieldDataset.trim()
    if (!field || !dataset) return
    await biGovernanceAuditApi.upsertFieldSensitivity({ dataset_id: dataset, field_name: field, sensitivity: newFieldSensitivity }).catch(() => null)
    setNewFieldName(''); setNewFieldDataset('')
    setGovAuditTick(x => x + 1)
  }

  /* ── Render ───────────────────────────────────────────────────────────────── */
  return (
    <PageShell style={isMobile ? { paddingLeft: 14, paddingRight: 14, paddingTop: 14, paddingBottom: 14 } : undefined}>

      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', flexWrap: 'wrap', gap: 16, marginBottom: 24 }}>
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <div style={{ width: 36, height: 36, borderRadius: 10, background: 'var(--accent-muted)', border: '1px solid rgba(79,142,247,0.25)', display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--accent)', flexShrink: 0 }}>
              <PieChartIcon size={18} />
            </div>
            <h1 style={{ fontSize: "var(--text-xl-em)", fontWeight: 700, color: 'var(--text-1)', letterSpacing: '-0.01em', lineHeight: 1.2, margin: 0 }}>
              {t('bi.title')}
            </h1>
          </div>
          <p style={{ margin: '8px 0 0', fontSize: "var(--text-base)", color: 'var(--text-2)', paddingLeft: 46 }}>
            {isHub ? 'Centro de analítica: selecciona un módulo para trabajar con foco.' : `${t('bi.subtitle')} · últimos ${days} días`}
          </p>
        </div>
        {!isHub && (
          <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', justifyContent: isMobile ? 'flex-start' : 'flex-end' }}>
            {[7, 30, 90, 365].map(d => (
              <PeriodButton key={d} active={days === d} label={d === 365 ? '1a' : `${d}d`} onClick={() => setDays(d)} />
            ))}
          </div>
        )}
      </div>

      {/* Tab navigation */}
      <TabNav activeTab={activeTab} onTabChange={handleTabChange} />

      {activeTab === 'hub' && (
        <div style={{ display: 'grid', gridTemplateColumns: isMobile ? '1fr' : 'repeat(2, minmax(320px, 1fr))', gap: 14 }}>
          {HUB_SECTIONS.map((item) => (
            <HubSectionCard key={item.id} section={item} onOpen={handleTabChange} />
          ))}
        </div>
      )}

      {/* ══════════════════════ DASHBOARD TAB ══════════════════════ */}
      {activeTab === 'dashboard' && (
        isLoading
          ? <div style={{ display: 'flex', justifyContent: 'center', padding: '80px 0' }}><Spinner /></div>
          : (!totalProjects && !revenue)
            ? <TabEmpty icon="📊" title="Sin datos ejecutivos" description="Crea proyectos y registra actividad para ver el dashboard aquí" />
            : (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>

                {/* KPI row */}
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(160px, 1fr))', gap: 14 }}>
                  <KpiCard icon="⬡" label={t('bi.active_projects')} value={totalProjects} color="var(--text-1)" accentBar={COLOR.accent} />
                  <KpiCard icon="🚨" label={t('bi.critical_projects')} value={critProj} color={critProj > 0 ? COLOR.danger : COLOR.success} accentBar={critProj > 0 ? COLOR.danger : COLOR.success} sub={critProj > 0 ? 'Fuera de plazo o presupuesto' : 'Sin proyectos críticos'} />
                  <KpiCard icon="▦"  label={t('bi.overdue_tasks')} value={kpis?.tasks_overdue ?? 0} color={(kpis?.tasks_overdue ?? 0) > 0 ? COLOR.warning : COLOR.success} accentBar={(kpis?.tasks_overdue ?? 0) > 0 ? COLOR.warning : COLOR.success} sub={t('bi.need_attention')} />
                  <KpiCard icon="💰" label={t('bi.budget_used')} value={kpis?.total_budget > 0 ? `${Math.round((kpis.total_spent / kpis.total_budget) * 100)}%` : '—'} color={COLOR.warning} accentBar={COLOR.warning} sub={`${fmtCur(kpis?.total_spent ?? 0, lang)} gastado`} />
                  <KpiCard icon="⏱" label={t('bi.hours_this_week')} value={kpis?.hours_logged_this_week?.toFixed(0) ?? '0'} color="var(--sky-blue)" accentBar="var(--sky-blue)" sub="horas imputadas esta semana" />
                  <KpiCard icon="🎫" label={t('bi.open_tickets')} value={kpis?.tasks_open ?? 0} color={COLOR.purple} accentBar={COLOR.purple} sub={t('bi.service_desk_short')} />
                </div>

                {/* Gauges */}
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: 14 }}>
                  <GaugeCard label="Proyectos a tiempo" value={onTimePct} color={onTimeColor} sub={onTimePct >= 80 ? 'Excelente estado' : onTimePct >= 60 ? 'Aceptable' : 'Requiere atención'} />
                  <GaugeCard label="Margen bruto"       value={marginPct} color={marginColor} sub={`${fmtCur(margin, lang)} de ${fmtCur(revenue, lang)}`} />
                  {normalizedUtilPct != null && (
                    <GaugeCard label="Utilización equipo" value={Math.round(normalizedUtilPct)} color={normalizedUtilPct >= 70 ? COLOR.success : normalizedUtilPct >= 50 ? COLOR.warning : COLOR.danger} sub={normalizedUtilPct >= 70 ? 'Buen aprovechamiento' : 'Capacidad disponible'} />
                  )}
                </div>

                {/* Charts */}
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))', gap: 14 }}>
                  <div style={S.card}>
                    <div style={{ ...S.cardPad, borderBottom: '1px solid var(--surface-4)' }}><div style={S.sectionTitle}>Proyectos por tipo</div></div>
                    <div style={S.cardPad}>
                      {byType.length === 0
                        ? <div style={{ textAlign: 'center', color: 'var(--text-3)', fontSize: "var(--text-sm)", padding: '16px 0' }}>Sin datos</div>
                        : byType.map((row, i) => (
                            <BarRow key={row.label} label={row.label || 'Sin tipo'} count={row.value || 0} total={totalByType} color={typePalette[i % typePalette.length]} />
                          ))
                      }
                    </div>
                  </div>
                  <div style={S.card}>
                    <div style={{ ...S.cardPad, borderBottom: '1px solid var(--surface-4)' }}><div style={S.sectionTitle}>Estado de salud</div></div>
                    <div style={S.cardPad}>
                      {totalProjects === 0
                        ? <div style={{ textAlign: 'center', color: 'var(--text-3)', fontSize: "var(--text-sm)", padding: '16px 0' }}>Sin datos</div>
                        : healthRows.map(row => <BarRow key={row.label} label={row.label} count={row.count} total={totalProjects} color={row.color} />)
                      }
                    </div>
                  </div>
                </div>

                {/* Revenue flow Sankey */}
                <div style={S.card}>
                  <div style={{ ...S.cardPad, borderBottom: '1px solid var(--surface-4)' }}><div style={S.sectionTitle}>Flujo de rentabilidad</div></div>
                  <div style={S.cardPad}><RevenueFlowSankey data={sankeyData} /></div>
                </div>

                {/* Revenue KPIs */}
                {revenue > 0 && (
                  <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: 14 }}>
                    <KpiCard icon="📈" label="Ingresos totales"  value={fmtCur(revenue, lang)} color={COLOR.accent}  accentBar={COLOR.accent} />
                    <KpiCard icon="💸" label="Costes totales"    value={fmtCur(costs, lang)}   color={COLOR.warning} accentBar={COLOR.warning} />
                    <KpiCard icon="✅" label="Margen bruto"      value={fmtCur(margin, lang)}  color={margin >= 0 ? COLOR.success : COLOR.danger} accentBar={margin >= 0 ? COLOR.success : COLOR.danger} sub={`${marginPct}% de margen`} />
                  </div>
                )}

                {/* Top projects */}
                {topProjects.length > 0 && (
                  <div style={S.card}>
                    <div style={{ ...S.cardPad, borderBottom: '1px solid var(--surface-4)', display: 'flex', alignItems: 'center', gap: 10 }}>
                      <div style={S.sectionTitle}>Rentabilidad por proyecto</div>
                      <span style={{ fontSize: "var(--text-2xs)", fontWeight: 700, color: 'var(--text-3)', background: 'var(--surface-4)', borderRadius: 12, padding: '2px 8px', marginTop: -14 }}>{topProjects.length}</span>
                    </div>
                    <div style={{ overflowX: 'auto' }}>
                      <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                        <thead>
                          <tr style={{ background: 'var(--surface-3)' }}>
                            {['Proyecto', 'Cliente', 'Ingresos', 'Costes', 'Margen', 'Estado'].map((col, i) => (
                              <th key={col} style={{ padding: '10px 16px', textAlign: i === 0 ? 'left' : 'center', fontSize: "var(--text-2xs)", fontWeight: 700, color: 'var(--text-3)', textTransform: 'uppercase', letterSpacing: '0.08em', whiteSpace: 'nowrap' }}>{col}</th>
                            ))}
                          </tr>
                        </thead>
                        <tbody>
                          {topProjects.slice(0, 10).map((p, idx) => {
                            const rev  = p.revenue_actual ?? p.budget_amount ?? 0
                            const cost = p.cost_actual ?? 0
                            const mgn  = rev - cost
                            const statusColor = p.status === 'active' ? COLOR.accent : p.status === 'completed' ? COLOR.success : 'var(--text-3)'
                            return (
                              <tr key={p.project_id || p.id} style={{ borderBottom: '1px solid var(--surface-4)', background: idx % 2 === 0 ? 'transparent' : 'var(--surface-3)08' }}>
                                <td style={{ padding: '12px 16px' }}>
                                  <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                                    <ProjectAvatar name={p.project_name || p.name} code={p.project_code || p.code} />
                                    <div>
                                      <div style={{ fontSize: "var(--text-base)", fontWeight: 500, color: 'var(--text-1)' }}>{p.project_name || p.name}</div>
                                      {(p.project_code || p.code) && <div style={{ fontSize: "var(--text-2xs)", color: 'var(--text-3)' }}>{p.project_code || p.code}</div>}
                                    </div>
                                  </div>
                                </td>
                                <td style={{ padding: '12px 16px', textAlign: 'center' }}><span style={{ fontSize: "var(--text-sm)", color: 'var(--text-2)' }}>{p.client_name || '—'}</span></td>
                                <td style={{ padding: '12px 16px', textAlign: 'center' }}><span style={{ fontSize: "var(--text-base)", fontWeight: 600, color: 'var(--text-1)' }}>{fmtCur(rev, lang)}</span></td>
                                <td style={{ padding: '12px 16px', textAlign: 'center' }}><span style={{ fontSize: "var(--text-sm)", fontWeight: 600, color: 'var(--text-2)', background: 'var(--surface-4)', padding: '3px 8px', borderRadius: 6, whiteSpace: 'nowrap' }}>{fmtCur(cost, lang)}</span></td>
                                <td style={{ padding: '12px 16px', minWidth: 160 }}><div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center' }}><MarginBar margin={mgn} revenue={rev} /></div></td>
                                <td style={{ padding: '12px 16px', textAlign: 'center' }}>
                                  <span style={{ display: 'inline-flex', alignItems: 'center', gap: 4, fontSize: "var(--text-xs)", fontWeight: 700, color: statusColor, background: `${statusColor}18`, border: `1px solid ${statusColor}30`, borderRadius: 6, padding: '3px 9px', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                                    {p.status || '—'}
                                  </span>
                                </td>
                              </tr>
                            )
                          })}
                        </tbody>
                      </table>
                    </div>
                  </div>
                )}
              </div>
            )
      )}

      {/* ══════════════════════ ANALYTICS TAB ══════════════════════ */}
      {activeTab === 'analytics' && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
          <SectionHeading title="Exploración de datos" description="Consultas en lenguaje natural, query builder visual y visualizaciones avanzadas" />

          <div style={{ display: 'grid', gridTemplateColumns: isMobile ? '1fr' : 'repeat(auto-fit, minmax(360px, 1fr))', gap: 14 }}>
            <NarrativeCard lang={lang} />
            <AskDataWidget />
            <VisualQueryBuilderWidget />
          </div>

          <BiAdvancedViz />
          <BiQueryBuilderPanel />

          {/* Report Builder v2 */}
          <div style={S.card}>
            <div style={{ ...S.cardPad, borderBottom: '1px solid var(--surface-4)', display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: 8 }}>
              <span style={{ fontWeight: 700, fontSize: '1rem' }}>Report Builder — Presets</span>
              <span style={{ fontSize: "var(--text-xs)", color: 'var(--text-3)' }}>{(rbv2Presets?.items || []).length} presets disponibles</span>
            </div>
            <div style={S.cardPad}>
              <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginBottom: 14 }}>
                {(rbv2Presets?.items || []).slice(0, 8).map(p => (
                  <button key={p.id} onClick={() => setRbv2SelectedPreset(p.id)}
                    style={{ padding: '5px 14px', borderRadius: 20, fontSize: "var(--text-xs)", cursor: 'pointer', fontFamily: 'inherit', border: `1.5px solid ${rbv2SelectedPreset === p.id ? COLOR.accent : 'var(--surface-4)'}`, background: rbv2SelectedPreset === p.id ? `${COLOR.accent}18` : 'transparent', color: rbv2SelectedPreset === p.id ? COLOR.accent : 'var(--text-2)', fontWeight: rbv2SelectedPreset === p.id ? 700 : 400 }}>
                    {p.name}
                  </button>
                ))}
                {(rbv2Presets?.items || []).length > 8 && <span style={{ fontSize: "var(--text-xs)", color: 'var(--text-3)', alignSelf: 'center' }}>+{(rbv2Presets?.items || []).length - 8} más</span>}
              </div>
              <div style={{ display: 'flex', gap: 10, marginBottom: 14 }}>
                <button onClick={async () => { try { const res = await biReportBuilderV2Api.preview(rbv2SelectedPreset, 10); setRbv2PreviewData(res.data) } catch (_e) { /* ignore */ } }}
                  style={S.btnPrimary}>Vista previa</button>
                <button onClick={async () => { try { const res = await biReportBuilderV2Api.export(rbv2SelectedPreset, 'json'); const blob = new Blob([JSON.stringify(res.data, null, 2)], { type: 'application/json' }); const url = URL.createObjectURL(blob); const a = document.createElement('a'); a.href = url; a.download = res.data.filename || 'report.json'; a.click(); URL.revokeObjectURL(url) } catch (_e) { /* ignore */ } }}
                  style={{ ...S.btnPrimary, background: COLOR.success }}>Exportar JSON</button>
              </div>
              {rbv2PreviewData && (
                <div style={{ overflowX: 'auto' }}>
                  <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: "var(--text-sm)" }}>
                    <thead>
                      <tr style={{ background: 'var(--surface-3)' }}>
                        {(rbv2PreviewData.columns || []).map(c => (
                          <th key={c} style={{ padding: '8px 12px', textAlign: 'left', color: 'var(--text-2)', fontWeight: 700, fontSize: "var(--text-xs)", textTransform: 'uppercase', letterSpacing: '0.06em', borderBottom: '1px solid var(--surface-4)' }}>{c.replace(/_/g, ' ')}</th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {(rbv2PreviewData.rows || []).map((row, ri) => (
                        <tr key={ri} style={{ borderBottom: '1px solid var(--surface-4)' }}>
                          {(rbv2PreviewData.columns || []).map(c => <td key={c} style={{ padding: '8px 12px', color: 'var(--text-1)' }}>{row[c] ?? '—'}</td>)}
                        </tr>
                      ))}
                      {!(rbv2PreviewData.rows || []).length && (
                        <tr><td colSpan={(rbv2PreviewData.columns || []).length || 1} style={{ padding: 16, textAlign: 'center', color: 'var(--text-3)' }}>Sin datos para este preset</td></tr>
                      )}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      {/* ══════════════════════ INTELLIGENCE TAB ══════════════════════ */}
      {activeTab === 'intelligence' && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
          <SectionHeading title="Inteligencia predictiva" description="Forecasting, detección de anomalías, entrega condicional y alertas inteligentes" />

          <BiForecastingPanel />
          <BiAnomalyPanel />
          <BiConditionalDeliveryPanel />

          {/* Smart Alerts */}
          <div>
            <SectionHeading title="Alertas inteligentes" description="Define reglas de alerta basadas en métricas y recibe notificaciones automáticas" />
            <div style={{ display: 'grid', gridTemplateColumns: isMobile ? '1fr' : '1fr 1fr', gap: 14 }}>

              {/* Alert rules */}
              <div style={S.card}>
                <div style={{ ...S.cardPad, borderBottom: '1px solid var(--surface-4)', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                  <span style={{ fontWeight: 700, fontSize: '0.95rem' }}>Reglas de alerta</span>
                  <button onClick={async () => { try { await biSmartAlertsApi.evaluate(); setAlertsTick(x => x + 1) } catch (_e) { /* ignore */ } }}
                    style={{ ...S.btnPrimary, padding: '5px 14px', fontSize: "var(--text-xs)" }}>Evaluar ahora</button>
                </div>
                <div style={S.cardPad}>
                  <div style={{ display: 'flex', gap: 8, marginBottom: 14, flexWrap: 'wrap' }}>
                    <input value={newAlertName} onChange={e => setNewAlertName(e.target.value)} placeholder="Nombre de la regla"
                      style={{ ...S.input, flex: 1, minWidth: 120 }} />
                    <select value={newAlertMetric} onChange={e => setNewAlertMetric(e.target.value)} style={{ ...S.input, width: 'auto' }}>
                      {(alertSupportedMetrics?.metrics || [{ key: 'revenue', label: 'Revenue' }]).map(m => <option key={m.key} value={m.key}>{m.label}</option>)}
                    </select>
                    <select value={newAlertCondition} onChange={e => setNewAlertCondition(e.target.value)} style={{ ...S.input, width: 'auto' }}>
                      {(alertSupportedMetrics?.conditions || ['trend_down', 'trend_up', 'anomaly', 'threshold_above', 'threshold_below']).map(c => <option key={c} value={c}>{c.replace(/_/g, ' ')}</option>)}
                    </select>
                    <select value={newAlertSeverity} onChange={e => setNewAlertSeverity(e.target.value)} style={{ ...S.input, width: 'auto' }}>
                      {['info', 'warning', 'critical'].map(s => <option key={s} value={s}>{s}</option>)}
                    </select>
                    <button onClick={async () => { if (!newAlertName.trim()) return; try { await biSmartAlertsApi.createRule({ name: newAlertName, metric_key: newAlertMetric, condition: newAlertCondition, severity: newAlertSeverity }); setNewAlertName(''); setAlertsTick(x => x + 1) } catch (_e) { /* ignore */ } }}
                      style={S.btnPrimary}>+ Crear</button>
                  </div>
                  {(alertRules?.items || []).map(rule => (
                    <div key={rule.id} style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '8px 0', borderBottom: '1px solid var(--surface-4)' }}>
                      <div style={{ width: 8, height: 8, borderRadius: '50%', background: rule.severity === 'critical' ? COLOR.danger : rule.severity === 'warning' ? COLOR.warning : COLOR.success, flexShrink: 0 }} />
                      <div style={{ flex: 1 }}>
                        <div style={{ fontSize: "var(--text-sm)", fontWeight: 600, color: 'var(--text-1)' }}>{rule.name}</div>
                        <div style={{ fontSize: "var(--text-2xs)", color: 'var(--text-3)' }}>{rule.metric_key} · {rule.condition.replace(/_/g, ' ')}</div>
                      </div>
                      <span style={{ fontSize: "var(--text-2xs)", padding: '2px 8px', borderRadius: 10, background: rule.enabled ? `${COLOR.success}18` : 'var(--surface-4)', color: rule.enabled ? COLOR.success : 'var(--text-3)', fontWeight: 700 }}>
                        {rule.enabled ? 'activa' : 'pausada'}
                      </span>
                      <button onClick={async () => { try { await biSmartAlertsApi.deleteRule(rule.id); setAlertsTick(x => x + 1) } catch (_e) { /* ignore */ } }}
                        style={{ ...S.btnSecondary, padding: '3px 10px', fontSize: "var(--text-xs)" }}>✕</button>
                    </div>
                  ))}
                  {!(alertRules?.items || []).length && (
                    <div style={{ textAlign: 'center', color: 'var(--text-3)', fontSize: "var(--text-sm)", padding: '16px 0' }}>
                      Sin reglas.{' '}
                      <button onClick={async () => { try { await biSmartAlertsApi.seedDefaults(); setAlertsTick(x => x + 1) } catch (_e) { /* ignore */ } }}
                        style={{ background: 'none', border: 'none', color: COLOR.accent, cursor: 'pointer', fontSize: "var(--text-sm)", fontWeight: 600, fontFamily: 'inherit' }}>
                        Cargar por defecto
                      </button>
                    </div>
                  )}
                </div>
              </div>

              {/* Alert history */}
              <div style={S.card}>
                <div style={{ ...S.cardPad, borderBottom: '1px solid var(--surface-4)' }}>
                  <span style={{ fontWeight: 700, fontSize: '0.95rem' }}>Historial de alertas</span>
                </div>
                <div style={{ ...S.cardPad, maxHeight: 320, overflowY: 'auto' }}>
                  {!(alertHistory?.items || []).length && <div style={{ textAlign: 'center', color: 'var(--text-3)', fontSize: "var(--text-sm)", padding: '16px 0' }}>Sin alertas disparadas</div>}
                  {[...(alertHistory?.items || [])].reverse().map(entry => (
                    <div key={entry.id} style={{ padding: '10px 0', borderBottom: '1px solid var(--surface-4)', display: 'flex', gap: 10, alignItems: 'flex-start' }}>
                      <div style={{ width: 8, height: 8, borderRadius: '50%', marginTop: 4, background: entry.severity === 'critical' ? COLOR.danger : entry.severity === 'warning' ? COLOR.warning : COLOR.success, flexShrink: 0 }} />
                      <div style={{ flex: 1 }}>
                        <div style={{ fontSize: "var(--text-sm)", fontWeight: 600, color: 'var(--text-1)' }}>{entry.rule_name}</div>
                        <div style={{ fontSize: "var(--text-2xs)", color: 'var(--text-3)' }}>{entry.metric_key} · {(entry.condition || '').replace(/_/g, ' ')} · {new Date(entry.triggered_at).toLocaleDateString('es-ES')}</div>
                        {entry.correlated?.length > 0 && <div style={{ fontSize: "var(--text-2xs)", color: COLOR.warning, marginTop: 2 }}>↔ Correlada con: {entry.correlated.map(c => c.metric_key).join(', ')}</div>}
                      </div>
                      {!entry.acknowledged
                        ? <button onClick={async () => { try { await biSmartAlertsApi.acknowledge(entry.id); setAlertsTick(x => x + 1) } catch (_e) { /* ignore */ } }}
                            style={{ padding: '3px 10px', borderRadius: 6, border: `1px solid ${COLOR.accent}`, background: 'transparent', color: COLOR.accent, cursor: 'pointer', fontSize: "var(--text-2xs)", fontWeight: 600, flexShrink: 0, fontFamily: 'inherit' }}>ACK</button>
                        : <span style={{ fontSize: "var(--text-2xs)", color: COLOR.success, fontWeight: 600, flexShrink: 0 }}>✓</span>
                      }
                    </div>
                  ))}
                </div>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* ══════════════════════ DATA SOURCES TAB ══════════════════════ */}
      {activeTab === 'data-sources' && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
          <SectionHeading title="Fuentes de datos e integraciones" description="ETL, conectores de datos, plataforma de embedding y streaming en tiempo real" />

          <BiEtlPanel />
          <BiO365Panel />

          {/* Phase 2: Connectors */}
          {connectors.length > 0 && (
            <div style={S.card}>
              <div style={{ ...S.cardPad, borderBottom: '1px solid var(--surface-4)' }}><div style={S.sectionTitle}>Conectores de datos activos</div></div>
              <div style={{ ...S.cardPad, display: 'flex', flexDirection: 'column', gap: 10 }}>
                {connectors.map(([name, cfg]) => (
                  <div key={name} style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '8px 12px', background: 'var(--surface-3)', borderRadius: 8 }}>
                    <div style={{ width: 8, height: 8, borderRadius: '50%', background: cfg.enabled ? COLOR.success : 'var(--text-4)', flexShrink: 0 }} />
                    <div style={{ flex: 1 }}>
                      <div style={{ fontSize: "var(--text-sm)", fontWeight: 600, color: 'var(--text-1)' }}>{name}</div>
                      <div style={{ fontSize: "var(--text-2xs)", color: 'var(--text-3)' }}>{cfg.last_sync_at ? `Último sync: ${new Date(cfg.last_sync_at).toLocaleString(getLocale(lang))}` : 'Sin sincronizar'}</div>
                    </div>
                    <button onClick={() => handleToggleConnector(name, !cfg.enabled)} style={S.btnSecondary}>{cfg.enabled ? 'Desactivar' : 'Activar'}</button>
                    <button onClick={() => handleSyncConnector(name)} style={S.btnAccentOutline()}>Sync</button>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Phase 2: Report presets + delivery + streaming */}
          <div style={{ display: 'grid', gridTemplateColumns: isMobile ? '1fr' : '1fr 1fr', gap: 14 }}>
            <div style={S.card}>
              <div style={{ ...S.cardPad, borderBottom: '1px solid var(--surface-4)' }}><div style={S.sectionTitle}>Report presets — Preview</div></div>
              <div style={{ ...S.cardPad, display: 'grid', gap: 10 }}>
                <select value={presetId} onChange={e => setPresetId(e.target.value)} style={S.input}>
                  {(reportPresets?.items || []).map(p => <option key={p.id} value={p.id}>{p.name}</option>)}
                </select>
                <button onClick={() => refetchPreview()} style={S.btnAccentOutline()}>Previsualizar preset</button>
                <div style={{ fontSize: "var(--text-xs)", color: 'var(--text-3)' }}>Filas preview: {previewData?.count || 0}</div>
                <div style={{ fontSize: "var(--text-xs)", color: 'var(--text-3)' }}>
                  Delivery activo: {deliveryOverview?.active ?? 0} · errores: {deliveryOverview?.errored ?? 0}
                </div>
              </div>
            </div>
            <div style={S.card}>
              <div style={{ ...S.cardPad, borderBottom: '1px solid var(--surface-4)' }}><div style={S.sectionTitle}>Streaming en tiempo real</div></div>
              <div style={{ ...S.cardPad, display: 'grid', gap: 10 }}>
                <button onClick={() => setStreamLive(v => !v)}
                  style={{ ...S.btnAccentOutline(streamLive ? COLOR.success : 'var(--surface-5)'), color: streamLive ? COLOR.success : 'var(--text-2)' }}>
                  {streamLive ? '● Streaming activo' : 'Activar streaming'}
                </button>
                <div style={{ fontSize: "var(--text-xs)", color: 'var(--text-3)' }}>
                  {streamSnapshot?.timestamp ? `Snapshot: ${new Date(streamSnapshot.timestamp).toLocaleTimeString(getLocale(lang))}` : 'Sin snapshot reciente'}
                </div>
              </div>
            </div>
          </div>

          {/* Phase 3: Platform */}
          <div>
            <SectionHeading title="Plataforma BI" description="Embed SDK, catálogo de conectores y conectores personalizados" />
            <div style={{ display: 'grid', gridTemplateColumns: isMobile ? '1fr' : 'repeat(auto-fit, minmax(300px, 1fr))', gap: 14 }}>

              {/* Embed SDK */}
              <div style={S.card}>
                <div style={{ ...S.cardPad, borderBottom: '1px solid var(--surface-4)' }}><div style={S.sectionTitle}>Embed SDK</div></div>
                <div style={{ ...S.cardPad, display: 'grid', gap: 8 }}>
                  <div style={{ fontSize: "var(--text-sm)", color: 'var(--text-2)' }}>{phase3Manifest?.name || 'Contecflow BI Embed SDK'} v{phase3Manifest?.version || '1.0.0'}</div>
                  <div style={{ fontSize: "var(--text-xs)", color: 'var(--text-3)' }}>Features: {(phase3Manifest?.features || []).join(', ') || 'n/a'}</div>
                  <button onClick={handleIssueEmbedToken} style={S.btnAccentOutline()}>Emitir token embed</button>
                  {embedToken && <div style={{ fontSize: "var(--text-2xs)", color: 'var(--text-3)', wordBreak: 'break-all' }}>JWT: {embedToken.slice(0, 70)}...</div>}
                </div>
              </div>

              {/* Connector catalog */}
              <div style={S.card}>
                <div style={{ ...S.cardPad, borderBottom: '1px solid var(--surface-4)' }}><div style={S.sectionTitle}>Catálogo de conectores ({phase3CatalogEntries.filter(([, cfg]) => !!cfg?.enabled).length} activos)</div></div>
                <div style={{ ...S.cardPad, display: 'grid', gap: 6 }}>
                  {phase3CatalogEntries.slice(0, 8).map(([name, cfg]) => (
                    <div key={name} style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                      <div style={{ width: 6, height: 6, borderRadius: '50%', background: cfg.enabled ? COLOR.success : 'var(--text-4)', flexShrink: 0 }} />
                      <span style={{ flex: 1, fontSize: "var(--text-sm)", color: 'var(--text-2)' }}>{name}</span>
                      <button onClick={() => handleToggleCatalogConnector(name, !cfg.enabled)}
                        style={{ ...S.btnSecondary, padding: '3px 10px', fontSize: "var(--text-xs)" }}>{cfg.enabled ? 'Off' : 'On'}</button>
                    </div>
                  ))}
                  {phase3CatalogEntries.length === 0 && <div style={{ fontSize: "var(--text-sm)", color: 'var(--text-3)' }}>Sin conectores en catálogo</div>}
                </div>
              </div>

              {/* Custom connectors */}
              <div style={S.card}>
                <div style={{ ...S.cardPad, borderBottom: '1px solid var(--surface-4)' }}><div style={S.sectionTitle}>Conectores personalizados</div></div>
                <div style={{ ...S.cardPad, display: 'grid', gap: 8 }}>
                  <input value={customConnectorName} onChange={e => setCustomConnectorName(e.target.value)} placeholder="Nombre" style={S.input} />
                  <input value={customConnectorEndpoint} onChange={e => setCustomConnectorEndpoint(e.target.value)} placeholder="Endpoint URL" style={S.input} />
                  <button onClick={handleCreateCustomConnector} style={S.btnAccentOutline()}>Crear conector</button>
                  {phase3CustomItems.slice(0, 3).map(c => (
                    <div key={c.id} style={{ border: '1px solid var(--surface-4)', borderRadius: 8, padding: 8 }}>
                      <div style={{ fontSize: "var(--text-sm)", color: 'var(--text-1)', fontWeight: 600 }}>{c.name}</div>
                      <div style={{ fontSize: "var(--text-2xs)", color: 'var(--text-3)' }}>{c.endpoint}</div>
                      <button onClick={() => handleTestCustomConnector(c.id)} style={{ ...S.btnSecondary, padding: '3px 10px', fontSize: "var(--text-xs)", marginTop: 6 }}>Test</button>
                    </div>
                  ))}
                </div>
              </div>

              {/* Lineage & snapshots */}
              <div style={S.card}>
                <div style={{ ...S.cardPad, borderBottom: '1px solid var(--surface-4)' }}><div style={S.sectionTitle}>Lineage y versiones</div></div>
                <div style={{ ...S.cardPad, display: 'grid', gap: 8 }}>
                  <div style={{ fontSize: "var(--text-sm)", color: 'var(--text-2)' }}>
                    Edges: {phase3LineageEdges.length} · Snapshots: {phase3SnapshotItems.length}
                  </div>
                  <input value={datasetKey} onChange={e => setDatasetKey(e.target.value)} placeholder="dataset key" style={S.input} />
                  <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
                    <button onClick={handleCreateSnapshot} style={S.btnAccentOutline()}>Crear snapshot</button>
                    <button onClick={handleDiffLastSnapshots} style={S.btnSecondary}>Diff últimos 2</button>
                    <button onClick={() => refetchPhase3Lineage()} style={S.btnSecondary}>Refrescar</button>
                  </div>
                  {snapshotDiff && <div style={{ fontSize: "var(--text-xs)", color: 'var(--text-3)' }}>Cambios: {snapshotDiff?.change_count ?? 0}</div>}
                </div>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* ══════════════════════ GOVERNANCE TAB ══════════════════════ */}
      {activeTab === 'governance' && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
          <SectionHeading title="Gobernanza de datos" description="Privacidad, compliance GDPR, auditoría de accesos, linaje y clasificación de campos" />

          <BiGdprPanel />
          <BiGovernancePanel />

          {/* Governance Audit: 3-column */}
          <div>
            <SectionHeading title="Auditoría y linaje" />
            <div style={{ display: 'grid', gridTemplateColumns: isMobile ? '1fr' : 'repeat(3, 1fr)', gap: 14 }}>

              {/* Audit trail */}
              <div style={S.card}>
                <div style={{ ...S.cardPad, borderBottom: '1px solid var(--surface-4)', display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: 6 }}>
                  <span style={{ fontWeight: 700, fontSize: '0.95rem' }}>Auditoría de accesos</span>
                  <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
                    <input value={govAuditUserFilter} onChange={e => setGovAuditUserFilter(e.target.value)} placeholder="Filtrar por user_id"
                      style={{ ...S.input, width: 130, padding: '5px 10px', fontSize: "var(--text-xs)" }} />
                    <button onClick={() => setGovAuditTick(x => x + 1)} style={{ ...S.btnSecondary, padding: '5px 10px', fontSize: "var(--text-xs)" }}>Filtrar</button>
                  </div>
                </div>
                <div style={{ ...S.cardPad, display: 'grid', gap: 8 }}>
                  <button onClick={handleLogGovAuditEvent} style={S.btnAccentOutline()}>Registrar acceso</button>
                  {(govAuditData?.items || []).length === 0
                    ? <div style={{ fontSize: "var(--text-sm)", color: 'var(--text-3)' }}>Sin eventos de auditoría</div>
                    : <div style={{ maxHeight: 200, overflowY: 'auto', display: 'grid', gap: 4 }}>
                        {(govAuditData?.items || []).slice(0, 20).map((ev, i) => (
                          <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '5px 0', borderBottom: '1px solid var(--surface-4)' }}>
                            <span style={{ fontSize: "var(--text-2xs)", background: `${COLOR.info}18`, color: COLOR.info, borderRadius: 6, padding: '2px 7px', fontWeight: 700, flexShrink: 0 }}>{ev.action || 'view'}</span>
                            <div style={{ flex: 1, minWidth: 0 }}>
                              <div style={{ fontSize: "var(--text-xs)", color: 'var(--text-1)', fontWeight: 600, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{ev.resource || '—'}</div>
                              <div style={{ fontSize: "var(--text-2xs)", color: 'var(--text-3)' }}>{ev.user_id || '—'} · {ev.accessed_at ? new Date(ev.accessed_at).toLocaleString() : '—'}</div>
                            </div>
                          </div>
                        ))}
                      </div>
                  }
                </div>
              </div>

              {/* Data Lineage */}
              <div style={S.card}>
                <div style={{ ...S.cardPad, borderBottom: '1px solid var(--surface-4)', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                  <span style={{ fontWeight: 700, fontSize: '0.95rem' }}>Linaje de datos</span>
                  <button onClick={() => refetchGovLineage()} style={{ ...S.btnSecondary, padding: '5px 10px', fontSize: "var(--text-xs)" }}>Refrescar</button>
                </div>
                <div style={{ ...S.cardPad, display: 'grid', gap: 8 }}>
                  <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', alignItems: 'center' }}>
                    <input value={newLineageSource} onChange={e => setNewLineageSource(e.target.value)} placeholder="Tabla origen" style={{ ...S.input, flex: 1, minWidth: 80, padding: '6px 10px', fontSize: "var(--text-xs)" }} />
                    <span style={{ color: 'var(--text-3)' }}>→</span>
                    <input value={newLineageTarget} onChange={e => setNewLineageTarget(e.target.value)} placeholder="Tabla destino" style={{ ...S.input, flex: 1, minWidth: 80, padding: '6px 10px', fontSize: "var(--text-xs)" }} />
                    <button onClick={handleAddLineageEdge} style={{ ...S.btnAccentOutline(), padding: '6px 14px', fontSize: "var(--text-xs)" }}>Añadir</button>
                  </div>
                  {(govLineageData?.items || []).length === 0
                    ? <div style={{ fontSize: "var(--text-sm)", color: 'var(--text-3)' }}>Sin edges de linaje</div>
                    : <div style={{ maxHeight: 200, overflowY: 'auto', display: 'grid', gap: 4 }}>
                        {(govLineageData?.items || []).slice(0, 20).map((edge, i) => (
                          <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 6, padding: '5px 0', borderBottom: '1px solid var(--surface-4)' }}>
                            <span style={{ fontSize: "var(--text-xs)", color: 'var(--text-2)', fontWeight: 600, flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{edge.source_table || edge.source || '—'}</span>
                            <span style={{ color: 'var(--text-3)', fontSize: "var(--text-sm)" }}>→</span>
                            <span style={{ fontSize: "var(--text-xs)", color: 'var(--text-1)', fontWeight: 600, flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{edge.target_table || edge.target || '—'}</span>
                          </div>
                        ))}
                      </div>
                  }
                </div>
              </div>

              {/* Field sensitivity */}
              <div style={S.card}>
                <div style={{ ...S.cardPad, borderBottom: '1px solid var(--surface-4)', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                  <span style={{ fontWeight: 700, fontSize: '0.95rem' }}>Clasificación de campos</span>
                  <button onClick={() => refetchGovFields()} style={{ ...S.btnSecondary, padding: '5px 10px', fontSize: "var(--text-xs)" }}>Refrescar</button>
                </div>
                <div style={{ ...S.cardPad, display: 'grid', gap: 8 }}>
                  <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 6 }}>
                    <input value={newFieldDataset} onChange={e => setNewFieldDataset(e.target.value)} placeholder="Dataset ID" style={{ ...S.input, padding: '6px 10px', fontSize: "var(--text-xs)" }} />
                    <input value={newFieldName} onChange={e => setNewFieldName(e.target.value)} placeholder="Campo (ej. email)" style={{ ...S.input, padding: '6px 10px', fontSize: "var(--text-xs)" }} />
                    <select value={newFieldSensitivity} onChange={e => setNewFieldSensitivity(e.target.value)} style={{ ...S.input, padding: '6px 10px', fontSize: "var(--text-xs)" }}>
                      {['low', 'medium', 'high', 'critical', 'pii'].map(s => <option key={s} value={s}>{s}</option>)}
                    </select>
                    <button onClick={handleUpsertFieldSensitivity} style={{ ...S.btnAccentOutline(COLOR.warning), padding: '6px 14px', fontSize: "var(--text-xs)" }}>Clasificar</button>
                  </div>
                  {(govFieldData?.items || []).length === 0
                    ? <div style={{ fontSize: "var(--text-sm)", color: 'var(--text-3)' }}>Sin campos clasificados</div>
                    : <div style={{ maxHeight: 200, overflowY: 'auto', display: 'grid', gap: 4 }}>
                        {(govFieldData?.items || []).slice(0, 20).map((f, i) => {
                          const sc = f.sensitivity === 'critical' || f.sensitivity === 'pii' ? COLOR.danger : f.sensitivity === 'high' ? COLOR.warning : COLOR.success
                          return (
                            <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '5px 0', borderBottom: '1px solid var(--surface-4)' }}>
                              <span style={{ fontSize: "var(--text-2xs)", background: `${sc}18`, color: sc, borderRadius: 6, padding: '2px 7px', fontWeight: 700, flexShrink: 0, textTransform: 'uppercase' }}>{f.sensitivity || '—'}</span>
                              <div style={{ flex: 1, minWidth: 0 }}>
                                <div style={{ fontSize: "var(--text-xs)", color: 'var(--text-1)', fontWeight: 600, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{f.field_name || '—'}</div>
                                <div style={{ fontSize: "var(--text-2xs)", color: 'var(--text-3)' }}>{f.dataset_id || '—'}</div>
                              </div>
                            </div>
                          )
                        })}
                      </div>
                  }
                </div>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* ══════════════════════ COLLABORATION TAB ══════════════════════ */}
      {activeTab === 'collaboration' && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
          <SectionHeading title="Colaboración y vistas compartidas" description="Comenta en widgets, guarda vistas, comparte dashboards y gestiona bookmarks" />

          <BiDashboardCollabPanel />

          <div style={{ display: 'grid', gridTemplateColumns: isMobile ? '1fr' : '1fr 1fr', gap: 14 }}>

            {/* Shared views */}
            <div style={S.card}>
              <div style={{ ...S.cardPad, borderBottom: '1px solid var(--surface-4)' }}>
                <span style={{ fontWeight: 700, fontSize: '0.95rem' }}>Vistas compartidas</span>
              </div>
              <div style={{ ...S.cardPad, display: 'grid', gap: 10 }}>
                <div style={{ display: 'flex', gap: 8 }}>
                  <input value={sharedViewName} onChange={e => setSharedViewName(e.target.value)} placeholder="Nombre de la vista..."
                    style={{ ...S.input, flex: 1 }} />
                  <button onClick={handleCreateSharedView} style={S.btnAccentOutline(COLOR.success)}>Guardar vista</button>
                </div>
                <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center' }}>
                  <input value={sharedViewsSearch} onChange={e => setSharedViewsSearch(e.target.value)} placeholder="Buscar vista..."
                    style={{ ...S.input, flex: 1, minWidth: 160 }} />
                  <select value={sharedViewsSort} onChange={e => setSharedViewsSort(e.target.value)} style={{ ...S.input, width: 'auto' }}>
                    <option value="date_desc">Más recientes</option>
                    <option value="date_asc">Más antiguas</option>
                    <option value="author_asc">Autor (A-Z)</option>
                    <option value="name_asc">Nombre (A-Z)</option>
                  </select>
                </div>
                <label style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: "var(--text-xs)", color: 'var(--text-2)', cursor: 'pointer' }}>
                  <input type="checkbox" checked={showInactiveSharedViews} onChange={e => setShowInactiveSharedViews(e.target.checked)} />
                  Mostrar inactivas ({activeSharedViews} activas{showInactiveSharedViews ? ` · ${inactiveSharedViews} inactivas` : ''})
                </label>
                <div style={{ display: 'grid', gap: 6, maxHeight: 260, overflowY: 'auto' }}>
                  {sortedSharedViews.length === 0
                    ? <div style={{ fontSize: "var(--text-sm)", color: 'var(--text-3)' }}>
                        {sharedViews.length === 0 ? 'Sin vistas compartidas. Guarda una para empezar.' : 'Sin coincidencias.'}
                      </div>
                    : sortedSharedViews.map(v => (
                        <div key={v.id} style={{ border: '1px solid var(--surface-4)', borderRadius: 8, padding: '8px 12px', display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
                          <div>
                            <div style={{ fontSize: "var(--text-sm)", fontWeight: 600, color: 'var(--text-1)' }}>{v.name}</div>
                            <div style={{ fontSize: "var(--text-2xs)", color: 'var(--text-3)' }}>{v.dashboard_key} · {v.created_by_name || '—'} · {v.active === false ? 'inactiva' : 'activa'}</div>
                          </div>
                          <div style={{ display: 'flex', gap: 6 }}>
                            <button onClick={() => handleApplySharedView(v)} style={{ ...S.btnSecondary, padding: '4px 8px', fontSize: "var(--text-xs)" }}>Aplicar</button>
                            <button onClick={() => handleToggleSharedView(v)}
                              style={{ ...S.btnAccentOutline(v.active ? COLOR.warning : COLOR.success), padding: '4px 8px', fontSize: "var(--text-xs)" }}>
                              {v.active ? 'Desactivar' : 'Activar'}
                            </button>
                          </div>
                        </div>
                      ))
                  }
                </div>
              </div>
            </div>

            {/* Widget comments */}
            <div style={S.card}>
              <div style={{ ...S.cardPad, borderBottom: '1px solid var(--surface-4)' }}>
                <span style={{ fontWeight: 700, fontSize: '0.95rem' }}>Comentarios de widgets</span>
              </div>
              <div style={{ ...S.cardPad, display: 'flex', flexDirection: 'column', gap: 10 }}>
                <select value={commentWidget} onChange={e => setCommentWidget(e.target.value)} style={S.input}>
                  <option value="kpi_grid">KPI grid</option>
                  <option value="health_chart">Estado de salud</option>
                  <option value="profit_table">Rentabilidad por proyecto</option>
                  <option value="ai_narrative">Narrativa IA</option>
                </select>
                <textarea value={commentText} onChange={e => setCommentText(e.target.value)} rows={3}
                  placeholder="Añade un comentario para este widget..."
                  style={{ ...S.input, resize: 'vertical' }} />
                <button onClick={handleCreateComment} style={S.btnAccentOutline()}>Guardar comentario</button>
                <div style={{ borderTop: '1px solid var(--surface-4)', paddingTop: 10, display: 'grid', gap: 8, maxHeight: 200, overflowY: 'auto' }}>
                  {comments.length === 0
                    ? <div style={{ color: 'var(--text-3)', fontSize: "var(--text-sm)" }}>Sin comentarios para este widget</div>
                    : comments.map(c => (
                        <div key={c.id} style={{ padding: '8px 10px', background: 'var(--surface-3)', borderRadius: 8, display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 8 }}>
                          <div style={{ flex: 1 }}>
                            <div style={{ fontSize: "var(--text-sm)", color: 'var(--text-1)' }}>{c.message}</div>
                            <div style={{ fontSize: "var(--text-2xs)", color: 'var(--text-3)', marginTop: 2 }}>{c.created_by_name || '—'} · {c.created_at ? new Date(c.created_at).toLocaleString(getLocale(lang)) : ''}</div>
                          </div>
                          {!c.resolved && (
                            <button onClick={() => handleResolveComment(c.id)}
                              style={{ fontSize: "var(--text-2xs)", color: COLOR.success, background: 'none', border: 'none', cursor: 'pointer', flexShrink: 0, fontFamily: 'inherit' }}>✓ Resolver</button>
                          )}
                        </div>
                      ))
                  }
                </div>
              </div>
            </div>
          </div>

          {/* Bookmarks */}
          <div style={S.card}>
            <div style={{ ...S.cardPad, borderBottom: '1px solid var(--surface-4)', display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: 8 }}>
              <span style={{ fontWeight: 700, fontSize: '0.95rem' }}>Bookmarks de dashboard</span>
              <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
                <input value={newBookmarkName} onChange={e => setNewBookmarkName(e.target.value)} placeholder="Nombre del bookmark"
                  style={{ ...S.input, width: 200 }} />
                <button onClick={async () => { if (!newBookmarkName.trim()) return; try { await biBookmarksApi.create({ name: newBookmarkName, period_days: days, active_tab: 'executive', shared: false }); setNewBookmarkName(''); setBookmarksTick(x => x + 1) } catch (_e) { /* ignore */ } }}
                  style={S.btnPrimary}>Guardar vista actual</button>
              </div>
            </div>
            <div style={S.cardPad}>
              {!(bookmarks?.items || []).length
                ? <div style={{ textAlign: 'center', color: 'var(--text-3)', fontSize: "var(--text-sm)", padding: '16px 0' }}>Sin bookmarks guardados</div>
                : <div style={{ display: 'grid', gridTemplateColumns: isMobile ? '1fr' : 'repeat(auto-fill, minmax(240px, 1fr))', gap: 10 }}>
                    {(bookmarks?.items || []).map(bm => (
                      <div key={bm.id} style={{ ...S.card, padding: '12px 16px', display: 'flex', flexDirection: 'column', gap: 6 }}>
                        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                          <span style={{ fontSize: "var(--text-base)", fontWeight: 700, color: 'var(--text-1)' }}>🔖 {bm.name}</span>
                          <button onClick={async () => { try { await biBookmarksApi.delete(bm.id); setBookmarksTick(x => x + 1) } catch (_e) { /* ignore */ } }}
                            style={{ background: 'none', border: 'none', color: 'var(--text-3)', cursor: 'pointer', fontSize: "var(--text-sm)", fontFamily: 'inherit' }}>✕</button>
                        </div>
                        <div style={{ fontSize: "var(--text-xs)", color: 'var(--text-3)' }}>Período: {bm.period_days}d · Tab: {bm.active_tab || 'executive'}</div>
                        {bm.description && <div style={{ fontSize: "var(--text-xs)", color: 'var(--text-2)' }}>{bm.description}</div>}
                        <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
                          <button onClick={() => setDays(bm.period_days || 30)} style={{ ...S.btnAccentOutline(), flex: 1, padding: '5px 0', fontSize: "var(--text-xs)" }}>Cargar vista</button>
                          {bm.shared && <span style={{ fontSize: "var(--text-2xs)", padding: '3px 8px', borderRadius: 10, background: `${COLOR.success}18`, color: COLOR.success, fontWeight: 700 }}>Compartido</span>}
                        </div>
                      </div>
                    ))}
                  </div>
              }
            </div>
          </div>

          {/* Governance overview (read-only) */}
          {governance && (
            <div style={S.card}>
              <div style={{ ...S.cardPad, borderBottom: '1px solid var(--surface-4)', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                <span style={{ fontWeight: 700, fontSize: '0.95rem' }}>Resumen de gobernanza</span>
                <button onClick={handleRunGovernance} style={S.btnAccentOutline()}>Ejecutar checks</button>
              </div>
              <div style={{ ...S.cardPad, display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(180px, 1fr))', gap: 12 }}>
                {[
                  { label: 'Reports programados activos', value: govScheduledActive },
                  { label: 'Anomalías detectadas',         value: governance?.anomalies_detected ?? 0 },
                  { label: 'Checks ejecutados',            value: governance?.checks_run ?? 0 },
                ].map(k => (
                  <div key={k.label} style={{ padding: '12px 16px', background: 'var(--surface-3)', borderRadius: 10 }}>
                    <div style={{ fontSize: "var(--text-xl)", fontWeight: 800, color: 'var(--text-1)', marginBottom: 4 }}>{k.value ?? '—'}</div>
                    <div style={{ fontSize: "var(--text-xs)", color: 'var(--text-3)' }}>{k.label}</div>
                  </div>
                ))}
              </div>
              {governanceRun && (
                <div style={{ ...S.cardPad, borderTop: '1px solid var(--surface-4)', fontSize: "var(--text-sm)", color: 'var(--text-2)' }}>
                  Último run: {JSON.stringify(governanceRun).slice(0, 200)}
                </div>
              )}
            </div>
          )}
        </div>
      )}

    </PageShell>
  )
}
