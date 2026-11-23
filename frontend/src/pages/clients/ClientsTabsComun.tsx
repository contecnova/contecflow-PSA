// Tipos y constantes compartidos por las pestañas de la ficha de cliente. 23-11-2026: troceado de ClientsPageTabs sin cambio de comportamiento.
import type { LucideIcon } from 'lucide-react'
import { BookOpen, FilePen, FileText, FlaskConical, LayoutDashboard, Lightbulb, Map as MapIcon, MessageSquare, Package, Receipt, Ticket, FileBarChart, ClipboardList, Paperclip } from 'lucide-react'
import type { ClienteContrato, ClienteLicencia, ClientePortalConfig, ClienteProyecto, PortalDocumento, PortalPeticion, PortalSesionUat } from '../../services/api/tipos-alm'

// Etiqueta: clientstabs.mod_<id>.
export const MODULES: { id: string; Icon: LucideIcon }[] = [
  { id: 'dashboard',    Icon: LayoutDashboard },
  { id: 'deliverables', Icon: Package },
  { id: 'uat',          Icon: FlaskConical },
  { id: 'requests',     Icon: Lightbulb },
  { id: 'documents',    Icon: FileText },
  { id: 'roadmap',      Icon: MapIcon },
  { id: 'wiki',         Icon: BookOpen },
  { id: 'support',      Icon: Ticket },
  { id: 'messages',     Icon: MessageSquare },
]

/** Icono de cada categoría de documento del portal. */
export const DOC_ICON: Record<string, LucideIcon> = {
  general: FileText, contract: FilePen, invoice: Receipt, report: FileBarChart, specification: ClipboardList, other: Paperclip,
}

// ── Datos de las pestañas del cliente (campos según su uso aquí) ─────────────
// Respuestas de /clients/{id}/* y /portal/*/team: services/api/tipos-alm.
export type ClientProjectRow = ClienteProyecto

/** Proyecto del detalle del cliente que se pasa a las pestañas del portal. */
export interface ClientProjectRef {
  id: string
  code?: string
  name?: string
}

/** Lo que las pestañas usan del detalle del cliente (`projects` llega sin tipar). */
export interface ClientDetail {
  name?: string
  projects?: unknown[]
}

export interface ContactForm { full_name: string; email: string; phone: string; job_title: string; role: string; is_primary: boolean }

export type LinkedLicense = ClienteLicencia

export interface License { id: string; name: string }

export type LinkedContract = ClienteContrato

// Contrato: el tipo del cliente de API. Auditoria 2026-11 (#39): aqui se leia
// `title`, que el backend no envia (contract_service da `name`): el selector salia sin nombre.

export type TeamUatSession = PortalSesionUat

export type TeamFeatureRequest = PortalPeticion

export interface FeatureRequestResponseForm {
  pm_response: string
  estimated_hours: string
  estimated_cost: string
  estimated_delivery_weeks: string
  status: string
}

export type TeamPortalDocument = PortalDocumento

export type PortalConfig = ClientePortalConfig

export interface PortalConfigPayload {
  enabled_modules: string[]
  sd_without_project: boolean
  sla_tier: string | null
  max_portal_users: number
  default_language: string
  allow_profile_edit: boolean
  allow_pwd_change: boolean
}

export const CR_FECHAS = ['submitted_at', 'approved_at', 'implemented_at'] as const

export const SLA_COLOR: Record<string, string> = {
  enterprise: 'var(--purple)',
  gold: 'var(--warning)',
  silver: 'var(--text-2)',
  bronze: 'var(--warning)',
}
