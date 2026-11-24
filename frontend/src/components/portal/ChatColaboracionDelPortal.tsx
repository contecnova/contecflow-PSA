/**
 * Pestaña «Chat» del portal de clientes (24-11-2026, docs/portal/CHAT_DEL_PORTAL.md §9).
 *
 * Las conversaciones a las que el equipo invita al cliente desde el chat interno
 * (dominio de colaboración, `/portal/collaboration/*`), con lo mismo que las
 * conversaciones formales y reutilizando sus piezas: `AdjuntoDelChat` (vista
 * previa y descarga por la API), `LlamadaDelPortal` (sala de LiveKit),
 * `SelectorDeEmoji` y `TextoConEnlaces` del kit, la fila y el editor del chat
 * interno (`components/chat`, «un solo chat», 24-11-2026) y los
 * ajustes por empresa `portal_chat`.
 *
 * El cliente NO puede iniciar llamadas: solo ve el aviso de llamada entrante
 * (Aceptar / Rechazar) y cuelga. El servidor lo impone (403
 * `portal_llamada_solo_operador`).
 */
import { Fragment, useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { MessageSquare, Pencil, Phone, PhoneIncoming, PhoneOff, Reply, Trash2, Video } from 'lucide-react'
import { apiWsUrl } from '../../services/api'
import { useToast } from '../../context/ToastContext'
import { confirmar } from '../../context/ConfirmContext'
import { CLIENT_API, useClientAuth, useErrorDelPortal, useLang } from '../../pages/portal-client/portalClientContext'
import { Button, TextoConEnlaces } from '../ui'
import { type AccionDeMensaje, AvisoDelEditor, CabeceraDeConversacion, EditorDeChat, Escribiendo, EstadoDeEntrega, FilaDeConversacion, FilaDeMensaje, ListaDeChats, PanelDeChat, PantallaDeChat, SeparadorDeDia, ZonaDeMensajes, agruparReacciones as agruparReaccionesDelChat, cambiaDeDia } from '../chat'
import { POLL_ACTIVE_CHAT_MS, POLL_FAST_MS, POLL_FREQUENT_MS, WS_HEARTBEAT_MS } from '../../constants/timings'
import type { PortalAjustesDelChat, PortalLlamada } from '../../services/api/tipos-alm'
import AdjuntoDelChat from './AdjuntoDelChat'
import LlamadaDelPortal from './LlamadaDelPortal'
import './ChatDelPortal.css'

const BASE = '/portal/collaboration'
const ESCRIBIENDO_CADA_MS = 3_000
const ESCRIBIENDO_DURA_MS = 6_000

/** `list_conversations` (app/services/collaboration/portal.py). */
interface ConversacionColab {
  id: string
  title?: string | null
  team_last_read_at?: string | null
}

interface AdjuntoColab {
  id: string
  name: string
  mime_type: string | null
  size_bytes: number
  is_quarantined: boolean
}

/** `_serialize_message` (app/services/collaboration/messages.py). */
export interface MensajeColab {
  id: string
  conversation_id: string
  user_id: string | null
  client_user_id: string | null
  author_name: string | null
  type: string
  status: string
  body: string | null
  attachments: AdjuntoColab[]
  reactions: { emoji: string; user_id: string | null; client_user_id: string | null }[]
  edited_at: string | null
  deleted_at: string | null
  sent_at: string
  reply_to?: { id: string; author_name: string | null; body: string; is_deleted: boolean } | null
}

interface Aviso { type?: string; event?: string; conversation_id?: string | null; call_id?: string | null }

/** Agrupa reacciones por emoji y marca las del propio cliente. */
export function agruparReacciones(m: Pick<MensajeColab, 'reactions'>, clienteId: string | null) {
  const grupos: Record<string, { n: number; mia: boolean }> = {}
  for (const r of m.reactions || []) {
    const g = grupos[r.emoji] || (grupos[r.emoji] = { n: 0, mia: false })
    g.n += 1
    if (clienteId && r.client_user_id === clienteId) g.mia = true
  }
  return Object.entries(grupos)
}

/** Leído por el equipo: el mensaje es anterior o igual a su última lectura. */
export function leidoPorElEquipo(enviado: string, ultimaLectura?: string | null): boolean {
  if (!ultimaLectura) return false
  return new Date(enviado).getTime() <= new Date(ultimaLectura).getTime()
}

export default function ChatColaboracionDelPortal({ vacio }: { vacio: ReactNode }) {
  const t = useLang()
  const errorDe = useErrorDelPortal()
  const toast = useToast()
  const qc = useQueryClient()
  const { client } = useClientAuth()
  const clienteId = client?.id ? String(client.id) : null
  const [activa, setActiva] = useState<string | null>(null)
  const [filtro, setFiltro] = useState('')
  const [borrador, setBorrador] = useState('')
  const [respondiendo, setRespondiendo] = useState<MensajeColab | null>(null)
  const [editando, setEditando] = useState<MensajeColab | null>(null)
  const [escribe, setEscribe] = useState<string | null>(null)
  const [llamada, setLlamada] = useState<PortalLlamada | null>(null)
  const socketRef = useRef<WebSocket | null>(null)
  const ultimoAviso = useRef(0)
  const temporizador = useRef<number | null>(null)

  const { data: conversaciones = [], isLoading } = useQuery<ConversacionColab[]>({
    queryKey: ['portal-collab-conversations'],
    queryFn: () => CLIENT_API.get(`${BASE}/conversations`).then(r => r.data),
    refetchInterval: POLL_FREQUENT_MS,
  })
  useEffect(() => {
    if (!activa && conversaciones.length > 0) setActiva(conversaciones[0].id)
  }, [conversaciones, activa])
  useEffect(() => { setRespondiendo(null); setEditando(null); setBorrador('') }, [activa])

  const { data: mensajes = [] } = useQuery<MensajeColab[]>({
    queryKey: ['portal-collab-messages', activa],
    queryFn: () => CLIENT_API.get(`${BASE}/conversations/${activa}/messages`).then(r => r.data),
    enabled: !!activa,
    refetchInterval: POLL_ACTIVE_CHAT_MS,
  })
  const { data: ajustes } = useQuery<PortalAjustesDelChat>({
    queryKey: ['portal-collab-settings'],
    queryFn: () => CLIENT_API.get(`${BASE}/settings`).then(r => r.data),
    staleTime: POLL_FREQUENT_MS,
  })
  const { data: sonando = [] } = useQuery<PortalLlamada[]>({
    queryKey: ['portal-collab-ringing'],
    queryFn: () => CLIENT_API.get(`${BASE}/calls/ringing`).then(r => r.data),
    refetchInterval: POLL_FAST_MS,
  })
  const entrante = !llamada ? sonando[0] || null : null
  const conversacion = conversaciones.find(c => c.id === activa) || null

  // Marca leída la conversación abierta hasta el último mensaje.
  const ultimo = mensajes.length ? mensajes[mensajes.length - 1].id : null
  useEffect(() => {
    if (!activa || !ultimo) return
    CLIENT_API.post(`${BASE}/conversations/${activa}/read`, { last_message_id: ultimo })
      .catch(() => { /* accesorio: sin marca de leído el equipo ve el mensaje como no leído */ })
  }, [activa, ultimo])

  const refrescar = useCallback(() => {
    qc.invalidateQueries({ queryKey: ['portal-collab-messages'] })
    qc.invalidateQueries({ queryKey: ['portal-collab-conversations'] })
    qc.invalidateQueries({ queryKey: ['portal-collab-ringing'] })
  }, [qc])
  const fallo = useCallback((clave: string) => (e: unknown) => toast.error(errorDe(e, t(clave))), [errorDe, t, toast])

  const enviar = useMutation({
    mutationFn: (): Promise<unknown> => editando
      ? CLIENT_API.put(`${BASE}/messages/${editando.id}`, { body: borrador })
      : CLIENT_API.post(`${BASE}/messages`, { conversation_id: activa, body: borrador, parent_message_id: respondiendo?.id || undefined }),
    onSuccess: () => { setBorrador(''); setRespondiendo(null); setEditando(null); refrescar() },
    onError: (e: unknown) => fallo(editando ? 'governedconversations.err_editar' : 'pas_err_generic')(e),
  })
  const adjuntar = useMutation({
    mutationFn: (f: File) => {
      const fd = new FormData()
      fd.append('file', f, f.name)
      if (borrador.trim()) fd.append('caption', borrador.trim())
      if (respondiendo) fd.append('parent_message_id', respondiendo.id)
      return CLIENT_API.post(`${BASE}/conversations/${activa}/attachments`, fd)
    },
    onSuccess: () => { setBorrador(''); setRespondiendo(null); refrescar() },
    onError: fallo('governedconversations.err_adjuntar'),
  })
  const reaccionar = useMutation({
    mutationFn: ({ id, emoji }: { id: string; emoji: string }) => CLIENT_API.post(`${BASE}/messages/${id}/reactions`, { emoji }),
    onSuccess: refrescar,
    onError: fallo('governedconversations.err_reaccion'),
  })
  const borrar = useMutation({
    mutationFn: (id: string) => CLIENT_API.delete(`${BASE}/messages/${id}`),
    onSuccess: refrescar,
    onError: fallo('governedconversations.err_borrar'),
  })
  const aceptar = useMutation({
    mutationFn: (c: PortalLlamada) => CLIENT_API.post(`${BASE}/calls/${c.id}/accept`).then(r => r.data as PortalLlamada),
    onSuccess: (c) => { setLlamada(c); setActiva(c.conversation_id) },
    onError: fallo('governedconversations.err_llamada'),
  })
  const rechazar = useMutation({
    mutationFn: (c: PortalLlamada) => CLIENT_API.post(`${BASE}/calls/${c.id}/decline`),
    onSettled: refrescar,
    onError: fallo('governedconversations.err_llamada'),
  })
  const colgar = () => {
    const actual = llamada
    setLlamada(null)
    if (actual) CLIENT_API.post(`${BASE}/calls/${actual.id}/end`).catch(() => { /* accesorio: si ya terminó no hay nada que deshacer */ })
  }
  const pedirBorrado = async (m: MensajeColab) => {
    const ok = await confirmar({
      title: t('governedconversations.borrar'), message: t('governedconversations.confirmar_borrar'),
      confirmLabel: t('governedconversations.borrar'), cancelLabel: t('common.cancel'), danger: true,
    })
    if (ok) borrar.mutate(m.id)
  }
  const cargarAdjunto = useCallback((id: string) =>
    CLIENT_API.get(`${BASE}/attachments/${id}`, { responseType: 'blob' }).then(r => r.data as Blob), [])

  // ── Tiempo real (WebSocket del portal: avisos `portal_collab` del bus) ──────
  const alAviso = useRef<(a: Aviso) => void>(() => undefined)
  alAviso.current = (a: Aviso) => {
    if (a.type !== 'portal_collab') return
    if (a.event === 'typing' && a.conversation_id) {
      setEscribe(a.conversation_id)
      if (temporizador.current) window.clearTimeout(temporizador.current)
      temporizador.current = window.setTimeout(() => setEscribe(null), ESCRIBIENDO_DURA_MS)
      return
    }
    if (a.event === 'call.ended' && llamada && a.call_id === llamada.id) setLlamada(null)
    refrescar()
  }
  useEffect(() => {
    let socket: WebSocket | null = null
    let cerrado = false
    let ping: number | null = null
    ;(async () => {
      try {
        const r = await CLIENT_API.get('/ws/portal-ticket')
        const ticket = r?.data?.ticket
        if (!ticket || cerrado) return
        socket = new window.WebSocket(apiWsUrl(`/ws/portal-notifications?ticket=${encodeURIComponent(ticket)}`))
        socketRef.current = socket
        socket.onmessage = (ev: MessageEvent) => {
          try { alAviso.current(JSON.parse(String(ev.data))) } catch { /* accesorio: un aviso ilegible no hace nada */ }
        }
        ping = window.setInterval(() => {
          if (socket && socket.readyState === window.WebSocket.OPEN) socket.send(JSON.stringify({ type: 'ping' }))
        }, WS_HEARTBEAT_MS)
      } catch { /* accesorio: sin socket quedan los sondeos */ }
    })()
    return () => {
      cerrado = true
      if (ping) window.clearInterval(ping)
      if (socket && socket.readyState === window.WebSocket.OPEN) socket.close()
      socketRef.current = null
      if (temporizador.current) window.clearTimeout(temporizador.current)
    }
  }, [])
  const avisarEscribiendo = () => {
    const ahora = Date.now()
    const s = socketRef.current
    if (!activa || ahora - ultimoAviso.current < ESCRIBIENDO_CADA_MS || !s || s.readyState !== window.WebSocket.OPEN) return
    ultimoAviso.current = ahora
    s.send(JSON.stringify({ type: 'portal_collab_typing', conversation_id: activa }))
  }

  const aceptados = useMemo(() => (ajustes?.allowed_extensions || []).join(','), [ajustes])

  if (isLoading) return <div className="poadse-box-13">{t('common.loading')}</div>

  return (
    <>
      {entrante && (
        <div className="chat-portal-entrante" role="alert">
          <PhoneIncoming size={18} aria-hidden="true" />
          <div className="u-flex1-min0">
            <div className="u-sm-700">{t(entrante.kind === 'video' ? 'governedconversations.videollamada_entrante' : 'governedconversations.llamada_entrante')}</div>
            <div className="u-text2-sm">{t('governedconversations.llamada_no_se_graba')}</div>
          </div>
          <Button size="sm" icon={entrante.kind === 'video' ? <Video size={13} /> : <Phone size={13} />} loading={aceptar.isPending} onClick={() => aceptar.mutate(entrante)}>
            {t('governedconversations.aceptar')}
          </Button>
          <Button size="sm" variant="danger" icon={<PhoneOff size={13} />} loading={rechazar.isPending} onClick={() => rechazar.mutate(entrante)}>
            {t('governedconversations.rechazar')}
          </Button>
        </div>
      )}

      {conversaciones.length === 0 ? vacio : (
        // 24-11-2026 («un solo chat»): la pantalla del chat interno (components/chat): lista,
        // cabecera, zona de mensajes y editor. El cliente no tiene botones de llamar.
        <PantallaDeChat incrustada>
          <ListaDeChats buscar={{ valor: filtro, onCambiar: setFiltro, etiqueta: t('governedconversations.buscar') }}>
            {conversaciones.filter(c => !filtro || (c.title || '').toLowerCase().includes(filtro.toLowerCase())).map(c => (
              <FilaDeConversacion key={c.id} titulo={c.title || ''} activa={activa === c.id} onClick={() => setActiva(c.id)}
                icono={<MessageSquare size={13} aria-hidden="true" />} />
            ))}
          </ListaDeChats>
          <PanelDeChat etiqueta={conversacion?.title || t('governedconversations.mensajes')}>
            <CabeceraDeConversacion titulo={conversacion?.title || ''} icono={<MessageSquare size={18} aria-hidden="true" />} />
            <ZonaDeMensajes etiqueta={t('governedconversations.mensajes')}>
              {mensajes.map((m, i) => {
                const previo = mensajes[i - 1]
                // 24-11-2026 (burbujas): separador de día; lo del cliente que mira a la derecha.
                const nuevoDia = cambiaDeDia(previo?.sent_at, m.sent_at)
                const compacto = !!previo && !nuevoDia && previo.status !== 'deleted' && m.status !== 'deleted'
                  && (previo.user_id || previo.client_user_id) === (m.user_id || m.client_user_id)
                  && new Date(m.sent_at).getTime() - new Date(previo.sent_at).getTime() < 5 * 60_000
                const mio = !!clienteId && m.client_user_id === clienteId
                const borrado = m.status === 'deleted'
                const autor = m.author_name || (mio ? t('pas_you') : t('dashboard_team'))
                const soloAdjunto = m.type === 'file' && (m.attachments || []).some(a => a.name === m.body)
                const acciones: AccionDeMensaje[] = [
                  { clave: 'responder', etiqueta: t('governedconversations.responder'), icono: <Reply size={13} aria-hidden="true" />, onClick: () => { setEditando(null); setRespondiendo(m) } },
                  ...(mio && (m.type === 'text' || m.type === 'file') ? [
                    { clave: 'editar', etiqueta: t('governedconversations.editar'), icono: <Pencil size={13} aria-hidden="true" />, onClick: () => { setRespondiendo(null); setEditando(m); setBorrador(m.body || '') } },
                    { clave: 'borrar', etiqueta: t('governedconversations.borrar'), icono: <Trash2 size={13} aria-hidden="true" />, onClick: () => { void pedirBorrado(m) }, peligro: true },
                  ] : []),
                ]
                return (
                  <Fragment key={m.id}>
                  {nuevoDia && <SeparadorDeDia fecha={m.sent_at} />}
                  <FilaDeMensaje
                    autor={autor}
                    fecha={m.sent_at}
                    propio={mio}
                    compacto={compacto}
                    borrado={borrado}
                    editado={!!m.edited_at && !borrado}
                    textos={{
                      mensajeDe: t('governedconversations.mensaje_de', { name: autor }),
                      acciones: t('governedconversations.acciones_del_mensaje'),
                      editado: t('governedconversations.editado'),
                      eliminado: t('governedconversations.mensaje_borrado'),
                      reaccion: (emoji, n) => t('governedconversations.reaccion_de', { emoji, n }),
                      reaccionarCon: (emoji) => t('governedconversations.reaccionar_con', { emoji }),
                    }}
                    cita={m.reply_to ? { autor: m.reply_to.author_name || '', texto: m.reply_to.body, borrada: m.reply_to.is_deleted } : null}
                    cuerpo={borrado
                      ? <div className="chat-msg__body">{t('governedconversations.mensaje_borrado')}</div>
                      : (!soloAdjunto && <TextoConEnlaces texto={m.body || ''} className="chat-msg__body" />)}
                    extras={!borrado && (m.attachments || []).length > 0 ? (
                      <div className="chat-msg__attachments">
                        {m.attachments.map(a => (
                          <AdjuntoDelChat key={a.id} adjunto={a} cargar={cargarAdjunto} t={t} onError={fallo('governedconversations.err_descargar')} />
                        ))}
                      </div>
                    ) : null}
                    reacciones={agruparReaccionesDelChat(m.reactions, { clientId: clienteId })}
                    onReaccionar={(emoji) => reaccionar.mutate({ id: m.id, emoji })}
                    acciones={acciones}
                    pie={mio && !borrado ? (
                      <EstadoDeEntrega leido={leidoPorElEquipo(m.sent_at, conversacion?.team_last_read_at)}
                        textoLeido={t('governedconversations.leido')} textoEnviado={t('governedconversations.enviado')} />
                    ) : null}
                  />
                  </Fragment>
                )
              })}
            </ZonaDeMensajes>
            <Escribiendo texto={escribe === activa ? t('governedconversations.escribiendo', { name: t('dashboard_team') }) : null} />
            <EditorDeChat
              valor={borrador}
              onCambiar={(v) => { setBorrador(v); if (v.trim()) avisarEscribiendo() }}
              onEnviar={() => { if (borrador.trim() && !enviar.isPending) enviar.mutate() }}
              etiquetaCampo={t('portaladvanced.escribe_un_mensaje')}
              placeholder={t('portaladvanced.escribe_un_mensaje')}
              etiquetaEnviar={editando ? t('governedconversations.guardar_edicion') : t('chat.send')}
              adjuntar={ajustes?.attachments_enabled && !editando ? {
                etiqueta: t('governedconversations.adjuntar'), aceptar: aceptados,
                onFichero: (f) => adjuntar.mutate(f), desactivado: adjuntar.isPending,
              } : null}
              etiquetaEmoji={t('governedconversations.insertar_emoji')}
              encima={<>
                {respondiendo && !editando && (
                  <AvisoDelEditor icono={<Reply size={12} aria-hidden="true" />}
                    texto={`${t('governedconversations.respondiendo_a', { name: respondiendo.author_name || '' })}: ${String(respondiendo.body || '').slice(0, 120)}`}
                    etiquetaCancelar={t('governedconversations.cancelar_respuesta')} onCancelar={() => setRespondiendo(null)} />
                )}
                {editando && (
                  <AvisoDelEditor icono={<Pencil size={12} aria-hidden="true" />} texto={t('governedconversations.editando')}
                    etiquetaCancelar={t('governedconversations.cancelar_edicion')} onCancelar={() => { setEditando(null); setBorrador('') }} />
                )}
              </>}
            />
          </PanelDeChat>
        </PantallaDeChat>
      )}
      {llamada && (
        <LlamadaDelPortal llamada={llamada} titulo={conversacion?.title || t('governedconversations.llamada')} onColgar={colgar} t={t} />
      )}
    </>
  )
}
