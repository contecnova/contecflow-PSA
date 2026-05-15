import { useState, useMemo } from 'react'
import { openConfirmGlobal } from '../context/ConfirmContext'
import { useToast } from '../context/ToastContext'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { imputationsApi, projectsApi, tasksApi, aiCopilotApi } from '../services/api'
import { queueImputation } from '../services/offlineQueue'
import { Button, Card } from '../components/ui'
import PageHeader from '../components/layout/PageHeader'
import PageShell from '../components/layout/PageShell'
import { Clock } from 'lucide-react'
import { useAuth } from '../context/AuthContext'
import { fmtDate, fmtNumber, extractErr} from '../utils/helpers'
import { GENERIC_ERROR_FALLBACK } from '../constants/errors'
import { NOTIFICATIONS_POLL_MS, STALE_5_MIN_MS } from '../constants/timings'
import { useAppT } from '../i18n/AppLangContext'

const HOUR_OPTIONS = [0.5, 1, 1.5, 2, 3, 4, 5, 6, 7, 8]

function WeekGrid({ weekData, anomaliesByDate, hasAnyAnomaly, onOpenDrawer, t }) {
  if (!weekData) return null
  const days = ['L', 'M', 'X', 'J', 'V']
  const byDay = weekData.by_day || []

  return (
    <Card style={{ marginTop: 20 }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 16 }}>
        <h3 style={{ fontSize: "var(--text-md)", fontWeight: 700, margin: 0 }}>{t('imputa_page.week_title')}</h3>
        {/* Item #48: badge global de anomalías detectadas en los últimos 30 días.
            Click → abre drawer con detalle de high_hours/gaps/closed_project. */}
        {hasAnyAnomaly && (
          <button
            onClick={onOpenDrawer}
            style={{
              background: 'var(--warning-glow, rgba(251,146,60,0.12))',
              border: '1px solid var(--warning)',
              color: 'var(--warning)',
              borderRadius: 8, padding: '4px 10px',
              fontSize: 'var(--text-sm)', fontWeight: 600, cursor: 'pointer',
              display: 'flex', alignItems: 'center', gap: 6,
            }}
            title="Ver anomalías detectadas en tus imputaciones"
          >
            ⚠ Anomalías detectadas
          </button>
        )}
      </div>
      <div style={{ display: 'flex', gap: 8, marginBottom: 14 }}>
        {days.map((d, i) => {
          // Compute the ISO date for this weekday from week_start to avoid index-based mapping bugs
          let dayIso = null
          if (weekData.week_start) {
            const base = new Date(weekData.week_start + 'T12:00:00')
            base.setDate(base.getDate() + i)
            dayIso = base.toISOString().split('T')[0]
          }
          const entry = dayIso ? byDay.find(e => e.date === dayIso) : byDay[i]
          const hasHours = entry && entry.hours > 0
          const dayAnomaly = dayIso ? anomaliesByDate?.[dayIso] : null
          return (
            <div key={d} style={{ flex: 1, textAlign: 'center', position: 'relative' }}>
              <div style={{ fontSize: "var(--text-xs)", color: 'var(--text-2)', marginBottom: 6 }}>{d}</div>
              <div
                onClick={dayAnomaly ? onOpenDrawer : undefined}
                style={{
                  background: dayAnomaly
                    ? 'var(--warning-glow, rgba(251,146,60,0.18))'
                    : hasHours ? 'var(--accent-glow)' : 'var(--surface-3)',
                  border: `1px solid ${dayAnomaly ? 'var(--warning)' : hasHours ? 'var(--accent)' : 'var(--surface-4)'}`,
                  borderRadius: 8, padding: '12px 4px',
                  fontFamily: 'var(--font-mono)', fontSize: "var(--text-base)", fontWeight: 700,
                  color: dayAnomaly ? 'var(--warning)' : hasHours ? 'var(--accent)' : 'var(--text-3)',
                  cursor: dayAnomaly ? 'pointer' : 'default',
                  position: 'relative',
                }}
                title={dayAnomaly ? dayAnomaly.message : undefined}
              >
                {hasHours ? `${fmtNumber(entry.hours, 2)}h` : '—'}
                {dayAnomaly && (
                  <span
                    style={{
                      position: 'absolute', top: -6, right: -6,
                      width: 18, height: 18, borderRadius: '50%',
                      background: 'var(--warning)', color: 'white',
                      fontSize: 11, fontWeight: 700,
                      display: 'flex', alignItems: 'center', justifyContent: 'center',
                      border: '1px solid var(--surface-0)',
                    }}
                  >!</span>
                )}
              </div>
            </div>
          )
        })}
      </div>
      <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: "var(--text-base)", color: 'var(--text-2)' }}>
        <span>{t('imputa_page.total')}: <span style={{ color: 'var(--text-1)', fontWeight: 700 }}>{fmtNumber(weekData.total_hours, 2)}h</span></span>
        <span>{t('imputa_page.capacity')}: <span style={{ color: 'var(--text-1)' }}>{weekData.capacity_hours}h</span></span>
        <span style={{ color: weekData.load_pct > 100 ? 'var(--danger)' : weekData.load_pct > 85 ? 'var(--warning)' : 'var(--success)', fontWeight: 700 }}>
          {weekData.load_pct?.toFixed(0)}{t('imputa_page.load_pct')}
        </span>
      </div>
    </Card>
  )
}


function AnomaliesDrawer({ open, onClose, anomaliesData }) {
  if (!open) return null
  const items = anomaliesData?.anomalies || []
  return (
    <div
      onClick={onClose}
      style={{
        position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.45)',
        zIndex: 1000, display: 'flex', justifyContent: 'flex-end',
      }}
    >
      <div
        onClick={e => e.stopPropagation()}
        style={{
          width: 420, maxWidth: '92vw', height: '100%',
          background: 'var(--surface-1)', borderLeft: '1px solid var(--surface-4)',
          padding: '20px 22px', overflowY: 'auto',
          display: 'flex', flexDirection: 'column', gap: 12,
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <h3 style={{ margin: 0, fontSize: 'var(--text-md)', fontWeight: 700 }}>
            ⚠ Anomalías en imputaciones
          </h3>
          <button onClick={onClose}
            style={{ background: 'transparent', border: 'none', color: 'var(--text-2)', fontSize: 20, cursor: 'pointer' }}>
            ✕
          </button>
        </div>
        <div style={{ fontSize: 'var(--text-sm)', color: 'var(--text-3)' }}>
          Periodo analizado: {anomaliesData?.period?.from} → {anomaliesData?.period?.to}
          {' · '}{anomaliesData?.total_entries} imputaciones
        </div>
        {items.length === 0 ? (
          <div style={{ padding: 20, textAlign: 'center', color: 'var(--text-3)' }}>
            Sin anomalías detectadas.
          </div>
        ) : items.map((a, idx) => (
          <div key={idx} style={{
            background: 'var(--surface-2)', border: '1px solid var(--surface-4)',
            borderRadius: 10, padding: 14,
          }}>
            <div style={{ fontWeight: 700, marginBottom: 6, color: 'var(--warning)' }}>
              {a.type === 'high_hours'
                ? `⏰ Día con muchas horas — ${a.date}`
                : a.type === 'gap'
                  ? `📉 Periodo sin imputaciones`
                  : `🗂 Proyectos cerrados`}
            </div>
            <div style={{ fontSize: 'var(--text-sm)', color: 'var(--text-1)', marginBottom: 6 }}>
              {a.message}
            </div>
            {a.suggestion && (
              <div style={{ fontSize: 'var(--text-sm)', color: 'var(--text-2)' }}>
                💡 {a.suggestion}
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  )
}

export default function ImputarPage(): JSX.Element {
  const t = useAppT()
  const { user } = useAuth()
  const qc = useQueryClient()
  const toast = useToast()
  const today = new Date().toISOString().split('T')[0]

  const [form, setForm] = useState({
    project_id: '',
    task_id: '',
    date: today,
    hours: 0,
    description: '',
    is_billable: false,
  })
  const [saved, setSaved] = useState(false)
  const [duplicateError, setDuplicateError] = useState(null)
  const [forceDuplicate, setForceDuplicate] = useState(false)

  const { data: projects = [] } = useQuery({
    queryKey: ['projects'],
    queryFn: () => projectsApi.list().then(r => r.data),
  })

  const { data: tasks = [] } = useQuery({
    queryKey: ['tasks-my', form.project_id],
    queryFn: () => tasksApi.list({ project_id: form.project_id, assignee_id: user?.id }).then(r => r.data?.items ?? r.data ?? []),
    enabled: !!form.project_id,
  })

  const { data: weekData } = useQuery({
    queryKey: ['my-week'],
    queryFn: () => imputationsApi.myWeek().then(r => r.data),
  })

  const { data: activeTimer } = useQuery({
    queryKey: ['timer-current'],
    queryFn: () => imputationsApi.timerCurrent().then(r => r.data).catch(() => null),
    refetchInterval: NOTIFICATIONS_POLL_MS,
  })

  const { data: todayImputations = [] } = useQuery({
    queryKey: ['imputations-today'],
    queryFn: () => imputationsApi.list({ date_from: today, date_to: today, user_id: user?.id }).then(r => r.data?.items ?? r.data ?? []),
  })

  // Item #48: anomalías de imputación del propio user (últimos 30 días).
  // Heurística + estadística (mean + 2σ con n≥7). Solo se invoca si hay user.
  const { data: anomaliesData } = useQuery({
    queryKey: ['ai-timesheet-anomalies', user?.id],
    queryFn: () =>
      user?.id
        ? aiCopilotApi.timesheetSuggestions(user.id)
            .then(r => r.data)
            .catch(() => ({ anomalies: [] }))
        : Promise.resolve({ anomalies: [] }),
    enabled: !!user?.id,
    staleTime: STALE_5_MIN_MS,  // 5 min — heurística suave, no refrescar agresivamente
  })

  // Map ISO date → high_hours anomaly para badge inline en WeekGrid.
  const anomaliesByDate = useMemo(() => {
    const out = {}
    for (const a of (anomaliesData?.anomalies || [])) {
      if (a?.type === 'high_hours' && a?.date) out[a.date] = a
    }
    return out
  }, [anomaliesData])

  const hasAnyAnomaly = (anomaliesData?.anomalies?.length || 0) > 0

  const [anomaliesDrawerOpen, setAnomaliesDrawerOpen] = useState(false)

  const { mutate, isPending } = useMutation({
    mutationFn: (data) => imputationsApi.create(data),
    onSuccess: () => {
      setSaved(true)
      setDuplicateError(null)
      setForceDuplicate(false)
      setTimeout(() => setSaved(false), 2500)
      setForm(f => ({ ...f, task_id: '', hours: 0, description: '' }))
      qc.invalidateQueries(['my-week'])
      qc.invalidateQueries(['imputations-today'])
      qc.invalidateQueries(['dash-hours-week'])
      qc.invalidateQueries(['timesheets-mine'])
      qc.invalidateQueries(['timesheets-pending'])
      qc.invalidateQueries(['timesheets-team'])
    },
    onError: e => {
      if (e?.response?.status === 409) {
        setDuplicateError(e?.response?.data?.detail || 'Ya existe una imputación para esta tarea en esa fecha.')
      } else {
        toast.error(extractErr(e, t('common.error') || GENERIC_ERROR_FALLBACK))
      }
    },
  })

  // Offline-aware submit: if offline, queue to IndexedDB instead
  const handleSubmit = async () => {
    if (!canSubmit) return
    if (!navigator.onLine) {
      try {
        await queueImputation(form)
        setSaved(true)
        setTimeout(() => setSaved(false), 2500)
        setForm(f => ({ ...f, task_id: '', hours: 0, description: '' }))
        toast.success('Sin conexi\u00f3n — la imputaci\u00f3n se sincronizar\u00e1 autom\u00e1ticamente')
      } catch {
        toast.error(t('imputa_page.offline_error'))
      }
      return
    }
    mutate({ ...form, force_duplicate: forceDuplicate })
  }

  const [editingId, setEditingId] = useState(null)
  const [editForm, setEditForm] = useState({ hours: 0, description: '', is_billable: false })

  const { mutate: updateImp, isPending: updating } = useMutation({
    mutationFn: ({ id, data }) => imputationsApi.update(id, data),
    onSuccess: () => {
      setEditingId(null)
      qc.invalidateQueries(['my-week'])
      qc.invalidateQueries(['imputations-today'])
      qc.invalidateQueries(['dash-hours-week'])
      qc.invalidateQueries(['timesheets-mine'])
      qc.invalidateQueries(['timesheets-pending'])
      qc.invalidateQueries(['timesheets-team'])
      toast.success(t('imputa_page.updated_ok'))
    },
    onError: e => toast.error(extractErr(e, t('common.error') || GENERIC_ERROR_FALLBACK)),  
  })

  const { mutate: deleteImp } = useMutation({
    mutationFn: (id) => imputationsApi.delete(id),
    onSuccess: () => {
      qc.invalidateQueries(['my-week'])
      qc.invalidateQueries(['imputations-today'])
      qc.invalidateQueries(['dash-hours-week'])
      qc.invalidateQueries(['timesheets-mine'])
      qc.invalidateQueries(['timesheets-pending'])
      qc.invalidateQueries(['timesheets-team'])
      toast.success(t('imputa_page.deleted_ok'))
    },
    onError: e => toast.error(extractErr(e, t('common.error') || GENERIC_ERROR_FALLBACK)),  
  })

  const set = (k) => (v) => {
    setForm(f => ({ ...f, [k]: v }))
    if (k === 'task_id' || k === 'date') {
      setDuplicateError(null)
      setForceDuplicate(false)
    }
  }
  const todayHours = todayImputations.reduce((s, i) => s + i.hours, 0)
  const canSubmit = form.project_id && form.hours > 0 && form.date

  return (
    <PageShell style={{ maxWidth: 680, margin: '0 auto' }}>
      <PageHeader
        icon={<Clock size={18} />}
        title={t('imputa_page.title')}
        subtitle={t('imputa_page.subtitle', { date: fmtDate(today), hours: todayHours.toFixed(1) })}
      showListExport={false}
      />

      {activeTimer && (
        <div style={{
          background: 'var(--accent-glow)',
          border: '1px solid var(--accent)',
          borderRadius: 10,
          padding: '10px 16px',
          marginBottom: 16,
          display: 'flex',
          alignItems: 'center',
          gap: 10,
          fontSize: "var(--text-base)",
          color: 'var(--accent)',
          fontWeight: 600,
        }}>
          <span style={{ fontSize: "var(--text-lg-em)" }}>⏱</span>
          {t('imputa_page.timer_running')}
          {activeTimer.total_elapsed_seconds != null && (
            <span style={{ fontFamily: 'var(--font-mono)', marginLeft: 4 }}>
              · {Math.floor(activeTimer.total_elapsed_seconds / 3600)}h {Math.floor((activeTimer.total_elapsed_seconds % 3600) / 60)}m
            </span>
          )}
          <a href="/timer" style={{ marginLeft: 'auto', color: 'var(--accent)', fontSize: "var(--text-sm)", textDecoration: 'underline' }}>
            {t('imputa_page.timer_link')}
          </a>
        </div>
      )}

      <Card>
        {/* Project */}
        <div style={{ marginBottom: 20 }}>
          <label style={{ fontSize: "var(--text-sm)", fontWeight: 700, color: 'var(--text-2)', textTransform: 'uppercase', letterSpacing: '0.07em', display: 'block', marginBottom: 8 }}>
            {t('imputa_page.project_label')} <span style={{ color: 'var(--danger)' }}>*</span>
          </label>
          <select
            value={form.project_id}
            onChange={e => set('project_id')(e.target.value)}
            style={{ width: '100%', background: 'var(--surface-3)', border: '1px solid var(--surface-4)', borderRadius: 'var(--radius-md)', padding: 'var(--space-4) var(--space-4)', color: form.project_id ? 'var(--text-1)' : 'var(--text-2)', fontSize: '14px', outline: 'none', fontFamily: 'var(--font-sans)', cursor: 'pointer' }}
          >
            <option value="">{t('imputa_page.project_placeholder')}</option>
            {projects.map(p => (
              <option key={p.id} value={p.id}>{p.code} — {p.name}</option>
            ))}
          </select>
        </div>

        {/* Task */}
        <div style={{ marginBottom: 20 }}>
          <label style={{ fontSize: "var(--text-sm)", fontWeight: 700, color: 'var(--text-2)', textTransform: 'uppercase', letterSpacing: '0.07em', display: 'block', marginBottom: 8 }}>
            {t('imputa_page.task_label')}
          </label>
          <select
            value={form.task_id}
            onChange={e => set('task_id')(e.target.value)}
            disabled={!form.project_id}
            style={{ width: '100%', background: 'var(--surface-3)', border: '1px solid var(--surface-4)', borderRadius: 'var(--radius-md)', padding: 'var(--space-4) var(--space-4)', color: 'var(--text-1)', fontSize: '14px', outline: 'none', fontFamily: 'var(--font-sans)', cursor: form.project_id ? 'pointer' : 'not-allowed', opacity: form.project_id ? 1 : 0.5 }}
          >
            <option value="">{t('imputa_page.task_none')}</option>
            {tasks.map(t => (
              <option key={t.id} value={t.id}>{t.code} — {t.title}</option>
            ))}
          </select>
        </div>

        {/* Date */}
        <div style={{ marginBottom: 20 }}>
          <label style={{ fontSize: "var(--text-sm)", fontWeight: 700, color: 'var(--text-2)', textTransform: 'uppercase', letterSpacing: '0.07em', display: 'block', marginBottom: 8 }}>
            {t('imputa_page.date_label')} <span style={{ color: 'var(--danger)' }}>*</span>
          </label>
          <input
            type="date"
            value={form.date}
            onChange={e => set('date')(e.target.value)}
            max={today}
            style={{ background: 'var(--surface-3)', border: '1px solid var(--surface-4)', borderRadius: 'var(--radius-md)', padding: 'var(--space-4) var(--space-4)', color: 'var(--text-1)', fontSize: '14px', outline: 'none', fontFamily: 'var(--font-sans)', width: '100%', boxSizing: 'border-box' }}
          />
        </div>

        {/* Hours */}
        <div style={{ marginBottom: 20 }}>
          <label style={{ fontSize: "var(--text-sm)", fontWeight: 700, color: 'var(--text-2)', textTransform: 'uppercase', letterSpacing: '0.07em', display: 'block', marginBottom: 8 }}>
            {t('imputa_page.hours_label')} <span style={{ color: 'var(--danger)' }}>*</span>
          </label>
          <div style={{ display: 'flex', gap: 'var(--space-2)', flexWrap: 'wrap' }}>
            {HOUR_OPTIONS.map(h => (
              <button
                key={h}
                onClick={() => set('hours')(h)}
                style={{
                  flex: '1 0 60px', padding: 'var(--space-4) var(--space-2)', borderRadius: 'var(--radius-md)', textAlign: 'center',
                  border: `1px solid ${form.hours === h ? 'var(--accent)' : 'var(--surface-4)'}`,
                  background: form.hours === h ? 'var(--accent-glow)' : 'var(--surface-3)',
                  color: form.hours === h ? 'var(--accent)' : 'var(--text-2)',
                  fontWeight: 700, fontSize: '13px', cursor: 'pointer', fontFamily: 'var(--font-sans)', transition: 'all 0.15s',
                }}
              >
                {h}h
              </button>
            ))}
          </div>
          {form.hours > 0 && (
            <div style={{ marginTop: 'var(--space-2)', fontSize: '12px', color: 'var(--text-2)', textAlign: 'right' }}>
              {t('imputa_page.total_today')}: <span style={{ color: todayHours + form.hours > 8 ? 'var(--warning)' : 'var(--text-1)', fontWeight: 700 }}>
                {(todayHours + form.hours).toFixed(1)}h
              </span> / 8h
            </div>
          )}
        </div>

        {/* Description */}
        <div style={{ marginBottom: 20 }}>
          <label style={{ fontSize: '12px', fontWeight: 700, color: 'var(--text-2)', textTransform: 'uppercase', letterSpacing: '0.07em', display: 'block', marginBottom: 'var(--space-2)' }}>
            {t('imputa_page.description_label')}
          </label>
          <textarea
            value={form.description}
            onChange={e => set('description')(e.target.value)}
            placeholder={t('imputa_page.description_placeholder')}
            rows={3}
            style={{ width: '100%', background: 'var(--surface-3)', border: '1px solid var(--surface-4)', borderRadius: 'var(--radius-md)', padding: 'var(--space-4) var(--space-4)', color: 'var(--text-1)', fontSize: '14px', outline: 'none', fontFamily: 'var(--font-sans)', resize: 'vertical', boxSizing: 'border-box' }}
          />
        </div>

        {/* Billable toggle */}
        <div style={{ marginBottom: 'var(--space-6)' }}>
          <label style={{ display: 'flex', alignItems: 'center', gap: 10, cursor: 'pointer', userSelect: 'none' }}>
            <input
              type="checkbox"
              checked={form.is_billable}
              onChange={e => set('is_billable')(e.target.checked)}
              style={{ position: 'absolute', opacity: 0, width: 0, height: 0 }}
            />
            <div aria-hidden="true" style={{
              width: 42, height: 24, borderRadius: 12, flexShrink: 0,
              background: form.is_billable ? 'var(--accent)' : 'var(--surface-4)',
              position: 'relative', transition: 'background 0.2s',
            }}>
              <div style={{
                position: 'absolute', top: 3, left: form.is_billable ? 21 : 3,
                width: 18, height: 18, borderRadius: '50%',
                background: 'var(--surface-0)', transition: 'left 0.2s',
              }} />
            </div>
            <span style={{ fontSize: '14px', fontWeight: 600, color: form.is_billable ? 'var(--accent)' : 'var(--text-2)' }}>
              {t('imputa_page.billable_label')}
            </span>
            {form.is_billable && (
              <span style={{ fontSize: '11px', background: 'var(--accent-glow)', color: 'var(--accent)', borderRadius: 6, padding: '2px 8px', fontWeight: 700 }}>
                {t('imputa_page.billable_badge')}
              </span>
            )}
          </label>
        </div>

        {/* Duplicate error panel */}
        {duplicateError && (
          <div style={{
            background: 'color-mix(in srgb, var(--warning) 12%, transparent)',
            border: '1px solid var(--warning)',
            borderRadius: 10,
            padding: '12px 16px',
            marginBottom: 16,
          }}>
            <div style={{ fontSize: '13px', color: 'var(--warning)', fontWeight: 700, marginBottom: 8 }}>
              ⚠️ {duplicateError}
            </div>
            <label style={{ display: 'flex', alignItems: 'flex-start', gap: 10, cursor: 'pointer', fontSize: '13px', color: 'var(--text-2)', lineHeight: 1.5 }}>
              <input
                type="checkbox"
                checked={forceDuplicate}
                onChange={e => setForceDuplicate(e.target.checked)}
                style={{ width: 16, height: 16, accentColor: 'var(--warning)', cursor: 'pointer', marginTop: 2, flexShrink: 0 }}
              />
              <span>Permitir imputación duplicada y avisar al manager para revisión.</span>
            </label>
          </div>
        )}

        <button
          onClick={handleSubmit}
          disabled={!canSubmit || isPending || (!!duplicateError && !forceDuplicate)}
          style={{
            width: '100%', padding: '14px', borderRadius: 10, border: 'none',
            background: saved ? 'var(--success)' : (canSubmit && (!duplicateError || forceDuplicate)) ? 'var(--accent)' : 'var(--surface-4)',
            color: (canSubmit && (!duplicateError || forceDuplicate)) ? 'var(--surface-0)' : 'var(--text-2)',
            fontWeight: 800, fontSize: "var(--text-md-em)", cursor: (canSubmit && (!duplicateError || forceDuplicate)) ? 'pointer' : 'not-allowed',
            fontFamily: 'inherit', transition: 'all 0.3s',
          }}
        >
          {saved ? t('imputa_page.saved') : isPending ? t('imputa_page.saving') : navigator.onLine ? t('imputa_page.submit') : t('imputa_page.submit_offline')}
        </button>
      </Card>

      {/* Today's imputations */}
      {todayImputations.length > 0 && (
        <Card style={{ marginTop: 20 }}>
          <h3 style={{ fontSize: "var(--text-md)", fontWeight: 700, marginBottom: 12 }}>{t('imputa_page.today_entries')}</h3>
          {todayImputations.map(imp => (
            <div key={imp.id} style={{ background: 'var(--surface-3)', borderRadius: 8, marginBottom: 6 }}>
              {editingId === imp.id ? (
                /* Modo edición inline */
                <div style={{ padding: '10px 12px', display: 'flex', gap: 8, alignItems: 'flex-end', flexWrap: 'wrap' }}>
                  <div style={{ flex: '0 0 80px' }}>
                    <label style={{ fontSize: "var(--text-2xs)", color: 'var(--text-3)', display: 'block', marginBottom: 3 }}>{t('imputa_page.hours_edit').toUpperCase()}</label>
                    <input
                      type="number" step="0.25" min="0.25" max="24"
                      value={editForm.hours}
                      onChange={e => setEditForm(f => ({ ...f, hours: parseFloat(e.target.value) || 0 }))}
                      style={{ width: '100%', background: 'var(--surface-2)', border: '1px solid var(--accent)', borderRadius: 6,
                        padding: '6px 8px', color: 'var(--text-1)', fontSize: "var(--text-base)", outline: 'none', fontFamily: 'inherit' }}
                    />
                  </div>
                  <div style={{ flex: 1, minWidth: 120 }}>
                    <label style={{ fontSize: "var(--text-2xs)", color: 'var(--text-3)', display: 'block', marginBottom: 3 }}>{t('imputa_page.description_edit').toUpperCase()}</label>
                    <input
                      value={editForm.description}
                      onChange={e => setEditForm(f => ({ ...f, description: e.target.value }))}
                      style={{ width: '100%', background: 'var(--surface-2)', border: '1px solid var(--accent)', borderRadius: 6,
                        padding: '6px 8px', color: 'var(--text-1)', fontSize: "var(--text-base)", outline: 'none', fontFamily: 'inherit', boxSizing: 'border-box' }}
                    />
                  </div>
                  <div style={{ alignSelf: 'flex-end', paddingBottom: 4 }}>
                    <label style={{ display: 'flex', alignItems: 'center', gap: 6, cursor: 'pointer', fontSize: "var(--text-xs)", color: editForm.is_billable ? 'var(--accent)' : 'var(--text-3)', userSelect: 'none' }}>
                      <input
                        type="checkbox"
                        checked={editForm.is_billable}
                        onChange={e => setEditForm(f => ({ ...f, is_billable: e.target.checked }))}
                        style={{ accentColor: 'var(--accent)', width: 14, height: 14, cursor: 'pointer' }}
                      />
                      {t('imputa_page.billable_label')}
                    </label>
                  </div>
                  <div style={{ display: 'flex', gap: 6 }}>
                    <Button
                      onClick={() => updateImp({ id: imp.id, data: { hours: editForm.hours, description: editForm.description, is_billable: editForm.is_billable } })}
                      disabled={updating || editForm.hours <= 0}
                      loading={updating}
                    >{t('common.save')}</Button>
                    <Button variant="secondary" onClick={() => setEditingId(null)}>{t('common.cancel')}</Button>
                  </div>
                </div>
              ) : (
                /* Vista normal con botones de editar/borrar */
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '10px 12px', fontSize: "var(--text-base)" }}>
                  <div>
                    <span style={{ fontWeight: 600 }}>{imp.project?.name || '—'}</span>
                    {imp.task?.title && <span style={{ color: 'var(--text-3)', marginLeft: 6, fontSize: "var(--text-xs)" }}>· {imp.task.title}</span>}
                    {imp.description && <span style={{ color: 'var(--text-2)', marginLeft: 8 }}>· {imp.description}</span>}
                    {imp.is_billable && (
                      <span style={{ marginLeft: 8, fontSize: '11px', background: 'var(--accent-glow)', color: 'var(--accent)', borderRadius: 4, padding: '1px 6px', fontWeight: 700 }}>
                        {t('imputa_page.billable_badge')}
                      </span>
                    )}
                  </div>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                    <span style={{ fontFamily: 'var(--font-mono)', color: 'var(--accent)', fontWeight: 700 }}>{imp.hours}h</span>
                    <button
                      onClick={() => { setEditingId(imp.id); setEditForm({ hours: imp.hours, description: imp.description || '', is_billable: imp.is_billable ?? false }) }}
                      style={{ background: 'none', border: 'none', color: 'var(--text-2)', cursor: 'pointer', fontSize: "var(--text-md)", padding: '2px 4px' }}
                      aria-label={t('imputa_page.edit_aria')}
                      title={t('imputa_page.edit_aria')}>✏</button>
                    <button
                      onClick={() => { openConfirmGlobal({ message: t('imputa_page.confirm_delete'), onConfirm: () => deleteImp(imp.id), danger: true }) }}
                      style={{ background: 'none', border: 'none', color: 'var(--danger)', cursor: 'pointer', fontSize: "var(--text-md)", padding: '2px 4px' }}
                      aria-label={t('imputa_page.delete_aria')}
                      title={t('imputa_page.delete_aria')}>✕</button>
                  </div>
                </div>
              )}
            </div>
          ))}
          <div style={{ borderTop: '1px solid var(--surface-4)', marginTop: 10, paddingTop: 10, display: 'flex', justifyContent: 'flex-end', fontSize: "var(--text-md)", fontWeight: 700 }}>
            {t('imputa_page.total')}: <span style={{ fontFamily: 'var(--font-mono)', color: 'var(--accent)', marginLeft: 8 }}>{todayHours.toFixed(1)}h</span>
          </div>
        </Card>
      )}

      <WeekGrid
        weekData={weekData}
        anomaliesByDate={anomaliesByDate}
        hasAnyAnomaly={hasAnyAnomaly}
        onOpenDrawer={() => setAnomaliesDrawerOpen(true)}
        t={t}
      />
      <AnomaliesDrawer
        open={anomaliesDrawerOpen}
        onClose={() => setAnomaliesDrawerOpen(false)}
        anomaliesData={anomaliesData}
      />
    </PageShell>
  )
}
