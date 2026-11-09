import type { ComponentType } from 'react'
import { CSSProperties, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { tasksApi, analyticsApi, approvalsApi, expensesApi, absencesApi } from '../services/api'
import type { TaskListParams } from '../services/api/tasks'
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
import { useAppT } from '../i18n/AppLangContext'
import { localeActivo } from '../utils/helpers'

type TaskStatResponse = { open: number; overdue: number; done: number }
type HourRow = { label?: string; value?: number }
type ApprovalItem = { id: string | number }
type ExpenseItem = { id: string | number }
type AbsenceItem = { status?: string }
type DashboardTrendRow = {
  label: string
  hours: number
  delta: number
  deltaPct: number | null
  hasBaseline: boolean
  hasStableBaseline: boolean
  color: string
}
type ActivityRow = { label: string; count: number; color: string }
type HeroProps = { navigate: (path: string) => void; userName?: string | null; t: (key: string) => string }
type ActivityFooterProps = { pendingAbsences: number; t: (key: string) => string }
type TrendRowProps = { row: DashboardTrendRow; max: number; t: (key: string) => string }

const DASH_ICON = (icon: unknown) => icon as ComponentType<{ size?: number; strokeWidth?: number }>

const heroCardStyle: CSSProperties = {
  gap: 'var(--space-4)',
  background: 'linear-gradient(135deg, var(--surface-2) 0%, var(--surface-3) 100%)',
}

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
function fmtShort(dateStr: string) {
  return new Intl.DateTimeFormat(localeActivo(), { month: 'short', day: 'numeric' }).format(new Date(dateStr + 'T12:00:00'))
}
function weekDateRangeLabel() {
  const from = startOfWeekIso()
  const to = new Date().toISOString().slice(0, 10)
  if (from.slice(0, 7) === to.slice(0, 7)) return null
  return `${fmtShort(from)} – ${fmtShort(to)}`
}
function totalCountFrom(response?: { headers?: Record<string, unknown> }) {
  const total = response?.headers?.['x-total-count']
  const parsed = Number(total)
  return Number.isFinite(parsed) ? parsed : 0
}

const TREND_MIN_BASELINE_HOURS = 8
const formatTrendDelta = (delta: number) =>
  !Number.isFinite(delta) || delta === 0 ? '0.0h' : `${delta > 0 ? '+' : ''}${delta.toFixed(1)}h`
const formatTrendPct = (deltaPct: number | null, baseline: number) =>
  deltaPct == null || !Number.isFinite(deltaPct)
    ? (baseline > 0 ? 'Base baja' : 'Nuevo')
    : `${deltaPct > 0 ? '+' : ''}${deltaPct}%`

// ── Hero banner ─────────────────────────────────────────────────────────────
// Saludo + acciones rápidas. Sustituye "¿qué hacemos hoy?" por una versión
// más sobria con una CTA destacada y atajos secundarios.
function Hero({ navigate, userName, t }: HeroProps) {
  const now = new Date()
  const day = new Intl.DateTimeFormat(localeActivo(), { weekday: 'long' }).format(now)
  const date = new Intl.DateTimeFormat(localeActivo(), { day: 'numeric', month: 'long' }).format(now)
  const hour = now.getHours()
  const greeting = hour < 13 ? t('work_dashboard.greeting_morning') : hour < 20 ? t('work_dashboard.greeting_afternoon') : t('work_dashboard.greeting_evening')

  const SHORTCUTS = [
    { label: t('work_dashboard.shortcut_new_task'),   icon: Plus,   path: '/tasks' },
    { label: t('work_dashboard.shortcut_log_hours'),  icon: Clock,  path: '/imputar' },
    { label: t('work_dashboard.shortcut_new_ticket'), icon: Ticket, path: '/service-desk' },
    { label: t('work_dashboard.shortcut_timer'),      icon: Timer,  path: '/time' },
  ]

  return (
    <div className="ds-card" style={heroCardStyle}>
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
            background: 'var(--accent)', color: 'var(--on-accent)', border: 'none',
            fontSize: 'var(--text-sm)', fontWeight: 700, cursor: 'pointer',
            boxShadow: '0 1px 3px rgba(79,142,247,0.3)', whiteSpace: 'nowrap',
            transition: 'transform 0.1s var(--easing), box-shadow 0.15s var(--easing)',
          }}
          onMouseEnter={e => { e.currentTarget.style.boxShadow = '0 4px 12px rgba(79,142,247,0.4)' }}
          onMouseLeave={e => { e.currentTarget.style.boxShadow = '0 1px 3px rgba(79,142,247,0.3)' }}
        >
          <Clock size={14} /> {t('work_dashboard.shortcut_log_hours')}
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
export default function WorkDashboardPage(): JSX.Element {
  const t = useAppT() as (key: string) => string
  const navigate = useNavigate()
  const toast = useToast()
  const { user } = useAuth()
  const userId = user?.id

  const { data: taskStats, isLoading: lt, isError: taskStatsError } = useQuery<TaskStatResponse>({
    queryKey: ['work-dash-task-stats', userId],
    queryFn: async () => {
      const [openRes, overdueRes, doneRes] = await Promise.all([
        tasksApi.list({ assigned_to_me: true, status: 'backlog,todo,in_progress,blocked,in_review', page_size: 500 } as unknown as TaskListParams),
        tasksApi.list({ assigned_to_me: true, overdue_only: true, page_size: 500 } as TaskListParams),
        tasksApi.list({ assigned_to_me: true, status: 'done', page_size: 1 } as TaskListParams),
      ])
      const openItems = openRes?.data ?? []
      const overdueItems = overdueRes?.data ?? []
      const openTaskIds = new Set<string | number>(openItems.map((task: { id?: string | number }) => task.id).filter(Boolean) as Array<string | number>)
      overdueItems.forEach((task: { id?: string | number }) => { if (task?.id) openTaskIds.add(task.id) })
      return {
        open: openTaskIds.size,
        overdue: totalCountFrom(overdueRes),
        done: totalCountFrom(doneRes),
      }
    },
    enabled: !!userId, staleTime: 60_000, retry: 1,
  })

  const { data: myWeekHours = 0, isError: e1 } = useQuery<number>({
    queryKey: ['work-dash-my-week', userId],
    queryFn: async (): Promise<number> => {
      const r = await analyticsApi.query('hours_by_week', { user_id: userId, date_from: startOfWeekIso(), date_to: new Date().toISOString().slice(0, 10) })
      return ((r.data?.rows as Array<{ value?: number }> | undefined) || []).reduce((s: number, x) => s + (x.value || 0), 0)
    },
    enabled: !!userId, staleTime: 60_000,
  })

  const { data: myMonthHours = null, isError: e2 } = useQuery<number | null>({
    queryKey: ['work-dash-my-month', userId],
    queryFn: async (): Promise<number | null> => {
      const r = await analyticsApi.query('hours_by_week', { user_id: userId, date_from: startOfMonthIso(), date_to: new Date().toISOString().slice(0, 10) })
      return ((r.data?.rows as Array<{ value?: number }> | undefined) || []).reduce((s: number, x) => s + (x.value || 0), 0)
    },
    enabled: !!userId, staleTime: 60_000,
  })

  const { data: approvals = [], isLoading: la, isError: e3 } = useQuery<ApprovalItem[]>({
    queryKey: ['work-dash-approvals'],
    queryFn: () => approvalsApi.pendingMyAction().then(r => {
      const d = r.data; return Array.isArray(d) ? d : (d?.items || [])
    }),
    staleTime: 60_000,
  })

  const { data: expenses = [], isLoading: le, isError: e4 } = useQuery<ExpenseItem[]>({
    queryKey: ['work-dash-expenses'],
    queryFn: () => expensesApi.my({ status: 'pending' }).then(r => {
      const d = r.data; return Array.isArray(d) ? d : (d?.items || [])
    }),
    staleTime: 60_000,
  })

  const { data: hoursData = [], isError: e5 } = useQuery<HourRow[]>({
    queryKey: ['work-dash-hours-trend', userId],
    queryFn: async (): Promise<HourRow[]> => {
      const r = await analyticsApi.query('hours_by_month', { ...dateRange(180), ...(userId ? { user_id: userId } : {}) })
      return (r.data?.rows as HourRow[] | undefined) || []
    },
    enabled: !!userId, staleTime: 60_000,
  })

  const { data: absences = [], isLoading: lab, isError: e6 } = useQuery<AbsenceItem[]>({
    queryKey: ['work-dash-absences'],
    queryFn: () => absencesApi.my({}).then(r => {
      const d = r.data; return Array.isArray(d) ? d : (d?.items || [])
    }),
    staleTime: 60_000,
  })

  // Revisión 2026-11: cualquier consulta que falle avisa; antes su KPI enseñaba 0 en silencio.
  const algunFallo = taskStatsError || e1 || e2 || e3 || e4 || e5 || e6
  useEffect(() => {
    if (algunFallo) toast.error(t('work_dashboard.metrics_load_error'))
  }, [algunFallo]) // eslint-disable-line react-hooks/exhaustive-deps

  const tasksOpen    = taskStats?.open ?? 0
  const tasksOverdue = taskStats?.overdue ?? 0
  const tasksDone    = taskStats?.done ?? 0
  const hoursWeek    = (myWeekHours ?? 0) as number
  const pendingApprv = approvals.length
  const pendingExp   = expenses.length
  const pendingAbsences = absences.filter((absence: AbsenceItem) => absence.status === 'pending').length

  const hoursTarget  = (user?.weekly_capacity_hours ?? 40) as number
  const hoursWeekPct = Math.min(Math.round((hoursWeek / Math.max(hoursTarget, 1)) * 100), 100)
  const hoursColor   = hoursWeekPct >= 80 ? COLOR.success : hoursWeekPct >= 50 ? COLOR.warning : COLOR.danger
  const taskCompletionBase = tasksOpen + tasksDone
  const taskCompletionPct = taskCompletionBase > 0 ? Math.round((tasksDone / taskCompletionBase) * 100) : 100

  const last  = hoursData[hoursData.length - 1]?.value || 0
  const prev  = hoursData[hoursData.length - 2]?.value || 0
  const totalHoursMonth = myMonthHours !== null ? myMonthHours : last

  const hoursTrendRows: DashboardTrendRow[] = hoursData.slice(-6).map((row, index, rows) => {
    const previousValue = index > 0 ? (rows[index - 1]?.value || 0) : null
    const currentValue = row.value || 0
    const delta = previousValue == null ? 0 : currentValue - previousValue
    const hasStableBaseline = previousValue != null && previousValue >= TREND_MIN_BASELINE_HOURS
    const deltaPct = hasStableBaseline ? Math.round((delta / previousValue) * 100) : null
    return {
      label: row.label ? String(row.label) : `${t('work_dashboard.month_label')} ${index + 1}`,
      hours: currentValue, delta, deltaPct,
      hasBaseline: previousValue != null, hasStableBaseline,
      color: previousValue == null ? COLOR.accent
        : delta > 0 ? COLOR.success
        : delta < 0 ? COLOR.danger
        : COLOR.warning,
    }
  })
  const maxTrendHours = Math.max(...hoursTrendRows.map(row => row.hours || 0), 1)

  const activityRows: ActivityRow[] = [
    { label: t('work_dashboard.row_open_tasks'),         count: tasksOpen,    color: COLOR.accent },
    { label: t('work_dashboard.row_overdue_tasks'),      count: tasksOverdue, color: COLOR.danger },
    { label: t('work_dashboard.row_pending_approvals'),  count: pendingApprv, color: COLOR.warning },
    { label: t('work_dashboard.row_pending_expenses'),   count: pendingExp,   color: COLOR.purple },
    { label: t('work_dashboard.row_pending_absences'),   count: pendingAbsences, color: 'var(--sky-blue)' },
  ]
  const totalActivity = activityRows.reduce((s, r) => s + r.count, 0)

  const isLoading = lt || la || le || lab

  return (
    <DashPageShell
      icon={<Clock size={18} />}
      title={t('work_dashboard.title')}
      subtitle={t('work_dashboard.subtitle')}
      showPeriodSuffix={false}
    >
      <div className="ds-page">
        <Hero navigate={navigate} userName={String(user?.full_name || user?.name || '')} t={t} />

        {/* KPI row */}
        <div className="ds-grid-stats">
          {isLoading ? Array.from({ length: 6 }).map((_, i) => <KpiCardSkeleton key={i} />) : <>
            <KpiCard
              icon={<KpiIcon icon={DASH_ICON(CheckCircle2)} />} label={t('work_dashboard.kpi_open_tasks')}
              value={tasksOpen}
              color={tasksOpen > 10 ? COLOR.warning : 'var(--text-1)'}
              accentBar={COLOR.accent}
              action={{ label: t('work_dashboard.action_view_tasks'), to: '/tasks?view=list&mine=1&status=open' }} />
            <KpiCard
              icon={<KpiIcon icon={DASH_ICON(AlertTriangle)} />} label={t('work_dashboard.kpi_overdue_tasks')}
              value={tasksOverdue}
              color={tasksOverdue > 0 ? COLOR.danger : COLOR.success}
              accentBar={tasksOverdue > 0 ? COLOR.danger : COLOR.success}
              sub={tasksOverdue > 0 ? t('work_dashboard.needs_attention') : t('work_dashboard.all_up_to_date')}
              action={tasksOverdue > 0 ? { label: t('work_dashboard.action_review_overdue'), to: '/tasks?view=list&mine=1&status=open&overdue=1' } : undefined} />
            <KpiCard
              icon={<KpiIcon icon={DASH_ICON(Clock)} />} label={t('work_dashboard.kpi_hours_week')}
              value={hoursWeek.toFixed(1)}
              color={hoursColor} accentBar={hoursColor}
              sub={weekDateRangeLabel() ? `${weekDateRangeLabel()} · ${t('work_dashboard.target_short')}: ${hoursTarget}h` : `${t('work_dashboard.target_word')}: ${hoursTarget}h`}
              action={{ label: t('work_dashboard.shortcut_log_hours'), to: '/imputar' }} />
            <KpiCard
              icon={<KpiIcon icon={DASH_ICON(Calendar)} />} label={t('work_dashboard.kpi_hours_month')}
              value={totalHoursMonth.toFixed(1)}
              color={COLOR.accent} accentBar={COLOR.accent}
              sub={prev > 0 ? `${t('work_dashboard.previous_month')}: ${prev.toFixed(1)}h` : undefined}
              action={{ label: t('work_dashboard.action_view_timesheets'), to: '/timesheets' }} />
            <KpiCard
              icon={<KpiIcon icon={DASH_ICON(Bell)} />} label={t('work_dashboard.kpi_approvals')}
              value={pendingApprv}
              color={pendingApprv > 0 ? COLOR.warning : COLOR.success}
              accentBar={pendingApprv > 0 ? COLOR.warning : COLOR.success}
              sub={pendingApprv > 0 ? t('work_dashboard.pending_my_action') : t('work_dashboard.no_pending')}
              action={pendingApprv > 0 ? { label: t('work_dashboard.action_review'), to: '/approvals' } : undefined} />
            <KpiCard
              icon={<KpiIcon icon={DASH_ICON(Wallet)} />} label={t('work_dashboard.kpi_pending_expenses')}
              value={pendingExp}
              color={pendingExp > 0 ? COLOR.purple : COLOR.success}
              accentBar={COLOR.purple}
              sub={pendingExp > 0 ? t('work_dashboard.my_expenses_to_approve') : t('work_dashboard.no_pending_expenses')}
              action={pendingExp > 0 ? { label: t('work_dashboard.action_view_expenses'), to: '/expenses' } : undefined} />
          </>}
        </div>

        {/* Gauges */}
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: 'var(--space-3)' }}>
          {isLoading ? <><GaugeCardSkeleton /><GaugeCardSkeleton /></> : <>
            <GaugeCard label={t('work_dashboard.gauge_hours_target')}
              value={hoursWeekPct} color={hoursColor}
              sub={`${hoursWeek.toFixed(1)}h ${t('work_dashboard.of_word')} ${hoursTarget}h ${t('work_dashboard.target_word')}`} />
            <GaugeCard label={t('work_dashboard.gauge_tasks_completed')}
              value={taskCompletionPct} color={COLOR.success}
              sub={t('work_dashboard.task_resolution_ratio')} />
          </>}
        </div>

        {/* Activity + trend */}
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))', gap: 'var(--space-3)' }}>
          <SectionCard title={t('work_dashboard.section_activity_summary')}>
            {totalActivity === 0 ? (
              <div className="ds-empty" style={{ padding: 'var(--space-6) var(--space-4)' }}>
                <CheckCircle2 size={32} className="ds-empty__icon" style={{ color: 'var(--success)' }} />
                <div className="ds-empty__title">{t('work_dashboard.all_in_order_title')}</div>
                <div className="ds-empty__desc">{t('work_dashboard.all_in_order_desc')}</div>
              </div>
            ) : activityRows.map(row => (
              <BarRow key={row.label} label={row.label} count={row.count}
                total={Math.max(totalActivity, 1)} color={row.color} />
            ))}
            <ActivityFooter pendingAbsences={pendingAbsences} t={t} />
          </SectionCard>

          <SectionCard title={t('work_dashboard.section_hours_trend')}>
            {hoursTrendRows.length === 0 ? (
              <DashEmpty icon="—" title={t('work_dashboard.no_hours_data')} />
            ) : (
              <div className="ds-stack" style={{ gap: 'var(--space-3)' }}>
                {hoursTrendRows.map((row, i) => (
                  <TrendRow key={row.label || i} row={row} max={maxTrendHours} t={t} />
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
function ActivityFooter({ pendingAbsences, t }: ActivityFooterProps) {
  if (pendingAbsences === 0) return null
  return (
    <div style={{
      display: 'flex', alignItems: 'center', gap: 'var(--space-2)',
      marginTop: 'var(--space-3)', paddingTop: 'var(--space-3)',
      borderTop: '1px solid var(--surface-4)',
      fontSize: 'var(--text-xs)', color: 'var(--text-3)',
    }}>
      <Plane size={11} />
      <span>{pendingAbsences} {pendingAbsences !== 1 ? t('work_dashboard.absences_waiting_plural') : t('work_dashboard.absences_waiting_singular')}</span>
      <a href="/absences" style={{ marginLeft: 'auto', color: 'var(--accent)', fontWeight: 600, textDecoration: 'none' }}>
        {t('work_dashboard.see')} <ArrowRight size={10} style={{ display: 'inline-block', verticalAlign: 'middle' }} />
      </a>
    </div>
  )
}

// ── Trend row — fila individual del breakdown mensual ───────────────────────
function TrendRow({ row, max, t }: TrendRowProps) {
  const TrendIcon = row.delta > 0 ? ArrowUpRight : row.delta < 0 ? ArrowDownRight : Minus
  return (
    <div>
      <div className="ds-row-between" style={{ marginBottom: 6 }}>
        <div className="ds-stack-sm">
          <div style={{ fontSize: 'var(--text-sm)', color: 'var(--text-2)', fontWeight: 600 }}>{row.label}</div>
          <div className="ds-muted">{row.hours.toFixed(1)}h {t('work_dashboard.total_lower')}</div>
        </div>
        <div style={{ textAlign: 'right' }}>
          <div style={{ fontSize: 'var(--text-xs)', fontWeight: 700, color: row.color, display: 'inline-flex', alignItems: 'center', gap: 4 }}>
            {row.hasBaseline ? <><TrendIcon size={11} /> {formatTrendPct(row.deltaPct, row.hours)}</> : t('work_dashboard.base_short')}
          </div>
          <div className="ds-muted">
            {row.hasBaseline
              ? (row.hasStableBaseline
                ? formatTrendDelta(row.delta)
                : `${formatTrendDelta(row.delta)} · ${t('work_dashboard.base_lt')} ${TREND_MIN_BASELINE_HOURS}h`)
              : t('work_dashboard.first_comparable_month')}
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
