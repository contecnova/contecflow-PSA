/**
 * Panel central de una conversación (mensajes, compositor, hilos).
 * Troceado de ChatPage.tsx sin cambio de comportamiento (23-11-2026).
 */
import {
  type ReactNode,
  type Dispatch,
  type SetStateAction,
  type DragEvent as ReactDragEvent,
  type ClipboardEvent as ReactClipboardEvent,
  useEffect,
  useReducer,
  useRef,
  useState,
} from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Hash, MessageSquare, Users, Send, Paperclip, AtSign, Phone, Video, MoreVertical, Pencil, X, ChevronLeft } from 'lucide-react'
import { useToast } from '../../context/ToastContext'
import { confirmar } from '../../context/ConfirmContext'
import { useChatRealtime } from '../../context/ChatRealtimeContext'
import { collabApi } from '../../services/collaborationApi'
import { useAppLang } from '../../i18n/AppLangContext'
import { extractErr } from '../../utils/helpers'
import { EmptyState, Pulsable, Textarea } from '../../components/ui'
import { POLL_FREQUENT_MS, TYPING_IDLE_MS, TYPING_SWEEP_MS } from '../../constants/timings'
import { CHAT_MESSAGES_PAGE_SIZE } from '../../constants/pagination'
import { type ChatBot, type Conv, IconBtn, type LinkPicker, type Msg, tituloConv, type TypingDetail, type UserLike } from './compartido'
import { AddGroupMembersModal, ConvHeaderMenu } from './ModalesDeConversacion'
import { Loader } from './PanelDeContexto'
import { MentionMenu, MessageBubble, SlashMenu, ThreadPanel } from './Mensajes'
import { LinkPickerModal } from './BusquedaYEnlaces'

// ── Conversation pane ────────────────────────────────────────────────────────
export function ConversationPane({ onBack, newConvAction, conv, currentUser, _bots, draft, setDraft, showSlashMenu, setShowSlashMenu }: {
  onBack?: () => void; newConvAction?: ReactNode; conv: Conv | null; currentUser: UserLike | null; _bots: ChatBot[]; draft: string;
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
    onError: (e: unknown) => toast.error(extractErr(e, traducir('chat.err_send'))),
  })

  const editMsg = useMutation({
    mutationFn: ({ id, body }: { id: string; body: string }) => collabApi.editMessage(id, { body }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['collab-messages', conv?.id] }),
    onError: (e: unknown) => toast.error(extractErr(e, traducir('chat.err_edit'))),
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
      collabApi.markRead(conv.id, last.id).catch(() => { /* accesorio: el «leído» se reintenta al abrir otro mensaje; no merece aviso */ })
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
      .catch(() => setMentionState(null)) // accesorio: sin sugerencias se cierra la lista; no se tapa el chat con avisos mientras se escribe
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
        <EmptyState icon={<MessageSquare size={28} />}
          title={traducir('chat.selecciona_una_conversacion')}
          description={traducir('chat.selecciona_desc')}
          action={newConvAction} />
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
      toast.error(extractErr(e, traducir('chat.err_upload', { name: file.name })))
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
      const claveCreds = `call_creds_${c.call_id}`
      sessionStorage.setItem(claveCreds, JSON.stringify({
        token: c.livekit_token,
        room: c.livekit_room,
        url: c.livekit_url,
        kind,
      }))
      const ventana = window.open(`/chat/call/${c.call_id}?kind=${kind}`, '_blank', 'width=1100,height=720')
      if (!ventana) {
        // 23-11-2026 (04 B10): el navegador bloqueó la ventana emergente; las credenciales de la llamada
        // no se dejan en sessionStorage sin dueño.
        try { sessionStorage.removeItem(claveCreds) } catch { /* accesorio: sessionStorage puede no estar disponible */ }
        toast.error(traducir('chat.err_call_popup'))
      }
    } catch (e) {
      toast.error(extractErr(e, traducir('chat.err_call')))
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
            <h2 className="chat-pane__title">{tituloConv(conv)}</h2>
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
        {!isLoading && messages.length === 0 && (
          <EmptyState icon={<MessageSquare size={28} />}
            title={traducir('chat.sin_mensajes')}
            description={traducir('chat.sin_mensajes_desc', { title: tituloConv(conv) })} />
        )}
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
            <Pulsable type="button" onClick={() => setActiveThreadRoot(null)} className="chat-icon-close chat-icon-close--end" aria-label={traducir('chat.cancel_reply')}>
              <X size={12} aria-hidden="true" />
            </Pulsable>
          </div>
        )}
        {editing && (
          <div className="chat-hint-bar">
            <Pencil size={12} aria-hidden="true" /> {traducir('chat.editing_message')}
            <Pulsable type="button" onClick={() => { setEditing(null); setDraft('') }} className="chat-icon-close chat-icon-close--end" aria-label={traducir('chat.cancel_edit')}>
              <X size={12} aria-hidden="true" />
            </Pulsable>
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
          <Textarea
            ref={composerRef}
            className="u-flex1-min0"
            data-chat-composer
            aria-label={traducir('chat.message_in', { title: tituloConv(conv) })}
            value={draft}
            onChange={e => setDraft(e.target.value)}
            onKeyDown={e => {
              if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault()
                handleSend()
              }
            }}
            onPaste={onPaste}
            placeholder={traducir('chat.composer_placeholder', { title: tituloConv(conv) })}
            rows={1}
            inputClassName="chat-composer__input"
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
