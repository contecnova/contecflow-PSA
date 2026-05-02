/**
 * TimerWidget — Cronómetro compacto (para usar en navbar u otros lugares)
 * Usa el api autenticado y el mismo cálculo de tiempo que TimerPage.
 */
import { useState, useEffect, useRef } from 'react'
import api from '../services/api'
import { useAuth } from '../context/AuthContext'

function fmt(s) {
  return String(Math.floor(s/3600)).padStart(2,'0')+':'+
         String(Math.floor((s%3600)/60)).padStart(2,'0')+':'+
         String(s%60).padStart(2,'0')
}

function calcElapsed(timer) {
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
    return Math.max(0, Math.floor((new Date(pausedStr) - start) / 1000) - paused)
  }
  return Math.max(0, Math.floor((Date.now() - start) / 1000) - paused)
}

const TimerWidget = () => {
  const { user } = useAuth()
  const hasRate = !!(user?.hourly_rate && user.hourly_rate > 0)
  const [timer,     setTimer]    = useState(null)
  const [elapsed,   setElapsed]  = useState(0)
  const [projects,  setProjects] = useState([])
  const [projectId, setProjectId] = useState('')
  const [loading,   setLoading]  = useState(false)
  const [error,     setError]    = useState('')
  const tickRef = useRef(null)

  useEffect(() => {
    api.get('/imputations/timer/current').then(r => {
      if (r.data) setTimer(r.data)
    }).catch(() => {})
    if (hasRate) {
      api.get('/projects?page_size=100').then(r => {
        setProjects(Array.isArray(r.data) ? r.data : (r.data.items || []))
      }).catch(() => {})
    }
  }, [hasRate])

  useEffect(() => {
    clearInterval(tickRef.current)
    if (!timer) { setElapsed(0); return }
    const tick = () => setElapsed(calcElapsed(timer))
    tick()
    if (!timer.paused_at) tickRef.current = setInterval(tick, 1000)
    return () => clearInterval(tickRef.current)
  }, [timer])

  const call = async (fn) => {
    setLoading(true); setError('')
    try { const r = await fn(); if (r?.data !== undefined) setTimer(r.data || null) }
    catch (e) { const raw = e?.response?.data?.detail; setError(Array.isArray(raw) ? raw.map(d => d.msg).join(', ') : (raw || 'Error')) }
    finally { setLoading(false) }
  }

  const isPaused = !!timer?.paused_at
  const stateColor = timer && !isPaused ? 'var(--success)' : isPaused ? 'var(--warning)' : 'var(--text-3)'

  const btnStyle = (bg) => ({
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
          {'\u23f1'} Cronómetro
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
            Proyecto #{timer.project_id}
          </div>
          <div style={{ display: 'flex', gap: 6 }}>
            {isPaused
              ? <button style={btnStyle('var(--accent)')} disabled={loading}
                  onClick={() => call(() => api.post('/imputations/timer/resume'))}>
                  {'\u25b6'} Reanudar
                </button>
              : <button style={btnStyle('var(--warning)')} disabled={loading}
                  onClick={() => call(() => api.post('/imputations/timer/pause'))}>
                  {'\u23f8'} Pausar
                </button>
            }
            <button style={btnStyle('var(--danger)')} disabled={loading}
              onClick={() => call(() =>
                api.post('/imputations/timer/stop', { description: 'Sesión', is_billable: true })
                  .then(r => { setTimer(null); return r })
              )}>
              {'\u23f9'}
            </button>
          </div>
        </>
      ) : (
        <>
          {!hasRate ? (
            <div style={{ fontSize: "var(--text-xs)", color: 'var(--danger)', lineHeight: 1.5 }}>
              ⚠ Sin tarifa horaria asignada. Contacta con RRHH para activar el cronómetro.
            </div>
          ) : (
            <>
              <select value={projectId} onChange={e => setProjectId(e.target.value)} style={selectStyle}>
                <option value="">— Proyecto —</option>
                {projects.map(p => <option key={p.id} value={p.id}>{p.name}</option>)}
              </select>
              <button
                disabled={!projectId || loading}
                onClick={() => call(() => api.post('/imputations/timer/start', { project_id: projectId }))}
                style={{ ...btnStyle('var(--accent)'), width: '100%', opacity: (!projectId || loading) ? 0.5 : 1 }}>
                {loading ? 'Iniciando…' : '▶ Iniciar'}
              </button>
            </>
          )}
        </>
      )}
      {error && <div style={{ fontSize: "var(--text-xs)", color: 'var(--danger)', marginTop: 6 }}>{'⚠'} {error}</div>}
    </div>
  )
}

export default TimerWidget
