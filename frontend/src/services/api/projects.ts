/**
 * services/api/projects.ts — Audit #C10 typed slice.
 */
import type { AxiosResponse } from 'axios'
import api from './_core'
import { todasLasPaginas } from './todasLasPaginas'
import type { UserPublic } from './users'

/** `ProjectStatus` (app/schemas/common_enums.py). */
export type ProjectStatus =
  | 'planning' | 'active' | 'on_hold' | 'paused' | 'completed' | 'closed' | 'cancelled' | 'archived'
/** `ProjectType` (app/schemas/common_enums.py). */
export type ProjectType = 'development' | 'maintenance' | 'rd' | 'internal' | 'consulting'
/** `ProjectRisk` (app/schemas/common_enums.py). */
export type ProjectRisk = 'low' | 'medium' | 'high' | 'critical'

/** `ProjectSummary` (app/schemas/projects.py): elemento de `GET /projects`.
 *  Auditoría 2026-11 (#25): el tipo anterior anunciaba `client_id`, `manager_id`,
 *  `end_date` y `budget`, que el listado no manda. */
export interface ProjectListItem {
  id: string
  code: string
  name: string
  project_type: ProjectType
  status: ProjectStatus
  risk_level: ProjectRisk
  pm_name: string | null
  client_name: string | null
  department: string | null
  budget_amount: number | null
  total_cost_spent: number | null
  budget_used_pct: number | null
  progress_pct: number | null
  team_size: number
  start_date: string | null
  end_date_planned: string | null
}

/** `ProjectPhaseOut` (app/schemas/projects.py). */
export interface ProjectPhase {
  id: string
  project_id: string
  name: string
  description: string | null
  order: number
  budget_hours: number | null
  start_date: string | null
  end_date: string | null
  status: ProjectStatus
  created_at: string
}

/** `ProjectOut` (app/schemas/projects.py): detalle, alta y edición. */
export interface ProjectDetail {
  id: string
  code: string
  name: string
  description: string | null
  project_type: ProjectType
  status: ProjectStatus
  risk_level: ProjectRisk
  client_name: string | null
  client_id: string | null
  department: string | null
  is_billable: boolean
  billing_rate: number | null
  budget_hours: number | null
  budget_amount: number | null
  start_date: string | null
  end_date_planned: string | null
  tags: string | null
  jira_project_key: string | null
  pm_id: string | null
  project_manager: UserPublic | null
  phases: ProjectPhase[]
  created_at: string
  total_hours_spent: number | null
  total_cost_spent: number | null
  budget_used_pct: number | null
  progress_pct: number | null
  team_size: number
  tasks_total: number
  tasks_done: number
}

/** Filtros de `GET /projects` (list_projects en app/api/v1/endpoints/projects). */
export interface ProjectListParams {
  status?: ProjectStatus
  project_type?: ProjectType
  pm_id?: string
  search?: string
  page?: number
  page_size?: number
}

/** `ProjectPhaseCreate` (app/schemas/projects.py). */
export interface ProjectPhaseCreatePayload {
  name: string
  description?: string | null
  order?: number
  budget_hours?: number | null
  start_date?: string | null
  end_date?: string | null
  status?: ProjectStatus
}

/** `ProjectCreate` (app/schemas/projects.py). `code` es opcional: si falta, lo pone el servidor. */
export interface ProjectCreatePayload {
  name: string
  code?: string | null
  description?: string | null
  project_type?: ProjectType
  client_name?: string | null
  client_id?: string | null
  department?: string | null
  is_billable?: boolean
  billing_rate?: number | null
  budget_hours?: number | null
  budget_amount?: number | null
  start_date?: string | null
  end_date_planned?: string | null
  tags?: string | null
  jira_project_key?: string | null
  pm_id?: string | null
  phases?: ProjectPhaseCreatePayload[]
}

/** `ProjectUpdate` (app/schemas/projects.py). */
export interface ProjectUpdatePayload {
  name?: string | null
  description?: string | null
  project_type?: ProjectType | null
  status?: ProjectStatus | null
  risk_level?: ProjectRisk | null
  pm_id?: string | null
  client_name?: string | null
  client_id?: string | null
  department?: string | null
  budget_hours?: number | null
  budget_amount?: number | null
  billing_rate?: number | null
  start_date?: string | null
  end_date_planned?: string | null
  end_date_real?: string | null
  tags?: string | null
  jira_project_key?: string | null
}

export interface PhaseCreatePayload {
  name: string
  start_date?: string
  end_date?: string
  description?: string
}

export interface MemberAddPayload {
  user_id: string
  role: string
  allocation_pct?: number
}

export interface ChangelogEntry {
  id: string
  title: string
  body: string
  created_at: string
  author_name: string
}

export interface RaciEntry {
  user_id: string
  user_name?: string
  task_or_phase: string
  role: 'R' | 'A' | 'C' | 'I'
}

export const projectsApi = {
  list: (params?: ProjectListParams): Promise<AxiosResponse<ProjectListItem[]>> =>
    // Auditoría 2026-11: sin `page`, todas las páginas (antes, solo las 50 primeras).
    todasLasPaginas('/projects', params as Record<string, unknown> | undefined),

  get: (id: string): Promise<AxiosResponse<ProjectDetail>> =>
    api.get(`/projects/${id}`),

  create: (data: ProjectCreatePayload): Promise<AxiosResponse<ProjectDetail>> =>
    api.post('/projects', data),

  update: (id: string, data: ProjectUpdatePayload): Promise<AxiosResponse<ProjectDetail>> =>
    api.patch(`/projects/${id}`, data),

  delete: (id: string): Promise<AxiosResponse<{ ok: boolean }>> =>
    api.delete(`/projects/${id}`),

  team: (id: string): Promise<AxiosResponse<unknown>> =>
    api.get(`/projects/${id}/team`),

  members: (id: string): Promise<AxiosResponse<unknown>> =>
    api.get(`/projects/${id}/members`),

  addMember: (id: string, data: MemberAddPayload): Promise<AxiosResponse<unknown>> =>
    api.post(`/projects/${id}/members`, data),

  removeMember: (id: string, memberId: string): Promise<AxiosResponse<{ ok: boolean }>> =>
    api.delete(`/projects/${id}/members/${memberId}`),

  milestones: (params?: Record<string, unknown>): Promise<AxiosResponse<unknown>> =>
    api.get('/projects/milestones', { params }),

  evm: (id: string): Promise<AxiosResponse<unknown>> =>
    api.get(`/projects/${id}/evm`),

  evmPortfolio: (): Promise<AxiosResponse<unknown>> =>
    api.get('/projects/evm/portfolio'),
} as const
