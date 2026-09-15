import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { dashboardApi, analyticsApi, risksApi } from '../services/api'
import { useAllProjects } from '../hooks/useProjects'
import { Spinner } from '../components/ui'
import {
  FolderOpen, Hexagon, Activity, AlertOctagon, Zap, AlertTriangle, ListTodo,
  AlertCircle,
} from 'lucide-react'
import type { ComponentType } from 'react'
import {
  COLOR, DashPageShell, KpiCard, KpiIcon, GaugeCard, BarRow, SectionCard, DashEmpty,
  dateRange, typePalette,
} from '../components/dashboard/DashKit'
import { useAppT } from '../i18n/AppLangContext'

const STATUS_COLORS: Record<string, string> = {
  active:    COLOR.accent,
  planning:  'var(--sky-blue)',
  on_hold:   COLOR.warning,
  paused:    COLOR.warning,
  completed: COLOR.success,
  closed:    COLOR.success,
  cancelled: COLOR.danger,
  archived:  'var(--text-3)',
}

interface DashboardProjectHealth {
  project_id: string | number
  project_code?: string
  project_name?: string
  schedule_deviation_days?: number
  budget_used_pct?: number
  alerts_count?: number
}

interface ProjectItem {
  status?: string
}

interface TypeRow {
  label?: string
  value?: number
}

interface RiskRow {
  severity?: string
}

export default function ProjectsDashboardPage() {
  const t = useAppT()
  const STATUS_LABELS: Record<string, string> = {
    active:    t('projects_dashboard.status_active'),
    planning:  t('projects_dashboard.status_planning'),
    on_hold:   t('projects_dashboard.status_on_hold'),
    paused:    t('projects_dashboard.status_paused'),
    completed: t('projects_dashboard.status_completed'),
    closed:    t('projects_dashboard.status_closed'),
    cancelled: t('projects_dashboard.status_cancelled'),
    archived:  t('projects_dashboard.status_archived'),
  }
  const [days, setDays] = useState(30)
  const iconCompat = <T,>(icon: T) => icon as unknown as ComponentType<{ size?: number; strokeWidth?: number }>
  const params = dateRange(days)

  const { data: health = [], isLoading: lh } = useQuery<DashboardProjectHealth[]>({
    queryKey: ['proj-dash-health', days],
    queryFn: () => dashboardApi.projectsHealth(params).then(r => r.data).catch(() => []),
    staleTime: 60_000,
  })

  const { data: allProjects = [] } = useAllProjects() as { data: ProjectItem[] }

  const { data: byTypeRaw, isLoading: lt } = useQuery<TypeRow[]>({
    queryKey: ['proj-dash-type', days],
    queryFn: () => analyticsApi.query('projects_by_type', params).then(r => r.data?.rows || []).catch(() => []),
    staleTime: 60_000,
  })
  const byType: TypeRow[] = byTypeRaw ?? []

  const { data: kpis } = useQuery({
    queryKey: ['proj-dash-kpis', days],
    queryFn: () => dashboardApi.kpis().then(r => r.data).catch(() => ({})),
    staleTime: 60_000,
  })

  const { data: risks = [] } = useQuery<RiskRow[]>({
    queryKey: ['proj-dash-risks'],
    queryFn: () => risksApi.portfolioAll().then(r => {
      const d = r.data; return Array.isArray(d) ? d : (d?.items ?? [])
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
  const isCrit = (p: DashboardProjectHealth) => (p.schedule_deviation_days || 0) > 0 || (p.budget_used_pct || 0) > 100
  const isWarn = (p: DashboardProjectHealth) => !isCrit(p) && ((p.budget_used_pct || 0) > 80 || (p.alerts_count || 0) > 0)
  const crit = health.filter(isCrit).length
  const warn = health.filter(isWarn).length
  const ok = Math.max(health.length - crit - warn, 0)
  const onTimePct = health.length > 0 ? Math.round((ok / health.length) * 100) : 0
  const onTimeColor = onTimePct >= 80 ? COLOR.success : onTimePct >= 60 ? COLOR.warning : COLOR.danger

  const budgetTotal = Number(kpis?.total_budget) || 0
  const budgetSpent = Number(kpis?.total_spent) || 0
  const budgetPct = budgetTotal > 0 ? Math.round((budgetSpent / budgetTotal) * 100) : null
  const budgetColor = budgetPct == null ? COLOR.accent : budgetPct > 90 ? COLOR.danger : budgetPct > 70 ? COLOR.warning : COLOR.success

  const highRisks = risks.filter((r) => r.severity === 'high' || r.severity === 'critical').length

  const statusCounts = allProjects.reduce<Record<string, number>>((acc, p) => {
    const estado = p.status ?? 'desconocido'
    acc[estado] = (acc[estado] || 0) + 1
    return acc
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
      title={t('projects_dashboard.title')}
      subtitle={t('projects_dashboard.subtitle')}
      days={days} setDays={setDays}
      periods={[30, 90, 365]}
    >
      <div className="ds-page">
        {/* KPI row */}
        <div className="ds-grid-stats">
          <KpiCard icon={<KpiIcon icon={iconCompat(Hexagon)} />} label={t('projects_dashboard.kpi_total')}
            value={total} color="var(--text-1)" accentBar={COLOR.accent} />
          <KpiCard icon={<KpiIcon icon={iconCompat(Activity)} />} label={t('projects_dashboard.kpi_active')}
            value={active} color={COLOR.accent} accentBar={COLOR.accent} />
          <KpiCard icon={<KpiIcon icon={iconCompat(AlertOctagon)} />} label={t('projects_dashboard.kpi_critical')}
            value={crit}
            color={crit > 0 ? COLOR.danger : COLOR.success}
            accentBar={crit > 0 ? COLOR.danger : COLOR.success}
            sub={crit > 0 ? t('projects_dashboard.critical_sub_active') : t('projects_dashboard.critical_sub_none')} />
          <KpiCard icon={<KpiIcon icon={iconCompat(Zap)} />} label={t('projects_dashboard.kpi_at_risk')}
            value={warn}
            color={warn > 0 ? COLOR.warning : COLOR.success}
            accentBar={warn > 0 ? COLOR.warning : COLOR.success}
            sub={t('projects_dashboard.at_risk_sub')} />
          <KpiCard icon={<KpiIcon icon={iconCompat(AlertTriangle)} />} label={t('projects_dashboard.kpi_open_risks')}
            value={risks.length}
            color={highRisks > 0 ? COLOR.danger : risks.length > 0 ? COLOR.warning : COLOR.success}
            accentBar={COLOR.warning}
            sub={highRisks > 0 ? `${highRisks} ${t('projects_dashboard.high_severity_sub')}` : undefined} />
          <KpiCard icon={<KpiIcon icon={iconCompat(ListTodo)} />} label={t('projects_dashboard.kpi_overdue_tasks')}
            value={kpis?.tasks_overdue ?? 0}
            color={(kpis?.tasks_overdue ?? 0) > 0 ? COLOR.warning : COLOR.success}
            accentBar={COLOR.warning} />
        </div>

        {/* Gauges */}
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: 'var(--space-3)' }}>
          <GaugeCard label={t('projects_dashboard.gauge_on_time')}
            value={onTimePct} color={onTimeColor}
            sub={onTimePct >= 80 ? t('projects_dashboard.excellent_performance') : onTimePct >= 60 ? t('projects_dashboard.acceptable') : t('projects_dashboard.needs_attention')} />
          {budgetPct != null && (
            <GaugeCard label={t('projects_dashboard.gauge_budget_usage')}
              value={budgetPct} color={budgetColor}
              sub={budgetPct > 90 ? t('projects_dashboard.budget_almost_depleted') : budgetPct > 70 ? t('projects_dashboard.budget_high_use') : t('projects_dashboard.budget_under_control')} />
          )}
        </div>

        {/* Charts */}
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))', gap: 'var(--space-3)' }}>
          <SectionCard title={t('projects_dashboard.section_by_type')}>
            {byType.length === 0
              ? <DashEmpty title={t('projects_dashboard.no_type_data')} />
              : byType.map((row, i) => (
                  <BarRow key={row.label || i}
                    label={row.label || t('projects_dashboard.no_type')}
                    count={row.value || 0} total={totalByType}
                    color={typePalette[i % typePalette.length]} />
                ))
            }
          </SectionCard>

          <SectionCard title={t('projects_dashboard.section_by_status')}>
            {statusRows.length === 0
              ? <DashEmpty title={t('projects_dashboard.no_status_data')} />
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
          <SectionCard title={t('projects_dashboard.section_critical_projects')} badge={crit}>
            <div className="ds-stack-sm">
              {health
                .filter(p => (p.schedule_deviation_days ?? 0) > 0 || (p.budget_used_pct ?? 0) > 100)
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
                          {t('projects_dashboard.budget_label')}: {budPct}% · {t('projects_dashboard.deviation_label')}: {(p.schedule_deviation_days ?? 0) > 0 ? `+${p.schedule_deviation_days}d` : t('projects_dashboard.deviation_ok')}
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

