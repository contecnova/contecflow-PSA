import { useEffect, useMemo, useState, type ReactNode, useId } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import type { AxiosInstance } from 'axios'

// TODO type: services/api still JS — apiClient is treated as a loose `{ get, post }` shape.
import api, { usersApi, portalClientsApi, portalConversationsApi, sdGroupsApi, apiWsUrl, type UserListItem } from '../../services/api'
import type { PortalMensajeDeConversacion, PortalPoliticaDeConversacion } from '../../services/api/tipos-alm'
// TODO type: ToastContext still JS — useToast().success/error are typed inline.
import { useToast } from '../../context/ToastContext'
import { extractErr } from '../../utils/helpers'
import { CLIENT_API, S as PORTAL_STYLES } from '../../pages/portal-client/portalClientContext'
import { useAppLang } from '../../i18n/AppLangContext'
import { useDialogo } from '../ui'
import StatusBadge from '../ui/StatusBadge'
import { POLL_FREQUENT_MS, WS_HEARTBEAT_MS } from '../../constants/timings'
import './GovernedConversations.css'

// Formas del backend: app/services/portal_conversation_service (serializacion.py, politicas.py).

type ConversationPolicy = PortalPoliticaDeConversacion
type Message = PortalMensajeDeConversacion

/** `_participant_out` (lo que se pinta). */
interface Participant {
  id: string
  display_name: string
}

/** `_conversation_out` / `_legacy_conversation_out`. */
interface Conversation {
  id: string
  source: string
  title?: string | null
  topic_type?: string | null
  policy?: ConversationPolicy | null
  assigned_group_name?: string | null
  assigned_role_key?: string | null
  is_sla_breached?: boolean
  pending_review_count?: number
  created_at?: string | null
  last_message_at?: string | null
  participants?: Participant[]
  unread_for_team?: number
  unread_for_client?: number
  last_message?: Message | null
}

/** Borrador editable de una política (keywords como texto separado por comas). */
interface PolicyDraft {
  requires_client_message_approval?: boolean
  requires_team_message_approval?: boolean
  redact_sensitive_content?: boolean
  allow_legacy_federation?: boolean
  assignment_mode?: string
  default_role_key?: string
  default_group_id?: string
  first_response_hours?: number
  escalation_hours?: number
  approval_role_key?: string
  sensitive_keywords?: string
}

type PolicyFlag = 'requires_client_message_approval' | 'requires_team_message_approval' | 'redact_sensitive_content' | 'allow_legacy_federation'

/** Lo que se envía al guardar una política. */
interface PolicyPayload {
  requires_client_message_approval: boolean
  requires_team_message_approval: boolean
  redact_sensitive_content: boolean
  allow_legacy_federation: boolean
  assignment_mode?: string
  default_group_id: string | null
  default_role_key: string | null
  first_response_hours: number
  escalation_hours: number
  approval_role_key: string | null
  sensitive_keywords: string[]
}

interface AgentGroup {
  id: string
  name: string
}

/** Cliente axios: el del backoffice o el del portal. */
type ApiClient = Pick<AxiosInstance, 'get' | 'post'>
type Toast = { success: (m: string) => void; error: (m: string) => void }
type Mode = 'team' | 'client'
type ProjectOption = { id: string; name?: string; code?: string }
type UserOption = { id: string; full_name?: string; email?: string }
type GrcLabel = { text: string; color: string }




const TOPIC_OPTIONS = [
  { value: 'general', label: 'General' },
  { value: 'project', label: 'Proyecto' },
  { value: 'billing', label: 'Facturación' },
  { value: 'security', label: 'Seguridad' },
  { value: 'governance', label: 'Gobierno / GRC' },
]

const SOURCE_LABEL: Record<string, string> = {
  native: 'Gobernada',
  legacy_client_message: 'Legacy',
}

const GRC_LABEL: Record<string, GrcLabel> = {
  allowed: { text: 'Permitido', color: 'var(--success)' },
  pending_review: { text: 'Pendiente revisión', color: 'var(--warning)' },
  redacted: { text: 'Redactado', color: 'var(--accent)' },
  blocked: { text: 'Bloqueado', color: 'var(--danger)' },
}

const EMPTY_LIST: never[] = []

const POLICY_FLAGS: Array<[PolicyFlag, string]> = [
  ['requires_client_message_approval', 'Aprobación para mensajes cliente'],
  ['requires_team_message_approval', 'Aprobación para mensajes equipo'],
  ['redact_sensitive_content', 'Redactar contenido sensible'],
  ['allow_legacy_federation', 'Federar chat legacy'],
]


interface ConversationListItemProps {
  conversation: Conversation
  selected: boolean
  onSelect: (id: string) => void
  mode: Mode
}

function ConversationListItem({ conversation, selected, onSelect, mode }: ConversationListItemProps) {
  const { t } = useAppLang()
  const unread = mode === 'team' ? conversation.unread_for_team : conversation.unread_for_client
  const lastPreview = conversation.last_message?.body || conversation.title
  return (
    <button className="goveconv-box-13 governed-sx1"
      onClick={() => onSelect(conversation.id)}
      style={{ border: `1px solid ${selected ? 'var(--accent)' : 'var(--surface-4)'}`, background: selected ? 'var(--accent-muted)' : 'var(--surface-1)' }}
    >
      <div className="goveconv-row-1">
        <div className="goveconv-txt-1">{conversation.title || 'Conversación sin título'}</div>
        <div className="goveconv-txt-2">{(conversation.last_message_at || conversation.created_at || '').slice(0, 16)}</div>
      </div>
      <div className="goveconv-row-2">
        <StatusBadge color={conversation.source === 'legacy_client_message' ? 'var(--warning)' : 'var(--accent)'}>{SOURCE_LABEL[conversation.source] || conversation.source}</StatusBadge>
        {conversation.pending_review_count > 0 && <StatusBadge color="var(--warning)">{conversation.pending_review_count} {t('governedconversations.revision')}</StatusBadge>}
        {conversation.is_sla_breached && <StatusBadge color="var(--danger)">{t('governedconversations.sla_vencido')}</StatusBadge>}
        {unread > 0 && <StatusBadge color="var(--danger)">{unread} {t('governedconversations.sin_leer')}</StatusBadge>}
      </div>
      <div className="goveconv-txt-3">{lastPreview ? String(lastPreview).slice(0, 120) : 'Sin mensajes aún'}</div>
    </button>
  )
}

interface MessageBubbleProps {
  message: Message
  mode: Mode
  onReview: (message: Message, decision: 'approved' | 'rejected') => void
}

function MessageBubble({ message, mode, onReview }: MessageBubbleProps) {
  const { t } = useAppLang()
  const grc = GRC_LABEL[message.grc_status] || { text: message.grc_status, color: 'var(--text-2)' }
  const alignSelf = message.sender_type === 'client' ? 'flex-start' : 'flex-end'
  const bubbleBg = message.sender_type === 'client' ? 'var(--surface-1)' : 'rgba(0,212,255,0.08)'
  const borderColor = message.grc_status === 'pending_review' ? 'var(--warning-border)' : 'var(--surface-4)'
  return (
    <div className="goveconv-stack-1" style={{ alignItems: alignSelf }}>
      <div className="goveconv-box-14 governed-sx2" style={{ background: bubbleBg, border: `1px solid ${borderColor}` }}>
        <div className="goveconv-row-1">
          <div className="u-sm-700">{message.sender_name}</div>
          <div className="u-text3-2xs">{(message.created_at || '').slice(0, 16)}</div>
        </div>
        <div className="goveconv-row-2">
          <StatusBadge color={message.sender_type === 'client' ? 'var(--warning)' : 'var(--accent)'}>{message.sender_type}</StatusBadge>
          <StatusBadge color={grc.color}>{grc.text}</StatusBadge>
          {message.is_internal_note && <StatusBadge color="var(--danger)">{t('governedconversations.interna')}</StatusBadge>}
          {message.is_redacted && <StatusBadge color="var(--accent)">{t('governedconversations.redactada')}</StatusBadge>}
          {message.source === 'legacy_client_message' && <StatusBadge color="var(--warning)">Legacy</StatusBadge>}
        </div>
        <div className="goveconv-txt-4">{message.body}</div>
        {message.moderation_notes && <div className="goveconv-box-1">{t('governedconversations.moderacion')} {message.moderation_notes}</div>}
        {mode === 'team' && message.grc_status === 'pending_review' && (
          <div className="goveconv-row-3">
            <button onClick={() => onReview(message, 'approved')} className="goveconv-box-2">
              {t('aus.aprobar')}
            </button>
            <button onClick={() => onReview(message, 'rejected')} className="goveconv-box-3">
              {t('aus.rechazar')}
            </button>
          </div>
        )}
      </div>
    </div>
  )
}

interface ConversationComposerProps {
  mode: Mode
  value: string
  onChange: (v: string) => void
  onSend: () => void
  sending: boolean
  canInternalNotes: boolean
  isInternalNote: boolean
  onToggleInternalNote: (checked: boolean) => void
  disabled: boolean
}

function ConversationComposer({ mode, value, onChange, onSend, sending, canInternalNotes, isInternalNote, onToggleInternalNote, disabled }: ConversationComposerProps) {
  const idCampo = useId()
  const { t } = useAppLang()
  return (
    <div className="goveconv-cardstyle">
      <label id={`${idCampo}-et1`} htmlFor={`${idCampo}-1`} className="goveconv-labelstyle">{t('mentions.reply')}</label>
      <textarea id={`${idCampo}-1`} aria-labelledby={`${idCampo}-et1`}
        value={value}
        onChange={(event) => onChange(event.target.value)}
        rows={4}
        placeholder={mode === 'team' ? 'Responder al cliente o dejar una nota gobernada' : 'Escribe tu mensaje al equipo'}
        className="goveconv-inputstyle2"
      />
      <div className="goveconv-row-4">
        <label className="goveconv-box-15" style={{ display: canInternalNotes ? 'flex' : 'none' }}>
          <input type="checkbox" aria-label={t('governedconversations.enviar_como_nota_interna')} checked={isInternalNote} onChange={(event) => onToggleInternalNote(event.target.checked)} />
          {t('governedconversations.enviar_como_nota_interna')}
        </label>
        <button className="goveconv-box-16"
          onClick={onSend}
          disabled={disabled || sending || !value.trim()}
          style={{ cursor: disabled || sending || !value.trim() ? 'not-allowed' : 'pointer', opacity: disabled || sending || !value.trim() ? 0.6 : 1 }}
        >
          {sending ? 'Enviando…' : 'Enviar mensaje'}
        </button>
      </div>
    </div>
  )
}

interface CreateConversationModalProps {
  mode: Mode
  open: boolean
  onClose: () => void
  onSubmit: (form: CreateConversationForm) => void
  projectOptions: ProjectOption[]
  defaultProjectId?: string
  teamUsers: UserOption[]
  clientUsers: UserOption[]
  saving: boolean
}

interface CreateConversationForm {
  title: string
  topic_type: string
  project_id: string
  body: string
  internal_user_ids: string[]
  client_user_ids: string[]
}

function CreateConversationModal({ mode, open, onClose, onSubmit, projectOptions, defaultProjectId, teamUsers, clientUsers, saving }: CreateConversationModalProps) {
  const idCampo = useId()
  const { t } = useAppLang()
  const [form, setForm] = useState<CreateConversationForm>({
    title: '',
    topic_type: 'general',
    project_id: defaultProjectId || projectOptions[0]?.id || '',
    body: '',
    internal_user_ids: [],
    client_user_ids: [],
  })

  useEffect(() => {
    if (!open) {
      setForm({
        title: '',
        topic_type: 'general',
        project_id: defaultProjectId || projectOptions[0]?.id || '',
        body: '',
        internal_user_ids: [],
        client_user_ids: [],
      })
    }
  }, [defaultProjectId, open, projectOptions])
  const dialogRef = useDialogo<HTMLDivElement>(open, onClose)

  if (!open) return null

  return (
    <div className="governed-sx3">
      <div ref={dialogRef} role="dialog" aria-modal="true" className="goveconv-cardstyle2">
        <div className="goveconv-box-4">{mode === 'team' ? 'Nueva conversación gobernada' : 'Nueva conversación con el equipo'}</div>
        <div className="u-grid2-14">
          <div className="u-col-full">
            <label id={`${idCampo}-et1`} htmlFor={`${idCampo}-1`} className="goveconv-labelstyle">{t('governedconversations.titulo')}</label>
            <input id={`${idCampo}-1`} aria-labelledby={`${idCampo}-et1`} value={form.title} onChange={(event) => setForm((prev) => ({ ...prev, title: event.target.value }))} className="goveconv-inputstyle" />
          </div>
          <div>
            <label id={`${idCampo}-et2`} htmlFor={`${idCampo}-2`} className="goveconv-labelstyle">{t('alm.type')}</label>
            <select id={`${idCampo}-2`} aria-labelledby={`${idCampo}-et2`} value={form.topic_type} onChange={(event) => setForm((prev) => ({ ...prev, topic_type: event.target.value }))} className="goveconv-inputstyle">
              {TOPIC_OPTIONS.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
            </select>
          </div>
          <div>
            <label id={`${idCampo}-et3`} htmlFor={`${idCampo}-3`} className="goveconv-labelstyle">{t('gas.proyecto')}</label>
            <select id={`${idCampo}-3`} aria-labelledby={`${idCampo}-et3`} value={form.project_id} onChange={(event) => setForm((prev) => ({ ...prev, project_id: event.target.value }))} className="goveconv-inputstyle">
              <option value="">{t('governedconversations.sin_proyecto')}</option>
              {projectOptions.map((project) => <option key={project.id} value={project.id}>{project.code ? `${project.code} — ` : ''}{project.name}</option>)}
            </select>
          </div>
          {mode === 'team' && (
            <>
              <div>
                <label id={`${idCampo}-et4`} htmlFor={`${idCampo}-4`} className="goveconv-labelstyle">{t('governedconversations.equipo_invitado')}</label>
                <select id={`${idCampo}-4`} aria-labelledby={`${idCampo}-et4`} multiple value={form.internal_user_ids} onChange={(event) => setForm((prev) => ({ ...prev, internal_user_ids: Array.from(event.target.selectedOptions).map((option) => option.value) }))} className="goveconv-inputstyle3">
                  {teamUsers.map((user) => <option key={user.id} value={user.id}>{user.full_name || user.email}</option>)}
                </select>
              </div>
              <div>
                <label id={`${idCampo}-et5`} htmlFor={`${idCampo}-5`} className="goveconv-labelstyle">{t('governedconversations.usuarios_portal_invitados')}</label>
                <select id={`${idCampo}-5`} aria-labelledby={`${idCampo}-et5`} multiple value={form.client_user_ids} onChange={(event) => setForm((prev) => ({ ...prev, client_user_ids: Array.from(event.target.selectedOptions).map((option) => option.value) }))} className="goveconv-inputstyle3">
                  {clientUsers.map((user) => <option key={user.id} value={user.id}>{user.full_name || user.email}</option>)}
                </select>
              </div>
            </>
          )}
          <div className="u-col-full">
            <label id={`${idCampo}-et6`} htmlFor={`${idCampo}-6`} className="goveconv-labelstyle">{t('governedconversations.primer_mensaje')}</label>
            <textarea id={`${idCampo}-6`} aria-labelledby={`${idCampo}-et6`} value={form.body} onChange={(event) => setForm((prev) => ({ ...prev, body: event.target.value }))} rows={5} className="goveconv-inputstyle4" />
          </div>
        </div>
        <div className="goveconv-row-5">
          <button onClick={onClose} className="goveconv-box-5">{t('common.cancel')}</button>
          <button className="goveconv-box-17" onClick={() => onSubmit(form)} disabled={saving || !form.title.trim() || !form.body.trim()} style={{ cursor: saving || !form.title.trim() || !form.body.trim() ? 'not-allowed' : 'pointer', opacity: saving || !form.title.trim() || !form.body.trim() ? 0.6 : 1 }}>
            {saving ? 'Creando…' : 'Crear conversación'}
          </button>
        </div>
      </div>
    </div>
  )
}

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
  const { t } = useAppLang()
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
    queryFn: () => apiClient.get<Conversation[]>(listPath, { params: filters }).then((response) => response.data).catch((): Conversation[] => []),
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

  const { data: teamUsersData } = useQuery<UserOption[]>({
    queryKey: ['users', 'portal-conversations'],
    queryFn: () => usersApi.list().then((response: { data: UserListItem[] | { items?: UserListItem[] } }) => Array.isArray(response.data) ? response.data : (response.data?.items || [])).catch((): UserListItem[] => []),
    enabled: mode === 'team' && showCreate,
  })
  const teamUsers: UserOption[] = teamUsersData || EMPTY_LIST

  const { data: portalClientsData } = useQuery<UserOption[]>({
    queryKey: ['portal-clients', 'portal-conversations', selectedProject || 'all', clientOrgId || 'all'],
    queryFn: () => portalClientsApi.list({ project_id: selectedProject || undefined, client_org_id: clientOrgId || undefined }).then(r => r.data).catch(() => []),
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
    onError: (error) => toast.error(extractErr(error, 'No se pudo crear la conversación')),
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
    onError: (error) => toast.error(extractErr(error, 'No se pudo enviar el mensaje')),
  })

  const reviewMessage = useMutation({
    mutationFn: ({ messageId, decision }: { messageId: string; decision: 'approved' | 'rejected' }) => portalConversationsApi.reviewMessage(selectedConversationId, messageId, { decision }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: [queryPrefix] })
      toast.success(t('governedconversations.revision_aplicada'))
    },
    onError: (error) => toast.error(extractErr(error, 'No se pudo revisar el mensaje')),
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
          <div className="u-text2-sm">{conversations.length} {t('governedconversations.conversacion_es')} {headerKpi} {t('governedconversations.sin_leer')}</div>
        </div>
        <div className="u-wrap-10">
          {projectOptions.length > 1 && (
            <select value={selectedProject} onChange={(event) => setSelectedProject(event.target.value)} className="goveconv-inputstyle5">
              <option value="">{t('governedconversations.todos_los_proyectos')}</option>
              {projectOptions.map((project) => <option key={project.id} value={project.id}>{project.code ? `${project.code} — ` : ''}{project.name}</option>)}
            </select>
          )}
          <button onClick={() => setShowCreate(true)} className="goveconv-box-7">{t('governedconversations.nueva_conversacion')}</button>
        </div>
      </div>

      {loadingConversations ? (
        <div className="goveconv-box-8">{t('governedconversations.cargando_conversaciones')}</div>
      ) : conversations.length === 0 ? (
        <div className="goveconv-cardstyle3">
          <div className="goveconv-box-9">💬</div>
          <div className="goveconv-box-10">{emptyTitle}</div>
          <div className="u-text2-base">{emptyDescription}</div>
        </div>
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
                      {t('risks_page.tipo')} {selectedConversation.topic_type || 'general'}
                      {selectedConversation.assigned_group_name ? ` · Cola: ${selectedConversation.assigned_group_name}` : ''}
                      {selectedConversation.assigned_role_key ? ` · Rol: ${selectedConversation.assigned_role_key}` : ''}
                    </div>
                  </div>
                  <div className="u-wrap-6">
                    <StatusBadge color={selectedConversation.source === 'legacy_client_message' ? 'var(--warning)' : 'var(--accent)'}>{SOURCE_LABEL[selectedConversation.source] || selectedConversation.source}</StatusBadge>
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

export function ConversationPoliciesPanel() {
  const idCampo = useId()
  const { t } = useAppLang()
  const toast = useToast()
  const qc = useQueryClient()
  const [drafts, setDrafts] = useState<Record<string, PolicyDraft>>({})

  const { data: agentGroupsData } = useQuery<AgentGroup[]>({
    queryKey: ['sd-agent-groups', 'portal-conversations'],
    queryFn: () => sdGroupsApi.list().then((response) => response.data || []).catch(() => []),
  })
  const agentGroups = agentGroupsData || EMPTY_LIST

  const { data: policiesData, isLoading } = useQuery<ConversationPolicy[]>({
    queryKey: ['portal-conversation-policies'],
    queryFn: () => portalConversationsApi.getPolicies().then((response) => response.data).catch(() => []),
  })
  const policies = policiesData || EMPTY_LIST

  useEffect(() => {
    const nextDrafts: Record<string, PolicyDraft> = {}
    policies.forEach(policy => {
      nextDrafts[policy.topic_type] = {
        requires_client_message_approval: policy.requires_client_message_approval,
        requires_team_message_approval: policy.requires_team_message_approval,
        redact_sensitive_content: policy.redact_sensitive_content,
        allow_legacy_federation: policy.allow_legacy_federation,
        assignment_mode: policy.assignment_mode,
        default_role_key: policy.default_role_key || '',
        default_group_id: policy.default_group_id || '',
        first_response_hours: policy.first_response_hours || 0,
        escalation_hours: policy.escalation_hours || 0,
        approval_role_key: policy.approval_role_key || '',
        sensitive_keywords: Array.isArray(policy.sensitive_keywords) ? policy.sensitive_keywords.join(', ') : '',
      }
    })
    setDrafts((prev) => {
      const prevStr = JSON.stringify(prev)
      const nextStr = JSON.stringify(nextDrafts)
      return prevStr === nextStr ? prev : nextDrafts
    })
  }, [policies])

  const savePolicy = useMutation({
    mutationFn: ({ topicType, payload }: { topicType: string; payload: PolicyPayload }) => portalConversationsApi.updatePolicy(topicType, payload),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['portal-conversation-policies'] })
      toast.success(t('grc.retencion_guardada'))
    },
    onError: (error) => toast.error(extractErr(error, 'No se pudo guardar la política')),
  })

  if (isLoading) return <div className="u-text2-base">{t('governedconversations.cargando_politicas')}</div>

  return (
    <div className="u-stack-14">
      {policies.map(policy => {
        const draft: PolicyDraft = drafts[policy.topic_type] || {}
        return (
          <div key={policy.id} className="goveconv-cardstyle4">
            <div className="goveconv-row-8">
              <div>
                <div className="goveconv-txt-6">{policy.topic_type}</div>
                <div className="u-text2-sm">{t('governedconversations.politica_grc_y_de_enrutado_para_conversaciones')} {policy.topic_type}.</div>
              </div>
              <StatusBadge color={policy.is_active ? 'var(--success)' : 'var(--text-2)'}>{policy.is_active ? 'Activa' : 'Inactiva'}</StatusBadge>
            </div>

            <div className="goveconv-grid-2">
              <div>
                <label className="goveconv-labelstyle">{t('governedconversations.modo_de_asignacion')}</label>
                <select value={draft.assignment_mode || 'manual'} onChange={(event) => setDrafts((prev) => ({ ...prev, [policy.topic_type]: { ...prev[policy.topic_type], assignment_mode: event.target.value } }))} className="goveconv-inputstyle">
                  <option value="manual">{t('governedconversations.manual')}</option>
                  <option value="owner_based">{t('governedconversations.owner_del_proyecto')}</option>
                  <option value="role_pool">{t('governedconversations.pool_rol')}</option>
                </select>
              </div>
              <div>
                <label className="goveconv-labelstyle">{t('governedconversations.rol_por_defecto')}</label>
                <input aria-label="admin, manager, pm..." value={draft.default_role_key || ''} onChange={(event) => setDrafts((prev) => ({ ...prev, [policy.topic_type]: { ...prev[policy.topic_type], default_role_key: event.target.value } }))} className="goveconv-inputstyle" placeholder="admin, manager, pm..." />
              </div>
              <div>
                <label id={`${idCampo}-${policy.id}-et-pool`} htmlFor={`${idCampo}-${policy.id}-pool`} className="goveconv-labelstyle">{t('governedconversations.pool_de_asignacion')}</label>
                <select id={`${idCampo}-${policy.id}-pool`} aria-labelledby={`${idCampo}-${policy.id}-et-pool`} value={draft.default_group_id || ''} onChange={(event) => setDrafts((prev) => ({ ...prev, [policy.topic_type]: { ...prev[policy.topic_type], default_group_id: event.target.value } }))} className="goveconv-inputstyle">
                  <option value="">{t('governedconversations.sin_pool')}</option>
                  {agentGroups.map(group => <option key={group.id} value={group.id}>{group.name}</option>)}
                </select>
              </div>
              <div>
                <label id={`${idCampo}-${policy.id}-et-fr`} htmlFor={`${idCampo}-${policy.id}-fr`} className="goveconv-labelstyle">{t('governedconversations.primera_respuesta_sla_h')}</label>
                <input id={`${idCampo}-${policy.id}-fr`} aria-labelledby={`${idCampo}-${policy.id}-et-fr`} type="number" min={0} value={draft.first_response_hours || 0} onChange={(event) => setDrafts((prev) => ({ ...prev, [policy.topic_type]: { ...prev[policy.topic_type], first_response_hours: Number(event.target.value) } }))} className="goveconv-inputstyle" />
              </div>
              <div>
                <label id={`${idCampo}-${policy.id}-et-esc`} htmlFor={`${idCampo}-${policy.id}-esc`} className="goveconv-labelstyle">{t('governedconversations.escalado_sla_h')}</label>
                <input id={`${idCampo}-${policy.id}-esc`} aria-labelledby={`${idCampo}-${policy.id}-et-esc`} type="number" min={0} value={draft.escalation_hours || 0} onChange={(event) => setDrafts((prev) => ({ ...prev, [policy.topic_type]: { ...prev[policy.topic_type], escalation_hours: Number(event.target.value) } }))} className="goveconv-inputstyle" />
              </div>
              <div>
                <label id={`${idCampo}-${policy.id}-et-apr`} htmlFor={`${idCampo}-${policy.id}-apr`} className="goveconv-labelstyle">{t('governedconversations.rol_aprobador')}</label>
                <input id={`${idCampo}-${policy.id}-apr`} aria-labelledby={`${idCampo}-${policy.id}-et-apr`} value={draft.approval_role_key || ''} onChange={(event) => setDrafts((prev) => ({ ...prev, [policy.topic_type]: { ...prev[policy.topic_type], approval_role_key: event.target.value } }))} className="goveconv-inputstyle" placeholder="admin" />
              </div>
              <div>
                <label id={`${idCampo}-${policy.id}-et-kw`} htmlFor={`${idCampo}-${policy.id}-kw`} className="goveconv-labelstyle">{t('governedconversations.keywords_sensibles')}</label>
                <input id={`${idCampo}-${policy.id}-kw`} aria-labelledby={`${idCampo}-${policy.id}-et-kw`} value={draft.sensitive_keywords || ''} onChange={(event) => setDrafts((prev) => ({ ...prev, [policy.topic_type]: { ...prev[policy.topic_type], sensitive_keywords: event.target.value } }))} className="goveconv-inputstyle" placeholder="password, token, iban" />
              </div>
            </div>

            <div className="goveconv-grid-3">
              {POLICY_FLAGS.map(([key, label]) => (
                <label key={key} className="goveconv-row-9">
                  <input type="checkbox" aria-label={label} checked={Boolean(draft[key])} onChange={(event) => setDrafts((prev) => ({ ...prev, [policy.topic_type]: { ...prev[policy.topic_type], [key]: event.target.checked } }))} />
                  {label}
                </label>
              ))}
            </div>

            <div className="goveconv-row-10">
              <button
                onClick={() => savePolicy.mutate({
                  topicType: policy.topic_type,
                  payload: {
                    requires_client_message_approval: Boolean(draft.requires_client_message_approval),
                    requires_team_message_approval: Boolean(draft.requires_team_message_approval),
                    redact_sensitive_content: Boolean(draft.redact_sensitive_content),
                    allow_legacy_federation: Boolean(draft.allow_legacy_federation),
                    assignment_mode: draft.assignment_mode,
                    default_group_id: draft.default_group_id || null,
                    default_role_key: draft.default_role_key || null,
                    first_response_hours: Number(draft.first_response_hours || 0),
                    escalation_hours: Number(draft.escalation_hours || 0),
                    approval_role_key: draft.approval_role_key || null,
                    sensitive_keywords: String(draft.sensitive_keywords || '').split(',').map((item) => item.trim()).filter(Boolean),
                  },
                })}
                className="goveconv-box-12"
              >
                {t('governedconversations.guardar_politica')}
              </button>
            </div>
          </div>
        )
      })}
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