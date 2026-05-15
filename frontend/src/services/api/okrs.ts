/**
 * OKRs + key results.
 */
import { api } from './client'
import type { Id, JsonBody, Params, Response } from './types'

export const okrsApi = {
  list:     (params?: Params): Promise<Response<unknown>> => api.get('/okrs', { params }),
  get:      (id: Id): Promise<Response<unknown>> => api.get(`/okrs/${id}`),
  create:   (data: JsonBody): Promise<Response<unknown>> => api.post('/okrs', data),
  update:   (id: Id, data: JsonBody): Promise<Response<unknown>> => api.patch(`/okrs/${id}`, data),
  delete:   (id: Id): Promise<Response<unknown>> => api.delete(`/okrs/${id}`),
  updateKR: (id: Id, krid: Id, d: JsonBody): Promise<Response<unknown>> =>
    api.patch(`/okrs/${id}/key-results/${krid}`, d),
  createKR: (data: JsonBody): Promise<Response<unknown>> => api.post('/okrs/key-results', data),
  deleteKR: (id: Id): Promise<Response<unknown>> => api.delete(`/okrs/key-results/${id}`),
  checkin:  (krId: Id, data: JsonBody): Promise<Response<unknown>> =>
    api.post(`/okrs/key-results/${krId}/checkin`, data),
}
