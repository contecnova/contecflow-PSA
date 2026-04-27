import React, { useEffect, useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import api from '../../services/api'
import { useToast } from '../../context/ToastContext'
import { extractErr } from '../../utils/helpers'
import { resolveWsBase } from '../../utils/wsUtils'
import { CLIENT_API, S as PORTAL_STYLES } from '../../pages/portal-client/portalClientContext'

const cardStyle = {
  background: 'var(--surface-2)',
  border: '1px solid var(--surface-4)',
  borderRadius: 14,
}

const inputStyle = {
  width: '100%',
  background: 'var(--surface-3)',
  border: '1px solid var(--surface-4)',
  borderRadius: 8,
  padding: '9px 12px',
  color: 'var(--text-1)',
  fontSize: 13,
  outline: 'none',
  fontFamily: 'inherit',
  boxSizing: 'border-box',
}

const labelStyle = {
  fontSize: 11,
  fontWeight: 700,
  color: 'var(--text-2)',
  textTransform: 'uppercase',
  letterSpacing: '0.07em',
  display: 'block',
  marginBottom: 5,
}

const TOPIC_OPTIONS = [
  { value: 'general', label: 'General' },
  { value: 'project', label: 'Proyecto' },
  { value: 'billing', label: 'Facturación' },
  { value: 'security', label: 'Seguridad' },
  { value: 'governance', label: 'Gobierno / GRC' },
]

const SOURCE_LABEL = {
  native: 'Gobernada',
  legacy_client_message: 'Legacy',
}

const GRC_LABEL = {
  allowed: { text: 'Permitido', color: 'var(--success)' },
  pending_review: { text: 'Pendiente revisión', color: 'var(--warning)' },
  redacted: { text: 'Redactado', color: 'var(--accent)' },
  blocked: { text: 'Bloqueado', color: 'var(--danger)' },
}

const EMPTY_LIST = []

function Badge({ children, color = 'var(--text-2)' }) {
  return (
    <span style={{ fontSize: 10, fontWeight: 700, padding: '2px 8px', borderRadius: 999, background: `${color}22`, color, border: `1px solid ${color}33`, textTransform: 'uppercase', letterSpacing: '0.05em' }}>
      {children}
    </span>
  )
}

function ConversationListItem({ conversation, selected, onSelect, mode }) {
  const unread = mode === 'team' ? conversation.unread_for_team : conversation.unread_for_client
  const lastPreview = conversation.last_message?.body || conversation.title
  return (
    <button
      onClick={() => onSelect(conversation.id)}
      style={{
        width: '100%',
        textAlign: 'left',
        border: `1px solid ${selected ? 'var(--accent-glow)' : 'var(--surface-4)'}`,
        background: selected ? 'var(--accent-muted)' : 'var(--surface-1)',
        borderRadius: 12,
        padding: '12px 14px',
        cursor: 'pointer',
        color: 'inherit',
        fontFamily: 'inherit',
      }}
    >
      <div style={{ display: 'flex', justifyContent: 'space-between', gap: 10, marginBottom: 6 }}>
        <div style={{ fontSize: 13, fontWeight: 700, color: 'var(--text-1)' }}>{conversation.title || 'Conversación sin título'}</div>
        <div style={{ fontSize: 10, color: 'var(--text-3)', whiteSpace: 'nowrap' }}>{(conversation.last_message_at || conversation.created_at || '').slice(0, 16)}</div>
      </div>
      <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginBottom: 8 }}>
        <Badge color={conversation.source === 'legacy_client_message' ? 'var(--warning)' : 'var(--accent)'}>{SOURCE_LABEL[conversation.source] || conversation.source}</Badge>
        {conversation.pending_review_count > 0 && <Badge color="var(--warning)">{conversation.pending_review_count} revisión</Badge>}
        {conversation.is_sla_breached && <Badge color="var(--danger)">SLA vencido</Badge>}
        {unread > 0 && <Badge color="var(--danger)">{unread} sin leer</Badge>}
      </div>
      <div style={{ fontSize: 12, color: 'var(--text-2)', lineHeight: 1.45 }}>{lastPreview ? String(lastPreview).slice(0, 120) : 'Sin mensajes aún'}</div>
    </button>
  )
}

function MessageBubble({ message, mode, onReview }) {
  const grc = GRC_LABEL[message.grc_status] || { text: message.grc_status, color: 'var(--text-2)' }
  const alignSelf = message.sender_type === 'client' ? 'flex-start' : 'flex-end'
  const bubbleBg = message.sender_type === 'client' ? 'var(--surface-1)' : 'rgba(0,212,255,0.08)'
  const borderColor = message.grc_status === 'pending_review' ? 'var(--warning-border)' : 'var(--surface-4)'
  return (
    <div style={{ display: 'flex', flexDirection: 'column', alignItems: alignSelf }}>
      <div style={{ maxWidth: '88%', width: 'fit-content', background: bubbleBg, border: `1px solid ${borderColor}`, borderRadius: 14, padding: '12px 14px' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', gap: 10, marginBottom: 6 }}>
          <div style={{ fontSize: 12, fontWeight: 700 }}>{message.sender_name}</div>
          <div style={{ fontSize: 10, color: 'var(--text-3)' }}>{(message.created_at || '').slice(0, 16)}</div>
        </div>
        <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginBottom: 8 }}>
          <Badge color={message.sender_type === 'client' ? 'var(--warning)' : 'var(--accent)'}>{message.sender_type}</Badge>
          <Badge color={grc.color}>{grc.text}</Badge>
          {message.is_internal_note && <Badge color="var(--danger)">Interna</Badge>}
          {message.is_redacted && <Badge color="var(--accent)">Redactada</Badge>}
          {message.source === 'legacy_client_message' && <Badge color="var(--warning)">Legacy</Badge>}
        </div>
        <div style={{ fontSize: 13, color: 'var(--text-1)', whiteSpace: 'pre-wrap', lineHeight: 1.5 }}>{message.body}</div>
        {message.moderation_notes && <div style={{ marginTop: 8, fontSize: 11, color: 'var(--text-2)' }}>Moderación: {message.moderation_notes}</div>}
        {mode === 'team' && message.grc_status === 'pending_review' && (
          <div style={{ display: 'flex', gap: 8, marginTop: 10 }}>
            <button onClick={() => onReview(message, 'approved')} style={{ background: 'var(--success-bg)', border: '1px solid var(--success-border)', color: 'var(--success)', borderRadius: 8, padding: '6px 10px', cursor: 'pointer', fontSize: 12, fontFamily: 'inherit', fontWeight: 700 }}>
              Aprobar
            </button>
            <button onClick={() => onReview(message, 'rejected')} style={{ background: 'var(--danger-bg)', border: '1px solid var(--danger-border)', color: 'var(--danger)', borderRadius: 8, padding: '6px 10px', cursor: 'pointer', fontSize: 12, fontFamily: 'inherit', fontWeight: 700 }}>
              Rechazar
            </button>
          </div>
        )}
      </div>
    </div>
  )
}

function ConversationComposer({ mode, value, onChange, onSend, sending, canInternalNotes, isInternalNote, onToggleInternalNote, disabled }) {
  return (
    <div style={{ ...cardStyle, padding: '14px 16px' }}>
      <label style={labelStyle}>Responder</label>
      <textarea
        value={value}
        onChange={(event) => onChange(event.target.value)}
        rows={4}
        placeholder={mode === 'team' ? 'Responder al cliente o dejar una nota gobernada' : 'Escribe tu mensaje al equipo'}
        style={{ ...inputStyle, resize: 'vertical', marginBottom: 10 }}
      />
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
        <label style={{ display: canInternalNotes ? 'flex' : 'none', gap: 8, alignItems: 'center', fontSize: 12, color: 'var(--text-2)', cursor: 'pointer' }}>
          <input type="checkbox" checked={isInternalNote} onChange={(event) => onToggleInternalNote(event.target.checked)} />
          Enviar como nota interna
        </label>
        <button
          onClick={onSend}
          disabled={disabled || sending || !value.trim()}
          style={{ background: 'var(--accent)', border: 'none', borderRadius: 8, padding: '9px 14px', color: 'var(--portal-bg)', cursor: disabled || sending || !value.trim() ? 'not-allowed' : 'pointer', opacity: disabled || sending || !value.trim() ? 0.6 : 1, fontWeight: 700, fontFamily: 'inherit' }}
        >
          {sending ? 'Enviando…' : 'Enviar mensaje'}
        </button>
      </div>
    </div>
  )
}

function CreateConversationModal({ mode, open, onClose, onSubmit, projectOptions, defaultProjectId, teamUsers, clientUsers, saving }) {
  const [form, setForm] = useState({
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

  if (!open) return null

  return (
    <div style={{ position: 'fixed', inset: 0, background: 'rgba(0, 0, 0, 0.45)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 1000, padding: 20 }}>
      <div role="dialog" aria-modal="true" style={{ ...cardStyle, width: 620, maxWidth: '100%', maxHeight: '90vh', overflowY: 'auto', padding: '18px 20px' }}>
        <div style={{ fontSize: 17, fontWeight: 800, marginBottom: 16 }}>{mode === 'team' ? 'Nueva conversación gobernada' : 'Nueva conversación con el equipo'}</div>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 14 }}>
          <div style={{ gridColumn: '1 / -1' }}>
            <label style={labelStyle}>Título</label>
            <input value={form.title} onChange={(event) => setForm((prev) => ({ ...prev, title: event.target.value }))} style={inputStyle} />
          </div>
          <div>
            <label style={labelStyle}>Tipo</label>
            <select value={form.topic_type} onChange={(event) => setForm((prev) => ({ ...prev, topic_type: event.target.value }))} style={inputStyle}>
              {TOPIC_OPTIONS.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
            </select>
          </div>
          <div>
            <label style={labelStyle}>Proyecto</label>
            <select value={form.project_id} onChange={(event) => setForm((prev) => ({ ...prev, project_id: event.target.value }))} style={inputStyle}>
              <option value="">Sin proyecto</option>
              {projectOptions.map((project) => <option key={project.id} value={project.id}>{project.code ? `${project.code} — ` : ''}{project.name}</option>)}
            </select>
          </div>
          {mode === 'team' && (
            <>
              <div>
                <label style={labelStyle}>Equipo invitado</label>
                <select multiple value={form.internal_user_ids} onChange={(event) => setForm((prev) => ({ ...prev, internal_user_ids: Array.from(event.target.selectedOptions).map((option) => option.value) }))} style={{ ...inputStyle, minHeight: 110 }}>
                  {teamUsers.map((user) => <option key={user.id} value={user.id}>{user.full_name || user.email}</option>)}
                </select>
              </div>
              <div>
                <label style={labelStyle}>Usuarios portal invitados</label>
                <select multiple value={form.client_user_ids} onChange={(event) => setForm((prev) => ({ ...prev, client_user_ids: Array.from(event.target.selectedOptions).map((option) => option.value) }))} style={{ ...inputStyle, minHeight: 110 }}>
                  {clientUsers.map((user) => <option key={user.id} value={user.id}>{user.full_name || user.email}</option>)}
                </select>
              </div>
            </>
          )}
          <div style={{ gridColumn: '1 / -1' }}>
            <label style={labelStyle}>Primer mensaje</label>
            <textarea value={form.body} onChange={(event) => setForm((prev) => ({ ...prev, body: event.target.value }))} rows={5} style={{ ...inputStyle, resize: 'vertical' }} />
          </div>
        </div>
        <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 10, marginTop: 16 }}>
          <button onClick={onClose} style={{ background: 'transparent', border: '1px solid var(--surface-4)', borderRadius: 8, padding: '8px 14px', color: 'var(--text-2)', cursor: 'pointer', fontFamily: 'inherit' }}>Cancelar</button>
          <button onClick={() => onSubmit(form)} disabled={saving || !form.title.trim() || !form.body.trim()} style={{ background: 'var(--accent)', border: 'none', borderRadius: 8, padding: '8px 14px', color: 'var(--portal-bg)', cursor: saving || !form.title.trim() || !form.body.trim() ? 'not-allowed' : 'pointer', fontWeight: 700, fontFamily: 'inherit', opacity: saving || !form.title.trim() || !form.body.trim() ? 0.6 : 1 }}>
            {saving ? 'Creando…' : 'Crear conversación'}
          </button>
        </div>
      </div>
    </div>
  )
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
}) {
  const toast = useToast()
  const qc = useQueryClient()
  const [selectedProject, setSelectedProject] = useState(initialProjectId || projectOptions[0]?.id || '')
  const [selectedConversationId, setSelectedConversationId] = useState(null)
  const [draft, setDraft] = useState('')
  const [isInternalNote, setIsInternalNote] = useState(false)
  const [showCreate, setShowCreate] = useState(false)

  useEffect(() => {
    if (!selectedProject && initialProjectId) setSelectedProject(initialProjectId)
  }, [initialProjectId, selectedProject])

  const filters = useMemo(() => ({
    project_id: selectedProject || undefined,
    client_org_id: mode === 'team' ? clientOrgId || undefined : undefined,
  }), [clientOrgId, mode, selectedProject])

  const listPath = mode === 'team' ? '/portal/conversations/team' : '/portal/conversations'
  const listQueryKey = [queryPrefix, 'list', selectedProject || 'all', clientOrgId || 'all']

  const { data: conversationsData, isLoading: loadingConversations } = useQuery({
    queryKey: listQueryKey,
    queryFn: () => apiClient.get(listPath, { params: filters }).then((response) => response.data).catch(() => []),
    refetchInterval: enableRealtime ? false : 30000,
  })
  const conversations = conversationsData || EMPTY_LIST

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

  const { data: messagesData, isLoading: loadingMessages } = useQuery({
    queryKey: messagesQueryKey,
    queryFn: () => apiClient.get(messagesPath).then((response) => response.data),
    enabled: !!messagesPath,
  })
  const messages = messagesData || EMPTY_LIST

  const { data: teamUsersData } = useQuery({
    queryKey: ['users', 'portal-conversations'],
    queryFn: () => api.get('/users').then((response) => Array.isArray(response.data) ? response.data : (response.data?.items || [])).catch(() => []),
    enabled: mode === 'team' && showCreate,
  })
  const teamUsers = teamUsersData || EMPTY_LIST

  const { data: portalClientsData } = useQuery({
    queryKey: ['portal-clients', 'portal-conversations', selectedProject || 'all', clientOrgId || 'all'],
    queryFn: () => api.get('/portal/clients', { params: { project_id: selectedProject || undefined, client_org_id: clientOrgId || undefined } }).then((response) => response.data).catch(() => []),
    enabled: mode === 'team' && showCreate && Boolean(selectedProject || clientOrgId),
  })
  const portalClients = portalClientsData || EMPTY_LIST

  const createConversation = useMutation({
    mutationFn: async (payload) => {
      const createResponse = await apiClient.post(listPath, {
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
      toast.success('Conversación creada')
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
    mutationFn: ({ messageId, decision }) => api.post(`/portal/conversations/team/${selectedConversationId}/messages/${messageId}/review`, { decision }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: [queryPrefix] })
      toast.success('Revisión aplicada')
    },
    onError: (error) => toast.error(extractErr(error, 'No se pudo revisar el mensaje')),
  })

  useEffect(() => {
    if (!enableRealtime || !wsTicketPath || !wsEndpoint) return undefined
    let socket = null
    let pingInterval = null
    let closed = false

    async function connect() {
      try {
        const response = await apiClient.get(wsTicketPath)
        const ticket = response?.data?.ticket
        if (!ticket || closed) return
        const wsBase = resolveWsBase()
        socket = new window.WebSocket(`${wsBase}${wsEndpoint}?ticket=${encodeURIComponent(ticket)}`)
        socket.onmessage = () => {
          qc.invalidateQueries({ queryKey: [queryPrefix] })
        }
        socket.onerror = () => {
          if (socket) socket.close()
        }
        pingInterval = window.setInterval(() => {
          if (socket && socket.readyState === window.WebSocket.OPEN) {
            socket.send(JSON.stringify({ type: 'ping' }))
          }
        }, 25000)
      } catch {
        // Polling remains as fallback.
      }
    }

    connect()
    return () => {
      closed = true
      if (pingInterval) window.clearInterval(pingInterval)
      if (socket && socket.readyState === window.WebSocket.OPEN) socket.close()
    }
  }, [apiClient, enableRealtime, qc, queryPrefix, wsEndpoint, wsTicketPath])

  const headerKpi = conversations.reduce((total, conversation) => total + (mode === 'team' ? conversation.unread_for_team : conversation.unread_for_client), 0)

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 12, marginBottom: 16, flexWrap: 'wrap' }}>
        <div>
          <div style={{ fontSize: 18, fontWeight: 800, marginBottom: 4 }}>{title}</div>
          <div style={{ fontSize: 12, color: 'var(--text-2)' }}>{conversations.length} conversación(es) · {headerKpi} sin leer</div>
        </div>
        <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
          {projectOptions.length > 1 && (
            <select value={selectedProject} onChange={(event) => setSelectedProject(event.target.value)} style={{ ...inputStyle, minWidth: 220 }}>
              <option value="">Todos los proyectos</option>
              {projectOptions.map((project) => <option key={project.id} value={project.id}>{project.code ? `${project.code} — ` : ''}{project.name}</option>)}
            </select>
          )}
          <button onClick={() => setShowCreate(true)} style={{ background: 'var(--accent)', border: 'none', borderRadius: 8, padding: '9px 14px', color: 'var(--portal-bg)', cursor: 'pointer', fontWeight: 700, fontFamily: 'inherit' }}>Nueva conversación</button>
        </div>
      </div>

      {loadingConversations ? (
        <div style={{ fontSize: 13, color: 'var(--text-2)', padding: '30px 0' }}>Cargando conversaciones…</div>
      ) : conversations.length === 0 ? (
        <div style={{ ...cardStyle, padding: '32px 24px', textAlign: 'center' }}>
          <div style={{ fontSize: 38, marginBottom: 12 }}>💬</div>
          <div style={{ fontSize: 16, fontWeight: 700, marginBottom: 6 }}>{emptyTitle}</div>
          <div style={{ fontSize: 13, color: 'var(--text-2)' }}>{emptyDescription}</div>
        </div>
      ) : (
        <div style={{ display: 'grid', gridTemplateColumns: '320px minmax(0, 1fr)', gap: 18 }}>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
            {conversations.map((conversation) => (
              <ConversationListItem key={conversation.id} conversation={conversation} selected={conversation.id === selectedConversationId} onSelect={setSelectedConversationId} mode={mode} />
            ))}
          </div>

          <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
            {selectedConversation && (
              <div style={{ ...cardStyle, padding: '16px 18px' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12, flexWrap: 'wrap', marginBottom: 10 }}>
                  <div>
                    <div style={{ fontSize: 17, fontWeight: 800 }}>{selectedConversation.title}</div>
                    <div style={{ fontSize: 12, color: 'var(--text-2)', marginTop: 4 }}>
                      Tipo: {selectedConversation.topic_type || 'general'}
                      {selectedConversation.assigned_group_name ? ` · Cola: ${selectedConversation.assigned_group_name}` : ''}
                      {selectedConversation.assigned_role_key ? ` · Rol: ${selectedConversation.assigned_role_key}` : ''}
                    </div>
                  </div>
                  <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
                    <Badge color={selectedConversation.source === 'legacy_client_message' ? 'var(--warning)' : 'var(--accent)'}>{SOURCE_LABEL[selectedConversation.source] || selectedConversation.source}</Badge>
                    {selectedConversation.policy?.requires_client_message_approval && <Badge color="var(--warning)">Aprobación cliente</Badge>}
                    {selectedConversation.policy?.requires_team_message_approval && <Badge color="var(--warning)">Aprobación equipo</Badge>}
                    {selectedConversation.is_sla_breached && <Badge color="var(--danger)">SLA vencido</Badge>}
                  </div>
                </div>
                {Array.isArray(selectedConversation.participants) && selectedConversation.participants.length > 0 && (
                  <div style={{ fontSize: 12, color: 'var(--text-2)' }}>
                    Participantes: {selectedConversation.participants.map((participant) => participant.display_name).join(', ')}
                  </div>
                )}
              </div>
            )}

            <div style={{ ...cardStyle, padding: '16px 18px', minHeight: 320 }}>
              {loadingMessages ? (
                <div style={{ fontSize: 13, color: 'var(--text-2)' }}>Cargando mensajes…</div>
              ) : (
                <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
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
  const toast = useToast()
  const qc = useQueryClient()
  const [drafts, setDrafts] = useState({})

  const { data: agentGroupsData } = useQuery({
    queryKey: ['sd-agent-groups', 'portal-conversations'],
    queryFn: () => api.get('/sd/groups').then((response) => response.data || []).catch(() => []),
  })
  const agentGroups = agentGroupsData || EMPTY_LIST

  const { data: policiesData, isLoading } = useQuery({
    queryKey: ['portal-conversation-policies'],
    queryFn: () => api.get('/portal/conversations/team/policies').then((response) => response.data).catch(() => []),
  })
  const policies = policiesData || EMPTY_LIST

  useEffect(() => {
    const nextDrafts = {}
    policies.forEach((policy) => {
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
    mutationFn: ({ topicType, payload }) => api.put(`/portal/conversations/team/policies/${topicType}`, payload),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['portal-conversation-policies'] })
      toast.success('Política guardada')
    },
    onError: (error) => toast.error(extractErr(error, 'No se pudo guardar la política')),
  })

  if (isLoading) return <div style={{ fontSize: 13, color: 'var(--text-2)' }}>Cargando políticas…</div>

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
      {policies.map((policy) => {
        const draft = drafts[policy.topic_type] || {}
        return (
          <div key={policy.id} style={{ ...cardStyle, padding: '16px 18px' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12, marginBottom: 14, flexWrap: 'wrap' }}>
              <div>
                <div style={{ fontSize: 15, fontWeight: 800, textTransform: 'capitalize' }}>{policy.topic_type}</div>
                <div style={{ fontSize: 12, color: 'var(--text-2)' }}>Política GRC y de enrutado para conversaciones de tipo {policy.topic_type}.</div>
              </div>
              <Badge color={policy.is_active ? 'var(--success)' : 'var(--text-2)'}>{policy.is_active ? 'Activa' : 'Inactiva'}</Badge>
            </div>

            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, minmax(0, 1fr))', gap: 14 }}>
              <div>
                <label style={labelStyle}>Modo de asignación</label>
                <select value={draft.assignment_mode || 'manual'} onChange={(event) => setDrafts((prev) => ({ ...prev, [policy.topic_type]: { ...prev[policy.topic_type], assignment_mode: event.target.value } }))} style={inputStyle}>
                  <option value="manual">Manual</option>
                  <option value="owner_based">Owner del proyecto</option>
                  <option value="role_pool">Pool / rol</option>
                </select>
              </div>
              <div>
                <label style={labelStyle}>Rol por defecto</label>
                <input value={draft.default_role_key || ''} onChange={(event) => setDrafts((prev) => ({ ...prev, [policy.topic_type]: { ...prev[policy.topic_type], default_role_key: event.target.value } }))} style={inputStyle} placeholder="admin, manager, pm..." />
              </div>
              <div>
                <label style={labelStyle}>Pool de asignación</label>
                <select value={draft.default_group_id || ''} onChange={(event) => setDrafts((prev) => ({ ...prev, [policy.topic_type]: { ...prev[policy.topic_type], default_group_id: event.target.value } }))} style={inputStyle}>
                  <option value="">Sin pool</option>
                  {agentGroups.map((group) => <option key={group.id} value={group.id}>{group.name}</option>)}
                </select>
              </div>
              <div>
                <label style={labelStyle}>Primera respuesta SLA (h)</label>
                <input type="number" min={0} value={draft.first_response_hours || 0} onChange={(event) => setDrafts((prev) => ({ ...prev, [policy.topic_type]: { ...prev[policy.topic_type], first_response_hours: Number(event.target.value) } }))} style={inputStyle} />
              </div>
              <div>
                <label style={labelStyle}>Escalado SLA (h)</label>
                <input type="number" min={0} value={draft.escalation_hours || 0} onChange={(event) => setDrafts((prev) => ({ ...prev, [policy.topic_type]: { ...prev[policy.topic_type], escalation_hours: Number(event.target.value) } }))} style={inputStyle} />
              </div>
              <div>
                <label style={labelStyle}>Rol aprobador</label>
                <input value={draft.approval_role_key || ''} onChange={(event) => setDrafts((prev) => ({ ...prev, [policy.topic_type]: { ...prev[policy.topic_type], approval_role_key: event.target.value } }))} style={inputStyle} placeholder="admin" />
              </div>
              <div>
                <label style={labelStyle}>Keywords sensibles</label>
                <input value={draft.sensitive_keywords || ''} onChange={(event) => setDrafts((prev) => ({ ...prev, [policy.topic_type]: { ...prev[policy.topic_type], sensitive_keywords: event.target.value } }))} style={inputStyle} placeholder="password, token, iban" />
              </div>
            </div>

            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, minmax(0, 1fr))', gap: 10, marginTop: 14 }}>
              {[
                ['requires_client_message_approval', 'Aprobación para mensajes cliente'],
                ['requires_team_message_approval', 'Aprobación para mensajes equipo'],
                ['redact_sensitive_content', 'Redactar contenido sensible'],
                ['allow_legacy_federation', 'Federar chat legacy'],
              ].map(([key, label]) => (
                <label key={key} style={{ display: 'flex', gap: 8, alignItems: 'center', fontSize: 12, color: 'var(--text-2)', cursor: 'pointer' }}>
                  <input type="checkbox" checked={Boolean(draft[key])} onChange={(event) => setDrafts((prev) => ({ ...prev, [policy.topic_type]: { ...prev[policy.topic_type], [key]: event.target.checked } }))} />
                  {label}
                </label>
              ))}
            </div>

            <div style={{ display: 'flex', justifyContent: 'flex-end', marginTop: 16 }}>
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
                style={{ background: 'var(--accent)', border: 'none', borderRadius: 8, padding: '8px 14px', color: 'var(--portal-bg)', cursor: 'pointer', fontFamily: 'inherit', fontWeight: 700 }}
              >
                Guardar política
              </button>
            </div>
          </div>
        )
      })}
    </div>
  )
}

export function TeamGovernedConversationInbox(props) {
  return (
    <GovernedConversationInbox
      {...props}
      mode="team"
      apiClient={api}
      queryPrefix="portal-conversations-team"
      enableRealtime
      wsTicketPath="/ws/ticket"
      wsEndpoint="/api/v1/ws/notifications"
    />
  )
}

export function ClientGovernedConversationInbox(props) {
  return (
    <GovernedConversationInbox
      {...props}
      mode="client"
      apiClient={CLIENT_API}
      queryPrefix="portal-conversations-client"
      enableRealtime
      wsTicketPath="/ws/portal-ticket"
      wsEndpoint="/api/v1/ws/portal-notifications"
    />
  )
}

export const PortalCardStyles = PORTAL_STYLES