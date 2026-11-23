// Tipos y utilidades compartidos por el detalle de ticket y sus modales. 23-11-2026: troceado de TicketDetail sin cambio de comportamiento.
import type { CSSProperties } from 'react'
import { etiquetaCodigo } from '../../i18n/etiquetaCodigo'
import type { SdAprobacionDeTicket, SdRespuestaRapida, SdSugerenciaIA, SdTicketComentario, SdTicketDetalle, SdTicketEnlace, SdTicketHistorial } from '../../services/api/tipos-sd'

/** Clases de los formularios (locales a la pantalla). */
export const LS = 'tkd-label'

/** Color del dato (estado de SLA, de aprobacion) para las clases `.tkd-*` que lo leen. */
export const colorVar = (c: string) => ({ '--tkd-c': c } as CSSProperties)

export type TicketShape = SdTicketDetalle

export type TicketLink = SdTicketEnlace

export type TicketComment = SdTicketComentario

export type TicketHistoryEntry = SdTicketHistorial

/** Contrato de ALM usado como contrato de soporte (UC). */
export interface UcContract { id: string; title?: string; vendor_name?: string | null; status?: string; response_hours?: number | null; resolution_hours?: number | null }

/** Una línea del historial con el campo y los valores legibles (estado y
 *  prioridad traducidos), no los códigos del servidor. */
const CLAVE_ESTADO: Record<string, string> = {
  new: 'status_new', assigned: 'status_assigned', in_progress: 'status_in_progress',
  pending_client: 'status_waiting_client', pending_third: 'status_pending_third',
  resolved: 'status_resolved', closed: 'status_closed', cancelled: 'status_cancelled',
}

const CLAVE_PRIORIDAD: Record<string, string> = { p1_critical: 'priority_p1', p2_high: 'priority_p2', p3_medium: 'priority_p3', p4_low: 'priority_p4' }

export function lineaDeHistorial(t: (k: string, p?: Record<string, unknown>) => string, h: TicketHistoryEntry): string {
  const campo = h.field ?? ''
  const valor = (v?: string | null) => {
    if (v == null || v === '') return '—'
    if (campo === 'status' && CLAVE_ESTADO[v]) return t(`service_desk.${CLAVE_ESTADO[v]}`)
    if (campo === 'priority' && CLAVE_PRIORIDAD[v]) return t(`service_desk.${CLAVE_PRIORIDAD[v]}`)
    return v
  }
  return `${etiquetaCodigo(t, 'ticketdetail.campo', campo)}: ${valor(h.old_value)} → ${valor(h.new_value)}`
}

// ── CannedResponsePicker ──────────────────────────────────────────────────────
export type CannedResponse = SdRespuestaRapida

export type Aprobacion = SdAprobacionDeTicket

export type Sugerencia = SdSugerenciaIA
