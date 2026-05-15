/**
 * Absences (vacation, sick, etc.).
 */
import { api } from './client'
import type { Id, JsonBody, Params, Response } from './types'

export const absencesApi = {
  list:            (params?: Params): Promise<Response<unknown>> => api.get('/absences', { params }),
  my:              (params?: Params): Promise<Response<unknown>> => api.get('/absences/my', { params }),
  pending:         (): Promise<Response<unknown>> => api.get('/absences/pending'),
  team:            (params?: Params): Promise<Response<unknown>> => api.get('/absences/team', { params }),
  calendar:        (params?: Params): Promise<Response<unknown>> => api.get('/absences/calendar', { params }),
  get:             (id: Id): Promise<Response<unknown>> => api.get(`/absences/${id}`),
  create:          (data: JsonBody): Promise<Response<unknown>> => api.post('/absences', data),
  createMy:        (data: JsonBody): Promise<Response<unknown>> => api.post('/absences/my', data),
  update:          (id: Id, data: JsonBody): Promise<Response<unknown>> => api.patch(`/absences/${id}`, data),
  updateMy:        (id: Id, data: JsonBody): Promise<Response<unknown>> => api.patch(`/absences/my/${id}`, data),
  approve:         (id: Id): Promise<Response<unknown>> => api.post(`/absences/${id}/approve`),
  reject:          (id: Id, data: JsonBody): Promise<Response<unknown>> => api.post(`/absences/${id}/reject`, data),
  review:          (id: Id, data: JsonBody): Promise<Response<unknown>> => api.post(`/absences/${id}/review`, data),
  delete:          (id: Id): Promise<Response<unknown>> => api.delete(`/absences/${id}`),
  deleteMy:        (id: Id): Promise<Response<unknown>> => api.delete(`/absences/my/${id}`),
  balance:         (params?: Params): Promise<Response<unknown>> => api.get('/absences/balance', { params }),
  vacationBalance: (): Promise<Response<unknown>> => api.get('/absences/my/vacation-balance'),
  policies:        (): Promise<Response<unknown>> => api.get('/absences/policies'),
}
