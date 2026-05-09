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

const ROLE_LABELS = {
  admin: 'Admin',
  pm: 'PM',
  team_lead: 'Team Lead',
  employee: 'Empleado',
  hr: 'RRHH',
  finance: 'Finanzas',
  client_user: 'Cliente',
}

const okrCategory = (o) => {
  if (o.status === 'cancelled') return 'cancelled'
  if (o.status === 'completed' || (o.progress_pct ?? 0) >= 100) return 'completed'
  if ((o.progress_pct ?? 0) > 0 || o.status === 'in_progress') return 'in_progress'
  return 'pending'
}

export default function TeamDashboardPage() {
  const [days, setDays] = useState(30)
  const params = dateRange(days)

  const { data: resources = [], isLoading: lr } = useQuery({
    queryKey: ['team-dash-resources'],
    queryFn: () => usersApi.list({ page_size: 200 }).then(r => {
      const d = r.data; return Array.isArray(d) ? d : (d?.items || [])
    }).catch(() => []),
    staleTime: 60_000,
  })

  const { data: utilData } = useQuery({
    queryKey: ['team-dash-util', days],
    queryFn: () => analyticsApi.utilization(params).then(r => r.data).catch(() => null),
    staleTime: 60_000,
  })

  const { data: okrs = [] } = useQuery({
    queryKey: ['team-dash-okrs'],
    queryFn: () => okrsApi.list({ page_size: 100 }).then(r => {
      const d = r.data; return Array.isArray(d) ? d : (d?.items || [])
    }).catch(() => []),
    staleTime: 60_000,
  })

  const { data: perfReviews = [] } = useQuery({
    queryKey: ['team-dash-perf'],
    queryFn: () => performanceApi.myReviews().then(r => {
      const d = r.data; return Array.isArray(d) ? d : (d?.items || [])
    }).catch(() => []),
    staleTime: 60_000,
  })

  const { data: trainings = [] } = useQuery({
    queryKey: ['team-dash-training'],
    queryFn: () => trainingApi.enrollments().then(r => {
      const d = r.data; return Array.isArray(d) ? d : (d?.items || [])
    }).catch(() => []),
    staleTime: 60_000,
  })

  const { data: absences = [] } = useQuery({
    queryKey: ['team-dash-absences'],
    queryFn: () => absencesApi.list({ page_size: 100 }).then(r => {
      const d = r.data; return Array.isArray(d) ? d : (d?.items || [])
    }).catch(() => []),
    staleTime: 60_000,
  })

  if (lr) return (
    <div style={{ padding: 32, display: 'flex', justifyContent: 'center', minHeight: 300, alignItems: 'center' }}>
      <Spinner />
    </div>
  )

  const teamSize   = resources.length
  const utilPct    = utilData?.avg_utilization_pct != null ? Math.round(utilData.avg_utilization_pct) : null
  const utilColor  = utilPct == null ? COLOR.accent : utilPct >= 70 ? COLOR.success : utilPct >= 50 ? COLOR.warning : COLOR.danger

  const totalOkrs      = okrs.length
  const okrBuckets     = okrs.reduce((acc, o) => {
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

  const deptCounts = resources.reduce((acc, r) => {
    const dept = r.department || 'Sin departamento'
    acc[dept] = (acc[dept] || 0) + 1; return acc
  }, {})
  const deptRows = Object.entries(deptCounts)
    .sort((a, b) => b[1] - a[1])
    .slice(0, 6)
    .map(([dept, count]) => ({ label: dept, count }))

  const roleCounts = resources.reduce((acc, r) => {
    const role = r.role || r.job_title || 'Sin rol'
    acc[role] = (acc[role] || 0) + 1; return acc
  }, {})
  const roleRows = Object.entries(roleCounts)
    .sort((a, b) => b[1] - a[1])
    .slice(0, 6)
    .map(([role, count]) => ({ label: ROLE_LABELS[role] || role, count }))

  return (
    <DashPageShell
      icon={<Users size={18} />}
      title="Equipo y Personas"
      subtitle="Métricas de capacidad, rendimiento y desarrollo del equipo"
      days={days} setDays={setDays}
      periods={[30, 90, 365]}
    >
      <div className="ds-page">
        {/* KPI row */}
        <div className="ds-grid-stats">
          <KpiCard icon={<KpiIcon icon={Users} />} label="Personas en equipo"
            value={teamSize} color="var(--text-1)" accentBar={COLOR.accent} />
          <KpiCard icon={<KpiIcon icon={Target} />} label="OKRs activos"
            value={totalOkrs} color={COLOR.purple} accentBar={COLOR.purple}
            sub={completedOkrs > 0 ? `${completedOkrs} completados` : undefined} />
          <KpiCard icon={<KpiIcon icon={Star} />} label="Reviews pendientes"
            value={pendingReviews}
            color={pendingReviews > 0 ? COLOR.warning : COLOR.success}
            accentBar={pendingReviews > 0 ? COLOR.warning : COLOR.success}
            sub={completedReviews > 0 ? `${completedReviews} completadas` : undefined} />
          <KpiCard icon={<KpiIcon icon={GraduationCap} />} label="Formaciones"
            value={trainingTotal}
            color={COLOR.accent} accentBar={COLOR.accent}
            sub={`${trainingCompleted} completadas · ${trainingInProgress} en curso`} />
          <KpiCard icon={<KpiIcon icon={Plane} />} label="Ausencias hoy"
            value={todayAbsences}
            color={todayAbsences > 0 ? COLOR.warning : COLOR.success}
            accentBar={todayAbsences > 0 ? COLOR.warning : COLOR.success} />
          <KpiCard icon={<KpiIcon icon={Zap} />} label="Ausencias pendientes"
            value={absences.filter(a => a.status === 'pending').length}
            color={COLOR.purple} accentBar={COLOR.purple} />
        </div>

        {/* Gauges */}
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: 'var(--space-3)' }}>
          {utilPct != null && (
            <GaugeCard label="Utilización media equipo"
              value={utilPct} color={utilColor}
              sub={utilPct >= 70 ? 'Buen aprovechamiento' : utilPct >= 50 ? 'Capacidad disponible' : 'Baja ocupación'} />
          )}
          {okrPct != null && (
            <GaugeCard label="OKRs completados"
              value={okrPct} color={okrColor}
              sub={`${completedOkrs} de ${totalOkrs} objetivos`} />
          )}
          {trainingTotal > 0 && (
            <GaugeCard label="Formación completada"
              value={Math.round((trainingCompleted / trainingTotal) * 100)}
              color={COLOR.success}
              sub={`${trainingCompleted} de ${trainingTotal} formaciones`} />
          )}
        </div>

        {/* Distribution charts */}
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))', gap: 'var(--space-3)' }}>
          <SectionCard title="Distribución por departamento" badge={deptRows.length}>
            {deptRows.length === 0
              ? <DashEmpty title="Sin departamentos definidos" />
              : deptRows.map((row, i) => (
                  <BarRow key={row.label}
                    label={row.label} count={row.count}
                    total={Math.max(teamSize, 1)}
                    color={typePalette[i % typePalette.length]} />
                ))
            }
          </SectionCard>

          <SectionCard title="Distribución por rol" badge={roleRows.length}>
            {roleRows.length === 0
              ? <DashEmpty title="Sin roles definidos" />
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
          <SectionCard title="Estado de OKRs" badge={totalOkrs}>
            {(() => {
              const groups = [
                { label: 'Completados', count: okrBuckets.completed   || 0, color: COLOR.success },
                { label: 'En progreso', count: okrBuckets.in_progress || 0, color: COLOR.accent },
                { label: 'Sin iniciar', count: okrBuckets.pending     || 0, color: 'var(--text-3)' },
                { label: 'Cancelados',  count: okrBuckets.cancelled   || 0, color: COLOR.danger },
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
