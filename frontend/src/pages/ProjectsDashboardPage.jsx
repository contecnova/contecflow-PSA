import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import api from '../services/api'
import { Spinner } from '../components/ui'
import { FolderOpen } from 'lucide-react'
import {
  COLOR, S, DashPageShell, KpiCard, GaugeCard, BarRow, SectionCard, DashEmpty,
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

export default function ProjectsDashboardPage() {
  const [days, setDays] = useState(30)
  const params = dateRange(days)

  const { data: health = [], isLoading: lh } = useQuery({
    queryKey: ['proj-dash-health', days],
    queryFn: () => api.get('/dashboard/projects-health', { params }).then(r => r.data).catch(() => []),
    staleTime: 60_000,
  })

  const { data: byType = [], isLoading: lt } = useQuery({
    queryKey: ['proj-dash-type', days],
    queryFn: () => api.get('/analytics/query/projects_by_type', { params }).then(r => r.data?.rows || []).catch(() => []),
    staleTime: 60_000,
  })

  const { data: kpis } = useQuery({
    queryKey: ['proj-dash-kpis', days],
    queryFn: () => api.get('/dashboard/kpis', { params }).then(r => r.data).catch(() => ({})),
    staleTime: 60_000,
  })

  const { data: risks = [] } = useQuery({
    queryKey: ['proj-dash-risks'],
    queryFn: () => api.get('/risks/all/portfolio').then(r => {
      const d = r.data; return Array.isArray(d) ? d : []
    }).catch(() => []),
    staleTime: 60_000,
  })

  if (lh || lt) return (
    <div style={{ padding: 32, display: 'flex', justifyContent: 'center', minHeight: 300, alignItems: 'center' }}>
      <Spinner />
    </div>
  )

  const total     = health.length
  const active    = health.filter(p => p.status === 'active').length
  const crit      = health.filter(p => p.schedule_deviation_days > 0 || p.budget_used_pct > 100).length
  const warn      = health.filter(p => p.budget_used_pct > 80 || p.alerts_count > 0).length
  const ok        = total - crit - warn
  const onTimePct = total > 0 ? Math.round((ok / total) * 100) : 0
  const onTimeColor = onTimePct >= 80 ? COLOR.success : onTimePct >= 60 ? COLOR.warning : COLOR.danger

  const budgetPct = kpis?.total_budget > 0
    ? Math.round((kpis.total_spent / kpis.total_budget) * 100) : null
  const budgetColor = budgetPct == null ? COLOR.accent : budgetPct > 90 ? COLOR.danger : budgetPct > 70 ? COLOR.warning : COLOR.success

  const highRisks = risks.filter(r => r.severity === 'high' || r.severity === 'critical').length

  const statusCounts = health.reduce((acc, p) => {
    acc[p.status] = (acc[p.status] || 0) + 1; return acc
  }, {})
  const statusRows = Object.entries(statusCounts)
    .sort((a, b) => b[1] - a[1])
    .map(([status, count]) => ({ label: status, count, color: STATUS_COLORS[status] || 'var(--text-3)' }))

  const totalByType = byType.reduce((s, r) => s + (r.value || 0), 0)

  return (
    <DashPageShell
      icon={<FolderOpen size={18} />}
      title="Cartera de Proyectos"
      subtitle="Estado, salud y rendimiento de todos los proyectos"
      days={days} setDays={setDays}
      periods={[30, 90, 365]}
    >
      {/* KPI row */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(160px, 1fr))', gap: 14, marginBottom: 14 }}>
        <KpiCard icon="⬡" label="Total proyectos"
          value={total} color="var(--text-1)" accentBar={COLOR.accent} />
        <KpiCard icon="🟢" label="Activos"
          value={active} color={COLOR.accent} accentBar={COLOR.accent} />
        <KpiCard icon="🚨" label="Críticos"
          value={crit}
          color={crit > 0 ? COLOR.danger : COLOR.success}
          accentBar={crit > 0 ? COLOR.danger : COLOR.success}
          sub={crit > 0 ? 'Fuera de plazo o presupuesto' : 'Sin proyectos críticos'} />
        <KpiCard icon="⚡" label="En riesgo"
          value={warn}
          color={warn > 0 ? COLOR.warning : COLOR.success}
          accentBar={warn > 0 ? COLOR.warning : COLOR.success}
          sub="Presupuesto > 80% o alertas" />
        <KpiCard icon="🔺" label="Riesgos abiertos"
          value={risks.length}
          color={highRisks > 0 ? COLOR.danger : risks.length > 0 ? COLOR.warning : COLOR.success}
          accentBar={COLOR.warning}
          sub={highRisks > 0 ? `${highRisks} de alta gravedad` : undefined} />
        <KpiCard icon="▦" label="Tareas vencidas"
          value={kpis?.tasks_overdue ?? 0}
          color={(kpis?.tasks_overdue ?? 0) > 0 ? COLOR.warning : COLOR.success}
          accentBar={COLOR.warning} />
      </div>

      {/* Gauges */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: 14, marginBottom: 20 }}>
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
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))', gap: 14, marginBottom: 20 }}>
        <SectionCard title="Por tipo de proyecto">
          {byType.length === 0
            ? <DashEmpty icon="🧩" title="Sin datos por tipo" />
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
            ? <DashEmpty icon="📋" title="Sin datos de estado" />
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
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            {health
              .filter(p => p.schedule_deviation_days > 0 || p.budget_used_pct > 100)
              .slice(0, 8)
              .map(p => {
                const budPct = Math.round(p.budget_used_pct || 0)
                const color  = budPct > 100 ? COLOR.danger : COLOR.warning
                return (
                  <div key={p.project_id} style={{
                    display: 'flex', alignItems: 'center', gap: 12,
                    padding: '10px 14px',
                    background: 'var(--surface-3)',
                    border: `1px solid ${color}30`,
                    borderRadius: 10,
                  }}>
                    <span style={{ fontSize: 14 }}>{budPct > 100 ? '🔴' : '🟡'}</span>
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--text-1)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                        {p.project_code && <span style={{ color: 'var(--text-3)', marginRight: 6, fontSize: 11 }}>{p.project_code}</span>}
                        {p.project_name}
                      </div>
                      <div style={{ fontSize: 11, color: 'var(--text-3)', marginTop: 2 }}>
                        Presupuesto: {budPct}% · Desviación: {p.schedule_deviation_days > 0 ? `+${p.schedule_deviation_days}d` : 'OK'}
                      </div>
                    </div>
                    <span style={{
                      fontSize: 11, fontWeight: 700, color,
                      background: `${color}18`, border: `1px solid ${color}30`,
                      borderRadius: 6, padding: '3px 9px',
                    }}>{budPct}%</span>
                  </div>
                )
              })}
          </div>
        </SectionCard>
      )}
    </DashPageShell>
  )
}
