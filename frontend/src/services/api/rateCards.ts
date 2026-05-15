/**
 * Rate cards + effective rate lookups.
 */
import { api } from './client'
import type { Id, JsonBody, Params, Response } from './types'

export const rateCardsApi = {
  list:           (): Promise<Response<unknown>> => api.get('/rate-cards'),
  get:            (id: Id): Promise<Response<unknown>> => api.get(`/rate-cards/${id}`),
  create:         (d: JsonBody): Promise<Response<unknown>> => api.post('/rate-cards', d),
  update:         (id: Id, d: JsonBody): Promise<Response<unknown>> => api.patch(`/rate-cards/${id}`, d),
  delete:         (id: Id): Promise<Response<unknown>> => api.delete(`/rate-cards/${id}`),
  duplicate:      (id: Id, d: JsonBody): Promise<Response<unknown>> => api.post(`/rate-cards/${id}/duplicate`, d),
  addEntry:       (id: Id, d: JsonBody): Promise<Response<unknown>> => api.post(`/rate-cards/${id}/entries`, d),
  updateEntry:    (id: Id, eid: Id, d: JsonBody): Promise<Response<unknown>> =>
    api.patch(`/rate-cards/${id}/entries/${eid}`, d),
  deleteEntry:    (id: Id, eid: Id): Promise<Response<unknown>> => api.delete(`/rate-cards/${id}/entries/${eid}`),
  addOverride:    (id: Id, d: JsonBody): Promise<Response<unknown>> => api.post(`/rate-cards/${id}/overrides`, d),
  deleteOverride: (id: Id, oid: Id): Promise<Response<unknown>> => api.delete(`/rate-cards/${id}/overrides/${oid}`),
  effectiveRate:  (params?: Params): Promise<Response<unknown>> => api.get('/rate-cards/effective', { params }),
}
