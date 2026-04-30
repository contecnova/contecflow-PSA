import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useAppT } from '../../i18n/AppLangContext'
import { useToast } from '../../context/ToastContext'
import { extractErr } from '../../utils/helpers'
import { Button, Spinner, Modal } from '../../components/ui'
import AIInlineEditor from '../../components/AIInlineEditor'
import DocumentsPanel from '../../components/DocumentsPanel'
import { COLOR } from '../../constants/theme'
import { sdCannedApi, ticketsApi, usersApi } from '../../services/api'
import { PBadge, SBadge, fmtDate, fmtMinutes, INPUT_STYLE, LABEL_STYLE } from './sdUtils'

// ── CannedResponsePicker ──────────────────────────────────────────────────────
function CannedResponsePicker({ onSelect, onClose }) {
  const t = useAppT()
  const [search, setSearch] = useState('')
  const { data: responses = [] } = useQuery({
    queryKey: ['canned-responses', search],
    queryFn: () => sdCannedApi.list(search ? { search } : {}).then(r => r.data).catch(() => []),
    staleTime: 60000,
  })
  const cats = [...new Set(responses.map(r => r.category || 'General'))].sort()
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
                <button key={r.id} onClick={() => { onSelect(r.body); onClose() }}
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
function SplitTicketModal({ ticket, onClose, onCreated }) {
  const t = useAppT()
  const toast = useToast()
  const [form, setForm] = useState({
    new_title: '', new_description: ticket?.description || '',
    keep_original_description: ticket?.description || '', tags: '',
  })
  const { mutate, isPending } = useMutation({
    mutationFn: data => ticketsApi.split(ticket.id, data),
    onSuccess: res => {
      toast.success(`${t('service_desk.ticket_created_success')} ${res?.data?.child?.number || ''}`)
      onCreated?.(res?.data)
      onClose()
    },
    onError: e => toast.error(extractErr(e, t('common.error'))),
  })
  const IS = INPUT_STYLE
  const LS = LABEL_STYLE
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
function TicketEditModal({ ticket, onClose, onSaved }) {
  const t = useAppT()
  const toast = useToast()
  const [form, setForm] = useState({
    title: ticket.title || '', description: ticket.description || '',
    priority: ticket.priority || 'p3_medium', ticket_type: ticket.ticket_type || 'incident',
    urgency: ticket.urgency || 'medium', impact: ticket.impact || 'user',
    status: ticket.status || 'new', resolution: ticket.resolution || '', tags: ticket.tags || '',
  })
  const { mutate, isPending } = useMutation({
    mutationFn: data => ticketsApi.update(ticket.id, data),
    onSuccess: onSaved,
    onError: e => toast.error(extractErr(e, 'Error al guardar')),
  })
  const set = k => e => setForm(f => ({ ...f, [k]: e.target.value }))
  const IS = INPUT_STYLE
  const LS = LABEL_STYLE
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
          <AIInlineEditor value={form.description} onChange={val => set('description')({ target: { value: val } })} rows={5} style={{ ...IS, resize: 'vertical' }} />
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
          <Button onClick={() => mutate(form)} disabled={isPending || !form.title.trim() || !form.description.trim()} loading={isPending}>
            {t('common.save')}
          </Button>
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

export default function TicketDetail({ ticketId, onClose, embedded = false }) {
  const t = useAppT()
  const qc = useQueryClient()
  const toast = useToast()
  const [commentText, setCommentText] = useState('')
  const [showCanned, setShowCanned] = useState(false)
  const [timeMin, setTimeMin] = useState('')
  const [editAssign, setEditAssign] = useState(false)
  const [showEdit, setShowEdit] = useState(false)
  const [showSplit, setShowSplit] = useState(false)

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

  const { mutate: addComment, isPending: commenting } = useMutation({
    mutationFn: () => ticketsApi.comment(ticketId, { body: commentText, is_internal: false }),
    onSuccess: () => { invalidate(); setCommentText(''); toast.success(t('service_desk.comment_added')) },
    onError: e => toast.error(extractErr(e, 'Error')),
  })
  const { mutate: suggestReply, isPending: suggestingReply } = useMutation({
    mutationFn: () => ticketsApi.aiSuggest(ticketId, { content: commentText }),
    onSuccess: res => {
      const draft = res?.data?.draft || ''
      if (!draft) { toast.error(t('common.error')); return }
      setCommentText(prev => prev ? `${prev}\n\n${draft}` : draft)
      toast.success(t('service_desk.detail_ai_generating'))
    },
    onError: e => toast.error(extractErr(e, 'Error al sugerir respuesta IA')),
  })
  const { mutate: logTime, isPending: loggingTime } = useMutation({
    mutationFn: () => ticketsApi.timelog(ticketId, { minutes: Number(timeMin) }),
    onSuccess: () => { invalidate(); setTimeMin(''); toast.success(`${timeMin} min`) },
    onError: e => toast.error(extractErr(e, 'Error')),
  })
  const { mutate: updateTicket } = useMutation({
    mutationFn: data => ticketsApi.update(ticketId, data),
    onSuccess: () => { invalidate(); toast.success(t('service_desk.ticket_updated')) },
    onError: e => toast.error(extractErr(e, 'Error')),
  })
  const { mutate: escalate } = useMutation({
    mutationFn: () => ticketsApi.escalate(ticketId),
    onSuccess: () => { invalidate(); toast.success(t('service_desk.ticket_escalated')) },
    onError: e => toast.error(extractErr(e, 'Error')),
  })
  const { mutate: pauseSLA } = useMutation({
    mutationFn: () => ticketsApi.slaPause(ticketId, { note: 'Esperando respuesta del cliente' }),
    onSuccess: () => { invalidate(); qc.invalidateQueries({ queryKey: ['sd-sla-events'] }); toast.success(t('service_desk.sla_paused')) },
    onError: e => toast.error(extractErr(e, 'Error')),
  })
  const { mutate: resumeSLA } = useMutation({
    mutationFn: () => ticketsApi.slaResume(ticketId),
    onSuccess: () => { invalidate(); qc.invalidateQueries({ queryKey: ['sd-sla-events'] }); toast.success(t('service_desk.sla_resumed')) },
    onError: e => toast.error(extractErr(e, 'Error')),
  })

  if (!ticketId) return null

  const IS = INPUT_STYLE
  const slaColor = ticket?.sla_resolution_status === 'breached' ? COLOR.danger
    : ticket?.sla_resolution_status === 'at_risk' ? COLOR.warning : COLOR.success

  return (
    <div style={embedded ? {
      height: 'calc(100vh - 210px)', minHeight: 520, background: 'var(--surface-0)',
      border: '1px solid var(--surface-4)', borderRadius: 12, display: 'flex', flexDirection: 'column', overflow: 'hidden',
    } : {
      position: 'fixed', top: 0, right: 0, bottom: 0, width: 560,
      background: 'var(--surface-0)', borderLeft: '1px solid var(--surface-4)',
      zIndex: 200, display: 'flex', flexDirection: 'column', overflowY: 'auto',
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
              <button onClick={() => updateTicket({ status: 'in_progress' })} style={{ ...qaBtnStyle, background: `${COLOR.accent}20`, color: COLOR.accent }}>▶ {t('service_desk.ticket_status')}</button>
              <button onClick={() => updateTicket({ status: 'resolved', resolution: 'Resuelto' })} style={{ ...qaBtnStyle, background: `${COLOR.success}20`, color: COLOR.success }}>✓ {t('service_desk.ticket_status')}</button>
              <button onClick={() => escalate()} style={{ ...qaBtnStyle, background: `${COLOR.warning}20`, color: COLOR.warning }}>↑ {t('service_desk.ticket_escalated')}</button>
              {ticket.sla_paused_at
                ? <button onClick={() => resumeSLA()} style={qaBtnStyle}>▶ {t('service_desk.sla_resumed')}</button>
                : <button onClick={() => pauseSLA()} style={qaBtnStyle}>⏸ {t('service_desk.sla_paused')}</button>}
              <button onClick={() => setShowSplit(true)} style={qaBtnStyle}>✂ {t('service_desk.split_title_lbl')}</button>
            </>}
            {ticket.status === 'resolved' && (
              <button onClick={() => updateTicket({ status: 'closed' })} style={{ ...qaBtnStyle, background: `${COLOR.text2}20`, color: 'var(--text-2)' }}>✕ Cerrar</button>
            )}
          </div>
        )}
      </div>

      {/* Body */}
      <div style={{ flex: 1, padding: '20px', overflowY: 'auto' }}>
        {isLoading ? <div style={{ padding: 40, textAlign: 'center' }}><Spinner /></div> : ticket && <>
          {/* SLA status */}
          <div style={{ background: 'var(--surface-2)', border: `1px solid ${slaColor}40`, borderRadius: 10, padding: '12px 16px', marginBottom: 16, display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
            <div>
              <div style={{ fontSize: "var(--text-2xs)", color: 'var(--text-3)', textTransform: 'uppercase', marginBottom: 2 }}>{t('service_desk.detail_sla_response')}</div>
              <div style={{ fontSize: "var(--text-sm)", fontWeight: 600, color: ticket.sla_response_status === 'breached' ? COLOR.danger : COLOR.success }}>
                {ticket.sla_response_status?.replace(/_/g, ' ')} · {fmtDate(ticket.sla_response_due)}
              </div>
            </div>
            <div>
              <div style={{ fontSize: "var(--text-2xs)", color: 'var(--text-3)', textTransform: 'uppercase', marginBottom: 2 }}>{t('service_desk.detail_sla_resolution')}</div>
              <div style={{ fontSize: "var(--text-sm)", fontWeight: 600, color: slaColor }}>
                {ticket.sla_resolution_status?.replace(/_/g, ' ')} · {fmtDate(ticket.sla_resolution_due)}
              </div>
            </div>
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

          {ticket.resolution && (
            <div style={{ marginBottom: 20 }}>
              <div style={{ fontSize: "var(--text-xs)", fontWeight: 700, color: COLOR.success, marginBottom: 8, textTransform: 'uppercase' }}>{t('service_desk.edit_resolution')}</div>
              <div style={{ fontSize: "var(--text-base)", color: 'var(--text-1)', background: `${COLOR.success}08`, border: `1px solid ${COLOR.success}20`, borderRadius: 8, padding: '12px 14px', lineHeight: 1.5 }}>
                {ticket.resolution}
              </div>
            </div>
          )}

          {links.length > 0 && (
            <div style={{ marginBottom: 20 }}>
              <div style={{ fontSize: "var(--text-xs)", fontWeight: 700, color: 'var(--text-3)', marginBottom: 8, textTransform: 'uppercase' }}>
                {t('service_desk.detail_linked')} ({links.length})
              </div>
              {links.map(lk => (
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
              <Button onClick={() => logTime()} disabled={loggingTime || !timeMin} loading={loggingTime}>{t('service_desk.detail_add_btn')}</Button>
            </div>
          </div>

          {/* Comments */}
          <div style={{ marginBottom: 20 }}>
            <div style={{ fontSize: "var(--text-xs)", fontWeight: 700, color: 'var(--text-3)', marginBottom: 12, textTransform: 'uppercase' }}>
              {t('common.description')} ({(ticket.comments || []).length})
            </div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 10, marginBottom: 14 }}>
              {(ticket.comments || []).map(c => (
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
                ⚡ Respuestas rápidas
              </button>
              <button onClick={() => suggestReply()} disabled={suggestingReply}
                style={{ fontSize: "var(--text-xs)", padding: '5px 10px', borderRadius: 7, background: 'var(--surface-3)', border: '1px solid var(--surface-4)', color: 'var(--text-2)', cursor: suggestingReply ? 'wait' : 'pointer', fontFamily: 'inherit' }}>
                {suggestingReply ? t('service_desk.detail_ai_generating') : `✨ ${t('service_desk.detail_send_comment')}`}
              </button>
            </div>
            <Button onClick={() => addComment()} disabled={commenting || !commentText} loading={commenting} style={{ width: '100%' }}>
              {t('service_desk.detail_send_comment')}
            </Button>
          </div>

          <div style={{ marginBottom: 20 }}><DocumentsPanel ticketId={ticketId} /></div>

          {(ticket.history || []).length > 0 && (
            <div>
              <div style={{ fontSize: "var(--text-xs)", fontWeight: 700, color: 'var(--text-3)', marginBottom: 10, textTransform: 'uppercase' }}>{t('service_desk.detail_history')}</div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                {ticket.history.slice(-8).reverse().map((h, i) => (
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
