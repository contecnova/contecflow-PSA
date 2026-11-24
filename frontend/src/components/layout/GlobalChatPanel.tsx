import { Fragment, useEffect, useMemo, useRef, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { MessageSquare, X, ExternalLink, Plus, User, Minus, Volume2, VolumeX, Hash, Users } from 'lucide-react'
import { Buscador, Checkbox, Contador, EmptyState, IconButton, Pulsable, Select, TextoConEnlaces } from '../ui'
import { EditorDeChat, Escribiendo, FilaDeMensaje, SeparadorDeDia, cambiaDeDia } from '../chat'
import { collabApi } from '../../services/collaborationApi'
import { useToast } from '../../context/ToastContext'
import { useAuth } from '../../context/AuthContext'
import { useChatRealtime } from '../../context/ChatRealtimeContext'
import { useAppLang } from '../../i18n/AppLangContext'
import { NOTIFICATION_BEEP_MS, POLL_ACTIVE_CHAT_MS, POLL_FREQUENT_MS, STALE_DEFAULT_MS, TYPING_SWEEP_PANEL_MS } from '../../constants/timings'
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
  /** El serializador manda `user_id`; `author_id` queda por compatibilidad. */
  user_id?: string | null
  author_id?: string
  author_name?: string
  body?: string
  sent_at?: string | null
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

type Traductor = (clave: string, params?: Record<string, string | number>) => string

/** Nombre visible de la conversación. El backend titula los canales "# nombre";
 *  el «#» ya lo pone el icono, así que se quita del texto (antes salía «# # General»). */
function labelForConversation(c: Conversation | null | undefined, t: Traductor): string {
  if (!c) return t('globalchat.sin_conversacion')
  const titulo = (c.title || '').replace(/^#\s*/, '').trim()
  if (titulo) return titulo
  if (c.kind === 'direct') return t('chat.tab_direct')
  if (c.kind === 'channel') return t('chat.tab_channel')
  return t('chat.conversacion')
}

function IconoConversacion({ kind }: { kind?: string }) {
  if (kind === 'channel') return <Hash size={13} aria-hidden="true" />
  if (kind === 'group') return <Users size={13} aria-hidden="true" />
  return <MessageSquare size={13} aria-hidden="true" />
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
    return conversations.filter(c => labelForConversation(c, t).toLowerCase().includes(q))
  }, [conversations, filter, t])

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
      if (item?.user_id) m[item.user_id] = item.user_name || item.full_name || t('chat.user')
    }
    return m
  }, [members, t])

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
    const names = ids.map(uid => memberNames[uid] || t('globalchat.alguien')).slice(0, 2)
    if (ids.length === 1) return t('globalchat.escribiendo_uno', { name: names[0] })
    if (ids.length === 2) return t('globalchat.escribiendo_dos', { a: names[0], b: names[1] })
    return t('globalchat.escribiendo_varios')
  }, [typingUsers, memberNames, t])

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
      toast.error(e?.response?.data?.detail || t('globalchat.err_enviar'))
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
    onError: (e: ApiError) => toast.error(e?.response?.data?.detail || t('globalchat.err_abrir_directo')),
  })

  if (!open) return null

  if (minimized) {
    return (
      <Pulsable className={`glchpa-row-14 globalch-sx1 ${visible ? 'global-chat-panel-m1' : 'global-chat-panel-m2'}`}
        onClick={() => setMinimized(false)}
        aria-label={t('globalchat.abrir_chat')}
        title={t('globalchat.abrir_chat')}
      >
        <MessageSquare size={16} aria-hidden="true" />
        <span className="u-sm-700">{t('nav.chat')}</span>
        {/* 24-11-2026: el contador del kit. */}
        <Contador n={unread} tono="acento" />
      </Pulsable>
    )
  }

  return (
    <>
      <div className={`glchpa-box-10 ${isMobile ? 'global-chat-panel-m5' : 'global-chat-panel-m6'}`}
        role="presentation"
        onMouseDown={(e) => {
          if (e.target === e.currentTarget) onClose?.()
        }}
      />
      <div role="dialog" aria-label={t('globalchat.chat_interno')}
        className={`glchpa-panel${isMobile ? ' glchpa-panel--movil' : ''}${visible ? ' glchpa-panel--visible' : ''}`}>
        <div className="glchpa-row-1">
          <div className="glchpa-row-2">
            <MessageSquare size={16} aria-hidden="true" />
            <h2 className="glchpa-box-1">{t('globalchat.chat_interno')}</h2>
          </div>
          <div className="glchpa-row-3">
            <IconButton className="glchpa-row-4" onClick={() => setSoundEnabled(v => !v)}
              aria-pressed={soundEnabled}
              ariaLabel={soundEnabled ? t('globalchat.desactivar_sonido') : t('globalchat.activar_sonido')}>
              {soundEnabled ? <Volume2 size={14} aria-hidden="true" /> : <VolumeX size={14} aria-hidden="true" />}
            </IconButton>
            <IconButton className="glchpa-row-4" ariaLabel={t('globalchat.abrir_chat_completo')} onClick={onOpenFull}>
              <ExternalLink size={14} aria-hidden="true" />
            </IconButton>
            <IconButton className="glchpa-row-4" ariaLabel={t('globalchat.minimizar')} onClick={() => setMinimized(true)}>
              <Minus size={14} aria-hidden="true" />
            </IconButton>
            <IconButton className="glchpa-row-4" ariaLabel={t('common.close')} onClick={onClose}>
              <X size={14} aria-hidden="true" />
            </IconButton>
          </div>
        </div>

        <div className="glchpa-row-5">
          <Buscador className="glchpa-box-2" aria-label={t('globalchat.buscar_conversacion')} value={filter} onChange={setFilter} placeholder={t('globalchat.buscar_conversacion')} />
          <IconButton ariaLabel={t('globalchat.nuevo_chat_directo')}
            onClick={() => setNewDirectOpen(v => !v)}
            aria-expanded={newDirectOpen}
            className="glchpa-row-6"
          >
            <Plus size={14} aria-hidden="true" />
          </IconButton>
        </div>

        <div className="glchpa-row-7">
          <Select label={t('nav.notifications')} placeholder={false} tamano="sm"
            value={notifyMode}
            onChange={(e) => updateNotifyMode(e.target.value)}
          >
            <option value="all">{t('globalchat.todas')}</option>
            <option value="mentions">{t('globalchat.solo_menciones')}</option>
            <option value="none">{t('globalchat.silencio')}</option>
          </Select>
          <Checkbox className="glchpa-row-8" label={t('globalchat.no_molestar_22_00_08_00')} checked={dndEnabled} onChange={(marcado) => updateDnd(marcado)} />
        </div>

        {newDirectOpen && (
          <div className="glchpa-box-3">
            <Buscador aria-label={t('globalchat.buscar_persona')} value={userSearch} onChange={setUserSearch} placeholder={t('globalchat.buscar_persona')} />
            <div className="glchpa-stack-1">
              {(suggestions.users || []).slice(0, 8).map(u => (
                <Pulsable
                  key={u.id}
                  onClick={() => openDirect.mutate(u.id)}
                  className="glchpa-row-9"
                >
                  <User size={13} aria-hidden="true" />
                  <span className="glchpa-ellipsis">{u.full_name || u.username || t('chat.user')}</span>
                </Pulsable>
              ))}
              {(suggestions.users || []).length === 0 && (
                <div className="glchpa-box-4">{t('globalchat.sin_resultados')}</div>
              )}
            </div>
          </div>
        )}

        <div className={`glchpa-box-11 ${isMobile ? 'global-chat-panel-m7' : 'global-chat-panel-m8'}`}>
          <div className={`glchpa-box-12 ${isMobile ? 'global-chat-panel-m9' : 'global-chat-panel-m10'}`}>
            {visibleConversations.map(c => {
              const active = c.id === activeConvId
              const rawUnread = Number(c.unread_count || c.unread || 0)
              const convUnread = (active || clearedUnreadMap[c.id]) ? 0 : rawUnread
              return (
                <Pulsable className={`glchpa-box-13 ${active ? 'global-chat-panel-m11' : 'global-chat-panel-m12'}`}
                  key={c.id}
                  aria-current={active ? 'true' : undefined}
                  onClick={() => {
                    setActiveConvId(c.id)
                    markConversationAsReadNow(c)
                  }}
                >
                  <div className="glchpa-box-5"><IconoConversacion kind={c.kind} /><span className="glchpa-ellipsis">{labelForConversation(c, t)}</span></div>
                  <div className="glchpa-row-10">
                    <span>{t(c.kind === 'channel' ? 'chat.tab_channel' : c.kind === 'group' ? 'chat.tab_group' : 'chat.tab_direct')}</span>
                    <Contador n={convUnread} tono="acento" />
                  </div>
                </Pulsable>
              )
            })}
            {visibleConversations.length === 0 && (
              <div className="glchpa-box-6">{t('globalchat.no_hay_conversaciones')}</div>
            )}
          </div>

          <div className="glchpa-stack-2">
            <h3 className="glchpa-row-12">
              {activeConv && <IconoConversacion kind={activeConv.kind} />}
              <span className="glchpa-ellipsis">{labelForConversation(activeConv, t)}</span>
            </h3>

            <div ref={messagesRef} onScroll={onMessagesScroll} className="glchpa-stack-3">
              {/* 24-11-2026 (burbujas «como WhatsApp»): la fila de todos los chats; lo tuyo a la
                  derecha y lo de los demás a la izquierda, con separador de día. */}
              {messages.map((m, i) => {
                const mine = !!user?.id && (m.user_id ?? m.author_id) === user.id
                const autor = m.author_name || t('chat.user')
                const previo = messages[i - 1]
                const nuevoDia = cambiaDeDia(previo?.sent_at, m.sent_at)
                const quien = (x: ChatMessage) => x.user_id ?? x.author_id ?? x.author_name
                return (
                  <Fragment key={m.id}>
                    {nuevoDia && <SeparadorDeDia fecha={m.sent_at} />}
                    <FilaDeMensaje autor={autor} fecha={m.sent_at} propio={mine}
                      mostrarNombre={activeConv?.kind !== 'direct'}
                      compacto={!!previo && !nuevoDia && quien(previo) === quien(m)}
                      textos={{ mensajeDe: t('chat.message_from', { author: autor }) }}
                      cuerpo={<TextoConEnlaces texto={m.body || ''} className="chat-msg__body" />} />
                  </Fragment>
                )
              })}
              {activeConvId && messages.length === 0 && (
                <EmptyState icon={<MessageSquare size={28} />}
                  title={t('globalchat.sin_mensajes_todavia')}
                  description={t('globalchat.sin_mensajes_desc')} />
              )}
              {!activeConvId && (
                <EmptyState icon={<MessageSquare size={28} />}
                  title={conversations.length ? t('globalchat.selecciona_una_conversacion') : t('globalchat.no_hay_conversaciones')}
                  description={conversations.length ? undefined : t('globalchat.no_hay_conversaciones_desc')} />
              )}
            </div>

            <Escribiendo texto={typingLabel || null} />
            <EditorDeChat
              campoRef={composerRef}
              valor={draft}
              onCambiar={setDraft}
              onEnviar={() => { if (activeConvId && draft.trim() && !send.isPending) send.mutate() }}
              etiquetaCampo={activeConvId ? t('globalchat.escribe_mensaje') : t('globalchat.selecciona_una_conversacion')}
              placeholder={activeConvId ? t('globalchat.escribe_mensaje') : t('globalchat.selecciona_una_conversacion')}
              etiquetaEnviar={t('chat.send')}
              etiquetaEmoji={t('governedconversations.insertar_emoji')}
              desactivado={!activeConvId}
            />
          </div>
        </div>
      </div>
    </>
  )
}
