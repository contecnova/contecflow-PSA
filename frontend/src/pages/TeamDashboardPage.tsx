import type React from 'react'
import { useQuery } from '@tanstack/react-query'
import { usersApi, analyticsApi, okrsApi, performanceApi, trainingApi, absencesApi } from '../services/api'
import type { Objetivo } from '../services/api/tipos-proyectos'
import { Spinner, KpiCard, EmptyState, Card, Section, StatusBadge } from '../components/ui'
import PageShell from '../components/layout/PageShell'
import PageHeader from '../components/layout/PageHeader'
import {
  Users, Target, Star, GraduationCap, Plane, CalendarClock, Building2, BadgeCheck,
} from 'lucide-react'
import { COLOR, GaugeCard, BarRow, typePalette } from '../components/dashboard/DashKit'
import { useAppT } from '../i18n/AppLangContext'
import { STALE_DEFAULT_MS } from '../constants/timings'
import { DASHBOARD_LIST_SIZE, SELECTOR_LIST_SIZE } from '../constants/pagination'
// 19-11-2026: etiqueta del rol con `rol_usuario` (la lista local tenía roles inexistentes: finance, client_user).
import { etiquetaCodigo } from '../i18n/etiquetaCodigo'
import './TeamDashboardPage.css'

/*
 * 16-11-2026: cabecera con el nombre del menú (nav.team_dashboard), KPIs con el
 * KpiCard común (antes los de DashKit con barra superior de color), secciones con
 * Card + Section y vacíos con EmptyState e icono lucide (antes DashEmpty con emoji).
 */

interface TeamUser {
  status?: string
  department?: string
  role?: string
  job_title?: string
}

interface ChartRow {
  label: string
  count: number
}

// okr_service.serialize_objective: `progress` (0-100) y OKRStatus (draft/active/completed/cancelled).
const okrCategory = (o: Objetivo) => {
  if (o.status === 'cancelled') return 'cancelled'
  if (o.status === 'completed' || o.progress >= 100) return 'completed'
  if (o.progress > 0 || o.status === 'active') return 'in_progress'
  return 'pending'
}

export default function TeamDashboardPage() {
  const t = useAppT()

  const { data: resourcesRaw = [], isLoading: lr } = useQuery({
    queryKey: ['team-dash-resources'],
    queryFn: () => usersApi.list({ page_size: SELECTOR_LIST_SIZE }).then(r => {
      return r.data ?? []
    }),
    staleTime: STALE_DEFAULT_MS,
  })
  const resources = resourcesRaw as TeamUser[]

  const { data: utilData = null } = useQuery({
    // La utilización es de la semana en curso: el endpoint no admite periodo
    // (revisión 2026-11: se leía un campo que no existe y nunca se veía).
    queryKey: ['team-dash-util'],
    queryFn: () => analyticsApi.utilization().then(r => r.data),
    staleTime: STALE_DEFAULT_MS,
  })

  const { data: okrs = [] } = useQuery({
    queryKey: ['team-dash-okrs'],
    queryFn: () => okrsApi.list({ page_size: DASHBOARD_LIST_SIZE }).then(r => r.data),
    staleTime: STALE_DEFAULT_MS,
  })

  const { data: perfReviews = [] } = useQuery({
    queryKey: ['team-dash-perf'],
    queryFn: () => performanceApi.myReviews().then(r => r.data),
    staleTime: STALE_DEFAULT_MS,
  })

  const { data: trainings = [] } = useQuery({
    queryKey: ['team-dash-training'],
    queryFn: () => trainingApi.enrollments({ page_size: DASHBOARD_LIST_SIZE }).then(r => r.data),
    staleTime: STALE_DEFAULT_MS,
  })

  const { data: absences = [] } = useQuery({
    queryKey: ['team-dash-absences'],
    // `todasLasPaginas` siempre devuelve el array ya desenvuelto.
    queryFn: () => absencesApi.list({ page_size: DASHBOARD_LIST_SIZE }).then(r => r.data),
    staleTime: STALE_DEFAULT_MS,
  })

  const header = (
    <PageHeader
      icon={<Users size={18} />}
      title={t('nav.team_dashboard')}
      subtitle={t('team_dashboard.subtitle')}
      showListExport={false}
    />
  )

  if (lr) return (
    <PageShell>
      {header}
      <div className="tdp-loading" role="status" aria-busy="true">
        <Spinner />
      </div>
    </PageShell>
  )

  const teamSize   = resources.length
  const utilPct    = utilData?.summary?.actual_utilization_pct != null ? Math.round(utilData.summary.actual_utilization_pct) : null
  const utilColor  = utilPct == null ? COLOR.accent : utilPct >= 70 ? COLOR.success : utilPct >= 50 ? COLOR.warning : COLOR.danger

  const totalOkrs      = okrs.length
  const okrBuckets     = okrs.reduce<Record<string, number>>((acc, o) => {
    const cat = okrCategory(o)
    acc[cat] = (acc[cat] || 0) + 1
    return acc
  }, {})
  const completedOkrs  = okrBuckets.completed || 0
  const okrPct         = totalOkrs > 0 ? Math.round((completedOkrs / totalOkrs) * 100) : null
  const okrColor       = okrPct == null ? COLOR.accent : okrPct >= 70 ? COLOR.success : okrPct >= 40 ? COLOR.warning : COLOR.danger

  // Las evaluaciones que te tocan rellenar (/performance/my-reviews); los estados son pending | submitted | approved.
  const pendingReviews   = perfReviews.filter(r => r.status === 'pending').length

  const trainingCompleted  = trainings.filter(t => t.status === 'completed').length
  const trainingInProgress = trainings.filter(t => t.status === 'in_progress').length
  const trainingTotal      = trainings.length

  const todayAbsences = absences.filter(a => {
    const today = new Date().toISOString().slice(0, 10)
    return Boolean(a.start_date && a.end_date) && a.start_date! <= today && a.end_date! >= today && a.status === 'approved'
  }).length

  const deptCounts = resources.reduce<Record<string, number>>((acc, r) => {
    const dept = r.department || t('team_dashboard.no_department')
    acc[dept] = (acc[dept] || 0) + 1; return acc
  }, {})
  const deptRows: ChartRow[] = Object.entries(deptCounts)
    .sort((a, b) => b[1] - a[1])
    .slice(0, 6)
    .map(([dept, count]) => ({ label: dept, count }))

  const roleCounts = resources.reduce<Record<string, number>>((acc, r) => {
    const role = r.role || r.job_title || t('team_dashboard.no_role')
    acc[role] = (acc[role] || 0) + 1; return acc
  }, {})
  const roleRows: ChartRow[] = Object.entries(roleCounts)
    .sort((a, b) => b[1] - a[1])
    .slice(0, 6)
    .map(([role, count]) => ({ label: etiquetaCodigo(t as never, 'rol_usuario', role), count }))

  const pendingAbsences = absences.filter(a => a.status === 'pending').length

  const seccion = (titulo: string, n: number | null, cuerpo: React.ReactNode) => (
    <Card>
      <Section title={titulo} actions={n != null ? <StatusBadge kind="neutral" caps={false}>{n}</StatusBadge> : undefined}>
        {cuerpo}
      </Section>
    </Card>
  )

  return (
    <PageShell>
      {header}
      <div className="ds-page">
        <div className="ds-grid-stats">
          <KpiCard icon={<Users size={16} />} label={t('team_dashboard.kpi_team_size')} value={teamSize} />
          <KpiCard icon={<Target size={16} />} label={t('team_dashboard.kpi_active_okrs')} value={totalOkrs}
            sub={completedOkrs > 0 ? `${completedOkrs} ${t('team_dashboard.completed_lower')}` : undefined} />
          <KpiCard icon={<Star size={16} />} label={t('team_dashboard.kpi_pending_reviews')}
            value={pendingReviews} warning={pendingReviews > 0} />
          <KpiCard icon={<GraduationCap size={16} />} label={t('team_dashboard.kpi_trainings')} value={trainingTotal}
            sub={t('team_dashboard.trainings_sub', { completadas: trainingCompleted, en_curso: trainingInProgress })} />
          <KpiCard icon={<Plane size={16} />} label={t('team_dashboard.kpi_absences_today')}
            value={todayAbsences} warning={todayAbsences > 0} />
          <KpiCard icon={<CalendarClock size={16} />} label={t('team_dashboard.kpi_pending_absences')}
            value={pendingAbsences} warning={pendingAbsences > 0} />
        </div>

        {(utilPct != null || okrPct != null || trainingTotal > 0) && (
          <div className="tdp-gauges">
            {utilPct != null && (
              <GaugeCard label={t('team_dashboard.gauge_avg_utilization')}
                value={utilPct} color={utilColor}
                sub={utilPct >= 70 ? t('team_dashboard.good_use') : utilPct >= 50 ? t('team_dashboard.capacity_available') : t('team_dashboard.low_occupancy')} />
            )}
            {okrPct != null && (
              <GaugeCard label={t('team_dashboard.gauge_okrs_completed')}
                value={okrPct} color={okrColor}
                sub={t('team_dashboard.okrs_sub', { completados: completedOkrs, total: totalOkrs })} />
            )}
            {trainingTotal > 0 && (
              <GaugeCard label={t('team_dashboard.gauge_training_completed')}
                value={Math.round((trainingCompleted / trainingTotal) * 100)}
                color={COLOR.success}
                sub={t('team_dashboard.trainings_gauge_sub', { completadas: trainingCompleted, total: trainingTotal })} />
            )}
          </div>
        )}

        <div className="tdp-sections">
          {seccion(t('team_dashboard.section_by_department'), deptRows.length,
            deptRows.length === 0
              ? <EmptyState icon={<Building2 size={28} />} title={t('team_dashboard.no_departments')} description={t('team_dashboard.no_departments_desc')} />
              : deptRows.map((row, i) => (
                  <BarRow key={row.label}
                    label={row.label} count={row.count}
                    total={Math.max(teamSize, 1)}
                    color={typePalette[i % typePalette.length]} />
                )))}

          {seccion(t('team_dashboard.section_by_role'), roleRows.length,
            roleRows.length === 0
              ? <EmptyState icon={<BadgeCheck size={28} />} title={t('team_dashboard.no_roles')} description={t('team_dashboard.no_roles_desc')} />
              : roleRows.map((row, i) => (
                  <BarRow key={row.label}
                    label={row.label} count={row.count}
                    total={Math.max(teamSize, 1)}
                    color={typePalette[(i + 2) % typePalette.length]} />
                )))}
        </div>

        {okrs.length > 0 && seccion(t('team_dashboard.section_okr_status'), totalOkrs,
          [
            { label: t('team_dashboard.okr_completed'), count: okrBuckets.completed   || 0, color: COLOR.success },
            { label: t('team_dashboard.okr_in_progress'), count: okrBuckets.in_progress || 0, color: COLOR.accent },
            { label: t('team_dashboard.okr_not_started'), count: okrBuckets.pending     || 0, color: 'var(--text-3)' },
            { label: t('team_dashboard.okr_cancelled'),  count: okrBuckets.cancelled   || 0, color: COLOR.danger },
          ].filter(g => g.count > 0).map(g => (
            <BarRow key={g.label} label={g.label}
              count={g.count} total={Math.max(totalOkrs, 1)} color={g.color} />
          )))}
      </div>
    </PageShell>
  )
}
