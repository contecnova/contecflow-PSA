/**
 * Timer Page — Seguimiento de tiempo con cronómetro activo e historial
 *
 * 16-11-2026: título con el nombre del menú (nav.timer); botones con Button del
 * kit e iconos lucide (antes emojis en el texto); diálogos con
 * Modal y campos ds-input (antes diálogos y campos propios con fondo gris);
 * vacíos con EmptyState; tipo de sesión con StatusBadge; fecha con el
 * formateador de la app; sin ancho máximo centrado.
 */
import { useState, useEffect, useRef } from 'react'
import type { TaskListParams, TaskListItem } from '../services/api/tasks'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { imputationsApi, projectsApi, tasksApi } from '../services/api'
import type { Imputacion, SesionDeCronometro } from '../services/api/tipos-personas'
import { useAuth } from '../context/AuthContext'
import PageHeader from '../components/layout/PageHeader'
import PageShell from '../components/layout/PageShell'
import { Button, Card, EmptyState, FormField, Modal, Section, StatusBadge, Table, Select, Checkbox } from '../components/ui'
import { Timer, Play, Pause, Square, Trash2, FolderOpen, History, WifiOff } from 'lucide-react'
import { useToast } from '../context/ToastContext'
import { useAppT } from '../i18n/AppLangContext'
import { useOnlineStatus } from '../hooks/useOnlineStatus'
import { DEFAULT_PAGE_SIZE, LARGE_PAGE_SIZE, NOTIFICATIONS_POLL_MS, STALE_5_MIN_MS, POLL_DEFAULT_MS, CLOCK_TICK_MS } from '../constants/timings'
import { fmtDate, formateadorDeFecha } from '../utils/helpers'
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

function StartModal({ onClose, onStart, isPending }: {
  onClose: () => void
  onStart: (p: { project_id: string; task_id: string | null; is_billable: boolean }) => void
  isPending: boolean
}) {
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

  return (
    <Modal open onClose={onClose} size="sm"
      title={traducir('timer.iniciar_cronometro')}
      subtitle={traducir('timer.selecciona_proyecto_y_tarea')}>
      <div className="tm-form">
        <FormField label={traducir('timer.col_proyecto')} required>
          <Select suelto placeholder={false} value={projectId} onChange={e => { setProjectId(e.target.value); setTaskId('') }}>
            <option value="">{traducir('timer.selecciona_un_proyecto')}</option>
            {projects.map(p => <option key={p.id} value={p.id}>{p.name}</option>)}
          </Select>
        </FormField>
        <FormField label={traducir('timer.tarea_opcional')}>
          <Select suelto placeholder={false} value={taskId} onChange={e => setTaskId(e.target.value)} disabled={!projectId}>
            <option value="">{traducir('timer.sin_tarea')}</option>
            {tasks.map(t => <option key={t.id} value={t.id}>{t.title || (t as { name?: string }).name}</option>)}
          </Select>
        </FormField>
        <Checkbox className="tm-check" checked={!!billable} onChange={setBillable}
          label={traducir('timer.tiempo_facturable')} />
        <div className="tm-modal-actions">
          <Button variant="secondary" onClick={onClose}>{traducir('timer.cancelar')}</Button>
          <Button icon={<Play size={14} />} disabled={!projectId} loading={isPending}
            onClick={() => onStart({ project_id: projectId, task_id: taskId || null, is_billable: billable })}>
            {isPending ? traducir('timer.iniciando') : traducir('timer.iniciar')}
          </Button>
        </div>
      </div>
    </Modal>
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

  return (
    <Modal open onClose={onClose} size="sm"
      title={traducir('timer.detener_sesion')}
      subtitle={<>{traducir('timer.tiempo')}: <strong className="tm-elapsed-inline">{formatTime(elapsed)}</strong></>}>
      <div className="tm-form">
        <FormField label={traducir('timer.descripcion_del_trabajo')}>
          <textarea value={description} onChange={e => setDescription(e.target.value)}
            className="ds-input tm-textarea" rows={3}
            placeholder={traducir('timer.describe_el_trabajo_realizado')} autoFocus />
        </FormField>
        <FormField label={traducir('timer.tarea_final')} hint={traducir('timer.si_ya_existe_una_imputacion_para_esa')}>
          <Select suelto placeholder={false} value={taskId} onChange={e => setTaskId(e.target.value)}>
            <option value="">{traducir('timer.sin_tarea')}</option>
            {tasks.map(task => <option key={task.id} value={task.id}>{task.title || (task as { name?: string }).name}</option>)}
          </Select>
        </FormField>
        <Checkbox className="tm-check" checked={!!billable} onChange={setBillable}
          label={traducir('timer.marcar_como_facturable')} />
        <Checkbox className="tm-check tm-check--top" checked={!!forceDuplicate} onChange={setForceDuplicate}
          label={traducir('timer.permitir_imputacion_duplicada_y_avisar_al_manager')} />
        <div className="tm-modal-actions tm-modal-actions--split">
          <Button variant="danger" icon={<Trash2 size={14} />} disabled={isBusy && !isCancelling} loading={isCancelling} onClick={onCancelTimer}>
            {isCancelling ? traducir('timer.cancelando') : traducir('timer.cancelar_cronometro')}
          </Button>
          <div className="tm-modal-actions">
            <Button variant="secondary" onClick={onClose}>{traducir('timer.cancelar')}</Button>
            <Button icon={<Square size={14} />} disabled={isBusy && !isSaving} loading={isSaving}
              onClick={() => onStop({ description: description || traducir('timer.sesion_de_trabajo'), is_billable: billable, task_id: taskId || null, force_duplicate: forceDuplicate })}>
              {isSaving ? traducir('timer.guardando') : traducir('timer.guardar_y_cerrar')}
            </Button>
          </div>
        </div>
      </div>
    </Modal>
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

  const horaInicio = formateadorDeFecha({ hour: '2-digit', minute: '2-digit', second: '2-digit' }).format(new Date(currentTimer?.started_at || Date.now()))

  return (
    <PageShell>
      <PageHeader
        icon={<Timer size={18} />}
        title={t('nav.timer')}
        subtitle={t('timer.subtitle')}
        showListExport={false}
        actions={!currentTimer && (
          <Button icon={<Play size={14} />} onClick={() => setShowStart(true)}>{traducir('timer.nueva_sesion')}</Button>
        )}
      />

      <div className="ds-page">
        {!isOnline && (
          <div className="tm-offline" role="status">
            <WifiOff size={15} aria-hidden="true" />
            <span>{traducir('timer.sin_conexion_los_registros_de_tiempo_se')}</span>
          </div>
        )}

        {currentTimer ? (
          <Card className={`tm-session ${stateClass}`}>
            <StatusBadge kind={isRunning ? 'success' : 'warning'} dot>{stateLabel}</StatusBadge>

            <div className="tm-session-project">
              <FolderOpen size={15} aria-hidden="true" />
              <span>{timerProjectLabel}</span>
              {currentTimer.task_id && (
                <span className="tm-session-task">· {timerTaskLabel}</span>
              )}
            </div>

            <div className="tm-clock" role="timer" aria-label={t('timer.elapsed')}>
              {formatTime(elapsed)}
            </div>

            <div className="tm-meta">
              {t('timer.inicio')}: {horaInicio}
              {(currentTimer.paused_duration_secs || 0) > 0 && (
                <span> · {t('timer.pausado_acumulado')}: {formatTime(currentTimer.paused_duration_secs ?? 0)}</span>
              )}
            </div>

            <div className="tm-controls">
              {isPaused ? (
                <Button size="lg" icon={<Play size={15} />} onClick={() => resumeMutation.mutate()} disabled={isLoading}>{t('timer.reanudar')}</Button>
              ) : (
                <Button size="lg" variant="secondary" icon={<Pause size={15} />} onClick={() => pauseMutation.mutate()} disabled={isLoading}>{t('timer.pausar')}</Button>
              )}
              <Button size="lg" icon={<Square size={15} />} onClick={() => setShowStop(true)} disabled={isLoading}>{t('timer.detener_y_guardar')}</Button>
            </div>
          </Card>
        ) : (
          <Card>
            <EmptyState icon={<Timer size={28} />}
              title={traducir('timer.sin_sesion_activa')}
              description={traducir('timer.inicia_el_cronometro_para_registrar_tiempo_automaticamente')}
              action={<Button icon={<Play size={14} />} onClick={() => setShowStart(true)}>{traducir('timer.iniciar_cronometro')}</Button>} />
          </Card>
        )}

        <Card>
          <Section title={traducir('timer.historial_de_sesiones')}
            actions={<span className="tm-count">{t(timerHistory.length === 1 ? 'timer.n_sesion_una' : 'timer.n_sesiones', { n: timerHistory.length })}</span>}>
            {timerHistory.length === 0 ? (
              <EmptyState icon={<History size={28} />}
                title={traducir('timer.no_hay_sesiones_registradas_todavia')}
                description={traducir('timer.historial_vacio_desc')} />
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
                    <StatusBadge kind={s.is_billable ? 'success' : 'neutral'} caps={false}>
                      {s.is_billable ? t('timer.facturable') : t('timer.interno')}
                    </StatusBadge>
                  ) },
                  { key: 'created_at', label: t('timer.col_fecha'), render: (_v, s) => (
                    <span className="tm-meta">{fmtDate(s.created_at)}</span>
                  ) },
                ]}
              />
            )}
          </Section>
        </Card>
      </div>

      {showStart && <StartModal onClose={() => setShowStart(false)} onStart={p => startMutation.mutate(p)} isPending={startMutation.isPending} />}
      {showStop  && <StopModal  currentTimer={currentTimer} elapsed={elapsed} onClose={() => setShowStop(false)} onStop={p => stopMutation.mutate(p)} onCancelTimer={() => cancelMutation.mutate()} pendingAction={stopPendingAction} />}
    </PageShell>
  )
}
