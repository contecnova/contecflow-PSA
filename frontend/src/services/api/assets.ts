/**
 * ALM — assets, licenses, vendors + extended (contracts, cost-centers, compliance).
 */
import { api } from './client'
import type { Id, JsonBody, Params, Response } from './types'

export const assetsApi = {
  list:   (params?: Params): Promise<Response<unknown>> => api.get('/alm/assets', { params }),
  get:    (id: Id): Promise<Response<unknown>> => api.get(`/alm/assets/${id}`),
  create: (data: JsonBody): Promise<Response<unknown>> => api.post('/alm/assets', data),
  update: (id: Id, data: JsonBody): Promise<Response<unknown>> => api.patch(`/alm/assets/${id}`, data),
  delete: (id: Id): Promise<Response<unknown>> => api.delete(`/alm/assets/${id}`),
  cmdb:   (id: Id): Promise<Response<unknown>> => api.get(`/alm/assets/${id}/cmdb`),
}

export const licensesApi = {
  list:   (params?: Params): Promise<Response<unknown>> => api.get('/alm/licenses', { params }),
  get:    (id: Id): Promise<Response<unknown>> => api.get(`/alm/licenses/${id}`),
  create: (data: JsonBody): Promise<Response<unknown>> => api.post('/alm/licenses', data),
  update: (id: Id, data: JsonBody): Promise<Response<unknown>> => api.patch(`/alm/licenses/${id}`, data),
  delete: (id: Id): Promise<Response<unknown>> => api.delete(`/alm/licenses/${id}`),
  assign: (id: Id, data: JsonBody): Promise<Response<unknown>> => api.post(`/alm/licenses/${id}/assign`, data),
  revoke: (id: Id, uid: Id): Promise<Response<unknown>> => api.delete(`/alm/licenses/${id}/users/${uid}`),
}

export const vendorsApi = {
  list:   (params?: Params): Promise<Response<unknown>> => api.get('/alm/vendors', { params }),
  get:    (id: Id): Promise<Response<unknown>> => api.get(`/alm/vendors/${id}`),
  create: (data: JsonBody): Promise<Response<unknown>> => api.post('/alm/vendors', data),
  update: (id: Id, data: JsonBody): Promise<Response<unknown>> => api.patch(`/alm/vendors/${id}`, data),
  delete: (id: Id): Promise<Response<unknown>> => api.delete(`/alm/vendors/${id}`),
}

export const almExtApi = {
  dashboard:        (): Promise<Response<unknown>> => api.get('/alm/dashboard'),
  contracts:        (): Promise<Response<unknown>> => api.get('/alm/contracts'),
  createContract:   (data: JsonBody): Promise<Response<unknown>> => api.post('/alm/contracts', data),
  updateContract:   (id: Id, data: JsonBody): Promise<Response<unknown>> => api.patch(`/alm/contracts/${id}`, data),
  deleteContract:   (id: Id): Promise<Response<unknown>> => api.delete(`/alm/contracts/${id}`),
  costCenters:      (): Promise<Response<unknown>> => api.get('/alm/cost-centers'),
  createCostCenter: (data: JsonBody): Promise<Response<unknown>> => api.post('/alm/cost-centers', data),
  updateCostCenter: (id: Id, data: JsonBody): Promise<Response<unknown>> => api.patch(`/alm/cost-centers/${id}`, data),
  deleteCostCenter: (id: Id): Promise<Response<unknown>> => api.delete(`/alm/cost-centers/${id}`),
  compliance:       (): Promise<Response<unknown>> => api.get('/alm/compliance'),
}
