import type { CSSProperties } from 'react'
import { useMemo, useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useAppT } from '../../i18n/AppLangContext'
import { useToast } from '../../context/ToastContext'
import { extractErr } from '../../utils/helpers'
import { GENERIC_ERROR_FALLBACK } from '../../constants/errors'
import { Button, Spinner, Modal } from '../../components/ui'
import AIInlineEditorRaw from '../../components/AIInlineEditor'
import DocumentsPanelRaw from '../../components/DocumentsPanel'
import { COLOR, alpha } from '../../constants/theme'
import { almExtApi, sdApprovalsApi, sdCannedApi, ticketsApi, usersApi } from '../../services/api'
import { useAuth } from '../../context/AuthContext'
import { PBadge, SBadge, fmtDate, fmtMinutes, INPUT_STYLE, LABEL_STYLE } from './sdUtils'

// Loosely-typed aliases: these components still infer their props as required.
const AIInlineEditor = AIInlineEditorRaw as unknown as (props: Record<string, unknown>) => JSX.Element
const DocumentsPanel = DocumentsPanelRaw as unknown as (props: Record<string, unknown>) => JSX.Element
const IS_STYLE = INPUT_STYLE as CSSProperties
const LS_STYLE = LABEL_STYLE as CSSProperties

type TicketShape = { [k: string]: unknown; id: string; number?: string | number; title?: string; description?: string; status?: string }

// ── CannedResponsePicker ──────────────────────────────────────────────────────
interface CannedResponse {
  id: string; title?: string; body?: string; category?: string; shortcut?: string
}
function CannedResponsePicker({ onSelect, onClose }: { onSelect: (body: string) => void; onClose: () => void }) {
  const t = useAppT()
  const [search, setSearch] = useState('')
  const { data: responses = [] } = useQuery<CannedResponse[]>({
    queryKey: ['canned-responses', search],
    queryFn: () => sdCannedApi.list(search ? { search } : {}).then((r: { data: CannedResponse[] }) => r.data).catch(() => []),
    staleTime: 60000,
  })
  const cats: string[] = Array.from<string>(new Set(responses.map((r) => String(r.category || 'General')))).sort()
  return (
    <div style={{
      position: 'absolute', bottom: '100%', left: 0, right: 0, marginBottom: 4,
      background: 'var(--surface-1)', border: '1px solid var(--surface-4)', borderRadius: 10,
      boxShadow: '0 -4px 20px rgba(0,0,0,0.3)', zIndex: 100, maxHeight: 340, overflow: 'hidden',
      display: 'flex', flexDirection: 'column',
    }}>
      <div style={{ padding: '10px 12px', borderBottom: '1px solid var(--surface-4)' }}>
        <input autoFocus value={search} onChange={e => setSearch(e.target.value)}
          aria-label={t('service_desk.canned_search')}
          placeholder={t('service_desk.canned_search')}
          style={{ width: '100%', background: 'var(--surface-3)', border: '1px solid var(--surface-4)', borderRadius: 6, padding: '7px 10px', color: 'var(--text-1)', fontSize: "var(--text-base)", outline: 'none', fontFamily: 'inherit', boxSizing: 'border-box' }} />
      </div>
      <div style={{ overflowY: 'auto', flex: 1 }}>
        {responses.length === 0 ? (
          <div style={{ padding: '20px', textAlign: 'center', fontSize: "var(--text-sm)", color: 'var(--text-3)' }}>
            {search ? t('service_desk.canned_no_results') : t('service_desk.canned_empty')}
          </div>
        ) : cats.map(cat => {
          const catItems = responses.filter(r => (r.category || 'General') === cat)
          if (!catItems.length) return null
          return (
            <div key={cat}>
              <div style={{ padding: '6px 12px 2px', fontSize: "var(--text-2xs)", fontWeight: 700, color: 'var(--text-3)', textTransform: 'uppercase', letterSpacing: '0.07em' }}>{cat}</div>
              {catItems.map(r => (
                <button key={r.id} onClick={() => { onSelect(r.body || ''); onClose() }}
                  aria-label={r.title || t('service_desk.detail_send_comment')}
                  style={{ width: '100%', textAlign: 'left', padding: '8px 12px', cursor: 'pointer', borderBottom: '1px solid var(--surface-4)', borderTop: 'none', borderLeft: 'none', borderRight: 'none', background: 'transparent' }}
                  onMouseEnter={e => e.currentTarget.style.background = 'var(--surface-3)'}
                  onMouseLeave={e => e.currentTarget.style.background = 'transparent'}>
                  <div style={{ fontSize: "var(--text-base)", fontWeight: 600, color: 'var(--text-1)', marginBottom: 2 }}>
                    {r.shortcut && <span style={{ fontSize: "var(--text-xs)", color: 'var(--accent)', marginRight: 6, fontFamily: 'var(--font-mono)' }}>{r.shortcut}</span>}
                    {r.title}
                  </div>
                  <div style={{ fontSize: "var(--text-xs)", color: 'var(--text-2)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{r.body?.slice(0, 80)}</div>
                </button>
              ))}
            </div>
          )
        })}
      </div>
      <div style={{ padding: '6px 12px', borderTop: '1px solid var(--surface-4)', textAlign: 'right' }}>
        <button onClick={onClose} style={{ fontSize: "var(--text-xs)", color: 'var(--text-3)', background: 'none', border: 'none', cursor: 'pointer', fontFamily: 'inherit' }}>{t('service_desk.canned_cancel_esc')}</button>
      </div>
    </div>
  )
}

// ── SplitTicketModal ──────────────────────────────────────────────────────────
function SplitTicketModal({ ticket, onClose, onCreated }: { ticket: TicketShape; onClose: () => void; onCreated?: (data: unknown) => void }) {
  const t = useAppT()
  const toast = useToast()
  const [form, setForm] = useState({
    new_title: '', new_description: ticket?.description || '',
    keep_original_description: ticket?.description || '', tags: '',
  })
  const { mutate, isPending } = useMutation({
    mutationFn: (data: Record<string, unknown>) => ticketsApi.split(ticket.id, data),
    onSuccess: res => {
      toast.success(`${t('service_desk.ticket_created_success')} ${res?.data?.child?.number || ''}`)
      onCreated?.(res?.data)
      onClose()
    },
    onError: e => toast.error(extractErr(e, t('common.error'))),
  })
  const IS = IS_STYLE
  const LS = LS_STYLE
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
    <Modal open title={`✂ Dividir ticket ${ticket?.number}`} onClose={onClose}>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
        <div style={{ padding: '10px 14px', background: 'var(--surface-1)', borderRadius: 8, border: '1px solid var(--surface-4)', fontSize: "var(--text-sm)", color: 'var(--text-2)' }}>
          {t('service_desk.split_desc_original')} <strong style={{ color: 'var(--text-1)' }}>{ticket?.number}</strong>.
        </div>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 14 }}>
          <div>
            <label style={LS}>{t('service_desk.split_title_lbl')} *</label>
            <input value={form.new_title} onChange={e => setForm(f => ({ ...f, new_title: e.target.value }))} style={IS} autoFocus />
          </div>
          <div>
            <label style={LS}>{t('service_desk.split_tags_lbl')}</label>
            <input value={form.tags} onChange={e => setForm(f => ({ ...f, tags: e.target.value }))} style={IS} />
          </div>
        </div>
        <div>
          <label style={LS}>{t('service_desk.split_desc_child')}</label>
          <textarea value={form.new_description} onChange={e => setForm(f => ({ ...f, new_description: e.target.value }))} rows={4} style={{ ...IS, resize: 'vertical' }} />
        </div>
        <div>
          <label style={LS}>{t('service_desk.split_desc_original')}</label>
          <textarea value={form.keep_original_description} onChange={e => setForm(f => ({ ...f, keep_original_description: e.target.value }))} rows={4} style={{ ...IS, resize: 'vertical' }} />
        </div>
        <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 10 }}>
          <Button variant="secondary" onClick={onClose}>{t('common.cancel')}</Button>
          <Button onClick={handleSave} disabled={isPending || !form.new_title.trim()} loading={isPending}>✂ {t('service_desk.split_create_btn')}</Button>
        </div>
      </div>
    </Modal>
  )
}

// ── TicketEditModal ───────────────────────────────────────────────────────────
function TicketEditModal({ ticket, onClose, onSaved }: { ticket: TicketShape; onClose: () => void; onSaved: () => void }) {
  const t = useAppT()
  const toast = useToast()
  const initialDynamic = useMemo(() => {
    const raw = ticket?.dynamic_fields
    if (!raw || typeof raw !== 'object') return '{}'
    try { return JSON.stringify(raw, null, 2) } catch { return '{}' }
  }, [ticket?.dynamic_fields])
  const [form, setForm] = useState({
    title: (ticket.title as string) || '', description: (ticket.description as string) || '',
    priority: (ticket.priority as string) || 'p3_medium', ticket_type: (ticket.ticket_type as string) || 'incident',
    urgency: (ticket.urgency as string) || 'medium', impact: (ticket.impact as string) || 'user',
    status: (ticket.status as string) || 'new', resolution: (ticket.resolution as string) || '', tags: (ticket.tags as string) || '',
  })
  const [dynamicFieldsText, setDynamicFieldsText] = useState(initialDynamic)
  const { mutate, isPending } = useMutation({
    mutationFn: (data: Record<string, unknown>) => ticketsApi.update(ticket.id, data),
    onSuccess: onSaved,
    onError: e => toast.error(extractErr(e, 'Error al guardar')),
  })
  const set = (k: string) => (e: { target: { value: string } }) => setForm(f => ({ ...f, [k]: e.target.value }))
  const IS = IS_STYLE
  const LS = LS_STYLE
  return (
    <Modal open title={`${t('common.edit')} ${ticket.number}`} onClose={onClose} size="lg">
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 14, maxHeight: '75vh', overflowY: 'auto', paddingRight: 4 }}>
        <div style={{ gridColumn: '1/-1' }}>
          <label style={LS}>{t('service_desk.ticket_title')} *</label>
          <input value={form.title} onChange={set('title')} style={IS} />
        </div>
        <div>
          <label style={LS}>{t('service_desk.ticket_type')}</label>
          <select value={form.ticket_type} onChange={set('ticket_type')} style={IS}>
            {[['incident', `🔴 ${t('service_desk.type_incident')}`], ['service_request', `🔵 ${t('service_desk.type_service_request')}`],
              ['change', `🟡 ${t('service_desk.type_change')}`], ['problem', `🟠 ${t('service_desk.type_problem')}`], ['question', `⚪ ${t('service_desk.type_question')}`]
            ].map(([v, l]) => <option key={v} value={v}>{l}</option>)}
          </select>
        </div>
        <div>
          <label style={LS}>{t('service_desk.ticket_priority')}</label>
          <select value={form.priority} onChange={set('priority')} style={IS}>
            {[['p1_critical', `🔴 ${t('service_desk.priority_p1')}`], ['p2_high', `🟠 ${t('service_desk.priority_p2')}`],
              ['p3_medium', `🟡 ${t('service_desk.priority_p3')}`], ['p4_low', `⚪ ${t('service_desk.priority_p4')}`]
            ].map(([v, l]) => <option key={v} value={v}>{l}</option>)}
          </select>
        </div>
        <div>
          <label style={LS}>{t('service_desk.edit_urgency')}</label>
          <select value={form.urgency} onChange={set('urgency')} style={IS}>
            {[['critical', t('service_desk.urgency_critical')], ['high', t('service_desk.urgency_high')], ['medium', t('service_desk.urgency_medium')], ['low', t('service_desk.urgency_low')]].map(([v, l]) => <option key={v} value={v}>{l}</option>)}
          </select>
        </div>
        <div>
          <label style={LS}>{t('service_desk.edit_impact')}</label>
          <select value={form.impact} onChange={set('impact')} style={IS}>
            {[['enterprise', t('service_desk.impact_enterprise')], ['department', t('service_desk.impact_department')], ['user', t('service_desk.impact_user')], ['minimal', t('service_desk.impact_minimal')]].map(([v, l]) => <option key={v} value={v}>{l}</option>)}
          </select>
        </div>
        <div>
          <label style={LS}>{t('common.status')}</label>
          <select value={form.status} onChange={set('status')} style={IS}>
            {[['new', t('service_desk.status_new')], ['assigned', t('service_desk.status_assigned')], ['in_progress', t('service_desk.status_in_progress')],
              ['pending_client', t('service_desk.status_waiting_client')], ['pending_third', t('service_desk.status_pending_change')],
              ['resolved', t('service_desk.status_resolved')], ['closed', t('service_desk.status_closed')], ['cancelled', t('service_desk.status_cancelled')]
            ].map(([v, l]) => <option key={v} value={v}>{l}</option>)}
          </select>
        </div>
        <div style={{ gridColumn: '1/-1' }}>
          <label style={LS}>{t('common.description')} *</label>
          <AIInlineEditor value={form.description} onChange={(val: string) => set('description')({ target: { value: val } })} rows={5} style={{ ...IS, resize: 'vertical' }} />
        </div>
        {['resolved', 'closed'].includes(form.status) && (
          <div style={{ gridColumn: '1/-1' }}>
            <label style={LS}>{t('service_desk.edit_resolution')}</label>
            <textarea value={form.resolution} onChange={set('resolution')} rows={3} style={{ ...IS, resize: 'vertical' }} />
          </div>
        )}
        <div style={{ gridColumn: '1/-1' }}>
          <label style={LS}>{t('service_desk.edit_tags')}</label>
          <input value={form.tags} onChange={set('tags')} style={IS} />
        </div>
        <div style={{ gridColumn: '1/-1', display: 'flex', justifyContent: 'flex-end', gap: 10 }}>
          <Button variant="secondary" onClick={onClose}>{t('common.cancel')}</Button>
          <Button onClick={() => {
            let parsedDynamic = {}
            try {
              parsedDynamic = JSON.parse(dynamicFieldsText || '{}')
              if (!parsedDynamic || typeof parsedDynamic !== 'object' || Array.isArray(parsedDynamic)) {
                toast.error('Campos dinámicos inválidos: se esperaba un objeto JSON')
                return
              }
            } catch {
              toast.error('Campos dinámicos inválidos: JSON no válido')
              return
            }
            mutate({ ...form, dynamic_fields: parsedDynamic })
          }} disabled={isPending || !form.title.trim() || !form.description.trim()} loading={isPending}>
            {t('common.save')}
          </Button>
        </div>
        <div style={{ gridColumn: '1/-1' }}>
          <label style={LS}>{t('ticketdetail.campos_dinamicos_json')}</label>
          <textarea value={dynamicFieldsText} onChange={e => setDynamicFieldsText(e.target.value)} rows={6} style={{ ...IS, resize: 'vertical', fontFamily: 'var(--font-mono)' }} />
        </div>
      </div>
    </Modal>
  )
}

// ── TicketDetail (main) ────────────────────────────────────────────────────────
// Estilo "ghost" alineado con el resto de la app (mismo que ImportPage "Descargar plantilla")
const qaBtnStyle = {
  padding: '5px 12px', borderRadius: 6,
  border: '1px solid var(--accent-border)',
  background: 'transparent', color: 'var(--accent)',
  fontSize: "var(--text-xs)", fontWeight: 600,
  cursor: 'pointer', fontFamily: 'inherit',
}

export default function TicketDetail({ ticketId, onClose, embedded = false }: { ticketId: string | null | undefined; onClose: () => void; embedded?: boolean }) {
  const t = useAppT()
  const qc = useQueryClient()
  const toast = useToast()
  const [commentText, setCommentText] = useState('')
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
    refetchInterval: 30000,
  })
  const { data: users = [] } = useQuery({
    queryKey: ['users'],
    queryFn: () => usersApi.list().then(r => r.data),
  })
  const { data: links = [] } = useQuery({
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
    select: (cs: any[]) => cs.filter(c => c.resolution_hours > 0 && c.status === 'active'),
  })
  const { mutate: elegirUc } = useMutation({
    mutationFn: (id: string) => ticketsApi.update(ticketId, { uc_contract_id: id }),
    onSuccess: invalidate,
    onError: e => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })

  const { mutate: addComment, isPending: commenting } = useMutation({
    mutationFn: () => ticketsApi.comment(ticketId, { body: commentText, is_internal: false }),
    onSuccess: () => { invalidate(); setCommentText(''); toast.success(t('service_desk.comment_added')) },
    onError: e => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })
  const { mutate: suggestReply, isPending: suggestingReply } = useMutation({
    mutationFn: () => ticketsApi.aiSuggest(ticketId, { content: commentText }),
    onSuccess: res => {
      const datos = res?.data as Sugerencia | undefined
      setSugerencia(datos ?? null)
      const draft = datos?.draft || ''
      // Sin IA se dice, y los articulos y documentos se ensenan igual.
      if (!draft) { toast.error(datos?.ai_error || t('common.error')); return }
      setCommentText(prev => prev ? `${prev}\n\n${draft}` : draft)
    },
    onError: e => toast.error(extractErr(e, 'Error al sugerir respuesta IA')),
  })
  const { mutate: logTime, isPending: loggingTime } = useMutation({
    mutationFn: () => ticketsApi.timelog(ticketId, { minutes: Number(timeMin), unit: timeUnit, billable: facturable }),
    onSuccess: res => {
      invalidate(); setTimeMin('')
      // Dice si el tiempo llegó a los partes o por qué no: sin eso, el agente
      // daba por imputado lo que se había quedado en el ticket.
      const r = res?.data as { timesheet?: string; hours?: number; reason?: string } | undefined
      if (r?.timesheet === 'created') toast.success(t('sd_cfg.time_to_timesheet', { h: r.hours ?? 0 }))
      else if (r?.timesheet === 'skipped') toast.info(t('sd_cfg.time_not_to_timesheet', { reason: r.reason ?? '' }))
      else toast.success(`${timeMin} min`)
    },
    onError: e => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })
  const { mutate: restorePending, isPending: restoringPending } = useMutation({
    mutationFn: () => ticketsApi.restorePending(ticketId),
    onSuccess: () => { invalidate(); toast.success('Estado previo restaurado') },
    onError: e => toast.error(extractErr(e, 'Error al restaurar estado pendiente')),
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
    mutationFn: () => ticketsApi.slaPause(ticketId, { note: 'Esperando respuesta del cliente' }),
    onSuccess: () => { invalidate(); qc.invalidateQueries({ queryKey: ['sd-sla-events'] }); toast.success(t('service_desk.sla_paused')) },
    onError: e => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })
  const { mutate: resumeSLA } = useMutation({
    mutationFn: () => ticketsApi.slaResume(ticketId),
    onSuccess: () => { invalidate(); qc.invalidateQueries({ queryKey: ['sd-sla-events'] }); toast.success(t('service_desk.sla_resumed')) },
    onError: e => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })

  if (!ticketId) return null

  const IS = IS_STYLE
  const colorSla = (estado?: string) => estado === 'breached' ? COLOR.danger
    : estado === 'at_risk' ? COLOR.warning : estado === 'paused' ? 'var(--text-2)' : COLOR.success
  const textoSla = (estado?: string) => estado ? t(`sd_cfg.sla_${estado}`) : ''
  const slaColor = colorSla(ticket?.sla_resolution_status)

  return (
    <div style={embedded ? {
      height: 'calc(100vh - 210px)', minHeight: 520, background: 'var(--surface-0)',
      border: '1px solid var(--surface-4)', borderRadius: 12, display: 'flex', flexDirection: 'column', overflow: 'hidden',
    } : {
      position: 'fixed', top: 12, right: 12, width: 560, maxWidth: 'calc(100vw - 24px)', maxHeight: 'calc(100vh - 24px)',
      background: 'var(--surface-0)', border: '1px solid var(--surface-4)', borderRadius: 12,
      zIndex: 200, display: 'flex', flexDirection: 'column', overflow: 'hidden',
      boxShadow: '-8px 0 32px rgba(0,0,0,0.25)',
    }}>
      {/* Header */}
      <div style={{ padding: '16px 20px', borderBottom: '1px solid var(--surface-4)', background: 'var(--surface-1)', position: 'sticky', top: 0, zIndex: 10 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
          <div>
            {isLoading ? <Spinner /> : <>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 6 }}>
                <span style={{ fontSize: "var(--text-sm)", color: 'var(--accent)', fontWeight: 700 }}>{ticket?.number}</span>
                <span style={{ fontSize: "var(--text-xs)", color: 'var(--text-3)' }}>{ticket?.type_label}</span>
                <PBadge v={ticket?.priority} />
                <SBadge v={ticket?.status} />
              </div>
              <div style={{ fontSize: "var(--text-md-em)", fontWeight: 600, color: 'var(--text-1)', lineHeight: 1.3 }}>{ticket?.title}</div>
            </>}
          </div>
          <div style={{ display: 'flex', gap: 6, alignItems: 'center', flexShrink: 0 }}>
            {ticket && (
              <button onClick={() => setShowEdit(true)}
                style={{ background: 'var(--accent-muted)', border: '1px solid var(--accent-glow)', borderRadius: 6, padding: '4px 10px', color: 'var(--accent)', fontSize: "var(--text-sm)", cursor: 'pointer', fontFamily: 'inherit', fontWeight: 600 }}>
                ✏ Editar
              </button>
            )}
            <button onClick={onClose} style={{ background: 'none', border: 'none', color: 'var(--text-2)', fontSize: "var(--text-xl)", cursor: 'pointer', padding: '0 4px', lineHeight: 1 }}>×</button>
          </div>
        </div>
        {ticket && (
          <div style={{ display: 'flex', gap: 6, marginTop: 12, flexWrap: 'wrap' }}>
            {!['resolved', 'closed', 'cancelled'].includes(ticket.status) && <>
              {ticket.status !== 'in_progress' && (
                <button onClick={() => updateTicket({ status: 'in_progress' })} style={{ ...qaBtnStyle, background: alpha(COLOR.accent, '20'), color: COLOR.accent }}>▶ {t('sd_cfg.qa_start')}</button>
              )}
              <button onClick={() => { setTextoResolucion(ticket.resolution || ''); setResolviendo(true) }} style={{ ...qaBtnStyle, background: alpha(COLOR.success, '20'), color: COLOR.success }}>✓ {t('sd_cfg.qa_resolve')}</button>
              <button onClick={() => escalate()} style={{ ...qaBtnStyle, background: alpha(COLOR.warning, '20'), color: COLOR.warning }}>↑ {t('sd_cfg.qa_escalate')}</button>
              {(ticket.status === 'pending_client' || ticket.status === 'pending_third') && (
                <button onClick={() => restorePending()} disabled={restoringPending} style={qaBtnStyle}>↺ Restaurar pendiente</button>
              )}
              {ticket.sla_paused_at
                ? <button onClick={() => resumeSLA()} style={qaBtnStyle}>▶ {t('service_desk.sla_resumed')}</button>
                : <button onClick={() => pauseSLA()} style={qaBtnStyle}>⏸ {t('service_desk.sla_paused')}</button>}
              <button onClick={() => setShowSplit(true)} style={qaBtnStyle}>✂ {t('service_desk.split_title_lbl')}</button>
            </>}
            {ticket.status === 'resolved' && (
              <button onClick={() => updateTicket({ status: 'closed' })} style={{ ...qaBtnStyle, background: alpha(COLOR.text2, '20'), color: 'var(--text-2)' }}>✕ Cerrar</button>
            )}
          </div>
        )}
      </div>

      {/* Body */}
      <div style={{ flex: 1, padding: '20px', overflowY: 'auto' }}>
        {isLoading ? <div style={{ padding: 40, textAlign: 'center' }}><Spinner /></div> : ticket && <>
          {/* Petición madre y tareas de cumplimiento */}
          {ticket.parent && (
            <div style={{ fontSize: 'var(--text-sm)', marginBottom: 12 }}>
              <a href={`/service-desk?ticket=${ticket.parent.id}`} style={{ color: 'var(--accent)' }}>{t('sd_cfg.ff_parent', { n: ticket.parent.number })}</a>
            </div>
          )}
          {(ticket.fulfillment_tasks ?? []).length > 0 && (
            <div className="ds-card" style={{ padding: 12, marginBottom: 16, fontSize: 'var(--text-sm)' }}>
              <div style={{ fontWeight: 700, marginBottom: 6 }}>{t('sd_cfg.ff_tasks')}</div>
              {(ticket.fulfillment_tasks as { id: string; number: string; title: string; status: string; group_name?: string; assignee_name?: string }[]).map(ft => (
                <div key={ft.id} style={{ display: 'flex', gap: 8, padding: '3px 0' }}>
                  <a href={`/service-desk?ticket=${ft.id}`} style={{ color: 'var(--accent)', fontWeight: 600 }}>{ft.number}</a>
                  <span style={{ flex: 1 }}>{ft.title.split(' · ').slice(1).join(' · ') || ft.title}</span>
                  <span style={{ color: 'var(--text-3)' }}>{ft.group_name}{ft.assignee_name ? ` · ${ft.assignee_name}` : ''}</span>
                  <SBadge v={ft.status} />
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
          <div style={{ background: 'var(--surface-2)', border: `1px solid ${alpha(slaColor, '40')}`, borderRadius: 10, padding: '12px 16px', marginBottom: 16, display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
            <div>
              <div style={{ fontSize: "var(--text-2xs)", color: 'var(--text-3)', textTransform: 'uppercase', marginBottom: 2 }}>{t('service_desk.detail_sla_response')}</div>
              <div style={{ fontSize: "var(--text-sm)", fontWeight: 600, color: colorSla(ticket.sla_response_status) }}>
                {textoSla(ticket.sla_response_status)} · {fmtDate(ticket.sla_response_due)}
              </div>
            </div>
            <div>
              <div style={{ fontSize: "var(--text-2xs)", color: 'var(--text-3)', textTransform: 'uppercase', marginBottom: 2 }}>{t('service_desk.detail_sla_resolution')}</div>
              <div style={{ fontSize: "var(--text-sm)", fontWeight: 600, color: slaColor }}>
                {textoSla(ticket.sla_resolution_status)} · {fmtDate(ticket.sla_resolution_due)}
              </div>
            </div>
            {ticket.ola_due && (
              <div style={{ gridColumn: '1 / -1' }}>
                <div style={{ fontSize: "var(--text-2xs)", color: 'var(--text-3)', textTransform: 'uppercase', marginBottom: 2 }}>{t('sd_cfg.ola_of_queue', { group: ticket.assigned_group_name ?? '' })}</div>
                <div style={{ fontSize: "var(--text-sm)", fontWeight: 600, color: colorSla(ticket.ola_breached ? 'breached' : 'ok') }}>
                  {textoSla(ticket.ola_breached ? 'breached' : 'ok')} · {fmtDate(ticket.ola_due)}
                </div>
              </div>
            )}
            {conUc && (
              <div style={{ gridColumn: '1 / -1' }}>
                <label htmlFor="uc-contrato" style={{ display: 'block', fontSize: "var(--text-2xs)", color: 'var(--text-3)', textTransform: 'uppercase', marginBottom: 2 }}>
                  {t('sd_cfg.uc_of_vendor')}
                </label>
                {ticket.uc_due && (
                  <div style={{ fontSize: "var(--text-sm)", fontWeight: 600, marginBottom: 4, color: colorSla(ticket.uc_breached ? 'breached' : 'ok') }}>
                    {textoSla(ticket.uc_breached ? 'breached' : 'ok')} · {fmtDate(ticket.uc_due)}
                  </div>
                )}
                <select id="uc-contrato" value={ticket.uc_contract_id ?? ''} onChange={e => e.target.value && elegirUc(e.target.value)}
                  style={{ ...IS_STYLE, padding: '6px 10px' }}>
                  <option value="">{contratosUc.length ? t('sd_cfg.uc_choose') : t('sd_cfg.uc_none')}</option>
                  {contratosUc.map((c: any) => (
                    <option key={c.id} value={c.id}>{c.vendor_name ? `${c.vendor_name} · ` : ''}{c.title} ({t('sd_cfg.uc_hours', { n: c.resolution_hours })})</option>
                  ))}
                </select>
              </div>
            )}
          </div>

          {/* Info grid */}
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10, marginBottom: 16 }}>
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
              <div key={label} style={{ background: 'var(--surface-2)', borderRadius: 8, padding: '10px 12px' }}>
                <div style={{ fontSize: "var(--text-2xs)", color: 'var(--text-3)', textTransform: 'uppercase', marginBottom: 2 }}>{label}</div>
                <div style={{ fontSize: "var(--text-sm)", color: 'var(--text-1)', fontWeight: 500 }}>{val}</div>
              </div>
            ))}
          </div>

          {/* Reasignar */}
          <div style={{ marginBottom: 16 }}>
            <button onClick={() => setEditAssign(e => !e)} style={{ fontSize: "var(--text-sm)", color: 'var(--accent)', background: 'none', border: 'none', cursor: 'pointer', padding: 0 }}>
              {editAssign ? '▼' : '▶'} Reasignar ticket
            </button>
            {editAssign && (
              <div style={{ display: 'flex', gap: 8, marginTop: 8 }}>
                <select aria-label={t('service_desk.detail_select_agent')} onChange={e => e.target.value && updateTicket({ assigned_to_user_id: e.target.value })} style={{ ...IS, flex: 1 }} defaultValue="">
                  <option value="" disabled>{t('service_desk.detail_select_agent')}</option>
                  {users.map(u => <option key={u.id} value={u.id}>{u.full_name}</option>)}
                </select>
              </div>
            )}
          </div>

          {/* Descripción */}
          <div style={{ marginBottom: 20 }}>
            <div style={{ fontSize: "var(--text-xs)", fontWeight: 700, color: 'var(--text-3)', marginBottom: 8, textTransform: 'uppercase' }}>{t('common.description')}</div>
            <div style={{ fontSize: "var(--text-base)", color: 'var(--text-1)', lineHeight: 1.6, whiteSpace: 'pre-wrap', background: 'var(--surface-2)', borderRadius: 8, padding: '12px 14px' }}>
              {ticket.description}
            </div>
          </div>

          {ticket.dynamic_fields && Object.keys(ticket.dynamic_fields).length > 0 && (
            <div style={{ marginBottom: 20 }}>
              <div style={{ fontSize: "var(--text-xs)", fontWeight: 700, color: 'var(--text-3)', marginBottom: 8, textTransform: 'uppercase' }}>
                {t('ticketdetail.campos_dinamicos')}
              </div>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
                {Object.entries(ticket.dynamic_fields).map(([k, v]) => (
                  <div key={k} style={{ background: 'var(--surface-2)', borderRadius: 8, padding: '10px 12px' }}>
                    <div style={{ fontSize: "var(--text-2xs)", color: 'var(--text-3)', textTransform: 'uppercase', marginBottom: 2 }}>{k}</div>
                    <div style={{ fontSize: "var(--text-sm)", color: 'var(--text-1)', fontWeight: 500, whiteSpace: 'pre-wrap' }}>{String(v ?? '—')}</div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {ticket.resolution && (
            <div style={{ marginBottom: 20 }}>
              <div style={{ fontSize: "var(--text-xs)", fontWeight: 700, color: COLOR.success, marginBottom: 8, textTransform: 'uppercase' }}>{t('service_desk.edit_resolution')}</div>
              <div style={{ fontSize: "var(--text-base)", color: 'var(--text-1)', background: alpha(COLOR.success, '08'), border: `1px solid ${alpha(COLOR.success, '20')}`, borderRadius: 8, padding: '12px 14px', lineHeight: 1.5 }}>
                {ticket.resolution}
              </div>
            </div>
          )}

          {links.length > 0 && (
            <div style={{ marginBottom: 20 }}>
              <div style={{ fontSize: "var(--text-xs)", fontWeight: 700, color: 'var(--text-3)', marginBottom: 8, textTransform: 'uppercase' }}>
                {t('service_desk.detail_linked')} ({links.length})
              </div>
              {links.map((lk: any) => (
                <div key={lk.link_id} style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '6px 0', borderBottom: '1px solid var(--surface-4)', fontSize: "var(--text-sm)" }}>
                  <span style={{ color: 'var(--text-3)', fontSize: "var(--text-2xs)", textTransform: 'uppercase', minWidth: 70 }}>{lk.link_type}</span>
                  <span style={{ color: 'var(--accent)', fontWeight: 600 }}>{lk.ticket_number}</span>
                  <span style={{ color: 'var(--text-1)', flex: 1 }}>{lk.ticket_title}</span>
                  <SBadge v={lk.ticket_status} />
                </div>
              ))}
            </div>
          )}

          {/* Time logging */}
          <div style={{ marginBottom: 20 }}>
            <div style={{ fontSize: "var(--text-xs)", fontWeight: 700, color: 'var(--text-3)', marginBottom: 8, textTransform: 'uppercase' }}>{t('service_desk.detail_log_time')}</div>
            <div style={{ display: 'flex', gap: 8 }}>
              <input type="number" aria-label={t('service_desk.detail_time_spent')} placeholder={t('service_desk.detail_time_spent')} value={timeMin} onChange={e => setTimeMin(e.target.value)} style={{ ...IS, flex: 1 }} />
              <select value={timeUnit} onChange={e => setTimeUnit(e.target.value)} style={{ ...IS, width: 120 }}>
                <option value="minutes">min</option>
                <option value="hours">h</option>
                <option value="days">d (8h)</option>
              </select>
              <label style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 'var(--text-sm)', color: 'var(--text-2)', whiteSpace: 'nowrap' }}>
                <input type="checkbox" checked={facturable} onChange={e => setFacturable(e.target.checked)} aria-label={t('sd_cfg.time_billable')} />
                {t('sd_cfg.time_billable')}
              </label>
              <Button onClick={() => logTime()} disabled={loggingTime || !timeMin} loading={loggingTime}>{t('service_desk.detail_add_btn')}</Button>
            </div>
          </div>

          {/* Comments */}
          <div style={{ marginBottom: 20 }}>
            <div style={{ fontSize: "var(--text-xs)", fontWeight: 700, color: 'var(--text-3)', marginBottom: 12, textTransform: 'uppercase' }}>
              {t('common.description')} ({(ticket.comments || []).length})
            </div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 10, marginBottom: 14 }}>
              {(ticket.comments || []).map((c: any) => (
                <div key={c.id} style={{ background: 'var(--surface-2)', borderRadius: 10, padding: '12px 14px' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 6 }}>
                    <span style={{ fontSize: "var(--text-sm)", fontWeight: 600, color: 'var(--text-1)' }}>{c.author_name}</span>
                    <span style={{ fontSize: "var(--text-xs)", color: 'var(--text-3)' }}>{fmtDate(c.created_at)}</span>
                  </div>
                  <div style={{ fontSize: "var(--text-base)", color: 'var(--text-1)', lineHeight: 1.5, whiteSpace: 'pre-wrap' }}>{c.body}</div>
                </div>
              ))}
            </div>
            <div style={{ position: 'relative' }}>
              {showCanned && (
                <CannedResponsePicker
                  onSelect={text => setCommentText(prev => prev ? prev + '\n\n' + text : text)}
                  onClose={() => setShowCanned(false)}
                />
              )}
              <textarea placeholder={t('service_desk.detail_send_comment')} value={commentText}
                onChange={e => setCommentText(e.target.value)} rows={3} style={{ ...IS, resize: 'vertical', marginBottom: 6 }} />
            </div>
            <div style={{ display: 'flex', gap: 8, marginBottom: 8 }}>
              <button onClick={() => setShowCanned(s => !s)}
                style={{ fontSize: "var(--text-xs)", padding: '5px 10px', borderRadius: 7, background: showCanned ? 'var(--accent-muted)' : 'var(--surface-3)', border: `1px solid ${showCanned ? 'var(--accent-border-strong)' : 'var(--surface-4)'}`, color: showCanned ? 'var(--accent)' : 'var(--text-2)', cursor: 'pointer', fontFamily: 'inherit' }}>
                {t('ticketdetail.respuestas_rapidas')}
              </button>
              <button onClick={() => suggestReply()} disabled={suggestingReply}
                style={{ fontSize: "var(--text-xs)", padding: '5px 10px', borderRadius: 7, background: 'var(--surface-3)', border: '1px solid var(--surface-4)', color: 'var(--text-2)', cursor: suggestingReply ? 'wait' : 'pointer', fontFamily: 'inherit' }}>
                {suggestingReply ? t('service_desk.detail_ai_generating') : `✨ ${t('sd_cfg.ai_suggest')}`}
              </button>
            </div>
            {sugerencia && <ApoyoDeLaSugerencia s={sugerencia} />}
            <Button onClick={() => addComment()} disabled={commenting || !commentText} loading={commenting} style={{ width: '100%' }}>
              {t('service_desk.detail_send_comment')}
            </Button>
          </div>

          <SeguirYFusionar ticketId={ticketId} />
          <div style={{ marginBottom: 20 }}><DocumentsPanel ticketId={ticketId} /></div>

          {(ticket.history || []).length > 0 && (
            <div>
              <div style={{ fontSize: "var(--text-xs)", fontWeight: 700, color: 'var(--text-3)', marginBottom: 10, textTransform: 'uppercase' }}>{t('service_desk.detail_history')}</div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                {ticket.history.slice(-8).reverse().map((h: any, i: number) => (
                  <div key={i} style={{ fontSize: "var(--text-xs)", color: 'var(--text-2)', padding: '5px 0', borderBottom: '1px solid var(--surface-4)', display: 'flex', justifyContent: 'space-between' }}>
                    <span>{h.change_description || `${h.field_name}: ${h.old_value} → ${h.new_value}`}</span>
                    <span style={{ color: 'var(--text-3)', whiteSpace: 'nowrap', marginLeft: 10 }}>{fmtDate(h.changed_at)}</span>
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
          <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
            <label htmlFor="sd-resolucion" style={LABEL_STYLE}>{t('sd_cfg.qa_resolution')}</label>
            <textarea id="sd-resolucion" aria-label={t('sd_cfg.qa_resolution')} value={textoResolucion} onChange={e => setTextoResolucion(e.target.value)}
              rows={5} style={{ ...(INPUT_STYLE as CSSProperties), resize: 'vertical' }} autoFocus />
            <div style={{ fontSize: 'var(--text-xs)', color: 'var(--text-3)' }}>{t('sd_cfg.qa_resolution_hint')}</div>
            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 10 }}>
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


type Aprobacion = { status: string; comment?: string | null; approver_user_id?: string | null; approver_name?: string | null; decided_by_name?: string | null }

/** Estado de la aprobación y, para quien la tiene que dar, los botones. */
function AprobacionDelTicket({ ticket, yo, rechazando, motivo, setRechazando, setMotivo }: {
  ticket: { id: string; approval: Aprobacion }; yo: { id?: string; role?: string } | null
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
  const puedeDecidir = a.status === 'pending' && (a.approver_user_id === yo?.id || yo?.role === 'admin')
  const color = a.status === 'approved' ? COLOR.success : a.status === 'rejected' ? COLOR.danger : COLOR.warning
  const texto = a.status === 'pending' ? t('sd_cfg.apr_pending', { name: a.approver_name ?? '—' })
    : t(a.status === 'approved' ? 'sd_cfg.apr_approved' : 'sd_cfg.apr_rejected', { name: a.decided_by_name ?? '—' })
  return (
    <div role="status" style={{ border: `1px solid ${alpha(color, '60')}`, background: alpha(color, '12'), borderRadius: 10,
      padding: '12px 16px', marginBottom: 16, display: 'flex', flexDirection: 'column', gap: 10 }}>
      <div style={{ fontSize: 'var(--text-sm)', fontWeight: 600, color }}>{texto}</div>
      {a.comment && <div style={{ fontSize: 'var(--text-sm)', color: 'var(--text-2)' }}>{a.comment}</div>}
      {puedeDecidir && !rechazando && (
        <div style={{ display: 'flex', gap: 8 }}>
          <Button onClick={() => decidir.mutate({ decision: 'approved' })} loading={decidir.isPending}>{t('sd_cfg.apr_approve')}</Button>
          <Button variant="secondary" onClick={() => setRechazando(true)}>{t('sd_cfg.apr_reject')}</Button>
        </div>
      )}
      {puedeDecidir && rechazando && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
          <label htmlFor="apr-motivo" style={LABEL_STYLE}>{t('sd_cfg.apr_reason')}</label>
          <textarea id="apr-motivo" aria-label={t('sd_cfg.apr_reason')} value={motivo} onChange={e => setMotivo(e.target.value)} rows={3}
            style={{ ...(INPUT_STYLE as CSSProperties), resize: 'vertical' }} autoFocus />
          <div style={{ display: 'flex', gap: 8 }}>
            <Button variant="secondary" onClick={() => setRechazando(false)}>{t('common.cancel')}</Button>
            <Button disabled={!motivo.trim()} loading={decidir.isPending}
              onClick={() => decidir.mutate({ decision: 'rejected', comment: motivo.trim() })}>{t('sd_cfg.apr_reject')}</Button>
          </div>
        </div>
      )}
    </div>
  )
}


type Sugerencia = {
  draft?: string | null; ai_error?: string | null
  kb_matches?: { id: string; number: string; title: string; summary?: string | null }[]
  documents?: { document_id: string; title: string; snippet: string }[]
  documents_configured?: boolean; documents_error?: string | null
}

/** Lo que acompaña al borrador: artículos y documentos en que apoyarse. */
function ApoyoDeLaSugerencia({ s }: { s: Sugerencia }) {
  const t = useAppT()
  const titulo: CSSProperties = { fontSize: 'var(--text-2xs)', fontWeight: 700, color: 'var(--text-3)', textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 4 }
  return (
    <div className="ds-card" style={{ padding: 12, marginBottom: 10, display: 'flex', flexDirection: 'column', gap: 10, fontSize: 'var(--text-sm)' }}>
      {s.ai_error && <div role="status" style={{ color: COLOR.warning }}>{s.ai_error}</div>}
      {(s.kb_matches ?? []).length > 0 && (
        <div>
          <div style={titulo}>{t('sd_cfg.ai_related')}</div>
          {(s.kb_matches ?? []).map(k => <div key={k.id}><strong>{k.number}</strong> {k.title}</div>)}
        </div>
      )}
      {s.documents_configured && (
        <div>
          <div style={titulo}>{t('sd_cfg.ai_documents')}</div>
          {s.documents_error ? <div style={{ color: COLOR.warning }}>{s.documents_error}</div>
            : (s.documents ?? []).length === 0 ? <div style={{ color: 'var(--text-3)' }}>{t('sd_cfg.ai_no_documents')}</div>
            : (s.documents ?? []).map(d => (
              <div key={d.document_id} style={{ marginBottom: 4 }}>
                <strong>{d.title}</strong>
                <div style={{ color: 'var(--text-2)' }}>{d.snippet}</div>
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
    queryFn: () => ticketsApi.watchers(ticketId).then(r => r.data as { user_id: string; user_name?: string }[]),
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
      const lista = await ticketsApi.list({ search: buscado, page_size: 5 }).then(r => r.data as { id: string; number: string }[])
      const duplicado = lista.find(x => x.number === buscado && x.id !== ticketId)
      if (!duplicado) throw new Error(t('sd_cfg.m_not_found'))
      await ticketsApi.mergeInto(ticketId, { merged_ticket_id: duplicado.id, reason: motivo || null })
      return buscado
    },
    onSuccess: (n: string) => { setNumero(''); setMotivo(''); qc.invalidateQueries({ queryKey: ['sd-ticket', ticketId] }); toast.success(t('sd_cfg.m_done', { n })) },
    onError: (e: unknown) => toast.error(e instanceof Error && e.message ? e.message : extractErr(e, GENERIC_ERROR_FALLBACK)),
  })
  return (
    <div className="ds-card" style={{ padding: 12, marginBottom: 16, display: 'flex', flexDirection: 'column', gap: 10, fontSize: 'var(--text-sm)' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
        <span style={{ flex: 1, color: 'var(--text-2)' }}>
          <strong>{t('sd_cfg.w_followers')}:</strong> {seguidores.length ? seguidores.map(s => s.user_name).join(', ') : t('sd_cfg.w_nobody')}
        </span>
        <Button variant="secondary" onClick={() => alternar.mutate()} loading={alternar.isPending}>{sigo ? t('sd_cfg.w_unfollow') : t('sd_cfg.w_follow')}</Button>
      </div>
      <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center' }}>
        <span style={{ fontWeight: 600 }}>{t('sd_cfg.m_title')}</span>
        <input aria-label={t('sd_cfg.m_number')} placeholder={t('sd_cfg.m_number')} value={numero} onChange={e => setNumero(e.target.value)}
          style={{ ...(INPUT_STYLE as CSSProperties), flex: '1 1 160px' }} />
        <input aria-label={t('sd_cfg.m_reason')} placeholder={t('sd_cfg.m_reason')} value={motivo} onChange={e => setMotivo(e.target.value)}
          style={{ ...(INPUT_STYLE as CSSProperties), flex: '2 1 200px' }} />
        <Button variant="secondary" disabled={!numero.trim()} loading={fusionar.isPending} onClick={() => fusionar.mutate()}>{t('sd_cfg.m_do')}</Button>
      </div>
    </div>
  )
}
