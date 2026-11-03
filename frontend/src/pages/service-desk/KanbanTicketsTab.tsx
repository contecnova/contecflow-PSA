import { useState } from 'react'
import type React from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useAppT } from '../../i18n/AppLangContext'
import { useToast } from '../../context/ToastContext'
import { Spinner } from '../../components/ui'
import { ticketsApi } from '../../services/api'
import { alpha } from '../../constants/theme'

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
    { id: 'open',           label: t('service_desk.status_open'),           color: '#4f8ef7' },
    { id: 'in_progress',    label: t('service_desk.status_in_progress'),    color: '#7F77DD' },
    { id: 'pending_client', label: t('service_desk.status_waiting_client'), color: '#fb923c' },
    { id: 'pending_third',  label: t('service_desk.status_pending_third'), color: '#fb923c' },
    { id: 'resolved',       label: t('service_desk.status_resolved'),       color: '#34d399' },
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
    staleTime: 30000,
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

  if (isLoading) return <div style={{ padding: 40, textAlign: 'center' }}><Spinner /></div>

  return (
    <>
    {tablero && tablero.total > tablero.vistos && (
      <div role="status" style={{ fontSize: 'var(--text-sm)', color: 'var(--warning)', marginBottom: 8 }}>
        {t('service_desk.kanban_truncado').replace('{vistos}', String(tablero.vistos)).replace('{total}', String(tablero.total))}
      </div>
    )}
    <div style={{ display: 'flex', gap: 12, overflowX: 'auto', paddingBottom: 16, minHeight: 400 }}>
      {KANBAN_COLS.map(col => {
        const tickets = raw[col.id] || []
        return (
          <div
            key={col.id}
            data-col={col.id}
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
              padding: '8px 12px', background: alpha(col.color, '18'),
              borderRadius: 8, border: `1px solid ${alpha(col.color, '35')}`,
            }}>
              <div style={{ width: 8, height: 8, borderRadius: '50%', background: col.color, flexShrink: 0 }} />
              <div style={{ fontSize: "var(--text-sm)", fontWeight: 700, color: 'var(--text-1)', flex: 1 }}>{col.label}</div>
              <div style={{ fontSize: "var(--text-xs)", color: col.color, fontWeight: 700, fontFamily: 'var(--font-mono)' }}>{tickets.length}</div>
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
                  onMouseEnter={e => { e.currentTarget.style.borderColor = alpha(col.color, '60'); e.currentTarget.style.boxShadow = `0 2px 8px ${alpha(col.color, '20')}` }}
                  onMouseLeave={e => { e.currentTarget.style.borderColor = 'var(--surface-4)'; e.currentTarget.style.boxShadow = 'none' }}
                >
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 5 }}>
                    <span style={{ fontSize: "var(--text-2xs)", color: 'var(--text-3)', fontFamily: 'var(--font-mono)' }}>#{ticket.number}</span>
                    {ticket.priority && (
                      <span style={{
                        fontSize: "var(--text-3xs)", fontWeight: 700, padding: '1px 6px', borderRadius: 4,
                        background: alpha(PRIO_COLOR[ticket.priority] || 'var(--text-2)', '20'),
                        color: PRIO_COLOR[ticket.priority] || 'var(--text-2)',
                      }}>
                        {PRIO_LABEL[ticket.priority] || ticket.priority}
                      </span>
                    )}
                  </div>
                  <div style={{
                    fontSize: "var(--text-sm)", fontWeight: 600, color: 'var(--text-1)',
                    lineHeight: 1.35, marginBottom: 6,
                    overflow: 'hidden', display: '-webkit-box',
                    WebkitLineClamp: 2, WebkitBoxOrient: 'vertical',
                  }}>
                    {ticket.title}
                  </div>
                  <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                    <span style={{ fontSize: "var(--text-2xs)", color: 'var(--text-3)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', maxWidth: 110 }}>
                      {ticket.requester_name || ticket.assigned_name || '—'}
                    </span>
                    {ticket.sla_resolution_status === 'breached' && (
                      <span style={{ fontSize: "var(--text-3xs)", color: 'var(--danger)', fontWeight: 700 }}>SLA ✗</span>
                    )}
                  </div>
                </div>
              ))}
              {tickets.length === 0 && (
                <div style={{
                  padding: '20px 0', textAlign: 'center', fontSize: "var(--text-xs)",
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
    </>
  )
}
