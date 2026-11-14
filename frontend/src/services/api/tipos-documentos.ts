/**
 * Respuestas de documentos (`/documents/**`), formularios públicos (`/forms/**`),
 * procesos BPMN (`/bpmn-processes/**`, `/bpmn-instances/**`) y alertas
 * operativas (`/alerts/**`), comprobadas contra el backend:
 * app/schemas/documents.py + app/services/documents_service.py +
 * app/services/reserva_de_documentos.py, app/services/public_forms_service.py,
 * app/services/bpmn_process_service.py + app/services/bpmn_engine.py y
 * app/schemas/alerts.py.
 *
 * Son `type` y no `interface` a propósito (como en tipos-sd.ts): un alias de
 * objeto se puede asignar a los tipos con índice `[k: string]: unknown`.
 *
 * Las listas llegan ya desenvueltas por el interceptor de _core.ts y los
 * `APIResponse {data, meta}` también: `res.data` es el payload.
 */
import type { ProjectListItem } from './projects'
import type { UserPublic } from './users'

// ── Documentos ─────────────────────────────────────────────────────────────

/** `DocumentCategory` (app/schemas/documents.py). */
export type CategoriaDeDocumento =
  | 'contract' | 'deliverable' | 'proposal' | 'sop' | 'requirements' | 'meeting_notes' | 'legal' | 'other'

/** `ApprovalStatus` (app/schemas/documents.py). */
export type EstadoDeAprobacionDeDocumento = 'pending' | 'approved' | 'rejected'

/** `DocumentAccessLevel` (app/schemas/documents.py). */
export type NivelDeAccesoADocumento = 'viewer' | 'editor' | 'admin'

/** `DocumentVersionOut`. En el listado (`latest_version`) no llegan `change_note` ni `s3_url`. */
export type VersionDeDocumento = {
  id: string
  version_num: number
  file_name: string
  file_size: number | null
  file_mime_type: string | null
  change_note?: string | null
  uploader_id: string
  uploader_name: string
  created_at: string
  /** Canónico; `s3_url` es el mismo valor, por compatibilidad. */
  download_url: string | null
  s3_url?: string | null
}

/** reserva_de_documentos.para_mostrar: la reserva vigente (check-out) o `null`. */
export type ReservaDeDocumento = {
  user_id: string
  user_name: string | null
  at: string | null
  expires_at: string | null
  /** Solo en el detalle y en check-out (para_mostrar); los listados mandan `vigente`, sin él. */
  mine?: boolean
} | null

/** Decisión de un paso (documents_service._serialize_approval_request). */
export type DecisionDeAprobacionDeDocumento = {
  step_order: number
  approver_id: string | null
  approver_name: string | null
  decision: string
  note: string | null
  decided_at: string | null
}

/** documents_service._serialize_approval_request. */
export type SolicitudDeAprobacionDeDocumento = {
  id: string
  status: string
  workflow_name: string | null
  total_steps: number
  current_step: number | null
  current_step_name: string | null
  current_approver_type: string | null
  current_approver_role: string | null
  current_approver_user_id: string | null
  current_approver_name: string | null
  requested_at: string | null
  completed_at: string | null
  decisions: DecisionDeAprobacionDeDocumento[]
}

/**
 * `DocumentListOut` (GET /documents, /documents/by-project, /by-task) y
 * documents_service.serialize_doc_list_item (GET /documents/by-ticket, sin
 * esquema: no trae `updated_at`).
 */
export type DocumentoEnLista = {
  id: string
  title: string
  category: CategoriaDeDocumento
  is_archived: boolean
  requires_approval: boolean
  approval_status: EstadoDeAprobacionDeDocumento
  created_by_name: string
  created_at: string
  updated_at?: string | null
  latest_version: VersionDeDocumento | null
  checkout: ReservaDeDocumento
  tags: string[]
  version_count: number
}

/** `DocumentPermissionOut`. */
export type PermisoDeDocumento = {
  id: string
  user_id: string | null
  user_name: string | null
  role: string | null
  department: string | null
  access_level: NivelDeAccesoADocumento
  granted_by_name: string | null
  granted_at: string
  expires_at: string | null
}

/** `DocumentOut` (documents_service.serialize_document): detalle, alta, edición, aprobación y subida. */
export type Documento = {
  id: string
  title: string
  description: string | null
  category: CategoriaDeDocumento
  requires_approval: boolean
  project_id: string | null
  client_id: string | null
  milestone_id: string | null
  approval_status: EstadoDeAprobacionDeDocumento
  is_archived: boolean
  created_by: string
  created_by_name: string
  updated_by: string | null
  updated_by_name: string | null
  approved_by: string | null
  approved_by_name: string | null
  approved_at: string | null
  created_at: string
  updated_at: string | null
  ai_summary: string | null
  versions: VersionDeDocumento[]
  permissions: PermisoDeDocumento[]
  tags: string[]
  approval_request: SolicitudDeAprobacionDeDocumento | null
  checkout: ReservaDeDocumento
}

/** DELETE /documents/{id}. */
export type DocumentoArchivado = { status: 'archived' }

/** DELETE /documents/{id}/permissions/{perm_id}. */
export type PermisoRevocado = { status: 'revoked' }

/** POST /documents/{id}/checkin. */
export type DocumentoLiberado = { checkout: null }

/** POST /documents/{id}/ai-summary. */
export type ResumenIaDeDocumento = { document_id: string; summary: string }

// ── Formularios públicos ───────────────────────────────────────────────────

/** public_forms_service.serialize_form. */
export type FormularioPublico = {
  id: string
  name: string
  description: string | null
  form_type: 'ticket' | 'task'
  token: string
  is_active: boolean
  target_project_id: string | null
  target_group_id: string | null
  default_priority: string
  default_category: string | null
  success_message: string | null
  notify_emails: string[]
  submission_count: number
  created_by: string
  created_at: string | null
  /** Ruta relativa (`/intake/{token}`). */
  public_url: string
}

/** GET /forms/{id}/submissions (endpoints/public_forms.py list_submissions). */
export type EnvioDeFormulario = {
  id: string
  submitter_name: string | null
  submitter_email: string | null
  subject: string
  description: string | null
  priority: string | null
  category: string | null
  created_entity_id: string | null
  created_entity_type: string | null
  submitted_at: string | null
}

// ── Procesos BPMN ──────────────────────────────────────────────────────────

/** bpmn_process_service.serialize_version (sin `bpmn_xml` en las listas de versiones). */
export type VersionDeProcesoBpmn = {
  id: string
  process_id: string
  version: number
  is_published: boolean
  notes: string | null
  published_at: string | null
  created_at: string | null
  created_by_user_id: string | null
  bpmn_xml?: string
}

/** bpmn_process_service.serialize_process. `versions` solo en alta, duplicado y detalle. */
export type ProcesoBpmn = {
  id: string
  key: string
  name: string
  description: string | null
  category: string
  icon: string | null
  owner: string | null
  sla: string | null
  source_kind: string | null
  source_ref: string | null
  latest_version: number | null
  status: string
  is_seeded: boolean
  is_active: boolean
  created_at: string | null
  updated_at: string | null
  versions?: VersionDeProcesoBpmn[]
}

/** GET /bpmn-processes/{id}: el proceso con sus versiones y la última con su XML. */
export type ProcesoBpmnDetalle = ProcesoBpmn & {
  versions: VersionDeProcesoBpmn[]
  latest: VersionDeProcesoBpmn | null
}

/** bpmn_engine.serializar_paso. */
export type PasoDeInstanciaBpmn = {
  id: string
  instance_id: string
  element_id: string
  element_type: string
  name: string | null
  status: string
  candidate_role: string | null
  due_at: string | null
  completed_by_user_id: string | null
  result: unknown
  created_at: string | null
  completed_at: string | null
  human: boolean
}

/** GET /bpmn-instances/inbox: el paso más el proceso y las variables de su instancia. */
export type PasoDeBandejaBpmn = PasoDeInstanciaBpmn & {
  process_id: string
  process_name: string | null
  variables: Record<string, unknown>
}

/** bpmn_engine.serializar. El listado no trae `steps` y añade `process_name`. */
export type InstanciaBpmn = {
  id: string
  process_id: string
  version: number
  status: string
  variables: Record<string, unknown>
  error: string | null
  started_by_user_id: string | null
  started_at: string | null
  ended_at: string | null
  active_steps: string[]
  steps?: PasoDeInstanciaBpmn[]
  process_name?: string | null
}

// ── Alertas operativas ─────────────────────────────────────────────────────

/** `AlertOut` (app/schemas/alerts.py) con `unit` (la de Ajustes → Alertas). */
export type Alerta = {
  id: string
  alert_type: string
  severity: 'info' | 'warning' | 'critical'
  title: string
  description: string | null
  value: number | null
  threshold: number | null
  unit: string | null
  user: UserPublic | null
  project: ProjectListItem | null
  is_read: boolean
  is_resolved: boolean
  created_at: string
}

/** POST /alerts/run. */
export type EjecucionDeAlertas = { message: string }
