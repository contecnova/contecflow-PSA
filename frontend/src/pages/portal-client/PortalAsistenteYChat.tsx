/**
 * PortalAsistenteYChat — en el portal de clientes (mejoras de mercado 16-11-2026):
 *
 * - **Asistente que actúa**: entiende «¿cómo va INC-0042?», «necesito un
 *   portátil» o «he olvidado la contraseña», contesta el estado al momento y
 *   PROPONE la petición del catálogo; solo se crea si el cliente la confirma.
 *   17-11-2026: entiende con la IA de la empresa (también busca en la base de
 *   conocimiento y contesta en el idioma del portal); si la IA no está, avisa y
 *   sigue con el reconocimiento por palabras. Conserva los turnos de la charla
 *   como contexto.
 * - **Chat en vivo**: contesta con artículos de la base de conocimiento y, si
 *   el cliente lo pide, pasa a una persona del equipo (traspaso a agente).
 *   17-11-2026: en tiempo real por el WebSocket del portal (mensaje nuevo,
 *   «escribiendo…», «leído» y traspaso); sondea solo si el socket no está.
 *
 * Textos en todos los idiomas del portal (`i18n/portal/*.ts`, claves `sdm_*`).
 */
import { useCallback, useEffect, useRef, useState, type ReactNode } from 'react'
import { AlertTriangle, Bot, BookOpen, Check, CheckCheck, MessagesSquare, Send, UserRound, X } from 'lucide-react'
import { CLIENT_API, useIdiomaDelPortal, useLang } from './portalClientContext'
import { PortalButton, PortalCard, PortalInput, PortalTabs } from './PortalUI'
import usePortalEnVivo, { enviarPorElPortal, type MensajeDelPortal } from './usePortalEnVivo'
import '../../components/servicedesk/sdMercado.css'

/** Cada cuánto se miran los mensajes nuevos del chat si el WebSocket no está (ms). */
const SONDEO_DEL_CHAT_MS = 5000
/** Cuánto dura el «escribiendo…» sin otro aviso (ms). */
const ESCRIBIENDO_MS = 6000
/** Cada cuánto se avisa como mucho de que el cliente escribe (ms). */
const AVISO_DE_ESCRITURA_MS = 3000
/** Turnos que se mandan al asistente como contexto. */
const TURNOS_DE_CONTEXTO = 6

const D = <T,>(p: Promise<{ data: unknown }>) => p.then(r => r.data as T)
const sustituir = (texto: string, valores: Record<string, string | number>) =>
  Object.entries(valores).reduce((acc, [k, v]) => acc.split(`{${k}}`).join(String(v)), texto)

interface Accion { id: string; action: string; params: { service_name?: string; description?: string }; expires_at: string }
interface Articulo { id: string; number?: string | null; title: string; summary?: string | null }
interface Intencion {
  intent: string
  engine?: 'ai' | 'rules'
  reply?: string | null
  notice?: string
  action?: Accion
  articles?: Articulo[]
  result?: { tickets: { id: string; number: string; title: string; status: string }[]; asked_number: string | null }
}
interface Turno { id: number; pregunta: string; respuesta: Intencion }
interface Mensaje { id: string; direction: 'in' | 'out'; author_type: string; body: string; created_at: string | null }
interface Conversacion { id: string; status: string; ticket_number: string | null; agent_read_at?: string | null }

/** 16-11-2026 (pasada de diseño): Soporte enseña el asistente y el chat como
 *  pestañas propias (un solo nivel de pestañas); esta vista con sub-pestañas
 *  queda para quien la monte suelta. */
export default function PortalAsistenteYChat() {
  const tr = useLang()
  const [vista, setVista] = useState('assistant')
  return (
    <div className="u-stack-12">
      <PortalTabs value={vista} onChange={setVista} ariaLabel={tr('sdm_titulo')} tabs={[
        { id: 'assistant', label: tr('sdm_asistente'), icon: <Bot size={14} /> },
        { id: 'chat', label: tr('sdm_chat'), icon: <MessagesSquare size={14} /> },
      ]} />
      {vista === 'assistant' ? <PortalAsistente /> : <PortalChatEnVivo />}
    </div>
  )
}

/** Lo que el asistente contestó, como texto para el contexto de la IA. */
function textoDeLaRespuesta(r: Intencion): string {
  if (r.reply) return r.reply
  if (r.result) return r.result.tickets.map(t => `${t.number} ${t.title} (${t.status})`).join('; ')
  if (r.action) return `${r.action.action}: ${r.action.params.service_name || ''}`
  return r.intent
}

export function PortalAsistente() {
  const tr = useLang()
  const idioma = useIdiomaDelPortal()
  const [texto, setTexto] = useState('')
  const [enviando, setEnviando] = useState(false)
  const [turnos, setTurnos] = useState<Turno[]>([])
  const [hecho, setHecho] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const siguiente = useRef(1)

  const preguntar = async () => {
    const pregunta = texto.trim()
    if (!pregunta) return
    setEnviando(true); setError(null); setHecho(null)
    const history = turnos.slice(-TURNOS_DE_CONTEXTO).flatMap(t => [
      { role: 'user', content: t.pregunta }, { role: 'assistant', content: textoDeLaRespuesta(t.respuesta).slice(0, 1900) }])
    try {
      const respuesta = await D<Intencion>(CLIENT_API.post('/sd/portal-assistant/intent', { message: pregunta, language: idioma, history }))
      setTurnos(prev => [...prev, { id: siguiente.current++, pregunta, respuesta }])
      setTexto('')
    } catch { setError(tr('sdm_error')) }
    finally { setEnviando(false) }
  }
  const decidir = async (turno: Turno, accion: Accion, confirmar: boolean) => {
    setEnviando(true); setError(null)
    try {
      if (confirmar) {
        const r = await D<{ ticket_number: string; approval_status: string | null }>(CLIENT_API.post(`/sd/portal-assistant/actions/${accion.id}/confirm`))
        setHecho(sustituir(tr(r.approval_status === 'pending' ? 'sdm_pedido_pendiente' : 'sdm_pedido_creado'), { n: r.ticket_number }))
      } else {
        await CLIENT_API.post(`/sd/portal-assistant/actions/${accion.id}/cancel`)
        setHecho(tr('sdm_cancelado'))
      }
      // La propuesta ya está decidida: deja de ofrecer los botones.
      setTurnos(prev => prev.map(t => t.id === turno.id ? { ...t, respuesta: { ...t.respuesta, action: undefined } } : t))
    } catch { setError(tr('sdm_error')) }
    finally { setEnviando(false) }
  }

  return (
    <PortalCard>
      <div className="u-stack-12">
        <div className="u-text2-xs">{tr('sdm_asistente_ayuda')}</div>
        {turnos.length > 0 && (
          <div className="sdm-chat" aria-live="polite">
            {turnos.map(t => (
              <div key={t.id} className="u-stack-8">
                <div className="sdm-chat__msg sdm-chat__msg--mine">{t.pregunta}</div>
                <div className="sdm-chat__msg">
                  <Respuesta r={t.respuesta} enviando={enviando} onDecidir={(a, ok) => decidir(t, a, ok)} />
                </div>
              </div>
            ))}
          </div>
        )}
        <div className="u-row-8">
          <PortalInput className="u-flex1" value={texto} aria-label={tr('sdm_asistente')} placeholder={tr('sdm_placeholder')}
            onChange={e => setTexto(e.target.value)} onKeyDown={e => { if (e.key === 'Enter') preguntar() }} />
          <PortalButton icon={<Send size={13} />} onClick={preguntar} loading={enviando} disabled={!texto.trim()}>
            {tr('sdm_enviar')}
          </PortalButton>
        </div>
        {error && <div role="alert" className="u-danger u-text2-xs">{error}</div>}
        {hecho && <div role="status" className="u-success u-text2-xs">{hecho}</div>}
      </div>
    </PortalCard>
  )
}

function Respuesta({ r, enviando, onDecidir }: { r: Intencion; enviando: boolean; onDecidir: (a: Accion, ok: boolean) => void }) {
  const tr = useLang()
  const aviso = r.notice === 'ai_unavailable' && (
    <div className="u-row-center-6 u-text3-xs" role="note"><AlertTriangle size={12} aria-hidden="true" />{tr('sdm_ia_no_disponible')}</div>
  )
  const respuestaLibre = r.reply ? <div>{r.reply}</div> : null
  let cuerpo: ReactNode = null
  if (r.intent === 'ticket_status' && r.result) {
    cuerpo = r.result.tickets.length === 0
      ? (respuestaLibre ? null : <div className="u-text2-xs">{r.result.asked_number ? sustituir(tr('sdm_ticket_no_encontrado'), { n: r.result.asked_number }) : tr('sdm_sin_abiertos')}</div>)
      : (
        <ul className="sdm-list">
          {r.result.tickets.map(tk => (
            <li key={tk.id} className="sdm-list__item"><span className="u-mono">{tk.number}</span>
              <span className="u-flex1-min0 sdm-wrap">{tk.title}</span><span className="u-text2-xs">{tr(`sdm_estado_${tk.status}`)}</span></li>
          ))}
        </ul>
      )
  } else if (r.intent === 'kb_answer') {
    cuerpo = r.articles && r.articles.length > 0 ? (
      <div className="u-stack-8">
        <div className="u-text3-2xs">{tr('sdm_articulos_sugeridos')}</div>
        <ul className="sdm-list">
          {r.articles.map(a => (
            <li key={a.id} className="sdm-list__item"><BookOpen size={13} aria-hidden="true" />
              <span className="u-flex1-min0 sdm-wrap"><span className="u-mono">{a.number}</span> {a.title}
                {a.summary && <span className="u-text3-xs"> — {a.summary}</span>}</span></li>
          ))}
        </ul>
      </div>
    ) : (respuestaLibre ? null : <div className="u-text2-xs">{tr('sdm_kb_sin_resultados')}</div>)
  } else if ((r.intent === 'catalog_request' || r.intent === 'password_reset') && r.action) {
    const a = r.action
    cuerpo = (
      <div className="u-stack-8">
        <div className="u-text1-sm-600">{sustituir(tr(r.intent === 'password_reset' ? 'sdm_propuesta_contrasena' : 'sdm_propuesta_catalogo'), { s: a.params.service_name || '' })}</div>
        <div className="u-text3-xs">{tr('sdm_confirmar_ayuda')}</div>
        <div className="u-actions-8">
          <PortalButton variant="secondary" size="sm" icon={<X size={13} />} disabled={enviando} onClick={() => onDecidir(a, false)}>{tr('sdm_no')}</PortalButton>
          <PortalButton size="sm" icon={<Check size={13} />} disabled={enviando} onClick={() => onDecidir(a, true)}>{tr('sdm_si_pedir')}</PortalButton>
        </div>
      </div>
    )
  } else if (!respuestaLibre && r.intent !== 'catalog_request' && r.intent !== 'password_reset') {
    const claves: Record<string, string> = {
      password_reset_unavailable: 'sdm_contrasena_no_disponible', catalog_no_match: 'sdm_catalogo_sin_coincidencia', none: 'sdm_no_entiendo',
    }
    cuerpo = <div className="u-text2-xs">{tr(claves[r.intent] || 'sdm_no_entiendo')}</div>
  }
  return <div className="u-stack-8">{aviso}{respuestaLibre}{cuerpo}</div>
}

export function PortalChatEnVivo() {
  const tr = useLang()
  const [conv, setConv] = useState<Conversacion | null>(null)
  const [mensajes, setMensajes] = useState<Mensaje[]>([])
  const [texto, setTexto] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [agenteEscribe, setAgenteEscribe] = useState(false)
  const ultimo = useRef<string | null>(null)
  const avisoDeEscritura = useRef(0)
  const finDeEscritura = useRef<ReturnType<typeof setTimeout> | null>(null)
  const convId = conv?.id

  const anadir = useCallback((nuevos: Mensaje[]) => {
    if (!nuevos.length) return
    setMensajes(prev => { const vistos = new Set(prev.map(m => m.id)); return [...prev, ...nuevos.filter(m => !vistos.has(m.id))] })
    ultimo.current = nuevos[nuevos.length - 1].id
  }, [])
  const empezar = async (cuerpo?: string) => {
    try {
      const r = await D<{ conversation: Conversacion; messages: Mensaje[] }>(CLIENT_API.post('/sd/channels/livechat', { body: cuerpo, language: document.documentElement.lang || undefined }))
      setConv(r.conversation); anadir(r.messages)
    } catch { setError(tr('sdm_error')) }
  }
  useEffect(() => { empezar() /* abre o sigue la conversación */ // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])
  const ponerAlDia = useCallback(async (id: string) => {
    try {
      const r = await D<{ conversation: Conversacion; messages: Mensaje[] }>(CLIENT_API.get(`/sd/channels/livechat/${id}/messages`, { params: { after: ultimo.current || undefined } }))
      setConv(r.conversation); anadir(r.messages)
    } catch { /* se reintenta en el siguiente aviso o sondeo */ }
  }, [anadir])

  // Tiempo real: mensajes, «escribiendo…», «leído» y traspaso de SU conversación.
  const enVivo = usePortalEnVivo(true, (m: MensajeDelPortal) => {
    if (m.type !== 'livechat' || !convId || m.conversation_id !== convId) return
    if (m.event === 'message' && m.message) {
      anadir([m.message as Mensaje])
      if ((m.message as Mensaje).author_type === 'agent') setAgenteEscribe(false)
    } else if (m.event === 'status' && m.conversation) {
      setConv(prev => prev ? { ...prev, ...(m.conversation as Partial<Conversacion>) } : prev)
    } else if (m.event === 'typing') {
      setAgenteEscribe(true)
      if (finDeEscritura.current) clearTimeout(finDeEscritura.current)
      finDeEscritura.current = setTimeout(() => setAgenteEscribe(false), ESCRIBIENDO_MS)
    } else if (m.event === 'read' && typeof m.read_at === 'string') {
      const leido = m.read_at
      setConv(prev => prev ? { ...prev, agent_read_at: leido } : prev)
    }
  })
  useEffect(() => () => { if (finDeEscritura.current) clearTimeout(finDeEscritura.current) }, [])
  // Al (re)conectar se recupera lo que llegara sin socket; sin socket, sondeo.
  useEffect(() => {
    if (!convId) return undefined
    if (enVivo) { void ponerAlDia(convId); return undefined }
    const id = setInterval(() => { void ponerAlDia(convId) }, SONDEO_DEL_CHAT_MS)
    return () => clearInterval(id)
  }, [convId, enVivo, ponerAlDia])
  // Leído: lo que el equipo escribió y el cliente tiene en pantalla.
  const ultimoDelEquipo = [...mensajes].reverse().find(m => m.direction === 'out')?.id
  useEffect(() => {
    if (convId && ultimoDelEquipo && document.visibilityState === 'visible') {
      enviarPorElPortal({ type: 'livechat_read', conversation_id: convId })
    }
  }, [convId, ultimoDelEquipo])

  const escribiendo = (valor: string) => {
    setTexto(valor)
    const ahora = Date.now()
    if (convId && valor.trim() && ahora - avisoDeEscritura.current > AVISO_DE_ESCRITURA_MS) {
      avisoDeEscritura.current = ahora
      enviarPorElPortal({ type: 'livechat_typing', conversation_id: convId })
    }
  }
  const enviar = async () => {
    if (!conv || !texto.trim()) return
    const cuerpo = texto.trim(); setTexto(''); setError(null)
    try {
      const r = await D<{ message: Mensaje | null }>(CLIENT_API.post(`/sd/channels/livechat/${conv.id}/messages`, { body: cuerpo }))
      if (r?.message) anadir([r.message])
      // Sin socket, la respuesta del asistente se recoge ahora; con socket llega sola.
      if (!enVivo) await ponerAlDia(conv.id)
    } catch { setError(tr('sdm_error')) }
  }
  const pedirPersona = async () => {
    if (!conv) return
    try { setConv(await D<Conversacion>(CLIENT_API.post(`/sd/channels/livechat/${conv.id}/agent`))) }
    catch { setError(tr('sdm_error')) }
  }

  const textoDe = (m: Mensaje) => m.author_type === 'system' ? tr(`sdm_evento_${m.body}`) : m.body
  const ultimoMio = [...mensajes].reverse().find(m => m.direction === 'in')
  const leidoElUltimo = !!(ultimoMio?.created_at && conv?.agent_read_at && Date.parse(conv.agent_read_at) >= Date.parse(ultimoMio.created_at))
  return (
    <PortalCard>
      <div className="u-stack-12">
        {conv && <div className="u-row-center-8 u-text2-xs">{tr(`sdm_conv_${conv.status}`)}{conv.ticket_number ? ` · ${conv.ticket_number}` : ''}</div>}
        <div className="sdm-chat" aria-live="polite">
          {mensajes.length === 0 && <div className="u-text3-xs">{tr('sdm_chat_bienvenida')}</div>}
          {mensajes.map(m => (
            <div key={m.id} className={`sdm-chat__msg${m.direction === 'in' ? ' sdm-chat__msg--mine' : ''}`}>
              {m.author_type === 'bot' && <div className="u-text3-2xs">{tr('sdm_articulos_sugeridos')}</div>}
              {textoDe(m)}
              {m.id === ultimoMio?.id && leidoElUltimo && (
                <div className="u-row-center-6 u-text3-2xs"><CheckCheck size={12} aria-hidden="true" />{tr('sdm_leido')}</div>
              )}
            </div>
          ))}
          {agenteEscribe && <div className="u-text3-xs" role="status">{tr('sdm_escribiendo')}</div>}
        </div>
        {error && <div role="alert" className="u-danger u-text2-xs">{error}</div>}
        {conv?.status !== 'closed' && (
          <div className="u-row-8">
            <PortalInput className="u-flex1" value={texto} aria-label={tr('sdm_chat')} placeholder={tr('sdm_chat_placeholder')}
              onChange={e => escribiendo(e.target.value)} onKeyDown={e => { if (e.key === 'Enter') enviar() }} />
            <PortalButton icon={<Send size={13} />} onClick={enviar} disabled={!texto.trim()}>{tr('sdm_enviar')}</PortalButton>
          </div>
        )}
        {conv?.status === 'bot' && (
          <div><PortalButton variant="secondary" size="sm" icon={<UserRound size={13} />} onClick={pedirPersona}>{tr('sdm_hablar_persona')}</PortalButton></div>
        )}
        {conv?.status === 'closed' && <div><PortalButton variant="secondary" size="sm" onClick={() => { setMensajes([]); ultimo.current = null; empezar() }}>{tr('sdm_nueva_conversacion')}</PortalButton></div>}
      </div>
    </PortalCard>
  )
}
