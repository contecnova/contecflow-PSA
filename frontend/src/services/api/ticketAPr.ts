/**
 * services/api/ticketAPr.ts — «Del ticket al PR» (migración 203, docs/integraciones/TICKET_A_PR.md).
 *
 * Un agente de código propone el arreglo de un ticket o tarea como pull request:
 * plan de solo lectura → aprobación de una persona → build en un contenedor
 * aislado → PR → cambio ITSM → CAB. Módulo opcional por empresa (apagado).
 */
import api from './_core'

export type OrigenTicketAPr = 'ticket' | 'task'

export type EstadoDeEjecucion =
  | 'queued_plan' | 'planning' | 'awaiting_approval' | 'rejected' | 'queued_build' | 'building'
  | 'blocked' | 'failed' | 'cancelled' | 'awaiting_cab' | 'cab_approved' | 'cab_rejected' | 'merged' | 'closed'

export interface RepoTicketAPr {
  id: string
  project_id: string
  provider: 'github' | 'gitlab'
  repo_full_name: string
  default_branch: string
  test_command: string | null
  is_active: boolean
  created_at: string | null
}

export interface EjecucionTicketAPr {
  id: string
  status: EstadoDeEjecucion
  status_code: string | null
  status_params: Record<string, unknown>
  source_type: OrigenTicketAPr
  ticket_id: string | null
  task_id: string | null
  source_ref: string | null
  project_id: string | null
  provider: string
  repo_full_name: string
  base_branch: string
  branch_name: string | null
  engine: string
  engine_image: string | null
  model: string | null
  instruction: string
  plan_text: string | null
  plan_files: string[]
  launched_by_name: string | null
  plan_decided_by_name: string | null
  plan_decided_at: string | null
  plan_decision_note: string | null
  diff_summary: { files: { path: string; action: string; added: number; removed: number }[]; added: number; removed: number } | null
  tests_ran: boolean
  tests_passed: boolean | null
  reasoning_summary: string | null
  pr_number: number | null
  pr_url: string | null
  pr_status_state: 'pending' | 'success' | 'failure' | null
  change: { id: string; number: string; status: string; change_type: string } | null
  tokens_in: number
  tokens_out: number
  cost_usd: number
  agent_hours: number
  started_at: string | null
  finished_at: string | null
  created_at: string | null
  can_decide: boolean
  can_cancel: boolean
}

export interface PanelTicketAPr {
  enabled: boolean
  can_launch: boolean
  can_approve: boolean
  reason: string | null
  repos: RepoTicketAPr[]
  runs: EjecucionTicketAPr[]
}

export interface LimitesTicketAPr {
  max_runs_per_day: number
  max_cost_per_day_usd: number
  max_concurrent: number
  plan_timeout_min: number
  build_timeout_min: number
  cpus: number
  memory_mb: number
  max_changed_files: number
  max_diff_kb: number
  max_repo_mb: number
}

export interface ConfigTicketAPr {
  engine: string
  engine_image: string
  engine_version: string
  proxy_image: string
  ai_provider_id: string | null
  model: string | null
  protected_paths: string[]
  run_tests: boolean
  block_on_test_failure: boolean
  extra_egress_hosts: string[]
  bash_allow: string[]
  plan_requires_other_person: boolean
  change_type: 'normal' | 'standard_if_fits'
  standard_model_id: string | null
  templates: { plan: string; build: string }
  limits: LimitesTicketAPr
}

export interface CampoDeCredencial {
  key: string
  label: string
  is_secret: boolean
  value: string | null
  configured: boolean
  source: 'db' | 'env' | 'unset'
}

export interface VistaDeConfigTicketAPr {
  enabled: boolean
  config: ConfigTicketAPr
  credentials: { provider: string; label: string; items: CampoDeCredencial[] }
  protected_defaults: string[]
  usage_today: { runs: number; cost_usd: number; active: number }
}

export interface PruebaTicketAPr {
  ok: boolean
  verificado: 'nada' | 'configuracion' | 'alcance' | 'credencial' | 'credencial_y_uso'
  comprobaciones: Record<'docker' | 'imagen_motor' | 'imagen_proxy' | 'imagen_ayudante' | 'git' | 'modelo', boolean | null>
  detail: string
}

export interface CosteDeProyecto {
  project_id: string | null
  project_name: string | null
  runs: number
  cost_usd: number
  tokens_in: number
  tokens_out: number
  agent_hours: number
}

// El interceptor de `_core` ya desenvuelve el sobre: `r.data` es el contenido.
const D = <T,>(p: Promise<{ data: unknown }>) => p.then(r => r.data as T)

export const CLAVES_TICKET_A_PR = {
  todo: ['ticket-pr'] as const,
  panel: (tipo: OrigenTicketAPr, id: string) => ['ticket-pr', 'panel', tipo, id] as const,
  config: ['ticket-pr', 'config'] as const,
  repos: ['ticket-pr', 'repos'] as const,
  costes: ['ticket-pr', 'costes'] as const,
  log: (id: string) => ['ticket-pr', 'log', id] as const,
}

export const ticketAPrApi = {
  panel: (tipo: OrigenTicketAPr, id: string) => D<PanelTicketAPr>(api.get(`/ticket-pr/origen/${tipo}/${id}`)),
  proponer: (tipo: OrigenTicketAPr, id: string, c: { repo_id: string; base_branch?: string }) =>
    D<{ instruction: string; base_branch: string; repo_id: string }>(api.post(`/ticket-pr/origen/${tipo}/${id}/instruccion`, c)),
  lanzar: (tipo: OrigenTicketAPr, id: string, c: { repo_id: string; base_branch?: string; instruction?: string }) =>
    D<EjecucionTicketAPr>(api.post(`/ticket-pr/origen/${tipo}/${id}/ejecuciones`, c)),
  decidir: (runId: string, c: { approve: boolean; note?: string }) =>
    D<EjecucionTicketAPr>(api.post(`/ticket-pr/ejecuciones/${runId}/plan`, c)),
  cancelar: (runId: string) => D<EjecucionTicketAPr>(api.post(`/ticket-pr/ejecuciones/${runId}/cancelar`)),
  sincronizar: (runId: string) => D<EjecucionTicketAPr>(api.post(`/ticket-pr/ejecuciones/${runId}/sincronizar`)),
  log: (runId: string) => D<{ id: string; log: string }>(api.get(`/ticket-pr/ejecuciones/${runId}/log`)),
  config: () => D<VistaDeConfigTicketAPr>(api.get('/ticket-pr/config')),
  cambiarConfig: (c: Partial<ConfigTicketAPr> & { enabled?: boolean }) =>
    D<VistaDeConfigTicketAPr>(api.patch('/ticket-pr/config', c)),
  repos: () => D<RepoTicketAPr[]>(api.get('/ticket-pr/repos')),
  crearRepo: (c: { project_id: string; provider: string; repo_full_name: string; default_branch: string; test_command?: string }) =>
    D<RepoTicketAPr>(api.post('/ticket-pr/repos', c)),
  editarRepo: (id: string, c: Partial<Pick<RepoTicketAPr, 'default_branch' | 'test_command' | 'is_active' | 'repo_full_name'>>) =>
    D<RepoTicketAPr>(api.patch(`/ticket-pr/repos/${id}`, c)),
  quitarRepo: (id: string) => D<unknown>(api.delete(`/ticket-pr/repos/${id}`)),
  probar: () => D<PruebaTicketAPr>(api.post('/ticket-pr/prueba')),
  costes: (dias = 30) => D<CosteDeProyecto[]>(api.get('/ticket-pr/costes', { params: { dias } })),
  /** Credenciales Git (almacén cifrado de integraciones; nunca se leen en claro). */
  guardarCredencial: (clave: string, valor: string) =>
    D<unknown>(api.put(`/settings/integrations/ticket_pr/${clave}`, { value: valor })),
}

/** Estados en los que la ejecución sigue viva (la pantalla refresca sola). */
export const ESTADOS_EN_MARCHA: EstadoDeEjecucion[] = ['queued_plan', 'planning', 'queued_build', 'building']
