import { useState } from 'react'
import type React from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useAppT } from '../../i18n/AppLangContext'
import { useToast } from '../../context/ToastContext'
import { Spinner } from '../../components/ui'
import { ticketsApi } from '../../services/api'
import { alpha } from '../../constants/theme'
import { STALE_SHORT_MS } from '../../constants/timings'
import './KanbanTicketsTab.css'

const PRIO_COLOR: Record<string, string> = { p1_critical: 'var(--danger)', p2_high: 'var(--orange)', p3_medium: 'var(--warning)', p4_low: 'var(--text-2)' }
const PRIO_LABEL: Record<string, string> = { p1_critical: 'P1', p2_high: 'P2', p3_medium: 'P3', p4_low: 'P4' }

interface KanbanTicket {
  id: string | number
  status?: string
  number?: string | number
  title?: string
  priority?: string
  requester_name?: string
  assigned_name?: string
  sla_resolution_status?: string
  [key: string]: unknown
}

const ESTADOS_DEL_TABLERO = ['new', 'assigned', 'in_progress', 'pending_client', 'pending_third', 'resolved']
const KANBAN_MAX = 200

interface DragState {
  ticket: KanbanTicket
  fromCol: string
}

export default function KanbanTicketsTab({ onSelect }: { onSelect: (ticket: KanbanTicket) => void }) {
  const t = useAppT()
  const toast = useToast()
  const qc = useQueryClient()
  const [dragging, setDragging] = useState<DragState | null>(null)
  const [dragOverCol, setDragOverCol] = useState<string | null>(null)

  const KANBAN_COLS = [
    { id: 'open',           label: t('service_desk.status_open'),           color: 'var(--accent)' },
    { id: 'in_progress',    label: t('service_desk.status_in_progress'),    color: 'var(--purple)' },
    { id: 'pending_client', label: t('service_desk.status_waiting_client'), color: 'var(--orange)' },
    { id: 'pending_third',  label: t('service_desk.status_pending_third'), color: 'var(--orange)' },
    { id: 'resolved',       label: t('service_desk.status_resolved'),       color: 'var(--success)' },
  ]

  // Auditoria 2026-11: se pedian los 200 mas recientes de cualquier estado y
  // todo lo que no tenia columna (nuevo, asignado, pero tambien cerrado y
  // cancelado) caia en «Abierto»; y soltar ahi enviaba `open`, que no es un
  // estado. Ahora se piden solo los estados de las columnas y «Abierto» son
  // los nuevos y asignados.
  const { data: tablero, isLoading } = useQuery<{ cols: Record<string, KanbanTicket[]>; total: number; vistos: number }>({
    queryKey: ['sd-tickets-kanban'],
    queryFn: () => ticketsApi.list({ page_size: KANBAN_MAX, status: ESTADOS_DEL_TABLERO.join(',') })
      .then((r: { data: unknown; meta?: { total?: number } }) => {
        const d = r.data as { tickets?: KanbanTicket[] } | KanbanTicket[]
        const tickets: KanbanTicket[] = Array.isArray(d) ? d : (d?.tickets || [])
        const cols: Record<string, KanbanTicket[]> = {}
        KANBAN_COLS.forEach(c => { cols[c.id] = [] })
        tickets.forEach(ticket => {
          const s = ticket.status ?? ''
          const col = s === 'new' || s === 'assigned' ? 'open' : s
          if (cols[col]) cols[col].push(ticket)
        })
        return { cols, total: Number(r.meta?.total ?? tickets.length), vistos: tickets.length }
      }),
    staleTime: STALE_SHORT_MS,
  })
  const raw = tablero?.cols ?? {}

  const { mutate: moveTicket } = useMutation({
    mutationFn: ({ id, status }: { id: string | number; status: string }) => ticketsApi.update(id, { status }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['sd-tickets-kanban'] }),
    onError: (e: unknown) => toast.error((e as { response?: { data?: { detail?: string } } })?.response?.data?.detail || 'Error al mover ticket'),
  })

  const onDragStart = (e: React.DragEvent, ticket: KanbanTicket, fromCol: string) => {
    setDragging({ ticket, fromCol })
    e.dataTransfer.effectAllowed = 'move'
    e.dataTransfer.setData('text/plain', String(ticket.id))
  }
  const onDragOver = (e: React.DragEvent) => { e.preventDefault(); e.dataTransfer.dropEffect = 'move' }
  const onDragEnter = (e: React.DragEvent, colId: string) => { e.preventDefault(); setDragOverCol(colId) }
  const onDragLeave = (e: React.DragEvent) => { if (!e.currentTarget.contains(e.relatedTarget as Node | null)) setDragOverCol(null) }
  const onDrop = (e: React.DragEvent, toColId: string) => {
    e.preventDefault()
    setDragOverCol(null)
    if (!dragging || dragging.fromCol === toColId) { setDragging(null); return }
    const estado = toColId === 'open' ? (dragging.ticket.assigned_to_id ? 'assigned' : 'new') : toColId
    moveTicket({ id: dragging.ticket.id, status: estado })
    setDragging(null)
  }

  if (isLoading) return <div className="katita-box-1"><Spinner /></div>

  return (
    <>
    {tablero && tablero.total > tablero.vistos && (
      <div role="status" className="katita-box-2">
        {t('service_desk.kanban_truncado').replace('{vistos}', String(tablero.vistos)).replace('{total}', String(tablero.total))}
      </div>
    )}
    <div className="katita-row-1">
      {KANBAN_COLS.map(col => {
        const tickets = raw[col.id] || []
        return (
          <div className="katita-box-7"
            key={col.id}
            data-col={col.id}
            role="presentation"
            onDragOver={onDragOver}
            onDragEnter={e => onDragEnter(e, col.id)}
            onDragLeave={onDragLeave}
            onDrop={e => onDrop(e, col.id)}
            style={{ outline: dragOverCol === col.id ? `2px solid ${col.color}` : '2px solid transparent' }}
          >
            <div className="katita-row-3" style={{ background: alpha(col.color, '18'), borderRadius: 8, border: `1px solid ${alpha(col.color, '35')}` }}>
              <div className="katita-box-8" style={{ background: col.color }} />
              <div className="katita-box-3">{col.label}</div>
              <div className="katita-txt-3" style={{ color: col.color }}>{tickets.length}</div>
            </div>
            <div className="katita-stack-1">
              {tickets.map(ticket => (
                <div className="katita-box-9"
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
                  style={{ opacity: dragging?.ticket?.id === ticket.id ? 0.5 : 1 }}
                  onMouseEnter={e => { e.currentTarget.style.borderColor = alpha(col.color, '60'); e.currentTarget.style.boxShadow = `0 2px 8px ${alpha(col.color, '20')}` }}
                  onMouseLeave={e => { e.currentTarget.style.borderColor = 'var(--surface-4)'; e.currentTarget.style.boxShadow = 'none' }}
                >
                  <div className="katita-row-2">
                    <span className="katita-txt-1">#{ticket.number}</span>
                    {ticket.priority && (
                      <span className="katita-box-10" style={{ background: alpha(PRIO_COLOR[ticket.priority] || 'var(--text-2)', '20'), color: PRIO_COLOR[ticket.priority] || 'var(--text-2)' }}>
                        {PRIO_LABEL[ticket.priority] || ticket.priority}
                      </span>
                    )}
                  </div>
                  <div className="katita-box-4">
                    {ticket.title}
                  </div>
                  <div className="u-row-between">
                    <span className="katita-box-5">
                      {ticket.requester_name || ticket.assigned_name || '—'}
                    </span>
                    {ticket.sla_resolution_status === 'breached' && (
                      <span className="katita-txt-2">SLA ✗</span>
                    )}
                  </div>
                </div>
              ))}
              {tickets.length === 0 && (
                <div className="katita-box-6">
                  {t('service_desk.kanban_no_tickets')}
                </div>
              )}
            </div>
          </div>
        )
      })}
    </div>
    </>
  )
}
