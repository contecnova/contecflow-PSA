import type { CSSProperties } from 'react'
import { useMemo, useState, useId } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useAppT } from '../../i18n/AppLangContext'
import { useToast } from '../../context/ToastContext'
import { extractErr } from '../../utils/helpers'
import { GENERIC_ERROR_FALLBACK } from '../../constants/errors'
import { Button, Spinner, Modal } from '../../components/ui'
import AIInlineEditor from '../../components/AIInlineEditor'
import DocumentsPanel from '../../components/DocumentsPanel'
import DocumentosDeFicha from '../../components/conectores/DocumentosDeFicha'
import LeccionesDeOrigen from '../../components/lecciones/LeccionesDeOrigen'
import PanelIaDelTicket from '../../components/servicedesk/PanelIaDelTicket'
import EstadoDeCicloDeVida from '../../components/servicedesk/EstadoDeCicloDeVida'
import AvisoDeColision from '../../components/servicedesk/AvisoDeColision'
import ContextoDelCliente from '../../components/servicedesk/ContextoDelCliente'
import { RecursoDelTicket } from '../../components/alm/EnlaceTicketRecurso'
import { COLOR } from '../../constants/theme'
import { almExtApi, sdApprovalsApi, sdCannedApi, ticketsApi, usersApi } from '../../services/api'
import type { SdAprobacionDeTicket, SdRespuestaRapida, SdSugerenciaIA, SdTicketComentario, SdTicketDetalle, SdTicketEnlace, SdTicketHistorial } from '../../services/api/tipos-sd'
import { useAuth } from '../../context/AuthContext'
import { PBadge, SBadge, fmtDate, fmtMinutes } from './sdUtils'
import { POLL_FREQUENT_MS, STALE_DEFAULT_MS } from '../../constants/timings'
import { TICKET_LINK_SEARCH_LIMIT } from '../../constants/pagination'
import './TicketDetail.css'

/** Clases de los formularios (locales a la pantalla). */
const IS = 'tkd-input'
const LS = 'tkd-label'
/** `Button` solo acepta `style`: va como objeto. */
const FULL_WIDTH_STYLE: CSSProperties = { width: '100%' }
/** Color del dato (estado de SLA, de aprobacion) para las clases `.tkd-*` que lo leen. */
const colorVar = (c: string) => ({ '--tkd-c': c } as CSSProperties)

type TicketShape = SdTicketDetalle

type TicketLink = SdTicketEnlace
type TicketComment = SdTicketComentario
type TicketHistoryEntry = SdTicketHistorial
/** Contrato de ALM usado como contrato de soporte (UC). */
interface UcContract { id: string; title?: string; vendor_name?: string | null; status?: string; response_hours?: number | null; resolution_hours?: number | null }

// ── CannedResponsePicker ──────────────────────────────────────────────────────
type CannedResponse = SdRespuestaRapida
function CannedResponsePicker({ onSelect, onClose }: { onSelect: (body: string) => void; onClose: () => void }) {
  const t = useAppT()
  const [search, setSearch] = useState('')
  const { data: responses = [] } = useQuery<CannedResponse[]>({
    queryKey: ['canned-responses', search],
    queryFn: () => sdCannedApi.list(search ? { search } : {}).then(r => r.data).catch(() => []),
    staleTime: STALE_DEFAULT_MS,
  })
  const cats: string[] = Array.from<string>(new Set(responses.map((r) => String(r.category || 'General')))).sort()
  return (
    <div className="tkd-canned">
      <div className="tkd-canned__search">
        <input autoFocus value={search} onChange={e => setSearch(e.target.value)}
          aria-label={t('service_desk.canned_search')}
          placeholder={t('service_desk.canned_search')}
          className="tkd-canned__input" />
      </div>
      <div className="tkd-canned__list">
        {responses.length === 0 ? (
          <div className="tkd-canned__empty">
            {search ? t('service_desk.canned_no_results') : t('service_desk.canned_empty')}
          </div>
        ) : cats.map(cat => {
          const catItems = responses.filter(r => (r.category || 'General') === cat)
          if (!catItems.length) return null
          return (
            <div key={cat}>
              <div className="tkd-canned__cat">{cat === 'General' ? t('ticketdetail.categoria_general') : cat}</div>
              {catItems.map(r => (
                <button type="button" key={r.id} onClick={() => { onSelect(r.body || ''); onClose() }}
                  aria-label={r.title || t('service_desk.detail_send_comment')}
                  className="tkd-canned__item">
                  <div className="tkd-canned__title">
                    {r.shortcut && <span className="tkd-canned__shortcut">{r.shortcut}</span>}
                    {r.title}
                  </div>
                  <div className="tkd-canned__body">{r.body?.slice(0, 80)}</div>
                </button>
              ))}
            </div>
          )
        })}
      </div>
      <div className="tkd-canned__foot">
        <button type="button" onClick={onClose} className="tkd-canned__cancel">{t('service_desk.canned_cancel_esc')}</button>
      </div>
    </div>
  )
}

// ── SplitTicketModal ──────────────────────────────────────────────────────────
function SplitTicketModal({ ticket, onClose, onCreated }: { ticket: TicketShape; onClose: () => void; onCreated?: (data: unknown) => void }) {
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
    <Modal open title={`✂ ${t('ticketdetail.dividir_ticket', { number: ticket?.number ?? '' })}`} onClose={onClose}>
      <div className="u-stack-16">
        <div className="tkd-note">
          {t('service_desk.split_desc_original')} <strong className="u-text1">{ticket?.number}</strong>.
        </div>
        <div className="u-grid2-14">
          <div>
            <label id={`${idCampo}-et1`} htmlFor={`${idCampo}-1`} className={LS}>{t('service_desk.split_title_lbl')} *</label>
            <input id={`${idCampo}-1`} aria-labelledby={`${idCampo}-et1`} value={form.new_title} onChange={e => setForm(f => ({ ...f, new_title: e.target.value }))} className={IS} autoFocus />
          </div>
          <div>
            <label id={`${idCampo}-et2`} htmlFor={`${idCampo}-2`} className={LS}>{t('service_desk.split_tags_lbl')}</label>
            <input id={`${idCampo}-2`} aria-labelledby={`${idCampo}-et2`} value={form.tags} onChange={e => setForm(f => ({ ...f, tags: e.target.value }))} className={IS} />
          </div>
        </div>
        <div>
          <label id={`${idCampo}-et3`} htmlFor={`${idCampo}-3`} className={LS}>{t('service_desk.split_desc_child')}</label>
          <textarea id={`${idCampo}-3`} aria-labelledby={`${idCampo}-et3`} value={form.new_description} onChange={e => setForm(f => ({ ...f, new_description: e.target.value }))} rows={4} className={IS} />
        </div>
        <div>
          <label id={`${idCampo}-et4`} htmlFor={`${idCampo}-4`} className={LS}>{t('service_desk.split_desc_original')}</label>
          <textarea id={`${idCampo}-4`} aria-labelledby={`${idCampo}-et4`} value={form.keep_original_description} onChange={e => setForm(f => ({ ...f, keep_original_description: e.target.value }))} rows={4} className={IS} />
        </div>
        <div className="u-actions-10">
          <Button variant="secondary" onClick={onClose}>{t('common.cancel')}</Button>
          <Button onClick={handleSave} disabled={isPending || !form.new_title.trim()} loading={isPending}>✂ {t('service_desk.split_create_btn')}</Button>
        </div>
      </div>
    </Modal>
  )
}

// ── TicketEditModal ───────────────────────────────────────────────────────────
function TicketEditModal({ ticket, onClose, onSaved }: { ticket: TicketShape; onClose: () => void; onSaved: () => void }) {
  const idCampo = useId()
  const t = useAppT()
  const toast = useToast()
  const initialDynamic = useMemo(() => {
    const raw = ticket?.dynamic_fields
    if (!raw || typeof raw !== 'object') return '{}'
    try { return JSON.stringify(raw, null, 2) } catch { return '{}' }
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
          <input id={`${idCampo}-1`} aria-labelledby={`${idCampo}-et1`} value={form.title} onChange={set('title')} className={IS} />
        </div>
        <div>
          <label id={`${idCampo}-et2`} htmlFor={`${idCampo}-2`} className={LS}>{t('service_desk.ticket_type')}</label>
          <select id={`${idCampo}-2`} aria-labelledby={`${idCampo}-et2`} value={form.ticket_type} onChange={set('ticket_type')} className={IS}>
            {[['incident', `🔴 ${t('service_desk.type_incident')}`], ['service_request', `🔵 ${t('service_desk.type_service_request')}`],
              ['change', `🟡 ${t('service_desk.type_change')}`], ['problem', `🟠 ${t('service_desk.type_problem')}`], ['question', `⚪ ${t('service_desk.type_question')}`]
            ].map(([v, l]) => <option key={v} value={v}>{l}</option>)}
          </select>
        </div>
        <div>
          <label id={`${idCampo}-et3`} htmlFor={`${idCampo}-3`} className={LS}>{t('service_desk.ticket_priority')}</label>
          <select id={`${idCampo}-3`} aria-labelledby={`${idCampo}-et3`} value={form.priority} onChange={set('priority')} className={IS}>
            {[['p1_critical', `🔴 ${t('service_desk.priority_p1')}`], ['p2_high', `🟠 ${t('service_desk.priority_p2')}`],
              ['p3_medium', `🟡 ${t('service_desk.priority_p3')}`], ['p4_low', `⚪ ${t('service_desk.priority_p4')}`]
            ].map(([v, l]) => <option key={v} value={v}>{l}</option>)}
          </select>
        </div>
        <div>
          <label id={`${idCampo}-et4`} htmlFor={`${idCampo}-4`} className={LS}>{t('service_desk.edit_urgency')}</label>
          <select id={`${idCampo}-4`} aria-labelledby={`${idCampo}-et4`} value={form.urgency} onChange={set('urgency')} className={IS}>
            {[['critical', t('service_desk.urgency_critical')], ['high', t('service_desk.urgency_high')], ['medium', t('service_desk.urgency_medium')], ['low', t('service_desk.urgency_low')]].map(([v, l]) => <option key={v} value={v}>{l}</option>)}
          </select>
        </div>
        <div>
          <label id={`${idCampo}-et5`} htmlFor={`${idCampo}-5`} className={LS}>{t('service_desk.edit_impact')}</label>
          <select id={`${idCampo}-5`} aria-labelledby={`${idCampo}-et5`} value={form.impact} onChange={set('impact')} className={IS}>
            {[['enterprise', t('service_desk.impact_enterprise')], ['department', t('service_desk.impact_department')], ['user', t('service_desk.impact_user')], ['minimal', t('service_desk.impact_minimal')]].map(([v, l]) => <option key={v} value={v}>{l}</option>)}
          </select>
        </div>
        <div>
          <label id={`${idCampo}-et6`} htmlFor={`${idCampo}-6`} className={LS}>{t('common.status')}</label>
          <select id={`${idCampo}-6`} aria-labelledby={`${idCampo}-et6`} value={form.status} onChange={set('status')} className={IS}>
            {[['new', t('service_desk.status_new')], ['assigned', t('service_desk.status_assigned')], ['in_progress', t('service_desk.status_in_progress')],
              ['pending_client', t('service_desk.status_waiting_client')], ['pending_third', t('service_desk.status_pending_third')],
              ['resolved', t('service_desk.status_resolved')], ['closed', t('service_desk.status_closed')], ['cancelled', t('service_desk.status_cancelled')]
            ].map(([v, l]) => <option key={v} value={v}>{l}</option>)}
          </select>
        </div>
        <div className="u-col-full">
          <label htmlFor={`${idCampo}-desc`} className={LS}>{t('common.description')} *</label>
          <AIInlineEditor inputId={`${idCampo}-desc`} value={form.description} onChange={(val: string) => set('description')({ target: { value: val } })} rows={5} className="campo-form tkd-vertical" />
        </div>
        {['resolved', 'closed'].includes(form.status) && (
          <div className="u-col-full">
            <label id={`${idCampo}-et7`} htmlFor={`${idCampo}-7`} className={LS}>{t('service_desk.edit_resolution')}</label>
            <textarea id={`${idCampo}-7`} aria-labelledby={`${idCampo}-et7`} value={form.resolution} onChange={set('resolution')} rows={3} className={IS} />
          </div>
        )}
        <div className="u-col-full">
          <label id={`${idCampo}-et8`} htmlFor={`${idCampo}-8`} className={LS}>{t('service_desk.edit_tags')}</label>
          <input id={`${idCampo}-8`} aria-labelledby={`${idCampo}-et8`} value={form.tags} onChange={set('tags')} className={IS} />
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
          <label id={`${idCampo}-et9`} htmlFor={`${idCampo}-9`} className={LS}>{t('ticketdetail.campos_dinamicos_json')}</label>
          <textarea id={`${idCampo}-9`} aria-labelledby={`${idCampo}-et9`} value={dynamicFieldsText} onChange={e => setDynamicFieldsText(e.target.value)} rows={6} className={`${IS} tkd-input--mono`} />
        </div>
      </div>
    </Modal>
  )
}

// ── TicketDetail (main) ────────────────────────────────────────────────────────
export default function TicketDetail({ ticketId, onClose, embedded = false }: { ticketId: string | null | undefined; onClose: () => void; embedded?: boolean }) {
  const t = useAppT()
  const qc = useQueryClient()
  const toast = useToast()
  const [commentText, setCommentText] = useState('')
  // Nota interna: no la ve el solicitante ni se le envia por correo.
  const [notaInterna, setNotaInterna] = useState(false)
  const [showCanned, setShowCanned] = useState(false)
  const [timeMin, setTimeMin] = useState('')
  const [timeUnit, setTimeUnit] = useState('minutes')
  const [facturable, setFacturable] = useState(false)
  const [editAssign, setEditAssign] = useState(false)
  const [showEdit, setShowEdit] = useState(false)
  const [showSplit, setShowSplit] = useState(false)
  // Resolver pide el texto: es lo que recibe el solicitante en el correo.
  const [resolviendo, setResolviendo] = useState(false)
  const [textoResolucion, setTextoResolucion] = useState('')
  const { user: yo } = useAuth()
  const [sugerencia, setSugerencia] = useState<Sugerencia | null>(null)
  const [rechazando, setRechazando] = useState(false)
  const [motivo, setMotivo] = useState('')

  const { data: ticket, isLoading } = useQuery({
    queryKey: ['sd-ticket', ticketId],
    queryFn: () => ticketsApi.get(ticketId).then(r => r.data),
    enabled: !!ticketId,
    refetchInterval: POLL_FREQUENT_MS,
  })
  const { data: users = [] } = useQuery({
    queryKey: ['users'],
    queryFn: () => usersApi.list().then(r => r.data),
  })
  const { data: links = [] } = useQuery<TicketLink[]>({
    queryKey: ['sd-ticket-links', ticketId],
    queryFn: () => ticketsApi.links(ticketId).then(r => r.data),
    enabled: !!ticketId,
  })

  const invalidate = () => {
    qc.invalidateQueries({ queryKey: ['sd-ticket', ticketId] })
    qc.invalidateQueries({ queryKey: ['sd-tickets'] })
  }

  // UC: solo hace falta mientras se espera a un tercero (o si ya hay contrato).
  const conUc = ticket?.status === 'pending_third' || !!ticket?.uc_contract_id
  const { data: contratosUc = [] } = useQuery({
    queryKey: ['alm-contracts'],
    queryFn: () => almExtApi.contracts().then(r => r.data ?? []),
    enabled: conUc,
    select: (cs: UcContract[]) => cs.filter(c => (c.resolution_hours > 0 || c.response_hours > 0) && c.status === 'active'),
  })
  const { mutate: anotarRespuesta, isPending: anotando } = useMutation({
    mutationFn: () => ticketsApi.update(ticketId, { uc_vendor_responded: true }),
    onSuccess: invalidate,
    onError: e => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })
  const { mutate: elegirUc } = useMutation({
    mutationFn: (id: string) => ticketsApi.update(ticketId, { uc_contract_id: id }),
    onSuccess: invalidate,
    onError: e => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })

  const { mutate: addComment, isPending: commenting } = useMutation({
    mutationFn: () => ticketsApi.comment(ticketId, { body: commentText, is_public: !notaInterna }),
    onSuccess: () => { invalidate(); setCommentText(''); toast.success(t('service_desk.comment_added')) },
    onError: e => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })
  const { mutate: suggestReply, isPending: suggestingReply } = useMutation({
    mutationFn: () => ticketsApi.aiSuggest(ticketId, { content: commentText }),
    onSuccess: res => {
      const datos = res.data
      setSugerencia(datos ?? null)
      const draft = datos?.draft || ''
      // Sin IA se dice, y los articulos y documentos se ensenan igual.
      if (!draft) { toast.error(datos?.ai_error || t('common.error')); return }
      setCommentText(prev => prev ? `${prev}\n\n${draft}` : draft)
    },
    onError: e => toast.error(extractErr(e, t('ticketdetail.error_sugerir'))),
  })
  const { mutate: logTime, isPending: loggingTime } = useMutation({
    mutationFn: () => ticketsApi.timelog(ticketId, { minutes: Number(timeMin), unit: timeUnit, billable: facturable }),
    onSuccess: res => {
      invalidate(); setTimeMin('')
      // Dice si el tiempo llegó a los partes o por qué no: sin eso, el agente
      // daba por imputado lo que se había quedado en el ticket.
      const r = res.data
      if (r?.timesheet === 'created') toast.success(t('sd_cfg.time_to_timesheet', { h: r.hours ?? 0 }))
      else if (r?.timesheet === 'skipped') toast.info(t('sd_cfg.time_not_to_timesheet', { reason: r.reason ?? '' }))
      else toast.success(t('ticketdetail.n_min', { n: timeMin }))
    },
    onError: e => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })
  const { mutate: restorePending, isPending: restoringPending } = useMutation({
    mutationFn: () => ticketsApi.restorePending(ticketId),
    onSuccess: () => { invalidate(); toast.success(t('service_desk.qa_back_ok')) },
    onError: e => toast.error(extractErr(e, t('service_desk.qa_back_error'))),
  })
  const { mutate: updateTicket } = useMutation({
    mutationFn: (data: Record<string, unknown>) => ticketsApi.update(ticketId, data),
    onSuccess: () => { invalidate(); toast.success(t('service_desk.ticket_updated')) },
    onError: e => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })
  const { mutate: escalate } = useMutation({
    mutationFn: () => ticketsApi.escalate(ticketId),
    onSuccess: () => { invalidate(); toast.success(t('service_desk.ticket_escalated')) },
    onError: e => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })
  const { mutate: pauseSLA } = useMutation({
    mutationFn: () => ticketsApi.slaPause(ticketId, { note: t('ticketdetail.nota_pausa_sla') }),
    onSuccess: () => { invalidate(); qc.invalidateQueries({ queryKey: ['sd-sla-events'] }); toast.success(t('service_desk.sla_paused')) },
    onError: e => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })
  const { mutate: resumeSLA } = useMutation({
    mutationFn: () => ticketsApi.slaResume(ticketId),
    onSuccess: () => { invalidate(); qc.invalidateQueries({ queryKey: ['sd-sla-events'] }); toast.success(t('service_desk.sla_resumed')) },
    onError: e => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })

  if (!ticketId) return null

  const colorSla = (estado?: string) => estado === 'breached' ? COLOR.danger
    : estado === 'at_risk' ? COLOR.warning : estado === 'paused' ? 'var(--text-2)' : COLOR.success
  const textoSla = (estado?: string) => estado ? t(`sd_cfg.sla_${estado}`) : ''
  const slaColor = colorSla(ticket?.sla_resolution_status)

  return (
    <div className={embedded ? 'tkd-panel tkd-panel--embedded' : 'tkd-panel tkd-panel--floating'}>
      {/* Header */}
      <div className="tkd-head">
        <div className="tkd-head__top">
          <div>
            {isLoading ? <Spinner /> : <>
              <div className="tkd-head__meta">
                <span className="tkd-head__number">{ticket?.number}</span>
                <span className="u-text3-xs">{ticket?.type_label}</span>
                <PBadge v={ticket?.priority} />
                <SBadge v={ticket?.status ?? ''} />
              </div>
              <div className="tkd-head__title">{ticket?.title}</div>
            </>}
          </div>
          <div className="tkd-head__tools">
            {ticket && (
              <button type="button" onClick={() => setShowEdit(true)}
                className="tkd-edit-btn">
                <span aria-hidden="true">✏</span> {t('common.edit')}
              </button>
            )}
            <button type="button" onClick={onClose} aria-label={t('ticketdetail.cerrar_detalle')} className="tkd-close"><span aria-hidden="true">×</span></button>
          </div>
        </div>
        {ticket && (
          <div className="tkd-qa-row">
            {!['resolved', 'closed', 'cancelled'].includes(ticket.status) && <>
              {ticket.status !== 'in_progress' && (
                <button type="button" onClick={() => updateTicket({ status: 'in_progress' })} className="tkd-qa tkd-qa--accent">▶ {t('sd_cfg.qa_start')}</button>
              )}
              <button type="button" onClick={() => { setTextoResolucion(ticket.resolution || ''); setResolviendo(true) }} className="tkd-qa tkd-qa--success">✓ {t('sd_cfg.qa_resolve')}</button>
              <button type="button" onClick={() => escalate()} className="tkd-qa tkd-qa--warning">↑ {t('sd_cfg.qa_escalate')}</button>
              {(ticket.status === 'pending_client' || ticket.status === 'pending_third') && (
                <button type="button" onClick={() => restorePending()} disabled={restoringPending} className="tkd-qa">↺ {t('service_desk.qa_back_to_previous')}</button>
              )}
              {(ticket.sla_resolution_status === 'paused' || ticket.sla_response_status === 'paused')
                ? <button type="button" onClick={() => resumeSLA()} className="tkd-qa">▶ {t('service_desk.qa_resume_sla')}</button>
                : <button type="button" onClick={() => pauseSLA()} className="tkd-qa">⏸ {t('service_desk.qa_pause_sla')}</button>}
              <button type="button" onClick={() => setShowSplit(true)} className="tkd-qa">✂ {t('service_desk.qa_split')}</button>
            </>}
            {ticket.status === 'resolved' && (
              <button type="button" onClick={() => updateTicket({ status: 'closed' })} className="tkd-qa tkd-qa--muted">✕ {t('ticketdetail.cerrar')}</button>
            )}
          </div>
        )}
      </div>

      {/* Body */}
      <div className="tkd-body">
        {isLoading ? <div className="tkd-loading"><Spinner /></div> : ticket && <>
          {/* Petición madre y tareas de cumplimiento */}
          {ticket.parent && (
            <div className="tkd-parent">
              <a href={`/service-desk?ticket=${ticket.parent.id}`} className="u-accent">{t('sd_cfg.ff_parent', { n: ticket.parent.number })}</a>
            </div>
          )}
          {(ticket.fulfillment_tasks ?? []).length > 0 && (
            <div className="ds-card tkd-ff">
              <div className="tkd-ff__title">{t('sd_cfg.ff_tasks')}</div>
              {ticket.fulfillment_tasks.map(ft => (
                <div key={ft.id} className="tkd-ff__row">
                  <a href={`/service-desk?ticket=${ft.id}`} className="tkd-ff__link">{ft.number}</a>
                  <span className="u-flex1">{ft.title.split(' · ').slice(1).join(' · ') || ft.title}</span>
                  <span className="u-text3">{ft.group_name}{ft.assignee_name ? ` · ${ft.assignee_name}` : ''}</span>
                  {ft.sla_resolution_due && <span className={ft.sla_breached ? 'u-danger u-text3-xs' : 'u-text3-xs'}>{fmtDate(ft.sla_resolution_due)}</span>}
                  <SBadge v={ft.status} />
                </div>
              ))}
              {(ticket.fulfillment_plan ?? []).filter(p => p.status === 'planned').map(p => (
                <div key={p.task_id} className="tkd-ff__row">
                  <span className="u-text3-xs">{t('sd_mercado.etapa_n', { n: p.stage })}</span>
                  <span className="u-flex1">{p.title}</span>
                  <span className="u-text3-xs">{t('sd_mercado.tarea_prevista')}</span>
                </div>
              ))}
            </div>
          )}
          {/* Aprobación del catálogo */}
          {ticket.approval && (
            <AprobacionDelTicket ticket={ticket} yo={yo} rechazando={rechazando} motivo={motivo}
              setRechazando={setRechazando} setMotivo={setMotivo} />
          )}
          {/* SLA status */}
          <div className="tkd-sla" style={colorVar(slaColor)}>
            <div>
              <div className="tkd-eyebrow">{t('service_desk.detail_sla_response')}</div>
              <div className="tkd-sla__value" style={colorVar(colorSla(ticket.sla_response_status))}>
                {textoSla(ticket.sla_response_status)} · {fmtDate(ticket.sla_response_due)}
              </div>
            </div>
            <div>
              <div className="tkd-eyebrow">{t('service_desk.detail_sla_resolution')}</div>
              <div className="tkd-sla__value">
                {textoSla(ticket.sla_resolution_status)} · {fmtDate(ticket.sla_resolution_due)}
              </div>
            </div>
            {ticket.ola_due && (
              <div className="u-col-full">
                <div className="tkd-eyebrow">{t('sd_cfg.ola_of_queue', { group: ticket.assigned_group_name ?? '' })}</div>
                <div className="tkd-sla__value" style={colorVar(colorSla(ticket.ola_breached ? 'breached' : 'ok'))}>
                  {textoSla(ticket.ola_breached ? 'breached' : 'ok')} · {fmtDate(ticket.ola_due)}
                </div>
              </div>
            )}
            {conUc && (
              <div className="u-col-full">
                <label htmlFor="uc-contrato" className="tkd-eyebrow tkd-eyebrow--label">
                  {t('sd_cfg.uc_of_vendor')}
                </label>
                {ticket.uc_response_due && (
                  <div className="tkd-sla__value tkd-sla__value--mb tkd-sla__uc"
                    style={colorVar(ticket.uc_vendor_responded_at ? 'var(--text-2)' : colorSla(ticket.uc_response_breached ? 'breached' : 'ok'))}>
                    <span>{t('sd_cfg.uc_response')}: {ticket.uc_vendor_responded_at
                      ? t('sd_cfg.uc_responded_at', { fecha: fmtDate(ticket.uc_vendor_responded_at) })
                      : `${textoSla(ticket.uc_response_breached ? 'breached' : 'ok')} · ${fmtDate(ticket.uc_response_due)}`}</span>
                    {!ticket.uc_vendor_responded_at && ticket.status === 'pending_third' && (
                      <button type="button" onClick={() => anotarRespuesta()} disabled={anotando} className="tkd-qa">{t('sd_cfg.uc_vendor_responded')}</button>
                    )}
                  </div>
                )}
                {ticket.uc_due && (
                  <div className="tkd-sla__value tkd-sla__value--mb" style={colorVar(colorSla(ticket.uc_breached ? 'breached' : 'ok'))}>
                    {t('sd_cfg.uc_resolution')}: {textoSla(ticket.uc_breached ? 'breached' : 'ok')} · {fmtDate(ticket.uc_due)}
                  </div>
                )}
                <select id="uc-contrato" value={ticket.uc_contract_id ?? ''} onChange={e => e.target.value && elegirUc(e.target.value)}
                  className={`${IS} tkd-input--uc`}>
                  <option value="">{contratosUc.length ? t('sd_cfg.uc_choose') : t('sd_cfg.uc_none')}</option>
                  {contratosUc.map(c => (
                    <option key={c.id} value={c.id}>{c.vendor_name ? `${c.vendor_name} · ` : ''}{c.title} ({[c.response_hours && t('sd_cfg.uc_resp_h', { n: c.response_hours }), c.resolution_hours && t('sd_cfg.uc_hours', { n: c.resolution_hours })].filter(Boolean).join(' / ')})</option>
                  ))}
                </select>
              </div>
            )}
          </div>

          {/* Info grid */}
          <div className="tkd-facts">
            {[
              [t('service_desk.detail_requester'), ticket.requester_name || '—'],
              [t('common.assigned_to'), ticket.assigned_to_name || t('service_desk.unassigned')],
              [t('service_desk.detail_group'), ticket.assigned_group_name || '—'],
              [t('service_desk.detail_project'), ticket.project_name || '—'],
              [t('service_desk.detail_ci'), ticket.ci_name || '—'],
              [t('service_desk.detail_time_spent'), fmtMinutes(ticket.time_spent_minutes)],
              [t('service_desk.detail_created'), fmtDate(ticket.created_at)],
              [t('service_desk.detail_updated'), fmtDate(ticket.updated_at)],
            ].map(([label, val]) => (
              <div key={label} className="tkd-fact">
                <div className="tkd-eyebrow">{label}</div>
                <div className="tkd-fact__value">{val}</div>
              </div>
            ))}
          </div>

          {/* Reasignar */}
          <div className="u-mb-16">
            <button type="button" aria-expanded={editAssign} onClick={() => setEditAssign(e => !e)} className="tkd-link-btn">
              <span aria-hidden="true">{editAssign ? '▼' : '▶'}</span> {t('ticketdetail.reasignar')}
            </button>
            {editAssign && (
              <div className="tkd-assign-row">
                <select aria-label={t('service_desk.detail_select_agent')} onChange={e => e.target.value && updateTicket({ assigned_to_user_id: e.target.value })} className={`${IS} tkd-input--flex1`} defaultValue="">
                  <option value="" disabled>{t('service_desk.detail_select_agent')}</option>
                  {users.map(u => <option key={u.id} value={u.id}>{u.full_name}</option>)}
                </select>
              </div>
            )}
          </div>

          {/* Descripción */}
          <div className="u-mb-20">
            <div className="tkd-section-title">{t('common.description')}</div>
            <div className="tkd-text-box">
              {ticket.description}
            </div>
          </div>

          {ticket.dynamic_fields && Object.keys(ticket.dynamic_fields).length > 0 && (
            <div className="u-mb-20">
              <div className="tkd-section-title">
                {t('ticketdetail.campos_dinamicos')}
              </div>
              <div className="u-grid2-10">
                {Object.entries(ticket.dynamic_fields).map(([k, v]) => (
                  <div key={k} className="tkd-fact">
                    <div className="tkd-eyebrow">{k}</div>
                    <div className="tkd-fact__value tkd-fact__value--pre">{String(v ?? '—')}</div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {ticket.resolution && (
            <div className="u-mb-20">
              <div className="tkd-section-title tkd-section-title--ok">{t('service_desk.edit_resolution')}</div>
              <div className="tkd-resolution">
                {ticket.resolution}
              </div>
            </div>
          )}

          {links.length > 0 && (
            <div className="u-mb-20">
              <div className="tkd-section-title">
                {t('service_desk.detail_linked')} ({links.length})
              </div>
              {links.map(lk => (
                <div key={lk.link_id} className="tkd-link-row">
                  <span className="tkd-link-row__type">{lk.link_type}</span>
                  <span className="tkd-link-row__number">{lk.ticket_number}</span>
                  <span className="tkd-link-row__title">{lk.ticket_title}</span>
                  <SBadge v={lk.ticket_status} />
                </div>
              ))}
            </div>
          )}

          <AvisoDeColision ticketId={ticket.id} escribiendo={commentText.trim().length > 0} />
          <EstadoDeCicloDeVida ticketId={ticket.id} onCambio={invalidate} />
          <ContextoDelCliente ticketId={ticket.id} />
          <PanelIaDelTicket ticketId={ticket.id} tieneGrupo={!!ticket.assigned_group_id} onCambio={invalidate} />

          {/* Licencias y hardware, fase 4: el equipo o la licencia del ticket. */}
          <RecursoDelTicket ticketId={ticket.id} />

          {/* Time logging */}
          <div className="u-mb-20">
            <div className="tkd-section-title">{t('service_desk.detail_log_time')}</div>
            <div className="u-row-8">
              <input type="number" aria-label={t('service_desk.detail_time_spent')} placeholder={t('service_desk.detail_time_spent')} value={timeMin} onChange={e => setTimeMin(e.target.value)} className={`${IS} tkd-input--flex1`} />
              <select aria-label={t('ticketdetail.unidad')} value={timeUnit} onChange={e => setTimeUnit(e.target.value)} className={`${IS} tkd-input--unit`}>
                <option value="minutes">{t('ticketdetail.unidad_min')}</option>
                <option value="hours">{t('ticketdetail.unidad_h')}</option>
                <option value="days">{t('ticketdetail.unidad_d')}</option>
              </select>
              <label className="tkd-check tkd-check--nowrap">
                <input type="checkbox" checked={facturable} onChange={e => setFacturable(e.target.checked)} aria-label={t('sd_cfg.time_billable')} />
                {t('sd_cfg.time_billable')}
              </label>
              <Button onClick={() => logTime()} disabled={loggingTime || !timeMin} loading={loggingTime}>{t('service_desk.detail_add_btn')}</Button>
            </div>
          </div>

          {/* Comments */}
          <div className="u-mb-20">
            <div className="tkd-section-title tkd-section-title--12">
              {t('ticketdetail.comentarios', { n: (ticket.comments || []).length })}
            </div>
            <div className="tkd-comments">
              {(ticket.comments || []).map((c: TicketComment) => (
                <div key={c.id} className="tkd-comment">
                  <div className="tkd-comment__head">
                    <span className="u-text1-sm-600">
                      {c.author_name}
                      {c.is_public === false && <span className="tkd-comment__internal">{t('service_desk.internal_note')}</span>}
                    </span>
                    <span className="u-text3-xs">{fmtDate(c.created_at)}</span>
                  </div>
                  <div className="tkd-comment__body">{c.body}</div>
                </div>
              ))}
            </div>
            <div className="tkd-relative">
              {showCanned && (
                <CannedResponsePicker
                  onSelect={text => setCommentText(prev => prev ? prev + '\n\n' + text : text)}
                  onClose={() => setShowCanned(false)}
                />
              )}
              <textarea aria-label={t('service_desk.detail_send_comment')} placeholder={t('service_desk.detail_send_comment')} value={commentText}
                onChange={e => setCommentText(e.target.value)} rows={3} className={`${IS} tkd-input--comment`} />
            </div>
            <div className="tkd-tools">
              <button type="button" aria-pressed={showCanned} onClick={() => setShowCanned(s => !s)}
                className="tkd-tool">
                {t('ticketdetail.respuestas_rapidas')}
              </button>
              <button type="button" onClick={() => suggestReply()} disabled={suggestingReply}
                className="tkd-tool">
                {suggestingReply ? t('service_desk.detail_ai_generating') : `✨ ${t('sd_cfg.ai_suggest')}`}
              </button>
            </div>
            {sugerencia && <ApoyoDeLaSugerencia s={sugerencia} />}
            <label className="tkd-check tkd-check--mb">
              <input type="checkbox" aria-label={t('service_desk.internal_note')} checked={notaInterna} onChange={e => setNotaInterna(e.target.checked)} />
              {t('service_desk.internal_note')}
            </label>
            <Button onClick={() => addComment()} disabled={commenting || !commentText} loading={commenting} style={FULL_WIDTH_STYLE}>
              {t('service_desk.detail_send_comment')}
            </Button>
          </div>

          <SeguirYFusionar ticketId={ticketId} />
          <div className="u-mb-20"><DocumentsPanel ticketId={ticketId} /></div>
          <div className="u-mb-20"><DocumentosDeFicha ficha="ticket" id={ticketId} sugerir /></div>
          <div className="u-mb-20"><LeccionesDeOrigen origen="ticket" id={ticketId} cerrado={['resolved', 'closed'].includes(String(ticket?.status))} /></div>

          {(ticket.history || []).length > 0 && (
            <div>
              <div className="tkd-section-title tkd-section-title--10">{t('service_desk.detail_history')}</div>
              <div className="u-stack-6">
                {ticket.history.slice(-8).reverse().map((h: TicketHistoryEntry, i: number) => (
                  <div key={i} className="tkd-hist">
                    <span>{`${h.field ?? ''}: ${h.old_value ?? '—'} → ${h.new_value ?? '—'}`}</span>
                    <span className="tkd-hist__date">{fmtDate(h.changed_at)}</span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </>}
      </div>

      {showEdit && ticket && (
        <TicketEditModal
          ticket={ticket}
          onClose={() => setShowEdit(false)}
          onSaved={() => { invalidate(); setShowEdit(false); toast.success(t('service_desk.ticket_updated')) }}
        />
      )}
      {resolviendo && ticket && (
        <Modal open title={`${t('sd_cfg.qa_resolve')} ${ticket.number}`} onClose={() => setResolviendo(false)}>
          <div className="u-stack-12">
            <label htmlFor="sd-resolucion" className={LS}>{t('sd_cfg.qa_resolution')}</label>
            <textarea id="sd-resolucion" aria-label={t('sd_cfg.qa_resolution')} value={textoResolucion} onChange={e => setTextoResolucion(e.target.value)}
              rows={5} className={IS} autoFocus />
            <div className="u-text3-xs">{t('sd_cfg.qa_resolution_hint')}</div>
            <div className="u-actions-10">
              <Button variant="secondary" onClick={() => setResolviendo(false)}>{t('common.cancel')}</Button>
              <Button disabled={!textoResolucion.trim()} onClick={() => {
                updateTicket({ status: 'resolved', resolution: textoResolucion.trim() })
                setResolviendo(false)
              }}>✓ {t('sd_cfg.qa_resolve')}</Button>
            </div>
          </div>
        </Modal>
      )}
      {showSplit && ticket && (
        <SplitTicketModal
          ticket={ticket}
          onClose={() => setShowSplit(false)}
          onCreated={() => { invalidate(); qc.invalidateQueries({ queryKey: ['sd-tickets'] }) }}
        />
      )}
    </div>
  )
}


type Aprobacion = SdAprobacionDeTicket

/** Estado de la aprobación y, para quien la tiene que dar, los botones. */
function AprobacionDelTicket({ ticket, yo, rechazando, motivo, setRechazando, setMotivo }: {
  ticket: { id: string; approval: Aprobacion | null }; yo: { id?: string; role?: string } | null
  rechazando: boolean; motivo: string; setRechazando: (v: boolean) => void; setMotivo: (v: string) => void
}) {
  const t = useAppT()
  const toast = useToast()
  const qc = useQueryClient()
  const a = ticket.approval
  const decidir = useMutation({
    mutationFn: (d: { decision: string; comment?: string }) => sdApprovalsApi.decide(ticket.id, d),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['sd-ticket', ticket.id] })
      qc.invalidateQueries({ queryKey: ['sd-approvals-mine'] })
      setRechazando(false); setMotivo('')
      toast.success(t('sd_cfg.apr_done'))
    },
    onError: (e: unknown) => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })
  if (!a) return null
  const puedeDecidir = a.status === 'pending' && (a.approver_user_id === yo?.id || yo?.role === 'admin')
  const color = a.status === 'approved' ? COLOR.success : a.status === 'rejected' ? COLOR.danger : COLOR.warning
  const texto = a.status === 'pending' ? t('sd_cfg.apr_pending', { name: a.approver_name ?? '—' })
    : t(a.status === 'approved' ? 'sd_cfg.apr_approved' : 'sd_cfg.apr_rejected', { name: a.decided_by_name ?? '—' })
  return (
    <div role="status" className="tkd-approval" style={colorVar(color)}>
      <div className="tkd-approval__text">{texto}</div>
      {a.comment && <div className="u-text2-sm">{a.comment}</div>}
      {puedeDecidir && !rechazando && (
        <div className="u-row-8">
          <Button onClick={() => decidir.mutate({ decision: 'approved' })} loading={decidir.isPending}>{t('sd_cfg.apr_approve')}</Button>
          <Button variant="secondary" onClick={() => setRechazando(true)}>{t('sd_cfg.apr_reject')}</Button>
        </div>
      )}
      {puedeDecidir && rechazando && (
        <div className="u-stack-8">
          <label htmlFor="apr-motivo" className={LS}>{t('sd_cfg.apr_reason')}</label>
          <textarea id="apr-motivo" aria-label={t('sd_cfg.apr_reason')} value={motivo} onChange={e => setMotivo(e.target.value)} rows={3}
            className={IS} autoFocus />
          <div className="u-row-8">
            <Button variant="secondary" onClick={() => setRechazando(false)}>{t('common.cancel')}</Button>
            <Button disabled={!motivo.trim()} loading={decidir.isPending}
              onClick={() => decidir.mutate({ decision: 'rejected', comment: motivo.trim() })}>{t('sd_cfg.apr_reject')}</Button>
          </div>
        </div>
      )}
    </div>
  )
}


type Sugerencia = SdSugerenciaIA

/** Lo que acompaña al borrador: artículos y documentos en que apoyarse. */
function ApoyoDeLaSugerencia({ s }: { s: Sugerencia }) {
  const t = useAppT()
  return (
    <div className="ds-card tkd-card-stack">
      {s.ai_error && <div role="status" className="tkd-warning">{s.ai_error}</div>}
      {(s.kb_matches ?? []).length > 0 && (
        <div>
          <div className="tkd-ai-title">{t('sd_cfg.ai_related')}</div>
          {(s.kb_matches ?? []).map(k => <div key={k.id}><strong>{k.number}</strong> {k.title}</div>)}
        </div>
      )}
      {s.documents_configured && (
        <div>
          <div className="tkd-ai-title">{t('sd_cfg.ai_documents')}</div>
          {s.documents_error ? <div className="tkd-warning">{s.documents_error}</div>
            : (s.documents ?? []).length === 0 ? <div className="u-text3">{t('sd_cfg.ai_no_documents')}</div>
            : (s.documents ?? []).map(d => (
              <div key={d.document_id} className="tkd-mb-4">
                <strong>{d.title}</strong>
                <div className="u-text2">{d.snippet}</div>
              </div>
            ))}
        </div>
      )}
    </div>
  )
}


/** Seguir el ticket (recibir sus avisos sin ser el agente) y fusionar duplicados. */
function SeguirYFusionar({ ticketId }: { ticketId: string }) {
  const t = useAppT()
  const toast = useToast()
  const qc = useQueryClient()
  const { user } = useAuth()
  const [numero, setNumero] = useState('')
  const [motivo, setMotivo] = useState('')
  const { data: seguidores = [] } = useQuery<{ user_id: string; user_name?: string }[]>({
    queryKey: ['sd-ticket-watchers', ticketId],
    queryFn: () => ticketsApi.watchers(ticketId).then(r => r.data),
  })
  const sigo = seguidores.some(s => s.user_id === user?.id)
  const err = (e: unknown) => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK))
  const alternar = useMutation({
    mutationFn: () => sigo ? ticketsApi.unwatch(ticketId) : ticketsApi.watch(ticketId),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['sd-ticket-watchers', ticketId] }), onError: err,
  })
  const fusionar = useMutation({
    mutationFn: async () => {
      const buscado = numero.trim().toUpperCase()
      const lista = await ticketsApi.list({ search: buscado, page_size: TICKET_LINK_SEARCH_LIMIT }).then(r => r.data)
      const duplicado = lista.find(x => x.number === buscado && x.id !== ticketId)
      if (!duplicado) throw new Error(t('sd_cfg.m_not_found'))
      await ticketsApi.mergeInto(ticketId, { merged_ticket_id: duplicado.id, reason: motivo || null })
      return buscado
    },
    onSuccess: (n: string) => { setNumero(''); setMotivo(''); qc.invalidateQueries({ queryKey: ['sd-ticket', ticketId] }); toast.success(t('sd_cfg.m_done', { n })) },
    onError: (e: unknown) => toast.error(e instanceof Error && e.message ? e.message : extractErr(e, GENERIC_ERROR_FALLBACK)),
  })
  return (
    <div className="ds-card tkd-card-stack tkd-card-stack--16">
      <div className="tkd-watch-row">
        <span className="tkd-watchers">
          <strong>{t('sd_cfg.w_followers')}:</strong> {seguidores.length ? seguidores.map(s => s.user_name).join(', ') : t('sd_cfg.w_nobody')}
        </span>
        <Button variant="secondary" onClick={() => alternar.mutate()} loading={alternar.isPending}>{sigo ? t('sd_cfg.w_unfollow') : t('sd_cfg.w_follow')}</Button>
      </div>
      <div className="u-wrap-center-8">
        <span className="u-600">{t('sd_cfg.m_title')}</span>
        <input aria-label={t('sd_cfg.m_number')} placeholder={t('sd_cfg.m_number')} value={numero} onChange={e => setNumero(e.target.value)}
          className={`${IS} tkd-input--merge-n`} />
        <input aria-label={t('sd_cfg.m_reason')} placeholder={t('sd_cfg.m_reason')} value={motivo} onChange={e => setMotivo(e.target.value)}
          className={`${IS} tkd-input--merge-r`} />
        <Button variant="secondary" disabled={!numero.trim()} loading={fusionar.isPending} onClick={() => fusionar.mutate()}>{t('sd_cfg.m_do')}</Button>
      </div>
    </div>
  )
}
