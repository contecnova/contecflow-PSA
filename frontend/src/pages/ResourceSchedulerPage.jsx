/**
 * ResourceSchedulerPage — visual resource scheduler (Runn/Parallax-style)
 *
 * - Timeline grid: people as rows, weeks as columns
 * - Heat-shaded cells: utilization % from /resource-forecast/weeks
 * - Bookings rendered as project-colored spans across cells
 * - Drag-create: mousedown on empty cell → drag right → mouseup POSTs booking
 * - Drag-move:   mousedown on existing booking → drag → PATCH booking dates
 * - Inline panel to set project + hours_per_day on new/edit booking
 * - Keyboard: Esc cancels drag · Delete removes selected booking
 */
import { useState, useRef, useCallback, useMemo, useEffect } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useToast } from '../context/ToastContext'
import api, { projectsApi } from '../services/api'
import PageHeader from '../components/layout/PageHeader'
import { Spinner, EmptyState } from '../components/ui'
import { useAppT } from '../i18n/AppLangContext'

// ── Constants ────────────────────────────────────────────────────────────────

const CELL_W  = 56   // px per week column
const ROW_H   = 44   // px per user row
const LABEL_W = 200  // px for the name column
const HDR_H   = 60   // header height

const UTIL_COLORS = [
  [0,   10,  '#1e2d45'],  // available
  [10,  50,  '#1a3a5c'],
  [50,  80,  '#1e4a7a'],
  [80,  100, '#2d6099'],
  [100, 120, '#c2410c'],  // overloaded
  [120, 999, '#991b1b'],
]

const PROJECT_PALETTE = [
  '#4f8ef7','#34d399','#f59e0b','#f87171','#a78bfa',
  '#38bdf8','#fb923c','#6ee7b7','#c084fc','#f472b6',
]

function utilColor(pct) {
  for (const [lo, hi, c] of UTIL_COLORS) {
    if (pct >= lo && pct < hi) return c
  }
  return UTIL_COLORS[UTIL_COLORS.length - 1][2]
}

function monday(d) {
  const r = new Date(d)
  r.setDate(r.getDate() - ((r.getDay() + 6) % 7))
  r.setHours(0, 0, 0, 0)
  return r
}
function addWeeks(d, n) { const r = new Date(d); r.setDate(r.getDate() + n * 7); return r }
function fmtISO(d) { return d.toISOString().slice(0, 10) }
function weekLabel(d) {
  return `${d.getDate().toString().padStart(2,'0')}/${(d.getMonth()+1).toString().padStart(2,'0')}`
}

// ── Project color map ─────────────────────────────────────────────────────────

function useProjectColorMap(projects) {
  return useMemo(() => {
    const m = {}
    projects.forEach((p, i) => { m[p.id] = PROJECT_PALETTE[i % PROJECT_PALETTE.length] })
    return m
  }, [projects])
}

// ── Booking bar ──────────────────────────────────────────────────────────────

function BookingBar({ booking, weekStart, weekCount, color, isSelected, onMouseDown, onClick, t }) {
  const bStart = new Date(booking.start_date + 'T00:00:00')
  const bEnd   = new Date(booking.end_date   + 'T00:00:00')
  const gridStart = weekStart

  const startWeek = Math.max(0, Math.round((monday(bStart) - monday(gridStart)) / 604800000))
  const endWeek   = Math.min(weekCount - 1, Math.round((monday(bEnd) - monday(gridStart)) / 604800000))

  if (startWeek > weekCount || endWeek < 0) return null

  const x = startWeek * CELL_W + 2
  const w = Math.max((endWeek - startWeek + 1) * CELL_W - 4, CELL_W - 4)

  return (
    <div
      onMouseDown={e => { e.stopPropagation(); onMouseDown(e) }}
      onClick={e => { e.stopPropagation(); onClick() }}
      title={`${booking.project_name || booking.project_id || t('resource_scheduler.no_project_short')} · ${booking.hours_per_day || 8}h/día · ${booking.booking_type || 'soft'}`}
      style={{
        position: 'absolute',
        left: x, top: 6, height: ROW_H - 12, width: w,
        background: color + (isSelected ? 'ff' : 'cc'),
        borderRadius: 6,
        border: isSelected ? `2px solid #fff` : `1px solid ${color}`,
        display: 'flex', alignItems: 'center', padding: '0 8px',
        cursor: 'grab', userSelect: 'none', overflow: 'hidden',
        boxShadow: isSelected ? `0 0 0 2px ${color}` : 'none',
        zIndex: isSelected ? 10 : 5,
        transition: 'box-shadow 0.1s',
      }}
    >
      <span style={{ fontSize: 10, fontWeight: 700, color: '#fff', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
        {booking.project_name || booking.project_id || '—'} · {booking.hours_per_day || 8}h
      </span>
    </div>
  )
}

// ── Booking panel (create/edit) ───────────────────────────────────────────────

function BookingPanel({ booking, position, projects, onSave, onDelete, onClose, t }) {
  const [projectId, setProjectId] = useState(booking.project_id || '')
  const [hoursPerDay, setHours]   = useState(booking.hours_per_day || 8)
  const [bookingType, setType]    = useState(booking.booking_type || 'soft')
  const isNew = !booking.id

  return (
    <div style={{
      position: 'fixed', zIndex: 200,
      left: Math.min(position.x + 8, window.innerWidth - 260),
      top:  Math.min(position.y + 8, window.innerHeight - 280),
      width: 240,
      background: '#0d1424', border: '1px solid #1e2d45',
      borderRadius: 12, padding: 16,
      boxShadow: '0 16px 48px rgba(0,0,0,0.7)',
      fontFamily: 'var(--font-sans)',
    }}>
      <div style={{ fontSize: 12, fontWeight: 700, color: 'var(--text-1)', marginBottom: 12 }}>
        {isNew ? t('resource_scheduler.new_booking') : t('resource_scheduler.edit_booking')}
      </div>

      <label style={{ fontSize: 11, color: 'var(--text-3)', display: 'block', marginBottom: 4 }}>{t('resource_scheduler.project')}</label>
      <select value={projectId} onChange={e => setProjectId(e.target.value)} style={{
        width: '100%', background: 'var(--surface-3)', border: '1px solid var(--surface-4)',
        borderRadius: 6, padding: '5px 8px', color: 'var(--text-1)',
        fontSize: 12, outline: 'none', fontFamily: 'inherit', marginBottom: 10,
      }}>
        <option value="">{t('resource_scheduler.no_project')}</option>
        {projects.map(p => (
          <option key={p.id} value={p.id}>{p.code} – {p.name}</option>
        ))}
      </select>

      <label style={{ fontSize: 11, color: 'var(--text-3)', display: 'block', marginBottom: 4 }}>{t('resource_scheduler.hours_per_day')}</label>
      <input type="number" min={1} max={24} value={hoursPerDay} onChange={e => setHours(Number(e.target.value))} style={{
        width: '100%', background: 'var(--surface-3)', border: '1px solid var(--surface-4)',
        borderRadius: 6, padding: '5px 8px', color: 'var(--text-1)',
        fontSize: 12, outline: 'none', fontFamily: 'inherit', marginBottom: 10, boxSizing: 'border-box',
      }} />

      <label style={{ fontSize: 11, color: 'var(--text-3)', display: 'block', marginBottom: 4 }}>{t('resource_scheduler.type')}</label>
      <div style={{ display: 'flex', gap: 6, marginBottom: 14 }}>
        {['soft', 'hard'].map(typeOption => (
          <button key={typeOption} onClick={() => setType(typeOption)} style={{
            flex: 1, padding: '4px 0', border: `1px solid ${bookingType === typeOption ? 'var(--accent)' : 'var(--surface-4)'}`,
            background: bookingType === typeOption ? 'var(--accent-muted)' : 'transparent',
            color: bookingType === typeOption ? 'var(--accent)' : 'var(--text-3)',
            borderRadius: 6, cursor: 'pointer', fontSize: 11, fontFamily: 'inherit', fontWeight: bookingType === typeOption ? 700 : 400,
          }}>
            {typeOption === 'soft' ? t('resource_scheduler.tentative') : t('resource_scheduler.confirmed')}
          </button>
        ))}
      </div>

      <div style={{ display: 'flex', gap: 6 }}>
        <button onClick={() => onSave({ project_id: projectId || null, hours_per_day: hoursPerDay, booking_type: bookingType })} style={{
          flex: 1, padding: '7px 0', background: 'var(--accent)', border: 'none',
          borderRadius: 7, color: '#fff', cursor: 'pointer', fontSize: 12, fontFamily: 'inherit', fontWeight: 600,
        }}>
          {isNew ? t('resource_scheduler.create') : t('resource_scheduler.save')}
        </button>
        {!isNew && (
          <button onClick={onDelete} style={{
            padding: '7px 10px', background: 'var(--danger)', border: 'none',
            borderRadius: 7, color: '#fff', cursor: 'pointer', fontSize: 12, fontFamily: 'inherit',
          }}>🗑</button>
        )}
        <button onClick={onClose} style={{
          padding: '7px 10px', background: 'var(--surface-3)', border: '1px solid var(--surface-4)',
          borderRadius: 7, color: 'var(--text-2)', cursor: 'pointer', fontSize: 12, fontFamily: 'inherit',
        }}>✕</button>
      </div>
    </div>
  )
}

// ── Main page ────────────────────────────────────────────────────────────────

export default function ResourceSchedulerPage() {
  const t = useAppT()
  const toast  = useToast()
  const qc     = useQueryClient()

  const [weeks, setWeeks]             = useState(12)
  const [department, setDepartment]   = useState('')
  const [viewMode, setViewMode]       = useState('scheduler')  // 'scheduler' | 'assign'
  const [selectedBooking, setSelected] = useState(null)
  const [panel, setPanel]             = useState(null)  // { booking, position, userId, startDate, endDate }
  const [dragState, setDragState]     = useState(null)  // { userId, startCol }

  const gridRef       = useRef(null)
  // assign-mode drag refs
  const assignDragUser    = useRef(null)
  const assignGhostRef    = useRef(null)
  const assignDropProject = useRef(null)
  const today   = monday(new Date())
  const weekDates = useMemo(() => Array.from({ length: weeks }, (_, i) => addWeeks(today, i)), [today, weeks])

  // ── Data ──────────────────────────────────────────────────────────────────
  const { data: projects = [] } = useQuery({
    queryKey: ['projects'],
    queryFn:  () => projectsApi.list().then(r => r.data),
  })

  const { data: forecastData, isLoading } = useQuery({
    queryKey: ['resource-forecast', weeks, department],
    queryFn:  () => {
      const params = { weeks, ...(department ? { department } : {}) }
      return api.get('/resource-forecast/weeks', { params }).then(r => r.data)
    },
    staleTime: 30000,
  })

  const { data: bookingsData = [] } = useQuery({
    queryKey: ['bookings'],
    queryFn:  () => api.get('/bookings', { params: { page_size: 500 } })
      .then(r => Array.isArray(r.data) ? r.data : (r.data?.items || [])),
    staleTime: 15000,
  })

  const { mutate: createBooking } = useMutation({
    mutationFn: b => api.post('/bookings', b),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['bookings'] }); qc.invalidateQueries({ queryKey: ['resource-forecast'] }); toast.success(t('resource_scheduler.booking_created')) },
    onError: e => toast.error(e?.response?.data?.detail || t('resource_scheduler.create_error')),
  })

  const { mutate: updateBooking } = useMutation({
    mutationFn: ({ id, ...data }) => api.patch(`/bookings/${id}`, data),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['bookings'] }); qc.invalidateQueries({ queryKey: ['resource-forecast'] }); toast.success(t('resource_scheduler.booking_updated')) },
    onError: e => toast.error(e?.response?.data?.detail || t('resource_scheduler.update_error')),
  })

  const { mutate: deleteBooking } = useMutation({
    mutationFn: id => api.delete(`/bookings/${id}`),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['bookings'] }); qc.invalidateQueries({ queryKey: ['resource-forecast'] }); toast.success(t('resource_scheduler.booking_deleted')) },
    onError: e => toast.error(e?.response?.data?.detail || t('resource_scheduler.delete_error')),
  })

  const projectColorMap = useProjectColorMap(projects)

  // Build project name map
  const projNameMap = useMemo(() => {
    const m = {}
    projects.forEach(p => { m[p.id] = p.name })
    return m
  }, [projects])

  // Enrich bookings with project names
  const bookings = useMemo(() => bookingsData.map(b => ({
    ...b,
    project_name: projNameMap[b.project_id] || null,
  })), [bookingsData, projNameMap])

  // Build department list
  const departments = useMemo(() => {
    const s = new Set()
    ;(forecastData?.users || []).forEach(u => { if (u.department) s.add(u.department) })
    return [...s]
  }, [forecastData])

  // ── Keyboard ─────────────────────────────────────────────────────────────
  useEffect(() => {
    const handler = e => {
      if (e.key === 'Escape') { setPanel(null); setDragState(null); setSelected(null) }
      if ((e.key === 'Delete' || e.key === 'Backspace') && selectedBooking) {
        setPanel(null)
        deleteBooking(selectedBooking.id)
        setSelected(null)
      }
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [selectedBooking, deleteBooking])

  // ── Drag to create booking ────────────────────────────────────────────────
  const handleCellMouseDown = useCallback((e, userId, colIndex) => {
    if (panel) { setPanel(null); return }
    e.preventDefault()
    const startCol = colIndex
    setDragState({ userId, startCol, endCol: colIndex })

    const onMove = (me) => {
      const gridLeft = gridRef.current?.getBoundingClientRect().left || 0
      const scrollLeft = gridRef.current?.scrollLeft || 0
      const relX = me.clientX - gridLeft + scrollLeft - LABEL_W
      const col = Math.max(0, Math.min(weeks - 1, Math.floor(relX / CELL_W)))
      setDragState(prev => prev ? { ...prev, endCol: col } : null)
    }

    const onUp = (me) => {
      document.removeEventListener('mousemove', onMove)
      document.removeEventListener('mouseup', onUp)
      setDragState(prev => {
        if (!prev) return null
        const s = Math.min(prev.startCol, prev.endCol)
        const end = Math.max(prev.startCol, prev.endCol)
        const startDate = fmtISO(weekDates[s])
        const endDate   = fmtISO(addWeeks(weekDates[end], 1) > weekDates[weeks - 1] ? weekDates[end] : addWeeks(weekDates[end], 1))
        setPanel({
          booking: { user_id: userId, start_date: startDate, end_date: endDate, project_id: '', hours_per_day: 8, booking_type: 'soft' },
          position: { x: me.clientX, y: me.clientY },
          isNew: true,
        })
        return null
      })
    }

    document.addEventListener('mousemove', onMove)
    document.addEventListener('mouseup', onUp)
  }, [panel, weekDates, weeks])

  // ── Drag to move booking ──────────────────────────────────────────────────
  const handleBookingMouseDown = useCallback((e, booking) => {
    e.preventDefault()
    const origStart  = new Date(booking.start_date + 'T00:00:00')
    const origEnd    = new Date(booking.end_date   + 'T00:00:00')
    const startX     = e.clientX
    let ghost = null
    let lastDWeeks = 0

    const onMove = (me) => {
      const dx     = me.clientX - startX
      const dWeeks = Math.round(dx / CELL_W)

      if (!ghost && Math.abs(dx) > 8) {
        ghost = document.createElement('div')
        ghost.style.cssText = `position:fixed;z-index:9999;pointer-events:none;background:var(--surface-2);border:1.5px solid var(--accent);border-radius:8px;padding:6px 12px;font-size:12px;font-weight:700;color:var(--accent);box-shadow:0 8px 32px rgba(0,0,0,.5);white-space:nowrap;`
        document.body.appendChild(ghost)
      }
      if (ghost) {
        ghost.style.left = (me.clientX + 14) + 'px'
        ghost.style.top  = (me.clientY - 20) + 'px'
        if (dWeeks !== lastDWeeks) {
          lastDWeeks = dWeeks
          const tmpS = new Date(origStart); tmpS.setDate(tmpS.getDate() + dWeeks * 7)
          const tmpE = new Date(origEnd);   tmpE.setDate(tmpE.getDate() + dWeeks * 7)
          ghost.textContent = `${fmtISO(tmpS)} → ${fmtISO(tmpE)}`
        }
      }
    }

    const onUp = (me) => {
      document.removeEventListener('mousemove', onMove)
      document.removeEventListener('mouseup', onUp)
      if (ghost) { ghost.remove(); ghost = null }
      const dx     = me.clientX - startX
      const dWeeks = Math.round(dx / CELL_W)
      if (dWeeks === 0) return
      const newStart = new Date(origStart)
      const newEnd   = new Date(origEnd)
      newStart.setDate(newStart.getDate() + dWeeks * 7)
      newEnd.setDate(newEnd.getDate()     + dWeeks * 7)
      updateBooking({ id: booking.id, start_date: fmtISO(newStart), end_date: fmtISO(newEnd) })
    }

    document.addEventListener('mousemove', onMove)
    document.addEventListener('mouseup', onUp)
  }, [updateBooking])

  // ── Assign-mode: drag person chip onto project row ────────────────────────
  const handlePersonDragStart = useCallback((e, user) => {
    if (e.button !== 0) return
    const startX = e.clientX
    const startY = e.clientY
    let dragging = false

    const onMove = ev => {
      if (!dragging) {
        const dx = ev.clientX - startX, dy = ev.clientY - startY
        if (Math.sqrt(dx * dx + dy * dy) < 5) return
        dragging = true
        assignDragUser.current = user

        const ghost = document.createElement('div')
        ghost.textContent = user.user_name.split(' ')[0]
        Object.assign(ghost.style, {
          position: 'fixed', zIndex: 9999, pointerEvents: 'none',
          background: '#1e3660', border: '1px solid var(--accent)',
          borderRadius: '16px', padding: '4px 12px',
          color: 'var(--accent)', fontSize: '11px', fontWeight: 700,
          fontFamily: 'var(--font-sans)', boxShadow: '0 4px 16px rgba(0,0,0,0.5)',
          left: ev.clientX + 12 + 'px', top: ev.clientY + 8 + 'px',
        })
        document.body.appendChild(ghost)
        assignGhostRef.current = ghost
      } else if (assignGhostRef.current) {
        assignGhostRef.current.style.left = ev.clientX + 12 + 'px'
        assignGhostRef.current.style.top  = ev.clientY + 8 + 'px'
      }
    }

    const onUp = ev => {
      document.removeEventListener('mousemove', onMove)
      document.removeEventListener('mouseup', onUp)
      if (assignGhostRef.current) { assignGhostRef.current.remove(); assignGhostRef.current = null }
      if (dragging && assignDragUser.current && assignDropProject.current) {
        const startDate = fmtISO(monday(new Date()))
        const endDate   = fmtISO(addWeeks(monday(new Date()), 4))
        setPanel({
          booking: {
            user_id: assignDragUser.current.user_id,
            project_id: assignDropProject.current,
            start_date: startDate,
            end_date: endDate,
            hours_per_day: 8,
            booking_type: 'soft',
          },
          position: { x: ev.clientX, y: ev.clientY },
          isNew: true,
        })
      }
      assignDragUser.current = null
      assignDropProject.current = null
    }

    document.addEventListener('mousemove', onMove)
    document.addEventListener('mouseup', onUp)
  }, [])

  const users = forecastData?.users || []

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: 'calc(100vh - 52px)', background: 'var(--surface-0)' }}>
      {/* Header */}
      <div style={{ padding: '16px 24px 8px', flexShrink: 0 }}>
        <PageHeader
          title={t('resource_scheduler.title')}
          subtitle={viewMode === 'assign' ? t('resource_scheduler.subtitle_assign') : t('resource_scheduler.subtitle_scheduler')}
          actions={
            <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
              {/* View mode toggle */}
              {['scheduler', 'assign'].map(mode => (
                <button key={mode} onClick={() => setViewMode(mode)} style={{
                  padding: '4px 12px', borderRadius: 6,
                  border: `1px solid ${viewMode === mode ? 'rgba(79,142,247,0.4)' : 'var(--surface-4)'}`,
                  background: viewMode === mode ? 'var(--accent-muted)' : 'transparent',
                  color: viewMode === mode ? 'var(--accent)' : 'var(--text-3)',
                  fontSize: 11, cursor: 'pointer', fontFamily: 'var(--font-sans)',
                }}>
                  {mode === 'scheduler' ? t('resource_scheduler.scheduler_mode') : t('resource_scheduler.assign_mode')}
                </button>
              ))}
              {departments.length > 0 && (
                <select value={department} onChange={e => setDepartment(e.target.value)} style={{
                  background: 'var(--surface-3)', border: '1px solid var(--surface-4)',
                  borderRadius: 8, padding: '5px 10px', color: 'var(--text-1)', fontSize: 12,
                  outline: 'none', fontFamily: 'var(--font-sans)',
                }}>
                  <option value="">{t('resource_scheduler.all_departments')}</option>
                  {departments.map(d => <option key={d} value={d}>{d}</option>)}
                </select>
              )}
              {[8, 12, 16, 24].map(w => (
                <button key={w} onClick={() => setWeeks(w)} style={{
                  padding: '4px 10px', borderRadius: 6,
                  border: `1px solid ${weeks === w ? 'rgba(79,142,247,0.4)' : 'var(--surface-4)'}`,
                  background: weeks === w ? 'var(--accent-muted)' : 'transparent',
                  color: weeks === w ? 'var(--accent)' : 'var(--text-3)',
                  fontSize: 11, cursor: 'pointer', fontFamily: 'var(--font-sans)',
                }}>
                  {w}s
                </button>
              ))}
            </div>
          }
        />
      </div>

      {/* Legend */}
      <div style={{ padding: '0 24px 8px', display: 'flex', gap: 16, alignItems: 'center', flexShrink: 0, flexWrap: 'wrap' }}>
        {[[t('resource_scheduler.legend_available'),'#1e2d45'],[t('resource_scheduler.legend_lt_50'),'#1e4a7a'],[t('resource_scheduler.legend_50_80'),'#2d6099'],[t('resource_scheduler.legend_80_100'),'#4f8ef7'],[t('resource_scheduler.legend_overloaded'),'#c2410c']].map(([l,c]) => (
          <span key={l} style={{ display: 'flex', alignItems: 'center', gap: 5, fontSize: 11, color: 'var(--text-3)' }}>
            <div style={{ width: 12, height: 12, borderRadius: 3, background: c }} />{l}
          </span>
        ))}
        <span style={{ marginLeft: 'auto', fontSize: 10, color: 'var(--text-4)' }}>{t('resource_scheduler.legend_shortcuts')}</span>
      </div>

      {isLoading ? (
        <div style={{ flex: 1, display: 'flex', justifyContent: 'center', alignItems: 'center' }}>
          <Spinner size={32} />
        </div>
      ) : users.length === 0 ? (
        <div style={{ flex: 1, display: 'flex', justifyContent: 'center', alignItems: 'center' }}>
          <EmptyState icon="👥" title={t('resource_scheduler.no_active_users')} description={t('resource_scheduler.no_active_users_desc')} />
        </div>
      ) : viewMode === 'assign' ? (
        /* ── Assign view: drag person chip → project row ───────────────────── */
        <div style={{ flex: 1, display: 'flex', overflow: 'hidden', padding: '0 24px 24px', gap: 16 }}>
          {/* People panel */}
          <div style={{ width: 160, flexShrink: 0, overflowY: 'auto', background: 'var(--surface-1)', border: '1px solid #1e2d45', borderRadius: 10, padding: 12 }}>
            <div style={{ fontSize: 10, fontWeight: 700, color: 'var(--text-3)', textTransform: 'uppercase', letterSpacing: '.07em', marginBottom: 10 }}>
              {t('resource_scheduler.people')}
            </div>
            {users.map(u => (
              <div
                key={u.user_id}
                onMouseDown={e => handlePersonDragStart(e, u)}
                title={`${u.user_name} · ${u.avg_load_pct}% ${t('dashboard.load_label').toLowerCase()} · ${t('resource_scheduler.person_drag_hint')}`}
                style={{
                  display: 'flex', alignItems: 'center', gap: 7,
                  padding: '7px 8px', marginBottom: 4, borderRadius: 8,
                  background: 'var(--surface-2)', border: '1px solid var(--surface-4)',
                  cursor: 'grab', userSelect: 'none',
                }}
              >
                <div style={{
                  width: 22, height: 22, borderRadius: '50%', background: 'var(--accent-glow)',
                  border: '1px solid var(--accent)', display: 'flex', alignItems: 'center',
                  justifyContent: 'center', fontSize: 9, fontWeight: 700, color: 'var(--accent)', flexShrink: 0,
                }}>
                  {u.user_name.slice(0, 1).toUpperCase()}
                </div>
                <div style={{ overflow: 'hidden' }}>
                  <div style={{ fontSize: 11, color: 'var(--text-1)', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                    {u.user_name.split(' ')[0]}
                  </div>
                  <div style={{ fontSize: 9, color: u.avg_load_pct >= 100 ? '#f87171' : 'var(--text-4)' }}>
                    {u.avg_load_pct}%
                  </div>
                </div>
              </div>
            ))}
          </div>

          {/* Project rows grid */}
          <div ref={gridRef} style={{ flex: 1, overflowX: 'auto' }}>
            <div style={{ display: 'grid', gridTemplateColumns: `${LABEL_W}px 1fr`, border: '1px solid #1e2d45', borderRadius: 10, overflow: 'hidden', background: 'var(--surface-1)', minWidth: LABEL_W + weekDates.length * CELL_W }}>
              {/* Corner */}
              <div style={{ height: HDR_H, borderRight: '1px solid #1e2d45', background: '#0a1120', display: 'flex', alignItems: 'flex-end', padding: '0 14px 8px' }}>
                <span style={{ fontSize: 10, fontWeight: 700, color: 'var(--text-3)', textTransform: 'uppercase', letterSpacing: '.07em' }}>{t('resource_scheduler.project')}</span>
              </div>
              {/* Week headers */}
              <div style={{ height: HDR_H, background: '#0a1120', borderBottom: '1px solid #1e2d45', display: 'flex', alignItems: 'flex-end' }}>
                {weekDates.map((w, i) => {
                  const isToday = fmtISO(w) === fmtISO(today)
                  return (
                    <div key={i} style={{
                      width: CELL_W, flexShrink: 0, borderLeft: '1px solid #1e2d4530',
                      height: '100%', display: 'flex', flexDirection: 'column', justifyContent: 'flex-end', padding: '0 4px 6px',
                      background: isToday ? 'rgba(79,142,247,0.08)' : 'transparent',
                    }}>
                      {i === 0 || w.getDate() <= 7 ? (
                        <div style={{ fontSize: 9, color: 'var(--text-4)', marginBottom: 2 }}>
                          {w.toLocaleString(undefined, { month: 'short' }).toUpperCase()}
                        </div>
                      ) : null}
                      <div style={{ fontSize: 10, fontWeight: isToday ? 700 : 400, color: isToday ? 'var(--accent)' : 'var(--text-3)' }}>
                        {weekLabel(w)}
                      </div>
                    </div>
                  )
                })}
              </div>

              {/* Project rows */}
              {projects.slice(0, 40).map(proj => {
                const projBookings = bookings.filter(b => b.project_id === proj.id)
                const color = projectColorMap[proj.id] || '#4f8ef7'
                return (
                  <div key={proj.id} style={{ display: 'contents' }}>
                    <div style={{
                      height: ROW_H, borderRight: '1px solid #1e2d45', borderTop: '1px solid #1e2d4530',
                      display: 'flex', alignItems: 'center', padding: '0 10px', gap: 6,
                    }}>
                      <div style={{ width: 8, height: 8, borderRadius: '50%', background: color, flexShrink: 0 }} />
                      <div style={{ overflow: 'hidden' }}>
                        <div style={{ fontSize: 11, color: 'var(--text-1)', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{proj.name}</div>
                        <div style={{ fontSize: 9, color: 'var(--text-4)' }}>{proj.code}</div>
                      </div>
                    </div>
                    <div
                      onMouseEnter={() => { assignDropProject.current = proj.id }}
                      onMouseLeave={() => { assignDropProject.current = null }}
                      style={{
                        height: ROW_H, borderTop: '1px solid #1e2d4530', position: 'relative', display: 'flex',
                        cursor: 'copy',
                      }}
                    >
                      {weekDates.map((_, colIdx) => (
                        <div key={colIdx} style={{
                          width: CELL_W, flexShrink: 0, height: '100%',
                          borderLeft: '1px solid #1e2d4530',
                          background: 'transparent',
                        }} />
                      ))}
                      {projBookings.map(b => (
                        <BookingBar
                          key={b.id}
                          booking={b}
                          weekStart={weekDates[0]}
                          weekCount={weeks}
                          color={color}
                          t={t}
                          isSelected={selectedBooking?.id === b.id}
                          onMouseDown={e => handleBookingMouseDown(e, b)}
                          onClick={() => {
                            setSelected(b)
                            setPanel({ booking: b, position: { x: 200, y: 200 }, isNew: false })
                          }}
                        />
                      ))}
                    </div>
                  </div>
                )
              })}
            </div>
          </div>
        </div>
      ) : (
        <div ref={gridRef} style={{ flex: 1, overflow: 'auto', padding: '0 24px 24px' }}>
          <div style={{ display: 'grid', gridTemplateColumns: `${LABEL_W}px 1fr`, border: '1px solid #1e2d45', borderRadius: 10, overflow: 'hidden', background: 'var(--surface-1)', minWidth: LABEL_W + weekDates.length * CELL_W }}>

            {/* Label column header */}
            <div style={{ height: HDR_H, borderRight: '1px solid #1e2d45', background: '#0a1120', display: 'flex', alignItems: 'flex-end', padding: '0 14px 8px' }}>
              <span style={{ fontSize: 10, fontWeight: 700, color: 'var(--text-3)', textTransform: 'uppercase', letterSpacing: '.07em' }}>{t('resource_scheduler.people')}</span>
            </div>

            {/* Week headers */}
            <div style={{ height: HDR_H, background: '#0a1120', borderBottom: '1px solid #1e2d45', display: 'flex', alignItems: 'flex-end' }}>
              {weekDates.map((w, i) => {
                const isToday = fmtISO(w) === fmtISO(today)
                return (
                  <div key={i} style={{
                    width: CELL_W, flexShrink: 0, borderLeft: '1px solid #1e2d4530',
                    height: '100%', display: 'flex', flexDirection: 'column', justifyContent: 'flex-end', padding: '0 4px 6px',
                    background: isToday ? 'rgba(79,142,247,0.08)' : 'transparent',
                  }}>
                    {i === 0 || w.getDate() <= 7 ? (
                      <div style={{ fontSize: 9, color: 'var(--text-4)', marginBottom: 2 }}>
                        {w.toLocaleString(undefined, { month: 'short' }).toUpperCase()}
                      </div>
                    ) : null}
                    <div style={{ fontSize: 10, fontWeight: isToday ? 700 : 400, color: isToday ? 'var(--accent)' : 'var(--text-3)' }}>
                      {weekLabel(w)}
                    </div>
                  </div>
                )
              })}
            </div>

            {/* User rows */}
            {users.map(user => {
              const userBookings = bookings.filter(b => b.user_id === user.user_id)

              return (
                <div key={user.user_id} style={{ display: 'contents' }}>
                  {/* Label */}
                  <div style={{
                    height: ROW_H, borderRight: '1px solid #1e2d45', borderTop: '1px solid #1e2d4530',
                    display: 'flex', alignItems: 'center', padding: '0 14px', gap: 8,
                  }}>
                    <div style={{
                      width: 24, height: 24, borderRadius: '50%', background: 'var(--accent-glow)',
                      border: '1px solid var(--accent)', display: 'flex', alignItems: 'center',
                      justifyContent: 'center', fontSize: 10, fontWeight: 700, color: 'var(--accent)', flexShrink: 0,
                    }}>
                      {user.user_name.slice(0, 1).toUpperCase()}
                    </div>
                    <div style={{ overflow: 'hidden' }}>
                      <div style={{ fontSize: 12, color: 'var(--text-1)', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{user.user_name}</div>
                      <div style={{ fontSize: 9, color: 'var(--text-4)' }}>{user.capacity_hours}h/sem · {user.avg_load_pct}% avg</div>
                    </div>
                  </div>

                  {/* Grid row */}
                  <div style={{ height: ROW_H, borderTop: '1px solid #1e2d4530', position: 'relative', display: 'flex' }}>
                    {/* Utilization cells */}
                    {weekDates.map((w, colIdx) => {
                      const weekData   = user.weeks?.[colIdx]
                      const loadPct    = weekData?.load_pct || 0
                      const isDrag     = dragState?.userId === user.user_id &&
                        colIdx >= Math.min(dragState.startCol, dragState.endCol) &&
                        colIdx <= Math.max(dragState.startCol, dragState.endCol)
                      return (
                        <div
                          key={colIdx}
                          onMouseDown={e => handleCellMouseDown(e, user.user_id, colIdx)}
                          title={weekData ? `${weekData.week} · ${loadPct}% ${t('dashboard.load_label').toLowerCase()} · ${weekData.available_hours}h ${t('resources.available').toLowerCase()}` : ''}
                          style={{
                            width: CELL_W, flexShrink: 0, height: '100%',
                            borderLeft: '1px solid #1e2d4530',
                            background: isDrag ? 'rgba(79,142,247,0.25)' : utilColor(loadPct),
                            cursor: 'crosshair',
                            transition: isDrag ? 'none' : 'background 0.15s',
                          }}
                        />
                      )
                    })}

                    {/* Booking bars overlaid */}
                    {userBookings.map(b => (
                      <BookingBar
                        key={b.id}
                        booking={b}
                        weekStart={weekDates[0]}
                        weekCount={weeks}
                        color={projectColorMap[b.project_id] || '#4f8ef7'}
                        t={t}
                        isSelected={selectedBooking?.id === b.id}
                        onMouseDown={e => handleBookingMouseDown(e, b)}
                        onClick={() => {
                          setSelected(b)
                          setPanel({ booking: b, position: { x: 200, y: 200 }, isNew: false })
                        }}
                      />
                    ))}
                  </div>
                </div>
              )
            })}
          </div>
        </div>
      )}

      {/* Booking panel */}
      {panel && (
        <BookingPanel
          booking={panel.booking}
          position={panel.position}
          projects={projects}
          projectColorMap={projectColorMap}
          t={t}
          onSave={data => {
            const b = panel.booking
            if (panel.isNew) {
              createBooking({ ...b, ...data })
            } else {
              updateBooking({ id: b.id, ...data })
            }
            setPanel(null)
            setSelected(null)
          }}
          onDelete={() => {
            if (panel.booking.id) deleteBooking(panel.booking.id)
            setPanel(null)
            setSelected(null)
          }}
          onClose={() => { setPanel(null); setSelected(null) }}
        />
      )}

      {/* Click-away to close panel */}
      {panel && (
        <div
          onClick={() => { setPanel(null); setSelected(null) }}
          style={{ position: 'fixed', inset: 0, zIndex: 199 }}
        />
      )}
    </div>
  )
}
