/**
 * ResourceHeatmap — Visual weekly load heatmap per team member
 * Shows hard/soft bookings, utilization %, and overload warnings
 */
import { useState } from 'react'
import { openConfirmGlobal } from '../context/ConfirmContext'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import api, { projectsApi, usersApi } from '../services/api'
import { Button, Modal, Spinner, EmptyState } from './ui'
import { z } from 'zod'
import { useFormValidation } from '../hooks/useFormValidation'

const STATUS_COLORS = {
  overloaded: { bg: 'var(--danger-border)', border: 'rgba(248,113,113,0.50)', text: 'var(--danger)', label: 'Sobrecargado' },
  high:       { bg: 'rgba(245,158,11,0.15)', border: 'rgba(245,158,11,0.38)', text: 'var(--warning)', label: 'Alta carga' },
  ok:         { bg: 'var(--accent-muted)', border: 'rgba(79,142,247,0.25)', text: 'var(--accent)', label: 'Ok' },
  free:       { bg: 'rgba(30,45,69,0.13)', border: 'rgba(30,45,69,0.25)', text: 'var(--text-3)', label: 'Libre' },
}

const BOOKING_COLORS = {
  hard: 'var(--accent)',
  soft: 'var(--purple)',
}

const fs = { width:'100%', background:'var(--surface-3)', border:'1px solid #1e2d45', borderRadius:8, padding:'9px 12px', color:'var(--text-1)', fontSize:13, outline:'none', fontFamily:'inherit', boxSizing:'border-box' }
const ls = { fontSize:11, fontWeight:700, color:'var(--text-2)', textTransform:'uppercase', letterSpacing:'0.07em', display:'block', marginBottom:5 }

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
      code: z.ZodIssueCode.custom,
      path: ['end_date'],
      message: 'La fecha de fin no puede ser anterior a la de inicio',
    })
  }
})

function BookingModal({ onClose, prefill }) {
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

  const { data: projRaw = [] } = useQuery({ queryKey: ['projects'], queryFn: () => projectsApi.list().then(r => r.data) })
  const { data: usersRaw = [] } = useQuery({ queryKey: ['users'], queryFn: () => usersApi.list().then(r => r.data) })
  const projects = Array.isArray(projRaw) ? projRaw : []
  const users = Array.isArray(usersRaw) ? usersRaw : []

  const { mutate: create, isPending } = useMutation({
    mutationFn: d => api.post('/bookings', d),
    onSuccess: () => { qc.invalidateQueries(['heatmap']); qc.invalidateQueries(['bookings']); validation.setErrors({}); onClose() },
  })

  const setField = (key) => (e) => {
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
    <Modal open title="Nueva reserva de recurso" onClose={onClose} width={480}>
      <div style={{ display:'flex', flexDirection:'column', gap:14 }}>
        <div><label style={ls}>Persona *</label>
          <select value={form.user_id} onChange={setField('user_id')} style={validation.inputStyle(fs, 'user_id')}>
            <option value="">Seleccionar...</option>
            {users.map(u => <option key={u.id} value={u.id}>{u.full_name} ({u.role})</option>)}
          </select>
          {validation.errors.user_id && <div style={{ color:'var(--danger)', fontSize:11, marginTop:4 }}>{validation.errors.user_id}</div>}
        </div>
        <div><label style={ls}>Proyecto</label>
          <select value={form.project_id} onChange={setField('project_id')} style={fs}>
            <option value="">Sin proyecto</option>
            {projects.map(p => <option key={p.id} value={p.id}>{p.code} — {p.name}</option>)}
          </select>
        </div>
        <div style={{ display:'grid', gridTemplateColumns:'1fr 1fr', gap:12 }}>
          <div><label style={ls}>Tipo</label>
            <select value={form.booking_type} onChange={setField('booking_type')} style={fs}>
              <option value="hard">Hard — Confirmado</option>
              <option value="soft">Soft — Tentativo</option>
            </select>
          </div>
          <div><label style={ls}>H/día</label>
            <input type="number" min={1} max={24} value={form.hours_per_day} onChange={setField('hours_per_day')} style={validation.inputStyle(fs, 'hours_per_day')} />
            {validation.errors.hours_per_day && <div style={{ color:'var(--danger)', fontSize:11, marginTop:4 }}>{validation.errors.hours_per_day}</div>}
          </div>
          <div><label style={ls}>Fecha inicio *</label>
            <input type="date" value={form.start_date} onChange={setField('start_date')} style={validation.inputStyle(fs, 'start_date')} />
            {validation.errors.start_date && <div style={{ color:'var(--danger)', fontSize:11, marginTop:4 }}>{validation.errors.start_date}</div>}
          </div>
          <div><label style={ls}>Fecha fin *</label>
            <input type="date" value={form.end_date} onChange={setField('end_date')} style={validation.inputStyle(fs, 'end_date')} />
            {validation.errors.end_date && <div style={{ color:'var(--danger)', fontSize:11, marginTop:4 }}>{validation.errors.end_date}</div>}
          </div>
        </div>
        <div><label style={ls}>Nota</label>
          <input value={form.note} onChange={setField('note')} style={fs} placeholder="Motivo de la reserva..." />
        </div>
        <div style={{ display:'flex', justifyContent:'flex-end', gap:10 }}>
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
  const qc = useQueryClient()
  const [weeks, setWeeks] = useState(8)
  const [showBooking, setShowBooking] = useState(false)
  const [bookingPrefill, setBookingPrefill] = useState(null)
  const [filterStatus, setFilterStatus] = useState('')
  const [showBookingsPanel, setShowBookingsPanel] = useState(false)

  const { data: heatmapData, isLoading } = useQuery({
    queryKey: ['heatmap', weeks],
    queryFn: () => api.get('/bookings/heatmap', { params: { weeks } }).then(r => r.data),
    refetchInterval: 60000,
  })

  const { data: bookingsRaw = [] } = useQuery({
    queryKey: ['bookings'],
    queryFn: () => api.get('/bookings').then(r => r.data),
    enabled: showBookingsPanel,
  })
  const bookings = Array.isArray(bookingsRaw) ? bookingsRaw : []

  const { mutate: deleteBooking } = useMutation({
    mutationFn: id => api.delete(`/bookings/${id}`),
    onSuccess: () => { qc.invalidateQueries(['heatmap']); qc.invalidateQueries(['bookings']) },
  })

  const users = heatmapData?.users || []
  const weekLabels = heatmapData?.week_labels || []

  const filteredUsers = filterStatus
    ? users.filter(u => u.weeks.some(w => w.status === filterStatus))
    : users

  const getStatusColor = (status) => STATUS_COLORS[status] || STATUS_COLORS.ok

  const overloadedCount = users.filter(u => u.weeks.some(w => w.status === 'overloaded')).length
  const highCount = users.filter(u => u.weeks.some(w => w.status === 'high')).length
  const freeCount = users.filter(u => u.avg_utilization < 20).length

  return (
    <div>
      {/* Summary KPIs */}
      <div style={{ display:'grid', gridTemplateColumns:'repeat(4,1fr)', gap:12, marginBottom:20 }}>
        {[
          { label:'Sobrecargados', value:overloadedCount, color:'var(--danger)', icon:'🔴' },
          { label:'Alta carga (>85%)', value:highCount, color:'var(--warning)', icon:'🟡' },
          { label:'Infrautilizados (<20%)', value:freeCount, color:'var(--text-2)', icon:'⚪' },
          { label:'Personas totales', value:users.length, color:'var(--accent)', icon:'👥' },
        ].map(({ label, value, color, icon }) => (
          <div key={label} style={{ background:'var(--surface-2)', border:'1px solid #1e2d45', borderRadius:10, padding:'12px 16px' }}>
            <div style={{ fontSize:18, marginBottom:4 }}>{icon}</div>
            <div style={{ fontSize:22, fontWeight:800, color }}>{value}</div>
            <div style={{ fontSize:11, color:'var(--text-2)' }}>{label}</div>
          </div>
        ))}
      </div>

      {/* Controls */}
      <div style={{ display:'flex', gap:10, marginBottom:16, alignItems:'center', flexWrap:'wrap' }}>
        <span style={{ fontSize:12, color:'var(--text-2)' }}>Semanas:</span>
        {[4,8,12,16].map(w => (
          <button key={w} onClick={() => setWeeks(w)}
            style={{ padding:'5px 12px', borderRadius:6, border:`1px solid ${weeks===w?'rgba(79,142,247,0.31)':'var(--surface-4)'}`, background:weeks===w?'var(--accent-muted)':'transparent', color:weeks===w?'var(--accent)':'var(--text-2)', fontSize:12, cursor:'pointer', fontFamily:'inherit' }}>
            {w}w
          </button>
        ))}

        <select value={filterStatus} onChange={e => setFilterStatus(e.target.value)}
          style={{ ...fs, width:'auto', marginLeft:8 }}>
          <option value="">Todos</option>
          <option value="overloaded">Solo sobrecargados</option>
          <option value="high">Alta carga</option>
          <option value="free">Infrautilizados</option>
        </select>

        <div style={{ marginLeft:'auto', display:'flex', gap:8 }}>
          <button onClick={() => setShowBookingsPanel(p => !p)}
            style={{ background:'transparent', border:'1px solid #1e2d45', borderRadius:8, padding:'7px 14px', color:'var(--text-2)', cursor:'pointer', fontSize:12, fontFamily:'inherit' }}>
            {showBookingsPanel ? '← Heatmap' : '📋 Ver reservas'}
          </button>
          <Button onClick={() => { setBookingPrefill(null); setShowBooking(true) }}>
            + Nueva reserva
          </Button>
        </div>
      </div>

      {/* Legend */}
      <div style={{ display:'flex', gap:16, marginBottom:14, flexWrap:'wrap' }}>
        {Object.entries(STATUS_COLORS).map(([status, cfg]) => (
          <div key={status} style={{ display:'flex', alignItems:'center', gap:6, fontSize:11, color:'var(--text-2)' }}>
            <div style={{ width:16, height:16, borderRadius:4, background:cfg.bg, border:`1px solid ${cfg.border}` }} />
            {cfg.label}
          </div>
        ))}
        <div style={{ display:'flex', alignItems:'center', gap:6, fontSize:11, color:'var(--text-2)', marginLeft:8 }}>
          <div style={{ width:12, height:3, background:BOOKING_COLORS.hard, borderRadius:2 }} /> Hard booking
        </div>
        <div style={{ display:'flex', alignItems:'center', gap:6, fontSize:11, color:'var(--text-2)' }}>
          <div style={{ width:12, height:3, background:BOOKING_COLORS.soft, borderRadius:2, borderTop:'1px dashed #7c3aed' }} /> Soft booking
        </div>
      </div>

      {/* Bookings panel */}
      {showBookingsPanel && (
        <div style={{ background:'var(--surface-2)', border:'1px solid #1e2d45', borderRadius:12, padding:'16px 20px', marginBottom:20 }}>
          <div style={{ fontSize:13, fontWeight:700, marginBottom:12 }}>Reservas activas</div>
          {bookings.length === 0 ? (
            <EmptyState icon="📅" title="Sin reservas" description="Crea reservas para planificar la carga del equipo" />
          ) : (
            <div style={{ display:'flex', flexDirection:'column', gap:6 }}>
              {bookings.map(b => (
                <div key={b.id} style={{ display:'grid', gridTemplateColumns:'1fr 80px 120px 120px 80px 80px auto', gap:10, padding:'8px 12px', background:'var(--surface-3)', borderRadius:8, alignItems:'center', fontSize:12 }}>
                  <span style={{ fontWeight:600 }}>{b.user_name}</span>
                  <span style={{ fontSize:11, fontWeight:700, color:BOOKING_COLORS[b.booking_type], background:BOOKING_COLORS[b.booking_type]+'20', padding:'2px 6px', borderRadius:4, textAlign:'center' }}>{b.booking_type}</span>
                  <span style={{ color:'var(--text-2)' }}>{b.project_name || 'Sin proyecto'}</span>
                  <span style={{ color:'var(--text-2)' }}>{b.start_date} → {b.end_date}</span>
                  <span>{b.hours_per_day}h/día</span>
                  <span style={{ fontWeight:700 }}>{b.total_hours}h total</span>
                  <button onClick={() => { openConfirmGlobal({message:'¿Eliminar esta reserva?',onConfirm:()=>deleteBooking(b.id),danger:true}) }}
                    style={{ background:'none', border:'1px solid #ff475730', borderRadius:6, padding:'2px 8px', color:'var(--danger)', cursor:'pointer', fontSize:11 }}>🗑</button>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Heatmap grid */}
      {isLoading ? <Spinner /> : filteredUsers.length === 0 ? (
        <EmptyState icon="👥" title="Sin datos" description="No hay datos de carga del equipo" />
      ) : (
        <div style={{ overflowX:'auto', border:'1px solid #1e2d45', borderRadius:12, background:'var(--surface-1)' }}>
          <div style={{ minWidth: 200 + weekLabels.length * 72 }}>
            {/* Header row */}
            <div style={{ display:'grid', gridTemplateColumns:`200px repeat(${weekLabels.length}, 1fr)`, borderBottom:'1px solid #1e2d45' }}>
              <div style={{ padding:'10px 14px', fontSize:11, fontWeight:700, color:'var(--text-2)', textTransform:'uppercase', letterSpacing:'0.06em' }}>Persona</div>
              {weekLabels.map((label, i) => (
                <div key={i} style={{ padding:'10px 4px', fontSize:11, color:'var(--text-2)', textAlign:'center', fontFamily:'monospace' }}>{label}</div>
              ))}
            </div>

            {/* User rows */}
            {filteredUsers.map((user, _ui) => (
              <div key={user.user_id}
                style={{ display:'grid', gridTemplateColumns:`200px repeat(${weekLabels.length}, 1fr)`, borderBottom:'1px solid #1e2d4520' }}>
                {/* User info */}
                <div style={{ padding:'10px 14px', display:'flex', alignItems:'center', gap:8 }}>
                  <div style={{ width:28, height:28, borderRadius:8, background:'var(--surface-4)', display:'flex', alignItems:'center', justifyContent:'center', fontSize:11, fontWeight:700, color:'var(--text-2)', flexShrink:0 }}>
                    {user.user_name.split(' ').map(n => n[0]).join('').slice(0,2)}
                  </div>
                  <div style={{ minWidth:0 }}>
                    <div style={{ fontSize:12, fontWeight:600, overflow:'hidden', textOverflow:'ellipsis', whiteSpace:'nowrap' }}>{user.user_name}</div>
                    <div style={{ fontSize:10, color:'var(--text-3)' }}>{user.role} · {Math.round(user.avg_utilization)}% avg</div>
                  </div>
                </div>

                {/* Week cells */}
                {user.weeks.map((week, wi) => {
                  const cfg = getStatusColor(week.status)
                  const showHours = week.hard_hours > 0 || week.soft_hours > 0
                  return (
                    <div
                      key={wi}
                      title={`${user.user_name} · ${week.week_label}\nCapacidad: ${week.capacity}h\nHard: ${week.hard_hours}h\nSoft: ${week.soft_hours}h\nDisponible: ${week.available}h\nUtilización: ${week.utilization_pct}%`}
                      onClick={() => { setBookingPrefill({ user_id: user.user_id, week: week.week }); setShowBooking(true) }}
                      style={{
                        padding:'6px 4px',
                        background: cfg.bg,
                        borderLeft:`1px solid #1e2d4515`,
                        cursor:'pointer',
                        display:'flex', flexDirection:'column', alignItems:'center', justifyContent:'center', gap:2,
                        minHeight:50,
                        transition:'background 0.1s',
                      }}
                      onMouseEnter={e => e.currentTarget.style.background = cfg.border}
                      onMouseLeave={e => e.currentTarget.style.background = cfg.bg}
                    >
                      {showHours ? (
                        <>
                          <div style={{ fontSize:12, fontWeight:700, color:cfg.text }}>{Math.round(week.utilization_pct)}%</div>
                          {week.hard_hours > 0 && <div style={{ fontSize:9, color:BOOKING_COLORS.hard }}>{week.hard_hours}h</div>}
                          {week.soft_hours > 0 && <div style={{ fontSize:9, color:BOOKING_COLORS.soft }}>{week.soft_hours}h ~</div>}
                        </>
                      ) : (
                        <div style={{ fontSize:10, color:'var(--text-3)' }}>—</div>
                      )}
                    </div>
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
