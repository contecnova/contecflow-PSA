import { useState, useMemo } from 'react'
import type { CSSProperties, KeyboardEvent as ReactKeyboardEvent } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Search, AlertTriangle, Inbox } from 'lucide-react'
import { useAppT } from '../../i18n/AppLangContext'
import { Spinner, useSort, SortableTH } from '../../components/ui'
import { ticketsApi } from '../../services/api'
import { COLOR } from '../../constants/theme'
import { PBadge, SBadge, fmtDate, PRIORITY_LABEL } from './sdUtils'

interface TicketRow {
  id: string | number
  number?: string
  title?: string
  requester_name?: string
  priority?: string
  status?: string
  ticket_type?: string
  sla_resolution_due?: string
  assigned_to?: { full_name?: string } | null
}

interface TicketListTabProps {
  queueOnly?: boolean
  onSelect: (ticket: TicketRow) => void
}

// ── Row ─────────────────────────────────────────────────────────────────────
function TRow({ t: ticket, onClick }: { t: TicketRow; onClick: () => void }) {
  const tr = useAppT()
  const now = new Date()
  const due = ticket.sla_resolution_due ? new Date(ticket.sla_resolution_due) : null
  const overdue = due && due < now && !['resolved', 'closed'].includes(ticket.status)
  return (
    <tr
      onClick={onClick}
      tabIndex={0}
      onKeyDown={(e: ReactKeyboardEvent<HTMLTableRowElement>) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onClick() } }}
      aria-label={`${ticket.number} ${ticket.title}`}
      style={{ cursor: 'pointer', borderBottom: '1px solid var(--surface-4)', transition: 'background 0.12s var(--easing)' }}
      onMouseEnter={e => e.currentTarget.style.background = 'var(--accent-muted)'}
      onMouseLeave={e => e.currentTarget.style.background = 'transparent'}
    >
      <td style={{ padding: '10px 14px', fontSize: 'var(--text-sm)', color: 'var(--accent)', fontWeight: 600, whiteSpace: 'nowrap' }}>
        {ticket.number}
      </td>
      <td style={{ padding: '10px 8px', maxWidth: 320 }}>
        <div style={{ fontSize: 'var(--text-base)', color: 'var(--text-1)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
          {ticket.title}
        </div>
        {ticket.requester_name && (
          <div className="ds-muted" style={{ fontSize: 'var(--text-xs)' }}>{ticket.requester_name}</div>
        )}
      </td>
      <td style={{ padding: '10px 8px' }}><PBadge v={ticket.priority} /></td>
      <td style={{ padding: '10px 8px' }}><SBadge v={ticket.status} /></td>
      <td style={{ padding: '10px 8px', fontSize: 'var(--text-xs)', color: 'var(--text-2)', whiteSpace: 'nowrap' }}>
        {ticket.ticket_type?.replace(/_/g, ' ')}
      </td>
      <td style={{ padding: '10px 8px', fontSize: 'var(--text-xs)', color: overdue ? COLOR.danger : 'var(--text-2)', whiteSpace: 'nowrap' }}>
        {due ? (
          <span style={{ display: 'inline-flex', alignItems: 'center', gap: 4 }}>
            {overdue && <AlertTriangle size={11} />} {fmtDate(due)}
          </span>
        ) : '—'}
      </td>
      <td style={{ padding: '10px 14px', fontSize: 'var(--text-xs)', color: 'var(--text-2)' }}>
        {ticket.assigned_to?.full_name || <span style={{ color: 'var(--text-4)' }}>{tr('service_desk.unassigned')}</span>}
      </td>
    </tr>
  )
}

// ── Main ────────────────────────────────────────────────────────────────────
export default function TicketListTab({ queueOnly = false, onSelect }: TicketListTabProps) {
  const t = useAppT()
  const [search, setSearch] = useState('')
  const [filterPrio, setFilterPrio] = useState('')
  const [filterStatus, setFilterStatus] = useState('')
  const [filterType, setFilterType] = useState('')

  const { data: tickets = [], isLoading } = useQuery<TicketRow[]>({
    queryKey: ['sd-tickets', queueOnly, filterPrio, filterStatus, filterType],
    queryFn: () => {
      if (queueOnly) return ticketsApi.myQueue().then(r => r.data)
      return ticketsApi.list({
        priority: filterPrio || undefined,
        status: filterStatus || undefined,
        ticket_type: filterType || undefined,
        page_size: 100,
      }).then(r => {
        const d = r.data as unknown
        if (Array.isArray(d)) return d as TicketRow[]
        if (typeof d === 'object' && d !== null) {
          const payload = d as { tickets?: unknown; items?: unknown }
          if (Array.isArray(payload.tickets)) return payload.tickets as TicketRow[]
          if (Array.isArray(payload.items)) return payload.items as TicketRow[]
        }
        return []
      })
    },
    staleTime: 15000,
    refetchInterval: 60000,
  })

  const filtered = useMemo(() => {
    const list = Array.isArray(tickets) ? tickets : []
    if (!search) return list
    const q = search.toLowerCase()
    return list.filter((tk) =>
      tk.title?.toLowerCase().includes(q) ||
      tk.number?.toLowerCase().includes(q) ||
      tk.requester_name?.toLowerCase().includes(q),
    )
  }, [tickets, search])

  const { sort: ticketSort, setSort: setTicketSort, sortedData: sortedTickets } = useSort(filtered, 'number')

  const hasFilters = !!(search || filterPrio || filterStatus || filterType)

  return (
    <div className="ds-stack-lg">
      {/* Toolbar — search + filtros + contador */}
      <div className="ds-toolbar">
        <div style={{ position: 'relative', flex: '1 1 240px', maxWidth: 380 }}>
          <Search size={14} aria-hidden style={{
            position: 'absolute', left: 10, top: '50%', transform: 'translateY(-50%)',
            color: 'var(--text-3)', pointerEvents: 'none',
          }} />
          <input
            placeholder={t('service_desk.search_tickets')}
            value={search}
            aria-label={t('service_desk.search_tickets')}
            onChange={e => setSearch(e.target.value)}
            className="ds-input"
            style={{ paddingLeft: 32 }}
          />
        </div>
        <select aria-label={t('service_desk.filter_all_priorities')}
          value={filterPrio} onChange={e => setFilterPrio(e.target.value)}
          className="ds-input" style={{ width: 'auto', minWidth: 140 }}>
          <option value="">{t('service_desk.filter_all_priorities')}</option>
          {['p1_critical', 'p2_high', 'p3_medium', 'p4_low'].map(p =>
            <option key={p} value={p}>{PRIORITY_LABEL[p]}</option>)}
        </select>
        <select aria-label={t('service_desk.filter_all_statuses')}
          value={filterStatus} onChange={e => setFilterStatus(e.target.value)}
          className="ds-input" style={{ width: 'auto', minWidth: 140 }}>
          <option value="">{t('service_desk.filter_all_statuses')}</option>
          {['new', 'assigned', 'in_progress', 'pending_client', 'resolved', 'closed'].map(s =>
            <option key={s} value={s}>{s.replace(/_/g, ' ')}</option>)}
        </select>
        <select aria-label={t('service_desk.filter_all_types')}
          value={filterType} onChange={e => setFilterType(e.target.value)}
          className="ds-input" style={{ width: 'auto', minWidth: 140 }}>
          <option value="">{t('service_desk.filter_all_types')}</option>
          {['incident', 'service_request', 'change', 'problem', 'question'].map(tk =>
            <option key={tk} value={tk}>{tk.replace(/_/g, ' ')}</option>)}
        </select>
        <div className="ds-toolbar__spacer" />
        {!isLoading && (
          <span className="ds-muted" style={{ fontSize: 'var(--text-xs)' }}>
            {filtered.length} ticket{filtered.length !== 1 ? 's' : ''}
          </span>
        )}
      </div>

      {/* Body */}
      {isLoading ? (
        <div style={{ textAlign: 'center', padding: 'var(--space-9)' }}><Spinner /></div>
      ) : filtered.length === 0 ? (
        <div className="ds-empty">
          <Inbox size={36} className="ds-empty__icon" />
          <div className="ds-empty__title">
            {hasFilters ? t('service_desk.no_matching') : t('service_desk.no_tickets')}
          </div>
          <div className="ds-empty__desc">
            {hasFilters ? 'Prueba con otros filtros o quita la búsqueda.' : 'Cuando lleguen tickets aparecerán aquí.'}
          </div>
        </div>
      ) : (
        <div className="ds-card" style={{ padding: 0, overflow: 'hidden' }}>
          <div style={{ overflowX: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 'var(--text-base)' }}>
              <thead>
                <tr style={{ borderBottom: '1px solid var(--surface-4)', background: 'var(--surface-3)' }}>
                  <th style={th}><SortableTH col="number" sort={ticketSort} onSort={setTicketSort}>{t('service_desk.col_number')}</SortableTH></th>
                  <th style={th}><SortableTH col="title" sort={ticketSort} onSort={setTicketSort}>{t('service_desk.ticket_title')}</SortableTH></th>
                  <th style={th}><SortableTH col="priority" sort={ticketSort} onSort={setTicketSort}>{t('service_desk.ticket_priority')}</SortableTH></th>
                  <th style={th}><SortableTH col="status" sort={ticketSort} onSort={setTicketSort}>{t('service_desk.ticket_status')}</SortableTH></th>
                  <th style={th}><SortableTH col="ticket_type" sort={ticketSort} onSort={setTicketSort}>{t('service_desk.ticket_type')}</SortableTH></th>
                  <th style={th}><SortableTH col="sla_due" sort={ticketSort} onSort={setTicketSort}>{t('service_desk.col_sla_deadline')}</SortableTH></th>
                  <th style={th}><SortableTH col="assignee_name" sort={ticketSort} onSort={setTicketSort}>{t('service_desk.assigned_to')}</SortableTH></th>
                </tr>
              </thead>
              <tbody>
                {sortedTickets.map(tk => <TRow key={tk.id} t={tk} onClick={() => onSelect(tk)} />)}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  )
}

const th: CSSProperties = {
  padding: '10px 8px',
  whiteSpace: 'nowrap',
  textAlign: 'left',
  fontSize: 'var(--text-xs)',
  fontWeight: 700,
  textTransform: 'uppercase',
  letterSpacing: '0.06em',
  color: 'var(--text-3)',
}
