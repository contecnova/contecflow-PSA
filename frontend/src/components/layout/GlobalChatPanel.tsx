import React, { useEffect, useMemo, useRef, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { MessageSquare, Search, Send, X, ExternalLink, Plus, User, Minus, Maximize2, Volume2, VolumeX } from 'lucide-react'
import { collabApi } from '../../services/collaborationApi'
import { useToast } from '../../context/ToastContext'
import { useAuth } from '../../context/AuthContext'
import { useChatRealtime } from '../../context/ChatRealtimeContext'
import { useAppLang } from '../../i18n/AppLangContext'
import { ANIMATION_FAST_MS, NOTIFICATION_BEEP_MS, POLL_ACTIVE_CHAT_MS, POLL_FREQUENT_MS, STALE_DEFAULT_MS, TYPING_SWEEP_PANEL_MS } from '../../constants/timings'
import { CHAT_MESSAGES_PAGE_SIZE, MENTION_SUGGESTIONS_COMPACT_LIMIT } from '../../constants/pagination'
import './GlobalChatPanel.css'

const LS_MIN_KEY = 'chat_global_minimized'
const LS_LAST_CONV_KEY = 'chat_global_last_conversation'
const LS_SOUND_KEY = 'chat_global_sound_enabled'


// TODO type: chat conversation payload — needs shared type from collabApi
interface Conversation {
  id: string
  title?: string
  kind?: 'direct' | 'channel' | string
  unread_count?: number
  unread?: number
  last_message_id?: string
  [key: string]: unknown
}

interface ChatMessage {
  id: string
  author_id?: string
  author_name?: string
  body?: string
  [key: string]: unknown
}

interface ConversationMember {
  user_id?: string
  user_name?: string
  full_name?: string
  [key: string]: unknown
}

interface NotificationRule {
  scope?: string
  target_id?: string | null
  notify_messages?: string
  do_not_disturb_from?: string | null
  do_not_disturb_to?: string | null
  [key: string]: unknown
}

type RulePayload = {
  scope: string
  notify_messages: string
  desktop_push: boolean
  email_digest: string
  do_not_disturb_from: string | null
  do_not_disturb_to: string | null
}

interface UserSuggestion {
  id: string
  full_name?: string
  username?: string
  [key: string]: unknown
}

interface ApiError {
  response?: { data?: { detail?: string } }
}

function labelForConversation(c: Conversation | null | undefined): string {
  if (!c) return 'Sin conversación'
  if (c.title) return c.title
  if (c.kind === 'direct') return 'Chat directo'
  if (c.kind === 'channel') return '# canal'
  return 'Conversación'
}

function safeLsGet(key: string, fallback: string): string {
  try {
    const raw = localStorage.getItem(key)
    return raw == null ? fallback : raw
  } catch {
    return fallback
  }
}

function safeLsSet(key: string, value: string): void {
  try {
    localStorage.setItem(key, value)
  } catch {
    // ignore localStorage errors
  }
}

interface Props {
  open: boolean
  unread?: number
  onClose: () => void
  onOpenFull?: () => void
}

export default function GlobalChatPanel({ open, unread = 0, onClose, onOpenFull }: Props) {
  const idCampo = React.useId()
  const { t } = useAppLang()
  const { user } = useAuth()
  const toast = useToast()
  const qc = useQueryClient()
  const realtime = useChatRealtime()

  const [isMobile, setIsMobile] = useState<boolean>(() => (typeof window !== 'undefined' ? window.innerWidth <= 860 : false))
  const [visible, setVisible] = useState<boolean>(false)
  const [minimized, setMinimized] = useState<boolean>(() => safeLsGet(LS_MIN_KEY, '0') === '1')

  const [filter, setFilter] = useState<string>('')
  const [activeConvId, setActiveConvId] = useState<string>(() => safeLsGet(LS_LAST_CONV_KEY, ''))
  const [draft, setDraft] = useState<string>('')
  const [newDirectOpen, setNewDirectOpen] = useState<boolean>(false)
  const [userSearch, setUserSearch] = useState<string>('')
  const [soundEnabled, setSoundEnabled] = useState<boolean>(() => safeLsGet(LS_SOUND_KEY, '1') !== '0')
  const [typingUsers, setTypingUsers] = useState<Record<string, number>>({})
  const [clearedUnreadMap, setClearedUnreadMap] = useState<Record<string, boolean>>({})
  const [panelBadgeVisible, setPanelBadgeVisible] = useState<boolean>(unread > 0)
  const [panelBadgeCount, setPanelBadgeCount] = useState<number>(unread)
  const [notifyMode, setNotifyMode] = useState<string>('all')
  const [dndEnabled, setDndEnabled] = useState<boolean>(false)
  const [stickToBottom, setStickToBottom] = useState<boolean>(true)
  const composerRef = useRef<HTMLTextAreaElement | null>(null)
  const messagesRef = useRef<HTMLDivElement | null>(null)

  const scrollToBottom = () => {
    const node = messagesRef.current
    if (!node) return
    node.scrollTop = node.scrollHeight
  }

  const onMessagesScroll = () => {
    const node = messagesRef.current
    if (!node) return
    const nearBottom = (node.scrollHeight - node.scrollTop - node.clientHeight) < 36
    setStickToBottom(nearBottom)
  }

  useEffect(() => {
    safeLsSet(LS_SOUND_KEY, soundEnabled ? '1' : '0')
  }, [soundEnabled])

  useEffect(() => {
    if (unread > 0) {
      setPanelBadgeCount(unread)
      setPanelBadgeVisible(true)
      return undefined
    }
    const id = setTimeout(() => setPanelBadgeVisible(false), ANIMATION_FAST_MS)
    return () => clearTimeout(id)
  }, [unread])

  useEffect(() => {
    if (!open) return
    if (!soundEnabled) return
    // Play a short beep when unread increases and panel is not in active reading mode.
    // This is best-effort and may be blocked by browser autoplay policies.
    const prev = Number(safeLsGet('chat_global_prev_unread', '0')) || 0
    if (unread > prev && (minimized || document.visibilityState !== 'visible')) {
      try {
        const Ctx = window.AudioContext || (window as unknown as { webkitAudioContext?: typeof AudioContext }).webkitAudioContext
        if (Ctx) {
          const ctx = new Ctx()
          const osc = ctx.createOscillator()
          const gain = ctx.createGain()
          osc.type = 'sine'
          osc.frequency.value = 880
          gain.gain.value = 0.04
          osc.connect(gain)
          gain.connect(ctx.destination)
          osc.start()
          setTimeout(() => {
            osc.stop()
            ctx.close().catch(() => {})
          }, NOTIFICATION_BEEP_MS)
        }
      } catch {
        // ignore audio failures
      }
    }
    safeLsSet('chat_global_prev_unread', String(unread))
  }, [open, unread, minimized, soundEnabled])

  useEffect(() => {
    if (!open) return undefined
    setVisible(false)
    const id = requestAnimationFrame(() => setVisible(true))
    return () => cancelAnimationFrame(id)
  }, [open])

  useEffect(() => {
    if (!open) return undefined
    const onResize = () => setIsMobile(window.innerWidth <= 860)
    window.addEventListener('resize', onResize)
    return () => window.removeEventListener('resize', onResize)
  }, [open])

  useEffect(() => {
    if (!open) return undefined
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose?.()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [open, onClose])

  useEffect(() => {
    if (!open) return
    safeLsSet(LS_MIN_KEY, minimized ? '1' : '0')
  }, [open, minimized])

  useEffect(() => {
    if (!open) return
    if (activeConvId) safeLsSet(LS_LAST_CONV_KEY, activeConvId)
  }, [open, activeConvId])

  const { data: conversations = [] } = useQuery<Conversation[]>({
    queryKey: ['collab-conversations'],
    queryFn: () => collabApi.listConversations() as Promise<Conversation[]>,
    enabled: open,
    refetchInterval: open ? POLL_FREQUENT_MS : false,
  })

  const visibleConversations = useMemo(() => {
    if (!filter.trim()) return conversations
    const q = filter.toLowerCase()
    return conversations.filter(c => labelForConversation(c).toLowerCase().includes(q))
  }, [conversations, filter])

  useEffect(() => {
    if (!open) return
    if (activeConvId && conversations.some(c => c.id === activeConvId)) return
    if (conversations.length > 0) setActiveConvId(conversations[0].id)
  }, [open, activeConvId, conversations])

  const activeConv = conversations.find(c => c.id === activeConvId) || null

  const markConversationAsReadNow = (conv: Conversation) => {
    if (!conv?.id) return
    const unreadCount = Number(conv.unread_count || conv.unread || 0)
    if (unreadCount <= 0) return

    setClearedUnreadMap(prev => ({ ...prev, [conv.id]: true }))
    realtime.consumeUnread(unreadCount)

    if (conv.last_message_id) {
      collabApi.markRead(conv.id, conv.last_message_id)
        .catch(() => {})
        .finally(() => {
          qc.invalidateQueries({ queryKey: ['collab-conversations'] })
          qc.invalidateQueries({ queryKey: ['collab-notifications'] })
          realtime.refresh()
        })
    } else {
      qc.invalidateQueries({ queryKey: ['collab-conversations'] })
      qc.invalidateQueries({ queryKey: ['collab-notifications'] })
      realtime.refresh()
    }
  }

  const { data: rules = [] } = useQuery<NotificationRule[]>({
    queryKey: ['collab-notification-rules'],
    queryFn: () => collabApi.listRules() as Promise<NotificationRule[]>,
    enabled: open,
    staleTime: STALE_DEFAULT_MS,
  })

  useEffect(() => {
    const globalRule = (rules || []).find(r => r.scope === 'global' && !r.target_id)
    if (!globalRule) {
      setNotifyMode('all')
      setDndEnabled(false)
      return
    }
    setNotifyMode(globalRule.notify_messages || 'all')
    setDndEnabled(Boolean(globalRule.do_not_disturb_from || globalRule.do_not_disturb_to))
  }, [rules])

  const saveRule = useMutation({
    mutationFn: (payload: RulePayload) => collabApi.upsertRule(payload),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['collab-notification-rules'] }),
    onError: () => toast.error(t('globalchat.no_se_pudieron_guardar_preferencias_de_notificacion')),
  })

  const updateNotifyMode = (value: string) => {
    setNotifyMode(value)
    saveRule.mutate({
      scope: 'global',
      notify_messages: value,
      desktop_push: true,
      email_digest: 'weekly',
      do_not_disturb_from: dndEnabled ? '22:00' : null,
      do_not_disturb_to: dndEnabled ? '08:00' : null,
    })
  }

  const updateDnd = (enabled: boolean) => {
    setDndEnabled(enabled)
    saveRule.mutate({
      scope: 'global',
      notify_messages: notifyMode,
      desktop_push: true,
      email_digest: 'weekly',
      do_not_disturb_from: enabled ? '22:00' : null,
      do_not_disturb_to: enabled ? '08:00' : null,
    })
  }

  const { data: messages = [] } = useQuery<ChatMessage[]>({
    queryKey: ['collab-messages', activeConvId],
    queryFn: () => collabApi.listMessages(activeConvId, { limit: CHAT_MESSAGES_PAGE_SIZE }) as Promise<ChatMessage[]>,
    enabled: open && !!activeConvId,
    refetchInterval: open && activeConvId ? POLL_ACTIVE_CHAT_MS : false,
  })

  const { data: members = [] } = useQuery<ConversationMember[]>({
    queryKey: ['collab-conversation-members', activeConvId],
    queryFn: () => collabApi.listConversationMembers(activeConvId) as Promise<ConversationMember[]>,
    enabled: open && !!activeConvId,
    staleTime: STALE_DEFAULT_MS,
  })

  const memberNames = useMemo(() => {
    const m: Record<string, string> = {}
    for (const item of members || []) {
      if (item?.user_id) m[item.user_id] = item.user_name || item.full_name || 'Usuario'
    }
    return m
  }, [members])

  useEffect(() => {
    const handler = (e: Event) => {
      const ev = (e as CustomEvent)?.detail || {}
      if (!ev?.conversation_id || ev.conversation_id !== activeConvId) return
      const uid = ev?.payload?.user_id
      const active = !!ev?.payload?.active
      if (!uid || uid === user?.id) return
      setTypingUsers(prev => {
        const next = { ...prev }
        if (active) next[uid] = Date.now()
        else delete next[uid]
        return next
      })
    }
    window.addEventListener('collab:typing', handler)
    return () => window.removeEventListener('collab:typing', handler)
  }, [activeConvId, user?.id])

  useEffect(() => {
    const id = setInterval(() => {
      const cutoff = Date.now() - 6000
      setTypingUsers(prev => {
        const next: Record<string, number> = {}
        for (const [uid, ts] of Object.entries(prev)) {
          if (ts > cutoff) next[uid] = ts
        }
        return next
      })
    }, TYPING_SWEEP_PANEL_MS)
    return () => clearInterval(id)
  }, [])

  const typingLabel = useMemo(() => {
    const ids = Object.keys(typingUsers)
    if (ids.length === 0) return ''
    const names = ids.map(uid => memberNames[uid] || 'Alguien').slice(0, 2)
    if (ids.length === 1) return `${names[0]} está escribiendo...`
    if (ids.length === 2) return `${names[0]} y ${names[1]} están escribiendo...`
    return 'Varias personas están escribiendo...'
  }, [typingUsers, memberNames])

  useEffect(() => {
    if (!open || minimized || !activeConvId || messages.length === 0) return
    const last = messages[messages.length - 1]
    collabApi.markRead(activeConvId, last.id).catch(() => {})
  }, [open, minimized, activeConvId, messages])

  useEffect(() => {
    if (!open || minimized) return
    if (!activeConvId) return
    setStickToBottom(true)
    const id = requestAnimationFrame(() => {
      scrollToBottom()
      composerRef.current?.focus()
    })
    return () => cancelAnimationFrame(id)
  }, [open, minimized, activeConvId])

  useEffect(() => {
    if (!open || minimized) return
    if (!stickToBottom) return
    const id = requestAnimationFrame(() => scrollToBottom())
    return () => cancelAnimationFrame(id)
  }, [open, minimized, stickToBottom, messages.length])

  useEffect(() => {
    if (!open || minimized) return
    realtime.clearUnread()
    collabApi.markAllRead()
      .catch(() => {})
      .finally(() => {
        qc.invalidateQueries({ queryKey: ['collab-notifications'] })
        qc.invalidateQueries({ queryKey: ['collab-conversations'] })
        realtime.refresh()
      })
  }, [open, minimized, qc, realtime])

  const send = useMutation({
    mutationFn: () => collabApi.sendMessage({ conversation_id: activeConvId, body: draft.trim() }),
    onSuccess: () => {
      setDraft('')
      qc.invalidateQueries({ queryKey: ['collab-messages', activeConvId] })
      qc.invalidateQueries({ queryKey: ['collab-conversations'] })
    },
    onError: (e: ApiError) => {
      toast.error(e?.response?.data?.detail || 'No se pudo enviar el mensaje')
    },
  })

  const { data: suggestions = { users: [] } } = useQuery<{ users: UserSuggestion[] }>({
    queryKey: ['chat-global-user-suggestions', userSearch],
    queryFn: () => collabApi.mentionSuggestions({ q: userSearch, limit: MENTION_SUGGESTIONS_COMPACT_LIMIT }) as Promise<{ users: UserSuggestion[] }>,
    enabled: open && newDirectOpen,
  })

  const openDirect = useMutation({
    mutationFn: (userId: string) => collabApi.openDirect({ user_id: userId }),
    onSuccess: (c: { conversation_id?: string; id?: string }) => {
      qc.invalidateQueries({ queryKey: ['collab-conversations'] })
      setNewDirectOpen(false)
      setUserSearch('')
      setActiveConvId(c.conversation_id || c.id || '')
      window.dispatchEvent(new CustomEvent('collab:resync'))
    },
    onError: (e: ApiError) => toast.error(e?.response?.data?.detail || 'No se pudo abrir el chat directo'),
  })

  if (!open) return null

  if (minimized) {
    return (
      <button className="glchpa-row-14 globalch-sx1"
        onClick={() => setMinimized(false)}
        aria-label={t('globalchat.abrir_chat')}
        title={t('globalchat.abrir_chat')}
        style={{ transform: visible ? 'translateY(0)' : 'translateY(10px)', opacity: visible ? 1 : 0 }}
      >
        <MessageSquare size={16} />
        <span className="u-sm-700">Chat</span>
        {panelBadgeVisible && (
          <span className="glchpa-row-15" style={{ opacity: unread > 0 ? 1 : 0, transform: unread > 0 ? 'scale(1)' : 'scale(0.9)' }}>{panelBadgeCount > 99 ? '99+' : panelBadgeCount}</span>
        )}
      </button>
    )
  }

  const panelStyle: React.CSSProperties = {
    position: 'fixed',
    top: isMobile ? 0 : 56,
    right: isMobile ? 0 : 12,
    left: isMobile ? 0 : 'auto',
    width: isMobile ? '100vw' : 460,
    maxWidth: isMobile ? '100vw' : 'calc(100vw - 24px)',
    height: isMobile ? '100dvh' : 'min(78vh, 780px)',
    zIndex: 115,
    background: 'var(--surface-1)',
    border: '1px solid var(--surface-4)',
    borderRadius: isMobile ? 0 : 12,
    boxShadow: isMobile ? 'none' : '0 14px 48px rgba(0,0,0,0.28)',
    overflow: 'hidden',
    display: 'flex',
    flexDirection: 'column',
    transform: visible ? 'translateY(0)' : (isMobile ? 'translateY(20px)' : 'translateY(-8px)'),
    opacity: visible ? 1 : 0,
    transition: 'transform .18s ease, opacity .18s ease',
  }

  return (
    <>
      <div className="glchpa-box-10"
        role="presentation"
        onMouseDown={(e) => {
          if (e.target === e.currentTarget) onClose?.()
        }}
        style={{ background: isMobile ? 'rgba(8, 12, 20, .48)' : 'rgba(8, 12, 20, .24)' }}
      />
      <div style={panelStyle}>
        <div className="glchpa-row-1">
          <div className="glchpa-row-2">
            <MessageSquare size={16} />
            <div className="glchpa-box-1">{t('globalchat.chat_interno')}</div>
          </div>
          <div className="glchpa-row-3">
              <button
                onClick={() => setSoundEnabled(v => !v)}
                title={soundEnabled ? 'Desactivar sonido' : 'Activar sonido'}
                className="glchpa-row-4"
              >
                {soundEnabled ? <Volume2 size={14} /> : <VolumeX size={14} />}
              </button>
            <button aria-label={t('globalchat.abrir_chat_completo')} onClick={onOpenFull} title={t('globalchat.abrir_chat_completo')} className="glchpa-row-4">
              <ExternalLink size={14} />
            </button>
            <button aria-label={t('globalchat.minimizar')} onClick={() => setMinimized(true)} title={t('globalchat.minimizar')} className="glchpa-row-4">
              <Minus size={14} />
            </button>
            <button aria-label={t('common.close')} onClick={onClose} title={t('common.close')} className="glchpa-row-4">
              <X size={14} />
            </button>
          </div>
        </div>

        <div className="glchpa-row-5">
          <div className="glchpa-box-2">
            <Search size={13} className="globalch-sx2" />
            <input aria-label={t('globalchat.buscar_conversacion')}
              value={filter}
              onChange={(e) => setFilter(e.target.value)}
              placeholder={t('globalchat.buscar_conversacion')}
              className="glchpa-fieldstyle2"
            />
          </div>
          <button aria-label={t('globalchat.nuevo_chat_directo')}
            onClick={() => setNewDirectOpen(v => !v)}
            title={t('globalchat.nuevo_chat_directo')}
            className="glchpa-row-6"
          >
            <Plus size={14} />
          </button>
        </div>

        <div className="glchpa-row-7">
          <label id={`${idCampo}-et1`} htmlFor={`${idCampo}-1`} className="u-text3-xs">{t('nav.notifications')}</label>
          <select id={`${idCampo}-1`} aria-labelledby={`${idCampo}-et1`}
            value={notifyMode}
            onChange={(e) => updateNotifyMode(e.target.value)}
            className="glchpa-fieldstyle3"
          >
            <option value="all">{t('globalchat.todas')}</option>
            <option value="mentions">{t('globalchat.solo_menciones')}</option>
            <option value="none">{t('globalchat.silencio')}</option>
          </select>
          <label className="glchpa-row-8">
            <input type="checkbox" aria-label={t('globalchat.no_molestar_22_00_08_00')} checked={dndEnabled} onChange={(e) => updateDnd(e.target.checked)} />
            {t('globalchat.no_molestar_22_00_08_00')}
          </label>
        </div>

        {newDirectOpen && (
          <div className="glchpa-box-3">
            <input aria-label={t('globalchat.buscar_persona')}
              value={userSearch}
              onChange={(e) => setUserSearch(e.target.value)}
              placeholder={t('globalchat.buscar_persona')}
              className="glchpa-fieldstyle"
            />
            <div className="glchpa-stack-1">
              {(suggestions.users || []).slice(0, 8).map(u => (
                <button
                  key={u.id}
                  onClick={() => openDirect.mutate(u.id)}
                  className="glchpa-row-9"
                >
                  <User size={13} />
                  <span>{u.full_name || u.username || 'Usuario'}</span>
                </button>
              ))}
              {(suggestions.users || []).length === 0 && (
                <div className="glchpa-box-4">{t('globalchat.sin_resultados')}</div>
              )}
            </div>
          </div>
        )}

        <div className="glchpa-box-11" style={{ display: isMobile ? 'grid' : 'grid', gridTemplateColumns: isMobile ? '1fr' : '170px 1fr', gridTemplateRows: isMobile ? '160px 1fr' : '1fr' }}>
          <div className="glchpa-box-12" style={{ borderRight: isMobile ? 'none' : '1px solid var(--surface-4)', borderBottom: isMobile ? '1px solid var(--surface-4)' : 'none' }}>
            {visibleConversations.map(c => {
              const active = c.id === activeConvId
              const rawUnread = Number(c.unread_count || c.unread || 0)
              const convUnread = (active || clearedUnreadMap[c.id]) ? 0 : rawUnread
              return (
                <button className="glchpa-box-13"
                  key={c.id}
                  onClick={() => {
                    setActiveConvId(c.id)
                    markConversationAsReadNow(c)
                  }}
                  style={{ background: active ? 'var(--accent-muted)' : 'transparent', color: active ? 'var(--accent)' : 'var(--text-2)' }}
                >
                  <div className="glchpa-box-5">{labelForConversation(c)}</div>
                  <div className="glchpa-row-10">
                    <span>{c.kind === 'channel' ? 'Canal' : c.kind === 'group' ? 'Grupo' : 'Directo'}</span>
                    {convUnread > 0 && (
                      <span className="glchpa-row-11">
                        {convUnread > 99 ? '99+' : convUnread}
                      </span>
                    )}
                  </div>
                </button>
              )
            })}
            {visibleConversations.length === 0 && (
              <div className="glchpa-box-6">{t('globalchat.no_hay_conversaciones')}</div>
            )}
          </div>

          <div className="glchpa-stack-2">
            <div className="glchpa-row-12">
              {labelForConversation(activeConv)}
              <span className="glchpa-box-7"><Maximize2 size={12} /></span>
            </div>

            <div ref={messagesRef} onScroll={onMessagesScroll} className="glchpa-stack-3">
              {messages.map(m => {
                const mine = !!user?.id && m.author_id === user.id
                return (
                  <div className="glchpa-box-14" key={m.id} style={{ alignSelf: mine ? 'flex-end' : 'flex-start' }}>
                    <div className="glchpa-box-8">
                      {m.author_name || 'Usuario'}
                    </div>
                    <div className="glchpa-box-15" style={{ background: mine ? 'var(--accent-muted)' : 'var(--surface-2)' }}>
                      {m.body || ''}
                    </div>
                  </div>
                )
              })}
              {activeConvId && messages.length === 0 && (
                <div className="u-text3-xs">{t('globalchat.sin_mensajes_todavia')}</div>
              )}
              {!activeConvId && (
                <div className="u-text3-xs">{t('globalchat.selecciona_una_conversacion')}</div>
              )}
            </div>

            <div className="glchpa-row-13">
              {typingLabel && (
                <div className="glchpa-box-9">
                  {typingLabel}
                </div>
              )}
              <textarea
                ref={composerRef}
                aria-label={activeConvId ? 'Escribe un mensaje...' : 'Selecciona una conversación'}
                value={draft}
                onChange={(e) => setDraft(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' && !e.shiftKey) {
                    e.preventDefault()
                    if (activeConvId && draft.trim() && !send.isPending) send.mutate()
                  }
                }}
                placeholder={activeConvId ? 'Escribe un mensaje...' : 'Selecciona una conversación'}
                disabled={!activeConvId}
                rows={2}
                className="glchpa-fieldstyle4"
              />
              <button className="glchpa-box-16"
                onClick={() => send.mutate()}
                disabled={!activeConvId || !draft.trim() || send.isPending}
                style={{ cursor: !activeConvId || !draft.trim() || send.isPending ? 'not-allowed' : 'pointer', opacity: !activeConvId || !draft.trim() || send.isPending ? 0.5 : 1 }}
              >
                <Send size={14} />
              </button>
            </div>
          </div>
        </div>
      </div>
    </>
  )
}
