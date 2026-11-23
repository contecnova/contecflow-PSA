import { type CSSProperties, useState, useRef, useEffect } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { nexusAgentApi, sdKbApi } from '../../services/api'
import type { Conversacion, FuenteDeRespuesta } from '../../services/api/tipos-analitica'
import { useConfirm } from '../../context/ConfirmContext'
import { useAppLang } from '../../i18n/AppLangContext'
import { Plus, Trash2, X } from 'lucide-react'
import { Checkbox, Pulsable, Textarea } from '../ui'
import './NexusAssistPanel.css'

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
  sources?: FuenteDeRespuesta[]
  correction?: boolean
}

/** Los mensajes guardados de una conversación, sin los de herramientas (no se pintan). */
const mensajesDe = (c: Conversacion): ChatMessage[] =>
  c.messages.flatMap(m => (m.role === 'tool' ? [] : [{ id: m.id, role: m.role, content: m.content }]))

interface Props {
  open: boolean
  onClose: () => void
  context?: AssistContext
}


export default function ContecflowAssistPanel({ open, onClose, context }: Props) {
  const { t } = useAppLang()
  // Auditoría 22-11-2026 (M3 del 04): el nombre de la pantalla sale del menú traducido
  // (`nav.<clave>`), no de una lista fija en castellano.
  const primerTramo = context?.page ? context.page.split('/')[1] || '' : ''
  const pageLabel = context?.page
    ? t(`nav.${primerTramo ? primerTramo.replace(/-/g, '_') : 'work_dashboard'}`)
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

  const { data: conversations = [] } = useQuery({
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
        setMessages(mensajesDe(data))
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
    setConvId(id); setMessages(mensajesDe(data))
  }

  if (!open) return null
  return (
    <div className="nexusass-sx1">
      {/* Revisión 2026-11: título, ruta y tres acciones no cabían en 420 px y la
          ✕ quedaba fuera del panel. La ruta va bajo el nombre y las acciones son
          iconos con su descripción. */}
      <div className="neaspa-row-1">
        <span aria-hidden className="neaspa-box-1">🤖</span>
        <div className="u-flex1-min0">
          <div className="u-md-600">NexusAssist</div>
          <div title={pageLabel || undefined} className="neaspa-box-2">
            {t('nexusassist.asistente_ia')}{pageLabel ? <span className="u-accent"> · {pageLabel}</span> : null}
          </div>
        </div>
        <div className="neaspa-row-2">
          <Pulsable title={t('nexusassist.nueva')} aria-label={t('nexusassist.nueva')} onClick={() => { localStorage.removeItem(LAST_CONV_KEY); setConvId(null); setMessages([]) }} className="neaspa-botonicono">
            <Plus size={16} />
          </Pulsable>
          <Pulsable className={`neaspa-botonicono2 ${conversations.length === 0 || isClearingHistory ? 'nexus-assist-panel-m1' : 'nexus-assist-panel-m2'}`} title={t(isClearingHistory ? 'nexusassist.borrando' : 'nexusassist.borrar_historial')} aria-label={t('nexusassist.borrar_historial')} disabled={conversations.length === 0 || isClearingHistory} onClick={() => openConfirm({
              title: t('nexusassist.borrar_historial'),
              message: t('nexusassist.borrar_historial_ayuda'),
              danger: true,
              onConfirm: () => clearHistory(),
            })}>
            <Trash2 size={16} />
          </Pulsable>
          <Pulsable title={t('nexusassist.cerrar')} aria-label={t('nexusassist.cerrar')} onClick={onClose} className="neaspa-botonicono">
            <X size={16} />
          </Pulsable>
        </div>
      </div>
      {!convId && messages.length === 0 && conversations.length > 0 && (
        <div className="neaspa-box-3">
          <div className="neaspa-box-4">{t('layoutshell.recientes')}</div>
          {conversations.slice(0,5).map(c => (
            <Pulsable key={c.id} onClick={() => loadConv(c.id)} className="neaspa-box-5">
              {c.title}
            </Pulsable>
          ))}
        </div>
      )}
      <div className="neaspa-stack-1">
        {messages.length === 0 && (
          <div>
            <div className="neaspa-box-6">{t('nexusassist.en_que_puedo_ayudarte_hoy')}</div>
            {SUGGESTIONS.map((s, i) => (
              <Pulsable key={i} onClick={() => sendMessage(s)} className="neaspa-box-7">
                {s}
              </Pulsable>
            ))}
          </div>
        )}
        {messages.map((m, i) => (
          <div className={`neaspa-stack-4 ${m.role === 'user' ? 'nexus-assist-panel-m3' : 'nexus-assist-panel-m4'}`} key={i}>
            <div className={`neaspa-box-12 nexus-assist-panel-e5 ${m.role === 'user' ? 'nexus-assist-panel-m6' : 'nexus-assist-panel-m7'}`} style={{ '--nexus-assist-panel-border': `.5px solid ${m.role === 'user' ? 'color-mix(in srgb, var(--accent) 25%, transparent)' : 'var(--surface-4)'}` } as CSSProperties}>
              {m.content}
            </div>
            {m.role === 'assistant' && i > 0 && messages[i - 1]?.role === 'user' && (
              <PieDeRespuesta mensaje={m} pregunta={messages[i - 1].content} />
            )}
          </div>
        ))}
        {loading && (
          <div className="neaspa-row-3">
            {[0,1,2].map(i => (
              <div className="neaspa-box-13 nexus-assist-panel-e8" key={i} style={{ '--nexus-assist-panel-animation': `bounce ${1.4}s ease-in-out ${i*0.2}s infinite` } as CSSProperties} />
            ))}
          </div>
        )}
        <div ref={bottomRef} />
      </div>
      <div className="neaspa-box-8">
        <div className="neaspa-row-4">
          <Textarea aria-label={t('nexusassist.escribe_aqui')} value={input} onChange={e => setInput(e.target.value)}
            onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendMessage(input) } }}
            placeholder={t('nexusassist.escribe_aqui')} rows={2}
            className="u-flex1-min0" inputClassName="neaspa-box-9" />
          <Pulsable className={`neaspa-box-14 nexusass-sx2 ${!input.trim() || loading ? 'nexus-assist-panel-m9' : 'nexus-assist-panel-m10'}`} onClick={() => sendMessage(input)} disabled={!input.trim() || loading}>↑</Pulsable>
        </div>
        <div className="neaspa-box-10">{t('nexusassist.enter_enviar_shift_enter_nueva_linea')}</div>
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
    return (
    <div className="neaspa-stack-2">
      <div className="neaspa-row-5">
        {mensaje.correction && <span className="neaspa-chip2">✓ {t('nexusassist.respuesta_validada')}</span>}
        {(mensaje.sources || []).map(s => (
          <a key={s.id} href="/service-desk?tab=kb" title={s.title} className="neaspa-chip">📖 {s.number} · {s.title.slice(0, 40)}</a>
        ))}
        {mensaje.id && (['up', 'down'] as const).map(d => (
          <Pulsable key={d} aria-pressed={voto === (d === 'up')} aria-label={t('nexusassist.voto_' + d)} title={t('nexusassist.voto_' + d)} onClick={() => votar(d === 'up')} className={`nexus-assist-panel-e11 ${voto === (d === 'up') ? 'nexus-assist-panel-m12' : ''}`}>
            {d === 'up' ? '👍' : '👎'}
          </Pulsable>
        ))}
        {voto === false && <span className="neaspa-chip3">{t('nexusassist.voto_gracias')}</span>}
        {!abierto && estado !== 'ok' && (
          <Pulsable onClick={() => setAbierto(true)} className="neaspa-chip4">✎ {t('nexusassist.corregir')}</Pulsable>
        )}
        {estado === 'ok' && <span className="neaspa-chip5">✓ {t('nexusassist.correccion_guardada')}</span>}
      </div>
      {abierto && (
        <div className="neaspa-stack-3">
          <div className="u-text3-xs">{t('nexusassist.corregir_ayuda')}</div>
          <Textarea aria-label={t('nexusassist.corregir')} value={respuesta} onChange={e => setRespuesta(e.target.value)} rows={4} inputClassName="neaspa-box-11" />
          <Checkbox className="neaspa-row-6" label={t('nexusassist.tambien_clientes')} checked={publica} onChange={m => setPublica(m)} />
          {estado === 'denegado' && <div role="alert" className="neaspa-txt-1">{t('nexusassist.correccion_sin_permiso')}</div>}
          {estado === 'error' && <div role="alert" className="neaspa-txt-1">{t('nexusassist.correccion_error')}</div>}
          <div className="neaspa-row-7">
            <Pulsable onClick={() => setAbierto(false)} className="neaspa-chip4">{t('nexusassist.cancelar')}</Pulsable>
            <Pulsable disabled={isPending || !respuesta.trim()} onClick={() => guardar()} className="neaspa-chip6">
              {t('nexusassist.guardar_correccion')}
            </Pulsable>
          </div>
        </div>
      )}
    </div>
  )
}
