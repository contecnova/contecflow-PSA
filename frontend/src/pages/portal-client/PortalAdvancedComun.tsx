// Tipos y distintivo de estado compartidos por las secciones avanzadas del portal de cliente. 23-11-2026: troceado de PortalAdvancedSections sin cambio de comportamiento.
import { useEtiquetaEstado } from './portalClientContext'
import { type ContenidoTraducido } from './TraduccionAutomatica'
import { PortalBadge } from './PortalUI'

// ── Status helpers ───────────────────────────────────────────────────────────
const STATUS_TONE: Record<string, string> = {
  pending: 'warning', new: 'default', reviewing: 'accent', estimated: 'warning',
  approved: 'success', rejected: 'danger', passed: 'success', conditional: 'success',
  failed: 'danger', in_progress: 'accent', planned: 'default', delivered: 'accent',
  accepted: 'success', closed: 'default', resolved: 'success', cancelled: 'default',
  paid: 'success', overdue: 'danger', sent: 'warning', draft: 'default',
}

export function StatusBadge({ status }: { status?: string | null }) {
  const etiqueta = useEtiquetaEstado()
  if (!status) return null
  return <PortalBadge tone={STATUS_TONE[status] || 'default'}>{etiqueta(status)}</PortalBadge>
}

// ── Respuestas del portal ────────────────────────────────────────────────────
// Campos según los serializadores de app/services/client_portal_service
// (serializacion.py, facturas.py, panel.py, wiki_y_encuestas.py).

/** `_uat_test_cases_out`. */
interface UatTestCase {
  id: string
  title: string
  steps?: string | null
  expected_result?: string | null
  actual_result?: string | null
  status: string
  notes?: string | null
  order?: number
}

/** `_uat_issues_out`. */
interface UatIssue {
  id: string
  title: string
  description?: string | null
  severity?: string
  status: string
  steps_to_reproduce?: string | null
}

/** `uat_out`. */
export interface UatSession {
  id: string
  code?: string
  title: string
  description?: string | null
  test_environment?: string | null
  test_credentials?: string | null
  status: string
  deadline?: string | null
  overdue?: boolean | null
  test_cases?: UatTestCase[]
  issues?: UatIssue[]
  stats?: { total: number; passed: number; failed: number; pending: number }
}

/** `fr_out` (+ `can_edit_by_client` que añade el listado). */
export interface FeatureRequest {
  id: string
  code?: string
  project_id?: string | null
  project_name?: string
  title: string
  description?: string | null
  business_justification?: string | null
  affected_area?: string | null
  priority?: string
  status: string
  pm_response?: string | null
  estimated_hours?: number | null
  estimated_cost?: number | null
  estimated_delivery_weeks?: number | null
  client_approved?: boolean | null
  client_approved_at?: string | null
  submitted_at?: string | null
  can_edit_by_client?: boolean
  cr_status?: string | null
  cr_status_label?: string | null
  cr_status_color?: string | null
}

/** Formulario de alta/edición de una solicitud. */
export interface FeatureRequestForm {
  title: string
  description: string
  business_justification: string
  affected_area: string
  priority: string
  project_id: string
}

/** Proyecto tal como viene en la sesión del cliente (`client.projects`). */
export interface ClientProject {
  id: string
  name?: string
  code?: string
}

/** Conversación de `/portal/collaboration/conversations`. */
export interface CollabConversation {
  id: string
  title?: string
}

/** Mensaje de `/portal/collaboration/conversations/{id}/messages`. */
export interface CollabMessage {
  id: string
  body: string
  author_name?: string | null
  client_user_id?: string | number | null
  sent_at: string
}

/** Factura de `list_client_invoices` (facturas.py). */
export interface ClientInvoice {
  id: string
  number?: string | null
  client_name?: string | null
  status: string
  subtotal?: number | null
  tax_amount?: number | null
  total?: number | null
  currency?: string | null
  issue_date?: string | null
  due_date?: string | null
  client_approval_status?: string | null
}

export interface RoadmapMilestone {
  id: string
  name: string
  due_date?: string | null
  is_completed?: boolean
  billing_pct?: number | null
}

export interface RoadmapDeliverable {
  id: string
  name: string
  format?: string | null
  status: string
  planned_date?: string | null
}

/** `GET /portal/project` (panel.py), lo que pinta el roadmap. */
export interface ClientProjectDetail {
  milestones?: RoadmapMilestone[]
  deliverables?: RoadmapDeliverable[]
}

/** `doc_out`. */
export interface ClientDocument {
  id: string
  title: string
  description?: string | null
  category?: string | null
  file_url?: string | null
  file_name?: string | null
  requires_signature?: boolean
  signed_by_client?: boolean
  signed_at?: string | null
  created_at?: string
}

// 16-11-2026: título y bloques pueden llegar traducidos automáticamente
// (`translated_from` + `original`); el contenido puede ser texto (páginas antiguas).
export interface WikiPageSummary extends ContenidoTraducido {
  id: string
  title: string
  updated_at?: string | null
}

interface WikiBlock extends ContenidoTraducido {
  type?: string
  content?: string
}

export interface WikiPageDetail extends WikiPageSummary {
  content?: WikiBlock[] | string
}

export interface KbArticle {
  id: string
  title: string
  summary?: string | null
  tags?: string | null
  view_count?: number
  helpful_count?: number
}
