/**
 * Risks (project + portfolio + scores), Oracle predictions.
 */
import { api } from './client'
import type { Id, JsonBody, Params, Response } from './types'

export const risksApi = {
  list:         (projectId: Id, params?: Params): Promise<Response<unknown>> => api.get(`/risks/${projectId}`, { params }),
  get:          (projectId: Id, riskId: Id): Promise<Response<unknown>> => api.get(`/risks/${projectId}/${riskId}`),
  create:       (projectId: Id, data: JsonBody): Promise<Response<unknown>> => api.post(`/risks/${projectId}`, data),
  update:       (projectId: Id, riskId: Id, data: JsonBody): Promise<Response<unknown>> =>
    api.patch(`/risks/${projectId}/${riskId}`, data),
  delete:       (projectId: Id, riskId: Id): Promise<Response<unknown>> => api.delete(`/risks/${projectId}/${riskId}`),
  scores:       (): Promise<Response<unknown>> => api.get('/risks/scores'),
  portfolioAll: (): Promise<Response<unknown>> => api.get('/risks/all/portfolio'),
}

export const riskScoresApi = {
  list:    (params?: Params): Promise<Response<unknown>> => api.get('/risk-scores', { params }),
  get:     (id: Id): Promise<Response<unknown>> => api.get(`/risk-scores/${id}`),
  refresh: (): Promise<Response<unknown>> => api.get('/risk-scores', { params: { refresh: true } }),
}

export const oracleApi = {
  predictions: (params?: Params): Promise<Response<unknown>> => api.get('/oracle/predictions', { params }),
  run:         (): Promise<Response<unknown>> => api.post('/oracle/run'),
  acknowledge: (id: Id): Promise<Response<unknown>> => api.post(`/oracle/predictions/${id}/acknowledge`),
}
