import { useEffect, useMemo, useState, useId } from 'react'
import type { CSSProperties } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useToast } from '../../context/ToastContext'
import { sdRoutingApi, sdGroupsApi, sdSlaPoliciesApi, usersApi, ticketsApi } from '../../services/api'
import { Button, Spinner, EmptyState, Modal, useSort, SortableTH, ariaSort } from '../../components/ui'
import Pagination from '../../components/ui/Pagination'
import { COLOR, alpha } from '../../constants/theme'
import { useAppT } from '../../i18n/AppLangContext'
import { extractErr, localeActivo } from '../../utils/helpers'
import { GENERIC_ERROR_FALLBACK } from '../../constants/errors'
import { PBadge, PRIORITY_LABEL, SBadge, etiquetaSd } from './sdUtils'
import { POLL_DEFAULT_MS, POLL_FREQUENT_MS, SEARCH_DEBOUNCE_MS, STALE_NEAR_LIVE_MS } from '../../constants/timings'

// PBadge y SBadge vienen de sdUtils. Auditoría 2026-11: aquí había una copia
// local de los dos (y de sus mapas de color), y por eso la lista seguía
// pintando el estado como código cuando se tradujo el compartido.

function fmtDate(d?: string | Date | null) {
  if (!d) return '—'
  return new Date(d).toLocaleDateString(localeActivo(), { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' })
}

type Ticket = {
  [k: string]: unknown
  id: string
  number?: string
  title?: string
  priority?: string
  status?: string
  ticket_type?: string
  requester_name?: string
  sla_resolution_due?: string
  assigned_to?: { full_name?: string } | null
}

function TRow({ t: ticket, onClick }: { t: Ticket; onClick: () => void }) {
  const tr = useAppT()
  const now = new Date()
  const due = ticket.sla_resolution_due ? new Date(ticket.sla_resolution_due) : null
  const overdue = due && due < now && !['resolved', 'closed'].includes(ticket.status || '')
  return (
    <tr onClick={onClick} tabIndex={0} onKeyDown={e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onClick() } }} aria-label={`${ticket.number} ${ticket.title}`}
      style={{ cursor: 'pointer', borderBottom: '1px solid var(--surface-4)' }}
      onMouseEnter={e => e.currentTarget.style.background = 'var(--accent-muted)'}
      onMouseLeave={e => e.currentTarget.style.background = 'transparent'}>
      <td style={{ padding: '10px 14px', fontSize: "var(--text-sm)", color: 'var(--accent)', fontWeight: 600, whiteSpace: 'nowrap' }}>{ticket.number}</td>
      <td style={{ padding: '10px 8px', maxWidth: 320 }}>
        <div style={{ fontSize: "var(--text-base)", color: 'var(--text-1)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{ticket.title}</div>
        {ticket.requester_name && <div className="u-text3-xs">{ticket.requester_name}</div>}
      </td>
      <td style={{ padding: '10px 8px' }}><PBadge v={ticket.priority} /></td>
      <td style={{ padding: '10px 8px' }}><SBadge v={ticket.status} /></td>
      <td style={{ padding: '10px 8px', fontSize: "var(--text-xs)", color: 'var(--text-2)', whiteSpace: 'nowrap' }}>{String(ticket.type_label ?? ticket.ticket_type ?? '')}</td>
      <td style={{ padding: '10px 8px', fontSize: "var(--text-xs)", color: overdue ? COLOR.danger : 'var(--text-2)', whiteSpace: 'nowrap' }}>
        {due ? `${overdue ? '⚠ ' : ''}${fmtDate(due)}` : '—'}
      </td>
      <td style={{ padding: '10px 14px', fontSize: "var(--text-xs)", color: 'var(--text-2)' }}>
        {ticket.assigned_to?.full_name || <span style={{ color: 'var(--text-4)' }}>{tr('service_desk.unassigned')}</span>}
      </td>
    </tr>
  )
}

const TICKETS_POR_PAGINA = 50

export function TicketList({ queueOnly, onSelect }: { queueOnly?: boolean; onSelect: (tk: Ticket) => void }) {
  const t = useAppT()
  const [search, setSearch] = useState('')
  const [filterPrio, setFilterPrio] = useState('')
  const [filterStatus, setFilterStatus] = useState('')
  const [filterType, setFilterType] = useState('')
  // Auditoria 2026-11: «Mi cola» se quedaba en 25 y «Todos» en 100, y la
  // busqueda solo miraba esos 100. Ahora se pagina en el servidor y, en
  // «Todos», la busqueda va al servidor.
  const [page, setPage] = useState(1)
  const [busqueda, setBusqueda] = useState('')
  useEffect(() => {
    const espera = setTimeout(() => { setBusqueda(search.trim()); setPage(1) }, SEARCH_DEBOUNCE_MS)
    return () => clearTimeout(espera)
  }, [search])
  useEffect(() => { setPage(1) }, [filterPrio, filterStatus, filterType])

  const { data: pagina, isLoading } = useQuery<{ items: Ticket[]; total: number }>({
    queryKey: ['sd-tickets', queueOnly, filterPrio, filterStatus, filterType, queueOnly ? '' : busqueda, page],
    queryFn: () => {
      const leer = (r: { data: unknown; meta?: { total?: number } }) => {
        const d = r.data as Ticket[] | { tickets?: Ticket[]; items?: Ticket[] }
        const items = Array.isArray(d) ? d : (d?.tickets || d?.items || [])
        return { items, total: Number(r.meta?.total ?? items.length) }
      }
      if (queueOnly) {
        return ticketsApi.myQueue({ page, page_size: TICKETS_POR_PAGINA }).then(leer)
      }
      return ticketsApi.list({
        priority: filterPrio || undefined,
        status: filterStatus || undefined,
        ticket_type: filterType || undefined,
        search: busqueda || undefined,
        page,
        page_size: TICKETS_POR_PAGINA,
      }).then(leer)
    },
    staleTime: STALE_NEAR_LIVE_MS,
    refetchInterval: POLL_DEFAULT_MS,
  })
  const tickets = useMemo(() => pagina?.items ?? [], [pagina])
  const total = pagina?.total ?? 0
  const paginas = Math.max(1, Math.ceil(total / TICKETS_POR_PAGINA))

  const filtered = useMemo(() => {
    const list = Array.isArray(tickets) ? tickets : []
    // «Todos» ya viene filtrado por el servidor; «Mi cola» no tiene busqueda en
    // la API y se filtra la pagina cargada.
    if (!search || !queueOnly) return list
    const q = search.toLowerCase()
    return list.filter(tk =>
      tk.title?.toLowerCase().includes(q) ||
      tk.number?.toLowerCase().includes(q) ||
      tk.requester_name?.toLowerCase().includes(q)
    )
  }, [tickets, search, queueOnly])

  const { sort: ticketSort, setSort: setTicketSort, sortedData: sortedTickets } = useSort(filtered, 'number')

  const IS = { background: 'var(--surface-3)', border: '1px solid var(--surface-4)',
    borderRadius: 8, padding: '7px 12px', color: 'var(--text-1)', fontSize: "var(--text-sm)",
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
          {['new', 'assigned', 'in_progress', 'pending_client', 'pending_third', 'resolved', 'closed', 'cancelled'].map(s =>
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
      <div data-export-table="service-desk-export" className="u-scroll-x">
        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: "var(--text-base)" }}>
          <thead>
            <tr style={{ borderBottom: '2px solid var(--surface-4)' }}>
              <th aria-sort={ariaSort(ticketSort, 'number')} className="u-cell-nowrap"><SortableTH col="number" sort={ticketSort} onSort={setTicketSort}>{t('service_desk.col_number')}</SortableTH></th>
              <th aria-sort={ariaSort(ticketSort, 'title')} className="u-cell-nowrap"><SortableTH col="title" sort={ticketSort} onSort={setTicketSort}>{t('service_desk.ticket_title')}</SortableTH></th>
              <th aria-sort={ariaSort(ticketSort, 'priority')} className="u-cell-nowrap"><SortableTH col="priority" sort={ticketSort} onSort={setTicketSort}>{t('service_desk.ticket_priority')}</SortableTH></th>
              <th aria-sort={ariaSort(ticketSort, 'status')} className="u-cell-nowrap"><SortableTH col="status" sort={ticketSort} onSort={setTicketSort}>{t('service_desk.ticket_status')}</SortableTH></th>
              <th aria-sort={ariaSort(ticketSort, 'ticket_type')} className="u-cell-nowrap"><SortableTH col="ticket_type" sort={ticketSort} onSort={setTicketSort}>{t('service_desk.ticket_type')}</SortableTH></th>
              <th aria-sort={ariaSort(ticketSort, 'sla_due')} className="u-cell-nowrap"><SortableTH col="sla_due" sort={ticketSort} onSort={setTicketSort}>{t('service_desk.col_sla_deadline')}</SortableTH></th>
              <th aria-sort={ariaSort(ticketSort, 'assignee_name')} className="u-cell-nowrap"><SortableTH col="assignee_name" sort={ticketSort} onSort={setTicketSort}>{t('service_desk.assigned_to')}</SortableTH></th>
            </tr>
          </thead>
          <tbody>
            {sortedTickets.map(tk => <TRow key={tk.id} t={tk} onClick={() => onSelect(tk)} />)}
          </tbody>
        </table>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 12, fontSize: "var(--text-xs)", color: 'var(--text-3)', padding: '10px 4px', flexWrap: 'wrap' }}>
          <span>{total} ticket{total !== 1 ? 's' : ''}</span>
          {paginas > 1 && <Pagination page={page} totalPages={paginas} onChange={setPage} />}
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

  type MI = { [k: string]: unknown; id: string; number?: string; title?: string; severity?: string; status?: string; commander?: string; declared_at?: string; resolved_at?: string }
  const { data: mis = [], isLoading } = useQuery<MI[]>({
    queryKey: ['sd-major-incidents'],
    queryFn: () => sdRoutingApi.majorIncidents().then(r => r.data as MI[]),
    refetchInterval: POLL_FREQUENT_MS,
  })

  const activeMis = mis.filter(m => m.status === 'active')
  const { sort: miSort, setSort: setMiSort, sortedData: sortedMis } = useSort<MI>(mis, 'declared_at', 'desc')

  return (
    <div>
      {activeMis.length > 0 && (
        <div style={{ background: alpha(COLOR.danger, '15'), border: `1px solid ${alpha(COLOR.danger, '40')}`,
          borderRadius: 12, padding: '16px 20px', marginBottom: 20 }}>
          <div style={{ fontSize: "var(--text-base)", fontWeight: 700, color: COLOR.danger, marginBottom: 10 }}>
            🚨 {activeMis.length} {t('service_desk.mi_declared_at').toLowerCase()} {activeMis.length > 1 ? 's' : ''}
          </div>
          {activeMis.map(m => (
            <div key={m.id} style={{ display: 'flex', justifyContent: 'space-between',
              alignItems: 'center', padding: '8px 0', borderTop: `1px solid ${alpha(COLOR.danger, '20')}` }}>
              <div>
                <span style={{ fontWeight: 600, fontSize: "var(--text-sm)", color: COLOR.danger, marginRight: 10 }}>{m.number}</span>
                <span style={{ fontSize: "var(--text-base)", color: 'var(--text-1)' }}>{m.title}</span>
              </div>
              <div className="u-text2-xs">{t('service_desk.mi_declared_at')} {fmtDate(m.declared_at)}</div>
            </div>
          ))}
        </div>
      )}

      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 20 }}>
        <div className="u-text2-base">{mis.length} incidentes mayores registrados</div>
        <Button onClick={() => setShowDeclare(true)} style={{ background: alpha(COLOR.danger, '20'), color: COLOR.danger,
          border: `1px solid ${alpha(COLOR.danger, '40')}` }}>
          🚨 {t('service_desk.mi_declare_btn')}
        </Button>
      </div>

      {isLoading ? <Spinner /> : (
        <div data-export-table="service-desk-export" className="u-scroll-x">
          <table className="u-table">
            <thead>
              <tr style={{ borderBottom: '2px solid var(--surface-4)' }}>
                <th aria-sort={ariaSort(miSort, 'number')} className="u-cell-nowrap"><SortableTH col="number" sort={miSort} onSort={setMiSort}>{t('service_desk.col_number')}</SortableTH></th>
                <th aria-sort={ariaSort(miSort, 'title')} className="u-cell-nowrap"><SortableTH col="title" sort={miSort} onSort={setMiSort}>{t('service_desk.ticket_title')}</SortableTH></th>
                <th aria-sort={ariaSort(miSort, 'severity')} className="u-cell-nowrap"><SortableTH col="severity" sort={miSort} onSort={setMiSort}>{t('service_desk.mi_severity')}</SortableTH></th>
                <th aria-sort={ariaSort(miSort, 'status')} className="u-cell-nowrap"><SortableTH col="status" sort={miSort} onSort={setMiSort}>{t('service_desk.ticket_status')}</SortableTH></th>
                <th aria-sort={ariaSort(miSort, 'commander')} className="u-cell-nowrap"><SortableTH col="commander" sort={miSort} onSort={setMiSort}>{t('service_desk.mi_commander')}</SortableTH></th>
                <th aria-sort={ariaSort(miSort, 'declared_at')} className="u-cell-nowrap"><SortableTH col="declared_at" sort={miSort} onSort={setMiSort}>{t('service_desk.mi_declared_at')}</SortableTH></th>
                <th aria-sort={ariaSort(miSort, 'resolved_at')} className="u-cell-nowrap"><SortableTH col="resolved_at" sort={miSort} onSort={setMiSort}>{t('service_desk.mi_resolved_at')}</SortableTH></th>
              </tr>
            </thead>
            <tbody>
              {sortedMis.map(m => (
                <tr key={m.id} className="u-border-b">
                  <td style={{ padding: '10px 8px', fontSize: "var(--text-sm)", color: COLOR.danger, fontWeight: 700 }}>{m.number}</td>
                  <td style={{ padding: '10px 8px', fontSize: "var(--text-base)", color: 'var(--text-1)' }}>{m.title}</td>
                  <td style={{ padding: '10px 8px' }}>
                    <span style={{ fontSize: "var(--text-sm)", fontWeight: 700,
                      color: m.severity === 'P1' ? COLOR.danger : 'var(--orange)' }}>{m.severity}</span>
                  </td>
                  <td style={{ padding: '10px 8px' }}>
                    <span style={{ fontSize: "var(--text-xs)", fontWeight: 600,
                      color: m.status === 'active' ? COLOR.danger : COLOR.success,
                      background: m.status === 'active' ? alpha(COLOR.danger, '15') : alpha(COLOR.success, '15'),
                      padding: '2px 8px', borderRadius: 4 }}>{etiquetaSd('mi_st', m.status)}</span>
                  </td>
                  <td style={{ padding: '10px 8px', fontSize: "var(--text-sm)", color: 'var(--text-2)' }}>{m.commander || '—'}</td>
                  <td style={{ padding: '10px 8px', fontSize: "var(--text-xs)", color: 'var(--text-2)' }}>{fmtDate(m.declared_at)}</td>
                  <td style={{ padding: '10px 8px', fontSize: "var(--text-xs)", color: 'var(--text-2)' }}>{m.resolved_at ? fmtDate(m.resolved_at) : '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
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

function DeclareMIModal({ onClose, onSaved }: { onClose: () => void; onSaved: () => void }) {
  const t = useAppT()
  const toast = useToast()
  const idPrefix = useId()
  const [form, setForm] = useState({ title: '', severity: 'P1', impact_statement: '' })
  const { mutate, isPending } = useMutation({
    mutationFn: (data: Record<string, unknown>) => sdRoutingApi.createMajorIncident(data),
    onSuccess: onSaved,
    onError: (e: unknown) => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })
  const set = (k: string) => (e: { target: { value: string } }) => setForm(f => ({ ...f, [k]: e.target.value }))
  const IS: CSSProperties = { width: '100%', background: 'var(--surface-3)', border: '1px solid var(--surface-4)',
    borderRadius: 8, padding: '9px 13px', color: 'var(--text-1)', fontSize: "var(--text-base)",
    outline: 'none', fontFamily: 'inherit', boxSizing: 'border-box' }
  const LS: CSSProperties = { fontSize: "var(--text-xs)", fontWeight: 600, color: 'var(--text-2)', display: 'block',
    marginBottom: 5, textTransform: 'uppercase', letterSpacing: '0.06em' }

  return (
    <Modal open title={`🚨 ${t('service_desk.mi_declare_btn')}`} onClose={onClose}>
      <div className="u-stack-16">
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
        <div className="u-actions-10">
          <Button variant="secondary" onClick={onClose}>{t('common.cancel')}</Button>
          <Button onClick={() => mutate(form)} disabled={isPending || !form.title} loading={isPending}
            style={{ background: alpha(COLOR.danger, '20'), color: COLOR.danger, border: `1px solid ${alpha(COLOR.danger, '40')}` }}>
            {t('service_desk.mi_declare_btn')}
          </Button>
        </div>
      </div>
    </Modal>
  )
}

type Rule = {
  [k: string]: unknown
  id: string
  name?: string
  priority?: number
  is_active?: boolean
  conditions?: string
  actions?: string
}

export function RoutingRules() {
  const t = useAppT()
  const qc = useQueryClient()
  const toast = useToast()
  const [showNew, setShowNew] = useState(false)
  const [editingRule, setEditingRule] = useState<Rule | null>(null)

  const { data: rules = [], isLoading } = useQuery<Rule[]>({
    queryKey: ['sd-routing-rules'],
    queryFn: () => sdRoutingApi.list().then(r => r.data),
  })

  const { mutate: toggleRule } = useMutation({
    mutationFn: ({ id, is_active }: { id: string; is_active: boolean }) => sdRoutingApi.update(id, { is_active }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['sd-routing-rules'] }),
    onError: (e: unknown) => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })
  const { mutate: deleteRule } = useMutation({
    mutationFn: (id: string) => sdRoutingApi.delete(id),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['sd-routing-rules'] }); toast.success(t('service_desk.routing_rule_deleted')) },
    onError: (e: unknown) => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 20 }}>
        <div className="u-text3-sm">
          {t('service_desk.routing_no_rules_desc')}
        </div>
        <Button onClick={() => setShowNew(true)}>+ {t('service_desk.routing_new_title')}</Button>
      </div>

      {isLoading ? <Spinner /> :
       rules.length === 0 ? <EmptyState icon="⚡" title={t('service_desk.routing_no_rules')} description={t('service_desk.routing_no_rules_desc')} /> :
      <div className="u-stack-8">
        {rules.map((rule, _i) => {
          let conds: Record<string, unknown> = {}, acts: Record<string, unknown> = {}
          try { conds = JSON.parse(rule.conditions || '{}'); acts = JSON.parse(rule.actions || '{}') } catch { /* noop */ }
          return (
            <div key={rule.id} style={{ background: 'var(--surface-2)', border: `1px solid ${rule.is_active ? 'var(--surface-4)' : 'var(--surface-3)'}`,
              borderRadius: 'var(--radius-md)', padding: '14px 18px', opacity: rule.is_active ? 1 : 0.5 }}>
              <div className="u-row-between">
                <div>
                  <span style={{ fontSize: "var(--text-xs)", color: 'var(--text-3)', marginRight: 10 }}>#{rule.priority}</span>
                  <span style={{ fontSize: "var(--text-md)", fontWeight: 600, color: 'var(--text-1)' }}>{rule.name}</span>
                </div>
                <div className="u-row-8">
                  <button onClick={() => toggleRule({ id: rule.id, is_active: !rule.is_active })}
                    aria-pressed={rule.is_active}
                    aria-label={`${rule.is_active ? 'Desactivar' : 'Activar'} regla ${rule.name}`}
                    style={{ padding: '4px 12px', borderRadius: 'var(--radius-sm)', border: '1px solid var(--surface-4)',
                      background: 'transparent', color: rule.is_active ? COLOR.success : 'var(--text-3)',
                      fontSize: "var(--text-xs)", cursor: 'pointer', fontFamily: 'inherit' }}>
                    {rule.is_active ? t('service_desk.routing_active') : t('service_desk.routing_inactive')}
                  </button>
                  <button aria-label={`${t('common.edit')} ${rule.name}`} onClick={() => setEditingRule(rule)}
                    style={{ padding: '4px 10px', borderRadius: 'var(--radius-sm)', border: '1px solid var(--surface-4)',
                      background: 'transparent', color: COLOR.accent, fontSize: "var(--text-xs)", cursor: 'pointer', fontFamily: 'inherit' }}>
                    ✏ {t('common.edit')}
                  </button>
                  <button aria-label={`${t('common.delete')} ${rule.name}`} onClick={() => deleteRule(rule.id)}
                    style={{ padding: '4px 10px', borderRadius: 'var(--radius-sm)', border: '1px solid var(--surface-4)',
                      background: 'transparent', color: COLOR.danger, fontSize: "var(--text-xs)", cursor: 'pointer', fontFamily: 'inherit' }}>
                    {t('common.delete')}
                  </button>
                </div>
              </div>
              <div style={{ display: 'flex', gap: 24, marginTop: 10, fontSize: "var(--text-sm)" }}>
                <div>
                  <span style={{ color: 'var(--text-3)', marginRight: 6 }}>SI</span>
                  {Object.entries(conds).map(([k, v]) => (
                    <span key={k} style={{ background: 'var(--surface-4)', borderRadius: 4,
                      padding: '2px 8px', marginRight: 6, color: 'var(--text-2)' }}>
                      {k}: {Array.isArray(v) ? v.join(', ') : String(v)}
                    </span>
                  ))}
                </div>
                <div>
                  <span style={{ color: 'var(--text-3)', marginRight: 6 }}>THEN</span>
                  {Object.entries(acts).map(([k, v]) => (
                    <span key={k} style={{ background: alpha(COLOR.accent, '15'), borderRadius: 4,
                      padding: '2px 8px', marginRight: 6, color: COLOR.accent }}>
                      {k}: {String(v)}
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

type Entry = { key: string; value: string }
function NewRoutingRuleModal({ onClose, onSaved, rule }: { onClose: () => void; onSaved: () => void; rule?: Rule }) {
  const idCampo = useId()
  const t = useAppT()
  const toast = useToast()
  const isEdit = !!rule

  const parseEntries = (jsonStr: unknown): Entry[] => {
    try {
      const obj = typeof jsonStr === 'string' ? JSON.parse(jsonStr || '{}') : (jsonStr || {})
      return Object.entries(obj).map(([key, value]) => ({ key, value: Array.isArray(value) ? value.join(',') : String(value) }))
    } catch { return [] }
  }

  const [form, setForm] = useState<{ name: string; priority: number | string }>(isEdit ? { name: rule!.name || '', priority: rule!.priority ?? 100 } : { name: '', priority: 100 })
  const [conditions, setConditions] = useState<Entry[]>(isEdit ? parseEntries(rule!.conditions) : [])
  const [actions, setActions] = useState<Entry[]>(isEdit ? parseEntries(rule!.actions) : [{ key: 'assign_group', value: '' }])

  const { data: groups = [] } = useQuery<Array<{ id?: string; name?: string }>>({
    queryKey: ['sd-groups'],
    queryFn: () => sdGroupsApi.list().then(r => r.data),
  })
  const { data: users = [] } = useQuery<Array<{ id?: string; full_name?: string }>>({
    queryKey: ['users'],
    queryFn: () => usersApi.list().then(r => r.data),
  })
  const { data: slaPolices = [] } = useQuery<Array<{ id?: string; name?: string }>>({
    queryKey: ['sd-sla-policies'],
    queryFn: () => sdSlaPoliciesApi.list().then(r => r.data).catch(() => []),
  })

  const { mutate, isPending } = useMutation({
    mutationFn: (data: Record<string, unknown>) => isEdit
      ? sdRoutingApi.update(rule!.id, data)
      : sdRoutingApi.create(data),
    onSuccess: onSaved,
    onError: (e: unknown) => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })

  const IS: CSSProperties = {
    width: '100%', background: 'var(--surface-3)', border: '1px solid var(--surface-4)',
    borderRadius: 8, padding: '8px 11px', color: 'var(--text-1)', fontSize: "var(--text-sm)",
    outline: 'none', fontFamily: 'inherit', boxSizing: 'border-box',
  }
  const LS: CSSProperties = {
    fontSize: "var(--text-2xs)", fontWeight: 600, color: 'var(--text-3)', display: 'block',
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
  const removeCondition = (i: number) => setConditions(prev => prev.filter((_, idx) => idx !== i))
  const updateCond = (i: number, patch: Partial<Entry>) => setConditions(prev => prev.map((c, idx) => idx === i ? { ...c, ...patch } : c))

  const addAction = () => {
    const usedActKeys = actions.map(a => a.key)
    const next = ACT_TYPES.find(type => !usedActKeys.includes(type.key))
    if (next) setActions(prev => [...prev, { key: next.key, value: '' }])
  }
  const removeAction = (i: number) => setActions(prev => prev.filter((_, idx) => idx !== i))
  const updateAct = (i: number, patch: Partial<Entry>) => setActions(prev => prev.map((a, idx) => idx === i ? { ...a, ...patch } : a))

  const renderCondValue = (cond: Entry, i: number) => {
    const upd = (v: string) => updateCond(i, { value: v })
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
                fontSize: "var(--text-xs)", cursor: 'pointer', fontFamily: 'inherit',
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

  const renderActValue = (act: Entry, i: number) => {
    const upd = (v: string) => updateAct(i, { value: v })
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
        <option value="">{t('queueandrouting.no_cambiar')}</option>
        {Object.entries(PRIORITY_LABEL).map(([v, l]) => <option key={v} value={v}>{l}</option>)}
      </select>
    )
    return <input value={act.value} onChange={e => upd(e.target.value)} style={IS} />
  }

  const handleSave = () => {
    if (!form.name.trim()) { toast.error(t('service_desk.routing_name_required')); return }
    const condObj: Record<string, string | string[]> = {}
    for (const c of conditions) {
      if (!c.value) continue
      if (c.key === 'priority' || c.key === 'day_of_week') {
        condObj[c.key] = c.value.includes(',') ? c.value.split(',') : c.value
      } else {
        condObj[c.key] = c.value
      }
    }
    const actObj: Record<string, string> = {}
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
            <label id={`${idCampo}-et1`} htmlFor={`${idCampo}-1`} style={LS}>{t('service_desk.routing_name_lbl')} *</label>
            <input id={`${idCampo}-1`} aria-labelledby={`${idCampo}-et1`} value={form.name} onChange={e => setForm(f => ({ ...f, name: e.target.value }))}
              style={IS} autoFocus />
          </div>
          <div>
            <label id={`${idCampo}-et2`} htmlFor={`${idCampo}-2`} style={LS}>{t('service_desk.routing_order_lbl')}</label>
            <input id={`${idCampo}-2`} aria-labelledby={`${idCampo}-et2`} type="number" value={form.priority}
              onChange={e => setForm(f => ({ ...f, priority: e.target.value }))}
              style={{ ...IS }} />
          </div>
        </div>

        <div style={{ background: 'var(--surface-1)', borderRadius: 'var(--radius-md)', padding: 14 }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 10 }}>
            <span style={{ fontSize: "var(--text-sm)", fontWeight: 700, color: 'var(--text-2)' }}>{t('service_desk.cond_field')}</span>
            <button type="button" onClick={addCondition}
              disabled={availCondTypes.length === 0}
              style={{ fontSize: "var(--text-xs)", padding: '3px 10px', borderRadius: 'var(--radius-sm)', border: '1px solid var(--surface-4)',
                background: 'var(--surface-3)', color: 'var(--text-2)', cursor: availCondTypes.length ? 'pointer' : 'not-allowed',
                fontFamily: 'inherit' }}>
              {t('queueandrouting.condicion')}
            </button>
          </div>
          {conditions.length === 0 && (
            <div style={{ fontSize: "var(--text-sm)", color: 'var(--text-3)', textAlign: 'center', padding: '10px 0' }}>
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
                    color: COLOR.danger, cursor: 'pointer', fontSize: "var(--text-md)", padding: '3px 6px', lineHeight: 1 }}>
                  ×
                </button>
              </div>
            </div>
          ))}
        </div>

        <div style={{ background: 'var(--surface-1)', borderRadius: 'var(--radius-md)', padding: 14 }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 10 }}>
            <span style={{ fontSize: "var(--text-sm)", fontWeight: 700, color: 'var(--text-2)' }}>{t('service_desk.act_label')}</span>
            <button type="button" onClick={addAction}
              disabled={actions.length >= ACT_TYPES.length}
              style={{ fontSize: "var(--text-xs)", padding: '3px 10px', borderRadius: 'var(--radius-sm)', border: '1px solid var(--surface-4)',
                background: 'var(--surface-3)', color: 'var(--text-2)', cursor: actions.length < ACT_TYPES.length ? 'pointer' : 'not-allowed',
                fontFamily: 'inherit' }}>
              {t('queueandrouting.accion')}
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
                    color: COLOR.danger, cursor: 'pointer', fontSize: "var(--text-md)", padding: '3px 6px', lineHeight: 1 }}>
                  ×
                </button>
              </div>
            </div>
          ))}
        </div>

        <div className="u-actions-10">
          <Button variant="secondary" onClick={onClose}>{t('common.cancel')}</Button>
          <Button onClick={handleSave} disabled={isPending || !form.name} loading={isPending}>{isEdit ? t('common.save') : t('service_desk.routing_new_title')}</Button>
        </div>
      </div>
    </Modal>
  )
}
