import { useEffect, useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import api, { biCollaborationApi, biIntelligenceApi, biPlatformApi, biSmartAlertsApi, biBookmarksApi, biReportBuilderV2Api, biGovernanceAuditApi } from '../services/api'
import PageHeader from '../components/layout/PageHeader'
import { Spinner } from '../components/ui'
import { PieChart as PieChartIcon } from 'lucide-react'
import { ResponsiveContainer, Sankey, Tooltip as SankeyTooltip } from 'recharts'
import { useAppT, useAppLang } from '../i18n/AppLangContext'
import { COLOR } from '../constants/theme'
import NarrativeCard from '../components/bi/NarrativeCard'
import AskDataWidget from '../components/bi/AskDataWidget'
import VisualQueryBuilderWidget from '../components/bi/VisualQueryBuilderWidget'
import BiAdvancedViz from '../components/bi/BiAdvancedViz'

/* ── Helpers ──────────────────────────────────────────────────────────────── */
function dateRange(days) {
  const d_to = new Date().toISOString().slice(0, 10)
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

function fmtPct(v) { return v != null ? `${Number(v).toFixed(1)}%` : '—' }

function toFiniteNumber(value, fallback = 0) {
  if (typeof value === 'number') {
    return Number.isFinite(value) ? value : fallback
  }
  if (typeof value === 'string') {
    const normalized = value
      .trim()
      .replace(/\s/g, '')
      .replace(/\.(?=\d{3}(?:\D|$))/g, '')
      .replace(',', '.')
    const parsed = Number(normalized)
    return Number.isFinite(parsed) ? parsed : fallback
  }
  return fallback
}

function useIsMobile(maxWidth = 900) {
  const [isMobile, setIsMobile] = useState(() => {
    if (typeof window === 'undefined') return false
    return window.matchMedia(`(max-width: ${maxWidth}px)`).matches
  })

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

/* ── Design tokens ────────────────────────────────────────────────────────── */
const S = {
  card: {
    background: 'var(--surface-2)',
    border: '1px solid var(--surface-4)',
    borderRadius: 14,
    overflow: 'hidden',
  },
  cardPad: { padding: '20px 24px' },
  sectionTitle: {
    fontSize: 11,
    fontWeight: 700,
    color: 'var(--text-3)',
    textTransform: 'uppercase',
    letterSpacing: '0.09em',
    marginBottom: 16,
    margin: 0,
  },
}

/* ── Sub-components (identical visual language to MetricsDashboardTab) ─────── */
function PeriodButton({ active, label, onClick }) {
  return (
    <button onClick={onClick} style={{
      padding: '7px 18px', borderRadius: 8,
      border: `1px solid ${active ? COLOR.accent : 'var(--surface-4)'}`,
      background: active ? COLOR.accentMuted : 'transparent',
      color: active ? COLOR.accent : 'var(--text-2)',
      fontSize: 12, fontWeight: 600, cursor: 'pointer', fontFamily: 'inherit',
      transition: 'all 0.15s',
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
          {icon && (
            <span style={{
              fontSize: 18, background: `${bar}18`, borderRadius: 8,
              padding: '5px 7px', lineHeight: 1,
            }}>{icon}</span>
          )}
          <span style={{
            fontSize: 10, fontWeight: 700, color: 'var(--text-3)',
            textTransform: 'uppercase', letterSpacing: '0.09em',
          }}>{label}</span>
        </div>
        <div style={{
          fontSize: 34, fontWeight: 700, color: color || 'var(--text-1)',
          lineHeight: 1.1, letterSpacing: '-0.5px',
        }}>{value ?? '—'}</div>
        {sub && <div style={{ fontSize: 11, color: 'var(--text-3)', lineHeight: 1.4 }}>{sub}</div>}
      </div>
    </div>
  )
}

function RingGauge({ value, color, size = 64 }) {
  const r = (size - 8) / 2
  const circ = 2 * Math.PI * r
  const progress = Math.min(Math.max(value ?? 0, 0), 100) / 100
  return (
    <svg width={size} height={size} style={{ transform: 'rotate(-90deg)', flexShrink: 0 }}>
      <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="var(--surface-4)" strokeWidth={7} />
      <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke={color} strokeWidth={7}
        strokeDasharray={circ} strokeDashoffset={circ * (1 - progress)} strokeLinecap="round" />
    </svg>
  )
}

function GaugeCard({ label, value, color, suffix = '%', sub }) {
  return (
    <div style={{ ...S.card, ...S.cardPad, display: 'flex', alignItems: 'center', gap: 16 }}>
      <div style={{ position: 'relative', flexShrink: 0 }}>
        <RingGauge value={typeof value === 'number' ? value : 0} color={color} size={68} />
        <div style={{
          position: 'absolute', inset: 0,
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          fontSize: 12, fontWeight: 700, color,
        }}>
          {value != null ? `${value}` : '—'}
        </div>
      </div>
      <div>
        <div style={{
          fontSize: 10, fontWeight: 700, color: 'var(--text-3)',
          textTransform: 'uppercase', letterSpacing: '0.09em', marginBottom: 4,
        }}>{label}</div>
        <div style={{ fontSize: 26, fontWeight: 700, color, lineHeight: 1, letterSpacing: '-0.5px' }}>
          {value != null ? `${value}${suffix}` : '—'}
        </div>
        {sub && <div style={{ fontSize: 11, color: 'var(--text-3)', marginTop: 4 }}>{sub}</div>}
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
        <span style={{ fontSize: 12, color: 'var(--text-2)', textTransform: 'capitalize' }}>
          {label.replace(/_/g, ' ')}
        </span>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <span style={{
            fontSize: 11, fontWeight: 700, color: 'var(--text-1)',
            background: 'var(--surface-4)', borderRadius: 6, padding: '2px 7px',
          }}>{displayVal}</span>
          <span style={{ fontSize: 11, color: 'var(--text-3)', minWidth: 32, textAlign: 'right' }}>{pct}%</span>
        </div>
      </div>
      <div style={{ height: 7, background: 'var(--surface-4)', borderRadius: 4, overflow: 'hidden' }}>
        <div style={{
          width: `${pct}%`, height: '100%', background: color, borderRadius: 4,
          transition: 'width 0.6s cubic-bezier(0.4,0,0.2,1)',
        }} />
      </div>
    </div>
  )
}

function ProjectAvatar({ name, code }) {
  const initials = (code || name || '?').slice(0, 2).toUpperCase()
  const colors = [COLOR.accent, COLOR.success, COLOR.warning, COLOR.purple, '#2dd4bf', '#fb923c']
  const idx = (name || '').charCodeAt(0) % colors.length
  return (
    <div style={{
      width: 32, height: 32, borderRadius: 8,
      background: `${colors[idx]}22`, border: `1.5px solid ${colors[idx]}44`,
      display: 'flex', alignItems: 'center', justifyContent: 'center',
      fontSize: 11, fontWeight: 700, color: colors[idx], flexShrink: 0,
    }}>{initials}</div>
  )
}

function MarginBar({ margin, revenue }) {
  const pct = revenue > 0 ? Math.round((margin / revenue) * 100) : 0
  const color = pct >= 30 ? COLOR.success : pct >= 15 ? COLOR.warning : COLOR.danger
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 8, minWidth: 120 }}>
      <div style={{ flex: 1, height: 5, background: 'var(--surface-4)', borderRadius: 3 }}>
        <div style={{ width: `${Math.max(0, Math.min(pct, 100))}%`, height: '100%', background: color, borderRadius: 3, transition: 'width 0.5s ease' }} />
      </div>
      <span style={{ fontSize: 11, fontWeight: 700, color, minWidth: 36 }}>{pct}%</span>
    </div>
  )
}

function RevenueFlowSankey({ data }) {
  const nodes = Array.isArray(data?.nodes) ? data.nodes : []
  const links = Array.isArray(data?.links)
    ? data.links
      .map((link) => ({
        ...link,
        source: toFiniteNumber(link?.source, -1),
        target: toFiniteNumber(link?.target, -1),
        value: toFiniteNumber(link?.value, 0),
      }))
      .filter((link) => (
        Number.isInteger(link.source)
        && Number.isInteger(link.target)
        && link.source >= 0
        && link.target >= 0
        && link.source < nodes.length
        && link.target < nodes.length
        && link.value > 0
      ))
    : []

  if (!nodes.length || !links.length) {
    return <div style={{ textAlign: 'center', color: 'var(--text-3)', fontSize: 12, padding: '16px 0' }}>Sin datos</div>
  }

  const safeData = { nodes, links }

  return (
    <div style={{ width: '100%', height: 240 }}>
      <ResponsiveContainer width="100%" height="100%">
        <Sankey
          data={safeData}
          nodePadding={30}
          margin={{ top: 10, right: 18, bottom: 10, left: 18 }}
          linkCurvature={0.5}
        >
          <SankeyTooltip />
        </Sankey>
      </ResponsiveContainer>
    </div>
  )
}

function EmptyDash() {
  return (
    <div style={{ textAlign: 'center', padding: '80px 24px', color: 'var(--text-3)' }}>
      <div style={{ fontSize: 48, marginBottom: 16, opacity: 0.4 }}>📊</div>
      <div style={{ fontSize: 15, fontWeight: 600, marginBottom: 8, color: 'var(--text-2)' }}>Sin datos ejecutivos</div>
      <div style={{ fontSize: 13, maxWidth: 280, margin: '0 auto', lineHeight: 1.6 }}>
        Crea proyectos y registra actividad para ver el dashboard ejecutivo aquí
      </div>
    </div>
  )
}

/* ── Main component ───────────────────────────────────────────────────────── */
export default function BIPage() {
  const t = useAppT()
  const { lang } = useAppLang()
  const isMobile = useIsMobile(900)
  const [days, setDays] = useState(30)
  const [commentWidget, setCommentWidget] = useState('kpi_grid')
  const [commentText, setCommentText] = useState('')
  const [sharedViewName, setSharedViewName] = useState('')
  const [sharedViewsSearch, setSharedViewsSearch] = useState('')
  const [sharedViewsSort, setSharedViewsSort] = useState('date_desc')
  const [showInactiveSharedViews, setShowInactiveSharedViews] = useState(false)
  const [rulesDraft, setRulesDraft] = useState(null)
  const [govRunTick, setGovRunTick] = useState(0)
  const [sharedViewsTick, setSharedViewsTick] = useState(0)
  const [phase2Tick, setPhase2Tick] = useState(0)
  const [presetId, setPresetId] = useState('ops_delivery_mix')
  const [streamLive, setStreamLive] = useState(false)
  const [streamSnapshot, setStreamSnapshot] = useState(null)
  const [phase3Tick, setPhase3Tick] = useState(0)
  const [embedToken, setEmbedToken] = useState('')
  const [customConnectorName, setCustomConnectorName] = useState('')
  const [customConnectorEndpoint, setCustomConnectorEndpoint] = useState('')
  const [datasetKey, setDatasetKey] = useState('olap.fact_projects')
  const [snapshotDiff, setSnapshotDiff] = useState(null)

  // ── Phase 4 state (alerts, bookmarks, report builder v2)
  const [alertsTick, setAlertsTick] = useState(0)
  const [bookmarksTick, setBookmarksTick] = useState(0)
  const [rbv2Tick, setRbv2Tick] = useState(0)
  const [newAlertName, setNewAlertName] = useState('')
  const [newAlertMetric, setNewAlertMetric] = useState('revenue')
  const [newAlertCondition, setNewAlertCondition] = useState('trend_down')
  const [newAlertSeverity, setNewAlertSeverity] = useState('warning')
  const [newBookmarkName, setNewBookmarkName] = useState('')
  const [rbv2SelectedPreset, setRbv2SelectedPreset] = useState('finance_revenue_by_client')
  const [rbv2PreviewData, setRbv2PreviewData] = useState(null)
  // ── BI Governance Audit state
  const [govAuditTick, setGovAuditTick] = useState(0)
  const [govAuditUserFilter, setGovAuditUserFilter] = useState('')
  const [newLineageSource, setNewLineageSource] = useState('')
  const [newLineageTarget, setNewLineageTarget] = useState('')
  const [newFieldName, setNewFieldName] = useState('')
  const [newFieldSensitivity, setNewFieldSensitivity] = useState('low')
  const [newFieldDataset, setNewFieldDataset] = useState('')

  const params = dateRange(days)

  const { data: kpis, isLoading: loadingKpis } = useQuery({
    queryKey: ['bi-exec-kpis', days],
    queryFn: () => api.get('/dashboard/kpis', { params }).then(r => r.data).catch(() => ({})),
    staleTime: 60_000,
  })

  const { data: health = [], isLoading: loadingHealth } = useQuery({
    queryKey: ['bi-exec-health', days],
    queryFn: () => api.get('/dashboard/projects-health', { params }).then(r => r.data).catch(() => []),
    staleTime: 60_000,
  })

  const { data: profitSummary } = useQuery({
    queryKey: ['bi-exec-profit', days],
    queryFn: () => api.get('/profitability/summary', { params: { ...params, period: 'custom' } }).then(r => r.data).catch(() => null),
    staleTime: 60_000,
  })

  const { data: topProjects = [] } = useQuery({
    queryKey: ['bi-exec-top-projects', days],
    queryFn: () => api.get('/profitability/projects', { params }).then(r => r.data).catch(() => []),
    staleTime: 60_000,
  })

  const { data: byType = [] } = useQuery({
    queryKey: ['bi-exec-by-type', days],
    queryFn: () => api.get('/analytics/query/projects_by_type', { params }).then(r => r.data?.rows || []).catch(() => []),
    staleTime: 60_000,
  })

  const { data: utilData } = useQuery({
    queryKey: ['bi-exec-utilization', days],
    queryFn: () => api.get('/analytics/utilization/advanced', { params }).then(r => r.data).catch(() => null),
    staleTime: 60_000,
  })

  const { data: funnel = [] } = useQuery({
    queryKey: ['bi-exec-funnel', days],
    queryFn: () => api.get('/analytics/olap/pipeline-funnel').then(r => r.data).catch(() => []),
    staleTime: 60_000,
  })

  const { data: commentsData, refetch: refetchComments } = useQuery({
    queryKey: ['bi-phase1-comments', commentWidget],
    queryFn: () => biCollaborationApi.listComments({ dashboard_key: 'executive', widget_id: commentWidget }).then(r => r.data).catch(() => ({ items: [] })),
    staleTime: 15_000,
  })

  const { data: sharedViewsData, refetch: refetchSharedViews } = useQuery({
    queryKey: ['bi-phase3-shared-views', sharedViewsTick, showInactiveSharedViews],
    queryFn: () => biCollaborationApi.listSharedViews({ include_inactive: showInactiveSharedViews }).then(r => r.data).catch(() => ({ items: [] })),
    staleTime: 15_000,
  })

  const { data: governance } = useQuery({
    queryKey: ['bi-phase1-governance-overview'],
    queryFn: () => biCollaborationApi.governanceOverview().then(r => r.data).catch(() => null),
    staleTime: 30_000,
  })

  const { data: governanceRules, refetch: refetchRules } = useQuery({
    queryKey: ['bi-phase1-governance-rules'],
    queryFn: () => biCollaborationApi.governanceRules().then(r => r.data).catch(() => null),
    staleTime: 30_000,
  })

  const { data: governanceRun, refetch: refetchGovRun } = useQuery({
    queryKey: ['bi-phase1-governance-run', govRunTick],
    queryFn: () => biCollaborationApi.lastGovernanceRun().then(r => r.data?.result || null).catch(() => null),
    staleTime: 10_000,
  })

  const { data: forecastRevenue } = useQuery({
    queryKey: ['bi-phase2-forecast', phase2Tick],
    queryFn: () => biIntelligenceApi.revenueForecast({ months_ahead: 6 }).then(r => r.data).catch(() => null),
    staleTime: 30_000,
  })

  const { data: revenueAnomalies } = useQuery({
    queryKey: ['bi-phase2-anomalies', phase2Tick],
    queryFn: () => biIntelligenceApi.revenueAnomalies({ z_threshold: 2.0 }).then(r => r.data).catch(() => ({ items: [] })),
    staleTime: 30_000,
  })

  const { data: connectorsData, refetch: refetchConnectors } = useQuery({
    queryKey: ['bi-phase2-connectors', phase2Tick],
    queryFn: () => biIntelligenceApi.listConnectors().then(r => r.data).catch(() => ({ items: {} })),
    staleTime: 15_000,
  })

  const { data: reportPresets } = useQuery({
    queryKey: ['bi-phase2-report-presets'],
    queryFn: () => biIntelligenceApi.reportPresets().then(r => r.data).catch(() => ({ items: [] })),
    staleTime: 60_000,
  })

  const { data: previewData, refetch: refetchPreview } = useQuery({
    queryKey: ['bi-phase2-preview', presetId, phase2Tick],
    queryFn: () => biIntelligenceApi.previewPreset({ preset_id: presetId, limit: 20 }).then(r => r.data).catch(() => null),
    staleTime: 20_000,
  })

  const { data: deliveryOverview } = useQuery({
    queryKey: ['bi-phase2-delivery', phase2Tick],
    queryFn: () => biIntelligenceApi.deliveryOverview().then(r => r.data).catch(() => null),
    staleTime: 20_000,
  })

  const { data: phase3Manifest } = useQuery({
    queryKey: ['bi-phase3-manifest'],
    queryFn: () => biPlatformApi.sdkManifest().then(r => r.data).catch(() => null),
    staleTime: 60_000,
  })

  const { data: phase3Catalog, refetch: refetchPhase3Catalog } = useQuery({
    queryKey: ['bi-phase3-catalog', phase3Tick],
    queryFn: () => biPlatformApi.connectorCatalog().then(r => r.data).catch(() => ({ count: 0, items: {} })),
    staleTime: 20_000,
  })

  const { data: phase3Custom, refetch: refetchPhase3Custom } = useQuery({
    queryKey: ['bi-phase3-custom', phase3Tick],
    queryFn: () => biPlatformApi.listCustomConnectors().then(r => r.data).catch(() => ({ items: [] })),
    staleTime: 20_000,
  })

  const { data: phase3Lineage, refetch: refetchPhase3Lineage } = useQuery({
    queryKey: ['bi-phase3-lineage', phase3Tick],
    queryFn: () => biPlatformApi.lineage().then(r => r.data).catch(() => ({ edges: [], audit: [] })),
    staleTime: 20_000,
  })

  const { data: phase3Snapshots, refetch: refetchPhase3Snapshots } = useQuery({
    queryKey: ['bi-phase3-snapshots', datasetKey, phase3Tick],
    queryFn: () => biPlatformApi.listSnapshots(datasetKey).then(r => r.data).catch(() => ({ items: [] })),
    staleTime: 20_000,
  })

  // ── Smart Alerts queries
  const { data: alertRules } = useQuery({
    queryKey: ['bi-alert-rules', alertsTick],
    queryFn: () => biSmartAlertsApi.listRules().then(r => r.data).catch(() => ({ items: [] })),
    staleTime: 30_000,
  })
  const { data: alertHistory } = useQuery({
    queryKey: ['bi-alert-history', alertsTick],
    queryFn: () => biSmartAlertsApi.getHistory(50).then(r => r.data).catch(() => ({ items: [] })),
    staleTime: 30_000,
  })
  const { data: alertSupportedMetrics } = useQuery({
    queryKey: ['bi-alert-supported-metrics'],
    queryFn: () => biSmartAlertsApi.supportedMetrics().then(r => r.data).catch(() => ({ metrics: [], conditions: [] })),
    staleTime: 600_000,
  })

  // ── Bookmarks queries
  const { data: bookmarks } = useQuery({
    queryKey: ['bi-bookmarks', bookmarksTick],
    queryFn: () => biBookmarksApi.list().then(r => r.data).catch(() => ({ items: [] })),
    staleTime: 30_000,
  })

  // ── Report Builder v2 queries
  const { data: rbv2Presets } = useQuery({
    queryKey: ['bi-rbv2-presets', rbv2Tick],
    queryFn: () => biReportBuilderV2Api.listPresets({ grouped: false }).then(r => r.data).catch(() => ({ items: [] })),
    staleTime: 60_000,
  })

  useEffect(() => {
    if (governanceRules) setRulesDraft(governanceRules)
  }, [governanceRules])

  // ── BI Governance Audit / Lineage / Field-sensitivity queries
  const { data: govAuditData, refetch: refetchGovAudit } = useQuery({
    queryKey: ['bi-gov-audit', govAuditTick, govAuditUserFilter],
    queryFn: () => biGovernanceAuditApi.getAccessHistory(
      govAuditUserFilter.trim() ? { user_id: govAuditUserFilter.trim(), limit: 50 } : { limit: 50 }
    ).then(r => r.data).catch(() => ({ items: [] })),
    staleTime: 15_000,
  })

  const { data: govLineageData, refetch: refetchGovLineage } = useQuery({
    queryKey: ['bi-gov-lineage', govAuditTick],
    queryFn: () => biGovernanceAuditApi.listLineage().then(r => r.data).catch(() => ({ items: [] })),
    staleTime: 15_000,
  })

  const { data: govFieldData, refetch: refetchGovFields } = useQuery({
    queryKey: ['bi-gov-fields', govAuditTick],
    queryFn: () => biGovernanceAuditApi.listFieldSensitivity().then(r => r.data).catch(() => ({ items: [] })),
    staleTime: 15_000,
  })

  useEffect(() => {
    let ws = null
    let closed = false

    async function connect() {
      if (!streamLive) return
      try {
        const tokenRes = await biIntelligenceApi.realtimeToken()
        const token = tokenRes?.data?.token
        if (!token) return
        const proto = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
        const wsBase = `${proto}//${window.location.host}`
        ws = new WebSocket(`${wsBase}/api/v1/bi/intelligence/realtime/stream?token=${encodeURIComponent(token)}`)
        ws.onmessage = (ev) => {
          try {
            const data = JSON.parse(ev.data)
            if (data?.type === 'bi_intelligence_snapshot') setStreamSnapshot(data)
          } catch (_e) {
            // Ignore malformed frames from network intermediaries.
          }
        }
        ws.onclose = () => {
          if (!closed && streamLive) {
            setTimeout(connect, 2000)
          }
        }
      } catch (_e) {
        // Keep UI responsive even if realtime token/stream fails.
      }
    }

    connect()

    return () => {
      closed = true
      if (ws) ws.close()
    }
  }, [streamLive])

  const isLoading = loadingKpis || loadingHealth

  if (isLoading) {
    return (
      <div style={{ padding: 32 }}>
        <PageHeader icon={<PieChartIcon size={18} />} title={t('bi.title')} subtitle={t('bi.subtitle')} />
        <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', minHeight: 300 }}>
          <Spinner />
        </div>
      </div>
    )
  }

  /* ── Derived stats ── */
  const totalProjects = health.length
  const critProj = health.filter(p => p.schedule_deviation_days > 0 || p.budget_used_pct > 100).length
  const warnProj = health.filter(p => p.budget_used_pct > 80 || p.alerts_count > 0).length
  const okProj   = totalProjects - critProj - warnProj
  const onTimePct = totalProjects > 0 ? Math.round((okProj / totalProjects) * 100) : 0

  const revenue    = toFiniteNumber(profitSummary?.total_revenue, 0)
  const costs      = toFiniteNumber(profitSummary?.total_cost, 0)
  const margin     = revenue - costs
  const marginPct  = revenue > 0 ? Math.round((margin / revenue) * 100) : 0
  const marginColor = marginPct >= 30 ? COLOR.success : marginPct >= 15 ? COLOR.warning : COLOR.danger

  const onTimeColor = onTimePct >= 80 ? COLOR.success : onTimePct >= 60 ? COLOR.warning : COLOR.danger

  const totalByType = byType.reduce((s, r) => s + (r.value || 0), 0)
  const typePalette = [COLOR.accent, COLOR.success, COLOR.warning, COLOR.purple, '#2dd4bf', '#fb923c']

  const healthRows = [
    { label: 'En tiempo y presupuesto', count: okProj,   color: COLOR.success },
    { label: 'En riesgo',              count: warnProj,  color: COLOR.warning },
    { label: 'Crítico',                count: critProj,  color: COLOR.danger  },
  ]

  const utilPctRaw = utilData?.avg_utilization_pct
  const utilPct = utilPctRaw == null ? null : toFiniteNumber(utilPctRaw, null)
  const normalizedUtilPct = utilPct == null ? null : Math.max(0, Math.min(100, utilPct))
  const comments = commentsData?.items || []
  const sharedViews = sharedViewsData?.items || []
  const sharedViewsQuery = sharedViewsSearch.trim().toLowerCase()
  const filteredSharedViews = sharedViews.filter((v) => {
    if (!sharedViewsQuery) return true
    const name = String(v?.name || '').toLowerCase()
    return name.includes(sharedViewsQuery)
  })
  const sortedSharedViews = [...filteredSharedViews].sort((a, b) => {
    if (sharedViewsSort === 'name_asc') {
      return String(a?.name || '').localeCompare(String(b?.name || ''), 'es', { sensitivity: 'base' })
    }
    if (sharedViewsSort === 'author_asc') {
      return String(a?.created_by_name || '').localeCompare(String(b?.created_by_name || ''), 'es', { sensitivity: 'base' })
    }
    const tA = Date.parse(a?.created_at || '') || 0
    const tB = Date.parse(b?.created_at || '') || 0
    if (sharedViewsSort === 'date_asc') return tA - tB
    return tB - tA
  })
  const activeSharedViews = sharedViews.filter((v) => v.active !== false).length
  const inactiveSharedViews = sharedViews.length - activeSharedViews
  const connectors = Object.entries(connectorsData?.items || {})
  const forecastHead = forecastRevenue?.forecast || []
  const anomalies = revenueAnomalies?.items || []
  const phase3CatalogEntries = Object.entries(phase3Catalog?.items || {})
  const phase3CatalogActive = phase3CatalogEntries.filter(([, cfg]) => !!cfg?.enabled).length
  const phase3CustomItems = phase3Custom?.items || []
  const phase3LineageEdges = phase3Lineage?.edges || []
  const phase3AuditEntries = phase3Lineage?.audit || []
  const phase3SnapshotItems = phase3Snapshots?.items || []

  const funnelRevenue = funnel.reduce((sum, f) => sum + toFiniteNumber(f?.weighted_revenue, 0), 0)
  const sourceValue = Math.max(0, Math.round(toFiniteNumber(funnelRevenue || revenue, 0)))
  const costsValue = Math.max(0, Math.round(toFiniteNumber(costs, 0)))
  const marginValue = Math.max(0, Math.round(toFiniteNumber(margin, 0)))
  const outgoingTotal = costsValue + marginValue
  const normalizedSourceValue = outgoingTotal > sourceValue ? outgoingTotal : sourceValue
  const sankeyData = {
    nodes: [
      { name: 'Pipeline' },
      { name: 'Ingresos' },
      { name: 'Costes' },
      { name: 'Margen' },
    ],
    links: [
      { source: 0, target: 1, value: normalizedSourceValue },
      { source: 1, target: 2, value: costsValue },
      { source: 1, target: 3, value: marginValue },
    ],
  }

  const governanceScheduledReports = governance?.scheduled_reports
  const governanceScheduledReportsActive = typeof governanceScheduledReports === 'object'
    ? toFiniteNumber(governanceScheduledReports?.active, 0)
    : toFiniteNumber(governanceScheduledReports, 0)

  async function handleCreateComment() {
    const trimmed = (commentText || '').trim()
    if (!trimmed) return
    await biCollaborationApi.createComment({
      dashboard_key: 'executive',
      widget_id: commentWidget,
      message: trimmed,
    })
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
    await biCollaborationApi.createSharedView({
      name,
      dashboard_key: 'executive',
      filters: {
        days,
        widget_id: commentWidget,
      },
    })
    setSharedViewName('')
    setSharedViewsTick((x) => x + 1)
    await refetchSharedViews()
  }

  async function handleToggleSharedView(view) {
    await biCollaborationApi.patchSharedView(view.id, { active: !view.active })
    setSharedViewsTick((x) => x + 1)
    await refetchSharedViews()
  }

  function handleApplySharedView(view) {
    const filters = view?.filters || {}
    const nextDays = toFiniteNumber(filters.days, days)
    if (nextDays > 0) setDays(nextDays)
    if (typeof filters.widget_id === 'string' && filters.widget_id.trim()) {
      setCommentWidget(filters.widget_id)
    }
  }

  async function handleRunGovernance() {
    await biCollaborationApi.runGovernanceChecks()
    setGovRunTick((x) => x + 1)
    await refetchGovRun()
  }

  async function handleSaveGovernanceRules() {
    if (!rulesDraft) return
    await biCollaborationApi.updateGovernanceRules(rulesDraft)
    await refetchRules()

    async function handleLogGovAuditEvent() {
      await biGovernanceAuditApi.logAccessEvent({
        user_id: govAuditUserFilter.trim() || 'console',
        resource: 'bi_dashboard',
        action: 'view',
      }).catch(() => null)
      setGovAuditTick(x => x + 1)
    }

    async function handleAddLineageEdge() {
      const src = newLineageSource.trim()
      const tgt = newLineageTarget.trim()
      if (!src || !tgt) return
      await biGovernanceAuditApi.trackLineage({ source_table: src, target_table: tgt }).catch(() => null)
      setNewLineageSource('')
      setNewLineageTarget('')
      setGovAuditTick(x => x + 1)
    }

    async function handleUpsertFieldSensitivity() {
      const field = newFieldName.trim()
      const dataset = newFieldDataset.trim()
      if (!field || !dataset) return
      await biGovernanceAuditApi.upsertFieldSensitivity({
        dataset_id: dataset,
        field_name: field,
        sensitivity: newFieldSensitivity,
      }).catch(() => null)
      setNewFieldName('')
      setNewFieldDataset('')
      setGovAuditTick(x => x + 1)
    }
  }

  async function handleToggleConnector(name, enabled) {
    await biIntelligenceApi.patchConnector(name, { enabled })
    setPhase2Tick((x) => x + 1)
    await refetchConnectors()
  }

  async function handleSyncConnector(name) {
    await biIntelligenceApi.syncConnector(name)
    setPhase2Tick((x) => x + 1)
    await refetchConnectors()
  }

  async function handleIssueEmbedToken() {
    const res = await biPlatformApi.embedToken({ dashboard_key: 'executive', expires_minutes: 60 })
    setEmbedToken(res?.data?.token || '')
  }

  async function handleToggleCatalogConnector(name, enabled) {
    await biPlatformApi.patchCatalogConnector(name, { enabled })
    setPhase3Tick((x) => x + 1)
    await refetchPhase3Catalog()
  }

  async function handleCreateCustomConnector() {
    const name = customConnectorName.trim()
    const endpoint = customConnectorEndpoint.trim()
    if (!name || !endpoint) return
    await biPlatformApi.createCustomConnector({
      name,
      endpoint,
      kind: 'rest',
      auth_type: 'api_key',
      enabled: true,
    })
    setCustomConnectorName('')
    setCustomConnectorEndpoint('')
    setPhase3Tick((x) => x + 1)
    await refetchPhase3Custom()
  }

  async function handleTestCustomConnector(id) {
    await biPlatformApi.testCustomConnector(id)
    setPhase3Tick((x) => x + 1)
    await refetchPhase3Custom()
  }

  async function handleCreateSnapshot() {
    await biPlatformApi.createSnapshot(datasetKey, {
      payload: {
        captured_at: new Date().toISOString(),
        revenue,
        margin,
        projects: totalProjects,
      },
    })
    setPhase3Tick((x) => x + 1)
    await refetchPhase3Snapshots()
  }

  async function handleDiffLastSnapshots() {
    const items = phase3Snapshots?.items || []
    if (items.length < 2) return
    const fromId = items[items.length - 2]?.id
    const toId = items[items.length - 1]?.id
    if (!fromId || !toId) return
    const res = await biPlatformApi.diffSnapshots(datasetKey, fromId, toId)
    setSnapshotDiff(res?.data || null)
  }

  if (!totalProjects && !revenue) return (
    <div style={{ padding: isMobile ? 14 : 32 }}>
      <PageHeader icon={<PieChartIcon size={18} />} title={t('bi.title')} subtitle={t('bi.subtitle')} />
      <EmptyDash />
    </div>
  )

  return (
    <div style={{ padding: isMobile ? 14 : 32 }}>

      {/* ── Header ── */}
      <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', flexWrap: 'wrap', gap: 16, marginBottom: 28 }}>
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <div style={{
              width: 36, height: 36, borderRadius: 10,
              background: 'var(--accent-muted)', border: '1px solid rgba(79,142,247,0.25)',
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              color: 'var(--accent)', flexShrink: 0,
            }}>
              <PieChartIcon size={18} />
            </div>
            <h1 style={{ fontSize: 22, fontWeight: 700, color: 'var(--text-1)', letterSpacing: '-0.01em', lineHeight: 1.2, margin: 0 }}>
              {t('bi.title')}
            </h1>
          </div>
          <p style={{ margin: '8px 0 0', fontSize: 13, color: 'var(--text-2)', paddingLeft: 46 }}>
            {t('bi.subtitle')} · últimos {days} días
          </p>
        </div>
        <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', justifyContent: isMobile ? 'flex-start' : 'flex-end' }}>
          {[7, 30, 90, 365].map(d => (
            <PeriodButton key={d} active={days === d} label={d === 365 ? '1a' : `${d}d`} onClick={() => setDays(d)} />
          ))}
        </div>
      </div>

      {/* ── KPI row ── */}
      <div style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(auto-fit, minmax(160px, 1fr))',
        gap: 14, marginBottom: 14,
      }}>
        <KpiCard
          icon="⬡" label={t('bi.active_projects')}
          value={totalProjects}
          color="var(--text-1)" accentBar={COLOR.accent}
        />
        <KpiCard
          icon="🚨" label={t('bi.critical_projects')}
          value={critProj}
          color={critProj > 0 ? COLOR.danger : COLOR.success}
          accentBar={critProj > 0 ? COLOR.danger : COLOR.success}
          sub={critProj > 0 ? 'Fuera de plazo o presupuesto' : 'Sin proyectos críticos'}
        />
        <KpiCard
          icon="▦" label={t('bi.overdue_tasks')}
          value={kpis?.tasks_overdue ?? 0}
          color={(kpis?.tasks_overdue ?? 0) > 0 ? COLOR.warning : COLOR.success}
          accentBar={(kpis?.tasks_overdue ?? 0) > 0 ? COLOR.warning : COLOR.success}
          sub={t('bi.need_attention')}
        />
        <KpiCard
          icon="💰" label={t('bi.budget_used')}
          value={kpis?.total_budget > 0 ? `${Math.round((kpis.total_spent / kpis.total_budget) * 100)}%` : '—'}
          color={COLOR.warning} accentBar={COLOR.warning}
          sub={`${fmtCur(kpis?.total_spent ?? 0, lang)} gastado`}
        />
        <KpiCard
          icon="⏱" label={t('bi.hours_this_week')}
          value={kpis?.hours_logged_this_week?.toFixed(0) ?? '0'}
          color="var(--sky-blue)" accentBar="var(--sky-blue)"
          sub="horas imputadas esta semana"
        />
        <KpiCard
          icon="🎫" label={t('bi.open_tickets')}
          value={kpis?.tasks_open ?? 0}
          color={COLOR.purple} accentBar={COLOR.purple}
          sub={t('bi.service_desk_short')}
        />
      </div>

      {/* ── Gauge row ── */}
      <div style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))',
        gap: 14, marginBottom: 20,
      }}>
        <GaugeCard
          label="Proyectos a tiempo"
          value={onTimePct}
          color={onTimeColor}
          sub={onTimePct >= 80 ? 'Excelente estado' : onTimePct >= 60 ? 'Aceptable' : 'Requiere atención'}
        />
        <GaugeCard
          label="Margen bruto"
          value={marginPct}
          color={marginColor}
          sub={`${fmtCur(margin, lang)} de ${fmtCur(revenue, lang)}`}
        />
        {normalizedUtilPct != null && (
          <GaugeCard
            label="Utilización equipo"
            value={Math.round(normalizedUtilPct)}
            color={normalizedUtilPct >= 70 ? COLOR.success : normalizedUtilPct >= 50 ? COLOR.warning : COLOR.danger}
            sub={normalizedUtilPct >= 70 ? 'Buen aprovechamiento' : 'Capacidad disponible'}
          />
        )}
      </div>

      {/* ── Charts row ── */}
      <div style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))',
        gap: 14, marginBottom: 20,
      }}>
        {/* Distribución por tipo */}
        <div style={S.card}>
          <div style={{ ...S.cardPad, borderBottom: '1px solid var(--surface-4)' }}>
            <div style={S.sectionTitle}>Proyectos por tipo</div>
          </div>
          <div style={S.cardPad}>
            {byType.length === 0 ? (
              <div style={{ textAlign: 'center', color: 'var(--text-3)', fontSize: 12, padding: '16px 0' }}>Sin datos</div>
            ) : byType.map((row, i) => (
              <BarRow
                key={row.label}
                label={row.label || 'Sin tipo'}
                count={row.value || 0}
                total={totalByType}
                color={typePalette[i % typePalette.length]}
              />
            ))}
          </div>
        </div>

        {/* Salud de proyectos */}
        <div style={S.card}>
          <div style={{ ...S.cardPad, borderBottom: '1px solid var(--surface-4)' }}>
            <div style={S.sectionTitle}>Estado de salud</div>
          </div>
          <div style={S.cardPad}>
            {totalProjects === 0 ? (
              <div style={{ textAlign: 'center', color: 'var(--text-3)', fontSize: 12, padding: '16px 0' }}>Sin datos</div>
            ) : healthRows.map(row => (
              <BarRow
                key={row.label}
                label={row.label}
                count={row.count}
                total={totalProjects}
                color={row.color}
              />
            ))}
          </div>
        </div>
      </div>

      {/* ── Advanced visualization ── */}
      <div style={{ ...S.card, marginBottom: 20 }}>
        <div style={{ ...S.cardPad, borderBottom: '1px solid var(--surface-4)' }}>
          <div style={S.sectionTitle}>Flujo de rentabilidad (Sankey)</div>
        </div>
        <div style={S.cardPad}>
          <RevenueFlowSankey data={sankeyData} />
        </div>
      </div>

      {/* ── Revenue section ── */}
      {revenue > 0 && (
        <div style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))',
          gap: 14, marginBottom: 20,
        }}>
          <KpiCard
            icon="📈" label="Ingresos totales"
            value={fmtCur(revenue, lang)}
            color={COLOR.accent} accentBar={COLOR.accent}
          />
          <KpiCard
            icon="💸" label="Costes totales"
            value={fmtCur(costs, lang)}
            color={COLOR.warning} accentBar={COLOR.warning}
          />
          <KpiCard
            icon="✅" label="Margen bruto"
            value={fmtCur(margin, lang)}
            color={margin >= 0 ? COLOR.success : COLOR.danger}
            accentBar={margin >= 0 ? COLOR.success : COLOR.danger}
            sub={`${marginPct}% de margen`}
          />
        </div>
      )}

      {/* ── BI Intelligence row ── */}
      <div style={{
        display: 'grid',
        gridTemplateColumns: isMobile ? '1fr' : 'repeat(auto-fit, minmax(360px, 1fr))',
        gap: 14, marginBottom: 20,
      }}>
        <NarrativeCard lang={lang} />
        <AskDataWidget />
        <VisualQueryBuilderWidget />
      </div>

      {/* ── Collaboration + governance ── */}
      <div style={{
        display: 'grid',
        gridTemplateColumns: isMobile ? '1fr' : 'repeat(auto-fit, minmax(360px, 1fr))',
        gap: 14,
        marginBottom: 20,
      }}>
        <div style={S.card}>
          <div style={{ ...S.cardPad, borderBottom: '1px solid var(--surface-4)' }}>
            <div style={S.sectionTitle}>Colaboración BI</div>
          </div>
          <div style={{ ...S.cardPad, display: 'flex', flexDirection: 'column', gap: 10 }}>
            <div style={{
              border: '1px solid var(--surface-4)',
              borderRadius: 10,
              padding: 10,
              display: 'grid',
              gap: 8,
            }}>
              <div style={{ fontSize: 11, fontWeight: 700, color: 'var(--text-2)', letterSpacing: '0.05em', textTransform: 'uppercase' }}>
                Vistas compartidas
              </div>
              <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
                <input
                  value={sharedViewName}
                  onChange={(e) => setSharedViewName(e.target.value)}
                  placeholder="Nombre de la vista..."
                  style={{
                    flex: 1,
                    minWidth: 170,
                    background: 'var(--surface-3)',
                    border: '1px solid var(--surface-4)',
                    color: 'var(--text-1)',
                    borderRadius: 8,
                    padding: '8px 10px',
                    fontSize: 12,
                  }}
                />
                <button
                  type="button"
                  onClick={handleCreateSharedView}
                  style={{
                    border: `1px solid ${COLOR.success}`,
                    background: `${COLOR.success}22`,
                    color: COLOR.success,
                    borderRadius: 8,
                    padding: '7px 12px',
                    fontSize: 12,
                    fontWeight: 700,
                    cursor: 'pointer',
                  }}
                >
                  Guardar vista
                </button>
              </div>
              <div style={{ display: 'grid', gap: 7 }}>
                <input
                  value={sharedViewsSearch}
                  onChange={(e) => setSharedViewsSearch(e.target.value)}
                  placeholder="Buscar vista compartida por nombre..."
                  style={{
                    background: 'var(--surface-3)',
                    border: '1px solid var(--surface-4)',
                    color: 'var(--text-1)',
                    borderRadius: 8,
                    padding: '8px 10px',
                    fontSize: 12,
                  }}
                />
                <select
                  value={sharedViewsSort}
                  onChange={(e) => setSharedViewsSort(e.target.value)}
                  style={{
                    background: 'var(--surface-3)',
                    border: '1px solid var(--surface-4)',
                    color: 'var(--text-1)',
                    borderRadius: 8,
                    padding: '8px 10px',
                    fontSize: 12,
                  }}
                >
                  <option value="date_desc">Más recientes primero</option>
                  <option value="date_asc">Más antiguas primero</option>
                  <option value="author_asc">Autor (A-Z)</option>
                  <option value="name_asc">Nombre (A-Z)</option>
                </select>
                <label style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: 8,
                  fontSize: 11,
                  color: 'var(--text-2)',
                }}>
                  <input
                    type="checkbox"
                    checked={showInactiveSharedViews}
                    onChange={(e) => setShowInactiveSharedViews(e.target.checked)}
                  />
                  Mostrar vistas inactivas
                  <span style={{ color: 'var(--text-3)' }}>
                    ({activeSharedViews} activas{showInactiveSharedViews ? ` · ${inactiveSharedViews} inactivas` : ''})
                  </span>
                </label>
                {sortedSharedViews.length === 0 ? (
                  <div style={{ color: 'var(--text-3)', fontSize: 12 }}>
                    {sharedViews.length === 0
                      ? (showInactiveSharedViews
                        ? 'No hay vistas compartidas todavía.'
                        : 'No hay vistas activas. Activa "Mostrar vistas inactivas" para restaurarlas.')
                      : 'No hay vistas que coincidan con la búsqueda.'}
                  </div>
                ) : sortedSharedViews.map((v) => (
                  <div key={v.id} style={{
                    border: '1px solid var(--surface-4)',
                    borderRadius: 8,
                    padding: 8,
                    display: 'flex',
                    flexWrap: 'wrap',
                    justifyContent: 'space-between',
                    alignItems: 'center',
                    gap: 8,
                  }}>
                    <div style={{ display: 'grid', gap: 2 }}>
                      <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-1)' }}>{v.name}</div>
                      <div style={{ fontSize: 10, color: 'var(--text-3)' }}>
                        {v.dashboard_key} · {v.created_by_name || '—'} · {v.active === false ? 'inactiva' : 'activa'}
                        {v.created_at ? ` · ${new Date(v.created_at).toLocaleString(getLocale(lang))}` : ''}
                      </div>
                    </div>
                    <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
                      <button
                        type="button"
                        onClick={() => handleApplySharedView(v)}
                        style={{
                          border: '1px solid var(--surface-4)',
                          background: 'transparent',
                          color: 'var(--text-2)',
                          borderRadius: 6,
                          padding: '4px 8px',
                          fontSize: 11,
                          cursor: 'pointer',
                        }}
                      >
                        Aplicar
                      </button>
                      <button
                        type="button"
                        onClick={() => handleToggleSharedView(v)}
                        style={{
                          border: `1px solid ${v.active ? COLOR.warning : COLOR.success}`,
                          background: v.active ? `${COLOR.warning}22` : `${COLOR.success}22`,
                          color: v.active ? COLOR.warning : COLOR.success,
                          borderRadius: 6,
                          padding: '4px 8px',
                          fontSize: 11,
                          cursor: 'pointer',
                        }}
                      >
                        {v.active ? 'Desactivar' : 'Activar'}
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            </div>

            <select
              value={commentWidget}
              onChange={(e) => setCommentWidget(e.target.value)}
              style={{
                background: 'var(--surface-3)',
                border: '1px solid var(--surface-4)',
                color: 'var(--text-1)',
                borderRadius: 8,
                padding: '8px 10px',
                fontSize: 12,
              }}
            >
              <option value="kpi_grid">KPI grid</option>
              <option value="health_chart">Estado de salud</option>
              <option value="profit_table">Rentabilidad por proyecto</option>
              <option value="ai_narrative">Narrativa IA</option>
            </select>
            <textarea
              value={commentText}
              onChange={(e) => setCommentText(e.target.value)}
              rows={3}
              placeholder="Añade comentario para este widget..."
              style={{
                background: 'var(--surface-3)',
                border: '1px solid var(--surface-4)',
                color: 'var(--text-1)',
                borderRadius: 8,
                padding: 10,
                fontSize: 12,
                resize: 'vertical',
              }}
            />
            <button
              type="button"
              onClick={handleCreateComment}
              style={{
                alignSelf: 'flex-start',
                border: `1px solid ${COLOR.accent}`,
                background: COLOR.accentMuted,
                color: COLOR.accent,
                borderRadius: 8,
                padding: '7px 12px',
                fontSize: 12,
                fontWeight: 700,
                cursor: 'pointer',
              }}
            >
              Guardar comentario
            </button>
            <div style={{ borderTop: '1px solid var(--surface-4)', paddingTop: 10, display: 'grid', gap: 8 }}>
              {comments.length === 0 ? (
                <div style={{ color: 'var(--text-3)', fontSize: 12 }}>No hay comentarios para este widget.</div>
              ) : comments.map((c) => (
                <div key={c.id} style={{ border: '1px solid var(--surface-4)', borderRadius: 8, padding: 9 }}>
                  <div style={{ fontSize: 12, color: 'var(--text-1)', marginBottom: 6 }}>{c.message}</div>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 8 }}>
                    <span style={{ fontSize: 10, color: 'var(--text-3)' }}>{c.status || 'open'}</span>
                    {c.status !== 'resolved' && (
                      <button
                        type="button"
                        onClick={() => handleResolveComment(c.id)}
                        style={{
                          border: '1px solid var(--surface-4)',
                          background: 'transparent',
                          color: 'var(--text-2)',
                          borderRadius: 6,
                          padding: '4px 8px',
                          fontSize: 11,
                          cursor: 'pointer',
                        }}
                      >
                        Marcar resuelto
                      </button>
                    )}
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>

        <div style={S.card}>
          <div style={{ ...S.cardPad, borderBottom: '1px solid var(--surface-4)' }}>
            <div style={S.sectionTitle}>Gobernanza BI</div>
          </div>
          <div style={{ ...S.cardPad, display: 'grid', gap: 10 }}>
            <div style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(3, minmax(80px, 1fr))',
              gap: 8,
            }}>
              <KpiCard label="Datasets" value={governance?.datasets || 0} color={COLOR.accent} accentBar={COLOR.accent} />
              <KpiCard label="Dashboards" value={governance?.dashboards || 0} color={COLOR.success} accentBar={COLOR.success} />
              <KpiCard label="Programados" value={governanceScheduledReportsActive} color={COLOR.warning} accentBar={COLOR.warning} />
            </div>
            <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
              <button
                type="button"
                onClick={handleRunGovernance}
                style={{
                  border: `1px solid ${COLOR.accent}`,
                  background: COLOR.accentMuted,
                  color: COLOR.accent,
                  borderRadius: 8,
                  padding: '7px 12px',
                  fontSize: 12,
                  fontWeight: 700,
                  cursor: 'pointer',
                }}
              >
                Ejecutar checks
              </button>
              <span style={{ fontSize: 11, color: 'var(--text-3)', alignSelf: 'center' }}>
                {governanceRun?.timestamp ? `Última ejecución: ${new Date(governanceRun.timestamp).toLocaleString(getLocale(lang))}` : 'Sin ejecución reciente'}
              </span>
            </div>
            <label style={{ display: 'grid', gap: 6 }}>
              <span style={{ fontSize: 11, fontWeight: 600, color: 'var(--text-2)' }}>Caducidad de caché BI (segundos)</span>
              <input
                type="number"
                min={60}
                step={60}
                value={rulesDraft?.cache_ttl_seconds ?? 3600}
                onChange={(e) => setRulesDraft((prev) => ({ ...prev, cache_ttl_seconds: Number(e.target.value || 3600) }))}
                style={{
                  background: 'var(--surface-3)',
                  border: '1px solid var(--surface-4)',
                  color: 'var(--text-1)',
                  borderRadius: 8,
                  padding: '8px 10px',
                  fontSize: 12,
                }}
              />
            </label>
            <button
              type="button"
              onClick={handleSaveGovernanceRules}
              style={{
                justifySelf: 'flex-start',
                border: '1px solid var(--surface-4)',
                background: 'transparent',
                color: 'var(--text-2)',
                borderRadius: 8,
                padding: '7px 12px',
                fontSize: 12,
                fontWeight: 700,
                cursor: 'pointer',
              }}
            >
              Guardar reglas
            </button>
          </div>
        </div>
      </div>

      {/* ── BI Intelligence: advanced analytics ── */}
      <div style={{
        display: 'grid',
        gridTemplateColumns: isMobile ? '1fr' : 'repeat(auto-fit, minmax(340px, 1fr))',
        gap: 14,
        marginBottom: 20,
      }}>
        <div style={S.card}>
          <div style={{ ...S.cardPad, borderBottom: '1px solid var(--surface-4)' }}>
            <div style={S.sectionTitle}>Fase 2 ML: Forecast y anomalías</div>
          </div>
          <div style={{ ...S.cardPad, display: 'grid', gap: 8 }}>
            {forecastHead.length === 0 ? (
              <div style={{ color: 'var(--text-3)', fontSize: 12 }}>Sin forecast disponible.</div>
            ) : forecastHead.map((f) => (
              <div key={f.month} style={{ border: '1px solid var(--surface-4)', borderRadius: 8, padding: 8 }}>
                <div style={{ fontSize: 11, color: 'var(--text-3)', marginBottom: 4 }}>{f.month}</div>
                <div style={{ fontSize: 14, fontWeight: 700, color: 'var(--text-1)' }}>{fmtCur(f.predicted_revenue, lang)}</div>
                <div style={{ fontSize: 11, color: 'var(--text-3)' }}>
                  [{fmtCur(f.lower_bound, lang)} - {fmtCur(f.upper_bound, lang)}]
                </div>
              </div>
            ))}
            <div style={{ fontSize: 12, color: anomalies.length > 0 ? COLOR.warning : COLOR.success }}>
              Anomalías detectadas: {anomalies.length}
            </div>
          </div>
        </div>

        <div style={S.card}>
          <div style={{ ...S.cardPad, borderBottom: '1px solid var(--surface-4)' }}>
            <div style={S.sectionTitle}>Fase 2 Conectores (5)</div>
          </div>
          <div style={{ ...S.cardPad, display: 'grid', gap: 8 }}>
            {connectors.length === 0 ? (
              <div style={{ color: 'var(--text-3)', fontSize: 12 }}>Sin conectores configurados.</div>
            ) : connectors.map(([name, cfg]) => (
              <div key={name} style={{ border: '1px solid var(--surface-4)', borderRadius: 8, padding: 8 }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 8 }}>
                  <strong style={{ fontSize: 12, color: 'var(--text-1)', textTransform: 'capitalize' }}>{name}</strong>
                  <span style={{ fontSize: 10, color: cfg.enabled ? COLOR.success : 'var(--text-3)' }}>
                    {cfg.enabled ? 'enabled' : 'disabled'}
                  </span>
                </div>
                <div style={{ display: 'flex', gap: 8, marginTop: 8, flexWrap: 'wrap' }}>
                  <button
                    type="button"
                    onClick={() => handleToggleConnector(name, !cfg.enabled)}
                    style={{
                      border: '1px solid var(--surface-4)',
                      background: 'transparent',
                      color: 'var(--text-2)',
                      borderRadius: 6,
                      padding: '4px 8px',
                      fontSize: 11,
                      cursor: 'pointer',
                    }}
                  >
                    {cfg.enabled ? 'Desactivar' : 'Activar'}
                  </button>
                  <button
                    type="button"
                    onClick={() => handleSyncConnector(name)}
                    style={{
                      border: `1px solid ${COLOR.accent}`,
                      background: COLOR.accentMuted,
                      color: COLOR.accent,
                      borderRadius: 6,
                      padding: '4px 8px',
                      fontSize: 11,
                      cursor: 'pointer',
                    }}
                  >
                    Sync
                  </button>
                  <span style={{ fontSize: 10, color: 'var(--text-3)', alignSelf: 'center' }}>
                    {cfg.last_sync_at ? `último: ${new Date(cfg.last_sync_at).toLocaleString(getLocale(lang))}` : 'sin sync'}
                  </span>
                </div>
              </div>
            ))}
          </div>
        </div>

        <div style={S.card}>
          <div style={{ ...S.cardPad, borderBottom: '1px solid var(--surface-4)' }}>
            <div style={S.sectionTitle}>Fase 2 Report Builder + Delivery</div>
          </div>
          <div style={{ ...S.cardPad, display: 'grid', gap: 10 }}>
            <select
              value={presetId}
              onChange={(e) => setPresetId(e.target.value)}
              style={{
                background: 'var(--surface-3)',
                border: '1px solid var(--surface-4)',
                color: 'var(--text-1)',
                borderRadius: 8,
                padding: '8px 10px',
                fontSize: 12,
              }}
            >
              {(reportPresets?.items || []).map((p) => (
                <option key={p.id} value={p.id}>{p.name}</option>
              ))}
            </select>
            <button
              type="button"
              onClick={() => refetchPreview()}
              style={{
                justifySelf: 'flex-start',
                border: `1px solid ${COLOR.accent}`,
                background: COLOR.accentMuted,
                color: COLOR.accent,
                borderRadius: 8,
                padding: '7px 12px',
                fontSize: 12,
                fontWeight: 700,
                cursor: 'pointer',
              }}
            >
              Previsualizar preset
            </button>
            <div style={{ fontSize: 11, color: 'var(--text-3)' }}>
              Filas preview: {previewData?.count || 0}
            </div>
            <div style={{ fontSize: 11, color: 'var(--text-3)' }}>
              Delivery activo: {deliveryOverview?.active ?? 0} · errores: {deliveryOverview?.errored ?? 0} · slack: {deliveryOverview?.with_slack ?? 0}
            </div>
            <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
              <button
                type="button"
                onClick={() => setStreamLive((v) => !v)}
                style={{
                  border: `1px solid ${streamLive ? COLOR.success : 'var(--surface-4)'}`,
                  background: streamLive ? `${COLOR.success}22` : 'transparent',
                  color: streamLive ? COLOR.success : 'var(--text-2)',
                  borderRadius: 8,
                  padding: '6px 10px',
                  fontSize: 11,
                  cursor: 'pointer',
                }}
              >
                {streamLive ? 'Streaming ON' : 'Activar streaming'}
              </button>
              <span style={{ fontSize: 10, color: 'var(--text-3)', alignSelf: 'center' }}>
                {streamSnapshot?.timestamp ? `snapshot ${new Date(streamSnapshot.timestamp).toLocaleTimeString(getLocale(lang))}` : 'sin snapshot realtime'}
              </span>
            </div>
          </div>
        </div>
      </div>

      {/* ── BI Platform: platform scale ── */}
      <div style={{
        display: 'grid',
        gridTemplateColumns: isMobile ? '1fr' : 'repeat(auto-fit, minmax(340px, 1fr))',
        gap: 14,
        marginBottom: 20,
      }}>
        <div style={S.card}>
          <div style={{ ...S.cardPad, borderBottom: '1px solid var(--surface-4)' }}>
            <div style={S.sectionTitle}>Fase 3 Embed SDK</div>
          </div>
          <div style={{ ...S.cardPad, display: 'grid', gap: 8 }}>
            <div style={{ fontSize: 12, color: 'var(--text-2)' }}>
              {phase3Manifest?.name || 'Contecflow BI Embed SDK'} · v{phase3Manifest?.version || '1.0.0'}
            </div>
            <div style={{ fontSize: 11, color: 'var(--text-3)' }}>
              Features: {(phase3Manifest?.features || []).join(', ') || 'n/a'}
            </div>
            <button
              type="button"
              onClick={handleIssueEmbedToken}
              style={{
                justifySelf: 'flex-start',
                border: `1px solid ${COLOR.accent}`,
                background: COLOR.accentMuted,
                color: COLOR.accent,
                borderRadius: 8,
                padding: '7px 12px',
                fontSize: 12,
                fontWeight: 700,
                cursor: 'pointer',
              }}
            >
              Emitir token embed
            </button>
            <div style={{ fontSize: 10, color: 'var(--text-3)', wordBreak: 'break-all' }}>
              {embedToken ? `JWT: ${embedToken.slice(0, 70)}...` : 'Sin token emitido'}
            </div>
          </div>
        </div>

        <div style={S.card}>
          <div style={{ ...S.cardPad, borderBottom: '1px solid var(--surface-4)' }}>
            <div style={S.sectionTitle}>Fase 3 Conectores (20+)</div>
          </div>
          <div style={{ ...S.cardPad, display: 'grid', gap: 10 }}>
            <div style={{ fontSize: 12, color: 'var(--text-2)' }}>
              Total catálogo: {phase3Catalog?.count || 0} · activos: {phase3CatalogActive}
            </div>
            <div style={{ display: 'grid', gap: 6 }}>
              {phase3CatalogEntries.slice(0, 6).map(([name, cfg]) => (
                <div key={name} style={{ border: '1px solid var(--surface-4)', borderRadius: 8, padding: 8 }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 8 }}>
                    <strong style={{ fontSize: 12, color: 'var(--text-1)' }}>{name}</strong>
                    <button
                      type="button"
                      onClick={() => handleToggleCatalogConnector(name, !cfg?.enabled)}
                      style={{
                        border: '1px solid var(--surface-4)',
                        background: 'transparent',
                        color: cfg?.enabled ? COLOR.success : 'var(--text-2)',
                        borderRadius: 6,
                        padding: '4px 8px',
                        fontSize: 11,
                        cursor: 'pointer',
                      }}
                    >
                      {cfg?.enabled ? 'Activo' : 'Inactivo'}
                    </button>
                  </div>
                </div>
              ))}
            </div>
            <div style={{ borderTop: '1px solid var(--surface-4)', paddingTop: 8, display: 'grid', gap: 6 }}>
              <input
                value={customConnectorName}
                onChange={(e) => setCustomConnectorName(e.target.value)}
                placeholder="Nombre conector custom"
                style={{
                  background: 'var(--surface-3)',
                  border: '1px solid var(--surface-4)',
                  color: 'var(--text-1)',
                  borderRadius: 8,
                  padding: '8px 10px',
                  fontSize: 12,
                }}
              />
              <input
                value={customConnectorEndpoint}
                onChange={(e) => setCustomConnectorEndpoint(e.target.value)}
                placeholder="https://api.partner.com/v1"
                style={{
                  background: 'var(--surface-3)',
                  border: '1px solid var(--surface-4)',
                  color: 'var(--text-1)',
                  borderRadius: 8,
                  padding: '8px 10px',
                  fontSize: 12,
                }}
              />
              <button
                type="button"
                onClick={handleCreateCustomConnector}
                style={{
                  justifySelf: 'flex-start',
                  border: `1px solid ${COLOR.accent}`,
                  background: COLOR.accentMuted,
                  color: COLOR.accent,
                  borderRadius: 8,
                  padding: '6px 10px',
                  fontSize: 11,
                  cursor: 'pointer',
                }}
              >
                Crear custom
              </button>
              <div style={{ display: 'grid', gap: 6 }}>
                {phase3CustomItems.slice(0, 3).map((c) => (
                  <div key={c.id} style={{ border: '1px solid var(--surface-4)', borderRadius: 8, padding: 8 }}>
                    <div style={{ fontSize: 12, color: 'var(--text-1)' }}>{c.name}</div>
                    <div style={{ fontSize: 10, color: 'var(--text-3)' }}>{c.endpoint}</div>
                    <button
                      type="button"
                      onClick={() => handleTestCustomConnector(c.id)}
                      style={{
                        marginTop: 6,
                        border: '1px solid var(--surface-4)',
                        background: 'transparent',
                        color: 'var(--text-2)',
                        borderRadius: 6,
                        padding: '4px 8px',
                        fontSize: 11,
                        cursor: 'pointer',
                      }}
                    >
                      Test
                    </button>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>

        <div style={S.card}>
          <div style={{ ...S.cardPad, borderBottom: '1px solid var(--surface-4)' }}>
            <div style={S.sectionTitle}>Fase 3 Lineage y Versionado</div>
          </div>
          <div style={{ ...S.cardPad, display: 'grid', gap: 8 }}>
            <div style={{ fontSize: 12, color: 'var(--text-2)' }}>
              Edges lineage: {phase3LineageEdges.length} · audit logs: {phase3AuditEntries.length}
            </div>
            <button
              type="button"
              onClick={() => refetchPhase3Lineage()}
              style={{
                justifySelf: 'flex-start',
                border: '1px solid var(--surface-4)',
                background: 'transparent',
                color: 'var(--text-2)',
                borderRadius: 8,
                padding: '6px 10px',
                fontSize: 11,
                cursor: 'pointer',
              }}
            >
              Refrescar lineage
            </button>
            <input
              value={datasetKey}
              onChange={(e) => setDatasetKey(e.target.value)}
              placeholder="dataset key"
              style={{
                background: 'var(--surface-3)',
                border: '1px solid var(--surface-4)',
                color: 'var(--text-1)',
                borderRadius: 8,
                padding: '8px 10px',
                fontSize: 12,
              }}
            />
            <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
              <button
                type="button"
                onClick={handleCreateSnapshot}
                style={{
                  border: `1px solid ${COLOR.accent}`,
                  background: COLOR.accentMuted,
                  color: COLOR.accent,
                  borderRadius: 8,
                  padding: '6px 10px',
                  fontSize: 11,
                  cursor: 'pointer',
                }}
              >
                Crear snapshot
              </button>
              <button
                type="button"
                onClick={handleDiffLastSnapshots}
                style={{
                  border: '1px solid var(--surface-4)',
                  background: 'transparent',
                  color: 'var(--text-2)',
                  borderRadius: 8,
                  padding: '6px 10px',
                  fontSize: 11,
                  cursor: 'pointer',
                }}
              >
                Diff últimos 2
              </button>
            </div>
            <div style={{ fontSize: 11, color: 'var(--text-3)' }}>
              Snapshots: {phase3SnapshotItems.length}
            </div>
            <div style={{ fontSize: 11, color: 'var(--text-3)' }}>
              Cambios último diff: {snapshotDiff?.change_count ?? 0}
            </div>
          </div>
        </div>
      </div>

      {/* ── Top projects table ── */}
      {topProjects.length > 0 && (
        <div style={S.card}>
          <div style={{ ...S.cardPad, borderBottom: '1px solid var(--surface-4)', display: 'flex', alignItems: 'center', gap: 10 }}>
            <div style={S.sectionTitle}>Rentabilidad por proyecto</div>
            <span style={{
              fontSize: 10, fontWeight: 700, color: 'var(--text-3)',
              background: 'var(--surface-4)', borderRadius: 12,
              padding: '2px 8px', marginLeft: 4, marginTop: -14,
            }}>{topProjects.length}</span>
          </div>
          <div style={{ overflowX: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse' }}>
              <thead>
                <tr style={{ background: 'var(--surface-3)' }}>
                  {['Proyecto', 'Cliente', 'Ingresos', 'Costes', 'Margen', 'Estado'].map((col, i) => (
                    <th key={col} style={{
                      padding: '10px 16px',
                      textAlign: i === 0 ? 'left' : 'center',
                      fontSize: 10, fontWeight: 700, color: 'var(--text-3)',
                      textTransform: 'uppercase', letterSpacing: '0.08em', whiteSpace: 'nowrap',
                    }}>{col}</th>
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
                    <tr key={p.project_id || p.id} style={{
                      borderBottom: '1px solid var(--surface-4)',
                      background: idx % 2 === 0 ? 'transparent' : 'var(--surface-3)08',
                    }}>
                      <td style={{ padding: '12px 16px' }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                          <ProjectAvatar name={p.project_name || p.name} code={p.project_code || p.code} />
                          <div>
                            <div style={{ fontSize: 13, fontWeight: 500, color: 'var(--text-1)' }}>
                              {p.project_name || p.name}
                            </div>
                            {(p.project_code || p.code) && (
                              <div style={{ fontSize: 10, color: 'var(--text-3)' }}>{p.project_code || p.code}</div>
                            )}
                          </div>
                        </div>
                      </td>
                      <td style={{ padding: '12px 16px', textAlign: 'center' }}>
                        <span style={{ fontSize: 12, color: 'var(--text-2)' }}>{p.client_name || '—'}</span>
                      </td>
                      <td style={{ padding: '12px 16px', textAlign: 'center' }}>
                        <span style={{ fontSize: 13, fontWeight: 600, color: 'var(--text-1)' }}>{fmtCur(rev, lang)}</span>
                      </td>
                      <td style={{ padding: '12px 16px', textAlign: 'center' }}>
                        <span style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-2)', background: 'var(--surface-4)', padding: '3px 8px', borderRadius: 6, whiteSpace: 'nowrap' }}>
                          {fmtCur(cost, lang)}
                        </span>
                      </td>
                      <td style={{ padding: '12px 16px', minWidth: 160 }}>
                        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                          <MarginBar margin={mgn} revenue={rev} />
                        </div>
                      </td>
                      <td style={{ padding: '12px 16px', textAlign: 'center' }}>
                        <span style={{
                          display: 'inline-flex', alignItems: 'center', gap: 4,
                          fontSize: 11, fontWeight: 700, color: statusColor,
                          background: `${statusColor}18`,
                          border: `1px solid ${statusColor}30`,
                          borderRadius: 6, padding: '3px 9px',
                          textTransform: 'uppercase', letterSpacing: '0.05em',
                        }}>{p.status || '—'}</span>
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* ── BI Phase 4-A: Visualización avanzada ECharts ── */}
      <BiAdvancedViz style={{ marginBottom: 20 }} />

      {/* ── BI Phase 4-B: Report Builder v2 ── */}
      <div style={{ ...S.card, marginBottom: 20 }}>
        <div style={{ ...S.cardPad, borderBottom: '1px solid var(--surface-4)', display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: 8 }}>
          <span style={{ fontWeight: 700, fontSize: '1rem' }}>Report Builder v2 — 15+ presets</span>
          <span style={{ fontSize: 11, color: 'var(--text-3)' }}>{(rbv2Presets?.items || []).length} presets disponibles</span>
        </div>
        <div style={{ ...S.cardPad }}>
          <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginBottom: 14 }}>
            {(rbv2Presets?.items || []).slice(0, 8).map(p => (
              <button
                key={p.id}
                onClick={() => setRbv2SelectedPreset(p.id)}
                style={{
                  padding: '5px 14px', borderRadius: 20, fontSize: 11, cursor: 'pointer',
                  border: `1.5px solid ${rbv2SelectedPreset === p.id ? COLOR.accent : 'var(--surface-4)'}`,
                  background: rbv2SelectedPreset === p.id ? `${COLOR.accent}18` : 'transparent',
                  color: rbv2SelectedPreset === p.id ? COLOR.accent : 'var(--text-2)',
                  fontWeight: rbv2SelectedPreset === p.id ? 700 : 400,
                }}
              >{p.name}</button>
            ))}
            {(rbv2Presets?.items || []).length > 8 && (
              <span style={{ fontSize: 11, color: 'var(--text-3)', alignSelf: 'center' }}>+{(rbv2Presets?.items || []).length - 8} más</span>
            )}
          </div>
          <div style={{ display: 'flex', gap: 10, marginBottom: 14 }}>
            <button
              onClick={async () => {
                try {
                  const res = await biReportBuilderV2Api.preview(rbv2SelectedPreset, 10)
                  setRbv2PreviewData(res.data)
                } catch (_e) { /* ignore */ }
              }}
              style={{ padding: '8px 20px', borderRadius: 8, background: COLOR.accent, color: '#fff', border: 'none', cursor: 'pointer', fontSize: 12, fontWeight: 600 }}
            >Vista previa</button>
            <button
              onClick={async () => {
                try {
                  const res = await biReportBuilderV2Api.export(rbv2SelectedPreset, 'json')
                  const blob = new Blob([JSON.stringify(res.data, null, 2)], { type: 'application/json' })
                  const url = URL.createObjectURL(blob)
                  const a = document.createElement('a'); a.href = url; a.download = res.data.filename || 'report.json'; a.click(); URL.revokeObjectURL(url)
                } catch (_e) { /* ignore */ }
              }}
              style={{ padding: '8px 20px', borderRadius: 8, background: '#22c55e', color: '#fff', border: 'none', cursor: 'pointer', fontSize: 12, fontWeight: 600 }}
            >Exportar JSON</button>
          </div>
          {rbv2PreviewData && (
            <div style={{ overflowX: 'auto' }}>
              <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12 }}>
                <thead>
                  <tr style={{ background: 'var(--surface-3)' }}>
                    {(rbv2PreviewData.columns || []).map(c => (
                      <th key={c} style={{ padding: '8px 12px', textAlign: 'left', color: 'var(--text-2)', fontWeight: 700, fontSize: 11, textTransform: 'uppercase', letterSpacing: '0.06em', borderBottom: '1px solid var(--surface-4)' }}>{c.replace(/_/g, ' ')}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {(rbv2PreviewData.rows || []).map((row, ri) => (
                    <tr key={ri} style={{ borderBottom: '1px solid var(--surface-4)' }}>
                      {(rbv2PreviewData.columns || []).map(c => (
                        <td key={c} style={{ padding: '8px 12px', color: 'var(--text-1)' }}>{row[c] ?? '—'}</td>
                      ))}
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

      {/* ── BI Phase 4-C: Smart Alerts ── */}
      <div style={{ display: 'grid', gridTemplateColumns: isMobile ? '1fr' : '1fr 1fr', gap: 14, marginBottom: 20 }}>
        <div style={S.card}>
          <div style={{ ...S.cardPad, borderBottom: '1px solid var(--surface-4)', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
            <span style={{ fontWeight: 700, fontSize: '1rem' }}>Reglas de alerta inteligente</span>
            <button
              onClick={async () => {
                try {
                  await biSmartAlertsApi.evaluate()
                  setAlertsTick(x => x + 1)
                } catch (_e) { /* ignore */ }
              }}
              style={{ padding: '5px 14px', borderRadius: 8, background: COLOR.accent, color: '#fff', border: 'none', cursor: 'pointer', fontSize: 11, fontWeight: 600 }}
            >Evaluar ahora</button>
          </div>
          <div style={{ ...S.cardPad }}>
            <div style={{ display: 'flex', gap: 8, marginBottom: 14, flexWrap: 'wrap' }}>
              <input
                value={newAlertName}
                onChange={e => setNewAlertName(e.target.value)}
                placeholder="Nombre de la regla"
                style={{ flex: 1, minWidth: 120, padding: '7px 12px', borderRadius: 8, border: '1px solid var(--surface-4)', background: 'var(--surface-1)', color: 'var(--text-1)', fontSize: 12 }}
              />
              <select
                value={newAlertMetric}
                onChange={e => setNewAlertMetric(e.target.value)}
                style={{ padding: '7px 12px', borderRadius: 8, border: '1px solid var(--surface-4)', background: 'var(--surface-1)', color: 'var(--text-1)', fontSize: 12 }}
              >
                {(alertSupportedMetrics?.metrics || [{ key: 'revenue', label: 'Revenue' }]).map(m => (
                  <option key={m.key} value={m.key}>{m.label}</option>
                ))}
              </select>
              <select
                value={newAlertCondition}
                onChange={e => setNewAlertCondition(e.target.value)}
                style={{ padding: '7px 12px', borderRadius: 8, border: '1px solid var(--surface-4)', background: 'var(--surface-1)', color: 'var(--text-1)', fontSize: 12 }}
              >
                {(alertSupportedMetrics?.conditions || ['trend_down','trend_up','anomaly','threshold_above','threshold_below']).map(c => (
                  <option key={c} value={c}>{c.replace(/_/g, ' ')}</option>
                ))}
              </select>
              <select
                value={newAlertSeverity}
                onChange={e => setNewAlertSeverity(e.target.value)}
                style={{ padding: '7px 12px', borderRadius: 8, border: '1px solid var(--surface-4)', background: 'var(--surface-1)', color: 'var(--text-1)', fontSize: 12 }}
              >
                {['info','warning','critical'].map(s => <option key={s} value={s}>{s}</option>)}
              </select>
              <button
                onClick={async () => {
                  if (!newAlertName.trim()) return
                  try {
                    await biSmartAlertsApi.createRule({ name: newAlertName, metric_key: newAlertMetric, condition: newAlertCondition, severity: newAlertSeverity })
                    setNewAlertName('')
                    setAlertsTick(x => x + 1)
                  } catch (_e) { /* ignore */ }
                }}
                style={{ padding: '7px 16px', borderRadius: 8, background: COLOR.accent, color: '#fff', border: 'none', cursor: 'pointer', fontSize: 12, fontWeight: 600 }}
              >+ Crear</button>
            </div>
            {(alertRules?.items || []).map(rule => (
              <div key={rule.id} style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '8px 0', borderBottom: '1px solid var(--surface-4)' }}>
                <div style={{ width: 8, height: 8, borderRadius: '50%', background: rule.severity === 'critical' ? COLOR.danger : rule.severity === 'warning' ? COLOR.warning : COLOR.success, flexShrink: 0 }} />
                <div style={{ flex: 1 }}>
                  <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-1)' }}>{rule.name}</div>
                  <div style={{ fontSize: 10, color: 'var(--text-3)' }}>{rule.metric_key} · {rule.condition.replace(/_/g, ' ')}</div>
                </div>
                <span style={{ fontSize: 10, padding: '2px 8px', borderRadius: 10, background: rule.enabled ? '#22c55e18' : 'var(--surface-4)', color: rule.enabled ? '#22c55e' : 'var(--text-3)', fontWeight: 700 }}>
                  {rule.enabled ? 'activa' : 'pausada'}
                </span>
                <button
                  onClick={async () => {
                    try { await biSmartAlertsApi.deleteRule(rule.id); setAlertsTick(x => x + 1) } catch (_e) { /* ignore */ }
                  }}
                  style={{ padding: '3px 10px', borderRadius: 6, border: '1px solid var(--surface-4)', background: 'transparent', color: 'var(--text-3)', cursor: 'pointer', fontSize: 11 }}
                >✕</button>
              </div>
            ))}
            {!(alertRules?.items || []).length && (
              <div style={{ textAlign: 'center', color: 'var(--text-3)', fontSize: 12, padding: '16px 0' }}>
                Sin reglas.{' '}
                <button
                  onClick={async () => { try { await biSmartAlertsApi.seedDefaults(); setAlertsTick(x => x + 1) } catch (_e) { /* ignore */ } }}
                  style={{ background: 'none', border: 'none', color: COLOR.accent, cursor: 'pointer', fontSize: 12, fontWeight: 600 }}
                >Cargar reglas por defecto</button>
              </div>
            )}
          </div>
        </div>

        <div style={S.card}>
          <div style={{ ...S.cardPad, borderBottom: '1px solid var(--surface-4)' }}>
            <span style={{ fontWeight: 700, fontSize: '1rem' }}>Historial de alertas</span>
          </div>
          <div style={{ ...S.cardPad, maxHeight: 320, overflowY: 'auto' }}>
            {(alertHistory?.items || []).length === 0 && (
              <div style={{ textAlign: 'center', color: 'var(--text-3)', fontSize: 12, padding: '16px 0' }}>Sin alertas disparadas</div>
            )}
            {[...(alertHistory?.items || [])].reverse().map(entry => (
              <div key={entry.id} style={{ padding: '10px 0', borderBottom: '1px solid var(--surface-4)', display: 'flex', gap: 10, alignItems: 'flex-start' }}>
                <div style={{ width: 8, height: 8, borderRadius: '50%', marginTop: 4, background: entry.severity === 'critical' ? COLOR.danger : entry.severity === 'warning' ? COLOR.warning : COLOR.success, flexShrink: 0 }} />
                <div style={{ flex: 1 }}>
                  <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-1)' }}>{entry.rule_name}</div>
                  <div style={{ fontSize: 10, color: 'var(--text-3)' }}>{entry.metric_key} · {(entry.condition || '').replace(/_/g, ' ')} · {new Date(entry.triggered_at).toLocaleDateString('es-ES')}</div>
                  {entry.correlated?.length > 0 && (
                    <div style={{ fontSize: 10, color: COLOR.warning, marginTop: 2 }}>↔ Correlada con: {entry.correlated.map(c => c.metric_key).join(', ')}</div>
                  )}
                </div>
                {!entry.acknowledged ? (
                  <button
                    onClick={async () => {
                      try { await biSmartAlertsApi.acknowledge(entry.id); setAlertsTick(x => x + 1) } catch (_e) { /* ignore */ }
                    }}
                    style={{ padding: '3px 10px', borderRadius: 6, border: `1px solid ${COLOR.accent}`, background: 'transparent', color: COLOR.accent, cursor: 'pointer', fontSize: 10, fontWeight: 600, flexShrink: 0 }}
                  >ACK</button>
                ) : (
                  <span style={{ fontSize: 10, color: '#22c55e', fontWeight: 600, flexShrink: 0 }}>✓</span>
                )}
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* ── BI Governance: Audit trail, Data Lineage, Field Sensitivity ── */}
      <div style={{ marginBottom: 20 }}>
        <div style={{ marginBottom: 10, fontWeight: 700, fontSize: '0.85rem', color: 'var(--text-3)', textTransform: 'uppercase', letterSpacing: '0.09em' }}>
          Gobernanza BI — Auditoría, Linaje y Clasificación de Campos
        </div>
        <div style={{ display: 'grid', gridTemplateColumns: isMobile ? '1fr' : 'repeat(3, 1fr)', gap: 14 }}>

          {/* Audit access trail */}
          <div style={S.card}>
            <div style={{ ...S.cardPad, borderBottom: '1px solid var(--surface-4)', display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: 6 }}>
              <span style={{ fontWeight: 700, fontSize: '0.95rem' }}>Auditoría de accesos</span>
              <div style={{ display: 'flex', gap: 6, alignItems: 'center', flexWrap: 'wrap' }}>
                <input
                  value={govAuditUserFilter}
                  onChange={e => setGovAuditUserFilter(e.target.value)}
                  placeholder="user_id (filtro)"
                  style={{ padding: '5px 10px', borderRadius: 8, border: '1px solid var(--surface-4)', background: 'var(--surface-1)', color: 'var(--text-1)', fontSize: 11, width: 130 }}
                />
                <button
                  type="button"
                  onClick={() => setGovAuditTick(x => x + 1)}
                  style={{ padding: '5px 10px', borderRadius: 8, border: '1px solid var(--surface-4)', background: 'transparent', color: 'var(--text-2)', cursor: 'pointer', fontSize: 11 }}
                >Filtrar</button>
              </div>
            </div>
            <div style={{ ...S.cardPad, display: 'grid', gap: 8 }}>
              <button
                type="button"
                onClick={handleLogGovAuditEvent}
                style={{ justifySelf: 'flex-start', padding: '6px 14px', borderRadius: 8, border: `1px solid ${COLOR.accent}`, background: COLOR.accentMuted, color: COLOR.accent, cursor: 'pointer', fontSize: 11, fontWeight: 700 }}
              >Registrar acceso</button>
              {(govAuditData?.items || []).length === 0 ? (
                <div style={{ fontSize: 12, color: 'var(--text-3)', padding: '8px 0' }}>Sin eventos de auditoria.</div>
              ) : (
                <div style={{ maxHeight: 200, overflowY: 'auto', display: 'grid', gap: 4 }}>
                  {(govAuditData?.items || []).slice(0, 20).map((ev, i) => (
                    <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '5px 0', borderBottom: '1px solid var(--surface-4)' }}>
                      <span style={{ fontSize: 10, background: `${COLOR.info}18`, color: COLOR.info, borderRadius: 6, padding: '2px 7px', fontWeight: 700, flexShrink: 0 }}>{ev.action || 'view'}</span>
                      <div style={{ flex: 1, minWidth: 0 }}>
                        <div style={{ fontSize: 11, color: 'var(--text-1)', fontWeight: 600, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{ev.resource || '—'}</div>
                        <div style={{ fontSize: 10, color: 'var(--text-3)' }}>{ev.user_id || '—'} · {ev.accessed_at ? new Date(ev.accessed_at).toLocaleString() : '—'}</div>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>

          {/* Data Lineage */}
          <div style={S.card}>
            <div style={{ ...S.cardPad, borderBottom: '1px solid var(--surface-4)', display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: 6 }}>
              <span style={{ fontWeight: 700, fontSize: '0.95rem' }}>Linaje de datos</span>
              <button
                type="button"
                onClick={() => refetchGovLineage()}
                style={{ padding: '5px 10px', borderRadius: 8, border: '1px solid var(--surface-4)', background: 'transparent', color: 'var(--text-2)', cursor: 'pointer', fontSize: 11 }}
              >Refrescar</button>
            </div>
            <div style={{ ...S.cardPad, display: 'grid', gap: 8 }}>
              <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
                <input
                  value={newLineageSource}
                  onChange={e => setNewLineageSource(e.target.value)}
                  placeholder="Tabla origen"
                  style={{ flex: 1, minWidth: 80, padding: '6px 10px', borderRadius: 8, border: '1px solid var(--surface-4)', background: 'var(--surface-1)', color: 'var(--text-1)', fontSize: 11 }}
                />
                <span style={{ alignSelf: 'center', color: 'var(--text-3)', fontSize: 13 }}>{'→'}</span>
                <input
                  value={newLineageTarget}
                  onChange={e => setNewLineageTarget(e.target.value)}
                  placeholder="Tabla destino"
                  style={{ flex: 1, minWidth: 80, padding: '6px 10px', borderRadius: 8, border: '1px solid var(--surface-4)', background: 'var(--surface-1)', color: 'var(--text-1)', fontSize: 11 }}
                />
                <button
                  type="button"
                  onClick={handleAddLineageEdge}
                  style={{ padding: '6px 14px', borderRadius: 8, border: `1px solid ${COLOR.accent}`, background: COLOR.accentMuted, color: COLOR.accent, cursor: 'pointer', fontSize: 11, fontWeight: 700 }}
                >Añadir</button>
              </div>
              {(govLineageData?.items || []).length === 0 ? (
                <div style={{ fontSize: 12, color: 'var(--text-3)', padding: '8px 0' }}>Sin edges de linaje registrados.</div>
              ) : (
                <div style={{ maxHeight: 200, overflowY: 'auto', display: 'grid', gap: 4 }}>
                  {(govLineageData?.items || []).slice(0, 20).map((edge, i) => (
                    <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 6, padding: '5px 0', borderBottom: '1px solid var(--surface-4)' }}>
                      <span style={{ fontSize: 11, color: 'var(--text-2)', fontWeight: 600, flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                        {edge.source_table || edge.source || '—'}
                      </span>
                      <span style={{ color: 'var(--text-3)', fontSize: 12, flexShrink: 0 }}>{'→'}</span>
                      <span style={{ fontSize: 11, color: 'var(--text-1)', fontWeight: 600, flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                        {edge.target_table || edge.target || '—'}
                      </span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>

          {/* Field Sensitivity */}
          <div style={S.card}>
            <div style={{ ...S.cardPad, borderBottom: '1px solid var(--surface-4)', display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: 6 }}>
              <span style={{ fontWeight: 700, fontSize: '0.95rem' }}>Clasificacion de campos</span>
              <button
                type="button"
                onClick={() => refetchGovFields()}
                style={{ padding: '5px 10px', borderRadius: 8, border: '1px solid var(--surface-4)', background: 'transparent', color: 'var(--text-2)', cursor: 'pointer', fontSize: 11 }}
              >Refrescar</button>
            </div>
            <div style={{ ...S.cardPad, display: 'grid', gap: 8 }}>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 6 }}>
                <input
                  value={newFieldDataset}
                  onChange={e => setNewFieldDataset(e.target.value)}
                  placeholder="Dataset ID"
                  style={{ padding: '6px 10px', borderRadius: 8, border: '1px solid var(--surface-4)', background: 'var(--surface-1)', color: 'var(--text-1)', fontSize: 11 }}
                />
                <input
                  value={newFieldName}
                  onChange={e => setNewFieldName(e.target.value)}
                  placeholder="Campo (ej. email)"
                  style={{ padding: '6px 10px', borderRadius: 8, border: '1px solid var(--surface-4)', background: 'var(--surface-1)', color: 'var(--text-1)', fontSize: 11 }}
                />
                <select
                  value={newFieldSensitivity}
                  onChange={e => setNewFieldSensitivity(e.target.value)}
                  style={{ padding: '6px 10px', borderRadius: 8, border: '1px solid var(--surface-4)', background: 'var(--surface-1)', color: 'var(--text-1)', fontSize: 11 }}
                >
                  {['low', 'medium', 'high', 'critical', 'pii'].map(s => (
                    <option key={s} value={s}>{s}</option>
                  ))}
                </select>
                <button
                  type="button"
                  onClick={handleUpsertFieldSensitivity}
                  style={{ padding: '6px 14px', borderRadius: 8, border: `1px solid ${COLOR.warning}`, background: `${COLOR.warning}18`, color: COLOR.warning, cursor: 'pointer', fontSize: 11, fontWeight: 700 }}
                >Clasificar</button>
              </div>
              {(govFieldData?.items || []).length === 0 ? (
                <div style={{ fontSize: 12, color: 'var(--text-3)', padding: '8px 0' }}>Sin campos clasificados.</div>
              ) : (
                <div style={{ maxHeight: 200, overflowY: 'auto', display: 'grid', gap: 4 }}>
                  {(govFieldData?.items || []).slice(0, 20).map((f, i) => {
                    const sensColor = f.sensitivity === 'critical' || f.sensitivity === 'pii' ? COLOR.danger : f.sensitivity === 'high' ? COLOR.warning : COLOR.success
                    return (
                      <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '5px 0', borderBottom: '1px solid var(--surface-4)' }}>
                        <span style={{ fontSize: 10, background: `${sensColor}18`, color: sensColor, borderRadius: 6, padding: '2px 7px', fontWeight: 700, flexShrink: 0, textTransform: 'uppercase' }}>{f.sensitivity || '—'}</span>
                        <div style={{ flex: 1, minWidth: 0 }}>
                          <div style={{ fontSize: 11, color: 'var(--text-1)', fontWeight: 600, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{f.field_name || '—'}</div>
                          <div style={{ fontSize: 10, color: 'var(--text-3)' }}>{f.dataset_id || '—'}</div>
                        </div>
                      </div>
                    )
                  })}
                </div>
              )}
            </div>
          </div>

        </div>
      </div>

      {/* ── BI Phase 4-D: Dashboard Bookmarks ── */}
      <div style={{ ...S.card, marginBottom: 20 }}>
        <div style={{ ...S.cardPad, borderBottom: '1px solid var(--surface-4)', display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: 8 }}>
          <span style={{ fontWeight: 700, fontSize: '1rem' }}>Bookmarks de dashboard</span>
          <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
            <input
              value={newBookmarkName}
              onChange={e => setNewBookmarkName(e.target.value)}
              placeholder="Nombre del bookmark"
              style={{ padding: '7px 12px', borderRadius: 8, border: '1px solid var(--surface-4)', background: 'var(--surface-1)', color: 'var(--text-1)', fontSize: 12, width: 200 }}
            />
            <button
              onClick={async () => {
                if (!newBookmarkName.trim()) return
                try {
                  await biBookmarksApi.create({ name: newBookmarkName, period_days: days, active_tab: 'executive', shared: false })
                  setNewBookmarkName('')
                  setBookmarksTick(x => x + 1)
                } catch (_e) { /* ignore */ }
              }}
              style={{ padding: '7px 16px', borderRadius: 8, background: COLOR.accent, color: '#fff', border: 'none', cursor: 'pointer', fontSize: 12, fontWeight: 600 }}
            >Guardar vista actual</button>
          </div>
        </div>
        <div style={{ ...S.cardPad }}>
          {!(bookmarks?.items || []).length ? (
            <div style={{ textAlign: 'center', color: 'var(--text-3)', fontSize: 12, padding: '16px 0' }}>Sin bookmarks guardados</div>
          ) : (
            <div style={{ display: 'grid', gridTemplateColumns: isMobile ? '1fr' : 'repeat(auto-fill, minmax(240px, 1fr))', gap: 10 }}>
              {(bookmarks?.items || []).map(bm => (
                <div key={bm.id} style={{ ...S.card, padding: '12px 16px', display: 'flex', flexDirection: 'column', gap: 6 }}>
                  <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                    <span style={{ fontSize: 13, fontWeight: 700, color: 'var(--text-1)' }}>🔖 {bm.name}</span>
                    <button
                      onClick={async () => {
                        try { await biBookmarksApi.delete(bm.id); setBookmarksTick(x => x + 1) } catch (_e) { /* ignore */ }
                      }}
                      style={{ background: 'none', border: 'none', color: 'var(--text-3)', cursor: 'pointer', fontSize: 12 }}
                    >✕</button>
                  </div>
                  <div style={{ fontSize: 11, color: 'var(--text-3)' }}>Período: {bm.period_days}d · Tab: {bm.active_tab || 'executive'}</div>
                  {bm.description && <div style={{ fontSize: 11, color: 'var(--text-2)' }}>{bm.description}</div>}
                  <div style={{ display: 'flex', gap: 6 }}>
                    <button
                      onClick={() => setDays(bm.period_days || 30)}
                      style={{ flex: 1, padding: '5px 0', borderRadius: 6, border: `1px solid ${COLOR.accent}`, background: `${COLOR.accent}10`, color: COLOR.accent, cursor: 'pointer', fontSize: 11, fontWeight: 600 }}
                    >Cargar vista</button>
                    {bm.shared && <span style={{ fontSize: 10, padding: '3px 8px', borderRadius: 10, background: '#22c55e18', color: '#22c55e', fontWeight: 700, alignSelf: 'center' }}>Compartido</span>}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

    </div>
  )
}
