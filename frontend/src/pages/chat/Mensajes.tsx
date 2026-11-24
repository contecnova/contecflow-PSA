/**
 * Burbujas de mensaje, tarjetas, adjuntos, menús de mención/comandos y panel de hilo.
 * Troceado de ChatPage.tsx sin cambio de comportamiento (23-11-2026).
 */
import { type CSSProperties, type ReactNode, useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  MessageSquare,
  Pin,
  Bookmark,
  Send,
  Video,
  Sparkles,
  Megaphone,
  Zap,
  Bot,
  FileText,
  AlertCircle,
  Trash2,
  Pencil,
  X,
  Headphones,
  ListChecks,
  FileSignature,
  Languages,
  BarChart3,
  type LucideIcon,
} from 'lucide-react'
import { collabApi } from '../../services/collaborationApi'
import { useAppLang } from '../../i18n/AppLangContext'
import { fmtDateTime, fmtNumber } from '../../utils/helpers'
import { sanitizeUrl } from '../../utils/security'
import { Button, Pulsable, Input, IconButton, TextoConEnlaces } from '../../components/ui'
import TextoTraducido from '../../components/traduccion/TextoTraducido'
import { useTraducirBajoDemanda } from '../../components/traduccion/useTraducirBajoDemanda'
import { POLL_FREQUENT_MS, STALE_1_HOUR_MS } from '../../constants/timings'
import { CHAT_THREAD_MESSAGES_LIMIT } from '../../constants/pagination'
import {
  type Attachment,
  type BotMeta,
  type Conv,
  fmtHora,
  IconBtn,
  type Msg,
  type Reaction,
  type SlashCommand,
  type UserLike,
} from './compartido'
import { LinkedEntityChips } from './BusquedaYEnlaces'

// ── Message bubble with hover actions ────────────────────────────────────────
export function MessageBubble({ msg, compact, isMine, onReact, onEdit, onDelete, onPin, onSave, onReplyThread, onLink }: {
  msg: Msg; compact?: boolean; isMine: boolean; onReact: (emoji: string) => void;
  onEdit: () => void; onDelete: () => void; onPin: () => void; onSave: () => void;
  onReplyThread: () => void; onLink: (kind: string) => void
}) {
  const { t: traducir } = useAppLang()
  const [showActions, setShowActions] = useState(false)
  const author = msg.author_name || (msg.bot_id ? traducir('chat.bot') : traducir('chat.user'))
  const deleted = msg.status === 'deleted'
  // Traducción en tiempo real (16-11-2026): «Traducir» bajo demanda al idioma de la interfaz.
  const trad = useTraducirBajoDemanda(msg.id)
  const puedeTraducir = trad.disponible && !deleted && !!msg.body?.trim()

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
            <time className="u-text3-xs" dateTime={msg.sent_at} title={fmtDateTime(msg.sent_at)}>
              {fmtHora(msg.sent_at)}
            </time>
            {msg.is_pinned && <Pin size={11} className="u-warning" role="img" aria-label={traducir('chat.pinned')} />}
            {msg.edited_at && <span className="u-text3-xs">{traducir('chat.edited')}</span>}
          </div>
        )}
        {msg.reply_to && (
          // 24-11-2026 (chat del portal): la cita del mensaje al que responde.
          <blockquote className="chat-msg__cita">
            <span className="u-sm-700">{msg.reply_to.author_name || traducir('chat.user')}</span>{' '}
            <span className="u-text2-sm">{msg.reply_to.is_deleted ? traducir('chat.mensaje_eliminado') : msg.reply_to.body}</span>
          </blockquote>
        )}
        {trad.traduccion || trad.cargando ? (
          <TextoTraducido original={msg.body || ''} traduccion={trad.traduccion} cargando={trad.cargando} className="chat-msg__body" />
        ) : (
          // 24-11-2026: enlaces seguros (http/https/www, saneados, `noopener`).
          <TextoConEnlaces texto={msg.body || ''} className="chat-msg__body" />
        )}
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
              <Pulsable type="button" key={emoji} onClick={() => onReact(emoji)} className="chat-reaction"
                aria-label={traducir('chat.reaction_label', { emoji, count: users.length })}>{emoji} <span>{users.length}</span></Pulsable>
            ))}
          </div>
        )}
      </div>

      {showActions && !deleted && (
        <div className="chat-msg__actions" role="toolbar" aria-label={traducir('chat.message_actions')}>
          {['👍', '❤️', '😂', '🎉'].map(e => (
            <Pulsable type="button" key={e} onClick={() => onReact(e)} className="chat-msg__emoji" aria-label={traducir('chat.react_with', { emoji: e })}>{e}</Pulsable>
          ))}
          <IconBtn onClick={onReplyThread} title={traducir('chat.reply_in_thread')}><MessageSquare size={13} aria-hidden="true" /></IconBtn>
          {puedeTraducir && (
            <IconBtn onClick={trad.traduccion ? trad.quitar : trad.pedir}
              title={trad.traduccion ? traducir('traduccion_admin.chat_quitar_traduccion') : traducir('traduccion_admin.chat_traducir')}>
              <Languages size={13} aria-hidden="true" />
            </IconBtn>
          )}
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
  if (meta.card === 'meeting_minutes') return <TarjetaDeActa meta={meta} />
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

/** Acta del asistente de reuniones al colgar una llamada (19-11-2026): botón «Ver acta». */
function TarjetaDeActa({ meta }: { meta: BotMeta }) {
  const { t: traducir } = useAppLang()
  const navigate = useNavigate()
  const destino = meta.link || (meta.meeting_id ? `/meetings-ai?meeting=${meta.meeting_id}` : '')
  return (
    <div className="chat-card chat-card--acta">
      <div className="chat-card__icon" aria-hidden="true"><FileText size={15} /></div>
      <div className="u-min0">
        <div className="chat-card__title">{traducir('chat.card_acta_de_reunion')}</div>
        <div className="u-text2-sm">{traducir('chat.card_actions_detected', { count: meta.actions?.length || 0 })}</div>
        {destino && (
          <Button size="xs" variant="secondary" icon={<FileText size={12} />} onClick={() => navigate(destino)}>
            {traducir('chat.card_ver_acta')}
          </Button>
        )}
      </div>
    </div>
  )
}

function PollCard({ meta }: { meta: BotMeta }) {
  return (
    <div className="chat-poll">
      <div className="chat-poll__q"><BarChart3 size={14} aria-hidden="true" /> {meta.question}</div>
      {(meta.options || []).map((o, i) => (
        <Pulsable type="button" key={i} className="chat-poll__opt">{o.label} <span className="u-text3-xs">({o.votes || 0})</span></Pulsable>
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
    collabApi.getAttachment(att.id).then(d => { if (!cancel) setMeta(d) }).catch(() => { /* accesorio: sin detalle el adjunto se pinta con los datos que ya trae el mensaje */ })
    return () => { cancel = true }
  }, [att.id, att.download_url, att.is_quarantined])

  const isImage = (meta.mime_type || '').startsWith('image/')
  // 23-11-2026 (04b): las URL que llegan del servidor se sanean antes de ir a un href/src.
  const downloadUrl = meta.download_url ? sanitizeUrl(meta.download_url) : meta.download_url
  const previewUrl = (meta.preview_url ? sanitizeUrl(meta.preview_url) : null) || (isImage ? downloadUrl : null)

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

// ── Mention menu ────────────────────────────────────────────────────────────
export function MentionMenu({ items, onPick }: { items: UserLike[]; onPick: (it: UserLike) => void }) {
  return (
    <div className="chat-popover" role="listbox">
      {items.map((it, i) => (
        <Pulsable type="button" role="option" aria-selected={false} key={i} onClick={() => onPick(it)} className="chat-popover-item">
          <span className="chat-avatar chat-avatar--26" aria-hidden="true">{(it.full_name || it.username || '?').charAt(0).toUpperCase()}</span>
          <div className="u-flex1-min0">
            <div className="chat-popover-item__name">
              {it.full_name}{it.is_group ? '' : ` (@${it.username || ''})`}
            </div>
            {it.email && <div className="u-text3-xs">{it.email}</div>}
          </div>
        </Pulsable>
      ))}
    </div>
  )
}

// ── Thread side panel ──────────────────────────────────────────────────────
export function ThreadPanel({ conv, rootId, onClose }: { conv: Conv; rootId: string; onClose: () => void }) {
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
        <IconButton variante="caja" onClick={onClose} ariaLabel={traducir('chat.close')}><X size={14} aria-hidden="true" /></IconButton>
      </div>
      <div className="chat-thread__body">
        {thread.length === 0 && <div className="u-text3-xs">{traducir('chat.sin_respuestas_todavia')}</div>}
        {thread.map(m => (
          <div key={m.id} className="u-mb-14">
            <div className="u-text3-xs">{m.author_name || traducir('chat.user')} · <time dateTime={m.sent_at} title={fmtDateTime(m.sent_at)}>{fmtHora(m.sent_at)}</time></div>
            <div className="chat-thread__msg">{m.body}</div>
          </div>
        ))}
      </div>
      <div className="chat-thread__foot">
        <Input aria-label={traducir('chat.reply_in_thread_placeholder')} value={reply} onChange={e => setReply(e.target.value)}
          onKeyDown={e => e.key === 'Enter' && reply.trim() && send.mutate()}
          placeholder={traducir('chat.reply_in_thread_placeholder')}
          className="u-flex1-min0" inputClassName="chat-thread__input" />
        <IconBtn onClick={() => reply.trim() && send.mutate()} title={traducir('chat.send')} variant="primary"><Send size={14} aria-hidden="true" /></IconBtn>
      </div>
    </aside>
  )
}

// ── Slash menu ──────────────────────────────────────────────────────────────
export function SlashMenu({ draft, onPick }: { draft: string; onPick: (cmd: string) => void }) {
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
        <Pulsable type="button" role="option" aria-selected={false} key={i} onClick={() => onPick(c.name.replace('/', ''))} className="chat-popover-item">
          <span className="ds-codigo chat-slash-cmd">{c.name}</span>
          <span className="u-text3-xs">{c.desc}</span>
        </Pulsable>
      ))}
    </div>
  )
}
