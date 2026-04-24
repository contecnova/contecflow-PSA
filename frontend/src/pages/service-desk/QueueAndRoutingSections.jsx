import { useMemo, useState, useId } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useToast } from '../../context/ToastContext'
import api from '../../services/api'
import { Button, Spinner, EmptyState, Modal, useSort, SortableTH } from '../../components/ui'
import { COLOR } from '../../constants/theme'
import { useAppT } from '../../i18n/AppLangContext'
import { extractErr } from '../../utils/helpers'

const PRIORITY_COLOR = {
  p1_critical: COLOR.danger,
  p2_high: '#fb923c',
  p3_medium: COLOR.warning,
  p4_low: COLOR.text2,
}

const PRIORITY_LABEL = {
  p1_critical: 'P1 Crítico',
  p2_high: 'P2 Alto',
  p3_medium: 'P3 Medio',
  p4_low: 'P4 Bajo',
}

const STATUS_COLOR = {
  new: COLOR.accent,
  assigned: COLOR.accent,
  in_progress: '#38bdf8',
  pending_client: COLOR.warning,
  pending_third: COLOR.warning,
  resolved: COLOR.success,
  closed: COLOR.text2,
  cancelled: COLOR.text3,
}

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

function TRow({ t: ticket, onClick }) {
  const tr = useAppT()
  const now = new Date()
  const due = ticket.sla_resolution_due ? new Date(ticket.sla_resolution_due) : null
  const overdue = due && due < now && !['resolved', 'closed'].includes(ticket.status)
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

export function TicketList({ queueOnly, onSelect }) {
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
          {['p1_critical', 'p2_high', 'p3_medium', 'p4_low'].map(p =>
            <option key={p} value={p}>{PRIORITY_LABEL[p]}</option>)}
        </select>
        <select aria-label={t('service_desk.filter_all_statuses')} value={filterStatus} onChange={e => setFilterStatus(e.target.value)} style={IS}>
          <option value="">{t('service_desk.filter_all_statuses')}</option>
          {['new', 'assigned', 'in_progress', 'pending_client', 'resolved', 'closed'].map(s =>
            <option key={s} value={s}>{s.replace(/_/g, ' ')}</option>)}
        </select>
        <select aria-label={t('service_desk.filter_all_types')} value={filterType} onChange={e => setFilterType(e.target.value)} style={IS}>
          <option value="">{t('service_desk.filter_all_types')}</option>
          {['incident', 'service_request', 'change', 'problem', 'question'].map(tk =>
            <option key={tk} value={tk}>{tk.replace(/_/g, ' ')}</option>)}
        </select>
      </div>

      {isLoading ? <div style={{ textAlign: 'center', padding: 40 }}><Spinner /></div> :
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

export function MajorIncidents() {
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
    onError: e => toast.error(extractErr(e, 'Error')),
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

export function RoutingRules() {
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
    onError: e => toast.error(extractErr(e, 'Error')),
  })
  const { mutate: deleteRule } = useMutation({
    mutationFn: id => api.delete(`/sd/routing-rules/${id}`),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['sd-routing-rules'] }); toast.success(t('service_desk.routing_rule_deleted')) },
    onError: e => toast.error(extractErr(e, 'Error')),
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
          try { conds = JSON.parse(rule.conditions || '{}'); acts = JSON.parse(rule.actions || '{}') } catch { /* noop */ }
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
                  {Object.entries(conds).map(([k, v]) => (
                    <span key={k} style={{ background: 'var(--surface-4)', borderRadius: 4,
                      padding: '2px 8px', marginRight: 6, color: 'var(--text-2)' }}>
                      {k}: {Array.isArray(v) ? v.join(', ') : v}
                    </span>
                  ))}
                </div>
                <div>
                  <span style={{ color: 'var(--text-3)', marginRight: 6 }}>THEN</span>
                  {Object.entries(acts).map(([k, v]) => (
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
  const [conditions, setConditions] = useState(isEdit ? parseEntries(rule.conditions) : [])
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
    { key: 'ticket_type', label: t('service_desk.ticket_type') },
    { key: 'priority', label: t('service_desk.ticket_priority') },
    { key: 'keyword_in_title', label: t('service_desk.ticket_title') },
    { key: 'requester_domain', label: 'Domain' },
    { key: 'tag_contains', label: 'Tag' },
    { key: 'time_of_day', label: 'Time (HH:MM-HH:MM)' },
    { key: 'day_of_week', label: 'Day of week' },
    { key: 'sla_policy_id', label: 'SLA Policy' },
  ]
  const ACT_TYPES = [
    { key: 'assign_group', label: t('service_desk.act_label') },
    { key: 'assign_user', label: t('service_desk.act_no_agent') },
    { key: 'set_support_level', label: t('service_desk.groups_support_level') },
    { key: 'set_priority', label: t('service_desk.ticket_priority') },
  ]

  const usedCondKeys = conditions.map(c => c.key)
  const availCondTypes = COND_TYPES.filter(type => !usedCondKeys.includes(type.key))

  const addCondition = () => {
    const next = availCondTypes[0]
    if (next) setConditions(prev => [...prev, { key: next.key, value: '' }])
  }
  const removeCondition = i => setConditions(prev => prev.filter((_, idx) => idx !== i))
  const updateCond = (i, patch) => setConditions(prev => prev.map((c, idx) => idx === i ? { ...c, ...patch } : c))

  const addAction = () => {
    const usedActKeys = actions.map(a => a.key)
    const next = ACT_TYPES.find(type => !usedActKeys.includes(type.key))
    if (next) setActions(prev => [...prev, { key: next.key, value: '' }])
  }
  const removeAction = i => setActions(prev => prev.filter((_, idx) => idx !== i))
  const updateAct = (i, patch) => setActions(prev => prev.map((a, idx) => idx === i ? { ...a, ...patch } : a))

  const renderCondValue = (cond, i) => {
    const upd = v => updateCond(i, { value: v })
    if (cond.key === 'ticket_type') return (
      <select value={cond.value} onChange={e => upd(e.target.value)} style={IS}>
        <option value="">{t('service_desk.cond_any_type')}</option>
        {[['incident', 'Incidencia'], ['service_request', 'Solicitud'], ['change', 'Cambio'], ['problem', 'Problema']].map(([v, l]) =>
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
      const DAYS = [['monday', 'Lun'], ['tuesday', 'Mar'], ['wednesday', 'Mié'], ['thursday', 'Jue'], ['friday', 'Vie'], ['saturday', 'Sáb'], ['sunday', 'Dom']]
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
          cond.key === 'requester_domain' ? 'acme.com, acorp.es...' :
          cond.key === 'tag_contains' ? 'backend, producción...' :
          cond.key === 'time_of_day' ? '08:00-17:00' : ''
        }
      />
    )
  }

  const renderActValue = (act, i) => {
    const upd = v => updateAct(i, { value: v })
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
        {[['l1', 'L1 — Básico'], ['l2', 'L2 — Técnico'], ['l3', 'L3 — Experto']].map(([v, l]) => <option key={v} value={v}>{l}</option>)}
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
                  {COND_TYPES.filter(type => type.key === cond.key || !usedCondKeys.filter((_, idx) => idx !== i).includes(type.key)).map(type =>
                    <option key={type.key} value={type.key}>{type.label}</option>
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
                  {ACT_TYPES.filter(type => type.key === act.key || !actions.filter((_, idx) => idx !== i).map(a => a.key).includes(type.key)).map(type =>
                    <option key={type.key} value={type.key}>{type.label}</option>
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
