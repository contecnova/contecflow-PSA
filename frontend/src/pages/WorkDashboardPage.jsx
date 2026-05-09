import { useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { tasksApi, analyticsApi, approvalsApi, expensesApi, absencesApi } from '../services/api'
import {
  Clock, Plus, Timer, Ticket, CheckCircle2, AlertTriangle, Calendar,
  Bell, Wallet, Plane, ArrowUpRight, ArrowDownRight, Minus, ArrowRight,
} from 'lucide-react'
import { useToast } from '../context/ToastContext'
import { useAuth } from '../context/AuthContext'
import {
  COLOR, DashPageShell, KpiCard, KpiIcon, KpiCardSkeleton, GaugeCard, GaugeCardSkeleton, BarRow, SectionCard, DashEmpty,
  dateRange,
} from '../components/dashboard/DashKit'

// ── Date helpers ────────────────────────────────────────────────────────────
function startOfWeekIso() {
  const d = new Date()
  const dow = (d.getDay() + 6) % 7
  d.setDate(d.getDate() - dow)
  return d.toISOString().slice(0, 10)
}
function startOfMonthIso() {
  const d = new Date()
  d.setDate(1)
  return d.toISOString().slice(0, 10)
}
function fmtShort(dateStr) {
  return new Intl.DateTimeFormat('es-ES', { month: 'short', day: 'numeric' }).format(new Date(dateStr + 'T12:00:00'))
}
function weekDateRangeLabel() {
  const from = startOfWeekIso()
  const to = new Date().toISOString().slice(0, 10)
  if (from.slice(0, 7) === to.slice(0, 7)) return null
  return `${fmtShort(from)} – ${fmtShort(to)}`
}
function totalCountFrom(response) {
  const total = response?.headers?.['x-total-count']
  const parsed = Number(total)
  return Number.isFinite(parsed) ? parsed : 0
}

const TREND_MIN_BASELINE_HOURS = 8
const formatTrendDelta = (delta) =>
  !Number.isFinite(delta) || delta === 0 ? '0.0h' : `${delta > 0 ? '+' : ''}${delta.toFixed(1)}h`
const formatTrendPct = (deltaPct, baseline) =>
  !Number.isFinite(deltaPct) ? (baseline > 0 ? 'Base baja' : 'Nuevo') : `${deltaPct > 0 ? '+' : ''}${deltaPct}%`

// ── Hero banner ─────────────────────────────────────────────────────────────
// Saludo + acciones rápidas. Sustituye "¿qué hacemos hoy?" por una versión
// más sobria con una CTA destacada y atajos secundarios.
function Hero({ navigate, userName }) {
  const now = new Date()
  const day = new Intl.DateTimeFormat('es-ES', { weekday: 'long' }).format(now)
  const date = new Intl.DateTimeFormat('es-ES', { day: 'numeric', month: 'long' }).format(now)
  const hour = now.getHours()
  const greeting = hour < 13 ? 'Buenos días' : hour < 20 ? 'Buenas tardes' : 'Buenas noches'

  const SHORTCUTS = [
    { label: 'Nueva tarea',   icon: Plus,   path: '/tasks' },
    { label: 'Imputar horas', icon: Clock,  path: '/imputar' },
    { label: 'Nuevo ticket',  icon: Ticket, path: '/service-desk' },
    { label: 'Cronómetro',    icon: Timer,  path: '/time' },
  ]

  return (
    <div className="ds-card" style={{
      gap: 'var(--space-4)',
      background: 'linear-gradient(135deg, var(--surface-2) 0%, var(--surface-3) 100%)',
    }}>
      <div className="ds-row-between" style={{ alignItems: 'flex-end', gap: 'var(--space-4)', flexWrap: 'wrap' }}>
        <div className="ds-stack-sm" style={{ minWidth: 0 }}>
          <div className="ds-eyebrow" style={{ textTransform: 'capitalize', letterSpacing: '0.06em' }}>
            {day} · {date}
          </div>
          <div style={{ fontSize: 'var(--text-2xl-em)', fontWeight: 800, color: 'var(--text-1)', letterSpacing: '-0.02em', lineHeight: 1.15 }}>
            {greeting}{userName ? `, ${userName.split(' ')[0]}` : ''}.
          </div>
        </div>
        <button
          onClick={() => navigate('/imputar')}
          style={{
            display: 'inline-flex', alignItems: 'center', gap: 'var(--space-2)',
            padding: '10px 18px', borderRadius: 'var(--radius-md)',
            background: 'var(--accent)', color: '#fff', border: 'none',
            fontSize: 'var(--text-sm)', fontWeight: 700, cursor: 'pointer',
            boxShadow: '0 1px 3px rgba(79,142,247,0.3)', whiteSpace: 'nowrap',
            transition: 'transform 0.1s var(--easing), box-shadow 0.15s var(--easing)',
          }}
          onMouseEnter={e => { e.currentTarget.style.boxShadow = '0 4px 12px rgba(79,142,247,0.4)' }}
          onMouseLeave={e => { e.currentTarget.style.boxShadow = '0 1px 3px rgba(79,142,247,0.3)' }}
        >
          <Clock size={14} /> Imputar horas
        </button>
      </div>
      <div style={{ display: 'flex', gap: 'var(--space-2)', flexWrap: 'wrap' }}>
        {SHORTCUTS.map(({ label, icon: Icon, path }) => (
          <button
            key={label}
            onClick={() => navigate(path)}
            style={{
              display: 'inline-flex', alignItems: 'center', gap: 'var(--space-2)',
              padding: '7px 12px', borderRadius: 'var(--radius-md)',
              background: 'var(--surface-3)', border: '1px solid var(--surface-4)',
              color: 'var(--text-2)', cursor: 'pointer', fontFamily: 'inherit',
              fontSize: 'var(--text-xs)', fontWeight: 600, whiteSpace: 'nowrap',
              transition: 'border-color 0.15s var(--easing), color 0.15s var(--easing)',
            }}
            onMouseEnter={e => {
              e.currentTarget.style.borderColor = 'var(--accent-border)'
              e.currentTarget.style.color = 'var(--accent)'
            }}
            onMouseLeave={e => {
              e.currentTarget.style.borderColor = 'var(--surface-4)'
              e.currentTarget.style.color = 'var(--text-2)'
            }}
          >
            <Icon size={12} /> {label}
          </button>
        ))}
      </div>
    </div>
  )
}

// ── Main page ───────────────────────────────────────────────────────────────
export default function WorkDashboardPage() {
  const navigate = useNavigate()
  const toast = useToast()
  const { user } = useAuth()
  const userId = user?.id

  const { data: taskStats, isLoading: lt, isError: taskStatsError } = useQuery({
    queryKey: ['work-dash-task-stats', userId],
    queryFn: async () => {
      const [openRes, overdueRes, doneRes] = await Promise.all([
        tasksApi.list({ assigned_to_me: true, status: 'backlog,todo,in_progress,blocked,in_review,review', page_size: 500 }),
        tasksApi.list({ assigned_to_me: true, overdue_only: true, page_size: 500 }),
        tasksApi.list({ assigned_to_me: true, status: 'done', page_size: 1 }),
      ])
      const openItems = Array.isArray(openRes?.data) ? openRes.data : []
      const overdueItems = Array.isArray(overdueRes?.data) ? overdueRes.data : []
      const openTaskIds = new Set(openItems.map(t => t.id).filter(Boolean))
      overdueItems.forEach(t => { if (t?.id) openTaskIds.add(t.id) })
      return {
        open: openTaskIds.size,
        overdue: totalCountFrom(overdueRes),
        done: totalCountFrom(doneRes),
      }
    },
    enabled: !!userId, staleTime: 60_000, retry: 1,
  })

  const { data: myWeekHours = 0 } = useQuery({
    queryKey: ['work-dash-my-week', userId],
    queryFn: () => analyticsApi.query('hours_by_week', { user_id: userId, date_from: startOfWeekIso(), date_to: new Date().toISOString().slice(0, 10) })
      .then(r => (r.data?.rows || []).reduce((s, x) => s + (x.value || 0), 0)).catch(() => 0),
    enabled: !!userId, staleTime: 60_000,
  })

  const { data: myMonthHours = null } = useQuery({
    queryKey: ['work-dash-my-month', userId],
    queryFn: () => analyticsApi.query('hours_by_week', { user_id: userId, date_from: startOfMonthIso(), date_to: new Date().toISOString().slice(0, 10) })
      .then(r => (r.data?.rows || []).reduce((s, x) => s + (x.value || 0), 0)).catch(() => null),
    enabled: !!userId, staleTime: 60_000,
  })

  const { data: approvals = [], isLoading: la } = useQuery({
    queryKey: ['work-dash-approvals'],
    queryFn: () => approvalsApi.pendingMyAction().then(r => {
      const d = r.data; return Array.isArray(d) ? d : (d?.items || [])
    }).catch(() => []),
    staleTime: 60_000,
  })

  const { data: expenses = [], isLoading: le } = useQuery({
    queryKey: ['work-dash-expenses'],
    queryFn: () => expensesApi.my({ status: 'pending' }).then(r => {
      const d = r.data; return Array.isArray(d) ? d : (d?.items || [])
    }).catch(() => []),
    staleTime: 60_000,
  })

  const { data: hoursData = [] } = useQuery({
    queryKey: ['work-dash-hours-trend', userId],
    queryFn: () => analyticsApi.query('hours_by_month', { ...dateRange(180), ...(userId ? { user_id: userId } : {}) })
      .then(r => r.data?.rows || []).catch(() => []),
    enabled: !!userId, staleTime: 60_000,
  })

  const { data: absences = [], isLoading: lab } = useQuery({
    queryKey: ['work-dash-absences'],
    queryFn: () => absencesApi.my().then(r => {
      const d = r.data; return Array.isArray(d) ? d : (d?.items || [])
    }).catch(() => []),
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
    const deltaPct = hasStableBaseline ? Math.round((delta / previousValue) * 100) : null
    return {
      label: row.label || `Mes ${index + 1}`,
      hours: currentValue, delta, deltaPct,
      hasBaseline: previousValue != null, hasStableBaseline,
      color: previousValue == null ? COLOR.accent
        : delta > 0 ? COLOR.success
        : delta < 0 ? COLOR.danger
        : COLOR.warning,
    }
  })
  const maxTrendHours = Math.max(...hoursTrendRows.map(row => row.hours || 0), 1)

  const activityRows = [
    { label: 'Tareas abiertas',         count: tasksOpen,    color: COLOR.accent },
    { label: 'Tareas vencidas',         count: tasksOverdue, color: COLOR.danger },
    { label: 'Aprobaciones pendientes', count: pendingApprv, color: COLOR.warning },
    { label: 'Gastos pendientes',       count: pendingExp,   color: COLOR.purple },
    { label: 'Ausencias pendientes',    count: pendingAbsences, color: 'var(--sky-blue)' },
  ]
  const totalActivity = activityRows.reduce((s, r) => s + r.count, 0)

  const isLoading = lt || la || le || lab

  return (
    <DashPageShell
      icon={<Clock size={18} />}
      title="Mi Trabajo"
      subtitle="Tu vista del día — tareas, horas, aprobaciones y tendencias personales"
      showPeriodSuffix={false}
    >
      <div className="ds-page">
        <Hero navigate={navigate} userName={user?.full_name || user?.name} />

        {/* KPI row */}
        <div className="ds-grid-stats">
          {isLoading ? Array.from({ length: 6 }).map((_, i) => <KpiCardSkeleton key={i} />) : <>
            <KpiCard
              icon={<KpiIcon icon={CheckCircle2} />} label="Tareas abiertas"
              value={tasksOpen}
              color={tasksOpen > 10 ? COLOR.warning : 'var(--text-1)'}
              accentBar={COLOR.accent}
              action={{ label: 'Ver tareas', to: '/tasks?view=list&mine=1&status=open' }} />
            <KpiCard
              icon={<KpiIcon icon={AlertTriangle} />} label="Tareas vencidas"
              value={tasksOverdue}
              color={tasksOverdue > 0 ? COLOR.danger : COLOR.success}
              accentBar={tasksOverdue > 0 ? COLOR.danger : COLOR.success}
              sub={tasksOverdue > 0 ? 'Requieren atención' : 'Todo al día'}
              action={tasksOverdue > 0 ? { label: 'Revisar vencidas', to: '/tasks?view=list&mine=1&status=open&overdue=1' } : undefined} />
            <KpiCard
              icon={<KpiIcon icon={Clock} />} label="Horas esta semana"
              value={hoursWeek.toFixed(1)}
              color={hoursColor} accentBar={hoursColor}
              sub={weekDateRangeLabel() ? `${weekDateRangeLabel()} · Obj: ${hoursTarget}h` : `Objetivo: ${hoursTarget}h`}
              action={{ label: 'Imputar horas', to: '/imputar' }} />
            <KpiCard
              icon={<KpiIcon icon={Calendar} />} label="Horas este mes"
              value={totalHoursMonth.toFixed(1)}
              color={COLOR.accent} accentBar={COLOR.accent}
              sub={prev > 0 ? `Mes anterior: ${prev.toFixed(1)}h` : undefined}
              action={{ label: 'Ver timesheets', to: '/timesheets' }} />
            <KpiCard
              icon={<KpiIcon icon={Bell} />} label="Aprobaciones"
              value={pendingApprv}
              color={pendingApprv > 0 ? COLOR.warning : COLOR.success}
              accentBar={pendingApprv > 0 ? COLOR.warning : COLOR.success}
              sub={pendingApprv > 0 ? 'Pendientes de mi acción' : 'Sin pendientes'}
              action={pendingApprv > 0 ? { label: 'Revisar', to: '/approvals' } : undefined} />
            <KpiCard
              icon={<KpiIcon icon={Wallet} />} label="Gastos pendientes"
              value={pendingExp}
              color={pendingExp > 0 ? COLOR.purple : COLOR.success}
              accentBar={COLOR.purple}
              sub={pendingExp > 0 ? 'Mis gastos por aprobar' : 'Sin gastos pendientes'}
              action={pendingExp > 0 ? { label: 'Ver gastos', to: '/expenses' } : undefined} />
          </>}
        </div>

        {/* Gauges */}
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: 'var(--space-3)' }}>
          {isLoading ? <><GaugeCardSkeleton /><GaugeCardSkeleton /></> : <>
            <GaugeCard label="Horas semana / objetivo"
              value={hoursWeekPct} color={hoursColor}
              sub={`${hoursWeek.toFixed(1)}h de ${hoursTarget}h objetivo`} />
            <GaugeCard label="Tareas completadas"
              value={taskCompletionPct} color={COLOR.success}
              sub="Ratio de resolución de tareas" />
          </>}
        </div>

        {/* Activity + trend */}
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))', gap: 'var(--space-3)' }}>
          <SectionCard title="Resumen de actividad">
            {totalActivity === 0 ? (
              <div className="ds-empty" style={{ padding: 'var(--space-6) var(--space-4)' }}>
                <CheckCircle2 size={32} className="ds-empty__icon" style={{ color: 'var(--success)' }} />
                <div className="ds-empty__title">Todo en orden</div>
                <div className="ds-empty__desc">No hay elementos pendientes ahora mismo.</div>
              </div>
            ) : activityRows.map(row => (
              <BarRow key={row.label} label={row.label} count={row.count}
                total={Math.max(totalActivity, 1)} color={row.color} />
            ))}
            <ActivityFooter pendingAbsences={pendingAbsences} />
          </SectionCard>

          <SectionCard title="Tendencia de horas (mensual)">
            {hoursTrendRows.length === 0 ? (
              <DashEmpty icon="—" title="Sin datos de horas" />
            ) : (
              <div className="ds-stack" style={{ gap: 'var(--space-3)' }}>
                {hoursTrendRows.map((row, i) => (
                  <TrendRow key={row.label || i} row={row} max={maxTrendHours} />
                ))}
              </div>
            )}
          </SectionCard>
        </div>
      </div>
    </DashPageShell>
  )
}

// ── Activity footer (if absences pending, hint a quick CTA) ──────────────────
function ActivityFooter({ pendingAbsences }) {
  if (pendingAbsences === 0) return null
  return (
    <div style={{
      display: 'flex', alignItems: 'center', gap: 'var(--space-2)',
      marginTop: 'var(--space-3)', paddingTop: 'var(--space-3)',
      borderTop: '1px solid var(--surface-4)',
      fontSize: 'var(--text-xs)', color: 'var(--text-3)',
    }}>
      <Plane size={11} />
      <span>{pendingAbsences} ausencia{pendingAbsences !== 1 ? 's' : ''} esperando aprobación</span>
      <a href="/absences" style={{ marginLeft: 'auto', color: 'var(--accent)', fontWeight: 600, textDecoration: 'none' }}>
        Ver <ArrowRight size={10} style={{ display: 'inline-block', verticalAlign: 'middle' }} />
      </a>
    </div>
  )
}

// ── Trend row — fila individual del breakdown mensual ───────────────────────
function TrendRow({ row, max }) {
  const TrendIcon = row.delta > 0 ? ArrowUpRight : row.delta < 0 ? ArrowDownRight : Minus
  return (
    <div>
      <div className="ds-row-between" style={{ marginBottom: 6 }}>
        <div className="ds-stack-sm">
          <div style={{ fontSize: 'var(--text-sm)', color: 'var(--text-2)', fontWeight: 600 }}>{row.label}</div>
          <div className="ds-muted">{row.hours.toFixed(1)}h totales</div>
        </div>
        <div style={{ textAlign: 'right' }}>
          <div style={{ fontSize: 'var(--text-xs)', fontWeight: 700, color: row.color, display: 'inline-flex', alignItems: 'center', gap: 4 }}>
            {row.hasBaseline ? <><TrendIcon size={11} /> {formatTrendPct(row.deltaPct, row.hours)}</> : 'Base'}
          </div>
          <div className="ds-muted">
            {row.hasBaseline
              ? (row.hasStableBaseline
                ? formatTrendDelta(row.delta)
                : `${formatTrendDelta(row.delta)} · base < ${TREND_MIN_BASELINE_HOURS}h`)
              : 'Primer mes comparable'}
          </div>
        </div>
      </div>
      <div style={{ height: 6, background: 'var(--surface-4)', borderRadius: 3, overflow: 'hidden' }}>
        <div style={{
          width: `${Math.max(6, Math.round((row.hours / max) * 100))}%`,
          height: '100%',
          background: 'var(--accent)',
          borderRadius: 3,
          transition: 'width 0.6s var(--easing)',
        }} />
      </div>
    </div>
  )
}
