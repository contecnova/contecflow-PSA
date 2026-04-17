import { useState } from 'react'
import { openConfirmGlobal } from '../context/ConfirmContext'
import { useToast } from '../context/ToastContext'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { imputationsApi, projectsApi, tasksApi } from '../services/api'
import { queueImputation } from '../services/offlineQueue'
import { Button, Card } from '../components/ui'
import PageHeader from '../components/layout/PageHeader'
import { useAuth } from '../context/AuthContext'
import { fmtDate, extractErr} from '../utils/helpers'
import { useAppT } from '../i18n/AppLangContext'

const HOUR_OPTIONS = [0.5, 1, 1.5, 2, 3, 4, 5, 6, 7, 8]

function WeekGrid({ weekData, t }) {
  if (!weekData) return null
  const days = ['L', 'M', 'X', 'J', 'V']
  const byDay = weekData.by_day || []

  return (
    <Card style={{ marginTop: 20 }}>
      <h3 style={{ fontSize: 14, fontWeight: 700, marginBottom: 16 }}>{t('imputa_page.week_title')}</h3>
      <div style={{ display: 'flex', gap: 8, marginBottom: 14 }}>
        {days.map((d, i) => {
          const entry = byDay[i]
          const hasHours = entry && entry.hours > 0
          return (
            <div key={d} style={{ flex: 1, textAlign: 'center' }}>
              <div style={{ fontSize: 11, color: 'var(--text-2)', marginBottom: 6 }}>{d}</div>
              <div style={{
                background: hasHours ? 'var(--accent-glow)' : 'var(--surface-3)',
                border: `1px solid ${hasHours ? 'var(--accent-glow)' : 'var(--surface-4)'}`,
                borderRadius: 8, padding: '12px 4px',
                fontFamily: "'Space Mono', monospace", fontSize: 13, fontWeight: 700,
                color: hasHours ? 'var(--accent)' : 'var(--text-3)',
              }}>
                {hasHours ? `${entry.hours}h` : '—'}
              </div>
            </div>
          )
        })}
      </div>
      <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 13, color: 'var(--text-2)' }}>
        <span>{t('imputa_page.total')}: <span style={{ color: 'var(--text-1)', fontWeight: 700 }}>{weekData.total_hours?.toFixed(1)}h</span></span>
        <span>{t('imputa_page.capacity')}: <span style={{ color: 'var(--text-1)' }}>{weekData.capacity_hours}h</span></span>
        <span style={{ color: weekData.load_pct > 100 ? 'var(--danger)' : weekData.load_pct > 85 ? 'var(--warning)' : 'var(--success)', fontWeight: 700 }}>
          {weekData.load_pct?.toFixed(0)}{t('imputa_page.load_pct')}
        </span>
      </div>
    </Card>
  )
}

export default function ImputarPage() {
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

  const { data: projects = [] } = useQuery({
    queryKey: ['projects'],
    queryFn: () => projectsApi.list().then(r => r.data),
  })

  const { data: tasks = [] } = useQuery({
    queryKey: ['tasks-my', form.project_id],
    queryFn: () => tasksApi.list({ project_id: form.project_id, assignee_id: user?.id }).then(r => r.data),
    enabled: !!form.project_id,
  })

  const { data: weekData } = useQuery({
    queryKey: ['my-week'],
    queryFn: () => imputationsApi.myWeek().then(r => r.data),
  })

  const { data: activeTimer } = useQuery({
    queryKey: ['timer-current'],
    queryFn: () => imputationsApi.timerCurrent().then(r => r.data).catch(() => null),
    refetchInterval: 30000,
  })

  const { data: todayImputations = [] } = useQuery({
    queryKey: ['imputations-today'],
    queryFn: () => imputationsApi.list({ date_from: today, date_to: today, user_id: user?.id }).then(r => r.data),
  })

  const { mutate, isPending } = useMutation({
    mutationFn: (data) => imputationsApi.create(data),
    onSuccess: () => {
      setSaved(true)
      setTimeout(() => setSaved(false), 2500)
      setForm(f => ({ ...f, task_id: '', hours: 0, description: '' }))
      qc.invalidateQueries(['my-week'])
      qc.invalidateQueries(['imputations-today'])
      qc.invalidateQueries(['dash-hours-week'])
    },
    onError: e => toast.error(extractErr(e, t('common.error') || 'Error')),
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
    mutate(form)
  }

  const [editingId, setEditingId] = useState(null)
  const [editForm, setEditForm] = useState({ hours: 0, description: '' })

  const { mutate: updateImp, isPending: updating } = useMutation({
    mutationFn: ({ id, data }) => imputationsApi.update(id, data),
    onSuccess: () => {
      setEditingId(null)
      qc.invalidateQueries(['my-week'])
      qc.invalidateQueries(['imputations-today'])
      qc.invalidateQueries(['dash-hours-week'])
      toast.success(t('imputa_page.updated_ok'))
    },
    onError: e => toast.error(extractErr(e, t('common.error') || 'Error')),  
  })

  const { mutate: deleteImp } = useMutation({
    mutationFn: (id) => imputationsApi.delete(id),
    onSuccess: () => {
      qc.invalidateQueries(['my-week'])
      qc.invalidateQueries(['imputations-today'])
      qc.invalidateQueries(['dash-hours-week'])
      toast.success(t('imputa_page.deleted_ok'))
    },
    onError: e => toast.error(extractErr(e, t('common.error') || 'Error')),  
  })

  const set = (k) => (v) => setForm(f => ({ ...f, [k]: v }))
  const todayHours = todayImputations.reduce((s, i) => s + i.hours, 0)
  const canSubmit = form.project_id && form.hours > 0 && form.date

  return (
    <div style={{ padding: 32, maxWidth: 680, margin: '0 auto' }}>
      <PageHeader
        title={t('imputa_page.title')}
        subtitle={`${fmtDate(today)} · ${t('imputa_page.total_today')}: ${todayHours.toFixed(1)}h`}
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
          fontSize: 13,
          color: 'var(--accent)',
          fontWeight: 600,
        }}>
          <span style={{ fontSize: 18 }}>⏱</span>
          {t('imputa_page.timer_running')}
          {activeTimer.total_elapsed_seconds != null && (
            <span style={{ fontFamily: "'Space Mono', monospace", marginLeft: 4 }}>
              · {Math.floor(activeTimer.total_elapsed_seconds / 3600)}h {Math.floor((activeTimer.total_elapsed_seconds % 3600) / 60)}m
            </span>
          )}
          <a href="/timer" style={{ marginLeft: 'auto', color: 'var(--accent)', fontSize: 12, textDecoration: 'underline' }}>
            {t('imputa_page.timer_link')}
          </a>
        </div>
      )}

      <Card>
        {/* Project */}
        <div style={{ marginBottom: 20 }}>
          <label style={{ fontSize: 12, fontWeight: 700, color: 'var(--text-2)', textTransform: 'uppercase', letterSpacing: '0.07em', display: 'block', marginBottom: 8 }}>
            {t('imputa_page.project_label')} <span style={{ color: 'var(--danger)' }}>*</span>
          </label>
          <select
            value={form.project_id}
            onChange={e => set('project_id')(e.target.value)}
            style={{ width: '100%', background: 'var(--surface-3)', border: '1px solid #1e2d45', borderRadius: 8, padding: '11px 14px', color: form.project_id ? 'var(--text-1)' : 'var(--text-2)', fontSize: 14, outline: 'none', fontFamily: 'inherit', cursor: 'pointer' }}
          >
            <option value="">{t('imputa_page.project_placeholder')}</option>
            {projects.map(p => (
              <option key={p.id} value={p.id}>{p.code} — {p.name}</option>
            ))}
          </select>
        </div>

        {/* Task */}
        <div style={{ marginBottom: 20 }}>
          <label style={{ fontSize: 12, fontWeight: 700, color: 'var(--text-2)', textTransform: 'uppercase', letterSpacing: '0.07em', display: 'block', marginBottom: 8 }}>
            {t('imputa_page.task_label')}
          </label>
          <select
            value={form.task_id}
            onChange={e => set('task_id')(e.target.value)}
            disabled={!form.project_id}
            style={{ width: '100%', background: 'var(--surface-3)', border: '1px solid #1e2d45', borderRadius: 8, padding: '11px 14px', color: 'var(--text-1)', fontSize: 14, outline: 'none', fontFamily: 'inherit', cursor: form.project_id ? 'pointer' : 'not-allowed', opacity: form.project_id ? 1 : 0.5 }}
          >
            <option value="">{t('imputa_page.task_none')}</option>
            {tasks.map(t => (
              <option key={t.id} value={t.id}>{t.code} — {t.title}</option>
            ))}
          </select>
        </div>

        {/* Date */}
        <div style={{ marginBottom: 20 }}>
          <label style={{ fontSize: 12, fontWeight: 700, color: 'var(--text-2)', textTransform: 'uppercase', letterSpacing: '0.07em', display: 'block', marginBottom: 8 }}>
            {t('imputa_page.date_label')} <span style={{ color: 'var(--danger)' }}>*</span>
          </label>
          <input
            type="date"
            value={form.date}
            onChange={e => set('date')(e.target.value)}
            max={today}
            style={{ background: 'var(--surface-3)', border: '1px solid #1e2d45', borderRadius: 8, padding: '11px 14px', color: 'var(--text-1)', fontSize: 14, outline: 'none', fontFamily: 'inherit', width: '100%', boxSizing: 'border-box' }}
          />
        </div>

        {/* Hours */}
        <div style={{ marginBottom: 20 }}>
          <label style={{ fontSize: 12, fontWeight: 700, color: 'var(--text-2)', textTransform: 'uppercase', letterSpacing: '0.07em', display: 'block', marginBottom: 8 }}>
            {t('imputa_page.hours_label')} <span style={{ color: 'var(--danger)' }}>*</span>
          </label>
          <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
            {HOUR_OPTIONS.map(h => (
              <button
                key={h}
                onClick={() => set('hours')(h)}
                style={{
                  flex: '1 0 60px', padding: '11px 6px', borderRadius: 8, textAlign: 'center',
                  border: `1px solid ${form.hours === h ? 'var(--accent-glow)' : 'var(--surface-4)'}`,
                  background: form.hours === h ? 'var(--accent-glow)' : 'var(--surface-3)',
                  color: form.hours === h ? 'var(--accent)' : 'var(--text-2)',
                  fontWeight: 700, fontSize: 13, cursor: 'pointer', fontFamily: 'inherit', transition: 'all 0.15s',
                }}
              >
                {h}h
              </button>
            ))}
          </div>
          {form.hours > 0 && (
            <div style={{ marginTop: 8, fontSize: 12, color: 'var(--text-2)', textAlign: 'right' }}>
              {t('imputa_page.total_today')}: <span style={{ color: todayHours + form.hours > 8 ? 'var(--warning)' : 'var(--text-1)', fontWeight: 700 }}>
                {(todayHours + form.hours).toFixed(1)}h
              </span> / 8h
            </div>
          )}
        </div>

        {/* Description */}
        <div style={{ marginBottom: 24 }}>
          <label style={{ fontSize: 12, fontWeight: 700, color: 'var(--text-2)', textTransform: 'uppercase', letterSpacing: '0.07em', display: 'block', marginBottom: 8 }}>
            {t('imputa_page.description_label')}
          </label>
          <textarea
            value={form.description}
            onChange={e => set('description')(e.target.value)}
            placeholder={t('imputa_page.description_placeholder')}
            rows={3}
            style={{ width: '100%', background: 'var(--surface-3)', border: '1px solid #1e2d45', borderRadius: 8, padding: '11px 14px', color: 'var(--text-1)', fontSize: 14, outline: 'none', fontFamily: 'inherit', resize: 'vertical', boxSizing: 'border-box' }}
          />
        </div>

        <button
          onClick={handleSubmit}
          disabled={!canSubmit || isPending}
          style={{
            width: '100%', padding: '14px', borderRadius: 10, border: 'none',
            background: saved ? 'var(--success)' : canSubmit ? 'var(--accent)' : 'var(--surface-4)',
            color: canSubmit ? 'var(--surface-0)' : 'var(--text-2)',
            fontWeight: 800, fontSize: 15, cursor: canSubmit ? 'pointer' : 'not-allowed',
            fontFamily: 'inherit', transition: 'all 0.3s',
          }} loading={isPending}
        >
          {saved ? t('imputa_page.saved') : isPending ? t('imputa_page.saving') : navigator.onLine ? t('imputa_page.submit') : t('imputa_page.submit_offline')}
        </button>
      </Card>

      {/* Today's imputations */}
      {todayImputations.length > 0 && (
        <Card style={{ marginTop: 20 }}>
          <h3 style={{ fontSize: 14, fontWeight: 700, marginBottom: 12 }}>{t('imputa_page.today_entries')}</h3>
          {todayImputations.map(imp => (
            <div key={imp.id} style={{ background: 'var(--surface-3)', borderRadius: 8, marginBottom: 6 }}>
              {editingId === imp.id ? (
                /* Modo edición inline */
                <div style={{ padding: '10px 12px', display: 'flex', gap: 8, alignItems: 'flex-end', flexWrap: 'wrap' }}>
                  <div style={{ flex: '0 0 80px' }}>
                    <label style={{ fontSize: 10, color: 'var(--text-3)', display: 'block', marginBottom: 3 }}>{t('imputa_page.hours_edit').toUpperCase()}</label>
                    <input
                      type="number" step="0.25" min="0.25" max="24"
                      value={editForm.hours}
                      onChange={e => setEditForm(f => ({ ...f, hours: parseFloat(e.target.value) || 0 }))}
                      style={{ width: '100%', background: 'var(--surface-2)', border: '1px solid var(--accent)', borderRadius: 6,
                        padding: '6px 8px', color: 'var(--text-1)', fontSize: 13, outline: 'none', fontFamily: 'inherit' }}
                    />
                  </div>
                  <div style={{ flex: 1, minWidth: 120 }}>
                    <label style={{ fontSize: 10, color: 'var(--text-3)', display: 'block', marginBottom: 3 }}>{t('imputa_page.description_edit').toUpperCase()}</label>
                    <input
                      value={editForm.description}
                      onChange={e => setEditForm(f => ({ ...f, description: e.target.value }))}
                      style={{ width: '100%', background: 'var(--surface-2)', border: '1px solid var(--accent)', borderRadius: 6,
                        padding: '6px 8px', color: 'var(--text-1)', fontSize: 13, outline: 'none', fontFamily: 'inherit', boxSizing: 'border-box' }}
                    />
                  </div>
                  <div style={{ display: 'flex', gap: 6 }}>
                    <Button
                      onClick={() => updateImp({ id: imp.id, data: { hours: editForm.hours, description: editForm.description } })}
                      disabled={updating || editForm.hours <= 0}
                      loading={updating}
                    >{t('common.save')}</Button>
                    <Button variant="secondary" onClick={() => setEditingId(null)}>{t('common.cancel')}</Button>
                  </div>
                </div>
              ) : (
                /* Vista normal con botones de editar/borrar */
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '10px 12px', fontSize: 13 }}>
                  <div>
                    <span style={{ fontWeight: 600 }}>{imp.project?.name || '—'}</span>
                    {imp.task?.title && <span style={{ color: 'var(--text-3)', marginLeft: 6, fontSize: 11 }}>· {imp.task.title}</span>}
                    {imp.description && <span style={{ color: 'var(--text-2)', marginLeft: 8 }}>· {imp.description}</span>}
                  </div>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                    <span style={{ fontFamily: "'Space Mono', monospace", color: 'var(--accent)', fontWeight: 700 }}>{imp.hours}h</span>
                    <button
                      onClick={() => { setEditingId(imp.id); setEditForm({ hours: imp.hours, description: imp.description || '' }) }}
                      style={{ background: 'none', border: 'none', color: 'var(--text-2)', cursor: 'pointer', fontSize: 14, padding: '2px 4px' }}
                      aria-label={t('imputa_page.edit_aria')}
                      title={t('imputa_page.edit_aria')}>✏</button>
                    <button
                      onClick={() => { openConfirmGlobal({ message: t('imputa_page.confirm_delete'), onConfirm: () => deleteImp(imp.id), danger: true }) }}
                      style={{ background: 'none', border: 'none', color: 'var(--danger)', cursor: 'pointer', fontSize: 14, padding: '2px 4px' }}
                      aria-label={t('imputa_page.delete_aria')}
                      title={t('imputa_page.delete_aria')}>✕</button>
                  </div>
                </div>
              )}
            </div>
          ))}
          <div style={{ borderTop: '1px solid #1e2d45', marginTop: 10, paddingTop: 10, display: 'flex', justifyContent: 'flex-end', fontSize: 14, fontWeight: 700 }}>
            {t('imputa_page.total')}: <span style={{ fontFamily: "'Space Mono', monospace", color: 'var(--accent)', marginLeft: 8 }}>{todayHours.toFixed(1)}h</span>
          </div>
        </Card>
      )}

      <WeekGrid weekData={weekData} t={t} />
    </div>
  )
}
