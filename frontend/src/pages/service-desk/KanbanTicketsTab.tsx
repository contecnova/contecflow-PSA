/**
 * KanbanTicketsTab — tablero de tickets por estado (arrastrar y soltar).
 *
 * 16-11-2026 (pasada de diseño): las columnas ocupan todo el ancho; la
 * prioridad es un `StatusBadge`; el resalte al pasar el ratón va en CSS (antes
 * se pintaba a mano en onMouseEnter/Leave); «SLA ✗» pasa a «SLA vencido» y el
 * error al mover se traduce (era un texto fijo en castellano).
 */
import { type CSSProperties, useState } from 'react'
import type React from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useAppT } from '../../i18n/AppLangContext'
import { useToast } from '../../context/ToastContext'
import { Spinner } from '../../components/ui'
import StatusBadge from '../../components/ui/StatusBadge'
import { ticketsApi } from '../../services/api'
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
    onError: (e: unknown) => toast.error((e as { response?: { data?: { detail?: string } } })?.response?.data?.detail || t('kanbantickets.error_mover')),
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

  if (isLoading) return <div className="kt-loading"><Spinner /></div>

  return (
    <>
    {tablero && tablero.total > tablero.vistos && (
      <div role="status" className="kt-aviso">
        {t('service_desk.kanban_truncado').replace('{vistos}', String(tablero.vistos)).replace('{total}', String(tablero.total))}
      </div>
    )}
    <div className="kt-board">
      {KANBAN_COLS.map(col => {
        const tickets = raw[col.id] || []
        return (
          <div className={`kt-col${dragOverCol === col.id ? ' kt-col--over' : ''}`}
            key={col.id}
            data-col={col.id}
            role="presentation"
            onDragOver={onDragOver}
            onDragEnter={e => onDragEnter(e, col.id)}
            onDragLeave={onDragLeave}
            onDrop={e => onDrop(e, col.id)}
            style={{ '--kt-col': col.color } as CSSProperties}
          >
            <div className="kt-col__head">
              <span className="kt-col__dot" aria-hidden="true" />
              <span className="kt-col__title">{col.label}</span>
              <span className="kt-col__count">{tickets.length}</span>
            </div>
            <div className="kt-col__list">
              {tickets.map(ticket => (
                <div className={`kt-card${dragging?.ticket?.id === ticket.id ? ' kt-card--dragging' : ''}`}
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
                >
                  <div className="kt-card__top">
                    <span className="kt-card__number">{ticket.number}</span>
                    {ticket.priority && (
                      <StatusBadge color={PRIO_COLOR[ticket.priority] || 'var(--text-2)'} caps={false}>
                        {PRIO_LABEL[ticket.priority] || ticket.priority}
                      </StatusBadge>
                    )}
                  </div>
                  <div className="kt-card__title">{ticket.title}</div>
                  <div className="kt-card__foot">
                    <span className="kt-card__who">{ticket.requester_name || ticket.assigned_name || '—'}</span>
                    {ticket.sla_resolution_status === 'breached' && (
                      <StatusBadge kind="danger" caps={false}>{t('kanbantickets.sla')}</StatusBadge>
                    )}
                  </div>
                </div>
              ))}
              {tickets.length === 0 && (
                <div className="kt-col__empty">{t('service_desk.kanban_no_tickets')}</div>
              )}
            </div>
          </div>
        )
      })}
    </div>
    </>
  )
}
