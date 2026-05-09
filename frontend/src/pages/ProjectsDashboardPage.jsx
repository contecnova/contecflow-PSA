import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { dashboardApi, analyticsApi, risksApi } from '../services/api'
import { useAllProjects } from '../hooks/useProjects'
import { Spinner } from '../components/ui'
import {
  FolderOpen, Hexagon, Activity, AlertOctagon, Zap, AlertTriangle, ListTodo,
  AlertCircle,
} from 'lucide-react'
import {
  COLOR, DashPageShell, KpiCard, KpiIcon, GaugeCard, BarRow, SectionCard, DashEmpty,
  dateRange, typePalette,
} from '../components/dashboard/DashKit'

const STATUS_COLORS = {
  active:    COLOR.accent,
  planning:  'var(--sky-blue)',
  on_hold:   COLOR.warning,
  paused:    COLOR.warning,
  completed: COLOR.success,
  closed:    COLOR.success,
  cancelled: COLOR.danger,
  archived:  'var(--text-3)',
}

const STATUS_LABELS = {
  active:    'Activo',
  planning:  'Planificación',
  on_hold:   'En espera',
  paused:    'Pausado',
  completed: 'Completado',
  closed:    'Cerrado',
  cancelled: 'Cancelado',
  archived:  'Archivado',
}

export default function ProjectsDashboardPage() {
  const [days, setDays] = useState(30)
  const params = dateRange(days)

  const { data: health = [], isLoading: lh } = useQuery({
    queryKey: ['proj-dash-health', days],
    queryFn: () => dashboardApi.projectsHealth(params).then(r => r.data).catch(() => []),
    staleTime: 60_000,
  })

  const { data: allProjects = [] } = useAllProjects()

  const { data: byTypeRaw, isLoading: lt } = useQuery({
    queryKey: ['proj-dash-type', days],
    queryFn: () => analyticsApi.query('projects_by_type', params).then(r => r.data?.rows || []).catch(() => []),
    staleTime: 60_000,
  })
  const byType = byTypeRaw ?? []

  const { data: kpis } = useQuery({
    queryKey: ['proj-dash-kpis', days],
    queryFn: () => dashboardApi.kpis().then(r => r.data).catch(() => ({})),
    staleTime: 60_000,
  })

  const { data: risks = [] } = useQuery({
    queryKey: ['proj-dash-risks'],
    queryFn: () => risksApi.portfolioAll().then(r => {
      const d = r.data; return Array.isArray(d) ? d : []
    }).catch(() => []),
    staleTime: 60_000,
  })

  if (lh || lt) return (
    <div style={{ padding: 32, display: 'flex', justifyContent: 'center', minHeight: 300, alignItems: 'center' }}>
      <Spinner />
    </div>
  )

  const total = allProjects.length
  const active = allProjects.filter(p => p.status === 'active').length
  const isCrit = p => (p.schedule_deviation_days || 0) > 0 || (p.budget_used_pct || 0) > 100
  const isWarn = p => !isCrit(p) && ((p.budget_used_pct || 0) > 80 || (p.alerts_count || 0) > 0)
  const crit = health.filter(isCrit).length
  const warn = health.filter(isWarn).length
  const ok = Math.max(health.length - crit - warn, 0)
  const onTimePct = health.length > 0 ? Math.round((ok / health.length) * 100) : 0
  const onTimeColor = onTimePct >= 80 ? COLOR.success : onTimePct >= 60 ? COLOR.warning : COLOR.danger

  const budgetTotal = Number(kpis?.total_budget) || 0
  const budgetSpent = Number(kpis?.total_spent) || 0
  const budgetPct = budgetTotal > 0 ? Math.round((budgetSpent / budgetTotal) * 100) : null
  const budgetColor = budgetPct == null ? COLOR.accent : budgetPct > 90 ? COLOR.danger : budgetPct > 70 ? COLOR.warning : COLOR.success

  const highRisks = risks.filter(r => r.severity === 'high' || r.severity === 'critical').length

  const statusCounts = allProjects.reduce((acc, p) => {
    acc[p.status] = (acc[p.status] || 0) + 1; return acc
  }, {})
  const statusRows = Object.entries(statusCounts)
    .sort((a, b) => b[1] - a[1])
    .map(([status, count]) => ({
      label: STATUS_LABELS[status] || status,
      count,
      color: STATUS_COLORS[status] || 'var(--text-3)',
    }))

  const totalByType = byType.reduce((s, r) => s + (r.value || 0), 0)

  return (
    <DashPageShell
      icon={<FolderOpen size={18} />}
      title="Cartera de Proyectos"
      subtitle="Estado, salud y rendimiento de todos los proyectos"
      days={days} setDays={setDays}
      periods={[30, 90, 365]}
    >
      <div className="ds-page">
        {/* KPI row */}
        <div className="ds-grid-stats">
          <KpiCard icon={<KpiIcon icon={Hexagon} />} label="Total proyectos"
            value={total} color="var(--text-1)" accentBar={COLOR.accent} />
          <KpiCard icon={<KpiIcon icon={Activity} />} label="Activos"
            value={active} color={COLOR.accent} accentBar={COLOR.accent} />
          <KpiCard icon={<KpiIcon icon={AlertOctagon} />} label="Críticos"
            value={crit}
            color={crit > 0 ? COLOR.danger : COLOR.success}
            accentBar={crit > 0 ? COLOR.danger : COLOR.success}
            sub={crit > 0 ? 'Fuera de plazo o presupuesto' : 'Sin proyectos críticos'} />
          <KpiCard icon={<KpiIcon icon={Zap} />} label="En riesgo"
            value={warn}
            color={warn > 0 ? COLOR.warning : COLOR.success}
            accentBar={warn > 0 ? COLOR.warning : COLOR.success}
            sub="Presupuesto > 80% o alertas" />
          <KpiCard icon={<KpiIcon icon={AlertTriangle} />} label="Riesgos abiertos"
            value={risks.length}
            color={highRisks > 0 ? COLOR.danger : risks.length > 0 ? COLOR.warning : COLOR.success}
            accentBar={COLOR.warning}
            sub={highRisks > 0 ? `${highRisks} de alta gravedad` : undefined} />
          <KpiCard icon={<KpiIcon icon={ListTodo} />} label="Tareas vencidas"
            value={kpis?.tasks_overdue ?? 0}
            color={(kpis?.tasks_overdue ?? 0) > 0 ? COLOR.warning : COLOR.success}
            accentBar={COLOR.warning} />
        </div>

        {/* Gauges */}
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: 'var(--space-3)' }}>
          <GaugeCard label="Proyectos a tiempo"
            value={onTimePct} color={onTimeColor}
            sub={onTimePct >= 80 ? 'Excelente rendimiento' : onTimePct >= 60 ? 'Aceptable' : 'Requiere atención'} />
          {budgetPct != null && (
            <GaugeCard label="Uso de presupuesto"
              value={budgetPct} color={budgetColor}
              sub={budgetPct > 90 ? 'Presupuesto casi agotado' : budgetPct > 70 ? 'Consumo elevado' : 'Bajo control'} />
          )}
        </div>

        {/* Charts */}
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))', gap: 'var(--space-3)' }}>
          <SectionCard title="Por tipo de proyecto">
            {byType.length === 0
              ? <DashEmpty title="Sin datos por tipo" />
              : byType.map((row, i) => (
                  <BarRow key={row.label || i}
                    label={row.label || 'Sin tipo'}
                    count={row.value || 0} total={totalByType}
                    color={typePalette[i % typePalette.length]} />
                ))
            }
          </SectionCard>

          <SectionCard title="Por estado">
            {statusRows.length === 0
              ? <DashEmpty title="Sin datos de estado" />
              : statusRows.map(row => (
                  <BarRow key={row.label}
                    label={row.label} count={row.count}
                    total={Math.max(total, 1)} color={row.color} />
                ))
            }
          </SectionCard>
        </div>

        {/* At-risk list */}
        {crit > 0 && (
          <SectionCard title="Proyectos críticos" badge={crit}>
            <div className="ds-stack-sm">
              {health
                .filter(p => p.schedule_deviation_days > 0 || p.budget_used_pct > 100)
                .slice(0, 8)
                .map(p => {
                  const budPct = Math.round(p.budget_used_pct || 0)
                  const color  = budPct > 100 ? COLOR.danger : COLOR.warning
                  const RiskIcon = budPct > 100 ? AlertOctagon : AlertCircle
                  return (
                    <div key={p.project_id} className="ds-card--inset" style={{
                      display: 'flex', alignItems: 'center', gap: 'var(--space-3)',
                      border: `1px solid ${color}30`,
                    }}>
                      <RiskIcon size={16} style={{ color, flexShrink: 0 }} />
                      <div style={{ flex: 1, minWidth: 0 }}>
                        <div style={{ fontSize: "var(--text-base)", fontWeight: 600, color: 'var(--text-1)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                          {p.project_code && <span className="ds-muted" style={{ marginRight: 6, fontSize: "var(--text-xs)" }}>{p.project_code}</span>}
                          {p.project_name}
                        </div>
                        <div className="ds-muted">
                          Presupuesto: {budPct}% · Desviación: {p.schedule_deviation_days > 0 ? `+${p.schedule_deviation_days}d` : 'OK'}
                        </div>
                      </div>
                      <span style={{
                        fontSize: "var(--text-xs)", fontWeight: 700, color,
                        background: `${color}18`, border: `1px solid ${color}30`,
                        borderRadius: 'var(--radius-sm)', padding: '3px 9px',
                      }}>{budPct}%</span>
                    </div>
                  )
                })}
            </div>
          </SectionCard>
        )}
      </div>
    </DashPageShell>
  )
}

