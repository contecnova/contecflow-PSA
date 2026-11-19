/**
 * Catálogos de código del frontend: UNA fuente por catálogo (19-11-2026).
 *
 * Auditoría de hardcodeados: había 4 listas distintas de estados de tarea
 * (TasksPage, planificador, SprintsPage, constants.json), prioridades y estados
 * duplicados con etiquetas distintas (helpers.ts, constants.json) y estados y
 * tipos ITSM repetidos en cuatro pantallas del service desk.
 *
 * Reglas:
 * - Lo que la empresa configura (tipos de proyecto, sectores, categorías de
 *   gasto, estados de proyecto y de tarea) se lee del backend con
 *   `hooks/useCatalogo`; las listas de aquí son solo el RESPALDO mientras carga
 *   o si el catálogo está vacío, y coinciden con las semillas del backend
 *   (`app/services/settings_service/catalogos.py`).
 * - Los estados de máquina (ciclo de un ticket, de un cambio…) son del código:
 *   viven aquí, con claves iguales a las del backend.
 * - Las etiquetas NO van aquí: se traducen con `etiquetaCodigo(t, 'estado', clave)`
 *   (bloque `estado` de i18n/langs/{es,en,zh}.mjs) o el bloque que se indique.
 * - Los colores son tokens del tema.
 */
import { etiquetaCodigo } from '../i18n/etiquetaCodigo'

type Traducir = Parameters<typeof etiquetaCodigo>[0]

/** Estados de tarea (todos los que entiende el backend, en orden de flujo). */
export const ESTADOS_DE_TAREA = ['backlog', 'todo', 'in_progress', 'in_review', 'blocked', 'done', 'cancelled'] as const

/** Columnas por defecto del tablero (semilla `DEFAULT_TASK_STATUSES` del backend). */
export const COLUMNAS_DE_TABLERO = ['todo', 'in_progress', 'blocked', 'in_review', 'done']

/** Prioridades (tareas, tickets, riesgos), de mayor a menor. */
export const PRIORIDADES = ['critical', 'high', 'medium', 'low'] as const

/** Estados de proyecto del backend (`ProjectStatus`). */
export const ESTADOS_DE_PROYECTO = ['planning', 'active', 'on_hold', 'paused', 'completed', 'closed', 'cancelled', 'archived'] as const

/** Ciclo de un ticket ITSM (`TicketStatus` de app/models/service_desk/_enums.py). */
export const ESTADOS_DE_TICKET = ['new', 'assigned', 'in_progress', 'pending_client', 'pending_third', 'resolved', 'closed', 'cancelled']

/** Columnas del tablero de tickets (los estados abiertos y «resuelto»). */
export const ESTADOS_DEL_TABLERO_DE_TICKETS = ESTADOS_DE_TICKET.filter(e => e !== 'closed' && e !== 'cancelled')

/** Tipos de ticket ITSM (`TicketType` del backend). */
export const TIPOS_DE_TICKET = ['incident', 'service_request', 'change', 'problem', 'question']

/** Prioridades de ticket ITSM (P1–P4). */
export const PRIORIDADES_DE_TICKET = ['p1_critical', 'p2_high', 'p3_medium', 'p4_low']

/** Color (token del tema) de cualquier estado o prioridad conocido; neutro si no se conoce. */
export const COLOR_DE_ESTADO: Record<string, string> = {
  // trabajo
  backlog: 'var(--text-3)', todo: 'var(--text-2)', in_progress: 'var(--accent)', in_review: 'var(--warning)',
  review: 'var(--warning)', blocked: 'var(--danger)', done: 'var(--success)', cancelled: 'var(--text-3)',
  // proyecto
  planning: 'var(--text-2)', active: 'var(--accent)', on_hold: 'var(--warning)', paused: 'var(--warning)',
  completed: 'var(--success)', closed: 'var(--success)', archived: 'var(--text-3)',
  // ticket / genéricos
  new: 'var(--text-2)', open: 'var(--accent)', pending: 'var(--warning)', resolved: 'var(--success)',
  assigned: 'var(--accent)', pending_client: 'var(--warning)', pending_third: 'var(--warning)',
  draft: 'var(--text-3)', submitted: 'var(--accent)', approved: 'var(--success)', rejected: 'var(--danger)',
  planned: 'var(--text-2)', delivered: 'var(--purple)', accepted: 'var(--success)', expired: 'var(--danger)',
  implemented: 'var(--success)',
  // prioridad
  critical: 'var(--danger)', high: 'var(--warning)', medium: 'var(--accent)', low: 'var(--text-3)',
  p1_critical: 'var(--danger)', p2_high: 'var(--warning)', p3_medium: 'var(--accent)', p4_low: 'var(--text-3)',
}

export const colorDeEstado = (clave: string | null | undefined) => (clave && COLOR_DE_ESTADO[clave]) || 'var(--text-3)'

/** Etiqueta traducida de un estado o prioridad (bloque i18n `estado`). */
export const etiquetaDeEstado = (t: Traducir, clave: string | null | undefined, respaldo?: string) =>
  etiquetaCodigo(t, 'estado', clave, respaldo)
