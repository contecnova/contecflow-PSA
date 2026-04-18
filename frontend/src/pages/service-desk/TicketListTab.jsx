import { useState, useMemo } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useAppT } from '../../i18n/AppLangContext'
import { Spinner, EmptyState, useSort, SortableTH } from '../../components/ui'
import api from '../../services/api'
import { COLOR } from '../../constants/theme'
import { PBadge, SBadge, fmtDate, PRIORITY_LABEL } from './sdUtils'

function TRow({ t: ticket, onClick }) {
  const tr = useAppT()
  const now = new Date()
  const due = ticket.sla_resolution_due ? new Date(ticket.sla_resolution_due) : null
  const overdue = due && due < now && !['resolved', 'closed'].includes(ticket.status)
  return (
    <tr
      onClick={onClick}
      tabIndex={0}
      onKeyDown={e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onClick() } }}
      aria-label={`${ticket.number} ${ticket.title}`}
      style={{ cursor: 'pointer', borderBottom: '1px solid var(--surface-4)' }}
      onMouseEnter={e => e.currentTarget.style.background = 'var(--accent-muted)'}
      onMouseLeave={e => e.currentTarget.style.background = 'transparent'}
    >
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

export default function TicketListTab({ queueOnly, onSelect }) {
  const t = useAppT()
  const [search, setSearch] = useState('')
  const [filterPrio, setFilterPrio] = useState('')
  const [filterStatus, setFilterStatus] = useState('')
  const [filterType, setFilterType] = useState('')

  const { data: tickets = [], isLoading } = useQuery({
    queryKey: ['sd-tickets', queueOnly, filterPrio, filterStatus, filterType],
    queryFn: () => {
      if (queueOnly) return api.get('/sd/tickets/my-queue').then(r => r.data)
      return api.get('/sd/tickets', {
        params: {
          priority: filterPrio || undefined,
          status: filterStatus || undefined,
          ticket_type: filterType || undefined,
          page_size: 100,
        },
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
      tk.requester_name?.toLowerCase().includes(q),
    )
  }, [tickets, search])

  const { sort: ticketSort, setSort: setTicketSort, sortedData: sortedTickets } = useSort(filtered, 'number')

  const IS = {
    background: 'var(--surface-3)', border: '1px solid var(--surface-4)',
    borderRadius: 8, padding: '7px 12px', color: 'var(--text-1)', fontSize: 12,
    outline: 'none', fontFamily: 'inherit',
  }

  return (
    <div>
      <div style={{ display: 'flex', gap: 10, marginBottom: 16, flexWrap: 'wrap' }}>
        <input
          placeholder={t('service_desk.search_tickets')}
          value={search}
          aria-label={t('service_desk.search_tickets')}
          onChange={e => setSearch(e.target.value)}
          style={{ ...IS, flex: 1, minWidth: 200 }}
        />
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

      {isLoading
        ? <div style={{ textAlign: 'center', padding: 40 }}><Spinner /></div>
        : filtered.length === 0
          ? <EmptyState icon="🎫" title={t('service_desk.no_tickets')} description={t('service_desk.no_matching')} />
          : (
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
            </div>
          )}
    </div>
  )
}
