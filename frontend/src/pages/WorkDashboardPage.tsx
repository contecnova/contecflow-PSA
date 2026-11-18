/*
 * 16-11-2026: cabecera con el nombre del menú (nav.work_dashboard); fecha con el
 * formateador de la app (antes `text-transform: capitalize` dejaba "16 De
 * Noviembre"); saludo con el peso de los títulos de sección; "Imputar horas"
 * salía dos veces (botón y atajo): queda sólo el botón; atajos y botón con
 * Button del kit; KPIs con el KpiCard común (antes barra superior de color) y
 * el enlace de cada uno debajo; vacíos con EmptyState; el indicador de tareas
 * completadas ya no marca 100% cuando no hay tareas.
 */
import { useEffect } from 'react'
import type { CSSProperties, ReactNode } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { tasksApi, analyticsApi, approvalsApi, expensesApi, absencesApi } from '../services/api'
import type { FilaDeMetrica } from '../services/api/tipos-analitica'
import type { Absence } from '../services/api/tipos-personas'
import type { Gasto } from '../services/api/tipos-finanzas'
import {
  Clock, Plus, Timer, Ticket, CheckCircle2, AlertTriangle, Calendar,
  Bell, Wallet, Plane, ArrowUpRight, ArrowDownRight, Minus, ArrowRight, LayoutGrid, BarChart3,
} from 'lucide-react'
import { useToast } from '../context/ToastContext'
import { useAuth } from '../context/AuthContext'
import { useOrgSettings } from '../hooks/useOrgSettings'
import {
  COLOR, KpiCardSkeleton, GaugeCard, GaugeCardSkeleton, BarRow,
  dateRange,
} from '../components/dashboard/DashKit'
import { Button, Card, EmptyState, KpiCard, Section } from '../components/ui'
import PageShell from '../components/layout/PageShell'
import PageHeader from '../components/layout/PageHeader'
import { useAppT } from '../i18n/AppLangContext'
import { formateadorDeFecha, localeActivo } from '../utils/helpers'
import { STALE_DEFAULT_MS } from '../constants/timings'
import { COUNT_ONLY_PAGE_SIZE, FULL_LIST_SIZE } from '../constants/pagination'
import './WorkDashboardPage.css'

type TaskStatResponse = { open: number; overdue: number; done: number }
type HourRow = FilaDeMetrica
type ApprovalItem = { id: string | number }
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
  return formateadorDeFecha({ month: 'short', day: 'numeric' }).format(new Date(dateStr + 'T12:00:00'))
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
const formatTrendPct = (deltaPct: number | null, baseline: number, t: (key: string) => string) =>
  deltaPct == null || !Number.isFinite(deltaPct)
    ? (baseline > 0 ? t('work_dashboard.base_baja') : t('work_dashboard.nuevo'))
    : `${deltaPct > 0 ? '+' : ''}${deltaPct}%`

// ── Hero banner ─────────────────────────────────────────────────────────────
// Saludo + acciones rápidas. Sustituye "¿qué hacemos hoy?" por una versión
// más sobria con una CTA destacada y atajos secundarios.
function Hero({ navigate, userName, t }: HeroProps) {
  const now = new Date()
  const fecha = formateadorDeFecha({ weekday: 'long', day: 'numeric', month: 'long' }).format(now)
  const fechaTexto = fecha.charAt(0).toLocaleUpperCase(localeActivo()) + fecha.slice(1)
  const hour = now.getHours()
  const greeting = hour < 13 ? t('work_dashboard.greeting_morning') : hour < 20 ? t('work_dashboard.greeting_afternoon') : t('work_dashboard.greeting_evening')

  // "Imputar horas" es el botón principal; no se repite entre los atajos.
  const SHORTCUTS = [
    { label: t('work_dashboard.shortcut_new_task'),   icon: Plus,   path: '/tasks' },
    { label: t('work_dashboard.shortcut_new_ticket'), icon: Ticket, path: '/service-desk' },
    { label: t('work_dashboard.shortcut_timer'),      icon: Timer,  path: '/time' },
  ]

  return (
    <Card className="wd-hero">
      <div className="wd-hero-top">
        <div className="wd-hero-text">
          <div className="wd-hero-date">{fechaTexto}</div>
          <div className="wd-hero-greeting">
            {greeting}{userName ? `, ${userName.split(' ')[0]}` : ''}
          </div>
        </div>
        <Button icon={<Clock size={14} aria-hidden="true" />} onClick={() => navigate('/imputar')}>
          {t('work_dashboard.shortcut_log_hours')}
        </Button>
      </div>
      <div className="wd-shortcuts">
        {SHORTCUTS.map(({ label, icon: Icon, path }) => (
          <Button key={label} variant="secondary" size="sm" icon={<Icon size={13} aria-hidden="true" />}
            onClick={() => navigate(path)}>
            {label}
          </Button>
        ))}
      </div>
    </Card>
  )
}

/** Texto del KPI y, debajo, el enlace a la pantalla donde se actúa. */
function KpiSub({ texto, to, label }: { texto?: ReactNode; to?: string; label?: string }) {
  if (!texto && !to) return null
  return (
    <span className="wd-kpi-sub">
      {texto && <span>{texto}</span>}
      {to && (
        <Link to={to} className="wd-kpi-link">
          {label} <ArrowRight size={11} aria-hidden="true" />
        </Link>
      )}
    </span>
  )
}

// ── Main page ───────────────────────────────────────────────────────────────
export default function WorkDashboardPage(): JSX.Element {
  const t = useAppT()
  const navigate = useNavigate()
  const toast = useToast()
  const { user } = useAuth()
  const { weekly_capacity_hours: capacidadEmpresa } = useOrgSettings() // 18-11-2026
  const userId = user?.id

  const { data: taskStats, isLoading: lt, isError: taskStatsError } = useQuery<TaskStatResponse>({
    queryKey: ['work-dash-task-stats', userId],
    queryFn: async () => {
      const [openRes, overdueRes, doneRes] = await Promise.all([
        tasksApi.list({ assigned_to_me: true, status: 'backlog,todo,in_progress,blocked,in_review', page_size: FULL_LIST_SIZE }),
        tasksApi.list({ assigned_to_me: true, overdue_only: true, page_size: FULL_LIST_SIZE }),
        tasksApi.list({ assigned_to_me: true, status: 'done', page_size: COUNT_ONLY_PAGE_SIZE }),
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
    enabled: !!userId, staleTime: STALE_DEFAULT_MS, retry: 1,
  })

  const { data: myWeekHours = 0, isError: e1 } = useQuery<number>({
    queryKey: ['work-dash-my-week', userId],
    queryFn: async (): Promise<number> => {
      const r = await analyticsApi.query('hours_by_week', { user_id: userId, date_from: startOfWeekIso(), date_to: new Date().toISOString().slice(0, 10) })
      return r.data.rows.reduce((s: number, x) => s + (x.value || 0), 0)
    },
    enabled: !!userId, staleTime: STALE_DEFAULT_MS,
  })

  const { data: myMonthHours = null, isError: e2 } = useQuery<number | null>({
    queryKey: ['work-dash-my-month', userId],
    queryFn: async (): Promise<number | null> => {
      const r = await analyticsApi.query('hours_by_week', { user_id: userId, date_from: startOfMonthIso(), date_to: new Date().toISOString().slice(0, 10) })
      return r.data.rows.reduce((s: number, x) => s + (x.value || 0), 0)
    },
    enabled: !!userId, staleTime: STALE_DEFAULT_MS,
  })

  const { data: approvals = [], isLoading: la, isError: e3 } = useQuery<ApprovalItem[]>({
    queryKey: ['work-dash-approvals'],
    queryFn: () => approvalsApi.pendingMyAction().then(r => r.data),
    staleTime: STALE_DEFAULT_MS,
  })

  const { data: expenses = [], isLoading: le, isError: e4 } = useQuery<Gasto[]>({
    queryKey: ['work-dash-expenses'],
    // `pending` es alias de `submitted` en el backend (expense_service._STATUS_ALIASES).
    queryFn: () => expensesApi.my({ status: 'submitted' }).then(r => r.data),
    staleTime: STALE_DEFAULT_MS,
  })

  const { data: hoursData = [], isError: e5 } = useQuery<HourRow[]>({
    queryKey: ['work-dash-hours-trend', userId],
    queryFn: async (): Promise<HourRow[]> => {
      const r = await analyticsApi.query('hours_by_month', { ...dateRange(180), ...(userId ? { user_id: userId } : {}) })
      return r.data.rows
    },
    enabled: !!userId, staleTime: STALE_DEFAULT_MS,
  })

  const { data: absences = [], isLoading: lab, isError: e6 } = useQuery<Absence[]>({
    queryKey: ['work-dash-absences'],
    queryFn: () => absencesApi.my({}).then(r => r.data),
    staleTime: STALE_DEFAULT_MS,
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
  const pendingAbsences = absences.filter((absence) => absence.status === 'pending').length

  const hoursTarget  = (user?.weekly_capacity_hours ?? capacidadEmpresa) as number
  const hoursWeekPct = Math.min(Math.round((hoursWeek / Math.max(hoursTarget, 1)) * 100), 100)
  const hoursColor   = hoursWeekPct >= 80 ? COLOR.success : hoursWeekPct >= 50 ? COLOR.warning : COLOR.danger
  const taskCompletionBase = tasksOpen + tasksDone
  // Sin tareas no hay ratio: antes salía 100% "completadas" sin tener ninguna.
  const taskCompletionPct = taskCompletionBase > 0 ? Math.round((tasksDone / taskCompletionBase) * 100) : null

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

  const semana = weekDateRangeLabel()

  return (
    <PageShell>
      <PageHeader
        icon={<LayoutGrid size={18} />}
        title={t('nav.work_dashboard')}
        subtitle={t('work_dashboard.subtitle')}
        showListExport={false}
      />
      <div className="ds-page">
        <Hero navigate={navigate} userName={String(user?.full_name || user?.name || '')} t={t} />

        <div className="ds-grid-stats">
          {isLoading ? Array.from({ length: 6 }).map((_, i) => <KpiCardSkeleton key={i} />) : <>
            <KpiCard
              icon={<CheckCircle2 size={16} />} label={t('work_dashboard.kpi_open_tasks')}
              value={tasksOpen} warning={tasksOpen > 10}
              sub={<KpiSub to="/tasks?view=list&mine=1&status=open" label={t('work_dashboard.action_view_tasks')} />} />
            <KpiCard
              icon={<AlertTriangle size={16} />} label={t('work_dashboard.kpi_overdue_tasks')}
              value={tasksOverdue} danger={tasksOverdue > 0}
              sub={<KpiSub
                texto={tasksOverdue > 0 ? t('work_dashboard.needs_attention') : t('work_dashboard.all_up_to_date')}
                to={tasksOverdue > 0 ? '/tasks?view=list&mine=1&status=open&overdue=1' : undefined}
                label={t('work_dashboard.action_review_overdue')} />} />
            <KpiCard
              icon={<Clock size={16} />} label={t('work_dashboard.kpi_hours_week')}
              value={hoursWeek.toFixed(1)}
              warning={hoursWeekPct >= 50 && hoursWeekPct < 80} danger={hoursWeekPct < 50}
              sub={<KpiSub texto={semana ? `${semana} · ${t('work_dashboard.target_short')}: ${hoursTarget}h` : `${t('work_dashboard.target_word')}: ${hoursTarget}h`} />} />
            <KpiCard
              icon={<Calendar size={16} />} label={t('work_dashboard.kpi_hours_month')}
              value={totalHoursMonth.toFixed(1)}
              sub={<KpiSub
                texto={prev > 0 ? `${t('work_dashboard.previous_month')}: ${prev.toFixed(1)}h` : undefined}
                to="/timesheets" label={t('work_dashboard.action_view_timesheets')} />} />
            <KpiCard
              icon={<Bell size={16} />} label={t('work_dashboard.kpi_approvals')}
              value={pendingApprv} warning={pendingApprv > 0}
              sub={<KpiSub
                texto={pendingApprv > 0 ? t('work_dashboard.pending_my_action') : t('work_dashboard.no_pending')}
                to={pendingApprv > 0 ? '/approvals' : undefined} label={t('work_dashboard.action_review')} />} />
            <KpiCard
              icon={<Wallet size={16} />} label={t('work_dashboard.kpi_pending_expenses')}
              value={pendingExp} warning={pendingExp > 0}
              sub={<KpiSub
                texto={pendingExp > 0 ? t('work_dashboard.my_expenses_to_approve') : t('work_dashboard.no_pending_expenses')}
                to={pendingExp > 0 ? '/expenses' : undefined} label={t('work_dashboard.action_view_expenses')} />} />
          </>}
        </div>

        <div className="wd-grid-gauges">
          {isLoading ? <><GaugeCardSkeleton /><GaugeCardSkeleton /></> : <>
            <GaugeCard label={t('work_dashboard.gauge_hours_target')}
              value={hoursWeekPct} color={hoursColor}
              sub={t('work_dashboard.hours_target_sub', { horas: hoursWeek.toFixed(1), objetivo: hoursTarget })} />
            <GaugeCard label={t('work_dashboard.gauge_tasks_completed')}
              value={taskCompletionPct} color={COLOR.success}
              sub={taskCompletionPct == null ? t('work_dashboard.no_tasks_assigned') : t('work_dashboard.task_resolution_ratio')} />
          </>}
        </div>

        <div className="wd-grid-sections">
          <Card>
            <Section title={t('work_dashboard.section_activity_summary')}>
              {totalActivity === 0 ? (
                <EmptyState icon={<CheckCircle2 size={28} />}
                  title={t('work_dashboard.all_in_order_title')}
                  description={t('work_dashboard.all_in_order_desc')} />
              ) : activityRows.map(row => (
                <BarRow key={row.label} label={row.label} count={row.count}
                  total={Math.max(totalActivity, 1)} color={row.color} />
              ))}
              <ActivityFooter pendingAbsences={pendingAbsences} t={t} />
            </Section>
          </Card>

          <Card>
            <Section title={t('work_dashboard.section_hours_trend')}>
              {hoursTrendRows.length === 0 ? (
                <EmptyState icon={<BarChart3 size={28} />}
                  title={t('work_dashboard.no_hours_data')}
                  description={t('work_dashboard.no_hours_data_desc')} />
              ) : (
                <div className="ds-stack wd-trend-list">
                  {hoursTrendRows.map((row, i) => (
                    <TrendRow key={row.label || i} row={row} max={maxTrendHours} t={t} />
                  ))}
                </div>
              )}
            </Section>
          </Card>
        </div>
      </div>
    </PageShell>
  )
}

// ── Activity footer (if absences pending, hint a quick CTA) ──────────────────
function ActivityFooter({ pendingAbsences, t }: ActivityFooterProps) {
  if (pendingAbsences === 0) return null
  return (
    <div className="wd-footer">
      <Plane size={13} aria-hidden="true" />
      <span>{pendingAbsences} {pendingAbsences !== 1 ? t('work_dashboard.absences_waiting_plural') : t('work_dashboard.absences_waiting_singular')}</span>
      <Link to="/absences" className="wd-footer-link">
        {t('work_dashboard.see')} <ArrowRight size={11} className="wd-inline-icon" aria-hidden="true" />
      </Link>
    </div>
  )
}

// ── Trend row — fila individual del breakdown mensual ───────────────────────
function TrendRow({ row, max, t }: TrendRowProps) {
  const TrendIcon = row.delta > 0 ? ArrowUpRight : row.delta < 0 ? ArrowDownRight : Minus
  return (
    <div>
      <div className="ds-row-between wd-trend-head">
        <div className="ds-stack-sm">
          <div className="wd-trend-label">{row.label}</div>
          <div className="ds-muted">{row.hours.toFixed(1)}h {t('work_dashboard.total_lower')}</div>
        </div>
        <div className="wd-trend-right">
          <div className="wd-trend-delta" style={{ '--wd-color': row.color } as CSSProperties}>
            {row.hasBaseline ? <><TrendIcon size={11} /> {formatTrendPct(row.deltaPct, row.hours, t)}</> : t('work_dashboard.base_short')}
          </div>
          <div className="ds-muted">
            {row.hasBaseline
              ? (row.hasStableBaseline
                ? formatTrendDelta(row.delta)
                : `${formatTrendDelta(row.delta)} ${t('work_dashboard.base_lt')} ${TREND_MIN_BASELINE_HOURS}h`)
              : t('work_dashboard.first_comparable_month')}
          </div>
        </div>
      </div>
      <div className="wd-bar">
        <div className="wd-bar-fill" style={{ '--wd-pct': `${Math.max(6, Math.round((row.hours / max) * 100))}%` } as CSSProperties} />
      </div>
    </div>
  )
}
