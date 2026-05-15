/**
 * AI modules — meetings, contracts, voice, smart-schedule, semantic, Nexus agent, providers.
 */
import { api } from './client'
import type { Id, JsonBody, Response } from './types'

export const meetingsAIApi = {
  list:        (): Promise<Response<unknown>> => api.get('/ai-modules/meetings'),
  get:         (id: Id): Promise<Response<unknown>> => api.get(`/ai-modules/meetings/${id}`),
  process:     (data: JsonBody): Promise<Response<unknown>> => api.post('/ai-modules/meetings/process', data),
  createTasks: (id: Id): Promise<Response<unknown>> => api.post(`/ai-modules/meetings/${id}/create-tasks`, {}),
}

export const contractsAIApi = {
  list:       (params?: Record<string, unknown>): Promise<Response<unknown>> => api.get('/ai-modules/contracts-ai', { params }),
  get:        (id: Id): Promise<Response<unknown>> => api.get(`/ai-modules/contracts-ai/${id}`),
  analyze:    (data: JsonBody): Promise<Response<unknown>> => api.post('/ai-modules/contracts-ai/analyze', data),
  analyzePdf: (formData: FormData): Promise<Response<unknown>> =>
    api.post('/ai-modules/contracts-ai/analyze-pdf', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    }),
}

export const voiceApi = {
  transcribe: (formData: FormData): Promise<Response<unknown>> =>
    api.post('/ai-modules/voice/transcribe', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    }),
  command:    (data: JsonBody): Promise<Response<unknown>> => api.post('/ai-modules/voice/command', data),
}

export const smartScheduleApi = {
  suggest: (data: JsonBody): Promise<Response<unknown>> => api.post('/ai-modules/smart-schedule', data),
}

export const semanticApi = {
  suggestTask:       (data: JsonBody): Promise<Response<unknown>> => api.post('/semantic/suggest/task', data),
  suggestTicket:     (data: JsonBody): Promise<Response<unknown>> => api.post('/semantic/suggest/ticket', data),
  estimateEffort:    (data: JsonBody): Promise<Response<unknown>> => api.post('/semantic/estimate/effort', data),
  estimateSprint:    (data: JsonBody): Promise<Response<unknown>> =>
    api.post('/semantic/estimate/sprint-backlog', data),
  profiles:          (): Promise<Response<unknown>> => api.get('/semantic/profiles'),
  createProfile:     (data: JsonBody): Promise<Response<unknown>> => api.post('/semantic/profiles', data),
  config:            (): Promise<Response<unknown>> => api.get('/semantic/config'),
  updateConfig:      (data: JsonBody): Promise<Response<unknown>> => api.patch('/semantic/config', data),
  stats:             (): Promise<Response<unknown>> => api.get('/semantic/stats'),
  autoGenerate:      (): Promise<Response<unknown>> => api.post('/semantic/profiles/auto-generate'),
  rebuildEmbeddings: (): Promise<Response<unknown>> => api.post('/semantic/profiles/rebuild-embeddings'),
  recordAssignment:  (data: JsonBody): Promise<Response<unknown>> => api.post('/semantic/record-assignment', data),
}

export const nexusAgentApi = {
  history:             (): Promise<Response<unknown>> => api.get('/ai/agent/history'),
  run:                 (instruction: string, autoApprove = true): Promise<Response<unknown>> =>
    api.post('/ai/agent', { instruction, auto_approve: autoApprove }),
  chat:                (data: JsonBody): Promise<Response<unknown>> => api.post('/ai/chat', data),
  listConversations:   (): Promise<Response<unknown>> => api.get('/ai/conversations'),
  getConversation:     (id: Id): Promise<Response<unknown>> => api.get(`/ai/conversations/${id}`),
  deleteConversations: (): Promise<Response<unknown>> => api.delete('/ai/conversations'),
}

export const aiProvidersApi = {
  list:        (): Promise<Response<unknown>> => api.get('/ai-providers'),
  catalog:     (): Promise<Response<unknown>> => api.get('/ai-providers/catalog'),
  stats:       (): Promise<Response<unknown>> => api.get('/ai-providers/stats'),
  diagnostics: (): Promise<Response<unknown>> => api.get('/ai-providers/diagnostics'),
  create:      (data: JsonBody): Promise<Response<unknown>> => api.post('/ai-providers', data),
  update:      (id: Id, data: JsonBody): Promise<Response<unknown>> => api.patch(`/ai-providers/${id}`, data),
  delete:      (id: Id): Promise<Response<unknown>> => api.delete(`/ai-providers/${id}`),
  test:        (id: Id): Promise<Response<unknown>> => api.post(`/ai-providers/${id}/test`),
  syncModels:  (id: Id): Promise<Response<unknown>> => api.post(`/ai-providers/${id}/sync-models`),
  setDefault:  (id: Id): Promise<Response<unknown>> => api.post(`/ai-providers/${id}/set-default`),
  syncAll:     (): Promise<Response<unknown>> => api.post('/ai-providers/sync-models/all'),
}
