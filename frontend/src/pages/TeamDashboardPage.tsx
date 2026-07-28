import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { usersApi, analyticsApi, okrsApi, performanceApi, trainingApi, absencesApi } from '../services/api'
import { Spinner } from '../components/ui'
import {
  Users, Target, Star, GraduationCap, Plane, Zap,
} from 'lucide-react'
import {
  COLOR, DashPageShell, KpiCard, KpiIcon, GaugeCard, BarRow, SectionCard, DashEmpty,
  dateRange, typePalette,
} from '../components/dashboard/DashKit'
import { useAppT } from '../i18n/AppLangContext'
import type { ComponentType } from 'react'

interface TeamUser {
  status?: string
  department?: string
  role?: string
  job_title?: string
}

interface UtilData {
  avg_utilization_pct?: number
}

interface OkrItem {
  status?: string
  progress_pct?: number
}

interface PerfReview {
  status?: string
}

interface TrainingItem {
  status?: string
}

interface AbsenceItem {
  start_date?: string
  end_date?: string
  status?: string
}

interface ChartRow {
  label: string
  count: number
}

const okrCategory = (o: OkrItem) => {
  if (o.status === 'cancelled') return 'cancelled'
  if (o.status === 'completed' || (o.progress_pct ?? 0) >= 100) return 'completed'
  if ((o.progress_pct ?? 0) > 0 || o.status === 'in_progress') return 'in_progress'
  return 'pending'
}

export default function TeamDashboardPage() {
  const t = useAppT()
  const ROLE_LABELS = {
    admin: t('team_dashboard.role_admin'),
    pm: t('team_dashboard.role_pm'),
    team_lead: t('team_dashboard.role_team_lead'),
    employee: t('team_dashboard.role_employee'),
    hr: t('team_dashboard.role_hr'),
    finance: t('team_dashboard.role_finance'),
    client_user: t('team_dashboard.role_client_user'),
  }
  const [days, setDays] = useState(30)
  const iconCompat = <T,>(icon: T) => icon as unknown as ComponentType<{ size?: number; strokeWidth?: number }>
  const params = dateRange(days)

  const { data: resourcesRaw = [], isLoading: lr } = useQuery({
    queryKey: ['team-dash-resources'],
    queryFn: () => usersApi.list({ page_size: 200 }).then(r => {
      return r.data ?? []
    }).catch(() => []),
    staleTime: 60_000,
  })
  const resources = resourcesRaw as TeamUser[]

  const { data: utilDataRaw } = useQuery({
    queryKey: ['team-dash-util', days],
    queryFn: () => analyticsApi.utilization(params).then(r => r.data).catch(() => null),
    staleTime: 60_000,
  })
  const utilData = (utilDataRaw ?? null) as UtilData | null

  const { data: okrsRaw = [] } = useQuery({
    queryKey: ['team-dash-okrs'],
    queryFn: () => okrsApi.list({ page_size: 100 }).then(r => {
      const d = r.data; return Array.isArray(d) ? d : (d?.items || [])
    }).catch(() => []),
    staleTime: 60_000,
  })
  const okrs = okrsRaw as OkrItem[]

  const { data: perfReviewsRaw = [] } = useQuery({
    queryKey: ['team-dash-perf'],
    queryFn: () => performanceApi.myReviews().then(r => {
      const d = r.data; return Array.isArray(d) ? d : (d?.items || [])
    }).catch(() => []),
    staleTime: 60_000,
  })
  const perfReviews = perfReviewsRaw as PerfReview[]

  const { data: trainingsRaw = [] } = useQuery({
    queryKey: ['team-dash-training'],
    queryFn: () => trainingApi.enrollments({ page_size: 100 }).then(r => {
      const d = r.data; return Array.isArray(d) ? d : (d?.items || [])
    }).catch(() => []),
    staleTime: 60_000,
  })
  const trainings = trainingsRaw as TrainingItem[]

  const { data: absencesRaw = [] } = useQuery({
    queryKey: ['team-dash-absences'],
    queryFn: () => absencesApi.list({ page_size: 100 }).then(r => {
      const d = r.data; return Array.isArray(d) ? d : (d?.items || [])
    }).catch(() => []),
    staleTime: 60_000,
  })
  const absences = absencesRaw as AbsenceItem[]

  if (lr) return (
    <div style={{ padding: 32, display: 'flex', justifyContent: 'center', minHeight: 300, alignItems: 'center' }}>
      <Spinner />
    </div>
  )

  const teamSize   = resources.length
  const utilPct    = utilData?.avg_utilization_pct != null ? Math.round(utilData.avg_utilization_pct) : null
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

  const pendingReviews   = perfReviews.filter(r => r.status === 'pending' || r.status === 'in_progress').length
  const completedReviews = perfReviews.filter(r => r.status === 'completed').length

  const trainingCompleted  = trainings.filter(t => t.status === 'completed').length
  const trainingInProgress = trainings.filter(t => t.status === 'in_progress').length
  const trainingTotal      = trainings.length

  const todayAbsences = absences.filter(a => {
    const today = new Date().toISOString().slice(0, 10)
    return a.start_date <= today && a.end_date >= today && a.status === 'approved'
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
    .map(([role, count]) => ({ label: ROLE_LABELS[role as keyof typeof ROLE_LABELS] || role, count }))

  return (
    <DashPageShell
      icon={<Users size={18} />}
      title={t('team_dashboard.title')}
      subtitle={t('team_dashboard.subtitle')}
      days={days} setDays={setDays}
      periods={[30, 90, 365]}
    >
      <div className="ds-page">
        {/* KPI row */}
        <div className="ds-grid-stats">
          <KpiCard icon={<KpiIcon icon={iconCompat(Users)} />} label={t('team_dashboard.kpi_team_size')}
            value={teamSize} color="var(--text-1)" accentBar={COLOR.accent} />
          <KpiCard icon={<KpiIcon icon={iconCompat(Target)} />} label={t('team_dashboard.kpi_active_okrs')}
            value={totalOkrs} color={COLOR.purple} accentBar={COLOR.purple}
            sub={completedOkrs > 0 ? `${completedOkrs} ${t('team_dashboard.completed_lower')}` : undefined} />
          <KpiCard icon={<KpiIcon icon={iconCompat(Star)} />} label={t('team_dashboard.kpi_pending_reviews')}
            value={pendingReviews}
            color={pendingReviews > 0 ? COLOR.warning : COLOR.success}
            accentBar={pendingReviews > 0 ? COLOR.warning : COLOR.success}
            sub={completedReviews > 0 ? `${completedReviews} ${t('team_dashboard.completed_fem_plural')}` : undefined} />
          <KpiCard icon={<KpiIcon icon={iconCompat(GraduationCap)} />} label={t('team_dashboard.kpi_trainings')}
            value={trainingTotal}
            color={COLOR.accent} accentBar={COLOR.accent}
            sub={`${trainingCompleted} ${t('team_dashboard.completed_fem_plural')} · ${trainingInProgress} ${t('team_dashboard.in_progress_lower')}`} />
          <KpiCard icon={<KpiIcon icon={iconCompat(Plane)} />} label={t('team_dashboard.kpi_absences_today')}
            value={todayAbsences}
            color={todayAbsences > 0 ? COLOR.warning : COLOR.success}
            accentBar={todayAbsences > 0 ? COLOR.warning : COLOR.success} />
          <KpiCard icon={<KpiIcon icon={iconCompat(Zap)} />} label={t('team_dashboard.kpi_pending_absences')}
            value={absences.filter(a => a.status === 'pending').length}
            color={COLOR.purple} accentBar={COLOR.purple} />
        </div>

        {/* Gauges */}
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: 'var(--space-3)' }}>
          {utilPct != null && (
            <GaugeCard label={t('team_dashboard.gauge_avg_utilization')}
              value={utilPct} color={utilColor}
              sub={utilPct >= 70 ? t('team_dashboard.good_use') : utilPct >= 50 ? t('team_dashboard.capacity_available') : t('team_dashboard.low_occupancy')} />
          )}
          {okrPct != null && (
            <GaugeCard label={t('team_dashboard.gauge_okrs_completed')}
              value={okrPct} color={okrColor}
              sub={`${completedOkrs} ${t('team_dashboard.of_word')} ${totalOkrs} ${t('team_dashboard.objectives')}`} />
          )}
          {trainingTotal > 0 && (
            <GaugeCard label={t('team_dashboard.gauge_training_completed')}
              value={Math.round((trainingCompleted / trainingTotal) * 100)}
              color={COLOR.success}
              sub={`${trainingCompleted} ${t('team_dashboard.of_word')} ${trainingTotal} ${t('team_dashboard.trainings_lower')}`} />
          )}
        </div>

        {/* Distribution charts */}
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))', gap: 'var(--space-3)' }}>
          <SectionCard title={t('team_dashboard.section_by_department')} badge={deptRows.length}>
            {deptRows.length === 0
              ? <DashEmpty title={t('team_dashboard.no_departments')} />
              : deptRows.map((row, i) => (
                  <BarRow key={row.label}
                    label={row.label} count={row.count}
                    total={Math.max(teamSize, 1)}
                    color={typePalette[i % typePalette.length]} />
                ))
            }
          </SectionCard>

          <SectionCard title={t('team_dashboard.section_by_role')} badge={roleRows.length}>
            {roleRows.length === 0
              ? <DashEmpty title={t('team_dashboard.no_roles')} />
              : roleRows.map((row, i) => (
                  <BarRow key={row.label}
                    label={row.label} count={row.count}
                    total={Math.max(teamSize, 1)}
                    color={typePalette[(i + 2) % typePalette.length]} />
                ))
            }
          </SectionCard>
        </div>

        {/* OKRs breakdown */}
        {okrs.length > 0 && (
          <SectionCard title={t('team_dashboard.section_okr_status')} badge={totalOkrs}>
            {(() => {
              const groups = [
                { label: t('team_dashboard.okr_completed'), count: okrBuckets.completed   || 0, color: COLOR.success },
                { label: t('team_dashboard.okr_in_progress'), count: okrBuckets.in_progress || 0, color: COLOR.accent },
                { label: t('team_dashboard.okr_not_started'), count: okrBuckets.pending     || 0, color: 'var(--text-3)' },
                { label: t('team_dashboard.okr_cancelled'),  count: okrBuckets.cancelled   || 0, color: COLOR.danger },
              ].filter(g => g.count > 0)
              return groups.map(g => (
                <BarRow key={g.label} label={g.label}
                  count={g.count} total={Math.max(totalOkrs, 1)} color={g.color} />
              ))
            })()}
          </SectionCard>
        )}
      </div>
    </DashPageShell>
  )
}
