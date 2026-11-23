/**
 * Estados del ticket del Service Desk (23-11-2026, auditoría 04b «Hardcode:
 * estados como cadena»). Mismos valores que `TicketStatus`
 * (`app/models/service_desk/_enums.py`); las etiquetas salen de i18n
 * (`service_desk.status_<estado>`).
 */
export const ESTADO_TICKET = {
  nuevo: 'new',
  asignado: 'assigned',
  enCurso: 'in_progress',
  pendienteCliente: 'pending_client',
  pendienteTercero: 'pending_third',
  resuelto: 'resolved',
  cerrado: 'closed',
  cancelado: 'cancelled',
} as const

export type EstadoTicket = typeof ESTADO_TICKET[keyof typeof ESTADO_TICKET]

/** Resuelto o cerrado: el trabajo está hecho (lecciones, cierre de SLA). */
export const ESTADOS_TICKET_RESUELTOS: readonly string[] = [ESTADO_TICKET.resuelto, ESTADO_TICKET.cerrado]
/** Terminados: ya no admiten acciones de trabajo (empezar, cerrar…). */
export const ESTADOS_TICKET_TERMINADOS: readonly string[] = [...ESTADOS_TICKET_RESUELTOS, ESTADO_TICKET.cancelado]
