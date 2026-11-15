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
import { fmtDateTime, fmtNumber, localeActivo } from '../utils/helpers'
import useMediaQuery from '../hooks/useMediaQuery'
import { useDialogo } from '../components/ui'
import { POLL_DEFAULT_MS, POLL_FREQUENT_MS, POLL_SLOW_MS, PRESENCE_POLL_MS, STALE_1_HOUR_MS, STALE_5_MIN_MS, STALE_DEFAULT_MS, TYPING_IDLE_MS, TYPING_SWEEP_MS } from '../constants/timings'
import './ChatPage.css'
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
    <div className="chat-root">
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
  const { t: traducir } = useAppLang()
  const items = [
    { id: 'activity', label: traducir('chat.nav_activity'), icon: Bell, badge: unreadNotifs },
    { id: 'chats',    label: traducir('chat.nav_chat'),     icon: MessageSquare },
    { id: 'teams',    label: traducir('chat.nav_teams'),    icon: Users },
    { id: 'calls',    label: traducir('chat.nav_calls'),    icon: Phone },
  ]
  return (
    <nav className="chat-rail" aria-label={traducir('chat.nav_label')}>
      {items.map(it => {
        const Icon = it.icon
        const active = activeTab === it.id
        return (
          <button type="button" key={it.id} onClick={() => onTab(it.id)} title={it.label}
            className="chat-rail__btn" aria-current={active ? 'page' : undefined}>
            <Icon size={20} aria-hidden="true" />
            <span className="u-xs">{it.label}</span>
            {(it.badge ?? 0) > 0 && (
              <span className="chat-rail__badge" aria-label={traducir('chat.unread_count', { count: it.badge ?? 0 })}>{(it.badge ?? 0) > 99 ? '99+' : it.badge}</span>
            )}
          </button>
        )
      })}
    </nav>
  )
}

// ── Conversations sidebar (middle column) ────────────────────────────────────
function ConversationsList({ narrow = false, activeTab, conversations, teams, channels, presence, loading, activeConv, onSelect }: {
  narrow?: boolean; activeTab: string; conversations: Conv[]; teams: Team[]; channels: Channel[];
  presence: Presence[]; loading: boolean; activeConv: Conv | null; onSelect: (c: Conv) => void
}) {
  const { t: traducir } = useAppLang()
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
    <div className={`chat-list${narrow ? ' chat-list--narrow' : ''}`}>
      <div className="chat-list__search">
        <div className="chat-search-box">
          <Search size={14} className="chat-search-box__icon" aria-hidden="true" />
          <input aria-label={traducir('chat.search_placeholder')}
            type="search"
            value={filter} onChange={e => setFilter(e.target.value)}
            placeholder={traducir('chat.search_placeholder')}
            className="chat-search-box__input"
          />
        </div>
      </div>

      <div className="chat-list__scroll">
        {loading && <Loader />}

        {activeTab !== 'teams' && directs.length > 0 && (
          <SectionGroup title={traducir('chat.direct_chats')} count={directs.length}>
            {directs.filter(c => matches(c.title)).map(c => (
              <ConvRow key={c.id} c={c} active={activeConv?.id === c.id} onClick={() => onSelect(c)}
                presence={c.peer_user_id ? presenceMap[c.peer_user_id] : null} />
            ))}
          </SectionGroup>
        )}

        {activeTab !== 'teams' && groups.length > 0 && (
          <SectionGroup title={traducir('chat.groups')} count={groups.length}>
            {groups.filter(c => matches(c.title)).map(c => (
              <ConvRow key={c.id} c={c} active={activeConv?.id === c.id} onClick={() => onSelect(c)} />
            ))}
          </SectionGroup>
        )}

        <SectionGroup
          title={traducir('chat.nav_teams')}
          count={teams.length}
          collapsed={!openTeams}
          onToggle={() => setOpenTeams(o => !o)}
        >
          {openTeams && teams.filter(t => matches(t.name)).map(team => (
            <div key={team.id} className="chat-team">
              <div className="chat-team__name">
                <Users size={13} aria-hidden="true" /> {team.name}
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

      <div className="chat-list__foot">
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
      {onToggle ? (
        <button type="button" onClick={onToggle} aria-expanded={!collapsed} className="chat-section-btn chat-section-btn--toggle">
          {collapsed ? <ChevronRight size={11} aria-hidden="true" /> : <ChevronDown size={11} aria-hidden="true" />}
          {title} {count != null && <span className="chat-section-btn__count">({count})</span>}
        </button>
      ) : (
        <h3 className="chat-section-btn">
          {title} {count != null && <span className="chat-section-btn__count">({count})</span>}
        </h3>
      )}
      {!collapsed && children}
    </div>
  )
}

function ConvRow({ c, active, onClick, presence, indent }: {
  c: Conv; active: boolean; onClick: () => void; presence?: string | null; indent?: boolean
}) {
  const { t: traducir } = useAppLang()
  return (
    <button type="button" onClick={onClick} aria-current={active ? 'true' : undefined}
      className={`chat-conv-row${indent ? ' chat-conv-row--indent' : ''}`}>
      {c.kind === 'channel' && <Hash size={13} aria-hidden="true" />}
      {c.kind === 'direct'  && (
        <span className="chat-presence-wrap">
          <span className="chat-avatar" aria-hidden="true">{(c.title || '?').charAt(0).toUpperCase()}</span>
          {presence && presence !== 'offline' && (
            <span className={`chat-presence-dot chat-presence-dot--${presence}`} role="img" aria-label={traducir(`chat.presence_${presence}`, presence)} />
          )}
        </span>
      )}
      {c.kind === 'group' && <Users size={13} aria-hidden="true" />}
      <span className="chat-ellipsis">{c.title}</span>
    </button>
  )
}

function NewConversationButton({ onCreated }: { onCreated?: (c: Conv) => void }) {
  const { t: traducir } = useAppLang()
  const [open, setOpen] = useState(false)
  return (
    <>
      <button type="button" onClick={() => setOpen(true)} className="chat-new-btn">
        <Plus size={14} aria-hidden="true" /> {traducir('chat.nuevo')}
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
        if (!selectedUsers.length) throw new Error(traducir('chat.selecciona_un_usuario'))
        return await collabApi.openDirect({ user_id: selectedUsers[0].id })
      } else if (tab === 'group') {
        if (!selectedUsers.length) throw new Error(traducir('chat.err_min_one_member'))
        return await collabApi.createGroup({
          title: groupTitle.trim() || null,
          user_ids: selectedUsers.map(u => u.id),
        })
      } else {
        if (!channelName.trim()) throw new Error(traducir('chat.err_channel_name'))
        if (!selectedTeamId) throw new Error(traducir('chat.err_select_team'))
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
      toast.success(traducir(tab === 'direct' ? 'chat.chat_opened' : tab === 'group' ? 'chat.group_created' : 'chat.channel_created'))
    },
    onError: (e: ApiError) => toast.error(e.message || e?.response?.data?.detail || traducir('chat.error_generic')),
  })

  const dialogRef = useDialogo<HTMLDivElement>(true, onClose)
  const tituloId = `${idCampo}-titulo`
  return (
    <div role="presentation" onClick={onClose} className="chat-modal-overlay">
      <div ref={dialogRef} role="dialog" aria-modal="true" aria-labelledby={tituloId} tabIndex={-1}
        onClick={(e) => e.stopPropagation()}
        onKeyDown={(e) => { if (e.key === 'Escape') onClose() }}
        className="chat-modal">
        <div className="chat-modal__head">
          <h2 id={tituloId} className="u-md-700 chat-reset-h">{traducir('chat.nueva_conversacion')}</h2>
          <button type="button" onClick={onClose} className="chat-icon-close" aria-label={traducir('chat.close')}><X size={14} aria-hidden="true" /></button>
        </div>
        <div className="chat-modal-tabs" role="tablist">
          {[{ id: 'direct', label: traducir('chat.tab_direct'), icon: MessageSquare },
            { id: 'group', label: traducir('chat.tab_group'), icon: Users },
            { id: 'channel', label: traducir('chat.tab_channel'), icon: Hash }].map(t => {
            const Icon = t.icon; const active = tab === t.id
            return (
              <button type="button" role="tab" aria-selected={active} key={t.id} onClick={() => setTab(t.id)} className="chat-modal-tab"><Icon size={13} aria-hidden="true" /> {t.label}</button>
            )
          })}
        </div>
        <div className="chat-modal__body">
          {tab === 'group' && (
            <div className="u-mb-12">
              <label id={`${idCampo}-et1`} htmlFor={`${idCampo}-1`} className="chat-form-label">{traducir('chat.titulo_opcional')}</label>
              <input id={`${idCampo}-1`} aria-labelledby={`${idCampo}-et1`} value={form.groupTitle} onChange={(e) => updateForm({ groupTitle: e.target.value })} placeholder={traducir('chat.group_title_placeholder')}
                className="chat-input" />
            </div>
          )}
          {tab === 'channel' && (
            <>
              <div className="u-mb-12">
                <label id={`${idCampo}-et2`} htmlFor={`${idCampo}-2`} className="chat-form-label">{traducir('chat.name')}</label>
                <input id={`${idCampo}-2`} aria-labelledby={`${idCampo}-et2`} value={form.channelName} onChange={(e) => updateForm({ channelName: e.target.value })} placeholder={traducir('chat.channel_name_placeholder')} className="chat-input" />
              </div>
              <div className="chat-form-grid2">
                <div>
                  <label id={`${idCampo}-et3`} htmlFor={`${idCampo}-3`} className="chat-form-label">{traducir('chat.team')}</label>
                  <select id={`${idCampo}-3`} aria-labelledby={`${idCampo}-et3`} value={form.selectedTeamId} onChange={(e) => updateForm({ selectedTeamId: e.target.value })} className="chat-input">
                    {teams.map(t => <option key={t.id} value={t.id}>{t.name}</option>)}
                  </select>
                </div>
                <div>
                  <label id={`${idCampo}-et4`} htmlFor={`${idCampo}-4`} className="chat-form-label">{traducir('chat.type')}</label>
                  <select id={`${idCampo}-4`} aria-labelledby={`${idCampo}-et4`} value={form.channelType} onChange={(e) => updateForm({ channelType: e.target.value })} className="chat-input">
                    <option value="public">{traducir('chat.publico')}</option>
                    <option value="private">{traducir('chat.private')}</option>
                    <option value="announcement">{traducir('chat.announcements')}</option>
                  </select>
                </div>
              </div>
            </>
          )}
          {tab === 'direct' ? (
            <div className="chat-hint-xs">{traducir('chat.selecciona_un_usuario')}</div>
          ) : (
            <div className="chat-hint-xs">
              {traducir(tab === 'group' ? 'chat.anade_miembros_minimo' : 'chat.anade_miembros_opcional')}
            </div>
          )}
          <input aria-label={traducir('chat.search_users')} value={search} onChange={(e) => updateForm({ search: e.target.value })} placeholder={traducir('chat.search_users')}
            className="chat-input" autoFocus />
          {selectedUsers.length > 0 && (
            <div className="chat-chips">
              {selectedUsers.map(u => (
                <span key={u.id} className="chat-chip">
                  {u.full_name || u.username} <button type="button" onClick={() => toggleUser(u)} className="chat-chip__remove" aria-label={traducir('chat.remove_name', { name: u.full_name || u.username || '' })}><X size={11} aria-hidden="true" /></button>
                </span>
              ))}
            </div>
          )}
          <div className="chat-user-list">
            {((suggestions.users || []) as UserLike[]).map((u: UserLike) => {
              const sel = !!selectedUsers.find(x => x.id === u.id)
              return (
                <button type="button" key={u.id} aria-pressed={sel} onClick={() => {
                  if (tab === 'direct') {
                    updateForm({ selectedUsers: [u] })
                  } else {
                    toggleUser(u)
                  }
                }} className="chat-user-option">
                  <span className="chat-avatar chat-avatar--28" aria-hidden="true">{(u.full_name || u.username || '?').charAt(0).toUpperCase()}</span>
                  <div className="u-flex1-min0">
                    <div className="u-text1-sm-600">{u.full_name}</div>
                    <div className="u-text3-xs">{u.email}</div>
                  </div>
                  {sel && <span className="chat-check" aria-hidden="true">✓</span>}
                </button>
              )
            })}
          </div>
        </div>
        <div className="chat-modal__foot">
          <button type="button" onClick={onClose} className="chat-btn-ghost">{traducir('chat.cancel')}</button>
          <button type="button" onClick={() => submit.mutate()} disabled={submit.isPending} className="chat-btn-primary">{submit.isPending ? traducir('chat.creating') : traducir('chat.create')}</button>
        </div>
      </div>
    </div>
  )
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
    onError: (e: ApiError) => toast.error(e?.response?.data?.detail || traducir('chat.err_add_members')),
  })

  const togglePick = (u: UserLike) => {
    setPicked(prev => prev.find(x => x.id === u.id) ? prev.filter(x => x.id !== u.id) : [...prev, u])
  }

  const dialogRef = useDialogo<HTMLDivElement>(true, onClose)
  const tituloId = useId()
  return (
    <div role="presentation" onClick={onClose} className="chat-modal-overlay">
      <div ref={dialogRef} role="dialog" aria-modal="true" aria-labelledby={tituloId} tabIndex={-1}
        onClick={(e) => e.stopPropagation()}
        onKeyDown={(e) => { if (e.key === 'Escape') onClose() }}
        className="chat-addm"
      >
        <div className="u-row-between">
          <h2 id={tituloId} className="u-md-700 chat-reset-h">{traducir('chat.anadir_miembros_a')} {conv.title || traducir('chat.group_fallback')}</h2>
          <button type="button" onClick={onClose} className="chat-icon-close" aria-label={traducir('chat.close')}>
            <X size={16} aria-hidden="true" />
          </button>
        </div>
        <input
          autoFocus
          aria-label={traducir('chat.busca_por_nombre_o_email')}
          value={search}
          onChange={e => setSearch(e.target.value)}
          placeholder={traducir('chat.busca_por_nombre_o_email')}
          className="chat-input"
        />
        {picked.length > 0 && (
          <div className="u-wrap-6">
            {picked.map(u => (
              <span key={u.id} className="chat-addm__chip">
                {u.full_name || u.username}
                <button type="button" onClick={() => togglePick(u)} className="chat-addm__chip-x" aria-label={traducir('chat.remove_name', { name: u.full_name || u.username || '' })}>
                  <X size={11} aria-hidden="true" />
                </button>
              </span>
            ))}
          </div>
        )}
        <div className="chat-addm__list">
          {candidates.length === 0 ? (
            <div className="chat-addm__empty">
              {search ? traducir('chat.sin_resultados') : traducir('chat.start_typing_name')}
            </div>
          ) : candidates.map(u => {
            const isPicked = !!picked.find(x => x.id === u.id)
            return (
              <button type="button" key={u.id} onClick={() => togglePick(u)} aria-pressed={isPicked}
                className="chat-addm__option">
                <div className="chat-avatar chat-avatar--24" aria-hidden="true">
                  {(u.full_name || u.username || '?').charAt(0).toUpperCase()}
                </div>
                <span className="u-flex1">{u.full_name || u.username}</span>
                {isPicked && <span className="chat-check" aria-hidden="true">✓</span>}
              </button>
            )
          })}
        </div>
        <div className="u-actions-8">
          <button type="button" onClick={onClose} className="chat-btn-ghost chat-btn--sm">{traducir('chat.cancel')}</button>
          <button
            type="button"
            disabled={!picked.length || submit.isPending}
            onClick={() => submit.mutate()}
            className="chat-addm__submit">
            {submit.isPending ? traducir('chat.adding') : picked.length ? traducir('chat.add_n', { count: picked.length }) : traducir('chat.anadir')}
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
  const { t: traducir } = useAppLang()
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
      toast.success(traducir('chat.link_copied'))
    } catch {
      toast.error(traducir('chat.copy_failed'))
    }
    onClose()
  }

  const leaveGroup = useMutation({
    mutationFn: () => collabApi.removeConversationMember(conv.id, currentUser.id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['collab-conversations'] })
      toast.success(traducir('chat.left_group'))
      onClose()
    },
    onError: (e: ApiError) => toast.error(e?.response?.data?.detail || traducir('chat.error_generic')),
  })

  const item = (icon: ReactNode, label: string, onClick: () => void, danger = false) => (
    <button type="button" role="menuitem" onClick={onClick} className={`chat-menu__item${danger ? ' chat-menu__item--danger' : ''}`}>
      {icon}
      <span className="u-flex1">{label}</span>
    </button>
  )

  return (
    <div ref={ref} role="menu" className="chat-menu">
      {item(<LinkIcon size={14} aria-hidden="true" />, traducir('chat.copy_link'), copyLink)}
      {item(
        <BellOff size={14} aria-hidden="true" />,
        muted ? traducir('chat.unmute') : traducir('chat.mute'),
        () => upsertMute.mutate(!muted),
      )}
      {conv.kind === 'group' && (
        <>
          <div className="chat-menu__sep" role="separator" />
          {item(<UserPlus size={14} aria-hidden="true" />, traducir('chat.add_members_ellipsis'), onAddMembers)}
          {item(<LogOut size={14} aria-hidden="true" />, traducir('chat.leave_group'), async () => {
            if (await confirmar({ message: traducir('chat.leave_group_confirm'), danger: true, confirmLabel: traducir('chat.leave') })) leaveGroup.mutate()
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
    onError: (e: ApiError) => toast.error(e?.response?.data?.detail || traducir('chat.err_send')),
  })

  const editMsg = useMutation({
    mutationFn: ({ id, body }: { id: string; body: string }) => collabApi.editMessage(id, { body }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['collab-messages', conv?.id] }),
    onError: (e: ApiError) => toast.error(e?.response?.data?.detail || traducir('chat.err_edit')),
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
      <div className="chat-pane-empty">
        <MessageSquare size={48} aria-hidden="true" />
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
      toast.error(traducir('chat.file_too_big', { name: file.name, max: 500 }))
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
        toast.warning(traducir(result.av_status === 'infected' ? 'chat.file_blocked_av' : 'chat.file_blocked_dlp'))
      } else {
        toast.success(traducir('chat.file_uploaded'))
      }
      // Reset input value para permitir subir el mismo nombre dos veces
      if (fileRef.current) fileRef.current.value = ''
    } catch (e) {
      const detail = (e as ApiError)?.response?.data?.detail
      toast.error(typeof detail === 'string' ? detail : traducir('chat.err_upload', { name: file.name }))
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
      toast.error(traducir('chat.err_call'))
    }
  }

  return (
    <div
      role="region"
      aria-label={traducir('chat.conversacion')}
      className="chat-pane"
      onDragEnter={onDragEnter}
      onDragOver={onDragOver}
      onDragLeave={onDragLeave}
      onDrop={onDrop}
    >
      {isDragging && (
        <div className="chat-dropzone" aria-hidden="true">
          {traducir('chat.suelta_el_archivo_para_subirlo')}
        </div>
      )}
      {/* Header */}
      <div className={`chat-pane__head${onBack ? ' chat-pane__head--back' : ''}`}>
        <div className="chat-pane__title-wrap">
          {onBack && <IconBtn onClick={onBack} title={traducir('chat.back')}><ChevronLeft size={16} aria-hidden="true" /></IconBtn>}
          {conv.kind === 'channel' && <Hash size={18} aria-hidden="true" />}
          {conv.kind === 'direct' && <MessageSquare size={18} aria-hidden="true" />}
          {conv.kind === 'group' && <Users size={18} aria-hidden="true" />}
          <div className="u-min0">
            <h2 className="chat-pane__title">{conv.title}</h2>
            {conv.channel_type && <div className="u-text3-xs">{traducir('chat.channel_type', { type: traducir(`chat.channel_type_${conv.channel_type}`, conv.channel_type) })}</div>}
          </div>
        </div>
        <div className="chat-pane__actions">
          <IconBtn onClick={() => onCallStart('audio')} title={traducir('chat.llamada_de_voz')}><Phone size={15} aria-hidden="true" /></IconBtn>
          <IconBtn onClick={() => onCallStart('video')} title={traducir('chat.video_call')}><Video size={15} aria-hidden="true" /></IconBtn>
          <IconBtn onClick={() => setPanelUi({ headerMenuOpen: !headerMenuOpen })} title={traducir('chat.mas_acciones')} expanded={headerMenuOpen}><MoreVertical size={15} aria-hidden="true" /></IconBtn>
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
            toast.success(traducir('chat.members_added'))
          }}
        />
      )}

      {/* Messages */}
      <div className="chat-pane__messages" role="log" aria-live="polite" aria-label={traducir('chat.messages')}>
        {isLoading && <Loader />}
        {messages.map((m, i) => {
          const prev = messages[i - 1]
          const compact = prev && prev.user_id === m.user_id && (+new Date(m.sent_at) - +new Date(prev.sent_at)) < 5 * 60_000
          return (
            <MessageBubble key={m.id} msg={m} compact={compact}
              isMine={m.user_id === currentUser?.id}
              onReact={(emoji) => react.mutate({ id: m.id, emoji })}
              onEdit={() => { setEditing({ id: m.id, body: m.body || '' }); setDraft(m.body || ''); composerRef.current?.focus() }}
              onDelete={async () => { if (await confirmar({ message: traducir('chat.delete_message_confirm'), danger: true, confirmLabel: traducir('chat.delete') })) delMsg.mutate(m.id) }}
              onPin={() => collabApi.pinMessage(conv.id, m.id).then(() => qc.invalidateQueries({ queryKey: ['collab-messages', conv.id] }))}
              onSave={() => collabApi.saveMessage(m.id, undefined).then(() => toast.success(traducir('chat.saved')))}
              onReplyThread={() => setActiveThreadRoot(m.id)}
              onLink={(kind) => setPanelUi({ linkPicker: { messageId: m.id, kind } })}
            />
          )
        })}
        <div ref={messagesEndRef} />
      </div>

      {/* Typing indicator */}
      {Object.keys(typingUsers).length > 0 && (
        <div className="chat-typing" role="status">
          {Object.keys(typingUsers).length === 1 ? traducir('chat.typing_one') : traducir('chat.typing_many', { count: Object.keys(typingUsers).length })}
        </div>
      )}

      {/* Composer */}
      <div className="chat-composer">
        {showSlashMenu && (
          <SlashMenu draft={draft} onPick={(cmd) => setDraft(`/${cmd} `)} />
        )}
        {mentionState && mentionState.items?.length > 0 && (
          <MentionMenu items={mentionState.items} onPick={insertMention} />
        )}
        {activeThreadRoot && (
          <div className="chat-hint-bar">
            <MessageSquare size={12} aria-hidden="true" /> {traducir('chat.replying_in_thread')}
            <button type="button" onClick={() => setActiveThreadRoot(null)} className="chat-icon-close chat-icon-close--end" aria-label={traducir('chat.cancel_reply')}>
              <X size={12} aria-hidden="true" />
            </button>
          </div>
        )}
        {editing && (
          <div className="chat-hint-bar">
            <Pencil size={12} aria-hidden="true" /> {traducir('chat.editing_message')}
            <button type="button" onClick={() => { setEditing(null); setDraft('') }} className="chat-icon-close chat-icon-close--end" aria-label={traducir('chat.cancel_edit')}>
              <X size={12} aria-hidden="true" />
            </button>
          </div>
        )}
        <div className="chat-composer__box">
          {/* Patrón label+input: el click en el label abre el selector sin
              depender de programmatic .click() (más fiable cross-browser) */}
          <label title={traducir('chat.attach_file')} className="chat-attach">
            <Paperclip size={16} aria-hidden="true" />
            <input ref={fileRef} type="file" aria-label={traducir('chat.attach_file')}
              className="u-sr-only"
              onChange={e => {
                const f = e.target.files?.[0]
                if (f) handleFile(f)
              }} />
          </label>
          <textarea
            ref={composerRef}
            data-chat-composer
            aria-label={traducir('chat.message_in', { title: conv.title ?? '' })}
            value={draft}
            onChange={e => setDraft(e.target.value)}
            onKeyDown={e => {
              if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault()
                handleSend()
              }
            }}
            onPaste={onPaste}
            placeholder={traducir('chat.composer_placeholder', { title: conv.title ?? '' })}
            rows={1}
            className="chat-composer__input"
          />
          <IconBtn onClick={() => setDraft(d => d + '@')} title={traducir('chat.mention')}><AtSign size={16} aria-hidden="true" /></IconBtn>
          <IconBtn onClick={handleSend} title={traducir('chat.send')} variant="primary">
            <Send size={16} aria-hidden="true" />
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
            toast.success(traducir('chat.linked'))
          }}
        />
      )}
    </div>
  )
}

/** Botón de icono 32×32. `title` sirve también de nombre accesible. */
function IconBtn({ children, onClick, title, variant = 'ghost', expanded }: {
  children: ReactNode; onClick?: () => void; title?: string
  variant?: 'ghost' | 'primary' | 'danger'; expanded?: boolean
}) {
  return (
    <button type="button" onClick={onClick} title={title} aria-label={title}
      aria-expanded={expanded}
      className={`chat-icon-btn chat-icon-btn--${variant}`}
    >{children}</button>
  )
}

// ── Message bubble with hover actions ────────────────────────────────────────
function MessageBubble({ msg, compact, isMine, onReact, onEdit, onDelete, onPin, onSave, onReplyThread, onLink }: {
  msg: Msg; compact?: boolean; isMine: boolean; onReact: (emoji: string) => void;
  onEdit: () => void; onDelete: () => void; onPin: () => void; onSave: () => void;
  onReplyThread: () => void; onLink: (kind: string) => void
}) {
  const { t: traducir } = useAppLang()
  const [showActions, setShowActions] = useState(false)
  const author = msg.author_name || (msg.bot_id ? traducir('chat.bot') : traducir('chat.user'))
  const deleted = msg.status === 'deleted'

  return (
    <div
      role="article"
      aria-label={traducir('chat.message_from', { author })}
      onMouseEnter={() => setShowActions(true)}
      onMouseLeave={() => setShowActions(false)}
      onFocus={() => setShowActions(true)}
      onBlur={() => setShowActions(false)}
      className={`chat-msg${compact ? ' chat-msg--compact' : ''}${deleted ? ' chat-msg--deleted' : ''}`}
    >
      {!compact ? (
        <div className={`chat-msg__avatar${msg.bot_id ? ' chat-msg__avatar--bot' : ''}`} aria-hidden="true">
          {msg.bot_id ? <Bot size={16} /> : (author?.charAt(0)?.toUpperCase() || '?')}
        </div>
      ) : (
        <div className="chat-msg__avatar-gap" />
      )}
      <div className="u-flex1-min0">
        {!compact && (
          <div className="chat-msg__meta">
            <span className="u-sm-700">{author}</span>
            {msg.bot_id && <span className="chat-msg__bot-tag">{traducir('chat.bot_tag')}</span>}
            <time className="u-text3-xs" dateTime={msg.sent_at}>
              {new Date(msg.sent_at).toLocaleTimeString(localeActivo(), { hour: '2-digit', minute: '2-digit' })}
            </time>
            {msg.is_pinned && <Pin size={11} className="u-warning" role="img" aria-label={traducir('chat.pinned')} />}
            {msg.edited_at && <span className="u-text3-xs">{traducir('chat.edited')}</span>}
          </div>
        )}
        <div className="chat-msg__body">
          {msg.body}
        </div>
        {msg.metadata_json?.card && <BotCard meta={msg.metadata_json} />}
        {(msg.linked_task_id || msg.linked_ticket_id || msg.linked_deliverable_id || msg.linked_risk_id) && (
          <LinkedEntityChips msg={msg} />
        )}
        {msg.attachments?.length > 0 && (
          <div className="chat-msg__attachments">
            {msg.attachments.map(a => <AttachmentChip key={a.id} att={a} />)}
          </div>
        )}
        {msg.reactions?.length > 0 && (
          <div className="chat-msg__reactions">
            {Object.entries(groupReactions(msg.reactions)).map(([emoji, users]) => (
              <button type="button" key={emoji} onClick={() => onReact(emoji)} className="chat-reaction"
                aria-label={traducir('chat.reaction_label', { emoji, count: users.length })}>{emoji} <span>{users.length}</span></button>
            ))}
          </div>
        )}
      </div>

      {showActions && !deleted && (
        <div className="chat-msg__actions" role="toolbar" aria-label={traducir('chat.message_actions')}>
          {['👍', '❤️', '😂', '🎉'].map(e => (
            <button type="button" key={e} onClick={() => onReact(e)} className="chat-msg__emoji" aria-label={traducir('chat.react_with', { emoji: e })}>{e}</button>
          ))}
          <IconBtn onClick={onReplyThread} title={traducir('chat.reply_in_thread')}><MessageSquare size={13} aria-hidden="true" /></IconBtn>
          <IconBtn onClick={onPin} title={traducir('chat.pin')}><Pin size={13} aria-hidden="true" /></IconBtn>
          <IconBtn onClick={onSave} title={traducir('chat.save')}><Bookmark size={13} aria-hidden="true" /></IconBtn>
          <IconBtn onClick={() => onLink && onLink('task')} title={traducir('chat.link_task')}><ListChecks size={13} aria-hidden="true" /></IconBtn>
          <IconBtn onClick={() => onLink && onLink('ticket')} title={traducir('chat.link_ticket')}><Headphones size={13} aria-hidden="true" /></IconBtn>
          <IconBtn onClick={() => onLink && onLink('deliverable')} title={traducir('chat.link_deliverable')}><FileText size={13} aria-hidden="true" /></IconBtn>
          <IconBtn onClick={() => onLink && onLink('risk')} title={traducir('chat.link_risk')}><AlertCircle size={13} aria-hidden="true" /></IconBtn>
          {isMine && <IconBtn onClick={onEdit} title={traducir('chat.edit')}><Pencil size={13} aria-hidden="true" /></IconBtn>}
          {isMine && <IconBtn onClick={onDelete} title={traducir('chat.delete')} variant="danger"><Trash2 size={13} aria-hidden="true" /></IconBtn>}
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
  if (meta.card === 'task') return <Card icon={ListChecks} accent="var(--success)" title={traducir('chat.card_task_created')} body={`#${meta.task_id?.slice(0, 8) || ''}`} />
  if (meta.card === 'ticket' || meta.card === 'escalation') return <Card icon={Headphones} accent="var(--warning)" title={traducir('chat.ticket_de_soporte')} body={traducir('chat.card_ticket_body', { number: meta.ticket?.number || meta.ticket?.id?.slice(0, 8) || '', assignee: meta.ticket?.assignee || '' })} />
  if (meta.card === 'imputation') return <Card icon={Zap} accent="var(--accent)" title={traducir('chat.card_hours_logged', { hours: meta.hours ?? 0 })} body={traducir('chat.card_project', { id: meta.project_id?.slice(0, 8) || '?' })} />
  if (meta.card === 'risk') return <Card icon={AlertCircle} accent="var(--danger)" title={traducir('chat.card_risk_logged')} body={meta.title} />
  if (meta.card === 'decision') return <Card icon={FileSignature} accent="var(--purple)" title={traducir('chat.decision_registrada')} body={meta.text} />
  if (meta.card === 'poll') return <PollCard meta={meta} />
  if (meta.card === 'call') return <Card icon={Video} accent="var(--accent)" title={traducir('chat.card_call_started')} body={traducir('chat.card_room', { room: meta.room?.slice(-8) || '' })} />
  if (meta.card === 'call_summary') return <Card icon={Sparkles} accent="var(--accent)" title={traducir('chat.resumen_de_reunion')} body={traducir('chat.card_actions_detected', { count: meta.actions?.length || 0 })} />
  if (meta.card === 'answer') return <Card icon={Sparkles} accent="var(--accent)" title="Nexus IA" body={meta.source} />
  if (meta.card === 'webhook') return <Card icon={Megaphone} accent="var(--purple)" title={meta.source || traducir('chat.card_incoming_webhook')} body="" />
  return null
}

function Card({ icon: Icon, accent, title, body }: {
  icon: LucideIcon; accent: string; title: ReactNode; body: ReactNode
}) {
  return (
    <div className="chat-card" style={{ '--card-accent': accent } as CSSProperties}>
      <div className="chat-card__icon" aria-hidden="true"><Icon size={15} /></div>
      <div className="u-min0">
        <div className="chat-card__title">{title}</div>
        {body && <div className="u-text2-sm">{body}</div>}
      </div>
    </div>
  )
}

function PollCard({ meta }: { meta: BotMeta }) {
  return (
    <div className="chat-poll">
      <div className="chat-poll__q"><span aria-hidden="true">📊</span> {meta.question}</div>
      {(meta.options || []).map((o, i) => (
        <button type="button" key={i} className="chat-poll__opt">{o.label} <span className="u-text3-xs">({o.votes || 0})</span></button>
      ))}
    </div>
  )
}

// ── Attachment chip ────────────────────────────────────────────────────────
function AttachmentChip({ att }: { att: Attachment }) {
  const { t: traducir } = useAppLang()
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
      <div className="chat-att chat-att--quarantine">
        <AlertCircle size={13} aria-hidden="true" /> {att.name} · {traducir('chat.quarantine')}
      </div>
    )
  }

  if (isImage && previewUrl) {
    return (
      <a href={downloadUrl} target="_blank" rel="noopener noreferrer"
        className="chat-att-img">
        <img src={previewUrl} alt={att.name} loading="lazy" decoding="async" />
      </a>
    )
  }

  return (
    <a href={downloadUrl || '#'} target="_blank" rel="noopener noreferrer" className="chat-att">
      <FileText size={15} className="u-accent" aria-hidden="true" />
      <div className="u-flex1-min0">
        <div className="chat-att__name">{att.name}</div>
        <div className="u-text3">
          {att.size_bytes >= 1024 * 1024
            ? `${fmtNumber(att.size_bytes / (1024 * 1024), 1)} MB`
            : `${fmtNumber(Math.round(att.size_bytes / 1024), 0)} KB`}
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
    <div role="presentation" onClick={onClose} className="chat-modal-overlay chat-modal-overlay--top">
      <div ref={dialogRef} role="dialog" aria-modal="true" aria-label={traducir('chat.search_messages')} tabIndex={-1}
        onClick={(e) => e.stopPropagation()}
        onKeyDown={(e) => { if (e.key === 'Escape') onClose() }}
        className="chat-modal chat-modal--wide">
        <div className="chat-search-head">
          <Search size={16} className="u-text3" aria-hidden="true" />
          <input type="search" aria-label={traducir('chat.search_messages_placeholder')} value={q} onChange={(e) => setQ(e.target.value)} autoFocus
            placeholder={traducir('chat.search_messages_placeholder')}
            className="chat-search-head__input" />
          <kbd className="chat-kbd">Esc</kbd>
        </div>
        <div className="chat-search-results" aria-live="polite">
          {q.trim().length < 2 && (
            <div className="chat-search-msg chat-search-msg--hint">
              {traducir('chat.escribe_al_menos_2_caracteres_soporta_operadores')} <code>from:juan</code> · <code>in:#general</code> · <code>before:2026-05-01</code> · <code>has:link</code> · <code>is:pinned</code> · <code>type:bot</code>
            </div>
          )}
          {isFetching && <div className="chat-search-msg">{traducir('chat.searching')}</div>}
          {!isFetching && q.trim().length >= 2 && hits.length === 0 && (
            <div className="chat-search-msg">{traducir('chat.sin_resultados')}</div>
          )}
          {hits.map((h) => (
            <button type="button" key={h.id} onClick={() => onJump(h.conversation_id)} className="chat-search-hit">
              <div className="chat-search-hit__snippet">{h.snippet}</div>
              <div className="u-text3-xs">
                {h.sent_at ? fmtDateTime(h.sent_at) : ''}
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
  const { t: traducir } = useAppLang()
  const chips: Array<{ icon: LucideIcon; label: string; href: string; color: string }> = []
  if (msg.linked_task_id) chips.push({ icon: ListChecks, label: traducir('chat.entity_task'), href: `/tasks?id=${msg.linked_task_id}`, color: 'var(--success)' })
  if (msg.linked_ticket_id) chips.push({ icon: Headphones, label: traducir('chat.entity_ticket'), href: `/service-desk?id=${msg.linked_ticket_id}`, color: 'var(--warning)' })
  if (msg.linked_deliverable_id) chips.push({ icon: FileText, label: traducir('chat.entity_deliverable'), href: `/deliverables?id=${msg.linked_deliverable_id}`, color: 'var(--accent)' })
  if (msg.linked_risk_id) chips.push({ icon: AlertCircle, label: traducir('chat.entity_risk'), href: `/risks?id=${msg.linked_risk_id}`, color: 'var(--danger)' })
  if (!chips.length) return null
  return (
    <div className="chat-linked">
      {chips.map((c, i) => (
        <a key={i} href={c.href} target="_blank" rel="noopener noreferrer"
          className="chat-linked__chip" style={{ '--chip-color': c.color } as CSSProperties}>
          <c.icon size={11} aria-hidden="true" /> {c.label}
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
  const tituloId = useId()
  return (
    <div role="presentation" onClick={onClose} className="chat-modal-overlay">
      <div ref={dialogRef} role="dialog" aria-modal="true" aria-labelledby={tituloId} tabIndex={-1}
        onClick={(e) => e.stopPropagation()}
        onKeyDown={(e) => { if (e.key === 'Escape') onClose() }}
        className="chat-linkpick">
        <div className="chat-linkpick__head">
          <h2 id={tituloId} className="u-md-700 chat-reset-h">
            {traducir('chat.link_to', { entity: traducir(`chat.entity_${kind}_lower`, kind) })}
          </h2>
          <button type="button" onClick={onClose} className="chat-icon-close" aria-label={traducir('chat.close')}>
            <X size={14} aria-hidden="true" />
          </button>
        </div>
        <input type="search" aria-label={traducir('chat.search_placeholder')} value={q} onChange={(e) => setQ(e.target.value)} placeholder={traducir('chat.search_placeholder')} autoFocus
          className="chat-input chat-input--lg" />
        <div className="chat-linkpick__list">
          {items.length === 0 && <div className="chat-linkpick__empty">{traducir('chat.sin_resultados')}</div>}
          {items.map((it) => (
            <button type="button" key={it.id} onClick={() => link.mutate(it.id)} className="chat-linkpick__item">
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
    <div className="chat-popover" role="listbox">
      {items.map((it, i) => (
        <button type="button" role="option" aria-selected={false} key={i} onClick={() => onPick(it)} className="chat-popover-item">
          <span className="chat-avatar chat-avatar--26" aria-hidden="true">{(it.full_name || it.username || '?').charAt(0).toUpperCase()}</span>
          <div className="u-flex1-min0">
            <div className="chat-popover-item__name">
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
    <aside className="chat-thread" aria-label={traducir('chat.thread')}>
      <div className="chat-thread__head">
        <h2 className="u-sm-700 chat-reset-h">{traducir('chat.thread_replies', { count: thread.length })}</h2>
        <button type="button" onClick={onClose} className="chat-icon-close" aria-label={traducir('chat.close')}><X size={14} aria-hidden="true" /></button>
      </div>
      <div className="chat-thread__body">
        {thread.length === 0 && <div className="u-text3-xs">{traducir('chat.sin_respuestas_todavia')}</div>}
        {thread.map(m => (
          <div key={m.id} className="u-mb-14">
            <div className="u-text3-xs">{m.author_name || traducir('chat.user')} · {new Date(m.sent_at).toLocaleTimeString(localeActivo(), { hour: '2-digit', minute: '2-digit' })}</div>
            <div className="chat-thread__msg">{m.body}</div>
          </div>
        ))}
      </div>
      <div className="chat-thread__foot">
        <input aria-label={traducir('chat.reply_in_thread_placeholder')} value={reply} onChange={e => setReply(e.target.value)}
          onKeyDown={e => e.key === 'Enter' && reply.trim() && send.mutate()}
          placeholder={traducir('chat.reply_in_thread_placeholder')}
          className="chat-thread__input" />
        <IconBtn onClick={() => reply.trim() && send.mutate()} title={traducir('chat.send')} variant="primary"><Send size={14} aria-hidden="true" /></IconBtn>
      </div>
    </aside>
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
    <div className="chat-popover" role="listbox">
      {cmds.map((c, i) => (
        <button type="button" role="option" aria-selected={false} key={i} onClick={() => onPick(c.name.replace('/', ''))} className="chat-popover-item">
          <span className="chat-slash-cmd">{c.name}</span>
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
      toast.success(traducir('chat.member_removed'))
    },
    onError: (e: ApiError) => toast.error(e?.response?.data?.detail || traducir('chat.err_remove')),
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
    <aside className="chat-ctx" aria-label={traducir('chat.informacion')}>
      <Section title={traducir('chat.informacion')}>
        <div className="u-text2-sm">{traducir(conv.kind === 'channel' ? 'chat.tab_channel' : conv.kind === 'group' ? 'chat.tab_group' : 'chat.tab_direct')}</div>
      </Section>
      <Section title={traducir('chat.online_count', { count: onlineUsers.length })}>
        {onlineUsers.length === 0 ? <Empty>{traducir('chat.nobody_online')}</Empty> : onlineUsers.slice(0, 12).map(p => {
          const name = p.user_name || traducir('chat.user')
          return (
            <div key={p.user_id} className="chat-ctx__person">
              <span className="chat-presence-wrap">
                <span className="chat-avatar" aria-hidden="true">{name.charAt(0).toUpperCase()}</span>
                <span className={`chat-presence-dot chat-presence-dot--${p.status}`} role="img" aria-label={traducir(`chat.presence_${p.status}`, p.status)} />
              </span>
              <span className="chat-ctx__name">{name}</span>
              {p.is_in_call && <Phone size={10} className="u-accent" role="img" aria-label={traducir('chat.in_call')} />}
            </div>
          )
        })}
      </Section>
      {(members.length > 0 || conv.kind === 'group') && (
        <Section
          title={traducir('chat.members_count', { count: members.length })}
          right={conv.kind === 'group' ? (
            <button
              type="button"
              onClick={() => setShowAddMember(true)}
              title={traducir('chat.anadir_miembro')}
              className="chat-ctx__add"
            >
              <Plus size={11} aria-hidden="true" /> {traducir('chat.anadir')}
            </button>
          ) : null}
        >
          {members.slice(0, 12).map(m => {
            const isMe = m.user_id === me?.id
            const canRemove = conv.kind === 'group' && (isMe || members.find(mm => mm.user_id === me?.id)?.is_admin)
            return (
              <div key={m.id} className="chat-ctx__person chat-ctx__person--sm">
                <div className="chat-avatar" aria-hidden="true">
                  {(m.user_name || '?').charAt(0).toUpperCase()}
                </div>
                <span className="chat-ctx__name">
                  {m.user_name || traducir('chat.client')}{isMe && ` ${traducir('chat.me_suffix')}`}
                </span>
                {(m.role && m.role !== 'member') && <span className="chat-ctx__role">{traducir(`chat.role_${m.role}`, m.role)}</span>}
                {m.is_admin && <span className="chat-ctx__role chat-ctx__role--admin">{traducir('chat.admin')}</span>}
                {canRemove && (
                  <button type="button" aria-label={isMe ? traducir('chat.leave_group') : traducir('chat.remove_from_group')}
                    onClick={async () => { if (await confirmar({ message: isMe ? traducir('chat.leave_group_q') : traducir('chat.remove_member_q', { name: m.user_name ?? '' }), danger: true, confirmLabel: isMe ? traducir('chat.leave') : traducir('chat.remove') })) removeMember.mutate(m.user_id) }}
                    title={isMe ? traducir('chat.leave_group') : traducir('chat.remove_from_group')}
                    className="chat-ctx__remove"
                  >
                    <X size={12} aria-hidden="true" />
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
            toast.success(traducir('chat.members_added'))
          }}
        />
      )}
      <Section title={traducir('chat.pinned_count', { count: pins.length })}>
        {pins.length === 0 ? <Empty>{traducir('chat.ningun_mensaje_anclado')}</Empty> : pins.map(p => (
          <div key={p.id} className="chat-ctx-muted">
            <Pin size={10} aria-hidden="true" /> {p.preview}
          </div>
        ))}
      </Section>
      <Section title={traducir('chat.calls_count', { count: calls.length })}>
        {calls.length === 0 ? <Empty>{traducir('chat.sin_llamadas')}</Empty> : calls.slice(0, 5).map(c => (
          <div key={c.id} className="chat-ctx-muted">
            {c.kind === 'video'
              ? <Video size={11} role="img" aria-label={traducir('chat.video_call')} />
              : <Phone size={11} role="img" aria-label={traducir('chat.llamada_de_voz')} />} {traducir('chat.seconds', { count: fmtNumber(c.duration_seconds, 0) })} — {traducir(`chat.call_status_${c.status}`, c.status)}
            {c.has_summary && <Sparkles size={10} className="chat-ctx__summary" role="img" aria-label={traducir('chat.has_summary')} />}
          </div>
        ))}
      </Section>
      <Section title={traducir('chat.proximos_eventos_7d')}>
        {!calendar?.events?.length ? (
          <Empty>{calendar?.providers_connected?.length ? traducir('chat.no_upcoming_events') : traducir('chat.connect_calendar')}</Empty>
        ) : calendar.events.slice(0, 6).map(ev => (
          <a key={ev.id} href={ev.link || '#'} target="_blank" rel="noopener noreferrer"
            className="chat-ctx__event">
            <div className="chat-ctx__event-title">{ev.title}</div>
            <div className="u-text3">
              <span role="img" aria-label={ev.source === 'google' ? 'Google' : 'Microsoft 365'}>{ev.source === 'google' ? '🅖' : '🅜'}</span> {ev.start ? new Date(ev.start).toLocaleString(localeActivo(), { weekday: 'short', hour: '2-digit', minute: '2-digit' }) : ''}
            </div>
          </a>
        ))}
      </Section>
      <Section title={traducir('chat.decisions_count', { count: decisions.length })}>
        {decisions.length === 0 ? <Empty>{traducir('chat.sin_decisiones_registradas')}</Empty> : decisions.slice(0, 5).map(d => (
          <div key={d.id} className="chat-ctx-muted">
            <FileSignature size={10} className="chat-ctx__decision-icon" aria-hidden="true" /> {(d.text || '').slice(0, 100)}
          </div>
        ))}
      </Section>
    </aside>
  )
}

function Section({ title, children, right }: { title: ReactNode; children?: ReactNode; right?: ReactNode }) {
  return (
    <section className="chat-sec">
      <div className="chat-sec__head">
        <h3 className="chat-sec__title">{title}</h3>
        {right}
      </div>
      {children}
    </section>
  )
}

function Empty({ children }: { children?: ReactNode }) { return <div className="chat-empty">{children}</div> }

function Loader() {
  const { t: traducir } = useAppLang()
  return <div className="chat-loader" role="status" aria-label={traducir('chat.loading')}>
    <div className="chat-loader__spin" />
  </div>
}

// ── Activity tab ────────────────────────────────────────────────────────────
function ActivityList({ narrow = false }: { narrow?: boolean }) {
  const { t: traducir } = useAppLang()
  const { data: notifs = [] } = useQuery({ queryKey: ['collab-notifications'], queryFn: () => collabApi.listNotifications(false) as Promise<CollabNotification[]> })
  const { data: mentions = [] } = useQuery({ queryKey: ['collab-mentions'], queryFn: () => collabApi.listMyMentions() as Promise<PreviewRow[]> })
  const { data: saved = [] } = useQuery({ queryKey: ['collab-saved'], queryFn: () => collabApi.listSaved() as Promise<PreviewRow[]> })
  return (
    <div className={`chat-activity${narrow ? ' chat-activity--narrow' : ''}`}>
      <Section title={traducir('chat.notifications_count', { count: notifs.length })}>
        {notifs.length === 0 ? <Empty>{traducir('chat.sin_notificaciones')}</Empty> : notifs.slice(0, 30).map(n => (
          <div key={n.id} className={`chat-notif${n.is_read ? '' : ' chat-notif--unread'}`}>
            <div className="chat-notif__title">{n.title}</div>
            <div className="u-text3-xs">{(n.body || '').slice(0, 80)}</div>
          </div>
        ))}
      </Section>
      <Section title={traducir('chat.mentions_count', { count: mentions.length })}>
        {mentions.length === 0 ? <Empty>{traducir('chat.sin_menciones')}</Empty> : mentions.slice(0, 20).map(m => (
          <div key={m.id} className="chat-ctx-muted">
            <AtSign size={10} aria-hidden="true" /> {m.preview}
          </div>
        ))}
      </Section>
      <Section title={traducir('chat.saved_count', { count: saved.length })}>
        {saved.length === 0 ? <Empty>{traducir('chat.sin_guardados')}</Empty> : saved.slice(0, 20).map(s => (
          <div key={s.id} className="chat-ctx-muted">
            <Bookmark size={10} aria-hidden="true" /> {s.preview}
          </div>
        ))}
      </Section>
    </div>
  )
}

// ── Admin panel placeholder (legacy CTA) ────────────────────────────────────
