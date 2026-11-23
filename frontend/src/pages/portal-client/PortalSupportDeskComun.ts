// Tonos, iconos y tipos del soporte del portal de cliente. 23-11-2026: troceado de PortalSupportDesk sin cambio de comportamiento.
import { Bug, ClipboardList, HelpCircle, GitBranch } from 'lucide-react'
import { type ContenidoTraducido } from './TraduccionAutomatica'

export const PRIORITY_TONE: Record<string, string> = {
  p1_critical: 'danger',
  p2_high:     'orange',
  p3_medium:   'warning',
  p4_low:      'default',
}

export const PRIORITY_COLORS: Record<string, string> = {
  p1_critical: 'var(--danger)',
  p2_high:     'var(--orange)',
  p3_medium:   'var(--warning)',
  p4_low:      'var(--text-2)',
}

export const STATUS_TONE: Record<string, string> = {
  new: 'default', assigned: 'accent', in_progress: 'accent',
  pending_client: 'warning', pending_third: 'warning',
  resolved: 'success', closed: 'default', cancelled: 'default',
}

export const TYPE_ICON: Record<string, typeof Bug> = {
  incident: Bug, service_request: ClipboardList, change: GitBranch, question: HelpCircle,
}

export interface Ticket {
  id: string
  number?: string
  title?: string
  ticket_type?: string
  status?: string
  status_label?: string
  approval_status?: string | null
  priority?: string
  priority_label?: string
  created_at?: string
  assigned_to_name?: string
  csat_requested_at?: string
  csat_score?: number
}

interface TicketComment {
  id: string
  author_type?: string
  author_name?: string
  created_at?: string
  body?: string
  is_public?: boolean
  /** 17-11-2026: editado o retirado en su canal (Slack). */
  edited_at?: string | null
  retracted_at?: string | null
}

interface TicketHistory {
  changed_at?: string
  changed_by?: string
  field?: string
  old_value?: unknown
  new_value?: unknown
}

export interface TicketDetail extends Ticket {
  client_name?: string
  service_item_name?: string
  ci_name?: string
  description?: string
  resolution?: string
  sla_resolution_due?: string
  dynamic_fields?: Record<string, unknown>
  comments?: TicketComment[]
  history?: TicketHistory[]
}

// 16-11-2026: avisos, catálogo y etiquetas de los formularios dinámicos pueden
// llegar traducidos automáticamente (`translated_from` + `original`).
interface CatalogService extends ContenidoTraducido { id: string; name?: string; sla_resolution_hours?: number }

export interface CatalogGroup extends ContenidoTraducido { id: string; icon?: string; name?: string; services: CatalogService[] }

export interface KbArticle { id: string; title?: string; summary?: string; tags?: string; view_count?: number; helpful_count?: number }

export interface Announcement extends ContenidoTraducido {
  id: string
  type?: string
  title?: string
  body?: string
  show_to_clients?: boolean
  starts_at?: string
  ends_at?: string
}

export interface ContextItem { id?: string; name?: string; code?: string; [k: string]: unknown }

export interface ContextOptions { clients: ContextItem[]; services: ContextItem[]; cis: ContextItem[] }

export interface DynamicField extends ContenidoTraducido {
  id: string
  label?: string
  type?: string
  required?: boolean
  options?: string[]
  visible_when?: { field?: string; equals?: unknown; in?: unknown[] }
  data_source?: string
  data_attribute?: string
}

interface RoutingHint { when?: { field?: string; equals?: unknown; in?: unknown[] }; set?: Record<string, unknown> }

export interface DynamicRules { fields?: DynamicField[]; routing_hints?: RoutingHint[] }
