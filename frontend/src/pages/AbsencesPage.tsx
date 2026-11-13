import { useId, useState } from 'react'
import type { CSSProperties, ChangeEvent } from 'react'
import { openConfirmGlobal } from '../context/ConfirmContext'
import { useToast } from '../context/ToastContext'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { absencesApi } from '../services/api'
import { Card, Button, Modal, Spinner, EmptyState, useSort, SortableTH, Tabs, SearchInput, FilterSelect } from '../components/ui'
import PageHeader from '../components/layout/PageHeader'
import PageShell from '../components/layout/PageShell'
import { Umbrella } from 'lucide-react'
import { fmtDate, extractErr} from '../utils/helpers'
import { useAuth } from '../context/AuthContext'
import { useAppT } from '../i18n/AppLangContext'
import { z } from 'zod'
import { useFormValidation } from '../hooks/useFormValidation'
import DsBadge from '../components/ui/StatusBadge'
import DateInput from '../components/ui/DateInput'

// ── Estilos compartidos ───────────────────────────────────────────────────────
const _fs: CSSProperties = { width: '100%', background: 'var(--surface-3)', border: '1px solid var(--surface-4)', borderRadius: 8, padding: '9px 13px', color: 'var(--text-1)', fontSize: "var(--text-base)", outline: 'none', fontFamily: 'inherit', boxSizing: 'border-box' }
const _ls: CSSProperties = { fontSize: "var(--text-xs)", fontWeight: 600, color: 'var(--text-2)', textTransform: 'uppercase', letterSpacing: '0.07em', display: 'block', marginBottom: 5 }

type TFn = (moduleOrFullKey: string, keyOrParams?: string | Record<string, unknown>) => string

interface VacationBalance {
  days_remaining?: number
  days_taken?: number
  days_pending?: number
  days_entitled?: number
}

interface ApiError {
  response?: { data?: { detail?: unknown } }
}
// Render-equivalent formatter for backend validation detail (string | [{msg}]).
const errDetailText = (err: unknown, fallback: string): string => {
  const d = (err as ApiError)?.response?.data?.detail
  if (Array.isArray(d)) return d.map((e: { msg?: string }) => e?.msg).join(', ')
  return (typeof d === 'string' ? d : '') || fallback
}

type Absence = {
  [k: string]: unknown
  id: string
  type?: string
  status?: string
  start_date?: string
  end_date?: string
  reason?: string
  rejection_reason?: string
  user_name?: string
  working_days?: number
}

const typeLabels = (t: TFn): Record<string, string> => ({
  vacation: t('absences.type_vacation_full'),
  sick: t('absences.type_sick_full'),
  personal: t('absences.type_personal_full'),
  training: t('absences.type_training_full'),
  maternity: t('absences.type_maternity_full'),
  paternity: t('absences.type_paternity_full'),
  other: t('absences.type_other_full'),
})

const statusCfg = (t: TFn): Record<string, { label: string; color: string }> => ({
  pending: { label: t('absences.status_pending'), color: 'var(--warning)' },
  approved: { label: t('absences.status_approved'), color: 'var(--success)' },
  rejected: { label: t('absences.status_rejected'), color: 'var(--danger)' },
  cancelled: { label: t('absences.status_cancelled'), color: 'var(--text-2)' },
})

const buildAbsenceRequestSchema = (t: TFn) => z.object({
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

const monthNames = (t: TFn): string[] => ['', ...t('absences.months').split('|')]
const dayNamesShort = (t: TFn): string[] => t('absences.days_short').split('|')

function StatusBadge({ status }: { status?: string }) {
  const t = useAppT()
  const cfgMap = statusCfg(t)
  const cfg = cfgMap[status || ''] || cfgMap.pending
  return <DsBadge color={cfg.color}>{cfg.label}</DsBadge>
}

function RequestModal({ onClose }: { onClose: () => void }) {
  const t = useAppT()
  const idPrefix = useId()
  const qc = useQueryClient()
  const toast = useToast()
  const [form, setForm] = useState({ type: 'vacation', start_date: '', end_date: '', reason: '' })
  const validation = useFormValidation(buildAbsenceRequestSchema(t))
  const fs: CSSProperties = { width: '100%', background: 'var(--surface-3)', border: '1px solid var(--surface-4)', borderRadius: 8, padding: '9px 13px', color: 'var(--text-1)', fontSize: "var(--text-base)", outline: 'none', fontFamily: 'inherit', boxSizing: 'border-box' }
  const ls: CSSProperties = { fontSize: "var(--text-xs)", fontWeight: 700, color: 'var(--text-2)', textTransform: 'uppercase', letterSpacing: '0.07em', display: 'block', marginBottom: 5 }
  const set = (k: string) => (e: ChangeEvent<HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement>) => {
    setForm(f => ({ ...f, [k]: e.target.value }))
    validation.clearFieldError(k)
  }
  const typeId = `${idPrefix}-type`
  const startId = `${idPrefix}-start`
  const endId = `${idPrefix}-end`
  const reasonId = `${idPrefix}-reason`

  const { data: balance } = useQuery<VacationBalance | null>({
    queryKey: ['vacation-balance-my'],
    queryFn: () => absencesApi.vacationBalance().then(r => r.data as VacationBalance).catch(() => null),
    staleTime: 60000,
  })

  const { mutate, isPending, error } = useMutation({
    mutationFn: (data: Record<string, unknown>) => absencesApi.createMy(data),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['absences-my'] }); qc.invalidateQueries({ queryKey: ['team-absences'] }); qc.invalidateQueries({ queryKey: ['vacation-balance-my'] }); qc.invalidateQueries({ queryKey: ['cal-absences'] }); qc.invalidateQueries({ queryKey: ['absence-calendar'] }); validation.setErrors({}); onClose() },
    onError: (e: unknown) => toast.error(extractErr(e, t('common.error'))),
  })

  const submit = () => {
    const result = validation.validateForm(form)
    if (!result.success) return
    mutate(result.data as Record<string, unknown>)
  }

  return (
    <Modal open title={t('absences.modal_request_title')} onClose={onClose} width={460}>
      <div className="u-stack-14">
        {/* Balance de vacaciones */}
        {balance && form.type === 'vacation' && (
          <div style={{ display: 'flex', gap: 8, padding: '10px 14px',
            background: 'var(--surface-3)', borderRadius: 'var(--radius-md)',
            border: '1px solid var(--surface-4)' }}>
            {[
              { label: t('absences.balance_available'), value: balance.days_remaining, color: (balance.days_remaining ?? 0) > 5 ? 'var(--success)' : (balance.days_remaining ?? 0) > 0 ? 'var(--warning)' : 'var(--danger)' },
              { label: t('absences.balance_taken'), value: balance.days_taken, color: 'var(--text-2)' },
              { label: t('absences.balance_pending'), value: balance.days_pending, color: 'var(--warning)' },
              { label: t('absences.balance_total'), value: balance.days_entitled, color: 'var(--accent)' },
            ].map(({ label, value, color }) => (
              <div key={label} style={{ flex: 1, textAlign: 'center' }}>
                <div style={{ fontSize: "var(--text-lg-em)", fontWeight: 800, color, fontFamily: 'var(--font-mono)' }}>{value}</div>
                <div className="u-text2-2xs">{label}</div>
              </div>
            ))}
          </div>
        )}
        <div>
          <label htmlFor={typeId} style={ls}>{t('absences.label_type')}</label>
          <select id={typeId} value={form.type} onChange={set('type')} style={validation.inputStyle(fs, 'type')}>
            {Object.entries(typeLabels(t)).map(([v, l]) => <option key={v} value={v}>{l}</option>)}
          </select>
          {validation.errors.type && <div className="u-field-error">{validation.errors.type}</div>}
        </div>
        <div className="u-grid2-12">
          <div>
            <label htmlFor={startId} style={ls}>{t('absences.label_start_required')}</label>
            <DateInput id={startId} value={form.start_date} onChange={set('start_date')} style={validation.inputStyle(fs, 'start_date')} />
            {validation.errors.start_date && <div className="u-field-error">{validation.errors.start_date}</div>}
          </div>
          <div>
            <label htmlFor={endId} style={ls}>{t('absences.label_end_required')}</label>
            <DateInput id={endId} value={form.end_date} onChange={set('end_date')} style={validation.inputStyle(fs, 'end_date')} />
            {validation.errors.end_date && <div className="u-field-error">{validation.errors.end_date}</div>}
          </div>
        </div>
        <div>
          <label htmlFor={reasonId} style={ls}>{t('absences.label_reason_optional')}</label>
          <textarea id={reasonId} value={form.reason} onChange={set('reason')} rows={2} style={{ ...fs, resize: 'vertical' }} placeholder={t('absences.reason_placeholder')} />
        </div>
        {error ? <div style={{ fontSize: "var(--text-base)", color: 'var(--danger)', background: 'var(--danger-bg)', borderRadius: 8, padding: '8px 12px' }}>{errDetailText(error, t('absences.error_submit'))}</div> : null}
        <div className="u-actions-10">
          <Button variant="secondary" onClick={onClose}>{t('common.cancel')}</Button>
          <Button onClick={submit} disabled={isPending}>
            {isPending ? t('absences.sending') : t('absences.request_action')}
          </Button>
        </div>
      </div>
    </Modal>
  )
}

function ReviewModal({ absence, onClose }: { absence: Absence; onClose: () => void }) {
  const t = useAppT()
  const idPrefix = useId()
  const toast = useToast()
  const qc = useQueryClient()
  const [notes, setNotes] = useState('')
  const { mutate, isPending } = useMutation({
    mutationFn: ({ approved }: { approved: boolean }) => absencesApi.review(absence.id, { approved, rejection_reason: notes }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['absences-pending'] }); qc.invalidateQueries({ queryKey: ['team-absences'] }); qc.invalidateQueries({ queryKey: ['vacation-balance-my'] }); qc.invalidateQueries({ queryKey: ['cal-absences'] }); qc.invalidateQueries({ queryKey: ['absence-calendar'] }); qc.invalidateQueries({ queryKey: ['capacity-board'] }); qc.invalidateQueries({ queryKey: ['dash-team-load'] }); onClose() },
    onError: (e: unknown) => toast.error(extractErr(e, t('common.error'))),
  })
  return (
    <Modal open title={`${t('absences.modal_review_title')} - ${absence.user_name}`} onClose={onClose} width={460}>
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 12, marginBottom: 16 }}>
        {[
          { label: t('absences.type_label'), value: typeLabels(t)[absence.type || '']?.replace(/^\S+\s/, '') || absence.type },
          { label: t('absences.start_label'), value: fmtDate(absence.start_date) },
          { label: t('absences.end_label'), value: fmtDate(absence.end_date) },
          { label: t('absences.working_days_label'), value: `${absence.working_days} ${t('absences.days_unit')}` },
        ].map(({ label, value }) => (
          <div key={label} style={{ background: 'var(--surface-3)', borderRadius: 8, padding: '10px 14px' }}>
            <div style={{ fontSize: "var(--text-xs)", color: 'var(--text-2)', marginBottom: 3 }}>{label}</div>
            <div className="u-base-600">{value}</div>
          </div>
        ))}
      </div>
      {absence.reason && <p style={{ color: 'var(--text-2)', fontSize: "var(--text-base)", marginBottom: 16 }}>{absence.reason}</p>}
      <div className="u-mb-16">
        <label htmlFor={`${idPrefix}-notes`} style={{ fontSize: "var(--text-xs)", fontWeight: 700, color: 'var(--text-2)', textTransform: 'uppercase', letterSpacing: '0.07em', display: 'block', marginBottom: 6 }}>{t('absences.label_notes_rejection')}</label>
        <textarea id={`${idPrefix}-notes`} value={notes} onChange={e => setNotes(e.target.value)} rows={2}
          style={{ width: '100%', background: 'var(--surface-3)', border: '1px solid var(--surface-4)', borderRadius: 8, padding: '9px 13px', color: 'var(--text-1)', fontSize: "var(--text-base)", outline: 'none', fontFamily: 'inherit', resize: 'vertical', boxSizing: 'border-box' }} />
      </div>
      <div className="u-actions-10">
        <Button variant="secondary" onClick={onClose}>{t('common.cancel')}</Button>
        <Button variant="danger" onClick={() => mutate({ approved: false })} disabled={isPending} loading={isPending}>{t('absences.reject_action')}</Button>
        <Button onClick={() => mutate({ approved: true })} disabled={isPending} loading={isPending}>{t('absences.approve_action')}</Button>
      </div>
    </Modal>
  )
}

interface Holiday { date?: string; name?: string }
interface CalendarData { absences: Absence[]; holidays: Holiday[] }

function CalendarView({ year, month }: { year: number; month: number }) {
  const t = useAppT()
  const { data } = useQuery<CalendarData>({
    queryKey: ['absence-calendar', year, month],
    queryFn: () => absencesApi.calendar({ year, month }).then(r => r.data as CalendarData),
  })

  if (!data) return <Spinner />

  const daysInMonth = new Date(year, month, 0).getDate()
  const firstDay = (new Date(year, month - 1, 1).getDay() + 6) % 7  // Monday = 0
  const days = Array.from({ length: daysInMonth }, (_, i) => i + 1)

  const getAbsencesForDay = (day: number) => {
    const dateStr = `${year}-${String(month).padStart(2, '0')}-${String(day).padStart(2, '0')}`
    return data.absences.filter((a: Absence) => (a.start_date ?? '') <= dateStr && (a.end_date ?? '') >= dateStr)
  }
  const isHoliday = (day: number) => {
    const dateStr = `${year}-${String(month).padStart(2, '0')}-${String(day).padStart(2, '0')}`
    return data.holidays.find((h: Holiday) => h.date === dateStr)
  }

  const MONTH_NAMES = monthNames(t)
  const DAY_NAMES = dayNamesShort(t)

  return (
    <Card style={{ padding: 16 }}>
      <h3 style={{ fontSize: "var(--text-md)", fontWeight: 700, marginBottom: 16 }}>{MONTH_NAMES[month]} {year}</h3>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(7, 1fr)', gap: 4 }}>
        {DAY_NAMES.map(d => (
          <div key={d} style={{ textAlign: 'center', fontSize: "var(--text-xs)", fontWeight: 700, color: 'var(--text-2)', padding: '4px 0' }}>{d}</div>
        ))}
        {Array.from({ length: firstDay }).map((_, i) => <div key={'empty-' + i} />)}
        {days.map(day => {
          const absences = getAbsencesForDay(day)
          const holiday = isHoliday(day)
          const isWeekend = (firstDay + day - 1) % 7 >= 5
          return (
            <div key={day} style={{ minHeight: 52, background: holiday ? 'var(--purple-bg)' : isWeekend ? 'var(--surface-1)' : 'var(--surface-2)', border: `1px solid ${holiday ? 'rgba(167,139,250,0.25)' : 'var(--surface-4)'}`, borderRadius: 'var(--radius-sm)', padding: '4px 6px' }}>
              <div style={{ fontSize: "var(--text-xs)", fontWeight: 700, color: holiday ? 'var(--purple)' : isWeekend ? 'var(--text-3)' : 'var(--text-2)', marginBottom: 2 }}>{day}</div>
              {holiday && <div style={{ fontSize: "var(--text-3xs)", color: 'var(--purple)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{holiday.name}</div>}
              {absences.slice(0, 2).map(a => (
                <div key={a.id} title={`${a.user_name} - ${typeLabels(t)[a.type || '']}`}
                  style={{ fontSize: "var(--text-3xs)", background: 'var(--accent-glow)', color: 'var(--accent)', borderRadius: 3, padding: '1px 4px', marginBottom: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                  {(a.user_name || '').split(' ')[0]}
                </div>
              ))}
              {absences.length > 2 && <div style={{ fontSize: "var(--text-3xs)", color: 'var(--text-2)' }}>+{absences.length - 2}</div>}
            </div>
          )
        })}
      </div>
    </Card>
  )
}

function EditAbsenceModal({ absence, onClose }: { absence: Absence; onClose: () => void }) {
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
    mutationFn: (data: Record<string, unknown>) => absencesApi.updateMy(absence.id, data),
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
    onError: (e: unknown) => toast.error(errDetailText(e, t('absences.error_update'))),
  })

  const IS: CSSProperties = { width:'100%', background:'var(--surface-3)', border:'1px solid var(--surface-4)',
    borderRadius:8, padding:'9px 12px', color:'var(--text-1)', fontSize: "var(--text-base)",
    outline:'none', fontFamily:'inherit', boxSizing:'border-box' }
  const LS: CSSProperties = { fontSize: "var(--text-xs)", fontWeight:600, color:'var(--text-2)', display:'block',
    marginBottom:5, textTransform:'uppercase', letterSpacing:'0.06em' }
  const typeId = `${idPrefix}-type`
  const startId = `${idPrefix}-start`
  const endId = `${idPrefix}-end`
  const reasonId = `${idPrefix}-reason`

  const setField = (key: string) => (e: ChangeEvent<HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement>) => {
    setForm(f => ({ ...f, [key]: e.target.value }))
    validation.clearFieldError(key)
  }

  const submit = () => {
    const result = validation.validateForm(form)
    if (!result.success) return
    mutate(result.data as Record<string, unknown>)
  }

  return (
    <Modal open title={t('absences.modal_edit_title')} onClose={onClose} width={460}>
      <div className="u-stack-14">
        <div style={{ padding:'10px 14px', background:'var(--warning-bg)',
          border:'1px solid rgba(255,184,0,0.3)', borderRadius:8, fontSize: "var(--text-sm)", color:'var(--warning)' }}>
          {t('absences.warning_edit_pending_only')}
        </div>

        <div>
          <label htmlFor={typeId} style={LS}>{t('absences.label_type')}</label>
          <select id={typeId} value={form.type} onChange={setField('type')} style={validation.inputStyle(IS, 'type')}>
            {Object.entries(typeLabels(t)).map(([v, l]) => <option key={v} value={v}>{l}</option>)}
          </select>
          {validation.errors.type && <div className="u-field-error">{validation.errors.type}</div>}
        </div>

        <div className="u-grid2-12">
          <div>
            <label htmlFor={startId} style={LS}>{t('absences.start_label')}</label>
            <DateInput id={startId} value={form.start_date}
              onChange={setField('start_date')} style={validation.inputStyle(IS, 'start_date')} />
            {validation.errors.start_date && <div className="u-field-error">{validation.errors.start_date}</div>}
          </div>
          <div>
            <label htmlFor={endId} style={LS}>{t('absences.end_label')}</label>
            <DateInput id={endId} value={form.end_date}
              onChange={setField('end_date')} style={validation.inputStyle(IS, 'end_date')} />
            {validation.errors.end_date && <div className="u-field-error">{validation.errors.end_date}</div>}
          </div>
        </div>

        <div>
          <label htmlFor={reasonId} style={LS}>{t('absences.label_reason_optional')}</label>
          <textarea id={reasonId} value={form.reason} onChange={setField('reason')}
            rows={3} placeholder={t('absences.reason_edit_placeholder')}
            style={{...IS, resize:'vertical'} as CSSProperties} />
        </div>

        {error ? (
          <div style={{ padding:'8px 12px', background:'var(--danger-bg)',
            border:'1px solid rgba(255,71,87,0.3)', borderRadius:8, fontSize: "var(--text-sm)", color:'var(--danger)' }}>
            {errDetailText(error, t('absences.error_update'))}
          </div>
        ) : null}

        <div className="u-actions-10">
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


export default function AbsencesPage(): JSX.Element {
  const t = useAppT()
  const { hasRole } = useAuth()
  const toast = useToast()
  const qc = useQueryClient()
  const [tab, setTab] = useState('mine')
  const [showRequest, setShowRequest] = useState(false)
  const [reviewing, setReviewing] = useState<Absence | null>(null)
  const [editingAbsence, setEditingAbsence] = useState<Absence | null>(null)
  const today = new Date()
  const [calYear, setCalYear] = useState(today.getFullYear())
  const [calMonth, setCalMonth] = useState(today.getMonth() + 1)

  const unwrapAbsences = (r: { data?: unknown }): Absence[] => {
    const d = r.data as { items?: Absence[] } | Absence[] | null | undefined
    return (Array.isArray(d) ? d : d?.items ?? []) as Absence[]
  }

  const { data: myAbsences = [], isLoading: loadingMine } = useQuery<Absence[]>({
    queryKey: ['absences-my'],
    queryFn: () => absencesApi.my({}).then(unwrapAbsences),
    enabled: tab === 'mine',
  })

  const { data: pending = [] } = useQuery<Absence[]>({
    queryKey: ['absences-pending'],
    queryFn: () => absencesApi.pending().then(unwrapAbsences),
    enabled: hasRole('admin', 'hr', 'pm', 'team_lead'),
  })

  const { data: teamAbsences = [] } = useQuery<Absence[]>({
    queryKey: ['team-absences'],
    queryFn: () => absencesApi.team({}).then(r => r.data as Absence[]),
    enabled: tab === 'team' && hasRole('admin', 'hr', 'pm', 'team_lead'),
  })
  const [teamSearch, setTeamSearch] = useState('')
  const [teamFilterType, setTeamFilterType] = useState('')
  const [teamFilterStatus, setTeamFilterStatus] = useState('')
  const [teamFilterFrom, setTeamFilterFrom] = useState('')
  const [teamFilterTo, setTeamFilterTo] = useState('')
  const filteredTeamAbs = teamAbsences.filter(a => {
    if (teamSearch && !(a.user_name || '').toLowerCase().includes(teamSearch.toLowerCase())) return false
    if (teamFilterType && a.type !== teamFilterType) return false
    if (teamFilterStatus && a.status !== teamFilterStatus) return false
    if (teamFilterFrom && a.end_date && a.end_date < teamFilterFrom) return false
    if (teamFilterTo && a.start_date && a.start_date > teamFilterTo) return false
    return true
  })
  const { sort: teamAbsSort, setSort: setTeamAbsSort, sortedData: sortedTeamAbs } = useSort(filteredTeamAbs, 'start_date', 'desc')

  // Mine filters
  const [mineFilterType, setMineFilterType] = useState('')
  const [mineFilterStatus, setMineFilterStatus] = useState('')
  const [mineFilterFrom, setMineFilterFrom] = useState('')
  const [mineFilterTo, setMineFilterTo] = useState('')
  const filteredMine = myAbsences.filter(a => {
    if (mineFilterType && a.type !== mineFilterType) return false
    if (mineFilterStatus && a.status !== mineFilterStatus) return false
    if (mineFilterFrom && a.end_date && a.end_date < mineFilterFrom) return false
    if (mineFilterTo && a.start_date && a.start_date > mineFilterTo) return false
    return true
  })

  // Pending filters
  const [pendingSearch, setPendingSearch] = useState('')
  const [pendingFilterType, setPendingFilterType] = useState('')
  const [pendingFilterFrom, setPendingFilterFrom] = useState('')
  const [pendingFilterTo, setPendingFilterTo] = useState('')
  const filteredPending = pending.filter(a => {
    if (pendingSearch && !(a.user_name || '').toLowerCase().includes(pendingSearch.toLowerCase())) return false
    if (pendingFilterType && a.type !== pendingFilterType) return false
    if (pendingFilterFrom && a.end_date && a.end_date < pendingFilterFrom) return false
    if (pendingFilterTo && a.start_date && a.start_date > pendingFilterTo) return false
    return true
  })

  const { mutate: cancel } = useMutation({
    mutationFn: (id: string) => absencesApi.deleteMy(id),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['absences-my'] }); qc.invalidateQueries({ queryKey: ['vacation-balance-my'] }); qc.invalidateQueries({ queryKey: ['cal-absences'] }); qc.invalidateQueries({ queryKey: ['absence-calendar'] }); },
    onError: (e: unknown) => toast.error(extractErr(e, t('common.error'))),
  })

  const tabs = [
    { id: 'mine', label: t('absences.tab_mine') },
    { id: 'calendar', label: t('absences.tab_calendar') },
    ...(hasRole('admin', 'hr', 'pm', 'team_lead') ? [
      { id: 'pending', label: `${t('absences.tab_pending')} (${pending.length})` },
      { id: 'team', label: t('absences.tab_team') },
    ] : []),
  ]

  const MONTH_NAMES = monthNames(t)

  return (
    <PageShell>
      <PageHeader
        icon={<Umbrella size={18} />}
        title={t('absences.title')}
        subtitle={t('absences.subtitle')}
        actions={<Button onClick={() => setShowRequest(true)} icon="＋">{t('absences.request_absence_btn')}</Button>}
      />

      <Tabs
        items={tabs}
        active={tab}
        onChange={setTab}
        ariaLabel={t('absences.sections_aria')}
        style={{ marginBottom: 20, paddingBottom: 12, borderBottom: '1px solid var(--surface-4)' }}
      />

      {tab === 'mine' && (
        <div id="absences-panel-mine" role="tabpanel" aria-labelledby="absences-tab-mine">
          {loadingMine ? <Spinner /> : myAbsences.length === 0 ? (
            <EmptyState icon="🏖" title={t('absences.no_absences')} description={t('absences.empty_mine_desc')} />
          ) : (
            <>
              <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginBottom: 14, alignItems: 'center' }}>
                <FilterSelect value={mineFilterType} onChange={setMineFilterType} placeholder={t('absences.type_label')} options={Object.entries(typeLabels(t)).map(([v, l]) => ({ value: v, label: l.replace(/^\S+\s/, '') }))} />
                <FilterSelect value={mineFilterStatus} onChange={setMineFilterStatus} placeholder={t('common.status')} options={[
                  { value: 'pending', label: t('absences.status_pending') },
                  { value: 'approved', label: t('absences.status_approved') },
                  { value: 'rejected', label: t('absences.status_rejected') },
                  { value: 'cancelled', label: t('absences.status_cancelled') },
                ]} />
                <DateInput aria-label={t('absences.start_label')} value={mineFilterFrom} onChange={e => setMineFilterFrom(e.target.value)}
                  style={{ background: mineFilterFrom ? 'var(--accent-muted)' : 'var(--surface-2)', border: `1px solid ${mineFilterFrom ? 'var(--accent)' : 'var(--surface-4)'}`, borderRadius: 8, padding: '8px 12px', color: mineFilterFrom ? 'var(--accent)' : 'var(--text-1)', fontSize: 'var(--text-sm)', fontFamily: 'inherit', outline: 'none' }} />
                <span className="u-text3">—</span>
                <DateInput aria-label={t('absences.end_label')} value={mineFilterTo} onChange={e => setMineFilterTo(e.target.value)}
                  style={{ background: mineFilterTo ? 'var(--accent-muted)' : 'var(--surface-2)', border: `1px solid ${mineFilterTo ? 'var(--accent)' : 'var(--surface-4)'}`, borderRadius: 8, padding: '8px 12px', color: mineFilterTo ? 'var(--accent)' : 'var(--text-1)', fontSize: 'var(--text-sm)', fontFamily: 'inherit', outline: 'none' }} />
                {(mineFilterType || mineFilterStatus || mineFilterFrom || mineFilterTo) && (
                  <button onClick={() => { setMineFilterType(''); setMineFilterStatus(''); setMineFilterFrom(''); setMineFilterTo('') }}
                    style={{ background: 'transparent', border: '1px solid var(--surface-4)', borderRadius: 8, padding: '8px 12px', color: 'var(--text-2)', fontSize: 'var(--text-sm)', cursor: 'pointer', fontFamily: 'inherit' }}>
                    {t('common.clear', 'Limpiar')}
                  </button>
                )}
                <span style={{ marginLeft: 'auto', fontSize: 'var(--text-xs)', color: 'var(--text-3)' }}>{filteredMine.length} / {myAbsences.length}</span>
              </div>
              {filteredMine.length === 0 ? (
                <EmptyState icon="🔍" title={t('common.no_results', 'Sin resultados con los filtros aplicados')} />
              ) : (
                <div className="u-stack-10">
                  {filteredMine.map(a => (
                    <div key={a.id} style={{ display: 'flex', alignItems: 'center', gap: 16, padding: '14px 20px', background: 'var(--surface-2)', border: `1px solid ${a.status === 'rejected' ? 'var(--danger-border)' : a.status === 'approved' ? 'var(--success-border)' : 'var(--surface-4)'}`, borderRadius: 12 }}>
                      <div className="u-flex1">
                        <div style={{ fontSize: "var(--text-md)", fontWeight: 700, marginBottom: 4 }}>{typeLabels(t)[a.type || ""] || a.type}</div>
                        <div className="u-text2-sm">
                          {fmtDate(a.start_date)} {'->'} {fmtDate(a.end_date)} · <span className="u-text1">{a.working_days} {t('absences.workdays_unit')}</span>
                        </div>
                        {a.rejection_reason && <div style={{ fontSize: "var(--text-sm)", color: 'var(--danger)', marginTop: 4 }}>💬 {a.rejection_reason}</div>}
                      </div>
                      <StatusBadge status={a.status} />
                      <div className="u-row-6">
                        {a.status === 'pending' && (
                          <button aria-label={`${t('absences.edit_action')} ${typeLabels(t)[a.type || ""] || a.type}`} onClick={() => setEditingAbsence(a)}
                            style={{ background:'none', border:'1px solid var(--surface-4)', borderRadius:'var(--radius-sm)',
                              padding:'3px 10px', color:'var(--accent)', cursor:'pointer', fontSize: "var(--text-sm)", fontFamily:'inherit' }}>
                            {t('absences.edit_action')}
                          </button>
                        )}
                        {(a.status === 'pending' || a.status === 'approved') && (
                          <button aria-label={`${t('absences.cancel_action')} ${typeLabels(t)[a.type || ""] || a.type}`} onClick={() => { openConfirmGlobal({ message: t('absences.cancel_confirm'), onConfirm: () => cancel(a.id), danger: true }) }} style={{ background: 'none', border: '1px solid var(--danger-border)', borderRadius: 'var(--radius-sm)', padding: '4px 10px', color: 'var(--danger)', cursor: 'pointer', fontSize: "var(--text-xs)", fontFamily: 'inherit' }}>{t('absences.cancel_action')}</button>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </>
          )}
        </div>
      )}

      {tab === 'calendar' && (
        <div id="absences-panel-calendar" role="tabpanel" aria-labelledby="absences-tab-calendar">
          <div style={{ display: 'flex', gap: 10, marginBottom: 20, alignItems: 'center' }}>
            <button aria-label={t('absences.month_prev_aria')} onClick={() => { if (calMonth === 1) { setCalMonth(12); setCalYear(y => y - 1) } else setCalMonth(m => m - 1) }}
              style={{ background: 'var(--surface-2)', border: '1px solid var(--surface-4)', borderRadius: 8, padding: '7px 14px', color: 'var(--text-2)', cursor: 'pointer', fontFamily: 'inherit', fontSize: "var(--text-lg)" }}>‹</button>
            <span aria-live="polite" style={{ fontSize: "var(--text-lg)", fontWeight: 700, minWidth: 160, textAlign: 'center' }}>{MONTH_NAMES[calMonth]} {calYear}</span>
            <button aria-label={t('absences.month_next_aria')} onClick={() => { if (calMonth === 12) { setCalMonth(1); setCalYear(y => y + 1) } else setCalMonth(m => m + 1) }}
              style={{ background: 'var(--surface-2)', border: '1px solid var(--surface-4)', borderRadius: 8, padding: '7px 14px', color: 'var(--text-2)', cursor: 'pointer', fontFamily: 'inherit', fontSize: "var(--text-lg)" }}>›</button>
          </div>
          <CalendarView year={calYear} month={calMonth} />
        </div>
      )}

      {tab === 'pending' && (
        <div id="absences-panel-pending" role="tabpanel" aria-labelledby="absences-tab-pending">
          {pending.length === 0 ? (
            <EmptyState icon="✅" title={t('absences.empty_pending_title')} description={t('absences.empty_pending_desc')} />
          ) : (
            <>
              <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginBottom: 14, alignItems: 'center' }}>
                <SearchInput value={pendingSearch} onChange={setPendingSearch} placeholder={t('absences.search_person', 'Buscar persona...')} style={{ minWidth: 220, flex: '1 1 220px', maxWidth: 320 }} />
                <FilterSelect value={pendingFilterType} onChange={setPendingFilterType} placeholder={t('absences.type_label')} options={Object.entries(typeLabels(t)).map(([v, l]) => ({ value: v, label: l.replace(/^\S+\s/, '') }))} />
                <DateInput aria-label={t('absences.start_label')} value={pendingFilterFrom} onChange={e => setPendingFilterFrom(e.target.value)}
                  style={{ background: pendingFilterFrom ? 'var(--accent-muted)' : 'var(--surface-2)', border: `1px solid ${pendingFilterFrom ? 'var(--accent)' : 'var(--surface-4)'}`, borderRadius: 8, padding: '8px 12px', color: pendingFilterFrom ? 'var(--accent)' : 'var(--text-1)', fontSize: 'var(--text-sm)', fontFamily: 'inherit', outline: 'none' }} />
                <span className="u-text3">—</span>
                <DateInput aria-label={t('absences.end_label')} value={pendingFilterTo} onChange={e => setPendingFilterTo(e.target.value)}
                  style={{ background: pendingFilterTo ? 'var(--accent-muted)' : 'var(--surface-2)', border: `1px solid ${pendingFilterTo ? 'var(--accent)' : 'var(--surface-4)'}`, borderRadius: 8, padding: '8px 12px', color: pendingFilterTo ? 'var(--accent)' : 'var(--text-1)', fontSize: 'var(--text-sm)', fontFamily: 'inherit', outline: 'none' }} />
                {(pendingSearch || pendingFilterType || pendingFilterFrom || pendingFilterTo) && (
                  <button onClick={() => { setPendingSearch(''); setPendingFilterType(''); setPendingFilterFrom(''); setPendingFilterTo('') }}
                    style={{ background: 'transparent', border: '1px solid var(--surface-4)', borderRadius: 8, padding: '8px 12px', color: 'var(--text-2)', fontSize: 'var(--text-sm)', cursor: 'pointer', fontFamily: 'inherit' }}>
                    {t('common.clear', 'Limpiar')}
                  </button>
                )}
                <span style={{ marginLeft: 'auto', fontSize: 'var(--text-xs)', color: 'var(--text-3)' }}>{filteredPending.length} / {pending.length}</span>
              </div>
              {filteredPending.length === 0 ? (
                <EmptyState icon="🔍" title={t('common.no_results', 'Sin resultados con los filtros aplicados')} />
              ) : (
                <div className="u-stack-10">
                  {filteredPending.map(a => (
                    <div key={a.id} style={{ display: 'flex', alignItems: 'center', gap: 16, padding: '14px 20px', background: 'var(--surface-2)', border: '1px solid var(--warning-border)', borderRadius: 12 }}>
                      <div className="u-flex1">
                        <div className="u-md-700">{a.user_name}</div>
                        <div className="u-text2-sm">
                          {typeLabels(t)[a.type || ""]} · {fmtDate(a.start_date)} {'->'} {fmtDate(a.end_date)} · {a.working_days} {t('absences.days_unit')}
                        </div>
                        {a.reason && <div className="u-text2-sm-mt2">{a.reason}</div>}
                      </div>
                      <StatusBadge status={a.status} />
                      <Button size="sm" onClick={() => setReviewing(a)}>{t('absences.review_action')}</Button>
                    </div>
                  ))}
                </div>
              )}
            </>
          )}
        </div>
      )}

      {tab === 'team' && (
        <div id="absences-panel-team" role="tabpanel" aria-labelledby="absences-tab-team">
          <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginBottom: 14, alignItems: 'center' }}>
            <SearchInput value={teamSearch} onChange={setTeamSearch} placeholder={t('absences.search_person', 'Buscar persona...')} style={{ minWidth: 220, flex: '1 1 220px', maxWidth: 320 }} />
            <FilterSelect value={teamFilterType} onChange={setTeamFilterType} placeholder={t('absences.type_label')} options={Object.entries(typeLabels(t)).map(([v, l]) => ({ value: v, label: l.replace(/^\S+\s/, '') }))} />
            <FilterSelect value={teamFilterStatus} onChange={setTeamFilterStatus} placeholder={t('common.status')} options={[
              { value: 'pending', label: t('absences.status_pending') },
              { value: 'approved', label: t('absences.status_approved') },
              { value: 'rejected', label: t('absences.status_rejected') },
              { value: 'cancelled', label: t('absences.status_cancelled') },
            ]} />
            <DateInput aria-label={t('absences.start_label')} value={teamFilterFrom} onChange={e => setTeamFilterFrom(e.target.value)}
              style={{ background: teamFilterFrom ? 'var(--accent-muted)' : 'var(--surface-2)', border: `1px solid ${teamFilterFrom ? 'var(--accent)' : 'var(--surface-4)'}`, borderRadius: 8, padding: '8px 12px', color: teamFilterFrom ? 'var(--accent)' : 'var(--text-1)', fontSize: 'var(--text-sm)', fontFamily: 'inherit', outline: 'none' }} />
            <span className="u-text3">—</span>
            <DateInput aria-label={t('absences.end_label')} value={teamFilterTo} onChange={e => setTeamFilterTo(e.target.value)}
              style={{ background: teamFilterTo ? 'var(--accent-muted)' : 'var(--surface-2)', border: `1px solid ${teamFilterTo ? 'var(--accent)' : 'var(--surface-4)'}`, borderRadius: 8, padding: '8px 12px', color: teamFilterTo ? 'var(--accent)' : 'var(--text-1)', fontSize: 'var(--text-sm)', fontFamily: 'inherit', outline: 'none' }} />
            {(teamSearch || teamFilterType || teamFilterStatus || teamFilterFrom || teamFilterTo) && (
              <button onClick={() => { setTeamSearch(''); setTeamFilterType(''); setTeamFilterStatus(''); setTeamFilterFrom(''); setTeamFilterTo('') }}
                style={{ background: 'transparent', border: '1px solid var(--surface-4)', borderRadius: 8, padding: '8px 12px', color: 'var(--text-2)', fontSize: 'var(--text-sm)', cursor: 'pointer', fontFamily: 'inherit' }}>
                {t('common.clear', 'Limpiar')}
              </button>
            )}
            <span style={{ marginLeft: 'auto', fontSize: 'var(--text-xs)', color: 'var(--text-3)' }}>{sortedTeamAbs.length} / {teamAbsences.length}</span>
          </div>
          {teamAbsences.length === 0 ? (
            <EmptyState icon="👥" title={t('absences.empty_team_title')} />
          ) : sortedTeamAbs.length === 0 ? (
            <EmptyState icon="🔍" title={t('common.no_results', 'Sin resultados con los filtros aplicados')} />
          ) : (
            <div className="ds-card ds-card--plano">
              <div style={{ display: 'grid', gridTemplateColumns: '1.5fr 1fr 1fr 1fr 80px 100px', gap: 16, padding: '10px 20px', borderBottom: '1px solid var(--surface-4)', fontSize: "var(--text-xs)", fontWeight: 700, color: 'var(--text-2)', textTransform: 'uppercase', letterSpacing: '0.07em', alignItems: 'center' }}>
                <SortableTH col="user_name" sort={teamAbsSort} onSort={setTeamAbsSort}>{t('absences.person_col')}</SortableTH>
                <SortableTH col="type" sort={teamAbsSort} onSort={setTeamAbsSort}>{t('absences.type_label')}</SortableTH>
                <SortableTH col="start_date" sort={teamAbsSort} onSort={setTeamAbsSort}>{t('absences.start_label')}</SortableTH>
                <SortableTH col="end_date" sort={teamAbsSort} onSort={setTeamAbsSort}>{t('absences.end_label')}</SortableTH>
                <SortableTH col="working_days" sort={teamAbsSort} onSort={setTeamAbsSort}>{t('absences.days')}</SortableTH>
                <SortableTH col="status" sort={teamAbsSort} onSort={setTeamAbsSort}>{t('common.status')}</SortableTH>
              </div>
              {(sortedTeamAbs as Absence[]).map(a => (
                <div key={a.id} style={{ display: 'grid', gridTemplateColumns: '1.5fr 1fr 1fr 1fr 80px 100px', gap: 16, padding: '12px 20px', borderBottom: '1px solid color-mix(in srgb, var(--surface-4) 19%, transparent)', alignItems: 'center' }}>
                  <span className="u-base-600">{a.user_name}</span>
                  <span className="u-text2-sm">{typeLabels(t)[a.type || ""]?.replace(/^\S+\s/, '') || a.type}</span>
                  <span className="u-sm">{fmtDate(a.start_date)}</span>
                  <span className="u-sm">{fmtDate(a.end_date)}</span>
                  <span style={{ fontSize: "var(--text-sm)", fontFamily: 'var(--font-mono)' }}>{a.working_days}d</span>
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
    </PageShell>
  )
}