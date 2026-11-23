// Piezas de la bandeja de conversaciones gobernadas (item, burbuja, redactor y modal de alta). 23-11-2026: troceado de GovernedConversations sin cambio de comportamiento.
import { type CSSProperties, useEffect, useState, useId } from 'react'
import { fmtDateTime } from '../../utils/helpers'
import { useDialogo, Button, Checkbox, GrupoDeOpciones, Pulsable, Select, Input, Textarea } from '../ui'
import { Check, X, Send } from 'lucide-react'
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
}

export function MessageBubble({ message, mode, onReview }: MessageBubbleProps) {
  const t = useTextoConversacion(mode)
  const grcCfg = GRC_LABEL[message.grc_status]
  const grc = grcCfg ? { text: t(grcCfg.text), color: grcCfg.color } : { text: message.grc_status, color: 'var(--text-2)' }
  const alignSelf = message.sender_type === 'client' ? 'flex-start' : 'flex-end'
  const bubbleBg = message.sender_type === 'client' ? 'var(--surface-1)' : 'var(--accent-muted)'
  const borderColor = message.grc_status === 'pending_review' ? 'var(--warning-border)' : 'var(--surface-4)'
  return (
    <div className="goveconv-stack-1 governed-conversations-e4" style={{ '--governed-conversations-align-items': alignSelf } as CSSProperties}>
      <div className="goveconv-box-14 governed-sx2 governed-conversations-e5" style={{ '--governed-conversations-background': bubbleBg, '--governed-conversations-border': `1px solid ${borderColor}` } as CSSProperties}>
        <div className="goveconv-row-1">
          <div className="u-sm-700">{message.sender_name}</div>
          <div className="u-text3-2xs">{fmtDateTime(message.created_at)}</div>
        </div>
        <div className="goveconv-row-2">
          <StatusBadge color={message.sender_type === 'client' ? 'var(--warning)' : 'var(--accent)'}>{t(message.sender_type === 'client' ? 'governedconversations.remitente_cliente' : 'governedconversations.remitente_equipo')}</StatusBadge>
          <StatusBadge color={grc.color}>{grc.text}</StatusBadge>
          {message.is_internal_note && <StatusBadge color="var(--danger)">{t('governedconversations.interna')}</StatusBadge>}
          {message.is_redacted && <StatusBadge color="var(--accent)">{t('governedconversations.redactada')}</StatusBadge>}
          {message.source === 'legacy_client_message' && <StatusBadge color="var(--warning)">{t('governedconversations.origen_anterior')}</StatusBadge>}
        </div>
        <div className="goveconv-txt-4">{message.body}</div>
        {message.moderation_notes && <div className="goveconv-box-1">{t('governedconversations.moderacion')} {message.moderation_notes}</div>}
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
}

export function ConversationComposer({ mode, value, onChange, onSend, sending, canInternalNotes, isInternalNote, onToggleInternalNote, disabled }: ConversationComposerProps) {
  const idCampo = useId()
  const t = useTextoConversacion(mode)
  return (
    <div className="goveconv-cardstyle">
      <Textarea label={t('mentions.reply')} id={`${idCampo}-1`} value={value} onChange={(event) => onChange(event.target.value)} rows={4} placeholder={t(mode === 'team' ? 'governedconversations.ph_equipo' : 'governedconversations.ph_cliente')} />
      <div className="goveconv-row-4">
        <Checkbox className={`goveconv-box-15 ${canInternalNotes ? 'governed-conversations-m6' : 'governed-conversations-m7'}`}
          label={t('governedconversations.enviar_como_nota_interna')} checked={isInternalNote} onChange={(marcado) => onToggleInternalNote(marcado)} />
        <Button icon={<Send size={13} />} onClick={onSend} loading={sending} disabled={disabled || !value.trim()}>
          {t('governedconversations.enviar_mensaje')}
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
