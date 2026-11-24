// Piezas de la bandeja de conversaciones gobernadas (item, burbuja, redactor y modal de alta). 23-11-2026: troceado de GovernedConversations sin cambio de comportamiento.
import { type CSSProperties, useEffect, useRef, useState, useId } from 'react'
import { fmtDateTime } from '../../utils/helpers'
import { useDialogo, Button, Checkbox, GrupoDeOpciones, IconButton, Pulsable, REACCIONES_RAPIDAS, Select, SelectorDeEmoji, Input, Textarea, TextoConEnlaces } from '../ui'
import { Check, CheckCheck, History, Paperclip, Pencil, Reply, Trash2, X, Send } from 'lucide-react'
import type { PortalAjustesDelChat } from '../../services/api/tipos-alm'
import AdjuntoDelChat from './AdjuntoDelChat'
import type { ChatDelPortalApi } from './chatDelPortalApi'
import StatusBadge from '../ui/StatusBadge'
import { type Conversation, GRC_LABEL, type Message, type Mode, type ProjectOption, SOURCE_KEY, TOPIC_OPTIONS, type UserOption, etiquetaDeTema, useTextoConversacion } from './GovernedConversationsComun'

interface ConversationListItemProps {
  conversation: Conversation
  selected: boolean
  onSelect: (id: string) => void
  mode: Mode
}

export function ConversationListItem({ conversation, selected, onSelect, mode }: ConversationListItemProps) {
  const t = useTextoConversacion(mode)
  const unread = mode === 'team' ? conversation.unread_for_team : conversation.unread_for_client
  const lastPreview = conversation.last_message?.body || conversation.title
  return (
    <Pulsable className={`goveconv-box-13 governed-sx1 governed-conversations-e1 ${selected ? 'governed-conversations-m2' : 'governed-conversations-m3'}`}
      onClick={() => onSelect(conversation.id)}
      style={{ '--governed-conversations-border': `1px solid ${selected ? 'var(--accent)' : 'var(--surface-4)'}` } as CSSProperties}
    >
      <div className="goveconv-row-1">
        <div className="goveconv-txt-1">{conversation.title || t('governedconversations.sin_titulo')}</div>
        <div className="goveconv-txt-2">{fmtDateTime(conversation.last_message_at || conversation.created_at)}</div>
      </div>
      <div className="goveconv-row-2">
        <StatusBadge color={conversation.source === 'legacy_client_message' ? 'var(--warning)' : 'var(--accent)'}>{SOURCE_KEY[conversation.source] ? t(SOURCE_KEY[conversation.source]) : conversation.source}</StatusBadge>
        {conversation.pending_review_count > 0 && <StatusBadge color="var(--warning)">{conversation.pending_review_count} {t('governedconversations.revision')}</StatusBadge>}
        {conversation.is_sla_breached && <StatusBadge color="var(--danger)">{t('governedconversations.sla_vencido')}</StatusBadge>}
        {unread > 0 && <StatusBadge color="var(--danger)">{unread} {t('governedconversations.sin_leer')}</StatusBadge>}
      </div>
      <div className="goveconv-txt-3">{lastPreview ? String(lastPreview).slice(0, 120) : t('governedconversations.sin_mensajes')}</div>
    </Pulsable>
  )
}

interface MessageBubbleProps {
  message: Message
  mode: Mode
  onReview: (message: Message, decision: 'approved' | 'rejected') => void
  /** 24-11-2026: chat del portal completo. */
  conversationId?: string
  api?: ChatDelPortalApi
  /** El mensaje es de quien mira (puede editarlo o borrarlo). */
  isMine?: boolean
  /** Ids de quien mira (para marcar sus reacciones). */
  viewerUserId?: string | null
  viewerClientId?: string | null
  onReply?: (message: Message) => void
  onEdit?: (message: Message) => void
  onDelete?: (message: Message) => void
  onReact?: (message: Message, emoji: string) => void
  onHistory?: (message: Message) => void
  onError?: (e: unknown) => void
}

function agruparReacciones(message: Message, viewerUserId?: string | null, viewerClientId?: string | null) {
  const grupos: Record<string, { n: number; mia: boolean }> = {}
  for (const r of message.reactions || []) {
    const g = grupos[r.emoji] || (grupos[r.emoji] = { n: 0, mia: false })
    g.n += 1
    if ((viewerUserId && r.user_id === viewerUserId) || (viewerClientId && r.client_user_id === viewerClientId)) g.mia = true
  }
  return Object.entries(grupos)
}

export function MessageBubble({ message, mode, onReview, conversationId, api, isMine, viewerUserId, viewerClientId, onReply, onEdit, onDelete, onReact, onHistory, onError }: MessageBubbleProps) {
  const t = useTextoConversacion(mode)
  const grcCfg = GRC_LABEL[message.grc_status]
  const grc = grcCfg ? { text: t(grcCfg.text), color: grcCfg.color } : { text: message.grc_status, color: 'var(--text-2)' }
  const alignSelf = message.sender_type === 'client' ? 'flex-start' : 'flex-end'
  const bubbleBg = message.sender_type === 'client' ? 'var(--surface-1)' : 'var(--accent-muted)'
  const borderColor = message.grc_status === 'pending_review' ? 'var(--warning-border)' : 'var(--surface-4)'
  const borrado = !!message.is_deleted
  const nativo = message.source !== 'legacy_client_message'
  const interactivo = nativo && !borrado && !!api && !!conversationId
  const reacciones = agruparReacciones(message, viewerUserId, viewerClientId)
  return (
    <div className="goveconv-stack-1 governed-conversations-e4" style={{ '--governed-conversations-align-items': alignSelf } as CSSProperties}>
      <div role="article" aria-label={t('governedconversations.mensaje_de', { name: message.sender_name })}
        className={`goveconv-box-14 governed-sx2 governed-conversations-e5 chat-portal-burbuja${borrado ? ' chat-portal-burbuja--borrada' : ''}`}
        style={{ '--governed-conversations-background': bubbleBg, '--governed-conversations-border': `1px solid ${borderColor}` } as CSSProperties}>
        <div className="goveconv-row-1">
          <div className="u-sm-700">{message.sender_name}</div>
          <div className="u-text3-2xs">
            {fmtDateTime(message.created_at)}
            {message.edited_at && !borrado && <span className="chat-portal-editado"> · {t('governedconversations.editado')}</span>}
          </div>
        </div>
        <div className="goveconv-row-2">
          <StatusBadge color={message.sender_type === 'client' ? 'var(--warning)' : 'var(--accent)'}>{t(message.sender_type === 'client' ? 'governedconversations.remitente_cliente' : 'governedconversations.remitente_equipo')}</StatusBadge>
          <StatusBadge color={grc.color}>{grc.text}</StatusBadge>
          {message.is_internal_note && <StatusBadge color="var(--danger)">{t('governedconversations.interna')}</StatusBadge>}
          {message.is_redacted && <StatusBadge color="var(--accent)">{t('governedconversations.redactada')}</StatusBadge>}
          {message.source === 'legacy_client_message' && <StatusBadge color="var(--warning)">{t('governedconversations.origen_anterior')}</StatusBadge>}
        </div>
        {message.reply_to && (
          <blockquote className="chat-portal-cita">
            <span className="u-sm-700">{message.reply_to.sender_name}</span>
            <span className="chat-portal-cita__texto">{message.reply_to.is_deleted ? t('governedconversations.mensaje_borrado') : message.reply_to.body}</span>
          </blockquote>
        )}
        {borrado ? (
          <div className="chat-portal-borrado">{t('governedconversations.mensaje_borrado')}</div>
        ) : (
          (message.message_type !== 'attachment' || (message.body && !(message.attachments || []).some(a => a.name === message.body))) && (
            <TextoConEnlaces texto={message.body} className="goveconv-txt-4 chat-portal-texto" />
          )
        )}
        {!borrado && (message.attachments || []).length > 0 && api && conversationId && (
          <div className="chat-portal-adjuntos">
            {(message.attachments || []).map(a => (
              <AdjuntoDelChat key={a.id} adjunto={a} cargar={(id) => api.adjunto(conversationId, id)} t={t} onError={onError || (() => undefined)} />
            ))}
          </div>
        )}
        {message.moderation_notes && mode === 'team' && <div className="goveconv-box-1">{t('governedconversations.moderacion')} {message.moderation_notes}</div>}
        {reacciones.length > 0 && (
          <div className="chat-portal-reacciones">
            {reacciones.map(([emoji, g]) => (
              <Pulsable key={emoji} type="button" className={`chat-portal-reaccion${g.mia ? ' chat-portal-reaccion--mia' : ''}`}
                aria-pressed={g.mia} onClick={() => interactivo && onReact?.(message, emoji)}
                aria-label={t('governedconversations.reaccion_de', { emoji, n: g.n })}>{emoji} <span>{g.n}</span></Pulsable>
            ))}
          </div>
        )}
        {interactivo && (
          <div className="chat-portal-acciones" role="toolbar" aria-label={t('governedconversations.acciones_del_mensaje')}>
            {REACCIONES_RAPIDAS.slice(0, 4).map(e => (
              <Pulsable key={e} type="button" className="chat-portal-reaccion-rapida" onClick={() => onReact?.(message, e)}
                aria-label={t('governedconversations.reaccionar_con', { emoji: e })}>{e}</Pulsable>
            ))}
            <SelectorDeEmoji tamano="xs" ariaLabel={t('governedconversations.reaccionar')} onElegir={e => onReact?.(message, e)} />
            <IconButton variante="caja" tamano="xs" ariaLabel={t('governedconversations.responder')} onClick={() => onReply?.(message)}>
              <Reply size={13} aria-hidden="true" />
            </IconButton>
            {isMine && (message.message_type === 'text' || message.message_type === 'attachment') && (
              <>
                <IconButton variante="caja" tamano="xs" ariaLabel={t('governedconversations.editar')} onClick={() => onEdit?.(message)}>
                  <Pencil size={13} aria-hidden="true" />
                </IconButton>
                <IconButton variante="caja" tamano="xs" tono="peligro" ariaLabel={t('governedconversations.borrar')} onClick={() => onDelete?.(message)}>
                  <Trash2 size={13} aria-hidden="true" />
                </IconButton>
              </>
            )}
            {mode === 'team' && message.edited_at && onHistory && (
              <IconButton variante="caja" tamano="xs" ariaLabel={t('governedconversations.ver_historial')} onClick={() => onHistory(message)}>
                <History size={13} aria-hidden="true" />
              </IconButton>
            )}
          </div>
        )}
        {mode === 'team' && borrado && onHistory && (
          <div className="chat-portal-acciones">
            <IconButton variante="caja" tamano="xs" ariaLabel={t('governedconversations.ver_historial')} onClick={() => onHistory(message)}>
              <History size={13} aria-hidden="true" />
            </IconButton>
          </div>
        )}
        {isMine && !borrado && nativo && (
          <div className="chat-portal-estado" aria-live="polite">
            {message.read_at
              ? <><CheckCheck size={12} aria-hidden="true" /> {t('governedconversations.leido')}</>
              : <><Check size={12} aria-hidden="true" /> {t('governedconversations.enviado')}</>}
          </div>
        )}
        {mode === 'team' && message.grc_status === 'pending_review' && (
          <div className="goveconv-row-3">
            <Button size="sm" icon={<Check size={13} />} onClick={() => onReview(message, 'approved')}>
              {t('aus.aprobar')}
            </Button>
            <Button size="sm" variant="secondary" icon={<X size={13} />} onClick={() => onReview(message, 'rejected')}>
              {t('aus.rechazar')}
            </Button>
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
  /** 24-11-2026: chat del portal completo. */
  replyTo?: Message | null
  onCancelReply?: () => void
  editing?: Message | null
  onCancelEdit?: () => void
  onAttach?: (file: File) => void
  attaching?: boolean
  settings?: PortalAjustesDelChat | null
  onTyping?: () => void
}

export function ConversationComposer({ mode, value, onChange, onSend, sending, canInternalNotes, isInternalNote, onToggleInternalNote, disabled, replyTo, onCancelReply, editing, onCancelEdit, onAttach, attaching, settings, onTyping }: ConversationComposerProps) {
  const idCampo = useId()
  const t = useTextoConversacion(mode)
  const fichero = useRef<HTMLInputElement | null>(null)
  const adjuntos = !!settings?.attachments_enabled && !!onAttach && !editing
  const aceptados = (settings?.allowed_extensions || []).join(',')
  const escribir = (v: string) => {
    onChange(v)
    if (v.trim()) onTyping?.()
  }
  return (
    <div className="goveconv-cardstyle">
      {replyTo && !editing && (
        <div className="chat-portal-contexto" role="status">
          <Reply size={13} aria-hidden="true" />
          <span className="chat-portal-contexto__texto">{t('governedconversations.respondiendo_a', { name: replyTo.sender_name })}: {replyTo.is_deleted ? t('governedconversations.mensaje_borrado') : String(replyTo.body || '').slice(0, 120)}</span>
          <IconButton ariaLabel={t('governedconversations.cancelar_respuesta')} onClick={onCancelReply}><X size={13} aria-hidden="true" /></IconButton>
        </div>
      )}
      {editing && (
        <div className="chat-portal-contexto" role="status">
          <Pencil size={13} aria-hidden="true" />
          <span className="chat-portal-contexto__texto">{t('governedconversations.editando')}</span>
          <IconButton ariaLabel={t('governedconversations.cancelar_edicion')} onClick={onCancelEdit}><X size={13} aria-hidden="true" /></IconButton>
        </div>
      )}
      <Textarea label={t('mentions.reply')} id={`${idCampo}-1`} value={value} onChange={(event) => escribir(event.target.value)} rows={4}
        onKeyDown={(e) => { if (e.key === 'Enter' && (e.ctrlKey || e.metaKey) && value.trim() && !disabled) { e.preventDefault(); onSend() } }}
        placeholder={t(mode === 'team' ? 'governedconversations.ph_equipo' : 'governedconversations.ph_cliente')} />
      <div className="goveconv-row-4">
        <div className="chat-portal-herramientas">
          <SelectorDeEmoji ariaLabel={t('governedconversations.insertar_emoji')} disabled={disabled} onElegir={e => escribir(`${value}${e}`)} />
          {adjuntos && (
            <>
              <input ref={fichero} type="file" className="chat-portal-oculto" accept={aceptados} aria-hidden="true" tabIndex={-1}
                onChange={(e) => { const f = e.target.files?.[0]; if (f) onAttach?.(f); e.target.value = '' }} />
              <IconButton variante="caja" ariaLabel={t('governedconversations.adjuntar')} disabled={disabled || attaching} onClick={() => fichero.current?.click()}>
                <Paperclip size={15} aria-hidden="true" />
              </IconButton>
              <span className="u-text3-2xs">{t('governedconversations.adjunto_limite', { mb: settings?.max_file_mb ?? 0 })}</span>
            </>
          )}
          {!editing && (
            <Checkbox className={`goveconv-box-15 ${canInternalNotes ? 'governed-conversations-m6' : 'governed-conversations-m7'}`}
              label={t('governedconversations.enviar_como_nota_interna')} checked={isInternalNote} onChange={(marcado) => onToggleInternalNote(marcado)} />
          )}
        </div>
        <Button icon={editing ? <Check size={13} /> : <Send size={13} />} onClick={onSend} loading={sending || attaching} disabled={disabled || !value.trim()}>
          {editing ? t('governedconversations.guardar_edicion') : t('governedconversations.enviar_mensaje')}
        </Button>
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

export interface CreateConversationForm {
  title: string
  topic_type: string
  project_id: string
  body: string
  internal_user_ids: string[]
  client_user_ids: string[]
}

export function CreateConversationModal({ mode, open, onClose, onSubmit, projectOptions, defaultProjectId, teamUsers, clientUsers, saving }: CreateConversationModalProps) {
  const idCampo = useId()
  const t = useTextoConversacion(mode)
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
        <div className="goveconv-box-4">{t(mode === 'team' ? 'governedconversations.nueva_con_cliente' : 'governedconversations.nueva_con_equipo')}</div>
        <div className="u-grid2-14">
          <div className="u-col-full">
            <label id={`${idCampo}-et1`} htmlFor={`${idCampo}-1`} className="goveconv-labelstyle">{t('governedconversations.titulo')}</label>
            <Input id={`${idCampo}-1`} aria-labelledby={`${idCampo}-et1`} value={form.title} onChange={(event) => setForm((prev) => ({ ...prev, title: event.target.value }))} inputClassName="goveconv-inputstyle" />
          </div>
          <div>
            <label id={`${idCampo}-et2`} htmlFor={`${idCampo}-2`} className="goveconv-labelstyle">{t('alm.type')}</label>
            <Select suelto placeholder={false} id={`${idCampo}-2`} value={form.topic_type} onChange={(event) => setForm((prev) => ({ ...prev, topic_type: event.target.value }))} className="goveconv-inputstyle">
              {TOPIC_OPTIONS.map((tema) => <option key={tema} value={tema}>{etiquetaDeTema(t, tema)}</option>)}
            </Select>
          </div>
          <div>
            <label id={`${idCampo}-et3`} htmlFor={`${idCampo}-3`} className="goveconv-labelstyle">{t('gas.proyecto')}</label>
            <Select suelto placeholder={t('governedconversations.sin_proyecto')} id={`${idCampo}-3`} value={form.project_id} onChange={(event) => setForm((prev) => ({ ...prev, project_id: event.target.value }))} className="goveconv-inputstyle">
              {projectOptions.map((project) => <option key={project.id} value={project.id}>{project.code ? `${project.code} — ` : ''}{project.name}</option>)}
            </Select>
          </div>
          {mode === 'team' && (
            <>
              <GrupoDeOpciones tipo="checkbox" forma="lista" className="goveconv-multi" leyenda={t('governedconversations.equipo_invitado')}
                valor={form.internal_user_ids} onChange={(ids) => setForm((prev) => ({ ...prev, internal_user_ids: ids }))}
                opciones={teamUsers.map((user) => ({ valor: String(user.id), titulo: user.full_name || user.email }))} />
              <GrupoDeOpciones tipo="checkbox" forma="lista" className="goveconv-multi" leyenda={t('governedconversations.usuarios_portal_invitados')}
                valor={form.client_user_ids} onChange={(ids) => setForm((prev) => ({ ...prev, client_user_ids: ids }))}
                opciones={clientUsers.map((user) => ({ valor: String(user.id), titulo: user.full_name || user.email }))} />
            </>
          )}
          <div className="u-col-full">
            <label id={`${idCampo}-et6`} htmlFor={`${idCampo}-6`} className="goveconv-labelstyle">{t('governedconversations.primer_mensaje')}</label>
            <Textarea id={`${idCampo}-6`} aria-labelledby={`${idCampo}-et6`} value={form.body} onChange={(event) => setForm((prev) => ({ ...prev, body: event.target.value }))} rows={5} inputClassName="goveconv-inputstyle4" />
          </div>
        </div>
        <div className="goveconv-row-5">
          <Button variant="secondary" onClick={onClose}>{t('common.cancel')}</Button>
          <Button onClick={() => onSubmit(form)} loading={saving} disabled={!form.title.trim() || !form.body.trim()}>
            {t('governedconversations.crear_conversacion')}
          </Button>
        </div>
      </div>
    </div>
  )
}
