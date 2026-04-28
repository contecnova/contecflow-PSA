import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import api from '../services/api'
import { Spinner } from '../components/ui'
import { Clock } from 'lucide-react'
import { useAppT } from '../i18n/AppLangContext'
import {
  COLOR, S, DashPageShell, KpiCard, GaugeCard, BarRow, SectionCard, DashEmpty,
  dateRange, typePalette,
} from '../components/dashboard/DashKit'

export default function WorkDashboardPage() {
  const t = useAppT()
  const [days, setDays] = useState(30)
  const params = dateRange(days)

  const { data: kpis, isLoading: lk } = useQuery({
    queryKey: ['work-dash-kpis', days],
    queryFn: () => api.get('/dashboard/kpis', { params }).then(r => r.data).catch(() => ({})),
    staleTime: 60_000,
  })

  const { data: approvals = [], isLoading: la } = useQuery({
    queryKey: ['work-dash-approvals'],
    queryFn: () => api.get('/approvals/requests', { params: { status: 'pending' } }).then(r => {
      const d = r.data; return Array.isArray(d) ? d : (d?.items || [])
    }).catch(() => []),
    staleTime: 60_000,
  })

  const { data: expenses = [] } = useQuery({
    queryKey: ['work-dash-expenses'],
    queryFn: () => api.get('/expenses', { params: { status: 'pending', page_size: 100 } }).then(r => {
      const d = r.data; return Array.isArray(d) ? d : (d?.items || [])
    }).catch(() => []),
    staleTime: 60_000,
  })

  const { data: hoursData = [] } = useQuery({
    queryKey: ['work-dash-hours', days],
    queryFn: () => api.get('/analytics/query/hours_by_month', { params }).then(r => r.data?.rows || []).catch(() => []),
    staleTime: 60_000,
  })

  const { data: absences = [] } = useQuery({
    queryKey: ['work-dash-absences'],
    queryFn: () => api.get('/absences', { params: { page_size: 100 } }).then(r => {
      const d = r.data; return Array.isArray(d) ? d : (d?.items || [])
    }).catch(() => []),
    staleTime: 60_000,
  })

  if (lk || la) return (
    <div style={{ padding: 32 }}>
      <div style={{ display: 'flex', justifyContent: 'center', minHeight: 300, alignItems: 'center' }}>
        <Spinner />
      </div>
    </div>
  )

  const tasksOpen    = kpis?.tasks_open ?? 0
  const tasksOverdue = kpis?.tasks_overdue ?? 0
  const hoursWeek    = kpis?.hours_logged_this_week ?? 0
  const pendingApprv = approvals.length
  const pendingExp   = expenses.length
  const pendingAbsences = absences.filter(a => a.status === 'pending').length

  const hoursTarget  = 40
  const hoursWeekPct = Math.min(Math.round((hoursWeek / hoursTarget) * 100), 100)
  const hoursColor   = hoursWeekPct >= 80 ? COLOR.success : hoursWeekPct >= 50 ? COLOR.warning : COLOR.danger

  const last  = hoursData[hoursData.length - 1]?.value || 0
  const prev  = hoursData[hoursData.length - 2]?.value || 0
  const totalHoursMonth = last

  const activityRows = [
    { label: 'Tareas abiertas',          count: tasksOpen,    color: COLOR.accent },
    { label: 'Tareas vencidas',          count: tasksOverdue, color: COLOR.danger },
    { label: 'Aprobaciones pendientes',  count: pendingApprv, color: COLOR.warning },
    { label: 'Gastos pendientes',        count: pendingExp,   color: COLOR.purple },
    { label: 'Ausencias pendientes',     count: pendingAbsences, color: 'var(--sky-blue)' },
  ]
  const totalActivity = activityRows.reduce((s, r) => s + r.count, 0)

  return (
    <DashPageShell
      icon={<Clock size={18} />}
      title="Mi Trabajo"
      subtitle="Métricas personales de actividad y productividad"
      days={days} setDays={setDays}
      periods={[7, 30, 90]}
    >
      {/* KPI row */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(160px, 1fr))', gap: 14, marginBottom: 14 }}>
        <KpiCard icon="✅" label="Tareas abiertas"
          value={tasksOpen}
          color={tasksOpen > 10 ? COLOR.warning : 'var(--text-1)'}
          accentBar={COLOR.accent}
          action={{ label: 'Ver tareas', to: '/tasks' }} />
        <KpiCard icon="⚠️" label="Tareas vencidas"
          value={tasksOverdue}
          color={tasksOverdue > 0 ? COLOR.danger : COLOR.success}
          accentBar={tasksOverdue > 0 ? COLOR.danger : COLOR.success}
          sub={tasksOverdue > 0 ? 'Requieren atención' : 'Todo al día'}
          action={tasksOverdue > 0 ? { label: 'Revisar vencidas', to: '/tasks' } : undefined} />
        <KpiCard icon="⏱" label="Horas esta semana"
          value={hoursWeek.toFixed(1)}
          color={hoursColor} accentBar={hoursColor}
          sub={`Objetivo: ${hoursTarget}h`}
          action={{ label: 'Imputar horas', to: '/imputar' }} />
        <KpiCard icon="📅" label={`Horas este mes`}
          value={totalHoursMonth.toFixed(1)}
          color={COLOR.accent} accentBar={COLOR.accent}
          sub={prev > 0 ? `Mes anterior: ${prev.toFixed(1)}h` : undefined}
          action={{ label: 'Ver timesheets', to: '/timesheets' }} />
        <KpiCard icon="🔔" label="Aprobaciones"
          value={pendingApprv}
          color={pendingApprv > 0 ? COLOR.warning : COLOR.success}
          accentBar={pendingApprv > 0 ? COLOR.warning : COLOR.success}
          sub={pendingApprv > 0 ? 'Pendientes de revisión' : 'Sin pendientes'}
          action={pendingApprv > 0 ? { label: 'Revisar', to: '/approvals' } : undefined} />
        <KpiCard icon="💸" label="Gastos pendientes"
          value={pendingExp}
          color={pendingExp > 0 ? COLOR.purple : COLOR.success}
          accentBar={COLOR.purple}
          sub={pendingExp > 0 ? 'Por aprobar' : 'Sin gastos pendientes'}
          action={pendingExp > 0 ? { label: 'Ver gastos', to: '/expenses' } : undefined} />
      </div>

      {/* Gauge + activity */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: 14, marginBottom: 20 }}>
        <GaugeCard label="Horas semana / objetivo"
          value={hoursWeekPct} color={hoursColor}
          sub={`${hoursWeek.toFixed(1)}h de ${hoursTarget}h objetivo`} />
        <GaugeCard label="Tareas completadas"
          value={kpis?.tasks_completion_pct ?? (tasksOpen > 0 ? Math.max(0, 100 - Math.round((tasksOverdue / tasksOpen) * 100)) : 100)}
          color={COLOR.success}
          sub="Ratio de resolución de tareas" />
      </div>

      {/* Activity breakdown */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))', gap: 14 }}>
        <SectionCard title="Resumen de actividad">
          {totalActivity === 0
            ? <DashEmpty icon="🎉" title="Todo en orden" description="No hay elementos pendientes" />
            : activityRows.map(row => (
                <BarRow key={row.label}
                  label={row.label} count={row.count}
                  total={Math.max(totalActivity, 1)} color={row.color} />
              ))
          }
        </SectionCard>

        <SectionCard title="Tendencia de horas (últimos meses)">
          {hoursData.length === 0
            ? <DashEmpty icon="⏱" title="Sin datos de horas" />
            : hoursData.slice(-6).map((row, i) => (
                <BarRow key={row.label || i}
                  label={row.label || `Mes ${i + 1}`}
                  count={row.value || 0}
                  total={Math.max(...hoursData.map(r => r.value || 0), 1)}
                  color={typePalette[i % typePalette.length]}
                  displayValue={`${(row.value || 0).toFixed(1)}h`} />
              ))
          }
        </SectionCard>
      </div>
    </DashPageShell>
  )
}
