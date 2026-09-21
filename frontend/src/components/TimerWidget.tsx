/**
 * TimerWidget — Cronómetro compacto (para usar en navbar u otros lugares)
 * Usa el api autenticado y el mismo cálculo de tiempo que TimerPage.
 */
import { useState, useEffect, useRef } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { imputationsApi, projectsApi } from '../services/api'
import { useAuth } from '../context/AuthContext'
import { useAppLang } from '../i18n/AppLangContext'

interface TimerState {
  paused_at?: string | null
  total_elapsed_seconds?: number | null
  started_at: string
  paused_duration_secs?: number | null
  project_name?: string | null
  project_id?: number | string | null
  task_id?: number | string | null
  task_name?: string | null
}

interface ProjectOption {
  id: number | string
  name: string
}

function extractErrorMessage(error: unknown): string {
  if (typeof error !== 'object' || error == null) return 'Error'
  const maybeResponse = error as { response?: { data?: { detail?: unknown } } }
  const raw = maybeResponse.response?.data?.detail
  if (Array.isArray(raw)) {
    return raw
      .map((item) => (typeof item === 'object' && item && 'msg' in item ? String((item as { msg: unknown }).msg) : String(item)))
      .join(', ')
  }
  return raw ? String(raw) : 'Error'
}

function normalizeProjects(data: unknown): ProjectOption[] {
  if (Array.isArray(data)) return data as ProjectOption[]
  if (typeof data === 'object' && data !== null && 'items' in data) {
    const items = (data as { items?: unknown }).items
    return Array.isArray(items) ? (items as ProjectOption[]) : []
  }
  return []
}

function fmt(s: number) {
  return String(Math.floor(s/3600)).padStart(2,'0')+':'+
         String(Math.floor((s%3600)/60)).padStart(2,'0')+':'+
         String(s%60).padStart(2,'0')
}

function calcElapsed(timer: TimerState | null) {
  if (!timer) return 0
  if (timer.paused_at && timer.total_elapsed_seconds != null) {
    return timer.total_elapsed_seconds
  }
  const startStr = timer.started_at.endsWith('Z') || timer.started_at.includes('+')
    ? timer.started_at : timer.started_at + 'Z'
  const start = new Date(startStr)
  const paused = timer.paused_duration_secs || 0
  if (timer.paused_at) {
    const pausedStr = timer.paused_at.endsWith('Z') || timer.paused_at.includes('+')
      ? timer.paused_at : timer.paused_at + 'Z'
    const pausedAt = new Date(pausedStr)
    return Math.max(0, Math.floor((pausedAt.getTime() - start.getTime()) / 1000) - paused)
  }
  return Math.max(0, Math.floor((Date.now() - start.getTime()) / 1000) - paused)
}

const TimerWidget = () => {
  const { t } = useAppLang()
  useAuth()
  const queryClient = useQueryClient()
  const [elapsed,   setElapsed]  = useState(0)
  const [projects,  setProjects] = useState<ProjectOption[]>([])
  const [projectId, setProjectId] = useState('')
  const [loading,   setLoading]  = useState(false)
  const [error,     setError]    = useState('')
  const tickRef = useRef<ReturnType<typeof setInterval> | null>(null)

  const { data: timer = null } = useQuery<TimerState | null>({
    queryKey: ['timer-current'],
    queryFn: () => imputationsApi.timerCurrent().then(r => r.data).catch(() => null),
    refetchInterval: 5_000,
    retry: false,
    staleTime: 1_000,
  })

  useEffect(() => {
    projectsApi.list({ page_size: 100 }).then(r => {
      setProjects(normalizeProjects(r.data))
    }).catch(() => {})
  }, [])

  useEffect(() => {
    if (tickRef.current) {
      clearInterval(tickRef.current)
      tickRef.current = null
    }
    if (!timer) { setElapsed(0); return }
    const tick = () => setElapsed(calcElapsed(timer))
    tick()
    if (!timer.paused_at) tickRef.current = setInterval(tick, 1000)
    return () => {
      if (tickRef.current) {
        clearInterval(tickRef.current)
        tickRef.current = null
      }
    }
  }, [timer])

  const call = async (fn: () => Promise<{ data?: TimerState | null }>, options: { syncTimerFromResponse?: boolean } = {}) => {
    const { syncTimerFromResponse = true } = options
    setLoading(true); setError('')
    try {
      const r = await fn()
      if (syncTimerFromResponse && r?.data !== undefined) {
        queryClient.setQueryData(['timer-current'], r.data || null)
      }
    }
    catch (e) { setError(extractErrorMessage(e)) }
    finally { setLoading(false) }
  }

  const stopTimer = () => call(async () => {
    const payload = { description: 'Sesión', is_billable: true }
    const response = await imputationsApi.timerStop(payload)
    queryClient.setQueryData(['timer-current'], null)
    return response
  }, { syncTimerFromResponse: false })

  const isPaused = !!timer?.paused_at
  const stateColor = timer && !isPaused ? 'var(--success)' : isPaused ? 'var(--warning)' : 'var(--text-3)'

  const btnStyle = (bg: string) => ({
    padding: '7px 14px', background: bg, border: 'none', borderRadius: 7,
    color: '#fff', fontSize: "var(--text-sm)", fontWeight: 700,
    cursor: loading ? 'not-allowed' : 'pointer',
    fontFamily: 'inherit', opacity: loading ? 0.6 : 1,
  })
  const selectStyle = {
    width: '100%', background: 'var(--surface-3)', border: '1px solid var(--surface-4)',
    borderRadius: 7, padding: '7px 10px', color: 'var(--text-1)', fontSize: "var(--text-sm)",
    outline: 'none', fontFamily: 'inherit', marginBottom: 8,
  }

  return (
    <div style={{
      background: 'var(--surface-2)', border: '1px solid var(--surface-4)',
      borderRadius: 10, padding: 12, minWidth: 220,
    }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 10 }}>
        <span style={{ width: 7, height: 7, borderRadius: '50%', background: stateColor }} />
        <span style={{ fontSize: "var(--text-xs)", fontWeight: 700, color: 'var(--text-2)' }}>
          {'\u23f1'} {t('timerwidget.cronometro')}
        </span>
      </div>

      {timer ? (
        <>
          <div style={{
            fontSize: "var(--text-3xl)", fontWeight: 800, fontFamily: 'var(--font-mono)',
            color: 'var(--text-1)', textAlign: 'center', marginBottom: 10, letterSpacing: 2,
          }}>
            {fmt(elapsed)}
          </div>
          <div style={{ fontSize: "var(--text-xs)", color: 'var(--text-3)', marginBottom: 10, textAlign: 'center' }}>
            {timer.project_name || `Proyecto #${timer.project_id}`}
            {timer.task_id && ` · ${timer.task_name || `Tarea #${timer.task_id}`}`}
          </div>
          <div style={{ display: 'flex', gap: 6 }}>
            {isPaused
              ? <button style={btnStyle('var(--accent)')} disabled={loading}
                  onClick={() => call(() => imputationsApi.timerResume())}>
                  {'\u25b6'} Reanudar
                </button>
              : <button style={btnStyle('var(--warning)')} disabled={loading}
                  onClick={() => call(() => imputationsApi.timerPause())}>
                  {'\u23f8'} Pausar
                </button>
            }
            <button style={btnStyle('var(--danger)')} disabled={loading}
              onClick={stopTimer}>
              {'\u23f9'}
            </button>
          </div>
        </>
      ) : (
        <>
          <>
            <select value={projectId} onChange={e => setProjectId(e.target.value)} style={selectStyle}>
              <option value="">— Proyecto —</option>
              {projects.map(p => <option key={String(p.id)} value={String(p.id)}>{p.name}</option>)}
            </select>
            <button
              disabled={!projectId || loading}
              onClick={() => call(() => imputationsApi.timerStart({ project_id: projectId }))}
              style={{ ...btnStyle('var(--accent)'), width: '100%', opacity: (!projectId || loading) ? 0.5 : 1 }}>
              {loading ? 'Iniciando…' : '▶ Iniciar'}
            </button>
          </>
        </>
      )}
      {error && <div style={{ fontSize: "var(--text-xs)", color: 'var(--danger)', marginTop: 6 }}>{'⚠'} {error}</div>}
    </div>
  )
}

export default TimerWidget
