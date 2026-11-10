/**
 * services/api/users.ts — Audit #C10 typed slice.
 */
import type { AxiosResponse } from 'axios'
import api from './_core'
import { todasLasPaginas } from './todasLasPaginas'

export interface UserListItem {
  id: string
  email: string
  full_name: string
  role: string
  is_active: boolean
  organization_id: string | null
  hourly_rate?: number | null
  picture_url?: string | null
  department?: string | null
}

export interface UserListParams {
  active?: boolean
  role?: string
  organization_id?: string
  q?: string
  page?: number
  page_size?: number
}

export interface UserCreatePayload {
  email: string
  full_name: string
  role: string
  password?: string
  hourly_rate?: number
  manager_id?: string | null
  department?: string | null
}

export type UserUpdatePayload = Partial<UserCreatePayload> & {
  is_active?: boolean
  language?: string | null
  picture_url?: string | null
}

export interface UserProductivityParams {
  period?: 'week' | 'month' | 'quarter'
  start?: string
  end?: string
}

export interface UserManagerUpdate {
  manager_id: string | null
  /** Revisión 2026-11: puesto y departamento viajan en la misma llamada (una transacción). */
  job_title?: string | null
  department?: string | null
}

export interface ApprovalChainNode {
  user_id: string
  full_name: string
  role: string
  level: number
}

export const usersApi = {
  list: (params?: UserListParams): Promise<AxiosResponse<UserListItem[]>> =>
    // Auditoría 2026-11: sin `page`, todas las páginas (antes, solo las 50 primeras).
    todasLasPaginas('/users', params as Record<string, unknown> | undefined),

  withRates: (): Promise<AxiosResponse<UserListItem[]>> =>
    api.get('/users/with-rates'),

  load: (params?: Record<string, unknown>): Promise<AxiosResponse<unknown>> =>
    api.get('/users/load', { params }),

  get: (id: string): Promise<AxiosResponse<UserListItem>> =>
    api.get(`/users/${id}`),

  create: (data: UserCreatePayload): Promise<AxiosResponse<UserListItem>> =>
    api.post('/users', data),

  update: (id: string, data: UserUpdatePayload): Promise<AxiosResponse<UserListItem>> =>
    api.patch(`/users/${id}`, data),

  deactivate: (id: string): Promise<AxiosResponse<{ ok: boolean }>> =>
    api.delete(`/users/${id}`),

  deletePermanent: (id: string): Promise<AxiosResponse<{ ok: boolean }>> =>
    api.delete(`/users/${id}/permanent`),

  productivity: (id: string, params?: UserProductivityParams): Promise<AxiosResponse<unknown>> =>
    api.get(`/users/${id}/productivity`, { params }),

  orgChart: (): Promise<AxiosResponse<unknown>> =>
    api.get('/users/org-chart'),

  updateManager: (id: string, data: UserManagerUpdate): Promise<AxiosResponse<UserListItem>> =>
    api.patch(`/users/${id}/manager`, data),

  updateMe: (data: UserUpdatePayload): Promise<AxiosResponse<UserListItem>> =>
    api.patch('/users/me', data),

  approvalChain: (userId: string): Promise<AxiosResponse<ApprovalChainNode[]>> =>
    api.get(`/users/${userId}/approval-chain`),

  myApprovalChain: (): Promise<AxiosResponse<ApprovalChainNode[]>> =>
    api.get('/users/me/approval-chain'),
} as const
