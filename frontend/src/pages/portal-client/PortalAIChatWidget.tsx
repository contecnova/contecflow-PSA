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
import { type CSSProperties, useState, useEffect, useRef } from 'react'
import { CLIENT_API, useErrorDelPortal, useLang } from './portalClientContext'
import { MessageCircle, X, Send, Sparkles, AlertTriangle, ThumbsUp, ThumbsDown } from 'lucide-react'
import './PortalAIChatWidget.css'
import { Pulsable } from '../../components/ui'

const SESSION_KEY = 'portal_ai_session_id'

type ChatRole = 'user' | 'assistant'

type Fuente = { id: string; number: string; title: string }

interface ChatMessage {
  id?: string
  role: ChatRole
  content: string
  sources?: Fuente[]   // revisión 2026-11: artículos de la base en que se apoya
}

interface ChatPostResponse {
  session_id?: string
  response?: string
  sources?: Fuente[]
  message_id?: string
}

/** Claves de texto del portal (`i18n/portal/*`) de las preguntas de ejemplo. */
const SUGGESTIONS = ['pai_sug_1', 'pai_sug_2', 'pai_sug_3', 'pai_sug_4']


export default function PortalAIChatWidget() {
  const t = useLang()
  const tp = useLang()
  const errorDe = useErrorDelPortal()
  const [open, setOpen] = useState(false)
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [input, setInput] = useState('')
  const [sending, setSending] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [sessionId, setSessionId] = useState<string | null>(() => {
    try { return localStorage.getItem(SESSION_KEY) || null } catch { return null }
  })
  const scrollRef = useRef<HTMLDivElement | null>(null)

  // Carga histórico al abrir si tenemos session_id
  useEffect(() => {
    if (!open || !sessionId) return
    let cancelled = false
    CLIENT_API.get(`/portal/ai-chat/${sessionId}/messages`)
      .then(res => {
        if (cancelled) return
        const arr = (Array.isArray(res?.data) ? res.data : []) as ChatMessage[]
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

  async function handleSend(text?: string) {
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
      const data = (res?.data || {}) as ChatPostResponse
      if (data.session_id && data.session_id !== sessionId) {
        setSessionId(data.session_id)
        try { localStorage.setItem(SESSION_KEY, data.session_id) } catch { /* noop */ }
      }
      setMessages(prev => [...prev, { id: data.message_id, role: 'assistant', content: data.response || '...', sources: data.sources || [] }])
    } catch (e: unknown) {
      // 16-11-2026: código del servidor en el idioma del portal; si no, `detail`
      // y, sin respuesta, el aviso de conexión (no el mensaje técnico de axios).
      setError(errorDe(e, tp('pai_err_connection')))
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
      <Pulsable
        onClick={() => setOpen(true)}
        aria-label={t('portalaichatwidget.abrir_asistente_ia')}
        title={t('portalaichatwidget.asistente_ia_pregunta_sobre_tus_proyectos')} className="portalai-sx1"
      >
        <MessageCircle size={24} />
      </Pulsable>
    )
  }

  // ── Open panel ───────────────────────────────────────────────────────────
  return (
    <div className="portalai-sx2"
    >
      {/* Header */}
      <div className="poaiwi-row-5">
        <div className="u-row-center-8">
          <Sparkles size={18} />
          <div>
            <div className="poaiwi-txt-1">{t('nexusassist.asistente_ia')}</div>
            <div className="poaiwi-box-1">
              {t('portalaichatwidget.pregunta_sobre_tus_proyectos')}
            </div>
          </div>
        </div>
        <div className="u-row-6">
          {messages.length > 0 && (
            <Pulsable onClick={handleClearSession}
              aria-label={t('portalaichatwidget.nueva_conversacion')} title={t('portalaichatwidget.empezar_de_nuevo')} className="portalai-sx3">
              {t('portalaichatwidget.nueva')}
            </Pulsable>
          )}
          <Pulsable onClick={() => setOpen(false)}
            aria-label={t('portalaichatwidget.cerrar_asistente')}
            className="poaiwi-row-1">
            <X size={18} />
          </Pulsable>
        </div>
      </div>

      {/* Messages */}
      <div ref={scrollRef} className="poaiwi-stack-1">
        {messages.length === 0 && !sending ? (
          <div className="poaiwi-box-2">
            <div className="poaiwi-box-3">
              {t('portalaichatwidget.hola_soy_el_asistente_ia_del_portal')}
            </div>
            <div className="poaiwi-box-4">
              {t('nexusagent.ejemplos')}
            </div>
            <div className="u-stack-6">
              {SUGGESTIONS.map(clave => tp(clave)).map(s => (
                <Pulsable key={s} onClick={() => handleSend(s)}
                  className="poaiwi-box-5 poaiwi-sugerencia">
                  <MessageCircle size={13} aria-hidden="true" /> {s}
                </Pulsable>
              ))}
            </div>
          </div>
        ) : (
          messages.map((m, idx) => (
            <div className={`poaiwi-box-10 portalai-sx4 ${m.role === 'user' ? 'portal-aichat-widget-m1' : 'portal-aichat-widget-m2'}`} key={idx}>
              {m.content}
              {!!m.sources?.length && (
                <div className="poaiwi-box-6">
                  {t('portalaichatwidget.fuentes')}: {m.sources.map(s => `${s.title} (${s.number})`).join(' · ')}
                </div>
              )}
              {m.role === 'assistant' && m.id && <Voto id={m.id} />}
            </div>
          ))
        )}
        {sending && (
          <div className="poaiwi-box-7">
            <span className="poaiwi-box-8">
              {t('portalaichatwidget.pensando')}
            </span>
          </div>
        )}
        {error && (
          <div className="portalai-sx5 poaiwi-sugerencia">
            <AlertTriangle size={14} aria-hidden="true" /> {error}
          </div>
        )}
      </div>

      {/* Input */}
      <div className="poaiwi-row-2">
        <input aria-label={t('portalaichatwidget.escribe_tu_pregunta')}
          value={input}
          onChange={e => setInput(e.target.value)}
          onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); handleSend() } }}
          disabled={sending}
          placeholder={t('portalaichatwidget.escribe_tu_pregunta')}
          className="poaiwi-box-9"
        />
        <Pulsable className={`poaiwi-row-4 ${input.trim() && !sending ? 'portal-aichat-widget-m3' : 'portal-aichat-widget-m4'}`} onClick={() => handleSend()} disabled={!input.trim() || sending}
          aria-label={t('chat.send')}>
          <Send size={14} />
        </Pulsable>
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


// Revisión 2026-11: 👍/👎 de cada respuesta; un 👎 avisa al equipo (pregunta sin respuesta).
function Voto({ id }: { id: string }) {
  const t = useLang()
  const [voto, setVoto] = useState<boolean | null>(null)
  const votar = (util: boolean) =>
    CLIENT_API.post(`/portal/ai-chat/messages/${id}/feedback`, { helpful: util }).then(() => setVoto(util)).catch(() => {})
  return (
    <div className="poaiwi-row-3">
      {([true, false] as const).map(util => (
        <Pulsable className="poaiwi-box-11 portalai-sx6 portal-aichat-widget-e5" key={String(util)} aria-pressed={voto === util} aria-label={t(util ? 'portalaichatwidget.voto_up' : 'portalaichatwidget.voto_down')}
          onClick={() => votar(util)}
          style={{ '--portal-aichat-widget-border': `1px solid ${voto === util ? 'var(--accent)' : 'var(--surface-4)'}` } as CSSProperties}>
          {util ? <ThumbsUp size={13} /> : <ThumbsDown size={13} />}
        </Pulsable>
      ))}
      {voto === false && <span className="u-text3">{t('portalaichatwidget.voto_gracias')}</span>}
    </div>
  )
}
