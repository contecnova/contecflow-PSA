/**
 * Timer Page — Seguimiento de tiempo con cronómetro activo e historial
 */
import { useState, useEffect, useRef, useId } from 'react'
import type { TaskListParams, TaskListItem } from '../services/api/tasks'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { imputationsApi, projectsApi, tasksApi } from '../services/api'
import type { Imputacion, SesionDeCronometro } from '../services/api/tipos-personas'
import { useAuth } from '../context/AuthContext'
import PageHeader from '../components/layout/PageHeader'
import PageShell from '../components/layout/PageShell'
import { useDialogo, Table } from '../components/ui'
import { Timer } from 'lucide-react'
import { useToast } from '../context/ToastContext'
import { useAppT } from '../i18n/AppLangContext'
import { useOnlineStatus } from '../hooks/useOnlineStatus'
import { DEFAULT_PAGE_SIZE, LARGE_PAGE_SIZE, NOTIFICATIONS_POLL_MS, STALE_5_MIN_MS, POLL_DEFAULT_MS, CLOCK_TICK_MS } from '../constants/timings'
import { localeActivo } from '../utils/helpers'
import './TimerPage.css'

type TimerData = SesionDeCronometro

type ApiErr = { response?: { data?: { detail?: string } } }

type TimerHistoryItem = Imputacion

function formatTime(seconds: number) {
  const h = Math.floor(seconds / 3600)
  const m = Math.floor((seconds % 3600) / 60)
  const s = seconds % 60
  return String(h).padStart(2,'0')+':'+String(m).padStart(2,'0')+':'+String(s).padStart(2,'0')
}

function computeElapsed(timer: TimerData | null | undefined) {
  if (!timer) return 0
  // If paused, use server-computed value (avoids timezone drift)
  if (timer.paused_at && timer.total_elapsed_seconds != null) {
    return timer.total_elapsed_seconds
  }
  // Ensure ISO string has timezone (backend may omit Z for naive UTC)
  const startStr = timer.started_at.endsWith('Z') || timer.started_at.includes('+')
    ? timer.started_at
    : timer.started_at + 'Z'
  const startedAt = new Date(startStr)
  const totalPausedSecs = timer.paused_duration_secs || 0
  if (timer.paused_at) {
    const pausedStr = timer.paused_at.endsWith('Z') || timer.paused_at.includes('+')
      ? timer.paused_at
      : timer.paused_at + 'Z'
    return Math.max(0, Math.floor((new Date(pausedStr).getTime() - startedAt.getTime()) / 1000) - totalPausedSecs)
  }
  return Math.max(0, Math.floor((Date.now() - startedAt.getTime()) / 1000) - totalPausedSecs)
}

function _onKeyboardActivate(event: { key: string; preventDefault: () => void }, action: () => void) {
  if (event.key === 'Enter' || event.key === ' ') {
    event.preventDefault()
    action()
  }
}

function StartModal({ onClose, onStart, isPending }: {
  onClose: () => void
  onStart: (p: { project_id: string; task_id: string | null; is_billable: boolean }) => void
  isPending: boolean
}) {
  const idCampo = useId()
  const traducir = useAppT()
  const [projectId, setProjectId] = useState('')
  const [taskId,    setTaskId]    = useState('')
  const [billable,  setBillable]  = useState(true)

  const { data: projects = [] } = useQuery<Array<{ id: string; name?: string }>>({
    queryKey: ['projects-list-timer'],
    queryFn: () => projectsApi.list({ page_size: LARGE_PAGE_SIZE, status: 'active' }).then((r) => r.data),
  })

  const { data: tasks = [] } = useQuery<TaskListItem[]>({
    queryKey: ['tasks-for-project-timer', projectId],
    queryFn: () => tasksApi.list({ project_id: projectId, assigned_to_me: true, page_size: LARGE_PAGE_SIZE } as TaskListParams).then((r) => r.data),
    enabled: !!projectId,
  })
  const dialogRef = useDialogo<HTMLDivElement>(true, onClose)

  return (
    <>
      <div role="presentation" onMouseDown={onClose} className="tm-scrim" />
      <div className="tm-dialog-wrap">
      <div ref={dialogRef} role="dialog" aria-modal="true" aria-labelledby="start-timer-title"
        tabIndex={-1}
        className="tm-dialog">
        <div className="tm-dialog-head">
          <div>
            <div id="start-timer-title" className="tm-dialog-title">{traducir('timer.iniciar_cronometro')}</div>
            <div className="tm-dialog-sub">{traducir('timer.selecciona_proyecto_y_tarea')}</div>
          </div>
          <button type="button" onClick={onClose} aria-label={traducir('timer.cerrar')} className="tm-close"><span aria-hidden="true">✕</span></button>
        </div>
        <div className="u-mb-14">
          <label id={`${idCampo}-et1`} htmlFor={`${idCampo}-1`} className="tm-label">{traducir('timer.proyecto_obligatorio')}</label>
          <select id={`${idCampo}-1`} aria-labelledby={`${idCampo}-et1`} value={projectId} onChange={e => { setProjectId(e.target.value); setTaskId('') }} className="tm-field" aria-required="true">
            <option value="">{traducir('timer.selecciona_un_proyecto')}</option>
            {projects.map(p => <option key={p.id} value={p.id}>{p.name}</option>)}
          </select>
        </div>
        <div className="u-mb-14">
          <label id={`${idCampo}-et2`} htmlFor={`${idCampo}-2`} className="tm-label">{traducir('timer.tarea_opcional')}</label>
          <select id={`${idCampo}-2`} aria-labelledby={`${idCampo}-et2`} value={taskId} onChange={e => setTaskId(e.target.value)}
            className="tm-field" disabled={!projectId}>
            <option value="">{traducir('timer.sin_tarea')}</option>
            {tasks.map(t => <option key={t.id} value={t.id}>{t.title || (t as { name?: string }).name}</option>)}
          </select>
        </div>
        <label className="tm-check">
          <input type="checkbox" aria-label={traducir('timer.tiempo_facturable')} checked={billable} onChange={e => setBillable(e.target.checked)}
            className="tm-check-input" />
          {traducir('timer.tiempo_facturable')}
        </label>
        <div className="u-row-10">
          <button type="button" disabled={!projectId || isPending}
            onClick={() => onStart({ project_id: projectId, task_id: taskId || null, is_billable: billable })}
            className="tm-btn tm-btn--accent tm-btn--grow">
            {isPending ? `▶ ${traducir('timer.iniciando')}` : `▶ ${traducir('timer.iniciar')}`}
          </button>
          <button type="button" onClick={onClose} className="tm-btn tm-btn--secondary">{traducir('timer.cancelar')}</button>
        </div>
      </div>
      </div>
    </>
  )
}

function StopModal({ currentTimer, onClose, onStop, onCancelTimer, pendingAction, elapsed }: {
  currentTimer: TimerData | null | undefined
  onClose: () => void
  onStop: (p: { description: string; is_billable: boolean; task_id: string | null; force_duplicate: boolean }) => void
  onCancelTimer: () => void
  pendingAction: 'stop' | 'cancel' | null
  elapsed: number
}) {
  const traducir = useAppT()
  const idCampo = useId()
  const [description, setDescription] = useState('')
  const [billable, setBillable] = useState(true)
  const [taskId, setTaskId] = useState<string>(currentTimer?.task_id ? String(currentTimer.task_id) : '')
  const [forceDuplicate, setForceDuplicate] = useState(false)

  useEffect(() => {
    setTaskId(currentTimer?.task_id ? String(currentTimer.task_id) : '')
    setForceDuplicate(false)
  }, [currentTimer?.id, currentTimer?.task_id])

  const { data: tasks = [] } = useQuery<TaskListItem[]>({
    queryKey: ['tasks-for-stop-timer', currentTimer?.project_id, 'mine'],
    queryFn: () => tasksApi.list({ project_id: currentTimer?.project_id, assigned_to_me: true, page_size: LARGE_PAGE_SIZE } as TaskListParams).then((r) => r.data),
    enabled: !!currentTimer?.project_id,
  })

  const isSaving = pendingAction === 'stop'
  const isCancelling = pendingAction === 'cancel'
  const isBusy = pendingAction !== null
  const dialogRef = useDialogo<HTMLDivElement>(true, onClose)

  return (
    <>
      <div role="presentation" onMouseDown={onClose} className="tm-scrim" />
      <div className="tm-dialog-wrap">
      <div ref={dialogRef} role="dialog" aria-modal="true" aria-labelledby="stop-timer-title"
        tabIndex={-1}
        className="tm-dialog tm-dialog--narrow">
        <div className="tm-dialog-head tm-dialog-head--tight">
          <div>
            <div id="stop-timer-title" className="tm-dialog-title">{traducir('timer.detener_sesion')}</div>
            <div className="tm-dialog-sub">
              {traducir('timer.tiempo')}: <strong className="tm-elapsed-inline">{formatTime(elapsed)}</strong>
            </div>
          </div>
          <button type="button" onClick={onClose} aria-label={traducir('timer.cerrar')} className="tm-close"><span aria-hidden="true">✕</span></button>
        </div>
        <div className="u-mb-14">
          <label id={`${idCampo}-etdesc`} htmlFor={`${idCampo}-desc`} className="tm-label">{traducir('timer.descripcion_del_trabajo')}</label>
          <textarea id={`${idCampo}-desc`} aria-labelledby={`${idCampo}-etdesc`} value={description} onChange={e => setDescription(e.target.value)}
            className="tm-field tm-field--textarea" rows={3}
            placeholder={traducir('timer.describe_el_trabajo_realizado')} autoFocus />
        </div>
        <div className="u-mb-14">
          <label id={`${idCampo}-etfin`} htmlFor={`${idCampo}-fin`} className="tm-label">{traducir('timer.tarea_final')}</label>
          <select id={`${idCampo}-fin`} aria-labelledby={`${idCampo}-etfin`} aria-describedby={`${idCampo}-finayuda`} value={taskId} onChange={e => setTaskId(e.target.value)} className="tm-field">
            <option value="">{traducir('timer.sin_tarea')}</option>
            {tasks.map(task => <option key={task.id} value={task.id}>{task.title || (task as { name?: string }).name}</option>)}
          </select>
          <div id={`${idCampo}-finayuda`} className="tm-help">
            {traducir('timer.si_ya_existe_una_imputacion_para_esa')}
          </div>
        </div>
        <label className="tm-check">
          <input type="checkbox" aria-label={traducir('timer.marcar_como_facturable')} checked={billable} onChange={e => setBillable(e.target.checked)}
            className="tm-check-input" />
          {traducir('timer.marcar_como_facturable')}
        </label>
        <label className="tm-check tm-check--warning">
          <input type="checkbox" aria-label={traducir('timer.permitir_imputacion_duplicada_y_avisar_al_manager')} checked={forceDuplicate} onChange={e => setForceDuplicate(e.target.checked)}
            className="tm-check-input tm-check-input--warning" />
          <span>{traducir('timer.permitir_imputacion_duplicada_y_avisar_al_manager')}</span>
        </label>
        <div className="tm-dialog-actions">
          <div className="u-grid2-10">
          <button type="button" disabled={isBusy}
            onClick={() => onStop({ description: description || traducir('timer.sesion_de_trabajo'), is_billable: billable, task_id: taskId || null, force_duplicate: forceDuplicate })}
            className="tm-btn tm-btn--danger">
            {isSaving ? traducir('timer.guardando') : `⏹ ${traducir('timer.guardar_y_cerrar')}`}
          </button>
          <button type="button" onClick={onClose} className="tm-btn tm-btn--secondary">{traducir('timer.cancelar')}</button>
          </div>
          <button type="button" disabled={isBusy} onClick={onCancelTimer} className="tm-btn tm-btn--cancel-timer">
            {isCancelling ? traducir('timer.cancelando') : `🗑 ${traducir('timer.cancelar_cronometro')}`}
          </button>
        </div>
      </div>
      </div>
    </>
  )
}

export default function TimerPage() {
  const traducir = useAppT()
  const t       = useAppT()
  const toast   = useToast()
  const qc      = useQueryClient()
  const { user } = useAuth()
  const [elapsed,    setElapsed]   = useState(0)
  const [showStart,  setShowStart] = useState(false)
  const [showStop,   setShowStop]  = useState(false)
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null)

  const { data: currentTimer } = useQuery<TimerData | null>({
    queryKey: ['timer-current'],
    queryFn: () => imputationsApi.timerCurrent().then((r) => r.data),
    refetchInterval: NOTIFICATIONS_POLL_MS,
  })

  const { data: timerProject } = useQuery({
    queryKey: ['timer-current-project', currentTimer?.project_id],
    queryFn: () => projectsApi.get(String(currentTimer?.project_id)).then(r => r.data),
    enabled: !!currentTimer?.project_id && !currentTimer?.project_name,
    staleTime: STALE_5_MIN_MS,
  })

  const { data: timerTask } = useQuery({
    queryKey: ['timer-current-task', currentTimer?.task_id],
    queryFn: () => tasksApi.get(String(currentTimer?.task_id)).then(r => r.data),
    enabled: !!currentTimer?.task_id && !currentTimer?.task_name,
    staleTime: STALE_5_MIN_MS,
  })

  // Solo las suyas: sin `user_id`, a un responsable `GET /imputations` le devuelve las de todos.
  const { data: timerHistory = [] } = useQuery<TimerHistoryItem[]>({
    queryKey: ['timer-history', user?.id],
    queryFn: () => imputationsApi.list({ page_size: DEFAULT_PAGE_SIZE, user_id: user?.id })
      .then((r) => r.data.filter((imp) => imp.timer_session_id)),
    enabled: !!user?.id,
    refetchInterval: POLL_DEFAULT_MS,
  })

  useEffect(() => {
    clearInterval(intervalRef.current ?? undefined)
    if (!currentTimer) { setElapsed(0); return }
    const tick = () => setElapsed(computeElapsed(currentTimer))
    tick()
    if (!currentTimer.paused_at) {
      intervalRef.current = setInterval(tick, CLOCK_TICK_MS)
    }
    return () => clearInterval(intervalRef.current ?? undefined)
  }, [currentTimer])

  const startMutation = useMutation({
    mutationFn: (p: Record<string, unknown>) => imputationsApi.timerStart(p).then(r => r.data),
    onSuccess: (data) => { toast.success(t('timer.toast_iniciado')); qc.setQueryData(['timer-current'], data); setShowStart(false) },
    onError: (e: ApiErr) => toast.error(e?.response?.data?.detail || t('timer.error_iniciar')),
  })
  const pauseMutation = useMutation({
    mutationFn: () => imputationsApi.timerPause().then(r => r.data),
    onSuccess: (data) => { toast.success(t('timer.toast_pausado')); qc.setQueryData(['timer-current'], data) },
    onError: (e: ApiErr) => toast.error(e?.response?.data?.detail || t('timer.error_pausar')),
  })
  const resumeMutation = useMutation({
    mutationFn: () => imputationsApi.timerResume().then(r => r.data),
    onSuccess: (data) => { toast.success(t('timer.toast_reanudado')); qc.setQueryData(['timer-current'], data) },
    onError: (e: ApiErr) => toast.error(e?.response?.data?.detail || t('timer.error_reanudar')),
  })
  const cancelMutation = useMutation({
    mutationFn: () => imputationsApi.timerCancel().then(r => r.data),
    onSuccess: () => {
      toast.success(t('timer.toast_cancelado'))
      qc.setQueryData(['timer-current'], null)
      setShowStop(false)
      setElapsed(0)
    },
    onError: (e: ApiErr) => toast.error(e?.response?.data?.detail || t('timer.error_cancelar')),
  })
  const stopMutation = useMutation({
    mutationFn: (p: Record<string, unknown>) => imputationsApi.timerStop(p).then(r => r.data),
    onSuccess: () => {
      toast.success(t('timer.toast_guardado'))
      qc.setQueryData(['timer-current'], null)
      qc.invalidateQueries({ queryKey: ['timer-history'] })
      qc.invalidateQueries({ queryKey: ['my-week'] })
      qc.invalidateQueries({ queryKey: ['imputations-today'] })
      qc.invalidateQueries({ queryKey: ['dash-hours-week'] })
      qc.invalidateQueries({ queryKey: ['timesheets-mine'] })
      qc.invalidateQueries({ queryKey: ['timesheets-pending'] })
      qc.invalidateQueries({ queryKey: ['timesheets-team'] })
      setShowStop(false); setElapsed(0)
    },
    onError: (e: ApiErr) => {
      const detail = e?.response?.data?.detail || t('timer.error_detener')
      toast.error(detail)
    },
  })

  const isPaused  = !!currentTimer?.paused_at
  const isRunning = !!currentTimer && !isPaused
  const isLoading = pauseMutation.isPending || resumeMutation.isPending || stopMutation.isPending || cancelMutation.isPending
  const stopPendingAction = stopMutation.isPending ? 'stop' : cancelMutation.isPending ? 'cancel' : null
  const stateClass = isRunning ? 'tm-session--running' : isPaused ? 'tm-session--paused' : ''
  const stateLabel = isRunning ? t('timer.estado_corriendo') : isPaused ? t('timer.paused') : t('timer.estado_sin_sesion')
  const isOnline = useOnlineStatus()
  const timerProjectLabel = currentTimer?.project_name || timerProject?.name || (currentTimer?.project_id ? t('timer.proyecto_n', { id: currentTimer.project_id }) : '—')
  const timerTaskLabel = currentTimer?.task_name || timerTask?.title || (timerTask as { name?: string } | undefined)?.name || (currentTimer?.task_id ? t('timer.tarea_n', { id: currentTimer.task_id }) : null)

  return (
    <PageShell className="tm-page">
      {!isOnline && (
        <div className="tm-offline" role="status">
          {traducir('timer.sin_conexion_los_registros_de_tiempo_se')}
        </div>
      )}
      <PageHeader
        icon={<Timer size={18} />}
        title={t('timer.title')}
        subtitle={t('timer.subtitle')}
        actions={!currentTimer && (
          <button type="button" onClick={() => setShowStart(true)} className="tm-btn tm-btn--header">{traducir('timer.nueva_sesion')}</button>
        )}
      />

      {currentTimer ? (
        <div className={`tm-session ${stateClass}`}>
          <div className="u-row-center-8">
            <span className="tm-state-dot" aria-hidden="true" />
            <span className="tm-state-label">
              {stateLabel}
            </span>
          </div>

          <div className="tm-session-project">
            <span aria-hidden="true">📁</span> {timerProjectLabel}
            {currentTimer.task_id && (
              <span className="tm-session-task">
                · {timerTaskLabel}
              </span>
            )}
          </div>

          <div className="tm-clock" role="timer" aria-label={t('timer.elapsed')}>
            {formatTime(elapsed)}
          </div>

          <div className="u-text3-sm">
            {t('timer.inicio')}: {new Date(currentTimer.started_at).toLocaleTimeString(localeActivo(), { hour: '2-digit', minute: '2-digit', second: '2-digit' })}
            {(currentTimer.paused_duration_secs || 0) > 0 && (
              <span className="tm-paused-acc">· {t('timer.pausado_acumulado')}: {formatTime(currentTimer.paused_duration_secs ?? 0)}</span>
            )}
          </div>

          <div className="tm-controls">
            {isPaused ? (
              <button type="button" onClick={() => resumeMutation.mutate()} disabled={isLoading} className="tm-btn tm-btn--big tm-btn--accent">▶ {t('timer.reanudar')}</button>
            ) : (
              <button type="button" onClick={() => pauseMutation.mutate()} disabled={isLoading} className="tm-btn tm-btn--big tm-btn--warning">⏸ {t('timer.pausar')}</button>
            )}
            <button type="button" onClick={() => setShowStop(true)} disabled={isLoading} className="tm-btn tm-btn--big tm-btn--danger">⏹ {t('timer.detener_y_guardar')}</button>
          </div>
        </div>
      ) : (
        <div className="tm-idle">
          <div className="tm-idle-icon" aria-hidden="true">⏱</div>
          <div className="tm-idle-title">{traducir('timer.sin_sesion_activa')}</div>
          <div className="tm-idle-desc">
            {traducir('timer.inicia_el_cronometro_para_registrar_tiempo_automaticamente')}
          </div>
          <button type="button" onClick={() => setShowStart(true)} className="tm-btn tm-btn--big tm-btn--accent tm-btn--start">{traducir('timer.iniciar_cronometro_2')}</button>
        </div>
      )}

      <div className="tm-history">
        <div className="tm-history-head">
          <div className="tm-history-title">{traducir('timer.historial_de_sesiones')}</div>
          <div className="u-text3-sm">
            {t(timerHistory.length === 1 ? 'timer.n_sesion_una' : 'timer.n_sesiones', { n: timerHistory.length })}
          </div>
        </div>
        {timerHistory.length === 0 ? (
          <div className="tm-history-empty">
            {traducir('timer.no_hay_sesiones_registradas_todavia')}
          </div>
        ) : (
          <Table
            data={timerHistory}
            columns={[
              { key: 'project', label: t('timer.col_proyecto'), render: (_v, s) => (
                <span className="tm-cell-strong">
                  {s.project?.name || s.project?.code || t('timer.proyecto_n', { id: s.project?.id || '?' })}
                </span>
              ) },
              { key: 'description', label: t('timer.col_descripcion'), render: (_v, s) => (
                <span className="tm-cell-desc">
                  {s.description || '—'}
                </span>
              ) },
              { key: 'hours', label: t('timer.col_horas'), render: (_v, s) => (
                <span className="tm-cell-hours">
                  {s.hours.toFixed(2)}h
                </span>
              ) },
              { key: 'is_billable', label: t('timer.col_tipo'), render: (_v, s) => (
                <span className={`tm-chip${s.is_billable ? ' tm-chip--billable' : ''}`}>
                  {s.is_billable ? `💰 ${t('timer.facturable')}` : `🔧 ${t('timer.interno')}`}
                </span>
              ) },
              { key: 'created_at', label: t('timer.col_fecha'), render: (_v, s) => (
                <span className="u-text3-sm">
                  {s.created_at ? new Date(s.created_at).toLocaleDateString(localeActivo(), { day: '2-digit', month: 'short', year: 'numeric' }) : '—'}
                </span>
              ) },
            ]}
          />
        )}
      </div>

      {showStart && <StartModal onClose={() => setShowStart(false)} onStart={p => startMutation.mutate(p)} isPending={startMutation.isPending} />}
      {showStop  && <StopModal  currentTimer={currentTimer} elapsed={elapsed} onClose={() => setShowStop(false)} onStop={p => stopMutation.mutate(p)} onCancelTimer={() => cancelMutation.mutate()} pendingAction={stopPendingAction} />}
    </PageShell>
  )
}
