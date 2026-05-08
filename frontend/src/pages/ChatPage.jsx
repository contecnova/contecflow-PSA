/**
 * ChatPage — Teams-like internal chat for Contecflow PSA.
 * Three-pane layout (sidebar / conversation / context panel) per
 * docs/chat_interno_teams_solucion_final.txt §6.1.
 *
 * Wired to /api/v1/collaboration endpoints + WebSocket realtime.
 */
import { useEffect, useRef, useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  Hash, MessageSquare, Users, Pin, Bookmark, Search,
  Send, Paperclip, AtSign, Plus, Phone, Video, Settings,
  ChevronDown, ChevronRight, Bell, Sparkles, Megaphone, Zap,
  Bot, FileText, AlertCircle, MoreVertical, Trash2, Pencil, X,
  Headphones, ListChecks, FileSignature,
} from 'lucide-react'
import { useToast } from '../context/ToastContext'
import { useAuth } from '../context/AuthContext'
import { collabApi } from '../services/collaborationApi'
import { registerCollabPush } from '../utils/collabPush'

// ── Page entry ───────────────────────────────────────────────────────────────
export default function ChatPage() {
  const qc = useQueryClient()
  const _toast = useToast()
  const { user } = useAuth()

  const [activeTab, setActiveTab] = useState('chats') // chats | teams | activity | calls
  const [activeConv, setActiveConv] = useState(null) // {id, kind, title, ...}
  const [showSlashMenu, setShowSlashMenu] = useState(false)
  const [draft, setDraft] = useState('')
  const [searchModalOpen, setSearchModalOpen] = useState(false)
  const wsRef = useRef(null)

  // ── Data ───────────────────────────────────────────────────────────────────
  useQuery({
    queryKey: ['collab-workspace'],
    queryFn:  () => collabApi.getWorkspace(),
    staleTime: 60_000,
  })

  const { data: conversations = [], isLoading: loadingConvs } = useQuery({
    queryKey: ['collab-conversations'],
    queryFn:  () => collabApi.listConversations(),
    refetchInterval: 30_000,
  })

  const { data: teams = [] } = useQuery({
    queryKey: ['collab-teams'],
    queryFn:  () => collabApi.listTeams(),
    staleTime: 60_000,
  })

  const { data: channels = [] } = useQuery({
    queryKey: ['collab-channels'],
    queryFn:  () => collabApi.listChannels(),
    staleTime: 60_000,
  })

  const { data: presence = [] } = useQuery({
    queryKey: ['collab-presence'],
    queryFn:  () => collabApi.listPresence(),
    refetchInterval: 60_000,
  })

  const { data: notifications = [] } = useQuery({
    queryKey: ['collab-notifications'],
    queryFn:  () => collabApi.listNotifications(false),
    refetchInterval: 30_000,
  })

  const { data: bots = [] } = useQuery({
    queryKey: ['collab-bots'],
    queryFn:  () => collabApi.listBots(),
    staleTime: 5 * 60_000,
  })

  // Pick a default conversation when nothing selected
  useEffect(() => {
    if (!activeConv && conversations.length > 0) {
      const channel = conversations.find(c => c.kind === 'channel')
      setActiveConv(channel || conversations[0])
    }
  }, [conversations, activeConv])

  // Register Web Push subscription (best-effort, only if VAPID configured)
  useEffect(() => {
    registerCollabPush().catch(() => { /* ignore */ })
  }, [])

  // Global keyboard shortcuts
  useEffect(() => {
    const handler = (e) => {
      const isMac = navigator.platform.toUpperCase().includes('MAC')
      const cmd = isMac ? e.metaKey : e.ctrlKey
      if (!cmd) return
      if (e.key.toLowerCase() === 'k') {
        e.preventDefault()
        setSearchModalOpen(true)
      } else if (e.key === '/') {
        e.preventDefault()
        const ta = document.querySelector('[data-chat-composer]')
        if (ta) { ta.focus(); ta.value = '/'; ta.dispatchEvent(new Event('input', { bubbles: true })) }
      } else if (e.shiftKey && e.key.toLowerCase() === 'a') {
        e.preventDefault()
        setActiveTab('activity')
      }
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [])

  // ── WebSocket ──────────────────────────────────────────────────────────────
  useEffect(() => {
    let cancelled = false
    let ws
    let pingInterval
    let reconnectTimer
    let attempt = 0

    const connect = async () => {
      if (cancelled || attempt >= 5) return
      attempt++
      try {
        const r = await fetch('/api/v1/ws/ticket', { credentials: 'include' })
        const { ticket } = await r.json()
        if (!ticket || cancelled) return
        const proto = window.location.protocol === 'https:' ? 'wss' : 'ws'
        ws = new WebSocket(`${proto}://${window.location.host}/api/v1/collaboration/ws?ticket=${encodeURIComponent(ticket)}`)
        wsRef.current = ws
        ws.onopen = () => { attempt = 0 }
        ws.onmessage = (event) => {
          try {
            const ev = JSON.parse(event.data)
            handleRealtimeEvent(ev)
          } catch { /* noop */ }
        }
        ws.onclose = (ev) => {
          if (cancelled || ev.code === 1000) return
          reconnectTimer = setTimeout(connect, Math.min(1000 * 2 ** (attempt - 1), 30000))
        }
        if (pingInterval) clearInterval(pingInterval)
        pingInterval = setInterval(() => {
          if (ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify({ type: 'ping' }))
        }, 25000)
      } catch {
        if (!cancelled) reconnectTimer = setTimeout(connect, Math.min(1000 * 2 ** (attempt - 1), 30000))
      }
    }

    function handleRealtimeEvent(ev) {
      if (!ev?.type) return
      if (ev.type === 'message.created' && ev.conversation_id) {
        qc.invalidateQueries(['collab-messages', ev.conversation_id])
        qc.invalidateQueries(['collab-conversations'])
      } else if (ev.type === 'message.updated' || ev.type === 'message.deleted' ||
                 ev.type.startsWith('reaction.') || ev.type === 'message.pinned' ||
                 ev.type === 'message.unpinned' || ev.type === 'read.updated') {
        if (ev.conversation_id) qc.invalidateQueries(['collab-messages', ev.conversation_id])
      } else if (ev.type === 'notification.new') {
        qc.invalidateQueries(['collab-notifications'])
        // Native browser notification cuando la pestaña no está activa
        try {
          if (typeof Notification !== 'undefined' && Notification.permission === 'granted' && document.visibilityState !== 'visible') {
            new Notification('Contecflow Chat', { body: 'Nueva actividad en tu chat', icon: '/favicon.ico', tag: 'collab' })
          }
        } catch { /* noop */ }
      } else if (ev.type === 'presence.updated') {
        qc.invalidateQueries(['collab-presence'])
      } else if (ev.type === 'typing') {
        // Re-emit como evento DOM para que el ConversationPane lo consuma sin acoplarse al WS
        window.dispatchEvent(new CustomEvent('collab:typing', { detail: ev }))
      }
    }

    connect()
    return () => {
      cancelled = true
      if (pingInterval) clearInterval(pingInterval)
      if (reconnectTimer) clearTimeout(reconnectTimer)
      if (ws && ws.readyState === WebSocket.OPEN) ws.close()
    }
  }, [qc])

  // ── Render ─────────────────────────────────────────────────────────────────
  return (
    <div style={{
      display: 'flex', height: 'calc(100vh - 56px)',
      background: 'var(--surface-0)', color: 'var(--text-1)',
    }}>
      <NavRail activeTab={activeTab} onTab={setActiveTab} unreadNotifs={notifications.filter(n => !n.is_read).length} />

      <ConversationsList
        activeTab={activeTab}
        conversations={conversations}
        teams={teams}
        channels={channels}
        presence={presence}
        loading={loadingConvs}
        activeConv={activeConv}
        onSelect={setActiveConv}
      />

      <ConversationPane
        conv={activeConv}
        currentUser={user}
        _bots={bots}
        draft={draft}
        setDraft={setDraft}
        showSlashMenu={showSlashMenu}
        setShowSlashMenu={setShowSlashMenu}
        wsRef={wsRef}
      />

      {activeConv && <ContextPanel conv={activeConv} />}

      {searchModalOpen && (
        <SearchModal
          onClose={() => setSearchModalOpen(false)}
          onJump={(conversationId) => {
            const c = conversations.find(c => c.id === conversationId)
            if (c) setActiveConv(c)
            setSearchModalOpen(false)
          }}
        />
      )}
    </div>
  )
}

// ── Left rail ────────────────────────────────────────────────────────────────
function NavRail({ activeTab, onTab, unreadNotifs }) {
  const items = [
    { id: 'activity', label: 'Actividad', icon: Bell, badge: unreadNotifs },
    { id: 'chats',    label: 'Chat',      icon: MessageSquare },
    { id: 'teams',    label: 'Equipos',   icon: Users },
    { id: 'calls',    label: 'Llamadas',  icon: Phone },
    { id: 'admin',    label: 'Admin',     icon: Settings },
  ]
  return (
    <div style={{
      width: 72, flexShrink: 0,
      background: 'var(--surface-1)',
      borderRight: '1px solid var(--surface-4)',
      display: 'flex', flexDirection: 'column', alignItems: 'center',
      padding: '12px 0',
    }}>
      {items.map(it => {
        const Icon = it.icon
        const active = activeTab === it.id
        return (
          <button key={it.id} onClick={() => onTab(it.id)} title={it.label}
            style={{
              display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 4,
              width: 60, padding: '10px 4px',
              background: 'transparent', border: 'none',
              borderLeft: `3px solid ${active ? 'var(--accent)' : 'transparent'}`,
              cursor: 'pointer', position: 'relative',
              fontFamily: 'inherit', color: active ? 'var(--accent)' : 'var(--text-2)',
              transition: 'color 0.15s',
            }}>
            <Icon size={20} />
            <span style={{ fontSize: 'var(--text-xs)' }}>{it.label}</span>
            {it.badge > 0 && (
              <span style={{
                position: 'absolute', top: 6, right: 8,
                background: 'var(--danger)', color: '#fff',
                fontSize: 9, fontWeight: 800, padding: '1px 5px',
                borderRadius: 999, minWidth: 14, textAlign: 'center',
              }}>{it.badge > 99 ? '99+' : it.badge}</span>
            )}
          </button>
        )
      })}
    </div>
  )
}

// ── Conversations sidebar (middle column) ────────────────────────────────────
function ConversationsList({ activeTab, conversations, teams, channels, presence, loading, activeConv, onSelect }) {
  const [filter, setFilter] = useState('')
  const [openTeams, setOpenTeams] = useState(true)

  // Hooks must run unconditionally — compute always.
  const presenceMap = (() => {
    const m = {}
    for (const p of presence) if (p.user_id) m[p.user_id] = p.status
    return m
  })()
  const channelsByTeam = (() => {
    const map = {}
    for (const ch of channels) {
      map[ch.team_id] = map[ch.team_id] || []
      map[ch.team_id].push(ch)
    }
    return map
  })()

  if (activeTab === 'activity') return <ActivityList />
  if (activeTab === 'admin') return <AdminPanelEntry />

  const directs = conversations.filter(c => c.kind === 'direct')
  const groups = conversations.filter(c => c.kind === 'group')

  const matches = (text) => !filter || (text || '').toLowerCase().includes(filter.toLowerCase())

  return (
    <div style={{
      width: 300, flexShrink: 0,
      background: 'var(--surface-1)',
      borderRight: '1px solid var(--surface-4)',
      display: 'flex', flexDirection: 'column',
    }}>
      <div style={{ padding: '14px 14px 8px', borderBottom: '1px solid var(--surface-4)' }}>
        <div style={{ position: 'relative' }}>
          <Search size={14} style={{ position: 'absolute', left: 10, top: '50%', transform: 'translateY(-50%)', color: 'var(--text-3)' }} />
          <input
            value={filter} onChange={e => setFilter(e.target.value)}
            placeholder="Buscar…"
            style={{
              width: '100%', boxSizing: 'border-box',
              background: 'var(--surface-3)', border: '1px solid var(--surface-4)',
              borderRadius: 8, padding: '8px 10px 8px 32px',
              color: 'var(--text-1)', fontSize: 'var(--text-sm)',
              outline: 'none', fontFamily: 'inherit',
            }}
          />
        </div>
      </div>

      <div style={{ flex: 1, overflowY: 'auto', padding: '8px 6px' }}>
        {loading && <Loader />}

        {activeTab !== 'teams' && directs.length > 0 && (
          <SectionGroup title="Chats directos" count={directs.length}>
            {directs.filter(c => matches(c.title)).map(c => (
              <ConvRow key={c.id} c={c} active={activeConv?.id === c.id} onClick={() => onSelect(c)}
                presence={c.peer_user_id ? presenceMap[c.peer_user_id] : null} />
            ))}
          </SectionGroup>
        )}

        {activeTab !== 'teams' && groups.length > 0 && (
          <SectionGroup title="Grupos" count={groups.length}>
            {groups.filter(c => matches(c.title)).map(c => (
              <ConvRow key={c.id} c={c} active={activeConv?.id === c.id} onClick={() => onSelect(c)} />
            ))}
          </SectionGroup>
        )}

        <SectionGroup
          title="Equipos"
          count={teams.length}
          collapsed={!openTeams}
          onToggle={() => setOpenTeams(o => !o)}
        >
          {openTeams && teams.filter(t => matches(t.name)).map(team => (
            <div key={team.id} style={{ marginBottom: 6 }}>
              <div style={{
                display: 'flex', alignItems: 'center', gap: 8,
                padding: '6px 10px', fontSize: 'var(--text-sm)', fontWeight: 700,
                color: 'var(--text-2)',
              }}>
                <Users size={13} /> {team.name}
              </div>
              {(channelsByTeam[team.id] || []).filter(ch => matches(ch.name)).map(ch => {
                const conv = conversations.find(c => c.id === ch.conversation_id)
                if (!conv) return null
                return (
                  <ConvRow key={ch.id} c={conv} active={activeConv?.id === conv.id}
                    onClick={() => onSelect(conv)} indent />
                )
              })}
            </div>
          ))}
        </SectionGroup>
      </div>

      <div style={{ padding: '10px 14px', borderTop: '1px solid var(--surface-4)' }}>
        <NewConversationButton />
      </div>
    </div>
  )
}

function SectionGroup({ title, count, children, collapsed, onToggle }) {
  return (
    <div style={{ marginBottom: 12 }}>
      <button onClick={onToggle} style={{
        display: 'flex', alignItems: 'center', gap: 6,
        width: '100%', padding: '4px 10px',
        background: 'none', border: 'none', cursor: onToggle ? 'pointer' : 'default',
        fontFamily: 'inherit', color: 'var(--text-3)',
        fontSize: 'var(--text-2xs, 10px)', fontWeight: 700,
        textTransform: 'uppercase', letterSpacing: '0.08em',
      }}>
        {onToggle ? (collapsed ? <ChevronRight size={11} /> : <ChevronDown size={11} />) : null}
        {title} {count != null && <span style={{ color: 'var(--text-4)' }}>({count})</span>}
      </button>
      {!collapsed && children}
    </div>
  )
}

function ConvRow({ c, active, onClick, presence, indent }) {
  return (
    <button onClick={onClick} style={{
      display: 'flex', alignItems: 'center', gap: 10,
      width: '100%', padding: '7px 10px',
      paddingLeft: indent ? 22 : 10,
      background: active ? 'var(--accent-muted)' : 'transparent',
      border: '1px solid transparent',
      borderRadius: 6,
      fontFamily: 'inherit', textAlign: 'left',
      color: active ? 'var(--accent)' : 'var(--text-1)',
      fontSize: 'var(--text-sm)', fontWeight: 500,
      cursor: 'pointer', position: 'relative',
    }}
      onMouseEnter={e => { if (!active) e.currentTarget.style.background = 'var(--surface-3)' }}
      onMouseLeave={e => { if (!active) e.currentTarget.style.background = 'transparent' }}
    >
      {c.kind === 'channel' && <Hash size={13} />}
      {c.kind === 'direct'  && (
        <span style={{ position: 'relative', display: 'inline-flex' }}>
          <span style={{
            width: 22, height: 22, borderRadius: '50%',
            background: 'linear-gradient(135deg, var(--accent), var(--purple, #7c3aed))',
            color: '#fff', display: 'flex', alignItems: 'center', justifyContent: 'center',
            fontSize: 10, fontWeight: 800,
          }}>{(c.title || '?').charAt(0).toUpperCase()}</span>
          {presence && presence !== 'offline' && (
            <span style={{
              position: 'absolute', bottom: 0, right: -2,
              width: 8, height: 8, borderRadius: '50%',
              background: presence === 'online' ? 'var(--success)' : presence === 'busy' ? 'var(--danger)' : 'var(--warning)',
              border: '1.5px solid var(--surface-1)',
            }} />
          )}
        </span>
      )}
      {c.kind === 'group' && <Users size={13} />}
      <span style={{ flex: 1, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{c.title}</span>
    </button>
  )
}

function NewConversationButton() {
  return (
    <button style={{
      width: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 6,
      padding: '8px',
      background: 'var(--accent)', color: '#fff',
      border: 'none', borderRadius: 8,
      fontFamily: 'inherit', fontSize: 'var(--text-sm)', fontWeight: 700,
      cursor: 'pointer',
    }} title="Próximamente: nuevo chat / canal">
      <Plus size={14} /> Nuevo
    </button>
  )
}

// ── Conversation pane ────────────────────────────────────────────────────────
function ConversationPane({ conv, currentUser, _bots, draft, setDraft, showSlashMenu, setShowSlashMenu, wsRef }) {
  const qc = useQueryClient()
  const toast = useToast()
  const fileRef = useRef(null)
  const composerRef = useRef(null)
  const messagesEndRef = useRef(null)
  const [editing, setEditing] = useState(null) // { id, body }
  const [mentionState, setMentionState] = useState(null) // { query, anchor, items }
  const [activeThreadRoot, setActiveThreadRoot] = useState(null)
  const [linkPicker, setLinkPicker] = useState(null) // { kind: 'task'|'ticket', items }
  const [typingUsers, setTypingUsers] = useState({})  // { user_id: ts }

  const { data: messages = [], isLoading } = useQuery({
    queryKey: ['collab-messages', conv?.id],
    queryFn:  () => collabApi.listMessages(conv.id, { limit: 50 }),
    enabled:  !!conv?.id,
    refetchInterval: 5_000, // fallback polling alongside websocket
  })

  // Parse @mentions from raw text → { mention_user_ids, is_everyone }
  const parseMentions = (text) => {
    const ids = []
    let everyone = false
    const re = /@([\w.\-]+|\[[^\]]+\])/g
    let m
    while ((m = re.exec(text)) !== null) {
      let token = m[1]
      if (token.startsWith('[') && token.endsWith(']')) token = token.slice(1, -1)
      if (['everyone', 'channel', 'here'].includes(token.toLowerCase())) {
        everyone = true
        continue
      }
      // Format: @[name|id]
      const parts = token.split('|')
      if (parts.length === 2) ids.push(parts[1])
    }
    return { mention_user_ids: ids, is_everyone: everyone }
  }

  const send = useMutation({
    mutationFn: (body) => {
      const mentions = parseMentions(body)
      return collabApi.sendMessage({
        conversation_id: conv.id,
        body,
        parent_message_id: activeThreadRoot,
        ...mentions,
      })
    },
    onSuccess: () => {
      qc.invalidateQueries(['collab-messages', conv.id])
      qc.invalidateQueries(['collab-conversations'])
    },
    onError: (e) => toast.error(e?.response?.data?.detail || 'Error al enviar'),
  })

  const editMsg = useMutation({
    mutationFn: ({ id, body }) => collabApi.editMessage(id, { body }),
    onSuccess: () => qc.invalidateQueries(['collab-messages', conv?.id]),
    onError: (e) => toast.error(e?.response?.data?.detail || 'Error al editar'),
  })

  const delMsg = useMutation({
    mutationFn: (id) => collabApi.deleteMessage(id),
    onSuccess: () => qc.invalidateQueries(['collab-messages', conv?.id]),
  })

  const react = useMutation({
    mutationFn: ({ id, emoji }) => collabApi.toggleReaction(id, emoji),
    onSuccess: () => qc.invalidateQueries(['collab-messages', conv?.id]),
  })

  // Mark read on open
  useEffect(() => {
    if (conv?.id && messages.length > 0) {
      const last = messages[messages.length - 1]
      collabApi.markRead(conv.id, last.id).catch(() => {})
    }
    // We intentionally trigger only when the conversation or message count changes,
    // not for in-place updates to the messages array.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [conv?.id, messages.length])

  // Scroll to bottom on new messages
  useEffect(() => {
    if (messagesEndRef.current) messagesEndRef.current.scrollIntoView({ behavior: 'smooth' })
  }, [messages.length, conv?.id])

  // Slash menu detection
  useEffect(() => {
    setShowSlashMenu(draft.startsWith('/') && !draft.includes(' '))
  }, [draft, setShowSlashMenu])

  // Mention detection — busca el último @ sin cerrar
  useEffect(() => {
    if (!conv) return
    const m = draft.match(/(^|[\s])@([\w.\-]{0,40})$/)
    if (!m) {
      setMentionState(null)
      return
    }
    const q = m[2]
    let cancelled = false
    collabApi.mentionSuggestions({ q, conversation_id: conv.id })
      .then((data) => {
        if (cancelled) return
        const items = [...(data.users || []), ...(data.groups || [])]
        setMentionState({ query: q, items })
      })
      .catch(() => setMentionState(null))
    return () => { cancelled = true }
  }, [draft, conv])

  // Typing emit (debounced)
  useEffect(() => {
    if (!conv?.id || !wsRef?.current) return
    if (wsRef.current.readyState !== WebSocket.OPEN) return
    if (!draft.trim()) return
    try {
      wsRef.current.send(JSON.stringify({ type: 'typing', conversation_id: conv.id, active: true }))
    } catch { /* noop */ }
    const t = setTimeout(() => {
      try { wsRef.current?.send(JSON.stringify({ type: 'typing', conversation_id: conv.id, active: false })) }
      catch { /* noop */ }
    }, 4000)
    return () => clearTimeout(t)
  }, [draft, conv?.id, wsRef])

  // Listen to typing events from bus (delegated through window CustomEvent)
  useEffect(() => {
    const handler = (e) => {
      const { conversation_id, payload } = e.detail || {}
      if (conversation_id !== conv?.id) return
      const uid = payload?.user_id
      const active = !!payload?.active
      if (!uid || uid === currentUser?.id) return
      setTypingUsers(prev => {
        const next = { ...prev }
        if (active) next[uid] = Date.now()
        else delete next[uid]
        return next
      })
    }
    window.addEventListener('collab:typing', handler)
    return () => window.removeEventListener('collab:typing', handler)
  }, [conv?.id, currentUser?.id])

  // Garbage-collect typing entries older than 6s
  useEffect(() => {
    const id = setInterval(() => {
      setTypingUsers(prev => {
        const cutoff = Date.now() - 6000
        const next = {}
        for (const [k, v] of Object.entries(prev)) if (v > cutoff) next[k] = v
        return next
      })
    }, 2000)
    return () => clearInterval(id)
  }, [])

  const insertMention = (item) => {
    const insert = item.is_group ? `@${item.username} ` : `@[${item.full_name}|${item.id}] `
    const replaced = draft.replace(/(^|[\s])@([\w.\-]{0,40})$/, (_m, p1) => `${p1}${insert}`)
    setDraft(replaced)
    setMentionState(null)
    composerRef.current?.focus()
  }

  if (!conv) {
    return (
      <div style={{
        flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center',
        color: 'var(--text-3)', flexDirection: 'column', gap: 14,
      }}>
        <MessageSquare size={48} />
        <div style={{ fontSize: 'var(--text-md)', fontWeight: 600 }}>Selecciona una conversación</div>
      </div>
    )
  }

  const handleSend = async () => {
    if (!draft.trim()) return
    if (editing) {
      await editMsg.mutateAsync({ id: editing.id, body: draft })
      setEditing(null)
    } else {
      await send.mutateAsync(draft)
    }
    setDraft('')
  }

  const handleFile = async (file) => {
    if (!file) return
    const fd = new FormData()
    fd.append('conversation_id', conv.id)
    fd.append('file', file)
    try {
      await collabApi.uploadAttachment(fd)
      qc.invalidateQueries(['collab-messages', conv.id])
      toast.success('Archivo subido')
    } catch (e) {
      toast.error(e?.response?.data?.detail || 'Error al subir')
    }
  }

  const onCallStart = async (kind) => {
    try {
      const c = await collabApi.startCall({ conversation_id: conv.id, kind })
      window.open(`/chat/call/${c.call_id}?token=${encodeURIComponent(c.livekit_token)}&room=${encodeURIComponent(c.livekit_room)}&url=${encodeURIComponent(c.livekit_url)}&kind=${kind}`, '_blank', 'width=1100,height=720')
    } catch {
      toast.error('Error iniciando llamada')
    }
  }

  return (
    <div style={{ flex: 1, display: 'flex', flexDirection: 'column', minWidth: 0 }}>
      {/* Header */}
      <div style={{
        height: 56, padding: '0 18px', flexShrink: 0,
        display: 'flex', alignItems: 'center', justifyContent: 'space-between',
        borderBottom: '1px solid var(--surface-4)', background: 'var(--surface-1)',
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, minWidth: 0 }}>
          {conv.kind === 'channel' && <Hash size={18} />}
          {conv.kind === 'direct' && <MessageSquare size={18} />}
          {conv.kind === 'group' && <Users size={18} />}
          <div style={{ minWidth: 0 }}>
            <div style={{ fontSize: 'var(--text-md)', fontWeight: 700, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{conv.title}</div>
            {conv.channel_type && <div style={{ fontSize: 'var(--text-xs)', color: 'var(--text-3)' }}>Canal {conv.channel_type}</div>}
          </div>
        </div>
        <div style={{ display: 'flex', gap: 8 }}>
          <IconBtn onClick={() => onCallStart('audio')} title="Llamada de voz"><Phone size={15} /></IconBtn>
          <IconBtn onClick={() => onCallStart('video')} title="Videollamada"><Video size={15} /></IconBtn>
          <IconBtn title="Información"><MoreVertical size={15} /></IconBtn>
        </div>
      </div>

      {/* Messages */}
      <div style={{ flex: 1, overflowY: 'auto', padding: '14px 18px', background: 'var(--surface-0)' }}>
        {isLoading && <Loader />}
        {messages.map((m, i) => {
          const prev = messages[i - 1]
          const compact = prev && prev.user_id === m.user_id && (new Date(m.sent_at) - new Date(prev.sent_at)) < 5 * 60_000
          return (
            <MessageBubble key={m.id} msg={m} compact={compact}
              isMine={m.user_id === currentUser?.id}
              onReact={(emoji) => react.mutate({ id: m.id, emoji })}
              onEdit={() => { setEditing({ id: m.id, body: m.body || '' }); setDraft(m.body || ''); composerRef.current?.focus() }}
              onDelete={() => { if (confirm('¿Borrar mensaje?')) delMsg.mutate(m.id) }}
              onPin={() => collabApi.pinMessage(conv.id, m.id).then(() => qc.invalidateQueries(['collab-messages', conv.id]))}
              onSave={() => collabApi.saveMessage(m.id).then(() => toast.success('Guardado'))}
              onReplyThread={() => setActiveThreadRoot(m.id)}
              onLink={(kind) => setLinkPicker({ messageId: m.id, kind })}
            />
          )
        })}
        <div ref={messagesEndRef} />
      </div>

      {/* Typing indicator */}
      {Object.keys(typingUsers).length > 0 && (
        <div style={{ padding: '0 22px', height: 22, fontSize: 'var(--text-xs)', color: 'var(--text-3)', fontStyle: 'italic' }}>
          {Object.keys(typingUsers).length === 1 ? 'Alguien está escribiendo…' : `${Object.keys(typingUsers).length} personas están escribiendo…`}
        </div>
      )}

      {/* Composer */}
      <div style={{
        padding: '10px 18px 14px',
        borderTop: '1px solid var(--surface-4)', background: 'var(--surface-1)',
        position: 'relative',
      }}>
        {showSlashMenu && (
          <SlashMenu draft={draft} onPick={(cmd) => setDraft(`/${cmd} `)} />
        )}
        {mentionState && mentionState.items?.length > 0 && (
          <MentionMenu items={mentionState.items} onPick={insertMention} />
        )}
        {activeThreadRoot && (
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '6px 10px', marginBottom: 6, background: 'var(--accent-muted)', borderRadius: 6, fontSize: 'var(--text-xs)' }}>
            <MessageSquare size={12} /> Respondiendo en hilo
            <button onClick={() => setActiveThreadRoot(null)} style={{ marginLeft: 'auto', background: 'none', border: 'none', cursor: 'pointer', color: 'var(--text-2)' }}>
              <X size={12} />
            </button>
          </div>
        )}
        {editing && (
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '6px 10px', marginBottom: 6, background: 'var(--accent-muted)', borderRadius: 6, fontSize: 'var(--text-xs)' }}>
            <Pencil size={12} /> Editando mensaje
            <button onClick={() => { setEditing(null); setDraft('') }} style={{ marginLeft: 'auto', background: 'none', border: 'none', cursor: 'pointer', color: 'var(--text-2)' }}>
              <X size={12} />
            </button>
          </div>
        )}
        <div style={{
          display: 'flex', alignItems: 'flex-end', gap: 8,
          background: 'var(--surface-3)', border: '1px solid var(--surface-4)',
          borderRadius: 12, padding: '8px 10px',
        }}>
          <IconBtn onClick={() => fileRef.current?.click()} title="Adjuntar"><Paperclip size={16} /></IconBtn>
          <input ref={fileRef} type="file" hidden onChange={e => handleFile(e.target.files?.[0])} />
          <textarea
            ref={composerRef}
            data-chat-composer
            value={draft}
            onChange={e => setDraft(e.target.value)}
            onKeyDown={e => {
              if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault()
                handleSend()
              }
            }}
            placeholder={`Escribe un mensaje en ${conv.title}…  ( / comandos · @ menciones )`}
            rows={1}
            style={{
              flex: 1, minWidth: 0, resize: 'none',
              background: 'transparent', border: 'none', outline: 'none',
              color: 'var(--text-1)', fontSize: 'var(--text-base)',
              fontFamily: 'inherit', maxHeight: 200,
            }}
          />
          <IconBtn onClick={() => setDraft(d => d + '@')} title="Mencionar"><AtSign size={16} /></IconBtn>
          <IconBtn onClick={handleSend} title="Enviar"
            style={{ background: 'var(--accent)', color: '#fff' }}>
            <Send size={16} />
          </IconBtn>
        </div>
      </div>

      {/* Thread side panel */}
      {activeThreadRoot && (
        <ThreadPanel
          conv={conv}
          rootId={activeThreadRoot}
          onClose={() => setActiveThreadRoot(null)}
        />
      )}

      {/* Link picker modal */}
      {linkPicker && (
        <LinkPickerModal
          messageId={linkPicker.messageId}
          kind={linkPicker.kind}
          onClose={() => setLinkPicker(null)}
          onPicked={() => {
            setLinkPicker(null)
            qc.invalidateQueries(['collab-messages', conv.id])
            toast.success('Anclado')
          }}
        />
      )}
    </div>
  )
}

function IconBtn({ children, onClick, title, style = {} }) {
  return (
    <button onClick={onClick} title={title} style={{
      width: 32, height: 32,
      display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
      background: 'transparent', border: '1px solid transparent', borderRadius: 6,
      color: 'var(--text-2)', cursor: 'pointer', flexShrink: 0,
      ...style,
    }}
      onMouseEnter={e => { if (!style.background) e.currentTarget.style.background = 'var(--surface-4)' }}
      onMouseLeave={e => { if (!style.background) e.currentTarget.style.background = 'transparent' }}
    >{children}</button>
  )
}

// ── Message bubble with hover actions ────────────────────────────────────────
function MessageBubble({ msg, compact, isMine, onReact, onEdit, onDelete, onPin, onSave, onReplyThread, onLink }) {
  const [showActions, setShowActions] = useState(false)
  const author = msg.author_name || (msg.bot_id ? 'Bot' : 'Usuario')

  return (
    <div
      role="article"
      aria-label={`Mensaje de ${author}`}
      onMouseEnter={() => setShowActions(true)}
      onMouseLeave={() => setShowActions(false)}
      onFocus={() => setShowActions(true)}
      onBlur={() => setShowActions(false)}
      style={{
        display: 'flex', gap: 12,
        marginTop: compact ? 2 : 12,
        position: 'relative',
        opacity: msg.status === 'deleted' ? 0.55 : 1,
      }}
    >
      {!compact ? (
        <div style={{
          width: 36, height: 36, borderRadius: '50%', flexShrink: 0,
          background: msg.bot_id
            ? 'linear-gradient(135deg, #7c3aed, #4f8ef7)'
            : 'linear-gradient(135deg, var(--accent), var(--purple, #7c3aed))',
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          fontSize: 'var(--text-sm)', fontWeight: 800, color: '#fff',
        }}>
          {msg.bot_id ? <Bot size={16} /> : (author?.charAt(0)?.toUpperCase() || '?')}
        </div>
      ) : (
        <div style={{ width: 36, flexShrink: 0 }} />
      )}
      <div style={{ flex: 1, minWidth: 0 }}>
        {!compact && (
          <div style={{ display: 'flex', alignItems: 'baseline', gap: 8, marginBottom: 2 }}>
            <span style={{ fontSize: 'var(--text-sm)', fontWeight: 700 }}>{author}</span>
            {msg.bot_id && <span style={{ fontSize: 'var(--text-xs)', padding: '1px 6px', background: 'var(--accent-muted)', color: 'var(--accent)', borderRadius: 4, fontWeight: 700 }}>BOT</span>}
            <span style={{ fontSize: 'var(--text-xs)', color: 'var(--text-3)' }}>
              {new Date(msg.sent_at).toLocaleTimeString('es-ES', { hour: '2-digit', minute: '2-digit' })}
            </span>
            {msg.is_pinned && <Pin size={11} style={{ color: 'var(--warning)' }} />}
            {msg.edited_at && <span style={{ fontSize: 'var(--text-xs)', color: 'var(--text-3)' }}>(editado)</span>}
          </div>
        )}
        <div style={{
          fontSize: 'var(--text-sm)', whiteSpace: 'pre-wrap', wordBreak: 'break-word',
          color: msg.status === 'deleted' ? 'var(--text-3)' : 'var(--text-1)',
          fontStyle: msg.status === 'deleted' ? 'italic' : 'normal',
        }}>
          {msg.body}
        </div>
        {msg.metadata_json?.card && <BotCard meta={msg.metadata_json} />}
        {(msg.linked_task_id || msg.linked_ticket_id || msg.linked_deliverable_id || msg.linked_risk_id) && (
          <LinkedEntityChips msg={msg} />
        )}
        {msg.attachments?.length > 0 && (
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, marginTop: 6 }}>
            {msg.attachments.map(a => (
              <div key={a.id} style={{
                display: 'flex', alignItems: 'center', gap: 8,
                padding: '6px 10px', background: 'var(--surface-3)',
                border: '1px solid var(--surface-4)', borderRadius: 8,
                fontSize: 'var(--text-xs)',
              }}>
                <FileText size={13} />
                <span>{a.name}</span>
                <span style={{ color: a.is_quarantined ? 'var(--danger)' : 'var(--text-3)' }}>
                  {a.is_quarantined ? '⚠ cuarentena' : `${Math.round(a.size_bytes / 1024)} KB`}
                </span>
              </div>
            ))}
          </div>
        )}
        {msg.reactions?.length > 0 && (
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4, marginTop: 4 }}>
            {Object.entries(groupReactions(msg.reactions)).map(([emoji, users]) => (
              <button key={emoji} onClick={() => onReact(emoji)} style={{
                display: 'inline-flex', alignItems: 'center', gap: 4,
                padding: '2px 8px', borderRadius: 999,
                background: 'var(--surface-3)', border: '1px solid var(--surface-4)',
                fontSize: 'var(--text-xs)', cursor: 'pointer', fontFamily: 'inherit',
              }}>{emoji} <span>{users.length}</span></button>
            ))}
          </div>
        )}
      </div>

      {showActions && msg.status !== 'deleted' && (
        <div style={{
          position: 'absolute', top: 0, right: 8,
          display: 'flex', gap: 2,
          background: 'var(--surface-2)', border: '1px solid var(--surface-4)',
          borderRadius: 6, padding: 2, boxShadow: '0 2px 8px rgba(0,0,0,0.3)',
        }}>
          {['👍', '❤️', '😂', '🎉'].map(e => (
            <button key={e} onClick={() => onReact(e)} style={{ background: 'none', border: 'none', cursor: 'pointer', padding: 4, fontSize: 14 }}>{e}</button>
          ))}
          <IconBtn onClick={onReplyThread} title="Responder en hilo"><MessageSquare size={13} /></IconBtn>
          <IconBtn onClick={onPin} title="Anclar"><Pin size={13} /></IconBtn>
          <IconBtn onClick={onSave} title="Guardar"><Bookmark size={13} /></IconBtn>
          <IconBtn onClick={() => onLink && onLink('task')} title="Anclar a tarea"><ListChecks size={13} /></IconBtn>
          <IconBtn onClick={() => onLink && onLink('ticket')} title="Anclar a ticket"><Headphones size={13} /></IconBtn>
          {isMine && <IconBtn onClick={onEdit} title="Editar"><Pencil size={13} /></IconBtn>}
          {isMine && <IconBtn onClick={onDelete} title="Borrar" style={{ color: 'var(--danger)' }}><Trash2 size={13} /></IconBtn>}
        </div>
      )}
    </div>
  )
}

function groupReactions(rs) {
  const out = {}
  for (const r of rs) {
    out[r.emoji] = out[r.emoji] || []
    out[r.emoji].push(r.user_id || r.client_user_id)
  }
  return out
}

// ── Bot card renderers ───────────────────────────────────────────────────────
function BotCard({ meta }) {
  if (!meta?.card) return null
  if (meta.card === 'task') return <Card icon={ListChecks} accent="var(--success)" title="Tarea creada" body={`#${meta.task_id?.slice(0, 8) || ''}`} />
  if (meta.card === 'ticket' || meta.card === 'escalation') return <Card icon={Headphones} accent="var(--warning)" title="Ticket de soporte" body={`Nº ${meta.ticket?.number || meta.ticket?.id?.slice(0, 8)} → ${meta.ticket?.assignee || ''}`} />
  if (meta.card === 'imputation') return <Card icon={Zap} accent="var(--accent)" title={`${meta.hours}h imputadas`} body={`Proyecto ${meta.project_id?.slice(0, 8) || '?'}`} />
  if (meta.card === 'risk') return <Card icon={AlertCircle} accent="var(--danger)" title="Riesgo registrado" body={meta.title} />
  if (meta.card === 'decision') return <Card icon={FileSignature} accent="var(--purple, #7c3aed)" title="Decisión registrada" body={meta.text} />
  if (meta.card === 'poll') return <PollCard meta={meta} />
  if (meta.card === 'call') return <Card icon={Video} accent="var(--accent)" title="Llamada iniciada" body={`Sala ${meta.room?.slice(-8) || ''}`} />
  if (meta.card === 'call_summary') return <Card icon={Sparkles} accent="var(--accent)" title="Resumen de reunión" body={`${meta.actions?.length || 0} acciones detectadas`} />
  if (meta.card === 'answer') return <Card icon={Sparkles} accent="var(--accent)" title="Nexus IA" body={meta.source} />
  if (meta.card === 'webhook') return <Card icon={Megaphone} accent="var(--purple)" title={meta.source || 'Webhook entrante'} body="" />
  return null
}

function Card({ icon: Icon, accent, title, body }) {
  return (
    <div style={{
      display: 'flex', alignItems: 'center', gap: 10,
      marginTop: 6, padding: '10px 12px',
      background: `${accent}10`, border: `1px solid ${accent}40`, borderRadius: 8,
      maxWidth: 480,
    }}>
      <div style={{
        width: 28, height: 28, borderRadius: 6, flexShrink: 0,
        background: `${accent}25`, color: accent,
        display: 'flex', alignItems: 'center', justifyContent: 'center',
      }}><Icon size={15} /></div>
      <div style={{ minWidth: 0 }}>
        <div style={{ fontSize: 'var(--text-xs)', fontWeight: 700, color: accent, textTransform: 'uppercase', letterSpacing: '0.06em' }}>{title}</div>
        {body && <div style={{ fontSize: 'var(--text-sm)', color: 'var(--text-2)' }}>{body}</div>}
      </div>
    </div>
  )
}

function PollCard({ meta }) {
  return (
    <div style={{ marginTop: 6, padding: '12px 14px', background: 'var(--surface-3)', border: '1px solid var(--surface-4)', borderRadius: 8, maxWidth: 460 }}>
      <div style={{ fontSize: 'var(--text-sm)', fontWeight: 700, marginBottom: 8 }}>📊 {meta.question}</div>
      {(meta.options || []).map((o, i) => (
        <button key={i} style={{
          display: 'block', width: '100%', textAlign: 'left',
          padding: '6px 10px', marginBottom: 4,
          background: 'var(--surface-2)', border: '1px solid var(--surface-4)', borderRadius: 6,
          fontFamily: 'inherit', cursor: 'pointer',
          fontSize: 'var(--text-sm)', color: 'var(--text-1)',
        }}>{o.label} <span style={{ color: 'var(--text-3)', fontSize: 'var(--text-xs)' }}>({o.votes || 0})</span></button>
      ))}
    </div>
  )
}

// ── Search modal (Cmd+K) ───────────────────────────────────────────────────
function SearchModal({ onClose, onJump }) {
  const [q, setQ] = useState('')
  const { data: result, isFetching } = useQuery({
    queryKey: ['collab-search', q],
    queryFn: () => collabApi.search({ q, limit: 30 }),
    enabled: q.trim().length >= 2,
  })
  const hits = result?.hits || []
  return (
    <div role="presentation" onClick={onClose} style={{
      position: 'fixed', inset: 0, background: 'rgba(8,12,20,0.78)', backdropFilter: 'blur(4px)',
      display: 'flex', alignItems: 'flex-start', justifyContent: 'center', padding: '8vh 16px', zIndex: 1000,
    }}>
      <div role="dialog" onClick={(e) => e.stopPropagation()} style={{
        background: 'var(--surface-2)', border: '1px solid var(--surface-4)',
        borderRadius: 14, width: 640, maxWidth: '94%', overflow: 'hidden',
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '14px 18px', borderBottom: '1px solid var(--surface-4)' }}>
          <Search size={16} style={{ color: 'var(--text-3)' }} />
          <input value={q} onChange={(e) => setQ(e.target.value)} autoFocus
            placeholder="Buscar mensajes…  (operadores: from:, in:, before:, has:link, is:pinned …)"
            style={{
              flex: 1, background: 'transparent', border: 'none', outline: 'none',
              color: 'var(--text-1)', fontSize: 'var(--text-md)', fontFamily: 'inherit',
            }} />
          <kbd style={{
            fontSize: 'var(--text-xs)', color: 'var(--text-3)',
            border: '1px solid var(--surface-4)', padding: '2px 6px', borderRadius: 4,
          }}>Esc</kbd>
        </div>
        <div style={{ maxHeight: '54vh', overflowY: 'auto' }}>
          {q.trim().length < 2 && (
            <div style={{ padding: 24, fontSize: 'var(--text-sm)', color: 'var(--text-3)' }}>
              Escribe al menos 2 caracteres. Soporta operadores: <code>from:juan</code> · <code>in:#general</code> · <code>before:2026-05-01</code> · <code>has:link</code> · <code>is:pinned</code> · <code>type:bot</code>
            </div>
          )}
          {isFetching && <div style={{ padding: 18, fontSize: 'var(--text-sm)', color: 'var(--text-3)' }}>Buscando…</div>}
          {!isFetching && q.trim().length >= 2 && hits.length === 0 && (
            <div style={{ padding: 18, fontSize: 'var(--text-sm)', color: 'var(--text-3)' }}>Sin resultados</div>
          )}
          {hits.map((h) => (
            <button key={h.id} onClick={() => onJump(h.conversation_id)} style={{
              display: 'block', width: '100%', textAlign: 'left',
              padding: '10px 18px',
              background: 'transparent', border: 'none', cursor: 'pointer',
              fontFamily: 'inherit', borderBottom: '1px solid var(--surface-4)',
            }}
              onMouseEnter={(e) => e.currentTarget.style.background = 'var(--surface-3)'}
              onMouseLeave={(e) => e.currentTarget.style.background = 'transparent'}>
              <div style={{ fontSize: 'var(--text-sm)', color: 'var(--text-1)', marginBottom: 4 }}>{h.snippet}</div>
              <div style={{ fontSize: 'var(--text-xs)', color: 'var(--text-3)' }}>
                {h.sent_at ? new Date(h.sent_at).toLocaleString('es-ES') : ''}
              </div>
            </button>
          ))}
        </div>
      </div>
    </div>
  )
}

// ── Linked entity chips ────────────────────────────────────────────────────
function LinkedEntityChips({ msg }) {
  const chips = []
  if (msg.linked_task_id) chips.push({ icon: ListChecks, label: 'Tarea', href: `/tasks?id=${msg.linked_task_id}`, color: 'var(--success)' })
  if (msg.linked_ticket_id) chips.push({ icon: Headphones, label: 'Ticket', href: `/service-desk?id=${msg.linked_ticket_id}`, color: 'var(--warning)' })
  if (msg.linked_deliverable_id) chips.push({ icon: FileText, label: 'Entregable', href: `/deliverables?id=${msg.linked_deliverable_id}`, color: 'var(--accent)' })
  if (msg.linked_risk_id) chips.push({ icon: AlertCircle, label: 'Riesgo', href: `/risks?id=${msg.linked_risk_id}`, color: 'var(--danger)' })
  if (!chips.length) return null
  return (
    <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, marginTop: 6 }}>
      {chips.map((c, i) => (
        <a key={i} href={c.href} target="_blank" rel="noopener noreferrer"
          style={{
            display: 'inline-flex', alignItems: 'center', gap: 6,
            padding: '4px 10px', borderRadius: 999,
            background: `${c.color}15`, border: `1px solid ${c.color}40`,
            color: c.color, fontSize: 'var(--text-xs)', fontWeight: 700,
            textDecoration: 'none',
          }}>
          <c.icon size={11} /> {c.label}
        </a>
      ))}
    </div>
  )
}

// ── Link picker modal ──────────────────────────────────────────────────────
function LinkPickerModal({ messageId, kind, onClose, onPicked }) {
  const [q, setQ] = useState('')
  const { data: items = [] } = useQuery({
    queryKey: ['link-candidates', messageId, kind, q],
    queryFn: () => collabApi.linkCandidates(messageId, { kind, q }),
  })
  const link = useMutation({
    mutationFn: (id) => collabApi.linkMessage(messageId, { kind, id }),
    onSuccess: onPicked,
  })
  return (
    <div role="presentation" onClick={onClose} style={{
      position: 'fixed', inset: 0, background: 'rgba(8,12,20,0.78)', backdropFilter: 'blur(4px)',
      display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 1000,
    }}>
      <div role="dialog" onClick={(e) => e.stopPropagation()} style={{
        background: 'var(--surface-2)', border: '1px solid var(--surface-4)',
        borderRadius: 12, padding: 18, width: 480, maxWidth: '92%',
      }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
          <div style={{ fontSize: 'var(--text-md)', fontWeight: 700 }}>
            Anclar a {kind === 'task' ? 'tarea' : kind === 'ticket' ? 'ticket' : kind}
          </div>
          <button onClick={onClose} style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--text-2)' }}>
            <X size={14} />
          </button>
        </div>
        <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Buscar…" autoFocus
          style={{
            width: '100%', boxSizing: 'border-box',
            background: 'var(--surface-3)', border: '1px solid var(--surface-4)',
            borderRadius: 8, padding: '10px 12px',
            color: 'var(--text-1)', fontSize: 'var(--text-sm)', outline: 'none', fontFamily: 'inherit',
          }} />
        <div style={{ marginTop: 10, maxHeight: 320, overflowY: 'auto' }}>
          {items.length === 0 && <div style={{ fontSize: 'var(--text-xs)', color: 'var(--text-3)', padding: 14 }}>Sin resultados</div>}
          {items.map((it) => (
            <button key={it.id} onClick={() => link.mutate(it.id)} style={{
              display: 'block', width: '100%', textAlign: 'left',
              padding: '10px 12px', borderRadius: 6,
              background: 'transparent', border: 'none', cursor: 'pointer',
              fontFamily: 'inherit', fontSize: 'var(--text-sm)', color: 'var(--text-1)',
            }}
              onMouseEnter={(e) => e.currentTarget.style.background = 'var(--surface-3)'}
              onMouseLeave={(e) => e.currentTarget.style.background = 'transparent'}>
              {it.label}
            </button>
          ))}
        </div>
      </div>
    </div>
  )
}

// ── Mention menu ────────────────────────────────────────────────────────────
function MentionMenu({ items, onPick }) {
  return (
    <div style={{
      position: 'absolute', bottom: '100%', left: 18, right: 18,
      marginBottom: 6, padding: 6,
      background: 'var(--surface-1)', border: '1px solid var(--surface-4)',
      borderRadius: 10, boxShadow: '0 -4px 18px rgba(0,0,0,0.3)',
      maxHeight: 280, overflowY: 'auto',
    }}>
      {items.map((it, i) => (
        <button key={i} onClick={() => onPick(it)} style={{
          display: 'flex', alignItems: 'center', gap: 10,
          width: '100%', padding: '8px 10px', borderRadius: 6,
          background: 'transparent', border: 'none', cursor: 'pointer',
          fontFamily: 'inherit', textAlign: 'left',
        }}
          onMouseEnter={e => e.currentTarget.style.background = 'var(--surface-3)'}
          onMouseLeave={e => e.currentTarget.style.background = 'transparent'}>
          <span style={{
            width: 26, height: 26, borderRadius: '50%', display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
            background: 'linear-gradient(135deg, var(--accent), var(--purple, #7c3aed))',
            color: '#fff', fontSize: 11, fontWeight: 800,
          }}>{(it.full_name || it.username || '?').charAt(0).toUpperCase()}</span>
          <div style={{ flex: 1, minWidth: 0 }}>
            <div style={{ fontSize: 'var(--text-sm)', fontWeight: 700, color: 'var(--text-1)' }}>
              {it.full_name}{it.is_group ? '' : ` (@${it.username || ''})`}
            </div>
            {it.email && <div style={{ fontSize: 'var(--text-xs)', color: 'var(--text-3)' }}>{it.email}</div>}
          </div>
        </button>
      ))}
    </div>
  )
}

// ── Thread side panel ──────────────────────────────────────────────────────
function ThreadPanel({ conv, rootId, onClose }) {
  const qc = useQueryClient()
  const [reply, setReply] = useState('')
  const { data: thread = [] } = useQuery({
    queryKey: ['collab-thread', conv?.id, rootId],
    queryFn: () => collabApi.listMessages(conv.id, { thread_root: rootId, limit: 200 }),
    enabled: !!conv?.id && !!rootId,
    refetchInterval: 5000,
  })
  const send = useMutation({
    mutationFn: () => collabApi.sendMessage({ conversation_id: conv.id, parent_message_id: rootId, body: reply }),
    onSuccess: () => {
      qc.invalidateQueries(['collab-thread', conv.id, rootId])
      qc.invalidateQueries(['collab-messages', conv.id])
      setReply('')
    },
  })
  return (
    <div style={{
      position: 'fixed', top: 56, right: 0, bottom: 0, width: 380,
      background: 'var(--surface-1)', borderLeft: '1px solid var(--surface-4)',
      display: 'flex', flexDirection: 'column', zIndex: 50,
    }}>
      <div style={{ height: 48, padding: '0 16px', display: 'flex', alignItems: 'center', justifyContent: 'space-between', borderBottom: '1px solid var(--surface-4)' }}>
        <div style={{ fontWeight: 700, fontSize: 'var(--text-sm)' }}>Hilo · {thread.length} respuesta{thread.length === 1 ? '' : 's'}</div>
        <button onClick={onClose} style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--text-2)' }}><X size={14} /></button>
      </div>
      <div style={{ flex: 1, overflowY: 'auto', padding: '12px 16px' }}>
        {thread.length === 0 && <div style={{ fontSize: 'var(--text-xs)', color: 'var(--text-3)' }}>Sin respuestas todavía.</div>}
        {thread.map(m => (
          <div key={m.id} style={{ marginBottom: 14 }}>
            <div style={{ fontSize: 'var(--text-xs)', color: 'var(--text-3)' }}>{m.author_name || 'Usuario'} · {new Date(m.sent_at).toLocaleTimeString('es-ES', { hour: '2-digit', minute: '2-digit' })}</div>
            <div style={{ fontSize: 'var(--text-sm)', whiteSpace: 'pre-wrap', color: 'var(--text-1)' }}>{m.body}</div>
          </div>
        ))}
      </div>
      <div style={{ padding: 10, borderTop: '1px solid var(--surface-4)', display: 'flex', gap: 6 }}>
        <input value={reply} onChange={e => setReply(e.target.value)}
          onKeyDown={e => e.key === 'Enter' && reply.trim() && send.mutate()}
          placeholder="Responder en hilo…"
          style={{
            flex: 1, padding: '8px 10px',
            background: 'var(--surface-3)', border: '1px solid var(--surface-4)', borderRadius: 8,
            color: 'var(--text-1)', fontSize: 'var(--text-sm)', outline: 'none', fontFamily: 'inherit',
          }} />
        <IconBtn onClick={() => reply.trim() && send.mutate()} style={{ background: 'var(--accent)', color: '#fff' }}><Send size={14} /></IconBtn>
      </div>
    </div>
  )
}

// ── Slash menu ──────────────────────────────────────────────────────────────
function SlashMenu({ draft, onPick }) {
  const { data: help = { commands: [] } } = useQuery({
    queryKey: ['collab-slash-help'],
    queryFn:  () => collabApi.slashHelp(),
    staleTime: 60 * 60_000,
  })
  const term = draft.replace('/', '').toLowerCase()
  const cmds = help.commands.filter(c => c.name.replace('/', '').toLowerCase().startsWith(term))
  if (!cmds.length) return null
  return (
    <div style={{
      position: 'absolute', bottom: '100%', left: 18, right: 18,
      marginBottom: 6, padding: 6,
      background: 'var(--surface-1)', border: '1px solid var(--surface-4)',
      borderRadius: 10, boxShadow: '0 -4px 18px rgba(0,0,0,0.3)',
      maxHeight: 280, overflowY: 'auto',
    }}>
      {cmds.map((c, i) => (
        <button key={i} onClick={() => onPick(c.name.replace('/', ''))} style={{
          display: 'flex', alignItems: 'center', gap: 10,
          width: '100%', padding: '8px 10px', borderRadius: 6,
          background: 'transparent', border: 'none', cursor: 'pointer',
          fontFamily: 'inherit', textAlign: 'left',
        }}
          onMouseEnter={e => e.currentTarget.style.background = 'var(--surface-3)'}
          onMouseLeave={e => e.currentTarget.style.background = 'transparent'}
        >
          <span style={{ fontFamily: 'var(--font-mono)', fontWeight: 800, color: 'var(--accent)' }}>{c.name}</span>
          <span style={{ fontSize: 'var(--text-xs)', color: 'var(--text-3)' }}>{c.desc}</span>
        </button>
      ))}
    </div>
  )
}

// ── Right context panel ─────────────────────────────────────────────────────
function ContextPanel({ conv }) {
  const { data: pins = [] } = useQuery({
    queryKey: ['collab-pins', conv.id],
    queryFn: () => collabApi.listPins(conv.id),
    enabled: !!conv?.id,
  })
  const { data: members = [] } = useQuery({
    queryKey: ['collab-members', conv?.team_id || conv?.id],
    queryFn: async () => {
      if (conv?.kind === 'channel') {
        const all = await collabApi.listChannels()
        const ch = all.find(x => x.conversation_id === conv.id)
        if (ch) return collabApi.listChannelMembers(ch.id)
      }
      return []
    },
    enabled: !!conv?.id,
  })
  const { data: calls = [] } = useQuery({
    queryKey: ['collab-calls', conv.id],
    queryFn: () => collabApi.listCalls(conv.id),
    enabled: !!conv?.id,
  })
  const { data: calendar } = useQuery({
    queryKey: ['collab-calendar'],
    queryFn: () => collabApi.calendarEvents(7),
    refetchInterval: 5 * 60_000,
  })
  const { data: decisions = [] } = useQuery({
    queryKey: ['collab-decisions-context'],
    queryFn: () => collabApi.listDecisions(5),
  })

  return (
    <div style={{
      width: 280, flexShrink: 0,
      background: 'var(--surface-1)',
      borderLeft: '1px solid var(--surface-4)',
      overflowY: 'auto', padding: '14px 14px 24px',
    }}>
      <Section title="Información">
        <div style={{ fontSize: 'var(--text-sm)', color: 'var(--text-2)' }}>{conv.kind === 'channel' ? 'Canal' : conv.kind === 'group' ? 'Grupo' : 'Chat directo'}</div>
      </Section>
      {members.length > 0 && (
        <Section title={`Miembros (${members.length})`}>
          {members.slice(0, 10).map(m => (
            <div key={m.id} style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '4px 0', fontSize: 'var(--text-sm)' }}>
              <div style={{ width: 22, height: 22, borderRadius: '50%', background: 'linear-gradient(135deg, var(--accent), var(--purple))', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 10, color: '#fff', fontWeight: 800 }}>
                {(m.user_name || '?').charAt(0).toUpperCase()}
              </div>
              <span>{m.user_name}</span>
              {m.role !== 'member' && <span style={{ fontSize: 10, color: 'var(--text-3)', marginLeft: 'auto' }}>{m.role}</span>}
            </div>
          ))}
        </Section>
      )}
      <Section title={`Anclados (${pins.length})`}>
        {pins.length === 0 ? <Empty>Ningún mensaje anclado</Empty> : pins.map(p => (
          <div key={p.id} style={{ padding: '6px 0', fontSize: 'var(--text-xs)', color: 'var(--text-2)' }}>
            <Pin size={10} /> {p.preview}
          </div>
        ))}
      </Section>
      <Section title={`Llamadas (${calls.length})`}>
        {calls.length === 0 ? <Empty>Sin llamadas</Empty> : calls.slice(0, 5).map(c => (
          <div key={c.id} style={{ padding: '6px 0', fontSize: 'var(--text-xs)', color: 'var(--text-2)' }}>
            {c.kind === 'video' ? <Video size={11} /> : <Phone size={11} />} {c.duration_seconds}s — {c.status}
            {c.has_summary && <Sparkles size={10} style={{ marginLeft: 4, color: 'var(--warning)' }} />}
          </div>
        ))}
      </Section>
      <Section title="Próximos eventos (7d)">
        {!calendar?.events?.length ? (
          <Empty>{calendar?.providers_connected?.length ? 'Sin eventos próximos' : 'Conecta Google/M365 para ver tu calendario'}</Empty>
        ) : calendar.events.slice(0, 6).map(ev => (
          <a key={ev.id} href={ev.link || '#'} target="_blank" rel="noopener noreferrer"
            style={{ display: 'block', padding: '6px 0', fontSize: 'var(--text-xs)', color: 'var(--text-2)', textDecoration: 'none' }}>
            <div style={{ color: 'var(--text-1)', fontWeight: 600 }}>{ev.title}</div>
            <div style={{ color: 'var(--text-3)' }}>
              {ev.source === 'google' ? '🅖' : '🅜'} {ev.start ? new Date(ev.start).toLocaleString('es-ES', { weekday: 'short', hour: '2-digit', minute: '2-digit' }) : ''}
            </div>
          </a>
        ))}
      </Section>
      <Section title={`Decisiones (${decisions.length})`}>
        {decisions.length === 0 ? <Empty>Sin decisiones registradas</Empty> : decisions.slice(0, 5).map(d => (
          <div key={d.id} style={{ padding: '6px 0', fontSize: 'var(--text-xs)', color: 'var(--text-2)' }}>
            <FileSignature size={10} style={{ marginRight: 4 }} /> {(d.text || '').slice(0, 100)}
          </div>
        ))}
      </Section>
    </div>
  )
}

function Section({ title, children }) {
  return (
    <div style={{ marginBottom: 18 }}>
      <div style={{ fontSize: 'var(--text-2xs, 10px)', fontWeight: 700, color: 'var(--text-3)', textTransform: 'uppercase', letterSpacing: '0.08em', marginBottom: 8 }}>{title}</div>
      {children}
    </div>
  )
}

function Empty({ children }) { return <div style={{ fontSize: 'var(--text-xs)', color: 'var(--text-4)' }}>{children}</div> }

function Loader() {
  return <div style={{ display: 'flex', justifyContent: 'center', padding: 24 }}>
    <div style={{ width: 24, height: 24, borderRadius: '50%', border: '3px solid var(--surface-4)', borderTopColor: 'var(--accent)', animation: 'spin 0.7s linear infinite' }} />
    <style>{`@keyframes spin { to { transform: rotate(360deg) } }`}</style>
  </div>
}

// ── Activity tab ────────────────────────────────────────────────────────────
function ActivityList() {
  const { data: notifs = [] } = useQuery({ queryKey: ['collab-notifications'], queryFn: () => collabApi.listNotifications(false) })
  const { data: mentions = [] } = useQuery({ queryKey: ['collab-mentions'], queryFn: () => collabApi.listMyMentions() })
  const { data: saved = [] } = useQuery({ queryKey: ['collab-saved'], queryFn: () => collabApi.listSaved() })
  return (
    <div style={{ width: 360, background: 'var(--surface-1)', borderRight: '1px solid var(--surface-4)', overflowY: 'auto', padding: 16 }}>
      <Section title={`Notificaciones (${notifs.length})`}>
        {notifs.length === 0 ? <Empty>Sin notificaciones</Empty> : notifs.slice(0, 30).map(n => (
          <div key={n.id} style={{ padding: '8px 10px', borderRadius: 6, background: n.is_read ? 'transparent' : 'var(--accent-muted)', marginBottom: 4 }}>
            <div style={{ fontSize: 'var(--text-sm)', fontWeight: 600 }}>{n.title}</div>
            <div style={{ fontSize: 'var(--text-xs)', color: 'var(--text-3)' }}>{(n.body || '').slice(0, 80)}</div>
          </div>
        ))}
      </Section>
      <Section title={`Menciones (${mentions.length})`}>
        {mentions.length === 0 ? <Empty>Sin menciones</Empty> : mentions.slice(0, 20).map(m => (
          <div key={m.id} style={{ padding: '6px 0', fontSize: 'var(--text-xs)', color: 'var(--text-2)' }}>
            <AtSign size={10} /> {m.preview}
          </div>
        ))}
      </Section>
      <Section title={`Guardados (${saved.length})`}>
        {saved.length === 0 ? <Empty>Sin guardados</Empty> : saved.slice(0, 20).map(s => (
          <div key={s.id} style={{ padding: '6px 0', fontSize: 'var(--text-xs)', color: 'var(--text-2)' }}>
            <Bookmark size={10} /> {s.preview}
          </div>
        ))}
      </Section>
    </div>
  )
}

// ── Admin panel placeholder ─────────────────────────────────────────────────
function AdminPanelEntry() {
  return (
    <div style={{ width: 360, background: 'var(--surface-1)', borderRight: '1px solid var(--surface-4)', padding: 16, color: 'var(--text-2)' }}>
      <Section title="Administración Collaboration">
        <p style={{ fontSize: 'var(--text-sm)', lineHeight: 1.5 }}>
          Configura políticas de retención, legal hold, integraciones y auditoría desde la página dedicada.
        </p>
        <a href="/chat/admin" style={{
          display: 'inline-flex', alignItems: 'center', gap: 6, marginTop: 10,
          padding: '8px 14px', borderRadius: 8,
          background: 'var(--accent)', color: '#fff', fontSize: 'var(--text-sm)',
          fontWeight: 700, textDecoration: 'none',
        }}><Settings size={14} /> Abrir admin</a>
      </Section>
    </div>
  )
}
