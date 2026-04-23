/**
 * ServiceDeskPage — ITIL/ITSM completo
 * Módulos: Queue · Tickets · Problems/KEDB · Changes · Major Incidents ·
 *          KB · CMDB · Metrics · Routing · Templates · Config
 */
import { useState, useMemo, useEffect, lazy, Suspense, useId } from 'react'
import { openConfirmGlobal } from '../context/ConfirmContext'
import { extractErr } from '../utils/helpers'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useToast } from '../context/ToastContext'
import api from '../services/api'
import PageHeader from '../components/layout/PageHeader'
import { MessageSquare } from 'lucide-react'
import { Button, Spinner, EmptyState, Modal, useSort, SortableTH } from '../components/ui'
import { COLOR } from '../constants/theme'
import DocumentsPanel from '../components/DocumentsPanel'
import AIInlineEditor from '../components/AIInlineEditor'
import { useAppT } from '../i18n/AppLangContext'
import { z } from 'zod'
import { useFormValidation } from '../hooks/useFormValidation'

// ── Helpers ─────────────────────────────────────────────────────────────────
const PRIORITY_COLOR = {
  p1_critical: COLOR.danger,
  p2_high:     '#fb923c',
  p3_medium:   COLOR.warning,
  p4_low:      COLOR.text2,
}
const PRIORITY_LABEL = {
  p1_critical: 'P1 Crítico', p2_high: 'P2 Alto',
  p3_medium: 'P3 Medio', p4_low: 'P4 Bajo',
}
const STATUS_COLOR = {
  new: COLOR.accent, assigned: COLOR.accent, in_progress: '#38bdf8',
  pending_client: COLOR.warning, pending_third: COLOR.warning,
  resolved: COLOR.success, closed: COLOR.text2, cancelled: COLOR.text3,
}

function _getCreateTicketSchema(t) {
  return z.object({
  ticket_type: z.enum(['incident', 'service_request', 'change', 'problem', 'question']),
  title: z.string().trim().min(1, t('service_desk.zod_title_required')),
  description: z.string().trim().min(1, t('service_desk.zod_description_required')),
  priority: z.enum(['p1_critical', 'p2_high', 'p3_medium', 'p4_low']),
  urgency: z.enum(['critical', 'high', 'medium', 'low']),
  impact: z.enum(['enterprise', 'department', 'user', 'minimal']),
  assigned_to_user_id: z.string().optional(),
  client_id: z.string().optional(),
  service_item_id: z.string().optional(),
  })
}

const LazyMetricsDashboard = lazy(() => import('./service-desk/MetricsDashboardTab'))
const LazyChangeManagementTab = lazy(() => import('./service-desk/ChangeManagementTab'))
const LazyITSMKnowledgeTab = lazy(() => import('./service-desk/ITSMKnowledgeTab'))
const LazyCMDBTab = lazy(() => import('./service-desk/CMDBTab'))

function PBadge({ v }) {
  const color = PRIORITY_COLOR[v] || COLOR.text2
  return (
    <span style={{ fontSize: 10, fontWeight: 700, color, padding: '2px 7px',
      borderRadius: 4, border: `1px solid ${color}30`, background: `${color}12`,
      whiteSpace: 'nowrap' }}>
      {PRIORITY_LABEL[v] || v}
    </span>
  )
}

function SBadge({ v }) {
  const color = STATUS_COLOR[v] || COLOR.text2
  const label = v?.replace(/_/g, ' ')
  return (
    <span style={{ fontSize: 10, fontWeight: 600, color, padding: '2px 8px',
      borderRadius: 4, background: `${color}15`, whiteSpace: 'nowrap' }}>
      {label}
    </span>
  )
}

function fmtDate(d) {
  if (!d) return '—'
  return new Date(d).toLocaleDateString('es-ES', { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' })
}

function fmtMinutes(m) {
  if (!m) return '—'
  if (m < 60) return `${m}m`
  const h = Math.floor(m / 60), min = Math.round(m % 60)
  return min > 0 ? `${h}h ${min}m` : `${h}h`
}

// ── Ticket Row ────────────────────────────────────────────────────────────────
function TRow({ t: ticket, onClick }) {
  const tr = useAppT()
  const now = new Date()
  const due = ticket.sla_resolution_due ? new Date(ticket.sla_resolution_due) : null
  const overdue = due && due < now && !['resolved','closed'].includes(ticket.status)
  return (
    <tr onClick={onClick} tabIndex={0} onKeyDown={e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onClick() } }} aria-label={`${ticket.number} ${ticket.title}`}
      style={{ cursor: 'pointer', borderBottom: '1px solid var(--surface-4)' }}
      onMouseEnter={e => e.currentTarget.style.background = 'var(--accent-muted)'}
      onMouseLeave={e => e.currentTarget.style.background = 'transparent'}>
      <td style={{ padding: '10px 14px', fontSize: 12, color: 'var(--accent)', fontWeight: 600, whiteSpace: 'nowrap' }}>{ticket.number}</td>
      <td style={{ padding: '10px 8px', maxWidth: 320 }}>
        <div style={{ fontSize: 13, color: 'var(--text-1)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{ticket.title}</div>
        {ticket.requester_name && <div style={{ fontSize: 11, color: 'var(--text-3)' }}>{ticket.requester_name}</div>}
      </td>
      <td style={{ padding: '10px 8px' }}><PBadge v={ticket.priority} /></td>
      <td style={{ padding: '10px 8px' }}><SBadge v={ticket.status} /></td>
      <td style={{ padding: '10px 8px', fontSize: 11, color: 'var(--text-2)', whiteSpace: 'nowrap' }}>{ticket.ticket_type?.replace(/_/g, ' ')}</td>
      <td style={{ padding: '10px 8px', fontSize: 11, color: overdue ? COLOR.danger : 'var(--text-2)', whiteSpace: 'nowrap' }}>
        {due ? `${overdue ? '⚠ ' : ''}${fmtDate(due)}` : '—'}
      </td>
      <td style={{ padding: '10px 14px', fontSize: 11, color: 'var(--text-2)' }}>
        {ticket.assigned_to?.full_name || <span style={{ color: 'var(--text-4)' }}>{tr('service_desk.unassigned')}</span>}
      </td>
    </tr>
  )
}

// ── Queue / All Tickets ───────────────────────────────────────────────────────
function TicketList({ queueOnly, onSelect }) {
  const t = useAppT()
  const [search, setSearch] = useState('')
  const [filterPrio, setFilterPrio] = useState('')
  const [filterStatus, setFilterStatus] = useState('')
  const [filterType, setFilterType] = useState('')

  const { data: tickets = [], isLoading } = useQuery({
    queryKey: ['sd-tickets', queueOnly, filterPrio, filterStatus, filterType],
    queryFn: () => {
      if (queueOnly) {
        return api.get('/sd/tickets/my-queue').then(r => r.data)
      }
      return api.get('/sd/tickets', {
        params: {
          priority: filterPrio || undefined,
          status: filterStatus || undefined,
          ticket_type: filterType || undefined,
          page_size: 100,
        }
      }).then(r => {
        const d = r.data
        return Array.isArray(d) ? d : (d?.tickets || d?.items || [])
      })
    },
    staleTime: 15000,
    refetchInterval: 60000,
  })

  const filtered = useMemo(() => {
    const list = Array.isArray(tickets) ? tickets : []
    if (!search) return list
    const q = search.toLowerCase()
    return list.filter(tk =>
      tk.title?.toLowerCase().includes(q) ||
      tk.number?.toLowerCase().includes(q) ||
      tk.requester_name?.toLowerCase().includes(q)
    )
  }, [tickets, search])

  const { sort: ticketSort, setSort: setTicketSort, sortedData: sortedTickets } = useSort(filtered, 'number')

  const IS = { background: 'var(--surface-3)', border: '1px solid var(--surface-4)',
    borderRadius: 8, padding: '7px 12px', color: 'var(--text-1)', fontSize: 12,
    outline: 'none', fontFamily: 'inherit' }

  return (
    <div>
      <div style={{ display: 'flex', gap: 10, marginBottom: 16, flexWrap: 'wrap' }}>
        <input placeholder={t('service_desk.search_tickets')} value={search}
          aria-label={t('service_desk.search_tickets')} onChange={e => setSearch(e.target.value)} style={{ ...IS, flex: 1, minWidth: 200 }} />
        <select aria-label={t('service_desk.filter_all_priorities')} value={filterPrio} onChange={e => setFilterPrio(e.target.value)} style={IS}>
          <option value="">{t('service_desk.filter_all_priorities')}</option>
          {['p1_critical','p2_high','p3_medium','p4_low'].map(p =>
            <option key={p} value={p}>{PRIORITY_LABEL[p]}</option>)}
        </select>
        <select aria-label={t('service_desk.filter_all_statuses')} value={filterStatus} onChange={e => setFilterStatus(e.target.value)} style={IS}>
          <option value="">{t('service_desk.filter_all_statuses')}</option>
          {['new','assigned','in_progress','pending_client','resolved','closed'].map(s =>
            <option key={s} value={s}>{s.replace(/_/g,' ')}</option>)}
        </select>
        <select aria-label={t('service_desk.filter_all_types')} value={filterType} onChange={e => setFilterType(e.target.value)} style={IS}>
          <option value="">{t('service_desk.filter_all_types')}</option>
          {['incident','service_request','change','problem','question'].map(tk =>
            <option key={tk} value={tk}>{tk.replace(/_/g,' ')}</option>)}
        </select>
      </div>

      {isLoading ? <div style={{ textAlign:'center', padding: 40 }}><Spinner /></div> :
       filtered.length === 0 ? <EmptyState icon="🎫" title={t('service_desk.no_tickets')} description={t('service_desk.no_matching')} /> :
      <div style={{ overflowX: 'auto' }}>
        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
          <thead>
            <tr style={{ borderBottom: '2px solid var(--surface-4)' }}>
              <th style={{ padding: '10px 8px', whiteSpace: 'nowrap' }}><SortableTH col="number" sort={ticketSort} onSort={setTicketSort}>{t('service_desk.col_number')}</SortableTH></th>
              <th style={{ padding: '10px 8px', whiteSpace: 'nowrap' }}><SortableTH col="title" sort={ticketSort} onSort={setTicketSort}>{t('service_desk.ticket_title')}</SortableTH></th>
              <th style={{ padding: '10px 8px', whiteSpace: 'nowrap' }}><SortableTH col="priority" sort={ticketSort} onSort={setTicketSort}>{t('service_desk.ticket_priority')}</SortableTH></th>
              <th style={{ padding: '10px 8px', whiteSpace: 'nowrap' }}><SortableTH col="status" sort={ticketSort} onSort={setTicketSort}>{t('service_desk.ticket_status')}</SortableTH></th>
              <th style={{ padding: '10px 8px', whiteSpace: 'nowrap' }}><SortableTH col="ticket_type" sort={ticketSort} onSort={setTicketSort}>{t('service_desk.ticket_type')}</SortableTH></th>
              <th style={{ padding: '10px 8px', whiteSpace: 'nowrap' }}><SortableTH col="sla_due" sort={ticketSort} onSort={setTicketSort}>{t('service_desk.col_sla_deadline')}</SortableTH></th>
              <th style={{ padding: '10px 8px', whiteSpace: 'nowrap' }}><SortableTH col="assignee_name" sort={ticketSort} onSort={setTicketSort}>{t('service_desk.assigned_to')}</SortableTH></th>
            </tr>
          </thead>
          <tbody>
            {sortedTickets.map(tk => <TRow key={tk.id} t={tk} onClick={() => onSelect(tk)} />)}
          </tbody>
        </table>
        <div style={{ fontSize: 11, color: 'var(--text-3)', padding: '10px 4px' }}>
          {filtered.length} ticket{filtered.length !== 1 ? 's' : ''}
        </div>
      </div>}
    </div>
  )
}

// ── Major Incidents ───────────────────────────────────────────────────────────
function MajorIncidents() {
  const t = useAppT()
  const qc = useQueryClient()
  const toast = useToast()
  const [showDeclare, setShowDeclare] = useState(false)

  const { data: mis = [], isLoading } = useQuery({
    queryKey: ['sd-major-incidents'],
    queryFn: () => api.get('/sd/major-incidents').then(r => r.data),
    refetchInterval: 30000,
  })

  const activeMis = mis.filter(m => m.status === 'active')
  const { sort: miSort, setSort: setMiSort, sortedData: sortedMis } = useSort(mis, 'declared_at', 'desc')

  return (
    <div>
      {activeMis.length > 0 && (
        <div style={{ background: `${COLOR.danger}15`, border: `1px solid ${COLOR.danger}40`,
          borderRadius: 12, padding: '16px 20px', marginBottom: 20 }}>
          <div style={{ fontSize: 13, fontWeight: 700, color: COLOR.danger, marginBottom: 10 }}>
            🚨 {activeMis.length} {t('service_desk.mi_declared_at').toLowerCase()} {activeMis.length > 1 ? 's' : ''}
          </div>
          {activeMis.map(m => (
            <div key={m.id} style={{ display: 'flex', justifyContent: 'space-between',
              alignItems: 'center', padding: '8px 0', borderTop: `1px solid ${COLOR.danger}20` }}>
              <div>
                <span style={{ fontWeight: 600, fontSize: 12, color: COLOR.danger, marginRight: 10 }}>{m.number}</span>
                <span style={{ fontSize: 13, color: 'var(--text-1)' }}>{m.title}</span>
              </div>
              <div style={{ fontSize: 11, color: 'var(--text-2)' }}>{t('service_desk.mi_declared_at')} {fmtDate(m.declared_at)}</div>
            </div>
          ))}
        </div>
      )}

      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 20 }}>
        <div style={{ fontSize: 13, color: 'var(--text-2)' }}>{mis.length} incidentes mayores registrados</div>
        <Button onClick={() => setShowDeclare(true)} style={{ background: `${COLOR.danger}20`, color: COLOR.danger,
          border: `1px solid ${COLOR.danger}40` }}>
          🚨 {t('service_desk.mi_declare_btn')}
        </Button>
      </div>

      {isLoading ? <Spinner /> : (
        <table style={{ width: '100%', borderCollapse: 'collapse' }}>
          <thead>
            <tr style={{ borderBottom: '2px solid var(--surface-4)' }}>
              <th style={{ padding: '10px 8px', whiteSpace: 'nowrap' }}><SortableTH col="number" sort={miSort} onSort={setMiSort}>{t('service_desk.col_number')}</SortableTH></th>
              <th style={{ padding: '10px 8px', whiteSpace: 'nowrap' }}><SortableTH col="title" sort={miSort} onSort={setMiSort}>{t('service_desk.ticket_title')}</SortableTH></th>
              <th style={{ padding: '10px 8px', whiteSpace: 'nowrap' }}><SortableTH col="severity" sort={miSort} onSort={setMiSort}>{t('service_desk.mi_severity')}</SortableTH></th>
              <th style={{ padding: '10px 8px', whiteSpace: 'nowrap' }}><SortableTH col="status" sort={miSort} onSort={setMiSort}>{t('service_desk.ticket_status')}</SortableTH></th>
              <th style={{ padding: '10px 8px', whiteSpace: 'nowrap' }}><SortableTH col="commander" sort={miSort} onSort={setMiSort}>{t('service_desk.mi_commander')}</SortableTH></th>
              <th style={{ padding: '10px 8px', whiteSpace: 'nowrap' }}><SortableTH col="declared_at" sort={miSort} onSort={setMiSort}>{t('service_desk.mi_declared_at')}</SortableTH></th>
              <th style={{ padding: '10px 8px', whiteSpace: 'nowrap' }}><SortableTH col="resolved_at" sort={miSort} onSort={setMiSort}>{t('service_desk.mi_resolved_at')}</SortableTH></th>
            </tr>
          </thead>
          <tbody>
            {sortedMis.map(m => (
              <tr key={m.id} style={{ borderBottom: '1px solid var(--surface-4)' }}>
                <td style={{ padding: '10px 8px', fontSize: 12, color: COLOR.danger, fontWeight: 700 }}>{m.number}</td>
                <td style={{ padding: '10px 8px', fontSize: 13, color: 'var(--text-1)' }}>{m.title}</td>
                <td style={{ padding: '10px 8px' }}>
                  <span style={{ fontSize: 12, fontWeight: 700,
                    color: m.severity === 'P1' ? COLOR.danger : '#fb923c' }}>{m.severity}</span>
                </td>
                <td style={{ padding: '10px 8px' }}>
                  <span style={{ fontSize: 11, fontWeight: 600,
                    color: m.status === 'active' ? COLOR.danger : COLOR.success,
                    background: m.status === 'active' ? `${COLOR.danger}15` : `${COLOR.success}15`,
                    padding: '2px 8px', borderRadius: 4 }}>{m.status}</span>
                </td>
                <td style={{ padding: '10px 8px', fontSize: 12, color: 'var(--text-2)' }}>{m.commander || '—'}</td>
                <td style={{ padding: '10px 8px', fontSize: 11, color: 'var(--text-2)' }}>{fmtDate(m.declared_at)}</td>
                <td style={{ padding: '10px 8px', fontSize: 11, color: 'var(--text-2)' }}>{m.resolved_at ? fmtDate(m.resolved_at) : '—'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      {showDeclare && (
        <DeclareMIModal onClose={() => setShowDeclare(false)} onSaved={() => {
          qc.invalidateQueries({ queryKey: ['sd-major-incidents'] })
          setShowDeclare(false)
          toast.success(t('service_desk.mi_declared_success'))
        }} />
      )}
    </div>
  )
}

function DeclareMIModal({ onClose, onSaved }) {
  const t = useAppT()
  const toast = useToast()
  const idPrefix = useId()
  const [form, setForm] = useState({ title: '', severity: 'P1', impact_statement: '' })
  const { mutate, isPending } = useMutation({
    mutationFn: data => api.post('/sd/major-incidents', data),
    onSuccess: onSaved,
    onError: e => toast.error(extractErr(e, 'Error'))
  })
  const set = k => e => setForm(f => ({ ...f, [k]: e.target.value }))
  const IS = { width: '100%', background: 'var(--surface-3)', border: '1px solid var(--surface-4)',
    borderRadius: 8, padding: '9px 13px', color: 'var(--text-1)', fontSize: 13,
    outline: 'none', fontFamily: 'inherit', boxSizing: 'border-box' }
  const LS = { fontSize: 11, fontWeight: 600, color: 'var(--text-2)', display: 'block',
    marginBottom: 5, textTransform: 'uppercase', letterSpacing: '0.06em' }

  return (
    <Modal open title={`🚨 ${t('service_desk.mi_declare_btn')}`} onClose={onClose}>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
        <div>
          <label htmlFor={`${idPrefix}-title`} style={LS}>{t('service_desk.mi_title_lbl')} *</label>
          <input id={`${idPrefix}-title`} value={form.title} onChange={set('title')} style={IS} />
        </div>
        <div>
          <label htmlFor={`${idPrefix}-severity`} style={LS}>{t('service_desk.mi_severity_lbl')}</label>
          <select id={`${idPrefix}-severity`} value={form.severity} onChange={set('severity')} style={IS}>
            <option value="P1">P1 — {t('service_desk.mi_severity')} (P1)</option>
            <option value="P2">P2 — {t('service_desk.mi_severity')} (P2)</option>
          </select>
        </div>
        <div>
          <label htmlFor={`${idPrefix}-impact`} style={LS}>{t('service_desk.mi_impact_lbl')}</label>
          <textarea id={`${idPrefix}-impact`} value={form.impact_statement} onChange={set('impact_statement')} rows={3}
            style={{ ...IS, resize: 'vertical' }} />
        </div>
        <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 10 }}>
          <Button variant="secondary" onClick={onClose}>{t('common.cancel')}</Button>
          <Button onClick={() => mutate(form)} disabled={isPending || !form.title} loading={isPending}
            style={{ background: `${COLOR.danger}20`, color: COLOR.danger, border: `1px solid ${COLOR.danger}40` }}>
            {t('service_desk.mi_declare_btn')}
          </Button>
        </div>
      </div>
    </Modal>
  )
}

// ── Routing Rules ─────────────────────────────────────────────────────────────
function RoutingRules() {
  const t = useAppT()
  const qc = useQueryClient()
  const toast = useToast()
  const [showNew, setShowNew] = useState(false)
  const [editingRule, setEditingRule] = useState(null)

  const { data: rules = [], isLoading } = useQuery({
    queryKey: ['sd-routing-rules'],
    queryFn: () => api.get('/sd/routing-rules').then(r => r.data),
  })

  const { mutate: toggleRule } = useMutation({
    mutationFn: ({ id, is_active }) => api.patch(`/sd/routing-rules/${id}`, { is_active }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['sd-routing-rules'] }),
    onError: e => toast.error(extractErr(e, 'Error'))
  })
  const { mutate: deleteRule } = useMutation({
    mutationFn: id => api.delete(`/sd/routing-rules/${id}`),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['sd-routing-rules'] }); toast.success(t('service_desk.routing_rule_deleted')) },

    onError: e => toast.error(extractErr(e, 'Error'))
  })

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 20 }}>
        <div style={{ fontSize: 12, color: 'var(--text-3)' }}>
          {t('service_desk.routing_no_rules_desc')}
        </div>
        <Button onClick={() => setShowNew(true)}>+ {t('service_desk.routing_new_title')}</Button>
      </div>

      {isLoading ? <Spinner /> :
       rules.length === 0 ? <EmptyState icon="⚡" title={t('service_desk.routing_no_rules')} description={t('service_desk.routing_no_rules_desc')} /> :
      <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
        {rules.map((rule, _i) => {
          let conds = {}, acts = {}
          try { conds = JSON.parse(rule.conditions || '{}'); acts = JSON.parse(rule.actions || '{}') } catch{ /* noop */ }
          return (
            <div key={rule.id} style={{ background: 'var(--surface-2)', border: `1px solid ${rule.is_active ? 'var(--surface-4)' : 'var(--surface-3)'}`,
              borderRadius: 10, padding: '14px 18px', opacity: rule.is_active ? 1 : 0.5 }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <div>
                  <span style={{ fontSize: 11, color: 'var(--text-3)', marginRight: 10 }}>#{rule.priority}</span>
                  <span style={{ fontSize: 14, fontWeight: 600, color: 'var(--text-1)' }}>{rule.name}</span>
                </div>
                <div style={{ display: 'flex', gap: 8 }}>
                  <button onClick={() => toggleRule({ id: rule.id, is_active: !rule.is_active })}
                    aria-pressed={rule.is_active}
                    aria-label={`${rule.is_active ? 'Desactivar' : 'Activar'} regla ${rule.name}`}
                    style={{ padding: '4px 12px', borderRadius: 6, border: '1px solid var(--surface-4)',
                      background: 'transparent', color: rule.is_active ? COLOR.success : 'var(--text-3)',
                      fontSize: 11, cursor: 'pointer', fontFamily: 'inherit' }}>
                    {rule.is_active ? t('service_desk.routing_active') : t('service_desk.routing_inactive')}
                  </button>
                  <button aria-label={`${t('common.edit')} ${rule.name}`} onClick={() => setEditingRule(rule)}
                    style={{ padding: '4px 10px', borderRadius: 6, border: '1px solid var(--surface-4)',
                      background: 'transparent', color: COLOR.accent, fontSize: 11, cursor: 'pointer', fontFamily: 'inherit' }}>
                    ✏ {t('common.edit')}
                  </button>
                  <button aria-label={`${t('common.delete')} ${rule.name}`} onClick={() => deleteRule(rule.id)}
                    style={{ padding: '4px 10px', borderRadius: 6, border: '1px solid var(--surface-4)',
                      background: 'transparent', color: COLOR.danger, fontSize: 11, cursor: 'pointer', fontFamily: 'inherit' }}>
                    {t('common.delete')}
                  </button>
                </div>
              </div>
              <div style={{ display: 'flex', gap: 24, marginTop: 10, fontSize: 12 }}>
                <div>
                  <span style={{ color: 'var(--text-3)', marginRight: 6 }}>SI</span>
                  {Object.entries(conds).map(([k,v]) => (
                    <span key={k} style={{ background: 'var(--surface-4)', borderRadius: 4,
                      padding: '2px 8px', marginRight: 6, color: 'var(--text-2)' }}>
                      {k}: {Array.isArray(v) ? v.join(', ') : v}
                    </span>
                  ))}
                </div>
                <div>
                  <span style={{ color: 'var(--text-3)', marginRight: 6 }}>THEN</span>
                  {Object.entries(acts).map(([k,v]) => (
                    <span key={k} style={{ background: `${COLOR.accent}15`, borderRadius: 4,
                      padding: '2px 8px', marginRight: 6, color: COLOR.accent }}>
                      {k}: {v}
                    </span>
                  ))}
                </div>
              </div>
            </div>
          )
        })}
      </div>}

      {showNew && <NewRoutingRuleModal onClose={() => setShowNew(false)} onSaved={() => {
        qc.invalidateQueries({ queryKey: ['sd-routing-rules'] })
        setShowNew(false)
        toast.success(t('service_desk.routing_rule_created'))
      }} />}
      {editingRule && <NewRoutingRuleModal rule={editingRule} onClose={() => setEditingRule(null)} onSaved={() => {
        qc.invalidateQueries({ queryKey: ['sd-routing-rules'] })
        setEditingRule(null)
        toast.success(t('service_desk.routing_rule_updated'))
      }} />}
    </div>
  )
}

function NewRoutingRuleModal({ onClose, onSaved, rule }) {
  const t = useAppT()
  const toast = useToast()
  const isEdit = !!rule

  const parseEntries = (jsonStr) => {
    try {
      const obj = typeof jsonStr === 'string' ? JSON.parse(jsonStr || '{}') : (jsonStr || {})
      return Object.entries(obj).map(([key, value]) => ({ key, value: Array.isArray(value) ? value.join(',') : String(value) }))
    } catch { return [] }
  }

  const [form, setForm] = useState(isEdit ? { name: rule.name, priority: rule.priority } : { name: '', priority: 100 })
  // Conditions list: each entry = { key, value }
  const [conditions, setConditions] = useState(isEdit ? parseEntries(rule.conditions) : [])
  // Actions list: each entry = { key, value }
  const [actions, setActions] = useState(isEdit ? parseEntries(rule.actions) : [{ key: 'assign_group', value: '' }])

  const { data: groups = [] } = useQuery({
    queryKey: ['sd-groups'],
    queryFn: () => api.get('/sd/groups').then(r => r.data),
  })
  const { data: users = [] } = useQuery({
    queryKey: ['users'],
    queryFn: () => api.get('/users').then(r => r.data),
  })
  const { data: slaPolices = [] } = useQuery({
    queryKey: ['sd-sla-policies'],
    queryFn: () => api.get('/sd/sla-policies').then(r => r.data).catch(() => []),
  })

  const { mutate, isPending } = useMutation({
    mutationFn: data => isEdit
      ? api.patch(`/sd/routing-rules/${rule.id}`, data)
      : api.post('/sd/routing-rules', data),
    onSuccess: onSaved,
    onError: e => toast.error(extractErr(e, 'Error')),
  })

  const IS = {
    width: '100%', background: 'var(--surface-3)', border: '1px solid var(--surface-4)',
    borderRadius: 8, padding: '8px 11px', color: 'var(--text-1)', fontSize: 12,
    outline: 'none', fontFamily: 'inherit', boxSizing: 'border-box',
  }
  const LS = {
    fontSize: 10, fontWeight: 600, color: 'var(--text-3)', display: 'block',
    marginBottom: 4, textTransform: 'uppercase', letterSpacing: '0.06em',
  }

  const COND_TYPES = [
    { key: 'ticket_type',     label: t('service_desk.ticket_type') },
    { key: 'priority',        label: t('service_desk.ticket_priority') },
    { key: 'keyword_in_title',label: t('service_desk.ticket_title') },
    { key: 'requester_domain',label: 'Domain' },
    { key: 'tag_contains',    label: 'Tag' },
    { key: 'time_of_day',     label: 'Time (HH:MM-HH:MM)' },
    { key: 'day_of_week',     label: 'Day of week' },
    { key: 'sla_policy_id',   label: 'SLA Policy' },
  ]
  const ACT_TYPES = [
    { key: 'assign_group',    label: t('service_desk.act_label') },
    { key: 'assign_user',     label: t('service_desk.act_no_agent') },
    { key: 'set_support_level', label: t('service_desk.groups_support_level') },
    { key: 'set_priority',    label: t('service_desk.ticket_priority') },
  ]

  // Prevent duplicate condition keys
  const usedCondKeys = conditions.map(c => c.key)
  const availCondTypes = COND_TYPES.filter(t => !usedCondKeys.includes(t.key))

  const addCondition = () => {
    const next = availCondTypes[0]
    if (next) setConditions(prev => [...prev, { key: next.key, value: '' }])
  }
  const removeCondition = (i) => setConditions(prev => prev.filter((_, idx) => idx !== i))
  const updateCond = (i, patch) => setConditions(prev => prev.map((c, idx) => idx === i ? { ...c, ...patch } : c))

  const addAction = () => {
    const usedActKeys = actions.map(a => a.key)
    const next = ACT_TYPES.find(t => !usedActKeys.includes(t.key))
    if (next) setActions(prev => [...prev, { key: next.key, value: '' }])
  }
  const removeAction = (i) => setActions(prev => prev.filter((_, idx) => idx !== i))
  const updateAct = (i, patch) => setActions(prev => prev.map((a, idx) => idx === i ? { ...a, ...patch } : a))

  const renderCondValue = (cond, i) => {
    const upd = (v) => updateCond(i, { value: v })
    if (cond.key === 'ticket_type') return (
      <select value={cond.value} onChange={e => upd(e.target.value)} style={IS}>
        <option value="">{t('service_desk.cond_any_type')}</option>
        {[['incident','Incidencia'],['service_request','Solicitud'],['change','Cambio'],['problem','Problema']].map(([v,l]) =>
          <option key={v} value={v}>{l}</option>)}
      </select>
    )
    if (cond.key === 'priority') return (
      <select value={cond.value} onChange={e => upd(e.target.value)} style={IS}>
        <option value="">{t('service_desk.cond_any_priority')}</option>
        {Object.entries(PRIORITY_LABEL).map(([v, l]) => <option key={v} value={v}>{l}</option>)}
      </select>
    )
    if (cond.key === 'sla_policy_id') return (
      <select value={cond.value} onChange={e => upd(e.target.value)} style={IS}>
        <option value="">{t('service_desk.cond_any_policy')}</option>
        {slaPolices.map(p => <option key={p.id} value={p.id}>{p.name}</option>)}
      </select>
    )
    if (cond.key === 'day_of_week') {
      const DAYS = [['monday','Lun'],['tuesday','Mar'],['wednesday','Mié'],['thursday','Jue'],['friday','Vie'],['saturday','Sáb'],['sunday','Dom']]
      const selected = cond.value ? cond.value.split(',') : []
      return (
        <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap' }}>
          {DAYS.map(([v, l]) => (
            <button key={v} type="button"
              onClick={() => {
                const next = selected.includes(v) ? selected.filter(d => d !== v) : [...selected, v]
                upd(next.join(','))
              }}
              style={{ padding: '3px 7px', borderRadius: 5, border: '1px solid var(--surface-4)',
                fontSize: 11, cursor: 'pointer', fontFamily: 'inherit',
                background: selected.includes(v) ? 'var(--accent)' : 'var(--surface-3)',
                color: selected.includes(v) ? '#fff' : 'var(--text-2)' }}>
              {l}
            </button>
          ))}
        </div>
      )
    }
    return (
      <input value={cond.value} onChange={e => upd(e.target.value)} style={IS}
        placeholder={
          cond.key === 'keyword_in_title' ? 'urgente, VIP, bloqueado...' :
          cond.key === 'requester_domain'  ? 'acme.com, acorp.es...' :
          cond.key === 'tag_contains'      ? 'backend, producción...' :
          cond.key === 'time_of_day'       ? '08:00-17:00' : ''
        }
      />
    )
  }

  const renderActValue = (act, i) => {
    const upd = (v) => updateAct(i, { value: v })
    if (act.key === 'assign_group') return (
      <select value={act.value} onChange={e => upd(e.target.value)} style={IS}>
        <option value="">{t('service_desk.act_no_group')}</option>
        {groups.map(g => <option key={g.id} value={g.id}>{g.name}</option>)}
      </select>
    )
    if (act.key === 'assign_user') return (
      <select value={act.value} onChange={e => upd(e.target.value)} style={IS}>
        <option value="">{t('service_desk.act_no_agent')}</option>
        {users.map(u => <option key={u.id} value={u.id}>{u.full_name}</option>)}
      </select>
    )
    if (act.key === 'set_support_level') return (
      <select value={act.value} onChange={e => upd(e.target.value)} style={IS}>
        <option value="">{t('service_desk.act_no_change')}</option>
        {[['l1','L1 — Básico'],['l2','L2 — Técnico'],['l3','L3 — Experto']].map(([v, l]) => <option key={v} value={v}>{l}</option>)}
      </select>
    )
    if (act.key === 'set_priority') return (
      <select value={act.value} onChange={e => upd(e.target.value)} style={IS}>
        <option value="">No cambiar</option>
        {Object.entries(PRIORITY_LABEL).map(([v, l]) => <option key={v} value={v}>{l}</option>)}
      </select>
    )
    return <input value={act.value} onChange={e => upd(e.target.value)} style={IS} />
  }

  const handleSave = () => {
    if (!form.name.trim()) { toast.error(t('service_desk.routing_name_required')); return }
    const condObj = {}
    for (const c of conditions) {
      if (!c.value) continue
      if (c.key === 'priority' || c.key === 'day_of_week') {
        condObj[c.key] = c.value.includes(',') ? c.value.split(',') : c.value
      } else {
        condObj[c.key] = c.value
      }
    }
    const actObj = {}
    for (const a of actions) {
      if (a.value) actObj[a.key] = a.value
    }
    if (Object.keys(actObj).length === 0) { toast.error(t('service_desk.routing_needs_action')); return }
    mutate({
      name: form.name.trim(),
      priority: Number(form.priority),
      conditions: condObj,
      actions: actObj,
      is_active: true,
    })
  }

  return (
    <Modal open title={isEdit ? `${t('service_desk.routing_new_title')} ${rule.name}` : t('service_desk.routing_new_title')} onClose={onClose}>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 16, maxHeight: '80vh', overflowY: 'auto' }}>

        {/* Name + priority */}
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 90px', gap: 12 }}>
          <div>
            <label style={LS}>{t('service_desk.routing_name_lbl')} *</label>
            <input value={form.name} onChange={e => setForm(f => ({ ...f, name: e.target.value }))}
              style={IS} autoFocus />
          </div>
          <div>
            <label style={LS}>{t('service_desk.routing_order_lbl')}</label>
            <input type="number" value={form.priority}
              onChange={e => setForm(f => ({ ...f, priority: e.target.value }))}
              style={{ ...IS }} />
          </div>
        </div>

        {/* Conditions */}
        <div style={{ background: 'var(--surface-1)', borderRadius: 10, padding: 14 }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 10 }}>
            <span style={{ fontSize: 12, fontWeight: 700, color: 'var(--text-2)' }}>{t('service_desk.cond_field')}</span>
            <button type="button" onClick={addCondition}
              disabled={availCondTypes.length === 0}
              style={{ fontSize: 11, padding: '3px 10px', borderRadius: 6, border: '1px solid var(--surface-4)',
                background: 'var(--surface-3)', color: 'var(--text-2)', cursor: availCondTypes.length ? 'pointer' : 'not-allowed',
                fontFamily: 'inherit' }}>
              + Condición
            </button>
          </div>
          {conditions.length === 0 && (
            <div style={{ fontSize: 12, color: 'var(--text-3)', textAlign: 'center', padding: '10px 0' }}>
              {t('service_desk.routing_no_rules')}
            </div>
          )}
          {conditions.map((cond, i) => (
            <div key={i} style={{ display: 'grid', gridTemplateColumns: '180px 1fr 28px', gap: 8, marginBottom: 8, alignItems: 'start' }}>
              <div>
                <label style={LS}>{t('service_desk.cond_field')}</label>
                <select value={cond.key}
                  onChange={e => updateCond(i, { key: e.target.value, value: '' })}
                  style={IS}>
                  {COND_TYPES.filter(t => t.key === cond.key || !usedCondKeys.filter((_,idx) => idx !== i).includes(t.key)).map(t =>
                    <option key={t.key} value={t.key}>{t.label}</option>
                  )}
                </select>
              </div>
              <div>
                <label style={LS}>{t('service_desk.cond_value')}</label>
                {renderCondValue(cond, i)}
              </div>
              <div style={{ paddingTop: 20 }}>
                <button type="button" onClick={() => removeCondition(i)}
                  style={{ background: 'none', border: '1px solid var(--surface-4)', borderRadius: 5,
                    color: COLOR.danger, cursor: 'pointer', fontSize: 14, padding: '3px 6px', lineHeight: 1 }}>
                  ×
                </button>
              </div>
            </div>
          ))}
        </div>

        {/* Actions */}
        <div style={{ background: 'var(--surface-1)', borderRadius: 10, padding: 14 }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 10 }}>
            <span style={{ fontSize: 12, fontWeight: 700, color: 'var(--text-2)' }}>{t('service_desk.act_label')}</span>
            <button type="button" onClick={addAction}
              disabled={actions.length >= ACT_TYPES.length}
              style={{ fontSize: 11, padding: '3px 10px', borderRadius: 6, border: '1px solid var(--surface-4)',
                background: 'var(--surface-3)', color: 'var(--text-2)', cursor: actions.length < ACT_TYPES.length ? 'pointer' : 'not-allowed',
                fontFamily: 'inherit' }}>
              + Acción
            </button>
          </div>
          {actions.map((act, i) => (
            <div key={i} style={{ display: 'grid', gridTemplateColumns: '170px 1fr 28px', gap: 8, marginBottom: 8, alignItems: 'start' }}>
              <div>
                <label style={LS}>{t('service_desk.act_label')}</label>
                <select value={act.key}
                  onChange={e => updateAct(i, { key: e.target.value, value: '' })}
                  style={IS}>
                  {ACT_TYPES.filter(t => t.key === act.key || !actions.filter((_,idx) => idx !== i).map(a => a.key).includes(t.key)).map(t =>
                    <option key={t.key} value={t.key}>{t.label}</option>
                  )}
                </select>
              </div>
              <div>
                <label style={LS}>{t('service_desk.cond_value')}</label>
                {renderActValue(act, i)}
              </div>
              <div style={{ paddingTop: 20 }}>
                <button type="button" onClick={() => removeAction(i)}
                  style={{ background: 'none', border: '1px solid var(--surface-4)', borderRadius: 5,
                    color: COLOR.danger, cursor: 'pointer', fontSize: 14, padding: '3px 6px', lineHeight: 1 }}>
                  ×
                </button>
              </div>
            </div>
          ))}
        </div>

        <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 10 }}>
          <Button variant="secondary" onClick={onClose}>{t('common.cancel')}</Button>
          <Button onClick={handleSave} disabled={isPending || !form.name} loading={isPending}>{isEdit ? t('common.save') : t('service_desk.routing_new_title')}</Button>
        </div>
      </div>
    </Modal>
  )
}

// ── Reports / Config (simplificado) ──────────────────────────────────────────
// ── Catalog Config ────────────────────────────────────────────────────────────
function CatalogConfig() {
  const t = useAppT()
  const qc = useQueryClient()
  const toast = useToast()
  const [showNewCat, setShowNewCat] = useState(false)
  const [showNewSvc, setShowNewSvc] = useState(false)

  const { data: catalog = [], isLoading } = useQuery({
    queryKey: ['sd-catalog'],
    queryFn: () => api.get('/sd/catalog').then(r => r.data),
  })

  const [editingCat, setEditingCat] = useState(null)
  const [editingSvc, setEditingSvc] = useState(null)

  const { mutate: createCat, isPending: creatingCat } = useMutation({
    mutationFn: d => api.post('/sd/catalog/categories', d),
    onSuccess: () => { qc.invalidateQueries({queryKey:['sd-catalog']}); setShowNewCat(false); toast.success(t('service_desk.cat_new_title')) },

    onError: e => toast.error(extractErr(e, 'Error'))
  })
  const { mutate: updateCat } = useMutation({
    mutationFn: ({id, ...d}) => api.patch(`/sd/catalog/categories/${id}`, d),
    onSuccess: () => { qc.invalidateQueries({queryKey:['sd-catalog']}); setEditingCat(null); toast.success(t('service_desk.cat_edit_title')) },
    onError: e => toast.error(extractErr(e, 'Error')),
  })
  const { mutate: deleteCat } = useMutation({
    mutationFn: id => api.delete(`/sd/catalog/categories/${id}`),
    onSuccess: () => { qc.invalidateQueries({queryKey:['sd-catalog']}); toast.success(t('common.delete')) },
    onError: e => toast.error(extractErr(e, 'Error')),
  })
  const { mutate: createSvc, isPending: creatingSvc } = useMutation({
    mutationFn: d => api.post('/sd/catalog/services', d),
    onSuccess: () => { qc.invalidateQueries({queryKey:['sd-catalog']}); setShowNewSvc(false); toast.success(t('service_desk.svc_new_title')) },

    onError: e => toast.error(extractErr(e, 'Error'))
  })
  const { mutate: updateSvc } = useMutation({
    mutationFn: ({id, ...d}) => api.patch(`/sd/catalog/services/${id}`, d),
    onSuccess: () => { qc.invalidateQueries({queryKey:['sd-catalog']}); setEditingSvc(null); toast.success(t('service_desk.svc_edit_title')) },
    onError: e => toast.error(extractErr(e, 'Error')),
  })
  const { mutate: deleteSvc } = useMutation({
    mutationFn: id => api.delete(`/sd/catalog/services/${id}`),
    onSuccess: () => { qc.invalidateQueries({queryKey:['sd-catalog']}); toast.success(t('common.delete')) },
    onError: e => toast.error(extractErr(e, 'Error')),
  })

  const IS = { width:'100%', background:'var(--surface-3)', border:'1px solid var(--surface-4)',
    borderRadius:8, padding:'9px 13px', color:'var(--text-1)', fontSize:13,
    outline:'none', fontFamily:'inherit', boxSizing:'border-box' }
  const LS = { fontSize:11, fontWeight:600, color:'var(--text-2)', display:'block',
    marginBottom:5, textTransform:'uppercase', letterSpacing:'0.06em' }

  return (
    <div>
      <div style={{ display:'flex', justifyContent:'space-between', alignItems:'center', marginBottom:20 }}>
        <div style={{ fontSize:12, color:'var(--text-3)' }}>{t('service_desk.catalog_empty_desc')}</div>
        <div style={{ display:'flex', gap:8 }}>
          <Button variant="secondary" onClick={() => setShowNewSvc(true)} disabled={catalog.length===0}>+ {t('service_desk.svc_new_title')}</Button>
          <Button onClick={() => setShowNewCat(true)}>+ {t('service_desk.cat_new_title')}</Button>
        </div>
      </div>

      {isLoading ? <Spinner /> :
       catalog.length === 0 ? <EmptyState icon="📋" title={t('service_desk.catalog_empty')} description={t('service_desk.catalog_empty_desc')} /> :
      <div style={{ display:'flex', flexDirection:'column', gap:12 }}>
        {catalog.map(cat => (
          <div key={cat.id} style={{ background:'var(--surface-2)', border:'1px solid var(--surface-4)', borderRadius:12, overflow:'hidden' }}>
            <div style={{ padding:'14px 18px', background:'var(--surface-1)', borderBottom:'1px solid var(--surface-4)',
              display:'flex', alignItems:'center', gap:10 }}>
              <span style={{ fontSize:18 }}>{cat.icon || '📁'}</span>
              <span style={{ fontSize:14, fontWeight:600, color:'var(--text-1)' }}>{cat.name}</span>
              {cat.description && <span style={{ fontSize:12, color:'var(--text-3)' }}>— {cat.description}</span>}
              <span style={{ marginLeft:'auto', fontSize:11, color:'var(--text-3)' }}>{cat.services?.length || 0} servicios</span>
              <div style={{ display:'flex', gap:6, marginLeft:8 }}>
                <button onClick={() => setEditingCat(cat)}
                  style={{ padding:'3px 8px', borderRadius:5, border:'1px solid var(--surface-4)', background:'transparent', color:'var(--accent)', fontSize:11, cursor:'pointer', fontFamily:'inherit' }}>✏ Editar</button>
                <button onClick={() => { openConfirmGlobal({ message: '¿Eliminar categoría y todos sus servicios?', onConfirm: () => deleteCat(cat.id), danger: true }) }}
                  style={{ padding:'3px 8px', borderRadius:5, border:`1px solid ${COLOR.danger}30`, background:'transparent', color:COLOR.danger, fontSize:11, cursor:'pointer', fontFamily:'inherit' }}>🗑 Eliminar</button>
              </div>
            </div>
            {cat.services?.length > 0 && (
              <table style={{ width:'100%', borderCollapse:'collapse' }}>
                <tbody>
                  {cat.services.map(svc => (
                    <tr key={svc.id} style={{ borderBottom:'1px solid var(--surface-4)' }}>
                      <td style={{ padding:'10px 18px', fontSize:13, color:'var(--text-1)', fontWeight:500 }}>{svc.name}</td>
                      <td style={{ padding:'10px 8px', fontSize:11, color:'var(--text-2)' }}>{svc.ticket_type?.replace(/_/g,' ')}</td>
                      <td style={{ padding:'10px 8px' }}><PBadge v={svc.default_priority} /></td>
                      <td style={{ padding:'10px 8px', fontSize:11, color:'var(--text-2)' }}>R:{svc.sla_response_hours}h / Res:{svc.sla_resolution_hours}h</td>
                      <td style={{ padding:'10px 8px', fontSize:11, color:'var(--text-3)' }}>{svc.requires_approval ? '🔐' : ''}</td>
                      <td style={{ padding:'6px 12px' }}>
                        <div style={{ display:'flex', gap:6 }}>
                          <button onClick={() => setEditingSvc({...svc, category_id: cat.id})}
                            style={{ padding:'3px 8px', borderRadius:5, border:'1px solid var(--surface-4)', background:'transparent', color:'var(--accent)', fontSize:11, cursor:'pointer', fontFamily:'inherit' }}>✏</button>
                          <button onClick={() => { openConfirmGlobal({ message: '¿Eliminar servicio?', onConfirm: () => deleteSvc(svc.id), danger: true }) }}
                            style={{ padding:'3px 8px', borderRadius:5, border:`1px solid ${COLOR.danger}30`, background:'transparent', color:COLOR.danger, fontSize:11, cursor:'pointer', fontFamily:'inherit' }}>🗑</button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        ))}
      </div>}

      {showNewCat && (
        <NewCategoryModal onClose={() => setShowNewCat(false)}
          onSave={d => createCat(d)} isPending={creatingCat} IS={IS} LS={LS} />
      )}
      {editingCat && (
        <NewCategoryModal
          initial={editingCat}
          onClose={() => setEditingCat(null)}
          onSave={d => updateCat({id: editingCat.id, ...d})}
          isPending={false} IS={IS} LS={LS} />
      )}
      {showNewSvc && (
        <NewServiceModal catalog={catalog} onClose={() => setShowNewSvc(false)}
          onSave={d => createSvc(d)} isPending={creatingSvc} IS={IS} LS={LS} />
      )}
      {editingSvc && (
        <NewServiceModal
          catalog={catalog} initial={editingSvc}
          onClose={() => setEditingSvc(null)}
          onSave={d => updateSvc({id: editingSvc.id, ...d})}
          isPending={false} IS={IS} LS={LS} />
      )}
    </div>
  )
}

function NewCategoryModal({ onClose, onSave, isPending, IS, LS, initial }) {
  const t = useAppT()
  const [form, setForm] = useState({
    name: initial?.name || '', description: initial?.description || '',
    icon: initial?.icon || '📁', color: initial?.color || '#4f8ef7'
  })
  const set = k => e => setForm(f => ({...f, [k]: e.target.value}))
  return (
    <Modal open title={initial ? t('service_desk.cat_edit_title') : t('service_desk.cat_new_title')} onClose={onClose}>
      <div style={{ display:'flex', flexDirection:'column', gap:14 }}>
        <div style={{ display:'grid', gridTemplateColumns:'1fr auto auto', gap:10 }}>
          <div><label style={LS}>{t('common.name')} *</label><input value={form.name} onChange={set('name')} style={IS} /></div>
        </div>
          <div><label style={LS}>Icon</label><input value={form.icon} onChange={set('icon')} style={{...IS, width:60, textAlign:'center'}} /></div>
          <div><label style={LS}>Color</label><input type="color" value={form.color} onChange={set('color')} style={{...IS, width:60, padding:'4px'}} /></div>
        <div style={{ display:'flex', justifyContent:'flex-end', gap:10 }}>
          <Button variant="secondary" onClick={onClose}>{t('common.cancel')}</Button>
          <Button onClick={() => onSave(form)} disabled={isPending || !form.name} loading={isPending}>{initial ? t('common.save') : t('common.new')}</Button>
        </div>
      </div>
    </Modal>
  )
}

function NewServiceModal({ catalog, onClose, onSave, isPending, IS, LS, initial }) {
  const t = useAppT()
  const [form, setForm] = useState({
    name: initial?.name || '',
    category_id: initial?.category_id || catalog[0]?.id || '',
    ticket_type: initial?.ticket_type || 'service_request',
    default_priority: initial?.default_priority || 'p3_medium',
    sla_response_hours: initial?.sla_response_hours || 4,
    sla_resolution_hours: initial?.sla_resolution_hours || 24,
    requires_approval: initial?.requires_approval || false,
    is_visible_to_clients: initial?.is_visible_to_clients ?? true,
  })
  const set = k => e => setForm(f => ({...f, [k]: e.target.type==='checkbox' ? e.target.checked : e.target.value}))
  return (
    <Modal open title={initial ? t('service_desk.svc_edit_title') : t('service_desk.svc_new_title')} onClose={onClose}>
      <div style={{ display:'grid', gridTemplateColumns:'1fr 1fr', gap:14 }}>
        <div style={{ gridColumn:'1/-1' }}><label style={LS}>{t('common.name')} *</label><input value={form.name} onChange={set('name')} style={IS} /></div>
        <div>
          <label style={LS}>{t('service_desk.svc_ticket_type')}</label>
          <select value={form.category_id} onChange={set('category_id')} style={IS}>
            {catalog.map(c => <option key={c.id} value={c.id}>{c.name}</option>)}
          </select>
        </div>
        <div>
          <label style={LS}>{t('service_desk.svc_ticket_type')}</label>
          <select value={form.ticket_type} onChange={set('ticket_type')} style={IS}>
            {['incident','service_request','change','question'].map(tk => <option key={tk} value={tk}>{tk.replace(/_/g,' ')}</option>)}
          </select>
        </div>
        <div>
          <label style={LS}>{t('service_desk.svc_default_priority')}</label>
          <select value={form.default_priority} onChange={set('default_priority')} style={IS}>
            {['p1_critical','p2_high','p3_medium','p4_low'].map(p => <option key={p} value={p}>{PRIORITY_LABEL[p]}</option>)}
          </select>
        </div>
        <div style={{ display:'grid', gridTemplateColumns:'1fr 1fr', gap:8 }}>
          <div><label style={LS}>{t('service_desk.sla_response_h')}</label><input type="number" value={form.sla_response_hours} onChange={set('sla_response_hours')} style={IS} /></div>
          <div><label style={LS}>{t('service_desk.sla_resolution_h')}</label><input type="number" value={form.sla_resolution_hours} onChange={set('sla_resolution_hours')} style={IS} /></div>
        </div>
        <div style={{ display:'flex', alignItems:'center', gap:10 }}>
          <input type="checkbox" id="req_appr" checked={form.requires_approval} onChange={set('requires_approval')} />
          <label htmlFor="req_appr" style={{ fontSize:13, color:'var(--text-1)', cursor:'pointer' }}>{t('service_desk.svc_requires_approval')}</label>
        </div>
        <div style={{ gridColumn:'1/-1', display:'flex', justifyContent:'flex-end', gap:10 }}>
          <Button variant="secondary" onClick={onClose}>{t('common.cancel')}</Button>
          <Button onClick={() => onSave(form)} disabled={isPending || !form.name} loading={isPending}>{initial ? t('common.save') : t('service_desk.svc_new_title')}</Button>
        </div>
      </div>
    </Modal>
  )
}

// ── SLA Config ────────────────────────────────────────────────────────────────
function SLAConfig() {
  const qc = useQueryClient()
  const toast = useToast()
  const [showNew, setShowNew] = useState(false)

  const { data: policies = [], isLoading } = useQuery({
    queryKey: ['sd-sla-policies'],
    queryFn: () => api.get('/sd/sla-policies').then(r => r.data),
  })
  const [editing, setEditing] = useState(null)
  const { mutate: create, isPending } = useMutation({
    mutationFn: d => api.post('/sd/sla-policies', d),
    onSuccess: () => { qc.invalidateQueries({queryKey:['sd-sla-policies']}); setShowNew(false); toast.success(t('service_desk.sla_created')) },

    onError: e => toast.error(extractErr(e, 'Error'))
  })
  const { mutate: update } = useMutation({
    mutationFn: ({id, ...d}) => api.patch(`/sd/sla-policies/${id}`, d),
    onSuccess: () => { qc.invalidateQueries({queryKey:['sd-sla-policies']}); setEditing(null); toast.success(t('service_desk.sla_updated')) },
    onError: e => toast.error(extractErr(e, 'Error')),
  })
  const { mutate: remove } = useMutation({
    mutationFn: id => api.delete(`/sd/sla-policies/${id}`),
    onSuccess: () => { qc.invalidateQueries({queryKey:['sd-sla-policies']}); toast.success(t('service_desk.sla_deleted')) },
    onError: e => toast.error(extractErr(e, 'Error')),
  })

  const IS = { width:'100%', background:'var(--surface-3)', border:'1px solid var(--surface-4)',
    borderRadius:8, padding:'9px 13px', color:'var(--text-1)', fontSize:13,
    outline:'none', fontFamily:'inherit', boxSizing:'border-box' }
  const LS = { fontSize:11, fontWeight:600, color:'var(--text-2)', display:'block', marginBottom:5, textTransform:'uppercase', letterSpacing:'0.06em' }

  return (
    <div>
      <div style={{ display:'flex', justifyContent:'space-between', marginBottom:20 }}>
        <div style={{ fontSize:12, color:'var(--text-3)' }}>{t('service_desk.sla_empty_desc')}</div>
        <Button onClick={() => setShowNew(true)}>+ {t('service_desk.sla_new_title')}</Button>
      </div>

      {isLoading ? <Spinner /> :
       policies.length === 0 ? <EmptyState icon="⏱" title={t('service_desk.sla_empty')} description={t('service_desk.sla_empty_desc')} /> :
      <div style={{ display:'flex', flexDirection:'column', gap:12 }}>
        {policies.map(p => (
          <div key={p.id} style={{ background:'var(--surface-2)', border:`1px solid ${p.is_default ? 'var(--accent-glow)' : 'var(--surface-4)'}`, borderRadius:12, padding:20 }}>
            <div style={{ display:'flex', alignItems:'center', gap:10, marginBottom:16 }}>
              <span style={{ fontSize:14, fontWeight:600, color:'var(--text-1)' }}>{p.name}</span>
              {p.is_default && <span style={{ fontSize:10, background:'var(--accent-muted)', color:'var(--accent)', padding:'2px 8px', borderRadius:4, fontWeight: 600 }}>{t('service_desk.sla_default_policy').toUpperCase()}</span>}
              {p.business_hours_only && <span style={{ fontSize:10, background:'var(--surface-4)', color:'var(--text-2)', padding:'2px 8px', borderRadius:4 }}>{t('service_desk.sla_business_hours')}</span>}
              <div style={{ marginLeft:'auto', display:'flex', gap:8 }}>
                <button onClick={() => setEditing(p)}
                  style={{ padding:'3px 10px', borderRadius:6, border:'1px solid var(--surface-4)', background:'transparent', color:'var(--accent)', fontSize:11, cursor:'pointer', fontFamily:'inherit' }}>✏ Editar</button>
                <button onClick={() => { openConfirmGlobal({ message: '¿Eliminar esta política SLA?', onConfirm: () => remove(p.id), danger: true }) }}
                  style={{ padding:'3px 10px', borderRadius:6, border:`1px solid ${COLOR.danger}30`, background:'transparent', color:COLOR.danger, fontSize:11, cursor:'pointer', fontFamily:'inherit' }}>🗑 Eliminar</button>
              </div>
            </div>
            <div style={{ display:'grid', gridTemplateColumns:'repeat(4,1fr)', gap:10 }}>
              {[['P1 Crítico', 'p1', COLOR.danger], ['P2 Alto', 'p2', '#fb923c'], ['P3 Medio', 'p3', COLOR.warning], ['P4 Bajo', 'p4', COLOR.text2]].map(([label, key, color]) => (
                <div key={key} style={{ background:'var(--surface-1)', borderRadius:8, padding:12, borderTop:`3px solid ${color}` }}>
                  <div style={{ fontSize:11, fontWeight:700, color, marginBottom:8 }}>{label}</div>
                  <div style={{ fontSize:12, color:'var(--text-2)' }}>
                    <div>Resp: <strong style={{ color:'var(--text-1)' }}>{p[`${key}_response_hours`]}h</strong></div>
                    <div>Res: <strong style={{ color:'var(--text-1)' }}>{p[`${key}_resolution_hours`]}h</strong></div>
                  </div>
                </div>
              ))}
            </div>
          </div>
        ))}
      </div>}

      {showNew && (
        <Modal open title={t('service_desk.sla_new_title')} onClose={() => setShowNew(false)} size="lg">
          <NewSLAForm IS={IS} LS={LS} onSave={d => create(d)} isPending={isPending} onClose={() => setShowNew(false)} />
        </Modal>
      )}
      {editing && (
        <Modal open title={t('service_desk.sla_edit_title')} onClose={() => setEditing(null)} size="lg">
          <NewSLAForm IS={IS} LS={LS} initial={editing}
            onSave={d => update({id: editing.id, ...d})}
            isPending={false} onClose={() => setEditing(null)} />
        </Modal>
      )}
    </div>
  )
}

function NewSLAForm({ IS, LS, onSave, isPending, onClose, initial }) {
  const t = useAppT()
  const [form, setForm] = useState({
    name: initial?.name || '', description: initial?.description || '',
    is_default: initial?.is_default || false, business_hours_only: initial?.business_hours_only || false,
    p1_response_hours: initial?.p1_response_hours ?? 1, p1_resolution_hours: initial?.p1_resolution_hours ?? 4,
    p2_response_hours: initial?.p2_response_hours ?? 4, p2_resolution_hours: initial?.p2_resolution_hours ?? 8,
    p3_response_hours: initial?.p3_response_hours ?? 8, p3_resolution_hours: initial?.p3_resolution_hours ?? 24,
    p4_response_hours: initial?.p4_response_hours ?? 24, p4_resolution_hours: initial?.p4_resolution_hours ?? 72,
  })
  const set = k => e => setForm(f => ({...f, [k]: e.target.type==='checkbox' ? e.target.checked : e.target.value}))
  return (
    <div style={{ display:'grid', gridTemplateColumns:'1fr 1fr', gap:14 }}>
      <div style={{ gridColumn:'1/-1' }}><label style={LS}>{t('common.name')} *</label><input value={form.name} onChange={set('name')} style={IS} /></div>
      {[['P1 Crítico', 'p1'], ['P2 Alto', 'p2'], ['P3 Medio', 'p3'], ['P4 Bajo', 'p4']].map(([label, key]) => (
        <div key={key} style={{ background:'var(--surface-1)', borderRadius:10, padding:14 }}>
          <div style={{ fontSize:12, fontWeight:700, color:'var(--text-2)', marginBottom:10 }}>{label}</div>
          <div style={{ display:'grid', gridTemplateColumns:'1fr 1fr', gap:8 }}>
            <div><label style={LS}>{t('service_desk.sla_response_h')}</label><input type="number" value={form[`${key}_response_hours`]} onChange={set(`${key}_response_hours`)} style={IS} /></div>
            <div><label style={LS}>{t('service_desk.sla_resolution_h')}</label><input type="number" value={form[`${key}_resolution_hours`]} onChange={set(`${key}_resolution_hours`)} style={IS} /></div>
          </div>
        </div>
      ))}
      <div style={{ gridColumn:'1/-1', display:'flex', gap:20, alignItems:'center' }}>
        <label style={{ display:'flex', gap:8, alignItems:'center', fontSize:13, color:'var(--text-1)', cursor:'pointer' }}>
          <input type="checkbox" checked={form.is_default} onChange={set('is_default')} />
          {t('service_desk.sla_default_policy')}
        </label>
        <label style={{ display:'flex', gap:8, alignItems:'center', fontSize:13, color:'var(--text-1)', cursor:'pointer' }}>
          <input type="checkbox" checked={form.business_hours_only} onChange={set('business_hours_only')} />
          {t('service_desk.sla_business_only')}
        </label>
      </div>
      <div style={{ gridColumn:'1/-1', display:'flex', justifyContent:'flex-end', gap:10 }}>
        <Button variant="secondary" onClick={onClose}>{t('common.cancel')}</Button>
        <Button onClick={() => onSave(form)} disabled={isPending || !form.name} loading={isPending}>{initial ? t('common.save') : t('service_desk.sla_new_title')}</Button>
      </div>
    </div>
  )
}

// ── Groups Config ─────────────────────────────────────────────────────────────
function GroupsConfig() {
  const t = useAppT()
  const qc = useQueryClient()
  const toast = useToast()
  const [showNew, setShowNew] = useState(false)

  const { data: groups = [], isLoading } = useQuery({
    queryKey: ['sd-groups'],
    queryFn: () => api.get('/sd/groups').then(r => r.data),
  })
  const { data: users = [] } = useQuery({
    queryKey: ['users'],
    queryFn: () => api.get('/users').then(r => r.data),
  })
  const [editing, setEditing] = useState(null)
  const { mutate: createGroup, isPending } = useMutation({
    mutationFn: d => api.post('/sd/groups', d),
    onSuccess: () => { qc.invalidateQueries({queryKey:['sd-groups']}); setShowNew(false); toast.success(t('service_desk.groups_created')) },

    onError: e => toast.error(extractErr(e, 'Error'))
  })
  const { mutate: updateGroup } = useMutation({
    mutationFn: ({id, ...d}) => api.patch(`/sd/groups/${id}`, d),
    onSuccess: () => { qc.invalidateQueries({queryKey:['sd-groups']}); setEditing(null); toast.success(t('service_desk.groups_updated')) },
    onError: e => toast.error(extractErr(e, 'Error')),
  })
  const { mutate: deleteGroup } = useMutation({
    mutationFn: id => api.delete(`/sd/groups/${id}`),
    onSuccess: () => { qc.invalidateQueries({queryKey:['sd-groups']}); toast.success(t('service_desk.groups_deleted')) },
    onError: e => toast.error(extractErr(e, 'Error')),
  })
  const { mutate: addMember } = useMutation({
    mutationFn: ({gid, uid}) => api.post(`/sd/groups/${gid}/members/${uid}`),
    onSuccess: () => qc.invalidateQueries({queryKey:['sd-groups']}),
    onError: e => toast.error(extractErr(e, 'Error'))
  })
  const { mutate: removeMember } = useMutation({
    mutationFn: ({gid, uid}) => api.delete(`/sd/groups/${gid}/members/${uid}`),
    onSuccess: () => qc.invalidateQueries({queryKey:['sd-groups']}),
    onError: e => toast.error(extractErr(e, 'Error'))
  })

  const IS = { width:'100%', background:'var(--surface-3)', border:'1px solid var(--surface-4)',
    borderRadius:8, padding:'9px 13px', color:'var(--text-1)', fontSize:13,
    outline:'none', fontFamily:'inherit', boxSizing:'border-box' }
  const LS = { fontSize:11, fontWeight:600, color:'var(--text-2)', display:'block', marginBottom:5, textTransform:'uppercase', letterSpacing:'0.06em' }

  return (
    <div>
      <div style={{ display:'flex', justifyContent:'space-between', marginBottom:20 }}>
        <div style={{ fontSize:12, color:'var(--text-3)' }}>{t('service_desk.groups_empty_desc')}</div>
        <Button onClick={() => setShowNew(true)}>+ {t('service_desk.groups_new_title')}</Button>
      </div>

      {isLoading ? <Spinner /> :
       groups.length === 0 ? <EmptyState icon="👥" title={t('service_desk.groups_empty')} description={t('service_desk.groups_empty_desc')} /> :
      <div style={{ display:'flex', flexDirection:'column', gap:12 }}>
        {groups.map(g => {
          const memberIds = new Set((g.members || []).map(m => m.id))
          const available = (users || []).filter(u => !memberIds.has(u.id))
          return (
            <div key={g.id} style={{ background:'var(--surface-2)', border:'1px solid var(--surface-4)', borderRadius:12, padding:20 }}>
              <div style={{ display:'flex', justifyContent:'space-between', alignItems:'center', marginBottom:14 }}>
                <div style={{ display:'flex', alignItems:'center', gap:8 }}>
                  <span style={{ fontSize:14, fontWeight:600, color:'var(--text-1)' }}>{g.name}</span>
                  <span style={{ fontSize:11, background:'var(--surface-4)', color:'var(--text-2)', padding:'2px 8px', borderRadius:4 }}>{g.support_level?.toUpperCase() || 'L1'}</span>
                </div>
                <div style={{ display:'flex', gap:8, alignItems:'center' }}>
                  {available.length > 0 && (
                    <select defaultValue="" onChange={e => { if(e.target.value) addMember({gid:g.id, uid:e.target.value}); e.target.value='' }}
                      style={{ ...IS, width:'auto', fontSize:12 }}>
                      <option value="" disabled>+ Añadir miembro</option>
                      {available.map(u => <option key={u.id} value={u.id}>{u.full_name}</option>)}
                    </select>
                  )}
                  <button onClick={() => setEditing(g)}
                    style={{ padding:'4px 10px', borderRadius:6, border:'1px solid var(--surface-4)', background:'transparent', color:'var(--accent)', fontSize:11, cursor:'pointer', fontFamily:'inherit', whiteSpace:'nowrap' }}>✏ Editar</button>
                  <button onClick={() => { openConfirmGlobal({ message: `¿Eliminar el grupo "${g.name}"?`, onConfirm: () => deleteGroup(g.id), danger: true }) }}
                    style={{ padding:'4px 10px', borderRadius:6, border:`1px solid ${COLOR.danger}30`, background:'transparent', color:COLOR.danger, fontSize:11, cursor:'pointer', fontFamily:'inherit', whiteSpace:'nowrap' }}>🗑 Eliminar</button>
                </div>
              </div>
              {g.description && <div style={{ fontSize:12, color:'var(--text-3)', marginBottom:12 }}>{g.description}</div>}
              <div style={{ display:'flex', gap:8, flexWrap:'wrap' }}>
                {(g.members || []).map(m => (
                  <div key={m.id} style={{ display:'flex', alignItems:'center', gap:6, background:'var(--surface-1)',
                    border:'1px solid var(--surface-4)', borderRadius:20, padding:'4px 12px' }}>
                    <span style={{ fontSize:12, color:'var(--text-1)' }}>{m.full_name}</span>
                    {m.is_lead && <span style={{ fontSize:10, color:COLOR.accent }}>★</span>}
                    <button onClick={() => removeMember({gid:g.id, uid:m.id})}
                      style={{ background:'none', border:'none', color:'var(--text-4)', cursor:'pointer',
                        fontSize:14, padding:'0 0 0 4px', lineHeight:1 }}>×</button>
                  </div>
                ))}
                {(!g.members || g.members.length === 0) &&
                  <span style={{ fontSize:12, color:'var(--text-4)' }}>{t('service_desk.groups_no_members')}</span>}
              </div>
            </div>
          )
        })}
      </div>}

      {showNew && (
        <Modal open title={t('service_desk.groups_new_title')} onClose={() => setShowNew(false)}>
          <div style={{ display:'flex', flexDirection:'column', gap:14 }}>
            <NewGroupForm IS={IS} LS={LS} onSave={createGroup} isPending={isPending} onClose={() => setShowNew(false)} />
          </div>
        </Modal>
      )}
      {editing && (
        <Modal open title={t('service_desk.groups_edit_title')} onClose={() => setEditing(null)}>
          <div style={{ display:'flex', flexDirection:'column', gap:14 }}>
            <NewGroupForm IS={IS} LS={LS} initial={editing}
              onSave={d => updateGroup({id: editing.id, ...d})}
              isPending={false} onClose={() => setEditing(null)} />
          </div>
        </Modal>
      )}
    </div>
  )
}

function NewGroupForm({ IS, LS, onSave, isPending, onClose, initial }) {
  const t = useAppT()
  const [form, setForm] = useState({
    name: initial?.name || '', description: initial?.description || '',
    support_level: initial?.support_level || 'l1'
  })
  const set = k => e => setForm(f => ({...f, [k]: e.target.value}))
  return (
    <>
      <div><label style={LS}>{t('common.name')} *</label><input value={form.name} onChange={set('name')} style={IS} /></div>
      <div><label style={LS}>{t('service_desk.groups_support_level')}</label>
        <select value={form.support_level} onChange={set('support_level')} style={IS}>
          {[['l1','L1 — Soporte básico'],['l2','L2 — Soporte técnico'],['l3','L3 — Experto / Desarrollo']].map(([v,l]) =>
            <option key={v} value={v}>{l}</option>)}
        </select>
      </div>
      <div><label style={LS}>{t('common.description')}</label><input value={form.description} onChange={set('description')} style={IS} /></div>
      <div style={{ display:'flex', justifyContent:'flex-end', gap:10 }}>
        <Button variant="secondary" onClick={onClose}>{t('common.cancel')}</Button>
        <Button onClick={() => onSave(form)} disabled={isPending || !form.name} loading={isPending}>{initial ? t('common.save') : t('service_desk.groups_new_title')}</Button>
      </div>
    </>
  )
}

// ── Templates Config ──────────────────────────────────────────────────────────
function TemplatesConfig() {
  const t = useAppT()
  const qc = useQueryClient()
  const toast = useToast()
  const [showNew, setShowNew] = useState(false)

  const { data: templates = [], isLoading } = useQuery({
    queryKey: ['sd-templates'],
    queryFn: () => api.get('/sd/ticket-templates').then(r => r.data),
  })
  const [editing, setEditing] = useState(null)
  const { mutate: create, isPending } = useMutation({
    mutationFn: d => api.post('/sd/ticket-templates', d),
    onSuccess: () => { qc.invalidateQueries({queryKey:['sd-templates']}); setShowNew(false); toast.success(t('service_desk.templates_created')) },

    onError: e => toast.error(extractErr(e, 'Error'))
  })
  const { mutate: update } = useMutation({
    mutationFn: ({id, ...d}) => api.patch(`/sd/ticket-templates/${id}`, d),
    onSuccess: () => { qc.invalidateQueries({queryKey:['sd-templates']}); setEditing(null); toast.success(t('service_desk.templates_updated')) },
    onError: e => toast.error(extractErr(e, 'Error')),
  })
  const { mutate: toggle } = useMutation({
    mutationFn: ({id, is_active}) => api.patch(`/sd/ticket-templates/${id}`, {is_active}),
    onSuccess: () => qc.invalidateQueries({queryKey:['sd-templates']}),
    onError: e => toast.error(extractErr(e, 'Error'))
  })
  const { mutate: remove } = useMutation({
    mutationFn: id => api.delete(`/sd/ticket-templates/${id}`),
    onSuccess: () => { qc.invalidateQueries({queryKey:['sd-templates']}); toast.success(t('service_desk.templates_deleted')) },
    onError: e => toast.error(extractErr(e, 'Error')),
  })

  const IS = { width:'100%', background:'var(--surface-3)', border:'1px solid var(--surface-4)',
    borderRadius:8, padding:'9px 13px', color:'var(--text-1)', fontSize:13,
    outline:'none', fontFamily:'inherit', boxSizing:'border-box' }
  const LS = { fontSize:11, fontWeight:600, color:'var(--text-2)', display:'block', marginBottom:5, textTransform:'uppercase', letterSpacing:'0.06em' }

  return (
    <div>
      <div style={{ display:'flex', justifyContent:'space-between', marginBottom:20 }}>
        <div style={{ fontSize:12, color:'var(--text-3)' }}>{t('service_desk.templates_hint')}</div>
        <Button onClick={() => setShowNew(true)}>+ {t('service_desk.templates_new_title')}</Button>
      </div>

      {isLoading ? <Spinner /> :
       templates.length === 0 ? <EmptyState icon="📝" title={t('service_desk.templates_empty')} description={t('service_desk.templates_empty_desc')} /> :
      <div style={{ display:'grid', gridTemplateColumns:'repeat(auto-fill, minmax(280px,1fr))', gap:12 }}>
        {templates.map(t => (
          <div key={t.id} style={{ background:'var(--surface-2)', border:'1px solid var(--surface-4)',
            borderRadius:12, padding:16, opacity: t.is_active ? 1 : 0.55 }}>
            <div style={{ display:'flex', justifyContent:'space-between', alignItems:'flex-start', marginBottom:10 }}>
              <div>
                <div style={{ fontSize:13, fontWeight:600, color:'var(--text-1)', marginBottom:4 }}>{t.name}</div>
                <span style={{ fontSize:11, background:'var(--surface-4)', color:'var(--text-2)', padding:'2px 8px', borderRadius:4 }}>
                  {t.ticket_type?.replace(/_/g,' ')}
                </span>
              </div>
              <div style={{ display:'flex', gap:6 }}>
                <button onClick={() => toggle({id:t.id, is_active:!t.is_active})}
                  style={{ background:'none', border:'1px solid var(--surface-4)', borderRadius:6, padding:'3px 8px',
                    fontSize:11, color: t.is_active ? COLOR.success : 'var(--text-3)', cursor:'pointer', fontFamily:'inherit' }}>
                  {t.is_active ? t('service_desk.templates_active') : t('service_desk.templates_inactive')}
                </button>
                <button onClick={() => setEditing(t)}
                  style={{ background:'none', border:'1px solid var(--surface-4)', borderRadius:6, padding:'3px 8px',
                    fontSize:11, color:'var(--accent)', cursor:'pointer', fontFamily:'inherit' }}>✏</button>
                <button onClick={() => { openConfirmGlobal({ message: '¿Eliminar esta plantilla?', onConfirm: () => remove(t.id), danger: true }) }}
                  style={{ background:'none', border:`1px solid ${COLOR.danger}30`, borderRadius:6, padding:'3px 8px',
                    fontSize:11, color:COLOR.danger, cursor:'pointer', fontFamily:'inherit' }}>🗑</button>
              </div>
            </div>
            {t.default_priority && <div style={{ fontSize:12, color:'var(--text-2)', marginBottom:6 }}>
              {t('service_desk.templates_priority')}: <PBadge v={t.default_priority} />
            </div>}
            {t.description_template && (
              <div style={{ fontSize:12, color:'var(--text-3)', borderTop:'1px solid var(--surface-4)', paddingTop:8, marginTop:8 }}>
                {t.description_template.slice(0, 80)}{t.description_template.length > 80 ? '…' : ''}
              </div>
            )}
          </div>
        ))}
      </div>}

      {showNew && (
        <Modal open title={t('service_desk.templates_new_title')} onClose={() => setShowNew(false)}>
          <NewTemplateForm IS={IS} LS={LS} onSave={create} isPending={isPending} onClose={() => setShowNew(false)} />
        </Modal>
      )}
      {editing && (
        <Modal open title={t('service_desk.templates_edit_title')} onClose={() => setEditing(null)}>
          <NewTemplateForm IS={IS} LS={LS} initial={editing}
            onSave={d => update({id: editing.id, ...d})}
            isPending={false} onClose={() => setEditing(null)} />
        </Modal>
      )}
    </div>
  )
}

function NewTemplateForm({ IS, LS, onSave, isPending, onClose, initial }) {
  const t = useAppT()
  const [form, setForm] = useState({
    name: initial?.name || '', ticket_type: initial?.ticket_type || 'service_request',
    default_priority: initial?.default_priority || 'p3_medium',
    description_template: initial?.description_template || '',
  })
  const set = k => e => setForm(f => ({...f, [k]: e.target.value}))
  return (
    <div style={{ display:'flex', flexDirection:'column', gap:14 }}>
      <div><label style={LS}>{t('common.name')} *</label><input value={form.name} onChange={set('name')} style={IS} /></div>
      <div style={{ display:'grid', gridTemplateColumns:'1fr 1fr', gap:10 }}>
        <div>
          <label style={LS}>{t('service_desk.svc_ticket_type')}</label>
          <select value={form.ticket_type} onChange={set('ticket_type')} style={IS}>
            {['incident','service_request','change','question','problem'].map(tk =>
              <option key={tk} value={tk}>{tk.replace(/_/g,' ')}</option>)}
          </select>
        </div>
        <div>
          <label style={LS}>{t('service_desk.templates_priority')}</label>
          <select value={form.default_priority} onChange={set('default_priority')} style={IS}>
            {['p1_critical','p2_high','p3_medium','p4_low'].map(p =>
              <option key={p} value={p}>{PRIORITY_LABEL[p]}</option>)}
          </select>
        </div>
      </div>
      <div>
        <label style={LS}>{t('service_desk.templates_hint')}</label>
        <textarea value={form.description_template} onChange={set('description_template')} rows={4}
          style={{...IS, resize:'vertical'}} placeholder="Texto de la plantilla de descripcion..." />
      </div>
      <div style={{ display:'flex', justifyContent:'flex-end', gap:10 }}>
        <Button variant="secondary" onClick={onClose}>{t('common.cancel')}</Button>
        <Button onClick={() => onSave(form)} disabled={isPending || !form.name} loading={isPending}>{initial ? t('common.save') : t('service_desk.templates_new_title')}</Button>
      </div>
    </div>
  )
}

// ── Config (wrapper con tabs) ─────────────────────────────────────────────────
function Config() {
  const t = useAppT()
  const [sub, setSub] = useState('catalog')
  const tabs = [
    {id:'catalog',  label:`${t('service_desk.tab_catalog')}`},
    {id:'sla',      label:`⏱ ${t('service_desk.tab_sla')}`},
    {id:'groups',   label:`${t('service_desk.tab_groups')}`},
    {id:'routing',  label:`${t('service_desk.tab_routing')}`},
    {id:'templates',label:`${t('service_desk.tab_templates')}`},
    {id:'canned',   label:`${t('service_desk.tab_canned')}`},
    {id:'announcements', label:`${t('service_desk.tab_announcements')}`},
  ]
  return (
    <div>
      <div style={{ display:'flex', gap:8, marginBottom:24, borderBottom:'1px solid var(--surface-4)', paddingBottom:16, flexWrap:'wrap', paddingLeft:12 }}>
        {tabs.map(t => (
          <button key={t.id} onClick={() => setSub(t.id)} style={{
            padding:'7px 16px', borderRadius:8,
            border:`1px solid ${sub===t.id ? 'var(--accent-glow)' : 'var(--surface-4)'}`,
            background: sub===t.id ? 'var(--accent-muted)' : 'transparent',
            color: sub===t.id ? 'var(--accent)' : 'var(--text-2)',
            fontSize:12, fontWeight:600, cursor:'pointer', fontFamily:'inherit',
          }}>{t.label}</button>
        ))}
      </div>
      {sub === 'catalog'   && <CatalogConfig />}
      {sub === 'sla'       && <SLAConfig />}
      {sub === 'groups'    && <GroupsConfig />}
      {sub === 'routing'   && <RoutingRules />}
      {sub === 'templates' && <TemplatesConfig />}
      {sub === 'canned'    && <CannedResponsesManager />}
      {sub === 'announcements' && <AnnouncementsConfig />}
    </div>
  )
}

// ── Ticket Detail Panel ───────────────────────────────────────────────────────
/** Thin wrapper so ServiceDesk can use DocumentsPanel without extra style overhead */
function DocumentsPanelSD({ ticketId }) {
  return (
    <div style={{ marginBottom: 20 }}>
      <DocumentsPanel ticketId={ticketId} />
    </div>
  )
}

function useWindowWidth() {
  const [width, setWidth] = useState(typeof window !== 'undefined' ? window.innerWidth : 1280)
  useEffect(() => {
    const handler = () => setWidth(window.innerWidth)
    window.addEventListener('resize', handler)
    return () => window.removeEventListener('resize', handler)
  }, [])
  return width
}

// ── Split Ticket Modal ────────────────────────────────────────────────────────
function SplitTicketModal({ ticket, onClose, onCreated }) {
  const t = useAppT()
  const toast = useToast()
  const [form, setForm] = useState({
    new_title: '',
    new_description: ticket?.description || '',
    keep_original_description: ticket?.description || '',
    tags: '',
  })

  const { mutate, isPending } = useMutation({
    mutationFn: (data) => api.post(`/sd/tickets/${ticket.id}/split`, data),
    onSuccess: (res) => {
      toast.success(`${t('service_desk.ticket_created_success')} ${res?.data?.child?.number || ''}`)
      onCreated?.(res?.data)
      onClose()
    },
    onError: (e) => toast.error(extractErr(e, t('common.error'))),
  })

  const IS = {
    width: '100%', background: 'var(--surface-3)', border: '1px solid var(--surface-4)',
    borderRadius: 8, padding: '9px 12px', color: 'var(--text-1)', fontSize: 13,
    outline: 'none', fontFamily: 'inherit', boxSizing: 'border-box',
  }
  const LS = {
    fontSize: 11, fontWeight: 600, color: 'var(--text-2)', display: 'block',
    marginBottom: 5, textTransform: 'uppercase', letterSpacing: '0.06em',
  }

  const handleSave = () => {
    if (!form.new_title.trim()) { toast.error(t('service_desk.zod_title_required')); return }
    mutate({
      new_title: form.new_title.trim(),
      new_description: form.new_description,
      keep_original_description: form.keep_original_description,
      tags: form.tags ? form.tags.split(',').map(t => t.trim()).filter(Boolean) : [],
    })
  }

  return (
    <Modal open title={`✂ Dividir ticket ${ticket?.number}`} onClose={onClose}>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
        <div style={{ padding: '10px 14px', background: 'var(--surface-1)', borderRadius: 8,
          border: '1px solid var(--surface-4)', fontSize: 12, color: 'var(--text-2)' }}>
          {t('service_desk.split_desc_original')} <strong style={{ color: 'var(--text-1)' }}>{ticket?.number}</strong>.
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 14 }}>
          <div>
            <label style={LS}>{t('service_desk.split_title_lbl')} *</label>
            <input value={form.new_title} onChange={e => setForm(f => ({ ...f, new_title: e.target.value }))}
              style={IS} autoFocus />
          </div>
          <div>
            <label style={LS}>{t('service_desk.split_tags_lbl')}</label>
            <input value={form.tags} onChange={e => setForm(f => ({ ...f, tags: e.target.value }))}
              style={IS} />
          </div>
        </div>

        <div>
          <label style={LS}>{t('service_desk.split_desc_child')}</label>
          <textarea value={form.new_description}
            onChange={e => setForm(f => ({ ...f, new_description: e.target.value }))}
            rows={4} style={{ ...IS, resize: 'vertical' }}
            placeholder="Descripcion del nuevo ticket hijo..." />
        </div>

        <div>
          <label style={LS}>{t('service_desk.split_desc_original')}</label>
          <textarea value={form.keep_original_description}
            onChange={e => setForm(f => ({ ...f, keep_original_description: e.target.value }))}
            rows={4} style={{ ...IS, resize: 'vertical' }} />
        </div>

        <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 10 }}>
          <Button variant="secondary" onClick={onClose}>{t('common.cancel')}</Button>
          <Button onClick={handleSave} disabled={isPending || !form.new_title.trim()} loading={isPending}>
            ✂ {t('service_desk.split_create_btn')}
          </Button>
        </div>
      </div>
    </Modal>
  )
}

function TicketDetail({ ticketId, onClose, embedded = false }) {
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
    queryFn: () => api.get(`/sd/tickets/${ticketId}`).then(r => r.data),
    enabled: !!ticketId,
    refetchInterval: 30000,
  })
  const { data: users = [] } = useQuery({
    queryKey: ['users'],
    queryFn: () => api.get('/users').then(r => r.data),
  })
  const { data: _slaEvents = [] } = useQuery({
    queryKey: ['sd-sla-events', ticketId],
    queryFn: () => api.get(`/sd/tickets/${ticketId}/sla/events`).then(r => r.data),
    enabled: !!ticketId,
  })
  const { data: links = [] } = useQuery({
    queryKey: ['sd-ticket-links', ticketId],
    queryFn: () => api.get(`/sd/tickets/${ticketId}/links`).then(r => r.data),
    enabled: !!ticketId,
  })

  const invalidate = () => {
    qc.invalidateQueries({ queryKey: ['sd-ticket', ticketId] })
    qc.invalidateQueries({ queryKey: ['sd-tickets'] })
  }

  const { mutate: addComment, isPending: commenting } = useMutation({
    mutationFn: () => api.post(`/sd/tickets/${ticketId}/comments`, { body: commentText, is_internal: false }),
    onSuccess: () => { invalidate(); setCommentText(''); toast.success(t('service_desk.comment_added')) },

    onError: e => toast.error(extractErr(e, 'Error'))
  })
  const { mutate: suggestReply, isPending: suggestingReply } = useMutation({
    mutationFn: () => api.post(`/sd/tickets/${ticketId}/ai-suggest`, { content: commentText }),
    onSuccess: (res) => {
      const draft = res?.data?.draft || ''
      if (!draft) {
        toast.error(t('common.error'))
        return
      }
      setCommentText(prev => (prev ? `${prev}\n\n${draft}` : draft))
      toast.success(t('service_desk.detail_ai_generating'))
    },
    onError: e => toast.error(extractErr(e, 'Error al sugerir respuesta IA')),
  })
  const { mutate: logTime, isPending: loggingTime } = useMutation({
    mutationFn: () => api.post(`/sd/tickets/${ticketId}/time-log`, { minutes: Number(timeMin) }),
    onSuccess: () => { invalidate(); setTimeMin(''); toast.success(`${timeMin} min`) },

    onError: e => toast.error(extractErr(e, 'Error'))
  })
  const { mutate: updateTicket } = useMutation({
    mutationFn: data => api.patch(`/sd/tickets/${ticketId}`, data),
    onSuccess: () => { invalidate(); toast.success(t('service_desk.ticket_updated')) },

    onError: e => toast.error(extractErr(e, 'Error'))
  })
  const { mutate: escalate } = useMutation({
    mutationFn: () => api.post(`/sd/tickets/${ticketId}/escalate?to_level=l2`, {}),
    onSuccess: () => { invalidate(); toast.success(t('service_desk.ticket_escalated')) },

    onError: e => toast.error(extractErr(e, 'Error'))
  })
  const { mutate: pauseSLA } = useMutation({
    mutationFn: () => api.post(`/sd/tickets/${ticketId}/sla/pause`, { note: 'Esperando respuesta del cliente' }),
    onSuccess: () => { invalidate(); qc.invalidateQueries({ queryKey: ['sd-sla-events'] }); toast.success(t('service_desk.sla_paused')) },

    onError: e => toast.error(extractErr(e, 'Error'))
  })
  const { mutate: resumeSLA } = useMutation({
    mutationFn: () => api.post(`/sd/tickets/${ticketId}/sla/resume`),
    onSuccess: () => { invalidate(); qc.invalidateQueries({ queryKey: ['sd-sla-events'] }); toast.success(t('service_desk.sla_resumed')) },

    onError: e => toast.error(extractErr(e, 'Error'))
  })

  if (!ticketId) return null

  const IS = { width:'100%', background:'var(--surface-3)', border:'1px solid var(--surface-4)',
    borderRadius:8, padding:'9px 12px', color:'var(--text-1)', fontSize:13,
    outline:'none', fontFamily:'inherit', boxSizing:'border-box' }

  const slaColor = ticket?.sla_resolution_status === 'breached' ? COLOR.danger :
                   ticket?.sla_resolution_status === 'at_risk'  ? COLOR.warning : COLOR.success

  return (
    <div style={embedded ? {
      height: 'calc(100vh - 210px)',
      minHeight: 520,
      background:'var(--surface-0)',
      border:'1px solid var(--surface-4)',
      borderRadius: 12,
      display:'flex',
      flexDirection:'column',
      overflow:'hidden',
    } : {
      position:'fixed', top:0, right:0, bottom:0, width:560,
      background:'var(--surface-0)', borderLeft:'1px solid var(--surface-4)',
      zIndex:200, display:'flex', flexDirection:'column', overflowY:'auto',
      boxShadow:'-8px 0 32px rgba(0,0,0,0.25)',
    }}>

      {/* Header */}
      <div style={{ padding:'16px 20px', borderBottom:'1px solid var(--surface-4)',
        background:'var(--surface-1)', position:'sticky', top:0, zIndex:10 }}>
        <div style={{ display:'flex', justifyContent:'space-between', alignItems:'flex-start' }}>
          <div>
            {isLoading ? <Spinner /> : <>
              <div style={{ display:'flex', alignItems:'center', gap:8, marginBottom:6 }}>
                <span style={{ fontSize:12, color:'var(--accent)', fontWeight:700 }}>{ticket?.number}</span>
                <span style={{ fontSize:11, color:'var(--text-3)' }}>{ticket?.type_label}</span>
                <PBadge v={ticket?.priority} />
                <SBadge v={ticket?.status} />
              </div>
              <div style={{ fontSize:15, fontWeight:600, color:'var(--text-1)', lineHeight:1.3 }}>{ticket?.title}</div>
            </>}
          </div>
          <div style={{ display:'flex', gap:6, alignItems:'center', flexShrink:0 }}>
            {ticket && (
              <button onClick={() => setShowEdit(true)}
                style={{ background:'var(--accent-muted)', border:'1px solid var(--accent-glow)',
                  borderRadius:6, padding:'4px 10px', color:'var(--accent)',
                  fontSize:12, cursor:'pointer', fontFamily:'inherit', fontWeight:600 }}>
                ✏ Editar
              </button>
            )}
            <button onClick={onClose} style={{ background:'none', border:'none',
              color:'var(--text-2)', fontSize:20, cursor:'pointer', padding:'0 4px', lineHeight:1 }}>×</button>
          </div>
        </div>

        {/* Quick actions */}
        {ticket && (
          <div style={{ display:'flex', gap:6, marginTop:12, flexWrap:'wrap' }}>
            {!['resolved','closed','cancelled'].includes(ticket.status) && <>
              <button onClick={() => updateTicket({ status:'in_progress' })}
                style={{ ...qaBtnStyle, background:`${COLOR.accent}20`, color:COLOR.accent }}>▶ {t('service_desk.ticket_status')}</button>
              <button onClick={() => updateTicket({ status:'resolved', resolution:'Resuelto' })}
                style={{ ...qaBtnStyle, background:`${COLOR.success}20`, color:COLOR.success }}>✓ {t('service_desk.ticket_status')}</button>
              <button onClick={() => escalate()}
                style={{ ...qaBtnStyle, background:`${COLOR.warning}20`, color:COLOR.warning }}>↑ {t('service_desk.ticket_escalated')}</button>
              {ticket.sla_paused_at
                ? <button onClick={() => resumeSLA()} style={{ ...qaBtnStyle }}>▶ {t('service_desk.sla_resumed')}</button>
                : <button onClick={() => pauseSLA()} style={{ ...qaBtnStyle }}>⏸ {t('service_desk.sla_paused')}</button>}
              <button onClick={() => setShowSplit(true)}
                style={{ ...qaBtnStyle }}>✂ {t('service_desk.split_title_lbl')}</button>
            </>}
            {ticket.status === 'resolved' && (
              <button onClick={() => updateTicket({ status:'closed' })}
                style={{ ...qaBtnStyle, background:`${COLOR.text2}20`, color:'var(--text-2)' }}>✕ Cerrar</button>
            )}
          </div>
        )}
      </div>

      {/* Body */}
      <div style={{ flex:1, padding:'20px', overflowY:'auto' }}>
        {isLoading ? <div style={{ padding:40, textAlign:'center' }}><Spinner /></div> : ticket && <>

          {/* SLA status */}
          <div style={{ background:'var(--surface-2)', border:`1px solid ${slaColor}40`,
            borderRadius:10, padding:'12px 16px', marginBottom:16, display:'grid',
            gridTemplateColumns:'1fr 1fr', gap:10 }}>
            <div>
              <div style={{ fontSize:10, color:'var(--text-3)', textTransform:'uppercase', marginBottom:2 }}>{t('service_desk.detail_sla_response')}</div>
              <div style={{ fontSize:12, fontWeight:600, color: ticket.sla_response_status === 'breached' ? COLOR.danger : COLOR.success }}>
                {ticket.sla_response_status?.replace(/_/g,' ')} · {fmtDate(ticket.sla_response_due)}
              </div>
            </div>
            <div>
              <div style={{ fontSize:10, color:'var(--text-3)', textTransform:'uppercase', marginBottom:2 }}>{t('service_desk.detail_sla_resolution')}</div>
              <div style={{ fontSize:12, fontWeight:600, color: slaColor }}>
                {ticket.sla_resolution_status?.replace(/_/g,' ')} · {fmtDate(ticket.sla_resolution_due)}
              </div>
            </div>
          </div>

          {/* Info grid */}
          <div style={{ display:'grid', gridTemplateColumns:'1fr 1fr', gap:10, marginBottom:16 }}>
            {[
              [t('service_desk.detail_requester'),  ticket.requester_name || '—'],
              [t('common.assigned_to'), ticket.assigned_to_name || t('service_desk.unassigned')],
              [t('service_desk.detail_group'),      ticket.assigned_group_name || '—'],
              [t('service_desk.detail_project'),    ticket.project_name || '—'],
              [t('service_desk.detail_ci'),         ticket.ci_name || '—'],
              [t('service_desk.detail_time_spent'), fmtMinutes(ticket.time_spent_minutes)],
              [t('service_desk.detail_created'),    fmtDate(ticket.created_at)],
              [t('service_desk.detail_updated'),    fmtDate(ticket.updated_at)],
            ].map(([label, val]) => (
              <div key={label} style={{ background:'var(--surface-2)', borderRadius:8, padding:'10px 12px' }}>
                <div style={{ fontSize:10, color:'var(--text-3)', textTransform:'uppercase', marginBottom:2 }}>{label}</div>
                <div style={{ fontSize:12, color:'var(--text-1)', fontWeight:500 }}>{val}</div>
              </div>
            ))}
          </div>

          {/* Asignar */}
          <div style={{ marginBottom:16 }}>
            <button onClick={() => setEditAssign(e => !e)}
              style={{ fontSize:12, color:'var(--accent)', background:'none', border:'none', cursor:'pointer', padding:0 }}>
              {editAssign ? '▼' : '▶'} Reasignar ticket
            </button>
            {editAssign && (
              <div style={{ display:'flex', gap:8, marginTop:8 }}>
                <select onChange={e => e.target.value && updateTicket({ assigned_to_user_id: e.target.value })}
                  style={{ ...IS, flex:1 }} defaultValue="">
                  <option value="" disabled>{t('service_desk.detail_select_agent')}</option>
                  {users.map(u => <option key={u.id} value={u.id}>{u.full_name}</option>)}
                </select>
              </div>
            )}
          </div>

          {/* Descripción */}
          <div style={{ marginBottom:20 }}>
            <div style={{ fontSize:11, fontWeight:700, color:'var(--text-3)', marginBottom:8, textTransform:'uppercase' }}>{t('common.description')}</div>
            <div style={{ fontSize:13, color:'var(--text-1)', lineHeight:1.6, whiteSpace:'pre-wrap',
              background:'var(--surface-2)', borderRadius:8, padding:'12px 14px' }}>
              {ticket.description}
            </div>
          </div>

          {/* Resolución si existe */}
          {ticket.resolution && (
            <div style={{ marginBottom:20 }}>
              <div style={{ fontSize:11, fontWeight:700, color:COLOR.success, marginBottom:8, textTransform:'uppercase' }}>{t('service_desk.edit_resolution')}</div>
              <div style={{ fontSize:13, color:'var(--text-1)', background:`${COLOR.success}08`,
                border:`1px solid ${COLOR.success}20`, borderRadius:8, padding:'12px 14px', lineHeight:1.5 }}>
                {ticket.resolution}
              </div>
            </div>
          )}

          {/* Tickets vinculados */}
          {links.length > 0 && (
            <div style={{ marginBottom:20 }}>
              <div style={{ fontSize:11, fontWeight:700, color:'var(--text-3)', marginBottom:8, textTransform:'uppercase' }}>
                {t('service_desk.detail_linked')} ({links.length})
              </div>
              {links.map(lk => (
                <div key={lk.link_id} style={{ display:'flex', alignItems:'center', gap:8, padding:'6px 0',
                  borderBottom:'1px solid var(--surface-4)', fontSize:12 }}>
                  <span style={{ color:'var(--text-3)', fontSize:10, textTransform:'uppercase', minWidth:70 }}>{lk.link_type}</span>
                  <span style={{ color:'var(--accent)', fontWeight:600 }}>{lk.ticket_number}</span>
                  <span style={{ color:'var(--text-1)', flex:1 }}>{lk.ticket_title}</span>
                  <SBadge v={lk.ticket_status} />
                </div>
              ))}
            </div>
          )}

          {/* Registrar tiempo */}
          <div style={{ marginBottom:20 }}>
            <div style={{ fontSize:11, fontWeight:700, color:'var(--text-3)', marginBottom:8, textTransform:'uppercase' }}>
              {t('service_desk.detail_log_time')}
            </div>
            <div style={{ display:'flex', gap:8 }}>
              <input type="number" placeholder="Minutos" value={timeMin}
                onChange={e => setTimeMin(e.target.value)} style={{ ...IS, flex:1 }} />
              <Button onClick={() => logTime()} disabled={loggingTime || !timeMin} loading={loggingTime}>
                {t('service_desk.detail_add_btn')}
              </Button>
            </div>
          </div>

          {/* Comentarios */}
          <div style={{ marginBottom:20 }}>
            <div style={{ fontSize:11, fontWeight:700, color:'var(--text-3)', marginBottom:12, textTransform:'uppercase' }}>
              {t('common.description')} ({(ticket.comments || []).length})
            </div>
            <div style={{ display:'flex', flexDirection:'column', gap:10, marginBottom:14 }}>
              {(ticket.comments || []).map(c => (
                <div key={c.id} style={{ background:'var(--surface-2)', borderRadius:10, padding:'12px 14px' }}>
                  <div style={{ display:'flex', justifyContent:'space-between', marginBottom:6 }}>
                    <span style={{ fontSize:12, fontWeight:600, color:'var(--text-1)' }}>{c.author_name}</span>
                    <span style={{ fontSize:11, color:'var(--text-3)' }}>{fmtDate(c.created_at)}</span>
                  </div>
                  <div style={{ fontSize:13, color:'var(--text-1)', lineHeight:1.5, whiteSpace:'pre-wrap' }}>{c.body}</div>
                </div>
              ))}
            </div>
            <div style={{ position:'relative' }}>
              {showCanned && (
                <CannedResponsePicker
                  onSelect={text => setCommentText(prev => prev ? prev + '\n\n' + text : text)}
                  onClose={() => setShowCanned(false)}
                />
              )}
              <textarea placeholder={t('service_desk.detail_send_comment')} value={commentText}
                onChange={e => setCommentText(e.target.value)} rows={3}
                style={{ ...IS, resize:'vertical', marginBottom:6 }} />
            </div>
            <div style={{ display:'flex', gap:8, marginBottom:8 }}>
              <button onClick={() => setShowCanned(s => !s)}
                style={{ fontSize:11, padding:'5px 10px', borderRadius:7,
                  background: showCanned ? 'var(--accent-muted)' : 'var(--surface-3)',
                  border: `1px solid ${showCanned ? '#00d4ff40' : 'var(--surface-4)'}`,
                  color: showCanned ? 'var(--accent)' : 'var(--text-2)',
                  cursor:'pointer', fontFamily:'inherit' }}>
                ⚡ Respuestas rápidas
              </button>
              <button onClick={() => suggestReply()} disabled={suggestingReply}
                style={{ fontSize:11, padding:'5px 10px', borderRadius:7,
                  background:'var(--surface-3)', border:'1px solid var(--surface-4)',
                  color:'var(--text-2)', cursor: suggestingReply ? 'wait' : 'pointer',
                  fontFamily:'inherit' }}>
                {suggestingReply ? t('service_desk.detail_ai_generating') : `✨ ${t('service_desk.detail_send_comment')}`}
              </button>
            </div>
            <Button onClick={() => addComment()} disabled={commenting || !commentText} loading={commenting} style={{ width:'100%' }}>
              {t('service_desk.detail_send_comment')}
            </Button>
          </div>

          {/* Attachments */}
          <DocumentsPanelSD ticketId={ticketId} />

          {/* Historial */}
          {(ticket.history || []).length > 0 && (            <div>
              <div style={{ fontSize:11, fontWeight:700, color:'var(--text-3)', marginBottom:10, textTransform:'uppercase' }}>
                {t('service_desk.detail_history')}
              </div>
              <div style={{ display:'flex', flexDirection:'column', gap:6 }}>
                {ticket.history.slice(-8).reverse().map((h, i) => (
                  <div key={i} style={{ fontSize:11, color:'var(--text-2)', padding:'5px 0',
                    borderBottom:'1px solid var(--surface-4)', display:'flex', justifyContent:'space-between' }}>
                    <span>{h.change_description || `${h.field_name}: ${h.old_value} → ${h.new_value}`}</span>
                    <span style={{ color:'var(--text-3)', whiteSpace:'nowrap', marginLeft:10 }}>{fmtDate(h.changed_at)}</span>
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

const qaBtnStyle = {
  padding:'5px 12px', borderRadius:6, border:'1px solid var(--surface-4)',
  background:'var(--surface-3)', color:'var(--text-2)',
  fontSize:11, fontWeight:600, cursor:'pointer', fontFamily:'inherit',
}

// ── Ticket Edit Modal — edición completa ─────────────────────────────────────
function TicketEditModal({ ticket, onClose, onSaved }) {
  const t = useAppT()
  const toast = useToast()
  const [form, setForm] = useState({
    title:       ticket.title       || '',
    description: ticket.description || '',
    priority:    ticket.priority    || 'p3_medium',
    ticket_type: ticket.ticket_type || 'incident',
    urgency:     ticket.urgency     || 'medium',
    impact:      ticket.impact      || 'user',
    status:      ticket.status      || 'new',
    resolution:  ticket.resolution  || '',
    tags:        ticket.tags        || '',
  })
  const { mutate, isPending } = useMutation({
    mutationFn: data => api.patch(`/sd/tickets/${ticket.id}`, data),
    onSuccess: onSaved,
    onError: e => toast.error(extractErr(e, 'Error al guardar')),
  })
  const set = k => e => setForm(f => ({ ...f, [k]: e.target.value }))
  const IS = { width:'100%', background:'var(--surface-3)', border:'1px solid var(--surface-4)',
    borderRadius:8, padding:'9px 12px', color:'var(--text-1)', fontSize:13,
    outline:'none', fontFamily:'inherit', boxSizing:'border-box' }
  const LS = { fontSize:11, fontWeight:600, color:'var(--text-2)', display:'block',
    marginBottom:5, textTransform:'uppercase', letterSpacing:'0.06em' }
  return (
    <Modal open title={`${t('common.edit')} ${ticket.number}`} onClose={onClose} size="lg">
      <div style={{ display:'grid', gridTemplateColumns:'1fr 1fr', gap:14,
        maxHeight:'75vh', overflowY:'auto', paddingRight:4 }}>
        <div style={{ gridColumn:'1/-1' }}>
          <label style={LS}>{t('service_desk.ticket_title')} *</label>
          <input value={form.title} onChange={set('title')} style={IS} />
        </div>
        <div>
          <label style={LS}>{t('service_desk.ticket_type')}</label>
          <select value={form.ticket_type} onChange={set('ticket_type')} style={IS}>
            {[['incident',`🔴 ${t('service_desk.type_incident')}`],['service_request',`🔵 ${t('service_desk.type_service_request')}`],
              ['change',`🟡 ${t('service_desk.type_change')}`],['problem',`🟠 ${t('service_desk.type_problem')}`],['question',`⚪ ${t('service_desk.type_question')}`],
            ].map(([v,l]) => <option key={v} value={v}>{l}</option>)}
          </select>
        </div>
        <div>
          <label style={LS}>{t('service_desk.ticket_priority')}</label>
          <select value={form.priority} onChange={set('priority')} style={IS}>
            {[['p1_critical',`🔴 ${t('service_desk.priority_p1')}`],['p2_high',`🟠 ${t('service_desk.priority_p2')}`],
              ['p3_medium',`🟡 ${t('service_desk.priority_p3')}`],['p4_low',`⚪ ${t('service_desk.priority_p4')}`],
            ].map(([v,l]) => <option key={v} value={v}>{l}</option>)}
          </select>
        </div>
        <div>
          <label style={LS}>{t('service_desk.edit_urgency')}</label>
          <select value={form.urgency} onChange={set('urgency')} style={IS}>
            {[['critical',t('service_desk.urgency_critical')],['high',t('service_desk.urgency_high')],['medium',t('service_desk.urgency_medium')],['low',t('service_desk.urgency_low')],
            ].map(([v,l]) => <option key={v} value={v}>{l}</option>)}
          </select>
        </div>
        <div>
          <label style={LS}>{t('service_desk.edit_impact')}</label>
          <select value={form.impact} onChange={set('impact')} style={IS}>
            {[['enterprise',t('service_desk.impact_enterprise')],['department',t('service_desk.impact_department')],
              ['user',t('service_desk.impact_user')],['minimal',t('service_desk.impact_minimal')],
            ].map(([v,l]) => <option key={v} value={v}>{l}</option>)}
          </select>
        </div>
        <div>
          <label style={LS}>{t('common.status')}</label>
          <select value={form.status} onChange={set('status')} style={IS}>
            {[['new',t('service_desk.status_new')],['assigned',t('service_desk.status_assigned')],['in_progress',t('service_desk.status_in_progress')],
              ['pending_client',t('service_desk.status_waiting_client')],['pending_third',t('service_desk.status_pending_change')],
              ['resolved',t('service_desk.status_resolved')],['closed',t('service_desk.status_closed')],['cancelled',t('service_desk.status_cancelled')],
            ].map(([v,l]) => <option key={v} value={v}>{l}</option>)}
          </select>
        </div>
        <div style={{ gridColumn:'1/-1' }}>
          <label style={LS}>{t('common.description')} *</label>
          <AIInlineEditor value={form.description} onChange={val => set('description')({ target: { value: val } })} rows={5} style={{ ...IS, resize:'vertical' }} />
        </div>
        {['resolved','closed'].includes(form.status) && (
          <div style={{ gridColumn:'1/-1' }}>
            <label style={LS}>{t('service_desk.edit_resolution')}</label>
            <textarea value={form.resolution} onChange={set('resolution')} rows={3}
              style={{ ...IS, resize:'vertical' }} />
          </div>
        )}
        <div style={{ gridColumn:'1/-1' }}>
          <label style={LS}>{t('service_desk.edit_tags')}</label>
          <input value={form.tags} onChange={set('tags')} style={IS} />
        </div>
        <div style={{ gridColumn:'1/-1', display:'flex', justifyContent:'flex-end', gap:10 }}>
          <Button variant="secondary" onClick={onClose}>{t('common.cancel')}</Button>
          <Button onClick={() => mutate(form)}
            disabled={isPending || !form.title.trim() || !form.description.trim()}
            loading={isPending}>
            {t('common.save')}
          </Button>
        </div>
      </div>
    </Modal>
  )
}

// ── Create Ticket Modal ───────────────────────────────────────────────────────
function CreateTicketModal({ onClose, onCreated }) {
  const t = useAppT()
  const idPrefix = useId()
  const qc = useQueryClient()
  const toast = useToast()
  const { data: catalog = [] } = useQuery({
    queryKey: ['sd-catalog'],
    queryFn: () => api.get('/sd/catalog').then(r => r.data),
  })
  const { data: users = [] } = useQuery({
    queryKey: ['users'],
    queryFn: () => api.get('/users').then(r => r.data),
  })
  const { data: clients = [] } = useQuery({
    queryKey: ['clients'],
    queryFn: () => api.get('/clients').then(r => r.data),
  })

  const [form, setForm] = useState({
    ticket_type: 'incident', title: '', description: '',
    priority: 'p3_medium', urgency: 'medium', impact: 'user',
    assigned_to_user_id: '', client_id: '', service_item_id: '',
  })
  const validation = useFormValidation(createTicketSchema)

  // Priority matrix auto-calc
  const suggestedPrio = useMemo(() => {
    const matrix = {
      critical_enterprise:'p1_critical', critical_department:'p1_critical', critical_user:'p2_high',
      high_enterprise:'p1_critical', high_department:'p2_high', high_user:'p2_high',
      medium_enterprise:'p2_high', medium_department:'p3_medium', medium_user:'p3_medium',
      low_enterprise:'p3_medium', low_department:'p4_low', low_user:'p4_low',
    }
    return matrix[`${form.urgency}_${form.impact}`] || 'p3_medium'
  }, [form.urgency, form.impact])

  const set = k => e => {
    setForm(f => ({...f, [k]: e.target.value}))
    validation.clearFieldError(k)
  }

  const buildTicketPayload = (raw) => {
    const payload = {
      ticket_type: raw.ticket_type,
      title: raw.title?.trim(),
      description: raw.description?.trim(),
      priority: raw.priority,
      urgency: raw.urgency,
      impact: raw.impact,
    }

    if (raw.assigned_to_user_id) payload.assigned_to_user_id = raw.assigned_to_user_id
    if (raw.client_id) payload.client_id = raw.client_id
    if (raw.service_item_id) payload.service_item_id = raw.service_item_id

    return payload
  }

  const { mutate, isPending } = useMutation({
    mutationFn: data => api.post('/sd/tickets', data),
    onSuccess: (res) => {
      validation.setErrors({})
      qc.invalidateQueries({ queryKey: ['sd-tickets'] })
      toast.success(`${t('service_desk.ticket_created_success')} ${res.data?.number || ''}`)
      onCreated?.(res.data)
      onClose()
    },

    onError: e => toast.error(extractErr(e, 'Error'))
  })

  const IS = { width:'100%', background:'var(--surface-3)', border:'1px solid var(--surface-4)',
    borderRadius:8, padding:'9px 13px', color:'var(--text-1)', fontSize:13,
    outline:'none', fontFamily:'inherit', boxSizing:'border-box' }
  const LS = { fontSize:11, fontWeight:600, color:'var(--text-2)', display:'block',
    marginBottom:5, textTransform:'uppercase', letterSpacing:'0.06em' }
  const submit = () => {
    const result = validation.validateForm(form)
    if (!result.success) return
    mutate(buildTicketPayload(result.data))
  }

  return (
    <Modal open title={t('service_desk.ticket_create_btn')} onClose={onClose} size="lg">
      <div style={{ display:'grid', gridTemplateColumns:'1fr 1fr', gap:16 }}>
        <div>
          <label htmlFor={`${idPrefix}-ticket-type`} style={LS}>{t('service_desk.ticket_type')} *</label>
          <select id={`${idPrefix}-ticket-type`} value={form.ticket_type} onChange={set('ticket_type')} style={validation.inputStyle(IS, 'ticket_type')}>
            {[['incident',t('service_desk.type_incident')],['service_request',t('service_desk.type_service_request')],['change',t('service_desk.type_change')],['problem',t('service_desk.type_problem')],['question',t('service_desk.type_question')]].map(([v,l]) =>
              <option key={v} value={v}>{l}</option>)}
          </select>
          {validation.errors.ticket_type && <div style={{ color:'var(--danger)', fontSize:11, marginTop:4 }}>{validation.errors.ticket_type}</div>}
        </div>
        <div>
          <label htmlFor={`${idPrefix}-service-item`} style={LS}>{t('service_desk.svc_ticket_type')}</label>
          <select id={`${idPrefix}-service-item`} value={form.service_item_id} onChange={set('service_item_id')} style={IS}>
            <option value="">{t('service_desk.ticket_no_service')}</option>
            {catalog.flatMap(cat => cat.services?.map(s => (
              <option key={s.id} value={s.id}>{cat.name} → {s.name}</option>
            )) || [])}
          </select>
        </div>
        <div style={{ gridColumn:'1/-1' }}>
          <label htmlFor={`${idPrefix}-title`} style={LS}>{t('service_desk.ticket_title')} *</label>
          <input id={`${idPrefix}-title`} value={form.title} onChange={set('title')} style={validation.inputStyle(IS, 'title')}
            placeholder="Titulo del ticket..." />
          {validation.errors.title && <div style={{ color:'var(--danger)', fontSize:11, marginTop:4 }}>{validation.errors.title}</div>}
        </div>
        <div style={{ gridColumn:'1/-1' }}>
          <label htmlFor={`${idPrefix}-description`} style={LS}>{t('common.description')} *</label>
          <AIInlineEditor inputId={`${idPrefix}-description`} ariaLabel={t('common.description')} value={form.description} onChange={val => set('description')({ target: { value: val } })} rows={4} style={{...validation.inputStyle(IS, 'description'), resize:'vertical'}} />
          {validation.errors.description && <div style={{ color:'var(--danger)', fontSize:11, marginTop:4 }}>{validation.errors.description}</div>}
        </div>

        {/* Priority matrix */}
        <div>
          <label htmlFor={`${idPrefix}-urgency`} style={LS}>{t('service_desk.edit_urgency')}</label>
          <select id={`${idPrefix}-urgency`} value={form.urgency} onChange={set('urgency')} style={validation.inputStyle(IS, 'urgency')}>
            {[['critical',t('service_desk.urgency_critical')],['high',t('service_desk.urgency_high')],['medium',t('service_desk.urgency_medium')],['low',t('service_desk.urgency_low')]].map(([v,l]) => <option key={v} value={v}>{l}</option>)}
          </select>
          {validation.errors.urgency && <div style={{ color:'var(--danger)', fontSize:11, marginTop:4 }}>{validation.errors.urgency}</div>}
        </div>
        <div>
          <label htmlFor={`${idPrefix}-impact`} style={LS}>{t('service_desk.edit_impact')}</label>
          <select id={`${idPrefix}-impact`} value={form.impact} onChange={set('impact')} style={validation.inputStyle(IS, 'impact')}>
            {[['enterprise',t('service_desk.impact_enterprise')],['department',t('service_desk.impact_department')],
              ['user',t('service_desk.impact_user')],['minimal',t('service_desk.impact_minimal')]
            ].map(([v,l]) => <option key={v} value={v}>{l}</option>)}
          </select>
          {validation.errors.impact && <div style={{ color:'var(--danger)', fontSize:11, marginTop:4 }}>{validation.errors.impact}</div>}
        </div>

        {/* Auto priority suggestion */}
        <div style={{ gridColumn:'1/-1', display:'flex', alignItems:'center', gap:12,
          background:'var(--surface-1)', borderRadius:8, padding:'10px 14px' }}>
          <span style={{ fontSize:12, color:'var(--text-3)' }}>{t('service_desk.ticket_auto_routing')}:</span>
          <PBadge v={suggestedPrio} />
          <button onClick={() => setForm(f => ({...f, priority: suggestedPrio}))}
            style={{ fontSize:11, color:'var(--accent)', background:'none', border:'none', cursor:'pointer' }}>
            {t('common.save')}
          </button>
          <select aria-label="Prioridad del ticket" value={form.priority} onChange={set('priority')} style={{...validation.inputStyle(IS, 'priority'), width:'auto', flex:1}}>
            {['p1_critical','p2_high','p3_medium','p4_low'].map(p =>
              <option key={p} value={p}>{PRIORITY_LABEL[p]}</option>)}
          </select>
        </div>

        <div>
          <label htmlFor={`${idPrefix}-assigned-to`} style={LS}>{t('common.assigned_to')}</label>
          <select id={`${idPrefix}-assigned-to`} value={form.assigned_to_user_id} onChange={set('assigned_to_user_id')} style={IS}>
            <option value="">{t('service_desk.ticket_auto_routing')}</option>
            {users.map(u => <option key={u.id} value={u.id}>{u.full_name}</option>)}
          </select>
        </div>
        <div>
          <label htmlFor={`${idPrefix}-client`} style={LS}>{t('service_desk.detail_requester')}</label>
          <select id={`${idPrefix}-client`} value={form.client_id} onChange={set('client_id')} style={IS}>
            <option value="">{t('service_desk.ticket_no_client')}</option>
            {(Array.isArray(clients) ? clients : clients?.items || []).map(c =>
              <option key={c.id} value={c.id}>{c.name}</option>)}
          </select>
        </div>

        <div style={{ gridColumn:'1/-1', display:'flex', justifyContent:'flex-end', gap:10, marginTop:8 }}>
          <Button variant="secondary" onClick={onClose}>{t('common.cancel')}</Button>
          <Button onClick={submit}
            disabled={isPending} loading={isPending}>
            {t('service_desk.ticket_create_btn')}
          </Button>
        </div>
      </div>
    </Modal>
  )
}

// ── Main Page ─────────────────────────────────────────────────────────────────
// ── Kanban de tickets ──────────────────────────────────────────────────────────

function KanbanTickets({ onSelect }) {
  const t = useAppT()
  const toast = useToast()
  const qc = useQueryClient()
  const [dragging, setDragging] = useState(null)

  const KANBAN_COLS = [
    { id: 'open',           label: t('service_desk.status_open'),           color: '#378ADD' },
    { id: 'in_progress',    label: t('service_desk.status_in_progress'),    color: '#7F77DD' },
    { id: 'waiting_client', label: t('service_desk.status_waiting_client'), color: '#BA7517' },
    { id: 'pending_change', label: t('service_desk.status_pending_change'), color: '#D85A30' },
    { id: 'resolved',       label: t('service_desk.status_resolved'),       color: '#1D9E75' },
  ]

  const { data: raw = {}, isLoading } = useQuery({
    queryKey: ['sd-tickets-kanban'],
    queryFn: () => api.get('/sd/tickets', { params: { page_size: 200 } })
      .then(r => {
        const tickets = Array.isArray(r.data) ? r.data : (r.data?.tickets || [])
        const cols = {}
        KANBAN_COLS.forEach(c => { cols[c.id] = [] })
        tickets.forEach(t => {
          const s = t.status
          if (cols[s]) cols[s].push(t)
          else cols['open'] = [...(cols['open'] || []), t]
        })
        return cols
      }),
    staleTime: 30000,
  })

  const { mutate: moveTicket } = useMutation({
    mutationFn: ({ id, status }) => api.patch(`/sd/tickets/${id}`, { status }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['sd-tickets-kanban'] }),
    onError: e => {
      const msg = e?.response?.data?.detail || 'Error al mover ticket'
      if (toast.error) toast.error(msg)
    },
  })

  const PRIO_COLOR = { p1_critical: '#E24B4A', p2_high: '#BA7517', p3_medium: '#378ADD', p4_low: '#1D9E75' }
  const PRIO_LABEL = { p1_critical: 'P1', p2_high: 'P2', p3_medium: 'P3', p4_low: 'P4' }

  const [dragOverCol, setDragOverCol] = useState(null)
  const onDragStart = (e, ticket, fromCol) => {
    setDragging({ ticket, fromCol })
    e.dataTransfer.effectAllowed = 'move'
    e.dataTransfer.setData('text/plain', String(ticket.id))
  }
  const onDragOver = (e) => { e.preventDefault(); e.dataTransfer.dropEffect = 'move' }
  const onDragEnter = (e, colId) => { e.preventDefault(); setDragOverCol(colId) }
  const onDragLeave = (e) => {
    if (!e.currentTarget.contains(e.relatedTarget)) setDragOverCol(null)
  }
  const onDrop = (e, toColId) => {
    e.preventDefault()
    setDragOverCol(null)
    if (!dragging || dragging.fromCol === toColId) { setDragging(null); return }
    moveTicket({ id: dragging.ticket.id, status: toColId })
    setDragging(null)
  }

  if (isLoading) return <div style={{ padding: 40, textAlign: 'center' }}><Spinner /></div>

  return (
    <div style={{ display: 'flex', gap: 12, overflowX: 'auto', paddingBottom: 16, minHeight: 400 }}>
      {KANBAN_COLS.map(col => {
        const tickets = raw[col.id] || []
        return (
          <div key={col.id}
            onDragOver={onDragOver}
            onDragEnter={e => onDragEnter(e, col.id)}
            onDragLeave={onDragLeave}
            onDrop={e => onDrop(e, col.id)}
            role="presentation"
            style={{ minWidth: 220, width: 220, flexShrink: 0,
              outline: dragOverCol === col.id ? `2px solid ${col.color}` : '2px solid transparent',
              borderRadius: 10, transition: 'outline .15s' }}>
            {/* Cabecera columna */}
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 10,
              padding: '8px 12px', background: `${col.color}18`,
              borderRadius: 8, border: `1px solid ${col.color}35` }}>
              <div style={{ width: 8, height: 8, borderRadius: '50%', background: col.color, flexShrink: 0 }} />
              <div style={{ fontSize: 12, fontWeight: 700, color: 'var(--text-1)', flex: 1 }}>{col.label}</div>
              <div style={{ fontSize: 11, color: col.color, fontWeight: 700, fontFamily: "'Space Mono', monospace" }}>{tickets.length}</div>
            </div>
            {/* Tarjetas */}
            <div style={{ display: 'flex', flexDirection: 'column', gap: 8, minHeight: 60 }}>
              {tickets.map(t => (
                <div key={t.id}
                  draggable
                  onDragStart={e => onDragStart(e, t, col.id)}
                  onClick={() => onSelect(t)}
                  role="button"
                  tabIndex={0}
                  onKeyDown={e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onSelect(t) } }}
                  style={{ padding: '10px 12px', background: 'var(--surface-2)',
                    border: '1px solid var(--surface-4)', borderRadius: 10,
                    cursor: 'grab', transition: 'border-color .15s, box-shadow .15s',
                    opacity: dragging?.ticket?.id === t.id ? 0.5 : 1 }}
                  onMouseEnter={e => { e.currentTarget.style.borderColor = col.color + '60'; e.currentTarget.style.boxShadow = `0 2px 8px ${col.color}20` }}
                  onMouseLeave={e => { e.currentTarget.style.borderColor = 'var(--surface-4)'; e.currentTarget.style.boxShadow = 'none' }}>
                  {/* Número + prioridad */}
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 5 }}>
                    <span style={{ fontSize: 10, color: 'var(--text-3)', fontFamily: "'Space Mono', monospace" }}>#{t.number}</span>
                    {t.priority && (
                      <span style={{ fontSize: 9, fontWeight: 700, padding: '1px 6px',
                        borderRadius: 4, background: `${PRIO_COLOR[t.priority] || '#888'}20`,
                        color: PRIO_COLOR[t.priority] || 'var(--text-2)' }}>
                        {PRIO_LABEL[t.priority] || t.priority}
                      </span>
                    )}
                  </div>
                  {/* Título */}
                  <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-1)',
                    lineHeight: 1.35, marginBottom: 6,
                    overflow: 'hidden', display: '-webkit-box',
                    WebkitLineClamp: 2, WebkitBoxOrient: 'vertical' }}>
                    {t.title}
                  </div>
                  {/* Footer */}
                  <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                    <span style={{ fontSize: 10, color: 'var(--text-3)', overflow: 'hidden',
                      textOverflow: 'ellipsis', whiteSpace: 'nowrap', maxWidth: 110 }}>
                      {t.requester_name || t.assigned_name || '—'}
                    </span>
                    {t.sla_resolution_status === 'breached' && (
                      <span style={{ fontSize: 9, color: 'var(--danger)', fontWeight: 700 }}>SLA ✗</span>
                    )}
                  </div>
                </div>
              ))}
              {tickets.length === 0 && (
                <div style={{ padding: '20px 0', textAlign: 'center', fontSize: 11,
                  color: 'var(--text-3)', border: '1px dashed var(--surface-4)', borderRadius: 8 }}>
                  {t('service_desk.kanban_no_tickets')}
                </div>
              )}
            </div>
          </div>
        )
      })}
    </div>
  )
}


// ── Canned Responses Picker ───────────────────────────────────────────────────
function CannedResponsePicker({ onSelect, onClose }) {
  const t = useAppT()
  const [search, setSearch] = useState('')
  const { data: responses = [] } = useQuery({
    queryKey: ['canned-responses', search],
    queryFn: () => api.get('/sd/canned-responses', { params: search ? { search } : {} }).then(r => r.data).catch(() => []),
    staleTime: 60000,
  })

  const cats = [...new Set(responses.map(r => r.category || 'General'))].sort()

  return (
    <div style={{ position: 'absolute', bottom: '100%', left: 0, right: 0, marginBottom: 4,
      background: 'var(--surface-1)', border: '1px solid var(--surface-4)', borderRadius: 10,
      boxShadow: '0 -4px 20px rgba(0,0,0,0.3)', zIndex: 100, maxHeight: 340, overflow: 'hidden',
      display: 'flex', flexDirection: 'column' }}>
      {/* Buscador */}
      <div style={{ padding: '10px 12px', borderBottom: '1px solid var(--surface-4)' }}>
        <input
          autoFocus
          value={search}
          onChange={e => setSearch(e.target.value)}
          placeholder={t('service_desk.canned_search')}
          style={{ width: '100%', background: 'var(--surface-3)', border: '1px solid var(--surface-4)',
            borderRadius: 6, padding: '7px 10px', color: 'var(--text-1)', fontSize: 13,
            outline: 'none', fontFamily: 'inherit', boxSizing: 'border-box' }}
        />
      </div>
      {/* Resultados */}
      <div style={{ overflowY: 'auto', flex: 1 }}>
        {responses.length === 0 ? (
          <div style={{ padding: '20px', textAlign: 'center', fontSize: 12, color: 'var(--text-3)' }}>
            {search ? t('service_desk.canned_no_results') : t('service_desk.canned_empty')}
          </div>
        ) : cats.map(cat => {
          const catItems = responses.filter(r => (r.category || 'General') === cat)
          if (!catItems.length) return null
          return (
            <div key={cat}>
              <div style={{ padding: '6px 12px 2px', fontSize: 10, fontWeight: 700, color: 'var(--text-3)',
                textTransform: 'uppercase', letterSpacing: '0.07em' }}>{cat}</div>
              {catItems.map(r => (
                <button key={r.id}
                  type="button"
                  onClick={() => { onSelect(r.body); onClose() }}
                  style={{ padding: '8px 12px', cursor: 'pointer', borderBottom: '1px solid var(--surface-4)', width:'100%', textAlign:'left', background:'transparent', fontFamily:'inherit', borderLeft:'none', borderRight:'none', borderTop:'none' }}
                  onMouseEnter={e => e.currentTarget.style.background = 'var(--surface-3)'}
                  onMouseLeave={e => e.currentTarget.style.background = 'transparent'}>
                  <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--text-1)', marginBottom: 2 }}>
                    {r.shortcut && <span style={{ fontSize: 11, color: 'var(--accent)', marginRight: 6,
                      fontFamily: 'monospace' }}>{r.shortcut}</span>}
                    {r.title}
                  </div>
                  <div style={{ fontSize: 11, color: 'var(--text-2)', overflow: 'hidden',
                    textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{r.body?.slice(0, 80)}</div>
                </button>
              ))}
            </div>
          )
        })}
      </div>
      <div style={{ padding: '6px 12px', borderTop: '1px solid var(--surface-4)', textAlign: 'right' }}>
        <button onClick={onClose} style={{ fontSize: 11, color: 'var(--text-3)', background: 'none',
          border: 'none', cursor: 'pointer', fontFamily: 'inherit' }}>{t('service_desk.canned_cancel_esc')}</button>
      </div>
    </div>
  )
}

// ── Canned Responses Manager (en Config) ─────────────────────────────────────
function CannedResponsesManager() {
  const t = useAppT()
  const qc = useQueryClient()
  const toast = useToast()
  const [form, setForm] = useState({ title: '', body: '', category: '', shortcut: '' })
  const [editing, setEditing] = useState(null)
  const [editForm, setEditForm] = useState({})

  const { data: responses = [], isLoading } = useQuery({
    queryKey: ['canned-responses-all'],
    queryFn: () => api.get('/sd/canned-responses').then(r => r.data).catch(() => []),
  })
  const IS = { width:'100%', background:'var(--surface-3)', border:'1px solid var(--surface-4)', borderRadius:8,
    padding:'8px 12px', color:'var(--text-1)', fontSize:13, outline:'none', fontFamily:'inherit',
    boxSizing:'border-box' }
  const LS = { fontSize:11, fontWeight:700, color:'var(--text-2)', textTransform:'uppercase',
    letterSpacing:'0.06em', display:'block', marginBottom:4 }

  const { mutate: create } = useMutation({
    mutationFn: d => api.post('/sd/canned-responses', d),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['canned-responses-all'] }); setForm({ title:'', body:'', category:'', shortcut:'' }) },
    onError: e => toast.error(e?.response?.data?.detail || 'Error'),
  })
  const { mutate: update } = useMutation({
    mutationFn: ({ id, data }) => api.patch(`/sd/canned-responses/${id}`, data),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['canned-responses-all'] }); setEditing(null) },
    onError: e => toast.error(e?.response?.data?.detail || 'Error'),
  })
  const { mutate: del } = useMutation({
    mutationFn: id => api.delete(`/sd/canned-responses/${id}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['canned-responses-all'] }),
    onError: e => toast.error(e?.response?.data?.detail || 'Error'),
  })

  return (
    <div>
      <div style={{ fontSize:13, color:'var(--text-2)', marginBottom:16 }}>
        Respuestas predefinidas reutilizables por los agentes al responder tickets.
      </div>

      {/* Lista de respuestas existentes */}
      {isLoading ? <div style={{textAlign:'center',padding:20}}><Spinner /></div> : (
        <div style={{ display:'flex', flexDirection:'column', gap:6, marginBottom:20 }}>
          {responses.map(r => editing === r.id ? (
            <div key={r.id} style={{ padding:'12px 14px', background:'var(--accent-muted)',
              border:'1px solid var(--accent-glow)', borderRadius:10 }}>
              <div style={{ display:'grid', gridTemplateColumns:'1fr 1fr', gap:8, marginBottom:8 }}>
          <div><label style={LS}>{t('common.name')} *</label>
            <input value={editForm.title||''} onChange={e=>setEditForm(f=>({...f,title:e.target.value}))} style={IS} /></div>
          <div><label style={LS}>{t('service_desk.routing_name_lbl')}</label>
            <input value={editForm.category||''} onChange={e=>setEditForm(f=>({...f,category:e.target.value}))} style={IS} /></div>
        </div>
        <div style={{marginBottom:8}}><label style={LS}>{t('service_desk.canned_shortcut')}</label>
          <input value={editForm.shortcut||''} onChange={e=>setEditForm(f=>({...f,shortcut:e.target.value}))} style={{...IS}} /></div>
        <div style={{marginBottom:10}}><label style={LS}>{t('service_desk.canned_body_lbl')} *</label>
                <textarea value={editForm.body||''} onChange={e=>setEditForm(f=>({...f,body:e.target.value}))} rows={4}
                  style={{...IS, resize:'vertical'}} /></div>
              <div style={{display:'flex',gap:8}}>
                <button onClick={() => update({ id:r.id, data:editForm })} disabled={!editForm.title||!editForm.body}
                  style={{background:'var(--accent)',border:'none',borderRadius:7,padding:'7px 16px',color:'#fff',cursor:'pointer',fontSize:12,fontFamily:'inherit'}}>
                  ✓ Guardar</button>
                <button onClick={() => setEditing(null)}
                  style={{background:'none',border:'1px solid var(--surface-4)',borderRadius:7,padding:'7px 12px',color:'var(--text-2)',cursor:'pointer',fontSize:12}}>
                  Cancelar</button>
              </div>
            </div>
          ) : (
            <div key={r.id} style={{ display:'flex', alignItems:'center', gap:12, padding:'10px 14px',
              background:'var(--surface-2)', border:'1px solid var(--surface-4)', borderRadius:10 }}>
              <div style={{ flex:1, minWidth:0 }}>
                <div style={{ fontSize:13, fontWeight:700 }}>{r.title}
                  {r.shortcut && <span style={{ fontSize:10, color:'var(--accent)', marginLeft:8,
                    fontFamily:'monospace', background:'var(--accent-muted)', padding:'1px 6px', borderRadius:4 }}>{r.shortcut}</span>}
                  {r.category && <span style={{ fontSize:10, color:'var(--text-3)', marginLeft:6 }}>{r.category}</span>}
                </div>
                <div style={{ fontSize:11, color:'var(--text-2)', marginTop:2, overflow:'hidden',
                  textOverflow:'ellipsis', whiteSpace:'nowrap' }}>{r.body?.slice(0,100)}</div>
              </div>
              <button onClick={() => { setEditing(r.id); setEditForm({title:r.title,body:r.body,category:r.category||'',shortcut:r.shortcut||''}) }}
                style={{background:'none',border:'1px solid var(--surface-4)',borderRadius:6,padding:'4px 10px',color:'var(--text-2)',cursor:'pointer',fontSize:12}}>✏</button>
              <button onClick={() => { openConfirmGlobal({ message: `¿Eliminar "${r.title}"?`, onConfirm: () => del(r.id), danger: true }) }}
                style={{background:'none',border:'1px solid #ff475730',borderRadius:6,padding:'4px 10px',color:'var(--danger)',cursor:'pointer',fontSize:12}}>🗑</button>
            </div>
          ))}
          {responses.length === 0 && !isLoading && (
            <div style={{fontSize:13,color:'var(--text-3)',textAlign:'center',padding:'20px 0'}}>{t('service_desk.canned_empty')}</div>
          )}
        </div>
      )}

      {/* Formulario nueva respuesta */}
      <div style={{ padding:'14px', background:'var(--accent-muted)', border:'1px dashed #00d4ff30', borderRadius:10 }}>
        <div style={{ fontSize:12, fontWeight:700, color:'var(--accent)', marginBottom:12 }}>{t('service_desk.canned_new_header')}</div>
        <div style={{ display:'grid', gridTemplateColumns:'1fr 1fr', gap:8, marginBottom:8 }}>
          <div><label style={LS}>{t('common.name')} *</label>
            <input value={form.title} onChange={e=>setForm(f=>({...f,title:e.target.value}))} style={IS} /></div>
          <div><label style={LS}>{t('service_desk.routing_name_lbl')}</label>
            <input value={form.category} onChange={e=>setForm(f=>({...f,category:e.target.value}))} style={IS} /></div>
        </div>
        <div style={{marginBottom:8}}><label style={LS}>{t('service_desk.canned_shortcut')}</label>
          <input value={form.shortcut} onChange={e=>setForm(f=>({...f,shortcut:e.target.value}))} style={IS} placeholder={t('service_desk.canned_shortcut')} /></div>
        <div style={{marginBottom:12}}><label style={LS}>{t('service_desk.canned_body_lbl')} *</label>
          <textarea value={form.body} onChange={e=>setForm(f=>({...f,body:e.target.value}))} rows={4}
            style={{...IS, resize:'vertical'}} placeholder="Texto de la respuesta enlatada..." /></div>
        <button onClick={() => create(form)} disabled={!form.title || !form.body}
          style={{background:'var(--accent)',border:'none',borderRadius:8,padding:'8px 18px',color:'#fff',cursor:'pointer',fontSize:13,fontFamily:'inherit',fontWeight:600}}>
          + {t('service_desk.canned_add_btn')}
        </button>
      </div>
    </div>
  )
}

// ── Announcements (admin) ─────────────────────────────────────────────────────
function AnnouncementsConfig() {
  const t = useAppT()
  const toast = useToast()
  const qc = useQueryClient()
  const [showCreate, setShowCreate] = useState(false)
  const [form, setForm] = useState({ title:'', body:'', type:'info', show_to_clients:true, starts_at:'', ends_at:'' })

  const IS = { background:'var(--surface-3)', border:'1px solid var(--surface-4)', borderRadius:7, padding:'7px 11px', color:'var(--text-1)', fontSize:12, outline:'none', fontFamily:'inherit', width:'100%', boxSizing:'border-box' }
  const LS = { fontSize:11, fontWeight:700, color:'var(--text-2)', textTransform:'uppercase', letterSpacing:'0.06em', display:'block', marginBottom:4 }
  const TYPE_COLOR = { info:'var(--accent)', warning:'var(--warning)', outage:'var(--danger)', maintenance:'#a855f7' }

  const { data: anns = [], isLoading } = useQuery({
    queryKey: ['sd-announcements'],
    queryFn: () => api.get('/sd/announcements').then(r => r.data),
  })
  const { mutate: create, isPending: creating } = useMutation({
    mutationFn: d => api.post('/sd/announcements', d),
    onSuccess: () => { qc.invalidateQueries(['sd-announcements']); setShowCreate(false); setForm({ title:'', body:'', type:'info', show_to_clients:true, starts_at:'', ends_at:'' }); toast.success(t('service_desk.ann_published')) },
    onError: e => toast.error(extractErr(e, 'Error')),
  })
  const { mutate: del } = useMutation({
    mutationFn: id => api.delete(`/sd/announcements/${id}`),
    onSuccess: () => { qc.invalidateQueries(['sd-announcements']); toast.success(t('service_desk.ann_deactivated')) },
    onError: e => toast.error(extractErr(e, 'Error')),
  })

  return (
    <div>
      <div style={{ display:'flex', justifyContent:'flex-end', marginBottom:14 }}>
        <Button size="sm" onClick={() => setShowCreate(true)}>{t('service_desk.ann_new_btn')}</Button>
      </div>
      {isLoading ? <div style={{ textAlign:'center', padding:30 }}><Spinner /></div>
        : anns.length === 0
          ? <EmptyState icon="📢" title={t('service_desk.ann_empty')} description={t('service_desk.ann_empty_desc')} />
          : (
            <div style={{ display:'flex', flexDirection:'column', gap:10 }}>
              {anns.map(a => (
                <div key={a.id} style={{ display:'flex', gap:14, padding:'12px 16px', background:'var(--surface-2)', border:`1px solid ${(TYPE_COLOR[a.type]||'var(--accent)')}30`, borderRadius:10, alignItems:'flex-start' }}>
                  <div style={{ width:4, alignSelf:'stretch', borderRadius:4, background:TYPE_COLOR[a.type]||'var(--accent)', flexShrink:0 }} />
                  <div style={{ flex:1 }}>
                    <div style={{ fontSize:13, fontWeight:700, marginBottom:4 }}>{a.title}
                      <span style={{ fontSize:10, padding:'2px 7px', marginLeft:8, borderRadius:20, background:(TYPE_COLOR[a.type]||'var(--accent)')+'20', color:TYPE_COLOR[a.type]||'var(--accent)', fontWeight:700, textTransform:'uppercase' }}>{a.type}</span>
                      {a.show_to_clients && <span style={{ fontSize:10, marginLeft:6, color:'var(--text-3)' }}>👁 {t('service_desk.ann_visible_clients')}</span>}
                    </div>
                    <div style={{ fontSize:12, color:'var(--text-2)', lineHeight:1.5 }}>{a.body}</div>
                    {(a.starts_at||a.ends_at) && (
                      <div style={{ fontSize:11, color:'var(--text-3)', marginTop:6 }}>
                        {a.starts_at && `${t('service_desk.ann_starts')}: ${new Date(a.starts_at).toLocaleString()}`}
                        {a.ends_at && ` · ${t('service_desk.ann_ends')}: ${new Date(a.ends_at).toLocaleString()}`}
                      </div>
                    )}
                  </div>
                  <button onClick={() => { openConfirmGlobal({ message: '¿Desactivar este anuncio?', onConfirm: () => del(a.id) }) }}
                    style={{ background:'none', border:'1px solid #ff475730', borderRadius:6, padding:'4px 10px', color:'var(--danger)', cursor:'pointer', fontSize:11 }}>🗑</button>
                </div>
              ))}
            </div>
          )
      }
      {showCreate && (
        <Modal open title="Nuevo comunicado" onClose={() => setShowCreate(false)} width={500}>
          <div style={{ display:'grid', gridTemplateColumns:'1fr 1fr', gap:12, marginBottom:14 }}>
            <div style={{ gridColumn:'1/-1' }}><label style={LS}>{t('service_desk.ticket_title')} *</label><input value={form.title} onChange={e=>setForm(f=>({...f,title:e.target.value}))} style={IS} /></div>
            <div><label style={LS}>{t('common.status')}</label>
              <select value={form.type} onChange={e=>setForm(f=>({...f,type:e.target.value}))} style={IS}>
                {['info','warning','outage','maintenance'].map(t=><option key={t} value={t}>{t}</option>)}
              </select>
            </div>
            <div style={{ display:'flex', alignItems:'center', gap:8, paddingTop:18 }}>
              <input type="checkbox" id="showCl" checked={form.show_to_clients} onChange={e=>setForm(f=>({...f,show_to_clients:e.target.checked}))} />
              <label htmlFor="showCl" style={{ fontSize:12, color:'var(--text-1)', cursor:'pointer' }}>{t('service_desk.ann_visible_clients')}</label>
            </div>
            <div><label style={LS}>{t('service_desk.ann_starts')}</label><input type="datetime-local" value={form.starts_at} onChange={e=>setForm(f=>({...f,starts_at:e.target.value}))} style={IS} /></div>
            <div><label style={LS}>{t('service_desk.ann_ends')}</label><input type="datetime-local" value={form.ends_at} onChange={e=>setForm(f=>({...f,ends_at:e.target.value}))} style={IS} /></div>
            <div style={{ gridColumn:'1/-1' }}><label style={LS}>{t('service_desk.ann_message')} *</label><textarea value={form.body} onChange={e=>setForm(f=>({...f,body:e.target.value}))} rows={4} style={{ ...IS, resize:'vertical' }} /></div>
          </div>
          <div style={{ display:'flex', gap:8, justifyContent:'flex-end' }}>
            <button onClick={()=>setShowCreate(false)} style={{ background:'transparent', border:'1px solid var(--surface-4)', borderRadius:8, padding:'7px 16px', color:'var(--text-2)', cursor:'pointer', fontSize:12 }}>{t('common.cancel')}</button>
            <Button onClick={()=>create(form)} loading={creating} disabled={!form.title||!form.body||creating}>{t('service_desk.ann_published')}</Button>
          </div>
        </Modal>
      )}
    </div>
  )
}

export default function ServiceDeskPage() {
  const t = useAppT()
  const [tab, setTab] = useState('queue')
  const [selId, setSelId] = useState(null)
  const [showCreate, setShowCreate] = useState(false)
  const [mobileView, setMobileView] = useState('list') // 'list' | 'detail'
  const windowWidth = useWindowWidth()
  const isMobile = windowWidth < 768
  const splitMode = selId && (tab === 'queue' || tab === 'all' || tab === 'kanban')

  // Auto-switch to detail view when a ticket is selected on mobile
  useEffect(() => {
    if (isMobile && selId) setMobileView('detail')
  }, [selId, isMobile])

  // Reset mobile view when switching tabs
  useEffect(() => {
    setMobileView('list')
    setSelId(null)
  }, [tab])

  const TABS = [
    { id: 'queue',    label: `${t('service_desk.tab_queue')}` },
    { id: 'all',      label: `${t('service_desk.tab_all')}` },
    { id: 'kanban',   label: `${t('service_desk.tab_kanban')}` },
    { id: 'changes',  label: `${t('service_desk.tab_changes')}` },
    { id: 'mi',       label: `${t('service_desk.tab_mi')}` },
    { id: 'problems', label: `${t('service_desk.tab_problems')}` },
    { id: 'kedb',     label: `${t('service_desk.tab_kedb')}` },
    { id: 'kb',       label: `${t('service_desk.tab_kb')}` },
    { id: 'cmdb',     label: `${t('service_desk.tab_cmdb')}` },
    { id: 'metrics',  label: `${t('service_desk.tab_metrics')}` },
    { id: 'config',   label: `${t('service_desk.tab_config')}` },
  ]

  return (
    <div className="p-4 sm:p-5 lg:px-7 lg:py-5" style={{ minHeight: '100%' }}>
      <PageHeader
        icon={<MessageSquare size={18} />}
        title={t('service_desk.title')}
        subtitle={t('service_desk.subtitle')}
        actions={
          <Button onClick={() => setShowCreate(true)}>+ {t('service_desk.ticket_create_btn')}</Button>
        }/>

      {/* Tab bar */}
      <div role="tablist" aria-label={t('service_desk.tab_config')} style={{ display: 'flex', gap: 6, marginBottom: 28, flexWrap: 'wrap',
        borderBottom: '1px solid var(--surface-4)', paddingBottom: 16 }}>
        {TABS.map((t, i) => (
          <button key={t.id} role="tab" aria-selected={tab===t.id} aria-controls={`sd-panel-${t.id}`} id={`sd-tab-${t.id}`} onClick={() => setTab(t.id)} style={{
            padding: '7px 16px', borderRadius: 8,
            border: `1px solid ${tab===t.id ? 'var(--accent-glow)' : 'var(--surface-4)'}`,
            background: tab===t.id ? 'var(--accent-muted)' : 'transparent',
            color: tab===t.id ? 'var(--accent)' : 'var(--text-2)',
            fontSize: 12, fontWeight: 600, cursor: 'pointer', fontFamily: 'inherit',
            whiteSpace: 'nowrap',
            marginLeft: i === 0 ? 12 : undefined,
          }}>{t.label}</button>
        ))}
      </div>

      {/* Mobile toggle bar when in split mode */}
      {isMobile && splitMode && (
        <div style={{ display: 'flex', gap: 8, marginBottom: 12 }}>
          <button onClick={() => setMobileView('list')}
            aria-pressed={mobileView === 'list'}
            style={{ flex: 1, padding: '8px 0', borderRadius: 8, fontFamily: 'inherit', fontSize: 12,
              fontWeight: 600, cursor: 'pointer',
              border: `1px solid ${mobileView === 'list' ? 'var(--accent-glow)' : 'var(--surface-4)'}`,
              background: mobileView === 'list' ? 'var(--accent-muted)' : 'var(--surface-2)',
              color: mobileView === 'list' ? 'var(--accent)' : 'var(--text-2)' }}>
            ← {t('service_desk.tab_all')}
          </button>
          <button onClick={() => setMobileView('detail')}
            aria-pressed={mobileView === 'detail'}
            style={{ flex: 1, padding: '8px 0', borderRadius: 8, fontFamily: 'inherit', fontSize: 12,
              fontWeight: 600, cursor: 'pointer',
              border: `1px solid ${mobileView === 'detail' ? 'var(--accent-glow)' : 'var(--surface-4)'}`,
              background: mobileView === 'detail' ? 'var(--accent-muted)' : 'var(--surface-2)',
              color: mobileView === 'detail' ? 'var(--accent)' : 'var(--text-2)' }}>
            {t('service_desk.tab_all')} →
          </button>
        </div>
      )}

      {/* Content */}
      <div className="min-w-0" style={!isMobile && splitMode ? {
        display: 'grid',
        gridTemplateColumns: 'minmax(360px, 1fr) minmax(380px, 1fr)',
        gap: 16,
        alignItems: 'start',
      } : undefined}>
        {/* List panel — hidden on mobile when viewing detail */}
        {(!isMobile || !splitMode || mobileView === 'list') && (
          <div>
            {tab === 'queue'    && <div id="sd-panel-queue" role="tabpanel" aria-labelledby="sd-tab-queue"><TicketList queueOnly={true}  onSelect={t => setSelId(t.id)} /></div>}
            {tab === 'all'      && <div id="sd-panel-all" role="tabpanel" aria-labelledby="sd-tab-all"><TicketList queueOnly={false} onSelect={t => setSelId(t.id)} /></div>}
            {tab === 'kanban'   && <div id="sd-panel-kanban" role="tabpanel" aria-labelledby="sd-tab-kanban"><KanbanTickets onSelect={t => setSelId(t.id)} /></div>}
            {tab === 'changes'  && (
              <div id="sd-panel-changes" role="tabpanel" aria-labelledby="sd-tab-changes"><Suspense fallback={<div style={{ padding: 40, textAlign: 'center' }}><Spinner /></div>}>
                <LazyChangeManagementTab />
              </Suspense></div>
            )}
            {tab === 'mi'       && <div id="sd-panel-mi" role="tabpanel" aria-labelledby="sd-tab-mi"><MajorIncidents /></div>}
            {tab === 'problems' && (
              <div id="sd-panel-problems" role="tabpanel" aria-labelledby="sd-tab-problems"><Suspense fallback={<div style={{ padding: 40, textAlign: 'center' }}><Spinner /></div>}>
                <LazyITSMKnowledgeTab mode="problems" />
              </Suspense></div>
            )}
            {tab === 'kedb'     && (
              <div id="sd-panel-kedb" role="tabpanel" aria-labelledby="sd-tab-kedb"><Suspense fallback={<div style={{ padding: 40, textAlign: 'center' }}><Spinner /></div>}>
                <LazyITSMKnowledgeTab mode="kedb" />
              </Suspense></div>
            )}
            {tab === 'kb'       && (
              <div id="sd-panel-kb" role="tabpanel" aria-labelledby="sd-tab-kb"><Suspense fallback={<div style={{ padding: 40, textAlign: 'center' }}><Spinner /></div>}>
                <LazyITSMKnowledgeTab mode="kb" />
              </Suspense></div>
            )}
            {tab === 'cmdb'     && (
              <div id="sd-panel-cmdb" role="tabpanel" aria-labelledby="sd-tab-cmdb"><Suspense fallback={<div style={{ padding: 40, textAlign: 'center' }}><Spinner /></div>}>
                <LazyCMDBTab />
              </Suspense></div>
            )}
            {tab === 'metrics'  && (
              <div id="sd-panel-metrics" role="tabpanel" aria-labelledby="sd-tab-metrics"><Suspense fallback={<div style={{ padding: 40, textAlign: 'center' }}><Spinner /></div>}>
                <LazyMetricsDashboard />
              </Suspense></div>
            )}
            {tab === 'config'   && <div id="sd-panel-config" role="tabpanel" aria-labelledby="sd-tab-config"><Config /></div>}
          </div>
        )}
        {/* Detail panel — inline on desktop split, full-width on mobile */}
        {splitMode && (!isMobile || mobileView === 'detail') && (
          <div>
            {isMobile && (
              <button onClick={() => setMobileView('list')}
                style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 12,
                  background: 'none', border: 'none', cursor: 'pointer', color: 'var(--accent)',
                  fontSize: 13, fontWeight: 600, fontFamily: 'inherit', padding: 0 }}>
                ← Volver a la lista
              </button>
            )}
            <TicketDetail ticketId={selId} onClose={() => { setSelId(null); setMobileView('list') }} embedded={true} />
          </div>
        )}
      </div>

      {/* Create ticket modal */}
      {showCreate && (
        <CreateTicketModal
          onClose={() => setShowCreate(false)}
          onCreated={t => t?.id && setSelId(t.id)}
        />
      )}
    </div>
  )
}
