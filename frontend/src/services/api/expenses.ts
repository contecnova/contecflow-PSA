/**
 * Expenses (own + admin/team).
 */
import { api } from './client'
import type { Id, JsonBody, Params, Response } from './types'

export const expensesApi = {
  list:      (params?: Params): Promise<Response<unknown>> => api.get('/expenses', { params }),
  my:        (params?: Params): Promise<Response<unknown>> => api.get('/expenses/my', { params }),
  pending:   (): Promise<Response<unknown>> => api.get('/expenses/pending'),
  team:      (params?: Params): Promise<Response<unknown>> => api.get('/expenses/team', { params }),
  get:       (id: Id): Promise<Response<unknown>> => api.get(`/expenses/${id}`),
  create:    (data: JsonBody): Promise<Response<unknown>> => api.post('/expenses', data),
  update:    (id: Id, data: JsonBody): Promise<Response<unknown>> => api.patch(`/expenses/${id}`, data),
  updateMy:  (id: Id, data: JsonBody): Promise<Response<unknown>> => api.patch(`/expenses/my/${id}`, data),
  approve:   (id: Id): Promise<Response<unknown>> => api.post(`/expenses/${id}/approve`),
  reject:    (id: Id, data: JsonBody): Promise<Response<unknown>> => api.post(`/expenses/${id}/reject`, data),
  review:    (id: Id, data: JsonBody): Promise<Response<unknown>> => api.post(`/expenses/${id}/review`, data),
  submitMy:  (id: Id): Promise<Response<unknown>> => api.post(`/expenses/my/${id}/submit`),
  recall:    (id: Id): Promise<Response<unknown>> => api.post(`/expenses/my/${id}/recall`),
  reimburse: (id: Id): Promise<Response<unknown>> => api.post(`/expenses/${id}/reimburse`),
  delete:    (id: Id): Promise<Response<unknown>> => api.delete(`/expenses/${id}`),
  deleteMy:  (id: Id): Promise<Response<unknown>> => api.delete(`/expenses/my/${id}`),
  ocr:       (fd: FormData): Promise<Response<unknown>> => api.post('/expenses/ocr', fd),
}
