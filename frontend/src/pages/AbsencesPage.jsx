import { useState } from 'react'
import { openConfirmGlobal } from '../context/ConfirmContext'
import { useToast } from '../context/ToastContext'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import api from '../services/api'
import { Card, Button, Modal, Spinner, EmptyState, useSort, SortableTH } from '../components/ui'
import PageHeader from '../components/layout/PageHeader'
import { Umbrella } from 'lucide-react'
import { fmtDate, extractErr} from '../utils/helpers'
import { useAuth } from '../context/AuthContext'
import { useAppT } from '../i18n/AppLangContext'

// ── Estilos compartidos ───────────────────────────────────────────────────────
const _fs = { width: '100%', background: 'var(--surface-3)', border: '1px solid #1e2d45', borderRadius: 8, padding: '8px 12px', color: 'var(--text-1)', fontSize: 13, outline: 'none', fontFamily: 'inherit', boxSizing: 'border-box' }
const _ls = { fontSize: 11, fontWeight: 600, color: 'var(--text-2)', textTransform: 'uppercase', letterSpacing: '0.07em', display: 'block', marginBottom: 5 }


const TYPE_LABELS = {
  vacation: '🏖 Vacaciones', sick: '🤒 Baja médica', personal: '👤 Asunto personal',
  training: '📚 Formación', maternity: '👶 Maternidad', paternity: '👨‍👧 Paternidad', other: '📋 Otro'
}
const STATUS_CFG = {
  pending:   { label: 'Pendiente',  color: 'var(--warning)' },
  approved:  { label: 'Aprobada',   color: 'var(--success)' },
  rejected:  { label: 'Rechazada',  color: 'var(--danger)' },
  cancelled: { label: 'Cancelada',  color: 'var(--text-2)' },
}

function StatusBadge({ status }) {
  const cfg = STATUS_CFG[status] || STATUS_CFG.pending
  return <span style={{ fontSize: 11, fontWeight: 700, padding: '2px 8px', borderRadius: 20, background: cfg.color + '20', color: cfg.color, border: `1px solid ${cfg.color}40`, textTransform: 'uppercase' }}>{cfg.label}</span>
}

function RequestModal({ onClose }) {
  const qc = useQueryClient()
  const toast = useToast()
  const [form, setForm] = useState({ type: 'vacation', start_date: '', end_date: '', reason: '' })
  const fs = { width: '100%', background: 'var(--surface-3)', border: '1px solid #1e2d45', borderRadius: 8, padding: '9px 12px', color: 'var(--text-1)', fontSize: 13, outline: 'none', fontFamily: 'inherit', boxSizing: 'border-box' }
  const ls = { fontSize: 11, fontWeight: 700, color: 'var(--text-2)', textTransform: 'uppercase', letterSpacing: '0.07em', display: 'block', marginBottom: 5 }
  const set = (k) => (e) => setForm(f => ({ ...f, [k]: e.target.value }))

  const { data: balance } = useQuery({
    queryKey: ['vacation-balance-my'],
    queryFn: () => api.get('/absences/my/vacation-balance').then(r => r.data).catch(() => null),
    staleTime: 60000,
  })

  const { mutate, isPending, error } = useMutation({
    mutationFn: (data) => api.post('/absences/my', data),
    onSuccess: () => { qc.invalidateQueries(['absences-my']); qc.invalidateQueries(['team-absences']); qc.invalidateQueries(['vacation-balance-my']); qc.invalidateQueries(['cal-absences']); qc.invalidateQueries(['absence-calendar']); onClose() },
    onError: e => toast.error(extractErr(e, 'Error')),
  })

  return (
    <Modal open title="Solicitar ausencia" onClose={onClose} width={460}>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
        {/* Balance de vacaciones */}
        {balance && form.type === 'vacation' && (
          <div style={{ display: 'flex', gap: 8, padding: '10px 14px',
            background: 'var(--surface-3)', borderRadius: 10,
            border: '1px solid var(--surface-4)' }}>
            {[
              { label: 'Disponibles', value: balance.days_remaining, color: balance.days_remaining > 5 ? 'var(--success)' : balance.days_remaining > 0 ? 'var(--warning)' : 'var(--danger)' },
              { label: 'Tomados', value: balance.days_taken, color: 'var(--text-2)' },
              { label: 'Pendientes', value: balance.days_pending, color: 'var(--warning)' },
              { label: 'Totales', value: balance.days_entitled, color: 'var(--accent)' },
            ].map(({ label, value, color }) => (
              <div key={label} style={{ flex: 1, textAlign: 'center' }}>
                <div style={{ fontSize: 18, fontWeight: 800, color, fontFamily: "'Space Mono', monospace" }}>{value}</div>
                <div style={{ fontSize: 10, color: 'var(--text-2)' }}>{label}</div>
              </div>
            ))}
          </div>
        )}
        <div>
          <label style={ls}>Tipo</label>
          <select value={form.type} onChange={set('type')} style={fs}>
            {Object.entries(TYPE_LABELS).map(([v, l]) => <option key={v} value={v}>{l}</option>)}
          </select>
        </div>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
          <div>
            <label style={ls}>Fecha inicio *</label>
            <input type="date" value={form.start_date} onChange={set('start_date')} style={fs} />
          </div>
          <div>
            <label style={ls}>Fecha fin *</label>
            <input type="date" value={form.end_date} onChange={set('end_date')} style={fs} />
          </div>
        </div>
        <div>
          <label style={ls}>Motivo (opcional)</label>
          <textarea value={form.reason} onChange={set('reason')} rows={2} style={{ ...fs, resize: 'vertical' }} placeholder="Motivo de la ausencia..." />
        </div>
        {error && <div style={{ fontSize: 13, color: 'var(--danger)', background: 'var(--danger-bg)', borderRadius: 8, padding: '8px 12px' }}>{Array.isArray(error.response?.data?.detail) ? error.response.data.detail.map(e => e.msg).join(', ') : (error.response?.data?.detail || 'Error al enviar la solicitud')}</div>}
        <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 10 }}>
          <Button variant="secondary" onClick={onClose}>Cancelar</Button>
          <Button onClick={() => mutate(form)}>
            {isPending ? 'Enviando...' : 'Solicitar'}
          </Button>
        </div>
      </div>
    </Modal>
  )
}

function ReviewModal({ absence, onClose }) {
  const toast = useToast()
  const qc = useQueryClient()
  const [notes, setNotes] = useState('')
  const { mutate, isPending } = useMutation({
    mutationFn: ({ approved }) => api.post(`/absences/${absence.id}/review`, { approved, rejection_reason: notes }),
    onSuccess: () => { qc.invalidateQueries(['absences-pending']); qc.invalidateQueries(['team-absences']); qc.invalidateQueries(['vacation-balance-my']); qc.invalidateQueries(['cal-absences']); qc.invalidateQueries(['absence-calendar']); qc.invalidateQueries(['capacity-board']); qc.invalidateQueries(['dash-team-load']); onClose() },
    onError: e => toast.error(extractErr(e, 'Error')),
  })
  return (
    <Modal open title={`Revisar ausencia — ${absence.user_name}`} onClose={onClose} width={460}>
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 12, marginBottom: 16 }}>
        {[
          { label: 'Tipo', value: TYPE_LABELS[absence.type]?.replace(/^\S+\s/, '') || absence.type },
          { label: 'Inicio', value: fmtDate(absence.start_date) },
          { label: 'Fin', value: fmtDate(absence.end_date) },
          { label: 'Días laborables', value: `${absence.working_days} días` },
        ].map(({ label, value }) => (
          <div key={label} style={{ background: 'var(--surface-3)', borderRadius: 8, padding: '10px 14px' }}>
            <div style={{ fontSize: 11, color: 'var(--text-2)', marginBottom: 3 }}>{label}</div>
            <div style={{ fontSize: 13, fontWeight: 600 }}>{value}</div>
          </div>
        ))}
      </div>
      {absence.reason && <p style={{ color: 'var(--text-2)', fontSize: 13, marginBottom: 16 }}>{absence.reason}</p>}
      <div style={{ marginBottom: 16 }}>
        <label style={{ fontSize: 11, fontWeight: 700, color: 'var(--text-2)', textTransform: 'uppercase', letterSpacing: '0.07em', display: 'block', marginBottom: 6 }}>Notas (motivo rechazo si aplica)</label>
        <textarea value={notes} onChange={e => setNotes(e.target.value)} rows={2}
          style={{ width: '100%', background: 'var(--surface-3)', border: '1px solid #1e2d45', borderRadius: 8, padding: '8px 12px', color: 'var(--text-1)', fontSize: 13, outline: 'none', fontFamily: 'inherit', resize: 'vertical', boxSizing: 'border-box' }} />
      </div>
      <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 10 }}>
        <Button variant="secondary" onClick={onClose}>Cancelar</Button>
        <Button variant="danger" onClick={() => mutate({ approved: false })} disabled={isPending} loading={isPending}>✕ Rechazar</Button>
        <Button onClick={() => mutate({ approved: true })} disabled={isPending} loading={isPending}>✓ Aprobar</Button>
      </div>
    </Modal>
  )
}

function CalendarView({ year, month }) {
  const { data } = useQuery({
    queryKey: ['absence-calendar', year, month],
    queryFn: () => api.get(`/absences/calendar?year=${year}&month=${month}`).then(r => r.data),
  })

  if (!data) return <Spinner />

  const daysInMonth = new Date(year, month, 0).getDate()
  const firstDay = (new Date(year, month - 1, 1).getDay() + 6) % 7  // Monday = 0
  const days = Array.from({ length: daysInMonth }, (_, i) => i + 1)

  const getAbsencesForDay = (day) => {
    const dateStr = `${year}-${String(month).padStart(2, '0')}-${String(day).padStart(2, '0')}`
    return data.absences.filter(a => a.start_date <= dateStr && a.end_date >= dateStr)
  }
  const isHoliday = (day) => {
    const dateStr = `${year}-${String(month).padStart(2, '0')}-${String(day).padStart(2, '0')}`
    return data.holidays.find(h => h.date === dateStr)
  }

  const MONTH_NAMES = ['', 'Enero', 'Febrero', 'Marzo', 'Abril', 'Mayo', 'Junio', 'Julio', 'Agosto', 'Septiembre', 'Octubre', 'Noviembre', 'Diciembre']
  const DAY_NAMES = ['L', 'M', 'X', 'J', 'V', 'S', 'D']

  return (
    <Card style={{ padding: 16 }}>
      <h3 style={{ fontSize: 14, fontWeight: 700, marginBottom: 16 }}>{MONTH_NAMES[month]} {year}</h3>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(7, 1fr)', gap: 4 }}>
        {DAY_NAMES.map(d => (
          <div key={d} style={{ textAlign: 'center', fontSize: 11, fontWeight: 700, color: 'var(--text-2)', padding: '4px 0' }}>{d}</div>
        ))}
        {Array.from({ length: firstDay }).map((_, i) => <div key={'empty-' + i} />)}
        {days.map(day => {
          const absences = getAbsencesForDay(day)
          const holiday = isHoliday(day)
          const isWeekend = (firstDay + day - 1) % 7 >= 5
          return (
            <div key={day} style={{ minHeight: 52, background: holiday ? 'var(--purple-bg)' : isWeekend ? 'var(--surface-1)' : 'var(--surface-2)', border: `1px solid ${holiday ? 'rgba(167,139,250,0.25)' : 'var(--surface-4)'}`, borderRadius: 6, padding: '4px 6px' }}>
              <div style={{ fontSize: 11, fontWeight: 700, color: holiday ? 'var(--purple)' : isWeekend ? 'var(--text-3)' : 'var(--text-2)', marginBottom: 2 }}>{day}</div>
              {holiday && <div style={{ fontSize: 9, color: 'var(--purple)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{holiday.name}</div>}
              {absences.slice(0, 2).map(a => (
                <div key={a.id} title={`${a.user_name} — ${TYPE_LABELS[a.type]}`}
                  style={{ fontSize: 9, background: 'var(--accent-glow)', color: 'var(--accent)', borderRadius: 3, padding: '1px 4px', marginBottom: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                  {a.user_name.split(' ')[0]}
                </div>
              ))}
              {absences.length > 2 && <div style={{ fontSize: 9, color: 'var(--text-2)' }}>+{absences.length - 2}</div>}
            </div>
          )
        })}
      </div>
    </Card>
  )
}

function EditAbsenceModal({ absence, onClose }) {
  const toast = useToast()
  const qc = useQueryClient()
  const [form, setForm] = useState({
    type:       absence.type       || 'vacation',
    start_date: absence.start_date || '',
    end_date:   absence.end_date   || '',
    reason:     absence.reason     || '',
  })

  const { mutate, isPending, error } = useMutation({
    mutationFn: (data) => api.patch(`/absences/my/${absence.id}`, data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['absences-my'] })
      qc.invalidateQueries({ queryKey: ['absences-pending'] })
      qc.invalidateQueries({ queryKey: ['vacation-balance-my'] })
      qc.invalidateQueries({ queryKey: ['cal-absences'] })
      qc.invalidateQueries({ queryKey: ['absence-calendar'] })
      toast.success('Ausencia actualizada')
      onClose()
    },
    onError: e => toast.error(e?.response?.data?.detail || 'Error al actualizar'),
  })

  const IS = { width:'100%', background:'var(--surface-3)', border:'1px solid var(--surface-4)',
    borderRadius:8, padding:'9px 12px', color:'var(--text-1)', fontSize:13,
    outline:'none', fontFamily:'inherit', boxSizing:'border-box' }
  const LS = { fontSize:11, fontWeight:600, color:'var(--text-2)', display:'block',
    marginBottom:5, textTransform:'uppercase', letterSpacing:'0.06em' }

  return (
    <Modal open title="Editar solicitud de ausencia" onClose={onClose} width={460}>
      <div style={{ display:'flex', flexDirection:'column', gap:14 }}>
        <div style={{ padding:'10px 14px', background:'var(--warning-bg)',
          border:'1px solid rgba(255,184,0,0.3)', borderRadius:8, fontSize:12, color:'var(--warning)' }}>
          ⚠️ Solo puedes editar ausencias en estado <strong>Pendiente</strong>.
        </div>

        <div>
          <label style={LS}>Tipo de ausencia</label>
          <select value={form.type} onChange={e => setForm(f=>({...f,type:e.target.value}))} style={IS}>
            {[['vacation','Vacaciones'],['sick','Baja médica'],['personal','Asunto personal'],
              ['training','Formación'],['maternity','Maternidad'],['paternity','Paternidad'],['other','Otro']
            ].map(([v,l]) => <option key={v} value={v}>{l}</option>)}
          </select>
        </div>

        <div style={{ display:'grid', gridTemplateColumns:'1fr 1fr', gap:12 }}>
          <div>
            <label style={LS}>Fecha inicio</label>
            <input type="date" value={form.start_date}
              onChange={e => setForm(f=>({...f,start_date:e.target.value}))} style={IS} />
          </div>
          <div>
            <label style={LS}>Fecha fin</label>
            <input type="date" value={form.end_date}
              onChange={e => setForm(f=>({...f,end_date:e.target.value}))} style={IS} />
          </div>
        </div>

        <div>
          <label style={LS}>Motivo (opcional)</label>
          <textarea value={form.reason} onChange={e => setForm(f=>({...f,reason:e.target.value}))}
            rows={3} placeholder="Describe el motivo de la ausencia..."
            style={{...IS, resize:'vertical'}} />
        </div>

        {error && (
          <div style={{ padding:'8px 12px', background:'var(--danger-bg)',
            border:'1px solid rgba(255,71,87,0.3)', borderRadius:8, fontSize:12, color:'var(--danger)' }}>
            {Array.isArray(error?.response?.data?.detail) ? error.response.data.detail.map(e => e.msg).join(', ') : (error?.response?.data?.detail || 'Error al actualizar')}
          </div>
        )}

        <div style={{ display:'flex', justifyContent:'flex-end', gap:10 }}>
          <Button variant="secondary" onClick={onClose}>Cancelar</Button>
          <Button
            onClick={() => mutate(form)}
            disabled={isPending || !form.start_date || !form.end_date}
            loading={isPending}>
            Guardar cambios
          </Button>
        </div>
      </div>
    </Modal>
  )
}


export default function AbsencesPage() {
  const t = useAppT()
  const { _user, hasRole } = useAuth()
  const toast = useToast()
  const qc = useQueryClient()
  const [tab, setTab] = useState('mine')
  const [showRequest, setShowRequest] = useState(false)
  const [reviewing, setReviewing] = useState(null)
  const [editingAbsence, setEditingAbsence] = useState(null)
  const today = new Date()
  const [calYear, setCalYear] = useState(today.getFullYear())
  const [calMonth, setCalMonth] = useState(today.getMonth() + 1)

  const { data: myAbsences = [], isLoading: loadingMine } = useQuery({
    queryKey: ['absences-my'],
    queryFn: () => api.get('/absences/my').then(r => r.data),
    enabled: tab === 'mine',
  })

  const { data: pending = [] } = useQuery({
    queryKey: ['absences-pending'],
    queryFn: () => api.get('/absences/pending').then(r => r.data),
    enabled: hasRole('admin', 'hr', 'pm'),
  })

  const { data: teamAbsences = [] } = useQuery({
    queryKey: ['team-absences'],
    queryFn: () => api.get('/absences/team').then(r => r.data),
    enabled: tab === 'team' && hasRole('admin', 'hr', 'pm'),
  })
  const { sort: teamAbsSort, setSort: setTeamAbsSort, sortedData: sortedTeamAbs } = useSort(teamAbsences, 'start_date', 'desc')

  const { mutate: cancel } = useMutation({
    mutationFn: (id) => api.delete(`/absences/my/${id}`),
    onSuccess: () => { qc.invalidateQueries(['absences-my']); qc.invalidateQueries(['vacation-balance-my']); qc.invalidateQueries(['cal-absences']); qc.invalidateQueries(['absence-calendar']); },
    onError: e => toast.error(extractErr(e, 'Error')),
  })

  const tabs = [
    { id: 'mine', label: '📋 Mis ausencias' },
    { id: 'calendar', label: '📅 Calendario' },
    ...(hasRole('admin', 'hr', 'pm') ? [
      { id: 'pending', label: `⏳ Pendientes (${pending.length})` },
      { id: 'team', label: '👥 Equipo' },
    ] : []),
  ]

  const MONTH_NAMES = ['', 'Enero', 'Febrero', 'Marzo', 'Abril', 'Mayo', 'Junio', 'Julio', 'Agosto', 'Septiembre', 'Octubre', 'Noviembre', 'Diciembre']

  return (
    <div style={{ padding: 32 }}>
      <PageHeader
        icon={<Umbrella size={18} />}
        title={t('absences.title')}
        subtitle="Gestión de ausencias con flujo de aprobación"
        actions={<Button onClick={() => setShowRequest(true)} icon="＋">Solicitar ausencia</Button>}
      />

      <div style={{ display: 'flex', gap: 10, marginBottom: 24 }}>
        {tabs.map(t => (
          <button key={t.id} onClick={() => setTab(t.id)}
            style={{ padding: '8px 18px', borderRadius: 8, border: `1px solid ${tab === t.id ? 'var(--accent-glow)' : 'var(--surface-4)'}`, background: tab === t.id ? 'var(--accent-muted)' : 'transparent', color: tab === t.id ? 'var(--accent)' : 'var(--text-2)', fontSize: 13, fontWeight: 600, cursor: 'pointer', fontFamily: 'inherit' }}>
            {t.label}
          </button>
        ))}
      </div>

      {tab === 'mine' && (
        loadingMine ? <Spinner /> : myAbsences.length === 0 ? (
          <EmptyState icon="🏖" title="Sin ausencias registradas" description="Solicita tus vacaciones o registra una ausencia" />
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
            {myAbsences.map(a => (
              <div key={a.id} style={{ display: 'flex', alignItems: 'center', gap: 16, padding: '14px 20px', background: 'var(--surface-2)', border: `1px solid ${a.status === 'rejected' ? 'var(--danger-border)' : a.status === 'approved' ? 'var(--success-border)' : 'var(--surface-4)'}`, borderRadius: 12 }}>
                <div style={{ flex: 1 }}>
                  <div style={{ fontSize: 14, fontWeight: 700, marginBottom: 4 }}>{TYPE_LABELS[a.type] || a.type}</div>
                  <div style={{ fontSize: 12, color: 'var(--text-2)' }}>
                    {fmtDate(a.start_date)} → {fmtDate(a.end_date)} · <span style={{ color: 'var(--text-1)' }}>{a.working_days} días laborables</span>
                  </div>
                  {a.rejection_reason && <div style={{ fontSize: 12, color: 'var(--danger)', marginTop: 4 }}>💬 {a.rejection_reason}</div>}
                </div>
                <StatusBadge status={a.status} />
                <div style={{ display:'flex', gap:6 }}>
                {a.status === 'pending' && (
                  <button onClick={() => setEditingAbsence(a)}
                    style={{ background:'none', border:'1px solid var(--surface-4)', borderRadius:6,
                      padding:'3px 10px', color:'var(--accent)', cursor:'pointer', fontSize:12, fontFamily:'inherit' }}>
                    ✏ Editar
                  </button>
                )}
                {(a.status === 'pending' || a.status === 'approved') && (
                  <button onClick={() => { openConfirmGlobal({ message: '¿Cancelar esta solicitud de ausencia?', onConfirm: () => cancel(a.id), danger: true }) }} style={{ background: 'none', border: '1px solid #ff475730', borderRadius: 6, padding: '4px 10px', color: 'var(--danger)', cursor: 'pointer', fontSize: 11, fontFamily: 'inherit' }}>Cancelar</button>
                )}
                </div>
              </div>
            ))}
          </div>
        )
      )}

      {tab === 'calendar' && (
        <div>
          <div style={{ display: 'flex', gap: 10, marginBottom: 20, alignItems: 'center' }}>
            <button onClick={() => { if (calMonth === 1) { setCalMonth(12); setCalYear(y => y - 1) } else setCalMonth(m => m - 1) }}
              style={{ background: 'var(--surface-2)', border: '1px solid #1e2d45', borderRadius: 8, padding: '7px 14px', color: 'var(--text-2)', cursor: 'pointer', fontFamily: 'inherit', fontSize: 16 }}>‹</button>
            <span style={{ fontSize: 16, fontWeight: 700, minWidth: 160, textAlign: 'center' }}>{MONTH_NAMES[calMonth]} {calYear}</span>
            <button onClick={() => { if (calMonth === 12) { setCalMonth(1); setCalYear(y => y + 1) } else setCalMonth(m => m + 1) }}
              style={{ background: 'var(--surface-2)', border: '1px solid #1e2d45', borderRadius: 8, padding: '7px 14px', color: 'var(--text-2)', cursor: 'pointer', fontFamily: 'inherit', fontSize: 16 }}>›</button>
          </div>
          <CalendarView year={calYear} month={calMonth} />
        </div>
      )}

      {tab === 'pending' && (
        pending.length === 0 ? (
          <EmptyState icon="✅" title="Sin solicitudes pendientes" description="Todas las ausencias están revisadas" />
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
            {pending.map(a => (
              <div key={a.id} style={{ display: 'flex', alignItems: 'center', gap: 16, padding: '14px 20px', background: 'var(--surface-2)', border: '1px solid #ffb80030', borderRadius: 12 }}>
                <div style={{ flex: 1 }}>
                  <div style={{ fontSize: 14, fontWeight: 700 }}>{a.user_name}</div>
                  <div style={{ fontSize: 12, color: 'var(--text-2)' }}>
                    {TYPE_LABELS[a.type]} · {fmtDate(a.start_date)} → {fmtDate(a.end_date)} · {a.working_days} días
                  </div>
                  {a.reason && <div style={{ fontSize: 12, color: 'var(--text-2)', marginTop: 2 }}>{a.reason}</div>}
                </div>
                <StatusBadge status={a.status} />
                <Button size="sm" onClick={() => setReviewing(a)}>Revisar</Button>
              </div>
            ))}
          </div>
        )
      )}

      {tab === 'team' && (
        teamAbsences.length === 0 ? (
          <EmptyState icon="👥" title="Sin ausencias del equipo" />
        ) : (
          <div style={{ background: 'var(--surface-2)', border: '1px solid #1e2d45', borderRadius: 12, overflow: 'hidden' }}>
            <div style={{ display: 'grid', gridTemplateColumns: '1.5fr 1fr 1fr 1fr 80px 100px', gap: 16, padding: '10px 20px', borderBottom: '1px solid #1e2d45', fontSize: 11, fontWeight: 700, color: 'var(--text-2)', textTransform: 'uppercase', letterSpacing: '0.07em', alignItems: 'center' }}>
              <SortableTH col="user_name" sort={teamAbsSort} onSort={setTeamAbsSort}>Persona</SortableTH>
              <SortableTH col="type" sort={teamAbsSort} onSort={setTeamAbsSort}>Tipo</SortableTH>
              <SortableTH col="start_date" sort={teamAbsSort} onSort={setTeamAbsSort}>Inicio</SortableTH>
              <SortableTH col="end_date" sort={teamAbsSort} onSort={setTeamAbsSort}>Fin</SortableTH>
              <SortableTH col="working_days" sort={teamAbsSort} onSort={setTeamAbsSort}>Días</SortableTH>
              <SortableTH col="status" sort={teamAbsSort} onSort={setTeamAbsSort}>Estado</SortableTH>
            </div>
            {sortedTeamAbs.map(a => (
              <div key={a.id} style={{ display: 'grid', gridTemplateColumns: '1.5fr 1fr 1fr 1fr 80px 100px', gap: 16, padding: '12px 20px', borderBottom: '1px solid #1e2d4530', alignItems: 'center' }}>
                <span style={{ fontSize: 13, fontWeight: 600 }}>{a.user_name}</span>
                <span style={{ fontSize: 12, color: 'var(--text-2)' }}>{TYPE_LABELS[a.type]?.replace(/^\S+\s/, '') || a.type}</span>
                <span style={{ fontSize: 12 }}>{fmtDate(a.start_date)}</span>
                <span style={{ fontSize: 12 }}>{fmtDate(a.end_date)}</span>
                <span style={{ fontSize: 12, fontFamily: "'Space Mono', monospace" }}>{a.working_days}d</span>
                <StatusBadge status={a.status} />
              </div>
            ))}
          </div>
        )
      )}

      {showRequest && <RequestModal onClose={() => setShowRequest(false)} />}
      {editingAbsence && (
        <EditAbsenceModal
          absence={editingAbsence}
          onClose={() => setEditingAbsence(null)}
        />
      )}
      {reviewing && <ReviewModal absence={reviewing} onClose={() => setReviewing(null)} />}
    </div>
  )
}