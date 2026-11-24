import { Fragment, useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import api, { portalClientsApi, portalConversationsApi, apiWsUrl } from '../../services/api'
import { useListaDeUsuarios } from '../../hooks/useListas'
import { useToast } from '../../context/ToastContext'
import { confirmar } from '../../context/ConfirmContext'
import { useAuth } from '../../context/AuthContext'
import { extractErr } from '../../utils/helpers'
import { CLIENT_API, S as PORTAL_STYLES, useClientAuth, useErrorDelPortal } from '../../pages/portal-client/portalClientContext'
import { Button, Modal, Select } from '../ui'
import { MessagesSquare, Phone, PhoneIncoming, PhoneOff, Plus, Video } from 'lucide-react'
import { POLL_ACTIVE_CHAT_MS, POLL_FAST_MS, POLL_FREQUENT_MS, WS_HEARTBEAT_MS } from '../../constants/timings'
import type { PortalAjustesDelChat, PortalLlamada } from '../../services/api/tipos-alm'
import './GovernedConversations.css'
import './ChatDelPortal.css'
import { type ApiClient, type Conversation, EMPTY_LIST, type Message, type Mode, type ProjectOption, type Toast, type UserOption, useTextoConversacion } from './GovernedConversationsComun'
import { ConversationComposer, type CreateConversationForm, CreateConversationModal, MessageBubble, esCompacto } from './GovernedConversationsPiezas'
import { chatDelPortalApi, type VersionDeMensaje } from './chatDelPortalApi'
import LlamadaDelPortal from './LlamadaDelPortal'
import { BotonesDeLlamada, CabeceraDeConversacion, Escribiendo, FilaDeConversacion, IndicadorDeCabecera, ListaDeChats, PanelDeChat, PanelVacio, PantallaDeChat, SeparadorDeDia, ZonaDeMensajes, cambiaDeDia } from '../chat'
export { useTextoConversacion } from './GovernedConversationsComun'
export { ConversationPoliciesPanel } from './ConversationPoliciesPanel'

/** Cada cuánto se avisa de «escribiendo…» mientras se teclea, y cuánto dura el aviso. */
const ESCRIBIENDO_CADA_MS = 3_000
const ESCRIBIENDO_DURA_MS = 6_000

export interface GovernedConversationInboxProps {
  mode: Mode
  apiClient: ApiClient
  queryPrefix: string
  projectOptions?: ProjectOption[]
  initialProjectId?: string
  clientOrgId?: string
  enableRealtime?: boolean
  wsTicketPath?: string
  /** Ruta WebSocket relativa a la API (`/ws/...`), sin el prefijo `/api/v1`. */
  wsEndpoint?: string
  title?: ReactNode
  emptyTitle?: ReactNode
  emptyDescription?: ReactNode
  /** 24-11-2026: quién mira (sus mensajes se pueden editar/borrar; sus reacciones se marcan). */
  viewerUserId?: string | null
  viewerClientId?: string | null
}

/** Evento en vivo del chat del portal (`app/services/portal_conversation_service/en_vivo.py`). */
interface EventoDelChat {
  type?: string
  event?: 'message' | 'reaction' | 'read' | 'typing' | 'call'
  conversation_id?: string
  who?: 'team' | 'client'
  name?: string
  call_id?: string
  status?: PortalLlamada['status']
  kind?: PortalLlamada['kind']
}

export function GovernedConversationInbox({
  mode,
  apiClient,
  queryPrefix,
  projectOptions = [],
  initialProjectId = '',
  clientOrgId,
  enableRealtime = false,
  wsTicketPath,
  wsEndpoint,
  title,
  emptyTitle,
  emptyDescription,
  viewerUserId,
  viewerClientId,
}: GovernedConversationInboxProps) {
  const t = useTextoConversacion(mode)
  // 16-11-2026: en el portal, los errores del servidor con código salen en el
  // idioma del cliente; en la vista interna, el `detail` de siempre.
  const errorDelPortal = useErrorDelPortal()
  const errorDe = useCallback((e: unknown, fallback: string) => mode === 'client' ? errorDelPortal(e, fallback) : extractErr(e, fallback), [errorDelPortal, mode])
  const toast = useToast() as Toast
  const qc = useQueryClient()
  const chat = useMemo(() => chatDelPortalApi(apiClient, mode), [apiClient, mode])
  const [selectedProject, setSelectedProject] = useState<string>(initialProjectId || projectOptions[0]?.id || '')
  const [selectedConversationId, setSelectedConversationId] = useState<string | null>(null)
  const [draft, setDraft] = useState<string>('')
  const [isInternalNote, setIsInternalNote] = useState<boolean>(false)
  const [showCreate, setShowCreate] = useState<boolean>(false)
  const [filtro, setFiltro] = useState('')
  // 24-11-2026 (chat del portal completo): responder, editar, escribiendo, historial y llamadas.
  const [replyTo, setReplyTo] = useState<Message | null>(null)
  const [editing, setEditing] = useState<Message | null>(null)
  const [escribiendo, setEscribiendo] = useState<{ conversationId: string; name: string } | null>(null)
  const [historial, setHistorial] = useState<{ message: Message; versiones: VersionDeMensaje[] } | null>(null)
  const [llamada, setLlamada] = useState<PortalLlamada | null>(null)
  const socketRef = useRef<WebSocket | null>(null)
  const llamadaRef = useRef<PortalLlamada | null>(null)
  const ultimoAvisoDeEscritura = useRef(0)
  const temporizadorDeEscritura = useRef<number | null>(null)

  useEffect(() => {
    if (!selectedProject && initialProjectId) setSelectedProject(initialProjectId)
  }, [initialProjectId, selectedProject])

  const filters = useMemo(() => ({
    project_id: selectedProject || undefined,
    client_org_id: mode === 'team' ? clientOrgId || undefined : undefined,
  }), [clientOrgId, mode, selectedProject])

  const listPath = mode === 'team' ? '/portal/conversations/team' : '/portal/conversations'
  const listQueryKey = [queryPrefix, 'list', selectedProject || 'all', clientOrgId || 'all']

  const { data: conversationsData, isLoading: loadingConversations } = useQuery<Conversation[]>({
    queryKey: listQueryKey,
    queryFn: () => apiClient.get<Conversation[]>(listPath, { params: filters }).then((response) => response.data),
    // Con tiempo real el sondeo queda de respaldo (por si el socket se cae).
    refetchInterval: POLL_FREQUENT_MS,
  })
  const conversations: Conversation[] = conversationsData || EMPTY_LIST

  useEffect(() => {
    if (!conversations.length) {
      setSelectedConversationId(null)
      return
    }
    const exists = conversations.some((conversation) => conversation.id === selectedConversationId)
    if (!exists) setSelectedConversationId(conversations[0].id)
  }, [conversations, selectedConversationId])

  // Al cambiar de conversación se olvidan la respuesta y la edición en curso.
  useEffect(() => { setReplyTo(null); setEditing(null) }, [selectedConversationId])

  const selectedConversation = conversations.find((conversation) => conversation.id === selectedConversationId) || null
  const esNativa = !!selectedConversation && selectedConversation.source !== 'legacy_client_message'
  const messagesQueryKey = [queryPrefix, 'messages', selectedConversationId || 'none']
  const messagesPath = selectedConversationId
    ? mode === 'team'
      ? `/portal/conversations/team/${selectedConversationId}/messages`
      : `/portal/conversations/${selectedConversationId}/messages`
    : null

  const { data: messagesData, isLoading: loadingMessages } = useQuery<Message[]>({
    queryKey: messagesQueryKey,
    queryFn: () => apiClient.get<Message[]>(messagesPath as string).then((response) => response.data),
    enabled: !!messagesPath,
    refetchInterval: POLL_ACTIVE_CHAT_MS,
  })
  const messages: Message[] = messagesData || EMPTY_LIST

  const { data: ajustes } = useQuery<PortalAjustesDelChat>({
    queryKey: [queryPrefix, 'chat-settings'],
    queryFn: () => chat.ajustes(),
    staleTime: POLL_FREQUENT_MS,
  })

  const { data: llamadasData } = useQuery<PortalLlamada[]>({
    queryKey: [queryPrefix, 'calls', selectedConversationId || 'none'],
    queryFn: () => chat.llamadas(selectedConversationId as string),
    enabled: !!selectedConversationId && esNativa,
    refetchInterval: POLL_FREQUENT_MS,
  })
  const llamadaEnCurso = (llamadasData || EMPTY_LIST).find(c => c.status === 'active' || c.status === 'ringing') || null

  // Cliente: llamadas del equipo que suenan (en cualquiera de sus conversaciones).
  const { data: sonandoData } = useQuery<PortalLlamada[]>({
    queryKey: [queryPrefix, 'calls-ringing'],
    queryFn: () => chat.sonando(),
    enabled: mode === 'client',
    refetchInterval: POLL_FAST_MS,
  })
  const entrante = mode === 'client' && !llamada ? (sonandoData || EMPTY_LIST)[0] || null : null

  // 23-11-2026: lista compartida de personas (antes clave propia y `.catch` que tragaba el error).
  const { data: teamUsersData } = useListaDeUsuarios(undefined, { enabled: mode === 'team' && showCreate })
  const teamUsers: UserOption[] = teamUsersData || EMPTY_LIST

  const { data: portalClientsData } = useQuery<UserOption[]>({
    queryKey: ['portal-clients', 'portal-conversations', selectedProject || 'all', clientOrgId || 'all'],
    queryFn: () => portalClientsApi.list({ project_id: selectedProject || undefined, client_org_id: clientOrgId || undefined }).then(r => r.data),
    enabled: mode === 'team' && showCreate && Boolean(selectedProject || clientOrgId),
  })
  const portalClients: UserOption[] = portalClientsData || EMPTY_LIST

  const refrescar = useCallback(() => qc.invalidateQueries({ queryKey: [queryPrefix] }), [qc, queryPrefix])

  const createConversation = useMutation({
    mutationFn: async (payload: CreateConversationForm) => {
      const createResponse = await apiClient.post<Conversation>(listPath, {
        title: payload.title,
        topic_type: payload.topic_type,
        project_id: payload.project_id || undefined,
        client_org_id: clientOrgId || undefined,
        internal_user_ids: payload.internal_user_ids || [],
        client_user_ids: payload.client_user_ids || [],
      })
      const created = createResponse.data
      const messagePath = mode === 'team'
        ? `/portal/conversations/team/${created.id}/messages`
        : `/portal/conversations/${created.id}/messages`
      await apiClient.post(messagePath, {
        body: payload.body,
        message_type: 'text',
        is_internal_note: false,
      })
      return created
    },
    onSuccess: (created) => {
      refrescar()
      setSelectedConversationId(created.id)
      setShowCreate(false)
      toast.success(t('governedconversations.conversacion_creada'))
    },
    onError: (error) => toast.error(errorDe(error, t('governedconversations.err_crear'))),
  })

  const sendMessage = useMutation({
    mutationFn: (): Promise<unknown> => {
      if (editing) return chat.editar(selectedConversationId as string, editing.id, draft)
      return apiClient.post(
        mode === 'team'
          ? `/portal/conversations/team/${selectedConversationId}/messages`
          : `/portal/conversations/${selectedConversationId}/messages`,
        {
          body: draft,
          message_type: 'text',
          is_internal_note: mode === 'team' ? isInternalNote : false,
          parent_message_id: replyTo?.id || undefined,
        },
      )
    },
    onSuccess: () => {
      refrescar()
      setDraft('')
      setIsInternalNote(false)
      setReplyTo(null)
      setEditing(null)
    },
    onError: (error) => toast.error(errorDe(error, t(editing ? 'governedconversations.err_editar' : 'governedconversations.err_enviar'))),
  })

  const attach = useMutation({
    mutationFn: (file: File) => chat.subir(selectedConversationId as string, file, {
      caption: draft.trim() || undefined, parentId: replyTo?.id, nota: mode === 'team' && isInternalNote,
    }),
    onSuccess: () => {
      refrescar()
      setDraft('')
      setReplyTo(null)
      setIsInternalNote(false)
    },
    onError: (error) => toast.error(errorDe(error, t('governedconversations.err_adjuntar'))),
  })

  const react = useMutation({
    mutationFn: ({ messageId, emoji }: { messageId: string; emoji: string }) => chat.reaccionar(selectedConversationId as string, messageId, emoji),
    onSuccess: () => qc.invalidateQueries({ queryKey: messagesQueryKey }),
    onError: (error) => toast.error(errorDe(error, t('governedconversations.err_reaccion'))),
  })

  const remove = useMutation({
    mutationFn: (messageId: string) => chat.borrar(selectedConversationId as string, messageId),
    onSuccess: () => refrescar(),
    onError: (error) => toast.error(errorDe(error, t('governedconversations.err_borrar'))),
  })

  const reviewMessage = useMutation({
    mutationFn: ({ messageId, decision }: { messageId: string; decision: 'approved' | 'rejected' }) => portalConversationsApi.reviewMessage(selectedConversationId, messageId, { decision }),
    onSuccess: () => {
      refrescar()
      toast.success(t('governedconversations.revision_aplicada'))
    },
    onError: (error) => toast.error(errorDe(error, t('governedconversations.err_revisar'))),
  })

  // ── Llamadas ───────────────────────────────────────────────────────────────
  const llamar = useMutation({
    mutationFn: (kind: 'audio' | 'video') => chat.llamar(selectedConversationId as string, kind),
    onSuccess: (c) => { setLlamada(c); qc.invalidateQueries({ queryKey: [queryPrefix, 'calls'] }) },
    onError: (error) => toast.error(errorDe(error, t('governedconversations.err_llamada'))),
  })
  const unirse = useMutation({
    mutationFn: (callId: string) => chat.unirse(selectedConversationId as string, callId),
    onSuccess: (c) => setLlamada(c),
    onError: (error) => toast.error(errorDe(error, t('governedconversations.err_llamada'))),
  })
  const aceptar = useMutation({
    mutationFn: (c: PortalLlamada) => chat.aceptar(c.conversation_id, c.id),
    onSuccess: (c) => { setLlamada(c); setSelectedConversationId(c.conversation_id); qc.invalidateQueries({ queryKey: [queryPrefix, 'calls-ringing'] }) },
    onError: (error) => toast.error(errorDe(error, t('governedconversations.err_llamada'))),
  })
  const rechazar = useMutation({
    mutationFn: (c: PortalLlamada) => chat.rechazar(c.conversation_id, c.id),
    onSettled: () => qc.invalidateQueries({ queryKey: [queryPrefix, 'calls-ringing'] }),
    onError: (error) => toast.error(errorDe(error, t('governedconversations.err_llamada'))),
  })
  const colgar = useCallback(() => {
    const actual = llamada
    setLlamada(null)
    if (actual && (actual.status === 'ringing' || actual.status === 'active')) {
      chat.colgar(actual.conversation_id, actual.id)
        .catch(() => { /* accesorio: si ya había terminado, el servidor lo dice y no hay nada que deshacer */ })
        .finally(() => qc.invalidateQueries({ queryKey: [queryPrefix, 'calls'] }))
    }
  }, [chat, llamada, qc, queryPrefix])

  // ── Tiempo real ────────────────────────────────────────────────────────────
  llamadaRef.current = llamada
  const alEvento = useCallback((ev: EventoDelChat) => {
    if (ev.type !== 'portal_conv') {
      refrescar()
      return
    }
    if (ev.event === 'typing' && ev.conversation_id) {
      setEscribiendo({ conversationId: ev.conversation_id, name: ev.name || '' })
      if (temporizadorDeEscritura.current) window.clearTimeout(temporizadorDeEscritura.current)
      temporizadorDeEscritura.current = window.setTimeout(() => setEscribiendo(null), ESCRIBIENDO_DURA_MS)
      return
    }
    if (ev.event === 'message') setEscribiendo(null)
    const actual = llamadaRef.current
    if (ev.event === 'call' && ev.status && actual && actual.id === ev.call_id) {
      if (ev.status === 'declined') toast.error(t('governedconversations.llamada_rechazada'))
      if (ev.status === 'missed') toast.error(t('governedconversations.llamada_perdida'))
      setLlamada(ev.status === 'ended' || ev.status === 'declined' || ev.status === 'missed' ? null : { ...actual, status: ev.status })
    }
    refrescar()
  }, [refrescar, t, toast])

  // El socket vive mientras la bandeja está abierta: lee siempre el último
  // manejador (traductor y avisos cambian en cada pintado y no deben reconectar).
  const alEventoRef = useRef(alEvento)
  alEventoRef.current = alEvento

  const avisarEscribiendo = useCallback(() => {
    const ahora = Date.now()
    if (!selectedConversationId || !esNativa || ahora - ultimoAvisoDeEscritura.current < ESCRIBIENDO_CADA_MS) return
    ultimoAvisoDeEscritura.current = ahora
    const s = socketRef.current
    if (s && s.readyState === window.WebSocket.OPEN) {
      s.send(JSON.stringify({ type: 'portal_conv_typing', conversation_id: selectedConversationId }))
    }
  }, [esNativa, selectedConversationId])

  useEffect(() => {
    if (!enableRealtime || !wsTicketPath || !wsEndpoint) return undefined
    let socket: WebSocket | null = null
    let pingInterval: number | null = null
    let reconnectTimer: number | null = null
    let closed = false
    let attempt = 0
    const MAX_ATTEMPTS = 5

    async function connect() {
      if (closed || attempt >= MAX_ATTEMPTS) return
      attempt++
      try {
        const response = await apiClient.get(wsTicketPath!)
        const ticket = response?.data?.ticket
        if (!ticket || closed) return
        socket = new window.WebSocket(apiWsUrl(`${wsEndpoint}?ticket=${encodeURIComponent(ticket)}`))
        socketRef.current = socket
        socket.onopen = () => { attempt = 0 }
        socket.onmessage = (mensaje: MessageEvent) => {
          let ev: EventoDelChat = {}
          try { ev = JSON.parse(String(mensaje.data)) } catch { /* accesorio: un aviso ilegible solo refresca */ }
          if (ev.type === 'pong' || ev.type === 'connected') return
          alEventoRef.current(ev)
        }
        socket.onerror = () => {
          if (socket) socket.close()
        }
        socket.onclose = (ev) => {
          if (socketRef.current === socket) socketRef.current = null
          if (closed) return
          if (ev.code === 1000 || ev.code === 1001) return
          const delay = Math.min(1000 * 2 ** (attempt - 1), 30000)
          reconnectTimer = window.setTimeout(connect, delay)
        }
        pingInterval = window.setInterval(() => {
          if (socket && socket.readyState === window.WebSocket.OPEN) {
            socket.send(JSON.stringify({ type: 'ping' }))
          }
        }, WS_HEARTBEAT_MS)
      } catch {
        // Polling remains as fallback.
        if (!closed && attempt < MAX_ATTEMPTS) {
          const delay = Math.min(1000 * 2 ** (attempt - 1), 30000)
          reconnectTimer = window.setTimeout(connect, delay)
        }
      }
    }

    connect()
    return () => {
      closed = true
      if (reconnectTimer) window.clearTimeout(reconnectTimer)
      if (pingInterval) window.clearInterval(pingInterval)
      if (socket && socket.readyState === window.WebSocket.OPEN) socket.close()
      socketRef.current = null
    }
  }, [apiClient, enableRealtime, wsEndpoint, wsTicketPath])

  useEffect(() => () => { if (temporizadorDeEscritura.current) window.clearTimeout(temporizadorDeEscritura.current) }, [])

  // ── Acciones sobre un mensaje ──────────────────────────────────────────────
  const empezarEdicion = (message: Message) => {
    setReplyTo(null)
    setEditing(message)
    setDraft(message.raw_body || message.body || '')
  }
  const cancelarEdicion = () => { setEditing(null); setDraft('') }
  const borrarMensaje = async (message: Message) => {
    const ok = await confirmar({
      title: t('governedconversations.borrar'),
      message: t('governedconversations.confirmar_borrar'),
      confirmLabel: t('governedconversations.borrar'),
      cancelLabel: t('common.cancel'),
      danger: true,
    })
    if (ok) remove.mutate(message.id)
  }
  const verHistorial = async (message: Message) => {
    try {
      setHistorial({ message, versiones: await chat.versiones(selectedConversationId as string, message.id) })
    } catch (e) {
      toast.error(errorDe(e, t('governedconversations.err_historial')))
    }
  }
  const esMio = (m: Message) => mode === 'team'
    ? !!viewerUserId && m.sender_user_id === viewerUserId
    : !!viewerClientId && m.sender_client_id === viewerClientId

  const headerKpi = conversations.reduce((total, conversation) => total + ((mode === 'team' ? conversation.unread_for_team : conversation.unread_for_client) || 0), 0)
  const escribiendoAqui = escribiendo && escribiendo.conversationId === selectedConversationId ? escribiendo : null
  const puedeLlamar = mode === 'team' && esNativa && !!ajustes?.can_call && !llamada

  // 24-11-2026 («un solo chat»): la pantalla es la del chat interno (components/chat):
  // lista de conversaciones a la izquierda, panel con su barra superior, zona de
  // mensajes y editor. «Con supervisión» solo lo ve el equipo, como indicador
  // discreto en la cabecera con su explicación.
  const botonNueva = (
    <Button icon={<Plus size={14} />} onClick={() => setShowCreate(true)}>{t('governedconversations.nueva_conversacion')}</Button>
  )
  const politica = selectedConversation?.policy
  const explicacionDeSupervision = [
    politica?.requires_team_message_approval ? t('governedconversations.supervision_equipo') : null,
    politica?.requires_client_message_approval ? t('governedconversations.supervision_cliente') : null,
    politica?.redact_sensitive_content ? t('governedconversations.supervision_ocultar') : null,
  ].filter(Boolean).join(' ') || t('governedconversations.supervision_general')

  return (
    <div className="u-stack-12">
      <div className="ds-toolbar">
        <div className="u-min0">
          <div className="u-sm-700">{title}</div>
          <div className="u-text3-xs">{t('governedconversations.resumen', { n: conversations.length, sin_leer: headerKpi })}</div>
        </div>
        <span className="ds-toolbar__spacer" />
        {projectOptions.length > 1 && (
          <Select suelto aria-label={t('gas.proyecto')} placeholder={t('governedconversations.todos_los_proyectos')} value={selectedProject} onChange={(event) => setSelectedProject(event.target.value)}>
            {projectOptions.map((project) => <option key={project.id} value={project.id}>{project.code ? `${project.code} — ` : ''}{project.name}</option>)}
          </Select>
        )}
        {botonNueva}
      </div>

      {entrante && (
        <div className="chat-portal-entrante" role="alert">
          <PhoneIncoming size={18} aria-hidden="true" />
          <div className="u-flex1-min0">
            <div className="u-sm-700">{t(entrante.kind === 'video' ? 'governedconversations.videollamada_entrante' : 'governedconversations.llamada_entrante')}</div>
            <div className="u-text2-sm">{entrante.conversation_title || ''} · {t('governedconversations.llamada_no_se_graba')}</div>
          </div>
          <Button size="sm" icon={entrante.kind === 'video' ? <Video size={13} /> : <Phone size={13} />} loading={aceptar.isPending} onClick={() => aceptar.mutate(entrante)}>
            {t('governedconversations.aceptar')}
          </Button>
          <Button size="sm" variant="danger" icon={<PhoneOff size={13} />} loading={rechazar.isPending} onClick={() => rechazar.mutate(entrante)}>
            {t('governedconversations.rechazar')}
          </Button>
        </div>
      )}

      <PantallaDeChat incrustada>
        <ListaDeChats
          buscar={{ valor: filtro, onCambiar: setFiltro, etiqueta: t('governedconversations.buscar') }}
          cargando={loadingConversations}
          vacio={!loadingConversations && conversations.length === 0
            ? { icono: <MessagesSquare size={28} />, titulo: String(emptyTitle || t('governedconversations.sin_mensajes')), descripcion: emptyDescription ? String(emptyDescription) : undefined }
            : null}
          accion={botonNueva}>
          {conversations.filter(c => !filtro || (c.title || '').toLowerCase().includes(filtro.toLowerCase())).map((conversation) => (
            <FilaDeConversacion key={conversation.id} avatar
              titulo={conversation.title || t('governedconversations.sin_titulo')}
              activa={conversation.id === selectedConversationId}
              onClick={() => setSelectedConversationId(conversation.id)}
              noLeidos={(mode === 'team' ? conversation.unread_for_team : conversation.unread_for_client) || 0}
              etiquetaNoLeidos={t('governedconversations.sin_leer')} />
          ))}
        </ListaDeChats>

        {!selectedConversation ? (
          <PanelVacio icono={<MessagesSquare size={28} />} titulo={String(emptyTitle || t('governedconversations.sin_mensajes'))}
            descripcion={emptyDescription ? String(emptyDescription) : undefined} accion={botonNueva} />
        ) : (
          <PanelDeChat etiqueta={selectedConversation.title || t('governedconversations.sin_titulo')}>
            <CabeceraDeConversacion
              titulo={selectedConversation.title || t('governedconversations.sin_titulo')}
              icono={<MessagesSquare size={18} aria-hidden="true" />}
              indicador={mode === 'team' && esNativa
                ? <IndicadorDeCabecera texto={t('governedconversations.origen_gobernada')} explicacion={explicacionDeSupervision} />
                : null}
              subtitulo={(selectedConversation.participants || []).map((participant) => participant.display_name).join(', ') || null}
              acciones={puedeLlamar ? (llamadaEnCurso ? (
                <Button size="sm" icon={llamadaEnCurso.kind === 'video' ? <Video size={13} /> : <Phone size={13} />} loading={unirse.isPending} onClick={() => unirse.mutate(llamadaEnCurso.id)}>
                  {t('governedconversations.unirse')}
                </Button>
              ) : (
                <BotonesDeLlamada onLlamar={(kind) => llamar.mutate(kind)} desactivado={llamar.isPending}
                  video={!!ajustes?.video_enabled}
                  etiquetaVoz={t('governedconversations.llamar')} etiquetaVideo={t('governedconversations.videollamada')} />
              )) : null}
            />
            <ZonaDeMensajes etiqueta={t('governedconversations.mensajes')}>
              {loadingMessages && <div className="u-text3-xs" role="status">{t('governedconversations.cargando_mensajes')}</div>}
              {messages.map((message, i) => (
                // 24-11-2026 (burbujas): separador de día; lo de quien mira (`esMio`) a la derecha.
                <Fragment key={message.id}>
                {cambiaDeDia(messages[i - 1]?.created_at, message.created_at) && <SeparadorDeDia fecha={message.created_at} />}
                <MessageBubble message={message} mode={mode}
                  compact={esCompacto(messages[i - 1], message)}
                  onReview={(item, decision) => reviewMessage.mutate({ messageId: item.id, decision })}
                  conversationId={selectedConversationId || undefined}
                  api={chat}
                  isMine={esMio(message)}
                  viewerUserId={viewerUserId}
                  viewerClientId={viewerClientId}
                  onReply={(m) => { setEditing(null); setReplyTo(m) }}
                  onEdit={empezarEdicion}
                  onDelete={borrarMensaje}
                  onReact={(m, emoji) => react.mutate({ messageId: m.id, emoji })}
                  onHistory={mode === 'team' ? verHistorial : undefined}
                  onError={(e) => toast.error(errorDe(e, t('governedconversations.err_descargar')))}
                />
                </Fragment>
              ))}
            </ZonaDeMensajes>
            <Escribiendo texto={escribiendoAqui
              ? t('governedconversations.escribiendo', { name: escribiendoAqui.name || t(mode === 'team' ? 'governedconversations.remitente_cliente' : 'governedconversations.remitente_equipo') })
              : null} />
            <ConversationComposer
              mode={mode}
              value={draft}
              onChange={setDraft}
              onSend={() => sendMessage.mutate()}
              sending={sendMessage.isPending}
              canInternalNotes={mode === 'team' && selectedConversation?.source !== 'legacy_client_message'}
              isInternalNote={isInternalNote}
              onToggleInternalNote={setIsInternalNote}
              disabled={!selectedConversationId}
              replyTo={esNativa ? replyTo : null}
              onCancelReply={() => setReplyTo(null)}
              editing={editing}
              onCancelEdit={cancelarEdicion}
              onAttach={esNativa ? (file) => attach.mutate(file) : undefined}
              attaching={attach.isPending}
              settings={ajustes || null}
              onTyping={avisarEscribiendo}
            />
          </PanelDeChat>
        )}
      </PantallaDeChat>

      <CreateConversationModal
        mode={mode}
        open={showCreate}
        onClose={() => setShowCreate(false)}
        onSubmit={(payload) => createConversation.mutate(payload)}
        projectOptions={projectOptions}
        defaultProjectId={selectedProject}
        teamUsers={teamUsers}
        clientUsers={portalClients}
        saving={createConversation.isPending}
      />

      {historial && (
        <Modal open onClose={() => setHistorial(null)} title={t('governedconversations.historial_titulo')} avisarSinGuardar={false}>
          {historial.versiones.length === 0 ? (
            <div className="u-text2-sm">{t('governedconversations.historial_vacio')}</div>
          ) : (
            <ol className="chat-portal-historial">
              {historial.versiones.map(v => (
                <li key={v.id}>
                  <div className="u-text3-xs">
                    {t(v.change_type === 'delete' ? 'governedconversations.historial_borrado' : 'governedconversations.historial_edicion')} · {v.edited_at || ''}
                  </div>
                  <div className="goveconv-txt-4">{v.raw_body || v.body || ''}</div>
                </li>
              ))}
            </ol>
          )}
        </Modal>
      )}

      {llamada && (
        <LlamadaDelPortal
          llamada={llamada}
          titulo={selectedConversation?.title || llamada.conversation_title || t('governedconversations.llamada')}
          esperando={llamada.status === 'ringing' && mode === 'team'}
          onColgar={colgar}
          t={t}
        />
      )}
    </div>
  )
}

export function TeamGovernedConversationInbox(props: Partial<GovernedConversationInboxProps>) {
  const { user } = useAuth()
  return (
    <GovernedConversationInbox
      {...props}
      mode="team"
      apiClient={api}
      queryPrefix="portal-conversations-team"
      enableRealtime
      wsTicketPath="/ws/ticket"
      wsEndpoint="/ws/notifications"
      viewerUserId={user?.id ? String(user.id) : null}
    />
  )
}

export function ClientGovernedConversationInbox(props: Partial<GovernedConversationInboxProps>) {
  const { client } = useClientAuth()
  return (
    <GovernedConversationInbox
      {...props}
      mode="client"
      apiClient={CLIENT_API}
      queryPrefix="portal-conversations-client"
      enableRealtime
      wsTicketPath="/ws/portal-ticket"
      wsEndpoint="/ws/portal-notifications"
      viewerClientId={client?.id ? String(client.id) : null}
    />
  )
}

export const PortalCardStyles = PORTAL_STYLES
