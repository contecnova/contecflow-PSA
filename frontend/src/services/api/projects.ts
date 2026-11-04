/**
 * services/api/projects.ts — Audit #C10 typed slice.
 */
import type { AxiosResponse } from 'axios'
import api from './_core'
import { todasLasPaginas } from './todasLasPaginas'

export interface ProjectListItem {
  id: string
  code: string
  name: string
  status: string
  client_id: string | null
  client_name?: string | null
  manager_id?: string | null
  start_date?: string | null
  end_date?: string | null
  budget?: number | null
}

export interface ProjectListParams {
  status?: string
  client_id?: string
  manager_id?: string
  q?: string
  page?: number
  page_size?: number
}

export interface ProjectCreatePayload {
  code: string
  name: string
  client_id?: string
  status?: string
  start_date?: string
  end_date?: string
  budget?: number
  manager_id?: string
}

export type ProjectUpdatePayload = Partial<ProjectCreatePayload>

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

  get: (id: string): Promise<AxiosResponse<ProjectListItem>> =>
    api.get(`/projects/${id}`),

  create: (data: ProjectCreatePayload): Promise<AxiosResponse<ProjectListItem>> =>
    api.post('/projects', data),

  update: (id: string, data: ProjectUpdatePayload): Promise<AxiosResponse<ProjectListItem>> =>
    api.patch(`/projects/${id}`, data),

  delete: (id: string): Promise<AxiosResponse<{ ok: boolean }>> =>
    api.delete(`/projects/${id}`),

  team: (id: string): Promise<AxiosResponse<unknown>> =>
    api.get(`/projects/${id}/team`),

  addPhase: (id: string, data: PhaseCreatePayload): Promise<AxiosResponse<unknown>> =>
    api.post(`/projects/${id}/phases`, data),

  members: (id: string): Promise<AxiosResponse<unknown>> =>
    api.get(`/projects/${id}/members`),

  addMember: (id: string, data: MemberAddPayload): Promise<AxiosResponse<unknown>> =>
    api.post(`/projects/${id}/members`, data),

  removeMember: (id: string, memberId: string): Promise<AxiosResponse<{ ok: boolean }>> =>
    api.delete(`/projects/${id}/members/${memberId}`),

  milestones: (params?: Record<string, unknown>): Promise<AxiosResponse<unknown>> =>
    api.get('/projects/milestones', { params }),

  changelog: (id: string, params?: Record<string, unknown>): Promise<AxiosResponse<ChangelogEntry[]>> =>
    api.get(`/projects/${id}/changelog`, { params }),

  createChangelog: (id: string, data: Partial<ChangelogEntry>): Promise<AxiosResponse<ChangelogEntry>> =>
    api.post(`/projects/${id}/changelog`, data),

  generateChangelog: (id: string, data: Record<string, unknown>): Promise<AxiosResponse<ChangelogEntry>> =>
    api.post(`/projects/${id}/changelog/generate`, data),

  deleteChangelog: (id: string, entryId: string): Promise<AxiosResponse<{ ok: boolean }>> =>
    api.delete(`/projects/${id}/changelog/${entryId}`),

  raci: (id: string): Promise<AxiosResponse<RaciEntry[]>> =>
    api.get(`/projects/${id}/raci`),

  updateRaci: (id: string, data: RaciEntry[]): Promise<AxiosResponse<RaciEntry[]>> =>
    api.put(`/projects/${id}/raci`, data),

  deleteRaci: (id: string, entryId: string): Promise<AxiosResponse<{ ok: boolean }>> =>
    api.delete(`/projects/${id}/raci/${entryId}`),

  evm: (id: string): Promise<AxiosResponse<unknown>> =>
    api.get(`/projects/${id}/evm`),

  evmPortfolio: (): Promise<AxiosResponse<unknown>> =>
    api.get('/projects/evm/portfolio'),
} as const
