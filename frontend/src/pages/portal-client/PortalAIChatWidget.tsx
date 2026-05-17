// @ts-nocheck
/**
 * PortalAIChatWidget — Item I26 (UI del Client Portal AI Chat).
 *
 * Widget flotante tipo Intercom: burbuja en la esquina inferior derecha,
 * click → panel deslizable con conversación. Persistencia de session_id en
 * localStorage para mantener contexto entre navegaciones / recargas.
 *
 * Auth: usa la cookie httponly del portal cliente (``portal_access_token``)
 * vía ``CLIENT_API``; el backend resuelve el ``client_user`` con
 * ``get_current_client``. No necesitamos pasar JWT como body (que sería
 * inalcanzable desde JS por httponly).
 */
import { useState, useEffect, useRef } from 'react'
import { CLIENT_API } from './portalClientContext'
import { MessageCircle, X, Send, Sparkles } from 'lucide-react'

const SESSION_KEY = 'portal_ai_session_id'

const SUGGESTIONS = [
  '¿Cómo va el proyecto?',
  '¿Cuántas tareas quedan pendientes?',
  '¿Cuándo es la próxima entrega?',
  '¿Qué riesgos hay identificados?',
]


export default function PortalAIChatWidget() {
  const [open, setOpen] = useState(false)
  const [messages, setMessages] = useState([])
  const [input, setInput] = useState('')
  const [sending, setSending] = useState(false)
  const [error, setError] = useState(null)
  const [sessionId, setSessionId] = useState(() => {
    try { return localStorage.getItem(SESSION_KEY) || null } catch { return null }
  })
  const scrollRef = useRef(null)

  // Carga histórico al abrir si tenemos session_id
  useEffect(() => {
    if (!open || !sessionId) return
    let cancelled = false
    CLIENT_API.get(`/portal/ai-chat/${sessionId}/messages`)
      .then(res => {
        if (cancelled) return
        const arr = Array.isArray(res?.data) ? res.data : []
        setMessages(arr)
      })
      .catch(() => {
        // 404 → la sesión guardada ya no existe (servidor reiniciado/limpiado)
        if (cancelled) return
        try { localStorage.removeItem(SESSION_KEY) } catch { /* noop */ }
        setSessionId(null)
        setMessages([])
      })
    return () => { cancelled = true }
  }, [open, sessionId])

  // Auto-scroll al final cuando llegan mensajes
  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight
    }
  }, [messages, sending])

  async function handleSend(text) {
    const msg = (text ?? input).trim()
    if (!msg || sending) return
    setError(null)
    setSending(true)
    setInput('')
    // Optimistic insert user message
    setMessages(prev => [...prev, { role: 'user', content: msg }])
    try {
      const res = await CLIENT_API.post('/portal/ai-chat', {
        message: msg,
        session_id: sessionId || undefined,
      })
      const data = res?.data || {}
      if (data.session_id && data.session_id !== sessionId) {
        setSessionId(data.session_id)
        try { localStorage.setItem(SESSION_KEY, data.session_id) } catch { /* noop */ }
      }
      setMessages(prev => [...prev, { role: 'assistant', content: data.response || '...' }])
    } catch (e) {
      const detail = e?.response?.data?.detail || e?.message || 'Error de conexión'
      setError(detail)
      // Quitar el mensaje user que añadimos optimísticamente si no se procesó
      setMessages(prev => prev.slice(0, -1))
    } finally {
      setSending(false)
    }
  }

  function handleClearSession() {
    try { localStorage.removeItem(SESSION_KEY) } catch { /* noop */ }
    setSessionId(null)
    setMessages([])
  }

  // ── Floating bubble ──────────────────────────────────────────────────────
  if (!open) {
    return (
      <button
        onClick={() => setOpen(true)}
        aria-label="Abrir asistente IA"
        title="Asistente IA — pregunta sobre tus proyectos"
        style={{
          position: 'fixed', bottom: 24, right: 24, zIndex: 1000,
          width: 56, height: 56, borderRadius: '50%',
          background: 'linear-gradient(135deg, var(--accent), var(--purple, #7c3aed))',
          border: 'none', cursor: 'pointer',
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          boxShadow: '0 10px 28px rgba(0,0,0,0.35)',
          color: '#fff',
        }}
      >
        <MessageCircle size={24} />
      </button>
    )
  }

  // ── Open panel ───────────────────────────────────────────────────────────
  return (
    <div
      style={{
        position: 'fixed', bottom: 24, right: 24, zIndex: 1000,
        width: 380, maxWidth: 'calc(100vw - 32px)',
        height: 560, maxHeight: 'calc(100vh - 48px)',
        background: 'var(--surface-1)',
        border: '1px solid var(--surface-4)',
        borderRadius: 14,
        boxShadow: '0 18px 50px rgba(0,0,0,0.45)',
        display: 'flex', flexDirection: 'column',
        overflow: 'hidden',
      }}
    >
      {/* Header */}
      <div style={{
        padding: '14px 16px',
        background: 'linear-gradient(135deg, var(--accent), var(--purple, #7c3aed))',
        color: '#fff', display: 'flex', alignItems: 'center', justifyContent: 'space-between',
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <Sparkles size={18} />
          <div>
            <div style={{ fontWeight: 700, fontSize: 14 }}>Asistente IA</div>
            <div style={{ fontSize: 11, opacity: 0.85 }}>
              Pregunta sobre tus proyectos
            </div>
          </div>
        </div>
        <div style={{ display: 'flex', gap: 6 }}>
          {messages.length > 0 && (
            <button onClick={handleClearSession}
              aria-label="Nueva conversación" title="Empezar de nuevo"
              style={{
                background: 'rgba(255,255,255,0.15)', color: '#fff', border: 'none',
                borderRadius: 6, padding: '4px 8px', cursor: 'pointer',
                fontSize: 11, fontWeight: 600,
              }}>
              Nueva
            </button>
          )}
          <button onClick={() => setOpen(false)}
            aria-label="Cerrar asistente"
            style={{
              background: 'transparent', color: '#fff', border: 'none',
              cursor: 'pointer', padding: 4, display: 'flex',
            }}>
            <X size={18} />
          </button>
        </div>
      </div>

      {/* Messages */}
      <div ref={scrollRef} style={{
        flex: 1, padding: '14px 16px', overflowY: 'auto',
        display: 'flex', flexDirection: 'column', gap: 10,
        background: 'var(--surface-2)',
      }}>
        {messages.length === 0 && !sending ? (
          <div style={{ color: 'var(--text-2)', fontSize: 13, padding: '10px 0' }}>
            <div style={{ marginBottom: 12, lineHeight: 1.5 }}>
              👋 Hola, soy el asistente IA del portal. Puedo responderte sobre el
              estado de tus proyectos, tareas pendientes, hitos próximos y más.
            </div>
            <div style={{ fontSize: 11, color: 'var(--text-3)', textTransform: 'uppercase', letterSpacing: 0.5, marginBottom: 6 }}>
              Ejemplos
            </div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
              {SUGGESTIONS.map(s => (
                <button key={s} onClick={() => handleSend(s)}
                  style={{
                    textAlign: 'left', background: 'var(--surface-3)',
                    border: '1px solid var(--surface-4)', borderRadius: 8,
                    padding: '8px 12px', cursor: 'pointer', fontSize: 12,
                    color: 'var(--text-1)',
                  }}>
                  💬 {s}
                </button>
              ))}
            </div>
          </div>
        ) : (
          messages.map((m, idx) => (
            <div key={idx} style={{
              alignSelf: m.role === 'user' ? 'flex-end' : 'flex-start',
              maxWidth: '85%',
              background: m.role === 'user' ? 'var(--accent)' : 'var(--surface-1)',
              color: m.role === 'user' ? '#fff' : 'var(--text-1)',
              border: m.role === 'user' ? 'none' : '1px solid var(--surface-4)',
              borderRadius: 10,
              padding: '8px 12px',
              fontSize: 13, lineHeight: 1.4,
              whiteSpace: 'pre-wrap', wordBreak: 'break-word',
            }}>
              {m.content}
            </div>
          ))
        )}
        {sending && (
          <div style={{
            alignSelf: 'flex-start', maxWidth: '85%',
            background: 'var(--surface-1)', border: '1px solid var(--surface-4)',
            borderRadius: 10, padding: '8px 12px',
            color: 'var(--text-3)', fontSize: 13, fontStyle: 'italic',
          }}>
            <span style={{ display: 'inline-block', animation: 'pulse 1.2s ease-in-out infinite' }}>
              Pensando…
            </span>
          </div>
        )}
        {error && (
          <div style={{
            background: 'rgba(239,68,68,0.12)', color: 'var(--danger)',
            border: '1px solid var(--danger)', borderRadius: 8,
            padding: '8px 12px', fontSize: 12,
          }}>
            ⚠ {error}
          </div>
        )}
      </div>

      {/* Input */}
      <div style={{
        padding: '10px 12px', borderTop: '1px solid var(--surface-4)',
        background: 'var(--surface-1)', display: 'flex', gap: 6,
      }}>
        <input
          value={input}
          onChange={e => setInput(e.target.value)}
          onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); handleSend() } }}
          disabled={sending}
          placeholder="Escribe tu pregunta…"
          style={{
            flex: 1, padding: '8px 10px',
            background: 'var(--surface-3)', border: '1px solid var(--surface-4)',
            borderRadius: 8, color: 'var(--text-1)', fontSize: 13,
            outline: 'none',
          }}
        />
        <button onClick={() => handleSend()} disabled={!input.trim() || sending}
          aria-label="Enviar"
          style={{
            padding: '8px 12px', background: 'var(--accent)', color: '#fff',
            border: 'none', borderRadius: 8, cursor: input.trim() && !sending ? 'pointer' : 'not-allowed',
            opacity: input.trim() && !sending ? 1 : 0.5,
            display: 'flex', alignItems: 'center', justifyContent: 'center',
          }}>
          <Send size={14} />
        </button>
      </div>

      <style>{`
        @keyframes pulse {
          0%, 100% { opacity: 0.5; }
          50%      { opacity: 1; }
        }
      `}</style>
    </div>
  )
}
