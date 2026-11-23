import { useEffect, useMemo, useState, type ReactNode } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

// TODO type: services/api still JS — apiClient is treated as a loose `{ get, post }` shape.
import api, { portalClientsApi, portalConversationsApi, apiWsUrl } from '../../services/api'
import { useListaDeUsuarios } from '../../hooks/useListas'
// TODO type: ToastContext still JS — useToast().success/error are typed inline.
import { useToast } from '../../context/ToastContext'
import { extractErr } from '../../utils/helpers'
import { CLIENT_API, S as PORTAL_STYLES, useErrorDelPortal } from '../../pages/portal-client/portalClientContext'
import { Button, EmptyState, Select } from '../ui'
import { MessagesSquare, Plus } from 'lucide-react'
import StatusBadge from '../ui/StatusBadge'
import { POLL_FREQUENT_MS, WS_HEARTBEAT_MS } from '../../constants/timings'
import './GovernedConversations.css'
import { type ApiClient, type Conversation, EMPTY_LIST, type Message, type Mode, type ProjectOption, SOURCE_KEY, type Toast, type UserOption, etiquetaDeTema, useTextoConversacion } from './GovernedConversationsComun'
import { ConversationComposer, ConversationListItem, type CreateConversationForm, CreateConversationModal, MessageBubble } from './GovernedConversationsPiezas'
export { useTextoConversacion } from './GovernedConversationsComun'
export { ConversationPoliciesPanel } from './ConversationPoliciesPanel'

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
}: GovernedConversationInboxProps) {
  const t = useTextoConversacion(mode)
  // 16-11-2026: en el portal, los errores del servidor con código salen en el
  // idioma del cliente; en la vista interna, el `detail` de siempre.
  const errorDelPortal = useErrorDelPortal()
  const errorDe = (e: unknown, fallback: string) => mode === 'client' ? errorDelPortal(e, fallback) : extractErr(e, fallback)
  const toast = useToast() as Toast
  const qc = useQueryClient()
  const [selectedProject, setSelectedProject] = useState<string>(initialProjectId || projectOptions[0]?.id || '')
  const [selectedConversationId, setSelectedConversationId] = useState<string | null>(null)
  const [draft, setDraft] = useState<string>('')
  const [isInternalNote, setIsInternalNote] = useState<boolean>(false)
  const [showCreate, setShowCreate] = useState<boolean>(false)

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
    refetchInterval: enableRealtime ? false : POLL_FREQUENT_MS,
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

  const selectedConversation = conversations.find((conversation) => conversation.id === selectedConversationId) || null
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
  })
  const messages: Message[] = messagesData || EMPTY_LIST

  // 23-11-2026: lista compartida de personas (antes clave propia y `.catch` que tragaba el error).
  const { data: teamUsersData } = useListaDeUsuarios(undefined, { enabled: mode === 'team' && showCreate })
  const teamUsers: UserOption[] = teamUsersData || EMPTY_LIST

  const { data: portalClientsData } = useQuery<UserOption[]>({
    queryKey: ['portal-clients', 'portal-conversations', selectedProject || 'all', clientOrgId || 'all'],
    queryFn: () => portalClientsApi.list({ project_id: selectedProject || undefined, client_org_id: clientOrgId || undefined }).then(r => r.data),
    enabled: mode === 'team' && showCreate && Boolean(selectedProject || clientOrgId),
  })
  const portalClients: UserOption[] = portalClientsData || EMPTY_LIST

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
      qc.invalidateQueries({ queryKey: [queryPrefix] })
      setSelectedConversationId(created.id)
      setShowCreate(false)
      toast.success(t('governedconversations.conversacion_creada'))
    },
    onError: (error) => toast.error(errorDe(error, t('governedconversations.err_crear'))),
  })

  const sendMessage = useMutation({
    mutationFn: () => apiClient.post(
      mode === 'team'
        ? `/portal/conversations/team/${selectedConversationId}/messages`
        : `/portal/conversations/${selectedConversationId}/messages`,
      {
        body: draft,
        message_type: 'text',
        is_internal_note: mode === 'team' ? isInternalNote : false,
      },
    ),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: [queryPrefix] })
      setDraft('')
      setIsInternalNote(false)
    },
    onError: (error) => toast.error(errorDe(error, t('governedconversations.err_enviar'))),
  })

  const reviewMessage = useMutation({
    mutationFn: ({ messageId, decision }: { messageId: string; decision: 'approved' | 'rejected' }) => portalConversationsApi.reviewMessage(selectedConversationId, messageId, { decision }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: [queryPrefix] })
      toast.success(t('governedconversations.revision_aplicada'))
    },
    onError: (error) => toast.error(errorDe(error, t('governedconversations.err_revisar'))),
  })

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
        socket.onopen = () => { attempt = 0 }
        socket.onmessage = () => {
          qc.invalidateQueries({ queryKey: [queryPrefix] })
        }
        socket.onerror = () => {
          if (socket) socket.close()
        }
        socket.onclose = (ev) => {
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
    }
  }, [apiClient, enableRealtime, qc, queryPrefix, wsEndpoint, wsTicketPath])

  const headerKpi = conversations.reduce((total, conversation) => total + (mode === 'team' ? conversation.unread_for_team : conversation.unread_for_client), 0)

  return (
    <div>
      <div className="goveconv-row-6">
        <div>
          <div className="goveconv-box-6">{title}</div>
          <div className="u-text2-sm">{t('governedconversations.resumen', { n: conversations.length, sin_leer: headerKpi })}</div>
        </div>
        <div className="u-wrap-10">
          {projectOptions.length > 1 && (
            <Select suelto aria-label={t('gas.proyecto')} placeholder={t('governedconversations.todos_los_proyectos')} value={selectedProject} onChange={(event) => setSelectedProject(event.target.value)} className="goveconv-inputstyle5">
              {projectOptions.map((project) => <option key={project.id} value={project.id}>{project.code ? `${project.code} — ` : ''}{project.name}</option>)}
            </Select>
          )}
          <Button icon={<Plus size={14} />} onClick={() => setShowCreate(true)}>{t('governedconversations.nueva_conversacion')}</Button>
        </div>
      </div>

      {loadingConversations ? (
        <div className="goveconv-box-8">{t('governedconversations.cargando_conversaciones')}</div>
      ) : conversations.length === 0 ? (
        <EmptyState icon={<MessagesSquare size={28} />} title={emptyTitle} description={emptyDescription}
          action={<Button icon={<Plus size={14} />} onClick={() => setShowCreate(true)}>{t('governedconversations.nueva_conversacion')}</Button>} />
      ) : (
        <div className="goveconv-grid-1">
          <div className="u-stack-10">
            {conversations.map((conversation) => (
              <ConversationListItem key={conversation.id} conversation={conversation} selected={conversation.id === selectedConversationId} onSelect={setSelectedConversationId} mode={mode} />
            ))}
          </div>

          <div className="u-stack-14">
            {selectedConversation && (
              <div className="goveconv-cardstyle4">
                <div className="goveconv-row-7">
                  <div>
                    <div className="goveconv-txt-5">{selectedConversation.title}</div>
                    <div className="goveconv-box-11">
                      {t('risks_page.tipo')} {etiquetaDeTema(t, selectedConversation.topic_type)}
                      {selectedConversation.assigned_group_name ? ` · ${t('governedconversations.cola', { name: selectedConversation.assigned_group_name })}` : ''}
                      {selectedConversation.assigned_role_key ? ` · ${t('governedconversations.rol', { name: selectedConversation.assigned_role_key })}` : ''}
                    </div>
                  </div>
                  <div className="u-wrap-6">
                    <StatusBadge color={selectedConversation.source === 'legacy_client_message' ? 'var(--warning)' : 'var(--accent)'}>{SOURCE_KEY[selectedConversation.source] ? t(SOURCE_KEY[selectedConversation.source]) : selectedConversation.source}</StatusBadge>
                    {selectedConversation.policy?.requires_client_message_approval && <StatusBadge color="var(--warning)">{t('governedconversations.aprobacion_cliente')}</StatusBadge>}
                    {selectedConversation.policy?.requires_team_message_approval && <StatusBadge color="var(--warning)">{t('governedconversations.aprobacion_equipo')}</StatusBadge>}
                    {selectedConversation.is_sla_breached && <StatusBadge color="var(--danger)">{t('governedconversations.sla_vencido')}</StatusBadge>}
                  </div>
                </div>
                {Array.isArray(selectedConversation.participants) && selectedConversation.participants.length > 0 && (
                  <div className="u-text2-sm">
                    {t('governedconversations.participantes')} {selectedConversation.participants.map((participant) => participant.display_name).join(', ')}
                  </div>
                )}
              </div>
            )}

            <div className="goveconv-cardstyle5">
              {loadingMessages ? (
                <div className="u-text2-base">{t('governedconversations.cargando_mensajes')}</div>
              ) : (
                <div className="u-stack-12">
                  {messages.map((message) => (
                    <MessageBubble key={message.id} message={message} mode={mode} onReview={(item, decision) => reviewMessage.mutate({ messageId: item.id, decision })} />
                  ))}
                </div>
              )}
            </div>

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
            />
          </div>
        </div>
      )}

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
    </div>
  )
}

export function TeamGovernedConversationInbox(props: Partial<GovernedConversationInboxProps>) {
  return (
    <GovernedConversationInbox
      {...props}
      mode="team"
      apiClient={api}
      queryPrefix="portal-conversations-team"
      enableRealtime
      wsTicketPath="/ws/ticket"
      wsEndpoint="/ws/notifications"
    />
  )
}

export function ClientGovernedConversationInbox(props: Partial<GovernedConversationInboxProps>) {
  return (
    <GovernedConversationInbox
      {...props}
      mode="client"
      apiClient={CLIENT_API}
      queryPrefix="portal-conversations-client"
      enableRealtime
      wsTicketPath="/ws/portal-ticket"
      wsEndpoint="/ws/portal-notifications"
    />
  )
}

export const PortalCardStyles = PORTAL_STYLES