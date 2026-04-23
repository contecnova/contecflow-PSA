/**
 * CalendarPage v23 — Vista calendario global unificada
 * Muestra: tareas con fecha, milestones, sprints, ausencias, vencimientos
 */
import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import api from '../services/api'
import PageHeader from '../components/layout/PageHeader'
import { Calendar } from 'lucide-react'
import { useNavigate } from 'react-router-dom'
import { useToast } from '../context/ToastContext'
import { useAppT } from '../i18n/AppLangContext'

const MONTHS = ['Enero','Febrero','Marzo','Abril','Mayo','Junio','Julio','Agosto','Septiembre','Octubre','Noviembre','Diciembre']
const DAYS   = ['L','M','X','J','V','S','D']

const EVENT_TYPES = {
  task:      { color: 'var(--success)', icon: '▦', label: 'Tarea' },
  milestone: { color: 'var(--accent)', icon: '⬟', label: 'Hito' },
  sprint:    { color: 'var(--purple)', icon: '🔄', label: 'Sprint' },
  absence:   { color: 'var(--warning)', icon: '🏖', label: 'Ausencia' },
  contract:  { color: 'var(--danger)', icon: '📄', label: 'Vencimiento' },
  license:   { color: 'var(--warning)', icon: '🔑', label: 'Licencia' },
}

function getDaysInMonth(year, month) {
  return new Date(year, month + 1, 0).getDate()
}
function getFirstDayOfMonth(year, month) {
  let d = new Date(year, month, 1).getDay()
  return d === 0 ? 6 : d - 1 // Lunes = 0
}

export default function CalendarPage() {
  const t = useAppT()
  const _toast = useToast()
  const _nav = useNavigate()
  const now = new Date()
  const [year, setYear]   = useState(now.getFullYear())
  const [month, setMonth] = useState(now.getMonth())
  const [filter, setFilter] = useState('all') // all | task | milestone | sprint | absence

  const dateFrom = `${year}-${String(month+1).padStart(2,'0')}-01`
  const dateTo   = `${year}-${String(month+1).padStart(2,'0')}-${String(getDaysInMonth(year,month)).padStart(2,'0')}`

  // Tareas con fecha de vencimiento
  const { data: tasks = [] } = useQuery({
    queryKey: ['cal-tasks', year, month],
    queryFn: () => api.get('/tasks', { params: { due_date_from: dateFrom, due_date_to: dateTo, limit: 100 } })
      .then(r => (r.data?.items || r.data || []).map(t => ({
        date: t.due_date, type: 'task', title: t.title, id: t.id, status: t.status,
      }))).catch(() => []),
  })

  // Milestones
  const { data: milestones = [] } = useQuery({
    queryKey: ['cal-milestones', year, month],
    queryFn: () => api.get('/projects/milestones', { params: { date_from: dateFrom, date_to: dateTo } })
      .then(r => (r.data || []).map(m => ({
        date: m.due_date, type: 'milestone', title: m.title, id: m.id,
      }))).catch(() => []),
  })

  // Sprints
  const { data: sprints = [] } = useQuery({
    queryKey: ['cal-sprints', year, month],
    queryFn: () => api.get('/sprints', { params: { limit: 20 } })
      .then(r => (r.data?.items || r.data || []).flatMap(s => [
        s.start_date ? { date: s.start_date, type: 'sprint', title: `${s.name} (inicio)`, id: s.id + '_s' } : null,
        s.end_date   ? { date: s.end_date,   type: 'sprint', title: `${s.name} (fin)`,   id: s.id + '_e' } : null,
      ].filter(Boolean))).catch(() => []),
  })

  // Ausencias
  const { data: absences = [] } = useQuery({
    queryKey: ['cal-absences', year, month],
    queryFn: () => api.get('/absences', { params: { date_from: dateFrom, date_to: dateTo, limit: 50 } })
      .then(r => (r.data?.items || r.data || []).map(a => ({
        date: a.start_date, type: 'absence', title: `${a.user_name || 'Equipo'}: ${a.type || 'Ausencia'}`, id: a.id,
      }))).catch(() => []),
  })

  // Todos los eventos del mes
  const allEvents = [...tasks, ...milestones, ...sprints, ...absences]
    .filter(e => e.date && e.date.startsWith(`${year}-${String(month+1).padStart(2,'0')}`))
    .filter(e => filter === 'all' || e.type === filter)

  // Agrupar por día
  const eventsByDay = {}
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
    <div style={{ padding: 32 }}>
      <PageHeader icon={<Calendar size={18} />} title={t('calendar.title')} subtitle={t('calendar.subtitle')} />

      {/* Controles */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 20 }}>
        <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
          <button onClick={prevMonth} style={{ background: 'var(--surface-2)', border: '1px solid var(--surface-4)', borderRadius: 8, color: 'var(--text-1)', padding: '6px 12px', cursor: 'pointer', fontFamily: 'inherit', fontSize: 16 }}>‹</button>
          <div style={{ fontSize: 18, fontWeight: 800, minWidth: 200, textAlign: 'center' }}>{MONTHS[month]} {year}</div>
          <button onClick={nextMonth} style={{ background: 'var(--surface-2)', border: '1px solid var(--surface-4)', borderRadius: 8, color: 'var(--text-1)', padding: '6px 12px', cursor: 'pointer', fontFamily: 'inherit', fontSize: 16 }}>›</button>
          <button onClick={() => { setYear(now.getFullYear()); setMonth(now.getMonth()) }}
            style={{ background: 'transparent', border: '1px solid var(--surface-4)', borderRadius: 8, color: 'var(--text-2)', padding: '6px 12px', cursor: 'pointer', fontFamily: 'inherit', fontSize: 12 }}>
            Hoy
          </button>
        </div>

        {/* Filtros */}
        <div style={{ display: 'flex', gap: 6 }}>
          {[['all', 'Todo'], ...Object.entries(EVENT_TYPES).map(([k, v]) => [k, v.label])].map(([k, label]) => (
            <button key={k} onClick={() => setFilter(k)}
              style={{ padding: '5px 12px', borderRadius: 20, border: `1px solid ${filter === k ? EVENT_TYPES[k]?.color || 'var(--accent)' : 'var(--surface-4)'}`,
                background: filter === k ? (EVENT_TYPES[k]?.color || 'var(--accent)') + '15' : 'transparent',
                color: filter === k ? (EVENT_TYPES[k]?.color || 'var(--accent)') : 'var(--text-2)',
                fontSize: 11, fontWeight: filter === k ? 700 : 400, cursor: 'pointer', fontFamily: 'inherit' }}>
              {k !== 'all' && EVENT_TYPES[k]?.icon + ' '}{label}
            </button>
          ))}
        </div>
      </div>

      {/* Leyenda */}
      <div style={{ display: 'flex', gap: 16, marginBottom: 16, flexWrap: 'wrap' }}>
        {Object.entries(EVENT_TYPES).map(([k, v]) => (
          <span key={k} style={{ fontSize: 11, color: 'var(--text-2)', display: 'flex', gap: 5, alignItems: 'center' }}>
            <span style={{ width: 8, height: 8, borderRadius: '50%', background: v.color, display: 'inline-block' }} />
            {v.label}
          </span>
        ))}
        <span style={{ marginLeft: 'auto', fontSize: 11, color: 'var(--text-2)' }}>
          {allEvents.length} evento(s) este mes
        </span>
      </div>

      {/* Cabecera días */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(7, 1fr)', gap: 4, marginBottom: 4 }}>
        {DAYS.map(d => (
          <div key={d} style={{ textAlign: 'center', fontSize: 11, fontWeight: 700, color: 'var(--text-2)',
            padding: '8px 4px', textTransform: 'uppercase', letterSpacing: '0.08em' }}>
            {d}
          </div>
        ))}
      </div>

      {/* Grid del calendario */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(7, 1fr)', gap: 4 }}>
        {cells.map((day, i) => {
          if (day === null) return <div key={`empty-${i}`} style={{ minHeight: 100 }} />
          const isToday = isCurrentMonth && day === today
          const dayEvents = eventsByDay[day] || []
          return (
            <div key={day} style={{
              minHeight: 100,
              border: `1px solid ${isToday ? 'var(--accent-glow)' : 'var(--surface-4)'}`,
              borderRadius: 8, padding: '8px 6px',
              background: isToday ? 'var(--accent-muted)' : 'var(--surface-2)',
            }}>
              <div style={{
                fontSize: 13, fontWeight: isToday ? 800 : 400,
                color: isToday ? 'var(--accent)' : 'var(--text-2)',
                marginBottom: 4,
                ...(isToday ? { background: 'var(--accent)', color: '#000', width: 22, height: 22, borderRadius: '50%', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 11 } : {})
              }}>{day}</div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
                {dayEvents.slice(0, 3).map(e => {
                  const cfg = EVENT_TYPES[e.type] || {}
                  return (
                    <div key={e.id} title={e.title}
                      style={{ fontSize: 10, padding: '2px 5px', borderRadius: 4, borderLeft: `2px solid ${cfg.color}`,
                        background: cfg.color + '15', color: 'var(--text-1)',
                        overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', cursor: 'pointer' }}>
                      {cfg.icon} {e.title}
                    </div>
                  )
                })}
                {dayEvents.length > 3 && (
                  <div style={{ fontSize: 10, color: 'var(--text-2)', padding: '1px 4px' }}>+{dayEvents.length - 3} más</div>
                )}
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}
