/**
 * PortalAsistenteYChat — en el portal de clientes (mejoras de mercado 16-11-2026):
 *
 * - **Asistente que actúa**: entiende «¿cómo va INC-0042?», «necesito un
 *   portátil» o «he olvidado la contraseña», contesta el estado al momento y
 *   PROPONE la petición del catálogo; solo se crea si el cliente la confirma.
 * - **Chat en vivo**: contesta con artículos de la base de conocimiento y, si
 *   el cliente lo pide, pasa a una persona del equipo (traspaso a agente).
 *
 * Textos en todos los idiomas del portal (`i18n/portal/*.ts`, claves `sdm_*`).
 */
import { useEffect, useRef, useState } from 'react'
import { Bot, Check, MessagesSquare, Send, UserRound, X } from 'lucide-react'
import { CLIENT_API, useLang } from './portalClientContext'
import { PortalButton, PortalCard, PortalInput, PortalTabs } from './PortalUI'
import '../../components/servicedesk/sdMercado.css'

/** Cada cuánto se miran los mensajes nuevos del chat (ms). */
const SONDEO_DEL_CHAT_MS = 5000

const D = <T,>(p: Promise<{ data: unknown }>) => p.then(r => r.data as T)
const sustituir = (texto: string, valores: Record<string, string | number>) =>
  Object.entries(valores).reduce((acc, [k, v]) => acc.split(`{${k}}`).join(String(v)), texto)

interface Accion { id: string; action: string; params: { service_name?: string; description?: string }; expires_at: string }
interface Intencion {
  intent: string
  action?: Accion
  result?: { tickets: { id: string; number: string; title: string; status: string }[]; asked_number: string | null }
}
interface Mensaje { id: string; direction: 'in' | 'out'; author_type: string; body: string; created_at: string | null }
interface Conversacion { id: string; status: string; ticket_number: string | null }

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

export function PortalAsistente() {
  const tr = useLang()
  const [texto, setTexto] = useState('')
  const [enviando, setEnviando] = useState(false)
  const [respuesta, setRespuesta] = useState<Intencion | null>(null)
  const [hecho, setHecho] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  const preguntar = async () => {
    if (!texto.trim()) return
    setEnviando(true); setError(null); setHecho(null)
    try { setRespuesta(await D<Intencion>(CLIENT_API.post('/sd/portal-assistant/intent', { message: texto.trim() }))) }
    catch { setError(tr('sdm_error')) }
    finally { setEnviando(false) }
  }
  const decidir = async (accion: Accion, confirmar: boolean) => {
    setEnviando(true); setError(null)
    try {
      if (confirmar) {
        const r = await D<{ ticket_number: string; approval_status: string | null }>(CLIENT_API.post(`/sd/portal-assistant/actions/${accion.id}/confirm`))
        setHecho(sustituir(tr(r.approval_status === 'pending' ? 'sdm_pedido_pendiente' : 'sdm_pedido_creado'), { n: r.ticket_number }))
      } else {
        await CLIENT_API.post(`/sd/portal-assistant/actions/${accion.id}/cancel`)
        setHecho(tr('sdm_cancelado'))
      }
      setRespuesta(null); setTexto('')
    } catch { setError(tr('sdm_error')) }
    finally { setEnviando(false) }
  }

  return (
    <PortalCard>
      <div className="u-stack-12">
        <div className="u-text2-xs">{tr('sdm_asistente_ayuda')}</div>
        <div className="u-row-8">
          <PortalInput className="u-flex1" value={texto} aria-label={tr('sdm_asistente')} placeholder={tr('sdm_placeholder')}
            onChange={e => setTexto(e.target.value)} onKeyDown={e => { if (e.key === 'Enter') preguntar() }} />
          <PortalButton icon={<Send size={13} />} onClick={preguntar} loading={enviando} disabled={!texto.trim()}>
            {tr('sdm_enviar')}
          </PortalButton>
        </div>
        {error && <div role="alert" className="u-danger u-text2-xs">{error}</div>}
        {hecho && <div role="status" className="u-success u-text2-xs">{hecho}</div>}
        {respuesta && <Respuesta r={respuesta} enviando={enviando} onDecidir={decidir} />}
      </div>
    </PortalCard>
  )
}

function Respuesta({ r, enviando, onDecidir }: { r: Intencion; enviando: boolean; onDecidir: (a: Accion, ok: boolean) => void }) {
  const tr = useLang()
  if (r.intent === 'ticket_status' && r.result) {
    if (r.result.tickets.length === 0) {
      return <div className="u-text2-xs">{r.result.asked_number ? sustituir(tr('sdm_ticket_no_encontrado'), { n: r.result.asked_number }) : tr('sdm_sin_abiertos')}</div>
    }
    return (
      <ul className="sdm-list">
        {r.result.tickets.map(tk => (
          <li key={tk.id} className="sdm-list__item"><span className="u-mono">{tk.number}</span>
            <span className="u-flex1-min0 sdm-wrap">{tk.title}</span><span className="u-text2-xs">{tr(`sdm_estado_${tk.status}`)}</span></li>
        ))}
      </ul>
    )
  }
  if ((r.intent === 'catalog_request' || r.intent === 'password_reset') && r.action) {
    const a = r.action
    return (
      <div className="u-stack-8">
        <div className="u-text1-sm-600">{sustituir(tr(r.intent === 'password_reset' ? 'sdm_propuesta_contrasena' : 'sdm_propuesta_catalogo'), { s: a.params.service_name || '' })}</div>
        <div className="u-text3-xs">{tr('sdm_confirmar_ayuda')}</div>
        <div className="u-actions-8">
          <PortalButton variant="secondary" size="sm" icon={<X size={13} />} disabled={enviando} onClick={() => onDecidir(a, false)}>{tr('sdm_no')}</PortalButton>
          <PortalButton size="sm" icon={<Check size={13} />} disabled={enviando} onClick={() => onDecidir(a, true)}>{tr('sdm_si_pedir')}</PortalButton>
        </div>
      </div>
    )
  }
  const claves: Record<string, string> = {
    password_reset_unavailable: 'sdm_contrasena_no_disponible', catalog_no_match: 'sdm_catalogo_sin_coincidencia', none: 'sdm_no_entiendo',
  }
  return <div className="u-text2-xs">{tr(claves[r.intent] || 'sdm_no_entiendo')}</div>
}

export function PortalChatEnVivo() {
  const tr = useLang()
  const [conv, setConv] = useState<Conversacion | null>(null)
  const [mensajes, setMensajes] = useState<Mensaje[]>([])
  const [texto, setTexto] = useState('')
  const [error, setError] = useState<string | null>(null)
  const ultimo = useRef<string | null>(null)

  const anadir = (nuevos: Mensaje[]) => {
    if (!nuevos.length) return
    setMensajes(prev => { const vistos = new Set(prev.map(m => m.id)); return [...prev, ...nuevos.filter(m => !vistos.has(m.id))] })
    ultimo.current = nuevos[nuevos.length - 1].id
  }
  const empezar = async (cuerpo?: string) => {
    try {
      const r = await D<{ conversation: Conversacion; messages: Mensaje[] }>(CLIENT_API.post('/sd/channels/livechat', { body: cuerpo, language: document.documentElement.lang || undefined }))
      setConv(r.conversation); anadir(r.messages)
    } catch { setError(tr('sdm_error')) }
  }
  useEffect(() => { empezar() /* abre o sigue la conversación */ // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])
  // El sondeo depende solo del id: cada respuesta trae un objeto `conv` nuevo y
  // reiniciar el intervalo por eso no tendría sentido.
  const convId = conv?.id
  useEffect(() => {
    if (!convId) return
    const id = setInterval(async () => {
      try {
        const r = await D<{ conversation: Conversacion; messages: Mensaje[] }>(CLIENT_API.get(`/sd/channels/livechat/${convId}/messages`, { params: { after: ultimo.current || undefined } }))
        setConv(r.conversation); anadir(r.messages)
      } catch { /* se reintenta en el siguiente sondeo */ }
    }, SONDEO_DEL_CHAT_MS)
    return () => clearInterval(id)
  }, [convId])

  const enviar = async () => {
    if (!conv || !texto.trim()) return
    const cuerpo = texto.trim(); setTexto(''); setError(null)
    try {
      await CLIENT_API.post(`/sd/channels/livechat/${conv.id}/messages`, { body: cuerpo })
      const r = await D<{ conversation: Conversacion; messages: Mensaje[] }>(CLIENT_API.get(`/sd/channels/livechat/${conv.id}/messages`, { params: { after: ultimo.current || undefined } }))
      setConv(r.conversation); anadir(r.messages)
    } catch { setError(tr('sdm_error')) }
  }
  const pedirPersona = async () => {
    if (!conv) return
    try { setConv(await D<Conversacion>(CLIENT_API.post(`/sd/channels/livechat/${conv.id}/agent`))) }
    catch { setError(tr('sdm_error')) }
  }

  const textoDe = (m: Mensaje) => m.author_type === 'system' ? tr(`sdm_evento_${m.body}`) : m.body
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
            </div>
          ))}
        </div>
        {error && <div role="alert" className="u-danger u-text2-xs">{error}</div>}
        {conv?.status !== 'closed' && (
          <div className="u-row-8">
            <PortalInput className="u-flex1" value={texto} aria-label={tr('sdm_chat')} placeholder={tr('sdm_chat_placeholder')}
              onChange={e => setTexto(e.target.value)} onKeyDown={e => { if (e.key === 'Enter') enviar() }} />
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
