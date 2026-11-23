// Selector de respuesta rapida y modales de dividir y editar ticket. 23-11-2026: troceado de TicketDetail sin cambio de comportamiento.
import { useMemo, useState, useId } from 'react'
import { useQuery, useMutation } from '@tanstack/react-query'
import { useAppT } from '../../i18n/AppLangContext'
import { useToast } from '../../context/ToastContext'
import { extractErr } from '../../utils/helpers'
import { Scissors } from 'lucide-react'
import { Buscador, Button, Modal, Pulsable, Select, Input, Textarea } from '../../components/ui'
import AIInlineEditor from '../../components/AIInlineEditor'
import { sdCannedApi, ticketsApi } from '../../services/api'
import { STALE_DEFAULT_MS } from '../../constants/timings'
import { type CannedResponse, LS, type TicketShape } from './TicketDetailComun'
import { ESTADOS_TICKET_RESUELTOS } from '../../constants/estadosDeTicket'

export function CannedResponsePicker({ onSelect, onClose }: { onSelect: (body: string) => void; onClose: () => void }) {
  const t = useAppT()
  const [search, setSearch] = useState('')
  const { data: responses = [] } = useQuery<CannedResponse[]>({
    queryKey: ['canned-responses', search],
    queryFn: () => sdCannedApi.list(search ? { search } : {}).then(r => r.data),
    staleTime: STALE_DEFAULT_MS,
  })
  const cats: string[] = Array.from<string>(new Set(responses.map((r) => String(r.category || '')))).sort()
  return (
    <div className="tkd-canned">
      <div className="tkd-canned__search">
        <Buscador autoFocus value={search} onChange={setSearch} aria-label={t('service_desk.canned_search')} placeholder={t('service_desk.canned_search')} />
      </div>
      <div className="tkd-canned__list">
        {responses.length === 0 ? (
          <div className="tkd-canned__empty">
            {search ? t('service_desk.canned_no_results') : t('service_desk.canned_empty')}
          </div>
        ) : cats.map(cat => {
          const catItems = responses.filter(r => (r.category || '') === cat)
          if (!catItems.length) return null
          return (
            <div key={cat}>
              <div className="tkd-canned__cat">{cat === '' ? t('ticketdetail.categoria_general') : cat}</div>
              {catItems.map(r => (
                <Pulsable key={r.id} onClick={() => { onSelect(r.body || ''); onClose() }}
                  aria-label={r.title || t('service_desk.detail_send_comment')}
                  className="tkd-canned__item">
                  <div className="tkd-canned__title">
                    {r.shortcut && <span className="ds-codigo tkd-canned__shortcut">{r.shortcut}</span>}
                    {r.title}
                  </div>
                  <div className="tkd-canned__body">{r.body?.slice(0, 80)}</div>
                </Pulsable>
              ))}
            </div>
          )
        })}
      </div>
      <div className="tkd-canned__foot">
        <Pulsable onClick={onClose} className="tkd-canned__cancel">{t('service_desk.canned_cancel_esc')}</Pulsable>
      </div>
    </div>
  )
}

// ── SplitTicketModal ──────────────────────────────────────────────────────────
export function SplitTicketModal({ ticket, onClose, onCreated }: { ticket: TicketShape; onClose: () => void; onCreated?: (data: unknown) => void }) {
  const idCampo = useId()
  const t = useAppT()
  const toast = useToast()
  const [form, setForm] = useState({
    new_title: '', new_description: ticket?.description || '',
    keep_original_description: ticket?.description || '', tags: '',
  })
  const { mutate, isPending } = useMutation({
    mutationFn: (data: Record<string, unknown>) => ticketsApi.split(ticket.id, data),
    onSuccess: res => {
      toast.success(`${t('service_desk.ticket_created_success')} ${res.data.child}`)
      onCreated?.(res?.data)
      onClose()
    },
    onError: e => toast.error(extractErr(e, t('common.error'))),
  })
  const handleSave = () => {
    if (!form.new_title.trim()) { toast.error(t('service_desk.zod_title_required')); return }
    mutate({
      new_title: form.new_title.trim(),
      new_description: form.new_description,
      keep_original_description: form.keep_original_description,
      tags: form.tags ? form.tags.split(',').map(s => s.trim()).filter(Boolean) : [],
    })
  }
  return (
    <Modal open title={t('ticketdetail.dividir_ticket', { number: ticket?.number ?? '' })} onClose={onClose}>
      <div className="u-stack-16">
        <div className="tkd-note">
          {t('service_desk.split_desc_original')} <strong className="u-text1">{ticket?.number}</strong>.
        </div>
        <div className="u-grid2-14">
          <div>
            <label id={`${idCampo}-et1`} htmlFor={`${idCampo}-1`} className={LS}>{t('service_desk.split_title_lbl')} *</label>
            <Input id={`${idCampo}-1`} aria-labelledby={`${idCampo}-et1`} value={form.new_title} onChange={e => setForm(f => ({ ...f, new_title: e.target.value }))} autoFocus inputClassName="tkd-input" />
          </div>
          <div>
            <label id={`${idCampo}-et2`} htmlFor={`${idCampo}-2`} className={LS}>{t('service_desk.split_tags_lbl')}</label>
            <Input id={`${idCampo}-2`} aria-labelledby={`${idCampo}-et2`} value={form.tags} onChange={e => setForm(f => ({ ...f, tags: e.target.value }))} inputClassName="tkd-input" />
          </div>
        </div>
        <div>
          <label id={`${idCampo}-et3`} htmlFor={`${idCampo}-3`} className={LS}>{t('service_desk.split_desc_child')}</label>
          <Textarea id={`${idCampo}-3`} aria-labelledby={`${idCampo}-et3`} value={form.new_description} onChange={e => setForm(f => ({ ...f, new_description: e.target.value }))} rows={4} inputClassName="tkd-input" />
        </div>
        <div>
          <label id={`${idCampo}-et4`} htmlFor={`${idCampo}-4`} className={LS}>{t('service_desk.split_desc_original')}</label>
          <Textarea id={`${idCampo}-4`} aria-labelledby={`${idCampo}-et4`} value={form.keep_original_description} onChange={e => setForm(f => ({ ...f, keep_original_description: e.target.value }))} rows={4} inputClassName="tkd-input" />
        </div>
        <div className="u-actions-10">
          <Button variant="secondary" onClick={onClose}>{t('common.cancel')}</Button>
          <Button icon={<Scissors size={14} />} onClick={handleSave} disabled={isPending || !form.new_title.trim()} loading={isPending}>{t('service_desk.split_create_btn')}</Button>
        </div>
      </div>
    </Modal>
  )
}

// ── TicketEditModal ───────────────────────────────────────────────────────────
export function TicketEditModal({ ticket, onClose, onSaved }: { ticket: TicketShape; onClose: () => void; onSaved: () => void }) {
  const idCampo = useId()
  const t = useAppT()
  const toast = useToast()
  const initialDynamic = useMemo(() => {
    const raw = ticket?.dynamic_fields
    if (!raw || typeof raw !== 'object') return '{}'
    try { return JSON.stringify(raw, null, 2) } catch { /* accesorio: valor no serializable; el editor arranca con un objeto vacío */ return '{}' }
  }, [ticket?.dynamic_fields])
  const [form, setForm] = useState({
    title: ticket.title || '', description: ticket.description || '',
    priority: ticket.priority || 'p3_medium', ticket_type: ticket.ticket_type || 'incident',
    urgency: ticket.urgency || 'medium', impact: ticket.impact || 'user',
    status: ticket.status || 'new', resolution: ticket.resolution || '', tags: ticket.tags || '',
  })
  const [dynamicFieldsText, setDynamicFieldsText] = useState(initialDynamic)
  const { mutate, isPending } = useMutation({
    mutationFn: (data: Record<string, unknown>) => ticketsApi.update(ticket.id, data),
    onSuccess: onSaved,
    onError: e => toast.error(extractErr(e, t('ticketdetail.error_guardar'))),
  })
  const set = (k: string) => (e: { target: { value: string } }) => setForm(f => ({ ...f, [k]: e.target.value }))
  return (
    <Modal open title={`${t('common.edit')} ${ticket.number}`} onClose={onClose} size="lg">
      <div className="tkd-edit-grid">
        <div className="u-col-full">
          <label id={`${idCampo}-et1`} htmlFor={`${idCampo}-1`} className={LS}>{t('service_desk.ticket_title')} *</label>
          <Input id={`${idCampo}-1`} aria-labelledby={`${idCampo}-et1`} value={form.title} onChange={set('title')} inputClassName="tkd-input" />
        </div>
        <div>
          <label id={`${idCampo}-et2`} htmlFor={`${idCampo}-2`} className={LS}>{t('service_desk.ticket_type')}</label>
          <Select suelto placeholder={false} id={`${idCampo}-2`} value={form.ticket_type} onChange={set('ticket_type')} className="tkd-sel">
            {[['incident', t('service_desk.type_incident')], ['service_request', t('service_desk.type_service_request')],
              ['change', t('service_desk.type_change')], ['problem', t('service_desk.type_problem')], ['question', t('service_desk.type_question')]
            ].map(([v, l]) => <option key={v} value={v}>{l}</option>)}
          </Select>
        </div>
        <div>
          <label id={`${idCampo}-et3`} htmlFor={`${idCampo}-3`} className={LS}>{t('service_desk.ticket_priority')}</label>
          <Select suelto placeholder={false} id={`${idCampo}-3`} value={form.priority} onChange={set('priority')} className="tkd-sel">
            {[['p1_critical', t('service_desk.priority_p1')], ['p2_high', t('service_desk.priority_p2')],
              ['p3_medium', t('service_desk.priority_p3')], ['p4_low', t('service_desk.priority_p4')]
            ].map(([v, l]) => <option key={v} value={v}>{l}</option>)}
          </Select>
        </div>
        <div>
          <label id={`${idCampo}-et4`} htmlFor={`${idCampo}-4`} className={LS}>{t('service_desk.edit_urgency')}</label>
          <Select suelto placeholder={false} id={`${idCampo}-4`} value={form.urgency} onChange={set('urgency')} className="tkd-sel">
            {[['critical', t('service_desk.urgency_critical')], ['high', t('service_desk.urgency_high')], ['medium', t('service_desk.urgency_medium')], ['low', t('service_desk.urgency_low')]].map(([v, l]) => <option key={v} value={v}>{l}</option>)}
          </Select>
        </div>
        <div>
          <label id={`${idCampo}-et5`} htmlFor={`${idCampo}-5`} className={LS}>{t('service_desk.edit_impact')}</label>
          <Select suelto placeholder={false} id={`${idCampo}-5`} value={form.impact} onChange={set('impact')} className="tkd-sel">
            {[['enterprise', t('service_desk.impact_enterprise')], ['department', t('service_desk.impact_department')], ['user', t('service_desk.impact_user')], ['minimal', t('service_desk.impact_minimal')]].map(([v, l]) => <option key={v} value={v}>{l}</option>)}
          </Select>
        </div>
        <div>
          <label id={`${idCampo}-et6`} htmlFor={`${idCampo}-6`} className={LS}>{t('common.status')}</label>
          <Select suelto placeholder={false} id={`${idCampo}-6`} value={form.status} onChange={set('status')} className="tkd-sel">
            {[['new', t('service_desk.status_new')], ['assigned', t('service_desk.status_assigned')], ['in_progress', t('service_desk.status_in_progress')],
              ['pending_client', t('service_desk.status_waiting_client')], ['pending_third', t('service_desk.status_pending_third')],
              ['resolved', t('service_desk.status_resolved')], ['closed', t('service_desk.status_closed')], ['cancelled', t('service_desk.status_cancelled')]
            ].map(([v, l]) => <option key={v} value={v}>{l}</option>)}
          </Select>
        </div>
        <div className="u-col-full">
          <label htmlFor={`${idCampo}-desc`} className={LS}>{t('common.description')} *</label>
          <AIInlineEditor inputId={`${idCampo}-desc`} value={form.description} onChange={(val: string) => set('description')({ target: { value: val } })} rows={5} className="campo-form tkd-vertical" />
        </div>
        {ESTADOS_TICKET_RESUELTOS.includes(form.status) && (
          <div className="u-col-full">
            <label id={`${idCampo}-et7`} htmlFor={`${idCampo}-7`} className={LS}>{t('service_desk.edit_resolution')}</label>
            <Textarea id={`${idCampo}-7`} aria-labelledby={`${idCampo}-et7`} value={form.resolution} onChange={set('resolution')} rows={3} inputClassName="tkd-input" />
          </div>
        )}
        <div className="u-col-full">
          <label id={`${idCampo}-et8`} htmlFor={`${idCampo}-8`} className={LS}>{t('service_desk.edit_tags')}</label>
          <Input id={`${idCampo}-8`} aria-labelledby={`${idCampo}-et8`} value={form.tags} onChange={set('tags')} inputClassName="tkd-input" />
        </div>
        <div className="tkd-full-actions">
          <Button variant="secondary" onClick={onClose}>{t('common.cancel')}</Button>
          <Button onClick={() => {
            let parsedDynamic = {}
            try {
              parsedDynamic = JSON.parse(dynamicFieldsText || '{}')
              if (!parsedDynamic || typeof parsedDynamic !== 'object' || Array.isArray(parsedDynamic)) {
                toast.error(t('ticketdetail.dinamicos_no_objeto'))
                return
              }
            } catch {
              toast.error(t('ticketdetail.dinamicos_json_invalido'))
              return
            }
            mutate({ ...form, dynamic_fields: parsedDynamic })
          }} disabled={isPending || !form.title.trim() || !form.description.trim()} loading={isPending}>
            {t('common.save')}
          </Button>
        </div>
        <div className="u-col-full">
          <Textarea label={t('ticketdetail.campos_dinamicos_json')} id={`${idCampo}-9`} value={dynamicFieldsText} onChange={e => setDynamicFieldsText(e.target.value)} rows={6} inputClassName="tkd-input--mono ds-campo-codigo" />
        </div>
      </div>
    </Modal>
  )
}
