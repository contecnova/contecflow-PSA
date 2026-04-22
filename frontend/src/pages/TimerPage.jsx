/**
 * Timer Page — Seguimiento de tiempo con cronómetro activo e historial
 */
import { useState, useEffect, useRef } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import api from '../services/api'
import PageHeader from '../components/layout/PageHeader'
import { useToast } from '../context/ToastContext'
import { useAuth } from '../context/AuthContext'
import { useAppT } from '../i18n/AppLangContext'
import { useOnlineStatus } from '../hooks/useOnlineStatus'

const FS = {
  width: '100%', background: 'var(--surface-3)', border: '1px solid var(--surface-4)',
  borderRadius: 8, padding: '9px 12px', color: 'var(--text-1)', fontSize: 13,
  outline: 'none', fontFamily: 'inherit', boxSizing: 'border-box',
}
const LS = {
  fontSize: 11, fontWeight: 700, color: 'var(--text-3)', textTransform: 'uppercase',
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

function StartModal({ onClose, onStart, isPending, user }) {
  const [projectId, setProjectId] = useState('')
  const [taskId,    setTaskId]    = useState('')
  const [billable,  setBillable]  = useState(true)

  const hasRate = user?.hourly_rate && user.hourly_rate > 0

  const { data: projects = [] } = useQuery({
    queryKey: ['projects-list-timer'],
    queryFn: () => api.get('/projects?page_size=200&status=active').then(r =>
      Array.isArray(r.data) ? r.data : (r.data.items || [])
    ),
    enabled: hasRate,
  })

  const { data: tasks = [] } = useQuery({
    queryKey: ['tasks-for-project-timer', projectId],
    // assigned_to_me=true → backend filters to current user's assigned tasks only
    queryFn: () => api.get(`/tasks?project_id=${projectId}&assigned_to_me=true&page_size=200`).then(r =>
      Array.isArray(r.data) ? r.data : (r.data.items || [])
    ),
    enabled: !!projectId && hasRate,
  })

  return (
    <div style={{
      position: 'fixed', inset: 0, zIndex: 500,
      background: 'rgba(0,0,0,0.55)', backdropFilter: 'blur(3px)',
      display: 'flex', alignItems: 'center', justifyContent: 'center',
    }} onClick={onClose}>
      <div style={{
        background: 'var(--surface-1)', border: '1px solid var(--surface-4)',
        borderRadius: 14, padding: 28, width: 440, maxWidth: '95vw',
        boxShadow: '0 24px 64px rgba(0,0,0,0.5)',
      }} onClick={e => e.stopPropagation()}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 22 }}>
          <div>
            <div style={{ fontSize: 16, fontWeight: 700, color: 'var(--text-1)' }}>⏱ Iniciar cronómetro</div>
            <div style={{ fontSize: 12, color: 'var(--text-3)', marginTop: 2 }}>Selecciona proyecto y tarea</div>
          </div>
          <button onClick={onClose} style={{ background: 'none', border: 'none', color: 'var(--text-3)', cursor: 'pointer', fontSize: 20 }}>✕</button>
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
        <label style={{ display: 'flex', alignItems: 'center', gap: 10, cursor: 'pointer', marginBottom: 22, fontSize: 13, color: 'var(--text-1)' }}>
          <input type="checkbox" checked={billable} onChange={e => setBillable(e.target.checked)}
            style={{ width: 16, height: 16, accentColor: 'var(--accent)', cursor: 'pointer' }} />
          Tiempo facturable
        </label>
        {!hasRate && (
          <div style={{
            background: 'rgba(252,129,129,0.12)', border: '1px solid #fc8181',
            borderRadius: 8, padding: '10px 14px', marginBottom: 16,
            fontSize: 12, color: '#fc8181', lineHeight: 1.5,
          }}>
            ⚠ No tienes tarifa horaria asignada. No puedes iniciar el cronómetro hasta que Recursos Humanos la configure.
          </div>
        )}
        <div style={{ display: 'flex', gap: 10 }}>
          <button disabled={!projectId || isPending || !hasRate}
            onClick={() => onStart({ project_id: projectId, task_id: taskId || null, is_billable: billable })}
            style={{
              flex: 1, padding: '11px', background: 'var(--accent)', border: 'none',
              borderRadius: 9, color: '#fff', fontSize: 13, fontWeight: 700,
              cursor: (projectId && hasRate) ? 'pointer' : 'not-allowed', fontFamily: 'inherit',
              opacity: (!projectId || isPending || !hasRate) ? 0.6 : 1,
              display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 8,
            }}>
            {isPending ? '▶ Iniciando…' : '▶ Iniciar'}
          </button>
          <button onClick={onClose} style={{
            padding: '11px 18px', background: 'var(--surface-3)', border: '1px solid var(--surface-4)',
            borderRadius: 9, color: 'var(--text-2)', fontSize: 13, cursor: 'pointer', fontFamily: 'inherit',
          }}>Cancelar</button>
        </div>
      </div>
    </div>
  )
}

function StopModal({ onClose, onStop, isPending, elapsed }) {
  const [description, setDescription] = useState('')
  const [billable, setBillable] = useState(true)
  return (
    <div style={{
      position: 'fixed', inset: 0, zIndex: 500,
      background: 'rgba(0,0,0,0.55)', backdropFilter: 'blur(3px)',
      display: 'flex', alignItems: 'center', justifyContent: 'center',
    }} onClick={onClose}>
      <div style={{
        background: 'var(--surface-1)', border: '1px solid var(--surface-4)',
        borderRadius: 14, padding: 28, width: 420, maxWidth: '95vw',
        boxShadow: '0 24px 64px rgba(0,0,0,0.5)',
      }} onClick={e => e.stopPropagation()}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 18 }}>
          <div>
            <div style={{ fontSize: 16, fontWeight: 700, color: 'var(--text-1)' }}>⏹ Detener sesión</div>
            <div style={{ fontSize: 12, color: 'var(--text-3)', marginTop: 2 }}>
              Tiempo: <strong style={{ color: 'var(--accent)', fontFamily: 'monospace' }}>{formatTime(elapsed)}</strong>
            </div>
          </div>
          <button onClick={onClose} style={{ background: 'none', border: 'none', color: 'var(--text-3)', cursor: 'pointer', fontSize: 20 }}>✕</button>
        </div>
        <div style={{ marginBottom: 14 }}>
          <label style={LS}>Descripción del trabajo</label>
          <textarea value={description} onChange={e => setDescription(e.target.value)}
            style={{ ...FS, resize: 'vertical' }} rows={3}
            placeholder="Describe el trabajo realizado" aria-label="Descripcion del trabajo" autoFocus />
        </div>
        <label style={{ display: 'flex', alignItems: 'center', gap: 10, cursor: 'pointer', marginBottom: 22, fontSize: 13, color: 'var(--text-1)' }}>
          <input type="checkbox" checked={billable} onChange={e => setBillable(e.target.checked)}
            style={{ width: 16, height: 16, accentColor: 'var(--accent)', cursor: 'pointer' }} />
          Marcar como facturable
        </label>
        <div style={{ display: 'flex', gap: 10 }}>
          <button disabled={isPending}
            onClick={() => onStop({ description: description || 'Sesión de trabajo', is_billable: billable })}
            style={{
              flex: 1, padding: '11px', background: '#c0392b', border: 'none',
              borderRadius: 9, color: '#fff', fontSize: 13, fontWeight: 700,
              cursor: 'pointer', fontFamily: 'inherit', opacity: isPending ? 0.6 : 1,
              display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 8,
            }}>
            {isPending ? 'Guardando…' : '⏹ Guardar y cerrar'}
          </button>
          <button onClick={onClose} style={{
            padding: '11px 18px', background: 'var(--surface-3)', border: '1px solid var(--surface-4)',
            borderRadius: 9, color: 'var(--text-2)', fontSize: 13, cursor: 'pointer', fontFamily: 'inherit',
          }}>Cancelar</button>
        </div>
      </div>
    </div>
  )
}

export default function TimerPage() {
  const { user } = useAuth()
  const t       = useAppT()
  const toast   = useToast()
  const qc      = useQueryClient()
  const [elapsed,    setElapsed]   = useState(0)
  const [showStart,  setShowStart] = useState(false)
  const [showStop,   setShowStop]  = useState(false)
  const intervalRef = useRef(null)

  const { data: currentTimer } = useQuery({
    queryKey: ['timer-current'],
    queryFn: () => api.get('/imputations/timer/current').then(r => r.data),
    refetchInterval: 30_000,
  })

  const { data: timerHistory = [] } = useQuery({
    queryKey: ['timer-history'],
    queryFn: () => api.get('/imputations?page_size=50').then(r => {
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
    mutationFn: (p) => api.post('/imputations/timer/start', p).then(r => r.data),
    onSuccess: (data) => { toast.success('Cronómetro iniciado'); qc.setQueryData(['timer-current'], data); setShowStart(false) },
    onError: (e) => toast.error(e?.response?.data?.detail || 'Error al iniciar'),
  })
  const pauseMutation = useMutation({
    mutationFn: () => api.post('/imputations/timer/pause').then(r => r.data),
    onSuccess: (data) => { toast.success('Cronómetro pausado'); qc.setQueryData(['timer-current'], data) },
    onError: (e) => toast.error(e?.response?.data?.detail || 'Error al pausar'),
  })
  const resumeMutation = useMutation({
    mutationFn: () => api.post('/imputations/timer/resume').then(r => r.data),
    onSuccess: (data) => { toast.success('Cronómetro reanudado'); qc.setQueryData(['timer-current'], data) },
    onError: (e) => toast.error(e?.response?.data?.detail || 'Error al reanudar'),
  })
  const stopMutation = useMutation({
    mutationFn: (p) => api.post('/imputations/timer/stop', p).then(r => r.data),
    onSuccess: () => {
      toast.success('Sesión guardada como imputación')
      qc.setQueryData(['timer-current'], null)
      qc.invalidateQueries({ queryKey: ['timer-history'] })
      setShowStop(false); setElapsed(0)
    },
    onError: (e) => toast.error(e?.response?.data?.detail || 'Error al detener'),
  })

  const isPaused  = !!currentTimer?.paused_at
  const isRunning = !!currentTimer && !isPaused
  const isLoading = pauseMutation.isPending || resumeMutation.isPending || stopMutation.isPending
  const stateColor = isRunning ? '#68d391' : isPaused ? '#f6ad55' : 'var(--text-3)'
  const stateLabel = isRunning ? 'Corriendo' : isPaused ? 'Pausado' : 'Sin sesión'
  const isOnline = useOnlineStatus()

  return (
    <div style={{ padding: 32, maxWidth: 860, margin: '0 auto' }}>
      {!isOnline && (
        <div style={{
          background: '#744210', border: '1px solid #d69e2e', borderRadius: 10,
          padding: '10px 16px', marginBottom: 16, color: '#fefcbf',
          fontSize: 13, fontWeight: 600, display: 'flex', alignItems: 'center', gap: 8,
        }}>
          ⚠️ Sin conexión — los registros de tiempo se guardarán automáticamente cuando recuperes internet.
        </div>
      )}
      <PageHeader
        title={t('timer.title')}
        subtitle={t('timer.subtitle')}
        actions={!currentTimer && (
          <button onClick={() => setShowStart(true)} style={{
            padding: '9px 20px', background: 'var(--accent)', border: 'none',
            borderRadius: 9, color: '#fff', fontSize: 13, fontWeight: 700,
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
            <span style={{ fontSize: 11, fontWeight: 700, color: stateColor, textTransform: 'uppercase', letterSpacing: '0.1em' }}>
              {stateLabel}
            </span>
          </div>

          <div style={{ fontSize: 13, color: 'var(--text-2)', fontWeight: 600 }}>
            📁 {currentTimer.project_name || `Proyecto #${currentTimer.project_id}`}
            {currentTimer.task_id && (
              <span style={{ marginLeft: 12, fontSize: 12, color: 'var(--text-3)' }}>
                · Tarea #{currentTimer.task_id}
              </span>
            )}
          </div>

          <div style={{
            fontSize: 80, fontWeight: 800,
            fontFamily: '"Roboto Mono","Courier New",monospace',
            color: 'var(--text-1)', letterSpacing: 4, lineHeight: 1,
            textShadow: isRunning ? `0 0 40px ${stateColor}55` : 'none',
          }}>
            {formatTime(elapsed)}
          </div>

          <div style={{ fontSize: 12, color: 'var(--text-3)' }}>
            Inicio: {new Date(currentTimer.started_at).toLocaleTimeString('es-ES', { hour: '2-digit', minute: '2-digit', second: '2-digit' })}
            {(currentTimer.paused_duration_secs || 0) > 0 && (
              <span style={{ marginLeft: 14 }}>· Pausado acumulado: {formatTime(currentTimer.paused_duration_secs)}</span>
            )}
          </div>

          <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap', justifyContent: 'center' }}>
            {isPaused ? (
              <button onClick={() => resumeMutation.mutate()} disabled={isLoading} style={{
                padding: '12px 28px', background: 'var(--accent)', border: 'none',
                borderRadius: 10, color: '#fff', fontSize: 14, fontWeight: 700,
                cursor: isLoading ? 'not-allowed' : 'pointer', fontFamily: 'inherit',
                opacity: isLoading ? 0.6 : 1,
              }}>▶ Reanudar</button>
            ) : (
              <button onClick={() => pauseMutation.mutate()} disabled={isLoading} style={{
                padding: '12px 28px', background: '#d97706', border: 'none',
                borderRadius: 10, color: '#fff', fontSize: 14, fontWeight: 700,
                cursor: isLoading ? 'not-allowed' : 'pointer', fontFamily: 'inherit',
                opacity: isLoading ? 0.6 : 1,
              }}>⏸ Pausar</button>
            )}
            <button onClick={() => setShowStop(true)} disabled={isLoading} style={{
              padding: '12px 28px', background: '#c0392b', border: 'none',
              borderRadius: 10, color: '#fff', fontSize: 14, fontWeight: 700,
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
          <div style={{ fontSize: 56, opacity: 0.3 }}>⏱</div>
          <div style={{ fontSize: 18, fontWeight: 700, color: 'var(--text-1)' }}>Sin sesión activa</div>
          <div style={{ fontSize: 13, color: 'var(--text-3)', maxWidth: 360, lineHeight: 1.7 }}>
            Inicia el cronómetro para registrar tiempo automáticamente. Al detenerlo se creará una imputación.
          </div>
          <button onClick={() => setShowStart(true)} style={{
            marginTop: 8, padding: '12px 32px', background: 'var(--accent)', border: 'none',
            borderRadius: 10, color: '#fff', fontSize: 14, fontWeight: 700,
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
          <div style={{ fontSize: 14, fontWeight: 700, color: 'var(--text-1)' }}>Historial de sesiones</div>
          <div style={{ fontSize: 12, color: 'var(--text-3)' }}>
            {timerHistory.length} sesión{timerHistory.length !== 1 ? 'es' : ''}
          </div>
        </div>
        {timerHistory.length === 0 ? (
          <div style={{ padding: 40, textAlign: 'center', color: 'var(--text-3)', fontSize: 13 }}>
            No hay sesiones registradas todavía
          </div>
        ) : (
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
            <thead>
              <tr style={{ background: 'var(--surface-3)' }}>
                {['Proyecto', 'Descripción', 'Horas', 'Tipo', 'Fecha'].map(h => (
                  <th key={h} style={{
                    padding: '10px 16px', textAlign: 'left',
                    fontSize: 11, fontWeight: 700, color: 'var(--text-3)',
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
                  <td style={{ padding: '12px 16px', color: 'var(--text-1)', fontWeight: 600, fontFamily: 'monospace' }}>
                    {typeof s.hours === 'number' ? s.hours.toFixed(2) : (s.hours_imputed?.toFixed(2) || '—')}h
                  </td>
                  <td style={{ padding: '12px 16px' }}>
                    <span style={{
                      display: 'inline-flex', alignItems: 'center',
                      padding: '3px 10px', borderRadius: 20, fontSize: 11, fontWeight: 700,
                      background: s.is_billable ? 'rgba(104,211,145,0.15)' : 'rgba(113,128,150,0.15)',
                      color: s.is_billable ? '#68d391' : 'var(--text-3)',
                    }}>
                      {s.is_billable ? '💰 Facturable' : '🔧 Interno'}
                    </span>
                  </td>
                  <td style={{ padding: '12px 16px', color: 'var(--text-3)', fontSize: 12 }}>
                    {s.created_at ? new Date(s.created_at).toLocaleDateString('es-ES', { day: '2-digit', month: 'short', year: 'numeric' }) : '—'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {showStart && <StartModal onClose={() => setShowStart(false)} onStart={p => startMutation.mutate(p)} isPending={startMutation.isPending} user={user} />}
      {showStop  && <StopModal  elapsed={elapsed} onClose={() => setShowStop(false)} onStop={p => stopMutation.mutate(p)} isPending={stopMutation.isPending} />}

      <style>{`
        @keyframes timerPulse {
          0%, 100% { opacity: 1; transform: scale(1); }
          50% { opacity: 0.3; transform: scale(0.8); }
        }
      `}</style>
    </div>
  )
}
