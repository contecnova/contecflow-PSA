import { useState, useRef, useEffect } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { nexusAgentApi, sdKbApi } from '../../services/api'
import { useConfirm } from '../../context/ConfirmContext'
import { useAppLang } from '../../i18n/AppLangContext'
import { Plus, Trash2, X } from 'lucide-react'

const LAST_CONV_KEY = 'nexusassist_last_conversation_id'

const SUGGESTIONS = [
  '¿Cuáles son los proyectos con más riesgo esta semana?',
  '¿Qué tickets llevan más de 24h sin respuesta?',
  'Resume el estado del equipo esta semana',
  '¿Cuántas horas se han imputado en los últimos 7 días?',
]

interface AssistContext {
  page?: string
  search?: string
}

interface ChatMessage {
  id?: string
  role: 'user' | 'assistant'
  content: string
  // Revisión 2026-11: artículos citados y si se aplicó la corrección de un experto.
  sources?: Array<{ id: string; number: string; title: string }>
  correction?: boolean
}

// TODO type: conversation summary payload — needs shared type from nexusAgentApi
interface ConversationSummary {
  id: string
  title: string
}

interface Props {
  open: boolean
  onClose: () => void
  context?: AssistContext
}

const botonIcono: React.CSSProperties = { width: 32, height: 32, display: 'flex', alignItems: 'center', justifyContent: 'center',
  background: 'transparent', border: '.5px solid var(--surface-4)', borderRadius: 8, color: 'var(--text-2)', cursor: 'pointer', padding: 0 }

export default function ContecflowAssistPanel({ open, onClose, context }: Props) {
  const { t } = useAppLang()
  // Derive human-readable page label from path
  const PAGE_LABELS: Record<string, string> = {
    '/': 'Dashboard', '/projects': 'Proyectos', '/tasks': 'Tareas',
    '/timesheets': 'Imputaciones', '/resources': 'Recursos', '/clients': 'Clientes',
    '/pipeline': 'Pipeline', '/expenses': 'Gastos', '/documents': 'Documentos',
    '/service-desk': 'Service Desk', '/risks': 'Riesgos', '/okrs': 'OKRs',
    '/analytics': 'Analytics', '/reports': 'Informes', '/capacity': 'Capacidad',
    '/settings': 'Ajustes',
  }
  const pageLabel = context?.page
    ? (Object.entries(PAGE_LABELS).find(([k]) => context.page === k || context.page!.startsWith(k + '/'))?.[1] || context.page)
    : null
  const qc = useQueryClient()
  const { openConfirm } = useConfirm()
  const [convId, setConvId]   = useState<string | null>(null)
  const [input, setInput]     = useState<string>('')
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [loading, setLoading] = useState<boolean>(false)
  const [restoredOnce, setRestoredOnce] = useState<boolean>(false)
  const bottomRef = useRef<HTMLDivElement | null>(null)

  useEffect(() => { bottomRef.current?.scrollIntoView({ behavior: 'smooth' }) }, [messages])

  const { data: conversations = [] } = useQuery<ConversationSummary[]>({
    queryKey: ['ai-conversations'],
    queryFn: () => nexusAgentApi.listConversations().then(r => r.data),
    enabled: open,
  })

  const { mutate: clearHistory, isPending: isClearingHistory } = useMutation({
    mutationFn: () => nexusAgentApi.deleteConversations().then(r => r.data),
    onSuccess: () => {
      localStorage.removeItem(LAST_CONV_KEY)
      setConvId(null)
      setMessages([])
      qc.invalidateQueries({ queryKey: ['ai-conversations'] })
    },
  })

  useEffect(() => {
    if (convId) {
      localStorage.setItem(LAST_CONV_KEY, convId)
    }
  }, [convId])

  useEffect(() => {
    if (!open) {
      setRestoredOnce(false)
      return
    }
    if (restoredOnce || convId || messages.length > 0) return

    const storedId = localStorage.getItem(LAST_CONV_KEY)
    if (!storedId) {
      setRestoredOnce(true)
      return
    }

    const exists = conversations.some(c => c.id === storedId)
    if (!exists && conversations.length > 0) {
      localStorage.removeItem(LAST_CONV_KEY)
      setRestoredOnce(true)
      return
    }

    if (!exists && conversations.length === 0) return

    const restore = async () => {
      try {
        const { data } = await nexusAgentApi.getConversation(storedId)
        setConvId(storedId)
        setMessages(data.messages || [])
      } catch {
        localStorage.removeItem(LAST_CONV_KEY)
      } finally {
        setRestoredOnce(true)
      }
    }

    restore()
  }, [open, restoredOnce, convId, messages.length, conversations])

  // Detección de contexto entity-level desde la URL (project_id, ticket_id, etc.)
  // Cableando A2 que estaba muerto: el backend soporta context_type/context_id
  // pero antes solo se pasaba {page: path}. Ahora si la URL es /projects/{id}
  // o /service-desk/{ticketId}, propagamos esa entity al chat.
  const _entityCtx = (() => {
    if (!context?.page) return {}
    const path = context.page
    const m1 = path.match(/^\/projects\/([\w-]+)/)
    if (m1) return { context_type: 'project', context_id: m1[1] }
    // El ticket se abre como `/service-desk?ticket=<id>` (no hay ruta propia).
    const ticket = path.startsWith('/service-desk') && new URLSearchParams(context.search || '').get('ticket')
    if (ticket) return { context_type: 'ticket', context_id: ticket }
    return {}
  })()

  const sendMessage = async (text: string) => {
    if (!text.trim() || loading) return
    const userText = text.trim(); setInput(''); setLoading(true)
    setMessages(prev => [...prev, { role: 'user', content: userText }])
    try {
      const { data } = await nexusAgentApi.chat({
        message: userText,
        conversation_id: convId,
        context: context || undefined,
        ..._entityCtx,
      })
      setConvId(data.conversation_id)
      setMessages(prev => [...prev, { id: data.message_id || undefined, role: 'assistant', content: data.message, sources: data.sources || [], correction: !!data.correction_applied }])
      qc.invalidateQueries({ queryKey: ['ai-conversations'] })
    } catch {
      setMessages(prev => [...prev, { role: 'assistant', content: t('nexusassist.error_conexion') }])
    }
    setLoading(false)
  }

  const loadConv = async (id: string) => {
    const { data } = await nexusAgentApi.getConversation(id)
    setConvId(id); setMessages(data.messages || [])
  }

  if (!open) return null
  return (
    <div style={{
      position:'fixed', top:12, right:12, width:420, maxWidth:'calc(100vw - 24px)', maxHeight:'calc(100vh - 24px)', zIndex:'var(--z-modal)',
      background:'var(--surface-1)', border:'.5px solid var(--surface-4)', borderRadius:12,
      display:'flex', flexDirection:'column', overflow:'hidden', boxShadow:'-4px 0 24px rgba(0,0,0,0.18)',
    }}>
      {/* Revisión 2026-11: título, ruta y tres acciones no cabían en 420 px y la
          ✕ quedaba fuera del panel. La ruta va bajo el nombre y las acciones son
          iconos con su descripción. */}
      <div style={{ padding:'14px 16px', borderBottom:'.5px solid var(--surface-4)',
        background:'var(--surface-2)', display:'flex', alignItems:'center', gap:10 }}>
        <span aria-hidden style={{ fontSize: "var(--text-xl-em)", flexShrink:0 }}>🤖</span>
        <div className="u-flex1-min0">
          <div className="u-md-600">NexusAssist</div>
          <div title={pageLabel || undefined} style={{ fontSize: "var(--text-xs)", color:'var(--text-2)', overflow:'hidden', textOverflow:'ellipsis', whiteSpace:'nowrap' }}>
            {t('nexusassist.asistente_ia')}{pageLabel ? <span className="u-accent"> · {pageLabel}</span> : null}
          </div>
        </div>
        <div style={{ display:'flex', gap:4, flexShrink:0 }}>
          <button type="button" title={t('nexusassist.nueva')} aria-label={t('nexusassist.nueva')}
            onClick={() => { localStorage.removeItem(LAST_CONV_KEY); setConvId(null); setMessages([]) }}
            style={botonIcono}>
            <Plus size={16} />
          </button>
          <button
            type="button"
            title={t(isClearingHistory ? 'nexusassist.borrando' : 'nexusassist.borrar_historial')}
            aria-label={t('nexusassist.borrar_historial')}
            disabled={conversations.length === 0 || isClearingHistory}
            onClick={() => openConfirm({
              title: t('nexusassist.borrar_historial'),
              message: t('nexusassist.borrar_historial_ayuda'),
              danger: true,
              onConfirm: () => clearHistory(),
            })}
            style={{ ...botonIcono, cursor: conversations.length === 0 || isClearingHistory ? 'not-allowed' : 'pointer', opacity: conversations.length === 0 || isClearingHistory ? 0.4 : 1 }}>
            <Trash2 size={16} />
          </button>
          <button type="button" title={t('nexusassist.cerrar')} aria-label={t('nexusassist.cerrar')} onClick={onClose} style={botonIcono}>
            <X size={16} />
          </button>
        </div>
      </div>
      {!convId && messages.length === 0 && conversations.length > 0 && (
        <div style={{ padding:'12px 16px', borderBottom:'.5px solid var(--surface-4)', maxHeight:180, overflowY:'auto' }}>
          <div style={{ fontSize: "var(--text-xs)", fontWeight:500, color:'var(--text-2)', marginBottom:8 }}>Recientes</div>
          {conversations.slice(0,5).map(c => (
            <button key={c.id} onClick={() => loadConv(c.id)}
              type="button"
              style={{ padding:'7px 10px', borderRadius:7, cursor:'pointer', marginBottom:4,
                background:'var(--surface-2)', fontSize: "var(--text-sm)",
                border:'.5px solid var(--surface-4)', overflow:'hidden', textOverflow:'ellipsis', whiteSpace:'nowrap',
                width:'100%', textAlign:'left', color:'var(--text-2)', fontFamily:'inherit' }}>
              {c.title}
            </button>
          ))}
        </div>
      )}
      <div style={{ flex:1, overflowY:'auto', padding:'16px 18px', display:'flex', flexDirection:'column', gap:12 }}>
        {messages.length === 0 && (
          <div>
            <div style={{ fontSize: "var(--text-base)", color:'var(--text-2)', marginBottom:16, textAlign:'center', paddingTop:20 }}>{t('nexusassist.en_que_puedo_ayudarte_hoy')}</div>
            {SUGGESTIONS.map((s, i) => (
              <button key={i} onClick={() => sendMessage(s)}
                type="button"
                style={{ padding:'10px 14px', borderRadius:'var(--radius-md)', border:'.5px solid var(--surface-4)',
                  cursor:'pointer', marginBottom:8, fontSize: "var(--text-sm)", color:'var(--text-2)',
                  background:'var(--surface-2)', width:'100%', textAlign:'left', fontFamily:'inherit' }}>
                {s}
              </button>
            ))}
          </div>
        )}
        {messages.map((m, i) => (
          <div key={i} style={{ display:'flex', flexDirection:'column', alignItems: m.role === 'user' ? 'flex-end' : 'flex-start' }}>
            <div style={{ maxWidth:'85%', padding:'10px 14px',
              borderRadius: m.role === 'user' ? '16px 16px 4px 16px' : '4px 16px 16px 16px',
              background: m.role === 'user' ? 'var(--accent-muted)' : 'var(--surface-2)',
              border: `.5px solid ${m.role === 'user' ? 'rgba(0,212,255,0.25)' : 'var(--surface-4)'}`,
              fontSize: "var(--text-base)", lineHeight:1.55, whiteSpace:'pre-wrap' }}>
              {m.content}
            </div>
            {m.role === 'assistant' && i > 0 && messages[i - 1]?.role === 'user' && (
              <PieDeRespuesta mensaje={m} pregunta={messages[i - 1].content} />
            )}
          </div>
        ))}
        {loading && (
          <div style={{ display:'flex', gap:6, padding:'12px 14px',
            background:'var(--surface-2)', borderRadius:'4px 16px 16px 16px',
            width:'fit-content', border:'.5px solid var(--surface-4)' }}>
            {[0,1,2].map(i => (
              <div key={i} style={{ width:8, height:8, borderRadius:'50%', background:'var(--text-3)',
                animation:`bounce ${1.4}s ease-in-out ${i*0.2}s infinite` }} />
            ))}
          </div>
        )}
        <div ref={bottomRef} />
      </div>
      <div style={{ padding:'14px 18px', borderTop:'.5px solid var(--surface-4)', background:'var(--surface-2)' }}>
        <div style={{ display:'flex', gap:10, alignItems:'flex-end' }}>
          <textarea aria-label={t('nexusassist.escribe_aqui')} value={input} onChange={e => setInput(e.target.value)}
            onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendMessage(input) } }}
            placeholder={t('nexusassist.escribe_aqui')} rows={2}
            style={{ flex:1, background:'var(--surface-1)', border:'.5px solid var(--surface-4)',
              borderRadius:'var(--radius-md)', padding:'10px 14px', fontSize: "var(--text-base)", outline:'none', fontFamily:'inherit', resize:'none', lineHeight:1.4 }} />
          <button onClick={() => sendMessage(input)} disabled={!input.trim() || loading}
            style={{ padding:'10px 16px', borderRadius:'var(--radius-md)', background:'var(--accent)',
              border:'none', color:'white', cursor:'pointer', fontSize: "var(--text-lg-em)",
              opacity: !input.trim() || loading ? 0.5 : 1 }}>↑</button>
        </div>
        <div style={{ fontSize: "var(--text-2xs)", color:'var(--text-3)', marginTop:5, textAlign:'center' }}>{t('nexusassist.enter_enviar_shift_enter_nueva_linea')}</div>
      </div>
      <style>{`@keyframes bounce{0%,80%,100%{transform:scale(0)}40%{transform:scale(1)}}`}</style>
    </div>
  )
}


// Revisión 2026-11: fuentes citadas, aviso de respuesta validada y «Corregir»:
// quien puede publicar en la base deja la respuesta buena y se aplica al momento
// a las preguntas parecidas (también a los clientes si lo marca).
function PieDeRespuesta({ mensaje, pregunta }: { mensaje: ChatMessage; pregunta: string }) {
  const { t } = useAppLang()
  const [abierto, setAbierto] = useState(false)
  const [respuesta, setRespuesta] = useState(mensaje.content)
  const [publica, setPublica] = useState(false)
  const [estado, setEstado] = useState<'' | 'ok' | 'error' | 'denegado'>('')
  // Revisión 2026-11: 👍/👎. Un 👎 lleva la pregunta a «Preguntas sin respuesta».
  const [voto, setVoto] = useState<boolean | null>(null)
  const { mutate: votar } = useMutation({
    mutationFn: (util: boolean) => nexusAgentApi.feedback(mensaje.id as string, { helpful: util }),
    onSuccess: (_r: unknown, util: boolean) => setVoto(util),
  })
  const { mutate: guardar, isPending } = useMutation({
    mutationFn: () => sdKbApi.createCorrection({ question: pregunta, answer: respuesta.trim(), is_public: publica }),
    onSuccess: () => { setEstado('ok'); setAbierto(false) },
    onError: (e: unknown) => setEstado((e as { response?: { status?: number } })?.response?.status === 403 ? 'denegado' : 'error'),
  })
  const chip = { fontSize: 'var(--text-2xs)', padding: '2px 8px', borderRadius: 'var(--radius-md)', border: '.5px solid var(--surface-4)', background: 'var(--surface-2)', color: 'var(--text-2)', textDecoration: 'none' } as const
  return (
    <div style={{ maxWidth: '85%', marginTop: 4, display: 'flex', flexDirection: 'column', gap: 4 }}>
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4, alignItems: 'center' }}>
        {mensaje.correction && <span style={{ ...chip, color: 'var(--success)', borderColor: 'var(--success)' }}>✓ {t('nexusassist.respuesta_validada')}</span>}
        {(mensaje.sources || []).map(s => (
          <a key={s.id} href="/service-desk?tab=kb" title={s.title} style={chip}>📖 {s.number} · {s.title.slice(0, 40)}</a>
        ))}
        {mensaje.id && (['up', 'down'] as const).map(d => (
          <button key={d} type="button" aria-pressed={voto === (d === 'up')} aria-label={t('nexusassist.voto_' + d)} title={t('nexusassist.voto_' + d)}
            onClick={() => votar(d === 'up')}
            style={{ ...chip, cursor: 'pointer', fontFamily: 'inherit', ...(voto === (d === 'up') ? { borderColor: 'var(--accent)', color: 'var(--accent)' } : {}) }}>
            {d === 'up' ? '👍' : '👎'}
          </button>
        ))}
        {voto === false && <span style={{ ...chip, color: 'var(--text-3)' }}>{t('nexusassist.voto_gracias')}</span>}
        {!abierto && estado !== 'ok' && (
          <button type="button" onClick={() => setAbierto(true)} style={{ ...chip, cursor: 'pointer', fontFamily: 'inherit' }}>✎ {t('nexusassist.corregir')}</button>
        )}
        {estado === 'ok' && <span style={{ ...chip, color: 'var(--success)' }}>✓ {t('nexusassist.correccion_guardada')}</span>}
      </div>
      {abierto && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 6, padding: 8, border: '.5px solid var(--surface-4)', borderRadius: 8, background: 'var(--surface-2)' }}>
          <div className="u-text3-xs">{t('nexusassist.corregir_ayuda')}</div>
          <textarea aria-label={t('nexusassist.corregir')} value={respuesta} onChange={e => setRespuesta(e.target.value)} rows={4}
            style={{ background: 'var(--surface-1)', border: '.5px solid var(--surface-4)', borderRadius: 8, padding: 8, fontSize: 'var(--text-sm)', fontFamily: 'inherit', resize: 'vertical' }} />
          <label style={{ display: 'flex', gap: 6, alignItems: 'center', fontSize: 'var(--text-xs)', color: 'var(--text-2)' }}>
            <input type="checkbox" checked={publica} onChange={e => setPublica(e.target.checked)} /> {t('nexusassist.tambien_clientes')}
          </label>
          {estado === 'denegado' && <div role="alert" style={{ fontSize: 'var(--text-xs)', color: 'var(--danger)' }}>{t('nexusassist.correccion_sin_permiso')}</div>}
          {estado === 'error' && <div role="alert" style={{ fontSize: 'var(--text-xs)', color: 'var(--danger)' }}>{t('nexusassist.correccion_error')}</div>}
          <div style={{ display: 'flex', gap: 6, justifyContent: 'flex-end' }}>
            <button type="button" onClick={() => setAbierto(false)} style={{ ...chip, cursor: 'pointer', fontFamily: 'inherit' }}>{t('nexusassist.cancelar')}</button>
            <button type="button" disabled={isPending || !respuesta.trim()} onClick={() => guardar()}
              style={{ ...chip, cursor: 'pointer', fontFamily: 'inherit', background: 'var(--accent)', color: 'var(--on-accent)', borderColor: 'var(--accent)' }}>
              {t('nexusassist.guardar_correccion')}
            </button>
          </div>
        </div>
      )}
    </div>
  )
}
