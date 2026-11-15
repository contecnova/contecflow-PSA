import { useAppLang } from '../i18n/AppLangContext'
import { useState, useMemo, useId } from 'react'
import { openConfirmGlobal } from '../context/ConfirmContext'
import { useToast } from '../context/ToastContext'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { imputationsApi, projectsApi, tasksApi, aiCopilotApi } from '../services/api'
import type { AnomaliasDeImputacion } from '../services/api/tipos-analitica'
import type { Imputacion, ResumenSemanal, SesionDeCronometro } from '../services/api/tipos-personas'
import { queueImputation } from '../services/offlineQueue'
import { Button, Card, Drawer } from '../components/ui'
import PageHeader from '../components/layout/PageHeader'
import PageShell from '../components/layout/PageShell'
import { Clock } from 'lucide-react'
import { useAuth } from '../context/AuthContext'
import { fmtDate, fmtNumber, extractErr, localeActivo } from '../utils/helpers'
import { GENERIC_ERROR_FALLBACK } from '../constants/errors'
import { NOTIFICATIONS_POLL_MS, STALE_5_MIN_MS, UI_FEEDBACK_SAVED_MS } from '../constants/timings'
import { useAppT } from '../i18n/AppLangContext'
import DateInput from '../components/ui/DateInput'
import './ImputarPage.css'

const HOUR_OPTIONS = [0.5, 1, 1.5, 2, 3, 4, 5, 6, 7, 8]

type TFn = (moduleOrFullKey: string, keyOrParams?: string | Record<string, unknown>) => string

interface Anomaly {
  type?: string
  date?: string
  message?: string
  suggestion?: string
  [k: string]: unknown
}
type AnomaliesData = Partial<AnomaliasDeImputacion>
type WeekData = ResumenSemanal

interface ProjectOption { id: string; code?: string; name?: string }
interface TaskOption { id: string; code?: string; title?: string }

interface WeekGridProps {
  weekData: WeekData | undefined
  anomaliesByDate: Record<string, Anomaly>
  hasAnyAnomaly: boolean
  onOpenDrawer: () => void
  t: TFn
}

function WeekGrid({ weekData, anomaliesByDate, hasAnyAnomaly, onOpenDrawer, t }: WeekGridProps) {
  const traducir = useAppT()
  if (!weekData) return null
  // Iniciales de lunes a viernes en el idioma activo (el 1-1-2024 fue lunes).
  const days = [0, 1, 2, 3, 4].map(i => new Intl.DateTimeFormat(localeActivo(), { weekday: 'narrow' }).format(new Date(2024, 0, 1 + i)))
  const byDay = weekData.by_day || []

  return (
    <Card className="imputarp-sx1">
      <div className="u-row-between-mb16">
        <h3 className="imput-title">{t('imputa_page.week_title')}</h3>
        {/* Item #48: badge global de anomalías detectadas en los últimos 30 días.
            Click → abre drawer con detalle de high_hours/gaps/closed_project. */}
        {hasAnyAnomaly && (
          <button
            onClick={onOpenDrawer}
            className="imput-btn"
            title={traducir('imputar.ver_anomalias_detectadas_en_tus_imputaciones')}
          >
            {traducir('imputar.anomalias_detectadas')}
          </button>
        )}
      </div>
      <div className="imput-row">
        {days.map((d, i) => {
          // Compute the ISO date for this weekday from week_start to avoid index-based mapping bugs
          let dayIso = null
          if (weekData.week_start) {
            const base = new Date(weekData.week_start + 'T12:00:00')
            base.setDate(base.getDate() + i)
            dayIso = base.toISOString().split('T')[0]
          }
          const entry = dayIso ? byDay.find((e) => e.date === dayIso) : byDay[i]
          const hasHours = entry && (entry.hours ?? 0) > 0
          const dayAnomaly = dayIso ? anomaliesByDate?.[dayIso] : null
          return (
            <div key={d} className="imput-box">
              <div className="imput-box-2">{d}</div>
              {/* Auditoría 2026-08 (P1-6): era un div con onClick y sin ninguna vía
                  de teclado, así que la celda no se podía activar sin ratón.
                  Se renderiza un <button> REAL cuando es interactiva y un div
                  cuando no: un rol condicional sobre un div deja fuera del orden
                  de tabulación lo que no hace nada, pero el elemento nativo da
                  foco, Enter/Espacio y semántica sin reimplementar nada. */}
              {(() => {
                const Cell = dayAnomaly ? 'button' : 'div'
                const interactiveProps = dayAnomaly
                  ? {
                      type: 'button' as const,
                      onClick: onOpenDrawer,
                      'aria-label': t('pagina_imput.ver_anomalia_del', { dia: d, mensaje: dayAnomaly.message }),
                    }
                  : {}
                return (
              <Cell
                {...interactiveProps}
                style={{
                  background: dayAnomaly
                    ? 'color-mix(in srgb, var(--warning) 18%, transparent)'
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
                {hasHours ? `${fmtNumber(entry?.hours ?? 0, 2)}h` : '—'}
                {dayAnomaly && (
                  <span
                    className="imput-row-2"
                  >!</span>
                )}
              </Cell>
                )
              })()}
            </div>
          )
        })}
      </div>
      <div className="imput-row-3">
        <span>{t('imputa_page.total')}: <span className="imput-label">{fmtNumber(weekData.total_hours, 2)}h</span></span>
        <span>{t('imputa_page.capacity')}: <span className="u-text1">{weekData.capacity_hours}h</span></span>
        <span className="imput-label-2" style={{ color: (weekData.load_pct ?? 0) > 100 ? 'var(--danger)' : (weekData.load_pct ?? 0) > 85 ? 'var(--warning)' : 'var(--success)' }}>
          {weekData.load_pct?.toFixed(0)}{t('imputa_page.load_pct')}
        </span>
      </div>
    </Card>
  )
}


interface AnomaliesDrawerProps {
  open: boolean
  onClose: () => void
  anomaliesData: AnomaliesData | undefined
}

function AnomaliesDrawer({ open, onClose, anomaliesData }: AnomaliesDrawerProps) {
  const { t } = useAppLang()
  const traducir = useAppT()
  // Auditoría 2026-08 (P1-6): el panel NO se cerraba con Escape — sólo con el
  // ratón sobre el fondo o la X. <Drawer> da Escape, trampa de foco y
  // devolución del foco.
  const items: Anomaly[] = anomaliesData?.anomalies || []
  return (
    <Drawer
      open={open}
      onClose={onClose}
      ariaLabel={traducir('imputar.anomalias_en_imputaciones')}
      variant="borde"
      width={420}
      zIndex={1000}
      backdrop="rgba(0,0,0,0.45)"
      style={{ maxWidth: '92vw', boxShadow: 'none', padding: '20px 22px', overflowY: 'auto', gap: 12 }}
    >
        <div className="u-row-between">
          <h3 className="imput-title-2">
            {traducir('imputar.anomalias_en_imputaciones_2')}
          </h3>
          <button onClick={onClose} aria-label={t('pagina_imput.cerrar')}
            className="imput-btn-2">
            ✕
          </button>
        </div>
        <div className="u-text3-sm">
          {t('pagina_imput.periodo_resumen', { desde: anomaliesData?.period?.from ?? '', hasta: anomaliesData?.period?.to ?? '', n: anomaliesData?.total_entries ?? 0 })}
        </div>
        {items.length === 0 ? (
          <div className="imput-box-3">
            {traducir('imputar.sin_anomalias_detectadas')}
          </div>
        ) : items.map((a: Anomaly, idx: number) => (
          <div key={idx} className="imput-card">
            <div className="imput-box-4">
              {a.type === 'high_hours'
                ? t('pagina_imput.dia_con_muchas_horas', { date: a.date })
                : a.type === 'gap'
                  ? t('pagina_imput.periodo_sin_imputaciones')
                  : t('pagina_imput.proyectos_cerrados')}
            </div>
            <div className="imput-box-5">
              {a.message}
            </div>
            {a.suggestion && (
              <div className="u-text2-sm">
                💡 {a.suggestion}
              </div>
            )}
          </div>
        ))}
    </Drawer>
  )
}

export default function ImputarPage(): JSX.Element {
  const idCampo = useId()
  const traducir = useAppT()
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
  const [duplicateError, setDuplicateError] = useState<string | null>(null)
  const [forceDuplicate, setForceDuplicate] = useState(false)

  const { data: projects = [] } = useQuery<ProjectOption[]>({
    queryKey: ['projects'],
    queryFn: () => projectsApi.list().then(r => r.data),
  })

  const { data: tasks = [] } = useQuery<TaskOption[]>({
    queryKey: ['tasks-my', form.project_id],
    // Auditoría 2026-11 (#25): `GET /tasks` no tiene filtro `assigned_to` (lo ignoraba y salían
    // todas las tareas del proyecto); el suyo es `assigned_to_me`, como en TimerPage.
    queryFn: () => tasksApi.list({ project_id: form.project_id, assigned_to_me: true }).then(r => r.data),
    enabled: !!form.project_id,
  })

  const { data: weekData } = useQuery<WeekData>({
    queryKey: ['my-week'],
    queryFn: () => imputationsApi.myWeek({}).then(r => r.data),
  })

  const { data: activeTimer } = useQuery<SesionDeCronometro | null>({
    queryKey: ['timer-current'],
    queryFn: () => imputationsApi.timerCurrent().then(r => r.data).catch(() => null),
    refetchInterval: NOTIFICATIONS_POLL_MS,
  })

  const { data: todayImputations = [] } = useQuery<Imputacion[]>({
    queryKey: ['imputations-today'],
    queryFn: () => imputationsApi.list({ date_from: today, date_to: today, user_id: user?.id }).then(r => r.data),
  })

  // Item #48: anomalías de imputación del propio user (últimos 30 días).
  // Heurística + estadística (mean + 2σ con n≥7). Solo se invoca si hay user.
  const { data: anomaliesData } = useQuery<AnomaliesData>({
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
    const out: Record<string, Anomaly> = {}
    for (const a of (anomaliesData?.anomalies || [])) {
      if (a?.type === 'high_hours' && a?.date) out[a.date] = a
    }
    return out
  }, [anomaliesData])

  const hasAnyAnomaly = (anomaliesData?.anomalies?.length || 0) > 0

  const [anomaliesDrawerOpen, setAnomaliesDrawerOpen] = useState(false)

  const { mutate, isPending } = useMutation({
    mutationFn: (data: Record<string, unknown>) => imputationsApi.create(data),
    onSuccess: () => {
      setSaved(true)
      setDuplicateError(null)
      setForceDuplicate(false)
      setTimeout(() => setSaved(false), UI_FEEDBACK_SAVED_MS)
      setForm(f => ({ ...f, task_id: '', hours: 0, description: '' }))
      qc.invalidateQueries({ queryKey: ['my-week'] })
      qc.invalidateQueries({ queryKey: ['imputations-today'] })
      qc.invalidateQueries({ queryKey: ['dash-hours-week'] })
      qc.invalidateQueries({ queryKey: ['timesheets-mine'] })
      qc.invalidateQueries({ queryKey: ['timesheets-pending'] })
      qc.invalidateQueries({ queryKey: ['timesheets-team'] })
    },
    onError: (e: unknown) => {
      const err = e as { response?: { status?: number; data?: { detail?: string } } }
      if (err?.response?.status === 409) {
        setDuplicateError(err?.response?.data?.detail || t('pagina_imput.ya_existe_una_imputacion_para_esta'))
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
        setTimeout(() => setSaved(false), UI_FEEDBACK_SAVED_MS)
        setForm(f => ({ ...f, task_id: '', hours: 0, description: '' }))
        toast.success(t('pagina_imput.sin_conexion_la_imputacion_se_sincronizara'))
      } catch {
        toast.error(t('imputa_page.offline_error'))
      }
      return
    }
    mutate({ ...form, force_duplicate: forceDuplicate })
  }

  const [editingId, setEditingId] = useState<string | null>(null)
  const [editForm, setEditForm] = useState({ hours: 0, description: '', is_billable: false })

  const { mutate: updateImp, isPending: updating } = useMutation({
    mutationFn: ({ id, data }: { id: string; data: Record<string, unknown> }) => imputationsApi.update(id, data),
    onSuccess: () => {
      setEditingId(null)
      qc.invalidateQueries({ queryKey: ['my-week'] })
      qc.invalidateQueries({ queryKey: ['imputations-today'] })
      qc.invalidateQueries({ queryKey: ['dash-hours-week'] })
      qc.invalidateQueries({ queryKey: ['timesheets-mine'] })
      qc.invalidateQueries({ queryKey: ['timesheets-pending'] })
      qc.invalidateQueries({ queryKey: ['timesheets-team'] })
      toast.success(t('imputa_page.updated_ok'))
    },
    onError: (e: unknown) => toast.error(extractErr(e, t('common.error') || GENERIC_ERROR_FALLBACK)),
  })

  const { mutate: deleteImp } = useMutation({
    mutationFn: (id: string) => imputationsApi.delete(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['my-week'] })
      qc.invalidateQueries({ queryKey: ['imputations-today'] })
      qc.invalidateQueries({ queryKey: ['dash-hours-week'] })
      qc.invalidateQueries({ queryKey: ['timesheets-mine'] })
      qc.invalidateQueries({ queryKey: ['timesheets-pending'] })
      qc.invalidateQueries({ queryKey: ['timesheets-team'] })
      toast.success(t('imputa_page.deleted_ok'))
    },
    onError: (e: unknown) => toast.error(extractErr(e, t('common.error') || GENERIC_ERROR_FALLBACK)),
  })

  const set = (k: string) => (v: unknown) => {
    setForm(f => ({ ...f, [k]: v }))
    if (k === 'task_id' || k === 'date') {
      setDuplicateError(null)
      setForceDuplicate(false)
    }
  }
  const todayHours = todayImputations.reduce((s: number, i: Imputacion) => s + i.hours, 0)
  const canSubmit = form.project_id && form.hours > 0 && form.date

  return (
    <PageShell className="imput-box-13">
      <PageHeader
        icon={<Clock size={18} />}
        title={t('imputa_page.title')}
        subtitle={t('imputa_page.subtitle', { date: fmtDate(today), hours: todayHours.toFixed(1) })}
      showListExport={false}
      />

      {activeTimer && (
        <div className="imput-row-4">
          <span className="imput-label-3">⏱</span>
          {t('imputa_page.timer_running')}
          {activeTimer.total_elapsed_seconds != null && (
            <span className="imput-label-4">
              · {Math.floor(activeTimer.total_elapsed_seconds / 3600)}h {Math.floor((activeTimer.total_elapsed_seconds % 3600) / 60)}m
            </span>
          )}
          <a href="/timer" className="imput-link">
            {t('imputa_page.timer_link')}
          </a>
        </div>
      )}

      <Card>
        {/* Project */}
        <div className="u-mb-20">
          <label id={`${idCampo}-et1`} htmlFor={`${idCampo}-1`} className="imput-label-5">
            {t('imputa_page.project_label')} <span className="u-danger">*</span>
          </label>
          <select id={`${idCampo}-1`} aria-labelledby={`${idCampo}-et1`}
            value={form.project_id}
            onChange={e => set('project_id')(e.target.value)}
            className={`imput-input ${form.project_id ? 'imputarp-sx2' : 'imputarp-sx3'}`}
          >
            <option value="">{t('imputa_page.project_placeholder')}</option>
            {projects.map(p => (
              <option key={p.id} value={p.id}>{p.code} — {p.name}</option>
            ))}
          </select>
        </div>

        {/* Task */}
        <div className="u-mb-20">
          <label id={`${idCampo}-et2`} htmlFor={`${idCampo}-2`} className="imput-label-5">
            {t('imputa_page.task_label')}
          </label>
          <select id={`${idCampo}-2`} aria-labelledby={`${idCampo}-et2`}
            value={form.task_id}
            onChange={e => set('task_id')(e.target.value)}
            disabled={!form.project_id}
            className={`imput-input-2 ${form.project_id ? 'imputarp-sx4' : 'imputarp-sx5'}`}
          >
            <option value="">{t('imputa_page.task_none')}</option>
            {tasks.map(t => (
              <option key={t.id} value={t.id}>{t.code} — {t.title}</option>
            ))}
          </select>
        </div>

        {/* Date */}
        <div className="u-mb-20">
          <label id={`${idCampo}-et3`} htmlFor={`${idCampo}-3`} className="imput-label-5">
            {t('imputa_page.date_label')} <span className="u-danger">*</span>
          </label>
          <DateInput id={`${idCampo}-3`}
            value={form.date}
            onChange={e => set('date')(e.target.value)}
            max={today}
            className="imput-card-7"
          />
        </div>

        {/* Hours */}
        <div className="u-mb-20">
          <label className="imput-label-5">
            {t('imputa_page.hours_label')} <span className="u-danger">*</span>
          </label>
          <div className="imput-row-5">
            {HOUR_OPTIONS.map(h => (
              <button
                key={h}
                onClick={() => set('hours')(h)}
                className={`imput-btn-3 imputarp-sx6 ${form.hours === h ? 'imputarp-sx7' : 'imputarp-sx8'}`} style={{ border: `1px solid ${form.hours === h ? 'var(--accent)' : 'var(--surface-4)'}` }}
              >
                {h}h
              </button>
            ))}
          </div>
          {form.hours > 0 && (
            <div className="imput-box-6">
              {t('imputa_page.total_today')}: <span className={`imput-label-2 ${todayHours + form.hours > 8 ? 'imputarp-sx9' : 'imputarp-sx2'}`}>
                {(todayHours + form.hours).toFixed(1)}h
              </span> / 8h
            </div>
          )}
        </div>

        {/* Description */}
        <div className="u-mb-20">
          <label id={`${idCampo}-et4`} htmlFor={`${idCampo}-4`} className="imput-label-6">
            {t('imputa_page.description_label')}
          </label>
          <textarea id={`${idCampo}-4`} aria-labelledby={`${idCampo}-et4`}
            value={form.description}
            onChange={e => set('description')(e.target.value)}
            placeholder={t('imputa_page.description_placeholder')}
            rows={3}
            className="imput-input-3"
          />
        </div>

        {/* Billable toggle */}
        <div className="imput-box-7">
          <label className="imput-label-7">
            <input
              type="checkbox"
              checked={form.is_billable}
              aria-label={t('imputa_page.billable_label')}
              onChange={e => set('is_billable')(e.target.checked)}
              className="imput-input-4"
            />
            <div aria-hidden="true" className={`imput-box-8 ${form.is_billable ? 'imputarp-sx10' : 'imputarp-sx11'}`}>
              <div className={`imput-card-2 ${form.is_billable ? 'imputarp-sx12' : 'imputarp-sx13'}`} />
            </div>
            <span className={`imput-label-8 ${form.is_billable ? 'imputarp-sx14' : 'imputarp-sx3'}`}>
              {t('imputa_page.billable_label')}
            </span>
            {form.is_billable && (
              <span className="imput-card-3">
                {t('imputa_page.billable_badge')}
              </span>
            )}
          </label>
        </div>

        {/* Duplicate error panel */}
        {duplicateError && (
          <div className="imput-card-4">
            <div className="imput-box-9">
              ⚠️ {duplicateError}
            </div>
            <label className="imput-label-9">
              <input
                type="checkbox"
                checked={forceDuplicate}
                aria-label={traducir('imputar.permitir_imputacion_duplicada_y_avisar_al_manager')}
                onChange={e => setForceDuplicate(e.target.checked)}
                className="imput-input-5"
              />
              <span>{traducir('imputar.permitir_imputacion_duplicada_y_avisar_al_manager')}</span>
            </label>
          </div>
        )}

        <button
          onClick={handleSubmit}
          disabled={!canSubmit || isPending || (!!duplicateError && !forceDuplicate)}
          className={`imput-btn-4 ${(canSubmit && (!duplicateError || forceDuplicate)) ? 'imputarp-sx15' : 'imputarp-sx16'}`} style={{ background: saved ? 'var(--success)' : (canSubmit && (!duplicateError || forceDuplicate)) ? 'var(--accent)' : 'var(--surface-4)' }}
        >
          {saved ? t('imputa_page.saved') : isPending ? t('imputa_page.saving') : navigator.onLine ? t('imputa_page.submit') : t('imputa_page.submit_offline')}
        </button>
      </Card>

      {/* Today's imputations */}
      {todayImputations.length > 0 && (
        <Card className="imputarp-sx1">
          <h3 className="imput-title-3">{t('imputa_page.today_entries')}</h3>
          {todayImputations.map(imp => (
            <div key={imp.id} className="imput-card-5">
              {editingId === imp.id ? (
                /* Modo edición inline */
                <div className="imput-row-6">
                  <div className="imput-box-10">
                    <label className="imput-label-10">{t('imputa_page.hours_edit').toUpperCase()}</label>
                    <input
                      type="number" step="0.25" min="0.25" max="24"
                      value={editForm.hours}
                      aria-label={t('imputa_page.hours_edit')}
                      onChange={e => setEditForm(f => ({ ...f, hours: parseFloat(e.target.value) || 0 }))}
                      className="imput-input-6"
                    />
                  </div>
                  <div className="imput-box-11">
                    <label className="imput-label-10">{t('imputa_page.description_edit').toUpperCase()}</label>
                    <input
                      value={editForm.description}
                      aria-label={t('imputa_page.description_edit')}
                      onChange={e => setEditForm(f => ({ ...f, description: e.target.value }))}
                      className="imput-input-7"
                    />
                  </div>
                  <div className="imput-box-12">
                    <label className={`imput-label-11 ${editForm.is_billable ? 'imputarp-sx14' : 'imputarp-sx17'}`}>
                      <input
                        type="checkbox"
                        checked={editForm.is_billable}
                        aria-label={t('imputa_page.billable_label')}
                        onChange={e => setEditForm(f => ({ ...f, is_billable: e.target.checked }))}
                        className="imput-input-8"
                      />
                      {t('imputa_page.billable_label')}
                    </label>
                  </div>
                  <div className="u-row-6">
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
                <div className="imput-row-7">
                  <div>
                    <span className="u-600">{imp.project?.name || '—'}</span>
                    {imp.task?.title && <span className="imput-label-12">· {imp.task.title}</span>}
                    {imp.description && <span className="imput-label-13">· {imp.description}</span>}
                    {imp.is_billable && (
                      <span className="imput-card-6">
                        {t('imputa_page.billable_badge')}
                      </span>
                    )}
                  </div>
                  <div className="u-row-center-8">
                    <span className="imput-label-14">{imp.hours}h</span>
                    <button
                      onClick={() => { setEditingId(imp.id); setEditForm({ hours: imp.hours, description: imp.description || '', is_billable: imp.is_billable ?? false }) }}
                      className="imput-btn-5"
                      aria-label={t('imputa_page.edit_aria')}
                      title={t('imputa_page.edit_aria')}>✏</button>
                    <button
                      onClick={() => { openConfirmGlobal({ message: t('imputa_page.confirm_delete'), onConfirm: () => deleteImp(imp.id), danger: true }) }}
                      className="imput-btn-6"
                      aria-label={t('imputa_page.delete_aria')}
                      title={t('imputa_page.delete_aria')}>✕</button>
                  </div>
                </div>
              )}
            </div>
          ))}
          <div className="imput-row-8">
            {t('imputa_page.total')}: <span className="imput-label-15">{todayHours.toFixed(1)}h</span>
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
