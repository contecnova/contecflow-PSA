import { useId, useState } from 'react'
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
import { z } from 'zod'
import { useFormValidation } from '../hooks/useFormValidation'

// ── Estilos compartidos ───────────────────────────────────────────────────────
const _fs = { width: '100%', background: 'var(--surface-3)', border: '1px solid var(--surface-4)', borderRadius: 8, padding: '8px 12px', color: 'var(--text-1)', fontSize: 13, outline: 'none', fontFamily: 'inherit', boxSizing: 'border-box' }
const _ls = { fontSize: 11, fontWeight: 600, color: 'var(--text-2)', textTransform: 'uppercase', letterSpacing: '0.07em', display: 'block', marginBottom: 5 }


const typeLabels = (t) => ({
  vacation: t('absences.type_vacation_full'),
  sick: t('absences.type_sick_full'),
  personal: t('absences.type_personal_full'),
  training: t('absences.type_training_full'),
  maternity: t('absences.type_maternity_full'),
  paternity: t('absences.type_paternity_full'),
  other: t('absences.type_other_full'),
})

const statusCfg = (t) => ({
  pending: { label: t('absences.status_pending'), color: 'var(--warning)' },
  approved: { label: t('absences.status_approved'), color: 'var(--success)' },
  rejected: { label: t('absences.status_rejected'), color: 'var(--danger)' },
  cancelled: { label: t('absences.status_cancelled'), color: 'var(--text-2)' },
})

const buildAbsenceRequestSchema = (t) => z.object({
  type: z.string().min(1, t('absences.error_type_required')),
  start_date: z.string().min(1, t('absences.error_start_required')),
  end_date: z.string().min(1, t('absences.error_end_required')),
  reason: z.string().optional(),
}).superRefine((data, ctx) => {
  if (data.end_date < data.start_date) {
    ctx.addIssue({
      code: z.ZodIssueCode.custom,
      path: ['end_date'],
      message: t('absences.error_end_before_start'),
    })
  }
})

const monthNames = (t) => ['', ...t('absences.months').split('|')]
const dayNamesShort = (t) => t('absences.days_short').split('|')

function StatusBadge({ status }) {
  const t = useAppT()
  const cfgMap = statusCfg(t)
  const cfg = cfgMap[status] || cfgMap.pending
  return <span style={{ fontSize: 11, fontWeight: 700, padding: '2px 8px', borderRadius: 20, background: cfg.color + '20', color: cfg.color, border: `1px solid ${cfg.color}40`, textTransform: 'uppercase' }}>{cfg.label}</span>
}

function RequestModal({ onClose }) {
  const t = useAppT()
  const idPrefix = useId()
  const qc = useQueryClient()
  const toast = useToast()
  const [form, setForm] = useState({ type: 'vacation', start_date: '', end_date: '', reason: '' })
  const validation = useFormValidation(buildAbsenceRequestSchema(t))
  const fs = { width: '100%', background: 'var(--surface-3)', border: '1px solid var(--surface-4)', borderRadius: 8, padding: '9px 12px', color: 'var(--text-1)', fontSize: 13, outline: 'none', fontFamily: 'inherit', boxSizing: 'border-box' }
  const ls = { fontSize: 11, fontWeight: 700, color: 'var(--text-2)', textTransform: 'uppercase', letterSpacing: '0.07em', display: 'block', marginBottom: 5 }
  const set = (k) => (e) => {
    setForm(f => ({ ...f, [k]: e.target.value }))
    validation.clearFieldError(k)
  }
  const typeId = `${idPrefix}-type`
  const startId = `${idPrefix}-start`
  const endId = `${idPrefix}-end`
  const reasonId = `${idPrefix}-reason`

  const { data: balance } = useQuery({
    queryKey: ['vacation-balance-my'],
    queryFn: () => api.get('/absences/my/vacation-balance').then(r => r.data).catch(() => null),
    staleTime: 60000,
  })

  const { mutate, isPending, error } = useMutation({
    mutationFn: (data) => api.post('/absences/my', data),
    onSuccess: () => { qc.invalidateQueries(['absences-my']); qc.invalidateQueries(['team-absences']); qc.invalidateQueries(['vacation-balance-my']); qc.invalidateQueries(['cal-absences']); qc.invalidateQueries(['absence-calendar']); validation.setErrors({}); onClose() },
    onError: e => toast.error(extractErr(e, t('common.error'))),
  })

  const submit = () => {
    const result = validation.validateForm(form)
    if (!result.success) return
    mutate(result.data)
  }

  return (
    <Modal open title={t('absences.modal_request_title')} onClose={onClose} width={460}>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
        {/* Balance de vacaciones */}
        {balance && form.type === 'vacation' && (
          <div style={{ display: 'flex', gap: 8, padding: '10px 14px',
            background: 'var(--surface-3)', borderRadius: 10,
            border: '1px solid var(--surface-4)' }}>
            {[
              { label: t('absences.balance_available'), value: balance.days_remaining, color: balance.days_remaining > 5 ? 'var(--success)' : balance.days_remaining > 0 ? 'var(--warning)' : 'var(--danger)' },
              { label: t('absences.balance_taken'), value: balance.days_taken, color: 'var(--text-2)' },
              { label: t('absences.balance_pending'), value: balance.days_pending, color: 'var(--warning)' },
              { label: t('absences.balance_total'), value: balance.days_entitled, color: 'var(--accent)' },
            ].map(({ label, value, color }) => (
              <div key={label} style={{ flex: 1, textAlign: 'center' }}>
                <div style={{ fontSize: 18, fontWeight: 800, color, fontFamily: "'Space Mono', monospace" }}>{value}</div>
                <div style={{ fontSize: 10, color: 'var(--text-2)' }}>{label}</div>
              </div>
            ))}
          </div>
        )}
        <div>
          <label htmlFor={typeId} style={ls}>{t('absences.label_type')}</label>
          <select id={typeId} value={form.type} onChange={set('type')} style={validation.inputStyle(fs, 'type')}>
            {Object.entries(typeLabels(t)).map(([v, l]) => <option key={v} value={v}>{l}</option>)}
          </select>
          {validation.errors.type && <div style={{ color: 'var(--danger)', fontSize: 11, marginTop: 4 }}>{validation.errors.type}</div>}
        </div>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
          <div>
            <label htmlFor={startId} style={ls}>{t('absences.label_start_required')}</label>
            <input id={startId} type="date" value={form.start_date} onChange={set('start_date')} style={validation.inputStyle(fs, 'start_date')} />
            {validation.errors.start_date && <div style={{ color: 'var(--danger)', fontSize: 11, marginTop: 4 }}>{validation.errors.start_date}</div>}
          </div>
          <div>
            <label htmlFor={endId} style={ls}>{t('absences.label_end_required')}</label>
            <input id={endId} type="date" value={form.end_date} onChange={set('end_date')} style={validation.inputStyle(fs, 'end_date')} />
            {validation.errors.end_date && <div style={{ color: 'var(--danger)', fontSize: 11, marginTop: 4 }}>{validation.errors.end_date}</div>}
          </div>
        </div>
        <div>
          <label htmlFor={reasonId} style={ls}>{t('absences.label_reason_optional')}</label>
          <textarea id={reasonId} value={form.reason} onChange={set('reason')} rows={2} style={{ ...fs, resize: 'vertical' }} placeholder={t('absences.reason_placeholder')} />
        </div>
        {error && <div style={{ fontSize: 13, color: 'var(--danger)', background: 'var(--danger-bg)', borderRadius: 8, padding: '8px 12px' }}>{Array.isArray(error.response?.data?.detail) ? error.response.data.detail.map(e => e.msg).join(', ') : (error.response?.data?.detail || t('absences.error_submit'))}</div>}
        <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 10 }}>
          <Button variant="secondary" onClick={onClose}>{t('common.cancel')}</Button>
          <Button onClick={submit} disabled={isPending}>
            {isPending ? t('absences.sending') : t('absences.request_action')}
          </Button>
        </div>
      </div>
    </Modal>
  )
}

function ReviewModal({ absence, onClose }) {
  const t = useAppT()
  const idPrefix = useId()
  const toast = useToast()
  const qc = useQueryClient()
  const [notes, setNotes] = useState('')
  const { mutate, isPending } = useMutation({
    mutationFn: ({ approved }) => api.post(`/absences/${absence.id}/review`, { approved, rejection_reason: notes }),
    onSuccess: () => { qc.invalidateQueries(['absences-pending']); qc.invalidateQueries(['team-absences']); qc.invalidateQueries(['vacation-balance-my']); qc.invalidateQueries(['cal-absences']); qc.invalidateQueries(['absence-calendar']); qc.invalidateQueries(['capacity-board']); qc.invalidateQueries(['dash-team-load']); onClose() },
    onError: e => toast.error(extractErr(e, t('common.error'))),
  })
  return (
    <Modal open title={`${t('absences.modal_review_title')} - ${absence.user_name}`} onClose={onClose} width={460}>
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 12, marginBottom: 16 }}>
        {[
          { label: t('absences.type_label'), value: typeLabels(t)[absence.type]?.replace(/^\S+\s/, '') || absence.type },
          { label: t('absences.start_label'), value: fmtDate(absence.start_date) },
          { label: t('absences.end_label'), value: fmtDate(absence.end_date) },
          { label: t('absences.working_days_label'), value: `${absence.working_days} ${t('absences.days_unit')}` },
        ].map(({ label, value }) => (
          <div key={label} style={{ background: 'var(--surface-3)', borderRadius: 8, padding: '10px 14px' }}>
            <div style={{ fontSize: 11, color: 'var(--text-2)', marginBottom: 3 }}>{label}</div>
            <div style={{ fontSize: 13, fontWeight: 600 }}>{value}</div>
          </div>
        ))}
      </div>
      {absence.reason && <p style={{ color: 'var(--text-2)', fontSize: 13, marginBottom: 16 }}>{absence.reason}</p>}
      <div style={{ marginBottom: 16 }}>
        <label htmlFor={`${idPrefix}-notes`} style={{ fontSize: 11, fontWeight: 700, color: 'var(--text-2)', textTransform: 'uppercase', letterSpacing: '0.07em', display: 'block', marginBottom: 6 }}>{t('absences.label_notes_rejection')}</label>
        <textarea id={`${idPrefix}-notes`} value={notes} onChange={e => setNotes(e.target.value)} rows={2}
          style={{ width: '100%', background: 'var(--surface-3)', border: '1px solid var(--surface-4)', borderRadius: 8, padding: '8px 12px', color: 'var(--text-1)', fontSize: 13, outline: 'none', fontFamily: 'inherit', resize: 'vertical', boxSizing: 'border-box' }} />
      </div>
      <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 10 }}>
        <Button variant="secondary" onClick={onClose}>{t('common.cancel')}</Button>
        <Button variant="danger" onClick={() => mutate({ approved: false })} disabled={isPending} loading={isPending}>{t('absences.reject_action')}</Button>
        <Button onClick={() => mutate({ approved: true })} disabled={isPending} loading={isPending}>{t('absences.approve_action')}</Button>
      </div>
    </Modal>
  )
}

function CalendarView({ year, month }) {
  const t = useAppT()
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

  const MONTH_NAMES = monthNames(t)
  const DAY_NAMES = dayNamesShort(t)

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
                <div key={a.id} title={`${a.user_name} - ${typeLabels(t)[a.type]}`}
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
  const t = useAppT()
  const idPrefix = useId()
  const toast = useToast()
  const qc = useQueryClient()
  const [form, setForm] = useState({
    type:       absence.type       || 'vacation',
    start_date: absence.start_date || '',
    end_date:   absence.end_date   || '',
    reason:     absence.reason     || '',
  })
  const validation = useFormValidation(buildAbsenceRequestSchema(t))

  const { mutate, isPending, error } = useMutation({
    mutationFn: (data) => api.patch(`/absences/my/${absence.id}`, data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['absences-my'] })
      qc.invalidateQueries({ queryKey: ['absences-pending'] })
      qc.invalidateQueries({ queryKey: ['vacation-balance-my'] })
      qc.invalidateQueries({ queryKey: ['cal-absences'] })
      qc.invalidateQueries({ queryKey: ['absence-calendar'] })
      validation.setErrors({})
      toast.success(t('absences.update_success'))
      onClose()
    },
    onError: e => toast.error(e?.response?.data?.detail || t('absences.error_update')),
  })

  const IS = { width:'100%', background:'var(--surface-3)', border:'1px solid var(--surface-4)',
    borderRadius:8, padding:'9px 12px', color:'var(--text-1)', fontSize:13,
    outline:'none', fontFamily:'inherit', boxSizing:'border-box' }
  const LS = { fontSize:11, fontWeight:600, color:'var(--text-2)', display:'block',
    marginBottom:5, textTransform:'uppercase', letterSpacing:'0.06em' }
  const typeId = `${idPrefix}-type`
  const startId = `${idPrefix}-start`
  const endId = `${idPrefix}-end`
  const reasonId = `${idPrefix}-reason`

  const setField = (key) => (e) => {
    setForm(f => ({ ...f, [key]: e.target.value }))
    validation.clearFieldError(key)
  }

  const submit = () => {
    const result = validation.validateForm(form)
    if (!result.success) return
    mutate(result.data)
  }

  return (
    <Modal open title={t('absences.modal_edit_title')} onClose={onClose} width={460}>
      <div style={{ display:'flex', flexDirection:'column', gap:14 }}>
        <div style={{ padding:'10px 14px', background:'var(--warning-bg)',
          border:'1px solid rgba(255,184,0,0.3)', borderRadius:8, fontSize:12, color:'var(--warning)' }}>
          {t('absences.warning_edit_pending_only')}
        </div>

        <div>
          <label htmlFor={typeId} style={LS}>{t('absences.label_type')}</label>
          <select id={typeId} value={form.type} onChange={setField('type')} style={validation.inputStyle(IS, 'type')}>
            {Object.entries(typeLabels(t)).map(([v, l]) => <option key={v} value={v}>{l}</option>)}
          </select>
          {validation.errors.type && <div style={{ color: 'var(--danger)', fontSize: 11, marginTop: 4 }}>{validation.errors.type}</div>}
        </div>

        <div style={{ display:'grid', gridTemplateColumns:'1fr 1fr', gap:12 }}>
          <div>
            <label htmlFor={startId} style={LS}>{t('absences.start_label')}</label>
            <input id={startId} type="date" value={form.start_date}
              onChange={setField('start_date')} style={validation.inputStyle(IS, 'start_date')} />
            {validation.errors.start_date && <div style={{ color: 'var(--danger)', fontSize: 11, marginTop: 4 }}>{validation.errors.start_date}</div>}
          </div>
          <div>
            <label htmlFor={endId} style={LS}>{t('absences.end_label')}</label>
            <input id={endId} type="date" value={form.end_date}
              onChange={setField('end_date')} style={validation.inputStyle(IS, 'end_date')} />
            {validation.errors.end_date && <div style={{ color: 'var(--danger)', fontSize: 11, marginTop: 4 }}>{validation.errors.end_date}</div>}
          </div>
        </div>

        <div>
          <label htmlFor={reasonId} style={LS}>{t('absences.label_reason_optional')}</label>
          <textarea id={reasonId} value={form.reason} onChange={setField('reason')}
            rows={3} placeholder={t('absences.reason_edit_placeholder')}
            style={{...IS, resize:'vertical'}} />
        </div>

        {error && (
          <div style={{ padding:'8px 12px', background:'var(--danger-bg)',
            border:'1px solid rgba(255,71,87,0.3)', borderRadius:8, fontSize:12, color:'var(--danger)' }}>
            {Array.isArray(error?.response?.data?.detail) ? error.response.data.detail.map(e => e.msg).join(', ') : (error?.response?.data?.detail || t('absences.error_update'))}
          </div>
        )}

        <div style={{ display:'flex', justifyContent:'flex-end', gap:10 }}>
          <Button variant="secondary" onClick={onClose}>{t('common.cancel')}</Button>
          <Button
            onClick={submit}
            disabled={isPending}
            loading={isPending}>
            {t('common.save')}
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
    onError: e => toast.error(extractErr(e, t('common.error'))),
  })

  const tabs = [
    { id: 'mine', label: t('absences.tab_mine') },
    { id: 'calendar', label: t('absences.tab_calendar') },
    ...(hasRole('admin', 'hr', 'pm') ? [
      { id: 'pending', label: `${t('absences.tab_pending')} (${pending.length})` },
      { id: 'team', label: t('absences.tab_team') },
    ] : []),
  ]

  const MONTH_NAMES = monthNames(t)

  return (
    <div style={{ padding: 32 }}>
      <PageHeader
        icon={<Umbrella size={18} />}
        title={t('absences.title')}
        subtitle={t('absences.subtitle')}
        actions={<Button onClick={() => setShowRequest(true)} icon="＋">{t('absences.request_absence_btn')}</Button>}
      />

      <div role="tablist" aria-label={t('absences.sections_aria')} style={{ display: 'flex', gap: 10, marginBottom: 20 , borderBottom: '1px solid var(--surface-4)', paddingBottom: 12 }}>
        {tabs.map(tabItem => (
          <button key={tabItem.id} role="tab" aria-selected={tab === tabItem.id} aria-controls={`absences-panel-${tabItem.id}`} id={`absences-tab-${tabItem.id}`} onClick={() => setTab(tabItem.id)}
            style={{ padding: '7px 16px', borderRadius: 8, border: `1px solid ${tab === tabItem.id ? 'var(--accent-glow)' : 'var(--surface-4)'}`, background: tab === tabItem.id ? 'var(--accent-muted)' : 'transparent', color: tab === tabItem.id ? 'var(--accent)' : 'var(--text-2)', fontSize: 12, fontWeight: 600, cursor: 'pointer', fontFamily: 'inherit' }}>
            {tabItem.label}
          </button>
        ))}
      </div>

      {tab === 'mine' && (
        <div id="absences-panel-mine" role="tabpanel" aria-labelledby="absences-tab-mine">
          {loadingMine ? <Spinner /> : myAbsences.length === 0 ? (
            <EmptyState icon="🏖" title={t('absences.no_absences')} description={t('absences.empty_mine_desc')} />
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
              {myAbsences.map(a => (
                <div key={a.id} style={{ display: 'flex', alignItems: 'center', gap: 16, padding: '14px 20px', background: 'var(--surface-2)', border: `1px solid ${a.status === 'rejected' ? 'var(--danger-border)' : a.status === 'approved' ? 'var(--success-border)' : 'var(--surface-4)'}`, borderRadius: 12 }}>
                  <div style={{ flex: 1 }}>
                    <div style={{ fontSize: 14, fontWeight: 700, marginBottom: 4 }}>{typeLabels(t)[a.type] || a.type}</div>
                    <div style={{ fontSize: 12, color: 'var(--text-2)' }}>
                      {fmtDate(a.start_date)} {'->'} {fmtDate(a.end_date)} · <span style={{ color: 'var(--text-1)' }}>{a.working_days} {t('absences.workdays_unit')}</span>
                    </div>
                    {a.rejection_reason && <div style={{ fontSize: 12, color: 'var(--danger)', marginTop: 4 }}>💬 {a.rejection_reason}</div>}
                  </div>
                  <StatusBadge status={a.status} />
                  <div style={{ display:'flex', gap:6 }}>
                    {a.status === 'pending' && (
                      <button aria-label={`${t('absences.edit_action')} ${typeLabels(t)[a.type] || a.type}`} onClick={() => setEditingAbsence(a)}
                        style={{ background:'none', border:'1px solid var(--surface-4)', borderRadius:6,
                          padding:'3px 10px', color:'var(--accent)', cursor:'pointer', fontSize:12, fontFamily:'inherit' }}>
                        {t('absences.edit_action')}
                      </button>
                    )}
                    {(a.status === 'pending' || a.status === 'approved') && (
                      <button aria-label={`${t('absences.cancel_action')} ${typeLabels(t)[a.type] || a.type}`} onClick={() => { openConfirmGlobal({ message: t('absences.cancel_confirm'), onConfirm: () => cancel(a.id), danger: true }) }} style={{ background: 'none', border: '1px solid #ff475730', borderRadius: 6, padding: '4px 10px', color: 'var(--danger)', cursor: 'pointer', fontSize: 11, fontFamily: 'inherit' }}>{t('absences.cancel_action')}</button>
                    )}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {tab === 'calendar' && (
        <div id="absences-panel-calendar" role="tabpanel" aria-labelledby="absences-tab-calendar">
          <div style={{ display: 'flex', gap: 10, marginBottom: 20, alignItems: 'center' }}>
            <button aria-label={t('absences.month_prev_aria')} onClick={() => { if (calMonth === 1) { setCalMonth(12); setCalYear(y => y - 1) } else setCalMonth(m => m - 1) }}
              style={{ background: 'var(--surface-2)', border: '1px solid var(--surface-4)', borderRadius: 8, padding: '7px 14px', color: 'var(--text-2)', cursor: 'pointer', fontFamily: 'inherit', fontSize: 16 }}>‹</button>
            <span aria-live="polite" style={{ fontSize: 16, fontWeight: 700, minWidth: 160, textAlign: 'center' }}>{MONTH_NAMES[calMonth]} {calYear}</span>
            <button aria-label={t('absences.month_next_aria')} onClick={() => { if (calMonth === 12) { setCalMonth(1); setCalYear(y => y + 1) } else setCalMonth(m => m + 1) }}
              style={{ background: 'var(--surface-2)', border: '1px solid var(--surface-4)', borderRadius: 8, padding: '7px 14px', color: 'var(--text-2)', cursor: 'pointer', fontFamily: 'inherit', fontSize: 16 }}>›</button>
          </div>
          <CalendarView year={calYear} month={calMonth} />
        </div>
      )}

      {tab === 'pending' && (
        <div id="absences-panel-pending" role="tabpanel" aria-labelledby="absences-tab-pending">
          {pending.length === 0 ? (
            <EmptyState icon="✅" title={t('absences.empty_pending_title')} description={t('absences.empty_pending_desc')} />
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
              {pending.map(a => (
                <div key={a.id} style={{ display: 'flex', alignItems: 'center', gap: 16, padding: '14px 20px', background: 'var(--surface-2)', border: '1px solid #ffb80030', borderRadius: 12 }}>
                  <div style={{ flex: 1 }}>
                    <div style={{ fontSize: 14, fontWeight: 700 }}>{a.user_name}</div>
                    <div style={{ fontSize: 12, color: 'var(--text-2)' }}>
                      {typeLabels(t)[a.type]} · {fmtDate(a.start_date)} {'->'} {fmtDate(a.end_date)} · {a.working_days} {t('absences.days_unit')}
                    </div>
                    {a.reason && <div style={{ fontSize: 12, color: 'var(--text-2)', marginTop: 2 }}>{a.reason}</div>}
                  </div>
                  <StatusBadge status={a.status} />
                  <Button size="sm" onClick={() => setReviewing(a)}>{t('absences.review_action')}</Button>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {tab === 'team' && (
        <div id="absences-panel-team" role="tabpanel" aria-labelledby="absences-tab-team">
          {teamAbsences.length === 0 ? (
            <EmptyState icon="👥" title={t('absences.empty_team_title')} />
          ) : (
            <div style={{ background: 'var(--surface-2)', border: '1px solid var(--surface-4)', borderRadius: 12, overflow: 'hidden' }}>
              <div style={{ display: 'grid', gridTemplateColumns: '1.5fr 1fr 1fr 1fr 80px 100px', gap: 16, padding: '10px 20px', borderBottom: '1px solid var(--surface-4)', fontSize: 11, fontWeight: 700, color: 'var(--text-2)', textTransform: 'uppercase', letterSpacing: '0.07em', alignItems: 'center' }}>
                <SortableTH col="user_name" sort={teamAbsSort} onSort={setTeamAbsSort}>{t('absences.person_col')}</SortableTH>
                <SortableTH col="type" sort={teamAbsSort} onSort={setTeamAbsSort}>{t('absences.type_label')}</SortableTH>
                <SortableTH col="start_date" sort={teamAbsSort} onSort={setTeamAbsSort}>{t('absences.start_label')}</SortableTH>
                <SortableTH col="end_date" sort={teamAbsSort} onSort={setTeamAbsSort}>{t('absences.end_label')}</SortableTH>
                <SortableTH col="working_days" sort={teamAbsSort} onSort={setTeamAbsSort}>{t('absences.days')}</SortableTH>
                <SortableTH col="status" sort={teamAbsSort} onSort={setTeamAbsSort}>{t('common.status')}</SortableTH>
              </div>
              {sortedTeamAbs.map(a => (
                <div key={a.id} style={{ display: 'grid', gridTemplateColumns: '1.5fr 1fr 1fr 1fr 80px 100px', gap: 16, padding: '12px 20px', borderBottom: '1px solid var(--surface-4)30', alignItems: 'center' }}>
                  <span style={{ fontSize: 13, fontWeight: 600 }}>{a.user_name}</span>
                  <span style={{ fontSize: 12, color: 'var(--text-2)' }}>{typeLabels(t)[a.type]?.replace(/^\S+\s/, '') || a.type}</span>
                  <span style={{ fontSize: 12 }}>{fmtDate(a.start_date)}</span>
                  <span style={{ fontSize: 12 }}>{fmtDate(a.end_date)}</span>
                  <span style={{ fontSize: 12, fontFamily: "'Space Mono', monospace" }}>{a.working_days}d</span>
                  <StatusBadge status={a.status} />
                </div>
              ))}
            </div>
          )}
        </div>
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