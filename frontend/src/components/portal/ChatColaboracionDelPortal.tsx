/**
 * Pestaña «Chat» del portal de clientes (24-11-2026, docs/portal/CHAT_DEL_PORTAL.md §9).
 *
 * Las conversaciones a las que el equipo invita al cliente desde el chat interno
 * (dominio de colaboración, `/portal/collaboration/*`), con lo mismo que las
 * conversaciones formales y reutilizando sus piezas: `AdjuntoDelChat` (vista
 * previa y descarga por la API), `LlamadaDelPortal` (sala de LiveKit),
 * `SelectorDeEmoji`, `REACCIONES_RAPIDAS` y `TextoConEnlaces` del kit, y los
 * ajustes por empresa `portal_chat`.
 *
 * El cliente NO puede iniciar llamadas: solo ve el aviso de llamada entrante
 * (Aceptar / Rechazar) y cuelga. El servidor lo impone (403
 * `portal_llamada_solo_operador`).
 */
import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Check, CheckCheck, MessageSquare, Paperclip, Pencil, Phone, PhoneIncoming, PhoneOff, Reply, Send, Trash2, Video, X } from 'lucide-react'
import { apiWsUrl } from '../../services/api'
import { useToast } from '../../context/ToastContext'
import { confirmar } from '../../context/ConfirmContext'
import { fmtDateTime } from '../../utils/helpers'
import { CLIENT_API, useClientAuth, useErrorDelPortal, useLang } from '../../pages/portal-client/portalClientContext'
import { Button, IconButton, Pulsable, REACCIONES_RAPIDAS, SelectorDeEmoji, Textarea, TextoConEnlaces } from '../ui'
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
  const [borrador, setBorrador] = useState('')
  const [respondiendo, setRespondiendo] = useState<MensajeColab | null>(null)
  const [editando, setEditando] = useState<MensajeColab | null>(null)
  const [escribe, setEscribe] = useState<string | null>(null)
  const [llamada, setLlamada] = useState<PortalLlamada | null>(null)
  const fichero = useRef<HTMLInputElement | null>(null)
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
        <div className="poadse-grid-1">
          <div className="portalad-sx4">
            {conversaciones.map(c => (
              <Pulsable className={`poadse-box-29 ${activa === c.id ? 'portal-advanced-sections-m7' : 'portal-advanced-sections-m8'}`} key={c.id} onClick={() => setActiva(c.id)}>
                <MessageSquare size={13} aria-hidden="true" /> {c.title}
              </Pulsable>
            ))}
          </div>
          <div className="portalad-sx5">
            <div className="poadse-box-14">
              {mensajes.map(m => {
                const mio = !!clienteId && m.client_user_id === clienteId
                const borrado = m.status === 'deleted'
                const reacciones = agruparReacciones(m, clienteId)
                return (
                  <div key={m.id} role="article" aria-label={t('governedconversations.mensaje_de', { name: m.author_name || '' })}
                    className={`u-mb-10 chat-portal-burbuja${borrado ? ' chat-portal-burbuja--borrada' : ''}`}>
                    <div className="u-text3-xs">
                      {m.author_name || (mio ? t('pas_you') : t('dashboard_team'))} · {fmtDateTime(m.sent_at)}
                      {m.edited_at && !borrado && <span className="chat-portal-editado"> · {t('governedconversations.editado')}</span>}
                    </div>
                    {m.reply_to && (
                      <blockquote className="chat-portal-cita">
                        <span className="u-sm-700">{m.reply_to.author_name || ''}</span>
                        <span className="chat-portal-cita__texto">{m.reply_to.is_deleted ? t('governedconversations.mensaje_borrado') : m.reply_to.body}</span>
                      </blockquote>
                    )}
                    {borrado
                      ? <div className="chat-portal-borrado">{t('governedconversations.mensaje_borrado')}</div>
                      : (m.type !== 'file' || !(m.attachments || []).some(a => a.name === m.body)) && <TextoConEnlaces texto={m.body || ''} className="poadse-txt-4 chat-portal-texto" />}
                    {!borrado && (m.attachments || []).length > 0 && (
                      <div className="chat-portal-adjuntos">
                        {m.attachments.map(a => (
                          <AdjuntoDelChat key={a.id} adjunto={a} cargar={cargarAdjunto} t={t} onError={fallo('governedconversations.err_descargar')} />
                        ))}
                      </div>
                    )}
                    {reacciones.length > 0 && (
                      <div className="chat-portal-reacciones">
                        {reacciones.map(([emoji, g]) => (
                          <Pulsable key={emoji} type="button" className={`chat-portal-reaccion${g.mia ? ' chat-portal-reaccion--mia' : ''}`}
                            aria-pressed={g.mia} onClick={() => reaccionar.mutate({ id: m.id, emoji })}
                            aria-label={t('governedconversations.reaccion_de', { emoji, n: g.n })}>{emoji} <span>{g.n}</span></Pulsable>
                        ))}
                      </div>
                    )}
                    {!borrado && (
                      <div className="chat-portal-acciones" role="toolbar" aria-label={t('governedconversations.acciones_del_mensaje')}>
                        {REACCIONES_RAPIDAS.slice(0, 4).map(e => (
                          <Pulsable key={e} type="button" className="chat-portal-reaccion-rapida" onClick={() => reaccionar.mutate({ id: m.id, emoji: e })}
                            aria-label={t('governedconversations.reaccionar_con', { emoji: e })}>{e}</Pulsable>
                        ))}
                        <SelectorDeEmoji tamano="xs" ariaLabel={t('governedconversations.reaccionar')} onElegir={e => reaccionar.mutate({ id: m.id, emoji: e })} />
                        <IconButton variante="caja" tamano="xs" ariaLabel={t('governedconversations.responder')} onClick={() => { setEditando(null); setRespondiendo(m) }}>
                          <Reply size={13} aria-hidden="true" />
                        </IconButton>
                        {mio && (m.type === 'text' || m.type === 'file') && (
                          <>
                            <IconButton variante="caja" tamano="xs" ariaLabel={t('governedconversations.editar')} onClick={() => { setRespondiendo(null); setEditando(m); setBorrador(m.body || '') }}>
                              <Pencil size={13} aria-hidden="true" />
                            </IconButton>
                            <IconButton variante="caja" tamano="xs" tono="peligro" ariaLabel={t('governedconversations.borrar')} onClick={() => pedirBorrado(m)}>
                              <Trash2 size={13} aria-hidden="true" />
                            </IconButton>
                          </>
                        )}
                      </div>
                    )}
                    {mio && !borrado && (
                      <div className="chat-portal-estado">
                        {leidoPorElEquipo(m.sent_at, conversacion?.team_last_read_at)
                          ? <><CheckCheck size={12} aria-hidden="true" /> {t('governedconversations.leido')}</>
                          : <><Check size={12} aria-hidden="true" /> {t('governedconversations.enviado')}</>}
                      </div>
                    )}
                  </div>
                )
              })}
              {escribe === activa && (
                <div className="chat-portal-escribiendo" aria-live="polite">
                  {t('governedconversations.escribiendo', { name: t('dashboard_team') })}
                </div>
              )}
            </div>
            {(respondiendo || editando) && (
              <div className="chat-portal-contexto" role="status">
                {editando ? <Pencil size={13} aria-hidden="true" /> : <Reply size={13} aria-hidden="true" />}
                <span className="chat-portal-contexto__texto">
                  {editando ? t('governedconversations.editando') : `${t('governedconversations.respondiendo_a', { name: respondiendo?.author_name || '' })}: ${String(respondiendo?.body || '').slice(0, 120)}`}
                </span>
                <IconButton ariaLabel={t(editando ? 'governedconversations.cancelar_edicion' : 'governedconversations.cancelar_respuesta')}
                  onClick={() => { setEditando(null); setRespondiendo(null); if (editando) setBorrador('') }}>
                  <X size={13} aria-hidden="true" />
                </IconButton>
              </div>
            )}
            <div className="poadse-row-15">
              <SelectorDeEmoji ariaLabel={t('governedconversations.insertar_emoji')} onElegir={e => setBorrador(v => `${v}${e}`)} />
              {ajustes?.attachments_enabled && !editando && (
                <>
                  <input ref={fichero} type="file" className="chat-portal-oculto" accept={aceptados} aria-hidden="true" tabIndex={-1}
                    onChange={(e) => { const f = e.target.files?.[0]; if (f) adjuntar.mutate(f); e.target.value = '' }} />
                  <IconButton variante="caja" ariaLabel={t('governedconversations.adjuntar')} disabled={adjuntar.isPending} onClick={() => fichero.current?.click()}>
                    <Paperclip size={15} aria-hidden="true" />
                  </IconButton>
                </>
              )}
              <Textarea aria-label={t('portaladvanced.escribe_un_mensaje')} value={borrador}
                onChange={e => { setBorrador(e.target.value); if (e.target.value.trim()) avisarEscribiendo() }}
                onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); if (borrador.trim()) enviar.mutate() } }}
                placeholder={t('portaladvanced.escribe_un_mensaje')} rows={1}
                className="u-flex1-min0" inputClassName="poadse-box-15" />
              <Button size="sm" icon={<Send size={13} />} onClick={() => borrador.trim() && enviar.mutate()} disabled={!borrador.trim()} loading={enviar.isPending || adjuntar.isPending}>
                {editando ? t('governedconversations.guardar_edicion') : t('chat.send')}
              </Button>
            </div>
          </div>
        </div>
      )}

      {llamada && (
        <LlamadaDelPortal llamada={llamada} titulo={conversacion?.title || t('governedconversations.llamada')} onColgar={colgar} t={t} />
      )}
    </>
  )
}
