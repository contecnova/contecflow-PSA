import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useAppT } from '../../i18n/AppLangContext'
import { useToast } from '../../context/ToastContext'
import { Spinner } from '../../components/ui'
import api from '../../services/api'

const PRIO_COLOR = { p1_critical: '#E24B4A', p2_high: '#BA7517', p3_medium: '#378ADD', p4_low: '#1D9E75' }
const PRIO_LABEL = { p1_critical: 'P1', p2_high: 'P2', p3_medium: 'P3', p4_low: 'P4' }

export default function KanbanTicketsTab({ onSelect }) {
  const t = useAppT()
  const toast = useToast()
  const qc = useQueryClient()
  const [dragging, setDragging] = useState(null)
  const [dragOverCol, setDragOverCol] = useState(null)

  const KANBAN_COLS = [
    { id: 'open',           label: t('service_desk.status_open'),           color: '#378ADD' },
    { id: 'in_progress',    label: t('service_desk.status_in_progress'),    color: '#7F77DD' },
    { id: 'waiting_client', label: t('service_desk.status_waiting_client'), color: '#BA7517' },
    { id: 'pending_change', label: t('service_desk.status_pending_change'), color: '#D85A30' },
    { id: 'resolved',       label: t('service_desk.status_resolved'),       color: '#1D9E75' },
  ]

  const { data: raw = {}, isLoading } = useQuery({
    queryKey: ['sd-tickets-kanban'],
    queryFn: () => api.get('/sd/tickets', { params: { page_size: 200 } }).then(r => {
      const tickets = Array.isArray(r.data) ? r.data : (r.data?.tickets || [])
      const cols = {}
      KANBAN_COLS.forEach(c => { cols[c.id] = [] })
      tickets.forEach(ticket => {
        const s = ticket.status
        if (cols[s]) cols[s].push(ticket)
        else cols['open'] = [...(cols['open'] || []), ticket]
      })
      return cols
    }),
    staleTime: 30000,
  })

  const { mutate: moveTicket } = useMutation({
    mutationFn: ({ id, status }) => api.patch(`/sd/tickets/${id}`, { status }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['sd-tickets-kanban'] }),
    onError: e => toast.error(e?.response?.data?.detail || 'Error al mover ticket'),
  })

  const onDragStart = (e, ticket, fromCol) => {
    setDragging({ ticket, fromCol })
    e.dataTransfer.effectAllowed = 'move'
    e.dataTransfer.setData('text/plain', String(ticket.id))
  }
  const onDragOver = e => { e.preventDefault(); e.dataTransfer.dropEffect = 'move' }
  const onDragEnter = (e, colId) => { e.preventDefault(); setDragOverCol(colId) }
  const onDragLeave = e => { if (!e.currentTarget.contains(e.relatedTarget)) setDragOverCol(null) }
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
          <div
            key={col.id}
            role="presentation"
            onDragOver={onDragOver}
            onDragEnter={e => onDragEnter(e, col.id)}
            onDragLeave={onDragLeave}
            onDrop={e => onDrop(e, col.id)}
            style={{
              minWidth: 220, width: 220, flexShrink: 0,
              outline: dragOverCol === col.id ? `2px solid ${col.color}` : '2px solid transparent',
              borderRadius: 10, transition: 'outline .15s',
            }}
          >
            <div style={{
              display: 'flex', alignItems: 'center', gap: 8, marginBottom: 10,
              padding: '8px 12px', background: `${col.color}18`,
              borderRadius: 8, border: `1px solid ${col.color}35`,
            }}>
              <div style={{ width: 8, height: 8, borderRadius: '50%', background: col.color, flexShrink: 0 }} />
              <div style={{ fontSize: 12, fontWeight: 700, color: 'var(--text-1)', flex: 1 }}>{col.label}</div>
              <div style={{ fontSize: 11, color: col.color, fontWeight: 700, fontFamily: "'Space Mono', monospace" }}>{tickets.length}</div>
            </div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 8, minHeight: 60 }}>
              {tickets.map(ticket => (
                <div
                  key={ticket.id}
                  draggable
                  onDragStart={e => onDragStart(e, ticket, col.id)}
                  onClick={() => onSelect(ticket)}
                  onKeyDown={e => {
                    if (e.key === 'Enter' || e.key === ' ') {
                      e.preventDefault()
                      onSelect(ticket)
                    }
                  }}
                  role="button"
                  tabIndex={0}
                  aria-label={`${ticket.number} ${ticket.title}`}
                  style={{
                    padding: '10px 12px', background: 'var(--surface-2)',
                    border: '1px solid var(--surface-4)', borderRadius: 10,
                    cursor: 'grab', transition: 'border-color .15s, box-shadow .15s',
                    opacity: dragging?.ticket?.id === ticket.id ? 0.5 : 1,
                  }}
                  onMouseEnter={e => { e.currentTarget.style.borderColor = col.color + '60'; e.currentTarget.style.boxShadow = `0 2px 8px ${col.color}20` }}
                  onMouseLeave={e => { e.currentTarget.style.borderColor = 'var(--surface-4)'; e.currentTarget.style.boxShadow = 'none' }}
                >
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 5 }}>
                    <span style={{ fontSize: 10, color: 'var(--text-3)', fontFamily: "'Space Mono', monospace" }}>#{ticket.number}</span>
                    {ticket.priority && (
                      <span style={{
                        fontSize: 9, fontWeight: 700, padding: '1px 6px', borderRadius: 4,
                        background: `${PRIO_COLOR[ticket.priority] || '#888'}20`,
                        color: PRIO_COLOR[ticket.priority] || 'var(--text-2)',
                      }}>
                        {PRIO_LABEL[ticket.priority] || ticket.priority}
                      </span>
                    )}
                  </div>
                  <div style={{
                    fontSize: 12, fontWeight: 600, color: 'var(--text-1)',
                    lineHeight: 1.35, marginBottom: 6,
                    overflow: 'hidden', display: '-webkit-box',
                    WebkitLineClamp: 2, WebkitBoxOrient: 'vertical',
                  }}>
                    {ticket.title}
                  </div>
                  <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                    <span style={{ fontSize: 10, color: 'var(--text-3)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', maxWidth: 110 }}>
                      {ticket.requester_name || ticket.assigned_name || '—'}
                    </span>
                    {ticket.sla_resolution_status === 'breached' && (
                      <span style={{ fontSize: 9, color: 'var(--danger)', fontWeight: 700 }}>SLA ✗</span>
                    )}
                  </div>
                </div>
              ))}
              {tickets.length === 0 && (
                <div style={{
                  padding: '20px 0', textAlign: 'center', fontSize: 11,
                  color: 'var(--text-3)', border: '1px dashed var(--surface-4)', borderRadius: 8,
                }}>
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
