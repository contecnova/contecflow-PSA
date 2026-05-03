import { useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import api from '../services/api'
import { Clock, Plus, Timer, Ticket } from 'lucide-react'
import { useToast } from '../context/ToastContext'
import { useAuth } from '../context/AuthContext'
import {
  COLOR, DashPageShell, KpiCard, KpiCardSkeleton, GaugeCard, GaugeCardSkeleton, BarRow, SectionCard, DashEmpty,
  dateRange, typePalette,
} from '../components/dashboard/DashKit'

function startOfWeekIso() {
  const d = new Date()
  const dow = (d.getDay() + 6) % 7 // Monday-based
  d.setDate(d.getDate() - dow)
  return d.toISOString().slice(0, 10)
}

function startOfMonthIso() {
  const d = new Date()
  d.setDate(1)
  return d.toISOString().slice(0, 10)
}

const SHORT_MONTH = { month: 'short', day: 'numeric' }
function fmtShort(dateStr) {
  return new Intl.DateTimeFormat('es-ES', SHORT_MONTH).format(new Date(dateStr + 'T12:00:00'))
}

function weekDateRangeLabel() {
  const from = startOfWeekIso()
  const to = new Date().toISOString().slice(0, 10)
  if (from.slice(0, 7) === to.slice(0, 7)) return null // same month, no label needed
  return `${fmtShort(from)} – ${fmtShort(to)}`
}

function totalCountFrom(response) {
  const total = response?.headers?.['x-total-count']
  const parsed = Number(total)
  return Number.isFinite(parsed) ? parsed : 0
}

const TREND_MIN_BASELINE_HOURS = 8

function formatTrendDelta(delta) {
  if (!Number.isFinite(delta) || delta === 0) return '0.0h'
  return `${delta > 0 ? '+' : ''}${delta.toFixed(1)}h`
}

function formatTrendPct(deltaPct, baseline) {
  if (!Number.isFinite(deltaPct)) {
    return baseline > 0 ? 'Base baja' : 'Nuevo registro'
  }
  return `${deltaPct > 0 ? '+' : ''}${deltaPct}%`
}

function TodayBanner({ navigate }) {
  const now = new Date()
  const day = new Intl.DateTimeFormat('es-ES', { weekday: 'long' }).format(now)
  const date = new Intl.DateTimeFormat('es-ES', { day: 'numeric', month: 'long' }).format(now)
  const hour = now.getHours()
  const greeting = hour < 13 ? 'Buenos días' : hour < 20 ? 'Buenas tardes' : 'Buenas noches'

  const ACTIONS = [
    { label: 'Nueva tarea',    icon: Plus,   path: '/tasks',        accent: 'var(--accent)' },
    { label: 'Imputar horas',  icon: Clock,  path: '/time',         accent: 'var(--success)' },
    { label: 'Nuevo ticket',   icon: Ticket, path: '/service-desk', accent: 'var(--warning)' },
    { label: 'Cronómetro',     icon: Timer,  path: '/time',         accent: 'var(--purple)' },
  ]

  return (
    <div style={{
      background: 'var(--surface-2)', border: '1px solid var(--surface-4)',
      borderRadius: 12, padding: '18px 22px', marginBottom: 18,
      display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 20, flexWrap: 'wrap',
    }}>
      <div>
        <div style={{ fontSize: "var(--text-sm)", color: 'var(--text-3)', fontWeight: 500, textTransform: 'capitalize', marginBottom: 2 }}>
          {greeting} · {day}, {date}
        </div>
        <div style={{ fontSize: "var(--text-lg-em)", fontWeight: 800, color: 'var(--text-1)' }}>¿Qué hacemos hoy?</div>
      </div>
      <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
        {ACTIONS.map(({ label, icon: Icon, path, accent }) => (
          <button key={label} onClick={() => navigate(path)} style={{
            display: 'flex', alignItems: 'center', gap: 6,
            padding: '8px 14px', borderRadius: 8,
            background: `${accent}12`, border: `1px solid ${accent}35`,
            color: accent, cursor: 'pointer', fontSize: "var(--text-sm)", fontWeight: 600,
            fontFamily: 'inherit', transition: 'all 0.1s', whiteSpace: 'nowrap',
          }}
            onMouseEnter={e => { e.currentTarget.style.background = `${accent}22`; e.currentTarget.style.borderColor = `${accent}60` }}
            onMouseLeave={e => { e.currentTarget.style.background = `${accent}12`; e.currentTarget.style.borderColor = `${accent}35` }}
          >
            <Icon size={13} />{label}
          </button>
        ))}
      </div>
    </div>
  )
}

export default function WorkDashboardPage() {
  const navigate = useNavigate()
  const toast = useToast()
  const { user } = useAuth()
  const userId = user?.id

  const { data: taskStats, isLoading: lt, isError: taskStatsError } = useQuery({
    queryKey: ['work-dash-task-stats', userId],
    queryFn: async () => {
      const [openRes, overdueRes, doneRes] = await Promise.all([
        api.get('/tasks', {
          params: {
            assigned_to_me: true,
            status: 'backlog,todo,in_progress,blocked,in_review,review',
            page_size: 1,
          },
        }),
        api.get('/tasks', {
          params: {
            assigned_to_me: true,
            overdue_only: true,
            page_size: 1,
          },
        }),
        api.get('/tasks', {
          params: {
            assigned_to_me: true,
            status: 'done',
            page_size: 1,
          },
        }),
      ])

      return {
        open: totalCountFrom(openRes),
        overdue: totalCountFrom(overdueRes),
        done: totalCountFrom(doneRes),
      }
    },
    enabled: !!userId,
    staleTime: 60_000,
    retry: 1,
  })

  const { data: myWeekHours = 0 } = useQuery({
    queryKey: ['work-dash-my-week', userId],
    queryFn: () => api.get('/analytics/query/hours_by_week', {
      params: { user_id: userId, date_from: startOfWeekIso(), date_to: new Date().toISOString().slice(0, 10) },
    }).then(r => (r.data?.rows || []).reduce((s, x) => s + (x.value || 0), 0)).catch(() => 0),
    enabled: !!userId,
    staleTime: 60_000,
  })

  const { data: myMonthHours = null } = useQuery({
    queryKey: ['work-dash-my-month', userId],
    queryFn: () => api.get('/analytics/query/hours_by_week', {
      params: { user_id: userId, date_from: startOfMonthIso(), date_to: new Date().toISOString().slice(0, 10) },
    }).then(r => (r.data?.rows || []).reduce((s, x) => s + (x.value || 0), 0)).catch(() => null),
    enabled: !!userId,
    staleTime: 60_000,
  })

  const { data: approvals = [], isLoading: la } = useQuery({
    queryKey: ['work-dash-approvals'],
    queryFn: () => api.get('/approvals/requests/pending-my-action').then(r => {
      const d = r.data; return Array.isArray(d) ? d : (d?.items || [])
    }).catch(e => { console.error('Error loading approvals:', e); return [] }),
    staleTime: 60_000,
  })

  const { data: expenses = [], isLoading: le } = useQuery({
    queryKey: ['work-dash-expenses'],
    queryFn: () => api.get('/expenses/my', { params: { status: 'pending' } }).then(r => {
      const d = r.data; return Array.isArray(d) ? d : (d?.items || [])
    }).catch(e => { console.error('Error loading expenses:', e); return [] }),
    staleTime: 60_000,
  })

  const { data: hoursData = [] } = useQuery({
    queryKey: ['work-dash-hours-trend', userId],
    queryFn: () => api.get('/analytics/query/hours_by_month', {
      params: { ...dateRange(180), ...(userId ? { user_id: userId } : {}) },
    }).then(r => r.data?.rows || []).catch(e => {
      console.error('Error loading hours data:', e); return []
    }),
    enabled: !!userId,
    staleTime: 60_000,
  })

  const { data: absences = [], isLoading: lab } = useQuery({
    queryKey: ['work-dash-absences'],
    queryFn: () => api.get('/absences/my').then(r => {
      const d = r.data; return Array.isArray(d) ? d : (d?.items || [])
    }).catch(e => { console.error('Error loading absences:', e); return [] }),
    staleTime: 60_000,
  })

  useEffect(() => {
    if (taskStatsError) toast.error('No se pudieron cargar las métricas personales del dashboard')
  }, [taskStatsError]) // eslint-disable-line react-hooks/exhaustive-deps

  const tasksOpen    = taskStats?.open ?? 0
  const tasksOverdue = taskStats?.overdue ?? 0
  const tasksDone    = taskStats?.done ?? 0
  const hoursWeek    = myWeekHours || 0
  const pendingApprv = approvals.length
  const pendingExp   = expenses.length
  const pendingAbsences = absences.filter(a => a.status === 'pending').length

  const hoursTarget  = user?.weekly_capacity_hours ?? 40
  const hoursWeekPct = Math.min(Math.round((hoursWeek / Math.max(hoursTarget, 1)) * 100), 100)
  const hoursColor   = hoursWeekPct >= 80 ? COLOR.success : hoursWeekPct >= 50 ? COLOR.warning : COLOR.danger
  const taskCompletionBase = tasksOpen + tasksDone
  const taskCompletionPct = taskCompletionBase > 0 ? Math.round((tasksDone / taskCompletionBase) * 100) : 100

  const last  = hoursData[hoursData.length - 1]?.value || 0
  const prev  = hoursData[hoursData.length - 2]?.value || 0
  const totalHoursMonth = myMonthHours !== null ? myMonthHours : last
  const hoursTrendRows = hoursData.slice(-6).map((row, index, rows) => {
    const previousValue = index > 0 ? (rows[index - 1]?.value || 0) : null
    const currentValue = row.value || 0
    const delta = previousValue == null ? 0 : currentValue - previousValue
    const hasStableBaseline = previousValue != null && previousValue >= TREND_MIN_BASELINE_HOURS
    const deltaPct = hasStableBaseline
      ? Math.round((delta / previousValue) * 100)
      : null

    return {
      label: row.label || `Mes ${index + 1}`,
      hours: currentValue,
      delta,
      deltaPct,
      hasBaseline: previousValue != null,
      hasStableBaseline,
      color: previousValue == null
        ? COLOR.accent
        : delta > 0
          ? COLOR.success
          : delta < 0
            ? COLOR.danger
            : COLOR.warning,
    }
  })
  const maxTrendHours = Math.max(...hoursTrendRows.map(row => row.hours || 0), 1)
  const hoursBarFill = 'var(--accent)'

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
      showPeriodSuffix={false}
    >
      <TodayBanner navigate={navigate} />
      {/* KPI row — skeletons while loading */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(160px, 1fr))', gap: 14, marginBottom: 14 }}>
        {(lt || la || le || lab) ? Array.from({ length: 6 }).map((_, i) => <KpiCardSkeleton key={i} />) : <>
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
          sub={weekDateRangeLabel() ? `${weekDateRangeLabel()} · Obj: ${hoursTarget}h` : `Objetivo: ${hoursTarget}h`}
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
          sub={pendingApprv > 0 ? 'Pendientes de mi acción' : 'Sin pendientes'}
          action={pendingApprv > 0 ? { label: 'Revisar', to: '/approvals' } : undefined} />
        <KpiCard icon="💸" label="Gastos pendientes"
          value={pendingExp}
          color={pendingExp > 0 ? COLOR.purple : COLOR.success}
          accentBar={COLOR.purple}
          sub={pendingExp > 0 ? 'Mis gastos por aprobar' : 'Sin gastos pendientes'}
          action={pendingExp > 0 ? { label: 'Ver gastos', to: '/expenses' } : undefined} />
        </>}
      </div>

      {/* Gauge + activity */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: 14, marginBottom: 20 }}>
        {(lt || la || le || lab) ? <><GaugeCardSkeleton /><GaugeCardSkeleton /></> : <>
        <GaugeCard label="Horas semana / objetivo"
          value={hoursWeekPct} color={hoursColor}
          sub={`${hoursWeek.toFixed(1)}h de ${hoursTarget}h objetivo`} />
        <GaugeCard label="Tareas completadas"
          value={taskCompletionPct}
          color={COLOR.success}
          sub="Ratio de resolución de tareas" />
        </>}
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

        <SectionCard title="Tendencia de horas (mensual)">
          {hoursTrendRows.length === 0
            ? <DashEmpty icon="⏱" title="Sin datos de horas" />
            : hoursTrendRows.map((row, i) => (
                <div key={row.label || i} style={{ marginBottom: i === hoursTrendRows.length - 1 ? 0 : 14 }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 6, gap: 12 }}>
                    <div>
                      <div style={{ fontSize: "var(--text-sm)", color: 'var(--text-2)', fontWeight: 600 }}>
                        {row.label}
                      </div>
                      <div style={{ fontSize: "var(--text-xs)", color: 'var(--text-3)' }}>
                        {row.hours.toFixed(1)}h totales
                      </div>
                    </div>
                    <div style={{ textAlign: 'right' }}>
                      <div style={{ fontSize: "var(--text-xs)", fontWeight: 700, color: row.color }}>
                        {row.hasBaseline ? `${row.delta > 0 ? '↑' : row.delta < 0 ? '↓' : '→'} ${formatTrendPct(row.deltaPct, row.hours)}` : 'Base'}
                      </div>
                      <div style={{ fontSize: "var(--text-xs)", color: 'var(--text-3)' }}>
                        {row.hasBaseline
                          ? (row.hasStableBaseline
                            ? formatTrendDelta(row.delta)
                            : `${formatTrendDelta(row.delta)} · base < ${TREND_MIN_BASELINE_HOURS}h`)
                          : 'Primer mes comparable'}
                      </div>
                    </div>
                  </div>
                  <div style={{ height: 7, background: 'var(--surface-4)', borderRadius: 4, overflow: 'hidden' }}>
                    <div style={{
                      width: `${Math.max(6, Math.round((row.hours / maxTrendHours) * 100))}%`,
                      height: '100%',
                      background: hoursBarFill,
                      borderRadius: 4,
                      transition: 'width 0.6s cubic-bezier(0.4,0,0.2,1)',
                    }} />
                  </div>
                </div>
              ))
          }
        </SectionCard>
      </div>
    </DashPageShell>
  )
}
