/**
 * CalendarPage v23 — Vista calendario global unificada
 * Muestra: tareas con fecha, milestones, sprints, ausencias, vencimientos
 */
import { useMemo, useState, type CSSProperties } from 'react'
import { useQuery } from '@tanstack/react-query'
import { tasksApi, projectsApi, sprintsApi, absencesApi, unwrapList } from '../services/api'
import PageHeader from '../components/layout/PageHeader'
import PageShell from '../components/layout/PageShell'
import { Calendar } from 'lucide-react'
import { useAppLang } from '../i18n/AppLangContext'
import { localeActivo } from '../utils/helpers'
import { CALENDAR_ABSENCES_LIMIT, CALENDAR_SPRINTS_LIMIT, CALENDAR_TASKS_LIMIT } from '../constants/pagination'
import './CalendarPage.css'

interface CalendarEvent {
  date: string
  type: keyof typeof EVENT_TYPES
  title: string
  id: string | number
  status?: string
}

interface TaskItem { id: string | number; due_date?: string; title?: string; status?: string }
interface MilestoneItem { id: string | number; due_date?: string; title?: string }
interface SprintItem { id: string | number; start_date?: string; end_date?: string; name?: string }

/** Tipos de evento: color (token), icono y clave i18n de la etiqueta. */
const EVENT_TYPES = {
  task:      { color: 'var(--success)', icon: '▦', labelKey: 'calendar.type_task' },
  milestone: { color: 'var(--accent)', icon: '⬟', labelKey: 'calendar.type_milestone' },
  sprint:    { color: 'var(--purple)', icon: '🔄', labelKey: 'calendar.type_sprint' },
  absence:   { color: 'var(--warning)', icon: '🏖', labelKey: 'calendar.type_absence' },
  contract:  { color: 'var(--danger)', icon: '📄', labelKey: 'calendar.type_contract' },
  license:   { color: 'var(--warning)', icon: '🔑', labelKey: 'calendar.type_license' },
}
type EventType = keyof typeof EVENT_TYPES

/** Color del tipo como custom property, consumida por las clases .cal-*. */
const evColor = (color: string): CSSProperties => ({ '--ev-color': color } as CSSProperties)

function getDaysInMonth(year: number, month: number) {
  return new Date(year, month + 1, 0).getDate()
}
function getFirstDayOfMonth(year: number, month: number) {
  const d = new Date(year, month, 1).getDay()
  return d === 0 ? 6 : d - 1 // Lunes = 0
}

export default function CalendarPage(): JSX.Element {
  const { t, lang } = useAppLang()
  const locale = localeActivo(lang)
  const now = new Date()
  const [year, setYear]   = useState<number>(now.getFullYear())
  const [month, setMonth] = useState<number>(now.getMonth())
  const [filter, setFilter] = useState<'all' | EventType>('all')

  const dateFrom = `${year}-${String(month+1).padStart(2,'0')}-01`
  const dateTo   = `${year}-${String(month+1).padStart(2,'0')}-${String(getDaysInMonth(year,month)).padStart(2,'0')}`

  // Nombre del mes y días de la semana (lunes primero) según el idioma activo.
  const monthLabel = useMemo(() => {
    const m = new Intl.DateTimeFormat(locale, { month: 'long' }).format(new Date(year, month, 1))
    return `${m.charAt(0).toLocaleUpperCase(locale)}${m.slice(1)} ${year}`
  }, [locale, year, month])
  const weekdays = useMemo(() => {
    const corto = new Intl.DateTimeFormat(locale, { weekday: 'narrow' })
    const largo = new Intl.DateTimeFormat(locale, { weekday: 'long' })
    // 2024-01-01 fue lunes.
    return Array.from({ length: 7 }, (_, i) => {
      const d = new Date(2024, 0, 1 + i)
      return { short: corto.format(d), long: largo.format(d) }
    })
  }, [locale])

  // Tareas con fecha de vencimiento
  const { data: tasks = [] } = useQuery<CalendarEvent[]>({
    queryKey: ['cal-tasks', year, month],
    queryFn: () => tasksApi.list({ due_date_from: dateFrom, due_date_to: dateTo, limit: CALENDAR_TASKS_LIMIT })
      .then(r => (unwrapList(r) as TaskItem[]).map((t): CalendarEvent => ({
        date: t.due_date ?? '', type: 'task', title: t.title ?? '', id: t.id, status: t.status,
      }))).catch(() => []),
  })

  // Milestones
  const { data: milestones = [] } = useQuery<CalendarEvent[]>({
    queryKey: ['cal-milestones', year, month],
    queryFn: () => projectsApi.milestones({ date_from: dateFrom, date_to: dateTo })
      .then(r => (unwrapList(r) as MilestoneItem[]).map((m): CalendarEvent => ({
        date: m.due_date ?? '', type: 'milestone', title: m.title ?? '', id: m.id,
      }))).catch(() => []),
  })

  // Sprints
  const { data: sprints = [] } = useQuery<CalendarEvent[]>({
    queryKey: ['cal-sprints', year, month, lang],
    queryFn: () => sprintsApi.list(undefined, { limit: CALENDAR_SPRINTS_LIMIT })
      .then(r => (unwrapList(r) as SprintItem[]).flatMap(s => [
        s.start_date ? { date: s.start_date, type: 'sprint', title: t('calendar.sprint_start', { name: s.name ?? '' }), id: s.id + '_s' } : null,
        s.end_date   ? { date: s.end_date,   type: 'sprint', title: t('calendar.sprint_end', { name: s.name ?? '' }), id: s.id + '_e' } : null,
      ].filter(Boolean) as CalendarEvent[])).catch(() => []),
  })

  // Ausencias
  const { data: absences = [] } = useQuery<CalendarEvent[]>({
    queryKey: ['cal-absences', year, month, lang],
    queryFn: () => absencesApi.list({ date_from: dateFrom, date_to: dateTo, limit: CALENDAR_ABSENCES_LIMIT })
      // Una ausencia ocupa todos sus días del mes, no sólo el primero (revisión 2026-11).
      .then(r => r.data.flatMap((a): CalendarEvent[] => {
        if (!a.start_date) return []
        const desde = a.start_date > dateFrom ? a.start_date : dateFrom
        const fin = a.end_date || a.start_date
        const hasta = fin < dateTo ? fin : dateTo
        const dias: CalendarEvent[] = []
        for (let d = Number(desde.slice(8, 10)); d <= Number(hasta.slice(8, 10)) && desde <= hasta; d++) {
          dias.push({ date: `${dateFrom.slice(0, 8)}${String(d).padStart(2, '0')}`, type: 'absence',
            title: t('calendar.absence_title', { user: a.user_name || t('calendar.team'), type: a.type || t('calendar.type_absence') }), id: `${a.id}_${d}` })
        }
        return dias
      })).catch(() => []),
  })

  // Todos los eventos del mes
  const allEvents = [...tasks, ...milestones, ...sprints, ...absences]
    .filter(e => e.date && e.date.startsWith(`${year}-${String(month+1).padStart(2,'0')}`))
    .filter(e => filter === 'all' || e.type === filter)

  // Agrupar por día
  const eventsByDay: Record<number, CalendarEvent[]> = {}
  allEvents.forEach(e => {
    const day = parseInt(e.date.split('-')[2])
    if (!eventsByDay[day]) eventsByDay[day] = []
    eventsByDay[day].push(e)
  })

  const daysInMonth  = getDaysInMonth(year, month)
  const firstDay     = getFirstDayOfMonth(year, month)
  const today        = now.getDate()
  const isCurrentMonth = now.getFullYear() === year && now.getMonth() === month

  const prevMonth = () => { if (month === 0) { setYear(y => y-1); setMonth(11) } else setMonth(m => m-1) }
  const nextMonth = () => { if (month === 11) { setYear(y => y+1); setMonth(0) } else setMonth(m => m+1) }

  const cells = []
  for (let i = 0; i < firstDay; i++) cells.push(null)
  for (let d = 1; d <= daysInMonth; d++) cells.push(d)

  return (
    <PageShell>
      <PageHeader icon={<Calendar size={18} />} title={t('calendar.title')} subtitle={t('calendar.subtitle')} showListExport={false} />

      {/* Controles */}
      <div className="cal-controls">
        <div className="u-row-center-8">
          <button type="button" onClick={prevMonth} className="cal-nav-btn" aria-label={t('calendar.prev_month')} title={t('calendar.prev_month')}>‹</button>
          <div className="cal-month-label" aria-live="polite">{monthLabel}</div>
          <button type="button" onClick={nextMonth} className="cal-nav-btn" aria-label={t('calendar.next_month')} title={t('calendar.next_month')}>›</button>
          <button type="button" onClick={() => { setYear(now.getFullYear()); setMonth(now.getMonth()) }} className="cal-today-btn">
            {t('calendar.today')}
          </button>
        </div>

        {/* Filtros */}
        <div className="u-wrap-6" role="group" aria-label={t('calendar.filter_label')}>
          <button type="button" onClick={() => setFilter('all')} className="cal-filter" aria-pressed={filter === 'all'}>
            {t('calendar.filter_all')}
          </button>
          {(Object.keys(EVENT_TYPES) as EventType[]).map(k => (
            <button type="button" key={k} onClick={() => setFilter(k)} className="cal-filter" style={evColor(EVENT_TYPES[k].color)} aria-pressed={filter === k}>
              <span aria-hidden="true">{EVENT_TYPES[k].icon} </span>{t(EVENT_TYPES[k].labelKey)}
            </button>
          ))}
        </div>
      </div>

      {/* Leyenda */}
      <div className="cal-legend">
        {Object.entries(EVENT_TYPES).map(([k, v]) => (
          <span key={k} className="cal-legend__item">
            <span className="cal-legend__dot" style={evColor(v.color)} aria-hidden="true" />
            {t(v.labelKey)}
          </span>
        ))}
        <span className="cal-legend__count">
          {t('calendar.events_this_month', { count: allEvents.length })}
        </span>
      </div>

      {/* Cabecera días */}
      <div className="cal-grid cal-grid--head">
        {weekdays.map((d, i) => (
          <div key={i} className="cal-weekday">
            <abbr title={d.long}>{d.short}</abbr>
          </div>
        ))}
      </div>

      {/* Grid del calendario */}
      <div className="cal-grid">
        {cells.map((day, i) => {
          if (day === null) return <div key={`empty-${i}`} className="cal-empty" />
          const isToday = isCurrentMonth && day === today
          const dayEvents = eventsByDay[day] || []
          return (
            <div key={day} className={`cal-day${isToday ? ' cal-day--today' : ''}`} aria-current={isToday ? 'date' : undefined}>
              <div className="cal-day__num">{day}</div>
              <div className="cal-day__events">
                {dayEvents.slice(0, 3).map((e) => {
                  const cfg = EVENT_TYPES[e.type]
                  return (
                    <div key={e.id} title={e.title} className="cal-event" style={evColor(cfg.color)}>
                      <span aria-hidden="true">{cfg.icon}</span> {e.title}
                    </div>
                  )
                })}
                {dayEvents.length > 3 && (
                  <div className="cal-more">{t('calendar.more_count', { count: dayEvents.length - 3 })}</div>
                )}
              </div>
            </div>
          )
        })}
      </div>
    </PageShell>
  )
}
