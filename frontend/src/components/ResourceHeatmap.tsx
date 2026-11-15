/**
 * ResourceHeatmap — Visual weekly load heatmap per team member
 * Shows hard/soft bookings, utilization %, and overload warnings
 */
import { useState, type CSSProperties, useId } from 'react'
import { openConfirmGlobal } from '../context/ConfirmContext'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import api, { projectsApi, usersApi } from '../services/api'
import { Button, Modal, Spinner, EmptyState } from './ui'
import { z } from 'zod'
import { useFormValidation } from '../hooks/useFormValidation'
import { useAppT } from '../i18n/AppLangContext'
import { alpha } from '../constants/theme'
import DateInput from './ui/DateInput'
import { POLL_DEFAULT_MS } from '../constants/timings'
import './ResourceHeatmap.css'

interface ProjectItem {
  id: string | number
  code?: string
  name?: string
}

interface UserItem {
  id: string | number
  full_name?: string
  role?: string
}

interface BookingPrefill {
  user_id?: string | number
  week?: string
}

interface BookingItem {
  id: string | number
  user_name?: string
  booking_type?: 'hard' | 'soft'
  project_name?: string
  start_date?: string
  end_date?: string
  hours_per_day?: number
  total_hours?: number
}

interface HeatmapWeek {
  status: 'overloaded' | 'high' | 'ok' | 'free'
  hard_hours: number
  soft_hours: number
  capacity: number
  available: number
  utilization_pct: number
  week_label: string
  week: string
}

interface HeatmapUser {
  user_id: string | number
  user_name: string
  role?: string
  avg_utilization: number
  weeks: HeatmapWeek[]
}

interface HeatmapData {
  users?: HeatmapUser[]
  week_labels?: string[]
}

const STATUS_COLORS: Record<string, { bg: string; border: string; text: string; label: string }> = {
  overloaded: { bg: 'var(--danger-border)', border: 'rgba(248,113,113,0.50)', text: 'var(--danger)', label: 'Sobrecargado' },
  high:       { bg: 'rgba(245,158,11,0.15)', border: 'rgba(245,158,11,0.38)', text: 'var(--warning)', label: 'Alta carga' },
  ok:         { bg: 'var(--accent-muted)', border: 'color-mix(in srgb, var(--accent) 25%, transparent)', text: 'var(--accent)', label: 'Ok' },
  free:       { bg: 'rgba(30,45,69,0.13)', border: 'rgba(30,45,69,0.25)', text: 'var(--text-3)', label: 'Libre' },
}

const BOOKING_COLORS = {
  hard: 'var(--accent)',
  soft: 'var(--purple)',
}

const fs: CSSProperties = {
  width: '100%',
  background: 'var(--surface-3)',
  border: '1px solid var(--surface-4)',
  borderRadius: 'var(--radius-md)',
  padding: 'var(--space-3) var(--space-3)',
  color: 'var(--text-1)',
  fontSize: '13px',
  outline: 'none',
  fontFamily: 'var(--font-sans)',
  boxSizing: 'border-box',
}

const bookingSchema = z.object({
  user_id: z.string().trim().min(1, 'La persona es obligatoria'),
  project_id: z.string().optional(),
  booking_type: z.enum(['hard', 'soft']),
  start_date: z.string().min(1, 'La fecha de inicio es obligatoria'),
  end_date: z.string().min(1, 'La fecha de fin es obligatoria'),
  hours_per_day: z.coerce.number().min(1, 'Las horas por dia deben ser al menos 1').max(24, 'Las horas por dia no pueden superar 24'),
  note: z.string().optional(),
}).superRefine((data, ctx) => {
  if (data.end_date < data.start_date) {
    ctx.addIssue({
      code: 'custom',
      path: ['end_date'],
      message: 'La fecha de fin no puede ser anterior a la de inicio',
    })
  }
})

function BookingModal({ onClose, prefill }: { onClose: () => void; prefill?: BookingPrefill | null }) {
  const idCampo = useId()
  const t = useAppT()
  const qc = useQueryClient()
  const [form, setForm] = useState({
    user_id: prefill?.user_id || '',
    project_id: '',
    booking_type: 'hard',
    start_date: prefill?.week || new Date().toISOString().slice(0,10),
    end_date: '',
    hours_per_day: 8,
    note: '',
  })
  const validation = useFormValidation(bookingSchema)

  const { data: projRaw = [] } = useQuery({ queryKey: ['projects'], queryFn: () => projectsApi.list({}).then(r => r.data ?? []) })
  const { data: usersRaw = [] } = useQuery({ queryKey: ['users'], queryFn: () => usersApi.list({}).then(r => r.data) })
  const projects = projRaw as ProjectItem[]
  const users = usersRaw as UserItem[]

  const { mutate: create, isPending } = useMutation({
    mutationFn: (d: unknown) => api.post('/bookings', d),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['heatmap'] }); qc.invalidateQueries({ queryKey: ['bookings'] }); validation.setErrors({}); onClose() },
  })

  const setField = (key: 'user_id' | 'project_id' | 'booking_type' | 'start_date' | 'end_date' | 'hours_per_day' | 'note') => (e: { target: { value: string } }) => {
    const value = key === 'hours_per_day' ? +e.target.value : e.target.value
    setForm(current => ({ ...current, [key]: value }))
    validation.clearFieldError(key)
  }

  const submit = () => {
    const result = validation.validateForm(form)
    if (!result.success) {
      return
    }
    create(result.data)
  }

  return (
    <Modal open title={t('resource_heatmap.new_booking_title')} onClose={onClose} width={480}>
      <div className="u-stack-14">
        <div><label id={`${idCampo}-et1`} htmlFor={`${idCampo}-1`} className="resoheat-ls">Persona *</label>
          <select id={`${idCampo}-1`} aria-labelledby={`${idCampo}-et1`} value={form.user_id} onChange={setField('user_id')} style={validation.inputStyle(fs, 'user_id')}>
            <option value="">Seleccionar...</option>
            {users.map(u => <option key={u.id} value={u.id}>{u.full_name} ({u.role})</option>)}
          </select>
          {validation.errors.user_id && <div className="u-field-error">{validation.errors.user_id}</div>}
        </div>
        <div><label id={`${idCampo}-et2`} htmlFor={`${idCampo}-2`} className="resoheat-ls">Proyecto</label>
          <select id={`${idCampo}-2`} aria-labelledby={`${idCampo}-et2`} value={form.project_id} onChange={setField('project_id')} className="resoheat-fs">
            <option value="">{t('resourceheatmap.sin_proyecto')}</option>
            {projects.map(p => <option key={p.id} value={p.id}>{p.code} — {p.name}</option>)}
          </select>
        </div>
        <div className="u-grid2-12">
          <div><label id={`${idCampo}-et3`} htmlFor={`${idCampo}-3`} className="resoheat-ls">Tipo</label>
            <select id={`${idCampo}-3`} aria-labelledby={`${idCampo}-et3`} value={form.booking_type} onChange={setField('booking_type')} className="resoheat-fs">
              <option value="hard">Hard — Confirmado</option>
              <option value="soft">Soft — Tentativo</option>
            </select>
          </div>
          <div><label id={`${idCampo}-et4`} htmlFor={`${idCampo}-4`} className="resoheat-ls">{t('resourceheatmap.h_dia')}</label>
            <input id={`${idCampo}-4`} aria-labelledby={`${idCampo}-et4`} type="number" min={1} max={24} value={form.hours_per_day} onChange={setField('hours_per_day')} style={validation.inputStyle(fs, 'hours_per_day')} />
            {validation.errors.hours_per_day && <div className="u-field-error">{validation.errors.hours_per_day}</div>}
          </div>
          <div><label id={`${idCampo}-et5`} htmlFor={`${idCampo}-5`} className="resoheat-ls">Fecha inicio *</label>
            <DateInput id={`${idCampo}-5`} value={form.start_date} onChange={setField('start_date')} style={validation.inputStyle(fs, 'start_date')} />
            {validation.errors.start_date && <div className="u-field-error">{validation.errors.start_date}</div>}
          </div>
          <div><label id={`${idCampo}-et6`} htmlFor={`${idCampo}-6`} className="resoheat-ls">Fecha fin *</label>
            <DateInput id={`${idCampo}-6`} value={form.end_date} onChange={setField('end_date')} style={validation.inputStyle(fs, 'end_date')} />
            {validation.errors.end_date && <div className="u-field-error">{validation.errors.end_date}</div>}
          </div>
        </div>
        <div><label id={`${idCampo}-et7`} htmlFor={`${idCampo}-7`} className="resoheat-ls">Nota</label>
          <input id={`${idCampo}-7`} aria-labelledby={`${idCampo}-et7`} value={form.note} onChange={setField('note')} className="resoheat-fs" placeholder={t('resourceheatmap.motivo_de_la_reserva')} />
        </div>
        <div className="u-actions-10">
          <Button variant="secondary" onClick={onClose}>Cancelar</Button>
          <Button onClick={submit} disabled={isPending}>
            {isPending ? 'Guardando...' : 'Crear reserva'}
          </Button>
        </div>
      </div>
    </Modal>
  )
}

export default function ResourceHeatmap() {
  const t = useAppT()
  const qc = useQueryClient()
  const [weeks, setWeeks] = useState(8)
  const [showBooking, setShowBooking] = useState(false)
  const [bookingPrefill, setBookingPrefill] = useState<BookingPrefill | null>(null)
  const [filterStatus, setFilterStatus] = useState('')
  const [showBookingsPanel, setShowBookingsPanel] = useState(false)

  const { data: heatmapData } = useQuery<HeatmapData>({
    queryKey: ['heatmap', weeks],
    queryFn: () => api.get('/bookings/heatmap', { params: { weeks } }).then(r => r.data),
    refetchInterval: POLL_DEFAULT_MS,
  })
  const isLoading = !heatmapData

  const { data: bookingsRaw = [] } = useQuery({
    queryKey: ['bookings'],
    queryFn: () => api.get('/bookings').then(r => r.data?.items ?? r.data ?? []),
    enabled: showBookingsPanel,
  })
  const bookings = bookingsRaw as BookingItem[]

  const { mutate: deleteBooking } = useMutation({
    mutationFn: (id: string | number) => api.delete(`/bookings/${id}`),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['heatmap'] }); qc.invalidateQueries({ queryKey: ['bookings'] }) },
  })

  const users = heatmapData?.users || []
  const weekLabels = heatmapData?.week_labels || []

  const filteredUsers = filterStatus
    ? users.filter(u => u.weeks.some(w => w.status === filterStatus))
    : users

  const getStatusColor = (status?: string) => (status && STATUS_COLORS[status]) || STATUS_COLORS.ok

  const overloadedCount = users.filter(u => u.weeks.some(w => w.status === 'overloaded')).length
  const highCount = users.filter(u => u.weeks.some(w => w.status === 'high')).length
  const freeCount = users.filter(u => u.avg_utilization < 20).length

  return (
    <div>
      {/* Summary KPIs */}
      <div className="resoheat-grid-1">
        {[
          { label:'Sobrecargados', value:overloadedCount, color:'var(--danger)', icon:'🔴' },
          { label:'Alta carga (>85%)', value:highCount, color:'var(--warning)', icon:'🟡' },
          { label:'Infrautilizados (<20%)', value:freeCount, color:'var(--text-2)', icon:'⚪' },
          { label:'Personas totales', value:users.length, color:'var(--accent)', icon:'👥' },
        ].map(({ label, value, color, icon }) => (
          <div key={label} className="resoheat-box-1">
            <div className="resoheat-box-2">{icon}</div>
            <div className="resoheat-txt-2" style={{ color }}>{value}</div>
            <div className="u-text2-xs">{label}</div>
          </div>
        ))}
      </div>

      {/* Controls */}
      <div className="resoheat-row-1">
        <span className="u-text2-sm">Semanas:</span>
        {[4,8,12,16].map(w => (
          <button className="resoheat-box-11" key={w} onClick={() => setWeeks(w)}
            style={{ borderRadius:'var(--radius-sm)', border:`1px solid ${weeks===w?'color-mix(in srgb, var(--accent) 31%, transparent)':'var(--surface-4)'}`, background:weeks===w?'var(--accent-muted)':'transparent', color:weeks===w?'var(--accent)':'var(--text-2)' }}>
            {w}w
          </button>
        ))}

        <select value={filterStatus} onChange={e => setFilterStatus(e.target.value)}
          className="resoheat-fs2">
          <option value="">{t('resourceheatmap.todos')}</option>
          <option value="overloaded">Solo sobrecargados</option>
          <option value="high">Alta carga</option>
          <option value="free">Infrautilizados</option>
        </select>

        <div className="resoheat-row-2">
          <button onClick={() => setShowBookingsPanel(p => !p)}
            className="resoheat-box-3">
            {showBookingsPanel ? '← Heatmap' : '📋 Ver reservas'}
          </button>
          <Button onClick={() => { setBookingPrefill(null); setShowBooking(true) }}>
            {t('resourceheatmap.nueva_reserva')}
          </Button>
        </div>
      </div>

      {/* Legend */}
      <div className="resoheat-row-3">
        {Object.entries(STATUS_COLORS).map(([status, cfg]) => (
          <div key={status} className="resoheat-row-4">
            <div className="resoheat-box-12" style={{ borderRadius:4, background:cfg.bg, border:`1px solid ${cfg.border}` }} />
            {cfg.label}
          </div>
        ))}
        <div className="resoheat-row-5">
          <div className="resoheat-box-13" style={{ background:BOOKING_COLORS.hard }} /> {t('resource_heatmap.hard_booking')}
        </div>
        <div className="resoheat-row-4">
          <div className="resoheat-box-13 resoheat-box-15" style={{ background:BOOKING_COLORS.soft }} /> {t('resource_heatmap.soft_booking')}
        </div>
      </div>

      {/* Bookings panel */}
      {showBookingsPanel && (
        <div className="resoheat-box-4">
          <div className="resoheat-box-5">{t('resource_heatmap.active_bookings')}</div>
          {bookings.length === 0 ? (
            <EmptyState icon="📅" title={t('resource_heatmap.empty_bookings_title')} description={t('resource_heatmap.empty_bookings_desc')} />
          ) : (
            <div className="u-stack-6">
              {bookings.map(b => (
                <div key={b.id} className="resoheat-grid-2">
                  <span className="u-600">{b.user_name}</span>
                  <span className="resoheat-box-14" style={{ color:(b.booking_type && BOOKING_COLORS[b.booking_type]) || 'var(--text-2)', background:alpha(((b.booking_type && BOOKING_COLORS[b.booking_type]) || 'var(--text-2)'), '20') }}>{b.booking_type}</span>
                  <span className="u-text2">{b.project_name || t('resource_heatmap.no_project')}</span>
                  <span className="u-text2">{b.start_date} → {b.end_date}</span>
                  <span>{b.hours_per_day}{t('resourceheatmap.h_dia_2')}</span>
                  <span className="resoheat-txt-1">{b.total_hours}h total</span>
                  <button onClick={() => { openConfirmGlobal({message:t('resource_heatmap.delete_booking_confirm'),onConfirm:()=>deleteBooking(b.id),danger:true}) }}
                    className="resoheat-box-6">🗑</button>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Heatmap grid */}
      {isLoading ? <Spinner /> : filteredUsers.length === 0 ? (
        <EmptyState icon="👥" title={t('resource_heatmap.empty_data_title')} description={t('resource_heatmap.empty_data_desc')} />
      ) : (
        <div className="resoheat-box-7">
          <div style={{ minWidth: 200 + weekLabels.length * 72 }}>
            {/* Header row */}
            <div className="resoheat-grid-3" style={{ gridTemplateColumns:`200px repeat(${weekLabels.length}, 1fr)` }}>
              <div className="resoheat-box-8">{t('resource_heatmap.person')}</div>
              {weekLabels.map((label, i) => (
                <div key={i} className="resoheat-box-9">{label}</div>
              ))}
            </div>

            {/* User rows */}
            {filteredUsers.map((user, _ui) => (
              <div className="resoheat-grid-4" key={user.user_id}
                style={{ gridTemplateColumns:`200px repeat(${weekLabels.length}, 1fr)`, borderBottom:'1px solid #1e2d4520' }}>
                {/* User info */}
                <div className="resoheat-row-6">
                  <div className="resoheat-row-7">
                    {user.user_name.split(' ').map(n => n[0]).join('').slice(0,2)}
                  </div>
                  <div className="u-min0">
                    <div className="resoheat-box-10">{user.user_name}</div>
                    <div className="u-text3-2xs">{user.role} · {Math.round(user.avg_utilization)}% avg</div>
                  </div>
                </div>

                {/* Week cells */}
                {user.weeks.map((week, wi) => {
                  const cfg = getStatusColor(week.status)
                  const showHours = week.hard_hours > 0 || week.soft_hours > 0
                  return (
                    <button className="resoheat-stack-1"
                      key={wi}
                      title={`${user.user_name} · ${week.week_label}\nCapacidad: ${week.capacity}h\nHard: ${week.hard_hours}h\nSoft: ${week.soft_hours}h\nDisponible: ${week.available}h\nUtilización: ${week.utilization_pct}%`}
                      onClick={() => { setBookingPrefill({ user_id: user.user_id, week: week.week }); setShowBooking(true) }}
                      style={{ background: cfg.bg, borderLeft:`1px solid #1e2d4515` }}
                      type="button"
                      onMouseEnter={e => e.currentTarget.style.background = cfg.border}
                      onMouseLeave={e => e.currentTarget.style.background = cfg.bg}
                    >
                      {showHours ? (
                        <>
                          <div className="resoheat-txt-3" style={{ color:cfg.text }}>{Math.round(week.utilization_pct)}%</div>
                          {week.hard_hours > 0 && <div className="resoheat-txt-4" style={{ color:BOOKING_COLORS.hard }}>{week.hard_hours}h</div>}
                          {week.soft_hours > 0 && <div className="resoheat-txt-4" style={{ color:BOOKING_COLORS.soft }}>{week.soft_hours}h ~</div>}
                        </>
                      ) : (
                        <div className="u-text3-2xs">—</div>
                      )}
                    </button>
                  )
                })}
              </div>
            ))}
          </div>
        </div>
      )}

      {showBooking && <BookingModal onClose={() => setShowBooking(false)} prefill={bookingPrefill} />}
    </div>
  )
}
