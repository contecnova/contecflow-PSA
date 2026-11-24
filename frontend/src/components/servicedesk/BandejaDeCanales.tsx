/**
 * BandejaDeCanales — conversaciones de WhatsApp, Slack y del chat en vivo del portal
 * (mejoras de mercado 16-11-2026). Las que piden una persona salen primero;
 * el agente la toma (traspaso), contesta por el canal del cliente y la cierra.
 * Cada conversación está atada a su ticket.
 *
 * Traducción en tiempo real (16-11-2026): los mensajes del cliente y de los agentes se
 * enseñan en el idioma del operador (`TextoTraducido`; los eventos del sistema no), y la
 * respuesta se puede previsualizar y corregir en el idioma del cliente (`VistaPreviaDeSalida`).
 *
 * 16-11-2026 (pasada de diseño): pestañas de filtro con <Tabs> estándar (antes
 * subrayadas y pequeñas), conversación elegida marcada con --accent, vacío con
 * icono lucide y hora en cada mensaje (fmtDateTime).
 *
 * 17-11-2026 (canales en tiempo real): va por el WebSocket de avisos
 * (`useAvisosEnVivo`): la bandeja se apunta (`channel_watch`) y recibe al momento
 * los mensajes, «escribiendo…», «leído» y traspasos; manda los suyos. Sondea
 * solo si el socket no está. Enseña cómo salió cada mensaje (plantilla, fallo,
 * fuera de ventana), la ventana de 24 h de WhatsApp y permite enviar un
 * documento del ticket por el canal.
 *
 * 24-11-2026 (chat en vivo completo y «un solo chat», docs/portal/CHAT_DEL_PORTAL.md §10): la
 * pantalla es la del chat interno (lista, cabecera, mensajes y editor de components/chat). En el
 * chat en vivo del portal el operador además envía imágenes y ficheros (validados), reacciona,
 * cita, edita y borra lo suyo con rastro (ve el historial) y LLAMA o videollama al cliente si
 * tiene `clientes.llamar` y la empresa lo permite (el cliente nunca inicia).
 */
import { Fragment, useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Clock, MessagesSquare, Paperclip, Pencil, Phone, Reply, Video } from 'lucide-react'
import { useAppLang, useAppT } from '../../i18n/AppLangContext'
import { useToast } from '../../context/ToastContext'
import { extractErr, fmtDateTime } from '../../utils/helpers'
import { GENERIC_ERROR_FALLBACK } from '../../constants/errors'
import { POLL_FREQUENT_MS } from '../../constants/timings'
import { Button, Modal, Pulsable, Section, Select, Spinner, StatusBadge, Tabs, TextoConEnlaces } from '../ui'
import type { StatusBadgeKind } from '../ui/StatusBadge'
import { etiquetaCodigo } from '../../i18n/etiquetaCodigo'
import { canalesApi, type Conversacion as ConversacionDeCanal, type MensajeDeCanal } from '../../services/api/serviceDeskMercado'
import TextoTraducido from '../traduccion/TextoTraducido'
import VistaPreviaDeSalida, { type SalidaAlCliente } from '../traduccion/VistaPreviaDeSalida'
import { claveDeTraduccion, useConfigDeTraduccion, useMensajesTraducidos, type ElementoATraducir } from '../../hooks/useTraduccion'
import useAvisosEnVivo, { enviarPorAvisosEnVivo, type MensajeDeAvisos } from '../../hooks/useAvisosEnVivo'
import './sdMercado.css'
import apiHttp from '../../services/api'
import { useAuth } from '../../context/AuthContext'
import { confirmar } from '../../context/ConfirmContext'
import type { PortalLlamada } from '../../services/api/tipos-alm'
import {
  AvisoDelEditor, BotonesDeLlamada, CabeceraDeConversacion, EditorDeChat, Escribiendo, FilaDeConversacion, ListaDeChats,
  MensajeDeSistema, PanelDeChat, PanelVacio, PantallaDeChat, SeparadorDeDia, ZonaDeMensajes, cambiaDeDia,
} from '../chat'
import { chatEnVivoApi } from '../portal/chatEnVivoApi'
import type { VersionDeMensaje } from '../portal/chatDelPortalApi'
import MensajeDelChatEnVivo from '../portal/MensajeDelChatEnVivo'
import LlamadaDelPortal from '../portal/LlamadaDelPortal'
import { useTextoConversacion } from '../portal/GovernedConversationsComun'
import '../portal/ChatDelPortal.css'

const ENTREGA_KIND: Record<string, StatusBadgeKind> = { template: 'info', failed: 'danger', outside_window: 'warning' }
/** Latido de la bandeja abierta (el servidor la olvida a los 90 s sin él). */
const LATIDO_DE_BANDEJA_MS = 30_000
/** Cuánto dura el «escribiendo…» sin otro aviso, y cada cuánto se avisa como mucho. */
const ESCRIBIENDO_MS = 6000
const AVISO_DE_ESCRITURA_MS = 3000

/** Lo que llega por el WebSocket de la bandeja (`type: sd_channel`). */
interface AvisoDeCanal { event: string; conversation_id: string; who?: string; name?: string; read_at?: string; by?: string; call_id?: string; status?: string }

export default function BandejaDeCanales({ onAbrirTicket }: { onAbrirTicket: (id: string) => void }) {
  const t = useAppT()
  const qc = useQueryClient()
  const [filtro, setFiltro] = useState('waiting_agent')
  const [busqueda, setBusqueda] = useState('')
  const [elegida, setElegida] = useState<string | null>(null)
  const [ultimoAviso, setUltimoAviso] = useState<AvisoDeCanal | null>(null)
  const enVivo = useAvisosEnVivo(true, useCallback((m: MensajeDeAvisos) => {
    if (m.type !== 'sd_channel' || typeof m.conversation_id !== 'string') return
    const aviso = m as unknown as AvisoDeCanal
    if (aviso.event === 'message' || aviso.event === 'status' || aviso.event === 'reaction') {
      qc.invalidateQueries({ queryKey: ['sdm-convs'] })
      qc.invalidateQueries({ queryKey: ['sdm-conv', aviso.conversation_id] })
    }
    if (aviso.event === 'call') qc.invalidateQueries({ queryKey: ['sdm-conv-calls', aviso.conversation_id] })
    setUltimoAviso(aviso)
  }, [qc]))
  // La bandeja se apunta mientras está abierta (y al reconectar).
  useEffect(() => {
    if (!enVivo) return undefined
    enviarPorAvisosEnVivo({ type: 'channel_watch' })
    qc.invalidateQueries({ queryKey: ['sdm-convs'] })
    const id = setInterval(() => enviarPorAvisosEnVivo({ type: 'channel_watch' }), LATIDO_DE_BANDEJA_MS)
    return () => clearInterval(id)
  }, [enVivo, qc])
  const { data, isLoading } = useQuery({
    queryKey: ['sdm-convs', filtro],
    queryFn: () => canalesApi.conversaciones({ status: filtro === 'open' ? undefined : filtro, page: 1, page_size: 50 }),
    refetchInterval: enVivo ? false : POLL_FREQUENT_MS,
  })
  const items = (data?.items ?? []).filter(c => !busqueda || (c.visitor_name || c.external_id || '').toLowerCase().includes(busqueda.toLowerCase()))
  // 24-11-2026 («un solo chat»): la pantalla del chat interno (components/chat): lista a la
  // izquierda y panel con su barra superior, zona de mensajes y editor. El filtro por estado
  // queda encima, con las pestañas estándar.
  return (
    <Section title={<span className="u-row-center-6"><MessagesSquare size={16} aria-hidden="true" />{t('sd_mercado.conversaciones')}</span>}
      subtitle={t('sd_mercado.conversaciones_desc')}>
      <Tabs active={filtro} onChange={id => { setFiltro(id); setElegida(null) }} ariaLabel={t('sd_mercado.conversaciones')}
        items={['waiting_agent', 'agent', 'bot', 'open', 'closed'].map(id => ({ id, label: etiquetaCodigo(t, 'sd_mercado.conv_filtro', id) }))} />
      <PantallaDeChat incrustada>
        <ListaDeChats buscar={{ valor: busqueda, onCambiar: setBusqueda, etiqueta: t('governedconversations.buscar') }}
          cargando={isLoading}
          vacio={!isLoading && items.length === 0 ? { icono: <MessagesSquare size={28} />, titulo: t('sd_mercado.sin_conversaciones') } : null}>
          {items.map(c => (
            <FilaDeConversacion key={c.id} avatar titulo={c.visitor_name || c.external_id || '—'}
              activa={elegida === c.id} onClick={() => setElegida(c.id)}
              title={`${etiquetaCodigo(t, 'sd_mercado.canal', c.channel)} · ${etiquetaCodigo(t, 'sd_mercado.conv_estado', c.status)}`} />
          ))}
        </ListaDeChats>
        {elegida
          ? <Conversacion id={elegida} onAbrirTicket={onAbrirTicket} enVivo={enVivo}
              aviso={ultimoAviso?.conversation_id === elegida ? ultimoAviso : null} />
          : <PanelVacio icono={<MessagesSquare size={28} />} titulo={t('sd_mercado.conversaciones')} descripcion={t('sd_mercado.conversaciones_desc')} />}
      </PantallaDeChat>
    </Section>
  )
}

function Entrega({ m }: { m: MensajeDeCanal }) {
  const t = useAppT()
  if (!m.delivery_status || m.delivery_status === 'sent') return null
  return <StatusBadge kind={ENTREGA_KIND[m.delivery_status] || 'neutral'} caps={false}>{etiquetaCodigo(t, 'sd_mercado.entrega', m.delivery_status)}</StatusBadge>
}

/** Estado de la ventana de 24 h de WhatsApp (también en la ficha del ticket). */
export function Ventana({ c }: { c: ConversacionDeCanal }) {
  const t = useAppT()
  const v = c.whatsapp_window
  if (!v) return null
  if (v.open) {
    return <span className="u-row-center-6 u-text3-xs"><Clock size={12} aria-hidden="true" />
      {t('sd_mercado.ventana_abierta').replace('{{hasta}}', v.expires_at ? fmtDateTime(v.expires_at) : '—')}</span>
  }
  return <StatusBadge kind={v.template ? 'info' : 'warning'} caps={false}>
    {t(v.template ? 'sd_mercado.ventana_cerrada_plantilla' : 'sd_mercado.ventana_cerrada')}</StatusBadge>
}

function Conversacion({ id, onAbrirTicket, enVivo, aviso }: { id: string; onAbrirTicket: (id: string) => void; enVivo: boolean; aviso: AvisoDeCanal | null }) {
  const t = useAppT()
  const tc = useTextoConversacion('team')
  const toast = useToast()
  const qc = useQueryClient()
  const { lang } = useAppLang()
  const { user } = useAuth()
  const api = useMemo(() => chatEnVivoApi(apiHttp, 'team'), [])
  const [texto, setTexto] = useState('')
  const [salida, setSalida] = useState<SalidaAlCliente | null>(null)
  const [desfasada, setDesfasada] = useState(false)
  const [adjunto, setAdjunto] = useState('')
  const [clienteEscribe, setClienteEscribe] = useState(false)
  const [leidoPorCliente, setLeidoPorCliente] = useState<string | null>(null)
  const [respondiendo, setRespondiendo] = useState<MensajeDeCanal | null>(null)
  const [editando, setEditando] = useState<MensajeDeCanal | null>(null)
  const [historial, setHistorial] = useState<VersionDeMensaje[] | null>(null)
  const [llamada, setLlamada] = useState<PortalLlamada | null>(null)
  const avisoDeEscritura = useRef(0)
  const { data } = useQuery({ queryKey: ['sdm-conv', id], queryFn: () => canalesApi.conversacion(id),
    refetchInterval: enVivo ? false : POLL_FREQUENT_MS })
  const esLivechat = data?.conversation.channel === 'livechat'
  const { data: ajustes } = useQuery({ queryKey: ['sdm-chat-settings'], queryFn: () => api.ajustes(), staleTime: POLL_FREQUENT_MS })
  const { data: llamadas = [] } = useQuery({ queryKey: ['sdm-conv-calls', id], queryFn: () => api.llamadas(id), enabled: esLivechat,
    refetchInterval: enVivo ? false : POLL_FREQUENT_MS })
  const llamadaEnCurso = llamadas.find(c => c.status === 'active' || c.status === 'ringing') || null
  useEffect(() => { setTexto(''); setAdjunto(''); setClienteEscribe(false); setLeidoPorCliente(null); setRespondiendo(null); setEditando(null) }, [id])
  // Avisos en vivo de esta conversación: el cliente escribe, ha leído o cambia una llamada.
  useEffect(() => {
    if (!aviso) return undefined
    if (aviso.event === 'typing' && aviso.who === 'customer') {
      setClienteEscribe(true)
      const fin = setTimeout(() => setClienteEscribe(false), ESCRIBIENDO_MS)
      return () => clearTimeout(fin)
    }
    if (aviso.event === 'message') setClienteEscribe(false)
    if (aviso.event === 'read' && aviso.by === 'customer' && aviso.read_at) setLeidoPorCliente(aviso.read_at)
    if (aviso.event === 'call' && llamada && aviso.call_id === llamada.id) {
      if (aviso.status === 'declined') toast.error(tc('governedconversations.llamada_rechazada'))
      if (aviso.status === 'missed') toast.error(tc('governedconversations.llamada_perdida'))
      if (aviso.status === 'ended' || aviso.status === 'declined' || aviso.status === 'missed') setLlamada(null)
      else if (aviso.status) setLlamada({ ...llamada, status: aviso.status as PortalLlamada['status'] })
    }
    return undefined
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [aviso])
  // Leído por el agente: lo que el cliente escribió y el agente tiene delante.
  const ultimoDelCliente = [...(data?.messages ?? [])].reverse().find(m => m.direction === 'in')?.id
  useEffect(() => {
    if (ultimoDelCliente && document.visibilityState === 'visible') enviarPorAvisosEnVivo({ type: 'channel_read', conversation_id: id })
  }, [id, ultimoDelCliente])
  // Mensajes del cliente y de agentes que no están en el idioma del operador (o no se sabe).
  const { data: configTrad } = useConfigDeTraduccion()
  const aTraducir = useMemo<ElementoATraducir[]>(() => (data?.messages ?? [])
    .filter(m => (m.author_type === 'customer' || m.author_type === 'agent') && !m.is_deleted
      && (!m.language || m.language.toLowerCase() !== lang.toLowerCase()))
    .map((m): ElementoATraducir => ({ type: 'channel_message', id: m.id })), [data?.messages, lang])
  const { porClave, isFetching: traduciendo } = useMensajesTraducidos(aTraducir, !!configTrad?.enabled)
  const refrescar = () => { qc.invalidateQueries({ queryKey: ['sdm-conv', id] }); qc.invalidateQueries({ queryKey: ['sdm-convs'] }) }
  const err = (e: unknown) => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK))
  const tomar = useMutation({ mutationFn: () => canalesApi.tomar(id), onSuccess: refrescar, onError: err })
  const responder = useMutation({
    mutationFn: () => editando
      ? api.editar(id, editando.id, texto.trim())
      : canalesApi.responder(id, texto.trim(), salida, respondiendo?.id),
    onSuccess: () => { setTexto(''); setRespondiendo(null); setEditando(null); refrescar() }, onError: err })
  const subir = useMutation({ mutationFn: (f: File) => api.subir(id, f, { caption: texto.trim() || undefined, replyTo: respondiendo?.id }),
    onSuccess: () => { setTexto(''); setRespondiendo(null); refrescar() }, onError: err })
  const enviarAdjunto = useMutation({ mutationFn: () => canalesApi.enviarAdjunto(id, adjunto), onSuccess: () => { setAdjunto(''); refrescar() }, onError: err })
  const cerrar = useMutation({ mutationFn: () => canalesApi.cerrar(id), onSuccess: refrescar, onError: err })
  const reaccionar = (m: MensajeDeCanal, emoji: string) => { api.reaccionar(id, m.id, emoji).then(refrescar).catch(err) }
  const borrar = async (m: MensajeDeCanal) => {
    const ok = await confirmar({ title: tc('governedconversations.borrar'), message: tc('governedconversations.confirmar_borrar'),
      confirmLabel: tc('governedconversations.borrar'), cancelLabel: t('common.cancel'), danger: true })
    if (ok) api.borrar(id, m.id).then(refrescar).catch(err)
  }
  const verHistorial = (m: MensajeDeCanal) => { api.versiones(id, m.id).then(setHistorial).catch(err) }
  const llamar = useMutation({ mutationFn: (kind: 'audio' | 'video') => api.llamar(id, kind),
    onSuccess: (c) => { setLlamada(c); qc.invalidateQueries({ queryKey: ['sdm-conv-calls', id] }) }, onError: err })
  const unirse = useMutation({ mutationFn: (callId: string) => api.unirse(id, callId), onSuccess: setLlamada, onError: err })
  const colgar = () => {
    const actual = llamada
    setLlamada(null)
    if (actual) api.colgar(id, actual.id).catch(() => { /* accesorio: si ya terminó no hay nada que deshacer */ })
      .finally(() => qc.invalidateQueries({ queryKey: ['sdm-conv-calls', id] }))
  }
  const escribiendo = (valor: string) => {
    setTexto(valor)
    const ahora = Date.now()
    if (valor.trim() && ahora - avisoDeEscritura.current > AVISO_DE_ESCRITURA_MS) {
      avisoDeEscritura.current = ahora
      enviarPorAvisosEnVivo({ type: 'channel_typing', conversation_id: id })
    }
  }
  if (!data) return <PanelDeChat etiqueta={t('sd_mercado.conversaciones')}><Spinner /></PanelDeChat>
  const c = data.conversation
  const activa = c.status !== 'closed'
  const leidoHasta = leidoPorCliente || c.client_read_at || null
  const adjuntables = (c.channel === 'whatsapp' || c.channel === 'slack') && (data.attachments?.length ?? 0) > 0
  const puedeLlamar = esLivechat && activa && !!ajustes?.can_call && !llamada
  const nombre = (m: MensajeDeCanal) => m.author_type === 'customer'
    ? (m.author_name || c.visitor_name || tc('governedconversations.remitente_cliente'))
    : m.author_type === 'bot' ? etiquetaCodigo(t, 'sd_mercado.autor', 'bot')
      : (m.author_name || etiquetaCodigo(t, 'sd_mercado.autor', m.author_type))
  return (
    <PanelDeChat etiqueta={c.visitor_name || c.external_id || t('sd_mercado.conversaciones')}>
      <CabeceraDeConversacion
        titulo={c.visitor_name || c.external_id || '—'}
        icono={<MessagesSquare size={18} aria-hidden="true" />}
        subtitulo={<span className="u-row-center-6">
          {etiquetaCodigo(t, 'sd_mercado.canal', c.channel)} · {etiquetaCodigo(t, 'sd_mercado.conv_estado', c.status)}
          {c.ticket_id && <> · <Pulsable className="u-btn-outline-sm" onClick={() => onAbrirTicket(c.ticket_id as string)}>{c.ticket_number}</Pulsable></>}
          <Ventana c={c} />
        </span>}
        acciones={<>
          {puedeLlamar && (llamadaEnCurso ? (
            <Button size="xs" icon={llamadaEnCurso.kind === 'video' ? <Video size={13} /> : <Phone size={13} />} loading={unirse.isPending} onClick={() => unirse.mutate(llamadaEnCurso.id)}>
              {tc('governedconversations.unirse')}
            </Button>
          ) : (
            <BotonesDeLlamada onLlamar={(kind) => llamar.mutate(kind)} desactivado={llamar.isPending} video={!!ajustes?.video_enabled}
              etiquetaVoz={tc('governedconversations.llamar')} etiquetaVideo={tc('governedconversations.videollamada')} />
          ))}
          {c.status !== 'agent' && activa && <Button size="xs" onClick={() => tomar.mutate()} loading={tomar.isPending}>{t('sd_mercado.tomar')}</Button>}
          {activa && <Button size="xs" variant="ghost" onClick={() => cerrar.mutate()} disabled={cerrar.isPending}>{t('sd_mercado.cerrar')}</Button>}
        </>}
      />
      <ZonaDeMensajes etiqueta={t('sd_mercado.conversaciones')}>
        {data.messages.map((m, i) => {
          // 24-11-2026 (burbujas): separador de día; sistema en pastilla centrada; lo del
          // operador que mira (su usuario) a la derecha; cliente, bot y compañeros a la izquierda.
          const previo = data.messages[i - 1]
          const nuevoDia = cambiaDeDia(previo?.created_at, m.created_at)
          if (m.author_type === 'system') {
            return (
              <Fragment key={m.id}>
                {nuevoDia && <SeparadorDeDia fecha={m.created_at} />}
                <MensajeDeSistema>{etiquetaCodigo(t, 'sd_mercado.evento_conv', m.body)}</MensajeDeSistema>
              </Fragment>
            )
          }
          const tr = porClave.get(claveDeTraduccion('channel_message', m.id))
          const pedido = aTraducir.some(a => a.id === m.id)
          const mio = m.author_type === 'agent' && !!user?.id && m.author_user_id === user.id
          const compacto = !!previo && !nuevoDia && previo.author_type === m.author_type && previo.author_user_id === m.author_user_id
            && !!previo.created_at && !!m.created_at && Date.parse(m.created_at) - Date.parse(previo.created_at) < 5 * 60_000
          return (
            <Fragment key={m.id}>
            {nuevoDia && <SeparadorDeDia fecha={m.created_at} />}
            <MensajeDelChatEnVivo m={m} lado="team" convId={id} api={api}
              autor={nombre(m)}
              autorDeCita={(tipo) => tipo === 'customer' ? (c.visitor_name || tc('governedconversations.remitente_cliente')) : etiquetaCodigo(t, 'sd_mercado.autor', tipo)}
              esMio={mio} quien={{ userId: user?.id }} activa={activa && esLivechat} compacto={compacto}
              cuerpo={<TextoTraducido original={m.body} traduccion={tr} cargando={!tr && traduciendo && pedido} />}
              extras={<>
                {m.attachment_document_id && (
                  <div className="u-row-center-6 u-text3-xs"><Paperclip size={12} aria-hidden="true" />{m.attachment_name || t('sd_mercado.adjunto')}</div>
                )}
                <Entrega m={m} />
              </>}
              leido={m.author_type === 'agent' ? !!(leidoHasta && m.created_at && Date.parse(leidoHasta) >= Date.parse(m.created_at)) : null}
              onResponder={(x) => { setEditando(null); setRespondiendo(x) }}
              onEditar={(x) => { setRespondiendo(null); setEditando(x); setTexto(x.body || '') }}
              onBorrar={borrar}
              onReaccionar={reaccionar}
              onHistorial={verHistorial}
              onError={err}
            />
            </Fragment>
          )
        })}
      </ZonaDeMensajes>
      <Escribiendo texto={clienteEscribe ? t('sd_mercado.cliente_escribiendo') : null} />
      {activa && (
        <EditorDeChat
          valor={texto}
          onCambiar={escribiendo}
          onEnviar={() => { if (texto.trim() && !desfasada && !responder.isPending) responder.mutate() }}
          etiquetaCampo={t('sd_mercado.respuesta')}
          placeholder={t('sd_mercado.respuesta')}
          etiquetaEnviar={editando ? tc('governedconversations.guardar_edicion') : t('sd_mercado.enviar')}
          etiquetaEmoji={tc('governedconversations.insertar_emoji')}
          adjuntar={esLivechat && ajustes?.attachments_enabled && !editando ? {
            etiqueta: `${tc('governedconversations.adjuntar')} · ${tc('governedconversations.adjunto_limite', { mb: ajustes.max_file_mb })}`,
            aceptar: (ajustes.allowed_extensions || []).join(','), onFichero: (f) => subir.mutate(f), desactivado: subir.isPending,
          } : null}
          encima={<>
            {respondiendo && !editando && (
              <AvisoDelEditor icono={<Reply size={12} aria-hidden="true" />}
                texto={`${tc('governedconversations.respondiendo_a', { name: nombre(respondiendo) })}: ${String(respondiendo.body || '').slice(0, 120)}`}
                etiquetaCancelar={tc('governedconversations.cancelar_respuesta')} onCancelar={() => setRespondiendo(null)} />
            )}
            {editando && (
              <AvisoDelEditor icono={<Pencil size={12} aria-hidden="true" />} texto={tc('governedconversations.editando')}
                etiquetaCancelar={tc('governedconversations.cancelar_edicion')} onCancelar={() => { setEditando(null); setTexto('') }} />
            )}
            {adjuntables && (
              <div className="u-row-8">
                <Select suelto tamano="sm" className="u-flex1" aria-label={t('sd_mercado.adjunto_del_ticket')} value={adjunto}
                  placeholder={t('sd_mercado.elige_adjunto')} onChange={e => setAdjunto(e.target.value)}
                  options={(data.attachments ?? []).map(a => ({ value: a.id, label: a.file_name || a.title }))} />
                <Button size="sm" variant="secondary" icon={<Paperclip size={14} />} onClick={() => enviarAdjunto.mutate()}
                  loading={enviarAdjunto.isPending} disabled={!adjunto}>{t('sd_mercado.enviar_adjunto')}</Button>
              </div>
            )}
          </>}
        />
      )}
      {activa && !editando && (
        <VistaPreviaDeSalida key={id} contextType="conversation" contextId={id} texto={texto}
          onChange={(s, e) => { setSalida(s); setDesfasada(e.desfasada) }} />
      )}
      {historial && (
        <Modal open onClose={() => setHistorial(null)} title={tc('governedconversations.historial_titulo')} avisarSinGuardar={false}>
          {historial.length === 0 ? (
            <div className="u-text2-sm">{tc('governedconversations.historial_vacio')}</div>
          ) : (
            <ol className="chat-portal-historial">
              {historial.map(v => (
                <li key={v.id}>
                  <div className="u-text3-xs">
                    {tc(v.change_type === 'delete' ? 'governedconversations.historial_borrado' : 'governedconversations.historial_edicion')} · {v.edited_at || ''}
                  </div>
                  <TextoConEnlaces texto={v.body || ''} className="chat-msg__body" />
                </li>
              ))}
            </ol>
          )}
        </Modal>
      )}
      {llamada && (
        <LlamadaDelPortal llamada={llamada} titulo={c.visitor_name || tc('governedconversations.llamada')}
          esperando={llamada.status === 'ringing'} onColgar={colgar} t={tc} />
      )}
    </PanelDeChat>
  )
}
