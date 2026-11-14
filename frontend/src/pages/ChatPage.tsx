/**
 * ChatPage — Teams-like internal chat for Contecflow PSA.
 * Three-pane layout (sidebar / conversation / context panel) per
 * docs/chat_interno_teams_solucion_final.txt §6.1.
 *
 * Wired to /api/v1/collaboration endpoints + WebSocket realtime.
 */
import type { CSSProperties, ReactNode, Dispatch, SetStateAction, DragEvent as ReactDragEvent, ClipboardEvent as ReactClipboardEvent } from 'react'
import { useEffect, useReducer, useRef, useState, useId } from 'react'
import { useSearchParams } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  Hash, MessageSquare, Users, Pin, Bookmark, Search,
  Send, Paperclip, AtSign, Plus, Phone, Video,
  ChevronDown, ChevronRight, Bell, Sparkles, Megaphone, Zap,
  Bot, FileText, AlertCircle, MoreVertical, Trash2, Pencil, X,
  Headphones, ListChecks, FileSignature, BellOff, Link as LinkIcon,
  UserPlus, LogOut, ChevronLeft,
  type LucideIcon,
} from 'lucide-react'
import { useToast } from '../context/ToastContext'
import { confirmar } from '../context/ConfirmContext'
import { useAuth } from '../context/AuthContext'
import { useChatRealtime } from '../context/ChatRealtimeContext'
import { collabApi } from '../services/collaborationApi'
import { apiUrl, type ApiError } from '../services/api'
import { registerCollabPush } from '../utils/collabPush'
import { useAppLang } from '../i18n/AppLangContext'
import { alpha } from '../constants/theme'
import { localeActivo } from '../utils/helpers'
import useMediaQuery from '../hooks/useMediaQuery'
import { useDialogo } from '../components/ui'
import { POLL_DEFAULT_MS, POLL_FREQUENT_MS, POLL_SLOW_MS, PRESENCE_POLL_MS, STALE_1_HOUR_MS, STALE_5_MIN_MS, STALE_DEFAULT_MS, TYPING_IDLE_MS, TYPING_SWEEP_MS } from '../constants/timings'
import { CHAT_MESSAGES_PAGE_SIZE, CHAT_SEARCH_LIMIT, CHAT_THREAD_MESSAGES_LIMIT, MENTION_SUGGESTIONS_LIMIT, MENTION_SUGGESTIONS_MEMBERS_LIMIT } from '../constants/pagination'

// ── Entity types ────────────────────────────────────────────────────────────
// The collaboration API client returns untyped data (`r.data` / `unknown[]`),
// so each query states the shape it reads. Fields come from the backend
// serializers in app/services/collaboration/** where they exist; the rest are
// what this page reads, optional. Type annotations only — no runtime effect.

/** Conversación (canal, directo o grupo). */
interface Conv { id: string; kind?: string; title?: string | null; peer_user_id?: string | null; channel_type?: string | null }
/** Usuario o grupo (`@menciones`, miembros elegidos, usuario de la sesión). */
interface UserLike { id: string; full_name?: string | null; username?: string | null; email?: string | null; is_group?: boolean }
interface MentionSuggestions { users?: UserLike[]; groups?: UserLike[] }
interface Reaction { emoji: string; user_id: string | null; client_user_id: string | null }
interface Attachment {
  id: string; name: string; mime_type: string | null; size_bytes: number
  av_status?: string | null; dlp_status?: string | null; is_quarantined?: boolean
  // `getAttachment` los añade al pedir el detalle.
  download_url?: string | null; preview_url?: string | null
}
interface PollOption { label: string; votes?: number }
/** `metadata_json` de un mensaje de bot: la tarjeta que pinta y sus datos. */
interface BotMeta {
  card?: string; task_id?: string; ticket?: { number?: string | number | null; id?: string; assignee?: string }
  hours?: number; project_id?: string; title?: string; text?: string; room?: string; actions?: unknown[]
  source?: string; question?: string; options?: PollOption[]
}
/** `_serialize_message` (app/services/collaboration/messages.py). */
interface Msg {
  id: string; conversation_id: string; thread_id: string | null; parent_message_id: string | null
  user_id: string | null; client_user_id: string | null; bot_id: string | null
  author_name: string | null; author_avatar: string | null
  type: string; status: string; body: string | null; body_html: string | null
  metadata_json: BotMeta; has_attachments: boolean; attachments: Attachment[]; reactions: Reaction[]
  is_pinned: boolean; is_redacted: boolean; linked_task_id: string | null; linked_ticket_id: string | null
  // `_serialize_message` los envía desde la auditoría 2026-11 (antes no llegaban nunca).
  linked_deliverable_id?: string | null; linked_risk_id?: string | null
  edited_at: string | null; deleted_at: string | null; sent_at: string
}
interface Team { id: string; name: string }
interface Channel { id: string; team_id: string; name: string; conversation_id: string }
interface Presence { user_id: string; status: string; user_name?: string | null; is_in_call?: boolean }
interface CollabNotification { id: string; is_read: boolean; title: string; body: string | null }
interface ChatBot { id: string; name?: string }
interface Member { id?: string; user_id: string; user_name?: string | null; role?: string | null; is_admin?: boolean }
interface NotificationRule { scope: string; target_id: string | null; notify_messages: string }
interface SearchHit { id: string; conversation_id: string; snippet: string; sent_at: string | null }
interface LinkCandidate { id: string; label: string }
interface SlashCommand { name: string; desc: string }
/** Fila con vista previa: fijados, menciones y guardados. */
interface PreviewRow { id: string; preview: string }
interface CallRow { id: string; kind: string; duration_seconds: number; status: string; has_summary?: boolean }
interface CalendarEvent { id: string; link?: string | null; title: string; source: string; start: string | null }
interface CalendarData { events?: CalendarEvent[]; providers_connected?: string[] }
interface Decision { id: string; text: string | null }
type LinkPicker = { messageId: string; kind: string }
type TypingDetail = { conversation_id?: string; payload?: { user_id?: string; active?: boolean } }

// ── Shared style constants (extracted from repeated inline styles) ──────────
// Keep these read-only objects: never mutate, never assign per-render. They
// reduce duplication without changing visuals.
const styles: Record<string, CSSProperties> = {
  modalOverlay: {
    position: 'fixed', inset: 0, background: 'rgba(8,12,20,0.78)', backdropFilter: 'blur(4px)',
    display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 'var(--z-modal)',
  },
  modalDialog: {
    background: 'var(--surface-2)', border: '1px solid var(--surface-4)',
    borderRadius: 'var(--radius-lg)', width: 540, maxWidth: '94%', overflow: 'hidden',
  },
  iconCloseBtn: {
    background: 'none', border: 'none', cursor: 'pointer', color: 'var(--text-2)',
  },
  formLabel: {
    fontSize: 'var(--text-xs)', fontWeight: 700, color: 'var(--text-2)',
    textTransform: 'uppercase', letterSpacing: '0.07em',
  },
  popoverMenu: {
    position: 'absolute', bottom: '100%', left: 18, right: 18,
    marginBottom: 6, padding: 6,
    background: 'var(--surface-1)', border: '1px solid var(--surface-4)',
    borderRadius: 'var(--radius-md)', boxShadow: '0 -4px 18px rgba(0,0,0,0.3)',
    maxHeight: 280, overflowY: 'auto',
  },
  popoverItem: {
    display: 'flex', alignItems: 'center', gap: 10,
    width: '100%', padding: '8px 10px', borderRadius: 'var(--radius-sm)',
    background: 'transparent', border: 'none', cursor: 'pointer',
    fontFamily: 'inherit', textAlign: 'left',
  },
  avatar22: {
    width: 22, height: 22, borderRadius: '50%',
    background: 'linear-gradient(135deg, var(--accent), var(--purple))',
    color: 'var(--on-accent-light)', display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
    fontSize: 10, fontWeight: 800,
  },
  presenceDot: {
    position: 'absolute', bottom: 0, right: -2, width: 8, height: 8, borderRadius: '50%',
    border: '1.5px solid var(--surface-1)',
  },
  sectionEmptyText: {
    fontSize: 'var(--text-xs)', color: 'var(--text-3)',
  },
  contextRowMutedText: {
    padding: '6px 0', fontSize: 'var(--text-xs)', color: 'var(--text-2)',
  },
  composerHintBar: {
    display: 'flex', alignItems: 'center', gap: 8, padding: '6px 10px', marginBottom: 6,
    background: 'var(--accent-muted)', borderRadius: 'var(--radius-sm)', fontSize: 'var(--text-xs)',
  },
}

// ── Page entry ───────────────────────────────────────────────────────────────
export default function ChatPage(): JSX.Element {
  const _toast = useToast()
  const { user } = useAuth()

  const [activeTab, setActiveTab] = useState('chats') // chats | teams | activity | calls
  const [searchParams, setSearchParams] = useSearchParams()
  const urlConvId = searchParams.get('conv')
  const [showSlashMenu, setShowSlashMenu] = useState(false)
  const [draft, setDraft] = useState('')
  const [searchModalOpen, setSearchModalOpen] = useState(false)
  // En pantalla estrecha se ve una sola columna: la lista o la conversación.
  const narrow = useMediaQuery('(max-width: 900px)')
  const [mobileShowConv, setMobileShowConv] = useState(false)

  // ── Data ───────────────────────────────────────────────────────────────────
  useQuery({
    queryKey: ['collab-workspace'],
    queryFn:  () => collabApi.getWorkspace(),
    staleTime: STALE_DEFAULT_MS,
  })

  const { data: conversations = [], isLoading: loadingConvs } = useQuery({
    queryKey: ['collab-conversations'],
    queryFn:  () => collabApi.listConversations() as Promise<Conv[]>,
    refetchInterval: POLL_FREQUENT_MS,
  })

  const { data: teams = [] } = useQuery({
    queryKey: ['collab-teams'],
    queryFn:  () => collabApi.listTeams() as Promise<Team[]>,
    staleTime: STALE_DEFAULT_MS,
  })

  const { data: channels = [] } = useQuery({
    queryKey: ['collab-channels'],
    queryFn:  () => collabApi.listChannels(undefined) as Promise<Channel[]>,
    staleTime: STALE_DEFAULT_MS,
  })

  const { data: presence = [] } = useQuery({
    queryKey: ['collab-presence'],
    queryFn:  () => collabApi.listPresence() as Promise<Presence[]>,
    refetchInterval: POLL_DEFAULT_MS,
  })

  const { data: notifications = [] } = useQuery({
    queryKey: ['collab-notifications'],
    queryFn:  () => collabApi.listNotifications(false) as Promise<CollabNotification[]>,
    refetchInterval: POLL_FREQUENT_MS,
  })

  const { data: bots = [] } = useQuery({
    queryKey: ['collab-bots'],
    queryFn:  () => collabApi.listBots() as Promise<ChatBot[]>,
    staleTime: STALE_5_MIN_MS,
  })

  // Conversación activa = ?conv= de la URL si es válida; si no, primer canal disponible
  const activeConv = (() => {
    if (urlConvId) {
      const found = conversations.find(c => c.id === urlConvId)
      if (found) return found
    }
    if (conversations.length === 0) return null
    return conversations.find(c => c.kind === 'channel') || conversations[0]
  })()

  // Si la URL no trae conv pero ya hay conversaciones cargadas, fija la URL
  // por defecto (sin generar entrada nueva en el historial → replace).
  useEffect(() => {
    if (!urlConvId && activeConv?.id) {
      setSearchParams({ conv: activeConv.id }, { replace: true })
    }
  }, [urlConvId, activeConv?.id, setSearchParams])

  const setActiveConv = (c: Conv | null) => {
    if (!c?.id) return
    setSearchParams({ conv: c.id }, { replace: false })
    setMobileShowConv(true)
  }

  // Register Web Push subscription (best-effort, only if VAPID configured)
  useEffect(() => {
    registerCollabPush().catch(() => { /* ignore */ })
  }, [])

  // Auto-presencia: online al cargar, away en blur, offline al cerrar
  // Sólo activa cuando hay sesión válida (user no nulo) para evitar 401
  // del cleanup tras logout.
  useEffect(() => {
    if (!user?.id) return
    let stopped = false
    const setStatus = (status: string) => {
      if (stopped) return
      collabApi.setPresence({ status }).catch(() => {})
    }
    setStatus('online')
    const onVis = () => setStatus(document.visibilityState === 'visible' ? 'online' : 'away')
    const onBeforeUnload = () => {
      try {
        // sendBeacon y no el cliente: es lo único que sobrevive al cierre de la pestaña.
        navigator.sendBeacon(apiUrl('/collaboration/presence/me'), new Blob([JSON.stringify({ status: 'offline' })], { type: 'application/json' }))
      } catch { /* noop */ }
    }
    // Listener para "logout" — cuando se dispara este evento dejamos de
    // mandar updates de presencia (evita 401 inútiles al servidor).
    const onLogout = () => { stopped = true }
    document.addEventListener('visibilitychange', onVis)
    window.addEventListener('beforeunload', onBeforeUnload)
    window.addEventListener('auth:session-expired', onLogout)
    window.addEventListener('auth:logout-start', onLogout)
    // Heartbeat
    const hb = setInterval(() => {
      if (!stopped && document.visibilityState === 'visible') setStatus('online')
    }, PRESENCE_POLL_MS)
    return () => {
      stopped = true
      document.removeEventListener('visibilitychange', onVis)
      window.removeEventListener('beforeunload', onBeforeUnload)
      window.removeEventListener('auth:session-expired', onLogout)
      window.removeEventListener('auth:logout-start', onLogout)
      clearInterval(hb)
      // No emitimos "away" en el cleanup: si el cleanup viene de un logout,
      // ya no hay sesión y la llamada daría 401.
    }
  }, [user?.id])

  // Global keyboard shortcuts
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      const isMac = navigator.platform.toUpperCase().includes('MAC')
      const cmd = isMac ? e.metaKey : e.ctrlKey
      if (!cmd) return
      if (e.key.toLowerCase() === 'k') {
        e.preventDefault()
        setSearchModalOpen(true)
      } else if (e.key === '/') {
        e.preventDefault()
        const ta = document.querySelector('[data-chat-composer]') as HTMLTextAreaElement | null
        if (ta) { ta.focus(); ta.value = '/'; ta.dispatchEvent(new Event('input', { bubbles: true })) }
      } else if (e.shiftKey && e.key.toLowerCase() === 'a') {
        e.preventDefault()
        setActiveTab('activity')
      }
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [])

  // El WebSocket vive ahora en ChatRealtimeProvider (always-on, app-wide).
  // Aquí ya no se abre una conexión adicional para evitar duplicados; el
  // provider invalida React Query y reemite `collab:typing`/`collab:resync`.

  // ── Render ─────────────────────────────────────────────────────────────────
  return (
    <div style={{
      display: 'flex', height: 'calc(100vh - 56px)',
      background: 'var(--surface-0)', color: 'var(--text-1)',
    }}>
      {(!narrow || !mobileShowConv) && (<>
      <NavRail activeTab={activeTab} onTab={setActiveTab} unreadNotifs={notifications.filter(n => !n.is_read).length} />

      <ConversationsList
        narrow={narrow}
        activeTab={activeTab}
        conversations={conversations}
        teams={teams}
        channels={channels}
        presence={presence}
        loading={loadingConvs}
        activeConv={activeConv}
        onSelect={setActiveConv}
      />
      </>)}

      {(!narrow || mobileShowConv) && (
      <ConversationPane
        onBack={narrow ? () => setMobileShowConv(false) : undefined}
        conv={activeConv}
        currentUser={user}
        _bots={bots}
        draft={draft}
        setDraft={setDraft}
        showSlashMenu={showSlashMenu}
        setShowSlashMenu={setShowSlashMenu}
      />
      )}

      {activeConv && !narrow ? <ContextPanel conv={activeConv} /> : null}

      {searchModalOpen && (
        <SearchModal
          onClose={() => setSearchModalOpen(false)}
          onJump={(conversationId: string) => {
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
function NavRail({ activeTab, onTab, unreadNotifs }: { activeTab: string; onTab: (id: string) => void; unreadNotifs: number }) {
  const items = [
    { id: 'activity', label: 'Actividad', icon: Bell, badge: unreadNotifs },
    { id: 'chats',    label: 'Chat',      icon: MessageSquare },
    { id: 'teams',    label: 'Equipos',   icon: Users },
    { id: 'calls',    label: 'Llamadas',  icon: Phone },
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
            <span className="u-xs">{it.label}</span>
            {(it.badge ?? 0) > 0 && (
              <span style={{
                position: 'absolute', top: 6, right: 8,
                background: 'var(--danger)', color: 'var(--on-accent-light)',
                fontSize: 9, fontWeight: 800, padding: '1px 5px',
                borderRadius: 'var(--radius-full)', minWidth: 14, textAlign: 'center',
              }}>{(it.badge ?? 0) > 99 ? '99+' : it.badge}</span>
            )}
          </button>
        )
      })}
    </div>
  )
}

// ── Conversations sidebar (middle column) ────────────────────────────────────
function ConversationsList({ narrow = false, activeTab, conversations, teams, channels, presence, loading, activeConv, onSelect }: {
  narrow?: boolean; activeTab: string; conversations: Conv[]; teams: Team[]; channels: Channel[];
  presence: Presence[]; loading: boolean; activeConv: Conv | null; onSelect: (c: Conv) => void
}) {
  const [filter, setFilter] = useState('')
  const [openTeams, setOpenTeams] = useState(true)

  // Hooks must run unconditionally — compute always.
  const presenceMap = (() => {
    const m: Record<string, string> = {}
    for (const p of presence) if (p.user_id) m[p.user_id] = p.status
    return m
  })()
  const channelsByTeam = (() => {
    const map: Record<string, Channel[]> = {}
    for (const ch of channels) {
      map[ch.team_id] = map[ch.team_id] || []
      map[ch.team_id].push(ch)
    }
    return map
  })()

  if (activeTab === 'activity') return <ActivityList narrow={narrow} />

  const directs = conversations.filter(c => c.kind === 'direct')
  const groups = conversations.filter(c => c.kind === 'group')

  const matches = (text: string | undefined | null) => !filter || (text || '').toLowerCase().includes(filter.toLowerCase())

  return (
    <div style={{
      ...(narrow ? { flex: 1, minWidth: 0 } : { width: 300, flexShrink: 0 }),
      background: 'var(--surface-1)',
      borderRight: '1px solid var(--surface-4)',
      display: 'flex', flexDirection: 'column',
    }}>
      <div style={{ padding: '14px 14px 8px', borderBottom: '1px solid var(--surface-4)' }}>
        <div style={{ position: 'relative' }}>
          <Search size={14} style={{ position: 'absolute', left: 10, top: '50%', transform: 'translateY(-50%)', color: 'var(--text-3)' }} />
          <input aria-label="Buscar…"
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
        <NewConversationButton onCreated={(c) => onSelect && onSelect(c)} />
      </div>
    </div>
  )
}

function SectionGroup({ title, count, children, collapsed, onToggle }: {
  title: string; count?: number; children?: ReactNode; collapsed?: boolean; onToggle?: () => void
}) {
  return (
    <div className="u-mb-12">
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

function ConvRow({ c, active, onClick, presence, indent }: {
  c: Conv; active: boolean; onClick: () => void; presence?: string | null; indent?: boolean
}) {
  return (
    <button onClick={onClick} style={{
      display: 'flex', alignItems: 'center', gap: 10,
      width: '100%', padding: '7px 10px',
      paddingLeft: indent ? 22 : 10,
      background: active ? 'var(--accent-muted)' : 'transparent',
      border: '1px solid transparent',
      borderRadius: 'var(--radius-sm)',
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
            color: 'var(--on-accent-light)', display: 'flex', alignItems: 'center', justifyContent: 'center',
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

function NewConversationButton({ onCreated }: { onCreated?: (c: Conv) => void }) {
  const { t: traducir } = useAppLang()
  const [open, setOpen] = useState(false)
  return (
    <>
      <button onClick={() => setOpen(true)} style={{
        width: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 6,
        padding: '8px',
        background: 'var(--accent)', color: 'var(--on-accent)',
        border: 'none', borderRadius: 8,
        fontFamily: 'inherit', fontSize: 'var(--text-sm)', fontWeight: 700,
        cursor: 'pointer',
      }}>
        <Plus size={14} /> {traducir('chat.nuevo')}
      </button>
      {open && <NewConversationModal onClose={() => setOpen(false)} onCreated={(c) => { setOpen(false); onCreated?.(c) }} />}
    </>
  )
}

function NewConversationModal({ onClose, onCreated }: { onClose: () => void; onCreated?: (c: Conv) => void }) {
  const idCampo = useId()
  const { t: traducir } = useAppLang()
  const qc = useQueryClient()
  const toast = useToast()
  // Estado del formulario agrupado: todos los campos cambian juntos al
  // navegar entre pestañas (direct | group | channel) y se resetean a la
  // vez al cerrar. Un único objeto reduce el ruido de useStates sin
  // alterar la lógica.
  const [tab, setTab] = useState('direct')  // direct | group | channel
  type ModalForm = {
    search: string; selectedUsers: UserLike[]; groupTitle: string;
    channelName: string; channelType: string; selectedTeamId: string
  }
  const [form, updateForm] = useReducer(
    (s: ModalForm, patch: Partial<ModalForm>) => ({ ...s, ...patch }),
    {
      search: '',
      selectedUsers: [] as UserLike[],
      groupTitle: '',
      channelName: '',
      channelType: 'public',
      selectedTeamId: '',
    },
  )
  const { search, selectedUsers, groupTitle, channelName, channelType, selectedTeamId } = form

  const { data: suggestions = { users: [], groups: [] } } = useQuery({
    queryKey: ['mention-suggestions-modal', search],
    queryFn: () => collabApi.mentionSuggestions({ q: search, limit: MENTION_SUGGESTIONS_LIMIT }) as Promise<MentionSuggestions>,
  })
  const { data: teams = [] } = useQuery({
    queryKey: ['collab-teams'],
    queryFn: () => collabApi.listTeams() as Promise<Team[]>,
  })

  useEffect(() => {
    if (!selectedTeamId && teams.length > 0) updateForm({ selectedTeamId: teams[0].id })
  }, [teams, selectedTeamId])

  const toggleUser = (u: UserLike) => {
    updateForm({
      selectedUsers: selectedUsers.find(x => x.id === u.id)
        ? selectedUsers.filter(x => x.id !== u.id)
        : [...selectedUsers, u],
    })
  }

  const submit = useMutation({
    mutationFn: async () => {
      if (tab === 'direct') {
        if (!selectedUsers.length) throw new Error('Selecciona un usuario')
        return await collabApi.openDirect({ user_id: selectedUsers[0].id })
      } else if (tab === 'group') {
        if (!selectedUsers.length) throw new Error('Selecciona al menos 1 miembro')
        return await collabApi.createGroup({
          title: groupTitle.trim() || null,
          user_ids: selectedUsers.map(u => u.id),
        })
      } else {
        if (!channelName.trim()) throw new Error('Pon un nombre al canal')
        if (!selectedTeamId) throw new Error('Selecciona un equipo')
        const ch = await collabApi.createChannel({
          team_id: selectedTeamId,
          name: channelName.trim(),
          channel_type: channelType,
          initial_member_ids: selectedUsers.map(u => u.id),
        })
        return { conversation_id: ch.conversation_id }
      }
    },
    onSuccess: (data) => {
      qc.invalidateQueries({ queryKey: ['collab-conversations'] })
      qc.invalidateQueries({ queryKey: ['collab-channels'] })
      // Notifica al WS para que re-suscriba a la nueva conversación sin recargar página
      window.dispatchEvent(new CustomEvent('collab:resync'))
      onCreated?.({ id: data.conversation_id || data.id, kind: tab === 'channel' ? 'channel' : tab })
      toast.success(tab === 'direct' ? 'Chat abierto' : tab === 'group' ? 'Grupo creado' : 'Canal creado')
    },
    onError: (e: ApiError) => toast.error(e.message || e?.response?.data?.detail || 'Error'),
  })

  const dialogRef = useDialogo<HTMLDivElement>(true, onClose)
  return (
    <div role="presentation" onClick={onClose} style={styles.modalOverlay}>
      <div ref={dialogRef} role="dialog" aria-modal="true" tabIndex={-1}
        onClick={(e) => e.stopPropagation()}
        onKeyDown={(e) => { if (e.key === 'Escape') onClose() }}
        style={styles.modalDialog}>
        <div style={{ padding: '14px 18px', borderBottom: '1px solid var(--surface-4)', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <div className="u-md-700">{traducir('chat.nueva_conversacion')}</div>
          <button onClick={onClose} style={styles.iconCloseBtn}><X size={14} /></button>
        </div>
        <div style={{ display: 'flex', borderBottom: '1px solid var(--surface-4)' }}>
          {[{ id: 'direct', label: 'Chat directo', icon: MessageSquare },
            { id: 'group', label: 'Grupo', icon: Users },
            { id: 'channel', label: 'Canal', icon: Hash }].map(t => {
            const Icon = t.icon; const active = tab === t.id
            return (
              <button key={t.id} onClick={() => setTab(t.id)} style={{
                flex: 1, padding: '10px 14px',
                background: 'transparent', border: 'none',
                borderBottom: `2px solid ${active ? 'var(--accent)' : 'transparent'}`,
                cursor: 'pointer', fontFamily: 'inherit',
                fontSize: 'var(--text-sm)', fontWeight: active ? 700 : 500,
                color: active ? 'var(--accent)' : 'var(--text-2)',
                display: 'inline-flex', alignItems: 'center', justifyContent: 'center', gap: 6,
              }}><Icon size={13} /> {t.label}</button>
            )
          })}
        </div>
        <div style={{ padding: 18, maxHeight: '60vh', overflowY: 'auto' }}>
          {tab === 'group' && (
            <div className="u-mb-12">
              <label id={`${idCampo}-et1`} htmlFor={`${idCampo}-1`} style={styles.formLabel}>{traducir('chat.titulo_opcional')}</label>
              <input id={`${idCampo}-1`} aria-labelledby={`${idCampo}-et1`} value={form.groupTitle} onChange={(e) => updateForm({ groupTitle: e.target.value })} placeholder="Ej. Refactor backend"
                style={inputStyle} />
            </div>
          )}
          {tab === 'channel' && (
            <>
              <div className="u-mb-12">
                <label id={`${idCampo}-et2`} htmlFor={`${idCampo}-2`} style={styles.formLabel}>Nombre</label>
                <input id={`${idCampo}-2`} aria-labelledby={`${idCampo}-et2`} value={form.channelName} onChange={(e) => updateForm({ channelName: e.target.value })} placeholder="ej. ventas-q4" style={inputStyle} />
              </div>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10, marginBottom: 12 }}>
                <div>
                  <label id={`${idCampo}-et3`} htmlFor={`${idCampo}-3`} style={styles.formLabel}>Equipo</label>
                  <select id={`${idCampo}-3`} aria-labelledby={`${idCampo}-et3`} value={form.selectedTeamId} onChange={(e) => updateForm({ selectedTeamId: e.target.value })} style={inputStyle}>
                    {teams.map(t => <option key={t.id} value={t.id}>{t.name}</option>)}
                  </select>
                </div>
                <div>
                  <label id={`${idCampo}-et4`} htmlFor={`${idCampo}-4`} style={styles.formLabel}>Tipo</label>
                  <select id={`${idCampo}-4`} aria-labelledby={`${idCampo}-et4`} value={form.channelType} onChange={(e) => updateForm({ channelType: e.target.value })} style={inputStyle}>
                    <option value="public">{traducir('chat.publico')}</option>
                    <option value="private">Privado</option>
                    <option value="announcement">Anuncios</option>
                  </select>
                </div>
              </div>
            </>
          )}
          {tab === 'direct' ? (
            <div style={{ marginBottom: 8, fontSize: 'var(--text-xs)', color: 'var(--text-3)' }}>{traducir('chat.selecciona_un_usuario')}</div>
          ) : (
            <div style={{ marginBottom: 8, fontSize: 'var(--text-xs)', color: 'var(--text-3)' }}>
              {traducir('chat.anade_miembros')} {tab === 'group' ? '(mínimo 1)' : '(opcional)'}
            </div>
          )}
          <input aria-label="Buscar usuarios…" value={search} onChange={(e) => updateForm({ search: e.target.value })} placeholder="Buscar usuarios…"
            style={inputStyle} autoFocus />
          {selectedUsers.length > 0 && (
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, marginTop: 10 }}>
              {selectedUsers.map(u => (
                <span key={u.id} style={{
                  display: 'inline-flex', alignItems: 'center', gap: 6,
                  padding: '4px 10px', borderRadius: 'var(--radius-full)',
                  background: 'var(--accent-muted)', color: 'var(--accent)',
                  fontSize: 'var(--text-xs)', fontWeight: 700,
                }}>
                  {u.full_name || u.username} <button onClick={() => toggleUser(u)} style={{ background: 'none', border: 'none', color: 'var(--accent)', cursor: 'pointer' }}><X size={11} /></button>
                </span>
              ))}
            </div>
          )}
          <div style={{ marginTop: 10, maxHeight: 240, overflowY: 'auto' }}>
            {((suggestions.users || []) as UserLike[]).map((u: UserLike) => {
              const sel = !!selectedUsers.find(x => x.id === u.id)
              return (
                <button key={u.id} onClick={() => {
                  if (tab === 'direct') {
                    updateForm({ selectedUsers: [u] })
                  } else {
                    toggleUser(u)
                  }
                }} style={{
                  display: 'flex', alignItems: 'center', gap: 10,
                  width: '100%', padding: '8px 10px', borderRadius: 'var(--radius-sm)',
                  background: sel ? 'var(--accent-muted)' : 'transparent',
                  border: 'none', cursor: 'pointer', fontFamily: 'inherit', textAlign: 'left',
                }}>
                  <span style={{
                    width: 28, height: 28, borderRadius: '50%',
                    background: 'linear-gradient(135deg, var(--accent), var(--purple))',
                    color: 'var(--on-accent-light)', display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
                    fontSize: 11, fontWeight: 800,
                  }}>{(u.full_name || u.username || '?').charAt(0).toUpperCase()}</span>
                  <div className="u-flex1-min0">
                    <div className="u-text1-sm-600">{u.full_name}</div>
                    <div className="u-text3-xs">{u.email}</div>
                  </div>
                  {sel && <span style={{ fontSize: 'var(--text-xs)', color: 'var(--accent)' }}>✓</span>}
                </button>
              )
            })}
          </div>
        </div>
        <div style={{ padding: '12px 18px', borderTop: '1px solid var(--surface-4)', display: 'flex', justifyContent: 'flex-end', gap: 8 }}>
          <button onClick={onClose} style={{
            padding: '8px 16px', borderRadius: 8,
            background: 'transparent', color: 'var(--text-2)',
            border: '1px solid var(--surface-4)', cursor: 'pointer', fontFamily: 'inherit',
            fontSize: 'var(--text-sm)',
          }}>Cancelar</button>
          <button onClick={() => submit.mutate()} disabled={submit.isPending} style={{
            padding: '8px 16px', borderRadius: 8,
            background: 'var(--accent)', color: 'var(--on-accent)',
            border: 'none', cursor: submit.isPending ? 'not-allowed' : 'pointer',
            fontFamily: 'inherit', fontSize: 'var(--text-sm)', fontWeight: 700,
          }}>{submit.isPending ? 'Creando…' : 'Crear'}</button>
        </div>
      </div>
    </div>
  )
}

const inputStyle: CSSProperties = {
  width: '100%', boxSizing: 'border-box', marginTop: 4,
  background: 'var(--surface-3)', border: '1px solid var(--surface-4)',
  borderRadius: 8, padding: '8px 10px',
  color: 'var(--text-1)', fontSize: 'var(--text-sm)',
  outline: 'none', fontFamily: 'inherit',
}

// ── Modal: añadir miembros a un grupo existente ─────────────────────────────
function AddGroupMembersModal({ conv, existingUserIds, onClose, onAdded }: {
  conv: Conv; existingUserIds?: string[]; onClose: () => void; onAdded?: () => void
}) {
  const { t: traducir } = useAppLang()
  const toast = useToast()
  const [search, setSearch] = useState('')
  const [picked, setPicked] = useState<UserLike[]>([])

  const { data: suggestions = { users: [] } } = useQuery({
    queryKey: ['mention-suggestions-add-members', search],
    queryFn: () => collabApi.mentionSuggestions({ q: search, limit: MENTION_SUGGESTIONS_MEMBERS_LIMIT }) as Promise<MentionSuggestions>,
  })
  // Si no nos pasan existingUserIds, los obtenemos del servidor para evitar
  // que el listado proponga gente ya dentro del grupo.
  const { data: serverMembers = [] } = useQuery({
    queryKey: ['collab-members-for-add', conv?.id],
    queryFn: () => collabApi.listConversationMembers(conv.id) as Promise<Member[]>,
    enabled: !existingUserIds && !!conv?.id,
  })
  const dedupeIds: string[] = existingUserIds && existingUserIds.length
    ? existingUserIds
    : serverMembers.map(m => m.user_id).filter(Boolean)
  const candidates = ((suggestions.users || []) as UserLike[]).filter(u => !dedupeIds.includes(u.id))

  const submit = useMutation({
    mutationFn: () => collabApi.addConversationMembers(conv.id, { user_ids: picked.map(u => u.id) }),
    onSuccess: () => onAdded?.(),
    onError: (e: ApiError) => toast.error(e?.response?.data?.detail || 'No se pudieron añadir'),
  })

  const togglePick = (u: UserLike) => {
    setPicked(prev => prev.find(x => x.id === u.id) ? prev.filter(x => x.id !== u.id) : [...prev, u])
  }

  const dialogRef = useDialogo<HTMLDivElement>(true, onClose)
  return (
    <div role="presentation" onClick={onClose} style={styles.modalOverlay}>
      <div ref={dialogRef} role="dialog" aria-modal="true" tabIndex={-1}
        onClick={(e) => e.stopPropagation()}
        onKeyDown={(e) => { if (e.key === 'Escape') onClose() }}
        style={{
          background: 'var(--surface-2)', border: '1px solid var(--surface-4)',
          borderRadius: 12, padding: 20, width: 480, maxWidth: '90vw',
          maxHeight: '80vh', display: 'flex', flexDirection: 'column', gap: 12,
        }}
      >
        <div className="u-row-between">
          <div className="u-md-700">{traducir('chat.anadir_miembros_a')} {conv.title || 'grupo'}</div>
          <button onClick={onClose} style={styles.iconCloseBtn} aria-label="Cerrar">
            <X size={16} />
          </button>
        </div>
        <input
          autoFocus
          aria-label={traducir('chat.busca_por_nombre_o_email')}
          value={search}
          onChange={e => setSearch(e.target.value)}
          placeholder={traducir('chat.busca_por_nombre_o_email')}
          style={inputStyle}
        />
        {picked.length > 0 && (
          <div className="u-wrap-6">
            {picked.map(u => (
              <span key={u.id} style={{ display: 'inline-flex', alignItems: 'center', gap: 4, background: 'var(--accent-muted)', color: 'var(--accent)', borderRadius: 12, padding: '3px 8px', fontSize: 'var(--text-xs)' }}>
                {u.full_name || u.username}
                <button onClick={() => togglePick(u)} style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'inherit', padding: 0 }}>
                  <X size={11} />
                </button>
              </span>
            ))}
          </div>
        )}
        <div style={{ flex: 1, overflowY: 'auto', borderRadius: 8, border: '1px solid var(--surface-4)' }}>
          {candidates.length === 0 ? (
            <div style={{ padding: 14, fontSize: 'var(--text-sm)', color: 'var(--text-3)' }}>
              {search ? 'Sin resultados' : 'Empieza a escribir un nombre'}
            </div>
          ) : candidates.map(u => {
            const isPicked = !!picked.find(x => x.id === u.id)
            return (
              <button key={u.id} onClick={() => togglePick(u)}
                style={{
                  width: '100%', display: 'flex', alignItems: 'center', gap: 8,
                  padding: '8px 10px', background: isPicked ? 'var(--accent-muted)' : 'transparent',
                  border: 'none', borderBottom: '1px solid var(--surface-4)',
                  cursor: 'pointer', textAlign: 'left', color: 'var(--text-1)', fontSize: 'var(--text-sm)',
                }}>
                <div style={{ width: 24, height: 24, borderRadius: '50%', background: 'linear-gradient(135deg, var(--accent), var(--purple))', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 11, color: 'var(--on-accent-light)', fontWeight: 800 }}>
                  {(u.full_name || u.username || '?').charAt(0).toUpperCase()}
                </div>
                <span className="u-flex1">{u.full_name || u.username}</span>
                {isPicked && <span style={{ color: 'var(--accent)', fontSize: 'var(--text-xs)' }}>✓</span>}
              </button>
            )
          })}
        </div>
        <div className="u-actions-8">
          <button onClick={onClose} style={{
            background: 'transparent', border: '1px solid var(--surface-4)', borderRadius: 8,
            color: 'var(--text-2)', padding: '8px 14px', cursor: 'pointer', fontSize: 'var(--text-sm)',
          }}>Cancelar</button>
          <button
            disabled={!picked.length || submit.isPending}
            onClick={() => submit.mutate()}
            style={{
              background: picked.length ? 'var(--accent)' : 'var(--surface-4)',
              color: 'var(--on-accent-light)', border: 'none', borderRadius: 8, padding: '8px 14px',
              cursor: picked.length ? 'pointer' : 'not-allowed', fontSize: 'var(--text-sm)', fontWeight: 600,
            }}>
            {submit.isPending ? 'Añadiendo…' : `Añadir ${picked.length || ''}`.trim()}
          </button>
        </div>
      </div>
    </div>
  )
}

// ── Header dropdown: "..." con acciones de la conversación ─────────────────
function ConvHeaderMenu({ conv, currentUser, onClose, onAddMembers }: {
  conv: Conv; currentUser: UserLike; onClose: () => void; onAddMembers: () => void
}) {
  const qc = useQueryClient()
  const toast = useToast()
  const ref = useRef<HTMLDivElement>(null)

  // Click fuera + Esc cierran
  useEffect(() => {
    const onDoc = (e: MouseEvent) => { if (!ref.current?.contains(e.target as Node)) onClose() }
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }
    document.addEventListener('mousedown', onDoc)
    document.addEventListener('keydown', onKey)
    return () => {
      document.removeEventListener('mousedown', onDoc)
      document.removeEventListener('keydown', onKey)
    }
  }, [onClose])

  // Reglas existentes para esta conv → permite alternar silencio
  const { data: rules = [] } = useQuery({
    queryKey: ['collab-rules'],
    queryFn: () => collabApi.listRules() as Promise<NotificationRule[]>,
  })
  const convRule = rules.find(r => r.scope === 'conversation' && r.target_id === conv.id)
  const muted = convRule?.notify_messages === 'none'

  const upsertMute = useMutation({
    mutationFn: (toMute: boolean) => collabApi.upsertRule({
      scope: 'conversation', target_id: conv.id,
      notify_messages: toMute ? 'none' : 'all',
      desktop_push: !toMute, email_digest: 'weekly',
    }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['collab-rules'] }); onClose() },
  })

  const copyLink = () => {
    const url = `${window.location.origin}/chat?conv=${encodeURIComponent(conv.id)}`
    try {
      navigator.clipboard.writeText(url)
      toast.success('Enlace copiado')
    } catch {
      toast.error('No se pudo copiar')
    }
    onClose()
  }

  const leaveGroup = useMutation({
    mutationFn: () => collabApi.removeConversationMember(conv.id, currentUser.id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['collab-conversations'] })
      toast.success('Has salido del grupo')
      onClose()
    },
    onError: (e: ApiError) => toast.error(e?.response?.data?.detail || 'Error'),
  })

  const item = (icon: ReactNode, label: string, onClick: () => void, danger = false) => (
    <button onClick={onClick} style={{
      display: 'flex', alignItems: 'center', gap: 10, width: '100%',
      padding: '8px 12px', border: 'none', background: 'transparent',
      cursor: 'pointer', fontSize: 'var(--text-sm)', color: danger ? 'var(--danger)' : 'var(--text-1)',
      textAlign: 'left',
    }}
      onMouseEnter={e => { e.currentTarget.style.background = 'var(--surface-3)' }}
      onMouseLeave={e => { e.currentTarget.style.background = 'transparent' }}
    >
      {icon}
      <span className="u-flex1">{label}</span>
    </button>
  )

  return (
    <div ref={ref} role="menu" style={{
      position: 'absolute', top: 38, right: 0, zIndex: 'var(--z-sticky)',
      background: 'var(--surface-2)', border: '1px solid var(--surface-4)',
      borderRadius: 8, minWidth: 220, padding: '4px 0',
      boxShadow: '0 8px 24px rgba(0,0,0,0.32)',
    }}>
      {item(<LinkIcon size={14} />, 'Copiar enlace', copyLink)}
      {item(
        <BellOff size={14} />,
        muted ? 'Activar notificaciones' : 'Silenciar notificaciones',
        () => upsertMute.mutate(!muted),
      )}
      {conv.kind === 'group' && (
        <>
          <div style={{ height: 1, background: 'var(--surface-4)', margin: '4px 0' }} />
          {item(<UserPlus size={14} />, 'Añadir miembros…', onAddMembers)}
          {item(<LogOut size={14} />, 'Salir del grupo', async () => {
            if (await confirmar({ message: '¿Salir del grupo? Dejarás de recibir mensajes.', danger: true, confirmLabel: 'Salir' })) leaveGroup.mutate()
          }, true)}
        </>
      )}
    </div>
  )
}

// ── Conversation pane ────────────────────────────────────────────────────────
function ConversationPane({ onBack, conv, currentUser, _bots, draft, setDraft, showSlashMenu, setShowSlashMenu }: {
  onBack?: () => void; conv: Conv | null; currentUser: UserLike | null; _bots: ChatBot[]; draft: string;
  setDraft: Dispatch<SetStateAction<string>>; showSlashMenu: boolean;
  setShowSlashMenu: (v: boolean) => void
}) {
  const { t: traducir } = useAppLang()
  const realtime = useChatRealtime()
  const qc = useQueryClient()
  const toast = useToast()
  const fileRef = useRef<HTMLInputElement>(null)
  const composerRef = useRef<HTMLTextAreaElement>(null)
  const messagesEndRef = useRef<HTMLDivElement>(null)
  const [editing, setEditing] = useState<{ id: string; body: string } | null>(null)
  const [mentionState, setMentionState] = useState<{ query: string; items: UserLike[] } | null>(null)
  const [activeThreadRoot, setActiveThreadRoot] = useState<string | null>(null)
  const [typingUsers, setTypingUsers] = useState<Record<string, number>>({})  // { user_id: ts }
  const [isDragging, setIsDragging] = useState(false)
  const dragCounterRef = useRef(0)
  // panelUi agrupa flags de UI puramente locales del pane (popovers/modales
  // disparados desde el header o desde una acción de mensaje). No interactúan
  // con el WebSocket; agruparlos reduce ruido sin tocar la lógica realtime.
  type PanelUi = { headerMenuOpen: boolean; showAddMembers: boolean; linkPicker: LinkPicker | null }
  const [panelUi, setPanelUi] = useReducer(
    (s: PanelUi, patch: Partial<PanelUi>) => ({ ...s, ...patch }),
    { headerMenuOpen: false, showAddMembers: false, linkPicker: null } as PanelUi,
  )
  const { headerMenuOpen, showAddMembers, linkPicker } = panelUi

  const { data: messages = [], isLoading } = useQuery({
    queryKey: ['collab-messages', conv?.id],
    queryFn:  () => collabApi.listMessages(conv!.id, { limit: CHAT_MESSAGES_PAGE_SIZE }) as Promise<Msg[]>,
    enabled:  !!conv?.id,
    refetchInterval: POLL_FREQUENT_MS, // fallback polling — WS invalida casi siempre
  })

  // Parse @mentions from raw text → { mention_user_ids, is_everyone }
  const parseMentions = (text: string) => {
    const ids: string[] = []
    let everyone = false
    const re = /@([\w.-]+|\[[^\]]+\])/g
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
    mutationFn: (body: string) => {
      const mentions = parseMentions(body)
      return collabApi.sendMessage({
        conversation_id: conv!.id,
        body,
        parent_message_id: activeThreadRoot,
        ...mentions,
      })
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['collab-messages', conv!.id] })
      qc.invalidateQueries({ queryKey: ['collab-conversations'] })
    },
    onError: (e: ApiError) => toast.error(e?.response?.data?.detail || 'Error al enviar'),
  })

  const editMsg = useMutation({
    mutationFn: ({ id, body }: { id: string; body: string }) => collabApi.editMessage(id, { body }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['collab-messages', conv?.id] }),
    onError: (e: ApiError) => toast.error(e?.response?.data?.detail || 'Error al editar'),
  })

  const delMsg = useMutation({
    mutationFn: (id: string) => collabApi.deleteMessage(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['collab-messages', conv?.id] }),
  })

  const react = useMutation({
    mutationFn: ({ id, emoji }: { id: string; emoji: string }) => collabApi.toggleReaction(id, emoji),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['collab-messages', conv?.id] }),
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

  // Si el drag se cancela fuera del pane (Esc, salir de la ventana), aseguramos
  // que el overlay se cierra para que no quede pegado.
  useEffect(() => {
    const reset = () => { dragCounterRef.current = 0; setIsDragging(false) }
    window.addEventListener('dragend', reset)
    window.addEventListener('drop', reset)
    return () => {
      window.removeEventListener('dragend', reset)
      window.removeEventListener('drop', reset)
    }
  }, [])

  // Scroll to bottom on new messages
  useEffect(() => {
    if (messagesEndRef.current) messagesEndRef.current.scrollIntoView({ behavior: 'smooth' })
  }, [messages.length, conv?.id])

  // Slash menu detection
  useEffect(() => {
    setShowSlashMenu(draft.startsWith('/') && !draft.includes(' '))
  }, [draft, setShowSlashMenu])

  // Mention detection — busca el último @ sin cerrar.
  // Sólo dependemos de conv?.id para no relanzar al editar título u otros
  // campos del objeto conv que no afectan a la búsqueda.
  useEffect(() => {
    if (!conv?.id) return
    const m = draft.match(/(^|[\s])@([\w.-]{0,40})$/)
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
  }, [draft, conv?.id])

  // Typing emit (debounced)
  useEffect(() => {
    if (!conv?.id || !draft.trim()) return
    realtime.send({ type: 'typing', conversation_id: conv.id, active: true })
    const t = setTimeout(() => {
      realtime.send({ type: 'typing', conversation_id: conv.id, active: false })
    }, TYPING_IDLE_MS)
    return () => clearTimeout(t)
  }, [draft, conv?.id, realtime])

  // Listen to typing events from bus (delegated through window CustomEvent)
  useEffect(() => {
    const handler = (e: Event) => {
      const { conversation_id, payload }: TypingDetail = (e as CustomEvent<TypingDetail>).detail || {}
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
        const next: Record<string, number> = {}
        for (const [k, v] of Object.entries(prev)) if (v > cutoff) next[k] = v
        return next
      })
    }, TYPING_SWEEP_MS)
    return () => clearInterval(id)
  }, [])

  const insertMention = (item: UserLike) => {
    const insert = item.is_group ? `@${item.username} ` : `@[${item.full_name}|${item.id}] `
    const replaced = draft.replace(/(^|[\s])@([\w.-]{0,40})$/, (_m: string, p1: string) => `${p1}${insert}`)
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
        <div className="u-md-600">{traducir('chat.selecciona_una_conversacion')}</div>
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

  const handleFile = async (file: File) => {
    if (!file) return
    if (file.size > 500 * 1024 * 1024) {
      toast.error(`El archivo "${file.name}" excede el máximo de 500 MB`)
      return
    }
    const fd = new FormData()
    fd.append('conversation_id', conv.id)
    fd.append('file', file)
    try {
      const result = await collabApi.uploadAttachment(fd)
      qc.invalidateQueries({ queryKey: ['collab-messages', conv.id] })
      qc.invalidateQueries({ queryKey: ['collab-conversations'] })
      if (result?.is_quarantined) {
        toast.warning(`Archivo bloqueado: ${result.av_status === 'infected' ? 'antivirus' : 'DLP'}`)
      } else {
        toast.success('Archivo subido')
      }
      // Reset input value para permitir subir el mismo nombre dos veces
      if (fileRef.current) fileRef.current.value = ''
    } catch (e) {
      const detail = (e as ApiError)?.response?.data?.detail
      toast.error(typeof detail === 'string' ? detail : `Error al subir ${file.name}`)
      if (fileRef.current) fileRef.current.value = ''
    }
  }

  // Drag-and-drop + paste files anywhere within the conversation pane
  const onDragEnter = (e: ReactDragEvent) => {
    if (!e.dataTransfer?.types?.includes('Files')) return
    e.preventDefault()
    dragCounterRef.current += 1
    setIsDragging(true)
  }
  const onDragOver = (e: ReactDragEvent) => {
    if (!e.dataTransfer?.types?.includes('Files')) return
    e.preventDefault()
    e.dataTransfer.dropEffect = 'copy'
  }
  const onDragLeave = (e: ReactDragEvent) => {
    if (!e.dataTransfer?.types?.includes('Files')) return
    e.preventDefault()
    dragCounterRef.current = Math.max(0, dragCounterRef.current - 1)
    if (dragCounterRef.current === 0) setIsDragging(false)
  }
  const onDrop = (e: ReactDragEvent) => {
    if (!e.dataTransfer?.files?.length) return
    e.preventDefault()
    dragCounterRef.current = 0
    setIsDragging(false)
    for (const f of e.dataTransfer.files) handleFile(f)
  }
  const onPaste = (e: ReactClipboardEvent) => {
    const items = e.clipboardData?.items
    if (!items) return
    for (const it of items) {
      if (it.kind === 'file') {
        const f = it.getAsFile()
        if (f) handleFile(f)
      }
    }
  }

  const onCallStart = async (kind: string) => {
    try {
      const c = await collabApi.startCall({ conversation_id: conv.id, kind })
      // Almacenar credenciales en sessionStorage para evitar exponerlas en la URL
      sessionStorage.setItem(`call_creds_${c.call_id}`, JSON.stringify({
        token: c.livekit_token,
        room: c.livekit_room,
        url: c.livekit_url,
        kind,
      }))
      window.open(`/chat/call/${c.call_id}?kind=${kind}`, '_blank', 'width=1100,height=720')
    } catch {
      toast.error('Error iniciando llamada')
    }
  }

  return (
    <div
      role="region"
      aria-label={traducir('chat.conversacion')}
      style={{ flex: 1, display: 'flex', flexDirection: 'column', minWidth: 0, position: 'relative' }}
      onDragEnter={onDragEnter}
      onDragOver={onDragOver}
      onDragLeave={onDragLeave}
      onDrop={onDrop}
    >
      {isDragging && (
        <div style={{
          position: 'absolute', inset: 0, zIndex: 20,
          background: 'rgba(59,130,246,0.08)',
          border: '2px dashed var(--accent)', borderRadius: 8,
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          pointerEvents: 'none',
          fontSize: 'var(--text-md)', fontWeight: 700, color: 'var(--accent)',
        }}>
          {traducir('chat.suelta_el_archivo_para_subirlo')}
        </div>
      )}
      {/* Header */}
      <div style={{
        height: 56, padding: onBack ? '0 10px 0 56px' : '0 18px', flexShrink: 0, gap: 8,
        display: 'flex', alignItems: 'center', justifyContent: 'space-between',
        borderBottom: '1px solid var(--surface-4)', background: 'var(--surface-1)',
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, minWidth: 0 }}>
          {onBack && <IconBtn onClick={onBack} title={traducir('portalkb.volver')}><ChevronLeft size={16} /></IconBtn>}
          {conv.kind === 'channel' && <Hash size={18} />}
          {conv.kind === 'direct' && <MessageSquare size={18} />}
          {conv.kind === 'group' && <Users size={18} />}
          <div className="u-min0">
            <div style={{ fontSize: 'var(--text-md)', fontWeight: 700, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{conv.title}</div>
            {conv.channel_type && <div className="u-text3-xs">Canal {conv.channel_type}</div>}
          </div>
        </div>
        <div style={{ display: 'flex', gap: 8, position: 'relative', flexShrink: 0 }}>
          <IconBtn onClick={() => onCallStart('audio')} title={traducir('chat.llamada_de_voz')}><Phone size={15} /></IconBtn>
          <IconBtn onClick={() => onCallStart('video')} title="Videollamada"><Video size={15} /></IconBtn>
          <IconBtn onClick={() => setPanelUi({ headerMenuOpen: !headerMenuOpen })} title={traducir('chat.mas_acciones')}><MoreVertical size={15} /></IconBtn>
          {headerMenuOpen && (
            <ConvHeaderMenu
              conv={conv}
              currentUser={currentUser as UserLike}
              onClose={() => setPanelUi({ headerMenuOpen: false })}
              onAddMembers={() => setPanelUi({ headerMenuOpen: false, showAddMembers: true })}
            />
          )}
        </div>
      </div>
      {showAddMembers && conv.kind === 'group' && (
        <AddGroupMembersModal
          conv={conv}
          onClose={() => setPanelUi({ showAddMembers: false })}
          onAdded={() => {
            qc.invalidateQueries({ queryKey: ['collab-members', conv.id] })
            qc.invalidateQueries({ queryKey: ['collab-members-for-add', conv.id] })
            qc.invalidateQueries({ queryKey: ['collab-conversations'] })
            setPanelUi({ showAddMembers: false })
            toast.success('Miembros añadidos')
          }}
        />
      )}

      {/* Messages */}
      <div style={{ flex: 1, overflowY: 'auto', padding: '14px 18px', background: 'var(--surface-0)' }}>
        {isLoading && <Loader />}
        {messages.map((m, i) => {
          const prev = messages[i - 1]
          const compact = prev && prev.user_id === m.user_id && (+new Date(m.sent_at) - +new Date(prev.sent_at)) < 5 * 60_000
          return (
            <MessageBubble key={m.id} msg={m} compact={compact}
              isMine={m.user_id === currentUser?.id}
              onReact={(emoji) => react.mutate({ id: m.id, emoji })}
              onEdit={() => { setEditing({ id: m.id, body: m.body || '' }); setDraft(m.body || ''); composerRef.current?.focus() }}
              onDelete={async () => { if (await confirmar({ message: '¿Borrar mensaje?', danger: true, confirmLabel: 'Borrar' })) delMsg.mutate(m.id) }}
              onPin={() => collabApi.pinMessage(conv.id, m.id).then(() => qc.invalidateQueries({ queryKey: ['collab-messages', conv.id] }))}
              onSave={() => collabApi.saveMessage(m.id, undefined).then(() => toast.success('Guardado'))}
              onReplyThread={() => setActiveThreadRoot(m.id)}
              onLink={(kind) => setPanelUi({ linkPicker: { messageId: m.id, kind } })}
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
          <div style={styles.composerHintBar}>
            <MessageSquare size={12} /> Respondiendo en hilo
            <button onClick={() => setActiveThreadRoot(null)} style={{ ...styles.iconCloseBtn, marginLeft: 'auto' }}>
              <X size={12} />
            </button>
          </div>
        )}
        {editing && (
          <div style={styles.composerHintBar}>
            <Pencil size={12} /> Editando mensaje
            <button onClick={() => { setEditing(null); setDraft('') }} style={{ ...styles.iconCloseBtn, marginLeft: 'auto' }}>
              <X size={12} />
            </button>
          </div>
        )}
        <div style={{
          display: 'flex', alignItems: 'flex-end', gap: 8,
          background: 'var(--surface-3)', border: '1px solid var(--surface-4)',
          borderRadius: 12, padding: '8px 10px',
        }}>
          {/* Patrón label+input: el click en el label abre el selector sin
              depender de programmatic .click() (más fiable cross-browser) */}
          <label title="Adjuntar archivo" style={{
            position: 'relative',
            width: 32, height: 32, flexShrink: 0,
            display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
            background: 'transparent', borderRadius: 'var(--radius-sm)',
            color: 'var(--text-2)', cursor: 'pointer',
          }}
            onMouseEnter={e => { e.currentTarget.style.background = 'var(--surface-4)' }}
            onMouseLeave={e => { e.currentTarget.style.background = 'transparent' }}
          >
            <Paperclip size={16} />
            <input ref={fileRef} type="file" aria-label="Adjuntar archivo"
              style={{ position: 'absolute', width: 1, height: 1, padding: 0, margin: -1, overflow: 'hidden', clip: 'rect(0,0,0,0)', whiteSpace: 'nowrap', border: 0 }}
              onChange={e => {
                const f = e.target.files?.[0]
                if (f) handleFile(f)
              }} />
          </label>
          <textarea
            ref={composerRef}
            data-chat-composer
            aria-label={`Mensaje en ${conv.title}`}
            value={draft}
            onChange={e => setDraft(e.target.value)}
            onKeyDown={e => {
              if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault()
                handleSend()
              }
            }}
            onPaste={onPaste}
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
            style={{ background: 'var(--accent)', color: 'var(--on-accent)' }}>
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
          onClose={() => setPanelUi({ linkPicker: null })}
          onPicked={() => {
            setPanelUi({ linkPicker: null })
            qc.invalidateQueries({ queryKey: ['collab-messages', conv.id] })
            toast.success('Anclado')
          }}
        />
      )}
    </div>
  )
}

function IconBtn({ children, onClick, title, style = {} }: {
  children: ReactNode; onClick?: () => void; title?: string; style?: CSSProperties
}) {
  return (
    <button onClick={onClick} title={title} style={{
      width: 32, height: 32,
      display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
      background: 'transparent', border: '1px solid transparent', borderRadius: 'var(--radius-sm)',
      color: 'var(--text-2)', cursor: 'pointer', flexShrink: 0,
      ...style,
    }}
      onMouseEnter={e => { if (!style.background) e.currentTarget.style.background = 'var(--surface-4)' }}
      onMouseLeave={e => { if (!style.background) e.currentTarget.style.background = 'transparent' }}
    >{children}</button>
  )
}

// ── Message bubble with hover actions ────────────────────────────────────────
function MessageBubble({ msg, compact, isMine, onReact, onEdit, onDelete, onPin, onSave, onReplyThread, onLink }: {
  msg: Msg; compact?: boolean; isMine: boolean; onReact: (emoji: string) => void;
  onEdit: () => void; onDelete: () => void; onPin: () => void; onSave: () => void;
  onReplyThread: () => void; onLink: (kind: string) => void
}) {
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
          fontSize: 'var(--text-sm)', fontWeight: 800, color: 'var(--on-accent-light)',
        }}>
          {msg.bot_id ? <Bot size={16} /> : (author?.charAt(0)?.toUpperCase() || '?')}
        </div>
      ) : (
        <div style={{ width: 36, flexShrink: 0 }} />
      )}
      <div className="u-flex1-min0">
        {!compact && (
          <div style={{ display: 'flex', alignItems: 'baseline', gap: 8, marginBottom: 2 }}>
            <span className="u-sm-700">{author}</span>
            {msg.bot_id && <span style={{ fontSize: 'var(--text-xs)', padding: '1px 6px', background: 'var(--accent-muted)', color: 'var(--accent)', borderRadius: 4, fontWeight: 700 }}>BOT</span>}
            <span className="u-text3-xs">
              {new Date(msg.sent_at).toLocaleTimeString(localeActivo(), { hour: '2-digit', minute: '2-digit' })}
            </span>
            {msg.is_pinned && <Pin size={11} style={{ color: 'var(--warning)' }} />}
            {msg.edited_at && <span className="u-text3-xs">(editado)</span>}
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
            {msg.attachments.map(a => <AttachmentChip key={a.id} att={a} />)}
          </div>
        )}
        {msg.reactions?.length > 0 && (
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4, marginTop: 4 }}>
            {Object.entries(groupReactions(msg.reactions)).map(([emoji, users]) => (
              <button key={emoji} onClick={() => onReact(emoji)} style={{
                display: 'inline-flex', alignItems: 'center', gap: 4,
                padding: '2px 8px', borderRadius: 'var(--radius-full)',
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
          borderRadius: 'var(--radius-sm)', padding: 2, boxShadow: '0 2px 8px rgba(0,0,0,0.3)',
        }}>
          {['👍', '❤️', '😂', '🎉'].map(e => (
            <button key={e} onClick={() => onReact(e)} style={{ background: 'none', border: 'none', cursor: 'pointer', padding: 4, fontSize: 14 }}>{e}</button>
          ))}
          <IconBtn onClick={onReplyThread} title="Responder en hilo"><MessageSquare size={13} /></IconBtn>
          <IconBtn onClick={onPin} title="Anclar"><Pin size={13} /></IconBtn>
          <IconBtn onClick={onSave} title="Guardar"><Bookmark size={13} /></IconBtn>
          <IconBtn onClick={() => onLink && onLink('task')} title="Anclar a tarea"><ListChecks size={13} /></IconBtn>
          <IconBtn onClick={() => onLink && onLink('ticket')} title="Anclar a ticket"><Headphones size={13} /></IconBtn>
          <IconBtn onClick={() => onLink && onLink('deliverable')} title="Anclar a entregable"><FileText size={13} /></IconBtn>
          <IconBtn onClick={() => onLink && onLink('risk')} title="Anclar a riesgo"><AlertCircle size={13} /></IconBtn>
          {isMine && <IconBtn onClick={onEdit} title="Editar"><Pencil size={13} /></IconBtn>}
          {isMine && <IconBtn onClick={onDelete} title="Borrar" style={{ color: 'var(--danger)' }}><Trash2 size={13} /></IconBtn>}
        </div>
      )}
    </div>
  )
}

function groupReactions(rs: Reaction[]) {
  const out: Record<string, string[]> = {}
  for (const r of rs) {
    out[r.emoji] = out[r.emoji] || []
    out[r.emoji].push(r.user_id || r.client_user_id)
  }
  return out
}

// ── Bot card renderers ───────────────────────────────────────────────────────
function BotCard({ meta }: { meta: BotMeta }) {
  const { t: traducir } = useAppLang()
  if (!meta?.card) return null
  if (meta.card === 'task') return <Card icon={ListChecks} accent="var(--success)" title="Tarea creada" body={`#${meta.task_id?.slice(0, 8) || ''}`} />
  if (meta.card === 'ticket' || meta.card === 'escalation') return <Card icon={Headphones} accent="var(--warning)" title={traducir('chat.ticket_de_soporte')} body={`Nº ${meta.ticket?.number || meta.ticket?.id?.slice(0, 8)} → ${meta.ticket?.assignee || ''}`} />
  if (meta.card === 'imputation') return <Card icon={Zap} accent="var(--accent)" title={`${meta.hours}h imputadas`} body={`Proyecto ${meta.project_id?.slice(0, 8) || '?'}`} />
  if (meta.card === 'risk') return <Card icon={AlertCircle} accent="var(--danger)" title="Riesgo registrado" body={meta.title} />
  if (meta.card === 'decision') return <Card icon={FileSignature} accent="var(--purple, #7c3aed)" title={traducir('chat.decision_registrada')} body={meta.text} />
  if (meta.card === 'poll') return <PollCard meta={meta} />
  if (meta.card === 'call') return <Card icon={Video} accent="var(--accent)" title="Llamada iniciada" body={`Sala ${meta.room?.slice(-8) || ''}`} />
  if (meta.card === 'call_summary') return <Card icon={Sparkles} accent="var(--accent)" title={traducir('chat.resumen_de_reunion')} body={`${meta.actions?.length || 0} acciones detectadas`} />
  if (meta.card === 'answer') return <Card icon={Sparkles} accent="var(--accent)" title="Nexus IA" body={meta.source} />
  if (meta.card === 'webhook') return <Card icon={Megaphone} accent="var(--purple)" title={meta.source || 'Webhook entrante'} body="" />
  return null
}

function Card({ icon: Icon, accent, title, body }: {
  icon: LucideIcon; accent: string; title: ReactNode; body: ReactNode
}) {
  return (
    <div style={{
      display: 'flex', alignItems: 'center', gap: 10,
      marginTop: 6, padding: '10px 12px',
      background: alpha(accent, '10'), border: `1px solid ${alpha(accent, '40')}`, borderRadius: 8,
      maxWidth: 480,
    }}>
      <div style={{
        width: 28, height: 28, borderRadius: 'var(--radius-sm)', flexShrink: 0,
        background: alpha(accent, '25'), color: accent,
        display: 'flex', alignItems: 'center', justifyContent: 'center',
      }}><Icon size={15} /></div>
      <div className="u-min0">
        <div style={{ fontSize: 'var(--text-xs)', fontWeight: 700, color: accent, textTransform: 'uppercase', letterSpacing: '0.06em' }}>{title}</div>
        {body && <div className="u-text2-sm">{body}</div>}
      </div>
    </div>
  )
}

function PollCard({ meta }: { meta: BotMeta }) {
  return (
    <div style={{ marginTop: 6, padding: '12px 14px', background: 'var(--surface-3)', border: '1px solid var(--surface-4)', borderRadius: 8, maxWidth: 460 }}>
      <div style={{ fontSize: 'var(--text-sm)', fontWeight: 700, marginBottom: 8 }}>📊 {meta.question}</div>
      {(meta.options || []).map((o, i) => (
        <button key={i} style={{
          display: 'block', width: '100%', textAlign: 'left',
          padding: '6px 10px', marginBottom: 4,
          background: 'var(--surface-2)', border: '1px solid var(--surface-4)', borderRadius: 'var(--radius-sm)',
          fontFamily: 'inherit', cursor: 'pointer',
          fontSize: 'var(--text-sm)', color: 'var(--text-1)',
        }}>{o.label} <span className="u-text3-xs">({o.votes || 0})</span></button>
      ))}
    </div>
  )
}

// ── Attachment chip ────────────────────────────────────────────────────────
function AttachmentChip({ att }: { att: Attachment }) {
  const [meta, setMeta] = useState<Attachment>(att)
  // Si ya tenemos download_url usamos eso; si no, pedimos detalle al backend
  useEffect(() => {
    if (att.download_url || att.is_quarantined) return
    let cancel = false
    collabApi.getAttachment(att.id).then(d => { if (!cancel) setMeta(d) }).catch(() => {})
    return () => { cancel = true }
  }, [att.id, att.download_url, att.is_quarantined])

  const isImage = (meta.mime_type || '').startsWith('image/')
  const downloadUrl = meta.download_url
  const previewUrl = meta.preview_url || (isImage ? downloadUrl : null)

  if (meta.is_quarantined) {
    return (
      <div style={{
        display: 'flex', alignItems: 'center', gap: 8,
        padding: '6px 10px', background: 'var(--danger-bg, rgba(239,68,68,0.12))',
        border: '1px solid var(--danger-border, rgba(239,68,68,0.3))', borderRadius: 8,
        fontSize: 'var(--text-xs)', color: 'var(--danger)',
      }}>
        <AlertCircle size={13} /> {att.name} · cuarentena
      </div>
    )
  }

  if (isImage && previewUrl) {
    return (
      <a href={downloadUrl} target="_blank" rel="noopener noreferrer"
        style={{ display: 'block', maxWidth: 320, borderRadius: 'var(--radius-md)', overflow: 'hidden', border: '1px solid var(--surface-4)' }}>
        <img src={previewUrl} alt={att.name} loading="lazy" decoding="async" style={{ display: 'block', width: '100%', maxHeight: 240, objectFit: 'cover' }} />
      </a>
    )
  }

  return (
    <a href={downloadUrl || '#'} target="_blank" rel="noopener noreferrer"
      style={{
        display: 'flex', alignItems: 'center', gap: 8,
        padding: '8px 12px', background: 'var(--surface-3)',
        border: '1px solid var(--surface-4)', borderRadius: 8,
        fontSize: 'var(--text-xs)', textDecoration: 'none', color: 'var(--text-1)',
        maxWidth: 360,
      }}>
      <FileText size={15} style={{ color: 'var(--accent)' }} />
      <div className="u-flex1-min0">
        <div style={{ fontWeight: 600, color: 'var(--text-1)', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{att.name}</div>
        <div className="u-text3">
          {att.size_bytes >= 1024 * 1024
            ? `${(att.size_bytes / (1024 * 1024)).toFixed(1)} MB`
            : `${Math.round(att.size_bytes / 1024)} KB`}
          {att.mime_type && ` · ${att.mime_type.split('/')[1] || att.mime_type}`}
        </div>
      </div>
    </a>
  )
}

// ── Search modal (Cmd+K) ───────────────────────────────────────────────────
function SearchModal({ onClose, onJump }: { onClose: () => void; onJump: (conversationId: string) => void }) {
  const { t: traducir } = useAppLang()
  const [q, setQ] = useState('')
  const { data: result, isFetching } = useQuery({
    queryKey: ['collab-search', q],
    queryFn: () => collabApi.search({ q, limit: CHAT_SEARCH_LIMIT }) as Promise<{ hits?: SearchHit[] }>,
    enabled: q.trim().length >= 2,
  })
  const hits: SearchHit[] = result?.hits || []
  const dialogRef = useDialogo<HTMLDivElement>(true, onClose)
  return (
    <div role="presentation" onClick={onClose} style={{
      ...styles.modalOverlay,
      alignItems: 'flex-start', padding: '8vh 16px',
    }}>
      <div ref={dialogRef} role="dialog" aria-modal="true" tabIndex={-1}
        onClick={(e) => e.stopPropagation()}
        onKeyDown={(e) => { if (e.key === 'Escape') onClose() }}
        style={{
        background: 'var(--surface-2)', border: '1px solid var(--surface-4)',
        borderRadius: 'var(--radius-lg)', width: 640, maxWidth: '94%', overflow: 'hidden',
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '14px 18px', borderBottom: '1px solid var(--surface-4)' }}>
          <Search size={16} style={{ color: 'var(--text-3)' }} />
          <input aria-label="Buscar mensajes…  (operadores: from:, in:, before:, has:link, is:pinned …)" value={q} onChange={(e) => setQ(e.target.value)} autoFocus
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
              {traducir('chat.escribe_al_menos_2_caracteres_soporta_operadores')} <code>from:juan</code> · <code>in:#general</code> · <code>before:2026-05-01</code> · <code>has:link</code> · <code>is:pinned</code> · <code>type:bot</code>
            </div>
          )}
          {isFetching && <div style={{ padding: 18, fontSize: 'var(--text-sm)', color: 'var(--text-3)' }}>Buscando…</div>}
          {!isFetching && q.trim().length >= 2 && hits.length === 0 && (
            <div style={{ padding: 18, fontSize: 'var(--text-sm)', color: 'var(--text-3)' }}>{traducir('chat.sin_resultados')}</div>
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
              <div className="u-text3-xs">
                {h.sent_at ? new Date(h.sent_at).toLocaleString(localeActivo()) : ''}
              </div>
            </button>
          ))}
        </div>
      </div>
    </div>
  )
}

// ── Linked entity chips ────────────────────────────────────────────────────
function LinkedEntityChips({ msg }: { msg: Msg }) {
  const chips: Array<{ icon: LucideIcon; label: string; href: string; color: string }> = []
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
            padding: '4px 10px', borderRadius: 'var(--radius-full)',
            background: alpha(c.color, '15'), border: `1px solid ${alpha(c.color, '40')}`,
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
function LinkPickerModal({ messageId, kind, onClose, onPicked }: {
  messageId: string; kind: string; onClose: () => void; onPicked: () => void
}) {
  const { t: traducir } = useAppLang()
  const [q, setQ] = useState('')
  const { data: items = [] } = useQuery({
    queryKey: ['link-candidates', messageId, kind, q],
    queryFn: () => collabApi.linkCandidates(messageId, { kind, q }) as Promise<LinkCandidate[]>,
  })
  const link = useMutation({
    mutationFn: (id: string) => collabApi.linkMessage(messageId, { kind, id }),
    onSuccess: onPicked,
  })
  const dialogRef = useDialogo<HTMLDivElement>(true, onClose)
  return (
    <div role="presentation" onClick={onClose} style={styles.modalOverlay}>
      <div ref={dialogRef} role="dialog" aria-modal="true" tabIndex={-1}
        onClick={(e) => e.stopPropagation()}
        onKeyDown={(e) => { if (e.key === 'Escape') onClose() }}
        style={{
        background: 'var(--surface-2)', border: '1px solid var(--surface-4)',
        borderRadius: 12, padding: 18, width: 480, maxWidth: '92%',
      }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
          <div className="u-md-700">
            Anclar a {({ task: 'tarea', ticket: 'ticket', deliverable: 'entregable', risk: 'riesgo' } as Record<string, string>)[kind] ?? kind}
          </div>
          <button onClick={onClose} style={styles.iconCloseBtn}>
            <X size={14} />
          </button>
        </div>
        <input aria-label="Buscar…" value={q} onChange={(e) => setQ(e.target.value)} placeholder="Buscar…" autoFocus
          style={{
            width: '100%', boxSizing: 'border-box',
            background: 'var(--surface-3)', border: '1px solid var(--surface-4)',
            borderRadius: 8, padding: '10px 12px',
            color: 'var(--text-1)', fontSize: 'var(--text-sm)', outline: 'none', fontFamily: 'inherit',
          }} />
        <div style={{ marginTop: 10, maxHeight: 320, overflowY: 'auto' }}>
          {items.length === 0 && <div style={{ fontSize: 'var(--text-xs)', color: 'var(--text-3)', padding: 14 }}>{traducir('chat.sin_resultados')}</div>}
          {items.map((it) => (
            <button key={it.id} onClick={() => link.mutate(it.id)} style={{
              display: 'block', width: '100%', textAlign: 'left',
              padding: '10px 12px', borderRadius: 'var(--radius-sm)',
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
function MentionMenu({ items, onPick }: { items: UserLike[]; onPick: (it: UserLike) => void }) {
  return (
    <div style={styles.popoverMenu}>
      {items.map((it, i) => (
        <button key={i} onClick={() => onPick(it)} style={styles.popoverItem}
          onMouseEnter={e => e.currentTarget.style.background = 'var(--surface-3)'}
          onMouseLeave={e => e.currentTarget.style.background = 'transparent'}>
          <span style={{
            width: 26, height: 26, borderRadius: '50%', display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
            background: 'linear-gradient(135deg, var(--accent), var(--purple, #7c3aed))',
            color: 'var(--on-accent-light)', fontSize: 11, fontWeight: 800,
          }}>{(it.full_name || it.username || '?').charAt(0).toUpperCase()}</span>
          <div className="u-flex1-min0">
            <div style={{ fontSize: 'var(--text-sm)', fontWeight: 700, color: 'var(--text-1)' }}>
              {it.full_name}{it.is_group ? '' : ` (@${it.username || ''})`}
            </div>
            {it.email && <div className="u-text3-xs">{it.email}</div>}
          </div>
        </button>
      ))}
    </div>
  )
}

// ── Thread side panel ──────────────────────────────────────────────────────
function ThreadPanel({ conv, rootId, onClose }: { conv: Conv; rootId: string; onClose: () => void }) {
  const { t: traducir } = useAppLang()
  const qc = useQueryClient()
  const [reply, setReply] = useState('')
  const { data: thread = [] } = useQuery({
    queryKey: ['collab-thread', conv?.id, rootId],
    queryFn: () => collabApi.listMessages(conv.id, { thread_root: rootId, limit: CHAT_THREAD_MESSAGES_LIMIT }) as Promise<Msg[]>,
    enabled: !!conv?.id && !!rootId,
    refetchInterval: POLL_FREQUENT_MS,
  })
  const send = useMutation({
    mutationFn: () => collabApi.sendMessage({ conversation_id: conv.id, parent_message_id: rootId, body: reply }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['collab-thread', conv.id, rootId] })
      qc.invalidateQueries({ queryKey: ['collab-messages', conv.id] })
      setReply('')
    },
  })
  return (
    <div style={{
      position: 'fixed', top: 56, right: 0, bottom: 0, width: 380,
      background: 'var(--surface-1)', borderLeft: '1px solid var(--surface-4)',
      display: 'flex', flexDirection: 'column', zIndex: 'var(--z-sticky)',
    }}>
      <div style={{ height: 48, padding: '0 16px', display: 'flex', alignItems: 'center', justifyContent: 'space-between', borderBottom: '1px solid var(--surface-4)' }}>
        <div className="u-sm-700">Hilo · {thread.length} respuesta{thread.length === 1 ? '' : 's'}</div>
        <button onClick={onClose} style={styles.iconCloseBtn}><X size={14} /></button>
      </div>
      <div style={{ flex: 1, overflowY: 'auto', padding: '12px 16px' }}>
        {thread.length === 0 && <div className="u-text3-xs">{traducir('chat.sin_respuestas_todavia')}</div>}
        {thread.map(m => (
          <div key={m.id} className="u-mb-14">
            <div className="u-text3-xs">{m.author_name || 'Usuario'} · {new Date(m.sent_at).toLocaleTimeString(localeActivo(), { hour: '2-digit', minute: '2-digit' })}</div>
            <div style={{ fontSize: 'var(--text-sm)', whiteSpace: 'pre-wrap', color: 'var(--text-1)' }}>{m.body}</div>
          </div>
        ))}
      </div>
      <div style={{ padding: 10, borderTop: '1px solid var(--surface-4)', display: 'flex', gap: 6 }}>
        <input aria-label="Responder en hilo…" value={reply} onChange={e => setReply(e.target.value)}
          onKeyDown={e => e.key === 'Enter' && reply.trim() && send.mutate()}
          placeholder="Responder en hilo…"
          style={{
            flex: 1, padding: '8px 10px',
            background: 'var(--surface-3)', border: '1px solid var(--surface-4)', borderRadius: 8,
            color: 'var(--text-1)', fontSize: 'var(--text-sm)', outline: 'none', fontFamily: 'inherit',
          }} />
        <IconBtn onClick={() => reply.trim() && send.mutate()} style={{ background: 'var(--accent)', color: 'var(--on-accent)' }}><Send size={14} /></IconBtn>
      </div>
    </div>
  )
}

// ── Slash menu ──────────────────────────────────────────────────────────────
function SlashMenu({ draft, onPick }: { draft: string; onPick: (cmd: string) => void }) {
  const { data: help = { commands: [] } } = useQuery<{ commands: SlashCommand[] }>({
    queryKey: ['collab-slash-help'],
    queryFn:  () => collabApi.slashHelp() as Promise<{ commands: SlashCommand[] }>,
    staleTime: STALE_1_HOUR_MS,
  })
  const term = draft.replace('/', '').toLowerCase()
  const cmds = help.commands.filter(c => c.name.replace('/', '').toLowerCase().startsWith(term))
  if (!cmds.length) return null
  return (
    <div style={styles.popoverMenu}>
      {cmds.map((c, i) => (
        <button key={i} onClick={() => onPick(c.name.replace('/', ''))} style={styles.popoverItem}
          onMouseEnter={e => e.currentTarget.style.background = 'var(--surface-3)'}
          onMouseLeave={e => e.currentTarget.style.background = 'transparent'}
        >
          <span style={{ fontFamily: 'var(--font-mono)', fontWeight: 800, color: 'var(--accent)' }}>{c.name}</span>
          <span className="u-text3-xs">{c.desc}</span>
        </button>
      ))}
    </div>
  )
}

// ── Right context panel ─────────────────────────────────────────────────────
function ContextPanel({ conv }: { conv: Conv }) {
  const { t: traducir } = useAppLang()
  const qc = useQueryClient()
  const toast = useToast()
  const { user: me } = useAuth()
  const [showAddMember, setShowAddMember] = useState(false)
  const { data: pins = [] } = useQuery({
    queryKey: ['collab-pins', conv.id],
    queryFn: () => collabApi.listPins(conv.id) as Promise<PreviewRow[]>,
    enabled: !!conv?.id,
  })
  const { data: members = [] } = useQuery({
    queryKey: ['collab-members', conv?.id, conv?.kind],
    queryFn: async (): Promise<Member[]> => {
      if (conv?.kind === 'channel') {
        const all = await collabApi.listChannels(undefined)
        const ch = (all as Channel[]).find(x => x.conversation_id === conv.id)
        if (ch) return collabApi.listChannelMembers(ch.id) as Promise<Member[]>
        return []
      }
      if (conv?.kind === 'group') {
        return collabApi.listConversationMembers(conv.id) as Promise<Member[]>
      }
      return []
    },
    enabled: !!conv?.id,
  })
  const removeMember = useMutation({
    mutationFn: (uid: string) => collabApi.removeConversationMember(conv.id, uid),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['collab-members', conv.id] })
      qc.invalidateQueries({ queryKey: ['collab-conversations'] })
      toast.success('Miembro eliminado')
    },
    onError: (e: ApiError) => toast.error(e?.response?.data?.detail || 'No se pudo eliminar'),
  })
  const { data: calls = [] } = useQuery({
    queryKey: ['collab-calls', conv.id],
    queryFn: () => collabApi.listCalls(conv.id) as Promise<CallRow[]>,
    enabled: !!conv?.id,
  })
  const { data: calendar } = useQuery<CalendarData>({
    queryKey: ['collab-calendar'],
    queryFn: () => collabApi.calendarEvents(7) as Promise<CalendarData>,
    refetchInterval: POLL_SLOW_MS,
  })
  const { data: decisions = [] } = useQuery({
    queryKey: ['collab-decisions-context'],
    queryFn: () => collabApi.listDecisions(5) as Promise<Decision[]>,
  })
  const { data: presenceList = [] } = useQuery({
    queryKey: ['collab-presence'],
    queryFn: () => collabApi.listPresence() as Promise<Presence[]>,
    refetchInterval: POLL_FREQUENT_MS,
  })
  const onlineUsers = presenceList.filter(p => p.user_id && p.status && p.status !== 'offline')

  return (
    <div style={{
      width: 280, flexShrink: 0,
      background: 'var(--surface-1)',
      borderLeft: '1px solid var(--surface-4)',
      overflowY: 'auto', padding: '14px 14px 24px',
    }}>
      <Section title={traducir('chat.informacion')}>
        <div className="u-text2-sm">{conv.kind === 'channel' ? 'Canal' : conv.kind === 'group' ? 'Grupo' : 'Chat directo'}</div>
      </Section>
      <Section title={`Conectados (${onlineUsers.length})`}>
        {onlineUsers.length === 0 ? <Empty>Nadie online ahora</Empty> : onlineUsers.slice(0, 12).map(p => {
          const name = p.user_name || 'Usuario'
          return (
            <div key={p.user_id} style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '4px 0' }}>
              <span style={{ position: 'relative', display: 'inline-flex' }}>
                <span style={styles.avatar22}>{name.charAt(0).toUpperCase()}</span>
                <span style={{
                  ...styles.presenceDot,
                  background: p.status === 'online' ? 'var(--success)' : p.status === 'busy' ? 'var(--danger)' : 'var(--warning)',
                }} />
              </span>
              <span style={{ fontSize: 'var(--text-sm)', color: 'var(--text-1)', flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{name}</span>
              {p.is_in_call && <Phone size={10} style={{ color: 'var(--accent)' }} />}
            </div>
          )
        })}
      </Section>
      {(members.length > 0 || conv.kind === 'group') && (
        <Section
          title={`Miembros (${members.length})`}
          right={conv.kind === 'group' ? (
            <button
              onClick={() => setShowAddMember(true)}
              title={traducir('chat.anadir_miembro')}
              style={{ background: 'var(--surface-3)', border: '1px solid var(--surface-4)', borderRadius: 'var(--radius-sm)', color: 'var(--text-2)', cursor: 'pointer', padding: '2px 6px', fontSize: 'var(--text-xs)', fontWeight: 600, display: 'inline-flex', alignItems: 'center', gap: 4 }}
            >
              <Plus size={11} /> {traducir('chat.anadir')}
            </button>
          ) : null}
        >
          {members.slice(0, 12).map(m => {
            const isMe = m.user_id === me?.id
            const canRemove = conv.kind === 'group' && (isMe || members.find(mm => mm.user_id === me?.id)?.is_admin)
            return (
              <div key={m.id} style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '4px 0', fontSize: 'var(--text-sm)' }}>
                <div style={{ width: 22, height: 22, borderRadius: '50%', background: 'linear-gradient(135deg, var(--accent), var(--purple))', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 10, color: 'var(--on-accent-light)', fontWeight: 800 }}>
                  {(m.user_name || '?').charAt(0).toUpperCase()}
                </div>
                <span style={{ flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                  {m.user_name || 'Cliente'}{isMe && ' (yo)'}
                </span>
                {(m.role && m.role !== 'member') && <span style={{ fontSize: 10, color: 'var(--text-3)' }}>{m.role}</span>}
                {m.is_admin && <span style={{ fontSize: 10, color: 'var(--accent)' }}>admin</span>}
                {canRemove && (
                  <button aria-label={isMe ? 'Salir del grupo' : 'Quitar del grupo'}
                    onClick={async () => { if (await confirmar({ message: isMe ? '¿Salir del grupo?' : `¿Quitar a ${m.user_name}?`, danger: true, confirmLabel: isMe ? 'Salir' : 'Quitar' })) removeMember.mutate(m.user_id) }}
                    title={isMe ? 'Salir del grupo' : 'Quitar del grupo'}
                    style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--text-3)', padding: 2 }}
                  >
                    <X size={12} />
                  </button>
                )}
              </div>
            )
          })}
        </Section>
      )}
      {showAddMember && conv.kind === 'group' && (
        <AddGroupMembersModal
          conv={conv}
          existingUserIds={members.map(m => m.user_id).filter(Boolean)}
          onClose={() => setShowAddMember(false)}
          onAdded={() => {
            qc.invalidateQueries({ queryKey: ['collab-members', conv.id] })
            qc.invalidateQueries({ queryKey: ['collab-conversations'] })
            setShowAddMember(false)
            toast.success('Miembros añadidos')
          }}
        />
      )}
      <Section title={`Anclados (${pins.length})`}>
        {pins.length === 0 ? <Empty>{traducir('chat.ningun_mensaje_anclado')}</Empty> : pins.map(p => (
          <div key={p.id} style={styles.contextRowMutedText}>
            <Pin size={10} /> {p.preview}
          </div>
        ))}
      </Section>
      <Section title={`Llamadas (${calls.length})`}>
        {calls.length === 0 ? <Empty>{traducir('chat.sin_llamadas')}</Empty> : calls.slice(0, 5).map(c => (
          <div key={c.id} style={styles.contextRowMutedText}>
            {c.kind === 'video' ? <Video size={11} /> : <Phone size={11} />} {c.duration_seconds}s — {c.status}
            {c.has_summary && <Sparkles size={10} style={{ marginLeft: 4, color: 'var(--warning)' }} />}
          </div>
        ))}
      </Section>
      <Section title={traducir('chat.proximos_eventos_7d')}>
        {!calendar?.events?.length ? (
          <Empty>{calendar?.providers_connected?.length ? 'Sin eventos próximos' : 'Conecta Google/M365 para ver tu calendario'}</Empty>
        ) : calendar.events.slice(0, 6).map(ev => (
          <a key={ev.id} href={ev.link || '#'} target="_blank" rel="noopener noreferrer"
            style={{ display: 'block', padding: '6px 0', fontSize: 'var(--text-xs)', color: 'var(--text-2)', textDecoration: 'none' }}>
            <div style={{ color: 'var(--text-1)', fontWeight: 600 }}>{ev.title}</div>
            <div className="u-text3">
              {ev.source === 'google' ? '🅖' : '🅜'} {ev.start ? new Date(ev.start).toLocaleString(localeActivo(), { weekday: 'short', hour: '2-digit', minute: '2-digit' }) : ''}
            </div>
          </a>
        ))}
      </Section>
      <Section title={`Decisiones (${decisions.length})`}>
        {decisions.length === 0 ? <Empty>{traducir('chat.sin_decisiones_registradas')}</Empty> : decisions.slice(0, 5).map(d => (
          <div key={d.id} style={styles.contextRowMutedText}>
            <FileSignature size={10} style={{ marginRight: 4 }} /> {(d.text || '').slice(0, 100)}
          </div>
        ))}
      </Section>
    </div>
  )
}

function Section({ title, children, right }: { title: ReactNode; children?: ReactNode; right?: ReactNode }) {
  return (
    <div style={{ marginBottom: 18 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
        <div style={{ flex: 1, fontSize: 'var(--text-2xs, 10px)', fontWeight: 700, color: 'var(--text-3)', textTransform: 'uppercase', letterSpacing: '0.08em' }}>{title}</div>
        {right}
      </div>
      {children}
    </div>
  )
}

function Empty({ children }: { children?: ReactNode }) { return <div style={{ fontSize: 'var(--text-xs)', color: 'var(--text-4)' }}>{children}</div> }

function Loader() {
  return <div style={{ display: 'flex', justifyContent: 'center', padding: 24 }}>
    <div style={{ width: 24, height: 24, borderRadius: '50%', border: '3px solid var(--surface-4)', borderTopColor: 'var(--accent)', animation: 'spin 0.7s linear infinite' }} />
    <style>{`@keyframes spin { to { transform: rotate(360deg) } }`}</style>
  </div>
}

// ── Activity tab ────────────────────────────────────────────────────────────
function ActivityList({ narrow = false }: { narrow?: boolean }) {
  const { t: traducir } = useAppLang()
  const { data: notifs = [] } = useQuery({ queryKey: ['collab-notifications'], queryFn: () => collabApi.listNotifications(false) as Promise<CollabNotification[]> })
  const { data: mentions = [] } = useQuery({ queryKey: ['collab-mentions'], queryFn: () => collabApi.listMyMentions() as Promise<PreviewRow[]> })
  const { data: saved = [] } = useQuery({ queryKey: ['collab-saved'], queryFn: () => collabApi.listSaved() as Promise<PreviewRow[]> })
  return (
    <div style={{ ...(narrow ? { flex: 1, minWidth: 0 } : { width: 360 }), background: 'var(--surface-1)', borderRight: '1px solid var(--surface-4)', overflowY: 'auto', padding: 16 }}>
      <Section title={`Notificaciones (${notifs.length})`}>
        {notifs.length === 0 ? <Empty>{traducir('chat.sin_notificaciones')}</Empty> : notifs.slice(0, 30).map(n => (
          <div key={n.id} style={{ padding: '8px 10px', borderRadius: 'var(--radius-sm)', background: n.is_read ? 'transparent' : 'var(--accent-muted)', marginBottom: 4 }}>
            <div style={{ fontSize: 'var(--text-sm)', fontWeight: 600 }}>{n.title}</div>
            <div className="u-text3-xs">{(n.body || '').slice(0, 80)}</div>
          </div>
        ))}
      </Section>
      <Section title={`Menciones (${mentions.length})`}>
        {mentions.length === 0 ? <Empty>{traducir('chat.sin_menciones')}</Empty> : mentions.slice(0, 20).map(m => (
          <div key={m.id} style={styles.contextRowMutedText}>
            <AtSign size={10} /> {m.preview}
          </div>
        ))}
      </Section>
      <Section title={`Guardados (${saved.length})`}>
        {saved.length === 0 ? <Empty>{traducir('chat.sin_guardados')}</Empty> : saved.slice(0, 20).map(s => (
          <div key={s.id} style={styles.contextRowMutedText}>
            <Bookmark size={10} /> {s.preview}
          </div>
        ))}
      </Section>
    </div>
  )
}

// ── Admin panel placeholder (legacy CTA) ────────────────────────────────────
