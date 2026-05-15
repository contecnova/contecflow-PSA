/**
 * Contracts + work orders.
 */
import { api } from './client'
import type { Id, JsonBody, Params, Response } from './types'

export const contractsApi = {
  list:                  (params?: Params): Promise<Response<unknown>> => api.get('/contracts', { params }),
  get:                   (id: Id): Promise<Response<unknown>> => api.get(`/contracts/${id}`),
  create:                (data: JsonBody): Promise<Response<unknown>> => api.post('/contracts', data),
  update:                (id: Id, data: JsonBody): Promise<Response<unknown>> => api.patch(`/contracts/${id}`, data),
  delete:                (id: Id): Promise<Response<unknown>> => api.delete(`/contracts/${id}`),
  workOrders:            (id: Id): Promise<Response<unknown>> => api.get(`/contracts/${id}/work-orders`),
  createWorkOrder:       (id: Id, data: JsonBody): Promise<Response<unknown>> =>
    api.post(`/contracts/${id}/work-orders`, data),
  updateWorkOrderStatus: (id: Id, woId: Id, status: string): Promise<Response<unknown>> =>
    api.patch(`/contracts/${id}/work-orders/${woId}/status`, null, { params: { status } }),
}
