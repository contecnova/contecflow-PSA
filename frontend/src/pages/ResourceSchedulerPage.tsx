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
 *
 * 16-11-2026: pasada de diseño. Dentro de PageShell (antes contenedor propio
 * con otros márgenes); título como el menú ("Planificador visual"); modo con
 * Tabs e iconos lucide (antes botones propios con emojis); departamento y
 * horizonte en una barra bajo la cabecera con selects del kit (antes en la
 * cabecera y botones "8s/12s"); textos de ayuda legibles (antes --text-4);
 * panel de reserva con Button e iconos (antes emojis); tipo de reserva
 * traducido en el tooltip (antes "soft"/"hard").
 */
import type { CSSProperties } from 'react'
import { useState, useRef, useCallback, useMemo, useEffect, type MouseEvent as ReactMouseEvent, useId } from 'react'
import { useQuery, useMutation, useQueryClient, keepPreviousData } from '@tanstack/react-query'
import { useToast } from '../context/ToastContext'
import api, { projectsApi, unwrapList, type ApiError, type ProjectListItem } from '../services/api'
import PageHeader from '../components/layout/PageHeader'
import PageShell from '../components/layout/PageShell'
import { CalendarDays, Trash2, Users, X } from 'lucide-react'
import { Button, Spinner, EmptyState, Tabs, useDialogo, Select, Pulsable } from '../components/ui'
import { useAppT } from '../i18n/AppLangContext'
import { openConfirmGlobal } from '../context/ConfirmContext'
import useMediaQuery from '../hooks/useMediaQuery'
import { useOrgSettings } from '../hooks/useOrgSettings'
import { alpha } from '../constants/theme'
import { STALE_NEAR_LIVE_MS, STALE_SHORT_MS } from '../constants/timings'
import { FULL_LIST_SIZE } from '../constants/pagination'
import { ventanaVisible } from '../utils/ventanaDeReservas'
import { extractErr, localeActivo } from '../utils/helpers'
import './ResourceSchedulerPage.css'
import { px } from '../utils/estilos'

// ── Tipos ────────────────────────────────────────────────────────────────────

/** Reserva de `/bookings`; sin `id` mientras se está creando. */
interface Booking {
  id?: string
  user_id: string
  project_id: string | null
  start_date: string
  end_date: string
  hours_per_day?: number
  booking_type?: string
  /** Lo añade la página a partir de la lista de proyectos. */
  project_name?: string | null
}

/** Lo que edita el panel de una reserva. */
interface BookingChanges {
  project_id: string | null
  hours_per_day: number
  booking_type: string
}

interface ForecastWeek { week: string; load_pct?: number; available_hours?: number }

/** Persona de `/resource-forecast/weeks`. */
interface ForecastUser {
  user_id: string
  user_name: string
  department?: string | null
  capacity_hours?: number
  avg_load_pct?: number
  weeks?: ForecastWeek[]
}

interface ForecastData { users?: ForecastUser[] }

// ── Constants ────────────────────────────────────────────────────────────────

const CELL_W  = 56   // px per week column
const ROW_H   = 44   // px per user row
const LABEL_W = 200  // px for the name column
const HDR_H   = 60   // header height

// Escala de ocupación sobre el acento del tema (antes hex fijos, que no seguían el tema claro).
const UTIL_BAJO  = 'color-mix(in srgb, var(--accent) 25%, var(--surface-2))'
const UTIL_MEDIO = 'color-mix(in srgb, var(--accent) 45%, var(--surface-2))'
const UTIL_ALTO  = 'color-mix(in srgb, var(--accent) 70%, var(--surface-2))'
const UTIL_COLORS = [
  [0,   10,  'var(--surface-4)'],  // available
  [10,  50,  UTIL_BAJO],
  [50,  80,  UTIL_MEDIO],
  [80,  100, UTIL_ALTO],
  [100, 120, 'var(--orange)'],  // overloaded
  [120, 999, 'var(--danger)'],
]

const PROJECT_PALETTE = [
  'var(--accent)','var(--success)','var(--warning)','var(--danger)','var(--purple)',
  'var(--sky-blue)','var(--orange)','var(--success)','var(--chart-pink)','var(--coral)',
]

function utilColor(pct: number) {
  for (const [lo, hi, c] of UTIL_COLORS) {
    if (pct >= (lo as number) && pct < (hi as number)) return c
  }
  return UTIL_COLORS[UTIL_COLORS.length - 1][2]
}

function monday(d: Date | string) {
  const r = new Date(d)
  r.setDate(r.getDate() - ((r.getDay() + 6) % 7))
  r.setHours(0, 0, 0, 0)
  return r
}
function addWeeks(d: Date | string, n: number) { const r = new Date(d); r.setDate(r.getDate() + n * 7); return r }
function fmtISO(d: Date) { return d.toISOString().slice(0, 10) }
function weekLabel(d: Date) {
  return `${d.getDate().toString().padStart(2,'0')}/${(d.getMonth()+1).toString().padStart(2,'0')}`
}

// ── Project color map ─────────────────────────────────────────────────────────

function useProjectColorMap(projects: Array<{ id: string }>) {
  return useMemo(() => {
    const m: Record<string, string> = {}
    projects.forEach((p, i) => { m[p.id] = PROJECT_PALETTE[i % PROJECT_PALETTE.length] })
    return m
  }, [projects])
}

// ── Booking bar ──────────────────────────────────────────────────────────────

interface BookingBarProps {
  booking: Booking
  weekStart: Date
  weekCount: number
  color: string
  isSelected: boolean
  onMouseDown: (e: ReactMouseEvent) => void
  onClick: () => void
  t: (moduleOrFullKey: string, keyOrParams?: string | Record<string, unknown>) => string
}

function BookingBar({ booking, weekStart, weekCount, color, isSelected, onMouseDown, onClick, t }: BookingBarProps) {
  const { working_hours_per_day: jornada } = useOrgSettings() // 18-11-2026: horas/día por defecto = jornada de la empresa
  const bStart = new Date(booking.start_date + 'T00:00:00')
  const bEnd   = new Date(booking.end_date   + 'T00:00:00')
  const gridStart = weekStart

  const startWeek = Math.max(0, Math.round((+monday(bStart) - +monday(gridStart)) / 604800000))
  const endWeek   = Math.min(weekCount - 1, Math.round((+monday(bEnd) - +monday(gridStart)) / 604800000))

  if (startWeek > weekCount || endWeek < 0) return null

  const x = startWeek * CELL_W + 2
  const w = Math.max((endWeek - startWeek + 1) * CELL_W - 4, CELL_W - 4)

  return (
    <div className="rsch-row resource-scheduler-page-e1"
      onMouseDown={e => { e.stopPropagation(); onMouseDown(e) }}
      onClick={e => { e.stopPropagation(); onClick() }}
      role="button"
      tabIndex={0}
      onKeyDown={e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); e.stopPropagation(); onClick() } }}
      title={t('agenda_recursos_ui.titulo_reserva', { proyecto: booking.project_name || booking.project_id || t('resource_scheduler.no_project_short'), horas: booking.hours_per_day || jornada, tipo: booking.booking_type === 'hard' ? t('resource_scheduler.confirmed') : t('resource_scheduler.tentative') })}
      style={{ '--rsch-row-border': isSelected ? '2px solid var(--text-1)' : `1px solid ${color}`, '--rsch-row-box-shadow': isSelected ? `0 0 0 2px ${color}` : 'none', '--rsch-row-z-index': isSelected ? '10' : '5', '--resource-scheduler-page-left': px(x), '--resource-scheduler-page-height': px(ROW_H - 12), '--resource-scheduler-page-width': px(w), '--rsch-row-background': alpha(color, isSelected ? 'ff' : 'cc') } as CSSProperties}
    >
      <span className="rsch-box">
        {booking.project_name || booking.project_id || '—'} · {booking.hours_per_day || jornada}h
      </span>
    </div>
  )
}

// ── Booking panel (create/edit) ───────────────────────────────────────────────

interface BookingPanelProps {
  booking: Booking
  position: { x: number; y: number }
  projects: ProjectListItem[]
  onSave: (data: BookingChanges) => void
  onDelete: () => void
  onClose: () => void
  projectColorMap?: Record<string, string>
  t: (moduleOrFullKey: string, keyOrParams?: string | Record<string, unknown>) => string
}

function BookingPanel({ booking, position, projects, onSave, onDelete, onClose, t }: BookingPanelProps) {
  const { working_hours_per_day: jornada } = useOrgSettings() // 18-11-2026
  const idCampo = useId()
  const [projectId, setProjectId] = useState(booking.project_id || '')
  const [hoursPerDay, setHours]   = useState(booking.hours_per_day || jornada)
  const [bookingType, setType]    = useState(booking.booking_type || 'soft')
  const isNew = !booking.id
  const dialogRef = useDialogo<HTMLDivElement>(true, onClose)

  return (
    <div className="rsch-card resource-scheduler-page-e2" ref={dialogRef} role="dialog" aria-modal="true" style={{ '--resource-scheduler-page-left': px(Math.min(position.x + 8, window.innerWidth - 260)), '--resource-scheduler-page-top': px(Math.min(position.y + 8, window.innerHeight - 280)) } as CSSProperties}>
      <div className="rsch-text-sm-strong">
        {isNew ? t('resource_scheduler.new_booking') : t('resource_scheduler.edit_booking')}
      </div>

      <label className="rsch-label-muted-xs" id={`${idCampo}-et1`} htmlFor={`${idCampo}-1`}>{t('resource_scheduler.project')}</label>
      <Select suelto placeholder={false} className="rsch-input" id={`${idCampo}-1`} value={projectId} onChange={e => setProjectId(e.target.value)}>
        <option value="">{t('resource_scheduler.no_project')}</option>
        {projects.map(p => (
          <option key={p.id} value={p.id}>{p.code} – {p.name}</option>
        ))}
      </Select>

      <label className="rsch-label-muted-xs" id={`${idCampo}-et2`} htmlFor={`${idCampo}-2`}>{t('resource_scheduler.hours_per_day')}</label>
      <input className="ds-input rsch-input-2" id={`${idCampo}-2`} aria-labelledby={`${idCampo}-et2`} type="number" min={1} max={24} value={hoursPerDay} onChange={e => setHours(Number(e.target.value))} />

      <span className="rsch-label-muted-xs" id={`${idCampo}-et3`}>{t('resource_scheduler.type')}</span>
      <div className="rsch-row-2" role="group" aria-labelledby={`${idCampo}-et3`}>
        {['soft', 'hard'].map(typeOption => (
          <Pulsable type="button" className={`rsch-btn-xs${bookingType === typeOption ? ' is-active' : ''}`} key={typeOption}
            aria-pressed={bookingType === typeOption} onClick={() => setType(typeOption)}>
            {typeOption === 'soft' ? t('resource_scheduler.tentative') : t('resource_scheduler.confirmed')}
          </Pulsable>
        ))}
      </div>

      <div className="rsch-acciones">
        <Button size="sm" className="rsch-acciones__principal" onClick={() => onSave({ project_id: projectId || null, hours_per_day: hoursPerDay, booking_type: bookingType })}>
          {isNew ? t('resource_scheduler.create') : t('resource_scheduler.save')}
        </Button>
        {!isNew && (
          <Button size="sm" variant="danger" icon={<Trash2 size={14} />} onClick={onDelete}
            title={t('agenda_recursos_ui.eliminar')} />
        )}
        <Button size="sm" variant="secondary" icon={<X size={14} />} onClick={onClose}
          title={t('agenda_recursos_ui.cerrar')} />
      </div>
    </div>
  )
}

// ── Main page ────────────────────────────────────────────────────────────────

export default function ResourceSchedulerPage() {
  const { working_hours_per_day: jornada } = useOrgSettings() // 18-11-2026: jornada de la empresa
  const t = useAppT()
  const toast  = useToast()
  const qc     = useQueryClient()

  const [weeks, setWeeks]             = useState(12)
  const [department, setDepartment]   = useState('')
  const [viewMode, setViewMode]       = useState('scheduler')  // 'scheduler' | 'assign'
  const narrow = useMediaQuery('(max-width: 900px)')
  const [selectedBooking, setSelected] = useState<Booking | null>(null)
  const [panel, setPanel]             = useState<{ booking: Booking; position: { x: number; y: number }; isNew: boolean } | null>(null)  // { booking, position, userId, startDate, endDate }
  const [dragState, setDragState]     = useState<{ userId: string; startCol: number; endCol: number } | null>(null)  // { userId, startCol }

  const gridRef       = useRef<HTMLDivElement | null>(null)
  // assign-mode drag refs
  const assignDragUser    = useRef<ForecastUser | null>(null)
  const assignGhostRef    = useRef<HTMLDivElement | null>(null)
  const assignDropProject = useRef<string | null>(null)
  const today   = monday(new Date())
  const weekDates = useMemo(() => Array.from({ length: weeks }, (_, i) => addWeeks(today, i)), [today, weeks])

  // ── Data ──────────────────────────────────────────────────────────────────
  // Segunda auditoría 2026-11: los errores de estas tres queries se pintan en
  // la página (`loadError`), así que no pasan además por el aviso global.
  const { data: projects = [], error: projectsError } = useQuery<ProjectListItem[]>({
    queryKey: ['projects'],
    queryFn:  () => projectsApi.list().then(r => r.data),
    meta: { errorToast: false },
  })

  const { data: forecastData, isLoading, isError: forecastFailed, error: forecastError } = useQuery<ForecastData>({
    queryKey: ['resource-forecast', weeks, department],
    queryFn:  () => {
      const params = { weeks, ...(department ? { department } : {}) }
      return api.get('/resource-forecast/weeks', { params }).then(r => r.data)
    },
    staleTime: STALE_SHORT_MS,
    meta: { errorToast: false },
  })

  // Solo las reservas que solapan con la ventana visible (`date_from`/`date_to`,
  // SQL en el servidor). Al cambiar el nº de semanas la clave cambia y se vuelve a
  // pedir; las mutaciones invalidan el prefijo ['bookings'] y refrescan la ventana.
  const ventana = useMemo(() => ventanaVisible(today, weeks), [today, weeks])
  const { data: bookingsData = [], error: bookingsError } = useQuery<Booking[]>({
    queryKey: ['bookings', ventana.date_from, ventana.date_to],
    queryFn:  () => api.get('/bookings', { params: { ...ventana, page_size: FULL_LIST_SIZE } }).then(r => unwrapList(r) as Booking[]),
    placeholderData: keepPreviousData,
    staleTime: STALE_NEAR_LIVE_MS,
    meta: { errorToast: false },
  })
  const loadError = forecastError ?? projectsError ?? bookingsError

  const { mutate: createBooking } = useMutation({
    mutationFn: (b: Booking) => api.post('/bookings', b),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['bookings'] }); qc.invalidateQueries({ queryKey: ['resource-forecast'] }); toast.success(t('resource_scheduler.booking_created')) },
    onError: (e: ApiError) => toast.error(e?.response?.data?.detail || t('resource_scheduler.create_error')),
  })

  const { mutate: updateBooking } = useMutation({
    mutationFn: ({ id, ...data }: { id: string } & Partial<Omit<Booking, 'id'>>) => api.patch(`/bookings/${id}`, data),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['bookings'] }); qc.invalidateQueries({ queryKey: ['resource-forecast'] }); toast.success(t('resource_scheduler.booking_updated')) },
    onError: (e: ApiError) => toast.error(e?.response?.data?.detail || t('resource_scheduler.update_error')),
  })

  const { mutate: deleteBooking } = useMutation({
    mutationFn: (id: string) => api.delete(`/bookings/${id}`),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['bookings'] }); qc.invalidateQueries({ queryKey: ['resource-forecast'] }); toast.success(t('resource_scheduler.booking_deleted')) },
    onError: (e: ApiError) => toast.error(e?.response?.data?.detail || t('resource_scheduler.delete_error')),
  })

  const projectColorMap = useProjectColorMap(projects)

  // Build project name map
  const projNameMap = useMemo(() => {
    const m: Record<string, string> = {}
    projects.forEach(p => { m[p.id] = p.name })
    return m
  }, [projects])

  // Enrich bookings with project names
  const bookings = useMemo(() => bookingsData.map((b): Booking => ({
    ...b,
    project_name: projNameMap[b.project_id] || null,
  })), [bookingsData, projNameMap])

  // Build department list
  const departments = useMemo(() => {
    const s = new Set<string>()
    ;(forecastData?.users || []).forEach(u => { if (u.department) s.add(u.department) })
    return [...s]
  }, [forecastData])

  // ── Keyboard ─────────────────────────────────────────────────────────────
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'Escape') { setPanel(null); setDragState(null); setSelected(null) }
      if ((e.key === 'Delete' || e.key === 'Backspace') && selectedBooking) {
        setPanel(null)
        const bookingId = selectedBooking.id
        openConfirmGlobal({
          message: t('agenda_recursos_ui.eliminar_reserva_confirm'),
          danger: true,
          onConfirm: () => { deleteBooking(bookingId); setSelected(null) },
        })
      }
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [selectedBooking, deleteBooking, t])

  // ── Drag to create booking ────────────────────────────────────────────────
  const handleCellMouseDown = useCallback((e: { preventDefault: () => void }, userId: string, colIndex: number) => {
    if (panel) { setPanel(null); return }
    e.preventDefault()
    const startCol = colIndex
    setDragState({ userId, startCol, endCol: colIndex })

    const onMove = (me: MouseEvent) => {
      const gridLeft = gridRef.current?.getBoundingClientRect().left || 0
      const scrollLeft = gridRef.current?.scrollLeft || 0
      const relX = me.clientX - gridLeft + scrollLeft - LABEL_W
      const col = Math.max(0, Math.min(weeks - 1, Math.floor(relX / CELL_W)))
      setDragState(prev => prev ? { ...prev, endCol: col } : null)
    }

    const onUp = (me: MouseEvent) => {
      document.removeEventListener('mousemove', onMove)
      document.removeEventListener('mouseup', onUp)
      setDragState(prev => {
        if (!prev) return null
        const s = Math.min(prev.startCol, prev.endCol)
        const end = Math.max(prev.startCol, prev.endCol)
        const startDate = fmtISO(weekDates[s])
        const endDate   = fmtISO(addWeeks(weekDates[end], 1) > weekDates[weeks - 1] ? weekDates[end] : addWeeks(weekDates[end], 1))
        setPanel({
          booking: { user_id: userId, start_date: startDate, end_date: endDate, project_id: '', hours_per_day: jornada, booking_type: 'soft' },
          position: { x: me.clientX, y: me.clientY },
          isNew: true,
        })
        return null
      })
    }

    document.addEventListener('mousemove', onMove)
    document.addEventListener('mouseup', onUp)
  }, [panel, weekDates, weeks, jornada])

  // ── Drag to move booking ──────────────────────────────────────────────────
  const handleBookingMouseDown = useCallback((e: ReactMouseEvent, booking: Booking) => {
    e.preventDefault()
    const origStart  = new Date(booking.start_date + 'T00:00:00')
    const origEnd    = new Date(booking.end_date   + 'T00:00:00')
    const startX     = e.clientX
    let ghost: HTMLDivElement | null = null
    let lastDWeeks = 0

    const onMove = (me: MouseEvent) => {
      const dx     = me.clientX - startX
      const dWeeks = Math.round(dx / CELL_W)

      if (!ghost && Math.abs(dx) > 8) {
        ghost = document.createElement('div')
        ghost.style.cssText = `position:fixed;z-index:var(--z-drag);pointer-events:none;background:var(--surface-2);border:1.5px solid var(--accent);border-radius:8px;padding:6px 12px;font-size:12px;font-weight:700;color:var(--accent);box-shadow:var(--shadow-lg);white-space:nowrap;`
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

    const onUp = (me: MouseEvent) => {
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
  const handlePersonDragStart = useCallback((e: ReactMouseEvent, user: ForecastUser) => {
    if (e.button !== 0) return
    const startX = e.clientX
    const startY = e.clientY
    let dragging = false

    const onMove = (ev: MouseEvent) => {
      if (!dragging) {
        const dx = ev.clientX - startX, dy = ev.clientY - startY
        if (Math.sqrt(dx * dx + dy * dy) < 5) return
        dragging = true
        assignDragUser.current = user

        const ghost = document.createElement('div')
        ghost.textContent = user.user_name.split(' ')[0]
        Object.assign(ghost.style, {
          position: 'fixed', zIndex: 'var(--z-drag)', pointerEvents: 'none',
          background: 'var(--accent-glow)', border: '1px solid var(--accent)',
          borderRadius: '16px', padding: '4px 12px',
          color: 'var(--accent)', fontSize: '11px', fontWeight: 700,
          fontFamily: 'var(--font-sans)', boxShadow: 'var(--shadow-md)',
          left: ev.clientX + 12 + 'px', top: ev.clientY + 8 + 'px',
        })
        document.body.appendChild(ghost)
        assignGhostRef.current = ghost
      } else if (assignGhostRef.current) {
        assignGhostRef.current.style.left = ev.clientX + 12 + 'px'
        assignGhostRef.current.style.top  = ev.clientY + 8 + 'px'
      }
    }

    const onUp = (ev: MouseEvent) => {
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
            hours_per_day: jornada,
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
  }, [jornada])

  const users: ForecastUser[] = forecastData?.users || []

  return (
    <PageShell className="rsch-stack">
      <PageHeader
        icon={<CalendarDays size={18} />}
        title={t('resource_scheduler.title')}
        subtitle={viewMode === 'assign' ? t('resource_scheduler.subtitle_assign') : t('resource_scheduler.subtitle_scheduler')}
      />

      {/* Modo y filtros, bajo la cabecera */}
      <div className="ds-toolbar rsch-barra">
        <Tabs
          ariaLabel={t('agenda_recursos_ui.vista')}
          items={[
            { id: 'scheduler', label: t('resource_scheduler.scheduler_mode'), icon: <CalendarDays size={14} /> },
            { id: 'assign', label: t('resource_scheduler.assign_mode'), icon: <Users size={14} /> },
          ]}
          active={viewMode}
          onChange={setViewMode}
        />
        <div className="ds-toolbar__spacer" />
        {departments.length > 0 && (
          <Select suelto placeholder={false} className="rsch-input-3" aria-label={t('agenda_recursos_ui.departamento')} value={department} onChange={e => setDepartment(e.target.value)}>
            <option value="">{t('resource_scheduler.all_departments')}</option>
            {departments.map(d => <option key={d} value={d}>{d}</option>)}
          </Select>
        )}
        <Select suelto placeholder={false} className="rsch-input-3" aria-label={t('agenda_recursos_ui.horizonte')} value={weeks} onChange={e => setWeeks(Number(e.target.value))}>
          {[8, 12, 16, 24].map(w => (
            <option key={w} value={w}>{t('agenda_recursos_ui.n_semanas', { n: w })}</option>
          ))}
        </Select>
      </div>

      {/* Legend */}
      <div className="rsch-row-3">
        {[[t('resource_scheduler.legend_available'),'var(--surface-4)'],[t('resource_scheduler.legend_lt_50'),UTIL_BAJO],[t('resource_scheduler.legend_50_80'),UTIL_MEDIO],[t('resource_scheduler.legend_80_100'),UTIL_ALTO],[t('resource_scheduler.legend_overloaded'),'var(--orange)']].map(([l,c]) => (
          <span className="rsch-row-muted" key={l}>
            <div className="rsch-box-3 rsch-box-15" style={{ '--rsch-box-15-background': c } as CSSProperties} />{l}
          </span>
        ))}
        <span className="rsch-text-2xs">{t('resource_scheduler.legend_shortcuts')}</span>
      </div>

      {loadError && (
        <div role="alert" className="u-danger rsch-box-4">
          {extractErr(loadError, t('toast.load_error'))}
        </div>
      )}

      {isLoading ? (
        <div className="rsch-row-4">
          <Spinner size={32} />
        </div>
      ) : forecastFailed ? null : users.length === 0 ? (
        <div className="rsch-row-4">
          <EmptyState icon={<Users size={28} />} title={t('resource_scheduler.no_active_users')} description={t('resource_scheduler.no_active_users_desc')} />
        </div>
      ) : viewMode === 'assign' ? (
        /* ── Assign view: drag person chip → project row ───────────────────── */
        <div className="rsch-row-5" style={{ '--rsch-row-5-flex-direction': narrow ? 'column' : 'row' } as CSSProperties}>
          {/* People panel */}
          <div className={narrow ? 'rsch-personas rsch-personas--estrecho' : 'rsch-personas'}>
            <div className="rsch-text-muted-2xs-strong">
              {t('resource_scheduler.people')}
            </div>
            {users.map(u => (
              <div className="rsch-row-6"
                key={u.user_id}
                onMouseDown={e => handlePersonDragStart(e, u)}
                title={t('resource_scheduler.person_tooltip', { nombre: u.user_name, pct: u.avg_load_pct })}
                role="button"
                tabIndex={0}
              >
                <div className="rsch-row-accent">
                  {u.user_name.slice(0, 1).toUpperCase()}
                </div>
                <div className="rsch-box-5">
                  <div className="rsch-box-6">
                    {u.user_name.split(' ')[0]}
                  </div>
                  <div className="rsch-text-3xs" style={{ '--rsch-text-3xs-color': (u.avg_load_pct ?? 0) >= 100 ? 'var(--danger)' : 'var(--text-3)' } as CSSProperties}>
                    {u.avg_load_pct}%
                  </div>
                </div>
              </div>
            ))}
          </div>

          {/* Project rows grid */}
          <div className="rsch-box-7" ref={gridRef}>
            <div className="rsch-grid resource-scheduler-page-e3" style={{ '--rsch-grid-grid-template-columns': `${LABEL_W}px 1fr`, '--resource-scheduler-page-min-width': px(LABEL_W + weekDates.length * CELL_W) } as CSSProperties}>
              {/* Corner */}
              <div className="rsch-row-7 resource-scheduler-page-e4" style={{ '--resource-scheduler-page-height': px(HDR_H) } as CSSProperties}>
                <span className="rsch-text-muted-2xs-strong-2">{t('resource_scheduler.project')}</span>
              </div>
              {/* Week headers */}
              <div className="rsch-row-8 resource-scheduler-page-e4" style={{ '--resource-scheduler-page-height': px(HDR_H) } as CSSProperties}>
                {weekDates.map((w, i) => {
                  const isToday = fmtISO(w) === fmtISO(today)
                  return (
                    <div className="rsch-stack-2 resource-scheduler-page-e5" key={i} style={{ '--rsch-stack-2-background': isToday ? 'color-mix(in srgb, var(--accent) 8%, transparent)' : 'transparent', '--resource-scheduler-page-width': px(CELL_W) } as CSSProperties}>
                      {i === 0 || w.getDate() <= 7 ? (
                        <div className="rsch-text-3xs-2">
                          {w.toLocaleString(localeActivo(), { month: 'short' }).toUpperCase()}
                        </div>
                      ) : null}
                      <div className="rsch-text-2xs-2" style={{ '--rsch-text-2xs-2-font-weight': isToday ? '700' : '400', '--rsch-text-2xs-2-color': isToday ? 'var(--accent)' : 'var(--text-3)' } as CSSProperties}>
                        {weekLabel(w)}
                      </div>
                    </div>
                  )
                })}
              </div>

              {/* Project rows */}
              {projects.slice(0, 40).map(proj => {
                const projBookings = bookings.filter(b => b.project_id === proj.id)
                const color = projectColorMap[proj.id] || 'var(--accent)'
                return (
                  <div className="rsch-box-8" key={proj.id}>
                    <div className="rsch-row-9 resource-scheduler-page-e4" style={{ '--resource-scheduler-page-height': px(ROW_H) } as CSSProperties}>
                      <div className="rsch-box-9 rsch-box-16" style={{ '--rsch-box-16-background': color } as CSSProperties} />
                      <div className="rsch-box-5">
                        <div className="rsch-box-6">{proj.name}</div>
                        <div className="rsch-text-3xs-3">{proj.code}</div>
                      </div>
                    </div>
                    <div className="rsch-row-10 resource-scheduler-page-e4"
                      onPointerEnter={() => { assignDropProject.current = proj.id }}
                      onPointerLeave={() => { assignDropProject.current = null }}
                      style={{ '--resource-scheduler-page-height': px(ROW_H) } as CSSProperties}
                    >
                      {weekDates.map((_, colIdx) => (
                        <div className="rsch-box-10 resource-scheduler-page-e5" key={colIdx} style={{ '--resource-scheduler-page-width': px(CELL_W) } as CSSProperties} />
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
        <div className="rsch-box-11" ref={gridRef}>
          <div className="rsch-grid-2 resource-scheduler-page-e3" style={{ '--rsch-grid-2-grid-template-columns': `${LABEL_W}px 1fr`, '--resource-scheduler-page-min-width': px(LABEL_W + weekDates.length * CELL_W) } as CSSProperties}>

            {/* Label column header */}
            <div className="rsch-row-7 resource-scheduler-page-e4" style={{ '--resource-scheduler-page-height': px(HDR_H) } as CSSProperties}>
              <span className="rsch-text-muted-2xs-strong-2">{t('resource_scheduler.people')}</span>
            </div>

            {/* Week headers */}
            <div className="rsch-row-8 resource-scheduler-page-e4" style={{ '--resource-scheduler-page-height': px(HDR_H) } as CSSProperties}>
              {weekDates.map((w, i) => {
                const isToday = fmtISO(w) === fmtISO(today)
                return (
                  <div className="rsch-stack-3 resource-scheduler-page-e5" key={i} style={{ '--rsch-stack-3-background': isToday ? 'color-mix(in srgb, var(--accent) 8%, transparent)' : 'transparent', '--resource-scheduler-page-width': px(CELL_W) } as CSSProperties}>
                    {i === 0 || w.getDate() <= 7 ? (
                      <div className="rsch-text-3xs-2">
                        {w.toLocaleString(localeActivo(), { month: 'short' }).toUpperCase()}
                      </div>
                    ) : null}
                    <div className="rsch-text-2xs-3" style={{ '--rsch-text-2xs-3-font-weight': isToday ? '700' : '400', '--rsch-text-2xs-3-color': isToday ? 'var(--accent)' : 'var(--text-3)' } as CSSProperties}>
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
                <div className="rsch-box-8" key={user.user_id}>
                  {/* Label */}
                  <div className="rsch-row-11 resource-scheduler-page-e4" style={{ '--resource-scheduler-page-height': px(ROW_H) } as CSSProperties}>
                    <div className="rsch-row-accent-2">
                      {user.user_name.slice(0, 1).toUpperCase()}
                    </div>
                    <div className="rsch-box-5">
                      <div className="rsch-box-12">{user.user_name}</div>
                      <div className="rsch-text-3xs-3">{t('agenda_recursos_ui.capacidad', { horas: user.capacity_hours, pct: user.avg_load_pct })}</div>
                    </div>
                  </div>

                  {/* Grid row */}
                  <div className="rsch-row-12 resource-scheduler-page-e4" style={{ '--resource-scheduler-page-height': px(ROW_H) } as CSSProperties}>
                    {/* Utilization cells */}
                    {weekDates.map((w, colIdx) => {
                      const weekData   = user.weeks?.[colIdx]
                      const loadPct    = weekData?.load_pct || 0
                      const isDrag     = dragState?.userId === user.user_id &&
                        colIdx >= Math.min(dragState!.startCol, dragState!.endCol) &&
                        colIdx <= Math.max(dragState!.startCol, dragState!.endCol)
                      return (
                        <div className="rsch-box-13 resource-scheduler-page-e5"
                          key={colIdx}
                          onMouseDown={e => handleCellMouseDown(e, user.user_id, colIdx)}
                          role="button"
                          tabIndex={0}
                          onKeyDown={e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); handleCellMouseDown(e, user.user_id, colIdx) } }}
                          title={weekData ? t('resource_scheduler.cell_tooltip', { semana: weekData.week, pct: loadPct, horas: weekData.available_hours }) : ''}
                          aria-label={weekData ? t('resource_scheduler.cell_tooltip', { semana: weekData.week, pct: loadPct, horas: weekData.available_hours }) : undefined}
                          style={{ '--rsch-box-13-transition': isDrag ? 'none' : 'background 0.15s', '--resource-scheduler-page-width': px(CELL_W), '--rsch-box-13-background': isDrag ? 'color-mix(in srgb, var(--accent) 25%, transparent)' : utilColor(loadPct) } as CSSProperties}
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
                        color={projectColorMap[b.project_id] || 'var(--accent)'}
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
            const bookingId = panel.booking.id
            if (!bookingId) { setPanel(null); setSelected(null); return }
            openConfirmGlobal({
              message: t('agenda_recursos_ui.eliminar_reserva_confirm'),
              danger: true,
              onConfirm: () => {
                deleteBooking(bookingId)
                setPanel(null)
                setSelected(null)
              },
            })
          }}
          onClose={() => { setPanel(null); setSelected(null) }}
        />
      )}

      {/* Click-away to close panel */}
      {panel && (
        <div className="rsch-box-14"
          role="presentation"
          onMouseDown={() => { setPanel(null); setSelected(null) }}
        />
      )}
    </PageShell>
  )
}
