// Tipos de los datos del panel del portal de cliente. 23-11-2026: troceado de PortalDashboard sin cambio de comportamiento.
import { type PortalIcon } from './PortalUI'
import type { Umbrales } from '../../utils/umbrales'
import { type ContenidoTraducido } from './TraduccionAutomatica'

// ── Lo que devuelven los endpoints del portal que usa la pizarra ─────────────
export interface DashProject {
  id: string
  code?: string
  name: string
  status?: string
  start_date?: string | null
  end_date_planned?: string | null
}

export interface DashKpis {
  budget_total?: number
  budget_spent?: number
  milestones_done?: number
  milestones_total?: number
  deliverables_total?: number
  uat_total?: number
}

export interface DashServiceDesk {
  sla_compliance_pct?: number | null
  csat_avg?: number | null
  response_breached_open?: number
  resolution_breached_open?: number
  avg_first_response_minutes?: number | null
  avg_resolution_minutes?: number | null
}

export interface DashActivity {
  type?: string
  description?: string
  date?: string | null
}

/** `GET /portal/dashboard`. */
export interface PortalDashboardData {
  needs_project_selection?: boolean
  projects?: DashProject[]
  project?: DashProject | null
  message?: string
  kpis?: DashKpis
  service_desk?: DashServiceDesk
  recent_activity?: DashActivity[]
  /** Umbrales de semáforo de la empresa (19-11-2026; el portal no lee /settings/org-defaults). */
  umbrales?: Partial<Umbrales>
}

export interface DashMilestone {
  id: string
  name: string
  due_date?: string | null
  is_completed?: boolean
  billing_pct?: number | null
}

export interface DashDeliverable {
  id: string
  status: string
}

/** `GET /portal/project` (solo lo que usa la pizarra). */
export interface PortalProjectFull {
  milestones?: DashMilestone[]
  deliverables?: DashDeliverable[]
}

export interface DashInvoice {
  status: string
  client_approval_status?: string | null
  total?: number | string | null
  currency?: string
}

export interface DashTicket {
  status: string
  priority?: string
  ticket_type?: string
  created_at?: string | null
  csat_requested_at?: string | null
  csat_score?: number | null
}

export interface DashUat {
  status: string
  overdue?: boolean
  issues?: Array<{ status: string }>
}

export interface DashFeatureRequest {
  status: string
  client_approved?: boolean | null
}

export interface DashDocument {
  requires_signature?: boolean
  signed_by_client?: boolean
}

export interface DashAnnouncement extends ContenidoTraducido {
  id: string
  title: string
  body?: string
  type?: string
  show_to_clients?: boolean
}

export interface DashSurvey {
  status: string
}

export interface ActionItem {
  count: number
  label: string
  icon: PortalIcon
  target: string
  tone: string
}
