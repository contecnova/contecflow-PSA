import { useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import {
  AreaChart, Area, BarChart, Bar, Line,
  XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
  PieChart, Pie, Cell,
} from 'recharts'
import api, { dashboardApi } from '../../services/api'
import { Spinner, EmptyState } from '../../components/ui'

const BLUE = 'var(--accent)'
const GREEN = 'var(--success)'
const AMBER = 'var(--warning)'
const RED = 'var(--danger)'
const PURPLE = 'var(--purple)'
const PALETTE = [BLUE, GREEN, AMBER, PURPLE, RED, 'var(--sky-blue)', 'var(--chart-teal)']

const fmtCur = (v) => v != null
  ? new Intl.NumberFormat('es-ES', { style: 'currency', currency: 'EUR', maximumFractionDigits: 0 }).format(v)
  : '—'
const fmtPct = (v) => v != null ? `${v.toFixed(1)}%` : '—'

const buildFilterParams = (filters = {}) => ({
  date_from: filters.dateFrom || undefined,
  date_to: filters.dateTo || undefined,
  project_id: filters.projectId || undefined,
  project_type: filters.projectType || undefined,
  client_id: filters.clientId || undefined,
  user_id: filters.userId || undefined,
  department: filters.department || undefined,
})

function CustomTooltip({ active, payload, label, fmt = v => v }) {
  if (!active || !payload?.length) return null
  return (
    <div style={{ background: 'var(--surface-2)', border: '1px solid var(--surface-4)', borderRadius: 8, padding: '10px 14px', fontSize: 12, boxShadow: '0 8px 24px rgba(0,0,0,0.5)' }}>
      {label && <div style={{ fontWeight: 600, marginBottom: 6, color: 'var(--text-1)' }}>{label}</div>}
      {payload.map((p, i) => (
        <div key={i} style={{ display: 'flex', gap: 8, alignItems: 'center', marginBottom: 2 }}>
          <div style={{ width: 8, height: 8, borderRadius: '50%', background: p.color, flexShrink: 0 }} />
          <span style={{ color: 'var(--text-2)' }}>{p.name}:</span>
          <span style={{ color: 'var(--text-1)', fontWeight: 600 }}>{fmt(p.value)}</span>
        </div>
      ))}
    </div>
  )
}

function KpiGridWidget({ filters }) {
  const filterParams = useMemo(() => buildFilterParams(filters), [filters])

  const { data: kpis } = useQuery({
    queryKey: ['bi-kpis', filterParams],
    queryFn: () => dashboardApi.kpis(filterParams).then(r => r.data).catch(() => ({})),
  })
  const { data: health = [] } = useQuery({
    queryKey: ['bi-health', filterParams],
    queryFn: () => api.get('/dashboard/projects-health', { params: filterParams }).then(r => r.data).catch(() => []),
  })
  const { data: hoursMonth = [] } = useQuery({
    queryKey: ['bi-hours-month-delta', filterParams],
    queryFn: () => api.get('/analytics/query/hours_by_month', { params: filterParams }).then(r => r.data?.rows || []).catch(() => []),
  })

  const critProj = health.filter(p => p.budget_used_pct > 100 || p.schedule_deviation_days > 0).length
  const onTrackPct = health.length > 0 ? Math.round(((health.length - critProj) / health.length) * 100) : 0
  const last = hoursMonth[hoursMonth.length - 1]?.value || 0
  const prev = hoursMonth[hoursMonth.length - 2]?.value || 0
  const deltaHours = prev > 0 ? ((last - prev) / prev) * 100 : 0

  const items = [
    { icon: '⬡', label: 'Proyectos activos', value: health.length, color: BLUE, sub: `${onTrackPct}% en tiempo` },
    { icon: '▦', label: 'Tareas vencidas', value: kpis?.tasks_overdue ?? 0, color: (kpis?.tasks_overdue ?? 0) > 0 ? RED : GREEN, sub: 'requieren atención' },
    { icon: '💰', label: 'Presupuesto usado', value: kpis?.total_budget > 0 ? `${Math.round((kpis.total_spent / kpis.total_budget) * 100)}%` : '—', color: AMBER, sub: `${fmtCur(kpis?.total_spent ?? 0)} gastado` },
    { icon: '🎫', label: 'Tickets abiertos', value: kpis?.tasks_open ?? 0, color: PURPLE, sub: 'service desk' },
    { icon: '⏱', label: 'Horas esta semana', value: kpis?.hours_logged_this_week?.toFixed(0) ?? '0', color: 'var(--sky-blue)', sub: `${deltaHours >= 0 ? '▲' : '▼'} ${Math.abs(deltaHours).toFixed(1)}% vs periodo anterior` },
    { icon: '🚨', label: 'Proyectos críticos', value: critProj, color: critProj > 0 ? RED : GREEN, sub: 'fuera de tiempo/budget' },
  ]

  return (
    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3,1fr)', gap: 10 }}>
      {items.map(k => (
        <div key={k.label} style={{ background: 'var(--surface-3)', borderRadius: 10, padding: '12px 14px', border: `1px solid ${k.color}20` }}>
          <div style={{ fontSize: 20, marginBottom: 6 }}>{k.icon}</div>
          <div style={{ fontSize: 22, fontWeight: 800, color: k.color, fontFamily: 'var(--font-mono)', lineHeight: 1 }}>{k.value}</div>
          <div style={{ fontSize: 11, fontWeight: 600, color: 'var(--text-1)', marginTop: 3 }}>{k.label}</div>
          <div style={{ fontSize: 10, color: 'var(--text-3)', marginTop: 1 }}>{k.sub}</div>
        </div>
      ))}
    </div>
  )
}

function HealthWidget({ filters }) {
  const params = buildFilterParams(filters)
  const { data: health = [], isLoading } = useQuery({
    queryKey: ['bi-health', params],
    queryFn: () => api.get('/dashboard/projects-health', { params }).then(r => r.data).catch(() => []),
  })

  const getColor = p => p.schedule_deviation_days > 0 || p.budget_used_pct > 100 ? RED : p.budget_used_pct > 80 || p.alerts_count > 0 ? AMBER : GREEN
  const getIcon = p => p.schedule_deviation_days > 0 || p.budget_used_pct > 100 ? '🔴' : p.budget_used_pct > 80 || p.alerts_count > 0 ? '🟡' : '🟢'
  const counts = {
    ok: health.filter(p => getColor(p) === GREEN).length,
    warn: health.filter(p => getColor(p) === AMBER).length,
    crit: health.filter(p => getColor(p) === RED).length,
  }
  const pieData = [
    { name: 'OK', value: counts.ok, fill: GREEN },
    { name: 'Riesgo', value: counts.warn, fill: AMBER },
    { name: 'Crítico', value: counts.crit, fill: RED },
  ].filter(d => d.value > 0)

  if (isLoading) return <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100%' }}><Spinner /></div>

  return (
    <div style={{ display: 'flex', gap: 16, height: '100%' }}>
      <div style={{ width: 120, flexShrink: 0 }}>
        <ResponsiveContainer width="100%" height={120}>
          <PieChart>
            <Pie data={pieData} cx="50%" cy="50%" innerRadius={30} outerRadius={50} paddingAngle={3} dataKey="value">
              {pieData.map((d, i) => <Cell key={i} fill={d.fill} />)}
            </Pie>
            <Tooltip formatter={(v, n) => [v, n]} />
          </PieChart>
        </ResponsiveContainer>
      </div>
      <div style={{ flex: 1, overflow: 'auto', display: 'flex', flexDirection: 'column', gap: 5 }}>
        {health.sort((a, b) => {
          const r = p => p.schedule_deviation_days > 0 || p.budget_used_pct > 100 ? 0 : p.budget_used_pct > 80 || p.alerts_count > 0 ? 1 : 2
          return r(a) - r(b)
        }).slice(0, 8).map(p => (
          <div key={p.project_id} style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '5px 8px', background: 'var(--surface-3)', borderRadius: 7, border: `1px solid ${getColor(p)}20` }}>
            <span style={{ fontSize: 11 }}>{getIcon(p)}</span>
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{ fontSize: 12, fontWeight: 600, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                {p.project_code} — {p.project_name}
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}

function ProjectsByTypeWidget({ filters, onFilterType }) {
  const params = buildFilterParams(filters)
  const { data = [], isLoading } = useQuery({
    queryKey: ['bi-projects-by-type', params],
    queryFn: () => api.get('/analytics/query/projects_by_type', { params }).then(r => r.data?.rows || []).catch(() => []),
  })
  if (isLoading) return <Spinner />
  if (!data.length) return <EmptyState icon="🧩" title="Sin datos por tipo" />
  return (
    <ResponsiveContainer width="100%" height="100%">
      <PieChart>
        <Pie data={data} dataKey="value" nameKey="label" innerRadius={35} outerRadius={70} paddingAngle={2} onClick={(entry) => onFilterType?.(entry?.type)}>
          {data.map((d, i) => <Cell key={d.label} fill={PALETTE[i % PALETTE.length]} cursor="pointer" />)}
        </Pie>
        <Tooltip />
      </PieChart>
    </ResponsiveContainer>
  )
}

function RevenueVsCostWidget({ filters }) {
  const [period, setPeriod] = useState('ytd')
  const queryParams = { ...buildFilterParams(filters), period }
  const { data: revenueData, isLoading } = useQuery({
    queryKey: ['bi-revenue', queryParams],
    queryFn: () => api.get('/profitability/summary', { params: queryParams }).then(r => r.data).catch(() => null),
  })

  const chartData = (revenueData?.monthly || []).map(m => ({
    mes: m.month ? new Date(2024, (m.month || 1) - 1, 1).toLocaleDateString('es-ES', { month: 'short' }) : '',
    Ingresos: m.revenue_actual || 0,
    Costes: m.cost_actual || 0,
    Margen: (m.revenue_actual || 0) - (m.cost_actual || 0),
  }))

  if (isLoading) return <Spinner />
  if (!chartData.length) return <EmptyState icon="📊" title="Sin datos de ingresos" />

  return (
    <div style={{ height: '100%', display: 'flex', flexDirection: 'column', gap: 8 }}>
      <div style={{ display: 'flex', gap: 4, justifyContent: 'flex-end' }}>
        {[['ytd', 'YTD'], ['q', 'Trimestre'], ['m', 'Mes']].map(([p, l]) => (
          <button key={p} onClick={() => setPeriod(p)} style={{ padding: '3px 10px', border: 'none', borderRadius: 5, cursor: 'pointer', background: period === p ? 'var(--accent)' : 'var(--surface-3)', color: period === p ? '#fff' : 'var(--text-2)', fontSize: 11, fontFamily: 'inherit' }}>
            {l}
          </button>
        ))}
      </div>
      <div style={{ flex: 1, minHeight: 0 }}>
        <ResponsiveContainer width="100%" height="100%">
          <AreaChart data={chartData} margin={{ top: 4, right: 0, left: -20, bottom: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="var(--surface-4)" />
            <XAxis dataKey="mes" tick={{ fontSize: 10, fill: 'var(--text-3)' }} />
            <YAxis tick={{ fontSize: 10, fill: 'var(--text-3)' }} tickFormatter={v => `${(v / 1000).toFixed(0)}k`} />
            <Tooltip content={<CustomTooltip fmt={fmtCur} />} />
            <Area type="monotone" dataKey="Ingresos" stroke={BLUE} fillOpacity={0.25} fill={BLUE} strokeWidth={2} />
            <Area type="monotone" dataKey="Costes" stroke={RED} fillOpacity={0.2} fill={RED} strokeWidth={2} />
            <Line type="monotone" dataKey="Margen" stroke={GREEN} strokeWidth={2} dot={false} strokeDasharray="5 3" />
          </AreaChart>
        </ResponsiveContainer>
      </div>
    </div>
  )
}

function ProfitByProjectWidget({ onDrill, onFilterProject, filters }) {
  const params = buildFilterParams(filters)
  const { data: raw, isLoading } = useQuery({
    queryKey: ['bi-profit', params],
    queryFn: () => api.get('/profitability/summary', { params }).then(r => {
      const projects = r.data?.projects || r.data || []
      return projects.slice(0, 10).map(p => ({
        name: (p.project_code || p.code || '?') + ' ' + ((p.project_name || p.name || '').slice(0, 18)),
        fullName: p.project_name || p.name || '',
        id: p.project_id || p.id,
        margen: p.margin_pct || 0,
        ingresos: p.billing_revenue || p.revenue || 0,
        costes: p.total_cost || p.cost || 0,
        riesgo: (p.margin_pct || 0) < 0 ? 'critical' : (p.margin_pct || 0) < 15 ? 'warning' : 'ok',
      })).sort((a, b) => a.margen - b.margen)
    }).catch(() => []),
  })
  if (isLoading) return <Spinner />
  if (!raw?.length) return <EmptyState icon="💰" title="Sin datos de rentabilidad" />

  return (
    <ResponsiveContainer width="100%" height="100%">
      <BarChart data={raw} layout="vertical" margin={{ top: 0, right: 40, left: 0, bottom: 0 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="var(--surface-4)" horizontal={false} />
        <XAxis type="number" tick={{ fontSize: 10, fill: 'var(--text-3)' }} tickFormatter={v => `${v}%`} />
        <YAxis type="category" dataKey="name" tick={{ fontSize: 10, fill: 'var(--text-3)' }} width={130} />
        <Tooltip content={<CustomTooltip fmt={fmtPct} />} />
        <Bar dataKey="margen" radius={[0, 4, 4, 0]} onClick={(entry) => { onDrill?.(entry); onFilterProject?.(filters?.projectId === entry?.id ? '' : entry?.id) }} cursor="pointer">
          {(raw || []).map((p, i) => (
            <Cell key={i} fill={filters?.projectId && filters.projectId === p.id ? 'var(--accent)' : (p.margen >= 20 ? GREEN : p.margen >= 0 ? AMBER : RED)} />
          ))}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  )
}

function UtilizationWidget({ filters }) {
  const params = { ...buildFilterParams(filters), weeks_ahead: 4 }
  const { data = [] } = useQuery({
    queryKey: ['bi-utilization-advanced', params],
    queryFn: () => api.get('/analytics/utilization/advanced', { params }).then(r => {
      const items = r.data?.team || []
      return Array.isArray(items) ? items.slice(0, 8).map(u => ({
        name: (u.full_name || u.name || '').split(' ')[0],
        util: Math.min(130, Math.round(u.actual_utilization_pct || 0)),
      })) : []
    }).catch(() => []),
  })
  if (!data.length) return <EmptyState icon="👥" title="Sin datos de utilización" />
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 8, height: '100%', overflow: 'auto' }}>
      {data.map((u, i) => (
        <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <div style={{ width: 80, fontSize: 12, color: 'var(--text-2)', flexShrink: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{u.name}</div>
          <div style={{ flex: 1, height: 6, background: 'var(--surface-4)', borderRadius: 3, overflow: 'hidden' }}>
            <div style={{ width: `${Math.min(100, u.util)}%`, height: '100%', borderRadius: 3, background: u.util > 90 ? RED : u.util > 75 ? AMBER : GREEN, transition: 'width .3s' }} />
          </div>
          <div style={{ fontSize: 11, fontWeight: 700, width: 48, textAlign: 'right', flexShrink: 0, color: u.util > 90 ? RED : u.util > 75 ? AMBER : GREEN, fontFamily: 'var(--font-mono)' }}>
            {u.util}%
          </div>
        </div>
      ))}
    </div>
  )
}

function TopClientsWidget({ filters, onFilterClient }) {
  const params = buildFilterParams(filters)
  const { data = [], isLoading } = useQuery({
    queryKey: ['bi-top-clients', params],
    queryFn: () => api.get('/profitability/summary', { params }).then(r => {
      const projects = r.data?.projects || r.data || []
      const byClient = {}
      projects.forEach(p => {
        const cl = p.client_name || 'Sin cliente'
        const cid = p.client_id || cl
        if (!byClient[cid]) byClient[cid] = { name: cl, id: cid, revenue: 0, margin: [], projects: 0 }
        byClient[cid].revenue += p.billing_revenue || 0
        byClient[cid].margin.push(p.margin_pct || 0)
        byClient[cid].projects++
      })
      return Object.values(byClient)
        .map(d => ({ ...d, avg_margin: Math.round(d.margin.reduce((a, b) => a + b, 0) / d.margin.length) }))
        .sort((a, b) => b.revenue - a.revenue)
        .slice(0, 8)
    }).catch(() => []),
  })
  if (isLoading) return <Spinner />
  if (!data.length) return <EmptyState icon="🏢" title="Sin datos de clientes" />

  const maxRev = Math.max(...data.map(d => d.revenue))
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 7, height: '100%', overflow: 'auto' }}>
      {data.map((c, i) => (
        <div key={i} onClick={() => onFilterClient?.(filters?.clientId === c.id ? '' : c.id)} style={{ display: 'flex', alignItems: 'center', gap: 10, cursor: onFilterClient ? 'pointer' : 'default', borderRadius: 6, padding: '2px 4px', background: filters?.clientId === c.id ? 'var(--accent-muted)' : 'transparent', outline: filters?.clientId === c.id ? '1px solid var(--accent-glow)' : 'none' }}>
          <div style={{ width: 20, fontSize: 10, color: 'var(--text-3)', textAlign: 'right', flexShrink: 0 }}>{i + 1}</div>
          <div style={{ flex: 1, minWidth: 0 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 3, fontSize: 12 }}>
              <span style={{ color: 'var(--text-1)', fontWeight: 500, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', maxWidth: 130 }}>{c.name}</span>
              <span style={{ color: 'var(--text-2)', fontFamily: 'var(--font-mono)', flexShrink: 0, marginLeft: 4 }}>{fmtCur(c.revenue)}</span>
            </div>
            <div style={{ height: 4, background: 'var(--surface-4)', borderRadius: 2, overflow: 'hidden' }}>
              <div style={{ height: '100%', borderRadius: 2, width: `${(c.revenue / maxRev) * 100}%`, background: PALETTE[i % PALETTE.length] }} />
            </div>
          </div>
        </div>
      ))}
    </div>
  )
}

function PipelineWidget() {
  const { data: pipeline = [] } = useQuery({
    queryKey: ['bi-pipeline'],
    queryFn: () => api.get('/pipeline', { params: { page_size: 100 } }).then(r => Array.isArray(r.data) ? r.data : (r.data?.items || [])).catch(() => []),
  })

  const STAGES = ['lead', 'qualified', 'proposal', 'negotiation', 'won', 'lost']
  const STAGE_LABELS = { lead: 'Lead', qualified: 'Calificado', proposal: 'Propuesta', negotiation: 'Negociación', won: 'Ganado', lost: 'Perdido' }
  const byStage = STAGES.map(s => ({
    name: STAGE_LABELS[s] || s,
    deals: pipeline.filter(o => o.stage === s).length,
    revenue: pipeline.filter(o => o.stage === s).reduce((acc, o) => acc + (o.expected_revenue || 0), 0),
  })).filter(s => s.deals > 0)

  return (
    <ResponsiveContainer width="100%" height="100%">
      <BarChart data={byStage} margin={{ top: 0, right: 10, left: -20, bottom: 0 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="var(--surface-4)" />
        <XAxis dataKey="name" tick={{ fontSize: 10, fill: 'var(--text-3)' }} />
        <YAxis tick={{ fontSize: 10, fill: 'var(--text-3)' }} />
        <Tooltip formatter={(v, n) => n === 'revenue' ? [fmtCur(v), 'Revenue'] : [v, 'Deals']} contentStyle={{ background: 'var(--surface-2)', border: '1px solid var(--surface-4)', borderRadius: 8 }} />
        <Bar dataKey="deals" fill={AMBER} radius={[4, 4, 0, 0]} name="Deals" />
      </BarChart>
    </ResponsiveContainer>
  )
}

function HoursWidget({ filters }) {
  const params = { weeks: 10, project_id: filters?.projectId || undefined }
  const { data: hoursData = [] } = useQuery({
    queryKey: ['bi-hours', params],
    queryFn: () => api.get('/analytics/hours_by_week', { params }).then(r => r.data?.data || []).catch(() => []),
  })

  return (
    <ResponsiveContainer width="100%" height="100%">
      <AreaChart data={Array.isArray(hoursData) ? hoursData.slice(-10) : []} margin={{ top: 4, right: 0, left: -20, bottom: 0 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="var(--surface-4)" />
        <XAxis dataKey="week" tick={{ fontSize: 10, fill: 'var(--text-3)' }} />
        <YAxis tick={{ fontSize: 10, fill: 'var(--text-3)' }} />
        <Tooltip formatter={v => [`${v}h`, 'Horas']} />
        <Area type="monotone" dataKey="hours" stroke={BLUE} fill={BLUE} fillOpacity={0.25} strokeWidth={2} />
      </AreaChart>
    </ResponsiveContainer>
  )
}

function TopProjectsMarginWidget({ filters, onFilterProject }) {
  const params = buildFilterParams(filters)
  const { data: raw = [] } = useQuery({
    queryKey: ['bi-top-margin', params],
    queryFn: () => api.get('/profitability/projects', { params }).then(r => r.data).catch(() => []),
  })

  const top = [...raw].sort((a, b) => (b.margin_pct || 0) - (a.margin_pct || 0)).slice(0, 6)
  if (!top.length) return <EmptyState icon="💰" title="Sin datos" />

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 6, height: '100%', overflow: 'auto' }}>
      {top.map((p, i) => (
        <div key={p.project_id || i} onClick={() => onFilterProject?.(filters?.projectId === (p.project_id || p.id) ? '' : (p.project_id || p.id))} style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '7px 10px', background: filters?.projectId && filters.projectId === (p.project_id || p.id) ? 'var(--accent-muted)' : 'var(--surface-3)', borderRadius: 8, cursor: onFilterProject ? 'pointer' : 'default' }}>
          <span style={{ fontSize: 16, fontWeight: 900, color: 'var(--text-3)', fontFamily: 'var(--font-mono)', minWidth: 20 }}>#{i + 1}</span>
          <div style={{ flex: 1, minWidth: 0 }}>
            <div style={{ fontSize: 12, fontWeight: 600, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{p.project_name || p.name || p.code}</div>
            <div style={{ fontSize: 10, color: 'var(--text-2)' }}>{fmtCur(p.revenue || p.billed || 0)} facturado</div>
          </div>
          <div style={{ fontSize: 15, fontWeight: 800, fontFamily: 'var(--font-mono)', color: (p.margin_pct || 0) >= 30 ? GREEN : (p.margin_pct || 0) >= 15 ? AMBER : RED }}>
            {p.margin_pct ? `${p.margin_pct.toFixed(1)}%` : '—'}
          </div>
        </div>
      ))}
    </div>
  )
}

function MetricAlertsWidget() {
  const [threshold, setThreshold] = useState(10)
  const { data, isLoading } = useQuery({
    queryKey: ['bi-metric-alerts', threshold],
    queryFn: () => api.get('/analytics/alerts/metric-breaches', { params: { margin_threshold_pct: threshold } }).then(r => r.data).catch(() => ({ items: [] })),
  })

  if (isLoading) return <EmptyState icon="🚨" title="Cargando alertas..." />

  const alerts = data?.items || []
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 10, height: '100%' }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 10 }}>
        <div style={{ fontSize: 11, color: 'var(--text-2)' }}>Umbral de margen</div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <input type="range" min={-20} max={40} value={threshold} onChange={(e) => setThreshold(Number(e.target.value))} style={{ width: 120 }} />
          <span style={{ fontSize: 12, fontFamily: 'var(--font-mono)', color: 'var(--text-1)', minWidth: 40, textAlign: 'right' }}>{threshold}%</span>
        </div>
      </div>
      {alerts.length === 0 ? (
        <EmptyState icon="✅" title="No hay breaches de margen" subtitle="Todos los proyectos cumplen el umbral actual" />
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8, overflow: 'auto' }}>
          {alerts.slice(0, 10).map((a, i) => (
            <div key={`${a.project_code || i}-${i}`} style={{ background: 'var(--surface-3)', border: '1px solid var(--danger-border)', borderRadius: 8, padding: '8px 10px' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8 }}>
                <div style={{ fontSize: 12, fontWeight: 700, color: 'var(--text-1)' }}>{a.project_code || 'Proyecto'}</div>
                <div style={{ fontSize: 12, fontWeight: 700, color: RED }}>{fmtPct(a.margin_pct || 0)}</div>
              </div>
              <div style={{ fontSize: 11, color: 'var(--text-2)', marginTop: 2 }}>{a.description || 'Margen por debajo del umbral configurado'}</div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

export const WIDGET_REGISTRY = [
  { id: 'kpi_grid', label: 'KPIs principales', icon: '◈', defaultSize: 'L' },
  { id: 'health', label: 'Salud de proyectos', icon: '⬡', defaultSize: 'M' },
  { id: 'projects_type', label: 'Proyectos por tipo', icon: '🧩', defaultSize: 'M' },
  { id: 'revenue_cost', label: 'Ingresos vs Costes', icon: '📈', defaultSize: 'L' },
  { id: 'profit_project', label: 'Rentabilidad por proyecto', icon: '💰', defaultSize: 'L' },
  { id: 'utilization', label: 'Utilización del equipo', icon: '👥', defaultSize: 'M' },
  { id: 'top_clients', label: 'Top clientes', icon: '🏢', defaultSize: 'M' },
  { id: 'pipeline', label: 'Pipeline de ventas', icon: '🎪', defaultSize: 'M' },
  { id: 'hours', label: 'Horas imputadas', icon: '⏱', defaultSize: 'M' },
  { id: 'top_margin', label: 'Top proyectos por margen', icon: '🏆', defaultSize: 'M' },
  { id: 'metric_alerts', label: 'Alertas por umbral', icon: '🚨', defaultSize: 'M' },
]

export const DEFAULT_LAYOUT = WIDGET_REGISTRY.map(w => ({ id: w.id, visible: true, size: w.defaultSize }))
const SIZE_COLS = { S: 'span 1', M: 'span 1', L: 'span 2' }
const SIZE_HEIGHTS = { S: 200, M: 280, L: 280 }

export const WIDGET_ENDPOINTS = {
  kpi_grid: '/dashboard/kpis',
  health: '/dashboard/projects-health',
  projects_type: '/analytics/query/projects_by_type',
  revenue_cost: '/profitability/summary',
  profit_project: '/profitability/summary',
  utilization: '/analytics/utilization/advanced',
  top_clients: '/profitability/summary',
  pipeline: '/pipeline',
  hours: '/analytics/hours_by_week',
  top_margin: '/profitability/projects',
  metric_alerts: '/analytics/alerts/metric-breaches',
}

export function WidgetPanel({ wid, layout, onSizeChange, onToggle, onMoveUp, onMoveDown, isFirst, isLast, configMode, onExportData, onExportPdf, children }) {
  const reg = WIDGET_REGISTRY.find(w => w.id === wid)
  const cfg = layout.find(l => l.id === wid) || { size: 'M', visible: true }
  const height = SIZE_HEIGHTS[cfg.size] || 280

  return (
    <div id={`widget-${wid}`} style={{ gridColumn: SIZE_COLS[cfg.size] || 'span 1', background: 'var(--surface-2)', border: '1px solid var(--surface-4)', borderRadius: 14, padding: '16px 18px', display: 'flex', flexDirection: 'column', gap: 10, transition: 'all .2s', opacity: cfg.visible ? 1 : 0.4 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexShrink: 0 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <span style={{ fontSize: 16 }}>{reg?.icon}</span>
          <span style={{ fontSize: 13, fontWeight: 700, color: 'var(--text-1)' }}>{reg?.label}</span>
        </div>
        {configMode ? (
          <div style={{ display: 'flex', gap: 4, alignItems: 'center' }}>
            {['S', 'M', 'L'].map(s => (
              <button key={s} onClick={() => onSizeChange(wid, s)} style={{ padding: '2px 7px', borderRadius: 4, border: 'none', background: cfg.size === s ? 'var(--accent)' : 'var(--surface-4)', color: cfg.size === s ? '#fff' : 'var(--text-3)', cursor: 'pointer', fontSize: 10, fontFamily: 'inherit', fontWeight: 600 }}>
                {s}
              </button>
            ))}
            <button onClick={() => onMoveUp(wid)} disabled={isFirst} style={{ background: 'none', border: '1px solid var(--surface-4)', borderRadius: 4, padding: '2px 6px', color: isFirst ? 'var(--text-4)' : 'var(--text-2)', cursor: isFirst ? 'default' : 'pointer', fontSize: 12 }}>↑</button>
            <button onClick={() => onMoveDown(wid)} disabled={isLast} style={{ background: 'none', border: '1px solid var(--surface-4)', borderRadius: 4, padding: '2px 6px', color: isLast ? 'var(--text-4)' : 'var(--text-2)', cursor: isLast ? 'default' : 'pointer', fontSize: 12 }}>↓</button>
            <button onClick={() => onToggle(wid)} style={{ background: cfg.visible ? 'var(--success)' : 'var(--surface-4)', border: 'none', borderRadius: 4, padding: '2px 8px', color: cfg.visible ? '#fff' : 'var(--text-3)', cursor: 'pointer', fontSize: 10, fontFamily: 'inherit' }}>
              {cfg.visible ? '✓ Visible' : '○ Oculto'}
            </button>
          </div>
        ) : (
          <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
            <button onClick={() => onExportData?.(wid)} style={{ fontSize: 10, padding: '4px 8px', borderRadius: 6, border: '1px solid var(--surface-4)', background: 'var(--surface-3)', color: 'var(--text-2)', cursor: 'pointer' }}>XLS/CSV</button>
            <button onClick={() => onExportPdf?.(wid)} style={{ fontSize: 10, padding: '4px 8px', borderRadius: 6, border: '1px solid var(--surface-4)', background: 'var(--surface-3)', color: 'var(--text-2)', cursor: 'pointer' }}>PDF</button>
          </div>
        )}
      </div>
      <div style={{ flex: 1, minHeight: height, overflow: 'hidden' }}>
        {cfg.visible ? children : (
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100%', fontSize: 12, color: 'var(--text-3)' }}>
            Widget oculto — actívalo con el botón de configuración
          </div>
        )}
      </div>
    </div>
  )
}

const ACCENT_PRESETS = [
  { label: 'Azul clásico', color: 'var(--accent)' },
  { label: 'Índigo', color: '#7c3aed' },
  { label: 'Teal', color: '#1d9e75' },
  { label: 'Cyan', color: '#0ea5e9' },
  { label: 'Coral', color: '#f43f5e' },
  { label: 'Ámbar', color: '#f59e0b' },
  { label: 'Lime', color: '#84cc16' },
  { label: 'Rosa', color: '#ec4899' },
]

export function ConfigPanel({ prefs, onSave, onClose }) {
  const [localAccent, setLocalAccent] = useState(prefs.accent_color || '#4f8ef7')
  const [localDensity, setLocalDensity] = useState(prefs.ui_density || 'normal')

  const applyAccent = (color) => {
    setLocalAccent(color)
    document.documentElement.style.setProperty('--accent', color)
    document.documentElement.style.setProperty('--accent-muted', color + '14')
    document.documentElement.style.setProperty('--accent-glow', color + '26')
  }

  const handleSave = () => {
    onSave({ accent_color: localAccent, ui_density: localDensity })
    onClose()
  }

  return (
    <div style={{ position: 'fixed', top: 0, right: 0, bottom: 0, width: 340, zIndex: 200, background: 'var(--surface-1)', borderLeft: '1px solid var(--surface-4)', display: 'flex', flexDirection: 'column', boxShadow: '-8px 0 32px rgba(0,0,0,0.4)' }}>
      <div style={{ padding: '16px 20px', borderBottom: '1px solid var(--surface-4)', display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexShrink: 0 }}>
        <div style={{ fontSize: 14, fontWeight: 700 }}>⚙ Personalizar dashboard</div>
        <button onClick={onClose} style={{ background: 'none', border: 'none', color: 'var(--text-2)', cursor: 'pointer', fontSize: 20, padding: '0 4px' }}>✕</button>
      </div>
      <div style={{ flex: 1, overflowY: 'auto', padding: '20px' }}>
        <div style={{ marginBottom: 24 }}>
          <div style={{ fontSize: 12, fontWeight: 700, color: 'var(--text-2)', textTransform: 'uppercase', letterSpacing: '0.07em', marginBottom: 12 }}>Color de acento</div>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4,1fr)', gap: 8, marginBottom: 12 }}>
            {ACCENT_PRESETS.map(p => (
              <button key={p.color} onClick={() => applyAccent(p.color)} title={p.label} style={{ width: '100%', aspectRatio: '1', borderRadius: 8, background: p.color, border: `2px solid ${localAccent === p.color ? '#fff' : 'transparent'}`, cursor: 'pointer' }} />
            ))}
          </div>
          <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
            <input type="color" value={localAccent} onChange={e => applyAccent(e.target.value)} style={{ width: 40, height: 40, border: 'none', borderRadius: 8, cursor: 'pointer', background: 'none', padding: 0 }} />
            <div>
              <div style={{ fontSize: 12, color: 'var(--text-1)', fontFamily: 'var(--font-mono)' }}>{localAccent}</div>
              <div style={{ fontSize: 10, color: 'var(--text-3)' }}>Color personalizado</div>
            </div>
          </div>
        </div>

        <div style={{ marginBottom: 24 }}>
          <div style={{ fontSize: 12, fontWeight: 700, color: 'var(--text-2)', textTransform: 'uppercase', letterSpacing: '0.07em', marginBottom: 10 }}>Densidad de la interfaz</div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
            {[
              ['compact', 'Compacta', 'Más información en pantalla'],
              ['normal', 'Normal', 'Equilibrio entre densidad y legibilidad'],
              ['comfortable', 'Confortable', 'Más espaciado, más fácil de leer'],
            ].map(([val, label, desc]) => (
              <button key={val} onClick={() => setLocalDensity(val)} style={{ padding: '10px 14px', borderRadius: 9, textAlign: 'left', background: localDensity === val ? 'var(--accent-muted)' : 'var(--surface-3)', border: `1px solid ${localDensity === val ? 'var(--accent-glow)' : 'var(--surface-4)'}`, cursor: 'pointer', fontFamily: 'inherit' }}>
                <div style={{ fontSize: 13, fontWeight: 600, color: localDensity === val ? 'var(--accent)' : 'var(--text-1)' }}>{label}</div>
                <div style={{ fontSize: 11, color: 'var(--text-3)', marginTop: 2 }}>{desc}</div>
              </button>
            ))}
          </div>
        </div>
      </div>
      <div style={{ padding: '16px 20px', borderTop: '1px solid var(--surface-4)', display: 'flex', gap: 10, flexShrink: 0 }}>
        <button onClick={handleSave} style={{ flex: 1, padding: '10px', background: 'var(--accent)', border: 'none', borderRadius: 8, color: '#fff', cursor: 'pointer', fontSize: 13, fontFamily: 'inherit', fontWeight: 600 }}>Guardar preferencias</button>
        <button onClick={onClose} style={{ padding: '10px 16px', background: 'var(--surface-3)', border: '1px solid var(--surface-4)', borderRadius: 8, color: 'var(--text-2)', cursor: 'pointer', fontSize: 13, fontFamily: 'inherit' }}>Cancelar</button>
      </div>
    </div>
  )
}

export function buildWidgetComponents({ filters, setFilters, setDrillProject }) {
  return {
    kpi_grid: <KpiGridWidget filters={filters} />,
    health: <HealthWidget filters={filters} />,
    projects_type: <ProjectsByTypeWidget filters={filters} onFilterType={(type) => setFilters(prev => ({ ...prev, projectType: type || '' }))} />,
    revenue_cost: <RevenueVsCostWidget filters={filters} />,
    profit_project: <ProfitByProjectWidget onDrill={setDrillProject} onFilterProject={(pid) => setFilters(prev => ({ ...prev, projectId: pid || '' }))} filters={filters} />,
    utilization: <UtilizationWidget filters={filters} />,
    top_clients: <TopClientsWidget filters={filters} onFilterClient={(cid) => setFilters(prev => ({ ...prev, clientId: cid || '' }))} />,
    pipeline: <PipelineWidget />,
    hours: <HoursWidget filters={filters} />,
    top_margin: <TopProjectsMarginWidget filters={filters} onFilterProject={(pid) => setFilters(prev => ({ ...prev, projectId: pid || '' }))} />,
    metric_alerts: <MetricAlertsWidget />,
  }
}
