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
  /** Proveedor del recurso externo (rol `subcontractor`); null si es interno. */
  external_company?: string | null
}

/** `PersonaVisible` (app/schemas/users.py): ficha mínima de `GET /users/directory`, el
 *  selector de personas que sirve a cualquier rol (también al subcontratado, que recibe
 *  403 en `GET /users`). Sin correo, tarifa ni datos de RR. HH. */
export interface PersonaVisible {
  id: string
  full_name: string
  first_name: string | null
  last_name: string | null
  avatar_url: string | null
  role: string | null
  job_title: string | null
  /** Proveedor del recurso externo (rol `subcontractor`); null si es interno. */
  external_company?: string | null
}

/** `PersonaInterna` (app/schemas/users.py): la fila de `GET /users` de otra persona cuando
 *  quien pregunta no ve la ficha ajena (el empleado). Sin correo, teléfono, manager ni acceso. */
export interface PersonaInterna extends PersonaVisible {
  department: string | null
  is_active: boolean
}

/** Elemento de `GET /users` (`APIListResponse[Union[UserPublic, PersonaInterna]]`): la ficha
 *  completa para quien la puede ver (y la propia del empleado); la interna para el resto.
 *  Distinguir con `'email' in u` (`esFichaCompleta`). */
export type UserListItem = UserPublic | PersonaInterna

/** La fila de `GET /users` trae la ficha completa (correo, teléfono, manager...). */
export function esFichaCompleta(u: UserListItem): u is UserPublic {
  return 'email' in u
}

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

/** Un responsable de la cadena (user_service.approval_chain_for_user). */
export interface ApprovalChainNode {
  id: string
  full_name: string
  job_title: string | null
  department: string | null
  role: string
  /** 1 = aprobador directo; hasta 5 niveles. */
  level: number
}

/** GET /users/{id}/approval-chain y /users/me/approval-chain. */
export interface ApprovalChain {
  user_id: string
  user_name: string
  chain: ApprovalChainNode[]
  direct_approver: ApprovalChainNode | null
}

export const usersApi = {
  list: (params?: UserListParams): Promise<AxiosResponse<UserListItem[]>> =>
    // Auditoría 2026-11: sin `page`, todas las páginas (antes, solo las 50 primeras).
    todasLasPaginas('/users', params as Record<string, unknown> | undefined),

  /** Selector de personas para asignar o mencionar (lista entera, sin paginar). */
  directory: (params?: { search?: string }): Promise<AxiosResponse<PersonaVisible[]>> =>
    api.get('/users/directory', { params }),

  load: (params?: Record<string, unknown>): Promise<AxiosResponse<unknown>> =>
    api.get('/users/load', { params }),

  get: (id: string): Promise<AxiosResponse<UserWithRate>> =>
    api.get(`/users/${id}`),

  create: (data: UserCreatePayload): Promise<AxiosResponse<UserListItem>> =>
    api.post('/users', data),

  update: (id: string, data: UserUpdatePayload): Promise<AxiosResponse<UserListItem>> =>
    api.patch(`/users/${id}`, data),

  /** `confirmarEquipos`: desactivar aunque tenga equipo sin devolver (política «confirmar» de ALM, fase 4). */
  deactivate: (id: string, confirmarEquipos = false): Promise<AxiosResponse<{ ok: boolean }>> =>
    api.delete(`/users/${id}`, confirmarEquipos ? { params: { confirmar_equipos: true } } : undefined),

  deletePermanent: (id: string): Promise<AxiosResponse<{ ok: boolean }>> =>
    api.delete(`/users/${id}/permanent`),

  orgChart: (): Promise<AxiosResponse<unknown>> =>
    api.get('/users/org-chart'),

  updateManager: (id: string, data: UserManagerUpdate): Promise<AxiosResponse<UserListItem>> =>
    api.patch(`/users/${id}/manager`, data),

  updateMe: (data: UserSelfUpdatePayload): Promise<AxiosResponse<UserPublic>> =>
    api.patch('/users/me', data),

  approvalChain: (userId: string): Promise<AxiosResponse<ApprovalChain>> =>
    api.get(`/users/${userId}/approval-chain`),

  myApprovalChain: (): Promise<AxiosResponse<ApprovalChain>> =>
    api.get('/users/me/approval-chain'),
} as const
