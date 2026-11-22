/**
 * services/api/demanda.ts — motor de flujos de demanda (22-11-2026), lado del operador.
 *
 * Rutas `/api/v1/demand/...` (docs/FLUJO_DE_DEMANDA.md, sección 4). El interceptor
 * de `_core` ya desenvuelve `{ data, meta }` y `{ items, meta }`; algunas listas
 * pueden llegar como `{ items }` sin `meta`, de ahí `lista()`.
 * El portal del cliente usa su propio cliente (`CLIENT_API`, PortalDemandas.tsx).
 */
import api from './_core'

const D = <T,>(p: Promise<{ data: unknown }>) => p.then(r => r.data as T)

/** Texto en los tres idiomas del operador. */
export type TextoI18n = { es?: string; en?: string; zh?: string }

// ── Estados ─────────────────────────────────────────────────────────────────
export type EstadoDeDemanda = 'draft' | 'in_progress' | 'pending_info' | 'on_hold' | 'approved' | 'rejected' | 'withdrawn' | 'done'
export const ESTADOS_DE_DEMANDA: EstadoDeDemanda[] = ['draft', 'in_progress', 'pending_info', 'on_hold', 'approved', 'rejected', 'withdrawn', 'done']
export type EstadoSla = 'ok' | 'warning' | 'breached' | 'paused' | null
export type EstadoDeFase = 'done' | 'current' | 'pending' | 'skipped'

// ── Definición del flujo (JSON) ─────────────────────────────────────────────
export interface AsignadoDePaso { type: string; value?: string; label?: string }
export interface PasoDeFlujo {
  key: string; name: TextoI18n; mode: 'task' | 'approval' | string
  assignee: AsignadoDePaso; quorum?: 'any' | 'all' | 'majority' | string; optional?: boolean
}
export interface AvisoDeFlujo { event: string; to: { type: string; value?: string } }
export interface CondicionDePuerta { field: string; op: string; value: unknown }
export interface PuertaDeFase {
  conditions: CondicionDePuerta[]; match: 'any' | 'all' | string; use_policies?: boolean
  if_true: string; if_false: string; allow_bypass?: boolean
}
export interface FaseDeFlujo {
  key: string; name: TextoI18n; kind: string; parallel?: boolean
  steps: PasoDeFlujo[]; decisions: string[]
  on_approve: string; on_reject: string; return_targets: string[]
  required_fields: string[]; client_editable?: boolean; internal_editable?: string[]
  lock_client_from_here?: boolean
  sla_hours?: number | null; sla_warn_pct?: number | null; pause_on_info?: boolean
  segregation?: { not_requester?: boolean; not_actor_of_phases?: string[] }
  /** Fase condicional: si no se cumple, se salta sola. */
  condition?: { conditions: CondicionDePuerta[]; match: 'any' | 'all' | string; use_policies?: boolean; policy_tag?: string }
  /** Con el plazo vencido decide también este responsable. */
  escalation?: { to: AsignadoDePaso }
  /** Destino por decisión (next | clave de fase | end:approved | end:rejected). */
  targets?: { approve?: string; reject?: string; hold?: string }
  /** Campos que nadie edita en esta fase. */
  locked_fields?: string[]
  documents_tag?: string | null; notify?: AvisoDeFlujo[]
  gate?: PuertaDeFase; committee?: { executive_summary?: boolean | PlantillaDeResumen }
}
export interface PlantillaDeResumen { title?: TextoI18n; fields?: string[]; opinion_phases?: string[]; include_history?: boolean }
export interface AccionDeCierre { action: string; when: 'approved' | 'rejected' | 'any' | string; params?: Record<string, unknown> }
export interface OpcionDeCampo { value: string; label: TextoI18n }
export interface CampoDeFlujo {
  key: string; label: TextoI18n; type: string; options?: OpcionDeCampo[]
  critical?: boolean; owner: 'client' | 'internal' | string; client_visible?: boolean; policy_field?: string | null
}
export interface DefinicionDeFlujo {
  fields: CampoDeFlujo[]; submit_required: string[]; phases: FaseDeFlujo[]
  execution: string[]; notify?: AvisoDeFlujo[]; on_close_actions?: AccionDeCierre[]
}
export interface ErrorDeDefinicion { path: string; code: string }
export interface PlantillaDeFlujo { key: string; name: string; description: string }
export interface PasoDeRecorrido { phase: string; name: string; kind: string; skipped: boolean; decision: string | null; reasons: string[] }
export interface SimulacionDeFlujo { errors: ErrorDeDefinicion[]; path: PasoDeRecorrido[]; end: string | null; warnings: string[] }
export interface NodoDeDiagrama { id: string; label: string; kind: string; parallel?: boolean; steps?: number; conditional?: boolean }
export interface AristaDeDiagrama { from: string; to: string; label: string }
export interface DiagramaDeFlujo { nodes: NodoDeDiagrama[]; edges: AristaDeDiagrama[] }

// ── Flujos y tipos (configuración) ──────────────────────────────────────────
export interface FlujoDeDemanda {
  id: string; name: string; version: number; is_active: boolean
  definition?: DefinicionDeFlujo; updated_at?: string
}
export interface TipoDeDemanda {
  id: string; key: string; name: string; name_i18n?: TextoI18n
  channels: string[]; requires_project: boolean; allows_standalone: boolean
  scopes?: string[]; description?: string | null
  flow_id: string | null; flow_name?: string | null; is_active: boolean
}
export interface OpcionValorEtiqueta { value: string; label: string }
export interface CatalogoDeDemanda {
  assignee_types: string[]; decisions: string[]; phase_kinds: string[]; field_types: string[]
  document_tags: string[]; notify_events: string[]; condition_ops: string[]
  roles: OpcionValorEtiqueta[]; groups: OpcionValorEtiqueta[]; users: OpcionValorEtiqueta[]
  approval_workflows: OpcionValorEtiqueta[]; execution_modes: string[]; channels: string[]
  notify_targets?: string[]; quorums?: string[]; step_modes?: string[]; close_actions?: string[]; scopes?: string[]
  templates?: PlantillaDeFlujo[]
}

// ── Expediente ──────────────────────────────────────────────────────────────
export interface ResumenDeDemanda {
  id: string; code: string; title: string; type_key: string; type_name: string; origin: string
  status: EstadoDeDemanda; current_phase_key: string | null; current_phase_name: string | null
  project_id: string | null; project_name: string | null; standalone: boolean
  requester_name: string | null; created_at: string; submitted_at: string | null
  sla_due_at: string | null; sla_state: EstadoSla; closed_at: string | null
}
export interface CampoDeExpediente {
  key: string; label: string; type: string; options?: Array<{ value: string; label: string }>
  critical: boolean; owner: string; editable: boolean; required_now: boolean
}
export interface PasoDeExpediente {
  key: string; name: string; mode: string; assignee_label: string | null; status: string
  decided_by_name: string | null; decided_at: string | null; note: string | null
  assignee?: { type: string; value?: string; label?: string } | null
  votes: unknown; can_decide: boolean; decisions: string[]
}
export interface FaseDeExpediente {
  key: string; name: string; kind: string; status: EstadoDeFase
  entered_at: string | null; sla_due_at: string | null; steps: PasoDeExpediente[]
  /** Opcional: si el servidor lo da, se limita a ellas el selector de «devolver». */
  return_targets?: string[]
}
export interface TransicionDeExpediente {
  id: string; from_phase: string | null; to_phase: string | null; step_key: string | null
  seq?: number; is_bypass?: boolean
  decision: string; actor_name: string | null; actor_kind: 'user' | 'client' | 'system'
  actor_role: string | null; justification: string | null; created_at: string
}
export interface VersionDeCampo {
  field: string; value: unknown; source: 'client' | 'requester' | 'internal'; phase_key: string | null
  author_name: string | null; created_at: string
}
export interface DocumentoDeExpediente {
  id: string; tag: string; phase_key: string | null; file_name: string; size: number; mime: string
  uploaded_by_name: string | null; is_annex: boolean; internal?: boolean; personal_data: boolean; created_at: string
}
export interface ComentarioDeExpediente {
  id: string; body: string; internal: boolean; phase_key: string | null
  author_name: string | null; author_kind: string; created_at: string
}
export interface DetalleDeDemanda extends ResumenDeDemanda {
  flow: { id: string; name: string; version: number }
  data: Record<string, unknown>
  fields: CampoDeExpediente[]
  phases: FaseDeExpediente[]
  transitions: TransicionDeExpediente[]
  field_versions: VersionDeCampo[]
  documents: DocumentoDeExpediente[]
  comments: ComentarioDeExpediente[]
  committee: { required: boolean; date: string | null; reasons: string[] }
  result: { kind: string | null; project_id: string | null; change_request_id: string | null; proposal_id: string | null; actions?: Array<{ action: string; ok: boolean; id?: string | null; error?: string | null; at?: string }> } | null
  actions: {
    can_edit_fields: boolean; can_submit: boolean; can_comment: boolean; can_upload: boolean; can_withdraw: boolean
    can_schedule_committee: boolean; can_generate_summary: boolean; can_execute: boolean
  }
  client_locked: boolean
  metrics: { effective_hours: number | null; paused_hours: number | null }
}

/** Métricas: la forma exacta la decide el servidor; se enseña lo que llegue. */
export type MetricasDeDemanda = Record<string, unknown>

export interface FiltrosDeDemanda { status?: string; phase?: string; type?: string; pending_for_me?: boolean; q?: string }
export interface NuevaDemanda {
  type_key: string; title: string; project_id?: string | null; scope_kind?: string; scope_ref_id?: string | null
  client_id?: string | null; requester_user_id?: string | null; data: Record<string, unknown>; submit: boolean
}
export interface CampoDeTipo { key: string; label: string; type: string; options?: Array<{ value: string; label: string }>; critical?: boolean }
export interface TipoParaSolicitar {
  key: string; name: string; scopes?: string[]; requires_project?: boolean; allows_standalone?: boolean
  fields: CampoDeTipo[]; submit_required: string[]; phases?: Array<{ key: string; name: string }>
}
export interface DecisionDeDemanda { step_key: string; decision: string; target_phase?: string; justification?: string }
export interface EjecucionDeDemanda { mode: string; name?: string; pm_id?: string }

/** Lista tolerante: `[...]` o `{ items: [...] }`. */
export function lista<T>(d: unknown): T[] {
  if (Array.isArray(d)) return d as T[]
  const items = (d as { items?: unknown } | null | undefined)?.items
  return Array.isArray(items) ? items as T[] : []
}

export const demandaApi = {
  catalogo: () => D<CatalogoDeDemanda>(api.get('/demand/catalog')),
  tipos: () => api.get('/demand/types').then(r => lista<TipoDeDemanda>(r.data)),
  crearTipo: (b: unknown) => D<TipoDeDemanda>(api.post('/demand/types', b)),
  editarTipo: (id: string, b: unknown) => D<TipoDeDemanda>(api.patch(`/demand/types/${id}`, b)),
  flujos: () => api.get('/demand/flows').then(r => lista<FlujoDeDemanda>(r.data)),
  flujo: (id: string) => D<FlujoDeDemanda>(api.get(`/demand/flows/${id}`)),
  crearFlujo: (b: { name: string; definition: DefinicionDeFlujo; is_active?: boolean }) => D<FlujoDeDemanda>(api.post('/demand/flows', b)),
  editarFlujo: (id: string, b: { name?: string; definition?: DefinicionDeFlujo; is_active?: boolean }) => D<FlujoDeDemanda>(api.patch(`/demand/flows/${id}`, b)),
  validarFlujo: (definition: DefinicionDeFlujo) => D<{ errors: ErrorDeDefinicion[] }>(api.post('/demand/flows/validate', { definition })),
  plantillaPiloto: () => D<unknown>(api.post('/demand/flows/pilot-template')),

  solicitudes: (f: FiltrosDeDemanda = {}) => api.get('/demand/requests', {
    params: { status: f.status || undefined, phase: f.phase || undefined, type: f.type || undefined, pending_for_me: f.pending_for_me || undefined, q: f.q || undefined },
  }).then(r => lista<ResumenDeDemanda>(r.data)),
  crear: (b: NuevaDemanda) => D<DetalleDeDemanda>(api.post('/demand/requests', b)),
  detalle: (id: string) => D<DetalleDeDemanda>(api.get(`/demand/requests/${id}`)),
  editarCampos: (id: string, b: { title?: string; data: Record<string, unknown>; note?: string }) => D<DetalleDeDemanda>(api.patch(`/demand/requests/${id}/fields`, b)),
  retirar: (id: string, reason?: string) => D<unknown>(api.post(`/demand/requests/${id}/withdraw`, { reason: reason || undefined })),
  enviar: (id: string) => D<DetalleDeDemanda>(api.post(`/demand/requests/${id}/submit`)),
  decidir: (id: string, b: DecisionDeDemanda) => D<DetalleDeDemanda>(api.post(`/demand/requests/${id}/decide`, b)),
  comentar: (id: string, b: { body: string; internal: boolean }) => D<unknown>(api.post(`/demand/requests/${id}/comments`, b)),
  subirDocumento: (id: string, f: { file: File; tag: string; personal_data: boolean }) => {
    const fd = new FormData()
    fd.append('file', f.file)
    fd.append('tag', f.tag)
    fd.append('personal_data', f.personal_data ? 'true' : 'false')
    return D<unknown>(api.post(`/demand/requests/${id}/documents`, fd))
  },
  descargarDocumento: (id: string, docId: string) => api.get(`/demand/requests/${id}/documents/${docId}/download`, { responseType: 'blob' }).then(r => r.data as Blob),
  agendarComite: (id: string, date: string) => D<DetalleDeDemanda>(api.post(`/demand/requests/${id}/committee`, { date })),
  resumenEjecutivo: (id: string) => D<unknown>(api.post(`/demand/requests/${id}/executive-summary`)),
  ejecutar: (id: string, b: EjecucionDeDemanda) => D<unknown>(api.post(`/demand/requests/${id}/execute`, b)),
  metricas: () => D<MetricasDeDemanda>(api.get('/demand/metrics')),
  // Biblioteca, importar/exportar, simulador y diagrama
  plantillas: () => api.get('/demand/templates').then(r => lista<PlantillaDeFlujo>(r.data)),
  instalarPlantilla: (key: string) => D<{ flow_id: string; created: boolean }>(api.post(`/demand/templates/${key}/install`)),
  exportarFlujo: (id: string) => D<unknown>(api.get(`/demand/flows/${id}/export`)),
  importarFlujo: (cuerpo: unknown) => D<{ flow_id?: string }>(api.post('/demand/flows/import', cuerpo)),
  simular: (definition: DefinicionDeFlujo, data: Record<string, unknown>, decisions: Record<string, string>) => D<SimulacionDeFlujo>(api.post('/demand/flows/simulate', { definition, data, decisions })),
  diagrama: (definition: DefinicionDeFlujo) => D<DiagramaDeFlujo>(api.post('/demand/flows/diagram', { definition })),
  // Mis solicitudes (cualquier usuario)
  tiposParaSolicitar: (channel = 'operator') => D<{ types: TipoParaSolicitar[]; projects?: Array<{ id: string; name: string }> }>(api.get('/demand/mine/types', { params: { channel } })),
  mias: () => api.get('/demand/mine').then(r => lista<ResumenDeDemanda>(r.data)),
  crearMia: (b: NuevaDemanda, channel = 'operator') => D<DetalleDeDemanda>(api.post('/demand/mine', b, { params: { channel } })),
  verificar: (id: string) => D<{ ok: boolean }>(api.get(`/demand/requests/${id}/verify`)),
  /** Selector de alcance: elementos del catálogo (`service`) o CI de la CMDB (`asset`). */
  opcionesDeAlcance: (kind: 'service' | 'asset', q?: string) => api.get('/demand/mine/scope-options', { params: { kind, q } }).then(r => lista<{ value: string; label: string }>(r.data)),
}
