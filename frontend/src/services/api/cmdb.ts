/**
 * CMDB — items, categories, relations, topology, agents, 3D graph.
 */
import { api } from './client'
import type { Id, JsonBody, Params, Response } from './types'

export const cmdbApi = {
  items:          (params?: Params): Promise<Response<unknown>> => api.get('/cmdb/items', { params }),
  getItem:        (id: Id): Promise<Response<unknown>> => api.get(`/cmdb/items/${id}`),
  createItem:     (data: JsonBody): Promise<Response<unknown>> => api.post('/cmdb/items', data),
  updateItem:     (id: Id, data: JsonBody): Promise<Response<unknown>> => api.patch(`/cmdb/items/${id}`, data),
  deleteItem:     (id: Id): Promise<Response<unknown>> => api.delete(`/cmdb/items/${id}`),
  changelog:      (id: Id): Promise<Response<unknown>> => api.get(`/cmdb/items/${id}/changelog`),
  categories:     (): Promise<Response<unknown>> => api.get('/cmdb/categories'),
  relations:      (id: Id): Promise<Response<unknown>> => api.get(`/cmdb/items/${id}/relations`),
  createRelation: (data: JsonBody): Promise<Response<unknown>> => api.post('/cmdb/relations', data),
  deleteRelation: (id: Id): Promise<Response<unknown>> => api.delete(`/cmdb/relations/${id}`),
  topology:       (id: Id, r?: number): Promise<Response<unknown>> =>
    api.get(`/sd/cmdb/${id}/topology`, { params: { radius: r } }),
  topologyItems:  (): Promise<Response<unknown>> => api.get('/sd/cmdb'),
  sdList:         (params?: Params): Promise<Response<unknown>> => api.get('/sd/cmdb', { params }),
  sdGet:          (id: Id): Promise<Response<unknown>> => api.get(`/sd/cmdb/${id}`),
  sdCreate:       (data: JsonBody): Promise<Response<unknown>> => api.post('/sd/cmdb', data),
  sdUpdate:       (id: Id, data: JsonBody): Promise<Response<unknown>> => api.patch(`/sd/cmdb/${id}`, data),
  sdRelations:    (id: Id): Promise<Response<unknown>> => api.get(`/sd/cmdb/${id}/relations`),
  sdImpact:       (id: Id): Promise<Response<unknown>> => api.get(`/sd/cmdb/${id}/impact`),
  agents:         (): Promise<Response<unknown>> => api.get('/sd/cmdb/agents'),
  registerAgent:  (data: JsonBody): Promise<Response<unknown>> => api.post('/sd/cmdb/agents/register', data),
  deleteAgent:    (id: Id): Promise<Response<unknown>> => api.delete(`/sd/cmdb/agents/${id}`),
  agentDashboard: (agentId: Id, days?: number): Promise<Response<unknown>> =>
    api.get(`/cmdb/agent-dashboard/${agentId}?days=${days ?? ''}`),
  agentSnapshot:  (agentId: Id): Promise<Response<unknown>> => api.post(`/cmdb/agent-dashboard/${agentId}/snapshot`),
  assetsByCI:     (ciId: Id): Promise<Response<unknown>> => api.get(`/sd/assets/by-ci/${ciId}`),
}

export const cmdb3dApi = {
  getGraph:    (params?: Params): Promise<Response<unknown>> => api.get('/sd/cmdb/3d-graph', { params }),
  blastRadius: (ciId: Id): Promise<Response<unknown>> => api.get(`/sd/cmdb/blast-radius/${ciId}`),
  createLink:  (data: JsonBody): Promise<Response<unknown>> => api.post('/sd/cmdb/asset-links', data),
  listLinks:   (params?: Params): Promise<Response<unknown>> => api.get('/sd/cmdb/asset-links', { params }),
  getImpact:   (assetId: Id): Promise<Response<unknown>> => api.get(`/sd/cmdb/asset-impact/${assetId}`),
}
