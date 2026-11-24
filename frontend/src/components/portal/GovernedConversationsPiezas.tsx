// Piezas de la bandeja de conversaciones gobernadas (burbuja, redactor y modal de alta). 23-11-2026: troceado de GovernedConversations sin cambio de comportamiento.
// 24-11-2026 («un solo chat»): la fila de la lista es `FilaDeConversacion` de components/chat (se fue la fila de lista propia).
import { useEffect, useState, useId } from 'react'
import { useDialogo, Button, Checkbox, GrupoDeOpciones, Select, Input, Textarea, TextoConEnlaces } from '../ui'
import { type AccionDeMensaje, AvisoDelEditor, EditorDeChat, EstadoDeEntrega, EtiquetaDeAutor, FilaDeMensaje, agruparReacciones, cambiaDeDia } from '../chat'
import { Check, History, Pencil, Reply, Trash2, X } from 'lucide-react'
import type { PortalAjustesDelChat } from '../../services/api/tipos-alm'
import AdjuntoDelChat from './AdjuntoDelChat'
import type { ChatDelPortalApi } from './chatDelPortalApi'
import { GRC_LABEL, type Message, type Mode, type ProjectOption, TOPIC_OPTIONS, type UserOption, etiquetaDeTema, useTextoConversacion } from './GovernedConversationsComun'

/** Mismo autor en menos de 5 min y el mismo día: fila compacta, como en el chat interno. */
export function esCompacto(previo: Message | undefined, m: Message): boolean {
  if (!previo || previo.is_deleted || m.is_deleted) return false
  if (cambiaDeDia(previo.created_at, m.created_at)) return false
  const mismo = previo.sender_type === m.sender_type
    && (previo.sender_user_id || previo.sender_client_id) === (m.sender_user_id || m.sender_client_id)
  return mismo && !!previo.created_at && !!m.created_at
    && Date.parse(m.created_at) - Date.parse(previo.created_at) < 5 * 60_000
}

interface MessageBubbleProps {
  message: Message
  mode: Mode
  /** Fila compacta (mismo autor seguido), como en el chat interno. */
  compact?: boolean
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

// 24-11-2026 («un solo chat»): la fila y el editor son los del chat interno
// (`FilaDeMensaje` y `EditorDeChat` de components/chat). Aquí solo se dicen las
// acciones de cada lado (el cliente no ve notas internas, historial ni aprobar)
// y lo propio de las conversaciones gobernadas (insignias GRC, revisión).
export function MessageBubble({ message, mode, compact, onReview, conversationId, api, isMine, viewerUserId, viewerClientId, onReply, onEdit, onDelete, onReact, onHistory, onError }: MessageBubbleProps) {
  const t = useTextoConversacion(mode)
  const grcCfg = GRC_LABEL[message.grc_status]
  const grc = grcCfg ? { text: t(grcCfg.text), color: grcCfg.color } : { text: message.grc_status, color: 'var(--text-2)' }
  const borrado = !!message.is_deleted
  const nativo = message.source !== 'legacy_client_message'
  const interactivo = nativo && !borrado && !!api && !!conversationId
  const soloAdjunto = message.message_type === 'attachment' && !!message.body && (message.attachments || []).some(a => a.name === message.body)
  const historial: AccionDeMensaje[] = mode === 'team' && onHistory && (message.edited_at || borrado)
    ? [{ clave: 'historial', etiqueta: t('governedconversations.ver_historial'), icono: <History size={13} aria-hidden="true" />, onClick: () => onHistory(message) }]
    : []
  const acciones: AccionDeMensaje[] = !interactivo ? [] : [
    { clave: 'responder', etiqueta: t('governedconversations.responder'), icono: <Reply size={13} aria-hidden="true" />, onClick: () => onReply?.(message) },
    ...(isMine && (message.message_type === 'text' || message.message_type === 'attachment') ? [
      { clave: 'editar', etiqueta: t('governedconversations.editar'), icono: <Pencil size={13} aria-hidden="true" />, onClick: () => onEdit?.(message) },
      { clave: 'borrar', etiqueta: t('governedconversations.borrar'), icono: <Trash2 size={13} aria-hidden="true" />, onClick: () => onDelete?.(message), peligro: true },
    ] : []),
    ...historial,
  ]
  return (
    <FilaDeMensaje
      autor={message.sender_name || '?'}
      fecha={message.created_at}
      // 24-11-2026 (burbujas): lo de quien mira (equipo: su usuario; cliente: su usuario del portal) a la derecha.
      propio={!!isMine}
      compacto={compact}
      borrado={borrado}
      editado={!!message.edited_at && !borrado}
      textos={{
        mensajeDe: t('governedconversations.mensaje_de', { name: message.sender_name }),
        acciones: t('governedconversations.acciones_del_mensaje'),
        editado: t('governedconversations.editado'),
        eliminado: t('governedconversations.mensaje_borrado'),
        reaccion: (emoji, n) => t('governedconversations.reaccion_de', { emoji, n }),
        reaccionarCon: (emoji) => t('governedconversations.reaccionar_con', { emoji }),
      }}
      insignias={<>
        {/* Con el estilo de la etiqueta de bot del chat interno. El estado GRC solo lo ve el equipo. */}
        {message.sender_type === 'client' && <EtiquetaDeAutor>{t('governedconversations.remitente_cliente')}</EtiquetaDeAutor>}
        {mode === 'team' && message.grc_status !== 'allowed' && <EtiquetaDeAutor>{grc.text}</EtiquetaDeAutor>}
        {message.is_internal_note && <EtiquetaDeAutor>{t('governedconversations.interna')}</EtiquetaDeAutor>}
        {mode === 'team' && message.is_redacted && <EtiquetaDeAutor>{t('governedconversations.redactada')}</EtiquetaDeAutor>}
        {!nativo && <EtiquetaDeAutor>{t('governedconversations.origen_anterior')}</EtiquetaDeAutor>}
      </>}
      cita={message.reply_to ? { autor: message.reply_to.sender_name, texto: message.reply_to.body, borrada: message.reply_to.is_deleted } : null}
      cuerpo={borrado
        ? <div className="chat-msg__body">{t('governedconversations.mensaje_borrado')}</div>
        : (!soloAdjunto && <TextoConEnlaces texto={message.body} className="chat-msg__body" />)}
      extras={<>
        {!borrado && (message.attachments || []).length > 0 && api && conversationId && (
          <div className="chat-msg__attachments">
            {(message.attachments || []).map(a => (
              <AdjuntoDelChat key={a.id} adjunto={a} cargar={(id) => api.adjunto(conversationId, id)} t={t} onError={onError || (() => undefined)} />
            ))}
          </div>
        )}
        {message.moderation_notes && mode === 'team' && <div className="u-text3-xs">{t('governedconversations.moderacion')} {message.moderation_notes}</div>}
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
      </>}
      reacciones={agruparReacciones(message.reactions, { userId: viewerUserId, clientId: viewerClientId })}
      onReaccionar={interactivo ? (emoji) => onReact?.(message, emoji) : undefined}
      acciones={acciones}
      accionesSiBorrado={historial}
      pie={isMine && !borrado && nativo ? (
        <EstadoDeEntrega leido={!!message.read_at} textoLeido={t('governedconversations.leido')} textoEnviado={t('governedconversations.enviado')} />
      ) : null}
    />
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
  const t = useTextoConversacion(mode)
  const adjuntos = !!settings?.attachments_enabled && !!onAttach && !editing
  const escribir = (v: string) => {
    onChange(v)
    if (v.trim()) onTyping?.()
  }
  const placeholder = t(mode === 'team' ? 'governedconversations.ph_equipo' : 'governedconversations.ph_cliente')
  return (
    <EditorDeChat
      valor={value}
      onCambiar={escribir}
      onEnviar={() => { if (value.trim() && !disabled && !sending && !attaching) onSend() }}
      etiquetaCampo={placeholder}
      placeholder={placeholder}
      etiquetaEnviar={editing ? t('governedconversations.guardar_edicion') : t('governedconversations.enviar_mensaje')}
      desactivado={disabled}
      adjuntar={adjuntos ? {
        etiqueta: `${t('governedconversations.adjuntar')} · ${t('governedconversations.adjunto_limite', { mb: settings?.max_file_mb ?? 0 })}`,
        aceptar: (settings?.allowed_extensions || []).join(','), onFichero: (f) => onAttach?.(f), desactivado: attaching,
      } : null}
      etiquetaEmoji={t('governedconversations.insertar_emoji')}
      encima={<>
        {replyTo && !editing && (
          <AvisoDelEditor icono={<Reply size={12} aria-hidden="true" />}
            texto={`${t('governedconversations.respondiendo_a', { name: replyTo.sender_name })}: ${replyTo.is_deleted ? t('governedconversations.mensaje_borrado') : String(replyTo.body || '').slice(0, 120)}`}
            etiquetaCancelar={t('governedconversations.cancelar_respuesta')} onCancelar={() => onCancelReply?.()} />
        )}
        {editing && (
          <AvisoDelEditor icono={<Pencil size={12} aria-hidden="true" />} texto={t('governedconversations.editando')}
            etiquetaCancelar={t('governedconversations.cancelar_edicion')} onCancelar={() => onCancelEdit?.()} />
        )}
        {!editing && canInternalNotes && (
          <Checkbox label={t('governedconversations.enviar_como_nota_interna')} checked={isInternalNote} onChange={(marcado) => onToggleInternalNote(marcado)} />
        )}
      </>}
    />
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
