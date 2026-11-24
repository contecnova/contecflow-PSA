/**
 * Búsqueda de mensajes y enlaces a entidades.
 * Troceado de ChatPage.tsx sin cambio de comportamiento (23-11-2026).
 */
import { type CSSProperties, useState, useId } from 'react'
import { useQuery, useMutation } from '@tanstack/react-query'
import { Search, FileText, AlertCircle, X, Headphones, ListChecks, type LucideIcon } from 'lucide-react'
import { collabApi } from '../../services/collaborationApi'
import { useAppLang } from '../../i18n/AppLangContext'
import { fmtDateTime } from '../../utils/helpers'
import { useDialogo, Pulsable, Input, IconButton } from '../../components/ui'
import { CHAT_SEARCH_LIMIT } from '../../constants/pagination'
import { type LinkCandidate, type Msg, type SearchHit } from './compartido'

// ── Search modal (Cmd+K) ───────────────────────────────────────────────────
export function SearchModal({ onClose, onJump }: { onClose: () => void; onJump: (conversationId: string) => void }) {
  const { t: traducir } = useAppLang()
  const [q, setQ] = useState('')
  const { data: result, isFetching } = useQuery({
    queryKey: ['collab-search', q],
    queryFn: () => collabApi.search({ q, limit: CHAT_SEARCH_LIMIT }) as Promise<{ hits?: SearchHit[] }>,
    enabled: q.trim().length >= 2,
  })
  const hits: SearchHit[] = result?.hits || []
  // Buscador / selector: no es un formulario (no pregunta por cambios sin guardar).
  const dialogRef = useDialogo<HTMLDivElement>(true, onClose, { avisarSinGuardar: false })
  return (
    <div role="presentation" onClick={onClose} className="chat-modal-overlay chat-modal-overlay--top">
      <div ref={dialogRef} role="dialog" aria-modal="true" aria-label={traducir('chat.search_messages')} tabIndex={-1}
        onClick={(e) => e.stopPropagation()}
        onKeyDown={(e) => { if (e.key === 'Escape') onClose() }}
        className="chat-modal chat-modal--wide">
        <div className="chat-search-head">
          <Search size={16} className="u-text3" aria-hidden="true" />
          <Input type="search" aria-label={traducir('chat.search_messages_placeholder')} value={q} onChange={(e) => setQ(e.target.value)} autoFocus
            placeholder={traducir('chat.search_messages_placeholder')}
            className="u-flex1-min0" inputClassName="chat-search-head__input" />
          <kbd className="chat-kbd">Esc</kbd>
        </div>
        <div className="chat-search-results" aria-live="polite">
          {q.trim().length < 2 && (
            <div className="chat-search-msg chat-search-msg--hint">
              {traducir('chat.escribe_al_menos_2_caracteres_soporta_operadores')} <code className="ds-codigo">from:juan</code> · <code className="ds-codigo">in:#general</code> · <code className="ds-codigo">before:2026-05-01</code> · <code className="ds-codigo">has:link</code> · <code className="ds-codigo">is:pinned</code> · <code className="ds-codigo">type:bot</code>
            </div>
          )}
          {isFetching && <div className="chat-search-msg">{traducir('chat.searching')}</div>}
          {!isFetching && q.trim().length >= 2 && hits.length === 0 && (
            <div className="chat-search-msg">{traducir('chat.sin_resultados')}</div>
          )}
          {hits.map((h) => (
            <Pulsable type="button" key={h.id} onClick={() => onJump(h.conversation_id)} className="chat-search-hit">
              <div className="chat-search-hit__snippet">{h.snippet}</div>
              <div className="u-text3-xs">
                {h.sent_at ? fmtDateTime(h.sent_at) : ''}
              </div>
            </Pulsable>
          ))}
        </div>
      </div>
    </div>
  )
}

// ── Linked entity chips ────────────────────────────────────────────────────
export function LinkedEntityChips({ msg }: { msg: Msg }) {
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
export function LinkPickerModal({ messageId, kind, onClose, onPicked }: {
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
  // Buscador / selector: no es un formulario (no pregunta por cambios sin guardar).
  const dialogRef = useDialogo<HTMLDivElement>(true, onClose, { avisarSinGuardar: false })
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
          <IconButton variante="caja" onClick={onClose} ariaLabel={traducir('chat.close')}>
            <X size={14} aria-hidden="true" />
          </IconButton>
        </div>
        <Input type="search" aria-label={traducir('chat.search_placeholder')} value={q} onChange={(e) => setQ(e.target.value)} placeholder={traducir('chat.search_placeholder')} autoFocus
          inputClassName="chat-input chat-input--lg" />
        <div className="chat-linkpick__list">
          {items.length === 0 && <div className="chat-linkpick__empty">{traducir('chat.sin_resultados')}</div>}
          {items.map((it) => (
            <Pulsable type="button" key={it.id} onClick={() => link.mutate(it.id)} className="chat-linkpick__item">
              {it.label}
            </Pulsable>
          ))}
        </div>
      </div>
    </div>
  )
}
