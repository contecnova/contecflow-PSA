/**
 * ProjectsDashboardPage — panel de proyectos (/projects-dashboard).
 *
 * 16-11-2026: pasada de diseño. El título era «Cartera de Proyectos», igual que
 * /projects: ahora el del menú («Panel de proyectos»). KpiCard del kit (antes
 * la variante con borde superior de color), vacíos con EmptyState e icono
 * lucide (antes emoji desvaído) y el periodo con Tabs en una barra bajo la
 * cabecera (antes botones propios en la cabecera y «últimos N días» fijo en
 * castellano en el subtítulo). Proyectos críticos con StatusBadge.
 */
import { useQuery } from '@tanstack/react-query'
import { dashboardApi, analyticsApi, risksApi } from '../services/api'
import type { RiesgoAbiertoDeLaCartera } from '../services/api/tipos-proyectos'
import { useAllProjects } from '../hooks/useProjects'
import { EmptyState, KpiCard, SelectorDePeriodo, Spinner } from '../components/ui'
import StatusBadge from '../components/ui/StatusBadge'
import PageShell from '../components/layout/PageShell'
import PageHeader from '../components/layout/PageHeader'
import {
  LayoutDashboard, Hexagon, Activity, AlertOctagon, Zap, AlertTriangle, ListTodo,
  AlertCircle, PieChart, BarChart3,
} from 'lucide-react'
import {
  COLOR, GaugeCard, BarRow, SectionCard, typePalette,
} from '../components/dashboard/DashKit'
import { usePeriodo } from '../hooks/usePeriodo'
import { SIN_HORA, codigoDeErrorDePeriodo } from '../utils/periodo'
import { useAppT } from '../i18n/AppLangContext'
import { STALE_DEFAULT_MS } from '../constants/timings'
import type { FilaDeMetrica, KpisDelCuadroDeMando, SaludDeProyecto } from '../services/api/tipos-analitica'
import './ProjectsDashboardPage.css'

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
  // Periodo libre (16-11-2026): antes 30/90/365 días propios. La métrica es por
  // día de calendario y sin serie: sin hora ni agrupación.
  const periodo = usePeriodo({ defecto: '30d', granularidades: SIN_HORA })
  const params = periodo.params

  // `/dashboard/projects-health` y `/dashboard/kpis` no filtran por fechas: son
  // la foto actual, y no dependen del periodo elegido.
  const { data: health = [], isLoading: lh } = useQuery<SaludDeProyecto[]>({
    queryKey: ['proj-dash-health'],
    queryFn: () => dashboardApi.projectsHealth().then(r => r.data).catch(() => []),
    staleTime: STALE_DEFAULT_MS,
  })

  const { data: allProjects = [] } = useAllProjects()

  const { data: byTypeRaw, isLoading: lt, error: errorTipo } = useQuery<FilaDeMetrica[]>({
    queryKey: ['proj-dash-type', params],
    // Un periodo no válido (422 `periodo.*`) se explica; el resto, vacío como antes.
    queryFn: () => analyticsApi.query('projects_by_type', { ...params }).then(r => r.data.rows)
      .catch((e: unknown) => { if (codigoDeErrorDePeriodo(e)) throw e; return [] }),
    retry: false,
    staleTime: STALE_DEFAULT_MS,
  })
  const byType: FilaDeMetrica[] = byTypeRaw ?? []

  const { data: kpis } = useQuery<KpisDelCuadroDeMando | null>({
    queryKey: ['proj-dash-kpis'],
    queryFn: () => dashboardApi.kpis().then(r => r.data).catch(() => null),
    staleTime: STALE_DEFAULT_MS,
  })

  const { data: risks = [] } = useQuery({
    queryKey: ['proj-dash-risks'],
    queryFn: () => risksApi.portfolioAll().then(r => r.data).catch((): RiesgoAbiertoDeLaCartera[] => []),
    staleTime: STALE_DEFAULT_MS,
  })

  const errorDePeriodo = codigoDeErrorDePeriodo(errorTipo)

  const cabecera = (
    <PageHeader
      icon={<LayoutDashboard size={18} />}
      title={t('nav.projects_dashboard')}
      subtitle={t('projects_dashboard.subtitle')}
      showListExport={false}
    />
  )

  if (lh || lt) return (
    <PageShell>
      {cabecera}
      <div className="pdash-cargando"><Spinner /></div>
    </PageShell>
  )

  const total = allProjects.length
  const active = allProjects.filter(p => p.status === 'active').length
  const isCrit = (p: SaludDeProyecto) => (p.schedule_deviation_days || 0) > 0 || (p.budget_used_pct || 0) > 100
  const isWarn = (p: SaludDeProyecto) => !isCrit(p) && ((p.budget_used_pct || 0) > 80 || (p.alerts_count || 0) > 0)
  const crit = health.filter(isCrit).length
  const warn = health.filter(isWarn).length
  const ok = Math.max(health.length - crit - warn, 0)
  const onTimePct = health.length > 0 ? Math.round((ok / health.length) * 100) : 0
  const onTimeColor = onTimePct >= 80 ? COLOR.success : onTimePct >= 60 ? COLOR.warning : COLOR.danger

  const budgetTotal = Number(kpis?.total_budget) || 0
  const budgetSpent = Number(kpis?.total_spent) || 0
  const budgetPct = budgetTotal > 0 ? Math.round((budgetSpent / budgetTotal) * 100) : null
  const budgetColor = budgetPct == null ? COLOR.accent : budgetPct > 90 ? COLOR.danger : budgetPct > 70 ? COLOR.warning : COLOR.success

  const highRisks = risks.filter((r) => r.risk_level === 'high' || r.risk_level === 'critical').length
  const overdue = kpis?.tasks_overdue ?? 0

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
    <PageShell>
      {cabecera}
      <div className="u-stack-16">
        <div className="ds-toolbar">
          <SelectorDePeriodo {...periodo.selector} sinGranularidad />
        </div>
        {errorDePeriodo && (
          <EmptyState icon={<AlertTriangle size={28} />} title={t(`periodo_err.${errorDePeriodo.motivo}`, errorDePeriodo.params)} />
        )}

        {/* KPI row */}
        <div className="ds-grid-stats">
          <KpiCard icon={<Hexagon size={16} />} label={t('projects_dashboard.kpi_total')} value={total} />
          <KpiCard icon={<Activity size={16} />} label={t('projects_dashboard.kpi_active')} value={active} accent />
          <KpiCard icon={<AlertOctagon size={16} />} label={t('projects_dashboard.kpi_critical')} value={crit} danger={crit > 0}
            sub={crit > 0 ? t('projects_dashboard.critical_sub_active') : t('projects_dashboard.critical_sub_none')} />
          <KpiCard icon={<Zap size={16} />} label={t('projects_dashboard.kpi_at_risk')} value={warn} warning={warn > 0}
            sub={t('projects_dashboard.at_risk_sub')} />
          <KpiCard icon={<AlertTriangle size={16} />} label={t('projects_dashboard.kpi_open_risks')} value={risks.length}
            danger={highRisks > 0} warning={highRisks === 0 && risks.length > 0}
            sub={highRisks > 0 ? `${highRisks} ${t('projects_dashboard.high_severity_sub')}` : undefined} />
          <KpiCard icon={<ListTodo size={16} />} label={t('projects_dashboard.kpi_overdue_tasks')} value={overdue} warning={overdue > 0} />
        </div>

        {/* Gauges */}
        <div className="pdash-grid">
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
        <div className="pdash-grid-2">
          <SectionCard title={t('projects_dashboard.section_by_type')}>
            {byType.length === 0
              ? <EmptyState icon={<PieChart size={28} />} title={t('projects_dashboard.no_type_data')} description={t('projects_dashboard.no_type_data_desc')} />
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
              ? <EmptyState icon={<BarChart3 size={28} />} title={t('projects_dashboard.no_status_data')} description={t('projects_dashboard.no_status_data_desc')} />
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
                  const grave = budPct > 100
                  const RiskIcon = grave ? AlertOctagon : AlertCircle
                  return (
                    <div key={p.project_id} className={`ds-card--inset pdash-critico${grave ? ' pdash-critico--grave' : ''}`}>
                      <RiskIcon size={16} className="pdash-critico__icono" aria-hidden />
                      <div className="u-flex1-min0">
                        <div className="pdash-critico__nombre">
                          {p.project_code && <span className="pdash-critico__codigo">{p.project_code}</span>}
                          {p.project_name}
                        </div>
                        <div className="ds-muted">
                          {t('projects_dashboard.budget_label')}: {budPct}% · {t('projects_dashboard.deviation_label')}: {(p.schedule_deviation_days ?? 0) > 0 ? t('projects_dashboard.desviacion_dias', { n: p.schedule_deviation_days ?? 0 }) : t('projects_dashboard.deviation_ok')}
                        </div>
                      </div>
                      <StatusBadge kind={grave ? 'danger' : 'warning'} caps={false}>{budPct}%</StatusBadge>
                    </div>
                  )
                })}
            </div>
          </SectionCard>
        )}
      </div>
    </PageShell>
  )
}
