/**
 * Timer Page — Seguimiento de tiempo con cronómetro activo e historial
 */
import { useState, useEffect, useRef } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { imputationsApi, projectsApi, tasksApi } from '../services/api'
import PageHeader from '../components/layout/PageHeader'
import PageShell from '../components/layout/PageShell'
import { Timer } from 'lucide-react'
import { useToast } from '../context/ToastContext'
import { useAppT } from '../i18n/AppLangContext'
import { useOnlineStatus } from '../hooks/useOnlineStatus'
import { DEFAULT_PAGE_SIZE, LARGE_PAGE_SIZE, NOTIFICATIONS_POLL_MS, STALE_5_MIN_MS } from '../constants/timings'

const FS = {
  width: '100%', background: 'var(--surface-3)', border: '1px solid var(--surface-4)',
  borderRadius: 8, padding: '9px 12px', color: 'var(--text-1)', fontSize: "var(--text-base)",
  outline: 'none', fontFamily: 'inherit', boxSizing: 'border-box',
}
const LS = {
  fontSize: "var(--text-xs)", fontWeight: 700, color: 'var(--text-3)', textTransform: 'uppercase',
  letterSpacing: '0.07em', display: 'block', marginBottom: 5,
}

function formatTime(seconds) {
  const h = Math.floor(seconds / 3600)
  const m = Math.floor((seconds % 3600) / 60)
  const s = seconds % 60
  return String(h).padStart(2,'0')+':'+String(m).padStart(2,'0')+':'+String(s).padStart(2,'0')
}

function computeElapsed(timer) {
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
    return Math.max(0, Math.floor((new Date(pausedStr) - startedAt) / 1000) - totalPausedSecs)
  }
  return Math.max(0, Math.floor((Date.now() - startedAt) / 1000) - totalPausedSecs)
}

function _onKeyboardActivate(event, action) {
  if (event.key === 'Enter' || event.key === ' ') {
    event.preventDefault()
    action()
  }
}

function StartModal({ onClose, onStart, isPending }) {
  const [projectId, setProjectId] = useState('')
  const [taskId,    setTaskId]    = useState('')
  const [billable,  setBillable]  = useState(true)

  const { data: projects = [] } = useQuery({
    queryKey: ['projects-list-timer'],
    queryFn: () => projectsApi.list({ page_size: LARGE_PAGE_SIZE, status: 'active' }).then(r =>
      Array.isArray(r.data) ? r.data : (r.data.items || [])
    ),
  })

  const { data: tasks = [] } = useQuery({
    queryKey: ['tasks-for-project-timer', projectId],
    queryFn: () => tasksApi.list({ project_id: projectId, assigned_to_me: true, page_size: LARGE_PAGE_SIZE }).then(r =>
      Array.isArray(r.data) ? r.data : (r.data.items || [])
    ),
    enabled: !!projectId,
  })

  return (
    <>
      <div role="presentation" onMouseDown={onClose} style={{
        position: 'fixed', inset: 0, zIndex: 499,
        background: 'rgba(0,0,0,0.55)', backdropFilter: 'blur(3px)',
      }} />
      <div style={{
        position: 'fixed', inset: 0, zIndex: 500,
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        pointerEvents: 'none',
      }}>
      <div role="dialog" aria-modal="true" aria-labelledby="start-timer-title"
        onKeyDown={e => { if (e.key === 'Escape') onClose() }}
        tabIndex={-1}
        style={{
        background: 'var(--surface-1)', border: '1px solid var(--surface-4)',
        borderRadius: 14, padding: 28, width: 440, maxWidth: '95vw',
        boxShadow: '0 24px 64px rgba(0,0,0,0.5)',
        pointerEvents: 'all',
      }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 22 }}>
          <div>
            <div id="start-timer-title" style={{ fontSize: "var(--text-lg)", fontWeight: 700, color: 'var(--text-1)' }}>⏱ Iniciar cronómetro</div>
            <div style={{ fontSize: "var(--text-sm)", color: 'var(--text-3)', marginTop: 2 }}>Selecciona proyecto y tarea</div>
          </div>
          <button onClick={onClose} style={{ background: 'none', border: 'none', color: 'var(--text-3)', cursor: 'pointer', fontSize: "var(--text-xl)" }}>✕</button>
        </div>
        <div style={{ marginBottom: 14 }}>
          <label style={LS}>Proyecto *</label>
          <select value={projectId} onChange={e => { setProjectId(e.target.value); setTaskId('') }} style={FS}>
            <option value="">— Selecciona un proyecto —</option>
            {projects.map(p => <option key={p.id} value={p.id}>{p.name}</option>)}
          </select>
        </div>
        <div style={{ marginBottom: 14 }}>
          <label style={LS}>Tarea (opcional)</label>
          <select value={taskId} onChange={e => setTaskId(e.target.value)}
            style={{ ...FS, opacity: projectId ? 1 : 0.5 }} disabled={!projectId}>
            <option value="">— Sin tarea —</option>
            {tasks.map(t => <option key={t.id} value={t.id}>{t.title || t.name}</option>)}
          </select>
        </div>
        <label style={{ display: 'flex', alignItems: 'center', gap: 10, cursor: 'pointer', marginBottom: 22, fontSize: "var(--text-base)", color: 'var(--text-1)' }}>
          <input type="checkbox" checked={billable} onChange={e => setBillable(e.target.checked)}
            style={{ width: 16, height: 16, accentColor: 'var(--accent)', cursor: 'pointer' }} />
          Tiempo facturable
        </label>
        <div style={{ display: 'flex', gap: 10 }}>
          <button disabled={!projectId || isPending}
            onClick={() => onStart({ project_id: projectId, task_id: taskId || null, is_billable: billable })}
            style={{
              flex: 1, padding: '11px', background: 'var(--accent)', border: 'none',
              borderRadius: 9, color: '#fff', fontSize: "var(--text-base)", fontWeight: 700,
              cursor: projectId ? 'pointer' : 'not-allowed', fontFamily: 'inherit',
              opacity: (!projectId || isPending) ? 0.6 : 1,
              display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 8,
            }}>
            {isPending ? '▶ Iniciando…' : '▶ Iniciar'}
          </button>
          <button onClick={onClose} style={{
            padding: '11px 18px', background: 'var(--surface-3)', border: '1px solid var(--surface-4)',
            borderRadius: 9, color: 'var(--text-2)', fontSize: "var(--text-base)", cursor: 'pointer', fontFamily: 'inherit',
          }}>Cancelar</button>
        </div>
      </div>
      </div>
    </>
  )
}

function StopModal({ currentTimer, onClose, onStop, onCancelTimer, pendingAction, elapsed }) {
  const [description, setDescription] = useState('')
  const [billable, setBillable] = useState(true)
  const [taskId, setTaskId] = useState(currentTimer?.task_id || '')
  const [forceDuplicate, setForceDuplicate] = useState(false)

  useEffect(() => {
    setTaskId(currentTimer?.task_id || '')
    setForceDuplicate(false)
  }, [currentTimer?.id, currentTimer?.task_id])

  const { data: tasks = [] } = useQuery({
    queryKey: ['tasks-for-stop-timer', currentTimer?.project_id, 'mine'],
    queryFn: () => tasksApi.list({ project_id: currentTimer?.project_id, assigned_to_me: true, page_size: LARGE_PAGE_SIZE }).then(r =>
      Array.isArray(r.data) ? r.data : (r.data.items || [])
    ),
    enabled: !!currentTimer?.project_id,
  })

  const isSaving = pendingAction === 'stop'
  const isCancelling = pendingAction === 'cancel'
  const isBusy = pendingAction !== null

  return (
    <>
      <div role="presentation" onMouseDown={onClose} style={{
        position: 'fixed', inset: 0, zIndex: 499,
        background: 'rgba(0,0,0,0.55)', backdropFilter: 'blur(3px)',
      }} />
      <div style={{
        position: 'fixed', inset: 0, zIndex: 500,
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        pointerEvents: 'none',
      }}>
      <div role="dialog" aria-modal="true" aria-labelledby="stop-timer-title"
        onKeyDown={e => { if (e.key === 'Escape') onClose() }}
        tabIndex={-1}
        style={{
        background: 'var(--surface-1)', border: '1px solid var(--surface-4)',
        borderRadius: 14, padding: 28, width: 420, maxWidth: '95vw',
        boxShadow: '0 24px 64px rgba(0,0,0,0.5)',
        pointerEvents: 'all',
      }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 18 }}>
          <div>
            <div id="stop-timer-title" style={{ fontSize: "var(--text-lg)", fontWeight: 700, color: 'var(--text-1)' }}>⏹ Detener sesión</div>
            <div style={{ fontSize: "var(--text-sm)", color: 'var(--text-3)', marginTop: 2 }}>
              Tiempo: <strong style={{ color: 'var(--accent)', fontFamily: 'var(--font-mono)' }}>{formatTime(elapsed)}</strong>
            </div>
          </div>
          <button onClick={onClose} style={{ background: 'none', border: 'none', color: 'var(--text-3)', cursor: 'pointer', fontSize: "var(--text-xl)" }}>✕</button>
        </div>
        <div style={{ marginBottom: 14 }}>
          <label style={LS}>Descripción del trabajo</label>
          <textarea value={description} onChange={e => setDescription(e.target.value)}
            style={{ ...FS, resize: 'vertical' }} rows={3}
            placeholder="Describe el trabajo realizado" aria-label="Descripcion del trabajo" autoFocus />
        </div>
        <div style={{ marginBottom: 14 }}>
          <label style={LS}>Tarea final</label>
          <select value={taskId} onChange={e => setTaskId(e.target.value)} style={FS} aria-label="Tarea final">
            <option value="">— Sin tarea —</option>
            {tasks.map(task => <option key={task.id} value={task.id}>{task.title || task.name}</option>)}
          </select>
          <div style={{ marginTop: 6, fontSize: "var(--text-xs)", color: 'var(--text-3)', lineHeight: 1.5 }}>
            Si ya existe una imputación para esa tarea y fecha, selecciona otra tarea o activa el guardado forzado.
          </div>
        </div>
        <label style={{ display: 'flex', alignItems: 'center', gap: 10, cursor: 'pointer', marginBottom: 22, fontSize: "var(--text-base)", color: 'var(--text-1)' }}>
          <input type="checkbox" checked={billable} onChange={e => setBillable(e.target.checked)}
            style={{ width: 16, height: 16, accentColor: 'var(--accent)', cursor: 'pointer' }} />
          Marcar como facturable
        </label>
        <label style={{ display: 'flex', alignItems: 'flex-start', gap: 10, cursor: 'pointer', marginBottom: 22, fontSize: "var(--text-sm)", color: 'var(--text-2)', lineHeight: 1.5 }}>
          <input type="checkbox" checked={forceDuplicate} onChange={e => setForceDuplicate(e.target.checked)}
            style={{ width: 16, height: 16, accentColor: 'var(--warning)', cursor: 'pointer', marginTop: 2 }} />
          <span>Permitir imputación duplicada y avisar al manager para revisión si ya existe una en la misma tarea y fecha.</span>
        </label>
        <div style={{ display: 'grid', gap: 10 }}>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
          <button disabled={isBusy}
            onClick={() => onStop({ description: description || 'Sesión de trabajo', is_billable: billable, task_id: taskId || null, force_duplicate: forceDuplicate })}
            style={{
              padding: '11px', background: 'var(--danger)', border: 'none',
              borderRadius: 9, color: '#fff', fontSize: "var(--text-base)", fontWeight: 700,
              cursor: 'pointer', fontFamily: 'inherit', opacity: isBusy ? 0.6 : 1,
              display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 8,
            }}>
            {isSaving ? 'Guardando…' : '⏹ Guardar y cerrar'}
          </button>
          <button onClick={onClose} style={{
            padding: '11px 18px', background: 'var(--surface-3)', border: '1px solid var(--surface-4)',
            borderRadius: 9, color: 'var(--text-2)', fontSize: "var(--text-base)", cursor: 'pointer', fontFamily: 'inherit',
          }}>Cancelar</button>
          </div>
          <button disabled={isBusy} onClick={onCancelTimer} style={{
            padding: '11px 18px', width: '100%', background: 'rgba(255,71,87,0.14)', border: '1px solid rgba(255,71,87,0.35)',
            borderRadius: 9, color: 'var(--danger)', fontSize: "var(--text-base)", cursor: 'pointer', fontFamily: 'inherit',
            opacity: isBusy ? 0.6 : 1,
          }}>{isCancelling ? 'Cancelando…' : '🗑 Cancelar cronómetro'}</button>
        </div>
      </div>
      </div>
    </>
  )
}

export default function TimerPage() {
  const t       = useAppT()
  const toast   = useToast()
  const qc      = useQueryClient()
  const [elapsed,    setElapsed]   = useState(0)
  const [showStart,  setShowStart] = useState(false)
  const [showStop,   setShowStop]  = useState(false)
  const intervalRef = useRef(null)

  const { data: currentTimer } = useQuery({
    queryKey: ['timer-current'],
    queryFn: () => imputationsApi.timerCurrent().then(r => r.data),
    refetchInterval: NOTIFICATIONS_POLL_MS,
  })

  const { data: timerProject } = useQuery({
    queryKey: ['timer-current-project', currentTimer?.project_id],
    queryFn: () => projectsApi.get(currentTimer.project_id).then(r => r.data),
    enabled: !!currentTimer?.project_id && !currentTimer?.project_name,
    staleTime: STALE_5_MIN_MS,
  })

  const { data: timerTask } = useQuery({
    queryKey: ['timer-current-task', currentTimer?.task_id],
    queryFn: () => tasksApi.get(currentTimer.task_id).then(r => r.data),
    enabled: !!currentTimer?.task_id && !currentTimer?.task_name,
    staleTime: STALE_5_MIN_MS,
  })

  const { data: timerHistory = [] } = useQuery({
    queryKey: ['timer-history'],
    queryFn: () => imputationsApi.list({ page_size: DEFAULT_PAGE_SIZE }).then(r => {
      const data = r.data
      const items = Array.isArray(data) ? data : (data.items || [])
      return items.filter(imp => imp.timer_session_id)
    }),
    refetchInterval: 60_000,
  })

  useEffect(() => {
    clearInterval(intervalRef.current)
    if (!currentTimer) { setElapsed(0); return }
    const tick = () => setElapsed(computeElapsed(currentTimer))
    tick()
    if (!currentTimer.paused_at) {
      intervalRef.current = setInterval(tick, 1000)
    }
    return () => clearInterval(intervalRef.current)
  }, [currentTimer])

  const startMutation = useMutation({
    mutationFn: (p) => imputationsApi.timerStart(p).then(r => r.data),
    onSuccess: (data) => { toast.success('Cronómetro iniciado'); qc.setQueryData(['timer-current'], data); setShowStart(false) },
    onError: (e) => toast.error(e?.response?.data?.detail || 'Error al iniciar'),
  })
  const pauseMutation = useMutation({
    mutationFn: () => imputationsApi.timerPause().then(r => r.data),
    onSuccess: (data) => { toast.success('Cronómetro pausado'); qc.setQueryData(['timer-current'], data) },
    onError: (e) => toast.error(e?.response?.data?.detail || 'Error al pausar'),
  })
  const resumeMutation = useMutation({
    mutationFn: () => imputationsApi.timerResume().then(r => r.data),
    onSuccess: (data) => { toast.success('Cronómetro reanudado'); qc.setQueryData(['timer-current'], data) },
    onError: (e) => toast.error(e?.response?.data?.detail || 'Error al reanudar'),
  })
  const cancelMutation = useMutation({
    mutationFn: () => imputationsApi.timerCancel().then(r => r.data),
    onSuccess: () => {
      toast.success('Cronómetro cancelado')
      qc.setQueryData(['timer-current'], null)
      setShowStop(false)
      setElapsed(0)
    },
    onError: (e) => toast.error(e?.response?.data?.detail || 'Error al cancelar el cronómetro'),
  })
  const stopMutation = useMutation({
    mutationFn: (p) => imputationsApi.timerStop(p).then(r => r.data),
    onSuccess: () => {
      toast.success('Sesión guardada como imputación')
      qc.setQueryData(['timer-current'], null)
      qc.invalidateQueries({ queryKey: ['timer-history'] })
      qc.invalidateQueries(['my-week'])
      qc.invalidateQueries(['imputations-today'])
      qc.invalidateQueries(['dash-hours-week'])
      qc.invalidateQueries(['timesheets-mine'])
      qc.invalidateQueries(['timesheets-pending'])
      qc.invalidateQueries(['timesheets-team'])
      setShowStop(false); setElapsed(0)
    },
    onError: (e) => {
      const detail = e?.response?.data?.detail || 'Error al detener'
      toast.error(detail)
    },
  })

  const isPaused  = !!currentTimer?.paused_at
  const isRunning = !!currentTimer && !isPaused
  const isLoading = pauseMutation.isPending || resumeMutation.isPending || stopMutation.isPending || cancelMutation.isPending
  const stopPendingAction = stopMutation.isPending ? 'stop' : cancelMutation.isPending ? 'cancel' : null
  const stateColor = isRunning ? 'var(--success)' : isPaused ? 'var(--orange)' : 'var(--text-3)'
  const stateLabel = isRunning ? 'Corriendo' : isPaused ? 'Pausado' : 'Sin sesión'
  const isOnline = useOnlineStatus()
  const timerProjectLabel = currentTimer?.project_name || timerProject?.name || (currentTimer?.project_id ? `Proyecto #${currentTimer.project_id}` : '—')
  const timerTaskLabel = currentTimer?.task_name || timerTask?.title || timerTask?.name || (currentTimer?.task_id ? `Tarea #${currentTimer.task_id}` : null)

  return (
    <PageShell style={{ maxWidth: 860, margin: '0 auto' }}>
      {!isOnline && (
        <div style={{
          background: 'var(--warning-bg)', border: '1px solid var(--warning-border)', borderRadius: 10,
          padding: '10px 16px', marginBottom: 16, color: 'var(--warning)',
          fontSize: "var(--text-base)", fontWeight: 600, display: 'flex', alignItems: 'center', gap: 8,
        }}>
          ⚠️ Sin conexión — los registros de tiempo se guardarán automáticamente cuando recuperes internet.
        </div>
      )}
      <PageHeader
        icon={<Timer size={18} />}
        title={t('timer.title')}
        subtitle={t('timer.subtitle')}
        actions={!currentTimer && (
          <button onClick={() => setShowStart(true)} style={{
            padding: '9px 20px', background: 'var(--accent)', border: 'none',
            borderRadius: 9, color: '#fff', fontSize: "var(--text-base)", fontWeight: 700,
            cursor: 'pointer', fontFamily: 'inherit',
          }}>▶ Nueva sesión</button>
        )}
      />

      {currentTimer ? (
        <div style={{
          background: 'var(--surface-2)', border: '1px solid var(--surface-4)',
          borderRadius: 16, padding: 36, marginBottom: 24,
          borderLeft: `4px solid ${stateColor}`,
          display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 20,
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <span style={{
              width: 8, height: 8, borderRadius: '50%', background: stateColor,
              boxShadow: isRunning ? `0 0 10px ${stateColor}` : 'none',
              animation: isRunning ? 'timerPulse 1.5s ease-in-out infinite' : 'none',
            }} />
            <span style={{ fontSize: "var(--text-xs)", fontWeight: 700, color: stateColor, textTransform: 'uppercase', letterSpacing: '0.1em' }}>
              {stateLabel}
            </span>
          </div>

          <div style={{ fontSize: "var(--text-base)", color: 'var(--text-2)', fontWeight: 600 }}>
            📁 {timerProjectLabel}
            {currentTimer.task_id && (
              <span style={{ marginLeft: 12, fontSize: "var(--text-sm)", color: 'var(--text-3)' }}>
                · {timerTaskLabel}
              </span>
            )}
          </div>

          <div style={{
            fontSize: "var(--text-80)", fontWeight: 800,
            fontFamily: '"Roboto Mono","Courier New",monospace',
            color: 'var(--text-1)', letterSpacing: 4, lineHeight: 1,
            textShadow: isRunning ? `0 0 40px ${stateColor}55` : 'none',
          }}>
            {formatTime(elapsed)}
          </div>

          <div style={{ fontSize: "var(--text-sm)", color: 'var(--text-3)' }}>
            Inicio: {new Date(currentTimer.started_at).toLocaleTimeString('es-ES', { hour: '2-digit', minute: '2-digit', second: '2-digit' })}
            {(currentTimer.paused_duration_secs || 0) > 0 && (
              <span style={{ marginLeft: 14 }}>· Pausado acumulado: {formatTime(currentTimer.paused_duration_secs)}</span>
            )}
          </div>

          <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap', justifyContent: 'center' }}>
            {isPaused ? (
              <button onClick={() => resumeMutation.mutate()} disabled={isLoading} style={{
                padding: '12px 28px', background: 'var(--accent)', border: 'none',
                borderRadius: 10, color: '#fff', fontSize: "var(--text-md)", fontWeight: 700,
                cursor: isLoading ? 'not-allowed' : 'pointer', fontFamily: 'inherit',
                opacity: isLoading ? 0.6 : 1,
              }}>▶ Reanudar</button>
            ) : (
              <button onClick={() => pauseMutation.mutate()} disabled={isLoading} style={{
                padding: '12px 28px', background: 'var(--warning)', border: 'none',
                borderRadius: 10, color: '#fff', fontSize: "var(--text-md)", fontWeight: 700,
                cursor: isLoading ? 'not-allowed' : 'pointer', fontFamily: 'inherit',
                opacity: isLoading ? 0.6 : 1,
              }}>⏸ Pausar</button>
            )}
            <button onClick={() => setShowStop(true)} disabled={isLoading} style={{
              padding: '12px 28px', background: 'var(--danger)', border: 'none',
              borderRadius: 10, color: '#fff', fontSize: "var(--text-md)", fontWeight: 700,
              cursor: isLoading ? 'not-allowed' : 'pointer', fontFamily: 'inherit',
              opacity: isLoading ? 0.6 : 1,
            }}>⏹ Detener y guardar</button>
          </div>
        </div>
      ) : (
        <div style={{
          background: 'var(--surface-2)', border: '1px solid var(--surface-4)',
          borderRadius: 16, padding: 52, marginBottom: 24,
          display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 16, textAlign: 'center',
        }}>
          <div style={{ fontSize: "var(--text-56)", opacity: 0.3 }}>⏱</div>
          <div style={{ fontSize: "var(--text-lg-em)", fontWeight: 700, color: 'var(--text-1)' }}>Sin sesión activa</div>
          <div style={{ fontSize: "var(--text-base)", color: 'var(--text-3)', maxWidth: 360, lineHeight: 1.7 }}>
            Inicia el cronómetro para registrar tiempo automáticamente. Al detenerlo se creará una imputación.
          </div>
          <button onClick={() => setShowStart(true)} style={{
            marginTop: 8, padding: '12px 32px', background: 'var(--accent)', border: 'none',
            borderRadius: 10, color: '#fff', fontSize: "var(--text-md)", fontWeight: 700,
            cursor: 'pointer', fontFamily: 'inherit',
          }}>▶ Iniciar cronómetro</button>
        </div>
      )}

      <div style={{
        background: 'var(--surface-2)', border: '1px solid var(--surface-4)',
        borderRadius: 14, overflow: 'hidden',
      }}>
        <div style={{
          padding: '16px 20px', borderBottom: '1px solid var(--surface-4)',
          display: 'flex', alignItems: 'center', justifyContent: 'space-between',
        }}>
          <div style={{ fontSize: "var(--text-md)", fontWeight: 700, color: 'var(--text-1)' }}>Historial de sesiones</div>
          <div style={{ fontSize: "var(--text-sm)", color: 'var(--text-3)' }}>
            {timerHistory.length} sesión{timerHistory.length !== 1 ? 'es' : ''}
          </div>
        </div>
        {timerHistory.length === 0 ? (
          <div style={{ padding: 40, textAlign: 'center', color: 'var(--text-3)', fontSize: "var(--text-base)" }}>
            No hay sesiones registradas todavía
          </div>
        ) : (
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: "var(--text-base)" }}>
            <thead>
              <tr style={{ background: 'var(--surface-3)' }}>
                {['Proyecto', 'Descripción', 'Horas', 'Tipo', 'Fecha'].map(h => (
                  <th key={h} style={{
                    padding: '10px 16px', textAlign: 'left',
                    fontSize: "var(--text-xs)", fontWeight: 700, color: 'var(--text-3)',
                    textTransform: 'uppercase', letterSpacing: '0.06em',
                  }}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {timerHistory.map((s, i) => (
                <tr key={s.id} style={{ borderTop: '1px solid var(--surface-4)', background: i % 2 === 0 ? 'transparent' : 'var(--surface-3)' }}>
                  <td style={{ padding: '12px 16px', fontWeight: 600, color: 'var(--text-1)' }}>
                    {s.project?.name || s.project?.code || `Proyecto #${s.project?.id || '?'}`}
                  </td>
                  <td style={{ padding: '12px 16px', color: 'var(--text-2)', maxWidth: 200, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                    {s.description || '—'}
                  </td>
                  <td style={{ padding: '12px 16px', color: 'var(--text-1)', fontWeight: 600, fontFamily: 'var(--font-mono)' }}>
                    {typeof s.hours === 'number' ? s.hours.toFixed(2) : (s.hours_imputed?.toFixed(2) || '—')}h
                  </td>
                  <td style={{ padding: '12px 16px' }}>
                    <span style={{
                      display: 'inline-flex', alignItems: 'center',
                      padding: '3px 10px', borderRadius: 20, fontSize: "var(--text-xs)", fontWeight: 700,
                      background: s.is_billable ? 'rgba(104,211,145,0.15)' : 'rgba(113,128,150,0.15)',
                      color: s.is_billable ? 'var(--success)' : 'var(--text-3)',
                    }}>
                      {s.is_billable ? '💰 Facturable' : '🔧 Interno'}
                    </span>
                  </td>
                  <td style={{ padding: '12px 16px', color: 'var(--text-3)', fontSize: "var(--text-sm)" }}>
                    {s.created_at ? new Date(s.created_at).toLocaleDateString('es-ES', { day: '2-digit', month: 'short', year: 'numeric' }) : '—'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {showStart && <StartModal onClose={() => setShowStart(false)} onStart={p => startMutation.mutate(p)} isPending={startMutation.isPending} />}
      {showStop  && <StopModal  currentTimer={currentTimer} elapsed={elapsed} onClose={() => setShowStop(false)} onStop={p => stopMutation.mutate(p)} onCancelTimer={() => cancelMutation.mutate()} pendingAction={stopPendingAction} />}

      <style>{`
        @keyframes timerPulse {
          0%, 100% { opacity: 1; transform: scale(1); }
          50% { opacity: 0.3; transform: scale(0.8); }
        }
      `}</style>
    </PageShell>
  )
}
