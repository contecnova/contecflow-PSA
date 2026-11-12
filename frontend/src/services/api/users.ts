/**
 * services/api/users.ts — Audit #C10 typed slice.
 */
import type { AxiosResponse } from 'axios'
import api from './_core'
import { todasLasPaginas } from './todasLasPaginas'

/** `UserStatus` (app/schemas/common_enums.py). */
export type UserStatus = 'active' | 'inactive' | 'vacation' | 'leave'

/** `UserOrganizationOut` (app/schemas/users.py). */
export interface UserOrganization {
  id: string
  name: string | null
  slug: string | null
}

/** `UserPublic` (app/schemas/users.py). Es lo que devuelven `GET /users`, el alta y la edición,
 *  y lo que el servidor anida en tareas, comentarios y proyectos. No lleva `hourly_rate`. */
export interface UserPublic {
  id: string
  username: string
  email: string
  full_name: string
  first_name: string | null
  last_name: string | null
  department: string | null
  job_title: string | null
  role: string
  status: UserStatus
  weekly_capacity_hours: number
  organization_id: string | null
  organization_ids: string[] | null
  is_active: boolean
  avatar_url: string | null
  last_login: string | null
  created_at: string
  manager_id: string | null
  manager_name: string | null
  phone: string | null
  organizations: UserOrganization[] | null
  custom_role_id: string | null
  timezone: string | null
  sso_provider: string | null
  blocked_routes: string[]
  impersonated_by: string | null
}

/** Elemento de `GET /users` (`APIListResponse[UserPublic]`). */
export type UserListItem = UserPublic

/** `UserWithRate` (app/schemas/users.py): `GET /users/{id}`. */
export interface UserWithRate extends UserPublic {
  hourly_rate: number | null
  ldap_dn: string | null
}

/** Filtros de `GET /users` (list_users en app/api/v1/endpoints/users.py). */
export interface UserListParams {
  department?: string
  role?: string
  status?: UserStatus
  search?: string
  page?: number
  page_size?: number
}

/** `UserCreate` (app/schemas/users.py). No admite `manager_id`: si se manda, pydantic lo
 *  descarta. `hourly_rate` y `custom_role_id` sólo los puede fijar un administrador. */
export interface UserCreatePayload {
  username: string
  email: string
  full_name: string
  first_name?: string | null
  last_name?: string | null
  department?: string | null
  job_title?: string | null
  role?: string
  status?: UserStatus
  weekly_capacity_hours?: number
  organization_id?: string | null
  organization_ids?: string[] | null
  password?: string | null
  hourly_rate?: number | null
  timezone?: string | null
  custom_role_id?: string | null
}

/** `UserUpdate` (app/schemas/users.py). */
export interface UserUpdatePayload {
  email?: string | null
  full_name?: string | null
  first_name?: string | null
  last_name?: string | null
  department?: string | null
  job_title?: string | null
  role?: string | null
  status?: UserStatus | null
  weekly_capacity_hours?: number | null
  hourly_rate?: number | null
  phone?: string | null
  avatar_url?: string | null
  manager_id?: string | null
  timezone?: string | null
  organization_id?: string | null
  organization_ids?: string[] | null
  custom_role_id?: string | null
}

/** `UserSelfUpdate` (app/schemas/users.py): lo que cada cual puede cambiar de su perfil. */
export interface UserSelfUpdatePayload {
  email?: string | null
  first_name?: string | null
  last_name?: string | null
  full_name?: string | null
  phone?: string | null
  job_title?: string | null
  avatar_url?: string | null
  timezone?: string | null
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

  load: (params?: Record<string, unknown>): Promise<AxiosResponse<unknown>> =>
    api.get('/users/load', { params }),

  get: (id: string): Promise<AxiosResponse<UserWithRate>> =>
    api.get(`/users/${id}`),

  create: (data: UserCreatePayload): Promise<AxiosResponse<UserListItem>> =>
    api.post('/users', data),

  update: (id: string, data: UserUpdatePayload): Promise<AxiosResponse<UserListItem>> =>
    api.patch(`/users/${id}`, data),

  deactivate: (id: string): Promise<AxiosResponse<{ ok: boolean }>> =>
    api.delete(`/users/${id}`),

  deletePermanent: (id: string): Promise<AxiosResponse<{ ok: boolean }>> =>
    api.delete(`/users/${id}/permanent`),

  orgChart: (): Promise<AxiosResponse<unknown>> =>
    api.get('/users/org-chart'),

  updateManager: (id: string, data: UserManagerUpdate): Promise<AxiosResponse<UserListItem>> =>
    api.patch(`/users/${id}/manager`, data),

  updateMe: (data: UserSelfUpdatePayload): Promise<AxiosResponse<UserPublic>> =>
    api.patch('/users/me', data),

  approvalChain: (userId: string): Promise<AxiosResponse<ApprovalChainNode[]>> =>
    api.get(`/users/${userId}/approval-chain`),

  myApprovalChain: (): Promise<AxiosResponse<ApprovalChainNode[]>> =>
    api.get('/users/me/approval-chain'),
} as const
