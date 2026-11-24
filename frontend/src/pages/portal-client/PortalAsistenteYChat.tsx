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
 *   24-11-2026 (docs/portal/CHAT_DEL_PORTAL.md §10): igual que el chat interno
 *   (imágenes y ficheros, emojis y reacciones, citar, editar/borrar con rastro,
 *   enlaces seguros, «leído»; llamadas solo del equipo: aceptar o rechazar).
 *   17-11-2026: en tiempo real por el WebSocket del portal (mensaje nuevo,
 *   «escribiendo…», «leído» y traspaso); sondea solo si el socket no está.
 *
 * Textos en todos los idiomas del portal (`i18n/portal/*.ts`, claves `sdm_*`).
 */
import { Fragment, useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import { AlertTriangle, Bot, BookOpen, Check, MessagesSquare, Pencil, Phone, PhoneIncoming, PhoneOff, Reply, UserRound, Video, X } from 'lucide-react'
import { CLIENT_API, useClientAuth, useErrorDelPortal, useIdiomaDelPortal, useLang } from './portalClientContext'
import { Button } from '../../components/ui'
import { AvisoDelEditor, CabeceraDeConversacion, EditorDeChat, Escribiendo, FilaDeMensaje, MensajeDeSistema, PanelDeChat, PantallaDeChat, SeparadorDeDia, ZonaDeMensajes, cambiaDeDia } from '../../components/chat'
import { confirmar } from '../../context/ConfirmContext'
import { chatEnVivoApi } from '../../components/portal/chatEnVivoApi'
import MensajeDelChatEnVivo from '../../components/portal/MensajeDelChatEnVivo'
import LlamadaDelPortal from '../../components/portal/LlamadaDelPortal'
import type { MensajeDeCanal } from '../../services/api/serviceDeskMercado'
import type { PortalAjustesDelChat, PortalLlamada } from '../../services/api/tipos-alm'
import '../../components/portal/ChatDelPortal.css'
import { PortalButton, PortalCard, PortalTabs } from './PortalUI'
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
interface Turno { id: number; pregunta: string; respuesta: Intencion; fecha: string }
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
      setTurnos(prev => [...prev, { id: siguiente.current++, pregunta, respuesta, fecha: new Date().toISOString() }])
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
        {/* 24-11-2026 (burbujas «como WhatsApp»): la misma fila y el mismo editor que los
            chats; la pregunta del cliente a la derecha y el asistente a la izquierda. */}
        {(turnos.length > 0 || enviando) && (
          <div className="sdm-chat" role="log" aria-live="polite" aria-label={tr('sdm_asistente')}>
            {turnos.map(t => (
              <Fragment key={t.id}>
                <FilaDeMensaje propio autor={tr('pas_you')} fecha={t.fecha}
                  textos={{ mensajeDe: tr('governedconversations.mensaje_de', { name: tr('pas_you') }) }}
                  cuerpo={<div className="chat-msg__body">{t.pregunta}</div>} />
                <FilaDeMensaje autor={tr('sdm_asistente')} fecha={t.fecha} esBot
                  textos={{ mensajeDe: tr('governedconversations.mensaje_de', { name: tr('sdm_asistente') }) }}
                  cuerpo={<div className="chat-msg__body"><Respuesta r={t.respuesta} enviando={enviando} onDecidir={(a, ok) => decidir(t, a, ok)} /></div>} />
              </Fragment>
            ))}
            {enviando && (
              <FilaDeMensaje autor={tr('sdm_asistente')} fecha={null} esBot
                textos={{ mensajeDe: tr('governedconversations.mensaje_de', { name: tr('sdm_asistente') }) }}
                cuerpo={<div className="chat-msg__pensando" role="status">{tr('portalaichatwidget.pensando')}</div>} />
            )}
          </div>
        )}
        <EditorDeChat
          valor={texto}
          onCambiar={setTexto}
          onEnviar={() => { if (texto.trim() && !enviando) void preguntar() }}
          etiquetaCampo={tr('sdm_asistente')}
          placeholder={tr('sdm_placeholder')}
          etiquetaEnviar={tr('sdm_enviar')}
          etiquetaEmoji={tr('governedconversations.insertar_emoji')}
          desactivado={enviando}
        />
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

/**
 * Chat en vivo de Soporte, lado del cliente (24-11-2026, docs/portal/CHAT_DEL_PORTAL.md §10).
 *
 * Igual que el chat interno («un solo chat»): `FilaDeMensaje` con la barra
 * flotante (reaccionar, responder citando, editar y borrar lo propio dentro del
 * plazo de la empresa) y `EditorDeChat` (clip para imágenes y ficheros, emoji y
 * enviar dentro del cuadro). «Escribiendo…» y «Leído» por mensaje. Llamadas:
 * el cliente NO llama; ve el aviso de llamada del equipo con Aceptar y
 * Rechazar y cuelga (el servidor impone «solo el operador llama»).
 */
export function PortalChatEnVivo() {
  const tr = useLang()
  const errorDe = useErrorDelPortal()
  const client = useClientAuth()?.client ?? null
  const clienteId = client?.id ? String(client.id) : null
  const api = useMemo(() => chatEnVivoApi(CLIENT_API, 'client'), [])
  const [conv, setConv] = useState<Conversacion | null>(null)
  const [mensajes, setMensajes] = useState<MensajeDeCanal[]>([])
  const [texto, setTexto] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [agenteEscribe, setAgenteEscribe] = useState(false)
  const [respondiendo, setRespondiendo] = useState<MensajeDeCanal | null>(null)
  const [editando, setEditando] = useState<MensajeDeCanal | null>(null)
  const [enviando, setEnviando] = useState(false)
  const [ajustes, setAjustes] = useState<PortalAjustesDelChat | null>(null)
  const [sonando, setSonando] = useState<PortalLlamada[]>([])
  const [llamada, setLlamada] = useState<PortalLlamada | null>(null)
  const ultimo = useRef<string | null>(null)
  const avisoDeEscritura = useRef(0)
  const finDeEscritura = useRef<ReturnType<typeof setTimeout> | null>(null)
  const convId = conv?.id
  const fallo = (clave: string) => (e: unknown) => setError(errorDe(e, tr(clave)))

  const anadir = useCallback((nuevos: MensajeDeCanal[]) => {
    if (!nuevos.length) return
    setMensajes(prev => {
      const porId = new Map(prev.map(m => [m.id, m]))
      const salida = prev.map(m => nuevos.find(n => n.id === m.id) || m)
      for (const n of nuevos) if (!porId.has(n.id)) salida.push(n)
      return salida
    })
    ultimo.current = nuevos[nuevos.length - 1].id
  }, [])
  const empezar = async (cuerpo?: string) => {
    try {
      const r = await D<{ conversation: Conversacion; messages: MensajeDeCanal[] }>(CLIENT_API.post('/sd/channels/livechat', { body: cuerpo, language: document.documentElement.lang || undefined }))
      setConv(r.conversation); anadir(r.messages)
    } catch (e) { fallo('sdm_error')(e) }
  }
  useEffect(() => { empezar() /* abre o sigue la conversación */ // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])
  useEffect(() => { api.ajustes().then(setAjustes).catch(() => { /* accesorio: sin ajustes no se ofrece adjuntar */ }) }, [api])
  const ponerAlDia = useCallback(async (id: string, completo = false) => {
    try {
      const r = await D<{ conversation: Conversacion; messages: MensajeDeCanal[] }>(CLIENT_API.get(`/sd/channels/livechat/${id}/messages`, { params: { after: completo ? undefined : ultimo.current || undefined } }))
      setConv(r.conversation)
      if (completo) { setMensajes(r.messages); ultimo.current = r.messages.length ? r.messages[r.messages.length - 1].id : null }
      else anadir(r.messages)
    } catch { /* se reintenta en el siguiente aviso o sondeo */ }
  }, [anadir])
  const mirarLlamadas = useCallback(() => {
    api.sonando().then(setSonando).catch(() => { /* accesorio: sin la lista, el aviso llega con el siguiente evento */ })
  }, [api])

  // Tiempo real: mensajes (nuevos, editados, borrados), reacciones, «escribiendo…», «leído», traspaso y llamadas.
  const enVivo = usePortalEnVivo(true, (m: MensajeDelPortal) => {
    if (m.type !== 'livechat' || !convId || m.conversation_id !== convId) return
    if (m.event === 'message' && m.message) {
      anadir([m.message as MensajeDeCanal])
      if ((m.message as MensajeDeCanal).author_type === 'agent') setAgenteEscribe(false)
    } else if (m.event === 'reaction') {
      void ponerAlDia(convId, true)
    } else if (m.event === 'call') {
      mirarLlamadas()
      if (llamada && m.call_id === llamada.id && ['ended', 'declined', 'missed'].includes(String(m.status))) setLlamada(null)
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
  // Al (re)conectar se recupera lo que llegara sin socket; sin socket, sondeo (mensajes y llamadas).
  useEffect(() => {
    if (!convId) return undefined
    mirarLlamadas()
    if (enVivo) { void ponerAlDia(convId, true); return undefined }
    const id = setInterval(() => { void ponerAlDia(convId, true); mirarLlamadas() }, SONDEO_DEL_CHAT_MS)
    return () => clearInterval(id)
  }, [convId, enVivo, ponerAlDia, mirarLlamadas])
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
    if (!conv || !texto.trim() || enviando) return
    const cuerpo = texto.trim(); setError(null); setEnviando(true)
    try {
      if (editando) {
        anadir([await api.editar(conv.id, editando.id, cuerpo) as MensajeDeCanal])
        setEditando(null)
      } else {
        const r = await D<{ message: MensajeDeCanal | null }>(CLIENT_API.post(`/sd/channels/livechat/${conv.id}/messages`, { body: cuerpo, reply_to_message_id: respondiendo?.id || undefined }))
        if (r?.message) anadir([r.message])
        setRespondiendo(null)
        // Sin socket, la respuesta del asistente se recoge ahora; con socket llega sola.
        if (!enVivo) await ponerAlDia(conv.id)
      }
      setTexto('')
    } catch (e) { fallo(editando ? 'governedconversations.err_editar' : 'sdm_error')(e) }
    finally { setEnviando(false) }
  }
  const adjuntar = async (f: File) => {
    if (!conv) return
    setError(null); setEnviando(true)
    try {
      anadir([await api.subir(conv.id, f, { caption: texto.trim() || undefined, replyTo: respondiendo?.id }) as MensajeDeCanal])
      setTexto(''); setRespondiendo(null)
    } catch (e) { fallo('governedconversations.err_adjuntar')(e) }
    finally { setEnviando(false) }
  }
  const reaccionar = (m: MensajeDeCanal, emoji: string) => {
    if (!conv) return
    api.reaccionar(conv.id, m.id, emoji).then(() => ponerAlDia(conv.id, true)).catch(fallo('governedconversations.err_reaccion'))
  }
  const borrar = async (m: MensajeDeCanal) => {
    if (!conv) return
    const ok = await confirmar({
      title: tr('governedconversations.borrar'), message: tr('governedconversations.confirmar_borrar'),
      confirmLabel: tr('governedconversations.borrar'), cancelLabel: tr('common.cancel'), danger: true,
    })
    if (!ok) return
    try { anadir([await api.borrar(conv.id, m.id) as MensajeDeCanal]) } catch (e) { fallo('governedconversations.err_borrar')(e) }
  }
  const pedirPersona = async () => {
    if (!conv) return
    try { setConv(await D<Conversacion>(CLIENT_API.post(`/sd/channels/livechat/${conv.id}/agent`))) }
    catch (e) { fallo('sdm_error')(e) }
  }
  // Llamadas: solo aceptar, rechazar o colgar (el cliente no inicia nunca).
  const entrante = !llamada ? sonando.find(c => c.conversation_id === convId) || null : null
  const aceptar = async (c: PortalLlamada) => {
    try { setLlamada(await api.aceptar(c.conversation_id, c.id)); setSonando([]) } catch (e) { fallo('governedconversations.err_llamada')(e) }
  }
  const rechazar = async (c: PortalLlamada) => {
    try { await api.rechazar(c.conversation_id, c.id) } catch (e) { fallo('governedconversations.err_llamada')(e) }
    mirarLlamadas()
  }
  const colgar = () => {
    const actual = llamada
    setLlamada(null)
    if (actual) api.colgar(actual.conversation_id, actual.id).catch(() => { /* accesorio: si ya terminó no hay nada que deshacer */ })
  }

  const textoDeSistema = (m: MensajeDeCanal) => tr(`sdm_evento_${m.body}`)
  const autorDe = (tipo: string, nombre?: string | null, mio?: boolean) =>
    tipo === 'bot' ? tr('sdm_asistente') : mio ? tr('pas_you') : nombre || tr(tipo === 'customer' ? 'governedconversations.remitente_cliente' : 'governedconversations.remitente_equipo')
  const leidoHasta = conv?.agent_read_at ? Date.parse(conv.agent_read_at) : null
  const activa = conv?.status !== 'closed'
  // 24-11-2026 («un solo chat»): el panel del chat interno (cabecera, zona de mensajes y editor).
  return (
    <div className="u-stack-12">
        {entrante && (
          <div className="chat-portal-entrante" role="alert">
            <PhoneIncoming size={18} aria-hidden="true" />
            <div className="u-flex1-min0">
              <div className="u-sm-700">{tr(entrante.kind === 'video' ? 'governedconversations.videollamada_entrante' : 'governedconversations.llamada_entrante')}</div>
              <div className="u-text2-sm">{tr('governedconversations.llamada_no_se_graba')}</div>
            </div>
            <Button size="sm" icon={entrante.kind === 'video' ? <Video size={13} /> : <Phone size={13} />} onClick={() => aceptar(entrante)}>
              {tr('governedconversations.aceptar')}
            </Button>
            <Button size="sm" variant="danger" icon={<PhoneOff size={13} />} onClick={() => rechazar(entrante)}>
              {tr('governedconversations.rechazar')}
            </Button>
          </div>
        )}
      <PantallaDeChat incrustada>
      <PanelDeChat etiqueta={tr('sdm_chat')}>
        <CabeceraDeConversacion titulo={tr('sdm_chat')} icono={<MessagesSquare size={18} aria-hidden="true" />}
          subtitulo={conv ? `${tr(`sdm_conv_${conv.status}`)}${conv.ticket_number ? ` · ${conv.ticket_number}` : ''}` : null}
          acciones={conv?.status === 'bot'
            ? <PortalButton variant="secondary" size="sm" icon={<UserRound size={13} />} onClick={pedirPersona}>{tr('sdm_hablar_persona')}</PortalButton>
            : conv?.status === 'closed'
              ? <PortalButton variant="secondary" size="sm" onClick={() => { setMensajes([]); ultimo.current = null; empezar() }}>{tr('sdm_nueva_conversacion')}</PortalButton>
              : null} />
        <ZonaDeMensajes etiqueta={tr('sdm_chat')}>
          {mensajes.length === 0 && <div className="u-text3-xs">{tr('sdm_chat_bienvenida')}</div>}
          {mensajes.map((m, i) => {
            // 24-11-2026 (burbujas): separador de día; sistema en pastilla centrada; lo del cliente a la derecha.
            const prev = mensajes[i - 1]
            const nuevoDia = cambiaDeDia(prev?.created_at, m.created_at)
            if (m.author_type === 'system') return (
              <Fragment key={m.id}>{nuevoDia && <SeparadorDeDia fecha={m.created_at} />}<MensajeDeSistema>{textoDeSistema(m)}</MensajeDeSistema></Fragment>
            )
            const mio = m.author_type === 'customer'
            const compacto = !!prev && !nuevoDia && prev.author_type === m.author_type && prev.author_user_id === m.author_user_id
              && !!prev.created_at && !!m.created_at && Date.parse(m.created_at) - Date.parse(prev.created_at) < 5 * 60_000
            return (
              <Fragment key={m.id}>
              {nuevoDia && <SeparadorDeDia fecha={m.created_at} />}
              <MensajeDelChatEnVivo m={m} lado="client" convId={conv?.id || ''} api={api}
                autor={autorDe(m.author_type, m.author_name, mio)}
                autorDeCita={(tipo) => autorDe(tipo, null, tipo === 'customer')}
                esMio={mio} quien={{ clientId: clienteId }} activa={activa} compacto={compacto}
                extras={m.author_type === 'bot' ? <div className="u-text3-2xs">{tr('sdm_articulos_sugeridos')}</div> : null}
                leido={mio ? !!(leidoHasta && m.created_at && leidoHasta >= Date.parse(m.created_at)) : null}
                onResponder={(x) => { setEditando(null); setRespondiendo(x) }}
                onEditar={(x) => { setRespondiendo(null); setEditando(x); setTexto(x.body || '') }}
                onBorrar={borrar}
                onReaccionar={reaccionar}
                onError={fallo('governedconversations.err_descargar')}
              />
              </Fragment>
            )
          })}
        </ZonaDeMensajes>
        <Escribiendo texto={agenteEscribe ? tr('sdm_escribiendo') : null} />
        {error && <div role="alert" className="u-danger u-text2-xs">{error}</div>}
        {activa && (
          <EditorDeChat
            valor={texto}
            onCambiar={escribiendo}
            onEnviar={() => { void enviar() }}
            etiquetaCampo={tr('sdm_chat')}
            placeholder={tr('sdm_chat_placeholder')}
            etiquetaEnviar={editando ? tr('governedconversations.guardar_edicion') : tr('sdm_enviar')}
            desactivado={!conv}
            adjuntar={ajustes?.attachments_enabled && !editando ? {
              etiqueta: `${tr('governedconversations.adjuntar')} · ${tr('governedconversations.adjunto_limite', { mb: ajustes.max_file_mb })}`,
              aceptar: (ajustes.allowed_extensions || []).join(','), onFichero: (f) => { void adjuntar(f) }, desactivado: enviando,
            } : null}
            etiquetaEmoji={tr('governedconversations.insertar_emoji')}
            encima={<>
              {respondiendo && !editando && (
                <AvisoDelEditor icono={<Reply size={12} aria-hidden="true" />}
                  texto={`${tr('governedconversations.respondiendo_a', { name: autorDe(respondiendo.author_type, respondiendo.author_name, respondiendo.author_type === 'customer') })}: ${String(respondiendo.body || '').slice(0, 120)}`}
                  etiquetaCancelar={tr('governedconversations.cancelar_respuesta')} onCancelar={() => setRespondiendo(null)} />
              )}
              {editando && (
                <AvisoDelEditor icono={<Pencil size={12} aria-hidden="true" />} texto={tr('governedconversations.editando')}
                  etiquetaCancelar={tr('governedconversations.cancelar_edicion')} onCancelar={() => { setEditando(null); setTexto('') }} />
              )}
            </>}
          />
        )}
      </PanelDeChat>
      </PantallaDeChat>
      {llamada && <LlamadaDelPortal llamada={llamada} titulo={tr('sdm_chat')} onColgar={colgar} t={tr} />}
    </div>
  )
}
