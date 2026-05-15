/**
 * Users — CRUD, load, productivity, org-chart, approval chains.
 */
import { api } from './client'
import type { Id, JsonBody, Params, Response } from './types'

// TODO type: tighten against `app/schemas/user.py`.
export interface UserUpdatePayload extends JsonBody {
  full_name?: string
  email?: string
  role?: string
  department?: string | null
  is_active?: boolean
  manager_id?: string | null
  hourly_rate?: number | null
}

export const usersApi = {
  list:            (params?: Params): Promise<Response<unknown>> => api.get('/users', { params }),
  withRates:       (): Promise<Response<unknown>> => api.get('/users/with-rates'),
  load:            (params?: Params): Promise<Response<unknown>> => api.get('/users/load', { params }),
  get:             (id: Id): Promise<Response<unknown>> => api.get(`/users/${id}`),
  create:          (data: JsonBody): Promise<Response<unknown>> => api.post('/users', data),
  update:          (id: Id, data: UserUpdatePayload): Promise<Response<unknown>> => api.patch(`/users/${id}`, data),
  deactivate:      (id: Id): Promise<Response<unknown>> => api.delete(`/users/${id}`),
  deletePermanent: (id: Id): Promise<Response<unknown>> => api.delete(`/users/${id}/permanent`),
  productivity:    (id: Id, params?: Params): Promise<Response<unknown>> => api.get(`/users/${id}/productivity`, { params }),
  orgChart:        (): Promise<Response<unknown>> => api.get('/users/org-chart'),
  updateManager:   (id: Id, data: JsonBody): Promise<Response<unknown>> => api.patch(`/users/${id}/manager`, data),
  updateMe:        (data: JsonBody): Promise<Response<unknown>> => api.patch('/users/me', data),
  approvalChain:   (userId: Id): Promise<Response<unknown>> => api.get(`/users/${userId}/approval-chain`),
  myApprovalChain: (): Promise<Response<unknown>> => api.get('/users/me/approval-chain'),
}
